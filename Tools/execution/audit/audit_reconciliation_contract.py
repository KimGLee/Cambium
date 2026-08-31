"""Closed transport field set for AuditPlan evidence reconciliation.

The reconciliation algorithm and row validation belong to
``audit_evidence_runtime``.  This lower-level contract owns only the immutable
three-field envelope shared by that runtime and its transport consumers, so
Queue validation never has to import the higher-level evidence application.
"""


_PROJECTION_FIELDS = (
    "audit_evidence_reconciliation",
    "audit_evidence_reconciliation_sha256",
    "audit_evidence_unresolved_count",
)


def projection_fields():
    """Return the immutable closed reconciliation projection fields."""
    return _PROJECTION_FIELDS


__all__ = ["projection_fields"]
