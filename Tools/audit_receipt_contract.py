"""Strict loader for the Kernel-owned K12/07 full AuditReceipt contract."""

import os

import audit_plan_contract as _support
import kblib


AUDIT_RECEIPT_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/audit-receipt-contract.yaml")
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
_PAGE_ARTIFACT_FRONTMATTER_FIELDS = (
    "type", "priority", "tier", "coverage_disposition", "lifecycle",
    "prerequisites",
)
_FIELD_TYPES = frozenset((
    "integer", "string", "sha256", "utc-timestamp", "string-list",
))


def validate_contract(document):
    """Validate one full AuditReceipt contract and return projections."""
    if not isinstance(document, dict) or set(document) != _CONTRACT_FIELDS:
        raise ValueError("AuditReceipt contract fields are not closed")
    if document.get("schema_version") != 1:
        raise ValueError("AuditReceipt contract schema_version must be 1")
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
    exact_page_artifact_values = {
        "protocol_id": "cambium-page-artifact-v1",
        "digest_serialization":
            "sha256-prefixed-canonical-json-utf8",
        "path_binding": "canonical-repository-relative-posix",
        "body_binding": "exact-bytes-after-frontmatter",
        "frontmatter_normalization": "restricted-yaml-semantic",
        "opening_frontmatter_marker": "---",
        "excluded_frontmatter_policy": "all-other-fields",
        "absent_included_field_policy": "omit",
        "page_set_protocol_id": "cambium-page-artifact-set-v1",
        "page_set_order": "canonical-path-ascending",
    }
    for field, expected in exact_page_artifact_values.items():
        if page_artifact.get(field) != expected:
            raise ValueError(
                "page artifact fingerprint %s must be %s" %
                (field, expected))
    included_fields = _support.closed_string_list(
        page_artifact.get("included_frontmatter_fields"),
        "page_artifact_fingerprint.included_frontmatter_fields")
    if included_fields != _PAGE_ARTIFACT_FRONTMATTER_FIELDS:
        raise ValueError(
            "page artifact fingerprint frontmatter fields must be exactly "
            "the K12/07 ordered closed set")
    page_material_fields = _support.closed_string_list(
        page_artifact.get("page_material_fields"),
        "page_artifact_fingerprint.page_material_fields")
    if page_material_fields != (
            "protocol_id", "path", "frontmatter", "body"):
        raise ValueError(
            "page artifact fingerprint material fields are not closed")
    closing_markers = _support.closed_string_list(
        page_artifact.get("closing_frontmatter_markers"),
        "page_artifact_fingerprint.closing_frontmatter_markers")
    if closing_markers != ("---", "..."):
        raise ValueError(
            "page artifact fingerprint closing markers must be --- and ...")
    page_set_material_fields = _support.closed_string_list(
        page_artifact.get("page_set_material_fields"),
        "page_artifact_fingerprint.page_set_material_fields")
    if page_set_material_fields != ("protocol_id", "members"):
        raise ValueError(
            "page-set artifact fingerprint material fields are not closed")
    page_set_member_fields = _support.closed_string_list(
        page_artifact.get("page_set_member_fields"),
        "page_artifact_fingerprint.page_set_member_fields")
    if page_set_member_fields != ("path", "artifact_fingerprint"):
        raise ValueError(
            "page-set artifact fingerprint member fields are not closed")
    field_order, fields = _support.field_specs(
        document.get("fields"), "fields", allowed_types=_FIELD_TYPES)
    required_fields = {
        "schema_version", "record_kind", "receipt_id", "plan_id",
        "audit_plan_sha256", "obligation_id", "owner_kind",
        "owner_rule_id", "kernel_extension_point", "task_id", "batch_id",
        "opening_transition_receipt", "standards_version",
        "active_standards_sha256", "selected_profile_manifest",
        "profile_snapshot_sha256", "profile_contract_fingerprint",
        "due_stage", "evidence_role", "evidence_kind", "dimension", "scope",
        "acceptance_predicate", "producer_check", "producer_capability",
        "producer_gate_id", "consumer_gate_id", "fingerprint_binding",
        "artifact_fingerprint", "dependency_fingerprint",
        "contract_fingerprint", "verifier", "method", "evidence_ref",
        "checked_at", "review_due", "result", "invalidated_by",
        "reused_receipt_id", "reuse_reason",
    }
    if set(fields) != required_fields:
        raise ValueError("AuditReceipt instance fields do not match K12/07")
    result_values = _support.closed_string_list(
        document.get("result_values"), "result_values")
    if set(result_values) != {"passed", "failed"}:
        raise ValueError("AuditReceipt result values must be passed/failed")
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
    if set(due_stages) != {"pre-merge", "post-delta-close"}:
        raise ValueError("AuditReceipt due-stage namespace is not closed")
    if set(roles) != {"emits"}:
        raise ValueError("AuditReceipt can only carry emitting evidence")
    if set(kinds) != {"audit-receipt"}:
        raise ValueError("AuditReceipt evidence kind must be audit-receipt")
    if set(owner_kinds) != {"kernel", "profile-extension"}:
        raise ValueError("AuditReceipt owner-kind namespace is not closed")
    if set(fingerprint_bindings) != {"evidence-time", "reused-receipt"}:
        raise ValueError("AuditReceipt fingerprint binding namespace is not closed")
    fingerprint_fields = _support.closed_string_list(
        document.get("fingerprint_fields"), "fingerprint_fields")
    if set(fingerprint_fields) != {
            "artifact_fingerprint", "dependency_fingerprint",
            "contract_fingerprint"}:
        raise ValueError("AuditReceipt fingerprint fields are incomplete")
    reuse_fields = _support.closed_string_list(
        document.get("reuse_fields"), "reuse_fields")
    if set(reuse_fields) != {"reused_receipt_id", "reuse_reason"}:
        raise ValueError("AuditReceipt reuse fields are incomplete")
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
        "page_artifact_fingerprint": {
            **page_artifact,
            "included_frontmatter_fields": included_fields,
            "closing_frontmatter_markers": closing_markers,
            "page_material_fields": page_material_fields,
            "page_set_material_fields": page_set_material_fields,
            "page_set_member_fields": page_set_member_fields,
        },
    }


def load_contract(root=None, snapshots=None):
    """Load the current Kernel-owned full AuditReceipt contract."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    if record.get("schema_version") != 1:
        raise ValueError("AuditReceipt schema_version must be 1")
    if record.get("record_kind") != contract["record_kind"]:
        raise ValueError("AuditReceipt record_kind is invalid")
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


def receipt_set_sha256(records, contract=None, dimensions=None):
    """Hash a unique receipt set in canonical receipt-id order."""
    if not isinstance(records, (list, tuple)):
        raise ValueError("AuditReceipt set must be a list or tuple")
    validated = [validate_audit_receipt(
        record, contract=contract, dimensions=dimensions) for record in records]
    receipt_ids = [record["receipt_id"] for record in validated]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise ValueError("AuditReceipt set repeats receipt_id")
    ordered = sorted(validated, key=lambda record: record["receipt_id"])
    return kblib.sha256_bytes(kblib.canonical_json_bytes(ordered))


_SHIPPED_CONTRACT = load_contract()
_SHIPPED_VALUES = validate_contract(_SHIPPED_CONTRACT)
AUDIT_RECEIPT_FIELDS = _SHIPPED_VALUES["field_order"]
AUDIT_RECEIPT_RESULT_VALUES = _SHIPPED_VALUES["result_values"]


__all__ = [
    "AUDIT_RECEIPT_CONTRACT_PATH", "AUDIT_RECEIPT_FIELDS",
    "AUDIT_RECEIPT_RESULT_VALUES", "load_contract",
    "page_artifact_fingerprint_contract", "receipt_set_sha256",
    "validate_audit_receipt", "validate_contract",
]
