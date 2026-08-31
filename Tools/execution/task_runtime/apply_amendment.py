#!/usr/bin/env python3
"""Apply one approved scope Amendment across Coverage, Queue, and Progress.

The default is a dry run.  The apply path holds the shared runtime writer lock,
appends a durable prepare receipt, replaces the three canonical documents one
at a time, and rolls all three back on an ordinary failure.  A process crash
can interrupt those replacements; the surviving lock owner metadata and
prepare receipt bind every before/planned-after fingerprint for recovery.
The registered change-class/authority binding is re-derived before planning
and again under that same lock; a registration never authorizes different
proposal bytes merely because its Amendment id still matches.
"""

import copy
import os
import sys
import time
import uuid

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.canon as queue_canon
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.planning.compile_queue as compile_queue
import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.execution.task_runtime.amendment_plan as amendment_plan
import Tools.execution.task_runtime.amendment_policy as amendment_policy
import Tools.execution.planning.queue_replan as queue_replan
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.common import reporting
from Tools.platform.common.primitives import nonempty_string

TOOL = queue_canon.APPLY_AMENDMENT_TOOL
TOOL_VERSION = queue_canon.APPLY_AMENDMENT_TOOL_VERSION
RECEIPT_TYPE_ID = "amendment-transaction-receipt-v1"
QUEUE_CANCELLATION_RECEIPT_TYPE_ID = \
    runtime_state_contract.AMENDMENT_BATCH_CANCELLATION_REPLAY_PROTOCOL


def current_receipt_errors(record, *, root=None):
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks="amendment_transaction")


def current_queue_cancellation_receipt_errors(record, *, root=None):
    """Validate the current cross-ledger cancellation transition Receipt.

    A cancellation is not an ordinary ``update_queue`` transition.  It is an
    edge performed by the cross-ledger Amendment transaction, so it has its
    own type and check identity while retaining the existing K13 cancellation
    capability and lifecycle edge.  This prevents one body from pretending
    to be both the transaction record and the Queue-transition record.
    """
    errors = receipt_type_contract.base_receipt_errors(
        record,
        receipt_type_id=QUEUE_CANCELLATION_RECEIPT_TYPE_ID,
        tool=TOOL,
        tool_version=TOOL_VERSION,
        checks="amendment_queue_transition",
    )
    if not isinstance(record, dict):
        return errors
    required = (
        "task_id", "amendment_id", "operation", "actor_role",
        "before_state", "after_state", "before_hold_state",
        "after_hold_state", "before_state_revision", "after_state_revision",
        "before_required_queue_sha256", "after_required_queue_sha256",
        "queue_revision",
    )
    for field in required:
        if field not in record:
            errors.append("cancellation transition Receipt misses %s" % field)
    if record.get("operation") != "cancel-batch":
        errors.append("cancellation transition operation must be cancel-batch")
    if record.get("after_state") != "cancelled":
        errors.append("cancellation transition after_state must be cancelled")
    if record.get("actor_role") != "integrator":
        errors.append("cancellation transition actor_role must be integrator")
    return errors
RECEIPT_PATH = runtime_paths.AMENDMENT_RECEIPT_PATH

JSON_HELP = reporting.JSON_RECEIPT_HELP
_JSON_REPORTER = reporting.JsonReceiptCollector()


def _load_managed(root, relative, prefix, must_exist=True):
    path = kblib.managed_repository_path(
        root, relative, prefix, suffixes=(".yaml", ".yml"),
        must_exist=must_exist,
    )
    if must_exist and not os.path.isfile(path):
        raise ValueError("managed YAML path is not a regular file: %s" % relative)
    raw = kblib.read_bytes(path)
    try:
        data = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("%s is not UTF-8: %s" % (relative, exc))
    if not isinstance(data, dict):
        raise ValueError("%s top level must be a mapping" % relative)
    return path, raw, data


def _find_amendment(progress, plan, plan_path=None, plan_sha=None):
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        raise ValueError("Progress amendments must be an explicit list")
    matches = [entry for entry in amendments
               if isinstance(entry, dict) and
               entry.get("id") == plan["amendment_id"]]
    if len(matches) != 1:
        raise ValueError("Progress must contain exactly one matching Amendment %s" %
                         plan["amendment_id"])
    amendment = matches[0]
    if amendment.get("status") != "approved":
        raise ValueError("Progress Amendment status must be approved")
    if amendment.get("writeback_done") is not False:
        raise ValueError("Progress Amendment writeback_done must be false")
    if not nonempty_string(amendment.get("approval_reference")):
        raise ValueError("Progress Amendment approval_reference must be non-empty")
    if not nonempty_string(amendment.get("registration_receipt")):
        raise ValueError("Progress Amendment registration_receipt must be non-empty")
    if plan_path is not None and amendment.get("plan_path") != plan_path:
        raise ValueError("Progress Amendment plan_path does not match plan")
    if plan_sha is not None and amendment.get("plan_sha256") != plan_sha:
        raise ValueError("Progress Amendment plan_sha256 does not match plan")
    for amendment_field, plan_field in amendment_plan.AMENDMENT_BINDINGS.items():
        if amendment.get(amendment_field) != plan.get(plan_field):
            raise ValueError("Progress Amendment %s does not match plan" %
                             amendment_field)
    pending = [entry for entry in amendments
               if isinstance(entry, dict) and
               entry.get("operation") in amendment_plan.OPERATIONS and
               entry.get("status") == "approved" and
               entry.get("writeback_done") is False]
    if pending != [amendment]:
        raise ValueError("the selected plan must be the only pending "
                         "cross-Ledger Amendment")
    return amendment


def _transaction_chain_head(progress):
    verified = [entry for entry in progress.get("amendments", [])
                if isinstance(entry, dict) and
                entry.get("operation") in amendment_plan.OPERATIONS and
                entry.get("status") == "verified" and
                entry.get("writeback_done") is True]
    if not verified:
        return 1, None
    last = verified[-1]
    sequence = last.get("transaction_sequence")
    receipt_id = last.get("verification_receipt")
    if (not isinstance(sequence, int) or isinstance(sequence, bool) or
            sequence < 1 or not nonempty_string(receipt_id)):
        raise ValueError("verified Amendment transaction chain is malformed")
    return sequence + 1, receipt_id


def _sync_progress(progress, plan, queue, queue_text, transaction_id,
                   verification_receipt, transaction_sequence,
                   previous_transaction_commit_receipt, plan_path, plan_sha,
                   proposal_path, proposal_sha):
    result = copy.deepcopy(progress)
    contract = result.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("Progress contract must be a mapping")
    contract["scope_version"] = plan["scope_version_after"]
    result["queue_revision"] = queue["queue_revision"]
    result["queue_state_revision"] = queue["state_revision"]
    result["required_queue_sha256"] = kblib.sha256_bytes(queue_text)
    amendment = _find_amendment(result, plan)
    amendment["status"] = "verified"
    amendment["writeback_done"] = True
    amendment["transaction_id"] = transaction_id
    amendment["verification_receipt"] = verification_receipt
    amendment["transaction_sequence"] = transaction_sequence
    amendment["previous_transaction_commit_receipt"] = \
        previous_transaction_commit_receipt
    amendment["plan_path"] = plan_path
    amendment["plan_sha256"] = plan_sha
    amendment["coverage_proposal_path"] = proposal_path
    amendment["coverage_proposal_sha256"] = proposal_sha
    return result


def _new_transaction_receipt(phase, result, plan, transaction_id, plan_path,
                             plan_sha, proposal_path, proposal_sha,
                             transaction_sequence,
                             previous_transaction_commit_receipt, task_id,
                             registration_receipt):
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "amendment_transaction", plan["amendment_id"],
        result, "%s %s" % (phase, plan["operation"]),
        {"prepare": 1, "commit": 2, "abort": 3}[phase],
        receipt_type_id=RECEIPT_TYPE_ID,
    )
    receipt.update({
        "transaction_phase": phase,
        "task_id": task_id,
        "transaction_id": transaction_id,
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "coverage_proposal_path": proposal_path,
        "coverage_proposal_sha256": proposal_sha,
        "amendment_id": plan["amendment_id"],
        "operation": plan["operation"],
        "actor_role": "integrator",
        "transaction_sequence": transaction_sequence,
        "previous_transaction_commit_receipt":
            previous_transaction_commit_receipt,
        "registration_receipt": registration_receipt,
    })
    return receipt


def _new_queue_cancellation_receipt(plan, task_id, checked_at):
    """Build the distinct Receipt for the Amendment-owned cancellation edge."""
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "amendment_queue_transition",
        plan["cancel_batch_id"], "pass",
        "cancelled by cross-Ledger Amendment %s" % plan["amendment_id"],
        10, receipt_type_id=QUEUE_CANCELLATION_RECEIPT_TYPE_ID,
    )
    receipt.update({
        "checked_at": checked_at,
        "task_id": task_id,
        "amendment_id": plan["amendment_id"],
        "operation": "cancel-batch",
        "actor_role": "integrator",
    })
    return receipt


def _transaction_fields(receipt, before, after):
    for name in tuple(sorted(runtime_state_contract.RUNTIME_LEDGER_IDS)):
        receipt["before_%s_sha256" % name] = before[name]
        receipt["after_%s_sha256" % name] = after[name]


def _lock_operation(plan, transaction_id, plan_sha, before, after,
                    prepare_receipt_id, transaction_sequence,
                    previous_transaction_commit_receipt,
                    task_id, plan_path=None, receipt_path=None):
    operation = {
        "tool": TOOL,
        "task_id": task_id,
        "action": plan["operation"],
        "amendment_id": plan["amendment_id"],
        "transaction_id": transaction_id,
        "plan_sha256": plan_sha,
        "prepare_receipt_id": prepare_receipt_id,
        "actor_role": "integrator",
        "transaction_sequence": transaction_sequence,
        "previous_transaction_commit_receipt":
            previous_transaction_commit_receipt,
        "plan_path": plan_path,
        "coverage_proposal_path": plan["coverage_proposal_path"],
        "coverage_proposal_sha256": plan["coverage_proposal_sha256"],
        "receipt_path": receipt_path,
    }
    for name in tuple(sorted(runtime_state_contract.RUNTIME_LEDGER_IDS)):
        operation["before_%s_sha256" % name] = before[name]
        operation["planned_after_%s_sha256" % name] = after[name]
    return operation


def _prepare_result(root, plan_path, expected, admitted_runtime=None):
    root = os.path.realpath(os.path.abspath(root))
    plan_file, plan_raw, plan = _load_managed(
        root, plan_path, amendment_plan.PLAN_PREFIX, must_exist=True)
    amendment_plan.validate_plan(plan)
    plan_relative = os.path.relpath(plan_file, root).replace(os.sep, "/")
    plan_sha = kblib.sha256_bytes(plan_raw)
    proposal_path = plan["coverage_proposal_path"]
    if os.path.normpath(proposal_path) == os.path.normpath(plan_path):
        raise ValueError("plan and Coverage proposal must be different files")
    proposal_file, proposal_raw, proposal = _load_managed(
        root, proposal_path, amendment_plan.PLAN_PREFIX, must_exist=True)
    proposal_sha = kblib.sha256_bytes(proposal_raw)
    if proposal_sha != plan["coverage_proposal_sha256"]:
        raise ValueError("Coverage proposal SHA does not match plan")

    current = (runtime_validation.validate_runtime(root)
               if admitted_runtime is None else admitted_runtime)
    if (not isinstance(current, dict) or
            current.get("root") != root):
        raise ValueError(
            "admitted runtime belongs to a different repository root")
    if current["errors"]:
        raise ValueError("current runtime is inconsistent: %s" %
                         "; ".join(current["errors"]))
    authority = queue_runtime.runtime_authority_context(current)
    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
    barrier = queue_runtime.delta_apply_write_barrier(
        current, TOOL, "apply")
    if barrier:
        raise ValueError(barrier)
    if current.get("_writer_locks"):
        raise ValueError("runtime has an active or interrupted writer lock")
    coverage = current["coverage"]
    queue = current["queue"]
    progress = current["progress"]
    state_paths = {
        "coverage": kblib.managed_repository_path(
            root, queue_runtime.COVERAGE_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True),
        "queue": current["queue_path"],
        "progress": kblib.managed_repository_path(
            root, queue_runtime.PROGRESS_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True),
    }
    before_raw = {}
    for name, path in state_paths.items():
        with open(path, "rb") as fh:
            before_raw[name] = fh.read()
    before_sha = {name: kblib.sha256_bytes(raw)
                  for name, raw in before_raw.items()}
    for name in tuple(sorted(runtime_state_contract.RUNTIME_LEDGER_IDS)):
        if expected[name] != before_sha[name]:
            raise ValueError("expected %s SHA does not match current bytes" % name)
    if (queue.get("scope_version") != plan["scope_version_before"] or
            queue.get("queue_revision") != plan["queue_revision_before"] or
            queue.get("state_revision") != plan["state_revision_before"]):
        raise ValueError("plan before scope/revisions do not match current Queue")
    amendment = _find_amendment(
        progress, plan, plan_path=plan_relative, plan_sha=plan_sha)
    current_pages, proposed_pages, changed_specs = \
        amendment_plan.validate_coverage_proposal(coverage, proposal, plan)
    impact = amendment_policy.derive_amendment_impact(
        coverage, proposal, queue)
    if impact["writer_operation"] != plan["operation"]:
        raise ValueError(
            "plan operation %s does not match derived writer operation %s" %
            (plan["operation"], impact["writer_operation"])
        )
    amendment_policy.require_decision_binding(
        progress.get("contract") or {}, impact, amendment)

    proposal_relative = os.path.relpath(proposal_file, root).replace(os.sep, "/")
    transaction_id = "txn-%s-%s" % (plan["amendment_id"], uuid.uuid4().hex)
    registration_receipt = amendment["registration_receipt"]
    transaction_sequence, previous_transaction_commit_receipt = \
        _transaction_chain_head(progress)
    prepare = _new_transaction_receipt(
        "prepare", "candidate", plan, transaction_id,
        plan_relative, plan_sha, proposal_relative, proposal_sha,
        transaction_sequence, previous_transaction_commit_receipt,
        queue.get("task_id"), registration_receipt)
    commit = _new_transaction_receipt(
        "commit", "pass", plan, transaction_id,
        plan_relative, plan_sha, proposal_relative, proposal_sha,
        transaction_sequence, previous_transaction_commit_receipt,
        queue.get("task_id"), registration_receipt)
    transition = None

    if plan["operation"] == "scope-replan":
        compile_base = copy.deepcopy(queue)
        compile_base["scope_version"] = plan["scope_version_after"]
        compiled, _ = compile_queue.compile_document(compile_base, proposal)
        diff = compile_queue.replan_diff(queue, compiled, before_sha["queue"])
        queue_new = queue_replan.build_replanned_queue(queue, compiled, diff)
        queue_new["scope_version"] = plan["scope_version_after"]
        queue_new["queue_revision"] = plan["queue_revision_after"]
        queue_new["state_revision"] = plan["state_revision_after"]
        changed_batches = sorted(set(changed_specs).union(
            amendment_plan.structural_changes(queue, compiled)))
        if changed_batches != plan["affected_batches"]:
            raise ValueError("affected_batches does not exactly match replan; "
                             "found=%r expected=%r" %
                             (changed_batches, plan["affected_batches"]))
    elif plan["operation"] == "gap-routing-reconciliation":
        compile_base = copy.deepcopy(queue)
        compiled, _ = compile_queue.compile_document(compile_base, proposal)
        changed_batches = amendment_plan.structural_changes(queue, compiled)
        if changed_batches:
            raise ValueError(
                "gap-routing-reconciliation may not change Queue structure: %s" %
                ", ".join(changed_batches))
        queue_new = copy.deepcopy(queue)
        queue_new["queue_revision"] = plan["queue_revision_after"]
        queue_new["state_revision"] = plan["state_revision_after"]
        if plan["affected_batches"] != impact["affected_batches"]:
            raise ValueError(
                "affected_batches does not match gap-routing impact; "
                "found=%r expected=%r" %
                (impact["affected_batches"], plan["affected_batches"]))
    else:
        if proposed_pages.keys() != current_pages.keys():
            raise ValueError("cancel-batch may not add or remove Coverage pages")
        if changed_specs != [plan["cancel_batch_id"]]:
            raise ValueError("cancel-batch must remove exactly its own current "
                             "batch_specs entry")
        current_specs = amendment_plan.records_by_id(
            coverage.get("batch_specs"), "id", "Coverage batch_specs")
        proposed_specs = amendment_plan.records_by_id(
            proposal.get("batch_specs"), "id", "Coverage proposal batch_specs")
        if (plan["cancel_batch_id"] not in current_specs or
                plan["cancel_batch_id"] in proposed_specs):
            raise ValueError("cancel-batch must retire cancel_batch_id from "
                             "the current batch_specs proposal")
        current_item = current["items_by_id"].get(plan["cancel_batch_id"])
        if current_item is None:
            raise ValueError("cancel_batch_id is absent from Queue")
        manifest = sorted(current_item.get("manifest") or [])
        if plan["affected_pages"] != manifest:
            raise ValueError("cancel-batch affected_pages must equal its manifest")
        for object_path in manifest:
            page = proposed_pages[object_path]
            if page.get("coverage_disposition") == "required":
                raise ValueError("cancelled object %s remains Required" % object_path)
            if page.get("next_batch") == plan["cancel_batch_id"]:
                raise ValueError("cancelled object %s still routes to the batch" %
                                 object_path)
        cancellation_time = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        transition = _new_queue_cancellation_receipt(
            plan, queue.get("task_id"), cancellation_time)
        queue_new, cancelled_item = amendment_plan.project_cancelled_queue(
            queue, plan, cancellation_time,
            transition,
        )
        transition.update({
            "checked_at": cancellation_time,
            "task_id": queue.get("task_id"),
            "queue_revision": queue_new.get("queue_revision"),
            "before_state": current_item.get("state"),
            "after_state": "cancelled",
            "before_hold_state": current_item.get("hold_state"),
            "after_hold_state": "none",
            "before_state_revision": queue.get("state_revision"),
            "after_state_revision": queue_new.get("state_revision"),
            "before_required_queue_sha256": before_sha["queue"],
            "actor_role": "integrator",
            "amendment_id": plan["amendment_id"],
        })

    queue_text = kblib.canonical_yaml(queue_new)
    if transition is not None:
        transition["after_required_queue_sha256"] = \
            kblib.sha256_bytes(queue_text)
    progress_new = _sync_progress(
        progress, plan, queue_new, queue_text, transaction_id,
        commit["receipt_id"], transaction_sequence,
        previous_transaction_commit_receipt,
        plan_relative, plan_sha, proposal_relative, proposal_sha,
    )
    coverage_text = kblib.canonical_yaml(proposal)
    progress_text = kblib.canonical_yaml(progress_new)
    after_text = {
        "coverage": coverage_text,
        "queue": queue_text,
        "progress": progress_text,
    }
    after_sha = {name: kblib.sha256_bytes(text)
                 for name, text in after_text.items()}
    before_contract = progress.get("contract") or {}
    after_contract = progress_new.get("contract") or {}
    contract_fields = {
        "before_contract_sha256": queue_runtime.contract_sha256(progress),
        "after_contract_sha256": queue_runtime.contract_sha256(progress_new),
        "before_contract_version": before_contract.get("contract_version"),
        "after_contract_version": after_contract.get("contract_version"),
        "before_contract_scope_version": before_contract.get("scope_version"),
        "after_contract_scope_version": after_contract.get("scope_version"),
    }
    for receipt in (prepare, commit):
        _transaction_fields(receipt, before_sha, after_sha)
        receipt.update(contract_fields)
        receipt["queue_revision_before"] = plan["queue_revision_before"]
        receipt["queue_revision_after"] = plan["queue_revision_after"]
        receipt["state_revision_before"] = plan["state_revision_before"]
        receipt["state_revision_after"] = plan["state_revision_after"]

    overrides = {
        queue_runtime.COVERAGE_PATH: (coverage_text, proposal),
        queue_runtime.QUEUE_PATH: (queue_text, queue_new),
        queue_runtime.PROGRESS_PATH: (progress_text, progress_new),
    }
    pending = [commit]
    if transition is not None:
        pending.append(transition)
    final_check = runtime_validation.validate_runtime(
        root, state_overrides=overrides, extra_receipts=pending,
        **authority_kwargs)
    if final_check["errors"]:
        raise ValueError("planned final state fails check_queue: %s" %
                         "; ".join(final_check["errors"]))
    return {
        "plan": plan, "plan_file": plan_file, "plan_path": plan_relative,
        "plan_sha": plan_sha, "proposal_file": proposal_file,
        "proposal_path": proposal_relative, "proposal_sha": proposal_sha,
        "paths": state_paths,
        "before_raw": before_raw, "before_sha": before_sha,
        "after_text": after_text, "after_sha": after_sha,
        "contract_fields": contract_fields,
        "prepare": prepare, "commit": commit, "transition": transition,
        "transaction_id": transaction_id,
        "transaction_sequence": transaction_sequence,
        "previous_transaction_commit_receipt":
            previous_transaction_commit_receipt,
        "registration_receipt": registration_receipt,
        "task_id": queue.get("task_id"),
        "impact": impact,
        "proposal": proposal,
        "authority": authority,
    }


def _restore(paths, before_raw):
    failures = []
    for name in runtime_state_contract.RUNTIME_LEDGER_IDS:
        try:
            text = before_raw[name].decode("utf-8")
            kblib.atomic_write_text(paths[name], text,
                                    validator=kblib.parse_yaml_subset)
        except Exception as exc:  # preserve every attempted rollback failure
            failures.append("%s: %s" % (name, exc))
    for name in runtime_state_contract.RUNTIME_LEDGER_IDS:
        try:
            with open(paths[name], "rb") as fh:
                live = fh.read()
            if live != before_raw[name]:
                failures.append("%s bytes differ after rollback" % name)
        except Exception as exc:
            failures.append("%s verification: %s" % (name, exc))
    return failures


def _commit_transaction(root, prepared, receipt_path):
    plan = prepared["plan"]
    authority = prepared["authority"]
    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
    abort = _new_transaction_receipt(
        "abort", "fail", plan, prepared["transaction_id"],
        prepared["plan_path"], prepared["plan_sha"],
        prepared["proposal_path"], prepared["proposal_sha"],
        prepared["transaction_sequence"],
        prepared["previous_transaction_commit_receipt"],
        prepared["task_id"], prepared["registration_receipt"],
    )
    _transaction_fields(abort, prepared["before_sha"], prepared["after_sha"])
    abort.update(prepared["contract_fields"])
    operation = _lock_operation(
        plan, prepared["transaction_id"], prepared["plan_sha"],
        prepared["before_sha"], prepared["after_sha"],
        prepared["prepare"]["receipt_id"],
        prepared["transaction_sequence"],
        prepared["previous_transaction_commit_receipt"],
        prepared["task_id"],
        plan_path=prepared["plan_path"],
        receipt_path=os.path.relpath(receipt_path, root),
    )
    operation["registration_receipt"] = prepared["registration_receipt"]
    operation.update({
        "commit_receipt_id": prepared["commit"]["receipt_id"],
        "abort_receipt_id": abort["receipt_id"],
        "transition_receipt_id": (
            prepared["transition"]["receipt_id"]
            if prepared["transition"] is not None else None
        ),
    })
    operation.update(queue_runtime.runtime_authority_lock_fields(authority))
    with kblib.runtime_write_lock(root, owner_metadata=operation) as lock:
        with kblib.no_authoritative_write_guard(lock):
            for name, path in prepared["paths"].items():
                with open(path, "rb") as fh:
                    live = fh.read()
                if kblib.sha256_bytes(live) != prepared["before_sha"][name]:
                    raise ValueError(
                        "%s changed after transaction planning" % name)
            locked = runtime_validation.validate_runtime(
                root, **authority_kwargs)
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            queue_runtime.require_runtime_authority_current(
                root, authority, "runtime authority changed under lock")
            barrier = queue_runtime.delta_apply_write_barrier(
                locked, TOOL, "apply")
            if barrier:
                raise ValueError(barrier)
            if kblib.sha256_file(prepared["plan_file"]) != prepared["plan_sha"]:
                raise ValueError("Amendment plan changed after transaction planning")
            if kblib.sha256_file(
                    prepared["proposal_file"]) != prepared["proposal_sha"]:
                raise ValueError(
                    "Coverage proposal changed after transaction planning")
            locked_amendment = _find_amendment(
                locked["progress"], prepared["plan"],
                plan_path=prepared["plan_path"],
                plan_sha=prepared["plan_sha"])
            locked_impact = amendment_policy.derive_amendment_impact(
                locked["coverage"], prepared["proposal"], locked["queue"])
            amendment_policy.require_decision_binding(
                locked["progress"].get("contract") or {},
                locked_impact, locked_amendment)
        final_receipts = ([prepared["transition"]]
                          if prepared["transition"] else []) + [
                              prepared["commit"]]
        outcomes = {
            "prepare": "not-attempted",
            "final": "not-attempted",
            "commit": "not-attempted",
            "abort": "not-attempted",
        }
        try:
            commit_before = kblib.receipt_append_observation(
                receipt_path, [prepared["commit"]]
            )
            final_before = kblib.receipt_append_observation(
                receipt_path, final_receipts
            )
        except Exception:
            commit_before = None
            final_before = None
        try:
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before prepare receipt")
            outcome, append_error, _ = kblib.write_receipts_observed(
                receipt_path, _JSON_REPORTER.record([prepared["prepare"]])
            )
            outcomes["prepare"] = outcome
            if append_error is not None:
                raise append_error
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during prepare receipt")
            for name in runtime_state_contract.RUNTIME_LEDGER_IDS:
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before %s write" % name)
                kblib.atomic_write_text(
                    prepared["paths"][name], prepared["after_text"][name],
                    validator=kblib.parse_yaml_subset,
                )
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during %s write" % name)
            post = runtime_validation.validate_runtime(
                root,
                extra_receipts=(
                    [prepared["commit"], prepared["transition"]]
                    if prepared["transition"] else [prepared["commit"]]),
                **authority_kwargs,
            )
            if post["errors"]:
                raise ValueError("post-write check_queue failed: %s" %
                                 "; ".join(post["errors"]))
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before final receipts")
            outcome, append_error, _ = kblib.write_receipts_observed(
                receipt_path, _JSON_REPORTER.record(final_receipts),
                before=final_before
            )
            outcomes["final"] = outcome
            outcomes["commit"] = (
                kblib.receipt_outcome_from(
                    receipt_path, [prepared["commit"]], commit_before
                ) if commit_before is not None else "uncertain"
            )
            if append_error is not None:
                raise append_error
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during final receipts")
            persisted = runtime_validation.validate_runtime(
                root, **authority_kwargs)
            if persisted["errors"]:
                raise ValueError("persisted transaction evidence failed "
                                 "check_queue: %s" %
                                 "; ".join(persisted["errors"]))
        except Exception as exc:
            rollback_failures = []
            rollback_failures.extend(_restore(
                prepared["paths"], prepared["before_raw"]))
            if outcomes["final"] == "not-attempted":
                outcomes["final"] = (
                    kblib.receipt_outcome_from(
                        receipt_path, final_receipts, final_before
                    ) if final_before is not None else "uncertain"
                )
            if outcomes["commit"] == "not-attempted":
                outcomes["commit"] = (
                    kblib.receipt_outcome_from(
                        receipt_path, [prepared["commit"]], commit_before
                    ) if commit_before is not None else "uncertain"
                )
            abort["failure"] = str(exc)
            abort["rollback_failures"] = rollback_failures
            abort_error = None
            if outcomes["prepare"] in ("present", "uncertain"):
                outcomes["abort"], abort_error, _ = (
                    kblib.write_receipts_observed(
                        receipt_path, _JSON_REPORTER.record([abort]))
                )
            attempted = [
                value for key, value in outcomes.items()
                if key != "commit" and value != "not-attempted"
            ]
            all_attempted_absent = (
                bool(attempted) and
                all(value == "absent" for value in attempted) and
                outcomes["commit"] == "absent"
            )
            handled_prepare_failure = (
                outcomes["prepare"] == "present" and
                outcomes["abort"] == "present" and
                outcomes["final"] == "absent" and
                outcomes["commit"] == "absent"
            )
            receipt_recovery_closed = (
                all_attempted_absent or handled_prepare_failure
            )
            if rollback_failures or not receipt_recovery_closed:
                recovery = (
                    "receipt outcomes prepare=%s final=%s commit=%s abort=%s" %
                    (outcomes["prepare"], outcomes["final"],
                     outcomes["commit"], outcomes["abort"])
                )
                if abort_error is not None:
                    recovery += "; abort append: %s" % abort_error
                suffix = (("; " + "; ".join(rollback_failures))
                          if rollback_failures else "")
                raise ValueError(
                    "transaction failed and recovery was incomplete: %s; %s%s" %
                    (exc, recovery, suffix))
            lock.mark_reconciled()
            raise


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Apply one approved cross-Ledger Amendment transaction")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--plan", required=True,
                        help="%s/*.yaml plan" %
                        runtime_paths.AMENDMENT_DELTA_ROOT)
    parser.add_argument("--expected-coverage-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Coverage; planning is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-progress-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Progress; planning is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-queue-sha256", required=True,
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Queue; planning is "
                             "refused when the live bytes differ")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may "
                             "apply an Amendment transaction")
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--apply", action="store_true",
                        help="write the transaction; omit for a dry run")
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _JSON_REPORTER.run(lambda: _run(args))


def _run(args):
    """This tool's own run; `main` above owns only argument parsing."""
    root = os.path.realpath(os.path.abspath(args.root))
    expected = {
        "coverage": args.expected_coverage_sha256,
        "progress": args.expected_progress_sha256,
        "queue": args.expected_queue_sha256,
    }
    for name, value in expected.items():
        if not queue_runtime.SHA256_RE.fullmatch(value):
            print("[FAIL] expected %s SHA must be sha256:<64 lowercase hex>" % name)
            return 1
    admission = None
    if args.apply:
        strict_admission = runtime_validation.validate_runtime(root)
        if not strict_admission["errors"]:
            # Preserve the ordinary writer invariant: a healthy runtime must
            # pass the global applied-delta barrier before this command opens
            # or interprets an Amendment plan.
            barrier = queue_runtime.delta_apply_write_barrier(
                strict_admission, TOOL, "apply")
            if barrier:
                print("[FAIL] %s" % barrier)
                return 1
            admission = strict_admission
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
        prepared = _prepare_result(
            root, args.plan, expected,
            admitted_runtime=admission)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1
    print("amendment transaction: %s operation=%s scope=%s->%s "
          "queue_revision=%s->%s state_revision=%s->%s" % (
              prepared["plan"]["amendment_id"],
              prepared["plan"]["operation"],
              prepared["plan"]["scope_version_before"],
              prepared["plan"]["scope_version_after"],
              prepared["plan"]["queue_revision_before"],
              prepared["plan"]["queue_revision_after"],
              prepared["plan"]["state_revision_before"],
              prepared["plan"]["state_revision_after"],
          ))
    for name in runtime_state_contract.RUNTIME_LEDGER_IDS:
        print("%s_sha256=%s -> %s" % (
            name, prepared["before_sha"][name], prepared["after_sha"][name]))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with the same expected SHAs")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply an Amendment transaction")
        return 1
    try:
        _commit_transaction(root, prepared, receipt_path)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] Amendment transaction: %s" % exc)
        return 1
    print("[PASS] Amendment %s committed; transaction_id=%s" % (
        prepared["plan"]["amendment_id"], prepared["transaction_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
