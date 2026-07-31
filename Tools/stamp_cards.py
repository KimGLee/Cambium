#!/usr/bin/env python3
"""stamp_cards.py —— 重新计算并盖戳 Runtime Cards 的 source_hash（可选统一 compiled_from）。

规则 owner：00 Standards Control/03（Revision Write-back Checklist：受影响 Cards
重新生成后必须重新盖戳；修订关闭前必须 --check 通过）。hash = 按 source_files
顺序拼接各源文件字节的 sha256 前 12 位。card-index（无 source_files）不参与
hash 校验，但 --set-version 时同步其 compiled_from 版本戳。

用法：python3 stamp_cards.py <standards_root> [--set-version vX.Y] [--check]
  --check 只校验不写盘：hash 失配的卡列为 candidate（退出码 2）。
"""
import argparse, glob, hashlib, os, re, sys

def main():
    ap = argparse.ArgumentParser(description="Runtime Cards 盖戳")
    ap.add_argument("root", help="Knowledge Base Standards 根目录")
    ap.add_argument("--set-version", help="同时把全部卡的 compiled_from 改为该值（如 v2.2）")
    ap.add_argument("--check", action="store_true", help="只校验不写盘")
    args = ap.parse_args()
    os.chdir(args.root)
    stale, stamped = [], []
    for card in sorted(glob.glob("Cards/*.md")):
        t = open(card, encoding="utf-8").read()
        m = re.search(r'source_files:\n((?:  - .*\n)+)', t)
        if not m:
            # card-index：无 source_files，仅同步版本戳
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
            print(f"  [FAIL] {card}: 源文件缺失 {missing}"); return 1
        for s in srcs:
            h.update(open(s, "rb").read())
        new = h.hexdigest()[:12]
        cur = re.search(r'source_hash: (\S+)', t)
        cur_v = cur.group(1) if cur else "?"
        if args.check:
            if cur_v != new:
                stale.append(card); print(f"  [CAND] {card}: hash 失配 {cur_v} -> {new}")
            continue
        t2 = re.sub(r'source_hash: \S+', f'source_hash: {new}', t)
        if args.set_version:
            t2 = re.sub(r'compiled_from: v[\d.]+', f'compiled_from: {args.set_version}', t2)
        if t2 != t:
            open(card, "w", encoding="utf-8").write(t2); stamped.append(card)
            print(f"  [STAMP] {card} -> {new}")
    if args.check:
        print(f"stamp_cards --check: 失配 {len(stale)} 张"); return 2 if stale else 0
    print(f"stamp_cards: 盖戳 {len(stamped)} 张"); return 0

if __name__ == "__main__":
    sys.exit(main())
