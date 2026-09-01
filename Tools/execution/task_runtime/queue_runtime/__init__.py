"""The Required Queue runtime, as modules instead of one file.

The runtime is split into named responsibilities with a declared dependency
direction.  This package is the stable domain-facing API for Queue runtime
constants and operations.  The top-level `check_queue.py` remains a thin
CLI adapter and exposes no Python compatibility surface.

Two rules hold this together and both are machine-checked.  Intra-package
imports are absolute and name the defining submodule -- never `from . import`,
which the boundary collector cannot see, and never the package root, which
would point a submodule back at this file.  And every intra-package edge runs
strictly downward through the declared ranks, because `import_graph` collapses
a package to one node and cannot see a cycle that stays inside it.

This file defines no governance or algorithms.  It re-exports the public
surface implemented by the owning submodules so callers do not depend on their
physical layout.
"""

import os
import sys


from Tools.execution.task_runtime.queue_runtime.canon import (  # noqa: F401
    ACTIVE_STATES,
    APPLY_DELTA_TOOL_VERSION,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_ID_RE,
    COMPILE_QUEUE_TOOL,
    COMPILE_QUEUE_TOOL_VERSION,
    COVERAGE_PATH,
    GATE_CHECK,
    HOLDS,
    MANUAL_ATTESTATION_TOOL,
    PROGRESS_PATH,
    QUEUE_PATH,
    SHA256_RE,
    STANDARDS_ADOPTION_PLAN_PREFIX,
    STATES,
    TERMINAL_STATES,
    TOOL,
    TOOL_VERSION,
    UPDATE_QUEUE_TOOL_VERSION,
)
from Tools.governance.standards.adoption_lineage_contract import (  # noqa: F401
    STANDARDS_ADOPTION_TOOL,
)
from Tools.platform.common.primitives import (  # noqa: F401
    nonempty_string,
    timestamp_value,
    valid_timestamp,
)
from Tools.execution.task_runtime.queue_runtime.evidence_identity import (  # noqa: F401
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    evidence_identity_errors,
    property_receipt_utc_date,
)
from Tools.execution.task_runtime.queue_runtime.gate_registry import (  # noqa: F401
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
from Tools.execution.task_runtime.queue_runtime.policy_exceptions import (  # noqa: F401
    policy_exception_errors,
)
from Tools.execution.task_runtime.queue_runtime.history_identity import accounted_upstream_revision_ids  # noqa: F401
from Tools.execution.task_runtime.queue_runtime.profile_view import (  # noqa: F401
    authorized_profile_view_errors,
    public_profile_load_evidence,
    active_standards_authorized_view,
    active_standards_view_currency_errors,
    profile_load_authorized_view,
    profile_load_authorized_view_currency_errors,
    profile_load_errors,
    profile_load_evidence,
)
from Tools.execution.task_runtime.queue_runtime.receipts import (  # noqa: F401
    QUEUE_TRANSITION_RECEIPT_TYPE_ID,
    cold_receipt_store,
    current_queue_transition_receipt_errors,
    receipt_catalog,
    require_receipt,
    current_receipt_catalog,
    delta_gate_receipt_ids,
    historical_receipt_catalog,
    make_queue_receipt,
    receipt_group_sha256,
)
from Tools.execution.task_runtime.queue_runtime.task_contract import (  # noqa: F401
    contract_anchor_chain,
    contract_sha256,
    read_set_load_closure,
)
from Tools.execution.task_runtime.queue_runtime.work_spec import (  # noqa: F401
    work_spec_binding_errors,
)
from Tools.execution.task_runtime.queue_runtime.amendments import (  # noqa: F401
    CONTRACT_AMENDMENT_PLAN_PREFIX,
    operational_amendment_registration_errors,
)
from Tools.execution.task_runtime.queue_runtime.authority import (  # noqa: F401
    require_runtime_authority_current,
    runtime_authority_context,
    runtime_authority_currency_errors,
    runtime_authority_lock_fields,
    runtime_authority_validation_kwargs,
    runtime_metadata_execution_contract,
)
from Tools.execution.task_runtime.queue_runtime.control_plane import (  # noqa: F401
    batch_touches_control_plane,
)
from Tools.execution.task_runtime.queue_runtime.coverage import (  # noqa: F401
    reviewed_without_current_evidence,
)
from Tools.execution.task_runtime.queue_runtime.item_history import (  # noqa: F401
    item_revalidation_discharges,
    item_undischarged_revalidation_hold,
)
from Tools.execution.task_runtime.queue_runtime.property_state import (  # noqa: F401
    current_opening_semantic_context,
)
from Tools.execution.task_runtime.queue_runtime.review import (  # noqa: F401
    activation_phase_delivery_errors,
    resolve_activation_phase_receipt,
    batch_review_judgment_errors,
    batch_review_receipt_errors,
    task_phase_delivery_errors,
)
from Tools.execution.task_runtime.queue_runtime.task_record import (  # noqa: F401
    pending_control_ids,
)
from Tools.execution.task_runtime.queue_runtime.adoption import (  # noqa: F401
    standards_adoption_errors,
    standards_adoption_plan_errors,
)
from Tools.execution.task_runtime.queue_runtime.delta import (  # noqa: F401
    batch_reference_settlement_errors,
    delta_apply_write_barrier,
)
from Tools.execution.task_runtime.queue_runtime.maintenance import (  # noqa: F401
    MaintenanceConsumerContext,
    maintenance_completion_gate_errors,
    maintenance_gate_time_errors,
)
from Tools.execution.task_runtime.queue_runtime.revalidation import (  # noqa: F401
    consumed_standards_revalidation_keys,
    current_attempt_evidence_barrier,
    outstanding_standards_revalidation,
    standards_revalidation_context,
    standards_revalidation_producer_eligibility,
    standards_revalidation_receipt_errors,
    standards_revalidation_requirements,
)
from Tools.execution.task_runtime.queue_runtime.close_gate import (  # noqa: F401
    close_gate_receipt_errors,
)
from Tools.execution.task_runtime.queue_runtime.task_progress import (  # noqa: F401
    COMPLETION_SEMANTICS,
    CONTRACT_FIELDS,
)
from Tools.execution.task_runtime.queue_runtime.item_evidence import (  # noqa: F401
    INVALIDATION_APPLIED_ROLLBACK_FIELDS,
    INVALIDATION_FIELDS,
)
from Tools.execution.task_runtime.queue_runtime.resume import (  # noqa: F401
    actionable_revalidation_batches,
    batch_close_recovery_inventory,
    batch_close_transition_arguments,
    batch_close_update_command,
    maintenance_gate_inventory,
    resume_next_action,
)
from Tools.execution.task_runtime.queue_runtime.runtime import (  # noqa: F401
    COVERAGE_TOP_LEVEL_FIELDS,
    QUEUE_ITEM_FIELDS,
    required_queue_completion_errors,
)
