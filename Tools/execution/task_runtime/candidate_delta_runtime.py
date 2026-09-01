"""Publish one Agent-complete Coverage Delta as the open batch candidate.

This application layer owns no Coverage rule and no lifecycle transition.  It
combines the existing Coverage Delta policy, Queue handoff contract, repository
path boundary, and canonical serializer into the single producer that was
previously missing.  The only authoritative byte it may change is the derived
open-batch candidate at ``.cambium/deltas/<batch>.yaml``.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import argparse
import fcntl
import json
import os

import Tools.platform.common.kblib as kblib
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_validation as runtime_validation


TOOL = "publish_delta"


class CandidateDeltaError(ValueError):
    """A fail-closed refusal to plan or publish a candidate Delta."""

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = tuple(str(error) for error in errors if str(error))
        super().__init__("; ".join(self.errors) or
                         "candidate Delta publication refused")


@dataclass(frozen=True)
class _PublicationPlan:
    root: str
    batch_id: str
    proposal_path: str
    expected_delta_sha256: str
    delta_path: str
    canonical_text: str
    delta_sha256: str
    previous_delta_sha256: object
    action: str
    queue_sha256: str
    coverage_sha256: str
    progress_sha256: str
    manifest: tuple


def _canonical_root(root):
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if not os.path.isdir(root):
        raise CandidateDeltaError("repository root must be an existing directory")
    return root


def _expected_sha(value):
    if value == "absent":
        return value
    if not isinstance(value, str) or not queue_runtime.SHA256_RE.fullmatch(
            value):
        raise CandidateDeltaError(
            "expected Delta identity must be 'absent' or a canonical sha256")
    return value


def _proposal_snapshot(root, relative):
    if not isinstance(relative, str) or not relative:
        raise CandidateDeltaError("proposal path must be a non-empty string")
    try:
        kblib.managed_repository_path(
            root, relative, runtime_paths.TRANSIENT_ROOT,
            suffixes=(".yaml",), must_exist=True,
        )
        snapshot = kblib.repository_target_snapshot(
            root, relative, suffixes=(".yaml",), singly_linked=True)
        if not snapshot.exists:
            raise ValueError("proposal does not exist")
        document = kblib.parse_yaml_subset(snapshot.read_text())
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        raise CandidateDeltaError("unsafe or unreadable proposal: %s" % exc) \
            from exc
    if not isinstance(document, dict):
        raise CandidateDeltaError("proposal top-level value must be a mapping")
    try:
        canonical_text = kblib.canonical_yaml(document)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        raise CandidateDeltaError(
            "proposal cannot be canonically serialized: %s" % exc) from exc
    return document, canonical_text


def _coverage_records(result):
    records = {}
    for record in (result.get("coverage") or {}).get("pages") or []:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        if isinstance(path, str) and path:
            records[path] = record
    return records


def _runtime_and_item(root, batch_id):
    result = runtime_validation.validate_runtime(root)
    errors = list(result.get("errors") or [])
    if errors:
        raise CandidateDeltaError([
            "runtime is not admitted: %s" % error for error in errors[:12]
        ])
    if result.get("_writer_locks"):
        raise CandidateDeltaError(
            "runtime has an active or interrupted authoritative writer")
    if (result.get("progress") or {}).get("task_state") != "active":
        raise CandidateDeltaError(
            "candidate Delta publication requires task_state=active")
    item = (result.get("items_by_id") or {}).get(batch_id)
    if not isinstance(item, dict):
        raise CandidateDeltaError("unknown Queue batch %s" % batch_id)
    if item.get("state") != "open":
        raise CandidateDeltaError(
            "Queue batch %s must be open, found %r" %
            (batch_id, item.get("state")))
    if item.get("hold_state") != "none":
        raise CandidateDeltaError(
            "Queue batch %s must not be held, found %r" %
            (batch_id, item.get("hold_state")))
    manifest = item.get("manifest")
    if (not isinstance(manifest, list) or not manifest or
            len(manifest) != len(set(manifest)) or
            any(not isinstance(path, str) or not path for path in manifest)):
        raise CandidateDeltaError(
            "Queue batch %s has no valid frozen manifest" % batch_id)
    return result, item, tuple(manifest)


def _handoff_errors(delta, relative, result, item):
    errors, settlement, _report = queue_runtime.delta.delta_handoff_errors(
        relative,
        delta,
        item,
        _coverage_records(result),
        result["coverage"],
        result["queue"],
        queue_runtime.current_receipt_catalog(result),
    )
    errors.extend(settlement)
    return list(dict.fromkeys(errors))


def _target_snapshot(root, relative):
    try:
        kblib.managed_repository_path(
            root, relative, runtime_paths.DELTA_ROOT,
            suffixes=(".yaml",), must_exist=False,
        )
        return kblib.repository_target_snapshot(
            root, relative, suffixes=(".yaml",), singly_linked=True)
    except (OSError, ValueError) as exc:
        raise CandidateDeltaError(
            "unsafe canonical Delta target: %s" % exc) from exc


def _plan(root, batch_id, proposal_path, expected_delta_sha256):
    root = _canonical_root(root)
    if (not isinstance(batch_id, str) or
            not queue_runtime.BATCH_ID_RE.fullmatch(batch_id)):
        raise CandidateDeltaError("batch must be a canonical Queue batch id")
    expected_delta_sha256 = _expected_sha(expected_delta_sha256)
    delta_path = runtime_paths.child_path(
        runtime_paths.DELTA_ROOT, "%s.yaml" % batch_id)
    proposal, canonical_text = _proposal_snapshot(root, proposal_path)
    result, item, manifest = _runtime_and_item(root, batch_id)
    errors = _handoff_errors(proposal, delta_path, result, item)
    if errors:
        raise CandidateDeltaError([
            "proposal is not an admissible complete handoff: %s" % error
            for error in errors
        ])

    target = _target_snapshot(root, delta_path)
    delta_sha256 = kblib.sha256_bytes(canonical_text)
    previous = target.sha256 if target.exists else None
    same_bytes = target.exists and target.data == canonical_text.encode("utf-8")
    if same_bytes:
        if expected_delta_sha256 not in ("absent", previous):
            raise CandidateDeltaError(
                "expected Delta sha256 does not match the current candidate")
        action = "none"
    elif target.exists:
        if expected_delta_sha256 == "absent":
            raise CandidateDeltaError(
                "canonical Delta already exists with different bytes")
        if expected_delta_sha256 != previous:
            raise CandidateDeltaError(
                "expected Delta sha256 does not match the current candidate")
        action = "replace"
    else:
        if expected_delta_sha256 != "absent":
            raise CandidateDeltaError(
                "canonical Delta is absent but a previous sha256 was required")
        action = "create"

    return _PublicationPlan(
        root=root,
        batch_id=batch_id,
        proposal_path=proposal_path,
        expected_delta_sha256=expected_delta_sha256,
        delta_path=delta_path,
        canonical_text=canonical_text,
        delta_sha256=delta_sha256,
        previous_delta_sha256=previous,
        action=action,
        queue_sha256=result["queue_sha256"],
        coverage_sha256=result["coverage_sha256"],
        progress_sha256=result["progress_sha256"],
        manifest=manifest,
    )


def _public_result(plan, *, applied, status):
    return {
        "applied": applied,
        "status": status,
        "batch_id": plan.batch_id,
        "proposal_path": plan.proposal_path,
        "delta_path": plan.delta_path,
        "delta_sha256": plan.delta_sha256,
        "previous_delta_sha256": plan.previous_delta_sha256,
    }


@contextmanager
def _candidate_namespace_lock(root):
    """Serialize cooperating candidate publishers without runtime state."""
    directory = os.path.join(root, runtime_paths.DELTA_ROOT)
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
             getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_CLOEXEC", 0))
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        raise CandidateDeltaError(
            "canonical Delta namespace is unavailable: %s" % exc) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _remove_and_sync(path):
    os.unlink(path)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(os.path.dirname(path), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rollback(plan, before):
    """Restore the one candidate byte target after a failed publication."""
    current = _target_snapshot(plan.root, plan.delta_path)
    if before.exists:
        if current.exists and current.data == before.data:
            return
        if (not current.exists or
                current.data != plan.canonical_text.encode("utf-8")):
            raise CandidateDeltaError(
                "candidate rollback refused because target bytes changed")
        kblib.atomic_write_text(
            current.path, before.read_text(), validator=kblib.parse_yaml_subset)
        restored = _target_snapshot(plan.root, plan.delta_path)
        if not restored.exists or restored.data != before.data:
            raise CandidateDeltaError(
                "candidate rollback could not prove the original bytes")
    else:
        if not current.exists:
            return
        if current.data != plan.canonical_text.encode("utf-8"):
            raise CandidateDeltaError(
                "candidate rollback refused because target bytes changed")
        _remove_and_sync(current.path)
        if _target_snapshot(plan.root, plan.delta_path).exists:
            raise CandidateDeltaError(
                "candidate rollback could not prove target absence")


def _post_publish_errors(plan):
    result = runtime_validation.validate_runtime(plan.root)
    errors = list(result.get("errors") or [])
    if result.get("queue_sha256") != plan.queue_sha256:
        errors.append("Required Queue changed during candidate publication")
    if result.get("coverage_sha256") != plan.coverage_sha256:
        errors.append("Coverage changed during candidate publication")
    if result.get("progress_sha256") != plan.progress_sha256:
        errors.append("Progress changed during candidate publication")
    item = (result.get("items_by_id") or {}).get(plan.batch_id)
    if (not isinstance(item, dict) or item.get("state") != "open" or
            tuple(item.get("manifest") or ()) != plan.manifest):
        errors.append("open batch or frozen manifest changed during publication")
    records = [
        record for record in result.get("managed_deltas") or []
        if record.get("path") == plan.delta_path
    ]
    if (len(records) != 1 or
            records[0].get("sha256") != plan.delta_sha256 or
            records[0].get("handoff_status") != "candidate"):
        errors.append(
            "published bytes were not read back as the unique candidate")
    return list(dict.fromkeys(errors))


def plan_candidate_delta(root, *, batch_id, proposal_path,
                         expected_delta_sha256):
    """Validate a complete proposal and return its no-write publication plan."""
    plan = _plan(root, batch_id, proposal_path, expected_delta_sha256)
    status = "already-present" if plan.action == "none" else "planned"
    return _public_result(plan, applied=False, status=status)


def publish_candidate_delta(root, *, batch_id, proposal_path,
                            expected_delta_sha256):
    """CAS-publish and byte-read-back one canonical candidate Delta."""
    root = _canonical_root(root)
    with _candidate_namespace_lock(root):
        plan = _plan(
            root, batch_id, proposal_path, expected_delta_sha256)
        if plan.action == "none":
            return _public_result(
                plan, applied=True, status="already-present")
        before = _target_snapshot(plan.root, plan.delta_path)
        write_attempted = False
        try:
            write_attempted = True
            kblib.atomic_write_text(
                before.path,
                plan.canonical_text,
                validator=kblib.parse_yaml_subset,
            )
            read_back = _target_snapshot(plan.root, plan.delta_path)
            if (not read_back.exists or
                    read_back.data != plan.canonical_text.encode("utf-8") or
                    read_back.sha256 != plan.delta_sha256):
                raise CandidateDeltaError(
                    "canonical Delta byte read-back did not match publication")
            errors = _post_publish_errors(plan)
            if errors:
                raise CandidateDeltaError([
                    "post-publication validation: %s" % error
                    for error in errors[:12]
                ])
        except BaseException as exc:
            if write_attempted:
                try:
                    _rollback(plan, before)
                except BaseException as rollback_exc:
                    raise CandidateDeltaError(
                        "candidate publication failed (%s) and rollback "
                        "failed (%s)" % (exc, rollback_exc)) from rollback_exc
            raise
        return _public_result(plan, applied=True, status="published")


def main(argv=None):
    """Plan or publish one complete candidate Coverage Delta."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate an Agent-complete proposal and publish it to the "
            "canonical candidate Delta path for one current open batch."))
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True,
                        help="current open Queue batch id")
    parser.add_argument(
        "--proposal", required=True,
        help=("complete YAML proposal below %s/" %
              runtime_paths.TRANSIENT_ROOT))
    parser.add_argument(
        "--expected-delta-sha256", required=True,
        help="'absent' for first publication or the current canonical sha256")
    parser.add_argument("--apply", action="store_true",
                        help="publish after successful validation")
    args = parser.parse_args(argv)

    try:
        if args.apply:
            result = publish_candidate_delta(
                args.root,
                batch_id=args.batch,
                proposal_path=args.proposal,
                expected_delta_sha256=args.expected_delta_sha256,
            )
        else:
            result = plan_candidate_delta(
                args.root,
                batch_id=args.batch,
                proposal_path=args.proposal,
                expected_delta_sha256=args.expected_delta_sha256,
            )
    except CandidateDeltaError as exc:
        result = {"applied": False, "status": "invalid",
                  "errors": list(exc.errors)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"applied": False, "status": "invalid",
                  "errors": [str(exc)]}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    'main',
]
