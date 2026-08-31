"""Internal semantic owner for the initial Task Plan transaction.

The public operation is ``init_state --plan``.  This module owns the one
machine interpretation of that confirmed plan: its closed shape, the Task
Contract and planning-only Coverage after-image, the empty Queue before its
independent materialization, and the immutable transaction Receipt that binds
those bytes.  It deliberately has no CLI or MCP entry point.

The before boundary is absence of the task-state namespace plus the current
adopted Standards/Profile lineage.  A Task Plan therefore never copies three
state-file hashes from a skeleton that should not have existed in the first
place.  ``init_state`` owns staging, no-replace publication and the writer
lock; it delegates every planning decision and validation here.
"""

import copy
import os

import Tools.execution.context_delivery.card_contract as card_contract
import Tools.execution.context_delivery.read_set_contract as read_set_contract
import Tools.execution.planning.compile_queue as compile_queue
import Tools.execution.planning.coverage_contract as coverage_contract
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.amendment_policy as amendment_policy
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.standards.adoption_lineage_contract as adoption_lineage_contract
import Tools.platform.common.kblib as kblib
import Tools.platform.distribution.stamp_cards as stamp_cards
from Tools.execution.evidence import receipt_type_contract


TOOL = "apply_task_plan"
TOOL_VERSION = "2.0.0"
CHECK = "task_plan"
RECEIPT_TYPE_ID = "task-plan-publication-receipt-v1"


def current_receipt_errors(record, *, root=None):
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=CHECK)
PLAN_PREFIX = runtime_paths.TASK_PLAN_DELTA_ROOT
RECEIPT_PATH = runtime_paths.TASK_PLAN_RECEIPT_PATH
SENTINEL = "TODO(plan)"

PLAN_FIELDS = {
    "schema_version", "plan_id", "task_id", "approval_reference",
    "contract_after", "planned_work",
}
PLANNED_WORK_FIELDS = {"pages", "batch_specs"}
CONTRACT_FIELDS = set(queue_runtime.CONTRACT_FIELDS)


class Refusal(Exception):
    """The confirmed plan cannot become the initial task runtime."""


def _closed(mapping, allowed, label, optional=frozenset()):
    if not isinstance(mapping, dict):
        raise Refusal("%s must be a mapping" % label)
    unknown = sorted(set(mapping) - set(allowed))
    missing = sorted(set(allowed) - set(optional) - set(mapping))
    if unknown:
        raise Refusal("%s has unsupported field(s): %s" %
                      (label, ", ".join(unknown)))
    if missing:
        raise Refusal("%s is missing field(s): %s" %
                      (label, ", ".join(missing)))


def _load_plan(root, relative):
    path = kblib.managed_repository_path(
        root, relative, PLAN_PREFIX, suffixes=(".yaml",), must_exist=True)
    raw = kblib.read_bytes(path)
    try:
        plan = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise Refusal("task plan is not UTF-8: %s" % exc) from exc
    except kblib.YamlSubsetError as exc:
        raise Refusal(
            "task plan is not the restricted YAML subset: %s" % exc) from exc
    if not isinstance(plan, dict):
        raise Refusal("task plan top level must be a mapping")
    return path, raw, plan


def _validate_plan_shape(plan):
    if SENTINEL in kblib.canonical_yaml(plan):
        raise Refusal(
            "task plan still carries the template's %s sentinel; every one "
            "of them is a confirmed answer this transaction will not invent"
            % SENTINEL)
    _closed(plan, PLAN_FIELDS, "task plan")
    if plan["schema_version"] != 4:
        raise Refusal("task plan schema_version must be 4")
    for field in ("plan_id", "task_id", "approval_reference"):
        value = plan[field]
        if not isinstance(value, str) or not value.strip():
            raise Refusal("task plan %s must be a nonempty string" % field)

    contract = plan["contract_after"]
    _closed(contract, CONTRACT_FIELDS, "task plan contract_after")
    if contract.get("completion_semantics") not in \
            runtime_state_contract.COMPLETION_SEMANTICS:
        raise Refusal(
            "task plan contract_after.completion_semantics must be build or "
            "maintenance")
    if not isinstance(contract.get("objective"), str) or not \
            contract["objective"].strip():
        raise Refusal(
            "task plan contract_after.objective must be a nonempty string")
    exclusions = contract.get("exclusions")
    if (not isinstance(exclusions, list) or
            not all(isinstance(value, str) and value.strip()
                    for value in exclusions) or
            len(exclusions) != len(set(exclusions))):
        raise Refusal(
            "task plan contract_after.exclusions must be an explicit unique "
            "string list")
    cap = contract.get("concurrency_cap")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise Refusal(
            "task plan contract_after.concurrency_cap must be a positive "
            "integer")
    for field in ("contract_version", "scope_version", "upstream_revision_id",
                  "selected_profile_manifest", "completion_gate"):
        value = contract.get(field)
        if not isinstance(value, str) or not value.strip():
            raise Refusal(
                "task plan contract_after.%s must be a nonempty string" %
                field)
    authority = contract.get("amendment_authority")
    if authority is not None:
        authority_errors = amendment_policy.amendment_authority_errors(
            authority, "task plan contract_after.amendment_authority")
        if authority_errors:
            raise Refusal(
                "task plan amendment authority is not the K13/02 shape:\n  %s"
                % "\n  ".join(authority_errors[:8]))

    planned = plan["planned_work"]
    _closed(planned, PLANNED_WORK_FIELDS, "task plan planned_work")
    for field in sorted(PLANNED_WORK_FIELDS):
        if not isinstance(planned[field], list):
            raise Refusal(
                "task plan planned_work.%s must be a list" % field)
    if not planned["pages"]:
        raise Refusal(
            "task plan planned_work.pages is empty; initial planning must "
            "declare at least one Required work object")
    for index, page in enumerate(planned["pages"]):
        label = "task plan planned_work.pages[%d]" % index
        if not isinstance(page, dict):
            raise Refusal("%s must be a mapping" % label)
        shape_errors = coverage_contract.page_shape_errors(page, label)
        if shape_errors:
            raise Refusal("\n  ".join(shape_errors))
        if not coverage_contract.is_planning_page(page):
            raise Refusal(
                "%s claims current page state; initial Task Plan rows may "
                "declare only scope and Queue assignment" % label)


def _resolve_concurrency_cap_overrides(overrides, explicit):
    try:
        overrides = dict(overrides)
    except (TypeError, ValueError) as exc:
        raise Refusal(
            "authorized Profile evaluation has malformed execution-default "
            "overrides: %s" % exc) from exc
    raw = overrides.get("concurrency_cap")
    manifest_value = None
    if raw is not None:
        if not isinstance(raw, str) or not raw.isdigit() or int(raw) < 1:
            raise Refusal(
                "selected Profile declares malformed concurrency_cap=%r" % raw)
        manifest_value = int(raw)
    if manifest_value is not None and explicit != manifest_value:
        raise Refusal(
            "Task Plan concurrency_cap %d contradicts the selected Profile's "
            "registered concurrency_cap %d" % (explicit, manifest_value))
    return explicit, ("task-plan+profile-manifest" if manifest_value is not None
                      else "task-plan")


def _profile_configuration(root, manifest_relative, explicit_cap):
    view, errors = queue_runtime.profile_load_authorized_view(
        root, manifest_relative)
    if errors:
        raise Refusal("selected Profile failed profile-load: %s" %
                      "; ".join(errors))
    evaluation = view.get("_evaluation") if isinstance(view, dict) else None
    if evaluation is None:
        raise Refusal(
            "authorized Profile view has no snapshot-bound evaluation")
    cap, source = _resolve_concurrency_cap_overrides(
        evaluation.execution_default_overrides, explicit_cap)
    return view, queue_runtime.public_profile_load_evidence(view), cap, source


def _strings(values):
    return {value for value in (values or [])
            if isinstance(value, str) and value}


def _derive_load_sets(root, contract):
    """Resolve the confirmed route selection through canonical registries."""
    try:
        card_map, read_map = stamp_cards.discover_cards(root)
    except (card_contract.CardContractError,
            read_set_contract.ReadSetContractError) as exc:
        raise Refusal(
            "the Card/Read Set registry is not sound: %s" %
            exc) from exc
    routes = sorted(_strings(contract.get("selected_route_ids")) | {"R01"})
    contract["selected_route_ids"] = routes
    unknown = [route for route in routes if route not in read_map]
    if unknown:
        raise Refusal("selected_route_ids names unregistered route(s): %s" %
                      ", ".join(unknown))

    cards = _strings(contract.get("selected_card_paths"))
    registered_cards = {entry["path"] for entry in card_map.values()}
    selected_cards = {card_map[route]["path"] for route in routes}
    foreign = sorted(card for card in cards
                     if card in registered_cards and card not in selected_cards)
    if foreign:
        raise Refusal(
            "selected_card_paths declares %s, whose route is not in "
            "selected_route_ids" % ", ".join(foreign))

    seeds = _strings(contract.get("selected_read_sets")) | {
        read_map[route]["path"] for route in routes}
    read_sets, modules, invalid, closure_errors = \
        queue_runtime.read_set_load_closure(
            root, seeds, contract.get("selected_profile_manifest"),
            contract.get("selected_profile_route_ids"))
    if closure_errors or invalid:
        raise Refusal(
            "the selected routes' Read Set closure does not resolve:\n  %s" %
            "\n  ".join(closure_errors or sorted(invalid)))
    contract["selected_card_paths"] = sorted(cards | selected_cards)
    contract["selected_read_sets"] = sorted(read_sets)
    contract["loaded_module_paths"] = sorted(
        _strings(contract.get("loaded_module_paths")) | modules)
    return {
        "routes": len(routes),
        "read_sets": len(contract["selected_read_sets"]),
        "modules": len(contract["loaded_module_paths"]),
    }


def _empty_queue(plan):
    contract = plan["contract_after"]
    return {
        "schema_version": 2,
        "task_id": plan["task_id"],
        "scope_version": contract["scope_version"],
        "queue_revision": 1,
        "state_revision": 0,
        "upstream_revision_id": contract["upstream_revision_id"],
        "selected_profile_manifest": contract["selected_profile_manifest"],
        "required_queue": [],
    }


def _coverage(plan, timestamp):
    contract = plan["contract_after"]
    return {
        "schema_version": 2,
        "task_id": plan["task_id"],
        "updated_at": timestamp,
        "scope_version": contract["scope_version"],
        "upstream_revision_id": contract["upstream_revision_id"],
        "selected_profile_manifest": contract["selected_profile_manifest"],
        "batch_specs": copy.deepcopy(plan["planned_work"]["batch_specs"]),
        "maintenance_candidates": [],
        "pages": copy.deepcopy(plan["planned_work"]["pages"]),
        "open_gaps": [],
    }


def _progress(plan, contract, queue_text, receipt_id):
    completion = contract["completion_semantics"]
    return {
        "schema_version": 2,
        "task_id": plan["task_id"],
        "task_state": "planned",
        "task_transition_receipts": [],
        "required_queue_path": runtime_paths.QUEUE_PATH,
        "queue_revision": 1,
        "queue_state_revision": 0,
        "required_queue_sha256": kblib.sha256_bytes(queue_text),
        "initial_task_plan_receipt": receipt_id,
        "initial_queue_receipt": None,
        "contract": copy.deepcopy(contract),
        "checkpoint": {
            "recorded_at": None,
            "summary": None,
            "task_state": "planned",
            "task_transition_receipt": None,
            "coverage_sha256": None,
            "required_queue_sha256": None,
            "queue_revision": 1,
            "queue_state_revision": 0,
        },
        "terminal_audit": {
            "state": "not-started" if completion == "build"
                     else "not-applicable",
            "terminal_proof_path": None,
            "terminal_proof_sha256": None,
            "terminal_proof_receipt": None,
            "queue_check_receipt": None,
        },
        "maintenance_completion": {
            "state": "pending" if completion == "maintenance"
                     else "not-applicable",
            "completion_gate_receipt": None,
            "budget_manifest_receipt": None,
            "ledger_advance_receipt": None,
            "watermark_advance_receipt": None,
        },
        "amendments": [],
        "standards_adoptions": [],
        "guidance_queue": [],
    }


def _receipt(plan, plan_relative, plan_sha, profile_evidence):
    contract = plan["contract_after"]
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, plan["plan_id"], "pass",
        "published the confirmed Task Contract and %d planning-only Coverage "
        "record(s); Queue materialization remains owned by compile_queue" %
        len(plan["planned_work"]["pages"]), 1,
        receipt_type_id=RECEIPT_TYPE_ID,
        identity={
            "task_id": plan["task_id"],
            "upstream_revision_id": contract["upstream_revision_id"],
            "selected_profile_manifest":
                contract["selected_profile_manifest"],
        })
    receipt.update({
        "transaction_phase": "commit",
        "plan_id": plan["plan_id"],
        "plan_path": plan_relative,
        "plan_sha256": plan_sha,
        "approval_reference": plan["approval_reference"],
        "planning_record_count": len(plan["planned_work"]["pages"]),
        "batch_spec_count": len(plan["planned_work"]["batch_specs"]),
    })
    for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS:
        receipt[field] = profile_evidence.get(field)
    return receipt


def _task_state_exists(root):
    return os.path.lexists(os.path.join(root, runtime_paths.STATE_ROOT))


def prepare(root, plan_relative):
    """Build and validate the complete blank-to-planned transaction."""
    root = os.path.realpath(os.path.abspath(root))
    if _task_state_exists(root):
        raise Refusal(
            "%s already exists; initial planning is no-replace and a later "
            "change is a replan, Amendment, or successor task" %
            runtime_paths.STATE_ROOT)
    plan_path, plan_raw, plan = _load_plan(root, plan_relative)
    _validate_plan_shape(plan)
    contract = copy.deepcopy(plan["contract_after"])

    active_view, active_errors = queue_runtime.active_standards_authorized_view(
        root, contract["upstream_revision_id"],
        contract["selected_profile_manifest"])
    if active_errors:
        raise Refusal("; ".join(active_errors))
    profile_view, profile_evidence, cap, cap_source = _profile_configuration(
        root, contract["selected_profile_manifest"],
        contract["concurrency_cap"])
    contract["concurrency_cap"] = cap
    lineage_errors = adoption_lineage_contract.current_lineage_errors(
        active_view, profile_evidence=profile_evidence, root=root)
    if lineage_errors:
        raise Refusal("; ".join(lineage_errors))
    derived = _derive_load_sets(root, contract)

    plan_relative = os.path.relpath(plan_path, root).replace(os.sep, "/")
    plan_sha = kblib.sha256_bytes(plan_raw)
    receipt = _receipt(plan, plan_relative, plan_sha, profile_evidence)
    queue = _empty_queue(plan)
    queue_text = kblib.canonical_yaml(queue)
    coverage = _coverage(plan, receipt["checked_at"])
    progress = _progress(plan, contract, queue_text, receipt["receipt_id"])

    try:
        compiled_queue, _changed = compile_queue.compile_document(
            copy.deepcopy(queue), coverage)
    except (TypeError, ValueError) as exc:
        raise Refusal(
            "the Queue compiler rejects this Task Plan: %s" % exc) from exc

    texts = {
        "coverage": kblib.canonical_yaml(coverage),
        "queue": queue_text,
        "progress": kblib.canonical_yaml(progress),
    }
    shas = {name: kblib.sha256_bytes(text.encode("utf-8"))
            for name, text in texts.items()}
    receipt.update({
        "after_coverage_sha256": shas["coverage"],
        "after_required_queue_sha256": shas["queue"],
        "after_progress_sha256": shas["progress"],
        "contract_sha256": queue_runtime.contract_sha256(progress),
        "contract_version": contract["contract_version"],
        "contract_scope_version": contract["scope_version"],
        "active_standards_sha256": active_view["active_standards_sha256"],
    })
    validation = runtime_validation.validate_runtime(
        root,
        state_overrides={
            runtime_paths.COVERAGE_PATH: (texts["coverage"], coverage),
            runtime_paths.QUEUE_PATH: (texts["queue"], queue),
            runtime_paths.PROGRESS_PATH: (texts["progress"], progress),
        },
        extra_receipts=[receipt],
        allow_unmaterialized_queue=True,
        authorized_profile_view=profile_view,
        authorized_active_standards_view=active_view,
    )
    if validation["errors"]:
        raise Refusal(
            "the Task Plan after-image does not validate:\n  %s" %
            "\n  ".join(validation["errors"][:12]))
    authority = queue_runtime.runtime_authority_context(validation)
    return {
        "root": root,
        "plan": plan,
        "plan_path": plan_relative,
        "plan_sha": plan_sha,
        "documents": {
            os.path.basename(runtime_paths.COVERAGE_PATH): texts["coverage"],
            os.path.basename(runtime_paths.QUEUE_PATH): texts["queue"],
            os.path.basename(runtime_paths.PROGRESS_PATH): texts["progress"],
        },
        "state_documents": {
            "coverage": coverage, "queue": queue, "progress": progress,
        },
        "state_sha": shas,
        "receipt": receipt,
        "receipt_bytes": kblib.canonical_json_bytes(receipt) + b"\n",
        "compiled_queue": compiled_queue,
        "derived": derived,
        "concurrency_cap_source": cap_source,
        "authority": authority,
    }


def require_current(prepared, phase):
    """Re-prove the exact plan and adopted authority before publication."""
    root = prepared["root"]
    if _task_state_exists(root):
        raise Refusal(
            "%s task state appeared during %s" %
            (runtime_paths.RUNTIME_ROOT, phase))
    plan_path = kblib.managed_repository_path(
        root, prepared["plan_path"], PLAN_PREFIX,
        suffixes=(".yaml",), must_exist=True)
    if kblib.sha256_bytes(kblib.read_bytes(plan_path)) != prepared["plan_sha"]:
        raise Refusal("confirmed Task Plan changed during %s" % phase)
    queue_runtime.require_runtime_authority_current(
        root, prepared["authority"],
        "initial Task Plan authority changed during %s" % phase)
    active_view = prepared["authority"]["active_standards_view"]
    profile_view = prepared["authority"]["profile_view"]
    lineage_errors = adoption_lineage_contract.current_lineage_errors(
        active_view,
        profile_evidence=queue_runtime.public_profile_load_evidence(
            profile_view),
        root=root,
    )
    if lineage_errors:
        raise Refusal(
            "adoption lineage changed during %s: %s" %
            (phase, "; ".join(lineage_errors)))


def validate_published(prepared):
    """Validate the public state and its exact persisted planning Receipt."""
    receipt_path = os.path.join(prepared["root"], RECEIPT_PATH)
    try:
        persisted = kblib.read_bytes(receipt_path)
    except OSError as exc:
        raise Refusal("initial Task Plan Receipt is not published: %s" % exc)
    if persisted != prepared["receipt_bytes"]:
        raise Refusal(
            "initial Task Plan Receipt bytes differ from the staged evidence")
    result = runtime_validation.validate_runtime(
        prepared["root"], allow_unmaterialized_queue=True,
        **queue_runtime.runtime_authority_validation_kwargs(
            prepared["authority"]))
    if result["errors"]:
        raise Refusal(
            "published initial Task Plan does not validate: %s" %
            "; ".join(result["errors"][:12]))


def compile_command(prepared):
    queue = prepared["state_documents"]["queue"]
    return (
        "python3 Tools/compile_queue.py . --apply --actor-role integrator "
        "--expected-queue-revision %s --expected-sha256 %s" %
        (queue["queue_revision"], prepared["state_sha"]["queue"]))


def report(prepared):
    plan = prepared["plan"]
    print("initial Task Plan: %s (task %s)" %
          (plan["plan_id"], plan["task_id"]))
    print("  confirmed by: %s" % plan["approval_reference"])
    print("  planning-only Coverage records: %d" %
          len(plan["planned_work"]["pages"]))
    print("  batch specs: %d" % len(plan["planned_work"]["batch_specs"]))
    print("  Queue items after independent compilation: %d" %
          len(prepared["compiled_queue"].get("required_queue") or []))
    print("  concurrency_cap=%d (validated from %s)" %
          (plan["contract_after"]["concurrency_cap"],
           prepared["concurrency_cap_source"]))
    print("  resolved from %d route(s): %d Read Set(s), %d module(s)" %
          (prepared["derived"]["routes"],
           prepared["derived"]["read_sets"],
           prepared["derived"]["modules"]))
    print("  next: %s" % compile_command(prepared))
