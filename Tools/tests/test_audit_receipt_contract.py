"""Closed-contract tests for the Kernel-owned K12/07 AuditReceipt."""

import copy
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import audit_receipt_contract as contract  # noqa: E402
from profile_fixture import FIXTURE_UPSTREAM_REVISION  # noqa: E402


class AuditReceiptContractTests(unittest.TestCase):

    def receipt(self):
        return {
            "schema_version": 1,
            "record_kind": "audit-receipt",
            "receipt_id": "audit-complete_audit_receipt-example-0001",
            "plan_id": "audit-plan-example",
            "audit_plan_sha256": "sha256:" + "1" * 64,
            "obligation_id": "obligation-001",
            "owner_kind": "kernel",
            "owner_rule_id": "k12-12-substantive-correctness-review",
            "kernel_extension_point": None,
            "task_id": "task-example",
            "batch_id": "batch-example",
            "opening_transition_receipt": "audit-update_queue-open-1",
            "standards_version": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": "sha256:" + "2" * 64,
            "selected_profile_manifest": "profiles/example/profile.md",
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

    def test_shipped_contract_validates_one_full_receipt(self):
        receipt = self.receipt()
        self.assertIs(receipt, contract.validate_audit_receipt(
            receipt, dimensions={"content_and_depth"}))
        self.assertEqual(tuple(receipt), contract.AUDIT_RECEIPT_FIELDS)

    def test_shipped_contract_owns_exact_page_artifact_projection(self):
        projection = contract.page_artifact_fingerprint_contract()
        self.assertEqual(
            projection["protocol_id"], "cambium-page-artifact-v1")
        self.assertEqual(
            projection["digest_serialization"],
            "sha256-prefixed-canonical-json-utf8")
        self.assertEqual(
            projection["page_material_fields"],
            ("protocol_id", "path", "frontmatter", "body"))
        self.assertEqual(
            projection["included_frontmatter_fields"],
            ("type", "priority", "tier", "coverage_disposition",
             "lifecycle", "prerequisites"))
        self.assertEqual(
            projection["excluded_frontmatter_policy"], "all-other-fields")
        self.assertEqual(
            projection["body_binding"], "exact-bytes-after-frontmatter")
        self.assertEqual(
            projection["path_binding"],
            "canonical-repository-relative-posix")
        self.assertEqual(
            projection["page_set_member_fields"],
            ("path", "artifact_fingerprint"))

    def test_page_artifact_projection_is_closed_and_exact(self):
        mutated = copy.deepcopy(contract._SHIPPED_CONTRACT)
        mutated["page_artifact_fingerprint"][
            "included_frontmatter_fields"].reverse()
        with self.assertRaisesRegex(ValueError, "ordered closed set"):
            contract.validate_contract(mutated)

        mutated = copy.deepcopy(contract._SHIPPED_CONTRACT)
        mutated["page_artifact_fingerprint"]["extra"] = "not-owned"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_contract(mutated)

        mutated = copy.deepcopy(contract._SHIPPED_CONTRACT)
        mutated["page_artifact_fingerprint"]["body_binding"] = \
            "normalized-markdown"
        with self.assertRaisesRegex(ValueError, "body_binding"):
            contract.validate_contract(mutated)

    def test_lightweight_or_open_shape_cannot_pose_as_full_receipt(self):
        receipt = self.receipt()
        del receipt["contract_fingerprint"]
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_audit_receipt(receipt)

        receipt = self.receipt()
        receipt["gate_id"] = "content-correctness"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_audit_receipt(receipt)

    def test_result_and_dimension_are_closed(self):
        receipt = self.receipt()
        receipt["result"] = "pass"
        with self.assertRaisesRegex(ValueError, "result is invalid"):
            contract.validate_audit_receipt(receipt)

        receipt = self.receipt()
        with self.assertRaisesRegex(ValueError, "dimension is not registered"):
            contract.validate_audit_receipt(
                receipt, dimensions={"structure_and_links"})

    def test_scope_is_nonempty_unique_and_canonical(self):
        receipt = self.receipt()
        receipt["scope"] = ["Topics/Z.md", "Topics/A.md"]
        with self.assertRaisesRegex(ValueError, "sorted"):
            contract.validate_audit_receipt(receipt)

        receipt["scope"] = ["Topics/A.md", "Topics/A.md"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            contract.validate_audit_receipt(receipt)

    def test_reuse_binding_is_paired_and_points_to_its_evidence(self):
        receipt = self.receipt()
        receipt.update({
            "evidence_ref": "audit-prior-1",
            "reused_receipt_id": "audit-prior-1",
            "reuse_reason": "scope, predicate, and fingerprints are current",
            "fingerprint_binding": "reused-receipt",
        })
        contract.validate_audit_receipt(receipt)
        receipt["reuse_reason"] = None
        with self.assertRaisesRegex(ValueError, "paired"):
            contract.validate_audit_receipt(receipt)

    def test_receipt_set_hash_rejects_duplicate_identity(self):
        receipt = self.receipt()
        digest = contract.receipt_set_sha256([receipt])
        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        with self.assertRaisesRegex(ValueError, "repeats receipt_id"):
            contract.receipt_set_sha256([receipt, copy.deepcopy(receipt)])


if __name__ == "__main__":
    unittest.main()
