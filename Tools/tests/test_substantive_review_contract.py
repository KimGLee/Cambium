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

import Tools.execution.audit.substantive_review_contract as contract  # noqa: E402
import Tools.execution.audit.audit_plan_contract as audit_plan_contract  # noqa: E402
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime  # noqa: E402
import Tools.execution.audit.complete_audit_receipt as complete_audit_receipt  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.execution.audit.record_substantive_review as producer  # noqa: E402
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION  # noqa: E402


class SubstantiveReviewContractTests(unittest.TestCase):

    def attempt_context(self):
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
            "applicability": projection["applicability"],
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        })
        plan = {
            "schema_version": audit_plan_contract.load_contract(
                str(REPOSITORY))["schema_version"],
            "plan_id": "audit-plan-example",
            "task_id": "task-example",
            "batch_id": "batch-example",
            "generated_at": "2026-08-28T00:00:00Z",
            "queue_revision": 1,
            "queue_state_revision": 2,
            "required_queue_sha256": "sha256:" + "0" * 64,
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": "sha256:" + "2" * 64,
            "selected_profile_manifest": "profiles/example/profile.toml",
            "profile_snapshot_sha256": "sha256:" + "3" * 64,
            "profile_contract_fingerprint": "sha256:" + "4" * 64,
            "opening_transition_receipt": "audit-update_queue-open-1",
            "artifact_snapshot_sha256": "sha256:" + "5" * 64,
            "contract_snapshot_sha256": "sha256:" + "6" * 64,
            "accepted_baseline_sha256": "sha256:" + "7" * 64,
            "obligations": [obligation],
        }
        audit_plan_contract.validate_plan(plan)
        plan_sha256 = audit_plan_contract.plan_sha256(plan)
        text = "# Example\n\nCurrent claim.\n\n## Sources\n\n- source\n"
        snapshot = SimpleNamespace(read_text=lambda: text)
        frozen = (audit_producer_runtime.FrozenPage(
            page, kblib.sha256_bytes(text.encode("utf-8")),
            "sha256:" + "8" * 64, snapshot),)
        receipt = producer.build_review_receipt(
            root=str(REPOSITORY), result={}, plan=plan,
            plan_sha256=plan_sha256, obligation=obligation, page=page,
            frozen=frozen, authoring_context_id="author-context",
            reviewer_context_id="review-context", reviewer_role="reviewer",
            round_number=1, verdict="passed", findings=[],
            statement="current content passes substantive review")
        return plan, plan_sha256, obligation, frozen, receipt

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
            "applicability": projection["applicability"],
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
        frozen_page = SimpleNamespace(path=page)
        self.assertIs(frozen_page,
                      audit_producer_runtime.frozen_manifest_page(
                          [frozen_page], page))
        self.assertIsNone(audit_producer_runtime.frozen_manifest_page(
            [frozen_page], "Topics/Other.md"))
        self.assertIsNone(audit_producer_runtime.frozen_manifest_page(
            [frozen_page, frozen_page], page))

    def receipt(self):
        owner = contract.load_contract(str(REPOSITORY))
        return {
            "schema_version": owner["schema_version"],
            "record_kind": owner["record_kind"],
            "receipt_type_id": contract.RECEIPT_TYPE_ID,
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
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": "sha256:" + "2" * 64,
            "selected_profile_manifest": "profiles/example/profile.toml",
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
            "page_sha256": "sha256:" + "b" * 64,
            "sources_sha256": "sha256:" + "c" * 64,
            "semantic_content_fingerprint": "sha256:" + "d" * 64,
            "artifact_fingerprint": "sha256:" + "e" * 64,
            "dependency_fingerprint": "sha256:" + "f" * 64,
            "round": 2,
            "round_1_receipt_id": first["receipt_id"],
            "findings": [{
                "finding_id": "confirmation-001",
                "severity": "critical",
                "statement": "the conclusion does not follow",
                "status": "closed",
                "round_1_finding_id": "finding-001",
            }],
        })
        contract.validate_review_pair(first, second)

        second["findings"][0]["round_1_finding_id"] = "new-scope"
        with self.assertRaisesRegex(ValueError, "exact round 1 finding set"):
            contract.validate_review_pair(first, second)

    def test_round_two_cannot_rewrite_the_round_one_finding_identity(self):
        first = self.blocking_round_one()
        second = copy.deepcopy(self.receipt())
        second.update({
            "receipt_id": "audit-record_substantive_review-example-0002",
            "round": 2,
            "round_1_receipt_id": first["receipt_id"],
            "findings": [{
                "finding_id": "confirmation-001",
                "severity": "critical",
                "statement": "a different issue",
                "status": "closed",
                "round_1_finding_id": "finding-001",
            }],
        })
        with self.assertRaisesRegex(ValueError, "finding identity"):
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
                "statement": "the conclusion does not follow",
                "status": "open",
                "round_1_finding_id": "finding-001",
            }],
        })
        contract.validate_review_pair(first, second)
        second["round"] = 3
        with self.assertRaisesRegex(
                ValueError, "round exceeds its Kernel contract"):
            contract.validate_review_receipt(second)

    def test_substantive_and_completion_attempts_share_currentness_rules(self):
        plan, plan_sha256, obligation, frozen, evidence = \
            self.attempt_context()
        result = {
            "current_receipt_catalog": {
                evidence["receipt_id"]: evidence,
            },
        }
        self.assertIs(
            evidence, producer.current_review_attempt(
                result, plan, plan_sha256, obligation, frozen,
                str(REPOSITORY)))

        final = complete_audit_receipt.build_audit_receipt(
            plan=plan, plan_sha256=plan_sha256,
            obligation=obligation, evidence=evidence)
        result["current_receipt_catalog"][final["receipt_id"]] = final
        self.assertIs(
            final, complete_audit_receipt.current_audit_receipt_attempt(
                result, plan, plan_sha256, obligation, frozen,
                str(REPOSITORY)))

        changed_text = "# Example\n\nChanged claim.\n\n## Sources\n\n- source\n"
        changed = (audit_producer_runtime.FrozenPage(
            obligation["target"],
            kblib.sha256_bytes(changed_text.encode("utf-8")),
            "sha256:" + "9" * 64,
            SimpleNamespace(read_text=lambda: changed_text)),)
        self.assertIsNone(producer.current_review_attempt(
            result, plan, plan_sha256, obligation, changed,
            str(REPOSITORY)))
        self.assertIsNone(
            complete_audit_receipt.current_audit_receipt_attempt(
                result, plan, plan_sha256, obligation, changed,
                str(REPOSITORY)))

    def test_substantive_and_completion_attempts_fail_closed_on_ambiguity(self):
        plan, plan_sha256, obligation, frozen, evidence = \
            self.attempt_context()
        sibling = copy.deepcopy(evidence)
        sibling["receipt_id"] = "second-current-substantive-review"
        result = {"current_receipt_catalog": {
            evidence["receipt_id"]: evidence,
            sibling["receipt_id"]: sibling,
        }}
        with self.assertRaisesRegex(ValueError, "multiple current attempts"):
            producer.current_review_attempt(
                result, plan, plan_sha256, obligation, frozen,
                str(REPOSITORY))

        result["current_receipt_catalog"] = {evidence["receipt_id"]: evidence}
        final = complete_audit_receipt.build_audit_receipt(
            plan=plan, plan_sha256=plan_sha256,
            obligation=obligation, evidence=evidence)
        final_sibling = copy.deepcopy(final)
        final_sibling["receipt_id"] = "second-current-audit-receipt"
        result["current_receipt_catalog"].update({
            final["receipt_id"]: final,
            final_sibling["receipt_id"]: final_sibling,
        })
        with self.assertRaisesRegex(ValueError, "multiple current attempts"):
            complete_audit_receipt.current_audit_receipt_attempt(
                result, plan, plan_sha256, obligation, frozen,
                str(REPOSITORY))

    def test_invalid_stable_attempt_is_not_reclassified_as_stale(self):
        plan, plan_sha256, obligation, frozen, evidence = \
            self.attempt_context()
        evidence["tool_version"] = "forged"
        result = {"current_receipt_catalog": {
            evidence["receipt_id"]: evidence,
        }}
        with self.assertRaisesRegex(ValueError, "invalid stable attempt"):
            producer.current_review_attempt(
                result, plan, plan_sha256, obligation, frozen,
                str(REPOSITORY))


if __name__ == "__main__":
    unittest.main()
