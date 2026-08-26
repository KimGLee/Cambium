"""Strict current/legacy boundaries for the K00 Control registry."""

import ast
import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import audit_dimension_contract
import control_registry_contract
import kblib
from queue_runtime import gate_registry


class ControlRegistryContractTests(unittest.TestCase):
    def document(self):
        return copy.deepcopy(kblib.load_yaml_file(
            REPOSITORY /
            control_registry_contract.STANDARDS_GATE_REGISTRY_PATH))

    def parse(self, document):
        return control_registry_contract.parse_control_registry_document(
            document)

    def test_profile_and_runtime_share_one_independent_parser(self):
        self.assertIs(
            gate_registry.parse_control_registry_document,
            control_registry_contract.parse_control_registry_document)
        self.assertIs(
            gate_registry.parse_standards_gate_registry,
            control_registry_contract.parse_standards_gate_registry)
        profile_source = (TOOLS / "profile_contract.py").read_text(
            encoding="utf-8")
        self.assertIn("import control_registry_contract", profile_source)
        self.assertNotIn("queue_runtime", profile_source)
        contract_source = (TOOLS / "control_registry_contract.py").read_text(
            encoding="utf-8")
        self.assertNotIn("import check_profile", contract_source)
        self.assertNotIn("from queue_runtime", contract_source)

    def gate(self, document, gate_id="wiki-link-integrity"):
        return next(row for row in document["gates"]
                    if row["gate_id"] == gate_id)

    def test_every_gate_has_exactly_one_revalidation_projection(self):
        registry, capabilities, _metadata, errors = self.parse(
            self.document())
        self.assertEqual([], errors)
        self.assertEqual(set(registry), set(capabilities))
        self.assertEqual(len(registry), len(self.document()["gates"]))

    def test_every_machine_gate_has_one_human_risk_explanation(self):
        registry, _capabilities, _metadata, errors = self.parse(
            self.document())
        self.assertEqual([], errors)
        prose_path = control_registry_contract.\
            LEGACY_STANDARDS_GATE_REGISTRY_PATH
        prose = (REPOSITORY / prose_path).read_text(encoding="utf-8")
        section = prose.split("## Control Registry", 1)[1].split(
            "## Verification Set Contract", 1)[0]
        explained = set()
        for line in section.splitlines():
            if not line.startswith("| `"):
                continue
            explained.add(line.split("|", 2)[1].strip().strip("`"))
        self.assertEqual(set(registry), explained)

    def test_missing_and_duplicate_gate_rows_fail_closed(self):
        missing = self.document()
        self.gate(missing).pop("check")
        registry, _capabilities, _metadata, errors = self.parse(missing)
        self.assertNotIn("wiki-link-integrity", registry)
        self.assertTrue(any("fields are not closed" in item
                            for item in errors), errors)

        duplicate = self.document()
        duplicate["gates"].append(copy.deepcopy(duplicate["gates"][0]))
        _registry, _capabilities, _metadata, errors = self.parse(duplicate)
        self.assertTrue(any("repeats Gate ID profile-load" in item
                            for item in errors), errors)

    def test_invalid_gate_id_and_unknown_owner_fail_closed(self):
        invalid = self.document()
        self.gate(invalid)["gate_id"] = "Unknown Gate"
        _registry, _capabilities, _metadata, errors = self.parse(invalid)
        self.assertTrue(any("invalid Gate ID" in item for item in errors),
                        errors)

        unknown_owner = self.document()
        self.gate(unknown_owner)["revalidation_owner"] = "missing-owner"
        _registry, _capabilities, _metadata, errors = self.parse(unknown_owner)
        self.assertTrue(any("must project to a distinct native owner" in item
                            for item in errors), errors)

    def test_selector_markers_cannot_mix_or_replace_exact_identity(self):
        document = self.document()
        row = self.gate(document)
        row["tool"] = "*"
        row["dimensions"] = ["*", "structure_and_links"]
        _registry, _capabilities, _metadata, errors = self.parse(document)
        self.assertTrue(any("must be exact" in item for item in errors), errors)
        self.assertTrue(any("mixes a Dimension marker" in item
                            for item in errors), errors)

    def test_none_dimension_cannot_be_claimed_by_a_named_producer(self):
        registry, _capabilities, _metadata, errors = self.parse(
            self.document())
        self.assertEqual([], errors)
        registry["wiki-link-integrity"]["dimensions"] = ("none",)
        producer_errors = gate_registry.gate_registry_producer_errors(registry)
        self.assertTrue(any(
            "Dimension none against named producer check_links" in item
            for item in producer_errors), producer_errors)

    def test_invalid_role_edge_scope_and_binding_are_each_rejected(self):
        cases = (
            ("revalidation_role", "unknown-role", "unknown revalidation role"),
            ("claim_edge", "unknown-edge", "unknown claim edge"),
            ("scope_protocol", "unknown-scope", "unknown scope protocol"),
            ("binding_protocol", "unknown-binding",
             "unknown binding protocol"),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                document = self.document()
                self.gate(document)[field] = value
                _registry, _capabilities, _metadata, errors = \
                    self.parse(document)
                self.assertTrue(any(expected in item for item in errors),
                                errors)

    def test_current_yaml_parser_never_falls_back_to_legacy_markdown(self):
        legacy = (
            "# Archived Control Registry\n\n"
            "## Stable Gate ID Registry\n\n"
            "| Gate ID | Tool | Tool version | Check | Mode | Dimension | Lifecycle |\n"
            "|---|---|---|---|---|---|---|\n"
            "| `legacy-gate` | `legacy_tool` | `1.0.0` | `legacy-check` | `*` | `*` | `not-batch-scoped` |\n"
        )
        legacy_registry, legacy_errors = \
            control_registry_contract.\
            parse_legacy_standards_gate_registry_markdown(legacy)
        self.assertEqual([], legacy_errors)
        self.assertIn("legacy-gate", legacy_registry)
        current_registry, current_errors = \
            control_registry_contract.parse_standards_gate_registry(legacy)
        self.assertEqual({}, current_registry)
        self.assertTrue(current_errors)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit_target = root / audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH
            audit_target.parent.mkdir(parents=True)
            shutil.copy2(
                REPOSITORY /
                audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH,
                audit_target)
            legacy_target = root / control_registry_contract.\
                LEGACY_STANDARDS_GATE_REGISTRY_PATH
            legacy_target.parent.mkdir(parents=True, exist_ok=True)
            legacy_target.write_text(legacy, encoding="utf-8")
            loaded, _capabilities, _metadata, errors = \
                control_registry_contract.load_current_control_contract(root)
        self.assertEqual({}, loaded)
        self.assertTrue(any("control-registry.yaml" in item
                            for item in errors), errors)

    def test_production_python_does_not_redeclare_closed_vocabularies(self):
        closed_sets = (
            set(audit_dimension_contract.BASE_RECEIPT_DIMENSIONS),
            set(audit_dimension_contract.EVIDENCE_ROLES),
            set(self.document()["closed_sets"]["revalidation_roles"]),
            set(self.document()["closed_sets"]["claim_edges"]),
            set(self.document()["closed_sets"]["scope_protocols"]),
            set(self.document()["closed_sets"]["binding_protocols"]),
        )
        duplicates = []
        for path in sorted(TOOLS.rglob("*.py")):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                    continue
                values = []
                for element in node.elts:
                    if not isinstance(element, ast.Constant) or \
                            not isinstance(element.value, str):
                        break
                    values.append(element.value)
                else:
                    if any(set(values) == closed for closed in closed_sets):
                        duplicates.append(
                            "%s:%d" % (path.relative_to(REPOSITORY),
                                       node.lineno))
        self.assertEqual([], duplicates)

    def test_machine_shape_constants_exist_only_in_the_contract_parser(self):
        names = {
            "_CONTROL_REQUIRED_FIELDS", "_CONTROL_CLOSED_SET_FIELDS",
            "_GATE_FIELDS", "_ROLE_CONTRACT_FIELDS",
        }
        owners = {name: [] for name in names}
        for path in sorted(TOOLS.rglob("*.py")):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) \
                    else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        owners[target.id].append(
                            str(path.relative_to(REPOSITORY)))
        expected = ["Tools/control_registry_contract.py"]
        self.assertEqual(
            {name: expected for name in names}, owners)

    def test_k00_prose_no_longer_contains_machine_tables(self):
        prose_path = control_registry_contract.\
            LEGACY_STANDARDS_GATE_REGISTRY_PATH
        text = (REPOSITORY / prose_path).read_text(encoding="utf-8")
        self.assertNotIn("| Gate ID | Tool | Tool version | Check | Mode |",
                         text)
        self.assertNotIn("| Gate ID | Role | Owner | Claim edge |", text)


if __name__ == "__main__":
    unittest.main()
