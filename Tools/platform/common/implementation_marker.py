"""Pure parser for a Tool adapter's implementation-owner marker.

``IMPLEMENTATION_MODULE`` is a source-level edge, not executable metadata.
Consumers therefore inspect its top-level assignment without importing the
module.  This parser owns that inspection for both public-entrypoint loading
and distribution boundary analysis so malformed markers cannot mean an error
to one consumer and absence to another.
"""

import ast
import re


IMPLEMENTATION_MARKER = "IMPLEMENTATION_MODULE"
MODULE_NAME_RE = re.compile(r"Tools(?:\.[a-z][a-z0-9_]*)+\Z")


class ImplementationMarkerError(ValueError):
    """The implementation-owner marker is missing or not authoritative."""


def _marker_target_count(node):
    """How often one assignment target declares the reserved marker name."""
    if isinstance(node, ast.Name):
        return int(node.id == IMPLEMENTATION_MARKER)
    if isinstance(node, (ast.List, ast.Tuple)):
        return sum(_marker_target_count(element) for element in node.elts)
    if isinstance(node, ast.Starred):
        return _marker_target_count(node.value)
    return 0


def _marker_assignments(tree):
    assignments = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = (node.target,)
        else:
            continue
        count = sum(_marker_target_count(target) for target in targets)
        assignments.extend([node] * count)
    return assignments


def parse_implementation_module(tree, *, label="<source>", required=False):
    """Return the one qualified implementation module declared by ``tree``.

    An ordinary, non-wrapper module may omit the marker and receives ``None``.
    A public entrypoint passes ``required=True``.  Once the reserved marker is
    present, optional mode is no escape hatch: duplicates, computed values and
    invalid module names fail identically in both modes.
    """
    if not isinstance(tree, ast.Module):
        raise TypeError("tree must be an ast.Module")
    assignments = _marker_assignments(tree)
    if not assignments:
        if required:
            raise ImplementationMarkerError(
                "%s must declare exactly one %s" %
                (label, IMPLEMENTATION_MARKER))
        return None
    if len(assignments) != 1:
        raise ImplementationMarkerError(
            "%s must declare exactly one %s" %
            (label, IMPLEMENTATION_MARKER))

    assignment = assignments[0]
    value = assignment.value
    if isinstance(assignment, ast.Assign):
        direct_target = any(
            isinstance(target, ast.Name) and
            target.id == IMPLEMENTATION_MARKER
            for target in assignment.targets)
    elif isinstance(assignment, ast.AnnAssign):
        direct_target = (
            isinstance(assignment.target, ast.Name) and
            assignment.target.id == IMPLEMENTATION_MARKER)
    else:
        direct_target = False
    if not direct_target or not isinstance(value, ast.Constant) or \
            not isinstance(value.value, str):
        raise ImplementationMarkerError(
            "%s %s must be one literal module name" %
            (label, IMPLEMENTATION_MARKER))
    module_name = value.value
    if MODULE_NAME_RE.fullmatch(module_name) is None:
        raise ImplementationMarkerError(
            "%s %s is not a qualified Tools module" %
            (label, IMPLEMENTATION_MARKER))
    return module_name


def parse_implementation_module_source(
        source_text, *, label="<source>", required=False):
    """Parse source text and return its implementation-owner marker."""
    try:
        tree = ast.parse(source_text, filename=label)
    except SyntaxError as exc:
        raise ImplementationMarkerError(
            "%s does not parse: %s" % (label, exc)) from exc
    return parse_implementation_module(
        tree, label=label, required=required)


__all__ = (
    "IMPLEMENTATION_MARKER",
    "ImplementationMarkerError",
    "parse_implementation_module",
    "parse_implementation_module_source",
)
