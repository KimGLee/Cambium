"""Focused producer tests for AuditPlan -> review -> full AuditReceipt."""

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import audit_plan_contract
import audit_producer_runtime
import audit_receipt_contract
import batch_review_obligation_contract
import complete_audit_receipt
import prepare_audit_plan
import record_substantive_review
import substantive_review_contract


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
PAGE_TEXT = "# Page\n\nReasoning.\n\n## Sources\n\n- source\n"


class AuditProducerTests(unittest.TestCase):
    def frozen(self, path, semantic=SHA_B):
        return audit_producer_runtime.FrozenPage(
            path=path, page_sha256=SHA_A,
            semantic_content_fingerprint=semantic,
            snapshot=SimpleNamespace(read_text=lambda: PAGE_TEXT),
        )

    def plan(self, obligation):
        plan = {
            "schema_version": 1,
            "plan_id": "audit-plan-test",
            "task_id": "task-test",
            "batch_id": "B001",
            "generated_at": "2026-08-28T00:00:00Z",
            "queue_revision": 1,
            "queue_state_revision": 2,
            "required_queue_sha256": SHA_A,
            "standards_version": "standards-test",
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_A,
            "profile_contract_fingerprint": SHA_A,
            "opening_transition_receipt": "audit-open",
            "artifact_snapshot_sha256": SHA_A,
            "contract_snapshot_sha256": SHA_A,
            "accepted_baseline_sha256": SHA_A,
            "obligations": [obligation],
        }
        audit_plan_contract.validate_plan(plan)
        return plan

    def obligation(self, path="L.md"):
        projection = substantive_review_contract.load_contract(
            str(REPOSITORY))["obligation_projection"]
        partition = next(
            row["partition"]
            for row in projection["trigger_partition_mappings"]
            if row["trigger"] == "needs_rereview")
        return {
            "obligation_id": "substantive-review-0001",
            "owner_kind": projection["owner_kind"],
            "owner_rule_id": projection["owner_rule_id"],
            "kernel_extension_point": projection[
                "kernel_extension_point"],
            "partition": partition,
            "due_stage": projection["due_stage"],
            "target": path,
            "applicability": projection["applicability"],
            "evidence_role": projection["evidence_role"],
            "evidence_kind": projection["evidence_kind"],
            "dimension": projection["dimension"],
            "acceptance_predicate": projection[
                "acceptance_predicate"],
            "producer_check": projection["producer_check"],
            "producer_capability": projection["producer_capability"],
            "producer_gate_id": projection["producer_gate_id"],
            "consumer_gate_id": projection["consumer_gate_id"],
            "fingerprint_binding": projection["fingerprint_binding"],
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }

    def test_plan_derives_l_m_and_registry_selected_s_obligations(self):
        frozen = tuple(self.frozen(path) for path in ("L.md", "M.md", "S.md"))
        required_scan = SimpleNamespace(
            scan_id="fixture-residual",
            required_for_k12_item_6=True,
            judgment_item_id="fixture-residual-judgment",
            candidate_predicate="fixture residual predicate",
        )
        contract = SimpleNamespace(
            authorized=True,
            manifest_repo_path="profiles/test/profile.md",
            profile_contract_fingerprint=SHA_A,
            extension_dimensions=(),
            judgment_items=(SimpleNamespace(
                judgment_item_id="fixture-residual-judgment",
                dimension_id="coverage_and_integration",
                evidence_role="emits",
                predicate_owner=None,
            ),),
            registered_scans=(required_scan,),
            required_scan=required_scan,
            batch_review_requirements=(),
        )
        result = {
            "coverage": {"pages": [
                {"path": "L.md", "tier": "L",
                 "authoring_status": "unassessed", "property_state": {}},
                {"path": "M.md", "tier": "M",
                 "authoring_status": "unassessed", "property_state": {}},
                {"path": "S.md", "tier": "S",
                 "authoring_status": "unassessed", "property_state": {}},
            ]},
            "_profile_authorized_view": {"_contract": contract},
        }
        item = {"id": "B001", "manifest": ["L.md", "M.md", "S.md"]}
        activation = {}
        state = {
            "task_id": "task-test", "queue_revision": 1,
            "queue_state_revision": 2, "required_queue_sha256": SHA_A,
            "coverage_ledger_sha256": SHA_A,
            "progress_ledger_sha256": SHA_A,
        }
        profile = {
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_A,
            "profile_contract_fingerprint": SHA_A,
        }
        standards = {
            "standards_version": "standards-test",
            "active_standards_sha256": SHA_A,
        }
        opening = {
            "opening_transition_receipt": "audit-open",
            "manifest_semantic_before_set_sha256": SHA_A,
        }
        with mock.patch.object(
                audit_producer_runtime, "freeze_manifest_pages",
                return_value=frozen), mock.patch.object(
                    audit_producer_runtime, "runtime_state_bindings",
                    return_value=state), mock.patch.object(
                        audit_producer_runtime, "profile_bindings",
                        return_value=profile), mock.patch.object(
                            audit_producer_runtime, "standards_bindings",
                            return_value=standards), mock.patch.object(
                                prepare_audit_plan,
                                "check_queue_opening_context",
                                return_value=opening), mock.patch.object(
                                    prepare_audit_plan,
                                    "_changed_scope_targets",
                                    return_value=((), None)):
            plan, _ = prepare_audit_plan.build_plan(
                str(REPOSITORY), result, item, activation,
                generated_at="2026-08-28T00:00:00Z")
        registry = batch_review_obligation_contract.load_registry(
            str(REPOSITORY))
        m_rules = {row["rule_id"]
                   for row in registry["m_tier_atomic_items"]}
        s_rule = registry["s_tier_sampling"]["rule_id"]
        substantive_rule = substantive_review_contract.load_contract(
            str(REPOSITORY))["obligation_projection"]["owner_rule_id"]
        rows = plan["obligations"]
        self.assertEqual(1, sum(
            row["owner_rule_id"] == substantive_rule and
            row["target"] == "L.md" for row in rows))
        self.assertEqual(m_rules, {
            row["owner_rule_id"] for row in rows
            if row["target"] == "M.md" and
            row["owner_rule_id"] in m_rules})
        self.assertFalse(any(
            row["owner_rule_id"] == substantive_rule and
            row["target"] == "M.md" for row in rows))
        expected_s = batch_review_obligation_contract.select_s_targets(
            ["S.md"], task_id=plan["task_id"],
            batch_id=plan["batch_id"],
            opening_transition_receipt=plan[
                "opening_transition_receipt"],
            registry=registry)["sample_selected_targets"]
        self.assertEqual(expected_s, sorted(
            row["target"] for row in rows
            if row["owner_rule_id"] == s_rule))

    def test_review_and_full_receipt_match_kernel_contracts(self):
        obligation = self.obligation()
        plan = self.plan(obligation)
        plan_sha = audit_plan_contract.plan_sha256(plan)
        frozen_page = self.frozen("L.md")
        evidence = record_substantive_review.build_review_receipt(
            root=str(REPOSITORY), result={}, plan=plan,
            plan_sha256=plan_sha, obligation=obligation, page="L.md",
            frozen=(frozen_page,),
            authoring_context_id="author-context",
            reviewer_context_id="review-context",
            reviewer_role="reviewer", round_number=1,
            verdict="passed", findings=[], statement="reviewed", prior=None)
        substantive_review_contract.validate_review_receipt(evidence)
        full = complete_audit_receipt.build_audit_receipt(
            plan=plan, plan_sha256=plan_sha,
            obligation=obligation, evidence=evidence)
        audit_receipt_contract.validate_audit_receipt(full)
        self.assertEqual("content_and_depth", full["dimension"])
        self.assertEqual(
            audit_producer_runtime.page_artifact_fingerprint(frozen_page),
            full["artifact_fingerprint"])
        self.assertNotEqual(
            evidence["semantic_content_fingerprint"],
            full["artifact_fingerprint"])
        self.assertEqual(evidence["receipt_id"], full["evidence_ref"])

    def test_review_refuses_authoring_context_as_reviewer(self):
        obligation = self.obligation()
        plan = self.plan(obligation)
        with self.assertRaisesRegex(ValueError, "must differ"):
            record_substantive_review.build_review_receipt(
                root=str(REPOSITORY), result={}, plan=plan,
                plan_sha256=audit_plan_contract.plan_sha256(plan),
                obligation=obligation, page="L.md",
                frozen=(self.frozen("L.md"),),
                authoring_context_id="same", reviewer_context_id="same",
                reviewer_role="reviewer", round_number=1,
                verdict="passed", findings=[], statement="reviewed")


if __name__ == "__main__":
    unittest.main()
