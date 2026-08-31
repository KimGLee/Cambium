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

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_execution_runtime as audit_execution_runtime
import Tools.execution.audit.assemble_terminal_proof as assemble_terminal_proof
import Tools.execution.audit.batch_review_receipt_contract as batch_review_receipt_contract
import Tools.platform.common.kblib as kblib
import Tools.platform.agent_interface.cli_argv_renderer as cli_argv_renderer
import Tools.platform.agent_interface.compile_cli_contract as compile_cli_contract
import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader
import Tools.platform.agent_interface.tool_availability as tool_availability
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.gate_registry as gate_registry
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.task_runtime.task_runtime_action as task_runtime_action
from Tools.platform.common.primitives import catalog_record
from Tools.platform.common.reporting import write_canonical_json


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


class RunnerError(ValueError):
    """The Runner cannot safely derive or execute one current action."""


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
            result, "await-agent", "ack-activation-phase", {
                "phase_nonce": "nonce from the delivered phase payload",
                "phase_delivery_receipt":
                    "receipt_id returned with that payload",
            }, "delivered-phase-needs-same-context-ack", target=target)
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
        return _await(
            result, step["status"], step["token"], step["required_input"],
            step["reason_code"], target=target, plan_sha256=plan_sha)
    if step["status"] == "repair":
        return _repair(result, step["reason_code"], target=target)
    if step["status"] != "complete":
        return _repair(result, "unknown-audit-execution-status", target=target)

    delta = _managed_candidate_delta(result, item)
    if delta is None:
        return _await(
            result, "await-agent", "publish-candidate-delta", {
                "proposal": (
                    "repository-relative YAML path under %s" %
                    runtime_paths.TRANSIENT_ROOT),
            }, "batch-work-needs-candidate-delta",
            target={"batch_id": item["id"]},
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
            result, "await-agent", "record-batch-review", {
                "statement": "non-empty bounded integrator statement",
            }, "pre-merge-closure-needs-integrator-attestation",
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
              if "batch_id" in parameters else None)
    return _repair(result, route.route_id, target=target)


def _resume_terminal(result, _route, _parameters, token):
    return _action(
        result, disposition="terminal", token=token,
        reason_code="task-runtime-is-terminal")


def _resume_task_transition(result, route, _parameters, token):
    paused = route.route_id == "resume-paused-task"
    return _await(
        result, "await-user", token, {
            "task_transition": (
                "active|cancelled" if paused else
                "active|paused|cancelled"),
            "checkpoint_summary": "string",
        }, ("paused-task-needs-user-direction" if paused else
            "blocked-task-needs-user-direction"))


def _resume_external_reparse(result, route, _parameters, token):
    runtime = result.get("task_runtime") or {}
    target = {}
    reason = "runtime-boundary-needs-authoritative-external-change"
    required = {"external_resolution": (
        "use the named canonical owner, then derive the next action again")}
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
        result, route.action_disposition, token, required, reason,
        target=target)


def _resume_terminal_audit(result, _route, _parameters, token):
    terminal = (result.get("progress") or {}).get("terminal_audit") or {}
    return _await(
        result, "await-agent", token, {
            "terminal_audit_input": (
                "repository-relative .yaml/.json below .cambium/tmp"),
        }, "completion-candidate-needs-terminal-audit-input",
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
            result, "await-agent", token, {
                "boundary_gate_receipts": (
                    "mapping of required Gate ID to current receipt ID"),
            }, "standards-revalidation-needs-current-boundary-evidence",
            target={"batch_id": batch_id})
    item = (result.get("items_by_id") or {}).get(batch_id) or {}
    if item.get("state") == "queued":
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
        result, "await-agent", "run-batch-close-gate", {
            "integrator": "string",
            "reviewer": "string",
            "review_attestation": "non-empty independent statement",
            "accept_candidate_id": "list",
            "accept_candidate_type": "list",
            "accept_while_unchanged_id": "list",
            "accept_while_unchanged_type": "list",
        }, "post-delta-close-needs-independent-attestation",
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
        result, "await-agent", token, {
            "budget_manifest": "closed manifest path under .cambium/receipts",
            "before_coverage_sha256": "Coverage before-image fingerprint",
            "before_watermark_sha256": "watermark before-image fingerprint",
        }, "maintenance-completion-evidence-needs-publication",
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
    return _resume_action(result)


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
    matches = [
        row for row in _compiled_cli_contract(root)["tools"]
        if isinstance(row, dict) and row.get("tool") == tool
    ]
    if len(matches) != 1:
        raise RunnerError(
            "compiled CLI contract resolves %s to %d entries" %
            (tool, len(matches)))
    return matches[0]


def _compiled_entrypoint(root, tool, record):
    relative = record.get("module")
    return _repository_tool_entrypoint(root, tool, relative)


def _command(root, tool, arguments):
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
    try:
        tail, _ignored = cli_argv_renderer.build_argv(
            tool, schema, values,
            transport_owned_argument=
            cli_argv_renderer.STRUCTURED_OUTPUT_ARGUMENT,
            transport_owned_flag=cli_argv_renderer.STRUCTURED_OUTPUT_FLAG)
    except cli_argv_renderer.ArgvRenderError as exc:
        raise RunnerError(exc.message) from exc
    return [sys.executable, script] + tail


def _run_command(root, tool, arguments):
    command = _command(root, tool, arguments)
    return kblib.run_cambium_subprocess(
        command, cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False)


def _json_output(completed):
    try:
        value = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RunnerError("Tool did not return canonical JSON: %s" % exc)
    return value


def _single_json_receipt(completed, predicate, label):
    rows = _json_output(completed)
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


def _activate_ready_batch(root, batch_id, *,
                          standards_revalidation_receipt=None):
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
    if not isinstance(supplied, dict):
        raise RunnerError("await action input must be a mapping")
    allowed = set(action["required_input"])
    extra = sorted(set(supplied) - allowed)
    if extra:
        raise RunnerError(
            "await action input has unsupported field(s): %s" %
            ", ".join(extra))
    return supplied


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
    token = action["token"]
    transition = supplied.get("task_transition")
    allowed = ({"active", "cancelled"} if token == "resume-paused-task" else
               {"active", "paused", "cancelled"})
    if transition not in allowed:
        raise RunnerError(
            "%s requires task_transition in %s" %
            (token, ", ".join(sorted(allowed))))
    summary = supplied.get("checkpoint_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise RunnerError("%s requires checkpoint_summary" % token)
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
    required = {
        "budget_manifest",
        "before_coverage_sha256",
        "before_watermark_sha256",
    }
    missing = sorted(
        field for field in required
        if not isinstance(supplied.get(field), str) or
        not supplied[field].strip())
    if missing:
        raise RunnerError(
            "maintenance completion input misses: %s" % ", ".join(missing))
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
    boundary = supplied.get("boundary_gate_receipts")
    if not isinstance(boundary, dict):
        raise RunnerError(
            "Standards revalidation requires boundary_gate_receipts as a "
            "mapping")
    malformed = sorted(
        key for key, value in boundary.items()
        if not isinstance(key, str) or not key.strip() or
        not isinstance(value, str) or not value.strip())
    if malformed:
        raise RunnerError(
            "Standards revalidation boundary receipt mapping is invalid")
    batch_id = action["target"].get("batch_id")
    receipt_path = runtime_paths.child_path(
        runtime_paths.RECEIPT_ROOT,
        "standards-revalidation-%s.jsonl" % batch_id.lower())
    completed = _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), {
                "require_revalidation": batch_id,
                "boundary_gate_receipt": [
                    "%s=%s" % (gate_id, receipt_id)
                    for gate_id, receipt_id in sorted(boundary.items())
                ],
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
    input_path = supplied.get("terminal_audit_input")
    if not isinstance(input_path, str) or not input_path:
        raise RunnerError(
            "run-terminal-audit requires terminal_audit_input")

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
    if token == "record-substantive-review":
        findings = arguments.pop("findings", [])
        arguments["finding"] = [json.dumps(
            row, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")) for row in findings]
    elif token == "record-batch-page-review":
        references = arguments.pop("consumed_evidence_refs", [])
        arguments["consumed_evidence_ref"] = references
    arguments["apply"] = True
    return _run_command(root, step["resume_tool"], arguments)


def _await_candidate_delta(root, action, supplied, route):
    proposal = supplied.get("proposal")
    if not isinstance(proposal, str) or not proposal:
        raise RunnerError("publish-candidate-delta requires proposal")
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), {
                "batch": action["target"].get("batch_id"),
                "proposal": proposal,
                "expected_delta_sha256": "absent",
                "apply": True,
            })


def _await_batch_review(root, action, supplied, route):
    statement = supplied.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        raise RunnerError("record-batch-review requires statement")
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
    required = {"integrator", "reviewer", "review_attestation"}
    missing = sorted(
        key for key in required
        if not isinstance(supplied.get(key), str) or
        not supplied[key].strip())
    if missing:
        raise RunnerError("batch-close input misses: %s" % ", ".join(missing))
    arguments = {"batch": action["target"].get("batch_id"), "json": True}
    arguments.update(supplied)
    return _run_command(
        root, metadata_execution_contract.capability_invocation_tool(
            _route_capability(route), root=root), arguments)


def _await_activation_ack(root, action, supplied, route):
    phase_nonce = supplied.get("phase_nonce")
    delivery_receipt = supplied.get("phase_delivery_receipt")
    if (not isinstance(phase_nonce, str) or not phase_nonce or
            not isinstance(delivery_receipt, str) or not delivery_receipt):
        raise RunnerError(
            "activation phase ack requires nonce and delivery receipt")
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
    if action["disposition"] == "invoke":
        if input_record is not None:
            raise RunnerError("invoke action does not accept input_record")
        completed = _internal_step(root, action)
    elif action["disposition"] in task_runtime_action.AWAIT_DISPOSITIONS:
        if input_record is None:
            raise RunnerError("await action requires input_record")
        completed = _continue_awaited(root, action, input_record)
    else:
        raise RunnerError(
            "%s action cannot be executed" % action["disposition"])
    try:
        next_value = next_action(root)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        next_value = None
        next_error = str(exc)
    else:
        next_error = None
    return {
        "executed_action_id": action["action_id"],
        "executed_token": action["token"],
        "returncode": completed.returncode,
        "output": completed.stdout,
        "diagnostics": completed.stderr,
        "next_action": next_value,
        "next_action_error": next_error,
    }


def run_until_boundary(root, *, max_steps=64):
    """Run deterministic invoke actions until a semantic or repair boundary."""
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or \
            max_steps < 1:
        raise RunnerError("max_steps must be a positive integer")
    executed = []
    for _index in range(max_steps):
        action = next_action(root)
        if action["disposition"] != "invoke":
            return {"executed": executed, "next_action": action}
        outcome = execute(root, action["action_id"])
        executed.append({
            "action_id": action["action_id"],
            "token": action["token"],
            "returncode": outcome["returncode"],
            "output": outcome["output"],
            "diagnostics": outcome["diagnostics"],
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
            input_record = _input_record(args.root, args.input) or \
                _proposal_record(args.proposal)
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
    if args.execute and result.get("returncode") not in (None, 0):
        return result["returncode"]
    return 0


__all__ = [
    'main',
]
