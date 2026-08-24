"""One whole-repository consistency pass.

Composes every section validator over canonical Queue, Coverage and Progress
state and returns the authorized runtime result without writing anything,
plus the build-completion predicate asked of that result.

This module has seventeen in-package dependencies and is where a new section
validator naturally lands.  That accretion is the thing K00/18 was written
against, so a change that adds an out-edge here without adding a submodule is
a change that should have to be argued.
"""

import os
import sys

import kblib
import maintenance_candidates

from queue_runtime.adoption import _standards_adoption_errors
from queue_runtime.amendments import (
    _cross_ledger_amendment_errors,
    _initial_queue_receipt_errors,
    _pending_cross_ledger_amendments,
    _queue_replan_amendment_errors,
)
from queue_runtime.canon import (
    ACTIVE_STATES,
    APPLY_DELTA_TOOL_VERSION,
    BATCH_ID_RE,
    COVERAGE_PATH,
    EXECUTION_MODES,
    HOLDS,
    PROGRESS_PATH,
    QUEUE_PATH,
    SHA256_RE,
    STATES,
    TASK_STATES,
    TERMINAL_STATES,
)
from queue_runtime.close_gate import _close_gate_reuse_errors
from queue_runtime.control_plane import (
    hub_page_admission,
    profile_hub_paths,
)
from queue_runtime.coverage import (
    _coverage_batch_spec_errors,
    _coverage_provenance_errors,
    _coverage_records,
)
from queue_runtime.delta import (
    _delta_apply_receipt_candidates,
    _delta_handoff_errors,
)
from queue_runtime.item_evidence import _item_evidence_errors
from queue_runtime.locks import (
    _bind_generic_lock_receipts,
    _bind_lock_delta_archives,
    _bind_lock_receipts,
    _bind_lock_state_phases,
    _writer_locks,
)
from queue_runtime.primitives import (
    _acyclic,
    _identity,
    _nonempty_string,
    _valid_timestamp,
)
from queue_runtime.profile_view import (
    _authorized_profile_view_errors,
    _profile_view_snapshot_error,
    active_standards_authorized_view,
    active_standards_view_currency_errors,
    profile_load_authorized_view,
    selected_profile_manifest_errors,
)
from queue_runtime.property_state import (
    _coverage_property_state_errors,
    _legacy_property_state_source_errors,
)
from queue_runtime.receipts import (
    _Catalog,
    _cold_receipt_store,
    _receipt_catalog,
)
from queue_runtime.repofs import (
    _load_state,
    _path_error,
)
from queue_runtime.revalidation import (
    _unresolvable_consumed_aggregate_errors,
    current_attempt_evidence_barrier,
    outstanding_standards_revalidation,
    standards_revalidation_requirements,
)
from queue_runtime.task_progress import (
    _global_transition_errors,
    _progress_shape_errors,
    _task_transition_errors,
)
from queue_runtime.work_spec import _work_spec_errors


REQUIRED_ITEM_FIELDS = (
    "id", "family", "order", "record_count", "manifest", "source_route",
    "execution_mode", "depends_on", "confirmation_required", "state",
    "hold_state", "work_spec_path", "work_spec_sha256",
)
QUEUE_ITEM_FIELDS = frozenset(REQUIRED_ITEM_FIELDS + (
    "transition_receipts", "opened_at", "activation_receipt",
    "confirmation_receipt", "merge_ready_at", "delta_path",
    "delta_sha256", "batch_receipts", "closed_at",
    "queue_consistency_receipt", "close_gate_receipt",
    "delta_apply_receipt", "cancelled_at", "cancellation_amendment",
    "hold_reason", "successor_of", "invalidation_history",
))

HUB_EXIT_HINT = ("K13/10 admits a hub-editing batch only through an exclusive "
                 "or serial-integrator execution mode")


QUEUE_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "task_id", "scope_version", "queue_revision",
    "state_revision", "standards_version", "selected_profile_manifest",
    "required_queue",
))
COVERAGE_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "task_id", "updated_at", "scope_version",
    "standards_version", "selected_profile_manifest", "batch_specs",
    "maintenance_candidates", "pages", "open_gaps",
))
PROGRESS_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "task_id", "task_state", "required_queue_path",
    "queue_revision", "queue_state_revision", "required_queue_sha256",
    "initial_queue_receipt",
    "contract", "checkpoint", "terminal_audit", "maintenance_completion",
    "amendments",
    "standards_adoptions",
    "guidance_queue", "task_transition_receipts",
))


def validate_runtime(root, allowed_open_delta=None,
                     allowed_cancellation_id=None, state_overrides=None,
                     page_projection_overrides=None,
                     extra_receipts=None, allow_unmaterialized_queue=False,
                     allow_structural_drift=False,
                     allow_pending_replan_receipts=False,
                     allow_legacy_property_state_for_migration=False,
                     allow_standards_rollback_batch=None,
                     allow_invalid_current_profile_for_corrective_adoption=
                     False,
                     allow_active_standards_mismatch_for_adoption=False,
                     active_standards_state_override=None,
                     authorized_profile_view=None,
                     authorized_active_standards_view=None,
                     *, gate_evidence_errors):
    """Return a validation result dict without writing any state.

    Full ``profile-load`` is part of the default runtime invariant, so every
    ordinary reader/writer gets the same closure admission as the public CLI.
    The sole escape hatch exists for ``adopt_standards`` to read and replace
    an already-selected invalid Profile.  Even on that path, a valid current
    Profile is evaluated normally and its authorized view is retained; the
    smaller unadmitted identity check is used only when that one producer run
    actually fails.  The escape is intentionally inapplicable to proposed/
    overridden state: the adoption after-image must always pass the full
    invariant.  A caller that already ran
    :func:`profile_load_authorized_view` may inject that exact in-process view;
    its identity, typed contract, and current tree snapshot are rechecked, but
    the expensive producer is not run again.
    """
    if type(allow_invalid_current_profile_for_corrective_adoption) is not bool:
        raise TypeError(
            "allow_invalid_current_profile_for_corrective_adoption must be "
            "boolean")
    if type(allow_active_standards_mismatch_for_adoption) is not bool:
        raise TypeError(
            "allow_active_standards_mismatch_for_adoption must be boolean")
    if (active_standards_state_override is not None and
            (not isinstance(active_standards_state_override, str) or
             state_overrides is None)):
        raise ValueError(
            "active_standards_state_override must be text and requires "
            "proposed state_overrides")
    if page_projection_overrides is not None:
        if state_overrides is None or not isinstance(state_overrides, dict) or \
                COVERAGE_PATH not in state_overrides:
            raise ValueError(
                "page_projection_overrides requires a proposed Coverage "
                "state override")
        if (not isinstance(page_projection_overrides, dict) or
                any(not _nonempty_string(path) or not isinstance(text, str)
                    for path, text in page_projection_overrides.items())):
            raise TypeError(
                "page_projection_overrides must map non-empty page paths "
                "to exact text after-images")
    if type(allow_legacy_property_state_for_migration) is not bool:
        raise TypeError(
            "allow_legacy_property_state_for_migration must be bool")
    if allow_legacy_property_state_for_migration and isinstance(
            state_overrides, dict) and COVERAGE_PATH in state_overrides:
        raise ValueError(
            "legacy property-state migration admission is a persisted "
            "Coverage before-image escape; a proposed Coverage override "
            "must pass the current property-state contract strictly")
    if (allow_active_standards_mismatch_for_adoption and
            not allow_invalid_current_profile_for_corrective_adoption):
        raise ValueError(
            "active Standards mismatch escape is restricted to the same "
            "persisted before-image path as corrective Standards adoption")
    if (allow_invalid_current_profile_for_corrective_adoption and
            (state_overrides is not None or extra_receipts is not None)):
        raise ValueError(
            "corrective Profile escape applies only to persisted current "
            "state, never proposed state or pending receipts")
    if (authorized_profile_view is not None and
            not isinstance(authorized_profile_view, dict)):
        raise TypeError(
            "authorized_profile_view must be a mapping returned by "
            "profile_load_authorized_view")
    if (authorized_active_standards_view is not None and
            not isinstance(authorized_active_standards_view, dict)):
        raise TypeError(
            "authorized_active_standards_view must be a mapping returned by "
            "active_standards_authorized_view")
    if (allow_invalid_current_profile_for_corrective_adoption and
            authorized_profile_view is not None):
        raise ValueError(
            "corrective Profile escape cannot consume an authorized Profile "
            "view")
    if (allow_active_standards_mismatch_for_adoption and
            (state_overrides is not None or extra_receipts is not None or
             authorized_profile_view is not None or
             authorized_active_standards_view is not None)):
        raise ValueError(
            "active Standards mismatch escape cannot validate proposed state, "
            "pending receipts, or an injected after-image Profile view")
    root = os.path.realpath(os.path.abspath(root))
    errors = []
    writer_locks = _writer_locks(root, errors)
    try:
        queue_path, queue_raw, queue = _load_state(
            root, QUEUE_PATH, state_overrides)
        _, coverage_raw, coverage = _load_state(
            root, COVERAGE_PATH, state_overrides)
        _, progress_raw, progress = _load_state(
            root, PROGRESS_PATH, state_overrides)
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        errors.append(str(exc))
        catalog = _receipt_catalog(root, errors)
        _cold_receipt_store(root, errors, catalog)
        _bind_lock_receipts(writer_locks, catalog)
        _bind_lock_state_phases(writer_locks, {
            "coverage": None, "queue": None, "progress": None,
        })
        _bind_lock_delta_archives(root, writer_locks)
        _bind_generic_lock_receipts(root, writer_locks, catalog)
        return {
            "root": root, "errors": errors, "ready": [], "blocked": [],
            "queue": {}, "coverage": {}, "progress": {}, "queue_path": None,
            "coverage_sha256": None, "queue_sha256": None,
            "progress_sha256": None, "remaining": None,
            "receipt_catalog": catalog, "writer_locks": writer_locks,
            "managed_deltas": [], "hub_page_admission": {},
            "legacy_property_state_source_receipt_ids": [],
        }

    coverage_sha = kblib.sha256_bytes(coverage_raw)
    queue_sha = kblib.sha256_bytes(queue_raw)
    progress_sha = kblib.sha256_bytes(progress_raw)
    for data, label in ((queue, "Queue"), (coverage, "Coverage"),
                        (progress, "Progress")):
        if data.get("schema_version") != 1:
            errors.append("%s schema_version must be 1" % label)
    for data, label, fields in (
            (queue, "Queue", QUEUE_TOP_LEVEL_FIELDS),
            (coverage, "Coverage", COVERAGE_TOP_LEVEL_FIELDS),
            (progress, "Progress", PROGRESS_TOP_LEVEL_FIELDS)):
        missing = sorted(set(fields) - set(data))
        extra = sorted(set(data) - set(fields))
        if missing:
            errors.append("%s misses required top-level field(s): %s" %
                          (label, ", ".join(missing)))
        if extra:
            errors.append("%s has unsupported top-level field(s): %s" %
                          (label, ", ".join(extra)))
    errors.extend(_progress_shape_errors(progress))
    for field in ("batch_specs", "maintenance_candidates", "pages",
                  "open_gaps"):
        if not isinstance(coverage.get(field), list):
            errors.append("Coverage %s must be an explicit list" % field)
    if not _valid_timestamp(coverage.get("updated_at")):
        errors.append("Coverage updated_at must be a timezone-aware RFC 3339 timestamp")

    task_state = progress.get("task_state")
    if task_state not in TASK_STATES:
        errors.append("Progress task_state has invalid value %r" % task_state)
    contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    completion_semantics = contract.get("completion_semantics")
    candidate_records = coverage.get("maintenance_candidates")
    maintenance_candidate_context = None
    if isinstance(candidate_records, list):
        if completion_semantics == "build" and candidate_records:
            errors.append(
                "build completion semantics requires Coverage "
                "maintenance_candidates=[]"
            )
        elif completion_semantics == "maintenance":
            candidate_errors, maintenance_candidate_context = \
                maintenance_candidates.validate_candidates(
                root, candidate_records, validate_prior=False,
                label="Coverage maintenance_candidates",
            )
            errors.extend(candidate_errors)
            page_paths = {
                record.get("path") for record in coverage.get("pages", [])
                if isinstance(record, dict) and
                _nonempty_string(record.get("path"))
            }
            declared_candidate_paths = {
                record.get("object_path") for record in candidate_records
                if isinstance(record, dict) and
                _nonempty_string(record.get("object_path"))
            }
            missing_candidates = sorted(
                set(maintenance_candidate_context["selected_objects"]).union(
                    declared_candidate_paths) - page_paths
            )
            if missing_candidates:
                errors.append(
                    "Coverage maintenance candidates are absent from pages: %s" %
                    ", ".join(missing_candidates)
                )

    for key in ("task_id", "scope_version", "standards_version",
                "selected_profile_manifest"):
        qvalue = queue.get(key)
        cvalue = coverage.get(key)
        pvalue = _identity(progress, key, nested=(key not in ("task_id",)))
        if not _nonempty_string(qvalue):
            errors.append("Queue %s must be instantiated" % key)
        if qvalue != cvalue or qvalue != pvalue:
            errors.append("%s differs across Queue/Coverage/Progress: %r / %r / %r" %
                          (key, qvalue, cvalue, pvalue))

    active_standards_view = None
    if allow_active_standards_mismatch_for_adoption:
        # As with the corrective Profile path below, permission to replace a
        # mismatched authority is not proof that the persisted before image
        # is mismatched.  Retain a valid immutable K00/03 view whenever its
        # single producer attempt succeeds; only a real mismatch uses the
        # identity escape and leaves the before view absent.
        active_standards_view, active_errors = \
            active_standards_authorized_view(
                root, queue.get("standards_version"),
                queue.get("selected_profile_manifest"))
        if active_errors:
            active_standards_view = None
    else:
        if authorized_active_standards_view is None:
            active_standards_view, active_errors = \
                active_standards_authorized_view(
                    root, queue.get("standards_version"),
                    queue.get("selected_profile_manifest"),
                    state_override=active_standards_state_override)
        else:
            active_standards_view = authorized_active_standards_view
            active_errors = []
            for field, expected in (
                    ("standards_version", queue.get("standards_version")),
                    ("selected_profile_manifest",
                     queue.get("selected_profile_manifest"))):
                if active_standards_view.get(field) != expected:
                    active_errors.append(
                        "authorized active Standards view %s=%r, expected "
                        "runtime %r" % (
                            field, active_standards_view.get(field), expected))
            if not active_errors:
                active_errors.extend(active_standards_view_currency_errors(
                    root, active_standards_view))
        errors.extend(active_errors)

    profile = queue.get("selected_profile_manifest")
    profile_view = None
    if _nonempty_string(profile):
        if allow_invalid_current_profile_for_corrective_adoption:
            # Corrective adoption is not synonymous with an invalid current
            # Profile.  Preserve the full authorized before-view whenever the
            # canonical producer succeeds, so current opening/property
            # evidence remains verifiable.  Only an actual producer failure
            # falls back to the deliberately smaller manifest identity path;
            # the producer is never rerun in either branch.
            profile_view, profile_errors = profile_load_authorized_view(
                root, profile)
            if profile_errors:
                profile_view = None
                errors.extend(selected_profile_manifest_errors(root, profile))
        elif authorized_profile_view is not None:
            profile_errors = _authorized_profile_view_errors(
                root, profile, authorized_profile_view)
            errors.extend(profile_errors)
            if not profile_errors:
                profile_view = authorized_profile_view
        else:
            profile_view, profile_errors = profile_load_authorized_view(
                root, profile)
            errors.extend(profile_errors)
    elif authorized_profile_view is not None:
        errors.append("authorized Profile view cannot be injected when Queue "
                      "selected_profile_manifest is uninstantiated")

    for key in ("queue_revision", "state_revision"):
        value = queue.get(key)
        minimum = 1 if key == "queue_revision" else 0
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            errors.append("Queue %s must be an integer >= %d" % (key, minimum))

    if progress.get("required_queue_path") != QUEUE_PATH:
        errors.append("Progress required_queue_path must be %s" % QUEUE_PATH)
    if progress.get("queue_revision") != queue.get("queue_revision"):
        errors.append("Progress queue_revision does not match Queue")
    if progress.get("queue_state_revision") != queue.get("state_revision"):
        errors.append("Progress queue_state_revision does not match Queue")
    recorded_sha = progress.get("required_queue_sha256")
    if not isinstance(recorded_sha, str) or not SHA256_RE.fullmatch(recorded_sha):
        errors.append("Progress required_queue_sha256 is not sha256:<64 lowercase hex>")
    elif recorded_sha != queue_sha:
        errors.append("Progress required_queue_sha256 does not match current Queue bytes")

    catalog = _receipt_catalog(root, errors)
    cold_store = _cold_receipt_store(root, errors, catalog)
    _bind_lock_receipts(writer_locks, catalog)
    _bind_lock_state_phases(writer_locks, {
        "coverage": coverage_sha,
        "queue": queue_sha,
        "progress": progress_sha,
        "standards": (active_standards_view or {}).get(
            "active_standards_sha256"),
    })
    _bind_lock_delta_archives(root, writer_locks)
    _bind_generic_lock_receipts(root, writer_locks, catalog)
    for receipt in extra_receipts or []:
        if not isinstance(receipt, dict) or not _nonempty_string(
                receipt.get("receipt_id")):
            errors.append("pending receipt must be a mapping with receipt_id")
            continue
        receipt_id = receipt["receipt_id"]
        if receipt_id in catalog:
            errors.append("pending receipt_id duplicates existing evidence: %s" %
                          receipt_id)
            continue
        catalog[receipt_id] = ("<pending-write>", receipt)
    errors.extend(_standards_adoption_errors(
        root, progress, catalog, queue, active_standards_view))
    invalidated_evidence_receipt_ids = {
        receipt_id
        for adoption in (progress.get("standards_adoptions") or [])
        if isinstance(adoption, dict)
        for receipt_id in (
            adoption.get("invalidated_evidence_receipt_ids") or [])
        if _nonempty_string(receipt_id)
    }
    trusted_content_change_receipts = {
        record.get("evidence_receipt")
        for row in coverage.get("pages") or [] if isinstance(row, dict)
        for record in (row.get("property_state") or {}).values()
        if isinstance(record, dict) and
        _nonempty_string(record.get("evidence_receipt"))
    }
    trusted_content_change_receipts.update(
        item.get("delta_apply_receipt")
        for item in queue.get("required_queue") or []
        if isinstance(item, dict) and
        _nonempty_string(item.get("delta_apply_receipt")))
    # The just-applied merge-ready window has not yet projected its receipt ID
    # into Queue.  Its exact live Coverage/delta binding is nevertheless
    # enough to make the content-change invalidation authoritative now.
    trusted_content_change_receipts.update(
        receipt_id for receipt_id, entry in catalog.items()
        if isinstance(entry, tuple) and isinstance(entry[1], dict) and
        entry[1].get("tool") == "apply_delta" and
        entry[1].get("tool_version") == APPLY_DELTA_TOOL_VERSION and
        entry[1].get("check") == "delta_apply" and
        entry[1].get("result") == "pass" and
        entry[1].get("invalidated_by") is None and
        entry[1].get("after_coverage_sha256") == coverage_sha and
        any(isinstance(item, dict) and item.get("state") == "merge-ready" and
            item.get("id") == entry[1].get("target") and
            item.get("delta_path") == entry[1].get("delta_path") and
            item.get("delta_sha256") == entry[1].get("delta_sha256")
            for item in queue.get("required_queue") or []))
    content_invalidated_receipt_ids = set()
    for receipt_id in trusted_content_change_receipts:
        entry = catalog.get(receipt_id)
        receipt = entry[1] if isinstance(entry, tuple) else None
        if not (isinstance(receipt, dict) and
                receipt.get("tool") == "apply_delta" and
                receipt.get("tool_version") == APPLY_DELTA_TOOL_VERSION and
                receipt.get("check") == "delta_apply" and
                receipt.get("result") == "pass" and
                receipt.get("invalidated_by") is None):
            continue
        for event in receipt.get("property_events") or []:
            if not isinstance(event, dict):
                continue
            values = event.get("invalidated_property_receipt_ids")
            if isinstance(values, list):
                content_invalidated_receipt_ids.update(
                    value for value in values if _nonempty_string(value))
    invalidated_evidence_receipt_ids.update(
        content_invalidated_receipt_ids)
    # Historical transition/close validation keeps the full catalog.  Only
    # current-use admission, handoff, reuse, and completion queries consume
    # this adoption-aware view, so history is never rewritten or made invalid
    # merely because it was produced under an older Standards identity.
    current_catalog = _Catalog({
        receipt_id: entry for receipt_id, entry in catalog.items()
        if receipt_id not in invalidated_evidence_receipt_ids
    })
    # Sealed history is by definition not current evidence for any
    # current-use gate; the cold index rides along for existence resolution
    # only, and _require_receipt refuses field revalidation against it.
    current_catalog.cold = catalog.cold
    errors.extend(_initial_queue_receipt_errors(
        progress, catalog, queue, queue_sha, coverage_sha,
    ))
    errors.extend(_cross_ledger_amendment_errors(
        root, progress, current_catalog, catalog, queue,
        coverage_sha, queue_sha, progress_sha,
    ))
    errors.extend(_queue_replan_amendment_errors(
        root, progress, current_catalog, catalog, queue, queue_sha,
        coverage_sha, progress_sha,
        allow_pending_receipts=allow_pending_replan_receipts,
    ))
    pending_operational = _pending_cross_ledger_amendments(progress)
    if len(pending_operational) > 1:
        errors.append(
            "Progress has %d pending operational Amendments; exactly one "
            "may be registered at a time" % len(pending_operational)
        )

    items = queue.get("required_queue")
    if not isinstance(items, list):
        errors.append("Queue required_queue must be an explicit list")
        items = []
    items_by_id = {}
    orders = {}
    manifest_owners = {}
    records, assignments = _coverage_records(root, coverage, errors)
    legacy_property_state_source_receipt_ids = []
    if profile_view is not None:
        errors.extend(_coverage_property_state_errors(
            root, coverage, current_catalog, queue, profile_view,
            active_standards_view,
            page_projection_overrides=page_projection_overrides,
            allow_legacy_missing=
                allow_legacy_property_state_for_migration,
            gate_evidence_errors=gate_evidence_errors))
        # A proposed Coverage override is still inside its sole writer's
        # preflight; the writer-specific planner proves its before/after set
        # and the ordinary persisted validation below resolves the landed
        # receipt.  Treating a not-yet-emitted append-only receipt as absent
        # here would make an atomic first adoption impossible.
        if not (isinstance(state_overrides, dict) and
                COVERAGE_PATH in state_overrides):
            legacy_errors, legacy_property_state_source_receipt_ids = \
                _legacy_property_state_source_errors(
                    coverage, progress, catalog)
            errors.extend(legacy_errors)
    context = {"root": root, "profile_view": profile_view}

    # Closing a successor batch transfers Coverage ``batch`` ownership
    # forward (K12/03: Coverage names the most recent closed owner), so a
    # closed predecessor's immutable manifest is resolved through the
    # ``successor_of`` chain instead of demanding the live assignment it no
    # longer holds.  The chain walk is bounded by the Queue size.
    successor_parent = {
        entry.get("id"): entry.get("successor_of")
        for entry in items
        if isinstance(entry, dict) and _nonempty_string(entry.get("id"))
    }

    def _assigned_through_successors(item_id, assigned_ids):
        for assigned in assigned_ids:
            current, seen = assigned, set()
            while current is not None and current not in seen:
                if current == item_id:
                    return True
                seen.add(current)
                current = successor_parent.get(current)
        return False

    for index, item in enumerate(items):
        label = "required_queue[%d]" % index
        if not isinstance(item, dict):
            errors.append("%s must be a mapping" % label)
            continue
        missing = [field for field in REQUIRED_ITEM_FIELDS if field not in item]
        if missing:
            errors.append("%s misses explicit field(s): %s" %
                          (label, ", ".join(missing)))
        extra = sorted(set(item) - QUEUE_ITEM_FIELDS)
        if extra:
            errors.append("%s has unsupported field(s): %s" %
                          (label, ", ".join(extra)))
        item_id = item.get("id")
        if not _nonempty_string(item_id) or not BATCH_ID_RE.fullmatch(item_id):
            errors.append("%s id must match %s" %
                          (label, BATCH_ID_RE.pattern.replace("\\Z", "")))
            continue
        if item_id in items_by_id:
            errors.append("Queue repeats id %s" % item_id)
            continue
        items_by_id[item_id] = item
        if not _nonempty_string(item.get("family")):
            errors.append("%s family must be a non-empty string" % item_id)
        order = item.get("order")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            errors.append("%s order must be a positive integer" % item_id)
        elif order in orders:
            errors.append("Queue repeats order %s for %s and %s" %
                          (order, orders[order], item_id))
        else:
            orders[order] = item_id
        if item.get("source_route") is not None and not _nonempty_string(
                item.get("source_route")):
            errors.append("%s source_route must be a string or null" % item_id)
        if item.get("execution_mode") not in EXECUTION_MODES:
            errors.append("%s execution_mode must be concurrent-worker or "
                          "serial-integrator" % item_id)
        if not isinstance(item.get("confirmation_required"), bool):
            errors.append("%s confirmation_required must be boolean" % item_id)
        elif (item.get("hold_state") == "confirmation-required" and
              item.get("confirmation_required") is not True):
            errors.append("%s confirmation-required hold needs "
                          "confirmation_required=true" % item_id)
        if item.get("state") not in STATES:
            errors.append("%s has invalid state %r" % (item_id, item.get("state")))
        if item.get("hold_state") not in HOLDS:
            errors.append("%s has invalid hold_state %r" %
                          (item_id, item.get("hold_state")))

        manifest = item.get("manifest")
        if not isinstance(manifest, list):
            errors.append("%s manifest must be an explicit list" % item_id)
            manifest = []
        elif not manifest:
            errors.append("%s manifest must be non-empty; aggregate/zero-record "
                          "items are forbidden" % item_id)
        seen_manifest = set()
        for object_path in manifest:
            if not _nonempty_string(object_path):
                errors.append("%s manifest contains a non-string/empty path" % item_id)
                continue
            if object_path in seen_manifest:
                errors.append("%s manifest repeats %s" % (item_id, object_path))
                continue
            seen_manifest.add(object_path)
            path_error = _path_error(root, object_path, must_exist=False)
            if path_error:
                errors.append("%s manifest path %r is unsafe: %s" %
                              (item_id, object_path, path_error))
            if object_path not in records:
                errors.append("%s manifest path %s has no Coverage record" %
                              (item_id, object_path))
            else:
                disposition = records[object_path].get("coverage_disposition")
                cancellation_staging = (
                    item_id == allowed_cancellation_id and
                    item.get("state") in ("queued", "open")
                )
                if (item.get("state") != "cancelled" and
                        not cancellation_staging and
                        not allow_structural_drift and
                        disposition != "required"):
                    errors.append("%s manifest path %s has non-Required Coverage "
                                  "disposition %r" %
                                  (item_id, object_path, disposition))
                assigned_ids = assignments.get(object_path, [])
                if (not allow_structural_drift and
                        item_id not in assigned_ids and
                        not (item.get("state") == "closed" and
                             _assigned_through_successors(
                                 item_id, assigned_ids))):
                    errors.append("%s manifest path %s is not assigned to that batch in Coverage" %
                                  (item_id, object_path))
            manifest_owners.setdefault(object_path, []).append(item_id)
        count = item.get("record_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            errors.append("%s record_count must be a positive integer" % item_id)
        elif count != len(manifest):
            errors.append("%s record_count=%s but manifest has %d object(s)" %
                          (item_id, count, len(manifest)))

        errors.extend(_work_spec_errors(root, item))

        dependencies = item.get("depends_on")
        if not isinstance(dependencies, list):
            errors.append("%s depends_on must be an explicit list" % item_id)
        else:
            seen_dep = set()
            for dep in dependencies:
                if not _nonempty_string(dep):
                    errors.append("%s depends_on contains an invalid id" % item_id)
                elif dep == item_id:
                    errors.append("%s depends on itself" % item_id)
                elif dep in seen_dep:
                    errors.append("%s repeats dependency %s" % (item_id, dep))
                seen_dep.add(dep)

        errors.extend(_item_evidence_errors(
            item, progress, context, catalog, current_catalog, queue
        ))

    if items_by_id or not allow_unmaterialized_queue:
        errors.extend(_coverage_batch_spec_errors(coverage, items_by_id))

    if (completion_semantics == "maintenance" and items_by_id and
            maintenance_candidate_context is not None and
            not allow_structural_drift):
        queue_objects = sorted({
            object_path for item in items_by_id.values()
            for object_path in (item.get("manifest") or [])
        })
        selected_objects = sorted(set(
            maintenance_candidate_context["selected_objects"]))
        if queue_objects != selected_objects:
            errors.append(
                "maintenance Queue manifest union must equal selected "
                "Coverage candidate objects; queue=%r selected=%r" %
                (queue_objects, selected_objects)
            )

    if orders and set(orders) != set(range(1, len(orders) + 1)):
        errors.append("Queue order values must be contiguous from 1")

    # Coverage assignments and Queue manifests are two explicit views of the
    # same relation; neither side may silently contain an extra association.
    for object_path, batch_ids in assignments.items():
        for batch_id in batch_ids:
            item = items_by_id.get(batch_id)
            if item is None:
                if not ((allow_unmaterialized_queue and not items_by_id) or
                        allow_structural_drift):
                    errors.append("Coverage %s references unknown batch %s" %
                                  (object_path, batch_id))
            elif (not allow_structural_drift and
                  object_path not in (item.get("manifest") or [])):
                errors.append("Coverage assigns %s to %s but Queue manifest omits it" %
                              (object_path, batch_id))

    for item_id, item in items_by_id.items():
        order = item.get("order")
        for dep in item.get("depends_on", []) if isinstance(
                item.get("depends_on"), list) else []:
            dependency = items_by_id.get(dep)
            if dependency is None:
                errors.append("%s depends on unknown batch %s" % (item_id, dep))
            elif isinstance(order, int) and isinstance(dependency.get("order"), int) and \
                    dependency["order"] >= order:
                errors.append("%s dependency %s must have a lower order" %
                              (item_id, dep))
        predecessor_id = item.get("successor_of")
        if predecessor_id is not None:
            predecessor = items_by_id.get(predecessor_id)
            if (not _nonempty_string(predecessor_id) or
                    not BATCH_ID_RE.fullmatch(predecessor_id)):
                errors.append("%s successor_of must be null or a valid batch id" %
                              item_id)
            elif predecessor is None:
                errors.append("%s successor_of references unknown batch %s" %
                              (item_id, predecessor_id))
            elif predecessor_id == item_id:
                errors.append("%s cannot be its own successor" % item_id)
            elif (isinstance(order, int) and
                  isinstance(predecessor.get("order"), int) and
                  predecessor["order"] >= order):
                errors.append("%s successor_of %s must have a lower order" %
                              (item_id, predecessor_id))
    cycle = _acyclic(items_by_id)
    if cycle:
        errors.append("Queue dependency cycle: %s" % " -> ".join(cycle))

    # Readiness is not only a prospective queued calculation.  A resumed or
    # hand-edited state must prove that every batch which ever crossed into
    # execution had all of its declared dependencies closed.
    for item_id, item in items_by_id.items():
        if item.get("state") not in ("open", "merge-ready", "closed"):
            continue
        for dep in item.get("depends_on", []):
            dependency = items_by_id.get(dep)
            if dependency is not None and dependency.get("state") != "closed":
                errors.append("%s is %s but dependency %s is %s, not closed" %
                              (item_id, item.get("state"), dep,
                               dependency.get("state")))

    errors.extend(_global_transition_errors(
        items_by_id, catalog, queue, queue_sha,
    ))
    errors.extend(_close_gate_reuse_errors(items_by_id))
    errors.extend(_coverage_provenance_errors(
        progress, queue, catalog, coverage_sha, queue_sha,
    ))

    # Coverage `next_batch` is the explicit route for unfinished Required
    # objects.  Historical `batch` may remain after close, but a Required
    # object assigned to any non-terminal work may not omit next_batch.
    for object_path, record in records.items():
        if record.get("coverage_disposition") != "required":
            continue
        assigned = [items_by_id[batch_id] for batch_id in assignments.get(object_path, [])
                    if batch_id in items_by_id]
        unfinished = [item for item in assigned
                      if item.get("state") in ("queued", "open") and
                      item.get("id") != allowed_cancellation_id]
        next_batch = record.get("next_batch")
        if unfinished:
            if not _nonempty_string(next_batch):
                errors.append("unfinished Required object %s has no explicit next_batch" %
                              object_path)
            elif (next_batch not in items_by_id or
                  items_by_id[next_batch].get("state") in TERMINAL_STATES):
                errors.append("Required object %s next_batch %r is not a "
                              "non-terminal Queue item" %
                              (object_path, next_batch))

    # Managed Delta inventory.  A complete, compatible Delta beside an open
    # batch is a durable worker handoff and resume candidate; malformed or
    # mismatched handoffs fail closed.  update_queue may name the same open
    # Delta so its admission path can return the more specific policy error.
    # Once merge-ready, the Queue's frozen path and SHA remain authoritative.
    delta_dir = os.path.join(root, ".cambium", "deltas")
    delta_by_batch = {}
    managed_deltas = []
    if os.path.lexists(delta_dir):
        try:
            delta_real = os.path.realpath(delta_dir)
            if os.path.commonpath((root, delta_real)) != root:
                errors.append(".cambium/deltas resolves outside repository root")
            elif not os.path.isdir(delta_dir):
                errors.append(".cambium/deltas must be a directory")
            else:
                for name in sorted(os.listdir(delta_dir)):
                    if not name.endswith((".yaml", ".yml")):
                        continue
                    relative = ".cambium/deltas/%s" % name
                    full = os.path.join(delta_dir, name)
                    if not os.path.isfile(full) or os.path.islink(full):
                        errors.append("managed delta is not a regular in-repository file: %s" %
                                      relative)
                        continue
                    try:
                        delta = kblib.load_yaml_file(full)
                    except (OSError, ValueError, kblib.YamlSubsetError) as exc:
                        errors.append("cannot parse managed delta %s: %s" %
                                      (relative, exc))
                        managed_deltas.append({
                            "path": relative, "batch": None, "state": None,
                        })
                        continue
                    batch_id = delta.get("batch")
                    item = items_by_id.get(batch_id) if _nonempty_string(batch_id) else None
                    delta_record = {
                        "path": relative,
                        "batch": batch_id if _nonempty_string(batch_id) else None,
                        "state": item.get("state") if item else None,
                        "sha256": kblib.sha256_file(full),
                        "handoff_status": None,
                        "handoff_errors": [],
                    }
                    managed_deltas.append(delta_record)
                    if not _nonempty_string(batch_id):
                        errors.append("managed delta %s has no batch id" % relative)
                        continue
                    if batch_id in delta_by_batch:
                        errors.append("multiple managed deltas target batch %s" % batch_id)
                    delta_by_batch[batch_id] = relative
                    item = items_by_id.get(batch_id)
                    if item is None:
                        errors.append("managed delta %s targets unknown batch %s" %
                                      (relative, batch_id))
                        continue
                    state = item.get("state")
                    if state == "open":
                        structural_errors, settlement_errors, settlement = \
                            _delta_handoff_errors(
                            relative, delta, item, records, coverage,
                            queue, current_catalog,
                        )
                        handoff_errors = structural_errors + settlement_errors
                        if structural_errors:
                            delta_record["handoff_status"] = "invalid"
                        elif settlement_errors:
                            delta_record["handoff_status"] = "incomplete"
                        else:
                            delta_record["handoff_status"] = "candidate"
                        delta_record["handoff_errors"] = handoff_errors
                        if settlement is not None:
                            delta_record["routed_gap_settlement"] = settlement
                        # ``allowed_open_delta`` lets a preflight inspect an
                        # incomplete handoff; it never legalizes malformed
                        # paths, evidence, or Delta structure.
                        errors.extend(
                            "open delta %s is not an admissible handoff: %s" %
                            (relative, error) for error in structural_errors
                        )
                    elif state in ("queued", "cancelled"):
                        errors.append("unapplied delta %s exists for %s batch %s" %
                                      (relative, state, batch_id))
                    if state in ("merge-ready", "closed") and \
                            item.get("delta_path") != relative:
                        errors.append("%s batch %s delta_path does not identify %s" %
                                      (state, batch_id, relative))
        except (OSError, ValueError) as exc:
            errors.append("cannot inventory .cambium/deltas: %s" % exc)

    for item_id, item in items_by_id.items():
        if item.get("state") in ("merge-ready", "closed"):
            delta_path = item.get("delta_path")
            if delta_by_batch.get(item_id) != delta_path:
                errors.append("%s batch %s has no matching managed delta" %
                              (item.get("state"), item_id))

    # Cancellation changes disposition; it cannot erase still-Required work.
    for item_id, item in items_by_id.items():
        if item.get("state") == "cancelled":
            for path in item.get("manifest", []):
                record = records.get(path, {})
                if record.get("coverage_disposition") == "required":
                    errors.append("cancelled %s still contains Required Coverage object %s" %
                                  (item_id, path))
        if item.get("state") in TERMINAL_STATES:
            for path in item.get("manifest", []):
                if records.get(path, {}).get("next_batch") == item_id:
                    errors.append("terminal %s remains next_batch for %s" %
                                  (item_id, path))

    active = [item for item in items_by_id.values()
              if item.get("state") in ACTIVE_STATES]
    contract = progress.get("contract") if isinstance(progress.get("contract"), dict) else {}
    cap = contract.get("concurrency_cap")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        errors.append("Progress contract.concurrency_cap must be a positive integer")
        cap = 0
    if cap and len(active) > cap:
        errors.append("active batch count %d exceeds concurrency_cap %d" %
                      (len(active), cap))
    if len(active) > 1 and any(item.get("execution_mode") ==
                               "serial-integrator" for item in active):
        errors.append("serial-integrator batch cannot run concurrently")
    for left_index, left in enumerate(active):
        left_manifest = set(left.get("manifest") or [])
        for right in active[left_index + 1:]:
            overlap = sorted(left_manifest.intersection(right.get("manifest") or []))
            if overlap:
                errors.append("active manifests overlap for %s and %s: %s" %
                              (left.get("id"), right.get("id"), ", ".join(overlap)))

    ready = []
    blocked = []
    closed_ids = {item_id for item_id, item in items_by_id.items()
                  if item.get("state") == "closed"}
    active_manifest = set()
    for item in active:
        active_manifest.update(item.get("manifest") or [])
    # K13/10 admission condition 2.  Derived once per run and only for the
    # queued items whose activation the condition governs.
    registered_hub_paths, hub_derivation_errors = profile_hub_paths(
        root, queue.get("selected_profile_manifest"),
        authorized_view=profile_view, evaluate_if_missing=False,
        # The corrective flag permits an unadmitted derivation only when the
        # one canonical producer actually failed above.  A valid current
        # Profile keeps its authorized typed view throughout the same run.
        allow_unadmitted_profile=(
            allow_invalid_current_profile_for_corrective_adoption and
            profile_view is None))
    if profile_view is not None and hub_derivation_errors:
        # A successfully authorized view becoming unreadable or stale is a
        # runtime invariant failure even when no queued concurrent batch needs
        # hub classification today.  Readiness reasons below remain useful to
        # the operator, but they cannot be the only place this A/B-revision
        # violation is visible.
        errors.extend("selected Profile authorized view: %s" % error
                      for error in hub_derivation_errors)
    hub_page_cache = {}
    hub_admission = {}
    structural_admission_defects = []
    for item_id, item in items_by_id.items():
        if item.get("state") != "queued":
            continue
        reasons = []
        if item.get("execution_mode") != "serial-integrator":
            hub = hub_page_admission(
                root, item.get("manifest"), records, registered_hub_paths,
                hub_page_cache)
            hub_admission[item_id] = hub
            for reason in hub_derivation_errors:
                reasons.append("%s; %s" % (reason, HUB_EXIT_HINT))
            if hub["blocking"]:
                reasons.append(
                    "batch edits existing control or hub page(s): %s; %s" %
                    (", ".join(hub["blocking"]), HUB_EXIT_HINT))
                # K13/10 condition 2 does not depend on which batch is being
                # admitted today: a queued batch whose manifest edits an
                # existing hub page can never reach `open` while its
                # execution_mode stays concurrent, and only a structural
                # Amendment can change that.  Reported through readiness
                # alone the defect stays invisible until the batch reaches
                # the head of the queue, so the same class is rediscovered
                # one batch at a time; surfaced here it is visible for the
                # whole Queue at once.  It stays a candidate rather than an
                # error because the repair path is an Amendment, and
                # register_amendment/apply_amendment refuse to run against a
                # runtime with errors -- a hard failure would wedge the
                # instance out of its own fix.
                structural_admission_defects.append(
                    "%s: manifest edits existing hub page(s) %s while "
                    "execution_mode=%s; K13/10 admits a hub-editing batch "
                    "only under exclusive or serial-integrator execution, so "
                    "this batch cannot be activated until a structural "
                    "Amendment changes its mode" %
                    (item_id, ", ".join(hub["blocking"]),
                     item.get("execution_mode")))
            if hub["unresolved"]:
                reasons.append(
                    "manifest page(s) cannot be classified against K13/10 hub "
                    "roles: %s" % ", ".join(hub["unresolved"]))
                structural_admission_defects.append(
                    "%s: manifest page(s) cannot be classified against K13/10 "
                    "hub roles: %s" %
                    (item_id, ", ".join(hub["unresolved"])))
        if task_state not in ("planned", "active"):
            reasons.append("task_state=%s forbids activation" % task_state)
        pending_amendments = _pending_cross_ledger_amendments(progress)
        if pending_amendments:
            reasons.append("pending cross-Ledger Amendment(s): %s" %
                           ", ".join(pending_amendments))
        if item.get("hold_state") != "none":
            reasons.append("hold=%s" % item.get("hold_state"))
        missing_deps = [dep for dep in item.get("depends_on", [])
                        if dep not in closed_ids]
        if missing_deps:
            reasons.append("dependencies not closed: %s" % ", ".join(missing_deps))
        if item.get("confirmation_required") and not _nonempty_string(
                item.get("confirmation_receipt")):
            reasons.append("confirmation receipt absent")
        if cap and len(active) >= cap:
            reasons.append("concurrency cap reached")
        if set(item.get("manifest") or []).intersection(active_manifest):
            reasons.append("manifest overlaps active work")
        if item.get("execution_mode") == "serial-integrator" and active:
            reasons.append("serial-integrator execution requires no active batch")
        if active and any(active_item.get("execution_mode") ==
                          "serial-integrator" for active_item in active):
            reasons.append("a serial-integrator batch is active")
        if reasons:
            blocked.append((item_id, reasons))
        else:
            ready.append(item_id)

    remaining = sum(1 for item in items_by_id.values()
                    if item.get("state") not in TERMINAL_STATES)
    started = sorted(item_id for item_id, item in items_by_id.items()
                     if item.get("state") in
                     ("open", "merge-ready", "closed"))
    if task_state == "planned" and started:
        errors.append("Progress task_state=planned but lifecycle has started "
                      "for batch(es) %s" % ", ".join(started))
    if task_state == "complete" and remaining > 0:
        errors.append("Progress task_state=complete but %d Required work unit(s) remain" %
                      remaining)
    task_errors, task_runtime = _task_transition_errors(
        root, progress, catalog, queue, queue_sha, coverage_sha, progress_sha,
        remaining, items_by_id,
        coverage,
    )
    errors.extend(task_errors)
    # Derive the requirements map once from this validation's Progress view
    # and the adoption-plan bytes observed for it.  Rebuilding it through each
    # batch helper made a corpus with N batches parse every historical
    # adoption plan roughly 2N times.
    standards_revalidation_requirements_by_batch = \
        standards_revalidation_requirements(
            root, progress, catalog=catalog)
    standards_barrier_context = {
        "root": root, "queue": queue, "coverage": coverage,
        "progress": progress, "items_by_id": items_by_id,
        "receipt_catalog": catalog,
        "current_receipt_catalog": current_catalog,
        "invalidated_evidence_receipt_ids":
            sorted(invalidated_evidence_receipt_ids),
        "legacy_property_state_source_receipt_ids":
            legacy_property_state_source_receipt_ids,
        "_standards_revalidation_requirements":
            standards_revalidation_requirements_by_batch,
    }
    errors.extend(_unresolvable_consumed_aggregate_errors(items_by_id, catalog))
    standards_revalidation_barriers = {}
    standards_revalidation_outstanding = {}
    for batch_id, item in items_by_id.items():
        outstanding = outstanding_standards_revalidation(
            standards_barrier_context, batch_id)
        if outstanding:
            standards_revalidation_outstanding[batch_id] = outstanding
        barrier = current_attempt_evidence_barrier(
            standards_barrier_context, batch_id)
        if barrier:
            standards_revalidation_barriers[batch_id] = barrier
            rollback_exception = (
                item.get("state") == "merge-ready" and
                batch_id == allow_standards_rollback_batch)
            if (item.get("state") in ("open", "merge-ready") and
                    not rollback_exception):
                errors.append(barrier)
    applied_delta_receipts = []
    stale_delta_apply_receipts = []
    for item in sorted(
            (value for value in items_by_id.values()
             if value.get("state") == "merge-ready"),
            key=lambda value: (value.get("order", sys.maxsize),
                               value.get("id", ""))):
        compatible, stale = _delta_apply_receipt_candidates(
            item, current_catalog, queue, queue_sha, coverage_sha,
            root=root, coverage=coverage, profile_view=profile_view,
        )
        stale_delta_apply_receipts.extend(stale)
        applied_delta_receipts.append({
            "batch": item.get("id"),
            "selected_receipt": compatible[0] if compatible else None,
            "compatible_receipts": compatible,
            "stale_receipts": [entry["receipt"] for entry in stale],
            "selection_rule": "lexical-receipt-id",
        })
    current_applied = [entry for entry in applied_delta_receipts
                       if entry.get("selected_receipt")]
    for stale in stale_delta_apply_receipts:
        errors.append(
            "merge-ready batch %s has stale unconsumed delta_apply receipt %s; "
            "current binding differs in %s" % (
                stale["batch"], stale["receipt"],
                ", ".join(stale["mismatched_fields"]),
            )
        )
    if len(current_applied) > 1:
        errors.append(
            "multiple merge-ready batches have current-compatible unconsumed "
            "delta_apply receipts: %s" % ", ".join(
                entry["batch"] for entry in current_applied)
        )
    pending_delta_applies = {
        "status": (
            "repair" if stale_delta_apply_receipts or
            len(current_applied) > 1 else
            ("close-required" if len(current_applied) == 1 else "clear")
        ),
        "current": current_applied,
        "stale": stale_delta_apply_receipts,
    }
    if profile_view is not None:
        final_profile_error = _profile_view_snapshot_error(
            root, profile_view, "after runtime validation")
        if final_profile_error:
            errors.append("selected Profile authorized view: %s" %
                          final_profile_error)
    if active_standards_view is not None:
        errors.extend(active_standards_view_currency_errors(
            root, active_standards_view,
            state_override=active_standards_state_override))
    return {
        "root": root, "errors": errors, "ready": ready, "blocked": blocked,
        "hub_page_admission": hub_admission,
        "structural_admission_defects": sorted(structural_admission_defects),
        "queue": queue, "coverage": coverage, "progress": progress,
        "queue_path": queue_path, "coverage_sha256": coverage_sha,
        "queue_sha256": queue_sha, "progress_sha256": progress_sha,
        "remaining": remaining, "items_by_id": items_by_id,
        "receipt_catalog": catalog,
        "cold_receipts": cold_store,
        "current_receipt_catalog": current_catalog,
        "invalidated_evidence_receipt_ids":
            sorted(invalidated_evidence_receipt_ids),
        "standards_revalidation_barriers":
            standards_revalidation_barriers,
        "standards_revalidation_outstanding":
            standards_revalidation_outstanding,
        "_standards_revalidation_requirements":
            standards_revalidation_requirements_by_batch,
        "writer_locks": writer_locks,
        "managed_deltas": managed_deltas,
        "applied_delta_receipts": applied_delta_receipts,
        "pending_delta_applies": pending_delta_applies,
        "pending_cross_ledger_amendments":
            _pending_cross_ledger_amendments(progress),
        "maintenance_candidate_context": maintenance_candidate_context,
        "task_runtime": task_runtime,
        "_active_standards_authorized_view": active_standards_view,
        "_profile_authorized_view": profile_view,
    }


def required_queue_completion_errors(result):
    """Return the canonical build-completion errors for one runtime view.

    ``result`` must be the already-authorized result of ``validate_runtime``.
    This predicate deliberately performs no filesystem reads and never
    re-runs Profile admission, so callers such as Terminal Proof can consume
    exactly the same runtime observation as the surrounding transaction.
    """
    errors = list(result.get("errors") or [])
    if errors:
        return errors

    writer_locks = result.get("writer_locks") or []
    if writer_locks:
        lock_paths = ", ".join(
            lock.get("path", "<unknown>")
            for lock in writer_locks
            if isinstance(lock, dict)
        )
        errors.append(
            "runtime state has active or interrupted writer lock(s): %s" %
            (lock_paths or "<unknown>")
        )
        return errors

    contract = result.get("progress", {}).get("contract") or {}
    if contract.get("completion_semantics") != "build":
        errors.append(
            "--require-complete is the build completion gate; maintenance "
            "tasks must use --require-maintenance-complete"
        )
        return errors

    queue_items = result.get("queue", {}).get("required_queue") or []
    if not queue_items:
        errors.append("an empty Queue cannot prove completion")
    elif result.get("remaining") != 0:
        errors.append("remaining_required_work_units=%s, expected 0" %
                      result.get("remaining"))
    return errors
