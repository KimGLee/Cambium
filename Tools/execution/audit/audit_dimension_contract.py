"""Strict reader for the Kernel-owned K12 audit-dimension base registry.

The YAML document owns the closed semantic values.  This module owns only
their mechanical shape, identity, safe loading, and projections for Tool
consumers.  It does not add a dimension, evidence role, or Profile extension
choice of its own.
"""
from Tools.platform.repository.repository import repository_source_root

import os
import re

import Tools.platform.common.kblib as kblib


AUDIT_DIMENSION_BASE_PATH = (
    "kernel/K12 Quality Assurance/audit-dimension-base.yaml")
_REQUIRED_FIELDS = {
    "schema_version", "registry_id", "semantic_owner",
    "base_receipt_dimensions", "evidence_roles", "extension_output_kinds",
    "extension_target_mappings",
}
_ID_RE = re.compile(r"[a-z][a-z0-9_+ -]*[a-z0-9_]\Z")


def _unique_string_list(value, label):
    if (not isinstance(value, list) or not value or
            not all(isinstance(item, str) and item.strip() == item and item
                    for item in value)):
        raise ValueError("%s must be a non-empty string list" % label)
    if len(value) != len(set(value)):
        raise ValueError("%s must not contain duplicate values" % label)
    invalid = [item for item in value if _ID_RE.fullmatch(item) is None]
    if invalid:
        raise ValueError("%s contains invalid value(s): %s" %
                         (label, ", ".join(invalid)))
    return tuple(value)


def validate_audit_dimension_base(document):
    """Validate and return normalized projections from one registry document."""
    if not isinstance(document, dict) or set(document) != _REQUIRED_FIELDS:
        missing = sorted(_REQUIRED_FIELDS - set(document or {})) \
            if isinstance(document, dict) else sorted(_REQUIRED_FIELDS)
        extra = sorted(set(document) - _REQUIRED_FIELDS) \
            if isinstance(document, dict) else []
        raise ValueError(
            "audit-dimension registry fields are not closed: missing=%s "
            "extra=%s" % (missing, extra))
    if document.get("schema_version") != 1:
        raise ValueError("audit-dimension schema_version must be 1")
    if document.get("registry_id") != "cambium-audit-dimension-base":
        raise ValueError(
            "audit-dimension registry_id must be cambium-audit-dimension-base")
    if document.get("semantic_owner") != "K12/07-K12/08":
        raise ValueError("audit-dimension semantic_owner must be K12/07-K12/08")

    dimensions = _unique_string_list(
        document.get("base_receipt_dimensions"),
        "base_receipt_dimensions")
    roles = _unique_string_list(document.get("evidence_roles"),
                                "evidence_roles")
    output_kinds = _unique_string_list(
        document.get("extension_output_kinds"), "extension_output_kinds")

    rows = document.get("extension_target_mappings")
    if not isinstance(rows, list) or not rows:
        raise ValueError(
            "extension_target_mappings must be a non-empty list")
    mappings = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"declaration", "outputs"}:
            raise ValueError(
                "extension target mapping %d fields are not closed" % index)
        declaration = row.get("declaration")
        if (not isinstance(declaration, str) or not declaration or
                declaration.strip() != declaration or
                _ID_RE.fullmatch(declaration) is None):
            raise ValueError(
                "extension target mapping %d has an invalid declaration" %
                index)
        if declaration in mappings:
            raise ValueError(
                "duplicate extension target declaration %s" % declaration)
        outputs = _unique_string_list(
            row.get("outputs"),
            "extension target mapping %s outputs" % declaration)
        unknown = sorted(set(outputs) - set(output_kinds))
        if unknown:
            raise ValueError(
                "extension target mapping %s names unknown output kind(s): %s"
                % (declaration, ", ".join(unknown)))
        mappings[declaration] = outputs
    if set(output_kinds) - {
            output for outputs in mappings.values() for output in outputs}:
        raise ValueError(
            "every extension_output_kind must be reachable from a target "
            "mapping")
    return {
        "base_receipt_dimensions": dimensions,
        "evidence_roles": frozenset(roles),
        "extension_output_kinds": frozenset(output_kinds),
        "extension_target_mappings": mappings,
    }


def load_audit_dimension_base(root=None, snapshots=None):
    """Load one current registry from a repository root or frozen input set."""
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(AUDIT_DIMENSION_BASE_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        path = os.path.join(root, *AUDIT_DIMENSION_BASE_PATH.split("/"))
        text = kblib.read_text(path)
    document = kblib.parse_yaml_subset(text)
    validate_audit_dimension_base(document)
    return document


_SHIPPED_DOCUMENT = load_audit_dimension_base()
_SHIPPED_VALUES = validate_audit_dimension_base(_SHIPPED_DOCUMENT)
BASE_RECEIPT_DIMENSION_ORDER = _SHIPPED_VALUES["base_receipt_dimensions"]
BASE_RECEIPT_DIMENSIONS = frozenset(BASE_RECEIPT_DIMENSION_ORDER)
EVIDENCE_ROLES = _SHIPPED_VALUES["evidence_roles"]
EXTENSION_OUTPUT_KINDS = _SHIPPED_VALUES["extension_output_kinds"]
EXTENSION_TARGET_MAPPINGS = _SHIPPED_VALUES["extension_target_mappings"]


def current_audit_dimension_values(root=None, snapshots=None):
    """Return validated values and reject drift from this deployed Tool."""
    document = load_audit_dimension_base(root, snapshots=snapshots)
    if document != _SHIPPED_DOCUMENT:
        raise ValueError(
            "adopting audit-dimension registry differs from the validator's "
            "deployed Kernel contract")
    return validate_audit_dimension_base(document)


__all__ = [
    'AUDIT_DIMENSION_BASE_PATH',
    'BASE_RECEIPT_DIMENSION_ORDER',
    'BASE_RECEIPT_DIMENSIONS',
    'EVIDENCE_ROLES',
    'EXTENSION_TARGET_MAPPINGS',
    'current_audit_dimension_values',
    'load_audit_dimension_base',
    'validate_audit_dimension_base',
]
