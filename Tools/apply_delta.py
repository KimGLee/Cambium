#!/usr/bin/env python3
"""apply_delta.py —— 将并发批次的 Coverage Delta 确定性地应用到 canonical Coverage Ledger。

规则 owner：02 Build Execution/05（Concurrent Batches）；delta schema 见
Tools/schemas/coverage_delta.template.yaml。设计目的：串行合并区只执行确定性
动作——delta 应用由本脚本完成，不由 LLM 手工编辑大型 Ledger 文件。

行为：
- 逐页定位 Ledger 中 `- path: "<path>"` 的条目块，按 delta 更新其中的标量字段
  （authoring_status / interview_status / tier / lifecycle / next_batch 等——
  delta 页条目里出现什么标量键就更新什么键；块内不存在的键按块缩进追加）。
- gate_receipts 追加合并（去重）。
- 越界保护：页条目块中 next_batch 或 batch 不等于 delta.batch 时拒绝该页
  （--force 可覆盖，逐页记录理由）。
- open_gaps_added / open_gaps_closed 输出为待办清单（gap 结构因任务而异，
  由 integrator 按清单在 Ledger 的 open_gaps 节手动或后续脚本处理）。
- 默认 dry-run 打印计划；--apply 才写盘，写盘前生成 <ledger>.bak 备份。
- --receipts 追加一条 JSONL receipt（check: delta_apply）。

用法：python3 apply_delta.py <ledger.yaml> <delta.yaml> [--apply] [--force] [--receipts R]
"""
import argparse, os, re, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL, TOOL_VERSION = "apply_delta", "1.0.0"

def load_delta(path):
    text = "\n".join(l for l in open(path, encoding="utf-8") if not l.lstrip().startswith("#"))
    return kblib.parse_yaml_subset(text)

def find_page_block(lines, path):
    """返回 (start, end) 行号区间：`- path: "<path>"` 起，到下一个同缩进 `- ` 或列表结束。"""
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
    ap = argparse.ArgumentParser(description="Coverage Delta 确定性应用")
    ap.add_argument("ledger"); ap.add_argument("delta")
    ap.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    ap.add_argument("--force", action="store_true", help="允许越界页（记录理由）")
    ap.add_argument("--receipts", help="JSONL receipt 输出路径")
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
        # 越界保护
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

    print(f"apply_delta: batch={batch} 计划更新 {len(planned)} 页，拒绝 {len(rejected)} 页")
    for p, s, eds in planned:
        print(f"  [PLAN] {p}: {len(eds)} 项字段更新")
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
        # 逐块应用（按行号倒序避免位移）
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
        print(f"apply_delta: 已写盘（备份 {args.ledger}.bak）")
    elif not args.apply:
        print("apply_delta: dry-run（加 --apply 写盘）")

    if args.receipts:
        r = kblib.make_receipt(TOOL, TOOL_VERSION, "delta_apply",
                               f"{os.path.basename(args.delta)} -> {os.path.basename(args.ledger)}",
                               result,
                               f"planned={len(planned)} rejected={len(rejected)} applied={bool(args.apply and result != 'fail')}", 1)
        kblib.write_receipts(args.receipts, [r])
    return 0 if result == "pass" else (1 if result == "fail" else 2)

if __name__ == "__main__":
    sys.exit(main())
