from pathlib import Path
import shutil
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import read_set_contract
from queue_runtime import task_contract


class ReadSetMachineDeclarationTests(unittest.TestCase):
    @staticmethod
    def install_declaration_fixture(root):
        shutil.copytree(REPOSITORY / "Read Set", root / "Read Set")
        shutil.copytree(REPOSITORY / "kernel", root / "kernel")
        shutil.copytree(REPOSITORY / "Card", root / "Card")
        (root / "Tools").mkdir()
        shutil.copy2(REPOSITORY / "Tools/module-boundaries.yaml",
                     root / "Tools/module-boundaries.yaml")

    def test_shipped_declarations_cover_r01_through_r13(self):
        records = read_set_contract.discover(REPOSITORY)
        self.assertEqual(["R%02d" % number for number in range(1, 14)],
                         sorted(records))

    def test_body_links_do_not_change_machine_targets(self):
        record = read_set_contract.discover(REPOSITORY)["R01"]
        schema = read_set_contract.load_schema(REPOSITORY)
        before = read_set_contract.targets(record["declaration"])
        changed = record["text"] + "\n[[kernel/Not A Load Target]]\n"
        parsed = read_set_contract.parse_declaration(
            changed, record["path"], schema)
        self.assertEqual(before, read_set_contract.targets(parsed))

    def test_generated_index_is_not_parsed_as_a_registry(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.install_declaration_fixture(root)
        index = root / "Read Set/Read Sets Index.md"
        index.write_text("not yaml and not authoritative\n", encoding="utf-8")
        self.assertEqual(13, len(read_set_contract.discover(root)))

    def test_unknown_dependency_fails_closed(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.install_declaration_fixture(root)
        path = root / "Read Set/R01 Core Bootstrap Read Set.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("    read_sets: []",
                                     "    read_sets:\n      - R99", 1),
                        encoding="utf-8")
        with self.assertRaisesRegex(read_set_contract.ReadSetContractError,
                                    "unknown Read Set"):
            read_set_contract.discover(root)

    def test_body_shape_is_closed_to_purpose_and_trigger_explanation(self):
        record = read_set_contract.discover(REPOSITORY)["R01"]
        schema = read_set_contract.load_schema(REPOSITORY)
        changed = record["text"].replace(
            "## Non-deterministic triggers",
            "## Loading Rules\n\nSecond authority.\n\n"
            "## Non-deterministic triggers")
        with self.assertRaisesRegex(read_set_contract.ReadSetContractError,
                                    "body sections"):
            read_set_contract.parse_declaration(
                changed, record["path"], schema)

    def test_activation_phase_requires_a_matching_required_edge(self):
        record = read_set_contract.discover(REPOSITORY)["R01"]
        schema = read_set_contract.load_schema(REPOSITORY)
        changed = record["text"].replace(
            "activation_phase: batch-preflight",
            "activation_phase: governance")
        with self.assertRaisesRegex(read_set_contract.ReadSetContractError,
                                    "has no required load edge"):
            read_set_contract.parse_declaration(
                changed, record["path"], schema)

    def test_runtime_closure_uses_frontmatter_not_body_links(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.install_declaration_fixture(root)
        selected = ["Read Set/R01 Core Bootstrap Read Set.md"]
        before = task_contract.read_set_load_closure(root, selected)
        path = root / selected[0]
        path.write_text(path.read_text(encoding="utf-8") +
                        "\n[[kernel/Not A Load Target]]\n",
                        encoding="utf-8")
        after = task_contract.read_set_load_closure(root, selected)

        self.assertEqual(before, after)
        self.assertEqual([], before[3])

    def test_profile_supplemental_closure_uses_machine_load_edges(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.install_declaration_fixture(root)
        profile = root / "profiles/test"
        profile.mkdir(parents=True)
        (profile / "profile.md").write_text(
            "# Test Profile\n\n## Profile Identity\n\n"
            "- `profile_id`: `test`\n", encoding="utf-8")
        target = "kernel/K00 Standards Overview.md"
        relative = "profiles/test/P Supplemental Read Set.md"
        declaration = {
            "type": "profile-read-set",
            "schema_version": 1,
            "route_id": "P:test:supplemental",
            "activation_phase": "batch-preflight",
            "narrowable": True,
            "load_edges": [{
                "edge_id": "P:test:supplemental:start",
                "kind": "required",
                "phase_id": "batch-preflight",
                "trigger_id": "route-selected",
                "targets": [target],
                "read_sets": [],
            }],
        }
        import kblib
        (root / relative).write_text(
            "---\n%s---\n# Supplemental\n\n## Purpose\n\nFixture.\n\n"
            "## Non-deterministic triggers\n\n"
            "[[kernel/This Prose Link Is Not A Target]]\n" %
            kblib.canonical_yaml(declaration), encoding="utf-8")

        read_sets, modules, invalid, errors = (
            task_contract.read_set_load_closure(
                root, [relative], "profiles/test/profile.md",
                ["P:test:supplemental"]))

        self.assertEqual({relative}, read_sets)
        self.assertEqual({target}, modules)
        self.assertEqual(set(), invalid)
        self.assertEqual([], errors)

    def test_profile_supplemental_prose_cannot_replace_load_edges(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.install_declaration_fixture(root)
        profile = root / "profiles/test"
        profile.mkdir(parents=True)
        (profile / "profile.md").write_text(
            "# Test Profile\n\n## Profile Identity\n\n"
            "- `profile_id`: `test`\n", encoding="utf-8")
        relative = "profiles/test/P Supplemental Read Set.md"
        (root / relative).write_text(
            "---\ntype: profile-read-set\n"
            "route_id: P:test:supplemental\n---\n\n"
            "## Purpose\n\nFixture.\n\n"
            "## Non-deterministic triggers\n\n"
            "[[kernel/K00 Standards Overview]]\n",
            encoding="utf-8")

        _read_sets, _modules, _invalid, errors = (
            task_contract.read_set_load_closure(
                root, [relative], "profiles/test/profile.md",
                ["P:test:supplemental"]))

        self.assertTrue(any("declaration fields differ" in error
                            for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
