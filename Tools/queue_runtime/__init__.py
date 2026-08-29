"""The Required Queue runtime, as modules instead of one file.

`check_queue.py` was seventeen thousand lines holding one runtime, one CLI and
one Gate producer, and the Tool module boundary contract could say nothing about
its inside: a module is the unit the contract speaks about, so a single module
is a single answer to every question the contract asks.  The runtime is split
here into named responsibilities with a declared direction between them; the
CLI entry and the Gate producer stay in `check_queue.py`, which also remains
the permanent façade every existing importer and test reads.

Two rules hold this together and both are machine-checked.  Intra-package
imports are absolute and name the defining submodule -- never `from . import`,
which the boundary collector cannot see, and never the package root, which
would point a submodule back at this file.  And every intra-package edge runs
strictly downward through the declared ranks, because `import_graph` collapses
a package to one node and cannot see a cycle that stays inside it.

This file re-exports the surface the façade needs and defines nothing.  A name
is exported here because something outside the package reads it, which is also
what makes the register able to say who offers what.
"""

import os
import sys

# Every submodule reads peer tools by their plain names, exactly as
# the rest of Tools/ does.  The package entry is the one place that
# can put the tools root on the path before any of them load.
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from queue_runtime.canon import (  # noqa: F401
    ACTIVE_STANDARDS_PATH,
    ACTIVE_STATES,
    APPLY_DELTA_TOOL_VERSION,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_ID_RE,
    BATCH_REVIEW_GATE_ID,
    COVERAGE_PATH,
    GATE_CHECK,
    HOLDS,
    MANUAL_ATTESTATION_TOOL,
    MANUAL_ATTESTATION_TOOL_VERSION,
    PROGRESS_PATH,
    QUEUE_PATH,
    REGISTER_AMENDMENT_TOOL_VERSION,
    SHA256_RE,
    STANDARDS_ADOPTION_PLAN_PREFIX,
    STANDARDS_ADOPTION_TOOL,
    STANDARDS_ADOPTION_TOOL_VERSION,
    STATES,
    TERMINAL_STATES,
    TOOL,
    TOOL_VERSION,
    UPDATE_QUEUE_TOOL_VERSION,
    WATERMARK_PATH,
)
from queue_runtime.primitives import (  # noqa: F401
    nonempty_string,
    timestamp_value,
    valid_timestamp,
)
from queue_runtime.evidence_identity import (  # noqa: F401
    EVIDENCE_IDENTITY_USES,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_TERMINAL_HISTORY,
    evidence_identity_errors,
    property_receipt_utc_date,
)
from queue_runtime.gate_registry import (  # noqa: F401
    BASE_RECEIPT_DIMENSIONS,
    NOT_BATCH_SCOPED_GATE,
    QUEUE_EXHAUSTED_GATE,
    STANDARDS_GATE_REGISTRY_PATH,
    gate_registry_producer_errors,
    partition_boundary_gates_by_lifecycle,
    producer_module,
    project_adoption_gate_ids,
    queue_gate_id_for_mode,
    receipt_matches_gate_id,
    registered_gate_position,
    standards_gate_capability_registry,
    standards_gate_registry,
)
from queue_runtime.policy_exceptions import (  # noqa: F401
    policy_exception_errors,
)
from queue_runtime.producer_era import (  # noqa: F401
    terminal_proof_profile_binding_errors,
    accounted_standards_versions,
)
from queue_runtime.profile_view import (  # noqa: F401
    EXPRESSION_LAYER_SLOT,
    authorized_profile_view_errors,
    public_profile_load_evidence,
    active_standards_authorized_view,
    active_standards_view_currency_errors,
    profile_load_authorized_view,
    profile_load_authorized_view_currency_errors,
    profile_load_errors,
    profile_load_evidence,
    selected_profile_manifest_errors,
)
from queue_runtime.receipts import (  # noqa: F401
    RECEIPT_REFERENCE_FIELDS,
    cold_receipt_store,
    receipt_catalog,
    require_receipt,
    current_receipt_catalog,
    delta_gate_receipt_ids,
    historical_receipt_catalog,
)
from queue_runtime.task_contract import (  # noqa: F401
    contract_anchor_chain,
    contract_sha256,
    live_read_set_load_findings,
    read_set_load_closure,
)
from queue_runtime.work_spec import (  # noqa: F401
    WORK_SPEC_FIELDS,
    WORK_SPEC_PREFIX,
    work_spec_binding_errors,
    work_spec_errors,
)
from queue_runtime.amendments import (  # noqa: F401
    CONTRACT_AMENDMENT_PLAN_PREFIX,
    operational_amendment_registration_errors,
)
from queue_runtime.authority import (  # noqa: F401
    RUNTIME_AUTHORITY_REGISTRY,
    require_runtime_authority_current,
    runtime_authority_registry,
    runtime_authority_context,
    runtime_authority_currency_errors,
    runtime_authority_lock_fields,
    runtime_authority_validation_kwargs,
    runtime_metadata_execution_contract,
)
from queue_runtime.control_plane import (  # noqa: F401
    unadmitted_profile_hub_paths,
    batch_touches_control_plane,
    profile_hub_paths,
)
from queue_runtime.coverage import (  # noqa: F401
    COVERAGE_BATCH_SPEC_FIELDS,
    coverage_provenance_errors,
    coverage_reviewed_era_exception,
    unsupported_reviewed_records,
)
from queue_runtime.item_history import (  # noqa: F401
    item_revalidation_discharges,
    item_undischarged_revalidation_hold,
)
from queue_runtime.property_state import (  # noqa: F401
    LEGACY_PROPERTY_STATE_FIELD,
    current_close_transition_metadata_errors,
    current_open_semantic_baseline_errors,
    review_property_evidence_errors,
    current_opening_semantic_baseline,
    current_opening_semantic_context,
)
from queue_runtime.review import (  # noqa: F401
    BATCH_REVIEW_CHECK,
    activation_phase_delivery_errors,
    batch_review_judgment_errors,
    batch_review_receipt_errors,
    judgment_record_set_sha256,
    substantive_review_errors,
    task_phase_delivery_errors,
)
from queue_runtime.task_record import (  # noqa: F401
    last_reconciled_guidance_id,
    pending_control_ids,
)
from queue_runtime.adoption import (  # noqa: F401
    standards_adoption_errors,
    standards_adoption_plan_errors,
)
from queue_runtime.delta import (  # noqa: F401
    closed_delta_apply_errors,
    batch_reference_settlement_errors,
    delta_apply_write_barrier,
)
from queue_runtime.maintenance import (  # noqa: F401
    latest_consumed_maintenance_gate,
    maintenance_completion_gate_errors,
    maintenance_gate_time_errors,
    previous_maintenance_candidate_state,
)
from queue_runtime.revalidation import (  # noqa: F401
    consumed_standards_revalidation_keys,
    current_attempt_evidence_barrier,
    outstanding_standards_revalidation,
    standards_revalidation_context,
    standards_revalidation_producer_eligibility,
    standards_revalidation_receipt_errors,
    standards_revalidation_requirements,
)
from queue_runtime.close_gate import (  # noqa: F401
    CLOSED_LIST_EVIDENCE_FIELDS,
    COMPACT_CLOSE_EVIDENCE_VERSIONS,
    HISTORICAL_CORPUS_PLAN_TOOL_VERSIONS,
    SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS,
    candidate_evidence_binding_errors,
    close_gate_receipt_errors,
)
from queue_runtime.task_progress import (  # noqa: F401
    CHECKPOINT_FIELDS,
    COMPLETION_SEMANTICS,
    CONTRACT_FIELDS,
    CONTRACT_OPTIONAL_FIELDS,
    GUIDANCE_DISPOSITIONS,
    global_transition_errors,
)
from queue_runtime.item_evidence import (  # noqa: F401
    INVALIDATION_APPLIED_ROLLBACK_FIELDS,
    INVALIDATION_FIELDS,
)
from queue_runtime.resume import (  # noqa: F401
    actionable_revalidation_batches,
    batch_close_recovery_inventory,
    maintenance_gate_inventory,
    resume_next_action,
)
from queue_runtime.runtime import (  # noqa: F401
    COVERAGE_TOP_LEVEL_FIELDS,
    QUEUE_ITEM_FIELDS,
    required_queue_completion_errors,
)
