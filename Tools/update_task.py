#!/usr/bin/env python3
"""Apply one optimistic, receipt-backed task lifecycle transition.

Task state belongs to the Progress Ledger.  This tool is its only ordinary
writer.  It never edits Queue or Coverage bytes, but it compare-and-swaps all
three live fingerprints under the shared runtime writer lock so a restart can
distinguish a completed transition from an interrupted one.

The default is a dry run.  ``--apply`` requires the integrator role and exact
Progress and Required Queue fingerprints observed by the caller.
"""

import argparse
import copy
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib


TOOL = "update_task"
TOOL_VERSION = "1.1.0"
TERMINAL_PROOF_TOOL = "check_proof"
TERMINAL_PROOF_TOOL_VERSION = "1.15.0"
TERMINAL_PROOF_GATE_ID = "terminal-proof"
RECEIPT_PATH = ".cambium/receipts/task-transitions.jsonl"
FINAL_CONTROL_STATUSES = frozenset((
    "verified", "deferred", "superseded", "not-applicable",
))

# ``planned -> paused/blocked`` is intentional: an admitted task may be
# interrupted or encounter a blocker before its first batch is activated.
TRANSITIONS = {
    "planned": frozenset((
        "active", "paused", "blocked", "completion-candidate", "complete",
        "cancelled",
    )),
    "active": frozenset((
        "paused", "blocked", "completion-candidate", "complete", "cancelled",
    )),
    "paused": frozenset(("active", "blocked", "cancelled")),
    "blocked": frozenset(("active", "paused", "cancelled")),
    "completion-candidate": frozenset((
        "active", "paused", "blocked", "complete", "cancelled",
    )),
    "complete": frozenset(),
    "cancelled": frozenset(),
}


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
        if entry.get("status") not in FINAL_CONTROL_STATUSES:
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
        if (status not in FINAL_CONTROL_STATUSES or
                (status == "verified" and
                 entry.get("writeback_done") is not True)):
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
        if not check_queue._valid_timestamp(checked_at):
            raise ValueError("task transition %s has invalid checked_at" %
                             receipt_id)
        checked_time = check_queue._timestamp_value(checked_at)
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
            result["root"], proof_path, ".cambium/receipts",
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
    return receipt


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
        check_queue._maintenance_completion_gate_errors(
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
    time_errors = check_queue._maintenance_gate_time_errors(result, receipt)
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
    if after_state not in TRANSITIONS.get(before_state, frozenset()):
        raise ValueError("illegal task transition %s -> %s" %
                         (before_state, after_state))
    at_value = check_queue._timestamp_value(at)
    if at_value is None:
        raise ValueError("transition time must be timezone-aware RFC 3339")
    latest_at, history = _latest_transition_timestamp(result, progress)
    if latest_at is not None and at_value < latest_at:
        raise ValueError("task transition time precedes existing history")
    checkpoint = progress.get("checkpoint")
    if isinstance(checkpoint, dict):
        recorded_at = checkpoint.get("recorded_at")
        if recorded_at is not None:
            recorded_value = check_queue._timestamp_value(recorded_at)
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
        completion_receipt = _completion_gate_receipt(
            result, evidence_receipt)
        completion_time = check_queue._timestamp_value(
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
            terminal_time = check_queue._timestamp_value(
                terminal_receipt.get("checked_at"))
            if terminal_time is None or terminal_time > at_value:
                raise ValueError(
                    "complete transition cannot predate Terminal Proof"
                )
            evidence_receipt = terminal_proof_receipt
        else:
            if before_state not in ("planned", "active"):
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
            terminal_time = check_queue._timestamp_value(
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
        "contract_sha256": check_queue._contract_sha256(progress),
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
    parser = argparse.ArgumentParser(
        description="Apply one canonical task-state transition")
    parser.add_argument("root")
    parser.add_argument(
        "--transition", required=True,
        choices=tuple(sorted({target for targets in TRANSITIONS.values()
                              for target in targets})),
    )
    parser.add_argument("--checkpoint-summary")
    parser.add_argument("--queue-check-receipt")
    parser.add_argument("--terminal-proof-receipt")
    parser.add_argument("--maintenance-completion-receipt")
    parser.add_argument("--expected-progress-sha256")
    parser.add_argument("--expected-queue-sha256")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker")
    parser.add_argument("--at")
    parser.add_argument("--receipts", default=RECEIPT_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.at is None:
        args.at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    root = os.path.realpath(os.path.abspath(args.root))
    result = check_queue.validate_runtime(root)
    result["root"] = root
    if result["errors"]:
        for error in result["errors"]:
            print("[FAIL] current runtime state: %s" % error)
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
            root, check_queue.PROGRESS_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        )
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
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
    try:
        with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                with open(progress_path, encoding="utf-8") as fh:
                    old_progress_text = fh.read()
                current = check_queue.validate_runtime(root)
                if current["errors"]:
                    raise ValueError("runtime changed before write: %s" %
                                     "; ".join(current["errors"]))
                if (current.get("coverage_sha256") != result.get("coverage_sha256") or
                        current.get("queue_sha256") != result.get("queue_sha256") or
                        current.get("progress_sha256") != result.get("progress_sha256")):
                    raise ValueError("Coverage, Queue, or Progress changed after validation")
            receipt_attempted = False
            try:
                kblib.atomic_write_text(
                    progress_path, progress_text,
                    validator=kblib.parse_yaml_subset,
                )
                receipt_attempted = True
                kblib.write_receipts(receipt_path, [receipt])
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
                    # receipt.  Preserve the lock for operator reconciliation
                    # unless the receipt operation was never attempted.
                    if restored and not receipt_attempted:
                        lease.mark_reconciled()
                    raise
    except (OSError, ValueError, kblib.YamlSubsetError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] task transition write failed; restoration attempted: %s" %
              exc)
        return 1
    print("[PASS] task transition applied; task_state=%s progress_sha256=%s" %
          (args.transition, receipt["after_progress_sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
