"""Pure machine shapes shared by Coverage and Coverage Delta consumers.

The Coverage runtime validator, Amendment classifier, Queue compiler, and
Delta apply/check paths each enforce a different operation over the same
documents.  This module owns only their shared field sets; it owns no policy,
validation verdict, state, or write path.
"""

import work_spec_contract


COVERAGE_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "task_id", "updated_at", "scope_version",
    "standards_version", "selected_profile_manifest", "batch_specs",
    "maintenance_candidates", "pages", "open_gaps",
))

COVERAGE_PLANNED_PAGE_FIELDS = frozenset((
    "path", "coverage_disposition", "canonical_owner", "type", "priority",
    "tier", "prerequisites", "batch", "next_batch", "deferred_reason",
    "reentry_condition",
))

COVERAGE_RUNTIME_PAGE_REQUIRED_FIELDS = COVERAGE_PLANNED_PAGE_FIELDS.union((
    "authoring_status", "gate_receipts", "property_state",
))
COVERAGE_RUNTIME_PAGE_FIELDS = COVERAGE_RUNTIME_PAGE_REQUIRED_FIELDS.union((
    "legacy_property_state",
))

# Historical public name retained for the complete runtime row shape.  A
# planning-only row is deliberately a strict subset and is identified through
# ``is_planning_page`` rather than by inventing an authoring status.
COVERAGE_PAGE_FIELDS = COVERAGE_RUNTIME_PAGE_FIELDS

COVERAGE_PROMOTION_FIELDS = COVERAGE_PAGE_FIELDS - frozenset(("path",))
COVERAGE_REROUTE_FIELDS = frozenset(("batch", "next_batch"))

COVERAGE_BATCH_SPEC_FIELDS = frozenset((
    "id", "family", "order_hint", "source_route", "execution_mode",
    "depends_on", "confirmation_required",
)).union(work_spec_contract.WORK_SPEC_BINDING_FIELDS)

COVERAGE_DELTA_FIELDS = frozenset((
    "batch", "generated_at", "pages", "open_gaps_added",
    "open_gaps_closed", "next_batch_updates", "watermark_advance",
))

# Worker page deltas may carry content/evidence updates, but never these
# reconciliation- and Queue-owned Coverage fields.  Apply and admission must
# reject the identical set even when a supplied value equals the live value.
COVERAGE_DELTA_PAGE_CONTROL_FIELDS = frozenset((
    "coverage_disposition", "canonical_owner", "batch", "next_batch",
    "priority", "tier", "type", "prerequisites", "deferred_reason",
    "reentry_condition",
))


def is_planning_page(record):
    """Whether ``record`` declares work without claiming current page state.

    The three runtime-owner fields move together.  Their complete absence is
    the planning form; partial presence is malformed and remains visible to
    the validators rather than being silently classified as either form.
    """
    if not isinstance(record, dict):
        return False
    runtime_fields = {"authoring_status", "gate_receipts", "property_state"}
    return not runtime_fields.intersection(record)


def is_complete_planning_page(record):
    """Return whether ``record`` is exactly the closed planning form."""
    return (is_planning_page(record) and
            set(record) == COVERAGE_PLANNED_PAGE_FIELDS)


def page_shape_errors(record, label, *, allow_legacy_missing_property=False):
    """Validate the closed planning/runtime union for one Coverage row."""
    if not isinstance(record, dict):
        return ["%s must be a mapping" % label]
    legacy_runtime = (
        allow_legacy_missing_property and
        "authoring_status" in record and
        "gate_receipts" in record and
        "property_state" not in record
    )
    if is_planning_page(record):
        required = allowed = COVERAGE_PLANNED_PAGE_FIELDS
    else:
        required = (COVERAGE_RUNTIME_PAGE_REQUIRED_FIELDS -
                    ({"property_state"} if legacy_runtime else set()))
        allowed = COVERAGE_RUNTIME_PAGE_FIELDS
    missing = sorted(required - set(record))
    extra = sorted(set(record) - allowed)
    errors = []
    if missing:
        errors.append("%s misses required field(s): %s" %
                      (label, ", ".join(missing)))
    if extra:
        errors.append("%s has unsupported field(s): %s" %
                      (label, ", ".join(extra)))
    if not is_planning_page(record) and not legacy_runtime:
        runtime_fields = {"authoring_status", "gate_receipts", "property_state"}
        partial = sorted(runtime_fields - set(record))
        if partial:
            errors.append(
                "%s partially materializes runtime state; missing %s" %
                (label, ", ".join(partial)))
    return errors
