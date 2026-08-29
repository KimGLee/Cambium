"""Strict read-only projections from the Kernel-owned K08 vocabulary base.

``vocabulary-base.yaml`` owns vocabulary membership, source order, and review
interval values.  This module owns only the closed mechanical reader and the
immutable projections Tool consumers need.  It does not supply fallback
priorities, volatility tiers, or interval values of its own.
"""

import os
import re
from types import MappingProxyType

import kblib


VOCABULARY_BASE_PATH = (
    "kernel/K08 Metadata and Status/vocabulary-base.yaml")
_DOCUMENT_FIELDS = frozenset((
    "schema_version", "composition_policy", "fields",
    "review_intervals_days",
))
_FIELD_RECORD_FIELDS = frozenset(("owner", "values"))
_FIELD_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


class VocabularyContractError(ValueError):
    """The K08 vocabulary base is unsafe or mechanically malformed."""


def _closed_mapping(value, fields, label):
    if not isinstance(value, dict):
        raise VocabularyContractError("%s must be a mapping" % label)
    missing = sorted(set(fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing or extra:
        raise VocabularyContractError(
            "%s fields are not closed: missing=%s extra=%s" %
            (label, missing, extra))
    return value


def _field_values(fields, field_id, *, nonempty):
    record = fields.get(field_id)
    if record is None:
        raise VocabularyContractError(
            "vocabulary fields omit required field %s" % field_id)
    record = _closed_mapping(
        record, _FIELD_RECORD_FIELDS, "vocabulary field %s" % field_id)
    values = record.get("values")
    if (not isinstance(values, list) or
            (nonempty and not values) or
            any(not isinstance(value, str) or not value or
                value.strip() != value for value in values)):
        qualifier = "non-empty " if nonempty else ""
        raise VocabularyContractError(
            "vocabulary field %s values must be a %sstring list" %
            (field_id, qualifier))
    if len(values) != len(set(values)):
        raise VocabularyContractError(
            "vocabulary field %s values contain duplicates" % field_id)
    return tuple(values)


def validate_vocabulary_base(document):
    """Validate one base document and return its immutable Tool projections."""
    document = _closed_mapping(
        document, _DOCUMENT_FIELDS, "K08 vocabulary base")
    if document.get("schema_version") != 1:
        raise VocabularyContractError(
            "K08 vocabulary base schema_version must be 1")
    composition_policy = document.get("composition_policy")
    if (not isinstance(composition_policy, str) or not composition_policy or
            composition_policy.strip() != composition_policy):
        raise VocabularyContractError(
            "K08 vocabulary base composition_policy must be a non-empty "
            "string")

    fields = document.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise VocabularyContractError(
            "K08 vocabulary base fields must be a non-empty mapping")
    field_values = {}
    for field_id, record in fields.items():
        if (not isinstance(field_id, str) or
                _FIELD_ID_RE.fullmatch(field_id) is None):
            raise VocabularyContractError(
                "K08 vocabulary base has invalid field id %r" % field_id)
        record = _closed_mapping(
            record, _FIELD_RECORD_FIELDS,
            "vocabulary field %s" % field_id)
        owner = record.get("owner")
        if (not isinstance(owner, str) or not owner or
                owner.strip() != owner):
            raise VocabularyContractError(
                "vocabulary field %s owner must be a non-empty string" %
                field_id)
        field_values[field_id] = _field_values(
            fields, field_id, nonempty=False)

    priorities = field_values.get("priority", ())
    if not priorities:
        raise VocabularyContractError(
            "vocabulary field priority values must be non-empty")
    volatilities = field_values.get("volatility", ())
    if not volatilities:
        raise VocabularyContractError(
            "vocabulary field volatility values must be non-empty")
    coverage_dispositions = field_values.get("coverage_disposition", ())
    if not coverage_dispositions:
        raise VocabularyContractError(
            "vocabulary field coverage_disposition values must be non-empty")
    intervals = document.get("review_intervals_days")
    if not isinstance(intervals, dict):
        raise VocabularyContractError(
            "review_intervals_days must be a mapping")
    missing = sorted(set(volatilities) - set(intervals))
    extra = sorted(set(intervals) - set(volatilities))
    if missing or extra:
        raise VocabularyContractError(
            "review_intervals_days must exactly cover volatility values: "
            "missing=%s extra=%s" % (missing, extra))
    for volatility in volatilities:
        interval = intervals[volatility]
        if interval is not None and (
                type(interval) is not int or interval <= 0):
            raise VocabularyContractError(
                "review_intervals_days.%s must be a positive integer or "
                "null" % volatility)

    return MappingProxyType({
        "field_values": MappingProxyType(dict(field_values)),
        "priority_values": priorities,
        "priority_order": MappingProxyType({
            value: index for index, value in enumerate(priorities)
        }),
        "volatility_values": volatilities,
        "coverage_disposition_values": coverage_dispositions,
        "review_intervals_days": MappingProxyType({
            value: intervals[value] for value in volatilities
        }),
    })


def load_vocabulary_base(root=None, *, text=None):
    """Load and strictly project the current Kernel-owned vocabulary base."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if text is None:
        text = kblib.read_text(os.path.join(
            root, *VOCABULARY_BASE_PATH.split("/")))
    try:
        document = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        raise VocabularyContractError(
            "K08 vocabulary base is not parseable restricted YAML: %s" %
            exc) from exc
    return validate_vocabulary_base(document)


_SHIPPED = load_vocabulary_base()
PRIORITY_VALUES = _SHIPPED["priority_values"]
PRIORITY_ORDER = _SHIPPED["priority_order"]
VOLATILITY_VALUES = _SHIPPED["volatility_values"]
COVERAGE_DISPOSITION_VALUES = _SHIPPED["coverage_disposition_values"]
FIELD_VALUES = _SHIPPED["field_values"]
REVIEW_INTERVALS_DAYS = _SHIPPED["review_intervals_days"]


__all__ = [
    "COVERAGE_DISPOSITION_VALUES",
    "FIELD_VALUES",
    "PRIORITY_ORDER",
    "PRIORITY_VALUES",
    "REVIEW_INTERVALS_DAYS",
    "VOCABULARY_BASE_PATH",
    "VOLATILITY_VALUES",
    "VocabularyContractError",
    "load_vocabulary_base",
    "validate_vocabulary_base",
]
