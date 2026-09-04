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

import copy
import itertools
import os
import sys

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.canon as queue_canon
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.execution.task_runtime.amendment_policy as amendment_policy
import Tools.governance.control.contract_exception_policy as contract_exception_policy
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_io as runtime_state_io
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.common import reporting

TOOL = queue_canon.CONTRACT_AMENDMENT_TOOL
TOOL_VERSION = queue_canon.CONTRACT_AMENDMENT_TOOL_VERSION
CHECK = "contract_amendment"
RECEIPT_TYPE_ID = "contract-amendment-receipt-v1"


def current_receipt_errors(record, *, root=None):
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=CHECK)
PLAN_PREFIX = queue_runtime.CONTRACT_AMENDMENT_PLAN_PREFIX
RECEIPT_PATH = runtime_paths.CONTRACT_AMENDMENT_RECEIPT_PATH
SENTINEL = "TODO(amendment)"

# Receipt IDs embed (stamp, run-token, seq); two transactions inside one
# process and second would otherwise collide.  The counter costs nothing
# and makes the ID unique per prepared transaction.
_RECEIPT_SEQ = itertools.count(1)

PLAN_FIELDS = {
    "schema_version", "amendment_id", "task_id", "date", "summary",
    "approval_reference", "before", "contract_version_after",
    "policy_exceptions_after", "amendment_authority_after",
}
BEFORE_FIELDS = runtime_state_contract.RUNTIME_LEDGER_FINGERPRINT_FIELDS

STATE_NAMES = runtime_state_contract.RUNTIME_LEDGER_IDS
WRITTEN_NAMES = ("queue", "progress")


JSON_HELP = reporting.JSON_RECEIPT_HELP
_JSON_REPORTER = reporting.JsonReceiptCollector()


class Refusal(Exception):
    """A condition that stops the transaction before any byte is written."""


class ReceiptPublicationUncertain(Exception):
    """Receipt bytes may be durable; the lock is retained, nothing rolled back."""


def _load_plan(root, relative):
    path = kblib.managed_repository_path(
        root, relative, PLAN_PREFIX, suffixes=(".yaml", ".yml"),
        must_exist=True)
    raw = kblib.read_bytes(path)
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
    if schema_version != 2:
        raise Refusal("contract amendment plan schema_version must be 2")
    _closed(plan, PLAN_FIELDS, "contract amendment plan")
    for field in ("amendment_id", "task_id", "date", "summary",
                  "approval_reference", "contract_version_after"):
        value = plan[field]
        if not isinstance(value, str) or not value.strip():
            raise Refusal("amendment plan %s must be a nonempty string"
                          % field)
    _closed(plan["before"], BEFORE_FIELDS, "amendment plan before")
    for field, value in sorted(plan["before"].items()):
        if not (isinstance(value, str) and
                queue_runtime.SHA256_RE.fullmatch(value)):
            raise Refusal(
                "amendment plan before.%s must be spelled sha256:<64 hex "
                "digits>; `check_queue.py . --resume-status` reports the "
                "three current values" % field)
    shape_errors = queue_runtime.policy_exception_errors(
        plan["policy_exceptions_after"], "policy_exceptions_after")
    if shape_errors:
        raise Refusal(
            "amendment plan policy_exceptions_after is not the K13/02 "
            "shape:\n  %s" % "\n  ".join(shape_errors[:8]))
    authority_errors = amendment_policy.amendment_authority_errors(
        plan["amendment_authority_after"],
        "amendment_authority_after")
    if authority_errors:
        raise Refusal(
            "amendment plan amendment_authority_after is not the K13/02 "
            "shape:\n  %s" % "\n  ".join(authority_errors[:8]))


def _current_effective_policy(root, contract):
    """Resolve the selected Profile's optional quota policy, or refuse.

    The writer resolves the same slot bytes the batch-close consumer will:
    the manifest's ``Priority Rubric`` binding through
    ``contract_exception_policy.effective_priority_policy``.  A plan
    author never computes the canonical fingerprint by hand -- it is an
    internal representation -- so
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
                      "K00/07 places optional quota registration there")
    rubric_path = os.path.join(os.path.dirname(manifest_path), binding)
    try:
        with open(rubric_path, encoding="utf-8") as handle:
            rubric_text = handle.read()
    except OSError as exc:
        raise Refusal("the Priority Rubric slot is unreadable: %s" % exc)
    policy, fingerprint, errors = (
        contract_exception_policy.effective_priority_policy(rubric_text))
    if errors or fingerprint is None:
        raise Refusal(
            "the selected Profile's Priority Rubric does not resolve:\n  %s"
            % "\n  ".join(errors[:5]))
    return policy, fingerprint


def _require_policy_authorization(policy, fingerprint, exceptions):
    """Refuse a plan whose grants are unbound or jointly unbounded.

    Two checks.  First, every exception for a registered policy must carry
    the CURRENT effective-policy fingerprint of ITS OWN family -- a quota
    grant is judged against the Profile's resolved registration, while a
    kernel-owned policy is judged against the Kernel statement of the rule.
    An exception judged against a policy that is not current is not a grant,
    and the consumer would silently never match it. Second, quota exceptions
    are legal only when the Profile configured the pair, and the effective
    ceilings -- exception where granted, configured value where not -- must
    jointly stay below the Kernel registry's partition ceiling (K00/07).
    """
    for index, entry in enumerate(exceptions):
        if not isinstance(entry, dict):
            continue
        policy_id = entry.get("policy_id")
        if policy_id not in contract_exception_policy.POLICY_REGISTRY:
            continue
        if policy_id in contract_exception_policy.PRIORITY_QUOTA_POLICY_IDS:
            expected = fingerprint
        else:
            _object, expected, resolve_errors = (
                contract_exception_policy.effective_policy_for(policy_id))
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
                "policy object (for a quota: enabled state, configured values "
                "when present, and protocol version; for a kernel-owned "
                "policy: the kernel statement of the rule), not the SHA of "
                "any file; confirm the policy is the one this grant was "
                "judged against, then record the expected value"
                % (index, policy_id, claimed, expected))
    ceilings, errors = contract_exception_policy.effective_quota_ceilings(
        policy, exceptions)
    del ceilings
    if errors:
        raise Refusal(
            "the granted ceilings are not jointly admissible:\n  %s"
            % "\n  ".join(errors))


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
    paths = runtime_state_io.state_paths(root)
    raw, documents = runtime_state_io.read_state(paths)
    mismatch = runtime_state_io.before_image_mismatch(plan, raw)
    if mismatch is not None:
        raise Refusal(mismatch)
    # This is an admission boundary rather than a consistency exception: an
    # unmaterialized Queue is intentionally not yet a writer-owned runtime.
    # Preserve that precise refusal before the full materialized-runtime pass.
    _require_amendable_runtime(documents, plan)

    current = runtime_validation.validate_runtime(root)
    if current["errors"]:
        raise Refusal(
            "the current runtime does not validate; repair it before "
            "amending the contract:\n  %s"
            % "\n  ".join(current["errors"][:5]))
    before_sha = {
        name: kblib.sha256_bytes(raw[name])
        for name in STATE_NAMES
    }
    for name in STATE_NAMES:
        admitted = current.get("%s_sha256" % name)
        if admitted != before_sha[name]:
            raise Refusal(
                "%s changed while the runtime authority was being admitted; "
                "re-prepare against one stable runtime snapshot" % name)
    try:
        authority = queue_runtime.runtime_authority_context(current)
        authority_kwargs = \
            queue_runtime.runtime_authority_validation_kwargs(authority)
        queue_runtime.require_runtime_authority_current(
            root, authority,
            "runtime authority changed while preparing contract amendment")
    except (TypeError, ValueError) as exc:
        raise Refusal(str(exc))

    contract_before = documents["progress"]["contract"]
    changed = []
    if contract_before.get("policy_exceptions", []) != plan.get(
            "policy_exceptions_after"):
        changed.append("policy_exceptions")
    if contract_before.get("amendment_authority") != plan.get(
            "amendment_authority_after"):
        changed.append("amendment_authority")
    if not changed:
        raise Refusal(
            "contract amendment changes no amendable field")
    policy, policy_fingerprint = _current_effective_policy(
        root, contract_before)
    _require_policy_authorization(
        policy, policy_fingerprint, plan["policy_exceptions_after"])
    commit_receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, plan["amendment_id"], "pass",
        "amended Task Contract field(s) %s from plan %s"
        % (", ".join(changed), plan_relative), next(_RECEIPT_SEQ),
        receipt_type_id=RECEIPT_TYPE_ID,
        identity={
            "task_id": plan["task_id"],
            "upstream_revision_id": contract_before.get("upstream_revision_id"),
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
            queue_runtime.contract_sha256(documents["progress"]),
        "after_contract_sha256": queue_runtime.contract_sha256(progress),
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

    proposed = runtime_validation.validate_runtime(
        root,
        state_overrides={
            queue_runtime.QUEUE_PATH: (queue_text, queue),
            queue_runtime.PROGRESS_PATH: (progress_text, progress),
        },
        extra_receipts=[commit_receipt],
        **authority_kwargs,
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
        "before_sha": before_sha,
        "after_text": {"queue": queue_text, "progress": progress_text},
        "after_sha": {
            "coverage": before_sha["coverage"],
            "queue": kblib.sha256_bytes(queue_text),
            "progress": kblib.sha256_bytes(progress_text),
        },
        "receipt": commit_receipt,
        "row": row,
        "policy_fingerprint": policy_fingerprint,
        "contract_before": contract_before,
        "changed_contract_fields": changed,
        "authority": authority,
    }


def _state_image_errors(paths, expected_sha, label):
    """Return exact canonical-ledger read-back failures for one image.

    Runtime validation proves semantic consistency.  It does not replace the
    writer's byte-level resulting-state claim: a successful process must also
    re-open every canonical ledger and prove that the exact planned image is
    what became durable.
    """
    errors = []
    for name in STATE_NAMES:
        try:
            actual = kblib.sha256_file(paths[name])
        except OSError as exc:
            errors.append("%s %s cannot be read back: %s" %
                          (label, name, exc))
            continue
        if actual != expected_sha[name]:
            errors.append(
                "%s %s read-back is %s, expected %s" %
                (label, name, actual, expected_sha[name]))
    return errors


def _restore_written(paths, before_raw, written):
    """Restore and then byte-verify only ledgers this transaction touched."""
    failures = []
    for name in reversed(tuple(written)):
        try:
            kblib.atomic_write_text(
                paths[name], before_raw[name].decode("utf-8"),
                validator=kblib.parse_yaml_subset)
        except Exception as exc:
            failures.append("%s: %s" % (name, exc))
    for name in tuple(written):
        try:
            with open(paths[name], "rb") as handle:
                live = handle.read()
            if live != before_raw[name]:
                failures.append("%s bytes differ after rollback" % name)
        except Exception as exc:
            failures.append("%s rollback verification: %s" % (name, exc))
    return failures


def commit(prepared, receipt_path):
    plan = prepared["plan"]
    root = prepared["root"]
    receipt = prepared["receipt"]
    receipt_path = os.fspath(receipt_path)
    receipt_relative = os.path.relpath(
        os.path.realpath(os.path.abspath(receipt_path)), root).replace(
            os.sep, "/")
    authority = prepared["authority"]
    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
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
        # `bind_generic_lock_receipts`) reads these three: they let a
        # recovery view decide whether the declared receipt actually landed
        # and therefore whether to complete or roll back a stale lock.
        "receipt_id": receipt["receipt_id"],
        "receipt_path": receipt_relative,
        "transaction_phase": "commit",
    }
    for name in STATE_NAMES:
        operation["before_%s_sha256" % name] = prepared["before_sha"][name]
    for name in STATE_NAMES:
        operation["planned_after_%s_sha256" % name] = \
            prepared["after_sha"][name]
    operation["before_queue_sha256"] = \
        prepared["before_sha"]["queue"]
    operation["planned_after_queue_sha256"] = \
        prepared["after_sha"]["queue"]
    operation.update(queue_runtime.runtime_authority_lock_fields(authority))

    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        receipt_before = None
        with kblib.no_authoritative_write_guard(lease):
            locked = runtime_validation.validate_runtime(
                root, **authority_kwargs)
            if locked["errors"]:
                raise Refusal(
                    "runtime changed before contract amendment write:\n  %s"
                    % "\n  ".join(locked["errors"][:5]))
            before_errors = _state_image_errors(
                prepared["paths"], prepared["before_sha"],
                "locked before-image")
            if before_errors:
                raise Refusal("; ".join(before_errors))
            queue_runtime.require_runtime_authority_current(
                root, authority, "runtime authority changed under lock")
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
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during locked policy resolution")
            receipt_before = kblib.receipt_append_observation(
                receipt_path, [receipt])
        written = []
        receipt_attempted = False
        receipt_outcome = "not-attempted"
        try:
            for name in WRITTEN_NAMES:
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before %s write" % name)
                # Count the ledger before the call: an atomic-write exception
                # may occur after the replacement became durable.
                written.append(name)
                kblib.atomic_write_text(
                    prepared["paths"][name], prepared["after_text"][name],
                    validator=kblib.parse_yaml_subset)
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during %s write" % name)
            after_errors = _state_image_errors(
                prepared["paths"], prepared["after_sha"],
                "post-write after-image")
            if after_errors:
                raise ValueError("; ".join(after_errors))
            post = runtime_validation.validate_runtime(
                root, extra_receipts=[receipt], **authority_kwargs)
            if post["errors"]:
                raise ValueError(
                    "post-write contract amendment failed validation: %s" %
                    "; ".join(post["errors"][:10]))
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before contract amendment receipt")
            receipt_attempted = True
            receipt_outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, _JSON_REPORTER.record([receipt]),
                before=receipt_before)
            if (receipt_outcome == "uncertain" or
                    (receipt_outcome == "present" and error is not None)):
                # The receipt bytes may be durable.  Rolling back the state
                # now could leave a committed receipt describing a runtime
                # that no longer exists; the lock is retained with the
                # before/planned-after fingerprints as recovery evidence,
                # exactly as K13/15 keeps its lock past possible-commit.
                raise ReceiptPublicationUncertain(
                    "commit receipt publication is uncertain (%r); the "
                    "writer lock is retained for reconciliation" %
                    receipt_outcome)
            if error is not None:
                raise error
            if receipt_outcome != "present":
                raise Refusal(
                    "commit receipt append reported %r" % receipt_outcome)

            # From this point the pass Receipt is durable.  Any failure is a
            # reconciliation case, not permission to roll state back behind
            # an append-only commit claim.
            try:
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during contract amendment "
                    "receipt")
                persisted = runtime_validation.validate_runtime(
                    root, **authority_kwargs)
                if persisted["errors"]:
                    raise ValueError(
                        "persisted contract amendment failed validation: %s" %
                        "; ".join(persisted["errors"][:10]))
                resulting_errors = _state_image_errors(
                    prepared["paths"], prepared["after_sha"],
                    "persisted resulting state")
                if resulting_errors:
                    raise ValueError("; ".join(resulting_errors))
                if kblib.receipt_outcome_from(
                        receipt_path, [receipt], receipt_before) != "present":
                    raise ValueError(
                        "commit Receipt did not read back as exactly one "
                        "durable record")
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during resulting-state "
                    "read-back")
            except Exception as exc:
                raise ReceiptPublicationUncertain(
                    "commit receipt is durable but resulting-state read-back "
                    "failed; the writer lock is retained for reconciliation: "
                    "%s" % exc) from exc
        except ReceiptPublicationUncertain:
            raise
        except Exception as exc:
            if receipt_attempted and receipt_outcome == "not-attempted":
                receipt_outcome = kblib.receipt_outcome_from(
                    receipt_path, [receipt], receipt_before)
            elif not receipt_attempted:
                receipt_outcome = "absent"
            if receipt_outcome != "absent":
                raise ReceiptPublicationUncertain(
                    "contract amendment failed after receipt publication "
                    "became %s; the writer lock is retained for "
                    "reconciliation: %s" % (receipt_outcome, exc)) from exc
            rollback_failures = _restore_written(
                prepared["paths"], prepared["before_raw"], written)
            if rollback_failures:
                raise ValueError(
                    "contract amendment failed and rollback is incomplete: "
                    "%s; %s" % (exc, "; ".join(rollback_failures))) from exc
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
    parser = kblib.ArgumentParser(
        description="Amend the frozen Task Contract from one confirmed plan.")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--plan", required=True,
                        help="repository-relative path under %s" % PLAN_PREFIX)
    parser.add_argument("--receipts", default=RECEIPT_PATH,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may "
                             "apply a contract amendment")
    parser.add_argument("--apply", action="store_true",
                        help="write the transaction; omit for a dry run")
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _JSON_REPORTER.run(lambda: _run(args))


def _run(args):
    """This tool's own run; `main` above owns only argument parsing."""
    if args.apply and args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply a contract "
              "amendment")
        return 1

    root = os.path.realpath(os.path.abspath(args.root))
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
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
