#!/usr/bin/env python3
"""跨文件重复块检测脚本。

用途：对 vault 内所有 .md 文件做段落级相似度扫描，找出可能违反
Cross-domain Rule Registry（见 00 Standards Control/05）的跨文件复制段落。
输出只是候选，最终是否违规由人工判定；候选进入维护轮 candidates 池消化。

调用层级（v2.0）：默认全库，维护轮与 governance 任务使用；批次与单页
层面不再调用（批次关闭仅保留 Batch-close Closed List 中的 basename 级
duplicate candidates，见 12/07）。

--scope 子路径：仅报告至少一方位于该子路径下的相似对（全库索引仍然
构建，以保证 scope 内文件与全库的配对不漏报）。

方法与阈值：
- 段落切分：按空行切分，只考虑长度 >= 40 字符的段落；
- 相似度：12 字符滑动 shingle 集合，Jaccard > 0.5 或 containment > 0.7 报告；
- 自动排除：文件名含 "v1.1 Legacy" 的文件；以链接列表为主的段落
  （以 [[ 开头的行占比 > 60%）；同一文件内部的段落配对。

用法：python3 duplicate_check.py [vault_path] [--scope 子路径]（默认当前目录）。
"""

import argparse
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

MIN_PARA_LEN = 40      # 参与比较的最小段落长度（字符）
SHINGLE_SIZE = 12      # shingle 窗口长度（字符）
JACCARD_THRESHOLD = 0.5
CONTAINMENT_THRESHOLD = 0.7
LINK_LINE_RATIO = 0.6  # 段落中 [[ 开头行占比超过该值视为链接列表，排除
MAX_EXAMPLES_PER_PAIR = 3  # 每对文件展示的示例段落数


def iter_markdown_files(vault: Path):
    """遍历 vault 下所有 .md 文件，跳过 v1.1 Legacy 文件。"""
    for path in sorted(vault.rglob("*.md")):
        if "v1.1 Legacy" in path.name:
            continue
        yield path


def split_paragraphs(text: str):
    """按空行切分段落，返回 (段落文本) 列表。"""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def is_link_list(paragraph: str) -> bool:
    """段落是否以 wiki link 列表为主（[[ 开头行占比 > 60%）。"""
    lines = [ln.strip() for ln in paragraph.splitlines() if ln.strip()]
    if not lines:
        return True
    link_lines = sum(1 for ln in lines if ln.lstrip("-*>0123456789. \t|").startswith("[["))
    return link_lines / len(lines) > LINK_LINE_RATIO


def shingles(paragraph: str):
    """生成段落的 12 字符 shingle 集合（压缩空白后滑窗）。"""
    normalized = re.sub(r"\s+", " ", paragraph)
    if len(normalized) < SHINGLE_SIZE:
        return set()
    return {normalized[i:i + SHINGLE_SIZE] for i in range(len(normalized) - SHINGLE_SIZE + 1)}


def collect_paragraphs(vault: Path):
    """收集所有可比较段落：[(file, para_text, shingle_set), ...]。"""
    items = []
    for path in iter_markdown_files(vault):
        text = path.read_text(encoding="utf-8", errors="replace")
        for para in split_paragraphs(text):
            if len(para) < MIN_PARA_LEN or is_link_list(para):
                continue
            sh = shingles(para)
            if sh:
                items.append((path, para, sh))
    return items


def find_duplicates(items):
    """两两比较段落，返回按文件对聚合的相似段落记录。

    用倒排索引先粗筛共享 shingle 的段落对，避免全量 O(n^2) 精确比较。
    """
    index = defaultdict(set)  # shingle -> item indexes
    for i, (_, _, sh) in enumerate(items):
        for s in sh:
            index[s].add(i)

    candidate_pairs = set()
    for idxs in index.values():
        if 1 < len(idxs) <= 50:  # 极常见 shingle 不用于配对
            candidate_pairs.update(combinations(sorted(idxs), 2))

    pairs = defaultdict(list)  # (file_a, file_b) -> [(score_desc, para_a, para_b)]
    for i, j in sorted(candidate_pairs):
        path_a, para_a, sh_a = items[i]
        path_b, para_b, sh_b = items[j]
        if path_a == path_b:  # 相同文件内配对排除
            continue
        inter = len(sh_a & sh_b)
        if not inter:
            continue
        jaccard = inter / len(sh_a | sh_b)
        containment = inter / min(len(sh_a), len(sh_b))
        if jaccard > JACCARD_THRESHOLD or containment > CONTAINMENT_THRESHOLD:
            key = tuple(sorted((str(path_a), str(path_b))))
            pairs[key].append((f"jaccard={jaccard:.2f} containment={containment:.2f}", para_a, para_b))
    return pairs


def summarize(paragraph: str, width: int = 80) -> str:
    """取段落首行压缩为单行摘要。"""
    flat = re.sub(r"\s+", " ", paragraph)
    return flat[:width] + ("…" if len(flat) > width else "")


def path_in_scope(path_str: str, scope: Path) -> bool:
    """path 是否等于 scope 或位于 scope 之下（scope 可为文件或目录）。"""
    try:
        Path(path_str).resolve().relative_to(scope)
        return True
    except ValueError:
        return False


def main():
    ap = argparse.ArgumentParser(description="跨文件重复段落候选检测（维护轮与 governance 使用）")
    ap.add_argument("vault", nargs="?", default=".", help="vault 根目录（默认当前目录）")
    ap.add_argument("--scope", help="子路径（相对 vault 或绝对）：仅报告至少一方在该子路径下的相似对")
    args = ap.parse_args()

    vault = Path(args.vault)
    scope = None
    if args.scope:
        scope_path = Path(args.scope)
        scope = (scope_path if scope_path.is_absolute() else vault / scope_path).resolve()

    items = collect_paragraphs(vault)
    pairs = find_duplicates(items)
    if scope is not None:
        pairs = {
            key: records for key, records in pairs.items()
            if path_in_scope(key[0], scope) or path_in_scope(key[1], scope)
        }

    if not pairs:
        print("未发现超过阈值的跨文件相似段落。")
        return

    scope_note = f"（scope: {args.scope}）" if scope is not None else ""
    print(f"发现 {len(pairs)} 个文件对存在相似段落（候选，需人工判定）{scope_note}：\n")
    for (file_a, file_b), records in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        print(f"[{len(records)} 处] {file_a} <-> {file_b}")
        for score, para_a, para_b in records[:MAX_EXAMPLES_PER_PAIR]:
            print(f"  - {score}")
            print(f"    A: {summarize(para_a)}")
            print(f"    B: {summarize(para_b)}")
        print()


if __name__ == "__main__":
    main()
