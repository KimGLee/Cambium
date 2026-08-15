#!/usr/bin/env python3
"""Amend the frozen Task Contract through one guarded transaction.

Once the Queue is materialized the Task Contract fingerprint is frozen, and
K13/06 until now offered exactly one disposition for a non-scope contract
change: pause or cancel the task and carry the change into a successor.  This
writer is the guarded alternative that clause called for.  It consumes one
operator-confirmed restricted-YAML plan, rewrites one or both allowlisted
contract fields, advances the Queue revision exactly once, and appends the
amendment row and commit receipt that let `check_queue`'s contract anchor
chain follow the change instead of failing closed on it.

The allowlist is deliberately small.  `policy_exceptions` is a bounded,
task-scoped current authorization, and `amendment_authority` is the closed
delegation for routine operational Amendment change classes.  Both live in
the contract -- not in the amendment log, whose rows are history
("historical registration evidence never authorizes", K13/06), and not in a
batch-close disposition, which speaks only for one snapshot.  Scope belongs
to the replan machinery; standards identity to K13/15; objective and
completion semantics to a successor task.
A field outside the allowlist is refused here and stays on the successor path.

There is no pending phase.  Like the Standards adoption transaction this
writer prepares, validates the complete after-image, and commits under the
shared state-writer lock -- or writes nothing.  The row it appends is born
`verified`; a contract-amendment row in any other state is evidence of a
bypassed writer, and the runtime validator treats it as such.

Exit codes: 0 = dry run reported or transaction committed; 1 = refused.
"""

import argparse
import copy
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib
import amendment_policy

TOOL = "apply_contract_amendment"
TOOL_VERSION = "1.1.0"
CHECK = "contract_amendment"
PLAN_PREFIX = check_queue.CONTRACT_AMENDMENT_PLAN_PREFIX
RECEIPT_PATH = ".cambium/receipts/contract-amendments.jsonl"
SENTINEL = "TODO(amendment)"

# Receipt IDs embed (stamp, run-token, seq); two transactions inside one
# process and second would otherwise collide.  The counter costs nothing
# and makes the ID unique per prepared transaction.
_RECEIPT_SEQ = itertools.count(1)

# The only contract fields this writer may change.  Extending this tuple is a
# governance change under K13/06, not an edit.
AMENDABLE_FIELDS = ("policy_exceptions", "amendment_authority")

PLAN_FIELDS_V1 = {
    "schema_version", "amendment_id", "task_id", "date", "summary",
    "approval_reference", "before", "contract_version_after",
    "policy_exceptions_after",
}
PLAN_FIELDS_V2 = PLAN_FIELDS_V1.union(("amendment_authority_after",))
BEFORE_FIELDS = {"coverage_sha256", "queue_sha256", "progress_sha256"}

STATE_NAMES = ("coverage", "queue", "progress")
WRITTEN_NAMES = ("queue", "progress")


class Refusal(Exception):
    """A condition that stops the transaction before any byte is written."""


class ReceiptPublicationUncertain(Exception):
    """Receipt bytes may be durable; the lock is retained, nothing rolled back."""


def _load_plan(root, relative):
    path = kblib.managed_repository_path(
        root, relative, PLAN_PREFIX, suffixes=(".yaml", ".yml"),
        must_exist=True)
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        plan = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise Refusal("amendment plan is not UTF-8: %s" % exc)
    except kblib.YamlSubsetError as exc:
        raise Refusal(
            "amendment plan is not the restricted YAML subset: %s" % exc)
    if not isinstance(plan, dict):
        raise Refusal("amendment plan top level must be a mapping")
    return path, raw, plan


def _closed(mapping, allowed, label):
    if not isinstance(mapping, dict):
        raise Refusal("%s must be a mapping" % label)
    unknown = sorted(set(mapping) - allowed)
    missing = sorted(allowed - set(mapping))
    if unknown:
        raise Refusal("%s has unsupported field(s): %s"
                      % (label, ", ".join(unknown)))
    if missing:
        raise Refusal("%s is missing field(s): %s"
                      % (label, ", ".join(missing)))


def _validate_plan_shape(plan):
    if SENTINEL in kblib.canonical_yaml(plan):
        raise Refusal(
            "amendment plan still carries the template's %s sentinel; every "
            "one of them is an answer this transaction will not invent"
            % SENTINEL)
    schema_version = plan.get("schema_version")
    if schema_version not in (1, 2):
        raise Refusal("amendment plan schema_version must be 1 or 2")
    _closed(plan, (PLAN_FIELDS_V2 if schema_version == 2 else PLAN_FIELDS_V1),
            "amendment plan")
    for field in ("amendment_id", "task_id", "date", "summary",
                  "approval_reference", "contract_version_after"):
        value = plan[field]
        if not isinstance(value, str) or not value.strip():
            raise Refusal("amendment plan %s must be a nonempty string"
                          % field)
    _closed(plan["before"], BEFORE_FIELDS, "amendment plan before")
    for field, value in sorted(plan["before"].items()):
        if not (isinstance(value, str) and
                check_queue.SHA256_RE.fullmatch(value)):
            raise Refusal(
                "amendment plan before.%s must be spelled sha256:<64 hex "
                "digits>; `check_queue.py . --resume-status` reports the "
                "three current values" % field)
    shape_errors = check_queue._policy_exception_errors(
        plan["policy_exceptions_after"], "policy_exceptions_after")
    if shape_errors:
        raise Refusal(
            "amendment plan policy_exceptions_after is not the K13/02 "
            "shape:\n  %s" % "\n  ".join(shape_errors[:8]))
    if schema_version == 2:
        authority_errors = amendment_policy.amendment_authority_errors(
            plan["amendment_authority_after"],
            "amendment_authority_after")
        if authority_errors:
            raise Refusal(
                "amendment plan amendment_authority_after is not the K13/02 "
                "shape:\n  %s" % "\n  ".join(authority_errors[:8]))


def _current_effective_policy(root, contract):
    """Resolve the selected Profile's effective quota policy, or refuse.

    The writer resolves the same slot bytes the batch-close consumer will:
    the manifest's ``Priority Rubric`` binding through
    ``kblib.effective_priority_policy``.  A plan author never computes the
    canonical fingerprint by hand -- it is an internal representation -- so
    this function is what makes the template's fingerprint field checkable:
    the writer prints the expected value on mismatch.
    """
    manifest_rel = contract.get("selected_profile_manifest")
    if not isinstance(manifest_rel, str) or not manifest_rel.strip():
        raise Refusal("the contract names no selected_profile_manifest; a "
                      "policy exception cannot be judged against no profile")
    manifest_path = os.path.join(root, manifest_rel)
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest_text = handle.read()
    except OSError as exc:
        raise Refusal("the selected profile manifest is unreadable: %s" % exc)
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = (bindings.get("Priority Rubric") or "").strip("`").strip()
    if not binding:
        raise Refusal("the selected Profile binds no Priority Rubric slot; "
                      "K00/07 places the standing quotas there")
    rubric_path = os.path.join(os.path.dirname(manifest_path), binding)
    try:
        with open(rubric_path, encoding="utf-8") as handle:
            rubric_text = handle.read()
    except OSError as exc:
        raise Refusal("the Priority Rubric slot is unreadable: %s" % exc)
    policy, fingerprint, errors = kblib.effective_priority_policy(rubric_text)
    if errors or fingerprint is None:
        raise Refusal(
            "the selected Profile's Priority Rubric does not resolve:\n  %s"
            % "\n  ".join(errors[:5]))
    return policy, fingerprint


def _require_policy_authorization(policy, fingerprint, exceptions):
    """Refuse a plan whose grants are unbound or jointly unbounded.

    Two checks.  First, every exception for a registered policy must carry
    the CURRENT effective-policy fingerprint of ITS OWN family -- a quota
    grant is judged against the resolved Profile quotas, a kernel-owned
    policy against the kernel statement of the rule.  An exception judged
    against bytes that are not the live ones is not a grant, and the
    consumer would silently never match it.  Second, the effective quota
    ceilings -- exception where granted, standing quota where not -- must
    jointly stay strictly below 100 (K00/07): summing the grants alone
    would admit a P0 grant of 80 next to a standing P1 of 35.
    """
    for index, entry in enumerate(exceptions):
        if not isinstance(entry, dict):
            continue
        policy_id = entry.get("policy_id")
        if policy_id not in kblib.POLICY_REGISTRY:
            continue
        if policy_id in kblib.PRIORITY_QUOTA_POLICY_IDS:
            expected = fingerprint
        else:
            _object, expected, resolve_errors = kblib.effective_policy_for(
                policy_id)
            if resolve_errors or expected is None:
                raise Refusal(
                    "policy_exceptions_after[%d] names %s, which does not "
                    "resolve to an effective policy:\n  %s"
                    % (index, policy_id, "\n  ".join(resolve_errors)))
        claimed = entry.get("baseline_policy_fingerprint")
        if claimed != expected:
            raise Refusal(
                "policy_exceptions_after[%d] baseline_policy_fingerprint "
                "does not match the current effective policy for %s.\n"
                "  claimed:  %s\n"
                "  expected: %s\n"
                "The expected value is the fingerprint of the resolved "
                "policy object (for a quota: the standing values, kernel "
                "defaults and protocol version; for a kernel-owned policy: "
                "the kernel statement of the rule), not the SHA of any "
                "file; confirm the policy is the one this grant was judged "
                "against, then record the expected value"
                % (index, policy_id, claimed, expected))
    ceilings, errors = kblib.effective_quota_ceilings(policy, exceptions)
    del ceilings
    if errors:
        raise Refusal(
            "the granted ceilings are not jointly admissible:\n  %s"
            % "\n  ".join(errors))


def _state_paths(root):
    return {
        "coverage": kblib.managed_repository_path(
            root, check_queue.COVERAGE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
        "queue": kblib.managed_repository_path(
            root, check_queue.QUEUE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
        "progress": kblib.managed_repository_path(
            root, check_queue.PROGRESS_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True),
    }


def _read_state(paths):
    raw = {}
    documents = {}
    for name, path in paths.items():
        with open(path, "rb") as handle:
            raw[name] = handle.read()
        documents[name] = kblib.parse_yaml_subset(raw[name].decode("utf-8"))
    return raw, documents


def _require_before_match(plan, raw):
    for name in STATE_NAMES:
        expected = plan["before"]["%s_sha256" % name]
        actual = kblib.sha256_bytes(raw[name])
        if expected != actual:
            raise Refusal(
                "%s is %s but the plan was prepared against %s; the runtime "
                "moved after this plan was confirmed, so re-prepare it "
                "rather than merging" % (name, actual, expected))


def _require_amendable_runtime(documents, plan):
    queue, progress = documents["queue"], documents["progress"]
    if not (queue.get("required_queue") or []):
        raise Refusal(
            "the Queue is not materialized; before materialization the "
            "contract is an adopter input and initial planning owns the "
            "edge -- amend the task plan, not the contract")
    merge_ready = sorted(
        item.get("id") for item in queue.get("required_queue") or []
        if isinstance(item, dict) and item.get("state") == "merge-ready")
    if merge_ready:
        raise Refusal(
            "batch(es) %s are merge-ready; this transaction advances the "
            "Queue revision, which would strand their delta_apply receipt "
            "bindings. Close or roll back the merge-ready batch first (the "
            "K13/15 adoption transaction refuses the same state for the "
            "same reason) -- or grant the exception before the batch leaves "
            "open" % ", ".join(merge_ready))
    if progress.get("task_state") not in ("planned", "active", "paused"):
        raise Refusal(
            "task_state is %r; a contract amendment applies only to a "
            "planned, active, or paused task -- a terminal task's contract "
            "is history" % progress.get("task_state"))
    for name in STATE_NAMES:
        recorded = documents[name].get("task_id")
        if recorded != plan["task_id"]:
            raise Refusal("%s records task_id %r but the plan names %r"
                          % (name, recorded, plan["task_id"]))
    contract = progress.get("contract")
    if not isinstance(contract, dict):
        raise Refusal("Progress carries no Task Contract to amend")
    if plan["contract_version_after"] == contract.get("contract_version"):
        raise Refusal(
            "contract_version_after equals the live contract_version; the "
            "amendment must advance it so the anchor chain can tell the two "
            "contracts apart")
    for amendment in progress.get("amendments", []) if isinstance(
            progress.get("amendments"), list) else []:
        if (isinstance(amendment, dict) and
                amendment.get("id") == plan["amendment_id"]):
            raise Refusal("Progress already contains Amendment %s"
                          % plan["amendment_id"])


def _build_after(documents, plan, receipt_id, now):
    queue = copy.deepcopy(documents["queue"])
    progress = copy.deepcopy(documents["progress"])
    contract_before = progress.get("contract") or {}
    contract = copy.deepcopy(contract_before)
    contract["policy_exceptions"] = copy.deepcopy(
        plan["policy_exceptions_after"])
    if plan.get("schema_version") == 2:
        contract["amendment_authority"] = copy.deepcopy(
            plan["amendment_authority_after"])
    contract["contract_version"] = plan["contract_version_after"]
    progress["contract"] = contract

    revision_before = queue.get("queue_revision")
    if (not isinstance(revision_before, int) or
            isinstance(revision_before, bool) or revision_before < 1):
        raise Refusal("Queue queue_revision is not a positive integer")
    queue["queue_revision"] = revision_before + 1
    queue_text = kblib.canonical_yaml(queue)
    progress["queue_revision"] = revision_before + 1
    progress["required_queue_sha256"] = kblib.sha256_bytes(queue_text)

    row = {
        "id": plan["amendment_id"],
        "date": plan["date"],
        "summary": plan["summary"],
        "status": "verified",
        "writeback_done": True,
        "operation": "contract-amendment",
        "approval_reference": plan["approval_reference"],
        "scope_version_before": contract_before.get("scope_version"),
        "scope_version_after": contract_before.get("scope_version"),
        "queue_revision_before": revision_before,
        "queue_revision_after": revision_before + 1,
        "state_revision_before": queue.get("state_revision"),
        "state_revision_after": queue.get("state_revision"),
        "contract_version_before": contract_before.get("contract_version"),
        "contract_version_after": plan["contract_version_after"],
        "plan_path": None,   # bound after the relative path is known
        "plan_sha256": None,
        "verification_receipt": receipt_id,
    }
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        raise Refusal("Progress amendments must be an explicit list")
    amendments.append(row)
    del now
    return queue, queue_text, progress, contract_before, row


def prepare(root, plan_relative):
    """Everything that can refuse, before any byte is written."""
    plan_path, plan_raw, plan = _load_plan(root, plan_relative)
    _validate_plan_shape(plan)
    paths = _state_paths(root)
    raw, documents = _read_state(paths)
    _require_before_match(plan, raw)
    _require_amendable_runtime(documents, plan)

    current = check_queue.validate_runtime(root)
    if current["errors"]:
        raise Refusal(
            "the current runtime does not validate; repair it before "
            "amending the contract:\n  %s"
            % "\n  ".join(current["errors"][:5]))

    contract_before = documents["progress"]["contract"]
    if plan.get("schema_version") == 2:
        changed = []
        if contract_before.get("policy_exceptions", []) != plan.get(
                "policy_exceptions_after"):
            changed.append("policy_exceptions")
        if contract_before.get("amendment_authority") != plan.get(
                "amendment_authority_after"):
            changed.append("amendment_authority")
        if not changed:
            raise Refusal(
                "schema_version 2 contract amendment changes no amendable field")
    else:
        changed = ["policy_exceptions"]
    policy, policy_fingerprint = _current_effective_policy(
        root, contract_before)
    _require_policy_authorization(
        policy, policy_fingerprint, plan["policy_exceptions_after"])
    commit_receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, plan["amendment_id"], "pass",
        "amended Task Contract field(s) %s from plan %s"
        % (", ".join(changed), plan_relative), next(_RECEIPT_SEQ),
        identity={
            "task_id": plan["task_id"],
            "standards_version": contract_before.get("standards_version"),
            "selected_profile_manifest":
                contract_before.get("selected_profile_manifest"),
        })

    queue, queue_text, progress, contract_before, row = _build_after(
        documents, plan, commit_receipt["receipt_id"],
        commit_receipt["checked_at"])
    relative_plan = os.path.relpath(plan_path, root).replace(os.sep, "/")
    row["plan_path"] = relative_plan
    row["plan_sha256"] = kblib.sha256_bytes(plan_raw)
    # The row records the same state edge the receipt claims, so the runtime
    # validator can cross-bind the two exactly as the K13/15 adoption record
    # binds its commit receipt.  ``after_progress_sha256`` stays on the
    # receipt alone: the row lives inside the progress document, and a hash
    # of bytes that contain it is not computable.  This block runs BEFORE the
    # progress bytes are rendered; a field added after rendering would never
    # reach the written document.
    row.update({
        "coverage_sha256_before": kblib.sha256_bytes(raw["coverage"]),
        "required_queue_sha256_before": kblib.sha256_bytes(raw["queue"]),
        "progress_sha256_before": kblib.sha256_bytes(raw["progress"]),
        "after_coverage_sha256": kblib.sha256_bytes(raw["coverage"]),
        "after_required_queue_sha256": kblib.sha256_bytes(queue_text),
        "policy_fingerprint": policy_fingerprint,
        "changed_contract_fields": changed,
    })

    progress_text = kblib.canonical_yaml(progress)
    commit_receipt.update({
        "transaction_phase": "commit",
        "actor_role": "integrator",
        "plan_path": relative_plan,
        "plan_sha256": row["plan_sha256"],
        "before_contract_sha256":
            check_queue._contract_sha256(documents["progress"]),
        "after_contract_sha256": check_queue._contract_sha256(progress),
        "before_contract_version": row["contract_version_before"],
        "after_contract_version": row["contract_version_after"],
        "before_contract_scope_version": row["scope_version_before"],
        "after_contract_scope_version": row["scope_version_after"],
        "queue_revision_before": row["queue_revision_before"],
        "queue_revision_after": row["queue_revision_after"],
        "before_required_queue_sha256": kblib.sha256_bytes(raw["queue"]),
        "after_required_queue_sha256": kblib.sha256_bytes(queue_text),
        "before_progress_sha256": kblib.sha256_bytes(raw["progress"]),
        "after_progress_sha256": kblib.sha256_bytes(progress_text),
        "before_coverage_sha256": kblib.sha256_bytes(raw["coverage"]),
        "after_coverage_sha256": kblib.sha256_bytes(raw["coverage"]),
        "policy_fingerprint": policy_fingerprint,
        "changed_contract_fields": changed,
    })

    proposed = check_queue.validate_runtime(
        root,
        state_overrides={
            check_queue.QUEUE_PATH: (queue_text, queue),
            check_queue.PROGRESS_PATH: (progress_text, progress),
        },
        extra_receipts=[commit_receipt],
    )["errors"]
    if proposed:
        raise Refusal(
            "the runtime this amendment proposes does not validate:\n  %s"
            % "\n  ".join(proposed[:10]))

    return {
        "root": root,
        "plan": plan,
        "plan_path": relative_plan,
        "plan_sha": row["plan_sha256"],
        "paths": paths,
        "before_raw": raw,
        "before_sha": {name: kblib.sha256_bytes(raw[name])
                       for name in STATE_NAMES},
        "after_text": {"queue": queue_text, "progress": progress_text},
        "after_sha": {
            "queue": kblib.sha256_bytes(queue_text),
            "progress": kblib.sha256_bytes(progress_text),
        },
        "receipt": commit_receipt,
        "row": row,
        "policy_fingerprint": policy_fingerprint,
        "contract_before": contract_before,
        "changed_contract_fields": changed,
    }


def commit(prepared, receipt_path):
    plan = prepared["plan"]
    root = prepared["root"]
    receipt = prepared["receipt"]
    operation = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "contract-amendment",
        "target": plan["amendment_id"],
        "task_id": plan["task_id"],
        "plan_path": prepared["plan_path"],
        "plan_sha256": prepared["plan_sha"],
        "commit_receipt_id": receipt["receipt_id"],
        # The generic writer recovery protocol (`check_queue`
        # `_bind_generic_lock_receipts`) reads these three: they let a
        # recovery view decide whether the declared receipt actually landed
        # and therefore whether to complete or roll back a stale lock.
        "receipt_id": receipt["receipt_id"],
        "receipt_path": receipt_path,
        "transaction_phase": "commit",
    }
    for name in STATE_NAMES:
        operation["before_%s_sha256" % name] = prepared["before_sha"][name]
    for name in WRITTEN_NAMES:
        operation["planned_after_%s_sha256" % name] = \
            prepared["after_sha"][name]
    # The recovery semantic cross-check reads the longer Required Queue
    # spelling from writer-lock metadata; both names identify the same file.
    operation["before_required_queue_sha256"] = \
        prepared["before_sha"]["queue"]
    operation["planned_after_required_queue_sha256"] = \
        prepared["after_sha"]["queue"]

    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        with kblib.no_authoritative_write_guard(lease):
            for name in STATE_NAMES:
                with open(prepared["paths"][name], "rb") as handle:
                    live = handle.read()
                if kblib.sha256_bytes(live) != prepared["before_sha"][name]:
                    raise Refusal(
                        "%s changed between planning and commit" % name)
            # The plan's bytes are sealed into the row and receipt; a plan
            # edited after prepare would commit a row pointing at bytes that
            # no longer exist.  Same-lock re-verification, like the K13/15
            # adoption re-CAS of its own plan.
            plan_file = kblib.managed_repository_path(
                root, prepared["plan_path"], PLAN_PREFIX,
                suffixes=(".yaml", ".yml"), must_exist=True)
            if kblib.sha256_file(plan_file) != prepared["plan_sha"]:
                raise Refusal(
                    "the amendment plan changed between prepare and commit; "
                    "re-prepare against its current bytes")
            # Same-lock policy re-resolution: the Priority Rubric could have
            # been revised between prepare and commit, and a grant judged
            # against bytes that are no longer the live policy must refuse
            # here, not silently never match at consumption.
            _, live_fingerprint = _current_effective_policy(
                root, prepared["contract_before"])
            if live_fingerprint != prepared["policy_fingerprint"]:
                raise Refusal(
                    "the effective quota policy changed between prepare and "
                    "commit (fingerprint %s -> %s); re-prepare so the grant "
                    "is judged against the live policy"
                    % (prepared["policy_fingerprint"], live_fingerprint))
        written = []
        appended = False
        try:
            for name in WRITTEN_NAMES:
                kblib.atomic_write_text(
                    prepared["paths"][name], prepared["after_text"][name])
                written.append(name)
            before = kblib.receipt_append_observation(
                receipt_path, [receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, [receipt], before=before)
            appended = outcome == "present"
            if outcome == "uncertain" or (appended and error is not None):
                # The receipt bytes may be durable.  Rolling back the state
                # now could leave a committed receipt describing a runtime
                # that no longer exists; the lock is retained with the
                # before/planned-after fingerprints as recovery evidence,
                # exactly as K13/15 keeps its lock past possible-commit.
                raise ReceiptPublicationUncertain(
                    "commit receipt publication is uncertain (%r); the "
                    "writer lock is retained for reconciliation" % outcome)
            if error is not None:
                raise error
            if not appended:
                raise Refusal(
                    "commit receipt append reported %r" % outcome)
        except ReceiptPublicationUncertain:
            raise
        except Exception:
            for name in reversed(written):
                kblib.atomic_write_text(
                    prepared["paths"][name],
                    prepared["before_raw"][name].decode("utf-8"))
            lease.mark_reconciled()
            raise
    return receipt


def _report(prepared):
    plan = prepared["plan"]
    row = prepared["row"]
    print("apply_contract_amendment: amendment %s task %s"
          % (plan["amendment_id"], plan["task_id"]))
    print("  confirmed by: %s" % plan["approval_reference"])
    print("  contract_version: %s -> %s"
          % (row["contract_version_before"], row["contract_version_after"]))
    print("  policy exceptions after: %d"
          % len(plan["policy_exceptions_after"]))
    if plan.get("schema_version") == 2:
        authority = plan["amendment_authority_after"]
        print("  amendment authority after: %s (%s)"
              % (authority["authority_id"], authority["mode"]))
    print("  changed contract fields: %s"
          % ", ".join(prepared["changed_contract_fields"]))
    print("  queue_revision: %s -> %s"
          % (row["queue_revision_before"], row["queue_revision_after"]))
    for name in WRITTEN_NAMES:
        print("  %s: %s -> %s"
              % (name, prepared["before_sha"][name][:18],
                 prepared["after_sha"][name][:18]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Amend the frozen Task Contract from one confirmed plan.")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--plan", required=True,
                        help="repository-relative path under %s" % PLAN_PREFIX)
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under .cambium/receipts")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker")
    parser.add_argument("--apply", action="store_true",
                        help="write the transaction; omit for a dry run")
    args = parser.parse_args(argv)

    if args.apply and args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply a contract "
              "amendment")
        return 1

    root = os.path.realpath(os.path.abspath(args.root))
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
        prepared = prepare(root, args.plan)
    except (Refusal, OSError, UnicodeError, ValueError, TypeError,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1

    _report(prepared)
    if not args.apply:
        print("apply_contract_amendment: dry run; re-run with --apply to "
              "commit")
        return 0

    try:
        receipt = commit(prepared, receipt_path)
    except ReceiptPublicationUncertain as exc:
        print("[FAIL] %s" % exc)
        print("apply_contract_amendment: reconcile with check_queue.py . "
              "--resume-status before any further write")
        return 1
    except (Refusal, OSError, ValueError, TypeError) as exc:
        print("[FAIL] %s" % exc)
        return 1
    print("apply_contract_amendment: committed as %s" % receipt["receipt_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
