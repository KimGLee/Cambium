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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_producer_runtime
import card_activation
import check_queue
import kblib
import manual_attestation
import profile_batch_judgment_contract
import runtime_paths


CLI_TOOL = "record_batch_review"
RECEIPT_TOOL = check_queue.MANUAL_ATTESTATION_TOOL
TOOL_VERSION = check_queue.MANUAL_ATTESTATION_TOOL_VERSION
CHECK = check_queue.BATCH_REVIEW_CHECK
GATE_ID = check_queue.BATCH_REVIEW_GATE_ID
DEFAULT_RECEIPTS = runtime_paths.GATE_ATTESTATION_RECEIPT_PATH


def _managed_candidate_delta(root, result, item):
    """Return the exact structurally valid, settled managed Delta binding."""
    item_id = item.get("id")
    relative = runtime_paths.child_path(
        runtime_paths.DELTA_ROOT, "%s.yaml" % item_id)
    matches = [record for record in result.get("managed_deltas") or []
               if isinstance(record, dict) and
               record.get("path") == relative and
               record.get("batch") == item_id]
    if len(matches) != 1:
        raise ValueError(
            "open batch %s requires exactly one canonical Delta at %s" %
            (item_id, relative))
    record = matches[0]
    if record.get("handoff_status") != "candidate":
        details = record.get("handoff_errors") or []
        raise ValueError(
            "canonical Delta %s is not a complete candidate: %s" %
            (relative, "; ".join(details) if details else
             record.get("handoff_status")))
    path = kblib.managed_repository_path(
        root, relative, runtime_paths.DELTA_ROOT,
        suffixes=(".yaml",), must_exist=True)
    delta = kblib.load_yaml_file(path)
    if not isinstance(delta, dict) or delta.get("batch") != item_id:
        raise ValueError("canonical Delta does not bind batch %s" % item_id)
    receipt_ids = check_queue.delta_gate_receipt_ids(delta)
    sha256 = kblib.sha256_file(path)
    if record.get("sha256") != sha256:
        raise ValueError("canonical Delta changed after runtime admission")
    return {
        "path": relative,
        "sha256": sha256,
        "page_receipt_ids": receipt_ids,
    }


def _current_judgment_receipts(result, item):
    """Derive the complete current-attempt Profile judgment candidate set."""
    activation_id = item.get("activation_receipt")
    records = []
    for entry in check_queue.current_receipt_catalog(result).values():
        receipt = entry[1] if isinstance(entry, tuple) else entry
        if not isinstance(receipt, dict):
            continue
        if (receipt.get("tool") ==
                profile_batch_judgment_contract.PRODUCER_TOOL and
                receipt.get("check") ==
                profile_batch_judgment_contract.PRODUCER_CHECK and
                receipt.get("record_kind") ==
                profile_batch_judgment_contract.RECORD_KIND and
                receipt.get("result") == "pass" and
                receipt.get("invalidated_by") is None and
                receipt.get("batch_id") == item.get("id") and
                receipt.get("activation_receipt_id") == activation_id):
            records.append(receipt)
    return sorted(records, key=lambda row: row.get("receipt_id", ""))


def _audit_plan_evidence(result, item):
    """Resolve the current AuditPlan and exact heterogeneous evidence set.

    The runtime integration module is imported here so this producer never
    grows a second AuditPlan scanner or AuditReceipt validator. That resolver
    composes the two pure Kernel-contract loaders with the current receipt
    catalog and returns only their verified binding.
    """
    try:
        import audit_evidence_runtime
    except ImportError as exc:  # pragma: no cover - repository integration guard
        raise ValueError(
            "Audit evidence runtime consumer is unavailable") from exc
    binding = audit_evidence_runtime.batch_review_evidence(result, item)
    required = (
        "audit_plan_id", "audit_plan_path", "audit_plan_sha256",
        "audit_evidence_bindings", "audit_evidence_set_sha256",
        "audit_receipt_ids", "audit_receipt_set_sha256",
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
    catalog = check_queue.current_receipt_catalog(result)
    activation_entry = catalog.get(activation_id)
    activation = activation_entry[1] if isinstance(
        activation_entry, tuple) else activation_entry
    if not isinstance(activation, dict):
        raise ValueError("batch has no current activation receipt")

    judgments = _current_judgment_receipts(result, item)
    actual = [{
        "target": row.get("target"),
        "judgment_item_id": row.get("judgment_item_id"),
        "receipt_id": row.get("receipt_id"),
    } for row in judgments]

    receipt = kblib.make_receipt(
        RECEIPT_TOOL, TOOL_VERSION, CHECK, item.get("id"), "pass",
        statement, seq, root=result["root"])
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
        "audit_receipt_ids": list(audit_binding["audit_receipt_ids"]),
        "audit_receipt_set_sha256":
            audit_binding["audit_receipt_set_sha256"],
    })
    if activation.get(
            "activation_protocol") == card_activation.ACTIVATION_PROTOCOL:
        requirement_sha = activation.get("review_requirement_set_sha256")
        receipt.update({
            "review_requirement_set_sha256": requirement_sha,
            "judgment_receipt_ids": sorted(
                row["receipt_id"] for row in actual),
            "judgment_record_set_sha256":
                check_queue.judgment_record_set_sha256(actual),
        })
    return receipt


def validate_batch_review_receipt(result, item, receipt, *,
                                  delta_binding=None,
                                  audit_binding=None):
    """Run the exact transition consumers before the wrapper is published."""
    catalog = copy.copy(check_queue.current_receipt_catalog(result))
    catalog[receipt["receipt_id"]] = ("<pending-write>", receipt)
    errors = check_queue.batch_review_receipt_errors(
        catalog, receipt["receipt_id"], item_id=item.get("id"),
        task_id=(result.get("queue") or {}).get("task_id"),
        delta_page_receipt_ids=(
            delta_binding.get("page_receipt_ids")
            if isinstance(delta_binding, dict) else
            receipt.get("delta_page_receipt_ids")),
    )
    errors.extend(check_queue.batch_review_judgment_errors(
        result, item, receipt))
    try:
        import audit_evidence_runtime
        errors.extend(audit_evidence_runtime.wrapper_binding_errors(
            result, item, receipt))
    except ImportError as exc:  # pragma: no cover - integration guard
        errors.append("Audit evidence runtime consumer is unavailable: %s" % exc)
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
                "audit_receipt_ids", "audit_receipt_set_sha256"):
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
        sys.stdout.write(
            kblib.canonical_json_bytes([receipt]).decode("utf-8") + "\n")
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
                  "%d judgment receipt(s), %d planned evidence object(s), "
                  "and %d AuditReceipt(s)" %
                  (item.get("id"),
                   len(receipt["delta_page_receipt_ids"]),
                   len(receipt.get("judgment_receipt_ids") or []),
                   len(receipt["audit_evidence_bindings"]),
                   len(receipt["audit_receipt_ids"])))
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
