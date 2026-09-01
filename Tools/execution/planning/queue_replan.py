"""Public deterministic projection contract for Required Queue replans.

This module owns the pure structural projection shared by the Queue compiler,
Amendment registration, and Amendment execution.  It never reads or writes
runtime state and does not authorize a replan; callers must supply a validated
proposal and the already-derived diff.
"""

import copy

import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.execution.planning.work_spec_contract as work_spec_contract


STRUCTURAL_FIELDS = (
    "family", "order", "record_count", "manifest", "source_route",
    "execution_mode", "depends_on", "confirmation_required", "successor_of",
) + tuple(sorted(work_spec_contract.WORK_SPEC_BINDING_FIELDS))
WORK_SPEC_FIELDS = work_spec_contract.WORK_SPEC_BINDING_FIELDS


def changed_structural_fields(current, proposed):
    """Return value or explicit-presence changes in the closed structure."""
    return [
        field for field in STRUCTURAL_FIELDS
        if ((field in current) != (field in proposed) or
            current.get(field) != proposed.get(field))
    ]


def changed_batch_ids(diff):
    """Return the stable, sorted set of batch identities changed by a diff."""
    changed = set()
    for field in ("add_candidates", "update_candidates",
                  "reorder_candidates", "remove_candidates"):
        for entry in diff.get(field, []):
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                changed.add(entry["id"])
    return sorted(changed)


def build_replanned_queue(queue, proposal, diff):
    """Project safe structural candidates while preserving lifecycle data."""
    if diff.get("remove_candidates"):
        removed = ", ".join(entry.get("id", "<unknown>")
                            for entry in diff["remove_candidates"]
                            if isinstance(entry, dict))
        raise ValueError("replan cannot delete Queue history/items: %s" % removed)
    if diff.get("conflicts"):
        raise ValueError("replan has unresolved conflict(s): %s" %
                         "; ".join(str(value) for value in diff["conflicts"]))

    current = {item.get("id"): item for item in queue.get("required_queue", [])
               if isinstance(item, dict)}
    desired = {item.get("id"): item
               for item in proposal.get("required_queue", [])
               if isinstance(item, dict)}
    result_items = []
    for item in queue.get("required_queue", []):
        item_id = item.get("id")
        proposed = desired.get(item_id)
        if proposed is None:
            result_items.append(copy.deepcopy(item))
            continue
        changed = changed_structural_fields(item, proposed)
        work_spec_only = bool(changed) and set(changed).issubset(
            WORK_SPEC_FIELDS)
        open_spec_replan = (
            item.get("state") == "open" and work_spec_only and
            item.get("hold_state") == "revalidation-required"
        )
        if changed and item.get("state") in \
                runtime_state_contract.QUEUE_TERMINAL_STATES:
            # Sealed terminal structure is immutable history; a surviving
            # proposal row cannot rewrite it.
            changed = []
        elif (changed and item.get("state") != "queued" and
              not open_spec_replan):
            raise ValueError("cannot change structure of %s item %s" %
                             (item.get("state"), item_id))
        merged = copy.deepcopy(item)
        if item.get("state") == "queued":
            for field in STRUCTURAL_FIELDS:
                if field in proposed:
                    merged[field] = copy.deepcopy(proposed[field])
                else:
                    merged.pop(field, None)
        elif open_spec_replan:
            for field in WORK_SPEC_FIELDS:
                merged[field] = copy.deepcopy(proposed.get(field))
        result_items.append(merged)

    for proposed in proposal.get("required_queue", []):
        item_id = proposed.get("id")
        if item_id in current:
            continue
        if proposed.get("state") != "queued":
            raise ValueError("new Queue item %s must start queued" % item_id)
        result_items.append(copy.deepcopy(proposed))

    result_items.sort(key=lambda item: (item.get("order", 10 ** 9),
                                        item.get("id", "")))
    orders = [item.get("order") for item in result_items]
    if orders != list(range(1, len(result_items) + 1)):
        raise ValueError("replanned Queue order must remain contiguous from 1")
    positions = {item.get("id"): item.get("order") for item in result_items}
    for item in result_items:
        for dependency in item.get("depends_on", []):
            if dependency not in positions:
                raise ValueError("%s depends on missing batch %s" %
                                 (item.get("id"), dependency))
            if positions[dependency] >= item.get("order"):
                raise ValueError("%s dependency %s is not ordered earlier" %
                                 (item.get("id"), dependency))

    result = copy.deepcopy(queue)
    result["queue_revision"] = queue.get("queue_revision", 0) + 1
    result["state_revision"] = queue.get("state_revision")
    result["required_queue"] = result_items
    return result
