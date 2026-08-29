"""Pure routed-gap settlement and target-eligibility predicates."""

import hashlib

import coverage_delta
import kblib
import runtime_state_contract

PROTOCOL = "routed-gap-settlement/1"
ELIGIBLE_TARGET_STATES = runtime_state_contract.QUEUE_ACTIONABLE_TARGET_STATES


def _canonical_sha(value):
    return "sha256:" + hashlib.sha256(
        kblib.canonical_json_bytes(value)).hexdigest()


def _gap_record(gap):
    return {
        "identity": coverage_delta.gap_identity_text(gap),
        "page": gap.get("page"),
        "type": gap.get("type"),
        "next_batch": gap.get("next_batch"),
        "record_sha256": _canonical_sha(gap),
    }


def routed_obligations(coverage, batch_id):
    gaps = coverage.get("open_gaps") if isinstance(coverage, dict) else None
    if not isinstance(gaps, list):
        raise ValueError("Coverage open_gaps must be an explicit list")
    records = [_gap_record(gap) for gap in gaps
               if isinstance(gap, dict) and
               gap.get("next_batch") == batch_id]
    return sorted(records, key=lambda row: row["identity"].encode("utf-8"))


def _queue_index(queue):
    items = queue.get("required_queue") if isinstance(queue, dict) else None
    if not isinstance(items, list):
        raise ValueError("Required Queue must contain an explicit required_queue")
    by_id = {}
    order = {}
    for index, item in enumerate(items):
        item_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(item_id, str) or not item_id:
            continue
        by_id[item_id] = item
        order[item_id] = index
    return by_id, order


def _gaps_by_key(coverage, label):
    gaps = coverage.get("open_gaps") if isinstance(coverage, dict) else None
    if not isinstance(gaps, list):
        raise ValueError("%s open_gaps must be an explicit list" % label)
    result = {}
    for index, gap in enumerate(gaps):
        key = coverage_delta.gap_key(gap)
        if (not isinstance(gap, dict) or key is None or
                key in result):
            raise ValueError(
                "%s open_gaps[%d] has no unique stable identity" %
                (label, index))
        result[key] = gap
    return result


def amendment_gap_reconciliation_report(before, after, queue):
    """Validate the narrow cross-batch/orphan gap Amendment extension.

    The operation may close an existing gap or change only its ``next_batch``
    route.  Creating findings remains a batch Delta responsibility.  A new
    target must be an existing queued/open batch and, when replacing a named
    source target, must be later in Queue order.
    """
    errors = []
    left = _gaps_by_key(before, "current Coverage")
    right = _gaps_by_key(after, "proposed Coverage")
    by_id, order = _queue_index(queue)
    changed_pages = set()
    changed_batches = set()
    changed = []
    for key in sorted(set(left).union(right), key=repr):
        old = left.get(key)
        new = right.get(key)
        if old == new:
            continue
        identity = coverage_delta.gap_identity_text(old or new)
        changed.append(identity)
        page = (old or new).get("page")
        if isinstance(page, str) and page:
            changed_pages.add(page)
        if old is None:
            errors.append(
                "gap-reconciliation-may-not-create: %s; create it in the "
                "owning batch Delta" % identity)
            continue
        old_target = old.get("next_batch")
        if isinstance(old_target, str) and old_target:
            changed_batches.add(old_target)
        if new is None:
            continue
        differing = sorted(
            field for field in set(old).union(new)
            if old.get(field) != new.get(field))
        if differing != ["next_batch"]:
            errors.append(
                "gap-reconciliation-may-only-change-next_batch: %s changes "
                "%s" % (identity, ",".join(differing)))
            continue
        target_id = new.get("next_batch")
        if target_id in (None, ""):
            # Explicitly making a gap unowned would only postpone the same
            # failure.  Close it or route it to an actionable successor.
            errors.append("gap-target-missing: %s" % identity)
            continue
        target = by_id.get(target_id)
        changed_batches.add(target_id)
        if target is None:
            errors.append("gap-target-unknown: %s -> %s" %
                          (identity, target_id))
            continue
        if target.get("state") not in ELIGIBLE_TARGET_STATES:
            errors.append("gap-target-not-actionable: %s -> %s (%s)" %
                          (identity, target_id, target.get("state")))
        if (isinstance(old_target, str) and old_target in order and
                target_id in order and order[target_id] <= order[old_target]):
            errors.append("gap-target-not-later: %s -> %s" %
                          (identity, target_id))
    return {
        "protocol": PROTOCOL,
        "changed_gap_count": len(changed),
        "changed_gap_set_sha256": _canonical_sha(changed),
        "changed_pages": sorted(changed_pages),
        "changed_batches": sorted(changed_batches),
        "errors": errors,
    }


def delta_settlement_report(coverage_before, coverage_after, delta, queue,
                            batch_id):
    """Return a closed report for one prospective batch Delta."""
    errors = []
    before = routed_obligations(coverage_before, batch_id)
    after = routed_obligations(coverage_after, batch_id)
    before_keys = {
        coverage_delta.gap_key(gap): gap
        for gap in coverage_before.get("open_gaps", [])
        if isinstance(gap, dict)
    }
    closures = delta.get("open_gaps_closed") or []
    for selector in closures:
        key = coverage_delta.gap_key(selector)
        gap = before_keys.get(key)
        if gap is not None and gap.get("next_batch") != batch_id:
            errors.append(
                "gap-close-not-routed-to-batch: %s routes to %r, not %s" %
                (coverage_delta.gap_identity_text(gap),
                 gap.get("next_batch"), batch_id))

    by_id, order = _queue_index(queue)
    source_order = order.get(batch_id)
    for gap in delta.get("open_gaps_added") or []:
        target_id = gap.get("next_batch") if isinstance(gap, dict) else None
        if target_id in (None, ""):
            continue
        target = by_id.get(target_id)
        identity = coverage_delta.gap_identity_text(gap)
        if target is None:
            errors.append("gap-target-unknown: %s -> %s" %
                          (identity, target_id))
            continue
        if target_id == batch_id:
            errors.append("gap-target-self: %s -> %s" %
                          (identity, target_id))
        if target.get("state") not in ELIGIBLE_TARGET_STATES:
            code = ("gap-target-frozen" if target.get("state") == "merge-ready"
                    else "gap-target-terminal")
            errors.append("%s: %s -> %s (%s)" %
                          (code, identity, target_id, target.get("state")))
        if (source_order is not None and target_id in order and
                order[target_id] <= source_order):
            errors.append("gap-target-not-later: %s -> %s" %
                          (identity, target_id))

    if after:
        errors.append(
            "routed-gap-unsettled: %d open gap(s) still route to %s: %s" %
            (len(after), batch_id,
             ", ".join(row["identity"] for row in after[:8]) +
             ("..." if len(after) > 8 else "")))
    return {
        "protocol": PROTOCOL,
        "batch_id": batch_id,
        "obligation_count_before": len(before),
        "obligation_set_sha256_before": _canonical_sha(
            [row["identity"] for row in before]),
        "obligation_record_set_sha256_before": _canonical_sha(before),
        "unsettled_count_after": len(after),
        "unsettled_set_sha256_after": _canonical_sha(
            [row["identity"] for row in after]),
        "unsettled_ids_after": [row["identity"] for row in after],
        "errors": errors,
    }


def current_settlement_report(coverage, batch_id):
    remaining = routed_obligations(coverage, batch_id)
    errors = []
    if remaining:
        errors.append(
            "routed-gap-unsettled: %d open gap(s) still route to %s: %s" %
            (len(remaining), batch_id,
             ", ".join(row["identity"] for row in remaining[:8]) +
             ("..." if len(remaining) > 8 else "")))
    return {
        "protocol": PROTOCOL,
        "batch_id": batch_id,
        "unsettled_count": len(remaining),
        "unsettled_set_sha256": _canonical_sha(
            [row["identity"] for row in remaining]),
        "unsettled_ids": [row["identity"] for row in remaining],
        "errors": errors,
    }


def transition_binding(report):
    return {
        "settlement_protocol": report["protocol"],
        "routed_gap_obligation_count": report["obligation_count_before"],
        "routed_gap_obligation_set_sha256":
            report["obligation_set_sha256_before"],
        "routed_gap_obligation_record_set_sha256":
            report["obligation_record_set_sha256_before"],
        "prospective_unsettled_count": report["unsettled_count_after"],
        "prospective_unsettled_set_sha256":
            report["unsettled_set_sha256_after"],
    }


def close_binding(report):
    """Return the compact current-Coverage settlement bound by close."""
    return {
        "settlement_protocol": report["protocol"],
        "current_unsettled_count": report["unsettled_count"],
        "current_unsettled_set_sha256": report["unsettled_set_sha256"],
    }
