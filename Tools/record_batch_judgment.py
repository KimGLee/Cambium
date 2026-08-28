#!/usr/bin/env python3
"""Record one per-target judgment a Batch Review Requirement demands.

The Profile's ``Batch Review Requirements`` registry, not command-line
options, supplies which Judgment Item applies, over which targets, under
which pass-authority role, and in which receipt schema. The current AuditPlan
must contain exactly one matching Profile-extension obligation. One invocation
answers that frozen obligation: the judgment is bound to the
batch's current activation (so a reopened batch cannot reuse it), to the
target's K12/07 artifact fingerprint and, for a page target, its separate
Profile projection-neutral semantic fingerprint (so either relevant drift
invalidates it), and to the authorized Profile contract fingerprint (so a
revised Profile cannot keep it). The machine does not certify that the human
judgment is right; it certifies that the judgment happened, against these
bytes, by the declared role, for this attempt.

`open -> merge-ready` consumes these receipts through the batch-review
wrapper: expected records and actual records must match exactly.  This tool
changes no page, Ledger, or Queue state.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_evidence_runtime
import card_activation
import check_queue
import kblib
import profile_batch_judgment_contract as judgment_contract
import runtime_paths


TOOL = judgment_contract.PRODUCER_TOOL
TOOL_VERSION = judgment_contract.PRODUCER_TOOL_VERSION
JUDGMENT_CHECK = judgment_contract.PRODUCER_CHECK
DEFAULT_RECEIPTS = runtime_paths.BATCH_JUDGMENT_RECEIPT_PATH


def _current_plan(runtime, item):
    binding = audit_evidence_runtime.resolve_stage_plan(
        runtime, item, judgment_contract.DUE_STAGE,
        required_state="open")
    return binding["plan"], binding["audit_plan_sha256"]


def build_judgment_receipt(runtime, contract, item, plan, plan_sha256,
                           judgment_item_id, target, reviewer_role,
                           statement, seq=1):
    """Build one judgment receipt for one frozen obligation record."""
    (obligation, requirement, _judgment, _expected_record,
     expected) = judgment_contract.resolve_obligation(
         plan, contract, item, target, judgment_item_id)
    if reviewer_role != requirement.pass_authority_role_id:
        raise ValueError(
            "reviewer role %r cannot answer %s; the Profile registers %r" %
            (reviewer_role, judgment_item_id,
             requirement.pass_authority_role_id))
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("a batch judgment requires a non-empty statement")
    if item.get("state") != "open":
        raise ValueError(
            "batch %s is %s; judgments are recorded only while it is open" %
            (item.get("id"), item.get("state")))

    expected_sha = judgment_contract.requirement_set_sha256(expected)

    activation_id = item.get("activation_receipt")
    catalog = runtime.get("current_receipt_catalog",
                          runtime.get("receipt_catalog", {}))
    entry = catalog.get(activation_id) if isinstance(
        activation_id, str) else None
    activation = entry[1] if entry else None
    if not isinstance(activation, dict):
        raise ValueError(
            "batch %s has no current activation receipt to bind" %
            item.get("id"))
    if activation.get(
            "activation_protocol") != card_activation.ACTIVATION_PROTOCOL:
        raise ValueError(
            "batch %s was activated under %r; judgments bind only %s "
            "activations — reactivate the batch first" %
            (item.get("id"), activation.get("activation_protocol"),
             card_activation.ACTIVATION_PROTOCOL))
    frozen_sha = activation.get("review_requirement_set_sha256")
    if frozen_sha != expected_sha:
        raise ValueError(
            "the current Profile/manifest expansion no longer matches the "
            "activation-frozen requirement set; reactivate the batch "
            "before judging")

    # Judging is the first act of the gate phase, so this is where that
    # phase's delivery is owed.  The actor's own execution context is passed
    # deliberately: a judgment is somebody's judgment, and evidence that
    # another context received the Gate Card proves nothing about this one.
    phase_errors = check_queue.activation_phase_delivery_errors(
        runtime, item, card_activation.PHASE_BATCH_GATE,
        actor_context_id=os.environ.get(
            card_activation.EXECUTION_CONTEXT_ENV))
    if phase_errors:
        raise ValueError("; ".join(phase_errors))

    fingerprints = judgment_contract.evidence_fingerprints(
        runtime["root"], plan, obligation, contract, item, target,
        judgment_item_id)
    profile_view = runtime.get("_profile_authorized_view")
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, JUDGMENT_CHECK, target, "pass",
        statement.strip(), seq, root=runtime["root"])
    receipt.update({
        "schema_version": 1,
        "record_kind": judgment_contract.RECORD_KIND,
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": item.get("id"),
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        "dimension": obligation["dimension"],
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "judgment_item_id": judgment_item_id,
        "target_selector": requirement.target_selector,
        "trigger": requirement.trigger,
        "producer_kind": requirement.producer_kind,
        "receipt_schema": requirement.receipt_schema,
        "pass_authority_role_id": requirement.pass_authority_role_id,
        "reviewer_role": reviewer_role,
        "opening_transition_receipt":
            plan["opening_transition_receipt"],
        "activation_receipt_id": activation_id,
        "review_requirement_set_sha256": frozen_sha,
        "semantic_content_sha256": (
            judgment_contract.semantic_content_fingerprint(
                runtime["root"], target, profile_view)
            if requirement.target_selector == "each-manifest-page"
            else None),
        "standards_version": plan["standards_version"],
        "active_standards_sha256":
            plan["active_standards_sha256"],
        "selected_profile_manifest":
            plan["selected_profile_manifest"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "profile_snapshot_sha256":
            plan["profile_snapshot_sha256"],
    })
    receipt.update(fingerprints)
    errors = judgment_contract.receipt_binding_errors(
        runtime["root"], plan, plan_sha256, contract, item, receipt,
        profile_view)
    if errors:
        raise ValueError(
            "constructed Profile judgment is invalid in: %s" %
            ", ".join(errors))
    return receipt


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record one AuditPlan-bound Batch Review judgment")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True,
                        help="exact open Queue batch ID")
    parser.add_argument("--judgment-item", required=True,
                        help="registered Batch Review Requirement Judgment "
                             "Item ID")
    parser.add_argument("--target", required=True,
                        help="manifest page path, or the batch ID for a "
                             "batch-selector requirement")
    parser.add_argument("--reviewer-role", required=True,
                        help="declared pass-authority Profile role ID")
    parser.add_argument("--statement", required=True,
                        help="bounded judgment statement (the concrete "
                             "verdict, not \"reviewed\")")
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
        if runtime.get("errors"):
            raise ValueError("current runtime is inconsistent: %s" %
                             "; ".join(runtime["errors"]))
        authority = check_queue.runtime_authority_context(runtime)
        view = runtime.get("_profile_authorized_view") or {}
        contract = view.get("_contract")
        if contract is None or not getattr(contract, "authorized", False):
            raise ValueError(
                "runtime has no authorized typed Profile contract")
        item = (runtime.get("items_by_id") or {}).get(args.batch)
        if not isinstance(item, dict):
            raise ValueError("batch %s is not in the Required Queue" %
                             args.batch)
        plan, plan_sha256 = _current_plan(runtime, item)
        receipt = build_judgment_receipt(
            runtime, contract, item, plan, plan_sha256,
            args.judgment_item, args.target, args.reviewer_role,
            args.statement)
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
        print("[PLAN] %s answers (%s, %s) for batch %s" %
              (args.reviewer_role, args.target, args.judgment_item,
               args.batch))
        print("dry run; add --apply to publish the bound judgment")
        return 0

    operation = {
        "tool": TOOL,
        "action": "record-batch-review-judgment",
        "batch_id": args.batch,
        "judgment_item_id": args.judgment_item,
        "target": args.target,
        "receipt_id": receipt["receipt_id"],
        "receipt_path": args.receipts,
        "before_coverage_sha256": runtime.get("coverage_sha256"),
        "planned_after_coverage_sha256": runtime.get("coverage_sha256"),
        "before_required_queue_sha256": runtime.get("queue_sha256"),
        "planned_after_required_queue_sha256": runtime.get("queue_sha256"),
        "before_progress_sha256": runtime.get("progress_sha256"),
        "planned_after_progress_sha256": runtime.get("progress_sha256"),
    }
    operation.update(check_queue.runtime_authority_lock_fields(authority))
    try:
        authority_kwargs = check_queue.runtime_authority_validation_kwargs(
            authority)
        with kblib.runtime_write_lock(
                root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if locked.get("errors"):
                    raise ValueError(
                        "runtime changed before evidence publication: %s" %
                        "; ".join(locked["errors"]))
                locked_item = (locked.get("items_by_id") or {}).get(
                    args.batch)
                locked_contract = (locked.get(
                    "_profile_authorized_view") or {}).get("_contract")
                locked_plan, locked_plan_sha256 = _current_plan(
                    locked, locked_item)
                # Rebuild under the lock so a drifted page, Profile, or
                # reopened batch cannot slip between plan and publication.
                locked_receipt = build_judgment_receipt(
                    locked, locked_contract, locked_item,
                    locked_plan, locked_plan_sha256,
                    args.judgment_item, args.target, args.reviewer_role,
                    args.statement)
                for field in ("receipt_id", "checked_at"):
                    locked_receipt[field] = receipt[field]
                if locked_receipt != receipt:
                    raise ValueError(
                        "judgment bindings changed before publication")
                before = kblib.receipt_append_observation(
                    receipt_path, [receipt])
            outcome, error, _observation = kblib.write_receipts_observed(
                receipt_path, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise ValueError(
                    "batch judgment publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        sys.stdout.write(
            kblib.canonical_json_bytes([receipt]).decode("utf-8") + "\n")
    else:
        print("[PASS] batch judgment recorded: %s" % receipt["receipt_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
