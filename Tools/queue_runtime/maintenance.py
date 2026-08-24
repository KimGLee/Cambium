"""Is one bounded maintenance run complete against current canonical state.

Completion is judged against the state as it is now, not as it was when the
run started, and the run's true immediate predecessor is resolved rather than
assumed from ordering.  A maintenance gate that named the wrong predecessor
would prove a different run complete.
"""

import kblib
import maintenance_candidates

from queue_runtime.canon import (
    ANY_PRODUCER_ERA_VERSION,
    COVERAGE_PATH,
    QUEUE_PATH,
    SHA256_RE,
    SUPPORTED_CHECK_QUEUE_TOOL_VERSIONS,
    TERMINAL_STATES,
    TOOL,
)
from queue_runtime.primitives import (
    closed_mapping_errors,
    nonempty_string,
    timestamp_value,
    valid_timestamp,
)
from queue_runtime.receipts import require_receipt
from queue_runtime.repofs import repository_evidence_file
from queue_runtime.task_contract import contract_sha256
from queue_runtime.task_record import (
    pending_control_ids,
    task_transition_receipt_record_errors,
)


def _maintenance_evidence_receipt(root, result, receipt_id, label,
                                  expected, path_field, sha_field, errors):
    """Validate one current maintenance input and its persisted receipt."""
    receipt = require_receipt(
        result.get("receipt_catalog", {}), receipt_id, label, errors,
        expected=expected,
    )
    if receipt is None:
        return None
    for field in ("tool", "tool_version"):
        if not nonempty_string(receipt.get(field)):
            errors.append("%s receipt %s has invalid %s" %
                          (label, receipt_id, field))
    if not valid_timestamp(receipt.get("checked_at")):
        errors.append("%s receipt %s has invalid checked_at" %
                      (label, receipt_id))
    relative_path = receipt.get(path_field)
    fingerprint = receipt.get(sha_field)
    if not nonempty_string(relative_path):
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
    absolute = repository_evidence_file(
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
        consumer = require_receipt(
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
            local_errors.extend(task_transition_receipt_record_errors(
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
            gate_time = timestamp_value(gate.get("checked_at"))
            consumer_time = timestamp_value(consumer.get("checked_at"))
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


def latest_consumed_maintenance_gate(root, result, contract,
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
        if (nonempty_string(current_maintenance_run_id) and
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
            if not nonempty_string(gate.get(field)):
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
        if not valid_timestamp(gate.get("checked_at")):
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
            timestamp_value(consumer.get("checked_at")),
            timestamp_value(gate.get("checked_at")), gate_id,
            consumer_id,
        ))
    eligible.sort()
    return eligible[-1][2] if eligible else None


def previous_maintenance_candidate_state(root, result, receipt_id,
                                          contract, errors):
    """Resolve the prior run's candidate projection from a persisted gate."""
    if receipt_id is None:
        return None, [], maintenance_candidates.candidate_state_sha256([])
    receipt = require_receipt(
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
    if not nonempty_string(receipt.get("maintenance_run_id")):
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
    if not valid_timestamp(receipt.get("checked_at")):
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
    elif (timestamp_value(consumers[0][1].get("checked_at")) is None or
          (timestamp_value(receipt.get("checked_at")) is not None and
           timestamp_value(consumers[0][1].get("checked_at")) <
           timestamp_value(receipt.get("checked_at")))):
        errors.append(
            "previous maintenance task completion predates its gate receipt"
        )
    return receipt, records, fingerprint


def maintenance_completion_gate_errors(root, result,
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
    pending_guidance, pending_amendments = pending_control_ids(progress)
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
    if budget is not None and nonempty_string(
            budget.get("budget_manifest_path")):
        absolute = repository_evidence_file(
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
                errors.extend(closed_mapping_errors(
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
                if not nonempty_string(maintenance_run_id):
                    errors.append(
                        "maintenance budget manifest run_id must be a "
                        "non-empty string"
                    )
                previous_completion_id = manifest.get(
                    "previous_maintenance_completion_receipt")
                if (previous_completion_id is not None and
                        not nonempty_string(previous_completion_id)):
                    errors.append(
                        "maintenance budget manifest "
                        "previous_maintenance_completion_receipt must be null "
                        "or a non-empty receipt ID"
                    )
                expected_previous_completion_id = \
                    latest_consumed_maintenance_gate(
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
                    previous_maintenance_candidate_state(
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
                    prior_instant = timestamp_value(
                        previous_candidate_receipt.get("checked_at"))
                    closed_instant = timestamp_value(manifest.get("closed_at"))
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
                if not valid_timestamp(manifest.get("closed_at")):
                    errors.append(
                        "maintenance budget manifest closed_at is invalid"
                    )
                if budget.get("budget_manifest_closed_at") != manifest.get(
                        "closed_at"):
                    errors.append(
                        "maintenance budget receipt does not bind manifest "
                        "closed_at"
                    )
                closed_instant = timestamp_value(manifest.get("closed_at"))
                receipt_instant = timestamp_value(budget.get("checked_at"))
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

    if watermark is not None and nonempty_string(
            watermark.get("watermark_path")):
        if watermark.get("maintenance_run_id") != maintenance_run_id:
            errors.append(
                "maintenance watermark receipt does not bind maintenance_run_id"
            )
        absolute = repository_evidence_file(
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
                if not valid_timestamp(watermark_state.get("updated_at")):
                    errors.append("maintenance watermark updated_at is invalid")
                if not nonempty_string(watermark_state.get("last_run_id")):
                    errors.append("maintenance watermark last_run_id is invalid")
                if not nonempty_string(watermark_state.get("last_batch_id")):
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
                updated_instant = timestamp_value(
                    watermark_state.get("updated_at"))
                receipt_instant = timestamp_value(watermark.get("checked_at"))
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
        coverage_updated = timestamp_value(
            (result.get("coverage") or {}).get("updated_at"))
        receipt_checked = timestamp_value(ledger.get("checked_at"))
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
            instant = timestamp_value(item.get(field))
            if instant is not None:
                terminal_instants.append(instant)
    if terminal_instants:
        latest_terminal = max(terminal_instants)
        for label, receipt in (("budget manifest closure", budget),
                               ("Ledger advance", ledger),
                               ("watermark advance", watermark)):
            if receipt is not None:
                instant = timestamp_value(receipt.get("checked_at"))
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
        if nonempty_string(value):
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
        "contract_sha256": contract_sha256(progress),
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


def maintenance_gate_time_errors(result, gate):
    """Require the gate to follow every terminal event and consumed receipt."""
    errors = []
    gate_time = timestamp_value(gate.get("checked_at"))
    if gate_time is None:
        return ["maintenance completion gate has invalid checked_at"]
    instants = []
    for field in ("budget_manifest_receipt", "ledger_advance_receipt",
                  "watermark_advance_receipt"):
        entry = (result.get("receipt_catalog") or {}).get(gate.get(field))
        receipt = entry[1] if entry is not None else None
        instant = timestamp_value(
            receipt.get("checked_at")) if isinstance(receipt, dict) else None
        if instant is not None:
            instants.append((field, instant))
    for item in (result.get("items_by_id") or {}).values():
        for field in ("closed_at", "cancelled_at"):
            instant = timestamp_value(item.get(field))
            if instant is not None:
                instants.append(("batch.%s" % field, instant))
    future = sorted(label for label, instant in instants if instant > gate_time)
    if future:
        errors.append(
            "maintenance completion gate predates consumed evidence: %s" %
            ", ".join(future)
        )
    return errors
