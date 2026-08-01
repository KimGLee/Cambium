#!/usr/bin/env python3
"""stamp_cards.py -- recompute and stamp Runtime Cards' source_hash (optionally unify compiled_from).

Rule owner: 00 Standards Control/03 (Revision Write-back Checklist: affected
Cards must be re-stamped after regeneration; --check must pass before a
revision is closed). hash = first 12 hex digits of the sha256 over the bytes
of each source file concatenated in source_files order. card-index (no
source_files) does not take part in hash verification, but --set-version also
updates its compiled_from version stamp.

Usage: python3 stamp_cards.py <standards_root> [--cards-dir DIR] [--set-version vX.Y] [--check]
  --check verifies only, without writing: cards with a hash mismatch are
  listed as candidates (exit code 2).
"""
import argparse, glob, hashlib, os, re, sys

def main():
    ap = argparse.ArgumentParser(description="Stamp Runtime Cards")
    ap.add_argument("root", help="standards root directory")
    ap.add_argument("--cards-dir", default="Cards",
                    help="cards directory relative to <root> (default: Cards)")
    ap.add_argument("--set-version",
                    help="also set every card's compiled_from to this value (e.g. v2.2)")
    ap.add_argument("--check", action="store_true", help="verify only, do not write")
    args = ap.parse_args()
    os.chdir(args.root)
    if not os.path.isdir(args.cards_dir):
        print(f"no cards directory at {args.cards_dir}; nothing to stamp")
        return 0
    stale, stamped = [], []
    for card in sorted(glob.glob(os.path.join(args.cards_dir, "*.md"))):
        t = open(card, encoding="utf-8").read()
        m = re.search(r'source_files:\n((?:  - .*\n)+)', t)
        if not m:
            # card-index: no source_files, only sync the version stamp
            if args.set_version and not args.check:
                t2 = re.sub(r'compiled_from: v[\d.]+', f'compiled_from: {args.set_version}', t)
                if t2 != t:
                    open(card, "w", encoding="utf-8").write(t2); stamped.append(card)
                    print(f"  [STAMP] {card} -> compiled_from {args.set_version}")
            continue
        srcs = [l.strip()[2:].strip() for l in m.group(1).strip().split("\n")]
        h = hashlib.sha256()
        missing = [s for s in srcs if not os.path.exists(s)]
        if missing:
            print(f"  [FAIL] {card}: missing source file(s) {missing}"); return 1
        for s in srcs:
            h.update(open(s, "rb").read())
        new = h.hexdigest()[:12]
        cur = re.search(r'source_hash: (\S+)', t)
        cur_v = cur.group(1) if cur else "?"
        if args.check:
            if cur_v != new:
                stale.append(card); print(f"  [CAND] {card}: hash mismatch {cur_v} -> {new}")
            continue
        t2 = re.sub(r'source_hash: \S+', f'source_hash: {new}', t)
        if args.set_version:
            t2 = re.sub(r'compiled_from: v[\d.]+', f'compiled_from: {args.set_version}', t2)
        if t2 != t:
            open(card, "w", encoding="utf-8").write(t2); stamped.append(card)
            print(f"  [STAMP] {card} -> {new}")
    if args.check:
        print(f"stamp_cards --check: {len(stale)} card(s) mismatched"); return 2 if stale else 0
    print(f"stamp_cards: stamped {len(stamped)} card(s)"); return 0

if __name__ == "__main__":
    sys.exit(main())
