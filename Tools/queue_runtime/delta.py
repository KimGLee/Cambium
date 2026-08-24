"""Where a managed Coverage Delta is in its lifecycle.

Routed-gap settlement, unconsumed apply candidates, the closed apply binding,
rollback restore, and the serial write barrier that an applied-but-unclosed
delta opens.  The barrier is the reason these belong together: the lifecycle
position is what decides whether another writer may proceed.
"""

import batch_settlement
import coverage_delta

from queue_runtime.canon import (
    ANY_PRODUCER_ERA_VERSION,
    APPLY_DELTA_TOOL_VERSION,
    COVERAGE_PATH,
    SHA256_RE,
    UPDATE_QUEUE_TOOL_VERSION,
)
from queue_runtime.item_history import _latest_merge_transition
from queue_runtime.primitives import (
    _nonempty_string,
    _valid_timestamp,
)
from queue_runtime.property_state import (
    _delta_opening_semantic_binding,
    _delta_property_event_errors,
    _delta_property_invalidation_errors,
)
from queue_runtime.receipts import _require_receipt


SUPPORTED_APPLY_DELTA_TOOL_VERSIONS = frozenset((
    "1.4.0", "1.5.0", "1.6.0"))


DELTA_FIELDS = frozenset((
    "batch", "generated_at", "pages", "open_gaps_added",
    "open_gaps_closed", "next_batch_updates", "watermark_advance",
))
DELTA_CONTROL_FIELDS = frozenset((
    "coverage_disposition", "canonical_owner", "batch", "next_batch",
    "priority", "tier", "type", "prerequisites", "deferred_reason",
    "reentry_condition",
))


def batch_reference_settlement_errors(result, item):
    """Return K13/08 Batch Reference Settlement failures for a close.

    A terminal batch keeps its history and loses its live references.  Three
    of the four reference kinds in the K13/08 table were each discovered as a
    separate production incident -- page ownership, gap routing, and the
    stale ``batch_specs`` row -- because nothing enumerated them.  This is the
    enumeration made executable at the transition that consumes it.  Receipt
    ``batch_id`` is deliberately absent: sealed evidence names the batch
    forever and is never settled.

    Judged at write time against the post-delta Ledger, so sealed history is
    never re-judged.
    """
    errors = []
    item_id = item.get("id")
    coverage = result.get("coverage") or {}

    try:
        report = batch_settlement.current_settlement_report(coverage, item_id)
    except ValueError as exc:
        return ["K13/08 settlement cannot inspect Coverage: %s" % exc]
    if report["errors"]:
        errors.append(
            "K13/08 settlement: %d open gap(s) still route to this batch "
            "and would be stranded on a terminal batch: %s; the Delta must "
            "close each one or re-route it to a named later batch (routing, "
            "not manifest membership, decides which gaps the batch owes)" %
            (report["unsettled_count"],
             ", ".join(report["unsettled_ids"][:8]) +
             ("..." if report["unsettled_count"] > 8 else "")))

    # The batch_specs row is deliberately NOT settled here.  Its row is
    # harmless at close and becomes harmful only when a later replan tries to
    # recompile a sealed item from it; that reference is settled on the
    # replan side (compile_queue treats a terminal item's spec row as history
    # rather than a proposal), which is where the incident actually occurred.
    return errors


SETTLEMENT_BINDING_FIELDS = (
    "routed_gap_obligation_count",
    "routed_gap_obligation_set_sha256",
    "routed_gap_obligation_record_set_sha256",
    "prospective_unsettled_count",
    "prospective_unsettled_set_sha256",
)


def _settlement_binding_errors(receipt, label):
    """Validate the current routed-gap receipt protocol shape."""
    errors = []
    if receipt.get("settlement_protocol") != batch_settlement.PROTOCOL:
        errors.append("%s has unsupported settlement_protocol %r" %
                      (label, receipt.get("settlement_protocol")))
    for field in ("routed_gap_obligation_count",
                  "prospective_unsettled_count"):
        value = receipt.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append("%s has invalid %s" % (label, field))
    if receipt.get("prospective_unsettled_count") != 0:
        errors.append("%s does not bind a settled prospective Coverage" % label)
    for field in (
            "routed_gap_obligation_set_sha256",
            "routed_gap_obligation_record_set_sha256",
            "prospective_unsettled_set_sha256"):
        if not SHA256_RE.fullmatch(str(receipt.get(field) or "")):
            errors.append("%s has invalid %s" % (label, field))
    return errors


def _close_settlement_binding_errors(receipt, label):
    errors = []
    if receipt.get("settlement_protocol") != batch_settlement.PROTOCOL:
        errors.append("%s has unsupported settlement_protocol %r" %
                      (label, receipt.get("settlement_protocol")))
    if receipt.get("current_unsettled_count") != 0:
        errors.append("%s does not bind zero current routed gaps" % label)
    if not SHA256_RE.fullmatch(str(
            receipt.get("current_unsettled_set_sha256") or "")):
        errors.append("%s has invalid current_unsettled_set_sha256" % label)
    return errors


def _closed_delta_apply_errors(item, transition, catalog, queue, root=None):
    """Bind one closed batch to the Coverage delta application it consumed."""
    errors = []
    item_id = item.get("id", "<unknown>")
    receipt_id = item.get("delta_apply_receipt")
    receipt = _require_receipt(
        catalog, receipt_id, "%s delta application" % item_id, errors,
        expected={
            "tool": "apply_delta",
            "tool_version": ANY_PRODUCER_ERA_VERSION,
            "check": "delta_apply",
            "target": item_id,
            "task_id": queue.get("task_id"),
            "batch_id": item_id,
            "actor_role": "integrator",
            "coverage_ledger_path": COVERAGE_PATH,
            "delta_path": item.get("delta_path"),
        },
    )
    entry = catalog.get(receipt_id) if _nonempty_string(receipt_id) else None
    if entry is not None and entry[0] == "<pending-write>":
        errors.append("%s delta application receipt %s is not persisted in the "
                      "repository" % (item_id, receipt_id))
    if receipt is None:
        return errors
    if receipt.get("tool_version") not in SUPPORTED_APPLY_DELTA_TOOL_VERSIONS:
        errors.append("%s delta application receipt %s has unsupported "
                      "apply_delta producer version %r" %
                      (item_id, receipt_id, receipt.get("tool_version")))
    if receipt.get("tool_version") == APPLY_DELTA_TOOL_VERSION:
        errors.extend(_delta_property_event_errors(
            receipt, "%s delta application receipt %s" %
            (item_id, receipt_id)))
        if root is None:
            errors.append(
                "%s current-era delta application cannot replay property "
                "invalidation without repository root" % item_id)
        else:
            errors.extend(_delta_property_invalidation_errors(
                root, receipt))
        opening_errors, _opening_before = \
            _delta_opening_semantic_binding(
                receipt, catalog,
                "%s delta application receipt %s" %
                (item_id, receipt_id),
                expected_item=item)
        errors.extend(opening_errors)
        errors.extend(_settlement_binding_errors(
            receipt, "%s delta application receipt %s" %
            (item_id, receipt_id)))
        _, merge_transition = _latest_merge_transition(item, catalog)
        if (not isinstance(merge_transition, dict) or
                merge_transition.get("tool") != "update_queue" or
                merge_transition.get("tool_version") !=
                UPDATE_QUEUE_TOOL_VERSION):
            errors.append(
                "%s current delta application has no current-era frozen "
                "merge-ready settlement" % item_id)
        else:
            for field in SETTLEMENT_BINDING_FIELDS:
                if receipt.get(field) != merge_transition.get(field):
                    errors.append(
                        "%s delta application settlement %s does not match "
                        "the frozen merge-ready transition" %
                        (item_id, field))
    if receipt.get("delta_sha256") != item.get("delta_sha256"):
        errors.append("%s delta application receipt does not bind frozen "
                      "delta_sha256" % item_id)
    for field in ("delta_sha256", "before_coverage_sha256",
                  "after_coverage_sha256", "required_queue_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append("%s delta application receipt has invalid %s" %
                          (item_id, field))
    receipt_queue_revision = receipt.get("queue_revision")
    receipt_state_revision = receipt.get("queue_state_revision")
    if (not isinstance(receipt_queue_revision, int) or
            isinstance(receipt_queue_revision, bool) or
            receipt_queue_revision < 1 or
            receipt_queue_revision > queue.get("queue_revision", -1)):
        errors.append("%s delta application receipt has invalid queue_revision" %
                      item_id)
    if (not isinstance(receipt_state_revision, int) or
            isinstance(receipt_state_revision, bool) or
            receipt_state_revision < 0 or
            receipt_state_revision > queue.get("state_revision", -1)):
        errors.append("%s delta application receipt has invalid "
                      "queue_state_revision" % item_id)
    if transition is not None:
        expected = {
            "queue_revision": transition.get("queue_revision"),
            "queue_state_revision": transition.get("before_state_revision"),
            "required_queue_sha256":
                transition.get("before_required_queue_sha256"),
            "after_coverage_sha256":
                transition.get("before_coverage_sha256"),
        }
        for field, value in expected.items():
            if receipt.get(field) != value:
                errors.append("%s delta application receipt %s=%r, expected %r "
                              "from its close transition" %
                              (item_id, field, receipt.get(field), value))
        if transition.get("delta_apply_receipt") != receipt_id:
            errors.append("%s close transition does not bind delta application "
                          "receipt %s" % (item_id, receipt_id))
    return errors


def _applied_rollback_restore_errors(label, record, transition, catalog,
                                     item_id):
    """Cross-check the recorded Coverage restore against both its witnesses.

    ``coverage_restored_sha256`` is the only field in the applied-rollback
    triple that names bytes, so a non-empty check proves nothing: any well-
    formed digest passes.  Two independent records already state what those
    bytes must be.  The delta application being undone archived the pre-apply
    Coverage and recorded its path and digest; the rollback transition receipt
    recorded the Coverage fingerprint the rollback actually left on disk.  A
    truthful restore makes all three the same value, and a restore that put
    other bytes in place disagrees with at least one of them.
    """
    errors = []
    restored_sha = record.get("coverage_restored_sha256")
    restored_from = record.get("coverage_restored_from")
    if not SHA256_RE.fullmatch(restored_sha):
        errors.append("%s coverage_restored_sha256 is invalid" % label)
        restored_sha = None
    if transition is not None:
        after_coverage = transition.get("after_coverage_sha256")
        if not SHA256_RE.fullmatch(after_coverage or ""):
            errors.append("%s rollback transition receipt has no valid "
                          "after_coverage_sha256 to restore against" % label)
        elif restored_sha is not None and restored_sha != after_coverage:
            errors.append(
                "%s records coverage_restored_sha256=%s but its rollback "
                "transition receipt left Coverage at %s" %
                (label, restored_sha, after_coverage))
    apply_receipt = _require_receipt(
        catalog, record.get("delta_apply_receipt"),
        "%s delta application" % label, errors,
        expected={"check": "delta_apply", "target": item_id},
    )
    if apply_receipt is not None:
        archived_path = apply_receipt.get("before_coverage_archive_path")
        archived_sha = apply_receipt.get("before_coverage_sha256")
        if restored_from != archived_path:
            errors.append(
                "%s restores from %r but delta application %s archived the "
                "pre-apply Coverage at %r" %
                (label, restored_from, apply_receipt.get("receipt_id"),
                 archived_path))
        if restored_sha is not None and restored_sha != archived_sha:
            errors.append(
                "%s records coverage_restored_sha256=%s but delta application "
                "%s recorded pre-apply Coverage %s" %
                (label, restored_sha, apply_receipt.get("receipt_id"),
                 archived_sha))
    return errors


def _delta_gap_key(value):
    if isinstance(value, str) and value.strip():
        return ("id", value)
    if not isinstance(value, dict):
        return None
    if _nonempty_string(value.get("id")):
        return ("id", value["id"])
    if (_nonempty_string(value.get("page")) and
            _nonempty_string(value.get("type"))):
        return ("page-type", value["page"], value["type"])
    return None


def _delta_handoff_errors(relative, delta, item, coverage_records,
                          coverage, queue, catalog):
    """Return structural errors, repairable settlement blockers, and report.

    A syntactically or evidentially malformed managed Delta is a runtime
    error.  A well-formed open Delta that has not yet settled every gap routed
    to its batch is ordinary authoring work: it is reported as ``incomplete``
    and the merge-ready writer refuses it, but unrelated runtime readers are
    not wedged while the worker repairs the exact Delta bytes.
    """
    item_id = item.get("id")
    errors = []
    expected_path = ".cambium/deltas/%s.yaml" % item_id
    if relative != expected_path:
        errors.append("path must be exactly %s" % expected_path)
    missing = sorted(DELTA_FIELDS - set(delta))
    extra = sorted(set(delta) - DELTA_FIELDS)
    if missing:
        errors.append("missing field(s): %s" % ", ".join(missing))
    if extra:
        errors.append("unsupported field(s): %s" % ", ".join(extra))
    if delta.get("batch") != item_id:
        errors.append("batch must equal %s" % item_id)
    if not _valid_timestamp(delta.get("generated_at")):
        errors.append("generated_at must be a timezone-aware RFC 3339 timestamp")
    if delta.get("watermark_advance") not in (None, [], {}):
        errors.append("watermark_advance needs a registered instance adapter")
    if not isinstance(delta.get("next_batch_updates"), list):
        errors.append("next_batch_updates must be an explicit list")

    pages = delta.get("pages")
    manifest = item.get("manifest") if isinstance(item.get("manifest"), list) \
        else []
    page_paths = []
    if not isinstance(pages, list):
        errors.append("pages must be an explicit list")
        pages = []
    for index, page in enumerate(pages):
        label = "pages[%d]" % index
        if not isinstance(page, dict):
            errors.append("%s must be a mapping" % label)
            continue
        forbidden = sorted(DELTA_CONTROL_FIELDS.intersection(page))
        if forbidden:
            errors.append("%s contains control field(s): %s" %
                          (label, ", ".join(forbidden)))
        path = page.get("path")
        if not _nonempty_string(path):
            errors.append("%s path must be a non-empty string" % label)
            continue
        page_paths.append(path)
        record = coverage_records.get(path)
        if record is None:
            errors.append("%s is absent from Coverage" % path)
        elif record.get("next_batch") != item_id and \
                record.get("batch") != item_id:
            errors.append("%s is not routed to batch %s" % (path, item_id))
        receipt_ids = page.get("gate_receipts")
        if (not isinstance(receipt_ids, list) or not receipt_ids or
                not all(_nonempty_string(value) for value in receipt_ids)):
            errors.append("%s gate_receipts must be a non-empty string list" %
                          label)
        else:
            if len(receipt_ids) != len(set(receipt_ids)):
                errors.append("%s gate_receipts must be unique" % label)
            for receipt_id in receipt_ids:
                _require_receipt(
                    catalog, receipt_id, "%s page gate" % path, errors,
                    expected={"target": path},
                )
    if len(page_paths) != len(set(page_paths)):
        errors.append("pages repeat a path")
    if len(page_paths) != len(manifest) or set(page_paths) != set(manifest):
        errors.append("pages must equal the frozen manifest exactly")

    additions = delta.get("open_gaps_added")
    closures = delta.get("open_gaps_closed")
    if not isinstance(additions, list):
        errors.append("open_gaps_added must be an explicit list")
        additions = []
    if not isinstance(closures, list):
        errors.append("open_gaps_closed must be an explicit list")
        closures = []
    current_gaps = coverage.get("open_gaps")
    if not isinstance(current_gaps, list):
        current_gaps = []
    current_keys = [_delta_gap_key(gap) for gap in current_gaps]
    if None in current_keys or len(current_keys) != len(set(current_keys)):
        errors.append("Coverage open_gaps do not have unique stable identities")
    close_keys = [_delta_gap_key(value) for value in closures]
    add_keys = [_delta_gap_key(value) for value in additions]
    if None in close_keys:
        errors.append("open_gaps_closed contains an invalid selector")
    if None in add_keys:
        errors.append("open_gaps_added contains a gap without id or page+type")
    if len(close_keys) != len(set(close_keys)):
        errors.append("open_gaps_closed repeats a gap identity")
    if len(add_keys) != len(set(add_keys)):
        errors.append("open_gaps_added repeats a gap identity")
    if set(close_keys).intersection(add_keys):
        errors.append("one delta cannot close and add the same gap")
    for key in close_keys:
        if key is not None and key not in current_keys:
            errors.append("open_gaps_closed references an absent gap %r" %
                          (key,))
    for gap, key in zip(additions, add_keys):
        if key is not None and key in current_keys:
            errors.append("open_gaps_added already exists %r" % (key,))
        if isinstance(gap, dict) and gap.get("page") not in coverage_records:
            errors.append("open gap page is absent from Coverage: %s" %
                          gap.get("page"))
    settlement_errors = []
    settlement = None
    if not errors:
        try:
            prospective = coverage_delta.project_open_gaps(coverage, delta)
            settlement = batch_settlement.delta_settlement_report(
                coverage, prospective, delta, queue, item_id)
            settlement_errors = list(settlement.get("errors") or [])
        except (TypeError, ValueError) as exc:
            errors.append("cannot project routed-gap settlement: %s" % exc)
    return errors, settlement_errors, settlement


def _delta_apply_receipt_candidates(item, catalog, queue, queue_sha,
                                    coverage_sha, *, root=None,
                                    coverage=None, profile_view=None):
    """Classify unconsumed apply receipts for one merge-ready batch."""
    batch_id = item.get("id")
    expected = {
        "tool_version": APPLY_DELTA_TOOL_VERSION,
        "task_id": queue.get("task_id"),
        "actor_role": "integrator",
        "coverage_ledger_path": COVERAGE_PATH,
        "delta_path": item.get("delta_path"),
        "delta_sha256": item.get("delta_sha256"),
        "after_coverage_sha256": coverage_sha,
        "required_queue_sha256": queue_sha,
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
    }
    _, merge_transition = _latest_merge_transition(item, catalog)
    if (isinstance(merge_transition, dict) and
            merge_transition.get("tool") == "update_queue" and
            merge_transition.get("tool_version") ==
            UPDATE_QUEUE_TOOL_VERSION):
        for field in SETTLEMENT_BINDING_FIELDS:
            expected[field] = merge_transition.get(field)
    compatible = []
    stale = []
    for receipt_id in sorted(catalog):
        relative, receipt = catalog[receipt_id]
        if not (receipt.get("tool") == "apply_delta" and
                receipt.get("check") == "delta_apply" and
                receipt.get("target") == batch_id and
                receipt.get("batch_id") == batch_id and
                receipt.get("result") == "pass" and
                receipt.get("invalidated_by") is None):
            continue
        # A batch id can survive a merge-ready -> open rollback and a later
        # revalidation round.  Receipts from an older round are history, not
        # evidence that the current delta bytes were applied.  Anchor the
        # critical section to both immutable identities of this attempt before
        # judging its Queue/Coverage binding as current or stale.
        if (receipt.get("delta_path") != item.get("delta_path") or
                receipt.get("delta_sha256") != item.get("delta_sha256")):
            continue
        mismatches = [field for field, value in expected.items()
                      if receipt.get(field) != value]
        if receipt.get("tool_version") == APPLY_DELTA_TOOL_VERSION:
            if not (isinstance(merge_transition, dict) and
                    merge_transition.get("tool_version") ==
                    UPDATE_QUEUE_TOOL_VERSION):
                mismatches.append("merge_ready_settlement")
            mismatches.extend(_settlement_binding_errors(
                receipt, "delta application %s" % receipt_id))
            mismatches.extend(_delta_property_event_errors(
                receipt, "delta application %s" % receipt_id))
            if (root is not None and isinstance(coverage, dict) and
                    isinstance(profile_view, dict)):
                mismatches.extend(_delta_property_invalidation_errors(
                    root, receipt, coverage, profile_view))
        before_coverage = receipt.get("before_coverage_sha256")
        if (not isinstance(before_coverage, str) or
                not SHA256_RE.fullmatch(before_coverage)):
            mismatches.append("before_coverage_sha256")
        declared_path = receipt.get("receipt_path")
        if (relative != "<pending-write>" and declared_path is not None and
                declared_path != relative):
            mismatches.append("receipt_path")
        if mismatches:
            stale.append({
                "batch": batch_id,
                "receipt": receipt_id,
                "mismatched_fields": sorted(set(mismatches)),
            })
        else:
            compatible.append(receipt_id)
    return compatible, stale


def delta_apply_write_barrier(result, tool, action, target=None):
    """Return a fail-closed writer error while an apply awaits Queue close.

    An applied delta opens a strict serial critical section: Coverage already
    carries the batch content while the Queue still says ``merge-ready``.  Two
    writes close that window, and no others.  ``merge-ready -> closed`` is the
    passing outcome.  ``merge-ready -> open`` is the failing one, required by
    K00/10, K12/14 and K13/10 whenever the Batch-close Closed List rejects the
    merge -- which can only happen after the apply, because the Closed List
    runs against the merged snapshot.  The rollback carries its own evidence
    (the invalidated delta archive and a byte-exact Coverage restore), so it
    leaves the ledgers reconciled rather than diverged.
    """
    standards_barrier = (result.get("standards_revalidation_barriers") or {}).get(
        target)
    if standards_barrier and action in ("apply", "merge-ready", "closed"):
        return standards_barrier
    pending = result.get("pending_delta_applies") or {}
    if pending.get("status") != "close-required":
        return None
    current = pending.get("current") or []
    if len(current) != 1:
        return ("pending delta_apply state is ambiguous; repair the runtime "
                "before any Queue/Coverage write")
    applied = current[0]
    if (tool == "update_queue" and action in ("closed", "open") and
            target == applied.get("batch")):
        return None
    return ("batch %s already has current-compatible unconsumed delta_apply "
            "receipt %s; the only allowed Queue/Coverage writes are "
            "update_queue merge-ready->closed and the integrator-authorised "
            "merge-ready->open rollback for that batch" %
            (applied.get("batch"), applied.get("selected_receipt")))
