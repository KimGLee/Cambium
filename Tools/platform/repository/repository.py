"""Repository-path and exact-file-byte mechanics shared by Tool layers.

These helpers do not decide whether a path is authorized or whether bytes are
semantically valid.  They only canonicalize an explicitly supplied repository
root, hash one file's exact bytes, or produce a display spelling for a path.
"""

import hashlib
import os
from pathlib import Path

import Tools.platform.common.kblib as kblib


def relative_path_is_within(path, root):
    """Return whether one canonical slash path equals or descends from root."""
    return path == root or path.startswith(root + "/")


def relative_path_is_within_any(path, roots):
    """Return whether one canonical slash path is within any supplied root."""
    return any(relative_path_is_within(path, root) for root in roots)


def repository_source_root(source_file, root=None):
    """Return an explicit root, or the ancestor that owns ``Tools``.

    Implementations live below ``Tools/<Area>/<Domain>`` while public
    adapters remain directly below ``Tools``.  Counting parents from a source
    file therefore encodes the old flat layout and silently points at a
    domain directory after a move.  Resolve the named distribution boundary
    instead so every layer observes the same repository root.
    """
    if root is not None:
        return os.path.realpath(os.path.abspath(os.fspath(root)))
    source = Path(source_file).resolve()
    for parent in source.parents:
        if parent.name == "Tools":
            return os.fspath(parent.parent)
    raise ValueError("source file is not contained by a Tools directory")


def tools_source_root(source_file):
    """Return the physical ``Tools`` ancestor for one implementation file."""
    source = Path(source_file).resolve()
    for parent in source.parents:
        if parent.name == "Tools":
            return os.fspath(parent)
    raise ValueError("source file is not contained by a Tools directory")


def file_bytes_sha256(path):
    """Return the canonical SHA-256 identity of one file's exact bytes."""
    with open(path, "rb") as handle:
        return "sha256:" + hashlib.sha256(handle.read()).hexdigest()


def repository_relative_spelling(root, path):
    """Spell a path relative to ``root`` when inside it, else as absolute."""
    root = os.path.abspath(root)
    path = os.path.abspath(path)
    prefix = root + os.sep
    if path.startswith(prefix):
        return path[len(prefix):].replace(os.sep, "/")
    return path


def repository_input_snapshot(root, raw_path, label):
    """Bind one repository input to its canonical relative path and bytes.

    Actual ancestry, rather than lexical spelling, admits the harmless
    macOS ``/var``/``/private/var`` alias while preserving every path segment
    inside the repository for the no-follow file snapshot check.
    """
    root = os.path.abspath(os.fspath(root))
    candidate = os.fspath(raw_path)
    if not os.path.isabs(candidate):
        candidate = os.path.join(root, candidate)
    candidate = os.path.abspath(candidate)

    relative_parts = []
    current = candidate
    while True:
        try:
            if os.path.samefile(current, root):
                break
        except OSError:
            pass
        parent, name = os.path.split(current)
        if not name or parent == current:
            relative_parts = []
            break
        relative_parts.append(name)
        current = parent
    if not relative_parts:
        raise ValueError("%s path escapes the repository" % label)
    relative = "/".join(reversed(relative_parts))
    return relative, kblib.repository_file_snapshot(
        root, relative, singly_linked=True)


def same_existing_target_snapshot(left, right):
    """Compare two existing target snapshots by identity, stat state and bytes.

    This contract intentionally does not compare ``repository_path``.  It is
    for callers that have already fixed one target path and need an exact
    before-image CAS for that target.  Missing targets never satisfy this
    contract; they use :func:`same_missing_target_snapshot` instead.
    """
    return (
        left.exists and right.exists and
        (left.dev, left.ino, left.mode, left.nlink, left.size,
         left.mtime_ns, left.ctime_ns, left.data) ==
        (right.dev, right.ino, right.mode, right.nlink, right.size,
         right.mtime_ns, right.ctime_ns, right.data)
    )


def same_existing_repository_target_snapshot(left, right):
    """Compare two existing snapshots including their repository spelling."""
    return (
        left.repository_path == right.repository_path and
        same_existing_target_snapshot(left, right)
    )


def same_missing_target_snapshot(left, right):
    """Compare two safely missing targets by tail and existing-parent identity.

    A missing target has no file identity or bytes.  Its stable before-image is
    instead the exact missing tail plus the deepest existing repository parent
    and that parent's device/inode identity.
    """
    return (
        not left.exists and not right.exists and
        left.missing_components == right.missing_components and
        left.parent_repository_path == right.parent_repository_path and
        left.parent_dev == right.parent_dev and
        left.parent_ino == right.parent_ino
    )


def resolve_markdown_reference(root, value):
    """Resolve one in-root Markdown reference, with an optional suffix."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidates = [value]
    if not value.lower().endswith(".md"):
        candidates.append(value + ".md")
    root_real = os.path.realpath(root)
    for candidate in candidates:
        path = os.path.normpath(os.path.join(root, candidate))
        try:
            inside = os.path.commonpath(
                (root_real, os.path.realpath(path))) == root_real
        except ValueError:
            continue
        if inside and os.path.isfile(path):
            return path
    return None


def path_is_within_any(path, roots):
    """Return whether ``path`` is one of, or descends from, ``roots``."""
    normalized = os.path.normpath(path)
    return any(
        normalized == root or normalized.startswith(root + os.sep)
        for root in roots
    )
