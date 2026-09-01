"""Closed current contract for the Batch Review wrapper Receipt.

The wrapper is the one batch-level authorization object consumed by the
``batch-review`` Gate.  Detailed Profile judgments and Audit evidence keep
their own types; this contract binds their exact identifiers without turning
the wrapper into a second owner of those records.
"""

import Tools.execution.task_runtime.queue_runtime.canon as queue_canon

RECEIPT_TYPE_ID = "batch-review-wrapper-v1"
PRODUCER_TOOL = queue_canon.MANUAL_ATTESTATION_TOOL
PRODUCER_TOOL_VERSION = queue_canon.MANUAL_ATTESTATION_TOOL_VERSION
PRODUCER_CHECK = "batch_gate"
GATE_ID = queue_canon.BATCH_REVIEW_GATE_ID

RECEIPT_FIELDS = frozenset({
    "receipt_id", "receipt_type_id", "check", "target", "result",
    "details", "checked_at", "tool", "tool_version", "invalidated_by",
    "task_id", "upstream_revision_id", "selected_profile_manifest",
    "gate_id", "batch_id", "actor_role", "attestation_statement",
    "opening_transition_receipt", "delta_path", "delta_sha256",
    "delta_page_receipt_ids", "audit_plan_id", "audit_plan_path",
    "audit_plan_sha256", "audit_evidence_bindings",
    "audit_evidence_set_sha256", "audit_evidence_reconciliation",
    "audit_evidence_reconciliation_sha256",
    "audit_evidence_unresolved_count", "review_requirement_set_sha256",
    "judgment_receipt_ids", "judgment_record_set_sha256",
})


def current_receipt_errors(record, *, root=None):
    """Return errors in one hard-cut current Batch Review wrapper."""
    del root
    if not isinstance(record, dict):
        return ["Batch Review wrapper must be an object"]
    errors = []
    if set(record) != RECEIPT_FIELDS:
        errors.append("Batch Review wrapper fields are not closed")
    expected = {
        "receipt_type_id": RECEIPT_TYPE_ID,
        "tool": PRODUCER_TOOL,
        "tool_version": PRODUCER_TOOL_VERSION,
        "check": PRODUCER_CHECK,
        "gate_id": GATE_ID,
        "result": "pass",
        "invalidated_by": None,
        "actor_role": "integrator",
    }
    errors.extend(field for field, value in expected.items()
                  if record.get(field) != value)
    if record.get("target") != record.get("batch_id"):
        errors.append("target")
    for field in (
            "receipt_id", "target", "batch_id", "details", "checked_at",
            "attestation_statement", "opening_transition_receipt",
            "delta_path", "delta_sha256", "audit_plan_id",
            "audit_plan_path", "audit_plan_sha256",
            "audit_evidence_set_sha256",
            "audit_evidence_reconciliation_sha256",
            "review_requirement_set_sha256", "judgment_record_set_sha256"):
        value = record.get(field)
        if not isinstance(value, str) or not value or value.strip() != value:
            errors.append(field)
    for field in (
            "delta_page_receipt_ids", "audit_evidence_bindings",
            "judgment_receipt_ids"):
        value = record.get(field)
        if not isinstance(value, list):
            errors.append(field)
        elif field != "audit_evidence_bindings" and (
                value != sorted(set(value)) or
                any(not isinstance(item, str) or not item for item in value)):
            errors.append(field)
    if (not isinstance(record.get("audit_evidence_unresolved_count"), int) or
            isinstance(record.get("audit_evidence_unresolved_count"), bool) or
            record.get("audit_evidence_unresolved_count") < 0):
        errors.append("audit_evidence_unresolved_count")
    return sorted(set(errors))


__all__ = [
    'GATE_ID',
    'PRODUCER_CHECK',
    'PRODUCER_TOOL',
    'PRODUCER_TOOL_VERSION',
    'RECEIPT_TYPE_ID',
    'current_receipt_errors',
]
