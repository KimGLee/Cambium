"""Deterministically connect current Task Runtime state to its next Tool.

The Runner is an application-layer dispatcher.  It reads the admitted runtime,
derives one typed action, invokes only existing registered producers/writers,
and then reads the runtime again.  It never edits Queue, Coverage, Progress,
Receipts, AuditPlans, Deltas, or governed pages itself.
"""
from Tools.platform.repository.path_contract import \
    canonical_repository_relative_path
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from contextvars import ContextVar

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_execution_runtime as audit_execution_runtime
import Tools.execution.audit.assemble_terminal_proof as assemble_terminal_proof
import Tools.execution.audit.batch_review_receipt_contract as batch_review_receipt_contract
import Tools.platform.common.kblib as kblib
import Tools.platform.agent_interface.cli_argv_renderer as cli_argv_renderer
import Tools.platform.agent_interface.agent_interface_contract as interface_contract
import Tools.platform.agent_interface.compile_cli_contract as compile_cli_contract
import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader
import Tools.platform.agent_interface.tool_availability as tool_availability
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.profile_admission as profile_admission
import Tools.knowledge.rendering.profile_rendering_evidence_contract as profile_rendering
import Tools.knowledge.rendering.static_render_runtime as static_render_runtime
import Tools.knowledge.rendering.rendering_verification_contract as rendering_verification_contract
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.gate_registry as gate_registry
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.task_runtime.task_runtime_action as task_runtime_action
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.execution.audit.batch_review_obligation_contract as batch_review_obligation_contract
from Tools.platform.common.primitives import catalog_record
from Tools.platform.common.reporting import write_canonical_json, host_environment_boundary
from Tools.platform.common.reporting import publication_result_reliable, observe_tool_output
from Tools.platform.repository import path_admission, path_capability
from Tools.platform.common.host_environment import HostEnvironmentUnavailable, preparation_request


AUDIT_PLAN_CAPABILITY = "audit-plan-producer-v1"
RUNNER_CAPABILITY = task_runtime_action.action_route(
    "activate-ready-batch").capability_chain[0]
ACTIVATION_RECEIPT_TEMPLATE = \
    runtime_paths.RECEIPT_ROOT + "/ready-%s.jsonl"
COMPLETION_RECEIPT_PATH = runtime_paths.child_path(
    runtime_paths.RECEIPT_ROOT, "queue-complete.jsonl")
MAINTENANCE_GATE_RECEIPT_PATH = runtime_paths.child_path(
    runtime_paths.RECEIPT_ROOT, "maintenance-gate.jsonl")
TERMINAL_RECEIPT_PATH = runtime_paths.path_for("terminal-audit-receipts")
TERMINAL_PROOF_PATH = assemble_terminal_proof.DEFAULT_PROOF_PATH
_EXECUTION_OBSERVATION = ContextVar("runner_execution_observation", default=None)


class RunnerError(ValueError):
    """The Runner cannot safely derive or execute one current action."""

    def __init__(self, message, data=None):
        super().__init__(message)
        self.data = data


@dataclass(frozen=True)
class _RunnerRouteHandler:
    """Concrete Runner handlers for one registered ``runner_route``.

    The route table owns selection identity; this object only connects that
    identity to executable application code.  A route can participate in the
    resume projection, await-input consumption, invoke execution, or more than
    one of those boundaries without inventing another lifecycle state.
    """

    resume: object = None
    await_input: object = None
    invoke: object = None


def _await_control_route(token):
    """Project one await route from the shared action registry."""
    try:
        route, _parameters = task_runtime_action.action_route_for_token(token)
    except ValueError as exc:
        raise RunnerError(str(exc)) from exc
    if route.action_disposition not in task_runtime_action.AWAIT_DISPOSITIONS:
        raise RunnerError(
            "action %s is registered as %s, not await" %
            (token, route.action_disposition))
    return route.runner_route


def _route_capability(route, index=0):
    try:
        return route.capability_chain[index]
    except IndexError as exc:
        raise RunnerError(
            "action route %s has no capability at chain index %d" %
            (route.route_id, index)) from exc


def _action_control_route(action):
    """Prove every emitted action has exactly one Runner control route."""
    disposition = action.get("disposition")
    if disposition == "invoke":
        return "invoke-executor"
    if disposition in task_runtime_action.AWAIT_DISPOSITIONS:
        return _await_control_route(action.get("token"))
    if disposition in {"repair", "terminal"}:
        return "non-executable-boundary"
    raise RunnerError(
        "action disposition %r has no Runner control route" % disposition)


def _ordered_items(result, states=None):
    items = (result.get("items_by_id") or {}).values()
    if states is not None:
        items = [row for row in items if row.get("state") in states]
    return sorted(items, key=lambda row: (
        row.get("order", sys.maxsize), row.get("id") or ""))


def _binding(result, *, plan_sha256=None):
    queue = result.get("queue") or {}
    profile = result.get("_profile_authorized_view")
    standards = result.get("_active_standards_authorized_view")
    if not isinstance(profile, dict):
        raise RunnerError(
            "Runner binding requires the admitted Profile authority view")
    if not isinstance(standards, dict):
        raise RunnerError(
            "Runner binding requires the admitted Standards authority view")
    return {
        "upstream_revision_id": standards.get("upstream_revision_id"),
        "selected_profile_manifest": profile.get(
            "selected_profile_manifest"),
        "profile_snapshot_sha256": profile.get(
            "profile_snapshot_sha256"),
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": result.get("progress_sha256"),
        "audit_plan_sha256": plan_sha256,
    }


def _action(result, *, disposition, token, capability_id=None, tool=None,
            target=None, arguments=None, required_input=None, reason_code,
            plan_sha256=None):
    action = task_runtime_action.build_action(
        schema_version=task_runtime_action.SCHEMA_VERSION,
        disposition=disposition,
        token=token,
        capability_id=capability_id,
        tool=tool,
        target=dict(target or {}),
        arguments=dict(arguments or {}),
        required_input=required_input,
        binding=_binding(result, plan_sha256=plan_sha256),
        reason_code=reason_code,
    )
    _action_control_route(action)
    return action


def _repair(result, reason_code, *, target=None):
    return _action(
        result, disposition="repair", token="repair-runtime",
        target=target, reason_code=reason_code)


def _await(result, disposition, token, required_input, reason_code, *,
           target=None, plan_sha256=None):
    return _action(
        result, disposition=disposition, token=token,
        target=target, required_input=required_input,
        reason_code=reason_code, plan_sha256=plan_sha256)


def _route_input(result, token, fields, *, required=(), index=0,
                 shapes=None, encodings=None):
    route, _parameters = task_runtime_action.action_route_for_token(token)
    tool = _capability_tool(result, _route_capability(route, index))
    parameters = fields if isinstance(fields, dict) else {name: name for name in fields}
    return interface_contract.input_binding(
        _compiled_cli_tool(result["root"], tool), parameters,
        required=required, shapes=shapes, encodings=encodings)


def _producer_input(result, step):
    if step.get("required_input") is None:
        return None
    return interface_contract.input_binding(
        _compiled_cli_tool(result["root"], step["resume_tool"]),
        arguments=step["resume_arguments"], **step["required_input"])


def _capability_tool(result, capability_id):
    return metadata_execution_contract.capability_invocation_tool(
        capability_id, root=result["root"])


def _invoke(result, token, capability_id, arguments, reason_code, *,
            target=None, plan_sha256=None):
    return _action(
        result, disposition="invoke", token=token,
        capability_id=capability_id,
        tool=_capability_tool(result, capability_id),
        target=target, arguments=arguments, reason_code=reason_code,
        plan_sha256=plan_sha256)


def _managed_candidate_delta(result, item):
    return queue_runtime.delta.current_candidate_binding(
        result["root"], result, item, allow_absent=True)


def _current_batch_review_wrapper(result, item, delta):
    catalog = queue_runtime.current_receipt_catalog(result)
    valid = []
    invalid = []
    for receipt_id, entry in sorted(catalog.items()):
        record = catalog_record(entry)
        if not isinstance(record, dict):
            continue
        if not (record.get("tool") ==
                batch_review_receipt_contract.PRODUCER_TOOL and
                record.get("check") ==
                batch_review_receipt_contract.PRODUCER_CHECK and
                record.get("receipt_type_id") ==
                batch_review_receipt_contract.RECEIPT_TYPE_ID and
                record.get("target") == item["id"] and
                record.get("batch_id") == item["id"]):
            continue
        errors = queue_runtime.batch_review_receipt_errors(
            catalog, receipt_id, item_id=item["id"],
            task_id=(result.get("queue") or {}).get("task_id"),
            activation_receipt_id=item.get("activation_receipt"),
            delta_page_receipt_ids=delta.get("page_receipt_ids") or [])
        errors.extend(queue_runtime.batch_review_judgment_errors(
            result, item, record))
        errors.extend(audit_evidence_runtime.wrapper_binding_errors(
            result, item, record))
        for field, expected in (
                ("delta_path", delta.get("path")),
                ("delta_sha256", delta.get("sha256"))):
            if record.get(field) != expected:
                errors.append("batch-review wrapper %s drifted" % field)
        (invalid if errors else valid).append((receipt_id, errors))
    if len(valid) > 1:
        raise RunnerError(
            "batch %s has multiple valid Batch Review wrappers: %s" %
            (item["id"], ", ".join(row[0] for row in valid)))
    if valid:
        return valid[0][0]
    if invalid:
        raise RunnerError(
            "batch %s has an invalid Batch Review wrapper: %s" %
            (item["id"], "; ".join(invalid[0][1])))
    return None


def _phase_action(result, item, phase_id):
    status = queue_runtime.review.activation_phase_delivery_status(
        result, item, phase_id)
    if status["status"] in {"not-applicable", "complete"}:
        return None
    target = {
        "batch_id": item["id"],
        "phase_id": phase_id,
        "part_index": status.get("part_index"),
        "part_count": status.get("part_count"),
        "delivery_attempt_id": status.get("delivery_attempt_id"),
    }
    if status["status"] == "invalid":
        return _repair(
            result, "activation-phase-delivery-invalid", target=target)
    if status["status"] == "acknowledge":
        return _await(
            result, "await-agent", "ack-activation-phase", _route_input(
                result, "ack-activation-phase", ("phase_nonce", "phase_delivery_receipt"),
                required=("phase_nonce", "phase_delivery_receipt")),
            "delivered-phase-needs-same-context-ack", target=target)
    if status["status"] != "deliver":
        return _repair(
            result, "unknown-activation-phase-status", target=target)
    receipt_path = runtime_paths.child_path(
        runtime_paths.RECEIPT_ROOT,
        "phase-%s-%s-%d.jsonl" % (
            item["id"].lower(), phase_id, status["part_index"]))
    return _invoke(
        result, "deliver-activation-phase", _route_capability(
            task_runtime_action.action_route("ack-activation-phase")), {
            "deliver_phase": item["id"],
            "phase": phase_id,
            "phase_part": status["part_index"],
            "receipts": receipt_path,
            "json": True,
        }, "current-context-needs-frozen-phase", target=target)


def _first_phase_action(result, item, phase_ids):
    for phase_id in phase_ids:
        action = _phase_action(result, item, phase_id)
        if action is not None:
            return action
    return None


def _audit_action(result, item):
    phase_action = _first_phase_action(
        result, item, ("batch-preflight", "batch-running"))
    if phase_action is not None:
        return phase_action
    try:
        step = audit_execution_runtime.next_stage_step(
            result, item, "pre-merge", required_state="open")
    except audit_evidence_runtime.AuditPlanMissing:
        return _invoke(
            result, "prepare-audit-plan", AUDIT_PLAN_CAPABILITY,
            {"batch": item["id"], "apply": True},
            "open-batch-has-no-audit-plan", target={"batch_id": item["id"]})
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError):
        return _repair(
            result, "audit-plan-or-evidence-invalid",
            target={"batch_id": item["id"]})

    target = step.get("target") or {"batch_id": item["id"]}
    plan_sha = (step.get("closure") or {}).get("audit_plan_sha256") or \
        (step.get("target") or {}).get("audit_plan_sha256")
    if step["status"] == "invoke":
        arguments = dict(step["arguments"])
        arguments["apply"] = True
        return _invoke(
            result, step["token"], step["capability_id"],
            arguments, step["reason_code"], target=target,
            plan_sha256=plan_sha)
    if step["status"] in {"await-agent", "await-user", "await-host"}:
        phase_action = _phase_action(result, item, "batch-gate")
        if phase_action is not None:
            return phase_action
        if step.get("external_instruction"):
            target = dict(target, external_instruction=step["external_instruction"])
        return _await(
            result, step["status"], step["token"], _producer_input(result, step),
            step["reason_code"], target=target, plan_sha256=plan_sha)
    if step["status"] == "repair":
        return _repair(result, step["reason_code"], target=target)
    if step["status"] != "complete":
        return _repair(result, "unknown-audit-execution-status", target=target)

    delta = _managed_candidate_delta(result, item)
    page_evidence = audit_evidence_runtime.candidate_page_evidence(result, item)
    delta_errors = []
    if delta is not None:
        delta_document = kblib.load_yaml_file(os.path.join(result["root"], delta["path"]))
        delta_errors = audit_evidence_runtime.candidate_page_evidence_errors(
            result, item, delta_document, resolved=page_evidence)
    if delta is None or delta_errors:
        return _await(
            result, "await-agent", "publish-candidate-delta", _route_input(
                result, "publish-candidate-delta", ("proposal",)),
            "batch-work-needs-candidate-delta",
            target={"batch_id": item["id"], "page_evidence_refs": page_evidence,
                    "candidate_delta_sha256": delta["sha256"] if delta else "absent"},
            plan_sha256=step["closure"]["audit_plan_sha256"])
    if delta.get("handoff_status") != "candidate":
        return _repair(
            result, "candidate-delta-invalid",
            target={"batch_id": item["id"], "delta_path": delta.get("path")})
    try:
        wrapper_id = _current_batch_review_wrapper(result, item, delta)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError):
        return _repair(
            result, "batch-review-wrapper-invalid",
            target={"batch_id": item["id"]})
    if wrapper_id is None:
        phase_action = _phase_action(result, item, "batch-gate")
        if phase_action is not None:
            return phase_action
        return _await(
            result, "await-agent", "record-batch-review", _route_input(
                result, "record-batch-review", ("statement",)),
            "pre-merge-closure-needs-integrator-attestation",
            target={"batch_id": item["id"]},
            plan_sha256=step["closure"]["audit_plan_sha256"])
    phase_action = _phase_action(result, item, "batch-gate")
    if phase_action is not None:
        return phase_action
    return _invoke(
        result, "transition-batch-merge-ready",
        _route_capability(task_runtime_action.action_route(
            "transition-batch-merge-ready")), {
            "id": item["id"],
            "transition": "merge-ready",
            "delta_path": delta["path"],
            "batch_receipt": [wrapper_id],
            "expected_state_revision": result["queue"]["state_revision"],
            "expected_sha256": result["queue_sha256"],
            "actor_role": "integrator",
            "apply": True,
            "json": True,
        }, "candidate-delta-and-batch-review-are-current",
        target={"batch_id": item["id"]},
        plan_sha256=step["closure"]["audit_plan_sha256"])


def _current_standards_revalidation_aggregate(result, batch_id):
    """Select the latest current aggregate from authoritative Receipt state."""
    valid = []
    catalog = queue_runtime.current_receipt_catalog(result)
    mode = "require-revalidation:%s" % batch_id
    for receipt_id, entry in sorted(catalog.items()):
        record = catalog_record(entry)
        if not isinstance(record, dict) or \
                record.get("queue_check_mode") != mode:
            continue
        errors = queue_runtime.standards_revalidation_receipt_errors(
            result, batch_id, receipt_id)
        if not errors:
            valid.append((
                queue_runtime.timestamp_value(record.get("checked_at")),
                receipt_id,
            ))
    valid = [row for row in valid if row[0] is not None]
    valid.sort()
    return valid[-1][1] if valid else None


def _resume_repair(result, route, parameters, _token):
    target = ({"batch_id": parameters["batch_id"]}
              if "batch_id" in parameters else {})
    deficits = result.get("current_evidence_deficits")
    if deficits and not result.get("structural_errors"):
        target["current_evidence_deficits"] = deficits
        # The original state owner decides whether a rollback, new Gate, or
        # escalation is allowed. Never silently reopen closed/complete state.
        target["recorded_state_preserved"] = True
        return _repair(result, "withdrawn-evidence-needs-owned-continuation",
                       target=target)
    return _repair(result, route.route_id, target=target)


def _resume_terminal(result, _route, _parameters, token):
    return _action(
        result, disposition="terminal", token=token,
        reason_code="task-runtime-is-terminal")


def _resume_task_transition(result, route, _parameters, token):
    paused = route.route_id == "resume-paused-task"
    progress = result.get("progress") or {}
    choices = [target for target in ("active", "paused", "cancelled")
               if runtime_state_contract.task_transition_is_authorized(
                   (progress.get("contract") or {}).get("completion_semantics"),
                   progress.get("task_state"), target)]
    return _await(
        result, "await-user", token, _route_input(
            result, token, {"task_transition": "transition", "checkpoint_summary": "checkpoint_summary"},
            required=("checkpoint_summary",), shapes={"task_transition": {"enum": choices}}),
        ("paused-task-needs-user-direction" if paused else
            "blocked-task-needs-user-direction"))


def _resume_external_reparse(result, route, _parameters, token):
    runtime = result.get("task_runtime") or {}
    target = {}
    reason = "runtime-boundary-needs-authoritative-external-change"
    if route.route_id == "reconcile-control-input":
        target = {
            "pending_guidance": list(runtime.get("pending_guidance") or []),
            "pending_amendments": list(
                runtime.get("pending_amendments") or []),
        }
        reason = "pending-control-input-needs-authority"
    elif route.route_id == "resolve-holds-dependencies":
        target = {
            "blocked": list(result.get("blocked") or []),
            "remaining": result.get("remaining"),
        }
        reason = "recorded-hold-or-dependency-needs-resolution"
    return _await(
        result, route.action_disposition, token, None, reason,
        target=dict(target, external_instruction=
                    "Use the named canonical owner, then derive the next action again."))


def _resume_terminal_audit(result, _route, _parameters, token):
    terminal = (result.get("progress") or {}).get("terminal_audit") or {}
    return _await(
        result, "await-agent", token, _route_input(
            result, token, ("terminal_audit_input",), index=2),
        "completion-candidate-needs-terminal-audit-input",
        target={
            "task_id": (result.get("progress") or {}).get("task_id"),
            "candidate_queue_check_receipt":
                terminal.get("queue_check_receipt"),
        })


def _resume_materialize_required_queue(result, route, _parameters, token):
    queue = result.get("queue") or {}
    return _invoke(
        result, token, _route_capability(route), {
            "expected_queue_revision": queue.get("queue_revision"),
            "expected_sha256": result.get("queue_sha256"),
            "actor_role": "integrator", "apply": True, "json": True,
        }, "confirmed-task-plan-has-unmaterialized-queue")


def _resume_activate_ready_batch(result, route, parameters, _token):
    batch_id = parameters["batch_ids"].split(",", 1)[0]
    boundary = _rendering_boundary(result, batch_id)
    if boundary is not None:
        return boundary
    return _invoke(
        result, "activate-ready-batch", _route_capability(route),
        {"batch": batch_id}, "earliest-required-batch-is-ready",
        target={"batch_id": batch_id})


def _resume_open_batch_audit(result, route, parameters, _token):
    if not route.internal_dispatch or route.action_disposition is not None:
        raise RunnerError(
            "open-batch-audit must be an internal dispatch route")
    batch_values = parameters.get("batch_ids", parameters.get("batch_id"))
    batch_id = batch_values.split(",", 1)[0]
    item = (result.get("items_by_id") or {}).get(batch_id)
    if not isinstance(item, dict) or item.get("state") != "open":
        return _repair(
            result, "resume-token-does-not-name-open-batch",
            target={"batch_id": batch_id})
    return _audit_action(result, item)


def _resume_apply_delta(result, route, parameters, _token):
    batch_id = parameters["batch_id"]
    item = (result.get("items_by_id") or {}).get(batch_id)
    delta_path = (item or {}).get("delta_path")
    if not isinstance(delta_path, str):
        return _repair(
            result, "merge-ready-batch-has-no-delta-path",
            target={"batch_id": batch_id})
    return _invoke(
        result, "apply-delta", _route_capability(route), {
            "delta": delta_path,
            "actor_role": "integrator",
            "expected_coverage_sha256": result.get("coverage_sha256"),
            "expected_queue_sha256": result.get("queue_sha256"),
            "apply": True,
            "json": True,
        }, "merge-ready-delta-is-ready-to-apply",
        target={"batch_id": batch_id, "delta_path": delta_path})


def _resume_standards_revalidation(result, route, parameters, token):
    batch_id = parameters["batch_id"]
    aggregate_id = _current_standards_revalidation_aggregate(result, batch_id)
    if aggregate_id is None:
        return _await(
            result, "await-agent", token, _route_input(
                result, token, {"boundary_gate_receipts": "boundary_gate_receipt"},
                required=("boundary_gate_receipts",),
                shapes={"boundary_gate_receipts": {"type": "object", "properties": {},
                    "additionalProperties": {"type": "string", "minLength": 1}}},
                encodings={"boundary_gate_receipts": "key-value-items"}),
            "standards-revalidation-needs-current-boundary-evidence",
            target={"batch_id": batch_id})
    item = (result.get("items_by_id") or {}).get(batch_id) or {}
    if item.get("state") == "queued":
        boundary = _rendering_boundary(result, batch_id)
        if boundary is not None:
            return boundary
        return _invoke(
            result, "activate-revalidated-batch", _route_capability(route, 2), {
                "batch": batch_id,
                "standards_revalidation_receipt": aggregate_id,
            }, "queued-revalidation-aggregate-needs-activation-consumer",
            target={
                "batch_id": batch_id,
                "standards_revalidation_receipt": aggregate_id,
            })
    if item.get("state") != "open" or \
            item.get("hold_state") != "revalidation-required":
        return _repair(
            result, "revalidation-consumer-position-invalid",
            target={"batch_id": batch_id})
    queue = result.get("queue") or {}
    return _invoke(
        result, "consume-standards-revalidation", _route_capability(route, 1), {
            "id": batch_id,
            "hold_state": "none",
            "standards_revalidation_receipt": aggregate_id,
            "expected_state_revision": queue.get("state_revision"),
            "expected_sha256": result.get("queue_sha256"),
            "actor_role": "integrator",
            "apply": True,
            "json": True,
        }, "current-revalidation-aggregate-is-ready-for-consumption",
        target={
            "batch_id": batch_id,
            "standards_revalidation_receipt": aggregate_id,
        })


def _resume_batch_close_request(result, _route, parameters, _token):
    batch_id = parameters["batch_id"]
    return _await(
        result, "await-agent", "run-batch-close-gate", _route_input(
            result, "run-batch-close-gate", ("integrator", "reviewer", "review_attestation",
                "accept_candidate_id", "accept_candidate_type",
                "accept_while_unchanged_id", "accept_while_unchanged_type"),
            required=("integrator", "reviewer", "review_attestation")),
        "post-delta-close-needs-independent-attestation",
        target={"batch_id": batch_id})


def _resume_close_applied_batch(result, route, parameters, _token):
    batch_id = parameters["batch_id"]
    arguments = queue_runtime.batch_close_transition_arguments(result, {
        "batch": batch_id,
        "queue_consistency_receipt": parameters["queue_consistency_receipt"],
        "close_gate_receipt": parameters["close_gate_receipt"],
        "delta_apply_receipt": parameters["delta_apply_receipt"],
    })
    arguments["json"] = True
    return _invoke(
        result, "close-applied-batch", _route_capability(route), arguments,
        "current-close-bundle-is-complete", target={"batch_id": batch_id})


def _resume_enter_completion_candidate(result, route, _parameters, token):
    return _invoke(
        result, token, _route_capability(route), {},
        "required-queue-is-ready-for-completion-candidate",
        target={"task_id": (result.get("progress") or {}).get("task_id")})


def _resume_maintenance_completion_gate(result, _route, _parameters, token):
    return _await(
        result, "await-agent", token, _route_input(
            result, token, ("budget_manifest", "before_coverage_sha256", "before_watermark_sha256")),
        "maintenance-completion-evidence-needs-publication",
        target={"task_id": (result.get("progress") or {}).get("task_id")})


def _resume_complete_maintenance_task(result, route, parameters, _token):
    receipt_id = parameters["receipt_id"]
    return _invoke(
        result, "complete-maintenance-task", _route_capability(route), {
            "transition": "complete",
            "maintenance_completion_receipt": receipt_id,
            "checkpoint_summary": "bounded maintenance completion gate passed",
            "expected_progress_sha256": result.get("progress_sha256"),
            "expected_queue_sha256": result.get("queue_sha256"),
            "actor_role": "integrator",
            "apply": True,
            "json": True,
        }, "current-maintenance-completion-gate-is-selected",
        target={
            "task_id": (result.get("progress") or {}).get("task_id"),
            "maintenance_completion_receipt": receipt_id,
        })


def _resume_action(result):
    errors = list(result.get("errors") or [])
    token = queue_runtime.resume_next_action(result, errors)
    try:
        route, parameters = task_runtime_action.action_route_for_token(
            token, resume_source=True)
    except ValueError as exc:
        raise RunnerError(str(exc)) from exc
    handler = _RUNNER_ROUTE_HANDLERS.get(route.runner_route)
    if handler is None or handler.resume is None:
        raise RunnerError(
            "registered resume route %s has no Runner handler" %
            route.route_id)
    return handler.resume(result, route, parameters, token)


def next_action(root):
    """Read one authoritative snapshot and return its typed next action."""
    # An applied Task Plan intentionally precedes Required Queue
    # materialization.  The Runner admits that one empty-Queue boundary so it
    # can invoke the existing compiler; every non-empty Queue still receives
    # the ordinary full validation in the same validator.
    result = runtime_validation.validate_runtime(
        root, allow_unmaterialized_queue=True)
    try:
        return _resume_action(result)
    except HostEnvironmentUnavailable as exc:
        return _await_host_environment(result, None, {
            "result": "needs-preparation", "findings": [str(exc)],
            "diagnostics": [exc.diagnostic()]}, exc.constructs)


def _repository_tool_entrypoint(root, tool, relative):
    """Resolve one registered adapter inside the Tool root being executed."""
    if not isinstance(relative, str) or not relative.endswith(".py"):
        raise RunnerError(
            "compiled CLI contract gives %s no Python entrypoint" % tool)
    tools_root = os.path.realpath(os.path.join(root, "Tools"))
    script = os.path.realpath(os.path.join(root, relative))
    try:
        contained = os.path.commonpath((tools_root, script)) == tools_root
    except ValueError:
        contained = False
    if not contained or not os.path.isfile(script):
        raise RunnerError(
            "registered Tool entrypoint is absent or outside Tools: %s" %
            relative)
    return script


def _carried_cli_contract_currentness_check(root):
    """Run the contract owner's currentness check in the executed Tool root."""
    try:
        descriptor = entrypoint_loader.describe_entrypoint(
            compile_cli_contract.TOOL, os.path.join(root, "Tools"),
            require_marker=True)
    except entrypoint_loader.EntrypointResolutionError as exc:
        raise RunnerError(
            "carried-runtime CLI contract validator is unavailable: %s" %
            exc) from exc
    script = _repository_tool_entrypoint(
        root, compile_cli_contract.TOOL, descriptor.invocation_path)
    return kblib.run_cambium_subprocess(
        [sys.executable, script, root, "--check", "--projection-target",
         tool_availability.CARRIED_RUNTIME],
        cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False)


def _compiled_cli_contract(root):
    """Validate and load this adopter runtime's carried CLI contract.

    ``Tools/compiled/cli-contract.yaml`` describes the complete source
    distribution and is deliberately omitted from an adopter.  A Runner
    controls the reduced Tool surface installed in ``root``, so its only
    admissible invocation contract is the carried-runtime projection generated
    below that same root's derived namespace.  The compiler owner must prove
    the stored bytes current against that root's actual adapters,
    implementations, interface policy, runtime-path registry, and
    distribution boundary before any route in those bytes can be executed.
    """
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    try:
        path = kblib.managed_repository_path(
            root, runtime_paths.CLI_CONTRACT_ARTIFACT_PATH,
            runtime_paths.DERIVED_ROOT,
            suffixes=(".yaml",), must_exist=True)
        with open(path, "rb") as handle:
            before = handle.read()
    except (OSError, ValueError) as exc:
        raise RunnerError(
            "carried-runtime CLI contract cannot be loaded; generate it with "
            "`python3 Tools/compile_cli_contract.py . "
            "--projection-target carried-runtime`: %s" % exc) from exc
    checked = _carried_cli_contract_currentness_check(root)
    if checked.returncode != 0:
        details = (checked.stderr or checked.stdout or "").strip()
        raise RunnerError(
            "carried-runtime CLI contract is not current for the executed "
            "Tool root%s" % (": " + details if details else ""))
    try:
        with open(path, "rb") as handle:
            after = handle.read()
        if after != before:
            raise RunnerError(
                "carried-runtime CLI contract changed during currentness "
                "validation")
        document = kblib.parse_yaml_subset(after.decode("utf-8"))
    except (OSError, UnicodeError, kblib.YamlSubsetError, ValueError) as exc:
        raise RunnerError(
            "validated carried-runtime CLI contract cannot be loaded: %s" %
            exc) from exc
    if not isinstance(document, dict) or \
            document.get("artifact") != "cli-invocation-contract" or \
            not isinstance(document.get("tools"), list):
        raise RunnerError("compiled CLI contract has an invalid artifact shape")
    if document.get("projection_target") != "carried-runtime":
        raise RunnerError(
            "Runner requires a carried-runtime CLI contract; found %r" %
            document.get("projection_target"))
    return document


def _compiled_cli_tool(root, tool):
    document = _compiled_cli_contract(root)
    matches = [
        row for row in document["tools"]
        if isinstance(row, dict) and row.get("tool") == tool
    ]
    if len(matches) != 1:
        raise RunnerError(
            "compiled CLI contract resolves %s to %d entries" %
            (tool, len(matches)))
    return dict(matches[0], invocation_contract_source_hash=document.get("source_hash"))


def _compiled_entrypoint(root, tool, record):
    relative = record.get("module")
    return _repository_tool_entrypoint(root, tool, relative)


def _command_inputs(root, tool, arguments):
    record = _compiled_cli_tool(root, tool)
    script = _compiled_entrypoint(root, tool, record)
    schema = cli_argv_renderer.schema_from_compiled_tool(record)
    values = dict(arguments)
    interface = record.get("agent_interface") or {}
    workspace_argument = interface.get("workspace_argument")
    if not isinstance(workspace_argument, str) or \
            workspace_argument not in schema["properties"]:
        raise RunnerError(
            "compiled CLI contract gives %s no workspace argument" % tool)
    try:
        workspace_spelling = os.fspath(root)
    except TypeError as exc:
        raise RunnerError("Runner workspace has no filesystem spelling") \
            from exc
    supplied_root = values.get(workspace_argument)
    if supplied_root is not None:
        try:
            supplied_spelling = os.fspath(supplied_root)
        except TypeError as exc:
            raise RunnerError(
                "%s action carries an invalid workspace binding" % tool) \
                from exc
        if supplied_spelling != workspace_spelling:
            raise RunnerError(
                "%s action contradicts the Runner workspace binding" % tool)
    values[workspace_argument] = workspace_spelling
    return (script, schema, values, workspace_argument, interface["output"],
            record["host_environment_boundary"])


def _render_command(tool, script, schema, values):
    try:
        tail, _ignored = cli_argv_renderer.build_argv(
            tool, schema, values,
            transport_owned_argument=
            cli_argv_renderer.STRUCTURED_OUTPUT_ARGUMENT,
            transport_owned_flag=cli_argv_renderer.STRUCTURED_OUTPUT_FLAG)
    except cli_argv_renderer.ArgvRenderError as exc:
        raise RunnerError(exc.message, exc.data) from exc
    return [sys.executable, script] + tail


def _run_command(root, tool, arguments):
    observation = _EXECUTION_OBSERVATION.get()
    if observation is not None:
        observation.update(stage="parameter-admission", current_tool=tool)
    (script, schema, values, workspace_argument, output_contract,
     host_boundary) = _command_inputs(root, tool, arguments)
    retained_root = path_capability.controlled_root_fd()
    root_fd = (os.dup(retained_root) if retained_root is not None else
               os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
    try:
        actual = os.stat(root)
        retained = os.fstat(root_fd)
        if (actual.st_dev, actual.st_ino) != (retained.st_dev, retained.st_ino):
            raise RunnerError("Runner root differs from the invocation workspace")
        parent = path_capability.subprocess_kwargs().get("env_overrides", {})
        inherited = json.loads(parent.get(path_capability.PATH_CAPABILITIES_ENV,
                                         '{"capabilities":[]}'))["capabilities"]
        description = {"name": tool, "schema": schema,
                       "workspace_argument": workspace_argument}
        with path_admission.invocation(description, values, os.path.abspath(root),
                                       root_fd, os.environ,
                                       inherited_records=inherited) as binding:
            command = _render_command(tool, script, schema, binding["arguments"])
            if observation is not None:
                observation["stage"] = "dispatch"
            completed = kblib.run_cambium_subprocess(
                command, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                path_binding=binding, preexec_fn=lambda: os.fchdir(root_fd))
            if observation is not None:
                child = {"tool": tool, "tool_returncode": completed.returncode,
                         "output": completed.stdout, "diagnostics": completed.stderr}
                observation["substeps"].append(child)
                observation["stage"] = "output-admission"
        completed.tool_returncode = completed.returncode
        selected = dict(binding["arguments"])
        if cli_argv_renderer.STRUCTURED_OUTPUT_FLAG in command[2:]:
            selected[cli_argv_renderer.STRUCTURED_OUTPUT_ARGUMENT] = True
        observed = observe_tool_output(
            output_contract, completed.stdout.encode("utf-8"),
            completed.returncode, selected, host_boundary=host_boundary)
        errors = []
        if not observed["output_reliable"]:
            errors.append(observed.get("stdout_parse_error") or
                          "child output requires a stop or unresolved operation review")
        if completed.returncode in (0, 2) and binding["missing"]:
            errors.append("child did not consume admitted paths: %s" % binding["missing"])
        if binding["acknowledgement_error"]:
            errors.append(binding["acknowledgement_error"])
        completed.invocation_errors = errors
        if observation is not None:
            child.update(invocation_errors=errors, observation=observed)
            observation["stage"] = "handler-read-back"
        if errors:
            completed.returncode = 1
        return completed
    finally:
        os.close(root_fd)


def _json_output(completed):
    try:
        value = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RunnerError("Tool did not return canonical JSON: %s" % exc)
    return value


def _single_json_receipt(completed, predicate, label):
    rows = _json_output(completed)
    if isinstance(rows, dict) and "publication" in rows:
        if not publication_result_reliable(rows):
            raise RunnerError("%s publication is not confirmed" % label)
        rows = rows.get("receipts")
    if not isinstance(rows, list):
        raise RunnerError("%s did not return a receipt list" % label)
    matches = [row for row in rows
               if isinstance(row, dict) and predicate(row)]
    if len(matches) != 1:
        raise RunnerError("%s produced %d matching receipts" %
                          (label, len(matches)))
    return matches[0]


def _registered_gate_predicate(root, gate_id, *, extra=None):
    """Return a current K00/12 selector without restating producer fields."""
    registry, errors = gate_registry.standards_gate_registry(root)
    if errors:
        raise RunnerError(
            "%s Gate registry is invalid: %s" %
            (gate_id, "; ".join(errors)))

    def matches(row):
        return (isinstance(row, dict) and row.get("result") == "pass" and
                gate_registry.receipt_matches_gate_id(
                    row, gate_id, registry) and
                (extra is None or extra(row)))

    return matches


def _rendering_boundary(result, batch_id):
    """Check this batch's existing rendering seam without publishing evidence.

    The Profile owner supplies the already-admitted model, and the rendering
    owner alone selects constructs and checks their bindings. Missing future
    pages remain the existing admission/authoring owners' concern. This is a
    Host prerequisite, not an AuditPlan, successful check, or new Queue state.
    """
    root = result["root"]
    item = (result.get("items_by_id") or {}).get(batch_id) or {}
    manifest = item.get("manifest")
    if not isinstance(manifest, list):
        raise RunnerError("rendering preflight requires an admitted batch manifest")
    profile = profile_admission.contract_from_admitted_view(
        root, result.get("_profile_authorized_view"))
    pages = []
    for relative in manifest:
        snapshot = kblib.repository_target_snapshot(
            root, relative, suffixes=(".md", ".MD"), singly_linked=True)
        if snapshot.exists:
            pages.append((relative, snapshot.read_text()))
    try:
        selected = profile_rendering.require_bindings(pages, profile, root=root)
    except HostEnvironmentUnavailable as exc:
        return _await_host_environment(result, batch_id, {
            "result": "needs-preparation", "findings": [str(exc)],
            "diagnostics": [exc.diagnostic()]}, exc.constructs)
    except static_render_runtime.StaticRenderRuntimeError as exc:
        return _repair(result, "rendering-selector-failed", target={
            "batch_id": batch_id, "diagnostics": [str(exc)]})
    except ValueError as exc:
        return _repair(result, "profile-rendering-contract-gap", target={
            "batch_id": batch_id, "diagnostics": [str(exc)]})
    if not any(selected.values()):
        return None
    constructs = sorted({kind for kinds in selected.values() for kind in kinds})
    needs_browser = static_render_runtime.requires_browser(constructs, root=root)
    probe = static_render_runtime.probe_runtime(root, require_browser=needs_browser)
    if probe["result"] != "ready":
        if any(row.get("remedy") == "repair-contract" for row in probe.get("diagnostics", [])):
            return _repair(result, "rendering-selector-failed", target={
                "batch_id": batch_id, "diagnostics": probe["findings"]})
        return _await_host_environment(result, batch_id, probe, constructs)
    return None


def _await_host_environment(result, batch_id, probe, constructs):
    route = task_runtime_action.action_route("prepare-host-environment")
    capability = _route_capability(route)
    diagnostics = probe.get("diagnostics") or [{
        "capability_id": probe.get("capability_id", "static-markdown-render-v1"),
        "constructs": list(constructs), "message": "; ".join(probe["findings"])}]
    request = preparation_request(diagnostics)
    if request["capability_id"] != capability:
        raise RunnerError("Host preparation route differs from its request owner")
    return _await(result, "await-host", route.token_template, None,
        "host-environment-not-ready", target={
        "host_preparation": {
            **request,
            "tool": _capability_tool(result, capability),
            "instruction": (
                "Inspect first; apply preparation only with Host authorization, "
                "then query the Runner again. A supplied ready assertion is "
                "not accepted."),
        },
        "batch_id": batch_id, "runtime_result": probe["result"],
        "diagnostics": probe["findings"],
    })


def _require_rendering_ready(result, batch_id):
    boundary = _rendering_boundary(result, batch_id)
    if boundary is not None:
        raise RunnerError("batch activation prerequisite: " +
                          json.dumps(boundary, ensure_ascii=False, sort_keys=True))


def _activate_ready_batch(root, batch_id, *,
                          standards_revalidation_receipt=None):
    before = runtime_validation.validate_runtime(root)
    if before.get("errors"):
        raise RunnerError("runtime invalid before activation: %s" %
                          "; ".join(before["errors"]))
    # Recheck at execution before even the admission Receipt is written. An
    # earlier next_action observation is not a durable Host readiness claim.
    _require_rendering_ready(before, batch_id)
    route = task_runtime_action.action_route("activate-ready-batch")
    receipt_path = ACTIVATION_RECEIPT_TEMPLATE % batch_id.lower()
    checked = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 1), root=root), {
        "require_ready": batch_id,
        "receipts": receipt_path,
        "json": True,
    })
    if checked.returncode != 0:
        return checked
    rows = _json_output(checked)
    candidates = [row for row in rows if isinstance(row, dict) and
                  row.get("queue_check_mode") == "require-ready:%s" % batch_id]
    if len(candidates) != 1:
        raise RunnerError(
            "activation Gate produced %d matching receipts" % len(candidates))
    result = runtime_validation.validate_runtime(root)
    if result.get("errors"):
        raise RunnerError(
            "runtime changed after activation Gate: %s" %
            "; ".join(result["errors"]))
    _require_rendering_ready(result, batch_id)
    arguments = {
        "id": batch_id,
        "transition": "open",
        "gate_receipt": candidates[0]["receipt_id"],
        "expected_state_revision": result["queue"]["state_revision"],
        "expected_sha256": result["queue_sha256"],
        "actor_role": "integrator",
        "apply": True,
        "json": True,
    }
    if standards_revalidation_receipt is not None:
        arguments["standards_revalidation_receipt"] = \
            standards_revalidation_receipt
    completed = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 2), root=root), {
            **arguments,
        })
    if completed.returncode == 0:
        current = runtime_validation.validate_runtime(root)
        item = (current.get("items_by_id") or {}).get(batch_id) or {}
        if item.get("state") != "open":
            raise RunnerError(
                "activation writer succeeded without opening its batch")
        if standards_revalidation_receipt is not None and \
                queue_runtime.outstanding_standards_revalidation(
                    current, batch_id):
            raise RunnerError(
                "revalidated activation succeeded without consuming its "
                "authoritative aggregate")
    return completed


def _enter_completion_candidate(root):
    route = task_runtime_action.action_route("enter-completion-candidate")
    checked = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 1), root=root), {
        "require_complete": True,
        "receipts": COMPLETION_RECEIPT_PATH,
        "json": True,
    })
    if checked.returncode != 0:
        return checked
    rows = _json_output(checked)
    candidates = [
        row for row in rows if isinstance(row, dict) and
        row.get("queue_check_mode") == "require-complete"
    ]
    if len(candidates) != 1:
        raise RunnerError(
            "completion Gate produced %d matching receipts" %
            len(candidates))
    result = runtime_validation.validate_runtime(root)
    if result.get("errors"):
        raise RunnerError(
            "runtime changed after completion Gate: %s" %
            "; ".join(result["errors"]))
    completed = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 2), root=root), {
                "transition": "completion-candidate",
                "queue_check_receipt": candidates[0]["receipt_id"],
                "checkpoint_summary": (
                    "all Required work units are terminal"),
                "expected_progress_sha256": result["progress_sha256"],
                "expected_queue_sha256": result["queue_sha256"],
                "actor_role": "integrator",
                "apply": True,
                "json": True,
            })
    if completed.returncode == 0:
        current = runtime_validation.validate_runtime(root)
        if (current.get("progress") or {}).get("task_state") != \
                "completion-candidate":
            raise RunnerError(
                "task transition succeeded without entering "
                "completion-candidate")
    return completed


def _invoke_registered_tool(root, action):
    return _run_command(root, action["tool"], action["arguments"])


def _invoke_activate_ready_batch(root, action):
    return _activate_ready_batch(root, action["target"]["batch_id"])


def _invoke_enter_completion_candidate(root, _action):
    return _enter_completion_candidate(root)


def _invoke_activate_revalidated_batch(root, action):
    return _activate_ready_batch(
        root, action["target"]["batch_id"],
        standards_revalidation_receipt=action["target"][
            "standards_revalidation_receipt"])


def _invoke_consume_standards_revalidation(root, action):
    completed = _run_command(root, action["tool"], action["arguments"])
    if completed.returncode == 0:
        current = runtime_validation.validate_runtime(root)
        batch_id = action["target"]["batch_id"]
        item = (current.get("items_by_id") or {}).get(batch_id) or {}
        outstanding = queue_runtime.outstanding_standards_revalidation(
            current, batch_id)
        if item.get("hold_state") != "none" or outstanding:
            raise RunnerError(
                "Standards revalidation consumer succeeded without clearing "
                "its authoritative obligation")
    return completed


def _internal_step(root, action):
    try:
        route = task_runtime_action.action_route(action["token"])
    except ValueError:
        # Audit planning and activation-phase delivery are selected by their
        # own already-typed producers rather than by a Task Runtime route.
        return _invoke_registered_tool(root, action)
    if route.action_disposition != "invoke":
        raise RunnerError(
            "action %s is not registered as an invoke route" %
            action["token"])
    handler = _RUNNER_ROUTE_HANDLERS.get(route.runner_route)
    if handler is None or handler.invoke is None:
        raise RunnerError(
            "action %s has no invoke handler" % action["token"])
    return handler.invoke(root, action)


def _require_input(action, supplied):
    if action["required_input"] is None:
        raise RunnerError("external resolution has no submittable input")
    return interface_contract.bind_input(action["required_input"], supplied)


def _current_audit_step(root, action):
    result = runtime_validation.validate_runtime(root)
    item = (result.get("items_by_id") or {}).get(
        action["target"].get("batch_id"))
    if not isinstance(item, dict) or item.get("state") != "open":
        raise RunnerError("awaited audit action no longer targets an open batch")
    return result, item, audit_execution_runtime.next_stage_step(
        result, item, "pre-merge", required_state="open")


def _await_external_reparse(_root, action, _supplied, _route):
    raise RunnerError(
        "action %s is resolved outside the Runner; derive a new action after "
        "the authoritative state changes" % action["token"])


def _await_task_transition(root, action, supplied, route):
    transition = supplied["transition"]
    summary = supplied["checkpoint_summary"]
    result = runtime_validation.validate_runtime(root)
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), {
                "transition": transition,
                "checkpoint_summary": summary,
                "expected_progress_sha256": result["progress_sha256"],
                "expected_queue_sha256": result["queue_sha256"],
                "actor_role": "integrator",
                "apply": True,
                "json": True,
            })


def _await_maintenance_completion_gate(root, _action, supplied, route):
    published = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 0), root=root), {
                "budget_manifest": supplied["budget_manifest"],
                "before_coverage_sha256": supplied["before_coverage_sha256"],
                "before_watermark_sha256": supplied["before_watermark_sha256"],
                "apply": True,
                "json": True,
            })
    if published.returncode != 0:
        return published
    rows = _json_output(published)
    receipt_ids = {}
    expected = {
        "maintenance_budget_manifest": "budget_manifest_receipt",
        "maintenance_ledger_advanced": "ledger_advance_receipt",
        "maintenance_watermark_advanced": "watermark_advance_receipt",
    }
    for row in rows if isinstance(rows, list) else ():
        field = expected.get(row.get("check")) if isinstance(row, dict) else None
        if field is not None and isinstance(row.get("receipt_id"), str):
            if field in receipt_ids:
                raise RunnerError("maintenance evidence produced duplicate %s" %
                                  field)
            receipt_ids[field] = row["receipt_id"]
    if set(receipt_ids) != set(expected.values()):
        raise RunnerError("maintenance evidence did not produce exactly the current three Receipt kinds")
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 1), root=root), {
                "require_maintenance_complete": True,
                **receipt_ids,
                "receipts": MAINTENANCE_GATE_RECEIPT_PATH,
                "json": True,
            })


def _await_standards_revalidation(root, action, supplied, route):
    boundary = supplied["boundary_gate_receipt"]
    batch_id = action["target"].get("batch_id")
    receipt_path = runtime_paths.child_path(
        runtime_paths.RECEIPT_ROOT,
        "standards-revalidation-%s.jsonl" % batch_id.lower())
    completed = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), {
                "require_revalidation": batch_id,
                "boundary_gate_receipt": boundary,
                "receipts": receipt_path,
                "json": True,
            })
    if completed.returncode == 0:
        current = runtime_validation.validate_runtime(root)
        aggregate_id = _current_standards_revalidation_aggregate(
            current, batch_id)
        if aggregate_id is None:
            raise RunnerError(
                "Standards revalidation producer succeeded without a "
                "current authoritative aggregate")
    return completed


def _await_terminal_audit(root, action, supplied, route):
    input_path = supplied["terminal_audit_input"]
    assemble_terminal_proof.read_terminal_audit_input(root, input_path)

    queue_completed = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 0), root=root), {
                "require_complete": True,
                "receipts": TERMINAL_RECEIPT_PATH,
                "json": True,
            })
    if queue_completed.returncode != 0:
        return queue_completed
    queue_receipt = _single_json_receipt(
        queue_completed, _registered_gate_predicate(
            root, "required-queue-completion",
            extra=lambda row:
                row.get("queue_check_mode") == "require-complete"),
        "Terminal Required Queue Gate")

    corpus_completed = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 1), root=root), {
                "receipts": TERMINAL_RECEIPT_PATH,
                "json": True,
            })
    if corpus_completed.returncode != 0:
        return corpus_completed
    corpus_receipt = _single_json_receipt(
        corpus_completed, _registered_gate_predicate(
            root, "corpus-plan-structure"),
        "Terminal Corpus Plan Gate")

    assembled = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 2), root=root), {
                "terminal_audit_input": input_path,
                "queue_check_receipt": queue_receipt["receipt_id"],
                "corpus_plan_check_receipt": corpus_receipt["receipt_id"],
                "audit_receipt_register":
                    runtime_paths.AUDIT_RECEIPT_REGISTER_PATH,
                "terminal_audit_receipt_register": TERMINAL_RECEIPT_PATH,
                "full_deterministic_results":
                    runtime_paths.AUDIT_RECEIPT_REGISTER_PATH,
                "proof": TERMINAL_PROOF_PATH,
                "apply": True,
                "json": True,
            })
    if assembled.returncode != 0:
        return assembled
    assembled_result = _json_output(assembled)
    if (not isinstance(assembled_result, dict) or
            assembled_result.get("status") != "produced" or
            assembled_result.get("terminal_proof_path") !=
            TERMINAL_PROOF_PATH):
        raise RunnerError(
            "Terminal Proof producer did not report the canonical result")

    checked = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 3), root=root), {
                "proof": TERMINAL_PROOF_PATH,
                "ledger": runtime_paths.COVERAGE_PATH,
                "progress_ledger": runtime_paths.PROGRESS_PATH,
                "receipts": TERMINAL_RECEIPT_PATH,
                "json": True,
            })
    if checked.returncode != 0:
        return checked
    proof_receipt = _single_json_receipt(
        checked, _registered_gate_predicate(root, "terminal-proof"),
        "Terminal Proof Gate")

    current = runtime_validation.validate_runtime(root)
    if current.get("errors"):
        raise RunnerError(
            "runtime changed after Terminal Proof Gate: %s" %
            "; ".join(current["errors"]))
    completed = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route, 4), root=root), {
                "transition": "complete",
                "terminal_proof_receipt": proof_receipt["receipt_id"],
                "checkpoint_summary": (
                    "current Terminal Proof Gate passed"),
                "expected_progress_sha256": current["progress_sha256"],
                "expected_queue_sha256": current["queue_sha256"],
                "actor_role": "integrator",
                "apply": True,
                "json": True,
            })
    if completed.returncode == 0:
        resulting = runtime_validation.validate_runtime(root)
        if (resulting.get("progress") or {}).get("task_state") != "complete":
            raise RunnerError(
                "Terminal completion writer succeeded without completing task")
    return completed


def _await_audit_producer(root, action, supplied, _route):
    token = action["token"]
    _result, _item, step = _current_audit_step(root, action)
    if step.get("token") != token:
        raise RunnerError("awaited audit action is no longer current")
    arguments = dict(step["resume_arguments"])
    arguments.update(supplied)
    if token == "record-batch-page-review":
        batch_review_obligation_contract.validate_review_input(
            step["target"]["review_input_constraints"],
            arguments.get("applicability_disposition"), arguments.get("applicability_reason"))
    elif token == "record-rendering-verification":
        rendering_verification_contract.rendering_input(
            **{field: arguments.get(field) for field in ("rendering_mode", "visual_trigger",
                "unresolved_question", "verification_target", "verification_result")},
            contract=rendering_verification_contract.load_contract(root))
    arguments["apply"] = True
    return _run_command(root, step["resume_tool"], arguments)


def _await_candidate_delta(root, action, supplied, route):
    proposal = supplied["proposal"]
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), {
                "batch": action["target"].get("batch_id"),
                "proposal": proposal,
                "expected_delta_sha256": action["target"].get("candidate_delta_sha256", "absent"),
                "apply": True,
            })


def _await_batch_review(root, action, supplied, route):
    statement = supplied["statement"]
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), {
                "batch": action["target"].get("batch_id"),
                "actor_role": "integrator",
                "statement": statement,
                "apply": True,
                "json": True,
            })


def _await_batch_close(root, action, supplied, route):
    arguments = {"batch": action["target"].get("batch_id"), "json": True}
    arguments.update(supplied)
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), arguments)


def _await_activation_ack(root, action, supplied, route):
    phase_nonce = supplied.get("phase_nonce")
    delivery_receipt = supplied.get("phase_delivery_receipt")
    batch_id = action["target"].get("batch_id")
    phase_id = action["target"].get("phase_id")
    part_index = action["target"].get("part_index")
    receipt_path = runtime_paths.child_path(
        runtime_paths.RECEIPT_ROOT,
        "phase-ack-%s-%s-%d.jsonl" % (
            batch_id.lower(), phase_id, part_index))
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), {
                "ack_activation_phase": batch_id,
                "phase": phase_id,
                "phase_part": part_index,
                "phase_nonce": phase_nonce,
                "phase_delivery_receipt": delivery_receipt,
                "receipts": receipt_path,
                "json": True,
            })


_RUNNER_ROUTE_HANDLERS = {
    "repair": _RunnerRouteHandler(resume=_resume_repair),
    "terminal": _RunnerRouteHandler(resume=_resume_terminal),
    "task-transition": _RunnerRouteHandler(
        resume=_resume_task_transition,
        await_input=_await_task_transition),
    "external-reparse": _RunnerRouteHandler(
        resume=_resume_external_reparse,
        await_input=_await_external_reparse),
    "terminal-audit": _RunnerRouteHandler(
        resume=_resume_terminal_audit,
        await_input=_await_terminal_audit),
    "standards-revalidation": _RunnerRouteHandler(
        resume=_resume_standards_revalidation,
        await_input=_await_standards_revalidation),
    "apply-delta": _RunnerRouteHandler(
        resume=_resume_apply_delta,
        invoke=_invoke_registered_tool),
    "open-batch-audit": _RunnerRouteHandler(
        resume=_resume_open_batch_audit),
    "batch-close-request": _RunnerRouteHandler(
        resume=_resume_batch_close_request),
    "close-applied-batch": _RunnerRouteHandler(
        resume=_resume_close_applied_batch,
        invoke=_invoke_registered_tool),
    "complete-maintenance-task": _RunnerRouteHandler(
        resume=_resume_complete_maintenance_task,
        invoke=_invoke_registered_tool),
    "maintenance-completion-gate": _RunnerRouteHandler(
        resume=_resume_maintenance_completion_gate,
        await_input=_await_maintenance_completion_gate),
    "enter-completion-candidate": _RunnerRouteHandler(
        resume=_resume_enter_completion_candidate,
        invoke=_invoke_enter_completion_candidate),
    "activate-ready-batch": _RunnerRouteHandler(
        resume=_resume_activate_ready_batch,
        invoke=_invoke_activate_ready_batch),
    "materialize-required-queue": _RunnerRouteHandler(
        resume=_resume_materialize_required_queue,
        invoke=_invoke_registered_tool),
    "activation-ack": _RunnerRouteHandler(
        await_input=_await_activation_ack),
    "audit-producer": _RunnerRouteHandler(
        await_input=_await_audit_producer),
    "candidate-delta": _RunnerRouteHandler(
        await_input=_await_candidate_delta),
    "batch-review": _RunnerRouteHandler(
        await_input=_await_batch_review),
    "batch-close": _RunnerRouteHandler(
        await_input=_await_batch_close),
    "consume-standards-revalidation": _RunnerRouteHandler(
        invoke=_invoke_consume_standards_revalidation),
    "activate-revalidated-batch": _RunnerRouteHandler(
        invoke=_invoke_activate_revalidated_batch),
    "transition-batch-merge-ready": _RunnerRouteHandler(
        invoke=_invoke_registered_tool),
}


def _continue_awaited(root, action, supplied):
    supplied = _require_input(action, supplied)
    token = action["token"]
    try:
        route, _parameters = task_runtime_action.action_route_for_token(token)
    except ValueError as exc:
        raise RunnerError(str(exc)) from exc
    if route.action_disposition not in task_runtime_action.AWAIT_DISPOSITIONS:
        raise RunnerError("action %s is not a registered await route" % token)
    handler = _RUNNER_ROUTE_HANDLERS.get(route.runner_route)
    if handler is None or handler.await_input is None:
        raise RunnerError("action %s has no await-input handler" % token)
    return handler.await_input(root, action, supplied, route)


def execute(root, expected_action_id, input_record=None):
    """Execute exactly the current action and return its authoritative result."""
    action = next_action(root)
    if action["action_id"] != expected_action_id:
        raise RunnerError(
            "next action changed; expected %s, current %s" %
            (expected_action_id, action["action_id"]))
    return _execute_observed(root, action, input_record)


def _execute_observed(root, action, input_record=None):
    """Use this call's observed action; the selected writer still performs CAS."""
    observation = {"stage": "action-input", "current_tool": None, "substeps": []}
    context = _EXECUTION_OBSERVATION.set(observation)
    completed = None
    failure = None
    try:
        if action["disposition"] == "invoke":
            if input_record is not None:
                raise RunnerError("invoke action does not accept input_record")
            completed = _internal_step(root, action)
        elif action["disposition"] in task_runtime_action.AWAIT_DISPOSITIONS:
            if input_record is None:
                raise RunnerError("await action requires input_record")
            completed = _continue_awaited(root, action, input_record)
        else:
            raise RunnerError("%s action cannot be executed" % action["disposition"])
    except (OSError, TypeError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        failure = {"stage": observation["stage"], "tool": observation["current_tool"],
                   "message": str(exc), "details": getattr(exc, "data", None)}
    finally:
        _EXECUTION_OBSERVATION.reset(context)
    try:
        next_value = next_action(root)
    except HostEnvironmentUnavailable as exc:
        next_value = None
        next_error = {"status": "await-host", "host_environment": exc.diagnostic(),
                      "host_preparation": preparation_request([exc.diagnostic()])}
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        next_value = None
        next_error = str(exc)
    else:
        next_error = None
    return {
        "requested_action_id": action["action_id"],
        "executed_action_id": action["action_id"] if observation["substeps"] or completed is not None else None,
        "executed_token": action["token"] if observation["substeps"] or completed is not None else None,
        "execution_status": ("dispatch-unresolved" if failure and observation["stage"] == "dispatch" else
                             "not-dispatched" if failure and not observation["substeps"] else
                             "stopped-after-dispatch" if failure else "returned"),
        "failure": failure,
        "substeps": observation["substeps"],
        "returncode": completed.returncode if completed is not None else 1,
        "tool_returncode": getattr(completed, "tool_returncode", completed.returncode)
            if completed is not None else None,
        "invocation_errors": getattr(completed, "invocation_errors", []),
        "output": completed.stdout if completed is not None else "",
        "diagnostics": completed.stderr if completed is not None else failure["message"],
        "next_action": next_value,
        "next_action_error": next_error,
    }


def run_until_boundary(root, *, max_steps=64):
    """Run deterministic invoke actions until a semantic or repair boundary."""
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or \
            max_steps < 1:
        raise RunnerError("max_steps must be a positive integer")
    executed = []
    action = next_action(root)
    for _index in range(max_steps):
        if action["disposition"] != "invoke":
            return {"executed": executed, "next_action": action}
        outcome = _execute_observed(root, action)
        executed.append({
            "action_id": action["action_id"],
            "token": action["token"],
            "returncode": outcome["returncode"],
            "tool_returncode": outcome.get("tool_returncode", outcome["returncode"]),
            "invocation_errors": outcome.get("invocation_errors", []),
            "output": outcome["output"],
            "diagnostics": outcome["diagnostics"],
            "execution_status": outcome["execution_status"],
            "failure": outcome["failure"],
            "substeps": outcome["substeps"],
        })
        if outcome["returncode"] != 0:
            return {
                "executed": executed,
                "next_action": outcome["next_action"],
                "next_action_error": outcome["next_action_error"],
            }
        if (outcome["next_action"] is not None and
                outcome["next_action"]["action_id"] == action["action_id"]):
            raise RunnerError(
                "successful Tool invocation did not advance its action")
        if outcome["next_action"] is None:
            return {"executed": executed, "next_action": None,
                    "next_action_error": outcome["next_action_error"]}
        action = outcome["next_action"]
    raise RunnerError("max_steps reached before a boundary")


def _input_record(root, relative_path):
    if relative_path is None:
        return None
    relative_path = canonical_repository_relative_path(
        relative_path, "input")
    prefix = runtime_paths.TRANSIENT_ROOT + "/"
    if not relative_path.startswith(prefix) or not relative_path.endswith(
            ".json"):
        raise ValueError(
            "input must be a .json file below %s" %
            runtime_paths.TRANSIENT_ROOT)
    absolute = kblib.repository_path(
        root, relative_path, must_exist=True, reject_symlink=True)
    value = json.loads(kblib.read_text(absolute))
    if not isinstance(value, dict):
        raise ValueError("input JSON must contain one object")
    return value


def _proposal_record(relative_path):
    if relative_path is None:
        return None
    relative_path = canonical_repository_relative_path(
        relative_path, "proposal")
    prefix = runtime_paths.TRANSIENT_ROOT + "/"
    if (not relative_path.startswith(prefix) or
            not relative_path.endswith(".yaml")):
        raise ValueError(
            "proposal must be a .yaml file below %s" %
            runtime_paths.TRANSIENT_ROOT)
    return {"proposal": relative_path}


def main(argv=None):
    """Expose the deterministic runtime dispatcher as one typed CLI."""
    parser = kblib.ArgumentParser(
        description=(
            "Read the current Task Runtime action, execute that exact action, "
            "or advance deterministic actions to the next semantic boundary."))
    parser.add_argument("root", help="adopting repository root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--execute", metavar="ACTION_ID",
        help="execute exactly this current action identity")
    mode.add_argument(
        "--run-until-boundary", action="store_true",
        help="advance invoke actions until Agent, user, Host, repair, or terminal")
    await_input = parser.add_mutually_exclusive_group()
    await_input.add_argument(
        "--input",
        help=("repository-relative JSON object below %s for await input" %
              runtime_paths.TRANSIENT_ROOT))
    await_input.add_argument(
        "--proposal",
        help=("candidate Delta YAML below %s for the current publication "
              "action" % runtime_paths.TRANSIENT_ROOT))
    parser.add_argument(
        "--max-steps", type=int, default=64,
        help="maximum deterministic actions for --run-until-boundary")
    parser.add_argument(
        "--json", action="store_true",
        help=("emit the canonical machine result; output is always JSON and "
              "this flag marks that contract for transports"))
    args = parser.parse_args(argv)

    try:
        if args.input and not args.execute:
            raise ValueError("--input requires --execute")
        if args.proposal and not args.execute:
            raise ValueError("--proposal requires --execute")
        if args.max_steps != 64 and not args.run_until_boundary:
            raise ValueError("--max-steps requires --run-until-boundary")
        if args.execute:
            input_record = (_input_record(args.root, args.input) if args.input is not None
                            else _proposal_record(args.proposal))
            result = execute(
                args.root, args.execute, input_record=input_record)
        elif args.run_until_boundary:
            result = run_until_boundary(
                args.root, max_steps=args.max_steps)
        else:
            result = next_action(args.root)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        write_canonical_json({"status": "invalid", "errors": [str(exc)]})
        return 1

    write_canonical_json(result)
    if args.execute or args.run_until_boundary:
        codes = ([result.get("returncode")] if args.execute else
                 [row.get("returncode") for row in result.get("executed", [])])
        failures = [code for code in codes if code not in (None, 0)]
        if failures:
            return failures[0]
        if result.get("next_action_error") is not None:
            return 1
    return 0


__all__ = [
    'main',
]
