"""Closed machine contract for one Task Runtime next action.

This module only defines the typed handoff between the deterministic planner
and Runner.  It does not select an action, resolve a capability, invoke a Tool,
read adopter state, or interpret Agent/user input.  In particular,
``arguments`` is structured data and never a shell command string.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Optional

import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import require_trimmed_string


SCHEMA_VERSION = 1
ACTION_FIELDS = frozenset((
    "schema_version",
    "action_id",
    "disposition",
    "token",
    "capability_id",
    "tool",
    "target",
    "arguments",
    "required_input",
    "binding",
    "reason_code",
))
MACHINE_FIELDS = ACTION_FIELDS - {"action_id"}
DISPOSITIONS = frozenset((
    "invoke",
    "await-agent",
    "await-user",
    "await-host",
    "repair",
    "terminal",
))
AWAIT_DISPOSITIONS = frozenset((
    "await-agent",
    "await-user",
    "await-host",
))
ACTION_ID_RE = re.compile(r"action-[0-9a-f]{64}\Z")
REASON_CODE_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


@dataclass(frozen=True)
class ActionRoute:
    """One closed token family and its Task Runtime control ownership.

    ``resume.py`` owns precedence between runtime facts, but it does not own
    token grammar or execution routing.  The Runner owns dispatch, but it does
    not privately reinterpret token spelling or capability identity.  This
    registry is the shared machine boundary between those two responsibilities.

    ``capability_chain`` contains stable capability IDs only.  Their concrete
    public entrypoints remain owned by ``operation-capabilities.yaml`` and are
    resolved at invocation time; this registry never repeats a module path.
    """

    route_id: str
    token_pattern: str
    token_template: str
    parameter_names: tuple
    resume_source: bool
    action_disposition: Optional[str]
    internal_dispatch: bool
    runner_route: str
    capability_chain: tuple
    capability_resolution: str
    producer_owner: str
    consumer_owner: str
    next_edge: str
    recommendation: str
    recommendation_renderer: str = "template"


_ID = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_ID_LIST = r"[A-Za-z0-9][A-Za-z0-9._-]*(?:,[A-Za-z0-9][A-Za-z0-9._-]*)*"


def _route(route_id, pattern, template, parameters, *, resume_source,
           disposition, runner_route, capabilities=(), recommendation,
           recommendation_renderer="template", capability_resolution=None,
           producer_owner=None, internal_dispatch=False):
    if not isinstance(internal_dispatch, bool):
        raise ValueError("Task Runtime internal_dispatch must be boolean")
    if internal_dispatch:
        if disposition is not None:
            raise ValueError(
                "internal Task Runtime dispatch must not predeclare an "
                "outward disposition")
    elif disposition not in DISPOSITIONS:
        raise ValueError(
            "outward Task Runtime route disposition must be one of %s" %
            ", ".join(sorted(DISPOSITIONS)))
    if capability_resolution is None:
        capability_resolution = "registry-chain" if capabilities else "none"
    if producer_owner is None:
        producer_owner = (
            "Tools/execution/task_runtime/queue_runtime/resume.py"
            if resume_source else
            "Tools/execution/task_runtime/task_runtime_runner.py")
    return ActionRoute(
        route_id=route_id,
        token_pattern=pattern,
        token_template=template,
        parameter_names=tuple(parameters),
        resume_source=resume_source,
        action_disposition=disposition,
        internal_dispatch=internal_dispatch,
        runner_route=runner_route,
        capability_chain=tuple(capabilities),
        capability_resolution=capability_resolution,
        producer_owner=producer_owner,
        consumer_owner=(
            "Tools/execution/task_runtime/task_runtime_runner.py"),
        next_edge="authoritative-runtime-reread",
        recommendation=recommendation,
        recommendation_renderer=recommendation_renderer,
    )


# This is a routing registry, not a second lifecycle policy.  The resume
# selector still decides *which* route applies from canonical state; these rows
# own only the stable token grammar and the already-existing producer/consumer
# chain that can act on the selected route.
ACTION_ROUTES = (
    _route(
        "reconcile-interrupted-write", r"reconcile-interrupted-write",
        "reconcile-interrupted-write", (), resume_source=True,
        disposition="repair", runner_route="repair", recommendation=(
            "verify that no writer process remains, reconcile Queue/Progress/"
            "deltas, and remove only a proven-stale lock; do not initialize "
            "or overwrite the runtime")),
    _route(
        "repair-runtime", r"repair-runtime", "repair-runtime", (),
        resume_source=True, disposition="repair", runner_route="repair",
        recommendation=(
            "repair and reconcile the existing runtime before continuing; "
            "do not initialize or overwrite it")),
    _route(
        "archive-terminal-runtime", r"archive-terminal-runtime",
        "archive-terminal-runtime", (), resume_source=True,
        disposition="terminal", runner_route="terminal", recommendation=(
            "the existing task is terminal; preserve any unfinished batch or "
            "control records as incomplete history, then explicitly archive "
            "or roll over the runtime")),
    _route(
        "resume-paused-task", r"resume-paused-task", "resume-paused-task",
        (), resume_source=True, disposition="await-user",
        runner_route="task-transition",
        capabilities=("task-state-transition-v1",), recommendation=(
            "resume the paused task from its checkpoint, then derive the next "
            "action again; do not initialize a new task")),
    _route(
        "resolve-blocked-task", r"resolve-blocked-task",
        "resolve-blocked-task", (), resume_source=True,
        disposition="await-user", runner_route="task-transition",
        capabilities=("task-state-transition-v1",), recommendation=(
            "resolve the blocked task state from its checkpoint, then derive "
            "the next action again; do not initialize a new task")),
    _route(
        "reconcile-control-input", r"reconcile-control-input",
        "reconcile-control-input", (), resume_source=True,
        disposition="await-agent", runner_route="external-reparse",
        recommendation=(
            "reconcile the pending Guidance or Amendment through its owned "
            "writer, then derive the next action again")),
    _route(
        "repair-delta-settlement",
        rf"repair-delta-settlement:(?P<batch_id>{_ID})",
        "repair-delta-settlement:{batch_id}", ("batch_id",),
        resume_source=True, disposition="repair", runner_route="repair",
        recommendation=(
            "repair routed-gap settlement in the managed Delta for batch "
            "{batch_id} before batch review or merge-ready admission")),
    _route(
        "run-standards-revalidation",
        rf"run-standards-revalidation:(?P<batch_id>{_ID})",
        "run-standards-revalidation:{batch_id}", ("batch_id",),
        resume_source=True, disposition="await-agent",
        runner_route="standards-revalidation",
        capabilities=("required-queue-gate-v1",
                      "ordinary-queue-transition-v1",
                      "task-runtime-runner-v1"), recommendation=(
            "run the current boundary gates for batch {batch_id}, aggregate "
            "them with check_queue.py --require-revalidation, then consume "
            "that receipt before merge/apply/close")),
    _route(
        "run-terminal-audit", r"run-terminal-audit", "run-terminal-audit",
        (), resume_source=True, disposition="await-agent",
        runner_route="terminal-audit",
        capabilities=(
            "required-queue-gate-v1",
            "corpus-plan-structure-gate-v1",
            "terminal-proof-producer-v1",
            "terminal-proof-gate-v1",
            "task-state-transition-v1",
        ), recommendation=(
            "supply the bounded Terminal Audit input; the Runner will produce "
            "fresh Queue and Corpus evidence, assemble and verify Terminal "
            "Proof, then consume its Gate receipt through the task writer")),
    _route(
        "apply-delta", rf"apply-delta:(?P<batch_id>{_ID})",
        "apply-delta:{batch_id}", ("batch_id",), resume_source=True,
        disposition="invoke", runner_route="apply-delta",
        capabilities=("coverage-delta-application-v1",), recommendation=(
            "apply the admitted Delta for batch {batch_id} before any later "
            "Queue transition")),
    _route(
        "admit-delta", rf"admit-delta:(?P<batch_id>{_ID})",
        "admit-delta:{batch_id}", ("batch_id",), resume_source=True,
        disposition=None, internal_dispatch=True,
        runner_route="open-batch-audit",
        recommendation=(
            "admit the current candidate Delta for batch {batch_id} before "
            "starting new work")),
    _route(
        "resume-in-flight-batches",
        rf"resume-in-flight-batches:(?P<batch_ids>{_ID_LIST})",
        "resume-in-flight-batches:{batch_ids}", ("batch_ids",),
        resume_source=True, disposition=None, internal_dispatch=True,
        runner_route="open-batch-audit", recommendation=(
            "resume the existing task and reconcile in-flight batch(es) "
            "{batch_ids} before starting new work")),
    _route(
        "run-batch-close-gate-request",
        rf"run-batch-close-gate:(?P<batch_id>{_ID})",
        "run-batch-close-gate:{batch_id}", ("batch_id",),
        resume_source=True, disposition="await-agent",
        runner_route="batch-close-request",
        capabilities=("batch-close-producer-v1",), recommendation=(
            "run check_batch_close.py for applied batch {batch_id} before any "
            "Queue close, control input, another batch, or terminal archival")),
    _route(
        "close-applied-batch",
        (rf"close-applied-batch:(?P<batch_id>{_ID}):"
         rf"(?P<queue_consistency_receipt>{_ID}):"
         rf"(?P<close_gate_receipt>{_ID}):"
         rf"(?P<delta_apply_receipt>{_ID})"),
        ("close-applied-batch:{batch_id}:{queue_consistency_receipt}:"
         "{close_gate_receipt}:{delta_apply_receipt}"),
        ("batch_id", "queue_consistency_receipt", "close_gate_receipt",
         "delta_apply_receipt"), resume_source=True, disposition="invoke",
        runner_route="close-applied-batch",
        capabilities=("ordinary-queue-transition-v1",), recommendation=(
            "close applied batch {batch_id} with the recovered current "
            "bundle; run: {command}"),
        recommendation_renderer="batch-close-command"),
    _route(
        "complete-maintenance-task",
        rf"complete-maintenance-task:(?P<receipt_id>{_ID})",
        "complete-maintenance-task:{receipt_id}", ("receipt_id",),
        resume_source=True, disposition="invoke",
        runner_route="complete-maintenance-task",
        capabilities=("task-state-transition-v1",), recommendation=(
            "consume current maintenance completion gate {receipt_id} with "
            "update_task.py; do not regenerate state or Terminal Proof")),
    _route(
        "run-maintenance-completion-gate",
        r"run-maintenance-completion-gate",
        "run-maintenance-completion-gate", (), resume_source=True,
        disposition="await-agent", runner_route="maintenance-completion-gate",
        capabilities=("maintenance-evidence-producer-v1",
                      "required-queue-gate-v1"), recommendation=(
            "record current maintenance budget, Ledger, and watermark "
            "evidence, then run its completion Gate with update_task.py")),
    _route(
        "enter-completion-candidate", r"enter-completion-candidate",
        "enter-completion-candidate", (), resume_source=True,
        disposition="invoke", runner_route="enter-completion-candidate",
        capabilities=("task-runtime-runner-v1", "required-queue-gate-v1",
                      "task-state-transition-v1"), recommendation=(
            "enter completion-candidate with a current require-complete "
            "receipt, then run the build Terminal Audit")),
    _route(
        "activate-ready-batch",
        rf"activate-ready-batch:(?P<batch_ids>{_ID_LIST})",
        "activate-ready-batch:{batch_ids}", ("batch_ids",),
        resume_source=True, disposition="invoke",
        runner_route="activate-ready-batch",
        capabilities=("task-runtime-runner-v1", "required-queue-gate-v1",
                      "ordinary-queue-transition-v1"), recommendation=(
            "resume the existing task with ready batch(es) {batch_ids}; do "
            "not initialize a new task")),
    _route(
        "materialize-required-queue", r"materialize-required-queue",
        "materialize-required-queue", (), resume_source=True,
        disposition="invoke", runner_route="materialize-required-queue",
        capabilities=("required-queue-materialization-v1",), recommendation=(
            "resume the existing task by materializing its Required Queue; "
            "do not initialize a second task over it")),
    _route(
        "resolve-holds-dependencies", r"resolve-holds-dependencies",
        "resolve-holds-dependencies", (), resume_source=True,
        disposition="await-agent", runner_route="external-reparse",
        recommendation=(
            "resume or resolve the existing task's recorded holds or "
            "dependencies; do not initialize a new task")),

    # Await tokens emitted after the resume route has entered one bounded
    # phase.  They share this registry so the Runner has no private await map.
    _route(
        "ack-activation-phase", r"ack-activation-phase",
        "ack-activation-phase", (), resume_source=False,
        disposition="await-agent", runner_route="activation-ack",
        capabilities=("card-context-delivery-v1",), recommendation=""),
    _route(
        "record-substantive-review", r"record-substantive-review",
        "record-substantive-review", (), resume_source=False,
        disposition="await-agent", runner_route="audit-producer",
        capability_resolution="upstream-action",
        producer_owner=(
            "Tools/execution/audit/audit_execution_runtime.py"),
        recommendation=""),
    _route(
        "record-rendering-verification", r"record-rendering-verification",
        "record-rendering-verification", (), resume_source=False,
        disposition="await-agent", runner_route="audit-producer",
        capability_resolution="upstream-action",
        producer_owner=(
            "Tools/execution/audit/audit_execution_runtime.py"),
        recommendation=""),
    _route(
        "record-batch-page-review", r"record-batch-page-review",
        "record-batch-page-review", (), resume_source=False,
        disposition="await-agent", runner_route="audit-producer",
        capability_resolution="upstream-action",
        producer_owner=(
            "Tools/execution/audit/audit_execution_runtime.py"),
        recommendation=""),
    _route(
        "record-profile-batch-judgment", r"record-profile-batch-judgment",
        "record-profile-batch-judgment", (), resume_source=False,
        disposition="await-agent", runner_route="audit-producer",
        capability_resolution="upstream-action",
        producer_owner=(
            "Tools/execution/audit/audit_execution_runtime.py"),
        recommendation=""),
    _route(
        "publish-candidate-delta", r"publish-candidate-delta",
        "publish-candidate-delta", (), resume_source=False,
        disposition="await-agent", runner_route="candidate-delta",
        capabilities=("candidate-delta-publication-v1",), recommendation=""),
    _route(
        "record-batch-review", r"record-batch-review",
        "record-batch-review", (), resume_source=False,
        disposition="await-agent", runner_route="batch-review",
        capabilities=("batch-review-producer-v1",), recommendation=""),
    _route(
        "run-batch-close-gate-input", r"run-batch-close-gate",
        "run-batch-close-gate", (), resume_source=False,
        disposition="await-agent", runner_route="batch-close",
        capabilities=("batch-close-producer-v1",), recommendation=""),
    _route(
        "correct-audit-target", r"correct-audit-target",
        "correct-audit-target", (), resume_source=False,
        disposition="await-agent", runner_route="external-reparse",
        producer_owner=(
            "Tools/execution/audit/audit_execution_runtime.py"),
        recommendation=""),
    _route(
        "resolve-substantive-review-escalation",
        r"resolve-substantive-review-escalation",
        "resolve-substantive-review-escalation", (), resume_source=False,
        disposition="await-user", runner_route="external-reparse",
        producer_owner=(
            "Tools/execution/audit/audit_execution_runtime.py"),
        recommendation=""),
    _route(
        "consume-standards-revalidation", r"consume-standards-revalidation",
        "consume-standards-revalidation", (), resume_source=False,
        disposition="invoke", runner_route="consume-standards-revalidation",
        capabilities=("ordinary-queue-transition-v1",), recommendation=""),
    _route(
        "activate-revalidated-batch", r"activate-revalidated-batch",
        "activate-revalidated-batch", (), resume_source=False,
        disposition="invoke", runner_route="activate-revalidated-batch",
        capabilities=("task-runtime-runner-v1", "required-queue-gate-v1",
                      "ordinary-queue-transition-v1"), recommendation=""),
    _route(
        "transition-batch-merge-ready", r"transition-batch-merge-ready",
        "transition-batch-merge-ready", (), resume_source=False,
        disposition="invoke", runner_route="transition-batch-merge-ready",
        capabilities=("ordinary-queue-transition-v1",),
        recommendation=""),
)


def action_route(route_id):
    """Return one route by stable ID, refusing duplicate ownership."""
    matches = [route for route in ACTION_ROUTES if route.route_id == route_id]
    if len(matches) != 1:
        raise ValueError(
            "Task Runtime action route %s has %d owners" %
            (route_id, len(matches)))
    return matches[0]


def action_route_for_token(token, *, resume_source=None):
    """Resolve one token through the unique registered grammar."""
    require_trimmed_string(token, "Task Runtime action token")
    candidates = ACTION_ROUTES
    if resume_source is not None:
        candidates = tuple(
            route for route in candidates
            if route.resume_source is resume_source)
    matches = []
    for route in candidates:
        matched = re.fullmatch(route.token_pattern, token)
        if matched is not None:
            matches.append((route, matched.groupdict()))
    if len(matches) != 1:
        raise ValueError(
            "Task Runtime action token %s has %d registered routes" %
            (token, len(matches)))
    return matches[0]


def resume_action_token(route_id, **parameters):
    """Format one resume token from its route instead of open-coded text."""
    route = action_route(route_id)
    if not route.resume_source:
        raise ValueError("Task Runtime action route is not a resume source")
    missing = sorted(set(route.parameter_names) - set(parameters))
    extra = sorted(set(parameters) - set(route.parameter_names))
    if missing or extra:
        raise ValueError(
            "Task Runtime resume token parameters do not match %s" % route_id)
    token = route.token_template.format(**parameters)
    resolved, parsed = action_route_for_token(token, resume_source=True)
    if resolved.route_id != route_id or parsed != {
            key: str(value) for key, value in parameters.items()}:
        raise ValueError(
            "Task Runtime resume token does not round-trip through its route")
    return token


def resume_recommendation(token, **renderer_values):
    """Render the human projection of one already-selected resume token."""
    route, parameters = action_route_for_token(token, resume_source=True)
    values = dict(parameters)
    values.update(renderer_values)
    try:
        return route.recommendation.format(**values)
    except KeyError as exc:
        raise ValueError(
            "Task Runtime recommendation %s misses renderer value %s" %
            (route.route_id, exc.args[0])) from exc


def _closed_fields(record, fields, label):
    if not isinstance(record, dict):
        raise ValueError("%s must be a mapping" % label)
    missing = sorted(fields - set(record))
    extra = sorted(set(record) - fields)
    if missing or extra:
        details = []
        if missing:
            details.append("missing %s" % ", ".join(missing))
        if extra:
            details.append("unsupported %s" % ", ".join(extra))
        raise ValueError("%s fields are not closed (%s)" %
                         (label, "; ".join(details)))


def _json_value(value, label):
    """Reject values without one portable canonical-JSON representation."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("%s must not contain a non-finite number" % label)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json_value(item, "%s[%d]" % (label, index))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            require_trimmed_string(key, "%s key" % label)
            _json_value(item, "%s.%s" % (label, key))
        return
    raise ValueError(
        "%s must contain only canonical JSON values" % label)


def _mapping(value, label, *, nonempty=False):
    if not isinstance(value, dict):
        raise ValueError("%s must be a mapping" % label)
    if nonempty and not value:
        raise ValueError("%s must be a non-empty mapping" % label)
    _json_value(value, label)
    return value


def _optional_trimmed_string(value, label):
    if value is None:
        return None
    return require_trimmed_string(value, label)


def _validate_machine_fields(record):
    _closed_fields(record, MACHINE_FIELDS, "Task Runtime action payload")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Task Runtime action schema_version must be 1")

    disposition = record.get("disposition")
    if disposition not in DISPOSITIONS:
        raise ValueError(
            "Task Runtime action disposition must be one of %s" %
            ", ".join(sorted(DISPOSITIONS)))
    require_trimmed_string(record.get("token"),
                           "Task Runtime action token")
    _mapping(record.get("target"), "Task Runtime action target")
    _mapping(record.get("binding"), "Task Runtime action binding")

    reason_code = require_trimmed_string(
        record.get("reason_code"), "Task Runtime action reason_code")
    if REASON_CODE_RE.fullmatch(reason_code) is None:
        raise ValueError(
            "Task Runtime action reason_code must be a lowercase "
            "hyphenated stable code")

    capability_id = _optional_trimmed_string(
        record.get("capability_id"), "Task Runtime action capability_id")
    tool = _optional_trimmed_string(
        record.get("tool"), "Task Runtime action tool")
    arguments = record.get("arguments")
    required_input = record.get("required_input")

    if disposition == "invoke":
        if capability_id is None or tool is None:
            raise ValueError(
                "invoke action requires capability_id and tool")
        _mapping(arguments, "Task Runtime action arguments")
        if required_input is not None:
            raise ValueError("invoke action required_input must be null")
        return

    if capability_id is not None or tool is not None:
        raise ValueError(
            "%s action capability_id and tool must be null" % disposition)
    if arguments != {}:
        raise ValueError("%s action arguments must be an empty mapping" %
                         disposition)

    if disposition in AWAIT_DISPOSITIONS:
        _mapping(required_input, "Task Runtime action required_input",
                 nonempty=True)
    elif required_input is not None:
        raise ValueError("%s action required_input must be null" % disposition)


def canonical_action_id(record):
    """Return the content identity of all machine fields except action_id.

    ``record`` may already contain ``action_id``; that field is deliberately
    ignored so callers can recompute and compare the identity without creating
    a self-referential hash.
    """
    if not isinstance(record, dict):
        raise ValueError("Task Runtime action must be a mapping")
    payload = {key: value for key, value in record.items()
               if key != "action_id"}
    _validate_machine_fields(payload)
    digest = hashlib.sha256(kblib.canonical_json_bytes(payload)).hexdigest()
    return "action-%s" % digest


def validate_action(record):
    """Validate one closed next-action record and return it unchanged."""
    _closed_fields(record, ACTION_FIELDS, "Task Runtime action")
    action_id = record.get("action_id")
    if (not isinstance(action_id, str) or
            ACTION_ID_RE.fullmatch(action_id) is None):
        raise ValueError(
            "Task Runtime action action_id must be action-<64 lowercase hex>")
    expected = canonical_action_id(record)
    if action_id != expected:
        raise ValueError(
            "Task Runtime action action_id does not bind its machine fields")
    return record


def build_action(**fields):
    """Build and validate one action, deriving rather than choosing its ID."""
    record = dict(fields)
    supplied = record.pop("action_id", None)
    supplied_present = "action_id" in fields
    action_id = canonical_action_id(record)
    if supplied_present and supplied != action_id:
        raise ValueError(
            "supplied Task Runtime action_id does not bind its machine fields")
    record["action_id"] = action_id
    validate_action(record)
    return record


__all__ = [
    'AWAIT_DISPOSITIONS',
    'SCHEMA_VERSION',
    'action_route',
    'action_route_for_token',
    'build_action',
    'resume_action_token',
    'resume_recommendation',
]
