#!/usr/bin/env python3
"""Record one explicit, plan-bound substantive-review judgment.

The external reviewer supplies the verdict and graded findings. This Tool
only validates the Kernel contract, binds the judgment to current bytes, and
publishes the append-only producer evidence consumed by AuditPlan completion.
"""

import json
import os
import sys

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_producer_chain as audit_producer_chain
import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.audit.substantive_review_contract as substantive_review_contract
from Tools.platform.common import reporting


TOOL = "record_substantive_review"
TOOL_VERSION = substantive_review_contract.CURRENT_PRODUCER_VERSION
CHECK = substantive_review_contract.OBLIGATION_PROJECTION["producer_check"]
DEFAULT_RECEIPTS = runtime_paths.SUBSTANTIVE_REVIEW_RECEIPT_PATH


def parse_findings(values):
    findings = []
    for index, raw in enumerate(values or []):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise audit_producer_runtime.AuditProducerError(
                "--finding %d is not one JSON object: %s" %
                (index + 1, exc))
        if not isinstance(value, dict):
            raise audit_producer_runtime.AuditProducerError(
                "--finding %d must decode to one object" % (index + 1))
        findings.append(value)
    return findings


def resolve_current_plan(root, relative, result, item):
    """Resolve the requested pre-merge plan through the neutral authority."""
    absolute = audit_producer_runtime.managed_plan_path(
        root, relative, must_exist=True)
    resolved = audit_evidence_runtime.resolve_stage_plan(
        result, item, "pre-merge", required_state="open",
        plan_path=relative)
    plan = resolved["plan"]
    digest = resolved["audit_plan_sha256"]
    if digest != kblib.sha256_file(absolute):
        raise audit_producer_runtime.AuditProducerError(
            "resolved AuditPlan digest differs from stored bytes")
    return absolute, plan, digest


def load_current_plan(root, relative, result, item, activation=None):
    del activation
    absolute, plan, digest = resolve_current_plan(
        root, relative, result, item)
    frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
    return absolute, plan, digest, frozen


def _require_plan_current(root, relative, result, item, plan, plan_sha256):
    """Re-resolve one plan for publication CAS without reprojecting it."""
    _absolute, current_plan, current_sha256 = resolve_current_plan(
        root, relative, result, item)
    if current_plan != plan or current_sha256 != plan_sha256:
        raise audit_producer_runtime.AuditProducerError(
            "resolved AuditPlan changed before evidence publication")


def _obligation(root, plan, obligation_id, page):
    matches = [row for row in plan.get("obligations") or []
               if isinstance(row, dict) and
               row.get("obligation_id") == obligation_id]
    if len(matches) != 1:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan must contain exactly one obligation %s" % obligation_id)
    row = matches[0]
    expected = {
        "target": page,
        "status": "required",
    }
    mismatches = [field for field, value in expected.items()
                  if row.get(field) != value]
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "obligation %s is not a current substantive-review requirement: "
            "%s" % (obligation_id, ", ".join(mismatches)))
    try:
        chain = audit_producer_chain.precursor_chain_for_obligation(
            row, root=root)
    except audit_producer_chain.AuditProducerChainError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc
    if (chain.get("execution_route") != "substantive-review" or
            chain.get("precursor_tool") != TOOL):
        raise audit_producer_runtime.AuditProducerError(
            "obligation has no substantive-review precursor chain")
    return row










def build_review_receipt(*, root, result, plan, plan_sha256, obligation,
                         page, frozen, authoring_context_id,
                         reviewer_context_id, reviewer_role, round_number,
                         verdict, findings, statement, prior=None, seq=1):
    authoring_context_id = audit_producer_runtime.require_nonempty_string(
        authoring_context_id, "authoring context ID")
    reviewer_context_id = audit_producer_runtime.require_nonempty_string(
        reviewer_context_id, "reviewer context ID")
    reviewer_role = audit_producer_runtime.require_nonempty_string(
        reviewer_role, "reviewer role")
    statement = audit_producer_runtime.require_nonempty_string(
        statement, "review statement")
    if authoring_context_id == reviewer_context_id:
        raise audit_producer_runtime.AuditProducerError(
            "reviewer context must differ from the authoring context")
    if round_number == 1 and prior is not None:
        raise audit_producer_runtime.AuditProducerError(
            "round 1 cannot cite a round-1 receipt")
    if round_number == 2:
        if prior is None:
            raise audit_producer_runtime.AuditProducerError(
                "round 2 requires the exact round-1 receipt")

    page_snapshot = audit_producer_runtime.frozen_manifest_page(frozen, page)
    if page_snapshot is None:
        raise audit_producer_runtime.AuditProducerError(
            "page %s is not exactly one member of the open batch" % page)
    sources_digest = audit_fingerprint.sources_sha256(
        page_snapshot.snapshot.read_text())
    contract_fingerprint = \
        audit_producer_runtime.obligation_contract_fingerprint(
            plan, obligation)

    result_value = "pass" if verdict == "passed" else "fail"
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, page, result_value, statement, seq,
        receipt_type_id=substantive_review_contract.RECEIPT_TYPE_ID,
        root=root)
    contract = substantive_review_contract.load_contract(root)
    receipt.update({
        "schema_version": contract["schema_version"],
        "record_kind": "substantive-review-evidence",
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
        "page_sha256": page_snapshot.page_sha256,
        "sources_sha256": sources_digest,
        "semantic_content_fingerprint":
            page_snapshot.semantic_content_fingerprint,
        "artifact_fingerprint":
            audit_producer_runtime.page_artifact_fingerprint(page_snapshot),
        "dependency_fingerprint": sources_digest,
        "contract_fingerprint": contract_fingerprint,
        "fingerprint_binding": obligation["fingerprint_binding"],
        "acceptance_predicate": obligation["acceptance_predicate"],
        "authoring_context_id": authoring_context_id,
        "reviewer_context_id": reviewer_context_id,
        "reviewer_role": reviewer_role,
        "round": round_number,
        "round_1_receipt_id": (
            prior.get("receipt_id") if prior is not None else None),
        "verdict": verdict,
        "findings": findings,
    })
    substantive_review_contract.validate_review_receipt(receipt, contract)
    if prior is not None:
        substantive_review_contract.validate_review_pair(
            prior, receipt, contract)
    return receipt


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record one plan-bound substantive correctness review")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--obligation-id", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--authoring-context-id", required=True)
    parser.add_argument("--reviewer-context-id", required=True)
    parser.add_argument("--reviewer-role", required=True)
    parser.add_argument("--round", required=True, type=int, choices=(1, 2))
    parser.add_argument(
        "--verdict", required=True,
        choices=("passed", "changes-required", "escalated"))
    parser.add_argument(
        "--finding", action="append", default=[],
        help="one finding object encoded as JSON; repeat for each finding")
    parser.add_argument("--statement", required=True)
    parser.add_argument("--round-1-receipt-id")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        root, result, authority = audit_producer_runtime.admitted_runtime(
            args.root)
        item, activation = audit_producer_runtime.open_batch(
            result, args.batch)
        _absolute, plan, plan_sha256, frozen = load_current_plan(
            root, args.plan, result, item, activation)
        result = audit_evidence_runtime.evidence_evaluation(result)
        obligation = _obligation(
            root, plan, args.obligation_id, args.page)
        findings = parse_findings(args.finding)
        prior = audit_evidence_runtime.require_substantive_review_attempt(
            result, item, plan, plan_sha256, obligation,
            round_number=args.round, round_1_receipt_id=args.round_1_receipt_id)
        receipt = build_review_receipt(
            root=root, result=result, plan=plan,
            plan_sha256=plan_sha256, obligation=obligation, page=args.page,
            frozen=frozen, authoring_context_id=args.authoring_context_id,
            reviewer_context_id=args.reviewer_context_id,
            reviewer_role=args.reviewer_role, round_number=args.round,
            verdict=args.verdict, findings=findings,
            statement=args.statement, prior=prior)
        proposed = audit_evidence_runtime.obligation_evidence_resolution(
            result, item, plan, plan_sha256, obligation,
            proposed_record=receipt)
        if proposed["status"] in {"invalid", "ambiguous", "missing"}:
            raise audit_producer_runtime.AuditProducerError(
                "proposed review is not acceptable: %s" % proposed.get("reason"))
        receipt_absolute = audit_producer_runtime.managed_receipt_path(
            root, args.receipts)
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
        })
        return 0 if receipt["result"] == "pass" else 1

    operation = audit_producer_runtime.runtime_lock_metadata(
        TOOL, "record-substantive-review", result, authority,
        batch_id=args.batch, plan_id=plan["plan_id"],
        receipt_id=receipt["receipt_id"])
    try:
        with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = audit_producer_runtime.require_runtime_current(
                    root, authority, "before substantive review publication")
                locked_item, _locked_activation = \
                    audit_producer_runtime.open_batch(locked, args.batch)
                _require_plan_current(
                    root, args.plan, locked, locked_item, plan, plan_sha256)
                audit_producer_runtime.require_pages_current(
                    root, frozen, "before substantive review publication")
                locked = audit_evidence_runtime.evidence_evaluation(locked)
                locked_prior = audit_evidence_runtime.require_substantive_review_attempt(
                    locked, locked_item, plan, plan_sha256, obligation,
                    round_number=args.round, round_1_receipt_id=args.round_1_receipt_id)
                if locked_prior != prior:
                    raise audit_producer_runtime.AuditProducerError(
                        "review predecessor changed before publication")
                proposed = audit_evidence_runtime.obligation_evidence_resolution(
                    locked, locked_item, plan, plan_sha256, obligation,
                    proposed_record=receipt)
                if proposed["status"] in {"invalid", "ambiguous", "missing"}:
                    raise audit_producer_runtime.AuditProducerError(
                        "proposed review is not acceptable: %s" % proposed.get("reason"))
                before = kblib.receipt_append_observation(
                    receipt_absolute, [receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_absolute, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise audit_producer_runtime.AuditProducerError(
                    "substantive-review publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        reporting.write_canonical_json({
            "applied": False,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    try:
        persisted = [row for row in
                     audit_producer_runtime.read_receipt_records(
                         receipt_absolute)
                     if row.get("receipt_id") == receipt["receipt_id"]]
        if len(persisted) != 1 or persisted[0] != receipt:
            raise audit_producer_runtime.AuditProducerError(
                "published substantive-review receipt did not read back exactly")
        substantive_review_contract.validate_review_receipt(
            persisted[0], substantive_review_contract.load_contract(root))
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
    })
    return 0 if receipt["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
