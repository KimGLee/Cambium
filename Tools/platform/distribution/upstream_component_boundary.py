#!/usr/bin/env python3
"""Detect adopter component-byte drift from one exact upstream Git revision.

The upstream Git object database, not the adopter checkout and not a caller
supplied allow-list, owns both inputs to this comparison:

* the component file bytes come from the resolved commit; and
* the only files that may be absent come from that commit's
  ``distribution-boundary.yaml``.

The selected Profile is deliberately outside this byte boundary.  Only the
shared ``profiles/README.md`` is a component; every other ``profiles/`` member
is either adopter-owned configuration or distribution-only authoring material.

This module is read-only.  ``check_upstream_components.py`` owns the optional
write of the resulting manifest into adopter runtime-derived space.

The comparison is a drift detector, not a self-authenticating trust root. It
must be executed from a separately trusted upstream checkout (or an equivalent
protected runner) while ``adopter_root`` names the repository being checked.
Executing an adopter's own unchecked Tool bytes cannot prove those bytes safe.
"""

from dataclasses import dataclass
import hashlib
import os
import re
import stat

import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.platform.distribution.upstream_identity as upstream_identity
from Tools.platform.repository import repository as tool_repository
from Tools.platform.repository import path_contract as repository_path_contract


DEFAULT_MANIFEST_PATH = runtime_paths.UPSTREAM_COMPONENT_MANIFEST_PATH
DISTRIBUTION_BOUNDARY_PATH = "distribution-boundary.yaml"
IMMUTABLE_DIRECTORY_ROOTS = ("kernel", "Card", "Read Set", "Tools")
IMMUTABLE_FILE_PATHS = (
    "profiles/README.md", DISTRIBUTION_BOUNDARY_PATH)
MANIFEST_COLUMNS = (
    "path", "git_blob_oid", "sha256", "presence")
_REGULAR_GIT_MODES = frozenset(("100644", "100755"))
_OID_RE = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


class ComponentBoundaryError(ValueError):
    """The upstream snapshot or adopter tree cannot be checked safely."""


@dataclass(frozen=True)
class ComponentRow:
    path: str
    git_blob_oid: str
    sha256: str
    presence: str


@dataclass(frozen=True)
class ComponentBoundaryReport:
    upstream_revision_id: str
    distribution_boundary_sha256: str
    rows: tuple
    errors: tuple

    @property
    def present_count(self):
        return sum(row.presence == "present" for row in self.rows)

    @property
    def omitted_count(self):
        return sum(
            row.presence == "omitted-distribution-only" for row in self.rows)


def _canonical_path(raw, label):
    try:
        raw = repository_path_contract.canonical_repository_relative_path(
            raw, label)
    except ValueError as exc:
        raise ComponentBoundaryError(str(exc)) from exc
    if ("\\" in raw or "\x00" in raw or
            "\t" in raw or "\n" in raw or "\r" in raw or
            any(part in ("", ".", "..") for part in raw.split("/"))):
        raise ComponentBoundaryError(
            "%s must be a TSV-safe canonical repository path" % label)
    return raw


def _git(upstream_root, arguments, *, input_bytes=None, timeout=60):
    command = ["git", "-C", os.path.abspath(upstream_root)] + list(arguments)
    environment = dict(os.environ)
    # A local replace ref can make Git serve bytes from a different object
    # while the command line still names the recorded commit.  Component
    # identity must follow the commit object itself, never local repair state.
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        completed = kblib.run_cambium_subprocess(
            command, input=input_bytes, stdout=-1, stderr=-1,
            check=False, timeout=timeout, env=environment)
    except OSError as exc:
        raise ComponentBoundaryError("cannot execute Git: %s" % exc) from exc
    except Exception as exc:
        # subprocess.TimeoutExpired inherits SubprocessError rather than
        # OSError.  Do not leak a transport exception as a governance verdict.
        raise ComponentBoundaryError(
            "Git did not complete while reading the upstream revision: %s" %
            exc) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode(
            "utf-8", errors="replace").strip()
        raise ComponentBoundaryError(
            "Git could not read the upstream revision: %s" %
            (detail or "command exited %d" % completed.returncode))
    return completed.stdout


def _tree_entries(upstream_root, revision_id):
    raw = _git(
        upstream_root,
        ["ls-tree", "-r", "-z", "--full-tree", revision_id, "--"] +
        list(IMMUTABLE_DIRECTORY_ROOTS) + list(IMMUTABLE_FILE_PATHS))
    entries = []
    seen = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, encoded_oid = metadata.split(b" ")
            path = encoded_path.decode("utf-8")
            mode = mode.decode("ascii")
            object_type = object_type.decode("ascii")
            oid = encoded_oid.decode("ascii")
        except (ValueError, UnicodeError) as exc:
            raise ComponentBoundaryError(
                "Git returned an unreadable component tree row") from exc
        _canonical_path(path, "upstream component path")
        if path in seen:
            raise ComponentBoundaryError(
                "Git repeated upstream component path %s" % path)
        if object_type != "blob" or mode not in _REGULAR_GIT_MODES:
            raise ComponentBoundaryError(
                "upstream component %s is not a regular Git blob" % path)
        if _OID_RE.fullmatch(oid) is None:
            raise ComponentBoundaryError(
                "upstream component %s has an invalid object ID" % path)
        seen.add(path)
        entries.append((path, oid))

    paths = {path for path, _oid in entries}
    for root in IMMUTABLE_DIRECTORY_ROOTS:
        prefix = root + "/"
        if not any(path.startswith(prefix) for path in paths):
            raise ComponentBoundaryError(
                "upstream revision has no files under required component %s"
                % root)
    for path in IMMUTABLE_FILE_PATHS:
        if path not in paths:
            raise ComponentBoundaryError(
                "upstream revision is missing required component %s" % path)
    return tuple(sorted(entries))


def _blob_bytes(upstream_root, entries):
    unique_oids = tuple(sorted({oid for _path, oid in entries}))
    request = b"".join(oid.encode("ascii") + b"\n" for oid in unique_oids)
    raw = _git(upstream_root, ["cat-file", "--batch"], input_bytes=request)
    cursor = 0
    blobs = {}
    for expected_oid in unique_oids:
        line_end = raw.find(b"\n", cursor)
        if line_end < 0:
            raise ComponentBoundaryError(
                "Git returned a truncated component blob header")
        header = raw[cursor:line_end]
        cursor = line_end + 1
        try:
            encoded_oid, object_type, encoded_size = header.split(b" ")
            oid = encoded_oid.decode("ascii")
            kind = object_type.decode("ascii")
            size = int(encoded_size.decode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise ComponentBoundaryError(
                "Git returned an invalid component blob header") from exc
        if oid != expected_oid or kind != "blob" or size < 0:
            raise ComponentBoundaryError(
                "Git returned the wrong object for component blob %s" %
                expected_oid)
        end = cursor + size
        if end >= len(raw) or raw[end:end + 1] != b"\n":
            raise ComponentBoundaryError(
                "Git returned truncated bytes for component blob %s" % oid)
        blobs[oid] = raw[cursor:end]
        cursor = end + 1
    if cursor != len(raw):
        raise ComponentBoundaryError(
            "Git returned trailing bytes after the component blob batch")
    return blobs


def _distribution_only_paths(boundary_bytes):
    try:
        document = kblib.parse_yaml_subset(boundary_bytes.decode("utf-8"))
    except (UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        raise ComponentBoundaryError(
            "upstream distribution-boundary.yaml is invalid: %s" % exc)
    expected_keys = {"schema_version", "distribution_only"}
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise ComponentBoundaryError(
            "upstream distribution-boundary.yaml fields are not closed")
    if document.get("schema_version") != 1:
        raise ComponentBoundaryError(
            "upstream distribution-boundary.yaml schema_version must be 1")
    entries = document.get("distribution_only")
    if not isinstance(entries, list) or not entries:
        raise ComponentBoundaryError(
            "upstream distribution-boundary.yaml needs distribution_only")
    paths = []
    for index, entry in enumerate(entries):
        label = "distribution_only[%d]" % index
        if not isinstance(entry, dict) or set(entry) != {"path", "reason"}:
            raise ComponentBoundaryError("%s fields are not closed" % label)
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            raise ComponentBoundaryError("%s.path must be a string" % label)
        path = raw_path[:-1] if raw_path.endswith("/") else raw_path
        _canonical_path(path, label + ".path")
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ComponentBoundaryError(
                "%s.reason must be a non-empty string" % label)
        if path in paths:
            raise ComponentBoundaryError(
                "distribution-boundary.yaml repeats %s" % path)
        paths.append(path)
    return tuple(sorted(paths))


def _may_be_omitted(path, distribution_only):
    # The boundary itself cannot grant permission for its own disappearance:
    # without those upstream bytes there would be no authority for any
    # omission.  The required shared Profile guide is treated the same way.
    if path in IMMUTABLE_FILE_PATHS:
        return False
    return any(path == declared or path.startswith(declared + "/")
               for declared in distribution_only)


def _stable_regular_bytes(path):
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_CLOEXEC", 0))
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ComponentBoundaryError(
            "cannot open component as a regular file: %s" % exc) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ComponentBoundaryError("component is not a regular file")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    comparable = lambda value: (
        value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if comparable(before) != comparable(after):
        raise ComponentBoundaryError("component changed while it was read")
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise ComponentBoundaryError(
            "component disappeared after it was read: %s" % exc) from exc
    if comparable(after) != comparable(current):
        raise ComponentBoundaryError(
            "component namespace changed while it was read")
    return b"".join(chunks)


def _component_tree_entries(adopter_root):
    """Return every non-directory entry under immutable directory roots."""
    result = set()
    errors = []
    root = os.path.abspath(adopter_root)
    for component in IMMUTABLE_DIRECTORY_ROOTS:
        absolute = os.path.join(root, component)
        if not os.path.lexists(absolute):
            continue
        try:
            root_stat = os.lstat(absolute)
        except OSError as exc:
            errors.append("cannot inspect component root %s: %s" %
                          (component, exc))
            continue
        if not stat.S_ISDIR(root_stat.st_mode):
            errors.append("component root %s is not a directory" % component)
            result.add(component)
            continue
        for dirpath, dirnames, filenames in os.walk(
                absolute, topdown=True, followlinks=False):
            retained_dirs = []
            for name in sorted(dirnames):
                child = os.path.join(dirpath, name)
                relative = os.path.relpath(child, root).replace(os.sep, "/")
                try:
                    child_stat = os.lstat(child)
                except OSError as exc:
                    errors.append("cannot inspect component path %s: %s" %
                                  (relative, exc))
                    continue
                if stat.S_ISDIR(child_stat.st_mode):
                    retained_dirs.append(name)
                else:
                    result.add(relative)
            dirnames[:] = retained_dirs
            for name in sorted(filenames):
                child = os.path.join(dirpath, name)
                result.add(
                    os.path.relpath(child, root).replace(os.sep, "/"))
    return result, errors


def evaluate(adopter_root, upstream_root, revision_ref):
    """Return the exact component-byte report for one adopter.

    ``revision_ref`` may be a tag, branch, abbreviated object name, or full
    commit.  ``upstream_identity.resolve_revision`` resolves it first, and the
    returned report records only the full commit SHA.
    """
    adopter = os.path.abspath(adopter_root)
    upstream = os.path.abspath(upstream_root)
    if not os.path.isdir(adopter):
        raise ComponentBoundaryError(
            "adopter root is not a directory: %s" % adopter)
    if not os.path.isdir(upstream):
        raise ComponentBoundaryError(
            "upstream root is not a directory: %s" % upstream)
    try:
        revision_id = upstream_identity.resolve_revision(
            upstream, revision_ref)
    except (OSError, ValueError) as exc:
        raise ComponentBoundaryError(
            "cannot resolve upstream revision %r: %s" %
            (revision_ref, exc)) from exc

    entries = _tree_entries(upstream, revision_id)
    blobs = _blob_bytes(upstream, entries)
    by_path = {path: (oid, blobs[oid]) for path, oid in entries}
    boundary_bytes = by_path[DISTRIBUTION_BOUNDARY_PATH][1]
    distribution_only = _distribution_only_paths(boundary_bytes)
    boundary_sha256 = "sha256:" + hashlib.sha256(boundary_bytes).hexdigest()

    rows = []
    errors = []
    for path, oid in entries:
        source_bytes = blobs[oid]
        source_sha = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
        absolute = os.path.join(adopter, *path.split("/"))
        if not os.path.lexists(absolute):
            if _may_be_omitted(path, distribution_only):
                rows.append(ComponentRow(
                    path, oid, source_sha, "omitted-distribution-only"))
            else:
                errors.append("required component is missing: %s" % path)
            continue
        try:
            actual_bytes = _stable_regular_bytes(absolute)
        except ComponentBoundaryError as exc:
            errors.append("unsafe component %s: %s" % (path, exc))
            continue
        if actual_bytes != source_bytes:
            actual_sha = "sha256:" + hashlib.sha256(actual_bytes).hexdigest()
            errors.append(
                "component bytes differ from upstream: %s (expected %s, "
                "found %s)" % (path, source_sha, actual_sha))
            continue
        rows.append(ComponentRow(path, oid, source_sha, "present"))

    expected_paths = set(by_path)
    actual_paths, tree_errors = _component_tree_entries(adopter)
    errors.extend(tree_errors)
    for path in sorted(actual_paths - expected_paths):
        errors.append("unregistered file in immutable component: %s" % path)

    return ComponentBoundaryReport(
        upstream_revision_id=revision_id,
        distribution_boundary_sha256=boundary_sha256,
        rows=tuple(sorted(rows, key=lambda row: row.path)),
        errors=tuple(sorted(set(errors))),
    )


def manifest_text(report):
    """Render a deterministic TSV manifest for a clean report."""
    if not isinstance(report, ComponentBoundaryReport):
        raise ComponentBoundaryError(
            "manifest source must be a ComponentBoundaryReport")
    if report.errors:
        raise ComponentBoundaryError(
            "a manifest cannot be generated for a failing byte boundary")
    lines = [
        "# Cambium upstream component byte manifest",
        "# schema_version: 1",
        "# upstream_revision_id: %s" % report.upstream_revision_id,
        "# distribution_boundary_sha256: %s" %
        report.distribution_boundary_sha256,
        "\t".join(MANIFEST_COLUMNS),
    ]
    lines.extend("\t".join((
        row.path, row.git_blob_oid, row.sha256, row.presence))
                 for row in report.rows)
    return "\n".join(lines) + "\n"


def manifest_path(adopter_root):
    """Resolve the one registered adopter-derived manifest path."""
    relative = DEFAULT_MANIFEST_PATH
    try:
        absolute = kblib.repository_path(
            adopter_root, relative, reject_symlink=True)
    except ValueError as exc:
        raise ComponentBoundaryError("unsafe manifest path: %s" % exc) from exc
    current = os.path.abspath(adopter_root)
    for part in relative.split("/")[:-1]:
        current = os.path.join(current, part)
        if os.path.lexists(current) and stat.S_ISLNK(os.lstat(current).st_mode):
            raise ComponentBoundaryError(
                "manifest parent must not be a symlink: %s" % part)
    return absolute
