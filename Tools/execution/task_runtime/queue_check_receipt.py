"""Build Queue consistency receipts from an evaluated runtime snapshot.

This module owns the reusable receipt projection.  It does not validate or
mutate Queue state: callers must first validate the exact bytes they hold and
then pass that result here.  Keeping the projection outside ``check_queue``
lets other producers reuse the contract without importing a CLI entrypoint.
"""

import sys

import Tools.execution.context_delivery.card_activation as card_activation
from Tools.execution.evidence import receipt_type_contract
import Tools.platform.common.kblib as kblib
from Tools.execution.task_runtime import queue_runtime


RECEIPT_TYPE_ID = "required-queue-gate-receipt-v1"
STANDARDS_REVALIDATION_RECEIPT_TYPE_ID = \
    "standards-revalidation-queue-gate-receipt-v1"


def current_receipt_errors(record, *, root=None):
    """Validate the current Queue Gate producer envelope."""
    errors = receipt_type_contract.base_receipt_errors(
        record,
        receipt_type_id=RECEIPT_TYPE_ID,
        tool=queue_runtime.TOOL,
        tool_version=queue_runtime.TOOL_VERSION,
        checks=queue_runtime.GATE_CHECK,
    )
    if not isinstance(record, dict):
        return errors
    if str(record.get("queue_check_mode", "")).startswith(
            "require-revalidation:"):
        errors.append("ordinary Queue Gate type cannot carry revalidation mode")
    if not isinstance(record.get("queue_check_mode"), str):
        errors.append("Queue Gate Receipt requires queue_check_mode")
    gate_id = queue_runtime.queue_gate_id_for_mode(
        record.get("queue_check_mode"))
    if gate_id is not None and record.get("gate_id") != gate_id:
        errors.append("Queue Gate Receipt gate_id does not match its mode")
    return errors


def current_standards_revalidation_receipt_errors(record, *, root=None):
    """Validate the distinct Standards-revalidation Queue aggregate."""
    errors = receipt_type_contract.base_receipt_errors(
        record,
        receipt_type_id=STANDARDS_REVALIDATION_RECEIPT_TYPE_ID,
        tool=queue_runtime.TOOL,
        tool_version=queue_runtime.TOOL_VERSION,
        checks=queue_runtime.GATE_CHECK,
    )
    if not isinstance(record, dict):
        return errors
    mode = record.get("queue_check_mode")
    if not isinstance(mode, str) or not mode.startswith(
            "require-revalidation:"):
        errors.append("Standards revalidation Receipt requires revalidation mode")
    if record.get("gate_id") != "standards-revalidation":
        errors.append("gate_id must identify standards-revalidation")
    return errors


def make_check_receipt(result, outcome, details, mode,
                       confirmation_receipt=None, runtime_errors=None,
                       maintenance_context=None,
                       standards_revalidation_context=None,
                       hub_page_candidates=None,
                       activation_context=None,
                       readback_context=None,
                       phase_context=None,
                       phase_ack_context=None,
                       resume_activation_contexts=None):
    """Build the canonical receipt for one already-evaluated Queue result."""
    receipt_type_id = (STANDARDS_REVALIDATION_RECEIPT_TYPE_ID
                       if isinstance(mode, str) and
                       mode.startswith("require-revalidation:")
                       else RECEIPT_TYPE_ID)
    receipt = kblib.make_receipt(
        queue_runtime.TOOL,
        queue_runtime.TOOL_VERSION,
        queue_runtime.GATE_CHECK,
        queue_runtime.QUEUE_PATH,
        outcome,
        details,
        1,
        receipt_type_id=receipt_type_id,
    )
    if result.get("queue_sha256"):
        receipt["queue_check_mode"] = mode
        gate_id = queue_runtime.queue_gate_id_for_mode(mode)
        if gate_id is not None:
            receipt["gate_id"] = gate_id
        if confirmation_receipt:
            receipt["confirmation_receipt"] = confirmation_receipt
        receipt["required_queue_sha256"] = result["queue_sha256"]
        receipt["coverage_ledger_sha256"] = result.get("coverage_sha256")
        receipt["progress_ledger_sha256"] = result.get("progress_sha256")
        receipt["queue_revision"] = result["queue"].get("queue_revision")
        receipt["queue_state_revision"] = result["queue"].get(
            "state_revision")
        receipt["remaining_required_work_units"] = result.get("remaining")
        receipt["task_id"] = result["queue"].get("task_id")
        receipt["upstream_revision_id"] = result["queue"].get(
            "upstream_revision_id")
        receipt["selected_profile_manifest"] = result["queue"].get(
            "selected_profile_manifest")
        if mode.startswith("require-ready:"):
            receipt["hub_page_candidates"] = list(hub_page_candidates or [])
            if activation_context:
                receipt.update(card_activation.activation_receipt_binding(
                    activation_context))
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
            receipt["_writer_locks"] = result.get("_writer_locks", [])
            task_runtime = result.get("task_runtime") or {}
            receipt["checkpoint_binding"] = task_runtime.get(
                "checkpoint_binding")
            receipt["pending_guidance"] = task_runtime.get(
                "pending_guidance", [])
            receipt["pending_amendments"] = task_runtime.get(
                "pending_amendments", [])
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
            receipt["next_action"] = queue_runtime.resume_next_action(
                result, runtime_errors or [])
    return receipt


__all__ = ["make_check_receipt"]
