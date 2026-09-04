"""Strict read-only projections from the Kernel-owned K08 vocabulary base.

``vocabulary-base.yaml`` owns vocabulary membership, source order, and review
interval values.  This module owns only the closed mechanical reader and the
immutable projections Tool consumers need.  It does not supply fallback
priorities, volatility tiers, or interval values of its own.
"""
from Tools.platform.repository.repository import repository_source_root

import os
import re
from types import MappingProxyType

import Tools.platform.common.kblib as kblib


VOCABULARY_BASE_PATH = (
    "kernel/K08 Metadata and Status/vocabulary-base.yaml")
VOCABULARY_EXTENSIONS_CONTRACT_PATH = (
    "kernel/K08 Metadata and Status/vocabulary-extensions-contract.yaml")
_DOCUMENT_FIELDS = frozenset((
    "schema_version", "composition_policy", "fields",
    "review_intervals_days",
))
_FIELD_RECORD_FIELDS = frozenset(("owner", "values"))
_FIELD_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


class VocabularyContractError(ValueError):
    """The K08 vocabulary base is unsafe or mechanically malformed."""


def _unique_strings(value, label, *, allow_empty=False):
    if (not isinstance(value, list) or (not value and not allow_empty) or
            any(not isinstance(item, str) or not item or
                item.strip() != item for item in value) or
            len(value) != len(set(value))):
        raise VocabularyContractError(
            "%s must be a unique string list" % label)
    return tuple(value)


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
        root = repository_source_root(__file__)
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


def validate_vocabulary_extensions_contract(document):
    """Validate and project the K08-owned Profile extension form."""
    document = _closed_mapping(document, {
        "schema_version", "contract_id", "semantic_owner", "document",
        "frontmatter_extensions", "vocabulary_field",
        "volatility_defaults", "composition_rules"},
        "Vocabulary Extensions contract")
    if document.get("schema_version") != 1 or document.get(
            "contract_id") != "vocabulary-extensions-shape-v1":
        raise VocabularyContractError(
            "Vocabulary Extensions contract identity is invalid")
    form = _closed_mapping(document.get("document"), {
        "schema_version", "fields"}, "Vocabulary Extensions document form")
    if form.get("schema_version") != 1:
        raise VocabularyContractError(
            "Vocabulary Extensions document schema_version must be 1")
    fields = frozenset(_unique_strings(
        form.get("fields"), "Vocabulary Extensions document fields"))
    frontmatter = _closed_mapping(
        document.get("frontmatter_extensions"), {
            "fields", "field_list_shape"},
        "Vocabulary frontmatter extension form")
    frontmatter_fields = frozenset(_unique_strings(
        frontmatter.get("fields"), "Vocabulary frontmatter fields"))
    if frontmatter.get("field_list_shape") != \
            "unique-nonempty-string-list":
        raise VocabularyContractError(
            "Vocabulary frontmatter field-list shape is unsupported")
    field = _closed_mapping(document.get("vocabulary_field"), {
        "field_id_pattern", "required_fields", "optional_fields",
        "values_shape", "owner_shape", "role_shape"},
        "Vocabulary field form")
    required = frozenset(_unique_strings(
        field.get("required_fields"), "Vocabulary field required fields"))
    optional = frozenset(_unique_strings(
        field.get("optional_fields"), "Vocabulary field optional fields",
        allow_empty=True))
    pattern = field.get("field_id_pattern")
    if (not isinstance(pattern, str) or not pattern or
            field.get("values_shape") != "string-list" or
            field.get("owner_shape") != "nonempty-string" or
            field.get("role_shape") != "nonempty-string"):
        raise VocabularyContractError(
            "Vocabulary field shape declarations are unsupported")
    defaults = _closed_mapping(document.get("volatility_defaults"), {
        "minimum_items", "domain_id_shape", "value_owner"},
        "Vocabulary volatility defaults form")
    if (defaults.get("minimum_items") != 1 or
            defaults.get("domain_id_shape") != "nonempty-trimmed-string" or
            defaults.get("value_owner") != "K08-vocabulary.volatility"):
        raise VocabularyContractError(
            "Vocabulary volatility defaults form is unsupported")
    composition = _closed_mapping(document.get("composition_rules"), {
        "policy", "kernel_field_allowed_fields",
        "profile_only_field_allowed_fields", "domain_identity_owner",
        "fields_domain_forbidden", "composed_frontmatter_field_membership"},
        "Vocabulary extension composition rules")
    kernel_fields = frozenset(_unique_strings(
        composition.get("kernel_field_allowed_fields"),
        "Vocabulary kernel-field allowed fields"))
    profile_fields = frozenset(_unique_strings(
        composition.get("profile_only_field_allowed_fields"),
        "Vocabulary Profile-only allowed fields"))
    if (composition.get("policy") != "append-only-profile-extensions" or
            composition.get("domain_identity_owner") !=
            "volatility_defaults.keys" or
            composition.get("fields_domain_forbidden") is not True or
            composition.get("composed_frontmatter_field_membership") !=
            "explicit-plus-profile-only-fields"):
        raise VocabularyContractError(
            "Vocabulary extension composition rules are unsupported")
    return MappingProxyType({
        "document_schema_version": form["schema_version"],
        "document_fields": fields,
        "frontmatter_fields": frontmatter_fields,
        "field_id_pattern": pattern,
        "field_required_fields": required,
        "field_optional_fields": optional,
        "kernel_field_allowed_fields": kernel_fields,
        "profile_only_field_allowed_fields": profile_fields,
    })


def load_vocabulary_extensions_contract(root=None, *, text=None):
    if root is None:
        root = repository_source_root(__file__)
    if text is None:
        text = kblib.read_text(os.path.join(
            root, *VOCABULARY_EXTENSIONS_CONTRACT_PATH.split("/")))
    try:
        document = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        raise VocabularyContractError(
            "K08 Vocabulary Extensions contract is not parseable: %s" % exc)
    validate_vocabulary_extensions_contract(document)
    return document


def vocabulary_extensions_shape(contract=None):
    """Return the immutable shape projection used by Tool consumers."""
    return validate_vocabulary_extensions_contract(
        contract or _SHIPPED_EXTENSIONS_DOCUMENT)


def validate_vocabulary_extensions(document, contract=None,
                                   volatility_values=None):
    """Return closed-shape errors for one Profile vocabulary extension."""
    try:
        projection = validate_vocabulary_extensions_contract(
            contract or _SHIPPED_EXTENSIONS_DOCUMENT)
    except VocabularyContractError as exc:
        return ("owner contract is invalid: %s" % exc,)
    issues = []
    if not isinstance(document, dict):
        return ("document must be a mapping",)
    missing = sorted(projection["document_fields"] - set(document))
    extra = sorted(set(document) - projection["document_fields"])
    if missing or extra:
        issues.append("top-level fields are not closed: missing=%s extra=%s" %
                      (missing, extra))
    if document.get("schema_version") != projection["document_schema_version"]:
        issues.append("schema_version must be %d" %
                      projection["document_schema_version"])
    frontmatter = document.get("frontmatter_extensions")
    if not isinstance(frontmatter, dict) or set(frontmatter) != \
            projection["frontmatter_fields"]:
        issues.append("frontmatter_extensions fields are not closed")
    else:
        try:
            _unique_strings(
                frontmatter.get("fields"),
                "frontmatter_extensions.fields", allow_empty=True)
        except VocabularyContractError as exc:
            issues.append(str(exc))
    fields = document.get("fields")
    if not isinstance(fields, dict):
        issues.append("fields must be a mapping")
        fields = {}
    pattern = re.compile(projection["field_id_pattern"] + r"\Z")
    for field_id, declaration in fields.items():
        if not isinstance(field_id, str) or pattern.fullmatch(field_id) is None:
            issues.append("field id %r is invalid" % field_id)
            continue
        if field_id == "domain":
            issues.append("fields.domain is forbidden; domains are owned by "
                          "volatility_defaults keys")
        allowed = (projection["field_required_fields"] |
                   projection["field_optional_fields"])
        if not isinstance(declaration, dict) or \
                not projection["field_required_fields"].issubset(
                    set(declaration)) or set(declaration) - allowed:
            issues.append("field %r fields are not closed" % field_id)
            continue
        try:
            _unique_strings(
                declaration.get("values"), "field %s values" % field_id,
                allow_empty=True)
        except VocabularyContractError as exc:
            issues.append(str(exc))
        for name in projection["field_optional_fields"]:
            if name in declaration and (
                    not isinstance(declaration[name], str) or
                    not declaration[name].strip()):
                issues.append("field %r %s must be nonempty" %
                              (field_id, name))
    defaults = document.get("volatility_defaults")
    if not isinstance(defaults, dict) or not defaults:
        issues.append("volatility_defaults must be a non-empty mapping")
    else:
        allowed_values = frozenset(
            VOLATILITY_VALUES if volatility_values is None else
            volatility_values)
        for domain, value in defaults.items():
            if not isinstance(domain, str) or not domain or \
                    domain.strip() != domain:
                issues.append("volatility_defaults domain %r is invalid" %
                              domain)
            if value not in allowed_values:
                issues.append("volatility_defaults.%s must be one of %s" %
                              (domain, sorted(allowed_values)))
    return tuple(issues)


_SHIPPED = load_vocabulary_base()
PRIORITY_VALUES = _SHIPPED["priority_values"]
PRIORITY_ORDER = _SHIPPED["priority_order"]
VOLATILITY_VALUES = _SHIPPED["volatility_values"]
COVERAGE_DISPOSITION_VALUES = _SHIPPED["coverage_disposition_values"]
FIELD_VALUES = _SHIPPED["field_values"]
REVIEW_INTERVALS_DAYS = _SHIPPED["review_intervals_days"]
_SHIPPED_EXTENSIONS_DOCUMENT = load_vocabulary_extensions_contract()
_SHIPPED_EXTENSIONS = validate_vocabulary_extensions_contract(
    _SHIPPED_EXTENSIONS_DOCUMENT)


__all__ = [
    'COVERAGE_DISPOSITION_VALUES',
    'PRIORITY_ORDER',
    'PRIORITY_VALUES',
    'REVIEW_INTERVALS_DAYS',
    'VOCABULARY_BASE_PATH',
    'VOCABULARY_EXTENSIONS_CONTRACT_PATH',
    'VocabularyContractError',
    'load_vocabulary_base',
    'load_vocabulary_extensions_contract',
    'validate_vocabulary_base',
    'validate_vocabulary_extensions',
    'validate_vocabulary_extensions_contract',
    'vocabulary_extensions_shape',
]
