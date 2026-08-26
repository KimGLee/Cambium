"""Closed-schema and authority-coverage tests for metadata execution."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import kblib
import metadata_execution_contract as contract


def source_documents():
    authority = kblib.parse_yaml_subset(
        (REPOSITORY / contract.DEFAULT_AUTHORITY_PATH).read_text(
            encoding="utf-8"))
    capabilities = kblib.parse_yaml_subset(
        (REPOSITORY / contract.DEFAULT_CAPABILITIES_PATH).read_text(
            encoding="utf-8"))
    return authority, capabilities


def compile_documents(authority, capabilities, root=REPOSITORY):
    snapshots = {
        path: kblib.repository_file_snapshot(
            root, path, singly_linked=True)
        for path in contract.capability_implementation_paths(capabilities)
    }
    return contract.compile_metadata_execution_document(
        authority, capabilities, implementation_snapshots=snapshots)


def materialize_contract_root(destination):
    for relative in (
            contract.DEFAULT_AUTHORITY_PATH,
            contract.DEFAULT_CAPABILITIES_PATH):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY / relative).read_bytes())
    capabilities = kblib.parse_yaml_subset(
        (destination / contract.DEFAULT_CAPABILITIES_PATH).read_text(
            encoding="utf-8"))
    for relative in contract.capability_implementation_paths(capabilities):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY / relative).read_bytes())
    compiled = contract.compile_metadata_execution_contract(destination)
    artifact = destination / contract.DEFAULT_COMPILED_PATH
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(compiled.canonical_bytes)
    return artifact


class MetadataExecutionContractTests(unittest.TestCase):
    def test_real_contract_compiles_and_loads_canonical_artifact(self):
        compiled = contract.compile_metadata_execution_contract(REPOSITORY)
        loaded = contract.load_metadata_execution_contract(REPOSITORY)
        self.assertEqual(compiled.canonical_bytes, loaded.canonical_bytes)
        self.assertEqual(8, len(loaded.field_rules))
        self.assertEqual(contract.TEMPORAL_ORDER,
                         tuple(loaded.artifact["temporal_order"]))
        self.assertRegex(loaded.contract_fingerprint,
                         r"\Asha256:[0-9a-f]{64}\Z")

    def test_source_order_does_not_change_fingerprint(self):
        authority, capabilities = source_documents()
        first = compile_documents(authority, capabilities)
        authority["field_rules"].reverse()
        capabilities["capabilities"].reverse()
        for entry in capabilities["capabilities"]:
            entry["operations"].reverse()
            for role in contract.IMPLEMENTATION_ROLE_KEYS:
                entry[role].reverse()
        second = compile_documents(authority, capabilities)
        self.assertEqual(first.contract_fingerprint,
                         second.contract_fingerprint)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)

    def test_duplicate_field_transition_fails_closed(self):
        authority, capabilities = source_documents()
        authority["field_rules"].append(
            copy.deepcopy(authority["field_rules"][0]))
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("duplicate field transition rule", str(cm.exception))

    def test_unknown_rule_key_fails_closed(self):
        authority, capabilities = source_documents()
        authority["field_rules"][0]["helpful_note"] = "not executable"
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("unknown keys: helpful_note", str(cm.exception))

    def test_missing_mandatory_writer_capability_fails_closed(self):
        authority, capabilities = source_documents()
        del authority["field_rules"][0]["writer_capability"]
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("missing keys: writer_capability", str(cm.exception))

    def test_rule_without_installed_writer_fails_closed(self):
        authority, capabilities = source_documents()
        target = authority["field_rules"][0]
        writer = next(
            entry for entry in capabilities["capabilities"]
            if entry["kind"] == "writer" and
            entry["capability_id"] == target["writer_capability"])
        writer["operations"] = [
            operation for operation in writer["operations"]
            if (operation.get("field"), operation.get("transition")) !=
            (target["field"], target["transition"])]
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("has no installed writer", str(cm.exception))

    def test_orphan_installed_writer_fails_closed(self):
        authority, capabilities = source_documents()
        writer = next(
            entry for entry in capabilities["capabilities"]
            if entry["kind"] == "writer")
        writer["operations"].append({
            "field": "orphan_field",
            "transition": "owner-to-page-projection",
            "source_adapter": "coverage-row-value-v1",
        })
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("is unauthorized", str(cm.exception))

    def test_second_writer_for_same_transition_fails_closed(self):
        authority, capabilities = source_documents()
        original = next(
            entry for entry in capabilities["capabilities"]
            if entry["kind"] == "writer")
        duplicate = copy.deepcopy(original)
        duplicate["capability_id"] = "second-writer-v1"
        duplicate["operations"] = [duplicate["operations"][0]]
        capabilities["capabilities"].append(duplicate)
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("implemented more than once", str(cm.exception))

    def test_capability_id_is_unique_across_kinds(self):
        authority, capabilities = source_documents()
        writer = next(
            entry for entry in capabilities["capabilities"]
            if entry["kind"] == "writer")
        consumer = next(
            entry for entry in capabilities["capabilities"]
            if entry["kind"] == "consumer")
        consumer["capability_id"] = writer["capability_id"]

        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)

        self.assertIn("duplicate capability_id", str(cm.exception))
        self.assertIn("global, not kind-scoped", str(cm.exception))

    def test_content_change_requires_exact_nonsemantic_exclusions(self):
        authority, capabilities = source_documents()
        rule = next(
            item for item in authority["field_rules"]
            if item["field"] == "last_content_modified" and
            item["transition"] == "semantic-content-change")
        rule["evidence_requirement"]["excluded_change_classes"] = [
            "projection-only"]
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("content-change exclusions", str(cm.exception))

    def test_review_invalidation_is_explicit_tombstone_then_projection(self):
        compiled = contract.compile_metadata_execution_contract(REPOSITORY)
        rules = {(item["field"], item["transition"]): item
                 for item in compiled.field_rules}
        invalidation = rules[("last_reviewed", "semantic-content-change")]
        projection = rules[("last_reviewed", "owner-to-page-projection")]
        self.assertEqual("semantic-content-change-tombstone-v1",
                         invalidation["invalidation_rule"])
        self.assertEqual("tombstone-owner-property-state-v1",
                         invalidation["reconcile_policy"])
        self.assertEqual("coverage-property-state-v1",
                         projection["source_adapter"])
        self.assertEqual("upsert-exact-or-remove-v1",
                         projection["reconcile_policy"])

    def test_last_content_modified_only_accepts_semantic_change(self):
        compiled = contract.compile_metadata_execution_contract(REPOSITORY)
        rules = {(item["field"], item["transition"]): item
                 for item in compiled.field_rules}
        transition = rules[
            ("last_content_modified", "semantic-content-change")]
        evidence = transition["evidence_requirement"]
        self.assertEqual("content-change-event-v1",
                         transition["source_adapter"])
        self.assertEqual("semantic-content", evidence["change_scope"])
        self.assertEqual(
            {"projection-only", "tool-controlled-metadata-only"},
            set(evidence["excluded_change_classes"]))
        projection = rules[
            ("last_content_modified", "owner-to-page-projection")]
        self.assertEqual("coverage-property-state-v1",
                         projection["source_adapter"])
        self.assertEqual("date", transition["value_shape"])
        self.assertEqual("date", projection["value_shape"])

    def test_legacy_projection_value_shape_is_rule_driven(self):
        compiled = contract.compile_metadata_execution_contract(REPOSITORY)
        for field in ("authoring_status", "coverage_disposition", "next_batch"):
            rule = next(item for item in compiled.field_rules
                        if item["field"] == field)
            self.assertEqual("scalar-string-or-null", rule["value_shape"])

    def test_producer_era_gate_capabilities_remain_registered(self):
        self.assertTrue(contract.capability_registered(
            "manual-attestation-v1", "producer", root=REPOSITORY))
        self.assertTrue(contract.capability_registered(
            "registered-scan-v1", "producer", root=REPOSITORY))
        self.assertTrue(contract.capability_registered(
            "manual-gate-attestation-v1", "receipt-schema",
            root=REPOSITORY))
        self.assertTrue(contract.capability_supports(
            "typed-metadata-transition-v1",
            "typed-field-metadata-transition",
            root=REPOSITORY))
        self.assertTrue(contract.capability_supports(
            "project-page-state-v2",
            contract.PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION,
            root=REPOSITORY, kind="writer"))
        self.assertTrue(contract.capability_supports(
            "legacy-property-adoption-v1",
            contract.LEGACY_PROPERTY_ADOPTION_OPERATION,
            root=REPOSITORY, kind="writer"))
        self.assertFalse(contract.capability_registered(
            "unknown-producer-v1", "producer", root=REPOSITORY))

    def test_capability_implementations_are_closed_and_fingerprinted(self):
        authority, capabilities = source_documents()
        paths = contract.capability_implementation_paths(capabilities)
        self.assertIn("Tools/apply_metadata_transition.py", paths)
        self.assertIn("Tools/metadata_property_state.py", paths)
        compiled = compile_documents(authority, capabilities)
        records = {
            item["path"]: item["sha256"]
            for item in compiled.artifact["capability_implementations"]
        }
        self.assertEqual(set(paths), set(records))
        self.assertEqual(
            kblib.sha256_file(REPOSITORY / "Tools/record_gate_result.py"),
            records["Tools/record_gate_result.py"])
        self.assertEqual(
            "Tools/apply_metadata_transition.py",
            contract.capability_entry(
                "typed-metadata-transition-v1", "consumer",
                root=REPOSITORY)["implementation_owner"])
        self.assertEqual(
            "Tools/record_gate_result.py",
            contract.capability_entry(
                "registered-scan-v1", "producer",
                root=REPOSITORY)["implementation_owner"])

    def test_real_registry_separates_owner_writers_checkers_and_consumers(self):
        _authority, capabilities = source_documents()
        for entry in capabilities["capabilities"]:
            role_sets = [set(entry[role])
                         for role in contract.IMPLEMENTATION_ROLE_KEYS]
            self.assertTrue(all(
                entry["implementation_owner"] not in role_set
                for role_set in role_sets
            ), entry["capability_id"])
            for index, left in enumerate(role_sets):
                for right in role_sets[index + 1:]:
                    self.assertFalse(left & right, entry["capability_id"])

        projection = next(
            entry for entry in capabilities["capabilities"]
            if entry["capability_id"] == "project-page-state-v2")
        self.assertEqual(
            "Tools/project_page_state.py",
            projection["implementation_owner"],
        )
        self.assertEqual(
            {"Tools/check_batch_close.py"}, set(projection["checkers"]))
        self.assertNotIn("Tools/register_amendment.py", projection["writers"])

        card_currentness = next(
            entry for entry in capabilities["capabilities"]
            if entry["capability_id"] == "card-currentness-v1")
        self.assertEqual(
            "Tools/stamp_cards.py",
            card_currentness["implementation_owner"],
        )
        self.assertEqual(
            {"Tools/apply_profile_adoption.py"},
            set(card_currentness["writers"]),
        )
        self.assertEqual(
            {"Tools/run_gates.py"}, set(card_currentness["checkers"]))
        self.assertEqual(
            {"Tools/card_activation.py"},
            set(card_currentness["consumers"]),
        )

    def test_missing_or_noncanonical_implementation_fails_closed(self):
        authority, capabilities = source_documents()
        capabilities["capabilities"][0]["implementation_owner"] = \
            "../outside.py"
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            compile_documents(authority, capabilities)
        self.assertIn("canonical Tools/*.py", str(cm.exception))

        authority, capabilities = source_documents()
        snapshots = {
            path: kblib.repository_file_snapshot(
                REPOSITORY, path, singly_linked=True)
            for path in contract.capability_implementation_paths(capabilities)
            if path != "Tools/record_gate_result.py"
        }
        with self.assertRaises(contract.MetadataExecutionContractError) as cm:
            contract.compile_metadata_execution_document(
                authority, capabilities,
                implementation_snapshots=snapshots)
        self.assertIn("snapshot is missing", str(cm.exception))

    def test_compiled_artifact_fingerprint_tamper_fails_closed(self):
        compiled = contract.compile_metadata_execution_contract(REPOSITORY)
        artifact = copy.deepcopy(compiled.artifact)
        artifact["field_rules"][0]["write_timing"] = "tampered-timing"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaises(
                    contract.MetadataExecutionContractError) as cm:
                contract.load_metadata_execution_contract(
                    REPOSITORY, path=path)
        self.assertIn("fingerprint mismatch", str(cm.exception))

    def test_valid_old_artifact_is_rejected_after_authority_source_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            materialize_contract_root(root)
            authority = root / contract.DEFAULT_AUTHORITY_PATH
            text = authority.read_text(encoding="utf-8")
            authority.write_text(text.replace(
                "batch-close-after-owner-update",
                "after-owner-state-transition", 1), encoding="utf-8")
            with self.assertRaises(
                    contract.MetadataExecutionContractError) as cm:
                contract.load_metadata_execution_contract(root)
        self.assertIn("stale relative to live authority", str(cm.exception))

    def test_valid_old_artifact_is_rejected_after_consumer_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            materialize_contract_root(root)
            capabilities = root / contract.DEFAULT_CAPABILITIES_PATH
            text = capabilities.read_text(encoding="utf-8")
            capabilities.write_text(text.replace(
                "      - operation: typed-field-metadata-transition\n",
                "      - operation: metadata-reconciliation\n"),
                encoding="utf-8")
            with self.assertRaises(
                    contract.MetadataExecutionContractError) as cm:
                contract.load_metadata_execution_contract(root)
        self.assertIn("stale relative to live authority", str(cm.exception))

    def test_valid_old_artifact_is_rejected_after_implementation_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            materialize_contract_root(root)
            implementation = root / "Tools/record_gate_result.py"
            implementation.write_text(
                implementation.read_text(encoding="utf-8") + "\n# drift\n",
                encoding="utf-8")
            with self.assertRaises(
                    contract.MetadataExecutionContractError) as cm:
                contract.load_metadata_execution_contract(root)
        self.assertIn("stale relative to live authority", str(cm.exception))

    def test_property_state_helper_drift_invalidates_compiled_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            materialize_contract_root(root)
            implementation = root / "Tools/metadata_property_state.py"
            implementation.write_text(
                implementation.read_text(encoding="utf-8") +
                "\n# helper drift\n", encoding="utf-8")
            with self.assertRaises(
                    contract.MetadataExecutionContractError) as cm:
                contract.load_metadata_execution_contract(root)
        self.assertIn("stale relative to live authority", str(cm.exception))

    def test_coverage_property_adapter_record_shape_is_closed(self):
        compiled = contract.compile_metadata_execution_contract(REPOSITORY)
        adapter = next(
            item for item in compiled.artifact["source_adapters"]
            if item["adapter_id"] == "coverage-property-state-v1")
        self.assertEqual(
            ["content_fingerprint", "evidence_receipt", "value"],
            adapter["owner_record_keys"])


if __name__ == "__main__":
    unittest.main()
