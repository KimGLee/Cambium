#!/usr/bin/env python3
"""Pure reading and validation contract for metadata-backed page state.

This module owns the shared interpretation of page frontmatter, projection
rule identities, and Coverage owner records.  It performs
no write, takes no lock, and does not decide when a projection or transition is
authorized.  Writers and runtime consumers use the same public functions so a
page cannot be read under a different contract from the one used to project
it.
"""

import datetime
import hashlib
import json
import re

import Tools.platform.common.kblib as kblib
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths


COVERAGE_LEDGER_PATH = runtime_paths.COVERAGE_PATH
ROW_VALUE_ADAPTER = "coverage-row-value-v1"
PROPERTY_STATE_ADAPTER = "coverage-property-state-v1"
PROPERTY_VALUE_ADAPTERS = frozenset((PROPERTY_STATE_ADAPTER,))
VALUE_SHAPES = metadata_execution_contract.VALUE_SHAPES
PROPERTY_STATE_FIELDS = \
    metadata_execution_contract.source_adapter_owner_record_keys(
        PROPERTY_STATE_ADAPTER)
CONTENT_CHANGE_TOMBSTONE_RULE = \
    "semantic-content-change-tombstone-v1"
FRONTMATTER = re.compile(r"^(---\n)(.*?)(\n---\n)", re.S)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def field_pattern(name):
    """Return the unique top-level line matcher for one managed field."""
    return re.compile(r"^%s:[ \t]*(.*)$" % re.escape(name), re.M)


def frontmatter_mapping(text, relative):
    """Return one page's restricted-YAML frontmatter mapping."""
    raw = kblib.extract_frontmatter(text)
    if raw is None:
        raise ValueError("%s has no complete fenced frontmatter" % relative)
    fields = kblib.parse_yaml_subset(raw)
    if not isinstance(fields, dict):
        raise ValueError("%s frontmatter must be a mapping" % relative)
    return fields


def rules_fingerprint(rules):
    """Return the canonical identity of an ordered projection rule set."""
    rendered = json.dumps(
        list(rules), ensure_ascii=True, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(rendered).hexdigest()


def validate_value_rule(rule, field):
    """Validate and return one projection rule's closed value shape."""
    shape = rule.get("value_shape")
    if shape not in VALUE_SHAPES:
        raise ValueError(
            "page projection field %s has unsupported value_shape %r" %
            (field, shape))
    allowed = rule.get("allowed_values")
    if shape == "enum":
        if (not isinstance(allowed, list) or not allowed or
                not all(isinstance(value, str) for value in allowed) or
                len(allowed) != len(set(allowed))):
            raise ValueError(
                "page projection field %s enum has no closed "
                "allowed_values" % field)
    elif "allowed_values" in rule and allowed is not None:
        raise ValueError(
            "page projection field %s declares allowed_values outside enum" %
            field)
    return shape


def _date_value(value, field, relative):
    if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError(
            "Coverage property_state.%s value for %s must be YYYY-MM-DD" %
            (field, relative))
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "Coverage property_state.%s value for %s is not a calendar date" %
            (field, relative)) from exc
    return value


def typed_owner_value(value, rule, relative):
    """Validate one current Coverage owner value against its rule."""
    field = rule["field"]
    shape = validate_value_rule(rule, field)
    if shape == "scalar-string-or-null":
        if value is not None and not isinstance(value, str):
            raise ValueError(
                "Coverage owner value %s for %s must be a string or null" %
                (field, relative))
        return value
    if shape == "date":
        return _date_value(value, field, relative)
    if not isinstance(value, str) or value not in rule["allowed_values"]:
        raise ValueError(
            "Coverage owner value %s for %s must be one of %s; found %r" %
            (field, relative, ", ".join(rule["allowed_values"]), value))
    return value


def owner_value(row, rule, relative, semantic_fingerprint, property_states):
    """Return ``(exists, value)`` for one validated Coverage owner record."""
    field = rule["field"]
    adapter = rule["source_adapter"]
    if adapter == ROW_VALUE_ADAPTER:
        if field not in row:
            raise ValueError(
                "Coverage row for %s has no canonical owner value for %s" %
                (relative, field))
        return True, typed_owner_value(row[field], rule, relative)

    record = property_states.get(field)
    if record is None:
        return False, None
    if not isinstance(record, dict):
        raise ValueError(
            "Coverage property_state.%s for %s must be a mapping" %
            (field, relative))
    missing = sorted(PROPERTY_STATE_FIELDS - set(record))
    extra = sorted(set(record) - PROPERTY_STATE_FIELDS)
    if missing or extra:
        details = []
        if missing:
            details.append("missing %s" % ", ".join(missing))
        if extra:
            details.append("undeclared %s" % ", ".join(extra))
        raise ValueError(
            "Coverage property_state.%s for %s is not closed (%s)" %
            (field, relative, "; ".join(details)))
    receipt = record.get("evidence_receipt")
    if not isinstance(receipt, str) or not receipt.strip():
        raise ValueError(
            "Coverage property_state.%s for %s has no evidence_receipt" %
            (field, relative))
    fingerprint = record.get("content_fingerprint")
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(
            fingerprint):
        raise ValueError(
            "Coverage property_state.%s for %s has no valid "
            "content_fingerprint" % (field, relative))
    if fingerprint != semantic_fingerprint:
        raise ValueError(
            "Coverage property_state.%s for %s is bound to stale content "
            "(%s, current %s)" %
            (field, relative, fingerprint, semantic_fingerprint))
    raw_value = record.get("value")
    if raw_value is None:
        if rule.get("invalidation_rule") != CONTENT_CHANGE_TOMBSTONE_RULE:
            raise ValueError(
                "Coverage property_state.%s for %s uses an unauthorized "
                "null tombstone" % (field, relative))
        return True, None
    return True, typed_owner_value(raw_value, rule, relative)


def coverage_ledger_snapshot(root):
    """Return the exact existing Coverage Ledger repository snapshot."""
    snapshot = kblib.repository_target_snapshot(
        root, COVERAGE_LEDGER_PATH, suffixes=".yaml", singly_linked=True)
    if not snapshot.exists:
        raise ValueError("Coverage Ledger does not exist")
    return snapshot
