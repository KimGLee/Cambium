#!/usr/bin/env python3
"""check_moc.py —— domain MOC Module Index 与 leaf 实际 H2 headings 一致性候选检测。

规则 owner：12 Quality Assurance/05（Standards domain MOC、leaf module 一致性检查）。
只解析各 MOC `## Module Index` 小节表格：每行左列取 [[...|...]] 链接目标，右列取
反引号内的 section 名；与目标文件实际 `## ` headings 比对（`Navigation` 恒忽略）。
两个方向都报：文件有而 Index 未登记（missing_in_index）、Index 有而文件无
（stale_in_index）。**只产生候选**（退出码 2），最终判定交人工/维护轮；
仅维护轮与 governance 任务运行。

用法：python3 Tools/check_moc.py <standards_root> [--receipts PATH]
"""
import argparse, json, os, re, sys, time

MOC_GLOB_HINT = "Standard"  # domain MOC 文件名均以 ... Standard.md / Overview 结尾

def h2s(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("## "):
            h = line[3:].strip()
            if h != "Navigation" and not h.startswith("Navigation"):
                out.append(h)
    return out

def main():
    ap = argparse.ArgumentParser(description="MOC Module Index 一致性候选检测")
    ap.add_argument("root")
    ap.add_argument("--receipts")
    args = ap.parse_args()
    os.chdir(args.root)
    mocs = [f for f in sorted(os.listdir("."))
            if f.endswith(".md") and re.match(r"\d\d .*Standard\.md$", f)]
    cands = []
    for moc in mocs:
        text = open(moc, encoding="utf-8").read()
        m = re.search(r"## Module Index\n(.*?)(?=\n## |\Z)", text, re.S)
        if not m:
            continue
        for row in m.group(1).splitlines():
            lm = re.match(r"\| \[\[Knowledge Base Standards/([^\\|\]]+)\\?\|[^\]]*\]\] \| (.+) \|\s*$", row)
            if not lm:
                continue
            target, cell = lm.group(1) + ".md", lm.group(2)
            listed = re.findall(r"`([^`]+)`", cell)
            if not os.path.exists(target):
                cands.append((moc, target, "target_missing", ""))
                continue
            actual = [h for h in h2s(target)]
            for h in actual:
                if h not in listed:
                    cands.append((moc, target, "missing_in_index", h))
            for h in listed:
                if h not in actual:
                    cands.append((moc, target, "stale_in_index", h))
    for moc, target, kind, h in cands:
        print(f"  [CAND] {moc} -> {target}: {kind}: {h}")
    print(f"check_moc: {len(cands)} 个候选（{len(mocs)} 个 MOC 扫描）")
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
