"""Owner-to-consumer checks for distributed component layout projections.

The serialized Card, Read Set, and Profile layout contracts are the machine
owners. Contract tests exercise those owners and their direct consumers
without copying a repository. One integration test builds a single-route
repository from the owner documents and proves that discovery, activation,
load-closure resolution, and generated navigation consume the same changed
layout. A single negative contract keeps the retired compatibility surface
from becoming public again.
"""

import ast
from contextlib import contextmanager, redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.check_proof as check_proof  # noqa: E402
import Tools.execution.context_delivery.card_activation as card_activation  # noqa: E402
import Tools.execution.context_delivery.card_contract as card_contract  # noqa: E402
import Tools.execution.context_delivery.read_set_contract as read_set_contract  # noqa: E402
import Tools.execution.planning.apply_task_plan as apply_task_plan  # noqa: E402
import Tools.governance.profile.profile_layout_contract as profile_layout_contract  # noqa: E402
import Tools.governance.profile.profile_onboarding_status as profile_onboarding_status  # noqa: E402
import Tools.governance.profile.scaffold_profile as scaffold_profile  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.distribution.stamp_cards as stamp_cards  # noqa: E402
from Tools.execution.task_runtime.queue_runtime import task_contract  # noqa: E402


SOURCE = "kernel/K00 Fixture.md"
READ_SET = "Runtime Read/R01 Fixture Read Set.md"
CARD = "Action Card/R01 Fixture Card.md"


def _replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise AssertionError(
            "%s expected one %r anchor, found %d" %
            (label, old, text.count(old)))
    return text.replace(old, new)


def _write(root, relative, text):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


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


@contextmanager
def _changed_layout_root():
    """Yield one route materialized from deliberately changed owner values."""
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)

        card_schema_text = (REPOSITORY / card_contract.SCHEMA_PATH).read_text(
            encoding="utf-8")
        for old, new in (
                ("document_type: card", "document_type: action-card"),
                ("generation_mode: curated", "generation_mode: reviewed"),
                ('path_prefix: "Card/"', 'path_prefix: "Action Card/"'),
                ('index_name: "Card Index.md"',
                 'index_name: "Cards Navigation.md"')):
            card_schema_text = _replace_once(
                card_schema_text, old, new, card_contract.SCHEMA_PATH)
        _write(root, card_contract.SCHEMA_PATH, card_schema_text)

        read_schema_text = (REPOSITORY / read_set_contract.SCHEMA_PATH).read_text(
            encoding="utf-8")
        for old, new in (
                ("document_type: read-set", "document_type: route-load"),
                ('path_prefix: "Read Set/"',
                 'path_prefix: "Runtime Read/"'),
                ('index_name: "Read Sets Index.md"',
                 'index_name: "Loading Navigation.md"'),
                ("phase_fields:\n  - phase_id\n  - conditional\n"
                 "  - standard\n  - trigger",
                 "phase_fields:\n  - trigger\n  - standard\n"
                 "  - conditional\n  - phase_id")):
            read_schema_text = _replace_once(
                read_schema_text, old, new, read_set_contract.SCHEMA_PATH)
        _write(root, read_set_contract.SCHEMA_PATH, read_schema_text)
        _write(
            root, stamp_cards.CARD_BUDGET_PATH,
            (REPOSITORY / stamp_cards.CARD_BUDGET_PATH).read_text(
                encoding="utf-8"),
        )

        card_schema = card_contract.load_schema(root)
        read_schema = read_set_contract.load_schema(root)
        _write(root, SOURCE, "# Fixture source\n")
        declaration = {
            "type": read_schema["document_type"],
            "schema_version": read_schema["schema_version"],
            "route_id": "R01",
            "activation_phase": "batch-preflight",
            "narrowable": False,
            "load_edges": [{
                "edge_id": "R01:start",
                "kind": "required",
                "phase_id": "batch-preflight",
                "trigger_id": "route-selected",
                "targets": [SOURCE],
                "read_sets": [],
            }],
        }
        _write(
            root, READ_SET,
            "---\n%s---\n# Fixture Read Set\n\n"
            "## Purpose\n\nFixture loading boundary.\n\n"
            "## Non-deterministic triggers\n\nNone.\n" %
            kblib.canonical_yaml(declaration),
        )

        body = (
            "# Fixture Card\n\n"
            "## Purpose\n\nFixture action projection.\n\n"
            "## Actions\n\n- Read the declared source.\n\n"
            "## Stop or escalate\n\nStop when the source is stale.\n\n"
            "## Read-back hook\n\nReturn to the declared Read Set.\n"
        )
        sources = [READ_SET, SOURCE]
        source_hash = stamp_cards.source_digest(root, sources)
        card_data = {
            "type": card_schema["document_type"],
            "generation_mode": card_schema["generation_mode"],
            "route_id": "R01",
            "read_set_id": "R01",
            "read_set": READ_SET,
            "source_files": sources,
            "source_hash": source_hash,
            "reviewed_source_hash": source_hash,
            "reviewed_card_hash": "0" * 12,
        }
        provisional = "---\n%s---\n%s" % (
            kblib.canonical_yaml(card_data), body)
        card_data["reviewed_card_hash"] = stamp_cards.card_body_digest(
            provisional)
        _write(
            root, CARD,
            "---\n%s---\n%s" % (kblib.canonical_yaml(card_data), body),
        )

        cards, read_sets = stamp_cards.discover_cards(root)
        _write(
            root, card_schema["index_path"],
            stamp_cards.render_card_index(cards, read_sets),
        )
        _write(
            root, read_schema["index_path"],
            stamp_cards.render_read_set_index(read_sets),
        )
        yield root, card_schema, read_schema


class LayoutProjectionIntegrationTests(unittest.TestCase):
    def test_changed_owner_layout_reaches_every_direct_projection(self):
        with _changed_layout_root() as (root, card_schema, read_schema):
            cards, read_sets = stamp_cards.discover_cards(root)
            registry, _fingerprint = card_activation._route_registry(root)
            closure = task_contract.read_set_load_closure(root, [READ_SET])
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = stamp_cards.main([str(root), "--check"])

            self.assertEqual("Action Card", card_schema["directory"])
            self.assertEqual(
                "Action Card/Cards Navigation.md", card_schema["index_path"])
            self.assertEqual("Runtime Read", read_schema["directory"])
            self.assertEqual(
                "Runtime Read/Loading Navigation.md",
                read_schema["index_path"])
            self.assertEqual(
                ["trigger", "standard", "conditional", "phase_id"],
                read_schema["phase_fields"])
            self.assertEqual({"R01"}, set(cards))
            self.assertEqual({"R01"}, set(read_sets))
            self.assertEqual({"R01"}, set(registry))
            self.assertEqual({SOURCE}, closure[1])
            self.assertEqual([], closure[3])
            self.assertEqual(0, exit_code, output.getvalue())


class ProfileLayoutContractTests(unittest.TestCase):
    def test_owner_classifies_candidate_template_and_example_manifests(self):
        self.assertEqual(
            frozenset((profile_layout_contract.TEMPLATE_PROFILE_ID,)),
            profile_layout_contract.TEMPLATE_PROFILE_IDS)
        self.assertEqual(
            frozenset((profile_layout_contract.TEMPLATE_PROFILE_ID,
                       profile_layout_contract.EXAMPLES_PROFILE_ID)),
            profile_layout_contract.RESERVED_PROFILE_IDS)

        candidate = profile_layout_contract.\
            validate_selectable_profile_manifest_path(
                "profiles/candidate/profile.toml")
        self.assertEqual("candidate", candidate.profile_id)
        self.assertTrue(candidate.selectable)

        example = profile_layout_contract.parse_profile_manifest_path(
            "profiles/examples/worked-planning/profile.toml")
        self.assertEqual("worked-planning", example.profile_id)
        self.assertTrue(example.example)
        self.assertFalse(example.selectable)

        for template_id in profile_layout_contract.TEMPLATE_PROFILE_IDS:
            with self.subTest(template_id=template_id):
                location = profile_layout_contract.parse_profile_manifest_path(
                    "%s/%s" % (
                        profile_layout_contract.profile_relative(template_id),
                        profile_layout_contract.PROFILE_MANIFEST_NAME))
                self.assertEqual(template_id, location.reserved_namespace)
                with self.assertRaises(
                        profile_layout_contract.ProfileLayoutError):
                    profile_layout_contract.\
                        validate_selectable_profile_manifest_path(location.path)

        with self.assertRaises(profile_layout_contract.ProfileLayoutError):
            profile_layout_contract.parse_profile_manifest_path(
                "profiles/examples/profile.toml")

    def test_direct_consumers_use_the_owner_reserved_namespace_set(self):
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


class SingleOwnerContractTests(unittest.TestCase):
    def test_route_registry_consumers_share_the_current_projection(self):
        self.assertIs(
            stamp_cards.discover_cards,
            apply_task_plan.stamp_cards.discover_cards)
        self.assertIs(
            stamp_cards.discover_cards,
            check_proof.stamp_cards.discover_cards)
        self.assertIs(
            stamp_cards.discover_cards,
            card_activation.stamp_cards.discover_cards)
        self.assertFalse(hasattr(check_proof, "load_route_registry"))

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

    def test_retired_layout_aliases_and_exports_cannot_reappear(self):
        forbidden_names = {
            "execution/context_delivery/read_set_contract.py": {
                "READ_SET_DIRECTORY", "INDEX_NAME"},
            "platform/distribution/stamp_cards.py": {
                "DEFAULT_CARDS_DIR", "CARD_SCHEMA_PATH",
                "READ_SET_INDEX_PATH", "load_card_schema",
                "CardContractError"},
            "execution/context_delivery/card_activation.py": {
                "CARD_DIRECTORY"},
            "governance/profile/profile_onboarding_status.py": {
                "NON_CANDIDATE_DIRECTORIES"},
            "governance/profile/scaffold_profile.py": {
                "RESERVED_PROFILE_IDS"},
        }
        for filename, names in forbidden_names.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    set(), names & _top_level_names(TOOLS / filename))

        self.assertIs(
            stamp_cards._load_card_schema, card_contract.load_schema)
        self.assertIs(
            stamp_cards._CardContractError,
            card_contract.CardContractError)
        for relative in (
                "execution/audit/check_proof.py",
                "execution/task_runtime/queue_runtime/task_contract.py"):
            with self.subTest(relative=relative):
                text = (TOOLS / relative).read_text(encoding="utf-8")
                self.assertNotIn("READ_SET_DIRECTORY", text)


if __name__ == "__main__":
    unittest.main()
