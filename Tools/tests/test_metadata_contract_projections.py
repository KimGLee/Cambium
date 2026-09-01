"""Prevent metadata owner shapes from becoming consumer-side literals."""

import ast
import copy
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.knowledge.metadata.metadata_page_state_contract as metadata_page_state_contract
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.platform.common.kblib as kblib


REPOSITORY = TOOLS.parent


def assignment_value(module, name):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    values = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name
               for target in targets):
            values.append(node.value)
    if len(values) != 1:
        raise AssertionError("expected one assignment for %s" % name)
    return values[0]


class MetadataContractProjectionTests(unittest.TestCase):
    def test_owner_record_shape_is_one_identity_preserving_projection(self):
        keys = metadata_execution_contract.source_adapter_owner_record_keys(
            "coverage-property-state-v1")
        self.assertEqual(
            {"content_fingerprint", "evidence_receipt", "value"}, keys)
        self.assertIs(
            keys, metadata_execution_contract.source_adapter_owner_record_keys(
                "coverage-property-state-v1"))
        self.assertIs(keys, metadata_property_state.PROPERTY_RECORD_KEYS)
        self.assertIs(
            keys, metadata_page_state_contract.PROPERTY_STATE_FIELDS)
        with self.assertRaises(ValueError):
            metadata_execution_contract.source_adapter_owner_record_keys(
                "unregistered-adapter-v1")

    def test_value_shape_projection_has_owner_identity(self):
        self.assertIs(
            metadata_execution_contract.VALUE_SHAPES,
            metadata_page_state_contract.VALUE_SHAPES)

    def test_consumer_assignments_are_owner_projections_not_literals(self):
        direct_aliases = (
            (metadata_page_state_contract, "VALUE_SHAPES",
             "metadata_execution_contract", "VALUE_SHAPES"),
        )
        for module, name, owner, symbol in direct_aliases:
            with self.subTest(module=module.__name__, name=name):
                value = assignment_value(module, name)
                self.assertIsInstance(value, ast.Attribute)
                self.assertEqual(owner, value.value.id)
                self.assertEqual(symbol, value.attr)

        for module, name in (
                (metadata_page_state_contract, "PROPERTY_STATE_FIELDS"),
                (metadata_property_state, "PROPERTY_RECORD_KEYS")):
            with self.subTest(module=module.__name__, name=name):
                value = assignment_value(module, name)
                self.assertIsInstance(value, ast.Call)
                self.assertIsInstance(value.func, ast.Attribute)
                self.assertEqual(
                    "metadata_execution_contract", value.func.value.id)
                self.assertEqual(
                    "source_adapter_owner_record_keys", value.func.attr)

    def test_invocation_owners_are_top_level_declared_cli_tools(self):
        capabilities = metadata_execution_contract.load_operation_capabilities(
            REPOSITORY)
        policy = kblib.load_yaml_file(
            REPOSITORY / "Tools/agent-interface-policy.yaml")
        policy_tools = {row["tool"] for row in policy["tools"]}

        for entry in capabilities["capabilities"]:
            path = entry.get("invocation_owner")
            if path is None:
                continue
            self.assertRegex(path, r"^Tools/[a-z][a-z0-9_]*\.py$")
            self.assertIn(Path(path).stem, policy_tools)

    def test_nested_invocation_owner_is_rejected_before_basename_routing(self):
        document = copy.deepcopy(
            metadata_execution_contract.load_operation_capabilities(
                REPOSITORY))
        entry = next(row for row in document["capabilities"]
                     if row.get("invocation_owner"))
        nested = "Tools/queue_runtime/invoke.py"
        old = entry["invocation_owner"]
        entry["invocation_owner"] = nested
        for field in ("writers", "checkers", "consumers"):
            entry[field] = [nested if value == old else value
                            for value in entry[field]]
        if entry["implementation_owner"] == old:
            entry["consumers"].append(nested)

        with self.assertRaisesRegex(
                metadata_execution_contract.MetadataExecutionContractError,
                "top-level"):
            metadata_execution_contract.validate_operation_capabilities_document(
                document)

    def test_shared_manual_attestation_has_no_fake_unique_cli(self):
        entry = metadata_execution_contract.capability_entry_by_id(
            "manual-attestation-v1", root=REPOSITORY)
        self.assertNotIn("invocation_owner", entry)
        with self.assertRaisesRegex(ValueError, "invocation owner"):
            metadata_execution_contract.capability_invocation_tool(
                "manual-attestation-v1", root=REPOSITORY)


if __name__ == "__main__":
    unittest.main()
