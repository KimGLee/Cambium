#!/usr/bin/env python3
"""Record manual evidence for one typed Profile Extension Gate.

The Profile contract, not command-line field names, supplies the Gate's
transition, field, completion enum, pass-authority role, producer capability,
receipt schema and Integrator consumer.  The receipt is bound to one exact
semantic page snapshot and to the complete selected-Profile authority view.
It changes no page or Ledger state; ``apply_metadata_transition.py`` is the
sole consumer that may turn this evidence into canonical owner state.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib
import metadata_gate_runtime
import runtime_paths


TOOL = "record_gate_attestation"
TOOL_VERSION = "1.0.0"
DEFAULT_RECEIPTS = runtime_paths.GATE_ATTESTATION_RECEIPT_PATH


def _require_context_current(context, phase, *, runtime=None):
    """Run the facade's authority CAS, then the Gate runtime's own.

    ``check_queue`` owns the runtime-authority compare-and-swap and the Gate
    runtime no longer reaches back for it, so the two halves are sequenced
    here instead.  The order is the one the single call had: a moved
    Profile-load or active-Standards view is reported as an authority change
    before any metadata-contract, manifest or target difference derived from
    it.
    """
    check_queue.require_runtime_authority_current(
        context.root, context.authority, phase)
    metadata_gate_runtime.require_context_current(
        context, phase, runtime=runtime)


def build_attestation_receipt(context, requested_value, actor_role,
                              statement, seq=1):
    """Build one manual receipt from an already authorized Gate context."""
    gate = context.gate
    if gate.producer_kind != "manual-attestation":
        raise ValueError(
            "Gate %s uses producer kind %s, not manual-attestation" %
            (gate.gate_id, gate.producer_kind))
    if actor_role != gate.pass_authority_role_id:
        raise ValueError(
            "actor role %r cannot pass Gate %s; expected %r" %
            (actor_role, gate.gate_id, gate.pass_authority_role_id))
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("manual Gate attestation requires a non-empty statement")
    bindings = metadata_gate_runtime.receipt_bindings(
        context, requested_value)
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, metadata_gate_runtime.GATE_CHECK,
        context.page_path, "pass", statement.strip(), seq,
        root=context.root)
    receipt.update({
        "gate_id": bindings["gate_id"],
        "transition_id": bindings["transition_id"],
        "judgment_item_id": bindings["judgment_item_id"],
        "property_field": bindings["property_field"],
        "requested_completion_value":
            bindings["requested_completion_value"],
        "pass_authority_role_id": bindings["pass_authority_role_id"],
        "actor_role": actor_role,
        "producer_kind": bindings["producer_kind"],
        "producer_capability": bindings["producer_capability"],
        "producer_reference": bindings["producer_reference"],
        "receipt_schema": bindings["receipt_schema"],
        "consumer_capability": bindings["consumer_capability"],
        "semantic_content_fingerprint":
            bindings["semantic_content_fingerprint"],
        "page_sha256": bindings["page_sha256"],
        "selected_profile_manifest":
            bindings["selected_profile_manifest"],
        "selected_profile_manifest_sha256":
            bindings["selected_profile_manifest_sha256"],
        "profile_snapshot_sha256": bindings["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            bindings["profile_contract_fingerprint"],
        "profile_load_inputs_sha256":
            bindings["profile_load_inputs_sha256"],
        "active_standards_sha256": bindings["active_standards_sha256"],
        "metadata_execution_contract_fingerprint":
            bindings["metadata_execution_contract_fingerprint"],
        "attestation_statement": statement.strip(),
    })
    # Validate the producer's own output through the same closed consumer
    # schema before any bytes enter the receipt catalog.
    metadata_gate_runtime.validate_gate_receipt(
        context, receipt, requested_value)
    return receipt


def _output(receipt, as_json):
    if as_json:
        sys.stdout.write(
            kblib.canonical_json_bytes([receipt]).decode("utf-8") + "\n")
    else:
        print("[PASS] manual Gate evidence recorded: %s" %
              receipt["receipt_id"])


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record snapshot-bound manual Extension Gate evidence")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--gate-id", required=True,
                        help="exact typed Profile Extension Gate ID")
    parser.add_argument("--page", required=True,
                        help="repository-relative Markdown target")
    parser.add_argument("--value", required=True,
                        help="requested registered completion value")
    parser.add_argument("--actor-role", required=True,
                        help="declared pass-authority Profile role ID")
    parser.add_argument("--statement", required=True,
                        help="bounded manual attestation statement")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--apply", action="store_true",
                        help="append the evidence; omit for a dry run")
    parser.add_argument("--json", action="store_true",
                        help="write the applied receipt as one JSON array")
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    try:
        runtime = check_queue.validate_runtime(root)
        metadata_gate_runtime.require_admitted_runtime(runtime)
        authority = check_queue.runtime_authority_context(runtime)
        context = metadata_gate_runtime.load_gate_context(
            root, args.gate_id, args.page, runtime=runtime,
            authority=authority)
        receipt = build_attestation_receipt(
            context, args.value, args.actor_role, args.statement)
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    if not args.apply:
        if args.json:
            # A dry run publishes no receipt, matching the other writers.
            return 0
        print("[PLAN] Gate %s permits %s=%s for %s" %
              (context.gate.gate_id, context.gate.field_id,
               args.value, context.page_path))
        print("dry run; add --apply to publish the bound attestation")
        return 0

    operation = {
        "tool": TOOL,
        "action": "record-profile-extension-gate-attestation",
        "gate_id": context.gate.gate_id,
        "transition_id": context.gate.transition_id,
        "target": context.page_path,
        "receipt_id": receipt["receipt_id"],
        "receipt_path": args.receipts,
        "before_coverage_sha256": context.runtime.get("coverage_sha256"),
        "planned_after_coverage_sha256":
            context.runtime.get("coverage_sha256"),
        "before_required_queue_sha256": context.runtime.get("queue_sha256"),
        "planned_after_required_queue_sha256":
            context.runtime.get("queue_sha256"),
        "before_progress_sha256": context.runtime.get("progress_sha256"),
        "planned_after_progress_sha256":
            context.runtime.get("progress_sha256"),
        "page_sha256": context.page_snapshot.sha256,
        "metadata_execution_contract_fingerprint":
            context.metadata_contract_fingerprint,
    }
    operation.update(check_queue.runtime_authority_lock_fields(
        context.authority))
    try:
        authority_kwargs = check_queue.runtime_authority_validation_kwargs(
            context.authority)
        with kblib.runtime_write_lock(
                root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if locked.get("errors"):
                    raise ValueError(
                        "runtime changed before evidence publication: %s" %
                        "; ".join(locked["errors"]))
                _require_context_current(
                    context, "manual Gate evidence publication", runtime=locked)
                before = kblib.receipt_append_observation(
                    receipt_path, [receipt])
            outcome, error, _observation = kblib.write_receipts_observed(
                receipt_path, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise ValueError(
                    "manual Gate receipt publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    _output(receipt, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
