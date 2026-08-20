#!/usr/bin/env python3
"""Render the canonical Required Queue as a deterministic human report.

The Markdown is a disposable projection and is never read as runtime input.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib

DEFAULT_OUTPUT = ".cambium/reports/required_queue.md"


def _rows(items):
    lines = [
        "| Order | ID | Family | Records | Mode | State | Hold | Depends on |",
        "|---:|---|---|---:|---|---|---|---|",
    ]
    for item in sorted(items, key=lambda value: value.get("order", 10 ** 9)):
        dependencies = ", ".join(item.get("depends_on") or []) or "—"
        lines.append("| %s | `%s` | %s | %s | `%s` | `%s` | `%s` | %s |" % (
            item.get("order"), item.get("id"), item.get("family"),
            item.get("record_count"), item.get("execution_mode"),
            item.get("state"), item.get("hold_state"), dependencies,
        ))
    return lines


def render(result):
    queue = result["queue"]
    progress = result.get("progress") or {}
    contract = progress.get("contract") if isinstance(
        progress.get("contract"), dict) else {}
    maintenance = progress.get("maintenance_completion") if isinstance(
        progress.get("maintenance_completion"), dict) else {}
    items = queue.get("required_queue") or []
    ready = set(result.get("ready", []))
    blocked = dict(result.get("blocked", []))
    sections = [
        "# Required Queue",
        "",
        "> Derived report only. Canonical state: ".rstrip() +
        "`.cambium/state/required_queue.yaml`.",
        "",
        "- Task: `%s`" % queue.get("task_id"),
        "- Task state: `%s`" % progress.get("task_state"),
        "- Completion semantics: `%s`" %
        contract.get("completion_semantics"),
        "- Maintenance completion: `%s` (gate: `%s`)" % (
            maintenance.get("state"),
            maintenance.get("completion_gate_receipt") or "none",
        ),
        "- Objective: %s" % str(contract.get("objective", "")).replace(
            "\n", " "),
        "- Exclusions: %s" %
        (", ".join(contract.get("exclusions") or []) or "None"),
        "- Scope: `%s`" % queue.get("scope_version"),
        "- Queue revision: `%s`" % queue.get("queue_revision"),
        "- State revision: `%s`" % queue.get("state_revision"),
        "- Fingerprint: `%s`" % result.get("queue_sha256"),
        "- Remaining required work units: `%s`" % result.get("remaining"),
        "",
        "## Ready",
        "",
    ]
    if ready:
        sections.extend("- `%s`" % item_id for item_id in sorted(ready))
    else:
        sections.append("- None")
    sections.extend(["", "## Held Or Dependency-blocked", ""])
    if blocked:
        for item_id in sorted(blocked):
            sections.append("- `%s`: %s" %
                            (item_id, "; ".join(blocked[item_id])))
    else:
        sections.append("- None")
    sections.extend(["", "## Queue", ""])
    if items:
        sections.extend(_rows(items))
    else:
        sections.append("No work units have been materialized.")
    sections.extend(["", "## Closed History", ""])
    closed = [item for item in items
              if item.get("state") in ("closed", "cancelled")]
    if closed:
        for item in sorted(closed, key=lambda value: value.get("order", 10 ** 9)):
            sections.append("- `%s`: `%s` (%s object(s))" %
                            (item.get("id"), item.get("state"),
                             item.get("record_count")))
    else:
        sections.append("- None")
    return "\n".join(sections) + "\n"


def main(argv=None):
    parser = kblib.ArgumentParser(description="Render Required Queue human report")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="repository-relative report path")
    parser.add_argument("--stdout", action="store_true",
                        help="print the report to stdout and write nothing")
    parser.add_argument("--check", action="store_true",
                        help="compare existing report instead of writing")
    args = parser.parse_args(argv)

    result = check_queue.validate_runtime(args.root)
    if result["errors"]:
        for error in result["errors"]:
            print("[FAIL] %s" % error)
        return 1
    text = render(result)
    if args.stdout:
        sys.stdout.write(text)
        return 0
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        output = kblib.managed_repository_path(
            root, args.output, ".cambium/reports",
            suffixes=(".md",), must_exist=False,
        )
        if args.check:
            try:
                current = open(output, encoding="utf-8").read()
            except OSError:
                print("[FAIL] report is missing: %s" % args.output)
                return 1
            if current != text:
                print("[FAIL] report is stale: %s" % args.output)
                return 1
            print("[PASS] Required Queue report is current")
            return 0
        kblib.atomic_write_text(output, text)
    except (OSError, ValueError) as exc:
        print("[FAIL] cannot write report: %s" % exc)
        return 1
    print("[PASS] wrote derived report %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
