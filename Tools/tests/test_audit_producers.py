"""Focused producer tests for AuditPlan -> accepted review evidence."""

from pathlib import Path
from types import SimpleNamespace
import contextlib
import io
import json
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.record_substantive_review as record_substantive_review
import Tools.execution.audit.substantive_review_contract as substantive_review_contract
import Tools.platform.common.kblib as kblib


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
            "schema_version": audit_plan_contract.load_contract(
                str(REPOSITORY))["schema_version"],
            "plan_id": "audit-plan-test",
            "task_id": "task-test",
            "batch_id": "B001",
            "generated_at": "2026-08-28T00:00:00Z",
            "queue_revision": 1,
            "queue_state_revision": 2,
            "required_queue_sha256": SHA_A,
            "upstream_revision_id": "standards-test",
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/test/profile.toml",
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


    def test_review_first_publication_binds_the_kernel_obligation(self):
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
        self.assertEqual(plan["plan_id"], evidence["plan_id"])
        self.assertEqual(plan_sha, evidence["audit_plan_sha256"])
        self.assertEqual(obligation["obligation_id"], evidence["obligation_id"])
        self.assertEqual(obligation["evidence_kind"], evidence["record_kind"])
        self.assertEqual(
            audit_producer_runtime.page_artifact_fingerprint(frozen_page),
            evidence["artifact_fingerprint"])
        self.assertNotEqual(evidence["semantic_content_fingerprint"],
                            evidence["artifact_fingerprint"])
        self.assertNotIn("evidence_ref", evidence)

    def test_changes_required_confirms_recording_without_claiming_review_pass(self):
        obligation = self.obligation()
        plan = self.plan(obligation)
        plan_sha = audit_plan_contract.plan_sha256(plan)
        frozen = (self.frozen("L.md"),)
        path = str(REPOSITORY / ".cambium/receipts/unit-review.jsonl")
        runtime = record_substantive_review.audit_evidence_runtime
        finding = {
            "finding_id": "finding-001", "severity": "critical",
            "statement": "the conclusion does not follow", "status": "open",
            "round_1_finding_id": None,
        }

        def observe_publication(publication, actual_path, receipts, *, before=None):
            self.assertEqual(path, actual_path)
            publication.outcome = "present"
            publication.observation = kblib.ReceiptObservation(
                {"path": path}, b"".join(kblib.canonical_json_bytes(row) + b"\n" for row in receipts))
            return "present", None, before

        with contextlib.ExitStack() as stack:
            for owner, name, value in (
                    (audit_producer_runtime, "admitted_runtime", (str(REPOSITORY), {}, object())),
                    (audit_producer_runtime, "open_batch", ({}, {})),
                    (audit_producer_runtime, "managed_receipt_path", path),
                    (audit_producer_runtime, "runtime_lock_metadata", {}),
                    (audit_producer_runtime, "require_runtime_current", {}),
                    (audit_producer_runtime, "require_pages_current", None),
                    (record_substantive_review, "load_current_plan", (None, plan, plan_sha, frozen)),
                    (record_substantive_review, "_require_plan_current", None),
                    (runtime, "require_substantive_review_attempt", None),
                    (runtime, "obligation_evidence_resolution", {"status": "awaiting-revision"}),
                    (kblib, "receipt_append_observation", {})):
                stack.enter_context(mock.patch.object(owner, name, return_value=value))
            stack.enter_context(mock.patch.object(runtime, "evidence_evaluation", side_effect=lambda result: result))
            stack.enter_context(mock.patch.object(kblib, "runtime_write_lock",
                side_effect=lambda *args, **kwargs: contextlib.nullcontext(object())))
            stack.enter_context(mock.patch.object(kblib, "no_authoritative_write_guard",
                side_effect=lambda lease: contextlib.nullcontext()))
            stack.enter_context(mock.patch.object(kblib.ReceiptPublication, "append",
                autospec=True, side_effect=observe_publication))
            stack.enter_context(mock.patch.object(kblib, "read_receipt_bytes",
                side_effect=AssertionError("semantic confirmation must share the append observation")))
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            code = record_substantive_review.main([
                str(REPOSITORY), "--batch", "B001", "--plan", "unused.yaml",
                "--obligation-id", obligation["obligation_id"], "--page", "L.md",
                "--authoring-context-id", "author", "--reviewer-context-id", "reviewer",
                "--reviewer-role", "reviewer", "--round", "1",
                "--verdict", "changes-required", "--statement", "reviewed",
                "--finding", json.dumps(finding), "--apply"])
        result = json.loads(output.getvalue())
        self.assertEqual(1, code)
        self.assertEqual(("recorded", "fail", "changes-required"),
                         (result["status"], result["result"], result["verdict"]))
        self.assertTrue(result["applied"])
        self.assertEqual("confirmed", result["publication"]["record_confirmation"])

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
