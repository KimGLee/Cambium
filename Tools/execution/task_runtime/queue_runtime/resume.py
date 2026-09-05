"""What can an interrupted session still do.

Read-only recovery projections over persisted close bundles, maintenance
gates and outstanding revalidations, reduced to one stable next-action token.
Nothing here writes: recovery advice that acted would be a second writer
racing whatever left the session interrupted.
"""

import shlex
import sys

import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.execution.task_runtime.task_runtime_action as task_runtime_action

from Tools.execution.task_runtime.queue_runtime.canon import (
    ACTIVE_STATES,
    BATCH_CLOSE_TOOL,
    TOOL,
    TOOL_VERSION,
)
from Tools.execution.task_runtime.queue_runtime.close_gate import close_gate_receipt_errors
from Tools.execution.task_runtime.queue_runtime.maintenance import (
    MaintenanceConsumerContext,
    maintenance_completion_gate_errors,
    maintenance_gate_time_errors,
)
from Tools.execution.task_runtime.queue_runtime.primitives import (
    timestamp_value,
    valid_timestamp,
)
from Tools.execution.task_runtime.queue_runtime.receipts import current_receipt_catalog
from Tools.execution.task_runtime.queue_runtime.revalidation import standards_revalidation_producer_eligibility


def maintenance_gate_inventory(result):
    """Classify persisted maintenance gates against the exact current bytes."""
    consumer_context = MaintenanceConsumerContext.from_runtime(result)
    progress = result.get("progress") or {}
    contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    if contract.get("completion_semantics") != "maintenance":
        return {"compatible": [], "stale": [], "selected": None}
    task_state = progress.get("task_state")
    bound_progress_sha = result.get("progress_sha256")
    if task_state == "complete":
        latest_transition = (result.get("task_runtime") or {}).get(
            "latest_receipt") or {}
        if (latest_transition.get("after_task_state") == "complete" and
                latest_transition.get("completion_semantics") ==
                "maintenance"):
            # A consumed gate intentionally binds the bytes immediately
            # before the terminal transition.  The transition receipt is the
            # durable bridge from those bytes to current Progress.
            bound_progress_sha = latest_transition.get(
                "before_progress_sha256")
    expected = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "check": "required_queue",
        "queue_check_mode": "require-maintenance-complete",
        "result": "pass",
        "invalidated_by": None,
        "task_id": progress.get("task_id"),
        "completion_semantics": "maintenance",
        "scope_version": contract.get("scope_version"),
        "upstream_revision_id": contract.get("upstream_revision_id"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"),
        "queue_revision": (result.get("queue") or {}).get("queue_revision"),
        "queue_state_revision":
            (result.get("queue") or {}).get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": bound_progress_sha,
        "remaining_required_work_units": 0,
    }
    compatible = []
    stale = []
    current_catalog = consumer_context.current_receipts
    for receipt_id, (_, receipt) in sorted(current_catalog.items()):
        if (receipt.get("tool") != TOOL or
                receipt.get("check") != "required_queue" or
                receipt.get("queue_check_mode") !=
                "require-maintenance-complete"):
            continue
        mismatches = [field for field, value in expected.items()
                      if receipt.get(field) != value]
        gate_errors = []
        context = None
        if not mismatches:
            gate_errors, context = maintenance_completion_gate_errors(
                consumer_context,
                receipt.get("budget_manifest_receipt"),
                receipt.get("ledger_advance_receipt"),
                receipt.get("watermark_advance_receipt"),
                allow_complete=task_state == "complete",
            )
            if context is not None:
                mismatches.extend(
                    field for field, value in context.items()
                    if receipt.get(field) != value
                )
            gate_errors.extend(maintenance_gate_time_errors(
                consumer_context, receipt))
        if mismatches or gate_errors or not valid_timestamp(
                receipt.get("checked_at")):
            stale.append({
                "receipt_id": receipt_id,
                "mismatches": sorted(set(mismatches)),
                "errors": gate_errors,
            })
        else:
            compatible.append({
                "receipt_id": receipt_id,
                "checked_at": receipt.get("checked_at"),
            })
    compatible.sort(key=lambda entry: (
        timestamp_value(entry["checked_at"]), entry["receipt_id"],
    ))
    selected = compatible[-1]["receipt_id"] if compatible else None
    if task_state == "complete":
        completion = progress.get("maintenance_completion")
        consumed = (completion.get("completion_gate_receipt")
                    if isinstance(completion, dict) else None)
        if consumed in {entry["receipt_id"] for entry in compatible}:
            # Once consumed, Progress—not register append order—owns which
            # compatible gate explains the terminal state.
            selected = consumed
    return {
        "compatible": compatible,
        "stale": stale,
        "selected": selected,
    }


def batch_close_transition_arguments(result, selected):
    """Return the one writer argument set bound by a recovered close bundle."""
    queue = result.get("queue") or {}
    return {
        "id": selected.get("batch"),
        "transition": "closed",
        "gate_receipt": selected.get("queue_consistency_receipt"),
        "close_gate_receipt": selected.get("close_gate_receipt"),
        "delta_apply_receipt": selected.get("delta_apply_receipt"),
        "expected_state_revision": queue.get("state_revision"),
        "expected_sha256": result.get("queue_sha256"),
        "actor_role": "integrator",
        "apply": True,
    }


def batch_close_update_command(result, selected):
    """Render the exact close command from the shared writer arguments."""
    arguments = batch_close_transition_arguments(result, selected)
    values = {
        "root": result.get("root"),
        "batch": arguments["id"],
        "queue_consistency": arguments["gate_receipt"],
        "close_gate": arguments["close_gate_receipt"],
        "delta_apply": arguments["delta_apply_receipt"],
        "state_revision": arguments["expected_state_revision"],
        "queue_sha": arguments["expected_sha256"],
    }
    return (
        "python3 Tools/update_queue.py {root} --id {batch} "
        "--transition closed --gate-receipt {queue_consistency} "
        "--close-gate-receipt {close_gate} "
        "--delta-apply-receipt {delta_apply} "
        "--expected-state-revision {state_revision} "
        "--expected-sha256 {queue_sha} --actor-role integrator --apply"
    ).format(**{
        key: shlex.quote(str(value)) for key, value in values.items()
    })


def batch_close_recovery_inventory(result):
    """Find a persisted, current-compatible close bundle for resume.

    This is a read-only projection over canonical state, the complete receipt
    catalog, and the live repository-content snapshot.  It never trusts the
    former producer's stdout.  Multiple valid bundles are ordered by their
    checked instant and then receipt ID, producing one deterministic latest
    choice.  Invalid or stale lookalikes remain visible but are never selected.
    """
    inventory = {
        "status": "not-applicable",
        "batch": None,
        "repository_snapshot_sha256": None,
        "compatible": [],
        "stale": [],
        "selected": None,
        "selection_rule": "latest-checked-at-then-receipt-id",
        "update_queue_command": None,
        "errors": [],
    }
    if result.get("_writer_locks"):
        inventory["status"] = "writer-lock"
        return inventory
    pending = result.get("pending_delta_applies") or {}
    current = pending.get("current") or []
    if pending.get("status") == "repair":
        inventory["status"] = "runtime-repair"
        return inventory
    if pending.get("status") != "close-required" or len(current) != 1:
        return inventory

    applied = current[0]
    batch = applied.get("batch")
    inventory["batch"] = batch
    item = (result.get("items_by_id") or {}).get(batch)
    if not isinstance(item, dict) or item.get("state") != "merge-ready":
        inventory["status"] = "runtime-repair"
        inventory["errors"].append(
            "current applied batch is not merge-ready")
        return inventory
    try:
        snapshot = kblib.repository_snapshot_sha256(result.get("root"))
    except (OSError, ValueError) as exc:
        inventory["status"] = "snapshot-unavailable"
        inventory["errors"].append(str(exc))
        return inventory
    inventory["repository_snapshot_sha256"] = snapshot

    compatible_apply_ids = set(applied.get("compatible_receipts") or [])
    catalog = current_receipt_catalog(result)
    for receipt_id, (relative, receipt) in sorted(catalog.items()):
        if not isinstance(receipt, dict):
            continue
        if not (receipt.get("tool") == BATCH_CLOSE_TOOL and
                receipt.get("check") == "batch_close_gate" and
                (receipt.get("target") == batch or
                 receipt.get("batch_id") == batch)):
            continue
        queue_consistency = receipt.get("queue_consistency_receipt")
        delta_apply = receipt.get("delta_apply_receipt")
        candidate_errors = []
        checked_at = receipt.get("checked_at")
        checked_value = timestamp_value(checked_at)
        if checked_value is None:
            candidate_errors.append(
                "checked_at must be a timezone-aware RFC 3339 timestamp")
        if delta_apply not in compatible_apply_ids:
            candidate_errors.append(
                "delta_apply_receipt is not current-compatible")
        candidate_errors.extend(close_gate_receipt_errors(
            catalog, receipt_id,
            item_id=batch,
            root=result.get("root"),
            task_id=(result.get("queue") or {}).get("task_id"),
            queue_revision=(result.get("queue") or {}).get("queue_revision"),
            queue_state_revision=(result.get("queue") or {}).get(
                "state_revision"),
            required_queue_sha256=result.get("queue_sha256"),
            coverage_ledger_sha256=result.get("coverage_sha256"),
            progress_ledger_sha256=result.get("progress_sha256"),
            delta_sha256=item.get("delta_sha256"),
            queue_consistency_receipt=queue_consistency,
            delta_apply_receipt=delta_apply,
            work_spec_path=item.get("work_spec_path"),
            work_spec_sha256=item.get("work_spec_sha256"),
            manifest=item.get("manifest"),
            selected_profile_manifest=(result.get("queue") or {}).get(
                "selected_profile_manifest"),
            profile_snapshot_sha256=(result.get(
                "_profile_authorized_view") or {}).get(
                    "profile_snapshot_sha256"),
            profile_contract_fingerprint=(result.get(
                "_profile_authorized_view") or {}).get(
                    "profile_contract_fingerprint"),
            profile_load_inputs_sha256=(result.get(
                "_profile_authorized_view") or {}).get(
                    "profile_load_inputs_sha256"),
            profile_evaluation=(result.get(
                "_profile_authorized_view") or {}).get("_evaluation"),
            current_repository_snapshot_sha256=snapshot,
        ))
        entry = {
            "batch": batch,
            "receipt_path": relative,
            "checked_at": checked_at,
            "queue_consistency_receipt": queue_consistency,
            "close_gate_receipt": receipt_id,
            "delta_apply_receipt": delta_apply,
            "repository_snapshot_sha256": receipt.get(
                "merged_snapshot_sha256"),
        }
        if candidate_errors:
            entry["errors"] = sorted(set(candidate_errors))
            inventory["stale"].append(entry)
        else:
            entry["_checked_value"] = checked_value
            inventory["compatible"].append(entry)

    inventory["compatible"].sort(key=lambda entry: (
        entry["_checked_value"], entry["close_gate_receipt"]))
    inventory["stale"].sort(key=lambda entry: entry["close_gate_receipt"])
    if inventory["compatible"]:
        selected = dict(inventory["compatible"][-1])
        selected.pop("_checked_value", None)
        for entry in inventory["compatible"]:
            entry.pop("_checked_value", None)
        inventory["selected"] = selected
        inventory["status"] = "ready-to-close"
        inventory["update_queue_command"] = batch_close_update_command(
            result, selected)
    else:
        inventory["status"] = "gate-required"
    return inventory


def actionable_revalidation_batches(result):
    """Outstanding batches whose aggregate this producer would still admit.

    ``standards_revalidation_outstanding`` reports every batch whose plan
    bindings are unconsumed, terminal ones included, because that is a true
    statement about this runtime's history and dropping it would hide it.
    A *recommended action* is a different claim: it asserts the named tool
    would run.  So this filters on
    :func:`standards_revalidation_producer_eligibility` -- the same
    predicate ``--require-revalidation`` itself applies -- rather than on a
    second, parallel notion of eligibility that could drift from it.  A
    token naming a batch the producer declines is not a recovery action; it
    is a dead end that masks the real next step for as long as the runtime
    lives.
    """
    outstanding = result.get("standards_revalidation_outstanding") or {}
    items = result.get("items_by_id") or {}
    return sorted(
        (batch_id for batch_id in outstanding
         if standards_revalidation_producer_eligibility(
             result, batch_id) is None),
        key=lambda batch_id: (
            (items.get(batch_id) or {}).get("order", sys.maxsize), batch_id),
    )


def resume_next_action(result, errors):
    """Return one stable machine-readable recovery action token."""
    if result.get("_writer_locks"):
        return task_runtime_action.resume_action_token(
            "reconcile-interrupted-write")
    if errors:
        return task_runtime_action.resume_action_token("repair-runtime")
    progress = result.get("progress") or {}
    task_state = progress.get("task_state")
    items = result.get("items_by_id") or {}
    applied = [entry for entry in result.get("applied_delta_receipts", [])
               if entry.get("selected_receipt") and
               (items.get(entry.get("batch")) or {}).get("hold_state") ==
               "none"]
    if applied:
        selected = applied[0]
        if task_state == "paused":
            return task_runtime_action.resume_action_token(
                "resume-paused-task")
        if task_state == "blocked":
            return task_runtime_action.resume_action_token(
                "resolve-blocked-task")
        recovery = result.get("batch_close_recovery") or \
            batch_close_recovery_inventory(result)
        if recovery.get("status") in (
                "snapshot-unavailable", "runtime-repair"):
            return task_runtime_action.resume_action_token("repair-runtime")
        bundle = recovery.get("selected")
        if bundle:
            return task_runtime_action.resume_action_token(
                "close-applied-batch",
                batch_id=bundle["batch"],
                queue_consistency_receipt=
                    bundle["queue_consistency_receipt"],
                close_gate_receipt=bundle["close_gate_receipt"],
                delta_apply_receipt=bundle["delta_apply_receipt"],
            )
        return task_runtime_action.resume_action_token(
            "run-batch-close-gate-request", batch_id=selected["batch"])
    if task_state in runtime_state_contract.TASK_TERMINAL_STATES:
        return task_runtime_action.resume_action_token(
            "archive-terminal-runtime")
    runtime = result.get("task_runtime") or {}
    if runtime.get("pending_guidance") or runtime.get("pending_amendments"):
        return task_runtime_action.resume_action_token(
            "reconcile-control-input")
    if task_state == "paused":
        return task_runtime_action.resume_action_token("resume-paused-task")
    if task_state == "blocked":
        return task_runtime_action.resume_action_token("resolve-blocked-task")
    incomplete_deltas = sorted(
        (entry for entry in result.get("managed_deltas", [])
         if entry.get("state") == "open" and
         entry.get("handoff_status") == "incomplete"),
        key=lambda entry: ((items.get(entry.get("batch")) or {}).get(
            "order", sys.maxsize), entry.get("batch") or ""),
    )
    if incomplete_deltas:
        return task_runtime_action.resume_action_token(
            "repair-delta-settlement",
            batch_id=incomplete_deltas[0].get("batch"))
    actionable_revalidation = actionable_revalidation_batches(result)
    if actionable_revalidation:
        return task_runtime_action.resume_action_token(
            "run-standards-revalidation",
            batch_id=actionable_revalidation[0])
    if task_state == "completion-candidate":
        return task_runtime_action.resume_action_token("run-terminal-audit")
    merge_ready = sorted(
        (item for item in items.values()
         if item.get("state") == "merge-ready" and
         item.get("hold_state") == "none"),
        key=lambda item: (item.get("order", sys.maxsize), item.get("id", "")),
    )
    if merge_ready:
        return task_runtime_action.resume_action_token(
            "apply-delta", batch_id=merge_ready[0]["id"])
    handoff_ids = {
        entry.get("batch") for entry in result.get("managed_deltas", [])
        if entry.get("state") == "open" and
        entry.get("handoff_status") == "candidate"
    }
    handoffs = sorted(
        (item for item_id, item in items.items()
         if item_id in handoff_ids and item.get("hold_state") == "none"),
        key=lambda item: (item.get("order", sys.maxsize), item.get("id", "")),
    )
    if handoffs:
        return task_runtime_action.resume_action_token(
            "admit-delta", batch_id=handoffs[0]["id"])
    in_flight = sorted(
        item_id for item_id, item in items.items()
        if item.get("state") in ACTIVE_STATES
    )
    if in_flight:
        return task_runtime_action.resume_action_token(
            "resume-in-flight-batches", batch_ids=",".join(in_flight))
    if result.get("remaining") == 0 and items:
        contract = progress.get("contract") if isinstance(
            progress.get("contract"), dict) else {}
        if contract.get("completion_semantics") == "maintenance":
            inventory = maintenance_gate_inventory(result)
            if inventory.get("selected"):
                return task_runtime_action.resume_action_token(
                    "complete-maintenance-task",
                    receipt_id=inventory["selected"])
            return task_runtime_action.resume_action_token(
                "run-maintenance-completion-gate")
        return task_runtime_action.resume_action_token(
            "enter-completion-candidate")
    if result.get("ready"):
        return task_runtime_action.resume_action_token(
            "activate-ready-batch", batch_ids=",".join(result["ready"]))
    if not items:
        return task_runtime_action.resume_action_token(
            "materialize-required-queue")
    return task_runtime_action.resume_action_token(
        "resolve-holds-dependencies")
