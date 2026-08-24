"""Which completed event earned each live page property.

The Coverage metadata owner/evidence/projection loop, the semantic before-set
each in-flight change is measured against, and the legacy-marker migration
path.  A property is earned by a named completed event or it is not earned;
there is no route here that sets one from a current observation.

``_coverage_property_state_errors`` takes its persisted-Gate validator as a
keyword-only argument with no default.  A default would give an in-package
caller a quietly weaker check than the façade supplies, and the whole reason
that validator lives outside this package is that the dependency runs the
other way.
"""

import copy
import datetime
import re

import kblib
import metadata_execution_contract
import metadata_property_state
import project_page_state

from queue_runtime.canon import (
    APPLY_DELTA_TOOL_VERSION,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    LEGACY_PROPERTY_ADOPTION_OPERATION,
    SHA256_RE,
    UPDATE_QUEUE_TOOL_VERSION,
)
from queue_runtime.evidence_identity import (
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_TERMINAL_HISTORY,
    _current_property_receipt,
    evidence_identity_errors,
    property_receipt_utc_date,
)
from queue_runtime.primitives import _nonempty_string
from queue_runtime.receipts import current_receipt_catalog


LEGACY_PROPERTY_STATE_FIELD = "legacy_property_state"
LEGACY_PROPERTY_RECORD_FIELDS = frozenset(("status", "value"))
LEGACY_PROPERTY_STATUS = "legacy-unverified"


def _current_inflight_semantic_baselines(
        root, coverage, queue, current_catalog, profile_view):
    """Return the sole controlled owner-staleness window per manifest page.

    A canonical page may change after a current batch opens but before the
    serial Integrator consumes its delta.  During that bounded window an
    existing owner record is still admissible only when it binds the exact
    semantic before-image frozen by the latest *current* opening receipt.
    Missing/legacy/invalid openings and overlapping active manifests grant no
    exception; their ordinary validators report the underlying defect.
    """
    candidates = {}
    for item in queue.get("required_queue") or []:
        if not isinstance(item, dict) or item.get("state") not in (
                "open", "merge-ready"):
            continue
        if item.get("state") == "merge-ready":
            live_coverage_sha = kblib.sha256_bytes(
                kblib.canonical_yaml(coverage))
            matching_apply = any(
                isinstance(entry, tuple) and isinstance(entry[1], dict) and
                entry[1].get("tool") == "apply_delta" and
                entry[1].get("tool_version") == APPLY_DELTA_TOOL_VERSION and
                entry[1].get("check") == "delta_apply" and
                entry[1].get("target") == item.get("id") and
                entry[1].get("result") == "pass" and
                entry[1].get("invalidated_by") is None and
                entry[1].get("delta_path") == item.get("delta_path") and
                entry[1].get("delta_sha256") == item.get("delta_sha256") and
                entry[1].get("after_coverage_sha256") == live_coverage_sha
                for entry in current_catalog.values())
            if matching_apply:
                continue
        opening = None
        for receipt_id in reversed(item.get("transition_receipts") or []):
            entry = current_catalog.get(receipt_id)
            receipt = entry[1] if isinstance(entry, tuple) else None
            if (isinstance(receipt, dict) and
                    receipt.get("before_state") in
                    ("queued", "merge-ready") and
                    receipt.get("after_state") == "open"):
                opening = receipt
                break
        if (not isinstance(opening, dict) or
                opening.get("tool") != "update_queue" or
                opening.get("tool_version") != UPDATE_QUEUE_TOOL_VERSION):
            continue
        if _current_open_semantic_baseline_errors(
                root, opening, item, profile_view):
            continue
        try:
            before = metadata_property_state.validate_semantic_baseline_records(
                opening.get("manifest_semantic_before_records"),
                expected_paths=sorted(item.get("manifest") or []))
        except (TypeError, ValueError):
            continue
        for path, fingerprint in before.items():
            candidates.setdefault(path, []).append(fingerprint)
    return {
        path: values[0] for path, values in candidates.items()
        if len(values) == 1
    }


def _delta_opening_semantic_binding(
        receipt, catalog, label, *, expected_item=None):
    """Validate and resolve a current delta's frozen opening before-set."""
    errors = []
    opening_id = receipt.get("opening_transition_receipt")
    opening = _current_property_receipt(
        catalog, opening_id, "%s opening semantic binding" % label, errors)
    if opening is None:
        return errors, {}
    expected = {
        "tool": "update_queue",
        "tool_version": UPDATE_QUEUE_TOOL_VERSION,
        "after_state": "open",
        "semantic_content_protocol":
            project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
    }
    if isinstance(expected_item, dict):
        expected["target"] = expected_item.get("id")
    else:
        expected["target"] = receipt.get("batch_id")
    for name, value in expected.items():
        if opening.get(name) != value:
            errors.append(
                "%s opening receipt %s has %s=%r, expected %r" %
                (label, opening_id, name, opening.get(name), value))
    for name in (
            "task_id", "selected_profile_manifest",
            "profile_snapshot_sha256", "profile_contract_fingerprint",
            "profile_load_inputs_sha256",
            "metadata_execution_contract_fingerprint"):
        if opening.get(name) != receipt.get(name):
            errors.append(
                "%s opening receipt %s does not share %s with the delta "
                "receipt" % (label, opening_id, name))
    if opening.get("before_state") not in ("queued", "merge-ready"):
        errors.append(
            "%s opening receipt %s has invalid before_state" %
            (label, opening_id))
    if (receipt.get("manifest_semantic_before_set_sha256") !=
            opening.get("manifest_semantic_before_set_sha256")):
        errors.append(
            "%s does not bind the opening receipt's exact semantic "
            "before-set" % label)
    expected_paths = (sorted(expected_item.get("manifest") or [])
                      if isinstance(expected_item, dict) else None)
    try:
        before = metadata_property_state.validate_semantic_baseline_records(
            opening.get("manifest_semantic_before_records"),
            expected_paths=expected_paths)
        expected_set_sha = \
            metadata_property_state.semantic_baseline_set_sha256(
                opening.get("manifest_semantic_before_records"))
    except (TypeError, ValueError) as exc:
        errors.append(
            "%s opening receipt %s has invalid semantic before records: %s" %
            (label, opening_id, exc))
        return errors, {}
    if opening.get("manifest_semantic_before_count") != len(before):
        errors.append(
            "%s opening receipt %s does not bind the exact baseline count" %
            (label, opening_id))
    if (opening.get("manifest_semantic_before_set_sha256") !=
            expected_set_sha):
        errors.append(
            "%s opening receipt %s has a stale semantic before-set digest" %
            (label, opening_id))
    return errors, before




def _content_change_property_evidence_errors(
        receipt, *, receipt_id, path, field, value, semantic_fingerprint,
        task_id, include_shape, current_catalog):
    """Bind a live content property to one completed producer-era event."""
    label = "Coverage property_state.%s for %s" % (field, path)
    errors = []
    expected = {
        "tool": "apply_delta",
        "tool_version": APPLY_DELTA_TOOL_VERSION,
        "check": "delta_apply",
        "result": "pass",
        "invalidated_by": None,
        "actor_role": "integrator",
        "task_id": task_id,
        "semantic_content_protocol":
            project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
    }
    for name, expected_value in expected.items():
        if receipt.get(name) != expected_value:
            errors.append(
                "%s evidence receipt %s has %s=%r, expected %r" %
                (label, receipt_id, name, receipt.get(name), expected_value))
    errors.extend(evidence_identity_errors(
        receipt, label, use=EVIDENCE_USE_COMPLETED_EVENT))
    if include_shape:
        errors.extend(_delta_property_event_errors(
            receipt, "content-change evidence receipt %s" % receipt_id))
    opening_errors, opening_before = _delta_opening_semantic_binding(
        receipt, current_catalog, label)
    errors.extend(opening_errors)
    accepted_date = property_receipt_utc_date(receipt, label, errors)
    events = receipt.get("property_events")
    matches = ([event for event in events
                if isinstance(event, dict) and event.get("path") == path]
               if isinstance(events, list) else [])
    if len(matches) != 1:
        errors.append(
            "%s evidence receipt %s must carry exactly one event for that "
            "page; found %d" % (label, receipt_id, len(matches)))
        return errors
    event = matches[0]
    if event.get("event") != "semantic-content-change":
        errors.append("%s evidence event has the wrong event type" % label)
    if event.get("accepted_on") != accepted_date:
        errors.append(
            "%s evidence event accepted_on=%r does not equal its receipt "
            "UTC date %r" %
            (label, event.get("accepted_on"), accepted_date))
    if event.get("after_semantic_content_sha256") != semantic_fingerprint:
        errors.append(
            "%s evidence event does not bind the current semantic content" %
            label)
    if event.get("before_semantic_content_sha256") != opening_before.get(path):
        errors.append(
            "%s evidence event does not bind the page's frozen opening "
            "semantic fingerprint" % label)
    if field == metadata_property_state.LAST_CONTENT_MODIFIED:
        if value != event.get("accepted_on"):
            errors.append(
                "%s value=%r does not equal the accepted content-change "
                "date %r" % (label, value, event.get("accepted_on")))
    elif field == metadata_property_state.LAST_REVIEWED:
        if value is not None:
            errors.append(
                "%s content-change evidence may only own a null review "
                "tombstone" % label)
        if event.get("last_reviewed_invalidated") is not True:
            errors.append(
                "%s null tombstone is not backed by a review invalidation "
                "event" % label)
    return errors


def _review_property_evidence_errors(
        receipt, *, receipt_id, path, value, semantic_fingerprint,
        task_id, current_catalog):
    """Bind ``last_reviewed`` to one completed producer-era review."""
    label = "Coverage property_state.last_reviewed for %s" % path
    errors = []
    expected = {
        "tool": BATCH_CLOSE_TOOL,
        "tool_version": BATCH_CLOSE_TOOL_VERSION,
        "check": "page_review_acceptance",
        "target": path,
        "result": "pass",
        "invalidated_by": None,
        "task_id": task_id,
        "reviewed_on": value,
        "semantic_content_sha256": semantic_fingerprint,
    }
    for name, expected_value in expected.items():
        if receipt.get(name) != expected_value:
            errors.append(
                "%s evidence receipt %s has %s=%r, expected %r" %
                (label, receipt_id, name, receipt.get(name), expected_value))
    errors.extend(evidence_identity_errors(
        receipt, label, use=EVIDENCE_USE_COMPLETED_EVENT))
    accepted_date = property_receipt_utc_date(receipt, label, errors)
    if value != accepted_date:
        errors.append(
            "%s value=%r does not equal its review receipt UTC date %r" %
            (label, value, accepted_date))
    batch_id = receipt.get("batch_id")
    integrator_id = receipt.get("integrator_id")
    reviewer_id = receipt.get("reviewer_id")
    merged_snapshot = receipt.get("merged_snapshot_sha256")
    for name, candidate in (
            ("batch_id", batch_id), ("integrator_id", integrator_id),
            ("reviewer_id", reviewer_id)):
        if not _nonempty_string(candidate):
            errors.append(
                "%s evidence receipt %s has no %s" %
                (label, receipt_id, name))
    if (_nonempty_string(integrator_id) and
            _nonempty_string(reviewer_id) and
            integrator_id.casefold() == reviewer_id.casefold()):
        errors.append(
            "%s evidence receipt uses the same integrator and reviewer" %
            label)
    if (not isinstance(merged_snapshot, str) or
            not SHA256_RE.fullmatch(merged_snapshot)):
        errors.append(
            "%s evidence receipt has invalid merged_snapshot_sha256" %
            label)
    attestation_id = receipt.get("reviewer_attestation_receipt")
    attestation = _current_property_receipt(
        current_catalog, attestation_id,
        "%s reviewer attestation" % label, errors)
    if attestation is not None:
        attestation_expected = {
            "tool": BATCH_CLOSE_TOOL,
            "tool_version": BATCH_CLOSE_TOOL_VERSION,
            "check": "batch_global_review_attestation",
            "target": batch_id,
            "result": "pass",
            "invalidated_by": None,
            "task_id": task_id,
            "batch_id": batch_id,
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "merged_snapshot_sha256": merged_snapshot,
        }
        for name, expected_value in attestation_expected.items():
            if attestation.get(name) != expected_value:
                errors.append(
                    "%s reviewer attestation %s has %s=%r, expected %r" %
                    (label, attestation_id, name,
                     attestation.get(name), expected_value))
        if not _nonempty_string(attestation.get("details")):
            errors.append(
                "%s reviewer attestation %s has no review statement" %
                (label, attestation_id))
    return errors



def _coverage_property_state_errors(
        root, coverage, current_catalog, queue, profile_view,
        active_standards_view, page_projection_overrides=None,
        allow_legacy_missing=False, *, gate_evidence_errors):
    """Validate the live Coverage metadata-owner/evidence/projection loop.

    Every live page opts into the current contract explicitly, including a
    page with no earned owner values yet (``property_state: {}``).  An absent
    mapping is a legacy *live-state* defect, not a producer-era receipt to be
    reinterpreted.  The only caller allowed to tolerate that defect is the
    existing Amendment writer while it reads the exact migration before-image;
    its proposed Coverage after-image still passes this function strictly.

    A pre-contract page value may be remembered without inventing authority
    only as an exact ``legacy_property_state`` observation.  That marker owns
    no transition.  The migration transaction removes the unowned page copy
    at the same commit point, so ordinary frontmatter consumers cannot keep
    treating a legacy review/date/Gate value as current authority.
    """
    pages = coverage.get("pages")
    if not isinstance(pages, list) or not pages:
        return []
    errors = []
    try:
        metadata_contract, rules = \
            metadata_property_state.authorized_profile_projection_rules(
                root, profile_view)
        contract = profile_view.get("_contract")
        extension_gates = contract.extension_gates
        manifest_snapshot = kblib.repository_file_snapshot(
            root, profile_view.get("selected_profile_manifest"),
            singly_linked=True)
    except (OSError, TypeError, UnicodeError, ValueError,
            metadata_execution_contract.MetadataExecutionContractError) as exc:
        return [
            "Coverage current property_state cannot compose its authorized "
            "metadata rules: %s" % exc]
    metadata_fingerprint = metadata_contract.contract_fingerprint
    coverage_sha256 = kblib.sha256_bytes(
        kblib.canonical_yaml(coverage).encode("utf-8"))
    gates_by_id = {gate.gate_id: gate for gate in extension_gates}
    property_rules = {
        rule.get("field"): rule for rule in rules
        if isinstance(rule, dict) and
        rule.get("source_adapter") in
        project_page_state.PROPERTY_VALUE_ADAPTERS
    }
    projection_overrides = page_projection_overrides or {}
    inflight_baselines = _current_inflight_semantic_baselines(
        root, coverage, queue, current_catalog, profile_view)
    consumed_projection_overrides = set()
    seen_content_receipts = set()
    for index, row in enumerate(pages):
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        label = "Coverage pages[%d] property_state" % index
        if not _nonempty_string(path):
            errors.append("%s has no valid page path" % label)
            continue
        legacy_missing = "property_state" not in row
        if legacy_missing and not allow_legacy_missing:
            errors.append(
                "%s for %s is absent; this live legacy page must be "
                "adopted through a property-state-migration Amendment "
                "before further writes" % (label, path))
        try:
            projected_text = projection_overrides.get(path)
            if path in projection_overrides:
                consumed_projection_overrides.add(path)
            if legacy_missing:
                page_snapshot, semantic_fingerprint, records = None, None, {}
            else:
                page_snapshot, semantic_fingerprint, records = \
                    metadata_property_state.validate_owner_property_records(
                        root, row, path, rules=rules,
                        page_text=projected_text,
                        accepted_stale_fingerprint=inflight_baselines.get(
                            path))
        except (OSError, TypeError, UnicodeError, ValueError) as exc:
            errors.append("%s for %s is invalid: %s" % (label, path, exc))
            continue

        page_text = projected_text
        if page_text is None and page_snapshot is not None:
            page_text = page_snapshot.read_text()
        if page_text is None:
            try:
                candidate = kblib.repository_target_snapshot(
                    root, path, suffixes=(".md", ".MD"), singly_linked=True)
                if candidate.exists:
                    page_text = candidate.read_text()
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(
                    "%s for %s cannot inspect its page projection: %s" %
                    (label, path, exc))
        page_fields = {}
        page_has_frontmatter = (
            page_text is not None and
            kblib.extract_frontmatter(page_text) is not None)
        if page_has_frontmatter:
            try:
                page_fields = project_page_state._frontmatter_mapping(
                    page_text, path)
            except (TypeError, UnicodeError, ValueError,
                    kblib.YamlSubsetError) as exc:
                errors.append(
                    "%s for %s has invalid page frontmatter: %s" %
                    (label, path, exc))

        legacy = row.get(LEGACY_PROPERTY_STATE_FIELD)
        if legacy is None:
            legacy = {}
        elif not isinstance(legacy, dict):
            errors.append(
                "Coverage pages[%d] %s for %s must be a mapping" %
                (index, LEGACY_PROPERTY_STATE_FIELD, path))
            legacy = {}
        elif not legacy:
            errors.append(
                "Coverage pages[%d] %s for %s must be omitted when empty" %
                (index, LEGACY_PROPERTY_STATE_FIELD, path))
        undeclared_legacy = sorted(set(legacy) - set(property_rules))
        if undeclared_legacy:
            errors.append(
                "Coverage %s for %s has field(s) outside the authorized "
                "metadata rules: %s" %
                (LEGACY_PROPERTY_STATE_FIELD, path,
                 ", ".join(undeclared_legacy)))
        for field, record in sorted(legacy.items()):
            if field not in property_rules:
                continue
            legacy_label = "Coverage %s.%s for %s" % (
                LEGACY_PROPERTY_STATE_FIELD, field, path)
            if (not isinstance(record, dict) or
                    set(record) != LEGACY_PROPERTY_RECORD_FIELDS):
                errors.append(
                    "%s must be the closed status/value observation" %
                    legacy_label)
                continue
            if record.get("status") != LEGACY_PROPERTY_STATUS:
                errors.append(
                    "%s status must be %s" %
                    (legacy_label, LEGACY_PROPERTY_STATUS))
            try:
                project_page_state._typed_legacy_observation_value(
                    record.get("value"), property_rules[field], path)
            except (TypeError, ValueError) as exc:
                errors.append("%s has invalid value: %s" % (legacy_label, exc))
            if field in records:
                errors.append(
                    "%s conflicts with current property_state.%s; the "
                    "current-owner transaction must retire the legacy marker" %
                    (legacy_label, field))
            if field in page_fields:
                errors.append(
                    "%s still has a persisted page copy %r; a completed "
                    "migration must remove the unowned copy atomically" %
                    (legacy_label, page_fields.get(field)))

        # Reconcile only the property-copy surface here.  Value/tombstone and
        # semantic bindings already came from the generic projector's shared
        # owner parser above; this loop adds the lower-bound invariant the
        # projector itself needs: a persisted machine field may not exist with
        # neither current owner nor an exact legacy/unverified observation.
        for field, rule in sorted(property_rules.items()):
            current = records.get(field)
            if current is not None:
                expected = current.get("value")
                if expected is None:
                    if field in page_fields:
                        errors.append(
                            "%s for %s retains page field %s despite its "
                            "current owner tombstone" % (label, path, field))
                elif page_has_frontmatter and field not in page_fields:
                    errors.append(
                        "%s for %s has current owner %s=%r but the page "
                        "projection is absent" %
                        (label, path, field, expected))
                elif page_fields.get(field) != expected:
                    errors.append(
                        "%s for %s has current owner %s=%r but the page "
                        "projection is %r" %
                        (label, path, field, expected,
                         page_fields.get(field)))
            elif field in page_fields and field not in legacy and not (
                    allow_legacy_missing and legacy_missing):
                errors.append(
                    "%s for %s persists machine-managed field %s=%r "
                    "without a current owner or an exact "
                    "legacy/unverified observation" %
                    (label, path, field, page_fields.get(field)))

        if not records:
            continue
        modified = records.get(metadata_property_state.LAST_CONTENT_MODIFIED)
        reviewed = records.get(metadata_property_state.LAST_REVIEWED)
        if isinstance(reviewed, dict) and reviewed.get("value") is None:
            if not isinstance(modified, dict):
                errors.append(
                    "%s for %s has a last_reviewed tombstone without the "
                    "content-change state that invalidated it" %
                    (label, path))
            elif (reviewed.get("evidence_receipt") !=
                    modified.get("evidence_receipt") or
                    reviewed.get("content_fingerprint") !=
                    modified.get("content_fingerprint")):
                errors.append(
                    "%s for %s does not bind its last_reviewed tombstone "
                    "and last_content_modified value to one content-change "
                    "event" % (label, path))
        if (isinstance(modified, dict) and modified.get("value") is not None and
                isinstance(reviewed, dict) and
                reviewed.get("value") is not None):
            try:
                modified_date = datetime.date.fromisoformat(modified["value"])
                reviewed_date = datetime.date.fromisoformat(reviewed["value"])
            except (TypeError, ValueError):
                pass  # The shared value-shape validator already reported it.
            else:
                if reviewed_date < modified_date:
                    errors.append(
                        "%s for %s has last_reviewed before "
                        "last_content_modified" % (label, path))
        for field, record in sorted(records.items()):
            record_label = "Coverage property_state.%s for %s" % (field, path)
            receipt_id = record.get("evidence_receipt")
            receipt = _current_property_receipt(
                current_catalog, receipt_id, record_label, errors)
            if receipt is None:
                continue
            value = record.get("value")
            evidence_fingerprint = record.get("content_fingerprint")
            if (field == metadata_property_state.LAST_CONTENT_MODIFIED or
                    (field == metadata_property_state.LAST_REVIEWED and
                     value is None)):
                include_shape = receipt_id not in seen_content_receipts
                seen_content_receipts.add(receipt_id)
                errors.extend(_content_change_property_evidence_errors(
                    receipt, receipt_id=receipt_id, path=path, field=field,
                    value=value,
                    semantic_fingerprint=evidence_fingerprint,
                    task_id=queue.get("task_id"),
                    include_shape=include_shape,
                    current_catalog=current_catalog))
            elif field == metadata_property_state.LAST_REVIEWED:
                errors.extend(_review_property_evidence_errors(
                    receipt, receipt_id=receipt_id, path=path, value=value,
                    semantic_fingerprint=evidence_fingerprint,
                    task_id=queue.get("task_id"),
                    current_catalog=current_catalog))
            else:
                errors.extend(gate_evidence_errors(
                    receipt, receipt_id=receipt_id, path=path,
                    field=field, value=value,
                    semantic_fingerprint=evidence_fingerprint,
                    metadata_contract_fingerprint=metadata_fingerprint,
                    profile_view=profile_view,
                    active_standards_view=active_standards_view,
                    gates_by_id=gates_by_id,
                    manifest_sha256=manifest_snapshot.sha256,
                    root=root, rules=rules,
                    current_catalog=current_catalog,
                    coverage_sha256=coverage_sha256,
                    projected_page_text=projected_text))
    unused_overrides = sorted(
        set(projection_overrides) - consumed_projection_overrides)
    if unused_overrides:
        errors.append(
            "page projection after-images do not correspond to current "
            "Coverage property_state owners: %s" %
            ", ".join(unused_overrides))
    return errors


def _legacy_property_state_source_errors(
        coverage, progress, catalog):
    """Resolve every live legacy marker to exact current-protocol evidence.

    A migrated page no longer carries the unowned machine value, by design.
    Ordinary validation therefore proves the marker against the immutable
    before/after record set emitted by the sole writer instead of trusting the
    page copy that migration removed.  Producer-era identity stays closed:
    only the versions that introduced this protocol are parsed here.
    """
    errors = []
    wanted = {}
    for index, row in enumerate(coverage.get("pages") or []):
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        legacy = row.get(LEGACY_PROPERTY_STATE_FIELD)
        if not _nonempty_string(path) or not isinstance(legacy, dict):
            continue
        for field, record in legacy.items():
            if not isinstance(record, dict):
                continue
            key = (path, field, kblib.canonical_yaml({"value": record.get(
                "value")}))
            wanted[key] = (
                "Coverage pages[%d] %s.%s" %
                (index, LEGACY_PROPERTY_STATE_FIELD, field))
    if not wanted:
        return errors, []

    sources = {key: set() for key in wanted}
    for receipt_id, entry in catalog.items():
        receipt = entry[1] if isinstance(entry, tuple) and len(entry) == 2 \
            else None
        if not isinstance(receipt, dict) or not (
                receipt.get("tool") == "apply_task_plan" and
                receipt.get("tool_version") == "1.2.0" and
                receipt.get("check") == "task_plan" and
                receipt.get("transaction_phase") == "commit" and
                receipt.get("result") == "pass" and
                receipt.get("invalidated_by") is None and
                receipt.get("operation_capability") ==
                LEGACY_PROPERTY_ADOPTION_OPERATION):
            continue
        try:
            records = \
                metadata_property_state.validate_legacy_property_migration_records(
                    receipt.get("property_state_adoption_records"))
            set_sha = \
                metadata_property_state.legacy_property_migration_set_sha256(
                    receipt.get("property_state_adoption_records"))
        except (TypeError, ValueError) as exc:
            errors.append(
                "initial property adoption receipt %s has invalid exact "
                "migration records: %s" % (receipt_id, exc))
            continue
        if receipt.get("property_state_adoption_count") != len(records):
            errors.append(
                "initial property adoption receipt %s has a stale record "
                "count" % receipt_id)
            continue
        if receipt.get("property_state_adoption_set_sha256") != set_sha:
            errors.append(
                "initial property adoption receipt %s has a stale record-set "
                "digest" % receipt_id)
            continue
        if any(not SHA256_RE.fullmatch(str(receipt.get(field) or ""))
               for field in (
                   "metadata_execution_contract_fingerprint",
                   "metadata_execution_rule_fingerprint",
                   "profile_snapshot_sha256", "profile_contract_fingerprint",
                   "profile_load_inputs_sha256")) or not _nonempty_string(
                       receipt.get("selected_profile_manifest")):
            errors.append(
                "initial property adoption receipt %s has incomplete "
                "metadata/Profile authority bindings" % receipt_id)
            continue
        for path, record in records.items():
            for field, observation in record[
                    "legacy_property_state"].items():
                key = (path, field, kblib.canonical_yaml(
                    {"value": observation.get("value")}))
                if key in sources:
                    sources[key].add(receipt_id)

    for amendment in progress.get("amendments") or []:
        if not (isinstance(amendment, dict) and
                amendment.get("operation") == "property-state-migration" and
                amendment.get("status") == "verified" and
                amendment.get("writeback_done") is True):
            continue
        try:
            records = \
                metadata_property_state.validate_legacy_property_migration_records(
                    amendment.get("property_state_migration_records"),
                    expected_paths=amendment.get("affected_pages"))
        except (TypeError, ValueError):
            # The operational-Amendment validator reports the exact shape.
            continue
        source_ids = {
            value for value in (
                amendment.get("registration_receipt"),
                amendment.get("verification_receipt"))
            if _nonempty_string(value)
        }
        for path, record in records.items():
            for field, observation in record[
                    "legacy_property_state"].items():
                key = (path, field, kblib.canonical_yaml(
                    {"value": observation.get("value")}))
                if key in sources:
                    sources[key].update(source_ids)

    resolved = set()
    for key, label in wanted.items():
        if not sources[key]:
            errors.append(
                "%s is not bound to a current-protocol initial-adoption or "
                "property-state-migration receipt" % label)
        else:
            resolved.update(sources[key])
    return errors, sorted(resolved)


DELTA_PROPERTY_EVENT_KEYS = frozenset((
    "event", "path", "accepted_on",
    "before_semantic_content_sha256", "after_semantic_content_sha256",
    "last_reviewed_invalidated",
    "invalidated_property_fields",
    "invalidated_property_records",
    "invalidated_property_receipt_ids",
))
DELTA_INVALIDATED_PROPERTY_RECORD_KEYS = frozenset((
    "field", "action", "before_owner_record",
    "before_legacy_observation",
))


def _delta_property_event_errors(receipt, label):
    """Validate the current semantic-content event protocol by shape.

    Historical replay preserves its producer-era bytes; current-use exact
    content and Coverage equality are enforced by the Integrator before the
    receipt is written.  This consumer keeps the durable record closed so a
    later replay cannot reinterpret free-form extension data as authority.
    """
    errors = []
    fingerprint = receipt.get("metadata_execution_contract_fingerprint")
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
        errors.append("%s has invalid metadata execution contract fingerprint" %
                      label)
    rule_fingerprint = receipt.get("metadata_execution_rule_fingerprint")
    if not isinstance(rule_fingerprint, str) or not SHA256_RE.fullmatch(
            rule_fingerprint):
        errors.append("%s has invalid producer-era metadata rule fingerprint" %
                      label)
    if receipt.get("semantic_content_protocol") != \
            "cambium-semantic-page-v1":
        errors.append("%s has invalid semantic content protocol" % label)
    events = receipt.get("property_events")
    if not isinstance(events, list):
        errors.append("%s property_events must be an explicit list" % label)
        return errors
    paths = []
    for index, event in enumerate(events):
        event_label = "%s property_events[%d]" % (label, index)
        if not isinstance(event, dict):
            errors.append("%s must be a mapping" % event_label)
            continue
        missing = sorted(DELTA_PROPERTY_EVENT_KEYS - set(event))
        extra = sorted(set(event) - DELTA_PROPERTY_EVENT_KEYS)
        if missing or extra:
            errors.append(
                "%s must be closed (missing=%s extra=%s)" %
                (event_label, missing, extra))
            continue
        if event.get("event") != "semantic-content-change":
            errors.append("%s event must be semantic-content-change" %
                          event_label)
        path = event.get("path")
        if not _nonempty_string(path):
            errors.append("%s path must be non-empty" % event_label)
        else:
            paths.append(path)
        if not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                str(event.get("accepted_on") or "")):
            errors.append("%s accepted_on must be YYYY-MM-DD" % event_label)
        before = event.get("before_semantic_content_sha256")
        if not isinstance(before, str) or not SHA256_RE.fullmatch(before):
            errors.append("%s before fingerprint must be sha256" %
                          event_label)
        after = event.get("after_semantic_content_sha256")
        if not isinstance(after, str) or not SHA256_RE.fullmatch(after):
            errors.append("%s after fingerprint must be sha256" % event_label)
        if not isinstance(event.get("last_reviewed_invalidated"), bool):
            errors.append("%s last_reviewed_invalidated must be boolean" %
                          event_label)
        invalidated = event.get("invalidated_property_fields")
        if (not isinstance(invalidated, list) or
                any(not _nonempty_string(field) for field in invalidated) or
                invalidated != sorted(set(invalidated))):
            errors.append(
                "%s invalidated_property_fields must be a sorted unique "
                "string list" % event_label)
        elif ((metadata_property_state.LAST_REVIEWED in invalidated) !=
              (event.get("last_reviewed_invalidated") is True)):
            errors.append(
                "%s last_reviewed_invalidated must exactly equal membership "
                "in invalidated_property_fields" % event_label)
        invalidation_records = event.get("invalidated_property_records")
        record_fields = []
        record_receipts = []
        if not isinstance(invalidation_records, list):
            errors.append(
                "%s invalidated_property_records must be an explicit list" %
                event_label)
        else:
            for record_index, record in enumerate(invalidation_records):
                record_label = "%s invalidated_property_records[%d]" % (
                    event_label, record_index)
                if (not isinstance(record, dict) or set(record) !=
                        DELTA_INVALIDATED_PROPERTY_RECORD_KEYS):
                    errors.append(
                        "%s is not the closed invalidation record" %
                        record_label)
                    continue
                field = record.get("field")
                if not _nonempty_string(field):
                    errors.append("%s field must be non-empty" % record_label)
                    continue
                record_fields.append(field)
                expected_action = (
                    "tombstone-current-owner"
                    if field == metadata_property_state.LAST_REVIEWED else
                    "remove-owner-and-page-copy")
                if record.get("action") != expected_action:
                    errors.append(
                        "%s action=%r, expected %r" %
                        (record_label, record.get("action"), expected_action))
                owner = record.get("before_owner_record")
                legacy = record.get("before_legacy_observation")
                if owner is not None:
                    if (not isinstance(owner, dict) or set(owner) !=
                            metadata_property_state.PROPERTY_RECORD_KEYS):
                        errors.append(
                            "%s before_owner_record is not closed" %
                            record_label)
                    else:
                        if not _nonempty_string(owner.get("evidence_receipt")):
                            errors.append(
                                "%s before owner has no evidence receipt" %
                                record_label)
                        else:
                            record_receipts.append(
                                owner["evidence_receipt"])
                        if not SHA256_RE.fullmatch(str(
                                owner.get("content_fingerprint") or "")):
                            errors.append(
                                "%s before owner has invalid fingerprint" %
                                record_label)
                if legacy is not None and (
                        not isinstance(legacy, dict) or
                        set(legacy) != LEGACY_PROPERTY_RECORD_FIELDS or
                        legacy.get("status") != LEGACY_PROPERTY_STATUS):
                    errors.append(
                        "%s before_legacy_observation is not closed" %
                        record_label)
                if owner is None and legacy is None:
                    errors.append(
                        "%s has neither a current owner nor legacy source" %
                        record_label)
            if record_fields != sorted(set(record_fields)):
                errors.append(
                    "%s invalidated_property_records must be field-sorted "
                    "and unique" % event_label)
            if isinstance(invalidated, list) and record_fields != invalidated:
                errors.append(
                    "%s invalidated_property_fields does not equal the exact "
                    "record field set" % event_label)
        receipt_ids = event.get("invalidated_property_receipt_ids")
        if (not isinstance(receipt_ids, list) or
                any(not _nonempty_string(value) for value in receipt_ids) or
                receipt_ids != sorted(set(receipt_ids))):
            errors.append(
                "%s invalidated_property_receipt_ids must be a sorted unique "
                "string list" % event_label)
        elif receipt_ids != sorted(set(record_receipts)):
            errors.append(
                "%s invalidated_property_receipt_ids does not equal the "
                "prior owner evidence set" % event_label)
    if paths != sorted(set(paths)):
        errors.append("%s property_events paths must be unique and sorted" %
                      label)
    return errors


def _delta_property_invalidation_errors(
        root, receipt, coverage=None, profile_view=None):
    """Replay current-protocol invalidations from the frozen before image.

    The exact invalidated set is producer-era data: every content-bound owner
    other than LCM, plus a stale review/legacy review, must occur in the event
    record.  Historical replay deliberately does not compose today's Profile.
    A live after-image may additionally be supplied to prove the declared
    tombstone/removals landed.
    """
    errors = []
    if not SHA256_RE.fullmatch(str(
            receipt.get("metadata_execution_rule_fingerprint") or "")):
        errors.append(
            "property invalidation receipt has no producer-era rule "
            "fingerprint")
    archive_relative = receipt.get("before_coverage_archive_path")
    try:
        archive_path = kblib.managed_repository_path(
            root, archive_relative, ".cambium/receipts",
            suffixes=(".yaml",), must_exist=True)
        if kblib.sha256_file(archive_path) != receipt.get(
                "before_coverage_sha256"):
            raise ValueError("archive bytes differ from before_coverage_sha256")
        before_coverage = kblib.load_yaml_file(archive_path)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return errors + [
            "property invalidation replay cannot load its exact before "
            "Coverage: %s" % exc]
    before_rows = {
        row.get("path"): row for row in before_coverage.get("pages") or []
        if isinstance(row, dict) and _nonempty_string(row.get("path"))
    }
    after_rows = ({
        row.get("path"): row for row in coverage.get("pages") or []
        if isinstance(row, dict) and _nonempty_string(row.get("path"))
    } if isinstance(coverage, dict) else {})
    for event in receipt.get("property_events") or []:
        if not isinstance(event, dict):
            continue
        path = event.get("path")
        before_row = before_rows.get(path)
        after_row = after_rows.get(path)
        if not isinstance(before_row, dict):
            errors.append(
                "property invalidation event %s is absent from archived "
                "Coverage" % path)
            continue
        before_state = before_row.get("property_state") or {}
        after_state = (after_row.get("property_state") or {}
                       if isinstance(after_row, dict) else None)
        if not isinstance(before_state, dict) or (
                after_state is not None and not isinstance(after_state, dict)):
            errors.append(
                "property invalidation event %s has non-mapping owner state" %
                path)
            continue
        after_fingerprint = event.get("after_semantic_content_sha256")
        expected_records = []
        review = before_state.get(metadata_property_state.LAST_REVIEWED)
        legacy_mapping = before_row.get(LEGACY_PROPERTY_STATE_FIELD) or {}
        legacy_review = legacy_mapping.get(
            metadata_property_state.LAST_REVIEWED) if isinstance(
                legacy_mapping, dict) else None
        if ((isinstance(review, dict) and
             review.get("content_fingerprint") != after_fingerprint) or
                legacy_review is not None):
            expected_records.append({
                "field": metadata_property_state.LAST_REVIEWED,
                "action": "tombstone-current-owner",
                "before_owner_record": copy.deepcopy(
                    review if isinstance(review, dict) else None),
                "before_legacy_observation": copy.deepcopy(legacy_review),
            })
        for field, record in sorted(before_state.items()):
            if field in (metadata_property_state.LAST_CONTENT_MODIFIED,
                         metadata_property_state.LAST_REVIEWED):
                continue
            if not isinstance(record, dict) or \
                    record.get("content_fingerprint") == after_fingerprint:
                continue
            expected_records.append({
                "field": field,
                "action": "remove-owner-and-page-copy",
                "before_owner_record": copy.deepcopy(record),
                "before_legacy_observation": None,
            })
        expected_records.sort(key=lambda record: record["field"])
        if event.get("invalidated_property_records") != expected_records:
            errors.append(
                "property invalidation event %s records do not equal the "
                "exact archived owner set" % path)
        expected_fields = [record["field"] for record in expected_records]
        if event.get("invalidated_property_fields") != expected_fields:
            errors.append(
                "property invalidation event %s declares %r, expected exact "
                "%r from archived owner state" %
                (path, event.get("invalidated_property_fields"),
                 expected_fields))
        expected_receipts = sorted({
            record["before_owner_record"]["evidence_receipt"]
            for record in expected_records
            if isinstance(record.get("before_owner_record"), dict) and
            _nonempty_string(record["before_owner_record"].get(
                "evidence_receipt"))
        })
        if event.get("invalidated_property_receipt_ids") != expected_receipts:
            errors.append(
                "property invalidation event %s does not bind the exact prior "
                "owner receipt set" % path)
        if after_state is None:
            continue
        for record in expected_records:
            field = record["field"]
            if record["action"] == "remove-owner-and-page-copy" and \
                    field in after_state:
                errors.append(
                    "property invalidation event %s did not remove owner %s" %
                    (path, field))
            elif record["action"] == "tombstone-current-owner":
                tombstone = after_state.get(field)
                if not (isinstance(tombstone, dict) and
                        tombstone.get("value") is None and
                        tombstone.get("evidence_receipt") ==
                        receipt.get("receipt_id") and
                        tombstone.get("content_fingerprint") ==
                        after_fingerprint):
                    errors.append(
                        "property invalidation event %s did not publish its "
                        "current review tombstone" % path)
    return errors


def _current_open_semantic_baseline_errors(
        root, transition, item, profile_view, *, require_live_authority=True):
    """Validate the current opening receipt's exact semantic before-set.

    Producer version 1.5 is the adoption boundary.  Its before-set lets
    ``apply_delta`` distinguish a real semantic edit from a first observation
    or a machine-projection-only rewrite.  Versions 1.2--1.4 remain immutable
    history: they never claimed these fields and are not reinterpreted through
    today's Profile or metadata contract.  While the batch remains open or
    merge-ready, ``require_live_authority`` additionally binds that active
    execution baseline to the live Profile and metadata implementation.  A
    terminal batch keeps the exact same closed shape but replays the binding
    as producer-era history.
    """
    if not isinstance(transition, dict) or not (
            transition.get("tool") == "update_queue" and
            transition.get("tool_version") == UPDATE_QUEUE_TOOL_VERSION and
            transition.get("before_state") in ("queued", "merge-ready") and
            transition.get("after_state") == "open"):
        return []
    label = "%s current open transition %s" % (
        item.get("id", "<unknown>"),
        transition.get("receipt_id") or "<unknown>")
    errors = []
    manifest = item.get("manifest")
    if (not isinstance(manifest, list) or
            any(not _nonempty_string(path) for path in manifest)):
        errors.append("%s cannot bind an invalid manifest" % label)
        expected_paths = []
    else:
        expected_paths = sorted(manifest)

    records = transition.get("manifest_semantic_before_records")
    try:
        metadata_property_state.validate_semantic_baseline_records(
            records, expected_paths=expected_paths)
    except (TypeError, ValueError) as exc:
        errors.append(
            "%s has invalid manifest_semantic_before_records: %s" %
            (label, exc))
    record_count = len(records) if isinstance(records, list) else 0

    count = transition.get("manifest_semantic_before_count")
    if (not isinstance(count, int) or isinstance(count, bool) or
            count != record_count):
        errors.append(
            "%s manifest_semantic_before_count must equal the exact record "
            "list" % label)
    set_sha = transition.get("manifest_semantic_before_set_sha256")
    try:
        expected_set_sha = \
            metadata_property_state.semantic_baseline_set_sha256(records)
    except (TypeError, ValueError):
        expected_set_sha = None
    if (not isinstance(set_sha, str) or not SHA256_RE.fullmatch(set_sha) or
            expected_set_sha is None or set_sha != expected_set_sha):
        errors.append(
            "%s manifest_semantic_before_set_sha256 does not bind the "
            "exact canonical record list" % label)

    if transition.get("semantic_content_protocol") != \
            project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL:
        errors.append("%s has the wrong semantic content protocol" % label)
    live_metadata_fingerprint = None
    if require_live_authority:
        try:
            live_metadata_fingerprint = \
                metadata_execution_contract.load_metadata_execution_contract(
                    root).contract_fingerprint
        except (OSError, UnicodeError, ValueError,
                metadata_execution_contract.
                MetadataExecutionContractError) as exc:
            errors.append(
                "%s cannot load the live metadata execution contract: %s" %
                (label, exc))
    errors.extend(evidence_identity_errors(
        transition, label,
        use=(EVIDENCE_USE_ACTIVE_TRANSACTION if require_live_authority
             else EVIDENCE_USE_TERMINAL_HISTORY),
        profile_view=profile_view,
        metadata_contract_fingerprint=live_metadata_fingerprint))
    return errors


def current_opening_semantic_context(result, item_id):
    """Return the validated current opening receipt and semantic before-set.

    This is the sole durable consumer boundary for ``apply_delta``.  It
    resolves the most recent opening edge from the adoption-filtered hot
    receipt catalog, rejects a legacy producer instead of treating apply-time
    observation as a baseline, and returns both the exact semantic mapping and
    the receipt identity/hash that a later content-change receipt must bind.
    """
    if not isinstance(result, dict):
        raise TypeError("runtime result must be a mapping")
    item = (result.get("items_by_id") or {}).get(item_id)
    if not isinstance(item, dict):
        raise ValueError("unknown Queue item %s" % item_id)
    catalog = current_receipt_catalog(result)
    opening = None
    for receipt_id in reversed(item.get("transition_receipts") or []):
        entry = catalog.get(receipt_id)
        receipt = entry[1] if isinstance(entry, tuple) else None
        if (isinstance(receipt, dict) and
                receipt.get("before_state") in ("queued", "merge-ready") and
                receipt.get("after_state") == "open"):
            opening = receipt
            break
    if opening is None:
        raise ValueError(
            "Queue item %s has no current opening receipt" % item_id)
    if (opening.get("tool") != "update_queue" or
            opening.get("tool_version") != UPDATE_QUEUE_TOOL_VERSION):
        raise ValueError(
            "Queue item %s latest opening receipt uses legacy producer %r/%r; "
            "a current semantic before-set is required" %
            (item_id, opening.get("tool"), opening.get("tool_version")))
    errors = _current_open_semantic_baseline_errors(
        result.get("root"), opening, item,
        result.get("_profile_authorized_view"))
    if errors:
        raise ValueError("; ".join(errors))
    before = metadata_property_state.validate_semantic_baseline_records(
        opening.get("manifest_semantic_before_records"),
        expected_paths=sorted(item.get("manifest") or []))
    return {
        "opening_transition_receipt": opening.get("receipt_id"),
        "semantic_content_protocol": opening.get(
            "semantic_content_protocol"),
        "manifest_semantic_before_set_sha256": opening.get(
            "manifest_semantic_before_set_sha256"),
        "before_semantic_fingerprints": before,
    }


def current_opening_semantic_baseline(result, item_id):
    """Return the validated current opening path->semantic before-set."""
    return current_opening_semantic_context(
        result, item_id)["before_semantic_fingerprints"]


def _current_close_transition_metadata_errors(
        root, transition, catalog, item_id):
    """Validate the current update_queue close-to-property-state bridge.

    The producer-version equality is the era boundary.  Older 1.2--1.4
    transitions remain frozen history and are not reinterpreted through the
    live metadata/Profile protocol.  A current 1.5 close, however, is the
    durable bridge from the exact batch-close page-review children to the
    Coverage owner state it published, so its child set and producer-era
    metadata-contract identity must be closed and exact.  The transition and
    its close Gate must agree with each other; a terminal edge is not
    reinterpreted through today's implementation bytes.
    """
    if not isinstance(transition, dict) or not (
            transition.get("tool") == "update_queue" and
            transition.get("tool_version") == UPDATE_QUEUE_TOOL_VERSION and
            transition.get("before_state") == "merge-ready" and
            transition.get("after_state") == "closed"):
        return []
    label = "%s current close transition %s" % (
        item_id, transition.get("receipt_id") or "<unknown>")
    errors = []
    ids = transition.get("page_review_receipts")
    if (not isinstance(ids, list) or
            any(not _nonempty_string(value) for value in ids)):
        errors.append("%s page_review_receipts must be a string list" % label)
        ids = []
    else:
        if ids != sorted(ids):
            errors.append("%s page_review_receipts must be sorted" % label)
        if len(ids) != len(set(ids)):
            errors.append("%s page_review_receipts must be unique" % label)
    count = transition.get("page_review_receipt_count")
    if (not isinstance(count, int) or isinstance(count, bool) or
            count != len(ids)):
        errors.append(
            "%s page_review_receipt_count must equal the exact receipt list" %
            label)

    close_id = transition.get("close_gate_receipt")
    aggregate = None
    entry = catalog.get(close_id) if _nonempty_string(close_id) else None
    if isinstance(entry, tuple) and len(entry) == 2 and isinstance(
            entry[1], dict):
        aggregate = entry[1]
    elif (hasattr(catalog, "resolve_sealed") and
          close_id in (getattr(catalog, "cold", None) or {})):
        try:
            aggregate = catalog.resolve_sealed(close_id)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(
                "%s cannot resolve sealed close Gate %s: %s" %
                (label, close_id, exc))
    if not isinstance(aggregate, dict):
        errors.append(
            "%s cannot resolve close_gate_receipt %r" % (label, close_id))
        return errors
    aggregate_ids = aggregate.get("page_review_receipts")
    if ids != aggregate_ids:
        errors.append(
            "%s page_review_receipts do not equal the close Gate's exact "
            "child receipt IDs" % label)

    fingerprint = transition.get(
        "metadata_execution_contract_fingerprint")
    aggregate_fingerprint = aggregate.get(
        "metadata_execution_contract_fingerprint")
    errors.extend(evidence_identity_errors(
        transition, label, use=EVIDENCE_USE_TERMINAL_HISTORY,
        profile_bound=False))
    if fingerprint != aggregate_fingerprint:
        errors.append(
            "%s metadata execution fingerprint differs from its close Gate" %
            label)
    return errors
