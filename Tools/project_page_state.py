#!/usr/bin/env python3
"""Project Ledger-owned state fields onto page frontmatter (K08/07).

The Coverage Ledger owns ``coverage_disposition``, ``authoring_status`` and
``next_batch``.  A page MAY carry a copy of any of them, but only as a
tool-written projection.  This projector makes that sentence executable: for
every Ledger page whose file exists, each projection field already present in
the page's frontmatter is rewritten to the owner value, and removed when the
owner value is empty.  A field the page does not carry is never added --
whether to persist a projection stays a page-level choice.

The default is a dry run that prints the plan.  ``--apply`` writes with the
same re-parse-then-atomic-write discipline K08/07 requires of every writer.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "project_page_state"
TOOL_VERSION = "1.0.0"
COVERAGE_LEDGER_PATH = ".cambium/state/coverage_ledger.yaml"
PROJECTION_FIELDS = ("coverage_disposition", "authoring_status", "next_batch")
FRONTMATTER = re.compile(r"^(---\n)(.*?)(\n---\n)", re.S)


def _field_pattern(name):
    return re.compile(r"^%s:[ \t]*(.*)$" % re.escape(name), re.M)


def project_page(text, row):
    """Return (new_text, changes) for one page against its Ledger row."""
    match = FRONTMATTER.match(text)
    if not match:
        return text, []
    frontmatter = match.group(2)
    changes = []
    for name in PROJECTION_FIELDS:
        pattern = _field_pattern(name)
        found = pattern.search(frontmatter)
        if not found:
            continue
        page_value = found.group(1).strip().strip('"').strip("'")
        owner_value = row.get(name)
        if owner_value is None or owner_value == "":
            frontmatter = re.sub(
                r"^%s:.*\n?" % re.escape(name), "", frontmatter, count=1,
                flags=re.M)
            changes.append((name, page_value or "(empty)", None))
        elif page_value != str(owner_value):
            frontmatter = pattern.sub(
                "%s: %s" % (name, owner_value), frontmatter, count=1)
            changes.append((name, page_value or "(empty)", str(owner_value)))
    if not changes:
        return text, []
    return match.group(1) + frontmatter + match.group(3) + \
        text[match.end():], changes


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Project Ledger-owned state onto page frontmatter")
    parser.add_argument("root")
    parser.add_argument("--page", action="append", default=None,
                        help="limit to these repository-relative pages "
                             "(repeatable); default is every Ledger page")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    root = args.root

    ledger_path = os.path.join(root, COVERAGE_LEDGER_PATH)
    if not os.path.isfile(ledger_path):
        print("[FAIL] no Coverage Ledger at %s" % COVERAGE_LEDGER_PATH)
        return 1
    ledger = kblib.parse_yaml_subset(
        open(ledger_path, encoding="utf-8").read())
    rows = {str(row["path"]): row
            for row in (ledger or {}).get("pages") or []
            if isinstance(row, dict) and row.get("path")}
    selected = args.page if args.page else sorted(rows)
    unknown = [page for page in (args.page or []) if page not in rows]
    if unknown:
        print("[FAIL] not in the Coverage Ledger: %s" % ", ".join(unknown))
        return 1

    planned = 0
    touched = 0
    for rel in selected:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8").read()
        new_text, changes = project_page(text, rows[rel])
        if not changes:
            continue
        planned += len(changes)
        touched += 1
        for name, before, after in changes:
            print("  [%s] %s %s: %r -> %s" %
                  ("PROJECT" if args.apply else "PLAN", rel, name, before,
                   "removed (owner empty)" if after is None else repr(after)))
        if args.apply:
            current = open(path, encoding="utf-8").read()
            if current != text:
                print("[FAIL] %s changed during projection; re-run" % rel)
                return 1
            kblib.atomic_write_text(path, new_text)
    print("%s: pages=%d field_changes=%d%s" %
          (TOOL, touched, planned,
           "" if args.apply else " (dry run; add --apply)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
