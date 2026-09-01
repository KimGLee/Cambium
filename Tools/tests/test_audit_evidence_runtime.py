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
from Tools.tests.support.profile_contract_fixture import (  # noqa: E402
    CurrentProfileContractFixture,
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


class TerminalDimensionEvidenceProjectionTests(unittest.TestCase):
    """Own the closed-plan to Terminal dimension-evidence projection."""

    def setUp(self):
        self.profile_fixture = CurrentProfileContractFixture(self)
        self.profile_fixture.configure_extension_dimensions((
            ("language_quality", "receipt", "Language quality receipt."),
        ))
        self.profile_contract = self.profile_fixture.load()
        self.assertTrue(
            self.profile_contract.authorized,
            self.profile_contract.diagnostics)
        self.plan_sha256 = digest("terminal-plan")
        self.plan_path = \
            ".cambium/work_specs/audit-plans/audit-plan-B001.yaml"
        self.obligations = [
            {
                "obligation_id": "m-content",
                "due_stage": "pre-merge",
                "dimension": "content_and_depth",
                "evidence_kind": "batch-page-review-record",
            },
            {
                "obligation_id": "profile-language",
                "due_stage": "pre-merge",
                "dimension": "language_quality",
                "evidence_kind": "page-batch-judgment-v2",
            },
            {
                "obligation_id": "page-contract",
                "due_stage": "post-delta-close",
                "dimension": None,
                "evidence_kind": "gate-receipt",
            },
            {
                "obligation_id": "m-source-not-applicable",
                "due_stage": "pre-merge",
                "dimension": "source_and_currentness",
                "evidence_kind": "batch-page-review-record",
            },
        ]
        self.records = {
            "evidence-m-content": {
                "receipt_id": "evidence-m-content",
                "record_kind": "batch-page-review-record",
                "review_variant": "m-atomic-item",
                "applicability_disposition": "applicable",
            },
            "evidence-profile-language": {
                "receipt_id": "evidence-profile-language",
                "record_kind": "page-batch-judgment-v2",
            },
            "evidence-page-contract": {
                "receipt_id": "evidence-page-contract",
                "record_kind": "gate-receipt",
            },
            "evidence-m-source-na": {
                "receipt_id": "evidence-m-source-na",
                "record_kind": "batch-page-review-record",
                "review_variant": "m-atomic-item",
                "applicability_disposition": "not-applicable",
                "applicability_reason": "no source claim is present",
            },
        }
        self.refs = dict(zip(
            (row["obligation_id"] for row in self.obligations),
            self.records,
        ))
        reconciliation = runtime._reconciliation_projection([{
            "obligation_id": row["obligation_id"],
            "due_stage": row["due_stage"],
            "selected_evidence_ref": self.refs[row["obligation_id"]],
            "selected_disposition": "produced",
            "produced_evidence_refs": [self.refs[row["obligation_id"]]],
            "reused_reserved_evidence_ref": None,
            "superseded_evidence_refs": [],
            "invalidated_evidence_refs": [],
            "unresolved": False,
            "unresolved_reason": None,
        } for row in self.obligations])
        self.close = {
            "receipt_id": "close-B001",
            "result": "pass",
            "invalidated_by": None,
            "audit_plan_id": "audit-plan-B001",
            "audit_plan_path": self.plan_path,
            "audit_plan_sha256": self.plan_sha256,
            **reconciliation,
        }
        self.item = {
            "id": "B001",
            "state": "closed",
            "close_gate_receipt": self.close["receipt_id"],
        }
        self.plan = {
            "plan_id": "audit-plan-B001",
            "obligations": copy.deepcopy(self.obligations),
        }
        self.result = {
            "root": str(REPOSITORY),
            "errors": [],
            "items_by_id": {"B001": self.item},
            "current_receipt_catalog": {
                self.close["receipt_id"]: self.close,
                **self.records,
            },
            "invalidated_evidence_receipt_ids": [],
            "_profile_authorized_view": {
                "_contract": self.profile_contract,
            },
        }

    def _resolution(self, obligation):
        record = self.records[self.refs[obligation["obligation_id"]]]
        return {
            "status": "satisfied",
            "record": record,
            "reused": False,
            "reason": None,
            "attempts": [],
        }

    def _postdelta_closure(self):
        obligations = [
            row for row in self.obligations
            if row["due_stage"] == "post-delta-close"
        ]
        reconciliation = runtime._reconciliation_projection([{
            "obligation_id": row["obligation_id"],
            "due_stage": row["due_stage"],
            "selected_evidence_ref": self.refs[row["obligation_id"]],
            "selected_disposition": "produced",
            "produced_evidence_refs": [self.refs[row["obligation_id"]]],
            "reused_reserved_evidence_ref": None,
            "superseded_evidence_refs": [],
            "invalidated_evidence_refs": [],
            "unresolved": False,
            "unresolved_reason": None,
        } for row in obligations])
        return {
            "stage_plan": {
                "audit_plan_path": self.plan_path,
                "audit_plan_sha256": self.plan_sha256,
                "plan": self.plan,
            },
            "final_by_obligation": {
                row["obligation_id"]:
                    self.records[self.refs[row["obligation_id"]]]
                for row in obligations
            },
            "reconciliation": reconciliation,
        }

    def project(self):
        with mock.patch.object(
                runtime, "_post_delta_evidence_closure",
                return_value=self._postdelta_closure()), mock.patch.object(
                runtime, "_required_obligation_resolution",
                side_effect=lambda _result, _item, _plan, _sha, _catalog,
                obligation, require_current: self._resolution(obligation)):
            return runtime.terminal_dimension_evidence(self.result)

    def test_m_and_profile_evidence_project_but_dimensionless_and_na_do_not(self):
        rows = self.project()
        self.assertEqual(
            [
                ("content_and_depth", "batch-page-review-record",
                 "evidence-m-content"),
                ("language_quality", "page-batch-judgment-v2",
                 "evidence-profile-language"),
            ],
            [(row["dimension"], row["evidence_kind"], row["evidence_ref"])
             for row in rows],
        )

        self.result["current_receipt_catalog"]["foreign-current"] = {
            "receipt_id": "foreign-current",
            "record_kind": "batch-page-review-record",
            "dimension": "content_and_depth",
        }
        self.assertEqual(rows, self.project())

    def test_invalidated_or_owner_rejected_selected_evidence_fails_closed(self):
        self.result["invalidated_evidence_receipt_ids"] = [
            "evidence-m-content"]
        with self.assertRaisesRegex(
                runtime.AuditEvidenceError, "invalidated evidence"):
            self.project()

        self.result["invalidated_evidence_receipt_ids"] = []
        original = self._resolution

        def stale(obligation):
            value = original(obligation)
            if obligation["obligation_id"] == "m-content":
                value.update({
                    "status": "missing", "record": None,
                    "reason": "owner rejected stale input",
                })
            return value

        with mock.patch.object(self, "_resolution", side_effect=stale):
            with self.assertRaisesRegex(
                runtime.AuditEvidenceError,
                "no current selected evidence"):
                self.project()

    def test_close_reconciliation_scopes_current_records_and_rejects_history(self):
        reconciliation = {
            "selected_evidence_ref": "selected-final",
            "selected_disposition": "produced",
            "produced_evidence_refs": ["selected-final", "selected-raw"],
        }
        current = {
            "selected-final": {"receipt_id": "selected-final"},
            "selected-raw": {"receipt_id": "selected-raw"},
            "foreign-final": {"receipt_id": "foreign-final"},
            "foreign-raw": {"receipt_id": "foreign-raw"},
        }
        scoped = runtime._reconciled_current_catalog(
            current, reconciliation, batch_id="B001",
            obligation_id="m-content")
        self.assertEqual(
            {"selected-final", "selected-raw"}, set(scoped))

        historical_only = {
            "foreign-final": current["foreign-final"],
            "foreign-raw": current["foreign-raw"],
        }
        with self.assertRaisesRegex(
                runtime.AuditEvidenceError,
                "absent from the current receipt catalog"):
            runtime._reconciled_current_catalog(
                historical_only, reconciliation, batch_id="B001",
                obligation_id="m-content")

    def test_post_delta_reconciliation_must_equal_owner_closure(self):
        rows = copy.deepcopy(
            self.close["audit_evidence_reconciliation"])
        target = next(row for row in rows
                      if row["obligation_id"] == "page-contract")
        target["selected_evidence_ref"] = "foreign-page-contract"
        target["produced_evidence_refs"] = ["foreign-page-contract"]
        self.close.update(runtime._reconciliation_projection(rows))
        self.result["current_receipt_catalog"]["foreign-page-contract"] = {
            "receipt_id": "foreign-page-contract",
            "record_kind": "gate-receipt",
        }

        with self.assertRaisesRegex(
                runtime.AuditEvidenceError,
                "no current selected evidence matching"):
            self.project()

    def test_typed_profile_receipt_target_enters_but_review_only_stays_out(self):
        self.profile_fixture.configure_extension_dimensions((
            ("language_quality", "receipt", "Language quality receipt."),
            ("review_only", "review", "Review-only judgment."),
            ("terminal_receipt", "receipt", "Terminal receipt judgment."),
        ))
        contract = self.profile_fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.result["_profile_authorized_view"] = {"_contract": contract}

        additions = (
            ("profile-review-only", "review_only",
             "evidence-profile-review-only"),
            ("profile-terminal-receipt", "terminal_receipt",
             "evidence-profile-terminal-receipt"),
        )
        for obligation_id, dimension, evidence_ref in additions:
            self.obligations.append({
                "obligation_id": obligation_id,
                "due_stage": "pre-merge",
                "dimension": dimension,
                "evidence_kind": "page-batch-judgment-v2",
            })
            self.records[evidence_ref] = {
                "receipt_id": evidence_ref,
                "record_kind": "page-batch-judgment-v2",
            }
            self.refs[obligation_id] = evidence_ref
            self.result["current_receipt_catalog"][evidence_ref] = \
                self.records[evidence_ref]
        self.plan["obligations"] = copy.deepcopy(self.obligations)
        self.close.update(runtime._reconciliation_projection([{
            "obligation_id": row["obligation_id"],
            "due_stage": row["due_stage"],
            "selected_evidence_ref": self.refs[row["obligation_id"]],
            "selected_disposition": "produced",
            "produced_evidence_refs": [self.refs[row["obligation_id"]]],
            "reused_reserved_evidence_ref": None,
            "superseded_evidence_refs": [],
            "invalidated_evidence_refs": [],
            "unresolved": False,
            "unresolved_reason": None,
        } for row in self.obligations]))

        rows = self.project()
        projected = {
            row["obligation_id"]: row["dimension"] for row in rows
        }
        self.assertEqual(
            "terminal_receipt", projected["profile-terminal-receipt"])
        self.assertNotIn("profile-review-only", projected)


if __name__ == "__main__":
    unittest.main()
