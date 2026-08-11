#!/usr/bin/env python3
"""Typed, fail-closed linker for one selected Cambium Profile.

The Profile manifest names its slot files, but two of those files contain
machine-active references of their own:

* Audit Dimension Registry judgment items point at predicate-owner files and
  optional headings.
* Registered Scan Registry rows point at verifier tools, optional Profile-owned
  configuration files, and judgment items.

This module is the one parser and resolver for that transitive contract.  It
does not select a Profile, execute a verifier, write a receipt, or judge the
quality of a predicate.  A partial parse is retained only for deterministic
diagnostics; ``authorized`` is false and command compilation/fingerprinting is
unavailable whenever any diagnostic exists.
"""

from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Iterable, Optional, Sequence, Tuple

import kblib


AUDIT_SLOT = "Audit Dimension Registry"
SCAN_SLOT = "Registered Scan Registry"
PROFILE_FILE_SLOTS = (
    "Profile Scope",
    "Corpus Planning",
    "Structure Registry",
    "Metadata Contract",
    "Priority Rubric",
    "Vocabulary Extensions",
    "Language Contract",
    "Expression Layer Entry",
    "Source Policy",
    "Role Registry",
    AUDIT_SLOT,
    SCAN_SLOT,
    "Routing And Gate Registry",
)

EXTENSION_SECTION = "Extension Dimensions"
JUDGMENT_SECTION = "Judgment Items"
SCAN_SECTION = "Scan Registrations"

EXTENSION_HEADER = (
    "Dimension ID",
    "Target list(s): `review`, `receipt`, or `review + receipt`",
    "Meaning",
)
JUDGMENT_HEADER = (
    "Stable Judgment Item ID",
    "Base or registered receipt Dimension ID",
    "Exact kernel audit-layer name",
    "Bounded audit object one run proves",
    "Evidence role: `emits`, `consumes`, or `triggers`",
    "Predicate owner (repo-relative path; optional `#heading`)",
)
SCAN_HEADER = (
    "Stable Scan ID",
    "Activation role",
    "Whole-corpus scope/root",
    "Deterministic verifier command/path",
    "Candidate predicate/boundary",
    "Judgment Item ID reference",
)

BASE_DIMENSIONS = frozenset((
    "structure_and_links",
    "content_and_depth",
    "formula_and_numeric",
    "source_and_currentness",
    "coverage_and_integration",
    "rendering",
    "guidance_and_contract",
))
EXTENSION_TARGETS = {
    "review": ("review",),
    "receipt": ("receipt",),
    "review + receipt": ("review", "receipt"),
}
EVIDENCE_ROLES = frozenset(("emits", "consumes", "triggers"))
DIMENSION_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
STABLE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
REQUIRED_SCAN_RE = re.compile(r"(?<![A-Za-z0-9])K12/09\s+item\s+6(?![0-9])")
TABLE_SEPARATOR_RE = re.compile(r":?-{3,}:?\Z")
REGISTRATION_RE = re.compile(r"^\s*-\s+Registration:\s*(.*?)\s*$")
SHELL_OPERATORS = frozenset((";", "&&", "||", "|", ">", ">>", "<"))


class ProfileContractError(ValueError):
    """The Profile contract cannot authorize runtime consumption."""


@dataclass(frozen=True)
class SourceCell:
    """One machine-readable source cell with a stable source coordinate."""

    path: str
    section: str
    line: int
    row: int
    field: str
    raw: str

    @property
    def target(self):
        return "%s:%d" % (self.path, self.line)


@dataclass(frozen=True)
class Diagnostic:
    """One deterministic admission failure."""

    check: str
    target: str
    details: str
    source: Optional[SourceCell] = None


@dataclass(frozen=True)
class ProfileDependency:
    """A successfully linked Profile-owned file (and optional heading)."""

    kind: str
    owner_id: str
    path: str
    absolute_path: str
    heading: Optional[str]
    source: SourceCell


@dataclass(frozen=True)
class DependencyEdge:
    """Canonical semantic edge used by the contract fingerprint."""

    kind: str
    owner_id: str
    target_id: Optional[str] = None
    path: Optional[str] = None
    fragment: Optional[str] = None


@dataclass(frozen=True)
class ExtensionDimension:
    dimension_id: str
    targets: Tuple[str, ...]
    meaning: str
    source: SourceCell


@dataclass(frozen=True)
class JudgmentItem:
    judgment_item_id: str
    dimension_id: str
    audit_layer: str
    audit_object: str
    evidence_role: str
    predicate_owner: Optional[ProfileDependency]
    source: SourceCell


@dataclass(frozen=True)
class RegisteredScan:
    scan_id: str
    activation_role: str
    scope: str
    command_text: str
    command_tokens: Tuple[str, ...]
    script_repo_path: Optional[str]
    script_absolute_path: Optional[str]
    config_dependency: Optional[ProfileDependency]
    candidate_predicate: str
    judgment_item_id: str
    required_for_k12_item_6: bool
    source: SourceCell


@dataclass(frozen=True)
class ProfileContract:
    root: str
    manifest_path: str
    manifest_repo_path: str
    profile_root: str
    profile_repo_dir: str
    audit_registry_path: Optional[str]
    scan_registry_path: Optional[str]
    extension_registration: Optional[str]
    extension_dimensions: Tuple[ExtensionDimension, ...]
    judgment_items: Tuple[JudgmentItem, ...]
    registered_scans: Tuple[RegisteredScan, ...]
    dependency_edges: Tuple[DependencyEdge, ...]
    source_cells: Tuple[SourceCell, ...]
    diagnostics: Tuple[Diagnostic, ...]

    @property
    def authorized(self):
        return not self.diagnostics

    @property
    def required_scan(self):
        selected = tuple(
            scan for scan in self.registered_scans
            if scan.required_for_k12_item_6
        )
        return selected[0] if len(selected) == 1 else None

    @property
    def profile_contract_fingerprint(self):
        """Fingerprint only a fully authorized typed dependency graph."""
        if not self.authorized:
            return None
        value = {
            "schema_version": 1,
            "manifest": self.manifest_repo_path,
            "profile_dir": self.profile_repo_dir,
            "edges": [
                {
                    "kind": edge.kind,
                    "owner_id": edge.owner_id,
                    "target_id": edge.target_id,
                    "path": edge.path,
                    "fragment": edge.fragment,
                }
                for edge in self.dependency_edges
            ],
        }
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @property
    def fingerprint(self):
        return self.profile_contract_fingerprint


@dataclass(frozen=True)
class _Section:
    heading: str
    line: int
    lines: Tuple[Tuple[int, str], ...]


@dataclass(frozen=True)
class _TableRow:
    line: int
    cells: Tuple[str, ...]


def _repo_relative(root, path):
    root_real = os.path.realpath(os.path.abspath(os.fspath(root)))
    path_absolute = os.path.abspath(os.fspath(path))
    path_real = os.path.realpath(path_absolute)
    try:
        inside = os.path.commonpath((root_real, path_real)) == root_real
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("path resolves outside the repository root")
    # macOS exposes the temporary tree through both ``/var`` and
    # ``/private/var``.  Relativize canonical endpoints, not their display
    # aliases, or an actually contained absolute path appears to escape.
    relative = os.path.relpath(path_real, root_real).replace(os.sep, "/")
    if relative == "." or relative.startswith("../"):
        raise ValueError("path is not a repository file")
    return relative


def _strict_read(path):
    return Path(path).read_text(encoding="utf-8", errors="strict")


def _canonical_repository_relative_path(relative_path):
    """Validate and return one canonical repository-relative spelling."""
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("path must be a non-empty string")
    if relative_path != relative_path.strip():
        raise ValueError("path must not have leading or trailing whitespace")
    if "\\" in relative_path:
        raise ValueError("path must use canonical `/` separators")
    if "\x00" in relative_path:
        raise ValueError("path must not contain NUL")
    if os.path.isabs(relative_path):
        raise ValueError("path must be repository-relative")
    parts = relative_path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("path must not contain empty, `.` or `..` segments")
    if "/".join(parts) != relative_path:
        raise ValueError("path must use canonical repository-relative spelling")
    return relative_path


def _canonical_repository_file(root, relative_path, *, singly_linked=False):
    """Resolve one canonical repo-relative regular file without symlinks."""
    relative_path = _canonical_repository_relative_path(relative_path)
    return kblib.canonical_repository_file(
        root, relative_path, singly_linked=singly_linked)


def _blank_fenced_lines(text):
    """Return visible authority lines using the shared Markdown scanner."""
    return kblib.markdown_authority_lines(text)


def _sections(text):
    sections = []
    current_heading = None
    current_line = 0
    current_body = []
    for line_number, line in _blank_fenced_lines(text):
        heading = kblib.markdown_atx_heading(line)
        if heading is not None and heading[0] <= 2:
            if current_heading is not None:
                sections.append(_Section(
                    current_heading, current_line, tuple(current_body)))
            current_heading = (
                heading[1] if heading[0] == 2 else None
            )
            current_line = line_number
            current_body = []
            continue
        if current_heading is not None:
            current_body.append((line_number, line))
    if current_heading is not None:
        sections.append(_Section(
            current_heading, current_line, tuple(current_body)))
    return tuple(sections)


def _split_pipe_row(line):
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return ()
    return tuple(
        cell.replace("\\|", "|").strip()
        for cell in re.split(r"(?<!\\)\|", stripped[1:-1])
    )


def _table_groups(section):
    groups = []
    current = []
    for line_number, line in section.lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current.append(_TableRow(line_number, _split_pipe_row(line)))
        else:
            if current:
                groups.append(tuple(current))
                current = []
    if current:
        groups.append(tuple(current))
    return tuple(groups)


def _literal(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "`":
        return value[1:-1].strip()
    return value


class _Builder:
    def __init__(self, root, manifest_path, sentinel):
        self.root_input = os.path.abspath(os.fspath(root))
        self.root = os.path.realpath(os.path.abspath(os.fspath(root)))
        self.manifest_input = os.fspath(manifest_path)
        self.sentinel = sentinel
        self.diagnostics = []
        self.source_cells = []
        self.edges = []
        self.profile_snapshot = None

    def add(self, check, target, details, source=None):
        if (check == "profile-contract-sentinel" and any(
                item.check == check and item.target == target
                for item in self.diagnostics)):
            return
        self.diagnostics.append(Diagnostic(check, target, details, source))

    def scan_text_sentinel(self, text, source_path, owner):
        """Bind unfilled markers in every strict-UTF-8 authority file.

        Profile-owned dependencies are not allowed to hide a template marker
        behind an uncommon filename suffix.  The outer checker may scan more
        human-facing text for diagnostics, but authorization is decided from
        every file the typed closure actually reads.
        """
        if not self.sentinel:
            return
        for line_number, line in enumerate(text.splitlines(), 1):
            if self.sentinel not in line:
                continue
            source = SourceCell(
                source_path, "Profile dependency closure", line_number, 0,
                owner, line.strip())
            self.source_cells.append(source)
            self.add(
                "profile-contract-sentinel", source.target,
                "%s contains the unfilled sentinel %r" %
                (owner, self.sentinel), source)

    def read_profile_text(self, repository_relative_path):
        if self.profile_snapshot is None:
            raise OSError(errno.EINVAL,
                          "Profile snapshot is not bound")
        return self.profile_snapshot.read_text(repository_relative_path)

    def section(self, text, heading, source_path, prefix):
        matches = [item for item in _sections(text) if item.heading == heading]
        if len(matches) != 1:
            self.add(
                "%s-section-count" % prefix,
                source_path,
                "expected exactly one `## %s` section; found %d" %
                (heading, len(matches)),
            )
            return None
        return matches[0]

    def table(self, section, header, source_path, prefix):
        groups = _table_groups(section)
        if len(groups) != 1:
            self.add(
                "%s-table-count" % prefix,
                source_path,
                "expected exactly one Markdown table in `## %s`; found %d" %
                (section.heading, len(groups)),
            )
            return ()
        rows = groups[0]
        if len(rows) < 2:
            self.add(
                "%s-table-shape" % prefix,
                "%s:%d" % (source_path, rows[0].line),
                "table must contain a header and separator row",
            )
            return ()
        if rows[0].cells != tuple(header):
            self.add(
                "%s-table-header" % prefix,
                "%s:%d" % (source_path, rows[0].line),
                "table header must be exactly `%s`; found `%s`" %
                (" | ".join(header), " | ".join(rows[0].cells)),
            )
        separator = rows[1].cells
        if len(separator) != len(header) or not all(
                TABLE_SEPARATOR_RE.fullmatch(cell.replace(" ", ""))
                for cell in separator):
            self.add(
                "%s-table-separator" % prefix,
                "%s:%d" % (source_path, rows[1].line),
                "table separator must contain exactly %d canonical cells" %
                len(header),
            )
        return rows[2:]

    def cells(self, row, header, source_path, section, row_number, prefix):
        if len(row.cells) != len(header):
            self.add(
                "%s-row-shape" % prefix,
                "%s:%d" % (source_path, row.line),
                "data row %d must contain exactly %d cells; found %d" %
                (row_number, len(header), len(row.cells)),
            )
            return None
        cells = tuple(
            SourceCell(source_path, section, row.line, row_number,
                       header[index], value)
            for index, value in enumerate(row.cells)
        )
        self.source_cells.extend(cells)
        if any(self.sentinel and self.sentinel in cell.raw for cell in cells):
            source = next(
                cell for cell in cells
                if self.sentinel and self.sentinel in cell.raw)
            self.add(
                "profile-contract-sentinel", source.target,
                "data row %d contains the unfilled sentinel %r; dependent "
                "parsing is suppressed" % (row_number, self.sentinel),
                source,
            )
            return None
        empty = [cell for cell in cells if not cell.raw.strip()]
        if empty:
            source = empty[0]
            self.add(
                "%s-row-empty" % prefix, source.target,
                "data row %d has an empty `%s` cell" %
                (row_number, source.field), source,
            )
            return None
        return cells

    def profile_dependency(self, kind, owner_id, raw, source,
                           profile_repo_dir, require_heading=False):
        literal = _literal(raw)
        path_value, marker, heading = literal.partition("#")
        path_value = path_value.strip()
        heading = heading.strip() if marker else None
        if marker and not heading:
            self.add(
                "%s-heading-empty" % kind, source.target,
                "%s %r has an empty heading fragment" % (kind, literal),
                source,
            )
            return None
        if require_heading and not heading:
            self.add(
                "%s-heading-missing" % kind, source.target,
                "%s %r must include a `#heading` fragment" % (kind, literal),
                source,
            )
            return None
        try:
            _canonical_repository_relative_path(path_value)
        except ValueError as exc:
            self.add(
                "%s-path-invalid" % kind, source.target,
                "%s %r is not a canonical repository-relative path: "
                "%s" % (kind, path_value, exc), source,
            )
            return None

        expected_prefix = profile_repo_dir + "/"
        if not path_value.startswith(expected_prefix):
            self.add(
                "%s-path-outside-profile" % kind, source.target,
                "%s %r must stay inside selected Profile directory `%s/`" %
                (kind, path_value, profile_repo_dir), source,
            )
            return None

        try:
            absolute = _canonical_repository_file(
                self.root, path_value, singly_linked=True)
        except (OSError, ValueError) as exc:
            self.add(
                "%s-path-invalid" % kind, source.target,
                "%s %r is not a canonical repository-relative regular file: "
                "%s" % (kind, path_value, exc), source,
            )
            return None

        profile_absolute = os.path.join(
            self.root, *profile_repo_dir.split("/"))
        try:
            inside = os.path.commonpath((
                os.path.realpath(profile_absolute), os.path.realpath(absolute)
            )) == os.path.realpath(profile_absolute)
        except ValueError:
            inside = False
        if not inside:
            self.add(
                "%s-path-outside-profile" % kind, source.target,
                "%s %r resolves outside selected Profile directory `%s/`" %
                (kind, path_value, profile_repo_dir), source,
            )
            return None

        try:
            target_text = self.read_profile_text(path_value)
        except (OSError, UnicodeError) as exc:
            self.add(
                "%s-unreadable" % kind, source.target,
                "cannot read %s %r as strict UTF-8: %s" %
                (kind, path_value, exc), source,
            )
            return None

        self.scan_text_sentinel(
            target_text, path_value, "%s `%s`" % (kind, owner_id))

        if heading is not None:
            if not path_value.lower().endswith(".md"):
                self.add(
                    "%s-heading-non-markdown" % kind, source.target,
                    "%s %r has a heading fragment but does not name Markdown" %
                    (kind, literal), source,
                )
                return None
            matches = [
                line_number for line_number, _level, title in
                kblib.headings_of("\n".join(
                    line for _number, line in _blank_fenced_lines(target_text)))
                if title == heading
            ]
            if len(matches) != 1:
                self.add(
                    "%s-heading-count" % kind, source.target,
                    "%s %r must resolve to exactly one Markdown heading; "
                    "found %d" % (kind, literal, len(matches)), source,
                )
                return None

        dependency = ProfileDependency(
            kind, owner_id, path_value, absolute, heading, source)
        self.edges.append(DependencyEdge(
            kind=kind,
            owner_id=owner_id,
            path=path_value,
            fragment=heading,
        ))
        return dependency


def _manifest_location(root, manifest_path):
    root_display = os.path.abspath(os.fspath(root))
    root_real = os.path.realpath(root_display)
    value = os.fspath(manifest_path)
    if os.path.isabs(value):
        display_absolute = os.path.abspath(value)
        try:
            lexically_inside = os.path.commonpath(
                (root_display, display_absolute)) == root_display
        except ValueError:
            lexically_inside = False
        if lexically_inside:
            relative = os.path.relpath(
                display_absolute, root_display).replace(os.sep, "/")
        else:
            # Permit equivalent system aliases such as /var and /private/var,
            # but still derive one canonical repository-relative spelling.
            relative = _repo_relative(root_real, display_absolute)
        absolute = _canonical_repository_file(root_real, relative)
    else:
        absolute = _canonical_repository_file(root_real, value)
        relative = value
    return root_real, absolute, relative


def _slot_source(manifest_text, manifest_repo_path, slot_name):
    pattern = re.compile(r"^\s*-\s+`%s`\s*:" % re.escape(slot_name))
    for line_number, line in enumerate(
            _blank_fenced_lines(manifest_text), 1):
        # _blank_fenced_lines already carries source numbers.
        actual_line, value = line
        if pattern.match(value):
            return SourceCell(
                manifest_repo_path, "Implemented Slots", actual_line, 0,
                slot_name, value.strip())
    return None


def _load_bound_slot(builder, manifest_text, manifest_path,
                     manifest_repo_path, profile_root, slot_name):
    bindings, duplicates = kblib.profile_slot_bindings(
        manifest_text, include_duplicates=True)
    if slot_name in duplicates:
        builder.add(
            "profile-contract-slot-duplicate", manifest_repo_path,
            "Implemented Slots repeats `%s`" % slot_name,
            _slot_source(manifest_text, manifest_repo_path, slot_name),
        )
        return None, None
    binding = bindings.get(slot_name)
    if not binding:
        builder.add(
            "profile-contract-slot-missing", manifest_repo_path,
            "Implemented Slots has no `%s` binding" % slot_name,
        )
        return None, None
    source = _slot_source(manifest_text, manifest_repo_path, slot_name)
    if builder.sentinel and builder.sentinel in binding:
        builder.add(
            "profile-contract-sentinel",
            source.target if source else manifest_repo_path,
            "`%s` binding contains the unfilled sentinel %r" %
            (slot_name, builder.sentinel), source,
        )
        return None, None
    kind, resolved = kblib.resolve_profile_binding(
        binding, builder.root, profile_root)
    if kind != "path":
        check = ("profile-contract-slot-invalid" if kind == "invalid" else
                 "profile-contract-slot-unresolved")
        builder.add(
            check,
            source.target if source else manifest_repo_path,
            "`%s` binding must resolve to a file inside the selected Profile; "
            "resolver returned %s (%r)" % (slot_name, kind, resolved), source,
        )
        return None, None
    try:
        relative = os.path.relpath(
            os.path.abspath(resolved), builder.root).replace(os.sep, "/")
        if relative == "." or relative.startswith("../"):
            raise ValueError("slot path is outside the repository root")
        absolute = _canonical_repository_file(
            builder.root, relative, singly_linked=True)
    except (OSError, ValueError) as exc:
        builder.add(
            "profile-contract-slot-invalid",
            source.target if source else manifest_repo_path,
            "`%s` binding is not a canonical regular Profile file: %s" %
            (slot_name, exc), source,
        )
        return None, None
    profile_repo_dir = _repo_relative(builder.root, profile_root)
    if not relative.startswith(profile_repo_dir + "/"):
        builder.add(
            "profile-contract-slot-outside-profile",
            source.target if source else manifest_repo_path,
            "`%s` binding resolves outside `%s/`" %
            (slot_name, profile_repo_dir), source,
        )
        return None, None
    try:
        text = builder.read_profile_text(relative)
    except (OSError, UnicodeError) as exc:
        builder.add(
            "profile-contract-slot-unreadable", relative,
            "cannot read `%s` as strict UTF-8: %s" % (relative, exc), source,
        )
        return relative, None
    builder.scan_text_sentinel(text, relative, "slot `%s`" % slot_name)
    return relative, text


def _parse_extensions(builder, text, source_path):
    section = builder.section(
        text, EXTENSION_SECTION, source_path, "extension-dimensions")
    if section is None:
        return None, ()

    declarations = []
    for line_number, line in section.lines:
        match = REGISTRATION_RE.match(line)
        if match:
            declarations.append((line_number, match.group(1).strip()))
    registration = None
    if len(declarations) != 1:
        builder.add(
            "extension-dimensions-registration", source_path,
            "expected exactly one `- Registration:` declaration; found %d" %
            len(declarations),
        )
    else:
        line_number, raw = declarations[0]
        source = SourceCell(
            source_path, EXTENSION_SECTION, line_number, 0,
            "Registration", raw)
        builder.source_cells.append(source)
        if builder.sentinel and builder.sentinel in raw:
            builder.add(
                "profile-contract-sentinel", source.target,
                "Extension Dimensions registration contains the unfilled "
                "sentinel %r" % builder.sentinel, source,
            )
        elif raw not in ("None", "Configured"):
            builder.add(
                "extension-dimensions-registration", source.target,
                "Registration must be exactly `None` or `Configured`; found %r"
                % raw, source,
            )
        else:
            registration = raw

    rows = builder.table(
        section, EXTENSION_HEADER, source_path, "extension-dimensions")
    parsed = []
    seen = set()
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, EXTENSION_HEADER, source_path, EXTENSION_SECTION,
            row_number, "extension-dimensions")
        if cells is None:
            continue
        dimension_id = _literal(cells[0].raw)
        target_literal = _literal(cells[1].raw)
        valid = True
        if not DIMENSION_ID_RE.fullmatch(dimension_id):
            builder.add(
                "extension-dimension-id-invalid", cells[0].target,
                "Dimension ID %r must be lower_snake_case starting with a "
                "letter" % dimension_id, cells[0])
            valid = False
        if dimension_id in seen:
            builder.add(
                "extension-dimension-id-duplicate", cells[0].target,
                "Dimension ID %r is registered more than once" % dimension_id,
                cells[0])
            valid = False
        seen.add(dimension_id)
        if dimension_id in BASE_DIMENSIONS:
            builder.add(
                "extension-dimension-base-collision", cells[0].target,
                "Dimension ID %r redefines a base receipt dimension" %
                dimension_id, cells[0])
            valid = False
        targets = EXTENSION_TARGETS.get(target_literal)
        if targets is None:
            builder.add(
                "extension-dimension-target-invalid", cells[1].target,
                "target must be exactly `review`, `receipt`, or "
                "`review + receipt`; found %r" % target_literal, cells[1])
            valid = False
            targets = ()
        if valid:
            parsed.append(ExtensionDimension(
                dimension_id, tuple(targets), cells[2].raw.strip(), cells[0]))

    if registration == "None" and rows:
        builder.add(
            "extension-dimensions-none-with-rows", source_path,
            "`Registration: None` requires an empty registration table; "
            "found %d data row(s)" % len(rows),
        )
    if registration == "Configured" and not rows:
        builder.add(
            "extension-dimensions-configured-empty", source_path,
            "`Registration: Configured` requires at least one data row",
        )
    return registration, tuple(parsed)


def _parse_judgments(builder, text, source_path, profile_repo_dir,
                     extension_dimensions):
    section = builder.section(
        text, JUDGMENT_SECTION, source_path, "judgment-items")
    if section is None:
        return ()
    rows = builder.table(
        section, JUDGMENT_HEADER, source_path, "judgment-items")
    if not rows:
        builder.add(
            "judgment-items-empty", source_path,
            "Judgment Items requires at least one data row",
        )
    known_dimensions = BASE_DIMENSIONS.union(
        dimension.dimension_id for dimension in extension_dimensions)
    parsed = []
    seen = set()
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, JUDGMENT_HEADER, source_path, JUDGMENT_SECTION,
            row_number, "judgment-items")
        if cells is None:
            continue
        item_id = _literal(cells[0].raw)
        dimension_id = _literal(cells[1].raw)
        evidence_role = _literal(cells[4].raw)
        valid = True
        if not STABLE_ID_RE.fullmatch(item_id):
            builder.add(
                "judgment-item-id-invalid", cells[0].target,
                "Stable Judgment Item ID %r must be lowercase kebab-case" %
                item_id, cells[0])
            valid = False
        if item_id in seen:
            builder.add(
                "judgment-item-id-duplicate", cells[0].target,
                "Stable Judgment Item ID %r is registered more than once" %
                item_id, cells[0])
            valid = False
        seen.add(item_id)
        if dimension_id not in known_dimensions:
            builder.add(
                "judgment-item-dimension-unknown", cells[1].target,
                "Dimension ID %r is neither a base dimension nor a valid "
                "registered extension" % dimension_id, cells[1])
            valid = False
        if evidence_role not in EVIDENCE_ROLES:
            builder.add(
                "judgment-item-evidence-role-invalid", cells[4].target,
                "Evidence role must be `emits`, `consumes`, or `triggers`; "
                "found %r" % evidence_role, cells[4])
            valid = False
        dependency = builder.profile_dependency(
            "predicate-owner", item_id, cells[5].raw, cells[5],
            profile_repo_dir)
        if dependency is None:
            valid = False
        parsed.append(JudgmentItem(
            item_id, dimension_id, _literal(cells[2].raw),
            cells[3].raw.strip(), evidence_role, dependency, cells[0]))
        # Keep diagnostic IR even when invalid; authorization never consumes it.
        if not valid:
            continue
    return tuple(parsed)


def _option_values(tokens, option):
    values = []
    errors = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == option:
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                errors.append("%s requires a non-empty value" % option)
            else:
                values.append(tokens[index + 1])
                index += 1
        elif token.startswith(option + "="):
            value = token[len(option) + 1:]
            if not value:
                errors.append("%s requires a non-empty value" % option)
            else:
                values.append(value)
        index += 1
    return tuple(values), tuple(errors)


def _command_spec(builder, scan_id, command_raw, source, profile_repo_dir):
    command_text = _literal(command_raw)
    if "`" in command_text:
        builder.add(
            "registered-scan-command-literal", source.target,
            "verifier command must be one bare or fully backtick-wrapped "
            "command literal", source)
        return command_text, (), None, None, None
    if "--config" in command_text and "\\" in command_text:
        # POSIX shlex treats backslash as an escape and would erase the
        # evidence before the path resolver sees it.  Refuse the source
        # spelling itself so a Windows-style alias cannot become a different
        # apparently canonical argv value.
        builder.add(
            "scan-config-path-invalid", source.target,
            "scan-config command spelling must use canonical `/` separators",
            source)
    try:
        tokens = tuple(shlex.split(command_text, posix=True))
    except ValueError as exc:
        builder.add(
            "registered-scan-command-parse", source.target,
            "cannot parse verifier command: %s" % exc, source)
        return command_text, (), None, None, None
    if len(tokens) < 3:
        builder.add(
            "registered-scan-command-shape", source.target,
            "verifier command must contain interpreter, Tools script, and `.`",
            source)
        return command_text, tokens, None, None, None
    if os.path.basename(tokens[0]) not in ("python", "python3"):
        builder.add(
            "registered-scan-command-interpreter", source.target,
            "registered verifier must use a `python` or `python3` interpreter",
            source)
    script_repo_path = tokens[1]
    script_absolute_path = None
    if not (script_repo_path.startswith("Tools/") and
            script_repo_path.endswith(".py")):
        builder.add(
            "registered-scan-command-script", source.target,
            "registered verifier must name a canonical repository "
            "`Tools/*.py` script; found %r" % script_repo_path, source)
    else:
        try:
            script_absolute_path = _canonical_repository_file(
                builder.root, script_repo_path, singly_linked=True)
        except (OSError, ValueError) as exc:
            builder.add(
                "registered-scan-command-script", source.target,
                "registered verifier script %r is invalid: %s" %
                (script_repo_path, exc), source)
    if tokens[2] != ".":
        builder.add(
            "registered-scan-command-root", source.target,
            "registered verifier must bind the whole repository root as `.`",
            source)
    operators = sorted(SHELL_OPERATORS.intersection(tokens))
    if operators:
        builder.add(
            "registered-scan-command-shell-operator", source.target,
            "registered verifier command contains shell operator(s): %s" %
            ", ".join(operators), source)
    for option in ("--receipts", "--positive-controls-only"):
        if any(token == option or token.startswith(option + "=")
               for token in tokens):
            builder.add(
                "registered-scan-command-gate-option", source.target,
                "registered verifier command must leave `%s` to the gate" %
                option, source)

    scan_ids, scan_id_errors = _option_values(tokens[3:], "--scan-id")
    for details in scan_id_errors:
        builder.add("registered-scan-command-scan-id", source.target,
                    details, source)
    if len(scan_ids) != 1:
        builder.add(
            "registered-scan-command-scan-id", source.target,
            "verifier command must contain exactly one `--scan-id`; found %d" %
            len(scan_ids), source)
    elif scan_ids[0] != scan_id:
        builder.add(
            "registered-scan-command-scan-id", source.target,
            "command `--scan-id` %r does not match Stable Scan ID %r" %
            (scan_ids[0], scan_id), source)

    configs, config_errors = _option_values(tokens[3:], "--config")
    for details in config_errors:
        builder.add("registered-scan-command-config", source.target,
                    details, source)
    if len(configs) > 1:
        builder.add(
            "registered-scan-command-config", source.target,
            "verifier command may contain at most one `--config`; found %d" %
            len(configs), source)
    bundled = script_repo_path == "Tools/check_residual_content.py"
    if bundled and len(configs) != 1:
        builder.add(
            "registered-scan-command-config", source.target,
            "Tools/check_residual_content.py requires exactly one `--config`; "
            "found %d" % len(configs), source)
    config_dependency = None
    if len(configs) == 1:
        config_dependency = builder.profile_dependency(
            "scan-config", scan_id, configs[0], source, profile_repo_dir)

    if script_repo_path and script_absolute_path:
        builder.edges.append(DependencyEdge(
            kind="verifier-tool", owner_id=scan_id, path=script_repo_path))
    return (command_text, tokens, script_repo_path,
            script_absolute_path, config_dependency)


def _parse_scans(builder, text, source_path, profile_repo_dir):
    section = builder.section(
        text, SCAN_SECTION, source_path, "registered-scans")
    if section is None:
        return ()
    rows = builder.table(
        section, SCAN_HEADER, source_path, "registered-scans")
    if not rows:
        builder.add(
            "registered-scans-empty", source_path,
            "Scan Registrations requires at least one data row",
        )
    parsed = []
    seen = set()
    suppressed = False
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, SCAN_HEADER, source_path, SCAN_SECTION,
            row_number, "registered-scans")
        if cells is None:
            if any(builder.sentinel and builder.sentinel in value
                   for value in row.cells):
                suppressed = True
            continue
        scan_id = _literal(cells[0].raw)
        activation = _literal(cells[1].raw)
        if not STABLE_ID_RE.fullmatch(scan_id):
            builder.add(
                "registered-scan-id-invalid", cells[0].target,
                "Stable Scan ID %r must be lowercase kebab-case" % scan_id,
                cells[0])
        if scan_id in seen:
            builder.add(
                "registered-scan-id-duplicate", cells[0].target,
                "Stable Scan ID %r is registered more than once" % scan_id,
                cells[0])
        seen.add(scan_id)
        command = _command_spec(
            builder, scan_id, cells[3].raw, cells[3], profile_repo_dir)
        required = bool(REQUIRED_SCAN_RE.search(activation))
        parsed.append(RegisteredScan(
            scan_id=scan_id,
            activation_role=activation,
            scope=cells[2].raw.strip(),
            command_text=command[0],
            command_tokens=command[1],
            script_repo_path=command[2],
            script_absolute_path=command[3],
            config_dependency=command[4],
            candidate_predicate=cells[4].raw.strip(),
            judgment_item_id=_literal(cells[5].raw),
            required_for_k12_item_6=required,
            source=cells[0],
        ))
    required = [scan for scan in parsed if scan.required_for_k12_item_6]
    if len(required) != 1 and not suppressed:
        builder.add(
            "registered-scans-required-count", source_path,
            "Scan Registrations must contain exactly one K12/09 item 6 row; "
            "found %d" % len(required),
        )
    return tuple(parsed)


def _empty_contract(builder, manifest_path="", manifest_repo_path="",
                    profile_root="", profile_repo_dir=""):
    return ProfileContract(
        root=builder.root,
        manifest_path=manifest_path,
        manifest_repo_path=manifest_repo_path,
        profile_root=profile_root,
        profile_repo_dir=profile_repo_dir,
        audit_registry_path=None,
        scan_registry_path=None,
        extension_registration=None,
        extension_dimensions=(),
        judgment_items=(),
        registered_scans=(),
        dependency_edges=(),
        source_cells=tuple(builder.source_cells),
        diagnostics=tuple(builder.diagnostics),
    )


def load_profile_contract(root, manifest_path, sentinel="TODO(profile)",
                          profile_snapshot=None):
    """Load and link the machine-active contract of one Profile manifest.

    The return value always contains deterministic diagnostics and any safely
    parsed partial IR.  Only ``contract.authorized`` may be consumed as runtime
    authority.  Callers must not infer authorization from the presence of a
    row or dependency in an unauthorized contract.
    """
    builder = _Builder(root, manifest_path, sentinel)
    try:
        root_real, manifest_absolute, manifest_relative = _manifest_location(
            builder.root_input, manifest_path)
    except (OSError, ValueError) as exc:
        builder.add(
            "profile-contract-manifest-path", os.fspath(manifest_path),
            "manifest path is invalid: %s" % exc,
        )
        return _empty_contract(builder)
    builder.root = root_real
    profile_root = os.path.dirname(manifest_absolute)
    try:
        profile_repo_dir = _repo_relative(builder.root, profile_root)
    except ValueError as exc:
        builder.add(
            "profile-contract-profile-root", manifest_relative,
            "selected Profile directory is invalid: %s" % exc,
        )
        return _empty_contract(
            builder, manifest_absolute, manifest_relative, profile_root)

    try:
        if profile_snapshot is None:
            profile_snapshot = kblib.repository_tree_snapshot(
                builder.root, profile_repo_dir)
        if (os.path.realpath(profile_snapshot.root) != builder.root or
                profile_snapshot.relative_directory != profile_repo_dir):
            raise ValueError(
                "supplied Profile snapshot does not bind %s under this root" %
                profile_repo_dir)
        builder.profile_snapshot = profile_snapshot
    except (OSError, ValueError) as exc:
        builder.add(
            "profile-contract-snapshot-invalid", manifest_relative,
            "cannot bind one immutable Profile byte snapshot: %s" % exc,
        )
        return _empty_contract(
            builder, manifest_absolute, manifest_relative,
            profile_root, profile_repo_dir)

    if os.path.basename(manifest_absolute) != "profile.md":
        builder.add(
            "profile-contract-manifest-name", manifest_relative,
            "Profile manifest must be named `profile.md`",
        )
    try:
        canonical_manifest = _canonical_repository_file(
            builder.root, manifest_relative, singly_linked=True)
        manifest_text = builder.read_profile_text(manifest_relative)
    except (OSError, UnicodeError, ValueError) as exc:
        builder.add(
            "profile-contract-manifest-unreadable", manifest_relative,
            "cannot read Profile manifest as a canonical strict UTF-8 regular "
            "file: %s" % exc,
        )
        return _empty_contract(
            builder, manifest_absolute, manifest_relative,
            profile_root, profile_repo_dir)
    builder.scan_text_sentinel(
        manifest_text, manifest_relative, "Profile manifest")

    audit_path, audit_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, AUDIT_SLOT)
    scan_path, scan_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, SCAN_SLOT)

    # Bind every declared first-hop file, not only the two registries whose
    # contents this linker interprets transitively.  ``check_profile`` owns the
    # exact 13-slot cardinality; this layer owns the canonical path and typed
    # edge of each declared interface slot so the contract fingerprint cannot
    # omit the rest of the package graph.
    if audit_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=AUDIT_SLOT, path=audit_path))
    if scan_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=SCAN_SLOT, path=scan_path))
    bindings, duplicate_bindings = kblib.profile_slot_bindings(
        manifest_text, include_duplicates=True)
    for slot_name in PROFILE_FILE_SLOTS:
        if slot_name in (AUDIT_SLOT, SCAN_SLOT):
            continue
        if slot_name in duplicate_bindings:
            source = _slot_source(
                manifest_text, manifest_relative, slot_name)
            builder.add(
                "profile-contract-slot-duplicate",
                source.target if source else manifest_relative,
                "Implemented Slots repeats `%s`" % slot_name, source)
            continue
        binding = bindings.get(slot_name)
        if binding is None:
            builder.add(
                "profile-contract-slot-missing", manifest_relative,
                "Implemented Slots has no `%s` binding" % slot_name)
            continue
        source = _slot_source(manifest_text, manifest_relative, slot_name)
        if sentinel and sentinel in binding:
            builder.add(
                "profile-contract-sentinel",
                source.target if source else manifest_relative,
                "`%s` binding contains the unfilled sentinel %r" %
                (slot_name, sentinel), source)
            continue
        kind, resolved = kblib.resolve_profile_binding(
            binding, builder.root, profile_root)
        if kind != "path":
            builder.add(
                "profile-contract-slot-invalid",
                source.target if source else manifest_relative,
                "`%s` binding is not one canonical file inside the selected "
                "Profile: resolver returned %s (%r)" %
                (slot_name, kind, resolved), source)
            continue
        try:
            relative = os.path.relpath(
                os.path.abspath(resolved), builder.root).replace(os.sep, "/")
            slot_text = builder.read_profile_text(relative)
        except (OSError, UnicodeError) as exc:
            builder.add(
                "profile-contract-slot-unreadable",
                source.target if source else manifest_relative,
                "`%s` binding cannot be read as strict UTF-8: %s" %
                (slot_name, exc), source)
            continue
        builder.scan_text_sentinel(
            slot_text, relative, "slot `%s`" % slot_name)
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=slot_name, path=relative))

    registration = None
    dimensions = ()
    judgments = ()
    scans = ()
    if audit_text is not None:
        registration, dimensions = _parse_extensions(
            builder, audit_text, audit_path)
        judgments = _parse_judgments(
            builder, audit_text, audit_path, profile_repo_dir, dimensions)
    if scan_text is not None:
        scans = _parse_scans(
            builder, scan_text, scan_path, profile_repo_dir)

    judgment_ids = {}
    for item in judgments:
        judgment_ids.setdefault(item.judgment_item_id, []).append(item)
    for scan in scans:
        matches = judgment_ids.get(scan.judgment_item_id, ())
        if len(matches) != 1:
            builder.add(
                "registered-scan-judgment-reference", scan.source.target,
                "scan %r Judgment Item reference %r must resolve exactly once; "
                "found %d" %
                (scan.scan_id, scan.judgment_item_id, len(matches)), scan.source,
            )
        else:
            builder.edges.append(DependencyEdge(
                kind="scan-judgment",
                owner_id=scan.scan_id,
                target_id=scan.judgment_item_id,
            ))

    edges = tuple(sorted(
        builder.edges,
        key=lambda edge: (
            edge.kind, edge.owner_id, edge.target_id or "",
            edge.path or "", edge.fragment or ""),
    ))
    return ProfileContract(
        root=builder.root,
        manifest_path=manifest_absolute,
        manifest_repo_path=manifest_relative,
        profile_root=profile_root,
        profile_repo_dir=profile_repo_dir,
        audit_registry_path=audit_path,
        scan_registry_path=scan_path,
        extension_registration=registration,
        extension_dimensions=tuple(dimensions),
        judgment_items=tuple(judgments),
        registered_scans=tuple(scans),
        dependency_edges=edges,
        source_cells=tuple(builder.source_cells),
        diagnostics=tuple(builder.diagnostics),
    )


def format_diagnostics(diagnostics):
    """Render diagnostics without losing their stable check identifiers."""
    return "; ".join(
        "%s [%s]: %s" %
        (diagnostic.check, diagnostic.target, diagnostic.details)
        for diagnostic in diagnostics
    )


def compile_registered_scan_command(root, contract, scan=None):
    """Compile one authorized scan row to a shell-free subprocess argv.

    ``scan`` defaults to the unique K12/09 item 6 registration.  The root must
    be the same repository root used to link the contract.  Runtime consumers
    append gate-owned arguments such as ``--receipts`` and
    ``--positive-controls-only`` after this function returns.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    supplied_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if supplied_root != contract.root:
        raise ProfileContractError(
            "compile root does not match linked Profile contract root")
    if not contract.authorized:
        raise ProfileContractError(
            "Profile contract is not authorized: %s" %
            format_diagnostics(contract.diagnostics))
    selected = contract.required_scan if scan is None else scan
    if selected is None:
        raise ProfileContractError(
            "Profile contract has no unique K12/09 item 6 registration")
    if selected not in contract.registered_scans:
        raise ProfileContractError(
            "registered scan does not belong to this Profile contract")
    if (not selected.script_absolute_path or
            len(selected.command_tokens) < 3):
        raise ProfileContractError(
            "registered scan has no compiled verifier command")
    return tuple((
        sys.executable,
        selected.script_absolute_path,
        contract.root,
    ) + selected.command_tokens[3:])


__all__ = (
    "DependencyEdge",
    "Diagnostic",
    "ExtensionDimension",
    "JudgmentItem",
    "ProfileContract",
    "ProfileContractError",
    "ProfileDependency",
    "RegisteredScan",
    "SourceCell",
    "compile_registered_scan_command",
    "format_diagnostics",
    "load_profile_contract",
)
