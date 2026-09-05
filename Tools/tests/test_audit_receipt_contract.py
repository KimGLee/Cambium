"""Owned tests for the current full AuditReceipt machine contract."""

import copy
from pathlib import Path
import unittest

import Tools.execution.audit.audit_receipt_contract as contract
from Tools.execution.evidence import receipt_type_contract
import Tools.platform.common.kblib as kblib


REPOSITORY = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY.joinpath(
    *contract.AUDIT_RECEIPT_CONTRACT_PATH.split("/"))
SOURCE = kblib.parse_yaml_subset(CONTRACT_PATH.read_text(encoding="utf-8"))


def valid_receipt():
    return {
        "schema_version": SOURCE["schema_version"],
        "record_kind": SOURCE["record_kind"],
        "receipt_type_id": contract.RECEIPT_TYPE_ID,
        "receipt_id": "audit-current-example-0001",
        "plan_id": "audit-plan-example",
        "audit_plan_sha256": "sha256:" + "1" * 64,
        "obligation_id": "obligation-001",
        "owner_kind": "kernel",
        "owner_rule_id": "k12-12-substantive-correctness-review",
        "kernel_extension_point": None,
        "task_id": "task-example",
        "batch_id": "batch-example",
        "opening_transition_receipt": "audit-update_queue-open-1",
        "upstream_revision_id": "a" * 40,
        "active_standards_sha256": "sha256:" + "2" * 64,
        "selected_profile_manifest": "profiles/example/profile.toml",
        "profile_snapshot_sha256": "sha256:" + "3" * 64,
        "profile_contract_fingerprint": "sha256:" + "4" * 64,
        "due_stage": "pre-merge",
        "evidence_role": "emits",
        "evidence_kind": "audit-receipt",
        "dimension": "content_and_depth",
        "scope": ["Topics/Example.md"],
        "acceptance_predicate": "content-correctness",
        "producer_check": "substantive_review",
        "producer_capability": "substantive-review-attestation-v1",
        "producer_gate_id": None,
        "consumer_gate_id": "batch-review",
        "fingerprint_binding": "evidence-time",
        "artifact_fingerprint": "sha256:" + "5" * 64,
        "dependency_fingerprint": "sha256:" + "6" * 64,
        "contract_fingerprint": "sha256:" + "7" * 64,
        "verifier": "record_substantive_review/1.0.0",
        "method": "independent-substantive-review",
        "evidence_ref": "audit-record_substantive_review-example-0001",
        "checked_at": "2026-08-28T00:00:00Z",
        "review_due": None,
        "result": "passed",
        "invalidated_by": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    }


class AuditReceiptSchemaContractTests(unittest.TestCase):
    def test_field_order_types_and_closed_values_derive_from_source(self):
        values = contract.validate_contract(copy.deepcopy(SOURCE))
        expected_order = tuple(row["field"] for row in SOURCE["fields"])
        expected_fields = {
            row["field"]: {
                "type": row["type"],
                "nullable": row["nullable"],
            }
            for row in SOURCE["fields"]
        }

        self.assertEqual(expected_order, values["field_order"])
        self.assertEqual(expected_order, contract.AUDIT_RECEIPT_FIELDS)
        self.assertEqual(expected_fields, values["fields"])
        self.assertEqual(
            frozenset(SOURCE["result_values"]),
            contract.AUDIT_RECEIPT_RESULT_VALUES)

    def test_field_and_identity_mutations_fail_closed(self):
        def missing_field(record):
            record.pop("contract_fingerprint")

        def extra_field(record):
            record["gate_id"] = "invented"

        cases = (
            missing_field,
            extra_field,
            lambda record: record.update(schema_version=99),
            lambda record: record.update(record_kind="receipt"),
            lambda record: record.update(receipt_type_id="unknown-receipt"),
            lambda record: record.update(
                audit_plan_sha256="not-a-fingerprint"),
            lambda record: record.update(
                checked_at="2026-08-28"),
            lambda record: record.update(receipt_id=""),
        )
        for mutate in cases:
            with self.subTest(case=getattr(mutate, "__name__", "mutation")):
                record = valid_receipt()
                mutate(record)
                with self.assertRaises((TypeError, ValueError)):
                    contract.validate_audit_receipt(
                        record, dimensions={"content_and_depth"})


class AuditReceiptAfterImageContractTests(unittest.TestCase):
    def test_page_after_image_projection_is_exactly_the_source_contract(self):
        sequence_fields = {
            "page_material_fields", "closing_frontmatter_markers",
            "included_frontmatter_fields", "page_set_material_fields",
            "page_set_member_fields",
        }
        expected = {
            field: tuple(value) if field in sequence_fields else value
            for field, value in SOURCE[
                "page_artifact_fingerprint"].items()
        }

        self.assertEqual(
            expected, contract.page_artifact_fingerprint_contract())

    def test_page_after_image_contract_rejects_shape_order_and_binding_drift(self):
        def extra_field(document):
            document["page_artifact_fingerprint"]["extra"] = "invalid"

        def reorder_frontmatter(document):
            document["page_artifact_fingerprint"][
                "included_frontmatter_fields"].reverse()

        def change_body_binding(document):
            document["page_artifact_fingerprint"][
                "body_binding"] = "normalized-markdown"

        def change_path_binding(document):
            document["page_artifact_fingerprint"][
                "path_binding"] = "host-absolute"

        def reorder_member_fields(document):
            document["page_artifact_fingerprint"][
                "page_set_member_fields"].reverse()

        for mutate in (
                extra_field, reorder_frontmatter, change_body_binding,
                change_path_binding, reorder_member_fields):
            with self.subTest(case=mutate.__name__):
                document = copy.deepcopy(SOURCE)
                mutate(document)
                with self.assertRaises(ValueError):
                    contract.validate_contract(document)


class AuditReceiptAcceptanceContractTests(unittest.TestCase):
    def test_acceptance_axes_and_producer_identity_are_closed(self):
        invalid = (
            ("result", "pass"),
            ("due_stage", "open"),
            ("evidence_role", "consumes"),
            ("evidence_kind", "gate-receipt"),
            ("owner_kind", "repository"),
            ("fingerprint_binding", "current-state"),
        )
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                record = valid_receipt()
                record[field] = value
                with self.assertRaises(ValueError):
                    contract.validate_audit_receipt(
                        record, dimensions={"content_and_depth"})

        record = valid_receipt()
        with self.assertRaisesRegex(ValueError, "dimension is not registered"):
            contract.validate_audit_receipt(
                record, dimensions={"structure_and_links"})

        for capability, gate_id in ((None, None), ("capability", "gate")):
            with self.subTest(capability=capability, gate_id=gate_id):
                record = valid_receipt()
                record["producer_capability"] = capability
                record["producer_gate_id"] = gate_id
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    contract.validate_audit_receipt(record)

        profile = valid_receipt()
        profile.update({
            "owner_kind": "profile-extension",
            "kernel_extension_point": "audit-dimension-extension",
            "producer_capability": None,
            "producer_gate_id": "profile-audit-gate",
        })
        self.assertIs(profile, contract.validate_audit_receipt(profile))

    def test_scope_and_reuse_bindings_are_closed(self):
        for scope in (
                ["Topics/Z.md", "Topics/A.md"],
                ["Topics/A.md", "Topics/A.md"],
                [],
                [""],
        ):
            with self.subTest(scope=scope):
                record = valid_receipt()
                record["scope"] = scope
                with self.assertRaises((TypeError, ValueError)):
                    contract.validate_audit_receipt(record)

        reused = valid_receipt()
        reused.update({
            "evidence_ref": "audit-prior-1",
            "reused_receipt_id": "audit-prior-1",
            "reuse_reason": "scope, predicate, and fingerprints are current",
            "fingerprint_binding": "reused-receipt",
        })
        self.assertIs(reused, contract.validate_audit_receipt(reused))

        mutations = (
            {"reuse_reason": None},
            {"evidence_ref": "different-receipt"},
            {"result": "failed"},
            {"fingerprint_binding": "evidence-time"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                record = copy.deepcopy(reused)
                record.update(mutation)
                with self.assertRaises(ValueError):
                    contract.validate_audit_receipt(record)


class AuditReceiptTypedDispatchIntegrationTests(unittest.TestCase):
    def test_current_registry_dispatches_to_the_audit_receipt_validator(self):
        registry = receipt_type_contract.load_receipt_type_registry(REPOSITORY)
        registration = registry[contract.RECEIPT_TYPE_ID]

        self.assertEqual(
            "Tools.execution.audit.audit_receipt_contract:"
            "current_receipt_errors",
            registration.validator_owner)
        for lifecycle in registration.catalog_lifecycle:
            with self.subTest(lifecycle=lifecycle):
                self.assertEqual(
                    [], receipt_type_contract.current_receipt_errors(
                        valid_receipt(), lifecycle,
                        root=REPOSITORY, registry=registry))


if __name__ == "__main__":
    unittest.main()
