#!/usr/bin/env python3
"""Register one approved, current-protocol Amendment in Progress.

Registration is authorization, not execution.  The default is a dry run.  In
write mode an integrator must supply exact fingerprints for Coverage, Queue,
and Progress; the tool rechecks all three plus staged artifacts under the
shared runtime writer lock, publishes an otherwise inert receipt, and
atomically replaces only Progress with the row that activates it.  Scope
and cancellation registrations consume the exact plan later consumed by
``apply_amendment.py``.  A same-scope Queue replan derives its bindings
deterministically from the current state and Coverage proposal.

Before publication the tool derives a closed impact from those exact bytes.
It either binds a matching Task Contract ``amendment_authority`` delegation or
requires a fresh explicit-user approval reference; downstream writers derive
and compare the same binding again under their writer lock.
"""

import contextlib
import copy
import os
import re
import sys

import Tools.execution.task_runtime.amendment_plan as amendment_plan
import Tools.execution.task_runtime.amendment_policy as amendment_policy
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.canon as queue_canon
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.planning.compile_queue as compile_queue
import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.execution.planning.queue_replan as queue_replan
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_io as runtime_state_io
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.common import reporting
from Tools.platform.common.primitives import nonempty_string


TOOL = queue_canon.REGISTER_AMENDMENT_TOOL
TOOL_VERSION = queue_canon.REGISTER_AMENDMENT_TOOL_VERSION
RECEIPT_TYPE_ID = "amendment-registration-receipt-v1"
RECEIPT_CHECKS = ("amendment_registration", "amendment_withdrawal")


def current_receipt_errors(record, *, root=None):
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=RECEIPT_CHECKS)
RECEIPT_PATH = runtime_paths.AMENDMENT_RECEIPT_PATH
OPERATIONS = tuple(sorted(
    runtime_state_contract.OPERATIONAL_AMENDMENT_OPERATIONS))
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _load_yaml(root, relative, prefix, suffixes):
    path = kblib.managed_repository_path(
        root, relative, prefix, suffixes=suffixes, must_exist=True,
    )
    if not os.path.isfile(path):
        raise ValueError("managed YAML path is not a regular file: %s" % relative)
    raw = kblib.read_bytes(path)
    try:
        value = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("%s is not UTF-8: %s" % (relative, exc))
    if not isinstance(value, dict):
        raise ValueError("%s top level must be a mapping" % relative)
    normalized = os.path.relpath(path, root).replace(os.sep, "/")
    return path, normalized, raw, value


def _read_state(paths):
    raw = {}
    for name, path in paths.items():
        with open(path, "rb") as fh:
            raw[name] = fh.read()
    return raw, {name: kblib.sha256_bytes(value)
                 for name, value in raw.items()}


def _require_current_schema(runtime):
    for label in runtime_state_contract.RUNTIME_LEDGER_IDS:
        value = runtime.get(label)
        if not isinstance(value, dict) or value.get("schema_version") != 2:
            raise ValueError(
                "%s must use the current schema_version 2" % label.title()
            )


def _check_control_identity(runtime):
    coverage = runtime["coverage"]
    queue = runtime["queue"]
    progress = runtime["progress"]
    contract = progress.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("Progress contract must be a mapping")
    for field in runtime_state_contract.RUNTIME_CONTROL_IDENTITY_FIELDS:
        values = [coverage.get(field), queue.get(field)]
        values.append(contract.get(field) if field != "task_id"
                      else progress.get(field))
        if values[0] != values[1] or values[1] != values[2]:
            raise ValueError("current state disagrees on %s" % field)


def _check_no_pending_or_duplicate(progress, amendment_id):
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        raise ValueError("Progress amendments must be an explicit list")
    for index, entry in enumerate(amendments):
        if not isinstance(entry, dict):
            raise ValueError("Progress amendments[%d] must be a mapping" % index)
        if entry.get("id") == amendment_id:
            raise ValueError("Progress already contains Amendment %s" % amendment_id)
        if (entry.get("operation") in OPERATIONS and
                entry.get("status") == "approved" and
                entry.get("writeback_done") is False):
            raise ValueError(
                "Progress already has pending Amendment %s" %
                entry.get("id", "<unnamed>")
            )


def _validate_cross_plan(root, runtime, operation, plan_relative):
    plan_file, plan_path, plan_raw, plan = _load_yaml(
        root, plan_relative, amendment_plan.PLAN_PREFIX,
        (".yaml", ".yml"),
    )
    amendment_plan.validate_plan(plan)
    if plan.get("operation") != operation:
        raise ValueError("--operation does not match the Amendment plan")
    proposal_relative = plan["coverage_proposal_path"]
    if os.path.normpath(proposal_relative) == os.path.normpath(plan_path):
        raise ValueError("plan and Coverage proposal must be different files")
    proposal_file, proposal_path, proposal_raw, proposal = _load_yaml(
        root, proposal_relative, amendment_plan.PLAN_PREFIX,
        (".yaml", ".yml"),
    )
    proposal_sha = kblib.sha256_bytes(proposal_raw)
    if proposal_sha != plan["coverage_proposal_sha256"]:
        raise ValueError("Coverage proposal SHA does not match plan")

    coverage = runtime["coverage"]
    queue = runtime["queue"]
    if (queue.get("scope_version") != plan["scope_version_before"] or
            queue.get("queue_revision") != plan["queue_revision_before"] or
            queue.get("state_revision") != plan["state_revision_before"]):
        raise ValueError("plan before scope/revisions do not match current Queue")
    current_pages, proposed_pages, changed_specs = \
        amendment_plan.validate_coverage_proposal(coverage, proposal, plan)

    if operation == "scope-replan":
        compile_base = copy.deepcopy(queue)
        compile_base["scope_version"] = plan["scope_version_after"]
        compiled, _ = compile_queue.compile_document(compile_base, proposal)
        diff = compile_queue.replan_diff(
            queue, compiled, kblib.sha256_file(runtime["queue_path"])
        )
        queue_replan.build_replanned_queue(queue, compiled, diff)
        changed_batches = sorted(set(changed_specs).union(
            amendment_plan.structural_changes(queue, compiled)
        ))
        if changed_batches != plan["affected_batches"]:
            raise ValueError(
                "affected_batches does not exactly match replan; "
                "found=%r expected=%r" %
                (changed_batches, plan["affected_batches"])
            )
    elif operation == "gap-routing-reconciliation":
        compiled, _ = compile_queue.compile_document(queue, proposal)
        structural = amendment_plan.structural_changes(queue, compiled)
        if changed_specs or structural:
            raise ValueError(
                "gap-routing-reconciliation may not change Queue structure")
    else:
        cancel_id = plan["cancel_batch_id"]
        if proposed_pages.keys() != current_pages.keys():
            raise ValueError("cancel-batch may not add or remove Coverage pages")
        if changed_specs != [cancel_id]:
            raise ValueError(
                "cancel-batch must remove exactly its own batch_specs entry"
            )
        item = next((entry for entry in queue.get("required_queue", [])
                     if isinstance(entry, dict) and entry.get("id") == cancel_id),
                    None)
        if item is None:
            raise ValueError("cancel_batch_id is absent from Queue")
        manifest = sorted(item.get("manifest") or [])
        if plan["affected_pages"] != manifest:
            raise ValueError("cancel-batch affected_pages must equal its manifest")
        for object_path in manifest:
            page = proposed_pages.get(object_path)
            if page is None:
                raise ValueError("cancelled object is absent from proposal: %s" %
                                 object_path)
            if page.get("coverage_disposition") == "required":
                raise ValueError("cancelled object remains Required: %s" %
                                 object_path)
            if page.get("next_batch") == cancel_id:
                raise ValueError("cancelled object still routes to %s" % cancel_id)
        # The pure helper also proves lifecycle eligibility and leaf status.
        amendment_plan.project_cancelled_queue(
            queue, plan, "1970-01-01T00:00:00Z", {"receipt_id": "candidate"}
        )

    record = {
        "id": plan["amendment_id"],
        "operation": operation,
        "affected_pages": copy.deepcopy(plan["affected_pages"]),
        "affected_batches": copy.deepcopy(plan["affected_batches"]),
        "scope_version_before": plan["scope_version_before"],
        "scope_version_after": plan["scope_version_after"],
        "queue_revision_before": plan["queue_revision_before"],
        "queue_revision_after": plan["queue_revision_after"],
        "state_revision_before": plan["state_revision_before"],
        "state_revision_after": plan["state_revision_after"],
        "coverage_proposal_path": proposal_path,
        "coverage_proposal_sha256": proposal_sha,
        "cancel_batch_id": plan["cancel_batch_id"],
        "plan_path": plan_path,
        "plan_sha256": kblib.sha256_bytes(plan_raw),
    }
    bindings = {
        "plan_path": plan_path,
        "plan_sha256": record["plan_sha256"],
        "coverage_proposal_path": proposal_path,
        "coverage_proposal_sha256": proposal_sha,
        "scope_version_before": plan["scope_version_before"],
        "scope_version_after": plan["scope_version_after"],
        "queue_revision_before": plan["queue_revision_before"],
        "queue_revision_after": plan["queue_revision_after"],
        "state_revision_before": plan["state_revision_before"],
        "state_revision_after": plan["state_revision_after"],
        "affected_pages": copy.deepcopy(plan["affected_pages"]),
        "affected_batches": copy.deepcopy(plan["affected_batches"]),
        "cancel_batch_id": plan["cancel_batch_id"],
    }
    artifacts = [
        {
            "relative": plan_path,
            "prefix": amendment_plan.PLAN_PREFIX,
            "suffixes": (".yaml", ".yml"),
            "sha256": record["plan_sha256"],
            "resolved_path": plan_file,
        },
        {
            "relative": proposal_path,
            "prefix": amendment_plan.PLAN_PREFIX,
            "suffixes": (".yaml", ".yml"),
            "sha256": proposal_sha,
            "resolved_path": proposal_file,
        },
    ]
    impact = amendment_policy.derive_amendment_impact(
        coverage, proposal, queue)
    if impact["writer_operation"] != operation:
        raise ValueError(
            "--operation=%s does not match derived writer operation %s" %
            (operation, impact["writer_operation"])
        )
    if impact["affected_pages"] != record["affected_pages"]:
        raise ValueError(
            "derived authority impact affected_pages does not match the "
            "registered plan"
        )
    return record, bindings, artifacts, impact, proposal


def _validate_queue_replan(root, runtime, amendment_id, proposal_relative):
    if not nonempty_string(amendment_id):
        raise ValueError("queue-replan requires --amendment-id")
    proposal_file, proposal_path, proposal_raw, proposal = _load_yaml(
        root, proposal_relative, runtime_paths.REPLAN_DELTA_ROOT,
        (".coverage.yaml",),
    )
    coverage = runtime["coverage"]
    queue = runtime["queue"]
    affected_pages = compile_queue.validate_same_scope_proposal(
        coverage, proposal
    )
    compiled, _ = compile_queue.compile_document(queue, proposal)
    diff = compile_queue.replan_diff(
        queue, compiled, kblib.sha256_file(runtime["queue_path"])
    )
    if not diff.get("has_structural_changes"):
        stale = diff.get("stale_terminal_spec_ids") or []
        if stale:
            # K13/08: a terminal batch keeps its history and loses its live
            # references.  The proposal edits a sealed item's spec row, which
            # can never take effect -- say so rather than reporting an empty
            # diff and leaving the author to guess.
            raise ValueError(
                "queue-replan proposal has no structural changes; it only "
                "edits the batch_specs row(s) of terminal batch(es) %s, whose "
                "Queue structure is sealed (K13/08 Batch Reference "
                "Settlement) — retire the row instead of editing it" %
                ", ".join(stale))
        raise ValueError("queue-replan proposal has no structural changes")
    if diff.get("remove_candidates") or diff.get("conflicts"):
        raise ValueError("queue-replan proposal is not safely applicable: %s" %
                         "; ".join(str(value) for value in
                                   (diff.get("conflicts") or [])))
    # This pure construction is the same final structural admissibility check
    # used by compile_queue --apply-replan.
    queue_replan.build_replanned_queue(queue, compiled, diff)
    diff_text = kblib.canonical_yaml(diff)
    affected_batches = queue_replan.changed_batch_ids(diff)
    if not affected_batches:
        raise ValueError("queue-replan must affect at least one batch")
    proposal_sha = kblib.sha256_bytes(proposal_raw)
    record = {
        "id": amendment_id,
        "operation": "queue-replan",
        "coverage_proposal_path": proposal_path,
        "coverage_proposal_sha256": proposal_sha,
        "affected_pages": affected_pages,
        "affected_batches": affected_batches,
        "scope_version_before": queue["scope_version"],
        "scope_version_after": queue["scope_version"],
        "queue_revision_before": queue["queue_revision"],
        "queue_revision_after": queue["queue_revision"] + 1,
        "queue_state_revision_before": queue["state_revision"],
        "queue_state_revision_after": queue["state_revision"],
        "replan_diff_sha256": kblib.sha256_bytes(diff_text),
    }
    bindings = copy.deepcopy(record)
    bindings.pop("id")
    bindings.pop("operation")
    artifacts = [{
        "relative": proposal_path,
        "prefix": runtime_paths.REPLAN_DELTA_ROOT,
        "suffixes": (".coverage.yaml",),
        "sha256": proposal_sha,
        "resolved_path": proposal_file,
    }]
    impact = amendment_policy.derive_amendment_impact(
        coverage, proposal, queue)
    if impact["writer_operation"] != "queue-replan":
        raise ValueError(
            "--operation=queue-replan does not match derived writer operation %s" %
            impact["writer_operation"]
        )
    if impact["affected_pages"] != record["affected_pages"]:
        raise ValueError(
            "derived authority impact affected_pages does not match the "
            "registered replan"
        )
    return record, bindings, artifacts, impact, proposal


def _revalidate_artifacts(root, artifacts):
    """Re-open every staged input under the writer lock and verify its bytes."""
    for artifact in artifacts:
        path, normalized, raw, _ = _load_yaml(
            root, artifact["relative"], artifact["prefix"],
            artifact["suffixes"],
        )
        if path != artifact["resolved_path"] or normalized != artifact["relative"]:
            raise ValueError(
                "staged artifact path changed after registration planning: %s" %
                artifact["relative"]
            )
        if kblib.sha256_bytes(raw) != artifact["sha256"]:
            raise ValueError(
                "staged artifact bytes changed after registration planning: %s" %
                artifact["relative"]
            )


def _prepare(root, args, expected):
    root = os.path.realpath(os.path.abspath(root))
    runtime = runtime_validation.validate_runtime(root)
    if runtime["errors"]:
        raise ValueError("current runtime is inconsistent: %s" %
                         "; ".join(runtime["errors"]))
    authority = queue_runtime.runtime_authority_context(runtime)
    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
    if runtime.get("_writer_locks"):
        raise ValueError("runtime has an active or interrupted writer lock")
    task_state = (runtime.get("progress") or {}).get("task_state")
    if task_state in ("completion-candidate", "complete", "cancelled"):
        raise ValueError(
            "task_state=%s forbids operational Amendment registration" %
            task_state
        )
    barrier = queue_runtime.delta_apply_write_barrier(
        runtime, TOOL, "register-amendment")
    if barrier:
        raise ValueError(barrier)
    _require_current_schema(runtime)
    _check_control_identity(runtime)
    paths = runtime_state_io.state_paths(root)
    before_raw, before_sha = _read_state(paths)
    for name in tuple(sorted(runtime_state_contract.RUNTIME_LEDGER_IDS)):
        if expected[name] != before_sha[name]:
            raise ValueError("expected %s SHA does not match current bytes" % name)

    if args.operation in (
            runtime_state_contract.AMENDMENT_OPERATIONS_BY_EXECUTION_CAPABILITY[
                runtime_state_contract.CROSS_LEDGER_AMENDMENT_CAPABILITY]):
        if not args.plan:
            raise ValueError("%s requires --plan" % args.operation)
        if args.amendment_id or args.coverage_proposal:
            raise ValueError("cross-Ledger registration derives id/proposal from --plan")
        record, bindings, artifacts, impact, proposal = _validate_cross_plan(
            root, runtime, args.operation, args.plan)
    else:
        if args.plan:
            raise ValueError("queue-replan does not consume --plan")
        if not args.coverage_proposal:
            raise ValueError("queue-replan requires --coverage-proposal")
        record, bindings, artifacts, impact, proposal = _validate_queue_replan(
            root, runtime, args.amendment_id, args.coverage_proposal
        )

    progress = runtime["progress"]
    _check_no_pending_or_duplicate(progress, record["id"])
    decision = amendment_policy.resolve_authority(
        progress.get("contract") or {}, impact,
        requested_mode=getattr(args, "decision_mode", "auto"),
        approval_reference=getattr(args, "approval_reference", None),
    )
    record.update({
        "date": args.date,
        "summary": args.summary,
        "approval_reference": decision["approval_reference"],
        "status": "approved",
        "writeback_done": False,
    })
    record.update({field: copy.deepcopy(decision[field]) for field in (
        "decision_mode", "authority_id", "authority_sha256",
        "change_classes", "amendment_impact_sha256",
    )})
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "amendment_registration", record["id"], "pass",
        "registered approved %s Amendment" % args.operation, 1,
        receipt_type_id=RECEIPT_TYPE_ID,
    )
    record["registration_receipt"] = receipt["receipt_id"]
    progress_new = copy.deepcopy(progress)
    progress_new["amendments"].append(record)
    progress_text = kblib.canonical_yaml(progress_new)
    after_sha = dict(before_sha)
    after_sha["progress"] = kblib.sha256_bytes(progress_text)
    receipt.update({
        "task_id": runtime["queue"].get("task_id"),
        "actor_role": "integrator",
        "amendment_id": record["id"],
        "operation": args.operation,
        "approval_reference": record["approval_reference"],
        "summary": args.summary,
        "contract_sha256": queue_runtime.contract_sha256(progress),
    })
    receipt.update({field: copy.deepcopy(record[field]) for field in (
        "decision_mode", "authority_id", "authority_sha256",
        "change_classes", "amendment_impact_sha256",
    )})
    receipt.update(copy.deepcopy(bindings))
    receipt["state_revision_before"] = (
        record.get("queue_state_revision_before")
        if args.operation == "queue-replan"
        else record.get("state_revision_before")
    )
    receipt["state_revision_after"] = (
        record.get("queue_state_revision_after")
        if args.operation == "queue-replan"
        else record.get("state_revision_after")
    )
    receipt["before_coverage_sha256"] = before_sha["coverage"]
    receipt["after_coverage_sha256"] = after_sha["coverage"]
    receipt["before_required_queue_sha256"] = before_sha["queue"]
    receipt["after_required_queue_sha256"] = after_sha["queue"]
    receipt["before_progress_sha256"] = before_sha["progress"]
    receipt["after_progress_sha256"] = after_sha["progress"]
    if args.date != receipt["checked_at"][:10]:
        raise ValueError(
            "--date must equal the UTC registration date %s" %
            receipt["checked_at"][:10]
        )

    planned = runtime_validation.validate_runtime(
        root,
        state_overrides={
            queue_runtime.PROGRESS_PATH: (progress_text, progress_new),
        },
        extra_receipts=[receipt],
        **authority_kwargs,
    )
    if planned["errors"]:
        raise ValueError("planned registration fails check_queue: %s" %
                         "; ".join(planned["errors"]))
    return {
        "runtime": runtime,
        "paths": paths,
        "before_raw": before_raw,
        "before_sha": before_sha,
        "after_sha": after_sha,
        "progress_text": progress_text,
        "record": record,
        "receipt": receipt,
        "artifacts": artifacts,
        "impact": impact,
        "proposal": proposal,
        "authority": authority,
    }


def _prepare_withdrawal(root, args, expected):
    """Retire one pending registration through the writer (K13/06).

    A pending operational Amendment whose planned execution can no longer
    validate — or whose approval is rescinded — would otherwise wedge the
    one-pending rule forever, and directly editing the row is forbidden.
    Withdrawal keeps the row and its bound plan/proposal bytes as immutable
    evidence, publishes an append-only withdrawal receipt naming the
    registration receipt, and sets the row's status to ``withdrawn`` with
    write-back still false.  The amendment ID is never reused.
    """
    root = os.path.realpath(os.path.abspath(root))
    runtime = runtime_validation.validate_runtime(root)
    if runtime["errors"]:
        raise ValueError("current runtime is inconsistent: %s" %
                         "; ".join(runtime["errors"]))
    authority = queue_runtime.runtime_authority_context(runtime)
    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
    if runtime.get("_writer_locks"):
        raise ValueError("runtime has an active or interrupted writer lock")
    if not nonempty_string(args.reason):
        raise ValueError("--withdraw requires a nonempty --reason")
    barrier = queue_runtime.delta_apply_write_barrier(
        runtime, TOOL, "withdraw-amendment")
    if barrier:
        raise ValueError(barrier)
    _require_current_schema(runtime)
    _check_control_identity(runtime)
    paths = runtime_state_io.state_paths(root)
    before_raw, before_sha = _read_state(paths)
    for name in tuple(sorted(runtime_state_contract.RUNTIME_LEDGER_IDS)):
        if expected[name] != before_sha[name]:
            raise ValueError("expected %s SHA does not match current bytes" % name)

    progress = runtime["progress"]
    row = None
    for entry in progress.get("amendments") or []:
        if isinstance(entry, dict) and entry.get("id") == args.withdraw:
            row = entry
            break
    if row is None:
        raise ValueError("Progress has no Amendment %s" % args.withdraw)
    if not (row.get("status") == "approved" and
            row.get("writeback_done") is False):
        raise ValueError(
            "Amendment %s is not pending (status=%r, writeback_done=%r); "
            "only a pending registration can be withdrawn" %
            (args.withdraw, row.get("status"), row.get("writeback_done"))
        )

    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "amendment_withdrawal", row["id"], "pass",
        "withdrew pending %s Amendment: %s" %
        (row.get("operation"), args.reason), 1,
        receipt_type_id=RECEIPT_TYPE_ID,
    )
    progress_new = copy.deepcopy(progress)
    for entry in progress_new["amendments"]:
        if entry.get("id") == row["id"]:
            entry["status"] = "withdrawn"
            entry["withdrawal_reason"] = args.reason
            entry["withdrawal_receipt"] = receipt["receipt_id"]
            record = entry
            break
    progress_text = kblib.canonical_yaml(progress_new)
    after_sha = dict(before_sha)
    after_sha["progress"] = kblib.sha256_bytes(progress_text)
    receipt.update({
        "task_id": runtime["queue"].get("task_id"),
        "actor_role": "integrator",
        "amendment_id": row["id"],
        "operation": row.get("operation"),
        "registration_receipt": row.get("registration_receipt"),
        "withdrawal_reason": args.reason,
        "contract_sha256": queue_runtime.contract_sha256(progress),
        "before_coverage_sha256": before_sha["coverage"],
        "after_coverage_sha256": after_sha["coverage"],
        "before_required_queue_sha256": before_sha["queue"],
        "after_required_queue_sha256": after_sha["queue"],
        "before_progress_sha256": before_sha["progress"],
        "after_progress_sha256": after_sha["progress"],
    })

    planned = runtime_validation.validate_runtime(
        root,
        state_overrides={
            queue_runtime.PROGRESS_PATH: (progress_text, progress_new),
        },
        extra_receipts=[receipt],
        **authority_kwargs,
    )
    if planned["errors"]:
        raise ValueError("planned withdrawal fails check_queue: %s" %
                         "; ".join(planned["errors"]))
    return {
        "runtime": runtime,
        "paths": paths,
        "before_raw": before_raw,
        "before_sha": before_sha,
        "after_sha": after_sha,
        "progress_text": progress_text,
        "record": record,
        "receipt": receipt,
        "artifacts": [],
        "action": "withdraw",
        "authority": authority,
    }


def _restore_progress(prepared):
    path = prepared["paths"]["progress"]
    try:
        kblib.atomic_write_text(
            path, prepared["before_raw"]["progress"].decode("utf-8"),
            validator=kblib.parse_yaml_subset,
        )
        with open(path, "rb") as fh:
            return fh.read() == prepared["before_raw"]["progress"]
    except Exception:
        return False


def _apply(root, prepared, receipt_path):
    root = os.path.realpath(os.path.abspath(root))
    receipt_path = os.path.realpath(os.path.abspath(receipt_path))
    receipt_relative = os.path.relpath(receipt_path, root).replace(os.sep, "/")
    authority = prepared["authority"]
    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
    operation = {
        "tool": TOOL,
        "action": prepared.get("action", "register"),
        "task_id": prepared["runtime"]["queue"].get("task_id"),
        "target": prepared["record"]["id"],
        "amendment_id": prepared["record"]["id"],
        "amendment_operation": prepared["record"]["operation"],
        "actor_role": "integrator",
        "receipt_id": prepared["receipt"]["receipt_id"],
        "receipt_path": receipt_relative,
        "registration_receipt": prepared["receipt"]["receipt_id"],
    }
    for name in ("coverage", "progress"):
        operation["before_%s_sha256" % name] = prepared["before_sha"][name]
        operation["planned_after_%s_sha256" % name] = prepared["after_sha"][name]
    operation["before_queue_sha256"] = prepared["before_sha"]["queue"]
    operation["planned_after_queue_sha256"] = \
        prepared["after_sha"]["queue"]
    operation.update(queue_runtime.runtime_authority_lock_fields(authority))

    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        with kblib.no_authoritative_write_guard(lease):
            _, locked_sha = _read_state(prepared["paths"])
            if locked_sha != prepared["before_sha"]:
                raise ValueError("canonical state changed after registration planning")
            locked = runtime_validation.validate_runtime(
                root, **authority_kwargs)
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            queue_runtime.require_runtime_authority_current(
                root, authority, "runtime authority changed under lock")
            _require_current_schema(locked)
            _revalidate_artifacts(root, prepared["artifacts"])
            if "impact" in prepared:
                locked_impact = amendment_policy.derive_amendment_impact(
                    locked["coverage"], prepared["proposal"], locked["queue"])
                amendment_policy.require_decision_binding(
                    (locked["progress"].get("contract") or {}),
                    locked_impact, prepared["record"])

        receipt_before = kblib.receipt_append_observation(
            receipt_path, [prepared["receipt"]]
        )
        try:
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before Amendment receipt")
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, [prepared["receipt"]], before=receipt_before,
            )
            if error is not None or outcome != "present":
                raise error or OSError(
                    "registration receipt append outcome was %s" % outcome
                )
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during Amendment receipt")
            # The receipt is published first.  By itself it is an unreferenced
            # historical record and cannot authorize execution; authority
            # exists only after the pending Progress row names this exact ID.
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before Progress write")
            kblib.atomic_write_text(
                prepared["paths"]["progress"], prepared["progress_text"],
                validator=kblib.parse_yaml_subset,
            )
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during Progress write")
        except Exception:
            restored = _restore_progress(prepared)
            receipt_outcome = kblib.receipt_outcome_from(
                receipt_path, [prepared["receipt"]], receipt_before,
            )
            if restored and receipt_outcome == "absent":
                lease.mark_reconciled()
            raise

        _, committed_sha = _read_state(prepared["paths"])
        if committed_sha != prepared["after_sha"]:
            raise ValueError("registered state differs from planned fingerprints")
        persisted = runtime_validation.validate_runtime(
            root, **authority_kwargs)
        if persisted["errors"]:
            raise ValueError("persisted registration fails check_queue: %s" %
                             "; ".join(persisted["errors"]))


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Register one approved current-protocol Amendment"
    )
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--operation", choices=OPERATIONS,
                        help="Amendment operation being registered")
    parser.add_argument("--plan",
                        help="%s/*.yaml plan" %
                        runtime_paths.AMENDMENT_DELTA_ROOT)
    parser.add_argument("--amendment-id",
                        help="id for a queue-replan registration; cross-Ledger "
                             "operations derive it from --plan instead")
    parser.add_argument("--coverage-proposal",
                        help="%s/*.coverage.yaml proposal" %
                        runtime_paths.REPLAN_DELTA_ROOT)
    parser.add_argument("--withdraw", metavar="AMENDMENT_ID",
                        help="retire the named pending registration instead "
                             "of registering one (K13/06 withdrawal); "
                             "requires --reason")
    parser.add_argument("--reason",
                        help="nonempty withdrawal reason recorded on the row "
                             "and its receipt")
    parser.add_argument("--date",
                        help="YYYY-MM-DD; must equal the UTC registration date")
    parser.add_argument("--summary",
                        help="non-empty one-line rationale recorded on the row")
    parser.add_argument("--approval-reference",
                        help="explicit-user approval reference; required when "
                             "--decision-mode is explicit-user")
    parser.add_argument(
        "--decision-mode",
        choices=("auto", "contract-delegated", "explicit-user"),
        default="auto",
        help="derive delegated authority by default; explicit-user requires "
             "--approval-reference",
    )
    parser.add_argument("--expected-coverage-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Coverage; registration is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-progress-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Progress; registration is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-queue-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Queue; registration is "
                             "refused when the live bytes differ")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may "
                             "register or withdraw an Amendment")
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--apply", action="store_true",
                        help="write the registration; omit for a dry run")
    parser.add_argument(
        "--json", action="store_true",
        help="write the published receipt to stdout as one canonical JSON "
             "array and move the human report to stderr; a dry run publishes "
             "no receipt and so writes nothing there; receipt writing and "
             "exit codes are unchanged")
    args = parser.parse_args(argv)

    if not args.json:
        return _run(args, None)
    produced = []
    with contextlib.redirect_stdout(sys.stderr):
        code = _run(args, produced)
    reporting.write_canonical_json_array(produced, omit_if_empty=True)
    return code


def _run(args, produced):
    """Execute one already-parsed invocation; ``produced`` collects receipts."""
    if args.withdraw:
        conflicting = [name for name, value in (
            ("--operation", args.operation), ("--plan", args.plan),
            ("--amendment-id", args.amendment_id),
            ("--coverage-proposal", args.coverage_proposal),
            ("--date", args.date), ("--summary", args.summary),
            ("--approval-reference", args.approval_reference),
            ("--decision-mode", (args.decision_mode
                                  if args.decision_mode != "auto" else None)),
        ) if value]
        if conflicting:
            print("[FAIL] --withdraw takes no registration argument(s): %s" %
                  ", ".join(conflicting))
            return 1
        if not nonempty_string(args.reason):
            print("[FAIL] --withdraw requires a nonempty --reason")
            return 1
    else:
        if args.reason:
            print("[FAIL] --reason belongs to --withdraw")
            return 1
        for label, value in (("operation", args.operation),
                             ("date", args.date),
                             ("summary", args.summary)):
            if not value:
                print("[FAIL] registration requires --%s" % label)
                return 1
        if not DATE_RE.fullmatch(args.date):
            print("[FAIL] --date must use YYYY-MM-DD")
            return 1
        for label, value in (("summary", args.summary),):
            if not nonempty_string(value):
                print("[FAIL] --%s must be a non-empty string" % label)
                return 1
        if (args.approval_reference is not None and
                not nonempty_string(args.approval_reference)):
            print("[FAIL] --approval-reference must be a non-empty string")
            return 1
        if (args.decision_mode == "explicit-user" and
                not nonempty_string(args.approval_reference)):
            print("[FAIL] --decision-mode explicit-user requires a non-empty "
                  "--approval-reference")
            return 1
    expected = {
        "coverage": args.expected_coverage_sha256,
        "progress": args.expected_progress_sha256,
        "queue": args.expected_queue_sha256,
    }
    for name, value in expected.items():
        if not queue_runtime.SHA256_RE.fullmatch(str(value)):
            print("[FAIL] expected %s SHA must be sha256:<64 lowercase hex>" %
                  name)
            return 1
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False,
        )
        prepared = (_prepare_withdrawal(root, args, expected)
                    if args.withdraw else _prepare(root, args, expected))
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1

    print("Amendment %s: %s operation=%s" %
          ("withdrawal" if args.withdraw else "registration",
           prepared["record"]["id"],
           prepared["record"].get("operation") or args.operation))
    if not args.withdraw:
        print("decision_mode=%s change_classes=%s" %
              (prepared["record"]["decision_mode"],
               ",".join(prepared["record"]["change_classes"])))
    for name in runtime_state_contract.RUNTIME_LEDGER_IDS:
        print("%s_sha256=%s -> %s" %
              (name, prepared["before_sha"][name],
               prepared["after_sha"][name]))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with the same expected SHAs")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may register or withdraw "
              "an Amendment")
        return 1
    try:
        _apply(root, prepared, receipt_path)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] Amendment %s: %s" %
              ("withdrawal" if args.withdraw else "registration", exc))
        return 1
    if produced is not None:
        produced.append(prepared["receipt"])
    print("[PASS] Amendment %s %s; receipt=%s" %
          (prepared["record"]["id"],
           "withdrawn" if args.withdraw else "registered",
           prepared["receipt"]["receipt_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
