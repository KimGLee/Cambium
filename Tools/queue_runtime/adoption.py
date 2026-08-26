"""Is one Standards adoption plan admissible, and is every persisted one bound.

Plan, record and commit receipt must bind to each other in both directions.
An adoption whose record exists without its commit receipt, or whose receipt
names a plan nobody registered, is the shape a partially applied adoption
leaves behind, and it is refused rather than repaired.
"""

import datetime

import kblib
import runtime_state_contract
import standards_state

from queue_runtime.canon import (
    ANY_PRODUCER_ERA_VERSION,
    QUEUE_PATH,
    SHA256_RE,
    STANDARDS_ADOPTION_PLAN_PREFIX,
    STANDARDS_ADOPTION_TOOL,
    STANDARDS_ADOPTION_TOOL_VERSION,
    TERMINAL_STATES,
    TOOL,
)
from queue_runtime.gate_registry import (
    is_revalidation_boundary_owner,
    partition_revalidation_owner_claims,
    projected_revalidation_owners,
    standards_gate_registry,
    standards_revalidation_capabilities,
)
from queue_runtime.item_history import invalidated_receipt_consumers
from queue_runtime.primitives import (
    closed_mapping_errors,
    explicit_string_list_errors,
    nonempty_string,
)
from queue_runtime.producer_era import (
    producer_era_errors,
    standards_adoption_owner_projection_required,
    standards_adoption_profile_contract_required,
    standards_adoption_profile_inputs_required,
    standards_adoption_state_file_required,
    standards_adoption_upstream_required,
    accounted_standards_versions,
)
from queue_runtime.profile_view import profile_load_evidence
from queue_runtime.receipts import require_receipt
from queue_runtime.repofs import _path_error
from queue_runtime.task_contract import (
    READ_SET_BOUNDARY_OWNER_PATH,
    read_set_load_closure,
)


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
        standards_adoption_profile_contract_required(producer_tool_version)
    profile_inputs_required = validate_current or \
        standards_adoption_profile_inputs_required(producer_tool_version)
    upstream_required = validate_current or \
        standards_adoption_upstream_required(producer_tool_version)
    owner_projection_era = validate_current or \
        standards_adoption_owner_projection_required(producer_tool_version)
    state_file_required = validate_current or \
        standards_adoption_state_file_required(producer_tool_version)
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
    errors = closed_mapping_errors(
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
        if not nonempty_string(plan.get(field)):
            errors.append("Standards adoption plan %s must be non-empty" % field)
    if (plan.get("task_state_before") not in
            runtime_state_contract.STANDARDS_ADOPTION_TASK_STATES):
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
                not nonempty_string(source) or
                not nonempty_string(revision)):
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
        errors.extend(explicit_string_list_errors(
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
        if nonempty_string(after_profile):
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
                path_error_message = _path_error(root, relative, must_exist=True)
                if path_error_message:
                    errors.append("Standards adoption %s path %r is unsafe or "
                                  "missing: %s" % (field, relative, path_error_message))

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
        errors.extend(closed_mapping_errors(
            predicate, label, STANDARDS_CHANGED_PREDICATE_FIELDS))
        if not isinstance(predicate, dict):
            continue
        predicate_id = predicate.get("predicate_id")
        if not nonempty_string(predicate_id):
            errors.append("%s predicate_id must be non-empty" % label)
        else:
            predicate_ids.append(predicate_id)
        if predicate.get("change_kind") not in ("added", "removed", "modified"):
            errors.append("%s change_kind must be added, removed, or modified" %
                          label)
        owner = predicate.get("owner_path")
        if not nonempty_string(owner):
            errors.append("%s owner_path must be non-empty" % label)
        elif validate_current and root is not None:
            path_error_message = _path_error(root, owner, must_exist=True)
            if path_error_message:
                errors.append("%s owner_path is unsafe or missing: %s" %
                              (label, path_error_message))
        affected = predicate.get("affected_gate_ids")
        errors.extend(explicit_string_list_errors(
            affected, "%s affected_gate_ids" % label))
        if isinstance(affected, list):
            if not affected:
                errors.append("%s affected_gate_ids must be non-empty" % label)
            if affected != sorted(affected):
                errors.append("%s affected_gate_ids must be sorted" % label)
            registered_gate_ids.update(value for value in affected
                                       if nonempty_string(value))
            if validate_current and root is not None:
                projected, projection_errors = projected_revalidation_owners(
                    affected, revalidation_capabilities)
                errors.extend("%s: %s" % (label, error)
                              for error in projection_errors)
                if nonempty_string(predicate_id):
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
                    if (nonempty_string(value) and
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
        errors.extend(closed_mapping_errors(
            boundary, label, STANDARDS_INVALIDATION_BOUNDARY_FIELDS))
        if not isinstance(boundary, dict):
            continue
        boundary_id = boundary.get("boundary_id")
        if not nonempty_string(boundary_id):
            errors.append("%s boundary_id must be non-empty" % label)
        else:
            boundary_ids.append(boundary_id)
        if boundary.get("target_kind") not in target_kinds:
            errors.append("%s target_kind is invalid" % label)
        for field in ("predicate_ids", "target_ids", "required_gate_ids"):
            values = boundary.get(field)
            errors.extend(explicit_string_list_errors(
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
            if nonempty_string(value)
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
                if not is_revalidation_boundary_owner(capability):
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
        if nonempty_string(boundary_id):
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
            if nonempty_string(boundary_id):
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
                nonempty_string(predicate.get("predicate_id")) and
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
                    nonempty_string(predicate.get("predicate_id")) and
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
                    if nonempty_string(gate_id) and gate_id != "profile-load"
                }
                for predicate in predicates
                if (isinstance(predicate, dict) and
                    nonempty_string(predicate.get("predicate_id")) and
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
                if nonempty_string(gate_id)
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
        errors.extend(closed_mapping_errors(
            evidence, label, STANDARDS_INVALIDATED_EVIDENCE_FIELDS))
        if not isinstance(evidence, dict):
            continue
        receipt_id = evidence.get("receipt_id")
        if not nonempty_string(receipt_id):
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
            errors.extend(explicit_string_list_errors(
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
            if nonempty_string(boundary_id):
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
            if not nonempty_string(boundary_id) or boundary_id in enforced:
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

    # Canonical Read Set machine declarations are transitively closed over
    # their declared Read Set edges, and every non-Read-Set target in that
    # closure belongs in the declared module load set. The obligations are
    # containment, not equality: additional tool and profile paths remain
    # legitimate.
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
            if nonempty_string(value)
        } if isinstance(declared_values, list) else set()
        selected_values = plan.get("selected_read_sets_after")
        selected = {
            value for value in selected_values
            if nonempty_string(value)
        } if isinstance(selected_values, list) else set()
        read_sets, modules, invalid_selected, closure_errors = \
            read_set_load_closure(
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
                if nonempty_string(row.get("batch_id"))
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


def standards_adoption_errors(
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
        receipt = require_receipt(
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
            standards_adoption_profile_contract_required(
                producer_tool_version)
        profile_inputs_required = \
            standards_adoption_profile_inputs_required(
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
        if standards_adoption_upstream_required(producer_tool_version):
            for field in ("upstream_source_ref", "upstream_revision_id"):
                if field not in record:
                    errors.append(
                        "%s misses %s required by adopt_standards %s; the "
                        "distribution has no version numbers, so the "
                        "adoption record is what makes upstream and "
                        "downstream comparable" %
                        (label, field, producer_tool_version))
        state_file_required = standards_adoption_state_file_required(
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
            if isinstance(row, dict) and nonempty_string(row.get("predicate_id")))
        invalidated_ids = sorted(
            row.get("receipt_id")
            for row in plan.get("invalidated_evidence", [])
            if isinstance(row, dict) and nonempty_string(row.get("receipt_id")))
        boundary_ids = sorted(
            row.get("boundary_id") for row in plan.get("invalidation_boundaries", [])
            if isinstance(row, dict) and nonempty_string(row.get("boundary_id")))
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
        errors.extend(producer_era_errors(
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
                require_receipt(
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
