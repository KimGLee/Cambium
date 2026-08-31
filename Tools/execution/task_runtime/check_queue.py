#!/usr/bin/env python3
"""Validate Cambium's canonical Required Queue runtime state.

This module is the CLI and Queue Gate producer.  Python consumers use the
``queue_runtime`` API and ``runtime_validation`` composition layer directly.

The checker reconciles the Queue with Coverage object assignments and the
Progress Ledger's accepted revisions/fingerprint.  It also validates explicit
manifests, dependency order, lifecycle evidence, holds, confirmation,
concurrency, and repository-contained paths.

Exit codes:
  0  current state and requested gate pass
  1  malformed/inconsistent state or a requested gate fails
  2  state is reliable, but work is held/not yet materialized, or resume-status
     found an existing non-terminal task or a possible interrupted writer

Usage:
  python3 Tools/check_queue.py ROOT [--require-ready B1]
      [--require-complete | --require-maintenance-complete | --resume-status]
      [--receipts .cambium/receipts/queue.jsonl]
"""

import contextlib
import json
import os
import sys

import Tools.execution.context_delivery.card_activation as card_activation
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.execution.task_runtime.task_runtime_action as task_runtime_action
from Tools.platform.common import reporting
from Tools.execution.task_runtime.queue_check_receipt import make_check_receipt
from Tools.execution.task_runtime.runtime_validation import validate_runtime
from Tools.execution.task_runtime.queue_runtime import (
    ACTIVE_STATES,
    GATE_CHECK,  # producer registry introspects this CLI's declared check
    TOOL,
    TOOL_VERSION,
    MaintenanceConsumerContext,
    batch_close_recovery_inventory,
    batch_close_update_command,
    maintenance_completion_gate_errors,
    maintenance_gate_inventory,
    nonempty_string,
    current_receipt_catalog,
    require_receipt,
    resolve_activation_phase_receipt,
    resume_next_action,
    required_queue_completion_errors,
    standards_revalidation_context,
    standards_revalidation_producer_eligibility,
    reviewed_without_current_evidence,
)


def _parse_boundary_gate_arguments(values):
    mapping = {}
    errors = []
    for value in values or []:
        if not isinstance(value, str) or "=" not in value:
            errors.append("--boundary-gate-receipt must be GATE_ID=RECEIPT_ID")
            continue
        gate_id, receipt_id = value.split("=", 1)
        gate_id = gate_id.strip()
        receipt_id = receipt_id.strip()
        if not nonempty_string(gate_id) or not nonempty_string(receipt_id):
            errors.append("--boundary-gate-receipt has an empty gate/receipt ID")
        elif gate_id in mapping:
            errors.append("--boundary-gate-receipt repeats Gate ID %s" % gate_id)
        else:
            mapping[gate_id] = receipt_id
    return mapping, errors


def _delivery_result(receipt, activation_context=None, readback_context=None,
                     phase_context=None):
    """Attach transient bytes to the tool result, never the receipt register."""
    emitted = dict(receipt)
    if readback_context:
        emitted["readback_delivery_payload"] = readback_context.get(
            "readback_delivery_payload")
    if phase_context:
        emitted["activation_phase_payload"] = phase_context.get(
            "activation_phase_payload")
    return emitted


def _write_receipt(root, relative_path, result, outcome, details, mode,
                   confirmation_receipt=None, runtime_errors=None,
                   maintenance_context=None,
                   standards_revalidation_context=None,
                   hub_page_candidates=None, activation_context=None,
                   readback_context=None, phase_context=None,
                   phase_ack_context=None, resume_activation_contexts=None,
                   build_unwritten=False):
    """Append the small receipt and return its delivery-enriched tool result.

    Without ``--receipts`` there is no JSONL target and nothing is built, so
    a run that asks for nothing pays for nothing -- unchanged. ``--json``
    still needs the object itself, and passes ``build_unwritten=True`` to get
    it; the receipt is then constructed and returned but never written, which
    keeps ``--json`` a pure reader of what this invocation decided.
    """
    if not relative_path:
        if not build_unwritten:
            return None
        receipt = make_check_receipt(
            result, outcome, details, mode,
            confirmation_receipt=confirmation_receipt,
            runtime_errors=runtime_errors,
            maintenance_context=maintenance_context,
            standards_revalidation_context=standards_revalidation_context,
            hub_page_candidates=hub_page_candidates,
            activation_context=activation_context,
            readback_context=readback_context,
            phase_context=phase_context,
            phase_ack_context=phase_ack_context,
            resume_activation_contexts=resume_activation_contexts,
        )
        return _delivery_result(
            receipt, activation_context, readback_context, phase_context)
    path = kblib.managed_repository_path(
        root, relative_path, runtime_paths.RECEIPT_ROOT,
        suffixes=(".jsonl",), must_exist=False,
    )
    receipt = make_check_receipt(
        result, outcome, details, mode,
        confirmation_receipt=confirmation_receipt,
        runtime_errors=runtime_errors,
        maintenance_context=maintenance_context,
        standards_revalidation_context=standards_revalidation_context,
        hub_page_candidates=hub_page_candidates,
        activation_context=activation_context,
        readback_context=readback_context,
        phase_context=phase_context,
        phase_ack_context=phase_ack_context,
        resume_activation_contexts=resume_activation_contexts,
    )
    kblib.write_receipts(path, [receipt])
    return _delivery_result(
        receipt, activation_context, readback_context, phase_context)


def _resume_recommendation_for_token(result, token):
    """Render one already-selected token without re-selecting its priority."""
    try:
        route, parameters = task_runtime_action.action_route_for_token(
            token, resume_source=True)
    except ValueError:
        return "follow the selected runtime action %s" % token
    renderer_values = {}
    if route.recommendation_renderer == "batch-close-command":
        command = batch_close_update_command(result, {
            "batch": parameters["batch_id"],
            "queue_consistency_receipt":
                parameters["queue_consistency_receipt"],
            "close_gate_receipt": parameters["close_gate_receipt"],
            "delta_apply_receipt": parameters["delta_apply_receipt"],
        })
        renderer_values["command"] = command
    return task_runtime_action.resume_recommendation(
        token, **renderer_values)


def _resume_recommendation(result, token):
    return _resume_recommendation_for_token(result, token)


def _print_resume_status(result, errors):
    queue = result.get("queue") or {}
    progress = result.get("progress") or {}
    contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    checkpoint = progress.get("checkpoint") if isinstance(
        progress.get("checkpoint"), dict) else {}
    terminal_audit = progress.get("terminal_audit") if isinstance(
        progress.get("terminal_audit"), dict) else {}
    maintenance_completion = (progress.get("maintenance_completion")
                              if isinstance(
                                  progress.get("maintenance_completion"), dict)
                              else {})
    task_runtime = result.get("task_runtime") or {}
    items = result.get("items_by_id") or {}
    print("resume_status:")
    print("  task_id=%s" % queue.get("task_id"))
    print("  task_state=%s" % progress.get("task_state"))
    print("  scope_version=%s" % queue.get("scope_version"))
    print("  upstream_revision_id=%s" % queue.get("upstream_revision_id"))
    adoptions = progress.get("standards_adoptions")
    latest = adoptions[-1] if isinstance(adoptions, list) and adoptions and \
        isinstance(adoptions[-1], dict) else None
    if latest is not None and "upstream_revision_id" in latest:
        if latest.get("upstream_revision_id") is None:
            print("  standards_upstream=none-declared")
        else:
            print("  standards_upstream=%s@%s" %
                  (latest.get("upstream_source_ref"),
                   latest.get("upstream_revision_id")))
    print("  selected_profile_manifest=%s" %
          queue.get("selected_profile_manifest"))
    print("  contract_version=%s" % contract.get("contract_version"))
    exceptions = contract.get("policy_exceptions")
    if isinstance(exceptions, list) and exceptions:
        for entry in exceptions:
            if isinstance(entry, dict):
                print("  policy_exception=%s policy=%s limit=%s scope=%s:%s"
                      % (entry.get("decision_id"), entry.get("policy_id"),
                         entry.get("limit"), entry.get("scope_kind"),
                         entry.get("scope_ref")))
    else:
        print("  policy_exceptions=none")
    print("  completion_semantics=%s" %
          contract.get("completion_semantics"))
    print("  objective=%s" % json.dumps(
        contract.get("objective"), ensure_ascii=False))
    print("  exclusions=%s" % json.dumps(
        contract.get("exclusions"), ensure_ascii=False))
    print("  queue_revision=%s" % queue.get("queue_revision"))
    print("  state_revision=%s" % queue.get("state_revision"))
    print("  live.coverage_sha256=%s" % result.get("coverage_sha256"))
    print("  live.progress_sha256=%s" % result.get("progress_sha256"))
    print("  live.required_queue_sha256=%s" % result.get("queue_sha256"))
    print("  checkpoint.recorded_at=%s" % checkpoint.get("recorded_at"))
    print("  checkpoint.summary=%s" % json.dumps(
        checkpoint.get("summary"), ensure_ascii=False))
    print("  checkpoint.binding=%s" %
          task_runtime.get("checkpoint_binding", "unavailable"))
    latest_task_receipt = task_runtime.get("latest_receipt") or {}
    print("  task_transition.latest=%s" %
          (latest_task_receipt.get("receipt_id") or "none"))
    print("  task_transition.count=%d" %
          len(task_runtime.get("history") or []))
    print("  last_reconciled_guidance_id=%s" %
          (task_runtime.get("last_reconciled_guidance_id") or "none"))
    print("  pending_guidance=%s" %
          (",".join(task_runtime.get("pending_guidance") or []) or "none"))
    print("  pending_amendments=%s" %
          (",".join(task_runtime.get("pending_amendments") or []) or "none"))
    # Reported, never blocking: the next admitted adoption plan is where the
    # live contract's load-set declaration is re-judged, so a gap here is work
    # to schedule rather than a reason to refuse the runtime.
    for gap in task_runtime.get("contract_load_set_gaps") or []:
        print("  contract_load_set_gap=%s" % gap)
    print("  terminal_audit.state=%s" % terminal_audit.get("state"))
    print("  terminal_audit.proof_path=%s" %
          terminal_audit.get("terminal_proof_path"))
    print("  terminal_audit.proof_receipt=%s" %
          terminal_audit.get("terminal_proof_receipt"))
    print("  terminal_audit.queue_check_receipt=%s" %
          terminal_audit.get("queue_check_receipt"))
    print("  maintenance_completion.state=%s" %
          maintenance_completion.get("state"))
    print("  maintenance_completion.gate_receipt=%s" %
          maintenance_completion.get("completion_gate_receipt"))
    maintenance_inventory = maintenance_gate_inventory(result)
    print("  maintenance_gate.selected=%s" %
          (maintenance_inventory.get("selected") or "none"))
    print("  maintenance_gate.current_compatible=%s" %
          (",".join(entry["receipt_id"] for entry in
                    maintenance_inventory.get("compatible", [])) or "none"))
    print("  maintenance_gate.stale=%s" %
          (",".join(entry["receipt_id"] for entry in
                    maintenance_inventory.get("stale", [])) or "none"))
    candidate_context = result.get("maintenance_candidate_context") or {}
    print("  maintenance_candidates.sha256=%s" %
          (candidate_context.get("candidate_state_sha256") or "none"))
    print("  maintenance_candidates.total=%d" %
          len(candidate_context.get("records") or []))
    print("  maintenance_candidates.selected=%s" %
          (",".join(candidate_context.get("selected_ids") or []) or "none"))
    print("  maintenance_candidates.deferred=%s" %
          (",".join(candidate_context.get("deferred_ids") or []) or "none"))
    outstanding = result.get("standards_revalidation_outstanding") or {}
    print("  standards_revalidation.outstanding_batches=%s" %
          (",".join(sorted(outstanding)) or "none"))
    for batch_id in sorted(outstanding):
        print("  standards_revalidation.%s.bindings=%s" % (
            batch_id,
            json.dumps(outstanding[batch_id], ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")),
        ))
    barriers = result.get("standards_revalidation_barriers") or {}
    for batch_id in sorted(barriers):
        print("  standards_revalidation.%s.barrier=%s" % (
            batch_id, json.dumps(barriers[batch_id], ensure_ascii=False),
        ))
    selected_gate_id = maintenance_inventory.get("selected")
    selected_gate_entry = current_receipt_catalog(result).get(
        selected_gate_id) if selected_gate_id else None
    selected_gate = selected_gate_entry[1] if selected_gate_entry else {}
    print("  maintenance_candidates.run_id=%s" %
          (selected_gate.get("maintenance_run_id") or "none"))
    print("  maintenance_candidates.previous_receipt=%s" %
          (selected_gate.get("previous_maintenance_completion_receipt") or
           "none"))
    for state in runtime_state_contract.QUEUE_STATE_ORDER:
        batch_ids = sorted(
            (item_id for item_id, item in items.items()
             if item.get("state") == state),
            key=lambda item_id: (
                items[item_id].get("order", sys.maxsize), item_id),
        )
        print("  batches.%s=%s" % (state, ",".join(batch_ids) or "none"))
    for item_id, item in sorted(
            items.items(), key=lambda pair: (pair[1].get("order", sys.maxsize),
                                             pair[0])):
        print("  work_spec.%s.path=%s sha256=%s" % (
            item_id,
            item.get("work_spec_path") or "none",
            item.get("work_spec_sha256") or "none",
        ))
    holds = []
    for item_id, item in sorted(
            items.items(), key=lambda pair: (pair[1].get("order", sys.maxsize),
                                             pair[0])):
        if item.get("hold_state") != "none":
            holds.append("%s:%s:%s" % (
                item_id, item.get("hold_state"),
                json.dumps(item.get("hold_reason"), ensure_ascii=False),
            ))
    print("  holds=%s" % (" | ".join(holds) or "none"))
    deltas = result.get("managed_deltas") or []
    if deltas:
        for delta in deltas:
            print("  delta=%s batch=%s state=%s sha256=%s "
                  "handoff_status=%s handoff_errors=%s" % (
                      delta.get("path"), delta.get("batch"),
                      delta.get("state"), delta.get("sha256"),
                      delta.get("handoff_status"),
                      json.dumps(delta.get("handoff_errors") or [],
                                 ensure_ascii=False, sort_keys=True),
                  ))
    else:
        print("  deltas=none")
    applied = result.get("applied_delta_receipts") or []
    if applied:
        for entry in applied:
            print("  applied_delta batch=%s selected_receipt=%s "
                  "compatible_receipts=%s stale_receipts=%s selection_rule=%s" % (
                      entry.get("batch"), entry.get("selected_receipt"),
                      ",".join(entry.get("compatible_receipts") or []) or
                      "none",
                      ",".join(entry.get("stale_receipts") or []) or "none",
                      entry.get("selection_rule"),
                  ))
    else:
        print("  applied_deltas=none")
    pending_applies = result.get("pending_delta_applies") or {}
    print("  pending_delta_applies.status=%s current_batches=%s "
          "stale_receipts=%s" % (
              pending_applies.get("status"),
              ",".join(entry.get("batch") for entry in
                       pending_applies.get("current", [])) or "none",
              ",".join(entry.get("receipt") for entry in
                       pending_applies.get("stale", [])) or "none",
          ))
    close_recovery = result.get("batch_close_recovery") or {}
    close_selected = close_recovery.get("selected") or {}
    print("  batch_close_recovery.status=%s batch=%s selection_rule=%s" % (
        close_recovery.get("status"),
        close_recovery.get("batch") or "none",
        close_recovery.get("selection_rule") or "none",
    ))
    print("  batch_close_recovery.queue_consistency_receipt=%s" %
          (close_selected.get("queue_consistency_receipt") or "none"))
    print("  batch_close_recovery.close_gate_receipt=%s" %
          (close_selected.get("close_gate_receipt") or "none"))
    print("  batch_close_recovery.delta_apply_receipt=%s" %
          (close_selected.get("delta_apply_receipt") or "none"))
    print("  batch_close_recovery.repository_snapshot_sha256=%s" %
          (close_selected.get("repository_snapshot_sha256") or
           close_recovery.get("repository_snapshot_sha256") or "none"))
    print("  batch_close_recovery.compatible=%s stale=%s errors=%s" % (
        ",".join(entry.get("close_gate_receipt") for entry in
                 close_recovery.get("compatible", [])) or "none",
        ",".join(entry.get("close_gate_receipt") for entry in
                 close_recovery.get("stale", [])) or "none",
        json.dumps(close_recovery.get("errors") or [],
                   ensure_ascii=False, sort_keys=True),
    ))
    print("  batch_close_recovery.update_queue_command=%s" %
          (close_recovery.get("update_queue_command") or "none"))
    locks = result.get("_writer_locks") or []
    if locks:
        for lock in locks:
            print("  lock=%s transaction_phase=%s prepare_receipt_matches_owner=%s "
                  "transaction_receipts=%s "
                  "owner=%s owner_error=%s" % (
                lock.get("path"),
                lock.get("transaction_phase"),
                lock.get("prepare_receipt_matches_owner"),
                json.dumps(lock.get("transaction_receipts"),
                           ensure_ascii=False, sort_keys=True),
                json.dumps(lock.get("owner"), ensure_ascii=False,
                           sort_keys=True),
                json.dumps(lock.get("owner_error"), ensure_ascii=False),
            ))
            for state_name in tuple(sorted(
                    runtime_state_contract.RUNTIME_LEDGER_IDS)):
                phase = (lock.get("state_phases") or {}).get(state_name) or {}
                print("    state.%s phase=%s live=%s before=%s "
                      "planned_after=%s metadata_error=%s" % (
                          state_name, phase.get("phase"),
                          phase.get("live_sha256"),
                          phase.get("before_sha256"),
                          phase.get("planned_after_sha256"),
                          json.dumps(phase.get("metadata_error"),
                                     ensure_ascii=False),
                      ))
            archive = lock.get("delta_archive_recovery")
            if archive:
                print("    delta_archive status=%s source=%s archive=%s "
                      "expected_sha256=%s source_sha256=%s archive_sha256=%s "
                      "recovery_fact=%s" % (
                          archive.get("status"),
                          archive.get("delta_archive_source"),
                          archive.get("delta_archive_path"),
                          archive.get("delta_sha256"),
                          archive.get("source_sha256"),
                          archive.get("archive_sha256"),
                          archive.get("recovery_fact"),
                      ))
                print("    delta_archive_hint=%s" % archive.get("hint"))
            if "operation_receipt" in lock:
                print("    operation_receipt=%s" % json.dumps(
                    lock["operation_receipt"], ensure_ascii=False,
                    sort_keys=True))
            print("    reconciliation_hint=%s" %
                  lock.get("reconciliation_hint"))
    else:
        print("  locks=none")
    next_token = resume_next_action(result, errors)
    print("next_action=%s" % next_token)
    print("recommended_action=%s" %
          _resume_recommendation(result, next_token))


def main(argv=None):
    parser = kblib.ArgumentParser(description="Validate canonical Required Queue state")
    parser.add_argument("root", help="adopting repository root")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--require-ready", metavar="BATCH_ID",
                       help="prove BATCH_ID is queued and ready to activate")
    group.add_argument("--require-revalidation", metavar="BATCH_ID",
                       help="prove BATCH_ID may produce its Standards "
                            "revalidation aggregate")
    group.add_argument("--require-complete", action="store_true",
                       help="build completion gate: prove no Required work "
                            "remains")
    group.add_argument("--require-maintenance-complete", action="store_true",
                       help="maintenance completion gate: prove one bounded "
                            "maintenance run is complete")
    group.add_argument("--resume-status", action="store_true",
                       help="show interruption-safe task and batch resume state")
    group.add_argument(
        "--deliver-readback", metavar="BATCH_ID",
        help="deliver one registered conditional Card read-back source for an "
             "already-open batch")
    group.add_argument(
        "--deliver-phase", metavar="BATCH_ID",
        help="deliver one frozen activation phase part of BATCH_ID inside "
             "the protocol delivery budget")
    group.add_argument(
        "--ack-activation-phase", metavar="BATCH_ID",
        help="return one delivered phase part nonce as same-context delivery "
             "evidence")
    parser.add_argument(
        "--readback-rule", metavar="RULE_ID",
        help="registered rule selected with --deliver-readback")
    parser.add_argument(
        "--phase", metavar="PHASE_ID",
        help="frozen activation phase selected with --deliver-phase or "
             "--ack-activation-phase")
    parser.add_argument(
        "--phase-part", metavar="INDEX", type=int, default=0,
        help="part index inside the selected phase (default 0)")
    parser.add_argument(
        "--phase-nonce", metavar="NONCE",
        help="nonce returned from the delivered phase part, supplied to "
             "--ack-activation-phase")
    parser.add_argument(
        "--phase-delivery-receipt", metavar="RECEIPT_ID",
        help="delivery receipt the acknowledged phase nonce came from, "
             "supplied to --ack-activation-phase")
    parser.add_argument("--confirmation-receipt",
                        help="confirmation evidence supplied to --require-ready")
    parser.add_argument(
        "--boundary-gate-receipt", action="append", default=[],
        metavar="GATE_ID=RECEIPT_ID",
        help="current gate evidence supplied to --require-revalidation")
    parser.add_argument("--budget-manifest-receipt",
                        help="closed budget-manifest receipt ID supplied to "
                             "--require-maintenance-complete")
    parser.add_argument("--ledger-advance-receipt",
                        help="Coverage Ledger advance receipt ID supplied to "
                             "--require-maintenance-complete")
    parser.add_argument("--watermark-advance-receipt",
                        help="watermark advance receipt ID supplied to "
                             "--require-maintenance-complete")
    parser.add_argument("--receipts", help="repository-relative JSONL receipt path")
    parser.add_argument(
        "--json", action="store_true",
        help="write this run's receipt object to stdout as one canonical "
             "JSON array and move the human report to stderr; receipt "
             "writing and exit codes are unchanged")
    args = parser.parse_args(argv)

    if not args.json:
        return _run(args, None)
    produced = []
    with contextlib.redirect_stdout(sys.stderr):
        code = _run(args, produced)
    reporting.write_canonical_json_array(produced, omit_if_empty=True)
    return code


def _run(args, produced):
    """Evaluate one already-parsed invocation; ``produced`` collects receipts."""
    result = validate_runtime(args.root)
    errors = list(result["errors"])
    candidates = []
    # Notes are neither errors nor candidates: a fact the operator must keep
    # seeing, whose disposition is already recorded.  They never change the
    # exit code, because a decision already made is not an open judgment.
    notes = []
    hub_page_candidates = []
    _writer_locks = result.get("_writer_locks") or []
    maintenance_context = None
    revalidation_context = None
    activation_context = None
    readback_context = None
    phase_context = None
    phase_ack_context = None
    resume_activation_contexts = []

    if args.confirmation_receipt and not args.require_ready:
        errors.append("--confirmation-receipt is only valid with --require-ready")
    if args.boundary_gate_receipt and not args.require_revalidation:
        errors.append("--boundary-gate-receipt is only valid with "
                      "--require-revalidation")
    if args.readback_rule and not args.deliver_readback:
        errors.append("--readback-rule is only valid with --deliver-readback")
    if args.deliver_readback and not args.readback_rule:
        errors.append("--deliver-readback requires --readback-rule")
    if args.phase and not (args.deliver_phase or args.ack_activation_phase):
        errors.append("--phase is only valid with --deliver-phase or "
                      "--ack-activation-phase")
    if args.deliver_phase and not args.phase:
        errors.append("--deliver-phase requires --phase")
    if args.ack_activation_phase and not (
            args.phase and args.phase_nonce and args.phase_delivery_receipt):
        errors.append(
            "--ack-activation-phase requires --phase, --phase-nonce and "
            "--phase-delivery-receipt")
    for flag, value in (("--phase-nonce", args.phase_nonce),
                        ("--phase-delivery-receipt",
                         args.phase_delivery_receipt)):
        if value and not args.ack_activation_phase:
            errors.append("%s is only valid with --ack-activation-phase" %
                          flag)
    if args.phase_part and not (args.deliver_phase or
                                args.ack_activation_phase):
        errors.append("--phase-part is only valid with --deliver-phase or "
                      "--ack-activation-phase")
    if args.phase_part < 0:
        errors.append("--phase-part must not be negative")
    maintenance_evidence = (
        args.budget_manifest_receipt, args.ledger_advance_receipt,
        args.watermark_advance_receipt,
    )
    if any(maintenance_evidence) and not args.require_maintenance_complete:
        errors.append(
            "maintenance evidence receipts are only valid with "
            "--require-maintenance-complete"
        )
    if args.require_maintenance_complete and not all(maintenance_evidence):
        errors.append(
            "--require-maintenance-complete requires "
            "--budget-manifest-receipt, --ledger-advance-receipt, and "
            "--watermark-advance-receipt"
        )

    if _writer_locks:
        lock_paths = ", ".join(lock.get("path", "<unknown>")
                               for lock in _writer_locks)
        message = ("runtime state has active or interrupted writer lock(s): %s" %
                   lock_paths)
        if args.require_complete:
            # The shared build-completion predicate below owns this error so
            # in-process consumers and the CLI make the same decision.
            pass
        elif args.require_maintenance_complete:
            errors.append(message)
        else:
            candidates.append(message)

    if args.require_complete:
        for completion_error in required_queue_completion_errors(result):
            if completion_error not in errors:
                errors.append(completion_error)

    if args.resume_status:
        close_recovery = batch_close_recovery_inventory(result)
        result["batch_close_recovery"] = close_recovery
        if close_recovery.get("status") == "snapshot-unavailable":
            errors.extend(
                "batch-close recovery snapshot unavailable: %s" % error
                for error in close_recovery.get("errors", []))

    if not errors and args.require_revalidation:
        ineligible = standards_revalidation_producer_eligibility(
            result, args.require_revalidation)
        if ineligible:
            errors.append(ineligible)
        else:
            supplied, supplied_errors = _parse_boundary_gate_arguments(
                args.boundary_gate_receipt)
            errors.extend(supplied_errors)
            if not errors:
                revalidation_context, context_errors = \
                    standards_revalidation_context(
                        result, args.require_revalidation, supplied)
                errors.extend(context_errors)
    elif not errors and args.require_ready:
        item = result.get("items_by_id", {}).get(args.require_ready)
        # K13/10: a hub page this batch creates does not block activation; it
        # is handed to the integrator's post-merge hub synchronization step.
        hub_page_candidates = list((result.get("hub_page_admission") or {}).get(
            args.require_ready, {}).get("candidates") or [])
        if item is None:
            errors.append("requested batch %s does not exist" % args.require_ready)
        elif item.get("state") != "queued":
            errors.append("requested batch %s is %s, not queued" %
                          (args.require_ready, item.get("state")))
        elif (result.get("progress", {}).get("task_state") in
              runtime_state_contract.TASK_TERMINAL_STATES):
            errors.append("task_state=%s is terminal and cannot activate batch %s" %
                          (result["progress"].get("task_state"),
                           args.require_ready))
        elif args.require_ready not in result["ready"]:
            reasons = list(dict(result["blocked"]).get(
                args.require_ready, ["not ready"]))
            if ("confirmation receipt absent" in reasons and
                    args.confirmation_receipt):
                confirmation_errors = []
                require_receipt(
                    current_receipt_catalog(result),
                    args.confirmation_receipt,
                    "%s confirmation" % args.require_ready,
                    confirmation_errors,
                    expected={"check": "confirmation",
                              "target": args.require_ready},
                )
                if confirmation_errors:
                    errors.extend(confirmation_errors)
                else:
                    reasons.remove("confirmation receipt absent")
                    if "hold=confirmation-required" in reasons:
                        reasons.remove("hold=confirmation-required")
                    if not reasons and args.require_ready not in result["ready"]:
                        result["ready"].append(args.require_ready)
            if reasons and not errors:
                candidates.append("%s is not executable: %s" %
                                  (args.require_ready, "; ".join(reasons)))
    elif not errors and args.deliver_readback:
        item = result.get("items_by_id", {}).get(args.deliver_readback)
        if item is None:
            errors.append("requested batch %s does not exist" %
                          args.deliver_readback)
        elif item.get("state") not in ACTIVE_STATES:
            errors.append(
                "read-back delivery requires an open or merge-ready batch; "
                "%s is %s" % (args.deliver_readback, item.get("state")))
        else:
            catalog = current_receipt_catalog(result)
            activation_id = item.get("activation_receipt")
            entry = catalog.get(activation_id)
            activation_receipt = entry[1] if entry is not None else None
            if (not isinstance(activation_receipt, dict) or
                    activation_receipt.get("tool") != TOOL or
                    activation_receipt.get("tool_version") != TOOL_VERSION):
                errors.append(
                    "batch %s has no current Card-first activation receipt; "
                    "read-back delivery is unavailable for this runtime" %
                    args.deliver_readback)
            else:
                try:
                    readback_context = card_activation.build_readback_addendum(
                        result["root"],
                        card_activation.context_from_receipt(
                            activation_receipt),
                        args.readback_rule,
                    )
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("cannot deliver Card read-back: %s" % exc)
    elif not errors and (args.deliver_phase or args.ack_activation_phase):
        batch_id = args.deliver_phase or args.ack_activation_phase
        item = result.get("items_by_id", {}).get(batch_id)
        activation_receipt = None
        if item is None:
            errors.append("requested batch %s does not exist" % batch_id)
        elif item.get("state") not in ACTIVE_STATES:
            errors.append(
                "activation phase delivery requires an open or merge-ready "
                "batch; %s is %s" % (batch_id, item.get("state")))
        else:
            catalog = current_receipt_catalog(result)
            entry = catalog.get(item.get("activation_receipt"))
            activation_receipt = entry[1] if entry is not None else None
            if (not isinstance(activation_receipt, dict) or
                    activation_receipt.get("tool") != TOOL or
                    activation_receipt.get("tool_version") != TOOL_VERSION):
                errors.append(
                    "batch %s has no current Card-first activation receipt; "
                    "reopen it before phase delivery" % batch_id)
                activation_receipt = None
        if activation_receipt is not None and args.deliver_phase:
            try:
                phase_context = card_activation.build_phase_delivery(
                    result["root"],
                    card_activation.context_from_receipt(activation_receipt),
                    args.phase, args.phase_part,
                    activation_receipt_id=item.get("activation_receipt"))
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append("cannot deliver activation phase: %s" % exc)
        elif activation_receipt is not None:
            delivery, delivery_errors = resolve_activation_phase_receipt(
                result, item, args.phase_delivery_receipt,
                receipt_kind="delivery", phase_id=args.phase,
                part_index=args.phase_part)
            if delivery_errors:
                errors.extend(
                    "cannot acknowledge activation phase: %s" % error
                    for error in delivery_errors)
            else:
                try:
                    phase_ack_context = card_activation.build_phase_ack(
                        dict(delivery, receipt_id=args.phase_delivery_receipt),
                        args.phase_nonce)
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("cannot acknowledge activation phase: %s" %
                                  exc)
    elif not errors and args.require_maintenance_complete:
        maintenance_consumer = MaintenanceConsumerContext.from_runtime(result)
        maintenance_errors, maintenance_context = \
            maintenance_completion_gate_errors(
                maintenance_consumer,
                args.budget_manifest_receipt,
                args.ledger_advance_receipt,
                args.watermark_advance_receipt,
            )
        errors.extend(maintenance_errors)
    elif not errors and args.resume_status:
        progress = result.get("progress") or {}
        task_state = progress.get("task_state")
        active_ids = [item_id for item_id, item in
                      (result.get("items_by_id") or {}).items()
                      if item.get("state") in ACTIVE_STATES]
        held_ids = [item_id for item_id, item in
                    (result.get("items_by_id") or {}).items()
                    if item.get("hold_state") != "none"]
        if task_state in runtime_state_contract.TASK_NONTERMINAL_STATES:
            candidates.append(
                "existing task_state=%s is non-terminal and must be resumed or "
                "resolved before a new task" % task_state
            )
        if (active_ids and
                task_state in runtime_state_contract.TASK_NONTERMINAL_STATES):
            candidates.append("in-flight batch(es) require resume: %s" %
                              ", ".join(sorted(active_ids)))
        if (held_ids and
                task_state in runtime_state_contract.TASK_NONTERMINAL_STATES and
                task_state not in ("paused", "blocked")):
            candidates.append("batch hold(s) require resolution: %s" %
                              ", ".join(sorted(held_ids)))
        for item_id in sorted(active_ids):
            item = result["items_by_id"][item_id]
            try:
                delivery = card_activation.build_activation_context(
                    result["root"], result["progress"], item,
                    runtime_state=result)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(
                    "cannot compile resume Card delivery for %s: %s" %
                    (item_id, exc))
                continue
            catalog = current_receipt_catalog(result)
            recorded_entry = catalog.get(item.get("activation_receipt"))
            recorded = recorded_entry[1] if recorded_entry else None
            bundle_errors = card_activation.exact_bundle_errors(
                delivery, card_activation.context_from_receipt(recorded))
            if bundle_errors:
                errors.extend(
                    "cannot resume %s Card delivery: %s" % (item_id, error)
                    for error in bundle_errors)
                continue
            resume_activation_contexts.append({
                "batch_id": item_id,
                "parent_activation_receipt": item.get(
                    "activation_receipt"),
                **delivery,
            })
    for defect in result.get("structural_admission_defects") or []:
        candidates.append(defect)
    reviewed_without_evidence = reviewed_without_current_evidence(
        result.get("coverage"))
    if reviewed_without_evidence:
        candidates.append(
            "%d Coverage record(s) claim authoring_status=reviewed without "
            "an exact linked last_reviewed owner Receipt and therefore are "
            "not current authority "
            "(K02/01); initialize them as unassessed and earn current review "
            "evidence: %s" %
            (len(reviewed_without_evidence),
             ", ".join(reviewed_without_evidence[:5]) +
             ("..." if len(reviewed_without_evidence) > 5 else ""))
        )
    if not errors:
        queue_items = result.get("queue", {}).get("required_queue") or []
        if not queue_items:
            candidates.append("Queue is valid but empty; Required work has not been materialized")
        elif (result["remaining"] and not result["ready"] and
              not any(item.get("state") in ACTIVE_STATES
                      for item in queue_items if isinstance(item, dict))):
            candidates.append("no executable batch; remaining work is held or dependency-blocked")

    if (not errors and not candidates and args.require_ready and
            activation_context is None):
        try:
            activation_context = card_activation.build_activation_context(
                result["root"], result["progress"],
                result["items_by_id"][args.require_ready],
                runtime_state=result,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append("cannot compile Card activation bundle: %s" % exc)

    for error in errors:
        print("[FAIL] %s" % error)
    for candidate in candidates:
        print("[HOLD] %s" % candidate)
    for note in notes:
        print("[NOTE] %s" % note)
    if not errors and not candidates:
        print("[PASS] Required Queue is consistent")
    if args.resume_status:
        _print_resume_status(result, errors)
    elif result.get("queue"):
        print("queue_revision=%s state_revision=%s remaining=%s ready=%s" % (
            result["queue"].get("queue_revision"),
            result["queue"].get("state_revision"), result["remaining"],
            ",".join(result["ready"]) or "none",
        ))
        print("required_queue_sha256=%s" % result.get("queue_sha256"))
        if args.require_ready:
            print("hub_page_candidates=%s" %
                  ("; ".join(hub_page_candidates) or "none"))
            if activation_context:
                print("card_bundle_sha256=%s delivery_assurance=%s" % (
                    activation_context.get("card_bundle_sha256"),
                    activation_context.get("delivery_assurance")))
        if args.deliver_readback and readback_context:
            print("readback_addendum_sha256=%s delivery_assurance=%s" % (
                readback_context.get("readback_addendum_sha256"),
                readback_context.get("delivery_assurance")))

    code = 1 if errors else (2 if candidates else 0)
    outcome = "fail" if errors else ("candidate" if candidates else "pass")
    details = "errors=%d candidates=%d remaining=%s ready=%s" % (
        len(errors), len(candidates), result.get("remaining"),
        ",".join(result.get("ready", [])) or "none",
    )
    if args.require_revalidation:
        mode = "require-revalidation:%s" % args.require_revalidation
    elif args.require_ready:
        mode = "require-ready:%s" % args.require_ready
    elif args.deliver_readback:
        mode = "deliver-readback:%s:%s" % (
            args.deliver_readback, args.readback_rule)
    elif args.deliver_phase:
        mode = "deliver-phase:%s:%s:%d" % (
            args.deliver_phase, args.phase, args.phase_part)
    elif args.ack_activation_phase:
        mode = "ack-activation-phase:%s:%s:%d" % (
            args.ack_activation_phase, args.phase, args.phase_part)
    elif args.require_complete:
        mode = "require-complete"
    elif args.require_maintenance_complete:
        mode = "require-maintenance-complete"
    elif args.resume_status:
        mode = "resume-status"
    else:
        mode = "consistency"
    try:
        receipt = _write_receipt(
            args.root, args.receipts, result, outcome, details, mode,
            hub_page_candidates=hub_page_candidates,
            confirmation_receipt=args.confirmation_receipt,
            runtime_errors=errors,
            maintenance_context=maintenance_context,
            standards_revalidation_context=revalidation_context,
            activation_context=activation_context,
            readback_context=readback_context,
            phase_context=phase_context,
            phase_ack_context=phase_ack_context,
            resume_activation_contexts=resume_activation_contexts,
            build_unwritten=produced is not None,
        )
    except (OSError, ValueError) as exc:
        print("[FAIL] cannot write receipts: %s" % exc)
        return 1
    if produced is not None and receipt is not None:
        produced.append(receipt)
    return code


if __name__ == "__main__":
    sys.exit(main())
