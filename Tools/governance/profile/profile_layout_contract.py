#!/usr/bin/env python3
"""Tool-owned layout contract for the shipped ``profiles/`` namespace.

The candidate scaffolder and the read-only onboarding projector are separate
CLI programs.  This pure module owns the small layout facts every Profile
consumer requires: the namespace directory, manifest filename, canonical path
shapes, and which shipped namespace members can never be adopter candidate
IDs.  It does not parse Profile contents, scaffold files, select a candidate,
or expose a CLI.
"""

from dataclasses import dataclass
from collections.abc import Mapping
import re
from typing import Optional


PROFILES_DIRECTORY = "profiles"
PROFILE_MANIFEST_NAME = "profile.toml"
TEMPLATE_PROFILE_ID = "_template"
EXAMPLES_PROFILE_ID = "examples"
TEMPLATE_PROFILE_IDS = frozenset((TEMPLATE_PROFILE_ID,))
RESERVED_PROFILE_IDS = frozenset((
    *TEMPLATE_PROFILE_IDS,
    EXAMPLES_PROFILE_ID,
))
PROFILE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


class ProfileLayoutError(ValueError):
    """One Profile namespace path is not a canonical recognized manifest."""


@dataclass(frozen=True)
class ProfileManifestLocation:
    """Parsed identity and namespace class for one canonical manifest path."""

    path: str
    directory: str
    profile_id: str
    reserved_namespace: Optional[str] = None

    @property
    def selectable(self):
        return self.reserved_namespace is None

    @property
    def example(self):
        return self.reserved_namespace == EXAMPLES_PROFILE_ID


def validate_manifest_identity(document, location):
    """Validate only the encoding/identity envelope, never Profile admission.

    A Read Set locator can use this identity without turning discovery into
    policy validation or selection. Full Profile consumers still require the
    shared profile-load evaluation.
    """
    if not isinstance(location, ProfileManifestLocation) or not isinstance(document, Mapping):
        raise ProfileLayoutError("identity requires a parsed manifest location and object")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ProfileLayoutError("Profile must use the current structured encoding version")
    if document.get("profile_id") != location.profile_id:
        raise ProfileLayoutError("Profile identity must equal its canonical directory identity")
    return location.profile_id


def profile_relative(profile_id):
    """Return one namespace-relative Profile directory spelling."""
    return "%s/%s" % (PROFILES_DIRECTORY, profile_id)


def _validated_profile_id(profile_id):
    if not isinstance(profile_id, str) or not PROFILE_ID_RE.fullmatch(
            profile_id):
        raise ProfileLayoutError(
            "profile id %r must fully match [a-z0-9][a-z0-9_-]*" %
            profile_id)
    return profile_id


def parse_profile_manifest_path(value):
    """Parse one canonical candidate, template, or shipped-example manifest.

    Candidate and template packages are flat namespace members.  ``examples``
    is a reserved namespace containing named example packages, so it requires
    one additional path component.  No caller may infer either shape from a
    basename, a prefix match, or a permissive ``Path.parts`` test.
    """
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProfileLayoutError(
            "must be a non-empty canonical repository-relative path")
    parts = value.split("/")
    if (len(parts) == 3 and parts[0] == PROFILES_DIRECTORY and
            parts[2] == PROFILE_MANIFEST_NAME):
        profile_id = parts[1]
        if profile_id in TEMPLATE_PROFILE_IDS:
            return ProfileManifestLocation(
                value, profile_relative(profile_id), profile_id, profile_id)
        if profile_id == EXAMPLES_PROFILE_ID:
            raise ProfileLayoutError(
                "%s is a namespace; a shipped example manifest must name "
                "%s/%s/<profile-id>/%s" %
                (EXAMPLES_PROFILE_ID, PROFILES_DIRECTORY,
                 EXAMPLES_PROFILE_ID, PROFILE_MANIFEST_NAME))
        _validated_profile_id(profile_id)
        return ProfileManifestLocation(
            value, profile_relative(profile_id), profile_id)
    if (len(parts) == 4 and parts[0] == PROFILES_DIRECTORY and
            parts[1] == EXAMPLES_PROFILE_ID and
            parts[3] == PROFILE_MANIFEST_NAME):
        profile_id = _validated_profile_id(parts[2])
        return ProfileManifestLocation(
            value,
            "%s/%s/%s" % (
                PROFILES_DIRECTORY, EXAMPLES_PROFILE_ID, profile_id),
            profile_id,
            EXAMPLES_PROFILE_ID,
        )
    raise ProfileLayoutError(
        "must be exactly %s/<profile-id>/%s or "
        "%s/%s/<profile-id>/%s" %
        (PROFILES_DIRECTORY, PROFILE_MANIFEST_NAME,
         PROFILES_DIRECTORY, EXAMPLES_PROFILE_ID, PROFILE_MANIFEST_NAME))


def validate_selectable_profile_manifest_path(value):
    """Return the parsed location only when it names an adopter candidate."""
    location = parse_profile_manifest_path(value)
    if not location.selectable:
        raise ProfileLayoutError(
            "uses reserved/non-runnable Profile namespace %r" %
            location.reserved_namespace)
    return location
