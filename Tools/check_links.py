#!/usr/bin/env python3
"""Wiki link 确定性检查脚本（missing / ambiguous / heading resolution）。

规则 owner：
- "09 Wiki Link and Navigation/03 Path Alias and Heading Links.md"
  （path/alias 规则、表格中 `\\|` 转义、heading links）；
- "09 Wiki Link and Navigation/05 Verification and Anti-patterns.md"
  （每批任务完成后必须 missing=0、ambiguous=0，无错误 heading links）；
- "03 Note Types and Ownership/03 Split and Duplication Policy.md"
  （Retirement / Merge：退役 gate 要求入链逐条改指接替页；因此链接目标
   frontmatter 为 lifecycle: retired / merged 时报 candidate 提示改指）。

方法：
- 扫描 vault 内所有 .md 文件，先剔除 fenced code block 和行内代码，
  再提取 `[[target#heading|alias]]` 形式的链接（处理 `\\|` 转义）；
- 解析规则：target 含 `/` 时先按完整 vault-relative 路径精确匹配；
  精确匹配失败或 target 只有 basename 时按 basename 匹配：
  唯一匹配 -> resolved；多个匹配 -> ambiguous；无匹配 -> missing；
- 带 `#heading` 的链接对解析出的目标文件做 heading 存在性校验
  （精确比较，失败后再做大小写不敏感比较；`#^block` 引用跳过）。

结果语义：missing / ambiguous / 坏 heading 一律 result=fail
（09/05 要求三者为零）；目标页 lifecycle 为 retired / merged 只报
result=candidate（建议改指其 superseded_by 接替页，03/03），不算 fail。
退出码：0=全过，1=有 fail，2=无 fail 但有 candidate。

用法：python3 check_links.py <vault_root> [--scope 子路径] [--receipts PATH]
"""

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_links"
TOOL_VERSION = "1.1.0"

LINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")


def parse_link(inner):
    """拆出 (target_path, heading)；去掉 alias。

    表格中的 alias 分隔符写作 `\\|`（09/03：Markdown 表格中的 wiki alias
    pipe 必须转义），因此 `\\|` 和 `|` 都视为 target/alias 分隔符。
    """
    target_part = re.split(r"\\\||\|", inner, maxsplit=1)[0].strip()
    target, _, heading = target_part.partition("#")
    target = target.strip()
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target, heading.strip()


def build_index(files):
    """files: [(fullpath, relpath)]。返回 (路径索引, basename 索引)。"""
    by_path = {}
    by_base = defaultdict(list)
    for full, rel in files:
        key = rel[:-3].replace(os.sep, "/")  # 去 .md，统一分隔符
        by_path[key] = full
        by_base[key.rsplit("/", 1)[-1]].append(key)
    return by_path, by_base


def resolve(target, by_path, by_base):
    """返回 (status, resolved_key_or_candidates)。status: resolved/ambiguous/missing。"""
    if "/" in target and target in by_path:
        return "resolved", target
    base = target.rsplit("/", 1)[-1]
    matches = by_base.get(base, [])
    if len(matches) == 1:
        return "resolved", matches[0]
    if len(matches) > 1:
        return "ambiguous", matches
    return "missing", None


def headings_cache_get(cache, by_path, key):
    if key not in cache:
        text = open(by_path[key], encoding="utf-8", errors="replace").read()
        cache[key] = [h for _, _, h in kblib.headings_of(kblib.strip_code(text))]
    return cache[key]


def lifecycle_cache_get(cache, by_path, key):
    """返回目标页 {'lifecycle':..., 'superseded_by':...}（frontmatter 缺失/不可解析视为 active）。"""
    if key not in cache:
        info = {"lifecycle": None, "superseded_by": None}
        fm_text = kblib.extract_frontmatter(
            open(by_path[key], encoding="utf-8", errors="replace").read())
        if fm_text is not None:
            try:
                fm = kblib.parse_yaml_subset(fm_text)
            except kblib.YamlSubsetError:
                fm = None
            if isinstance(fm, dict):
                info["lifecycle"] = fm.get("lifecycle")
                info["superseded_by"] = fm.get("superseded_by")
        cache[key] = info
    return cache[key]


def main():
    ap = argparse.ArgumentParser(description="Wiki link missing/ambiguous/heading 检查")
    ap.add_argument("vault_root", help="vault 根目录")
    ap.add_argument("--scope", help="只扫描该子路径下的 .md（索引仍用全库）")
    ap.add_argument("--receipts", help="机读 receipts 追加写入的 JSONL 路径")
    args = ap.parse_args()

    all_files = kblib.iter_md_files(args.vault_root)
    scan_files = kblib.iter_md_files(args.vault_root, args.scope) if args.scope else all_files
    by_path, by_base = build_index(all_files)
    heading_cache = {}
    lifecycle_cache = {}

    receipts = []
    seq = 0
    counts = {"links": 0, "missing": 0, "ambiguous": 0, "bad_heading": 0,
              "block_ref_skipped": 0, "retired_target": 0}

    for full, rel in scan_files:
        text = kblib.strip_code(open(full, encoding="utf-8", errors="replace").read())
        rel_key = rel[:-3].replace(os.sep, "/")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in LINK_RE.finditer(line):
                target, heading = parse_link(m.group(1))
                counts["links"] += 1
                where = "%s:%d" % (rel.replace(os.sep, "/"), lineno)
                if target == "":
                    status, resolved = "resolved", rel_key  # [[#heading]] 自引用
                else:
                    status, resolved = resolve(target, by_path, by_base)
                if status == "missing":
                    counts["missing"] += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "link-missing", where, "fail",
                        "[[%s]] 无匹配目标（missing）" % m.group(1), seq))
                    continue
                if status == "ambiguous":
                    counts["ambiguous"] += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "link-ambiguous", where, "fail",
                        "[[%s]] basename 多匹配（ambiguous）: %s" % (m.group(1), "; ".join(resolved)), seq))
                    continue
                # 目标页已退役/合并：candidate（03/03 要求入链改指接替页），不算 fail
                if target != "" and resolved != rel_key:
                    life = lifecycle_cache_get(lifecycle_cache, by_path, resolved)
                    if str(life["lifecycle"]) in ("retired", "merged"):
                        counts["retired_target"] += 1
                        seq += 1
                        hint = ("接替页 superseded_by: %s" % life["superseded_by"]
                                if life["superseded_by"] else "目标页未声明 superseded_by，改指前先核对其 tombstone")
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION, "link-retired-target", where, "candidate",
                            "[[%s]] 指向 lifecycle: %s 的页面 %s；建议改指接替页（%s；03/03 退役 gate）"
                            % (m.group(1), life["lifecycle"], resolved, hint), seq))
                if heading:
                    if heading.startswith("^"):
                        counts["block_ref_skipped"] += 1  # block 引用无法确定性校验
                        continue
                    hs = headings_cache_get(heading_cache, by_path, resolved)
                    if heading not in hs and heading.casefold() not in {h.casefold() for h in hs}:
                        counts["bad_heading"] += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION, "link-bad-heading", where, "fail",
                            "[[%s]] 目标 %s 中不存在 heading '%s'" % (m.group(1), resolved, heading), seq))

    problems = counts["missing"] + counts["ambiguous"] + counts["bad_heading"]
    if problems == 0:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "link-check-summary",
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "missing=0 ambiguous=0 bad_heading=0（共 %d 个链接）" % counts["links"], seq))

    print("check_links: 扫描 %d 个文件、%d 个链接" % (len(scan_files), counts["links"]))
    print("  missing=%(missing)d ambiguous=%(ambiguous)d bad_heading=%(bad_heading)d "
          "block_ref_skipped=%(block_ref_skipped)d retired_target(candidate)=%(retired_target)d" % counts)
    for r in receipts:
        if r["result"] == "fail":
            print("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))
        elif r["result"] == "candidate":
            print("  [CAND %s] %s — %s" % (r["check"], r["target"], r["details"]))
    if problems == 0:
        print("  结论：链接检查全部通过（09/05: missing=0, ambiguous=0）。")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
