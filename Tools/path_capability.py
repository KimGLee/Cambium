#!/usr/bin/env python3
"""Descriptor-retained path capabilities for Cambium tool processes.

The MCP transport admits caller-visible paths while it still owns a pinned
workspace descriptor.  This module is the consumer-side half of that public
protocol: it validates the inherited manifest, reads through retained file
descriptors, publishes through retained parent descriptors, carries the same
authority into nested Cambium subprocesses, and acknowledges only actual
descriptor-backed consumption.

Ordinary CLI execution carries no manifest and keeps the historical pathname
behaviour.  This module deliberately owns no policy registry and no argparse
surface; classification remains in ``agent-interface-policy.yaml`` and
transport admission remains in ``mcp_server.py``.
"""

import errno
import hashlib
import json
import os
import stat
from types import MappingProxyType

import runtime_paths


PATH_CAPABILITIES_ENV = "CAMBIUM_PATH_CAPABILITIES"
PATH_CAPABILITIES_ACK_ENV = "CAMBIUM_PATH_CAPABILITIES_ACK_FD"
WORKSPACE_ENV = "CAMBIUM_WORKSPACE_ROOT"

_MANIFEST_CACHE = None
_TREE_BYTES = {}
_TREE_METADATA = {}
_TREE_SNAPSHOTS = {}
_ADVANCED_TARGETS = {}
_ACKNOWLEDGED = set()
_TREE_SNAPSHOT_FACTORY = None


def records():
    """Return the validated inherited descriptor manifest, if this is MCP."""
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    raw = os.environ.get(PATH_CAPABILITIES_ENV)
    if not raw:
        _MANIFEST_CACHE = ()
        return _MANIFEST_CACHE
    try:
        document = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "inherited path capability manifest is invalid: %s" % exc)
    if not isinstance(document, dict) or \
            document.get("schema_version") != 1 or \
            not isinstance(document.get("tool"), str) or \
            not isinstance(document.get("capabilities"), list):
        raise ValueError("inherited path capability manifest has wrong shape")
    parsed = []
    for row in document["capabilities"]:
        required = {
            "capability_id", "argument", "value_index", "spelling", "access",
            "consumption", "constraint", "exists", "kind", "target_fd",
            "parent_fd", "basename", "missing_components", "target_dev",
            "target_ino",
        }
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError(
                "inherited path capability record is incomplete")
        if row["consumption"] not in (
                "snapshot", "append", "replace", "transaction"):
            raise ValueError("inherited path capability mode is unknown")
        if row["kind"] not in ("file", "directory", "missing"):
            raise ValueError("inherited path capability kind is unknown")
        for field in ("target_fd", "parent_fd"):
            descriptor = row.get(field)
            if descriptor is None:
                continue
            if not isinstance(descriptor, int) or isinstance(descriptor, bool):
                raise ValueError("inherited path capability fd is invalid")
            try:
                metadata = os.fstat(descriptor)
            except OSError as exc:
                raise ValueError(
                    "inherited path capability fd is unavailable: %s" % exc)
            expected_dev = row.get(
                "target_dev" if field == "target_fd" else "parent_dev")
            expected_ino = row.get(
                "target_ino" if field == "target_fd" else "parent_ino")
            if expected_dev is not None and (
                    metadata.st_dev != expected_dev or
                    metadata.st_ino != expected_ino):
                raise ValueError(
                    "inherited path capability fd identity changed")
        parsed.append(MappingProxyType(dict(row)))
    _MANIFEST_CACHE = tuple(parsed)
    return _MANIFEST_CACHE


def logical_spelling(path):
    """Return the workspace-relative spelling used by the manifest."""
    value = os.fspath(path)
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in ("", "."):
        return "."
    if not os.path.isabs(value):
        return os.path.normpath(normalized).replace(os.sep, "/")
    candidates = []
    try:
        candidates.append(os.getcwd())
    except OSError:
        pass
    configured = os.environ.get(WORKSPACE_ENV)
    if configured:
        candidates.append(configured)
    for root in candidates:
        try:
            relative = os.path.relpath(value, root).replace(os.sep, "/")
        except ValueError:
            continue
        if relative == "." or (relative and relative != ".." and
                               not relative.startswith("../")):
            return relative
    return normalized


def inherited_capability(path, consumptions=None):
    """Return the retained capability matching ``path``, if this is MCP."""
    inherited = records()
    if not inherited:
        return None
    spelling = logical_spelling(path)
    matches = [row for row in inherited if row["spelling"] == spelling]
    if not matches:
        return None
    if consumptions is None:
        allowed = None
    elif isinstance(consumptions, str):
        allowed = {consumptions}
    else:
        allowed = set(consumptions)
    if allowed is not None:
        matches = [row for row in matches
                   if row["consumption"] in allowed]
        if not matches:
            raise ValueError(
                "typed path %s is not admitted for %s consumption" %
                (spelling, ", ".join(sorted(allowed))))
    if len(matches) > 1:
        raise ValueError(
            "typed path %s has ambiguous retained capabilities" % spelling)
    return matches[0]


def ancestor_directory_capability(path, consumptions):
    """Return the narrowest retained directory governing a child path."""
    spelling = logical_spelling(path)
    allowed = ({consumptions} if isinstance(consumptions, str) else
               set(consumptions))
    matches = []
    for row in records():
        prefix = row["spelling"]
        if (row["kind"] == "directory" and
                row["consumption"] in allowed and
                (prefix == "." or spelling.startswith(prefix + "/"))):
            matches.append(row)
    return (max(matches, key=lambda row: len(row["spelling"].split("/")))
            if matches else None)


def register_tree_snapshot_factory(factory):
    """Register the kblib snapshot value constructor once during import."""
    global _TREE_SNAPSHOT_FACTORY
    if _TREE_SNAPSHOT_FACTORY is not None and \
            _TREE_SNAPSHOT_FACTORY is not factory:
        raise RuntimeError("path capability tree factory is already set")
    _TREE_SNAPSHOT_FACTORY = factory


def acknowledge(capability):
    """Acknowledge only the exact manifest record that was consumed."""
    capability_id = capability["capability_id"]
    if capability_id in _ACKNOWLEDGED:
        return
    raw_fd = os.environ.get(PATH_CAPABILITIES_ACK_ENV)
    if raw_fd is None:
        raise ValueError(
            "inherited path capabilities carry no acknowledgement channel")
    try:
        descriptor = int(raw_fd)
    except (TypeError, ValueError):
        raise ValueError("path capability acknowledgement fd is invalid")
    encoded = (capability_id + "\n").encode("utf-8")
    if os.write(descriptor, encoded) != len(encoded):
        raise OSError(errno.EIO,
                      "path capability acknowledgement was partial")
    _ACKNOWLEDGED.add(capability_id)


def subprocess_kwargs():
    """Return subprocess kwargs preserving the inherited authority chain."""
    inherited = records()
    if not inherited:
        return {}
    descriptors = set()
    forwarded = []
    for row in inherited:
        forwarded_row = dict(row)
        advanced = _ADVANCED_TARGETS.get(row["capability_id"])
        if advanced is not None:
            forwarded_row.update({
                "exists": True,
                "kind": "file",
                "target_fd": advanced["fd"],
                "target_dev": advanced["dev"],
                "target_ino": advanced["ino"],
                "missing_components": [],
            })
        forwarded.append(forwarded_row)
        for field in ("target_fd", "parent_fd"):
            descriptor = forwarded_row.get(field)
            if descriptor is not None:
                descriptors.add(descriptor)
    raw_ack = os.environ.get(PATH_CAPABILITIES_ACK_ENV)
    if raw_ack is None:
        raise ValueError(
            "inherited path capabilities carry no acknowledgement channel")
    try:
        descriptors.add(int(raw_ack))
    except (TypeError, ValueError):
        raise ValueError("path capability acknowledgement fd is invalid")
    document = json.loads(os.environ[PATH_CAPABILITIES_ENV])
    document["capabilities"] = forwarded
    environment = {
        PATH_CAPABILITIES_ENV: json.dumps(
            document, sort_keys=True, separators=(",", ":")),
        PATH_CAPABILITIES_ACK_ENV: os.environ[PATH_CAPABILITIES_ACK_ENV],
    }
    if WORKSPACE_ENV in os.environ:
        environment[WORKSPACE_ENV] = os.environ[WORKSPACE_ENV]
    return {
        "pass_fds": tuple(sorted(descriptors)),
        "env_overrides": environment,
    }


def _stat_identity(descriptor):
    return (
        descriptor.st_dev, descriptor.st_ino, descriptor.st_mode,
        descriptor.st_nlink, descriptor.st_size,
        getattr(descriptor, "st_mtime_ns",
                int(descriptor.st_mtime * 1e9)),
        getattr(descriptor, "st_ctime_ns",
                int(descriptor.st_ctime * 1e9)),
    )


def read_stable_descriptor(descriptor, expected_dev, expected_ino,
                           display_path):
    """Read one retained regular file while proving its identity is stable."""
    fd = os.dup(descriptor)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or \
                (expected_dev is not None and
                 (before.st_dev, before.st_ino) !=
                 (expected_dev, expected_ino)):
            raise OSError(errno.EAGAIN,
                          "retained file identity changed", display_path)
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        if _stat_identity(before) != _stat_identity(after):
            raise OSError(errno.EAGAIN,
                          "retained file changed while reading", display_path)
        return b"".join(chunks)
    finally:
        os.close(fd)


def effective_target(capability):
    """Return the descriptor advanced by this exact capability, if any."""
    replacement = _ADVANCED_TARGETS.get(capability["capability_id"])
    if replacement is not None:
        return replacement["fd"], replacement["dev"], replacement["ino"]
    return (capability.get("target_fd"), capability.get("target_dev"),
            capability.get("target_ino"))


def record_replacement(capability, parent_fd, basename, published_path):
    """Advance one transaction capability to the newly published inode."""
    if capability.get("consumption") != "transaction" or \
            capability.get("spelling") != logical_spelling(published_path):
        return
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_CLOEXEC", 0))
    fd = os.open(basename, flags, dir_fd=parent_fd)
    descriptor = os.fstat(fd)
    if not stat.S_ISREG(descriptor.st_mode) or descriptor.st_nlink != 1:
        os.close(fd)
        raise ValueError("published transaction target is not a unique file")
    key = capability["capability_id"]
    old = _ADVANCED_TARGETS.get(key)
    if old is not None:
        os.close(old["fd"])
    _ADVANCED_TARGETS[key] = {
        "fd": fd, "dev": descriptor.st_dev, "ino": descriptor.st_ino,
    }


def record_append_target(capability, parent_fd, basename, published_path,
                         written_descriptor):
    """Bind a formerly missing append capability to its created inode.

    Admission retains the parent when an append target does not yet exist.
    Once ``O_CREAT`` has selected a regular file, later durability inspection
    in the same process must read that exact object rather than treating the
    frozen ``exists=false`` fact as permanent.  The read descriptor is opened
    relative to the retained parent and matched to the already-open writer
    before any receipt bytes are published.
    """
    if capability.get("consumption") != "append" or \
            capability.get("spelling") != logical_spelling(published_path):
        return
    flags = (os.O_RDWR | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_CLOEXEC", 0))
    fd = os.open(basename, flags, dir_fd=parent_fd)
    descriptor = os.fstat(fd)
    expected = (written_descriptor.st_dev, written_descriptor.st_ino)
    if (not stat.S_ISREG(descriptor.st_mode) or descriptor.st_nlink != 1 or
            (descriptor.st_dev, descriptor.st_ino) != expected):
        os.close(fd)
        raise OSError(errno.EAGAIN,
                      "append target changed before publication",
                      os.fspath(published_path))
    key = capability["capability_id"]
    old = _ADVANCED_TARGETS.get(key)
    if old is not None and (old["dev"], old["ino"]) != expected:
        os.close(fd)
        raise OSError(errno.EAGAIN,
                      "append target changed after first publication",
                      os.fspath(published_path))
    if old is not None:
        os.close(old["fd"])
    _ADVANCED_TARGETS[key] = {
        "fd": fd, "dev": descriptor.st_dev, "ino": descriptor.st_ino,
    }


def verify_named_target(capability, published_path):
    """Prove an effective file is still the unique admitted final name."""
    target_fd, target_dev, target_ino = effective_target(capability)
    if target_fd is None:
        raise FileNotFoundError(errno.ENOENT,
                                "typed path does not exist",
                                os.fspath(published_path))
    target = os.fstat(target_fd)
    if (not stat.S_ISREG(target.st_mode) or target.st_nlink != 1 or
            (target.st_dev, target.st_ino) != (target_dev, target_ino)):
        raise OSError(errno.EAGAIN,
                      "retained target is not a unique regular file",
                      os.fspath(published_path))
    parent_fd = capability.get("parent_fd")
    if parent_fd is None:
        raise OSError(errno.ENOTSUP,
                      "typed path has no retained parent capability",
                      os.fspath(published_path))
    parent = os.fstat(parent_fd)
    if (parent.st_dev, parent.st_ino) != (
            capability.get("parent_dev"), capability.get("parent_ino")):
        raise OSError(errno.EAGAIN,
                      "retained parent capability identity changed",
                      os.fspath(published_path))
    named = os.stat(capability["basename"], dir_fd=parent_fd,
                    follow_symlinks=False)
    if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1 or
            (named.st_dev, named.st_ino) != (target_dev, target_ino)):
        raise OSError(errno.EAGAIN,
                      "typed path no longer names the retained target",
                      os.fspath(published_path))


def cached_file(path):
    """Return cached tree bytes and stat, or ``None`` when not captured."""
    spelling = logical_spelling(path)
    if spelling not in _TREE_BYTES:
        return None
    return _TREE_BYTES[spelling], _TREE_METADATA[spelling]


def cache_file(path, data, metadata):
    """Advance descriptor-backed process state after an atomic publication."""
    spelling = logical_spelling(path)
    _TREE_BYTES[spelling] = data
    _TREE_METADATA[spelling] = metadata


def cached_tree(relative_directory):
    return _TREE_SNAPSHOTS.get(logical_spelling(relative_directory))


def cache_tree(relative_directory, snapshot):
    _TREE_SNAPSHOTS[logical_spelling(relative_directory)] = snapshot


def tree_contains(path):
    return logical_spelling(path) in _TREE_BYTES


def tree_is_bound(relative_directory):
    return logical_spelling(relative_directory) in _TREE_SNAPSHOTS


def materialize_tree(root, relative_directory, capability):
    """Snapshot a retained directory without reopening any pathname."""
    if _TREE_SNAPSHOT_FACTORY is None:
        raise RuntimeError("path capability tree factory is not registered")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_only = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_only is None:
        raise OSError(errno.ENOTSUP,
                      "tree capability requires O_NOFOLLOW and O_DIRECTORY",
                      relative_directory)
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | nofollow | directory_only | close_on_exec
    file_flags = os.O_RDONLY | nofollow | close_on_exec
    contents = {}
    entries = []

    def walk(directory_fd, nested):
        before = os.fstat(directory_fd)
        if not stat.S_ISDIR(before.st_mode):
            raise ValueError("retained tree component is not a directory")
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise OSError(exc.errno, "cannot enumerate retained tree", nested)
        for name in names:
            if not isinstance(name, str) or name in ("", ".", "..") or \
                    "/" in name or "\\" in name:
                raise ValueError("retained tree has a non-canonical entry")
            listed = os.stat(name, dir_fd=directory_fd,
                             follow_symlinks=False)
            child_nested = "/".join(filter(None, (nested, name)))
            if relative_directory == "." and not nested and \
                    name in (
                        ".git", runtime_paths.RUNTIME_ROOT, "__pycache__"):
                continue
            if stat.S_ISLNK(listed.st_mode):
                raise ValueError("snapshot cannot traverse symlink: %s" %
                                 child_nested)
            if stat.S_ISDIR(listed.st_mode):
                child_fd = os.open(
                    name, directory_flags, dir_fd=directory_fd)
                try:
                    opened = os.fstat(child_fd)
                    if ((listed.st_dev, listed.st_ino) !=
                            (opened.st_dev, opened.st_ino)):
                        raise OSError(errno.EAGAIN,
                                      "tree directory identity changed",
                                      child_nested)
                    walk(child_fd, child_nested)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(listed.st_mode) or listed.st_nlink != 1:
                raise ValueError(
                    "snapshot requires singly-linked regular file: %s" %
                    child_nested)
            file_fd = os.open(name, file_flags, dir_fd=directory_fd)
            try:
                opened = os.fstat(file_fd)
                if ((listed.st_dev, listed.st_ino) !=
                        (opened.st_dev, opened.st_ino)):
                    raise OSError(errno.EAGAIN,
                                  "tree file identity changed", child_nested)
                data = read_stable_descriptor(
                    file_fd, opened.st_dev, opened.st_ino, child_nested)
            finally:
                os.close(file_fd)
            repository_relative = "/".join(filter(
                None, (relative_directory if relative_directory != "." else
                       "", child_nested)))
            entries.append((repository_relative, opened, data))
        after = os.fstat(directory_fd)
        if _stat_identity(before) != _stat_identity(after):
            raise OSError(errno.EAGAIN,
                          "retained directory changed while snapshotting",
                          nested or relative_directory)

    root_fd = os.dup(capability["target_fd"])
    try:
        opened_root = os.fstat(root_fd)
        if ((opened_root.st_dev, opened_root.st_ino) !=
                (capability["target_dev"], capability["target_ino"])):
            raise OSError(errno.EAGAIN, "retained tree identity changed",
                          relative_directory)
        walk(root_fd, "")
    finally:
        os.close(root_fd)

    digest = hashlib.sha256()
    digest.update(b"cambium-repository-tree-snapshot-v1\0")
    for relative, descriptor, data in sorted(entries):
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(hashlib.sha256(data).digest())
        contents[relative] = data
        cache_file(relative, data, descriptor)
    snapshot = _TREE_SNAPSHOT_FACTORY(
        os.path.realpath(os.path.abspath(root)), relative_directory,
        "sha256:" + digest.hexdigest(), contents)
    acknowledge(capability)
    return snapshot


def materialize_ancestor_tree(path,
                              consumptions=("snapshot", "transaction")):
    """Snapshot the retained directory that semantically owns ``path``."""
    capability = ancestor_directory_capability(path, consumptions)
    if capability is None:
        return None
    prefix = capability["spelling"]
    cached = cached_tree(prefix)
    if cached is not None:
        acknowledge(capability)
        return cached
    root = os.environ.get(WORKSPACE_ENV) or os.getcwd()
    snapshot = materialize_tree(root, prefix, capability)
    if capability["consumption"] == "snapshot":
        cache_tree(prefix, snapshot)
    return snapshot


def read_bytes(path, consumptions=("snapshot", "transaction")):
    """Read bytes from a retained typed input, else from the CLI pathname."""
    cached = cached_file(path)
    if cached is not None:
        return cached[0]
    capability = inherited_capability(path, consumptions=consumptions)
    if capability is None and records():
        materialize_ancestor_tree(path, consumptions)
        cached = cached_file(path)
        if cached is not None:
            return cached[0]
    if capability is None:
        with open(path, "rb") as handle:
            return handle.read()
    if not capability["exists"]:
        raise FileNotFoundError(errno.ENOENT, "typed path does not exist",
                                os.fspath(path))
    if capability["kind"] != "file" or capability["target_fd"] is None:
        raise IsADirectoryError(errno.EISDIR, "typed path is not a file",
                                os.fspath(path))
    descriptor, dev, ino = effective_target(capability)
    data = read_stable_descriptor(descriptor, dev, ino, os.fspath(path))
    acknowledge(capability)
    return data


def read_text(path, encoding="utf-8", errors="strict"):
    return read_bytes(path).decode(encoding, errors=errors)


def open_parent(path, consumptions=("replace", "transaction")):
    """Return a retained parent FD and basename for a typed writer."""
    capability = inherited_capability(path, consumptions=consumptions)
    spelling = logical_spelling(path)
    if capability is None:
        allowed = ({consumptions} if isinstance(consumptions, str) else
                   set(consumptions))
        ancestors = []
        for row in records():
            prefix = row["spelling"]
            inside = prefix == "." or spelling.startswith(prefix + "/")
            if (inside and row["kind"] == "directory" and
                    row["consumption"] in allowed):
                ancestors.append(row)
        if ancestors:
            capability = max(
                ancestors, key=lambda row: len(row["spelling"].split("/")))
            prefix = capability["spelling"]
            nested = (spelling if prefix == "." else
                      spelling[len(prefix):].lstrip("/"))
            components = nested.split("/") if nested else []
            if not components:
                raise ValueError("typed directory capability needs a child")
            current_fd = os.dup(capability["target_fd"])
            directory_flags = (
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                getattr(os, "O_NOFOLLOW", 0) |
                getattr(os, "O_CLOEXEC", 0))
            try:
                for component in components[:-1]:
                    child_fd = os.open(
                        component, directory_flags, dir_fd=current_fd)
                    opened = os.fstat(child_fd)
                    if not stat.S_ISDIR(opened.st_mode):
                        os.close(child_fd)
                        raise ValueError(
                            "typed transaction parent is not a directory")
                    os.close(current_fd)
                    current_fd = child_fd
                acknowledge(capability)
                return capability, current_fd, components[-1]
            except Exception:
                os.close(current_fd)
                raise
    if capability is None:
        return None, None, None
    parent_fd = capability.get("parent_fd")
    if parent_fd is None:
        raise OSError(errno.ENOTSUP,
                      "typed path has no retained parent capability",
                      os.fspath(path))
    missing = capability.get("missing_components") or []
    if len(missing) > 1:
        raise OSError(
            errno.ENOTSUP,
            "typed writes require every parent directory to exist at "
            "admission", os.fspath(path))
    descriptor = os.fstat(parent_fd)
    if (descriptor.st_dev, descriptor.st_ino) != (
            capability.get("parent_dev"), capability.get("parent_ino")):
        raise OSError(errno.EAGAIN,
                      "retained parent capability identity changed",
                      os.fspath(path))
    basename = capability["basename"]
    if not basename or basename in (".", "..") or "/" in basename or \
            "\\" in basename:
        raise ValueError("typed write basename is not canonical")
    acknowledge(capability)
    return capability, os.dup(parent_fd), basename


def parent_tree_snapshot(root, child_path):
    """Bind the admitted parent package of one explicit file capability."""
    capability = inherited_capability(child_path, "snapshot")
    if capability is None or not capability["exists"] or \
            capability["kind"] != "file" or \
            capability.get("parent_fd") is None:
        raise ValueError("path has no retained file-parent capability")
    parent_relative = os.path.dirname(
        logical_spelling(child_path)).replace(os.sep, "/") or "."
    cached = cached_tree(parent_relative)
    if cached is not None:
        acknowledge(capability)
        return cached
    parent = os.fstat(capability["parent_fd"])
    synthetic = dict(capability)
    synthetic.update({
        "spelling": parent_relative,
        "exists": True,
        "kind": "directory",
        "target_fd": capability["parent_fd"],
        "target_dev": parent.st_dev,
        "target_ino": parent.st_ino,
    })
    snapshot = materialize_tree(root, parent_relative, synthetic)
    acknowledge(capability)
    cache_tree(parent_relative, snapshot)
    return snapshot
