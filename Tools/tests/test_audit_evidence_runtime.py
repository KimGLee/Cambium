"""Owner tests for the current AuditPlan evidence reconciliation boundary.

Producer record shapes, producer retry lifecycles, AuditPlan loading, Receipt
catalog filtering, and terminal-proof consumption have their own primary
tests.  This file starts from one current, producer-built evidence checkpoint
and owns only evidence resolution, reconciliation, and the adjacent stage to
Batch Review hand-off.
"""

import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]

import Tools.execution.audit.audit_evidence_runtime as runtime  # noqa: E402
import Tools.execution.audit.audit_obligation_projection as projection  # noqa: E402
import Tools.execution.audit.audit_plan_contract as plan_contract  # noqa: E402
import Tools.execution.audit.audit_producer_runtime as producer_runtime  # noqa: E402
import Tools.execution.audit.audit_receipt_contract as receipt_contract  # noqa: E402
import Tools.execution.audit.complete_audit_receipt as complete_receipt  # noqa: E402
import Tools.execution.audit.record_substantive_review as review_producer  # noqa: E402
import Tools.execution.audit.substantive_review_contract as review_contract  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.tests.support.profile_fixture import (  # noqa: E402
    FIXTURE_UPSTREAM_REVISION,
)


def digest(label):
    return kblib.sha256_bytes(label.encode("utf-8"))


class CurrentEvidenceCheckpoint:
    """Build one legal current-contract checkpoint without runtime replay."""

    @classmethod
    def setUpClass(cls):
        target = "README.md"
        text = (REPOSITORY / target).read_text(encoding="utf-8")
        snapshot = SimpleNamespace(read_text=lambda: text)
        frozen = (producer_runtime.FrozenPage(
            target,
            kblib.sha256_bytes(text.encode("utf-8")),
            digest("semantic-content"),
            snapshot,
        ),)

        spec = projection.obligation_spec_for_rule(
            "k12-12-substantive-correctness-review", REPOSITORY)
        obligation = projection.required_obligation(
            projection.resolve_obligation_definition(
                spec, target, trigger="needs_rereview"))
        plan = {
            "schema_version": plan_contract.load_contract(
                REPOSITORY)["schema_version"],
            "plan_id": "audit-plan-current-contract",
            "task_id": "task-current-contract",
            "batch_id": "B001",
            "generated_at": "2026-08-28T00:00:00Z",
            "queue_revision": 3,
            "queue_state_revision": 5,
            "required_queue_sha256": digest("required-queue"),
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": digest("active-standards"),
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": digest("profile"),
            "profile_contract_fingerprint": digest("profile-contract"),
            "opening_transition_receipt": "queue-open-current",
            "artifact_snapshot_sha256": digest("artifact-snapshot"),
            "contract_snapshot_sha256": digest("pending-contract"),
            "accepted_baseline_sha256": digest("accepted-baseline"),
            "obligations": [obligation],
        }
        plan["contract_snapshot_sha256"] = \
            plan_contract.plan_contract_snapshot_sha256(plan)
        plan_contract.validate_plan(plan)
        plan_sha256 = plan_contract.plan_sha256(plan)

        review = review_producer.build_review_receipt(
            root=str(REPOSITORY), result={}, plan=plan,
            plan_sha256=plan_sha256, obligation=obligation,
            page=target, frozen=frozen,
            authoring_context_id="author-context",
            reviewer_context_id="reviewer-context",
            reviewer_role="reviewer", round_number=1,
            verdict="passed", findings=[],
            statement="current content passes substantive review")
        full = complete_receipt.build_audit_receipt(
            plan=plan, plan_sha256=plan_sha256,
            obligation=obligation, evidence=review)

        review_contract.validate_review_receipt(review)
        receipt_contract.validate_audit_receipt(full)

        cls.base_plan = plan
        cls.base_plan_sha256 = plan_sha256
        cls.base_obligation = obligation
        cls.base_review = review
        cls.base_full = full
        cls.base_item = {
            "id": "B001",
            "state": "open",
            "manifest": [target],
        }

    def setUp(self):
        self.plan = copy.deepcopy(self.base_plan)
        self.plan_sha256 = self.base_plan_sha256
        self.obligation = copy.deepcopy(self.base_obligation)
        self.review = copy.deepcopy(self.base_review)
        self.full = copy.deepcopy(self.base_full)
        self.item = copy.deepcopy(self.base_item)
        self.catalog = {
            self.review["receipt_id"]: self.review,
            self.full["receipt_id"]: self.full,
        }
        self.result = {
            "root": str(REPOSITORY),
            "items_by_id": {self.item["id"]: self.item},
            "current_receipt_catalog": self.catalog,
            "receipt_catalog": {},
        }

    def resolution(self, *, catalog=None, obligation=None,
                   require_current=True):
        return runtime._required_obligation_resolution(
            self.result, self.item, self.plan, self.plan_sha256,
            self.catalog if catalog is None else catalog,
            self.obligation if obligation is None else obligation,
            require_current=require_current)

    @staticmethod
    def copy_with_id(record, receipt_id, *, invalidated_by=None):
        duplicate = copy.deepcopy(record)
        duplicate["receipt_id"] = receipt_id
        duplicate["invalidated_by"] = invalidated_by
        return duplicate


class AuditEvidenceReconciliationContractTests(CurrentEvidenceCheckpoint,
                                                unittest.TestCase):

    def test_current_typed_chain_resolves_to_one_reconciliation_row(self):
        resolution = self.resolution()
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, resolution)

        self.assertEqual(review_contract.RECEIPT_TYPE_ID,
                         self.review["receipt_type_id"])
        self.assertEqual(receipt_contract.RECEIPT_TYPE_ID,
                         self.full["receipt_type_id"])
        self.assertEqual("satisfied", resolution["status"])
        self.assertEqual(self.full["receipt_id"],
                         resolution["record"]["receipt_id"])
        self.assertEqual(self.full["receipt_id"],
                         row["selected_evidence_ref"])
        self.assertEqual(
            sorted((self.review["receipt_id"], self.full["receipt_id"])),
            row["produced_evidence_refs"])
        self.assertFalse(row["unresolved"])

    def test_resolution_status_matrix_uses_current_typed_attempts(self):
        duplicate_full = self.copy_with_id(
            self.full, "audit-complete_audit_receipt-duplicate-0001")
        misbound_full = self.copy_with_id(
            self.full, "audit-complete_audit_receipt-misbound-0001")
        misbound_full["audit_plan_sha256"] = digest("different-plan")
        cases = (
            ("empty", {}, "missing"),
            ("producer-only",
             {self.review["receipt_id"]: self.review},
             "ready-for-completion"),
            ("complete", self.catalog, "satisfied"),
            ("two-terminals", {
                **self.catalog, duplicate_full["receipt_id"]: duplicate_full,
            }, "ambiguous"),
            ("terminal-without-producer", {
                self.full["receipt_id"]: self.full,
            }, "invalid"),
            ("misbound-terminal", {
                self.review["receipt_id"]: self.review,
                misbound_full["receipt_id"]: misbound_full,
            }, "invalid"),
        )

        for label, catalog, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(
                    expected,
                    self.resolution(catalog=catalog)["status"])

    def test_terminal_receipt_cannot_mask_invalid_or_ambiguous_precursors(self):
        duplicate_review = self.copy_with_id(
            self.review, "audit-record_substantive_review-duplicate-0001")
        invalid_review = copy.deepcopy(self.review)
        invalid_review["audit_plan_sha256"] = digest("different-plan")
        cases = (
            ("ambiguous", "precursor", {
                **self.catalog,
                duplicate_review["receipt_id"]: duplicate_review,
            }),
            ("invalid", "invalid records", {
                self.full["receipt_id"]: self.full,
                invalid_review["receipt_id"]: invalid_review,
            }),
        )

        for expected, reason, catalog in cases:
            with self.subTest(expected=expected):
                resolution = self.resolution(catalog=catalog)
                self.assertEqual(expected, resolution["status"])
                self.assertIn(reason, resolution["reason"])

    def test_history_is_classified_but_never_reauthorizes_current_evidence(self):
        predecessor = self.copy_with_id(
            self.full, "audit-complete_audit_receipt-predecessor-0001",
            invalidated_by=self.full["receipt_id"])
        invalidated = self.copy_with_id(
            self.full, "audit-complete_audit_receipt-invalidated-0001",
            invalidated_by="standards-invalidation-event")
        self.result["receipt_catalog"] = {
            predecessor["receipt_id"]: predecessor,
            invalidated["receipt_id"]: invalidated,
        }

        resolution = self.resolution()
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, resolution)
        self.assertEqual([predecessor["receipt_id"]],
                         row["superseded_evidence_refs"])
        self.assertEqual([invalidated["receipt_id"]],
                         row["invalidated_evidence_refs"])
        self.assertFalse(row["unresolved"])

        unclassified = self.copy_with_id(
            self.full, "audit-complete_audit_receipt-unclassified-0001")
        self.result["receipt_catalog"][unclassified["receipt_id"]] = \
            unclassified
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, resolution)
        self.assertTrue(row["unresolved"])
        self.assertIn("absent from the current-use catalog",
                      row["unresolved_reason"])

    def test_reconciliation_projection_is_closed_disjoint_and_hash_bound(self):
        row = runtime._reconciliation_row(
            self.result, self.plan, self.obligation, self.resolution())
        projection_value = runtime._reconciliation_projection([row])
        self.assertEqual(
            projection_value,
            runtime.validate_plan_reconciliation(projection_value))

        overlapping = copy.deepcopy(projection_value)
        overlapping["audit_evidence_reconciliation"][0][
            "superseded_evidence_refs"] = [self.full["receipt_id"]]
        with self.assertRaisesRegex(runtime.AuditEvidenceError, "overlap"):
            runtime.validate_plan_reconciliation(overlapping)

        wrong_digest = copy.deepcopy(projection_value)
        wrong_digest["audit_evidence_reconciliation_sha256"] = \
            digest("wrong-reconciliation")
        with self.assertRaisesRegex(runtime.AuditEvidenceError, "sha256"):
            runtime.validate_plan_reconciliation(wrong_digest)


class AuditEvidenceCheckpointIntegrationTests(CurrentEvidenceCheckpoint,
                                              unittest.TestCase):

    def test_stage_and_batch_review_share_one_current_checkpoint(self):
        resolved = (
            ".cambium/work_specs/audit-plans/current.yaml",
            self.plan,
            self.plan_sha256,
        )
        with mock.patch.object(
                runtime, "_resolve_current_plan", return_value=resolved), \
                mock.patch.object(
                    runtime,
                    "_require_current_profile_rendering_contract_state",
                    return_value=None):
            status = runtime.stage_evidence_status(
                self.result, self.item, "pre-merge",
                required_state="open")
            closure = runtime.batch_review_evidence(
                self.result, self.item, required_state="open")
            self.assertEqual(
                [], runtime.wrapper_binding_errors(
                    self.result, self.item, copy.deepcopy(closure),
                    required_state="open"))

        self.assertEqual("satisfied", status["obligations"][0]["status"])
        self.assertEqual(status["audit_plan_id"], closure["audit_plan_id"])
        self.assertEqual(
            status["audit_evidence_reconciliation_sha256"],
            closure["audit_evidence_reconciliation_sha256"])
        self.assertEqual(
            self.full["receipt_id"],
            closure["audit_evidence_bindings"][0]["evidence_ref"])


if __name__ == "__main__":
    unittest.main()
