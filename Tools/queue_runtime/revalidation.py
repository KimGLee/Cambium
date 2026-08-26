"""Which Standards revalidation obligations are still owed.

Per-batch boundary bindings, the aggregate receipt and whether its producer
was eligible to write it, and the post-adoption evidence barrier.  An
obligation is discharged by a receipt from an eligible producer or it stands;
producer eligibility is not a formality here.
"""

import kblib

from queue_runtime.canon import (
    QUEUE_PATH,
    STANDARDS_ADOPTION_PLAN_PREFIX,
    STANDARDS_ADOPTION_TOOL,
    STANDARDS_ADOPTION_TOOL_VERSION,
    TERMINAL_STATES,
    TOOL,
    TOOL_VERSION,
)
from queue_runtime.gate_registry import (
    is_immediate_revalidation_owner,
    is_native_revalidation_owner,
    is_special_revalidation_owner,
    partition_revalidation_owner_claims,
    receipt_matches_gate_id,
    registered_gate_dimensions,
    registered_gate_position,
    standards_gate_registry,
    standards_revalidation_capabilities,
    standards_revalidation_owner,
)
from queue_runtime.item_history import (
    ordered_item_transitions,
    invalidated_receipt_consumers,
    walk_revalidation_hold,
)
from queue_runtime.primitives import (
    nonempty_string,
    timestamp_value,
)
from queue_runtime.producer_era import standards_adoption_owner_projection_required
from queue_runtime.receipts import (
    require_receipt,
    current_receipt_catalog,
    historical_receipt_catalog,
)


STANDARDS_REVALIDATION_CAPABILITY_PROTOCOL = "owner-projection-v1"


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
        if catalog is not None and nonempty_string(receipt_id):
            resolve = getattr(catalog, "resolve", None)
            if not callable(resolve):
                resolve = catalog.get
            entry = resolve(receipt_id)
            receipt = entry[1] if entry is not None else None
            if isinstance(receipt, dict) and \
                    receipt.get("tool") == STANDARDS_ADOPTION_TOOL:
                producer_tool_version = receipt.get("tool_version")
        owner_projection_era = \
            standards_adoption_owner_projection_required(
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
            nonempty_string(row.get("boundary_id"))
        }
        affected_by_predicate = {
            row.get("predicate_id"): [
                gate_id for gate_id in row.get("affected_gate_ids") or []
                if nonempty_string(gate_id)
            ]
            for row in plan.get("changed_predicates", [])
            if isinstance(row, dict) and
            nonempty_string(row.get("predicate_id"))
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
                if not nonempty_string(batch_id):
                    continue
                relevant_invalidated = sorted({
                    invalidated.get("receipt_id")
                    for invalidated in invalidated_by_boundary.get(
                        boundary_id, [])
                    if nonempty_string(invalidated.get("receipt_id")) and
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
                    if nonempty_string(invalidated.get("receipt_id")) and
                    (batch_id in (
                        invalidated.get("revalidation_scope_ids") or []) or
                     boundary.get("target_kind") == "batch")
                    for dimension in invalidated.get("dimension_ids") or []
                    if nonempty_string(dimension)
                })
                plan_required_gate_ids = [
                    gate_id for gate_id in
                    boundary.get("required_gate_ids") or []
                    if nonempty_string(gate_id)
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
                        if is_special_revalidation_owner(owner_capability):
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
    gate_registry, gate_errors = standards_gate_registry(result.get("root"))
    allowed_states = registered_gate_position(
        "standards-revalidation", gate_registry)
    if gate_errors or not isinstance(allowed_states, frozenset):
        return "Standards revalidation Gate position is unavailable"
    if item.get("state") not in allowed_states:
        return ("Standards revalidation batch %s is %s, expected %s" %
                (batch_id, item.get("state"),
                 " or ".join(sorted(allowed_states))))
    if item.get("state") == "open" and \
            item.get("hold_state") != "revalidation-required":
        return ("open Standards revalidation batch must have "
                "hold_state=revalidation-required")
    return None


def unresolvable_consumed_aggregate_errors(items_by_id, catalog):
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
        for transition in ordered_item_transitions(item, catalog):
            receipt_id = transition.get("standards_revalidation_receipt")
            if not nonempty_string(receipt_id) or \
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


def consumed_standards_revalidation_keys(item, catalog):
    consumed = set()
    transitions = ordered_item_transitions(item, catalog)
    if not transitions:
        return consumed
    # Sealing must not un-replay a consumption a Queue transition recorded.
    # This replay reads the aggregate's body, so it takes the K12/07 sealed
    # branch (`Catalog.resolve`) rather than the hot map alone; a reduced
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
        if not nonempty_string(receipt_id) and (
                transition.get("before_state") == transition.get("after_state")
                and transition.get("receipt_id") in discharges):
            receipt_id = transition.get("evidence_receipt")
        receipt_entry = resolve(receipt_id) if nonempty_string(
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
                not nonempty_string(receipt.get("tool_version")) or \
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
            if all(nonempty_string(value) for value in key):
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
    consumed = consumed_standards_revalidation_keys(
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
        if nonempty_string(row.get("required_gate_id"))
    })
    registry, registry_errors = standards_gate_registry(result.get("root"))
    errors.extend(registry_errors)
    capabilities, capability_errors = standards_revalidation_capabilities(
        result.get("root"), registry)
    errors.extend(capability_errors)
    for row in outstanding:
        if nonempty_string(row.get("mapping_error")):
            errors.append(row["mapping_error"])
    mapped_owner_gate_ids = sorted({
        row.get("mapped_owner_gate_id") for row in outstanding
        if nonempty_string(row.get("mapped_owner_gate_id"))
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
        entry = catalog.get(receipt_id) if nonempty_string(receipt_id) else None
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
        receipt_time = timestamp_value(receipt.get("checked_at"))
        relevant_times = [timestamp_value(row.get("adopted_at"))
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
        if is_immediate_revalidation_owner(capabilities.get(gate_id)))
    native_owner_gate_ids = sorted(
        gate_id for gate_id in mapped_owner_gate_ids
        if is_native_revalidation_owner(capabilities.get(gate_id)))
    deferred_native_owner_gate_ids = sorted(
        set(native_owner_gate_ids) & set(deferred_gate_ids))
    context = {
        "gate_id": "standards-revalidation",
        "batch_id": batch_id,
        "standards_adoption_ids": sorted({
            row.get("adoption_id") for row in outstanding
            if nonempty_string(row.get("adoption_id"))}),
        "standards_adoption_plan_sha256s": sorted({
            row.get("plan_sha256") for row in outstanding
            if nonempty_string(row.get("plan_sha256"))}),
        "invalidation_boundary_ids": sorted({
            row.get("boundary_id") for row in outstanding
            if nonempty_string(row.get("boundary_id"))}),
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
    receipt = require_receipt(
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
