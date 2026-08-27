#!/usr/bin/env python3
"""Resolve one upstream Git revision to its immutable commit identity.

Adoption plans may record a human-facing source name and an expected revision,
but neither string is authority.  Writers call :func:`resolve_revision` against
an explicit local upstream Git repository and compare the result with the plan
before they construct any adopter state.
"""

import os
import re

import kblib


FULL_COMMIT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class UpstreamIdentityError(ValueError):
    """The supplied upstream repository or revision cannot identify a commit."""


def is_full_commit_sha(value):
    """Return whether ``value`` is one canonical full Git object id."""
    return isinstance(value, str) and FULL_COMMIT_RE.fullmatch(value) is not None


def resolve_revision(upstream_root, revision_ref):
    """Resolve ``revision_ref`` in ``upstream_root`` to a full commit SHA.

    The repository is an explicit input rather than inferred from the adopter
    working tree.  This prevents an adopter commit, tag spelling, release label,
    or arbitrary version string from becoming Cambium's upstream identity.
    """
    try:
        root = os.path.realpath(os.path.abspath(os.fspath(upstream_root)))
    except (TypeError, ValueError) as exc:
        raise UpstreamIdentityError(
            "upstream root must be a filesystem path: %s" % exc)
    if not os.path.isdir(root):
        raise UpstreamIdentityError(
            "upstream root is not an existing directory: %s" % root)
    if (not isinstance(revision_ref, str) or not revision_ref.strip() or
            revision_ref != revision_ref.strip() or
            "\x00" in revision_ref or "\n" in revision_ref or
            "\r" in revision_ref or revision_ref.startswith("-")):
        raise UpstreamIdentityError(
            "upstream revision ref must be one non-empty Git revision argument")

    command = [
        "git", "-C", root, "rev-parse", "--verify", "--end-of-options",
        "%s^{commit}" % revision_ref,
    ]
    try:
        environment = dict(os.environ)
        environment["GIT_NO_REPLACE_OBJECTS"] = "1"
        completed = kblib.run_cambium_subprocess(
            command, text=True, stdout=-1, stderr=-1, check=False,
            env=environment)
    except OSError as exc:
        raise UpstreamIdentityError(
            "cannot execute Git for upstream identity: %s" % exc)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise UpstreamIdentityError(
            "cannot resolve upstream Git revision %r in %s%s" % (
                revision_ref, root, ": %s" % detail if detail else ""))
    lines = [line.strip().lower()
             for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1 or not is_full_commit_sha(lines[0]):
        raise UpstreamIdentityError(
            "Git returned no single full commit SHA for upstream revision %r" %
            revision_ref)
    return lines[0]
