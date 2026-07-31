#!/usr/bin/env python3
"""Terminal Proof 完整性检查脚本。

规则 owner：
- "12 Quality Assurance/06 Completion Terminal Audit and Final Report.md"
  （Terminal Proof 的完整字段清单，含 full_deterministic_results；
   完成条件：guidance 三个未决计数为 0、required_authoring_gaps=0、
   unverified_batches=0、unresolved_invalidations=0 且所有适用 gate 通过）；
- "12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md"
  （Terminal Reconciliation Rules：unresolved_invalidations 必须为 0）。

方法：
- 必填字段清单来自 Tools/schemas/terminal_proof.template.yaml 的顶层
  key（模板逐字段照抄 12/06，是本脚本的单一事实来源；--template 可覆盖）；
- proof 缺字段或字段为空 -> fail（Terminal Proof 不完整）；
- 零值条件字段（required_authoring_gaps / unverified_batches /
  unresolved_invalidations）非 0 -> fail；
- proof 出现清单外的多余顶层字段 -> candidate（是否合理由人判定）；
- 给了 --ledger（Coverage Ledger）时交叉校验：open_gaps 非空而 proof
  声称 required_authoring_gaps=0 -> fail。

退出码：0=全过，1=有 fail，2=无 fail 但有 candidate。

用法：python3 check_proof.py <proof.yaml> [--ledger coverage_ledger.yaml]
      [--template PATH] [--receipts PATH]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_proof"
TOOL_VERSION = "1.0.0"

# 12/06：完成条件中必须为 0 的字段（guidance 三个未决计数包含在
# guidance_reconciliation_result 的审阅里，不在此做数值断言）
ZERO_FIELDS = ("required_authoring_gaps", "unverified_batches",
               "unresolved_invalidations")


def main():
    ap = argparse.ArgumentParser(description="Terminal Proof 完整性与零值条件检查")
    ap.add_argument("proof", help="terminal proof YAML 文件路径")
    ap.add_argument("--ledger", help="Coverage Ledger YAML，用于 open_gaps 交叉校验")
    ap.add_argument("--template",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "schemas", "terminal_proof.template.yaml"),
                    help="字段清单模板（默认 Tools/schemas/terminal_proof.template.yaml）")
    ap.add_argument("--receipts", help="机读 receipts 追加写入的 JSONL 路径")
    args = ap.parse_args()

    template = kblib.parse_yaml_subset(open(args.template, encoding="utf-8").read())
    required_fields = list(template.keys())

    receipts = []
    seq = 0
    proof_name = os.path.basename(args.proof)

    try:
        proof = kblib.parse_yaml_subset(open(args.proof, encoding="utf-8").read())
    except (OSError, kblib.YamlSubsetError) as exc:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-unreadable", args.proof, "fail",
            "无法读取/解析 proof：%s" % exc, seq))
        kblib.write_receipts(args.receipts, receipts)
        print("check_proof: 无法读取或解析 %s：%s" % (args.proof, exc))
        return 1
    if not isinstance(proof, dict):
        proof = {}

    missing = []
    for field in required_fields:
        value = proof.get(field, None)
        # 注意：空列表 [] 对列表型字段合法（如 systemic_expansions: []），不算缺失
        if field not in proof or value is None or value == "":
            missing.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-field-missing",
                "%s#%s" % (proof_name, field), "fail",
                "Terminal Proof 缺少必填字段 %s（12/06 字段清单）" % field, seq))

    zero_bad = []
    for field in ZERO_FIELDS:
        if field in missing or field not in proof:
            continue
        value = proof.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            zero_bad.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-zero-field",
                "%s#%s" % (proof_name, field), "fail",
                "零值条件字段 %s = %r，完成条件要求必须为 0（12/06）" % (field, value), seq))

    extra = [k for k in proof if k not in required_fields]
    for field in extra:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-extra-field",
            "%s#%s" % (proof_name, field), "candidate",
            "字段 %s 不在 12/06 字段清单内（清单是'至少包含'，多余字段是否合理由人判定）"
            % field, seq))

    cross_fail = 0
    if args.ledger:
        try:
            ledger = kblib.parse_yaml_subset(open(args.ledger, encoding="utf-8").read())
        except (OSError, kblib.YamlSubsetError) as exc:
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "ledger-unreadable", args.ledger, "fail",
                "无法读取/解析 Coverage Ledger：%s" % exc, seq))
            ledger = None
        if isinstance(ledger, dict):
            open_gaps = ledger.get("open_gaps") or []
            gaps_claim = proof.get("required_authoring_gaps")
            if open_gaps and gaps_claim == 0:
                cross_fail += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "proof-ledger-mismatch",
                    "%s#required_authoring_gaps" % proof_name, "fail",
                    "Coverage Ledger open_gaps 有 %d 条未闭合缺口，但 proof 声称 "
                    "required_authoring_gaps=0（02/03：Coverage Ledger 是权威记录）"
                    % len(open_gaps), seq))

    if not any(r["result"] == "fail" for r in receipts):
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-check-summary", proof_name, "pass",
            "字段完整（%d/%d），零值条件字段均为 0%s" % (
                len(required_fields), len(required_fields),
                "，与 Coverage Ledger open_gaps 一致" if args.ledger else ""), seq))

    print("check_proof: 对照模板 %d 个必填字段检查 %s" % (len(required_fields), args.proof))
    print("  缺失字段=%d 零值条件违规=%d 多余字段(candidate)=%d ledger交叉失败=%d"
          % (len(missing), len(zero_bad), len(extra), cross_fail))
    for r in receipts:
        if r["result"] != "pass":
            print("  [%s %s] %s — %s" % (r["result"].upper()[:4], r["check"],
                                         r["target"], r["details"]))
    if not any(r["result"] == "fail" for r in receipts):
        print("  结论：Terminal Proof 完整性检查通过。")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
