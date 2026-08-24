"""Is the sole task-state history one complete, closed, append-only record.

Progress shape, the adoption record shape, the transition and restart
checkpoint, and the global transition invariant.  "Sole" is the load-bearing
word: every state change a tool makes is expected to appear here, so a shape
that admits an unrecorded transition admits an unrecorded change.
"""

import amendment_policy
import kblib

from queue_runtime.canon import (
    ANY_PRODUCER_ERA_VERSION,
    QUEUE_PATH,
    SHA256_RE,
    SUPPORTED_UPDATE_QUEUE_TOOL_VERSIONS,
    TASK_STATES,
    TERMINAL_PROOF_TOOL,
    TERMINAL_PROOF_TOOL_VERSION,
    TERMINAL_STATES,
    TOOL,
    TOOL_VERSION,
)
from queue_runtime.maintenance import (
    _maintenance_completion_gate_errors,
    _maintenance_gate_time_errors,
)
from queue_runtime.policy_exceptions import _policy_exception_errors
from queue_runtime.primitives import (
    _closed_mapping_errors,
    _explicit_string_list_errors,
    _nonempty_string,
    _timestamp_value,
    _valid_timestamp,
)
from queue_runtime.producer_era import (
    _producer_era_errors,
    _terminal_proof_profile_binding_errors,
    accounted_standards_versions,
)
from queue_runtime.receipts import _require_receipt
from queue_runtime.task_contract import (
    _contract_anchor_chain,
    _contract_sha256,
    _contract_sha_at_revision,
    _live_read_set_load_findings,
)
from queue_runtime.task_record import (
    _last_reconciled_guidance_id,
    _pending_control_ids,
    _task_transition_receipt_record_errors,
)


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
