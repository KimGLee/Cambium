"""Minimal inputs shared by post-Delta owner and consumer tests.

This factory does not resolve obligations, accept evidence, sign Receipts or
replay a Task. Tests invoke the real owner separately and derive expected
membership directly from the Kernel registry.
"""

from copy import deepcopy
from types import SimpleNamespace

from Tools.execution.audit import check_batch_close
from Tools.knowledge.metadata import check_page_contract
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION


SHA_A, SHA_B, SHA_C, SHA_D, SHA_E, SHA_F = (
    "sha256:" + character * 64 for character in "abcdef")


def profile_binding():
    return SimpleNamespace(
        required_scan=SimpleNamespace(judgment_item_id="fixture-residual-judgment"),
        judgment_items=(SimpleNamespace(
            judgment_item_id="fixture-residual-judgment",
            dimension_id="content_and_depth", evidence_role="emits"),),
        fingerprint=SHA_A, extension_gates=())


def plan_stage(rows, obligations=None):
    if obligations is None:
        obligations = []
        for row in rows:
            binding = row["dimension_binding"]
            dimension = (row["dimension"] if binding == "fixed" else
                         "content_and_depth" if binding == "profile-registration" else None)
            obligations.append({
                "obligation_id": "post-delta-%s" % row["member_id"],
                "owner_kind": "kernel", "owner_rule_id": row["rule_id"],
                "kernel_extension_point": None, "partition": "mandatory-full-deterministic",
                "due_stage": row["due_stage"],
                "target": "page-contract" if row["evidence_kind"] == "gate-receipt" else ".",
                "applicability": "always", "evidence_role": row["evidence_role"],
                "evidence_kind": row["evidence_kind"], "dimension": dimension,
                "acceptance_predicate": "fixture-%s-passes" % row["member_id"],
                "producer_check": row["producer_check"],
                "producer_capability": row.get("producer_capability"),
                "producer_gate_id": row.get("producer_gate_id"),
                "consumer_gate_id": row["consumer_gate_id"],
                "fingerprint_binding": "evidence-time", "review_due": None,
                "status": "required", "evidence_ref": None,
                "reused_receipt_id": None, "reuse_reason": None})
    plan = {
        "plan_id": "plan-b1", "task_id": "task-1", "batch_id": "B1",
        "opening_transition_receipt": "open-b1",
        "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
        "active_standards_sha256": SHA_B,
        "selected_profile_manifest": "profiles/test/profile.toml",
        "profile_snapshot_sha256": SHA_C, "profile_contract_fingerprint": SHA_D,
        "contract_snapshot_sha256": SHA_E, "obligations": deepcopy(list(obligations))}
    return {"audit_plan_id": plan["plan_id"],
            "audit_plan_path": ".cambium/work_specs/audit-plans/plan-b1.yaml",
            "audit_plan_sha256": SHA_A, "plan": plan,
            "obligations": tuple(plan["obligations"])}


def gate_evidence():
    return {"receipt_id": "page-contract-gate", "tool": "check_page_contract",
            "tool_version": check_page_contract.TOOL_VERSION, "check": "page-contract-summary",
            "target": "page-contract", "result": "pass", "details": "fixture Gate passed",
            "checked_at": "2026-08-28T00:00:00Z", "invalidated_by": None,
            "gate_id": "page-contract"}


def producer_evidence(stage, obligation, ordinal):
    plan = stage["plan"]
    return {
        "receipt_id": "raw-%02d" % ordinal, "tool": "check_batch_close",
        "tool_version": check_batch_close.TOOL_VERSION,
        "check": obligation["producer_check"], "target": obligation["target"],
        "result": "pass", "details": "fixture producer evidence",
        "checked_at": "2026-08-28T00:00:00Z", "invalidated_by": None,
        "plan_id": stage["audit_plan_id"], "audit_plan_path": stage["audit_plan_path"],
        "audit_plan_sha256": stage["audit_plan_sha256"],
        "obligation_id": obligation["obligation_id"],
        **{field: plan[field] for field in (
            "task_id", "batch_id", "opening_transition_receipt", "upstream_revision_id",
            "active_standards_sha256", "selected_profile_manifest",
            "profile_snapshot_sha256", "profile_contract_fingerprint")},
        "fingerprint_binding": obligation["fingerprint_binding"],
        "merged_snapshot_sha256": SHA_F, "artifact_fingerprint": SHA_F,
        "dependency_fingerprint": SHA_C, "contract_fingerprint": SHA_E}
