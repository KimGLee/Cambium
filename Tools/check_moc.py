#!/usr/bin/env python3
"""check_moc.py -- candidate detection for MOC "Module Index" vs. leaf H2 headings.

Rule owner: 12 Quality Assurance/05 (Standards domain MOC / leaf module
consistency checks).

Method:
- Recursively scan <root> for .md files that contain a `## Module Index`
  section (path components legacy, docs and _to_delete are excluded by
  default; --exclude appends more components).
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
"""
import argparse, json, os, re, sys, time

DEFAULT_EXCLUDES = ("legacy", "docs", "_to_delete")

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
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and d not in excludes)
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            text = open(full, encoding="utf-8", errors="replace").read()
            if SECTION_RE.search(text):
                mocs.append(rel)
    return sorted(mocs)


def main():
    ap = argparse.ArgumentParser(
        description="MOC Module Index consistency candidate detection")
    ap.add_argument("root", help="scan root directory")
    ap.add_argument("--exclude", action="append", default=[],
                    help="additional path component to exclude (repeatable; "
                         "legacy, docs and _to_delete are always excluded)")
    ap.add_argument("--receipts", help="JSONL path to append a machine-readable receipt to")
    args = ap.parse_args()

    excludes = set(DEFAULT_EXCLUDES) | set(args.exclude)
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
    if args.receipts:
        rec = {"receipt_id": f"audit-moc-{int(time.time())}-1",
               "check": "moc_index_consistency", "scope": "full-vault",
               "result": "candidates" if cands else "passed",
               "candidates": len(cands)}
        with open(args.receipts, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return 2 if cands else 0


if __name__ == "__main__":
    sys.exit(main())
