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
"""

import argparse
import copy
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_amendment
import check_queue
import compile_queue
import kblib


TOOL = "register_amendment"
TOOL_VERSION = "1.0.0"
RECEIPT_PATH = ".cambium/receipts/amendments.jsonl"
OPERATIONS = ("scope-replan", "cancel-batch", "queue-replan")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _load_yaml(root, relative, prefix, suffixes):
    path = kblib.managed_repository_path(
        root, relative, prefix, suffixes=suffixes, must_exist=True,
    )
    if not os.path.isfile(path):
        raise ValueError("managed YAML path is not a regular file: %s" % relative)
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        value = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("%s is not UTF-8: %s" % (relative, exc))
    if not isinstance(value, dict):
        raise ValueError("%s top level must be a mapping" % relative)
    normalized = os.path.relpath(path, root).replace(os.sep, "/")
    return path, normalized, raw, value


def _state_paths(root, runtime):
    return {
        "coverage": kblib.managed_repository_path(
            root, check_queue.COVERAGE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        ),
        "queue": kblib.managed_repository_path(
            root, check_queue.QUEUE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        ),
        "progress": kblib.managed_repository_path(
            root, check_queue.PROGRESS_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        ),
    }


def _read_state(paths):
    raw = {}
    for name, path in paths.items():
        with open(path, "rb") as fh:
            raw[name] = fh.read()
    return raw, {name: kblib.sha256_bytes(value)
                 for name, value in raw.items()}


def _require_current_schema(runtime):
    for label in ("coverage", "queue", "progress"):
        value = runtime.get(label)
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError(
                "%s must use the current schema_version 1" % label.title()
            )


def _check_control_identity(runtime):
    coverage = runtime["coverage"]
    queue = runtime["queue"]
    progress = runtime["progress"]
    contract = progress.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("Progress contract must be a mapping")
    for field in ("task_id", "scope_version", "standards_version",
                  "selected_profile_manifest"):
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
        root, plan_relative, apply_amendment.PLAN_PREFIX,
        (".yaml", ".yml"),
    )
    apply_amendment._validate_plan(plan)
    if plan.get("operation") != operation:
        raise ValueError("--operation does not match the Amendment plan")
    proposal_relative = plan["coverage_proposal_path"]
    if os.path.normpath(proposal_relative) == os.path.normpath(plan_path):
        raise ValueError("plan and Coverage proposal must be different files")
    proposal_file, proposal_path, proposal_raw, proposal = _load_yaml(
        root, proposal_relative, apply_amendment.PLAN_PREFIX,
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
        apply_amendment._validate_coverage_proposal(coverage, proposal, plan)

    if operation == "scope-replan":
        compile_base = copy.deepcopy(queue)
        compile_base["scope_version"] = plan["scope_version_after"]
        compiled, _ = compile_queue.compile_document(compile_base, proposal)
        diff = compile_queue.replan_diff(
            queue, compiled, kblib.sha256_file(runtime["queue_path"])
        )
        compile_queue._build_replanned_queue(queue, compiled, diff)
        changed_batches = sorted(set(changed_specs).union(
            apply_amendment._structural_changes(queue, compiled)
        ))
        if changed_batches != plan["affected_batches"]:
            raise ValueError(
                "affected_batches does not exactly match replan; "
                "found=%r expected=%r" %
                (changed_batches, plan["affected_batches"])
            )
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
        apply_amendment._cancel_queue(
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
            "prefix": apply_amendment.PLAN_PREFIX,
            "suffixes": (".yaml", ".yml"),
            "sha256": record["plan_sha256"],
            "resolved_path": plan_file,
        },
        {
            "relative": proposal_path,
            "prefix": apply_amendment.PLAN_PREFIX,
            "suffixes": (".yaml", ".yml"),
            "sha256": proposal_sha,
            "resolved_path": proposal_file,
        },
    ]
    return record, bindings, artifacts


def _validate_queue_replan(root, runtime, amendment_id, proposal_relative):
    if not _nonempty(amendment_id):
        raise ValueError("queue-replan requires --amendment-id")
    proposal_file, proposal_path, proposal_raw, proposal = _load_yaml(
        root, proposal_relative, ".cambium/deltas/replans",
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
        raise ValueError("queue-replan proposal has no structural changes")
    if diff.get("remove_candidates") or diff.get("conflicts"):
        raise ValueError("queue-replan proposal is not safely applicable: %s" %
                         "; ".join(str(value) for value in
                                   (diff.get("conflicts") or [])))
    # This pure construction is the same final structural admissibility check
    # used by compile_queue --apply-replan.
    compile_queue._build_replanned_queue(queue, compiled, diff)
    diff_text = kblib.canonical_yaml(diff)
    affected_batches = compile_queue._changed_batch_ids(diff)
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
        "prefix": ".cambium/deltas/replans",
        "suffixes": (".coverage.yaml",),
        "sha256": proposal_sha,
        "resolved_path": proposal_file,
    }]
    return record, bindings, artifacts


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
    runtime = check_queue.validate_runtime(root)
    if runtime["errors"]:
        raise ValueError("current runtime is inconsistent: %s" %
                         "; ".join(runtime["errors"]))
    if runtime.get("writer_locks"):
        raise ValueError("runtime has an active or interrupted writer lock")
    task_state = (runtime.get("progress") or {}).get("task_state")
    if task_state in ("completion-candidate", "complete", "cancelled"):
        raise ValueError(
            "task_state=%s forbids operational Amendment registration" %
            task_state
        )
    barrier = check_queue.delta_apply_write_barrier(
        runtime, TOOL, "register-amendment")
    if barrier:
        raise ValueError(barrier)
    _require_current_schema(runtime)
    _check_control_identity(runtime)
    paths = _state_paths(root, runtime)
    before_raw, before_sha = _read_state(paths)
    for name in ("coverage", "progress", "queue"):
        if expected[name] != before_sha[name]:
            raise ValueError("expected %s SHA does not match current bytes" % name)

    if args.operation in ("scope-replan", "cancel-batch"):
        if not args.plan:
            raise ValueError("%s requires --plan" % args.operation)
        if args.amendment_id or args.coverage_proposal:
            raise ValueError("cross-Ledger registration derives id/proposal from --plan")
        record, bindings, artifacts = _validate_cross_plan(
            root, runtime, args.operation, args.plan
        )
    else:
        if args.plan:
            raise ValueError("queue-replan does not consume --plan")
        if not args.coverage_proposal:
            raise ValueError("queue-replan requires --coverage-proposal")
        record, bindings, artifacts = _validate_queue_replan(
            root, runtime, args.amendment_id, args.coverage_proposal
        )

    progress = runtime["progress"]
    _check_no_pending_or_duplicate(progress, record["id"])
    record.update({
        "date": args.date,
        "summary": args.summary,
        "approval_reference": args.approval_reference,
        "status": "approved",
        "writeback_done": False,
    })
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "amendment_registration", record["id"], "pass",
        "registered approved %s Amendment" % args.operation, 1,
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
        "approval_reference": args.approval_reference,
        "summary": args.summary,
        "contract_sha256": check_queue._contract_sha256(progress),
    })
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

    planned = check_queue.validate_runtime(
        root,
        state_overrides={
            check_queue.PROGRESS_PATH: (progress_text, progress_new),
        },
        extra_receipts=[receipt],
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
    operation = {
        "tool": TOOL,
        "action": "register",
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
    operation["before_required_queue_sha256"] = prepared["before_sha"]["queue"]
    operation["planned_after_required_queue_sha256"] = \
        prepared["after_sha"]["queue"]

    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        with kblib.no_authoritative_write_guard(lease):
            _, locked_sha = _read_state(prepared["paths"])
            if locked_sha != prepared["before_sha"]:
                raise ValueError("canonical state changed after registration planning")
            locked = check_queue.validate_runtime(root)
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            _require_current_schema(locked)
            _revalidate_artifacts(root, prepared["artifacts"])

        receipt_before = kblib.receipt_append_observation(
            receipt_path, [prepared["receipt"]]
        )
        try:
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, [prepared["receipt"]], before=receipt_before,
            )
            if error is not None or outcome != "present":
                raise error or OSError(
                    "registration receipt append outcome was %s" % outcome
                )
            # The receipt is published first.  By itself it is an unreferenced
            # historical record and cannot authorize execution; authority
            # exists only after the pending Progress row names this exact ID.
            kblib.atomic_write_text(
                prepared["paths"]["progress"], prepared["progress_text"],
                validator=kblib.parse_yaml_subset,
            )
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
        persisted = check_queue.validate_runtime(root)
        if persisted["errors"]:
            raise ValueError("persisted registration fails check_queue: %s" %
                             "; ".join(persisted["errors"]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Register one approved current-protocol Amendment"
    )
    parser.add_argument("root")
    parser.add_argument("--operation", required=True, choices=OPERATIONS)
    parser.add_argument("--plan",
                        help=".cambium/deltas/amendments/*.yaml plan")
    parser.add_argument("--amendment-id")
    parser.add_argument("--coverage-proposal",
                        help=".cambium/deltas/replans/*.coverage.yaml proposal")
    parser.add_argument("--date", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--expected-coverage-sha256", required=True)
    parser.add_argument("--expected-progress-sha256", required=True)
    parser.add_argument("--expected-queue-sha256", required=True)
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker")
    parser.add_argument("--receipts", default=RECEIPT_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not DATE_RE.fullmatch(args.date):
        print("[FAIL] --date must use YYYY-MM-DD")
        return 1
    for label, value in (("summary", args.summary),
                         ("approval-reference", args.approval_reference)):
        if not _nonempty(value):
            print("[FAIL] --%s must be a non-empty string" % label)
            return 1
    expected = {
        "coverage": args.expected_coverage_sha256,
        "progress": args.expected_progress_sha256,
        "queue": args.expected_queue_sha256,
    }
    for name, value in expected.items():
        if not check_queue.SHA256_RE.fullmatch(str(value)):
            print("[FAIL] expected %s SHA must be sha256:<64 lowercase hex>" %
                  name)
            return 1
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False,
        )
        prepared = _prepare(root, args, expected)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1

    print("Amendment registration: %s operation=%s" %
          (prepared["record"]["id"], args.operation))
    for name in ("coverage", "queue", "progress"):
        print("%s_sha256=%s -> %s" %
              (name, prepared["before_sha"][name],
               prepared["after_sha"][name]))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with the same expected SHAs")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may register an Amendment")
        return 1
    try:
        _apply(root, prepared, receipt_path)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] Amendment registration: %s" % exc)
        return 1
    print("[PASS] Amendment %s registered; receipt=%s" %
          (prepared["record"]["id"],
           prepared["receipt"]["receipt_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
