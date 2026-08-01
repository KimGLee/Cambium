#!/usr/bin/env python3
"""Shared library for the kbstd check scripts (standard library only, no third-party dependencies).

Provides:
1. A restricted YAML subset parser, parse_yaml_subset -- only the following
   grammar is supported (matching the subset declared in the header comments
   of Tools/schemas/*.template.yaml):
   - `key: value` scalars (string / int / float / bool / null);
   - quoted strings and the inline empty list `[]`, simple inline lists
     `[a, b]`;
   - `- item` lists indented under a `key:` line;
   - a list item may be a one-level flat map (`- key: value` followed by key
     lines at the same indentation);
   - nested maps two or more levels deep (the parser is recursive and
     naturally supports deeper nesting, but the standards convention only
     uses two levels).
   Not supported: anchors/aliases, multi-line strings (| >), flow maps `{}`,
   tags, multiple documents.
2. Markdown helpers: frontmatter extraction, code-block stripping (preserving
   line numbers), heading extraction.
3. Receipt helpers: construction and append-writing of machine-readable JSONL
   receipts (field definitions in Tools/schemas/receipt.template.jsonl), plus
   the shared exit-code convention:
   0 = all pass; 1 = at least one fail; 2 = no fail but candidates.
"""

import json
import os
import re
import time

LIB_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Restricted YAML subset parser
# ---------------------------------------------------------------------------


class YamlSubsetError(ValueError):
    """Raised when the input goes beyond the restricted YAML subset grammar."""


def _strip_comment(line):
    """Strip inline comments (# must be at start of line or preceded by whitespace; # inside quotes is kept)."""
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
    """Parse a single scalar: quoted string, inline list, bool, null, int, float, bare string."""
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
    """Preprocess: strip comments, blank lines and document fences; return [(indent, content), ...]."""
    lines = []
    for raw in text.splitlines():
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlSubsetError("tabs are not allowed in indentation: %r" % raw)
        line = _strip_comment(raw)
        stripped = line.strip()
        if not stripped or stripped in ("---", "..."):
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append([indent, stripped])
    return lines


def _looks_like_map_entry(content):
    """`key: value` or `key:`; the key contains no whitespace-colon and is not a quoted plain scalar."""
    if content[0] in "\"'":
        # Starts with a quote: could be "key": value, but the subset does not
        # use quoted keys, so treat it as a scalar
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
            raise YamlSubsetError("cannot parse mapping line: %r" % content)
        key, rest = m.group(1).strip(), m.group(2)
        i += 1
        if rest:
            result[key] = parse_scalar(rest)
            continue
        # `key:` with no value -- the following lines decide: nested map / list / empty
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
            # List item is a one-level flat map: `- key: value` followed by
            # key lines at the same virtual indentation
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
    """Parse the restricted YAML subset; returns a dict / list / scalar; empty input returns {}."""
    lines = _prepare_lines(text)
    if not lines:
        return {}
    value, i = _parse_block(lines, 0, lines[0][0])
    if i != len(lines):
        raise YamlSubsetError(
            "unattachable line after block %d (bad indentation or beyond the subset grammar): %r"
            % (i, lines[i][1])
        )
    return value


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


def extract_frontmatter(text):
    """Extract the raw frontmatter inside the `---` fence; returns None when absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() in ("---", "..."):
            return "\n".join(lines[1:idx])
    return None


def strip_code(text):
    """Strip fenced code blocks and inline code, preserving the line count (so line numbers stay reportable)."""
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
    """Walk all .md files under the vault (sorted by relative path); scope is an optional subpath."""
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
    """Return [(lineno, level, heading text)]; the input should have gone through strip_code first."""
    result = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            result.append((lineno, len(m.group(1)), m.group(2).strip()))
    return result


# ---------------------------------------------------------------------------
# Receipt helpers (field definitions in Tools/schemas/receipt.template.jsonl)
# ---------------------------------------------------------------------------


def make_receipt(tool, tool_version, check, target, result, details, seq):
    """Build one receipt dict; result must be pass / fail / candidate."""
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
    """Append receipts to path as JSONL (one JSON object per line)."""
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for receipt in receipts:
            fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")


def exit_code(receipts):
    """Shared exit codes: 1 = at least one fail; 2 = no fail but candidates; 0 = all pass."""
    results = {r["result"] for r in receipts}
    if "fail" in results:
        return 1
    if "candidate" in results:
        return 2
    return 0
