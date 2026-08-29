"""Shared deterministic Markdown structure predicates.

This module owns no governance rule.  It centralizes the byte-level parsing
already used by ``check_batch_close`` so changed-scope producers and the
post-Delta Closed List do not maintain two implementations of fence and table
structure.  Semantic questions such as whether a section is useful or a table
cell is too long are deliberately absent.
"""

import re

import kblib


_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
_UNESCAPED_TABLE_ALIAS_RE = re.compile(r"\[\[[^\]\n]*(?<!\\)\|[^\]\n]*\]\]")


def split_pipe_row(line):
    """Return cells for one outer-pipe Markdown row."""
    value = line.strip()
    if not value.startswith("|") or not value.endswith("|"):
        return []
    cells = re.split(r"(?<!\\)\|", value[1:-1])
    return [cell.replace("\\|", "|").strip() for cell in cells]


def table_separator(cells):
    """Return whether ``cells`` are one Markdown delimiter row."""
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", ""))
        for cell in cells
    )


def fence_scan(text):
    """Return all fence openers and any final unclosed opener.

    The envelope is byte-for-byte the predicate formerly embedded in
    ``check_batch_close._structural_check``: up to three leading spaces, a
    matching marker character, a closing run at least as long as the opener,
    and no non-whitespace closing tail.
    """
    blocks = []
    current = None
    for line_number, line in enumerate((text or "").splitlines(), 1):
        match = _FENCE_RE.match(line)
        if not match:
            continue
        marker, tail = match.groups()
        if current is None:
            info = tail.strip()
            current = {
                "line": line_number,
                "marker": marker,
                "language": info.split(None, 1)[0].lower() if info else "",
            }
            continue
        if (marker[0] == current["marker"][0] and
                len(marker) >= len(current["marker"]) and
                not tail.strip()):
            block = dict(current)
            block["closing_line"] = line_number
            blocks.append(block)
            current = None
    return tuple(blocks), current


def table_scan(text):
    """Return deterministic outer-pipe table observations.

    A two-or-more-line outer-pipe block is treated as a table candidate.  The
    result records delimiter validity, row widths, and unescaped Wiki alias
    pipes.  It does not choose a maximum cell length.
    """
    lines = kblib.strip_code(text or "").splitlines()
    tables = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            index += 1
            continue
        start = index
        raw_rows = []
        rows = []
        while index < len(lines):
            stripped = lines[index].strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                break
            raw_rows.append(lines[index])
            rows.append(split_pipe_row(lines[index]))
            index += 1
        if len(rows) < 2:
            continue
        width = len(rows[0])
        tables.append({
            "line": start + 1,
            "delimiter_valid": table_separator(rows[1]),
            "expected_columns": width,
            "row_columns": tuple(len(row) for row in rows),
            "unescaped_alias_lines": tuple(
                start + offset + 1
                for offset, raw in enumerate(raw_rows)
                if _UNESCAPED_TABLE_ALIAS_RE.search(raw)
            ),
        })
    return tuple(tables)


def has_mermaid_fence(text):
    blocks, unclosed = fence_scan(text)
    return any(block["language"] == "mermaid" for block in blocks) or bool(
        unclosed and unclosed["language"] == "mermaid")


def has_markdown_table(text):
    return bool(table_scan(text))


__all__ = [
    "fence_scan", "has_markdown_table", "has_mermaid_fence",
    "split_pipe_row", "table_scan", "table_separator",
]
