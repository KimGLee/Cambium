"""Load the Kernel-owned Batch-close Closed List registry.

``kernel/K12 Quality Assurance/batch-close-closed-list.yaml`` owns the
current member definitions and order. This module owns only strict loading,
mechanical validation, and the current evidence-field projection. It does not
add a check, decide what any check means, or interpret retired close formats.
"""
from Tools.platform.repository.repository import repository_source_root

import os
import re

import Tools.platform.common.kblib as kblib
import Tools.governance.profile.profile_contract as profile_contract


BATCH_CLOSE_CLOSED_LIST_PATH = (
    "kernel/K12 Quality Assurance/batch-close-closed-list.yaml")
GATE_ID = "batch-close"
GATE_CHECK = "batch_close_gate"
GATE_RECEIPT_TYPE_ID = "batch-close-gate-v1"
MEMBER_RECEIPT_TYPE_ID = "batch-close-member-evidence-v1"
REVIEW_ATTESTATION_RECEIPT_TYPE_ID = "batch-close-review-attestation-v1"
PAGE_REVIEW_RECEIPT_TYPE_ID = "batch-close-page-review-v1"
GLOBAL_REVIEW_RECEIPT_TYPE_ID = "batch-close-global-review-v1"
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
        root = repository_source_root(__file__)
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


_COMMON_RECEIPT_FIELDS = frozenset({
    "receipt_id", "receipt_type_id", "check", "target", "result",
    "details", "checked_at", "tool", "tool_version", "invalidated_by",
    "task_id", "upstream_revision_id", "selected_profile_manifest",
    "gate_id",
})
_PLAN_BINDING_FIELDS = frozenset({
    "audit_plan_id", "audit_plan_path", "audit_plan_sha256",
    "post_delta_evidence_bindings", "post_delta_evidence_count",
    "post_delta_evidence_set_sha256", "audit_evidence_reconciliation",
    "audit_evidence_reconciliation_sha256",
    "audit_evidence_unresolved_count",
})
_PROFILE_BINDING_FIELDS = frozenset(
    profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS)
_EVIDENCE_FILE_FIELDS = frozenset({
    "candidate_evidence_path", "candidate_evidence_sha256",
    "candidate_evidence_bytes", "candidate_evidence_records",
})

_MEMBER_FIELDS = _COMMON_RECEIPT_FIELDS | frozenset({
    "batch_id", "integrator_id", "reviewer_id", "merged_snapshot_sha256",
    "candidate_count", "candidate_type_counts", "candidate_set_sha256",
    "plan_id", "audit_plan_path", "audit_plan_sha256", "obligation_id",
    "opening_transition_receipt", "active_standards_sha256",
    "profile_snapshot_sha256", "profile_contract_fingerprint",
    "fingerprint_binding", "artifact_fingerprint",
    "dependency_fingerprint", "contract_fingerprint",
})
_ATTESTATION_FIELDS = (
    _COMMON_RECEIPT_FIELDS | _PLAN_BINDING_FIELDS | _EVIDENCE_FILE_FIELDS |
    frozenset({
        "batch_id", "integrator_id", "reviewer_id",
        "merged_snapshot_sha256", "accepted_candidate_count",
        "accepted_candidate_types", "accepted_by_type_counts",
        "candidate_set_sha256", "candidate_protocol",
        "candidate_baseline_protocol", "candidate_baseline_receipt",
        "carried_candidate_count", "carried_candidate_set_sha256",
        "fresh_candidate_count", "fresh_candidate_set_sha256",
        "candidate_dispositions",
    }))
_PAGE_REVIEW_FIELDS = (
    _COMMON_RECEIPT_FIELDS | _PROFILE_BINDING_FIELDS | frozenset({
        "batch_id", "integrator_id", "reviewer_id",
        "reviewer_attestation_receipt", "reviewed_on",
        "semantic_content_sha256",
        "metadata_execution_contract_fingerprint",
        "merged_snapshot_sha256",
    }))
_GLOBAL_REVIEW_FIELDS = (
    _COMMON_RECEIPT_FIELDS | _PLAN_BINDING_FIELDS | frozenset({
        "batch_id", "integrator_id", "reviewer_id",
        "merged_snapshot_sha256", "reviewer_attestation_receipt",
        "closed_list_evidence", "closed_list_producer_evidence",
    }))
_GATE_PASS_FIELDS = (
    _COMMON_RECEIPT_FIELDS | _PLAN_BINDING_FIELDS | _PROFILE_BINDING_FIELDS |
    frozenset({
        "batch_id", "integrator_id", "reviewer_id", "queue_revision",
        "queue_state_revision", "required_queue_sha256",
        "coverage_ledger_sha256", "progress_ledger_sha256",
        "before_required_queue_sha256", "after_required_queue_sha256",
        "before_coverage_sha256", "after_coverage_sha256",
        "before_progress_sha256", "after_progress_sha256", "delta_sha256",
        "work_spec_path", "work_spec_sha256", "corpus_plan_required",
        "corpus_plan_triggers", "corpus_plan_receipt",
        "delta_apply_receipt", "queue_consistency_receipt",
        "merged_snapshot_sha256", "reviewer_attestation_receipt",
        "global_review_receipt", "closed_list_evidence",
        "closed_list_producer_evidence", "page_review_receipts",
        "page_review_receipt_count", "page_review_receipt_set_sha256",
        "metadata_execution_contract_fingerprint", "settlement_protocol",
        "current_unsettled_count", "current_unsettled_set_sha256",
    }))
_GATE_FAIL_ALLOWED_FIELDS = (
    _COMMON_RECEIPT_FIELDS | _EVIDENCE_FILE_FIELDS | frozenset({
        "batch_id", "merged_snapshot_sha256", "before_required_queue_sha256",
        "after_required_queue_sha256", "before_coverage_sha256",
        "after_coverage_sha256", "before_progress_sha256",
        "after_progress_sha256", "integrator_id", "reviewer_id",
        "candidate_count", "candidate_evidence_error",
        "manifest_page_count", "metadata_execution_contract_fingerprint",
    }))


def _base_errors(record, receipt_type_id, check):
    from Tools.execution.task_runtime.queue_runtime import canon

    expected = {
        "receipt_type_id": receipt_type_id,
        "tool": canon.BATCH_CLOSE_TOOL,
        "tool_version": canon.BATCH_CLOSE_TOOL_VERSION,
        "check": check,
        "gate_id": GATE_ID,
        "invalidated_by": None,
    }
    errors = [field for field, value in expected.items()
              if record.get(field) != value]
    for field in ("receipt_id", "target", "details", "checked_at"):
        value = record.get(field)
        if not isinstance(value, str) or not value or value.strip() != value:
            errors.append(field)
    return errors


def current_receipt_errors(record, *, root=None):
    """Validate one current check_batch_close-owned typed record."""
    del root
    if not isinstance(record, dict):
        return ["batch-close receipt must be an object"]
    type_id = record.get("receipt_type_id")
    if type_id == GATE_RECEIPT_TYPE_ID:
        errors = _base_errors(record, type_id, GATE_CHECK)
        if record.get("result") == "pass":
            if set(record) != _GATE_PASS_FIELDS:
                errors.append("batch-close pass Gate fields are not closed")
        elif record.get("result") == "fail":
            if (not _COMMON_RECEIPT_FIELDS.issubset(record) or
                    not set(record).issubset(_GATE_FAIL_ALLOWED_FIELDS)):
                errors.append("batch-close fail Gate fields are not closed")
        else:
            errors.append("result")
    elif type_id == MEMBER_RECEIPT_TYPE_ID:
        allowed = _MEMBER_FIELDS | {"source_command"}
        errors = _base_errors(record, type_id, record.get("check"))
        member_checks = {
            "closed_list_%s" % row["member_id"]
            for row in CLOSED_LIST_MEMBER_ROWS
        }
        if record.get("check") not in member_checks:
            errors.append("check")
        if (not _MEMBER_FIELDS.issubset(record) or
                not set(record).issubset(allowed)):
            errors.append("batch-close member fields are not closed")
        if record.get("result") != "pass":
            errors.append("result")
    elif type_id == REVIEW_ATTESTATION_RECEIPT_TYPE_ID:
        errors = _base_errors(
            record, type_id, "batch_global_review_attestation")
        if set(record) != _ATTESTATION_FIELDS:
            errors.append("batch-close attestation fields are not closed")
        if record.get("result") != "pass":
            errors.append("result")
    elif type_id == PAGE_REVIEW_RECEIPT_TYPE_ID:
        errors = _base_errors(record, type_id, "page_review_acceptance")
        if set(record) != _PAGE_REVIEW_FIELDS:
            errors.append("batch-close page-review fields are not closed")
        if record.get("result") != "pass":
            errors.append("result")
    elif type_id == GLOBAL_REVIEW_RECEIPT_TYPE_ID:
        errors = _base_errors(record, type_id, "batch_global_review")
        if set(record) != _GLOBAL_REVIEW_FIELDS:
            errors.append("batch-close global-review fields are not closed")
        if record.get("result") != "pass":
            errors.append("result")
    else:
        return ["batch-close receipt_type_id is invalid"]
    return sorted(set(errors))


__all__ = [
    'BATCH_CLOSE_CLOSED_LIST_PATH',
    'CLOSED_LIST_EVIDENCE_FIELDS',
    'GATE_CHECK',
    'GATE_ID',
    'GATE_RECEIPT_TYPE_ID',
    'GLOBAL_REVIEW_RECEIPT_TYPE_ID',
    'MEMBER_RECEIPT_TYPE_ID',
    'PAGE_REVIEW_RECEIPT_TYPE_ID',
    'REVIEW_ATTESTATION_RECEIPT_TYPE_ID',
    'closed_list_member_rows',
    'current_receipt_errors',
    'load_batch_close_closed_list',
    'validate_batch_close_closed_list',
]
