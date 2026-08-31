#!/usr/bin/env python3
"""Check the Tool-owned Kernel leaf-size engineering policy.

The policy is a repository-maintenance contract, not a Kernel governance
rule.  This checker enumerates every numbered Kernel leaf, measures its source
bytes, and compares the result with ``Tools/kernel-size-policy.yaml``.  It
never edits a page or refreshes the recorded measurements while checking.

Exit codes:
  0 = the policy is structurally valid and no measurement needs review
  1 = the policy or repository state is unsafe or a growth cap is exceeded
  2 = no failure, but an undeclared soft-cap breach or stale measurement needs
      engineering review
"""

import json
import os
from pathlib import Path
import re
import sys

import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.platform.repository import repository as tool_repository  # noqa: E402
from Tools.platform.repository import path_contract as repository_path_contract  # noqa: E402


TOOL = "check_kernel_size"
TOOL_VERSION = "1.0.0"
POLICY_PATH = "Tools/kernel-size-policy.yaml"
POLICY_FIELDS = frozenset((
    "schema_version", "policy_id", "kernel_root", "leaf_path_regex",
    "engineering_record", "target_bytes", "soft_cap_bytes", "exceptions",
    "outside_cap",
))
EXCEPTION_FIELDS = frozenset((
    "path", "measured_bytes", "growth_cap_bytes", "record_id",
))
OUTSIDE_FIELDS = frozenset(("path", "record_id"))
RECORD_ID_RE = re.compile(r"(?:EXC|OUT)-[0-9]{3}\Z")


class KernelSizePolicyError(ValueError):
    """The policy cannot safely and deterministically be evaluated."""


def _closed_mapping(value, expected, label):
    if not isinstance(value, dict):
        raise KernelSizePolicyError("%s must be a mapping" % label)
    actual = set(value)
    if actual != expected:
        raise KernelSizePolicyError(
            "%s fields differ from the closed contract; missing=%s extra=%s"
            % (label, sorted(expected - actual), sorted(actual - expected)))
    return value


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise KernelSizePolicyError("%s must be a positive integer" % label)
    return value


def _relative_path(value, label):
    try:
        return repository_path_contract.canonical_repository_relative_path(
            value, label)
    except ValueError as exc:
        raise KernelSizePolicyError(str(exc)) from exc


def _table_cells(line):
    """Split one Markdown row without treating a Wiki alias pipe as a cell."""
    return [cell.strip() for cell in re.split(
        r"(?<!\\)\|", line.strip().strip("|"))]


def _record_path(cell, label):
    match = re.search(r"\[\[([^\\|#\]]+)", cell)
    if match is None:
        raise KernelSizePolicyError("%s has no Kernel leaf link" % label)
    return match.group(1) + ".md"


def _load_engineering_records(root, relative):
    """Validate record presence/identity without judging prose quality."""
    try:
        path = kblib.repository_path(
            root, relative, must_exist=True, reject_symlink=True)
        text = kblib.read_text(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise KernelSizePolicyError(
            "%s is missing, unsafe, or unreadable: %s" % (relative, exc))
    records = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not re.match(r"^\| `(EXC|OUT)-[0-9]{3}` \|", line):
            continue
        cells = _table_cells(line)
        match = re.fullmatch(r"`((?:EXC|OUT)-[0-9]{3})`", cells[0]) \
            if cells else None
        if match is None:
            raise KernelSizePolicyError(
                "%s:%d has an invalid record ID" % (relative, number))
        record_id = match.group(1)
        expected_width = 4 if record_id.startswith("EXC-") else 3
        if len(cells) != expected_width:
            raise KernelSizePolicyError(
                "%s:%d record %s must have %d cells" %
                (relative, number, record_id, expected_width))
        path_value = _record_path(
            cells[1], "%s:%d record %s" % (relative, number, record_id))
        if any(not value.strip() for value in cells[2:]):
            raise KernelSizePolicyError(
                "%s:%d record %s has an empty rationale or follow-up" %
                (relative, number, record_id))
        if record_id in records:
            raise KernelSizePolicyError(
                "%s repeats record %s" % (relative, record_id))
        records[record_id] = path_value
    return records


def load_policy(root):
    """Load and close the sole numeric leaf-size contract."""
    root = Path(root).resolve()
    try:
        policy_path = kblib.repository_path(
            root, POLICY_PATH, must_exist=True, reject_symlink=True)
        document = kblib.parse_yaml_subset(kblib.read_text(policy_path))
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        raise KernelSizePolicyError(
            "%s is missing, unsafe, or invalid: %s" % (POLICY_PATH, exc))
    document = _closed_mapping(document, POLICY_FIELDS, POLICY_PATH)
    if document.get("schema_version") != 1:
        raise KernelSizePolicyError("unsupported kernel-size schema_version")
    if document.get("policy_id") != "kernel-leaf-size-v1":
        raise KernelSizePolicyError("policy_id must be kernel-leaf-size-v1")
    kernel_root = _relative_path(
        document.get("kernel_root"), "%s.kernel_root" % POLICY_PATH)
    if kernel_root != "kernel":
        raise KernelSizePolicyError("kernel_root must be exactly kernel")
    expression = document.get("leaf_path_regex")
    if not isinstance(expression, str) or not expression:
        raise KernelSizePolicyError("leaf_path_regex must be non-empty")
    try:
        leaf_re = re.compile(expression + r"\Z")
    except re.error as exc:
        raise KernelSizePolicyError("leaf_path_regex is invalid: %s" % exc)
    target = _positive_integer(
        document.get("target_bytes"), "%s.target_bytes" % POLICY_PATH)
    soft_cap = _positive_integer(
        document.get("soft_cap_bytes"), "%s.soft_cap_bytes" % POLICY_PATH)
    if target > soft_cap:
        raise KernelSizePolicyError(
            "target_bytes must not exceed soft_cap_bytes")
    engineering_record = _relative_path(
        document.get("engineering_record"),
        "%s.engineering_record" % POLICY_PATH)
    if (not engineering_record.startswith("Tools/") or
            not engineering_record.endswith(".md")):
        raise KernelSizePolicyError(
            "engineering_record must be a Markdown file under Tools/")

    exceptions = document.get("exceptions")
    outside = document.get("outside_cap")
    if not isinstance(exceptions, list) or not isinstance(outside, list):
        raise KernelSizePolicyError("exceptions and outside_cap must be lists")
    exception_by_path = {}
    outside_by_path = {}
    record_ids = set()
    for index, raw in enumerate(exceptions):
        label = "%s.exceptions[%d]" % (POLICY_PATH, index)
        row = _closed_mapping(raw, EXCEPTION_FIELDS, label)
        path = _relative_path(row.get("path"), label + ".path")
        if leaf_re.fullmatch(path) is None:
            raise KernelSizePolicyError(
                "%s is not a numbered Kernel leaf path" % path)
        if path in exception_by_path:
            raise KernelSizePolicyError("%s is registered more than once" % path)
        measured = _positive_integer(
            row.get("measured_bytes"), label + ".measured_bytes")
        cap = _positive_integer(
            row.get("growth_cap_bytes"), label + ".growth_cap_bytes")
        if cap < soft_cap:
            raise KernelSizePolicyError(
                "%s growth cap is below the standing soft cap" % path)
        if measured > cap:
            raise KernelSizePolicyError(
                "%s recorded measurement exceeds its growth cap" % path)
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or RECORD_ID_RE.fullmatch(record_id) is None:
            raise KernelSizePolicyError("%s.record_id is invalid" % label)
        if record_id in record_ids:
            raise KernelSizePolicyError("record_id %s is repeated" % record_id)
        record_ids.add(record_id)
        exception_by_path[path] = dict(row)
    for index, raw in enumerate(outside):
        label = "%s.outside_cap[%d]" % (POLICY_PATH, index)
        row = _closed_mapping(raw, OUTSIDE_FIELDS, label)
        path = _relative_path(row.get("path"), label + ".path")
        if leaf_re.fullmatch(path) is None:
            raise KernelSizePolicyError(
                "%s is not a numbered Kernel leaf path" % path)
        if path in outside_by_path:
            raise KernelSizePolicyError(
                "%s is declared outside the cap more than once" % path)
        if path in exception_by_path:
            raise KernelSizePolicyError(
                "%s has both exception and outside-cap dispositions" % path)
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or RECORD_ID_RE.fullmatch(record_id) is None:
            raise KernelSizePolicyError("%s.record_id is invalid" % label)
        if record_id in record_ids:
            raise KernelSizePolicyError("record_id %s is repeated" % record_id)
        record_ids.add(record_id)
        outside_by_path[path] = dict(row)
    observed_records = _load_engineering_records(root, engineering_record)
    expected_records = {
        row["record_id"]: path
        for path, row in {
            **exception_by_path, **outside_by_path}.items()
    }
    if observed_records != expected_records:
        raise KernelSizePolicyError(
            "%s record identities or paths differ from %s; missing=%s extra=%s"
            % (engineering_record, POLICY_PATH,
               sorted(set(expected_records) - set(observed_records)),
               sorted(set(observed_records) - set(expected_records))))
    return {
        "target_bytes": target,
        "soft_cap_bytes": soft_cap,
        "leaf_re": leaf_re,
        "exceptions": exception_by_path,
        "outside_cap": outside_by_path,
        "engineering_record": engineering_record,
    }


def discover_leaf_sizes(root, policy):
    """Return every numbered Kernel leaf and reject unsafe traversal state."""
    root = Path(root).resolve()
    kernel = root / "kernel"
    if not kernel.is_dir() or kernel.is_symlink():
        raise KernelSizePolicyError("kernel directory is missing or unsafe")
    measured = {}
    try:
        candidates = sorted(kernel.rglob("*.md"))
    except OSError as exc:
        raise KernelSizePolicyError("kernel directory cannot be scanned: %s" % exc)
    for path in candidates:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            raise KernelSizePolicyError("kernel traversal escaped the repository")
        if policy["leaf_re"].fullmatch(relative) is None:
            continue
        if path.is_symlink() or not path.is_file():
            raise KernelSizePolicyError("%s is not a safe regular file" % relative)
        try:
            measured[relative] = path.stat().st_size
        except OSError as exc:
            raise KernelSizePolicyError("%s cannot be measured: %s" %
                                        (relative, exc))
    return measured


def evaluate(root, policy=None):
    """Return ``(errors, candidates, summary)`` for one repository tree."""
    policy = policy or load_policy(root)
    measured = discover_leaf_sizes(root, policy)
    exceptions = policy["exceptions"]
    outside = policy["outside_cap"]
    errors = []
    candidates = []
    for path in sorted(measured):
        size = measured[path]
        if path in outside:
            continue
        row = exceptions.get(path)
        if row is None:
            if size > policy["soft_cap_bytes"]:
                candidates.append(
                    "%s is %d bytes, over the %d-byte soft cap, with no "
                    "exception or outside-cap disposition in %s"
                    % (path, size, policy["soft_cap_bytes"], POLICY_PATH))
            continue
        if size > row["growth_cap_bytes"]:
            errors.append(
                "%s is %d bytes, over its %d-byte growth cap in %s"
                % (path, size, row["growth_cap_bytes"], POLICY_PATH))
        if size != row["measured_bytes"]:
            candidates.append(
                "%s measures %d bytes; %s records %d and requires re-measurement"
                % (path, size, POLICY_PATH, row["measured_bytes"]))
    for path in sorted(set(exceptions) | set(outside)):
        if path not in measured:
            errors.append(
                "%s registers %s, which is not a current numbered Kernel leaf"
                % (POLICY_PATH, path))
    summary = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "policy": POLICY_PATH,
        "leaf_count": len(measured),
        "exception_count": len(exceptions),
        "outside_cap_count": len(outside),
        "error_count": len(errors),
        "candidate_count": len(candidates),
    }
    return errors, candidates, summary


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Check the Tool-owned Kernel leaf-size policy")
    parser.add_argument("root", help="Cambium repository root")
    parser.add_argument("--json", action="store_true",
                        help="emit one structured result")
    args = parser.parse_args(argv)
    try:
        errors, candidates, summary = evaluate(args.root)
    except KernelSizePolicyError as exc:
        errors = [str(exc)]
        candidates = []
        summary = {
            "tool": TOOL,
            "tool_version": TOOL_VERSION,
            "policy": POLICY_PATH,
            "leaf_count": 0,
            "exception_count": 0,
            "outside_cap_count": 0,
            "error_count": 1,
            "candidate_count": 0,
        }
    if args.json:
        payload = dict(summary, errors=errors, candidates=candidates)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        for message in errors:
            print("  [FAIL] %s" % message)
        for message in candidates:
            print("  [CAND] %s" % message)
        if errors:
            print("check_kernel_size: FAIL — %d error(s)" % len(errors))
        elif candidates:
            print("check_kernel_size: HOLD — %d candidate(s)" % len(candidates))
        else:
            print(
                "check_kernel_size: PASS — %d leaves, %d exceptions, %d outside cap"
                % (summary["leaf_count"], summary["exception_count"],
                   summary["outside_cap_count"]))
    return 1 if errors else (2 if candidates else 0)


if __name__ == "__main__":
    raise SystemExit(main())
