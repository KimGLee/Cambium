#!/usr/bin/env python3
"""Record the plan-bound K12/02 rendering escalation record shape.

This Tool records the highest rendering level and validates the escalation
record fields.  Its ``pass`` means only ``record-shape-only``.  It neither
runs nor attests the separate Level 0 / Level 1 checks and it does not judge
whether a visual observation is accurate.
"""

import os
import sys

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.execution.audit.audit_producer_chain as audit_producer_chain
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.platform.common.kblib as kblib
import Tools.knowledge.rendering.rendering_verification_contract as rendering_verification_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting
from Tools.platform.common.primitives import catalog_record


_SHIPPED_PRODUCER_CHAIN = audit_producer_chain.precursor_chain_for_spec(
    audit_obligation_projection.obligation_spec_for_rule(
        "k12-02-rendering-verification-record"))
TOOL = rendering_verification_contract.CURRENT_PRODUCER_TOOL
TOOL_VERSION = rendering_verification_contract.CURRENT_PRODUCER_VERSION
CHECK = rendering_verification_contract.CURRENT_PRODUCER_CHECK
if (TOOL != _SHIPPED_PRODUCER_CHAIN["precursor_tool"] or
        CHECK != _SHIPPED_PRODUCER_CHAIN["precursor_check"]):
    raise ValueError("rendering receipt owner differs from producer chain")
DEFAULT_RECEIPTS = runtime_paths.RENDERING_VERIFICATION_RECEIPT_PATH


class RenderingVerificationError(audit_producer_runtime.AuditProducerError):
    """A rendering record cannot be safely produced or published."""


def _optional_text(value, label):
    if value is None:
        return None
    if (not isinstance(value, str) or not value or
            value.strip() != value):
        raise RenderingVerificationError(
            "%s must be null or a non-empty trimmed string" % label)
    return value


def resolve_obligation(plan, obligation_id, contract=None, root=None):
    """Resolve the unique every-batch rendering record-shape obligation."""
    contract = contract or rendering_verification_contract.load_contract()
    rendering_verification_contract.validate_contract(contract)
    matches = [row for row in plan.get("obligations") or []
               if isinstance(row, dict) and
               row.get("obligation_id") == obligation_id]
    if len(matches) != 1:
        raise RenderingVerificationError(
            "AuditPlan must contain exactly one obligation %s" %
            obligation_id)
    obligation = matches[0]
    try:
        chain = audit_producer_chain.precursor_chain_for_obligation(
            obligation, root=root)
    except audit_producer_chain.AuditProducerChainError as exc:
        raise RenderingVerificationError(str(exc)) from exc
    expected = {
        "target": plan.get("batch_id"),
        "review_due": None,
        "status": "required",
        "evidence_ref": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    }
    mismatches = [field for field, value in expected.items()
                  if obligation.get(field) != value]
    if chain.get("execution_route") != "rendering-verification":
        mismatches.append("precursor_chain")
    if mismatches:
        raise RenderingVerificationError(
            "obligation %s is not the K12/02 every-batch rendering-record "
            "requirement in: %s" %
            (obligation_id, ", ".join(sorted(mismatches))))
    return obligation


def _record_input(*, rendering_mode, visual_trigger,
                  unresolved_question, verification_target,
                  verification_result, contract):
    values = rendering_verification_contract.validate_contract(contract)
    mode = values["modes"].get(rendering_mode)
    if mode is None:
        raise RenderingVerificationError(
            "rendering_mode is not registered by K12/02")
    visual_trigger = _optional_text(visual_trigger, "visual_trigger")
    unresolved_question = _optional_text(
        unresolved_question, "unresolved_question")
    verification_target = _optional_text(
        verification_target, "verification_target")
    verification_result = _optional_text(
        verification_result, "verification_result")
    if not mode["escalation"] and visual_trigger is None:
        visual_trigger = "not_applicable"
    return {
        "rendering_mode": rendering_mode,
        "highest_level": mode["highest_level"],
        "visual_trigger": visual_trigger,
        "unresolved_question": unresolved_question,
        "verification_target": verification_target,
        "verification_result": verification_result,
    }


def _dependency_fingerprint(record_input, contract):
    return rendering_verification_contract.record_dependency_fingerprint(
        record_input, contract)


def build_record(*, root, plan, plan_sha256, obligation, frozen,
                 rendering_mode, visual_trigger=None,
                 unresolved_question=None, verification_target=None,
                 verification_result=None, contract=None, seq=1):
    """Build one full producer-evidence record from frozen plan inputs."""
    contract = contract or rendering_verification_contract.load_contract(root)
    rendering_verification_contract.validate_contract(contract)
    resolved = resolve_obligation(
        plan, obligation["obligation_id"], contract, root=root)
    if resolved != obligation:
        raise RenderingVerificationError(
            "caller obligation differs from the frozen AuditPlan row")
    if not isinstance(frozen, (tuple, list)) or not frozen:
        raise RenderingVerificationError(
            "rendering record requires a non-empty frozen batch manifest")
    scope = sorted(page.path for page in frozen)
    if (len(scope) != len(set(scope)) or
            any(not isinstance(path, str) or not path for path in scope)):
        raise RenderingVerificationError(
            "frozen batch manifest paths must be non-empty and unique")
    record_input = _record_input(
        rendering_mode=rendering_mode,
        visual_trigger=visual_trigger,
        unresolved_question=unresolved_question,
        verification_target=verification_target,
        verification_result=verification_result,
        contract=contract)
    artifact_fingerprint = \
        audit_producer_runtime.page_set_artifact_fingerprint(frozen)
    contract_fingerprint = \
        audit_producer_runtime.obligation_contract_fingerprint(
            plan, obligation, additional={
                "rendering_verification_contract_sha256":
                    rendering_verification_contract.contract_sha256(
                        contract),
            })
    identity = {
        "task_id": plan["task_id"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
    }
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, obligation["target"], "pass",
        "K12/02 rendering record shape is complete; this does not attest "
        "Level 0/1 execution or visual correctness",
        seq,
        receipt_type_id=rendering_verification_contract.RECEIPT_TYPE_ID,
        root=root, identity=identity)
    receipt.update({
        "schema_version": contract["schema_version"],
        "record_kind": contract["record_kind"],
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt":
            plan["opening_transition_receipt"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "scope": scope,
        "artifact_fingerprint": artifact_fingerprint,
        "dependency_fingerprint": _dependency_fingerprint(
            record_input, contract),
        "contract_fingerprint": contract_fingerprint,
        "fingerprint_binding": obligation["fingerprint_binding"],
        "acceptance_predicate": obligation["acceptance_predicate"],
        "dimension": obligation["dimension"],
        **record_input,
    })
    rendering_verification_contract.validate_record(receipt, contract)
    return receipt


def validate_record_for_plan(record, plan, plan_sha256, obligation, frozen,
                             contract=None, root=None):
    """Validate exact plan, manifest, and evidence-time fingerprint binding."""
    contract = contract or rendering_verification_contract.load_contract(root)
    try:
        audit_producer_chain.require_precursor_record(
            record, obligation, root=root)
    except audit_producer_chain.AuditProducerChainError as exc:
        raise RenderingVerificationError(str(exc)) from exc
    rendering_verification_contract.validate_record_for_obligation(
        record, plan, plan_sha256, obligation, contract)
    expected = {
        "scope": sorted(page.path for page in frozen),
        "artifact_fingerprint":
            audit_producer_runtime.page_set_artifact_fingerprint(frozen),
    }
    mismatches = [field for field, value in expected.items()
                  if record.get(field) != value]
    if mismatches:
        raise RenderingVerificationError(
            "rendering-verification evidence differs from AuditPlan in: %s" %
            ", ".join(sorted(set(mismatches))))
    return record


def _reject_existing(result, plan, plan_sha256, obligation, frozen,
                     contract, root):
    """Reject only an attempt that still observes the current batch input.

    The current receipt catalog is append-only authority history, not an
    input-currentness index.  A structurally valid predecessor whose frozen
    page-set fingerprint no longer matches ``frozen`` remains history and
    must not prevent a successor attempt.
    """
    matches = audit_producer_runtime.obligation_attempt_records(
        result, tool=TOOL, plan_id=plan["plan_id"],
        obligation_id=obligation["obligation_id"])

    def validate_stable(record):
        audit_producer_chain.require_precursor_record(
            record, obligation, root=root)
        return rendering_verification_contract.validate_record_for_obligation(
            record, plan, plan_sha256, obligation, contract)

    existing = evidence_attempt_runtime.unique_current_attempt(
        matches,
        validate_stable=validate_stable,
        validate_current=lambda record: validate_record_for_plan(
            record, plan, plan_sha256, obligation, frozen,
            contract=contract, root=root),
        label="AuditPlan obligation %s rendering evidence" %
              obligation["obligation_id"])
    if existing is not None:
        raise RenderingVerificationError(
            "rendering-record obligation already has current producer "
            "evidence: %s" % existing["receipt_id"])


def _context(root_arg, batch_id, plan_path, obligation_id):
    root, result, authority = audit_producer_runtime.admitted_runtime(root_arg)
    item, _activation = audit_producer_runtime.open_batch(result, batch_id)
    stage = audit_evidence_runtime.resolve_stage_plan(
        result, item, "pre-merge", required_state="open")
    if stage["audit_plan_path"] != plan_path:
        raise RenderingVerificationError(
            "current AuditPlan path is %s, not %s" %
            (stage["audit_plan_path"], plan_path))
    contract = rendering_verification_contract.load_contract(root)
    obligation = resolve_obligation(
        stage["plan"], obligation_id, contract, root=root)
    frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
    _reject_existing(
        result, stage["plan"], stage["audit_plan_sha256"], obligation,
        frozen, contract, root)
    return {
        "root": root, "result": result, "authority": authority,
        "item": item, "stage": stage, "plan": stage["plan"],
        "plan_sha256": stage["audit_plan_sha256"],
        "obligation": obligation, "frozen": frozen, "contract": contract,
    }


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record one plan-bound K12/02 rendering record shape")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--obligation-id", required=True)
    parser.add_argument(
        "--rendering-mode", required=True,
        choices=tuple(sorted(rendering_verification_contract.RENDERING_MODES)))
    parser.add_argument("--visual-trigger")
    parser.add_argument("--unresolved-question")
    parser.add_argument("--verification-target")
    parser.add_argument("--verification-result")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        context = _context(
            args.root, args.batch, args.plan, args.obligation_id)
        receipt = build_record(
            root=context["root"], plan=context["plan"],
            plan_sha256=context["plan_sha256"],
            obligation=context["obligation"], frozen=context["frozen"],
            rendering_mode=args.rendering_mode,
            visual_trigger=args.visual_trigger,
            unresolved_question=args.unresolved_question,
            verification_target=args.verification_target,
            verification_result=args.verification_result,
            contract=context["contract"])
        receipt_absolute = audit_producer_runtime.managed_receipt_path(
            context["root"], args.receipts)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        reporting.write_canonical_json(
            {"applied": False, "errors": [str(exc)], "status": "invalid"})
        return 1

    if not args.apply:
        reporting.write_canonical_json({
            "applied": False,
            "errors": [],
            "status": "planned",
            "receipt_id": receipt["receipt_id"],
            "receipt_path": args.receipts,
            "result": receipt["result"],
        })
        return 0

    operation = audit_producer_runtime.runtime_lock_metadata(
        TOOL, "record-rendering-verification", context["result"],
        context["authority"], batch_id=args.batch,
        plan_id=context["plan"]["plan_id"],
        obligation_id=context["obligation"]["obligation_id"],
        receipt_id=receipt["receipt_id"])
    try:
        with kblib.runtime_write_lock(
                context["root"], owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = audit_producer_runtime.require_runtime_current(
                    context["root"], context["authority"],
                    "before rendering-record publication")
                locked_item, _ = audit_producer_runtime.open_batch(
                    locked, args.batch)
                locked_stage = audit_evidence_runtime.resolve_stage_plan(
                    locked, locked_item, "pre-merge", required_state="open")
                if (locked_stage["audit_plan_path"] != args.plan or
                        locked_stage["audit_plan_sha256"] !=
                        context["plan_sha256"] or
                        locked_stage["plan"] != context["plan"]):
                    raise RenderingVerificationError(
                        "AuditPlan changed before rendering-record publication")
                audit_producer_runtime.require_pages_current(
                    context["root"], context["frozen"],
                    "before rendering-record publication")
                locked_contract = \
                    rendering_verification_contract.load_contract(
                        context["root"])
                rebuilt = build_record(
                    root=context["root"], plan=context["plan"],
                    plan_sha256=context["plan_sha256"],
                    obligation=context["obligation"],
                    frozen=context["frozen"],
                    rendering_mode=args.rendering_mode,
                    visual_trigger=args.visual_trigger,
                    unresolved_question=args.unresolved_question,
                    verification_target=args.verification_target,
                    verification_result=args.verification_result,
                    contract=locked_contract)
                for field in ("receipt_id", "checked_at"):
                    rebuilt[field] = receipt[field]
                if rebuilt != receipt:
                    raise RenderingVerificationError(
                        "rendering-record bindings changed before publication")
                before = kblib.receipt_append_observation(
                    receipt_absolute, [receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_absolute, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise RenderingVerificationError(
                    "rendering-record publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        reporting.write_canonical_json({
            "applied": False,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    try:
        persisted = [
            row for row in audit_producer_runtime.read_receipt_records(
                receipt_absolute)
            if row.get("receipt_id") == receipt["receipt_id"]
        ]
        if len(persisted) != 1 or persisted[0] != receipt:
            raise RenderingVerificationError(
                "published rendering record did not read back exactly")
        validate_record_for_plan(
            persisted[0], context["plan"], context["plan_sha256"],
            context["obligation"], context["frozen"],
            context["contract"], context["root"])
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        reporting.write_canonical_json({
            "applied": True,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    reporting.write_canonical_json({
        "applied": True,
        "errors": [],
        "status": "recorded",
        "receipt_id": receipt["receipt_id"],
        "receipt_path": args.receipts,
        "result": receipt["result"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
