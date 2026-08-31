"""Dispatch tests for the read-only AuditPlan execution projection."""

from pathlib import Path
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "Tools"))

import Tools.execution.audit.audit_execution_runtime as audit_execution_runtime
import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract


class AuditExecutionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.item = {"id": "B001", "state": "open"}
        self.obligation = {
            "obligation_id": "obligation-1",
            "owner_rule_id": "k12-02-check",
            "partition": "changed-scope-deterministic",
            "target": "Topics/A.md",
            "evidence_kind": "gate-receipt",
            "producer_capability": None,
            "producer_check": "page-contract-summary",
        }
        self.status = {
            "audit_plan_id": "audit-plan-1",
            "audit_plan_path":
                ".cambium/work_specs/audit-plans/audit-plan-1.yaml",
            "audit_plan_sha256": "sha256:" + "a" * 64,
            "due_stage": "pre-merge",
            "obligations": [{
                "obligation": self.obligation,
                "status": "missing",
                "evidence_ref": None,
                "reused": False,
                "reason": "found 0",
            }],
        }
        self.result = {
            "root": str(REPOSITORY),
            "current_receipt_catalog": {},
        }

    def project(self):
        with mock.patch.object(
                audit_execution_runtime.audit_evidence_runtime,
                "stage_evidence_status", return_value=self.status):
            return audit_execution_runtime.next_stage_step(
                self.result, self.item, "pre-merge",
                required_state="open")

    def use_substantive_obligation(self):
        spec = audit_obligation_projection.obligation_spec_for_rule(
            "k12-12-substantive-correctness-review", root=REPOSITORY)
        definition = audit_obligation_projection.\
            resolve_obligation_definition(
                spec, "Topics/A.md", trigger="new")
        required = audit_obligation_projection.required_obligation(definition)
        required["obligation_id"] = "obligation-1"
        self.obligation.clear()
        self.obligation.update(required)

    def assert_execution_consumer(self, capability_id):
        entry = metadata_execution_contract.capability_entry_by_id(
            capability_id, root=REPOSITORY)
        self.assertIn(
            "Tools/execution/audit/audit_execution_runtime.py",
            entry["consumers"])

    def test_direct_deterministic_evidence_uses_registered_adapter(self):
        step = self.project()

        self.assertEqual("invoke", step["status"])
        self.assertEqual(
            "changed-scope-evidence-adapter-v1", step["capability_id"])
        self.assertEqual("record_changed_scope_evidence", step["tool"])
        self.assertEqual("obligation-1", step["arguments"]["obligation_id"])
        self.assert_execution_consumer(step["capability_id"])

    def test_substantive_review_is_an_explicit_agent_boundary(self):
        self.use_substantive_obligation()

        step = self.project()

        self.assertEqual("await-agent", step["status"])
        self.assertEqual("record-substantive-review", step["token"])
        self.assertIn("verdict", step["required_input"])
        self.assertEqual("record_substantive_review", step["resume_tool"])
        self.assert_execution_consumer(step["resume_capability_id"])

    def test_existing_precursor_is_completed_not_reproduced(self):
        self.use_substantive_obligation()
        self.result["current_receipt_catalog"] = {
            "review-1": ("receipts/reviews.jsonl", {
                "receipt_id": "review-1",
                "record_kind": "substantive-review-evidence",
                "plan_id": "audit-plan-1",
                "obligation_id": "obligation-1",
            }),
        }
        self.status["obligations"][0].update({
            "status": "ready-for-completion",
            "evidence_ref": "review-1",
            "reason": None,
        })

        step = self.project()

        self.assertEqual("invoke", step["status"])
        self.assertEqual("complete_audit_receipt", step["tool"])
        self.assertEqual("review-1", step["arguments"]["evidence_receipt"])
        self.assert_execution_consumer(step["capability_id"])

    def test_invalid_or_ambiguous_evidence_requires_repair(self):
        for state in ("invalid", "ambiguous"):
            with self.subTest(state=state):
                self.status["obligations"][0]["status"] = state
                self.status["obligations"][0]["reason"] = "broken binding"
                step = self.project()
                self.assertEqual("repair", step["status"])
                self.assertEqual(
                    "audit-evidence-%s" % state, step["reason_code"])

    def test_unknown_evidence_status_fails_closed_instead_of_producing(self):
        self.status["obligations"][0]["status"] = "future-status"
        self.status["obligations"][0]["reason"] = "not registered"

        step = self.project()

        self.assertEqual("repair", step["status"])
        self.assertEqual("repair-audit-evidence", step["token"])
        self.assertEqual(
            "unknown-audit-evidence-status", step["reason_code"])
        self.assertIsNone(step["tool"])

    def test_correction_and_escalation_are_external_reparse_boundaries(self):
        expectations = {
            "needs-correction": ("await-agent", "correct-audit-target"),
            "escalated": (
                "await-user", "resolve-substantive-review-escalation"),
        }
        for state, expected in expectations.items():
            with self.subTest(state=state):
                self.status["obligations"][0]["status"] = state
                self.status["obligations"][0]["reason"] = "owned work pending"
                step = self.project()
                self.assertEqual(expected, (step["status"], step["token"]))
                self.assertIsNone(step["capability_id"])
                self.assertIsNone(step["tool"])
                self.assertNotIn("resume_tool", step)
                self.assertIn("external_resolution", step["required_input"])

    def test_batch_page_variant_comes_from_frozen_producer_check(self):
        self.obligation.update({
            "evidence_kind": "batch-page-review-record",
            "producer_capability": "batch-page-review-attestation-v1",
            "producer_check": "batch_page_review:s-tier-sampled-review",
        })
        step = self.project()
        self.assertEqual(
            "s-sampled-page", step["resume_arguments"]["variant"])

        self.obligation["producer_check"] = \
            "batch_page_review:m01-note-type-explicit-consistent"
        step = self.project()
        self.assertEqual("m-atomic-item", step["resume_arguments"]["variant"])
        self.assert_execution_consumer(step["resume_capability_id"])

    def test_m_consumption_waits_for_registry_selected_evidence_not_hash_order(self):
        target = "Topics/Page-1.md"
        consume_spec = audit_obligation_projection.obligation_spec_for_rule(
            "k12-01-m-tier-no-required-link-ambiguous", root=REPOSITORY)
        emit_spec = audit_obligation_projection.obligation_spec_for_rule(
            "k12-02-level0-wiki-link-resolution", root=REPOSITORY)
        consuming = audit_obligation_projection.required_obligation(
            audit_obligation_projection.resolve_obligation_definition(
                consume_spec, target, trigger="new"))
        emitting = audit_obligation_projection.required_obligation(
            audit_obligation_projection.resolve_obligation_definition(
                emit_spec, target))
        self.assertLess(
            consuming["obligation_id"], emitting["obligation_id"],
            "the regression needs the consumes identity to sort first")
        rows = [{
            "obligation": obligation,
            "status": "missing",
            "evidence_ref": None,
            "reused": False,
            "reason": "found 0",
        } for obligation in sorted(
            (consuming, emitting), key=lambda row: row["obligation_id"])]
        self.status["obligations"] = rows

        step = self.project()

        self.assertEqual("invoke", step["status"])
        self.assertEqual("record-changed-scope-evidence", step["token"])
        self.assertEqual(target, step["target"]["page"])
        self.assertEqual(
            emitting["obligation_id"], step["target"]["obligation_id"])

        next(row for row in rows
             if row["obligation"]["obligation_id"] ==
             emitting["obligation_id"])["status"] = "satisfied"
        step = self.project()
        self.assertEqual("await-agent", step["status"])
        self.assertEqual(
            consuming["obligation_id"], step["target"]["obligation_id"])

    def test_audit_plan_and_profile_judgment_routes_are_registered(self):
        self.assert_execution_consumer("audit-plan-producer-v1")
        self.obligation.update({
            "evidence_kind": "page-batch-judgment-v2",
            "producer_capability": "manual-attestation-v1",
            "producer_check": "profile_batch_judgment",
        })

        step = self.project()

        self.assertEqual("await-agent", step["status"])
        self.assertEqual("record-profile-batch-judgment", step["token"])
        self.assertEqual("record_batch_judgment", step["resume_tool"])

    def test_profile_judgment_route_fails_closed_when_consumer_is_absent(self):
        self.obligation.update({
            "evidence_kind": "page-batch-judgment-v2",
            "producer_capability": "manual-attestation-v1",
            "producer_check": "profile_batch_judgment",
        })
        with mock.patch.object(
                audit_execution_runtime, "_registered_consumer",
                return_value=False):
            step = self.project()

        self.assertEqual("repair", step["status"])
        self.assertEqual(
            "profile-judgment-producer-not-registered",
            step["reason_code"])

    def test_complete_stage_returns_the_final_consumer_closure(self):
        self.status["obligations"][0]["status"] = "satisfied"
        closure = {"audit_evidence_set_sha256": "sha256:" + "b" * 64}
        with mock.patch.object(
                audit_execution_runtime.audit_evidence_runtime,
                "stage_evidence_status", return_value=self.status), \
                mock.patch.object(
                    audit_execution_runtime.audit_evidence_runtime,
                    "stage_evidence_closure", return_value=closure):
            step = audit_execution_runtime.next_stage_step(
                self.result, self.item, "pre-merge",
                required_state="open")

        self.assertEqual("complete", step["status"])
        self.assertEqual(closure, step["closure"])


if __name__ == "__main__":
    unittest.main()
