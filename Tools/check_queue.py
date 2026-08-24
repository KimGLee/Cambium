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
    APPLY_AMENDMENT_TOOL_VERSION,
    APPLY_DELTA_TOOL_VERSION,
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_ID_RE,
    BATCH_REVIEW_GATE_ID,
    CONTRACT_AMENDMENT_TOOL_VERSION,
    CORPUS_PLAN_TOOL,
    CORPUS_PLAN_TOOL_VERSION,
    COVERAGE_PATH,
    EVIDENCE_IDENTITY_USES,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_TERMINAL_HISTORY,
    EXECUTION_MODES,
    GATE_CHECK,
    HOLDS,
    LEGACY_PROPERTY_ADOPTION_OPERATION,
    MANUAL_ATTESTATION_TOOL,
    MANUAL_ATTESTATION_TOOL_VERSION,
    PROGRESS_PATH,
    QUEUE_PATH,
    REGISTER_AMENDMENT_TOOL,
    REGISTER_AMENDMENT_TOOL_VERSION,
    SEAL_TOOL,
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
    _acyclic,
    _closed_mapping_errors,
    _current_property_receipt,
    _explicit_string_list_errors,
    _identity,
    _load_state,
    _nonempty_string,
    _normalized_repository_path,
    _path_error,
    _repository_evidence_file,
    _timestamp_value,
    _valid_timestamp,
    evidence_identity_errors,
    property_receipt_utc_date,
)

# The historical spelling of one promoted name.  `evidence_identity`
# offers `evidence_identity_errors` because `metadata_gate_runtime` needs
# the identical identity policy and may not read a private name; the
# underscored spelling is kept here, where every other historical
# spelling is kept, for the test that has always read it.
_evidence_identity_errors = evidence_identity_errors

# These exact legacy protocols remain replayable.  1.0.0 is the first
# registration shape; 1.1.0 adds withdrawal.  Neither may claim the
# delegated-authority fields introduced by 1.2.0.  The current 1.3.0 era adds
# the Coverage-only ``property-state-migration`` operation; older rows remain
# producer-era history and are never asked to satisfy that new operation.
# 1.4.0 widens the legacy observation domain for Profile Gate vocabulary
# fields from the completion enum to the field's registered vocabulary and
# admits explicit null observations of present-but-blank claims; current
# owner state and Gate transitions keep the narrower completion enum.
SUPPORTED_REGISTER_AMENDMENT_TOOL_VERSIONS = frozenset((
    "1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0",
))
# 1.3.0 produced the original registered queue-replan commit shape.  Its
# bindings are still validated field by field; unknown protocols fail closed.
SUPPORTED_COMPILE_QUEUE_TOOL_VERSIONS = frozenset((
    "1.3.0", "1.4.0", "1.5.0",
))
OPERATIONAL_AMENDMENT_OPERATIONS = frozenset((
    "queue-replan", "scope-replan", "cancel-batch",
    "gap-routing-reconciliation", "property-state-migration",
))

WORK_SPEC_PREFIX = ".cambium/work_specs"
WORK_SPEC_FIELDS = frozenset(("work_spec_path", "work_spec_sha256"))
WORK_SPEC_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "batch_id", "manifest", "outcomes", "instructions",
    "acceptance_conditions", "constraints",
))
WORK_SPEC_OUTCOME_FIELDS = frozenset(("outcome_id", "required_result"))
WORK_SPEC_INSTRUCTION_FIELDS = frozenset((
    "instruction_id", "order", "target_scope", "required_transformation",
    "depends_on",
))
WORK_SPEC_ACCEPTANCE_FIELDS = frozenset((
    "condition_id", "target_scope", "observable_predicate",
    "evidence_requirement",
))
WORK_SPEC_CONSTRAINT_FIELDS = frozenset((
    "constraint_id", "target_scope", "requirement",
))
WORK_SPEC_QUEUE_OWNED_FIELDS = frozenset((
    "id", "family", "order", "record_count", "source_route",
    "execution_mode", "depends_on", "confirmation_required", "state",
    "lifecycle", "hold", "hold_state", "work_spec_path",
    "work_spec_sha256", "opened_at", "activation_receipt",
    "confirmation_receipt", "merge_ready_at", "delta_path",
    "delta_sha256", "closed_at", "queue_consistency_receipt",
    "close_gate_receipt", "delta_apply_receipt", "cancelled_at",
    "cancellation_amendment", "hold_reason", "successor_of",
    "invalidation_history",
    "queue_revision", "state_revision", "revision", "receipts",
    "transition_receipts", "batch_receipts", "revalidation_receipts",
))
WORK_SPEC_RECORD_ID_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\Z"
)
WORK_SPEC_SENTINELS = ("TODO(batch)", "REPLACE-ME")

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
# The named fields through which a Queue item, one of its invalidation
# records, or a transition receipt references another receipt by ID.
#
# This exists because a defect was not one missing field: sealing protected
# a hand-written list of fields while consumers resolved receipt IDs from
# wherever they liked, and nothing compared the two.  A closed structural
# inventory is what makes that comparison possible -- the reachability
# assertion in the tests walks these names, so it asks the schema what a
# reference is instead of guessing from the shape of a string.  Adding a
# reference to a record without adding it here is caught: a paired test
# asserts the item and invalidation groups stay subsets of
# ``QUEUE_ITEM_FIELDS`` and ``INVALIDATION_FIELDS``.
#
# The transition group is the transition receipt's own writer contract in
# ``update_queue.py``: ``evidence_receipt`` always, the aggregate on a
# consuming transition, the close trio on a close, and a deep copy of the
# invalidation record on a rollback.
RECEIPT_REFERENCE_FIELDS = {
    "item": {
        "scalar": ("activation_receipt", "confirmation_receipt",
                   "queue_consistency_receipt", "close_gate_receipt",
                   "delta_apply_receipt"),
        "list": ("transition_receipts", "batch_receipts"),
        "nested": (("invalidation_history", "invalidation"),),
    },
    "invalidation": {
        "scalar": ("transition_receipt", "delta_apply_receipt"),
        "list": ("batch_receipts", "delta_gate_receipts",
                 "revalidation_receipts"),
        "nested": (),
    },
    "transition": {
        "scalar": ("evidence_receipt", "standards_revalidation_receipt",
                   "queue_consistency_receipt", "close_gate_receipt",
                   "delta_apply_receipt"),
        "list": (),
        "nested": (("invalidation", "invalidation"),),
    },
}
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
COVERAGE_DISPOSITIONS = frozenset((
    "required", "optional", "deferred", "excluded",
))

# K13/10 concurrency admission condition 2 ("B does not edit control or hub
# pages").  The kernel enumerates the members; these constants only spell the
# machine judgment for that enumeration.  `type` and `scope` are the K08
# closed vocabularies in `kernel/K08 Metadata and Status/vocabulary-base.yaml`;
# the profile side reuses the `Expression Layer Entry` rows the selected
# profile already registers, so no profile slot or interface is added here.
# The kernel's "other profile-registered hub roles" clause has no registration
# path today and therefore contributes no member; see K13/10.
HUB_PAGE_TYPES = frozenset(("overview", "runtime-card", "card-index"))
HUB_TERM_TYPE = "term"
HUB_TERM_SCOPE = "shared"
EXPRESSION_LAYER_SLOT = "Expression Layer Entry"
HUB_DEPENDENCY_MAP_LABEL = "existing canonical dependency-map"
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

LOCK_STATE_FINGERPRINTS = {
    "coverage": {
        "before": ("before_coverage_sha256",),
        "planned_after": ("planned_after_coverage_sha256",),
    },
    "queue": {
        # Queue writers predate the cross-Ledger transaction and use the
        # longer Required Queue spelling.  Both names identify the exact same
        # canonical file and are accepted only when they do not conflict.
        "before": ("before_queue_sha256",
                   "before_required_queue_sha256"),
        "planned_after": ("planned_after_queue_sha256",
                          "planned_after_required_queue_sha256"),
    },
    "progress": {
        "before": ("before_progress_sha256",),
        "planned_after": ("planned_after_progress_sha256",),
    },
    "standards": {
        # Ordinary writers do not change adopter Standards state, but their
        # frozen runtime-authority context already records the exact active
        # bytes.  Treat that existing field as the before-image alias so
        # interrupted-write recovery does not call a bound authority input
        # unavailable. Standards adoption supplies its explicit before/after
        # pair and therefore retains the four-state transaction distinction.
        "before": ("before_standards_state_sha256",
                   "active_standards_sha256"),
        "planned_after": ("planned_after_standards_state_sha256",),
    },
}
GENERIC_WRITER_TOOLS = frozenset((
    "apply_delta", "update_queue", "compile_queue", "update_task",
    "check_batch_close", "adopt_standards", "register_amendment",
    "apply_contract_amendment", "apply_task_plan", "seal_receipts",
))
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
# K12/07 fixes these seven base receipt dimensions and K12/08 / K12/18 file
# every judgment item and Gate under one of them.  Like the Kxx numbers this
# only projects a closed kernel set into the checker; `check_proof` carries the
# same projection for the Terminal Proof, and a test asserts the two agree.
BASE_RECEIPT_DIMENSIONS = frozenset((
    "structure_and_links", "content_and_depth", "formula_and_numeric",
    "source_and_currentness", "coverage_and_integration", "rendering",
    "guidance_and_contract",
))
# The two Dimension cells that are not a dimension: `none` says the Gate's
# receipt carries no `dimension` because its members hold the verdicts, and
# `*` says a named producer's identity already fixes what its receipt means.
UNDIMENSIONED_GATE = "none"
UNNARROWED_GATE_DIMENSION = "*"
# The two Lifecycle cells that are not a batch lifecycle state.  Both name a
# position the same way a batch state does, so the partition stays one rule:
# `not-batch-scoped` is the position every batch is always at, because the
# Gate's producer takes no batch and nothing about the Queue constrains it;
# `queue-exhausted` is the position reached only once the Queue holds no
# non-terminal batch, which is ahead of every live batch and behind none.
NOT_BATCH_SCOPED_GATE = "not-batch-scoped"
QUEUE_EXHAUSTED_GATE = "queue-exhausted"
UNSCOPED_GATE_POSITIONS = frozenset((NOT_BATCH_SCOPED_GATE,
                                     QUEUE_EXHAUSTED_GATE))
BATCH_REVIEW_CHECK = "batch_gate"
# ``check_proof`` 1.16 first bound the authorized Profile snapshot and typed
# closure. Version 1.17 additionally binds the three root-owned profile-load
# inputs and the complete repository snapshot. Historical replay applies each
# producer era's promised shape only.
PROFILE_BOUND_TERMINAL_PROOF_MIN_VERSION = (1, 16, 0)
PROFILE_INPUT_BOUND_TERMINAL_PROOF_MIN_VERSION = (1, 17, 0)
REPOSITORY_BOUND_TERMINAL_PROOF_MIN_VERSION = (1, 17, 0)
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
COVERAGE_BATCH_SPEC_FIELDS = frozenset((
    "id", "family", "order_hint", "source_route", "execution_mode",
    "depends_on", "confirmation_required", "work_spec_path",
    "work_spec_sha256",
))
LEGACY_PROPERTY_STATE_FIELD = "legacy_property_state"
LEGACY_PROPERTY_RECORD_FIELDS = frozenset(("status", "value"))
LEGACY_PROPERTY_STATUS = "legacy-unverified"
PROPERTY_STATE_MIGRATION_BINDING_FIELDS = (
    "property_state_migration_records",
    "property_state_migration_count",
    "property_state_migration_set_sha256",
    "metadata_execution_contract_fingerprint",
    "metadata_execution_rule_fingerprint",
    "operation_capability",
    "selected_profile_manifest",
    "profile_snapshot_sha256",
    "profile_contract_fingerprint",
    "profile_load_inputs_sha256",
)
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
POLICY_EXCEPTION_FIELDS = frozenset((
    "decision_id", "policy_id", "baseline_policy_fingerprint", "limit",
    "scope_kind", "scope_ref", "rationale", "approval_reference",
))
POLICY_EXCEPTION_SCOPE_KINDS = frozenset(("task", "repository-snapshot"))
# Producer eras whose batch-close protocol carries the policy-exception
# disposition.  K12/10 producer-era identity cuts both ways: an older bundle
# is never re-judged against members its era lacked, and it is never allowed
# to carry evidence its era could not have produced.  A 1.7 bundle claiming a
# policy-exception disposition is a forgery, not history.
POLICY_EXCEPTION_DISPOSITION_VERSIONS = frozenset((
    "1.8.0", "1.9.0", "1.10.0", "1.11.0", "1.12.0",
))
SUPPORTED_SEAL_TOOL_VERSIONS = frozenset(("1.2.0", "1.3.0", "1.4.0"))

COMPACT_CLOSE_EVIDENCE_VERSIONS = frozenset((
    "1.9.0", "1.10.0", "1.11.0", "1.12.0",
))
CANDIDATE_CONTINUATION_VERSIONS = frozenset((
    "1.10.0", "1.11.0", "1.12.0"))
SEALED_POLICY_EXCEPTION_FIELDS = frozenset((
    "decision_id", "policy_id", "limit", "scope_kind", "scope_ref",
    "policy_fingerprint", "pages", "total",
))
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
STANDARDS_ADOPTION_PROFILE_CONTRACT_MIN_VERSION = (1, 3, 0)
# The 1.5 producer records where the adopted revision came from: the
# distribution has no version numbers by design, so upstream/downstream
# comparability is the adoption record's job, not a prose convention's.
STANDARDS_ADOPTION_UPSTREAM_MIN_VERSION = (1, 5, 0)
STANDARDS_ADOPTION_PROFILE_INPUT_MIN_VERSION = (1, 4, 0)
STANDARDS_ADOPTION_OWNER_PROJECTION_MIN_VERSION = (1, 6, 0)
STANDARDS_GATE_REGISTRY_PATH = \
    "kernel/K00 Standards Control/12 Control Registry.md"
STANDARDS_REVALIDATION_CAPABILITY_PROTOCOL = "owner-projection-v1"
STANDARDS_REVALIDATION_CAPABILITY_HEADING = \
    "Standards Revalidation Capability Registry"
STANDARDS_REVALIDATION_CAPABILITY_ROLES = frozenset((
    "special-owner", "immediate-owner", "native-owner", "semantic-leaf",
    "mechanism-only", "unsupported", "advisory",
))
STANDARDS_REVALIDATION_CAPABILITY_EDGES = frozenset((
    "after-image-admission", "adoption-commit", "native-transition",
    "project-to-owner", "mechanism-input-only", "advisory-only", "none",
))
STANDARDS_REVALIDATION_SCOPE_PROTOCOLS = frozenset((
    "profile-after-image", "runtime-after-image", "native-owner-scope",
    "inherit-owner-scope", "diagnostic-scope", "none",
))
STANDARDS_REVALIDATION_BINDING_PROTOCOLS = frozenset((
    "profile-fingerprints", "runtime-state-fingerprints",
    "native-owner-receipt", "owner-member-chain", "not-authorizing",
))
STANDARDS_REVALIDATION_ROLE_CONTRACTS = {
    "special-owner": (
        "after-image-admission", "profile-after-image",
        "profile-fingerprints"),
    "immediate-owner": (
        "adoption-commit", "runtime-after-image",
        "runtime-state-fingerprints"),
    "native-owner": (
        "native-transition", "native-owner-scope",
        "native-owner-receipt"),
    "semantic-leaf": (
        "project-to-owner", "inherit-owner-scope", "owner-member-chain"),
    "mechanism-only": (
        "mechanism-input-only", "none", "not-authorizing"),
    "unsupported": ("none", "none", "not-authorizing"),
    "advisory": (
        "advisory-only", "diagnostic-scope", "not-authorizing"),
}
READ_SET_BOUNDARY_OWNER_PATH = \
    "kernel/K00 Standards Control/15 Read Set Loading Boundaries.md"
READ_SET_PATH_PREFIX = "kernel/Read Sets/"

# --- Registered producer identity -------------------------------------------
# K00/12 registers one producer tuple per Gate ID and K12/17 requires every
# receipt offered for that Gate to carry it exactly.  Nothing deterministic
# used to compare the registered tuple against the producer that actually
# writes it, so a `Check` or `Mode` cell could disagree with its tool and the
# only symptom would be a receipt that silently misses every boundary it was
# recorded for.  The two tables below give the comparison its second source.
#
# `Check` for a Gate whose producer module does not export the name itself.
# The value is the one this module's own consumers compare a receipt against,
# so a drift is caught exactly where it would reject the receipt.  A module
# that later exports `GATE_CHECK` wins, and the two are required to agree.
CONSUMED_GATE_CHECKS = {
    "profile-load": "profile-check-summary",
    "terminal-proof": "proof-check-summary",
    "registered-residual-content": "residual-content-summary",
}
# Gates whose receipts this module consumes against its own producer-identity
# constants.  A registry row that disagrees with one of these would register a
# producer whose receipts this consumer rejects.
CONSUMED_PRODUCER_IDENTITY = {
    "profile-load": (check_profile.TOOL, check_profile.TOOL_VERSION),
    "batch-close": (BATCH_CLOSE_TOOL, BATCH_CLOSE_TOOL_VERSION),
    "corpus-plan-structure": (CORPUS_PLAN_TOOL, CORPUS_PLAN_TOOL_VERSION),
    "terminal-proof": (TERMINAL_PROOF_TOOL, TERMINAL_PROOF_TOOL_VERSION),
    "standards-adoption": (STANDARDS_ADOPTION_TOOL,
                           STANDARDS_ADOPTION_TOOL_VERSION),
    BATCH_REVIEW_GATE_ID: (MANUAL_ATTESTATION_TOOL,
                           MANUAL_ATTESTATION_TOOL_VERSION),
}
PRODUCER_MODULE_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
_TOOLS_ROOT = os.path.dirname(os.path.abspath(__file__))
_PRODUCER_MODULE_CACHE = {}
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


def current_receipt_catalog(result):
    """Return the adoption-filtered catalog for a new evidence decision.

    A present empty mapping is authoritative: falling back to the historical
    catalog in that case would re-enable every receipt explicitly declared
    invalidated.  There is deliberately no fallback to the historical catalog:
    a missing current view is an unavailable authorization source, not an
    invitation to reinterpret history as fresh evidence.
    """
    current = result.get("current_receipt_catalog")
    return current if isinstance(current, dict) else {}


def historical_receipt_catalog(result):
    """Return the immutable full catalog for history verification only."""
    historical = result.get("receipt_catalog")
    return historical if isinstance(historical, dict) else {}


def standards_gate_registry(root):
    """Parse the canonical Gate ID -> receipt predicate registry.

    K00/12 owns the table.  Plans cannot invent an opaque gate name: every
    affected/required gate must resolve to one stable producer identity that
    the revalidation aggregator can check without interpreting prose.
    """
    errors = []
    registry = {}
    try:
        path = kblib.repository_path(
            root, STANDARDS_GATE_REGISTRY_PATH, must_exist=True,
            reject_symlink=True)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, ["Gate ID registry is unsafe or unreadable: %s" % exc]
    inside = False
    seen_section = 0
    for line in text.splitlines():
        heading = re.match(r"^(#{2,3})\s+(.*?)\s*#*\s*$", line)
        if heading:
            is_registry = heading.group(2).strip() == "Stable Gate ID Registry"
            if is_registry:
                seen_section += 1
            inside = is_registry and seen_section == 1
            continue
        if not inside or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if cells == ["Gate ID", "Tool", "Tool version", "Check", "Mode",
                     "Dimension", "Lifecycle"]:
            continue
        if cells and all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) != 7:
            errors.append("Stable Gate ID Registry row must have seven cells")
            continue
        gate_id, tool, tool_version, check, mode, dimension, lifecycle = cells
        if not all(_nonempty_string(value) for value in cells):
            errors.append("Stable Gate ID Registry row has an empty cell")
            continue
        if "*" in (tool, tool_version, check):
            errors.append(
                "Stable Gate ID Registry Tool, Tool version, and Check must "
                "be exact for %s; only Mode may use *" % gate_id)
            continue
        if gate_id in registry:
            errors.append("Stable Gate ID Registry repeats %s" % gate_id)
            continue
        # The Dimension cell is a list, so it is tokenized rather than taken
        # whole: a Gate whose canonical gate files verdicts under several
        # dimensions registers all of them, and the consumer narrows to the
        # one its obligation names.
        dimensions = tuple(sorted({
            token.strip().strip("`")
            for token in re.split(r"[,\s]+", dimension) if token.strip()
        }))
        # The Lifecycle cell is tokenized the same way: a producer that
        # genuinely accepts several batch positions registers all of them.
        # It is not part of the receipt selector -- it says when the Gate can
        # be produced, not which receipt satisfies it -- so it is validated
        # here rather than in the producer-tuple agreement check.
        lifecycle_states = tuple(sorted({
            token.strip().strip("`")
            for token in re.split(r"[,\s]+", lifecycle) if token.strip()
        }))
        unknown_states = sorted(
            set(lifecycle_states) - set(kblib.BATCH_LIFECYCLE_TRANSITIONS) -
            UNSCOPED_GATE_POSITIONS)
        if unknown_states:
            errors.append(
                "Gate ID %s registers Lifecycle %s, which is neither a batch "
                "lifecycle state nor one of %s" % (
                    gate_id, ", ".join(unknown_states),
                    ", ".join(sorted(UNSCOPED_GATE_POSITIONS))))
            continue
        marker = sorted(set(lifecycle_states) & UNSCOPED_GATE_POSITIONS)
        if marker and len(lifecycle_states) != 1:
            errors.append(
                "Gate ID %s registers Lifecycle %s, which mixes %s with "
                "another position" % (
                    gate_id, ", ".join(lifecycle_states), marker[0]))
            continue
        registry[gate_id] = {
            "tool": tool,
            "tool_version": tool_version,
            "check": check,
            "mode": mode,
            "dimensions": dimensions,
            "lifecycle_states": lifecycle_states,
        }
    if seen_section != 1:
        errors.append("K00/12 must contain exactly one Stable Gate ID Registry")
    if not registry:
        errors.append("Stable Gate ID Registry has no gate rows")
    errors.extend(gate_registry_producer_errors(registry))
    return registry, errors


def standards_revalidation_capabilities(root, gate_registry=None):
    """Parse the closed Gate leaf-to-owner capability registry in K00/12.

    The Stable Gate ID Registry answers which receipt identifies a Gate and
    where its producer can run.  It does *not* answer whether a raw receipt is
    allowed to authorize a Standards-adoption boundary.  Keeping that second
    question in its own closed table prevents a semantic leaf from becoming a
    boundary authority merely because both happen to use the word ``Gate``.

    Every stable Gate occurs exactly once.  The role fixes the remaining four
    cells, and every semantic leaf points to a real native owner.  This makes
    the planner -> owner -> transition path machine-checkable before an
    adoption writes state.
    """
    errors = []
    capabilities = {}
    if gate_registry is None:
        gate_registry, gate_errors = standards_gate_registry(root)
        errors.extend(gate_errors)
    try:
        path = kblib.repository_path(
            root, STANDARDS_GATE_REGISTRY_PATH, must_exist=True,
            reject_symlink=True)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, errors + [
            "Standards revalidation capability registry is unsafe or "
            "unreadable: %s" % exc]

    inside = False
    seen_section = 0
    expected_header = [
        "Gate ID", "Role", "Owner", "Claim edge", "Scope protocol",
        "Binding protocol",
    ]
    for line in text.splitlines():
        heading = re.match(r"^(#{2,3})\s+(.*?)\s*#*\s*$", line)
        if heading:
            is_registry = heading.group(2).strip() == \
                STANDARDS_REVALIDATION_CAPABILITY_HEADING
            if is_registry:
                seen_section += 1
            inside = is_registry and seen_section == 1
            continue
        if not inside or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("`")
                 for cell in line.strip().strip("|").split("|")]
        if cells == expected_header:
            continue
        if cells and all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) != 6:
            errors.append(
                "Standards Revalidation Capability Registry row must have "
                "six cells")
            continue
        gate_id, role, owner, edge, scope, binding = cells
        if not all(_nonempty_string(value) for value in cells):
            errors.append(
                "Standards Revalidation Capability Registry row has an "
                "empty cell")
            continue
        if gate_id in capabilities:
            errors.append(
                "Standards Revalidation Capability Registry repeats %s" %
                gate_id)
            continue
        if role not in STANDARDS_REVALIDATION_CAPABILITY_ROLES:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Role %s" %
                (gate_id, role))
            continue
        if edge not in STANDARDS_REVALIDATION_CAPABILITY_EDGES:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Claim edge "
                "%s" % (gate_id, edge))
            continue
        if scope not in STANDARDS_REVALIDATION_SCOPE_PROTOCOLS:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Scope "
                "protocol %s" % (gate_id, scope))
            continue
        if binding not in STANDARDS_REVALIDATION_BINDING_PROTOCOLS:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Binding "
                "protocol %s" % (gate_id, binding))
            continue
        expected_contract = STANDARDS_REVALIDATION_ROLE_CONTRACTS[role]
        if (edge, scope, binding) != expected_contract:
            errors.append(
                "Gate ID %s Role %s requires Claim edge / Scope protocol / "
                "Binding protocol %s / %s / %s, found %s / %s / %s" % (
                    gate_id, role, *expected_contract, edge, scope, binding))
            continue
        capabilities[gate_id] = {
            "role": role,
            "owner": owner,
            "claim_edge": edge,
            "scope_protocol": scope,
            "binding_protocol": binding,
        }

    if seen_section != 1:
        errors.append(
            "K00/12 must contain exactly one Standards Revalidation "
            "Capability Registry")
    stable_ids = set(gate_registry or {})
    capability_ids = set(capabilities)
    missing = sorted(stable_ids - capability_ids)
    extra = sorted(capability_ids - stable_ids)
    if missing:
        errors.append(
            "Standards Revalidation Capability Registry omits stable Gate "
            "ID(s): %s" % ", ".join(missing))
    if extra:
        errors.append(
            "Standards Revalidation Capability Registry names unknown Gate "
            "ID(s): %s" % ", ".join(extra))
    for gate_id, capability in sorted(capabilities.items()):
        role = capability["role"]
        owner = capability["owner"]
        if role in ("special-owner", "immediate-owner", "native-owner"):
            if owner != gate_id:
                errors.append(
                    "Standards revalidation owner Gate %s must own itself, "
                    "not %s" % (gate_id, owner))
        elif role == "semantic-leaf":
            owner_capability = capabilities.get(owner)
            if owner == gate_id or not isinstance(owner_capability, dict) or \
                    owner_capability.get("role") != "native-owner":
                errors.append(
                    "Standards revalidation semantic leaf %s must project "
                    "to a distinct native owner; found %s" %
                    (gate_id, owner))
        elif owner != "none":
            errors.append(
                "Standards revalidation Gate %s Role %s must use Owner none, "
                "not %s" % (gate_id, role, owner))
    return capabilities, errors


def standards_gate_capability_registry(root, gate_registry=None):
    """Public spelling for the Gate capability registry.

    The longer internal name predates the registry's canonical heading.  Keep
    one implementation and expose the name used by callers that reason about
    Gate identity and Gate authority as two different registries.
    """
    return standards_revalidation_capabilities(root, gate_registry)


def standards_revalidation_owner(gate_id, capabilities):
    """Return the blocking owner of one semantic Gate, or ``None``.

    ``None`` is reserved for advisory/mechanism-only Gates that intentionally
    create no blocking claim.  Unsupported and unknown Gates raise a value
    error so a new plan cannot convert an absent capability into a waiver.
    """
    capability = capabilities.get(gate_id)
    if not isinstance(capability, dict):
        raise ValueError("Gate ID %s has no Standards revalidation capability"
                         % gate_id)
    role = capability.get("role")
    if role in ("special-owner", "immediate-owner", "native-owner"):
        return gate_id
    if role == "semantic-leaf":
        return capability.get("owner")
    if role == "advisory":
        return None
    if role == "mechanism-only":
        raise ValueError(
            "Gate ID %s has Role mechanism-only and cannot be used as an "
            "adoption boundary Gate" % gate_id)
    raise ValueError(
        "Gate ID %s has Role unsupported and cannot be used as an adoption "
        "boundary Gate" % gate_id)


def projected_revalidation_owners(gate_ids, capabilities):
    """Project semantic Gate IDs to the exact sorted blocking owner set."""
    owners = set()
    errors = []
    for gate_id in sorted({value for value in gate_ids
                           if _nonempty_string(value)}):
        try:
            owner = standards_revalidation_owner(gate_id, capabilities)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if owner is not None:
            owners.add(owner)
    return sorted(owners), errors


def project_adoption_gate_ids(gate_ids, capabilities):
    """Return the immediate and native owner closure for affected Gate IDs.

    Profile admission is evaluated against the writable after-image before an
    adoption commits, so it deliberately belongs to neither runtime list.
    Advisory observations likewise create no blocking owner.  Any unsupported
    or mechanism-only input remains an explicit error.
    """
    owners, errors = projected_revalidation_owners(gate_ids, capabilities)
    immediate = []
    native = []
    for gate_id in owners:
        role = (capabilities.get(gate_id) or {}).get("role")
        if role == "immediate-owner":
            immediate.append(gate_id)
        elif role == "native-owner":
            native.append(gate_id)
    return immediate, native, errors


def producer_module(tool):
    """Return the installed module a registry ``Tool`` cell names, or None.

    The producer is resolved next to this file rather than under the
    repository being checked: the module that will actually run is the one
    whose constants end up in the receipt, and an adopter's copy of the
    Standards text never redefines that identity.
    """
    if tool in _PRODUCER_MODULE_CACHE:
        return _PRODUCER_MODULE_CACHE[tool]
    module = None
    # Anchored on the Tools root, not on this file's directory.  A producer is
    # a sibling of the tools tree, not of whichever module happens to ask; if
    # this resolved relative to the caller it would find nothing from inside a
    # package and every lookup would return None -- and a missing producer is
    # read as "nothing to check", so the failure would be silent.
    if isinstance(tool, str) and PRODUCER_MODULE_RE.match(tool) and \
            os.path.isfile(os.path.join(_TOOLS_ROOT, tool + ".py")):
        try:
            module = importlib.import_module(tool)
        except Exception:  # pragma: no cover - a broken producer is an error
            module = None
    _PRODUCER_MODULE_CACHE[tool] = module
    return module


def registered_gate_check(gate_id, module):
    """Return the check name the producer of ``gate_id`` actually writes."""
    # A producer registering several Gates exports the whole mapping; the
    # single GATE_CHECK export remains the one-Gate spelling.
    mapping = getattr(module, "GATE_CHECKS", None) if module else None
    declared = None
    if isinstance(mapping, dict):
        declared = mapping.get(gate_id)
    if declared is None:
        declared = getattr(module, "GATE_CHECK", None) if module else None
    consumed = CONSUMED_GATE_CHECKS.get(gate_id)
    if declared is not None and consumed is not None and declared != consumed:
        return None
    return declared if declared is not None else consumed


def gate_registry_producer_errors(registry):
    """Return every K00/12 row whose producer tuple its producer contradicts.

    All five selector columns are compared against a source outside the table:

    * ``Tool`` names either the ``manual-attestation`` producer class or an
      installed module whose ``TOOL`` equals the cell.
    * ``Tool version`` equals that module's ``TOOL_VERSION`` -- the value it
      stamps on every receipt -- or, for a hand-recorded receipt, the single
      current ``manual-attestation`` protocol version K00/12 states.
    * ``Check`` equals the check name the producer writes for this Gate, and
      ``Gate ID`` equals the Gate the producer binds, where the module
      exports them.
    * ``Mode`` narrows on ``queue_check_mode``, a field only ``check_queue``
      writes.  A ``check_queue`` row therefore carries a mode that
      :func:`queue_gate_id_for_mode` maps back to the same Gate ID, and every
      other row carries ``*``: a narrower mode elsewhere could never match.
    * ``Dimension`` narrows on ``dimension``.  A named producer that exports
      ``GATE_DIMENSION`` must register that exact base dimension; other named
      producers carry ``*`` because they do not write the field.  A manual
      attestation may select one or more base dimensions, and ``none`` says
      the Gate's own receipt has no dimension.

    The five cells together are the receipt selector, so two Gate IDs may not
    share one tuple either.  This is a judgment, not an adjudication: the
    caller is told the two sides disagree, never which side to change.
    """
    errors = []
    selectors = {}
    for gate_id in sorted(registry):
        predicate = registry[gate_id]
        tool = predicate["tool"]
        mode = predicate["mode"]
        dimensions = predicate.get("dimensions") or ()
        module = (None if tool == MANUAL_ATTESTATION_TOOL
                  else producer_module(tool))
        declared_dimension = getattr(module, "GATE_DIMENSION", None)
        selector = (tool, predicate["tool_version"], predicate["check"], mode,
                    ",".join(dimensions))
        selectors.setdefault(selector, []).append(gate_id)
        if UNNARROWED_GATE_DIMENSION in dimensions or \
                UNDIMENSIONED_GATE in dimensions:
            if len(dimensions) != 1:
                errors.append(
                    "Gate ID %s registers Dimension %s, which mixes %r with "
                    "named dimensions" % (
                        gate_id, "/".join(dimensions), dimensions[0]))
            elif dimensions[0] == UNNARROWED_GATE_DIMENSION:
                if (tool == MANUAL_ATTESTATION_TOOL or
                        declared_dimension is not None):
                    errors.append(
                        "Gate ID %s registers Dimension %s against Tool %s, "
                        "but that producer %s" % (
                            gate_id, dimensions[0], tool,
                            "declares %s" % declared_dimension
                            if declared_dimension is not None else
                            "is manually dimensioned"))
            elif tool != MANUAL_ATTESTATION_TOOL:
                errors.append(
                    "Gate ID %s registers Dimension none against named "
                    "producer %s%s" % (
                        gate_id, tool,
                        ", which declares %s" % declared_dimension
                        if declared_dimension is not None else ""))
        else:
            unknown = sorted(set(dimensions) - BASE_RECEIPT_DIMENSIONS)
            if unknown:
                errors.append(
                    "Gate ID %s registers Dimension %s, which K12/07 does not "
                    "fix as a base receipt dimension" % (
                        gate_id, ", ".join(unknown)))
            if tool != MANUAL_ATTESTATION_TOOL:
                if declared_dimension is None:
                    errors.append(
                        "Gate ID %s narrows Dimension to %s, but its producer "
                        "%s writes no dimension field" % (
                            gate_id, ", ".join(dimensions), tool))
                elif dimensions != (declared_dimension,):
                    errors.append(
                        "Gate ID %s registers Dimension %s but producer %s "
                        "emits %s" % (
                            gate_id, ", ".join(dimensions), tool,
                            declared_dimension))
        consumed = CONSUMED_PRODUCER_IDENTITY.get(gate_id)
        if consumed is not None and consumed != (tool,
                                                 predicate["tool_version"]):
            errors.append(
                "Gate ID %s registers producer %s/%s but this checker "
                "consumes its receipts as %s/%s" % (
                    gate_id, tool, predicate["tool_version"], *consumed))
        if tool == TOOL:
            probe = mode[:-1] if mode.endswith("*") else mode
            if queue_gate_id_for_mode(probe) != gate_id:
                errors.append(
                    "Gate ID %s registers Mode %s, which %s does not emit for "
                    "that Gate" % (gate_id, mode, TOOL))
        elif mode != "*":
            errors.append(
                "Gate ID %s registers Mode %s, but only %s receipts carry "
                "queue_check_mode" % (gate_id, mode, TOOL))
        if tool == MANUAL_ATTESTATION_TOOL:
            if predicate["tool_version"] != MANUAL_ATTESTATION_TOOL_VERSION:
                errors.append(
                    "Gate ID %s registers manual-attestation protocol version "
                    "%s, not the current %s" % (
                        gate_id, predicate["tool_version"],
                        MANUAL_ATTESTATION_TOOL_VERSION))
            continue
        if module is None or getattr(module, "TOOL", None) != tool:
            errors.append(
                "Gate ID %s registers Tool %s, which is not an installed "
                "producer of that name" % (gate_id, tool))
            continue
        if getattr(module, "TOOL_VERSION", None) != predicate["tool_version"]:
            errors.append(
                "Gate ID %s registers Tool version %s but %s stamps %s" % (
                    gate_id, predicate["tool_version"], tool,
                    getattr(module, "TOOL_VERSION", None)))
        declared_gate = getattr(module, "GATE_ID", None)
        declared_gates = getattr(module, "GATE_CHECKS", None)
        admitted = (isinstance(declared_gates, dict) and
                    gate_id in declared_gates)
        if (declared_gate is not None and tool != TOOL and
                declared_gate != gate_id and not admitted):
            errors.append(
                "Gate ID %s registers Tool %s, which binds %s to its receipts"
                % (gate_id, tool, declared_gate))
        expected_check = registered_gate_check(gate_id, module)
        if expected_check is None:
            errors.append(
                "Gate ID %s registers Check %s against %s, which declares no "
                "check name for it" % (gate_id, predicate["check"], tool))
        elif expected_check != predicate["check"]:
            errors.append(
                "Gate ID %s registers Check %s but %s writes %s" % (
                    gate_id, predicate["check"], tool, expected_check))
    for selector, gate_ids in sorted(selectors.items()):
        if len(gate_ids) > 1:
            errors.append(
                "Gate IDs %s share one receipt selector %s" % (
                    ", ".join(gate_ids), "/".join(selector)))
    return errors


def registered_gate_dimensions(gate_id, registry):
    """Return the receipt dimensions K00/12 admits for ``gate_id``.

    ``None`` means the row is not narrowed on dimension at all.  An empty
    frozenset means the Gate's receipt carries no ``dimension`` field.
    """
    predicate = registry.get(gate_id)
    if not isinstance(predicate, dict):
        return None
    dimensions = predicate.get("dimensions") or ()
    if UNNARROWED_GATE_DIMENSION in dimensions:
        return None
    if dimensions == (UNDIMENSIONED_GATE,):
        return frozenset()
    return frozenset(dimensions)


def registered_gate_position(gate_id, registry):
    """Return the position K00/12 registers ``gate_id``'s producer for.

    One of three forms, matching the three forms of the Lifecycle cell:

    * ``None`` -- unpositioned.  The producer takes no batch and nothing about
      the Queue constrains it, so every batch is always at this position.  An
      unregistered Gate ID answers the same way, which is the fail-closed
      answer here: an unknown Gate is treated as producible now and therefore
      still owed a receipt, which the registry match then rejects.
    * ``QUEUE_EXHAUSTED_GATE`` -- the position the Queue reaches when it holds
      no non-terminal batch.
    * a ``frozenset`` of batch lifecycle states -- the positions of the batch
      itself at which the producer runs.
    """
    predicate = registry.get(gate_id)
    if not isinstance(predicate, dict):
        return None
    states = predicate.get("lifecycle_states") or ()
    if not states or NOT_BATCH_SCOPED_GATE in states:
        return None
    if QUEUE_EXHAUSTED_GATE in states:
        return QUEUE_EXHAUSTED_GATE
    return frozenset(states)


def partition_boundary_gates_by_lifecycle(gate_ids, state, registry):
    """Split boundary Gate IDs by where a batch at ``state`` can claim them.

    A boundary's required gates are claimed at the transition each one belongs
    to, not all at once when a hold is discharged.  Every Gate ID has one
    registered position; judged against one target batch's own position, it
    falls in exactly one of three sets:

    * **due** -- the batch is at that position now, so the gate can be
      produced and its receipt is required by the revalidation aggregate.  An
      unpositioned Gate is always due.
    * **deferred** -- the position is still ahead of the batch, so the gate is
      claimed at the transition that reaches it.  That transition already
      requires the gate natively, so nothing new enforces this.
    * **passed** -- the position is behind the batch and no sanctioned
      transition returns to it, so the evidence cannot be remade.  The batch
      proceeds carrying what it has, recorded as unrepeatable.

    The comparison is the same question for all three kinds of position; only
    how "ahead" is read differs.  For a batch-state position it is the forward
    closure of the one lifecycle map in ``kblib``, so this cannot disagree with
    the writer that applies the transitions.  Queue exhaustion is ahead of
    every non-terminal batch -- that batch must reach a terminal state before
    the Queue can hold none -- and behind none, because a terminal batch never
    returns to non-terminal.  A batch whose ``state`` is not a known lifecycle
    state has no reachable successor, so every Gate is due and nothing is
    waived.
    """
    due, deferred, passed = [], [], []
    known_state = state in kblib.BATCH_LIFECYCLE_TRANSITIONS
    reachable = kblib.reachable_batch_states(state)
    for gate_id in sorted({value for value in gate_ids
                           if _nonempty_string(value)}):
        position = registered_gate_position(gate_id, registry)
        if position is None or not known_state:
            due.append(gate_id)
        elif position == QUEUE_EXHAUSTED_GATE:
            (due if state in TERMINAL_STATES else deferred).append(gate_id)
        elif state in position:
            due.append(gate_id)
        elif position & reachable:
            deferred.append(gate_id)
        else:
            passed.append(gate_id)
    return due, deferred, passed


def partition_revalidation_owner_claims(owner_gate_ids, state, registry,
                                        capabilities):
    """Partition owner Gates by their *claim edge*, not producer availability.

    K00/12 Lifecycle says where a producer accepts an invocation.  A native
    transition Gate may accept one while the batch is queued/open/merge-ready,
    but a Standards hold must not demand it in the source state: the receipt
    belongs to the transition itself, after the hold has cleared.  Conflating
    those two facts made ``required-queue-admission`` due while its own
    producer refused a held batch and made semantic leaf checks block content
    before the lifecycle allowed content to be repaired.

    Immediate owners are the only raw receipts due in the aggregate.  Native
    owners at their position or ahead are deferred to their mandatory edge;
    an owner whose edge the batch already passed is unrepeatable here and a
    current plan is refused before it can create such a claim.
    """
    due, deferred, passed = [], [], []
    known_state = state in kblib.BATCH_LIFECYCLE_TRANSITIONS
    reachable = kblib.reachable_batch_states(state)
    for gate_id in sorted({value for value in owner_gate_ids
                           if _nonempty_string(value)}):
        capability = capabilities.get(gate_id) or {}
        role = capability.get("role")
        if role == "immediate-owner":
            due.append(gate_id)
            continue
        if role != "native-owner":
            # A malformed projection is due so the exact receipt set cannot
            # silently shrink.  The capability error reported alongside it
            # explains why no receipt can satisfy the claim.
            due.append(gate_id)
            continue
        position = registered_gate_position(gate_id, registry)
        if position is None or not known_state:
            passed.append(gate_id)
        elif position == QUEUE_EXHAUSTED_GATE:
            (passed if state in TERMINAL_STATES else deferred).append(gate_id)
        elif state in position or position & reachable:
            deferred.append(gate_id)
        else:
            passed.append(gate_id)
    return due, deferred, passed


def receipt_matches_gate_id(receipt, gate_id, registry, dimension=None):
    """Return whether one receipt satisfies the registered producer tuple.

    ``dimension``, when given, is the single receipt dimension the consumer's
    own obligation was raised in.  A Gate ID whose canonical gate files
    verdicts under several dimensions -- `content-correctness` and `rendering`
    are the live cases -- is not identified by the producer tuple alone: every
    dimension's attestation carries the same tool, version, check, and mode,
    so without this argument evidence re-established in one dimension
    discharges an obligation raised in another.
    """
    predicate = registry.get(gate_id)
    if not isinstance(receipt, dict) or not isinstance(predicate, dict):
        return False
    # A new revalidation aggregate never infers identity from descriptive
    # fields.  Every raw input must bind the registry key explicitly.  Older
    # receipts without ``gate_id`` remain available to historical validators,
    # but this function is a current-action predicate and must reject them.
    if receipt.get("gate_id") != gate_id:
        return False
    if predicate["tool"] != "*" and receipt.get("tool") != predicate["tool"]:
        return False
    if (predicate["tool_version"] != "*" and
            receipt.get("tool_version") != predicate["tool_version"]):
        return False
    if predicate["check"] != "*" and receipt.get("check") != predicate["check"]:
        return False
    registered = registered_gate_dimensions(gate_id, registry)
    if registered is not None:
        actual_dimension = receipt.get("dimension")
        if registered:
            # A missing field is a rejection, not a wildcard: an attestation
            # that never said which dimension it filed under has not been
            # narrowed by anyone, and reading silence as agreement is exactly
            # the hole this closes.
            if actual_dimension not in registered:
                return False
        elif actual_dimension is not None:
            return False
        if dimension is not None and actual_dimension != dimension:
            return False
    expected_mode = predicate["mode"]
    if expected_mode == "*":
        return True
    actual_mode = receipt.get("queue_check_mode")
    if expected_mode.endswith("*"):
        return isinstance(actual_mode, str) and actual_mode.startswith(
            expected_mode[:-1])
    return actual_mode == expected_mode


def queue_gate_id_for_mode(mode):
    """Return the stable Gate ID for a gate-producing Queue mode."""
    if mode == "consistency":
        return "required-queue-consistency"
    if isinstance(mode, str) and mode.startswith("require-ready:"):
        return "required-queue-admission"
    if isinstance(mode, str) and mode.startswith("require-revalidation:"):
        return "standards-revalidation"
    if mode == "require-complete":
        return "required-queue-completion"
    if mode == "require-maintenance-complete":
        return "maintenance-completion"
    if mode == "resume-status":
        return "runtime-startup-recovery"
    return None
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
TASK_LIFECYCLE_EDGES = frozenset((
    ("planned", "active"),
    ("planned", "paused"),
    ("planned", "blocked"),
    ("planned", "completion-candidate"),
    ("planned", "complete"),
    ("planned", "cancelled"),
    ("active", "paused"),
    ("active", "blocked"),
    ("active", "completion-candidate"),
    ("active", "complete"),
    ("active", "cancelled"),
    ("paused", "active"),
    ("paused", "blocked"),
    ("paused", "cancelled"),
    ("blocked", "active"),
    ("blocked", "paused"),
    ("blocked", "cancelled"),
    ("completion-candidate", "active"),
    ("completion-candidate", "paused"),
    ("completion-candidate", "blocked"),
    ("completion-candidate", "complete"),
    ("completion-candidate", "cancelled"),
))
FINAL_CONTROL_STATUSES = frozenset((
    "verified", "deferred", "superseded", "not-applicable",
    # K13/06: a withdrawn operational Amendment is final — it authorizes
    # nothing and is never resumed, so it raises no reconcile obligation.
    "withdrawn",
))






def delta_gate_receipt_ids(delta):
    """Return the deterministic receipt-ID set carried by delta pages."""
    if not isinstance(delta, dict):
        raise ValueError("delta document must be a mapping")
    pages = delta.get("pages")
    if not isinstance(pages, list):
        raise ValueError("delta pages must be an explicit list")
    receipt_ids = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError("delta pages[%d] must be a mapping" % index)
        gate_receipts = page.get("gate_receipts")
        if (not isinstance(gate_receipts, list) or not gate_receipts or
                not all(_nonempty_string(value) for value in gate_receipts)):
            raise ValueError("delta pages[%d] gate_receipts must be a non-empty "
                             "string list" % index)
        if len(gate_receipts) != len(set(gate_receipts)):
            raise ValueError("delta pages[%d] gate_receipts must be unique" %
                             index)
        receipt_ids.update(gate_receipts)
    return sorted(receipt_ids)






def _policy_exception_errors(value, label):
    """Validate the contract's bounded policy exceptions, K13/02 shape.

    Every entry is an answer a person already gave: which policy it excepts,
    the bound it grants, what it was granted against, and where the approval
    lives.  The baseline fingerprint is what makes an exception die with the
    policy it was judged against instead of surviving a Standards or Profile
    revision it never saw.
    """
    errors = []
    if not isinstance(value, list):
        return ["%s must be an explicit list" % label]
    seen = set()
    for index, entry in enumerate(value):
        entry_label = "%s[%d]" % (label, index)
        if not isinstance(entry, dict):
            errors.append("%s must be a mapping" % entry_label)
            continue
        errors.extend(_closed_mapping_errors(
            entry, entry_label, POLICY_EXCEPTION_FIELDS))
        if not isinstance(entry, dict) or set(entry) - POLICY_EXCEPTION_FIELDS:
            continue
        for field in ("decision_id", "policy_id", "scope_ref", "rationale",
                      "approval_reference"):
            if not _nonempty_string(entry.get(field)):
                errors.append("%s %s must be a non-empty string" %
                              (entry_label, field))
        decision = entry.get("decision_id")
        if _nonempty_string(decision):
            if decision in seen:
                errors.append("%s repeats decision_id %s" %
                              (label, decision))
            seen.add(decision)
        fingerprint = entry.get("baseline_policy_fingerprint")
        if (not isinstance(fingerprint, str) or
                not SHA256_RE.fullmatch(fingerprint)):
            errors.append(
                "%s baseline_policy_fingerprint must be sha256:<64 lowercase "
                "hex>; an exception unbound from the policy bytes it was "
                "judged against would survive revisions it never saw" %
                entry_label)
        policy_id = entry.get("policy_id")
        registered = (
            contract_exception_policy.POLICY_REGISTRY.get(policy_id)
            if isinstance(policy_id, str) else None)
        if _nonempty_string(policy_id) and registered is None:
            errors.append(
                "%s policy_id %r is not in the closed policy registry; an "
                "exception to a policy nobody registered is unbounded "
                "authorization" % (entry_label, policy_id))
        limit = entry.get("limit")
        domain = registered.get("limit_domain") if registered else None
        if (not isinstance(limit, (int, float)) or isinstance(limit, bool)):
            errors.append("%s limit must be a number" % entry_label)
        elif domain == "percent-share-under-100" and not 0 <= limit < 100:
            errors.append(
                "%s limit must be a corpus share at least 0 and under 100; "
                "%r is not a bound, per %s" %
                (entry_label, limit, registered["owner"]))
        elif domain == "record-count-ceiling" and (
                isinstance(limit, float) or limit < 0):
            errors.append(
                "%s limit must be a non-negative whole record count; %r "
                "cannot be compared to a number of records, per %s" %
                (entry_label, limit, registered["owner"]))
        if entry.get("scope_kind") not in POLICY_EXCEPTION_SCOPE_KINDS:
            errors.append(
                "%s scope_kind must be one of %s" %
                (entry_label,
                 ", ".join(sorted(POLICY_EXCEPTION_SCOPE_KINDS))))
    # Joint bound and conflict rules across the register: the granted P0 and
    # P1 ceilings partition the same corpus as the standing quotas do, and
    # two grants for the same policy in the same scope are a conflict, not a
    # choice the consumer may make.
    by_key = {}
    ceilings = {}
    for entry in value:
        if not isinstance(entry, dict):
            continue
        policy_id = entry.get("policy_id")
        limit = entry.get("limit")
        key = (policy_id, entry.get("scope_kind"), entry.get("scope_ref"))
        if all(key):
            if key in by_key:
                errors.append(
                    "%s carries conflicting grants for %s in the same scope; "
                    "one policy has one current bound" % (label, policy_id))
            by_key[key] = entry
        if (isinstance(limit, (int, float)) and not isinstance(limit, bool)
                and isinstance(policy_id, str) and
                policy_id in contract_exception_policy.POLICY_REGISTRY):
            ceilings[policy_id] = max(ceilings.get(policy_id, 0), limit)
    if (ceilings.get("priority_quota.P0", 0) +
            ceilings.get("priority_quota.P1", 0)) >= 100:
        errors.append(
            "%s granted quota ceilings sum to %.1f%%; K00/07 requires the "
            "pair to stay strictly below 100 so the P2 remainder class "
            "stays non-empty" %
            (label, ceilings.get("priority_quota.P0", 0) +
             ceilings.get("priority_quota.P1", 0)))
    return errors


def _sealed_policy_exception_errors(sealed, decision_id, candidate_type,
                                    label):
    """Validate one sealed policy-exception decision record, strictly.

    The sealed mapping is the durable record of an authorization; replay
    validates it with the same severity the close-time writer applied, and
    every check here FAILS CLOSED: a field of the wrong type is an error,
    never a skipped comparison.  In particular the share arithmetic is only
    meaningful over validated integers -- guarding it behind an isinstance
    test that silently skips on mismatch would let a string smuggle an
    unverified authorization through replay.
    """
    errors = []
    errors.extend(_closed_mapping_errors(
        sealed, "%s sealed policy exception" % label,
        SEALED_POLICY_EXCEPTION_FIELDS))
    if set(sealed) != set(SEALED_POLICY_EXCEPTION_FIELDS):
        return errors
    if sealed.get("decision_id") != decision_id:
        errors.append("%s sealed decision_id does not match accepted_by" %
                      label)
    policy_id = sealed.get("policy_id")
    registered = (contract_exception_policy.POLICY_REGISTRY.get(policy_id)
                  if isinstance(policy_id, str) else None)
    if registered is None:
        errors.append(
            "%s sealed policy_id %r is not in the closed policy registry" %
            (label, policy_id))
    else:
        # The candidate names its class in its type (`...:priority-quota-P0`)
        # and the exception names its policy; the two must be the same class.
        # A P0 excess accepted through a P1 grant is an authorization for a
        # different decision than the one the reviewer sealed.
        suffix = str(candidate_type or "").rsplit(":", 1)[-1]
        expected_suffix = "priority-quota-%s" % registered.get("quota_class")
        if suffix != expected_suffix:
            errors.append(
                "%s sealed policy %s covers class %s, but the candidate is "
                "%r; an exception authorizes exactly its own class" %
                (label, policy_id, registered.get("quota_class"),
                 candidate_type))
    fingerprint = sealed.get("policy_fingerprint")
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(
            fingerprint):
        errors.append(
            "%s sealed policy_fingerprint must be sha256:<64 lowercase "
            "hex>" % label)
    if sealed.get("scope_kind") not in POLICY_EXCEPTION_SCOPE_KINDS:
        errors.append("%s sealed scope_kind must be one of %s" %
                      (label, ", ".join(sorted(POLICY_EXCEPTION_SCOPE_KINDS))))
    if not _nonempty_string(sealed.get("scope_ref")):
        errors.append("%s sealed scope_ref must be a non-empty string" %
                      label)
    limit = sealed.get("limit")
    limit_ok = (not isinstance(limit, bool) and
                isinstance(limit, (int, float)))
    if not limit_ok:
        errors.append("%s sealed limit must be a number" % label)
    elif (registered is not None and
          registered.get("limit_domain") == "percent-share-under-100" and
          not 0 <= limit < 100):
        errors.append(
            "%s sealed limit %r is not a corpus share at least 0 and under "
            "100" % (label, limit))
        limit_ok = False
    counts_ok = True
    for field in ("pages", "total"):
        value = sealed.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append("%s sealed %s must be an integer" % (label, field))
            counts_ok = False
    if counts_ok:
        pages, total = sealed["pages"], sealed["total"]
        if not (0 <= pages <= total and total >= 1):
            errors.append(
                "%s sealed counts %r/%r are not a corpus share" %
                (label, pages, total))
            counts_ok = False
    if (counts_ok and limit_ok and
            not kblib.quota_share_within_limit(
                sealed["pages"], sealed["total"], limit)):
        errors.append(
            "%s sealed share %s/%s exceeds the sealed limit %r; the receipt "
            "claims an authorization its own numbers refute" %
            (label, sealed.get("pages"), sealed.get("total"), limit))
    return errors






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


def _contract_sha256(progress):
    """Return the canonical fingerprint of the immutable Task Contract.

    Before initial Queue materialization the contract is still an adopter
    input.  Once materialized, the compiler receipt and every task-state
    transition must carry this exact fingerprint.  Until a dedicated contract
    Amendment writer exists, any later mutation therefore fails closed.
    """
    contract = progress.get("contract") if isinstance(progress, dict) else None
    if not isinstance(contract, dict):
        return None
    try:
        return kblib.sha256_bytes(kblib.canonical_yaml(contract))
    except (TypeError, ValueError, kblib.YamlSubsetError):
        return None


def _contract_anchor_chain(progress, catalog):
    """Return the hash-linked Task Contract anchor chain.

    Scope Amendments and Standards adoptions are independent append-only logs.
    Their receipt before/after contract fingerprints, rather than list order,
    form one unambiguous chain.  This lets a later Amendment continue from an
    adopted Standards contract without either writer owning the other's log.
    """
    errors = []
    receipt_id = progress.get("initial_queue_receipt")
    entry = catalog.get(receipt_id) if _nonempty_string(receipt_id) else None
    if entry is None:
        return [], errors
    initial = entry[1]
    anchor = initial.get("contract_sha256")
    revision = initial.get("after_queue_revision")
    version = initial.get("contract_version")
    scope = initial.get("contract_scope_version")
    if not isinstance(anchor, str) or not SHA256_RE.fullmatch(anchor):
        errors.append("initial Queue receipt has invalid contract_sha256")
        return [], errors
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append("initial Queue receipt has invalid contract anchor revision")
        return [], errors
    if not _nonempty_string(version):
        errors.append("initial Queue receipt has invalid contract_version anchor")
    if not _nonempty_string(scope):
        errors.append("initial Queue receipt has invalid contract_scope_version anchor")
    chain = [{
        "queue_revision": revision,
        "contract_sha256": anchor,
        "contract_version": version,
        "scope_version": scope,
        "receipt_id": receipt_id,
    }]
    events = []
    for amendment in progress.get("amendments", []) if isinstance(
            progress.get("amendments"), list) else []:
        if (not isinstance(amendment, dict) or
                amendment.get("operation") not in
                ("scope-replan", "cancel-batch", "contract-amendment") or
                amendment.get("status") != "verified" or
                amendment.get("writeback_done") is not True):
            continue
        commit_id = amendment.get("verification_receipt")
        commit_entry = catalog.get(commit_id) if _nonempty_string(
            commit_id) else None
        if commit_entry is None:
            continue
        receipt = commit_entry[1]
        label = "Amendment %s contract anchor" % amendment.get("id")
        valid = True
        for field in ("before_contract_sha256", "after_contract_sha256"):
            value = receipt.get(field)
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append("%s has invalid %s" % (label, field))
                valid = False
        if receipt.get("after_contract_scope_version") != amendment.get(
                "scope_version_after"):
            errors.append("%s after scope does not match its Amendment" % label)
            valid = False
        if receipt.get("before_contract_scope_version") != amendment.get(
                "scope_version_before"):
            errors.append("%s before scope does not match its Amendment" % label)
            valid = False
        if (amendment.get("operation") == "contract-amendment" and
                receipt.get("before_contract_scope_version") !=
                receipt.get("after_contract_scope_version")):
            # Scope belongs to the replan machinery; a contract amendment
            # that moved scope_version would be a scope change routed
            # around the Coverage proposal it requires.
            errors.append("%s may not change scope_version" % label)
            valid = False
        if not _nonempty_string(receipt.get("after_contract_version")):
            errors.append("%s has invalid after_contract_version" % label)
            valid = False
        if receipt.get("queue_revision_after") != amendment.get(
                "queue_revision_after"):
            errors.append(
                "%s queue revision does not match its Amendment" % label
            )
            valid = False
        if valid:
            events.append({
                "label": label,
                "receipt_id": commit_id,
                "before_sha": receipt.get("before_contract_sha256"),
                "after_sha": receipt.get("after_contract_sha256"),
                "before_version": receipt.get("before_contract_version"),
                "after_version": receipt.get("after_contract_version"),
                "before_scope": receipt.get("before_contract_scope_version"),
                "after_scope": receipt.get("after_contract_scope_version"),
                "revision_before": receipt.get("queue_revision_before"),
                "revision_after": receipt.get("queue_revision_after"),
            })
    for adoption in progress.get("standards_adoptions", []) if isinstance(
            progress.get("standards_adoptions"), list) else []:
        if not isinstance(adoption, dict):
            continue
        commit_id = adoption.get("verification_receipt")
        commit_entry = catalog.get(commit_id) if _nonempty_string(
            commit_id) else None
        if commit_entry is None:
            continue
        receipt = commit_entry[1]
        label = "Standards adoption %s contract anchor" % adoption.get("id")
        valid = True
        for field in ("before_contract_sha256", "after_contract_sha256"):
            value = receipt.get(field)
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append("%s has invalid %s" % (label, field))
                valid = False
        if receipt.get("queue_revision_before") != adoption.get(
                "queue_revision_before") or receipt.get(
                    "queue_revision_after") != adoption.get(
                        "queue_revision_after"):
            errors.append("%s queue revision does not match its record" % label)
            valid = False
        if receipt.get("before_contract_scope_version") != receipt.get(
                "after_contract_scope_version"):
            errors.append("%s may not change scope_version" % label)
            valid = False
        if (receipt.get("before_contract_version") != adoption.get(
                "contract_version_before") or
                receipt.get("after_contract_version") != adoption.get(
                    "contract_version_after")):
            errors.append("%s contract versions do not match its record" % label)
            valid = False
        if valid:
            events.append({
                "label": label,
                "receipt_id": commit_id,
                "before_sha": receipt.get("before_contract_sha256"),
                "after_sha": receipt.get("after_contract_sha256"),
                "before_version": receipt.get("before_contract_version"),
                "after_version": receipt.get("after_contract_version"),
                "before_scope": receipt.get("before_contract_scope_version"),
                "after_scope": receipt.get("after_contract_scope_version"),
                "revision_before": receipt.get("queue_revision_before"),
                "revision_after": receipt.get("queue_revision_after"),
            })

    remaining = list(events)
    while remaining:
        # A queue-replan bumps the live queue_revision without touching the
        # Task Contract, so it is deliberately not an anchor event; the next
        # anchor event therefore continues from the same contract identity at
        # a strictly later revision. The contract bytes, version, and scope
        # remain the chain; revisions only need to stay monotonic and agree
        # with each event's own sealed before/after pair.
        candidates = [event for event in remaining
                      if event["before_sha"] == anchor and
                      event["before_version"] == version and
                      event["before_scope"] == scope and
                      isinstance(event["revision_before"], int) and
                      not isinstance(event["revision_before"], bool) and
                      event["revision_before"] >= revision]
        if not candidates:
            errors.extend("%s does not continue the prior contract anchor" %
                          event["label"] for event in remaining)
            break
        if len(candidates) != 1:
            errors.append("contract anchor chain forks at %s via %s" % (
                anchor, ", ".join(sorted(event["label"]
                                         for event in candidates))))
            break
        event = candidates[0]
        remaining.remove(event)
        next_revision = event["revision_after"]
        if (not isinstance(next_revision, int) or
                isinstance(next_revision, bool) or
                next_revision != event["revision_before"] + 1):
            errors.append("%s must increment queue_revision exactly once" %
                          event["label"])
            break
        anchor = event["after_sha"]
        version = event["after_version"]
        scope = event["after_scope"]
        revision = next_revision
        chain.append({
            "queue_revision": revision,
            "contract_sha256": anchor,
            "contract_version": version,
            "scope_version": scope,
            "receipt_id": event["receipt_id"],
        })

    if (isinstance(progress.get("queue_revision"), int) and
            not isinstance(progress.get("queue_revision"), bool) and
            revision > progress.get("queue_revision")):
        errors.append("contract anchor chain points beyond live Queue revision")
    live_contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    if chain:
        if anchor != _contract_sha256(progress):
            errors.append("contract anchor chain does not bind the current Task Contract")
        if version != live_contract.get("contract_version"):
            errors.append("contract anchor chain does not bind current contract_version")
        if scope != live_contract.get("scope_version"):
            errors.append("contract anchor chain does not bind current scope_version")
    return chain, errors


def _contract_sha_at_revision(chain, revision):
    anchors = [entry for entry in chain
               if isinstance(revision, int) and
               isinstance(entry.get("queue_revision"), int) and
               entry.get("queue_revision") <= revision]
    return anchors[-1].get("contract_sha256") if anchors else None


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


class _Catalog(dict):
    """The hot receipt catalog plus the sealed-receipt projection index.

    The hot map keeps ``receipt_id -> (relative_path, receipt)`` exactly as
    before.  ``cold`` carries the K12/07 sealed index --
    ``receipt_id -> thin projection`` -- so any consumer holding the catalog
    can resolve sealed existence without a second parameter threading
    through every historical-validation signature.
    """

    __slots__ = ("cold", "root", "_sealed_segments", "_sealed_bodies")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cold = {}
        self.root = None
        self._sealed_segments = {}
        self._sealed_bodies = {}

    def resolve_sealed(self, receipt_id):
        """Return one sealed body, re-proving its bytes at the read.

        This is a sealed branch, not a hole in sealing.  Existence and
        identity consumers are served by the projection through
        :func:`_require_receipt` and never come here; a consumer that must
        replay a *body* -- today the Standards-revalidation consumption
        replay, whose consumed keys live in ``revalidation_bindings`` and
        whose retraction test reads ``invalidated_by``, neither of which a
        projection carries -- has exactly two honest options under K12/07,
        an explicit sealed branch or failing closed.  Silently skipping an
        unresolvable reference is the third option, and taking it is what
        reopened bindings a Queue transition had already discharged.

        What sealing buys out is deserializing *every* sealed body on the
        hot path (1.33s of the measured 1.75s).  This resolves one body per
        asking consumer, lazily and memoized, from a segment whose bytes
        ``_cold_verified_records`` has already re-hashed against the
        manifest this run.  The line is re-proved against the projection's
        own ``record_sha256`` here anyway: this returns evidence or it
        returns nothing, and it does not inherit trust from the caller.
        """
        if receipt_id in self._sealed_bodies:
            return self._sealed_bodies[receipt_id]
        self._sealed_bodies[receipt_id] = None
        row = self.cold.get(receipt_id)
        if not isinstance(row, dict) or not isinstance(self.root, str):
            return None
        segment = row.get("segment")
        line_number = row.get("line")
        if not _nonempty_string(segment) or not isinstance(line_number, int) \
                or isinstance(line_number, bool) or line_number < 1:
            return None
        if segment not in self._sealed_segments:
            try:
                with open(os.path.join(self.root, segment), "rb") as handle:
                    self._sealed_segments[segment] = \
                        handle.read().splitlines(keepends=True)
            except OSError:
                self._sealed_segments[segment] = []
        lines = self._sealed_segments[segment]
        if line_number > len(lines):
            return None
        raw = lines[line_number - 1]
        if kblib.sha256_bytes(raw) != row.get("record_sha256"):
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            return None
        if not isinstance(body, dict) or body.get("receipt_id") != receipt_id:
            return None
        self._sealed_bodies[receipt_id] = (segment, body)
        return self._sealed_bodies[receipt_id]

    def resolve(self, receipt_id):
        """Resolve hot first, then through the sealed branch above."""
        entry = self.get(receipt_id)
        if entry is not None:
            return entry
        return self.resolve_sealed(receipt_id)


def _receipt_catalog(root, errors):
    """Load the repository receipt register into one collision-checked map.

    Queue references use receipt IDs rather than file paths.  The canonical
    receipt namespace is therefore scanned recursively; malformed JSONL,
    duplicate IDs, symlinks, and hard-linked files make the evidence set
    unreliable instead of being silently skipped.  The one deliberate
    exception is the ``cold/`` namespace: sealed segments and born-cold
    close evidence are never deserialized on the hot path -- that is the
    entire point of sealing -- and their integrity is carried by the cold
    manifest instead (K12/07).
    """
    relative_dir = ".cambium/receipts"
    receipt_dir = os.path.join(root, relative_dir)
    catalog = _Catalog()
    catalog.root = root
    if not os.path.exists(receipt_dir):
        return catalog
    if not os.path.isdir(receipt_dir) or os.path.islink(receipt_dir):
        errors.append("%s must be a real directory" % relative_dir)
        return catalog
    for dirpath, dirnames, filenames in os.walk(receipt_dir, topdown=True,
                                                followlinks=False):
        safe_dirs = []
        for name in sorted(dirnames):
            full = os.path.join(dirpath, name)
            if dirpath == receipt_dir and name == "cold":
                # The cold namespace is loaded by _cold_receipt_store from
                # its manifest and index, never by this recursive scan.
                continue
            if os.path.islink(full):
                errors.append("receipt namespace contains symlink directory %s" %
                              os.path.relpath(full, root))
            else:
                safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in sorted(filenames):
            if not name.endswith(".jsonl"):
                continue
            full = os.path.join(dirpath, name)
            relative = os.path.relpath(full, root)
            try:
                stat_result = os.lstat(full)
            except OSError as exc:
                errors.append("cannot stat receipt register %s: %s" %
                              (relative, exc))
                continue
            if os.path.islink(full) or not os.path.isfile(full):
                errors.append("receipt register is not a regular file: %s" % relative)
                continue
            if stat_result.st_nlink != 1:
                errors.append("receipt register must not be hard-linked: %s" % relative)
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except (OSError, UnicodeError) as exc:
                errors.append("cannot read receipt register %s: %s" %
                              (relative, exc))
                continue
            for line_number, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    receipt = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append("malformed receipt %s:%d: %s" %
                                  (relative, line_number, exc))
                    continue
                if not isinstance(receipt, dict):
                    errors.append("receipt %s:%d must be a JSON object" %
                                  (relative, line_number))
                    continue
                receipt_id = receipt.get("receipt_id")
                if not _nonempty_string(receipt_id):
                    errors.append("receipt %s:%d has no receipt_id" %
                                  (relative, line_number))
                    continue
                if receipt_id in catalog:
                    errors.append("duplicate receipt_id %s in %s and %s" %
                                  (receipt_id, catalog[receipt_id][0], relative))
                    continue
                catalog[receipt_id] = (relative, receipt)
    return catalog


def _cold_register_lines(path, label, errors):
    """Read one append-only cold register as exact lines, or None."""
    try:
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
    except (OSError, UnicodeError) as exc:
        errors.append("cannot read %s: %s" % (label, exc))
        return None
    if content and not content.endswith("\n"):
        errors.append("%s does not end with a newline; a truncated append "
                      "leaves the cold chain unprovable (K12/07 fail-closed)"
                      % label)
        return None
    return content.splitlines()


def _cold_group_sha256(lines):
    """Hash one seal's contiguous register rows exactly as written."""
    payload = "".join(line + "\n" for line in lines)
    return kblib.sha256_bytes(payload.encode("utf-8"))


def _cold_journal_errors(root, errors):
    """Every seal transaction must have reached its ``complete`` row.

    The journal is what makes an interrupted seal loud.  ``begin`` lands
    before the first segment byte and ``complete`` lands after the hot
    rewrites, so an unmatched ``begin`` means a writer died mid-transaction
    and the operator must reconcile it against the recorded fingerprints
    rather than let a half-sealed archive validate.
    """
    journal_path = os.path.join(root, kblib.RECEIPT_COLD_JOURNAL_PATH)
    if not os.path.exists(journal_path):
        return
    if not os.path.isfile(journal_path) or os.path.islink(journal_path):
        errors.append("cold journal must be a regular file")
        return
    lines = _cold_register_lines(journal_path, "cold journal", errors)
    if lines is None:
        return
    open_seals = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append("malformed cold journal line %d: %s" %
                          (line_number, exc))
            continue
        if not isinstance(entry, dict):
            errors.append("cold journal line %d must be a JSON object" %
                          line_number)
            continue
        phase = entry.get("phase")
        seal_id = entry.get("seal_receipt")
        if phase not in ("begin", "complete") or not _nonempty_string(seal_id):
            errors.append("cold journal line %d must record phase "
                          "begin/complete for one seal_receipt" % line_number)
            continue
        if phase == "begin":
            if seal_id in open_seals:
                errors.append("cold journal opens seal %s twice" % seal_id)
            open_seals[seal_id] = line_number
        else:
            open_seals.pop(seal_id, None)
    for seal_id, line_number in sorted(open_seals.items(),
                                       key=lambda pair: pair[1]):
        errors.append(
            "cold journal seal %s began at line %d and never completed; an "
            "interrupted seal must be reconciled against the journal's "
            "recorded fingerprints before the runtime validates again "
            "(K12/07 fail-closed)" % (seal_id, line_number))


def _cold_register_rows(lines, label, errors):
    """Parse one cold register into rows plus per-seal raw-line groups.

    Runs before any content check, because which rows count as evidence is
    decided by the seal binding and not by the rows themselves.
    """
    rows = []
    groups = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append("malformed %s line %d: %s" %
                          (label, line_number, exc))
            continue
        if not isinstance(entry, dict):
            errors.append("%s line %d must be a JSON object" %
                          (label, line_number))
            continue
        seal_id = entry.get("seal_receipt")
        if not _nonempty_string(seal_id):
            errors.append("%s line %d does not name the seal receipt that "
                          "wrote it; an unattributed cold row has no root of "
                          "trust (K12/07 fail-closed)" % (label, line_number))
            continue
        groups.setdefault(seal_id, []).append(line)
        rows.append((line_number, seal_id, entry))
    return rows, groups


def _cold_path_within_root(root, relative, errors):
    """Reject a cold path that leaves the repository by any component.

    Checking only the final component is not enough: a symlinked
    intermediate directory -- ``cold/segments`` pointed somewhere else, or
    ``cold`` itself -- moves the whole archive outside the repository while
    every per-file check still passes, and the sealed bytes then live
    somewhere the repository snapshot does not cover.

    This is containment detection for an ordinary mistake or a stale
    working copy, evaluated once per run.  It is not a defence against a
    party who can change the filesystem between the check and its use;
    that boundary is stated in K12/07 and the remaining hardening is
    registered in ROADMAP.md.
    """
    root_real = os.path.realpath(root)
    current = root_real
    for part in relative.split("/"):
        if part in ("", ".", ".."):
            errors.append("cold path %r is not a plain repository path" %
                          relative)
            return False
        current = os.path.join(current, part)
        if os.path.islink(current):
            errors.append("cold path %s traverses symlink %s; sealed evidence "
                          "must live inside the repository it is evidence "
                          "for (K12/07 fail-closed)" %
                          (relative, os.path.relpath(current, root_real)))
            return False
    resolved = os.path.realpath(os.path.join(root_real, relative))
    if resolved != current or not resolved.startswith(root_real + os.sep):
        errors.append("cold path %s resolves outside the repository "
                      "(K12/07 fail-closed)" % relative)
        return False
    return True


def _cold_namespace_errors(root, errors):
    """The cold namespace itself must be a real directory inside the root."""
    for relative in (kblib.RECEIPT_COLD_PREFIX,
                     kblib.RECEIPT_COLD_SEGMENT_PREFIX,
                     kblib.RECEIPT_COLD_EVIDENCE_PREFIX):
        full = os.path.join(root, relative)
        if not os.path.exists(full) and not os.path.islink(full):
            continue
        if not _cold_path_within_root(root, relative, errors):
            return False
        if not os.path.isdir(full):
            errors.append("cold path %s must be a directory" % relative)
            return False
    return True


def _cold_manifest_entries(root, rows, bound, errors):
    """Prove each bound manifest row's segment presence and shape."""
    entries = {}
    named = set()
    for line_number, seal_id, entry in rows:
        if seal_id not in bound:
            continue
        segment = entry.get("segment")
        if (not _nonempty_string(segment) or
                not (segment.startswith(
                    kblib.RECEIPT_COLD_SEGMENT_PREFIX + "/") or
                     segment.startswith(
                    kblib.RECEIPT_COLD_EVIDENCE_PREFIX + "/")) or
                not segment.endswith(".jsonl") or "/../" in segment):
            errors.append("cold manifest line %d has invalid segment path %r" %
                          (line_number, segment))
            continue
        named.add(segment)
        if segment in entries:
            errors.append("cold manifest repeats segment %s" % segment)
            continue
        sha_value = entry.get("segment_sha256")
        size_value = entry.get("segment_bytes")
        records = entry.get("records")
        if not isinstance(sha_value, str) or not SHA256_RE.fullmatch(sha_value):
            errors.append("cold manifest segment %s has invalid "
                          "segment_sha256" % segment)
            continue
        if (not isinstance(size_value, int) or isinstance(size_value, bool) or
                size_value < 0):
            errors.append("cold manifest segment %s has invalid "
                          "segment_bytes" % segment)
            continue
        if (not isinstance(records, int) or isinstance(records, bool) or
                records < 0):
            errors.append("cold manifest segment %s has invalid records" %
                          segment)
            continue
        if not _cold_path_within_root(root, segment, errors):
            continue
        segment_path = os.path.join(root, segment)
        try:
            descriptor = os.lstat(segment_path)
        except OSError:
            errors.append("cold segment %s is missing; sealed evidence "
                          "must stay resolvable (K12/07 fail-closed)" %
                          segment)
            continue
        if os.path.islink(segment_path) or not stat.S_ISREG(descriptor.st_mode):
            errors.append("cold segment %s must be a regular file" % segment)
            continue
        if descriptor.st_nlink != 1:
            # Detection at validation time, not prevention: a second name
            # for sealed bytes is a second writer for them, and this run
            # refuses to vouch for the segment.  It does not stop a party
            # who can create links from doing so between runs.
            errors.append("cold segment %s has %d hard links; a second name "
                          "for sealed bytes is a second writer for them "
                          "(K12/07 fail-closed)" %
                          (segment, descriptor.st_nlink))
            continue
        if descriptor.st_size != size_value:
            errors.append("cold segment %s is %d bytes on disk but the "
                          "manifest sealed %d; sealed bytes may not drift "
                          "(K12/07 fail-closed)" %
                          (segment, descriptor.st_size, size_value))
            continue
        entries[segment] = entry
    return entries, named


def _cold_index_rows(rows, entries, bound, catalog, errors):
    """Admit bound projections and bind each to a manifested segment."""
    index = {}
    by_segment = {}
    for line_number, seal_id, entry in rows:
        if seal_id not in bound:
            continue
        receipt_id = entry.get("receipt_id")
        if not _nonempty_string(receipt_id):
            errors.append("cold index line %d has no receipt_id" % line_number)
            continue
        if receipt_id in catalog:
            errors.append("sealed receipt_id %s still present in hot "
                          "register %s; a sealed row must leave the hot "
                          "file it was sealed from" %
                          (receipt_id, catalog[receipt_id][0]))
            continue
        if receipt_id in index:
            errors.append("cold index repeats receipt_id %s" % receipt_id)
            continue
        segment = entry.get("segment")
        if segment not in entries:
            errors.append("cold index receipt %s names unknown segment %r" %
                          (receipt_id, segment))
            continue
        record_sha = entry.get("record_sha256")
        if (not isinstance(record_sha, str) or
                not SHA256_RE.fullmatch(record_sha)):
            errors.append("cold index receipt %s has invalid record_sha256" %
                          receipt_id)
            continue
        record_line = entry.get("line")
        if (not isinstance(record_line, int) or isinstance(record_line, bool)
                or record_line < 1 or
                record_line > entries[segment].get("records", 0)):
            errors.append("cold index receipt %s names line %r, which is "
                          "outside segment %s" %
                          (receipt_id, record_line, segment))
            continue
        index[receipt_id] = entry
        by_segment.setdefault(segment, []).append(entry)
    return index, by_segment


def _cold_verified_records(root, entries, by_segment, errors):
    """Re-hash every sealed segment and return the projections it proves.

    This is the per-run cost sealing does not buy out.  Presence and size
    prove nothing about content: a same-length edit to a sealed verdict
    would pass a size check silently, and the projections that consumers
    read are derived from these bytes.  Measured on a 65 MB adopter
    archive this whole pass costs 0.42s; what sealing actually retires is
    re-deserializing the bodies, a further 1.33s on the same archive.

    The return value is what makes the check load-bearing rather than
    advisory.  Reporting a hash failure while still handing the projection
    to consumers would leave the run resolving a receipt it has just proved
    it cannot vouch for, so an unproven projection is withheld, not warned
    about.
    """
    verified = set()
    for segment in sorted(entries):
        entry = entries[segment]
        try:
            with open(os.path.join(root, segment), "rb") as handle:
                payload = handle.read()
        except OSError as exc:
            errors.append("cold segment %s became unreadable: %s" %
                          (segment, exc))
            continue
        if kblib.sha256_bytes(payload) != entry["segment_sha256"]:
            errors.append("cold segment %s does not match the hash the "
                          "manifest sealed; sealed bytes may not change "
                          "(K12/07 fail-closed)" % segment)
            continue
        if payload.count(b"\n") != entry["records"]:
            errors.append("cold segment %s holds %d records but the manifest "
                          "sealed %d" %
                          (segment, payload.count(b"\n"), entry["records"]))
            continue
        rows = by_segment.get(segment)
        if not rows:
            continue
        try:
            lines = payload.decode("utf-8").splitlines(keepends=True)
        except UnicodeError as exc:
            errors.append("cold segment %s is not valid UTF-8: %s" %
                          (segment, exc))
            continue
        for row in rows:
            raw = lines[row["line"] - 1]
            if kblib.sha256_bytes(raw.encode("utf-8")) != row["record_sha256"]:
                errors.append(
                    "cold index receipt %s does not hash to the sealed record "
                    "at %s line %d; a projection that no longer names its own "
                    "record is an assertion, not evidence (K12/07 "
                    "fail-closed)" % (row["receipt_id"], segment, row["line"]))
                continue
            verified.add(row["receipt_id"])
    return verified


def _cold_orphan_segment_errors(root, named, errors):
    """A segment file no manifest row names is an interrupted seal.

    Only ``segments/`` is swept.  Born-cold close evidence is written by
    ``check_batch_close`` at close time and adopted into the manifest by
    the next seal, so an unmanifested evidence file is a normal interval
    state -- its integrity is bound by the close attestation that names
    its path, bytes and hash.
    """
    segment_dir = os.path.join(root, kblib.RECEIPT_COLD_SEGMENT_PREFIX)
    if not os.path.isdir(segment_dir):
        return
    for name in sorted(os.listdir(segment_dir)):
        relative = "%s/%s" % (kblib.RECEIPT_COLD_SEGMENT_PREFIX, name)
        if relative not in named:
            errors.append("cold segment file %s is in no manifest row; an "
                          "unreferenced segment is an interrupted seal, not "
                          "spare evidence (K12/07 fail-closed)" % relative)


def _cold_bound_seals(catalog, manifest_groups, index_groups, errors):
    """Bind both cold registers to the seal receipt that wrote them.

    Manifest and index are ordinary editable files with no producer of
    their own; the seal receipt is a receipt, it never seals, and it
    records the exact bytes of the rows one transaction appended.  That
    makes the cold chain terminate where every other claim in this runtime
    terminates -- in the hot receipt register -- instead of in a side table
    that anyone may rewrite.

    Returns the seal IDs whose rows are proven.  Rows of an unproven seal
    are not merely reported: they never enter the catalog, so a forged
    projection cannot resolve for a consumer inside the same run that
    rejects it.
    """
    bound = set()
    for seal_id in sorted(set(manifest_groups) | set(index_groups)):
        entry = catalog.get(seal_id)
        if entry is None:
            errors.append("cold registers name seal receipt %s, which is "
                          "absent from the hot catalog; the cold chain's root "
                          "of trust is its seal receipt and seal receipts "
                          "never seal (K12/07 fail-closed)" % seal_id)
            continue
        receipt = entry[1]
        if (receipt.get("tool") != SEAL_TOOL or
                receipt.get("check") != "receipt_seal" or
                receipt.get("result") != "pass" or
                receipt.get("invalidated_by") is not None):
            errors.append("cold registers name %s as a seal receipt, but that "
                          "receipt is not a passing %s receipt_seal" %
                          (seal_id, SEAL_TOOL))
            continue
        if receipt.get("tool_version") not in SUPPORTED_SEAL_TOOL_VERSIONS:
            errors.append(
                "seal receipt %s was produced by %s %r, which is not a "
                "supported sealing protocol; a cold archive is only as "
                "trustworthy as the writer that made it (K12/07 fail-closed)"
                % (seal_id, SEAL_TOOL, receipt.get("tool_version")))
            continue
        proven = True
        for kind, groups, field in (
                ("manifest", manifest_groups, "manifest_rows_sha256"),
                ("index", index_groups, "index_rows_sha256")):
            recorded = receipt.get(field)
            actual = _cold_group_sha256(groups.get(seal_id, []))
            if recorded != actual:
                proven = False
                errors.append(
                    "cold %s rows attributed to seal %s hash to %s but the "
                    "seal receipt recorded %r; a cold register is evidence "
                    "only while its seal receipt still binds its bytes "
                    "(K12/07 fail-closed)" % (kind, seal_id, actual, recorded))
        if proven:
            bound.add(seal_id)
    seen = set(manifest_groups) | set(index_groups)
    for receipt_id, (_relative, receipt) in catalog.items():
        if (receipt.get("tool") != SEAL_TOOL or
                receipt.get("check") != "receipt_seal" or
                receipt.get("result") != "pass" or
                receipt.get("invalidated_by") is not None):
            continue
        if receipt_id not in seen:
            errors.append("seal receipt %s recorded a seal whose manifest and "
                          "index rows are both gone; sealed rows are "
                          "append-only (K12/07 fail-closed)" % receipt_id)
    return bound


def _cold_receipt_store(root, errors, catalog):
    """Load and fully verify the K12/07 cold chain, fail-closed.

    Sealing moves parse cost off the hot path.  It does not move integrity
    off it.  Every consistency run re-reads every sealed segment and proves
    its bytes against the manifest hash, proves each projection against the
    exact sealed line it names, proves both registers against the seal
    receipt that wrote them, refuses an unreferenced segment or an
    unfinished seal transaction, and refuses a sealed ``receipt_id`` that
    still has a hot twin.  Absence of the whole namespace means nothing is
    sealed and is not an error.
    """
    store = {"manifest": [], "index": {}, "seals": []}
    manifest_path = os.path.join(root, kblib.RECEIPT_COLD_MANIFEST_PATH)
    index_path = os.path.join(root, kblib.RECEIPT_COLD_INDEX_PATH)
    segment_dir = os.path.join(root, kblib.RECEIPT_COLD_SEGMENT_PREFIX)
    # The journal is checked before anything else, and unconditionally: a
    # seal that died between its begin row and its first segment byte
    # leaves no manifest, no index and no segment at all, and that is
    # exactly the interruption a namespace-presence short-circuit would
    # have declared clean.
    _cold_journal_errors(root, errors)
    if not _cold_namespace_errors(root, errors):
        catalog.cold = store["index"]
        return store
    if (not os.path.exists(manifest_path) and
            not os.path.exists(index_path) and
            not os.path.isdir(segment_dir)):
        catalog.cold = store["index"]
        return store
    for label, path in (("cold manifest", manifest_path),
                        ("cold index", index_path)):
        if not os.path.isfile(path) or os.path.islink(path):
            errors.append("%s must exist as a regular file once the cold "
                          "namespace exists" % label)
            catalog.cold = store["index"]
            return store
    manifest_lines = _cold_register_lines(manifest_path, "cold manifest",
                                          errors)
    index_lines = _cold_register_lines(index_path, "cold index", errors)
    if manifest_lines is None or index_lines is None:
        catalog.cold = store["index"]
        return store
    manifest_rows, manifest_groups = _cold_register_rows(
        manifest_lines, "cold manifest", errors)
    index_rows, index_groups = _cold_register_rows(
        index_lines, "cold index", errors)
    bound = _cold_bound_seals(catalog, manifest_groups, index_groups, errors)
    entries, named = _cold_manifest_entries(root, manifest_rows, bound, errors)
    index, by_segment = _cold_index_rows(
        index_rows, entries, bound, catalog, errors)
    verified = _cold_verified_records(root, entries, by_segment, errors)
    _cold_orphan_segment_errors(root, named, errors)
    store["manifest"] = [entries[segment] for segment in sorted(entries)]
    store["index"] = {receipt_id: row for receipt_id, row in index.items()
                      if receipt_id in verified}
    store["seals"] = sorted(bound)
    catalog.cold = store["index"]
    return store


def _current_item_transition_evidence(item, catalog):
    """Return hold-clear evidence in the current attempt, not all history."""
    transition_ids = item.get("transition_receipts")
    if not isinstance(transition_ids, list):
        return set()
    history = item.get("invalidation_history")
    last_rollback = (history[-1].get("transition_receipt")
                     if isinstance(history, list) and history and
                     isinstance(history[-1], dict) else None)
    start = 0
    if last_rollback in transition_ids:
        start = transition_ids.index(last_rollback) + 1
    evidence = set()
    window = set(transition_ids[start:])
    for transition_id in transition_ids[start:]:
        entry = catalog.get(transition_id)
        transition = entry[1] if entry is not None else None
        if not isinstance(transition, dict):
            continue
        revalidation = transition.get("standards_revalidation_receipt")
        if _nonempty_string(revalidation):
            evidence.add(revalidation)
    # A discharge is recognized by the replayed hold machine, not by the
    # adjacent `revalidation-required -> none` edge: the clear may legitimately
    # be taken from a hold the item moved to while the obligation stood.  The
    # machine is replayed over the whole history and the result filtered to
    # the current attempt, because the rollback that opened this attempt's
    # obligation sits just before the window.
    for transition in item_revalidation_discharges(item, catalog):
        if (transition.get("receipt_id") in window and
                transition.get("before_state") == transition.get("after_state")
                and _nonempty_string(transition.get("evidence_receipt"))):
            evidence.add(transition["evidence_receipt"])
    return evidence


def _clears_revalidation_hold(transition):
    """Return whether one transition discharges a `revalidation-required` hold.

    The discharge is the evidence, not the edge.  ``update_queue.py`` records
    whichever receipt authorized the clear -- the Standards revalidation
    aggregate when adoption bindings are outstanding, otherwise the bound
    Queue-consistency gate -- in ``evidence_receipt``, and additionally names
    the aggregate in ``standards_revalidation_receipt``.  A transition that
    lands on ``none`` carrying neither has proved nothing, whatever hold it
    came from.
    """
    if not isinstance(transition, dict):
        return False
    if transition.get("after_hold_state") != "none":
        return False
    return (_nonempty_string(transition.get("evidence_receipt")) or
            _nonempty_string(transition.get("standards_revalidation_receipt")))


def walk_revalidation_hold(transitions):
    """Replay the hold sub-state machine over one item's ordered history.

    Returns ``(outstanding, discharges)``: whether a ``revalidation-required``
    hold is still owed, and the transitions that actually retired one.

    ``hold_state`` is a sub-state machine, not a set of independent flags, so
    the obligation it records cannot be read off the current value alone.
    Entering ``revalidation-required`` opens the obligation; only a transition
    that lands on ``none`` with its discharge evidence retires it.  Moving to
    any other hold -- ``paused``, ``blocked``, ``confirmation-required`` --
    defers the obligation and never settles it, so
    ``revalidation-required -> paused -> none`` clears exactly as much as the
    direct ``revalidation-required -> none`` edge it routes around, which is
    nothing.

    Replaying the whole ordered list rather than reading the adjacent edge is
    the point: the bypass is only visible across an arbitrary number of
    intermediate holds, and a hand-edited ``hold_state`` that never recorded
    a clearing transition stays outstanding here too.
    """
    outstanding = False
    discharges = []
    for transition in transitions or []:
        if not isinstance(transition, dict):
            continue
        if transition.get("after_hold_state") == "revalidation-required":
            outstanding = True
        elif outstanding and _clears_revalidation_hold(transition):
            outstanding = False
            discharges.append(transition)
    return outstanding, discharges


def undischarged_revalidation_hold(transitions):
    """Return whether a `revalidation-required` hold is still outstanding."""
    return walk_revalidation_hold(transitions)[0]


def _ordered_item_transitions(item, catalog):
    """Return the item's transition receipts, in order, that resolve."""
    transition_ids = item.get("transition_receipts")
    if not isinstance(transition_ids, list):
        return []
    transitions = []
    for transition_id in transition_ids:
        entry = catalog.get(transition_id) if _nonempty_string(
            transition_id) else None
        if entry is not None and isinstance(entry[1], dict):
            transitions.append(entry[1])
    return transitions


def item_undischarged_revalidation_hold(item, catalog):
    """Resolve :func:`undischarged_revalidation_hold` from receipt IDs."""
    return undischarged_revalidation_hold(
        _ordered_item_transitions(item, catalog))


def item_revalidation_discharges(item, catalog):
    """Return the transitions that retired a `revalidation-required` hold."""
    return walk_revalidation_hold(
        _ordered_item_transitions(item, catalog))[1]


def invalidated_receipt_consumers(root, queue, catalog):
    """Map current non-terminal receipt references back to Queue batches."""
    consumers = {}

    def add(batch_id, receipt_id, source):
        if not _nonempty_string(receipt_id):
            return
        consumers.setdefault(receipt_id, []).append({
            "batch_id": batch_id, "source": source,
        })

    for item in queue.get("required_queue", []) if isinstance(
            queue.get("required_queue"), list) else []:
        if not isinstance(item, dict) or item.get("state") in TERMINAL_STATES:
            continue
        batch_id = item.get("id")
        for field in ("activation_receipt", "confirmation_receipt"):
            add(batch_id, item.get(field), "Queue.%s" % field)
        for receipt_id in _current_item_transition_evidence(item, catalog):
            add(batch_id, receipt_id, "Queue.current-transition-evidence")
        if item.get("state") == "merge-ready":
            for receipt_id in item.get("batch_receipts") or []:
                add(batch_id, receipt_id, "Queue.batch_receipts")
            for field in ("delta_apply_receipt", "queue_consistency_receipt",
                          "close_gate_receipt"):
                add(batch_id, item.get(field), "Queue.%s" % field)
        if item.get("state") in ("open", "merge-ready"):
            relative = item.get("delta_path")
            if not _nonempty_string(relative):
                relative = ".cambium/deltas/%s.yaml" % batch_id
            try:
                path = kblib.managed_repository_path(
                    root, relative, ".cambium/deltas", suffixes=(".yaml",),
                    must_exist=True)
                delta = kblib.load_yaml_file(path)
                for receipt_id in delta_gate_receipt_ids(delta):
                    add(batch_id, receipt_id, "Delta.gate_receipts")
            except (OSError, ValueError, kblib.YamlSubsetError):
                # The normal Delta validator reports the underlying defect.
                pass
    return consumers


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


def _read_set_load_closure(root, selected_paths,
                           selected_profile_manifest=None,
                           selected_profile_route_ids=None):
    """Resolve Read Sets and non-Read-Set targets from selected boundaries.

    Boundary references to another Read Set select that route too, so traversal
    continues until no new Read Set remains. ``visited`` makes cycles benign.
    A kernel Read Set proves both its canonical namespace and ``type:
    read-set``; a profile supplemental Read Set proves ``type:
    profile-read-set`` in its own frontmatter. Every other boundary target is
    a loaded module, including ordinary indexes inside ``kernel/Read Sets``.

    Every selected or boundary-referenced Read Set is decoded as UTF-8 and
    classified from its own frontmatter.  Kernel and profile namespaces are
    not interchangeable: ``read-set`` belongs under ``kernel/Read Sets/``;
    ``profile-read-set`` belongs under the selected profile directory and its
    route ID must be in the selected profile-route list.  Read/decode failures
    and namespace/route mismatches are explicit closure errors rather than a
    reason to silently shrink the load obligation.
    """
    selected = {
        value for value in (selected_paths or []) if _nonempty_string(value)
    }
    read_sets = set()
    invalid_selected = set()
    modules = set()
    pending = []
    visited = set()
    closure_errors = []
    profile_dir = (os.path.dirname(selected_profile_manifest)
                   if _nonempty_string(selected_profile_manifest) else None)
    profile_routes = {
        value for value in (selected_profile_route_ids or [])
        if _nonempty_string(value)
    }

    def read_text(relative):
        try:
            path = kblib.repository_path(
                root, relative, must_exist=True, reject_symlink=True)
            with open(path, encoding="utf-8") as handle:
                return handle.read(), None
        except (OSError, UnicodeError, ValueError) as exc:
            return None, str(exc)

    def frontmatter_fields(text):
        frontmatter = kblib.extract_frontmatter(text or "")
        if frontmatter is None:
            return {}
        try:
            fields = kblib.parse_yaml_subset(frontmatter)
        except (ValueError, kblib.YamlSubsetError):
            return {}
        return fields if isinstance(fields, dict) else {}

    def read_set_role_error(relative, text):
        document_type = kblib.read_set_document_type(text)
        if document_type is None:
            return ("%s does not prove frontmatter type read-set or "
                    "profile-read-set" % relative)
        if document_type == "read-set":
            if not relative.startswith(READ_SET_PATH_PREFIX):
                return ("%s declares type read-set outside the canonical %s "
                        "namespace" % (relative, READ_SET_PATH_PREFIX))
            return None
        if not profile_dir or not (relative == profile_dir or
                                   relative.startswith(profile_dir + "/")):
            return ("%s declares type profile-read-set outside the selected "
                    "profile directory %r" % (relative, profile_dir))
        route_id = frontmatter_fields(text).get("route_id")
        if not _nonempty_string(route_id) or route_id not in profile_routes:
            return ("%s declares profile Read Set route_id %r, which is not "
                    "present in selected_profile_route_ids" %
                    (relative, route_id))
        return None

    for relative in sorted(selected):
        text, read_error = read_text(relative)
        if text is None:
            closure_errors.append(
                "selected Read Set %s is unsafe or unreadable UTF-8: %s" %
                (relative, read_error))
            continue
        role_error = read_set_role_error(relative, text)
        if role_error:
            invalid_selected.add(relative)
            closure_errors.append(role_error)
            continue
        read_sets.add(relative)
        pending.append(relative)

    pending.sort(reverse=True)
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        text, read_error = read_text(relative)
        if text is None:
            closure_errors.append(
                "transitively selected Read Set %s is unsafe or unreadable "
                "UTF-8: %s" % (relative, read_error))
            continue
        for target in kblib.read_set_boundary_targets(text):
            target_text, target_error = read_text(target)
            if target_text is None:
                closure_errors.append(
                    "Read Set boundary target %s is unsafe or unreadable "
                    "UTF-8: %s" % (target, target_error))
                continue
            document_type = (
                kblib.read_set_document_type(target_text)
            )
            if document_type is not None:
                role_error = read_set_role_error(target, target_text)
                if role_error:
                    closure_errors.append(role_error)
                    continue
                if target not in read_sets:
                    read_sets.add(target)
                    pending.append(target)
                continue
            modules.add(target)

    return read_sets, modules, invalid_selected, sorted(set(closure_errors))


def _live_read_set_load_findings(root, contract):
    """Return structural errors and closure gaps of the live Task Contract.

    The two findings are separated because only one of them can be repaired
    from where the checker stands.  A selected Read Set that is unsafe,
    unreadable, or unusable as a traversal root leaves the load declaration
    unresolvable, and no reading of history makes broken bytes resolvable, so
    it stays an error; ``invalid_selected`` is that same class, a path that
    cannot serve as a traversal root, and is reported with it.  A *completeness*
    gap -- a Read Set or a non-Read-Set target the resolved closure names and
    the declaration omits -- is returned separately and is never a runtime
    error.

    The reason is the one the plan-side twin states at ``validate_current``:
    the live contract's five load fields were written by a Standards adoption
    whose plan bytes are sealed into append-only receipts, and
    ``Tools/adopt_standards.py`` -- the only writer that can re-declare them
    for a running task -- refuses to start while ``validate_runtime`` reports
    an error.  Making the gap an error would therefore lock the instance out of
    the one transaction that repairs it, exactly as refusing a sealed
    historical plan would.  K00/15 puts the judgment where a declaration is
    still writable: a plan being admitted.
    """
    if not isinstance(contract, dict):
        return [], []
    selected_values = contract.get("selected_read_sets")
    loaded_values = contract.get("loaded_module_paths")
    if not isinstance(selected_values, list) or not isinstance(
            loaded_values, list):
        return [], []
    selected = set(value for value in selected_values
                   if _nonempty_string(value))
    loaded = set(value for value in loaded_values
                 if _nonempty_string(value))
    read_sets, modules, invalid_selected, closure_errors = \
        _read_set_load_closure(
            root, selected,
            contract.get("selected_profile_manifest"),
            contract.get("selected_profile_route_ids"),
        )
    errors = ["Progress contract Read Set load closure: %s" % error
              for error in closure_errors]
    for target in sorted(invalid_selected):
        if not any(target in error for error in closure_errors):
            errors.append(
                "Progress contract.selected_read_sets path %s cannot be used "
                "as a Read Set traversal root, per %s" %
                (target, READ_SET_BOUNDARY_OWNER_PATH))
    gaps = []
    for target in sorted(read_sets - selected):
        gaps.append(
            "Progress contract.selected_read_sets omits %s, which a loading "
            "boundary of its transitive Read Set closure selects, per %s" %
            (target, READ_SET_BOUNDARY_OWNER_PATH))
    for target in sorted(modules - loaded):
        gaps.append(
            "Progress contract.loaded_module_paths omits %s, which a loading "
            "boundary in the transitive Read Set closure names, per %s" %
            (target, READ_SET_BOUNDARY_OWNER_PATH))
    return errors, gaps


def _standards_adoption_profile_contract_required(producer_tool_version):
    """Return whether this producer era promised a durable typed contract.

    Only an exact semantic version below 1.3 selects the legacy contract.  An
    absent or malformed producer identity fails closed onto the current shape
    instead of becoming a way to erase the new binding.
    """
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_PROFILE_CONTRACT_MIN_VERSION


def _standards_adoption_profile_inputs_required(producer_tool_version):
    """Return whether this producer era promised root input binding.

    Only an exact semantic version below 1.4 selects the legacy contract. An
    absent or malformed producer identity fails closed onto the current shape.
    """
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_PROFILE_INPUT_MIN_VERSION


def _standards_adoption_upstream_required(producer_tool_version):
    """Return whether this producer era promised an upstream identity.

    Only an exact semantic version below 1.5 selects the legacy shape.  An
    absent or malformed producer identity fails closed onto the current
    shape.
    """
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_UPSTREAM_MIN_VERSION


def _standards_adoption_owner_projection_required(producer_tool_version):
    """Return whether this producer era stored projected boundary owners."""
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= \
        STANDARDS_ADOPTION_OWNER_PROJECTION_MIN_VERSION


def _standards_adoption_state_file_required(producer_tool_version):
    """Return whether this era owns adopter identity in the state file."""
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(producer_tool_version),
    )
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= (1, 7, 0)


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


def _writer_locks(root, errors):
    """Inventory cooperating-writer locks without deciding whether stale.

    A lock can mean either a live writer or an interrupted writer.  The
    checker deliberately does not guess which: callers fail closed and expose
    the owner metadata so a later task can reconcile the state first.
    """
    relative_tmp = ".cambium/tmp"
    tmp_dir = os.path.join(root, relative_tmp)
    locks = []
    if not os.path.lexists(tmp_dir):
        # Candidate/preflight trees may contain only canonical state and
        # evidence.  No tmp namespace means there is no cooperating-writer
        # lock to report; initialization remains responsible for creating it
        # in a materialized adopter runtime.
        return locks
    if os.path.islink(tmp_dir) or not os.path.isdir(tmp_dir):
        errors.append("%s must be a real directory" % relative_tmp)
        return locks
    try:
        names = sorted(os.listdir(tmp_dir))
    except OSError as exc:
        errors.append("cannot inventory %s: %s" % (relative_tmp, exc))
        return locks
    for name in names:
        if not name.endswith(".lock"):
            continue
        relative = "%s/%s" % (relative_tmp, name)
        lock_path = os.path.join(tmp_dir, name)
        lock = {"path": relative, "owner": None, "owner_error": None}
        try:
            stat_result = os.lstat(lock_path)
            if os.path.islink(lock_path) or not os.path.isdir(lock_path):
                lock["owner_error"] = "lock is not a real directory"
                locks.append(lock)
                continue
            if stat_result.st_nlink < 2:
                lock["owner_error"] = "lock directory metadata is invalid"
        except OSError as exc:
            lock["owner_error"] = "cannot stat lock: %s" % exc
            locks.append(lock)
            continue
        owner_path = os.path.join(lock_path, "owner.json")
        if not os.path.lexists(owner_path):
            lock["owner_error"] = "owner.json is missing"
            locks.append(lock)
            continue
        try:
            owner_stat = os.lstat(owner_path)
            if (os.path.islink(owner_path) or not os.path.isfile(owner_path) or
                    owner_stat.st_nlink != 1):
                raise ValueError("owner.json must be a regular, singly-linked file")
            with open(owner_path, encoding="utf-8") as fh:
                owner = json.load(fh)
            if not isinstance(owner, dict):
                raise ValueError("owner.json top level must be an object")
            lock["owner"] = owner
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            lock["owner_error"] = str(exc)
        locks.append(lock)
    return locks


def _bind_lock_receipts(writer_locks, catalog):
    """Annotate transaction locks with durable prepare/commit/abort evidence."""
    for lock in writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        transaction_id = (operation.get("transaction_id")
                          if isinstance(operation, dict) else None)
        if not _nonempty_string(transaction_id):
            continue
        matches = []
        for receipt_id, (relative, receipt) in catalog.items():
            if (receipt.get("tool") == "apply_amendment" and
                    receipt.get("transaction_id") == transaction_id and
                    receipt.get("transaction_phase") in
                    ("prepare", "commit", "abort")):
                semantic_errors = []
                phase = receipt.get("transaction_phase")
                expected_result = {
                    "prepare": "candidate",
                    "commit": "pass",
                    "abort": "fail",
                }[phase]
                for field, expected in (
                        ("tool_version", APPLY_AMENDMENT_TOOL_VERSION),
                        ("check", "amendment_transaction"),
                        ("invalidated_by", None),
                        ("result", expected_result)):
                    if receipt.get(field) != expected:
                        semantic_errors.append(field)
                for operation_field, receipt_field in (
                        ("task_id", "task_id"),
                        ("amendment_id", "amendment_id"),
                        ("plan_path", "plan_path"),
                        ("plan_sha256", "plan_sha256"),
                        ("coverage_proposal_path", "coverage_proposal_path"),
                        ("coverage_proposal_sha256",
                         "coverage_proposal_sha256"),
                        ("actor_role", "actor_role"),
                        ("transaction_sequence", "transaction_sequence"),
                        ("previous_transaction_commit_receipt",
                         "previous_transaction_commit_receipt"),
                        ("registration_receipt", "registration_receipt")):
                    if operation.get(operation_field) != receipt.get(receipt_field):
                        semantic_errors.append(operation_field)
                for state_name in ("coverage", "progress", "queue"):
                    before = "before_%s_sha256" % state_name
                    planned = "planned_after_%s_sha256" % state_name
                    after = "after_%s_sha256" % state_name
                    if operation.get(before) != receipt.get(before):
                        semantic_errors.append(before)
                    if operation.get(planned) != receipt.get(after):
                        semantic_errors.append(planned)
                if operation.get("receipt_path") != relative:
                    semantic_errors.append("receipt_path")
                matches.append({
                    "receipt_id": receipt_id,
                    "path": relative,
                    "phase": phase,
                    "result": receipt.get("result"),
                    "semantic_match": not semantic_errors,
                    "semantic_mismatches": sorted(set(semantic_errors)),
                })
        matches.sort(key=lambda entry: (
            {"prepare": 0, "commit": 1, "abort": 2}[entry["phase"]],
            entry["receipt_id"],
        ))
        lock["transaction_receipts"] = matches
        expected_prepare = operation.get("prepare_receipt_id")
        lock["prepare_receipt_matches_owner"] = any(
            entry["phase"] == "prepare" and
            entry["receipt_id"] == expected_prepare and
            entry["semantic_match"] for entry in matches
        )
        phases = {entry["phase"] for entry in matches
                  if entry["semantic_match"]}
        mismatched_phases = {entry["phase"] for entry in matches
                             if not entry["semantic_match"]}
        if "abort" in phases:
            lock["transaction_phase"] = "abort"
        elif "commit" in phases:
            lock["transaction_phase"] = "commit"
        elif ("prepare" in phases and
              not lock["prepare_receipt_matches_owner"]):
            lock["transaction_phase"] = "prepare-receipt-mismatch"
        elif "prepare" in phases:
            lock["transaction_phase"] = "prepare"
        elif mismatched_phases:
            lock["transaction_phase"] = "receipt-semantic-mismatch"
        else:
            lock["transaction_phase"] = "prepare-receipt-missing"


def _operation_fingerprint(operation, names):
    """Return one valid fingerprint from compatible owner-field aliases."""
    provided = [(name, operation.get(name)) for name in names
                if name in operation]
    if not provided:
        return None, None
    invalid = [name for name, value in provided
               if not isinstance(value, str) or not SHA256_RE.fullmatch(value)]
    if invalid:
        return None, "invalid fingerprint field(s): %s" % ", ".join(invalid)
    values = {value for _, value in provided}
    if len(values) != 1:
        return None, "conflicting fingerprint aliases: %s" % ", ".join(
            name for name, _ in provided)
    return provided[0][1], None


def _reconciliation_hint(phases):
    """Describe evidence only; never prescribe automatic lock recovery."""
    available = [entry for entry in phases.values()
                 if entry["phase"] != "unavailable"]
    if not available:
        return ("owner metadata has no comparable state fingerprints; "
                "manual reconciliation is required")
    phase_names = {entry["phase"] for entry in available}
    unavailable = any(entry["phase"] == "unavailable"
                      for entry in phases.values())
    if "other" in phase_names:
        return ("live state differs from recorded before/planned-after "
                "fingerprints; manual reconciliation is required")
    if phase_names == {"before", "planned-after"}:
        return ("live state mixes before and planned-after fingerprints; "
                "a partial write is possible and must be reconciled manually")
    if phase_names == {"planned-after"}:
        qualifier = "available " if unavailable else "all "
        return ("%sstate fingerprints match planned-after bytes; verify the "
                "matching receipt and semantic checks before treating the "
                "operation as complete" % qualifier)
    qualifier = "available " if unavailable else "all "
    return ("%sstate fingerprints match pre-write bytes; verify writer and "
            "receipt evidence before treating the lock as stale" % qualifier)


def _bind_lock_state_phases(writer_locks, live_shas):
    """Compare exact live state bytes with every interrupted writer plan."""
    for lock in writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        phases = {}
        for state_name, field_names in LOCK_STATE_FINGERPRINTS.items():
            live = live_shas.get(state_name)
            before = None
            planned_after = None
            metadata_errors = []
            if isinstance(operation, dict):
                before, error = _operation_fingerprint(
                    operation, field_names["before"])
                if error:
                    metadata_errors.append(error)
                planned_after, error = _operation_fingerprint(
                    operation, field_names["planned_after"])
                if error:
                    metadata_errors.append(error)
            if (not isinstance(live, str) or
                    not SHA256_RE.fullmatch(live) or metadata_errors or
                    (before is None and planned_after is None)):
                phase = "unavailable"
            elif before is not None and live == before:
                # When before and after are byte-identical, use the
                # conservative pre-write interpretation and expose the
                # ambiguity explicitly.
                phase = "before"
            elif planned_after is not None and live == planned_after:
                phase = "planned-after"
            else:
                phase = "other"
            phases[state_name] = {
                "live_sha256": live,
                "before_sha256": before,
                "planned_after_sha256": planned_after,
                "phase": phase,
                "before_after_identical": (
                    before is not None and before == planned_after),
                "metadata_error": "; ".join(metadata_errors) or None,
            }
        lock["state_phases"] = phases
        lock["reconciliation_hint"] = _reconciliation_hint(phases)


def _bind_lock_delta_archives(root, writer_locks):
    """Locate and fingerprint a Delta moved by an interrupted Queue rollback.

    ``merge-ready -> open`` moves the rejected Delta before publishing the
    three canonical state files.  The writer lock therefore has to make that
    fourth filesystem effect independently observable after a hard exit.
    """
    for lock in writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        if not isinstance(operation, dict) or \
                operation.get("tool") != "update_queue":
            continue
        source_relative = operation.get("delta_archive_source")
        archive_relative = operation.get("delta_archive_path")
        expected_sha = operation.get("delta_sha256")
        if source_relative is None and archive_relative is None and \
                expected_sha is None:
            continue
        evidence = {
            "delta_archive_source": source_relative,
            "delta_archive_path": archive_relative,
            "delta_sha256": expected_sha,
            "source_sha256": None,
            "archive_sha256": None,
            "status": "metadata-incomplete",
            "recovery_fact": "archive-state-undetermined",
            "hint": "manual reconciliation is required",
        }
        lock["delta_archive_recovery"] = evidence
        if (not _nonempty_string(source_relative) or
                not _nonempty_string(archive_relative) or
                not isinstance(expected_sha, str) or
                not SHA256_RE.fullmatch(expected_sha)):
            continue
        try:
            source = kblib.managed_repository_path(
                root, source_relative, ".cambium/deltas",
                suffixes=(".yaml",), must_exist=False,
            )
            archive = kblib.managed_repository_path(
                root, archive_relative,
                ".cambium/receipts/invalidated-deltas",
                suffixes=(".yaml",), must_exist=False,
            )
        except (OSError, ValueError) as exc:
            evidence["status"] = "unsafe-path"
            evidence["error"] = str(exc)
            continue

        source_exists = os.path.isfile(source) and not os.path.islink(source)
        archive_exists = os.path.isfile(archive) and not os.path.islink(archive)
        if source_exists:
            evidence["source_sha256"] = kblib.sha256_file(source)
        if archive_exists:
            evidence["archive_sha256"] = kblib.sha256_file(archive)
        if source_exists and archive_exists:
            evidence["status"] = "source-and-archive-present"
        elif not source_exists and not archive_exists:
            evidence["status"] = "source-and-archive-missing"
        elif source_exists:
            evidence["status"] = (
                "source-ready" if evidence["source_sha256"] == expected_sha
                else "source-sha-mismatch"
            )
        else:
            evidence["status"] = (
                "archived" if evidence["archive_sha256"] == expected_sha
                else "archive-sha-mismatch"
            )

        phases = lock.get("state_phases") or {}
        all_state_before = all(
            (phases.get(name) or {}).get("phase") == "before"
            for name in ("coverage", "queue", "progress")
        )
        if all_state_before and evidence["status"] == "archived":
            evidence["recovery_fact"] = "archive-moved-state-before"
            evidence["hint"] = (
                "the Delta bytes match the declared archive while all three "
                "state files remain at their pre-transition fingerprints; "
                "restore the archive to its declared source before retrying"
            )
        elif all_state_before and evidence["status"] == "source-ready":
            evidence["recovery_fact"] = "archive-not-moved-state-before"
            evidence["hint"] = (
                "the Delta remains at its declared source and all three state "
                "files remain at their pre-transition fingerprints"
            )
        elif evidence["status"] in (
                "archive-sha-mismatch", "source-sha-mismatch",
                "source-and-archive-present", "source-and-archive-missing"):
            evidence["recovery_fact"] = "archive-state-conflict"
            evidence["hint"] = (
                "Delta location or bytes conflict with writer-lock metadata; "
                "manual reconciliation is required"
            )


def _bind_generic_lock_receipts(root, writer_locks, catalog):
    """Bind non-Amendment writer intent to its exact declared JSONL receipt."""
    for lock in writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        if not isinstance(operation, dict) or operation.get("tool") not in \
                GENERIC_WRITER_TOOLS:
            continue
        receipt_id = operation.get("receipt_id")
        receipt_path = operation.get("receipt_path")
        evidence = {
            "receipt_id": receipt_id,
            "receipt_path": receipt_path,
            "status": "metadata-incomplete",
            "matching_receipt": False,
            "result": None,
        }
        lock["operation_receipt"] = evidence
        repository_snapshot_errors = []
        if operation.get("tool") == BATCH_CLOSE_TOOL:
            expected_snapshot = operation.get("repository_snapshot_sha256")
            snapshot_binding = {
                "expected_sha256": expected_snapshot,
                "current_sha256": None,
                "status": "metadata-invalid",
                "error": None,
            }
            evidence["repository_snapshot"] = snapshot_binding
            if (not isinstance(expected_snapshot, str) or
                    not SHA256_RE.fullmatch(expected_snapshot)):
                repository_snapshot_errors.append(
                    "repository_snapshot_sha256")
            else:
                try:
                    current_snapshot = kblib.repository_snapshot_sha256(root)
                except (OSError, ValueError) as exc:
                    snapshot_binding["status"] = "unavailable"
                    snapshot_binding["error"] = str(exc)
                    repository_snapshot_errors.append(
                        "current_repository_snapshot_sha256")
                else:
                    snapshot_binding["current_sha256"] = current_snapshot
                    if current_snapshot == expected_snapshot:
                        snapshot_binding["status"] = "matching"
                    else:
                        snapshot_binding["status"] = "changed"
                        repository_snapshot_errors.append(
                            "current_repository_snapshot_sha256")
        if not _nonempty_string(receipt_id) or not _nonempty_string(receipt_path):
            continue
        try:
            declared = kblib.managed_repository_path(
                root, receipt_path, ".cambium/receipts",
                suffixes=(".jsonl",), must_exist=False,
            )
            declared_relative = os.path.relpath(declared, root)
        except (OSError, ValueError) as exc:
            evidence["status"] = "unsafe-path"
            evidence["error"] = str(exc)
            continue
        entry = catalog.get(receipt_id)
        if entry is None:
            evidence["status"] = "absent"
            continue
        actual_relative, receipt = entry
        if actual_relative != declared_relative:
            evidence["status"] = "path-mismatch"
            evidence["actual_path"] = actual_relative
            evidence["result"] = receipt.get("result")
            continue
        semantic_errors = []
        if receipt.get("tool") != operation.get("tool"):
            semantic_errors.append("tool")
        if (_nonempty_string(operation.get("task_id")) and
                receipt.get("task_id") != operation.get("task_id")):
            semantic_errors.append("task_id")
        expected_target = operation.get("target") or operation.get("batch_id")
        if (_nonempty_string(expected_target) and
                receipt.get("target") != expected_target):
            semantic_errors.append("target")
        for operation_field, receipt_fields in (
                ("before_coverage_sha256", ("before_coverage_sha256",)),
                ("planned_after_coverage_sha256", ("after_coverage_sha256",)),
                ("before_required_queue_sha256",
                 ("before_required_queue_sha256", "required_queue_sha256")),
                ("planned_after_required_queue_sha256",
                 ("after_required_queue_sha256", "required_queue_sha256")),
                ("before_progress_sha256", ("before_progress_sha256",)),
                ("planned_after_progress_sha256", ("after_progress_sha256",))):
            expected_value = operation.get(operation_field)
            if expected_value is None:
                continue
            actual_values = [receipt.get(field) for field in receipt_fields
                             if field in receipt]
            if not actual_values or any(value != expected_value
                                        for value in actual_values):
                semantic_errors.append(operation_field)
        if operation.get("tool") == REGISTER_AMENDMENT_TOOL:
            for field, expected_value in (
                    ("tool_version", REGISTER_AMENDMENT_TOOL_VERSION),
                    ("check", "amendment_withdrawal"
                     if operation.get("action") == "withdraw"
                     else "amendment_registration"),
                    ("result", "pass"),
                    ("invalidated_by", None),
                    ("actor_role", "integrator"),
                    ("amendment_id", operation.get("amendment_id")),
                    ("operation", operation.get("amendment_operation"))):
                if receipt.get(field) != expected_value:
                    semantic_errors.append(field)
            if operation.get("registration_receipt") != receipt_id:
                semantic_errors.append("registration_receipt")
        if operation.get("tool") == "apply_delta":
            if receipt.get("check") != "delta_apply":
                semantic_errors.append("check")
            if receipt.get("batch_id") != operation.get("batch_id"):
                semantic_errors.append("batch_id")
            if receipt.get("delta_sha256") != operation.get("delta_sha256"):
                semantic_errors.append("delta_sha256")
        if operation.get("tool") == BATCH_CLOSE_TOOL:
            if receipt.get("tool_version") != operation.get("tool_version"):
                semantic_errors.append("tool_version")
            if receipt.get("check") != "batch_close_gate":
                semantic_errors.append("check")
            if receipt.get("batch_id") != operation.get("batch_id"):
                semantic_errors.append("batch_id")
            if receipt.get("merged_snapshot_sha256") != operation.get(
                    "repository_snapshot_sha256"):
                semantic_errors.append("merged_snapshot_sha256")
            if receipt.get("result") not in ("pass", "fail"):
                semantic_errors.append("result")
            semantic_errors.extend(repository_snapshot_errors)
        if semantic_errors:
            evidence["status"] = "semantic-mismatch"
            evidence["mismatched_fields"] = sorted(set(semantic_errors))
            evidence["result"] = receipt.get("result")
            continue
        evidence["status"] = "matching"
        evidence["matching_receipt"] = True
        evidence["result"] = receipt.get("result")


def accounted_standards_versions(progress, queue=None):
    """Return the Standards versions this instance's own history accounts for.

    A receipt sealed into append-only history carries the producer identity of
    the Standards revision that emitted it.  K00/03 requires a producer's
    ``Tool version`` cell to move in the revision that changes its accept or
    reject set, so honouring that checklist retires the constant every past
    receipt was stamped with -- and no sanctioned transaction may rewrite a
    historical receipt to carry the new one.  Comparing a historical
    ``tool_version`` against today's constant therefore invalidates history for
    having been produced under an older Standards identity, which is precisely
    what K12/10 forbids.

    What is checkable without today's constants is internal consistency: the
    era a receipt claims must be an era this instance actually passed through.
    Each adoption record contributes both ends of the step it recorded, and the
    live Queue/contract identity covers the instance that has adopted nothing
    yet.  ``standards_version`` is the right field to carry this: it is already
    the field that demotes a receipt from current authorization the moment an
    adoption moves it, so it is also the field that states which Standards
    identity produced it.
    """
    versions = set()
    if isinstance(queue, dict) and _nonempty_string(
            queue.get("standards_version")):
        versions.add(queue["standards_version"])
    if not isinstance(progress, dict):
        return versions
    contract = progress.get("contract")
    if isinstance(contract, dict) and _nonempty_string(
            contract.get("standards_version")):
        versions.add(contract["standards_version"])
    records = progress.get("standards_adoptions")
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        for field in ("standards_version_before", "standards_version_after"):
            if _nonempty_string(record.get(field)):
                versions.add(record[field])
    return versions


def _producer_era_errors(receipt, receipt_id, label, accounted):
    """Return errors when a historical receipt claims an unaccounted era.

    This is what replaces a historical receipt's ``tool_version`` comparison
    against the current producer constant.  A receipt claiming a Standards
    version no adoption record and no live identity accounts for is one this
    instance never produced, so the replacement has teeth without freezing
    today's producer versions into the definition of valid history.  A
    current-action predicate keeps comparing the producer tuple exactly; see
    :func:`receipt_matches_gate_id`.

    A receipt that carries no ``standards_version`` claims no era, and absence
    is not an error here.  Demanding the field would repeat the very mistake
    this function removes: it would invalidate every receipt written before the
    identity fields existed, for a reason its producer could not have
    anticipated and no sanctioned transaction can repair.  Per ``kblib``, an
    omitted identity field already behaves as ``null`` against every consumer
    that compares it, so such a receipt is judged by its remaining bindings.
    """
    if not isinstance(receipt, dict):
        return []
    version = receipt.get("standards_version")
    if not _nonempty_string(version) or version in accounted:
        return []
    return ["%s receipt %s claims standards_version=%r, which no Standards "
            "adoption record or live identity of this instance accounts for" %
            (label, receipt_id, version)]


def _terminal_proof_profile_binding_errors(receipt, receipt_id):
    """Validate each current-use binding promised by its proof producer era.

    This is historical replay, not a new authorization decision.  It therefore
    checks only that a receipt retained the canonical fields its own producer
    promised: 1.16 introduced Profile snapshot/typed-contract bindings, and
    1.17 added the root-owned profile-load input and whole-repository snapshot
    bindings. It deliberately does not load today's selected Profile or
    reinterpret an already-consumed proof against changed bytes. The current
    completion transition performs those comparisons in :mod:`update_task`
    before history is sealed.
    """
    if not isinstance(receipt, dict):
        return []
    version = receipt.get("tool_version")
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\."
                         r"(0|[1-9][0-9]*)", str(version))
    if match is None:
        return []
    version_tuple = tuple(int(part) for part in match.groups())
    if version_tuple < PROFILE_BOUND_TERMINAL_PROOF_MIN_VERSION:
        return []
    fields = [
        "profile_snapshot_sha256", "profile_contract_fingerprint",
    ]
    if version_tuple >= PROFILE_INPUT_BOUND_TERMINAL_PROOF_MIN_VERSION:
        fields.append("profile_load_inputs_sha256")
    if version_tuple >= REPOSITORY_BOUND_TERMINAL_PROOF_MIN_VERSION:
        fields.append("repository_snapshot_sha256")
    errors = []
    for field in fields:
        if not SHA256_RE.fullmatch(str(receipt.get(field))):
            errors.append(
                "complete Terminal Proof receipt %s lacks canonical %s "
                "required by check_proof %s" %
                (receipt_id, field, version)
            )
    return errors


def _require_receipt(catalog, receipt_id, label, errors, expected=None):
    """Resolve one receipt and verify common pass/invalidation bindings.

    A sealed receipt (K12/07 cold chain) satisfies an existence-only
    consumer through its thin index projection, which this run has already
    proved against the sealed record's bytes and against the seal receipt
    that wrote it.  A consumer that supplies ``expected`` field bindings
    needs the body, and a sealed body is not re-deserialized on the hot
    path -- that deserialization is the one cost sealing buys out -- so
    that combination fails closed here unless the caller went through an
    explicit sealed branch instead of this resolver.
    """
    if not _nonempty_string(receipt_id):
        errors.append("%s must identify a receipt" % label)
        return None
    entry = catalog.get(receipt_id)
    if entry is None:
        cold = getattr(catalog, "cold", None) or {}
        projection = cold.get(receipt_id)
        if projection is not None:
            if not expected:
                if projection.get("result") != "pass":
                    errors.append("%s references sealed receipt %s whose "
                                  "sealed result is %r, not pass" %
                                  (label, receipt_id,
                                   projection.get("result")))
                return None
            errors.append(
                "%s requires live field revalidation of receipt %s, but "
                "that receipt is sealed (K12/07); a sealed body is "
                "verified at seal time and only its consumers with an "
                "explicit sealed branch may consume it" %
                (label, receipt_id))
            return None
        errors.append("%s references missing receipt %s" % (label, receipt_id))
        return None
    receipt = entry[1]
    common = {"result": "pass", "invalidated_by": None}
    if expected:
        common.update(expected)
    for field, value in common.items():
        if value is ANY_PRODUCER_ERA_VERSION:
            # K12/10 producer-era identity: a sealed historical receipt is
            # never re-judged against the current producer constant.
            if not _nonempty_string(receipt.get(field)):
                errors.append("%s receipt %s has empty %s" %
                              (label, receipt_id, field))
            continue
        if receipt.get(field) != value:
            errors.append("%s receipt %s has %s=%r, expected %r" %
                          (label, receipt_id, field, receipt.get(field), value))
    return receipt


def coverage_reviewed_era_exception(progress, queue, count):
    """Return the contract exception that currently covers ``count``, or None.

    K02/01 offers three dispositions for legacy `reviewed` records, and one
    of them -- carry them under an explicit exception with a stated end --
    had no machine carrier: the declaration lived in a revision's prose, no
    consumer could read it, and the candidate it was meant to answer came
    back every run.  Because activation requires a passing readiness gate,
    choosing the disposition the kernel offers wedged the queue.

    The carrier is the contract's `policy_exceptions` register (K13/02),
    written by the K13/06 Contract Amendment transaction, with
    `coverage.reviewed_era` in the closed policy registry.  Its `limit` is a
    ceiling on how many records may still claim an era they cannot produce,
    which is why the grant cannot hide new ones: the count only legitimately
    falls as batches re-review, and any record beyond the ceiling reports as
    a candidate exactly as before.  The stated end is the ceiling reaching
    the scope's end -- a task-scoped grant dies with the task.

    Returns ``(entry, reason)``: ``entry`` is the covering exception or
    None, and ``reason`` explains a near miss for the operator.
    """
    contract = (progress or {}).get("contract")
    entries = contract.get("policy_exceptions") if isinstance(
        contract, dict) else None
    if not isinstance(entries, list) or not entries:
        return None, None
    _policy, fingerprint, _errors = (
        contract_exception_policy.effective_coverage_policy())
    task_id = (queue or {}).get("task_id")
    stale = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("policy_id") != "coverage.reviewed_era":
            continue
        if entry.get("baseline_policy_fingerprint") != fingerprint:
            # Judged against policy bytes that are no longer the rule.
            stale = True
            continue
        if (entry.get("scope_kind") == "task" and
                entry.get("scope_ref") != task_id):
            continue
        limit = entry.get("limit")
        if isinstance(limit, bool) or not isinstance(limit, int):
            continue
        if count <= limit:
            return entry, None
        return None, (
            "%d record(s) exceed the %d the exception %s bounds" %
            (count, limit, entry.get("decision_id")))
    if stale:
        return None, ("an exception exists but was judged against a "
                      "superseded statement of the rule")
    return None, None


def unsupported_reviewed_records(coverage):
    """Return Coverage paths claiming `reviewed` with no evidence era.

    K02/01: the status carries the era of the evidence that earned it.  A
    record naming no `gate_receipts` is claiming an era it cannot produce, so
    a page reviewed under a superseded Standards version is indistinguishable
    from one reviewed under the current one.  Reported as candidates, never
    errors: in a corpus with legacy records the honest disposition is a
    declared migration, and a hard failure would wedge the instance out of
    the very replan that performs it.
    """
    unsupported = []
    for page in (coverage or {}).get("pages") or []:
        if not isinstance(page, dict):
            continue
        if page.get("authoring_status") != "reviewed":
            continue
        receipts = page.get("gate_receipts")
        if not isinstance(receipts, list) or not any(
                _nonempty_string(value) for value in receipts):
            path = page.get("path")
            if _nonempty_string(path):
                unsupported.append(str(path))
    return sorted(unsupported)


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


def _latest_merge_transition(item, catalog):
    for receipt_id in reversed(item.get("transition_receipts") or []):
        entry = catalog.get(receipt_id)
        receipt = entry[1] if isinstance(entry, tuple) else None
        if (isinstance(receipt, dict) and
                receipt.get("before_state") == "open" and
                receipt.get("after_state") == "merge-ready"):
            return receipt_id, receipt
    return None, None


def substantive_review_errors(result, item):
    """Return the K12/12 evidence gaps for one batch's L-tier manifest pages.

    Substantive correctness review is mandatory for L-tier pages and is
    produced by a procedurally separate context; batch integration requires
    that those receipts have all arrived.  This helper counts them for the
    merge-ready write guard: for every manifest page whose Coverage tier is
    ``L``, the current (adoption-filtered) catalog must hold at least one
    passing, non-invalidated receipt with ``check: substantive_review``
    targeting exactly that page.  S/M tiers are covered by batch spot checks
    and are not counted here.  This is a transition-time guard, not a
    runtime-wide validation: history closed before the guard shipped is not
    re-judged by it.
    """
    errors = []
    coverage = result.get("coverage") or {}
    tiers = {
        page.get("path"): page.get("tier")
        for page in coverage.get("pages") or []
        if isinstance(page, dict) and _nonempty_string(page.get("path"))
    }
    reviewed_targets = set()
    for entry in current_receipt_catalog(result).values():
        receipt = entry[1] if isinstance(entry, tuple) else entry
        if not isinstance(receipt, dict):
            continue
        if (receipt.get("check") == "substantive_review" and
                receipt.get("result") == "pass" and
                receipt.get("invalidated_by") is None and
                _nonempty_string(receipt.get("target"))):
            reviewed_targets.add(receipt.get("target"))
    for object_path in item.get("manifest") or []:
        if tiers.get(object_path) != "L":
            continue
        if object_path not in reviewed_targets:
            errors.append(
                "L-tier manifest page %s has no current passing "
                "substantive_review receipt (K12/12: mandatory for L-tier, "
                "produced by a context other than the author)" % object_path)
    return errors


def activation_phase_delivery_errors(result, item, phase_id, *,
                                     actor_context_id=None):
    """Prove one phase's frozen set reached the context that is acting now.

    Completeness is judged per attempt, never over their union.  One attempt
    has to cover the phase by itself, because the claim being tested is that
    a single reader received the whole thing: two half-deliveries to two
    contexts leave neither able to say it read the Card, and unioning them
    manufactures a reader that never existed.

    Which attempt has to be the covering one is what separates the callers:

    * an actor (a judgment, a governance write) must be covered by the
      attempt derived from its *own* context -- borrowing another context's
      ack chain would prove that somebody else read the Card.  Another
      context's chain sitting in the same history is not itself a fault;
      the actor's own absence is;
    * an integrator checking history at a queue edge is not the actor: it
      passes no ``actor_context_id`` and needs some one attempt to cover
      the phase, whichever context earned it.

    Every ack is already scoped to the current ``card_bundle_sha256``, so a
    complete chain from a superseded bundle -- internally consistent and
    worthless -- never enters the count.  An activation that never bound a
    host context is `prepared`/`degraded` and stays exempt (v3 D7): it may
    proceed, but nothing it produces may claim machine-enforced delivery.
    """
    errors = []
    if not isinstance(item, dict):
        return ["phase delivery check requires one Queue item"]
    catalog = current_receipt_catalog(result)
    entry = catalog.get(item.get("activation_receipt"))
    activation = entry[1] if isinstance(entry, tuple) else entry
    if not isinstance(activation, dict):
        return errors
    if activation.get("activation_protocol") not in \
            card_activation.PHASED_PROTOCOLS:
        # Pre-phase eras owe their own era's obligation, replayed as written.
        return errors
    if activation.get("delivery_assurance") != "host-bound":
        return errors
    context = card_activation.context_from_receipt(activation)
    expected_ids = set(card_activation.phase_piece_ids(context, phase_id))
    if not expected_ids:
        return errors
    record = card_activation.phase_record(context, phase_id) or {}
    part_count = record.get("part_count")
    bundle_sha = activation.get("card_bundle_sha256")
    by_attempt = {}
    for candidate in catalog.values():
        receipt = candidate[1] if isinstance(candidate, tuple) else candidate
        if not isinstance(receipt, dict):
            continue
        if receipt.get("phase_ack_protocol") != \
                card_activation.PHASE_ACK_PROTOCOL:
            continue
        if receipt.get("phase_id") != phase_id:
            continue
        if receipt.get("card_bundle_sha256") != bundle_sha:
            continue
        if receipt.get("result") not in (None, "pass"):
            continue
        if receipt.get("invalidated_by") is not None:
            continue
        earned = by_attempt.setdefault(
            receipt.get("delivery_attempt_id"),
            {"pieces": set(), "parts": set()})
        earned["pieces"].update(
            piece_id for piece_id in receipt.get("phase_piece_ids") or []
            if isinstance(piece_id, str))
        earned["parts"].add(receipt.get("part_index"))

    def _shortfall(earned):
        """Say how one attempt falls short of the phase, or None if it does not."""
        if earned is None:
            return "holds no ack of it at all"
        missing = sorted(expected_ids - earned["pieces"])
        if missing:
            return "covers %d of %d frozen piece(s), missing %s" % (
                len(expected_ids) - len(missing), len(expected_ids),
                ", ".join(missing[:4]) + ("..." if len(missing) > 4 else ""))
        if isinstance(part_count, int) and len(earned["parts"]) != part_count:
            return "acknowledges %d of %d frozen part(s)" % (
                len(earned["parts"]), part_count)
        return None

    if actor_context_id:
        expected_attempt = card_activation.expected_delivery_attempt_id(
            bundle_sha, actor_context_id)
        shortfall = _shortfall(by_attempt.get(expected_attempt))
        if shortfall:
            errors.append(
                "phase %s is not delivered to this actor: attempt %s %s%s" %
                (phase_id, expected_attempt, shortfall,
                 "" if not by_attempt else
                 "; %d other attempt(s) hold acks, and none of them is this "
                 "actor's" % len(
                     [key for key in by_attempt if key != expected_attempt])))
        return errors
    covering = [key for key, earned in by_attempt.items()
                if _shortfall(earned) is None]
    if not covering:
        if not by_attempt:
            errors.append(
                "phase %s is not delivered to this activation: none of its "
                "%d frozen piece(s) has a current ack" %
                (phase_id, len(expected_ids)))
        else:
            errors.append(
                "phase %s is not delivered to this activation: no single "
                "attempt covers it (%s)" %
                (phase_id, "; ".join(
                    "%s %s" % (key, _shortfall(earned))
                    for key, earned in sorted(
                        by_attempt.items(),
                        key=lambda row: str(row[0]))[:2])))
    return errors


CONTROL_PLANE_PREFIXES = ("kernel/", "profiles/", "Tools/")


def batch_touches_control_plane(item):
    """Say whether one batch's own manifest edits the control plane.

    This is the governance predicate, and it is deliberately about the
    objects a batch changes rather than about which tool it runs.  A tool
    name can be avoided -- a file is editable without any writer -- while a
    batch that carries `kernel/`, `profiles/` or `Tools/` in its manifest is
    doing governance whatever it invokes, and it still has to reach
    merge-ready through the one edge no editor can route around.
    """
    if not isinstance(item, dict):
        return False
    for path in item.get("manifest") or []:
        if isinstance(path, str) and path.startswith(CONTROL_PLANE_PREFIXES):
            return True
    return False


def task_phase_delivery_errors(result, phase_id, *, actor_context_id=None):
    """Check one phase across every batch that still carries an activation.

    Some phases are entered by a task-level act rather than a batch one: a
    completion-candidate transition, a Standards governance write.  Those
    acts have no batch of their own, and a phase plan is frozen per batch,
    so the honest scope is every batch currently holding an activation.
    When none does the obligation has no carrier and this returns nothing --
    the gate declines to invent evidence it has no place to look for, which
    is the same reason K13/20 refuses to treat an admission receipt as
    delivery.
    """
    errors = []
    for item in (result.get("queue") or {}).get("required_queue") or []:
        if not isinstance(item, dict):
            continue
        if item.get("state") not in ("open", "merge-ready"):
            continue
        for message in activation_phase_delivery_errors(
                result, item, phase_id, actor_context_id=actor_context_id):
            errors.append("%s: %s" % (item.get("id"), message))
    return errors


def judgment_record_set_sha256(records):
    """Hash the exact actual judgment set the batch-review wrapper binds."""
    identity = sorted(
        (
            {
                "target": row["target"],
                "judgment_item_id": row["judgment_item_id"],
                "receipt_id": row["receipt_id"],
            }
            for row in records
        ),
        key=lambda row: (row["judgment_item_id"], row["target"],
                         row["receipt_id"]),
    )
    return kblib.sha256_bytes(kblib.canonical_json_bytes(identity))


def batch_review_judgment_errors(result, item, wrapper_receipt):
    """Prove the Profile's frozen judgment obligations are exactly answered.

    Expected records come from the authorized Profile's Batch Review
    Requirements expanded over the frozen manifest — the same expansion the
    activation receipt froze at `queued -> open`.  Actual records come from
    the current `profile_batch_judgment` receipts the wrapper binds.  One
    missing, extra, duplicated, drifted, mis-roled, or reused record refuses
    the transition.  A batch activated under the pre-review era carries no
    obligations and must carry no judgment bindings: sealed history keeps
    its own shape.
    """
    errors = []
    item_id = item.get("id")
    catalog = current_receipt_catalog(result)
    activation_entry = catalog.get(item.get("activation_receipt")) if         isinstance(item.get("activation_receipt"), str) else None
    activation = activation_entry[1] if activation_entry else None
    protocol = activation.get("activation_protocol") if isinstance(
        activation, dict) else None
    # A batch whose activation predates delivery receipts entirely — or
    # was activated under v1 — predates the review era.  It owes nothing
    # and must carry nothing; the runtime validator, not this gate, is
    # what guarantees a current-era batch cannot shed its activation
    # receipt to slip into this branch.
    legacy = protocol != card_activation.ACTIVATION_PROTOCOL
    wrapper_fields = (
        "review_requirement_set_sha256", "judgment_receipt_ids",
        "judgment_record_set_sha256")
    if legacy:
        for field in wrapper_fields:
            if field in (wrapper_receipt or {}):
                errors.append(
                    "%s was activated under %s; its batch-review wrapper "
                    "must not carry %s" % (item_id, protocol, field))
        return errors

    view = result.get("_profile_authorized_view") or {}
    contract = view.get("_contract")
    if contract is None or not getattr(contract, "authorized", False):
        errors.append(
            "%s judgment validation requires one authorized typed Profile "
            "contract" % item_id)
        return errors
    try:
        expected = card_activation.expand_batch_review_requirements(
            contract, item)
    except (TypeError, ValueError) as exc:
        errors.append("%s requirement expansion failed: %s" % (item_id, exc))
        return errors
    expected_sha = card_activation.review_requirement_set_sha256(expected)
    if activation.get("review_requirement_set_sha256") != expected_sha:
        errors.append(
            "%s current Profile/manifest expansion no longer matches the "
            "activation-frozen requirement set; the batch must be "
            "reactivated" % item_id)
        return errors
    requirements = {
        row.judgment_item_id: row
        for row in getattr(contract, "batch_review_requirements", ())
    }

    wrapper = wrapper_receipt or {}
    if not expected:
        # A Profile with no requirements owes nothing: an absent binding IS
        # the empty set, so requirement-free adopters keep their exact
        # current wrapper shape.  A wrapper that does carry the fields must
        # still carry them correctly.
        if not any(field in wrapper for field in wrapper_fields):
            return errors
    if wrapper.get("review_requirement_set_sha256") != expected_sha:
        errors.append(
            "%s batch review wrapper must bind "
            "review_requirement_set_sha256=%s" % (item_id, expected_sha))
    bound = wrapper.get("judgment_receipt_ids")
    if not isinstance(bound, list) or not all(
            _nonempty_string(value) for value in bound):
        errors.append(
            "%s batch review wrapper judgment_receipt_ids must be an "
            "explicit string list" % item_id)
        return errors
    if bound != sorted(set(bound)):
        errors.append(
            "%s batch review wrapper judgment_receipt_ids must be sorted "
            "and unique" % item_id)
        return errors

    current_fingerprint = view.get("profile_contract_fingerprint")
    actual = []
    seen = {}
    for receipt_id in bound:
        entry = catalog.get(receipt_id)
        receipt = entry[1] if entry else None
        if not isinstance(receipt, dict):
            errors.append(
                "%s judgment receipt %s is absent from the current catalog" %
                (item_id, receipt_id))
            continue
        label = "%s judgment receipt %s" % (item_id, receipt_id)
        if receipt.get("invalidated_by") is not None:
            errors.append("%s is invalidated" % label)
            continue
        if (receipt.get("tool") != "record_batch_judgment" or
                receipt.get("check") != "profile_batch_judgment" or
                receipt.get("result") != "pass"):
            errors.append("%s is not a passing profile_batch_judgment" %
                          label)
            continue
        if receipt.get("task_id") != result["queue"].get("task_id"):
            errors.append("%s binds a different task" % label)
        if receipt.get("batch_id") != item_id:
            errors.append("%s binds a different batch" % label)
        if receipt.get("opening_transition_receipt") != item.get(
                "activation_receipt"):
            errors.append(
                "%s binds a different activation; a reopened batch redoes "
                "its judgments" % label)
        if receipt.get("review_requirement_set_sha256") != expected_sha:
            errors.append("%s binds a different requirement set" % label)
        if receipt.get("profile_contract_fingerprint") !=                 current_fingerprint:
            errors.append("%s binds a superseded Profile contract" % label)
        target = receipt.get("target")
        judgment_item_id = receipt.get("judgment_item_id")
        requirement = requirements.get(judgment_item_id)
        if requirement is None:
            errors.append("%s names an unregistered Judgment Item" % label)
            continue
        if receipt.get("reviewer_role") !=                 requirement.pass_authority_role_id:
            errors.append(
                "%s reviewer_role %r is not the registered pass authority "
                "%r" % (label, receipt.get("reviewer_role"),
                        requirement.pass_authority_role_id))
        if receipt.get("receipt_schema") != requirement.receipt_schema:
            errors.append("%s carries the wrong receipt schema" % label)
        if requirement.target_selector == "each-manifest-page":
            try:
                _snapshot, semantic_sha = metadata_property_state.                    semantic_page_snapshot(result["root"], target)
            except (OSError, TypeError, UnicodeError, ValueError) as exc:
                errors.append("%s target cannot be snapshotted: %s" %
                              (label, exc))
                semantic_sha = None
            if semantic_sha is not None and receipt.get(
                    "semantic_content_sha256") != semantic_sha:
                errors.append(
                    "%s was judged against different page bytes; the "
                    "changed page must be re-judged" % label)
        key = (target, judgment_item_id)
        if key in seen:
            errors.append(
                "%s duplicates the judgment %s already bound for %r" %
                (label, seen[key], key))
            continue
        seen[key] = receipt_id
        actual.append({
            "target": target,
            "judgment_item_id": judgment_item_id,
            "receipt_id": receipt_id,
        })

    expected_keys = {(row["target"], row["judgment_item_id"])
                     for row in expected}
    actual_keys = set(seen)
    for target, judgment_item_id in sorted(expected_keys - actual_keys):
        errors.append(
            "%s is missing the required judgment (%s, %s)" %
            (item_id, target, judgment_item_id))
    for target, judgment_item_id in sorted(actual_keys - expected_keys):
        errors.append(
            "%s binds the unexpected judgment (%s, %s)" %
            (item_id, target, judgment_item_id))
    if not errors and wrapper.get("judgment_record_set_sha256") !=             judgment_record_set_sha256(actual):
        errors.append(
            "%s batch review wrapper judgment_record_set_sha256 does not "
            "bind the exact actual judgment set" % item_id)
    return errors


def batch_review_receipt_errors(catalog, receipt_id, *, item_id, task_id,
                                delta_page_receipt_ids):
    """Validate the current batch-level authorization around page evidence.

    Page receipts may have been produced by older evidence protocols and are
    validated separately as history.  The lifecycle edge is authorized only
    by one current manual-attestation receipt that binds their exact IDs.
    """
    errors = []
    receipt = _require_receipt(
        catalog, receipt_id, "%s batch review" % item_id, errors,
        expected={
            "tool": MANUAL_ATTESTATION_TOOL,
            "tool_version": MANUAL_ATTESTATION_TOOL_VERSION,
            "gate_id": BATCH_REVIEW_GATE_ID,
            "check": BATCH_REVIEW_CHECK,
            "target": item_id,
            "task_id": task_id,
            "batch_id": item_id,
        },
    )
    if receipt is None:
        return errors
    bound = receipt.get("delta_page_receipt_ids")
    expected = sorted(set(delta_page_receipt_ids or []))
    if (not isinstance(bound, list) or
            not all(_nonempty_string(value) for value in bound)):
        errors.append(
            "%s batch review receipt %s delta_page_receipt_ids must be an "
            "explicit string list" % (item_id, receipt_id))
    elif bound != sorted(set(bound)):
        errors.append(
            "%s batch review receipt %s delta_page_receipt_ids must be "
            "sorted and unique" % (item_id, receipt_id))
    elif bound != expected:
        errors.append(
            "%s batch review receipt %s delta_page_receipt_ids=%r, "
            "expected exact Delta page receipt IDs %r" %
            (item_id, receipt_id, bound, expected))
    if isinstance(bound, list):
        for page_receipt_id in expected:
            _require_receipt(
                catalog, page_receipt_id,
                "%s batch review page evidence" % item_id, errors,
            )
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


def _pending_control_ids(progress):
    """Return pending Guidance and Amendment identifiers for resume/terminal gates."""
    pending_guidance = []
    guidance = progress.get("guidance_queue")
    if isinstance(guidance, list):
        for index, entry in enumerate(guidance):
            if (not isinstance(entry, dict) or
                    entry.get("status") not in FINAL_CONTROL_STATUSES):
                pending_guidance.append(str(
                    entry.get("guidance_id") if isinstance(entry, dict) else
                    "#%d" % index))
    pending_amendments = []
    amendments = progress.get("amendments")
    if isinstance(amendments, list):
        for index, entry in enumerate(amendments):
            if not isinstance(entry, dict):
                pending_amendments.append("#%d" % index)
                continue
            status = entry.get("status")
            if (status not in FINAL_CONTROL_STATUSES or
                    (status == "verified" and
                     entry.get("writeback_done") is not True)):
                pending_amendments.append(str(entry.get("id") or "#%d" % index))
    return pending_guidance, pending_amendments


def _last_reconciled_guidance_id(progress):
    """Derive the incremental guidance boundary named by K00/10 and K12/04.

    K13/07 keeps Pending/reconciled Guidance in Progress but forbids Progress
    holding a second authority for anything the owned records already
    determine.  ``last_reconciled_guidance_id`` is exactly such a value: it is
    the last entry of the longest recorded prefix that has left ``received``,
    so it is a projection of ``guidance_queue`` rather than an independently
    editable cursor.  ``guidance_id`` is task-local and monotonically
    increasing (K13/06), and no status transition returns to ``received``, so
    the projection never moves backwards.  Batch-close reconciliation still
    carries the existing open items separately (K12/04); this boundary only
    bounds what is *new*.
    """
    guidance = progress.get("guidance_queue")
    if not isinstance(guidance, list):
        return None
    boundary = None
    for entry in guidance:
        if not isinstance(entry, dict) or entry.get("status") == "received":
            break
        entry_id = entry.get("guidance_id")
        if not _nonempty_string(entry_id):
            break
        boundary = entry_id
    return boundary


def _task_transition_receipt_record_errors(
        catalog, receipt_id, receipt, completion_semantics,
        *, expected_contract_sha=None):
    """Validate the canonical, history-independent transition fields.

    The live Progress validator and historical maintenance-predecessor
    validation share this exact record contract.  History ordering and the
    live checkpoint remain the caller's responsibility; receipt shape, edge
    semantics, fingerprints, and evidence binding do not get a weaker
    historical substitute.
    """
    errors = []
    before = receipt.get("before_task_state")
    after = receipt.get("after_task_state")
    if (before, after) not in TASK_LIFECYCLE_EDGES:
        errors.append("task transition receipt %s has illegal edge %r -> %r" %
                      (receipt_id, before, after))
    elif (completion_semantics == "build" and after == "complete" and
          before != "completion-candidate"):
        errors.append(
            "build task transition %s may not bypass completion-candidate" %
            receipt_id
        )
    elif (completion_semantics == "maintenance" and
          "completion-candidate" in (before, after)):
        errors.append(
            "maintenance task transition %s may not enter or leave "
            "completion-candidate" % receipt_id
        )
    elif (completion_semantics == "maintenance" and after == "complete" and
          before not in ("planned", "active")):
        errors.append(
            "maintenance task transition %s must be planned/active -> "
            "complete" % receipt_id
        )
    checked_at = receipt.get("checked_at")
    if not _valid_timestamp(checked_at):
        errors.append("task transition receipt %s has invalid checked_at" %
                      receipt_id)
    for field in (
            "before_coverage_sha256", "after_coverage_sha256",
            "before_required_queue_sha256",
            "after_required_queue_sha256", "before_progress_sha256",
            "after_progress_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append("task transition receipt %s has invalid %s" %
                          (receipt_id, field))
    contract_sha = receipt.get("contract_sha256")
    if not isinstance(contract_sha, str) or not SHA256_RE.fullmatch(
            contract_sha):
        errors.append("task transition receipt %s has invalid "
                      "contract_sha256" % receipt_id)
    elif (expected_contract_sha is not None and
          contract_sha != expected_contract_sha):
        errors.append("task transition receipt %s does not bind the "
                      "Task Contract active at Queue revision %r" %
                      (receipt_id, receipt.get("queue_revision")))
    if receipt.get("before_coverage_sha256") != receipt.get(
            "after_coverage_sha256"):
        errors.append("task transition receipt %s must not mutate Coverage" %
                      receipt_id)
    if (isinstance(receipt.get("before_progress_sha256"), str) and
            isinstance(receipt.get("after_progress_sha256"), str) and
            receipt.get("before_progress_sha256") ==
            receipt.get("after_progress_sha256")):
        errors.append("task transition receipt %s must change Progress bytes" %
                      receipt_id)
    for field, minimum in (("queue_revision", 1),
                           ("queue_state_revision", 0)):
        value = receipt.get(field)
        if (not isinstance(value, int) or isinstance(value, bool) or
                value < minimum):
            errors.append("task transition receipt %s has invalid %s" %
                          (receipt_id, field))
    evidence = receipt.get("evidence_receipt")
    if after in ("completion-candidate", "complete"):
        if not _nonempty_string(evidence):
            errors.append("task transition %s requires evidence_receipt" %
                          receipt_id)
        else:
            _require_receipt(
                catalog, evidence, "task transition %s evidence" % receipt_id,
                errors,
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


def _operational_amendment_registration_errors(
        progress, amendment, label, current_catalog, historical_catalog,
        queue, coverage_sha, queue_sha, progress_sha):
    """Validate the registration which authorized one operational Amendment.

    A pending Amendment is a current authorization and therefore resolves only
    through the Standards-adoption-filtered catalog.  Once the transaction is
    verified, the same registration is immutable historical evidence; later
    Standards adoption may invalidate it for new work without erasing the fact
    that it authorized the completed transaction.
    """
    errors = []
    operation = amendment.get("operation")
    if operation is None:
        # An ordinary Guidance log row carries no operation and owes no
        # registration binding.
        return errors
    if operation == "contract-amendment":
        # Written only by its dedicated K13/06 transaction writer, which has
        # no pending phase; the row lands committed with its verification
        # receipt, and _contract_amendment_row_errors owns its binding.
        return errors
    if operation not in OPERATIONAL_AMENDMENT_OPERATIONS:
        # Fail closed: a row *claiming* an operation this validator does not
        # know would otherwise skip every registration binding below, making
        # an unknown operation name a way to hold authorization with no
        # registered evidence at all.
        errors.append(
            "%s declares unknown operation %r; operational Amendments are "
            "limited to %s, and an unrecognized operation cannot be exempt "
            "from registration binding" %
            (label, operation,
             ", ".join(sorted(OPERATIONAL_AMENDMENT_OPERATIONS) +
                       ["contract-amendment"])))
        return errors
    status = amendment.get("status")
    writeback = amendment.get("writeback_done")
    pending = status == "approved" and writeback is False
    verified = status == "verified" and writeback is True
    catalog = current_catalog if pending else historical_catalog
    receipt_id = amendment.get("registration_receipt")
    approval_reference = amendment.get("approval_reference")
    if not _nonempty_string(approval_reference):
        errors.append("%s approval_reference must be a non-empty string" % label)

    state_prefix = ("queue_state_revision" if operation == "queue-replan"
                    else "state_revision")
    expected = {
        "tool": REGISTER_AMENDMENT_TOOL,
        # K12/10 producer-era identity: a registration sealed under an
        # accounted Standards era is never re-judged against the current
        # writer constant — the payload contract below stays exact, and a
        # protocol the current runtime cannot execute fails at execution or
        # is withdrawn, never by version drift here.
        "tool_version": ANY_PRODUCER_ERA_VERSION,
        "check": "amendment_registration",
        "target": amendment.get("id"),
        "task_id": queue.get("task_id"),
        "actor_role": "integrator",
        "amendment_id": amendment.get("id"),
        "operation": operation,
        "approval_reference": approval_reference,
        "summary": amendment.get("summary"),
        "affected_pages": amendment.get("affected_pages"),
        "affected_batches": amendment.get("affected_batches"),
        "scope_version_before": amendment.get("scope_version_before"),
        "scope_version_after": amendment.get("scope_version_after"),
        "queue_revision_before": amendment.get("queue_revision_before"),
        "queue_revision_after": amendment.get("queue_revision_after"),
        "state_revision_before": amendment.get(state_prefix + "_before"),
        "state_revision_after": amendment.get(state_prefix + "_after"),
        "coverage_proposal_path": amendment.get("coverage_proposal_path"),
        "coverage_proposal_sha256": amendment.get(
            "coverage_proposal_sha256"),
    }
    if operation == "queue-replan":
        expected["replan_diff_sha256"] = amendment.get("replan_diff_sha256")
    else:
        expected.update({
            "plan_path": amendment.get("plan_path"),
            "plan_sha256": amendment.get("plan_sha256"),
            "cancel_batch_id": amendment.get("cancel_batch_id"),
        })
    if operation == "property-state-migration":
        expected.update({
            field: amendment.get(field)
            for field in PROPERTY_STATE_MIGRATION_BINDING_FIELDS
        })
    receipt = _require_receipt(
        catalog, receipt_id, "%s registration" % label, errors,
        expected=expected,
    )
    if receipt is None:
        return errors
    receipt_version = receipt.get("tool_version")
    if receipt_version not in SUPPORTED_REGISTER_AMENDMENT_TOOL_VERSIONS:
        errors.append(
            "%s registration receipt has unsupported register_amendment "
            "producer version %r" % (label, receipt_version))
    if (operation == "property-state-migration" and
            receipt_version != REGISTER_AMENDMENT_TOOL_VERSION):
        errors.append(
            "%s property-state-migration requires register_amendment %s" %
            (label, REGISTER_AMENDMENT_TOOL_VERSION))
    if operation == "property-state-migration":
        try:
            migration_records = \
                metadata_property_state.validate_legacy_property_migration_records(
                    amendment.get("property_state_migration_records"),
                    expected_paths=amendment.get("affected_pages"))
            migration_set_sha = \
                metadata_property_state.legacy_property_migration_set_sha256(
                    amendment.get("property_state_migration_records"))
        except (TypeError, ValueError) as exc:
            errors.append(
                "%s property-state-migration records are invalid: %s" %
                (label, exc))
            migration_records = {}
            migration_set_sha = None
        if amendment.get("property_state_migration_count") != len(
                migration_records):
            errors.append(
                "%s property-state-migration count does not equal its exact "
                "record set" % label)
        if amendment.get(
                "property_state_migration_set_sha256") != migration_set_sha:
            errors.append(
                "%s property-state-migration record-set digest is stale" %
                label)
        if amendment.get("operation_capability") != \
                LEGACY_PROPERTY_ADOPTION_OPERATION:
            errors.append(
                "%s property-state-migration does not bind the %s typed "
                "operation" % (label, LEGACY_PROPERTY_ADOPTION_OPERATION))
        for field in (
                "property_state_migration_set_sha256",
                "metadata_execution_contract_fingerprint",
                "metadata_execution_rule_fingerprint",
                "profile_snapshot_sha256", "profile_contract_fingerprint",
                "profile_load_inputs_sha256"):
            if not SHA256_RE.fullmatch(str(amendment.get(field) or "")):
                errors.append(
                    "%s property-state-migration has invalid %s" %
                    (label, field))
        if not _nonempty_string(amendment.get("selected_profile_manifest")):
            errors.append(
                "%s property-state-migration has no selected Profile "
                "manifest" % label)
    authority_fields = (
        "decision_mode", "authority_id", "authority_sha256",
        "change_classes", "amendment_impact_sha256",
    )
    if receipt_version in ("1.2.0", REGISTER_AMENDMENT_TOOL_VERSION):
        for field in authority_fields:
            if receipt.get(field) != amendment.get(field):
                errors.append(
                    "%s registration receipt %s=%r, expected %r" %
                    (label, field, receipt.get(field), amendment.get(field)))
        if amendment.get("decision_mode") not in (
                "contract-delegated", "explicit-user"):
            errors.append(
                "%s current registration decision_mode is invalid" % label)
        classes = amendment.get("change_classes")
        if (not isinstance(classes, list) or not classes or
                classes != sorted(set(classes))):
            errors.append(
                "%s current registration change_classes must be a non-empty "
                "sorted unique list" % label)
        for field in ("amendment_impact_sha256",):
            if not SHA256_RE.fullmatch(str(amendment.get(field) or "")):
                errors.append("%s current registration has invalid %s" %
                              (label, field))
        if amendment.get("decision_mode") == "contract-delegated":
            if (not _nonempty_string(amendment.get("authority_id")) or
                    not SHA256_RE.fullmatch(str(
                        amendment.get("authority_sha256") or ""))):
                errors.append(
                    "%s delegated registration must bind authority id/hash" %
                    label)
        elif (amendment.get("authority_id") is not None or
              amendment.get("authority_sha256") is not None):
            errors.append(
                "%s explicit-user registration must not claim contract "
                "authority" % label)
    elif any(field in amendment or field in receipt
             for field in authority_fields):
        errors.append(
            "%s legacy registration era must not claim delegated-authority "
            "fields" % label)
    if not _valid_timestamp(receipt.get("checked_at")):
        errors.append("%s registration receipt has invalid checked_at" % label)
    elif amendment.get("date") != receipt.get("checked_at")[:10]:
        errors.append("%s date must equal the registration receipt date" % label)
    for field in (
            "contract_sha256", "before_coverage_sha256",
            "after_coverage_sha256", "before_required_queue_sha256",
            "after_required_queue_sha256", "before_progress_sha256",
            "after_progress_sha256"):
        if not SHA256_RE.fullmatch(str(receipt.get(field, ""))):
            errors.append("%s registration receipt has invalid %s" %
                          (label, field))
    if pending:
        pending_bindings = {
            "contract_sha256": _contract_sha256(progress),
            "before_coverage_sha256": coverage_sha,
            "after_coverage_sha256": coverage_sha,
            "before_required_queue_sha256": queue_sha,
            "after_required_queue_sha256": queue_sha,
            "after_progress_sha256": progress_sha,
        }
        for field, value in pending_bindings.items():
            if receipt.get(field) != value:
                errors.append(
                    "%s current registration receipt has %s=%r, expected %r" %
                    (label, field, receipt.get(field), value)
                )
    elif status == "withdrawn" and writeback is False:
        # K13/06 withdrawal: a pending registration whose execution can no
        # longer validate is retired through the registering writer, never by
        # editing the row.  The withdrawal receipt is immutable history; the
        # bound plan/proposal bytes above stay verified forever.
        if not _nonempty_string(amendment.get("withdrawal_reason")):
            errors.append("%s withdrawn row must record a nonempty "
                          "withdrawal_reason" % label)
        _require_receipt(
            historical_catalog, amendment.get("withdrawal_receipt"),
            "%s withdrawal" % label, errors,
            expected={
                "tool": REGISTER_AMENDMENT_TOOL,
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "check": "amendment_withdrawal",
                "target": amendment.get("id"),
                "amendment_id": amendment.get("id"),
                "registration_receipt": receipt_id,
            },
        )
        return errors
    elif not verified:
        # The operation-specific validators report the illegal lifecycle pair;
        # registration is meaningful only at either end of that pair.
        return errors
    return errors


def _registration_execution_bridge_errors(
        amendment, label, historical_catalog, commit_receipt,
        commit_queue_before_field):
    """Bind one completed operation to the exact state its registration froze."""
    errors = []
    if not isinstance(commit_receipt, dict):
        return errors
    registration_id = amendment.get("registration_receipt")
    registration_entry = historical_catalog.get(registration_id) if \
        _nonempty_string(registration_id) else None
    registration = registration_entry[1] if registration_entry is not None \
        else None
    if not isinstance(registration, dict):
        return errors
    for registration_field, commit_field in (
            ("after_coverage_sha256", "before_coverage_sha256"),
            ("after_required_queue_sha256", commit_queue_before_field),
            ("after_progress_sha256", "before_progress_sha256")):
        registered_sha = registration.get(registration_field)
        execution_sha = commit_receipt.get(commit_field)
        if (SHA256_RE.fullmatch(str(registered_sha or "")) and
                SHA256_RE.fullmatch(str(execution_sha or "")) and
                registered_sha != execution_sha):
            errors.append(
                "%s registration %s=%r does not bridge to execution %s=%r" %
                (label, registration_field, registered_sha,
                 commit_field, execution_sha)
            )
    registration_time = _timestamp_value(registration.get("checked_at"))
    commit_time = _timestamp_value(commit_receipt.get("checked_at"))
    if commit_time is None:
        errors.append("%s execution receipt has invalid checked_at" % label)
    elif registration_time is not None and commit_time < registration_time:
        errors.append(
            "%s execution receipt predates its registration receipt" % label
        )
    return errors


CONTRACT_AMENDMENT_ROW_FIELDS = frozenset((
    "id", "date", "summary", "status", "writeback_done", "operation",
    "approval_reference",
    "scope_version_before", "scope_version_after",
    "queue_revision_before", "queue_revision_after",
    "state_revision_before", "state_revision_after",
    "contract_version_before", "contract_version_after",
    "plan_path", "plan_sha256", "verification_receipt",
    # The state edge this transaction claims, recorded in the row so the
    # commit receipt can be cross-bound to a durable record exactly as the
    # K13/15 adoption record binds its receipt.  ``after_progress_sha256``
    # is absent by construction: the row lives inside the progress document.
    "coverage_sha256_before", "required_queue_sha256_before",
    "progress_sha256_before", "after_coverage_sha256",
    "after_required_queue_sha256", "policy_fingerprint",
    "changed_contract_fields",
))
CONTRACT_AMENDMENT_ROW_OPTIONAL_FIELDS = frozenset((
    "changed_contract_fields",
))
CONTRACT_AMENDMENT_PLAN_PREFIX = ".cambium/deltas/contract-amendments"
CONTRACT_AMENDMENT_TOOL_VERSIONS = frozenset(("1.0.0", "1.1.0"))


def _contract_amendment_row_errors(root, amendment, label, historical_catalog,
                                   task_id, accounted, live_contract):
    """Validate one committed contract-amendment row, K13/06.

    The dedicated writer has no pending phase: it either commits the whole
    transaction -- contract bytes, Queue revision, this row, and the receipt
    the row names -- or writes nothing.  A row in any other state is
    therefore not an in-progress amendment but evidence of a bypassed
    writer, and fails closed.  Anchor continuity (the before/after contract
    fingerprints actually chaining) belongs to _contract_anchor_chain; this
    validator owns the row's own shape and its binding to plan and receipt.
    """
    errors = []
    errors.extend(_closed_mapping_errors(
        amendment, label, CONTRACT_AMENDMENT_ROW_FIELDS,
        CONTRACT_AMENDMENT_ROW_OPTIONAL_FIELDS))
    required_fields = (CONTRACT_AMENDMENT_ROW_FIELDS -
                       CONTRACT_AMENDMENT_ROW_OPTIONAL_FIELDS)
    if set(amendment) - CONTRACT_AMENDMENT_ROW_FIELDS or \
            required_fields - set(amendment):
        return errors
    if (amendment.get("status") != "verified" or
            amendment.get("writeback_done") is not True):
        errors.append(
            "%s contract-amendment must be verified/written-back; its writer "
            "has no pending phase, so any other state is a bypassed "
            "transaction rather than an in-progress one" % label)
    for field in ("id", "date", "summary", "approval_reference",
                  "contract_version_before", "contract_version_after"):
        if not _nonempty_string(amendment.get(field)):
            errors.append("%s %s must be a non-empty string" % (label, field))
    if amendment.get("contract_version_before") == amendment.get(
            "contract_version_after"):
        errors.append("%s must advance contract_version" % label)
    scope_before = amendment.get("scope_version_before")
    scope_after = amendment.get("scope_version_after")
    if not _nonempty_string(scope_before) or scope_before != scope_after:
        errors.append("%s must record one unchanged scope_version; scope "
                      "belongs to the replan machinery" % label)
    queue_before = amendment.get("queue_revision_before")
    queue_after = amendment.get("queue_revision_after")
    if (not isinstance(queue_before, int) or isinstance(queue_before, bool) or
            queue_before < 1 or queue_after != queue_before + 1):
        errors.append("%s queue revision edge must increment by one" % label)
    state_before = amendment.get("state_revision_before")
    state_after = amendment.get("state_revision_after")
    if (not isinstance(state_before, int) or isinstance(state_before, bool) or
            state_before < 0 or state_after != state_before):
        errors.append("%s must preserve state_revision; it changes no batch "
                      "lifecycle" % label)
    plan_path = amendment.get("plan_path")
    plan_sha = amendment.get("plan_sha256")
    if not _nonempty_string(plan_path) or not (
            isinstance(plan_sha, str) and SHA256_RE.fullmatch(plan_sha)):
        errors.append("%s must bind plan_path and plan_sha256" % label)
    else:
        try:
            plan_file = kblib.managed_repository_path(
                root, plan_path, CONTRACT_AMENDMENT_PLAN_PREFIX,
                suffixes=(".yaml", ".yml"), must_exist=True)
            if kblib.sha256_file(plan_file) != plan_sha:
                errors.append("%s plan bytes differ from persisted SHA" %
                              label)
        except (OSError, ValueError) as exc:
            errors.append("%s plan is not resolvable: %s" % (label, exc))
    # The row's own state-edge and policy identity fields must be well
    # formed before anything binds to them.
    for field in ("coverage_sha256_before", "required_queue_sha256_before",
                  "progress_sha256_before", "after_coverage_sha256",
                  "after_required_queue_sha256", "policy_fingerprint"):
        value = amendment.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append(
                "%s %s must be spelled sha256:<64 hex digits>" %
                (label, field))
    receipt_id = amendment.get("verification_receipt")
    entry = historical_catalog.get(receipt_id) if _nonempty_string(
        receipt_id) else None
    if entry is None:
        errors.append("%s verification_receipt is not in the receipt "
                      "catalog" % label)
        return errors
    receipt = entry[1]
    bindings = {
        "tool": "apply_contract_amendment",
        "check": "contract_amendment",
        "result": "pass",
        "actor_role": "integrator",
        "transaction_phase": "commit",
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "before_contract_version": amendment.get("contract_version_before"),
        "after_contract_version": amendment.get("contract_version_after"),
        "queue_revision_before": queue_before,
        "queue_revision_after": queue_after,
        # The receipt's claimed state edge must equal the durable row's,
        # so tampering either alone is visible.  The receipt spells the
        # queue fields with the longer Required Queue writer names.
        "before_coverage_sha256": amendment.get("coverage_sha256_before"),
        "before_required_queue_sha256":
            amendment.get("required_queue_sha256_before"),
        "before_progress_sha256": amendment.get("progress_sha256_before"),
        "after_coverage_sha256": amendment.get("after_coverage_sha256"),
        "after_required_queue_sha256":
            amendment.get("after_required_queue_sha256"),
        "policy_fingerprint": amendment.get("policy_fingerprint"),
    }
    for field, value in bindings.items():
        if receipt.get(field) != value:
            errors.append("%s commit receipt has %s=%r, expected %r" %
                          (label, field, receipt.get(field), value))
    after_progress = receipt.get("after_progress_sha256")
    if not SHA256_RE.fullmatch(str(after_progress or "")):
        errors.append("%s commit receipt has invalid after_progress_sha256" %
                      label)
    receipt_version = receipt.get("tool_version")
    if receipt_version not in \
            CONTRACT_AMENDMENT_TOOL_VERSIONS:
        errors.append(
            "%s commit receipt has unsupported producer tool_version %r; "
            "known contract-amendment eras: %s" %
            (label, receipt.get("tool_version"),
             ", ".join(sorted(CONTRACT_AMENDMENT_TOOL_VERSIONS))))
    if receipt_version == CONTRACT_AMENDMENT_TOOL_VERSION:
        changed = amendment.get("changed_contract_fields")
        if (not isinstance(changed, list) or not changed or
                changed != sorted(set(changed)) or
                set(changed) - {"policy_exceptions", "amendment_authority"}):
            errors.append(
                "%s current-era changed_contract_fields must be a non-empty "
                "sorted subset of policy_exceptions/amendment_authority" %
                label)
        elif receipt.get("changed_contract_fields") != changed:
            errors.append(
                "%s commit receipt does not bind changed_contract_fields" %
                label)
    elif "changed_contract_fields" in amendment or \
            "changed_contract_fields" in receipt:
        errors.append(
            "%s legacy contract-amendment era must not claim "
            "changed_contract_fields" % label)
    if receipt.get("task_id") != task_id:
        errors.append(
            "%s commit receipt has task_id=%r, expected %r" %
            (label, receipt.get("task_id"), task_id))
    for field in ("standards_version", "selected_profile_manifest"):
        if not _nonempty_string(receipt.get(field)):
            errors.append(
                "%s commit receipt carries no %s identity; a receipt whose "
                "Standards era cannot be told is not replayable evidence" %
                (label, field))
    # Nonemptiness is not identity: the claimed era must be one this
    # instance accounts for, and the manifest must be the task's own.  A
    # receipt claiming `never-adopted` or a foreign profile is one this
    # runtime never produced.
    errors.extend(_producer_era_errors(
        receipt, receipt_id, "%s commit" % label, accounted))
    live_manifest = (live_contract or {}).get("selected_profile_manifest")
    claimed_manifest = receipt.get("selected_profile_manifest")
    if (_nonempty_string(claimed_manifest) and
            _nonempty_string(live_manifest) and
            claimed_manifest != live_manifest):
        errors.append(
            "%s commit receipt claims selected_profile_manifest=%r, but "
            "this task's contract selects %r; a grant judged against a "
            "foreign profile is not this task's evidence" %
            (label, claimed_manifest, live_manifest))
    return errors


def _cross_ledger_amendment_errors(
        root, progress, current_catalog, historical_catalog, queue,
        coverage_sha, queue_sha, progress_sha):
    """Validate append-only commit evidence for cross-Ledger Amendments."""
    errors = []
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        return errors
    expected_sequence = 1
    previous_commit = None
    seen_transactions = set()
    seen_commits = set()
    pending_count = 0
    pending_seen = False
    accounted = accounted_standards_versions(progress, queue)
    live_contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    for index, amendment in enumerate(amendments):
        if (isinstance(amendment, dict) and
                amendment.get("operation") == "contract-amendment"):
            errors.extend(_contract_amendment_row_errors(
                root, amendment, "Progress amendments[%d]" % index,
                historical_catalog, progress.get("task_id"),
                accounted, live_contract))
            continue
        if (isinstance(amendment, dict) and
                amendment.get("operation") is not None and
                amendment.get("operation") not in
                ("scope-replan", "cancel-batch", "queue-replan",
                 "gap-routing-reconciliation", "property-state-migration")):
            # Fail closed here, at the walk itself: a row claiming an
            # operation no validator owns would otherwise be skipped by
            # every specialized check below, making an unknown operation
            # name an exemption from evidence.
            errors.append(
                "Progress amendments[%d] declares unknown operation %r; "
                "known operations are scope-replan, cancel-batch, "
                "queue-replan, gap-routing-reconciliation, "
                "property-state-migration, contract-amendment" %
                (index, amendment.get("operation")))
            continue
        if (not isinstance(amendment, dict) or
                amendment.get("operation") not in
                ("scope-replan", "cancel-batch",
                 "gap-routing-reconciliation", "property-state-migration")):
            continue
        label = "Progress amendments[%d]" % index
        status = amendment.get("status")
        writeback = amendment.get("writeback_done")
        operation = amendment.get("operation")
        for field in ("id", "summary", "scope_version_before",
                      "scope_version_after", "coverage_proposal_path"):
            if not _nonempty_string(amendment.get(field)):
                errors.append("%s %s must be a non-empty string" %
                              (label, field))
        for field in ("affected_pages", "affected_batches"):
            values = amendment.get(field)
            if (not isinstance(values, list) or
                    not all(_nonempty_string(value) for value in values)):
                errors.append("%s %s must be an explicit string list" %
                              (label, field))
            elif values != sorted(values) or len(values) != len(set(values)):
                errors.append("%s %s must be sorted and unique" %
                              (label, field))
        scope_before = amendment.get("scope_version_before")
        scope_after = amendment.get("scope_version_after")
        if (operation in (
                "gap-routing-reconciliation", "property-state-migration") and
                _nonempty_string(scope_before) and
                scope_after != scope_before):
            errors.append(
                "%s %s must preserve scope_version" % (label, operation))
        elif (operation not in (
                "gap-routing-reconciliation", "property-state-migration") and
              _nonempty_string(scope_before) and
              _nonempty_string(scope_after) and
              scope_before == scope_after):
            errors.append("%s cross-Ledger Amendment must change scope_version" %
                          label)
        queue_before = amendment.get("queue_revision_before")
        queue_after = amendment.get("queue_revision_after")
        expected_queue_after = (
            queue_before + 1
            if isinstance(queue_before, int) and
            not isinstance(queue_before, bool) else None)
        if (not isinstance(queue_before, int) or isinstance(queue_before, bool) or
                queue_before < 1 or not isinstance(queue_after, int) or
                isinstance(queue_after, bool) or
                queue_after != expected_queue_after):
            errors.append(
                "%s queue revision edge must increment by one" % label)
        state_before = amendment.get("state_revision_before")
        state_after = amendment.get("state_revision_after")
        if (not isinstance(state_before, int) or isinstance(state_before, bool) or
                state_before < 0 or not isinstance(state_after, int) or
                isinstance(state_after, bool)):
            errors.append("%s state revision edge must use non-negative integers" %
                          label)
        elif (operation in ("scope-replan",
                            "gap-routing-reconciliation",
                            "property-state-migration") and
              state_after != state_before):
            errors.append("%s %s must preserve state_revision" %
                          (label, operation))
        elif (operation == "cancel-batch" and
              state_after != state_before + 1):
            errors.append("%s cancel-batch must increment state_revision by one" %
                          label)
        proposal_sha = amendment.get("coverage_proposal_sha256")
        if (not isinstance(proposal_sha, str) or
                not SHA256_RE.fullmatch(proposal_sha)):
            errors.append("%s coverage_proposal_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)
        cancel_id = amendment.get("cancel_batch_id")
        if operation in ("scope-replan", "gap-routing-reconciliation",
                         "property-state-migration"):
            if cancel_id is not None:
                errors.append("%s %s cancel_batch_id must be null" %
                              (label, operation))
            if (operation == "property-state-migration" and
                    amendment.get("affected_batches") != []):
                errors.append(
                    "%s property-state-migration affected_batches must be "
                    "empty" % label)
        elif (not _nonempty_string(cancel_id) or
              amendment.get("affected_batches") != [cancel_id]):
            errors.append("%s cancel-batch must bind exactly cancel_batch_id" %
                          label)
        plan_path = amendment.get("plan_path")
        plan_sha = amendment.get("plan_sha256")
        proposal_path = amendment.get("coverage_proposal_path")
        plan = None
        for artifact_label, artifact_path, artifact_sha in (
                ("plan", plan_path, plan_sha),
                ("coverage proposal", proposal_path, proposal_sha)):
            if not _nonempty_string(artifact_path):
                errors.append("%s %s path must be a non-empty string" %
                              (label, artifact_label))
                continue
            if not isinstance(artifact_sha, str) or not SHA256_RE.fullmatch(
                    artifact_sha):
                errors.append("%s %s SHA must be sha256:<64 lowercase hex>" %
                              (label, artifact_label))
                continue
            try:
                artifact = kblib.managed_repository_path(
                    root, artifact_path, ".cambium/deltas/amendments",
                    suffixes=(".yaml", ".yml"), must_exist=True,
                )
                current_sha = kblib.sha256_file(artifact)
                if current_sha != artifact_sha:
                    errors.append("%s %s bytes differ from persisted SHA" %
                                  (label, artifact_label))
                if artifact_label == "plan":
                    plan = kblib.load_yaml_file(artifact)
            except (OSError, ValueError, kblib.YamlSubsetError) as exc:
                errors.append("%s %s is unsafe, missing, or invalid: %s" %
                              (label, artifact_label, exc))
        if (_nonempty_string(plan_path) and _nonempty_string(proposal_path) and
                os.path.normpath(plan_path) == os.path.normpath(proposal_path)):
            errors.append("%s plan and coverage proposal must be different files" %
                          label)
        if isinstance(plan, dict):
            plan_bindings = {
                "amendment_id": amendment.get("id"),
                "operation": operation,
                "affected_pages": amendment.get("affected_pages"),
                "affected_batches": amendment.get("affected_batches"),
                "scope_version_before": scope_before,
                "scope_version_after": scope_after,
                "queue_revision_before": queue_before,
                "queue_revision_after": queue_after,
                "state_revision_before": state_before,
                "state_revision_after": state_after,
                "coverage_proposal_path": proposal_path,
                "coverage_proposal_sha256": proposal_sha,
                "cancel_batch_id": cancel_id,
            }
            for field, value in plan_bindings.items():
                if plan.get(field) != value:
                    errors.append("%s plan %s=%r, expected %r" %
                                  (label, field, plan.get(field), value))
        errors.extend(_operational_amendment_registration_errors(
            progress, amendment, label, current_catalog, historical_catalog,
            queue, coverage_sha, queue_sha, progress_sha,
        ))
        if status == "approved" and writeback is False:
            if scope_before != queue.get("scope_version"):
                errors.append("%s pending Amendment scope_version_before does "
                              "not match the live Queue" % label)
            expected_pending_queue_after = \
                queue.get("queue_revision", 0) + 1
            if (queue_before != queue.get("queue_revision") or
                    queue_after != expected_pending_queue_after):
                errors.append("%s pending Amendment must bind the next live "
                              "Queue revision" % label)
            if state_before != queue.get("state_revision"):
                errors.append("%s pending Amendment state_revision_before does "
                              "not match the live Queue" % label)
            for field in ("transaction_id", "verification_receipt",
                          "transaction_sequence",
                          "previous_transaction_commit_receipt"):
                if amendment.get(field) is not None:
                    errors.append("%s pending Amendment must not claim %s" %
                                  (label, field))
            pending_count += 1
            pending_seen = True
            continue
        if status == "withdrawn" and writeback is False:
            # K13/06 withdrawal: the row stays as immutable evidence and
            # authorizes nothing; the withdrawal receipt is validated with
            # the registration binding above.
            for field in ("transaction_id", "verification_receipt",
                          "transaction_sequence",
                          "previous_transaction_commit_receipt"):
                if amendment.get(field) is not None:
                    errors.append("%s withdrawn Amendment must not claim %s" %
                                  (label, field))
            continue
        if status != "verified" or writeback is not True:
            errors.append("%s cross-Ledger state must be approved/pending, "
                          "withdrawn, or verified/written-back" % label)
            continue
        if pending_seen:
            errors.append("%s verified transaction appears after a pending "
                          "cross-Ledger Amendment" % label)
        transaction_id = amendment.get("transaction_id")
        commit_id = amendment.get("verification_receipt")
        sequence = amendment.get("transaction_sequence")
        prior = amendment.get("previous_transaction_commit_receipt")
        if sequence != expected_sequence:
            errors.append("%s transaction_sequence=%r, expected %d" %
                          (label, sequence, expected_sequence))
        if prior != previous_commit:
            errors.append("%s previous transaction commit is %r, expected %r" %
                          (label, prior, previous_commit))
        if transaction_id in seen_transactions:
            errors.append("%s repeats transaction_id %r" %
                          (label, transaction_id))
        if commit_id in seen_commits:
            errors.append("%s repeats verification_receipt %r" %
                          (label, commit_id))
        seen_transactions.add(transaction_id)
        seen_commits.add(commit_id)
        receipt = _require_receipt(
            historical_catalog, commit_id,
            "%s verification" % label, errors,
            expected={
                "tool": "apply_amendment",
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "check": "amendment_transaction",
                "target": amendment.get("id"),
                "transaction_phase": "commit",
                "transaction_id": transaction_id,
                "amendment_id": amendment.get("id"),
                "operation": amendment.get("operation"),
                "task_id": queue.get("task_id"),
                "actor_role": "integrator",
                "transaction_sequence": sequence,
                "previous_transaction_commit_receipt": prior,
                "registration_receipt":
                    amendment.get("registration_receipt"),
                "plan_path": plan_path,
                "plan_sha256": plan_sha,
                "coverage_proposal_path": proposal_path,
                "coverage_proposal_sha256": proposal_sha,
                "queue_revision_before": queue_before,
                "queue_revision_after": queue_after,
                "state_revision_before": state_before,
                "state_revision_after": state_after,
            },
        )
        if (receipt is not None and receipt.get("tool_version") not in
                SUPPORTED_APPLY_AMENDMENT_TOOL_VERSIONS):
            errors.append(
                "%s verification receipt has unsupported apply_amendment "
                "producer version %r" %
                (label, receipt.get("tool_version")))
        if (receipt is not None and operation ==
                "property-state-migration" and
                receipt.get("tool_version") != APPLY_AMENDMENT_TOOL_VERSION):
            errors.append(
                "%s property-state-migration requires apply_amendment %s" %
                (label, APPLY_AMENDMENT_TOOL_VERSION))
        if receipt is not None and operation == "property-state-migration":
            for field in PROPERTY_STATE_MIGRATION_BINDING_FIELDS:
                if receipt.get(field) != amendment.get(field):
                    errors.append(
                        "%s property-state-migration commit receipt does not "
                        "bind %s" % (label, field))
        if not _nonempty_string(transaction_id):
            errors.append("%s verified transaction_id must be non-empty" % label)
        if receipt is not None and not SHA256_RE.fullmatch(
                str(receipt.get("plan_sha256", ""))):
            errors.append("%s verification receipt has invalid plan_sha256" % label)
        if receipt is not None:
            for phase in ("before", "after"):
                for state_name in ("coverage", "queue", "progress"):
                    field = "%s_%s_sha256" % (phase, state_name)
                    if not SHA256_RE.fullmatch(str(receipt.get(field, ""))):
                        errors.append("%s verification receipt has invalid %s" %
                                      (label, field))
            errors.extend(_registration_execution_bridge_errors(
                amendment, label, historical_catalog, receipt,
                "before_queue_sha256",
            ))
        previous_commit = commit_id
        expected_sequence += 1
    if pending_count > 1:
        errors.append("Progress has %d pending cross-Ledger Amendments; exactly "
                      "one may be staged at a time" % pending_count)
    return errors


def _pending_cross_ledger_amendments(progress):
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        return []
    return [
        amendment.get("id", "<unnamed>")
        for amendment in amendments
        if (isinstance(amendment, dict) and
            amendment.get("operation") in
            ("scope-replan", "cancel-batch", "queue-replan",
             "gap-routing-reconciliation", "property-state-migration") and
            amendment.get("status") == "approved" and
            amendment.get("writeback_done") is False)
    ]


def _coverage_provenance_errors(progress, queue, catalog, coverage_sha,
                                queue_sha):
    """Bind materialized Coverage bytes to a qualified canonical writer.

    Before the first Queue materialization, initial Coverage is an adopter
    input.  Afterwards its ordinary write paths are transactional, so the live
    bytes must occur as the after-image of a semantically qualified receipt.
    Generic Guidance remains an authorized control input.  Executable
    operational Amendments are different: register_amendment must bind their
    approved bytes and current state before downstream writers may consume
    them.  Queue retains its own revision, fingerprint, and transition chain.
    """
    items = queue.get("required_queue")
    pre_materialization = (
        isinstance(items, list) and not items and
        queue.get("queue_revision") == 1 and
        queue.get("state_revision") == 0 and
        progress.get("initial_queue_receipt") is None
    )
    if pre_materialization:
        return []

    allowed = {
        ("compile_queue", "queue_structure"),
        ("compile_queue", "queue_replan"),
        ("update_queue", "queue_transition"),
        ("update_task", "task_transition"),
        ("apply_amendment", "amendment_transaction"),
        ("apply_delta", "delta_apply"),
        (STANDARDS_ADOPTION_TOOL, "standards_adoption"),
        ("apply_contract_amendment", "contract_amendment"),
    }
    writers = []
    # Writer receipts live in one collision-checked managed namespace.  Some
    # transactions (notably apply_delta before the following close edge) have
    # no canonical field in which to store their ID yet, so provenance may use
    # any semantically qualified receipt in that namespace.  Canonical state
    # references remain validated separately by their owning contracts.
    for receipt_id, entry in catalog.items():
        receipt = entry[1]
        if ((receipt.get("tool"), receipt.get("check")) not in allowed or
                receipt.get("result") != "pass" or
                receipt.get("invalidated_by") is not None or
                receipt.get("task_id") != queue.get("task_id") or
                receipt.get("actor_role") != "integrator"):
            continue
        tool = receipt.get("tool")
        if (tool in ("apply_amendment", STANDARDS_ADOPTION_TOOL,
                     "apply_contract_amendment") and
                receipt.get("transaction_phase") != "commit"):
            continue
        # Historical after-images remain valid evidence for history, but they
        # cannot authorize restoration of an older Coverage file.  A current
        # Coverage writer must be anchored to the exact live Queue point.
        if tool in ("apply_amendment", STANDARDS_ADOPTION_TOOL):
            receipt_queue_sha = receipt.get("after_queue_sha256")
        elif tool == "apply_delta":
            receipt_queue_sha = receipt.get("required_queue_sha256")
        else:
            receipt_queue_sha = receipt.get("after_required_queue_sha256")
        if receipt_queue_sha != queue_sha:
            continue
        if tool == "apply_delta":
            batch_id = receipt.get("batch_id")
            item = next((candidate for candidate in
                         queue.get("required_queue", [])
                         if isinstance(candidate, dict) and
                         candidate.get("id") == batch_id), None)
            if (item is None or item.get("state") not in
                    ("merge-ready", "closed") or
                    item.get("delta_path") != receipt.get("delta_path") or
                    item.get("delta_sha256") != receipt.get("delta_sha256")):
                continue
        writers.append((receipt_id, receipt))

    errors = []
    # Coverage has no ordinary direct-write phase after materialization.  By
    # contrast, Progress intentionally accepts new Guidance/Amendment control
    # inputs before their transactional write-back, and Queue already has its
    # own revision/fingerprint/transition chain.  Applying a blanket current-
    # byte rule to those two files would make legitimate control input
    # impossible without inventing a second writer API.
    for label, field, live_sha in (
            ("Coverage", "after_coverage_sha256", coverage_sha),):
        if not any(receipt.get(field) == live_sha for _, receipt in writers):
            errors.append(
                "%s current bytes are not the after-image of a qualified "
                "canonical writer receipt" % label
            )
    return errors


def _queue_replan_amendment_errors(
        root, progress, current_catalog, historical_catalog, queue, queue_sha,
        coverage_sha, progress_sha,
                                   allow_pending_receipts=False):
    """Validate durable evidence for same-scope Queue replans.

    A pending replan is an authorization for the *next* structural revision,
    not evidence that a write occurred.  A verified replan is historical
    evidence and therefore binds to one unique compile_queue receipt.  Older
    receipts remain valid after later replans or lifecycle transitions; only
    an Amendment whose two revision axes still equal the live Queue is
    expected to name the live bytes.

    ``allow_pending_receipts`` is reserved for compile_queue's in-memory
    preflight.  It lets that preflight inspect the receipt which will be
    appended by the same locked commit.  Normal validation never enables it,
    so persisted verified state must resolve to an on-disk receipt.
    """
    errors = []
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        return errors

    current_queue_revision = queue.get("queue_revision")
    current_state_revision = queue.get("state_revision")
    current_scope = queue.get("scope_version")
    seen_amendment_ids = set()
    receipt_owners = {}

    def valid_revision(value, minimum=0):
        return (isinstance(value, int) and not isinstance(value, bool) and
                value >= minimum)

    for index, amendment in enumerate(amendments):
        if (not isinstance(amendment, dict) or
                amendment.get("operation") != "queue-replan"):
            continue
        label = "Progress amendments[%d]" % index
        amendment_id = amendment.get("id")
        if not _nonempty_string(amendment_id):
            errors.append("%s queue-replan id must be a non-empty string" % label)
        elif amendment_id in seen_amendment_ids:
            errors.append("%s repeats queue-replan Amendment id %s" %
                          (label, amendment_id))
        else:
            seen_amendment_ids.add(amendment_id)

        affected = amendment.get("affected_batches")
        if (not isinstance(affected, list) or not affected or
                not all(_nonempty_string(value) and
                        BATCH_ID_RE.fullmatch(value) for value in affected)):
            errors.append("%s affected_batches must be a non-empty list of "
                          "valid batch ids" % label)
        elif len(affected) != len(set(affected)):
            errors.append("%s affected_batches must be unique" % label)
        elif affected != sorted(affected):
            errors.append("%s affected_batches must be sorted" % label)

        affected_pages = amendment.get("affected_pages")
        if (not isinstance(affected_pages, list) or
                not all(_nonempty_string(value) for value in affected_pages)):
            errors.append("%s affected_pages must be an explicit string list" %
                          label)
        elif (len(affected_pages) != len(set(affected_pages)) or
              affected_pages != sorted(affected_pages)):
            errors.append("%s affected_pages must be sorted and unique" % label)

        proposal_path = amendment.get("coverage_proposal_path")
        proposal_sha = amendment.get("coverage_proposal_sha256")
        if not _nonempty_string(proposal_path):
            errors.append("%s coverage_proposal_path must be non-empty" % label)
        else:
            try:
                proposal_file = kblib.managed_repository_path(
                    root, proposal_path, ".cambium/deltas/replans",
                    suffixes=(".coverage.yaml",), must_exist=True,
                )
                actual_proposal_sha = kblib.sha256_file(proposal_file)
                if actual_proposal_sha != proposal_sha:
                    errors.append("%s Coverage proposal SHA does not match %s" %
                                  (label, proposal_path))
            except (OSError, ValueError) as exc:
                errors.append("%s Coverage proposal is unsafe or missing: %s" %
                              (label, exc))
        if not isinstance(proposal_sha, str) or not SHA256_RE.fullmatch(
                proposal_sha):
            errors.append("%s coverage_proposal_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)

        scope_before = amendment.get("scope_version_before")
        scope_after = amendment.get("scope_version_after")
        if (not _nonempty_string(scope_before) or
                scope_after != scope_before):
            errors.append("%s same-scope replan must have one unchanged, "
                          "non-empty scope version" % label)

        revision_before = amendment.get("queue_revision_before")
        revision_after = amendment.get("queue_revision_after")
        revisions_valid = (valid_revision(revision_before, 1) and
                           valid_revision(revision_after, 1))
        if not revisions_valid or revision_after != revision_before + 1:
            errors.append("%s queue revisions must be integers with after = "
                          "before + 1" % label)

        state_before = amendment.get("queue_state_revision_before")
        state_after = amendment.get("queue_state_revision_after")
        states_valid = (valid_revision(state_before) and
                        valid_revision(state_after))
        if not states_valid or state_after != state_before:
            errors.append("%s same-scope replan must not change the Queue "
                          "state revision" % label)

        diff_sha = amendment.get("replan_diff_sha256")
        if not isinstance(diff_sha, str) or not SHA256_RE.fullmatch(diff_sha):
            errors.append("%s replan_diff_sha256 must be sha256:<64 lowercase "
                          "hex>" % label)

        status = amendment.get("status")
        writeback = amendment.get("writeback_done")
        errors.extend(_operational_amendment_registration_errors(
            progress, amendment, label, current_catalog, historical_catalog,
            queue, coverage_sha, queue_sha, progress_sha,
        ))
        if status == "approved" and writeback is False:
            if scope_before != current_scope:
                errors.append("%s pending replan scope does not match the live "
                              "Queue" % label)
            if (revision_before != current_queue_revision or
                    revision_after != (current_queue_revision + 1
                                       if valid_revision(current_queue_revision,
                                                         1) else None)):
                errors.append("%s pending replan must authorize the next live "
                              "Queue revision" % label)
            if (state_before != current_state_revision or
                    state_after != current_state_revision):
                errors.append("%s pending replan state revision must match the "
                              "live Queue" % label)
            if (amendment.get("transaction_receipt_id") is not None or
                    amendment.get("transaction_id") is not None or
                    amendment.get("after_required_queue_sha256") is not None or
                    amendment.get("after_coverage_sha256") is not None):
                errors.append("%s pending replan must not claim committed "
                              "receipt/SHA evidence" % label)
            continue

        if status == "withdrawn" and writeback is False:
            # K13/06 withdrawal keeps the row as evidence; it never executes.
            continue
        if status != "verified" or writeback is not True:
            errors.append("%s queue-replan state must be approved/pending, "
                          "withdrawn, or verified/written-back" % label)
            continue

        if (revisions_valid and valid_revision(current_queue_revision, 1) and
                revision_after > current_queue_revision):
            errors.append("%s verified replan revision is newer than the live "
                          "Queue" % label)
        if (states_valid and valid_revision(current_state_revision) and
                state_after > current_state_revision):
            errors.append("%s verified replan state revision is newer than the "
                          "live Queue" % label)

        receipt_id = amendment.get("transaction_receipt_id")
        transaction_id = amendment.get("transaction_id")
        if not _nonempty_string(transaction_id):
            errors.append("%s verified replan transaction_id must be non-empty" %
                          label)
        if _nonempty_string(receipt_id):
            owner = receipt_owners.get(receipt_id)
            if owner is not None:
                errors.append("%s reuses transaction receipt %s already bound "
                              "to %s" % (label, receipt_id, owner))
            else:
                receipt_owners[receipt_id] = amendment_id or label
        receipt = _require_receipt(
            historical_catalog, receipt_id, "%s queue-replan" % label, errors,
            expected={
                "tool": "compile_queue",
                "tool_version": ANY_PRODUCER_ERA_VERSION,
                "check": "queue_replan",
                "target": QUEUE_PATH,
                "task_id": queue.get("task_id"),
                "amendment_id": amendment_id,
                "transaction_id": transaction_id,
                "transaction_phase": "commit",
                "registration_receipt":
                    amendment.get("registration_receipt"),
                "actor_role": "integrator",
                "coverage_proposal_path": proposal_path,
                "coverage_proposal_sha256": proposal_sha,
                "affected_pages": affected_pages,
                "affected_batches": affected,
                "replan_diff_sha256": diff_sha,
                "before_queue_revision": revision_before,
                "after_queue_revision": revision_after,
                "queue_state_revision": state_after,
            },
        )
        catalog_entry = historical_catalog.get(receipt_id) if _nonempty_string(
            receipt_id) else None
        if (catalog_entry is not None and catalog_entry[0] == "<pending-write>" and
                not allow_pending_receipts):
            errors.append("%s verified replan receipt %s is not persisted in "
                          "the repository" % (label, receipt_id))
        if receipt is None:
            continue
        if receipt.get("tool_version") not in \
                SUPPORTED_COMPILE_QUEUE_TOOL_VERSIONS:
            errors.append(
                "%s receipt has unsupported compile_queue producer version "
                "%r" % (label, receipt.get("tool_version")))

        errors.extend(_registration_execution_bridge_errors(
            amendment, label, historical_catalog, receipt,
            "before_required_queue_sha256",
        ))

        before_sha = receipt.get("before_required_queue_sha256")
        after_sha = receipt.get("after_required_queue_sha256")
        if not isinstance(before_sha, str) or not SHA256_RE.fullmatch(before_sha):
            errors.append("%s receipt has invalid before Required Queue SHA" %
                          label)
        if not isinstance(after_sha, str) or not SHA256_RE.fullmatch(after_sha):
            errors.append("%s receipt has invalid after Required Queue SHA" %
                          label)
        amendment_after_sha = amendment.get("after_required_queue_sha256")
        if (not isinstance(amendment_after_sha, str) or
                not SHA256_RE.fullmatch(amendment_after_sha)):
            errors.append("%s after_required_queue_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)
        elif after_sha != amendment_after_sha:
            errors.append("%s Amendment after Required Queue SHA does not match "
                          "its receipt" % label)
        before_coverage_sha = receipt.get("before_coverage_sha256")
        after_coverage_sha = receipt.get("after_coverage_sha256")
        for field, value in (("before_coverage_sha256", before_coverage_sha),
                             ("after_coverage_sha256", after_coverage_sha),
                             ("before_progress_sha256",
                              receipt.get("before_progress_sha256")),
                             ("after_progress_sha256",
                              receipt.get("after_progress_sha256"))):
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append("%s receipt has invalid %s" % (label, field))
        amendment_after_coverage = amendment.get("after_coverage_sha256")
        if (not isinstance(amendment_after_coverage, str) or
                not SHA256_RE.fullmatch(amendment_after_coverage)):
            errors.append("%s after_coverage_sha256 must be sha256:<64 "
                          "lowercase hex>" % label)
        elif after_coverage_sha != amendment_after_coverage:
            errors.append("%s Amendment after Coverage SHA does not match its "
                          "receipt" % label)

        # A subsequent lifecycle transition changes Queue bytes without
        # changing queue_revision; therefore live-byte equality is required
        # only when *both* revision axes still name the current state.
        if (revision_after == current_queue_revision and
                state_after == current_state_revision and
                after_sha != queue_sha):
            errors.append("%s latest replan receipt does not match live Queue "
                          "bytes" % label)
        if (revision_after == current_queue_revision and
                state_after == current_state_revision and
                after_coverage_sha != coverage_sha):
            errors.append("%s latest replan receipt does not match live Coverage "
                          "bytes" % label)
    return errors


def _initial_queue_receipt_errors(progress, catalog, queue, queue_sha,
                                  coverage_sha):
    """Bind every materialized Queue to its unique initial compiler receipt."""
    errors = []
    items = queue.get("required_queue")
    receipt_id = progress.get("initial_queue_receipt")
    if isinstance(items, list) and not items:
        if receipt_id is not None:
            errors.append("empty Queue must have initial_queue_receipt=null")
        return errors
    if not isinstance(items, list):
        return errors
    receipt = _require_receipt(
        catalog, receipt_id, "Progress initial Queue", errors,
        expected={
            "tool": "compile_queue",
            "tool_version": ANY_PRODUCER_ERA_VERSION,
            "check": "queue_structure",
            "target": QUEUE_PATH,
            "task_id": queue.get("task_id"),
            "actor_role": "integrator",
        },
    )
    if receipt is None:
        return errors
    _, contract_errors = _contract_anchor_chain(progress, catalog)
    errors.extend(contract_errors)
    before_revision = receipt.get("before_queue_revision")
    after_revision = receipt.get("after_queue_revision")
    if (not isinstance(before_revision, int) or isinstance(before_revision, bool) or
            not isinstance(after_revision, int) or isinstance(after_revision, bool) or
            after_revision < 1 or before_revision != after_revision - 1):
        errors.append("initial Queue receipt has invalid revision edge %r -> %r" %
                      (before_revision, after_revision))
    elif after_revision > queue.get("queue_revision", -1):
        errors.append("initial Queue receipt is newer than the live Queue revision")
    if receipt.get("queue_state_revision") != 0:
        errors.append("initial Queue receipt queue_state_revision must be 0")
    fingerprints = {}
    for field in (
            "before_required_queue_sha256", "after_required_queue_sha256",
            "before_coverage_sha256", "after_coverage_sha256",
            "before_progress_sha256", "after_progress_sha256"):
        value = receipt.get(field)
        fingerprints[field] = value
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append("initial Queue receipt has invalid %s" % field)
    # Before the first lifecycle transition/replan, the origin receipt still
    # names the exact live Queue and Coverage bytes. Later changes retain the
    # receipt as immutable provenance rather than pretending it is current.
    if (after_revision == queue.get("queue_revision") and
            queue.get("state_revision") == 0):
        if fingerprints.get("after_required_queue_sha256") != queue_sha:
            errors.append("initial Queue receipt does not match live Queue bytes")
        if fingerprints.get("after_coverage_sha256") != coverage_sha:
            errors.append("initial Queue receipt does not match live Coverage bytes")
    return errors




def _work_spec_binding_errors(path, fingerprint, label):
    """Validate one explicit simple/complex batch declaration.

    Null/null is the only spelling for a simple batch.  A complex batch must
    bind both a managed restricted-YAML path and exact lowercase SHA-256.  The pair
    intentionally carries no inferred complexity flag: omission is invalid.
    """
    errors = []
    if path is None and fingerprint is None:
        return errors
    if path is None or fingerprint is None:
        errors.append(
            "%s work_spec_path and work_spec_sha256 must both be null or "
            "both be non-null" % label
        )
        return errors
    if not _nonempty_string(path):
        errors.append("%s work_spec_path must be null or a non-empty string" %
                      label)
    elif (not path.startswith(WORK_SPEC_PREFIX + "/") or
          not path.endswith(".yaml") or
          Path(path).parent.as_posix() != WORK_SPEC_PREFIX):
        errors.append(
            "%s work_spec_path must be a YAML file directly inside %s/" %
            (label, WORK_SPEC_PREFIX)
        )
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
        errors.append(
            "%s work_spec_sha256 must be null or sha256:<64 lowercase hex>" %
            label
        )
    return errors


def _closed_work_spec_mapping_errors(value, expected_fields, label):
    """Validate one mapping node in the closed Work Spec grammar."""
    if not isinstance(value, dict):
        return ["%s must be a mapping" % label]
    actual = set(value)
    missing = sorted(expected_fields - actual)
    extra = sorted(actual - expected_fields)
    errors = []
    if missing:
        errors.append("%s misses field(s): %s" % (label, ", ".join(missing)))
    if extra:
        queue_owned = sorted(set(extra).intersection(
            WORK_SPEC_QUEUE_OWNED_FIELDS))
        if queue_owned:
            errors.append(
                "%s must not declare Queue-owned field(s): %s" %
                (label, ", ".join(queue_owned))
            )
        errors.append("%s has unsupported field(s): %s" %
                      (label, ", ".join(extra)))
    return errors


def _work_spec_id_errors(value, label):
    if (not isinstance(value, str) or
            not WORK_SPEC_RECORD_ID_RE.fullmatch(value)):
        return ["%s must match %s" %
                (label, WORK_SPEC_RECORD_ID_RE.pattern.replace("\\Z", ""))]
    return []


def _work_spec_target_scope_errors(value, manifest, label):
    errors = []
    if (not isinstance(value, list) or not value or
            not all(_nonempty_string(entry) for entry in value)):
        return [
            "%s must be a non-empty explicit string list containing "
            "'batch' or Queue manifest paths" % label
        ]
    if len(set(value)) != len(value):
        errors.append("%s must not contain duplicate targets" % label)
    has_batch = "batch" in value
    if has_batch and value != ["batch"]:
        errors.append(
            "%s must be exactly ['batch'] or contain only Queue manifest "
            "paths; batch and paths cannot be mixed" % label
        )
    elif not has_batch:
        unknown = [entry for entry in value if entry not in manifest]
        if unknown:
            errors.append(
                "%s contains target(s) outside the Queue manifest: %s" %
                (label, ", ".join(unknown))
            )
    return errors


def _nested_queue_owned_work_spec_fields(value, path=()):
    """Return Queue-owned keys hidden below otherwise scalar/list fields.

    ``instructions[].order`` and ``instructions[].depends_on`` are the only
    intentional spelling overlaps with Queue item keys.  Exact mapping checks
    govern those positions; every other occurrence is a forbidden second
    source of runtime state.
    """
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            allowed_overlap = (
                len(path) == 2 and path[0] == "instructions" and
                isinstance(path[1], int) and key in ("order", "depends_on")
            )
            if key in WORK_SPEC_QUEUE_OWNED_FIELDS and not allowed_overlap:
                found.append(".".join(str(part) for part in path + (key,)))
            found.extend(_nested_queue_owned_work_spec_fields(
                child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_nested_queue_owned_work_spec_fields(
                child, path + (index,)))
    return found


def _work_spec_sentinel_paths(value, path=()):
    """Return scalar locations containing an unfilled Work Spec sentinel."""
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(_work_spec_sentinel_paths(child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_work_spec_sentinel_paths(child, path + (index,)))
    elif isinstance(value, str) and any(
            sentinel in value for sentinel in WORK_SPEC_SENTINELS):
        found.append(".".join(str(part) for part in path))
    return found


def _work_spec_errors(root, item):
    """Validate a complex batch's immutable Agent-readable work contract."""
    item_id = item.get("id", "<unknown>")
    label = "Queue item %s" % item_id
    path = item.get("work_spec_path")
    fingerprint = item.get("work_spec_sha256")
    errors = _work_spec_binding_errors(path, fingerprint, label)
    if errors or path is None:
        return errors
    try:
        absolute = kblib.managed_repository_path(
            root, path, WORK_SPEC_PREFIX, suffixes=(".yaml",), must_exist=True,
        )
        if not os.path.isfile(absolute):
            raise ValueError("path is not a regular file")
        with open(absolute, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append("%s Work Spec is unsafe or unreadable: %s" %
                      (label, exc))
        return errors
    actual = kblib.sha256_file(absolute)
    if actual != fingerprint:
        errors.append(
            "%s Work Spec SHA mismatch: Queue=%s actual=%s" %
            (label, fingerprint, actual)
        )
    try:
        metadata = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        errors.append("%s Work Spec is invalid restricted YAML: %s" %
                      (label, exc))
        return errors
    if not isinstance(metadata, dict):
        errors.append("%s Work Spec must be a top-level mapping" % label)
        return errors
    queue_owned = sorted(set(
        _nested_queue_owned_work_spec_fields(metadata)))
    if queue_owned:
        errors.append(
            "%s Work Spec must not declare Queue-owned field path(s): %s" %
            (label, ", ".join(queue_owned))
        )
    errors.extend(_closed_work_spec_mapping_errors(
        metadata, WORK_SPEC_TOP_LEVEL_FIELDS, "%s Work Spec" % label))
    schema_version = metadata.get("schema_version")
    if (not isinstance(schema_version, int) or
            isinstance(schema_version, bool) or schema_version != 1):
        errors.append("%s Work Spec schema_version must be 1" % label)
    if metadata.get("batch_id") != item_id:
        errors.append(
            "%s Work Spec batch_id=%r does not equal Queue id %r" %
            (label, metadata.get("batch_id"), item_id)
        )
    manifest = metadata.get("manifest")
    queue_manifest = item.get("manifest")
    scope_manifest = queue_manifest if isinstance(queue_manifest, list) else []
    if (not isinstance(manifest, list) or
            not all(_nonempty_string(value) for value in manifest)):
        errors.append("%s Work Spec manifest must be an explicit string list" %
                      label)
    elif manifest != queue_manifest:
        errors.append(
            "%s Work Spec manifest must exactly equal Queue manifest in "
            "membership and order" % label
        )
    outcomes = metadata.get("outcomes")
    instructions = metadata.get("instructions")
    conditions = metadata.get("acceptance_conditions")
    constraints = metadata.get("constraints")
    list_contracts = (
        ("outcomes", outcomes, WORK_SPEC_OUTCOME_FIELDS),
        ("instructions", instructions, WORK_SPEC_INSTRUCTION_FIELDS),
        ("acceptance_conditions", conditions, WORK_SPEC_ACCEPTANCE_FIELDS),
        ("constraints", constraints, WORK_SPEC_CONSTRAINT_FIELDS),
    )
    for list_name, records, fields in list_contracts:
        if not isinstance(records, list) or not records:
            errors.append(
                "%s Work Spec %s must be a non-empty list" %
                (label, list_name)
            )
            continue
        for index, record in enumerate(records, 1):
            errors.extend(_closed_work_spec_mapping_errors(
                record, fields, "%s Work Spec %s[%d]" %
                (label, list_name, index)))

    id_contracts = (
        ("outcomes", outcomes, "outcome_id"),
        ("instructions", instructions, "instruction_id"),
        ("acceptance_conditions", conditions, "condition_id"),
        ("constraints", constraints, "constraint_id"),
    )
    for list_name, records, id_field in id_contracts:
        if not isinstance(records, list):
            continue
        seen = set()
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict):
                continue
            identifier = record.get(id_field)
            errors.extend(_work_spec_id_errors(
                identifier, "%s Work Spec %s[%d].%s" %
                (label, list_name, index, id_field)))
            if isinstance(identifier, str):
                if identifier in seen:
                    errors.append(
                        "%s Work Spec %s has duplicate %s %r" %
                        (label, list_name, id_field, identifier)
                    )
                seen.add(identifier)

    if isinstance(outcomes, list):
        for index, record in enumerate(outcomes, 1):
            if isinstance(record, dict) and not _nonempty_string(
                    record.get("required_result")):
                errors.append(
                    "%s Work Spec outcomes[%d].required_result must be a "
                    "non-empty string" % (label, index)
                )

    instruction_by_id = {}
    if isinstance(instructions, list):
        orders = []
        for index, record in enumerate(instructions, 1):
            if not isinstance(record, dict):
                continue
            identifier = record.get("instruction_id")
            order = record.get("order")
            if not isinstance(order, int) or isinstance(order, bool):
                errors.append(
                    "%s Work Spec instructions[%d].order must be an integer" %
                    (label, index)
                )
            else:
                orders.append(order)
            if isinstance(identifier, str):
                instruction_by_id[identifier] = order
            errors.extend(_work_spec_target_scope_errors(
                record.get("target_scope"), scope_manifest,
                "%s Work Spec instructions[%d].target_scope" %
                (label, index)))
            if not _nonempty_string(record.get("required_transformation")):
                errors.append(
                    "%s Work Spec instructions[%d].required_transformation "
                    "must be a non-empty string" % (label, index)
                )
            dependencies = record.get("depends_on")
            if (not isinstance(dependencies, list) or
                    not all(isinstance(dep, str) and
                            WORK_SPEC_RECORD_ID_RE.fullmatch(dep)
                            for dep in dependencies)):
                errors.append(
                    "%s Work Spec instructions[%d].depends_on must be an "
                    "explicit list of stable instruction IDs" %
                    (label, index)
                )
            elif len(set(dependencies)) != len(dependencies):
                errors.append(
                    "%s Work Spec instructions[%d].depends_on must not "
                    "contain duplicates" % (label, index)
                )
        expected_orders = list(range(1, len(instructions) + 1))
        if orders != expected_orders:
            errors.append(
                "%s Work Spec instruction order must be unique, contiguous, "
                "and match list order 1..%d" % (label, len(instructions))
            )
        for index, record in enumerate(instructions, 1):
            if not isinstance(record, dict):
                continue
            order = record.get("order")
            dependencies = record.get("depends_on")
            if not isinstance(dependencies, list):
                continue
            for dependency in dependencies:
                if (not isinstance(dependency, str) or
                        not WORK_SPEC_RECORD_ID_RE.fullmatch(dependency)):
                    continue
                dependency_order = instruction_by_id.get(dependency)
                if dependency_order is None:
                    errors.append(
                        "%s Work Spec instructions[%d].depends_on references "
                        "unknown instruction %r" % (label, index, dependency)
                    )
                elif (isinstance(order, int) and not isinstance(order, bool) and
                      (not isinstance(dependency_order, int) or
                       isinstance(dependency_order, bool) or
                       dependency_order >= order)):
                    errors.append(
                        "%s Work Spec instructions[%d].depends_on must "
                        "reference only earlier instructions; %r has order %r" %
                        (label, index, dependency, dependency_order)
                    )

    if isinstance(conditions, list):
        for index, record in enumerate(conditions, 1):
            if not isinstance(record, dict):
                continue
            errors.extend(_work_spec_target_scope_errors(
                record.get("target_scope"), scope_manifest,
                "%s Work Spec acceptance_conditions[%d].target_scope" %
                (label, index)))
            for field in ("observable_predicate", "evidence_requirement"):
                if not _nonempty_string(record.get(field)):
                    errors.append(
                        "%s Work Spec acceptance_conditions[%d].%s must be "
                        "a non-empty string" % (label, index, field)
                    )

    if isinstance(constraints, list):
        for index, record in enumerate(constraints, 1):
            if not isinstance(record, dict):
                continue
            errors.extend(_work_spec_target_scope_errors(
                record.get("target_scope"), scope_manifest,
                "%s Work Spec constraints[%d].target_scope" %
                (label, index)))
            if not _nonempty_string(record.get("requirement")):
                errors.append(
                    "%s Work Spec constraints[%d].requirement must be a "
                    "non-empty string" % (label, index)
                )

    sentinel_paths = _work_spec_sentinel_paths(metadata)
    if sentinel_paths:
        errors.append(
            "%s Work Spec contains unfilled template sentinel(s) at: %s" %
            (label, ", ".join(sentinel_paths))
        )
    return errors


def _selected_profile_manifest_envelope_errors(profile):
    """Reject a selected-Profile reference outside the runtime envelope.

    This check is deliberately lexical: ordinary runtime admission must not
    read Profile bytes before the one authoritative ``profile-load`` producer
    binds them.  The smaller corrective-adoption guard below adds its own
    identity/sentinel reads because that explicit escape must remain usable
    when the current transitive closure is already invalid.
    """
    if not _nonempty_string(profile):
        return ["selected_profile_manifest must be instantiated"]
    parts = Path(profile).parts
    if len(parts) != 3 or parts[0] != "profiles" or parts[2] != "profile.md":
        return ["selected_profile_manifest must be profiles/<id>/profile.md"]
    return []


def selected_profile_manifest_errors(root, profile):
    """Reject template/example/unfilled manifests as runtime identities.

    Full profile quality remains owned by ``check_profile.py``.  This small
    persistent guard enforces the mechanical facts a resumed Queue must never
    forget: the selected package is an adopter-owned profile ID, not a shipped
    form/example, and its identity/sentinel state is instantiated.
    """
    errors = _selected_profile_manifest_envelope_errors(profile)
    if errors:
        return errors
    parts = Path(profile).parts
    profile_id = parts[1]
    reserved = {
        "_template", "template", "example", "examples", "REPLACE-ME",
        "your-profile-id", "TODO",
    }
    sentinel = "TODO(profile)"
    defaults_path = os.path.join(
        os.path.realpath(os.path.abspath(root)),
        "Tools/schemas/execution_defaults.template.yaml",
    )
    if os.path.isfile(defaults_path):
        try:
            defaults = kblib.load_yaml_file(defaults_path)
            reserved.update(str(value) for value in
                            (defaults.get("reserved_profile_ids") or []))
            sentinel = str(defaults.get("unfilled_sentinel") or sentinel)
        except (OSError, ValueError, kblib.YamlSubsetError) as exc:
            errors.append("selected profile default registry is unreadable: %s" %
                          exc)
    if profile_id in reserved or profile_id.startswith("_"):
        errors.append("selected_profile_manifest uses reserved/non-runnable "
                      "profile id %r" % profile_id)
    try:
        profile_snapshot = kblib.repository_tree_snapshot(
            root, os.path.dirname(profile))
        manifest_text = profile_snapshot.read_text(profile)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append("selected_profile_manifest is unsafe or missing: %s" % exc)
        return errors
    _, identity_errors = kblib.profile_identity(
        manifest_text, profile_id, reserved)
    for _, details in identity_errors:
        errors.append("selected profile identity: %s" % details)
    try:
        hits, _, _ = check_profile.scan_sentinel(profile_snapshot, sentinel)
    except (OSError, UnicodeError) as exc:
        errors.append("selected profile cannot be scanned for unfilled "
                      "sentinels: %s" % exc)
    else:
        if hits:
            sample = ", ".join("%s:%d" % hit for hit in hits[:3])
            errors.append("selected profile is not runnable; unfilled sentinel "
                          "%r remains at %s" % (sentinel, sample))
    return errors


def profile_load_authorized_view(root, profile):
    """Run ``profile-load`` once and retain its snapshot-bound consumer view.

    The public evidence fields bind the selected manifest, complete Profile
    tree, and typed dependency graph.  ``_manifest_slot_paths`` is an internal
    projection of that *same* authorized contract; it lets runtime consumers
    locate a slot without reparsing the manifest under a later revision.

    ``evaluate_profile_load`` returns the contract, snapshot, fingerprint, and
    summary from one producer invocation.  Consumers must not reconstruct the
    contract in a second parse: doing so could pair the verdict for revision A
    with revision B's dependency graph.
    """
    errors = _selected_profile_manifest_envelope_errors(profile)
    if errors or not _nonempty_string(profile):
        return None, errors

    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    profile_dir = os.path.join(
        root, os.path.dirname(profile).replace("/", os.sep))
    try:
        evaluation = check_profile.evaluate_profile_load(
            profile_dir, root=root, receipt_identity=None)
    except (OSError, SystemExit, TypeError, UnicodeError, ValueError) as exc:
        errors.append("profile-load producer could not run: %s" % exc)
        return None, errors

    if not evaluation.authorized:
        findings = [
            "[%s %s] %s — %s" % (
                str(receipt.get("result", "fail")).upper(),
                receipt.get("check", "profile-load"),
                receipt.get("target", profile),
                receipt.get("details", "profile-load was not authorized"),
            )
            for receipt in evaluation.findings[:5]
        ]
        detail = "; ".join(findings) if findings else \
            "check_profile exited %d without an authorized contract" % \
            evaluation.exit_code
        errors.append("selected Profile failed profile-load: %s" % detail)
        return None, errors

    contract = evaluation.contract
    summary = evaluation.summary_receipt
    if (not isinstance(contract,
                       check_profile.profile_contract.ProfileContract) or
            not contract.authorized):
        return None, ["profile-load pass exposed no authorized typed contract"]
    if not isinstance(summary, dict):
        return None, ["profile-load pass exposed no summary receipt"]
    if contract.manifest_repo_path != profile:
        errors.append(
            "profile-load selected manifest %r, expected %r" %
            (contract.manifest_repo_path, profile))
    if summary.get("selected_profile_manifest") != profile:
        errors.append(
            "profile-load summary selected manifest %r, expected %r" %
            (summary.get("selected_profile_manifest"), profile))

    if errors:
        return None, errors
    snapshot = evaluation.profile_snapshot_sha256
    if (not isinstance(snapshot, str) or
            not SHA256_RE.fullmatch(snapshot)):
        return None, ["profile-load did not authorize a canonical Profile "
                      "snapshot fingerprint"]
    bound_snapshot = evaluation.profile_snapshot
    if (not isinstance(bound_snapshot, kblib.RepositoryTreeSnapshot) or
            bound_snapshot.sha256 != snapshot or
            os.path.realpath(bound_snapshot.root) != root or
            bound_snapshot.relative_directory != contract.profile_repo_dir):
        return None, ["profile-load did not expose the immutable Profile "
                      "snapshot that authorized its typed contract"]
    fingerprint = evaluation.profile_contract_fingerprint
    if (not isinstance(fingerprint, str) or
            not SHA256_RE.fullmatch(fingerprint)):
        return None, ["profile-load did not authorize a typed contract "
                      "fingerprint"]
    inputs_fingerprint = evaluation.profile_load_inputs_sha256
    if (not isinstance(inputs_fingerprint, str) or
            not SHA256_RE.fullmatch(inputs_fingerprint)):
        return None, ["profile-load did not bind its canonical normative "
                      "input bytes"]
    for field, expected in (
            ("profile_snapshot_sha256", snapshot),
            ("profile_contract_fingerprint", fingerprint),
            ("profile_load_inputs_sha256", inputs_fingerprint)):
        if summary.get(field) != expected:
            return None, ["profile-load summary %s differs from the "
                          "authorized evaluation" % field]

    slot_paths = {}
    for edge in contract.dependency_edges:
        if edge.kind != "manifest-slot":
            continue
        if (not _nonempty_string(edge.owner_id) or
                not _nonempty_string(edge.path)):
            return None, ["profile-load authorized a malformed manifest-slot "
                          "dependency edge"]
        if edge.owner_id in slot_paths:
            return None, ["profile-load authorized duplicate manifest-slot "
                          "dependency edges for %r" % edge.owner_id]
        slot_paths[edge.owner_id] = edge.path
    if EXPRESSION_LAYER_SLOT not in slot_paths:
        return None, ["profile-load authorized no manifest-slot dependency "
                      "edge for %s" % EXPRESSION_LAYER_SLOT]

    return {
        "selected_profile_manifest": profile,
        "profile_snapshot_sha256": snapshot,
        "profile_contract_fingerprint": fingerprint,
        "profile_load_inputs_sha256": inputs_fingerprint,
        "_manifest_slot_paths": tuple(sorted(slot_paths.items())),
        "_contract": contract,
        "_profile_snapshot": bound_snapshot,
        "_evaluation": evaluation,
    }, []


def _public_profile_load_evidence(authorized_view):
    """Project an internal authorized view into durable evidence fields."""
    return {
        field: authorized_view[field]
        for field in (
            "selected_profile_manifest", "profile_snapshot_sha256",
            "profile_contract_fingerprint", "profile_load_inputs_sha256",
        )
    }


def active_standards_authorized_view(root, standards_version,
                                     selected_profile_manifest,
                                     state_override=None):
    """Return one immutable approved adopter-state view and its errors."""
    state, view, errors = standards_state.snapshot(
        root, override_text=state_override)
    errors = ["active Standards state: %s" % error for error in errors]
    if state is None:
        return None, errors
    if state.get("standards_version") != standards_version:
        errors.append(
            "runtime standards_version %r differs from active state %r" %
            (standards_version, state.get("standards_version")))
    if (state.get("selected_profile_manifest") !=
            selected_profile_manifest):
        errors.append(
            "runtime selected_profile_manifest %r differs from active "
            "state %r" %
            (selected_profile_manifest,
             state.get("selected_profile_manifest")))
    if errors:
        return None, errors
    return view, []


def active_standards_alignment_errors(root, standards_version,
                                      selected_profile_manifest):
    """Compare runtime identity to the canonical adopter Standards state."""
    _view, errors = active_standards_authorized_view(
        root, standards_version, selected_profile_manifest)
    return errors


def active_standards_view_currency_errors(root, authorized_view,
                                          state_override=None):
    """Fail when current-state bytes no longer equal an authorized view."""
    if not isinstance(authorized_view, dict):
        return ["active Standards authorized view must be a mapping"]
    expected = authorized_view.get("active_standards_sha256")
    view, errors = active_standards_authorized_view(
        root, authorized_view.get("standards_version"),
        authorized_view.get("selected_profile_manifest"),
        state_override=state_override)
    if errors:
        return errors
    if view.get("active_standards_sha256") != expected:
        return [
            "active Standards state changed after identity admission; "
            "rerun against one stable state revision"
        ]
    return []


def profile_load_evidence(root, profile):
    """Run ``profile-load`` and return one stable, receipt-free identity.

    The returned mapping is deliberately an in-memory value, not a Gate
    receipt.  Standards adoption judges a candidate *after* Profile while the
    Required Queue still names the current Profile; publishing that candidate
    receipt into the current receipt catalog would therefore combine two
    different task identities.  The eventual selected task must produce its
    own ``profile-load`` receipt after the adoption commits.

    Slot consumers inside this module use the authorized-view API so
    their source paths come from the same producer invocation.  External
    callers receive only the three durable identity fields.
    """
    authorized_view, errors = profile_load_authorized_view(root, profile)
    if authorized_view is None:
        return None, errors
    return _public_profile_load_evidence(authorized_view), errors


def profile_load_errors(root, profile):
    """Return the canonical ``profile-load`` admission failures.

    Default runtime consistency and every candidate after-image use this full
    producer.  :func:`selected_profile_manifest_errors` remains only as the
    smaller identity/sentinel check behind the explicit corrective-adoption
    escape, so a broken current closure can be replaced without weakening any
    ordinary reader, writer, or proposed state.
    """
    _authorized_view, errors = profile_load_authorized_view(root, profile)
    return errors




def _unadmitted_profile_hub_paths(root, profile_manifest):
    """Derive hub pages for the explicit corrective-adoption escape only.

    Ordinary runtime consumers must use :func:`profile_hub_paths`, whose slot
    path comes from one authorized typed contract.  This raw manifest reader
    survives only so ``adopt_standards`` can inspect and replace an invalid
    current Profile without requiring that broken closure to authorize itself.
    """
    paths = set()
    if not _nonempty_string(profile_manifest):
        return paths, []
    parts = Path(profile_manifest).parts
    if len(parts) < 3 or parts[0] != "profiles" or parts[-1] != "profile.md":
        # The exact runtime shape is owned by
        # selected_profile_manifest_errors; this only refuses to read a
        # package that is not a profile manifest at all.
        return paths, []
    try:
        manifest_path = kblib.repository_path(
            root, profile_manifest, must_exist=True, reject_symlink=True)
        manifest_text = check_profile.read_text(manifest_path)
    except (OSError, UnicodeError, ValueError) as exc:
        return paths, ["selected profile manifest is unreadable, so the "
                       "K13/10 hub set cannot be derived: %s" % exc]
    binding = kblib.profile_slot_bindings(manifest_text).get(
        EXPRESSION_LAYER_SLOT)
    if not _nonempty_string(binding):
        # No slot binding at all: the profile registers no expression hub.
        return paths, []
    profile_dir = os.path.dirname(manifest_path)
    kind, detail = kblib.resolve_profile_binding(binding, root, profile_dir)
    if kind != "path":
        return paths, [
            "selected profile %s binding is %s, so the K13/10 hub set cannot "
            "be derived" % (EXPRESSION_LAYER_SLOT, kind)
        ]
    try:
        text = check_profile.read_text(detail)
    except (OSError, UnicodeError, ValueError) as exc:
        return paths, ["selected profile %s is unreadable, so the K13/10 hub "
                       "set cannot be derived: %s" % (EXPRESSION_LAYER_SLOT,
                                                      exc)]
    for cells in check_profile.table_rows(text.splitlines()):
        if len(cells) != 2:
            continue
        label = check_profile.unbacktick(cells[0]).strip().lower()
        if not label.startswith(HUB_DEPENDENCY_MAP_LABEL):
            continue
        for declared in cells[1].split(";"):
            candidate = _normalized_repository_path(declared)
            if candidate is None or candidate.lower() == "none":
                continue
            if "TODO(" in candidate or "/" not in candidate:
                # An unfilled sentinel or an opaque artifact ID is not a
                # decidable repository path; check_profile owns that verdict.
                continue
            if _path_error(root, candidate, must_exist=False) is None:
                paths.add(candidate)
    return paths, []


def _profile_view_snapshot_error(root, authorized_view, phase):
    """Return a fail-closed error if an authorized view is no longer current."""
    manifest = authorized_view.get("selected_profile_manifest")
    expected = authorized_view.get("profile_snapshot_sha256")
    if (not _nonempty_string(manifest) or not isinstance(expected, str) or
            not SHA256_RE.fullmatch(expected)):
        return "authorized Profile view has malformed snapshot identity"
    profile_dir = os.path.dirname(manifest).replace("/", os.sep)
    try:
        actual = kblib.repository_tree_sha256(root, profile_dir)
    except (OSError, ValueError) as exc:
        return ("selected Profile cannot be rebound %s Expression hub "
                "derivation: %s" % (phase, exc))
    if actual != expected:
        return ("selected Profile changed after profile-load authorization; "
                "snapshot mismatch %s Expression hub derivation" % phase)
    expected_inputs = authorized_view.get("profile_load_inputs_sha256")
    try:
        _snapshots, actual_inputs = \
            check_profile.canonical_profile_load_inputs(root)
    except (OSError, ValueError) as exc:
        return ("canonical profile-load inputs cannot be rebound %s "
                "Expression hub derivation: %s" % (phase, exc))
    if actual_inputs != expected_inputs:
        return ("canonical profile-load inputs changed after profile-load "
                "authorization; input mismatch %s Expression hub "
                "derivation" % phase)
    return None


def _authorized_profile_view_errors(root, profile_manifest, authorized_view):
    """Validate one in-process view without rerunning ``profile-load``."""
    if not isinstance(authorized_view, dict):
        return ["authorized Profile view must be a mapping returned by "
                "profile_load_authorized_view"]
    errors = []
    if authorized_view.get("selected_profile_manifest") != profile_manifest:
        errors.append("authorized Profile view selects %r, not %r" % (
            authorized_view.get("selected_profile_manifest"),
            profile_manifest))
    snapshot = authorized_view.get("profile_snapshot_sha256")
    if not isinstance(snapshot, str) or not SHA256_RE.fullmatch(snapshot):
        errors.append("authorized Profile view has malformed snapshot identity")
    fingerprint = authorized_view.get("profile_contract_fingerprint")
    if (not isinstance(fingerprint, str) or
            not SHA256_RE.fullmatch(fingerprint)):
        errors.append("authorized Profile view has malformed typed-contract "
                      "fingerprint")
    inputs_fingerprint = authorized_view.get("profile_load_inputs_sha256")
    if (not isinstance(inputs_fingerprint, str) or
            not SHA256_RE.fullmatch(inputs_fingerprint)):
        errors.append("authorized Profile view has malformed canonical-input "
                      "fingerprint")

    contract = authorized_view.get("_contract")
    contract_type = check_profile.profile_contract.ProfileContract
    if not isinstance(contract, contract_type) or not contract.authorized:
        errors.append("authorized Profile view has no authorized typed "
                      "contract object")
        contract = None
    elif os.path.realpath(contract.root) != \
            os.path.realpath(os.path.abspath(os.fspath(root))):
        errors.append("authorized Profile view belongs to a different "
                      "repository root")
    else:
        if contract.manifest_repo_path != profile_manifest:
            errors.append("authorized Profile contract selects %r, not %r" % (
                contract.manifest_repo_path, profile_manifest))
        if contract.profile_contract_fingerprint != fingerprint:
            errors.append("authorized Profile view fingerprint differs from "
                          "its typed contract")

    bound_snapshot = authorized_view.get("_profile_snapshot")
    if not isinstance(bound_snapshot, kblib.RepositoryTreeSnapshot):
        errors.append("authorized Profile view has no immutable Profile "
                      "snapshot object")
    else:
        expected_directory = os.path.dirname(profile_manifest)
        if (bound_snapshot.sha256 != snapshot or
                os.path.realpath(bound_snapshot.root) !=
                os.path.realpath(os.path.abspath(os.fspath(root))) or
                bound_snapshot.relative_directory != expected_directory):
            errors.append("authorized Profile immutable snapshot identity "
                          "differs from its public binding")

    evaluation = authorized_view.get("_evaluation")
    if (not isinstance(evaluation, check_profile.ProfileLoadEvaluation) or
            not evaluation.authorized):
        errors.append("authorized Profile view has no authorized evaluation "
                      "object")
    else:
        if (evaluation.contract is not contract or
                evaluation.profile_snapshot is not bound_snapshot):
            errors.append("authorized Profile evaluation objects differ from "
                          "its typed contract or immutable snapshot")
        for field in (
                "profile_snapshot_sha256",
                "profile_contract_fingerprint",
                "profile_load_inputs_sha256"):
            if getattr(evaluation, field) != authorized_view.get(field):
                errors.append("authorized Profile evaluation %s differs "
                              "from its public binding" % field)

    projected_pairs = ()
    try:
        projected_pairs = tuple(authorized_view["_manifest_slot_paths"])
        projected = dict(projected_pairs)
        if (len(projected) != len(projected_pairs) or
                any(not _nonempty_string(key) or
                    not _nonempty_string(value)
                    for key, value in projected_pairs)):
            raise ValueError("malformed or duplicate manifest-slot edge")
    except (KeyError, TypeError, ValueError):
        errors.append("authorized Profile view has no immutable manifest-slot "
                      "projection")
        projected = {}

    if contract is not None:
        contract_pairs = tuple(sorted(
            (edge.owner_id, edge.path)
            for edge in contract.dependency_edges
            if edge.kind == "manifest-slot"
        ))
        if projected_pairs != contract_pairs:
            errors.append("authorized Profile manifest-slot projection differs "
                          "from its typed contract")
    if not _nonempty_string(projected.get(EXPRESSION_LAYER_SLOT)):
        errors.append("authorized Profile view has no %s path" %
                      EXPRESSION_LAYER_SLOT)

    if not errors:
        snapshot_error = _profile_view_snapshot_error(
            root, authorized_view, "before")
        if snapshot_error:
            errors.append(snapshot_error)
    return errors


def profile_load_authorized_view_currency_errors(root, authorized_view):
    """Rebind a previously authorized Profile view without rerunning producer."""
    manifest = authorized_view.get("selected_profile_manifest") \
        if isinstance(authorized_view, dict) else None
    if not _nonempty_string(manifest):
        return ["authorized Profile view has no selected manifest identity"]
    return _authorized_profile_view_errors(root, manifest, authorized_view)


def runtime_authority_context(result):
    """Freeze one successful runtime admission for a complete transaction.

    Ordinary writers call :func:`validate_runtime` once without injected
    views, then carry this opaque context through every proposed, locked, and
    post-write validation.  The Profile and K00/03 views are deliberately kept
    together: accepting a view from one admission and an active-Standards
    binding from another would recreate the split-revision window this API is
    intended to close.
    """
    if not isinstance(result, dict):
        raise TypeError("runtime validation result must be a mapping")
    if result.get("errors"):
        raise ValueError(
            "runtime authority context requires a successful validation")
    root = result.get("root")
    queue = result.get("queue")
    profile_view = result.get("_profile_authorized_view")
    active_view = result.get("_active_standards_authorized_view")
    if not _nonempty_string(root) or not isinstance(queue, dict):
        raise ValueError("runtime validation result has no canonical root or Queue")
    if not isinstance(profile_view, dict):
        raise ValueError("runtime validation result has no authorized Profile view")
    if not isinstance(active_view, dict):
        raise ValueError(
            "runtime validation result has no authorized active Standards view")
    expected_profile = queue.get("selected_profile_manifest")
    expected_standards = queue.get("standards_version")
    if (profile_view.get("selected_profile_manifest") != expected_profile or
            active_view.get("selected_profile_manifest") != expected_profile):
        raise ValueError(
            "runtime authority views do not select the validated Queue Profile")
    if active_view.get("standards_version") != expected_standards:
        raise ValueError(
            "runtime active Standards view does not select the validated "
            "Queue version")
    return {
        "root": os.path.realpath(os.path.abspath(root)),
        "profile_view": profile_view,
        "active_standards_view": active_view,
    }


def runtime_authority_validation_kwargs(context):
    """Return the indivisible view pair for a later runtime validation."""
    if not isinstance(context, dict):
        raise TypeError("runtime authority context must be a mapping")
    profile_view = context.get("profile_view")
    active_view = context.get("active_standards_view")
    if not isinstance(profile_view, dict) or not isinstance(active_view, dict):
        raise ValueError(
            "runtime authority context must contain both authorized views")
    return {
        "authorized_profile_view": profile_view,
        "authorized_active_standards_view": active_view,
    }


def runtime_authority_currency_errors(root, context):
    """Return CAS failures for every root authority bound by ``context``."""
    if not isinstance(context, dict):
        return ["runtime authority context must be a mapping"]
    canonical_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if context.get("root") != canonical_root:
        return ["runtime authority context belongs to a different repository root"]
    try:
        kwargs = runtime_authority_validation_kwargs(context)
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    errors = []
    for detail in active_standards_view_currency_errors(
            canonical_root, kwargs["authorized_active_standards_view"]):
        errors.append("active Standards authority: %s" % detail)
    for detail in profile_load_authorized_view_currency_errors(
            canonical_root, kwargs["authorized_profile_view"]):
        errors.append("Profile-load authority: %s" % detail)
    return errors


def require_runtime_authority_current(root, context, phase):
    """Raise when a transaction no longer sees its admitted authority bytes."""
    errors = runtime_authority_currency_errors(root, context)
    if errors:
        raise ValueError("%s: %s" % (phase, "; ".join(errors)))


def runtime_authority_lock_fields(context):
    """Project one transaction authority binding into writer-lock metadata."""
    kwargs = runtime_authority_validation_kwargs(context)
    profile_view = kwargs["authorized_profile_view"]
    active_view = kwargs["authorized_active_standards_view"]
    return {
        "standards_version": active_view.get("standards_version"),
        "active_standards_sha256": active_view.get(
            "active_standards_sha256"),
        "selected_profile_manifest": profile_view.get(
            "selected_profile_manifest"),
        "profile_snapshot_sha256": profile_view.get(
            "profile_snapshot_sha256"),
        "profile_contract_fingerprint": profile_view.get(
            "profile_contract_fingerprint"),
        "profile_load_inputs_sha256": profile_view.get(
            "profile_load_inputs_sha256"),
    }


def profile_hub_paths(root, profile_manifest, *, authorized_view=None,
                      evaluate_if_missing=True,
                      allow_unadmitted_profile=False):
    """Return Expression hubs from one snapshot-bound Profile view.

    K13/10 binds pages registered by the ``Expression Layer Entry`` into the
    hub set.  The slot path is taken from the typed dependency edges produced
    by the same ``profile-load`` invocation as ``authorized_view``; the
    manifest is never reparsed.  The complete Profile tree is CAS-checked
    before and after reading the slot, so a verdict for revision A cannot be
    combined with Expression rows from revision B.

    Direct callers may omit ``authorized_view`` and this function will create
    exactly one.  ``validate_runtime`` passes its already-created view and sets
    ``evaluate_if_missing=False`` so a failed producer is not run twice.  The
    unadmitted path is reserved for the explicit corrective-adoption escape.
    """
    if type(evaluate_if_missing) is not bool:
        raise TypeError("evaluate_if_missing must be boolean")
    if type(allow_unadmitted_profile) is not bool:
        raise TypeError("allow_unadmitted_profile must be boolean")
    if allow_unadmitted_profile:
        if authorized_view is not None:
            raise ValueError("corrective Profile hub derivation cannot accept "
                             "an authorized view")
        return _unadmitted_profile_hub_paths(root, profile_manifest)

    if not _nonempty_string(profile_manifest):
        return set(), []
    if authorized_view is None:
        if not evaluate_if_missing:
            # The caller already records the producer failure.  Do not create
            # a second observation window or duplicate its detailed
            # diagnostics.  Hub admission still fails closed: otherwise a
            # queued concurrent batch could be reported ready merely because
            # its selected Profile never produced an authorized view.
            return set(), ["selected Profile has no authorized view, so the "
                           "K13/10 hub set cannot be derived"]
        authorized_view, errors = profile_load_authorized_view(
            root, profile_manifest)
        if authorized_view is None:
            return set(), errors

    view_errors = _authorized_profile_view_errors(
        root, profile_manifest, authorized_view)
    if view_errors:
        return set(), view_errors
    slot_paths = dict(authorized_view["_manifest_slot_paths"])
    expression_path = slot_paths.get(EXPRESSION_LAYER_SLOT)
    try:
        text = authorized_view["_profile_snapshot"].read_text(
            expression_path)
    except (KeyError, OSError, UnicodeError, ValueError) as exc:
        return set(), ["authorized selected profile %s is unreadable, so the "
                       "K13/10 hub set cannot be derived: %s" % (
                           EXPRESSION_LAYER_SLOT, exc)]
    after_error = _profile_view_snapshot_error(root, authorized_view, "after")
    if after_error:
        return set(), [after_error]

    paths = set()
    for cells in check_profile.table_rows(text.splitlines()):
        if len(cells) != 2:
            continue
        label = check_profile.unbacktick(cells[0]).strip().lower()
        if not label.startswith(HUB_DEPENDENCY_MAP_LABEL):
            continue
        for declared in cells[1].split(";"):
            candidate = _normalized_repository_path(declared)
            if candidate is None or candidate.lower() == "none":
                continue
            if "TODO(" in candidate or "/" not in candidate:
                continue
            if _path_error(root, candidate, must_exist=False) is None:
                paths.add(candidate)
    return paths, []


def _page_frontmatter(root, relative_path):
    """Return ``(exists, fields, error)`` for one repository page.

    ``fields`` is ``None`` when the page exists but its metadata cannot be
    read, which the caller reports instead of treating as "not a hub".
    """
    try:
        absolute = kblib.repository_path(root, relative_path)
    except (OSError, ValueError) as exc:
        return False, None, "path is unsafe: %s" % exc
    if os.path.islink(absolute) or not os.path.isfile(absolute):
        return False, {}, None
    try:
        with open(absolute, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        return True, None, "page is unreadable: %s" % exc
    raw = kblib.extract_frontmatter(text)
    if raw is None:
        if text.startswith("---\n") or text.startswith("---\r\n"):
            return True, None, "frontmatter has no closing fence"
        return True, {}, None
    try:
        fields = kblib.parse_yaml_subset(raw)
    except (ValueError, kblib.YamlSubsetError) as exc:
        return True, None, "frontmatter is unparsable: %s" % exc
    if not isinstance(fields, dict):
        return True, None, "frontmatter is not a mapping"
    return True, fields, None


def _hub_basis(fields):
    """Name the K13/10 hub role a page's own metadata proves, or ``None``."""
    page_type = fields.get("type")
    if page_type in HUB_PAGE_TYPES:
        return "type=%s" % page_type
    if page_type == HUB_TERM_TYPE and fields.get("scope") == HUB_TERM_SCOPE:
        return "type=%s scope=%s" % (HUB_TERM_TYPE, HUB_TERM_SCOPE)
    return None


def hub_page_admission(root, manifest, records, registered_hub_paths, cache):
    """Classify one batch manifest against K13/10 admission condition 2.

    The kernel forbids a concurrently admitted batch from *editing* a control
    or hub page.  A hub page that already exists is an edit and blocks
    activation; a hub page this batch creates is not, and is reported as a
    candidate for the integrator's post-merge hub synchronization step.  This
    only reports what the bytes say; choosing the execution mode is the
    integrator's decision.
    """
    blocking = []
    candidates = []
    unresolved = []
    for path in sorted(set(manifest or [])):
        if not _nonempty_string(path):
            continue
        if path not in cache:
            cache[path] = _page_frontmatter(root, path)
        exists, fields, error = cache[path]
        registered = path in registered_hub_paths
        if error is not None:
            if exists and registered:
                blocking.append("%s (%s)" % (path, EXPRESSION_LAYER_SLOT))
            else:
                unresolved.append("%s (%s)" % (path, error))
            continue
        if exists:
            basis = _hub_basis(fields)
            if registered:
                basis = EXPRESSION_LAYER_SLOT if basis is None else basis
            if basis is not None:
                blocking.append("%s (%s)" % (path, basis))
            continue
        declared = records.get(path) or {}
        basis = None
        if declared.get("type") in HUB_PAGE_TYPES:
            basis = "Coverage type=%s" % declared.get("type")
        elif registered:
            basis = EXPRESSION_LAYER_SLOT
        if basis is not None:
            candidates.append("%s (%s)" % (path, basis))
    return {
        "blocking": blocking,
        "candidates": candidates,
        "unresolved": unresolved,
    }






def _coverage_records(root, coverage, errors):
    pages = coverage.get("pages")
    if not isinstance(pages, list):
        errors.append("Coverage pages must be an explicit list")
        return {}, {}
    records = {}
    assignments = {}
    for index, page in enumerate(pages):
        label = "Coverage pages[%d]" % index
        if not isinstance(page, dict):
            errors.append("%s must be a mapping" % label)
            continue
        core_fields = (
            "path", "coverage_disposition", "canonical_owner",
            "prerequisites", "batch", "next_batch", "deferred_reason",
            "reentry_condition", "gate_receipts",
        )
        missing = [field for field in core_fields if field not in page]
        if missing:
            errors.append("%s misses core field(s): %s" %
                          (label, ", ".join(missing)))
        path = page.get("path")
        if not _nonempty_string(path):
            errors.append("%s path must be a non-empty string" % label)
            continue
        if path in records:
            errors.append("Coverage repeats object path %s" % path)
            continue
        path_error = _path_error(root, path, must_exist=False)
        if path_error:
            errors.append("%s path %r is unsafe: %s" % (label, path, path_error))
        records[path] = page
        disposition = page.get("coverage_disposition")
        if disposition not in COVERAGE_DISPOSITIONS:
            errors.append("%s coverage_disposition must be one of %s; found %r" %
                          (label, ", ".join(sorted(COVERAGE_DISPOSITIONS)),
                           disposition))
        if not _nonempty_string(page.get("canonical_owner")):
            errors.append("%s canonical_owner must be a non-empty string" % label)
        for field in ("prerequisites", "gate_receipts"):
            values = page.get(field)
            if (not isinstance(values, list) or
                    not all(_nonempty_string(value) for value in values)):
                errors.append("%s %s must be an explicit string list" %
                              (label, field))
            elif len(values) != len(set(values)):
                errors.append("%s %s must not contain duplicates" %
                              (label, field))
        for field in ("batch", "next_batch", "deferred_reason",
                      "reentry_condition"):
            value = page.get(field)
            if value is not None and not _nonempty_string(value):
                errors.append("%s %s must be null or a non-empty string" %
                              (label, field))
        if disposition in ("deferred", "excluded") and not _nonempty_string(
                page.get("deferred_reason")):
            errors.append("%s %s disposition requires a reason or scope basis" %
                          (label, disposition))
        if disposition == "deferred" and not _nonempty_string(
                page.get("reentry_condition")):
            errors.append("%s deferred disposition requires reentry_condition" %
                          label)
        batch_ids = []
        for key in ("batch", "next_batch"):
            value = page.get(key)
            if value is None or value == "":
                continue
            if not _nonempty_string(value):
                errors.append("%s %s must be a string or null" % (label, key))
                continue
            if value not in batch_ids:
                batch_ids.append(value)
        assignments[path] = batch_ids
        if page.get("coverage_disposition") == "required" and not batch_ids:
            errors.append("Required Coverage object %s has no batch/next_batch assignment" %
                          path)
    return records, assignments






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


def _coverage_batch_spec_errors(coverage, items_by_id):
    """Detect direct edits to canonical compiler inputs after materialization."""
    errors = []
    specs = coverage.get("batch_specs")
    if not isinstance(specs, list):
        return ["Coverage batch_specs must be an explicit list"]
    seen = set()
    field_map = {
        "family": "family",
        "source_route": "source_route",
        "execution_mode": "execution_mode",
        "depends_on": "depends_on",
        "confirmation_required": "confirmation_required",
        "work_spec_path": "work_spec_path",
        "work_spec_sha256": "work_spec_sha256",
    }
    for index, spec in enumerate(specs):
        label = "Coverage batch_specs[%d]" % index
        if not isinstance(spec, dict):
            errors.append("%s must be a mapping" % label)
            continue
        missing = sorted(COVERAGE_BATCH_SPEC_FIELDS - set(spec))
        extra = sorted(set(spec) - COVERAGE_BATCH_SPEC_FIELDS)
        if missing:
            errors.append("%s misses required field(s): %s" %
                          (label, ", ".join(missing)))
        if extra:
            errors.append("%s has unsupported field(s): %s" %
                          (label, ", ".join(extra)))
        errors.extend(_work_spec_binding_errors(
            spec.get("work_spec_path"), spec.get("work_spec_sha256"),
            label,
        ))
        batch_id = spec.get("id")
        if not _nonempty_string(batch_id) or not BATCH_ID_RE.fullmatch(batch_id):
            errors.append("%s id must be a valid batch id" % label)
            continue
        if batch_id in seen:
            errors.append("Coverage repeats batch spec %s" % batch_id)
            continue
        seen.add(batch_id)
        item = items_by_id.get(batch_id)
        if item is None:
            # Assignment reconciliation reports a current zero/unknown batch;
            # terminal history is allowed to omit its old spec, not vice versa.
            errors.append("Coverage batch spec %s has no Queue item" % batch_id)
            continue
        for spec_field, queue_field in field_map.items():
            if spec.get(spec_field) != item.get(queue_field):
                errors.append(
                    "Coverage batch spec %s %s=%r does not match Queue %r" %
                    (batch_id, spec_field, spec.get(spec_field),
                     item.get(queue_field)))
        order_hint = spec.get("order_hint")
        if (order_hint is not None and
                (not isinstance(order_hint, int) or isinstance(order_hint, bool) or
                 order_hint < 1)):
            errors.append("Coverage batch spec %s order_hint must be a positive "
                          "integer or null" % batch_id)
        elif order_hint is not None and order_hint != item.get("order"):
            errors.append(
                "Coverage batch spec %s order_hint=%r does not match Queue order=%r" %
                (batch_id, order_hint, item.get("order"))
            )
    for batch_id, item in items_by_id.items():
        if item.get("state") not in TERMINAL_STATES and batch_id not in seen:
            errors.append("non-terminal Queue item %s has no Coverage batch spec" %
                          batch_id)
    return errors


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
