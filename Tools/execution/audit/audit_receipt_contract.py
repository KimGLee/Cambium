"""Strict loader for the Kernel-owned K12/07 full AuditReceipt contract."""
from Tools.platform.repository.repository import repository_source_root

import os

import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.audit_plan_contract as _support
import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import require_trimmed_string


AUDIT_RECEIPT_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/audit-receipt-contract.yaml")
RECEIPT_TYPE_ID = "audit-receipt-v3"
_CONTRACT_FIELDS = {
    "schema_version", "contract_id", "semantic_owner", "record_kind",
    "fingerprint_phase", "dimension_requirement", "producer_binding",
    "page_artifact_fingerprint", "fields", "result_values",
    "due_stage_values", "evidence_role_values", "evidence_kind_values",
    "owner_kind_values",
    "fingerprint_binding_values", "fingerprint_fields", "reuse_fields",
}
_PAGE_ARTIFACT_FIELDS = {
    "protocol_id", "digest_serialization", "page_material_fields",
    "path_binding", "body_binding",
    "frontmatter_normalization", "included_frontmatter_fields",
    "excluded_frontmatter_policy", "absent_included_field_policy",
    "opening_frontmatter_marker", "closing_frontmatter_markers",
    "page_set_protocol_id", "page_set_material_fields",
    "page_set_member_fields", "page_set_order",
}
_FIELD_TYPES = frozenset((
    "integer", "string", "sha256", "utc-timestamp", "string-list",
))
_SUPPORTED_PAGE_ARTIFACT = {
    "protocol_id": "cambium-page-artifact-v1",
    "digest_serialization": "sha256-prefixed-canonical-json-utf8",
    "page_material_fields": ("protocol_id", "path", "frontmatter", "body"),
    "path_binding": "canonical-repository-relative-posix",
    "body_binding": "exact-bytes-after-frontmatter",
    "frontmatter_normalization": "restricted-yaml-semantic",
    "included_frontmatter_fields": (
        "type", "priority", "tier", "coverage_disposition", "lifecycle",
        "prerequisites",
    ),
    "excluded_frontmatter_policy": "all-other-fields",
    "absent_included_field_policy": "omit",
    "opening_frontmatter_marker": "---",
    "closing_frontmatter_markers": ("---", "..."),
    "page_set_protocol_id": "cambium-page-artifact-set-v1",
    "page_set_material_fields": ("protocol_id", "members"),
    "page_set_member_fields": ("path", "artifact_fingerprint"),
    "page_set_order": "canonical-path-ascending",
}


def validate_contract(document):
    """Validate one full AuditReceipt contract and return projections."""
    if not isinstance(document, dict) or set(document) != _CONTRACT_FIELDS:
        raise ValueError("AuditReceipt contract fields are not closed")
    if document.get("schema_version") != 3:
        raise ValueError("AuditReceipt contract schema_version must be 3")
    if document.get("contract_id") != "cambium-audit-receipt":
        raise ValueError(
            "AuditReceipt contract_id must be cambium-audit-receipt")
    if document.get("semantic_owner") != "K12/07-K12/08":
        raise ValueError("AuditReceipt semantic_owner must be K12/07-K12/08")
    if document.get("record_kind") != "audit-receipt":
        raise ValueError("AuditReceipt record_kind must be audit-receipt")
    if document.get("fingerprint_phase") != "evidence-time":
        raise ValueError("AuditReceipt fingerprints must bind evidence time")
    if document.get("dimension_requirement") != "registered-non-null":
        raise ValueError("AuditReceipt dimension must be registered and non-null")
    if document.get("producer_binding") != \
            "exactly-one-of-capability-or-gate":
        raise ValueError(
            "AuditReceipt must bind exactly one stable producer reference")
    page_artifact = document.get("page_artifact_fingerprint")
    if (not isinstance(page_artifact, dict) or
            set(page_artifact) != _PAGE_ARTIFACT_FIELDS):
        raise ValueError(
            "page artifact fingerprint contract fields are not closed")
    for field in _PAGE_ARTIFACT_FIELDS - {
            "included_frontmatter_fields", "page_material_fields",
            "closing_frontmatter_markers", "page_set_material_fields",
            "page_set_member_fields"}:
        require_trimmed_string(
            page_artifact.get(field),
            "page_artifact_fingerprint.%s" % field)
    included_fields = _support.closed_string_list(
        page_artifact.get("included_frontmatter_fields"),
        "page_artifact_fingerprint.included_frontmatter_fields")
    page_material_fields = _support.closed_string_list(
        page_artifact.get("page_material_fields"),
        "page_artifact_fingerprint.page_material_fields")
    closing_markers = _support.closed_string_list(
        page_artifact.get("closing_frontmatter_markers"),
        "page_artifact_fingerprint.closing_frontmatter_markers")
    page_set_material_fields = _support.closed_string_list(
        page_artifact.get("page_set_material_fields"),
        "page_artifact_fingerprint.page_set_material_fields")
    page_set_member_fields = _support.closed_string_list(
        page_artifact.get("page_set_member_fields"),
        "page_artifact_fingerprint.page_set_member_fields")
    normalized_page_artifact = {
        **page_artifact,
        "included_frontmatter_fields": included_fields,
        "closing_frontmatter_markers": closing_markers,
        "page_material_fields": page_material_fields,
        "page_set_material_fields": page_set_material_fields,
        "page_set_member_fields": page_set_member_fields,
    }
    for field, supported in _SUPPORTED_PAGE_ARTIFACT.items():
        if normalized_page_artifact.get(field) != supported:
            qualifier = " supported ordered closed set" if isinstance(
                supported, tuple) else " supported value"
            raise ValueError(
                "page_artifact_fingerprint.%s must equal its%s" %
                (field, qualifier))
    field_order, fields = _support.field_specs(
        document.get("fields"), "fields", allowed_types=_FIELD_TYPES)
    result_values = _support.closed_string_list(
        document.get("result_values"), "result_values")
    due_stages = _support.closed_string_list(
        document.get("due_stage_values"), "due_stage_values")
    roles = _support.closed_string_list(
        document.get("evidence_role_values"), "evidence_role_values")
    kinds = _support.closed_string_list(
        document.get("evidence_kind_values"), "evidence_kind_values")
    owner_kinds = _support.closed_string_list(
        document.get("owner_kind_values"), "owner_kind_values")
    fingerprint_bindings = _support.closed_string_list(
        document.get("fingerprint_binding_values"),
        "fingerprint_binding_values")
    fingerprint_fields = _support.closed_string_list(
        document.get("fingerprint_fields"), "fingerprint_fields")
    reuse_fields = _support.closed_string_list(
        document.get("reuse_fields"), "reuse_fields")
    return {
        "field_order": field_order,
        "fields": fields,
        "result_values": frozenset(result_values),
        "due_stages": frozenset(due_stages),
        "roles": frozenset(roles),
        "kinds": frozenset(kinds),
        "owner_kinds": frozenset(owner_kinds),
        "fingerprint_bindings": frozenset(fingerprint_bindings),
        "fingerprint_fields": tuple(fingerprint_fields),
        "reuse_fields": tuple(reuse_fields),
        "page_artifact_fingerprint": normalized_page_artifact,
    }


def load_contract(root=None, snapshots=None):
    """Load the current Kernel-owned full AuditReceipt contract."""
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(AUDIT_RECEIPT_CONTRACT_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        text = kblib.read_text(os.path.join(
            root, *AUDIT_RECEIPT_CONTRACT_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_contract(document)
    return document


def page_artifact_fingerprint_contract(contract=None):
    """Return the validated K12/07 page-artifact protocol projection."""
    contract = contract or _SHIPPED_CONTRACT
    return validate_contract(contract)["page_artifact_fingerprint"]


def validate_audit_receipt(record, contract=None, dimensions=None):
    """Validate one closed full AuditReceipt and return it unchanged."""
    contract = contract or _SHIPPED_CONTRACT
    values = validate_contract(contract)
    if not isinstance(record, dict) or set(record) != set(values["fields"]):
        raise ValueError("AuditReceipt fields are not closed")
    for field, spec in values["fields"].items():
        _support.validate_value(
            record.get(field), spec, "AuditReceipt.%s" % field)
    if record.get("schema_version") != contract["schema_version"]:
        raise ValueError(
            "AuditReceipt schema_version must equal its Kernel contract")
    if record.get("record_kind") != contract["record_kind"]:
        raise ValueError("AuditReceipt record_kind is invalid")
    if record.get("receipt_type_id") != RECEIPT_TYPE_ID:
        raise ValueError("AuditReceipt receipt_type_id is invalid")
    if record.get("result") not in values["result_values"]:
        raise ValueError("AuditReceipt result is invalid")
    if record.get("due_stage") not in values["due_stages"]:
        raise ValueError("AuditReceipt due_stage is invalid")
    if record.get("evidence_role") not in values["roles"]:
        raise ValueError("AuditReceipt evidence_role must be emits")
    if record.get("evidence_kind") not in values["kinds"]:
        raise ValueError("AuditReceipt evidence_kind is invalid")
    if record.get("owner_kind") not in values["owner_kinds"]:
        raise ValueError("AuditReceipt owner_kind is invalid")
    if record.get("fingerprint_binding") not in \
            values["fingerprint_bindings"]:
        raise ValueError("AuditReceipt fingerprint_binding is invalid")
    capability = record.get("producer_capability")
    gate_id = record.get("producer_gate_id")
    if (capability is None) == (gate_id is None):
        raise ValueError(
            "AuditReceipt must bind exactly one producer capability or Gate")
    if record.get("owner_kind") == "kernel":
        if record.get("kernel_extension_point") is not None:
            raise ValueError(
                "Kernel AuditReceipt cannot claim an extension point")
    elif record.get("kernel_extension_point") is None:
        raise ValueError(
            "Profile AuditReceipt must bind its Kernel extension point")
    if dimensions is not None and record.get("dimension") not in set(
            dimensions):
        raise ValueError("AuditReceipt dimension is not registered")
    scope = record.get("scope")
    if scope != sorted(scope):
        raise ValueError("AuditReceipt scope must be sorted and unique")
    reused_id = record.get("reused_receipt_id")
    reason = record.get("reuse_reason")
    if (reused_id is None) != (reason is None):
        raise ValueError(
            "AuditReceipt reused_receipt_id and reuse_reason are paired")
    if reused_id is not None:
        if record.get("evidence_ref") != reused_id:
            raise ValueError(
                "AuditReceipt reused evidence_ref must equal reused_receipt_id")
        if record.get("result") != "passed":
            raise ValueError("a reused AuditReceipt must record passed")
        if record.get("fingerprint_binding") != "reused-receipt":
            raise ValueError(
                "a reused AuditReceipt must bind reused-receipt fingerprints")
    elif record.get("fingerprint_binding") != "evidence-time":
        raise ValueError(
            "a new AuditReceipt must bind evidence-time fingerprints")
    return record


def project_new_passing_audit_receipt(*, receipt_id, scope, plan,
                                      plan_sha256, obligation, evidence):
    """Project the shared mechanical shape for the registered finalizer.

    This is a stable contract projection, not a publication capability.
    Producer routes prove precursor admissibility and the unique record
    finalizer owns construction; atomic outer transactions delegate to that
    finalizer instead of becoming another producer.
    """
    binding = audit_lifecycle_contract.attempt_binding(
        plan, plan_sha256, obligation,
        present_fields=_SHIPPED_VALUES["field_order"])
    record = {
        "schema_version": _SHIPPED_CONTRACT["schema_version"],
        "record_kind": "audit-receipt",
        "receipt_type_id": RECEIPT_TYPE_ID,
        "receipt_id": receipt_id,
        **binding,
        "scope": sorted(set(scope)),
        "artifact_fingerprint": evidence["artifact_fingerprint"],
        "dependency_fingerprint": evidence["dependency_fingerprint"],
        "contract_fingerprint": evidence["contract_fingerprint"],
        "verifier": evidence["tool"],
        "method": "%s@%s/%s" % (
            evidence["tool"], evidence["tool_version"], evidence["check"]),
        "evidence_ref": evidence["receipt_id"],
        "checked_at": evidence["checked_at"],
        "result": "passed",
        "invalidated_by": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    }
    ordered = {field: record[field] for field in AUDIT_RECEIPT_FIELDS}
    validate_audit_receipt(ordered)
    return ordered


_SHIPPED_CONTRACT = load_contract()
_SHIPPED_VALUES = validate_contract(_SHIPPED_CONTRACT)
AUDIT_RECEIPT_FIELDS = _SHIPPED_VALUES["field_order"]
AUDIT_RECEIPT_RESULT_VALUES = _SHIPPED_VALUES["result_values"]


def current_receipt_errors(record, *, root=None):
    """Return current hard-cut AuditReceipt shape errors."""
    try:
        validate_audit_receipt(
            record, contract=load_contract(root) if root is not None else None)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return [str(exc)]
    return []


__all__ = [
    'RECEIPT_TYPE_ID',
    'current_receipt_errors',
    'load_contract',
    'page_artifact_fingerprint_contract',
    'project_new_passing_audit_receipt',
    'validate_audit_receipt',
]
