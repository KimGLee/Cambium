#!/usr/bin/env python3
"""中文优先语言检查脚本（只产生候选，不判 fail）。

规则 owner："10 Writing and Formatting/05 Chinese-first Technical Language.md"。
其 Acceptance And Audit 一节明确限定：自动检查可以发现英文-only heading
candidates 等信号，但"字符比例和英文密度只能产生 review candidates，
不能自动判错，因为代码、schema、Source identity 和 Interview English
sections 可能合法。最终判断必须执行有范围、有例外记录的人工或模型审阅。"
因此本脚本所有发现一律 result=candidate，绝不输出 fail。

检查项：
a) reader-facing 的 H2/H3 heading 全英文（不含任何中文字符）且没有
   `（中文注释）`后缀 —— 10/05 Headings And Titles 要求英文 heading
   使用 `English Title（中文注释）` 格式；
b) 反向双语格式 `中文（English）` 作标题 —— 10/05 禁止反向格式，
   英文身份必须位于括号外；
c) 正文段落里英文术语首现后缺中文括注：**不检**。该判定依赖"首次
   有意义出现"“受保护英文”等语义边界，不可确定性判定，按 10/05
   只能交给人工/模型审阅。

豁免（10/05 Standards Corpus Exemption）：`Knowledge Base Standards/`
语料自身（标准与管理页面）豁免"英文标题必须加中文注释"，因此路径中
含该文件夹的文件整体跳过；可用 --exempt 追加其它豁免子路径。
代码块内的 heading 样例一律跳过。

退出码：0=无候选，2=存在候选（本脚本不会返回 1）。

用法：python3 check_language.py <vault_root> [--scope 子路径]
      [--exempt 子路径 ...] [--receipts PATH]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_language"
TOOL_VERSION = "1.0.0"

EXEMPT_COMPONENT = "Knowledge Base Standards"  # 10/05 Standards Corpus Exemption

CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
# 反向双语：中文开头（可夹专名），括号内是纯英文/数字/常见符号
REVERSE_RE = re.compile(
    r"^(?P<zh>[^（()]*[一-鿿][^（()]*)（(?P<en>[A-Za-z][A-Za-z0-9 ,./&+'\-]*)）$")


def has_cjk(text):
    return bool(CJK_RE.search(text))


def is_exempt(rel, extra):
    parts = rel.replace(os.sep, "/").split("/")
    if EXEMPT_COMPONENT in parts:
        return True
    rel_norm = rel.replace(os.sep, "/")
    for ex in extra:
        ex_norm = ex.strip("/").replace(os.sep, "/")
        if ex_norm in (".", "") or rel_norm == ex_norm or rel_norm.startswith(ex_norm + "/"):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="中文优先语言候选检测（只产生候选）")
    ap.add_argument("vault_root", help="vault 根目录")
    ap.add_argument("--scope", help="只扫描该子路径下的 .md")
    ap.add_argument("--exempt", action="append", default=[],
                    help="追加豁免子路径（可多次；'.' 表示全部豁免）")
    ap.add_argument("--receipts", help="机读 receipts 追加写入的 JSONL 路径")
    args = ap.parse_args()

    receipts = []
    seq = 0
    counts = {"files": 0, "exempt_files": 0, "headings": 0,
              "english_only": 0, "reverse_bilingual": 0}

    for full, rel in kblib.iter_md_files(args.vault_root, args.scope):
        if is_exempt(rel, args.exempt):
            counts["exempt_files"] += 1
            continue
        counts["files"] += 1
        rel_disp = rel.replace(os.sep, "/")
        text = kblib.strip_code(open(full, encoding="utf-8", errors="replace").read())
        for lineno, level, heading in kblib.headings_of(text):
            if level not in (2, 3):  # 只检 reader-facing H2/H3
                continue
            counts["headings"] += 1
            where = "%s:%d" % (rel_disp, lineno)
            if not has_cjk(heading):
                counts["english_only"] += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "language-english-only-heading", where,
                    "candidate",
                    "H%d 全英文且无（中文）后缀: %r；10/05 要求 reader-facing 英文 "
                    "heading 使用 `English Title（中文注释）`；是否合法例外由人判定"
                    % (level, heading), seq))
                continue
            m = REVERSE_RE.match(heading.strip())
            if m:
                counts["reverse_bilingual"] += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "language-reverse-bilingual-heading", where,
                    "candidate",
                    "H%d 使用反向双语格式 `中文（English）`: %r；10/05 要求英文身份 "
                    "位于括号外（`English（中文）`）；是否误报由人判定"
                    % (level, heading), seq))

    total = counts["english_only"] + counts["reverse_bilingual"]
    if total == 0:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "language-check-summary",
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "未发现语言候选（english_only=0, reverse_bilingual=0；"
            "豁免 %d 个标准语料文件）" % counts["exempt_files"], seq))

    print("check_language: 扫描 %(files)d 个文件（另豁免 %(exempt_files)d 个），"
          "H2/H3 共 %(headings)d 个" % counts)
    print("  候选：english_only_heading=%(english_only)d "
          "reverse_bilingual_heading=%(reverse_bilingual)d（一律 candidate，"
          "最终判定按 10/05 交人工/模型审阅）" % counts)
    shown = 0
    for r in receipts:
        if r["result"] == "candidate" and shown < 20:
            print("  [CAND %s] %s" % (r["check"], r["target"]))
            shown += 1
    if total > shown:
        print("  ... 其余 %d 条候选见 receipts" % (total - shown))

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
