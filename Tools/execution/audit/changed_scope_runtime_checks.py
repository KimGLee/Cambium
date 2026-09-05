#!/usr/bin/env python3
"""Pure producers for K12/05 changed-scope runtime-state checks.

The Kernel registry owns the three rule/check identities implemented here.
This module only evaluates their already-defined predicates against canonical
Progress, Coverage, Queue, Card, and Read Set contracts.  It writes no state,
does not mint an AuditReceipt, and does not decide whether a rule is
applicable; the AuditPlan producer owns that selection.

Every public check returns the same closed, JSON-serializable result shape so
the plan-bound evidence writer can wrap it without interpreting prose::

    check_id, rule_id, scope, result, diagnostics, metrics

``diagnostics`` are stable structured observations, not human verdicts.
"""

from copy import deepcopy
from types import MappingProxyType

import Tools.execution.context_delivery.card_activation as card_activation
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract

from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string
from Tools.execution.task_runtime.queue_runtime.task_contract import live_read_set_load_findings


TOOL = "changed_scope_runtime_checks"
TOOL_VERSION = "1.0.0"

GUIDANCE_RULE_ID = "k12-05-guidance-state-zero-counts"
GUIDANCE_CHECK_ID = "changed_scope_guidance_state_zero_counts"
COVERAGE_RULE_ID = "k12-05-coverage-routing-state"
COVERAGE_CHECK_ID = "changed_scope_coverage_routing_state"
TASK_CONTRACT_RULE_ID = "k12-05-frozen-task-contract-references"
TASK_CONTRACT_CHECK_ID = "changed_scope_frozen_task_contract_references"

CHECKS_BY_RULE_ID = MappingProxyType({
    GUIDANCE_RULE_ID: GUIDANCE_CHECK_ID,
    COVERAGE_RULE_ID: COVERAGE_CHECK_ID,
    TASK_CONTRACT_RULE_ID: TASK_CONTRACT_CHECK_ID,
})

_RESULT_FIELDS = frozenset((
    "check_id", "rule_id", "scope", "result", "diagnostics", "metrics",
))
_SCOPE_FIELDS = frozenset(("kind", "targets"))
_DIAGNOSTIC_FIELDS = frozenset((
    "diagnostic_id", "target", "field", "expected", "actual",
))

# K13/06 defines the status lifecycle as receipt, classification, mapping,
# execution, verification.  The K13 machine model owns these exact status
# identities.  These three intermediate positions are therefore the direct
# machine projection of K12/04's three named non-zero counters; terminal and
# explicitly mapped records do not contribute to one of those counters.
_GUIDANCE_COUNTER_BY_STATUS = MappingProxyType({
    "received": "unclassified_guidance",
    "classified": "accepted_unmapped_guidance",
    "in-progress": "implemented_unverified_guidance",
})
_GUIDANCE_DIAGNOSTIC_BY_COUNTER = MappingProxyType({
    "unclassified_guidance": "guidance-unclassified",
    "accepted_unmapped_guidance": "guidance-accepted-unmapped",
    "implemented_unverified_guidance": "guidance-implemented-unverified",
})
_GUIDANCE_EXPECTED_BY_COUNTER = MappingProxyType({
    "unclassified_guidance": "classified-or-final",
    "accepted_unmapped_guidance": "mapped-or-final",
    "implemented_unverified_guidance": "verified-or-final-disposition",
})


def _sorted_unique_strings(values, label, *, allow_empty=False):
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError("%s must be a string collection" % label)
    normalized = list(values)
    if (any(not isinstance(value, str) or not value or
            value.strip() != value for value in normalized) or
            len(normalized) != len(set(normalized)) or
            (not allow_empty and not normalized)):
        raise ValueError(
            "%s must contain unique non-empty trimmed strings" % label)
    return sorted(normalized)


def _scope(kind, targets, *, allow_empty=False):
    value = {
        "kind": kind,
        "targets": _sorted_unique_strings(
            targets, "scope.targets", allow_empty=allow_empty),
    }
    if set(value) != _SCOPE_FIELDS:
        raise AssertionError("changed-scope check scope drifted")
    return value


def _diagnostic(diagnostic_id, target, field, expected, actual):
    value = {
        "diagnostic_id": diagnostic_id,
        "target": target,
        "field": field,
        "expected": deepcopy(expected),
        "actual": deepcopy(actual),
    }
    if set(value) != _DIAGNOSTIC_FIELDS:
        raise AssertionError("changed-scope diagnostic shape drifted")
    return value


def _result(rule_id, scope, diagnostics, metrics):
    check_id = CHECKS_BY_RULE_ID[rule_id]
    ordered = sorted(
        diagnostics,
        key=lambda row: (
            row["target"], row["field"], row["diagnostic_id"],
            repr(row["actual"]),
        ),
    )
    value = {
        "check_id": check_id,
        "rule_id": rule_id,
        "scope": scope,
        "result": "pass" if not ordered else "fail",
        "diagnostics": ordered,
        "metrics": deepcopy(metrics),
    }
    if set(value) != _RESULT_FIELDS:
        raise AssertionError("changed-scope check result shape drifted")
    return value


def validate_check_result(value):
    """Validate the common producer result without consulting prose."""
    if not isinstance(value, dict) or set(value) != _RESULT_FIELDS:
        raise ValueError("changed-scope result fields are not closed")
    rule_id = value.get("rule_id")
    if rule_id not in CHECKS_BY_RULE_ID:
        raise ValueError("changed-scope result has unknown rule_id")
    if value.get("check_id") != CHECKS_BY_RULE_ID[rule_id]:
        raise ValueError("changed-scope result check_id differs from its rule")
    scope = value.get("scope")
    if not isinstance(scope, dict) or set(scope) != _SCOPE_FIELDS:
        raise ValueError("changed-scope result scope fields are not closed")
    if (not isinstance(scope.get("kind"), str) or not scope["kind"] or
            not isinstance(scope.get("targets"), list) or
            scope["targets"] != sorted(scope["targets"]) or
            len(scope["targets"]) != len(set(scope["targets"])) or
            any(not isinstance(target, str) or not target
                for target in scope["targets"])):
        raise ValueError("changed-scope result scope is invalid")
    diagnostics = value.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise ValueError("changed-scope result diagnostics must be a list")
    for index, row in enumerate(diagnostics):
        if not isinstance(row, dict) or set(row) != _DIAGNOSTIC_FIELDS:
            raise ValueError(
                "changed-scope diagnostic %d fields are not closed" % index)
        for field in ("diagnostic_id", "target", "field"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError(
                    "changed-scope diagnostic %d has invalid %s" %
                    (index, field))
    if value.get("result") not in ("pass", "fail"):
        raise ValueError("changed-scope result must be pass or fail")
    if value["result"] != ("pass" if not diagnostics else "fail"):
        raise ValueError("changed-scope result disagrees with diagnostics")
    if not isinstance(value.get("metrics"), dict):
        raise ValueError("changed-scope result metrics must be a mapping")
    return value


def guidance_state_zero_counts(progress, guidance_ids=None):
    """Evaluate K12/04's three counters over the applicable Guidance rows.

    With no explicit ``guidance_ids``, all Guidance records are checked.  This
    is equivalent to K12/04's incremental boundary for this predicate: old
    final records contribute no count, while every existing open row and each
    new ``received`` row is included.
    """
    guidance = progress.get("guidance_queue") if isinstance(
        progress, dict) else None
    diagnostics = []
    if guidance_ids is None:
        selected_ids = None
        scope_targets = []
    else:
        scope_targets = _sorted_unique_strings(
            guidance_ids, "guidance_ids", allow_empty=True)
        selected_ids = set(scope_targets)
    counts = {
        "unclassified_guidance": 0,
        "accepted_unmapped_guidance": 0,
        "implemented_unverified_guidance": 0,
    }
    seen = set()
    if not isinstance(guidance, list):
        diagnostics.append(_diagnostic(
            "guidance-queue-invalid", "Progress.guidance_queue",
            "guidance_queue", "explicit-list", type(guidance).__name__))
    else:
        for index, row in enumerate(guidance):
            position = "Progress.guidance_queue[%d]" % index
            if not isinstance(row, dict):
                diagnostics.append(_diagnostic(
                    "guidance-record-invalid", position, "record",
                    "mapping", type(row).__name__))
                continue
            guidance_id = row.get("guidance_id")
            if selected_ids is not None and guidance_id not in selected_ids:
                continue
            if nonempty_string(guidance_id):
                seen.add(guidance_id)
                target = "Progress.guidance_queue[%s]" % guidance_id
            else:
                target = position
                diagnostics.append(_diagnostic(
                    "guidance-id-invalid", position, "guidance_id",
                    "non-empty-string", guidance_id))
            status = row.get("status")
            if status not in runtime_state_contract.GUIDANCE_STATUSES:
                diagnostics.append(_diagnostic(
                    "guidance-status-invalid", target, "status",
                    sorted(runtime_state_contract.GUIDANCE_STATUSES), status))
                continue
            counter = _GUIDANCE_COUNTER_BY_STATUS.get(status)
            if counter is None:
                continue
            counts[counter] += 1
            diagnostics.append(_diagnostic(
                _GUIDANCE_DIAGNOSTIC_BY_COUNTER[counter], target, "status",
                _GUIDANCE_EXPECTED_BY_COUNTER[counter], status))
    if selected_ids is not None:
        for missing in sorted(selected_ids - seen):
            diagnostics.append(_diagnostic(
                "guidance-target-missing", "Progress.guidance_queue[%s]" % missing,
                "guidance_id", "present", "missing"))
    if selected_ids is None and isinstance(guidance, list):
        scope_targets = sorted(
            row.get("guidance_id") for row in guidance
            if isinstance(row, dict) and nonempty_string(row.get("guidance_id")))
    scope = _scope("guidance-records", scope_targets, allow_empty=True)
    return validate_check_result(_result(
        GUIDANCE_RULE_ID, scope, diagnostics, counts))


def coverage_routing_state(coverage, queue, targets=None):
    """Check K12/05's deterministic routing observations in one scope."""
    pages = coverage.get("pages") if isinstance(coverage, dict) else None
    items = queue.get("required_queue") if isinstance(queue, dict) else None
    diagnostics = []
    records = {}
    if not isinstance(pages, list):
        diagnostics.append(_diagnostic(
            "coverage-pages-invalid", "Coverage.pages", "pages",
            "explicit-list", type(pages).__name__))
        pages = []
    for index, row in enumerate(pages):
        position = "Coverage.pages[%d]" % index
        if not isinstance(row, dict):
            diagnostics.append(_diagnostic(
                "coverage-record-invalid", position, "record", "mapping",
                type(row).__name__))
            continue
        path = row.get("path")
        if not nonempty_string(path):
            diagnostics.append(_diagnostic(
                "coverage-path-invalid", position, "path",
                "non-empty-string", path))
            continue
        if path in records:
            diagnostics.append(_diagnostic(
                "coverage-path-duplicate", "Coverage.pages[%s]" % path,
                "path", "unique", path))
            continue
        records[path] = row

    if targets is None:
        selected = sorted(records)
    else:
        selected = _sorted_unique_strings(
            targets, "targets", allow_empty=True)

    items_by_id = {}
    if not isinstance(items, list):
        diagnostics.append(_diagnostic(
            "required-queue-invalid", "RequiredQueue.required_queue",
            "required_queue", "explicit-list", type(items).__name__))
        items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not nonempty_string(item.get("id")):
            continue
        items_by_id.setdefault(item["id"], item)

    # `unassessed` is the legal first-open runtime value.  Completion-level
    # Coverage review owns any narrower authoring-status requirement; this
    # pre-merge routing producer must not promote it into a universal block.
    counts = {
        "required_without_current_next_batch": 0,
        "deferred_or_excluded_without_reason": 0,
    }
    for path in selected:
        record = records.get(path)
        target = "Coverage.pages[%s]" % path
        if record is None:
            diagnostics.append(_diagnostic(
                "coverage-target-missing", target, "path", "present",
                "missing"))
            continue
        disposition = record.get("coverage_disposition")
        if disposition in ("deferred", "excluded") and not nonempty_string(
                record.get("deferred_reason")):
            counts["deferred_or_excluded_without_reason"] += 1
            diagnostics.append(_diagnostic(
                "coverage-disposition-reason-missing", target,
                "deferred_reason", "non-empty-reason-or-scope-basis",
                record.get("deferred_reason")))

        if disposition != "required":
            continue
        route_ids = []
        for field in ("batch", "next_batch"):
            value = record.get(field)
            if nonempty_string(value) and value not in route_ids:
                route_ids.append(value)
        current = [
            items_by_id[item_id] for item_id in route_ids
            if item_id in items_by_id and
            items_by_id[item_id].get("state") in
            runtime_state_contract.QUEUE_NONTERMINAL_STATES
        ]
        next_batch = record.get("next_batch")
        missing_current_route = False
        actual = next_batch
        if not route_ids:
            missing_current_route = True
            actual = "no-batch-or-next-batch-assignment"
        elif not nonempty_string(next_batch):
            historical_batch = record.get("batch")
            historical_item = items_by_id.get(historical_batch) \
                if nonempty_string(historical_batch) else None
            if (current or historical_item is None or
                    historical_item.get("state") not in
                    runtime_state_contract.QUEUE_TERMINAL_STATES):
                missing_current_route = True
                actual = {
                    "next_batch": next_batch,
                    "batch": historical_batch,
                    "batch_state": (historical_item or {}).get("state"),
                }
        elif nonempty_string(next_batch) and (
                next_batch not in items_by_id or
                items_by_id[next_batch].get("state") not in
                runtime_state_contract.QUEUE_NONTERMINAL_STATES):
            missing_current_route = True
            actual = {
                "next_batch": next_batch,
                "state": (items_by_id.get(next_batch) or {}).get("state"),
            }
        if missing_current_route:
            counts["required_without_current_next_batch"] += 1
            diagnostics.append(_diagnostic(
                "required-next-batch-missing-or-terminal", target,
                "next_batch", "non-terminal-queue-item", actual))

    scope = _scope("coverage-records", selected, allow_empty=True)
    return validate_check_result(_result(
        COVERAGE_RULE_ID, scope, diagnostics, counts))


def frozen_task_contract_references(root, progress, item, runtime_state):
    """Validate frozen component references through their canonical parsers.

    Card/route/Profile-Read-Set references are checked by the same activation
    builder that consumes them.  Read Set target/dependency closure is checked
    by K13's canonical Task Contract resolver; both invalid roots and omitted
    transitive declarations fail this evidence check.  The function produces
    no activation receipt and performs no delivery.
    """
    task_id = (runtime_state.get("queue") or {}).get("task_id") \
        if isinstance(runtime_state, dict) else None
    batch_id = item.get("id") if isinstance(item, dict) else None
    targets = [
        value for value in (task_id, batch_id)
        if nonempty_string(value)
    ]
    diagnostics = []
    context = None
    try:
        context = card_activation.build_activation_context(
            root, progress, item, runtime_state=runtime_state)
        context_errors = card_activation.activation_context_errors(context)
        for index, error in enumerate(context_errors):
            diagnostics.append(_diagnostic(
                "activation-reference-invalid",
                "TaskContract.activation[%d]" % index, "component_reference",
                "valid-current-component-contract", error))
    except (OSError, UnicodeError, ValueError) as exc:
        diagnostics.append(_diagnostic(
            "activation-reference-invalid", "TaskContract.activation",
            "component_reference", "valid-current-component-contract",
            str(exc)))

    contract = progress.get("contract") if isinstance(progress, dict) else None
    if not isinstance(contract, dict):
        diagnostics.append(_diagnostic(
            "task-contract-invalid", "Progress.contract", "contract",
            "mapping", type(contract).__name__))
        load_errors, load_gaps = (), ()
    else:
        try:
            load_errors, load_gaps = live_read_set_load_findings(root, contract)
        except (OSError, UnicodeError, ValueError) as exc:
            load_errors, load_gaps = (str(exc),), ()
    for index, error in enumerate(load_errors):
        diagnostics.append(_diagnostic(
            "read-set-reference-invalid",
            "TaskContract.selected_read_sets[%d]" % index,
            "component_reference", "valid-read-set-contract", error))
    for index, gap in enumerate(load_gaps):
        diagnostics.append(_diagnostic(
            "read-set-load-closure-omission",
            "TaskContract.load_closure[%d]" % index,
            "declared_loading_boundary", "complete-transitive-closure", gap))

    metrics = {
        "activation_context_valid": context is not None and not any(
            row["diagnostic_id"] == "activation-reference-invalid"
            for row in diagnostics),
        "read_set_reference_error_count": len(load_errors),
        "read_set_load_closure_gap_count": len(load_gaps),
    }
    scope = _scope("task-contract-and-batch", targets, allow_empty=True)
    return validate_check_result(_result(
        TASK_CONTRACT_RULE_ID, scope, diagnostics, metrics))


__all__ = [
    'COVERAGE_RULE_ID',
    'GUIDANCE_RULE_ID',
    'TASK_CONTRACT_RULE_ID',
    'coverage_routing_state',
    'frozen_task_contract_references',
    'guidance_state_zero_counts',
]
