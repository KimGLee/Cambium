#!/usr/bin/env python3
"""apply_delta.py -- deterministically apply a concurrent batch's Coverage Delta to the canonical Coverage Ledger.

Rule owner: kernel/K02 Build Execution/05 Batch Execution.md (Concurrent Batches); see
Tools/schemas/coverage_delta.template.yaml for the delta schema. Design goal:
the serial merge zone only executes deterministic actions -- delta application
is done by this script, not by an LLM hand-editing the large Ledger file.

Behavior:
- For each page, locate the Ledger entry block starting at `- path: "<path>"`
  and update its scalar fields according to the delta
  (authoring_status / tier / lifecycle / next_batch etc. --
  whatever scalar keys appear in the delta's page entry get updated; keys not
  present in the block are appended at the block's indentation).
- gate_receipts are merged by appending (deduplicated); both legal Ledger
  forms are read (inline `[...]` and block list), and the merged result is
  always written back in the schema's block-list form with the existing
  items replaced in place (no orphan list lines).
- Scalar keys outside the Coverage Ledger core schema are applied but warned
  about ([WARN unknown-key]); they are legal for registered profile
  extensions and the warning is the visibility hook.
- Out-of-scope protection: a page is rejected when the entry block's
  next_batch or batch does not equal delta.batch (--force overrides, with a
  per-page reason recorded).
- open_gaps_added / open_gaps_closed are printed as a todo list (gap structure
  varies by task; the integrator handles them in the Ledger's open_gaps
  section manually or via a follow-up script); watermark_advance entries are
  likewise printed as integrator todos (K02/05: applied to
  Tools/state/watermark.yaml at merge, not by this script).
- Default is a dry run that prints the plan; --apply first re-parses the
  merged output with the restricted-subset parser and ABORTS without writing
  when it no longer parses; on success it writes atomically (temp file +
  rename) after creating a <ledger>.bak backup.
- --receipts appends one JSONL receipt (check: delta_apply).

Usage: python3 apply_delta.py <ledger.yaml> <delta.yaml> [--apply] [--force] [--receipts R]
"""
import argparse, os, re, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL, TOOL_VERSION = "apply_delta", "1.3.0"

# Scalar keys expected in a Coverage Ledger page entry (schema:
# Tools/schemas/coverage_ledger.template.yaml; profile extensions such as an
# Expression Status Axis are legal, so unknown keys are warned about and
# still applied, never silently absorbed).
KNOWN_SCALAR_KEYS = {"authoring_status", "tier",
                     "lifecycle", "batch", "next_batch", "volatility",
                     "review_by", "priority", "coverage_disposition"}

def load_delta(path):
    text = "\n".join(l for l in open(path, encoding="utf-8") if not l.lstrip().startswith("#"))
    return kblib.parse_yaml_subset(text)

def find_page_block(lines, path):
    """Return the (start, end) line range: from `- path: "<path>"` to the next `- ` at the same indentation or the end of the list."""
    pat = re.compile(r'^(\s*)-\s+path:\s*(.*?)\s*$')
    for i, line in enumerate(lines):
        clean = kblib.strip_yaml_comment(line.rstrip("\r\n"))
        m = pat.match(clean)
        if not m or str(kblib.parse_scalar(m.group(2))) != path:
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
            raw = kblib.strip_yaml_comment(m.group(2)).strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in '"\'':
                raw = raw[1:-1]
            return i, m.group(1), raw
    return None, None, None


def get_receipt_ids(lines, start, end):
    """Read the existing gate_receipts of a page block, in either legal form.

    Returns (key_line_idx, indent, ids, last_item_idx): inline `[...]` values
    come from the key line itself; block-list `- "id"` items are collected
    from the lines following the key line. last_item_idx is the index of the
    final line belonging to gate_receipts (== key line for inline/empty form).
    Returns (None, None, [], None) when the key is absent.
    """
    li, ind, raw = block_get(lines, start, end, "gate_receipts")
    if li is None:
        return None, None, [], None
    if raw:
        ids = [x.strip().strip('"\'') for x in raw.strip("[]").split(",") if x.strip()]
        return li, ind, ids, li
    ids, last = [], li
    item_pat = re.compile(r'^(\s+)-\s+(.*?)\s*$')
    for j in range(li + 1, end):
        m = item_pat.match(lines[j])
        if not m or len(m.group(1)) <= len(ind):
            break
        raw = kblib.strip_yaml_comment(m.group(2)).strip()
        ids.append(raw.strip('"\''))
        last = j
    return li, ind, ids, last

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

    planned, rejected, unknown_keys = [], [], []
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
                # Merge by appending (deduplicated) and always emit the
                # schema's block-list form; the replacement range covers the
                # key line plus any existing block-list items, so no orphan
                # `- "id"` lines survive (they would break the restricted
                # YAML subset).
                li, ind, cur_ids, last = get_receipt_ids(lines, start, end)
                new_ids = [str(v) for v in (val or [])]
                merged = cur_ids + [x for x in new_ids if x not in cur_ids]
                if li is not None:
                    block = [f'{ind}gate_receipts:\n'] + [
                        f'{ind}  - "{x}"\n' for x in merged]
                    edits.append(("range", li, last + 1, block))
                else:
                    block = ['    gate_receipts:\n'] + [
                        f'      - "{x}"\n' for x in merged]
                    edits.append(("range", end, end, block))
                continue
            if key not in KNOWN_SCALAR_KEYS:
                unknown_keys.append((path, key))
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
    for p, k in unknown_keys:
        print(f"  [WARN unknown-key] {p}: scalar key '{k}' is outside the "
              f"Coverage Ledger core schema (applied anyway; legal for "
              f"registered profile extensions, verify it is one)")
    for g in (delta.get("open_gaps_added") or []):
        print(f"  [TODO gaps+] {g}")
    for g in (delta.get("open_gaps_closed") or []):
        print(f"  [TODO gaps-] {g}")
    for s in (delta.get("next_batch_updates") or []):
        print(f"  [SUGGEST] {s}")
    for w in (delta.get("watermark_advance") or []):
        print(f"  [TODO watermark] {w} — integrator applies to "
              f"Tools/state/watermark.yaml at merge (K02/05); this script "
              f"does not apply watermark advances")

    result = "fail" if rejected and not args.force else ("pass" if planned else "candidate")
    if args.apply and result != "fail":
        # Apply block by block (descending line order to avoid offset shifts)
        flat = []
        for _, _, eds in planned:
            for e in eds:
                flat.append(e)

        def edit_pos(e):
            return e[1] if e[0] == "range" else e[0]

        new_lines = list(lines)
        for e in sorted(flat, key=lambda x: -edit_pos(x)):
            if e[0] == "range":
                _, rstart, rstop, block = e
                new_lines[rstart:rstop] = block
            elif len(e) == 3 and e[2] in ("insert", "append"):
                new_lines.insert(e[0], e[1])
            else:
                new_lines[e[0]] = e[1]
        new_text = "".join(new_lines)

        # Self-verification: the output must reparse under the restricted
        # YAML subset before it may replace the authoritative Ledger. On
        # failure nothing is written and the exit code is 1.
        try:
            kblib.parse_yaml_subset(new_text)
        except kblib.YamlSubsetError as exc:
            print(f"apply_delta: ABORT — merged output no longer parses "
                  f"({exc}); the Ledger was NOT modified")
            result = "fail"
        else:
            shutil.copyfile(args.ledger, args.ledger + ".bak")
            tmp_path = args.ledger + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(tmp_path, args.ledger)
            print(f"apply_delta: written to disk (backup {args.ledger}.bak; "
                  f"output re-parsed OK)")
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
