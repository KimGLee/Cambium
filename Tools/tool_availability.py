#!/usr/bin/env python3
"""Resolve which tool modules a projection target is allowed to be missing.

The distribution boundary already says which files never reach an adopter
runtime.  Until this module existed, nothing in the interface compile chain
read that declaration, so the closed interface policy asked every adopter for
a tool the same repository had excluded from adopter runtimes, and the
compiler refused when the adopter correctly did not have it.

The resolution is deliberately not "skip whatever is absent".  Absence is
evidence of two opposite things -- a tool the boundary excludes, and a tool
that was supposed to arrive and did not -- and a rule that cannot tell them
apart turns the second into a silent pass.  Only a module the boundary names
may be missing; every other absence stays a refusal.

Which target applies is declared by the caller and recorded in what the
caller produces.  It is never inferred from what happens to be on disk: a
distribution with a half-finished checkout would otherwise identify itself as
an adopter runtime and excuse the very absence that needs reporting.
"""

import os

import kblib


DEFAULT_BOUNDARY_PATH = "distribution-boundary.yaml"
TOOLS_SUBDIR = "Tools"

#: A projection either describes the distribution that owns every tool, or an
#: adopter runtime carrying only what its governance needs.
SOURCE_DISTRIBUTION = "source-distribution"
CARRIED_RUNTIME = "carried-runtime"
PROJECTION_TARGETS = (SOURCE_DISTRIBUTION, CARRIED_RUNTIME)


class AvailabilityError(Exception):
    """The boundary declaration or the requested target cannot be resolved."""


class ToolAvailability(object):
    """One resolved answer about which tool modules a target expects.

    ``excluded`` is the set the boundary permits to be missing under this
    target.  It is empty for the source distribution, which owns everything
    it declares, and it is the reason a carried runtime can compile at all.
    """

    __slots__ = ("target", "boundary_sha256", "excluded", "boundary_path")

    def __init__(self, target, boundary_sha256, excluded, boundary_path):
        self.target = target
        self.boundary_sha256 = boundary_sha256
        self.excluded = frozenset(excluded)
        self.boundary_path = boundary_path

    def permits_missing(self, tool_name):
        """True when this target may legitimately lack that tool module."""
        return tool_name in self.excluded

    def partition(self, declared_tools, present_tools):
        """Split declared tools into (included, excluded, unregistered).

        ``unregistered`` is the finding: a declared tool that is neither
        present nor named by the boundary.  Callers fail closed on it.
        """
        declared = sorted(set(declared_tools))
        present = set(present_tools)
        included, excluded, unregistered = [], [], []
        for name in declared:
            if name in present:
                included.append(name)
            elif self.permits_missing(name):
                excluded.append(name)
            else:
                unregistered.append(name)
        return included, excluded, unregistered


def _boundary_document(root, boundary_path=None):
    relative = boundary_path or DEFAULT_BOUNDARY_PATH
    absolute = os.path.join(os.path.abspath(root), relative)
    try:
        with open(absolute, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise AvailabilityError(
            "cannot read the distribution boundary at %s: %s"
            % (relative, exc))
    try:
        document = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise AvailabilityError(
            "%s is not a readable boundary declaration: %s"
            % (relative, exc))
    if not isinstance(document, dict):
        raise AvailabilityError(
            "%s must be a mapping" % relative)
    return document, kblib.sha256_bytes(raw), relative


def excluded_tool_modules(document):
    """Tool module names the declaration keeps out of an adopter runtime.

    A tool module is a top-level ``Tools/<name>.py``.  A declared tree never
    contributes one, because a module inside a package is not a tool; naming
    the tree is how the distribution retires the whole closure at once.
    """
    entries = document.get("distribution_only")
    if not isinstance(entries, list):
        raise AvailabilityError(
            "the distribution boundary carries no distribution_only list")
    names = set()
    prefix = TOOLS_SUBDIR + "/"
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else entry
        if not isinstance(path, str):
            continue
        normalized = path.replace("\\", "/").strip()
        if not normalized.startswith(prefix) or not normalized.endswith(".py"):
            continue
        remainder = normalized[len(prefix):]
        if "/" in remainder:
            continue
        names.add(remainder[: -len(".py")])
    return names


def resolve(root, target, boundary_path=None):
    """Return the availability answer for one declared projection target."""
    if target not in PROJECTION_TARGETS:
        raise AvailabilityError(
            "unknown projection target %r; declare one of %s"
            % (target, ", ".join(PROJECTION_TARGETS)))
    document, boundary_sha256, relative = _boundary_document(
        root, boundary_path)
    declared = excluded_tool_modules(document)
    # The distribution owns every tool it declares.  Granting it the same
    # exclusions would let its own CI pass while a carried tool is missing,
    # which is the failure this resolver exists to keep visible.
    excluded = declared if target == CARRIED_RUNTIME else frozenset()
    return ToolAvailability(target, boundary_sha256, excluded, relative)


def boundary_sha256(root, boundary_path=None):
    """The hash derived artifacts bind so boundary drift marks them stale."""
    return _boundary_document(root, boundary_path)[1]
