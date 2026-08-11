#!/usr/bin/env python3
"""Materialize an adopter's empty ``.cambium/`` runtime state.

Initialization never invents Required work.  It refuses any existing runtime
namespace and is a dry run unless ``--apply`` is present.
"""

import argparse
import ctypes
import errno
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib

TOOL = "init_state"
TOOL_VERSION = "1.3.0"
RUNTIME_DIRS = (
    "state", "work_specs", "deltas", "receipts", "reports", "tmp",
)


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
            root, ".cambium/state/required_queue.yaml", ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        )
        progress_path = kblib.managed_repository_path(
            root, ".cambium/state/progress_ledger.yaml", ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        )
        coverage_path = kblib.managed_repository_path(
            root, ".cambium/state/coverage_ledger.yaml", ".cambium/state",
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
        for field in ("task_id", "scope_version", "standards_version",
                      "selected_profile_manifest"):
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
    lock_path = os.path.join(staging, "tmp", "state-writer.lock")
    os.mkdir(lock_path, 0o700)
    owner_path = os.path.join(lock_path, "owner.json")
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
    lock_path = os.path.join(runtime, "tmp", "state-writer.lock")
    owner_path = os.path.join(lock_path, "owner.json")
    names = sorted(os.listdir(lock_path))
    if names != ["owner.json"]:
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
    _fsync_directory(os.path.join(runtime, "tmp"))


def publish_runtime(root, documents, *, pre_publish_validator=None,
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
    runtime = os.path.join(root, ".cambium")
    if os.path.lexists(runtime):
        raise FileExistsError(
            ".cambium already exists; refusing to overwrite even an empty namespace"
        )
    expected = {
        "coverage_ledger.yaml", "required_queue.yaml", "progress_ledger.yaml"
    }
    if set(documents) != expected:
        raise ValueError("runtime initialization requires exactly the three state files")

    staging = tempfile.mkdtemp(prefix=".cambium-init-", dir=root)
    published = False
    try:
        for directory in RUNTIME_DIRS:
            os.makedirs(os.path.join(staging, directory), exist_ok=False)
        state_dir = os.path.join(staging, "state")
        for name, text in documents.items():
            target = os.path.join(state_dir, name)
            kblib.atomic_write_text(
                target, text, validator=kblib.parse_yaml_subset
            )
            with open(target, encoding="utf-8") as fh:
                reparsed = kblib.parse_yaml_subset(fh.read())
            if not isinstance(reparsed, dict):
                raise kblib.YamlSubsetError(
                    "staged state file is not a mapping: %s" % name
                )
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


KERNEL_CONCURRENCY_CAP = 3


def _resolve_concurrency_cap_overrides(overrides, explicit):
    """Resolve a cap from one snapshot-bound evaluation override tuple."""
    try:
        overrides = dict(overrides)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "authorized Profile evaluation has malformed execution-default "
            "overrides: %s" % exc) from exc
    raw = overrides.get("concurrency_cap")
    manifest_value = None
    if raw is not None:
        if (not isinstance(raw, str) or
                not re.fullmatch(r"[0-9]+", raw) or int(raw) < 1):
            raise ValueError(
                "selected profile manifest declares concurrency_cap=%r; "
                "K13/10 requires a positive integer" % raw
            )
        manifest_value = int(raw)
    if manifest_value is None:
        if explicit is None:
            return KERNEL_CONCURRENCY_CAP, "kernel-default"
        return explicit, "task-contract"
    if explicit is None:
        return manifest_value, "profile-manifest"
    if explicit != manifest_value:
        raise ValueError(
            "--concurrency-cap %d contradicts the selected profile "
            "manifest's registered concurrency_cap %d; K13/10 sets no "
            "precedence between them, so reconcile the two explicit "
            "overrides before initializing" % (explicit, manifest_value)
        )
    return manifest_value, "task-contract+profile-manifest"


def resolve_concurrency_cap(root, manifest_relative, explicit, *,
                            authorized_profile_view=None):
    """Resolve K13/10's concurrency cap and name the layer that decided it.

    K13/10 makes `3` the kernel default and lets the selected profile manifest
    or the task contract override it explicitly; it fixes no precedence
    between those two.  This resolver therefore does not invent one.  It reads
    whichever of the two is present, and when both are present and disagree it
    reports the inconsistency instead of picking a winner.  The resolved value
    is written into Progress, which is what "the resolved cap MUST be recorded
    at runtime" requires and what ``check_queue.py`` then enforces; no runtime
    check reads the manifest prose.

    The override is consumed only from the immutable evaluation returned by
    ``profile-load``.  It is never reparsed from a live manifest path, because
    a pre/post digest check cannot exclude an A -> B -> A read between those
    observations.
    """
    if not manifest_relative:
        return _resolve_concurrency_cap_overrides((), explicit)
    view = authorized_profile_view
    if view is None:
        view, errors = check_queue.profile_load_authorized_view(
            root, manifest_relative)
    else:
        errors = check_queue._authorized_profile_view_errors(
            root, manifest_relative, view)
    if view is None or errors:
        raise ValueError("selected Profile failed profile-load: %s" %
                         "; ".join(errors or ("no authorized view",)))
    evaluation = view.get("_evaluation")
    if evaluation is None:
        raise ValueError(
            "authorized Profile view has no snapshot-bound evaluation")
    return _resolve_concurrency_cap_overrides(
        evaluation.execution_default_overrides, explicit)


def _profile_configuration(root, manifest_relative, explicit_cap, *,
                           expected_evidence=None, expected_cap=None,
                           expected_cap_source=None, phase):
    """Return one snapshot-bound Profile load and its runtime override."""
    view, errors = check_queue.profile_load_authorized_view(
        root, manifest_relative)
    if errors:
        raise ValueError("%s selected Profile failed profile-load: %s" %
                         (phase, "; ".join(errors)))
    resolved_cap, cap_source = resolve_concurrency_cap(
        root, manifest_relative, explicit_cap,
        authorized_profile_view=view)
    evidence = check_queue._public_profile_load_evidence(view)
    for field in (
            "selected_profile_manifest", "profile_snapshot_sha256",
            "profile_contract_fingerprint",
            "profile_load_inputs_sha256"):
        if (expected_evidence is not None and
                evidence.get(field) != expected_evidence.get(field)):
            raise ValueError(
                "%s selected Profile %s changed after initialization "
                "admission" % (phase, field))
    if expected_cap is not None and resolved_cap != expected_cap:
        raise ValueError(
            "%s selected Profile concurrency_cap changed after "
            "initialization admission" % phase)
    if (expected_cap_source is not None and
            cap_source != expected_cap_source):
        raise ValueError(
            "%s selected Profile concurrency_cap source changed after "
            "initialization admission" % phase)
    return evidence, resolved_cap, cap_source


def build_documents(args):
    if getattr(args, "completion_semantics", None) not in (
            "build", "maintenance"):
        raise ValueError(
            "completion_semantics must be explicitly build or maintenance"
        )
    if not isinstance(args.objective, str) or not args.objective.strip():
        raise ValueError("objective must be a non-empty string")
    if (not isinstance(args.concurrency_cap, int) or
            isinstance(args.concurrency_cap, bool) or
            args.concurrency_cap < 1):
        raise ValueError(
            "concurrency_cap must be resolved to a positive integer before "
            "the contract is materialized"
        )
    if (not isinstance(args.exclusions, list) or
            not all(isinstance(value, str) and value.strip()
                    for value in args.exclusions)):
        raise ValueError("exclusions must be an explicit non-empty-string list")
    if len(args.exclusions) != len(set(args.exclusions)):
        raise ValueError("exclusions must not contain duplicates")
    queue = {
        "schema_version": 1,
        "task_id": args.task_id,
        "scope_version": args.scope_version,
        "queue_revision": 1,
        "state_revision": 0,
        "standards_version": args.standards_version,
        "selected_profile_manifest": args.profile_manifest,
        "required_queue": [],
    }
    queue_text = kblib.canonical_yaml(queue)
    coverage = {
        "schema_version": 1,
        "task_id": args.task_id,
        "updated_at": args.at,
        "scope_version": args.scope_version,
        "standards_version": args.standards_version,
        "selected_profile_manifest": args.profile_manifest,
        "batch_specs": [],
        "maintenance_candidates": [],
        "pages": [],
        "open_gaps": [],
    }
    progress = {
        "schema_version": 1,
        "task_id": args.task_id,
        "task_state": "planned",
        "task_transition_receipts": [],
        "required_queue_path": ".cambium/state/required_queue.yaml",
        "queue_revision": 1,
        "queue_state_revision": 0,
        "required_queue_sha256": kblib.sha256_bytes(queue_text),
        "initial_queue_receipt": None,
        "contract": {
            "contract_version": args.contract_version,
            "completion_semantics": args.completion_semantics,
            "objective": args.objective,
            "exclusions": list(args.exclusions),
            "scope_version": args.scope_version,
            "concurrency_cap": args.concurrency_cap,
            "standards_version": args.standards_version,
            "selected_profile_manifest": args.profile_manifest,
            "selected_route_ids": [],
            "selected_card_paths": [],
            "selected_profile_route_ids": [],
            "selected_read_sets": [],
            "loaded_module_paths": [],
            "minimum_run_until": "",
            "checkpoint_at": "",
            "hard_stop_at": "",
            "completion_gate": (
                "guidance pending=0 AND required_authoring_gaps=0 AND "
                "remaining_required_work_units=0 AND "
                "unresolved_invalidations=0 AND all applicable gates passed"
                if args.completion_semantics == "build" else
                "maintenance budget manifest closed AND ledger advanced AND "
                "watermark advanced AND remaining_required_work_units=0 AND "
                "all applicable batch gates persisted"
            ),
        },
        "checkpoint": {
            "recorded_at": None,
            "summary": None,
            "task_state": "planned",
            "task_transition_receipt": None,
            "coverage_sha256": None,
            "required_queue_sha256": None,
            "queue_revision": 1,
            "queue_state_revision": 0,
        },
        "terminal_audit": {
            "state": ("not-started" if args.completion_semantics == "build"
                      else "not-applicable"),
            "terminal_proof_path": None,
            "terminal_proof_sha256": None,
            "terminal_proof_receipt": None,
            "queue_check_receipt": None,
        },
        "maintenance_completion": {
            "state": ("pending" if args.completion_semantics == "maintenance"
                      else "not-applicable"),
            "completion_gate_receipt": None,
            "budget_manifest_receipt": None,
            "ledger_advance_receipt": None,
            "watermark_advance_receipt": None,
        },
        "amendments": [],
        "standards_adoptions": [],
        "guidance_queue": [],
    }
    return {
        "coverage_ledger.yaml": kblib.canonical_yaml(coverage),
        "required_queue.yaml": queue_text,
        "progress_ledger.yaml": kblib.canonical_yaml(progress),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Initialize empty Cambium runtime state")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--objective", required=True,
                        help="non-empty statement of the task outcome")
    parser.add_argument("--exclude", dest="exclusions", action="append",
                        default=[], help="explicit out-of-scope item; repeatable")
    parser.add_argument("--scope-version", required=True)
    parser.add_argument("--standards-version", required=True)
    parser.add_argument("--profile-manifest", required=True)
    parser.add_argument("--contract-version", default="c1")
    parser.add_argument(
        "--completion-semantics", required=True,
        choices=("build", "maintenance"),
        help=("build requires completion-candidate plus Terminal Proof; "
              "maintenance closes directly through the bounded maintenance "
              "completion gate"),
    )
    parser.add_argument(
        "--concurrency-cap", type=int, default=None,
        help=("explicit task-contract override of K13/10's concurrency cap; "
              "omit it to take the selected profile manifest's registered "
              "override, or the kernel default 3 when the manifest registers "
              "none"),
    )
    parser.add_argument("--at", default=None,
                        help="initial Coverage timestamp (default: current UTC)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    if not os.path.isdir(root):
        print("[FAIL] root is not an existing directory: %s" % args.root)
        return 1
    if args.concurrency_cap is not None and args.concurrency_cap < 1:
        print("[FAIL] --concurrency-cap must be >= 1")
        return 1
    for label, value in (("task id", args.task_id),
                         ("objective", args.objective),
                         ("scope version", args.scope_version),
                         ("standards version", args.standards_version),
                         ("contract version", args.contract_version)):
        if not value.strip():
            print("[FAIL] %s must be non-empty" % label)
            return 1
    if (not all(value.strip() for value in args.exclusions) or
            len(args.exclusions) != len(set(args.exclusions))):
        print("[FAIL] --exclude values must be non-empty and unique")
        return 1
    requested_concurrency_cap = args.concurrency_cap
    active_standards_view, active_errors = \
        check_queue.active_standards_authorized_view(
        root, args.standards_version, args.profile_manifest)
    if active_errors:
        for error in active_errors:
            print("[FAIL] %s" % error)
        return 1
    try:
        profile_evidence, args.concurrency_cap, concurrency_cap_source = \
            _profile_configuration(
                root, args.profile_manifest, requested_concurrency_cap,
                phase="initial admission")
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        print("[FAIL] cannot admit selected Profile: %s" % exc)
        return 1

    runtime = os.path.join(root, ".cambium")
    if os.path.lexists(runtime):
        _report_existing_runtime(root, ".cambium already exists")
        return 1
    if args.at is None:
        args.at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not check_queue._valid_timestamp(args.at):
        print("[FAIL] --at must be a timezone-aware RFC 3339 timestamp")
        return 1
    try:
        documents = build_documents(args)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot materialize runtime state: %s" % exc)
        return 1

    print("initialization plan:")
    for directory in RUNTIME_DIRS:
        print("  .cambium/%s/" % directory)
    for name in documents:
        print("  .cambium/state/%s" % name)
    print("  Required Queue items: 0 (no work inferred)")
    print("  objective=%s" % args.objective)
    print("  exclusions=%s" % (", ".join(args.exclusions) or "none"))
    print("  completion_semantics=%s" % args.completion_semantics)
    print("  concurrency_cap=%d (resolved from %s)" %
          (args.concurrency_cap, concurrency_cap_source))
    print("queue_revision=1 state_revision=0")
    print("required_queue_sha256=%s" %
          kblib.sha256_bytes(documents["required_queue.yaml"]))
    if not args.apply:
        print("dry run; add --apply to create the runtime state")
        return 0

    def revalidate_profile(phase):
        active_errors = check_queue.active_standards_view_currency_errors(
            root, active_standards_view)
        if active_errors:
            raise ValueError("%s active Standards identity changed: %s" %
                             (phase, "; ".join(active_errors)))
        _profile_configuration(
            root, args.profile_manifest, requested_concurrency_cap,
            expected_evidence=profile_evidence,
            expected_cap=args.concurrency_cap,
            expected_cap_source=concurrency_cap_source,
            phase=phase)

    lock_operation = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "initialize-runtime",
        "task_id": args.task_id,
        "selected_profile_manifest": args.profile_manifest,
        "profile_snapshot_sha256":
            profile_evidence["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            profile_evidence["profile_contract_fingerprint"],
        "profile_load_inputs_sha256":
            profile_evidence["profile_load_inputs_sha256"],
        "active_standards_sha256":
            active_standards_view["active_standards_sha256"],
        "planned_required_queue_sha256":
            kblib.sha256_bytes(documents["required_queue.yaml"]),
    }
    try:
        publish_runtime(
            root, documents,
            pre_publish_validator=lambda: revalidate_profile(
                "pre-publication"),
            post_publish_validator=lambda: revalidate_profile(
                "post-publication"),
            lock_operation=lock_operation)
    except FileExistsError as exc:
        _report_existing_runtime(root, str(exc))
        return 1
    except (OSError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] initialization stopped: %s" % exc)
        return 1
    print("[PASS] initialized empty Cambium runtime state")
    return 0


if __name__ == "__main__":
    sys.exit(main())
