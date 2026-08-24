"""One Queue item's ordered transitions and the holds they drive.

The ordered transition receipts, the revalidation-hold sub-state machine they
drive, and which batches still reference a receipt that has not reached a
terminal state.  Ordering is the whole subject: the same set of receipts in a
different order is a different history.
"""

import kblib

from queue_runtime.canon import TERMINAL_STATES
from queue_runtime.primitives import _nonempty_string
from queue_runtime.receipts import delta_gate_receipt_ids


def _current_item_transition_evidence(item, catalog):
    """Return hold-clear evidence in the current attempt, not all history."""
    transition_ids = item.get("transition_receipts")
    if not isinstance(transition_ids, list):
        return set()
    history = item.get("invalidation_history")
    last_rollback = (history[-1].get("transition_receipt")
                     if isinstance(history, list) and history and
                     isinstance(history[-1], dict) else None)
    start = 0
    if last_rollback in transition_ids:
        start = transition_ids.index(last_rollback) + 1
    evidence = set()
    window = set(transition_ids[start:])
    for transition_id in transition_ids[start:]:
        entry = catalog.get(transition_id)
        transition = entry[1] if entry is not None else None
        if not isinstance(transition, dict):
            continue
        revalidation = transition.get("standards_revalidation_receipt")
        if _nonempty_string(revalidation):
            evidence.add(revalidation)
    # A discharge is recognized by the replayed hold machine, not by the
    # adjacent `revalidation-required -> none` edge: the clear may legitimately
    # be taken from a hold the item moved to while the obligation stood.  The
    # machine is replayed over the whole history and the result filtered to
    # the current attempt, because the rollback that opened this attempt's
    # obligation sits just before the window.
    for transition in item_revalidation_discharges(item, catalog):
        if (transition.get("receipt_id") in window and
                transition.get("before_state") == transition.get("after_state")
                and _nonempty_string(transition.get("evidence_receipt"))):
            evidence.add(transition["evidence_receipt"])
    return evidence


def _clears_revalidation_hold(transition):
    """Return whether one transition discharges a `revalidation-required` hold.

    The discharge is the evidence, not the edge.  ``update_queue.py`` records
    whichever receipt authorized the clear -- the Standards revalidation
    aggregate when adoption bindings are outstanding, otherwise the bound
    Queue-consistency gate -- in ``evidence_receipt``, and additionally names
    the aggregate in ``standards_revalidation_receipt``.  A transition that
    lands on ``none`` carrying neither has proved nothing, whatever hold it
    came from.
    """
    if not isinstance(transition, dict):
        return False
    if transition.get("after_hold_state") != "none":
        return False
    return (_nonempty_string(transition.get("evidence_receipt")) or
            _nonempty_string(transition.get("standards_revalidation_receipt")))


def walk_revalidation_hold(transitions):
    """Replay the hold sub-state machine over one item's ordered history.

    Returns ``(outstanding, discharges)``: whether a ``revalidation-required``
    hold is still owed, and the transitions that actually retired one.

    ``hold_state`` is a sub-state machine, not a set of independent flags, so
    the obligation it records cannot be read off the current value alone.
    Entering ``revalidation-required`` opens the obligation; only a transition
    that lands on ``none`` with its discharge evidence retires it.  Moving to
    any other hold -- ``paused``, ``blocked``, ``confirmation-required`` --
    defers the obligation and never settles it, so
    ``revalidation-required -> paused -> none`` clears exactly as much as the
    direct ``revalidation-required -> none`` edge it routes around, which is
    nothing.

    Replaying the whole ordered list rather than reading the adjacent edge is
    the point: the bypass is only visible across an arbitrary number of
    intermediate holds, and a hand-edited ``hold_state`` that never recorded
    a clearing transition stays outstanding here too.
    """
    outstanding = False
    discharges = []
    for transition in transitions or []:
        if not isinstance(transition, dict):
            continue
        if transition.get("after_hold_state") == "revalidation-required":
            outstanding = True
        elif outstanding and _clears_revalidation_hold(transition):
            outstanding = False
            discharges.append(transition)
    return outstanding, discharges


def undischarged_revalidation_hold(transitions):
    """Return whether a `revalidation-required` hold is still outstanding."""
    return walk_revalidation_hold(transitions)[0]


def _ordered_item_transitions(item, catalog):
    """Return the item's transition receipts, in order, that resolve."""
    transition_ids = item.get("transition_receipts")
    if not isinstance(transition_ids, list):
        return []
    transitions = []
    for transition_id in transition_ids:
        entry = catalog.get(transition_id) if _nonempty_string(
            transition_id) else None
        if entry is not None and isinstance(entry[1], dict):
            transitions.append(entry[1])
    return transitions


def item_undischarged_revalidation_hold(item, catalog):
    """Resolve :func:`undischarged_revalidation_hold` from receipt IDs."""
    return undischarged_revalidation_hold(
        _ordered_item_transitions(item, catalog))


def item_revalidation_discharges(item, catalog):
    """Return the transitions that retired a `revalidation-required` hold."""
    return walk_revalidation_hold(
        _ordered_item_transitions(item, catalog))[1]


def invalidated_receipt_consumers(root, queue, catalog):
    """Map current non-terminal receipt references back to Queue batches."""
    consumers = {}

    def add(batch_id, receipt_id, source):
        if not _nonempty_string(receipt_id):
            return
        consumers.setdefault(receipt_id, []).append({
            "batch_id": batch_id, "source": source,
        })

    for item in queue.get("required_queue", []) if isinstance(
            queue.get("required_queue"), list) else []:
        if not isinstance(item, dict) or item.get("state") in TERMINAL_STATES:
            continue
        batch_id = item.get("id")
        for field in ("activation_receipt", "confirmation_receipt"):
            add(batch_id, item.get(field), "Queue.%s" % field)
        for receipt_id in _current_item_transition_evidence(item, catalog):
            add(batch_id, receipt_id, "Queue.current-transition-evidence")
        if item.get("state") == "merge-ready":
            for receipt_id in item.get("batch_receipts") or []:
                add(batch_id, receipt_id, "Queue.batch_receipts")
            for field in ("delta_apply_receipt", "queue_consistency_receipt",
                          "close_gate_receipt"):
                add(batch_id, item.get(field), "Queue.%s" % field)
        if item.get("state") in ("open", "merge-ready"):
            relative = item.get("delta_path")
            if not _nonempty_string(relative):
                relative = ".cambium/deltas/%s.yaml" % batch_id
            try:
                path = kblib.managed_repository_path(
                    root, relative, ".cambium/deltas", suffixes=(".yaml",),
                    must_exist=True)
                delta = kblib.load_yaml_file(path)
                for receipt_id in delta_gate_receipt_ids(delta):
                    add(batch_id, receipt_id, "Delta.gate_receipts")
            except (OSError, ValueError, kblib.YamlSubsetError):
                # The normal Delta validator reports the underlying defect.
                pass
    return consumers


def _latest_merge_transition(item, catalog):
    for receipt_id in reversed(item.get("transition_receipts") or []):
        entry = catalog.get(receipt_id)
        receipt = entry[1] if isinstance(entry, tuple) else None
        if (isinstance(receipt, dict) and
                receipt.get("before_state") == "open" and
                receipt.get("after_state") == "merge-ready"):
            return receipt_id, receipt
    return None, None
