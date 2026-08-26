"""Does a declared repository-relative path resolve to real bytes inside it.

One place refuses a path that escapes the repository, and it refuses through
symlinks and hardlinks both, because a check that only rejects ``..`` is a
check that a link defeats.  Normalizing a declared path, resolving evidence
files and loading a canonical state file all sit behind that same refusal, so
no caller can reach the filesystem by a route that skipped it.
"""

import os
import stat

import check_profile
import kblib
import runtime_paths


def load_state(root, relative_path, overrides=None):
    path = kblib.managed_repository_path(
        root, relative_path, runtime_paths.STATE_ROOT,
        suffixes=(".yaml",), must_exist=True,
    )
    if overrides and relative_path in overrides:
        raw, data = overrides[relative_path]
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not isinstance(raw, bytes) or not isinstance(data, dict):
            raise ValueError("invalid in-memory state override for %s" %
                             relative_path)
        return path, raw, data
    if not os.path.isfile(path):
        raise ValueError("%s is not a regular file" % relative_path)
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("%s is not UTF-8: %s" % (relative_path, exc))
    data = kblib.parse_yaml_subset(text)
    if not isinstance(data, dict):
        raise ValueError("%s top level must be a mapping" % relative_path)
    return path, raw, data


def repository_evidence_file(root, relative_path, label, errors,
                              *, suffixes=(".yaml", ".yml", ".json")):
    """Resolve one immutable evidence file without symlink/hardlink aliases."""
    try:
        absolute = kblib.repository_path(
            root, relative_path, must_exist=True, reject_symlink=True,
        )
        if suffixes and not relative_path.endswith(tuple(suffixes)):
            raise ValueError("path must end with %s" % " or ".join(suffixes))
        current = os.path.realpath(os.path.abspath(root))
        for part in relative_path.replace("\\", "/").split("/"):
            current = os.path.join(current, part)
            if os.path.lexists(current) and os.path.islink(current):
                raise ValueError("path must not traverse a symlink")
        descriptor = os.lstat(absolute)
        if not stat.S_ISREG(descriptor.st_mode):
            raise ValueError("path is not a regular file")
        if descriptor.st_nlink != 1:
            raise ValueError("file must have exactly one hard link")
        return absolute
    except (OSError, TypeError, ValueError) as exc:
        errors.append("%s is unsafe or missing: %s" % (label, exc))
        return None


def _path_error(root, raw_path, must_exist=False):
    try:
        path = kblib.repository_path(root, raw_path, must_exist=must_exist)
    except (OSError, ValueError) as exc:
        return str(exc)
    if must_exist and not os.path.isfile(path):
        return "path is not a regular file"
    return None


def normalized_repository_path(value):
    """Normalize one declared repository-relative path for set comparison."""
    if not isinstance(value, str):
        return None
    value = check_profile.unbacktick(value).strip()
    while value.startswith("./"):
        value = value[2:]
    value = value.strip("/")
    return value or None
