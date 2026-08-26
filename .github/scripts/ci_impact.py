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
import ast
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "Tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import card_contract  # noqa: E402
import profile_layout_contract  # noqa: E402
import read_set_contract  # noqa: E402


PYTHON_VERSIONS = ("3.10", "3.14")
MAX_SELECTIVE_TESTS = 24
TEST_NAME_RE = re.compile(r"test_[a-z0-9_]+\.py\Z")

FULL_EXACT_PATHS = {
    ".gitignore",
    "Makefile",
    ".github/scripts/ci_impact.py",
    "Tools/kblib.py",
    "Tools/tests/profile_fixture.py",
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
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidate = alias.name.split(".")[0]
                if candidate == "Tools" and "." in alias.name:
                    candidate = alias.name.split(".")[1]
                if candidate in local_modules:
                    found.add(candidate)
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            candidate = parts[1] if parts[0] == "Tools" and len(parts) > 1 \
                else parts[0]
            if candidate in local_modules:
                found.add(candidate)
            if node.module == "Tools":
                for alias in node.names:
                    if alias.name in local_modules:
                        found.add(alias.name)
    return found


def impacted_tool_tests(root, changed_tool_paths):
    tool_paths = {
        path.stem: path
        for path in (root / "Tools").glob("*.py")
        if path.is_file()
    }
    local_modules = set(tool_paths)
    changed_modules = {
        Path(path).stem for path in changed_tool_paths
        if Path(path).stem in local_modules
    }
    if len(changed_modules) != len(changed_tool_paths):
        return set(), "changed Tool is absent or is not a top-level Python module"

    tool_imports = {
        module: _imports(path, local_modules)
        for module, path in tool_paths.items()
    }
    affected = set(changed_modules)
    changed = True
    while changed:
        changed = False
        for module, imports in tool_imports.items():
            if module not in affected and imports.intersection(affected):
                affected.add(module)
                changed = True

    selected = set()
    for test_name in discover_tests(root):
        test_path = root / "Tools" / "tests" / test_name
        imports = _imports(test_path, local_modules)
        text = test_path.read_text(encoding="utf-8")
        referenced = any(
            (module in imports) or
            ("Tools/%s.py" % module in text) or
            ("%s.py" % module in text)
            for module in affected
        )
        if referenced:
            selected.add(test_name)

    for module in affected:
        conventional = "test_%s.py" % module
        if conventional in discover_tests(root):
            selected.add(conventional)
    if not selected:
        return set(), "no test imports or invokes the affected Tool closure"
    available = set(discover_tests(root))
    selected.update(name for name in CLI_SURFACE_TESTS if name in available)
    return selected, "affected Tool closure: %s" % ", ".join(sorted(affected))


# How many ways this repository shards, named once.  Selective mode reads the
# length rather than restating it, so changing the split changes both.
FULL_SHARD_RANGES = (
    ("a-b", "ab"),
    ("c-m", "cdefghijklm"),
    ("n-r", "nopqr"),
    ("s-z", "stuvwxyz"),
)


def _full_groups(test_names):
    ranges = FULL_SHARD_RANGES
    groups = []
    assigned = []
    for name, letters in ranges:
        members = [
            test_name for test_name in test_names
            if test_name[len("test_")] in letters
        ]
        if not members:
            raise ValueError("full CI group %s is empty" % name)
        groups.append((name, members))
        assigned.extend(members)
    if sorted(assigned) != sorted(test_names) or len(assigned) != len(set(assigned)):
        raise ValueError("full CI groups must cover every test file exactly once")
    return groups


def _test_weight(root, test_name):
    """A self-maintaining stand-in for how long one test file takes.

    Byte size is not the cost, but it tracks it closely enough to pack bins:
    against measured per-file wall clock across the whole suite it correlates
    at r = 0.80, and packing on it puts the worst bin at 1.26x a perfect
    split where round-robin puts it at 1.59x.  It is chosen over a recorded
    duration table because a table goes stale in silence -- a file can double
    in cost while the number claiming otherwise sits unchanged -- and a file
    cannot disagree with its own size.
    """
    try:
        return (root / "Tools" / "tests" / test_name).stat().st_size
    except OSError:
        return 0


def _selective_groups(root, test_names):
    """Shard the selected set, the way full mode already shards its own.

    A selective plan that ran in one job was slower than the full matrix it
    exists to avoid: nine modules measured 451-525s on a runner, against a
    worst full-mode shard well under that, and the widest closure projects
    past the job timeout outright.  Splitting is the fix; the packing order
    only decides how even the split is.

    The bin count follows full mode rather than restating it, so changing how
    this repository shards changes both together.
    """
    expected = sorted(test_names)
    count = min(len(FULL_SHARD_RANGES), len(expected))
    members = [[] for _ in range(count)]
    loads = [0] * count
    for name in sorted(expected, key=lambda item: (-_test_weight(root, item), item)):
        lightest = loads.index(min(loads))
        members[lightest].append(name)
        loads[lightest] += _test_weight(root, name)

    groups = [("affected-%d" % (index + 1), sorted(bin_names))
              for index, bin_names in enumerate(members) if bin_names]

    # The assertion full mode makes, for the same reason: a packing bug must
    # fail the planner rather than quietly drop a test file.
    assigned = sorted(name for _, bin_names in groups for name in bin_names)
    if assigned != expected or len(assigned) != len(set(assigned)):
        raise ValueError(
            "selective CI groups must cover every test file exactly once")
    return groups


def _matrix(versions, groups):
    include = []
    for version in versions:
        for name, tests in groups:
            include.append({
                "python-version": version,
                "shard": name,
                "test-files": ",".join(tests),
            })
    return {"include": include}


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
        "test_matrix": _matrix(PYTHON_VERSIONS, _full_groups(tests)),
        "run_tests": True,
    }


def plan_changes(root, changes, event="pull_request"):
    root = Path(root).resolve()
    changes = list(changes)
    if event != "pull_request":
        return _full_plan(
            root, changes,
            ["%s events always run the complete compatibility suite" % event],
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
        if path.startswith("Tools/") and path.count("/") == 1 \
                and path.endswith(".py"):
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
    groups = _selective_groups(root, selected)
    base.update({
        "mode": "selective",
        "test_matrix": _matrix(check_versions, groups),
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
    }
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


def run_selected_tests(root, value):
    names = validate_selected_tests(root, value)
    root = Path(root).resolve()
    for import_root in (root, root / "Tools", root / "Tools" / "tests"):
        import_string = str(import_root)
        if import_string not in sys.path:
            sys.path.insert(0, import_string)
    modules = ["Tools.tests.%s" % Path(name).stem for name in names]
    print("selected_test_modules = %s" % ",".join(names))
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    if suite.countTestCases() == 0:
        print("ci-impact: selected test modules contain no tests", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


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

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--root", default=".")

    run_parser = subparsers.add_parser("run-tests")
    run_parser.add_argument("--root", default=".")
    run_parser.add_argument("--tests", required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "validate":
        try:
            tracked_count = validate_repository_layout(root)
        except (OSError, ValueError) as error:
            print("ci-impact: %s" % error, file=sys.stderr)
            return 1
        tests = discover_tests(root)
        _full_groups(tests)
        print("repository_layout_tracked_files = %d" % tracked_count)
        print("ci_impact_tests = %d" % len(tests))
        return 0
    if args.command == "run-tests":
        try:
            return run_selected_tests(root, args.tests)
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
    plan["base_sha"] = args.base or ""
    plan["head_sha"] = args.head or ""
    plan["merge_base_sha"] = merge_base
    rendered = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.plan_path:
        Path(args.plan_path).write_text(rendered + "\n", encoding="utf-8")
    if args.github_output:
        _write_github_outputs(args.github_output, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
