"""Pure machine shapes shared by Coverage and Coverage Delta consumers.

The Coverage runtime validator, Amendment classifier, Queue compiler, and
Delta apply/check paths each enforce a different operation over the same
documents.  This module owns their shared field sets and the unique page-form
classification derived from those sets; it owns no policy, validation verdict,
state, or write path.
"""

import Tools.execution.planning.work_spec_contract as work_spec_contract


COVERAGE_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "task_id", "updated_at", "scope_version",
    "upstream_revision_id", "selected_profile_manifest", "batch_specs",
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
COVERAGE_RUNTIME_PAGE_FIELDS = COVERAGE_RUNTIME_PAGE_REQUIRED_FIELDS

PAGE_FORM_PLANNING = "planning"
PAGE_FORM_CURRENT_RUNTIME = "current-runtime"
PAGE_FORM_MALFORMED = "malformed"

_RUNTIME_STATE_FIELDS = frozenset((
    "authoring_status", "gate_receipts", "property_state",
))
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


def classify_page_form(record):
    """Classify one Coverage page by its exact closed machine shape.

    Planning rows claim no current page state.  Current runtime rows carry the
    complete runtime-owner field set.  Everything partial, open-ended, or
    non-mapping is malformed.
    """
    if not isinstance(record, dict):
        return PAGE_FORM_MALFORMED
    fields = frozenset(record)
    if fields == COVERAGE_PLANNED_PAGE_FIELDS:
        return PAGE_FORM_PLANNING
    if (COVERAGE_RUNTIME_PAGE_REQUIRED_FIELDS.issubset(fields) and
            fields.issubset(COVERAGE_RUNTIME_PAGE_FIELDS)):
        return PAGE_FORM_CURRENT_RUNTIME
    return PAGE_FORM_MALFORMED


def is_planning_page(record):
    """Whether ``record`` is the complete planning-only form."""
    return classify_page_form(record) == PAGE_FORM_PLANNING


def is_complete_planning_page(record):
    """Return whether ``record`` is exactly the closed planning form."""
    return classify_page_form(record) == PAGE_FORM_PLANNING


def page_shape_errors(record, label):
    """Validate the closed planning/runtime union for one Coverage row."""
    if not isinstance(record, dict):
        return ["%s must be a mapping" % label]
    form = classify_page_form(record)
    if form == PAGE_FORM_PLANNING:
        required = allowed = COVERAGE_PLANNED_PAGE_FIELDS
    elif form == PAGE_FORM_MALFORMED and not \
            _RUNTIME_STATE_FIELDS.intersection(record):
        required = allowed = COVERAGE_PLANNED_PAGE_FIELDS
    else:
        required = COVERAGE_RUNTIME_PAGE_REQUIRED_FIELDS
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
    if (form not in (PAGE_FORM_PLANNING, PAGE_FORM_CURRENT_RUNTIME) and
            _RUNTIME_STATE_FIELDS.intersection(record)):
        partial = sorted(_RUNTIME_STATE_FIELDS - set(record))
        if partial:
            errors.append(
                "%s partially materializes runtime state; missing %s" %
                (label, ", ".join(partial)))
    return errors
