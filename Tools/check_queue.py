#!/usr/bin/env python3
"""Validate Cambium's canonical Required Queue runtime state.

The checker reconciles the Queue with Coverage object assignments and the
Progress Ledger's accepted revisions/fingerprint.  It also validates explicit
manifests, dependency order, lifecycle evidence, holds, confirmation,
concurrency, and repository-contained paths.

Exit codes:
  0  current state and requested gate pass
  1  malformed/inconsistent state or a requested gate fails
  2  state is reliable, but work is held/not yet materialized, or resume-status
     found an existing non-terminal task or a possible interrupted writer

Usage:
  python3 Tools/check_queue.py ROOT [--require-ready B1]
      [--require-complete | --require-maintenance-complete | --resume-status]
      [--receipts .cambium/receipts/queue.jsonl]
"""

import contextlib
import copy
import datetime
import importlib
import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import check_profile
import amendment_policy
import contract_exception_policy
import batch_settlement
import card_activation
import candidate_lifecycle
import coverage_delta
import maintenance_candidates
import metadata_execution_contract
import metadata_property_state
import project_page_state
import standards_state
# The persisted typed Gate receipt validator this runtime asks for by
# name.  It used to be defined here and reach back into the Gate
# runtime through a function-body import; it now lives with the module
# whose object it validates, and the arrow points one way.
import metadata_gate_runtime

# The permanent facade.  Every name below is defined in `queue_runtime`
# and re-exported here because twenty-one shipped modules and twenty-one
# test files read it from `check_queue`.  Dropping a name is a
# compatibility break even when nothing in this file uses it.
from queue_runtime import (
    ACTIVE_STANDARDS_PATH,
    ACTIVE_STATES,
    ANY_PRODUCER_ERA_VERSION,
    APPLY_DELTA_TOOL_VERSION,
    BASE_RECEIPT_DIMENSIONS,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_ID_RE,
    BATCH_REVIEW_CHECK,
    BATCH_REVIEW_GATE_ID,
    CONTRACT_AMENDMENT_PLAN_PREFIX,
    CORPUS_PLAN_TOOL,
    CORPUS_PLAN_TOOL_VERSION,
    COVERAGE_BATCH_SPEC_FIELDS,
    COVERAGE_PATH,
    EVIDENCE_IDENTITY_USES,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_TERMINAL_HISTORY,
    EXECUTION_MODES,
    EXPRESSION_LAYER_SLOT,
    GATE_CHECK,
    HOLDS,
    LEGACY_PROPERTY_ADOPTION_OPERATION,
    MANUAL_ATTESTATION_TOOL,
    MANUAL_ATTESTATION_TOOL_VERSION,
    NOT_BATCH_SCOPED_GATE,
    PROGRESS_PATH,
    QUEUE_EXHAUSTED_GATE,
    QUEUE_PATH,
    READ_SET_BOUNDARY_OWNER_PATH,
    RECEIPT_REFERENCE_FIELDS,
    REGISTER_AMENDMENT_TOOL_VERSION,
    SHA256_RE,
    STANDARDS_ADOPTION_PLAN_PREFIX,
    STANDARDS_ADOPTION_TOOL,
    STANDARDS_ADOPTION_TOOL_VERSION,
    STANDARDS_GATE_REGISTRY_PATH,
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
    WORK_SPEC_FIELDS,
    WORK_SPEC_PREFIX,
    _Catalog,
    _acyclic,
    _authorized_profile_view_errors,
    _bind_generic_lock_receipts,
    _bind_lock_delta_archives,
    _bind_lock_receipts,
    _bind_lock_state_phases,
    _closed_mapping_errors,
    _cold_path_within_root,
    _cold_receipt_store,
    _contract_anchor_chain,
    _contract_sha256,
    _contract_sha_at_revision,
    _coverage_batch_spec_errors,
    _coverage_provenance_errors,
    _coverage_records,
    _cross_ledger_amendment_errors,
    _current_property_receipt,
    _explicit_string_list_errors,
    _identity,
    _initial_queue_receipt_errors,
    _last_reconciled_guidance_id,
    _latest_merge_transition,
    _live_read_set_load_findings,
    _load_state,
    _nonempty_string,
    _operational_amendment_registration_errors,
    _ordered_item_transitions,
    _path_error,
    _pending_control_ids,
    _pending_cross_ledger_amendments,
    _policy_exception_errors,
    _producer_era_errors,
    _profile_view_snapshot_error,
    _public_profile_load_evidence,
    _queue_replan_amendment_errors,
    _read_set_load_closure,
    _receipt_catalog,
    _repository_evidence_file,
    _require_receipt,
    _sealed_policy_exception_errors,
    _standards_adoption_owner_projection_required,
    _standards_adoption_profile_contract_required,
    _standards_adoption_profile_inputs_required,
    _standards_adoption_state_file_required,
    _standards_adoption_upstream_required,
    _task_transition_receipt_record_errors,
    _terminal_proof_profile_binding_errors,
    _timestamp_value,
    _unadmitted_profile_hub_paths,
    _valid_timestamp,
    _work_spec_binding_errors,
    _work_spec_errors,
    _writer_locks,
    accounted_standards_versions,
    activation_phase_delivery_errors,
    active_standards_authorized_view,
    active_standards_view_currency_errors,
    batch_review_judgment_errors,
    batch_review_receipt_errors,
    batch_touches_control_plane,
    coverage_reviewed_era_exception,
    current_receipt_catalog,
    delta_gate_receipt_ids,
    evidence_identity_errors,
    gate_registry_producer_errors,
    historical_receipt_catalog,
    hub_page_admission,
    invalidated_receipt_consumers,
    item_revalidation_discharges,
    item_undischarged_revalidation_hold,
    judgment_record_set_sha256,
    partition_boundary_gates_by_lifecycle,
    partition_revalidation_owner_claims,
    producer_module,
    profile_hub_paths,
    profile_load_authorized_view,
    profile_load_authorized_view_currency_errors,
    profile_load_errors,
    profile_load_evidence,
    project_adoption_gate_ids,
    projected_revalidation_owners,
    property_receipt_utc_date,
    queue_gate_id_for_mode,
    receipt_matches_gate_id,
    registered_gate_dimensions,
    registered_gate_position,
    require_runtime_authority_current,
    runtime_authority_context,
    runtime_authority_currency_errors,
    runtime_authority_lock_fields,
    runtime_authority_validation_kwargs,
    selected_profile_manifest_errors,
    standards_gate_capability_registry,
    standards_gate_registry,
    standards_revalidation_capabilities,
    standards_revalidation_owner,
    substantive_review_errors,
    task_phase_delivery_errors,
    undischarged_revalidation_hold,
    unsupported_reviewed_records,
    walk_revalidation_hold,
)

# The historical spelling of one promoted name.  `evidence_identity`
# offers `evidence_identity_errors` because `metadata_gate_runtime` needs
# the identical identity policy and may not read a private name; the
# underscored spelling is kept here, where every other historical
# spelling is kept, for the test that has always read it.
_evidence_identity_errors = evidence_identity_errors



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
INVALIDATION_FIELDS = frozenset((
    "transition_receipt", "invalidated_at", "reason",
    "delta_archive_path", "delta_sha256", "batch_receipts",
    "delta_gate_receipts", "revalidation_receipts",
))
# K00/12 gives the `standards-revalidation` Gate these lifecycle cells.  The
# producer's own admission and the recovery vocabulary that names a batch for
# it read the same constant, so the two cannot drift apart.
STANDARDS_REVALIDATION_STATES = ("queued", "open")
# A rollback taken after the delta was applied additionally names the
# application it undoes and the byte-exact Coverage restore that undid it.
# The three appear together or not at all: a pre-apply rollback never touched
# Coverage and carries none of them, and a partial set would assert a restore
# nobody can verify.
INVALIDATION_APPLIED_ROLLBACK_FIELDS = frozenset((
    "delta_apply_receipt", "coverage_restored_from",
    "coverage_restored_sha256",
))

HUB_EXIT_HINT = ("K13/10 admits a hub-editing batch only through an exclusive "
                 "or serial-integrator execution mode")


# K12/09 owns this closed set.  A close-gate receipt names one independently
# persisted pass receipt for every member; no omitted or ad-hoc eighth member
# can be hidden behind a generic "batch passed" assertion.
CLOSED_LIST_EVIDENCE_FIELDS = (
    "wiki_link_resolution",
    "structural_validity",
    "graph_and_duplicate_basenames",
    "coverage_file_count",
    "guidance_and_contract_continuity",
    "registered_residual_content",
    "controlled_vocabulary",
    "manifest_page_contract",
)
# Sealed close bundles are validated against the Closed List their producer
# era actually ran (K12/10 producer-era identity): a bundle produced before
# ``manifest_page_contract`` joined the list carries seven members forever,
# and re-judging it against the current list would retroactively invalidate
# every prior close on a checker upgrade.
LEGACY_CLOSED_LIST_VERSIONS = frozenset(("1.4.0",))
LEGACY_CLOSED_LIST_EVIDENCE_FIELDS = CLOSED_LIST_EVIDENCE_FIELDS[:-1]

SUPPORTED_APPLY_DELTA_TOOL_VERSIONS = frozenset((
    "1.4.0", "1.5.0", "1.6.0"))
# Batch-close has a finite historical protocol catalog because its 1.4 era
# sealed a different Closed List shape.  A current action still accepts only
# BATCH_CLOSE_TOOL_VERSION; this set is used only while replaying an already
# recorded closed edge.  Other historical receipts are judged through
# :func:`accounted_standards_versions` instead of an unbounded version list.
SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS = frozenset((
    BATCH_CLOSE_TOOL_VERSION, "1.11.0", "1.10.0", "1.9.0", "1.8.0", "1.7.0",
    "1.6.0", "1.5.0",
    *LEGACY_CLOSED_LIST_VERSIONS,
))
# A sealed close bundle keeps the child producer its batch-close era ran.
# Batch-close 1.7 is the first protocol that consumes corpus-plan 1.7; older
# supported bundles retain their 1.6 child identity during historical replay.
HISTORICAL_CORPUS_PLAN_TOOL_VERSIONS = {
    "1.11.0": "1.7.0",
    "1.10.0": "1.7.0",
    "1.9.0": "1.7.0",
    "1.8.0": "1.7.0",
    "1.7.0": "1.7.0",
    "1.6.0": "1.6.0",
    "1.5.0": "1.6.0",
    "1.4.0": "1.6.0",
}
CORPUS_PLAN_TRIGGERS = frozenset(("R13", "manifest"))
CORPUS_PLAN_PATH_SHA_FIELDS = (
    ("selected_profile_manifest", "selected_profile_manifest_sha256"),
    ("corpus_planning_slot_path", "corpus_planning_slot_sha256"),
    ("profile_scope_path", "profile_scope_sha256"),
    ("global_map_path", "global_map_sha256"),
    ("capability_matrix_path", "capability_matrix_sha256"),
    ("gap_register_path", "gap_register_sha256"),
)
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
LEGACY_PROPERTY_STATE_FIELD = "legacy_property_state"
LEGACY_PROPERTY_RECORD_FIELDS = frozenset(("status", "value"))
LEGACY_PROPERTY_STATUS = "legacy-unverified"
PROGRESS_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "task_id", "task_state", "required_queue_path",
    "queue_revision", "queue_state_revision", "required_queue_sha256",
    "initial_queue_receipt",
    "contract", "checkpoint", "terminal_audit", "maintenance_completion",
    "amendments",
    "standards_adoptions",
    "guidance_queue", "task_transition_receipts",
))
CONTRACT_FIELDS = frozenset((
    "contract_version", "completion_semantics", "objective", "exclusions",
    "scope_version",
    "concurrency_cap",
    "standards_version", "selected_profile_manifest", "selected_route_ids",
    "selected_card_paths", "selected_profile_route_ids",
    "selected_read_sets", "loaded_module_paths", "minimum_run_until",
    "checkpoint_at", "hard_stop_at", "completion_gate",
    "policy_exceptions", "amendment_authority",
))
# Optional so that contracts sealed before the field existed stay valid:
# requiring it would strand every live runtime behind a hand migration the
# anchor chain itself forbids (editing contract bytes outside a chained
# writer breaks the chain's binding to the current contract).  Absent means
# exactly what an explicit empty list means.
CONTRACT_OPTIONAL_FIELDS = frozenset((
    "policy_exceptions", "amendment_authority",
))
# Producer eras whose batch-close protocol carries the policy-exception
# disposition.  K12/10 producer-era identity cuts both ways: an older bundle
# is never re-judged against members its era lacked, and it is never allowed
# to carry evidence its era could not have produced.  A 1.7 bundle claiming a
# policy-exception disposition is a forgery, not history.
POLICY_EXCEPTION_DISPOSITION_VERSIONS = frozenset((
    "1.8.0", "1.9.0", "1.10.0", "1.11.0", "1.12.0",
))

COMPACT_CLOSE_EVIDENCE_VERSIONS = frozenset((
    "1.9.0", "1.10.0", "1.11.0", "1.12.0",
))
CANDIDATE_CONTINUATION_VERSIONS = frozenset((
    "1.10.0", "1.11.0", "1.12.0"))
CHECKPOINT_FIELDS = frozenset((
    "recorded_at", "summary", "task_state", "task_transition_receipt",
    "coverage_sha256", "required_queue_sha256", "queue_revision",
    "queue_state_revision",
))
TERMINAL_AUDIT_FIELDS = frozenset((
    "state", "terminal_proof_path", "terminal_proof_sha256",
    "terminal_proof_receipt", "queue_check_receipt",
))
TERMINAL_AUDIT_STATES = frozenset((
    "not-started", "ready", "passed", "invalidated", "not-applicable",
))
MAINTENANCE_COMPLETION_FIELDS = frozenset((
    "state", "completion_gate_receipt", "budget_manifest_receipt",
    "ledger_advance_receipt", "watermark_advance_receipt",
))
MAINTENANCE_COMPLETION_STATES = frozenset((
    "pending", "passed", "invalidated", "not-applicable",
))
COMPLETION_SEMANTICS = frozenset(("build", "maintenance"))
# Guidance records carry the kernel's own field names.  ``guidance_id`` and
# ``disposition`` are named by K13/06 Amendment Record; the accepted
# dispositions are the closed list K13/05 requires for every important
# guidance, and the accepted statuses are K13/06's recommended status values
# plus ``not-applicable``, the disposition-closing status both this checker
# and check_proof already treat as final.
GUIDANCE_FIELDS = frozenset(("guidance_id", "disposition", "status"))
GUIDANCE_DISPOSITIONS = frozenset((
    "interrupt-now", "apply-to-current-batch", "queue-next",
    "queue-by-dependency", "research-first", "deferred",
    "clarification-required", "superseded", "not-applicable",
))
GUIDANCE_STATUSES = frozenset((
    "received", "classified", "mapped", "in-progress", "verified",
    "clarification-required", "deferred", "superseded", "not-applicable",
))
AMENDMENT_COMMON_FIELDS = frozenset((
    "id", "date", "summary", "status", "writeback_done",
))
STANDARDS_REVALIDATION_CAPABILITY_PROTOCOL = "owner-projection-v1"

STANDARDS_ADOPTION_PLAN_FIELDS = frozenset((
    "schema_version", "adoption_id", "task_id", "task_state_before",
    "contract_version_before", "contract_version_after",
    "standards_version_before", "standards_version_after",
    "selected_profile_manifest_before", "selected_profile_manifest_after",
    "governance_revision_ref", "governance_revision_sha256",
    "standards_snapshot_sha256_after", "profile_snapshot_sha256_after",
    "profile_contract_fingerprint_after",
    "profile_load_inputs_sha256_after",
    "selected_route_ids_after", "selected_card_paths_after",
    "selected_profile_route_ids_after", "selected_read_sets_after",
    "loaded_module_paths_after", "queue_revision_before",
    "queue_revision_after", "queue_state_revision_before",
    "coverage_sha256_before", "required_queue_sha256_before",
    "progress_sha256_before", "changed_predicates", "invalidated_evidence",
    "invalidation_boundaries", "immediate_gate_reruns",
    "boundary_gate_reruns",
    # 1.5 producer: where the adopted revision came from.  Both explicit --
    # a nonempty pair naming the upstream source and its revision identifier
    # (for a git upstream, the commit hash), or both null, which DECLARES
    # that this adoption tracks no upstream.  Absent is not an answer.
    "upstream_source_ref", "upstream_revision_id",
    # 1.7 producer: instance state is no longer embedded in K00/03.
    "standards_state_sha256_before", "standards_effective_date_after",
))
STANDARDS_CHANGED_PREDICATE_FIELDS = frozenset((
    "predicate_id", "owner_path", "change_kind", "affected_gate_ids",
))
STANDARDS_INVALIDATED_EVIDENCE_FIELDS = frozenset((
    "receipt_id", "predicate_ids", "dimension_ids", "boundary_ids",
    "reason_code", "revalidation_scope_ids",
))
STANDARDS_INVALIDATION_BOUNDARY_FIELDS = frozenset((
    "boundary_id", "predicate_ids", "target_kind", "target_ids",
    "required_gate_ids",
))
STANDARDS_ADOPTION_RECORD_FIELDS = frozenset((
    "id", "adopted_at", "plan_path", "plan_sha256",
    "verification_receipt", "transaction_id", "task_state_before",
    "contract_version_before", "contract_version_after",
    "standards_version_before", "standards_version_after",
    "selected_profile_manifest_before", "selected_profile_manifest_after",
    "governance_revision_ref", "governance_revision_sha256",
    "standards_snapshot_sha256_after", "profile_snapshot_sha256_after",
    "profile_contract_fingerprint_after",
    "profile_load_inputs_sha256_after",
    "selected_route_ids_after", "selected_card_paths_after",
    "selected_profile_route_ids_after", "selected_read_sets_after",
    "loaded_module_paths_after", "queue_revision_before",
    "queue_revision_after", "queue_state_revision_before",
    "coverage_sha256_before", "required_queue_sha256_before",
    "progress_sha256_before", "after_coverage_sha256",
    "after_required_queue_sha256", "changed_predicate_ids",
    "invalidated_evidence_receipt_ids", "invalidation_boundary_ids",
    "immediate_gate_reruns", "immediate_gate_receipts",
    "boundary_gate_reruns",
    "upstream_source_ref", "upstream_revision_id",
    "standards_state_sha256_before", "standards_effective_date_after",
    "after_standards_state_sha256",
))


































DELTA_FIELDS = frozenset((
    "batch", "generated_at", "pages", "open_gaps_added",
    "open_gaps_closed", "next_batch_updates", "watermark_advance",
))
DELTA_CONTROL_FIELDS = frozenset((
    "coverage_disposition", "canonical_owner", "batch", "next_batch",
    "priority", "tier", "type", "prerequisites", "deferred_reason",
    "reentry_condition",
))
LIFECYCLE_EDGES = frozenset((
    ("queued", "open"),
    ("open", "merge-ready"),
    ("merge-ready", "closed"),
    ("merge-ready", "open"),
    ("queued", "cancelled"),
    ("open", "cancelled"),
))




















def _standards_adoption_shape_errors(progress):
    """Validate the closed append-only Progress adoption-record shape."""
    if "standards_adoptions" not in progress:
        return ["Progress standards_adoptions must be an explicit list"]
    records = progress.get("standards_adoptions")
    if not isinstance(records, list):
        return ["Progress standards_adoptions must be an explicit list"]
    errors = []
    seen_ids = set()
    seen_receipts = set()
    for index, record in enumerate(records):
        label = "Progress standards_adoptions[%d]" % index
        # The typed Profile contract became durable in adopt_standards 1.3,
        # and the root-owned profile-load inputs in 1.4.
        # Shape validation runs before the receipt catalog is available, so it
        # permits those two legacy omissions here. Historical replay below uses
        # the commit receipt's producer version to require each field from its
        # introduction onward and bind any legacy-present value across the
        # plan/record/receipt chain.
        errors.extend(_closed_mapping_errors(
            record, label, STANDARDS_ADOPTION_RECORD_FIELDS,
            optional_fields=("profile_contract_fingerprint_after",
                             "profile_load_inputs_sha256_after",
                             "upstream_source_ref",
                             "upstream_revision_id",
                             "standards_effective_date_after",
                             "standards_state_sha256_before",
                             "after_standards_state_sha256")))
        if not isinstance(record, dict):
            continue
        for field in (
                "id", "adopted_at", "plan_path", "plan_sha256",
                "verification_receipt", "transaction_id",
                "task_state_before", "standards_version_before",
                "contract_version_before", "contract_version_after",
                "standards_version_after", "selected_profile_manifest_before",
                "selected_profile_manifest_after", "coverage_sha256_before",
                "required_queue_sha256_before", "progress_sha256_before",
                "after_coverage_sha256", "after_required_queue_sha256"):
            if not _nonempty_string(record.get(field)):
                errors.append("%s %s must be a non-empty string" %
                              (label, field))
        if not _valid_timestamp(record.get("adopted_at")):
            errors.append("%s adopted_at must be timezone-aware RFC 3339" %
                          label)
        for field in (
                "plan_sha256", "coverage_sha256_before",
                "required_queue_sha256_before", "progress_sha256_before",
                "after_coverage_sha256", "after_required_queue_sha256"):
            if not SHA256_RE.fullmatch(str(record.get(field, ""))):
                errors.append("%s %s is not sha256:<64 lowercase hex>" %
                              (label, field))
        for field in ("queue_revision_before", "queue_revision_after",
                      "queue_state_revision_before"):
            value = record.get(field)
            if (not isinstance(value, int) or isinstance(value, bool) or
                    value < (1 if field.startswith("queue_revision") else 0)):
                errors.append("%s %s has an invalid revision" % (label, field))
        if (isinstance(record.get("queue_revision_before"), int) and
                isinstance(record.get("queue_revision_after"), int) and
                record["queue_revision_after"] !=
                record["queue_revision_before"] + 1):
            errors.append("%s queue_revision must increment exactly once" %
                          label)
        for field in (
                "selected_route_ids_after", "selected_card_paths_after",
                "selected_profile_route_ids_after", "selected_read_sets_after",
                "loaded_module_paths_after", "changed_predicate_ids",
                "invalidated_evidence_receipt_ids", "invalidation_boundary_ids",
                "immediate_gate_reruns", "immediate_gate_receipts",
                "boundary_gate_reruns"):
            errors.extend(_explicit_string_list_errors(
                record.get(field), "%s %s" % (label, field)))
            value = record.get(field)
            if isinstance(value, list) and value != sorted(value):
                errors.append("%s %s must be sorted" % (label, field))
        adoption_id = record.get("id")
        if _nonempty_string(adoption_id):
            if adoption_id in seen_ids:
                errors.append("Progress standards_adoptions repeats id %s" %
                              adoption_id)
            seen_ids.add(adoption_id)
        receipt_id = record.get("verification_receipt")
        if _nonempty_string(receipt_id):
            if receipt_id in seen_receipts:
                errors.append(
                    "Progress standards_adoptions repeats verification receipt %s" %
                    receipt_id)
            seen_receipts.add(receipt_id)
    return errors








def _progress_shape_errors(progress):
    """Close task-control records so truncation cannot mean 'nothing pending'."""
    errors = []
    contract = progress.get("contract")
    errors.extend(_closed_mapping_errors(contract, "Progress contract",
                                         CONTRACT_FIELDS,
                                         CONTRACT_OPTIONAL_FIELDS))
    if isinstance(contract, dict) and "policy_exceptions" in contract:
        errors.extend(_policy_exception_errors(
            contract.get("policy_exceptions"),
            "Progress contract.policy_exceptions"))
    if isinstance(contract, dict) and "amendment_authority" in contract:
        errors.extend(amendment_policy.amendment_authority_errors(
            contract.get("amendment_authority"),
            "Progress contract.amendment_authority"))
    if isinstance(contract, dict):
        for field in ("contract_version", "objective", "scope_version",
                      "standards_version",
                      "selected_profile_manifest", "completion_gate"):
            if not _nonempty_string(contract.get(field)):
                errors.append("Progress contract.%s must be a non-empty string" %
                              field)
        if contract.get("completion_semantics") not in COMPLETION_SEMANTICS:
            errors.append(
                "Progress contract.completion_semantics must be build or maintenance"
            )
        cap = contract.get("concurrency_cap")
        if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
            errors.append("Progress contract.concurrency_cap must be a positive integer")
        for field in ("selected_route_ids", "selected_card_paths",
                      "selected_profile_route_ids", "selected_read_sets",
                      "loaded_module_paths"):
            errors.extend(_explicit_string_list_errors(
                contract.get(field), "Progress contract.%s" % field))
        errors.extend(_explicit_string_list_errors(
            contract.get("exclusions"), "Progress contract.exclusions"))
        for field in ("minimum_run_until", "checkpoint_at", "hard_stop_at"):
            value = contract.get(field)
            if not isinstance(value, str) or (value and not _valid_timestamp(value)):
                errors.append("Progress contract.%s must be empty or an RFC 3339 timestamp" %
                              field)

    checkpoint = progress.get("checkpoint")
    errors.extend(_closed_mapping_errors(checkpoint, "Progress checkpoint",
                                         CHECKPOINT_FIELDS))

    terminal = progress.get("terminal_audit")
    errors.extend(_closed_mapping_errors(terminal, "Progress terminal_audit",
                                         TERMINAL_AUDIT_FIELDS))
    if isinstance(terminal, dict):
        if terminal.get("state") not in TERMINAL_AUDIT_STATES:
            errors.append("Progress terminal_audit.state has invalid value %r" %
                          terminal.get("state"))
        for field in ("terminal_proof_path", "terminal_proof_sha256",
                      "terminal_proof_receipt", "queue_check_receipt"):
            value = terminal.get(field)
            if value is not None and not _nonempty_string(value):
                errors.append("Progress terminal_audit.%s must be null or a non-empty string" %
                              field)
        proof_sha = terminal.get("terminal_proof_sha256")
        if proof_sha is not None and not SHA256_RE.fullmatch(proof_sha):
            errors.append("Progress terminal_audit.terminal_proof_sha256 is invalid")

    maintenance = progress.get("maintenance_completion")
    errors.extend(_closed_mapping_errors(
        maintenance, "Progress maintenance_completion",
        MAINTENANCE_COMPLETION_FIELDS,
    ))
    if isinstance(maintenance, dict):
        if maintenance.get("state") not in MAINTENANCE_COMPLETION_STATES:
            errors.append(
                "Progress maintenance_completion.state has invalid value %r" %
                maintenance.get("state")
            )
        for field in (
                "completion_gate_receipt", "budget_manifest_receipt",
                "ledger_advance_receipt", "watermark_advance_receipt"):
            value = maintenance.get(field)
            if value is not None and not _nonempty_string(value):
                errors.append(
                    "Progress maintenance_completion.%s must be null or a "
                    "non-empty string" % field
                )

    completion_semantics = (contract.get("completion_semantics")
                            if isinstance(contract, dict) else None)
    if completion_semantics == "build" and isinstance(maintenance, dict):
        if maintenance.get("state") != "not-applicable":
            errors.append(
                "build completion semantics requires maintenance_completion "
                "state not-applicable"
            )
        for field in MAINTENANCE_COMPLETION_FIELDS - {"state"}:
            if maintenance.get(field) is not None:
                errors.append(
                    "build completion semantics requires "
                    "maintenance_completion.%s=null" % field
                )
    if completion_semantics == "maintenance" and isinstance(terminal, dict):
        if terminal.get("state") != "not-applicable":
            errors.append(
                "maintenance completion semantics requires terminal_audit "
                "state not-applicable"
            )
        for field in TERMINAL_AUDIT_FIELDS - {"state"}:
            if terminal.get(field) is not None:
                errors.append(
                    "maintenance completion semantics requires "
                    "terminal_audit.%s=null" % field
                )

    guidance = progress.get("guidance_queue")
    if not isinstance(guidance, list):
        errors.append("Progress guidance_queue must be an explicit list")
    else:
        seen = set()
        for index, entry in enumerate(guidance):
            label = "Progress guidance_queue[%d]" % index
            errors.extend(_closed_mapping_errors(entry, label, GUIDANCE_FIELDS))
            if not isinstance(entry, dict):
                continue
            for field in GUIDANCE_FIELDS:
                if not _nonempty_string(entry.get(field)):
                    errors.append("%s %s must be a non-empty string" %
                                  (label, field))
            disposition = entry.get("disposition")
            if (_nonempty_string(disposition) and
                    disposition not in GUIDANCE_DISPOSITIONS):
                errors.append("%s disposition has invalid value %r" %
                              (label, disposition))
            status = entry.get("status")
            if _nonempty_string(status) and status not in GUIDANCE_STATUSES:
                errors.append("%s status has invalid value %r" %
                              (label, status))
            entry_id = entry.get("guidance_id")
            if _nonempty_string(entry_id):
                if entry_id in seen:
                    errors.append(
                        "Progress guidance_queue repeats guidance_id %s" %
                        entry_id)
                seen.add(entry_id)

    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        errors.append("Progress amendments must be an explicit list")
    else:
        seen = set()
        for index, entry in enumerate(amendments):
            label = "Progress amendments[%d]" % index
            if not isinstance(entry, dict):
                errors.append("%s must be a mapping" % label)
                continue
            missing = sorted(AMENDMENT_COMMON_FIELDS - set(entry))
            if missing:
                errors.append("%s misses explicit field(s): %s" %
                              (label, ", ".join(missing)))
            for field in ("id", "date", "summary", "status"):
                if not _nonempty_string(entry.get(field)):
                    errors.append("%s %s must be a non-empty string" %
                                  (label, field))
            if not isinstance(entry.get("writeback_done"), bool):
                errors.append("%s writeback_done must be boolean" % label)
            entry_id = entry.get("id")
            if _nonempty_string(entry_id):
                if entry_id in seen:
                    errors.append("Progress amendments repeats id %s" % entry_id)
                seen.add(entry_id)
    errors.extend(_standards_adoption_shape_errors(progress))
    return errors














































def standards_revalidation_requirements(root, progress, capabilities=None,
                                        catalog=None):
    """Return immutable per-batch boundary bindings from all adoption plans."""
    by_batch = {}
    if capabilities is None:
        gate_registry, _gate_errors = standards_gate_registry(root)
        capabilities, _capability_errors = \
            standards_revalidation_capabilities(root, gate_registry)
    records = progress.get("standards_adoptions")
    if not isinstance(records, list):
        return by_batch
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            path = kblib.managed_repository_path(
                root, record.get("plan_path"), STANDARDS_ADOPTION_PLAN_PREFIX,
                suffixes=(".yaml",), must_exist=True)
            plan = kblib.load_yaml_file(path)
        except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError):
            continue
        producer_tool_version = None
        receipt_id = record.get("verification_receipt")
        if catalog is not None and _nonempty_string(receipt_id):
            resolve = getattr(catalog, "resolve", None)
            if not callable(resolve):
                resolve = catalog.get
            entry = resolve(receipt_id)
            receipt = entry[1] if entry is not None else None
            if isinstance(receipt, dict) and \
                    receipt.get("tool") == STANDARDS_ADOPTION_TOOL:
                producer_tool_version = receipt.get("tool_version")
        owner_projection_era = \
            _standards_adoption_owner_projection_required(
                producer_tool_version)
        # Pre-1.6 plans stored raw leaf Gates, so their only safe forward
        # bridge is the current closed mapping.  A 1.6+ plan stores owner Gates
        # in required_gate_ids; once its producer is historical those recorded
        # owners, not a future capability table, remain authoritative.  The
        # running producer may still materialize leaf-to-owner audit rows from
        # the same table it just admitted.
        use_live_leaf_projection = (not owner_projection_era or
                                    producer_tool_version ==
                                    STANDARDS_ADOPTION_TOOL_VERSION)
        boundaries = {
            row.get("boundary_id"): row
            for row in plan.get("invalidation_boundaries", [])
            if isinstance(row, dict) and
            _nonempty_string(row.get("boundary_id"))
        }
        affected_by_predicate = {
            row.get("predicate_id"): [
                gate_id for gate_id in row.get("affected_gate_ids") or []
                if _nonempty_string(gate_id)
            ]
            for row in plan.get("changed_predicates", [])
            if isinstance(row, dict) and
            _nonempty_string(row.get("predicate_id"))
        }
        invalidated_by_boundary = {}
        for invalidated in plan.get("invalidated_evidence", []):
            if not isinstance(invalidated, dict):
                continue
            for boundary_id in invalidated.get("boundary_ids") or []:
                invalidated_by_boundary.setdefault(boundary_id, []).append(
                    invalidated)
        target_batches = {}
        for boundary_id, boundary in boundaries.items():
            if boundary.get("target_kind") == "batch":
                target_batches.setdefault(boundary_id, set()).update(
                    boundary.get("target_ids") or [])
            for invalidated in invalidated_by_boundary.get(boundary_id, []):
                target_batches.setdefault(boundary_id, set()).update(
                    invalidated.get("revalidation_scope_ids") or [])
        for boundary_id, batch_ids in target_batches.items():
            boundary = boundaries[boundary_id]
            for batch_id in batch_ids:
                if not _nonempty_string(batch_id):
                    continue
                relevant_invalidated = sorted({
                    invalidated.get("receipt_id")
                    for invalidated in invalidated_by_boundary.get(
                        boundary_id, [])
                    if _nonempty_string(invalidated.get("receipt_id")) and
                    (batch_id in (
                        invalidated.get("revalidation_scope_ids") or []) or
                     boundary.get("target_kind") == "batch")
                })
                # The dimensions this boundary put back in question.  They come
                # from the plan's own `dimension_ids`, not from reading the
                # superseded receipts: what has to be re-established is what
                # the adoption declared it invalidated.
                relevant_dimensions = sorted({
                    dimension
                    for invalidated in invalidated_by_boundary.get(
                        boundary_id, [])
                    if _nonempty_string(invalidated.get("receipt_id")) and
                    (batch_id in (
                        invalidated.get("revalidation_scope_ids") or []) or
                     boundary.get("target_kind") == "batch")
                    for dimension in invalidated.get("dimension_ids") or []
                    if _nonempty_string(dimension)
                })
                plan_required_gate_ids = [
                    gate_id for gate_id in
                    boundary.get("required_gate_ids") or []
                    if _nonempty_string(gate_id)
                ]
                affected_gate_ids = sorted({
                    gate_id
                    for predicate_id in boundary.get("predicate_ids") or []
                    for gate_id in affected_by_predicate.get(predicate_id, [])
                })
                binding_specs = []
                represented_required = set()

                def add_binding_spec(affected_gate_id):
                    mapped_owner = affected_gate_id
                    owner_claim_edge = None
                    mapping_error = None
                    try:
                        projected = standards_revalidation_owner(
                            affected_gate_id, capabilities or {})
                        if projected is None:
                            # Advisory observations are intentionally absent
                            # from the runtime boundary owner closure.
                            return
                        mapped_owner = projected
                    except ValueError as exc:
                        mapping_error = str(exc)
                    if mapped_owner in plan_required_gate_ids:
                        required_gate_id = mapped_owner
                    elif affected_gate_id in plan_required_gate_ids:
                        # Producer-era bridge: an old plan stores the raw leaf
                        # in required_gate_ids.  Keep that immutable key while
                        # moving its live claim to the current composite owner.
                        required_gate_id = affected_gate_id
                    else:
                        required_gate_id = mapped_owner
                        mapping_error = mapping_error or (
                            "Standards revalidation owner %s for affected "
                            "Gate %s is absent from boundary %s" % (
                                mapped_owner, affected_gate_id, boundary_id))
                    owner_capability = (capabilities or {}).get(mapped_owner)
                    if isinstance(owner_capability, dict):
                        owner_claim_edge = owner_capability.get("claim_edge")
                        if owner_capability.get("role") == "special-owner":
                            # Profile admission is completed against the
                            # writable after-image by the adoption writer.  It
                            # never becomes a post-admission batch obligation.
                            return
                    represented_required.add(required_gate_id)
                    binding_specs.append((
                        affected_gate_id, required_gate_id, mapped_owner,
                        owner_claim_edge, mapping_error))

                for gate_id in affected_gate_ids:
                    if use_live_leaf_projection:
                        add_binding_spec(gate_id)
                # A malformed or historical boundary may name a requirement
                # not reachable from its changed-predicate rows.  Preserve it
                # as an explicit binding so the aggregate cannot silently
                # shrink the recorded obligation.
                for gate_id in plan_required_gate_ids:
                    if gate_id not in represented_required:
                        add_binding_spec(gate_id)

                for (affected_gate_id, required_gate_id, mapped_owner,
                     owner_claim_edge, mapping_error) in binding_specs:
                    binding = {
                        "adoption_id": plan.get("adoption_id"),
                        "plan_sha256": record.get("plan_sha256"),
                        "adopted_at": record.get("adopted_at"),
                        "boundary_id": boundary_id,
                        "predicate_ids": sorted(
                            boundary.get("predicate_ids") or []),
                        "affected_gate_id": affected_gate_id,
                        "affected_gate_ids": affected_gate_ids,
                        "required_gate_id": required_gate_id,
                        "mapped_owner_gate_id": mapped_owner,
                        "owner_claim_edge": owner_claim_edge,
                        "mapping_protocol_version":
                            STANDARDS_REVALIDATION_CAPABILITY_PROTOCOL,
                        "mapping_error": mapping_error,
                        "required_dimension_ids": relevant_dimensions,
                        "superseded_invalidated_receipt_ids":
                            relevant_invalidated,
                    }
                    by_batch.setdefault(batch_id, []).append(binding)
    for batch_id in by_batch:
        by_batch[batch_id] = sorted(
            by_batch[batch_id], key=lambda row: (
                row.get("adoption_id", ""), row.get("boundary_id", ""),
                row.get("required_gate_id", ""),
                row.get("affected_gate_id", "")))
    return by_batch


def standards_revalidation_producer_eligibility(result, batch_id):
    """Why ``--require-revalidation <batch_id>`` would refuse, or ``None``.

    One predicate with two callers: this producer's own admission, and the
    resume vocabulary that names a batch for it.  They were separate before,
    and the recovery action outlived what the producer would accept -- a
    closed batch was named for an aggregate the tool refuses outright, so
    the recommendation could never be followed and nothing behind it was
    ever reported.  Sharing the predicate is what makes "the tool would run
    this" a checkable claim rather than a parallel guess.
    """
    if (result.get("progress") or {}).get("task_state") != "active":
        return ("Standards revalidation requires task_state=active; "
                "resume the recorded task before producing the "
                "state-bound aggregate")
    item = (result.get("items_by_id") or {}).get(batch_id)
    if item is None:
        return "requested batch %s does not exist" % batch_id
    if item.get("state") not in STANDARDS_REVALIDATION_STATES:
        return ("Standards revalidation batch %s is %s, expected "
                "queued or open" % (batch_id, item.get("state")))
    if item.get("state") == "open" and \
            item.get("hold_state") != "revalidation-required":
        return ("open Standards revalidation batch must have "
                "hold_state=revalidation-required")
    return None


def _unresolvable_consumed_aggregate_errors(items_by_id, catalog):
    """Fail closed when a recorded consumption's aggregate resolves nowhere.

    The replay below reads each consumed aggregate's body.  When the body
    is neither hot nor reachable through the sealed branch, the replay has
    no way to know which bindings that transition discharged -- and the
    quiet answer, dropping the transition and reporting its bindings as
    outstanding again, is indistinguishable from a batch that never
    revalidated at all.  It also cannot be acted on: the batch that
    recorded the consumption is closed by then, and
    ``--require-revalidation`` refuses a closed batch (K00/12 gives
    `standards-revalidation` the lifecycle cells `queued, open`).  So the
    run says the evidence became unreachable, rather than silently
    rewriting a discharged obligation into a permanent one.
    """
    errors = []
    resolve = getattr(catalog, "resolve", None)
    if not callable(resolve):
        resolve = catalog.get
    for batch_id in sorted(items_by_id):
        item = items_by_id[batch_id]
        if not isinstance(item, dict):
            continue
        for transition in _ordered_item_transitions(item, catalog):
            receipt_id = transition.get("standards_revalidation_receipt")
            if not _nonempty_string(receipt_id) or \
                    resolve(receipt_id) is not None:
                continue
            errors.append(
                "batch %s transition %s consumed Standards revalidation "
                "aggregate %s, which resolves neither in the hot register "
                "nor through the K12/07 cold chain; a recorded consumption "
                "whose evidence became unreachable is not a revalidation "
                "that never happened" %
                (batch_id, transition.get("receipt_id"), receipt_id))
    return errors


def _consumed_standards_revalidation_keys(item, catalog):
    consumed = set()
    transitions = _ordered_item_transitions(item, catalog)
    if not transitions:
        return consumed
    # Sealing must not un-replay a consumption a Queue transition recorded.
    # This replay reads the aggregate's body, so it takes the K12/07 sealed
    # branch (`_Catalog.resolve`) rather than the hot map alone; a reduced
    # test context that passes a plain dict keeps the historical behavior.
    resolve = getattr(catalog, "resolve", None)
    if not callable(resolve):
        resolve = catalog.get
    # The `evidence_receipt` fallback applies to a transition the replayed
    # hold machine recognizes as a discharge, not to the adjacent
    # `revalidation-required -> none` edge alone.
    discharges = {transition.get("receipt_id")
                  for transition in walk_revalidation_hold(transitions)[1]}
    for transition in transitions:
        receipt_id = transition.get("standards_revalidation_receipt")
        if not _nonempty_string(receipt_id) and (
                transition.get("before_state") == transition.get("after_state")
                and transition.get("receipt_id") in discharges):
            receipt_id = transition.get("evidence_receipt")
        receipt_entry = resolve(receipt_id) if _nonempty_string(
            receipt_id) else None
        receipt = receipt_entry[1] if receipt_entry is not None else None
        # Producer-era rule: a consumed aggregate is a historical fact a Queue
        # transition already validated at its own producer era.  The writer
        # that consumes a NEW aggregate still requires the current producer
        # (standards_revalidation_receipt_errors); the replay here accepts the
        # recorded era's version, because pinning it to the running
        # TOOL_VERSION orphaned every consumed aggregate at the next
        # registered producer bump and left the runtime permanently
        # inconsistent with no sanctioned repair path.  An adoption that
        # really retracts one still names it in `invalidated_evidence`.
        if not isinstance(receipt, dict) or receipt.get("result") != "pass" or \
                receipt.get("invalidated_by") is not None or \
                receipt.get("tool") != TOOL or \
                not _nonempty_string(receipt.get("tool_version")) or \
                receipt.get("check") != "required_queue" or \
                receipt.get("queue_check_mode") != \
                "require-revalidation:%s" % item.get("id") or \
                receipt.get("batch_id") != item.get("id"):
            continue
        for binding in receipt.get("revalidation_bindings") or []:
            if not isinstance(binding, dict):
                continue
            key = (binding.get("adoption_id"), binding.get("boundary_id"),
                   binding.get("required_gate_id"))
            if all(_nonempty_string(value) for value in key):
                consumed.add(key)
    return consumed


def outstanding_standards_revalidation(result, batch_id):
    """Return plan bindings not yet consumed by a Queue transition."""
    requirements = result.get("_standards_revalidation_requirements")
    if not isinstance(requirements, dict):
        # Public helpers also accept deliberately reduced/test contexts.  Such
        # a caller has no validation-scoped derivation to reuse, so preserve
        # the historical standalone behavior instead of requiring a private
        # field.  ``validate_runtime`` always supplies the derived map once.
        requirements = standards_revalidation_requirements(
            result.get("root"), result.get("progress") or {},
            catalog=historical_receipt_catalog(result))
    raw = requirements.get(batch_id, [])
    item = (result.get("items_by_id") or {}).get(batch_id) or {}
    # Consumption is replayed from the immutable historical catalog: the
    # era-filtered current catalog drops receipts whose producer version was
    # since bumped, and a recorded consumption must not disappear with them.
    consumed = _consumed_standards_revalidation_keys(
        item, historical_receipt_catalog(result))
    return [binding for binding in raw if (
        binding.get("adoption_id"), binding.get("boundary_id"),
        binding.get("required_gate_id")) not in consumed]


def current_attempt_evidence_barrier(result, batch_id):
    """Return why new merge/apply/close work is unsafe after adoption."""
    item = (result.get("items_by_id") or {}).get(batch_id)
    if not isinstance(item, dict) or item.get("state") in TERMINAL_STATES:
        return None
    outstanding = outstanding_standards_revalidation(result, batch_id)
    invalidated = set(
        result.get("invalidated_evidence_receipt_ids") or [])
    consumers = invalidated_receipt_consumers(
        result.get("root"), result.get("queue") or {},
        historical_receipt_catalog(result))
    # Activation/confirmation and pre-adoption hold-clear evidence remain
    # immutable history after the dedicated Standards-revalidation aggregate
    # has been consumed.  They are still consumers for adoption-scope
    # inference, but they must not permanently poison a later attempt.  Only
    # execution evidence that would be newly merged/applied/closed is a live
    # barrier here.
    historical_sources = {
        "Queue.activation_receipt", "Queue.confirmation_receipt",
        "Queue.current-transition-evidence",
    }
    referenced_invalidated = sorted(
        receipt_id for receipt_id in invalidated
        if any(row.get("batch_id") == batch_id and
               row.get("source") not in historical_sources
               for row in consumers.get(receipt_id, [])))
    if item.get("state") == "open" and item.get("hold_state") == \
            "revalidation-required":
        return None
    if outstanding:
        return ("batch %s has outstanding Standards revalidation bindings: %s" %
                (batch_id, ", ".join("%s/%s/%s" % (
                    row.get("adoption_id"), row.get("boundary_id"),
                    row.get("required_gate_id")) for row in outstanding)))
    if item.get("state") == "merge-ready" and referenced_invalidated:
        return ("merge-ready batch %s current attempt references invalidated "
                "receipt(s): %s" %
                (batch_id, ", ".join(referenced_invalidated)))
    return None


def _parse_boundary_gate_arguments(values):
    mapping = {}
    errors = []
    for value in values or []:
        if not isinstance(value, str) or "=" not in value:
            errors.append("--boundary-gate-receipt must be GATE_ID=RECEIPT_ID")
            continue
        gate_id, receipt_id = value.split("=", 1)
        gate_id = gate_id.strip()
        receipt_id = receipt_id.strip()
        if not _nonempty_string(gate_id) or not _nonempty_string(receipt_id):
            errors.append("--boundary-gate-receipt has an empty gate/receipt ID")
        elif gate_id in mapping:
            errors.append("--boundary-gate-receipt repeats Gate ID %s" % gate_id)
        else:
            mapping[gate_id] = receipt_id
    return mapping, errors


def standards_revalidation_context(result, batch_id, gate_receipts):
    """Validate boundary receipts and return the aggregate receipt payload.

    A boundary's required gates are claimed at the transition each one belongs
    to, so they are partitioned against the target batch's current lifecycle
    position before any receipt is demanded.  Only the **due** set -- what that
    position can still produce -- is required here; the other two are recorded
    on the aggregate.  Requiring the whole union regardless of position made
    some boundaries impossible to discharge: an `open` batch can reach neither
    `--require-ready` nor `check_batch_close`, so a boundary naming
    `required-queue-admission` or `batch-close` against one deadlocked its
    hold with no sanctioned way out.
    """
    errors = []
    outstanding = outstanding_standards_revalidation(result, batch_id)
    if not outstanding:
        return None, ["batch %s has no outstanding Standards revalidation" %
                      batch_id]
    required_gate_ids = sorted({
        row.get("required_gate_id") for row in outstanding
        if _nonempty_string(row.get("required_gate_id"))
    })
    registry, registry_errors = standards_gate_registry(result.get("root"))
    errors.extend(registry_errors)
    capabilities, capability_errors = standards_revalidation_capabilities(
        result.get("root"), registry)
    errors.extend(capability_errors)
    for row in outstanding:
        if _nonempty_string(row.get("mapping_error")):
            errors.append(row["mapping_error"])
    mapped_owner_gate_ids = sorted({
        row.get("mapped_owner_gate_id") for row in outstanding
        if _nonempty_string(row.get("mapped_owner_gate_id"))
    })
    item = (result.get("items_by_id") or {}).get(batch_id) or {}
    due_gate_ids, deferred_gate_ids, unrepeatable_gate_ids = \
        partition_revalidation_owner_claims(
            mapped_owner_gate_ids, item.get("state"), registry, capabilities)
    if sorted(gate_receipts) != due_gate_ids:
        errors.append("boundary gate receipt IDs must be exactly %r" %
                      due_gate_ids)
    catalog = current_receipt_catalog(result)
    queue = result.get("queue") or {}
    resolved = {}
    for gate_id in due_gate_ids:
        receipt_id = gate_receipts.get(gate_id)
        entry = catalog.get(receipt_id) if _nonempty_string(receipt_id) else None
        if entry is None:
            errors.append("Gate ID %s references missing current receipt %r" %
                          (gate_id, receipt_id))
            continue
        receipt = entry[1]
        # One Gate ID may cover several receipt dimensions, so the Gate ID
        # alone does not say which evidence the boundary is owed.  Narrow to
        # the dimensions the plan declared invalidated for this Gate, and
        # refuse a boundary whose declaration and registry cannot both hold
        # rather than falling back to the unnarrowed match.
        registered = registered_gate_dimensions(gate_id, registry)
        required_dimension = None
        if registered:
            declared = {
                dimension for row in outstanding
                if row.get("mapped_owner_gate_id") == gate_id
                for dimension in row.get("required_dimension_ids") or []
            }
            admissible = sorted(declared & registered)
            if declared and not admissible:
                errors.append(
                    "Gate ID %s is required for dimension(s) %s, which K00/12 "
                    "does not register for it" % (
                        gate_id, ", ".join(sorted(declared))))
                continue
            if len(admissible) == 1:
                required_dimension = admissible[0]
            elif admissible and receipt.get("dimension") not in admissible:
                errors.append(
                    "Gate ID %s receipt %s files under %r; this boundary is "
                    "owed one of %s" % (
                        gate_id, receipt_id, receipt.get("dimension"),
                        ", ".join(admissible)))
        if not receipt_matches_gate_id(receipt, gate_id, registry,
                                       dimension=required_dimension):
            errors.append("receipt %s does not match registered Gate ID %s" %
                          (receipt_id, gate_id))
        for field, expected in (
                ("result", "pass"), ("invalidated_by", None),
                ("task_id", queue.get("task_id")),
                ("standards_version", queue.get("standards_version")),
                ("selected_profile_manifest",
                 queue.get("selected_profile_manifest"))):
            if receipt.get(field) != expected:
                errors.append("Gate ID %s receipt %s has %s=%r, expected %r" %
                              (gate_id, receipt_id, field,
                               receipt.get(field), expected))
        receipt_time = _timestamp_value(receipt.get("checked_at"))
        relevant_times = [_timestamp_value(row.get("adopted_at"))
                          for row in outstanding
                          if row.get("mapped_owner_gate_id") == gate_id]
        if receipt_time is None or any(
                value is None or receipt_time < value for value in relevant_times):
            errors.append("Gate ID %s receipt %s predates its adoption" %
                          (gate_id, receipt_id))
        resolved[gate_id] = receipt_id
    bindings = []
    for row in outstanding:
        owner_gate_id = row.get("mapped_owner_gate_id")
        if owner_gate_id in due_gate_ids:
            disposition = "satisfied-immediate"
        elif owner_gate_id in deferred_gate_ids:
            disposition = "deferred-to-native-transition"
        else:
            disposition = "unrepeatable-passed"
        binding = {
            "adoption_id": row.get("adoption_id"),
            "plan_sha256": row.get("plan_sha256"),
            "boundary_id": row.get("boundary_id"),
            "predicate_ids": row.get("predicate_ids"),
            "affected_gate_id": row.get("affected_gate_id"),
            "required_gate_id": row.get("required_gate_id"),
            "mapped_owner_gate_id": owner_gate_id,
            "owner_claim_edge": row.get("owner_claim_edge"),
            "mapping_protocol_version": row.get(
                "mapping_protocol_version"),
            "claim_disposition": disposition,
            "gate_receipt_id": resolved.get(owner_gate_id),
            "superseded_invalidated_receipt_ids":
                row.get("superseded_invalidated_receipt_ids"),
        }
        bindings.append(binding)
    immediate_gate_ids = sorted(
        gate_id for gate_id in mapped_owner_gate_ids
        if (capabilities.get(gate_id) or {}).get("role") == "immediate-owner")
    native_owner_gate_ids = sorted(
        gate_id for gate_id in mapped_owner_gate_ids
        if (capabilities.get(gate_id) or {}).get("role") == "native-owner")
    deferred_native_owner_gate_ids = sorted(
        set(native_owner_gate_ids) & set(deferred_gate_ids))
    context = {
        "gate_id": "standards-revalidation",
        "batch_id": batch_id,
        "standards_adoption_ids": sorted({
            row.get("adoption_id") for row in outstanding
            if _nonempty_string(row.get("adoption_id"))}),
        "standards_adoption_plan_sha256s": sorted({
            row.get("plan_sha256") for row in outstanding
            if _nonempty_string(row.get("plan_sha256"))}),
        "invalidation_boundary_ids": sorted({
            row.get("boundary_id") for row in outstanding
            if _nonempty_string(row.get("boundary_id"))}),
        "required_gate_ids": required_gate_ids,
        "mapped_owner_gate_ids": mapped_owner_gate_ids,
        "immediate_gate_ids": immediate_gate_ids,
        "native_owner_gate_ids": native_owner_gate_ids,
        "deferred_native_owner_gate_ids":
            deferred_native_owner_gate_ids,
        "mapping_protocol_version":
            STANDARDS_REVALIDATION_CAPABILITY_PROTOCOL,
        "target_batch_state": item.get("state"),
        # The partition of `required_gate_ids` this aggregate was made under.
        # Each Gate ID appears in exactly one of the three, and the three
        # together are `required_gate_ids`: the aggregate says which gates it
        # discharged, which it handed to a later transition, and which it
        # recorded as beyond remaking.
        "due_gate_ids": due_gate_ids,
        "deferred_to_later_transition_gate_ids": deferred_gate_ids,
        "unrepeatable_passed_gate_ids": unrepeatable_gate_ids,
        "boundary_gate_receipts": [
            {"required_gate_id": gate_id,
             "receipt_id": resolved.get(gate_id)}
            for gate_id in due_gate_ids
        ],
        "revalidated_invalidated_receipt_ids": sorted({
            receipt_id for row in outstanding
            for receipt_id in row.get(
                "superseded_invalidated_receipt_ids") or []
        }),
        "revalidation_bindings": bindings,
        "repository_snapshot_sha256": kblib.repository_snapshot_sha256(
            result.get("root")),
    }
    return context, errors


def standards_revalidation_receipt_errors(result, batch_id, receipt_id):
    """Validate one current aggregate before activation or hold clear."""
    errors = []
    catalog = current_receipt_catalog(result)
    receipt = _require_receipt(
        catalog, receipt_id, "%s Standards revalidation" % batch_id, errors,
        expected={
            "tool": TOOL, "tool_version": TOOL_VERSION,
            "gate_id": "standards-revalidation",
            "check": "required_queue", "target": QUEUE_PATH,
            "queue_check_mode": "require-revalidation:%s" % batch_id,
            "task_id": (result.get("queue") or {}).get("task_id"),
            "batch_id": batch_id,
            "queue_revision": (result.get("queue") or {}).get(
                "queue_revision"),
            "queue_state_revision": (result.get("queue") or {}).get(
                "state_revision"),
            "required_queue_sha256": result.get("queue_sha256"),
            "coverage_ledger_sha256": result.get("coverage_sha256"),
            "progress_ledger_sha256": result.get("progress_sha256"),
            "standards_version": (result.get("queue") or {}).get(
                "standards_version"),
            "selected_profile_manifest": (result.get("queue") or {}).get(
                "selected_profile_manifest"),
        })
    if receipt is None:
        return errors
    supplied = {}
    rows = receipt.get("boundary_gate_receipts")
    if not isinstance(rows, list):
        errors.append("Standards revalidation receipt lacks boundary_gate_receipts")
    else:
        for row in rows:
            if not isinstance(row, dict):
                errors.append("boundary_gate_receipts contains a non-mapping")
                continue
            gate_id = row.get("required_gate_id")
            if gate_id in supplied:
                errors.append("boundary_gate_receipts repeats %s" % gate_id)
            supplied[gate_id] = row.get("receipt_id")
    expected, context_errors = standards_revalidation_context(
        result, batch_id, supplied)
    errors.extend(context_errors)
    if expected is not None:
        for field, value in expected.items():
            if receipt.get(field) != value:
                errors.append("Standards revalidation receipt %s=%r, expected %r" %
                              (field, receipt.get(field), value))
    return errors
















def standards_adoption_plan_errors(
        root, plan, catalog=None, queue=None, progress=None,
        validate_current=True,
        producer_tool_version=STANDARDS_ADOPTION_TOOL_VERSION):
    """Return closed-schema and referential errors for one adoption plan.

    New admission defaults to the current producer contract. Historical replay
    supplies the sealed commit receipt's ``tool_version`` so pre-1.3 and
    pre-1.4 plans are not reinterpreted under fields their producers did not
    promise.
    """
    # A plan being admitted is always judged by the running producer;
    # ``producer_tool_version`` is an era selector only for sealed replay.
    profile_contract_required = validate_current or \
        _standards_adoption_profile_contract_required(producer_tool_version)
    profile_inputs_required = validate_current or \
        _standards_adoption_profile_inputs_required(producer_tool_version)
    upstream_required = validate_current or \
        _standards_adoption_upstream_required(producer_tool_version)
    owner_projection_era = validate_current or \
        _standards_adoption_owner_projection_required(producer_tool_version)
    state_file_required = validate_current or \
        _standards_adoption_state_file_required(producer_tool_version)
    optional_fields = []
    if not profile_contract_required:
        optional_fields.append("profile_contract_fingerprint_after")
    if not profile_inputs_required:
        optional_fields.append("profile_load_inputs_sha256_after")
    if not upstream_required:
        optional_fields.extend(
            ("upstream_source_ref", "upstream_revision_id"))
    if not state_file_required:
        optional_fields.extend((
            "standards_state_sha256_before",
            "standards_effective_date_after",
        ))
    errors = _closed_mapping_errors(
        plan, "Standards adoption plan", STANDARDS_ADOPTION_PLAN_FIELDS,
        optional_fields=tuple(optional_fields))
    if not isinstance(plan, dict):
        return errors
    expected_schema = 2 if state_file_required else 1
    if plan.get("schema_version") != expected_schema:
        errors.append("Standards adoption plan schema_version must be %d" %
                      expected_schema)
    for field in (
            "adoption_id", "task_id", "task_state_before",
            "contract_version_before", "contract_version_after",
            "standards_version_before", "standards_version_after",
            "selected_profile_manifest_before",
            "selected_profile_manifest_after", "governance_revision_ref"):
        if not _nonempty_string(plan.get(field)):
            errors.append("Standards adoption plan %s must be non-empty" % field)
    if plan.get("task_state_before") not in ("active", "paused"):
        errors.append("Standards adoption plan supports only active or paused "
                      "tasks; completion-candidate must first transition back")
    if upstream_required and isinstance(plan, dict) and \
            not (set(("upstream_source_ref", "upstream_revision_id")) -
                 set(plan)):
        source = plan.get("upstream_source_ref")
        revision = plan.get("upstream_revision_id")
        if (source is None) != (revision is None):
            errors.append(
                "Standards adoption plan upstream_source_ref and "
                "upstream_revision_id must both name the upstream or both "
                "be null; half an identity identifies nothing")
        elif source is not None and (
                not _nonempty_string(source) or
                not _nonempty_string(revision)):
            errors.append(
                "Standards adoption plan upstream_source_ref and "
                "upstream_revision_id must be non-empty strings or an "
                "explicit null pair declaring no upstream")
    if state_file_required:
        effective = plan.get("standards_effective_date_after")
        try:
            parsed_effective = datetime.date.fromisoformat(str(effective))
        except ValueError:
            parsed_effective = None
        if parsed_effective is None or parsed_effective.isoformat() != effective:
            errors.append(
                "Standards adoption plan standards_effective_date_after "
                "must be YYYY-MM-DD")
    if (plan.get("standards_version_before") ==
            plan.get("standards_version_after")):
        errors.append("Standards adoption must change standards_version")
    for field in ("queue_revision_before", "queue_revision_after",
                  "queue_state_revision_before"):
        value = plan.get(field)
        minimum = 1 if field.startswith("queue_revision") else 0
        if (not isinstance(value, int) or isinstance(value, bool) or
                value < minimum):
            errors.append("Standards adoption plan %s must be an integer >= %d" %
                          (field, minimum))
    if (isinstance(plan.get("queue_revision_before"), int) and
            isinstance(plan.get("queue_revision_after"), int) and
            plan["queue_revision_after"] !=
            plan["queue_revision_before"] + 1):
        errors.append("Standards adoption queue_revision_after must increment "
                      "queue_revision_before exactly once")
    digest_fields = [
            "governance_revision_sha256", "standards_snapshot_sha256_after",
            "profile_snapshot_sha256_after", "coverage_sha256_before",
            "required_queue_sha256_before", "progress_sha256_before",
    ]
    if state_file_required:
        digest_fields.append("standards_state_sha256_before")
    if (profile_contract_required or
            "profile_contract_fingerprint_after" in plan):
        digest_fields.append("profile_contract_fingerprint_after")
    if (profile_inputs_required or
            "profile_load_inputs_sha256_after" in plan):
        digest_fields.append("profile_load_inputs_sha256_after")
    for field in digest_fields:
        if not SHA256_RE.fullmatch(str(plan.get(field, ""))):
            errors.append("Standards adoption plan %s is not a SHA-256" % field)

    list_fields = (
        "selected_route_ids_after", "selected_card_paths_after",
        "selected_profile_route_ids_after", "selected_read_sets_after",
        "loaded_module_paths_after", "immediate_gate_reruns",
        "boundary_gate_reruns",
    )
    for field in list_fields:
        errors.extend(_explicit_string_list_errors(
            plan.get(field), "Standards adoption plan %s" % field))
        if isinstance(plan.get(field), list) and plan[field] != sorted(plan[field]):
            errors.append("Standards adoption plan %s must be sorted" % field)

    if validate_current and root is not None:
        governance = plan.get("governance_revision_ref")
        expected_governance = \
            "kernel/K00 Standards Control/03 Standards Governance.md"
        if governance != expected_governance:
            errors.append("governance_revision_ref must be exactly %s" %
                          expected_governance)
        else:
            try:
                governance_path = kblib.repository_path(
                    root, governance, must_exist=True, reject_symlink=True)
                governance_sha = kblib.sha256_file(governance_path)
                if governance_sha != plan.get("governance_revision_sha256"):
                    errors.append("governance_revision_sha256 does not bind "
                                  "the approved K00/03 rule bytes")
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append("governance revision is unsafe or unreadable: %s" %
                              exc)
        if state_file_required:
            current_state, current_view, state_errors = \
                standards_state.snapshot(root)
            errors.extend("active Standards state: %s" % error
                          for error in state_errors)
            if current_view is not None:
                if current_view["active_standards_sha256"] != plan.get(
                        "standards_state_sha256_before"):
                    errors.append(
                        "standards_state_sha256_before is stale")
                if current_state.get("standards_version") != plan.get(
                        "standards_version_before"):
                    errors.append(
                        "active Standards state does not match plan before "
                        "version")
                if current_state.get("selected_profile_manifest") != plan.get(
                        "selected_profile_manifest_before"):
                    errors.append(
                        "active Standards state does not match plan before "
                        "Profile")
        after_profile = plan.get("selected_profile_manifest_after")
        if _nonempty_string(after_profile):
            profile_evidence, profile_errors = profile_load_evidence(
                root, after_profile)
            errors.extend(profile_errors)
            if profile_evidence is not None:
                if (profile_evidence.get("profile_snapshot_sha256") !=
                        plan.get("profile_snapshot_sha256_after")):
                    errors.append("profile_snapshot_sha256_after is stale")
                if (profile_evidence.get(
                        "profile_contract_fingerprint") != plan.get(
                            "profile_contract_fingerprint_after")):
                    errors.append(
                        "profile_contract_fingerprint_after is stale")
                if (profile_evidence.get(
                        "profile_load_inputs_sha256") != plan.get(
                            "profile_load_inputs_sha256_after")):
                    errors.append(
                        "profile_load_inputs_sha256_after is stale")
        try:
            actual = kblib.repository_tree_sha256(root, "kernel")
            if actual != plan.get("standards_snapshot_sha256_after"):
                errors.append("standards_snapshot_sha256_after is stale")
        except (OSError, ValueError) as exc:
            errors.append("cannot snapshot kernel Standards: %s" % exc)
        for field in ("selected_card_paths_after", "selected_read_sets_after",
                      "loaded_module_paths_after"):
            for relative in plan.get(field) if isinstance(
                    plan.get(field), list) else []:
                path_error = _path_error(root, relative, must_exist=True)
                if path_error:
                    errors.append("Standards adoption %s path %r is unsafe or "
                                  "missing: %s" % (field, relative, path_error))

    gate_registry = {}
    revalidation_capabilities = {}
    if validate_current and root is not None:
        gate_registry, gate_registry_errors = standards_gate_registry(root)
        errors.extend(gate_registry_errors)
        revalidation_capabilities, capability_errors = \
            standards_revalidation_capabilities(root, gate_registry)
        errors.extend(capability_errors)

    predicates = plan.get("changed_predicates")
    predicate_ids = []
    predicate_projected_owners = {}
    boundary_gate_ids = set()
    registered_gate_ids = set()
    if not isinstance(predicates, list):
        errors.append("Standards adoption changed_predicates must be an explicit list")
        predicates = []
    for index, predicate in enumerate(predicates):
        label = "changed_predicates[%d]" % index
        errors.extend(_closed_mapping_errors(
            predicate, label, STANDARDS_CHANGED_PREDICATE_FIELDS))
        if not isinstance(predicate, dict):
            continue
        predicate_id = predicate.get("predicate_id")
        if not _nonempty_string(predicate_id):
            errors.append("%s predicate_id must be non-empty" % label)
        else:
            predicate_ids.append(predicate_id)
        if predicate.get("change_kind") not in ("added", "removed", "modified"):
            errors.append("%s change_kind must be added, removed, or modified" %
                          label)
        owner = predicate.get("owner_path")
        if not _nonempty_string(owner):
            errors.append("%s owner_path must be non-empty" % label)
        elif validate_current and root is not None:
            path_error = _path_error(root, owner, must_exist=True)
            if path_error:
                errors.append("%s owner_path is unsafe or missing: %s" %
                              (label, path_error))
        affected = predicate.get("affected_gate_ids")
        errors.extend(_explicit_string_list_errors(
            affected, "%s affected_gate_ids" % label))
        if isinstance(affected, list):
            if not affected:
                errors.append("%s affected_gate_ids must be non-empty" % label)
            if affected != sorted(affected):
                errors.append("%s affected_gate_ids must be sorted" % label)
            registered_gate_ids.update(value for value in affected
                                       if _nonempty_string(value))
            if validate_current and root is not None:
                projected, projection_errors = projected_revalidation_owners(
                    affected, revalidation_capabilities)
                errors.extend("%s: %s" % (label, error)
                              for error in projection_errors)
                if _nonempty_string(predicate_id):
                    predicate_projected_owners[predicate_id] = set(projected)
                boundary_gate_ids.update(
                    value for value in projected
                    if (not profile_contract_required or
                        value != "profile-load"))
            elif not owner_projection_era:
                # Historical plans are replayed under their recorded raw Gate
                # union.  They predate owner projection and cannot be
                # rewritten merely because the current kernel gained it.
                boundary_gate_ids.update(
                    value for value in affected
                    if (_nonempty_string(value) and
                        (not profile_contract_required or
                         value != "profile-load")))
    if len(predicate_ids) != len(set(predicate_ids)):
        errors.append("Standards adoption repeats predicate_id")
    if predicate_ids != sorted(predicate_ids):
        errors.append("Standards adoption changed_predicates must be sorted by "
                      "predicate_id")
    predicate_set = set(predicate_ids)

    boundaries = plan.get("invalidation_boundaries")
    boundary_ids = []
    boundary_batch_targets = {}
    boundary_runtime_gate_ids = {}
    covered_predicates = set()
    affected_batches = set()
    if not isinstance(boundaries, list):
        errors.append("Standards adoption invalidation_boundaries must be an explicit list")
        boundaries = []
    target_kinds = frozenset((
        "batch", "receipt", "task", "terminal-audit",
        "maintenance-completion", "profile-load",
    ))
    for index, boundary in enumerate(boundaries):
        label = "invalidation_boundaries[%d]" % index
        errors.extend(_closed_mapping_errors(
            boundary, label, STANDARDS_INVALIDATION_BOUNDARY_FIELDS))
        if not isinstance(boundary, dict):
            continue
        boundary_id = boundary.get("boundary_id")
        if not _nonempty_string(boundary_id):
            errors.append("%s boundary_id must be non-empty" % label)
        else:
            boundary_ids.append(boundary_id)
        if boundary.get("target_kind") not in target_kinds:
            errors.append("%s target_kind is invalid" % label)
        for field in ("predicate_ids", "target_ids", "required_gate_ids"):
            values = boundary.get(field)
            errors.extend(_explicit_string_list_errors(
                values, "%s %s" % (label, field)))
            if isinstance(values, list):
                if not values:
                    errors.append("%s %s must be non-empty" % (label, field))
                if values != sorted(values):
                    errors.append("%s %s must be sorted" % (label, field))
        referenced = set(boundary.get("predicate_ids") or [])
        if not referenced.issubset(predicate_set):
            errors.append("%s references an unknown changed predicate" % label)
        covered_predicates.update(referenced)
        required_gate_ids = [
            value for value in (boundary.get("required_gate_ids") or [])
            if _nonempty_string(value)
        ]
        registered_gate_ids.update(required_gate_ids)
        if validate_current and root is not None:
            allowed_required_gate_ids = set().union(*(
                predicate_projected_owners.get(predicate_id, set())
                for predicate_id in referenced
            )) if referenced else set()
            extra_required_gate_ids = sorted(
                set(required_gate_ids) - allowed_required_gate_ids)
            if extra_required_gate_ids:
                errors.append(
                    "%s required_gate_ids adds owner Gate(s) not projected "
                    "by its predicate_ids: %s" % (
                        label, ", ".join(extra_required_gate_ids)))
            for gate_id in required_gate_ids:
                capability = revalidation_capabilities.get(gate_id) or {}
                if capability.get("role") not in (
                        "special-owner", "immediate-owner", "native-owner"):
                    errors.append(
                        "%s required_gate_ids names %s, which is not a "
                        "Standards revalidation boundary owner" %
                        (label, gate_id))
                if gate_id == "profile-load" and \
                        boundary.get("target_kind") != "profile-load":
                    errors.append(
                        "%s may require profile-load only on target_kind "
                        "profile-load; after-image admission cannot be moved "
                        "onto a batch boundary" % label)
        runtime_gate_ids = [
            value for value in required_gate_ids
            if not profile_contract_required or value != "profile-load"
        ]
        if _nonempty_string(boundary_id):
            boundary_runtime_gate_ids[boundary_id] = runtime_gate_ids
        if not validate_current:
            # Every historical producer froze its boundary-level additions
            # in required_gate_ids.  Pre-1.6 plans combine those recorded
            # gates with their raw affected-gate union; 1.6+ plans store only
            # projected owners there.  Reuse the recorded values in both
            # eras instead of dropping part of the old contract or
            # re-projecting it through a future capability table.
            boundary_gate_ids.update(runtime_gate_ids)
        targets = boundary.get("target_ids") or []
        if boundary.get("target_kind") == "batch":
            affected_batches.update(targets)
            if _nonempty_string(boundary_id):
                boundary_batch_targets[boundary_id] = set(targets)
            if queue is not None:
                known = {item.get("id") for item in queue.get("required_queue", [])
                         if isinstance(item, dict)}
                unknown = sorted(set(targets) - known)
                if unknown:
                    errors.append("%s names unknown batch target(s): %s" %
                                  (label, ", ".join(unknown)))
        if boundary.get("target_kind") == "receipt" and catalog is not None:
            unknown = sorted(set(targets) - set(catalog))
            if unknown:
                errors.append("%s names unknown receipt target(s): %s" %
                              (label, ", ".join(unknown)))
        if boundary.get("target_kind") == "task" and targets != [plan.get("task_id")]:
            errors.append("%s task target_ids must contain only task_id" % label)
        if (profile_contract_required and
                boundary.get("target_kind") == "profile-load"):
            expected_target = [plan.get("selected_profile_manifest_after")]
            if targets != expected_target:
                errors.append(
                    "%s profile-load target_ids must contain only "
                    "selected_profile_manifest_after" % label)
            if "profile-load" not in required_gate_ids:
                errors.append(
                    "%s profile-load boundary must require the profile-load "
                    "Gate at after-image admission" % label)
    if len(boundary_ids) != len(set(boundary_ids)):
        errors.append("Standards adoption repeats invalidation boundary_id")
    if boundary_ids != sorted(boundary_ids):
        errors.append("Standards adoption invalidation_boundaries must be sorted "
                      "by boundary_id")
    boundary_set = set(boundary_ids)

    # A Profile selection change is never an identity-only no-op.  Even when
    # two packages currently contain equivalent prose, profile-load authority
    # is deliberately path-bound and its receipt cannot transfer to another
    # manifest.  Require that edge to be declared as a changed predicate and
    # discharged by exactly one after-image admission boundary.  The same
    # rule applies when governance explicitly says any changed predicate
    # affects profile-load while keeping the manifest spelling unchanged.
    if profile_contract_required:
        profile_gate_predicates = {
            predicate.get("predicate_id")
            for predicate in predicates
            if (isinstance(predicate, dict) and
                _nonempty_string(predicate.get("predicate_id")) and
                isinstance(predicate.get("affected_gate_ids"), list) and
                "profile-load" in (predicate.get("affected_gate_ids") or []))
        }
        profile_boundaries = [
            (index, boundary) for index, boundary in enumerate(boundaries)
            if (isinstance(boundary, dict) and
                boundary.get("target_kind") == "profile-load")
        ]
        profile_selection_changed = (
            plan.get("selected_profile_manifest_before") !=
            plan.get("selected_profile_manifest_after")
        )
        if profile_selection_changed and not profile_gate_predicates:
            errors.append(
                "selected Profile change must declare a changed predicate whose "
                "affected_gate_ids include profile-load")
        if profile_gate_predicates or profile_selection_changed:
            if len(profile_boundaries) != 1:
                errors.append(
                    "Profile authority change requires exactly one profile-load "
                    "after-image invalidation boundary; found %d" %
                    len(profile_boundaries))
            else:
                index, boundary = profile_boundaries[0]
                referenced = set(boundary.get("predicate_ids") or [])
                omitted_profile_predicates = sorted(
                    profile_gate_predicates - referenced)
                if omitted_profile_predicates:
                    errors.append(
                        "invalidation_boundaries[%d] profile-load boundary must "
                        "reference every changed predicate whose "
                        "affected_gate_ids include profile-load; omitted: %s" %
                        (index, ", ".join(omitted_profile_predicates)))
        elif profile_boundaries:
            errors.append(
                "profile-load invalidation boundary requires a changed predicate "
                "whose affected_gate_ids include profile-load")

    # ``boundary_gate_reruns`` is only a projection; an entry there creates no
    # runtime obligation by itself.  Every Gate a predicate says it affects
    # must therefore occur on at least one concrete boundary that references
    # that same predicate.  Otherwise a plan can look complete in its union
    # while silently dropping the Gate from every enforcement edge.
    if profile_contract_required:
        if validate_current:
            predicate_affected_gates = {
                predicate.get("predicate_id"): set(
                    predicate_projected_owners.get(
                        predicate.get("predicate_id"), set()))
                for predicate in predicates
                if (isinstance(predicate, dict) and
                    _nonempty_string(predicate.get("predicate_id")) and
                    isinstance(predicate.get("affected_gate_ids"), list))
            }
        elif not owner_projection_era:
            # Historical plans retain their recorded raw Gate closure.  They
            # are replayed under their producer era, not retroactively
            # rewritten to the current leaf-to-owner projection.
            predicate_affected_gates = {
                predicate.get("predicate_id"): {
                    gate_id for gate_id in
                    predicate.get("affected_gate_ids") or []
                    if _nonempty_string(gate_id) and gate_id != "profile-load"
                }
                for predicate in predicates
                if (isinstance(predicate, dict) and
                    _nonempty_string(predicate.get("predicate_id")) and
                    isinstance(predicate.get("affected_gate_ids"), list))
            }
        else:
            # Current-era owner closure is already recorded in each boundary;
            # historical replay does not reinterpret semantic leaves through
            # a later capability table.
            predicate_affected_gates = {}
        boundary_gates_by_predicate = {
            predicate_id: set() for predicate_id in predicate_affected_gates
        }
        for boundary in boundaries:
            if not isinstance(boundary, dict):
                continue
            gates = {
                gate_id for gate_id in boundary.get("required_gate_ids", [])
                if _nonempty_string(gate_id)
            } if isinstance(boundary.get("required_gate_ids"), list) else set()
            for predicate_id in boundary.get("predicate_ids", []) \
                    if isinstance(boundary.get("predicate_ids"), list) else ():
                if predicate_id in boundary_gates_by_predicate:
                    boundary_gates_by_predicate[predicate_id].update(gates)
        for predicate_id in sorted(predicate_affected_gates):
            missing_gates = sorted(
                predicate_affected_gates[predicate_id] -
                boundary_gates_by_predicate[predicate_id])
            if missing_gates:
                errors.append(
                    "changed predicate %s affected_gate_ids lack an enforcing "
                    "invalidation boundary for: %s" %
                    (predicate_id, ", ".join(missing_gates)))

    invalidated = plan.get("invalidated_evidence")
    invalidated_ids = []
    reason_codes = frozenset((
        "predicate-changed", "receipt-schema-changed",
        "profile-binding-changed", "gate-semantics-changed",
    ))
    if not isinstance(invalidated, list):
        errors.append(
            "Standards adoption invalidated_evidence must be an explicit list")
        invalidated = []
    queue_ids = ({item.get("id") for item in queue.get("required_queue", [])
                  if isinstance(item, dict)} if queue is not None else set())
    for index, evidence in enumerate(invalidated):
        label = "invalidated_evidence[%d]" % index
        errors.extend(_closed_mapping_errors(
            evidence, label, STANDARDS_INVALIDATED_EVIDENCE_FIELDS))
        if not isinstance(evidence, dict):
            continue
        receipt_id = evidence.get("receipt_id")
        if not _nonempty_string(receipt_id):
            errors.append("%s receipt_id must be non-empty" % label)
        else:
            invalidated_ids.append(receipt_id)
            if (catalog is not None and receipt_id not in catalog and
                    receipt_id not in (getattr(catalog, "cold", None) or {})):
                errors.append("%s names unknown receipt %s" %
                              (label, receipt_id))
        for field in ("predicate_ids", "dimension_ids", "boundary_ids",
                      "revalidation_scope_ids"):
            values = evidence.get(field)
            errors.extend(_explicit_string_list_errors(
                values, "%s %s" % (label, field)))
            if isinstance(values, list) and values != sorted(values):
                errors.append("%s %s must be sorted" % (label, field))
        if not evidence.get("predicate_ids") or not set(
                evidence.get("predicate_ids", [])).issubset(predicate_set):
            errors.append("%s predicate_ids must name changed predicates" % label)
        if not evidence.get("dimension_ids"):
            errors.append("%s dimension_ids must be non-empty" % label)
        if not evidence.get("boundary_ids") or not set(
                evidence.get("boundary_ids", [])).issubset(boundary_set):
            errors.append("%s boundary_ids must name invalidation boundaries" %
                          label)
        if evidence.get("reason_code") not in reason_codes:
            errors.append("%s reason_code is invalid" % label)
        affected_batches.update(
            value for value in (evidence.get("revalidation_scope_ids") or [])
            if value in queue_ids)
    if len(invalidated_ids) != len(set(invalidated_ids)):
        errors.append("Standards adoption repeats invalidated receipt_id")
    if invalidated_ids != sorted(invalidated_ids):
        errors.append(
            "Standards adoption invalidated_evidence must be sorted by receipt_id")

    # The Queue batches each boundary actually reaches: the batches it targets
    # directly, plus every Queue batch an invalidated-evidence row that lists
    # this boundary puts in its revalidation scope.  This is the one
    # derivation of that union; both the reachability rule below and the
    # dead-gate refusal further down read it, so neither can disagree with the
    # other about which batches a boundary binds.  A boundary target that is
    # not a Queue batch stays in the mapping -- it is reported as an unknown
    # batch target above -- and is filtered where live state is needed.
    boundary_reached_batches = {
        boundary_id: set(targets)
        for boundary_id, targets in boundary_batch_targets.items()
    }
    for evidence in invalidated:
        if not isinstance(evidence, dict):
            continue
        scoped = {value for value
                  in evidence.get("revalidation_scope_ids") or []
                  if value in queue_ids}
        if not scoped:
            continue
        for boundary_id in evidence.get("boundary_ids") or []:
            if _nonempty_string(boundary_id):
                boundary_reached_batches.setdefault(
                    boundary_id, set()).update(scoped)

    # Any route by which a boundary reaches a terminal batch is equally
    # impossible to discharge.  Checking only target_kind=batch left an
    # alternate path through invalidated-evidence revalidation_scope_ids:
    # the plan admitted a post-admission claim whose producer rejects the
    # closed/cancelled target forever.  Admission therefore judges the exact
    # direct-target plus evidence-scope union derived above.  Historical
    # replay remains producer-era fact and is never rejected retroactively.
    if validate_current and queue is not None:
        terminal_states = {
            item.get("id"): item.get("state")
            for item in queue.get("required_queue", [])
            if isinstance(item, dict) and
            item.get("state") in TERMINAL_STATES
        }
        for index, boundary in enumerate(boundaries):
            if not isinstance(boundary, dict):
                continue
            boundary_id = boundary.get("boundary_id")
            if not boundary_runtime_gate_ids.get(boundary_id):
                continue
            terminal = sorted(
                set(boundary_reached_batches.get(boundary_id, set())) &
                set(terminal_states))
            if terminal:
                errors.append(
                    "invalidation_boundaries[%d] boundary %s creates "
                    "post-admission owner claims on terminal batch(es) %s; "
                    "route the impact to a non-terminal successor instead" %
                    (index, boundary_id, ", ".join(terminal)))

    # K12/10: a boundary is only ever claimed at a Queue batch's next
    # transition, either because it targets that batch or because invalidated
    # evidence puts the batch in its revalidation scope.  A boundary that
    # reaches neither is silently discharged, so the plan is refused instead
    # of recording protection nothing will apply.
    # Only a plan being admitted is refused.  A historical adoption was
    # approved under the rules of its own day, its plan bytes are sealed into
    # append-only receipts, and no sanctioned transaction can rewrite them --
    # so refusing it here would strand the instance with a defect it has no
    # legal way to repair.  Historical records are replayed with
    # validate_current=False for exactly this reason.
    if validate_current and queue is not None and boundaries:
        enforced = set(boundary_reached_batches)
        for index, boundary in enumerate(boundaries):
            if not isinstance(boundary, dict):
                continue
            boundary_id = boundary.get("boundary_id")
            if not _nonempty_string(boundary_id) or boundary_id in enforced:
                continue
            if (boundary.get("target_kind") == "profile-load" and
                    not boundary_runtime_gate_ids.get(boundary_id)):
                # The canonical producer is invoked against the writable
                # after-image above.  Only additional downstream Gate IDs need
                # a Queue batch through which their revalidation is claimed.
                continue
            errors.append(
                "invalidation_boundaries[%d] boundary %s has target_kind %r "
                "and no invalidated evidence scoping it to a Queue batch, so "
                "no gate rerun would ever be required for it" %
                (index, boundary_id, boundary.get("target_kind")))

    # K00/15: selected Read Sets are transitively closed over Read Sets named by
    # their loading boundaries, and every non-Read-Set target in that closure
    # belongs in the declared module load set. The obligations are containment,
    # not equality: additional tool and profile paths remain legitimate.
    #
    # Only a plan being admitted is judged, for the reason the boundary rule
    # above is so scoped: a historical adoption's plan bytes are sealed into
    # append-only receipts and no sanctioned transaction can rewrite them, so
    # refusing one here would strand an instance with an under-declaration it
    # has no legal way to repair.  Replay passes validate_current=False.
    if validate_current and root is not None:
        declared_values = plan.get("loaded_module_paths_after")
        declared = {
            value for value in declared_values
            if _nonempty_string(value)
        } if isinstance(declared_values, list) else set()
        selected_values = plan.get("selected_read_sets_after")
        selected = {
            value for value in selected_values
            if _nonempty_string(value)
        } if isinstance(selected_values, list) else set()
        read_sets, modules, invalid_selected, closure_errors = \
            _read_set_load_closure(
                root, selected,
                plan.get("selected_profile_manifest_after"),
                plan.get("selected_profile_route_ids_after"),
            )
        errors.extend("Read Set load closure: %s" % error
                      for error in closure_errors)
        for target in sorted(invalid_selected):
            if not any(target in error for error in closure_errors):
                errors.append(
                    "selected_read_sets_after path %s cannot be used as a "
                    "Read Set traversal root, per %s" %
                    (target, READ_SET_BOUNDARY_OWNER_PATH))
        for target in sorted(read_sets - selected):
            errors.append(
                "selected_read_sets_after omits %s, which a loading boundary "
                "of its transitive Read Set closure selects; every "
                "boundary-referenced Read Set MUST be declared, per %s" %
                (target, READ_SET_BOUNDARY_OWNER_PATH))
        for target in sorted(modules - declared):
            errors.append(
                "loaded_module_paths_after omits %s, which a loading boundary "
                "in the transitive Read Set closure names; the load set MUST "
                "contain every non-Read-Set target, per %s" %
                (target, READ_SET_BOUNDARY_OWNER_PATH))

    if predicate_set:
        blocking_predicate_set = (set(
            predicate_id for predicate_id, owners in
            predicate_projected_owners.items() if owners)
            if validate_current else
            (set(covered_predicates) if owner_projection_era else predicate_set))
        if blocking_predicate_set and not boundary_ids:
            errors.append(
                "changed predicates with blocking owner Gates require "
                "invalidation boundaries")
        if not blocking_predicate_set.issubset(covered_predicates):
            errors.append(
                "every changed predicate with a blocking owner Gate must "
                "occur in an invalidation boundary")
    elif invalidated or boundaries:
        errors.append("no-op adoption requires empty invalidated_evidence and "
                      "invalidation_boundaries")
    if plan.get("immediate_gate_reruns") != ["required-queue-consistency"]:
        errors.append("immediate_gate_reruns must be exactly "
                      "[required-queue-consistency]")
    expected_boundary_gates = sorted(boundary_gate_ids)
    if plan.get("boundary_gate_reruns") != expected_boundary_gates:
        errors.append("boundary_gate_reruns must equal the exact affected-gate "
                      "union %r" % expected_boundary_gates)

    if validate_current and root is not None:
        registry = gate_registry
        unknown_gates = sorted(registered_gate_ids - set(registry))
        if unknown_gates:
            errors.append("Standards adoption names unregistered Gate ID(s): %s" %
                          ", ".join(unknown_gates))

        # K12/10: a boundary's gates are claimed at the position each one
        # belongs to.  A gate a batch is at the position of is claimed now;
        # one whose position lies ahead is claimed there.  A boundary that
        # reaches neither, at every batch it reaches, names only gates those
        # batches have already left behind and can never remake, so it records
        # protection that will never apply -- the same defect the reachability
        # rule above refuses, one level down: that rule asks whether a
        # boundary reaches a batch at all, this one whether reaching them
        # obliges anything.  Both read the same reached-batch mapping, and
        # this one judges every batch a boundary reaches by either route, not
        # only its declared `batch` targets: a boundary bound to a batch
        # through invalidated-evidence scope is enforced there identically.
        #
        # Only a plan being admitted is judged, for the reason stated there: a
        # historical adoption's plan bytes are sealed into append-only
        # receipts and no sanctioned transaction can rewrite them, so refusing
        # one here would strand an instance with a defect it has no legal way
        # to repair.  Replay passes validate_current=False.
        if queue is not None:
            states = {item.get("id"): item.get("state")
                      for item in queue.get("required_queue", [])
                      if isinstance(item, dict)}
            for index, boundary in enumerate(boundaries):
                if not isinstance(boundary, dict):
                    continue
                boundary_id = boundary.get("boundary_id")
                gate_ids = boundary_runtime_gate_ids.get(boundary_id, [])
                reached = sorted(
                    boundary_reached_batches.get(boundary_id, set()) &
                    set(states))
                if not gate_ids or not reached:
                    continue
                dead = {}
                for batch_id in reached:
                    due, deferred, passed = \
                        partition_revalidation_owner_claims(
                            gate_ids, states[batch_id], registry,
                            revalidation_capabilities)
                    if due or deferred:
                        if passed:
                            dead[batch_id] = passed
                        continue
                    if passed:
                        dead[batch_id] = passed
                if dead:
                    errors.append(
                        "invalidation_boundaries[%d] boundary %s reaches "
                        "Queue batch(es) that already passed Standards "
                        "revalidation owner edge(s): %s; roll back before "
                        "that edge or route the impact to a successor" % (
                            index, boundary_id,
                            ", ".join("%s (%s: %s)" % (
                                batch_id, states[batch_id],
                                "/".join(dead[batch_id]))
                                for batch_id in sorted(dead))))

    if validate_current and root is not None and queue is not None and \
            catalog is not None:
        consumers = invalidated_receipt_consumers(root, queue, catalog)
        for evidence in invalidated:
            if not isinstance(evidence, dict):
                continue
            receipt_id = evidence.get("receipt_id")
            actual_batches = {
                row.get("batch_id") for row in consumers.get(receipt_id, [])
                if _nonempty_string(row.get("batch_id"))
            }
            declared_batches = set(evidence.get("revalidation_scope_ids") or [])
            for boundary_id in evidence.get("boundary_ids") or []:
                declared_batches.update(
                    boundary_batch_targets.get(boundary_id, set()))
            omitted = sorted(actual_batches - declared_batches)
            if omitted:
                errors.append(
                    "invalidated receipt %s is consumed by Queue/Delta batch(es) "
                    "omitted from its own boundaries/revalidation scope: %s" %
                    (receipt_id, ", ".join(omitted)))

    if validate_current and queue is not None:
        items = {item.get("id"): item for item in queue.get("required_queue", [])
                 if isinstance(item, dict)}
        for batch_id in sorted(affected_batches):
            item = items.get(batch_id)
            if item is None:
                continue
            if item.get("state") == "merge-ready":
                errors.append("affected batch %s is merge-ready; roll it back "
                              "before Standards adoption" % batch_id)
            if (item.get("state") == "open" and
                    item.get("hold_state") != "revalidation-required"):
                errors.append("affected open batch %s must already have "
                              "hold_state=revalidation-required" % batch_id)

    if validate_current and progress is not None and isinstance(
            progress.get("contract"), dict):
        contract = progress["contract"]
        if contract.get("contract_version") != plan.get(
                "contract_version_before"):
            errors.append("contract_version_before does not match Progress")
        load_changed = any(contract.get(field[:-6]) != plan.get(field)
                           for field in (
                               "selected_route_ids_after",
                               "selected_card_paths_after",
                               "selected_profile_route_ids_after",
                               "selected_read_sets_after",
                               "loaded_module_paths_after"))
        material_change = bool(predicate_set) or load_changed or (
            plan.get("selected_profile_manifest_before") !=
            plan.get("selected_profile_manifest_after"))
        if (material_change and plan.get("contract_version_after") ==
                plan.get("contract_version_before")):
            errors.append("predicate/Profile/load-set change requires a new "
                          "contract_version")
    return errors


def _standards_adoption_errors(
        root, progress, catalog, queue, active_standards_view=None):
    """Validate plan/record/commit bindings for all persisted adoptions."""
    records = progress.get("standards_adoptions")
    if not isinstance(records, list):
        return []
    errors = []
    previous = None
    accounted = accounted_standards_versions(progress, queue)
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        label = "Progress standards_adoptions[%d]" % index
        try:
            plan_file = kblib.managed_repository_path(
                root, record.get("plan_path"), STANDARDS_ADOPTION_PLAN_PREFIX,
                suffixes=(".yaml",), must_exist=True)
            plan_sha = kblib.sha256_file(plan_file)
            plan = kblib.load_yaml_file(plan_file)
        except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
            errors.append("%s plan is unsafe or unreadable: %s" % (label, exc))
            continue
        if plan_sha != record.get("plan_sha256"):
            errors.append("%s plan_sha256 does not match current plan bytes" % label)
        receipt_id = record.get("verification_receipt")
        # Resolve the sealed producer identity before interpreting its plan.
        # Current 1.4 fields cannot be projected backward onto earlier history,
        # while an absent/malformed version must not downgrade the contract.
        receipt = _require_receipt(
            catalog, receipt_id, "%s commit" % label, errors,
            expected={
                "tool": STANDARDS_ADOPTION_TOOL,
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "gate_id": "standards-adoption",
                "check": "standards_adoption",
                "target": record.get("id"),
                "result": "pass",
                "invalidated_by": None,
                "transaction_phase": "commit",
                "task_id": queue.get("task_id"),
                "actor_role": "integrator",
                "plan_path": record.get("plan_path"),
                "plan_sha256": record.get("plan_sha256"),
                "transaction_id": record.get("transaction_id"),
            },
        )
        producer_tool_version = (
            receipt.get("tool_version") if isinstance(receipt, dict) else
            STANDARDS_ADOPTION_TOOL_VERSION
        )
        profile_contract_required = \
            _standards_adoption_profile_contract_required(
                producer_tool_version)
        profile_inputs_required = \
            _standards_adoption_profile_inputs_required(
                producer_tool_version)
        if (profile_contract_required and
                "profile_contract_fingerprint_after" not in record):
            errors.append(
                "%s misses profile_contract_fingerprint_after required by "
                "adopt_standards %s" % (label, producer_tool_version))
        if (profile_inputs_required and
                "profile_load_inputs_sha256_after" not in record):
            errors.append(
                "%s misses profile_load_inputs_sha256_after required by "
                "adopt_standards %s" % (label, producer_tool_version))
        if _standards_adoption_upstream_required(producer_tool_version):
            for field in ("upstream_source_ref", "upstream_revision_id"):
                if field not in record:
                    errors.append(
                        "%s misses %s required by adopt_standards %s; the "
                        "distribution has no version numbers, so the "
                        "adoption record is what makes upstream and "
                        "downstream comparable" %
                        (label, field, producer_tool_version))
        state_file_required = _standards_adoption_state_file_required(
            producer_tool_version)
        if state_file_required:
            for field in (
                    "standards_effective_date_after",
                    "standards_state_sha256_before",
                    "after_standards_state_sha256"):
                if field not in record:
                    errors.append(
                        "%s misses %s required by adopt_standards %s" %
                        (label, field, producer_tool_version))
        errors.extend("%s %s" % (label, error)
                      for error in standards_adoption_plan_errors(
                          root, plan, catalog=catalog, queue=queue,
                          progress=progress, validate_current=False,
                          producer_tool_version=producer_tool_version))
        changed_ids = sorted(
            row.get("predicate_id") for row in plan.get("changed_predicates", [])
            if isinstance(row, dict) and _nonempty_string(row.get("predicate_id")))
        invalidated_ids = sorted(
            row.get("receipt_id")
            for row in plan.get("invalidated_evidence", [])
            if isinstance(row, dict) and _nonempty_string(row.get("receipt_id")))
        boundary_ids = sorted(
            row.get("boundary_id") for row in plan.get("invalidation_boundaries", [])
            if isinstance(row, dict) and _nonempty_string(row.get("boundary_id")))
        record_plan_fields = {
            "id": "adoption_id",
            "task_state_before": "task_state_before",
            "contract_version_before": "contract_version_before",
            "contract_version_after": "contract_version_after",
            "standards_version_before": "standards_version_before",
            "standards_version_after": "standards_version_after",
            "selected_profile_manifest_before":
                "selected_profile_manifest_before",
            "selected_profile_manifest_after":
                "selected_profile_manifest_after",
            "governance_revision_ref": "governance_revision_ref",
            "governance_revision_sha256": "governance_revision_sha256",
            "standards_snapshot_sha256_after":
                "standards_snapshot_sha256_after",
            "profile_snapshot_sha256_after":
                "profile_snapshot_sha256_after",
            "profile_contract_fingerprint_after":
                "profile_contract_fingerprint_after",
            "profile_load_inputs_sha256_after":
                "profile_load_inputs_sha256_after",
            "selected_route_ids_after": "selected_route_ids_after",
            "selected_card_paths_after": "selected_card_paths_after",
            "selected_profile_route_ids_after":
                "selected_profile_route_ids_after",
            "selected_read_sets_after": "selected_read_sets_after",
            "loaded_module_paths_after": "loaded_module_paths_after",
            "queue_revision_before": "queue_revision_before",
            "queue_revision_after": "queue_revision_after",
            "queue_state_revision_before": "queue_state_revision_before",
            "coverage_sha256_before": "coverage_sha256_before",
            "required_queue_sha256_before": "required_queue_sha256_before",
            "progress_sha256_before": "progress_sha256_before",
            "immediate_gate_reruns": "immediate_gate_reruns",
            "boundary_gate_reruns": "boundary_gate_reruns",
        }
        if state_file_required:
            record_plan_fields.update({
                "standards_effective_date_after":
                    "standards_effective_date_after",
                "standards_state_sha256_before":
                    "standards_state_sha256_before",
            })
        for record_field, plan_field in record_plan_fields.items():
            if record.get(record_field) != plan.get(plan_field):
                errors.append("%s %s does not match its plan" %
                              (label, record_field))
        for field, expected in (
                ("changed_predicate_ids", changed_ids),
                ("invalidated_evidence_receipt_ids", invalidated_ids),
                ("invalidation_boundary_ids", boundary_ids)):
            if record.get(field) != expected:
                errors.append("%s %s does not match its plan" % (label, field))
        # Historical: a committed adoption's own commit receipt.  Its producer
        # version is whatever `adopt_standards` was when the transaction ran,
        # so the era it claims is checked instead of today's constant.
        errors.extend(_producer_era_errors(
            receipt, receipt_id, "%s commit" % label, accounted))
        if receipt is not None:
            receipt_bindings = {
                "checked_at": "adopted_at",
                "before_coverage_sha256": "coverage_sha256_before",
                "before_queue_sha256": "required_queue_sha256_before",
                "before_progress_sha256": "progress_sha256_before",
                "after_coverage_sha256": "after_coverage_sha256",
                "after_queue_sha256": "after_required_queue_sha256",
                "queue_revision_before": "queue_revision_before",
                "queue_revision_after": "queue_revision_after",
                "state_revision_before": "queue_state_revision_before",
                "state_revision_after": "queue_state_revision_before",
                "standards_version_before": "standards_version_before",
                "standards_version_after": "standards_version_after",
                "selected_profile_manifest_before":
                    "selected_profile_manifest_before",
                "selected_profile_manifest_after":
                    "selected_profile_manifest_after",
                "contract_version_before": "contract_version_before",
                "contract_version_after": "contract_version_after",
                "governance_revision_ref": "governance_revision_ref",
                "governance_revision_sha256": "governance_revision_sha256",
                "standards_snapshot_sha256_after":
                    "standards_snapshot_sha256_after",
                "profile_snapshot_sha256_after":
                    "profile_snapshot_sha256_after",
                "profile_contract_fingerprint_after":
                    "profile_contract_fingerprint_after",
                "profile_load_inputs_sha256_after":
                    "profile_load_inputs_sha256_after",
                "changed_predicate_ids": "changed_predicate_ids",
                "invalidated_evidence_receipt_ids":
                    "invalidated_evidence_receipt_ids",
                "invalidation_boundary_ids": "invalidation_boundary_ids",
                "immediate_gate_reruns": "immediate_gate_reruns",
                "immediate_gate_receipts": "immediate_gate_receipts",
                "boundary_gate_reruns": "boundary_gate_reruns",
                # 1.5 upstream identity; on legacy chains both sides are
                # absent and absent equals absent.
                "upstream_source_ref": "upstream_source_ref",
                "upstream_revision_id": "upstream_revision_id",
            }
            if state_file_required:
                receipt_bindings.update({
                    "before_standards_state_sha256":
                        "standards_state_sha256_before",
                    "after_standards_state_sha256":
                        "after_standards_state_sha256",
                    "standards_effective_date_after":
                        "standards_effective_date_after",
                })
            for receipt_field, record_field in receipt_bindings.items():
                if receipt.get(receipt_field) != record.get(record_field):
                    errors.append("%s receipt %s does not match record %s" %
                                  (label, receipt_field, record_field))
            after_progress = receipt.get("after_progress_sha256")
            if not SHA256_RE.fullmatch(str(after_progress or "")):
                errors.append("%s receipt has invalid after_progress_sha256" %
                              label)
            immediate_ids = record.get("immediate_gate_receipts")
            if not isinstance(immediate_ids, list) or len(immediate_ids) != 1:
                errors.append("%s must bind exactly one immediate gate receipt" %
                              label)
            else:
                # Historical: the gate this committed transaction already
                # consumed.  No `tool_version` comparison, and none is needed
                # -- `standards_version` below binds the record's own
                # `standards_version_after` exactly, which states the producer
                # era more tightly than the accounted-version set could.
                _require_receipt(
                    catalog, immediate_ids[0], "%s immediate Queue gate" % label,
                    errors, expected={
                        "tool": TOOL,
                        "gate_id": "required-queue-consistency",
                        "check": "required_queue",
                        "target": QUEUE_PATH,
                        "result": "pass",
                        "invalidated_by": None,
                        "queue_check_mode": "consistency",
                        "task_id": queue.get("task_id"),
                        "queue_revision": record.get("queue_revision_after"),
                        "queue_state_revision":
                            record.get("queue_state_revision_before"),
                        "required_queue_sha256":
                            record.get("after_required_queue_sha256"),
                        "coverage_ledger_sha256":
                            record.get("after_coverage_sha256"),
                        "progress_ledger_sha256": after_progress,
                        "standards_version":
                            record.get("standards_version_after"),
                        "selected_profile_manifest":
                            record.get("selected_profile_manifest_after"),
                    })
        if previous is not None:
            if (record.get("standards_version_before") !=
                    previous.get("standards_version_after")):
                errors.append("%s does not continue prior Standards version" % label)
            if (record.get("selected_profile_manifest_before") !=
                    previous.get("selected_profile_manifest_after")):
                errors.append("%s does not continue prior profile selection" % label)
            if (isinstance(record.get("queue_revision_before"), int) and
                    isinstance(previous.get("queue_revision_after"), int) and
                    record["queue_revision_before"] <
                    previous["queue_revision_after"]):
                errors.append("%s moves Queue revision backward" % label)
        previous = record
    if records and isinstance(records[-1], dict):
        latest = records[-1]
        if active_standards_view is not None:
            if (active_standards_view.get("latest_adoption_receipt") !=
                    latest.get("verification_receipt")):
                errors.append(
                    "canonical Standards state latest_adoption_receipt does "
                    "not match latest Progress adoption")
            expected_state_sha = latest.get(
                "after_standards_state_sha256")
            if (expected_state_sha is not None and
                    active_standards_view.get("active_standards_sha256") !=
                    expected_state_sha):
                errors.append(
                    "canonical Standards state bytes do not match latest "
                    "Progress adoption")
        contract = progress.get("contract") if isinstance(
            progress.get("contract"), dict) else {}
        # A K13/06 Contract Amendment is the other guarded writer of the
        # frozen contract, and it MUST advance `contract_version`.  This
        # binding was written when adoption was the only one, so it read
        # "the adoption is the last word on the contract" -- a sentence no
        # kernel module states.  An amendment that literally continues from
        # this adoption's after-version supersedes that one field; the
        # contract anchor chain owns the continuity from there, and every
        # other field stays strictly bound because the amendment writer's
        # allowlist cannot touch them.
        superseding = next(
            (row for row in (progress.get("amendments") or [])
             if isinstance(row, dict) and
             row.get("operation") == "contract-amendment" and
             row.get("contract_version_before") ==
             latest.get("contract_version_after")), None)
        for field, contract_field in (
                ("contract_version_after", "contract_version"),
                ("standards_version_after", "standards_version"),
                ("selected_profile_manifest_after", "selected_profile_manifest"),
                ("selected_route_ids_after", "selected_route_ids"),
                ("selected_card_paths_after", "selected_card_paths"),
                ("selected_profile_route_ids_after", "selected_profile_route_ids"),
                ("selected_read_sets_after", "selected_read_sets"),
                ("loaded_module_paths_after", "loaded_module_paths")):
            if field == "contract_version_after" and superseding is not None:
                continue
            if latest.get(field) != contract.get(contract_field):
                errors.append("latest Standards adoption %s does not bind live "
                              "Progress contract.%s" % (field, contract_field))
    return errors




























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




















def _candidate_evidence_binding_errors(root, label, relative, expected_sha,
                                       expected_bytes, expected_records):
    """Prove the born-cold evidence file is the one the attestation bound.

    The attestation carries this file's hash precisely because the full
    disposition detail was moved out of it; checking only that a file of
    the right length sits at the path re-creates the hole the externalizing
    was supposed to be safe under.  A same-length edit to an acceptance row
    would pass, and the next seal would then hash the edited bytes into the
    cold manifest and make the edit permanent evidence -- laundering a
    tamper through the very mechanism that exists to freeze history.  So
    the bytes are compared on every run, before any seal can adopt them.
    """
    errors = []
    if not _cold_path_within_root(root, relative, errors):
        return errors
    full = os.path.join(root, relative)
    try:
        descriptor = os.lstat(full)
    except OSError:
        return ["%s candidate evidence file %s is missing (K12/07 "
                "fail-closed)" % (label, relative)]
    if os.path.islink(full) or not stat.S_ISREG(descriptor.st_mode):
        return ["%s candidate evidence file %s must be a regular file" %
                (label, relative)]
    if descriptor.st_nlink != 1:
        return ["%s candidate evidence file %s has %d hard links" %
                (label, relative, descriptor.st_nlink)]
    try:
        with open(full, "rb") as handle:
            payload = handle.read()
    except OSError as exc:
        return ["%s candidate evidence file %s is unreadable: %s" %
                (label, relative, exc)]
    if expected_bytes is not None and len(payload) != expected_bytes:
        errors.append("%s candidate evidence file %s is %d bytes on disk but "
                      "the attestation sealed %d (K12/07 fail-closed)" %
                      (label, relative, len(payload), expected_bytes))
    if isinstance(expected_sha, str) and SHA256_RE.fullmatch(expected_sha):
        actual = kblib.sha256_bytes(payload)
        if actual != expected_sha:
            errors.append(
                "%s candidate evidence file %s hashes to %s but the "
                "attestation bound %s; externalized detail is evidence only "
                "while its attestation still names these exact bytes (K12/07 "
                "fail-closed)" % (label, relative, actual, expected_sha))
    if (isinstance(expected_records, int) and
            not isinstance(expected_records, bool)):
        actual_records = payload.count(b"\n")
        if actual_records != expected_records:
            errors.append(
                "%s candidate evidence file %s holds %d record(s) but the "
                "attestation sealed %d" %
                (label, relative, actual_records, expected_records))
    return errors


def _compact_attestation_errors(attestation, attestation_id, item_id,
                                root=None, receipt_version=None):
    """Validate a compact-era reviewer attestation (K12/09, 1.9.0+).

    A compact bundle keeps the authorization surface inline -- counts, the
    per-type counts, the accepted-set fingerprint, and every
    policy-exception disposition with its sealed decision facts -- and
    externalizes the full candidate detail to one born-cold evidence file
    that the hot path never deserializes.  What must therefore hold here:
    the inline numbers are coherent with each other, the evidence file is
    bound by path, byte size, record count and content hash, and when a
    repository root is available the bound file actually exists at exactly
    its sealed size (fail closed; the full hash is re-proven on
    dereference and under ``seal_receipts.py --verify``).
    """
    errors = []
    label = "%s declared reviewer attestation %s" % (item_id, attestation_id)
    count = attestation.get("accepted_candidate_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append("%s accepted_candidate_count must be a non-negative "
                      "integer" % label)
        count = None
    accepted_types = attestation.get("accepted_candidate_types")
    if not isinstance(accepted_types, list) or any(
            not _nonempty_string(value) for value in accepted_types):
        errors.append("%s accepted_candidate_types must be a string list" %
                      label)
        accepted_types = []
    if len(accepted_types) != len(set(accepted_types)):
        errors.append("%s repeats an accepted candidate type" % label)
    type_counts = attestation.get("accepted_by_type_counts")
    if not isinstance(type_counts, dict):
        errors.append("%s accepted_by_type_counts must be a mapping" % label)
        type_counts = {}
    else:
        bad_values = [key for key, value in type_counts.items()
                      if not isinstance(value, int) or
                      isinstance(value, bool) or value < 0]
        if bad_values:
            errors.append("%s accepted_by_type_counts values must be "
                          "non-negative integers" % label)
        if sorted(type_counts) != sorted(set(accepted_types)):
            errors.append("%s accepted_by_type_counts keys must equal "
                          "accepted_candidate_types" % label)
        elif count is not None and not bad_values and \
                sum(type_counts.values()) != count:
            errors.append("%s accepted_by_type_counts sum to %d, expected "
                          "accepted_candidate_count %d" %
                          (label, sum(type_counts.values()), count))
    set_sha = attestation.get("candidate_set_sha256")
    if not isinstance(set_sha, str) or not SHA256_RE.fullmatch(set_sha):
        errors.append("%s candidate_set_sha256 must be a sha256 fingerprint "
                      "over the sorted accepted candidate IDs" % label)
    evidence_path = attestation.get("candidate_evidence_path")
    evidence_sha = attestation.get("candidate_evidence_sha256")
    evidence_bytes = attestation.get("candidate_evidence_bytes")
    evidence_records = attestation.get("candidate_evidence_records")
    if (not _nonempty_string(evidence_path) or
            not evidence_path.startswith(
                kblib.RECEIPT_COLD_EVIDENCE_PREFIX + "/") or
            not evidence_path.endswith(".jsonl")):
        errors.append("%s candidate_evidence_path must be a .jsonl file "
                      "under %s" %
                      (label, kblib.RECEIPT_COLD_EVIDENCE_PREFIX))
        evidence_path = None
    if not isinstance(evidence_sha, str) or not SHA256_RE.fullmatch(
            evidence_sha):
        errors.append("%s candidate_evidence_sha256 must be a sha256 "
                      "fingerprint" % label)
    if (not isinstance(evidence_bytes, int) or
            isinstance(evidence_bytes, bool) or evidence_bytes < 0):
        errors.append("%s candidate_evidence_bytes must be a non-negative "
                      "integer" % label)
        evidence_bytes = None
    if (not isinstance(evidence_records, int) or
            isinstance(evidence_records, bool) or evidence_records < 0):
        errors.append("%s candidate_evidence_records must be a non-negative "
                      "integer" % label)
    elif count is not None and evidence_records != count:
        errors.append("%s candidate_evidence_records=%d does not equal "
                      "accepted_candidate_count=%d" %
                      (label, evidence_records, count))
    if root is not None and evidence_path is not None:
        errors.extend(_candidate_evidence_binding_errors(
            root, label, evidence_path, evidence_sha, evidence_bytes,
            evidence_records))
    dispositions = attestation.get("candidate_dispositions")
    if not isinstance(dispositions, list):
        errors.append("%s candidate_dispositions must be a list carrying "
                      "exactly the policy-exception dispositions" % label)
        dispositions = []
    for index, disposition in enumerate(dispositions):
        disposition_label = "%s candidate_dispositions[%d]" % (
            item_id, index)
        if not isinstance(disposition, dict):
            errors.append("%s must be a mapping" % disposition_label)
            continue
        candidate_id = disposition.get("candidate_id")
        candidate_type = disposition.get("candidate_type")
        if (not _nonempty_string(candidate_id) or
                not candidate_id.startswith("candidate-sha256:") or
                not SHA256_RE.fullmatch(candidate_id.replace(
                    "candidate-sha256:", "sha256:", 1))):
            errors.append("%s has invalid stable candidate_id" %
                          disposition_label)
        if not _nonempty_string(candidate_type) or ":" not in candidate_type:
            errors.append("%s has invalid candidate_type" % disposition_label)
        accepted_by = disposition.get("accepted_by")
        if (not isinstance(accepted_by, str) or
                not accepted_by.startswith("policy-exception:")):
            errors.append(
                "%s a compact attestation carries only policy-exception "
                "dispositions inline; ordinary dispositions live in the "
                "bound candidate evidence file" % disposition_label)
            continue
        decision_id = accepted_by.split(":", 1)[1]
        sealed = disposition.get("policy_exception")
        if not _nonempty_string(decision_id):
            errors.append("%s has empty policy-exception decision" %
                          disposition_label)
        elif not isinstance(sealed, dict):
            errors.append("%s policy-exception disposition seals no "
                          "decision facts" % disposition_label)
        else:
            errors.extend(_sealed_policy_exception_errors(
                sealed, decision_id, candidate_type, disposition_label))
    if receipt_version in CANDIDATE_CONTINUATION_VERSIONS:
        errors.extend(candidate_lifecycle.continuation_attestation_errors(
            attestation, label))
    return errors


def _page_review_acceptance_errors(
        catalog, aggregate, aggregate_id, *, item_id, task_id, manifest,
        integrator_id, reviewer_id, attestation_id, merged_snapshot_sha256,
        root=None, historical=False, selected_profile_manifest=None,
        profile_snapshot_sha256=None, profile_contract_fingerprint=None,
        profile_load_inputs_sha256=None,
        metadata_execution_contract_fingerprint=None,
        authorized_profile_contract=None,
        authorized_metadata_contract=None,
        authorized_page_semantic_fingerprints=None):
    """Validate the 1.11 exact per-page review-evidence subgraph.

    ``authorized_page_semantic_fingerprints`` is a same-transaction
    orchestration input, not persisted authority: the producer may pass the
    hashes it just computed from its frozen target snapshots and must still
    perform the final exact-byte/identity CAS.  Independent consumers omit it
    and this validator re-reads every current page before accepting the hash.
    """
    errors = []
    label = "%s batch-close gate receipt %s" % (item_id, aggregate_id)

    if (not isinstance(manifest, list) or
            any(not _nonempty_string(value) for value in manifest)):
        errors.append(
            "%s current page-review protocol requires an explicit manifest "
            "page-path list" % label)
        expected_targets = []
    else:
        expected_targets = sorted(manifest)
        if len(expected_targets) != len(set(expected_targets)):
            errors.append("%s manifest page paths must be unique" % label)
    expected_target_set = set(expected_targets)

    frozen_semantics = None
    if not historical and authorized_page_semantic_fingerprints is not None:
        if not isinstance(authorized_page_semantic_fingerprints, dict):
            errors.append(
                "%s authorized page semantic fingerprints must be a "
                "target-to-sha256 mapping" % label)
        else:
            supplied_targets = set(authorized_page_semantic_fingerprints)
            bad_values = sorted(
                target for target, value in
                authorized_page_semantic_fingerprints.items()
                if (not _nonempty_string(target) or
                    not isinstance(value, str) or
                    not SHA256_RE.fullmatch(value)))
            if supplied_targets != expected_target_set:
                errors.append(
                    "%s authorized page semantic fingerprint targets do not "
                    "equal the exact manifest" % label)
            if bad_values:
                errors.append(
                    "%s authorized page semantic fingerprints have invalid "
                    "values for: %s" % (label, ", ".join(bad_values)))
            if supplied_targets == expected_target_set and not bad_values:
                frozen_semantics = dict(
                    authorized_page_semantic_fingerprints)

    ids = aggregate.get("page_review_receipts")
    if (not isinstance(ids, list) or
            any(not _nonempty_string(value) for value in ids)):
        errors.append("%s page_review_receipts must be a string list" % label)
        ids = []
    elif ids != sorted(ids):
        errors.append("%s page_review_receipts must be sorted" % label)
    if len(ids) != len(set(ids)):
        errors.append("%s page_review_receipts must be unique" % label)
    reserved_receipt_ids = {
        value for value in (
            aggregate_id,
            aggregate.get("global_review_receipt"),
            aggregate.get("reviewer_attestation_receipt"),
            aggregate.get("queue_consistency_receipt"),
            aggregate.get("delta_apply_receipt"),
            aggregate.get("corpus_plan_receipt"),
        ) if _nonempty_string(value)
    }
    evidence = aggregate.get("closed_list_evidence")
    if isinstance(evidence, dict):
        reserved_receipt_ids.update(
            value for value in evidence.values()
            if _nonempty_string(value))
    overlaps = sorted(set(ids).intersection(reserved_receipt_ids))
    if overlaps:
        errors.append(
            "%s page review children must use receipt IDs distinct from "
            "the aggregate and its non-page evidence: %s" %
            (label, ", ".join(overlaps)))
    count = aggregate.get("page_review_receipt_count")
    if (not isinstance(count, int) or isinstance(count, bool) or
            count < 0 or count != len(ids)):
        errors.append(
            "%s page_review_receipt_count must equal the exact receipt list" %
            label)
    set_sha = aggregate.get("page_review_receipt_set_sha256")
    expected_set_sha = candidate_lifecycle.candidate_set_sha256(ids)
    if (not isinstance(set_sha, str) or not SHA256_RE.fullmatch(set_sha) or
            set_sha != expected_set_sha):
        errors.append(
            "%s page_review_receipt_set_sha256 does not bind the exact "
            "sorted receipt-ID set" % label)

    profile_bindings = {
        field: aggregate.get(field)
        for field in (
            "selected_profile_manifest", "profile_snapshot_sha256",
            "profile_contract_fingerprint", "profile_load_inputs_sha256")
    }
    expected_profile = {
        "selected_profile_manifest": selected_profile_manifest,
        "profile_snapshot_sha256": profile_snapshot_sha256,
        "profile_contract_fingerprint": profile_contract_fingerprint,
        "profile_load_inputs_sha256": profile_load_inputs_sha256,
    }
    live_profile_view = dict(profile_bindings)
    live_profile_view.update({
        field: value for field, value in expected_profile.items()
        if value is not None
    })
    metadata_fingerprint = aggregate.get(
        "metadata_execution_contract_fingerprint")

    projection_rules = None
    live_metadata_fingerprint = None
    if not historical:
        if root is None:
            errors.append(
                "%s current page-review validation requires repository root" %
                label)
        else:
            try:
                contract = authorized_metadata_contract
                if contract is None:
                    contract = metadata_execution_contract.\
                        load_metadata_execution_contract(root)
                elif not isinstance(
                        contract,
                        metadata_execution_contract.
                        CompiledMetadataExecutionContract):
                    raise ValueError(
                        "authorized metadata contract has the wrong type")
                live_metadata_fingerprint = contract.contract_fingerprint
                extension_gates = getattr(
                    authorized_profile_contract, "extension_gates", None)
                if extension_gates is None:
                    raise ValueError(
                        "no authorized typed Profile contract was supplied")
                if (getattr(authorized_profile_contract, "authorized", False)
                        is not True or
                        getattr(
                            authorized_profile_contract,
                            "manifest_repo_path", None) !=
                        profile_bindings["selected_profile_manifest"] or
                        getattr(
                            authorized_profile_contract,
                            "profile_contract_fingerprint", None) !=
                        profile_bindings["profile_contract_fingerprint"]):
                    raise ValueError(
                        "typed Profile contract does not match the exact "
                        "authorized fingerprint")
                projection_rules = metadata_property_state.\
                    profile_gate_projection_rules(
                        root, extension_gates, metadata_contract=contract,
                        authorized_profile_contract=
                            authorized_profile_contract)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(
                    "%s cannot authorize current metadata/Profile execution "
                    "context: %s" %
                    (label, exc))
    errors.extend(evidence_identity_errors(
        aggregate, label,
        use=(EVIDENCE_USE_TERMINAL_HISTORY if historical else
             EVIDENCE_USE_CURRENT_AUTHORIZATION),
        profile_view=live_profile_view,
        metadata_contract_fingerprint=live_metadata_fingerprint))

    targets = []
    for index, page_receipt_id in enumerate(ids):
        child_label = "%s page review child[%d]" % (item_id, index)
        child = _require_receipt(
            catalog, page_receipt_id, child_label, errors,
            expected={
                "tool": BATCH_CLOSE_TOOL,
                "tool_version": BATCH_CLOSE_TOOL_VERSION,
                "check": "page_review_acceptance",
                "result": "pass",
                "task_id": task_id,
                "batch_id": item_id,
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "reviewer_attestation_receipt": attestation_id,
                "merged_snapshot_sha256": merged_snapshot_sha256,
                "metadata_execution_contract_fingerprint":
                    metadata_fingerprint,
                **profile_bindings,
            },
        )
        if not isinstance(child, dict):
            continue
        target = child.get("target")
        if not _nonempty_string(target):
            errors.append("%s target must be a non-empty page path" %
                          child_label)
            continue
        targets.append(target)
        checked_at = _timestamp_value(child.get("checked_at"))
        reviewed_on = child.get("reviewed_on")
        if checked_at is None:
            errors.append("%s checked_at must be an RFC 3339 instant" %
                          child_label)
        expected_date = (checked_at.date().isoformat()
                         if checked_at is not None else None)
        try:
            parsed_date = datetime.date.fromisoformat(reviewed_on)
        except (TypeError, ValueError):
            parsed_date = None
        if parsed_date is None or reviewed_on != expected_date:
            errors.append(
                "%s reviewed_on must equal its own checked_at UTC date" %
                child_label)
        semantic = child.get("semantic_content_sha256")
        if not isinstance(semantic, str) or not SHA256_RE.fullmatch(semantic):
            errors.append(
                "%s semantic_content_sha256 must be a sha256 fingerprint" %
                child_label)
        if (not historical and root is not None and
                projection_rules is not None and
                target in expected_target_set):
            if frozen_semantics is not None:
                current_semantic = frozen_semantics[target]
            else:
                try:
                    page = kblib.repository_target_snapshot(
                        root, target, suffixes=".md", singly_linked=True)
                    if not page.exists:
                        raise ValueError("page does not exist")
                    current_semantic = \
                        project_page_state.semantic_content_fingerprint(
                            target, page.read_text(), projection_rules)
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("%s cannot re-read exact target: %s" %
                                  (child_label, exc))
                    current_semantic = None
            if (current_semantic is not None and
                    semantic != current_semantic):
                errors.append(
                    "%s semantic_content_sha256 does not match the "
                    "authorized current page content" % child_label)

    if sorted(targets) != expected_targets:
        errors.append(
            "%s page review child targets %r do not equal exact manifest %r" %
            (label, sorted(targets), expected_targets))
    elif len(targets) != len(set(targets)):
        errors.append("%s page review child targets must be unique" % label)
    return errors, ids


def close_gate_receipt_errors(catalog, receipt_id, *, item_id, task_id,
                              root=None,
                              queue_revision, queue_state_revision,
                              required_queue_sha256,
                              coverage_ledger_sha256,
                              progress_ledger_sha256, delta_sha256,
                              queue_consistency_receipt,
                              delta_apply_receipt,
                              work_spec_path=None,
                              work_spec_sha256=None,
                              manifest=None,
                              selected_profile_manifest=None,
                              profile_snapshot_sha256=None,
                              profile_contract_fingerprint=None,
                              profile_load_inputs_sha256=None,
                              metadata_execution_contract_fingerprint=None,
                              authorized_profile_contract=None,
                              authorized_metadata_contract=None,
                              authorized_page_semantic_fingerprints=None,
                              corpus_plan_required=None,
                              corpus_plan_triggers=None,
                              corpus_plan_expected_binding=None,
                              current_repository_snapshot_sha256=None,
                              historical=False):
    """Validate the independent merged-snapshot gate consumed by close.

    The gate is deliberately distinct from both the in-batch ``batch_gate``
    receipts and the K13/08 Queue consistency receipt.  It binds the exact
    post-apply/pre-close runtime bytes and the independently recomputed
    repository-content snapshot, then closes its producer era's K12/09 set
    with independently persisted evidence IDs.
    """
    errors = []
    label = "%s batch-close gate" % item_id
    # The producer version is validated separately below: a new close action
    # must use the current producer, while replay of a closed edge keeps the
    # finite protocol era whose shape its sealed bundle records.
    expected = {
        "tool": BATCH_CLOSE_TOOL,
        "check": "batch_close_gate",
        "target": item_id,
        "batch_id": item_id,
        "task_id": task_id,
        "queue_revision": queue_revision,
        "queue_state_revision": queue_state_revision,
        "required_queue_sha256": required_queue_sha256,
        "coverage_ledger_sha256": coverage_ledger_sha256,
        "progress_ledger_sha256": progress_ledger_sha256,
        "delta_sha256": delta_sha256,
        "queue_consistency_receipt": queue_consistency_receipt,
        "delta_apply_receipt": delta_apply_receipt,
    }
    receipt = _require_receipt(
        catalog, receipt_id, label, errors,
        expected=expected,
    )
    if receipt is None:
        return errors
    receipt_version = receipt.get("tool_version")
    allowed_versions = (SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS
                        if historical else
                        frozenset((BATCH_CLOSE_TOOL_VERSION,)))
    if receipt_version not in allowed_versions:
        protocol = ("historical producer era" if historical else
                    "current close action")
        errors.append(
            "%s receipt %s has unsupported tool_version=%r for %s; "
            "expected one of %s" % (
                label, receipt_id, receipt_version, protocol,
                sorted(allowed_versions))
        )
    if receipt_version == BATCH_CLOSE_TOOL_VERSION:
        errors.extend(_close_settlement_binding_errors(
            receipt, "%s receipt %s" % (label, receipt_id)))
    for field, value in (
            ("work_spec_path", work_spec_path),
            ("work_spec_sha256", work_spec_sha256)):
        if field not in receipt:
            errors.append(
                "%s receipt %s misses explicit %s" %
                (label, receipt_id, field)
            )
        elif receipt.get(field) != value:
            errors.append(
                "%s receipt %s has %s=%r, expected %r" %
                (label, receipt_id, field, receipt.get(field), value)
            )
    if (corpus_plan_required is not None and
            receipt.get("corpus_plan_required") != corpus_plan_required):
        errors.append(
            "%s receipt %s has corpus_plan_required=%r, expected %r" %
            (label, receipt_id, receipt.get("corpus_plan_required"),
             corpus_plan_required)
        )
    if (corpus_plan_triggers is not None and
            receipt.get("corpus_plan_triggers") != corpus_plan_triggers):
        errors.append(
            "%s receipt %s has corpus_plan_triggers=%r, expected %r" %
            (label, receipt_id, receipt.get("corpus_plan_triggers"),
             corpus_plan_triggers)
        )
    entry = catalog.get(receipt_id)
    if entry is not None and entry[0] == "<pending-write>":
        errors.append("%s receipt %s is not persisted in the repository" %
                      (label, receipt_id))

    merged_snapshot_sha256 = receipt.get("merged_snapshot_sha256")
    if (not isinstance(merged_snapshot_sha256, str) or
            not SHA256_RE.fullmatch(merged_snapshot_sha256)):
        errors.append("%s receipt %s merged_snapshot_sha256 must be a valid "
                      "sha256 fingerprint" % (label, receipt_id))
    elif (current_repository_snapshot_sha256 is not None and
          merged_snapshot_sha256 != current_repository_snapshot_sha256):
        errors.append(
            "%s receipt %s merged_snapshot_sha256=%r does not match the "
            "current repository snapshot %r" %
            (label, receipt_id, merged_snapshot_sha256,
             current_repository_snapshot_sha256)
        )

    actual_corpus_required = receipt.get("corpus_plan_required")
    actual_corpus_triggers = receipt.get("corpus_plan_triggers")
    corpus_receipt_id = receipt.get("corpus_plan_receipt")
    if not isinstance(actual_corpus_required, bool):
        errors.append(
            "%s receipt %s corpus_plan_required must be an explicit boolean" %
            (label, receipt_id))
    if (not isinstance(actual_corpus_triggers, list) or
            any(not _nonempty_string(value)
                for value in actual_corpus_triggers)):
        errors.append(
            "%s receipt %s corpus_plan_triggers must be an explicit string "
            "list" % (label, receipt_id))
        actual_corpus_triggers = []
    else:
        if actual_corpus_triggers != sorted(set(actual_corpus_triggers)):
            errors.append(
                "%s receipt %s corpus_plan_triggers must be unique and sorted" %
                (label, receipt_id))
        unsupported = sorted(
            set(actual_corpus_triggers) - CORPUS_PLAN_TRIGGERS)
        if unsupported:
            errors.append(
                "%s receipt %s has unsupported corpus-plan trigger(s): %s" %
                (label, receipt_id, ", ".join(unsupported)))
    if actual_corpus_required is False:
        if actual_corpus_triggers:
            errors.append(
                "%s receipt %s non-applicable corpus plan must use no "
                "triggers" % (label, receipt_id))
        if corpus_receipt_id is not None:
            errors.append(
                "%s receipt %s non-applicable corpus plan must use "
                "corpus_plan_receipt=null" % (label, receipt_id))
    elif actual_corpus_required is True:
        if not actual_corpus_triggers:
            errors.append(
                "%s receipt %s required corpus plan has no trigger" %
                (label, receipt_id))
        corpus_tool_version = CORPUS_PLAN_TOOL_VERSION
        if historical and receipt_version != BATCH_CLOSE_TOOL_VERSION:
            corpus_tool_version = \
                HISTORICAL_CORPUS_PLAN_TOOL_VERSIONS.get(receipt_version)
            if corpus_tool_version is None:
                errors.append(
                    "%s receipt %s has no registered historical Corpus "
                    "Planning child protocol for batch-close %r" %
                    (label, receipt_id, receipt_version))
        corpus_expected = {
            "tool": CORPUS_PLAN_TOOL,
            "tool_version": corpus_tool_version,
            "check": "corpus_plan",
            "result": "pass",
            "task_id": task_id,
            "queue_revision": queue_revision,
            "queue_state_revision": queue_state_revision,
            "required_queue_sha256": required_queue_sha256,
            "coverage_ledger_sha256": coverage_ledger_sha256,
            "progress_ledger_sha256": progress_ledger_sha256,
            "repository_snapshot_sha256": merged_snapshot_sha256,
        }
        if selected_profile_manifest is not None:
            corpus_expected.update({
                "target": selected_profile_manifest,
                "selected_profile_manifest": selected_profile_manifest,
            })
        corpus_receipt = _require_receipt(
            catalog, corpus_receipt_id,
            "%s Corpus Planning child" % item_id, errors,
            expected=corpus_expected,
        )
        if isinstance(corpus_receipt, dict):
            if corpus_plan_expected_binding is not None:
                if not isinstance(corpus_plan_expected_binding, dict):
                    errors.append(
                        "%s Corpus Planning expected binding must be a "
                        "mapping" % item_id)
                else:
                    for field, value in sorted(
                            corpus_plan_expected_binding.items()):
                        if (field not in corpus_receipt or
                                corpus_receipt.get(field) != value):
                            errors.append(
                                "%s Corpus Planning child %s has %s=%r, "
                                "expected current %r" % (
                                    item_id, corpus_receipt_id, field,
                                    corpus_receipt.get(field), value))
            applicability = corpus_receipt.get("corpus_plan_applicability")
            if applicability not in ("configured", "not-applicable"):
                errors.append(
                    "%s Corpus Planning child %s has invalid applicability %r" %
                    (item_id, corpus_receipt_id, applicability))
            if ("R13" in actual_corpus_triggers and
                    applicability != "configured"):
                errors.append(
                    "%s R13 close requires a configured Corpus Planning child" %
                    item_id)
            for path_field, sha_field in CORPUS_PLAN_PATH_SHA_FIELDS:
                path_value = corpus_receipt.get(path_field)
                sha_value = corpus_receipt.get(sha_field)
                always_required = path_field in (
                    "selected_profile_manifest", "corpus_planning_slot_path")
                configured_required = applicability == "configured"
                if always_required or configured_required:
                    if not _nonempty_string(path_value):
                        errors.append(
                            "%s Corpus Planning child %s lacks %s" %
                            (item_id, corpus_receipt_id, path_field))
                    if (not isinstance(sha_value, str) or
                            not SHA256_RE.fullmatch(sha_value)):
                        errors.append(
                            "%s Corpus Planning child %s has invalid %s" %
                            (item_id, corpus_receipt_id, sha_field))
                else:
                    if (path_field not in corpus_receipt or
                            sha_field not in corpus_receipt):
                        errors.append(
                            "%s inactive Corpus Planning child %s must "
                            "explicitly bind null %s/%s" % (
                                item_id, corpus_receipt_id, path_field,
                                sha_field))
                    elif path_value is not None or sha_value is not None:
                        errors.append(
                            "%s inactive Corpus Planning child %s must use "
                            "null %s/%s" % (
                                item_id, corpus_receipt_id, path_field,
                                sha_field))

    _require_receipt(
        catalog, queue_consistency_receipt,
        "%s Queue consistency snapshot" % item_id, errors,
        expected={
            "tool": TOOL,
            # K12/10 producer-era identity: a close bundle sealed under an
            # accounted era keeps the consistency snapshot its own runtime
            # produced; it is never re-judged against this checker's
            # current constant after an upgrade.
            "tool_version": ANY_PRODUCER_ERA_VERSION,
            "check": "required_queue",
            "queue_check_mode": "consistency",
            "repository_snapshot_sha256": merged_snapshot_sha256,
        },
    )

    global_review_id = receipt.get("global_review_receipt")
    global_review = _require_receipt(
        catalog, global_review_id, "%s global review" % item_id, errors,
        expected={
            "tool": BATCH_CLOSE_TOOL,
            "tool_version": receipt_version,
            "check": "batch_global_review",
            "target": item_id,
            "batch_id": item_id,
            "task_id": task_id,
            "merged_snapshot_sha256": merged_snapshot_sha256,
        },
    )

    integrator_id = receipt.get("integrator_id")
    reviewer_id = receipt.get("reviewer_id")
    for field, value in (("integrator_id", integrator_id),
                         ("reviewer_id", reviewer_id)):
        if not _nonempty_string(value):
            errors.append("%s receipt %s %s must be a non-empty declared label" %
                          (label, receipt_id, field))
    if (_nonempty_string(integrator_id) and _nonempty_string(reviewer_id) and
            integrator_id.casefold() == reviewer_id.casefold()):
        errors.append("%s receipt %s integrator and reviewer must use "
                      "different declared labels" % (label, receipt_id))

    attestation_id = receipt.get("reviewer_attestation_receipt")
    if isinstance(global_review, dict):
        for field, value in (("integrator_id", integrator_id),
                             ("reviewer_id", reviewer_id),
                             ("reviewer_attestation_receipt", attestation_id)):
            if global_review.get(field) != value:
                errors.append("%s global review receipt %s has %s=%r, "
                              "expected %r" %
                              (item_id, global_review_id, field,
                               global_review.get(field), value))
    attestation = _require_receipt(
        catalog, attestation_id, "%s declared reviewer attestation" %
        item_id, errors,
        expected={
            "tool": BATCH_CLOSE_TOOL,
            "tool_version": receipt_version,
            "check": "batch_global_review_attestation",
            "target": item_id,
            "batch_id": item_id,
            "task_id": task_id,
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "merged_snapshot_sha256": merged_snapshot_sha256,
        },
    )
    if (isinstance(attestation, dict) and
            receipt_version in COMPACT_CLOSE_EVIDENCE_VERSIONS):
        if not _nonempty_string(attestation.get("details")):
            errors.append("%s declared reviewer attestation %s has no "
                          "review statement" % (item_id, attestation_id))
        errors.extend(_compact_attestation_errors(
            attestation, attestation_id, item_id, root=root,
            receipt_version=receipt_version))
    elif isinstance(attestation, dict):
        if not _nonempty_string(attestation.get("details")):
            errors.append("%s declared reviewer attestation %s has no "
                          "review statement" % (item_id, attestation_id))
        accepted_ids = attestation.get("accepted_candidate_ids")
        accepted_types = attestation.get("accepted_candidate_types")
        dispositions = attestation.get("candidate_dispositions")
        if not isinstance(accepted_ids, list) or any(
                not _nonempty_string(value) for value in accepted_ids):
            errors.append("%s declared reviewer attestation %s "
                          "accepted_candidate_ids must be a string list" %
                          (item_id, attestation_id))
            accepted_ids = []
        if not isinstance(accepted_types, list) or any(
                not _nonempty_string(value) for value in accepted_types):
            errors.append("%s declared reviewer attestation %s "
                          "accepted_candidate_types must be a string list" %
                          (item_id, attestation_id))
            accepted_types = []
        if len(accepted_ids) != len(set(accepted_ids)):
            errors.append("%s declared reviewer attestation %s repeats an "
                          "accepted candidate ID" % (item_id, attestation_id))
        if len(accepted_types) != len(set(accepted_types)):
            errors.append("%s declared reviewer attestation %s repeats an "
                          "accepted candidate type" %
                          (item_id, attestation_id))
        if not isinstance(dispositions, list):
            errors.append("%s declared reviewer attestation %s "
                          "candidate_dispositions must be a list" %
                          (item_id, attestation_id))
            dispositions = []
        disposition_ids = []
        disposition_types = []
        for index, disposition in enumerate(dispositions):
            disposition_label = "%s candidate_dispositions[%d]" % (
                item_id, index)
            if not isinstance(disposition, dict):
                errors.append("%s must be a mapping" % disposition_label)
                continue
            candidate_id = disposition.get("candidate_id")
            candidate_type = disposition.get("candidate_type")
            if (not _nonempty_string(candidate_id) or
                    not candidate_id.startswith("candidate-sha256:") or
                    not SHA256_RE.fullmatch(candidate_id.replace(
                        "candidate-sha256:", "sha256:", 1))):
                errors.append("%s has invalid stable candidate_id" %
                              disposition_label)
            else:
                disposition_ids.append(candidate_id)
            if (not _nonempty_string(candidate_type) or
                    ":" not in candidate_type):
                errors.append("%s has invalid candidate_type" %
                              disposition_label)
            else:
                disposition_types.append(candidate_type)
            accepted_by = disposition.get("accepted_by")
            if isinstance(accepted_by, str) and accepted_by.startswith(
                    "policy-exception:"):
                # K00/07: a priority-quota excess is consumed only through a
                # bounded contract exception.  The disposition seals the
                # decision facts so this receipt replays as history even
                # after the exception is revoked or the task ends; replay
                # validates the sealed record, never current contract state.
                decision_id = accepted_by.split(":", 1)[1]
                if receipt_version not in \
                        POLICY_EXCEPTION_DISPOSITION_VERSIONS:
                    errors.append(
                        "%s claims a policy-exception disposition, but its "
                        "producer era %s predates that protocol; an older "
                        "bundle cannot carry evidence its era could not "
                        "have produced" % (disposition_label,
                                           receipt_version))
                sealed = disposition.get("policy_exception")
                if not _nonempty_string(decision_id):
                    errors.append("%s has empty policy-exception decision" %
                                  disposition_label)
                elif not isinstance(sealed, dict):
                    errors.append(
                        "%s policy-exception disposition seals no decision "
                        "facts" % disposition_label)
                else:
                    errors.extend(_sealed_policy_exception_errors(
                        sealed, decision_id, candidate_type,
                        disposition_label))
            elif accepted_by not in ("candidate-id", "candidate-type"):
                errors.append("%s has invalid accepted_by" %
                              disposition_label)
        if sorted(disposition_ids) != sorted(accepted_ids):
            errors.append("%s declared reviewer attestation %s accepted "
                          "candidate IDs do not equal its dispositions" %
                          (item_id, attestation_id))
        if sorted(set(disposition_types)) != sorted(accepted_types):
            errors.append("%s declared reviewer attestation %s accepted "
                          "candidate types do not equal its dispositions" %
                          (item_id, attestation_id))

    page_review_ids = []
    if receipt_version == BATCH_CLOSE_TOOL_VERSION:
        page_review_errors, page_review_ids = \
            _page_review_acceptance_errors(
                catalog, receipt, receipt_id,
                item_id=item_id, task_id=task_id, manifest=manifest,
                integrator_id=integrator_id, reviewer_id=reviewer_id,
                attestation_id=attestation_id,
                merged_snapshot_sha256=merged_snapshot_sha256,
                root=root, historical=historical,
                selected_profile_manifest=selected_profile_manifest,
                profile_snapshot_sha256=profile_snapshot_sha256,
                profile_contract_fingerprint=profile_contract_fingerprint,
                profile_load_inputs_sha256=profile_load_inputs_sha256,
                metadata_execution_contract_fingerprint=
                    metadata_execution_contract_fingerprint,
                authorized_profile_contract=authorized_profile_contract,
                authorized_metadata_contract=authorized_metadata_contract,
                authorized_page_semantic_fingerprints=
                    authorized_page_semantic_fingerprints,
            )
        errors.extend(page_review_errors)

    evidence = receipt.get("closed_list_evidence")
    # The Closed List a bundle answers to is the one its producer era ran:
    # a pre-1.5.0 bundle carries seven members forever (K12/10 producer-era
    # identity), a current bundle carries the full list.
    era_fields = (LEGACY_CLOSED_LIST_EVIDENCE_FIELDS
                  if receipt_version in LEGACY_CLOSED_LIST_VERSIONS
                  else CLOSED_LIST_EVIDENCE_FIELDS)
    expected_fields = set(era_fields)
    if not isinstance(evidence, dict):
        errors.append("%s receipt %s closed_list_evidence must be a mapping" %
                      (label, receipt_id))
        return errors
    missing = sorted(expected_fields - set(evidence))
    extra = sorted(set(evidence) - expected_fields)
    if missing:
        errors.append("%s receipt %s closed_list_evidence misses: %s" %
                      (label, receipt_id, ", ".join(missing)))
    if extra:
        errors.append("%s receipt %s closed_list_evidence has unsupported "
                      "member(s): %s" %
                      (label, receipt_id, ", ".join(extra)))
    evidence_ids = []
    for field in era_fields:
        evidence_id = evidence.get(field)
        if not _nonempty_string(evidence_id):
            errors.append("%s receipt %s closed_list_evidence.%s must identify "
                          "a receipt" % (label, receipt_id, field))
            continue
        evidence_ids.append(evidence_id)
        _require_receipt(
            catalog, evidence_id,
            "%s Closed List member %s" % (item_id, field), errors,
            expected={
                "tool": BATCH_CLOSE_TOOL,
                "tool_version": receipt_version,
                "check": "closed_list_%s" % field,
                "target": ".",
                "batch_id": item_id,
                "task_id": task_id,
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "merged_snapshot_sha256": merged_snapshot_sha256,
            },
        )
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("%s receipt %s closed_list_evidence must use one "
                      "distinct receipt ID per Closed List member" %
                      (label, receipt_id))
    if receipt_id in evidence_ids:
        errors.append("%s receipt %s cannot cite itself as Closed List "
                      "evidence" % (label, receipt_id))
    if global_review_id in evidence_ids or global_review_id == receipt_id:
        errors.append("%s receipt %s global_review_receipt must be a distinct "
                      "record from the aggregator and the Closed List members" %
                      (label, receipt_id))
    if attestation_id in evidence_ids or attestation_id in (
            global_review_id, receipt_id):
        errors.append("%s receipt %s reviewer attestation must be a distinct "
                      "record from the aggregator, global review, and the Closed "
                      "List members" % (label, receipt_id))
    if page_review_ids:
        reserved = set(evidence_ids + [
            receipt_id, global_review_id, attestation_id,
            queue_consistency_receipt, delta_apply_receipt,
        ])
        if corpus_receipt_id is not None:
            reserved.add(corpus_receipt_id)
        reused = sorted(set(page_review_ids).intersection(reserved))
        if reused:
            errors.append(
                "%s receipt %s page-review children must be distinct from "
                "the aggregator and every other close-evidence record: %s" %
                (label, receipt_id, ", ".join(reused)))
    if (isinstance(global_review, dict) and
            global_review.get("closed_list_evidence") != evidence):
        errors.append("%s global review receipt %s does not bind the same "
                      "Closed List evidence mapping" %
                      (item_id, global_review_id))
    if corpus_receipt_id is not None and corpus_receipt_id in (
            evidence_ids + [receipt_id, global_review_id, attestation_id,
                            queue_consistency_receipt, delta_apply_receipt]):
        errors.append(
            "%s receipt %s Corpus Planning child must be distinct from the "
            "aggregator and all other close evidence" % (label, receipt_id))
    return errors




def _maintenance_evidence_receipt(root, result, receipt_id, label,
                                  expected, path_field, sha_field, errors):
    """Validate one current maintenance input and its persisted receipt."""
    receipt = _require_receipt(
        result.get("receipt_catalog", {}), receipt_id, label, errors,
        expected=expected,
    )
    if receipt is None:
        return None
    for field in ("tool", "tool_version"):
        if not _nonempty_string(receipt.get(field)):
            errors.append("%s receipt %s has invalid %s" %
                          (label, receipt_id, field))
    if not _valid_timestamp(receipt.get("checked_at")):
        errors.append("%s receipt %s has invalid checked_at" %
                      (label, receipt_id))
    relative_path = receipt.get(path_field)
    fingerprint = receipt.get(sha_field)
    if not _nonempty_string(relative_path):
        errors.append("%s receipt %s lacks %s" %
                      (label, receipt_id, path_field))
        return receipt
    if receipt.get("target") != relative_path:
        errors.append("%s receipt %s target must equal %s" %
                      (label, receipt_id, path_field))
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
        errors.append("%s receipt %s has invalid %s" %
                      (label, receipt_id, sha_field))
        return receipt
    absolute = _repository_evidence_file(
        root, relative_path, "%s %s" % (label, path_field), errors,
    )
    if absolute is not None and kblib.sha256_file(absolute) != fingerprint:
        errors.append("%s receipt %s does not bind current %s bytes" %
                      (label, receipt_id, path_field))
    return receipt


def _canonical_maintenance_completion_consumers(result, gate_id, gate,
                                                 errors):
    """Return persisted canonical task completions that consume ``gate_id``.

    Historical candidate ageing cannot trust a receipt merely because it says
    ``after_task_state: complete``.  Apply the same history-independent task
    transition contract used for the live Progress chain, then bind every
    pre-transition fingerprint to the maintenance gate it consumes.
    """
    catalog = result.get("receipt_catalog") or {}
    consumers = []
    for consumer_id, (relative, candidate) in sorted(catalog.items()):
        if not isinstance(candidate, dict):
            continue
        if not (candidate.get("tool") == "update_task" and
                candidate.get("check") == "task_transition" and
                candidate.get("evidence_receipt") == gate_id):
            continue
        local_errors = []
        consumer = _require_receipt(
            catalog, consumer_id,
            "maintenance gate %s task completion" % gate_id, local_errors,
            expected={
                "tool": "update_task",
                "tool_version": "1.1.0",
                "check": "task_transition",
                "target": gate.get("task_id"),
                "task_id": gate.get("task_id"),
                "actor_role": "integrator",
                "completion_semantics": "maintenance",
                "after_task_state": "complete",
                "evidence_receipt": gate_id,
            },
        )
        if relative == "<pending-write>":
            local_errors.append(
                "maintenance gate %s task completion %s is not persisted" %
                (gate_id, consumer_id)
            )
        if consumer is not None:
            local_errors.extend(_task_transition_receipt_record_errors(
                catalog, consumer_id, consumer, "maintenance",
                expected_contract_sha=gate.get("contract_sha256"),
            ))
            before = consumer.get("before_task_state")
            if consumer.get("details") != "%s -> complete" % before:
                local_errors.append(
                    "maintenance gate %s task completion %s has non-canonical "
                    "details" % (gate_id, consumer_id)
                )
            for consumer_field, gate_field in (
                    ("queue_revision", "queue_revision"),
                    ("queue_state_revision", "queue_state_revision"),
                    ("before_coverage_sha256", "coverage_ledger_sha256"),
                    ("after_coverage_sha256", "coverage_ledger_sha256"),
                    ("before_required_queue_sha256",
                     "required_queue_sha256"),
                    ("after_required_queue_sha256",
                     "required_queue_sha256"),
                    ("before_progress_sha256", "progress_ledger_sha256")):
                if consumer.get(consumer_field) != gate.get(gate_field):
                    local_errors.append(
                        "maintenance gate %s task completion %s does not bind "
                        "%s" % (gate_id, consumer_id, consumer_field)
                    )
            gate_time = _timestamp_value(gate.get("checked_at"))
            consumer_time = _timestamp_value(consumer.get("checked_at"))
            if (gate_time is not None and consumer_time is not None and
                    consumer_time < gate_time):
                local_errors.append(
                    "maintenance gate %s task completion predates its gate" %
                    gate_id
                )
        if local_errors:
            errors.extend(local_errors)
        else:
            consumers.append((consumer_id, consumer))
    return consumers


def _latest_consumed_maintenance_gate(root, result, contract,
                                      *, current_task_id,
                                      current_maintenance_run_id, errors):
    """Select the one immediate predecessor across matching maintenance runs.

    Ordering is by the durable task-completion instant, then gate instant and
    receipt ID.  A later task therefore cannot reset candidate age by writing
    ``previous_maintenance_completion_receipt: null`` or by naming an older
    consumed gate.
    """
    eligible = []
    catalog = result.get("receipt_catalog") or {}
    for gate_id, (relative, gate) in sorted(catalog.items()):
        if not isinstance(gate, dict):
            continue
        if not (gate.get("tool") == TOOL and
                gate.get("tool_version") in
                SUPPORTED_CHECK_QUEUE_TOOL_VERSIONS and
                gate.get("check") == "required_queue" and
                gate.get("queue_check_mode") ==
                "require-maintenance-complete" and
                gate.get("result") == "pass" and
                gate.get("invalidated_by") is None and
                gate.get("completion_semantics") == "maintenance" and
                gate.get("standards_version") ==
                contract.get("standards_version") and
                gate.get("selected_profile_manifest") ==
                contract.get("selected_profile_manifest")):
            continue
        if gate.get("task_id") == current_task_id:
            continue
        if (_nonempty_string(current_maintenance_run_id) and
                gate.get("maintenance_run_id") ==
                current_maintenance_run_id):
            errors.append(
                "maintenance run_id %s was already used by prior task %s" %
                (current_maintenance_run_id, gate.get("task_id"))
            )
            continue
        claims = [
            candidate for _, candidate in catalog.values()
            if isinstance(candidate, dict) and
            candidate.get("tool") == "update_task" and
            candidate.get("check") == "task_transition" and
            candidate.get("evidence_receipt") == gate_id
        ]
        if not claims:
            continue
        local_errors = []
        if relative == "<pending-write>":
            local_errors.append(
                "consumed maintenance gate %s is not persisted" % gate_id
            )
        for field in ("task_id", "maintenance_run_id", "scope_version"):
            if not _nonempty_string(gate.get(field)):
                local_errors.append(
                    "consumed maintenance gate %s lacks %s" %
                    (gate_id, field)
                )
        for field in (
                "required_queue_sha256", "coverage_ledger_sha256",
                "progress_ledger_sha256",
                "contract_sha256",
                "maintenance_candidate_state_sha256"):
            value = gate.get(field)
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                local_errors.append(
                    "consumed maintenance gate %s has invalid %s" %
                    (gate_id, field)
                )
        for field, minimum in (("queue_revision", 1),
                               ("queue_state_revision", 0)):
            value = gate.get(field)
            if (not isinstance(value, int) or isinstance(value, bool) or
                    value < minimum):
                local_errors.append(
                    "consumed maintenance gate %s has invalid %s" %
                    (gate_id, field)
                )
        if gate.get("remaining_required_work_units") != 0:
            local_errors.append(
                "consumed maintenance gate %s must bind zero remaining work" %
                gate_id
            )
        if not _valid_timestamp(gate.get("checked_at")):
            local_errors.append(
                "consumed maintenance gate %s has invalid checked_at" % gate_id
            )
        records = gate.get("maintenance_candidate_states")
        candidate_errors, context = maintenance_candidates.validate_candidates(
            root, records, validate_prior=False,
            label="consumed maintenance gate %s candidate states" % gate_id,
        )
        local_errors.extend(candidate_errors)
        for field, expected in (
                ("maintenance_candidate_state_sha256",
                 context["candidate_state_sha256"]),
                ("selected_candidate_ids", context["selected_ids"]),
                ("deferred_candidate_ids", context["deferred_ids"])):
            if gate.get(field) != expected:
                local_errors.append(
                    "consumed maintenance gate %s does not bind %s" %
                    (gate_id, field)
                )
        consumers = _canonical_maintenance_completion_consumers(
            result, gate_id, gate, local_errors,
        )
        if len(consumers) != 1:
            local_errors.append(
                "consumed maintenance gate %s must have exactly one canonical "
                "persisted task completion; found %d" %
                (gate_id, len(consumers))
            )
        if local_errors:
            errors.extend(local_errors)
            continue
        consumer_id, consumer = consumers[0]
        eligible.append((
            _timestamp_value(consumer.get("checked_at")),
            _timestamp_value(gate.get("checked_at")), gate_id,
            consumer_id,
        ))
    eligible.sort()
    return eligible[-1][2] if eligible else None


def _previous_maintenance_candidate_state(root, result, receipt_id,
                                          contract, errors):
    """Resolve the prior run's candidate projection from a persisted gate."""
    if receipt_id is None:
        return None, [], maintenance_candidates.candidate_state_sha256([])
    receipt = _require_receipt(
        result.get("receipt_catalog", {}), receipt_id,
        "previous maintenance completion", errors,
        expected={
            "tool": TOOL,
            "tool_version": ANY_PRODUCER_ERA_VERSION,
            "check": "required_queue",
            "target": QUEUE_PATH,
            "queue_check_mode": "require-maintenance-complete",
            "completion_semantics": "maintenance",
            "standards_version": contract.get("standards_version"),
            "selected_profile_manifest": contract.get(
                "selected_profile_manifest"),
            "remaining_required_work_units": 0,
        },
    )
    if receipt is None:
        return None, [], None
    if receipt.get("tool_version") not in SUPPORTED_CHECK_QUEUE_TOOL_VERSIONS:
        errors.append(
            "previous maintenance completion receipt %s has unsupported "
            "check_queue producer version %r" %
            (receipt_id, receipt.get("tool_version")))
    entry = (result.get("receipt_catalog") or {}).get(receipt_id)
    if entry is not None and entry[0] == "<pending-write>":
        errors.append(
            "previous maintenance completion receipt %s is not persisted" %
            receipt_id
        )
    records = receipt.get("maintenance_candidate_states")
    if not isinstance(records, list):
        errors.append(
            "previous maintenance completion receipt %s lacks an explicit "
            "maintenance_candidate_states list" % receipt_id
        )
        records = []
    prior_errors, prior_context = maintenance_candidates.validate_candidates(
        root, records, validate_prior=False,
        label="previous maintenance candidate states",
    )
    errors.extend(prior_errors)
    if not _nonempty_string(receipt.get("maintenance_run_id")):
        errors.append(
            "previous maintenance completion receipt %s lacks "
            "maintenance_run_id" % receipt_id
        )
    for field, expected in (
            ("selected_candidate_ids", prior_context["selected_ids"]),
            ("deferred_candidate_ids", prior_context["deferred_ids"])):
        if receipt.get(field) != expected:
            errors.append(
                "previous maintenance completion receipt %s has %s=%r, "
                "expected %r" %
                (receipt_id, field, receipt.get(field), expected)
            )
    fingerprint = receipt.get("maintenance_candidate_state_sha256")
    if (not isinstance(fingerprint, str) or
            not SHA256_RE.fullmatch(fingerprint)):
        errors.append(
            "previous maintenance completion receipt %s has invalid "
            "maintenance_candidate_state_sha256" % receipt_id
        )
    elif fingerprint != prior_context["candidate_state_sha256"]:
        errors.append(
            "previous maintenance completion receipt %s candidate-state "
            "fingerprint does not bind its projection" % receipt_id
        )
    if not _valid_timestamp(receipt.get("checked_at")):
        errors.append(
            "previous maintenance completion receipt %s has invalid checked_at" %
            receipt_id
        )
    consumers = _canonical_maintenance_completion_consumers(
        result, receipt_id, receipt, errors,
    )
    if len(consumers) != 1:
        errors.append(
            "previous maintenance completion receipt %s must be consumed by "
            "exactly one persisted maintenance task completion; found %d" %
            (receipt_id, len(consumers))
        )
    elif (_timestamp_value(consumers[0][1].get("checked_at")) is None or
          (_timestamp_value(receipt.get("checked_at")) is not None and
           _timestamp_value(consumers[0][1].get("checked_at")) <
           _timestamp_value(receipt.get("checked_at")))):
        errors.append(
            "previous maintenance task completion predates its gate receipt"
        )
    return receipt, records, fingerprint


def _maintenance_completion_gate_errors(root, result,
                                        budget_manifest_receipt,
                                        ledger_advance_receipt,
                                        watermark_advance_receipt,
                                        *, allow_complete=False):
    """Prove one bounded maintenance run against current canonical state."""
    errors = []
    progress = result.get("progress") or {}
    contract = (progress.get("contract")
                if isinstance(progress.get("contract"), dict) else {})
    queue = result.get("queue") or {}
    task_id = queue.get("task_id")
    if contract.get("completion_semantics") != "maintenance":
        errors.append(
            "--require-maintenance-complete requires "
            "contract.completion_semantics=maintenance"
        )
    allowed_states = (("planned", "active", "complete")
                      if allow_complete else ("planned", "active"))
    if progress.get("task_state") not in allowed_states:
        errors.append(
            "maintenance completion gate requires task_state=planned or active"
        )
    pending_guidance, pending_amendments = _pending_control_ids(progress)
    if pending_guidance or pending_amendments:
        errors.append(
            "maintenance completion gate requires reconciled Guidance/"
            "Amendments; pending guidance=%s amendments=%s" %
            (",".join(pending_guidance) or "none",
             ",".join(pending_amendments) or "none")
        )
    items = result.get("items_by_id") or {}
    if not items:
        errors.append("an empty Queue cannot prove maintenance completion")
    nonterminal = sorted(
        item_id for item_id, item in items.items()
        if item.get("state") not in TERMINAL_STATES
    )
    queue_batch_ids = [
        item.get("id") for item in sorted(
            items.values(), key=lambda value: value.get("order", 0))
    ]
    if result.get("remaining") != 0 or nonterminal:
        errors.append(
            "maintenance completion requires zero remaining Required work; "
            "remaining=%s nonterminal=%s" %
            (result.get("remaining"), ",".join(nonterminal) or "none")
        )

    common = {
        "task_id": task_id,
        "scope_version": contract.get("scope_version"),
        "standards_version": contract.get("standards_version"),
        "selected_profile_manifest":
            contract.get("selected_profile_manifest"),
    }
    budget = _maintenance_evidence_receipt(
        root, result, budget_manifest_receipt, "maintenance budget manifest",
        dict(common, check="maintenance_budget_manifest",
             budget_manifest_state="closed", manifest_open_items=0),
        "budget_manifest_path", "budget_manifest_sha256", errors,
    )
    ledger = _maintenance_evidence_receipt(
        root, result, ledger_advance_receipt, "maintenance Ledger advance",
        dict(common, check="maintenance_ledger_advanced", advanced=True,
             coverage_ledger_path=COVERAGE_PATH,
             after_coverage_sha256=result.get("coverage_sha256"),
             coverage_updated_at=(result.get("coverage") or {}).get(
                 "updated_at")),
        "coverage_ledger_path", "after_coverage_sha256", errors,
    )
    watermark = _maintenance_evidence_receipt(
        root, result, watermark_advance_receipt,
        "maintenance watermark advance",
        dict(common, check="maintenance_watermark_advanced", advanced=True),
        "watermark_path", "after_watermark_sha256", errors,
    )

    manifest = None
    candidate_context = {
        "records": [],
        "selected_ids": [],
        "deferred_ids": [],
        "selected_objects": [],
        "candidate_state_sha256":
            maintenance_candidates.candidate_state_sha256([]),
    }
    previous_candidate_receipt = None
    previous_candidate_sha = maintenance_candidates.candidate_state_sha256([])
    maintenance_run_id = None
    previous_completion_id = None
    if budget is not None and _nonempty_string(
            budget.get("budget_manifest_path")):
        absolute = _repository_evidence_file(
            root, budget["budget_manifest_path"],
            "maintenance budget manifest", errors,
        )
        if absolute is not None:
            try:
                manifest = kblib.load_yaml_file(absolute)
            except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
                errors.append(
                    "maintenance budget manifest is not parseable: %s" % exc
                )
                manifest = None
            if isinstance(manifest, dict):
                manifest_fields = frozenset((
                    "schema_version", "task_id", "run_id", "scope_version",
                    "standards_version", "selected_profile_manifest",
                    "previous_maintenance_completion_receipt",
                    "budget_unit", "budget_limit", "consumed_hours",
                    "candidates", "selected_candidate_ids",
                    "deferred_candidate_ids", "selected_objects",
                    "required_batch_ids", "deferred_count",
                    "open_items", "state", "closed_at",
                ))
                errors.extend(_closed_mapping_errors(
                    manifest, "maintenance budget manifest", manifest_fields,
                ))
                for field, expected in common.items():
                    if manifest.get(field) != expected:
                        errors.append(
                            "maintenance budget manifest %s=%r, expected %r" %
                            (field, manifest.get(field), expected)
                        )
                if manifest.get("schema_version") != 2:
                    errors.append(
                        "maintenance budget manifest schema_version must be 2"
                    )
                maintenance_run_id = manifest.get("run_id")
                if not _nonempty_string(maintenance_run_id):
                    errors.append(
                        "maintenance budget manifest run_id must be a "
                        "non-empty string"
                    )
                previous_completion_id = manifest.get(
                    "previous_maintenance_completion_receipt")
                if (previous_completion_id is not None and
                        not _nonempty_string(previous_completion_id)):
                    errors.append(
                        "maintenance budget manifest "
                        "previous_maintenance_completion_receipt must be null "
                        "or a non-empty receipt ID"
                    )
                expected_previous_completion_id = \
                    _latest_consumed_maintenance_gate(
                        root, result, contract,
                        current_task_id=task_id,
                        current_maintenance_run_id=maintenance_run_id,
                        errors=errors,
                    )
                if previous_completion_id != expected_previous_completion_id:
                    errors.append(
                        "maintenance budget manifest must name the latest "
                        "consumed maintenance gate as "
                        "previous_maintenance_completion_receipt; found %r, "
                        "expected %r" %
                        (previous_completion_id,
                         expected_previous_completion_id)
                    )
                (previous_candidate_receipt, previous_candidates,
                 previous_candidate_sha) = \
                    _previous_maintenance_candidate_state(
                        root, result, previous_completion_id, contract, errors,
                    )
                candidate_errors, candidate_context = \
                    maintenance_candidates.validate_candidates(
                        root, manifest.get("candidates"),
                        previous_candidates=previous_candidates,
                        label="maintenance budget manifest candidates",
                    )
                errors.extend(candidate_errors)
                errors.extend(maintenance_candidates.validate_partition(
                    manifest, candidate_context,
                    queue_items=list(items.values()),
                    coverage_candidates=(result.get("coverage") or {}).get(
                        "maintenance_candidates"),
                    coverage_pages=(result.get("coverage") or {}).get("pages"),
                ))
                for field, expected in (
                        ("maintenance_run_id", maintenance_run_id),
                        ("previous_maintenance_completion_receipt",
                         previous_completion_id),
                        ("maintenance_candidate_state_sha256",
                         candidate_context["candidate_state_sha256"]),
                        ("selected_candidate_ids",
                         candidate_context["selected_ids"]),
                        ("deferred_candidate_ids",
                         candidate_context["deferred_ids"])):
                    if budget.get(field) != expected:
                        errors.append(
                            "maintenance budget receipt does not bind %s" %
                            field
                        )
                if previous_candidate_receipt is not None:
                    if previous_candidate_receipt.get(
                            "maintenance_run_id") == maintenance_run_id:
                        errors.append(
                            "maintenance run_id must differ from its prior run"
                        )
                    prior_instant = _timestamp_value(
                        previous_candidate_receipt.get("checked_at"))
                    closed_instant = _timestamp_value(manifest.get("closed_at"))
                    if (prior_instant is not None and
                            closed_instant is not None and
                            prior_instant > closed_instant):
                        errors.append(
                            "previous maintenance completion receipt postdates "
                            "the current manifest closure"
                        )
                budget_unit = manifest.get("budget_unit")
                if budget_unit not in ("pages", "batches", "hours"):
                    errors.append(
                        "maintenance budget manifest budget_unit must be pages, "
                        "batches, or hours"
                    )
                budget_limit = manifest.get("budget_limit")
                if budget_unit == "hours":
                    if (not isinstance(budget_limit, (int, float)) or
                            isinstance(budget_limit, bool) or
                            budget_limit <= 0):
                        errors.append(
                            "maintenance budget manifest budget_limit must be "
                            "a number > 0 for hours"
                        )
                elif (not isinstance(budget_limit, int) or
                      isinstance(budget_limit, bool) or budget_limit < 1):
                    errors.append(
                        "maintenance budget manifest budget_limit must be an "
                        "integer >= 1 for pages or batches"
                    )
                for field, minimum in (("deferred_count", 0),
                                       ("open_items", 0)):
                    value = manifest.get(field)
                    if (not isinstance(value, int) or isinstance(value, bool) or
                            value < minimum):
                        errors.append(
                            "maintenance budget manifest %s must be an integer "
                            ">= %d" % (field, minimum)
                        )
                expected_objects = candidate_context["selected_objects"]
                expected_batches = [
                    item.get("id") for item in sorted(
                        items.values(), key=lambda value: value.get("order", 0))
                ]
                consumed_hours = manifest.get("consumed_hours")
                if budget_unit == "pages":
                    if consumed_hours is not None:
                        errors.append(
                            "maintenance budget manifest consumed_hours must "
                            "be null unless budget_unit=hours"
                        )
                    if (isinstance(budget_limit, int) and
                            not isinstance(budget_limit, bool) and
                            len(expected_objects) > budget_limit):
                        errors.append(
                            "maintenance budget manifest selects %d pages, "
                            "exceeding budget_limit %d" %
                            (len(expected_objects), budget_limit)
                        )
                elif budget_unit == "batches":
                    if consumed_hours is not None:
                        errors.append(
                            "maintenance budget manifest consumed_hours must "
                            "be null unless budget_unit=hours"
                        )
                    if (isinstance(budget_limit, int) and
                            not isinstance(budget_limit, bool) and
                            len(expected_batches) > budget_limit):
                        errors.append(
                            "maintenance budget manifest selects %d batches, "
                            "exceeding budget_limit %d" %
                            (len(expected_batches), budget_limit)
                        )
                elif budget_unit == "hours":
                    if (not isinstance(consumed_hours, (int, float)) or
                            isinstance(consumed_hours, bool) or
                            consumed_hours < 0):
                        errors.append(
                            "maintenance budget manifest consumed_hours must "
                            "be a number >= 0 for an hours budget"
                        )
                    elif (isinstance(budget_limit, (int, float)) and
                          not isinstance(budget_limit, bool) and
                          consumed_hours > budget_limit):
                        errors.append(
                            "maintenance budget manifest consumed_hours %s "
                            "exceeds budget_limit %s" %
                            (consumed_hours, budget_limit)
                        )
                if manifest.get("state") != "closed":
                    errors.append(
                        "maintenance budget manifest state must be closed"
                    )
                if manifest.get("open_items") != 0:
                    errors.append(
                        "maintenance budget manifest open_items must be 0"
                    )
                if not _valid_timestamp(manifest.get("closed_at")):
                    errors.append(
                        "maintenance budget manifest closed_at is invalid"
                    )
                if budget.get("budget_manifest_closed_at") != manifest.get(
                        "closed_at"):
                    errors.append(
                        "maintenance budget receipt does not bind manifest "
                        "closed_at"
                    )
                closed_instant = _timestamp_value(manifest.get("closed_at"))
                receipt_instant = _timestamp_value(budget.get("checked_at"))
                if (closed_instant is not None and
                        receipt_instant is not None and
                        closed_instant > receipt_instant):
                    errors.append(
                        "maintenance budget receipt predates manifest closure"
                    )

    if ledger is not None:
        for field, expected in (
                ("maintenance_run_id", maintenance_run_id),
                ("previous_maintenance_completion_receipt",
                 previous_completion_id),
                ("before_maintenance_candidate_state_sha256",
                 previous_candidate_sha),
                ("after_maintenance_candidate_state_sha256",
                 candidate_context["candidate_state_sha256"])):
            if ledger.get(field) != expected:
                errors.append(
                    "maintenance Ledger receipt does not bind %s" % field
                )

    if watermark is not None and _nonempty_string(
            watermark.get("watermark_path")):
        if watermark.get("maintenance_run_id") != maintenance_run_id:
            errors.append(
                "maintenance watermark receipt does not bind maintenance_run_id"
            )
        absolute = _repository_evidence_file(
            root, watermark["watermark_path"],
            "maintenance watermark", errors,
        )
        if absolute is not None:
            try:
                watermark_state = kblib.load_yaml_file(absolute)
            except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
                errors.append("maintenance watermark is not parseable: %s" % exc)
                watermark_state = None
            if isinstance(watermark_state, dict):
                if not _valid_timestamp(watermark_state.get("updated_at")):
                    errors.append("maintenance watermark updated_at is invalid")
                if not _nonempty_string(watermark_state.get("last_run_id")):
                    errors.append("maintenance watermark last_run_id is invalid")
                if not _nonempty_string(watermark_state.get("last_batch_id")):
                    errors.append(
                        "maintenance watermark last_batch_id is invalid"
                    )
                if watermark.get("watermark_updated_at") != \
                        watermark_state.get("updated_at"):
                    errors.append(
                        "maintenance watermark receipt does not bind updated_at"
                    )
                if watermark.get("watermark_run_id") != \
                        watermark_state.get("last_run_id"):
                    errors.append(
                        "maintenance watermark receipt does not bind last_run_id"
                    )
                if watermark.get("watermark_batch_id") != \
                        watermark_state.get("last_batch_id"):
                    errors.append(
                        "maintenance watermark receipt does not bind "
                        "last_batch_id"
                    )
                if watermark_state.get("last_run_id") != maintenance_run_id:
                    errors.append(
                        "maintenance watermark last_run_id differs from the "
                        "budget manifest run_id"
                    )
                if watermark_state.get("last_batch_id") not in queue_batch_ids:
                    errors.append(
                        "maintenance watermark last_batch_id is not one of "
                        "the budget manifest required_batch_ids"
                    )
                updated_instant = _timestamp_value(
                    watermark_state.get("updated_at"))
                receipt_instant = _timestamp_value(watermark.get("checked_at"))
                if (updated_instant is not None and receipt_instant is not None and
                        updated_instant > receipt_instant):
                    errors.append(
                        "maintenance watermark receipt predates watermark update"
                    )

    if ledger is not None:
        before = ledger.get("before_coverage_sha256")
        after = ledger.get("after_coverage_sha256")
        if (not isinstance(before, str) or not SHA256_RE.fullmatch(before) or
                before == after):
            errors.append(
                "maintenance Ledger advance must bind distinct valid before/after "
                "Coverage fingerprints"
            )
        coverage_updated = _timestamp_value(
            (result.get("coverage") or {}).get("updated_at"))
        receipt_checked = _timestamp_value(ledger.get("checked_at"))
        if (coverage_updated is not None and receipt_checked is not None and
                coverage_updated > receipt_checked):
            errors.append(
                "maintenance Ledger receipt predates Coverage updated_at"
            )
    if watermark is not None:
        before = watermark.get("before_watermark_sha256")
        after = watermark.get("after_watermark_sha256")
        if (not isinstance(before, str) or not SHA256_RE.fullmatch(before) or
                before == after):
            errors.append(
                "maintenance watermark advance must bind distinct valid "
                "before/after fingerprints"
            )

    terminal_instants = []
    for item in items.values():
        for field in ("closed_at", "cancelled_at"):
            instant = _timestamp_value(item.get(field))
            if instant is not None:
                terminal_instants.append(instant)
    if terminal_instants:
        latest_terminal = max(terminal_instants)
        for label, receipt in (("budget manifest closure", budget),
                               ("Ledger advance", ledger),
                               ("watermark advance", watermark)):
            if receipt is not None:
                instant = _timestamp_value(receipt.get("checked_at"))
                if instant is not None and instant < latest_terminal:
                    errors.append(
                        "maintenance %s predates the latest terminal batch event" %
                        label
                    )

    batch_receipts = []
    close_receipts = []
    for item_id, item in sorted(items.items()):
        if item.get("state") != "closed":
            continue
        batch_receipts.extend(item.get("batch_receipts") or [])
        value = item.get("close_gate_receipt")
        if _nonempty_string(value):
            close_receipts.append(value)
    context = {
        "completion_semantics": "maintenance",
        "scope_version": contract.get("scope_version"),
        "standards_version": contract.get("standards_version"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"),
        "budget_manifest_receipt": budget_manifest_receipt,
        "ledger_advance_receipt": ledger_advance_receipt,
        "watermark_advance_receipt": watermark_advance_receipt,
        "budget_manifest_path": (budget or {}).get("budget_manifest_path"),
        "budget_manifest_sha256":
            (budget or {}).get("budget_manifest_sha256"),
        "watermark_path": (watermark or {}).get("watermark_path"),
        "watermark_sha256":
            (watermark or {}).get("after_watermark_sha256"),
        "watermark_run_id": (watermark or {}).get("watermark_run_id"),
        "watermark_batch_id": (watermark or {}).get("watermark_batch_id"),
        "maintenance_run_id": maintenance_run_id,
        "contract_sha256": _contract_sha256(progress),
        "previous_maintenance_completion_receipt": previous_completion_id,
        "maintenance_candidate_state_sha256":
            candidate_context["candidate_state_sha256"],
        "maintenance_candidate_states": candidate_context["records"],
        "selected_candidate_ids": candidate_context["selected_ids"],
        "deferred_candidate_ids": candidate_context["deferred_ids"],
        "terminal_batch_ids": sorted(items),
        "applicable_batch_gate_receipts": sorted(set(batch_receipts)),
        "batch_close_gate_receipts": sorted(set(close_receipts)),
    }
    return errors, context


def _maintenance_gate_time_errors(result, gate):
    """Require the gate to follow every terminal event and consumed receipt."""
    errors = []
    gate_time = _timestamp_value(gate.get("checked_at"))
    if gate_time is None:
        return ["maintenance completion gate has invalid checked_at"]
    instants = []
    for field in ("budget_manifest_receipt", "ledger_advance_receipt",
                  "watermark_advance_receipt"):
        entry = (result.get("receipt_catalog") or {}).get(gate.get(field))
        receipt = entry[1] if entry is not None else None
        instant = _timestamp_value(
            receipt.get("checked_at")) if isinstance(receipt, dict) else None
        if instant is not None:
            instants.append((field, instant))
    for item in (result.get("items_by_id") or {}).values():
        for field in ("closed_at", "cancelled_at"):
            instant = _timestamp_value(item.get(field))
            if instant is not None:
                instants.append(("batch.%s" % field, instant))
    future = sorted(label for label, instant in instants if instant > gate_time)
    if future:
        errors.append(
            "maintenance completion gate predates consumed evidence: %s" %
            ", ".join(future)
        )
    return errors








def _task_transition_errors(root, progress, catalog, queue, queue_sha,
                            coverage_sha, progress_sha, remaining,
                            items_by_id, coverage):
    """Validate the sole task-state history and its restart checkpoint."""
    errors = []
    task_id = progress.get("task_id")
    task_state = progress.get("task_state")
    contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    contract_load_errors, contract_load_set_gaps = \
        _live_read_set_load_findings(root, contract)
    errors.extend(contract_load_errors)
    accounted_versions = accounted_standards_versions(progress, queue)
    completion_semantics = contract.get("completion_semantics")
    live_contract_sha = _contract_sha256(progress)
    contract_chain, _ = _contract_anchor_chain(progress, catalog)
    history = progress.get("task_transition_receipts")
    if not isinstance(history, list):
        errors.append("Progress task_transition_receipts must be an explicit list")
        history = []
    elif (not all(_nonempty_string(value) for value in history) or
          len(history) != len(set(history))):
        errors.append("Progress task_transition_receipts must contain unique receipt IDs")

    transitions = []
    previous = None
    for index, receipt_id in enumerate(history):
        receipt = _require_receipt(
            catalog, receipt_id, "task transition[%d]" % index, errors,
            expected={
                "tool": "update_task",
                "tool_version": "1.1.0",
                "check": "task_transition",
                "target": task_id,
                "task_id": task_id,
                "actor_role": "integrator",
                "completion_semantics": completion_semantics,
            },
        )
        if receipt is None:
            continue
        before = receipt.get("before_task_state")
        after = receipt.get("after_task_state")
        checked_at = receipt.get("checked_at")
        expected_contract_sha = (_contract_sha_at_revision(
            contract_chain, receipt.get("queue_revision")) or
            live_contract_sha)
        errors.extend(_task_transition_receipt_record_errors(
            catalog, receipt_id, receipt, completion_semantics,
            expected_contract_sha=expected_contract_sha,
        ))
        if previous is None:
            if before != "planned":
                errors.append("task transition history must begin at planned")
        else:
            if before != previous.get("after_task_state"):
                errors.append("task transition history breaks before %s" %
                              receipt_id)
            previous_time = _timestamp_value(previous.get("checked_at"))
            current_time = _timestamp_value(checked_at)
            if (previous_time is not None and current_time is not None and
                    current_time < previous_time):
                errors.append("task transition timestamps move backward at %s" %
                              receipt_id)
            for field in ("queue_revision", "queue_state_revision"):
                if (isinstance(receipt.get(field), int) and
                        isinstance(previous.get(field), int) and
                        receipt.get(field) < previous.get(field)):
                    errors.append("task transition %s moves %s backward" %
                                  (receipt_id, field))
        transitions.append(receipt)
        previous = receipt

    direct_activation = next((
        receipt for receipt in transitions
        if (receipt.get("before_task_state"),
            receipt.get("after_task_state")) == ("planned", "active")
    ), None)
    if direct_activation is not None:
        activation = direct_activation
        batch_id = activation.get("first_open_batch_id")
        queue_transition_id = activation.get(
            "first_open_transition_receipt")
        if not _nonempty_string(batch_id):
            errors.append("first task activation must identify "
                          "first_open_batch_id")
        if not _nonempty_string(queue_transition_id):
            errors.append("first task activation must identify "
                          "first_open_transition_receipt")
        opening = _require_receipt(
            catalog, queue_transition_id,
            "first task activation Queue transition", errors,
            expected={
                "tool": "update_queue",
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "check": "queue_transition",
                "target": batch_id,
                "task_id": task_id,
                "actor_role": "integrator",
                "before_state": "queued",
                "after_state": "open",
                "before_state_revision": 0,
                "after_state_revision": 1,
                "queue_revision": activation.get("queue_revision"),
                "before_required_queue_sha256":
                    activation.get("before_required_queue_sha256"),
                "after_required_queue_sha256":
                    activation.get("after_required_queue_sha256"),
                "evidence_receipt": activation.get("evidence_receipt"),
            },
        )
        if (isinstance(opening, dict) and
                opening.get("tool_version") not in
                SUPPORTED_UPDATE_QUEUE_TOOL_VERSIONS):
            errors.append(
                "first task activation Queue transition has unsupported "
                "update_queue producer version %r" %
                opening.get("tool_version"))
        if activation.get("queue_state_revision") != 1:
            errors.append("first task activation must bind Queue "
                          "state_revision 1")
        item = items_by_id.get(batch_id)
        if (not isinstance(item, dict) or
                queue_transition_id not in
                (item.get("transition_receipts") or [])):
            errors.append("first task activation Queue transition is not "
                          "retained by batch %s" % batch_id)

    if task_state == "planned":
        if history:
            errors.append("task_state=planned cannot have transition history")
    elif task_state in TASK_STATES:
        if not transitions:
            errors.append("task_state=%s requires task transition evidence" %
                          task_state)
        elif transitions[-1].get("after_task_state") != task_state:
            errors.append("latest task transition ends in %r, live task_state is %r" %
                          (transitions[-1].get("after_task_state"), task_state))

    checkpoint = progress.get("checkpoint")
    checkpoint_binding = "unavailable"
    if not isinstance(checkpoint, dict):
        errors.append("Progress checkpoint must be a mapping")
    elif task_state == "planned" and not transitions:
        if checkpoint.get("recorded_at") is not None:
            errors.append("planned initial checkpoint recorded_at must be null")
        checkpoint_binding = "initial"
    elif transitions:
        latest = transitions[-1]
        latest_id = history[-1]
        expected = {
            "recorded_at": latest.get("checked_at"),
            "task_state": task_state,
            "task_transition_receipt": latest_id,
            "coverage_sha256": latest.get("after_coverage_sha256"),
            "required_queue_sha256":
                latest.get("after_required_queue_sha256"),
            "queue_revision": latest.get("queue_revision"),
            "queue_state_revision": latest.get("queue_state_revision"),
        }
        for field, value in expected.items():
            if checkpoint.get(field) != value:
                errors.append("checkpoint %s=%r, expected %r from latest task "
                              "transition" %
                              (field, checkpoint.get(field), value))
        if not _nonempty_string(checkpoint.get("summary")):
            errors.append("checkpoint summary must be non-empty after activation")
        live_match = (
            checkpoint.get("coverage_sha256") == coverage_sha and
            checkpoint.get("required_queue_sha256") == queue_sha and
            checkpoint.get("queue_revision") == queue.get("queue_revision") and
            checkpoint.get("queue_state_revision") == queue.get("state_revision") and
            latest.get("after_progress_sha256") == progress_sha
        )
        checkpoint_binding = "current" if live_match else "historical"

    pending_guidance, pending_amendments = _pending_control_ids(progress)
    terminal_audit = progress.get("terminal_audit")
    if not isinstance(terminal_audit, dict):
        errors.append("Progress terminal_audit must be a mapping")
        terminal_audit = {}
    maintenance_completion = progress.get("maintenance_completion")
    if not isinstance(maintenance_completion, dict):
        errors.append("Progress maintenance_completion must be a mapping")
        maintenance_completion = {}
    if completion_semantics == "build":
        terminal_state = terminal_audit.get("state")
        if task_state in ("planned", "active", "paused", "blocked"):
            left_candidate = any(
                receipt.get("before_task_state") == "completion-candidate" and
                receipt.get("after_task_state") in
                ("active", "paused", "blocked")
                for receipt in transitions
            )
            expected_terminal = "invalidated" if left_candidate else "not-started"
            if terminal_state != expected_terminal:
                errors.append(
                    "build task_state=%s requires terminal_audit.state=%s" %
                    (task_state, expected_terminal)
                )
        elif task_state == "cancelled" and terminal_state != "not-applicable":
            errors.append(
                "cancelled build task requires terminal_audit.state="
                "not-applicable"
            )
        if terminal_state in ("not-started", "invalidated", "not-applicable"):
            for field in TERMINAL_AUDIT_FIELDS - {"state"}:
                if terminal_audit.get(field) is not None:
                    errors.append(
                        "build terminal_audit.state=%s requires %s=null" %
                        (terminal_state, field)
                    )
        elif terminal_state == "ready":
            for field in ("terminal_proof_path", "terminal_proof_sha256",
                          "terminal_proof_receipt"):
                if terminal_audit.get(field) is not None:
                    errors.append(
                        "ready terminal_audit requires %s=null" % field
                    )
    if task_state == "completion-candidate":
        if completion_semantics != "build":
            errors.append(
                "completion-candidate requires completion_semantics=build"
            )
        if remaining != 0:
            errors.append("completion-candidate requires zero remaining work")
        if pending_guidance or pending_amendments:
            errors.append("completion-candidate has pending Guidance/Amendments")
        if terminal_audit.get("state") != "ready":
            errors.append("completion-candidate terminal_audit state must be ready")
        completion_id = terminal_audit.get("queue_check_receipt")
        completion_receipt = _require_receipt(
            catalog, completion_id, "completion-candidate Queue gate", errors,
            expected={
                "tool": TOOL,
                "check": "required_queue",
                "queue_check_mode": "require-complete",
                "task_id": task_id,
                "queue_revision": queue.get("queue_revision"),
                "queue_state_revision": queue.get("state_revision"),
                "required_queue_sha256": queue_sha,
                "coverage_ledger_sha256": coverage_sha,
                "progress_ledger_sha256":
                    transitions[-1].get("before_progress_sha256")
                    if transitions else progress_sha,
                "remaining_required_work_units": 0,
            },
        )
        # Historical: the gate that admitted the state the task is already in.
        # A completion-candidate task cannot adopt, so it cannot re-produce
        # this receipt under a newer producer identity either.
        errors.extend(_producer_era_errors(
            completion_receipt, completion_id,
            "completion-candidate Queue gate", accounted_versions))
        if isinstance(completion_receipt, dict):
            completion_version = completion_receipt.get("tool_version")
            if (completion_version == TOOL_VERSION and
                    completion_receipt.get("gate_id") !=
                    "required-queue-completion"):
                errors.append("current completion-candidate Queue gate must "
                              "bind gate_id=required-queue-completion")
    if task_state == "complete" and completion_semantics == "build":
        if terminal_audit.get("state") != "passed":
            errors.append("complete terminal_audit state must be passed")
        proof_id = terminal_audit.get("terminal_proof_receipt")
        proof = _require_receipt(
            catalog, proof_id, "complete Terminal Proof", errors,
            expected={
                "tool": TERMINAL_PROOF_TOOL,
                "check": "proof-check-summary",
                "task_id": task_id,
                "coverage_ledger_sha256": coverage_sha,
                "required_queue_path": QUEUE_PATH,
                "queue_revision": queue.get("queue_revision"),
                "queue_state_revision": queue.get("state_revision"),
                "required_queue_sha256": queue_sha,
                "remaining_required_work_units": 0,
            },
        )
        # Historical: the proof a completed task already consumed.  A complete
        # task cannot adopt, so nothing can restamp this receipt.
        errors.extend(_producer_era_errors(
            proof, proof_id, "complete Terminal Proof", accounted_versions))
        if isinstance(proof, dict):
            errors.extend(_terminal_proof_profile_binding_errors(
                proof, proof_id))
            proof_version = proof.get("tool_version")
            if (proof_version == TERMINAL_PROOF_TOOL_VERSION and
                    proof.get("gate_id") != "terminal-proof"):
                errors.append("current Terminal Proof receipt must bind "
                              "gate_id=terminal-proof")
        if transitions and proof is not None:
            latest = transitions[-1]
            if latest.get("evidence_receipt") != proof_id:
                errors.append("complete task transition does not consume its "
                              "Terminal Proof receipt")
            if proof.get("progress_ledger_sha256") != latest.get(
                    "before_progress_sha256"):
                errors.append("Terminal Proof must bind the pre-complete Progress "
                              "bytes")
            if terminal_audit.get("terminal_proof_path") != proof.get(
                    "terminal_proof_path"):
                errors.append("terminal_audit proof path differs from receipt")
            if terminal_audit.get("terminal_proof_sha256") != proof.get(
                    "terminal_proof_sha256"):
                errors.append("terminal_audit proof SHA differs from receipt")
            proof_path = proof.get("terminal_proof_path")
            proof_sha = proof.get("terminal_proof_sha256")
            try:
                proof_file = kblib.managed_repository_path(
                    root, proof_path, ".cambium/receipts",
                    suffixes=(".yaml", ".yml"), must_exist=True,
                )
                if kblib.sha256_file(proof_file) != proof_sha:
                    errors.append("complete Terminal Proof bytes differ from "
                                  "the persisted proof receipt")
            except (OSError, TypeError, ValueError) as exc:
                errors.append("complete Terminal Proof is unsafe or missing: %s" %
                              exc)
    if task_state == "complete" and completion_semantics == "maintenance":
        if remaining != 0:
            errors.append("maintenance complete requires zero remaining work")
        if pending_guidance or pending_amendments:
            errors.append(
                "maintenance complete has pending Guidance/Amendments"
            )
        if maintenance_completion.get("state") != "passed":
            errors.append(
                "maintenance complete requires maintenance_completion.state=passed"
            )
        gate_id = maintenance_completion.get("completion_gate_receipt")
        gate = _require_receipt(
            catalog, gate_id, "maintenance completion gate", errors,
            expected={
                "tool": TOOL,
                "check": "required_queue",
                "queue_check_mode": "require-maintenance-complete",
                "task_id": task_id,
                "completion_semantics": "maintenance",
                "scope_version": contract.get("scope_version"),
                "standards_version": contract.get("standards_version"),
                "selected_profile_manifest": contract.get(
                    "selected_profile_manifest"),
                "queue_revision": queue.get("queue_revision"),
                "queue_state_revision": queue.get("state_revision"),
                "required_queue_sha256": queue_sha,
                "coverage_ledger_sha256": coverage_sha,
                "progress_ledger_sha256":
                    transitions[-1].get("before_progress_sha256")
                    if transitions else progress_sha,
                "remaining_required_work_units": 0,
            },
        )
        # Historical: the gate a completed maintenance run already consumed.
        # No `tool_version` comparison, and none is needed -- the expected
        # mapping above binds `standards_version` to the live contract exactly,
        # which states the producer era without naming a producer constant.
        if isinstance(gate, dict):
            gate_version = gate.get("tool_version")
            if (gate_version == TOOL_VERSION and
                    gate.get("gate_id") != "maintenance-completion"):
                errors.append("current maintenance completion gate must bind "
                              "gate_id=maintenance-completion")
        if transitions and gate is not None:
            latest = transitions[-1]
            if (latest.get("before_task_state") not in ("planned", "active") or
                    latest.get("after_task_state") != "complete"):
                errors.append(
                    "maintenance completion must use planned/active -> complete"
                )
            if latest.get("evidence_receipt") != gate_id:
                errors.append(
                    "maintenance complete transition does not consume its gate"
                )
        if gate is not None:
            for field in (
                    "budget_manifest_receipt", "ledger_advance_receipt",
                    "watermark_advance_receipt"):
                if maintenance_completion.get(field) != gate.get(field):
                    errors.append(
                        "maintenance_completion.%s differs from its gate receipt" %
                        field
                    )
                _require_receipt(
                    catalog, gate.get(field),
                    "maintenance completion %s" % field, errors,
                )
            if gate.get("terminal_batch_ids") != sorted(items_by_id):
                errors.append(
                    "maintenance completion gate does not bind every Queue batch"
                )
            evidence_errors, expected_context = \
                _maintenance_completion_gate_errors(
                    root, {
                        "progress": progress,
                        "coverage": coverage,
                        "queue": queue,
                        "items_by_id": items_by_id,
                        "remaining": remaining,
                        "coverage_sha256": coverage_sha,
                        "queue_sha256": queue_sha,
                        "progress_sha256": progress_sha,
                        "receipt_catalog": catalog,
                    },
                    gate.get("budget_manifest_receipt"),
                    gate.get("ledger_advance_receipt"),
                    gate.get("watermark_advance_receipt"),
                    allow_complete=True,
                )
            errors.extend(evidence_errors)
            errors.extend(_maintenance_gate_time_errors({
                "receipt_catalog": catalog,
                "items_by_id": items_by_id,
            }, gate))
            for field, expected in expected_context.items():
                if gate.get(field) != expected:
                    errors.append(
                        "maintenance completion gate %s=%r, expected %r" %
                        (field, gate.get(field), expected)
                    )

    if completion_semantics == "maintenance" and task_state != "complete":
        expected_state = ("invalidated" if task_state == "cancelled"
                          else "pending")
        if maintenance_completion.get("state") != expected_state:
            errors.append(
                "maintenance task_state=%s requires "
                "maintenance_completion.state=%s" %
                (task_state, expected_state)
            )
        for field in MAINTENANCE_COMPLETION_FIELDS - {"state"}:
            if maintenance_completion.get(field) is not None:
                errors.append(
                    "non-complete maintenance task requires "
                    "maintenance_completion.%s=null" % field
                )

    # Terminal admission cannot predate the last terminal batch event.
    terminal_times = []
    for item in items_by_id.values():
        for field in ("closed_at", "cancelled_at"):
            value = item.get(field)
            if _valid_timestamp(value):
                terminal_times.append(value)
    if transitions and task_state in ("completion-candidate", "complete") and \
            terminal_times:
        candidate = (transitions[-1] if completion_semantics == "maintenance"
                     else next((entry for entry in transitions
                                if entry.get("after_task_state") ==
                                "completion-candidate"), None))
        candidate_time = _timestamp_value(
            candidate.get("checked_at")) if candidate else None
        terminal_instants = [
            _timestamp_value(value) for value in terminal_times
        ]
        terminal_instants = [value for value in terminal_instants
                             if value is not None]
        if (candidate_time is not None and terminal_instants and
                candidate_time < max(terminal_instants)):
            errors.append(
                "%s completion admission predates a terminal batch event" %
                completion_semantics
            )

    return errors, {
        "history": history,
        "latest_receipt": transitions[-1] if transitions else None,
        "checkpoint_binding": checkpoint_binding,
        "pending_guidance": pending_guidance,
        "pending_amendments": pending_amendments,
        "last_reconciled_guidance_id": _last_reconciled_guidance_id(progress),
        # Reported, never an error: the live contract's completeness gaps are
        # repaired by the next admitted adoption plan, not by refusing the
        # runtime that holds them.  Nothing in the error set reads this key.
        "contract_load_set_gaps": contract_load_set_gaps,
    }




























































































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
        allow_legacy_missing=False,
        gate_evidence_errors=
        metadata_gate_runtime.persisted_property_gate_errors):
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


def _closed_bundle_seal_state(item, catalog):
    """Classify one closed item's evidence trio against the cold index.

    The trio -- batch-close gate, pre-close Queue consistency snapshot, and
    Coverage delta application -- is sealed together or not at all, because
    a half-sealed bundle can neither replay the hot revalidation nor claim
    the sealed short-circuit.  Returns ``"hot"``, ``"sealed"``, or
    ``"mixed"``.
    """
    cold = getattr(catalog, "cold", None) or {}
    trio = [item.get("close_gate_receipt"),
            item.get("queue_consistency_receipt"),
            item.get("delta_apply_receipt")]
    sealed = [receipt_id for receipt_id in trio
              if _nonempty_string(receipt_id) and receipt_id in cold]
    if not sealed:
        return "hot"
    if len(sealed) != len([r for r in trio if _nonempty_string(r)]):
        return "mixed"
    return "sealed"


def _sealed_closed_bundle_errors(item, transition, catalog, queue):
    """Validate one sealed close bundle through its thin projections.

    Reading a projection is sound here only because ``_cold_receipt_store``
    has already proved, this run, that each projection hashes to the exact
    sealed record it names and that the seal receipt which produced it
    still binds the whole index row set byte for byte.  Without those two
    proofs a projection would be an editable side table asserting its own
    correctness, and this function would be reading the claim instead of
    the evidence.

    Given them, the per-run obligation drops to identity: the projections
    still name the receipts this item and its close transition bind, with
    the identities their producers recorded.  Body-level bindings (snapshot
    hashes, delta hashes, disposition schemas) were proven at seal time
    against exactly the bytes still on disk, and sealing refuses any bundle
    whose full frozen-history revalidation does not pass at that moment.
    """
    errors = []
    item_id = item.get("id", "<unknown>")
    cold = getattr(catalog, "cold", None) or {}
    close_gate_id = item.get("close_gate_receipt")
    consistency_id = item.get("queue_consistency_receipt")
    delta_apply_id = item.get("delta_apply_receipt")
    expectations = (
        (close_gate_id, "%s sealed batch-close gate" % item_id, {
            "tool": BATCH_CLOSE_TOOL,
            "check": "batch_close_gate",
            "target": item_id,
            "batch_id": item_id,
            "task_id": queue.get("task_id"),
            "result": "pass",
        }),
        (consistency_id, "%s sealed Queue consistency gate" % item_id, {
            "tool": TOOL,
            "check": GATE_CHECK,
            "queue_check_mode": "consistency",
            "task_id": queue.get("task_id"),
            "result": "pass",
        }),
        (delta_apply_id, "%s sealed delta application" % item_id, {
            "tool": "apply_delta",
            "check": "delta_apply",
            "target": item_id,
            "batch_id": item_id,
            "task_id": queue.get("task_id"),
            "result": "pass",
        }),
    )
    for receipt_id, label, expected in expectations:
        projection = cold.get(receipt_id)
        if projection is None:
            errors.append("%s projection is absent from the cold index" %
                          label)
            continue
        for field, value in expected.items():
            if projection.get(field) != value:
                errors.append("%s projection has %s=%r, expected %r" %
                              (label, field, projection.get(field), value))
    close_projection = cold.get(close_gate_id) or {}
    close_version = close_projection.get("tool_version")
    if close_version not in SUPPORTED_BATCH_CLOSE_TOOL_VERSIONS:
        errors.append("%s sealed batch-close gate has unsupported producer "
                      "era %r" % (item_id, close_version))
    if transition is None:
        return errors
    if transition.get("queue_consistency_receipt") != consistency_id:
        errors.append("%s close transition does not bind Queue consistency "
                      "receipt %s" % (item_id, consistency_id))
    if transition.get("close_gate_receipt") != close_gate_id:
        errors.append("%s close transition does not bind batch-close gate "
                      "receipt %s" % (item_id, close_gate_id))
    if transition.get("evidence_receipt") != close_gate_id:
        errors.append("%s close transition evidence_receipt must be the "
                      "independent batch-close gate" % item_id)
    if transition.get("delta_apply_receipt") != delta_apply_id:
        errors.append("%s close transition does not bind delta application "
                      "receipt %s" % (item_id, delta_apply_id))
    return errors


def _closed_gate_errors(item, transition, catalog, queue,
                        accounted_versions=frozenset(), root=None):
    """Revalidate the two independent pre-close gates from frozen history."""
    errors = []
    item_id = item.get("id", "<unknown>")
    consistency_id = item.get("queue_consistency_receipt")
    close_gate_id = item.get("close_gate_receipt")
    close_gate_entry = catalog.get(close_gate_id)
    close_gate_identity = (close_gate_entry[1]
                           if close_gate_entry is not None else {})
    consistency_expected = {
        "tool": TOOL,
        "check": "required_queue",
        "queue_check_mode": "consistency",
        "task_id": queue.get("task_id"),
    }
    if transition is not None:
        consistency_expected.update({
            "queue_revision": transition.get("queue_revision"),
            "queue_state_revision": transition.get("before_state_revision"),
            "required_queue_sha256":
                transition.get("before_required_queue_sha256"),
            "coverage_ledger_sha256":
                transition.get("before_coverage_sha256"),
            "progress_ledger_sha256":
                transition.get("before_progress_sha256"),
        })
    consistency_receipt = _require_receipt(
        catalog, consistency_id, "%s Queue consistency gate" % item_id,
        errors, expected=consistency_expected,
    )
    # Historical: a closed batch's pre-close Queue consistency gate, bound to
    # the frozen before-bytes of a transition that already happened.
    errors.extend(_producer_era_errors(
        consistency_receipt, consistency_id,
        "%s Queue consistency gate" % item_id, accounted_versions))
    if transition is None:
        # Transition-history validation reports the missing edge.  Avoid
        # inventing live-state bindings for an unanchored historical gate.
        return errors
    if transition.get("queue_consistency_receipt") != consistency_id:
        errors.append("%s close transition does not bind Queue consistency "
                      "receipt %s" % (item_id, consistency_id))
    if transition.get("close_gate_receipt") != close_gate_id:
        errors.append("%s close transition does not bind batch-close gate "
                      "receipt %s" % (item_id, close_gate_id))
    if transition.get("evidence_receipt") != close_gate_id:
        errors.append("%s close transition evidence_receipt must be the "
                      "independent batch-close gate" % item_id)
    errors.extend(close_gate_receipt_errors(
        catalog, close_gate_id,
        item_id=item_id,
        root=root,
        task_id=queue.get("task_id"),
        queue_revision=transition.get("queue_revision"),
        queue_state_revision=transition.get("before_state_revision"),
        required_queue_sha256=
            transition.get("before_required_queue_sha256"),
        coverage_ledger_sha256=transition.get("before_coverage_sha256"),
        progress_ledger_sha256=transition.get("before_progress_sha256"),
        delta_sha256=item.get("delta_sha256"),
        queue_consistency_receipt=consistency_id,
        delta_apply_receipt=transition.get("delta_apply_receipt"),
        work_spec_path=item.get("work_spec_path"),
        work_spec_sha256=item.get("work_spec_sha256"),
        manifest=item.get("manifest"),
        # Historical closure is checked against the identity frozen by its
        # producer.  A later Standards adoption must not reinterpret a valid
        # closed edge using the live Profile.
        selected_profile_manifest=close_gate_identity.get(
            "selected_profile_manifest"),
        historical=True,
    ))
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


def _close_gate_reuse_errors(items_by_id):
    """Reject one snapshot-specific close assertion owning two histories."""
    errors = []
    owners = {}
    for item_id, item in sorted(items_by_id.items()):
        receipt_id = item.get("close_gate_receipt")
        if not _nonempty_string(receipt_id):
            continue
        previous = owners.get(receipt_id)
        if previous is not None and previous != item_id:
            errors.append("batch-close gate receipt %s is reused by %s and %s" %
                          (receipt_id, previous, item_id))
        else:
            owners[receipt_id] = item_id
    return errors


def _global_transition_errors(items_by_id, catalog, queue, queue_sha):
    """Prove that transition evidence is one complete global state history."""
    errors = []
    references = {}
    transitions = []
    for item_id, item in items_by_id.items():
        receipt_ids = item.get("transition_receipts")
        if not isinstance(receipt_ids, list):
            continue
        for receipt_id in receipt_ids:
            if not _nonempty_string(receipt_id):
                continue
            if receipt_id in references:
                errors.append("transition receipt %s is referenced by both %s "
                              "and %s" %
                              (receipt_id, references[receipt_id], item_id))
                continue
            references[receipt_id] = item_id
            entry = catalog.get(receipt_id)
            if entry is not None:
                transitions.append((item_id, receipt_id, entry[1]))

    by_revision = {}
    for item_id, receipt_id, receipt in transitions:
        after_revision = receipt.get("after_state_revision")
        if isinstance(after_revision, int) and not isinstance(
                after_revision, bool):
            by_revision.setdefault(after_revision, []).append(
                (item_id, receipt_id, receipt))
        if receipt.get("actor_role") != "integrator":
            errors.append("transition receipt %s actor_role must be integrator" %
                          receipt_id)
        if not _valid_timestamp(receipt.get("checked_at")):
            errors.append("transition receipt %s checked_at must be a "
                          "timezone-aware RFC 3339 timestamp" % receipt_id)
        before_state = receipt.get("before_state")
        after_state = receipt.get("after_state")
        before_hold = receipt.get("before_hold_state")
        after_hold = receipt.get("after_hold_state")
        if before_state == after_state:
            if before_hold == after_hold:
                errors.append("transition receipt %s is a state/hold no-op" %
                              receipt_id)
            elif before_state in TERMINAL_STATES:
                errors.append("transition receipt %s mutates terminal history" %
                              receipt_id)
        elif (before_state, after_state) not in LIFECYCLE_EDGES:
            errors.append("transition receipt %s has illegal lifecycle edge "
                          "%r -> %r" %
                          (receipt_id, before_state, after_state))

        evidence_id = receipt.get("evidence_receipt")
        evidence_required = (
            (before_state, after_state) in
            (("queued", "open"), ("open", "merge-ready"),
             ("merge-ready", "closed")) or
            (before_state == after_state and
             before_hold == "revalidation-required" and after_hold == "none")
        )
        if evidence_required and not _nonempty_string(evidence_id):
            errors.append("transition receipt %s requires evidence_receipt" %
                          receipt_id)
        evidence_receipt = None
        if evidence_id is not None:
            evidence_receipt = _require_receipt(
                catalog, evidence_id,
                "transition %s evidence" % receipt_id, errors,
            )
        if (evidence_receipt is not None and
                evidence_receipt.get("tool") == TOOL):
            expected_evidence = {
                "coverage_ledger_sha256":
                    receipt.get("before_coverage_sha256"),
                "progress_ledger_sha256":
                    receipt.get("before_progress_sha256"),
                "required_queue_sha256":
                    receipt.get("before_required_queue_sha256"),
                "queue_revision": receipt.get("queue_revision"),
                "queue_state_revision":
                    receipt.get("before_state_revision"),
            }
            for field, expected in expected_evidence.items():
                if evidence_receipt.get(field) != expected:
                    errors.append(
                        "transition %s evidence %s=%r, expected %r" %
                        (receipt_id, field,
                         evidence_receipt.get(field), expected)
                    )

    state_revision = queue.get("state_revision")
    if not isinstance(state_revision, int) or isinstance(state_revision, bool):
        return errors
    expected_revisions = set(range(1, state_revision + 1))
    found_revisions = set(by_revision)
    missing = sorted(expected_revisions - found_revisions)
    extra = sorted(found_revisions - expected_revisions)
    repeated = sorted(revision for revision, values in by_revision.items()
                      if len(values) != 1)
    if missing or extra or repeated:
        errors.append("transition receipts must cover every state_revision "
                      "1..%d exactly once; missing=%s extra=%s repeated=%s" %
                      (state_revision, missing, extra, repeated))

    ordered = []
    for revision in sorted(expected_revisions.intersection(found_revisions)):
        values = by_revision[revision]
        if len(values) == 1:
            ordered.append(values[0])
    previous = None
    for item_id, receipt_id, receipt in ordered:
        revision = receipt.get("after_state_revision")
        if receipt.get("before_state_revision") != revision - 1:
            errors.append("transition receipt %s does not own exact revision "
                          "edge %d -> %d" %
                          (receipt_id, revision - 1, revision))
        if previous is not None:
            previous_receipt = previous[2]
            previous_time = _timestamp_value(
                previous_receipt.get("checked_at"))
            current_time = _timestamp_value(receipt.get("checked_at"))
            if (previous_time is not None and current_time is not None and
                    current_time < previous_time):
                errors.append("transition receipt %s moves time backward" %
                              receipt_id)
            previous_queue_revision = previous_receipt.get("queue_revision")
            queue_revision = receipt.get("queue_revision")
            if (isinstance(previous_queue_revision, int) and
                    isinstance(queue_revision, int) and
                    queue_revision < previous_queue_revision):
                errors.append("transition receipt %s moves queue_revision "
                              "backward" % receipt_id)
            if (queue_revision == previous_queue_revision and
                    receipt.get("before_required_queue_sha256") !=
                    previous_receipt.get("after_required_queue_sha256")):
                errors.append("global transition SHA chain breaks before %s" %
                              receipt_id)
        previous = (item_id, receipt_id, receipt)

    if ordered:
        last = ordered[-1][2]
        if (last.get("after_state_revision") == state_revision and
                last.get("queue_revision") == queue.get("queue_revision") and
                last.get("after_required_queue_sha256") != queue_sha):
            errors.append("latest transition receipt does not match live Queue "
                          "bytes")
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


def _item_evidence_errors(item, progress, records, catalog, current_catalog,
                          queue):
    errors = []
    item_id = item.get("id", "<unknown>")
    state = item.get("state")
    hold = item.get("hold_state")
    current_delta_gate_receipts = []
    accounted_versions = accounted_standards_versions(progress, queue)

    transition = None
    transition_history = []
    transition_ids = item.get("transition_receipts")
    if state != "queued" or transition_ids is not None:
        if (not isinstance(transition_ids, list) or not transition_ids or
                not all(_nonempty_string(value) for value in transition_ids)):
            errors.append("%s state %s requires non-empty transition_receipts" %
                          (item_id, state))
            transition_ids = []
        elif len(transition_ids) != len(set(transition_ids)):
            errors.append("%s transition_receipts must be unique" % item_id)
        previous = None
        for position, receipt_id in enumerate(transition_ids):
            current = _require_receipt(
                catalog, receipt_id,
                "%s transition[%d]" % (item_id, position), errors,
                expected={
                    "check": "queue_transition",
                    "target": item_id,
                    "task_id": queue.get("task_id"),
                },
            )
            if current is None:
                continue
            producer = (current.get("tool"), current.get("tool_version"))
            allowed_producers = {
                ("update_queue", version)
                for version in SUPPORTED_UPDATE_QUEUE_TOOL_VERSIONS
            }
            if current.get("after_state") == "cancelled":
                # Cancellation changes all three canonical state documents;
                # the cross-Ledger transaction is therefore a truthful
                # producer for this edge.  Other lifecycle edges remain
                # update_queue-owned.
                allowed_producers.update(
                    ("apply_amendment", version)
                    for version in SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS
                )
            if producer not in allowed_producers:
                errors.append("%s transition receipt %s has unsupported "
                              "producer %r/%r" %
                              (item_id, receipt_id,
                               producer[0], producer[1]))
            if (producer == ("update_queue", UPDATE_QUEUE_TOOL_VERSION) and
                    current.get("before_state") == "open" and
                    current.get("after_state") == "merge-ready"):
                errors.extend(_settlement_binding_errors(
                    current, "%s merge-ready transition %s" %
                    (item_id, receipt_id)))
                if current.get("delta_path") != \
                        ".cambium/deltas/%s.yaml" % item_id:
                    errors.append(
                        "%s merge-ready transition %s has noncanonical "
                        "delta_path" % (item_id, receipt_id))
                for field in (
                        "delta_sha256",
                        "settlement_coverage_sha256_before",
                        "settlement_prospective_coverage_sha256"):
                    if not SHA256_RE.fullmatch(str(current.get(field) or "")):
                        errors.append(
                            "%s merge-ready transition %s has invalid %s" %
                            (item_id, receipt_id, field))
            errors.extend(_current_open_semantic_baseline_errors(
                records["root"], current, item,
                records.get("profile_view"),
                require_live_authority=state in ("open", "merge-ready")))
            errors.extend(_current_close_transition_metadata_errors(
                records["root"], current, catalog, item_id))
            if (current.get("before_state") not in STATES or
                    current.get("after_state") not in STATES):
                errors.append("%s transition receipt %s has invalid lifecycle "
                              "state edge %r -> %r" %
                              (item_id, receipt_id,
                               current.get("before_state"),
                               current.get("after_state")))
            if (current.get("before_hold_state") not in HOLDS or
                    current.get("after_hold_state") not in HOLDS):
                errors.append("%s transition receipt %s has invalid hold edge "
                              "%r -> %r" %
                              (item_id, receipt_id,
                               current.get("before_hold_state"),
                               current.get("after_hold_state")))
            before_revision = current.get("before_state_revision")
            after_revision = current.get("after_state_revision")
            if (not isinstance(before_revision, int) or
                    isinstance(before_revision, bool) or
                    not isinstance(after_revision, int) or
                    isinstance(after_revision, bool) or
                    after_revision != before_revision + 1 or
                    after_revision < 1 or
                    after_revision > queue.get("state_revision", -1)):
                errors.append("%s transition receipt %s has invalid state "
                              "revision edge %r -> %r" %
                              (item_id, receipt_id, before_revision,
                               after_revision))
            receipt_queue_revision = current.get("queue_revision")
            if (not isinstance(receipt_queue_revision, int) or
                    receipt_queue_revision < 1 or
                    receipt_queue_revision > queue.get("queue_revision", -1)):
                errors.append("%s transition receipt %s has invalid "
                              "queue_revision %r" %
                              (item_id, receipt_id, receipt_queue_revision))
            for fingerprint_field in (
                    "before_required_queue_sha256",
                    "after_required_queue_sha256"):
                fingerprint = current.get(fingerprint_field)
                if (not isinstance(fingerprint, str) or
                        not SHA256_RE.fullmatch(fingerprint)):
                    errors.append("%s transition receipt %s has invalid %s" %
                                  (item_id, receipt_id, fingerprint_field))
            if previous is not None:
                previous_time = _timestamp_value(previous.get("checked_at"))
                current_time = _timestamp_value(current.get("checked_at"))
                if (previous_time is not None and current_time is not None and
                        current_time < previous_time):
                    errors.append("%s transition timestamps move backward at %s" %
                                  (item_id, receipt_id))
                for left, right in (("after_state", "before_state"),
                                    ("after_hold_state", "before_hold_state")):
                    if previous.get(left) != current.get(right):
                        errors.append("%s transition history breaks between %s "
                                      "and %s" %
                                      (item_id,
                                       transition_ids[position - 1], receipt_id))
                        break
                if previous.get("after_state_revision") >= after_revision:
                    errors.append("%s transition revisions are not increasing" %
                                  item_id)
                if before_revision < previous.get("after_state_revision", -1):
                    errors.append("%s transition history moves state revision backward" %
                                  item_id)
                elif (before_revision == previous.get("after_state_revision") and
                      current.get("queue_revision") ==
                      previous.get("queue_revision") and
                      current.get("before_required_queue_sha256") !=
                      previous.get("after_required_queue_sha256")):
                    errors.append("%s adjacent transition fingerprints do not chain" %
                                  item_id)
            previous = current
            transition_history.append(current)
        if transition_history:
            transition = transition_history[-1]
            if transition_history[0].get("before_state") != "queued":
                errors.append("%s transition history must begin at queued" % item_id)
            if transition.get("after_state") != state:
                errors.append("%s last transition ends in %r, current state is %r" %
                              (item_id, transition.get("after_state"), state))
            if transition.get("after_hold_state") != hold:
                errors.append("%s last transition hold is %r, current hold is %r" %
                              (item_id, transition.get("after_hold_state"), hold))
        if state in ("open", "merge-ready"):
            latest_opening = next((
                receipt for receipt in reversed(transition_history)
                if receipt.get("before_state") in ("queued", "merge-ready")
                and receipt.get("after_state") == "open"), None)
            if latest_opening is None:
                errors.append(
                    "%s live state %s has no opening semantic before-set" %
                    (item_id, state))
            elif (latest_opening.get("tool") != "update_queue" or
                    latest_opening.get("tool_version") !=
                    UPDATE_QUEUE_TOOL_VERSION):
                errors.append(
                    "%s live state %s uses legacy opening producer %r/%r; "
                    "migrate/reopen it before further writes" %
                    (item_id, state, latest_opening.get("tool"),
                     latest_opening.get("tool_version")))
    if state in ("closed", "cancelled") and hold != "none":
        errors.append("%s history is immutable and must have hold_state none" %
                      item_id)

    # The hold sub-state machine, read over the whole ordered history rather
    # than the last edge.  An item sitting at any hold other than
    # `revalidation-required` while its revalidation obligation is still
    # undischarged reached that hold by routing around the clear, and an item
    # sitting at `none` has had the obligation silently dropped.  Both fail
    # closed here, including for state written by hand.
    if hold != "revalidation-required" and undischarged_revalidation_hold(
            transition_history):
        errors.append(
            "%s left revalidation-required for hold_state %r without the "
            "clearing evidence; the hold is discharged by its own gate, not "
            "by an intermediate hold" % (item_id, hold))

    if hold != "none" and not _nonempty_string(item.get("hold_reason")):
        errors.append("%s hold_state %s requires hold_reason" % (item_id, hold))

    if state in ("open", "merge-ready", "closed"):
        if not _valid_timestamp(item.get("opened_at")):
            errors.append("%s state %s requires a timezone-aware opened_at" %
                          (item_id, state))
        activation_expected = {
            "tool": TOOL,
            "check": "required_queue",
            "queue_check_mode": "require-ready:%s" % item_id,
            "task_id": queue.get("task_id"),
        }
        opening_transition = next((receipt for receipt in transition_history
                                   if receipt.get("before_state") == "queued" and
                                   receipt.get("after_state") == "open"), None)
        if opening_transition is not None:
            activation_expected.update({
                "queue_revision": opening_transition.get("queue_revision"),
                "queue_state_revision":
                    opening_transition.get("before_state_revision"),
                "required_queue_sha256":
                    opening_transition.get("before_required_queue_sha256"),
                "coverage_ledger_sha256":
                    opening_transition.get("before_coverage_sha256"),
                "progress_ledger_sha256":
                    opening_transition.get("before_progress_sha256"),
            })
        if item.get("confirmation_required"):
            activation_expected["confirmation_receipt"] = \
                item.get("confirmation_receipt")
        activation_receipt = _require_receipt(
            catalog, item.get("activation_receipt"),
            "%s activation" % item_id, errors,
            expected=activation_expected,
        )
        # Historical: the admission gate that authorized the already-recorded
        # `queued -> open` edge.  The batch cannot be readmitted, so no later
        # producer version can restamp it.
        errors.extend(_producer_era_errors(
            activation_receipt, item.get("activation_receipt"),
            "%s activation" % item_id, accounted_versions))
        if (isinstance(activation_receipt, dict) and
                activation_receipt.get("tool") == TOOL and
                activation_receipt.get("tool_version") == TOOL_VERSION):
            activation_context = card_activation.context_from_receipt(
                activation_receipt)
            errors.extend(
                "%s activation %s" % (item_id, error)
                for error in card_activation.activation_context_errors(
                    activation_context))
            if opening_transition is not None:
                for field in (
                        "activation_protocol", "task_contract_sha256",
                        "reading_plan_sha256", "readback_plan_sha256",
                        "card_bundle_sha256", "delivery_mode",
                        "delivery_assurance", "execution_context_id"):
                    if opening_transition.get(field) != \
                            activation_receipt.get(field):
                        errors.append(
                            "%s opening transition does not preserve "
                            "activation %s" % (item_id, field))
        if item.get("confirmation_required"):
            _require_receipt(
                catalog, item.get("confirmation_receipt"),
                "%s confirmation" % item_id, errors,
                expected={"check": "confirmation", "target": item_id},
            )

    if state in ("merge-ready", "closed"):
        if not _valid_timestamp(item.get("merge_ready_at")):
            errors.append("%s state %s requires a timezone-aware merge_ready_at" %
                          (item_id, state))
        delta_path = item.get("delta_path")
        if not _nonempty_string(delta_path):
            errors.append("%s state %s requires delta_path" % (item_id, state))
        else:
            expected_delta = ".cambium/deltas/%s.yaml" % item_id
            if delta_path != expected_delta:
                errors.append("%s delta_path must be exactly %s" %
                              (item_id, expected_delta))
            try:
                delta_file = kblib.managed_repository_path(
                    records["root"], delta_path, ".cambium/deltas",
                    suffixes=(".yaml",), must_exist=True,
                )
                delta_data = kblib.load_yaml_file(delta_file)
                frozen_delta_sha = item.get("delta_sha256")
                if (not isinstance(frozen_delta_sha, str) or
                        not SHA256_RE.fullmatch(frozen_delta_sha)):
                    errors.append("%s state %s requires delta_sha256" %
                                  (item_id, state))
                elif kblib.sha256_file(delta_file) != frozen_delta_sha:
                    errors.append("%s delta bytes do not match frozen "
                                  "delta_sha256" % item_id)
                if delta_data.get("batch") != item_id:
                    errors.append("%s delta document batch must equal %s" %
                                  (item_id, item_id))
                try:
                    current_delta_gate_receipts = delta_gate_receipt_ids(
                        delta_data)
                except ValueError as exc:
                    errors.append("%s %s" % (item_id, exc))
                pages = delta_data.get("pages")
                if not isinstance(pages, list):
                    errors.append("%s delta pages must be an explicit list" % item_id)
                else:
                    delta_paths = []
                    for page_index, page in enumerate(pages):
                        if not isinstance(page, dict):
                            errors.append("%s delta pages[%d] must be a mapping" %
                                          (item_id, page_index))
                            continue
                        page_path = page.get("path")
                        if not _nonempty_string(page_path):
                            errors.append("%s delta pages[%d] has no path" %
                                          (item_id, page_index))
                            continue
                        if page_path in delta_paths:
                            errors.append("%s delta repeats page %s" %
                                          (item_id, page_path))
                        delta_paths.append(page_path)
                        gate_receipts = page.get("gate_receipts")
                        if (not isinstance(gate_receipts, list) or
                                not gate_receipts or
                                not all(_nonempty_string(value)
                                        for value in gate_receipts)):
                            errors.append("%s delta page %s requires gate_receipts" %
                                          (item_id, page_path))
                        else:
                            for receipt_id in gate_receipts:
                                _require_receipt(
                                    catalog, receipt_id,
                                    "%s delta page %s" % (item_id, page_path),
                                    errors,
                                )
                    expected_paths = sorted(item.get("manifest") or [])
                    if sorted(delta_paths) != expected_paths:
                        errors.append("%s delta pages must equal its frozen manifest; "
                                      "found=%r expected=%r" %
                                      (item_id, sorted(delta_paths), expected_paths))
            except (OSError, ValueError, kblib.YamlSubsetError) as exc:
                errors.append("%s delta_path %r is unsafe or missing: %s" %
                              (item_id, delta_path, exc))
        receipts = item.get("batch_receipts")
        if not isinstance(receipts, list) or not receipts or not all(
                _nonempty_string(value) for value in receipts):
            errors.append("%s state %s requires non-empty batch_receipts" %
                          (item_id, state))
        else:
            if len(receipts) != 1:
                errors.append("%s batch_receipts must contain exactly one "
                              "current batch-review gate" % item_id)
            else:
                batch_catalog = (current_catalog
                                 if state == "merge-ready" else catalog)
                errors.extend(batch_review_receipt_errors(
                    batch_catalog, receipts[0], item_id=item_id,
                    task_id=queue.get("task_id"),
                    delta_page_receipt_ids=current_delta_gate_receipts,
                ))
                merge_transition = next((
                    candidate for candidate in reversed(transition_history)
                    if candidate.get("before_state") == "open" and
                    candidate.get("after_state") == "merge-ready"
                ), None)
                if (merge_transition is not None and
                        merge_transition.get("evidence_receipt") != receipts[0]):
                    errors.append(
                        "%s open -> merge-ready transition evidence_receipt "
                        "must equal its batch-review gate %s" %
                        (item_id, receipts[0]))

    if state == "closed":
        if not _valid_timestamp(item.get("closed_at")):
            errors.append("%s closed state requires a timezone-aware closed_at" %
                          item_id)
        seal_state = _closed_bundle_seal_state(item, catalog)
        if seal_state == "mixed":
            errors.append(
                "%s close bundle is partially sealed; the batch-close "
                "gate, Queue consistency snapshot, and delta application "
                "seal together or not at all (K12/07)" % item_id)
        elif seal_state == "sealed":
            errors.extend(_sealed_closed_bundle_errors(
                item, transition, catalog, queue,
            ))
        else:
            errors.extend(_closed_gate_errors(
                item, transition, catalog, queue, accounted_versions,
                root=records.get("root"),
            ))
            errors.extend(_closed_delta_apply_errors(
                item, transition, catalog, queue,
                root=records.get("root"),
            ))

    if state == "cancelled":
        if not _valid_timestamp(item.get("cancelled_at")):
            errors.append("%s cancelled state requires a timezone-aware cancelled_at" %
                          item_id)
        if not _nonempty_string(item.get("cancellation_amendment")):
            errors.append("%s cancelled state requires cancellation_amendment" %
                          item_id)
        amendment_id = item.get("cancellation_amendment")
        amendments = progress.get("amendments")
        matches = []
        if isinstance(amendments, list):
            matches = [entry for entry in amendments
                       if isinstance(entry, dict) and
                       entry.get("id") == amendment_id]
        if len(matches) != 1:
            errors.append("%s cancellation amendment %r must resolve uniquely" %
                          (item_id, amendment_id))
        else:
            amendment = matches[0]
            expected_amendment = {
                "status": "verified",
                "writeback_done": True,
                "operation": "cancel-batch",
                "cancel_batch_id": item_id,
                "affected_batches": [item_id],
            }
            for field, value in expected_amendment.items():
                if amendment.get(field) != value:
                    errors.append("%s cancellation Amendment %s=%r, expected %r" %
                                  (item_id, field, amendment.get(field), value))
            if sorted(amendment.get("affected_pages") or []) != sorted(
                    item.get("manifest") or []):
                errors.append("%s cancellation Amendment affected_pages must "
                              "equal its manifest" % item_id)
            verification_id = amendment.get("verification_receipt")
            _require_receipt(
                catalog, verification_id,
                "%s cancellation Amendment commit" % item_id, errors,
                expected={
                    "tool": "apply_amendment",
                    "tool_version": ANY_PRODUCER_ERA_VERSION,
                    "check": "amendment_transaction",
                    "target": amendment_id,
                    "transaction_phase": "commit",
                    "amendment_id": amendment_id,
                    "operation": "cancel-batch",
                    "actor_role": "integrator",
                },
            )
            if transition is None:
                errors.append("%s cancellation lacks its final transition" %
                              item_id)
            else:
                for field, value in {
                    "tool": "apply_amendment",
                    "check": "queue_transition",
                    "after_state": "cancelled",
                    "amendment_id": amendment_id,
                }.items():
                    if transition.get(field) != value:
                        errors.append("%s cancellation transition %s=%r, "
                                      "expected %r" %
                                      (item_id, field,
                                      transition.get(field), value))
                if transition.get("tool_version") not in \
                        SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS:
                    errors.append(
                        "%s cancellation transition has unsupported "
                        "apply_amendment producer version %r" %
                        (item_id, transition.get("tool_version")))

    timestamp_bindings = []
    opening = next((entry for entry in transition_history
                    if entry.get("before_state") == "queued" and
                    entry.get("after_state") == "open"), None)
    latest_merge = next((entry for entry in reversed(transition_history)
                         if entry.get("before_state") == "open" and
                         entry.get("after_state") == "merge-ready"), None)
    if (latest_merge is not None and state in ("merge-ready", "closed") and
            latest_merge.get("tool") == "update_queue" and
            latest_merge.get("tool_version") == UPDATE_QUEUE_TOOL_VERSION):
        if latest_merge.get("delta_path") != item.get("delta_path"):
            errors.append("%s latest merge-ready transition does not bind "
                          "current delta_path" % item_id)
        if latest_merge.get("delta_sha256") != item.get("delta_sha256"):
            errors.append("%s latest merge-ready transition does not bind "
                          "current delta_sha256" % item_id)
    closing = next((entry for entry in reversed(transition_history)
                    if entry.get("after_state") == "closed"), None)
    cancelling = next((entry for entry in reversed(transition_history)
                       if entry.get("after_state") == "cancelled"), None)
    for field, event in (("opened_at", opening),
                         ("merge_ready_at", latest_merge),
                         ("closed_at", closing),
                         ("cancelled_at", cancelling)):
        if field not in item or event is None:
            continue
        item_time = _timestamp_value(item.get(field))
        event_time = _timestamp_value(event.get("checked_at"))
        if (item_time is not None and event_time is not None and
                item_time != event_time):
            errors.append("%s %s must equal its transition receipt time" %
                          (item_id, field))
        if item_time is not None:
            timestamp_bindings.append((field, item_time))
    chronological = {field: value for field, value in timestamp_bindings}
    for before_field, after_field in (
            ("opened_at", "merge_ready_at"),
            ("opened_at", "cancelled_at"),
            ("merge_ready_at", "closed_at")):
        if (before_field in chronological and after_field in chronological and
                chronological[after_field] < chronological[before_field]):
            errors.append("%s lifecycle time moves backward: %s < %s" %
                          (item_id, after_field, before_field))

    rollback_transitions = [
        entry for entry in transition_history
        if entry.get("before_state") == "merge-ready" and
        entry.get("after_state") == "open"
    ]
    invalidations = item.get("invalidation_history")
    if invalidations is None:
        invalidations = []
    if not isinstance(invalidations, list):
        errors.append("%s invalidation_history must be an explicit list" % item_id)
        invalidations = []
    if len(invalidations) != len(rollback_transitions):
        errors.append("%s invalidation_history has %d record(s), expected %d "
                      "from transition history" %
                      (item_id, len(invalidations), len(rollback_transitions)))
    seen_paths = set()
    seen_receipts = set()
    invalidated_receipts = set()
    previous_rollback_position = -1
    transition_positions = {
        receipt.get("receipt_id"): position
        for position, receipt in enumerate(transition_history)
        if isinstance(receipt, dict) and
        _nonempty_string(receipt.get("receipt_id"))
    }
    for index, record in enumerate(invalidations):
        label = "%s invalidation_history[%d]" % (item_id, index)
        if not isinstance(record, dict):
            errors.append("%s must be a mapping" % label)
            continue
        missing = sorted(INVALIDATION_FIELDS - set(record))
        extra = sorted(set(record) - INVALIDATION_FIELDS -
                       INVALIDATION_APPLIED_ROLLBACK_FIELDS)
        applied_present = INVALIDATION_APPLIED_ROLLBACK_FIELDS & set(record)
        if missing:
            errors.append("%s misses explicit field(s): %s" %
                          (label, ", ".join(missing)))
        if extra:
            errors.append("%s has unsupported field(s): %s" %
                          (label, ", ".join(extra)))
        if applied_present and applied_present != \
                INVALIDATION_APPLIED_ROLLBACK_FIELDS:
            errors.append(
                "%s records an applied-delta rollback but misses explicit "
                "field(s): %s" %
                (label, ", ".join(sorted(
                    INVALIDATION_APPLIED_ROLLBACK_FIELDS - applied_present))))
        for field in sorted(applied_present):
            if not _nonempty_string(record.get(field)):
                errors.append("%s %s must be non-empty" % (label, field))
        transition = (rollback_transitions[index]
                      if index < len(rollback_transitions) else None)
        if applied_present == INVALIDATION_APPLIED_ROLLBACK_FIELDS and all(
                _nonempty_string(record.get(field))
                for field in INVALIDATION_APPLIED_ROLLBACK_FIELDS):
            errors.extend(_applied_rollback_restore_errors(
                label, record, transition, catalog, item_id))
        receipt_id = record.get("transition_receipt")
        if not _nonempty_string(receipt_id):
            errors.append("%s transition_receipt must be non-empty" % label)
        elif receipt_id in seen_receipts:
            errors.append("%s repeats transition receipt %s" %
                          (label, receipt_id))
        else:
            seen_receipts.add(receipt_id)
        if transition is not None:
            if transition.get("receipt_id") != receipt_id:
                errors.append("%s does not bind its ordered rollback transition" %
                              label)
            if transition.get("invalidation") != record:
                errors.append("%s differs from its transition receipt binding" %
                              label)
            record_time = _timestamp_value(record.get("invalidated_at"))
            transition_time = _timestamp_value(transition.get("checked_at"))
            if record_time is None or record_time != transition_time:
                errors.append("%s invalidated_at must equal transition time" %
                              label)
        if not _nonempty_string(record.get("reason")):
            errors.append("%s reason must be non-empty" % label)
        delta_sha = record.get("delta_sha256")
        if not isinstance(delta_sha, str) or not SHA256_RE.fullmatch(delta_sha):
            errors.append("%s delta_sha256 is invalid" % label)
        batch_receipts = record.get("batch_receipts")
        if (not isinstance(batch_receipts, list) or not batch_receipts or
                not all(_nonempty_string(value) for value in batch_receipts)):
            errors.append("%s batch_receipts must be a non-empty string list" %
                          label)
        elif len(batch_receipts) != len(set(batch_receipts)):
            errors.append("%s batch_receipts must be unique" % label)
        else:
            for batch_receipt in batch_receipts:
                _require_receipt(
                    catalog, batch_receipt, "%s batch evidence" % label,
                    errors, expected={
                        "check": "batch_gate",
                        "target": item_id,
                    },
                )
            invalidated_receipts.update(batch_receipts)
        delta_gate_receipts = record.get("delta_gate_receipts")
        if (not isinstance(delta_gate_receipts, list) or
                not delta_gate_receipts or
                not all(_nonempty_string(value)
                        for value in delta_gate_receipts)):
            errors.append("%s delta_gate_receipts must be a non-empty string "
                          "list" % label)
        elif (len(delta_gate_receipts) != len(set(delta_gate_receipts)) or
              delta_gate_receipts != sorted(delta_gate_receipts)):
            errors.append("%s delta_gate_receipts must be sorted and unique" %
                          label)
        else:
            for gate_receipt in delta_gate_receipts:
                _require_receipt(catalog, gate_receipt,
                                 "%s delta page evidence" % label, errors)
            invalidated_receipts.update(delta_gate_receipts)
        revalidation_receipts = record.get("revalidation_receipts")
        if (not isinstance(revalidation_receipts, list) or
                not all(_nonempty_string(value)
                        for value in revalidation_receipts)):
            errors.append("%s revalidation_receipts must be an explicit string "
                          "list" % label)
        elif len(revalidation_receipts) != len(set(revalidation_receipts)):
            errors.append("%s revalidation_receipts must be unique" % label)
        else:
            for gate_receipt in revalidation_receipts:
                _require_receipt(catalog, gate_receipt,
                                 "%s revalidation evidence" % label, errors)
            invalidated_receipts.update(revalidation_receipts)
        if transition is not None:
            rollback_position = transition_positions.get(
                transition.get("receipt_id"))
            if rollback_position is not None:
                expected_revalidation = []
                for candidate in transition_history[
                        previous_rollback_position + 1:rollback_position]:
                    if (candidate.get("before_state") ==
                            candidate.get("after_state") and
                            candidate.get("before_hold_state") ==
                            "revalidation-required" and
                            candidate.get("after_hold_state") == "none"):
                        evidence = candidate.get("evidence_receipt")
                        if _nonempty_string(evidence):
                            expected_revalidation.append(evidence)
                if revalidation_receipts != expected_revalidation:
                    errors.append("%s revalidation_receipts do not exactly bind "
                                  "this invalidated attempt" % label)
                previous_rollback_position = rollback_position
        archive_path = record.get("delta_archive_path")
        if not _nonempty_string(archive_path):
            errors.append("%s delta_archive_path must be non-empty" % label)
            continue
        if archive_path in seen_paths:
            errors.append("%s repeats delta archive path %s" %
                          (label, archive_path))
        seen_paths.add(archive_path)
        try:
            archived = kblib.managed_repository_path(
                records["root"], archive_path, ".cambium/receipts",
                suffixes=(".yaml",), must_exist=True,
            )
            if kblib.sha256_file(archived) != delta_sha:
                errors.append("%s archived delta bytes differ from delta_sha256" %
                              label)
            archived_data = kblib.load_yaml_file(archived)
            if archived_data.get("batch") != item_id:
                errors.append("%s archived delta batch does not match item" % label)
            try:
                archived_gate_receipts = delta_gate_receipt_ids(archived_data)
                if delta_gate_receipts != archived_gate_receipts:
                    errors.append("%s delta_gate_receipts do not exactly match "
                                  "the archived delta" % label)
            except ValueError as exc:
                errors.append("%s archived delta gate evidence is invalid: %s" %
                              (label, exc))
        except (OSError, ValueError, kblib.YamlSubsetError) as exc:
            errors.append("%s delta archive is unsafe or missing: %s" %
                          (label, exc))

    current_batch_receipts = item.get("batch_receipts")
    if isinstance(current_batch_receipts, list):
        replayed = sorted(set(current_batch_receipts).intersection(
            invalidated_receipts))
        if replayed:
            errors.append("%s current batch_receipts reuse invalidated ID(s): %s" %
                          (item_id, ", ".join(replayed)))
    replayed = sorted(set(current_delta_gate_receipts).intersection(
        invalidated_receipts))
    if replayed:
        errors.append("%s current delta gate_receipts reuse invalidated ID(s): %s" %
                      (item_id, ", ".join(replayed)))
    last_rollback_position = max(
        (transition_positions.get(receipt.get("receipt_id"), -1)
         for receipt in rollback_transitions), default=-1)
    for candidate in transition_history[last_rollback_position + 1:]:
        if (candidate.get("before_state") == candidate.get("after_state") and
                candidate.get("before_hold_state") == "revalidation-required" and
                candidate.get("after_hold_state") == "none" and
                candidate.get("evidence_receipt") in invalidated_receipts):
            errors.append("%s current revalidation admission reuses invalidated "
                          "receipt %s" %
                          (item_id, candidate.get("evidence_receipt")))
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
                     gate_evidence_errors=
                     metadata_gate_runtime.persisted_property_gate_errors,
                     active_standards_state_override=None,
                     authorized_profile_view=None,
                     authorized_active_standards_view=None):
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


def make_check_receipt(result, outcome, details, mode,
                       confirmation_receipt=None, runtime_errors=None,
                       maintenance_context=None,
                       standards_revalidation_context=None,
                       hub_page_candidates=None,
                       activation_context=None,
                       readback_context=None,
                       piece_context=None,
                       piece_ack_context=None,
                       phase_context=None,
                       phase_ack_context=None,
                       resume_activation_contexts=None):
    """Build the canonical receipt for one already-evaluated Queue result.

    This is the canonical construction path for ``check_queue`` receipt bytes.
    A caller that composes a larger gate while holding the shared runtime lock
    may use it only after calling :func:`validate_runtime` on those exact
    locked bytes.  Centralization keeps schema/state bindings consistent; it
    does not authenticate the caller or stop another writer copying labels.
    """
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, GATE_CHECK, QUEUE_PATH, outcome,
        details, 1,
    )
    if result.get("queue_sha256"):
        receipt["queue_check_mode"] = mode
        gate_id = queue_gate_id_for_mode(mode)
        if gate_id is not None:
            receipt["gate_id"] = gate_id
        if confirmation_receipt:
            receipt["confirmation_receipt"] = confirmation_receipt
        receipt["required_queue_sha256"] = result["queue_sha256"]
        receipt["coverage_ledger_sha256"] = result.get("coverage_sha256")
        receipt["progress_ledger_sha256"] = result.get("progress_sha256")
        receipt["queue_revision"] = result["queue"].get("queue_revision")
        receipt["queue_state_revision"] = result["queue"].get("state_revision")
        receipt["remaining_required_work_units"] = result.get("remaining")
        receipt["task_id"] = result["queue"].get("task_id")
        receipt["standards_version"] = result["queue"].get(
            "standards_version")
        receipt["selected_profile_manifest"] = result["queue"].get(
            "selected_profile_manifest")
        if mode.startswith("require-ready:"):
            # K13/10 hands the hub pages this batch creates to the
            # integrator's post-merge synchronization step; the durable
            # record travels with the activation receipt.
            receipt["hub_page_candidates"] = list(hub_page_candidates or [])
            if activation_context:
                receipt.update(card_activation.activation_receipt_binding(
                    activation_context))
        if mode.startswith("deliver-activation-piece:") and piece_context:
            receipt.update(card_activation.piece_receipt_binding(
                piece_context))
        if mode.startswith("ack-activation-piece:") and piece_ack_context:
            receipt.update(card_activation.piece_ack_receipt_binding(
                piece_ack_context))
        if mode.startswith("deliver-phase:") and phase_context:
            receipt.update(card_activation.phase_receipt_binding(
                phase_context))
        if mode.startswith("ack-activation-phase:") and phase_ack_context:
            receipt.update(card_activation.phase_ack_receipt_binding(
                phase_ack_context))
        if mode.startswith("deliver-readback:") and readback_context:
            receipt.update(card_activation.readback_receipt_binding(
                readback_context))
        if mode == "consistency" and outcome == "pass":
            receipt["repository_snapshot_sha256"] = \
                kblib.repository_snapshot_sha256(result["root"])
        if maintenance_context:
            receipt.update(maintenance_context)
        if standards_revalidation_context:
            receipt.update(standards_revalidation_context)
        if mode == "resume-status":
            progress = result.get("progress") or {}
            contract = progress.get("contract") if isinstance(
                progress.get("contract"), dict) else {}
            checkpoint = progress.get("checkpoint")
            receipt["task_state"] = progress.get("task_state")
            receipt["active_card_context_deliveries"] = [
                {
                    "batch_id": delivery.get("batch_id"),
                    "parent_activation_receipt": delivery.get(
                        "parent_activation_receipt"),
                    **card_activation.activation_receipt_binding(delivery),
                }
                for delivery in (resume_activation_contexts or [])
            ]
            receipt["objective"] = contract.get("objective")
            receipt["exclusions"] = contract.get("exclusions")
            receipt["checkpoint"] = checkpoint if isinstance(
                checkpoint, dict) else None
            receipt["managed_deltas"] = result.get("managed_deltas", [])
            receipt["applied_delta_receipts"] = result.get(
                "applied_delta_receipts", [])
            receipt["pending_delta_applies"] = result.get(
                "pending_delta_applies", {})
            receipt["batch_close_recovery"] = result.get(
                "batch_close_recovery", {})
            receipt["writer_locks"] = result.get("writer_locks", [])
            task_runtime = result.get("task_runtime") or {}
            receipt["checkpoint_binding"] = task_runtime.get(
                "checkpoint_binding")
            receipt["pending_guidance"] = task_runtime.get(
                "pending_guidance", [])
            receipt["pending_amendments"] = task_runtime.get(
                "pending_amendments", [])
            # Derived boundary, never stored state: see
            # ``_last_reconciled_guidance_id``.
            receipt["last_reconciled_guidance_id"] = task_runtime.get(
                "last_reconciled_guidance_id")
            receipt["standards_revalidation_outstanding"] = result.get(
                "standards_revalidation_outstanding", {})
            receipt["standards_revalidation_barriers"] = result.get(
                "standards_revalidation_barriers", {})
            receipt["batch_work_specs"] = [
                {
                    "batch_id": item_id,
                    "work_spec_path": item.get("work_spec_path"),
                    "work_spec_sha256": item.get("work_spec_sha256"),
                }
                for item_id, item in sorted(
                    (result.get("items_by_id") or {}).items(),
                    key=lambda pair: (
                        pair[1].get("order", sys.maxsize), pair[0]),
                )
            ]
            candidate_context = result.get("maintenance_candidate_context")
            if isinstance(candidate_context, dict):
                receipt["maintenance_candidate_state"] = {
                    "sha256": candidate_context.get(
                        "candidate_state_sha256"),
                    "total": len(candidate_context.get("records") or []),
                    "selected_candidate_ids": candidate_context.get(
                        "selected_ids") or [],
                    "deferred_candidate_ids": candidate_context.get(
                        "deferred_ids") or [],
                }
            receipt["next_action"] = _resume_next_action(
                result, runtime_errors or [])
    return receipt


def _emit_json_receipts(receipts):
    """Write this run's receipt-shaped tool results to real stdout.

    ``--json`` publishes the receipts plus any transient Card payload that a
    Host must inject. The payload is deliberately absent from durable JSONL;
    its content-addressed manifest remains in the receipt. Otherwise this is
    not a schema projection:
    ``Tools/schemas/receipt.template.jsonl`` says in its own text that its
    examples are "not the complete set", and this tool's per-mode extension
    fields (the whole ``resume-status`` block, the maintenance and Standards
    revalidation contexts) are exactly the part a whitelist would drop.
    Serialization goes through the shared ``kblib.canonical_json_bytes``;
    this module owns no serializer. A run that produced no receipt writes
    nothing, so the settled rejection shape -- empty stdout, one line of
    reason on stderr, exit 1 -- is untouched.
    """
    if not receipts:
        return
    sys.stdout.write(
        kblib.canonical_json_bytes(list(receipts)).decode("utf-8") + "\n")


def _delivery_result(receipt, activation_context=None, readback_context=None,
                     piece_context=None, phase_context=None,
                     resume_activation_contexts=None):
    """Attach transient bytes to the tool result, never the receipt register."""
    emitted = dict(receipt)
    if activation_context and "activation_delivery_payload" in \
            activation_context:
        emitted["activation_delivery_payload"] = activation_context[
            "activation_delivery_payload"]
    if readback_context:
        emitted["readback_delivery_payload"] = readback_context.get(
            "readback_delivery_payload")
    if phase_context:
        emitted["activation_phase_payload"] = phase_context.get(
            "activation_phase_payload")
    if piece_context:
        emitted["activation_piece_payload"] = piece_context.get(
            "activation_piece_payload")
    if resume_activation_contexts:
        persisted = emitted.get("active_card_context_deliveries") or []
        emitted["active_card_context_deliveries"] = [
            {
                **dict(binding),
                # A v3 resume re-freezes the manifest for the new context and
                # names the pieces it must pull; the bytes travel one budgeted
                # piece at a time, never inside this status result.
                **({"activation_delivery_payload": delivery[
                    "activation_delivery_payload"]}
                   if "activation_delivery_payload" in delivery else {}),
            }
            for binding, delivery in zip(
                persisted, resume_activation_contexts)
        ]
    return emitted


def _write_receipt(root, relative_path, result, outcome, details, mode,
                   confirmation_receipt=None, runtime_errors=None,
                   maintenance_context=None,
                   standards_revalidation_context=None,
                   hub_page_candidates=None, activation_context=None,
                   readback_context=None, piece_context=None,
                   piece_ack_context=None, phase_context=None,
                   phase_ack_context=None, resume_activation_contexts=None,
                   build_unwritten=False):
    """Append the small receipt and return its delivery-enriched tool result.

    Without ``--receipts`` there is no JSONL target and nothing is built, so
    a run that asks for nothing pays for nothing -- unchanged. ``--json``
    still needs the object itself, and passes ``build_unwritten=True`` to get
    it; the receipt is then constructed and returned but never written, which
    keeps ``--json`` a pure reader of what this invocation decided.
    """
    if not relative_path:
        if not build_unwritten:
            return None
        receipt = make_check_receipt(
            result, outcome, details, mode,
            confirmation_receipt=confirmation_receipt,
            runtime_errors=runtime_errors,
            maintenance_context=maintenance_context,
            standards_revalidation_context=standards_revalidation_context,
            hub_page_candidates=hub_page_candidates,
            activation_context=activation_context,
            readback_context=readback_context,
            piece_context=piece_context,
            piece_ack_context=piece_ack_context,
            phase_context=phase_context,
            phase_ack_context=phase_ack_context,
            resume_activation_contexts=resume_activation_contexts,
        )
        return _delivery_result(
            receipt, activation_context, readback_context, piece_context,
            phase_context, resume_activation_contexts)
    path = kblib.managed_repository_path(
        root, relative_path, ".cambium/receipts",
        suffixes=(".jsonl",), must_exist=False,
    )
    receipt = make_check_receipt(
        result, outcome, details, mode,
        confirmation_receipt=confirmation_receipt,
        runtime_errors=runtime_errors,
        maintenance_context=maintenance_context,
        standards_revalidation_context=standards_revalidation_context,
        hub_page_candidates=hub_page_candidates,
        activation_context=activation_context,
        readback_context=readback_context,
        piece_context=piece_context,
        piece_ack_context=piece_ack_context,
        phase_context=phase_context,
        phase_ack_context=phase_ack_context,
        resume_activation_contexts=resume_activation_contexts,
    )
    kblib.write_receipts(path, [receipt])
    return _delivery_result(
        receipt, activation_context, readback_context, piece_context,
        phase_context, resume_activation_contexts)


def _maintenance_gate_inventory(result):
    """Classify persisted maintenance gates against the exact current bytes."""
    progress = result.get("progress") or {}
    contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    if contract.get("completion_semantics") != "maintenance":
        return {"compatible": [], "stale": [], "selected": None}
    task_state = progress.get("task_state")
    bound_progress_sha = result.get("progress_sha256")
    if task_state == "complete":
        latest_transition = (result.get("task_runtime") or {}).get(
            "latest_receipt") or {}
        if (latest_transition.get("after_task_state") == "complete" and
                latest_transition.get("completion_semantics") ==
                "maintenance"):
            # A consumed gate intentionally binds the bytes immediately
            # before the terminal transition.  The transition receipt is the
            # durable bridge from those bytes to current Progress.
            bound_progress_sha = latest_transition.get(
                "before_progress_sha256")
    expected = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "check": "required_queue",
        "queue_check_mode": "require-maintenance-complete",
        "result": "pass",
        "invalidated_by": None,
        "task_id": progress.get("task_id"),
        "completion_semantics": "maintenance",
        "scope_version": contract.get("scope_version"),
        "standards_version": contract.get("standards_version"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"),
        "queue_revision": (result.get("queue") or {}).get("queue_revision"),
        "queue_state_revision":
            (result.get("queue") or {}).get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": bound_progress_sha,
        "remaining_required_work_units": 0,
    }
    compatible = []
    stale = []
    current_catalog = current_receipt_catalog(result)
    current_result = dict(result, receipt_catalog=current_catalog)
    for receipt_id, (_, receipt) in sorted(current_catalog.items()):
        if (receipt.get("tool") != TOOL or
                receipt.get("check") != "required_queue" or
                receipt.get("queue_check_mode") !=
                "require-maintenance-complete"):
            continue
        mismatches = [field for field, value in expected.items()
                      if receipt.get(field) != value]
        gate_errors = []
        context = None
        if not mismatches:
            gate_errors, context = _maintenance_completion_gate_errors(
                result.get("root"), current_result,
                receipt.get("budget_manifest_receipt"),
                receipt.get("ledger_advance_receipt"),
                receipt.get("watermark_advance_receipt"),
                allow_complete=task_state == "complete",
            )
            if context is not None:
                mismatches.extend(
                    field for field, value in context.items()
                    if receipt.get(field) != value
                )
            gate_errors.extend(_maintenance_gate_time_errors(result, receipt))
        if mismatches or gate_errors or not _valid_timestamp(
                receipt.get("checked_at")):
            stale.append({
                "receipt_id": receipt_id,
                "mismatches": sorted(set(mismatches)),
                "errors": gate_errors,
            })
        else:
            compatible.append({
                "receipt_id": receipt_id,
                "checked_at": receipt.get("checked_at"),
            })
    compatible.sort(key=lambda entry: (
        _timestamp_value(entry["checked_at"]), entry["receipt_id"],
    ))
    selected = compatible[-1]["receipt_id"] if compatible else None
    if task_state == "complete":
        completion = progress.get("maintenance_completion")
        consumed = (completion.get("completion_gate_receipt")
                    if isinstance(completion, dict) else None)
        if consumed in {entry["receipt_id"] for entry in compatible}:
            # Once consumed, Progress—not register append order—owns which
            # compatible gate explains the terminal state.
            selected = consumed
    return {
        "compatible": compatible,
        "stale": stale,
        "selected": selected,
    }


def _batch_close_update_command(result, selected):
    """Render the exact close command bound by one recovered gate bundle."""
    queue = result.get("queue") or {}
    values = {
        "root": result.get("root"),
        "batch": selected.get("batch"),
        "queue_consistency": selected.get("queue_consistency_receipt"),
        "close_gate": selected.get("close_gate_receipt"),
        "delta_apply": selected.get("delta_apply_receipt"),
        "state_revision": queue.get("state_revision"),
        "queue_sha": result.get("queue_sha256"),
    }
    return (
        "python3 Tools/update_queue.py {root} --id {batch} "
        "--transition closed --gate-receipt {queue_consistency} "
        "--close-gate-receipt {close_gate} "
        "--delta-apply-receipt {delta_apply} "
        "--expected-state-revision {state_revision} "
        "--expected-sha256 {queue_sha} --actor-role integrator --apply"
    ).format(**{
        key: shlex.quote(str(value)) for key, value in values.items()
    })


def _batch_close_recovery_inventory(result):
    """Find a persisted, current-compatible close bundle for resume.

    This is a read-only projection over canonical state, the complete receipt
    catalog, and the live repository-content snapshot.  It never trusts the
    former producer's stdout.  Multiple valid bundles are ordered by their
    checked instant and then receipt ID, producing one deterministic latest
    choice.  Invalid or stale lookalikes remain visible but are never selected.
    """
    inventory = {
        "status": "not-applicable",
        "batch": None,
        "repository_snapshot_sha256": None,
        "compatible": [],
        "stale": [],
        "selected": None,
        "selection_rule": "latest-checked-at-then-receipt-id",
        "update_queue_command": None,
        "errors": [],
    }
    if result.get("writer_locks"):
        inventory["status"] = "writer-lock"
        return inventory
    pending = result.get("pending_delta_applies") or {}
    current = pending.get("current") or []
    if pending.get("status") == "repair":
        inventory["status"] = "runtime-repair"
        return inventory
    if pending.get("status") != "close-required" or len(current) != 1:
        return inventory

    applied = current[0]
    batch = applied.get("batch")
    inventory["batch"] = batch
    item = (result.get("items_by_id") or {}).get(batch)
    if not isinstance(item, dict) or item.get("state") != "merge-ready":
        inventory["status"] = "runtime-repair"
        inventory["errors"].append(
            "current applied batch is not merge-ready")
        return inventory
    try:
        snapshot = kblib.repository_snapshot_sha256(result.get("root"))
    except (OSError, ValueError) as exc:
        inventory["status"] = "snapshot-unavailable"
        inventory["errors"].append(str(exc))
        return inventory
    inventory["repository_snapshot_sha256"] = snapshot

    compatible_apply_ids = set(applied.get("compatible_receipts") or [])
    catalog = current_receipt_catalog(result)
    for receipt_id, (relative, receipt) in sorted(catalog.items()):
        if not isinstance(receipt, dict):
            continue
        if not (receipt.get("tool") == BATCH_CLOSE_TOOL and
                receipt.get("check") == "batch_close_gate" and
                (receipt.get("target") == batch or
                 receipt.get("batch_id") == batch)):
            continue
        queue_consistency = receipt.get("queue_consistency_receipt")
        delta_apply = receipt.get("delta_apply_receipt")
        candidate_errors = []
        checked_at = receipt.get("checked_at")
        checked_value = _timestamp_value(checked_at)
        if checked_value is None:
            candidate_errors.append(
                "checked_at must be a timezone-aware RFC 3339 timestamp")
        if delta_apply not in compatible_apply_ids:
            candidate_errors.append(
                "delta_apply_receipt is not current-compatible")
        candidate_errors.extend(close_gate_receipt_errors(
            catalog, receipt_id,
            item_id=batch,
            root=result.get("root"),
            task_id=(result.get("queue") or {}).get("task_id"),
            queue_revision=(result.get("queue") or {}).get("queue_revision"),
            queue_state_revision=(result.get("queue") or {}).get(
                "state_revision"),
            required_queue_sha256=result.get("queue_sha256"),
            coverage_ledger_sha256=result.get("coverage_sha256"),
            progress_ledger_sha256=result.get("progress_sha256"),
            delta_sha256=item.get("delta_sha256"),
            queue_consistency_receipt=queue_consistency,
            delta_apply_receipt=delta_apply,
            work_spec_path=item.get("work_spec_path"),
            work_spec_sha256=item.get("work_spec_sha256"),
            manifest=item.get("manifest"),
            selected_profile_manifest=(result.get("queue") or {}).get(
                "selected_profile_manifest"),
            profile_snapshot_sha256=(result.get(
                "_profile_authorized_view") or {}).get(
                    "profile_snapshot_sha256"),
            profile_contract_fingerprint=(result.get(
                "_profile_authorized_view") or {}).get(
                    "profile_contract_fingerprint"),
            profile_load_inputs_sha256=(result.get(
                "_profile_authorized_view") or {}).get(
                    "profile_load_inputs_sha256"),
            authorized_profile_contract=(result.get(
                "_profile_authorized_view") or {}).get("_contract"),
            current_repository_snapshot_sha256=snapshot,
        ))
        entry = {
            "batch": batch,
            "receipt_path": relative,
            "checked_at": checked_at,
            "queue_consistency_receipt": queue_consistency,
            "close_gate_receipt": receipt_id,
            "delta_apply_receipt": delta_apply,
            "repository_snapshot_sha256": receipt.get(
                "merged_snapshot_sha256"),
        }
        if candidate_errors:
            entry["errors"] = sorted(set(candidate_errors))
            inventory["stale"].append(entry)
        else:
            entry["_checked_value"] = checked_value
            inventory["compatible"].append(entry)

    inventory["compatible"].sort(key=lambda entry: (
        entry["_checked_value"], entry["close_gate_receipt"]))
    inventory["stale"].sort(key=lambda entry: entry["close_gate_receipt"])
    if inventory["compatible"]:
        selected = dict(inventory["compatible"][-1])
        selected.pop("_checked_value", None)
        for entry in inventory["compatible"]:
            entry.pop("_checked_value", None)
        inventory["selected"] = selected
        inventory["status"] = "ready-to-close"
        inventory["update_queue_command"] = _batch_close_update_command(
            result, selected)
    else:
        inventory["status"] = "gate-required"
    return inventory


def _actionable_revalidation_batches(result):
    """Outstanding batches whose aggregate this producer would still admit.

    ``standards_revalidation_outstanding`` reports every batch whose plan
    bindings are unconsumed, terminal ones included, because that is a true
    statement about this runtime's history and dropping it would hide it.
    A *recommended action* is a different claim: it asserts the named tool
    would run.  So this filters on
    :func:`standards_revalidation_producer_eligibility` -- the same
    predicate ``--require-revalidation`` itself applies -- rather than on a
    second, parallel notion of eligibility that could drift from it.  A
    token naming a batch the producer declines is not a recovery action; it
    is a dead end that masks the real next step for as long as the runtime
    lives.
    """
    outstanding = result.get("standards_revalidation_outstanding") or {}
    items = result.get("items_by_id") or {}
    return sorted(
        (batch_id for batch_id in outstanding
         if standards_revalidation_producer_eligibility(
             result, batch_id) is None),
        key=lambda batch_id: (
            (items.get(batch_id) or {}).get("order", sys.maxsize), batch_id),
    )


def _resume_recommendation(result, errors):
    locks = result.get("writer_locks") or []
    if locks:
        return ("verify that no writer process remains, reconcile Queue/Progress/"
                "deltas, and remove only a proven-stale lock; do not initialize "
                "or overwrite the runtime")
    if errors:
        return ("repair and reconcile the existing runtime before continuing; "
                "do not initialize or overwrite it")
    progress = result.get("progress") or {}
    task_state = progress.get("task_state")
    items = result.get("items_by_id") or {}
    pending_applies = result.get("pending_delta_applies") or {}
    current_applies = pending_applies.get("current") or []
    if (pending_applies.get("status") == "close-required" and
            len(current_applies) == 1):
        applied = current_applies[0]
        if task_state == "paused":
            return ("resume the paused task, then rerun resume-status and "
                    "close applied batch %s with receipt %s before any other "
                    "Queue/Coverage write" %
                    (applied.get("batch"),
                     applied.get("selected_receipt")))
        if task_state == "blocked":
            return ("resolve the blocked task state, then rerun resume-status "
                    "and close applied batch %s with receipt %s before any "
                    "other Queue/Coverage write" %
                    (applied.get("batch"),
                     applied.get("selected_receipt")))
        close_recovery = result.get("batch_close_recovery") or \
            _batch_close_recovery_inventory(result)
        selected = close_recovery.get("selected")
        if selected:
            return ("close applied batch %s with the recovered current bundle; "
                    "run: %s" %
                    (applied.get("batch"),
                     close_recovery.get("update_queue_command")))
        return ("run check_batch_close.py for applied batch %s before any "
                "Queue close, control input, another batch, or terminal "
                "archival" % applied.get("batch"))
    in_flight = [item_id for item_id, item in items.items()
                 if item.get("state") in ACTIVE_STATES]
    if task_state in ("complete", "cancelled"):
        return ("the existing task is terminal; preserve any unfinished batch "
                "or control records as incomplete history, then explicitly "
                "archive or roll over the runtime")
    if task_state in ("paused", "blocked"):
        return ("resume or resolve the existing %s task from its checkpoint; "
                "do not initialize a new task" % task_state)
    if task_state == "completion-candidate":
        return ("preserve the frozen candidate and run the Terminal Audit; "
                "do not activate new work or initialize a new task")
    incomplete_deltas = sorted(
        (entry for entry in result.get("managed_deltas", [])
         if entry.get("state") == "open" and
         entry.get("handoff_status") == "incomplete"),
        key=lambda entry: ((items.get(entry.get("batch")) or {}).get(
            "order", sys.maxsize), entry.get("batch") or ""),
    )
    if incomplete_deltas:
        return ("repair routed-gap settlement in the managed Delta for batch "
                "%s before batch review or merge-ready admission" %
                incomplete_deltas[0].get("batch"))
    actionable_revalidation = _actionable_revalidation_batches(result)
    if actionable_revalidation:
        return ("run the current boundary gates for batch %s, aggregate them "
                "with check_queue.py --require-revalidation, then consume "
                "that receipt before merge/apply/close" %
                actionable_revalidation[0])
    if in_flight:
        return ("resume the existing task and reconcile in-flight batch(es) %s "
                "before starting new work" % ",".join(sorted(in_flight)))
    queue_items = (result.get("queue") or {}).get("required_queue") or []
    if result.get("remaining") == 0 and queue_items:
        semantics = ((progress.get("contract") or {}).get(
            "completion_semantics") if isinstance(
                progress.get("contract"), dict) else None)
        if semantics == "maintenance":
            inventory = _maintenance_gate_inventory(result)
            if inventory.get("selected"):
                return (
                    "consume current maintenance completion gate %s with "
                    "update_task.py; do not regenerate state or Terminal Proof" %
                    inventory["selected"]
                )
            return (
                "run check_queue.py --require-maintenance-complete with the "
                "current budget-manifest, Ledger-advance, and watermark-advance "
                "receipts; then consume that gate with update_task.py"
            )
        return (
            "enter completion-candidate with a current require-complete "
            "receipt, then run the build Terminal Audit"
        )
    if result.get("ready"):
        return ("resume the existing task with ready batch(es) %s; do not "
                "initialize a new task" % ",".join(result["ready"]))
    if not queue_items:
        return ("resume the existing task by materializing its Required Queue; "
                "do not initialize a second task over it")
    return ("resume or resolve the existing task's recorded holds or dependencies; "
            "do not initialize a new task")


def _resume_next_action(result, errors):
    """Return one stable machine-readable recovery action token."""
    if result.get("writer_locks"):
        return "reconcile-interrupted-write"
    if errors:
        return "repair-runtime"
    progress = result.get("progress") or {}
    task_state = progress.get("task_state")
    items = result.get("items_by_id") or {}
    applied = [entry for entry in result.get("applied_delta_receipts", [])
               if entry.get("selected_receipt") and
               (items.get(entry.get("batch")) or {}).get("hold_state") ==
               "none"]
    if applied:
        selected = applied[0]
        if task_state == "paused":
            return "resume-paused-task"
        if task_state == "blocked":
            return "resolve-blocked-task"
        recovery = result.get("batch_close_recovery") or \
            _batch_close_recovery_inventory(result)
        if recovery.get("status") in (
                "snapshot-unavailable", "runtime-repair"):
            return "repair-runtime"
        bundle = recovery.get("selected")
        if bundle:
            return "close-applied-batch:%s:%s:%s:%s" % (
                bundle["batch"], bundle["queue_consistency_receipt"],
                bundle["close_gate_receipt"],
                bundle["delta_apply_receipt"],
            )
        return "run-batch-close-gate:%s" % selected["batch"]
    if task_state in ("complete", "cancelled"):
        return "archive-terminal-runtime"
    runtime = result.get("task_runtime") or {}
    if runtime.get("pending_guidance") or runtime.get("pending_amendments"):
        return "reconcile-control-input"
    if task_state == "paused":
        return "resume-paused-task"
    if task_state == "blocked":
        return "resolve-blocked-task"
    incomplete_deltas = sorted(
        (entry for entry in result.get("managed_deltas", [])
         if entry.get("state") == "open" and
         entry.get("handoff_status") == "incomplete"),
        key=lambda entry: ((items.get(entry.get("batch")) or {}).get(
            "order", sys.maxsize), entry.get("batch") or ""),
    )
    if incomplete_deltas:
        return "repair-delta-settlement:%s" % \
            incomplete_deltas[0].get("batch")
    actionable_revalidation = _actionable_revalidation_batches(result)
    if actionable_revalidation:
        return "run-standards-revalidation:%s" % actionable_revalidation[0]
    if task_state == "completion-candidate":
        return "run-terminal-audit"
    merge_ready = sorted(
        (item for item in items.values()
         if item.get("state") == "merge-ready" and
         item.get("hold_state") == "none"),
        key=lambda item: (item.get("order", sys.maxsize), item.get("id", "")),
    )
    if merge_ready:
        return "apply-delta:%s" % merge_ready[0]["id"]
    handoff_ids = {
        entry.get("batch") for entry in result.get("managed_deltas", [])
        if entry.get("state") == "open" and
        entry.get("handoff_status") == "candidate"
    }
    handoffs = sorted(
        (item for item_id, item in items.items()
         if item_id in handoff_ids and item.get("hold_state") == "none"),
        key=lambda item: (item.get("order", sys.maxsize), item.get("id", "")),
    )
    if handoffs:
        return "admit-delta:%s" % handoffs[0]["id"]
    in_flight = sorted(
        item_id for item_id, item in items.items()
        if item.get("state") in ACTIVE_STATES
    )
    if in_flight:
        return "resume-in-flight-batches:%s" % ",".join(in_flight)
    if result.get("remaining") == 0 and items:
        contract = progress.get("contract") if isinstance(
            progress.get("contract"), dict) else {}
        if contract.get("completion_semantics") == "maintenance":
            inventory = _maintenance_gate_inventory(result)
            if inventory.get("selected"):
                return "complete-maintenance-task:%s" % inventory["selected"]
            return "run-maintenance-completion-gate"
        return "enter-completion-candidate"
    if result.get("ready"):
        return "activate-ready-batch:%s" % ",".join(result["ready"])
    if not items:
        return "materialize-required-queue"
    return "resolve-holds-dependencies"


def _print_resume_status(result, errors):
    queue = result.get("queue") or {}
    progress = result.get("progress") or {}
    contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    checkpoint = progress.get("checkpoint") if isinstance(
        progress.get("checkpoint"), dict) else {}
    terminal_audit = progress.get("terminal_audit") if isinstance(
        progress.get("terminal_audit"), dict) else {}
    maintenance_completion = (progress.get("maintenance_completion")
                              if isinstance(
                                  progress.get("maintenance_completion"), dict)
                              else {})
    task_runtime = result.get("task_runtime") or {}
    items = result.get("items_by_id") or {}
    print("resume_status:")
    print("  task_id=%s" % queue.get("task_id"))
    print("  task_state=%s" % progress.get("task_state"))
    print("  scope_version=%s" % queue.get("scope_version"))
    print("  standards_version=%s" % queue.get("standards_version"))
    adoptions = progress.get("standards_adoptions")
    latest = adoptions[-1] if isinstance(adoptions, list) and adoptions and \
        isinstance(adoptions[-1], dict) else None
    if latest is not None and "upstream_revision_id" in latest:
        if latest.get("upstream_revision_id") is None:
            print("  standards_upstream=none-declared")
        else:
            print("  standards_upstream=%s@%s" %
                  (latest.get("upstream_source_ref"),
                   latest.get("upstream_revision_id")))
    print("  selected_profile_manifest=%s" %
          queue.get("selected_profile_manifest"))
    print("  contract_version=%s" % contract.get("contract_version"))
    exceptions = contract.get("policy_exceptions")
    if isinstance(exceptions, list) and exceptions:
        for entry in exceptions:
            if isinstance(entry, dict):
                print("  policy_exception=%s policy=%s limit=%s scope=%s:%s"
                      % (entry.get("decision_id"), entry.get("policy_id"),
                         entry.get("limit"), entry.get("scope_kind"),
                         entry.get("scope_ref")))
    else:
        print("  policy_exceptions=none")
    print("  completion_semantics=%s" %
          contract.get("completion_semantics"))
    print("  objective=%s" % json.dumps(
        contract.get("objective"), ensure_ascii=False))
    print("  exclusions=%s" % json.dumps(
        contract.get("exclusions"), ensure_ascii=False))
    print("  queue_revision=%s" % queue.get("queue_revision"))
    print("  state_revision=%s" % queue.get("state_revision"))
    print("  live.coverage_sha256=%s" % result.get("coverage_sha256"))
    print("  live.progress_sha256=%s" % result.get("progress_sha256"))
    print("  live.required_queue_sha256=%s" % result.get("queue_sha256"))
    print("  checkpoint.recorded_at=%s" % checkpoint.get("recorded_at"))
    print("  checkpoint.summary=%s" % json.dumps(
        checkpoint.get("summary"), ensure_ascii=False))
    print("  checkpoint.binding=%s" %
          task_runtime.get("checkpoint_binding", "unavailable"))
    latest_task_receipt = task_runtime.get("latest_receipt") or {}
    print("  task_transition.latest=%s" %
          (latest_task_receipt.get("receipt_id") or "none"))
    print("  task_transition.count=%d" %
          len(task_runtime.get("history") or []))
    print("  last_reconciled_guidance_id=%s" %
          (task_runtime.get("last_reconciled_guidance_id") or "none"))
    print("  pending_guidance=%s" %
          (",".join(task_runtime.get("pending_guidance") or []) or "none"))
    print("  pending_amendments=%s" %
          (",".join(task_runtime.get("pending_amendments") or []) or "none"))
    # Reported, never blocking: the next admitted adoption plan is where the
    # live contract's load-set declaration is re-judged, so a gap here is work
    # to schedule rather than a reason to refuse the runtime.
    for gap in task_runtime.get("contract_load_set_gaps") or []:
        print("  contract_load_set_gap=%s" % gap)
    print("  terminal_audit.state=%s" % terminal_audit.get("state"))
    print("  terminal_audit.proof_path=%s" %
          terminal_audit.get("terminal_proof_path"))
    print("  terminal_audit.proof_receipt=%s" %
          terminal_audit.get("terminal_proof_receipt"))
    print("  terminal_audit.queue_check_receipt=%s" %
          terminal_audit.get("queue_check_receipt"))
    print("  maintenance_completion.state=%s" %
          maintenance_completion.get("state"))
    print("  maintenance_completion.gate_receipt=%s" %
          maintenance_completion.get("completion_gate_receipt"))
    maintenance_inventory = _maintenance_gate_inventory(result)
    print("  maintenance_gate.selected=%s" %
          (maintenance_inventory.get("selected") or "none"))
    print("  maintenance_gate.current_compatible=%s" %
          (",".join(entry["receipt_id"] for entry in
                    maintenance_inventory.get("compatible", [])) or "none"))
    print("  maintenance_gate.stale=%s" %
          (",".join(entry["receipt_id"] for entry in
                    maintenance_inventory.get("stale", [])) or "none"))
    candidate_context = result.get("maintenance_candidate_context") or {}
    print("  maintenance_candidates.sha256=%s" %
          (candidate_context.get("candidate_state_sha256") or "none"))
    print("  maintenance_candidates.total=%d" %
          len(candidate_context.get("records") or []))
    print("  maintenance_candidates.selected=%s" %
          (",".join(candidate_context.get("selected_ids") or []) or "none"))
    print("  maintenance_candidates.deferred=%s" %
          (",".join(candidate_context.get("deferred_ids") or []) or "none"))
    outstanding = result.get("standards_revalidation_outstanding") or {}
    print("  standards_revalidation.outstanding_batches=%s" %
          (",".join(sorted(outstanding)) or "none"))
    for batch_id in sorted(outstanding):
        print("  standards_revalidation.%s.bindings=%s" % (
            batch_id,
            json.dumps(outstanding[batch_id], ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")),
        ))
    barriers = result.get("standards_revalidation_barriers") or {}
    for batch_id in sorted(barriers):
        print("  standards_revalidation.%s.barrier=%s" % (
            batch_id, json.dumps(barriers[batch_id], ensure_ascii=False),
        ))
    selected_gate_id = maintenance_inventory.get("selected")
    selected_gate_entry = (result.get("receipt_catalog") or {}).get(
        selected_gate_id) if selected_gate_id else None
    selected_gate = selected_gate_entry[1] if selected_gate_entry else {}
    print("  maintenance_candidates.run_id=%s" %
          (selected_gate.get("maintenance_run_id") or "none"))
    print("  maintenance_candidates.previous_receipt=%s" %
          (selected_gate.get("previous_maintenance_completion_receipt") or
           "none"))
    for state in ("queued", "open", "merge-ready", "closed", "cancelled"):
        batch_ids = sorted(
            (item_id for item_id, item in items.items()
             if item.get("state") == state),
            key=lambda item_id: (
                items[item_id].get("order", sys.maxsize), item_id),
        )
        print("  batches.%s=%s" % (state, ",".join(batch_ids) or "none"))
    for item_id, item in sorted(
            items.items(), key=lambda pair: (pair[1].get("order", sys.maxsize),
                                             pair[0])):
        print("  work_spec.%s.path=%s sha256=%s" % (
            item_id,
            item.get("work_spec_path") or "none",
            item.get("work_spec_sha256") or "none",
        ))
    holds = []
    for item_id, item in sorted(
            items.items(), key=lambda pair: (pair[1].get("order", sys.maxsize),
                                             pair[0])):
        if item.get("hold_state") != "none":
            holds.append("%s:%s:%s" % (
                item_id, item.get("hold_state"),
                json.dumps(item.get("hold_reason"), ensure_ascii=False),
            ))
    print("  holds=%s" % (" | ".join(holds) or "none"))
    deltas = result.get("managed_deltas") or []
    if deltas:
        for delta in deltas:
            print("  delta=%s batch=%s state=%s sha256=%s "
                  "handoff_status=%s handoff_errors=%s" % (
                      delta.get("path"), delta.get("batch"),
                      delta.get("state"), delta.get("sha256"),
                      delta.get("handoff_status"),
                      json.dumps(delta.get("handoff_errors") or [],
                                 ensure_ascii=False, sort_keys=True),
                  ))
    else:
        print("  deltas=none")
    applied = result.get("applied_delta_receipts") or []
    if applied:
        for entry in applied:
            print("  applied_delta batch=%s selected_receipt=%s "
                  "compatible_receipts=%s stale_receipts=%s selection_rule=%s" % (
                      entry.get("batch"), entry.get("selected_receipt"),
                      ",".join(entry.get("compatible_receipts") or []) or
                      "none",
                      ",".join(entry.get("stale_receipts") or []) or "none",
                      entry.get("selection_rule"),
                  ))
    else:
        print("  applied_deltas=none")
    pending_applies = result.get("pending_delta_applies") or {}
    print("  pending_delta_applies.status=%s current_batches=%s "
          "stale_receipts=%s" % (
              pending_applies.get("status"),
              ",".join(entry.get("batch") for entry in
                       pending_applies.get("current", [])) or "none",
              ",".join(entry.get("receipt") for entry in
                       pending_applies.get("stale", [])) or "none",
          ))
    close_recovery = result.get("batch_close_recovery") or {}
    close_selected = close_recovery.get("selected") or {}
    print("  batch_close_recovery.status=%s batch=%s selection_rule=%s" % (
        close_recovery.get("status"),
        close_recovery.get("batch") or "none",
        close_recovery.get("selection_rule") or "none",
    ))
    print("  batch_close_recovery.queue_consistency_receipt=%s" %
          (close_selected.get("queue_consistency_receipt") or "none"))
    print("  batch_close_recovery.close_gate_receipt=%s" %
          (close_selected.get("close_gate_receipt") or "none"))
    print("  batch_close_recovery.delta_apply_receipt=%s" %
          (close_selected.get("delta_apply_receipt") or "none"))
    print("  batch_close_recovery.repository_snapshot_sha256=%s" %
          (close_selected.get("repository_snapshot_sha256") or
           close_recovery.get("repository_snapshot_sha256") or "none"))
    print("  batch_close_recovery.compatible=%s stale=%s errors=%s" % (
        ",".join(entry.get("close_gate_receipt") for entry in
                 close_recovery.get("compatible", [])) or "none",
        ",".join(entry.get("close_gate_receipt") for entry in
                 close_recovery.get("stale", [])) or "none",
        json.dumps(close_recovery.get("errors") or [],
                   ensure_ascii=False, sort_keys=True),
    ))
    print("  batch_close_recovery.update_queue_command=%s" %
          (close_recovery.get("update_queue_command") or "none"))
    locks = result.get("writer_locks") or []
    if locks:
        for lock in locks:
            print("  lock=%s transaction_phase=%s prepare_receipt_matches_owner=%s "
                  "transaction_receipts=%s "
                  "owner=%s owner_error=%s" % (
                lock.get("path"),
                lock.get("transaction_phase"),
                lock.get("prepare_receipt_matches_owner"),
                json.dumps(lock.get("transaction_receipts"),
                           ensure_ascii=False, sort_keys=True),
                json.dumps(lock.get("owner"), ensure_ascii=False,
                           sort_keys=True),
                json.dumps(lock.get("owner_error"), ensure_ascii=False),
            ))
            for state_name in ("coverage", "progress", "queue"):
                phase = (lock.get("state_phases") or {}).get(state_name) or {}
                print("    state.%s phase=%s live=%s before=%s "
                      "planned_after=%s metadata_error=%s" % (
                          state_name, phase.get("phase"),
                          phase.get("live_sha256"),
                          phase.get("before_sha256"),
                          phase.get("planned_after_sha256"),
                          json.dumps(phase.get("metadata_error"),
                                     ensure_ascii=False),
                      ))
            archive = lock.get("delta_archive_recovery")
            if archive:
                print("    delta_archive status=%s source=%s archive=%s "
                      "expected_sha256=%s source_sha256=%s archive_sha256=%s "
                      "recovery_fact=%s" % (
                          archive.get("status"),
                          archive.get("delta_archive_source"),
                          archive.get("delta_archive_path"),
                          archive.get("delta_sha256"),
                          archive.get("source_sha256"),
                          archive.get("archive_sha256"),
                          archive.get("recovery_fact"),
                      ))
                print("    delta_archive_hint=%s" % archive.get("hint"))
            if "operation_receipt" in lock:
                print("    operation_receipt=%s" % json.dumps(
                    lock["operation_receipt"], ensure_ascii=False,
                    sort_keys=True))
            print("    reconciliation_hint=%s" %
                  lock.get("reconciliation_hint"))
    else:
        print("  locks=none")
    print("next_action=%s" % _resume_next_action(result, errors))
    print("recommended_action=%s" % _resume_recommendation(result, errors))


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


def main(argv=None):
    parser = kblib.ArgumentParser(description="Validate canonical Required Queue state")
    parser.add_argument("root", help="adopting repository root")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--require-ready", metavar="BATCH_ID",
                       help="prove BATCH_ID is queued and ready to activate")
    group.add_argument("--require-revalidation", metavar="BATCH_ID",
                       help="prove BATCH_ID may produce its Standards "
                            "revalidation aggregate")
    group.add_argument("--require-complete", action="store_true",
                       help="build completion gate: prove no Required work "
                            "remains")
    group.add_argument("--require-maintenance-complete", action="store_true",
                       help="maintenance completion gate: prove one bounded "
                            "maintenance run is complete")
    group.add_argument("--resume-status", action="store_true",
                       help="show interruption-safe task and batch resume state")
    group.add_argument(
        "--deliver-readback", metavar="BATCH_ID",
        help="deliver one registered conditional Card read-back source for an "
             "already-open batch")
    group.add_argument(
        "--deliver-activation-piece", metavar="BATCH_ID",
        help="deliver one frozen activation piece of BATCH_ID inside the "
             "protocol delivery budget")
    group.add_argument(
        "--ack-activation-piece", metavar="BATCH_ID",
        help="return one delivered piece nonce as same-context delivery "
             "evidence")
    group.add_argument(
        "--deliver-phase", metavar="BATCH_ID",
        help="deliver one frozen activation phase part of BATCH_ID inside "
             "the protocol delivery budget")
    group.add_argument(
        "--ack-activation-phase", metavar="BATCH_ID",
        help="return one delivered phase part nonce as same-context delivery "
             "evidence")
    parser.add_argument(
        "--readback-rule", metavar="RULE_ID",
        help="registered rule selected with --deliver-readback")
    parser.add_argument(
        "--phase", metavar="PHASE_ID",
        help="frozen activation phase selected with --deliver-phase or "
             "--ack-activation-phase")
    parser.add_argument(
        "--phase-part", metavar="INDEX", type=int, default=0,
        help="part index inside the selected phase (default 0)")
    parser.add_argument(
        "--phase-nonce", metavar="NONCE",
        help="nonce returned from the delivered phase part, supplied to "
             "--ack-activation-phase")
    parser.add_argument(
        "--phase-delivery-receipt", metavar="RECEIPT_ID",
        help="delivery receipt the acknowledged phase nonce came from, "
             "supplied to --ack-activation-phase")
    parser.add_argument(
        "--piece", metavar="PIECE_ID",
        help="frozen activation piece selected with "
             "--deliver-activation-piece or --ack-activation-piece")
    parser.add_argument(
        "--piece-nonce", metavar="NONCE",
        help="nonce returned from the delivered piece, supplied to "
             "--ack-activation-piece")
    parser.add_argument(
        "--piece-delivery-receipt", metavar="RECEIPT_ID",
        help="delivery receipt the acknowledged nonce came from, supplied to "
             "--ack-activation-piece")
    parser.add_argument("--confirmation-receipt",
                        help="confirmation evidence supplied to --require-ready")
    parser.add_argument(
        "--boundary-gate-receipt", action="append", default=[],
        metavar="GATE_ID=RECEIPT_ID",
        help="current gate evidence supplied to --require-revalidation")
    parser.add_argument("--budget-manifest-receipt",
                        help="closed budget-manifest receipt ID supplied to "
                             "--require-maintenance-complete")
    parser.add_argument("--ledger-advance-receipt",
                        help="Coverage Ledger advance receipt ID supplied to "
                             "--require-maintenance-complete")
    parser.add_argument("--watermark-advance-receipt",
                        help="watermark advance receipt ID supplied to "
                             "--require-maintenance-complete")
    parser.add_argument("--receipts", help="repository-relative JSONL receipt path")
    parser.add_argument(
        "--json", action="store_true",
        help="write this run's receipt object to stdout as one canonical "
             "JSON array and move the human report to stderr; receipt "
             "writing and exit codes are unchanged")
    args = parser.parse_args(argv)

    if not args.json:
        return _run(args, None)
    produced = []
    with contextlib.redirect_stdout(sys.stderr):
        code = _run(args, produced)
    _emit_json_receipts(produced)
    return code


def _run(args, produced):
    """Evaluate one already-parsed invocation; ``produced`` collects receipts."""
    result = validate_runtime(args.root)
    errors = list(result["errors"])
    candidates = []
    # Notes are neither errors nor candidates: a fact the operator must keep
    # seeing, whose disposition is already recorded.  They never change the
    # exit code, because a decision already made is not an open judgment.
    notes = []
    hub_page_candidates = []
    writer_locks = result.get("writer_locks") or []
    maintenance_context = None
    revalidation_context = None
    activation_context = None
    readback_context = None
    piece_context = None
    piece_ack_context = None
    phase_context = None
    phase_ack_context = None
    resume_activation_contexts = []

    if args.confirmation_receipt and not args.require_ready:
        errors.append("--confirmation-receipt is only valid with --require-ready")
    if args.boundary_gate_receipt and not args.require_revalidation:
        errors.append("--boundary-gate-receipt is only valid with "
                      "--require-revalidation")
    if args.readback_rule and not args.deliver_readback:
        errors.append("--readback-rule is only valid with --deliver-readback")
    if args.deliver_readback and not args.readback_rule:
        errors.append("--deliver-readback requires --readback-rule")
    if args.piece and not (args.deliver_activation_piece or
                           args.ack_activation_piece):
        errors.append("--piece is only valid with --deliver-activation-piece "
                      "or --ack-activation-piece")
    if args.deliver_activation_piece and not args.piece:
        errors.append("--deliver-activation-piece requires --piece")
    if args.ack_activation_piece and not (
            args.piece and args.piece_nonce and args.piece_delivery_receipt):
        errors.append(
            "--ack-activation-piece requires --piece, --piece-nonce and "
            "--piece-delivery-receipt")
    for flag, value in (("--piece-nonce", args.piece_nonce),
                        ("--piece-delivery-receipt",
                         args.piece_delivery_receipt)):
        if value and not args.ack_activation_piece:
            errors.append("%s is only valid with --ack-activation-piece" %
                          flag)
    if args.phase and not (args.deliver_phase or args.ack_activation_phase):
        errors.append("--phase is only valid with --deliver-phase or "
                      "--ack-activation-phase")
    if args.deliver_phase and not args.phase:
        errors.append("--deliver-phase requires --phase")
    if args.ack_activation_phase and not (
            args.phase and args.phase_nonce and args.phase_delivery_receipt):
        errors.append(
            "--ack-activation-phase requires --phase, --phase-nonce and "
            "--phase-delivery-receipt")
    for flag, value in (("--phase-nonce", args.phase_nonce),
                        ("--phase-delivery-receipt",
                         args.phase_delivery_receipt)):
        if value and not args.ack_activation_phase:
            errors.append("%s is only valid with --ack-activation-phase" %
                          flag)
    if args.phase_part and not (args.deliver_phase or
                                args.ack_activation_phase):
        errors.append("--phase-part is only valid with --deliver-phase or "
                      "--ack-activation-phase")
    if args.phase_part < 0:
        errors.append("--phase-part must not be negative")
    maintenance_evidence = (
        args.budget_manifest_receipt, args.ledger_advance_receipt,
        args.watermark_advance_receipt,
    )
    if any(maintenance_evidence) and not args.require_maintenance_complete:
        errors.append(
            "maintenance evidence receipts are only valid with "
            "--require-maintenance-complete"
        )
    if args.require_maintenance_complete and not all(maintenance_evidence):
        errors.append(
            "--require-maintenance-complete requires "
            "--budget-manifest-receipt, --ledger-advance-receipt, and "
            "--watermark-advance-receipt"
        )

    if writer_locks:
        lock_paths = ", ".join(lock.get("path", "<unknown>")
                               for lock in writer_locks)
        message = ("runtime state has active or interrupted writer lock(s): %s" %
                   lock_paths)
        if args.require_complete:
            # The shared build-completion predicate below owns this error so
            # in-process consumers and the CLI make the same decision.
            pass
        elif args.require_maintenance_complete:
            errors.append(message)
        else:
            candidates.append(message)

    if args.require_complete:
        for completion_error in required_queue_completion_errors(result):
            if completion_error not in errors:
                errors.append(completion_error)

    if args.resume_status:
        close_recovery = _batch_close_recovery_inventory(result)
        result["batch_close_recovery"] = close_recovery
        if close_recovery.get("status") == "snapshot-unavailable":
            errors.extend(
                "batch-close recovery snapshot unavailable: %s" % error
                for error in close_recovery.get("errors", []))

    if not errors and args.require_revalidation:
        ineligible = standards_revalidation_producer_eligibility(
            result, args.require_revalidation)
        if ineligible:
            errors.append(ineligible)
        else:
            supplied, supplied_errors = _parse_boundary_gate_arguments(
                args.boundary_gate_receipt)
            errors.extend(supplied_errors)
            if not errors:
                revalidation_context, context_errors = \
                    standards_revalidation_context(
                        result, args.require_revalidation, supplied)
                errors.extend(context_errors)
    elif not errors and args.require_ready:
        item = result.get("items_by_id", {}).get(args.require_ready)
        # K13/10: a hub page this batch creates does not block activation; it
        # is handed to the integrator's post-merge hub synchronization step.
        hub_page_candidates = list((result.get("hub_page_admission") or {}).get(
            args.require_ready, {}).get("candidates") or [])
        if item is None:
            errors.append("requested batch %s does not exist" % args.require_ready)
        elif item.get("state") != "queued":
            errors.append("requested batch %s is %s, not queued" %
                          (args.require_ready, item.get("state")))
        elif result.get("progress", {}).get("task_state") in (
                "complete", "cancelled"):
            errors.append("task_state=%s is terminal and cannot activate batch %s" %
                          (result["progress"].get("task_state"),
                           args.require_ready))
        elif args.require_ready not in result["ready"]:
            reasons = list(dict(result["blocked"]).get(
                args.require_ready, ["not ready"]))
            if ("confirmation receipt absent" in reasons and
                    args.confirmation_receipt):
                confirmation_errors = []
                _require_receipt(
                    result.get("current_receipt_catalog",
                               result.get("receipt_catalog", {})),
                    args.confirmation_receipt,
                    "%s confirmation" % args.require_ready,
                    confirmation_errors,
                    expected={"check": "confirmation",
                              "target": args.require_ready},
                )
                if confirmation_errors:
                    errors.extend(confirmation_errors)
                else:
                    reasons.remove("confirmation receipt absent")
                    if "hold=confirmation-required" in reasons:
                        reasons.remove("hold=confirmation-required")
                    if not reasons and args.require_ready not in result["ready"]:
                        result["ready"].append(args.require_ready)
            if reasons and not errors:
                candidates.append("%s is not executable: %s" %
                                  (args.require_ready, "; ".join(reasons)))
    elif not errors and args.deliver_readback:
        item = result.get("items_by_id", {}).get(args.deliver_readback)
        if item is None:
            errors.append("requested batch %s does not exist" %
                          args.deliver_readback)
        elif item.get("state") not in ("open", "merge-ready"):
            errors.append(
                "read-back delivery requires an open or merge-ready batch; "
                "%s is %s" % (args.deliver_readback, item.get("state")))
        else:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            activation_id = item.get("activation_receipt")
            entry = catalog.get(activation_id)
            activation_receipt = entry[1] if entry is not None else None
            if (not isinstance(activation_receipt, dict) or
                    activation_receipt.get("tool") != TOOL or
                    activation_receipt.get("tool_version") != TOOL_VERSION):
                errors.append(
                    "batch %s has no current Card-first activation receipt; "
                    "reopen or migrate it before read-back delivery" %
                    args.deliver_readback)
            else:
                try:
                    readback_context = card_activation.build_readback_addendum(
                        result["root"],
                        card_activation.context_from_receipt(
                            activation_receipt),
                        args.readback_rule,
                    )
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("cannot deliver Card read-back: %s" % exc)
    elif not errors and (args.deliver_activation_piece or
                         args.ack_activation_piece):
        batch_id = args.deliver_activation_piece or args.ack_activation_piece
        item = result.get("items_by_id", {}).get(batch_id)
        activation_receipt = None
        if item is None:
            errors.append("requested batch %s does not exist" % batch_id)
        elif item.get("state") not in ("open", "merge-ready"):
            errors.append(
                "activation piece delivery requires an open or merge-ready "
                "batch; %s is %s" % (batch_id, item.get("state")))
        else:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            entry = catalog.get(item.get("activation_receipt"))
            activation_receipt = entry[1] if entry is not None else None
            if (not isinstance(activation_receipt, dict) or
                    activation_receipt.get("tool") != TOOL or
                    activation_receipt.get("tool_version") != TOOL_VERSION):
                errors.append(
                    "batch %s has no current Card-first activation receipt; "
                    "reopen it before piece delivery" % batch_id)
                activation_receipt = None
        if activation_receipt is not None and args.deliver_activation_piece:
            try:
                piece_context = card_activation.build_activation_piece(
                    result["root"],
                    card_activation.context_from_receipt(activation_receipt),
                    args.piece)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append("cannot deliver activation piece: %s" % exc)
        elif activation_receipt is not None:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            delivery_entry = catalog.get(args.piece_delivery_receipt)
            delivery = delivery_entry[1] if delivery_entry is not None else None
            if not isinstance(delivery, dict):
                errors.append(
                    "piece delivery receipt %s is absent from the current "
                    "catalog" % args.piece_delivery_receipt)
            elif delivery.get("piece_id") != args.piece:
                errors.append(
                    "piece delivery receipt %s does not deliver %s" %
                    (args.piece_delivery_receipt, args.piece))
            elif delivery.get("card_bundle_sha256") != activation_receipt.get(
                    "card_bundle_sha256"):
                errors.append(
                    "piece delivery receipt %s belongs to another activation "
                    "bundle" % args.piece_delivery_receipt)
            else:
                try:
                    piece_ack_context = card_activation.build_piece_ack(
                        dict(delivery, receipt_id=args.piece_delivery_receipt),
                        args.piece_nonce)
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("cannot acknowledge activation piece: %s" %
                                  exc)
    elif not errors and (args.deliver_phase or args.ack_activation_phase):
        batch_id = args.deliver_phase or args.ack_activation_phase
        item = result.get("items_by_id", {}).get(batch_id)
        activation_receipt = None
        if item is None:
            errors.append("requested batch %s does not exist" % batch_id)
        elif item.get("state") not in ("open", "merge-ready"):
            errors.append(
                "activation phase delivery requires an open or merge-ready "
                "batch; %s is %s" % (batch_id, item.get("state")))
        else:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            entry = catalog.get(item.get("activation_receipt"))
            activation_receipt = entry[1] if entry is not None else None
            if (not isinstance(activation_receipt, dict) or
                    activation_receipt.get("tool") != TOOL or
                    activation_receipt.get("tool_version") != TOOL_VERSION):
                errors.append(
                    "batch %s has no current Card-first activation receipt; "
                    "reopen it before phase delivery" % batch_id)
                activation_receipt = None
        if activation_receipt is not None and args.deliver_phase:
            try:
                phase_context = card_activation.build_phase_delivery(
                    result["root"],
                    card_activation.context_from_receipt(activation_receipt),
                    args.phase, args.phase_part)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append("cannot deliver activation phase: %s" % exc)
        elif activation_receipt is not None:
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            delivery_entry = catalog.get(args.phase_delivery_receipt)
            delivery = delivery_entry[1] if delivery_entry is not None else None
            if not isinstance(delivery, dict):
                errors.append(
                    "phase delivery receipt %s is absent from the current "
                    "catalog" % args.phase_delivery_receipt)
            elif delivery.get("phase_id") != args.phase:
                errors.append(
                    "phase delivery receipt %s does not deliver %s" %
                    (args.phase_delivery_receipt, args.phase))
            elif delivery.get("part_index") != args.phase_part:
                errors.append(
                    "phase delivery receipt %s delivers part %s, not %s" %
                    (args.phase_delivery_receipt, delivery.get("part_index"),
                     args.phase_part))
            elif delivery.get("card_bundle_sha256") != activation_receipt.get(
                    "card_bundle_sha256"):
                errors.append(
                    "phase delivery receipt %s belongs to another activation "
                    "bundle" % args.phase_delivery_receipt)
            else:
                try:
                    phase_ack_context = card_activation.build_phase_ack(
                        dict(delivery, receipt_id=args.phase_delivery_receipt),
                        args.phase_nonce)
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append("cannot acknowledge activation phase: %s" %
                                  exc)
    elif not errors and args.require_maintenance_complete:
        maintenance_errors, maintenance_context = \
            _maintenance_completion_gate_errors(
                os.path.realpath(os.path.abspath(args.root)),
                dict(result, receipt_catalog=result.get(
                    "current_receipt_catalog",
                    result.get("receipt_catalog", {}))),
                args.budget_manifest_receipt,
                args.ledger_advance_receipt,
                args.watermark_advance_receipt,
            )
        errors.extend(maintenance_errors)
    elif not errors and args.resume_status:
        progress = result.get("progress") or {}
        task_state = progress.get("task_state")
        active_ids = [item_id for item_id, item in
                      (result.get("items_by_id") or {}).items()
                      if item.get("state") in ACTIVE_STATES]
        held_ids = [item_id for item_id, item in
                    (result.get("items_by_id") or {}).items()
                    if item.get("hold_state") != "none"]
        if task_state in (
                "planned", "active", "paused", "blocked",
                "completion-candidate"):
            candidates.append(
                "existing task_state=%s is non-terminal and must be resumed or "
                "resolved before a new task" % task_state
            )
        if active_ids and task_state not in ("complete", "cancelled"):
            candidates.append("in-flight batch(es) require resume: %s" %
                              ", ".join(sorted(active_ids)))
        if (held_ids and task_state not in
                ("paused", "blocked", "complete", "cancelled")):
            candidates.append("batch hold(s) require resolution: %s" %
                              ", ".join(sorted(held_ids)))
        for item_id in sorted(active_ids):
            item = result["items_by_id"][item_id]
            try:
                delivery = card_activation.build_activation_context(
                    result["root"], result["progress"], item,
                    runtime_state=result)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(
                    "cannot compile resume Card delivery for %s: %s" %
                    (item_id, exc))
                continue
            catalog = result.get(
                "current_receipt_catalog", result.get("receipt_catalog", {}))
            recorded_entry = catalog.get(item.get("activation_receipt"))
            recorded = recorded_entry[1] if recorded_entry else None
            bundle_errors = card_activation.exact_bundle_errors(
                delivery, card_activation.context_from_receipt(recorded))
            if bundle_errors:
                errors.extend(
                    "cannot resume %s Card delivery: %s" % (item_id, error)
                    for error in bundle_errors)
                continue
            resume_activation_contexts.append({
                "batch_id": item_id,
                "parent_activation_receipt": item.get(
                    "activation_receipt"),
                **delivery,
            })
    for defect in result.get("structural_admission_defects") or []:
        candidates.append(defect)
    unsupported_reviewed = unsupported_reviewed_records(result.get("coverage"))
    if unsupported_reviewed:
        covering, near_miss = coverage_reviewed_era_exception(
            result.get("progress"), result.get("queue"),
            len(unsupported_reviewed))
        if covering is not None:
            # Covered by a bounded contract exception: the disposition
            # K02/01 offers, now readable.  Reported, never suppressed --
            # the operator sees the count falling toward the stated end.
            notes.append(
                "%d Coverage record(s) still claim authoring_status=reviewed "
                "with no gate_receipts, within the %d bounded by contract "
                "policy exception %s (%s:%s, K02/01)" %
                (len(unsupported_reviewed), covering.get("limit"),
                 covering.get("decision_id"), covering.get("scope_kind"),
                 covering.get("scope_ref")))
        else:
            candidates.append(
                "%d Coverage record(s) claim authoring_status=reviewed with "
                "no gate_receipts, so the era of the review that earned the "
                "status cannot be produced (K02/01); a declared migration "
                "must re-review, retire, or explicitly except them%s: %s" %
                (len(unsupported_reviewed),
                 "" if near_miss is None else " -- %s" % near_miss,
                 ", ".join(unsupported_reviewed[:5]) +
                 ("..." if len(unsupported_reviewed) > 5 else ""))
            )
    if not errors:
        queue_items = result.get("queue", {}).get("required_queue") or []
        if not queue_items:
            candidates.append("Queue is valid but empty; Required work has not been materialized")
        elif (result["remaining"] and not result["ready"] and
              not any(item.get("state") in ACTIVE_STATES
                      for item in queue_items if isinstance(item, dict))):
            candidates.append("no executable batch; remaining work is held or dependency-blocked")

    if (not errors and not candidates and args.require_ready and
            activation_context is None):
        try:
            activation_context = card_activation.build_activation_context(
                result["root"], result["progress"],
                result["items_by_id"][args.require_ready],
                runtime_state=result,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append("cannot compile Card activation bundle: %s" % exc)

    for error in errors:
        print("[FAIL] %s" % error)
    for candidate in candidates:
        print("[HOLD] %s" % candidate)
    for note in notes:
        print("[NOTE] %s" % note)
    if not errors and not candidates:
        print("[PASS] Required Queue is consistent")
    if args.resume_status:
        _print_resume_status(result, errors)
    elif result.get("queue"):
        print("queue_revision=%s state_revision=%s remaining=%s ready=%s" % (
            result["queue"].get("queue_revision"),
            result["queue"].get("state_revision"), result["remaining"],
            ",".join(result["ready"]) or "none",
        ))
        print("required_queue_sha256=%s" % result.get("queue_sha256"))
        if args.require_ready:
            print("hub_page_candidates=%s" %
                  ("; ".join(hub_page_candidates) or "none"))
            if activation_context:
                print("card_bundle_sha256=%s delivery_assurance=%s" % (
                    activation_context.get("card_bundle_sha256"),
                    activation_context.get("delivery_assurance")))
        if args.deliver_readback and readback_context:
            print("readback_addendum_sha256=%s delivery_assurance=%s" % (
                readback_context.get("readback_addendum_sha256"),
                readback_context.get("delivery_assurance")))

    code = 1 if errors else (2 if candidates else 0)
    outcome = "fail" if errors else ("candidate" if candidates else "pass")
    details = "errors=%d candidates=%d remaining=%s ready=%s" % (
        len(errors), len(candidates), result.get("remaining"),
        ",".join(result.get("ready", [])) or "none",
    )
    mode = ("require-revalidation:%s" % args.require_revalidation
            if args.require_revalidation else
            ("require-ready:%s" % args.require_ready if args.require_ready else
            ("deliver-readback:%s:%s" % (
                args.deliver_readback, args.readback_rule)
             if args.deliver_readback else
            ("deliver-activation-piece:%s:%s" % (
                args.deliver_activation_piece, args.piece)
             if args.deliver_activation_piece else
            ("ack-activation-piece:%s:%s" % (
                args.ack_activation_piece, args.piece)
             if args.ack_activation_piece else
            ("deliver-phase:%s:%s:%d" % (
                args.deliver_phase, args.phase, args.phase_part)
             if args.deliver_phase else
            ("ack-activation-phase:%s:%s:%d" % (
                args.ack_activation_phase, args.phase, args.phase_part)
             if args.ack_activation_phase else
            ("require-complete" if args.require_complete else
             ("require-maintenance-complete"
              if args.require_maintenance_complete else
              ("resume-status" if args.resume_status else
               "consistency"))))))))))
    try:
        receipt = _write_receipt(
            args.root, args.receipts, result, outcome, details, mode,
            hub_page_candidates=hub_page_candidates,
            confirmation_receipt=args.confirmation_receipt,
            runtime_errors=errors,
            maintenance_context=maintenance_context,
            standards_revalidation_context=revalidation_context,
            activation_context=activation_context,
            readback_context=readback_context,
            piece_context=piece_context,
            piece_ack_context=piece_ack_context,
            phase_context=phase_context,
            phase_ack_context=phase_ack_context,
            resume_activation_contexts=resume_activation_contexts,
            build_unwritten=produced is not None,
        )
    except (OSError, ValueError) as exc:
        print("[FAIL] cannot write receipts: %s" % exc)
        return 1
    if produced is not None and receipt is not None:
        produced.append(receipt)
    return code


if __name__ == "__main__":
    sys.exit(main())
