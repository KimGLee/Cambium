#!/usr/bin/env python3
"""保质期（freshness / review_by）确定性检查脚本。

调用层级（v2.0）：维护轮专属；不在批次检查中运行（已从 12/05 每批自动
检查清单移除，维护轮开始时运行一次）。

规则 owner：
- "08 Metadata and Status/05 Review Source and Migration Metadata.md"
  （Freshness And Review Due：volatility 三档定义、domain 默认派发、
   复验间隔、review_by 计算与过期语义）；
- "08 Metadata and Status/01 Frontmatter and Core Vocabularies.md"
  （volatility / lifecycle 词表登记；review_by 为脚本生成只读字段）；
- "00 Standards Control/02 Task Routing and Pre-execution.md"
  （Maintenance Run Envelope：本脚本的过期清单是维护轮候选清单的输入之一）。

方法：
- 扫描 vault 内所有 .md 的 frontmatter（受限 YAML 子集解析，kblib）；
- 跳过 `lifecycle` 为 retired / merged 的页面；
- 跳过 Knowledge Base Standards 自身语料：路径含 "Knowledge Base Standards/"、
  匹配 --exempt 前缀，或 frontmatter type 为 standard / runtime-card /
  card-index；--include-standards 可取消该跳过；
- volatility 显式声明优先；缺省时按 domain 派发默认值（fast: agent / llm /
  retrieval-rag；slow: machine-learning / deep-learning / ai-systems；
  stable: modeling-fundamentals）；无 domain 或 domain 未映射时按
  --default-volatility（默认 slow）；
- 复验间隔：fast=120 天，slow=365 天，stable=不设到期（不产生候选）；
- 基准日期取 `last_verified`，缺则 `last_reviewed`；两者皆缺 -> 标记"待首验"；
- `review_by` = 基准日期 + 间隔；--as-of（默认今天）>= review_by 视为过期。

结果语义：过期与待首验一律 result=candidate——只把页面送入维护轮候选清单，
不自动改变页面任何状态轴（08/05）。输出按 priority（P0 最前）＋过期天数
（大在前）排序；待首验项排在同 priority 过期项之后。
退出码：0=无候选，2=存在候选；本脚本不产生 fail。

用法：python3 check_freshness.py <vault_root> [--scope 子路径]
      [--as-of YYYY-MM-DD] [--default-volatility fast|slow|stable]
      [--include-standards] [--exempt 前缀] [--receipts PATH]
"""

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_freshness"
TOOL_VERSION = "1.0.0"

# 复验间隔（天）：owner 08/05 Freshness And Review Due
INTERVAL_DAYS = {"fast": 120, "slow": 365, "stable": None}

# domain -> 默认 volatility：owner 08/05（表格逐字对应）
DOMAIN_DEFAULT = {
    "agent": "fast",
    "llm": "fast",
    "retrieval-rag": "fast",
    "machine-learning": "slow",
    "deep-learning": "slow",
    "ai-systems": "slow",
    "modeling-fundamentals": "stable",
}

# 标准语料自身的 frontmatter type（控制面/编译产物，不属于知识保鲜范围）
STANDARDS_TYPES = ("standard", "runtime-card", "card-index")

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def parse_date(value):
    """把 frontmatter 中的日期值解析为 date；无法解析返回 None。"""
    if value is None:
        return None
    s = str(value).strip().strip("\"'")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def load_frontmatter(path):
    """返回 (frontmatter dict 或 None, 是否解析失败)。"""
    text = open(path, encoding="utf-8", errors="replace").read()
    fm_text = kblib.extract_frontmatter(text)
    if fm_text is None:
        return None, False
    try:
        fm = kblib.parse_yaml_subset(fm_text)
    except kblib.YamlSubsetError:
        return None, True
    if not isinstance(fm, dict):
        return None, True
    return fm, False


def main():
    ap = argparse.ArgumentParser(description="保质期 / review_by 过期候选检查")
    ap.add_argument("vault_root", help="vault 根目录")
    ap.add_argument("--scope", help="只扫描该子路径下的 .md")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="计算过期的基准日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--default-volatility", dest="default_volatility",
                    default="slow", choices=("fast", "slow", "stable"),
                    help="无 domain 或 domain 未映射时使用的档位（默认 slow）")
    ap.add_argument("--include-standards", action="store_true",
                    help="也检查 Knowledge Base Standards 自身语料（默认跳过）")
    ap.add_argument("--exempt", action="append", default=[],
                    help="按前缀追加标准语料路径（可多次；同 check_language）")
    ap.add_argument("--receipts", help="机读 receipts 追加写入的 JSONL 路径")
    args = ap.parse_args()

    as_of = parse_date(args.as_of) if args.as_of else datetime.date.today()
    if as_of is None:
        print("check_freshness: --as-of 无法解析（要求 YYYY-MM-DD）：%r" % args.as_of)
        return 1

    exempt_prefixes = [e.strip("/").replace(os.sep, "/") for e in args.exempt]

    counts = {"files": 0, "skipped_standards": 0, "skipped_lifecycle": 0,
              "unparseable": 0, "stable": 0, "fresh": 0,
              "overdue": 0, "pending_first_verification": 0}
    candidates = []  # (prio_rank, -overdue_days, rel, details)

    for full, rel in kblib.iter_md_files(args.vault_root, args.scope):
        rel_disp = rel.replace(os.sep, "/")
        fm, unparseable = load_frontmatter(full)
        fm = fm or {}

        # ---- 标准语料跳过（--include-standards 可开） ----
        is_standards = (
            "Knowledge Base Standards/" in rel_disp
            or any(rel_disp == e or rel_disp.startswith(e + "/")
                   for e in exempt_prefixes)
            or str(fm.get("type", "")) in STANDARDS_TYPES
        )
        if is_standards and not args.include_standards:
            counts["skipped_standards"] += 1
            continue
        counts["files"] += 1
        if unparseable:
            counts["unparseable"] += 1

        # ---- lifecycle 跳过：retired / merged 页不再保鲜（03/03） ----
        lifecycle = str(fm.get("lifecycle") or "active")
        if lifecycle in ("retired", "merged"):
            counts["skipped_lifecycle"] += 1
            continue

        # ---- volatility 判定：显式 > domain 派发 > --default-volatility ----
        volatility = fm.get("volatility")
        volatility = str(volatility) if volatility else None
        if volatility not in INTERVAL_DAYS:
            domain = str(fm.get("domain") or "")
            volatility = DOMAIN_DEFAULT.get(domain, args.default_volatility)
        interval = INTERVAL_DAYS[volatility]
        if interval is None:
            counts["stable"] += 1
            continue

        priority = str(fm.get("priority") or "")
        prio_rank = PRIORITY_ORDER.get(priority, len(PRIORITY_ORDER))
        prio_disp = priority or "无priority"

        # ---- 基准日期：last_verified > last_reviewed > 待首验 ----
        baseline = parse_date(fm.get("last_verified"))
        baseline_field = "last_verified"
        if baseline is None:
            baseline = parse_date(fm.get("last_reviewed"))
            baseline_field = "last_reviewed"
        if baseline is None:
            counts["pending_first_verification"] += 1
            details = ("待首验：无 last_verified / last_reviewed 基准日期"
                       "（volatility=%s, priority=%s）" % (volatility, prio_disp))
            candidates.append((prio_rank, 1, rel_disp, details))
            continue

        review_by = baseline + datetime.timedelta(days=interval)
        if as_of >= review_by:
            overdue_days = (as_of - review_by).days
            counts["overdue"] += 1
            details = ("过期 %d 天：review_by=%s（%s=%s + %d 天, volatility=%s, "
                       "priority=%s）" % (overdue_days, review_by.isoformat(),
                                          baseline_field, baseline.isoformat(),
                                          interval, volatility, prio_disp))
            candidates.append((prio_rank, -overdue_days, rel_disp, details))
        else:
            counts["fresh"] += 1

    # 排序：priority（P0 前）> 过期天数（大在前）> 待首验 > 路径
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    receipts = []
    seq = 0
    for _, _, rel_disp, details in candidates:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "freshness", rel_disp, "candidate",
            details + "；进入维护轮候选清单（00/02 Envelope），不改变状态轴", seq))
    if not candidates:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "freshness-check-summary",
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "as_of=%s 无过期或待首验页面" % as_of.isoformat(), seq))

    print("check_freshness: as_of=%s 检查 %d 个文件（另跳过标准语料 %d、"
          "retired/merged %d）" % (as_of.isoformat(), counts["files"],
                                   counts["skipped_standards"],
                                   counts["skipped_lifecycle"]))
    print("  过期=%(overdue)d 待首验=%(pending_first_verification)d "
          "未到期=%(fresh)d stable不到期=%(stable)d "
          "frontmatter不可解析=%(unparseable)d" % counts)
    for _, _, rel_disp, details in candidates:
        print("  [CANDIDATE] %s — %s" % (rel_disp, details))
    if not candidates:
        print("  结论：无维护轮候选（过期=0、待首验=0）。")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
