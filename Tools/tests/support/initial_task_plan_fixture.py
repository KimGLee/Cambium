"""Build the one legal hard-cut initial Task Plan history for runtime tests.

The production runtime no longer accepts a state skeleton that later tools
silently reinterpret as planned work.  Test repositories therefore start from
the same two transactions as an adopter:

1. one confirmed Task Plan publishes the Task Contract, planning-only
   Coverage, and an empty Queue;
2. ``compile_queue`` materializes the Required Queue without replacing the
   retained Task Plan Receipt reference.

This module is the only test owner of that history.  Tests which need an
invalid runtime first call this builder and then mutate the single field under
test.  It deliberately calls the production shape helpers instead of copying
their field sets into another fixture contract.
"""

from pathlib import Path
import copy
import json

from Tools.execution.planning import apply_task_plan
from Tools.execution.planning import compile_queue
from Tools.execution.task_runtime import queue_runtime
from Tools.execution.task_runtime import runtime_paths
from Tools.platform.common import kblib


FIXTURE_PLAN_ID = "TP-fixture-initial"
FIXTURE_PLAN_RELATIVE = (
    runtime_paths.TASK_PLAN_DELTA_ROOT + "/" + FIXTURE_PLAN_ID + ".yaml"
)
FIXTURE_PLAN_RECEIPT_ID = "audit-fixture-initial-task-plan"
FIXTURE_QUEUE_RECEIPT_ID = "audit-fixture-initial-queue"
FIXTURE_APPROVAL_REFERENCE = "fixture operator confirmation"

_RUNTIME_PAGE_FIELDS = frozenset((
    "authoring_status", "gate_receipts", "property_state",
))


def confirmed_initial_task_plan(*, upstream_revision_id,
                                profile_manifest="profiles/sample/profile.toml",
                                task_id="new-task",
                                plan_id=FIXTURE_PLAN_ID,
                                objective="Exercise safe runtime publication",
                                exclusions=None, concurrency_cap=1):
    """Return one legal confirmed-plan baseline for blank-runtime tests.

    Tests mutate a copy of this value when proving a refusal.  Keeping the
    baseline here prevents each safety suite from inventing a second Task Plan
    shape while still leaving every semantic value explicit.
    """
    batch_id = "%s-B0" % task_id
    return {
        "schema_version": 4,
        "plan_id": plan_id,
        "task_id": task_id,
        "approval_reference": "fixture operator confirmation",
        "contract_after": {
            "contract_version": "c1",
            "completion_semantics": "build",
            "objective": objective,
            "exclusions": list(exclusions or []),
            "scope_version": "s1",
            "concurrency_cap": concurrency_cap,
            "upstream_revision_id": upstream_revision_id,
            "selected_profile_manifest": profile_manifest,
            "selected_route_ids": ["R02"],
            "selected_profile_route_ids": [],
            "selected_card_paths": [],
            "selected_read_sets": [],
            "loaded_module_paths": [],
            "minimum_run_until": "",
            "checkpoint_at": "",
            "hard_stop_at": "",
            "completion_gate": "required-queue-complete",
            "policy_exceptions": [],
            "amendment_authority": {
                "schema_version": 1,
                "authority_id": "AUTH-FIXTURE",
                "mode": "user-only",
                "allowed_change_classes": [],
            },
        },
        "planned_work": {
            "pages": [{
                "path": "Notes/First Owner.md",
                "canonical_owner": "Notes/First Owner.md",
                "type": "concept",
                "tier": "M",
                "priority": "P1",
                "coverage_disposition": "required",
                "prerequisites": [],
                "batch": None,
                "next_batch": batch_id,
                "deferred_reason": None,
                "reentry_condition": None,
            }],
            "batch_specs": [{
                "id": batch_id,
                "family": "founding",
                "order_hint": 1,
                "source_route": "R02",
                "execution_mode": "serial-integrator",
                "depends_on": [],
                "confirmation_required": False,
                "work_spec_path": None,
                "work_spec_sha256": None,
            }],
        },
    }


def _load(root, relative):
    return kblib.load_yaml_file(Path(root) / relative)


def _write_yaml(root, relative, document):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    text = kblib.canonical_yaml(document)
    path.write_text(text, encoding="utf-8")
    return text


def _planning_pages(coverage):
    pages = []
    for record in coverage.get("pages") or []:
        if not isinstance(record, dict):
            raise AssertionError("fixture Coverage page must be a mapping")
        planned = {
            field: copy.deepcopy(value)
            for field, value in record.items()
            if field not in _RUNTIME_PAGE_FIELDS
        }
        pages.append(planned)
    return pages


def _profile_evidence(root, manifest):
    view, errors = queue_runtime.profile_load_authorized_view(root, manifest)
    if errors:
        raise AssertionError(
            "fixture Profile is not authorized for initial planning: %s" %
            "; ".join(errors)
        )
    return queue_runtime.public_profile_load_evidence(view)


def _active_standards_sha(root, contract):
    view, errors = queue_runtime.active_standards_authorized_view(
        root, contract["upstream_revision_id"],
        contract["selected_profile_manifest"],
    )
    if errors:
        raise AssertionError(
            "fixture Standards state is not authorized for initial planning: "
            "%s" % "; ".join(errors)
        )
    return view["active_standards_sha256"]


def _replace_receipt(root, relative, receipt_id, receipt):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    if path.exists():
        records = [
            json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip()
        ]
    records = [
        record for record in records
        if record.get("receipt_id") != receipt_id
    ]
    records.append(receipt)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) +
                "\n" for record in records),
        encoding="utf-8",
    )


def install_initial_task_plan_fixture(root, *, materialize_queue=True):
    """Install a complete Task Plan -> Queue history into a scratch repo.

    A repository without the three state documents is an onboarding/profile
    fixture and is intentionally left alone.  A repository with runtime state
    is normalized to the current hard-cut contract: queued pages stay in their
    planning-only form until a batch-opening writer materializes them.
    """
    root = Path(root)
    state_paths = (
        root / queue_runtime.COVERAGE_PATH,
        root / queue_runtime.QUEUE_PATH,
        root / queue_runtime.PROGRESS_PATH,
    )
    if not any(path.exists() for path in state_paths):
        return None
    if not all(path.is_file() for path in state_paths):
        raise AssertionError(
            "fixture runtime must contain Coverage, Queue, and Progress"
        )

    coverage = _load(root, queue_runtime.COVERAGE_PATH)
    live_queue = _load(root, queue_runtime.QUEUE_PATH)
    live_progress = _load(root, queue_runtime.PROGRESS_PATH)
    contract = copy.deepcopy(live_progress.get("contract"))
    if not isinstance(contract, dict):
        raise AssertionError("fixture Progress contract must be a mapping")

    plan = {
        "schema_version": 4,
        "plan_id": FIXTURE_PLAN_ID,
        "task_id": live_progress.get("task_id"),
        "approval_reference": FIXTURE_APPROVAL_REFERENCE,
        "contract_after": copy.deepcopy(contract),
        "planned_work": {
            "pages": _planning_pages(coverage),
            "batch_specs": copy.deepcopy(coverage.get("batch_specs") or []),
        },
    }
    try:
        apply_task_plan._validate_plan_shape(plan)
    except apply_task_plan.Refusal as exc:
        raise AssertionError(
            "shared fixture cannot form a legal initial Task Plan: %s" % exc
        ) from exc

    plan_text = _write_yaml(root, FIXTURE_PLAN_RELATIVE, plan)
    plan_sha = kblib.sha256_bytes(plan_text)
    profile_evidence = _profile_evidence(
        str(root), contract["selected_profile_manifest"])
    receipt = apply_task_plan._receipt(
        plan, FIXTURE_PLAN_RELATIVE, plan_sha, profile_evidence)
    receipt["receipt_id"] = FIXTURE_PLAN_RECEIPT_ID
    # The fixture's Coverage timestamp is the historical transaction time.
    # Reusing it keeps repeated fixture installation byte-stable.
    receipt["checked_at"] = coverage.get("updated_at") or \
        "2026-08-04T00:00:00Z"

    empty_queue = apply_task_plan._empty_queue(plan)
    empty_queue_text = kblib.canonical_yaml(empty_queue)
    planning_coverage = apply_task_plan._coverage(
        plan, receipt["checked_at"])
    planning_coverage_text = _write_yaml(
        root, queue_runtime.COVERAGE_PATH, planning_coverage)
    planning_progress = apply_task_plan._progress(
        plan, contract, empty_queue_text, FIXTURE_PLAN_RECEIPT_ID)
    planning_progress_text = kblib.canonical_yaml(planning_progress)

    receipt.update({
        "after_coverage_sha256": kblib.sha256_bytes(
            planning_coverage_text),
        "after_required_queue_sha256": kblib.sha256_bytes(empty_queue_text),
        "after_progress_sha256": kblib.sha256_bytes(planning_progress_text),
        "contract_sha256": queue_runtime.contract_sha256(planning_progress),
        "contract_version": contract["contract_version"],
        "contract_scope_version": contract["scope_version"],
        "active_standards_sha256": _active_standards_sha(
            str(root), contract),
    })
    _replace_receipt(
        root, runtime_paths.TASK_PLAN_RECEIPT_PATH,
        FIXTURE_PLAN_RECEIPT_ID, receipt)

    # Prove that the plan has one deterministic Queue result before either
    # exposing that result or retaining the legitimate unmaterialized state.
    materialized, changed = compile_queue.compile_document(
        copy.deepcopy(empty_queue), planning_coverage)
    if not changed:
        raise AssertionError("fixture Task Plan did not materialize a Queue")
    if not materialize_queue:
        _write_yaml(root, queue_runtime.QUEUE_PATH, empty_queue)
        _write_yaml(root, queue_runtime.PROGRESS_PATH, planning_progress)
        _remove_receipt(
            root, runtime_paths.TASK_TRANSITION_RECEIPT_PATH,
            FIXTURE_QUEUE_RECEIPT_ID)
        return {
            "plan": plan,
            "plan_receipt": receipt,
            "queue_receipt": None,
        }

    # Materialize the current Queue from the same planning Coverage.  This is
    # the exact independent transaction production compile_queue performs.
    expected_items = materialized.get("required_queue")
    actual_items = live_queue.get("required_queue")
    if expected_items != actual_items:
        raise AssertionError(
            "fixture Queue structure differs from its Task Plan compiler "
            "result"
        )
    live_queue = materialized
    live_queue_text = _write_yaml(root, queue_runtime.QUEUE_PATH, live_queue)

    live_progress["queue_revision"] = live_queue["queue_revision"]
    live_progress["queue_state_revision"] = live_queue["state_revision"]
    live_progress["required_queue_sha256"] = kblib.sha256_bytes(
        live_queue_text)
    live_progress["initial_task_plan_receipt"] = \
        FIXTURE_PLAN_RECEIPT_ID
    live_progress["initial_queue_receipt"] = FIXTURE_QUEUE_RECEIPT_ID
    checkpoint = live_progress.get("checkpoint")
    if isinstance(checkpoint, dict):
        checkpoint["queue_revision"] = live_queue["queue_revision"]
        checkpoint["queue_state_revision"] = live_queue["state_revision"]
    live_progress_text = _write_yaml(
        root, queue_runtime.PROGRESS_PATH, live_progress)

    queue_receipt = kblib.make_receipt(
        "compile_queue", compile_queue.TOOL_VERSION, "queue_structure",
        queue_runtime.QUEUE_PATH, "pass",
        "fixture initial Queue materialization", 1,
        receipt_type_id=compile_queue.RECEIPT_TYPE_ID,
        identity={
            "task_id": plan["task_id"],
            "upstream_revision_id": contract["upstream_revision_id"],
            "selected_profile_manifest":
                contract["selected_profile_manifest"],
        },
    )
    queue_receipt.update({
        "receipt_id": FIXTURE_QUEUE_RECEIPT_ID,
        "checked_at": receipt["checked_at"],
        "contract_sha256": queue_runtime.contract_sha256(live_progress),
        "contract_version": contract["contract_version"],
        "contract_scope_version": contract["scope_version"],
        "before_required_queue_sha256": kblib.sha256_bytes(empty_queue_text),
        "after_required_queue_sha256": kblib.sha256_bytes(live_queue_text),
        "before_coverage_sha256": kblib.sha256_bytes(
            planning_coverage_text),
        "after_coverage_sha256": kblib.sha256_bytes(
            planning_coverage_text),
        "before_progress_sha256": kblib.sha256_bytes(
            planning_progress_text),
        "after_progress_sha256": kblib.sha256_bytes(live_progress_text),
        "before_queue_revision": empty_queue["queue_revision"],
        "after_queue_revision": live_queue["queue_revision"],
        "queue_state_revision": live_queue["state_revision"],
        "actor_role": "integrator",
    })
    _replace_receipt(
        root, runtime_paths.TASK_TRANSITION_RECEIPT_PATH,
        FIXTURE_QUEUE_RECEIPT_ID, queue_receipt)
    return {
        "plan": plan,
        "plan_receipt": receipt,
        "queue_receipt": queue_receipt,
    }


def reset_to_initial_task_plan_fixture(root):
    """Return an untouched fixture runtime to its unmaterialized boundary.

    Tests of ``compile_queue`` use this instead of deleting a Queue receipt
    pointer by hand.  The resulting three documents and Receipt body are the
    actual Task Plan after-image and therefore pass the same currentness checks
    as production state.
    """
    root = Path(root)
    plan = _load(root, FIXTURE_PLAN_RELATIVE)
    contract = copy.deepcopy(plan["contract_after"])
    plan_receipts = _load_receipts(
        root / runtime_paths.TASK_PLAN_RECEIPT_PATH)
    receipt = next((row for row in plan_receipts
                    if row.get("receipt_id") ==
                    FIXTURE_PLAN_RECEIPT_ID), None)
    if receipt is None:
        raise AssertionError("fixture initial Task Plan Receipt is absent")
    queue = apply_task_plan._empty_queue(plan)
    queue_text = _write_yaml(root, queue_runtime.QUEUE_PATH, queue)
    coverage = apply_task_plan._coverage(plan, receipt["checked_at"])
    coverage_text = _write_yaml(root, queue_runtime.COVERAGE_PATH, coverage)
    progress = apply_task_plan._progress(
        plan, contract, queue_text, FIXTURE_PLAN_RECEIPT_ID)
    progress_text = _write_yaml(root, queue_runtime.PROGRESS_PATH, progress)
    expected = {
        "after_required_queue_sha256": kblib.sha256_bytes(queue_text),
        "after_coverage_sha256": kblib.sha256_bytes(coverage_text),
        "after_progress_sha256": kblib.sha256_bytes(progress_text),
        "contract_sha256": queue_runtime.contract_sha256(progress),
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise AssertionError(
                "fixture Task Plan Receipt %s does not bind reconstructed "
                "after-image" % field
            )
    return progress


def _load_receipts(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines() if line.strip()]


def _remove_receipt(root, relative, receipt_id):
    path = Path(root) / relative
    if not path.exists():
        return
    records = [row for row in _load_receipts(path)
               if row.get("receipt_id") != receipt_id]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) +
                "\n" for row in records),
        encoding="utf-8",
    )


__all__ = [
    "FIXTURE_PLAN_ID",
    "FIXTURE_PLAN_RECEIPT_ID",
    "FIXTURE_PLAN_RELATIVE",
    "FIXTURE_QUEUE_RECEIPT_ID",
    "confirmed_initial_task_plan",
    "install_initial_task_plan_fixture",
    "reset_to_initial_task_plan_fixture",
]
