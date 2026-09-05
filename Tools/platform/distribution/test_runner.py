"""Run catalog-owned tests with bounded, file-level isolation.

The ownership manifest decides which cases are safe to overlap. One child
process always receives every selected case from one test module, so failures
remain attributable to a file and module-local process state is never split
across workers. Modules not declared ``parallel_safe`` run serially.
"""

from __future__ import annotations

import argparse
from concurrent import futures
from dataclasses import dataclass
import os
import pathlib
import subprocess
import sys
import time

from Tools.platform.common import kblib
from Tools.platform.distribution import test_catalog


CATALOG_PATH = "Tools/compiled/test-catalog.json"
LEVELS = ("unit", "contract", "integration", "e2e", "slow", "historical-read-only")
DEFAULT_JOBS = min(4, max(1, os.cpu_count() or 1))


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
) -> GroupResult:
    """The only subprocess boundary used by the catalog runner."""
    started = time.monotonic()
    try:
        result = kblib.run_cambium_subprocess(
            [python, "-m", "unittest", *group.test_ids],
            cwd=str(root),
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return GroupResult(
            group=group,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed=time.monotonic() - started,
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

    for _number, result in _parallel_results(
        parallel, jobs=jobs, run_child=run_child
    ):
        number = number_by_group[result.group]
        _emit_result(suite, number, len(groups), result, "parallel")
        completed_cases += len(result.group.test_ids)
        completed_modules += 1
        if result.returncode and not returncode:
            returncode = result.returncode
    if returncode:
        return returncode, completed_cases, completed_modules

    for group in serial:
        result = run_child(group)
        _emit_result(suite, number_by_group[group], len(groups), result, "serial")
        completed_cases += len(group.test_ids)
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
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
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
    suite_names = (args.suite,)
    try:
        selections = {suite: select_test_ids(catalog, suite, args.test_files)
                      for suite in suite_names}
        if args.test_files is not None and not any(selections.values()):
            raise TestRunnerError("--test-files selects no current cases in this suite")
    except TestRunnerError as exc:
        print("test runner: FAIL: %s" % exc, file=sys.stderr)
        return 1
    if args.list_only:
        for suite in suite_names:
            for test_id in selections[suite]:
                print(test_id)
        return 0
    env = dict(os.environ)
    paths = [str(root / "Tools" / "tests"), str(root)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    started = time.monotonic()
    selected_total = sum(len(selections[suite]) for suite in suite_names)
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
    completed_total = 0
    completed_modules = 0
    returncode = 0
    completed_suites = 0
    for suite in suite_names:
        test_ids = selections[suite]
        try:
            groups = module_groups(catalog, test_ids)
        except TestRunnerError as exc:
            print("test runner: FAIL: %s" % exc, file=sys.stderr)
            return 1
        if not groups:
            print("test runner: suite=%s selected=0 completed=0 elapsed=0.000s exit=0" % suite)
            completed_suites += 1
            continue
        suite_started = time.monotonic()
        run_child = lambda group: _run_child(
            group, python=args.python or sys.executable, root=root, env=env
        )
        result, completed, modules = _execute_suite(
            suite, groups, jobs=args.jobs, run_child=run_child
        )
        completed_total += completed
        completed_modules += modules
        returncode = result
        print(
            "test runner: suite=%s selected=%d completed=%d modules=%d/%d jobs=%d elapsed=%.3fs exit=%d"
            % (
                suite,
                len(test_ids),
                completed,
                modules,
                len(groups),
                args.jobs,
                time.monotonic() - suite_started,
                returncode,
            )
        )
        if returncode:
            break
        completed_suites += 1
    elapsed = time.monotonic() - started
    if args.suite == "full":
        print(
            "test runner: suite=full selected=%d completed=%d modules=%d suites=%d/%d jobs=%d elapsed=%.3fs exit=%d"
            % (
                selected_total,
                completed_total,
                completed_modules,
                completed_suites,
                len(suite_names),
                args.jobs,
                elapsed,
                returncode,
            )
        )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
