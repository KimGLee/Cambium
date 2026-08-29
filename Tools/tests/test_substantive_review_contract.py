"""Closed-contract tests for K12/12 substantive correctness review."""

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import substantive_review_contract as contract  # noqa: E402
import audit_producer_runtime  # noqa: E402
import record_substantive_review as producer  # noqa: E402
from profile_fixture import FIXTURE_UPSTREAM_REVISION  # noqa: E402


class SubstantiveReviewContractTests(unittest.TestCase):

    def test_producer_page_must_be_the_frozen_obligation_target(self):
        projection = contract.load_contract(REPOSITORY)[
            "obligation_projection"]
        page = "Topics/Example.md"
        obligation = {
            field: projection[field]
            for field in (
                "owner_kind", "owner_rule_id", "kernel_extension_point",
                "due_stage", "evidence_role", "evidence_kind", "dimension",
                "acceptance_predicate", "producer_check",
                "producer_capability", "producer_gate_id",
                "consumer_gate_id", "fingerprint_binding")
        }
        obligation.update({
            "obligation_id": "obligation-001",
            "target": page,
            "partition": projection["trigger_partition_mappings"][0][
                "partition"],
            "status": "required",
        })
        plan = {"obligations": [obligation]}

        self.assertIs(
            obligation,
            producer._obligation(
                REPOSITORY, plan, obligation["obligation_id"], page))
        with self.assertRaisesRegex(
                audit_producer_runtime.AuditProducerError,
                "not a current substantive-review requirement"):
            producer._obligation(
                REPOSITORY, plan, obligation["obligation_id"],
                "Topics/Other.md")
        with self.assertRaisesRegex(
                audit_producer_runtime.AuditProducerError,
                "not exactly one member"):
            producer._frozen_page(
                [SimpleNamespace(path=page)], "Topics/Other.md")

    def receipt(self):
        return {
            "schema_version": 1,
            "record_kind": "substantive-review-evidence",
            "receipt_id": "audit-record_substantive_review-example-0001",
            "tool": "record_substantive_review",
            "tool_version": "1.0.0",
            "check": "substantive_review",
            "target": "Topics/Example.md",
            "result": "pass",
            "details": "reasoning and sampled source claims are supported",
            "checked_at": "2026-08-28T00:00:00Z",
            "invalidated_by": None,
            "plan_id": "audit-plan-example",
            "audit_plan_sha256": "sha256:" + "1" * 64,
            "obligation_id": "obligation-001",
            "task_id": "task-example",
            "batch_id": "batch-example",
            "opening_transition_receipt": "audit-update_queue-open-1",
            "standards_version": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": "sha256:" + "2" * 64,
            "selected_profile_manifest": "profiles/example/profile.md",
            "profile_snapshot_sha256": "sha256:" + "3" * 64,
            "profile_contract_fingerprint": "sha256:" + "4" * 64,
            "page_sha256": "sha256:" + "5" * 64,
            "sources_sha256": "sha256:" + "6" * 64,
            "semantic_content_fingerprint": "sha256:" + "7" * 64,
            "artifact_fingerprint": "sha256:" + "8" * 64,
            "dependency_fingerprint": "sha256:" + "9" * 64,
            "contract_fingerprint": "sha256:" + "a" * 64,
            "fingerprint_binding": "evidence-time",
            "acceptance_predicate": "content-correctness",
            "authoring_context_id": "author-context",
            "reviewer_context_id": "review-context",
            "reviewer_role": "reviewer",
            "round": 1,
            "round_1_receipt_id": None,
            "verdict": "passed",
            "findings": [],
        }

    def blocking_round_one(self):
        receipt = self.receipt()
        receipt.update({
            "result": "fail",
            "verdict": "changes-required",
            "findings": [{
                "finding_id": "finding-001",
                "severity": "critical",
                "statement": "the conclusion does not follow",
                "status": "open",
                "round_1_finding_id": None,
            }],
        })
        return receipt

    def test_shipped_contract_accepts_independent_round_one_pass(self):
        receipt = self.receipt()
        self.assertIs(receipt, contract.validate_review_receipt(receipt))
        self.assertEqual(2, contract.ROUND_CAP)

    def test_author_cannot_produce_its_own_review(self):
        receipt = self.receipt()
        receipt["reviewer_context_id"] = receipt["authoring_context_id"]
        with self.assertRaisesRegex(ValueError, "must differ"):
            contract.validate_review_receipt(receipt)

    def test_blocking_round_one_requires_changes(self):
        receipt = self.blocking_round_one()
        contract.validate_review_receipt(receipt)
        receipt["result"] = "pass"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            contract.validate_review_receipt(receipt)

    def test_round_two_only_confirms_the_exact_round_one_blocking_set(self):
        first = self.blocking_round_one()
        second = copy.deepcopy(self.receipt())
        second.update({
            "receipt_id": "audit-record_substantive_review-example-0002",
            "round": 2,
            "round_1_receipt_id": first["receipt_id"],
            "findings": [{
                "finding_id": "confirmation-001",
                "severity": "critical",
                "statement": "the corrected conclusion now follows",
                "status": "closed",
                "round_1_finding_id": "finding-001",
            }],
        })
        contract.validate_review_pair(first, second)

        second["findings"][0]["round_1_finding_id"] = "new-scope"
        with self.assertRaisesRegex(ValueError, "exact round 1 finding set"):
            contract.validate_review_pair(first, second)

    def test_unresolved_round_two_escalates_instead_of_opening_round_three(self):
        first = self.blocking_round_one()
        second = copy.deepcopy(self.receipt())
        second.update({
            "receipt_id": "audit-record_substantive_review-example-0002",
            "round": 2,
            "round_1_receipt_id": first["receipt_id"],
            "result": "fail",
            "verdict": "escalated",
            "findings": [{
                "finding_id": "confirmation-001",
                "severity": "critical",
                "statement": "the conclusion remains unsupported",
                "status": "open",
                "round_1_finding_id": "finding-001",
            }],
        })
        contract.validate_review_pair(first, second)
        second["round"] = 3
        with self.assertRaisesRegex(ValueError, "round must be 1 or 2"):
            contract.validate_review_receipt(second)


if __name__ == "__main__":
    unittest.main()
