"""Owner-to-consumer projection checks for Card, Read Set, and Profile layout.

These tests deliberately change owner values in isolated repository copies.
A consumer that keeps a second directory, index, type, mode, or phase-field
literal will fail even though the owner and its data agree.  The AST guard
also prevents the retired compatibility constants from reappearing under
their old public names.
"""

import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import card_activation  # noqa: E402
import card_contract  # noqa: E402
import profile_layout_contract  # noqa: E402
import profile_onboarding_status  # noqa: E402
import read_set_contract  # noqa: E402
import scaffold_profile  # noqa: E402
import stamp_cards  # noqa: E402
from queue_runtime import task_contract  # noqa: E402


def _replace_once(path, old, new):
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise AssertionError(
            "%s expected one %r anchor, found %d" %
            (path, old, text.count(old)))
    path.write_text(text.replace(old, new), encoding="utf-8")


def _top_level_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


class ProjectionFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        for name in ("Card", "Read Set", "kernel"):
            shutil.copytree(REPOSITORY / name, self.root / name)
        (self.root / "Tools").mkdir()
        shutil.copy2(TOOLS / "module-boundaries.yaml",
                     self.root / "Tools/module-boundaries.yaml")

    def refresh_card_review_bindings(self):
        cards, _read_sets = stamp_cards.discover_cards(self.root)
        for record in cards.values():
            expected_source = stamp_cards.source_digest(
                self.root, record["source_files"])
            text = record["text"]
            text = stamp_cards.replace_frontmatter_scalar(
                text, "source_hash", expected_source)
            text = stamp_cards.replace_frontmatter_scalar(
                text, "reviewed_source_hash", expected_source)
            text = stamp_cards.replace_frontmatter_scalar(
                text, "reviewed_card_hash", record["body_hash"])
            (self.root / record["path"]).write_text(text, encoding="utf-8")


class CardProjectionTests(ProjectionFixture):
    def test_card_consumers_follow_schema_directory_type_and_mode(self):
        schema_path = self.root / card_contract.SCHEMA_PATH
        _replace_once(schema_path, 'document_type: card',
                      'document_type: action-card')
        _replace_once(schema_path, 'generation_mode: curated',
                      'generation_mode: reviewed')
        _replace_once(schema_path, 'path_prefix: "Card/"',
                      'path_prefix: "Action Card/"')

        target = self.root / "Action Card"
        target.mkdir()
        for path in sorted((self.root / "Card").glob("*.md")):
            shutil.move(str(path), target / path.name)
        for path in sorted(target.glob("R*.md")):
            text = path.read_text(encoding="utf-8")
            text = text.replace("type: card", "type: action-card", 1)
            text = text.replace(
                "generation_mode: curated", "generation_mode: reviewed", 1)
            path.write_text(text, encoding="utf-8")

        schema = card_contract.load_schema(self.root)
        cards, read_sets = stamp_cards.discover_cards(self.root)
        registry, _fingerprint = card_activation._route_registry(self.root)

        self.assertEqual("Action Card", schema["directory"])
        self.assertEqual(set(read_sets), set(cards))
        self.assertEqual(set(cards), set(registry))
        self.assertTrue(all(
            record["path"].startswith(schema["path_prefix"])
            for record in cards.values()))

    def test_both_generated_index_paths_come_from_their_schemas(self):
        self.refresh_card_review_bindings()
        card_schema_path = self.root / card_contract.SCHEMA_PATH
        read_schema_path = self.root / read_set_contract.SCHEMA_PATH
        _replace_once(card_schema_path, 'index_name: "Card Index.md"',
                      'index_name: "Cards Navigation.md"')
        _replace_once(read_schema_path,
                      'index_name: "Read Sets Index.md"',
                      'index_name: "Loading Navigation.md"')
        (self.root / "Card/Card Index.md").rename(
            self.root / "Card/Cards Navigation.md")
        (self.root / "Read Set/Read Sets Index.md").rename(
            self.root / "Read Set/Loading Navigation.md")

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = stamp_cards.main([str(self.root), "--check"])

        self.assertEqual(0, exit_code, output.getvalue())
        self.assertEqual(
            "Card/Cards Navigation.md",
            card_contract.load_schema(self.root)["index_path"])
        self.assertEqual(
            "Read Set/Loading Navigation.md",
            read_set_contract.load_schema(self.root)["index_path"])


class ReadSetProjectionTests(ProjectionFixture):
    def test_consumers_follow_schema_layout_type_and_phase_field_order(self):
        schema_path = self.root / read_set_contract.SCHEMA_PATH
        _replace_once(schema_path, 'document_type: read-set',
                      'document_type: route-load')
        _replace_once(schema_path, 'path_prefix: "Read Set/"',
                      'path_prefix: "Runtime Read/"')
        _replace_once(
            schema_path,
            "phase_fields:\n  - phase_id\n  - conditional\n  - standard\n  - trigger",
            "phase_fields:\n  - trigger\n  - standard\n  - conditional\n  - phase_id",
        )

        target = self.root / "Runtime Read"
        target.mkdir()
        for path in sorted((self.root / "Read Set").glob("*.md")):
            shutil.move(str(path), target / path.name)
        for path in sorted(target.glob("R*.md")):
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("type: read-set", "type: route-load", 1),
                encoding="utf-8")
        for path in sorted((self.root / "Card").glob("R*.md")):
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("Read Set/", "Runtime Read/"),
                encoding="utf-8")

        schema = read_set_contract.load_schema(self.root)
        records = read_set_contract.discover(self.root, schema=schema)
        cards, paired = stamp_cards.discover_cards(self.root)
        selected = [records["R01"]["path"]]
        closure = task_contract.read_set_load_closure(self.root, selected)

        self.assertEqual("Runtime Read", schema["directory"])
        self.assertEqual(
            ["trigger", "standard", "conditional", "phase_id"],
            schema["phase_fields"])
        self.assertEqual(set(records), set(cards))
        self.assertEqual(set(records), set(paired))
        self.assertIn(selected[0], closure[0])
        self.assertEqual([], closure[3])


class ProfileLayoutProjectionTests(unittest.TestCase):
    def test_manifest_parser_classifies_candidates_and_shipped_namespaces(self):
        candidate = profile_layout_contract.\
            validate_selectable_profile_manifest_path(
                "profiles/candidate/profile.md")
        self.assertEqual("candidate", candidate.profile_id)
        self.assertTrue(candidate.selectable)
        self.assertIsNone(candidate.reserved_namespace)

        example = profile_layout_contract.parse_profile_manifest_path(
            "profiles/examples/minimal-notes/profile.md")
        self.assertEqual("minimal-notes", example.profile_id)
        self.assertTrue(example.example)
        self.assertFalse(example.selectable)

        for template_id in profile_layout_contract.TEMPLATE_PROFILE_IDS:
            with self.subTest(template_id=template_id):
                location = profile_layout_contract.parse_profile_manifest_path(
                    profile_layout_contract.profile_manifest_relative(
                        template_id))
                self.assertEqual(template_id, location.reserved_namespace)
                with self.assertRaises(
                        profile_layout_contract.ProfileLayoutError):
                    profile_layout_contract.\
                        validate_selectable_profile_manifest_path(location.path)

        with self.assertRaises(profile_layout_contract.ProfileLayoutError):
            profile_layout_contract.parse_profile_manifest_path(
                "profiles/examples/profile.md")

    def test_both_profile_clis_consume_the_same_reserved_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profiles = root / profile_layout_contract.PROFILES_DIRECTORY
            for name in sorted(profile_layout_contract.RESERVED_PROFILE_IDS |
                               {"candidate"}):
                (profiles / name).mkdir(parents=True, exist_ok=True)

            self.assertEqual(
                ["candidate"],
                profile_onboarding_status.candidate_directories(str(root)))
            for reserved in profile_layout_contract.RESERVED_PROFILE_IDS:
                with self.subTest(reserved=reserved):
                    with self.assertRaises(scaffold_profile.ScaffoldRefusal):
                        scaffold_profile.validate_profile_id(reserved)


class NoDuplicateAuthorityTests(unittest.TestCase):
    def test_profile_manifest_filename_has_one_production_owner(self):
        duplicates = []
        for path in TOOLS.rglob("*.py"):
            if ("tests" in path.parts or
                    path.name == "profile_layout_contract.py"):
                continue
            tree = ast.parse(
                path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and
                        node.value ==
                        profile_layout_contract.PROFILE_MANIFEST_NAME):
                    duplicates.append("%s:%d" % (
                        path.relative_to(TOOLS), node.lineno))
        self.assertEqual([], duplicates)

    def test_retired_owner_constants_do_not_reappear_in_consumers(self):
        forbidden = {
            "read_set_contract.py": {"READ_SET_DIRECTORY", "INDEX_NAME"},
            "stamp_cards.py": {
                "DEFAULT_CARDS_DIR", "CARD_SCHEMA_PATH", "READ_SET_INDEX_PATH",
            },
            "card_activation.py": {"CARD_DIRECTORY"},
            "profile_onboarding_status.py": {"NON_CANDIDATE_DIRECTORIES"},
            "scaffold_profile.py": {"RESERVED_PROFILE_IDS"},
        }
        for filename, names in forbidden.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    set(), names & _top_level_names(TOOLS / filename))

    def test_stamp_cards_exports_the_single_card_loader_for_compatibility(self):
        self.assertIs(stamp_cards.load_card_schema, card_contract.load_schema)
        self.assertIs(stamp_cards.CardContractError,
                      card_contract.CardContractError)

    def test_read_set_path_consumers_do_not_read_a_deployed_literal_alias(self):
        for relative in ("check_proof.py", "queue_runtime/task_contract.py"):
            with self.subTest(relative=relative):
                text = (TOOLS / relative).read_text(encoding="utf-8")
                self.assertNotIn("READ_SET_DIRECTORY", text)


if __name__ == "__main__":
    unittest.main()
