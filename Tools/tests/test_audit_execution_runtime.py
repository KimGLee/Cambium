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
        self.assertEqual(["obligation-1"], step["arguments"]["obligation_id"])
        self.assert_execution_consumer(step["capability_id"])
        second = dict(self.obligation, obligation_id="obligation-2", target="Topics/B.md")
        self.status["obligations"].append(dict(self.status["obligations"][0], obligation=second))
        grouped = self.project()
        self.assertEqual(["obligation-1", "obligation-2"], grouped["arguments"]["obligation_id"])
        self.assertEqual(step["capability_id"], grouped["capability_id"])

    def test_substantive_review_is_an_explicit_agent_boundary(self):
        self.use_substantive_obligation()

        step = self.project()

        self.assertEqual("await-agent", step["status"])
        self.assertEqual("record-substantive-review", step["token"])
        self.assertIn("verdict", step["required_input"]["parameters"])
        self.assertEqual("record_substantive_review", step["resume_tool"])
        self.assertEqual(1, step["resume_arguments"]["round"])
        self.assertNotIn("round_1_receipt_id", step["resume_arguments"])
        self.assert_execution_consumer(step["resume_capability_id"])


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
                self.assertIsNone(step["required_input"])
                self.assertIn("external_resolution", step["external_instruction"])

    def test_batch_page_inputs_leave_variant_and_evidence_selection_with_producer(self):
        registry = audit_execution_runtime.batch_review_obligation_contract
        for rule, variant in (
                (registry.S_SAMPLING_RULE_ID, "s-sampled-page"),
                (registry.M_ATOMIC_RULE_IDS[0], "m-atomic-item")):
            with self.subTest(rule=rule):
                spec = audit_obligation_projection.obligation_spec_for_rule(
                    rule, root=REPOSITORY)
                definition = audit_obligation_projection.resolve_obligation_definition(
                    spec, "Topics/A.md", **(
                        {"trigger": "new"} if variant == "m-atomic-item" else {}))
                self.obligation.clear()
                self.obligation.update(
                    audit_obligation_projection.required_obligation(definition))
                step = self.project()
                self.assertEqual({"batch", "plan", "page"}, set(step["resume_arguments"]))
                self.assertEqual({"reviews": "reviews"}, step["required_input"]["parameters"])
                self.assert_execution_consumer(step["resume_capability_id"])

    def test_m_shared_condition_is_selected_before_its_dependent_answers(self):
        target = "Topics/Page-1.md"
        registry = audit_execution_runtime.batch_review_obligation_contract.load_registry()
        shared = registry["m_shared_applicability"]
        dependency = next(row for row in registry["m_tier_atomic_items"]
                          if row["applicability"] == shared["dependent_predicate"])
        condition = next(row for row in registry["m_tier_atomic_items"]
                         if row["item_id"] == shared["condition_item_id"])
        consume_spec = audit_obligation_projection.obligation_spec_for_rule(
            dependency["rule_id"], root=REPOSITORY)
        emit_spec = audit_obligation_projection.obligation_spec_for_rule(
            condition["rule_id"], root=REPOSITORY)
        consuming = audit_obligation_projection.required_obligation(
            audit_obligation_projection.resolve_obligation_definition(
                consume_spec, target, trigger="new"))
        emitting = audit_obligation_projection.required_obligation(
            audit_obligation_projection.resolve_obligation_definition(
                emit_spec, target, trigger="new"))
        rows = [{
            "obligation": obligation,
            "status": "missing",
            "evidence_ref": None,
            "reason": "found 0",
        } for obligation in sorted(
            (consuming, emitting), key=lambda row: row["obligation_id"])]
        self.status["obligations"] = rows

        registry_owner = audit_execution_runtime.batch_review_obligation_contract
        with mock.patch.object(registry_owner, "_validate_registry", wraps=registry_owner._validate_registry) as validate:
            step = self.project()
            self.assertEqual(1, validate.call_count)

        self.assertEqual("await-agent", step["status"])
        self.assertEqual("record-batch-page-review", step["token"])
        self.assertEqual(target, step["target"]["page"])
        self.assertEqual(
            emitting["obligation_id"], step["target"]["obligation_id"])

        next(row for row in rows
             if row["obligation"]["obligation_id"] ==
             emitting["obligation_id"]).update(
                 status="satisfied", evidence_ref="shared-condition-evidence")
        step = self.project()
        self.assertEqual("await-agent", step["status"])
        self.assertEqual(
            consuming["obligation_id"], step["target"]["obligation_id"])
        self.assertEqual(["shared-condition-evidence"],
                         step["target"]["review_input_constraints"]["consumed_evidence_refs"])
        self.assertEqual(["applicable"], step["target"][
            "review_input_constraints"]["allowed_applicability_dispositions"])

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
