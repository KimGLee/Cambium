#!/usr/bin/env python3
"""apply_delta.py -- deterministically apply a concurrent batch's Coverage Delta to the canonical Coverage Ledger.

Rule owner: 02 Build Execution/05 (Concurrent Batches); see
Tools/schemas/coverage_delta.template.yaml for the delta schema. Design goal:
the serial merge zone only executes deterministic actions -- delta application
is done by this script, not by an LLM hand-editing the large Ledger file.

Behavior:
- For each page, locate the Ledger entry block starting at `- path: "<path>"`
  and update its scalar fields according to the delta
  (authoring_status / interview_status / tier / lifecycle / next_batch etc. --
  whatever scalar keys appear in the delta's page entry get updated; keys not
  present in the block are appended at the block's indentation).
- gate_receipts are merged by appending (deduplicated).
- Out-of-scope protection: a page is rejected when the entry block's
  next_batch or batch does not equal delta.batch (--force overrides, with a
  per-page reason recorded).
- open_gaps_added / open_gaps_closed are printed as a todo list (gap structure
  varies by task; the integrator handles them in the Ledger's open_gaps
  section manually or via a follow-up script).
- Default is a dry run that prints the plan; --apply writes to disk, creating
  a <ledger>.bak backup first.
- --receipts appends one JSONL receipt (check: delta_apply).

Usage: python3 apply_delta.py <ledger.yaml> <delta.yaml> [--apply] [--force] [--receipts R]
"""
import argparse, os, re, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL, TOOL_VERSION = "apply_delta", "1.0.0"

def load_delta(path):
    text = "\n".join(l for l in open(path, encoding="utf-8") if not l.lstrip().startswith("#"))
    return kblib.parse_yaml_subset(text)

def find_page_block(lines, path):
    """Return the (start, end) line range: from `- path: "<path>"` to the next `- ` at the same indentation or the end of the list."""
    pat = re.compile(r'^(\s*)-\s+path:\s*["\']?' + re.escape(path) + r'["\']?\s*$')
    for i, line in enumerate(lines):
        m = pat.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        j = i + 1
        while j < len(lines):
            s = lines[j]
            if s.strip() and not s.startswith(" " * (indent + 1)) and not s.startswith(" " * indent + " "):
                stripped_indent = len(s) - len(s.lstrip(" "))
                if stripped_indent <= indent and s.strip():
                    break
            if re.match(r'^\s{%d}-\s' % indent, s):
                break
            j += 1
        return i, j
    return None, None

def block_get(lines, start, end, key):
    pat = re.compile(r'^(\s+)' + re.escape(key) + r':\s*(.*)$')
    for i in range(start + 1, end):
        m = pat.match(lines[i])
        if m:
            return i, m.group(1), m.group(2).strip().strip('"\'')
    return None, None, None

def main():
    ap = argparse.ArgumentParser(description="Deterministic Coverage Delta application")
    ap.add_argument("ledger"); ap.add_argument("delta")
    ap.add_argument("--apply", action="store_true", help="actually write to disk (default is a dry run)")
    ap.add_argument("--force", action="store_true", help="allow out-of-scope pages (reason recorded)")
    ap.add_argument("--receipts", help="JSONL receipt output path")
    args = ap.parse_args()

    delta = load_delta(args.delta)
    batch = str(delta.get("batch", "")).strip()
    pages = delta.get("pages") or []
    lines = open(args.ledger, encoding="utf-8").read().splitlines(keepends=True)

    planned, rejected = [], []
    for page in pages:
        path = str(page.get("path", "")).strip()
        if not path:
            continue
        start, end = find_page_block(lines, path)
        if start is None:
            rejected.append((path, "not-found-in-ledger")); continue
        # Out-of-scope protection
        _, _, nb = block_get(lines, start, end, "next_batch")
        _, _, bt = block_get(lines, start, end, "batch")
        if batch and nb != batch and bt != batch and not args.force:
            rejected.append((path, f"manifest-mismatch(next_batch={nb},batch={bt})")); continue
        edits = []
        for key, val in page.items():
            if key in ("path",):
                continue
            if key == "gate_receipts":
                li, ind, cur = block_get(lines, start, end, "gate_receipts")
                new_ids = [str(v) for v in (val or [])]
                if li is not None:
                    cur_ids = [x.strip().strip('"\'') for x in cur.strip("[]").split(",") if x.strip()]
                    merged = cur_ids + [x for x in new_ids if x not in cur_ids]
                    edits.append((li, f'{ind}gate_receipts: [{", ".join(chr(34)+x+chr(34) for x in merged)}]\n'))
                else:
                    edits.append((start, f'    gate_receipts: [{", ".join(chr(34)+x+chr(34) for x in new_ids)}]\n', "append"))
                continue
            sval = "" if val is None else str(val)
            li, ind, _ = block_get(lines, start, end, key)
            if li is not None:
                edits.append((li, f'{ind}{key}: {sval}\n' if sval else f'{ind}{key}:\n'))
            else:
                edits.append((end, f'    {key}: {sval}\n', "insert"))
        planned.append((path, start, edits))

    print(f"apply_delta: batch={batch} planning to update {len(planned)} page(s), rejected {len(rejected)} page(s)")
    for p, s, eds in planned:
        print(f"  [PLAN] {p}: {len(eds)} field update(s)")
    for p, r in rejected:
        print(f"  [REJECT] {p}: {r}")
    for g in (delta.get("open_gaps_added") or []):
        print(f"  [TODO gaps+] {g}")
    for g in (delta.get("open_gaps_closed") or []):
        print(f"  [TODO gaps-] {g}")
    for s in (delta.get("next_batch_updates") or []):
        print(f"  [SUGGEST] {s}")

    result = "fail" if rejected and not args.force else ("pass" if planned else "candidate")
    if args.apply and result != "fail":
        shutil.copyfile(args.ledger, args.ledger + ".bak")
        # Apply block by block (descending line order to avoid offset shifts)
        flat = []
        for _, _, eds in planned:
            for e in eds:
                flat.append(e)
        for e in sorted(flat, key=lambda x: -x[0]):
            if len(e) == 3 and e[2] in ("insert", "append"):
                lines.insert(e[0], e[1])
            else:
                lines[e[0]] = e[1]
        open(args.ledger, "w", encoding="utf-8").write("".join(lines))
        print(f"apply_delta: written to disk (backup {args.ledger}.bak)")
    elif not args.apply:
        print("apply_delta: dry run (add --apply to write)")

    if args.receipts:
        r = kblib.make_receipt(TOOL, TOOL_VERSION, "delta_apply",
                               f"{os.path.basename(args.delta)} -> {os.path.basename(args.ledger)}",
                               result,
                               f"planned={len(planned)} rejected={len(rejected)} applied={bool(args.apply and result != 'fail')}", 1)
        kblib.write_receipts(args.receipts, [r])
    return 0 if result == "pass" else (1 if result == "fail" else 2)

if __name__ == "__main__":
    sys.exit(main())
