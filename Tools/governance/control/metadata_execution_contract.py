#!/usr/bin/env python3
"""Compile and load Cambium's closed metadata-execution authority contract.

This module is deliberately the single authority boundary between metadata
declarations and executable writers.  A field rule is executable only when an
installed writer capability declares the same ``(field, transition, adapter)``
operation, and every installed writer operation must be authorized by exactly
one rule.  Unknown keys, unknown adapters, orphan implementations, and partial
evidence bindings fail closed.
"""
from Tools.platform.repository.repository import repository_source_root

from dataclasses import dataclass
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys

import Tools.platform.common.kblib as kblib
import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader
import Tools.execution.task_runtime.runtime_paths as runtime_paths


TOOL = "metadata_execution_contract"
TOOL_VERSION = "1.1.0"
SCHEMA_VERSION = 1
ARTIFACT = "metadata-execution-contract"
DEFAULT_AUTHORITY_PATH = (
    "kernel/K08 Metadata and Status/metadata-authority-base.yaml")
DEFAULT_CAPABILITIES_PATH = "Tools/operation-capabilities.yaml"
DEFAULT_COMPILED_PATH = "Tools/compiled/metadata-execution-contract.json"

TEMPORAL_ORDER = (
    "first_seen",
    "last_content_modified",
    "last_reviewed",
    "last_verified",
)

TOP_KEYS = frozenset((
    "schema_version", "contract_id", "temporal_order", "field_rules"))
RULE_KEYS = frozenset((
    "field", "transition", "value_shape", "allowed_values",
    "authority_class", "canonical_owner",
    "source_adapter", "writer_capability", "write_timing",
    "reconcile_policy", "invalidation_rule", "evidence_requirement"))
EVIDENCE_KEYS = frozenset((
    "protocol", "result", "target_binding", "value_selector",
    "content_binding", "invalidation", "change_scope",
    "excluded_change_classes"))
CAPABILITIES_TOP_KEYS = frozenset(("schema_version", "capabilities"))
CAPABILITY_KEYS = frozenset((
    "capability_id", "kind", "capability_version", "implementation_owner",
    "writers", "checkers", "consumers", "operations"))
PROJECTION_CAPABILITY_KEYS = CAPABILITY_KEYS | frozenset(("input_owners",))
INVOCATION_OWNER_KEY = "invocation_owner"
INVOCATION_OWNER_RE = re.compile(r"Tools/[a-z][a-z0-9_]*\.py\Z")
IMPLEMENTATION_ROLE_KEYS = ("writers", "checkers", "consumers")
WRITER_OPERATION_KEYS = frozenset((
    "field", "transition", "source_adapter"))
CONSUMER_OPERATION_KEYS = frozenset(("operation",))
PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION = \
    "profile-extension-enum-owner-projection-v1"
GENERIC_WRITER_OPERATIONS = frozenset((
    PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION,
))
COMPILED_KEYS = frozenset((
    "artifact", "schema_version", "contract_id", "temporal_order",
    "source_adapters", "field_rules", "operation_capabilities",
    "writer_capabilities", "capability_implementations",
    "contract_fingerprint"))
IMPLEMENTATION_RECORD_KEYS = frozenset(("path", "sha256"))

AUTHORITY_CLASSES = frozenset((
    "content-authored", "user-owned", "ledger-projection",
    "evidence-projection", "derived-transient"))
CAPABILITY_KINDS = frozenset((
    "writer", "consumer", "producer", "receipt-schema", "projection"))
METADATA_EXECUTION_CAPABILITY_KINDS = CAPABILITY_KINDS - {"projection"}
CAPABILITIES_SCHEMA_VERSION = 3
FIELD_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
STABLE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
VALUE_SHAPES = frozenset(("scalar-string-or-null", "date", "enum"))
UPSERT_EXACT_OR_REMOVE_POLICY = "upsert-exact-or-remove-v1"
UPSERT_OWNER_PROPERTY_STATE_POLICY = "upsert-owner-property-state-v1"
TOMBSTONE_OWNER_PROPERTY_STATE_POLICY = \
    "tombstone-owner-property-state-v1"
RECONCILE_POLICIES = frozenset((
    UPSERT_EXACT_OR_REMOVE_POLICY,
    UPSERT_OWNER_PROPERTY_STATE_POLICY,
    TOMBSTONE_OWNER_PROPERTY_STATE_POLICY,
))
OWNER_RE = re.compile(
    r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9_]*(?:\[\])?)+\Z")

# Adapter definitions are code-owned protocol schemas, not free-form labels.
# ``owner_record_keys`` closes the Coverage property-state record consumed by
# page projection.  Event adapters require evidence; ledger readers do not.
SOURCE_ADAPTERS = {
    "content-change-event-v1": {
        "authority_class": "evidence-projection",
        "evidence_required": True,
        "owner_record_keys": [],
    },
    "coverage-property-state-v1": {
        "authority_class": "ledger-projection",
        "evidence_required": False,
        "owner_record_keys": [
            "content_fingerprint", "evidence_receipt", "value"],
    },
    "coverage-row-value-v1": {
        "authority_class": "ledger-projection",
        "evidence_required": False,
        "owner_record_keys": [],
    },
    "current-review-receipt-value-v1": {
        "authority_class": "evidence-projection",
        "evidence_required": True,
        "owner_record_keys": [],
    },
}


def _owner_record_key_projection(adapter_id, spec):
    keys = spec.get("owner_record_keys") if isinstance(spec, dict) else None
    if (not isinstance(keys, list) or len(keys) != len(set(keys)) or
            any(not isinstance(key, str) or
                FIELD_ID_RE.fullmatch(key) is None for key in keys)):
        raise ValueError(
            "source adapter %s owner_record_keys must be a unique field-id "
            "list" % adapter_id)
    return frozenset(keys)


_SOURCE_ADAPTER_OWNER_RECORD_KEYS = {
    adapter_id: _owner_record_key_projection(adapter_id, spec)
    for adapter_id, spec in SOURCE_ADAPTERS.items()
}


def source_adapter_owner_record_keys(adapter_id):
    """Return the immutable owner-record shape declared by one adapter."""
    try:
        return _SOURCE_ADAPTER_OWNER_RECORD_KEYS[adapter_id]
    except KeyError as exc:
        raise ValueError("unknown source adapter %r" % adapter_id) from exc


class MetadataExecutionContractError(ValueError):
    """The metadata contract cannot authorize runtime execution."""

    def __init__(self, errors):
        self.errors = tuple(str(item) for item in errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class CompiledMetadataExecutionContract:
    """Immutable result returned by both the compiler and artifact loader."""

    artifact: dict
    field_rules: tuple
    writer_capabilities: tuple
    contract_fingerprint: str
    canonical_bytes: bytes

    def rules_for_capability(self, capability_id):
        return tuple(
            rule for rule in self.field_rules
            if rule["writer_capability"] == capability_id)


class AuthorizedProjectionRules(tuple):
    """Rule sequence minted from one compiled contract/Profile composition."""

    def __new__(cls, rules, metadata_contract_fingerprint,
                profile_contract_fingerprint=None):
        value = super().__new__(cls, tuple(copy.deepcopy(tuple(rules))))
        value.metadata_contract_fingerprint = metadata_contract_fingerprint
        value.profile_contract_fingerprint = profile_contract_fingerprint
        return value


def profile_extension_enum_projection_rule(
        field, allowed_values, *, writer_capability):
    values = list(allowed_values)
    if (not isinstance(field, str) or FIELD_ID_RE.fullmatch(field) is None or
            not values or len(values) != len(set(values)) or
            any(not isinstance(value, str) or not value for value in values)):
        raise ValueError("Profile enum projection has invalid field or values")
    if (not isinstance(writer_capability, str) or
            STABLE_ID_RE.fullmatch(writer_capability) is None):
        raise ValueError("Profile enum projection has no writer capability")
    return {
        "field": field,
        "transition": "owner-to-page-projection",
        "value_shape": "enum",
        "allowed_values": values,
        "authority_class": "ledger-projection",
        "canonical_owner": (
            "coverage-ledger.pages[].property_state.%s" % field),
        "source_adapter": "coverage-property-state-v1",
        "writer_capability": writer_capability,
        "write_timing": "after-profile-extension-gate-transition",
        "reconcile_policy": UPSERT_EXACT_OR_REMOVE_POLICY,
        "invalidation_rule":
            "remove-owner-and-page-copy-on-semantic-content-change-v1",
        "evidence_requirement": None,
    }


def compose_profile_projection_rules(contract, profile_contract):
    """Instantiate the closed generic Profile-enum writer operation.

    Static Kernel fields remain covered bidirectionally by exact authority
    rules and concrete writer operations.  Dynamic Profile fields are instead
    admitted through one installed generic operation, then instantiated only
    from an authorized typed Profile's exact Gate enum set.
    """
    if not isinstance(contract, CompiledMetadataExecutionContract):
        raise TypeError("contract must be a CompiledMetadataExecutionContract")
    if (profile_contract is None or
            not getattr(profile_contract, "authorized", False)):
        raise ValueError(
            "Profile projection composition requires an authorized typed "
            "Profile contract")
    writer_capability = compiled_operation_owner(
        contract, PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION, kind="writer")
    rules = [copy.deepcopy(rule) for rule in
             contract.rules_for_capability(writer_capability)]
    kernel_fields = {rule.get("field") for rule in rules}
    values_by_field = {}
    for gate in getattr(profile_contract, "extension_gates", ()):
        field = getattr(gate, "field_id", None)
        if field is None:
            continue
        if (not isinstance(field, str) or
                FIELD_ID_RE.fullmatch(field) is None):
            raise ValueError("authorized Profile Gate has an invalid field")
        if field in kernel_fields:
            raise ValueError(
                "Profile field %s collides with a Kernel-managed page "
                "property" % field)
        values = values_by_field.setdefault(field, [])
        for value in getattr(gate, "completion_values", ()):
            if (not isinstance(value, str) or not value or
                    value in values):
                raise ValueError(
                    "authorized Profile Gate has an invalid completion enum")
            values.append(value)
    for field in sorted(values_by_field):
        rules.append(profile_extension_enum_projection_rule(
            field, values_by_field[field],
            writer_capability=writer_capability))
    fingerprint = getattr(
        profile_contract, "profile_contract_fingerprint", None)
    if fingerprint is None:
        fingerprint = getattr(profile_contract, "fingerprint", None)
    if not isinstance(fingerprint, str) or SHA256_RE.fullmatch(
            fingerprint) is None:
        raise ValueError(
            "authorized Profile contract has no canonical fingerprint")
    return AuthorizedProjectionRules(
        rules, contract.contract_fingerprint, fingerprint)


def _repository_root(root=None):
    if root is None:
        return Path(repository_source_root(__file__))
    return Path(root).resolve()


def _read_text(root, path):
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.read_text(encoding="utf-8")
    return kblib.repository_file_snapshot(
        str(root), candidate.as_posix(), singly_linked=True).read_text()


def _parse_yaml(root, path, label):
    try:
        document = kblib.parse_yaml_subset(_read_text(root, path))
    except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
        raise MetadataExecutionContractError(
            ["%s could not be read: %s" % (label, exc)]) from exc
    if not isinstance(document, dict):
        raise MetadataExecutionContractError(
            ["%s must be a mapping" % label])
    return document


def _closed_keys(value, required, target, errors, optional=frozenset()):
    if not isinstance(value, dict):
        errors.append("%s must be a mapping" % target)
        return False
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        errors.append("%s missing keys: %s" % (target, ", ".join(missing)))
    if unknown:
        errors.append("%s unknown keys: %s" % (target, ", ".join(unknown)))
    return not missing and not unknown


def _nonempty_id(value, pattern, target, errors):
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        errors.append("%s is not a valid stable identifier" % target)
        return False
    return True


def _validate_capabilities(document):
    errors = []
    if not _closed_keys(
            document, CAPABILITIES_TOP_KEYS, "operation capabilities", errors):
        return errors
    schema_version = document.get("schema_version")
    if schema_version != CAPABILITIES_SCHEMA_VERSION:
        errors.append("operation capabilities schema_version must be 3")
    entries = document.get("capabilities")
    if not isinstance(entries, list):
        errors.append("operation capabilities capabilities must be a list")
        return errors

    seen_capability_ids = {}
    seen_writer_operations = {}
    seen_generic_writer_operations = {}
    for index, entry in enumerate(entries):
        target = "capabilities[%d]" % index
        kind = entry.get("kind") if isinstance(entry, dict) else None
        entry_keys = (
            PROJECTION_CAPABILITY_KEYS
            if kind == "projection" else CAPABILITY_KEYS)
        if isinstance(entry, dict) and INVOCATION_OWNER_KEY in entry:
            entry_keys = entry_keys | frozenset((INVOCATION_OWNER_KEY,))
        if not _closed_keys(
                entry, entry_keys, target, errors,
                optional=frozenset(("receipt_contracts",))):
            continue
        capability_id = entry.get("capability_id")
        _nonempty_id(capability_id, STABLE_ID_RE,
                     target + ".capability_id", errors)
        if kind not in CAPABILITY_KINDS:
            errors.append("%s.kind is not registered" % target)
        if capability_id in seen_capability_ids:
            errors.append(
                "duplicate capability_id %s across capabilities[%d] and %s; "
                "capability identity is global, not kind-scoped" %
                (capability_id, seen_capability_ids[capability_id], target))
        else:
            seen_capability_ids[capability_id] = index
        if (not isinstance(entry.get("capability_version"), str) or
                VERSION_RE.fullmatch(entry["capability_version"]) is None):
            errors.append("%s.capability_version must be semver x.y.z" % target)
        owner = entry.get("implementation_owner")
        implementation_groups = tuple(
            (key, entry.get(key)) for key in IMPLEMENTATION_ROLE_KEYS)
        seen_paths = set()

        def validate_path(path, path_target):
            if (not isinstance(path, str) or not path or
                    path.startswith("/") or "\\" in path or
                    not path.startswith("Tools/") or
                    not path.endswith(".py") or
                    any(part in ("", ".", "..")
                        for part in path.split("/"))):
                errors.append(
                    "%s must be a canonical Tools/*.py repository path" %
                    path_target)
                return False
            return True

        if validate_path(owner, target + ".implementation_owner"):
            seen_paths.add(owner)
        if kind == "projection":
            input_owners = entry.get("input_owners")
            if (not isinstance(input_owners, list) or not input_owners or
                    any(not isinstance(item, str) or
                        STABLE_ID_RE.fullmatch(item) is None
                        for item in input_owners) or
                    len(input_owners) != len(set(input_owners))):
                errors.append(
                    "%s.input_owners must be a non-empty unique stable-ID "
                    "list" % target)
            else:
                unknown = []
                for input_owner in sorted(input_owners):
                    try:
                        runtime_paths.path_for(input_owner)
                    except KeyError:
                        unknown.append(input_owner)
                if unknown:
                    errors.append(
                        "%s.input_owners names unknown runtime object(s): "
                        "%s" % (target, ", ".join(unknown)))
        for group_name, implementation_paths in implementation_groups:
            if not isinstance(implementation_paths, list):
                errors.append(
                    "%s.%s must be a canonical repository-path list" %
                    (target, group_name))
                continue
            for path_index, path in enumerate(implementation_paths):
                path_target = "%s.%s[%d]" % (
                    target, group_name, path_index)
                if not validate_path(path, path_target):
                    continue
                if path in seen_paths:
                    errors.append(
                        "%s assigns implementation path %s more than once" %
                        (target, path))
                seen_paths.add(path)
        if INVOCATION_OWNER_KEY in entry:
            invocation_owner = entry.get(INVOCATION_OWNER_KEY)
            if validate_path(invocation_owner,
                             target + ".invocation_owner"):
                if INVOCATION_OWNER_RE.fullmatch(invocation_owner) is None:
                    errors.append(
                        "%s.invocation_owner must name one top-level "
                        "Tools/<tool>.py CLI" % target)
                # Invocation is a separate adapter edge, not an
                # implementation role.  Its marker-to-owner closure is
                # checked against source bytes by
                # ``capability_invocation_edge_errors``.
        operations = entry.get("operations")
        if not isinstance(operations, list):
            errors.append("%s.operations must be a list" % target)
            continue
        if kind in ("producer", "receipt-schema", "projection") and operations:
            errors.append("%s kind %s must have closed empty operations" %
                          (target, kind))
            continue
        local_seen = set()
        for operation_index, operation in enumerate(operations):
            op_target = "%s.operations[%d]" % (target, operation_index)
            if kind == "writer":
                if (isinstance(operation, dict) and
                        set(operation) == CONSUMER_OPERATION_KEYS):
                    generic = operation.get("operation")
                    if generic not in GENERIC_WRITER_OPERATIONS:
                        errors.append(
                            "%s.operation is not a registered generic writer "
                            "operation" % op_target)
                    canonical = ("generic", generic)
                    if canonical in local_seen:
                        errors.append(
                            "duplicate generic writer operation in %s: %r" %
                            (target, generic))
                    local_seen.add(canonical)
                    previous = seen_generic_writer_operations.get(generic)
                    if previous is not None:
                        errors.append(
                            "generic writer operation %s is implemented more "
                            "than once by %s and %s" %
                            (generic, previous, capability_id))
                    else:
                        seen_generic_writer_operations[generic] = capability_id
                    continue
                if not _closed_keys(
                        operation, WRITER_OPERATION_KEYS,
                        op_target, errors):
                    continue
                field = operation.get("field")
                transition = operation.get("transition")
                adapter = operation.get("source_adapter")
                _nonempty_id(field, FIELD_ID_RE, op_target + ".field", errors)
                _nonempty_id(transition, STABLE_ID_RE,
                             op_target + ".transition", errors)
                if adapter not in SOURCE_ADAPTERS:
                    errors.append("%s.source_adapter is not registered" %
                                  op_target)
                key = (field, transition)
                canonical = (field, transition, adapter)
                if canonical in local_seen:
                    errors.append("duplicate writer operation in %s: %r" %
                                  (target, canonical))
                local_seen.add(canonical)
                if key in seen_writer_operations:
                    previous = seen_writer_operations[key]
                    errors.append(
                        "writer operation %s/%s is implemented more than once "
                        "by %s and %s" %
                        (field, transition, previous, capability_id))
                else:
                    seen_writer_operations[key] = capability_id
            else:
                if not _closed_keys(
                        operation, CONSUMER_OPERATION_KEYS,
                        op_target, errors):
                    continue
                _nonempty_id(operation.get("operation"), STABLE_ID_RE,
                             op_target + ".operation", errors)
    return errors


def _validate_evidence(rule, target, errors):
    adapter = rule.get("source_adapter")
    spec = SOURCE_ADAPTERS.get(adapter)
    evidence = rule.get("evidence_requirement")
    if spec is None:
        return
    if not spec["evidence_required"]:
        if evidence is not None:
            errors.append("%s evidence_requirement must be null for %s" %
                          (target, adapter))
        return
    if not _closed_keys(evidence, EVIDENCE_KEYS,
                        target + ".evidence_requirement", errors):
        return
    for key in EVIDENCE_KEYS - {"excluded_change_classes"}:
        if not isinstance(evidence.get(key), str) or not evidence[key]:
            errors.append("%s.evidence_requirement.%s must be non-empty" %
                          (target, key))
    if evidence.get("result") != "pass":
        errors.append("%s evidence result must be pass" % target)
    excluded = evidence.get("excluded_change_classes")
    if (not isinstance(excluded, list) or
            any(not isinstance(item, str) for item in excluded) or
            len(excluded) != len(set(excluded))):
        errors.append("%s excluded_change_classes must be a unique string list"
                      % target)
        return
    if adapter == "content-change-event-v1":
        expected = ["projection-only", "tool-controlled-metadata-only"]
        if evidence.get("change_scope") != "semantic-content":
            errors.append("%s content-change scope must be semantic-content" %
                          target)
        if sorted(excluded) != sorted(expected):
            errors.append(
                "%s content-change exclusions must close projection-only and "
                "tool-controlled-metadata-only" % target)
    if adapter == "current-review-receipt-value-v1":
        if evidence.get("change_scope") != "reviewed-content":
            errors.append("%s review scope must be reviewed-content" % target)
        if excluded:
            errors.append("%s review receipt exclusions must be empty" % target)


def _validate_authority(document, capabilities):
    errors = []
    if not _closed_keys(document, TOP_KEYS, "metadata authority", errors):
        return errors
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append("metadata authority schema_version must be 1")
    _nonempty_id(document.get("contract_id"), STABLE_ID_RE,
                 "metadata authority contract_id", errors)
    temporal = document.get("temporal_order")
    if temporal != list(TEMPORAL_ORDER):
        errors.append(
            "metadata authority temporal_order must be first_seen -> "
            "last_content_modified -> last_reviewed -> last_verified")
    rules = document.get("field_rules")
    if not isinstance(rules, list) or not rules:
        errors.append("metadata authority field_rules must be a non-empty list")
        return errors

    seen_rules = {}
    field_shapes = {}
    for index, rule in enumerate(rules):
        target = "field_rules[%d]" % index
        required_rule_keys = RULE_KEYS - {"allowed_values"}
        if not _closed_keys(rule, required_rule_keys, target, errors,
                            optional={"allowed_values"}):
            continue
        field = rule.get("field")
        transition = rule.get("transition")
        adapter = rule.get("source_adapter")
        _nonempty_id(field, FIELD_ID_RE, target + ".field", errors)
        _nonempty_id(transition, STABLE_ID_RE,
                     target + ".transition", errors)
        for key in ("writer_capability", "write_timing", "reconcile_policy",
                    "invalidation_rule"):
            _nonempty_id(rule.get(key), STABLE_ID_RE,
                         target + "." + key, errors)
        if rule.get("reconcile_policy") not in RECONCILE_POLICIES:
            errors.append(
                "%s.reconcile_policy is not registered" % target)
        owner = rule.get("canonical_owner")
        if not isinstance(owner, str) or OWNER_RE.fullmatch(owner) is None:
            errors.append("%s.canonical_owner is not a canonical owner path" %
                          target)
        authority = rule.get("authority_class")
        if authority not in AUTHORITY_CLASSES:
            errors.append("%s.authority_class is not registered" % target)
        spec = SOURCE_ADAPTERS.get(adapter)
        if spec is None:
            errors.append("%s.source_adapter is not registered" % target)
        elif authority != spec["authority_class"]:
            errors.append(
                "%s authority_class does not match source adapter %s" %
                (target, adapter))
        value_shape = rule.get("value_shape")
        if value_shape not in VALUE_SHAPES:
            errors.append("%s.value_shape is not registered" % target)
        previous_shape = field_shapes.get(field)
        if previous_shape is not None and previous_shape != value_shape:
            errors.append("field %s has inconsistent value_shape" % field)
        else:
            field_shapes[field] = value_shape
        allowed_values = rule.get("allowed_values")
        if value_shape == "enum":
            if (not isinstance(allowed_values, list) or not allowed_values or
                    any(not isinstance(item, str) or not item
                        for item in allowed_values) or
                    len(allowed_values) != len(set(allowed_values))):
                errors.append(
                    "%s.allowed_values must be a non-empty unique string list "
                    "for enum" % target)
        elif "allowed_values" in rule and allowed_values is not None:
            errors.append(
                "%s.allowed_values is only permitted for enum" % target)
        key = (field, transition)
        if key in seen_rules:
            errors.append("duplicate field transition rule: %s/%s" % key)
        else:
            seen_rules[key] = rule
        _validate_evidence(rule, target, errors)

    # Installed writer capabilities and authority rules cover one another
    # exactly.  This makes the registry executable fact, not documentation.
    installed = {}
    for capability in capabilities.get("capabilities", []):
        if not isinstance(capability, dict) or capability.get("kind") != "writer":
            continue
        capability_id = capability.get("capability_id")
        for operation in capability.get("operations", []):
            if not isinstance(operation, dict):
                continue
            if set(operation) == CONSUMER_OPERATION_KEYS:
                continue
            key = (operation.get("field"), operation.get("transition"))
            installed[key] = (capability_id, operation.get("source_adapter"))
    for key, rule in seen_rules.items():
        fact = installed.get(key)
        expected = (rule.get("writer_capability"), rule.get("source_adapter"))
        if fact is None:
            errors.append("authority rule %s/%s has no installed writer" % key)
        elif fact != expected:
            errors.append(
                "authority rule %s/%s expects %s/%s but installed writer is "
                "%s/%s" % (key + expected + fact))
    for key, fact in installed.items():
        rule = seen_rules.get(key)
        if rule is None:
            errors.append("installed writer %s operation %s/%s is unauthorized" %
                          (fact[0], key[0], key[1]))
    return errors


def _normalized_capabilities(document, kind=None, kinds=None):
    result = []
    if kind is not None and kinds is not None:
        raise ValueError("kind and kinds are mutually exclusive")
    for entry in document["capabilities"]:
        if kind is not None and entry["kind"] != kind:
            continue
        if kinds is not None and entry["kind"] not in kinds:
            continue
        copied = copy.deepcopy(entry)
        for role in IMPLEMENTATION_ROLE_KEYS:
            copied[role] = sorted(copied[role])
        copied["operations"] = sorted(
            copied["operations"],
            key=lambda item: tuple(str(item[key]) for key in sorted(item)))
        result.append(copied)
    return sorted(result, key=lambda item: (
        item["kind"], item["capability_id"], item["capability_version"]))


def capability_implementation_paths(document):
    """Return the closed implementation-file set declared by capabilities.

    The caller may parse the capability registry from an already frozen input
    snapshot, call this pure function, and add the returned paths to that same
    snapshot boundary before compilation.  No filesystem access occurs here.
    """
    errors = _validate_capabilities(document)
    if errors:
        raise MetadataExecutionContractError(errors)
    paths = {
        entry["implementation_owner"]
        for entry in document["capabilities"]
    }
    paths.update(
        path
        for entry in document["capabilities"]
        for role in IMPLEMENTATION_ROLE_KEYS
        for path in entry[role]
    )
    paths.update(
        entry[INVOCATION_OWNER_KEY]
        for entry in document["capabilities"]
        if INVOCATION_OWNER_KEY in entry
    )
    return tuple(sorted(paths))


def capability_invocation_edge_errors(document, root=None):
    """Return public-adapter edges that do not close over declared roles.

    ``invocation_owner`` is intentionally not a writer/checker/consumer.  The
    adapter's literal implementation marker must instead point to the entry's
    implementation owner or to one of its actual implementation-role paths.
    This detects a stale wrapper without forcing that wrapper to masquerade as
    a business implementation or consumer.
    """
    errors = _validate_capabilities(document)
    if errors:
        return errors
    repository = _repository_root(root)
    tools_root = os.path.join(repository, "Tools")
    for index, entry in enumerate(document["capabilities"]):
        invocation_owner = entry.get(INVOCATION_OWNER_KEY)
        if invocation_owner is None:
            continue
        tool = os.path.basename(invocation_owner)[:-3]
        try:
            descriptor = entrypoint_loader.describe_entrypoint(
                tool, tools_root, require_marker=True)
        except entrypoint_loader.EntrypointResolutionError as exc:
            errors.append(
                "capabilities[%d].invocation_owner cannot resolve: %s" %
                (index, exc))
            continue
        allowed = {entry["implementation_owner"]}
        allowed.update(
            path for role in IMPLEMENTATION_ROLE_KEYS for path in entry[role])
        if descriptor.invocation_path != invocation_owner:
            errors.append(
                "capabilities[%d].invocation_owner resolves a different "
                "public adapter" % index)
        if descriptor.implementation_path not in allowed:
            errors.append(
                "capabilities[%d].invocation_owner implementation %s is not "
                "its owner, writer, checker, or consumer" %
                (index, descriptor.implementation_path))
    return errors


def metadata_execution_capability_implementation_paths(document):
    """Return only implementation paths owned by the metadata contract.

    ``operation-capabilities.yaml`` is the repository-wide Tool capability
    registry.  Projection capabilities are valid registry members and remain
    in Profile-load's root-owned input closure, but they are not silently
    absorbed into the compiled metadata-execution artifact.
    """
    errors = _validate_capabilities(document)
    if errors:
        raise MetadataExecutionContractError(errors)
    filtered = copy.deepcopy(document)
    filtered["capabilities"] = [
        entry for entry in filtered["capabilities"]
        if entry["kind"] in METADATA_EXECUTION_CAPABILITY_KINDS
    ]
    return capability_implementation_paths(filtered)


def _capability_implementation_records(capabilities,
                                       implementation_snapshots):
    paths = capability_implementation_paths(capabilities)
    if not isinstance(implementation_snapshots, dict):
        raise MetadataExecutionContractError([
            "capability implementation snapshots must be a path mapping"])
    records = []
    errors = []
    for path in paths:
        snapshot = implementation_snapshots.get(path)
        sha256 = snapshot if isinstance(snapshot, str) else getattr(
            snapshot, "sha256", None)
        repository_path = getattr(snapshot, "repository_path", path)
        if repository_path != path:
            errors.append(
                "capability implementation snapshot %s belongs to %s" %
                (path, repository_path))
            continue
        if not isinstance(sha256, str) or SHA256_RE.fullmatch(sha256) is None:
            errors.append(
                "capability implementation snapshot is missing or invalid: "
                "%s" % path)
            continue
        records.append({"path": path, "sha256": sha256})
    if errors:
        raise MetadataExecutionContractError(errors)
    return records


def _build_contract(document, capabilities, implementation_snapshots):
    errors = _validate_capabilities(capabilities)
    if not errors:
        errors.extend(_validate_authority(document, capabilities))
    if errors:
        raise MetadataExecutionContractError(errors)
    metadata_capabilities = copy.deepcopy(capabilities)
    metadata_capabilities["capabilities"] = [
        entry for entry in metadata_capabilities["capabilities"]
        if entry["kind"] in METADATA_EXECUTION_CAPABILITY_KINDS
    ]
    implementation_records = _capability_implementation_records(
        metadata_capabilities, implementation_snapshots)

    core = {
        "artifact": ARTIFACT,
        "schema_version": SCHEMA_VERSION,
        "contract_id": document["contract_id"],
        "temporal_order": list(TEMPORAL_ORDER),
        "source_adapters": [
            {"adapter_id": adapter_id, **copy.deepcopy(spec)}
            for adapter_id, spec in sorted(SOURCE_ADAPTERS.items())
        ],
        "field_rules": sorted(
            copy.deepcopy(document["field_rules"]),
            key=lambda item: (item["field"], item["transition"])),
        # The fingerprint binds current Gate producer, receipt-schema, and
        # consumer facts as well as writer facts.  ``writer_capabilities`` is
        # retained as a narrow convenience view for page projectors.
        "operation_capabilities": _normalized_capabilities(
            capabilities, kinds=METADATA_EXECUTION_CAPABILITY_KINDS),
        "writer_capabilities": _normalized_capabilities(
            capabilities, kind="writer"),
        "capability_implementations": implementation_records,
    }
    fingerprint = kblib.sha256_bytes(kblib.canonical_json_bytes(core))
    artifact = dict(core)
    artifact["contract_fingerprint"] = fingerprint
    canonical = kblib.canonical_json_bytes(artifact) + b"\n"
    return CompiledMetadataExecutionContract(
        artifact=artifact,
        field_rules=tuple(copy.deepcopy(artifact["field_rules"])),
        writer_capabilities=tuple(
            copy.deepcopy(artifact["writer_capabilities"])),
        contract_fingerprint=fingerprint,
        canonical_bytes=canonical,
    )


def load_operation_capabilities_snapshot(root=None, capabilities_path=None):
    """Return one validated capability document and its immutable snapshot."""

    repository = _repository_root(root)
    path = capabilities_path or DEFAULT_CAPABILITIES_PATH
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            path = candidate.resolve().relative_to(repository).as_posix()
        except ValueError as exc:
            raise MetadataExecutionContractError([
                "operation capabilities must stay inside the repository"
            ]) from exc
    try:
        snapshot = kblib.repository_file_snapshot(
            str(repository), str(path), singly_linked=True
        )
        document = kblib.parse_yaml_subset(snapshot.read_text())
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        raise MetadataExecutionContractError(
            ["operation capabilities could not be read: %s" % exc]
        ) from exc
    if not isinstance(document, dict):
        raise MetadataExecutionContractError([
            "operation capabilities must be a mapping"
        ])
    errors = _validate_capabilities(document)
    if not errors:
        errors.extend(capability_invocation_edge_errors(
            document, repository))
    if errors:
        raise MetadataExecutionContractError(errors)
    return document, snapshot


def load_operation_capabilities(root=None, capabilities_path=None):
    """Load and strictly validate the installed capability registry."""

    document, _snapshot = load_operation_capabilities_snapshot(
        root, capabilities_path
    )
    return document


def validate_operation_capabilities_document(document):
    """Validate and copy one already-snapshotted capability document.

    Profile-load uses this entry point so the Gate linker parses the exact
    bytes already included in its canonical input digest instead of reopening
    the registry through a second filesystem revision.
    """
    copied = copy.deepcopy(document)
    errors = _validate_capabilities(copied)
    if errors:
        raise MetadataExecutionContractError(errors)
    return copied


def capability_entry(capability_id, kind, root=None, capabilities_path=None):
    """Return one registered capability entry, or ``None``."""
    document = load_operation_capabilities(root, capabilities_path)
    for entry in document["capabilities"]:
        if (entry["capability_id"] == capability_id and
                entry["kind"] == kind):
            return copy.deepcopy(entry)
    return None


def capability_entry_by_id(capability_id, root=None, capabilities_path=None,
                           *, document=None):
    """Return the globally unique registered capability, or ``None``.

    ``document`` lets a caller resolve several related identities from one
    already validated registry snapshot.  This prevents a producer chain from
    combining entries read from different filesystem revisions.  Callers that
    do not already own a snapshot retain the normal load-and-validate path.
    """
    if document is None:
        document = load_operation_capabilities(root, capabilities_path)
    else:
        document = validate_operation_capabilities_document(document)
    matches = [entry for entry in document["capabilities"]
               if entry["capability_id"] == capability_id]
    if len(matches) > 1:
        raise MetadataExecutionContractError([
            "capability_id %s is not globally unique" % capability_id])
    return copy.deepcopy(matches[0]) if matches else None


def capability_invocation_tool(capability_id, root=None,
                               capabilities_path=None, *, document=None):
    """Resolve one capability's declared public Tool entrypoint name.

    The operation registry owns this implementation route.  Callers must not
    infer it from a similarly named module or maintain a private mapping.
    """
    entry = capability_entry_by_id(
        capability_id, root=root, capabilities_path=capabilities_path,
        document=document)
    if entry is None:
        raise ValueError("unknown Tool capability %s" % capability_id)
    path = entry.get(INVOCATION_OWNER_KEY)
    if (not isinstance(path, str) or
            INVOCATION_OWNER_RE.fullmatch(path) is None):
        raise ValueError(
            "Tool capability %s has no valid public invocation owner" %
            capability_id)
    return os.path.basename(path)[:-3]


def capability_registered(capability_id, kind, root=None,
                          capabilities_path=None):
    """Whether an exact ``(kind, id)`` capability is installed."""
    return capability_entry(
        capability_id, kind, root=root,
        capabilities_path=capabilities_path) is not None


def capability_supports(capability_id, operation, root=None,
                        capabilities_path=None, kind="consumer"):
    """Whether a registered capability declares an exact operation.

    ``operation`` may be a stable operation string (for consumer entries) or a
    closed operation mapping (for writer entries).  Mapping comparison is
    exact so a caller cannot silently omit field/source binding.
    """
    entry = capability_entry(
        capability_id, kind, root=root,
        capabilities_path=capabilities_path)
    if entry is None:
        return False
    wanted = ({"operation": operation} if isinstance(operation, str)
              else operation)
    return isinstance(wanted, dict) and wanted in entry["operations"]


def compiled_capability_supports(contract, capability_id, operation, *,
                                 kind="writer"):
    """Query one exact operation from an already compiled authority view."""
    if not isinstance(contract, CompiledMetadataExecutionContract):
        raise TypeError("contract must be a CompiledMetadataExecutionContract")
    wanted = ({"operation": operation} if isinstance(operation, str)
              else operation)
    if not isinstance(wanted, dict):
        return False
    entries = contract.artifact.get("operation_capabilities", ())
    matches = [
        entry for entry in entries
        if isinstance(entry, dict) and
        entry.get("capability_id") == capability_id and
        entry.get("kind") == kind
    ]
    return (len(matches) == 1 and
            wanted in matches[0].get("operations", ()))


def compiled_operation_owner(contract, operation, *, kind="writer"):
    """Return the unique installed capability that owns one operation."""
    if not isinstance(contract, CompiledMetadataExecutionContract):
        raise TypeError("contract must be a CompiledMetadataExecutionContract")
    wanted = ({"operation": operation} if isinstance(operation, str)
              else operation)
    if not isinstance(wanted, dict):
        raise ValueError("operation must be a string or closed mapping")
    matches = [
        entry.get("capability_id")
        for entry in contract.artifact.get("operation_capabilities", ())
        if isinstance(entry, dict) and entry.get("kind") == kind and
        wanted in entry.get("operations", ())
    ]
    if (len(matches) != 1 or not isinstance(matches[0], str) or
            STABLE_ID_RE.fullmatch(matches[0]) is None):
        raise ValueError(
            "installed %s operation %r must have exactly one capability owner"
            % (kind, operation))
    return matches[0]


def compile_metadata_execution_contract(root=None, authority_path=None,
                                        capabilities_path=None):
    """Compile Kernel authority plus installed capabilities in one bundle."""
    repository = _repository_root(root)
    authority = _parse_yaml(
        repository, authority_path or DEFAULT_AUTHORITY_PATH,
        "metadata authority")
    capabilities = load_operation_capabilities(
        repository, capabilities_path=capabilities_path)
    implementation_snapshots = {}
    # Metadata implementations are mostly siblings, so resolving them one at
    # a time re-lists the same handful of directories once per file.  This
    # block already means to read one consistent view -- that is what the
    # compiled artifact is -- so it says so.  Non-metadata projection
    # implementations remain in Profile-load's generic root-input closure but
    # are not consumed merely because this compiler shares the registry.
    with kblib.directory_listing_scope():
        for path in metadata_execution_capability_implementation_paths(
                capabilities):
            try:
                implementation_snapshots[path] = (
                    kblib.repository_file_snapshot(
                        repository, path, singly_linked=True))
            except (OSError, TypeError, UnicodeError, ValueError) as exc:
                raise MetadataExecutionContractError([
                    "capability implementation is unavailable or unstable: "
                    "%s (%s)" % (path, exc)]) from exc
    return _build_contract(
        authority, capabilities, implementation_snapshots)


def compile_metadata_execution_document(
        authority, capabilities, implementation_snapshots=None):
    """Compile already-frozen inputs without reopening implementation files.

    ``implementation_snapshots`` is the caller's canonical path-to-snapshot
    mapping.  Requiring it here keeps Profile load from compiling declarations
    against implementation bytes read from a later filesystem revision.
    """
    return _build_contract(
        copy.deepcopy(authority), copy.deepcopy(capabilities),
        implementation_snapshots)


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def _artifact_to_source(artifact):
    operation_capabilities = copy.deepcopy(
        artifact["operation_capabilities"])
    capabilities = {
        "schema_version": CAPABILITIES_SCHEMA_VERSION,
        "capabilities": operation_capabilities,
    }
    source = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": artifact["contract_id"],
        "temporal_order": copy.deepcopy(artifact["temporal_order"]),
        "field_rules": copy.deepcopy(artifact["field_rules"]),
    }
    snapshots = {
        item["path"]: item["sha256"]
        for item in artifact["capability_implementations"]
        if isinstance(item, dict) and
        set(item) == IMPLEMENTATION_RECORD_KEYS
    }
    return source, capabilities, snapshots


def load_metadata_execution_contract(root=None, path=None):
    """Load, fingerprint-check, and revalidate the compiled artifact."""
    repository = _repository_root(root)
    artifact_path = path or DEFAULT_COMPILED_PATH
    try:
        raw = _read_text(repository, artifact_path)
        artifact = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise MetadataExecutionContractError(
            ["compiled metadata contract could not be read: %s" % exc]) from exc
    errors = []
    if not _closed_keys(artifact, COMPILED_KEYS,
                        "compiled metadata contract", errors):
        raise MetadataExecutionContractError(errors)
    if artifact.get("artifact") != ARTIFACT:
        errors.append("compiled metadata contract artifact id is invalid")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        errors.append("compiled metadata contract schema_version must be 1")
    expected_adapters = [
        {"adapter_id": adapter_id, **copy.deepcopy(spec)}
        for adapter_id, spec in sorted(SOURCE_ADAPTERS.items())]
    if artifact.get("source_adapters") != expected_adapters:
        errors.append("compiled metadata contract source_adapters are invalid")
    operation_capabilities = artifact.get("operation_capabilities")
    if isinstance(operation_capabilities, list):
        expected_writer_view = [
            copy.deepcopy(item) for item in operation_capabilities
            if isinstance(item, dict) and item.get("kind") == "writer"]
        if artifact.get("writer_capabilities") != expected_writer_view:
            errors.append(
                "compiled metadata contract writer_capabilities view is stale")
    implementations = artifact.get("capability_implementations")
    if not isinstance(implementations, list):
        errors.append(
            "compiled metadata contract capability_implementations is invalid")
    else:
        seen_implementations = set()
        for index, implementation in enumerate(implementations):
            target = "capability_implementations[%d]" % index
            if not _closed_keys(
                    implementation, IMPLEMENTATION_RECORD_KEYS,
                    target, errors):
                continue
            path = implementation.get("path")
            sha256 = implementation.get("sha256")
            if (not isinstance(path, str) or not path or
                    path.startswith("/") or "\\" in path or
                    not path.startswith("Tools/") or
                    not path.endswith(".py") or
                    any(part in ("", ".", "..")
                        for part in path.split("/"))):
                errors.append("%s.path is not canonical" % target)
            elif path in seen_implementations:
                errors.append("duplicate capability implementation: %s" % path)
            seen_implementations.add(path)
            if (not isinstance(sha256, str) or
                    SHA256_RE.fullmatch(sha256) is None):
                errors.append("%s.sha256 is invalid" % target)
        if implementations != sorted(
                implementations,
                key=lambda item: item.get("path", "")
                if isinstance(item, dict) else ""):
            errors.append(
                "compiled capability implementations are not canonical")
    fingerprint = artifact.get("contract_fingerprint")
    core = {key: copy.deepcopy(value) for key, value in artifact.items()
            if key != "contract_fingerprint"}
    expected_fingerprint = kblib.sha256_bytes(
        kblib.canonical_json_bytes(core))
    if fingerprint != expected_fingerprint:
        errors.append("compiled metadata contract fingerprint mismatch")
    if errors:
        raise MetadataExecutionContractError(errors)
    source, capabilities, implementation_snapshots = _artifact_to_source(
        artifact)
    compiled = _build_contract(
        source, capabilities, implementation_snapshots)
    if compiled.artifact != artifact:
        raise MetadataExecutionContractError(
            ["compiled metadata contract is not canonical"])
    # A self-consistent artifact is still stale authority if either live
    # Kernel rules or the installed capability registry has changed.  Runtime
    # consumers only receive authorization when both representations agree.
    live = compile_metadata_execution_contract(repository)
    if live.canonical_bytes != compiled.canonical_bytes:
        raise MetadataExecutionContractError([
            "compiled metadata contract is stale relative to live authority "
            "or installed capabilities"])
    return compiled



def rules_for_capability(contract, capability_id):
    """Return deterministic rules authorized for one writer capability."""
    if not isinstance(contract, CompiledMetadataExecutionContract):
        raise TypeError("contract must be CompiledMetadataExecutionContract")
    return contract.rules_for_capability(capability_id)


def _write_compiled(contract, root, output_path):
    target = kblib.registered_repository_artifact_path(
        _repository_root(root), output_path, DEFAULT_COMPILED_PATH)
    kblib.atomic_write_text(target, contract.canonical_bytes.decode("utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(_repository_root()))
    parser.add_argument("--authority", default=DEFAULT_AUTHORITY_PATH)
    parser.add_argument("--capabilities", default=DEFAULT_CAPABILITIES_PATH)
    parser.add_argument("--output", default=DEFAULT_COMPILED_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = kblib.registered_repository_artifact_path(
            _repository_root(args.root), args.output, DEFAULT_COMPILED_PATH)
        contract = compile_metadata_execution_contract(
            args.root, args.authority, args.capabilities)
        if args.check:
            try:
                actual = kblib.read_bytes(output)
            except OSError:
                actual = b""
            if actual != contract.canonical_bytes:
                print("FAIL: compiled metadata contract is missing or stale",
                      file=sys.stderr)
                return 1
        else:
            _write_compiled(contract, args.root, args.output)
        print("PASS: %s (%s)" %
              (contract.contract_fingerprint, len(contract.field_rules)))
        return 0
    except (MetadataExecutionContractError, ValueError) as exc:
        errors = exc.errors if isinstance(
            exc, MetadataExecutionContractError) else [str(exc)]
        for error in errors:
            print("FAIL: " + error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
