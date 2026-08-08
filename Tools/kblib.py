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

LIB_VERSION = "1.6.0"

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


def parse_vocabulary_artifact(text):
    """Parse the composed vocabulary artifact and prove it is a composition.

    ``kernel/K12 Quality Assurance/05 Automated and Manual Checks.md`` requires
    that the input of the frontmatter vocabulary check "MUST be composed from
    the kernel base vocabulary and the selected profile's `Vocabulary
    Extensions`".  ``parse_yaml_subset`` maps empty input to ``{}``, so on its
    own it cannot tell a composed artifact from a truncated or half-written
    file; both yield an empty field set, and an empty field set makes every
    controlled value legal.  This predicate is the deterministic reading of
    that MUST: the bytes must parse, be a mapping, and carry a non-empty
    ``fields`` mapping, because the kernel base contributes fields
    unconditionally.  Whether the *values* are the right ones stays with the
    rule owners and with ``compose_vocab.py --check``; this function only
    separates "a vocabulary" from "a file".

    Returns the parsed mapping. Raises ``YamlSubsetError`` when the bytes are
    outside the subset grammar and ``ValueError`` when they parse but are not
    a vocabulary artifact.
    """
    data = parse_yaml_subset(text)
    if not isinstance(data, dict):
        raise ValueError(
            "composed vocabulary must be a mapping, found %s"
            % type(data).__name__)
    fields = data.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise ValueError(
            "composed vocabulary carries no `fields` mapping; an empty, "
            "truncated, or half-written artifact is not the composition of "
            "the kernel base and the selected profile's Vocabulary Extensions")
    return data


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


# ---------------------------------------------------------------------------
# Batch lifecycle transition map
# ---------------------------------------------------------------------------
# The single map of which batch lifecycle state may follow which.  It lives
# here, beside the other rules two tools share, because both sides of the
# lifecycle need it and neither may import the other: the writer that applies
# a transition (`update_queue`) already imports the checker (`check_queue`),
# so the checker cannot import the writer back to ask what is reachable.  A
# second copy would let the two disagree about which position a batch can
# still get to, and a boundary gate would then be waived or demanded wrongly.

BATCH_LIFECYCLE_TRANSITIONS = {
    "queued": frozenset(("open",)),
    "open": frozenset(("merge-ready",)),
    "merge-ready": frozenset(("closed", "open")),
    "closed": frozenset(),
    "cancelled": frozenset(),
}


def reachable_batch_states(state):
    """Return every state reachable from ``state`` by one or more transitions.

    Reachability is transitive and follows cycles: ``merge-ready -> open``
    means an ``open`` batch can return to ``open``, so ``open`` is in its own
    forward set.  An unknown state has no sanctioned successor and returns the
    empty set, which makes every position judged against it fail closed.
    """
    if state not in BATCH_LIFECYCLE_TRANSITIONS:
        return frozenset()
    seen = set()
    pending = list(BATCH_LIFECYCLE_TRANSITIONS[state])
    while pending:
        candidate = pending.pop()
        if candidate in seen:
            continue
        seen.add(candidate)
        pending.extend(BATCH_LIFECYCLE_TRANSITIONS.get(candidate, ()))
    return frozenset(seen)


WIKI_LINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
READ_SET_NON_BOUNDARY_SECTIONS = ("Purpose", "Related")
READ_SET_DOCUMENT_TYPES = frozenset(("read-set", "profile-read-set"))


def parse_wiki_link(inner):
    r"""Return one Wiki Link's normalized target and optional heading.

    Markdown tables escape the alias separator as ``\|`` while ordinary prose
    uses ``|``.  Both forms share one path rule, and an explicit ``.md`` suffix
    is normalized away so callers can choose their own storage form without
    ever producing ``.md.md``.
    """
    target_part = re.split(r"\\\||\|", inner, maxsplit=1)[0].strip()
    target, _, heading = target_part.partition("#")
    target = target.strip()
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target, heading.strip()


def read_set_document_type(text):
    """Return a recognized Read Set frontmatter type, otherwise ``None``.

    Kernel routes use ``type: read-set`` and profile supplemental routes use
    ``type: profile-read-set``.  A boundary target is traversed as a Read Set
    only when its own bytes prove one of those types; directory names alone do
    not turn an index or ordinary profile page into a Read Set.
    """
    frontmatter = extract_frontmatter(text or "")
    if frontmatter is None:
        return None
    try:
        fields = parse_yaml_subset(frontmatter)
    except (ValueError, YamlSubsetError):
        return None
    if not isinstance(fields, dict):
        return None
    document_type = fields.get("type")
    return (document_type if isinstance(document_type, str) and
            document_type in READ_SET_DOCUMENT_TYPES else None)


def read_set_boundary_targets(text):
    """Return the repository paths one Read Set's loading boundaries name.

    A Read Set's `Purpose` states applicability and `Related` is navigation, so
    neither is a loading boundary; every other H2 is one, and every Wiki Link
    inside a boundary names a module the route loads.  A Wiki Link is the only
    boundary syntax: a code span such as a `python3 Tools/...` command line is
    an instruction the route runs, not a module its reader loads.  Targets come
    back as repository-relative `.md` paths, deduplicated and sorted.

    Both consumers of this rule share this one parser -- the leaf-coverage
    check that asks which kernel leaves no boundary names, and the adoption
    check that asks which boundary-named modules a declared load set omits --
    so the two can never disagree about what a boundary names.
    """
    targets = set()
    section = ""
    fence_character = None
    fence_length = 0
    for line in (text or "").splitlines():
        if fence_character is None:
            fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
            if fence:
                marker = fence.group(1)
                info = fence.group(2)
                if marker[0] == "`" and "`" in info:
                    fence = None
            if fence:
                fence_character = marker[0]
                fence_length = len(marker)
                continue
        else:
            closing = re.match(
                r"^ {0,3}%s{%d,}[ \t]*$" %
                (re.escape(fence_character), fence_length), line)
            if closing:
                fence_character = None
                fence_length = 0
            continue
        heading = re.match(r"^ {0,3}##[ \t]+(.+?)\s*#*\s*$", line)
        if heading:
            section = heading.group(1).strip()
            continue
        if not section or section in READ_SET_NON_BOUNDARY_SECTIONS:
            continue
        for inner in WIKI_LINK_RE.findall(line):
            target, _heading = parse_wiki_link(inner)
            if target:
                targets.add(target + ".md")
    return sorted(targets)


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
# Structure Registry shape contract (owner: K01/05 + K01/06; slot shape:
# profiles/_template/structure-registry.yaml).  Shared by check_profile.py
# (profile shape gate) and check_structure.py (vault resolution gate) so the
# two cannot drift into parallel validators.
# ---------------------------------------------------------------------------

STRUCTURE_REGISTRY_TOP_FIELDS = frozenset((
    "schema_version", "applicability", "units", "support_layers",
))
STRUCTURE_APPLICABILITY_FIELDS = frozenset(("state", "reason"))
STRUCTURE_UNIT_FIELDS = frozenset((
    "id", "kind", "parent", "root", "entry", "global_map_entry", "roles",
))
STRUCTURE_ENTRY_FIELDS = frozenset(("path", "expected_type"))
STRUCTURE_UNIT_ROLES = ("sequence", "coverage", "quick_reference",
                        "expression")
STRUCTURE_ROLE_MODE_FIELDS = {
    "embedded": (frozenset(("mode", "path", "heading")), frozenset()),
    "standalone": (frozenset(("mode", "path")), frozenset()),
    "derived": (frozenset(("mode", "generator", "inputs_owner")),
                frozenset(("path", "heading"))),
    "not-applicable": (frozenset(("mode", "reason")), frozenset()),
}
STRUCTURE_LAYER_FIELDS = frozenset((
    "layer_id", "role", "root", "entry", "layout", "taxonomy", "coverage",
    "global_map_entry", "bindings",
))
STRUCTURE_LAYER_ROLES = ("cases", "sources", "synthesis", "expression")
STRUCTURE_TAXONOMY_FIELDS = frozenset(("axis", "page_field", "classes"))
STRUCTURE_TAXONOMY_CLASS_FIELDS = frozenset(("class", "directory"))
STRUCTURE_LAYER_BINDING_FIELDS = {
    "cases": frozenset(("evidence_binding_owner",)),
    "sources": frozenset(("authority_taxonomy_ref", "intake_policy_ref",
                          "freshness_policy_ref", "index_mode")),
    "synthesis": frozenset(("question_identity_field",
                            "promotion_policy_ref")),
    "expression": frozenset(("artifact_registry_ref",
                             "preparation_route_ref",
                             "readiness_projection")),
}
STRUCTURE_SOURCE_INDEX_MODES = frozenset(("derived", "none"))


def _structure_nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _structure_closed(errors, value, required, label, optional=frozenset()):
    """Closed-mapping check; returns the mapping (or {}) for further reads."""
    if not isinstance(value, dict):
        errors.append(("structure-registry-schema", label,
                       "must be a mapping"))
        return {}
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required - optional)
    if missing:
        errors.append(("structure-registry-schema", label,
                       "missing field(s): %s" % ", ".join(missing)))
    if extra:
        errors.append(("structure-registry-schema", label,
                       "unsupported field(s): %s" % ", ".join(extra)))
    return value


def _structure_role_mapping(errors, value, label):
    """Validate one role declaration; returns the mapping (or {})."""
    if not isinstance(value, dict):
        errors.append(("structure-registry-role", label,
                       "role must be a mapping declaring exactly one mode"))
        return {}
    mode = value.get("mode")
    if mode not in STRUCTURE_ROLE_MODE_FIELDS:
        errors.append((
            "structure-registry-role", label,
            "mode must be one of embedded, standalone, derived, "
            "not-applicable; found %r — absence of a declaration must not "
            "express not-applicable" % (mode,)))
        return value
    required, optional = STRUCTURE_ROLE_MODE_FIELDS[mode]
    value = _structure_closed(errors, value, required, label, optional)
    for field in sorted((required | optional) & set(value)):
        if field == "mode":
            continue
        if not _structure_nonempty(value.get(field)):
            errors.append(("structure-registry-role", "%s:%s" % (label, field),
                           "must be a nonempty string"))
    if value.get("heading") is not None and mode == "derived" and \
            value.get("path") is None:
        errors.append(("structure-registry-role", label,
                       "a derived rendering heading requires its path"))
    return value


def validate_structure_registry_shape(document, target="structure-registry"):
    """Return [(check_id, label, details)] shape errors for one registry.

    Pure byte-level contract: closed fields, applicability branches, per-mode
    role declarations, ID uniqueness, and an existing acyclic parent graph.
    Vault resolution (paths, headings, Profile Scope layers, Global Map and
    Coverage references) belongs to check_structure.py.
    """
    errors = []
    document = _structure_closed(
        errors, document, STRUCTURE_REGISTRY_TOP_FIELDS, target)
    if type(document.get("schema_version")) is not int or \
            document.get("schema_version") != 1:
        errors.append(("structure-registry-schema", target,
                       "schema_version must be integer 1"))
    applicability = _structure_closed(
        errors, document.get("applicability"),
        STRUCTURE_APPLICABILITY_FIELDS, target + ":applicability")
    units = document.get("units")
    layers = document.get("support_layers")
    if not isinstance(units, list):
        errors.append(("structure-registry-schema", target + ":units",
                       "must be a list"))
        units = []
    if not isinstance(layers, list):
        errors.append(("structure-registry-schema",
                       target + ":support_layers", "must be a list"))
        layers = []

    state = applicability.get("state")
    reason = applicability.get("reason")
    if state == "configured":
        if reason is not None:
            errors.append(("structure-registry-applicability", target,
                           "configured requires null reason"))
        if not units:
            errors.append((
                "structure-registry-applicability", target,
                "configured requires at least one unit; a corpus with no "
                "registrable unit selects not-applicable instead"))
    elif state == "not-applicable":
        if not _structure_nonempty(reason):
            errors.append(("structure-registry-applicability", target,
                           "not-applicable requires a nonempty reason"))
        if units or layers:
            errors.append((
                "structure-registry-applicability", target,
                "not-applicable requires empty units and support_layers"))
    else:
        errors.append(("structure-registry-applicability", target,
                       "state must be configured or not-applicable; found %r"
                       % (state,)))

    seen_ids = {}
    parents = {}
    kinds = {}
    for index, unit in enumerate(units):
        label = "%s:units[%d]" % (target, index)
        unit = _structure_closed(errors, unit, STRUCTURE_UNIT_FIELDS, label)
        unit_id = unit.get("id")
        if not _structure_nonempty(unit_id):
            errors.append(("structure-registry-unit", label + ":id",
                           "must be a nonempty string"))
        elif unit_id in seen_ids:
            errors.append(("structure-registry-unit", label + ":id",
                           "duplicate unit id %r; unit IDs are unique"
                           % unit_id))
        else:
            seen_ids[unit_id] = index
            parents[unit_id] = unit.get("parent")
            kinds[unit_id] = unit.get("kind")
        kind = unit.get("kind")
        parent = unit.get("parent")
        if kind not in ("domain", "module"):
            errors.append(("structure-registry-unit", label + ":kind",
                           "kind must be domain or module; found %r"
                           % (kind,)))
        elif kind == "domain" and parent is not None:
            errors.append(("structure-registry-unit", label + ":parent",
                           "a domain has no parent; found %r" % (parent,)))
        elif kind == "module" and not _structure_nonempty(parent):
            errors.append(("structure-registry-unit", label + ":parent",
                           "a module requires exactly one existing parent "
                           "unit id"))
        root = unit.get("root")
        if not _structure_nonempty(root):
            errors.append(("structure-registry-unit", label + ":root",
                           "must be a nonempty repository-relative directory"))
        elif root.endswith("/"):
            errors.append(("structure-registry-unit", label + ":root",
                           "no trailing slash"))
        entry = _structure_closed(errors, unit.get("entry"),
                                  STRUCTURE_ENTRY_FIELDS, label + ":entry")
        if not _structure_nonempty(entry.get("path")) or \
                not str(entry.get("path", "")).lower().endswith(".md"):
            errors.append(("structure-registry-unit", label + ":entry",
                           "entry.path must be a nonempty .md path"))
        expected = entry.get("expected_type")
        if expected is not None and not _structure_nonempty(expected):
            errors.append(("structure-registry-unit",
                           label + ":entry:expected_type",
                           "must be null or a nonempty type value"))
        gm_entry = unit.get("global_map_entry")
        if gm_entry is not None and not _structure_nonempty(gm_entry):
            errors.append(("structure-registry-unit",
                           label + ":global_map_entry",
                           "must be null or a nonempty entry id"))
        roles = _structure_closed(errors, unit.get("roles"),
                                  frozenset(STRUCTURE_UNIT_ROLES),
                                  label + ":roles")
        for role in STRUCTURE_UNIT_ROLES:
            if role in roles:
                _structure_role_mapping(errors, roles.get(role),
                                        "%s:roles:%s" % (label, role))

    for unit_id, parent in parents.items():
        if parent is None or not _structure_nonempty(parent):
            continue
        if parent not in parents:
            errors.append(("structure-registry-parent",
                           "%s:%s" % (target, unit_id),
                           "parent %r is not a registered unit id" % parent))
    for unit_id in parents:
        seen = set()
        current = unit_id
        while current is not None and current in parents:
            if current in seen:
                errors.append(("structure-registry-parent",
                               "%s:%s" % (target, unit_id),
                               "parent graph contains a cycle through %r"
                               % current))
                break
            seen.add(current)
            current = parents.get(current) \
                if _structure_nonempty(parents.get(current)) else None

    seen_layers = set()
    for index, layer in enumerate(layers):
        label = "%s:support_layers[%d]" % (target, index)
        layer = _structure_closed(errors, layer, STRUCTURE_LAYER_FIELDS,
                                  label)
        layer_id = layer.get("layer_id")
        if not _structure_nonempty(layer_id):
            errors.append(("structure-registry-layer", label + ":layer_id",
                           "must be a nonempty Profile Scope Layer ID"))
        elif layer_id in seen_layers:
            errors.append(("structure-registry-layer", label + ":layer_id",
                           "duplicate support layer %r" % layer_id))
        else:
            seen_layers.add(layer_id)
        role = layer.get("role")
        if role not in STRUCTURE_LAYER_ROLES:
            errors.append(("structure-registry-layer", label + ":role",
                           "role must be one of %s; found %r"
                           % (", ".join(STRUCTURE_LAYER_ROLES), role)))
        root = layer.get("root")
        if not _structure_nonempty(root) or str(root).endswith("/"):
            errors.append(("structure-registry-layer", label + ":root",
                           "must be a nonempty directory with no trailing "
                           "slash"))
        entry = _structure_closed(errors, layer.get("entry"),
                                  STRUCTURE_ENTRY_FIELDS, label + ":entry")
        if not _structure_nonempty(entry.get("path")) or \
                not str(entry.get("path", "")).lower().endswith(".md"):
            errors.append(("structure-registry-layer", label + ":entry",
                           "entry.path must be a nonempty .md path"))
        layout = layer.get("layout")
        taxonomy = layer.get("taxonomy")
        if layout == "flat":
            if taxonomy is not None:
                errors.append(("structure-registry-layout", label,
                               "flat layout requires null taxonomy"))
        elif layout == "grouped":
            taxonomy = _structure_closed(errors, taxonomy,
                                         STRUCTURE_TAXONOMY_FIELDS,
                                         label + ":taxonomy")
            for field in ("axis", "page_field"):
                if not _structure_nonempty(taxonomy.get(field)):
                    errors.append(("structure-registry-layout",
                                   "%s:taxonomy:%s" % (label, field),
                                   "must be a nonempty string"))
            classes = taxonomy.get("classes")
            if not isinstance(classes, list) or not classes:
                errors.append(("structure-registry-layout",
                               label + ":taxonomy:classes",
                               "grouped layout requires at least one class"))
                classes = []
            names = []
            directories = []
            for c_index, entry_row in enumerate(classes):
                c_label = "%s:taxonomy:classes[%d]" % (label, c_index)
                entry_row = _structure_closed(
                    errors, entry_row, STRUCTURE_TAXONOMY_CLASS_FIELDS,
                    c_label)
                for field, bucket in (("class", names),
                                      ("directory", directories)):
                    value = entry_row.get(field)
                    if not _structure_nonempty(value):
                        errors.append(("structure-registry-layout",
                                       "%s:%s" % (c_label, field),
                                       "must be a nonempty string"))
                    else:
                        bucket.append(value)
            for bucket, what in ((names, "class"), (directories,
                                                    "directory")):
                if len(set(bucket)) != len(bucket):
                    errors.append((
                        "structure-registry-layout",
                        label + ":taxonomy:classes",
                        "%s values must be unique; the class-to-directory "
                        "mapping is one-to-one" % what))
        else:
            errors.append(("structure-registry-layout", label + ":layout",
                           "layout must be flat or grouped; found %r"
                           % (layout,)))
        _structure_role_mapping(errors, layer.get("coverage"),
                                label + ":coverage")
        gm_entry = layer.get("global_map_entry")
        if gm_entry is not None and not _structure_nonempty(gm_entry):
            errors.append(("structure-registry-layer",
                           label + ":global_map_entry",
                           "must be null or a nonempty entry id"))
        binding_fields = STRUCTURE_LAYER_BINDING_FIELDS.get(role)
        if binding_fields is not None:
            bindings = _structure_closed(errors, layer.get("bindings"),
                                         binding_fields, label + ":bindings")
            for field in sorted(binding_fields & set(bindings)):
                value = bindings.get(field)
                if field == "index_mode":
                    if value not in STRUCTURE_SOURCE_INDEX_MODES:
                        errors.append((
                            "structure-registry-layer",
                            "%s:bindings:index_mode" % label,
                            "must be derived or none; a hand-maintained "
                            "member index is not a registrable mode"))
                elif field == "readiness_projection":
                    _structure_role_mapping(
                        errors, value, "%s:bindings:%s" % (label, field))
                elif not _structure_nonempty(value):
                    errors.append(("structure-registry-layer",
                                   "%s:bindings:%s" % (label, field),
                                   "must be a nonempty string"))
    return errors


PROFILE_SCOPE_ARCHITECTURE_HEADING = "Logical Architecture"


def profile_scope_layers(scope_text):
    """Return {layer_id: [directories]} from a Profile Scope's Logical
    Architecture table (Profile Scope is the sole Layer ID owner)."""
    layers = {}
    in_section = False
    for line in scope_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = (stripped[3:].strip() ==
                          PROFILE_SCOPE_ARCHITECTURE_HEADING)
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2 or all(
                c and set(c) <= set(":-") for c in cells if c):
            continue
        layer = cells[0].strip("`").strip()
        if not layer or layer.lower().startswith("stable layer id"):
            continue
        directories = [d.strip().strip("`").strip()
                       for d in cells[1].split(";")]
        layers[layer] = [d for d in directories if d]
    return layers


# ---------------------------------------------------------------------------
# Metadata Contract shape contract (owner: K08/06 + K08/08; slot shape:
# profiles/_template/metadata-contract.yaml).  Shared by check_profile.py
# (profile shape gate) and compose_page_contract.py (composition) so the two
# cannot drift into parallel validators.
# ---------------------------------------------------------------------------

METADATA_CONTRACT_TOP_FIELDS = frozenset((
    "schema_version", "applicability", "applicability_differences",
    "extension_fields", "relationship_extensions", "section_roles",
))
# Optional top-level keys of the Metadata Contract slot (K08/09:
# boundary projection display-label overrides).
METADATA_CONTRACT_OPTIONAL_FIELDS = frozenset(("boundary_projection",))
METADATA_APPLICABILITY_FIELDS = frozenset(("state",))
METADATA_MODES = frozenset((
    "required", "conditional", "optional", "derived", "projection",
    "user-owned", "forbidden",
))
METADATA_SHAPES = frozenset((
    "nonempty-string", "date", "url", "path", "list-of-strings",
    "list-of-paths", "delegated",
))
METADATA_DIFFERENCE_FIELDS = frozenset(("field", "mode", "condition", "note"))
METADATA_EXTENSION_FIELDS = frozenset((
    "field", "mode", "shape", "condition", "owner",
))
METADATA_RELATIONSHIP_FIELDS = frozenset((
    "field", "mode", "direction", "target", "shape", "owner",
))
METADATA_SECTION_ROLE_FIELDS = frozenset((
    "role", "titles", "aliases", "owner",
))
METADATA_SECTION_ROLES = frozenset(("sources", "related"))
# The only mode transitions a profile difference may declare (K08/06:
# a profile only tightens).
METADATA_TIGHTENING = frozenset((
    ("optional", "required"), ("optional", "conditional"),
    ("conditional", "required"),
))


def validate_condition_shape(condition, label, errors):
    """Validate one K08/06 condition: {all|any: [{field, in|absent}]}."""
    if not isinstance(condition, dict) or \
            set(condition) - {"all", "any"} or not condition:
        errors.append(("metadata-contract-condition", label,
                       "condition must be a mapping with `all` and/or `any` "
                       "clause lists"))
        return
    for group in ("all", "any"):
        if group not in condition:
            continue
        clauses = condition[group]
        if not isinstance(clauses, list) or not clauses:
            errors.append(("metadata-contract-condition",
                           "%s:%s" % (label, group),
                           "must be a nonempty list of clauses"))
            continue
        for index, clause in enumerate(clauses):
            c_label = "%s:%s[%d]" % (label, group, index)
            if not isinstance(clause, dict) or \
                    set(clause) - {"field", "in", "absent"} or \
                    not _structure_nonempty(clause.get("field")):
                errors.append(("metadata-contract-condition", c_label,
                               "clause must carry a nonempty `field` plus "
                               "`in` or `absent`"))
                continue
            has_in = "in" in clause
            has_absent = "absent" in clause
            if has_in == has_absent:
                errors.append(("metadata-contract-condition", c_label,
                               "exactly one of `in` / `absent` is required"))
            elif has_in and (not isinstance(clause["in"], list)
                             or not clause["in"]):
                errors.append(("metadata-contract-condition", c_label,
                               "`in` must be a nonempty value list"))
            elif has_absent and clause["absent"] is not True:
                errors.append(("metadata-contract-condition", c_label,
                               "`absent` carries only the literal true"))


def validate_metadata_contract_shape(document, target="metadata-contract"):
    """Return [(check_id, label, details)] shape errors for one contract.

    Pure byte-level: closed fields, the configured / kernel-defaults branch,
    mode and shape vocabularies, and per-entry conditional coherence.
    Whether a difference is a legal tightening of the kernel base belongs to
    Tools/compose_page_contract.py, which owns the composition."""
    errors = []
    document = _structure_closed(
        errors, document, METADATA_CONTRACT_TOP_FIELDS, target,
        METADATA_CONTRACT_OPTIONAL_FIELDS)
    if type(document.get("schema_version")) is not int or \
            document.get("schema_version") != 1:
        errors.append(("metadata-contract-schema", target,
                       "schema_version must be integer 1"))
    applicability = _structure_closed(
        errors, document.get("applicability"),
        METADATA_APPLICABILITY_FIELDS, target + ":applicability")
    state = applicability.get("state")
    lists = {}
    for name in ("applicability_differences", "extension_fields",
                 "relationship_extensions", "section_roles"):
        value = document.get(name)
        if not isinstance(value, list):
            errors.append(("metadata-contract-schema",
                           "%s:%s" % (target, name), "must be a list"))
            value = []
        lists[name] = value
    total = sum(len(v) for v in lists.values())
    if state == "kernel-defaults":
        if total:
            errors.append(("metadata-contract-applicability", target,
                           "kernel-defaults requires all three lists empty"))
    elif state == "configured":
        if not total:
            errors.append((
                "metadata-contract-applicability", target,
                "configured requires at least one difference, extension "
                "field, or relationship extension; a profile with none "
                "declares kernel-defaults instead"))
    else:
        errors.append(("metadata-contract-applicability", target,
                       "state must be configured or kernel-defaults; "
                       "found %r" % (state,)))

    seen = set()

    def check_entry(entry, allowed, label, requires_shape):
        entry = _structure_closed(errors, entry, frozenset(("field", "mode")),
                                  label, allowed - {"field", "mode"})
        field = entry.get("field")
        if not _structure_nonempty(field):
            errors.append(("metadata-contract-entry", label + ":field",
                           "must be a nonempty field name"))
        elif field in seen:
            errors.append(("metadata-contract-entry", label + ":field",
                           "field %r is declared more than once across the "
                           "contract" % field))
        else:
            seen.add(field)
        mode = entry.get("mode")
        if mode not in METADATA_MODES:
            errors.append(("metadata-contract-entry", label + ":mode",
                           "mode must be one of %s; found %r"
                           % (", ".join(sorted(METADATA_MODES)), mode)))
        condition = entry.get("condition")
        if mode == "conditional" and condition is None:
            errors.append(("metadata-contract-entry", label,
                           "conditional mode requires a condition"))
        if condition is not None:
            if "condition" not in allowed:
                errors.append(("metadata-contract-entry", label,
                               "this entry kind carries no condition"))
            else:
                validate_condition_shape(condition, label + ":condition",
                                         errors)
        if requires_shape and entry.get("shape") not in METADATA_SHAPES:
            errors.append(("metadata-contract-entry", label + ":shape",
                           "shape must be one of %s; found %r"
                           % (", ".join(sorted(METADATA_SHAPES)),
                              entry.get("shape"))))
        if "owner" in allowed and not _structure_nonempty(
                entry.get("owner")):
            errors.append(("metadata-contract-entry", label + ":owner",
                           "must name a nonempty prose owner"))
        return entry

    for index, entry in enumerate(lists["applicability_differences"]):
        label = "%s:applicability_differences[%d]" % (target, index)
        entry = check_entry(entry, METADATA_DIFFERENCE_FIELDS, label, False)
        mode = entry.get("mode")
        if mode is not None and mode in METADATA_MODES and \
                mode not in ("required", "conditional"):
            errors.append((
                "metadata-contract-entry", label + ":mode",
                "a difference only tightens: the declared mode must be "
                "required or conditional"))
    for index, entry in enumerate(lists["extension_fields"]):
        label = "%s:extension_fields[%d]" % (target, index)
        check_entry(entry, METADATA_EXTENSION_FIELDS, label, True)

    seen_roles = set()
    for index, entry in enumerate(lists["section_roles"]):
        label = "%s:section_roles[%d]" % (target, index)
        entry = _structure_closed(errors, entry,
                                  frozenset(("role", "titles", "owner")),
                                  label, frozenset(("aliases",)))
        role = entry.get("role")
        if role not in METADATA_SECTION_ROLES:
            errors.append(("metadata-contract-section-role",
                           label + ":role",
                           "role must be sources or related; found %r"
                           % (role,)))
        elif role in seen_roles:
            errors.append(("metadata-contract-section-role",
                           label + ":role",
                           "role %r is bound more than once" % role))
        else:
            seen_roles.add(role)
        titles = entry.get("titles")
        if not isinstance(titles, list) or not titles or \
                not all(_structure_nonempty(v) for v in titles):
            errors.append(("metadata-contract-section-role",
                           label + ":titles",
                           "must be a nonempty list of nonempty display "
                           "titles"))
        aliases = entry.get("aliases")
        if aliases is not None and (
                not isinstance(aliases, list) or
                not all(_structure_nonempty(v) for v in aliases)):
            errors.append(("metadata-contract-section-role",
                           label + ":aliases",
                           "must be a list of nonempty migration aliases"))
        if not _structure_nonempty(entry.get("owner")):
            errors.append(("metadata-contract-section-role",
                           label + ":owner",
                           "must point at the Language Contract owner"))

    for index, entry in enumerate(lists["relationship_extensions"]):
        label = "%s:relationship_extensions[%d]" % (target, index)
        entry = check_entry(entry, METADATA_RELATIONSHIP_FIELDS, label, True)
        if not _structure_nonempty(entry.get("direction")):
            errors.append(("metadata-contract-entry", label + ":direction",
                           "must be a nonempty direction word"))
        t = entry.get("target")
        target_ok = _structure_nonempty(t) or (
            isinstance(t, list) and t and
            all(_structure_nonempty(item) for item in t))
        if not target_ok:
            errors.append(("metadata-contract-entry", label + ":target",
                           "must be a nonempty target type or type list"))

    projection = document.get("boundary_projection")
    if projection is not None:
        projection = _structure_closed(
            errors, projection, frozenset(("labels",)),
            target + ":boundary_projection")
        labels = projection.get("labels")
        if not isinstance(labels, dict) or not labels:
            errors.append(("metadata-contract-boundary-projection",
                           target + ":boundary_projection:labels",
                           "must be a nonempty mapping of display labels"))
        else:
            for key, value in labels.items():
                if key not in BOUNDARY_PROJECTION_LABEL_KEYS:
                    errors.append((
                        "metadata-contract-boundary-projection",
                        "%s:boundary_projection:labels:%s" % (target, key),
                        "label key must be one of %s"
                        % ", ".join(sorted(BOUNDARY_PROJECTION_LABEL_KEYS))))
                elif not _structure_nonempty(value):
                    errors.append((
                        "metadata-contract-boundary-projection",
                        "%s:boundary_projection:labels:%s" % (target, key),
                        "display label must be a nonempty string"))
    return errors


# ---------------------------------------------------------------------------
# Page boundary contract (semantic owner: kernel/K08 Metadata and Status/
# 09 Page Boundary Contract.md; gate: boundary-contract)
# ---------------------------------------------------------------------------


BOUNDARY_FIELD = "boundary"
BOUNDARY_KEYS = frozenset(("owns", "excludes", "goals", "non_goals"))
BOUNDARY_EXCLUDE_FIELDS = frozenset(("concern", "owner"))
BOUNDARY_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BOUNDARY_PROJECTION_BEGIN = "<!-- boundary-projection:begin -->"
BOUNDARY_PROJECTION_END = "<!-- boundary-projection:end -->"
# Kernel default display labels, owned by K08/09 Projection; the selected
# profile MAY override any of them via `boundary_projection.labels` in its
# Metadata Contract slot. Display text only — never schema or semantics.
BOUNDARY_PROJECTION_LABELS = {
    "preamble": "Generated by `Tools/render_boundary_projection.py` from "
                "the `boundary` frontmatter block (K08/09); regenerate "
                "instead of editing.",
    "owns": "Owns",
    "excludes": "Not owned here",
    "owner": "Owner",
    "goals": "Goals",
    "non_goals": "Non-goals",
}
BOUNDARY_PROJECTION_LABEL_KEYS = frozenset(BOUNDARY_PROJECTION_LABELS)


def _boundary_slug_ok(value):
    return isinstance(value, str) and bool(BOUNDARY_SLUG_RE.match(value))


def validate_boundary_shape(value, target="boundary"):
    """Return [(check_id, label, details)] K08/09 shape errors for one block.

    Pure byte-level: key closure, slug shape, entry shapes, in-block slug
    uniqueness, and the owns/excludes overlap. Cross-page rules
    (resolvability, reciprocity, corpus-wide uniqueness) belong to
    Tools/check_boundary_contract.py, which owns the gate."""
    errors = []
    if not isinstance(value, dict) or not value:
        errors.append(("boundary-shape", target,
                       "the boundary block must be a nonempty mapping"))
        return errors
    for key in value:
        if key not in BOUNDARY_KEYS:
            errors.append(("boundary-shape", "%s:%s" % (target, key),
                           "key must be one of %s"
                           % ", ".join(sorted(BOUNDARY_KEYS))))
    owns = value.get("owns")
    owned = []
    if not isinstance(owns, list) or not owns:
        errors.append(("boundary-shape", target + ":owns",
                       "owns must be a nonempty list"))
    else:
        for index, entry in enumerate(owns):
            label = "%s:owns[%d]" % (target, index)
            if isinstance(entry, str):
                if not _boundary_slug_ok(entry):
                    errors.append(("boundary-shape", label,
                                   "concern must be a kebab-case slug; "
                                   "found %r" % (entry,)))
                else:
                    owned.append(entry)
            elif isinstance(entry, dict):
                if len(entry) != 1:
                    errors.append(("boundary-shape", label,
                                   "a grouped entry maps exactly one slug "
                                   "to its sub-slug list"))
                    continue
                slug, subs = next(iter(entry.items()))
                if not _boundary_slug_ok(slug):
                    errors.append(("boundary-shape", label,
                                   "concern must be a kebab-case slug; "
                                   "found %r" % (slug,)))
                else:
                    owned.append(slug)
                if not isinstance(subs, list) or not subs:
                    errors.append(("boundary-shape", label,
                                   "sub-slugs must be a nonempty list"))
                    continue
                for sub in subs:
                    if not _boundary_slug_ok(sub):
                        errors.append(("boundary-shape", label,
                                       "sub-slug must be a kebab-case "
                                       "slug; found %r" % (sub,)))
                    else:
                        owned.append(sub)
            else:
                errors.append(("boundary-shape", label,
                               "entry must be a slug or a one-key mapping "
                               "from a slug to sub-slugs"))
    duplicates = sorted({s for s in owned if owned.count(s) > 1})
    for slug in duplicates:
        errors.append(("boundary-shape", target + ":owns",
                       "slug %r repeats inside owns" % slug))
    excludes = value.get("excludes")
    concerns = []
    if excludes is not None:
        if not isinstance(excludes, list) or not excludes:
            errors.append(("boundary-shape", target + ":excludes",
                           "excludes must be a nonempty list when present"))
        else:
            for index, entry in enumerate(excludes):
                label = "%s:excludes[%d]" % (target, index)
                if not isinstance(entry, dict) or \
                        set(entry) != BOUNDARY_EXCLUDE_FIELDS:
                    errors.append(("boundary-shape", label,
                                   "entry carries exactly `concern` and "
                                   "`owner`"))
                    continue
                if not _boundary_slug_ok(entry.get("concern")):
                    errors.append(("boundary-shape", label + ":concern",
                                   "concern must be a kebab-case slug; "
                                   "found %r" % (entry.get("concern"),)))
                else:
                    concerns.append(entry["concern"])
                owner = entry.get("owner")
                if not isinstance(owner, str) or not owner.strip():
                    errors.append(("boundary-shape", label + ":owner",
                                   "owner must be a nonempty page "
                                   "reference"))
    overlap = sorted(set(owned) & set(concerns))
    for slug in overlap:
        errors.append(("boundary-consistency", target,
                       "slug %r appears both in owns and as an excluded "
                       "concern" % slug))
    for key in ("goals", "non_goals"):
        entries = value.get(key)
        if entries is None:
            continue
        if not isinstance(entries, list) or not entries or \
                not all(isinstance(v, str) and v.strip() for v in entries):
            errors.append(("boundary-shape", "%s:%s" % (target, key),
                           "must be a nonempty list of nonempty strings "
                           "when present"))
    return errors


def boundary_owned_slugs(value):
    """Every referenceable concern this block owns, in declaration order.

    Top-level and sub-slugs are equally referenceable (K08/09). Assumes a
    block that passed validate_boundary_shape; unparseable entries are
    skipped."""
    slugs = []
    if not isinstance(value, dict):
        return slugs
    for entry in value.get("owns") or []:
        if isinstance(entry, str):
            slugs.append(entry)
        elif isinstance(entry, dict) and len(entry) == 1:
            slug, subs = next(iter(entry.items()))
            slugs.append(slug)
            if isinstance(subs, list):
                slugs.extend(s for s in subs if isinstance(s, str))
    return slugs


def render_boundary_projection_lines(boundary, labels=None):
    """Deterministic projection lines for one boundary block, markers
    included. `labels` overlays BOUNDARY_PROJECTION_LABELS (K08/09
    Projection); content order follows declaration order."""
    effective = dict(BOUNDARY_PROJECTION_LABELS)
    for key, value in (labels or {}).items():
        if key in effective and isinstance(value, str) and value.strip():
            effective[key] = value
    lines = [BOUNDARY_PROJECTION_BEGIN, effective["preamble"]]
    rendered_owns = []
    for entry in boundary.get("owns") or []:
        if isinstance(entry, str):
            rendered_owns.append("`%s`" % entry)
        elif isinstance(entry, dict) and len(entry) == 1:
            slug, subs = next(iter(entry.items()))
            rendered_owns.append("`%s` (%s)" % (
                slug, ", ".join("`%s`" % s for s in subs
                                if isinstance(s, str))))
    if rendered_owns:
        lines += ["", "**%s**: %s" % (effective["owns"],
                                      "; ".join(rendered_owns))]
    excludes = [e for e in boundary.get("excludes") or []
                if isinstance(e, dict) and e.get("concern") and
                e.get("owner")]
    if excludes:
        lines += ["", "| %s | %s |" % (effective["excludes"],
                                       effective["owner"]),
                  "|---|---|"]
        for entry in excludes:
            owner = str(entry["owner"])
            link_target = owner[:-3] if owner.lower().endswith(".md") \
                else owner
            title = os.path.basename(link_target)
            lines.append("| `%s` | [[%s\\|%s]] |"
                         % (entry["concern"], link_target, title))
    for key in ("goals", "non_goals"):
        entries = [v for v in boundary.get(key) or []
                   if isinstance(v, str) and v.strip()]
        if entries:
            lines += ["", "**%s**" % effective[key], ""]
            lines += ["- %s" % v for v in entries]
    lines.append(BOUNDARY_PROJECTION_END)
    return lines


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
