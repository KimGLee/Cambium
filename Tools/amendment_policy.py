#!/usr/bin/env python3
"""Pure delegated-Amendment impact and authority policy.

This module owns no state and performs no writes.  It turns one complete
Coverage before/after pair plus the live Queue lifecycle into three facts used
by every operational Amendment writer:

* the closed set of change classes present in the proposal;
* the writer operation implied by those changes; and
* whether the Task Contract delegates that exact set to the integrator.

The first protocol is deliberately small.  It covers the Queue-growth path an
autonomous task needs today and fails closed on metadata/removal/gap changes
whose writers or semantics belong elsewhere.
"""

import copy

import batch_settlement
import coverage_contract
import kblib
import runtime_state_contract
import work_spec_contract


AUTHORITY_SCHEMA_VERSION = 1
AUTHORITY_MODES = frozenset(("delegated-integrator", "user-only"))
AUTHORITY_FIELDS = frozenset((
    "schema_version", "authority_id", "mode", "allowed_change_classes",
))

CHANGE_REQUIRED_ADD = "required-object-add"
CHANGE_REQUIRED_PROMOTE = "required-object-promote"
CHANGE_BATCH_ADD = "batch-add"
CHANGE_REQUIRED_REROUTE = "required-object-reroute"
CHANGE_QUEUED_BATCH_UPDATE = "queued-batch-update"

# Known, executable only with an explicit user decision in v1.  These remain
# visible change classes instead of being confused with an unknown effect.
CHANGE_REQUIRED_DEMOTE = "required-object-demote"
CHANGE_BATCH_RETIRE = "batch-retire"
CHANGE_OPEN_WORK_SPEC_UPDATE = "open-work-spec-update"
CHANGE_GAP_ROUTING_RECONCILIATION = "gap-routing-reconciliation"
CHANGE_PROPERTY_STATE_ADOPTION = "property-state-adoption"

DELEGATABLE_CHANGE_CLASSES = frozenset((
    CHANGE_REQUIRED_ADD,
    CHANGE_REQUIRED_PROMOTE,
    CHANGE_BATCH_ADD,
    CHANGE_REQUIRED_REROUTE,
    CHANGE_QUEUED_BATCH_UPDATE,
))
KNOWN_CHANGE_CLASSES = DELEGATABLE_CHANGE_CLASSES.union((
    CHANGE_REQUIRED_DEMOTE,
    CHANGE_BATCH_RETIRE,
    CHANGE_OPEN_WORK_SPEC_UPDATE,
    CHANGE_GAP_ROUTING_RECONCILIATION,
    CHANGE_PROPERTY_STATE_ADOPTION,
))

# Compatibility names remain direct projections of the neutral Tool owners.
# Amendment policy classifies authorized changes; it does not own document
# shape merely because it must inspect that shape.
PAGE_FIELDS = coverage_contract.COVERAGE_PAGE_FIELDS
PROMOTION_FIELDS = coverage_contract.COVERAGE_PROMOTION_FIELDS
REROUTE_FIELDS = coverage_contract.COVERAGE_REROUTE_FIELDS
BATCH_SPEC_FIELDS = coverage_contract.COVERAGE_BATCH_SPEC_FIELDS
WORK_SPEC_FIELDS = work_spec_contract.WORK_SPEC_BINDING_FIELDS
TOP_LEVEL_FIELDS = coverage_contract.COVERAGE_TOP_LEVEL_FIELDS
IDENTITY_FIELDS = frozenset((
    "schema_version", "task_id", "standards_version",
    "selected_profile_manifest",
))
TERMINAL_STATES = runtime_state_contract.QUEUE_TERMINAL_STATES


class AmendmentPolicyError(ValueError):
    """A proposal or authority record is outside the closed v1 protocol."""


class UserDecisionRequired(AmendmentPolicyError):
    """The proposal is known and executable, but not contract-delegated."""


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _string_list_errors(value, label):
    if not isinstance(value, list) or not all(_nonempty(item) for item in value):
        return ["%s must be an explicit string list" % label]
    errors = []
    if value != sorted(value):
        errors.append("%s must be sorted" % label)
    if len(value) != len(set(value)):
        errors.append("%s must not contain duplicates" % label)
    return errors


def amendment_authority_errors(value, label="amendment_authority"):
    """Return closed-shape errors for one Task Contract authority block."""
    if not isinstance(value, dict):
        return ["%s must be a mapping" % label]
    errors = []
    missing = sorted(AUTHORITY_FIELDS - set(value))
    extra = sorted(set(value) - AUTHORITY_FIELDS)
    if missing:
        errors.append("%s misses field(s): %s" % (label, ", ".join(missing)))
    if extra:
        errors.append("%s has unsupported field(s): %s" %
                      (label, ", ".join(extra)))
    if value.get("schema_version") != AUTHORITY_SCHEMA_VERSION:
        errors.append("%s schema_version must be %d" %
                      (label, AUTHORITY_SCHEMA_VERSION))
    if not _nonempty(value.get("authority_id")):
        errors.append("%s authority_id must be a non-empty string" % label)
    mode = value.get("mode")
    if mode not in AUTHORITY_MODES:
        errors.append("%s mode must be one of %s" %
                      (label, ", ".join(sorted(AUTHORITY_MODES))))
    allowed = value.get("allowed_change_classes")
    errors.extend(_string_list_errors(
        allowed, "%s.allowed_change_classes" % label))
    if isinstance(allowed, list):
        unknown = sorted(set(allowed) - DELEGATABLE_CHANGE_CLASSES)
        if unknown:
            errors.append("%s names unsupported delegated class(es): %s" %
                          (label, ", ".join(unknown)))
        if mode == "user-only" and allowed:
            errors.append("%s user-only mode requires an empty allowlist" % label)
    return errors


def authority_sha256(value):
    errors = amendment_authority_errors(value)
    if errors:
        raise AmendmentPolicyError("; ".join(errors))
    return kblib.sha256_bytes(kblib.canonical_yaml(value))


def _map_by_id(values, field, label):
    if not isinstance(values, list):
        raise AmendmentPolicyError("%s must be an explicit list" % label)
    result = {}
    for index, value in enumerate(values):
        if not isinstance(value, dict) or not _nonempty(value.get(field)):
            raise AmendmentPolicyError(
                "%s[%d] must be a mapping with %s" % (label, index, field))
        key = value[field]
        if key in result:
            raise AmendmentPolicyError("%s repeats %s %s" %
                                       (label, field, key))
        result[key] = value
    return result


def _changed_fields(before, after):
    return sorted(field for field in set(before).union(after)
                  if before.get(field) != after.get(field))


def _queue_items(queue):
    if not isinstance(queue, dict):
        raise AmendmentPolicyError("Required Queue must be a mapping")
    return _map_by_id(queue.get("required_queue"), "id", "Required Queue")


def _batch_refs(page):
    result = set()
    if isinstance(page, dict):
        for field in sorted(coverage_contract.COVERAGE_REROUTE_FIELDS):
            value = page.get(field)
            if _nonempty(value):
                result.add(value)
    return result


def derive_amendment_impact(current, proposal, queue):
    """Derive the exact v1 change-class set and writer operation.

    Unsupported effects are returned as ``forbidden_reasons`` rather than
    silently collapsed into a known class.  Callers must refuse any nonempty
    reason set.
    """
    if not isinstance(current, dict) or not isinstance(proposal, dict):
        raise AmendmentPolicyError("Coverage before/after must be mappings")

    reasons = []
    classes = set()
    affected_pages = set()
    affected_batches = set()

    unknown_top = sorted((set(current).union(proposal)) - TOP_LEVEL_FIELDS)
    changed_unknown_top = [field for field in unknown_top
                           if current.get(field) != proposal.get(field)]
    if changed_unknown_top:
        reasons.append("unsupported Coverage top-level field change(s): %s" %
                       ", ".join(changed_unknown_top))
    for field in IDENTITY_FIELDS:
        if current.get(field) != proposal.get(field):
            reasons.append("Coverage proposal may not change identity field %s" %
                           field)
    if current.get("maintenance_candidates") != proposal.get(
            "maintenance_candidates"):
        reasons.append("operational Amendment may not change maintenance_candidates")
    if current.get("open_gaps") != proposal.get("open_gaps"):
        classes.add(CHANGE_GAP_ROUTING_RECONCILIATION)
        try:
            gap_report = batch_settlement.amendment_gap_reconciliation_report(
                current, proposal, queue)
            reasons.extend(gap_report["errors"])
            affected_pages.update(gap_report["changed_pages"])
            affected_batches.update(gap_report["changed_batches"])
        except ValueError as exc:
            reasons.append("invalid gap-routing reconciliation: %s" % exc)

    current_pages = _map_by_id(current.get("pages"), "path", "Coverage pages")
    proposed_pages = _map_by_id(proposal.get("pages"), "path",
                                "Coverage proposal pages")
    for path in sorted(set(current_pages).union(proposed_pages)):
        before = current_pages.get(path)
        after = proposed_pages.get(path)
        if before == after:
            continue
        affected_pages.add(path)
        if before is None:
            extra = sorted(set(after) - PAGE_FIELDS)
            if extra:
                reasons.append("new Coverage page %s has unsupported field(s): %s" %
                               (path, ", ".join(extra)))
            if after.get("coverage_disposition") != "required":
                reasons.append("new Coverage page %s is not Required; v1 only "
                               "delegates Required-object growth" % path)
            else:
                classes.add(CHANGE_REQUIRED_ADD)
            if "property_state" not in after or not isinstance(
                    after.get("property_state"), dict):
                reasons.append(
                    "new Coverage page %s must carry explicit "
                    "property_state mapping" % path)
            elif after.get("property_state"):
                reasons.append(
                    "new Coverage page %s may not claim pre-existing current "
                    "property evidence" % path)
            if "legacy_property_state" in after:
                reasons.append(
                    "new Coverage page %s may not claim legacy property "
                    "observations" % path)
            affected_batches.update(_batch_refs(after))
            continue
        if after is None:
            reasons.append("Coverage page removal is unsupported in v1: %s" % path)
            affected_batches.update(_batch_refs(before))
            continue

        changed = set(_changed_fields(before, after))
        migration_fields = {"property_state", "legacy_property_state"}
        if changed and changed.issubset(migration_fields):
            if ("property_state" not in before and
                    after.get("property_state") == {} and
                    "legacy_property_state" not in before and
                    ("legacy_property_state" not in after or
                     isinstance(after.get("legacy_property_state"), dict))):
                classes.add(CHANGE_PROPERTY_STATE_ADOPTION)
                continue
            reasons.append(
                "Coverage page %s property-state migration may only adopt "
                "one absent owner mapping as property_state: {} plus optional "
                "legacy_property_state observations" % path)
            continue

        affected_batches.update(_batch_refs(before))
        affected_batches.update(_batch_refs(after))
        extra = sorted((set(before).union(after)) - PAGE_FIELDS)
        changed_extra = [field for field in extra
                         if before.get(field) != after.get(field)]
        if changed_extra:
            reasons.append("Coverage page %s changes unsupported field(s): %s" %
                           (path, ", ".join(changed_extra)))
        before_disposition = before.get("coverage_disposition")
        after_disposition = after.get("coverage_disposition")
        if before_disposition != "required" and after_disposition == "required":
            unsupported = sorted(changed - PROMOTION_FIELDS)
            if unsupported:
                reasons.append("Required promotion %s changes unsupported field(s): %s" %
                               (path, ", ".join(unsupported)))
            classes.add(CHANGE_REQUIRED_PROMOTE)
        elif before_disposition == "required" and after_disposition != "required":
            classes.add(CHANGE_REQUIRED_DEMOTE)
        elif before_disposition == "required" and after_disposition == "required":
            if changed.issubset(REROUTE_FIELDS):
                classes.add(CHANGE_REQUIRED_REROUTE)
            else:
                unsupported = sorted(changed - REROUTE_FIELDS)
                reasons.append("existing Required page %s changes field(s) outside "
                               "queued routing: %s" %
                               (path, ", ".join(unsupported)))
                if changed.intersection(REROUTE_FIELDS):
                    classes.add(CHANGE_REQUIRED_REROUTE)
        else:
            reasons.append("existing non-Required page %s metadata change is "
                           "unsupported in v1" % path)

    current_specs = _map_by_id(current.get("batch_specs"), "id",
                               "Coverage batch_specs")
    proposed_specs = _map_by_id(proposal.get("batch_specs"), "id",
                                "Coverage proposal batch_specs")
    items = _queue_items(queue)
    # A terminal Queue item owns its sealed structure.  Its lingering
    # batch_specs row is historical input that the compiler deliberately
    # ignores; editing or retiring that stale row is therefore not an
    # operational Amendment effect and must not turn an unrelated replan into
    # cancel-batch.
    removed_specs = {
        batch_id for batch_id in set(current_specs) - set(proposed_specs)
        if (items.get(batch_id) or {}).get("state") not in TERMINAL_STATES
    }
    for batch_id in sorted(set(current_specs).union(proposed_specs)):
        before = current_specs.get(batch_id)
        after = proposed_specs.get(batch_id)
        if before == after:
            continue
        item = items.get(batch_id)
        state = item.get("state") if isinstance(item, dict) else None
        if state in TERMINAL_STATES:
            continue
        affected_batches.add(batch_id)
        if before is None:
            extra = sorted(set(after) - BATCH_SPEC_FIELDS)
            if extra:
                reasons.append("new batch %s has unsupported field(s): %s" %
                               (batch_id, ", ".join(extra)))
            classes.add(CHANGE_BATCH_ADD)
            continue
        if after is None:
            classes.add(CHANGE_BATCH_RETIRE)
            continue
        changed = set(_changed_fields(before, after))
        if state == "queued":
            classes.add(CHANGE_QUEUED_BATCH_UPDATE)
        elif (state == "open" and changed and
              changed.issubset(WORK_SPEC_FIELDS) and
              item.get("hold_state") == "revalidation-required"):
            classes.add(CHANGE_OPEN_WORK_SPEC_UPDATE)
        else:
            reasons.append("batch %s structure cannot change while state=%r" %
                           (batch_id, state))

    scope_changed = current.get("scope_version") != proposal.get("scope_version")
    scope_classes = {CHANGE_REQUIRED_ADD, CHANGE_REQUIRED_PROMOTE,
                     CHANGE_REQUIRED_DEMOTE}
    non_gap_classes = classes - {CHANGE_GAP_ROUTING_RECONCILIATION}
    if CHANGE_GAP_ROUTING_RECONCILIATION in classes and non_gap_classes:
        reasons.append(
            "gap-routing reconciliation may not be mixed with Scope/Queue "
            "structure changes in protocol v1")
    if (CHANGE_PROPERTY_STATE_ADOPTION in classes and
            classes != {CHANGE_PROPERTY_STATE_ADOPTION}):
        reasons.append(
            "property-state adoption may not be mixed with Scope, routing, "
            "gap, or batch changes")
    if classes == {CHANGE_PROPERTY_STATE_ADOPTION}:
        operation = "property-state-migration"
    elif classes == {CHANGE_GAP_ROUTING_RECONCILIATION}:
        operation = "gap-routing-reconciliation"
    elif removed_specs:
        operation = "cancel-batch"
    elif classes.intersection(scope_classes):
        operation = "scope-replan"
    else:
        operation = "queue-replan"
    if operation in ("queue-replan", "gap-routing-reconciliation",
                     "property-state-migration") and \
            scope_changed:
        reasons.append("%s effects may not change scope_version" % operation)
    if operation in ("scope-replan", "cancel-batch") and not scope_changed:
        reasons.append("%s effects must change scope_version" % operation)
    if not classes and not reasons:
        reasons.append("proposal has no supported Amendment effect")

    return {
        "schema_version": 1,
        "change_classes": sorted(classes),
        "writer_operation": operation,
        "affected_pages": sorted(affected_pages),
        "affected_batches": sorted(affected_batches),
        "forbidden_reasons": sorted(set(reasons)),
    }


def impact_sha256(impact):
    return kblib.sha256_bytes(kblib.canonical_yaml({
        "schema_version": impact.get("schema_version"),
        "change_classes": copy.deepcopy(impact.get("change_classes")),
        "writer_operation": impact.get("writer_operation"),
        "affected_pages": copy.deepcopy(impact.get("affected_pages")),
        "affected_batches": copy.deepcopy(impact.get("affected_batches")),
        "forbidden_reasons": copy.deepcopy(impact.get("forbidden_reasons")),
    }))


def resolve_authority(contract, impact, requested_mode="auto",
                      approval_reference=None):
    """Resolve one impact to a persisted decision binding.

    ``approval_reference`` remains an assertion inside the deployment's local
    trust domain; this v1 intentionally does not claim host-backed identity.
    """
    if impact.get("forbidden_reasons"):
        raise AmendmentPolicyError("; ".join(impact["forbidden_reasons"]))
    classes = impact.get("change_classes")
    if (not isinstance(classes, list) or not classes or
            set(classes) - KNOWN_CHANGE_CLASSES):
        raise AmendmentPolicyError("impact has no closed known change-class set")
    if requested_mode not in ("auto", "contract-delegated", "explicit-user"):
        raise AmendmentPolicyError("unsupported decision mode %r" % requested_mode)

    authority = contract.get("amendment_authority") if isinstance(
        contract, dict) else None
    authority_errors = ([] if authority is None else
                        amendment_authority_errors(
                            authority, "Task Contract amendment_authority"))
    if authority_errors:
        raise AmendmentPolicyError("; ".join(authority_errors))
    delegated = bool(
        isinstance(authority, dict) and
        authority.get("mode") == "delegated-integrator" and
        set(classes).issubset(set(authority.get("allowed_change_classes") or []))
    )

    if requested_mode == "contract-delegated" and not delegated:
        raise UserDecisionRequired(
            "Task Contract does not delegate change class(es): %s" %
            ", ".join(classes))
    if requested_mode == "auto" and not delegated:
        if _nonempty(approval_reference):
            requested_mode = "explicit-user"
        else:
            raise UserDecisionRequired(
                "fresh user decision required for change class(es): %s" %
                ", ".join(classes))

    if requested_mode in ("auto", "contract-delegated"):
        return {
            "decision_mode": "contract-delegated",
            "authority_id": authority["authority_id"],
            "authority_sha256": authority_sha256(authority),
            "change_classes": list(classes),
            "amendment_impact_sha256": impact_sha256(impact),
            "approval_reference": "contract:%s" % authority["authority_id"],
        }
    if not _nonempty(approval_reference):
        raise UserDecisionRequired(
            "explicit-user decision requires a non-empty approval_reference")
    return {
        "decision_mode": "explicit-user",
        "authority_id": None,
        "authority_sha256": None,
        "change_classes": list(classes),
        "amendment_impact_sha256": impact_sha256(impact),
        "approval_reference": approval_reference,
    }


def require_decision_binding(contract, impact, record):
    """Re-derive and compare a persisted current-protocol decision binding."""
    mode = record.get("decision_mode")
    approval = record.get("approval_reference")
    expected = resolve_authority(
        contract, impact,
        requested_mode=(mode if mode in ("contract-delegated", "explicit-user")
                        else "invalid"),
        approval_reference=approval,
    )
    for field in ("decision_mode", "authority_id", "authority_sha256",
                  "change_classes", "amendment_impact_sha256",
                  "approval_reference"):
        if record.get(field) != expected[field]:
            raise AmendmentPolicyError(
                "Amendment decision binding %s=%r, expected %r" %
                (field, record.get(field), expected[field]))
    if record.get("operation") != impact.get("writer_operation"):
        raise AmendmentPolicyError(
            "Amendment operation %r does not match derived writer %r" %
            (record.get("operation"), impact.get("writer_operation")))
    return expected
