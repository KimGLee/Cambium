#!/usr/bin/env python3
"""Apply one optimistic, receipt-backed task lifecycle transition.

Task state belongs to the Progress Ledger.  This tool is its only ordinary
writer.  It never edits Queue or Coverage bytes, but it compare-and-swaps all
three live fingerprints under the shared runtime writer lock so a restart can
distinguish a completed transition from an interrupted one.

The default is a dry run.  ``--apply`` requires the integrator role and exact
Progress and Required Queue fingerprints observed by the caller.
"""

import contextlib
import copy
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_activation
import check_queue
import kblib
import profile_contract
import runtime_paths
import runtime_state_contract


TOOL = "update_task"
TOOL_VERSION = "1.1.0"
TERMINAL_PROOF_TOOL = "check_proof"
TERMINAL_PROOF_TOOL_VERSION = "1.18.0"
TERMINAL_PROOF_GATE_ID = "terminal-proof"
RECEIPT_PATH = runtime_paths.TASK_TRANSITION_RECEIPT_PATH
PROFILE_BINDING_FIELDS = profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS
TERMINAL_BINDING_FIELDS = PROFILE_BINDING_FIELDS + (
    "repository_snapshot_sha256",
)
def _emit_json_receipts(receipts):
    """Write the exact receipt objects this run produced to real stdout.

    ``--json`` publishes the receipts themselves, not a projection of them:
    ``Tools/schemas/receipt.template.jsonl`` says in its own text that its
    examples are "not the complete set", and this tool's transition bindings
    are exactly what a whitelist would drop. Serialization goes through the
    shared ``kblib.canonical_json_bytes``; this module owns no serializer.
    Only a run that actually applied the transition writes here: a dry run
    plans a receipt but publishes none, so its stdout stays empty and the
    plan stays on stderr. That also leaves the settled rejection shape --
    empty stdout, one line of reason on stderr, exit 1 -- exactly as it was.
    """
    if not receipts:
        return
    sys.stdout.write(
        kblib.canonical_json_bytes(list(receipts)).decode("utf-8") + "\n")


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _receipt(result, receipt_id, label, expected):
    catalog = check_queue.current_receipt_catalog(result)
    entry = catalog.get(receipt_id)
    if entry is None:
        raise ValueError("%s receipt %r does not exist" % (label, receipt_id))
    receipt = entry[1]
    requirements = {"result": "pass", "invalidated_by": None}
    requirements.update(expected)
    for field, value in requirements.items():
        if receipt.get(field) != value:
            raise ValueError(
                "%s receipt %s has %s=%r, expected %r" %
                (label, receipt_id, field, receipt.get(field), value)
            )
    return receipt


def _historical_receipt(result, receipt_id, label, expected):
    """Resolve immutable transition history from the unfiltered catalog.

    A Standards adoption removes invalidated evidence only from new authorization.
    Existing task-transition records must remain readable so monotonic-time
    and hash-chain checks do not reinterpret history as missing.
    """
    catalog = check_queue.historical_receipt_catalog(result)
    entry = catalog.get(receipt_id)
    if entry is None:
        raise ValueError("%s receipt %r does not exist" % (label, receipt_id))
    receipt = entry[1]
    requirements = {"result": "pass", "invalidated_by": None}
    requirements.update(expected)
    for field, value in requirements.items():
        if receipt.get(field) != value:
            raise ValueError(
                "%s receipt %s has %s=%r, expected %r" %
                (label, receipt_id, field, receipt.get(field), value)
            )
    return receipt


def _pending_controls(progress):
    pending_guidance = []
    guidance = progress.get("guidance_queue")
    if not isinstance(guidance, list):
        raise ValueError("Progress guidance_queue must be an explicit list")
    for index, entry in enumerate(guidance):
        if not isinstance(entry, dict):
            raise ValueError("Progress guidance_queue[%d] must be a mapping" %
                             index)
        if (entry.get("status") not in
                runtime_state_contract.FINAL_GUIDANCE_STATUSES):
            pending_guidance.append(
                str(entry.get("guidance_id") or "#%d" % index))

    pending_amendments = []
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        raise ValueError("Progress amendments must be an explicit list")
    for index, entry in enumerate(amendments):
        if not isinstance(entry, dict):
            raise ValueError("Progress amendments[%d] must be a mapping" %
                             index)
        status = entry.get("status")
        if not runtime_state_contract.amendment_is_final(
                status, entry.get("writeback_done")):
            pending_amendments.append(str(entry.get("id") or "#%d" % index))
    return pending_guidance, pending_amendments


def _latest_transition_timestamp(result, progress):
    history = progress.get("task_transition_receipts")
    if history is None:
        history = []
    if not isinstance(history, list) or not all(_nonempty(value)
                                                for value in history):
        raise ValueError("Progress task_transition_receipts must be a list of IDs")
    if len(history) != len(set(history)):
        raise ValueError("Progress task_transition_receipts must be unique")
    latest = None
    for receipt_id in history:
        receipt = _historical_receipt(result, receipt_id, "task transition", {
            "tool": TOOL,
            "tool_version": TOOL_VERSION,
            "check": "task_transition",
            "task_id": progress.get("task_id"),
            "actor_role": "integrator",
            "completion_semantics":
                (progress.get("contract") or {}).get("completion_semantics"),
        })
        checked_at = receipt.get("checked_at")
        if not check_queue.valid_timestamp(checked_at):
            raise ValueError("task transition %s has invalid checked_at" %
                             receipt_id)
        checked_time = check_queue.timestamp_value(checked_at)
        if latest is not None and checked_time < latest:
            raise ValueError("task transition timestamps are not monotonic")
        latest = checked_time
    return latest, history


def _completion_gate_receipt(result, receipt_id):
    queue = result["queue"]
    return _receipt(result, receipt_id, "Queue completion gate", {
        "tool": check_queue.TOOL,
        "tool_version": check_queue.TOOL_VERSION,
        "gate_id": "required-queue-completion",
        "check": "required_queue",
        "queue_check_mode": "require-complete",
        "task_id": queue.get("task_id"),
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": result.get("progress_sha256"),
        "remaining_required_work_units": 0,
    })


def _terminal_proof_receipt(result, receipt_id):
    progress = result["progress"]
    contract = progress.get("contract") or {}
    receipt = _receipt(result, receipt_id, "Terminal Proof", {
        "tool": TERMINAL_PROOF_TOOL,
        "tool_version": TERMINAL_PROOF_TOOL_VERSION,
        "gate_id": TERMINAL_PROOF_GATE_ID,
        "check": "proof-check-summary",
        "task_id": progress.get("task_id"),
        "scope_version": contract.get("scope_version"),
        "contract_version": contract.get("contract_version"),
        "standards_version": contract.get("standards_version"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": result.get("progress_sha256"),
        "required_queue_path": check_queue.QUEUE_PATH,
        "queue_revision": result["queue"].get("queue_revision"),
        "queue_state_revision": result["queue"].get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "remaining_required_work_units": 0,
    })
    proof_path = receipt.get("terminal_proof_path")
    proof_sha = receipt.get("terminal_proof_sha256")
    if not _nonempty(proof_path) or not check_queue.SHA256_RE.fullmatch(
            str(proof_sha)):
        raise ValueError("Terminal Proof receipt lacks canonical proof path/SHA")
    if receipt.get("target") != proof_path:
        raise ValueError("Terminal Proof receipt target must equal proof path")
    try:
        absolute = kblib.managed_repository_path(
            result["root"], proof_path, runtime_paths.RECEIPT_ROOT,
            suffixes=(".yaml", ".yml"), must_exist=True,
        )
    except (OSError, ValueError) as exc:
        raise ValueError("Terminal Proof path is unsafe or missing: %s" % exc)
    if kblib.sha256_file(absolute) != proof_sha:
        raise ValueError("Terminal Proof receipt does not match current proof bytes")
    queue_check = receipt.get("queue_check_receipt")
    if not _nonempty(queue_check):
        raise ValueError("Terminal Proof receipt lacks queue_check_receipt")
    _completion_gate_receipt(result, queue_check)

    # ``check_proof`` 1.17 binds its pass verdict to one authorized Profile
    # closure plus the root-owned inputs that define profile-load. Completion
    # is the current-use consumer of that verdict: all three digests must match
    # one evaluation of the exact selected manifest frozen in the Task
    # Contract. A completed task is replayed historically by ``check_queue``;
    # this is therefore the last boundary at which today's Profile may be used
    # to authorize the state transition.
    for field in profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS:
        if not check_queue.SHA256_RE.fullmatch(str(receipt.get(field))):
            raise ValueError(
                "Terminal Proof receipt lacks canonical %s" % field
            )
    selected_manifest = contract.get("selected_profile_manifest")
    profile_evidence = result.get("_profile_authorized_view")
    if not isinstance(profile_evidence, dict):
        raise ValueError(
            "current runtime exposed no authorized selected Profile view"
        )
    profile_errors = \
        check_queue.profile_load_authorized_view_currency_errors(
            result["root"], profile_evidence)
    if profile_errors:
        raise ValueError(
            "current selected Profile authorization is stale: %s" %
            "; ".join(profile_errors)
        )
    if profile_evidence.get("selected_profile_manifest") != selected_manifest:
        raise ValueError(
            "profile-load evidence selected manifest %r, expected %r" %
            (profile_evidence.get("selected_profile_manifest"),
             selected_manifest)
        )
    for field in profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS:
        if receipt.get(field) != profile_evidence.get(field):
            raise ValueError(
                "Terminal Proof receipt %s does not match the current "
                "selected Profile" % field
            )
    repository_snapshot = receipt.get("repository_snapshot_sha256")
    if not check_queue.SHA256_RE.fullmatch(str(repository_snapshot)):
        raise ValueError(
            "Terminal Proof receipt lacks canonical "
            "repository_snapshot_sha256"
        )
    try:
        current_repository_snapshot = kblib.repository_snapshot_sha256(
            result["root"])
    except (OSError, ValueError) as exc:
        raise ValueError(
            "current repository snapshot is unreadable: %s" % exc
        )
    if current_repository_snapshot != repository_snapshot:
        raise ValueError(
            "Terminal Proof receipt repository_snapshot_sha256 does not "
            "match the current repository"
        )
    return receipt


def _terminal_binding_from_receipt(result, terminal_receipt):
    """Freeze the exact Profile and repository view one proof binds."""
    return {
        "selected_profile_manifest":
            (result["progress"].get("contract") or {}).get(
                "selected_profile_manifest"),
        "profile_snapshot_sha256":
            terminal_receipt.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint":
            terminal_receipt.get("profile_contract_fingerprint"),
        "profile_load_inputs_sha256":
            terminal_receipt.get("profile_load_inputs_sha256"),
        "repository_snapshot_sha256":
            terminal_receipt.get("repository_snapshot_sha256"),
    }


def _require_transaction_currency(root, authority, phase,
                                  terminal_binding=None):
    """CAS one transaction's authority and optional Terminal repository."""
    check_queue.require_runtime_authority_current(root, authority, phase)
    if terminal_binding is None:
        return
    try:
        repository_snapshot = kblib.repository_snapshot_sha256(root)
    except (OSError, ValueError) as exc:
        raise ValueError(
            "%s repository snapshot is unreadable: %s" % (phase, exc)
        )
    if repository_snapshot != terminal_binding.get(
            "repository_snapshot_sha256"):
        raise ValueError(
            "%s repository_snapshot_sha256 changed after locked validation" %
            phase
        )


def _task_transition_abort_receipt(result, transition_receipt):
    """Build durable recovery evidence for an attempted task transition."""
    progress = result["progress"]
    history = progress.get("task_transition_receipts") or []
    identity = {
        "task_id": progress.get("task_id"),
        "standards_version":
            (progress.get("contract") or {}).get("standards_version"),
        "selected_profile_manifest":
            (progress.get("contract") or {}).get(
                "selected_profile_manifest"),
    }
    abort = kblib.make_receipt(
        TOOL, TOOL_VERSION, "task_transition_abort",
        progress.get("task_id"), "fail",
        "Task transition aborted and pre-transition Progress restored",
        len(history) + 2, identity=identity,
    )
    abort.update({
        "transaction_id": transition_receipt["receipt_id"],
        "aborted_task_transition_receipt":
            transition_receipt["receipt_id"],
        "before_progress_sha256":
            transition_receipt["before_progress_sha256"],
        "planned_after_progress_sha256":
            transition_receipt["after_progress_sha256"],
        "actor_role": "integrator",
    })
    return abort


def _maintenance_completion_receipt(result, receipt_id):
    progress = result["progress"]
    receipt = _receipt(result, receipt_id, "maintenance completion gate", {
        "tool": check_queue.TOOL,
        "tool_version": check_queue.TOOL_VERSION,
        "gate_id": "maintenance-completion",
        "check": "required_queue",
        "queue_check_mode": "require-maintenance-complete",
        "task_id": progress.get("task_id"),
        "completion_semantics": "maintenance",
        "scope_version": (progress.get("contract") or {}).get(
            "scope_version"),
        "standards_version": (progress.get("contract") or {}).get(
            "standards_version"),
        "selected_profile_manifest": (progress.get("contract") or {}).get(
            "selected_profile_manifest"),
        "queue_revision": result["queue"].get("queue_revision"),
        "queue_state_revision": result["queue"].get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": result.get("progress_sha256"),
        "remaining_required_work_units": 0,
    })
    for field in (
            "budget_manifest_receipt", "ledger_advance_receipt",
            "watermark_advance_receipt"):
        if not _nonempty(receipt.get(field)):
            raise ValueError(
                "maintenance completion receipt lacks %s" % field
            )
    evidence_errors, expected_context = \
        check_queue.maintenance_completion_gate_errors(
            result["root"], result,
            receipt["budget_manifest_receipt"],
            receipt["ledger_advance_receipt"],
            receipt["watermark_advance_receipt"],
        )
    if evidence_errors:
        raise ValueError(
            "maintenance completion evidence is stale or invalid: %s" %
            "; ".join(evidence_errors)
        )
    time_errors = check_queue.maintenance_gate_time_errors(result, receipt)
    if time_errors:
        raise ValueError(
            "maintenance completion gate is stale: %s" %
            "; ".join(time_errors)
        )
    for field, expected in expected_context.items():
        if receipt.get(field) != expected:
            raise ValueError(
                "maintenance completion receipt has %s=%r, expected %r" %
                (field, receipt.get(field), expected)
            )
    for field in (
            "terminal_batch_ids", "applicable_batch_gate_receipts",
            "batch_close_gate_receipts"):
        value = receipt.get(field)
        if (not isinstance(value, list) or
                not all(_nonempty(item) for item in value) or
                len(value) != len(set(value))):
            raise ValueError(
                "maintenance completion receipt %s must be a unique "
                "non-empty-string list" % field
            )
    return receipt


def build_task_transition(result, after_state, at, summary, evidence_receipt,
                          *, queue=None, queue_text=None,
                          first_open_batch_id=None,
                          terminal_proof_receipt=None,
                          maintenance_completion_receipt=None):
    """Return ``(Progress, text, receipt)`` for one valid task transition.

    ``queue``/``queue_text`` and ``first_open_batch_id`` let ``update_queue``
    reuse this exact owner when the first batch opening atomically changes
    planned -> active. The ordinary task-state CLI cannot claim that edge.
    """
    progress = result["progress"]
    contract = progress.get("contract") or {}
    completion_semantics = contract.get("completion_semantics")
    if completion_semantics not in check_queue.COMPLETION_SEMANTICS:
        raise ValueError(
            "Progress contract must declare completion_semantics build or "
            "maintenance"
        )
    before_state = progress.get("task_state")
    if not runtime_state_contract.task_transition_is_authorized(
            completion_semantics, before_state, after_state):
        raise ValueError("illegal task transition %s -> %s" %
                         (before_state, after_state))
    at_value = check_queue.timestamp_value(at)
    if at_value is None:
        raise ValueError("transition time must be timezone-aware RFC 3339")
    latest_at, history = _latest_transition_timestamp(result, progress)
    if latest_at is not None and at_value < latest_at:
        raise ValueError("task transition time precedes existing history")
    checkpoint = progress.get("checkpoint")
    if isinstance(checkpoint, dict):
        recorded_at = checkpoint.get("recorded_at")
        if recorded_at is not None:
            recorded_value = check_queue.timestamp_value(recorded_at)
            if recorded_value is None:
                raise ValueError("existing checkpoint recorded_at is invalid")
            if at_value < recorded_value:
                raise ValueError("task transition time precedes checkpoint")

    queue = queue or result["queue"]
    if queue_text is None:
        queue_text = kblib.canonical_yaml(queue)
    queue_sha = kblib.sha256_bytes(queue_text)

    if before_state == "planned" and after_state == "active":
        if not _nonempty(first_open_batch_id):
            raise ValueError(
                "first task activation is owned by update_queue.py while "
                "opening the first Required batch"
            )
        before_items = {
            item.get("id"): item
            for item in result["queue"].get("required_queue", [])
            if isinstance(item, dict)
        }
        after_items = {
            item.get("id"): item
            for item in queue.get("required_queue", [])
            if isinstance(item, dict)
        }
        before_item = before_items.get(first_open_batch_id)
        after_item = after_items.get(first_open_batch_id)
        if (not before_items or set(before_items) != set(after_items) or
                not isinstance(before_item, dict) or
                before_item.get("state") != "queued" or
                not isinstance(after_item, dict) or
                after_item.get("state") != "open" or
                after_item.get("activation_receipt") != evidence_receipt or
                queue.get("queue_revision") !=
                result["queue"].get("queue_revision") or
                queue.get("state_revision") !=
                result["queue"].get("state_revision") + 1):
            raise ValueError(
                "planned -> active requires the bound first queued -> open "
                "Queue transition"
            )
        changed_other = [
            item_id for item_id in before_items
            if item_id != first_open_batch_id and
            before_items[item_id] != after_items[item_id]
        ]
        if changed_other:
            raise ValueError(
                "first-batch activation may not change other Queue items: %s" %
                ", ".join(sorted(changed_other))
            )

    if after_state in ("paused", "blocked", "cancelled") and not _nonempty(
            summary):
        raise ValueError("%s transition requires --checkpoint-summary" %
                         after_state)
    if before_state == "completion-candidate" and after_state != "complete" \
            and not _nonempty(summary):
        raise ValueError("leaving completion-candidate requires a reason")

    pending_guidance, pending_amendments = _pending_controls(progress)
    terminal_receipt = None
    if after_state == "completion-candidate":
        if completion_semantics != "build":
            raise ValueError(
                "maintenance tasks may not enter completion-candidate"
            )
        if result.get("remaining") != 0:
            raise ValueError("completion-candidate requires zero remaining work")
        if pending_guidance or pending_amendments:
            raise ValueError(
                "completion-candidate requires reconciled Guidance/Amendments; "
                "pending guidance=%s amendments=%s" %
                (",".join(pending_guidance) or "none",
                 ",".join(pending_amendments) or "none")
            )
        if not _nonempty(evidence_receipt):
            raise ValueError("completion-candidate requires --queue-check-receipt")
        # R08 travels in the task-completion phase.  Its carrier is whatever
        # batch still holds an activation; with zero remaining work there is
        # usually none, and then the phase has nothing to prove against.
        phase_errors = check_queue.task_phase_delivery_errors(
            result, card_activation.PHASE_TASK_COMPLETION,
            actor_context_id=os.environ.get(
                card_activation.EXECUTION_CONTEXT_ENV))
        if phase_errors:
            raise ValueError(
                "completion-candidate requires the task-completion phase: %s"
                % "; ".join(phase_errors))
        completion_receipt = _completion_gate_receipt(
            result, evidence_receipt)
        completion_time = check_queue.timestamp_value(
            completion_receipt.get("checked_at"))
        if completion_time is None or completion_time > at_value:
            raise ValueError(
                "completion-candidate cannot predate its Queue completion gate")
    elif after_state == "complete":
        if completion_semantics == "build":
            if before_state != "completion-candidate":
                raise ValueError(
                    "build completion requires completion-candidate -> complete"
                )
            if maintenance_completion_receipt is not None:
                raise ValueError(
                    "build completion does not accept a maintenance gate receipt"
                )
            if not _nonempty(terminal_proof_receipt):
                raise ValueError("complete requires --terminal-proof-receipt")
            terminal_receipt = _terminal_proof_receipt(
                result, terminal_proof_receipt)
            terminal_time = check_queue.timestamp_value(
                terminal_receipt.get("checked_at"))
            if terminal_time is None or terminal_time > at_value:
                raise ValueError(
                    "complete transition cannot predate Terminal Proof"
                )
            evidence_receipt = terminal_proof_receipt
        else:
            if (before_state not in
                    runtime_state_contract.MAINTENANCE_COMPLETION_TASK_STATES):
                raise ValueError(
                    "maintenance completion requires planned/active -> complete"
                )
            if terminal_proof_receipt is not None:
                raise ValueError(
                    "maintenance completion does not accept Terminal Proof"
                )
            if not _nonempty(maintenance_completion_receipt):
                raise ValueError(
                    "maintenance complete requires "
                    "--maintenance-completion-receipt"
                )
            terminal_receipt = _maintenance_completion_receipt(
                result, maintenance_completion_receipt,
            )
            terminal_time = check_queue.timestamp_value(
                terminal_receipt.get("checked_at"))
            if terminal_time is None or terminal_time > at_value:
                raise ValueError(
                    "complete transition cannot predate the maintenance gate"
                )
            evidence_receipt = maintenance_completion_receipt

    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "task_transition", progress.get("task_id"),
        "pass", "%s -> %s" % (before_state, after_state),
        len(history) + 1,
    )
    receipt["checked_at"] = at
    receipt.update({
        "task_id": progress.get("task_id"),
        "completion_semantics": completion_semantics,
        "contract_sha256": check_queue.contract_sha256(progress),
        "before_task_state": before_state,
        "after_task_state": after_state,
        "actor_role": "integrator",
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
        "before_coverage_sha256": result.get("coverage_sha256"),
        "after_coverage_sha256": result.get("coverage_sha256"),
        "before_required_queue_sha256": result.get("queue_sha256"),
        "after_required_queue_sha256": queue_sha,
        "before_progress_sha256": result.get("progress_sha256"),
        "evidence_receipt": evidence_receipt,
    })
    if (after_state == "complete" and
            completion_semantics == "build" and
            terminal_receipt is not None):
        # Keep the transition's own audit record source-addressable to the
        # Profile closure whose Terminal Proof authorized this edge.
        receipt.update(_terminal_binding_from_receipt(
            result, terminal_receipt))
    if before_state == "planned" and after_state == "active":
        after_item = next((
            item for item in queue.get("required_queue", [])
            if isinstance(item, dict) and
            item.get("id") == first_open_batch_id
        ), None)
        transition_ids = (after_item.get("transition_receipts")
                          if isinstance(after_item, dict) else None)
        if not isinstance(transition_ids, list) or not transition_ids:
            raise ValueError(
                "first task activation requires the persisted queued -> open "
                "Queue transition"
            )
        receipt["first_open_batch_id"] = first_open_batch_id
        receipt["first_open_transition_receipt"] = transition_ids[-1]

    new_progress = copy.deepcopy(progress)
    new_progress["task_state"] = after_state
    new_progress["queue_revision"] = queue.get("queue_revision")
    new_progress["queue_state_revision"] = queue.get("state_revision")
    new_progress["required_queue_sha256"] = queue_sha
    new_progress["task_transition_receipts"] = history + [
        receipt["receipt_id"]
    ]
    new_progress["checkpoint"] = {
        "recorded_at": at,
        "summary": summary or "%s -> %s" % (before_state, after_state),
        "task_state": after_state,
        "task_transition_receipt": receipt["receipt_id"],
        "coverage_sha256": result.get("coverage_sha256"),
        "required_queue_sha256": queue_sha,
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
    }
    terminal_audit = copy.deepcopy(new_progress.get("terminal_audit") or {})
    maintenance_completion = copy.deepcopy(
        new_progress.get("maintenance_completion") or {})
    if after_state == "completion-candidate":
        terminal_audit = {
            "state": "ready",
            "terminal_proof_path": None,
            "terminal_proof_sha256": None,
            "terminal_proof_receipt": None,
            "queue_check_receipt": evidence_receipt,
        }
    elif after_state == "complete" and completion_semantics == "build":
        terminal_audit = {
            "state": "passed",
            "terminal_proof_path": terminal_receipt["terminal_proof_path"],
            "terminal_proof_sha256":
                terminal_receipt["terminal_proof_sha256"],
            "terminal_proof_receipt": terminal_proof_receipt,
            "queue_check_receipt": terminal_receipt["queue_check_receipt"],
        }
    elif after_state == "cancelled" and completion_semantics == "build":
        terminal_audit = {
            "state": "not-applicable",
            "terminal_proof_path": None,
            "terminal_proof_sha256": None,
            "terminal_proof_receipt": None,
            "queue_check_receipt": None,
        }
    elif before_state == "completion-candidate":
        terminal_audit = {
            "state": "invalidated",
            "terminal_proof_path": None,
            "terminal_proof_sha256": None,
            "terminal_proof_receipt": None,
            "queue_check_receipt": None,
        }
    new_progress["terminal_audit"] = terminal_audit
    if after_state == "complete" and completion_semantics == "maintenance":
        maintenance_completion = {
            "state": "passed",
            "completion_gate_receipt": maintenance_completion_receipt,
            "budget_manifest_receipt":
                terminal_receipt["budget_manifest_receipt"],
            "ledger_advance_receipt":
                terminal_receipt["ledger_advance_receipt"],
            "watermark_advance_receipt":
                terminal_receipt["watermark_advance_receipt"],
        }
    elif after_state == "cancelled" and completion_semantics == "maintenance":
        maintenance_completion = {
            "state": "invalidated",
            "completion_gate_receipt": None,
            "budget_manifest_receipt": None,
            "ledger_advance_receipt": None,
            "watermark_advance_receipt": None,
        }
    new_progress["maintenance_completion"] = maintenance_completion

    progress_text = kblib.canonical_yaml(new_progress)
    receipt["after_progress_sha256"] = kblib.sha256_bytes(progress_text)
    return new_progress, progress_text, receipt


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Apply one canonical task-state transition")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument(
        "--transition", required=True,
        choices=tuple(sorted({
            target
            for edges in runtime_state_contract.TASK_TRANSITIONS_BY_SEMANTICS.values()
            for _source, target in edges
        })),
        help="target task state in the Progress Ledger",
    )
    parser.add_argument("--checkpoint-summary",
                        help="non-empty reason required by paused, blocked "
                             "and cancelled, and when leaving "
                             "completion-candidate for anything but complete")
    parser.add_argument("--queue-check-receipt",
                        help="Queue completion gate receipt id required by "
                             "the completion-candidate transition")
    parser.add_argument("--terminal-proof-receipt",
                        help="Terminal Proof receipt id required by complete "
                             "under build completion_semantics")
    parser.add_argument("--maintenance-completion-receipt",
                        help="maintenance completion gate receipt id required "
                             "by complete under maintenance "
                             "completion_semantics")
    parser.add_argument("--expected-progress-sha256",
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Progress; --apply is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-queue-sha256",
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Queue; --apply is refused "
                             "when the live bytes differ")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may apply "
                             "a task-state write")
    parser.add_argument("--at",
                        help="transition timestamp; defaults to now in UTC")
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--apply", action="store_true",
                        help="write the transition; omit for a dry run")
    parser.add_argument(
        "--json", action="store_true",
        help="write the applied transition receipt to stdout as one canonical "
             "JSON array and move the human report to stderr; a dry run "
             "publishes no receipt and so writes nothing there; receipt "
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
    """Execute one already-parsed invocation; ``produced`` collects receipts."""
    if args.at is None:
        args.at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    root = os.path.realpath(os.path.abspath(args.root))
    result = check_queue.validate_runtime(root)
    if result["errors"]:
        for error in result["errors"]:
            print("[FAIL] current runtime state: %s" % error)
        return 1
    try:
        authority = check_queue.runtime_authority_context(result)
        authority_kwargs = \
            check_queue.runtime_authority_validation_kwargs(authority)
    except (TypeError, ValueError) as exc:
        print("[FAIL] current runtime authority: %s" % exc)
        return 1
    try:
        progress_new, progress_text, receipt = build_task_transition(
            result, args.transition, args.at, args.checkpoint_summary,
            args.queue_check_receipt,
            terminal_proof_receipt=args.terminal_proof_receipt,
            maintenance_completion_receipt=
                args.maintenance_completion_receipt,
        )
        progress_path = kblib.managed_repository_path(
            root, check_queue.PROGRESS_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True,
        )
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False,
        )
    except (OSError, TypeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1

    proposed = check_queue.validate_runtime(
        root,
        state_overrides={
            check_queue.PROGRESS_PATH: (progress_text, progress_new),
        },
        extra_receipts=[receipt],
        **authority_kwargs,
    )
    if proposed["errors"]:
        for error in proposed["errors"]:
            print("[FAIL] proposed runtime state: %s" % error)
        return 1

    before_state = result["progress"].get("task_state")
    print("task transition plan: %s -> %s" %
          (before_state, args.transition))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with expected hashes")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply a task-state write")
        return 1
    if not args.expected_progress_sha256 or not args.expected_queue_sha256:
        print("[FAIL] --apply requires expected Progress and Queue fingerprints")
        return 1
    if args.expected_progress_sha256 != result.get("progress_sha256"):
        print("[FAIL] expected Progress fingerprint does not match current bytes")
        return 1
    if args.expected_queue_sha256 != result.get("queue_sha256"):
        print("[FAIL] expected Queue fingerprint does not match current bytes")
        return 1

    is_build_completion = (
        args.transition == "complete" and
        (result["progress"].get("contract") or {}).get(
            "completion_semantics") == "build"
    )
    abort_receipt = (_task_transition_abort_receipt(result, receipt)
                     if is_build_completion else None)
    operation = {
        "tool": TOOL,
        "action": "transition:%s" % args.transition,
        "target": result["progress"].get("task_id"),
        "task_id": result["progress"].get("task_id"),
        "before_queue_revision": result["queue"].get("queue_revision"),
        "before_state_revision": result["queue"].get("state_revision"),
        "planned_after_queue_revision": result["queue"].get("queue_revision"),
        "planned_after_state_revision": result["queue"].get("state_revision"),
        "before_coverage_sha256": result.get("coverage_sha256"),
        "planned_after_coverage_sha256": result.get("coverage_sha256"),
        "before_required_queue_sha256": result.get("queue_sha256"),
        "planned_after_required_queue_sha256": result.get("queue_sha256"),
        "before_progress_sha256": result.get("progress_sha256"),
        "planned_after_progress_sha256": receipt["after_progress_sha256"],
        "receipt_id": receipt["receipt_id"],
        "receipt_path": args.receipts,
    }
    operation.update(check_queue.runtime_authority_lock_fields(authority))
    if is_build_completion:
        operation.update({
            "abort_receipt_id": abort_receipt["receipt_id"],
            "selected_profile_manifest":
                receipt["selected_profile_manifest"],
            "profile_snapshot_sha256":
                receipt["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                receipt["profile_contract_fingerprint"],
            "profile_load_inputs_sha256":
                receipt["profile_load_inputs_sha256"],
            "repository_snapshot_sha256":
                receipt["repository_snapshot_sha256"],
        })
    try:
        with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
            locked_terminal_binding = None
            receipt_before = None
            with kblib.no_authoritative_write_guard(lease):
                with open(progress_path, encoding="utf-8") as fh:
                    old_progress_text = fh.read()
                current = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if current["errors"]:
                    raise ValueError("runtime changed before write: %s" %
                                     "; ".join(current["errors"]))
                if (current.get("coverage_sha256") != result.get("coverage_sha256") or
                        current.get("queue_sha256") != result.get("queue_sha256") or
                        current.get("progress_sha256") != result.get("progress_sha256")):
                    raise ValueError("Coverage, Queue, or Progress changed after validation")
                _require_transaction_currency(
                    root, authority, "runtime authority changed under lock")
                if is_build_completion:
                    # Profile bytes are outside the state-ledger CAS.  Reuse
                    # the exact Terminal Proof consumer at the last locked
                    # pre-write boundary so a valid Profile replacement after
                    # prevalidation cannot authorize completion with stale
                    # snapshot/contract bindings.
                    locked_terminal = _terminal_proof_receipt(
                        current, args.terminal_proof_receipt)
                    locked_terminal_binding = _terminal_binding_from_receipt(
                        current, locked_terminal)
                    for field in TERMINAL_BINDING_FIELDS:
                        if receipt.get(field) != locked_terminal_binding[field]:
                            raise ValueError(
                                "planned task transition %s differs from the "
                                "locked Terminal Proof" % field)
                    receipt_before = kblib.receipt_append_observation(
                        receipt_path, [receipt])
            if not is_build_completion:
                receipt_attempted = False
                try:
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed before Progress write")
                    kblib.atomic_write_text(
                        progress_path, progress_text,
                        validator=kblib.parse_yaml_subset,
                    )
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed during Progress write")
                    post = check_queue.validate_runtime(
                        root, extra_receipts=[receipt], **authority_kwargs)
                    if post["errors"]:
                        raise ValueError(
                            "persisted Progress state is invalid: %s" %
                            "; ".join(post["errors"]))
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed before task receipt")
                    receipt_attempted = True
                    kblib.write_receipts(receipt_path, [receipt])
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed during task receipt")
                    persisted = check_queue.validate_runtime(
                        root, **authority_kwargs)
                    if persisted["errors"]:
                        raise ValueError(
                            "persisted task transition is invalid: %s" %
                            "; ".join(persisted["errors"]))
                except Exception:
                    restored = False
                    try:
                        kblib.atomic_write_text(
                            progress_path, old_progress_text,
                            validator=kblib.parse_yaml_subset,
                        )
                        restored = (
                            kblib.sha256_file(progress_path) ==
                            result.get("progress_sha256")
                        )
                    finally:
                        # A failed append may have persisted a full or partial
                        # receipt. Preserve the lock unless no append began.
                        if restored and not receipt_attempted:
                            lease.mark_reconciled()
                        raise
            else:
                receipt_attempted = False
                receipt_outcome = "not-attempted"
                try:
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed before Progress write",
                        locked_terminal_binding)
                    kblib.atomic_write_text(
                        progress_path, progress_text,
                        validator=kblib.parse_yaml_subset,
                    )
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed during Progress write",
                        locked_terminal_binding)
                    post = check_queue.validate_runtime(
                        root, extra_receipts=[receipt], **authority_kwargs)
                    if post["errors"]:
                        raise ValueError(
                            "persisted Progress state is invalid: %s" %
                            "; ".join(post["errors"]))
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed before task receipt",
                        locked_terminal_binding)
                    receipt_attempted = True
                    receipt_outcome, receipt_error, _ = \
                        kblib.write_receipts_observed(
                            receipt_path, [receipt], before=receipt_before)
                    if receipt_error is not None:
                        raise receipt_error
                    _require_transaction_currency(
                        root, authority,
                        "runtime authority changed during task receipt",
                        locked_terminal_binding)
                    persisted = check_queue.validate_runtime(
                        root, **authority_kwargs)
                    if persisted["errors"]:
                        raise ValueError(
                            "persisted task transition is invalid: %s" %
                            "; ".join(persisted["errors"]))
                except Exception as write_error:
                    rollback_failures = []
                    try:
                        kblib.atomic_write_text(
                            progress_path, old_progress_text,
                            validator=kblib.parse_yaml_subset,
                        )
                    except Exception as exc:
                        rollback_failures.append("Progress: %s" % exc)
                    try:
                        if (kblib.sha256_file(progress_path) !=
                                result.get("progress_sha256")):
                            rollback_failures.append(
                                "Progress fingerprint not restored")
                    except OSError as exc:
                        rollback_failures.append(
                            "Progress verification: %s" % exc)
                    if receipt_attempted and receipt_outcome == \
                            "not-attempted":
                        receipt_outcome = kblib.receipt_outcome_from(
                            receipt_path, [receipt], receipt_before)
                    elif not receipt_attempted:
                        receipt_outcome = "absent"

                    abort_receipt["failure"] = str(write_error)
                    abort_receipt["task_transition_receipt_outcome"] = \
                        receipt_outcome
                    abort_receipt["rollback_failures"] = rollback_failures
                    abort_outcome, abort_error, _ = \
                        kblib.write_receipts_observed(
                            receipt_path, [abort_receipt])
                    fully_reconciled = (
                        not rollback_failures and
                        receipt_outcome == "absent" and
                        abort_outcome == "present"
                    )
                    if fully_reconciled:
                        lease.mark_reconciled()
                        raise
                    raise ValueError(
                        "build completion failed and recovery is incomplete: "
                        "%s; transition_receipt=%s abort=%s "
                        "abort_error=%s rollback=%s" % (
                            write_error, receipt_outcome, abort_outcome,
                            abort_error,
                            "; ".join(rollback_failures) or "none"))
    except (OSError, ValueError, kblib.YamlSubsetError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] task transition write failed; restoration attempted: %s" %
              exc)
        return 1
    if produced is not None:
        produced.append(receipt)
    print("[PASS] task transition applied; task_state=%s progress_sha256=%s" %
          (args.transition, receipt["after_progress_sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
