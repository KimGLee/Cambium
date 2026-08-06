#!/usr/bin/env python3
"""Atomically adopt an approved Standards/Profile identity for an active task.

The restricted-YAML plan is the canonical machine revision record.  The
default is a dry run.  ``--apply --actor-role integrator`` is the only write
path; it holds the shared runtime writer lock, appends prepare/commit/abort
evidence, preserves unrelated state exactly, and rolls ordinary failures back
to the three frozen before images.
"""

import argparse
import copy
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib

TOOL = "adopt_standards"
TOOL_VERSION = "1.1.0"
GATE_ID = "standards-adoption"
PLAN_PREFIX = check_queue.STANDARDS_ADOPTION_PLAN_PREFIX
RECEIPT_PATH = ".cambium/receipts/standards-adoptions.jsonl"
ALLOWED_TASK_STATES = frozenset(("active", "paused"))
LOAD_FIELDS = (
    "selected_route_ids", "selected_card_paths",
    "selected_profile_route_ids", "selected_read_sets",
    "loaded_module_paths",
)


def _make_receipt(check, target, result, details, seq, identity=None):
    """Build one producer-era adoption receipt with its stable Gate ID.

    Adoption receipts are built before the state write and consumed after it,
    so the identity they bind is the planned post-adoption Queue identity
    (:func:`_plan_identity`), never the bytes currently on disk.
    """
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, check, target, result, details, seq,
        identity=identity)
    receipt["gate_id"] = GATE_ID
    return receipt


def _plan_identity(plan):
    """Return the Required Queue identity this adoption leaves behind."""
    return {
        "task_id": plan["task_id"],
        "standards_version": plan["standards_version_after"],
        "selected_profile_manifest":
            plan["selected_profile_manifest_after"],
    }


def _load_plan(root, relative):
    path = kblib.managed_repository_path(
        root, relative, PLAN_PREFIX, suffixes=(".yaml",), must_exist=True)
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        plan = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("adoption plan is not UTF-8: %s" % exc)
    if not isinstance(plan, dict):
        raise ValueError("adoption plan top level must be a mapping")
    return path, raw, plan


def _state_paths(root, current):
    return {
        "coverage": kblib.managed_repository_path(
            root, check_queue.COVERAGE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
        "queue": current["queue_path"],
        "progress": kblib.managed_repository_path(
            root, check_queue.PROGRESS_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
    }


def _read_state_bytes(paths):
    result = {}
    for name, path in paths.items():
        with open(path, "rb") as fh:
            result[name] = fh.read()
    return result


def _ids(rows, field):
    return sorted(row[field] for row in rows)


def _non_adoption_projection(name, document):
    """Remove only the fields this writer is authorized to change."""
    value = copy.deepcopy(document)
    if name == "coverage":
        value.pop("standards_version", None)
        value.pop("selected_profile_manifest", None)
    elif name == "queue":
        value.pop("standards_version", None)
        value.pop("selected_profile_manifest", None)
        value.pop("queue_revision", None)
    elif name == "progress":
        value.pop("standards_adoptions", None)
        value.pop("queue_revision", None)
        value.pop("required_queue_sha256", None)
        contract = value.get("contract")
        if isinstance(contract, dict):
            for field in (
                    "contract_version", "standards_version",
                    "selected_profile_manifest") + LOAD_FIELDS:
                contract.pop(field, None)
    return value


def _projection_sha(name, document):
    return kblib.sha256_bytes(kblib.canonical_yaml(
        _non_adoption_projection(name, document)))


def _assert_only_permitted_changes(before, after):
    for name in ("coverage", "queue", "progress"):
        if _non_adoption_projection(name, before[name]) != \
                _non_adoption_projection(name, after[name]):
            raise ValueError(
                "planned adoption changes forbidden %s fields" % name)
    if before["queue"].get("state_revision") != after["queue"].get(
            "state_revision"):
        raise ValueError("Standards adoption may not change state_revision")
    before_items = before["queue"].get("required_queue")
    after_items = after["queue"].get("required_queue")
    if before_items != after_items:
        raise ValueError("Standards adoption may not change Queue items")
    if before["progress"].get("task_state") != after["progress"].get(
            "task_state"):
        raise ValueError("Standards adoption may not change task_state")


def _new_receipt(phase, result, plan, transaction_id, plan_path, plan_sha,
                 before, after, before_sha, after_sha, projection_shas,
                 immediate_receipts):
    receipt = _make_receipt(
        "standards_adoption", plan["adoption_id"],
        result,
        "%s Standards adoption %s -> %s" % (
            phase, plan["standards_version_before"],
            plan["standards_version_after"]),
        {"prepare": 1, "commit": 2, "abort": 3}[phase],
        identity=_plan_identity(plan),
    )
    before_contract = before["progress"]["contract"]
    after_contract = after["progress"]["contract"]
    receipt.update({
        "transaction_phase": phase,
        "transaction_id": transaction_id,
        "actor_role": "integrator",
        "task_id": plan["task_id"],
        "adoption_id": plan["adoption_id"],
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "before_coverage_sha256": before_sha["coverage"],
        "before_queue_sha256": before_sha["queue"],
        "before_progress_sha256": before_sha["progress"],
        "after_coverage_sha256": after_sha["coverage"],
        "after_queue_sha256": after_sha["queue"],
        "after_progress_sha256": after_sha["progress"],
        "before_contract_sha256": check_queue._contract_sha256(
            before["progress"]),
        "after_contract_sha256": check_queue._contract_sha256(
            after["progress"]),
        "before_contract_version": before_contract.get("contract_version"),
        "after_contract_version": after_contract.get("contract_version"),
        "before_contract_scope_version": before_contract.get("scope_version"),
        "after_contract_scope_version": after_contract.get("scope_version"),
        "contract_version_before": plan["contract_version_before"],
        "contract_version_after": plan["contract_version_after"],
        "standards_version_before": plan["standards_version_before"],
        "standards_version_after": plan["standards_version_after"],
        "selected_profile_manifest_before":
            plan["selected_profile_manifest_before"],
        "selected_profile_manifest_after":
            plan["selected_profile_manifest_after"],
        "governance_revision_ref": plan["governance_revision_ref"],
        "governance_revision_sha256": plan["governance_revision_sha256"],
        "standards_snapshot_sha256_after":
            plan["standards_snapshot_sha256_after"],
        "profile_snapshot_sha256_after":
            plan["profile_snapshot_sha256_after"],
        "queue_revision_before": plan["queue_revision_before"],
        "queue_revision_after": plan["queue_revision_after"],
        "state_revision_before": plan["queue_state_revision_before"],
        "state_revision_after": plan["queue_state_revision_before"],
        "task_state_before": plan["task_state_before"],
        "task_state_after": plan["task_state_before"],
        "selected_route_ids_before": before_contract["selected_route_ids"],
        "selected_route_ids_after": plan["selected_route_ids_after"],
        "selected_card_paths_before": before_contract["selected_card_paths"],
        "selected_card_paths_after": plan["selected_card_paths_after"],
        "selected_profile_route_ids_before":
            before_contract["selected_profile_route_ids"],
        "selected_profile_route_ids_after":
            plan["selected_profile_route_ids_after"],
        "selected_read_sets_before": before_contract["selected_read_sets"],
        "selected_read_sets_after": plan["selected_read_sets_after"],
        "loaded_module_paths_before": before_contract["loaded_module_paths"],
        "loaded_module_paths_after": plan["loaded_module_paths_after"],
        "changed_predicate_ids": _ids(
            plan["changed_predicates"], "predicate_id"),
        "invalidated_evidence_receipt_ids": _ids(
            plan["invalidated_evidence"], "receipt_id"),
        "invalidation_boundary_ids": _ids(
            plan["invalidation_boundaries"], "boundary_id"),
        "immediate_gate_reruns": plan["immediate_gate_reruns"],
        "immediate_gate_receipts": immediate_receipts,
        "boundary_gate_reruns": plan["boundary_gate_reruns"],
        "preserved_coverage_projection_sha256": projection_shas["coverage"],
        "preserved_queue_projection_sha256": projection_shas["queue"],
        "preserved_progress_projection_sha256": projection_shas["progress"],
    })
    return receipt


def _prepare_result(root, plan_relative):
    root = os.path.realpath(os.path.abspath(root))
    plan_file, plan_raw, plan = _load_plan(root, plan_relative)
    current = check_queue.validate_runtime(root)
    if current["errors"]:
        raise ValueError("current runtime is inconsistent: %s" %
                         "; ".join(current["errors"]))
    if current.get("writer_locks"):
        raise ValueError("runtime has an active or interrupted writer lock")
    barrier = check_queue.delta_apply_write_barrier(
        current, TOOL, "apply")
    if barrier:
        raise ValueError(barrier)
    queue = current["queue"]
    coverage = current["coverage"]
    progress = current["progress"]
    if progress.get("task_state") not in ALLOWED_TASK_STATES:
        raise ValueError("Standards adoption requires task_state active or paused")
    catalog = current.get("receipt_catalog") or {}
    plan_errors = check_queue.standards_adoption_plan_errors(
        root, plan, catalog=catalog, queue=queue, progress=progress,
        validate_current=True)
    if plan_errors:
        raise ValueError("invalid Standards adoption plan: %s" %
                         "; ".join(plan_errors))

    paths = _state_paths(root, current)
    before_raw = _read_state_bytes(paths)
    before_sha = {name: kblib.sha256_bytes(raw)
                  for name, raw in before_raw.items()}
    expected_sha = {
        "coverage": plan["coverage_sha256_before"],
        "queue": plan["required_queue_sha256_before"],
        "progress": plan["progress_sha256_before"],
    }
    for name in ("coverage", "queue", "progress"):
        if before_sha[name] != expected_sha[name]:
            raise ValueError("plan %s SHA does not match current bytes" % name)
    contract = progress["contract"]
    expected_identity = {
        "task_id": plan["task_id"],
        "task_state": plan["task_state_before"],
        "standards_version": plan["standards_version_before"],
        "selected_profile_manifest":
            plan["selected_profile_manifest_before"],
        "contract_version": plan["contract_version_before"],
        "queue_revision": plan["queue_revision_before"],
        "state_revision": plan["queue_state_revision_before"],
    }
    actual_identity = {
        "task_id": queue.get("task_id"),
        "task_state": progress.get("task_state"),
        "standards_version": queue.get("standards_version"),
        "selected_profile_manifest": queue.get("selected_profile_manifest"),
        "contract_version": contract.get("contract_version"),
        "queue_revision": queue.get("queue_revision"),
        "state_revision": queue.get("state_revision"),
    }
    for field, expected in expected_identity.items():
        if actual_identity[field] != expected:
            raise ValueError("plan before %s=%r, current value is %r" %
                             (field, expected, actual_identity[field]))
    existing = progress.get("standards_adoptions")
    if not isinstance(existing, list):
        raise ValueError("Progress standards_adoptions is malformed")
    if any(isinstance(record, dict) and
           record.get("id") == plan["adoption_id"] for record in existing):
        raise ValueError("adoption_id already exists in Progress")

    before = {
        "coverage": copy.deepcopy(coverage),
        "queue": copy.deepcopy(queue),
        "progress": copy.deepcopy(progress),
    }
    after = copy.deepcopy(before)
    after["coverage"]["standards_version"] = plan["standards_version_after"]
    after["coverage"]["selected_profile_manifest"] = \
        plan["selected_profile_manifest_after"]
    after["queue"]["standards_version"] = plan["standards_version_after"]
    after["queue"]["selected_profile_manifest"] = \
        plan["selected_profile_manifest_after"]
    after["queue"]["queue_revision"] = plan["queue_revision_after"]
    after_contract = after["progress"]["contract"]
    after_contract["contract_version"] = plan["contract_version_after"]
    after_contract["standards_version"] = plan["standards_version_after"]
    after_contract["selected_profile_manifest"] = \
        plan["selected_profile_manifest_after"]
    for field in LOAD_FIELDS:
        after_contract[field] = copy.deepcopy(plan[field + "_after"])
    after["progress"]["queue_revision"] = plan["queue_revision_after"]

    coverage_text = kblib.canonical_yaml(after["coverage"])
    queue_text = kblib.canonical_yaml(after["queue"])
    after_coverage_sha = kblib.sha256_bytes(coverage_text)
    after_queue_sha = kblib.sha256_bytes(queue_text)
    after["progress"]["required_queue_sha256"] = after_queue_sha

    plan_path = os.path.relpath(plan_file, root).replace(os.sep, "/")
    plan_sha = kblib.sha256_bytes(plan_raw)
    transaction_id = "txn-%s-%s" % (plan["adoption_id"], uuid.uuid4().hex)
    gate_stub = kblib.make_receipt(
        check_queue.TOOL, check_queue.TOOL_VERSION, "required_queue",
        check_queue.QUEUE_PATH, "pass",
        "post-adoption required Queue consistency", 90)
    immediate_receipts = [gate_stub["receipt_id"]]
    # Commit id/time are known before serializing Progress, avoiding a
    # self-referential after-Progress hash while retaining an exact reference.
    commit_stub = _make_receipt(
        "standards_adoption", plan["adoption_id"],
        "pass", "Standards adoption commit", 2,
        identity=_plan_identity(plan))
    record = {
        "id": plan["adoption_id"],
        "adopted_at": commit_stub["checked_at"],
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "verification_receipt": commit_stub["receipt_id"],
        "transaction_id": transaction_id,
        "task_state_before": plan["task_state_before"],
        "contract_version_before": plan["contract_version_before"],
        "contract_version_after": plan["contract_version_after"],
        "standards_version_before": plan["standards_version_before"],
        "standards_version_after": plan["standards_version_after"],
        "selected_profile_manifest_before":
            plan["selected_profile_manifest_before"],
        "selected_profile_manifest_after":
            plan["selected_profile_manifest_after"],
        "governance_revision_ref": plan["governance_revision_ref"],
        "governance_revision_sha256": plan["governance_revision_sha256"],
        "standards_snapshot_sha256_after":
            plan["standards_snapshot_sha256_after"],
        "profile_snapshot_sha256_after":
            plan["profile_snapshot_sha256_after"],
        "selected_route_ids_after": plan["selected_route_ids_after"],
        "selected_card_paths_after": plan["selected_card_paths_after"],
        "selected_profile_route_ids_after":
            plan["selected_profile_route_ids_after"],
        "selected_read_sets_after": plan["selected_read_sets_after"],
        "loaded_module_paths_after": plan["loaded_module_paths_after"],
        "queue_revision_before": plan["queue_revision_before"],
        "queue_revision_after": plan["queue_revision_after"],
        "queue_state_revision_before": plan["queue_state_revision_before"],
        "coverage_sha256_before": before_sha["coverage"],
        "required_queue_sha256_before": before_sha["queue"],
        "progress_sha256_before": before_sha["progress"],
        "after_coverage_sha256": after_coverage_sha,
        "after_required_queue_sha256": after_queue_sha,
        "changed_predicate_ids": _ids(
            plan["changed_predicates"], "predicate_id"),
        "invalidated_evidence_receipt_ids": _ids(
            plan["invalidated_evidence"], "receipt_id"),
        "invalidation_boundary_ids": _ids(
            plan["invalidation_boundaries"], "boundary_id"),
        "immediate_gate_reruns": plan["immediate_gate_reruns"],
        "immediate_gate_receipts": immediate_receipts,
        "boundary_gate_reruns": plan["boundary_gate_reruns"],
    }
    after["progress"]["standards_adoptions"] = copy.deepcopy(existing) + [record]
    progress_text = kblib.canonical_yaml(after["progress"])
    after_text = {
        "coverage": coverage_text,
        "queue": queue_text,
        "progress": progress_text,
    }
    after_sha = {name: kblib.sha256_bytes(text)
                 for name, text in after_text.items()}
    _assert_only_permitted_changes(before, after)
    projection_shas = {name: _projection_sha(name, before[name])
                       for name in before}

    prepare = _new_receipt(
        "prepare", "candidate", plan, transaction_id, plan_path, plan_sha,
        before, after, before_sha, after_sha, projection_shas,
        immediate_receipts)
    commit = _new_receipt(
        "commit", "pass", plan, transaction_id, plan_path, plan_sha,
        before, after, before_sha, after_sha, projection_shas,
        immediate_receipts)
    # Preserve the already embedded commit identity/time.
    commit["receipt_id"] = commit_stub["receipt_id"]
    commit["checked_at"] = commit_stub["checked_at"]

    synthetic = {
        "root": root,
        "queue": after["queue"],
        "coverage": after["coverage"],
        "progress": after["progress"],
        "queue_sha256": after_sha["queue"],
        "coverage_sha256": after_sha["coverage"],
        "progress_sha256": after_sha["progress"],
        "remaining": sum(
            1 for item in after["queue"].get("required_queue", [])
            if not isinstance(item, dict) or
            item.get("state") not in check_queue.TERMINAL_STATES),
    }
    gate = check_queue.make_check_receipt(
        synthetic, "pass", "post-adoption Queue consistency passed",
        "consistency")
    gate["receipt_id"] = gate_stub["receipt_id"]
    gate["checked_at"] = gate_stub["checked_at"]

    overrides = {
        check_queue.COVERAGE_PATH: (coverage_text, after["coverage"]),
        check_queue.QUEUE_PATH: (queue_text, after["queue"]),
        check_queue.PROGRESS_PATH: (progress_text, after["progress"]),
    }
    final = check_queue.validate_runtime(
        root, state_overrides=overrides, extra_receipts=[gate, commit])
    if final["errors"]:
        raise ValueError("planned final state fails check_queue: %s" %
                         "; ".join(final["errors"]))
    return {
        "root": root, "plan": plan, "plan_path": plan_path,
        "plan_sha": plan_sha, "paths": paths, "before": before,
        "after": after, "before_raw": before_raw, "before_sha": before_sha,
        "after_text": after_text, "after_sha": after_sha,
        "prepare": prepare, "commit": commit, "gate": gate,
        "transaction_id": transaction_id,
        "projection_shas": projection_shas,
    }


def _restore(paths, before_raw):
    failures = []
    for name in ("coverage", "queue", "progress"):
        try:
            kblib.atomic_write_text(
                paths[name], before_raw[name].decode("utf-8"),
                validator=kblib.parse_yaml_subset)
        except Exception as exc:
            failures.append("%s: %s" % (name, exc))
    for name, path in paths.items():
        try:
            with open(path, "rb") as fh:
                if fh.read() != before_raw[name]:
                    failures.append("%s bytes differ after rollback" % name)
        except Exception as exc:
            failures.append("%s verification: %s" % (name, exc))
    return failures


def _lock_operation(prepared, receipt_path, abort_id):
    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "standards-adoption",
        "target": prepared["plan"]["adoption_id"],
        "task_id": prepared["plan"]["task_id"],
        "transaction_id": prepared["transaction_id"],
        "plan_path": prepared["plan_path"],
        "plan_sha256": prepared["plan_sha"],
        "receipt_path": os.path.relpath(
            receipt_path, prepared["root"]).replace(os.sep, "/"),
        "prepare_receipt_id": prepared["prepare"]["receipt_id"],
        "commit_receipt_id": prepared["commit"]["receipt_id"],
        "abort_receipt_id": abort_id,
        "immediate_gate_receipt_id": prepared["gate"]["receipt_id"],
        "before_coverage_sha256": prepared["before_sha"]["coverage"],
        "planned_after_coverage_sha256": prepared["after_sha"]["coverage"],
        "before_required_queue_sha256": prepared["before_sha"]["queue"],
        "planned_after_required_queue_sha256": prepared["after_sha"]["queue"],
        "before_progress_sha256": prepared["before_sha"]["progress"],
        "planned_after_progress_sha256": prepared["after_sha"]["progress"],
    }


def _commit_transaction(prepared, receipt_path):
    abort = copy.deepcopy(prepared["prepare"])
    abort.update(_make_receipt(
        "standards_adoption",
        prepared["plan"]["adoption_id"], "fail",
        "Standards adoption aborted and before state restored", 3,
        identity=_plan_identity(prepared["plan"])))
    abort["transaction_phase"] = "abort"
    abort["transaction_id"] = prepared["transaction_id"]
    operation = _lock_operation(prepared, receipt_path, abort["receipt_id"])
    with kblib.runtime_write_lock(
            prepared["root"], owner_metadata=operation) as lock:
        with kblib.no_authoritative_write_guard(lock):
            for name, path in prepared["paths"].items():
                with open(path, "rb") as fh:
                    live = fh.read()
                if kblib.sha256_bytes(live) != prepared["before_sha"][name]:
                    raise ValueError("%s changed after adoption planning" % name)
            locked = check_queue.validate_runtime(prepared["root"])
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            if locked.get("writer_locks") and len(locked["writer_locks"]) > 1:
                raise ValueError("another runtime writer lock appeared")

        prepare_before = kblib.receipt_append_observation(
            receipt_path, [prepared["prepare"]])
        final_receipts = [prepared["gate"], prepared["commit"]]
        prepare_outcome = "not-attempted"
        final_outcome = "not-attempted"
        commit_before = None
        try:
            prepare_outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, [prepared["prepare"]], before=prepare_before)
            if error is not None:
                raise error
            # The prepare record is an intentional append.  Observe the final
            # gate/commit baseline only after it is durable; otherwise the
            # later append would be compared with a stale file image and the
            # prepare line could be mistaken for an uncertain append.
            final_before = kblib.receipt_append_observation(
                receipt_path, final_receipts)
            commit_before = kblib.receipt_append_observation(
                receipt_path, [prepared["commit"]])
            for name in ("coverage", "queue", "progress"):
                kblib.atomic_write_text(
                    prepared["paths"][name], prepared["after_text"][name],
                    validator=kblib.parse_yaml_subset)
            post = check_queue.validate_runtime(
                prepared["root"], extra_receipts=final_receipts)
            if post["errors"]:
                raise ValueError("post-write check_queue failed: %s" %
                                 "; ".join(post["errors"]))
            # The gate was computed from these exact after bytes during
            # preparation and is consumed only after the locked revalidation.
            final_outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, final_receipts, before=final_before)
            if error is not None:
                raise error
        except Exception as exc:
            rollback_failures = _restore(
                prepared["paths"], prepared["before_raw"])
            commit_outcome = (
                kblib.receipt_outcome_from(
                    receipt_path, [prepared["commit"]], commit_before)
                if commit_before is not None else "absent"
            )
            abort["failure"] = str(exc)
            abort["rollback_failures"] = rollback_failures
            abort_outcome = "not-attempted"
            abort_error = None
            if prepare_outcome in ("present", "uncertain"):
                abort_outcome, abort_error, _ = kblib.write_receipts_observed(
                    receipt_path, [abort])
            fully_reconciled = (
                not rollback_failures and
                commit_outcome == "absent" and
                ((prepare_outcome == "absent") or
                 (prepare_outcome == "present" and
                  abort_outcome == "present"))
            )
            if fully_reconciled:
                lock.mark_reconciled()
                raise
            raise ValueError(
                "Standards adoption failed and recovery is incomplete: %s; "
                "prepare=%s final=%s commit=%s abort=%s abort_error=%s "
                "rollback=%s" % (
                    exc, prepare_outcome, final_outcome, commit_outcome,
                    abort_outcome, abort_error,
                    "; ".join(rollback_failures) or "none"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Adopt one approved Standards/Profile revision")
    parser.add_argument("root")
    parser.add_argument("--plan", required=True,
                        help=".cambium/deltas/standards-adoptions/*.yaml")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker")
    parser.add_argument("--receipts", default=RECEIPT_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
        prepared = _prepare_result(root, args.plan)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1
    plan = prepared["plan"]
    print("Standards adoption %s: %s -> %s; queue_revision %s -> %s" % (
        plan["adoption_id"], plan["standards_version_before"],
        plan["standards_version_after"], plan["queue_revision_before"],
        plan["queue_revision_after"]))
    for name in ("coverage", "queue", "progress"):
        print("%s_sha256=%s -> %s" % (
            name, prepared["before_sha"][name], prepared["after_sha"][name]))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with unchanged plan/state bytes")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply a Standards adoption")
        return 1
    try:
        _commit_transaction(prepared, receipt_path)
    except (OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] Standards adoption transaction: %s" % exc)
        return 1
    print("[PASS] Standards adoption %s committed; transaction_id=%s" % (
        plan["adoption_id"], prepared["transaction_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
