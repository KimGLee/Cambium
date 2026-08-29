"""Prevent metadata owner shapes from becoming consumer-side literals."""

import ast
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import metadata_execution_contract
import metadata_property_state
import project_page_state
from queue_runtime import property_state as runtime_property_state


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
        self.assertIs(keys, project_page_state.PROPERTY_STATE_FIELDS)
        with self.assertRaises(ValueError):
            metadata_execution_contract.source_adapter_owner_record_keys(
                "unregistered-adapter-v1")

    def test_value_shape_projection_has_owner_identity(self):
        self.assertIs(
            metadata_execution_contract.VALUE_SHAPES,
            project_page_state.VALUE_SHAPES)

    def test_legacy_shape_facade_has_owner_identity(self):
        self.assertEqual(
            metadata_property_state.LEGACY_PROPERTY_STATE,
            runtime_property_state.LEGACY_PROPERTY_STATE_FIELD)
        self.assertIs(
            metadata_property_state.LEGACY_PROPERTY_RECORD_KEYS,
            runtime_property_state.LEGACY_PROPERTY_RECORD_FIELDS)
        self.assertEqual(
            metadata_property_state.LEGACY_PROPERTY_STATUS,
            runtime_property_state.LEGACY_PROPERTY_STATUS)

    def test_consumer_assignments_are_owner_projections_not_literals(self):
        direct_aliases = (
            (project_page_state, "VALUE_SHAPES",
             "metadata_execution_contract", "VALUE_SHAPES"),
            (runtime_property_state, "LEGACY_PROPERTY_STATE_FIELD",
             "metadata_property_state", "LEGACY_PROPERTY_STATE"),
            (runtime_property_state, "LEGACY_PROPERTY_RECORD_FIELDS",
             "metadata_property_state", "LEGACY_PROPERTY_RECORD_KEYS"),
            (runtime_property_state, "LEGACY_PROPERTY_STATUS",
             "metadata_property_state", "LEGACY_PROPERTY_STATUS"),
        )
        for module, name, owner, symbol in direct_aliases:
            with self.subTest(module=module.__name__, name=name):
                value = assignment_value(module, name)
                self.assertIsInstance(value, ast.Attribute)
                self.assertEqual(owner, value.value.id)
                self.assertEqual(symbol, value.attr)

        for module, name in (
                (project_page_state, "PROPERTY_STATE_FIELDS"),
                (metadata_property_state, "PROPERTY_RECORD_KEYS")):
            with self.subTest(module=module.__name__, name=name):
                value = assignment_value(module, name)
                self.assertIsInstance(value, ast.Call)
                self.assertIsInstance(value.func, ast.Attribute)
                self.assertEqual(
                    "metadata_execution_contract", value.func.value.id)
                self.assertEqual(
                    "source_adapter_owner_record_keys", value.func.attr)


if __name__ == "__main__":
    unittest.main()
