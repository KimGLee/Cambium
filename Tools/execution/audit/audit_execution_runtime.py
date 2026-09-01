"""Derive the next legal AuditPlan production step without owning a rule.

The immutable AuditPlan owns the obligation, producer identity, evidence kind,
and due stage.  :mod:`audit_evidence_runtime` owns final evidence acceptance.
This application module only connects those two existing contracts to the
registered producer entry point.  It never creates an obligation or accepts a
weaker record than the final closure consumer.
"""

from Tools.platform.common.primitives import catalog_record

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.batch_review_obligation_contract as batch_review_obligation_contract
import Tools.execution.audit.audit_producer_chain as audit_producer_chain
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.profile_batch_judgment_contract as profile_batch_judgment_contract
from Tools.platform.agent_interface.entrypoint_loader import (
    EntrypointResolutionError,
    describe_entrypoint,
)
from Tools.execution.task_runtime.queue_runtime.receipts import current_receipt_catalog


AUDIT_RECEIPT_COMPLETION_CAPABILITY = \
    audit_producer_chain.FINAL_AUDIT_RECEIPT_CAPABILITY
MANUAL_ATTESTATION_CAPABILITY = "manual-attestation-v1"


def resolution_route(status):
    """Return the sole next-action interpretation of a consumer status."""
    return audit_lifecycle_contract.resolution_route(status)


def producer_route(obligation, *, root=None):
    """Return the sole execution route for one frozen obligation.

    This is an implementation projection, not an obligation registry.  The
    AuditPlan already owns kind, stage, check, and producer identity; this
    function makes the Tool-side dispatch exhaustive and independently
    testable.  Post-Delta obligations belong to the batch-close producer as a
    single after-image closure and must never be dispatched one by one here.
    """
    if not isinstance(obligation, dict):
        return None
    if obligation.get("due_stage") == "post-delta-close":
        return "batch-close-stage"
    kind = obligation.get("evidence_kind")
    if kind == "audit-receipt":
        try:
            chain = (audit_producer_chain.precursor_chain_for_spec(
                         obligation, root=root)
                     if "spec_id" in obligation else
                     audit_producer_chain.precursor_chain_for_obligation(
                         obligation, root=root))
            return chain["execution_route"]
        except audit_producer_chain.AuditProducerChainError:
            return None
    if kind in {"gate-receipt", "candidate-set-receipt"}:
        return "deterministic-direct-evidence"
    if kind == "batch-page-review-record":
        return "batch-page-review"
    if kind == profile_batch_judgment_contract.RECORD_KIND:
        return "profile-batch-judgment"
    return None


def _tool(root, capability_id):
    return metadata_execution_contract.capability_invocation_tool(
        capability_id, root=root)


def _registered_consumer(root, capability_id, consumer_path):
    entry = metadata_execution_contract.capability_entry_by_id(
        capability_id, root=root)
    return (isinstance(entry, dict) and
            consumer_path in (entry.get("consumers") or []))


def _target(item, obligation=None, plan=None):
    value = {"batch_id": item.get("id")}
    if isinstance(plan, dict):
        value["plan_id"] = plan.get("audit_plan_id")
        value["audit_plan_sha256"] = plan.get("audit_plan_sha256")
    if isinstance(obligation, dict):
        value.update({
            "obligation_id": obligation.get("obligation_id"),
            "page": obligation.get("target"),
        })
    return value


def _base_arguments(item, status, obligation):
    return {
        "batch": item["id"],
        "plan": status["audit_plan_path"],
        "obligation_id": obligation["obligation_id"],
    }


def _repair(item, status, obligation, reason_code, reason):
    return {
        "status": "repair",
        "token": "repair-audit-evidence",
        "capability_id": None,
        "tool": None,
        "target": _target(item, obligation, status),
        "arguments": {},
        "required_input": None,
        "reason_code": reason_code,
        "reason": reason,
    }


def _external_reparse(item, status, obligation, *, disposition, token,
                      required_input, reason_code, reason):
    """Expose work that must change an authoritative object outside Runner.

    A prior evidence attempt can require content correction or user escalation,
    but neither outcome authorizes this projection to invent another producer
    attempt or mutate the governed page.  The external actor completes that
    owned work and then asks the runtime to derive a fresh step.
    """
    return {
        "status": disposition,
        "token": token,
        "capability_id": None,
        "tool": None,
        "target": _target(item, obligation, status),
        "arguments": {},
        "required_input": required_input,
        "reason_code": reason_code,
        "reason": reason,
    }


def _complete_precursor(root, item, status, obligation, precursor):
    arguments = _base_arguments(item, status, obligation)
    arguments["evidence_receipt"] = precursor["receipt_id"]
    return {
        "status": "invoke",
        "token": "complete-audit-receipt",
        "capability_id": AUDIT_RECEIPT_COMPLETION_CAPABILITY,
        "tool": _tool(root, AUDIT_RECEIPT_COMPLETION_CAPABILITY),
        "target": _target(item, obligation, status),
        "arguments": arguments,
        "required_input": None,
        "reason_code": "valid-precursor-needs-full-audit-receipt",
        "reason": None,
    }


def _catalog_record(result, receipt_id):
    return catalog_record(current_receipt_catalog(result).get(receipt_id))


def _substantive_review_step(result, item, status, obligation, *, prior=None,
                             chain=None):
    chain = chain or audit_producer_chain.precursor_chain_for_obligation(
        obligation, root=result["root"])
    if chain["execution_route"] != "substantive-review":
        raise audit_producer_chain.AuditProducerChainError(
            "obligation is not a substantive-review producer chain")
    arguments = _base_arguments(item, status, obligation)
    arguments["page"] = obligation["target"]
    if prior is None:
        arguments.update({"round": 1, "round_1_receipt_id": None})
        required_input = {
            "authoring_context_id": "string",
            "reviewer_context_id": "string",
            "reviewer_role": "string",
            "verdict": "passed|changes-required",
            "statement": "string",
            "findings": "list",
        }
        reason_code = "substantive-review-round-one-requires-judgment"
    else:
        arguments.update({
            "round": 2,
            "round_1_receipt_id": prior["receipt_id"],
            "authoring_context_id": prior["authoring_context_id"],
        })
        required_input = {
            "reviewer_context_id": "string",
            "reviewer_role": "string",
            "verdict": "passed|escalated",
            "statement": "string",
            "findings": "exact round-1 finding reconciliation list",
        }
        reason_code = "substantive-review-round-two-confirms-corrections"
    return {
        "status": "await-agent",
        "token": "record-substantive-review",
        "capability_id": None,
        "tool": None,
        "target": _target(item, obligation, status),
        "arguments": {},
        "required_input": required_input,
        "reason_code": reason_code,
        "reason": None,
        "resume_tool": _tool(result["root"],
                             chain["precursor_capability"]),
        "resume_capability_id": chain["precursor_capability"],
        "resume_arguments": arguments,
    }


def _missing_step(result, item, status, obligation):
    arguments = _base_arguments(item, status, obligation)
    route = producer_route(obligation, root=result["root"])
    capability = obligation.get("producer_capability")
    evidence_kind = obligation.get("evidence_kind")

    if route == "batch-close-stage":
        return _repair(
            item, status, obligation, "post-delta-obligation-misrouted",
            "post-Delta obligations must be produced and consumed as the "
            "single batch-close after-image closure")

    if route in {
            "substantive-review", "rendering-verification",
            "deterministic-audit-precursor"}:
        try:
            chain = audit_producer_chain.precursor_chain_for_obligation(
                obligation, root=result["root"])
        except audit_producer_chain.AuditProducerChainError as exc:
            return _repair(
                item, status, obligation, "unmapped-audit-producer",
                str(exc))
        if route == "substantive-review":
            return _substantive_review_step(
                result, item, status, obligation, chain=chain)
        if route == "rendering-verification":
            producer_capability = chain["precursor_capability"]
            return {
                "status": "await-host",
                "token": "record-rendering-verification",
                "capability_id": None,
                "tool": None,
                "target": _target(item, obligation, status),
                "arguments": {},
                "required_input": {
                    "rendering_mode": "registered rendering mode",
                    "visual_trigger": "string|null",
                    "unresolved_question": "string|null",
                    "verification_target": "string|null",
                    "verification_result": "string|null",
                },
                "reason_code": "rendering-verification-requires-host-result",
                "reason": None,
                "resume_tool": _tool(result["root"], producer_capability),
                "resume_capability_id": producer_capability,
                "resume_arguments": arguments,
            }
        adapter_capability = chain["precursor_capability"]
        return {
            "status": "invoke",
            "token": "record-changed-scope-evidence",
            "capability_id": adapter_capability,
            "tool": _tool(result["root"], adapter_capability),
            "target": _target(item, obligation, status),
            "arguments": arguments,
            "required_input": None,
            "reason_code": "deterministic-audit-precursor-missing",
            "reason": None,
        }

    if route == "deterministic-direct-evidence":
        adapter_capability = \
            changed_scope_evidence_contract.ADAPTER_CAPABILITY_ID
        return {
            "status": "invoke",
            "token": "record-changed-scope-evidence",
            "capability_id": adapter_capability,
            "tool": _tool(result["root"], adapter_capability),
            "target": _target(item, obligation, status),
            "arguments": arguments,
            "required_input": None,
            "reason_code": "deterministic-direct-evidence-missing",
            "reason": None,
        }

    if route == "batch-page-review":
        variant = ("s-sampled-page" if obligation.get("producer_check") ==
                   "batch_page_review:s-tier-sampled-review"
                   else "m-atomic-item")
        return {
            "status": "await-agent",
            "token": "record-batch-page-review",
            "capability_id": None,
            "tool": None,
            "target": _target(item, obligation, status),
            "arguments": {},
            "required_input": {
                "reviewer_context_id": "string",
                "reviewer_role": "string",
                "verdict": "passed|changes-required",
                "statement": "string",
                "applicability_disposition": "applicable|not-applicable|null",
                "applicability_reason": "string|null",
                "consumed_evidence_refs": "list",
            },
            "reason_code": "batch-page-review-requires-judgment",
            "reason": None,
            "resume_tool": _tool(result["root"], capability),
            "resume_capability_id": capability,
            "resume_arguments": dict(
                arguments, page=obligation["target"], variant=variant),
        }

    if route == "profile-batch-judgment":
        try:
            producer_path = describe_entrypoint(
                profile_batch_judgment_contract.PRODUCER_TOOL).\
                implementation_path
        except EntrypointResolutionError:
            return _repair(
                item, status, obligation,
                "profile-judgment-producer-entrypoint-invalid",
                "Profile batch judgment producer has no unique public-to-"
                "implementation edge")
        if (capability != MANUAL_ATTESTATION_CAPABILITY or
                not _registered_consumer(
                    result["root"], capability, producer_path)):
            return _repair(
                item, status, obligation,
                "profile-judgment-producer-not-registered",
                "Profile batch judgment producer is not a registered "
                "manual-attestation consumer")
        return {
            "status": "await-agent",
            "token": "record-profile-batch-judgment",
            "capability_id": None,
            "tool": None,
            "target": _target(item, obligation, status),
            "arguments": {},
            "required_input": {
                "reviewer_role": "string",
                "statement": "string",
            },
            "reason_code": "profile-batch-judgment-requires-authority",
            "reason": None,
            "resume_tool": profile_batch_judgment_contract.PRODUCER_TOOL,
            "resume_capability_id": capability,
            "resume_arguments": {
                "batch": item["id"],
                "judgment_item": obligation["owner_rule_id"],
                "target": obligation["target"],
            },
        }

    return _repair(
        item, status, obligation, "unmapped-audit-producer",
        "no Tool producer dispatch is registered for evidence kind %s" %
        evidence_kind)


def _next_executable_row(status):
    """Select one unresolved obligation whose frozen dependencies are done.

    AuditPlan obligation IDs are content identities, not an execution order.
    M ``consumes`` atoms obtain their dependencies from the Kernel-owned
    Batch Review registry; all other rows remain dependency-free here.  The
    original AuditPlan order is retained only as a deterministic tie-break
    among rows that are actually executable.
    """
    rows = status.get("obligations")
    if not isinstance(rows, list):
        raise ValueError("audit evidence status has no obligation list")
    obligations = []
    by_id = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(
                row.get("obligation"), dict):
            raise ValueError(
                "audit evidence status obligation %d is invalid" % index)
        obligation = row["obligation"]
        obligation_id = obligation.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id:
            raise ValueError(
                "audit evidence status obligation %d has no identity" %
                index)
        if obligation_id in by_id:
            raise ValueError(
                "audit evidence status repeats obligation %s" %
                obligation_id)
        obligations.append(obligation)
        by_id[obligation_id] = row

    unresolved = [row for row in rows if row.get("status") != "satisfied"]
    for row in unresolved:
        obligation = row["obligation"]
        dependency_ids = \
            batch_review_obligation_contract.\
                consumption_dependency_obligation_ids(
                    obligations, obligation)
        missing = [value for value in dependency_ids if value not in by_id]
        if missing:
            raise ValueError(
                "AuditPlan consumption dependency is outside the due-stage "
                "closure: %s" % ", ".join(missing))
        if all(by_id[value].get("status") == "satisfied"
               for value in dependency_ids):
            return row
    if unresolved:
        blocked = sorted(
            row["obligation"]["obligation_id"] for row in unresolved)
        raise ValueError(
            "AuditPlan unresolved obligations form a dependency cycle or "
            "have no executable producer: %s" % ", ".join(blocked))
    return None


def next_stage_step(result, item, due_stage, required_state=None):
    """Return the next missing obligation step, or a complete projection."""
    status = audit_evidence_runtime.stage_evidence_status(
        result, item, due_stage, required_state=required_state)
    row = _next_executable_row(status)
    if row is not None:
        obligation = row["obligation"]
        route = resolution_route(row.get("status"))
        if route == "complete-precursor":
            precursor = _catalog_record(result, row.get("evidence_ref"))
            if not isinstance(precursor, dict):
                return _repair(
                    item, status, obligation,
                    "audit-precursor-not-current",
                    "selected producer attempt is not current")
            return _complete_precursor(
                result["root"], item, status, obligation, precursor)
        if route == "confirm-substantive-review":
            prior = _catalog_record(result, row.get("evidence_ref"))
            try:
                chain = audit_producer_chain.precursor_chain_for_obligation(
                    obligation, root=result["root"])
            except audit_producer_chain.AuditProducerChainError:
                chain = None
            if (not isinstance(prior, dict) or not isinstance(chain, dict) or
                    chain.get("execution_route") != "substantive-review"):
                return _repair(
                    item, status, obligation,
                    "audit-confirmation-precursor-invalid", row["reason"])
            return _substantive_review_step(
                result, item, status, obligation, prior=prior, chain=chain)
        if route == "external-correction":
            return _external_reparse(
                item, status, obligation,
                disposition="await-agent", token="correct-audit-target",
                required_input={
                    "external_resolution": (
                        "correct the governed target through its canonical "
                        "authoring path, then derive the next action again"),
                },
                reason_code="audit-evidence-needs-correction",
                reason=row["reason"])
        if route == "external-escalation":
            return _external_reparse(
                item, status, obligation,
                disposition="await-user",
                token="resolve-substantive-review-escalation",
                required_input={
                    "external_resolution": (
                        "resolve the escalated judgment through the existing "
                        "authority path, then derive the next action again"),
                },
                reason_code="audit-evidence-escalated-to-user",
                reason=row["reason"])
        if route == "repair":
            return _repair(
                item, status, obligation,
                "audit-evidence-%s" % row["status"], row["reason"])
        if route == "produce":
            return _missing_step(result, item, status, obligation)
        return _repair(
            item, status, obligation,
            "unknown-audit-evidence-status",
            "Audit evidence consumer returned an unsupported status %r" %
            row["status"])
    return {
        "status": "complete",
        "token": "audit-stage-complete",
        "capability_id": None,
        "tool": None,
        "target": _target(item, plan=status),
        "arguments": {},
        "required_input": None,
        "reason_code": "all-due-obligations-satisfied",
        "reason": None,
        "closure": audit_evidence_runtime.stage_evidence_closure(
            result, item, due_stage, required_state=required_state),
    }
