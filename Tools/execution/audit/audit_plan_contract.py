"""Strict loader for the Kernel-owned K12/19 AuditPlan contract.

The YAML contract owns the closed fields and values.  This module provides
only mechanical loading, validation, and deterministic projections used by
AuditPlan producers and consumers.
"""
from Tools.platform.repository.repository import repository_source_root

import os
import re

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import require_trimmed_string


AUDIT_PLAN_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/audit-plan-contract.yaml")
_CONTRACT_FIELDS = {
    "schema_version", "contract_id", "semantic_owner", "producer_binding",
    "registry_references", "fields", "obligation_fields", "partitions",
    "due_stage_values", "evidence_kind_values", "owner_kind_values",
    "kernel_extension_point_values", "fingerprint_binding_values",
    "obligation_status_values",
}
_REGISTRY_REFERENCE_FIELDS = {"audit_dimension_base"}
_FIELD_SPEC_FIELDS = {"field", "type", "nullable"}
_FIELD_TYPES = frozenset((
    "integer", "string", "sha256", "utc-timestamp", "obligation-list",
))
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_UTC_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z\Z")


def closed_string_list(value, label):
    """Return one validated ordered closed string tuple."""
    if (not isinstance(value, list) or not value or
            any(not isinstance(item, str) or not item or
                item.strip() != item for item in value)):
        raise ValueError("%s must be a non-empty string list" % label)
    if len(value) != len(set(value)):
        raise ValueError("%s must not contain duplicate values" % label)
    return tuple(value)


def field_specs(value, label, *, allowed_types):
    """Validate shared field-spec rows and return their order and mapping."""
    if not isinstance(value, list) or not value:
        raise ValueError("%s must be a non-empty field list" % label)
    specs = {}
    order = []
    for index, row in enumerate(value):
        item_label = "%s[%d]" % (label, index)
        if not isinstance(row, dict) or set(row) != _FIELD_SPEC_FIELDS:
            raise ValueError("%s fields are not closed" % item_label)
        field = require_trimmed_string(
            row.get("field"), item_label + ".field")
        if field in specs:
            raise ValueError("%s repeats field %s" % (label, field))
        type_id = row.get("type")
        if type_id not in allowed_types:
            raise ValueError("%s has unknown type %r" % (item_label, type_id))
        if not isinstance(row.get("nullable"), bool):
            raise ValueError("%s.nullable must be boolean" % item_label)
        specs[field] = {"type": type_id, "nullable": row["nullable"]}
        order.append(field)
    return tuple(order), specs


def _canonical_evidence_roles(root=None, snapshots=None):
    """Resolve roles from the canonical registry without redeclaring them."""
    registry_path = audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH
    has_snapshot = snapshots is not None and registry_path in snapshots
    has_root_copy = root is not None and os.path.isfile(os.path.join(
        os.fspath(root), *registry_path.split("/")))
    if has_snapshot or has_root_copy:
        return audit_dimension_contract.current_audit_dimension_values(
            root, snapshots=snapshots)["evidence_roles"]
    return audit_dimension_contract.EVIDENCE_ROLES


def validate_contract(document, *, root=None, snapshots=None):
    """Validate one AuditPlan contract and return its machine projections."""
    if not isinstance(document, dict) or set(document) != _CONTRACT_FIELDS:
        raise ValueError("AuditPlan contract fields are not closed")
    if document.get("schema_version") != 2:
        raise ValueError("AuditPlan contract schema_version must be 2")
    if document.get("contract_id") != "cambium-audit-plan":
        raise ValueError("AuditPlan contract_id must be cambium-audit-plan")
    if document.get("semantic_owner") != "K12/19":
        raise ValueError("AuditPlan semantic_owner must be K12/19")
    if document.get("producer_binding") != \
            "exactly-one-of-capability-or-gate":
        raise ValueError(
            "AuditPlan producer_binding must require exactly one stable "
            "producer reference")
    references = document.get("registry_references")
    if (not isinstance(references, dict) or
            set(references) != _REGISTRY_REFERENCE_FIELDS):
        raise ValueError(
            "AuditPlan registry_references fields are not closed")
    if references.get("audit_dimension_base") != \
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH:
        raise ValueError(
            "AuditPlan audit_dimension_base reference must be %s" %
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH)
    evidence_roles = _canonical_evidence_roles(
        root=root, snapshots=snapshots)
    field_order, fields = field_specs(
        document.get("fields"), "fields", allowed_types=_FIELD_TYPES)
    obligation_order, obligation_fields = field_specs(
        document.get("obligation_fields"), "obligation_fields",
        allowed_types=frozenset(("integer", "string", "sha256",
                                 "utc-timestamp")))
    partitions = closed_string_list(document.get("partitions"), "partitions")
    due_stages = closed_string_list(
        document.get("due_stage_values"), "due_stage_values")
    evidence_kinds = closed_string_list(
        document.get("evidence_kind_values"), "evidence_kind_values")
    owner_kinds = closed_string_list(
        document.get("owner_kind_values"), "owner_kind_values")
    extension_points = closed_string_list(
        document.get("kernel_extension_point_values"),
        "kernel_extension_point_values")
    fingerprint_bindings = closed_string_list(
        document.get("fingerprint_binding_values"),
        "fingerprint_binding_values")
    statuses = closed_string_list(
        document.get("obligation_status_values"),
        "obligation_status_values")
    return {
        "field_order": field_order,
        "fields": fields,
        "obligation_field_order": obligation_order,
        "obligation_fields": obligation_fields,
        "partitions": partitions,
        "due_stages": frozenset(due_stages),
        "evidence_roles": evidence_roles,
        "evidence_kinds": frozenset(evidence_kinds),
        "owner_kinds": frozenset(owner_kinds),
        "extension_points": frozenset(extension_points),
        "fingerprint_bindings": frozenset(fingerprint_bindings),
        "statuses": frozenset(statuses),
    }


def load_contract(root=None, snapshots=None):
    """Load the current Kernel-owned AuditPlan contract."""
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(AUDIT_PLAN_CONTRACT_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        text = kblib.read_text(os.path.join(
            root, *AUDIT_PLAN_CONTRACT_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_contract(document, root=root, snapshots=snapshots)
    return document


def is_sha256(value):
    """Return whether ``value`` is the canonical sha256-prefixed form."""
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def validate_value(value, spec, label):
    """Validate one value against a shared machine-contract field spec."""
    if value is None:
        if spec["nullable"]:
            return
        raise ValueError("%s must not be null" % label)
    type_id = spec["type"]
    if type_id == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("%s must be a non-negative integer" % label)
    elif type_id == "string":
        require_trimmed_string(value, label)
    elif type_id == "sha256":
        if not is_sha256(value):
            raise ValueError("%s must be sha256:<64 lowercase hex>" % label)
    elif type_id == "utc-timestamp":
        if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
            raise ValueError("%s must be a UTC timestamp ending in Z" % label)
    elif type_id == "string-list":
        closed_string_list(value, label)
    elif type_id != "obligation-list":
        raise ValueError("%s has unsupported contract type %s" %
                         (label, type_id))


def _dimension_allowed(dimension, dimensions):
    if dimensions is None:
        return True
    return dimension in set(dimensions)


def validate_plan(plan, contract=None, dimensions=None):
    """Validate one closed AuditPlan instance and return it unchanged."""
    contract = contract or _SHIPPED_CONTRACT
    values = validate_contract(contract)
    if not isinstance(plan, dict) or set(plan) != set(values["fields"]):
        raise ValueError("AuditPlan fields are not closed")
    for field, spec in values["fields"].items():
        if field != "obligations":
            validate_value(plan.get(field), spec, "AuditPlan.%s" % field)
    if plan.get("schema_version") != contract["schema_version"]:
        raise ValueError(
            "AuditPlan schema_version must equal its Kernel contract")
    obligations = plan.get("obligations")
    if not isinstance(obligations, list) or not obligations:
        raise ValueError("AuditPlan.obligations must be a non-empty list")
    obligation_ids = []
    for index, obligation in enumerate(obligations):
        label = "AuditPlan.obligations[%d]" % index
        if (not isinstance(obligation, dict) or
                set(obligation) != set(values["obligation_fields"])):
            raise ValueError("%s fields are not closed" % label)
        for field, spec in values["obligation_fields"].items():
            validate_value(obligation.get(field), spec,
                            "%s.%s" % (label, field))
        obligation_id = obligation["obligation_id"]
        if obligation_id in obligation_ids:
            raise ValueError("AuditPlan repeats obligation_id %s" % obligation_id)
        obligation_ids.append(obligation_id)
        if obligation["partition"] not in values["partitions"]:
            raise ValueError("%s.partition is not registered" % label)
        if obligation["due_stage"] not in values["due_stages"]:
            raise ValueError("%s.due_stage is not registered" % label)
        if obligation["evidence_role"] not in values["evidence_roles"]:
            raise ValueError("%s.evidence_role is not registered" % label)
        if obligation["evidence_kind"] not in values["evidence_kinds"]:
            raise ValueError("%s.evidence_kind is not registered" % label)
        if obligation["owner_kind"] not in values["owner_kinds"]:
            raise ValueError("%s.owner_kind is not registered" % label)
        if obligation["fingerprint_binding"] not in \
                values["fingerprint_bindings"]:
            raise ValueError("%s.fingerprint_binding is not registered" % label)
        if obligation["status"] not in values["statuses"]:
            raise ValueError("%s.status is not registered" % label)
        if (obligation["dimension"] is not None and
                not _dimension_allowed(obligation["dimension"], dimensions)):
            raise ValueError("%s.dimension is not registered" % label)
        capability = obligation.get("producer_capability")
        gate_id = obligation.get("producer_gate_id")
        if (capability is None) == (gate_id is None):
            raise ValueError(
                "%s must bind exactly one producer capability or Gate" % label)
        if obligation["owner_kind"] == "kernel":
            if obligation.get("kernel_extension_point") is not None:
                raise ValueError(
                    "%s kernel obligation cannot claim an extension point" %
                    label)
        elif obligation.get("kernel_extension_point") not in \
                values["extension_points"]:
            raise ValueError(
                "%s Profile obligation requires a registered Kernel "
                "extension point" % label)
        if (obligation["evidence_kind"] == "audit-receipt" and
                (obligation["evidence_role"] != "emits" or
                 obligation.get("dimension") is None)):
            raise ValueError(
                "%s AuditReceipt obligation must emit exactly one dimension" %
                label)
        reuse_values = tuple(obligation.get(field) for field in (
            "evidence_ref", "reused_receipt_id", "reuse_reason"))
        if obligation["status"] == "required":
            if any(value is not None for value in reuse_values):
                raise ValueError(
                    "%s required obligation must not predeclare evidence" %
                    label)
            if obligation["partition"] == "reusable-evidence":
                raise ValueError(
                    "%s required obligation cannot use reusable-evidence" %
                    label)
            if obligation["fingerprint_binding"] != "evidence-time":
                raise ValueError(
                    "%s required obligation binds fingerprints at evidence "
                    "time" % label)
        else:
            if any(value is None for value in reuse_values):
                raise ValueError(
                    "%s reused obligation requires evidence and rationale" %
                    label)
            if obligation["partition"] != "reusable-evidence":
                raise ValueError(
                    "%s reused obligation must use reusable-evidence" % label)
            if obligation["evidence_ref"] != obligation["reused_receipt_id"]:
                raise ValueError(
                    "%s reused evidence_ref must equal reused_receipt_id" %
                    label)
            if obligation["fingerprint_binding"] != "reused-receipt":
                raise ValueError(
                    "%s reused obligation must bind the reused receipt's "
                    "fingerprints" % label)
    if obligation_ids != sorted(obligation_ids):
        raise ValueError("AuditPlan obligations must be ordered by obligation_id")
    return plan


def plan_sha256(plan, contract=None, dimensions=None):
    """Return the hash of the canonical serialized AuditPlan bytes."""
    validate_plan(plan, contract=contract, dimensions=dimensions)
    return kblib.sha256_bytes(kblib.canonical_yaml(plan).encode("utf-8"))


def contract_snapshot_sha256(*, task_id, upstream_revision_id,
                             active_standards_sha256,
                             selected_profile_manifest,
                             profile_snapshot_sha256,
                             profile_contract_fingerprint,
                             opening_transition_receipt,
                             accepted_baseline_sha256, obligations):
    """Hash the frozen authority and obligation-definition material.

    The producer and every later consumer use this one mechanical projection;
    the hash is not a substitute for a publication anchor, but it detects
    accidental definition drift without a second field-filter implementation.
    """
    if not isinstance(obligations, list) or not obligations:
        raise ValueError("contract snapshot obligations must be non-empty")
    excluded = {
        "obligation_id", "status", "evidence_ref",
        "reused_receipt_id", "reuse_reason",
    }
    material = {
        "task_id": task_id,
        "upstream_revision_id": upstream_revision_id,
        "active_standards_sha256": active_standards_sha256,
        "selected_profile_manifest": selected_profile_manifest,
        "profile_snapshot_sha256": profile_snapshot_sha256,
        "profile_contract_fingerprint": profile_contract_fingerprint,
        "opening_transition_receipt": opening_transition_receipt,
        "accepted_baseline_sha256": accepted_baseline_sha256,
        "obligation_definitions": [
            {field: value for field, value in row.items()
             if field not in excluded}
            for row in obligations
        ],
    }
    return kblib.sha256_bytes(kblib.canonical_json_bytes(material))


def plan_contract_snapshot_sha256(plan):
    """Recompute the internal definition snapshot carried by one plan."""
    if not isinstance(plan, dict):
        raise ValueError("AuditPlan must be a mapping")
    return contract_snapshot_sha256(
        task_id=plan.get("task_id"),
        upstream_revision_id=plan.get("upstream_revision_id"),
        active_standards_sha256=plan.get("active_standards_sha256"),
        selected_profile_manifest=plan.get("selected_profile_manifest"),
        profile_snapshot_sha256=plan.get("profile_snapshot_sha256"),
        profile_contract_fingerprint=plan.get(
            "profile_contract_fingerprint"),
        opening_transition_receipt=plan.get(
            "opening_transition_receipt"),
        accepted_baseline_sha256=plan.get("accepted_baseline_sha256"),
        obligations=plan.get("obligations"),
    )


def required_obligation_ids(plan, contract=None, dimensions=None):
    """Return ordered obligations that require newly produced evidence."""
    validate_plan(plan, contract=contract, dimensions=dimensions)
    return tuple(row["obligation_id"] for row in plan["obligations"]
                 if row["status"] == "required")


_SHIPPED_CONTRACT = load_contract()
_SHIPPED_VALUES = validate_contract(_SHIPPED_CONTRACT)
PLAN_FIELDS = _SHIPPED_VALUES["field_order"]
OBLIGATION_FIELDS = _SHIPPED_VALUES["obligation_field_order"]
PARTITION_IDS = _SHIPPED_VALUES["partitions"]
AUDIT_DUE_STAGES = _SHIPPED_VALUES["due_stages"]
AUDIT_EVIDENCE_KINDS = _SHIPPED_VALUES["evidence_kinds"]
OBLIGATION_STATUS_VALUES = _SHIPPED_VALUES["statuses"]


__all__ = [
    'AUDIT_PLAN_CONTRACT_PATH',
    'closed_string_list',
    'contract_snapshot_sha256',
    'field_specs',
    'is_sha256',
    'load_contract',
    'plan_contract_snapshot_sha256',
    'plan_sha256',
    'required_obligation_ids',
    'validate_contract',
    'validate_plan',
    'validate_value',
]
