"""Pure Coverage Delta validation and after-image planning.

This module is the public machine owner for the deterministic part of applying
one worker-produced Coverage Delta: Delta policy validation, line-preserving
page-field projection, and ``open_gaps_added`` / ``open_gaps_closed``
reconciliation.  Writers and lifecycle admission checks consume the same API,
so neither has to reach into another command's private implementation to judge
the prospective Coverage after-image.
"""

import copy
import re

import Tools.execution.planning.coverage_contract as coverage_contract
import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import valid_timestamp as _valid_timestamp


DELTA_PAGE_CONTROL_FIELDS = \
    coverage_contract.COVERAGE_DELTA_PAGE_CONTROL_FIELDS

# Known non-control scalar fields in the generic Coverage contract.  Profile
# extension fields remain legal and visible through warnings.
KNOWN_PAGE_SCALAR_FIELDS = frozenset((
    "authoring_status", "lifecycle", "volatility", "review_by",
))


def delta_policy_errors(delta):
    """Return operation-wide policy errors for one Coverage Delta mapping."""
    errors = []
    pages = delta.get("pages")
    if not isinstance(pages, list):
        return ["delta pages must be an explicit list"]
    seen_paths = set()
    for index, page in enumerate(pages):
        label = "pages[%d]" % index
        if not isinstance(page, dict):
            errors.append("%s must be a mapping" % label)
            continue
        forbidden = sorted(DELTA_PAGE_CONTROL_FIELDS.intersection(page))
        if forbidden:
            errors.append(
                "%s contains worker-forbidden Coverage control field(s): %s" %
                (label, ", ".join(forbidden))
            )
        path = page.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append("%s path must be a non-empty string" % label)
        elif path in seen_paths:
            errors.append("delta repeats page path %s" % path)
        else:
            seen_paths.add(path)
        if page.get("authoring_status") == "reviewed":
            errors.append(
                "%s cannot promote authoring_status to reviewed; the "
                "merge-ready -> closed Queue transaction owns review "
                "completion and must consume one current per-page review "
                "Receipt" % label
            )
        receipts = page.get("gate_receipts")
        if receipts is not None and (
                not isinstance(receipts, list) or
                not all(isinstance(value, str) and value.strip()
                        for value in receipts)):
            errors.append("%s gate_receipts must be a list of non-empty ids" %
                          label)
    generated_at = delta.get("generated_at")
    if not _valid_timestamp(generated_at):
        errors.append(
            "delta generated_at must be a timezone-aware RFC 3339 timestamp")
    additions = delta.get("open_gaps_added")
    closures = delta.get("open_gaps_closed")
    if not isinstance(additions, list):
        errors.append("open_gaps_added must be an explicit list")
        additions = []
    if not isinstance(closures, list):
        errors.append("open_gaps_closed must be an explicit list")
        closures = []
    for index, gap in enumerate(additions):
        label = "open_gaps_added[%d]" % index
        if not isinstance(gap, dict):
            errors.append("%s must be a mapping" % label)
            continue
        if not isinstance(gap.get("page"), str) or not gap["page"].strip():
            errors.append("%s page must be a non-empty string" % label)
        if not isinstance(gap.get("type"), str) or not gap["type"].strip():
            errors.append("%s type must be a non-empty string" % label)
        if "id" in gap and (not isinstance(gap["id"], str) or
                            not gap["id"].strip()):
            errors.append("%s id must be a non-empty string when present" %
                          label)
    for index, selector in enumerate(closures):
        label = "open_gaps_closed[%d]" % index
        if isinstance(selector, str):
            if not selector.strip():
                errors.append("%s id must be non-empty" % label)
        elif isinstance(selector, dict):
            has_id = isinstance(selector.get("id"), str) and bool(
                selector["id"].strip())
            has_pair = (isinstance(selector.get("page"), str) and
                        bool(selector["page"].strip()) and
                        isinstance(selector.get("type"), str) and
                        bool(selector["type"].strip()))
            if not has_id and not has_pair:
                errors.append("%s must identify id or page+type" % label)
        else:
            errors.append("%s must be a gap id or mapping" % label)
    return errors


def _find_page_block(lines, path):
    pattern = re.compile(r'^(\s*)-\s+path:\s*(.*?)\s*$')
    for index, line in enumerate(lines):
        clean = kblib.strip_yaml_comment(line.rstrip("\r\n"))
        match = pattern.match(clean)
        if not match or str(kblib.parse_scalar(match.group(2))) != path:
            continue
        indent = len(match.group(1))
        end = index + 1
        while end < len(lines):
            candidate = lines[end]
            if re.match(r'^\s{%d}-\s' % indent, candidate):
                break
            if candidate.strip():
                candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                if candidate_indent <= indent:
                    break
            end += 1
        return index, end
    return None, None


def _block_get(lines, start, end, key):
    pattern = re.compile(r'^(\s+)' + re.escape(key) + r':\s*(.*)$')
    for index in range(start + 1, end):
        match = pattern.match(lines[index])
        if match:
            raw = kblib.strip_yaml_comment(match.group(2)).strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
                raw = raw[1:-1]
            return index, match.group(1), raw
    return None, None, None


def _receipt_ids(lines, start, end):
    line_index, indent, raw = _block_get(
        lines, start, end, "gate_receipts")
    if line_index is None:
        return None, None, [], None
    if raw:
        values = [item.strip().strip("\"'")
                  for item in raw.strip("[]").split(",") if item.strip()]
        return line_index, indent, values, line_index
    values, last = [], line_index
    item_pattern = re.compile(r'^(\s+)-\s+(.*?)\s*$')
    for index in range(line_index + 1, end):
        match = item_pattern.match(lines[index])
        if not match or len(match.group(1)) <= len(indent):
            break
        raw_item = kblib.strip_yaml_comment(match.group(2)).strip()
        values.append(raw_item.strip("\"'"))
        last = index
    return line_index, indent, values, last


def plan_page_updates(coverage_text, delta):
    """Plan line-preserving Delta page edits without writing any state.

    Return ``(page_edited_text, planned, rejected, unknown_keys)``.  Open-gap
    reconciliation is deliberately a separate public step so callers can
    report page-manifest rejections with their existing operation semantics.
    """
    lines = coverage_text.splitlines(keepends=True)
    batch = str(delta.get("batch", "")).strip()
    planned, rejected, unknown_keys = [], [], []
    for page in delta.get("pages") or []:
        path = page["path"]
        start, end = _find_page_block(lines, path)
        if start is None:
            rejected.append((path, "not-found-in-ledger"))
            continue
        _, _, next_batch = _block_get(lines, start, end, "next_batch")
        _, _, historical_batch = _block_get(lines, start, end, "batch")
        if batch and next_batch != batch and historical_batch != batch:
            rejected.append((
                path,
                "manifest-mismatch(next_batch=%s,batch=%s)" %
                (next_batch, historical_batch),
            ))
            continue
        edits = []
        for key, value in page.items():
            if key == "path":
                continue
            if key == "gate_receipts":
                line_index, indent, current, last = _receipt_ids(
                    lines, start, end)
                incoming = [str(item) for item in (value or [])]
                merged = current + [item for item in incoming
                                    if item not in current]
                if line_index is not None:
                    block = [f"{indent}gate_receipts:\n"] + [
                        f'{indent}  - "{item}"\n' for item in merged
                    ]
                    edits.append(("range", line_index, last + 1, block))
                else:
                    block = ["    gate_receipts:\n"] + [
                        f'      - "{item}"\n' for item in merged
                    ]
                    edits.append(("range", end, end, block))
                continue
            if key not in KNOWN_PAGE_SCALAR_FIELDS:
                unknown_keys.append((path, key))
            scalar = "" if value is None else str(value)
            line_index, indent, _ = _block_get(lines, start, end, key)
            if line_index is not None:
                rendered = (f"{indent}{key}: {scalar}\n" if scalar else
                            f"{indent}{key}:\n")
                edits.append((line_index, rendered))
            else:
                edits.append((end, f"    {key}: {scalar}\n", "insert"))
        planned.append((path, edits))

    flat_edits = [edit for _, edits in planned for edit in edits]

    def edit_position(edit):
        return edit[1] if edit[0] == "range" else edit[0]

    new_lines = list(lines)
    for edit in sorted(flat_edits, key=lambda item: -edit_position(item)):
        if edit[0] == "range":
            _, begin, finish, block = edit
            new_lines[begin:finish] = block
        elif len(edit) == 3 and edit[2] == "insert":
            new_lines.insert(edit[0], edit[1])
        else:
            new_lines[edit[0]] = edit[1]
    return "".join(new_lines), planned, rejected, unknown_keys


def gap_key(value):
    """Return the stable identity used by the current open-gap protocol."""
    if isinstance(value, dict) and isinstance(value.get("id"), str) and \
            value["id"].strip():
        return ("id", value["id"])
    if isinstance(value, dict):
        return ("page-type", value.get("page"), value.get("type"))
    if isinstance(value, str):
        return ("id", value)
    return None


def gap_identity_text(value):
    key = gap_key(value)
    if key is None:
        return "<invalid>"
    if key[0] == "id":
        return str(key[1])
    return "%s#%s" % (key[1], key[2])


def _indexed_gaps(gaps, label):
    if not isinstance(gaps, list):
        raise ValueError("%s must be an explicit list" % label)
    indexed = {}
    for index, gap in enumerate(gaps):
        key = gap_key(gap)
        if key is None or (key[0] == "page-type" and
                           (not key[1] or not key[2])):
            raise ValueError("%s[%d] has no stable id or page+type" %
                             (label, index))
        if key in indexed:
            raise ValueError("%s repeats gap identity %r" % (label, key))
        indexed[key] = copy.deepcopy(gap)
    return indexed


def project_open_gaps(coverage, delta):
    """Return a complete Coverage object after applying Delta gap sections."""
    if not isinstance(coverage, dict):
        raise ValueError("Coverage Ledger top level must be a mapping")
    if not isinstance(delta, dict):
        raise ValueError("Coverage Delta top level must be a mapping")
    result = copy.deepcopy(coverage)
    indexed = _indexed_gaps(result.get("open_gaps"), "Coverage open_gaps")
    additions = delta.get("open_gaps_added")
    closures = delta.get("open_gaps_closed")
    if not isinstance(additions, list):
        raise ValueError("open_gaps_added must be an explicit list")
    if not isinstance(closures, list):
        raise ValueError("open_gaps_closed must be an explicit list")

    close_keys = [gap_key(selector) for selector in closures]
    if None in close_keys:
        raise ValueError("open_gaps_closed contains an invalid selector")
    if len(close_keys) != len(set(close_keys)):
        raise ValueError("open_gaps_closed repeats a gap identity")
    add_index = _indexed_gaps(additions, "open_gaps_added")
    overlap = set(close_keys).intersection(add_index)
    if overlap:
        raise ValueError("one delta cannot close and add the same gap: %r" %
                         sorted(overlap))
    for key in close_keys:
        if key not in indexed:
            raise ValueError("open_gaps_closed references absent gap %r" %
                             (key,))
        indexed.pop(key)

    page_paths = {
        page.get("path") for page in result.get("pages", [])
        if isinstance(page, dict)
    }
    for key, gap in add_index.items():
        if key in indexed:
            raise ValueError("open_gaps_added already exists: %r" % (key,))
        if gap.get("page") not in page_paths:
            raise ValueError("open gap page is absent from Coverage: %s" %
                             gap.get("page"))
        indexed[key] = gap
    result["open_gaps"] = list(indexed.values())
    if delta.get("generated_at") is not None:
        result["updated_at"] = delta["generated_at"]
    return result


def project_coverage_text(page_edited_text, delta):
    """Project gaps on page-edited Coverage bytes and return canonical bytes."""
    coverage = kblib.parse_yaml_subset(page_edited_text)
    return kblib.canonical_yaml(project_open_gaps(coverage, delta))
