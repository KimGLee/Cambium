"""What an interrupted cooperating writer left behind.

The lock inventory and the durable prepare/commit/abort, state-phase and
moved-Delta evidence bound to it.  Everything here is described as evidence
and nothing is auto-recovered: a writer that died mid-transaction leaves a
state a person must read, and a runtime that tidied it away would destroy the
only record of what happened.
"""

import json
import os

import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract

from Tools.execution.task_runtime.queue_runtime.canon import (
    APPLY_AMENDMENT_TOOL_VERSION,
    BATCH_CLOSE_TOOL,
    REGISTER_AMENDMENT_TOOL,
    REGISTER_AMENDMENT_TOOL_VERSION,
    SHA256_RE,
)
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string


LOCK_STATE_FINGERPRINTS = {
    "coverage": {
        "before": ("before_coverage_sha256",),
        "planned_after": ("planned_after_coverage_sha256",),
    },
    "queue": {
        "before": ("before_queue_sha256",),
        "planned_after": ("planned_after_queue_sha256",),
    },
    "progress": {
        "before": ("before_progress_sha256",),
        "planned_after": ("planned_after_progress_sha256",),
    },
    "standards": {
        # The active Standards admission binding and the transaction
        # before-image are different roles even when they name the same
        # bytes.  Every current writer records both explicitly; recovery
        # consumes only the transaction field here.
        "before": ("before_standards_state_sha256",),
        "planned_after": ("planned_after_standards_state_sha256",),
    },
}
# The lock operation and the produced Receipt are different machine objects.
# This table is their exact queue-fingerprint adapter: one field per position,
# never a list of historical aliases.  Receipt owners keep their own stable
# vocabulary while lock metadata follows runtime ledger id ``queue``.
GENERIC_RECEIPT_QUEUE_FIELDS = {
    "apply_delta": (
        "before_required_queue_sha256", "after_required_queue_sha256"),
    "update_queue": (
        "before_required_queue_sha256", "after_required_queue_sha256"),
    "compile_queue": (
        "before_required_queue_sha256", "after_required_queue_sha256"),
    "update_task": (
        "before_required_queue_sha256", "after_required_queue_sha256"),
    "check_batch_close": (
        "before_required_queue_sha256", "after_required_queue_sha256"),
    "adopt_standards": ("before_queue_sha256", "after_queue_sha256"),
    "register_amendment": (
        "before_required_queue_sha256", "after_required_queue_sha256"),
    "apply_contract_amendment": (
        "before_required_queue_sha256", "after_required_queue_sha256"),
    "apply_task_plan": (None, "after_required_queue_sha256"),
}
GENERIC_WRITER_TOOLS = frozenset(GENERIC_RECEIPT_QUEUE_FIELDS)


def inventory_writer_locks(root, errors):
    """Inventory cooperating-writer locks without deciding whether stale.

    A lock can mean either a live writer or an interrupted writer.  The
    checker deliberately does not guess which: callers fail closed and expose
    the owner metadata so a later task can reconcile the state first.
    """
    relative_tmp = runtime_paths.TRANSIENT_ROOT
    tmp_dir = os.path.join(root, relative_tmp)
    locks = []
    if not os.path.lexists(tmp_dir):
        # Candidate/preflight trees may contain only canonical state and
        # evidence.  No tmp namespace means there is no cooperating-writer
        # lock to report; initialization remains responsible for creating it
        # in a materialized adopter runtime.
        return locks
    if os.path.islink(tmp_dir) or not os.path.isdir(tmp_dir):
        errors.append("%s must be a real directory" % relative_tmp)
        return locks
    try:
        names = sorted(os.listdir(tmp_dir))
    except OSError as exc:
        errors.append("cannot inventory %s: %s" % (relative_tmp, exc))
        return locks
    for name in names:
        if not name.endswith(".lock"):
            continue
        relative = "%s/%s" % (relative_tmp, name)
        lock_path = os.path.join(tmp_dir, name)
        lock = {"path": relative, "owner": None, "owner_error": None}
        try:
            stat_result = os.lstat(lock_path)
            if os.path.islink(lock_path) or not os.path.isdir(lock_path):
                lock["owner_error"] = "lock is not a real directory"
                locks.append(lock)
                continue
            if stat_result.st_nlink < 2:
                lock["owner_error"] = "lock directory metadata is invalid"
        except OSError as exc:
            lock["owner_error"] = "cannot stat lock: %s" % exc
            locks.append(lock)
            continue
        owner_path = os.path.join(lock_path, "owner.json")
        if not os.path.lexists(owner_path):
            lock["owner_error"] = "owner.json is missing"
            locks.append(lock)
            continue
        try:
            owner_stat = os.lstat(owner_path)
            if (os.path.islink(owner_path) or not os.path.isfile(owner_path) or
                    owner_stat.st_nlink != 1):
                raise ValueError("owner.json must be a regular, singly-linked file")
            with open(owner_path, encoding="utf-8") as fh:
                owner = json.load(fh)
            if not isinstance(owner, dict):
                raise ValueError("owner.json top level must be an object")
            lock["owner"] = owner
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            lock["owner_error"] = str(exc)
        locks.append(lock)
    return locks


def bind_lock_receipts(_writer_locks, catalog):
    """Annotate transaction locks with durable prepare/commit/abort evidence."""
    for lock in _writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        transaction_id = (operation.get("transaction_id")
                          if isinstance(operation, dict) else None)
        if not nonempty_string(transaction_id):
            continue
        matches = []
        for receipt_id, (relative, receipt) in catalog.items():
            if (receipt.get("tool") == "apply_amendment" and
                    receipt.get("transaction_id") == transaction_id and
                    receipt.get("transaction_phase") in
                    ("prepare", "commit", "abort")):
                semantic_errors = []
                phase = receipt.get("transaction_phase")
                expected_result = {
                    "prepare": "candidate",
                    "commit": "pass",
                    "abort": "fail",
                }[phase]
                for field, expected in (
                        ("tool_version", APPLY_AMENDMENT_TOOL_VERSION),
                        ("check", "amendment_transaction"),
                        ("invalidated_by", None),
                        ("result", expected_result)):
                    if receipt.get(field) != expected:
                        semantic_errors.append(field)
                for operation_field, receipt_field in (
                        ("task_id", "task_id"),
                        ("amendment_id", "amendment_id"),
                        ("plan_path", "plan_path"),
                        ("plan_sha256", "plan_sha256"),
                        ("coverage_proposal_path", "coverage_proposal_path"),
                        ("coverage_proposal_sha256",
                         "coverage_proposal_sha256"),
                        ("actor_role", "actor_role"),
                        ("transaction_sequence", "transaction_sequence"),
                        ("previous_transaction_commit_receipt",
                         "previous_transaction_commit_receipt"),
                        ("registration_receipt", "registration_receipt")):
                    if operation.get(operation_field) != receipt.get(receipt_field):
                        semantic_errors.append(operation_field)
                for state_name in tuple(sorted(
                        runtime_state_contract.RUNTIME_LEDGER_IDS)):
                    before = "before_%s_sha256" % state_name
                    planned = "planned_after_%s_sha256" % state_name
                    after = "after_%s_sha256" % state_name
                    if operation.get(before) != receipt.get(before):
                        semantic_errors.append(before)
                    if operation.get(planned) != receipt.get(after):
                        semantic_errors.append(planned)
                if operation.get("receipt_path") != relative:
                    semantic_errors.append("receipt_path")
                matches.append({
                    "receipt_id": receipt_id,
                    "path": relative,
                    "phase": phase,
                    "result": receipt.get("result"),
                    "semantic_match": not semantic_errors,
                    "semantic_mismatches": sorted(set(semantic_errors)),
                })
        matches.sort(key=lambda entry: (
            {"prepare": 0, "commit": 1, "abort": 2}[entry["phase"]],
            entry["receipt_id"],
        ))
        lock["transaction_receipts"] = matches
        expected_prepare = operation.get("prepare_receipt_id")
        lock["prepare_receipt_matches_owner"] = any(
            entry["phase"] == "prepare" and
            entry["receipt_id"] == expected_prepare and
            entry["semantic_match"] for entry in matches
        )
        phases = {entry["phase"] for entry in matches
                  if entry["semantic_match"]}
        mismatched_phases = {entry["phase"] for entry in matches
                             if not entry["semantic_match"]}
        if "abort" in phases:
            lock["transaction_phase"] = "abort"
        elif "commit" in phases:
            lock["transaction_phase"] = "commit"
        elif ("prepare" in phases and
              not lock["prepare_receipt_matches_owner"]):
            lock["transaction_phase"] = "prepare-receipt-mismatch"
        elif "prepare" in phases:
            lock["transaction_phase"] = "prepare"
        elif mismatched_phases:
            lock["transaction_phase"] = "receipt-semantic-mismatch"
        else:
            lock["transaction_phase"] = "prepare-receipt-missing"


def _operation_fingerprint(operation, names):
    """Return the one fingerprint owned by this operation-state position."""
    provided = [(name, operation.get(name)) for name in names
                if name in operation]
    if not provided:
        return None, None
    invalid = [name for name, value in provided
               if not isinstance(value, str) or not SHA256_RE.fullmatch(value)]
    if invalid:
        return None, "invalid fingerprint field(s): %s" % ", ".join(invalid)
    return provided[0][1], None


def _reconciliation_hint(phases):
    """Describe evidence only; never prescribe automatic lock recovery."""
    available = [entry for entry in phases.values()
                 if entry["phase"] != "unavailable"]
    if not available:
        return ("owner metadata has no comparable state fingerprints; "
                "manual reconciliation is required")
    phase_names = {entry["phase"] for entry in available}
    unavailable = any(entry["phase"] == "unavailable"
                      for entry in phases.values())
    if "other" in phase_names:
        return ("live state differs from recorded before/planned-after "
                "fingerprints; manual reconciliation is required")
    if phase_names == {"before", "planned-after"}:
        return ("live state mixes before and planned-after fingerprints; "
                "a partial write is possible and must be reconciled manually")
    if phase_names == {"planned-after"}:
        qualifier = "available " if unavailable else "all "
        return ("%sstate fingerprints match planned-after bytes; verify the "
                "matching receipt and semantic checks before treating the "
                "operation as complete" % qualifier)
    qualifier = "available " if unavailable else "all "
    return ("%sstate fingerprints match pre-write bytes; verify writer and "
            "receipt evidence before treating the lock as stale" % qualifier)


def bind_lock_state_phases(_writer_locks, live_shas):
    """Compare exact live state bytes with every interrupted writer plan."""
    for lock in _writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        phases = {}
        for state_name, field_names in LOCK_STATE_FINGERPRINTS.items():
            live = live_shas.get(state_name)
            before = None
            planned_after = None
            metadata_errors = []
            if isinstance(operation, dict):
                before, error = _operation_fingerprint(
                    operation, field_names["before"])
                if error:
                    metadata_errors.append(error)
                planned_after, error = _operation_fingerprint(
                    operation, field_names["planned_after"])
                if error:
                    metadata_errors.append(error)
            if (not isinstance(live, str) or
                    not SHA256_RE.fullmatch(live) or metadata_errors or
                    (before is None and planned_after is None)):
                phase = "unavailable"
            elif before is not None and live == before:
                # When before and after are byte-identical, use the
                # conservative pre-write interpretation and expose the
                # ambiguity explicitly.
                phase = "before"
            elif planned_after is not None and live == planned_after:
                phase = "planned-after"
            else:
                phase = "other"
            phases[state_name] = {
                "live_sha256": live,
                "before_sha256": before,
                "planned_after_sha256": planned_after,
                "phase": phase,
                "before_after_identical": (
                    before is not None and before == planned_after),
                "metadata_error": "; ".join(metadata_errors) or None,
            }
        lock["state_phases"] = phases
        lock["reconciliation_hint"] = _reconciliation_hint(phases)


def bind_lock_delta_archives(root, _writer_locks):
    """Locate and fingerprint a Delta moved by an interrupted Queue rollback.

    ``merge-ready -> open`` moves the rejected Delta before publishing the
    three canonical state files.  The writer lock therefore has to make that
    fourth filesystem effect independently observable after a hard exit.
    """
    for lock in _writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        if not isinstance(operation, dict) or \
                operation.get("tool") != "update_queue":
            continue
        source_relative = operation.get("delta_archive_source")
        archive_relative = operation.get("delta_archive_path")
        expected_sha = operation.get("delta_sha256")
        if source_relative is None and archive_relative is None and \
                expected_sha is None:
            continue
        evidence = {
            "delta_archive_source": source_relative,
            "delta_archive_path": archive_relative,
            "delta_sha256": expected_sha,
            "source_sha256": None,
            "archive_sha256": None,
            "status": "metadata-incomplete",
            "recovery_fact": "archive-state-undetermined",
            "hint": "manual reconciliation is required",
        }
        lock["delta_archive_recovery"] = evidence
        if (not nonempty_string(source_relative) or
                not nonempty_string(archive_relative) or
                not isinstance(expected_sha, str) or
                not SHA256_RE.fullmatch(expected_sha)):
            continue
        try:
            source = kblib.managed_repository_path(
                root, source_relative, runtime_paths.DELTA_ROOT,
                suffixes=(".yaml",), must_exist=False,
            )
            archive = kblib.managed_repository_path(
                root, archive_relative,
                runtime_paths.INVALIDATED_DELTA_RECEIPT_ROOT,
                suffixes=(".yaml",), must_exist=False,
            )
        except (OSError, ValueError) as exc:
            evidence["status"] = "unsafe-path"
            evidence["error"] = str(exc)
            continue

        source_exists = os.path.isfile(source) and not os.path.islink(source)
        archive_exists = os.path.isfile(archive) and not os.path.islink(archive)
        if source_exists:
            evidence["source_sha256"] = kblib.sha256_file(source)
        if archive_exists:
            evidence["archive_sha256"] = kblib.sha256_file(archive)
        if source_exists and archive_exists:
            evidence["status"] = "source-and-archive-present"
        elif not source_exists and not archive_exists:
            evidence["status"] = "source-and-archive-missing"
        elif source_exists:
            evidence["status"] = (
                "source-ready" if evidence["source_sha256"] == expected_sha
                else "source-sha-mismatch"
            )
        else:
            evidence["status"] = (
                "archived" if evidence["archive_sha256"] == expected_sha
                else "archive-sha-mismatch"
            )

        phases = lock.get("state_phases") or {}
        all_state_before = all(
            (phases.get(name) or {}).get("phase") == "before"
            for name in runtime_state_contract.RUNTIME_LEDGER_IDS
        )
        if all_state_before and evidence["status"] == "archived":
            evidence["recovery_fact"] = "archive-moved-state-before"
            evidence["hint"] = (
                "the Delta bytes match the declared archive while all three "
                "state files remain at their pre-transition fingerprints; "
                "restore the archive to its declared source before retrying"
            )
        elif all_state_before and evidence["status"] == "source-ready":
            evidence["recovery_fact"] = "archive-not-moved-state-before"
            evidence["hint"] = (
                "the Delta remains at its declared source and all three state "
                "files remain at their pre-transition fingerprints"
            )
        elif evidence["status"] in (
                "archive-sha-mismatch", "source-sha-mismatch",
                "source-and-archive-present", "source-and-archive-missing"):
            evidence["recovery_fact"] = "archive-state-conflict"
            evidence["hint"] = (
                "Delta location or bytes conflict with writer-lock metadata; "
                "manual reconciliation is required"
            )


def bind_generic_lock_receipts(root, _writer_locks, catalog):
    """Bind non-Amendment writer intent to its exact declared JSONL receipt."""
    for lock in _writer_locks:
        owner = lock.get("owner")
        operation = owner.get("operation") if isinstance(owner, dict) else None
        if not isinstance(operation, dict) or operation.get("tool") not in \
                GENERIC_WRITER_TOOLS:
            continue
        receipt_id = operation.get("receipt_id")
        receipt_path = operation.get("receipt_path")
        evidence = {
            "receipt_id": receipt_id,
            "receipt_path": receipt_path,
            "status": "metadata-incomplete",
            "matching_receipt": False,
            "result": None,
        }
        lock["operation_receipt"] = evidence
        repository_snapshot_errors = []
        if operation.get("tool") == BATCH_CLOSE_TOOL:
            expected_snapshot = operation.get("repository_snapshot_sha256")
            snapshot_binding = {
                "expected_sha256": expected_snapshot,
                "current_sha256": None,
                "status": "metadata-invalid",
                "error": None,
            }
            evidence["repository_snapshot"] = snapshot_binding
            if (not isinstance(expected_snapshot, str) or
                    not SHA256_RE.fullmatch(expected_snapshot)):
                repository_snapshot_errors.append(
                    "repository_snapshot_sha256")
            else:
                try:
                    current_snapshot = kblib.repository_snapshot_sha256(root)
                except (OSError, ValueError) as exc:
                    snapshot_binding["status"] = "unavailable"
                    snapshot_binding["error"] = str(exc)
                    repository_snapshot_errors.append(
                        "current_repository_snapshot_sha256")
                else:
                    snapshot_binding["current_sha256"] = current_snapshot
                    if current_snapshot == expected_snapshot:
                        snapshot_binding["status"] = "matching"
                    else:
                        snapshot_binding["status"] = "changed"
                        repository_snapshot_errors.append(
                            "current_repository_snapshot_sha256")
        if not nonempty_string(receipt_id) or not nonempty_string(receipt_path):
            continue
        try:
            declared = kblib.managed_repository_path(
                root, receipt_path, runtime_paths.RECEIPT_ROOT,
                suffixes=(".jsonl",), must_exist=False,
            )
            declared_relative = os.path.relpath(declared, root)
        except (OSError, ValueError) as exc:
            evidence["status"] = "unsafe-path"
            evidence["error"] = str(exc)
            continue
        entry = catalog.get(receipt_id)
        if entry is None:
            evidence["status"] = "absent"
            continue
        actual_relative, receipt = entry
        if actual_relative != declared_relative:
            evidence["status"] = "path-mismatch"
            evidence["actual_path"] = actual_relative
            evidence["result"] = receipt.get("result")
            continue
        semantic_errors = []
        if receipt.get("tool") != operation.get("tool"):
            semantic_errors.append("tool")
        if (nonempty_string(operation.get("task_id")) and
                receipt.get("task_id") != operation.get("task_id")):
            semantic_errors.append("task_id")
        expected_target = operation.get("target") or operation.get("batch_id")
        if (nonempty_string(expected_target) and
                receipt.get("target") != expected_target):
            semantic_errors.append("target")
        receipt_queue_before, receipt_queue_after = \
            GENERIC_RECEIPT_QUEUE_FIELDS[operation.get("tool")]
        field_pairs = [
            ("before_coverage_sha256", "before_coverage_sha256"),
            ("planned_after_coverage_sha256", "after_coverage_sha256"),
            ("before_progress_sha256", "before_progress_sha256"),
            ("planned_after_progress_sha256", "after_progress_sha256"),
        ]
        if receipt_queue_before is not None:
            field_pairs.append(("before_queue_sha256", receipt_queue_before))
        if receipt_queue_after is not None:
            field_pairs.append(
                ("planned_after_queue_sha256", receipt_queue_after))
        for operation_field, receipt_field in field_pairs:
            expected_value = operation.get(operation_field)
            if expected_value is None:
                continue
            if receipt.get(receipt_field) != expected_value:
                semantic_errors.append(operation_field)
        if operation.get("tool") == REGISTER_AMENDMENT_TOOL:
            for field, expected_value in (
                    ("tool_version", REGISTER_AMENDMENT_TOOL_VERSION),
                    ("check", "amendment_withdrawal"
                     if operation.get("action") == "withdraw"
                     else "amendment_registration"),
                    ("result", "pass"),
                    ("invalidated_by", None),
                    ("actor_role", "integrator"),
                    ("amendment_id", operation.get("amendment_id")),
                    ("operation", operation.get("amendment_operation"))):
                if receipt.get(field) != expected_value:
                    semantic_errors.append(field)
            if operation.get("registration_receipt") != receipt_id:
                semantic_errors.append("registration_receipt")
        if operation.get("tool") == "apply_delta":
            if receipt.get("check") != "delta_apply":
                semantic_errors.append("check")
            if receipt.get("batch_id") != operation.get("batch_id"):
                semantic_errors.append("batch_id")
            if receipt.get("delta_sha256") != operation.get("delta_sha256"):
                semantic_errors.append("delta_sha256")
        if operation.get("tool") == BATCH_CLOSE_TOOL:
            if receipt.get("tool_version") != operation.get("tool_version"):
                semantic_errors.append("tool_version")
            if receipt.get("check") != "batch_close_gate":
                semantic_errors.append("check")
            if receipt.get("batch_id") != operation.get("batch_id"):
                semantic_errors.append("batch_id")
            if receipt.get("merged_snapshot_sha256") != operation.get(
                    "repository_snapshot_sha256"):
                semantic_errors.append("merged_snapshot_sha256")
            if receipt.get("result") not in ("pass", "fail"):
                semantic_errors.append("result")
            semantic_errors.extend(repository_snapshot_errors)
        if semantic_errors:
            evidence["status"] = "semantic-mismatch"
            evidence["mismatched_fields"] = sorted(set(semantic_errors))
            evidence["result"] = receipt.get("result")
            continue
        evidence["status"] = "matching"
        evidence["matching_receipt"] = True
        evidence["result"] = receipt.get("result")
