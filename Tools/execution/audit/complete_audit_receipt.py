#!/usr/bin/env python3
"""Complete AuditPlan obligations into their separate full AuditReceipts.

The caller may select only the plan obligation and producer evidence. Every
dimension, predicate, scope, fingerprint, and authority binding is derived
from the current plan and evidence; none is accepted as a free-form argument.
"""

import os
import sys

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.audit.audit_receipt_finalizer as audit_receipt_finalizer
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
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


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Complete one plan obligation into a full AuditReceipt")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--obligation-id", required=True, action="append")
    parser.add_argument("--evidence-receipt", required=True, action="append",
                        help="producer evidence, in the same order as repeated obligation IDs")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    publication = kblib.ReceiptPublication()

    try:
        root, result, authority = audit_producer_runtime.admitted_runtime(
            args.root)
        item, _activation = audit_producer_runtime.open_batch(
            result, args.batch)
        _absolute, plan, plan_sha256, frozen = _load_current_plan(
            root, args.plan, result, item)
        result = audit_evidence_runtime.evidence_evaluation(result)
        if len(args.obligation_id) != len(args.evidence_receipt) or len(set(args.obligation_id)) != len(args.obligation_id):
            raise audit_producer_runtime.AuditProducerError("completion requires unique paired obligation/evidence IDs")
        receipt_absolute = audit_producer_runtime.managed_receipt_path(
            root, args.receipts)
        completions = []
        for index, (identity, evidence_id) in enumerate(zip(args.obligation_id, args.evidence_receipt), 1):
            obligation = _obligation(plan, identity)
            evidence, existing = audit_evidence_runtime.require_completion_evidence(
                result, item, plan, plan_sha256, obligation, evidence_id)
            receipt = existing if existing is not None else build_audit_receipt(
                plan=plan, plan_sha256=plan_sha256, obligation=obligation, evidence=evidence, seq=index)
            if existing is None:
                proposed = audit_evidence_runtime.obligation_evidence_resolution(
                    result, item, plan, plan_sha256, obligation,
                    proposed_record=receipt)
                if proposed["status"] != "satisfied":
                    raise audit_producer_runtime.AuditProducerError(
                        "proposed AuditReceipt does not discharge its obligation: %s" %
                        proposed.get("reason"))
            completions.append((obligation, evidence, receipt, existing is None))
        receipts = [row[2] for row in completions]
        pending = [row for row in completions if row[3]]
        new_receipts = [row[2] for row in pending]
        receipt = receipts[0]
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        reporting.write_canonical_json(reporting.publication_result(
            publication, status="invalid", errors=[str(exc)]))
        return 1

    if not pending:
        publication.confirmed = True
        reporting.write_canonical_json(reporting.publication_result(
            publication, status="already-present", reused=True,
            receipt_id=receipt["receipt_id"], receipt_path=args.receipts,
            result=receipt["result"],
            receipt_ids=[row["receipt_id"] for row in receipts]))
        return 0

    if not args.apply:
        reporting.write_canonical_json(reporting.publication_result(
            publication, status="planned", receipt_id=receipt["receipt_id"],
            receipt_path=args.receipts, result=receipt["result"],
            receipt_ids=[row["receipt_id"] for row in receipts]))
        return 0

    operation = audit_producer_runtime.runtime_lock_metadata(
        TOOL, "complete-audit-receipt", result, authority,
        batch_id=args.batch, plan_id=plan["plan_id"],
        obligation_id=args.obligation_id[0],
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
                locked = audit_evidence_runtime.evidence_evaluation(locked)
                for obligation, evidence, candidate, _ in pending:
                    current_evidence, existing = audit_evidence_runtime.require_completion_evidence(
                        locked, locked_item, plan, plan_sha256, obligation,
                        evidence["receipt_id"])
                    if current_evidence != evidence:
                        raise audit_producer_runtime.AuditProducerError("producer evidence changed before AuditReceipt publication")
                    if existing is not None:
                        raise audit_producer_runtime.AuditProducerError("AuditReceipt evidence appeared before publication")
                    proposed = audit_evidence_runtime.obligation_evidence_resolution(
                        locked, locked_item, plan, plan_sha256, obligation,
                        proposed_record=candidate)
                    if proposed["status"] != "satisfied":
                        raise audit_producer_runtime.AuditProducerError(
                            "proposed AuditReceipt does not discharge its obligation: %s" %
                            proposed.get("reason"))
                before = kblib.receipt_append_observation(
                    receipt_absolute, new_receipts)
            outcome, error, _ = publication.append(
                receipt_absolute, new_receipts, before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise audit_producer_runtime.AuditProducerError(
                    "AuditReceipt publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        reporting.write_canonical_json(reporting.publication_result(
            publication, status="uncertain", errors=[str(exc)],
            receipt_id=receipt["receipt_id"]))
        return 1

    try:
        ids = {row["receipt_id"] for row in new_receipts}
        persisted = [row for row in
                     audit_producer_runtime.read_receipt_records(
                         receipt_absolute, observation=publication.observation)
                     if row.get("receipt_id") in ids]
        if persisted != new_receipts:
            raise audit_producer_runtime.AuditProducerError(
                "published AuditReceipt did not read back exactly")
        contract = audit_receipt_contract.load_contract(root)
        for row in persisted:
            audit_receipt_contract.validate_audit_receipt(row, contract)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        reporting.write_canonical_json(reporting.publication_result(
            publication, status="uncertain", errors=[str(exc)],
            receipt_id=receipt["receipt_id"]))
        return 1

    publication.confirmed = True
    reporting.write_canonical_json(reporting.publication_result(
        publication, status="recorded",
        receipt_id=receipt["receipt_id"],
        receipt_path=args.receipts,
        result=receipt["result"],
        receipt_ids=[row["receipt_id"] for row in receipts]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
