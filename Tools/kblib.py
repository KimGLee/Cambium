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
import uuid

LIB_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Restricted YAML subset parser
# ---------------------------------------------------------------------------


class YamlSubsetError(ValueError):
    """Raised when the input goes beyond the restricted YAML subset grammar."""


def strip_yaml_comment(line):
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
        line = strip_yaml_comment(raw)
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
    """Walk all .md files under the vault (sorted by relative path); scope is an optional subpath.

    scope may also point at a single .md file (note-close self-check, K00/05);
    in that case exactly that file is returned. A scope that exists as neither
    a directory nor an .md file yields an empty list -- callers implementing a
    gate MUST treat an empty scan set as a failure, not a pass.
    """
    base = os.path.join(vault_root, scope) if scope else vault_root
    base = os.path.normpath(base)
    if os.path.isfile(base):
        if base.lower().endswith(".md"):
            return [(base, os.path.relpath(base, vault_root))]
        return []
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


PROFILE_ID_LINE_RE = re.compile(
    r"^\s*-\s+`profile_id`\s*:\s*`([^`]*)`\s*$"
)
PROFILE_ID_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

ACTIVE_STANDARDS_STATE_LABELS = {
    "Standards version": "standards_version",
    "Status": "standards_status",
    "Effective date": "standards_effective_date",
    "Selected profile manifest": "selected_profile_manifest",
}

PROFILE_SLOT_BINDING_RE = re.compile(
    r"^\s*-\s+`([^`]+)`\s*:\s*(.+?)\s*$"
)
PROFILE_WIKI_BINDING_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
PROFILE_MARKDOWN_BINDING_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
PROFILE_CODE_BINDING_RE = re.compile(r"`([^`]+)`")
PROFILE_INLINE_BINDING_RE = re.compile(r"\binline\b", re.IGNORECASE)


def active_standards_state(text):
    """Return ``(state, errors)`` from K00/03's Standards Control table.

    This is deliberately a syntax-only parser.  Consumers decide whether a
    placeholder, status, or profile path is acceptable for their own mode;
    every consumer nevertheless reads the same four canonical fields.
    """
    state = {}
    errors = []
    inside = False
    section_count = 0
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and fence_match:
            fence = fence_match.group(1)[0] * 3
            continue
        if fence is not None:
            if fence_match and stripped.startswith(fence):
                fence = None
            continue
        heading = re.match(r"^(#{1,2})\s+(.*?)\s*#*\s*$", line)
        if heading:
            is_control = (
                len(heading.group(1)) == 2
                and heading.group(2).strip() == "Standards Control"
            )
            if is_control:
                section_count += 1
            inside = is_control and section_count == 1
            continue
        if not inside:
            continue
        row = re.match(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$", line)
        if not row:
            continue
        label = row.group(1).strip()
        if label not in ACTIVE_STANDARDS_STATE_LABELS:
            continue
        key = ACTIVE_STANDARDS_STATE_LABELS[label]
        value = row.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] == "`":
            value = value[1:-1].strip()
        if key in state:
            errors.append("Standards Control repeats %s" % label)
        else:
            state[key] = value

    if section_count != 1:
        errors.append(
            "document must contain exactly one non-fenced Standards Control "
            "H2; found %d" % section_count
        )
    for label, key in ACTIVE_STANDARDS_STATE_LABELS.items():
        if key not in state:
            errors.append("Standards Control has no %s row" % label)
    return state, errors


def profile_slot_bindings(manifest_text, include_duplicates=False):
    """Return the Implemented Slots mapping and optionally duplicate names."""
    bindings = {}
    duplicates = []
    inside = False
    fence = None
    for line in manifest_text.splitlines():
        stripped = line.lstrip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and fence_match:
            fence = fence_match.group(1)[0] * 3
            continue
        if fence is not None:
            if fence_match and stripped.startswith(fence):
                fence = None
            continue
        heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if heading and len(heading.group(1)) <= 2:
            inside = (
                len(heading.group(1)) == 2
                and heading.group(2).strip() == "Implemented Slots"
            )
            continue
        if inside:
            match = PROFILE_SLOT_BINDING_RE.match(line)
            if match:
                name = match.group(1).strip()
                if name in bindings and name not in duplicates:
                    duplicates.append(name)
                bindings[name] = match.group(2).strip()
    if include_duplicates:
        return bindings, duplicates
    return bindings


def _profile_binding_looks_like_path(value):
    return "/" in value or value.lower().endswith((".md", ".yaml", ".yml"))


def _profile_binding_candidate_paths(target, root, profile_dir):
    target = target.strip().lstrip("./")
    if not target:
        return []
    variants = [target]
    if not target.lower().endswith((".md", ".yaml", ".yml")):
        variants.append(target + ".md")
    paths = []
    for variant in variants:
        paths.append(os.path.join(profile_dir, variant))
        paths.append(os.path.join(root, variant))
    return paths


def resolve_profile_binding(binding, root, profile_dir):
    """Resolve one manifest slot binding with check_profile semantics.

    Returns ``(kind, detail)`` where kind is path, outside-profile,
    unresolved, inline, or unrecognized. Path resolution accepts either a
    profile-relative or repository-relative spelling, but the resolved file
    must stay inside the selected profile directory so one manifest cannot
    silently compose another profile's slots.
    """
    target = None
    match = PROFILE_WIKI_BINDING_RE.search(binding)
    if match:
        target = re.split(r"\\\||\|", match.group(1), maxsplit=1)[0].strip()
    if target is None:
        match = PROFILE_MARKDOWN_BINDING_RE.search(binding)
        if match:
            target = match.group(1).strip()
    if target is None and PROFILE_INLINE_BINDING_RE.search(binding):
        return "inline", None
    if target is None:
        for code in PROFILE_CODE_BINDING_RE.findall(binding):
            if _profile_binding_looks_like_path(code):
                target = code.strip()
                break
    if target is None:
        return "unrecognized", None
    for path in _profile_binding_candidate_paths(target, root, profile_dir):
        if os.path.isfile(path):
            profile_real = os.path.realpath(profile_dir)
            path_real = os.path.realpath(path)
            try:
                inside = os.path.commonpath((profile_real, path_real)) == profile_real
            except ValueError:
                inside = False
            if inside:
                return "path", path
            return "outside-profile", path
    return "unresolved", target


def profile_identity(manifest_text, directory_name, reserved_ids=()):
    """Return ``(profile_id, errors)`` for one profile manifest.

    ``errors`` contains ``(check_id, details)`` pairs.  The manifest is the
    sole profile-id source: exactly one ``profile_id`` bullet must occur under
    the ``Profile Identity`` H2, it must be a lowercase path slug, must not be
    reserved, and must equal the profile directory name.  Fenced examples are
    ignored so documentation cannot accidentally become identity data.
    """
    profile_ids = []
    inside_identity = False
    fence = None
    for line in manifest_text.splitlines():
        stripped = line.lstrip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and fence_match:
            fence = fence_match.group(1)[0] * 3
            continue
        if fence is not None:
            if fence_match and stripped.startswith(fence):
                fence = None
            continue

        heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if heading and len(heading.group(1)) <= 2:
            inside_identity = (
                len(heading.group(1)) == 2
                and heading.group(2).strip() == "Profile Identity"
            )
            continue
        if inside_identity:
            match = PROFILE_ID_LINE_RE.match(line)
            if match:
                profile_ids.append(match.group(1).strip())

    profile_id = profile_ids[0] if profile_ids else None
    errors = []
    if not profile_ids:
        errors.append((
            "profile-id-missing",
            "no `profile_id`: `<value>` bullet found under Profile Identity; "
            "the manifest must name the profile it composes with the kernel",
        ))
    elif len(profile_ids) > 1:
        errors.append((
            "profile-id-duplicate",
            "Profile Identity contains %d profile_id entries; exactly one "
            "manifest identity is allowed" % len(profile_ids),
        ))
    elif profile_id in {str(value) for value in reserved_ids}:
        errors.append((
            "profile-id-placeholder",
            "profile_id is still the reserved placeholder %r; replace it with "
            "this profile's own id before the profile may be loaded" % profile_id,
        ))
    elif not PROFILE_ID_VALUE_RE.fullmatch(profile_id):
        errors.append((
            "profile-id-invalid",
            "profile_id %r is not a lowercase path slug matching "
            "[a-z0-9][a-z0-9_-]*" % profile_id,
        ))
    elif profile_id != directory_name:
        errors.append((
            "profile-id-directory-mismatch",
            "profile_id %r must match the profile directory name %r; the "
            "manifest is the single identity source" % (profile_id, directory_name),
        ))
    return profile_id, errors


# ---------------------------------------------------------------------------
# Receipt helpers (field definitions in Tools/schemas/receipt.template.jsonl)
# ---------------------------------------------------------------------------


# One random token per process makes receipt IDs collision-resistant across
# concurrent or same-second tool invocations; seq still preserves order within
# one invocation.
_RECEIPT_RUN_TOKEN = uuid.uuid4().hex


def make_receipt(tool, tool_version, check, target, result, details, seq):
    """Build one receipt dict; result must be pass / fail / candidate."""
    assert result in ("pass", "fail", "candidate"), result
    now = time.time()
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    return {
        "receipt_id": "audit-%s-%s-%s-%04d" % (
            tool, stamp, _RECEIPT_RUN_TOKEN, seq),
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
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
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
