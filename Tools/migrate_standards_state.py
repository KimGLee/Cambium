#!/usr/bin/env python3
"""Materialize canonical adopter Standards state from an existing runtime.

This is a one-time compatibility bridge for adopters whose current identity is
still repeated across the three task ledgers.  It does not create an adoption,
rewrite history, or read K00/03 as mutable state.
"""

import json
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import runtime_paths
import standards_state

TOOL = "migrate_standards_state"
TOOL_VERSION = "1.0.0"
QUEUE_PATH = runtime_paths.QUEUE_PATH
COVERAGE_PATH = runtime_paths.COVERAGE_PATH
PROGRESS_PATH = runtime_paths.PROGRESS_PATH
HISTORY_PATH = runtime_paths.STANDARDS_ADOPTION_RECEIPT_PATH


def _read_yaml(root, relative):
    path = kblib.managed_repository_path(
        root, relative, os.path.dirname(relative),
        suffixes=(".yaml",), must_exist=True)
    with open(path, "rb") as stream:
        raw = stream.read()
    return path, raw, kblib.parse_yaml_subset(raw.decode("utf-8"))


def _history(root):
    path = kblib.managed_repository_path(
        root, HISTORY_PATH, runtime_paths.RECEIPT_ROOT,
        suffixes=(".jsonl",), must_exist=True)
    with open(path, "rb") as stream:
        raw = stream.read()
    rows = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("history line %d is not JSON: %s" %
                             (number, exc))
        if not isinstance(row, dict):
            raise ValueError("history line %d is not an object" % number)
        rows.append(row)
    return path, raw, rows


def prepare(root):
    root = os.path.realpath(os.path.abspath(root))
    target = os.path.join(root, standards_state.STATE_PATH)
    if os.path.lexists(target):
        raise ValueError("canonical Standards state already exists")
    snapshots = {}
    documents = {}
    for name, relative in (("queue", QUEUE_PATH), ("coverage", COVERAGE_PATH),
                           ("progress", PROGRESS_PATH)):
        path, raw, document = _read_yaml(root, relative)
        snapshots[path] = raw
        documents[name] = document
    history_path, history_raw, rows = _history(root)
    snapshots[history_path] = history_raw

    queue = documents["queue"]
    coverage = documents["coverage"]
    progress = documents["progress"]
    contract = progress.get("contract") if isinstance(progress, dict) else None
    if not all(isinstance(value, dict) for value in
               (queue, coverage, progress, contract)):
        raise ValueError("runtime ledgers do not have the required mappings")
    versions = {
        queue.get("standards_version"), coverage.get("standards_version"),
        contract.get("standards_version")}
    profiles = {
        queue.get("selected_profile_manifest"),
        coverage.get("selected_profile_manifest"),
        contract.get("selected_profile_manifest")}
    if len(versions) != 1 or not all(
            isinstance(value, str) and value for value in versions):
        raise ValueError("runtime ledgers disagree on standards_version")
    if len(profiles) != 1 or not all(
            isinstance(value, str) and value for value in profiles):
        raise ValueError(
            "runtime ledgers disagree on selected_profile_manifest")
    version = next(iter(versions))
    profile = next(iter(profiles))
    commits = [row for row in rows
               if row.get("tool") in
               ("adopt_standards", "apply_profile_adoption") and
               row.get("result") == "pass" and
               row.get("transaction_phase") == "commit" and
               row.get("standards_version_after") == version and
               isinstance(row.get("receipt_id"), str)]
    if not commits:
        raise ValueError(
            "no committed adoption receipt accounts for live Standards %s" %
            version)
    commit = commits[-1]
    checked_at = commit.get("checked_at")
    try:
        effective_date = datetime.date.fromisoformat(
            checked_at[:10]).isoformat()
    except (AttributeError, TypeError, ValueError):
        effective_date = None
    if effective_date is None:
        raise ValueError("latest adoption receipt has no usable checked_at")
    document = {
        "schema_version": 1,
        "state_revision": 1,
        "standards_version": version,
        "status": "approved",
        "effective_date": effective_date,
        "selected_profile_manifest": profile,
        "latest_adoption_receipt": commit["receipt_id"],
        "upstream_source_ref": commit.get("upstream_source_ref"),
        "upstream_revision_id": commit.get("upstream_revision_id"),
    }
    text = standards_state.canonical_text(document)
    return root, target, snapshots, document, text


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Migrate existing runtime identity to Standards state")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--apply", action="store_true",
                        help="write state; omit for a dry run")
    args = parser.parse_args(argv)
    try:
        root, target, snapshots, document, text = prepare(args.root)
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot migrate Standards state: %s" % exc)
        return 1
    print("migration plan:")
    print("  standards_version=%s" % document["standards_version"])
    print("  selected_profile_manifest=%s" %
          document["selected_profile_manifest"])
    print("  latest_adoption_receipt=%s" %
          document["latest_adoption_receipt"])
    print("  target=%s" % standards_state.STATE_PATH)
    if not args.apply:
        print("dry run; add --apply to write the state")
        return 0
    for path, raw in snapshots.items():
        with open(path, "rb") as stream:
            current = stream.read()
        if current != raw:
            print("[FAIL] migration input changed before publication")
            return 1
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        def validate(value):
            _state, errors = standards_state.parse(value)
            if errors:
                raise ValueError("; ".join(errors))
        kblib.atomic_write_text(target, text, validator=validate)
    except (OSError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot publish Standards state: %s" % exc)
        return 1
    print("[PASS] migrated canonical adopter Standards state")
    return 0


if __name__ == "__main__":
    sys.exit(main())
