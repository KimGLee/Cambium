"""The Required Queue runtime, as modules instead of one file.

`check_queue.py` was seventeen thousand lines holding one runtime, one CLI and
one Gate producer, and the boundary contract in K00/18 could say nothing about
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
    ANY_PRODUCER_ERA_VERSION,
    APPLY_DELTA_TOOL_VERSION,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_ID_RE,
    BATCH_REVIEW_GATE_ID,
    CORPUS_PLAN_TOOL,
    CORPUS_PLAN_TOOL_VERSION,
    COVERAGE_PATH,
    EXECUTION_MODES,
    GATE_CHECK,
    HOLDS,
    LEGACY_PROPERTY_ADOPTION_OPERATION,
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
    SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS,
    SUPPORTED_CHECK_QUEUE_TOOL_VERSIONS,
    SUPPORTED_UPDATE_QUEUE_TOOL_VERSIONS,
    TASK_STATES,
    TERMINAL_PROOF_TOOL,
    TERMINAL_PROOF_TOOL_VERSION,
    TERMINAL_STATES,
    TOOL,
    TOOL_VERSION,
    UPDATE_QUEUE_TOOL_VERSION,
)
from queue_runtime.primitives import (  # noqa: F401
    _acyclic,
    _closed_mapping_errors,
    _explicit_string_list_errors,
    _identity,
    _nonempty_string,
    _timestamp_value,
    _valid_timestamp,
)
from queue_runtime.repofs import (  # noqa: F401
    _load_state,
    _path_error,
    _repository_evidence_file,
)
from queue_runtime.evidence_identity import (  # noqa: F401
    EVIDENCE_IDENTITY_USES,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_TERMINAL_HISTORY,
    _current_property_receipt,
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
    partition_revalidation_owner_claims,
    producer_module,
    project_adoption_gate_ids,
    projected_revalidation_owners,
    queue_gate_id_for_mode,
    receipt_matches_gate_id,
    registered_gate_dimensions,
    registered_gate_position,
    standards_gate_capability_registry,
    standards_gate_registry,
    standards_revalidation_capabilities,
    standards_revalidation_owner,
)
from queue_runtime.locks import (  # noqa: F401
    _bind_generic_lock_receipts,
    _bind_lock_delta_archives,
    _bind_lock_receipts,
    _bind_lock_state_phases,
    _writer_locks,
)
from queue_runtime.policy_exceptions import (  # noqa: F401
    _policy_exception_errors,
    _sealed_policy_exception_errors,
)
from queue_runtime.producer_era import (  # noqa: F401
    _producer_era_errors,
    _standards_adoption_owner_projection_required,
    _standards_adoption_profile_contract_required,
    _standards_adoption_profile_inputs_required,
    _standards_adoption_state_file_required,
    _standards_adoption_upstream_required,
    _terminal_proof_profile_binding_errors,
    accounted_standards_versions,
)
from queue_runtime.profile_view import (  # noqa: F401
    EXPRESSION_LAYER_SLOT,
    _authorized_profile_view_errors,
    _profile_view_snapshot_error,
    _public_profile_load_evidence,
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
    _Catalog,
    _cold_path_within_root,
    _cold_receipt_store,
    _receipt_catalog,
    _require_receipt,
    current_receipt_catalog,
    delta_gate_receipt_ids,
    historical_receipt_catalog,
)
from queue_runtime.task_contract import (  # noqa: F401
    READ_SET_BOUNDARY_OWNER_PATH,
    _contract_anchor_chain,
    _contract_sha256,
    _contract_sha_at_revision,
    _live_read_set_load_findings,
    _read_set_load_closure,
)
from queue_runtime.work_spec import (  # noqa: F401
    WORK_SPEC_FIELDS,
    WORK_SPEC_PREFIX,
    _work_spec_binding_errors,
    _work_spec_errors,
)
from queue_runtime.amendments import (  # noqa: F401
    CONTRACT_AMENDMENT_PLAN_PREFIX,
    _cross_ledger_amendment_errors,
    _initial_queue_receipt_errors,
    _operational_amendment_registration_errors,
    _pending_cross_ledger_amendments,
    _queue_replan_amendment_errors,
)
from queue_runtime.authority import (  # noqa: F401
    require_runtime_authority_current,
    runtime_authority_context,
    runtime_authority_currency_errors,
    runtime_authority_lock_fields,
    runtime_authority_validation_kwargs,
)
from queue_runtime.control_plane import (  # noqa: F401
    _unadmitted_profile_hub_paths,
    batch_touches_control_plane,
    hub_page_admission,
    profile_hub_paths,
)
from queue_runtime.coverage import (  # noqa: F401
    COVERAGE_BATCH_SPEC_FIELDS,
    _coverage_batch_spec_errors,
    _coverage_provenance_errors,
    _coverage_records,
    coverage_reviewed_era_exception,
    unsupported_reviewed_records,
)
from queue_runtime.item_history import (  # noqa: F401
    _latest_merge_transition,
    _ordered_item_transitions,
    invalidated_receipt_consumers,
    item_revalidation_discharges,
    item_undischarged_revalidation_hold,
    undischarged_revalidation_hold,
    walk_revalidation_hold,
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
    _last_reconciled_guidance_id,
    _pending_control_ids,
    _task_transition_receipt_record_errors,
)
