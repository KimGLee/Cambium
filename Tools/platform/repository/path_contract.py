"""Canonical lexical path spellings shared by repository consumers.

This contract owns only repository-relative text shape.  It does not resolve
paths, inspect filesystem objects, decide authorization, or choose a managed
namespace.
"""

import os


def canonical_repository_relative_path(value, label, *, prefix=None,
                                       suffix=None):
    """Return one canonical POSIX repository-relative path spelling."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(
            "%s must be a non-empty canonical repository-relative path" %
            label)
    if "\x00" in value or "\\" in value or os.path.isabs(value):
        raise ValueError(
            "%s must be a canonical repository-relative path" % label)
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(
            "%s must be a canonical repository-relative path" % label)
    if prefix is not None and not value.startswith(prefix):
        raise ValueError("%s must start with %s" % (label, prefix))
    if suffix is not None and not value.endswith(suffix):
        raise ValueError("%s must end with %s" % (label, suffix))
    return value


__all__ = ("canonical_repository_relative_path",)
