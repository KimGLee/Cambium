"""Pure machine interpretation of the K08/09 page boundary contract.

The checker and projection writer are separate applications over the same
boundary object.  This module owns the shared parsing primitives so those
applications cannot silently develop different marker, frontmatter, or
compiled-label semantics.
"""

from __future__ import annotations

import Tools.platform.common.kblib as kblib


def projection_labels_from_text(text):
    """Return ``(labels, error)`` for one compiled Page Contract.

    An empty labels mapping is valid because K08/09 supplies the display
    defaults.  ``None`` means the compiled contract itself is not consumable.
    """

    try:
        data = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        return None, (
            "cannot parse the compiled contract: %s — compose it with "
            "Tools/compose_page_contract.py" % exc
        )
    if not isinstance(data, dict) or not isinstance(data.get("fields"), dict):
        return None, "the compiled contract carries no fields mapping"
    projection = data.get("boundary_projection")
    labels = projection.get("labels") if isinstance(projection, dict) else None
    return (labels if isinstance(labels, dict) else {}), None


def boundary_block_from_text(text):
    """Return ``(block, parse_ok)`` for one Markdown page.

    ``block`` is ``None`` when the field is absent.  Invalid frontmatter is
    reported only through ``parse_ok`` because its finding remains owned by
    the Page Contract checker, not by the boundary applications.
    """

    raw = kblib.extract_frontmatter(text)
    if raw is None:
        return None, True
    try:
        fields = kblib.parse_yaml_subset(raw)
    except kblib.YamlSubsetError:
        return None, False
    if not isinstance(fields, dict):
        return None, False
    return fields.get(kblib.BOUNDARY_FIELD), True


def projection_marker_pair(lines):
    """Return the single owned marker pair or its canonical shape error."""

    begins = [
        index
        for index, line in enumerate(lines)
        if line.strip() == kblib.BOUNDARY_PROJECTION_BEGIN
    ]
    ends = [
        index
        for index, line in enumerate(lines)
        if line.strip() == kblib.BOUNDARY_PROJECTION_END
    ]
    if not begins and not ends:
        return None, None, None
    if len(begins) != 1 or len(ends) != 1:
        return (
            None,
            None,
            "the page carries %d begin and %d end projection marker(s); "
            "exactly one well-formed pair is owned" % (len(begins), len(ends)),
        )
    if ends[0] < begins[0]:
        return None, None, "the end marker precedes the begin marker"
    return begins[0], ends[0], None
