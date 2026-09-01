"""Shared, read-only projections from governed Markdown frontmatter.

This module interprets the restricted-YAML frontmatter shape only.  It does
not choose scan scope, decide whether a page type is allowed, or own any
Profile value.
"""

import Tools.platform.common.kblib as kblib


def scalar_field(path, field):
    """Return one top-level frontmatter scalar as text, or ``None``."""
    raw = kblib.extract_frontmatter(
        kblib.read_text(path, errors="replace"))
    if raw is None:
        return None
    try:
        fields = kblib.parse_yaml_subset(raw)
    except kblib.YamlSubsetError:
        return None
    value = fields.get(field) if isinstance(fields, dict) else None
    return str(value) if value is not None else None


def page_type(path):
    """Return the page's declared ``type`` value, or ``None``."""
    return scalar_field(path, "type")
