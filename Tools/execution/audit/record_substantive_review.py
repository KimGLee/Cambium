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
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
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


def _prior_round(result, receipt_id, plan, plan_sha256, obligation, page):
    if not receipt_id:
        return None
    prior = audit_producer_runtime.receipt_by_id(result, receipt_id)
    if not isinstance(prior, dict):
        raise audit_producer_runtime.AuditProducerError(
            "round-1 substantive-review receipt %s is not current" %
            receipt_id)
    substantive_review_contract.validate_review_receipt(
        prior, substantive_review_contract.load_contract(result["root"]))
    audit_producer_runtime.validate_obligation_attempt_binding(
        prior, plan, plan_sha256, obligation)
    expected = {
        "round": 1,
        "round_1_receipt_id": None,
    }
    mismatches = [field for field, value in expected.items()
                  if prior.get(field) != value]
    if prior.get("invalidated_by") is not None:
        mismatches.append("invalidated_by")
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "round-1 receipt differs in %s" % ", ".join(mismatches))
    return prior


def _require_round_two_scope(prior, findings):
    prior_rows = prior.get("findings") or []
    prior_by_id = {row.get("finding_id"): row for row in prior_rows}
    references = [row.get("round_1_finding_id") for row in findings
                  if isinstance(row, dict)]
    if (len(references) != len(findings) or
            len(references) != len(set(references)) or
            set(references) != set(prior_by_id)):
        raise audit_producer_runtime.AuditProducerError(
            "round 2 must confirm every and only round 1 finding exactly once")
    for row in findings:
        before = prior_by_id[row["round_1_finding_id"]]
        if (row.get("severity") != before.get("severity") or
                row.get("statement") != before.get("statement")):
            raise audit_producer_runtime.AuditProducerError(
                "round 2 cannot change finding severity or statement")


def current_review_attempt(result, plan, plan_sha256, obligation, frozen,
                           root):
    """Return the sole review attempt that observes the current page bytes."""
    page = audit_producer_runtime.frozen_manifest_page(
        frozen, obligation["target"])
    if page is None:
        raise audit_producer_runtime.AuditProducerError(
            "substantive-review target is not one frozen manifest page")
    contract = substantive_review_contract.load_contract(root)
    attempts = audit_producer_runtime.obligation_attempt_records(
        result, tool=TOOL, plan_id=plan["plan_id"],
        obligation_id=obligation["obligation_id"],
        record_kind=contract["record_kind"])
    by_id = {record["receipt_id"]: record for record in attempts}

    def validate_stable(record):
        substantive_review_contract.validate_review_receipt(record, contract)
        if record.get("tool_version") != TOOL_VERSION:
            raise ValueError(
                "substantive-review tool version is not supported")
        audit_producer_runtime.validate_obligation_attempt_binding(
            record, plan, plan_sha256, obligation)
        if record.get("contract_fingerprint") != \
                audit_producer_runtime.obligation_contract_fingerprint(
                    plan, obligation):
            raise ValueError(
                "substantive-review contract fingerprint differs from plan")
        if record.get("round") == 2:
            prior = by_id.get(record.get("round_1_receipt_id"))
            if prior is None:
                raise ValueError(
                    "round 2 has no stable round-1 predecessor")
            substantive_review_contract.validate_review_pair(
                prior, record, contract)
        return record

    def validate_current(record):
        validate_stable(record)
        text = page.snapshot.read_text()
        sources = audit_producer_runtime.sources_sha256(text)
        expected = {
            "page_sha256": page.page_sha256,
            "sources_sha256": sources,
            "semantic_content_fingerprint":
                page.semantic_content_fingerprint,
            "artifact_fingerprint":
                audit_producer_runtime.page_artifact_fingerprint(page),
            "dependency_fingerprint": sources,
        }
        mismatches = [field for field, value in expected.items()
                      if record.get(field) != value]
        if mismatches:
            raise ValueError(
                "substantive-review input changed in: %s" %
                ", ".join(sorted(mismatches)))
        return record

    try:
        return evidence_attempt_runtime.unique_current_attempt(
            attempts, validate_stable=validate_stable,
            validate_current=validate_current,
            label="AuditPlan obligation %s substantive review" %
                  obligation["obligation_id"])
    except evidence_attempt_runtime.EvidenceAttemptError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc


def _require_no_current_attempt(result, plan, plan_sha256, obligation,
                                frozen, root):
    existing = current_review_attempt(
        result, plan, plan_sha256, obligation, frozen, root)
    if existing is not None:
        raise audit_producer_runtime.AuditProducerError(
            "substantive-review obligation already has current evidence: %s" %
            existing["receipt_id"])


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
        _require_round_two_scope(prior, findings)

    page_snapshot = audit_producer_runtime.frozen_manifest_page(frozen, page)
    if page_snapshot is None:
        raise audit_producer_runtime.AuditProducerError(
            "page %s is not exactly one member of the open batch" % page)
    sources_digest = audit_producer_runtime.sources_sha256(
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
        obligation = _obligation(
            root, plan, args.obligation_id, args.page)
        _require_no_current_attempt(
            result, plan, plan_sha256, obligation, frozen, root)
        findings = parse_findings(args.finding)
        prior = _prior_round(
            result, args.round_1_receipt_id, plan, plan_sha256,
            obligation, args.page)
        if args.round == 1 and args.round_1_receipt_id:
            raise audit_producer_runtime.AuditProducerError(
                "round 1 does not accept --round-1-receipt-id")
        receipt = build_review_receipt(
            root=root, result=result, plan=plan,
            plan_sha256=plan_sha256, obligation=obligation, page=args.page,
            frozen=frozen, authoring_context_id=args.authoring_context_id,
            reviewer_context_id=args.reviewer_context_id,
            reviewer_role=args.reviewer_role, round_number=args.round,
            verdict=args.verdict, findings=findings,
            statement=args.statement, prior=prior)
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
                _require_no_current_attempt(
                    locked, plan, plan_sha256, obligation, frozen, root)
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
