"""Run catalog-owned tests with bounded, file-level isolation.

The ownership manifest decides which cases are safe to overlap. One child
process always receives every selected case from one test module, so failures
remain attributable to a file and module-local process state is never split
across workers. Modules not declared ``parallel_safe`` run serially.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from concurrent import futures
from dataclasses import dataclass
import functools
import hashlib
import json
import math
import os
import pathlib
import platform
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from Tools.platform.common import kblib
from Tools.platform.distribution import test_catalog


CATALOG_PATH = "Tools/compiled/test-catalog.json"
LEVELS = ("unit", "contract", "integration", "e2e", "slow", "historical-read-only")
DEFAULT_JOBS = min(4, max(1, os.cpu_count() or 1))
_MEASUREMENTS = ContextVar("test_cost_measurements", default=None)


@contextmanager
def measure_scope(kind: str, identity: str):
    """Attribute engineering cost, never a production verdict or authority.

    A nested record reports inclusive and exclusive wall time. Outside the
    test child this is a no-op; no environment flag reaches production tools.
    """
    state = _MEASUREMENTS.get()
    counts = {}
    if state is None:
        yield counts
        return
    stack, rows, on_scope = state
    frame = {"kind": kind, "identity": identity, "children": 0.0}
    parent = stack[-1] if stack else None
    stack.append(frame)
    started = time.monotonic()
    outcome = "returned"
    try:
        yield counts
    except BaseException:
        outcome = "raised"
        raise
    finally:
        elapsed = time.monotonic() - started
        stack.pop()
        if parent is not None:
            parent["children"] += elapsed
        row = {"kind": kind, "identity": identity,
                     "parent": None if parent is None else parent["identity"],
                     "elapsed": elapsed,
                     "exclusive": max(0.0, elapsed - frame["children"]),
                     "outcome": outcome}
        if counts:
            if any(not isinstance(key, str) or not key or
                   not isinstance(value, int) or isinstance(value, bool) or value < 0
                   for key, value in counts.items()):
                raise ValueError("measured work counts require names and nonnegative integers")
            row["counts"] = dict(sorted(counts.items()))
        rows.append(row)
        if on_scope is not None:
            on_scope(dict(row))


def measured(kind: str, identity: str):
    """Instrument a fixture scope without changing its inputs or outputs."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            with measure_scope(kind, identity):
                return function(*args, **kwargs)
        return wrapped
    return decorate


class _TimedResult(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test)
        self._scope = measure_scope("case", test.id())
        self._scope.__enter__()

    def stopTest(self, test):
        self._scope.__exit__(None, None, None)
        super().stopTest(test)


def _cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _cases(item)
        else:
            yield item


@contextmanager
def _instrument_fixtures(suite):
    """Wrap real unittest hooks; unittest still owns execution and cleanup."""
    cases = list(_cases(suite))
    with ExitStack() as cleanup:
        def replace(obj, name, replacement):
            own = name in vars(obj)
            previous = vars(obj).get(name)
            setattr(obj, name, replacement)
            def restore():
                if own:
                    setattr(obj, name, previous)
                else:
                    delattr(obj, name)
            cleanup.callback(restore)

        for case in cases:
            for name in ("_callSetUp", "_callTestMethod", "_callTearDown", "_callCleanup"):
                original = getattr(case, name)
                replace(case, name, measured("method-hook", case.id() + ":" + name)(original))
        # Capture bound hooks before wrapping any inherited class, so a
        # shared base does not cause nested instrumentation of one call.
        hooks = [(cls, name, getattr(cls, name))
                 for cls in dict.fromkeys(type(case) for case in cases)
                 for name in ("setUpClass", "tearDownClass", "doClassCleanups")]
        for cls, name, original in hooks:
            identity = cls.__module__ + "." + cls.__qualname__ + ":" + name
            timed = measured("class-hook", identity)(original)
            replace(cls, name, staticmethod(timed))
        for module_name in dict.fromkeys(type(case).__module__ for case in cases):
            module = sys.modules[module_name]
            for name in ("setUpModule", "tearDownModule"):
                original = getattr(module, name, None)
                if original is not None:
                    replace(module, name, measured("module-hook", module_name + ":" + name)(original))
        original = unittest.case.doModuleCleanups
        replace(unittest.case, "doModuleCleanups", measured("module-hook", "module-cleanups")(original))
        yield


def run_measured_tests(test_ids, *, stream=None, on_scope=None):
    """Run one selected module in this already isolated child, without Catalog."""
    rows = []
    token = _MEASUREMENTS.set(([], rows, on_scope))
    try:
        with measure_scope("discovery", "unittest-load"):
            suite = unittest.defaultTestLoader.loadTestsFromNames(test_ids)
        discovered = [case.id() for case in _cases(suite)]
        with _instrument_fixtures(suite):
            result = unittest.TextTestRunner(
                stream=stream, resultclass=_TimedResult).run(suite)
        failing = {getattr(test, "test_case", test).id(): status for status, items in (
            ("failure", result.failures), ("error", result.errors),
            ("skipped", result.skipped), ("expected-failure", result.expectedFailures))
            for test, _detail in items}
        failing.update({test.id(): "unexpected-success" for test in result.unexpectedSuccesses})
        for row in rows:
            if row["kind"] == "case":
                row["status"] = failing.get(row["identity"], "passed")
        return {"schema_version": 1, "selected": list(test_ids),
                "discovered": discovered,
                "not_started": sorted(set(discovered) - {
                    row["identity"] for row in rows if row["kind"] == "case"}),
                "python": sys.version, "executable": sys.executable,
                "tests_run": result.testsRun,
                "successful": result.wasSuccessful(), "scopes": rows}
    finally:
        _MEASUREMENTS.reset(token)


def child_main(argv=None):
    """Private test-process entry; its report cannot select or authorize work."""
    args = sys.argv[1:] if argv is None else argv
    report, progress, *test_ids = args
    # Each child owns a separate external diagnostic file. Completed scopes
    # are flushed immediately; a killed child never emits a successful run.
    with ExitStack() as cleanup:
        handle = None
        if progress:
            try:
                handle = cleanup.enter_context(pathlib.Path(progress).open("x", encoding="utf-8"))
            except OSError as exc:
                print("test runner: progress unavailable: %s" % exc, file=sys.stderr)
        def emit(value):
            nonlocal handle
            if handle is not None:
                try:
                    handle.write(json.dumps(value, sort_keys=True) + "\n")
                    handle.flush()
                except OSError as exc:
                    print("test runner: progress unavailable: %s" % exc, file=sys.stderr)
                    handle = None
        emit({"kind": "test-cost-progress", "state": "incomplete", "selected": test_ids})
        value = run_measured_tests(test_ids, on_scope=emit)
        emit({"kind": "test-run-finished", "state": "complete",
              "successful": value["successful"], "tests_run": value["tests_run"]})
    pathlib.Path(report).write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if value["successful"] else 1


class TestRunnerError(Exception):
    """The compiled catalog cannot select a valid test run."""


@dataclass(frozen=True)
class TestGroup:
    """All selected cases from one test module and one suite."""

    module: str
    path: str
    test_ids: tuple[str, ...]
    parallel_safe: bool


@dataclass(frozen=True)
class GroupResult:
    """Captured output from one attributable child process."""

    group: TestGroup
    returncode: int
    stdout: str
    stderr: str
    elapsed: float
    measurement: dict | None = None


def _catalog(root: pathlib.Path) -> dict:
    try:
        value = test_catalog.load_current_catalog(root)
    except (OSError, UnicodeError, test_catalog.TestCatalogError) as exc:
        raise TestRunnerError("cannot use current %s: %s" % (CATALOG_PATH, exc)) from exc
    if value.get("schema_version") != 1 or not isinstance(value.get("modules"), list):
        raise TestRunnerError("%s has an unsupported schema" % CATALOG_PATH)
    return value


def select_test_ids(catalog: dict, suite: str, test_files: str | None = None) -> list[str]:
    """Select current cases, optionally restricted to exact catalog files.

    File selection changes neither levels nor the catalog's ``parallel_safe``
    declarations. It is shared by local use and CI's already-selected shards.
    """
    selected_levels = set(LEVELS) if suite == "full" else (
        {"unit", "contract"} if suite == "fast" else {suite}
    )
    names = None
    if test_files is not None:
        names = test_files.split(",")
        available = {pathlib.PurePosixPath(module["path"]).name
                     for module in catalog["modules"]}
        if not all(names) or len(names) != len(set(names)):
            raise TestRunnerError("--test-files must be a nonempty, unique file list")
        unknown = sorted(set(names) - available)
        if unknown:
            raise TestRunnerError("--test-files is absent from the current catalog: %s" %
                                  ", ".join(unknown))
        names = set(names)
    selected = []
    for module in catalog["modules"]:
        if names is not None and pathlib.PurePosixPath(module["path"]).name not in names:
            continue
        for case in module.get("cases", []):
            if case.get("disposition") == "keep" and case.get("level") in selected_levels:
                selected.append(case["test_id"])
    return sorted(set(selected))


def module_groups(catalog: dict, test_ids: list[str]) -> list[TestGroup]:
    """Group the selected cases by source file without losing classifications."""
    case_index = {}
    module_paths = {}
    for module in catalog["modules"]:
        for case in module.get("cases", []):
            test_id = case["test_id"]
            case_index[test_id] = case
            module_paths[test_id.split(".", 1)[0]] = module["path"]
    unknown = sorted(set(test_ids) - set(case_index))
    if unknown:
        raise TestRunnerError(
            "compiled catalog selected unknown test IDs: %s" % ", ".join(unknown)
        )
    grouped = {}
    for test_id in sorted(set(test_ids)):
        module = test_id.split(".", 1)[0]
        grouped.setdefault(module, []).append(test_id)
    return [
        TestGroup(
            module=module,
            path=module_paths[module],
            test_ids=tuple(ids),
            parallel_safe=all(bool(case_index[test_id].get("parallel_safe")) for test_id in ids),
        )
        for module, ids in sorted(grouped.items())
    ]


def _run_child(
    group: TestGroup,
    *,
    python: str,
    root: pathlib.Path,
    env: dict[str, str],
    progress_path: pathlib.Path | None = None,
    deadline: float | None = None,
) -> GroupResult:
    """The only subprocess boundary used by the catalog runner."""
    started = time.monotonic()
    if deadline is not None and started >= deadline:
        return GroupResult(group, 124, "", "test deadline exhausted before admission\n", 0.0)
    try:
        print("test runner: starting path=%s cases=%d" % (group.path, len(group.test_ids)), flush=True)
        with tempfile.TemporaryDirectory(prefix="cambium-test-cost-") as temporary:
            report = pathlib.Path(temporary) / "result.json"
            # This boundary owns test-process lifetime, not business execution.
            # Keep authority forwarding at its existing owner; private TMPDIR
            # also makes interrupted fixture resources reclaimable by parent.
            environment = {**env, "TMPDIR": temporary}
            timed_out = False
            with kblib.open_cambium_subprocess(
                [python, "-c", "from Tools.platform.distribution.test_runner import child_main; "
                 "raise SystemExit(child_main())", str(report),
                 str(progress_path) if progress_path else "", *group.test_ids],
                cwd=str(root), env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
                start_new_session=os.name == "posix") as process:
                def terminate(signum):
                    try:
                        if os.name == "posix":
                            os.killpg(process.pid, signum)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
                try:
                    remaining = None if deadline is None else max(0, deadline - time.monotonic())
                    stdout, stderr = process.communicate(timeout=remaining)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate(signal.SIGTERM)
                    try:
                        stdout, stderr = process.communicate(timeout=1)
                    except subprocess.TimeoutExpired:
                        terminate(signal.SIGKILL)
                        stdout, stderr = process.communicate()
                    # A descendant may ignore TERM and close its inherited
                    # pipes. Successful communicate is not proof it exited.
                    terminate(signal.SIGKILL)
                    stderr += "\ntest deadline exceeded; isolated process group terminated\n"
                except BaseException:
                    terminate(signal.SIGKILL)
                    process.communicate()
                    raise
            try:
                measurement = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                measurement = None  # A crash has no complete timing report.
        return GroupResult(
            group=group,
            returncode=124 if timed_out else process.returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed=time.monotonic() - started,
            measurement=measurement,
        )
    except (OSError, UnicodeError) as exc:
        return GroupResult(
            group=group,
            returncode=127,
            stdout="",
            stderr="cannot start test child for %s: %s\n" % (group.path, exc),
            elapsed=time.monotonic() - started,
        )


def _emit_result(suite: str, number: int, total: int, result: GroupResult, mode: str) -> None:
    print(
        "test runner: suite=%s module=%d/%d path=%s cases=%d mode=%s elapsed=%.3fs exit=%d"
        % (
            suite,
            number,
            total,
            result.group.path,
            len(result.group.test_ids),
            mode,
            result.elapsed,
            result.returncode,
        ),
        flush=True,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
        if not result.stdout.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    if result.stderr:
        sys.stderr.write("test runner: child stderr path=%s\n" % result.group.path)
        sys.stderr.write(result.stderr)
        if not result.stderr.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.flush()


def _parallel_results(
    groups: list[TestGroup],
    *,
    jobs: int,
    run_child,
):
    """Yield bounded results and stop admitting work after the first failure."""
    if not groups:
        return
    iterator = iter(enumerate(groups, 1))
    pending = {}
    stopped = False
    with futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        for _ in range(min(jobs, len(groups))):
            number, group = next(iterator)
            pending[executor.submit(run_child, group)] = number
        while pending:
            done, _ = futures.wait(pending, return_when=futures.FIRST_COMPLETED)
            for future in sorted(done, key=lambda item: pending[item]):
                number = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:  # defensive boundary for runner defects
                    group = groups[number - 1]
                    result = GroupResult(
                        group=group,
                        returncode=1,
                        stdout="",
                        stderr="test runner worker failed: %s\n" % exc,
                        elapsed=0.0,
                    )
                yield number, result
                if result.returncode:
                    stopped = True
            if stopped:
                for future in list(pending):
                    if future.cancel():
                        pending.pop(future)
                continue
            for _ in range(len(done)):
                try:
                    number, group = next(iterator)
                except StopIteration:
                    break
                pending[executor.submit(run_child, group)] = number


def _execute_suite(
    suite: str,
    groups: list[TestGroup],
    *,
    jobs: int,
    run_child,
) -> tuple[int, int, int]:
    """Return ``(exit, completed cases, completed modules)`` for one suite."""
    parallel = [group for group in groups if group.parallel_safe and jobs > 1]
    serial = [group for group in groups if group not in parallel]
    completed_cases = 0
    completed_modules = 0
    returncode = 0
    number_by_group = {group: number for number, group in enumerate(groups, 1)}
    def completed(result):
        count = (result.measurement or {}).get("tests_run")
        if type(count) is int and 0 <= count <= len(result.group.test_ids):
            return count
        return len(result.group.test_ids) if result.returncode == 0 else 0

    for _number, result in _parallel_results(
        parallel, jobs=jobs, run_child=run_child
    ):
        number = number_by_group[result.group]
        _emit_result(suite, number, len(groups), result, "parallel")
        completed_cases += completed(result)
        completed_modules += 1
        if result.returncode and not returncode:
            returncode = result.returncode
    if returncode:
        return returncode, completed_cases, completed_modules

    for group in serial:
        result = run_child(group)
        _emit_result(suite, number_by_group[group], len(groups), result, "serial")
        completed_cases += completed(result)
        completed_modules += 1
        if result.returncode:
            return result.returncode, completed_cases, completed_modules
    return 0, completed_cases, completed_modules


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "suite",
        choices=("fast", "integration", "e2e", "slow", "historical-read-only", "full"),
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--test-files",
        help="comma-separated exact catalog test filenames; preserve every selected level and file isolation",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="interpreter used to run test files (default: the current interpreter)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_JOBS,
        help="maximum parallel-safe test files to run at once (default: %(default)s)",
    )
    parser.add_argument("--list", action="store_true", dest="list_only")
    parser.add_argument("--report", help="write a new low-authority JSON cost report outside the repository")
    parser.add_argument("--deadline", type=float,
                        help="shared absolute Unix execution deadline; no per-file budget reset")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    deadline = None
    if args.deadline is not None:
        if not math.isfinite(args.deadline) or args.deadline <= 0 or os.name != "posix":
            print("test runner: FAIL: deadline requires a finite positive timestamp and POSIX process isolation", file=sys.stderr)
            return 1
        deadline = time.monotonic() + (args.deadline - time.time())
        if deadline <= time.monotonic():
            print("test runner: deadline exhausted before catalog admission", file=sys.stderr)
            return 124
    report_path = pathlib.Path(args.report).resolve() if args.report else None
    if report_path is not None and (report_path.is_relative_to(root) or report_path.exists()):
        print("test runner: FAIL: --report must be a new file outside the repository", file=sys.stderr)
        return 1
    if args.jobs < 1:
        print("test runner: FAIL: --jobs must be positive", file=sys.stderr)
        return 1
    try:
        catalog = _catalog(root)
    except TestRunnerError as exc:
        print("test runner: FAIL: %s" % exc, file=sys.stderr)
        return 1
    # ``full`` is one file-level execution pass. Splitting it by level would
    # import a mixed module repeatedly and rebuild the same isolated fixture
    # once per classification, defeating both ownership and runtime closure.
    try:
        test_ids = select_test_ids(catalog, args.suite, args.test_files)
        if args.test_files is not None and not test_ids:
            raise TestRunnerError("--test-files selects no current cases in this suite")
    except TestRunnerError as exc:
        print("test runner: FAIL: %s" % exc, file=sys.stderr)
        return 1
    if args.list_only:
        for test_id in test_ids:
            print(test_id)
        return 0
    env = dict(os.environ)
    paths = [str(root / "Tools" / "tests"), str(root)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    started = time.monotonic()
    if args.suite == "full":
        level_counts = {
            level: len(select_test_ids(catalog, level, args.test_files))
            for level in LEVELS
        }
        print(
            "test runner: suite=full selected-levels=%s"
            % ",".join(
                "%s:%d" % (level, level_counts[level]) for level in LEVELS
            )
        )
    try:
        groups = module_groups(catalog, test_ids)
    except TestRunnerError as exc:
        print("test runner: FAIL: %s" % exc, file=sys.stderr)
        return 1
    reports = []
    progress_dir = None
    if report_path is not None:
        candidate = report_path.with_suffix(".progress")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            progress_dir = candidate
        except OSError as exc:
            print("test runner: progress unavailable: %s" % exc, file=sys.stderr)
    def run_child(group):
        try:
            source_hash = hashlib.sha256((root / group.path).read_bytes()).hexdigest()
        except OSError:
            source_hash = None  # Diagnostics do not redefine test admission.
        result = _run_child(group, python=args.python or sys.executable, root=root, env=env,
                            progress_path=progress_dir / (group.module + ".jsonl")
                            if progress_dir else None, deadline=deadline)
        reports.append({"path": group.path, "test_ids": list(group.test_ids),
                        "test_source_sha256": source_hash,
                        "elapsed": result.elapsed, "exit": result.returncode,
                        "parallel_safe": group.parallel_safe,
                        "measurement": result.measurement})
        return result
    returncode, completed, modules = _execute_suite(
        args.suite, groups, jobs=args.jobs, run_child=run_child)
    elapsed = time.monotonic() - started
    print(
        "test runner: suite=%s selected=%d completed=%d modules=%d/%d jobs=%d elapsed=%.3fs exit=%d"
        % (args.suite, len(test_ids), completed, modules, len(groups),
           args.jobs, elapsed, returncode))
    if args.report:
        case_index = {case["test_id"]: case for module in catalog["modules"]
                      for case in module.get("cases", [])}
        for report in reports:
            for row in (report["measurement"] or {}).get("scopes", []):
                if row["kind"] == "case":
                    row["level"] = case_index.get(row["identity"], {}).get("level")
        def revision(expression):
            result = kblib.run_cambium_subprocess(
                ["git", "rev-parse", expression], cwd=root,
                text=True, capture_output=True, check=False)
            return result.stdout.strip() if result.returncode == 0 else None
        dependencies = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted((root / "Tools").glob("requirements*.txt"))}
        identity = {"commit": revision("HEAD"), "tree": revision("HEAD^{tree}"),
                    "python": sys.version, "platform": platform.platform(),
                    "python_override": args.python,
                    "dependencies": dependencies,
                    "ci": {key: os.environ.get(key) for key in (
                        "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "ImageOS", "ImageVersion", "RUNNER_ARCH")}}
        tree_status = kblib.run_cambium_subprocess(
            ["git", "status", "--porcelain=v1"], cwd=root,
            text=True, capture_output=True, check=False)
        identity["worktree_clean"] = (
            not tree_status.stdout if tree_status.returncode == 0 else None)
        value = {"schema_version": 1, "kind": "test-cost-report", "identity": identity,
                 "suite": args.suite, "selected": test_ids,
                 "elapsed": elapsed, "exit": returncode,
                 "modules": sorted(reports, key=lambda row: row["path"])}
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        except OSError as exc:
            print("test runner: cost report unavailable: %s" % exc, file=sys.stderr)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
