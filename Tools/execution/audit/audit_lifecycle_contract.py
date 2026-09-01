"""Tool-side machine contract for AuditPlan evidence lifecycle plumbing.

Kernel registries own obligation meaning and record contracts own their closed
shapes.  This module owns only the mechanical vocabulary shared between those
layers: immutable plan/obligation binding fields, the final closure binding
shape, and the exhaustive resolution-status to next-action routing table.

Keeping these projections here prevents producers, the evidence resolver, and
the execution adapter from independently deciding what the same binding or
status means.  It deliberately imports no producer, registry, or runtime.
"""

from types import MappingProxyType


class AuditLifecycleContractError(ValueError):
    """A Tool-side audit lifecycle value is outside the closed contract."""


# Record identities shared by the producer-chain resolver and the concrete
# changed-scope record validator.  Keeping this mechanical vocabulary here
# prevents the resolver and the record-shape contract from maintaining two
# spellings for the same intermediate evidence kind.
AUDIT_RECEIPT_RECORD_KIND = "audit-receipt"
CHANGED_SCOPE_PRECURSOR_RECORD_KIND = "audit-producer-evidence"


# Authority fields copied from the immutable plan into every plan-bound
# evidence attempt.  Ordering is part of the serialization-facing projection.
PLAN_BINDING_FIELDS = (
    "task_id", "batch_id", "opening_transition_receipt",
    "upstream_revision_id", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint",
)

ATTEMPT_IDENTITY_FIELDS = (
    "plan_id", "audit_plan_sha256", "obligation_id",
) + PLAN_BINDING_FIELDS

# Fields whose values are frozen by one AuditPlan obligation and may be copied
# into a producer attempt.  Record-shape contracts decide which are present;
# lifecycle comparison never invents a missing field for a narrower record.
OBLIGATION_BINDING_FIELDS = (
    "owner_kind", "owner_rule_id", "kernel_extension_point", "partition",
    "target", "due_stage", "applicability", "evidence_role",
    "evidence_kind", "dimension", "acceptance_predicate",
    "producer_check", "producer_capability", "producer_gate_id",
    "consumer_gate_id", "fingerprint_binding", "review_due",
)

EVIDENCE_BINDING_FIELDS = (
    "obligation_id", "owner_kind", "owner_rule_id", "due_stage", "target",
    "evidence_role", "evidence_kind", "dimension", "evidence_ref",
    "evidence_sha256", "artifact_fingerprint", "dependency_fingerprint",
    "contract_fingerprint", "result", "reused", "reuse_reason",
)


_RESOLUTION_ROUTES = {
    "satisfied": "terminal-evidence-complete",
    "ready-for-completion": "complete-precursor",
    "needs-confirmation": "confirm-substantive-review",
    "needs-correction": "external-correction",
    "escalated": "external-escalation",
    "ambiguous": "repair",
    "invalid": "repair",
    "missing": "produce",
}
RESOLUTION_ROUTES = MappingProxyType(_RESOLUTION_ROUTES)
RESOLUTION_STATUSES = frozenset(RESOLUTION_ROUTES)


def resolution_route(status):
    """Return the sole route for a registered status, else ``None``."""
    return RESOLUTION_ROUTES.get(status)


def validate_resolution_status(status):
    """Return a registered status or fail closed on an unknown value."""
    if status not in RESOLUTION_STATUSES:
        raise AuditLifecycleContractError(
            "unregistered resolution status %r" % status)
    if resolution_route(status) is None:
        raise AuditLifecycleContractError(
            "resolution status %r has no next-action route" % status)
    return status


def validate_resolution(resolution):
    """Validate the status-bearing portion of one resolver projection."""
    if not isinstance(resolution, dict):
        raise AuditLifecycleContractError(
            "audit evidence resolution must be a mapping")
    validate_resolution_status(resolution.get("status"))
    return resolution


def attempt_binding(plan, plan_sha256, obligation, *, present_fields=None):
    """Project immutable values copied into one producer/final attempt.

    ``present_fields`` lets a narrower record-shape contract opt into only the
    obligation fields it actually carries.  Identity and authority fields are
    never optional at this layer.
    """
    if not isinstance(plan, dict) or not isinstance(obligation, dict):
        raise AuditLifecycleContractError(
            "plan and obligation bindings must be mappings")
    values = {
        "plan_id": plan.get("plan_id"),
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation.get("obligation_id"),
    }
    values.update({field: plan.get(field) for field in PLAN_BINDING_FIELDS})
    admitted = (set(OBLIGATION_BINDING_FIELDS) if present_fields is None
                else set(present_fields) & set(OBLIGATION_BINDING_FIELDS))
    values.update({field: obligation.get(field)
                   for field in OBLIGATION_BINDING_FIELDS
                   if field in admitted})
    return values


def attempt_binding_mismatches(record, plan, plan_sha256, obligation, *,
                               present_only=True):
    """Return binding fields whose record values drift from the plan.

    Closed record contracts separately prove required fields.  ``present_only``
    therefore defaults to comparing each obligation field only when that
    record shape contains it, matching the shared lifecycle boundary without
    broadening any record schema.
    """
    if not isinstance(record, dict):
        return ["record"]
    present = set(record) if present_only else None
    expected = attempt_binding(
        plan, plan_sha256, obligation, present_fields=present)
    return sorted(field for field, value in expected.items()
                  if record.get(field) != value)


__all__ = [
    'ATTEMPT_IDENTITY_FIELDS',
    'AUDIT_RECEIPT_RECORD_KIND',
    'AuditLifecycleContractError',
    'CHANGED_SCOPE_PRECURSOR_RECORD_KIND',
    'EVIDENCE_BINDING_FIELDS',
    'PLAN_BINDING_FIELDS',
    'attempt_binding',
    'attempt_binding_mismatches',
    'resolution_route',
    'validate_resolution',
]
