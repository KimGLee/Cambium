#!/usr/bin/env python3
"""Complete one AuditPlan obligation into a full AuditReceipt.

The caller may select only the plan obligation and producer evidence. Every
dimension, predicate, scope, fingerprint, and authority binding is derived
from the current plan and evidence; none is accepted as a free-form argument.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_plan_contract
import audit_producer_runtime
import audit_receipt_contract
import changed_scope_evidence_contract
import kblib
import prepare_audit_plan
import record_substantive_review
import rendering_verification_contract
import runtime_paths
import substantive_review_contract


TOOL = "complete_audit_receipt"
TOOL_VERSION = "1.0.0"
CHECK = "audit_dimension"
DEFAULT_RECEIPTS = runtime_paths.AUDIT_RECEIPT_REGISTER_PATH


def _obligation(plan, obligation_id):
    matches = [row for row in plan.get("obligations") or []
               if isinstance(row, dict) and
               row.get("obligation_id") == obligation_id]
    if len(matches) != 1:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan must contain exactly one obligation %s" % obligation_id)
    row = matches[0]
    if row.get("status") != "required":
        raise audit_producer_runtime.AuditProducerError(
            "only a required obligation can be completed from new evidence")
    return row


def _producer_evidence(root, result, receipt_id, plan, plan_sha256,
                       obligation, frozen=None):
    if (obligation.get("evidence_kind") != "audit-receipt" or
            obligation.get("evidence_role") != "emits" or
            obligation.get("dimension") is None):
        raise audit_producer_runtime.AuditProducerError(
            "only a dimension-specific AuditReceipt obligation may use the "
            "AuditReceipt completion producer")
    evidence = audit_producer_runtime.receipt_by_id(result, receipt_id)
    if not isinstance(evidence, dict):
        raise audit_producer_runtime.AuditProducerError(
            "producer evidence %s is not current" % receipt_id)
    expected = {
        "check": obligation["producer_check"],
        "target": obligation["target"],
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt":
            plan["opening_transition_receipt"],
        "standards_version": plan["standards_version"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "fingerprint_binding": "evidence-time",
        "invalidated_by": None,
    }
    mismatches = [field for field, value in expected.items()
                  if evidence.get(field) != value]
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "producer evidence differs from AuditPlan in: %s" %
            ", ".join(mismatches))
    if evidence.get("result") not in ("pass", "fail"):
        raise audit_producer_runtime.AuditProducerError(
            "producer evidence result must be pass or fail")
    for field in (
            "artifact_fingerprint", "dependency_fingerprint",
            "contract_fingerprint"):
        value = evidence.get(field)
        if not audit_plan_contract.is_sha256(value):
            mismatches.append(field)
    if obligation["producer_check"] == "substantive_review":
        substantive_review_contract.validate_review_receipt(
            evidence, substantive_review_contract.load_contract(root))
        target_pages = [page for page in (frozen or ())
                        if page.path == obligation["target"]]
        if len(target_pages) != 1 or \
                evidence.get("artifact_fingerprint") != \
                audit_producer_runtime.page_artifact_fingerprint(
                    target_pages[0]):
            mismatches.append("artifact_fingerprint")
        if evidence["sources_sha256"] != \
                evidence.get("dependency_fingerprint"):
            mismatches.append("dependency_fingerprint")
        if evidence.get("contract_fingerprint") != \
                audit_producer_runtime.obligation_contract_fingerprint(
                    plan, obligation):
            mismatches.append("contract_fingerprint")
    elif obligation["producer_check"] == \
            "changed_scope_rendering_escalation_record":
        try:
            if not frozen:
                raise ValueError(
                    "rendering-verification requires the frozen manifest")
            contract = rendering_verification_contract.load_contract(root)
            rendering_verification_contract.validate_record_for_obligation(
                evidence, plan, plan_sha256, obligation, contract)
            expected_scope = sorted(page.path for page in frozen)
            if evidence.get("scope") != expected_scope:
                mismatches.append("scope")
            if evidence.get("artifact_fingerprint") != \
                    audit_producer_runtime.page_set_artifact_fingerprint(
                        frozen):
                mismatches.append("artifact_fingerprint")
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            mismatches.append("rendering-verification contract: %s" % exc)
    elif changed_scope_evidence_contract.pure_check_owner(
            obligation.get("owner_rule_id"),
            obligation.get("producer_check")) is not None:
        try:
            current_artifact = None
            target_pages = [page for page in (frozen or ())
                            if page.path == obligation.get("target")]
            if target_pages:
                if len(target_pages) != 1:
                    raise ValueError(
                        "changed-scope target repeats in frozen manifest")
                current_artifact = \
                    audit_producer_runtime.page_artifact_fingerprint(
                        target_pages[0])
            changed_scope_evidence_contract.validate_record_for_plan(
                evidence, plan, plan_sha256, obligation, root=root,
                artifact_fingerprint=current_artifact)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            mismatches.append("changed-scope evidence contract: %s" % exc)
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "producer evidence cannot discharge obligation: %s" %
            ", ".join(sorted(set(mismatches))))
    return evidence


def build_audit_receipt(*, plan, plan_sha256, obligation, evidence, seq=1):
    """Derive a full receipt without accepting semantic fields from caller."""
    seed = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, obligation["target"],
        "pass" if evidence["result"] == "pass" else "fail",
        "completed AuditPlan obligation %s from producer evidence %s" %
        (obligation["obligation_id"], evidence["receipt_id"]), seq)
    record = {
        "schema_version": 1,
        "record_kind": "audit-receipt",
        "receipt_id": seed["receipt_id"],
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt":
            plan["opening_transition_receipt"],
        "standards_version": plan["standards_version"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "due_stage": obligation["due_stage"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        "dimension": obligation["dimension"],
        "scope": sorted(set(
            (evidence.get("scope") or []) + [obligation["target"]])),
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "artifact_fingerprint": evidence["artifact_fingerprint"],
        "dependency_fingerprint": evidence["dependency_fingerprint"],
        "contract_fingerprint": evidence["contract_fingerprint"],
        "verifier": evidence["tool"],
        "method": "%s@%s/%s" % (
            evidence["tool"], evidence["tool_version"], evidence["check"]),
        "evidence_ref": evidence["receipt_id"],
        "checked_at": evidence["checked_at"],
        "review_due": obligation["review_due"],
        "result": "passed" if evidence["result"] == "pass" else "failed",
        "invalidated_by": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    }
    audit_receipt_contract.validate_audit_receipt(record)
    return record


def _emit(payload):
    sys.stdout.write(
        kblib.canonical_json_bytes(payload).decode("utf-8") + "\n")


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Complete one plan obligation into a full AuditReceipt")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--obligation-id", required=True)
    parser.add_argument("--evidence-receipt", required=True)
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        root, result, authority = audit_producer_runtime.admitted_runtime(
            args.root)
        item, activation = audit_producer_runtime.open_batch(
            result, args.batch)
        _absolute, plan, plan_sha256, frozen = \
            record_substantive_review.load_current_plan(
                root, args.plan, result, item, activation)
        obligation = _obligation(plan, args.obligation_id)
        evidence = _producer_evidence(
            root, result, args.evidence_receipt, plan, plan_sha256,
            obligation, frozen)
        receipt = build_audit_receipt(
            plan=plan, plan_sha256=plan_sha256,
            obligation=obligation, evidence=evidence)
        receipt_absolute = audit_producer_runtime.managed_receipt_path(
            root, args.receipts)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        _emit({"applied": False, "errors": [str(exc)], "status": "invalid"})
        return 1

    if not args.apply:
        _emit({
            "applied": False,
            "errors": [],
            "status": "planned",
            "receipt_id": receipt["receipt_id"],
            "receipt_path": args.receipts,
            "result": receipt["result"],
        })
        return 0 if receipt["result"] == "passed" else 1

    operation = audit_producer_runtime.runtime_lock_metadata(
        TOOL, "complete-audit-receipt", result, authority,
        batch_id=args.batch, plan_id=plan["plan_id"],
        obligation_id=obligation["obligation_id"],
        receipt_id=receipt["receipt_id"])
    try:
        with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = audit_producer_runtime.require_runtime_current(
                    root, authority, "before AuditReceipt publication")
                locked_item, locked_activation = \
                    audit_producer_runtime.open_batch(locked, args.batch)
                prepare_audit_plan.require_plan_current(
                    plan, root, locked, locked_item, locked_activation,
                    frozen=frozen)
                audit_producer_runtime.require_pages_current(
                    root, frozen, "before AuditReceipt publication")
                current_evidence = _producer_evidence(
                    root, locked, args.evidence_receipt, plan,
                    plan_sha256, obligation, frozen)
                if current_evidence != evidence:
                    raise audit_producer_runtime.AuditProducerError(
                        "producer evidence changed before AuditReceipt "
                        "publication")
                before = kblib.receipt_append_observation(
                    receipt_absolute, [receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_absolute, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise audit_producer_runtime.AuditProducerError(
                    "AuditReceipt publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        _emit({
            "applied": False,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    try:
        persisted = [row for row in
                     audit_producer_runtime.read_receipt_records(
                         receipt_absolute)
                     if row.get("receipt_id") == receipt["receipt_id"]]
        if len(persisted) != 1 or persisted[0] != receipt:
            raise audit_producer_runtime.AuditProducerError(
                "published AuditReceipt did not read back exactly")
        audit_receipt_contract.validate_audit_receipt(
            persisted[0], audit_receipt_contract.load_contract(root))
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        _emit({
            "applied": True,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    _emit({
        "applied": True,
        "errors": [],
        "status": "recorded",
        "receipt_id": receipt["receipt_id"],
        "receipt_path": args.receipts,
        "result": receipt["result"],
    })
    return 0 if receipt["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
