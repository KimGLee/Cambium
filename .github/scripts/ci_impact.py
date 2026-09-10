#!/usr/bin/env python3
"""Plan and run fail-closed, change-aware Cambium CI verification.

Pull requests should prove the behavior they can affect, rather than rerun the
entire suite after every edit.  This planner deliberately keeps the selective
boundary narrow:

* Markdown-only changes are covered by the repository's deterministic gates.
* A changed test module runs that module.
* A changed leaf Tool runs tests that import or invoke it, including tests of
  Tool modules that depend on it.
* Shared authority, schemas, generated contracts, CI policy, unknown paths,
  deletions, and renames fall back to the complete suite.
* Local-only process directories fail validation if any path under them enters
  the Git index, even when an ignore rule was bypassed with force-add.

Pushes to the default branch and manual dispatches always receive the complete
Python 3.10/3.14 suite.  The emitted plan is JSON so every selection decision
is visible in the GitHub Actions job summary.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import statistics
import subprocess
import sys
import time
import zipfile

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "Tools"
for import_root in (REPOSITORY_ROOT, TOOLS_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import Tools.execution.context_delivery.card_contract as card_contract  # noqa: E402
import Tools.execution.context_delivery.read_set_contract as read_set_contract  # noqa: E402
import Tools.governance.profile.profile_layout_contract as profile_layout_contract  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts  # noqa: E402
import Tools.platform.distribution.test_runner as test_runner  # noqa: E402


PYTHON_VERSIONS = ("3.10", "3.14")
CI_TARGET_SECONDS = 300
CI_LIMIT_SECONDS = 360
MAX_SELECTIVE_TESTS = 24
TEST_NAME_RE = re.compile(r"test_[a-z0-9_]+\.py\Z")


def _timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("CI metadata requires a UTC timestamp")
    return datetime.fromisoformat(value[:-1] + "+00:00").timestamp()


def required_job_names(plan):
    """Derive exact required job membership from the selection, not timings."""
    names = ["Impact plan", "ci-required"]
    names.extend("Contracts · Py%s" % row["python-version"]
                 for row in plan["check_matrix"]["include"])
    if plan["run_tests"]:
        names.extend("%s · Py%s" % (row["test-label"], row["python-version"])
                     for row in plan["test_matrix"]["include"])
    if len(names) != len(set(names)):
        raise ValueError("required job identities must be unique")
    return sorted(names)


def run_budget(run, *, run_id, attempt, observed_at):
    """One engineering deadline for an entire official workflow attempt.

    First-attempt queue time remains inside the budget. A rerun uses its
    official attempt start, while retaining elapsed time since first creation.
    This is CI acceptance, never a governance or Receipt verdict.
    """
    if (not isinstance(run, dict) or type(run_id) is not int or type(attempt) is not int or
            run_id < 1 or attempt < 1 or run.get("id") != run_id or
            run.get("run_attempt") != attempt):
        raise ValueError("CI metadata does not identify the requested run/attempt")
    created = _timestamp(run.get("created_at"))
    started = _timestamp(run.get("run_started_at"))
    now = _timestamp(observed_at)
    if not created <= started <= now:
        raise ValueError("CI run timestamps are inconsistent")
    origin = created if attempt == 1 else started
    elapsed = now - origin
    return {
        "run_id": run_id, "attempt": attempt,
        "origin": run["created_at"] if attempt == 1 else run["run_started_at"],
        "deadline": origin + CI_LIMIT_SECONDS,
        "target_seconds": CI_TARGET_SECONDS, "limit_seconds": CI_LIMIT_SECONDS,
        "elapsed_seconds": elapsed, "since_creation_seconds": now - created,
        "run_start_delay_seconds": started - created if attempt == 1 else None,
        "remaining_seconds": max(0, CI_LIMIT_SECONDS - elapsed),
        "within_limit": elapsed <= CI_LIMIT_SECONDS,
        "target_met": elapsed <= CI_TARGET_SECONDS,
    }


def required_budget_verdict(run, jobs, expected, *, run_id, attempt,
                            observed_at, final=False):
    """Verify coverage and wall time without adding parallel job durations.

    An executing gate proves only an observation. Publication must call this
    again with final=True and the gate's real completed_at. Unknown skipped
    placeholders cannot satisfy a required job or mask a missing matrix row.
    """
    if (not isinstance(expected, list) or not expected or
            any(not isinstance(name, str) or not name for name in expected) or
            len(expected) != len(set(expected)) or
            not {"Impact plan", "ci-required"}.issubset(expected)):
        raise ValueError("required job membership is missing or ambiguous")
    if not isinstance(jobs, list):
        raise ValueError("CI job metadata must be a list")
    by_name = {}
    identities = set()
    for job in jobs:
        if (not isinstance(job, dict) or job.get("run_id") != run_id or job.get("run_attempt") != attempt or
                type(job.get("id")) is not int or job["id"] in identities):
            raise ValueError("job metadata repeats or belongs to another run/attempt")
        identities.add(job["id"])
        name = job.get("name")
        if name not in expected:
            if job.get("conclusion") == "skipped" and job.get("status") == "completed":
                continue
            raise ValueError("unexpected active job in required workflow: %s" % name)
        if name in by_name:
            raise ValueError("required job name is ambiguous: %s" % name)
        by_name[name] = job
    if set(by_name) != set(expected):
        raise ValueError("required job metadata is incomplete")
    gate = by_name["ci-required"]
    finish = gate.get("completed_at") if final else observed_at
    budget = run_budget(run, run_id=run_id, attempt=attempt, observed_at=finish)
    if _timestamp(finish) > _timestamp(observed_at):
        raise ValueError("completed gate is later than the metadata observation")
    origin = _timestamp(budget["origin"])
    job_waits = {}
    for name, job in by_name.items():
        start = _timestamp(job.get("started_at"))
        if not origin <= start <= _timestamp(finish):
            raise ValueError("job start is outside the current attempt")
        if name == "ci-required" and not final:
            if job.get("status") != "in_progress" or job.get("completed_at") is not None:
                raise ValueError("gate observation is not from the executing gate")
        elif (job.get("status") != "completed" or job.get("conclusion") != "success" or
              not start <= _timestamp(job.get("completed_at")) <= _timestamp(finish)):
            raise ValueError("required job did not complete successfully: %s" % name)
        created = job.get("created_at")
        if created is not None and not origin <= _timestamp(created) <= start:
            raise ValueError("job creation is outside the current attempt")
        job_waits[name] = start - _timestamp(created) if created is not None else None
    return {**budget, "final": final, "required_jobs": sorted(by_name),
            "job_start_delay_seconds": job_waits,
            "job_wait_basis": "created_at to started_at; includes scheduling/dependency delay; not subtracted",
            "result": "passed" if budget["within_limit"] else "budget-exceeded"}


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_metadata(repository, run_id, attempt, *, include_jobs=False):
    """Read one official attempt, including every job page when requested."""
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or "") or
            type(run_id) is not int or run_id < 1 or
            type(attempt) is not int or attempt < 1):
        raise ValueError("repository, run ID and attempt are required")
    endpoint = "repos/%s/actions/runs/%d/attempts/%d" % (repository, run_id, attempt)
    # Bound this whole metadata read, not each page independently.
    stop = time.monotonic() + 15
    def api(path, paginate=False):
        remaining = stop - time.monotonic()
        if remaining <= 0:
            raise ValueError("CI metadata read deadline exceeded")
        response = subprocess.run(
            ["gh", "api", path] + (["--paginate", "--slurp"] if paginate else []),
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=remaining)
        return json.loads(response.stdout)
    run = api(endpoint)
    if not include_jobs:
        return run, []
    pages = api(endpoint + "/jobs?per_page=100", paginate=True)
    if not isinstance(pages, list) or not pages:
        raise ValueError("CI job pages are missing")
    if not all(isinstance(page, dict) for page in pages):
        raise ValueError("CI job pages must be objects")
    count = pages[0].get("total_count")
    if type(count) is not int or count < 1:
        raise ValueError("CI job count is missing")
    jobs = []
    for page in pages:
        if page.get("total_count") != count or not isinstance(page.get("jobs"), list):
            raise ValueError("CI job pages are inconsistent")
        jobs.extend(page["jobs"])
    if len(jobs) != count:
        raise ValueError("CI job pagination is incomplete")
    return run, jobs

FULL_EXACT_PATHS = {
    ".gitignore",
    "Makefile",
    ".github/scripts/ci_impact.py",
    "Tools/platform/common/kblib.py",
    "Tools/platform/distribution/module_boundary_facts.py",
    "Tools/tests/support/profile_fixture.py",
    "Tools/tests/test_ci_impact.py",
}
FULL_PREFIXES = (
    ".github/",
    "Tools/schemas/",
    "Tools/tests/fixtures/",
)
# Tools/compiled/ is regenerated alongside every Tool change.  While it was a
# full trigger, every Tool change also tripped it, and the selective path went
# unreached in 22 consecutive runs -- the planner had a branch nobody could
# enter.  Tampering with a compiled artifact is caught by the four --check
# gates, which run in every mode, so the full suite was not what protected it.
CHECK_ONLY_PREFIXES = ("assets/readme/", "LICENSES/", "Tools/compiled/")

# mcp_server reaches every tool through its command line rather than its
# imports, so no reverse-import closure can ever include it. The Tool module
# boundary contract names
# this blind spot exactly: subprocess invocation consumes a registered CLI
# surface, which the import rules do not see.  Declaring the edge is the
# remedy the contract asks for; hoping the graph finds it is not.
CLI_SURFACE_TESTS = ("test_mcp_server.py",)
FORBIDDEN_TRACKED_PREFIXES = ("docs/", "_to_delete/")
CHECK_ONLY_ROOT_FILES = {
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "README.zh-CN.md",
    "ROADMAP.md",
    "ROADMAP.zh-CN.md",
    "SECURITY.md",
}


def check_only_markdown_prefixes(root):
    """Project governance Markdown roots from their machine owners."""
    root = Path(root)
    return (
        "kernel/",
        card_contract.load_schema(root)["path_prefix"],
        read_set_contract.load_schema(root)["path_prefix"],
        profile_layout_contract.PROFILES_DIRECTORY + "/",
    )


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    old_path: str = ""


def _normal_path(value):
    path = PurePosixPath(value)
    rendered = path.as_posix()
    if path.is_absolute() or rendered == ".." or rendered.startswith("../"):
        raise ValueError("changed path must be repository-relative: %s" % value)
    return rendered


def parse_name_status(raw):
    """Parse ``git diff --name-status -z`` output."""
    fields = raw.decode("utf-8").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    changes = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            raise ValueError("empty git diff status")
        kind = status[0]
        if kind in {"R", "C"}:
            if index + 1 >= len(fields):
                raise ValueError("truncated rename/copy record")
            old_path = _normal_path(fields[index])
            path = _normal_path(fields[index + 1])
            index += 2
            changes.append(Change(kind, path, old_path))
        else:
            if index >= len(fields):
                raise ValueError("truncated git diff record")
            changes.append(Change(kind, _normal_path(fields[index])))
            index += 1
    return changes


def forbidden_tracked_paths(paths):
    """Return tracked paths that belong to local-only repository roots."""
    return sorted(
        path for path in paths
        if path.startswith(FORBIDDEN_TRACKED_PREFIXES)
    )


def validate_repository_layout(root):
    """Fail when the Git index contains a local-only process path."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(root),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError("cannot inspect Git index: %s" %
                         (detail or "git ls-files failed"))
    paths = [
        path for path in result.stdout.decode(
            "utf-8", errors="surrogateescape").split("\0")
        if path
    ]
    violations = forbidden_tracked_paths(paths)
    if violations:
        raise ValueError(
            "local-only paths are tracked: %s" % ", ".join(violations))
    return len(paths)


def git_changes(root, base, head):
    merge_base = subprocess.run(
        ["git", "merge-base", base, head], cwd=str(root),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.decode("ascii").strip()
    raw = subprocess.run(
        ["git", "diff", "--name-status", "-z", merge_base, head],
        cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True,
    ).stdout
    return merge_base, parse_name_status(raw)


def discover_tests(root):
    tests = []
    test_root = root / "Tools" / "tests"
    for path in sorted(test_root.glob("test_*.py")):
        if path.is_file() and TEST_NAME_RE.fullmatch(path.name):
            tests.append(path.name)
    if not tests:
        raise ValueError("no Tools/tests/test_*.py files found")
    return tests


def _imports(path, local_modules):
    return set(module_boundary_facts.source_imports(
        path.read_text(encoding="utf-8"), local_modules,
        filename=str(path)))


def impacted_tool_tests(root, changed_tool_paths):
    facts = module_boundary_facts.collect(str(root))
    local_modules = set(facts)
    modules_by_path = {
        "Tools/" + row["path"]: module
        for module, row in facts.items()
    }
    changed_modules = {
        modules_by_path[path] for path in changed_tool_paths
        if path in modules_by_path
    }
    if len(changed_modules) != len(set(changed_tool_paths)):
        return set(), "changed Tool is absent from the shipped recursive module tree"

    tool_imports = module_boundary_facts.import_graph(facts)
    affected = set(changed_modules)
    changed = True
    while changed:
        changed = False
        for module, imports in tool_imports.items():
            if module not in affected and set(imports).intersection(affected):
                affected.add(module)
                changed = True

    available = set(discover_tests(root))
    selected = set()
    for test_name in sorted(available):
        test_path = root / "Tools" / "tests" / test_name
        imports = _imports(test_path, local_modules)
        text = test_path.read_text(encoding="utf-8")
        referenced = any(
            (module in imports) or
            ("Tools/%s" % facts[module]["path"] in text) or
            (Path(facts[module]["path"]).name != "__init__.py" and
             Path(facts[module]["path"]).name in text)
            for module in affected
        )
        if referenced:
            selected.add(test_name)

    for module in affected:
        conventional = {
            "test_%s.py" % module.rsplit(".", 1)[-1],
            "test_%s.py" % module.replace(".", "_"),
        }
        selected.update(conventional.intersection(available))
    if not selected:
        return set(), "no test imports or invokes the affected Tool closure"
    selected.update(name for name in CLI_SURFACE_TESTS if name in available)
    return selected, "affected Tool closure: %s" % ", ".join(sorted(affected))


# CI owns placement only; Catalog and runner retain selection and isolation.
FULL_SHARD_COUNT = 10
SHARD_WORKERS = 2


def _historical_costs(repository, *, deadline=None):
    """Read at most two successful main runs; absence cannot suppress tests."""
    result = {"samples": {}, "runs": [], "status": "unavailable"}
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or ""):
        return result
    # Advisory placement cannot consume the verification budget while retrying
    # several independent network timeouts. Missing history keeps all tests.
    allowance = min(5, deadline - time.time()) if deadline is not None else 5
    stop = time.monotonic() + allowance
    def api(path):
        remaining = stop - time.monotonic()
        if remaining <= 0:
            raise ValueError("advisory CI history deadline exceeded")
        completed = subprocess.run(
            ["gh", "api", "repos/%s/%s" % (repository, path)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining)
        return completed.stdout
    try:
        runs = json.loads(api(
            "actions/workflows/verify.yml/runs?branch=main&event=push&status=success&per_page=2"))
        for run in runs.get("workflow_runs", [])[:2]:
            if run.get("event") != "push" or run.get("head_branch") != "main" or run.get("conclusion") != "success":
                continue
            raw = api("actions/runs/%d/logs" % int(run["id"]))
            if len(raw) > 50_000_000:
                continue
            metadata = {key: run.get(key) for key in
                        ("id", "head_sha", "run_attempt", "created_at", "html_url")}
            observed = {}
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for info in archive.infolist():
                    if info.file_size > 10_000_000:
                        continue
                    log = archive.read(info).decode("utf-8", errors="replace")
                    version = re.search(r"Successfully set up CPython \((3\.\d+\.\d+)", log)
                    if version is None:
                        continue
                    runner_image = re.search(r"Image: ([^\r\n]+)", log)
                    for match in re.finditer(
                            r"test runner: suite=full module=\d+/\d+ path=Tools/tests/(test_[a-z0-9_]+\.py) "
                            r"cases=(\d+) mode=(parallel|serial) elapsed=([0-9.]+)s exit=0", log):
                        name, cases, mode, elapsed = match.groups()
                        value = float(elapsed)
                        if value > 0 and math.isfinite(value):
                            observed[(version[1], name)] = {
                                "seconds": value, "python": version[1], "cases": int(cases),
                                "runner_image": runner_image[1][:80] if runner_image else None,
                                "mode": mode, "run": run["id"], "revision": run["head_sha"]}
            for (_version, name), sample in sorted(observed.items()):
                result["samples"].setdefault(name, []).append(sample)
            result["runs"].append(metadata)
        result["status"] = "observed" if result["samples"] else "no-module-observations"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile):
        result["status"] = "partial" if result["samples"] else "unavailable"
    return result


def _scheduling_facts(root, names, samples):
    """Use the generated Catalog as advisory placement data, never admission."""
    try:
        catalog = json.loads((root / "Tools/compiled/test-catalog.json").read_text(encoding="utf-8"))
        modules = {Path(row["path"]).name: row for row in catalog["modules"]}
    except (OSError, ValueError, KeyError, TypeError):
        modules = {}
    facts = {}
    for name in names:
        cases = modules.get(name, {}).get("cases", [])
        observed = [row["seconds"] for row in samples.get(name, [])
                    if isinstance(row.get("seconds"), (int, float))
                    and not isinstance(row["seconds"], bool)
                    and math.isfinite(row["seconds"]) and row["seconds"] > 0]
        try:
            size = (root / "Tools/tests" / name).stat().st_size
        except OSError:
            size = 1
        facts[name] = {
            "seconds": statistics.median(observed) if observed else max(0.1, size / 1024),
            "cost_basis": "observed-median-estimate" if observed else "source-size-fallback",
            "samples": len(observed),
            "parallel_safe": bool(cases) and all(row.get("parallel_safe") is True for row in cases),
            "e2e": any(row.get("level") == "e2e" for row in cases),
        }
    # Calibrate fallback bytes to observed seconds rather than mixing units.
    ratios = []
    for name in names:
        if facts[name]["samples"]:
            try:
                ratios.append(facts[name]["seconds"] / max(1, (root / "Tools/tests" / name).stat().st_size))
            except OSError:
                pass
    if ratios:
        ratio = statistics.median(ratios)
        for name in names:
            if not facts[name]["samples"]:
                facts[name]["seconds"] = max(0.1, facts[name]["seconds"] * 1024 * ratio)
    return facts


def _estimated_makespan(names, facts):
    workers = [0.0] * SHARD_WORKERS
    serial = 0.0
    for name in sorted(names, key=lambda key: (-facts[key]["seconds"], key)):
        row = facts[name]
        if row["parallel_safe"]:
            workers[workers.index(min(workers))] += row["seconds"]
        else:
            serial += row["seconds"]
    return serial + max(workers)


def _matrix(root, versions, tests, prefix, samples=None):
    """Place the exact selected set once, accounting for file isolation."""
    expected = sorted(tests)
    if len(expected) != len(set(expected)):
        raise ValueError("CI selected files must be unique")
    if not expected:
        return {"include": []}
    facts = _scheduling_facts(Path(root), expected, samples or {})
    count = min(FULL_SHARD_COUNT, len(expected))
    # Complete lifecycle modules keep a dedicated job when capacity permits.
    lifecycle = [name for name in expected if facts[name]["e2e"]]
    isolated = lifecycle if len(lifecycle) < count else []
    groups = [[name] for name in isolated] + [[] for _ in range(count - len(isolated))]
    for name in sorted(set(expected) - set(isolated), key=lambda key: (-facts[key]["seconds"], key)):
        available = range(len(isolated), len(groups))
        chosen = min(available, key=lambda index: (
            _estimated_makespan(groups[index] + [name], facts), index))
        groups[chosen].append(name)
    groups = [sorted(group) for group in groups if group]
    assigned = sorted(name for group in groups for name in group)
    if assigned != expected:
        raise ValueError("CI groups must cover every test file exactly once")
    rows = []
    for version in versions:
        for index, group in enumerate(groups):
            label = ("Lifecycle" if index < len(isolated) else "Tools")
            label += " " + chr(ord("A") + (index if index < len(isolated) else index - len(isolated)))
            rows.append({
                "python-version": version, "shard": "%s-%02d" % (prefix, index + 1),
                "test-label": label, "test-files": ",".join(group),
                "estimated-seconds": round(_estimated_makespan(group, facts), 3),
                "observed-modules": sum(bool(facts[name]["samples"]) for name in group),
            })
    return {"include": rows}


def _full_plan(root, changed, reasons):
    tests = discover_tests(root)
    return {
        "mode": "full",
        "reasons": reasons,
        "changed": [change.__dict__ for change in changed],
        "check_versions": list(PYTHON_VERSIONS),
        "selected_tests": tests,
        "check_matrix": {
            "include": [{"python-version": value}
                        for value in PYTHON_VERSIONS],
        },
        "test_matrix": _matrix(root, PYTHON_VERSIONS, tests, "full"),
        "run_tests": True,
    }


def plan_changes(root, changes, event="pull_request"):
    root = Path(root).resolve()
    changes = list(changes)
    if event != "pull_request":
        return _full_plan(
            root, changes,
            ["%s events always run the complete verification suite" % event],
        )
    if not changes:
        return _full_plan(root, changes, ["empty or unavailable diff is fail-closed"])
    try:
        markdown_prefixes = check_only_markdown_prefixes(root)
    except (card_contract.CardContractError,
            read_set_contract.ReadSetContractError) as error:
        return _full_plan(
            root, changes,
            ["governance path contract is invalid: %s" % error],
        )

    full_reasons = []
    selected = set()
    tool_paths = []
    python_changed = False
    check_only = []

    for change in changes:
        path = change.path
        if change.status not in {"A", "M"} or change.old_path:
            full_reasons.append(
                "%s change requires complete verification: %s" %
                (change.status, path))
            continue
        if path in FULL_EXACT_PATHS or path.startswith(FULL_PREFIXES):
            full_reasons.append("shared CI authority changed: %s" % path)
            continue
        if path.startswith("Tools/tests/test_") and path.endswith(".py"):
            name = Path(path).name
            if not TEST_NAME_RE.fullmatch(name) or not (root / path).is_file():
                full_reasons.append("invalid or absent test module: %s" % path)
            else:
                selected.add(name)
                python_changed = True
            continue
        if path.startswith("Tools/") and path.endswith(".py"):
            tool_paths.append(path)
            python_changed = True
            continue
        if path == "Tools/README.md":
            inventory_test = "test_tools_readme_inventory.py"
            if (root / "Tools" / "tests" / inventory_test).is_file():
                selected.add(inventory_test)
            else:
                full_reasons.append("Tools README inventory test is absent")
            continue
        if path in CHECK_ONLY_ROOT_FILES or path.startswith(CHECK_ONLY_PREFIXES) \
                or (path.endswith(".md") and
                    path.startswith(markdown_prefixes)):
            check_only.append(path)
            continue
        full_reasons.append("unclassified path is fail-closed: %s" % path)

    if tool_paths and not full_reasons:
        try:
            tool_tests, reason = impacted_tool_tests(root, tool_paths)
        except (OSError, SyntaxError, ValueError) as error:
            full_reasons.append("Tool dependency analysis failed: %s" % error)
        else:
            if not tool_tests:
                full_reasons.append(reason)
            else:
                selected.update(tool_tests)
                check_only.append(reason)

    if len(selected) > MAX_SELECTIVE_TESTS:
        full_reasons.append(
            "selective closure has %d tests, above the %d-test safety limit" %
            (len(selected), MAX_SELECTIVE_TESTS))
    if full_reasons:
        return _full_plan(root, changes, full_reasons)

    check_versions = list(PYTHON_VERSIONS if python_changed else ("3.14",))
    base = {
        "reasons": check_only or ["direct test-module change"],
        "changed": [change.__dict__ for change in changes],
        "check_versions": check_versions,
        "selected_tests": sorted(selected),
        "check_matrix": {
            "include": [{"python-version": value}
                        for value in check_versions],
        },
    }
    if not selected:
        base.update({
            "mode": "checks-only",
            "test_matrix": {"include": []},
            "run_tests": False,
        })
        return base
    base.update({
        "mode": "selective",
        "test_matrix": _matrix(root, check_versions, selected, "affected"),
        "run_tests": True,
    })
    return base


def _write_github_outputs(path, plan):
    compact = lambda value: json.dumps(
        value, sort_keys=True, separators=(",", ":"))
    values = {
        "mode": plan["mode"],
        "run_tests": str(plan["run_tests"]).lower(),
        "check_matrix": compact(plan["check_matrix"]),
        "test_matrix": compact(plan["test_matrix"]),
        "required_jobs": compact(required_job_names(plan)),
        "job_timeout_minutes": str(math.ceil(CI_LIMIT_SECONDS / 60)),
    }
    if "budget" in plan:
        values["deadline"] = str(plan["budget"]["deadline"])
    with Path(path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write("%s=%s\n" % (key, value))


def validate_selected_tests(root, value):
    available = set(discover_tests(root))
    names = [item for item in value.split(",") if item]
    if not names:
        raise ValueError("selected test list must not be empty")
    if len(names) != len(set(names)):
        raise ValueError("selected test list contains duplicates")
    for name in names:
        if not TEST_NAME_RE.fullmatch(name) or name not in available:
            raise ValueError("unknown selected test module: %s" % name)
    return names


def run_selected_tests(root, value, jobs=SHARD_WORKERS, report=None, deadline=None):
    """Delegate an exact shard to the same catalog runner as local full runs.

    CI owns impact selection, not another loader or isolation policy. The
    existing runner keeps module-local fixtures together, honors parallel_safe,
    and reports each module's elapsed time and result.
    """
    names = validate_selected_tests(root, value)
    root = Path(root).resolve()
    print("selected_test_modules = %s" % ",".join(names), flush=True)
    return test_runner.main([
        "full", "--root", str(root), "--python", sys.executable,
        "--test-files", ",".join(names), "--jobs", str(jobs),
    ] + (["--report", report] if report else [])
      + (["--deadline", str(deadline)] if deadline is not None else []))


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--root", default=".")
    plan_parser.add_argument("--event", default="pull_request")
    plan_parser.add_argument("--base")
    plan_parser.add_argument("--head")
    plan_parser.add_argument("--plan-path")
    plan_parser.add_argument("--github-output")
    plan_parser.add_argument("--cost-history", action="store_true", help="read advisory costs from recent successful main runs")
    plan_parser.add_argument("--ci-budget", action="store_true",
                             help="bind the plan to the official workflow attempt deadline")

    budget_parser = subparsers.add_parser("budget")
    budget_parser.add_argument("--repository", required=True)
    budget_parser.add_argument("--run-id", type=int, required=True)
    budget_parser.add_argument("--attempt", type=int, required=True)
    budget_parser.add_argument("--expected-jobs", required=True,
                               help="exact JSON job list from the impact plan")
    budget_parser.add_argument("--final", action="store_true",
                               help="require the gate's actual completed_at for publication")

    step_parser = subparsers.add_parser("run-step",
        help="execute a Linux CI preparation/check command within the shared deadline")
    step_parser.add_argument("--deadline", type=float, required=True)
    step_parser.add_argument("argv", nargs=argparse.REMAINDER)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--root", default=".")

    run_parser = subparsers.add_parser("run-tests")
    run_parser.add_argument("--root", default=".")
    run_parser.add_argument("--tests", required=True)
    run_parser.add_argument("--jobs", type=int, default=SHARD_WORKERS,
                            help="parallel-safe files per CI shard (default: %(default)s)")
    run_parser.add_argument("--report", help="new cost report outside the repository")
    run_parser.add_argument("--deadline", type=float,
                            help="shared workflow execution deadline")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.command == "run-step":
        command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        remaining = args.deadline - time.time()
        if not command or not math.isfinite(remaining) or remaining <= 0:
            print("ci-budget: no command or no execution time remaining", file=sys.stderr)
            return 124
        try:
            # Replace this adapter; GNU timeout owns the temporary process
            # group. Test modules instead use the catalog runner's deadline
            # so their progress and owned fixture cleanup survive expiry.
            os.execvp("timeout", ["timeout", "--kill-after=1s", "--",
                                  str(remaining), *command])
        except OSError as error:
            print("ci-budget: cannot start bounded CI step: %s" % error, file=sys.stderr)
            return 1
        return 0
    if args.command == "budget":
        try:
            run, jobs = _run_metadata(args.repository, args.run_id, args.attempt, include_jobs=True)
            verdict = required_budget_verdict(
                run, jobs, json.loads(args.expected_jobs), run_id=args.run_id,
                attempt=args.attempt, observed_at=_utc_now(), final=args.final)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            print("ci-budget: cannot establish required result: %s" % error, file=sys.stderr)
            return 1
        print(json.dumps(verdict, sort_keys=True, indent=2))
        return 0 if verdict["result"] == "passed" else 1
    root = Path(args.root).resolve()
    if args.command == "validate":
        try:
            tracked_count = validate_repository_layout(root)
        except (OSError, ValueError) as error:
            print("ci-impact: %s" % error, file=sys.stderr)
            return 1
        tests = discover_tests(root)
        _matrix(root, PYTHON_VERSIONS, tests, "full")
        print("repository_layout_tracked_files = %d" % tracked_count)
        print("ci_impact_tests = %d" % len(tests))
        return 0
    if args.command == "run-tests":
        try:
            return run_selected_tests(root, args.tests, args.jobs, args.report, args.deadline)
        except ValueError as error:
            print("ci-impact: %s" % error, file=sys.stderr)
            return 1

    if args.event == "pull_request":
        if not args.base or not args.head:
            raise SystemExit("pull_request planning requires --base and --head")
        merge_base, changes = git_changes(root, args.base, args.head)
    else:
        merge_base = args.base or ""
        changes = []
    plan = plan_changes(root, changes, event=args.event)
    if args.ci_budget:
        try:
            run_id = int(os.environ["GITHUB_RUN_ID"])
            attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
            run, _jobs = _run_metadata(os.environ["GITHUB_REPOSITORY"], run_id, attempt)
            plan["budget"] = run_budget(run, run_id=run_id, attempt=attempt, observed_at=_utc_now())
            if not plan["budget"]["within_limit"]:
                raise ValueError("workflow budget expired before scheduling")
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            print("ci-budget: %s" % error, file=sys.stderr)
            return 1
    history = _historical_costs(os.environ.get("GITHUB_REPOSITORY"),
        deadline=plan.get("budget", {}).get("deadline")) if args.cost_history else {
        "samples": {}, "runs": [], "status": "not-requested"}
    if plan["run_tests"]:
        plan["test_matrix"] = _matrix(root, plan["check_versions"], plan["selected_tests"],
            "full" if plan["mode"] == "full" else "affected", history["samples"])
    plan["cost_history"] = history
    plan["result_reuse"] = {"enabled": False, "status": "not-proven",
        "reason": "Prior head SHAs and module timings do not prove actual checkout tree, toolchain or complete required-check equivalence; main still executes all checks."}
    plan["base_sha"] = args.base or ""
    plan["head_sha"] = args.head or ""
    plan["merge_base_sha"] = merge_base
    plan["required_jobs"] = required_job_names(plan)
    rendered = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.plan_path:
        Path(args.plan_path).write_text(rendered + "\n", encoding="utf-8")
    if args.github_output:
        _write_github_outputs(args.github_output, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
