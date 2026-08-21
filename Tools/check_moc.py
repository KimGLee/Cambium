#!/usr/bin/env python3
"""check_moc.py -- candidate detection for MOC "Module Index" vs. leaf H2 headings.

Rule owner: kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
(Standards module MOC / leaf module consistency checks).

Method:
- Recursively scan <root> for .md files that contain a `## Module Index`
  section. No semantic directory name is excluded by default; --exclude is
  explicit and repeatable.
- In that section, take the first [[target\\|alias]] link of each table row;
  the target is resolved directly as a root-relative path (".md" appended).
  The backticked section names in the row are the listed sections.
- For each target file, extract the actual `## ` headings fence-aware
  (a ``` line toggles the fence state); `Navigation` is always ignored.
- Compare both directions: heading present in the file but not listed
  (missing_in_index), listed but absent from the file (stale_in_index),
  and a listed target file that does not exist (target_missing).

The check is candidate-only (exit code 2 when candidates exist); the final
verdict is left to humans/maintenance rounds; run only during maintenance
rounds and governance tasks.

Usage: python3 Tools/check_moc.py <root> [--exclude COMPONENT ...] [--receipts PATH]
       [--json]
"""
import contextlib
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL, TOOL_VERSION = "check_moc", "1.4.0"

SECTION_RE = re.compile(r"^## Module Index\s*\n(.*?)(?=\n## |\Z)", re.S | re.M)
LINK_RE = re.compile(r"\[\[([^\]\\|]+)")


def h2s(path):
    """Fence-aware H2 extraction; `Navigation` is always ignored."""
    out = []
    in_fence = False
    for line in open(path, encoding="utf-8"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## "):
            h = line[3:].strip()
            if h != "Navigation" and not h.startswith("Navigation"):
                out.append(h)
    return out


def find_mocs(root, excludes):
    """Return sorted root-relative paths of .md files with a Module Index section."""
    mocs = []
    for full, rel in kblib.repository_content_files(root):
        components = rel.split("/")
        if (not rel.endswith(".md") or
                any(part.startswith(".") or part in excludes
                    for part in components[:-1])):
            continue
        with open(full, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        if SECTION_RE.search(text):
            mocs.append(rel)
    return sorted(mocs)


# ---------------------------------------------------------------------------
# `--json` output (machine-readable receipts)
#
# Purely additive: without the flag not one byte of this tool's behaviour
# moves.  With it, everything written for a person goes to stderr and stdout
# carries exactly one canonical JSON array -- the receipt objects this run
# handed to the receipt writer, serialized verbatim.
#
# Nothing is filtered or renamed.  `schemas/receipt.template.jsonl` guarantees
# only the base fields every receipt carries; extension fields differ per
# producer and are discoverable from the receipt itself, which is why that
# template says its examples are "not the complete set".  A field allowlist
# here would silently drop exactly the fields a caller came for.
#
# Serialization goes through `kblib.canonical_json_bytes`; this module owns no
# serializer.  The flag changes no verdict, no exit code, and no receipt
# write.  A run that writes no receipt -- a dry run, or a refusal -- emits the
# empty array; a usage error still exits through argparse before any of this,
# leaving stdout empty and the reason on stderr.
# ---------------------------------------------------------------------------
JSON_HELP = ("write the receipts this run produced to stdout as one canonical "
             "JSON array and move the human-readable report to stderr; "
             "receipts written, verdicts, and exit codes are unchanged")

_JSON_RECEIPTS = []


def _record_receipts(receipts):
    """Remember the exact receipt objects handed to the receipt writer."""
    _JSON_RECEIPTS.extend(receipts)
    return receipts


def _run_reporting_json(runner):
    """Run `runner`, reserving stdout for JSON and giving stderr the prose."""
    stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        exit_code = runner()
    stdout.write(kblib.canonical_json_bytes(_JSON_RECEIPTS).decode("utf-8"))
    stdout.write("\n")
    stdout.flush()
    return exit_code


def _run(args):
    excludes = set(args.exclude)
    root = args.root
    mocs = find_mocs(root, excludes)

    cands = []
    for moc in mocs:
        text = open(os.path.join(root, moc), encoding="utf-8", errors="replace").read()
        m = SECTION_RE.search(text)
        if not m:
            continue
        for row in m.group(1).splitlines():
            if not row.lstrip().startswith("|") or "[[" not in row:
                continue
            lm = LINK_RE.search(row)
            if not lm:
                continue
            target = lm.group(1).strip()
            if not target.lower().endswith(".md"):
                target += ".md"
            rest = row.split("]]", 1)[1] if "]]" in row else row
            # Sections are read from the sections cell only (the cell after the
            # link cell). Slot annotations in the link cell ("+ `Slot Name`") and
            # trailing prose after the first ";" in the sections cell are ignored
            # by convention (see Tools/README.md).
            cells = re.split(r"\s\|\s", rest.strip().strip("|"))
            sections_cell = cells[-1] if cells else rest
            sections_cell = sections_cell.split(";", 1)[0]
            listed = re.findall(r"`([^`]+)`", sections_cell)
            target_full = os.path.join(root, target)
            if not os.path.exists(target_full):
                cands.append((moc, target, "target_missing", ""))
                continue
            actual = h2s(target_full)
            for h in actual:
                if h not in listed:
                    cands.append((moc, target, "missing_in_index", h))
            for h in listed:
                if h not in actual:
                    cands.append((moc, target, "stale_in_index", h))

    for moc, target, kind, h in cands:
        print(f"  [CAND] {moc} -> {target}: {kind}: {h}")
    print(f"check_moc: {len(cands)} candidate(s) ({len(mocs)} MOC file(s) scanned)")
    # Receipts follow the shared convention (kblib.make_receipt; same schema
    # as every other check_*.py -- Tools/schemas/receipt.template.jsonl).
    receipts = []
    for seq, (moc, target, kind, h) in enumerate(cands, 1):
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "moc-index-drift",
            "%s -> %s" % (moc, target), "candidate",
            "%s: %s (Module Index vs actual H2 headings, K12/05; candidates "
            "only, disposition is a human call)" % (kind, h), seq))
    if not cands:
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "moc-check-summary", "full-vault", "pass",
            "Module Index sections match actual H2 headings "
            "(%d MOC file(s) scanned)" % len(mocs), 1))
    kblib.write_receipts(args.receipts, _record_receipts(receipts))
    return kblib.exit_code(receipts)


def main():
    ap = kblib.ArgumentParser(
        description="MOC Module Index consistency candidate detection")
    ap.add_argument("root", help="scan root directory")
    ap.add_argument("--exclude", action="append", default=[],
                    help="path component to exclude (repeatable); no semantic "
                         "directory name is excluded by default")
    ap.add_argument("--receipts", help="JSONL path to append a machine-readable receipt to")
    ap.add_argument("--json", action="store_true", help=JSON_HELP)
    args = ap.parse_args()

    if not args.json:
        return _run(args)
    return _run_reporting_json(lambda: _run(args))


if __name__ == "__main__":
    sys.exit(main())
