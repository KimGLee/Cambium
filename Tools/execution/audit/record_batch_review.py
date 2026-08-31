#!/usr/bin/env python3
"""Record the current Batch Review wrapper without changing runtime state.

The producer derives every evidence set from the admitted runtime: page
evidence comes from the exact managed Delta, Profile judgments come from the
current activation, and full AuditReceipts come from the current AuditPlan.
Callers provide only the batch, the integrator role, and the integrator's
bounded statement. Queue, page, Delta, and AuditPlan bytes are read-only.
"""

import copy
import os
import sys

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_reconciliation_contract as audit_reconciliation_contract
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.batch_review_receipt_contract as batch_review_receipt_contract
import Tools.execution.context_delivery.card_activation as card_activation
import Tools.execution.task_runtime.queue_runtime.delta as queue_delta
import Tools.execution.task_runtime.queue_runtime.receipts as receipt_catalogs
import Tools.execution.task_runtime.queue_runtime.review as queue_review
import Tools.platform.common.kblib as kblib
import Tools.execution.evidence.manual_attestation as manual_attestation
import Tools.governance.profile.profile_batch_judgment_contract as profile_batch_judgment_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting


CLI_TOOL = "record_batch_review"
RECEIPT_TOOL = batch_review_receipt_contract.PRODUCER_TOOL
TOOL_VERSION = batch_review_receipt_contract.PRODUCER_TOOL_VERSION
CHECK = batch_review_receipt_contract.PRODUCER_CHECK
GATE_ID = batch_review_receipt_contract.GATE_ID
DEFAULT_RECEIPTS = runtime_paths.GATE_ATTESTATION_RECEIPT_PATH


def _managed_candidate_delta(root, result, item):
    """Return the shared exact candidate read-back used by all consumers."""
    return queue_delta.current_candidate_binding(root, result, item)


def _current_judgment_receipts(result, item, audit_binding):
    """Delegate the complete live-current judgment set to its sole resolver."""
    view = result.get("_profile_authorized_view") or {}
    contract = view.get("_contract")
    if contract is None or not getattr(contract, "authorized", False):
        raise ValueError(
            "batch review requires one authorized typed Profile contract")
    plan = profile_batch_judgment_contract.load_bound_plan(
        result["root"], audit_binding["audit_plan_path"],
        audit_binding["audit_plan_id"],
        audit_binding["audit_plan_sha256"])
    return list(profile_batch_judgment_contract.current_judgment_receipts(
        result["root"], plan, audit_binding["audit_plan_sha256"], contract,
        item, view, receipt_catalogs.current_receipt_catalog(result)))


def _audit_plan_evidence(result, item):
    """Resolve the current AuditPlan and exact heterogeneous evidence set.

    The shared runtime resolver composes the Kernel-contract loaders with the
    current receipt catalog and returns only their verified binding.
    """
    binding = audit_evidence_runtime.batch_review_evidence(result, item)
    required = (
        "audit_plan_id", "audit_plan_path", "audit_plan_sha256",
        "audit_evidence_bindings", "audit_evidence_set_sha256",
        *audit_reconciliation_contract.projection_fields(),
    )
    if (not isinstance(binding, dict) or
            any(field not in binding for field in required)):
        raise ValueError("AuditPlan batch-review binding is incomplete")
    return {field: binding[field] for field in required}


def build_batch_review_receipt(result, item, delta_binding, audit_binding,
                               actor_role, statement, seq=1):
    """Build one wrapper entirely from already admitted, current evidence."""
    if item.get("state") != "open":
        raise ValueError(
            "batch %s must be open, found %r" %
            (item.get("id"), item.get("state")))
    if actor_role != "integrator":
        raise ValueError(
            "batch-review manual attestation requires actor role 'integrator'")
    statement = manual_attestation.require_statement(
        statement, "batch-review manual attestation")
    if not isinstance(delta_binding, dict) or not isinstance(
            audit_binding, dict):
        raise TypeError("Delta and AuditPlan bindings must be mappings")

    activation_id = item.get("activation_receipt")
    catalog = receipt_catalogs.current_receipt_catalog(result)
    activation_entry = catalog.get(activation_id)
    activation = activation_entry[1] if isinstance(
        activation_entry, tuple) else activation_entry
    if not isinstance(activation, dict):
        raise ValueError("batch has no current activation receipt")

    judgments = _current_judgment_receipts(result, item, audit_binding)
    actual = [{
        "target": row.get("target"),
        "judgment_item_id": row.get("judgment_item_id"),
        "receipt_id": row.get("receipt_id"),
    } for row in judgments]

    receipt = kblib.make_receipt(
        RECEIPT_TOOL, TOOL_VERSION, CHECK, item.get("id"), "pass",
        statement, seq,
        receipt_type_id=batch_review_receipt_contract.RECEIPT_TYPE_ID,
        root=result["root"])
    receipt.update({
        "gate_id": GATE_ID,
        "batch_id": item.get("id"),
        "actor_role": actor_role,
        "attestation_statement": statement,
        "opening_transition_receipt": activation_id,
        "delta_path": delta_binding["path"],
        "delta_sha256": delta_binding["sha256"],
        "delta_page_receipt_ids": list(
            delta_binding["page_receipt_ids"]),
        "audit_plan_id": audit_binding["audit_plan_id"],
        "audit_plan_path": audit_binding["audit_plan_path"],
        "audit_plan_sha256": audit_binding["audit_plan_sha256"],
        "audit_evidence_bindings": list(
            audit_binding["audit_evidence_bindings"]),
        "audit_evidence_set_sha256":
            audit_binding["audit_evidence_set_sha256"],
        **copy.deepcopy({
            field: audit_binding[field]
            for field in
            audit_reconciliation_contract.projection_fields()
        }),
    })
    if activation.get(
            "activation_protocol") != card_activation.ACTIVATION_PROTOCOL:
        raise ValueError("batch activation does not use the current protocol")
    requirement_sha = activation.get("review_requirement_set_sha256")
    receipt.update({
        "review_requirement_set_sha256": requirement_sha,
        "judgment_receipt_ids": sorted(
            row["receipt_id"] for row in actual),
        "judgment_record_set_sha256":
            queue_review.judgment_record_set_sha256(actual),
    })
    receipt_errors = batch_review_receipt_contract.current_receipt_errors(
        receipt)
    if receipt_errors:
        raise ValueError("invalid Batch Review wrapper shape: %s" %
                         "; ".join(receipt_errors))
    return receipt


def validate_batch_review_receipt(result, item, receipt, *,
                                  delta_binding=None,
                                  audit_binding=None):
    """Run the exact transition consumers before the wrapper is published."""
    catalog = copy.copy(receipt_catalogs.current_receipt_catalog(result))
    catalog[receipt["receipt_id"]] = ("<pending-write>", receipt)
    errors = queue_review.batch_review_receipt_errors(
        catalog, receipt["receipt_id"], item_id=item.get("id"),
        task_id=(result.get("queue") or {}).get("task_id"),
        delta_page_receipt_ids=(
            delta_binding.get("page_receipt_ids")
            if isinstance(delta_binding, dict) else
            receipt.get("delta_page_receipt_ids")),
    )
    errors.extend(queue_review.batch_review_judgment_errors(
        result, item, receipt))
    reconciliation_fields = audit_reconciliation_contract.projection_fields()
    errors.extend(audit_evidence_runtime.wrapper_binding_errors(
        result, item, receipt))
    if delta_binding is not None:
        for field, expected in (
                ("delta_path", delta_binding.get("path")),
                ("delta_sha256", delta_binding.get("sha256"))):
            if receipt.get(field) != expected:
                errors.append(
                    "batch-review wrapper %s does not match the canonical "
                    "Delta" % field)
    if audit_binding is not None:
        for field in (
                "audit_plan_id", "audit_plan_path", "audit_plan_sha256",
                "audit_evidence_bindings", "audit_evidence_set_sha256",
                *reconciliation_fields):
            if receipt.get(field) != audit_binding.get(field):
                errors.append(
                    "batch-review wrapper %s does not match current AuditPlan "
                    "evidence" % field)
    if errors:
        raise ValueError("invalid batch-review wrapper: %s" %
                         "; ".join(errors))


def _build_context(root, batch_id, actor_role, statement):
    root, result, authority = audit_producer_runtime.admitted_runtime(root)
    item, _activation = audit_producer_runtime.open_batch(result, batch_id)
    delta_binding = _managed_candidate_delta(root, result, item)
    audit_binding = _audit_plan_evidence(result, item)
    receipt = build_batch_review_receipt(
        result, item, delta_binding, audit_binding, actor_role, statement)
    validate_batch_review_receipt(
        result, item, receipt, delta_binding=delta_binding,
        audit_binding=audit_binding)
    return (root, result, authority, item, delta_binding, audit_binding,
            receipt)


def _output(receipt, as_json):
    if as_json:
        reporting.write_canonical_json([receipt])
    else:
        print("[PASS] batch-review wrapper recorded: %s" %
              receipt["receipt_id"])


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record one current, evidence-complete Batch Review wrapper")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True,
                        help="exact current open Queue batch ID")
    parser.add_argument("--actor-role", required=True,
                        help="declared recording role; must be integrator")
    parser.add_argument("--statement", required=True,
                        help="bounded integrator Batch Review statement")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--apply", action="store_true",
                        help="append the wrapper; omit for a dry run")
    parser.add_argument("--json", action="store_true",
                        help="write the applied wrapper as one JSON array")
    args = parser.parse_args(argv)

    try:
        (root, result, authority, item, delta_binding, audit_binding,
         receipt) = _build_context(
            args.root, args.batch, args.actor_role, args.statement)
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    if not args.apply:
        if not args.json:
            print("[PLAN] batch %s wrapper binds %d Delta receipt(s), "
                  "%d judgment receipt(s), and %d planned evidence "
                  "object(s)" %
                  (item.get("id"),
                   len(receipt["delta_page_receipt_ids"]),
                   len(receipt.get("judgment_receipt_ids") or []),
                   len(receipt["audit_evidence_bindings"])))
            print("dry run; add --apply to publish the wrapper")
        return 0

    operation = audit_producer_runtime.runtime_lock_metadata(
        CLI_TOOL, "record-batch-review", result, authority,
        batch_id=item.get("id"), receipt_id=receipt["receipt_id"],
        receipt_path=args.receipts,
        delta_path=delta_binding["path"],
        delta_sha256=delta_binding["sha256"],
        audit_plan_id=audit_binding["audit_plan_id"],
        audit_plan_sha256=audit_binding["audit_plan_sha256"],
    )
    try:
        def rebuild(locked):
            locked_item, _activation = audit_producer_runtime.open_batch(
                locked, args.batch)
            locked_delta = _managed_candidate_delta(root, locked, locked_item)
            locked_audit = _audit_plan_evidence(locked, locked_item)
            return build_batch_review_receipt(
                locked, locked_item, locked_delta, locked_audit,
                args.actor_role, args.statement)

        def validate(locked, candidate):
            locked_item, _activation = audit_producer_runtime.open_batch(
                locked, args.batch)
            locked_delta = _managed_candidate_delta(
                root, locked, locked_item)
            locked_audit = _audit_plan_evidence(locked, locked_item)
            validate_batch_review_receipt(
                locked, locked_item, candidate,
                delta_binding=locked_delta,
                audit_binding=locked_audit)

        receipt = manual_attestation.publish_receipt(
            root, receipt_path, receipt, authority=authority,
            operation=operation, rebuild=rebuild, validate=validate,
            publication_label="batch-review wrapper publication")
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.RuntimeStateLockedError, kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    _output(receipt, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
