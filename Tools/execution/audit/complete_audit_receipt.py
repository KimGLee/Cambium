#!/usr/bin/env python3
"""Complete one AuditPlan obligation into a full AuditReceipt.

The caller may select only the plan obligation and producer evidence. Every
dimension, predicate, scope, fingerprint, and authority binding is derived
from the current plan and evidence; none is accepted as a free-form argument.
"""

import os
import sys

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.audit_producer_chain as audit_producer_chain
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.audit.audit_receipt_finalizer as audit_receipt_finalizer
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.platform.common.kblib as kblib
import Tools.knowledge.rendering.rendering_verification_contract as rendering_verification_contract
import Tools.knowledge.rendering.profile_rendering_evidence_contract as profile_rendering
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.audit.substantive_review_contract as substantive_review_contract
from Tools.platform.common import reporting


TOOL = "complete_audit_receipt"
TOOL_VERSION = "1.0.0"
CHECK = "audit_dimension"
DEFAULT_RECEIPTS = runtime_paths.AUDIT_RECEIPT_REGISTER_PATH


def _load_current_plan(root, relative, result, item):
    """Resolve one requested pre-merge plan without producer semantics."""
    absolute = audit_producer_runtime.managed_plan_path(
        root, relative, must_exist=True)
    resolved = audit_evidence_runtime.resolve_stage_plan(
        result, item, "pre-merge", required_state="open",
        plan_path=relative)
    plan = resolved["plan"]
    digest = resolved["audit_plan_sha256"]
    if digest != kblib.sha256_file(absolute):
        raise audit_producer_runtime.AuditProducerError(
            "resolved AuditPlan digest differs from stored bytes")
    frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
    return absolute, plan, digest, frozen


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
    audit_producer_runtime.validate_obligation_attempt_binding(
        evidence, plan, plan_sha256, obligation)
    try:
        chain = audit_producer_chain.require_precursor_record(
            evidence, obligation, root=root,
            evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"))
    except audit_producer_chain.AuditProducerChainError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc
    expected = {
        "check": obligation["producer_check"],
        "invalidated_by": None,
    }
    mismatches = [field for field, value in expected.items()
                  if evidence.get(field) != value]
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "producer evidence differs from AuditPlan in: %s" %
            ", ".join(mismatches))
    if evidence.get("result") != "pass":
        raise audit_producer_runtime.AuditProducerError(
            "only a terminal passing producer attempt may be completed into "
            "the current AuditReceipt")
    for field in (
            "artifact_fingerprint", "dependency_fingerprint",
            "contract_fingerprint"):
        value = evidence.get(field)
        if not audit_plan_contract.is_sha256(value):
            mismatches.append(field)
    if chain["execution_route"] == "substantive-review":
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
    elif chain["execution_route"] == "profile-rendering":
        try:
            profile_rendering.validate_record_for_obligation(
                evidence, plan, plan_sha256, obligation, root=root,
                evaluation=(result.get("_profile_authorized_view") or {}).get("_evaluation"))
        except (OSError, TypeError, UnicodeError, ValueError, RuntimeError) as exc:
            mismatches.append("Profile rendering evidence: %s" % exc)
    elif chain["execution_route"] == "rendering-verification":
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
    elif chain["execution_route"] == "deterministic-audit-precursor":
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
    else:
        mismatches.append("unsupported registered producer chain")
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "producer evidence cannot discharge obligation: %s" %
            ", ".join(sorted(set(mismatches))))
    return evidence


def build_audit_receipt(*, plan, plan_sha256, obligation, evidence, seq=1):
    """Derive a full receipt without accepting semantic fields from caller."""
    seed = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, obligation["target"],
        "pass",
        "completed AuditPlan obligation %s from producer evidence %s" %
        (obligation["obligation_id"], evidence["receipt_id"]), seq,
        receipt_type_id=audit_receipt_contract.RECEIPT_TYPE_ID)
    return audit_receipt_finalizer.finalize_audit_receipt_record(
        receipt_id=seed["receipt_id"],
        scope=(evidence.get("scope") or []) + [obligation["target"]],
        plan=plan,
        plan_sha256=plan_sha256,
        obligation=obligation,
        evidence=evidence,
    )

def _validate_audit_receipt_attempt_stable(record, plan, plan_sha256,
                                           obligation, root):
    audit_receipt_contract.validate_audit_receipt(
        record, audit_receipt_contract.load_contract(root))
    audit_producer_runtime.validate_obligation_attempt_binding(
        record, plan, plan_sha256, obligation)
    if (record.get("result") != "passed" or
            record.get("fingerprint_binding") != "evidence-time" or
            record.get("reused_receipt_id") is not None or
            record.get("reuse_reason") is not None):
        raise ValueError(
            "AuditReceipt completion attempt is not new passing evidence")
    return record


def _validate_audit_receipt_attempt_current(
        record, root, result, plan, plan_sha256, obligation, frozen):
    _validate_audit_receipt_attempt_stable(
        record, plan, plan_sha256, obligation, root)
    evidence = _producer_evidence(
        root, result, record["evidence_ref"], plan, plan_sha256,
        obligation, frozen)
    scope = sorted(set(
        (evidence.get("scope") or []) + [obligation["target"]]))
    expected = {
        "scope": scope,
        "artifact_fingerprint": evidence["artifact_fingerprint"],
        "dependency_fingerprint": evidence["dependency_fingerprint"],
        "contract_fingerprint": evidence["contract_fingerprint"],
        "verifier": evidence["tool"],
        "method": "%s@%s/%s" % (
            evidence["tool"], evidence["tool_version"], evidence["check"]),
        "checked_at": evidence["checked_at"],
    }
    mismatches = [field for field, value in expected.items()
                  if record.get(field) != value]
    if mismatches:
        raise ValueError(
            "AuditReceipt attempt differs from current producer evidence in: "
            "%s" % ", ".join(sorted(mismatches)))
    return record


def current_audit_receipt_attempt(result, plan, plan_sha256, obligation,
                                  frozen, root):
    """Return the sole completed receipt still bound to current evidence."""
    attempts = audit_producer_runtime.obligation_attempt_records(
        result, plan_id=plan["plan_id"],
        obligation_id=obligation["obligation_id"],
        record_kind="audit-receipt")
    try:
        return evidence_attempt_runtime.unique_current_attempt(
            attempts,
            validate_stable=lambda record:
                _validate_audit_receipt_attempt_stable(
                    record, plan, plan_sha256, obligation, root),
            validate_current=lambda record:
                _validate_audit_receipt_attempt_current(
                    record, root, result, plan, plan_sha256, obligation,
                    frozen),
            label="AuditPlan obligation %s AuditReceipt completion" %
                  obligation["obligation_id"])
    except evidence_attempt_runtime.EvidenceAttemptError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc


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
        item, _activation = audit_producer_runtime.open_batch(
            result, args.batch)
        _absolute, plan, plan_sha256, frozen = _load_current_plan(
            root, args.plan, result, item)
        obligation = _obligation(plan, args.obligation_id)
        evidence = _producer_evidence(
            root, result, args.evidence_receipt, plan, plan_sha256,
            obligation, frozen)
        receipt_absolute = audit_producer_runtime.managed_receipt_path(
            root, args.receipts)
        existing = current_audit_receipt_attempt(
            result, plan, plan_sha256, obligation, frozen, root)
        if existing is not None:
            if existing.get("evidence_ref") != evidence["receipt_id"]:
                raise audit_producer_runtime.AuditProducerError(
                    "AuditReceipt obligation already has current evidence: %s"
                    % existing["receipt_id"])
            receipt = existing
        else:
            receipt = build_audit_receipt(
                plan=plan, plan_sha256=plan_sha256,
                obligation=obligation, evidence=evidence)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        reporting.write_canonical_json(
            {"applied": False, "errors": [str(exc)], "status": "invalid"})
        return 1

    if existing is not None:
        reporting.write_canonical_json({
            "applied": args.apply,
            "errors": [],
            "status": "already-present",
            "receipt_id": receipt["receipt_id"],
            "receipt_path": args.receipts,
            "result": receipt["result"],
        })
        return 0

    if not args.apply:
        reporting.write_canonical_json({
            "applied": False,
            "errors": [],
            "status": "planned",
            "receipt_id": receipt["receipt_id"],
            "receipt_path": args.receipts,
            "result": receipt["result"],
        })
        return 0

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
                locked_item, _locked_activation = \
                    audit_producer_runtime.open_batch(locked, args.batch)
                (_locked_absolute, locked_plan, locked_plan_sha256,
                 _locked_frozen) = _load_current_plan(
                     root, args.plan, locked, locked_item)
                if (locked_plan != plan or
                        locked_plan_sha256 != plan_sha256):
                    raise audit_producer_runtime.AuditProducerError(
                        "resolved AuditPlan changed before evidence publication")
                audit_producer_runtime.require_pages_current(
                    root, frozen, "before AuditReceipt publication")
                current_evidence = _producer_evidence(
                    root, locked, args.evidence_receipt, plan,
                    plan_sha256, obligation, frozen)
                if current_evidence != evidence:
                    raise audit_producer_runtime.AuditProducerError(
                        "producer evidence changed before AuditReceipt "
                        "publication")
                if current_audit_receipt_attempt(
                        locked, plan, plan_sha256, obligation, frozen,
                        root) is not None:
                    raise audit_producer_runtime.AuditProducerError(
                        "AuditReceipt evidence appeared before publication")
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
        reporting.write_canonical_json({
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
        reporting.write_canonical_json({
            "applied": True,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    reporting.write_canonical_json({
        "applied": True,
        "errors": [],
        "status": "recorded",
        "receipt_id": receipt["receipt_id"],
        "receipt_path": args.receipts,
        "result": receipt["result"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
