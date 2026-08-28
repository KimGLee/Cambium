"""Load the Kernel-owned Batch-close Closed List registry.

``kernel/K12 Quality Assurance/batch-close-closed-list.yaml`` owns the
current member definitions and order. This module owns only strict loading,
mechanical validation, the evidence-field projection, and the
bounded producer-era compatibility needed to replay already sealed 1.4.0
close bundles. It does not add a check or decide what any check means.
"""

import os
import re

import kblib


BATCH_CLOSE_CLOSED_LIST_PATH = (
    "kernel/K12 Quality Assurance/batch-close-closed-list.yaml")
_DOCUMENT_FIELDS = {
    "schema_version", "registry_id", "semantic_owner", "members",
}
_COMMON_MEMBER_FIELDS = {
    "member_id", "rule_id", "meaning", "due_stage", "producer_check",
    "consumer_gate_id", "evidence_role", "evidence_kind", "dimension",
    "dimension_binding",
}
_PRODUCER_FIELDS = {"producer_capability", "producer_gate_id"}
_MEMBER_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


def validate_batch_close_closed_list(document):
    """Validate one registry document and return its ordered member IDs."""
    if not isinstance(document, dict) or set(document) != _DOCUMENT_FIELDS:
        missing = sorted(_DOCUMENT_FIELDS - set(document or {})) \
            if isinstance(document, dict) else sorted(_DOCUMENT_FIELDS)
        extra = sorted(set(document) - _DOCUMENT_FIELDS) \
            if isinstance(document, dict) else []
        raise ValueError(
            "batch-close Closed List registry fields are not closed: "
            "missing=%s extra=%s" % (missing, extra))
    if document.get("schema_version") != 1:
        raise ValueError(
            "batch-close Closed List registry schema_version must be 1")
    if document.get("registry_id") != "batch-close-closed-list":
        raise ValueError(
            "batch-close Closed List registry_id must be "
            "batch-close-closed-list")
    if document.get("semantic_owner") != "K12/09":
        raise ValueError(
            "batch-close Closed List semantic_owner must be K12/09")

    members = document.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError(
            "batch-close Closed List members must be a non-empty list")
    member_ids = []
    rule_ids = []
    for index, member in enumerate(members):
        label = "batch-close Closed List member %d" % index
        if not isinstance(member, dict):
            raise ValueError("%s must be a mapping" % label)
        producer_fields = set(member) & _PRODUCER_FIELDS
        expected = _COMMON_MEMBER_FIELDS | producer_fields
        if (set(member) != expected or len(producer_fields) != 1):
            raise ValueError(
                "%s fields are not closed or do not bind exactly one "
                "producer" % label)
        member_id = member.get("member_id")
        if (not isinstance(member_id, str) or
                _MEMBER_ID_RE.fullmatch(member_id) is None):
            raise ValueError("%s has an invalid member_id" % label)
        if member_id in member_ids:
            raise ValueError(
                "duplicate batch-close Closed List member_id %s" % member_id)
        meaning = member.get("meaning")
        if (not isinstance(meaning, str) or not meaning or
                meaning.strip() != meaning):
            raise ValueError("%s meaning must be a non-empty string" % label)
        rule_id = member.get("rule_id")
        if (not isinstance(rule_id, str) or not rule_id or
                rule_id.strip() != rule_id or rule_id in rule_ids):
            raise ValueError("%s has an invalid or duplicate rule_id" % label)
        for field in (
                "producer_check", "consumer_gate_id", "evidence_role",
                "evidence_kind", "dimension_binding"):
            value = member.get(field)
            if not isinstance(value, str) or not value or value.strip() != value:
                raise ValueError("%s %s must be a non-empty string" %
                                 (label, field))
        producer_field = next(iter(producer_fields))
        producer = member.get(producer_field)
        if (not isinstance(producer, str) or not producer or
                producer.strip() != producer):
            raise ValueError("%s %s must be a non-empty string" %
                             (label, producer_field))
        if member.get("due_stage") != "post-delta-close":
            raise ValueError("%s must be due at post-delta-close" % label)
        if member.get("consumer_gate_id") != "batch-close":
            raise ValueError("%s must be consumed by batch-close" % label)
        dimension = member.get("dimension")
        binding = member.get("dimension_binding")
        kind = member.get("evidence_kind")
        role = member.get("evidence_role")
        if binding == "fixed":
            if not isinstance(dimension, str) or not dimension:
                raise ValueError("%s fixed dimension must be non-empty" % label)
        elif binding in {"profile-registration", "dimensionless-gate"}:
            if dimension is not None:
                raise ValueError("%s dynamic/dimensionless dimension must be null" %
                                 label)
        else:
            raise ValueError("%s has unknown dimension_binding" % label)
        if kind == "audit-receipt":
            if role != "emits" or producer_field != "producer_capability" or \
                    binding == "dimensionless-gate":
                raise ValueError(
                    "%s AuditReceipt member has an invalid producer or role" %
                    label)
        elif kind == "gate-receipt":
            if (role != "consumes" or
                    producer_field != "producer_gate_id" or
                    binding != "dimensionless-gate"):
                raise ValueError(
                    "%s Gate member must directly consume a dimensionless "
                    "Gate producer" % label)
        else:
            raise ValueError("%s has unknown evidence_kind" % label)
        member_ids.append(member_id)
        rule_ids.append(rule_id)
    return tuple(member_ids)


def load_batch_close_closed_list(root=None, *, text=None):
    """Load and strictly validate the Kernel-owned machine registry."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if text is None:
        text = kblib.read_text(os.path.join(
            root, *BATCH_CLOSE_CLOSED_LIST_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_batch_close_closed_list(document)
    return document


_SHIPPED_DOCUMENT = load_batch_close_closed_list()
CLOSED_LIST_EVIDENCE_FIELDS = validate_batch_close_closed_list(
    _SHIPPED_DOCUMENT)
CLOSED_LIST_MEMBER_ROWS = tuple(dict(row) for row in
                                _SHIPPED_DOCUMENT["members"])


def closed_list_member_rows(root=None, *, text=None):
    """Return the ordered, validated machine rows without reinterpreting them."""
    document = load_batch_close_closed_list(root, text=text)
    return tuple(dict(row) for row in document["members"])

# Tool protocol history, not Kernel semantics. Version 1.4.0 sealed the first
# seven ordered members; every supported later producer era sealed the full
# current registry. Keeping only the era/count relation here means the seven
# identities and their order still derive from the one K12 registry.
_PRODUCER_ERA_MEMBER_COUNTS = {"1.4.0": 7}
LEGACY_CLOSED_LIST_VERSIONS = frozenset(_PRODUCER_ERA_MEMBER_COUNTS)


def closed_list_evidence_fields_for_producer_version(tool_version):
    """Project the ordered evidence fields sealed by one producer era."""
    count = _PRODUCER_ERA_MEMBER_COUNTS.get(
        tool_version, len(CLOSED_LIST_EVIDENCE_FIELDS))
    if count > len(CLOSED_LIST_EVIDENCE_FIELDS):
        raise ValueError(
            "batch-close Closed List registry cannot replay producer era %s: "
            "needs %d members, found %d" % (
                tool_version, count, len(CLOSED_LIST_EVIDENCE_FIELDS)))
    return CLOSED_LIST_EVIDENCE_FIELDS[:count]


LEGACY_CLOSED_LIST_EVIDENCE_FIELDS = \
    closed_list_evidence_fields_for_producer_version("1.4.0")


__all__ = [
    "BATCH_CLOSE_CLOSED_LIST_PATH",
    "CLOSED_LIST_EVIDENCE_FIELDS",
    "CLOSED_LIST_MEMBER_ROWS",
    "LEGACY_CLOSED_LIST_EVIDENCE_FIELDS",
    "LEGACY_CLOSED_LIST_VERSIONS",
    "closed_list_evidence_fields_for_producer_version",
    "closed_list_member_rows",
    "load_batch_close_closed_list",
    "validate_batch_close_closed_list",
]
