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
   Not supported: duplicate mapping keys, anchors/aliases, multi-line strings
   (| >), flow maps `{}`, tags, multiple documents.
2. Markdown helpers: frontmatter extraction, code-block stripping (preserving
   line numbers), heading extraction.
3. Receipt helpers: construction and append-writing of machine-readable JSONL
   receipts (field definitions in Tools/schemas/receipt.template.jsonl), plus
   the shared exit-code convention:
   0 = all pass; 1 = at least one fail; 2 = no fail but candidates.
"""

from contextlib import contextmanager
import errno
import hashlib
import json
import os
import re
import stat
import tempfile
import time
import uuid

LIB_VERSION = "1.5.0"

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
    document_started = False
    document_ended = False
    has_content = False
    for raw in text.splitlines():
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlSubsetError("tabs are not allowed in indentation: %r" % raw)
        line = strip_yaml_comment(raw)
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "---":
            if indent:
                raise YamlSubsetError("YAML document markers must start at column 0")
            if document_started or has_content or document_ended:
                raise YamlSubsetError("multiple YAML documents are not supported")
            document_started = True
            continue
        if stripped == "...":
            if indent:
                raise YamlSubsetError("YAML document markers must start at column 0")
            if document_ended:
                raise YamlSubsetError("multiple YAML document endings are not supported")
            document_ended = True
            continue
        if document_ended:
            raise YamlSubsetError("content after a YAML document ending is not supported")
        has_content = True
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
        if key in result:
            raise YamlSubsetError("duplicate mapping key: %r" % key)
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


PROFILE_OVERRIDES_SECTION = "Execution Default Overrides"
PROFILE_TABLE_SEPARATOR_RE = re.compile(r":?-{2,}:?")


class ProfileOverrideRowError(ValueError):
    """An override row whose shape no resolver may silently interpret."""


def profile_execution_default_overrides(manifest_text):
    """Return the manifest's ``Execution Default Overrides`` rows as a mapping.

    One reader for the whole sparse table, so every owner tool that resolves
    one of its items sees the same rows.  ``check_profile.py`` owns whether a
    row is admissible (closed item registry, exactly two cells, no duplicate,
    no redundant ``use-kernel-default``); this reader only reports what the
    manifest declares.  Values are returned as the manifest's raw strings with
    surrounding backticks removed, because each item's type, unit, and range
    belong to that item's kernel owner, not here.  Fenced examples are ignored
    and a repeated item keeps its last row, matching the shape validator.

    A data row that is not exactly two cells, or whose item cell is empty,
    raises :class:`ProfileOverrideRowError`.  Dropping such a row would leave a
    resolver reporting the kernel default for an item the manifest does declare
    -- the one outcome a reader must never produce, because a declared value
    that nobody saw is indistinguishable from no declaration at all.  Reporting
    the row is ``check_profile.py``'s ``override-row-shape``; refusing to
    resolve from it is this reader's, and the two are not substitutes.
    """
    rows = []
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
        if heading:
            if inside and len(heading.group(1)) <= 2:
                break
            inside = (len(heading.group(1)) == 2 and
                      heading.group(2).strip() == PROFILE_OVERRIDES_SECTION)
            continue
        if not inside:
            continue
        value = line.strip()
        if not value.startswith("|") or not value.endswith("|"):
            continue
        cells = [cell.replace("\\|", "|").strip()
                 for cell in re.split(r"(?<!\\)\|", value[1:-1])]
        if all(PROFILE_TABLE_SEPARATOR_RE.fullmatch(cell.replace(" ", ""))
               for cell in cells if cell):
            continue
        rows.append(cells)
    overrides = {}
    # The first non-separator row is the header, exactly as the shape
    # validator in check_profile.py treats it.
    for number, cells in enumerate(rows[1:], start=2):
        if len(cells) != 2:
            raise ProfileOverrideRowError(
                "%s data row %d has %d cell(s); every override row carries "
                "exactly two (item ID, profile value), and a row of another "
                "shape declares a value no resolver can read"
                % (PROFILE_OVERRIDES_SECTION, number, len(cells)))
        item = cells[0].strip("` ")
        if not item:
            raise ProfileOverrideRowError(
                "%s data row %d names no override item; the value %r belongs "
                "to no item ID"
                % (PROFILE_OVERRIDES_SECTION, number, cells[1].strip("` ")))
        overrides[item] = cells[1].strip("` ")
    return overrides


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

# A Gate receipt is consumed against the canonical Required Queue identity:
# check_queue's boundary-gate consumer requires exactly these three fields to
# equal the live Queue values.  The canonical Queue is their sole owner, so a
# producer binds them by reading that one file -- never by deriving them from
# its own descriptive fields.
RECEIPT_IDENTITY_FIELDS = ("task_id", "standards_version",
                           "selected_profile_manifest")
RUNTIME_STATE_PREFIX = ".cambium/state"
RUNTIME_QUEUE_PATH = ".cambium/state/required_queue.yaml"

# Receipts are produced one per finding, so a large scan may build thousands of
# them from one unchanged Queue file.  The stat signature keys the cache, so an
# in-process rewrite of the Queue is observed rather than served from cache.
_RUNTIME_IDENTITY_CACHE = {}
_RUNTIME_IDENTITY_CACHE_LIMIT = 64


def runtime_receipt_identity(root):
    """Return the Required Queue identity fields a receipt under ``root`` binds.

    The values are read from the one canonical Queue file, exactly where
    ``check_queue`` and ``check_proof`` read them, so a producer cannot drift
    from its consumer.

    A field this function cannot read is **omitted**, never written as
    ``null``.  Absence is the fail-closed spelling:

    * the boundary-gate consumer compares ``receipt.get(field)`` against the
      live Queue value, where an omitted field already behaves as ``null``, so
      omission introduces no new failure mode;
    * consumers that demand an explicit binding spell it
      ``field not in receipt or receipt.get(field) != expected``; an explicit
      ``null`` satisfies the presence half of that test and could admit a
      receipt those consumers reject today -- a loosening;
    * receipts are append-only evidence.  ``task_id: null`` asserts an identity
      the producer never observed, which is the inference
      ``check_queue.receipt_matches_gate_id`` exists to forbid.

    Returning ``{}`` therefore covers every case with no runtime to read: the
    Standards repository itself, an adopter who has not run ``init_state``, and
    a ``.cambium`` tree whose Queue is unreadable, unparseable, or reached
    through a symlink.
    """
    if root is None:
        return {}
    try:
        queue_path = managed_repository_path(
            root, RUNTIME_QUEUE_PATH, RUNTIME_STATE_PREFIX,
            suffixes=(".yaml",), must_exist=True)
        descriptor = os.stat(queue_path)
    except (OSError, TypeError, ValueError):
        return {}
    if not stat.S_ISREG(descriptor.st_mode):
        return {}
    key = (queue_path, descriptor.st_dev, descriptor.st_ino,
           descriptor.st_mtime_ns, descriptor.st_size)
    identity = _RUNTIME_IDENTITY_CACHE.get(key)
    if identity is None:
        try:
            queue = load_yaml_file(queue_path)
        except (OSError, UnicodeError, ValueError):
            queue = {}
        identity = {field: queue[field] for field in RECEIPT_IDENTITY_FIELDS
                    if field in queue}
        if len(_RUNTIME_IDENTITY_CACHE) >= _RUNTIME_IDENTITY_CACHE_LIMIT:
            _RUNTIME_IDENTITY_CACHE.clear()
        _RUNTIME_IDENTITY_CACHE[key] = identity
    return dict(identity)


def make_receipt(tool, tool_version, check, target, result, details, seq,
                 *, root=None, identity=None):
    """Build one receipt dict; result must be pass / fail / candidate.

    ``root`` binds the Required Queue identity fields read from that
    repository's runtime state; ``identity`` supplies them directly and wins,
    for a producer whose receipt describes a state transition and must bind the
    post-transaction identity rather than the bytes currently on disk.  Only
    :data:`RECEIPT_IDENTITY_FIELDS` are taken from either source, and a field
    absent there stays absent from the receipt.
    """
    assert result in ("pass", "fail", "candidate"), result
    now = time.time()
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    receipt = {
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
    if identity is None:
        identity = runtime_receipt_identity(root)
    for field in RECEIPT_IDENTITY_FIELDS:
        if field in identity:
            receipt[field] = identity[field]
    return receipt


def validate_receipt_output_path(path):
    """Return an absolute receipt path without crossing runtime authority.

    Generic checks may write receipts outside a Cambium runtime.  Once either
    the lexical or resolved path enters a ``.cambium`` namespace, however,
    the only legal destination is ``.cambium/receipts/**/*.jsonl``.  Keeping
    this guard in the shared append primitive prevents any caller from
    appending JSON to canonical state, delta, report, or lock files.
    """
    if not isinstance(path, (str, bytes, os.PathLike)):
        raise ValueError("receipt target must be a filesystem path")
    absolute = os.path.abspath(os.fspath(path))
    resolved = os.path.realpath(absolute)
    entered_runtime = False
    for spelling in (absolute, resolved):
        parts = os.path.normpath(spelling).split(os.sep)
        for index, component in enumerate(parts):
            if component != ".cambium":
                continue
            entered_runtime = True
            if index + 1 >= len(parts) or parts[index + 1] != "receipts":
                raise ValueError(
                    "receipt target inside .cambium must be under "
                    ".cambium/receipts/"
                )
    if entered_runtime and not absolute.endswith(".jsonl"):
        raise ValueError("managed Cambium receipts must use a .jsonl file")
    return absolute


def _receipt_lines(receipts):
    """Return the exact newline-terminated records used by receipt writers."""
    lines = [
        (json.dumps(receipt, ensure_ascii=False) + "\n").encode("utf-8")
        for receipt in receipts
    ]
    if len(lines) != len(set(lines)):
        raise ValueError("one append operation must not repeat a receipt record")
    return lines


def _read_receipt_bytes(path):
    """Read one receipt file through no-follow descriptors.

    A missing final component is represented by ``(False, b\"\")``.  The same
    regular-file and single-link rules as the append path apply so an
    after-error inspection cannot be redirected to authoritative state.
    """
    absolute = validate_receipt_output_path(path)
    parent = os.path.dirname(absolute)
    basename = os.path.basename(absolute)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_only = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_only is None:
        raise OSError(errno.ENOTSUP,
                      "safe receipt inspection requires O_NOFOLLOW and "
                      "O_DIRECTORY", absolute)
    directory_flags = os.O_RDONLY | directory_only | nofollow
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    parent_fd = os.open(parent, directory_flags)
    try:
        try:
            fd = os.open(
                basename,
                os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return False, b""
        try:
            descriptor = os.fstat(fd)
            if not stat.S_ISREG(descriptor.st_mode):
                raise ValueError("receipt target must be a regular file")
            if descriptor.st_nlink != 1:
                raise ValueError(
                    "receipt target must have exactly one hard link; found %d" %
                    descriptor.st_nlink
                )
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return True, b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def receipt_append_observation(path, receipts):
    """Observe exact own-record counts without treating other appends as ours.

    The returned value is intentionally small and JSON-serializable.  A caller
    takes one observation before publication and another after an exception;
    :func:`receipt_append_outcome` then distinguishes a proven absence from a
    durable exact append.  Invalid or partial JSONL is retained as an
    ``uncertain`` condition rather than repaired destructively.
    """
    lines = _receipt_lines(receipts)
    exists, content = _read_receipt_bytes(path)
    counts = [content.splitlines(keepends=True).count(line) for line in lines]
    structurally_valid = True
    if content and not content.endswith(b"\n"):
        structurally_valid = False
    if structurally_valid:
        try:
            for line in content.splitlines():
                value = json.loads(line.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("receipt record is not an object")
        except (UnicodeError, ValueError, json.JSONDecodeError):
            structurally_valid = False
    return {
        "path": validate_receipt_output_path(path),
        "exists": exists,
        "counts": counts,
        "structurally_valid": structurally_valid,
    }


def receipt_append_outcome(before, after):
    """Classify an attempted append as ``present``, ``absent`` or uncertain."""
    if (not isinstance(before, dict) or not isinstance(after, dict) or
            before.get("path") != after.get("path") or
            not isinstance(before.get("counts"), list) or
            not isinstance(after.get("counts"), list) or
            len(before["counts"]) != len(after["counts"])):
        return "uncertain"
    deltas = [new - old for old, new in
              zip(before["counts"], after["counts"])]
    if after.get("structurally_valid") is not True:
        return "uncertain"
    if deltas and all(delta == 1 for delta in deltas):
        return "present"
    if all(delta == 0 for delta in deltas):
        return "absent"
    return "uncertain"


def receipt_outcome_from(path, receipts, before):
    """Return the current exact-record outcome relative to ``before``.

    Inspection errors are deliberately converted to ``uncertain``.  This is
    the safe question for an exception handler deciding whether a canonical
    writer lock may be cleared; it must never turn unreadable or partial
    receipt evidence into a proven absence.
    """
    try:
        after = receipt_append_observation(path, receipts)
        return receipt_append_outcome(before, after)
    except Exception:
        return "uncertain"


def write_receipts_observed(path, receipts, exclusive=False, before=None):
    """Append receipts and report exact durable outcome plus any write error.

    Returns ``(outcome, error, before_observation)`` and does not raise an
    ordinary append/inspection exception.  A successful return is only one
    whose outcome is ``present``; a writer error after durable bytes therefore
    returns ``("present", error, before)`` while a partial/truncated record is
    ``uncertain``.  Canonical transaction callers use this distinction to
    decide whether rollback is fully closed or must retain its recovery lock.
    """
    try:
        baseline = before or receipt_append_observation(path, receipts)
    except Exception as exc:
        return "uncertain", exc, before
    write_error = None
    try:
        write_receipts(path, receipts, exclusive=exclusive)
    except Exception as exc:
        write_error = exc
    outcome = receipt_outcome_from(path, receipts, baseline)
    if write_error is not None:
        return outcome, write_error, baseline
    if outcome != "present":
        return (outcome,
                OSError(errno.EIO,
                        "receipt append could not be proven durable: %s" %
                        outcome, os.fspath(path)),
                baseline)
    return outcome, None, baseline


def write_receipts(path, receipts, exclusive=False):
    """Safely append receipts to one regular, singly-linked JSONL file.

    Queue tools validate the managed namespace before calling this helper, but
    the file can still be swapped between validation and append.  Opening with
    ``O_NOFOLLOW`` closes the final-component symlink race; the descriptor
    checks reject directories, devices, and hard links to authoritative state.
    One ``O_APPEND`` syscall per JSONL record keeps concurrent writers from
    sharing a file offset.  ``exclusive=True`` additionally requires this call
    to create the final name, which is suitable for a one-receipt canonical
    artifact.  Callers needing a state transaction must additionally hold
    :func:`runtime_write_lock` for the full transaction.
    """
    if not path:
        return
    lines = _receipt_lines(receipts)
    if not lines:
        return
    absolute = validate_receipt_output_path(path)
    parent = os.path.dirname(absolute)
    basename = os.path.basename(absolute)
    if not basename:
        raise ValueError("receipt target must name a file")
    os.makedirs(parent, exist_ok=True)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_only = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_only is None:
        raise OSError(errno.ENOTSUP,
                      "safe receipt append requires O_NOFOLLOW and O_DIRECTORY",
                      absolute)
    directory_flags = os.O_RDONLY | directory_only | nofollow
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    parent_fd = os.open(parent, directory_flags)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | nofollow
    if exclusive:
        flags |= os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        # APFS can transiently surface ENOENT when several O_CREAT|O_APPEND
        # opens race on the same previously absent name through a directory
        # descriptor.  Retrying that one result is safe: no namespace entry is
        # removed or replaced, and O_EXCL retains its winner semantics.
        for attempt in range(5):
            try:
                fd = os.open(basename, flags, 0o666, dir_fd=parent_fd)
                break
            except FileNotFoundError:
                if attempt == 4:
                    raise
                continue
    except Exception:
        os.close(parent_fd)
        raise
    try:
        descriptor = os.fstat(fd)
        if not stat.S_ISREG(descriptor.st_mode):
            raise ValueError("receipt target must be a regular file")
        if descriptor.st_nlink != 1:
            raise ValueError(
                "receipt target must have exactly one hard link; found %d" %
                descriptor.st_nlink
            )
        # Each JSONL record is one append syscall.  Retrying a short write
        # would allow a concurrent writer to land between fragments and make
        # both records ambiguous, so surface the partial append instead.  The
        # caller's writer lock and exact-record observation then preserve a
        # recovery boundary without deleting any concurrent record.
        for line in lines:
            written = os.write(fd, line)
            if written != len(line):
                raise OSError(errno.EIO, "receipt append was partial",
                              absolute)
        os.fsync(fd)
        # Persist a newly created receipt name as well as its contents.
        os.fsync(parent_fd)
    finally:
        os.close(fd)
        os.close(parent_fd)


def exit_code(receipts):
    """Shared exit codes: 1 = at least one fail; 2 = no fail but candidates; 0 = all pass."""
    results = {r["result"] for r in receipts}
    if "fail" in results:
        return 1
    if "candidate" in results:
        return 2
    return 0


# ---------------------------------------------------------------------------
# Canonical runtime-state helpers
# ---------------------------------------------------------------------------


def repository_path(root, relative_path, must_exist=False, reject_symlink=False):
    """Resolve one repository-relative path without permitting root escape.

    ``relative_path`` must be a canonical, non-empty relative spelling: no
    leading/trailing whitespace, absolute path, ``.``/``..`` segment, or NUL.
    Resolution follows symlinks only to prove the resulting path remains under
    ``root``.  Callers handling canonical state files may set
    ``reject_symlink`` to reject a symlink at the final path as well.
    """
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("path must be a non-empty string")
    if relative_path != relative_path.strip():
        raise ValueError("path must not have leading or trailing whitespace")
    if "\x00" in relative_path:
        raise ValueError("path must not contain NUL")
    if os.path.isabs(relative_path):
        raise ValueError("path must be repository-relative")
    parts = relative_path.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("path must not contain empty, '.' or '..' segments")

    root_real = os.path.realpath(os.path.abspath(root))
    candidate = os.path.join(root_real, *parts)
    resolved = os.path.realpath(candidate)
    try:
        inside = os.path.commonpath((root_real, resolved)) == root_real
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("path resolves outside the repository root")
    if reject_symlink and os.path.lexists(candidate) and os.path.islink(candidate):
        raise ValueError("canonical state path must not be a symlink")
    if must_exist and not os.path.exists(candidate):
        raise ValueError("path does not exist: %s" % relative_path)
    return candidate


def managed_repository_path(root, relative_path, managed_prefix,
                            suffixes=None, must_exist=False):
    """Resolve a file inside one fixed managed namespace without symlinks.

    This is the write-path boundary for ``.cambium``: a receipt argument may
    not name state, a report may not name a delta, and a symlinked component
    may not redirect an apparently safe spelling elsewhere inside the repo.
    """
    candidate = repository_path(root, relative_path, must_exist=must_exist,
                                reject_symlink=True)
    normalized = relative_path.replace("\\", "/")
    prefix = managed_prefix.strip("/")
    if not normalized.startswith(prefix + "/"):
        raise ValueError("path must be inside %s/" % prefix)
    if suffixes and not normalized.endswith(tuple(suffixes)):
        raise ValueError("path must end with %s" % " or ".join(suffixes))
    root_abs = os.path.realpath(os.path.abspath(root))
    current = root_abs
    for part in normalized.split("/"):
        current = os.path.join(current, part)
        if os.path.lexists(current) and os.path.islink(current):
            raise ValueError("managed path must not traverse symlink: %s" %
                             relative_path)
    if os.path.lexists(candidate):
        descriptor = os.lstat(candidate)
        if stat.S_ISREG(descriptor.st_mode) and descriptor.st_nlink != 1:
            raise ValueError(
                "managed file must have exactly one hard link: %s" %
                relative_path
            )
    return candidate


class RuntimeStateLockedError(RuntimeError):
    """Raised when another cooperating process owns the runtime-state lock."""


class RuntimeWriteLockLease(os.PathLike):
    """Path-like lock lease whose owner may attest successful reconciliation.

    A state writer that lets an exception escape must leave its lock behind so
    the next process can inspect the recorded transaction.  If the writer has
    *fully* restored every authoritative byte before re-raising, it may call
    :meth:`mark_reconciled`; only then is cleanup on error safe.
    """

    def __init__(self, path):
        self.path = path
        self.reconciled = False

    def __fspath__(self):
        return self.path

    def __str__(self):
        return self.path

    def mark_reconciled(self):
        self.reconciled = True


@contextmanager
def no_authoritative_write_guard(lease):
    """Clear a writer lock when a guarded preflight rejects before writing.

    Wrap only operations that run before the first possible mutation of
    canonical state, append-only receipts, managed deltas, or archives.  A
    normal Python exception in that region proves that no authoritative write
    was attempted, so retaining the lock would manufacture a false
    interrupted-write state.  Hard process exits still preserve the lock,
    because the context manager cannot attest what happened after the process
    disappeared.

    Once a writer crosses its first possible publication boundary it must
    leave this guard and use its transaction-specific rollback/evidence logic.
    """
    if not isinstance(lease, RuntimeWriteLockLease):
        raise TypeError("lease must be a RuntimeWriteLockLease")
    try:
        yield
    except BaseException:
        lease.mark_reconciled()
        raise


@contextmanager
def runtime_write_lock(root, lock_name="state-writer", timeout=0.0,
                       poll_interval=0.05, owner_metadata=None):
    """Hold one cooperating-writer lock under ``.cambium/tmp``.

    Directory creation is the atomic claim.  A process crash or any escaping
    error intentionally leaves a stale lock that fails closed; an operator may
    remove it only after proving that no writer remains and reconciling the
    recorded before/planned-after fingerprints.  A caller that fully restores
    all authoritative bytes may call ``lease.mark_reconciled()`` before
    re-raising.  This primitive does not make a multi-file update atomic by
    itself, but it removes concurrent cooperating writers from the
    compare/write/rollback window and preserves recovery intent.
    """
    if (not isinstance(lock_name, str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", lock_name)):
        raise ValueError("lock_name must be a simple path-safe identifier")
    if timeout is not None and timeout < 0:
        raise ValueError("timeout must be non-negative or None")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    if owner_metadata is not None and not isinstance(owner_metadata, dict):
        raise ValueError("owner_metadata must be a mapping or None")
    try:
        serialized_metadata = (json.loads(json.dumps(owner_metadata))
                               if owner_metadata else None)
    except (TypeError, ValueError) as exc:
        raise ValueError("owner_metadata must be JSON-serializable: %s" % exc)

    root_real = os.path.realpath(os.path.abspath(root))
    tmp_path = managed_repository_path(
        root_real, ".cambium/tmp", ".cambium", must_exist=True
    )
    if not os.path.isdir(tmp_path):
        raise ValueError(".cambium/tmp must be a directory")
    relative_lock = ".cambium/tmp/%s.lock" % lock_name
    lock_path = managed_repository_path(
        root_real, relative_lock, ".cambium/tmp", must_exist=False
    )
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        try:
            os.mkdir(lock_path, 0o700)
            parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            parent_fd = os.open(tmp_path, parent_flags)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            break
        except FileExistsError:
            if deadline is not None and time.monotonic() >= deadline:
                raise RuntimeStateLockedError(
                    "runtime state is locked by another writer: %s" %
                    relative_lock
                )
            time.sleep(poll_interval)
    owner_path = os.path.join(lock_path, "owner.json")
    owner = {
        "lock_name": lock_name,
        "pid": os.getpid(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if serialized_metadata:
        # Keep caller-supplied transaction intent in one nested object so it
        # cannot overwrite the lock identity.  The file is deliberately left
        # behind with the lock directory after a process crash: a later
        # ``check_queue --resume-status`` can then distinguish an ordinary
        # hold from an interrupted canonical-state write and compare the
        # recorded before/planned-after fingerprints with the live files.
        owner["operation"] = serialized_metadata
    with open(owner_path, "x", encoding="utf-8") as fh:
        json.dump(owner, fh, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    lock_fd = os.open(lock_path, directory_flags)
    try:
        os.fsync(lock_fd)
    finally:
        os.close(lock_fd)
    lease = RuntimeWriteLockLease(lock_path)
    completed = False
    try:
        yield lease
        completed = True
    finally:
        # An escaping exception may represent a partially published
        # multi-file transaction.  Preserve the owner metadata unless the
        # caller positively attests that rollback restored all authoritative
        # bytes.  A later ``check_queue --resume-status`` can then reconcile
        # the before/planned-after fingerprints instead of silently guessing.
        if completed or lease.reconciled:
            try:
                os.unlink(owner_path)
            except FileNotFoundError:
                pass
            try:
                os.rmdir(lock_path)
            except FileNotFoundError:
                pass
            else:
                parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                parent_fd = os.open(tmp_path, parent_flags)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)


def load_yaml_file(path):
    """Read and parse a UTF-8 restricted-subset YAML document."""
    with open(path, encoding="utf-8") as fh:
        value = parse_yaml_subset(fh.read())
    if not isinstance(value, dict):
        raise YamlSubsetError("top-level YAML value must be a mapping")
    return value


_YAML_RESERVED = frozenset(("true", "false", "yes", "no", "null", "~"))


def _yaml_scalar(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str):
        raise TypeError("unsupported YAML scalar type: %s" % type(value).__name__)
    # The restricted parser deliberately has no quoted-string escape grammar.
    # Reject control characters and quote using the opposite quote when the
    # value would otherwise be parsed as another scalar or a comment-bearing
    # token.  This keeps canonical output round-trippable under that parser.
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("YAML strings must not contain control characters")
    safe_bare = (
        value != "" and value == value.strip() and
        value.lower() not in _YAML_RESERVED and
        not re.fullmatch(r"-?\d+(?:\.\d+)?", value) and
        not value.startswith(("[", "- ")) and
        ": " not in value and " #" not in value and
        not value.startswith("#")
    )
    if safe_bare:
        return value
    if '"' not in value:
        return '"%s"' % value
    if "'" not in value:
        return "'%s'" % value
    raise ValueError("YAML strings containing both quote characters are unsupported")


def _render_yaml_node(value, indent):
    prefix = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, child in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[^:\s][^:]*", key):
                raise ValueError("unsupported YAML mapping key: %r" % (key,))
            if isinstance(child, dict):
                lines.append("%s%s:" % (prefix, key))
                lines.extend(_render_yaml_node(child, indent + 2))
            elif isinstance(child, list):
                if not child:
                    lines.append("%s%s: []" % (prefix, key))
                else:
                    lines.append("%s%s:" % (prefix, key))
                    lines.extend(_render_yaml_node(child, indent + 2))
            else:
                lines.append("%s%s: %s" % (prefix, key, _yaml_scalar(child)))
        return lines
    if isinstance(value, list):
        lines = []
        for child in value:
            if isinstance(child, dict):
                if not child:
                    raise ValueError("empty maps are outside the restricted YAML subset")
                first = True
                for key, grandchild in child.items():
                    if not isinstance(key, str) or not re.fullmatch(r"[^:\s][^:]*", key):
                        raise ValueError("unsupported YAML mapping key: %r" % (key,))
                    marker = "- " if first else "  "
                    line_prefix = prefix + marker
                    if isinstance(grandchild, (dict, list)):
                        if isinstance(grandchild, list) and not grandchild:
                            lines.append("%s%s: []" % (line_prefix, key))
                        else:
                            lines.append("%s%s:" % (line_prefix, key))
                            lines.extend(_render_yaml_node(grandchild, indent + 4))
                    else:
                        lines.append("%s%s: %s" %
                                     (line_prefix, key, _yaml_scalar(grandchild)))
                    first = False
            elif isinstance(child, list):
                raise ValueError("nested bare lists are outside the restricted YAML subset")
            else:
                lines.append("%s- %s" % (prefix, _yaml_scalar(child)))
        return lines
    return [prefix + _yaml_scalar(value)]


def canonical_yaml(data):
    """Render deterministic YAML accepted by :func:`parse_yaml_subset`."""
    if not isinstance(data, dict):
        raise TypeError("canonical runtime state must be a mapping")
    text = "\n".join(_render_yaml_node(data, 0)) + "\n"
    reparsed = parse_yaml_subset(text)
    if reparsed != data:
        raise YamlSubsetError("canonical YAML did not round-trip under the restricted parser")
    return text


def sha256_bytes(data):
    """Return the canonical ``sha256:<hex>`` spelling for bytes or text."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def repository_tree_sha256(root, relative_directory):
    """Hash one repository-contained regular-file tree deterministically.

    The digest binds repository-relative paths and bytes.  Symlinks, hard
    links, special files, path escape, and a non-directory root fail closed.
    It is used for Standards/Profile adoption snapshots where hashing the
    adopter's entire knowledge corpus would broaden the governance boundary.
    """
    directory = repository_path(
        root, relative_directory, must_exist=True, reject_symlink=True)
    if not os.path.isdir(directory) or os.path.islink(directory):
        raise ValueError("snapshot target must be a real directory: %s" %
                         relative_directory)
    root_real = os.path.realpath(os.path.abspath(root))
    digest = hashlib.sha256()
    digest.update(b"cambium-repository-tree-snapshot-v1\0")
    entries = []
    for current, directories, files in os.walk(directory, topdown=True,
                                               followlinks=False):
        directories[:] = sorted(directories)
        for name in directories:
            candidate = os.path.join(current, name)
            if os.path.islink(candidate):
                raise ValueError("snapshot cannot traverse symlink: %s" %
                                 os.path.relpath(candidate, root_real))
        for name in sorted(files):
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, root_real).replace(os.sep, "/")
            entries.append((relative, absolute))
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise OSError(errno.ENOTSUP, "tree snapshot requires O_NOFOLLOW",
                      directory)
    for relative, absolute in sorted(entries):
        listed = os.lstat(absolute)
        if not stat.S_ISREG(listed.st_mode) or listed.st_nlink != 1:
            raise ValueError("snapshot requires singly-linked regular file: %s" %
                             relative)
        fd = os.open(absolute, os.O_RDONLY | nofollow |
                     getattr(os, "O_CLOEXEC", 0))
        try:
            before = os.fstat(fd)
            file_digest = hashlib.sha256()
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                file_digest.update(chunk)
            after = os.fstat(fd)
            identity_before = (
                before.st_dev, before.st_ino, before.st_size,
                getattr(before, "st_mtime_ns", int(before.st_mtime * 1e9)),
                getattr(before, "st_ctime_ns", int(before.st_ctime * 1e9)),
            )
            identity_after = (
                after.st_dev, after.st_ino, after.st_size,
                getattr(after, "st_mtime_ns", int(after.st_mtime * 1e9)),
                getattr(after, "st_ctime_ns", int(after.st_ctime * 1e9)),
            )
            if identity_before != identity_after:
                raise OSError(errno.EAGAIN,
                              "repository file changed while hashing",
                              relative)
        finally:
            os.close(fd)
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(before.st_size.to_bytes(8, "big"))
        digest.update(file_digest.digest())
    return "sha256:" + digest.hexdigest()


def repository_snapshot_sha256(root):
    """Hash the current repository content outside Git and Cambium state.

    The digest is a deterministic, path-sensitive snapshot of every regular
    file below ``root`` except the top-level ``.git`` and ``.cambium`` control
    namespaces and every ``__pycache__`` directory at any depth.  Runtime state
    is bound separately by Queue receipts, so excluding it avoids a
    receipt/state hash cycle.  ``__pycache__`` is excluded because the gates
    execute in-repository Python against the same tree they measure: importing
    a Tools module writes bytecode into the snapshot, so a digest taken before
    a check would no longer match the digest observed after it.  Symlinks and
    special files fail closed because their target bytes are not a stable
    repository snapshot.  Each file is checked before and after reading so an
    in-place concurrent mutation cannot silently produce a mixed digest.
    """
    root_real = os.path.realpath(os.path.abspath(root))
    if not os.path.isdir(root_real):
        raise ValueError("repository snapshot root must be a directory")

    digest = hashlib.sha256()
    digest.update(b"cambium-repository-snapshot-v1\0")
    paths = []
    for current, directories, files in os.walk(root_real, topdown=True,
                                               followlinks=False):
        relative_dir = os.path.relpath(current, root_real)
        if relative_dir == ".":
            directories[:] = sorted(
                name for name in directories
                if name not in (".git", ".cambium", "__pycache__")
            )
        else:
            directories[:] = sorted(
                name for name in directories
                if name != "__pycache__"
            )
        for name in directories:
            candidate = os.path.join(current, name)
            if os.path.islink(candidate):
                raise ValueError(
                    "repository snapshot cannot traverse symlink: %s" %
                    os.path.relpath(candidate, root_real)
                )
        visible_files = files
        if relative_dir == ".":
            visible_files = [
                name for name in files
                if name not in (".git", ".cambium")
            ]
        for name in sorted(visible_files):
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, root_real).replace(os.sep, "/")
            paths.append((relative, absolute))

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise OSError(errno.ENOTSUP,
                      "repository snapshot requires O_NOFOLLOW", root_real)
    for relative, absolute in sorted(paths):
        listed = os.lstat(absolute)
        if not stat.S_ISREG(listed.st_mode):
            raise ValueError(
                "repository snapshot requires a regular file: %s" % relative
            )
        if listed.st_nlink != 1:
            raise ValueError(
                "repository snapshot rejects hard-linked content: %s" %
                relative
            )
        flags = (os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) |
                 getattr(os, "O_NONBLOCK", 0))
        fd = os.open(absolute, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(
                    "repository snapshot requires a regular file: %s" %
                    relative
                )
            if before.st_nlink != 1:
                raise ValueError(
                    "repository snapshot rejects hard-linked content: %s" %
                    relative
                )
            if (listed.st_dev, listed.st_ino) != (before.st_dev, before.st_ino):
                raise OSError(errno.EAGAIN,
                              "repository file changed before hashing",
                              relative)
            file_digest = hashlib.sha256()
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                file_digest.update(chunk)
            after = os.fstat(fd)
            before_identity = (
                before.st_dev, before.st_ino, before.st_size,
                getattr(before, "st_mtime_ns", int(before.st_mtime * 1e9)),
                getattr(before, "st_ctime_ns", int(before.st_ctime * 1e9)),
            )
            after_identity = (
                after.st_dev, after.st_ino, after.st_size,
                getattr(after, "st_mtime_ns", int(after.st_mtime * 1e9)),
                getattr(after, "st_ctime_ns", int(after.st_ctime * 1e9)),
            )
            if before_identity != after_identity:
                raise OSError(errno.EAGAIN,
                              "repository file changed while hashing",
                              relative)
        finally:
            os.close(fd)
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(before.st_size.to_bytes(8, "big"))
        digest.update(file_digest.digest())
    return "sha256:" + digest.hexdigest()


def durable_replace(source, destination):
    """Atomically rename one path and persist both directory-name changes.

    ``os.replace`` provides namespace atomicity but does not by itself prove
    that a cross-directory rename survives a crash.  After the rename this
    helper fsyncs the destination parent (new name) and then the distinct
    source parent (removed name).  An fsync failure is deliberately surfaced:
    callers must inspect the two paths and retain their recovery lock.
    """
    source = os.path.abspath(os.fspath(source))
    destination = os.path.abspath(os.fspath(destination))
    source_parent = os.path.dirname(source)
    destination_parent = os.path.dirname(destination)
    os.replace(source, destination)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    parents = [destination_parent]
    if os.path.realpath(source_parent) != os.path.realpath(destination_parent):
        parents.append(source_parent)
    for parent in parents:
        directory_fd = os.open(parent, flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def atomic_write_text(path, text, validator=None):
    """Validate and atomically replace one UTF-8 file in its own directory."""
    if validator:
        validator(text)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".cambium-write-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_write_yaml(path, data):
    text = canonical_yaml(data)
    atomic_write_text(path, text, validator=parse_yaml_subset)
    return text


def make_queue_receipt(action, target, result, details, seq=1, **fields):
    """Build a normal audit receipt with Queue before/after metadata."""
    receipt = make_receipt(
        "update_queue", "1.2.0", action, target, result, details, seq
    )
    receipt.update(fields)
    return receipt
