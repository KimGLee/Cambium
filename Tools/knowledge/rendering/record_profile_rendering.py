#!/usr/bin/env python3
"""Render frozen Profile obligations and publish their separate verified evidence."""

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_lifecycle_contract as lifecycle
import Tools.execution.audit.audit_producer_chain as audit_producer_chain
import Tools.execution.audit.audit_producer_runtime as producer_runtime
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.knowledge.rendering.profile_rendering_evidence_contract as contract
import Tools.platform.common.kblib as kblib
from Tools.platform.common import reporting


TOOL = contract.TOOL
TOOL_VERSION = contract.TOOL_VERSION
CHECK = contract.CHECK
DEFAULT_RECEIPTS = runtime_paths.PROFILE_RENDERING_RECEIPT_PATH


def build_record(*, root, plan, plan_sha256, obligation, evaluation, page, report, seq=1):
    admission = contract.load_profile_admission(
        root, plan["selected_profile_manifest"], evaluation=evaluation)
    profile = admission.contract
    rendering = contract.rendering_contract(profile)
    rule = contract.rule_for_obligation(profile, obligation)
    text = page.snapshot.read_text()
    kinds = contract.require_bindings([(page.path, text)], profile, root=root)[page.path]
    if rule.construct not in kinds:
        raise ValueError("obligation construct is absent from current source")
    bindings = {rule.construct: rule.acceptance}
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, page.path, report["result"],
        "Profile rendering compiler report for %s" % rule.rule_id, seq,
        receipt_type_id=contract.RECEIPT_TYPE_ID, root=root,
        identity={field: plan[field] for field in
                  ("task_id", "upstream_revision_id", "selected_profile_manifest")})
    receipt.update({
        **{field: plan[field] for field in lifecycle.PLAN_BINDING_FIELDS},
        **{field: obligation.get(field) for field in lifecycle.OBLIGATION_BINDING_FIELDS},
        "schema_version": 1, "record_kind": contract.RECORD_KIND,
        "plan_id": plan["plan_id"], "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"], "scope": [page.path],
        "construct": rule.construct, "render_bindings": bindings,
        "rendering_contract_sha256": rendering.fingerprint,
        "render_report": report,
        "artifact_fingerprint": producer_runtime.page_artifact_fingerprint(page),
        "dependency_fingerprint": contract.report_dependency_fingerprint(report),
        "contract_fingerprint": contract.contract_fingerprint(plan, obligation, rendering),
    })
    contract.validate_record_for_obligation(
        receipt, plan, plan_sha256, obligation, root=root,
        evaluation=evaluation, text=text)
    return receipt


def _context(root, batch, plan_path, obligation_id, *, shared=None):
    if shared is None:
        root, result, authority = producer_runtime.admitted_runtime(root)
        item, _ = producer_runtime.open_batch(result, batch)
        stage = audit_evidence_runtime.resolve_stage_plan(
            result, item, "pre-merge", required_state="open", plan_path=plan_path)
        frozen = producer_runtime.freeze_manifest_pages(root, result, item)
    else:
        root, result, authority, item, stage, frozen = shared
    if stage["audit_plan_path"] != plan_path:
        raise ValueError("requested rendering plan is not the current AuditPlan")
    plan = stage["plan"]
    matches = [row for row in plan["obligations"] if row["obligation_id"] == obligation_id]
    if len(matches) != 1:
        raise ValueError("rendering requires one exact AuditPlan obligation")
    obligation = matches[0]
    evaluation = result["_profile_authorized_view"]["_evaluation"]
    chain = audit_producer_chain.producer_chain_for_obligation(
        obligation, root=root, evaluation=evaluation)
    if chain["execution_route"] != "profile-rendering" or obligation["status"] != "required":
        raise ValueError("obligation is not a required Profile rendering producer")
    page = producer_runtime.frozen_manifest_page(frozen, obligation["target"])
    if page is None:
        raise ValueError("Profile rendering target is not a current manifest page")
    profile = result["_profile_authorized_view"]["_contract"]
    attempts = producer_runtime.obligation_attempt_records(
        result, tool=TOOL, plan_id=plan["plan_id"], obligation_id=obligation_id)

    def stable(record):
        return contract.validate_record_for_obligation(
            record, plan, stage["audit_plan_sha256"], obligation,
            root=root, require_current=False)

    current = evidence_attempt_runtime.unique_current_attempt(
        attempts, validate_stable=stable,
        validate_current=lambda record: contract.validate_record_for_obligation(
            record, plan, stage["audit_plan_sha256"], obligation, root=root,
            evaluation=evaluation, text=page.snapshot.read_text()),
        label="Profile rendering obligation %s" % obligation_id)
    if current is not None:
        raise ValueError("Profile rendering obligation already has current evidence")
    return root, result, authority, item, stage, obligation, frozen, page, profile


def main(argv=None):
    parser = kblib.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True, help="current open Queue batch ID")
    parser.add_argument("--plan", required=True, help="current AuditPlan path")
    parser.add_argument("--obligation-id", required=True, action="append",
                        help="exact Profile rendering obligation; repeat for a read-only compute group")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS, help="managed receipt register")
    parser.add_argument("--apply", action="store_true", help="publish verified rendering evidence")
    args = parser.parse_args(argv)
    receipt = None
    publication = kblib.ReceiptPublication()
    try:
        (root, result, authority, item, stage, obligation, frozen, page,
         profile) = _context(args.root, args.batch, args.plan, args.obligation_id[0])
        if len(set(args.obligation_id)) != len(args.obligation_id):
            raise ValueError("obligation identities must be unique")
        shared = (root, result, authority, item, stage, frozen)
        pairs = [(obligation, page)]
        for identity in args.obligation_id[1:]:
            current = _context(root, args.batch, args.plan, identity, shared=shared)
            pairs.append((current[5], current[7]))
        from Tools.knowledge.rendering import static_render_runtime
        binding = producer_runtime.computation_binding(root, result)
        jobs = []
        for obligation, page in pairs:
            rule = contract.rule_for_obligation(profile, obligation)
            jobs.append({"text": contract.rendering_source(page.snapshot.read_text()),
                         "target": page.path, "bindings": {rule.construct: rule.acceptance}})
        reports = static_render_runtime.render_pages(jobs, root=root)
        if any(report.get("result") != "pass" for report in reports):
            reporting.write_canonical_json(reporting.publication_result(
                publication, status="failed", reports=reports))
            return 1
        receipts = [build_record(
            root=root, plan=stage["plan"], plan_sha256=stage["audit_plan_sha256"],
            obligation=obligation, evaluation=result["_profile_authorized_view"]["_evaluation"],
            page=page, report=report, seq=index)
            for index, ((obligation, page), report) in enumerate(zip(pairs, reports), 1)]
        receipt = receipts[0]
        receipt_path = producer_runtime.managed_receipt_path(root, args.receipts)
        if not args.apply:
            reporting.write_canonical_json(reporting.publication_result(
                publication, status="planned", receipt=receipt, receipts=receipts))
            return 0
        operation = producer_runtime.runtime_lock_metadata(
            TOOL, "record-profile-rendering", result, authority, batch_id=args.batch,
            plan_id=stage["plan"]["plan_id"], obligation_id=args.obligation_id[0],
            receipt_id=receipt["receipt_id"])
        with publication.locked_append(root, receipt_path, receipts,
                operation=operation, label="record_profile_rendering publication"):
            locked = producer_runtime.require_runtime_current(root, authority, "before rendering publication")
            locked_item, _ = producer_runtime.open_batch(locked, args.batch)
            current_stage = audit_evidence_runtime.resolve_stage_plan(
                locked, locked_item, "pre-merge", required_state="open", plan_path=args.plan)
            if current_stage["plan"] != stage["plan"] or current_stage["audit_plan_sha256"] != stage["audit_plan_sha256"]:
                raise ValueError("AuditPlan changed before rendering publication")
            producer_runtime.require_pages_current(root, frozen, "before rendering publication")
            producer_runtime.require_computation_current(root, locked, binding)
            for (obligation, _), receipt in zip(pairs, receipts):
                _context(root, args.batch, args.plan, obligation["obligation_id"],
                    shared=(root, locked, authority, locked_item, current_stage, frozen))
                contract.validate_record_for_obligation(
                    receipt, stage["plan"], stage["audit_plan_sha256"], obligation,
                    root=root, evaluation=locked["_profile_authorized_view"]["_evaluation"])
        ids = {row["receipt_id"] for row in receipts}
        persisted = [row for row in producer_runtime.read_receipt_records(
                         receipt_path, observation=publication.observation)
                     if row.get("receipt_id") in ids]
        if persisted != receipts:
            raise ValueError("rendering receipt read-back differs from publication")
        publication.confirmed = True
        reporting.write_canonical_json(reporting.publication_result(
            publication, status="published", receipt=receipts[0], receipts=receipts))
        return 0
    except (OSError, TypeError, UnicodeError, ValueError, RuntimeError,
            kblib.RuntimeStateLockedError) as exc:
        reporting.write_canonical_json(reporting.publication_result(
            publication, status="invalid", errors=[str(exc)]))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
