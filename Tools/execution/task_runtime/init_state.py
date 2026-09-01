#!/usr/bin/env python3
"""Publish one confirmed Task Plan into an absent task-runtime namespace.

Planning semantics live in :mod:`Tools.execution.planning.apply_task_plan`.
This module owns only staging, the writer lock, atomic no-replace publication,
rollback, and the single public ``init_state --plan`` interface.
"""

import ctypes
import errno
import json
import os
import shlex
import shutil
import sys
import tempfile
import time

from Tools.execution.task_runtime import queue_runtime
import Tools.platform.common.kblib as kblib
import Tools.execution.planning.apply_task_plan as task_plan
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.common import reporting

TOOL = "init_state"
TOOL_VERSION = "2.0.0"
RUNTIME_DIRS = runtime_paths.TASK_RUNTIME_DIRECTORIES

_STATE_DOCUMENT_PATH_BY_NAME = {
    os.path.basename(path): path
    for path in (
        runtime_paths.COVERAGE_PATH,
        runtime_paths.QUEUE_PATH,
        runtime_paths.PROGRESS_PATH,
    )
}
_STATE_DOCUMENT_NAMES = frozenset(_STATE_DOCUMENT_PATH_BY_NAME)
_QUEUE_DOCUMENT_NAME = os.path.basename(runtime_paths.QUEUE_PATH)

JSON_HELP = reporting.JSON_RECEIPT_HELP
_JSON_REPORTER = reporting.JsonReceiptCollector()


def _runtime_namespace_path(runtime, repository_path):
    """Map a registered ``.cambium`` path into a staged/runtime root."""
    prefix = runtime_paths.RUNTIME_ROOT + "/"
    if (not isinstance(repository_path, str) or
            not repository_path.startswith(prefix)):
        raise ValueError(
            "runtime namespace projection requires a path below %s" %
            runtime_paths.RUNTIME_ROOT)
    relative = repository_path[len(prefix):]
    return os.path.join(runtime, *relative.split("/"))


def _runtime_relative_path(repository_path):
    """Return one registered runtime path relative to ``.cambium``."""
    projected = _runtime_namespace_path("", repository_path)
    return projected.lstrip(os.sep)


def _rename_noreplace(source, destination):
    """Atomically rename ``source`` only when ``destination`` is absent.

    Plain POSIX ``rename`` may replace an existing empty directory on macOS,
    so an existence check followed by ``os.rename`` is not a safe publication
    primitive.  Use the platform's atomic exclusion flag instead.  Unsupported
    platforms fail closed before publishing any public runtime namespace.
    """
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)

    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renameatx_np = getattr(libc, "renameatx_np", None)
        if renameatx_np is None:
            raise OSError(
                errno.ENOTSUP,
                "atomic no-replace directory publication is unavailable",
                destination,
            )
        renameatx_np.argtypes = (
            ctypes.c_int, ctypes.c_char_p,
            ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        )
        renameatx_np.restype = ctypes.c_int
        at_fdcwd = -2
        rename_excl = 0x00000004
        result = renameatx_np(
            at_fdcwd, source_bytes, at_fdcwd, destination_bytes,
            rename_excl,
        )
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise OSError(
                errno.ENOTSUP,
                "atomic no-replace directory publication is unavailable",
                destination,
            )
        renameat2.argtypes = (
            ctypes.c_int, ctypes.c_char_p,
            ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        at_fdcwd = -100
        rename_noreplace = 1
        result = renameat2(
            at_fdcwd, source_bytes, at_fdcwd, destination_bytes,
            rename_noreplace,
        )
    elif os.name == "nt":
        # Windows rename already refuses an existing destination.  The
        # operation is still one filesystem rename, not check-then-replace.
        os.rename(source, destination)
        return
    else:
        raise OSError(
            errno.ENOTSUP,
            "atomic no-replace directory publication is unavailable",
            destination,
        )

    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), destination)


def _existing_runtime_summary(root):
    """Return a best-effort, read-only summary of an existing runtime.

    Every path still passes the managed-path checks.  An unreadable or partial
    namespace is reported as such rather than guessed from loose files.
    """
    try:
        queue_path = kblib.managed_repository_path(
            root, runtime_paths.QUEUE_PATH,
            runtime_paths.roots_for(runtime_paths.CANONICAL_STATE)[1],
            suffixes=(".yaml",), must_exist=True,
        )
        progress_path = kblib.managed_repository_path(
            root, runtime_paths.PROGRESS_PATH,
            runtime_paths.roots_for(runtime_paths.CANONICAL_STATE)[1],
            suffixes=(".yaml",), must_exist=True,
        )
        coverage_path = kblib.managed_repository_path(
            root, runtime_paths.COVERAGE_PATH,
            runtime_paths.roots_for(runtime_paths.CANONICAL_STATE)[1],
            suffixes=(".yaml",), must_exist=True,
        )
        queue = kblib.load_yaml_file(queue_path)
        progress = kblib.load_yaml_file(progress_path)
        coverage = kblib.load_yaml_file(coverage_path)
        with open(queue_path, "rb") as fh:
            queue_raw = fh.read()
        queue_sha = kblib.sha256_bytes(queue_raw)
        contract = progress.get("contract")
        if not isinstance(contract, dict):
            raise ValueError("Progress contract is not a mapping")
        for field in runtime_state_contract.RUNTIME_CONTROL_IDENTITY_FIELDS:
            progress_value = (progress.get(field) if field == "task_id" else
                              contract.get(field))
            values = (queue.get(field), coverage.get(field), progress_value)
            if values[0] != values[1] or values[0] != values[2]:
                raise ValueError("%s differs across Queue/Coverage/Progress" % field)
        if progress.get("queue_revision") != queue.get("queue_revision"):
            raise ValueError("Progress queue_revision does not match Queue")
        if progress.get("queue_state_revision") != queue.get("state_revision"):
            raise ValueError("Progress queue_state_revision does not match Queue")
        if progress.get("required_queue_sha256") != queue_sha:
            raise ValueError("Progress Queue fingerprint does not match Queue bytes")
        return {
            "task_id": queue.get("task_id"),
            "task_state": progress.get("task_state"),
            "completion_semantics": contract.get("completion_semantics"),
            "objective": contract.get("objective"),
            "exclusions": contract.get("exclusions"),
            "queue_revision": queue.get("queue_revision"),
            "state_revision": queue.get("state_revision"),
            "required_queue_sha256": queue_sha,
        }, None
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        return None, str(exc)


def _report_existing_runtime(root, reason):
    print("[FAIL] %s; nothing was overwritten" % reason)
    summary, summary_error = _existing_runtime_summary(root)
    if summary is not None:
        print("existing_runtime:")
        for field in ("task_id", "task_state", "completion_semantics",
                      "objective", "exclusions",
                      "queue_revision",
                      "state_revision", "required_queue_sha256"):
            print("  %s=%s" % (field, summary.get(field)))
    else:
        print("existing_runtime_summary=unavailable (%s)" % summary_error)
    print("inspect before continuing:")
    print("  python3 Tools/check_queue.py %s --resume-status" %
          shlex.quote(root))


def _fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_publication_lock(staging, operation):
    """Place a cooperating-writer lock inside a not-yet-public runtime."""
    if not isinstance(operation, dict):
        raise ValueError("initialization lock operation must be a mapping")
    lock_path = _runtime_namespace_path(
        staging, runtime_paths.STATE_WRITER_LOCK_PATH)
    os.mkdir(lock_path, 0o700)
    owner_path = _runtime_namespace_path(
        staging, runtime_paths.STATE_WRITER_OWNER_PATH)
    owner = {
        "lock_name": "state-writer",
        "pid": os.getpid(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "operation": json.loads(json.dumps(operation)),
    }
    with open(owner_path, "x", encoding="utf-8") as handle:
        json.dump(owner, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(lock_path)
    _fsync_directory(os.path.dirname(lock_path))
    return lock_path


def _publication_lock_paths(runtime, expected_operation):
    """Return the lock paths only when its full operation still matches."""
    lock_path = _runtime_namespace_path(
        runtime, runtime_paths.STATE_WRITER_LOCK_PATH)
    owner_path = _runtime_namespace_path(
        runtime, runtime_paths.STATE_WRITER_OWNER_PATH)
    names = sorted(os.listdir(lock_path))
    expected_names = [os.path.basename(runtime_paths.STATE_WRITER_OWNER_PATH)]
    if names != expected_names:
        raise ValueError(
            "initialization lock changed before release: %s" % names)
    owner_stat = os.lstat(owner_path)
    if (os.path.islink(owner_path) or not os.path.isfile(owner_path) or
            owner_stat.st_nlink != 1):
        raise ValueError(
            "initialization lock owner must remain a singly-linked regular "
            "file")
    with open(owner_path, encoding="utf-8") as handle:
        owner = json.load(handle)
    operation = owner.get("operation") if isinstance(owner, dict) else None
    expected_operation = json.loads(json.dumps(expected_operation))
    if operation != expected_operation:
        raise ValueError("initialization lock ownership changed before release")
    return lock_path, owner_path


def _remove_publication_lock(runtime, expected_operation):
    """Release only the exact staged initialization lock."""
    lock_path, owner_path = _publication_lock_paths(
        runtime, expected_operation)
    os.unlink(owner_path)
    os.rmdir(lock_path)
    _fsync_directory(_runtime_namespace_path(
        runtime, runtime_paths.TRANSIENT_ROOT))


def _stage_evidence_files(staging, evidence_files):
    """Write exact immutable evidence bytes into the staged runtime tree."""
    evidence_files = evidence_files or {}
    for repository_path, raw in sorted(evidence_files.items()):
        if (not isinstance(repository_path, str) or
                not repository_path.startswith(runtime_paths.RECEIPT_ROOT + "/")
                or not repository_path.endswith(".jsonl")):
            raise ValueError(
                "initialization evidence must be a registered Receipt JSONL")
        if not isinstance(raw, bytes):
            raise TypeError("initialization evidence must be exact bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("initialization evidence is not UTF-8") from exc
        target = _runtime_namespace_path(staging, repository_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        kblib.atomic_write_text(target, text)
        with open(target, "rb") as handle:
            if handle.read() != raw:
                raise ValueError(
                    "staged initialization evidence changed bytes")


def publish_runtime(root, documents, *, evidence_files=None,
                    pre_publish_validator=None,
                    post_publish_validator=None, lock_operation=None):
    """Build a complete sibling tree, then atomically publish ``.cambium``.

    The public target is never created until every directory and state file has
    been written and reparsed.  Competing initializers may each stage a tree,
    but one atomic no-replace rename can publish; every losing/failed staging
    tree is removed.  Any pre-existing ``.cambium`` -- including an empty
    directory created between the initial check and publication -- is an
    explicit refusal rather than an overwrite target.

    When validators are supplied, the staged tree carries the shared writer
    lock across publication.  The pre-validator runs immediately before the
    no-replace rename and the post-validator runs after it while every
    cooperating runtime writer is excluded.  A failed post-validator moves
    the still-locked namespace back out with an atomic no-replace rename; if
    that rollback cannot be proved, the public lock remains for operator
    reconciliation rather than exposing an apparently usable partial state.
    """
    validators = (pre_publish_validator, post_publish_validator)
    if any(value is not None for value in validators):
        if not all(callable(value) for value in validators):
            raise ValueError(
                "pre/post publication validators must be supplied together")
        if not isinstance(lock_operation, dict):
            raise ValueError(
                "validated publication requires lock_operation metadata")
    elif lock_operation is not None:
        raise ValueError("lock_operation requires publication validators")
    runtime = os.path.join(root, runtime_paths.RUNTIME_ROOT)
    if os.path.lexists(runtime):
        raise FileExistsError(
            "%s already exists; refusing to overwrite even an empty namespace"
            % runtime_paths.RUNTIME_ROOT
        )
    if set(documents) != _STATE_DOCUMENT_NAMES:
        raise ValueError("runtime initialization requires exactly the three state files")

    staging = tempfile.mkdtemp(
        prefix=runtime_paths.RUNTIME_ROOT + "-init-", dir=root)
    published = False
    try:
        for directory in RUNTIME_DIRS:
            os.makedirs(os.path.join(staging, directory), exist_ok=False)
        for name, text in documents.items():
            target = _runtime_namespace_path(
                staging, _STATE_DOCUMENT_PATH_BY_NAME[name])
            kblib.atomic_write_text(
                target, text, validator=kblib.parse_yaml_subset
            )
            with open(target, encoding="utf-8") as fh:
                reparsed = kblib.parse_yaml_subset(fh.read())
            if not isinstance(reparsed, dict):
                raise kblib.YamlSubsetError(
                    "staged state file is not a mapping: %s" % name
                )
        _stage_evidence_files(staging, evidence_files)
        if pre_publish_validator is not None:
            pre_publish_validator()
            _create_publication_lock(staging, lock_operation)
        _rename_noreplace(staging, runtime)
        _fsync_directory(root)
        if post_publish_validator is not None:
            try:
                post_publish_validator()
            except BaseException as validation_error:
                try:
                    # Moving a public namespace back out is safe only while
                    # this exact initialization operation still owns the lock.
                    _publication_lock_paths(runtime, lock_operation)
                    _rename_noreplace(runtime, staging)
                    _fsync_directory(root)
                except BaseException as rollback_error:
                    raise ValueError(
                        "runtime publication validation failed and atomic "
                        "rollback is incomplete: validation=%s; rollback=%s" %
                        (validation_error, rollback_error)) from validation_error
                raise
            _remove_publication_lock(runtime, lock_operation)
        published = True
    finally:
        # ``staging`` exists before publication and after a successful atomic
        # rollback.  If the public rename succeeded but later recovery could
        # not be proved, it is absent and the locked public runtime is kept.
        if not published and os.path.lexists(staging):
            shutil.rmtree(staging)


def _governance_only_namespace_errors(root, *, allowed_plan_path=None):
    """Return errors when an existing namespace is not pre-runtime state."""
    runtime = os.path.join(root, runtime_paths.RUNTIME_ROOT)
    if not os.path.lexists(runtime):
        return []
    if os.path.islink(runtime) or not os.path.isdir(runtime):
        return ["%s must be a real directory" % runtime_paths.RUNTIME_ROOT]
    allowed_files = set(
        os.path.normpath(_runtime_relative_path(path))
        for path in runtime_paths.PRE_TASK_FILE_PATHS
    )
    if allowed_plan_path is not None:
        prefix = runtime_paths.TASK_PLAN_DELTA_ROOT + "/"
        if (not isinstance(allowed_plan_path, str) or
                not allowed_plan_path.startswith(prefix) or
                not allowed_plan_path.endswith(".yaml")):
            return ["confirmed Task Plan must stay below %s/" %
                    runtime_paths.TASK_PLAN_DELTA_ROOT]
        allowed_files.add(os.path.normpath(
            _runtime_relative_path(allowed_plan_path)))
    allowed_files = frozenset(allowed_files)
    required_files = frozenset(
        os.path.normpath(_runtime_relative_path(path))
        for path in runtime_paths.PRE_TASK_REQUIRED_FILE_PATHS
    )
    allowed_directories = set()
    for relative in allowed_files:
        parent = os.path.dirname(relative)
        while parent:
            allowed_directories.add(parent)
            parent = os.path.dirname(parent)

    errors = []
    for relative in sorted(required_files):
        target = os.path.join(runtime, *relative.split(os.sep))
        if os.path.islink(target) or not os.path.isfile(target):
            errors.append("pre-runtime %s must contain regular file %s" % (
                runtime_paths.RUNTIME_ROOT, relative.replace(os.sep, "/")))

    def record_walk_error(error):
        filename = getattr(error, "filename", None) or runtime
        try:
            relative = os.path.relpath(filename, runtime)
        except (TypeError, ValueError):
            relative = str(filename)
        if relative == ".":
            relative = ""
        display = relative.replace(os.sep, "/")
        errors.append("pre-runtime %s cannot inspect %s: %s" % (
            runtime_paths.RUNTIME_ROOT,
            display or runtime_paths.RUNTIME_ROOT,
            error,
        ))

    for current, directories, files in os.walk(
            runtime, topdown=True, onerror=record_walk_error,
            followlinks=False):
        current_relative = os.path.relpath(current, runtime)
        if current_relative == ".":
            current_relative = ""

        traversable = []
        for name in sorted(directories):
            path = os.path.join(current, name)
            relative = os.path.normpath(os.path.join(current_relative, name))
            display = relative.replace(os.sep, "/")
            if os.path.islink(path) or not os.path.isdir(path):
                errors.append("pre-runtime %s/%s must be a real directory" %
                              (runtime_paths.RUNTIME_ROOT, display))
            elif relative not in allowed_directories:
                errors.append("pre-runtime %s contains unregistered path %s" %
                              (runtime_paths.RUNTIME_ROOT, display))
            else:
                traversable.append(name)
        directories[:] = traversable

        for name in sorted(files):
            path = os.path.join(current, name)
            relative = os.path.normpath(os.path.join(current_relative, name))
            display = relative.replace(os.sep, "/")
            if os.path.islink(path) or not os.path.isfile(path):
                errors.append("pre-runtime %s/%s must be a regular file" %
                              (runtime_paths.RUNTIME_ROOT, display))
            elif relative not in allowed_files:
                errors.append("pre-runtime %s contains unregistered path %s" %
                              (runtime_paths.RUNTIME_ROOT, display))
    return errors


def _task_runtime_publication_roots():
    """Return the registered task roots with the lock namespace first."""
    return (runtime_paths.TRANSIENT_ROOT,) + tuple(
        path for path in runtime_paths.TASK_RUNTIME_ROOTS
        if path != runtime_paths.TRANSIENT_ROOT
    )


def publish_runtime_into_governance_namespace(
        root, documents, *, pre_publish_validator,
        post_publish_validator, lock_operation, evidence_files=None,
        allowed_plan_path=None):
    """Publish task runtime directories beside preserved governance state."""
    errors = _governance_only_namespace_errors(
        root, allowed_plan_path=allowed_plan_path)
    if errors:
        raise FileExistsError("; ".join(errors))
    runtime = os.path.join(root, runtime_paths.RUNTIME_ROOT)
    if set(documents) != _STATE_DOCUMENT_NAMES:
        raise ValueError(
            "runtime initialization requires exactly the three state files")
    staging = tempfile.mkdtemp(
        prefix=runtime_paths.RUNTIME_ROOT + "-init-", dir=root)
    moved = []
    moved_files = []
    # A governance-only namespace is already public. Publish the writer lock
    # before any task state, matching the pre-registry transaction ordering.
    publication_roots = _task_runtime_publication_roots()
    publication_dirs = tuple(
        _runtime_relative_path(directory) for directory in publication_roots)
    publish_dirs = [
        directory for directory in publication_dirs
        if not os.path.lexists(os.path.join(runtime, directory))
    ]
    publish_dirs = tuple(publish_dirs)
    public_transient = os.path.isdir(_runtime_namespace_path(
        runtime, runtime_paths.TRANSIENT_ROOT))
    try:
        for directory in publish_dirs:
            os.makedirs(os.path.join(staging, directory), exist_ok=False)
        for name, text in documents.items():
            target = _runtime_namespace_path(
                staging, _STATE_DOCUMENT_PATH_BY_NAME[name])
            kblib.atomic_write_text(
                target, text, validator=kblib.parse_yaml_subset)
        _stage_evidence_files(staging, evidence_files)
        pre_publish_validator()
        # Initial Profile adoption legitimately creates the receipt append
        # marker before task runtime exists.  In that serial handoff, tmp is
        # already public, so place this transaction's ordinary writer lock
        # there instead of assuming staging owns a second tmp directory.
        lock_runtime = runtime if public_transient else staging
        _create_publication_lock(lock_runtime, lock_operation)
        try:
            for directory in publish_dirs:
                source = os.path.join(staging, directory)
                target = os.path.join(runtime, directory)
                _rename_noreplace(source, target)
                moved.append(directory)
            for repository_path in sorted((evidence_files or {})):
                relative = _runtime_relative_path(repository_path)
                if any(relative == directory or
                       relative.startswith(directory + os.sep)
                       for directory in moved):
                    continue
                source = _runtime_namespace_path(staging, repository_path)
                target = _runtime_namespace_path(runtime, repository_path)
                if not os.path.isdir(os.path.dirname(target)):
                    raise ValueError(
                        "Receipt parent is absent during task publication: %s"
                        % repository_path)
                _rename_noreplace(source, target)
                moved_files.append(repository_path)
            _fsync_directory(runtime)
            post_publish_validator()
        except BaseException as publication_error:
            try:
                for repository_path in reversed(moved_files):
                    source = _runtime_namespace_path(runtime, repository_path)
                    target = _runtime_namespace_path(staging, repository_path)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    _rename_noreplace(source, target)
                for directory in reversed(moved):
                    _rename_noreplace(
                        os.path.join(runtime, directory),
                        os.path.join(staging, directory))
                _remove_publication_lock(lock_runtime, lock_operation)
                _fsync_directory(runtime)
            except BaseException as rollback_error:
                raise ValueError(
                    "runtime publication failed and rollback is incomplete: "
                    "publication=%s; rollback=%s" %
                    (publication_error, rollback_error)) from publication_error
            raise
        _remove_publication_lock(runtime, lock_operation)
    finally:
        if os.path.lexists(staging):
            shutil.rmtree(staging)


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Publish one confirmed Task Plan as initial runtime state")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument(
        "--plan", required=True,
        help="confirmed Task Plan below %s" % runtime_paths.TASK_PLAN_DELTA_ROOT)
    parser.add_argument("--apply", action="store_true",
                        help="publish the transaction; omit for a dry run")
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _JSON_REPORTER.run(lambda: _run(args))


def _run(args):
    root = os.path.realpath(os.path.abspath(args.root))
    if not os.path.isdir(root):
        print("[FAIL] root is not an existing directory: %s" % args.root)
        return 1
    try:
        prepared = task_plan.prepare(root, args.plan)
    except (OSError, UnicodeError, TypeError, ValueError,
            task_plan.Refusal, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot prepare initial Task Plan: %s" % exc)
        return 1

    runtime = os.path.join(root, runtime_paths.RUNTIME_ROOT)
    task_state = os.path.join(root, runtime_paths.STATE_ROOT)
    governance_only = os.path.lexists(runtime) and not os.path.lexists(
        task_state)
    namespace_errors = (_governance_only_namespace_errors(
                            root, allowed_plan_path=prepared["plan_path"])
                        if governance_only else [])
    if os.path.lexists(task_state) or namespace_errors:
        print("[FAIL] task runtime is not a blank governance-only namespace")
        for error in namespace_errors:
            print("[FAIL] %s" % error)
        return 1

    print("initialization plan:")
    for directory in RUNTIME_DIRS:
        print("  %s/%s/" % (runtime_paths.RUNTIME_ROOT, directory))
    for name in prepared["documents"]:
        print("  %s" % _STATE_DOCUMENT_PATH_BY_NAME[name])
    print("  %s" % task_plan.RECEIPT_PATH)
    task_plan.report(prepared)
    if not args.apply:
        print("dry run; add --apply to publish state and Receipt together")
        return 0

    receipt = prepared["receipt"]
    authority = prepared["authority"]
    lock_operation = {
        "tool": task_plan.TOOL,
        "tool_version": task_plan.TOOL_VERSION,
        "action": "initial-task-planning",
        "target": prepared["plan"]["plan_id"],
        "task_id": prepared["plan"]["task_id"],
        "plan_path": prepared["plan_path"],
        "plan_sha256": prepared["plan_sha"],
        "receipt_id": receipt["receipt_id"],
        "commit_receipt_id": receipt["receipt_id"],
        "receipt_path": task_plan.RECEIPT_PATH,
        "transaction_phase": "commit",
        "planned_after_coverage_sha256":
            prepared["state_sha"]["coverage"],
        "planned_after_progress_sha256":
            prepared["state_sha"]["progress"],
        "planned_after_queue_sha256":
            prepared["state_sha"]["queue"],
    }
    lock_operation.update(queue_runtime.runtime_authority_lock_fields(authority))
    try:
        publisher = (publish_runtime_into_governance_namespace
                     if governance_only else publish_runtime)
        keywords = {
            "evidence_files": {
                task_plan.RECEIPT_PATH: prepared["receipt_bytes"]},
            "pre_publish_validator": lambda: task_plan.require_current(
                prepared, "pre-publication"),
            "post_publish_validator": lambda: task_plan.validate_published(
                prepared),
            "lock_operation": lock_operation,
        }
        if governance_only:
            keywords["allowed_plan_path"] = prepared["plan_path"]
        publisher(root, prepared["documents"], **keywords)
    except FileExistsError as exc:
        _report_existing_runtime(root, str(exc))
        return 1
    except (OSError, TypeError, ValueError, task_plan.Refusal,
            kblib.YamlSubsetError) as exc:
        print("[FAIL] initialization stopped: %s" % exc)
        return 1
    _JSON_REPORTER.record([receipt])
    print("[PASS] published the confirmed Task Plan and its Receipt")
    print("next: %s" % task_plan.compile_command(prepared))
    return 0


if __name__ == "__main__":
    sys.exit(main())
