"""Unique pure finalizer for one current K12/07 AuditReceipt record.

The Kernel-owned contract owns the closed record projection. Evidence
producers and outer transactions call this one boundary after proving their
own precursor and currentness conditions; none of them restates the record
shape or becomes a second finalizer.
"""

import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract


def finalize_audit_receipt_record(*, receipt_id, scope, plan,
                                  plan_sha256, obligation, evidence):
    """Return the one contract-valid current AuditReceipt projection."""
    return audit_receipt_contract.project_new_passing_audit_receipt(
        receipt_id=receipt_id,
        scope=scope,
        plan=plan,
        plan_sha256=plan_sha256,
        obligation=obligation,
        evidence=evidence,
    )


__all__ = ["finalize_audit_receipt_record"]
