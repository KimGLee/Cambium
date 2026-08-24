#!/usr/bin/env python3
"""Validate Cambium's canonical Required Queue runtime state.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import card_activation
# Five peer modules this file no longer calls, and must keep importing.  The
# runtime moved into `queue_runtime` and took its calls with it, but about
# twenty-five test sites patch attributes on these module objects *through*
# `check_queue` -- `check_queue.metadata_property_state`, and so on -- and the
# object is shared only while the import statement is here.  Removing them as
# unused breaks all of those at once with an AttributeError, so they stay, and
# they stay with this note attached.
import candidate_lifecycle
import check_profile
import maintenance_candidates
import metadata_execution_contract
import metadata_property_state
import project_page_state
# The persisted typed Gate receipt validator this runtime asks for by name.
# It used to be defined here and reach back into the Gate runtime through a
# function-body import; it now lives with the module whose object it
# validates, and the arrow points one way.
import metadata_gate_runtime
import queue_runtime.property_state
import queue_runtime.runtime

# The permanent facade.  Every name below is defined in `queue_runtime`
# and re-exported here because twenty-one shipped modules and twenty-one
# test files read it from `check_queue`.  Dropping a name is a
# compatibility break even when nothing in this file uses it.
from queue_runtime import (
    ACTIVE_STANDARDS_PATH,
    ACTIVE_STATES,
    APPLY_DELTA_TOOL_VERSION,
    BASE_RECEIPT_DIMENSIONS,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_ID_RE,
    BATCH_REVIEW_CHECK,
    BATCH_REVIEW_GATE_ID,
    CHECKPOINT_FIELDS,
    CLOSED_LIST_EVIDENCE_FIELDS,
    COMPACT_CLOSE_EVIDENCE_VERSIONS,
    COMPLETION_SEMANTICS,
    CONTRACT_AMENDMENT_PLAN_PREFIX,
    CONTRACT_FIELDS,
    CONTRACT_OPTIONAL_FIELDS,
    COVERAGE_BATCH_SPEC_FIELDS,
    COVERAGE_PATH,
    COVERAGE_TOP_LEVEL_FIELDS,
    EVIDENCE_IDENTITY_USES,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_TERMINAL_HISTORY,
    EXPRESSION_LAYER_SLOT,
    GATE_CHECK,
    GUIDANCE_DISPOSITIONS,
    HISTORICAL_CORPUS_PLAN_TOOL_VERSIONS,
    HOLDS,
    INVALIDATION_APPLIED_ROLLBACK_FIELDS,
    INVALIDATION_FIELDS,
    LEGACY_PROPERTY_STATE_FIELD,
    MANUAL_ATTESTATION_TOOL,
    MANUAL_ATTESTATION_TOOL_VERSION,
    NOT_BATCH_SCOPED_GATE,
    PROGRESS_PATH,
    QUEUE_EXHAUSTED_GATE,
    QUEUE_ITEM_FIELDS,
    QUEUE_PATH,
    RECEIPT_REFERENCE_FIELDS,
    REGISTER_AMENDMENT_TOOL_VERSION,
    SHA256_RE,
    STANDARDS_ADOPTION_PLAN_PREFIX,
    STANDARDS_ADOPTION_TOOL,
    STANDARDS_ADOPTION_TOOL_VERSION,
    STANDARDS_GATE_REGISTRY_PATH,
    STATES,
    SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS,
    TERMINAL_STATES,
    TOOL,
    TOOL_VERSION,
    UPDATE_QUEUE_TOOL_VERSION,
    WORK_SPEC_FIELDS,
    WORK_SPEC_PREFIX,
    _actionable_revalidation_batches,
    _authorized_profile_view_errors,
    _batch_close_recovery_inventory,
    _candidate_evidence_binding_errors,
    _closed_delta_apply_errors,
    _cold_receipt_store,
    _consumed_standards_revalidation_keys,
    _contract_anchor_chain,
    _contract_sha256,
    _coverage_provenance_errors,
    _current_close_transition_metadata_errors,
    _current_open_semantic_baseline_errors,
    _global_transition_errors,
    _last_reconciled_guidance_id,
    _latest_consumed_maintenance_gate,
    _live_read_set_load_findings,
    _maintenance_completion_gate_errors,
    _maintenance_gate_inventory,
    _maintenance_gate_time_errors,
    _nonempty_string,
    _operational_amendment_registration_errors,
    _pending_control_ids,
    _policy_exception_errors,
    _previous_maintenance_candidate_state,
    _public_profile_load_evidence,
    _read_set_load_closure,
    _receipt_catalog,
    _require_receipt,
    _resume_next_action,
    _review_property_evidence_errors,
    _standards_adoption_errors,
    _terminal_proof_profile_binding_errors,
    _timestamp_value,
    _unadmitted_profile_hub_paths,
    _valid_timestamp,
    _work_spec_binding_errors,
    _work_spec_errors,
    accounted_standards_versions,
    activation_phase_delivery_errors,
    active_standards_authorized_view,
    active_standards_view_currency_errors,
    batch_reference_settlement_errors,
    batch_review_judgment_errors,
    batch_review_receipt_errors,
    batch_touches_control_plane,
    close_gate_receipt_errors,
    coverage_reviewed_era_exception,
    current_attempt_evidence_barrier,
    current_opening_semantic_baseline,
    current_opening_semantic_context,
    current_receipt_catalog,
    delta_apply_write_barrier,
    delta_gate_receipt_ids,
    evidence_identity_errors,
    gate_registry_producer_errors,
    historical_receipt_catalog,
    item_revalidation_discharges,
    item_undischarged_revalidation_hold,
    judgment_record_set_sha256,
    outstanding_standards_revalidation,
    partition_boundary_gates_by_lifecycle,
    producer_module,
    profile_hub_paths,
    profile_load_authorized_view,
    profile_load_authorized_view_currency_errors,
    profile_load_errors,
    profile_load_evidence,
    project_adoption_gate_ids,
    property_receipt_utc_date,
    queue_gate_id_for_mode,
    receipt_matches_gate_id,
    registered_gate_position,
    require_runtime_authority_current,
    required_queue_completion_errors,
    runtime_authority_context,
    runtime_authority_currency_errors,
    runtime_authority_lock_fields,
    runtime_authority_validation_kwargs,
    selected_profile_manifest_errors,
    standards_adoption_plan_errors,
    standards_gate_capability_registry,
    standards_gate_registry,
    standards_revalidation_context,
    standards_revalidation_producer_eligibility,
    standards_revalidation_receipt_errors,
    standards_revalidation_requirements,
    substantive_review_errors,
    task_phase_delivery_errors,
    unsupported_reviewed_records,
)

def validate_runtime(*args, **kwargs):
    """Run the whole-repository consistency pass with the Gate validator.

    `queue_runtime.runtime` cannot name `metadata_gate_runtime`: that module
    imports the package, and the arrow may not run both ways.  So the one
    argument it refuses to default is supplied here, by the file that imports
    both -- and every caller that has ever written `check_queue.validate_runtime`
    keeps writing it, including the ten test sites that patch this name.

    Arguments pass straight through rather than being restated, so a new
    parameter on the real function needs no edit here and cannot be silently
    dropped on the way.
    """
    kwargs.setdefault("gate_evidence_errors",
                      metadata_gate_runtime.persisted_property_gate_errors)
    return queue_runtime.runtime.validate_runtime(*args, **kwargs)


def _coverage_property_state_errors(*args, **kwargs):
    """Supply the persisted-Gate validator the package may not import.

    `queue_runtime.property_state` requires `gate_evidence_errors` and gives
    it no default, because a default of None would let an in-package caller
    run a quietly weaker check than this one.  The validator lives in
    `metadata_gate_runtime`, which imports the package -- so this file, which
    imports both, is the only place that can hand one to the other.  Callers
    that have always called this by name keep calling it by name.
    """
    kwargs.setdefault("gate_evidence_errors",
                      metadata_gate_runtime.persisted_property_gate_errors)
    return queue_runtime.property_state._coverage_property_state_errors(
        *args, **kwargs)


# The historical spelling of one promoted name.  `evidence_identity`
# offers `evidence_identity_errors` because `metadata_gate_runtime` needs
# the identical identity policy and may not read a private name; the
# underscored spelling is kept here, where every other historical
# spelling is kept, for the test that has always read it.
_evidence_identity_errors = evidence_identity_errors

































































































































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
        if not _nonempty_string(gate_id) or not _nonempty_string(receipt_id):
            errors.append("--boundary-gate-receipt has an empty gate/receipt ID")
        elif gate_id in mapping:
            errors.append("--boundary-gate-receipt repeats Gate ID %s" % gate_id)
        else:
            mapping[gate_id] = receipt_id
    return mapping, errors





























































































































































































































































def make_check_receipt(result, outcome, details, mode,
                       confirmation_receipt=None, runtime_errors=None,
                       maintenance_context=None,
                       standards_revalidation_context=None,
                       hub_page_candidates=None,
                       activation_context=None,
                       readback_context=None,
                       piece_context=None,
                       piece_ack_context=None,
                       phase_context=None,
                       phase_ack_context=None,
                       resume_activation_contexts=None):
    """Build the canonical receipt for one already-evaluated Queue result.

    This is the canonical construction path for ``check_queue`` receipt bytes.
    A caller that composes a larger gate while holding the shared runtime lock
    may use it only after calling :func:`validate_runtime` on those exact
    locked bytes.  Centralization keeps schema/state bindings consistent; it
    does not authenticate the caller or stop another writer copying labels.
    """
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, GATE_CHECK, QUEUE_PATH, outcome,
        details, 1,
    )
    if result.get("queue_sha256"):
        receipt["queue_check_mode"] = mode
        gate_id = queue_gate_id_for_mode(mode)
        if gate_id is not None:
            receipt["gate_id"] = gate_id
        if confirmation_receipt:
            receipt["confirmation_receipt"] = confirmation_receipt
        receipt["required_queue_sha256"] = result["queue_sha256"]
        receipt["coverage_ledger_sha256"] = result.get("coverage_sha256")
        receipt["progress_ledger_sha256"] = result.get("progress_sha256")
        receipt["queue_revision"] = result["queue"].get("queue_revision")
        receipt["queue_state_revision"] = result["queue"].get("state_revision")
        receipt["remaining_required_work_units"] = result.get("remaining")
        receipt["task_id"] = result["queue"].get("task_id")
        receipt["standards_version"] = result["queue"].get(
            "standards_version")
        receipt["selected_profile_manifest"] = result["queue"].get(
            "selected_profile_manifest")
        if mode.startswith("require-ready:"):
            # K13/10 hands the hub pages this batch creates to the
            # integrator's post-merge synchronization step; the durable
            # record travels with the activation receipt.
            receipt["hub_page_candidates"] = list(hub_page_candidates or [])
            if activation_context:
                receipt.update(card_activation.activation_receipt_binding(
                    activation_context))
        if mode.startswith("deliver-activation-piece:") and piece_context:
            receipt.update(card_activation.piece_receipt_binding(
                piece_context))
        if mode.startswith("ack-activation-piece:") and piece_ack_context:
            receipt.update(card_activation.piece_ack_receipt_binding(
                piece_ack_context))
        if mode.startswith("deliver-phase:") and phase_context:
            receipt.update(card_activation.phase_receipt_binding(
                phase_context))
        if mode.startswith("ack-activation-phase:") and phase_ack_context:
            receipt.update(card_activation.phase_ack_receipt_binding(
                phase_ack_context))
        if mode.startswith("deliver-readback:") and readback_context:
            receipt.update(card_activation.readback_receipt_binding(
                readback_context))
        if mode == "consistency" and outcome == "pass":
            receipt["repository_snapshot_sha256"] = \
                kblib.repository_snapshot_sha256(result["root"])
        if maintenance_context:
            receipt.update(maintenance_context)
        if standards_revalidation_context:
            receipt.update(standards_revalidation_context)
        if mode == "resume-status":
            progress = result.get("progress") or {}
            contract = progress.get("contract") if isinstance(
                progress.get("contract"), dict) else {}
            checkpoint = progress.get("checkpoint")
            receipt["task_state"] = progress.get("task_state")
            receipt["active_card_context_deliveries"] = [
                {
                    "batch_id": delivery.get("batch_id"),
                    "parent_activation_receipt": delivery.get(
                        "parent_activation_receipt"),
                    **card_activation.activation_receipt_binding(delivery),
                }
                for delivery in (resume_activation_contexts or [])
            ]
            receipt["objective"] = contract.get("objective")
            receipt["exclusions"] = contract.get("exclusions")
            receipt["checkpoint"] = checkpoint if isinstance(
                checkpoint, dict) else None
            receipt["managed_deltas"] = result.get("managed_deltas", [])
            receipt["applied_delta_receipts"] = result.get(
                "applied_delta_receipts", [])
            receipt["pending_delta_applies"] = result.get(
                "pending_delta_applies", {})
            receipt["batch_close_recovery"] = result.get(
                "batch_close_recovery", {})
            receipt["writer_locks"] = result.get("writer_locks", [])
            task_runtime = result.get("task_runtime") or {}
            receipt["checkpoint_binding"] = task_runtime.get(
                "checkpoint_binding")
            receipt["pending_guidance"] = task_runtime.get(
                "pending_guidance", [])
            receipt["pending_amendments"] = task_runtime.get(
                "pending_amendments", [])
            # Derived boundary, never stored state: see
            # ``_last_reconciled_guidance_id``.
            receipt["last_reconciled_guidance_id"] = task_runtime.get(
                "last_reconciled_guidance_id")
            receipt["standards_revalidation_outstanding"] = result.get(
                "standards_revalidation_outstanding", {})
            receipt["standards_revalidation_barriers"] = result.get(
                "standards_revalidation_barriers", {})
            receipt["batch_work_specs"] = [
                {
                    "batch_id": item_id,
                    "work_spec_path": item.get("work_spec_path"),
                    "work_spec_sha256": item.get("work_spec_sha256"),
                }
                for item_id, item in sorted(
                    (result.get("items_by_id") or {}).items(),
                    key=lambda pair: (
                        pair[1].get("order", sys.maxsize), pair[0]),
                )
            ]
            candidate_context = result.get("maintenance_candidate_context")
            if isinstance(candidate_context, dict):
                receipt["maintenance_candidate_state"] = {
                    "sha256": candidate_context.get(
                        "candidate_state_sha256"),
                    "total": len(candidate_context.get("records") or []),
                    "selected_candidate_ids": candidate_context.get(
                        "selected_ids") or [],
                    "deferred_candidate_ids": candidate_context.get(
                        "deferred_ids") or [],
                }
            receipt["next_action"] = _resume_next_action(
                result, runtime_errors or [])
    return receipt


def _emit_json_receipts(receipts):
    """Write this run's receipt-shaped tool results to real stdout.

    ``--json`` publishes the receipts plus any transient Card payload that a
    Host must inject. The payload is deliberately absent from durable JSONL;
    its content-addressed manifest remains in the receipt. Otherwise this is
    not a schema projection:
    ``Tools/schemas/receipt.template.jsonl`` says in its own text that its
    examples are "not the complete set", and this tool's per-mode extension
    fields (the whole ``resume-status`` block, the maintenance and Standards
    revalidation contexts) are exactly the part a whitelist would drop.
    Serialization goes through the shared ``kblib.canonical_json_bytes``;
    this module owns no serializer. A run that produced no receipt writes
    nothing, so the settled rejection shape -- empty stdout, one line of
    reason on stderr, exit 1 -- is untouched.
    """
    if not receipts:
        return
    sys.stdout.write(
        kblib.canonical_json_bytes(list(receipts)).decode("utf-8") + "\n")


def _delivery_result(receipt, activation_context=None, readback_context=None,
                     piece_context=None, phase_context=None,
                     resume_activation_contexts=None):
    """Attach transient bytes to the tool result, never the receipt register."""
    emitted = dict(receipt)
    if activation_context and "activation_delivery_payload" in \
            activation_context:
        emitted["activation_delivery_payload"] = activation_context[
            "activation_delivery_payload"]
    if readback_context:
        emitted["readback_delivery_payload"] = readback_context.get(
            "readback_delivery_payload")
    if phase_context:
        emitted["activation_phase_payload"] = phase_context.get(
            "activation_phase_payload")
    if piece_context:
        emitted["activation_piece_payload"] = piece_context.get(
            "activation_piece_payload")
    if resume_activation_contexts:
        persisted = emitted.get("active_card_context_deliveries") or []
        emitted["active_card_context_deliveries"] = [
            {
                **dict(binding),
                # A v3 resume re-freezes the manifest for the new context and
                # names the pieces it must pull; the bytes travel one budgeted
                # piece at a time, never inside this status result.
                **({"activation_delivery_payload": delivery[
                    "activation_delivery_payload"]}
                   if "activation_delivery_payload" in delivery else {}),
            }
            for binding, delivery in zip(
                persisted, resume_activation_contexts)
        ]
    return emitted


def _write_receipt(root, relative_path, result, outcome, details, mode,
                   confirmation_receipt=None, runtime_errors=None,
                   maintenance_context=None,
                   standards_revalidation_context=None,
                   hub_page_candidates=None, activation_context=None,
                   readback_context=None, piece_context=None,
                   piece_ack_context=None, phase_context=None,
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
            piece_context=piece_context,
            piece_ack_context=piece_ack_context,
            phase_context=phase_context,
            phase_ack_context=phase_ack_context,
            resume_activation_contexts=resume_activation_contexts,
        )
        return _delivery_result(
            receipt, activation_context, readback_context, piece_context,
            phase_context, resume_activation_contexts)
    path = kblib.managed_repository_path(
        root, relative_path, ".cambium/receipts",
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
        piece_context=piece_context,
        piece_ack_context=piece_ack_context,
        phase_context=phase_context,
        phase_ack_context=phase_ack_context,
        resume_activation_contexts=resume_activation_contexts,
    )
    kblib.write_receipts(path, [receipt])
    return _delivery_result(
        receipt, activation_context, readback_context, piece_context,
        phase_context, resume_activation_contexts)










def _resume_recommendation(result, errors):
    locks = result.get("writer_locks") or []
    if locks:
        return ("verify that no writer process remains, reconcile Queue/Progress/"
                "deltas, and remove only a proven-stale lock; do not initialize "
                "or overwrite the runtime")
    if errors:
        return ("repair and reconcile the existing runtime before continuing; "
                "do not initialize or overwrite it")
    progress = result.get("progress") or {}
    task_state = progress.get("task_state")
    items = result.get("items_by_id") or {}
    pending_applies = result.get("pending_delta_applies") or {}
    current_applies = pending_applies.get("current") or []
    if (pending_applies.get("status") == "close-required" and
            len(current_applies) == 1):
        applied = current_applies[0]
        if task_state == "paused":
            return ("resume the paused task, then rerun resume-status and "
                    "close applied batch %s with receipt %s before any other "
                    "Queue/Coverage write" %
                    (applied.get("batch"),
                     applied.get("selected_receipt")))
        if task_state == "blocked":
            return ("resolve the blocked task state, then rerun resume-status "
                    "and close applied batch %s with receipt %s before any "
                    "other Queue/Coverage write" %
                    (applied.get("batch"),
                     applied.get("selected_receipt")))
        close_recovery = result.get("batch_close_recovery") or \
            _batch_close_recovery_inventory(result)
        selected = close_recovery.get("selected")
        if selected:
            return ("close applied batch %s with the recovered current bundle; "
                    "run: %s" %
                    (applied.get("batch"),
                     close_recovery.get("update_queue_command")))
        return ("run check_batch_close.py for applied batch %s before any "
                "Queue close, control input, another batch, or terminal "
                "archival" % applied.get("batch"))
    in_flight = [item_id for item_id, item in items.items()
                 if item.get("state") in ACTIVE_STATES]
    if task_state in ("complete", "cancelled"):
        return ("the existing task is terminal; preserve any unfinished batch "
                "or control records as incomplete history, then explicitly "
                "archive or roll over the runtime")
    if task_state in ("paused", "blocked"):
        return ("resume or resolve the existing %s task from its checkpoint; "
                "do not initialize a new task" % task_state)
    if task_state == "completion-candidate":
        return ("preserve the frozen candidate and run the Terminal Audit; "
                "do not activate new work or initialize a new task")
    incomplete_deltas = sorted(
        (entry for entry in result.get("managed_deltas", [])
         if entry.get("state") == "open" and
         entry.get("handoff_status") == "incomplete"),
        key=lambda entry: ((items.get(entry.get("batch")) or {}).get(
            "order", sys.maxsize), entry.get("batch") or ""),
    )
    if incomplete_deltas:
        return ("repair routed-gap settlement in the managed Delta for batch "
                "%s before batch review or merge-ready admission" %
                incomplete_deltas[0].get("batch"))
    actionable_revalidation = _actionable_revalidation_batches(result)
    if actionable_revalidation:
        return ("run the current boundary gates for batch %s, aggregate them "
                "with check_queue.py --require-revalidation, then consume "
                "that receipt before merge/apply/close" %
                actionable_revalidation[0])
    if in_flight:
        return ("resume the existing task and reconcile in-flight batch(es) %s "
                "before starting new work" % ",".join(sorted(in_flight)))
    queue_items = (result.get("queue") or {}).get("required_queue") or []
    if result.get("remaining") == 0 and queue_items:
        semantics = ((progress.get("contract") or {}).get(
            "completion_semantics") if isinstance(
                progress.get("contract"), dict) else None)
        if semantics == "maintenance":
            inventory = _maintenance_gate_inventory(result)
            if inventory.get("selected"):
                return (
                    "consume current maintenance completion gate %s with "
                    "update_task.py; do not regenerate state or Terminal Proof" %
                    inventory["selected"]
                )
            return (
                "run check_queue.py --require-maintenance-complete with the "
                "current budget-manifest, Ledger-advance, and watermark-advance "
                "receipts; then consume that gate with update_task.py"
            )
        return (
            "enter completion-candidate with a current require-complete "
            "receipt, then run the build Terminal Audit"
        )
    if result.get("ready"):
        return ("resume the existing task with ready batch(es) %s; do not "
                "initialize a new task" % ",".join(result["ready"]))
    if not queue_items:
        return ("resume the existing task by materializing its Required Queue; "
                "do not initialize a second task over it")
    return ("resume or resolve the existing task's recorded holds or dependencies; "
            "do not initialize a new task")




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
    print("  standards_version=%s" % queue.get("standards_version"))
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
    maintenance_inventory = _maintenance_gate_inventory(result)
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
    selected_gate_entry = (result.get("receipt_catalog") or {}).get(
        selected_gate_id) if selected_gate_id else None
    selected_gate = selected_gate_entry[1] if selected_gate_entry else {}
    print("  maintenance_candidates.run_id=%s" %
          (selected_gate.get("maintenance_run_id") or "none"))
    print("  maintenance_candidates.previous_receipt=%s" %
          (selected_gate.get("previous_maintenance_completion_receipt") or
           "none"))
    for state in ("queued", "open", "merge-ready", "closed", "cancelled"):
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
    locks = result.get("writer_locks") or []
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
            for state_name in ("coverage", "progress", "queue"):
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
    print("next_action=%s" % _resume_next_action(result, errors))
    print("recommended_action=%s" % _resume_recommendation(result, errors))




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
        "--deliver-activation-piece", metavar="BATCH_ID",
        help="deliver one frozen activation piece of BATCH_ID inside the "
             "protocol delivery budget")
    group.add_argument(
        "--ack-activation-piece", metavar="BATCH_ID",
        help="return one delivered piece nonce as same-context delivery "
             "evidence")
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
    parser.add_argument(
        "--piece", metavar="PIECE_ID",
        help="frozen activation piece selected with "
             "--deliver-activation-piece or --ack-activation-piece")
    parser.add_argument(
        "--piece-nonce", metavar="NONCE",
        help="nonce returned from the delivered piece, supplied to "
             "--ack-activation-piece")
    parser.add_argument(
        "--piece-delivery-receipt", metavar="RECEIPT_ID",
        help="delivery receipt the acknowledged nonce came from, supplied to "
             "--ack-activation-piece")
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
    _emit_json_receipts(produced)
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
    writer_locks = result.get("writer_locks") or []
    maintenance_context = None
    revalidation_context = None
    activation_context = None
    readback_context = None
    piece_context = None
    piece_ack_context = None
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
    if args.piece and not (args.deliver_activation_piece or
                           args.ack_activation_piece):
        errors.append("--piece is only valid with --deliver-activation-piece "
                      "or --ack-activation-piece")
    if args.deliver_activation_piece and not args.piece:
        errors.append("--deliver-activation-piece requires --piece")
    if args.ack_activation_piece and not (
            args.piece and args.piece_nonce and args.piece_delivery_receipt):
        errors.append(
            "--ack-activation-piece requires --piece, --piece-nonce and "
            "--piece-delivery-receipt")
    for flag, value in (("--piece-nonce", args.piece_nonce),
                        ("--piece-delivery-receipt",
                         args.piece_delivery_receipt)):
        if value and not args.ack_activation_piece:
            errors.append("%s is only valid with --ack-activation-piece" %
                          flag)
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

    if writer_locks:
        lock_paths = ", ".join(lock.get("path", "<unknown>")
                               for lock in writer_locks)
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
        close_recovery = _batch_close_recovery_inventory(result)
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
        elif result.get("progress", {}).get("task_state") in (
                "complete", "cancelled"):
            errors.append("task_state=%s is terminal and cannot activate batch %s" %
                          (result["progress"].get("task_state"),
                           args.require_ready))
        elif args.require_ready not in result["ready"]:
            reasons = list(dict(result["blocked"]).get(
                args.require_ready, ["not ready"]))
            if ("confirmation receipt absent" in reasons and
                    args.confirmation_receipt):
                confirmation_errors = []
                _require_receipt(
                    result.get("current_receipt_catalog",
                               result.get("receipt_catalog", {})),
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
        elif item.get("state") not in ("open", "merge-ready"):
            errors.append(
                "read-back delivery requires an open or merge-ready batch; "
                "%s is %s" % (args.deliver_readback, item.get("state")))
        else:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            activation_id = item.get("activation_receipt")
            entry = catalog.get(activation_id)
            activation_receipt = entry[1] if entry is not None else None
            if (not isinstance(activation_receipt, dict) or
                    activation_receipt.get("tool") != TOOL or
                    activation_receipt.get("tool_version") != TOOL_VERSION):
                errors.append(
                    "batch %s has no current Card-first activation receipt; "
                    "reopen or migrate it before read-back delivery" %
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
    elif not errors and (args.deliver_activation_piece or
                         args.ack_activation_piece):
        batch_id = args.deliver_activation_piece or args.ack_activation_piece
        item = result.get("items_by_id", {}).get(batch_id)
        activation_receipt = None
        if item is None:
            errors.append("requested batch %s does not exist" % batch_id)
        elif item.get("state") not in ("open", "merge-ready"):
            errors.append(
                "activation piece delivery requires an open or merge-ready "
                "batch; %s is %s" % (batch_id, item.get("state")))
        else:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            entry = catalog.get(item.get("activation_receipt"))
            activation_receipt = entry[1] if entry is not None else None
            if (not isinstance(activation_receipt, dict) or
                    activation_receipt.get("tool") != TOOL or
                    activation_receipt.get("tool_version") != TOOL_VERSION):
                errors.append(
                    "batch %s has no current Card-first activation receipt; "
                    "reopen it before piece delivery" % batch_id)
                activation_receipt = None
        if activation_receipt is not None and args.deliver_activation_piece:
            try:
                piece_context = card_activation.build_activation_piece(
                    result["root"],
                    card_activation.context_from_receipt(activation_receipt),
                    args.piece)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append("cannot deliver activation piece: %s" % exc)
        elif activation_receipt is not None:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            delivery_entry = catalog.get(args.piece_delivery_receipt)
            delivery = delivery_entry[1] if delivery_entry is not None else None
            if not isinstance(delivery, dict):
                errors.append(
                    "piece delivery receipt %s is absent from the current "
                    "catalog" % args.piece_delivery_receipt)
            elif delivery.get("piece_id") != args.piece:
                errors.append(
                    "piece delivery receipt %s does not deliver %s" %
                    (args.piece_delivery_receipt, args.piece))
            elif delivery.get("card_bundle_sha256") != activation_receipt.get(
                    "card_bundle_sha256"):
                errors.append(
                    "piece delivery receipt %s belongs to another activation "
                    "bundle" % args.piece_delivery_receipt)
            else:
                try:
                    piece_ack_context = card_activation.build_piece_ack(
                        dict(delivery, receipt_id=args.piece_delivery_receipt),
                        args.piece_nonce)
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("cannot acknowledge activation piece: %s" %
                                  exc)
    elif not errors and (args.deliver_phase or args.ack_activation_phase):
        batch_id = args.deliver_phase or args.ack_activation_phase
        item = result.get("items_by_id", {}).get(batch_id)
        activation_receipt = None
        if item is None:
            errors.append("requested batch %s does not exist" % batch_id)
        elif item.get("state") not in ("open", "merge-ready"):
            errors.append(
                "activation phase delivery requires an open or merge-ready "
                "batch; %s is %s" % (batch_id, item.get("state")))
        else:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
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
                    args.phase, args.phase_part)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append("cannot deliver activation phase: %s" % exc)
        elif activation_receipt is not None:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            delivery_entry = catalog.get(args.phase_delivery_receipt)
            delivery = delivery_entry[1] if delivery_entry is not None else None
            if not isinstance(delivery, dict):
                errors.append(
                    "phase delivery receipt %s is absent from the current "
                    "catalog" % args.phase_delivery_receipt)
            elif delivery.get("phase_id") != args.phase:
                errors.append(
                    "phase delivery receipt %s does not deliver %s" %
                    (args.phase_delivery_receipt, args.phase))
            elif delivery.get("part_index") != args.phase_part:
                errors.append(
                    "phase delivery receipt %s delivers part %s, not %s" %
                    (args.phase_delivery_receipt, delivery.get("part_index"),
                     args.phase_part))
            elif delivery.get("card_bundle_sha256") != activation_receipt.get(
                    "card_bundle_sha256"):
                errors.append(
                    "phase delivery receipt %s belongs to another activation "
                    "bundle" % args.phase_delivery_receipt)
            else:
                try:
                    phase_ack_context = card_activation.build_phase_ack(
                        dict(delivery, receipt_id=args.phase_delivery_receipt),
                        args.phase_nonce)
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("cannot acknowledge activation phase: %s" %
                                  exc)
    elif not errors and args.require_maintenance_complete:
        maintenance_errors, maintenance_context = \
            _maintenance_completion_gate_errors(
                os.path.realpath(os.path.abspath(args.root)),
                dict(result, receipt_catalog=result.get(
                    "current_receipt_catalog",
                    result.get("receipt_catalog", {}))),
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
        if task_state in (
                "planned", "active", "paused", "blocked",
                "completion-candidate"):
            candidates.append(
                "existing task_state=%s is non-terminal and must be resumed or "
                "resolved before a new task" % task_state
            )
        if active_ids and task_state not in ("complete", "cancelled"):
            candidates.append("in-flight batch(es) require resume: %s" %
                              ", ".join(sorted(active_ids)))
        if (held_ids and task_state not in
                ("paused", "blocked", "complete", "cancelled")):
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
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
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
    unsupported_reviewed = unsupported_reviewed_records(result.get("coverage"))
    if unsupported_reviewed:
        covering, near_miss = coverage_reviewed_era_exception(
            result.get("progress"), result.get("queue"),
            len(unsupported_reviewed))
        if covering is not None:
            # Covered by a bounded contract exception: the disposition
            # K02/01 offers, now readable.  Reported, never suppressed --
            # the operator sees the count falling toward the stated end.
            notes.append(
                "%d Coverage record(s) still claim authoring_status=reviewed "
                "with no gate_receipts, within the %d bounded by contract "
                "policy exception %s (%s:%s, K02/01)" %
                (len(unsupported_reviewed), covering.get("limit"),
                 covering.get("decision_id"), covering.get("scope_kind"),
                 covering.get("scope_ref")))
        else:
            candidates.append(
                "%d Coverage record(s) claim authoring_status=reviewed with "
                "no gate_receipts, so the era of the review that earned the "
                "status cannot be produced (K02/01); a declared migration "
                "must re-review, retire, or explicitly except them%s: %s" %
                (len(unsupported_reviewed),
                 "" if near_miss is None else " -- %s" % near_miss,
                 ", ".join(unsupported_reviewed[:5]) +
                 ("..." if len(unsupported_reviewed) > 5 else ""))
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
    mode = ("require-revalidation:%s" % args.require_revalidation
            if args.require_revalidation else
            ("require-ready:%s" % args.require_ready if args.require_ready else
            ("deliver-readback:%s:%s" % (
                args.deliver_readback, args.readback_rule)
             if args.deliver_readback else
            ("deliver-activation-piece:%s:%s" % (
                args.deliver_activation_piece, args.piece)
             if args.deliver_activation_piece else
            ("ack-activation-piece:%s:%s" % (
                args.ack_activation_piece, args.piece)
             if args.ack_activation_piece else
            ("deliver-phase:%s:%s:%d" % (
                args.deliver_phase, args.phase, args.phase_part)
             if args.deliver_phase else
            ("ack-activation-phase:%s:%s:%d" % (
                args.ack_activation_phase, args.phase, args.phase_part)
             if args.ack_activation_phase else
            ("require-complete" if args.require_complete else
             ("require-maintenance-complete"
              if args.require_maintenance_complete else
              ("resume-status" if args.resume_status else
               "consistency"))))))))))
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
            piece_context=piece_context,
            piece_ack_context=piece_ack_context,
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
