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

COVERAGE_PAGE_FIELDS = frozenset((
    "path", "coverage_disposition", "canonical_owner", "type", "priority",
    "tier", "authoring_status", "prerequisites", "batch", "next_batch",
    "deferred_reason", "reentry_condition", "gate_receipts",
    "property_state", "legacy_property_state",
))

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
