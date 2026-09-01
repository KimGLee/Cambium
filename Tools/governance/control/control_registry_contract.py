"""Strict, runtime-independent reader for the K00 Control registry.

K00/12 owns the Gate selector, producer-position, and Standards-revalidation
closed contracts. This module validates and projects that YAML without
importing ``queue_runtime`` or any producer. Runtime producer conformance is a
separate consumer concern in ``queue_runtime.gate_registry``; Profile linking
needs only this independent, structurally valid Gate namespace.
"""
from Tools.platform.repository.repository import repository_source_root

import os
import re

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.common.primitives import nonempty_string


STANDARDS_GATE_REGISTRY_PATH = (
    "kernel/K00 Standards Control/control-registry.yaml")
CONTROL_REGISTRY_PROSE_PATH = (
    "kernel/K00 Standards Control/12 Control Registry.md")
_CONTROL_REQUIRED_FIELDS = {
    "schema_version", "registry_id", "semantic_owner",
    "registry_references", "closed_sets", "role_contracts", "gates",
}
_CONTROL_REFERENCE_FIELDS = {"audit_dimension_base"}
_CONTROL_CLOSED_SET_FIELDS = {
    "dimension_markers", "producer_availability_markers",
    "revalidation_roles", "claim_edges", "scope_protocols",
    "binding_protocols",
}
_GATE_FIELDS = {
    "gate_id", "tool", "tool_version", "check", "mode", "dimensions",
    "lifecycle", "revalidation_role", "revalidation_owner", "claim_edge",
    "scope_protocol", "binding_protocol",
}
_ROLE_CONTRACT_FIELDS = {
    "role", "claim_edge", "scope_protocol", "binding_protocol",
}
_GATE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


def _closed_string_list(value, label, errors):
    if (not isinstance(value, list) or not value or
            not all(nonempty_string(item) and item.strip() == item
                    for item in value)):
        errors.append("%s must be a non-empty unique string list" % label)
        return ()
    if len(value) != len(set(value)):
        errors.append("%s contains duplicate values" % label)
    return tuple(value)


def _closed_marker_mapping(value, expected_keys, label, errors):
    if not isinstance(value, dict) or set(value) != set(expected_keys):
        errors.append("%s marker fields are not closed" % label)
        return {}
    if not all(nonempty_string(item) and item.strip() == item
               for item in value.values()):
        errors.append("%s marker values must be non-empty strings" % label)
        return {}
    if len(set(value.values())) != len(value):
        errors.append("%s marker values must be unique" % label)
    return dict(value)


def parse_control_registry_document(document, *, audit_values=None,
                                    queue_states=None):
    """Validate one current K00/12 machine document.

    Returns ``(gate_registry, revalidation_capabilities, metadata, errors)``.
    Producer-module availability is deliberately outside this pure contract.
    """
    errors = []
    registry = {}
    capabilities = {}
    metadata = {}
    if not isinstance(document, dict) or \
            set(document) != _CONTROL_REQUIRED_FIELDS:
        missing = sorted(_CONTROL_REQUIRED_FIELDS - set(document or {})) \
            if isinstance(document, dict) else sorted(_CONTROL_REQUIRED_FIELDS)
        extra = sorted(set(document) - _CONTROL_REQUIRED_FIELDS) \
            if isinstance(document, dict) else []
        return {}, {}, {}, [
            "Control registry fields are not closed: missing=%s extra=%s" %
            (missing, extra)]
    if document.get("schema_version") != 1:
        errors.append("Control registry schema_version must be 1")
    if document.get("registry_id") != "cambium-control-registry":
        errors.append(
            "Control registry_id must be cambium-control-registry")
    if document.get("semantic_owner") != "K00/12":
        errors.append("Control registry semantic_owner must be K00/12")

    references = document.get("registry_references")
    if not isinstance(references, dict) or set(references) != \
            _CONTROL_REFERENCE_FIELDS:
        errors.append("Control registry references are not closed")
        references = {}
    if references.get("audit_dimension_base") != \
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH:
        errors.append(
            "Control registry audit_dimension_base reference must be %s" %
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH)

    closed = document.get("closed_sets")
    if not isinstance(closed, dict) or set(closed) != \
            _CONTROL_CLOSED_SET_FIELDS:
        errors.append("Control registry closed_sets fields are not closed")
        closed = {}
    dimension_markers = _closed_marker_mapping(
        closed.get("dimension_markers"),
        ("unnarrowed", "undimensioned"), "dimension_markers", errors)
    availability_markers = _closed_marker_mapping(
        closed.get("producer_availability_markers"),
        ("unscoped", "queue_exhausted"),
        "producer_availability_markers", errors)
    roles = frozenset(_closed_string_list(
        closed.get("revalidation_roles"), "revalidation_roles", errors))
    edges = frozenset(_closed_string_list(
        closed.get("claim_edges"), "claim_edges", errors))
    scopes = frozenset(_closed_string_list(
        closed.get("scope_protocols"), "scope_protocols", errors))
    bindings = frozenset(_closed_string_list(
        closed.get("binding_protocols"), "binding_protocols", errors))

    role_rows = document.get("role_contracts")
    role_contracts = {}
    if not isinstance(role_rows, list) or not role_rows:
        errors.append(
            "Control registry role_contracts must be a non-empty list")
        role_rows = []
    for index, row in enumerate(role_rows):
        if not isinstance(row, dict) or set(row) != _ROLE_CONTRACT_FIELDS:
            errors.append(
                "Control registry role contract %d fields are not closed" %
                index)
            continue
        role = row.get("role")
        if role not in roles:
            errors.append(
                "Control registry role contract %d has unknown role %r" %
                (index, role))
            continue
        if role in role_contracts:
            errors.append("Control registry repeats role contract %s" % role)
            continue
        contract = (row.get("claim_edge"), row.get("scope_protocol"),
                    row.get("binding_protocol"))
        if contract[0] not in edges:
            errors.append("Role %s has unknown claim edge %r" %
                          (role, contract[0]))
        if contract[1] not in scopes:
            errors.append("Role %s has unknown scope protocol %r" %
                          (role, contract[1]))
        if contract[2] not in bindings:
            errors.append("Role %s has unknown binding protocol %r" %
                          (role, contract[2]))
        role_contracts[role] = contract
    missing_roles = sorted(roles - set(role_contracts))
    if missing_roles:
        errors.append("Control registry omits role contract(s): %s" %
                      ", ".join(missing_roles))

    if audit_values is None:
        audit_values = {
            "base_receipt_dimensions":
                audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER,
        }
    base_dimensions = frozenset(
        audit_values.get("base_receipt_dimensions") or ())
    queue_states = frozenset(
        queue_states if queue_states is not None else
        runtime_state_contract.QUEUE_STATES)
    unscoped_positions = frozenset(availability_markers.values())

    gate_rows = document.get("gates")
    if not isinstance(gate_rows, list) or not gate_rows:
        errors.append("Control registry gates must be a non-empty list")
        gate_rows = []
    for index, row in enumerate(gate_rows):
        if not isinstance(row, dict) or set(row) != _GATE_FIELDS:
            errors.append(
                "Control registry Gate %d fields are not closed" % index)
            continue
        gate_id = row.get("gate_id")
        if not isinstance(gate_id, str) or \
                _GATE_ID_RE.fullmatch(gate_id) is None:
            errors.append("Control registry Gate %d has an invalid Gate ID" %
                          index)
            continue
        if gate_id in registry:
            errors.append("Control registry repeats Gate ID %s" % gate_id)
            continue
        scalar_fields = (
            "tool", "tool_version", "check", "mode", "revalidation_role",
            "revalidation_owner", "claim_edge", "scope_protocol",
            "binding_protocol",
        )
        if not all(nonempty_string(row.get(field))
                   for field in scalar_fields):
            errors.append("Gate ID %s has an empty scalar field" % gate_id)
            continue
        if any(row.get(field) == dimension_markers.get("unnarrowed")
               for field in ("tool", "tool_version", "check")):
            errors.append(
                "Gate ID %s Tool, Tool version, and Check must be exact" %
                gate_id)

        dimensions = _closed_string_list(
            row.get("dimensions"), "Gate ID %s dimensions" % gate_id,
            errors)
        dimension_marker_values = frozenset(dimension_markers.values())
        selected_markers = set(dimensions) & dimension_marker_values
        if selected_markers and len(dimensions) != 1:
            errors.append(
                "Gate ID %s mixes a Dimension marker with named dimensions" %
                gate_id)
        unknown_dimensions = sorted(
            set(dimensions) - base_dimensions - dimension_marker_values)
        if unknown_dimensions:
            errors.append(
                "Gate ID %s registers unknown K12 receipt dimension(s): %s" %
                (gate_id, ", ".join(unknown_dimensions)))

        lifecycle = _closed_string_list(
            row.get("lifecycle"), "Gate ID %s lifecycle" % gate_id, errors)
        selected_positions = set(lifecycle) & unscoped_positions
        if selected_positions and len(lifecycle) != 1:
            errors.append(
                "Gate ID %s mixes a producer-availability marker with "
                "another position" % gate_id)
        unknown_positions = sorted(
            set(lifecycle) - queue_states - unscoped_positions)
        if unknown_positions:
            errors.append(
                "Gate ID %s registers unknown producer position(s): %s" %
                (gate_id, ", ".join(unknown_positions)))

        role = row.get("revalidation_role")
        edge = row.get("claim_edge")
        scope = row.get("scope_protocol")
        binding = row.get("binding_protocol")
        if role not in roles:
            errors.append("Gate ID %s has unknown revalidation role %s" %
                          (gate_id, role))
        expected_contract = role_contracts.get(role)
        if expected_contract is not None and \
                (edge, scope, binding) != expected_contract:
            errors.append(
                "Gate ID %s role %s requires claim/scope/binding %s/%s/%s, "
                "found %s/%s/%s" %
                (gate_id, role, *expected_contract, edge, scope, binding))
        if edge not in edges:
            errors.append("Gate ID %s has unknown claim edge %s" %
                          (gate_id, edge))
        if scope not in scopes:
            errors.append("Gate ID %s has unknown scope protocol %s" %
                          (gate_id, scope))
        if binding not in bindings:
            errors.append("Gate ID %s has unknown binding protocol %s" %
                          (gate_id, binding))

        registry[gate_id] = {
            "tool": row["tool"],
            "tool_version": str(row["tool_version"]),
            "check": row["check"],
            "mode": row["mode"],
            "dimensions": tuple(sorted(dimensions)),
            "lifecycle_states": tuple(sorted(lifecycle)),
        }
        capabilities[gate_id] = {
            "role": role,
            "owner": row["revalidation_owner"],
            "claim_edge": edge,
            "scope_protocol": scope,
            "binding_protocol": binding,
        }

    for gate_id, capability in sorted(capabilities.items()):
        role = capability["role"]
        owner = capability["owner"]
        if role in ("special-owner", "immediate-owner", "native-owner"):
            if owner != gate_id:
                errors.append(
                    "Revalidation owner Gate %s must own itself, not %s" %
                    (gate_id, owner))
        elif role == "semantic-leaf":
            owner_capability = capabilities.get(owner)
            if owner == gate_id or not isinstance(owner_capability, dict) or \
                    owner_capability.get("role") not in (
                        "special-owner", "immediate-owner", "native-owner"):
                errors.append(
                    "Revalidation semantic leaf %s must project to a distinct "
                    "boundary owner; found %s" % (gate_id, owner))
        elif owner != "none":
            errors.append(
                "Revalidation Gate %s role %s must use owner none, not %s" %
                (gate_id, role, owner))

    metadata = {
        "dimension_markers": dimension_markers,
        "producer_availability_markers": availability_markers,
        "roles": roles,
        "role_contracts": role_contracts,
    }
    return registry, capabilities, metadata, errors


def parse_standards_gate_registry(text):
    """Parse the current YAML authority without producer checks."""
    try:
        document = kblib.parse_yaml_subset(text)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        return {}, ["Control registry YAML is invalid: %s" % exc]
    registry, _capabilities, _metadata, errors = \
        parse_control_registry_document(document)
    return registry, errors


_REPOSITORY_ROOT = repository_source_root(__file__)
try:
    _SHIPPED_CONTROL_DOCUMENT = kblib.parse_yaml_subset(kblib.read_text(
        os.path.join(
            _REPOSITORY_ROOT, *STANDARDS_GATE_REGISTRY_PATH.split("/"))))
    (_SHIPPED_GATE_REGISTRY, _SHIPPED_CAPABILITIES,
     _SHIPPED_CONTROL_METADATA, _SHIPPED_CONTROL_ERRORS) = \
        parse_control_registry_document(_SHIPPED_CONTROL_DOCUMENT)
except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
    raise RuntimeError("cannot load shipped Control registry: %s" % exc)
if _SHIPPED_CONTROL_ERRORS:
    raise RuntimeError(
        "shipped Control registry is invalid: %s" %
        "; ".join(_SHIPPED_CONTROL_ERRORS))

BASE_RECEIPT_DIMENSIONS = audit_dimension_contract.BASE_RECEIPT_DIMENSIONS
UNDIMENSIONED_GATE = \
    _SHIPPED_CONTROL_METADATA["dimension_markers"]["undimensioned"]
UNNARROWED_GATE_DIMENSION = \
    _SHIPPED_CONTROL_METADATA["dimension_markers"]["unnarrowed"]
NOT_BATCH_SCOPED_GATE = _SHIPPED_CONTROL_METADATA[
    "producer_availability_markers"]["unscoped"]
QUEUE_EXHAUSTED_GATE = _SHIPPED_CONTROL_METADATA[
    "producer_availability_markers"]["queue_exhausted"]
UNSCOPED_GATE_POSITIONS = frozenset(
    _SHIPPED_CONTROL_METADATA["producer_availability_markers"].values())


def load_current_control_contract(root):
    """Return one current validated YAML contract; never consult Markdown."""
    try:
        audit_values = audit_dimension_contract.current_audit_dimension_values(
            root)
        path = kblib.repository_path(
            root, STANDARDS_GATE_REGISTRY_PATH, must_exist=True,
            reject_symlink=True)
        with open(path, encoding="utf-8") as handle:
            document = kblib.parse_yaml_subset(handle.read())
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        return {}, {}, {}, [
            "Control registry is unsafe, unreadable, or invalid: %s" % exc]
    registry, capabilities, metadata, errors = \
        parse_control_registry_document(document, audit_values=audit_values)
    if document != _SHIPPED_CONTROL_DOCUMENT:
        errors.append(
            "adopting Control registry differs from the validator's deployed "
            "Kernel contract")
    return registry, capabilities, metadata, errors


__all__ = [
    'BASE_RECEIPT_DIMENSIONS',
    'NOT_BATCH_SCOPED_GATE',
    'QUEUE_EXHAUSTED_GATE',
    'STANDARDS_GATE_REGISTRY_PATH',
    'UNDIMENSIONED_GATE',
    'UNNARROWED_GATE_DIMENSION',
    'load_current_control_contract',
    'parse_standards_gate_registry',
]
