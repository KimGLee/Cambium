#!/usr/bin/env python3
"""kbstd 检查脚本共享库（仅标准库，无第三方依赖）。

提供：
1. 受限 YAML 子集解析器 parse_yaml_subset —— 仅支持以下语法
   （与 Tools/schemas/*.template.yaml 头注释中声明的子集一致）：
   - `key: value` 标量（字符串 / 整数 / 浮点 / 布尔 / 空值）；
   - 带引号字符串与内联空列表 `[]`、简单内联列表 `[a, b]`；
   - `key:` 之后缩进的 `- 项` 列表；
   - 列表项可以是一层平铺 map（`- key: value` 后接同缩进的 key 行）；
   - 两级及以上缩进嵌套 map（解析器递归实现，天然支持更深层级，
     但标准约定只使用两级）。
   不支持：锚点/别名、多行字符串（| >）、flow map `{}`、tag、多文档。
2. Markdown 工具：frontmatter 提取、代码块剔除（保持行号）、heading 提取。
3. Receipt 工具：机读 JSONL receipt 的构造与追加写入（字段定义见
   Tools/schemas/receipt.template.jsonl），以及统一退出码约定：
   0 = 全部 pass；1 = 存在 fail；2 = 无 fail 但存在 candidate。
"""

import json
import os
import re
import time

LIB_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# 受限 YAML 子集解析器
# ---------------------------------------------------------------------------


class YamlSubsetError(ValueError):
    """输入超出受限 YAML 子集语法时抛出。"""


def _strip_comment(line):
    """去掉行内注释（# 前需要是行首或空白；引号内的 # 保留）。"""
    out = []
    quote = None
    for idx, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        else:
            if ch in "\"'":
                quote = ch
                out.append(ch)
            elif ch == "#" and (idx == 0 or line[idx - 1] in " \t"):
                break
            else:
                out.append(ch)
    return "".join(out).rstrip()


def parse_scalar(text):
    """解析单个标量：引号字符串、内联列表、布尔、空值、整数、浮点、裸字符串。"""
    s = text.strip()
    if s == "":
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s == "[]":
        return []
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _prepare_lines(text):
    """预处理：去注释、去空行、去文档围栏，返回 [(indent, content), ...]。"""
    lines = []
    for raw in text.splitlines():
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlSubsetError("缩进不允许使用 Tab: %r" % raw)
        line = _strip_comment(raw)
        stripped = line.strip()
        if not stripped or stripped in ("---", "..."):
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append([indent, stripped])
    return lines


def _looks_like_map_entry(content):
    """`key: value` 或 `key:`，key 不含空白冒号且不是引号开头的纯标量。"""
    if content[0] in "\"'":
        # 引号开头：可能是 "key": value，子集里不使用引号 key，视为标量
        return False
    return re.match(r"^[^:\s][^:]*:(\s|$)", content) is not None


def _parse_map(lines, i, indent):
    result = {}
    while i < len(lines):
        cur_indent, content = lines[i]
        if cur_indent != indent or content.startswith("- ") or content == "-":
            break
        m = re.match(r"^([^:]+?)\s*:\s*(.*)$", content)
        if not m:
            raise YamlSubsetError("无法解析映射行: %r" % content)
        key, rest = m.group(1).strip(), m.group(2)
        i += 1
        if rest:
            result[key] = parse_scalar(rest)
            continue
        # `key:` 空值 —— 看后续行决定嵌套 map / 列表 / 空
        if i < len(lines) and lines[i][0] > indent:
            value, i = _parse_block(lines, i, lines[i][0])
        elif i < len(lines) and lines[i][0] == indent and (
            lines[i][1] == "-" or lines[i][1].startswith("- ")
        ):
            value, i = _parse_list(lines, i, indent)
        else:
            value = None
        result[key] = value
    return result, i


def _parse_list(lines, i, indent):
    result = []
    while i < len(lines):
        cur_indent, content = lines[i]
        if cur_indent != indent or not (content == "-" or content.startswith("- ")):
            break
        rest = content[1:].strip()
        if rest == "":
            i += 1
            if i < len(lines) and lines[i][0] > indent:
                value, i = _parse_block(lines, i, lines[i][0])
            else:
                value = None
            result.append(value)
        elif _looks_like_map_entry(rest):
            # 列表项为一层平铺 map：`- key: value` 后接同虚拟缩进的 key 行
            item_indent = cur_indent + (len(content) - len(rest))
            lines[i] = [item_indent, rest]
            value, i = _parse_map(lines, i, item_indent)
            result.append(value)
        else:
            result.append(parse_scalar(rest))
            i += 1
    return result, i


def _parse_block(lines, i, indent):
    if lines[i][1] == "-" or lines[i][1].startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def parse_yaml_subset(text):
    """解析受限 YAML 子集，返回 dict / list / 标量；空输入返回 {}。"""
    lines = _prepare_lines(text)
    if not lines:
        return {}
    value, i = _parse_block(lines, 0, lines[0][0])
    if i != len(lines):
        raise YamlSubsetError(
            "第 %d 段之后存在无法归属的行（缩进错误或超出子集语法）: %r"
            % (i, lines[i][1])
        )
    return value


# ---------------------------------------------------------------------------
# Markdown 工具
# ---------------------------------------------------------------------------


def extract_frontmatter(text):
    """提取 `---` 围栏内的 frontmatter 原文；不存在时返回 None。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() in ("---", "..."):
            return "\n".join(lines[1:idx])
    return None


def strip_code(text):
    """剔除 fenced code block 与行内代码，保持行数不变（便于报告行号）。"""
    out = []
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        m = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and m:
            fence = m.group(1)[0] * 3
            out.append("")
            continue
        if fence is not None:
            if m and stripped.startswith(fence):
                fence = None
            out.append("")
            continue
        out.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


def iter_md_files(vault_root, scope=None):
    """遍历 vault 下所有 .md 文件（按相对路径排序）；scope 为可选子路径。"""
    base = os.path.join(vault_root, scope) if scope else vault_root
    base = os.path.normpath(base)
    result = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                full = os.path.join(dirpath, name)
                result.append((full, os.path.relpath(full, vault_root)))
    return result


def headings_of(text):
    """返回 [(行号, 级别, heading 文本)]；输入应先经过 strip_code。"""
    result = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            result.append((lineno, len(m.group(1)), m.group(2).strip()))
    return result


# ---------------------------------------------------------------------------
# Receipt 工具（字段定义见 Tools/schemas/receipt.template.jsonl）
# ---------------------------------------------------------------------------


def make_receipt(tool, tool_version, check, target, result, details, seq):
    """构造一条 receipt dict；result 只允许 pass / fail / candidate。"""
    assert result in ("pass", "fail", "candidate"), result
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return {
        "receipt_id": "audit-%s-%s-%04d" % (tool, stamp, seq),
        "check": check,
        "target": target,
        "result": result,
        "details": details,
        "checked_at": checked_at,
        "tool": tool,
        "tool_version": tool_version,
        "invalidated_by": None,
    }


def write_receipts(path, receipts):
    """把 receipts 以 JSONL 追加写入 path（一行一个 JSON 对象）。"""
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for receipt in receipts:
            fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")


def exit_code(receipts):
    """统一退出码：1 = 有 fail；2 = 无 fail 但有 candidate；0 = 全 pass。"""
    results = {r["result"] for r in receipts}
    if "fail" in results:
        return 1
    if "candidate" in results:
        return 2
    return 0
