#!/usr/bin/env python3
"""Frontmatter 受控词表检查脚本。

规则 owner：
- "08 Metadata and Status/01 Frontmatter and Core Vocabularies.md"（schema 与 type/domain 词表）；
- "08 Metadata and Status/02 Scope Level Depth and Priority.md"（scope/level/depth/priority）；
- "08 Metadata and Status/03 Status Axes.md"（四条状态轴与 coverage_disposition）；
- "08 Metadata and Status/04 Evidence and Relationship Metadata.md"
  （evidence_maturity；旧 `status` 字段是 authoring_status 的迁移期兼容别名）。
词表取值来自编译产物 Tools/vocab.yaml（修订 owner 后必须重新生成）。

方法：
- 用受限 YAML 子集解析器（kblib.parse_yaml_subset）解析每个 .md 的
  `---` 围栏 frontmatter；
- 受控字段的取值必须在 vocab 内：未知值 -> result=fail；
- 字段缺失或为空 -> result=candidate（缺失是否允许由人判定：08/01
  说明"按适用字段使用"，08/05 说明无 frontmatter 页面默认 unassessed）；
- 整个文件没有 frontmatter -> 一条 candidate；frontmatter 超出子集
  语法无法解析 -> 一条 candidate。

退出码：0=全过，1=有 fail，2=无 fail 但有 candidate。

用法：python3 check_vocab.py <vault_root> [--scope 子路径]
      [--vocab Tools/vocab.yaml] [--receipts PATH]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_vocab"
TOOL_VERSION = "1.0.0"


def load_vocab(path):
    data = kblib.parse_yaml_subset(open(path, encoding="utf-8").read())
    fields = data.get("fields") or {}
    vocab = {}
    for name, spec in fields.items():
        vocab[name] = {
            "values": [str(v) for v in (spec.get("values") or [])],
            "owner": spec.get("owner", ""),
        }
    return vocab


def main():
    ap = argparse.ArgumentParser(description="Frontmatter 受控词表检查")
    ap.add_argument("vault_root", help="vault 根目录")
    ap.add_argument("--scope", help="只扫描该子路径下的 .md")
    ap.add_argument("--vocab", default=None,
                    help="vocab.yaml 路径（默认取脚本同目录的 vocab.yaml）")
    ap.add_argument("--exclude", action="append", default=[],
                    help="排除子路径（可多次；如编译产物 Cards/，其 frontmatter "
                         "不受 08 域知识页 schema 管辖）")
    ap.add_argument("--receipts", help="机读 receipts 追加写入的 JSONL 路径")
    args = ap.parse_args()

    vocab_path = args.vocab or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "vocab.yaml")
    vocab = load_vocab(vocab_path)

    receipts = []
    seq = 0
    counts = {"files": 0, "no_frontmatter": 0, "unparseable": 0,
              "unknown_value": 0, "missing_field": 0, "ok_values": 0}
    dist = {"priority": {}, "tier": {}}  # 00/02 Priority Quota 分布统计

    excludes = [e.strip("/").replace(os.sep, "/") for e in args.exclude]
    for full, rel in kblib.iter_md_files(args.vault_root, args.scope):
        rel_disp = rel.replace(os.sep, "/")
        if any(rel_disp == e or rel_disp.startswith(e + "/") for e in excludes):
            continue
        counts["files"] += 1
        text = open(full, encoding="utf-8", errors="replace").read()
        fm_text = kblib.extract_frontmatter(text)
        if fm_text is None:
            counts["no_frontmatter"] += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "frontmatter-missing", rel_disp, "candidate",
                "文件没有 frontmatter；按 08/05 默认 authoring_status=unassessed，"
                "是否需要补 frontmatter 由人判定", seq))
            continue
        try:
            fm = kblib.parse_yaml_subset(fm_text)
        except kblib.YamlSubsetError as exc:
            counts["unparseable"] += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "frontmatter-unparseable", rel_disp, "candidate",
                "frontmatter 超出受限 YAML 子集语法，无法确定性判定：%s" % exc, seq))
            continue
        for _axis in ("priority", "tier"):
            _v = fm.get(_axis)
            if isinstance(_v, str) and _v.strip():
                dist[_axis][_v.strip()] = dist[_axis].get(_v.strip(), 0) + 1
        if not isinstance(fm, dict):
            counts["unparseable"] += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "frontmatter-unparseable", rel_disp, "candidate",
                "frontmatter 顶层不是映射结构", seq))
            continue

        # 旧 `status` 字段：迁移期视为 authoring_status 的兼容别名（08/04）
        effective = dict(fm)
        if "authoring_status" not in effective and "status" in effective:
            effective["authoring_status"] = effective["status"]

        for field, spec in vocab.items():
            value = effective.get(field)
            if field not in effective or value is None or value == "" or value == []:
                counts["missing_field"] += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "vocab-field-missing",
                    "%s#%s" % (rel_disp, field), "candidate",
                    "受控字段 %s 缺失或为空；是否允许缺失由人判定（owner: %s）"
                    % (field, spec["owner"]), seq))
                continue
            for v in (value if isinstance(value, list) else [value]):
                sval = str(v)
                if sval not in spec["values"]:
                    counts["unknown_value"] += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "vocab-unknown-value",
                        "%s#%s" % (rel_disp, field), "fail",
                        "字段 %s 的取值 %r 不在受控词表内（owner: %s；合法值: %s）"
                        % (field, sval, spec["owner"], ", ".join(spec["values"])), seq))
                else:
                    counts["ok_values"] += 1

    if not any(r["result"] == "fail" for r in receipts):
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "vocab-check-summary",
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "未发现受控词表非法取值（unknown_value=0；candidate 另计）", seq))

    print("check_vocab: 扫描 %(files)d 个文件" % counts)
    print("  无 frontmatter=%(no_frontmatter)d 不可解析=%(unparseable)d "
          "非法取值(fail)=%(unknown_value)d 缺字段(candidate)=%(missing_field)d "
          "合法取值=%(ok_values)d" % counts)
    for r in receipts:
        if r["result"] == "fail":
            print("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))

    # 分布统计与 Priority Quota 检查（owner: 00/02 Effort Tiering / Priority Quota）
    for _axis in ("priority", "tier"):
        _tot = sum(dist[_axis].values())
        if _tot:
            _parts = ", ".join("%s=%d(%.0f%%)" % (k, v, 100.0 * v / _tot)
                               for k, v in sorted(dist[_axis].items()))
            print("  %s 分布: %s" % (_axis, _parts))
    _ptot = sum(dist["priority"].values())
    _p0 = dist["priority"].get("P0", 0)
    if _ptot and _p0 * 100.0 / _ptot > 15.0:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "priority-quota", "vault", "candidate",
            "P0 占比 %.0f%%（%d/%d）超出 00/02 Priority Quota 目标 ≤15%%；"
            "超配页面须降级或在 Coverage Ledger 记录豁免" % (_p0 * 100.0 / _ptot, _p0, _ptot), seq))
        print("  [CAND priority-quota] P0 占比 %.0f%% 超出 ≤15%% 配额（00/02）" % (_p0 * 100.0 / _ptot))

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
