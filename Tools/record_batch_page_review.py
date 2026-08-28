#!/usr/bin/env python3
"""Record one plan-bound M atom or sampled-S Batch Review judgment.

The CLI never chooses a new obligation.  It resolves one immutable AuditPlan
row back to the Kernel K12/14 registry, freezes the three evidence-time
fingerprints, and publishes one closed append-only producer record.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_plan_contract
import audit_producer_runtime
import batch_review_obligation_contract as batch_contract
import changed_scope_rendering_checks
import check_queue
import kblib
import runtime_paths


TOOL = batch_contract.PRODUCER_TOOL
TOOL_VERSION = batch_contract.PRODUCER_TOOL_VERSION
DEFAULT_RECEIPTS = runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise audit_producer_runtime.AuditProducerError(
            "%s must be a non-empty string" % label)
    return value.strip()


def _coverage_tiers(result, manifest):
    rows = (result.get("coverage") or {}).get("pages") or []
    tiers = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        tier = row.get("tier")
        if path in tiers and tiers[path] != tier:
            raise audit_producer_runtime.AuditProducerError(
                "Coverage repeats page %s with different tiers" % path)
        if isinstance(path, str):
            tiers[path] = tier
    missing = [path for path in manifest if tiers.get(path) not in {
        "L", "M", "S"}]
    if missing:
        raise audit_producer_runtime.AuditProducerError(
            "manifest pages lack an admitted tier: %s" % ", ".join(missing))
    return {path: tiers[path] for path in manifest}


def _require_plan_runtime_binding(plan, result, item):
    state = audit_producer_runtime.runtime_state_bindings(result)
    profile = audit_producer_runtime.profile_bindings(result)
    standards = audit_producer_runtime.standards_bindings(result)
    opening = check_queue.current_opening_semantic_context(
        result, item["id"])
    expected = {
        "task_id": state["task_id"],
        "batch_id": item["id"],
        "queue_revision": state["queue_revision"],
        "queue_state_revision": state["queue_state_revision"],
        "required_queue_sha256": state["required_queue_sha256"],
        "standards_version": standards["standards_version"],
        "active_standards_sha256": standards["active_standards_sha256"],
        "selected_profile_manifest": profile["selected_profile_manifest"],
        "profile_snapshot_sha256": profile["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            profile["profile_contract_fingerprint"],
        "opening_transition_receipt":
            opening["opening_transition_receipt"],
        "accepted_baseline_sha256":
            opening["manifest_semantic_before_set_sha256"],
    }
    mismatches = [field for field, value in expected.items()
                  if plan.get(field) != value]
    if mismatches:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan runtime binding drifted in: %s" %
            ", ".join(sorted(mismatches)))


def load_current_plan(root, relative, result, item):
    absolute = audit_producer_runtime.managed_plan_path(
        root, relative, must_exist=True)
    snapshot = kblib.repository_target_snapshot(
        root, relative, suffixes=(".yaml",), singly_linked=True)
    if not snapshot.exists:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan file is absent")
    text = snapshot.read_text()
    plan = kblib.parse_yaml_subset(text)
    audit_plan_contract.validate_plan(
        plan, audit_plan_contract.load_contract(root))
    if text != kblib.canonical_yaml(plan):
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan bytes are not canonical")
    digest = audit_plan_contract.plan_sha256(plan)
    if digest != kblib.sha256_file(absolute):
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan canonical digest differs from stored bytes")
    _require_plan_runtime_binding(plan, result, item)
    tiers = _coverage_tiers(result, item["manifest"])
    registry = batch_contract.load_registry(root)
    closure = batch_contract.validate_plan_base_closure(
        plan, item["manifest"], tiers, registry)
    frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
    changed_scope_rendering_checks.require_profile_rendering_contract_state(
        ((page.path, page.snapshot.read_text()) for page in frozen),
        contract_is_bound_and_valid=False)
    return (absolute, plan, digest, frozen, tiers, registry, closure,
            snapshot)


def _require_plan_bytes_current(root, relative, before):
    current = kblib.repository_target_snapshot(
        root, relative, suffixes=(".yaml",), singly_linked=True)
    identity_fields = (
        "exists", "repository_path", "dev", "ino", "mode", "nlink",
        "size", "mtime_ns", "ctime_ns", "data",
    )
    if any(getattr(current, field) != getattr(before, field)
           for field in identity_fields):
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan bytes changed before evidence publication")


def _frozen_page(frozen, page):
    matches = [value for value in frozen if value.path == page]
    if len(matches) != 1:
        raise audit_producer_runtime.AuditProducerError(
            "page %s is not exactly one frozen manifest member" % page)
    return matches[0]


def _required_obligation(plan, obligation_id, page, variant, registry):
    matches = [row for row in plan.get("obligations") or []
               if isinstance(row, dict) and
               row.get("obligation_id") == obligation_id]
    if len(matches) != 1:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan must contain exactly one obligation %s" %
            obligation_id)
    obligation = matches[0]
    if obligation.get("target") != page:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan obligation targets a different page")
    try:
        spec = batch_contract.obligation_spec_for_rule(
            obligation.get("owner_rule_id"), registry)
    except ValueError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc
    expected_variant = (
        "m-atomic-item" if spec["tier"] == "M" else "s-sampled-page")
    if variant != expected_variant:
        raise audit_producer_runtime.AuditProducerError(
            "--variant %s disagrees with plan rule %s" %
            (variant, spec["rule_id"]))
    if obligation.get("status") != "required":
        raise audit_producer_runtime.AuditProducerError(
            "batch-page producer accepts only a required obligation")
    if any(obligation.get(field) is not None for field in (
            "evidence_ref", "reused_receipt_id", "reuse_reason")):
        raise audit_producer_runtime.AuditProducerError(
            "required obligation already predeclares evidence")
    return obligation, spec


def _current_consumed_records(result, receipt_ids, *, plan, plan_sha256,
                              spec, page, disposition, registry):
    receipt_ids = sorted(receipt_ids or [])
    if (len(receipt_ids) != len(set(receipt_ids)) or
            any(not isinstance(value, str) or not value for value in receipt_ids)):
        raise audit_producer_runtime.AuditProducerError(
            "consumed evidence references must be sorted unique IDs")
    try:
        return list(batch_contract.resolve_consumed_evidence(
            plan, plan_sha256, spec, page,
            check_queue.current_receipt_catalog(result), receipt_ids,
            disposition, registry))
    except ValueError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc


def _obligation_projection_errors(obligation, spec):
    expected = {
        "owner_kind": spec["owner_kind"],
        "owner_rule_id": spec["owner_rule_id"],
        "kernel_extension_point": spec["kernel_extension_point"],
        "applicability": spec["applicability"],
        "due_stage": spec["due_stage"],
        "evidence_role": spec["evidence_role"],
        "evidence_kind": spec["evidence_kind"],
        "dimension": spec["dimension"],
        "acceptance_predicate": spec["acceptance_predicate"],
        "producer_check": spec["producer_check"],
        "producer_capability": spec["producer_capability"],
        "producer_gate_id": spec["producer_gate_id"],
        "consumer_gate_id": spec["consumer_gate_id"],
        "fingerprint_binding": spec["fingerprint_binding"],
        "review_due": spec["review_due"],
    }
    errors = [field for field, value in expected.items()
              if obligation.get(field) != value]
    if spec["tier"] == "M":
        allowed = {row["partition"]
                   for row in spec["trigger_partition_mappings"]}
        if obligation.get("partition") not in allowed:
            errors.append("partition")
    elif obligation.get("partition") != spec["partition"]:
        errors.append("partition")
    return sorted(set(errors))


def build_review_receipt(*, root, plan, plan_sha256, obligation, spec,
                         page_snapshot, reviewer_context_id, reviewer_role,
                         verdict, statement, consumed_records=(),
                         applicability_disposition=None,
                         applicability_reason=None,
                         selection=None, registry=None, identity=None, seq=1):
    """Build one closed record from evidence-time page/dependency bytes."""
    registry = registry or batch_contract.load_registry(root)
    reviewer_context_id = _nonempty(
        reviewer_context_id, "reviewer context ID")
    reviewer_role = _nonempty(reviewer_role, "reviewer role")
    statement = _nonempty(statement, "review statement")
    errors = _obligation_projection_errors(obligation, spec)
    if errors:
        raise audit_producer_runtime.AuditProducerError(
            "batch-page obligation projection drifts in: %s" %
            ", ".join(errors))
    if verdict not in {"passed", "changes-required"}:
        raise audit_producer_runtime.AuditProducerError(
            "batch-page verdict must be passed or changes-required")
    consumed_records = tuple(consumed_records or ())
    if spec["tier"] == "M" and selection is not None:
        raise audit_producer_runtime.AuditProducerError(
            "M atomic evidence cannot carry an S selection")
    if spec["tier"] == "M":
        try:
            disposition = batch_contract.validate_applicability_disposition(
                spec, applicability_disposition, applicability_reason,
                registry)
        except ValueError as exc:
            raise audit_producer_runtime.AuditProducerError(str(exc)) from exc
    else:
        if (applicability_disposition is not None or
                applicability_reason is not None):
            raise audit_producer_runtime.AuditProducerError(
                "sampled S evidence cannot carry an M applicability disposition")
        disposition = None
    consumed_ids = sorted(record["receipt_id"] for record in consumed_records)
    if len(consumed_ids) != len(set(consumed_ids)):
        raise audit_producer_runtime.AuditProducerError(
            "consumed evidence repeats receipt_id")
    try:
        synthetic_catalog = {
            record["receipt_id"]: record for record in consumed_records
        }
        batch_contract.resolve_consumed_evidence(
            plan, plan_sha256, spec, page_snapshot.path,
            synthetic_catalog, consumed_ids,
            disposition["applicability_disposition"]
            if disposition is not None else "applicable",
            registry)
    except (KeyError, TypeError, ValueError) as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc

    text = page_snapshot.snapshot.read_text()
    sources_digest = audit_producer_runtime.sources_sha256(text)
    selection_fingerprint = (
        selection.get("selection_fingerprint") if selection else None)
    artifact_fingerprint = audit_producer_runtime.page_artifact_fingerprint(
        page_snapshot)
    dependency = batch_contract.dependency_fingerprint(
        sources_digest, consumed_records,
        selection_fingerprint=selection_fingerprint)
    contract = batch_contract.contract_fingerprint(spec, plan, registry)
    result = "pass" if verdict == "passed" else "fail"
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, spec["producer_check"],
        page_snapshot.path, result, statement, seq,
        root=root, identity=identity)
    receipt.update({
        "schema_version": 1,
        "record_kind": "batch-page-review-record",
        "review_variant": (
            "m-atomic-item" if spec["tier"] == "M"
            else "s-sampled-page"),
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt":
            plan["opening_transition_receipt"],
        "standards_version": plan["standards_version"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "tier": spec["tier"],
        "partition": obligation["partition"],
        "due_stage": spec["due_stage"],
        "evidence_role": spec["evidence_role"],
        "evidence_kind": spec["evidence_kind"],
        "dimension": spec["dimension"],
        "acceptance_predicate": spec["acceptance_predicate"],
        "producer_capability": spec["producer_capability"],
        "consumer_gate_id": spec["consumer_gate_id"],
        "fingerprint_binding": spec["fingerprint_binding"],
        "artifact_fingerprint": artifact_fingerprint,
        "dependency_fingerprint": dependency,
        "contract_fingerprint": contract,
        "semantic_content_fingerprint":
            page_snapshot.semantic_content_fingerprint,
        "reviewer_context_id": reviewer_context_id,
        "reviewer_role": reviewer_role,
        "verdict": verdict,
        "consumed_evidence_refs": consumed_ids,
    })
    if spec["tier"] == "M":
        receipt.update({
            "applicability_disposition":
                disposition["applicability_disposition"],
            "applicability_reason": disposition["applicability_reason"],
            "item_id": spec["item_id"],
            "rule_id": spec["rule_id"],
            "source_group": spec["source_group"],
        })
    else:
        if selection is None:
            raise audit_producer_runtime.AuditProducerError(
                "sampled S evidence requires the frozen selection")
        receipt.update(selection)
        receipt["selection_frozen_at"] = plan["generated_at"]
    batch_contract.validate_producer_receipt(receipt, registry)
    batch_contract.validate_page_fingerprint_binding(
        receipt, page_snapshot.path, text,
        page_snapshot.semantic_content_fingerprint)
    return receipt


def _emit(payload):
    sys.stdout.write(
        kblib.canonical_json_bytes(payload).decode("utf-8") + "\n")


def require_exact_readback(receipt_absolute, receipt, registry):
    """Prove resulting append-only state contains one exact valid record."""
    persisted = [
        row for row in audit_producer_runtime.read_receipt_records(
            receipt_absolute)
        if row.get("receipt_id") == receipt["receipt_id"]]
    if len(persisted) != 1 or persisted[0] != receipt:
        raise audit_producer_runtime.AuditProducerError(
            "published batch-page review receipt did not read back exactly")
    batch_contract.validate_producer_receipt(persisted[0], registry)
    return persisted[0]


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record one plan-bound Batch Review page judgment")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--obligation-id", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument(
        "--variant", required=True,
        choices=("m-atomic-item", "s-sampled-page"))
    parser.add_argument("--reviewer-context-id", required=True)
    parser.add_argument("--reviewer-role", required=True)
    parser.add_argument(
        "--verdict", required=True,
        choices=("passed", "changes-required"))
    parser.add_argument("--statement", required=True)
    parser.add_argument(
        "--applicability-disposition",
        choices=("applicable", "not-applicable"),
        help="required for M atoms; evidence-time disposition, not plan status")
    parser.add_argument(
        "--applicability-reason",
        help="required only when a conditional M atom is not applicable")
    parser.add_argument(
        "--consumed-evidence-ref", action="append", default=[],
        help="current canonical evidence consumed by a consumes-role M atom")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        root, result, authority = audit_producer_runtime.admitted_runtime(
            args.root)
        item, _activation = audit_producer_runtime.open_batch(
            result, args.batch)
        (_absolute, plan, plan_sha256, frozen, tiers, registry,
         closure, plan_snapshot) = load_current_plan(
             root, args.plan, result, item)
        obligation, spec = _required_obligation(
            plan, args.obligation_id, args.page, args.variant, registry)
        if tiers[args.page] != spec["tier"]:
            raise audit_producer_runtime.AuditProducerError(
                "review target tier disagrees with the plan rule")
        page_snapshot = _frozen_page(frozen, args.page)
        consumed = _current_consumed_records(
            result, args.consumed_evidence_ref,
            plan=plan, plan_sha256=plan_sha256, spec=spec,
            page=args.page,
            disposition=args.applicability_disposition,
            registry=registry)
        selection = (
            closure["s_selection"] if spec["tier"] == "S" else None)
        receipt = build_review_receipt(
            root=root, plan=plan, plan_sha256=plan_sha256,
            obligation=obligation, spec=spec, page_snapshot=page_snapshot,
            reviewer_context_id=args.reviewer_context_id,
            reviewer_role=args.reviewer_role, verdict=args.verdict,
            statement=args.statement, consumed_records=consumed,
            applicability_disposition=args.applicability_disposition,
            applicability_reason=args.applicability_reason,
            selection=selection, registry=registry)
        receipt_absolute = audit_producer_runtime.managed_receipt_path(
            root, DEFAULT_RECEIPTS)
        registry_digest = batch_contract.registry_sha256(registry)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        _emit({"applied": False, "errors": [str(exc)], "status": "invalid"})
        return 1

    if not args.apply:
        _emit({
            "applied": False,
            "errors": [],
            "status": "planned",
            "receipt_id": receipt["receipt_id"],
            "receipt_path": DEFAULT_RECEIPTS,
            "review_variant": receipt["review_variant"],
        })
        return 0 if receipt["result"] == "pass" else 1

    operation = audit_producer_runtime.runtime_lock_metadata(
        TOOL, "record-batch-page-review", result, authority,
        batch_id=args.batch, plan_id=plan["plan_id"],
        obligation_id=obligation["obligation_id"],
        receipt_id=receipt["receipt_id"])
    try:
        with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = audit_producer_runtime.require_runtime_current(
                    root, authority, "before batch-page review publication")
                locked_item, _locked_activation = \
                    audit_producer_runtime.open_batch(locked, args.batch)
                _require_plan_runtime_binding(plan, locked, locked_item)
                _require_plan_bytes_current(root, args.plan, plan_snapshot)
                locked_tiers = _coverage_tiers(
                    locked, locked_item["manifest"])
                locked_registry = batch_contract.load_registry(root)
                if batch_contract.registry_sha256(
                        locked_registry) != registry_digest:
                    raise audit_producer_runtime.AuditProducerError(
                        "batch-review registry changed before publication")
                locked_closure = batch_contract.validate_plan_base_closure(
                    plan, locked_item["manifest"], locked_tiers,
                    locked_registry)
                if locked_closure["s_selection"] != closure["s_selection"]:
                    raise audit_producer_runtime.AuditProducerError(
                        "S selection changed before publication")
                audit_producer_runtime.require_pages_current(
                    root, (page_snapshot,),
                    "before batch-page review publication")
                locked_consumed = _current_consumed_records(
                    locked, args.consumed_evidence_ref,
                    plan=plan, plan_sha256=plan_sha256, spec=spec,
                    page=args.page,
                    disposition=args.applicability_disposition,
                    registry=locked_registry)
                if locked_consumed != consumed:
                    raise audit_producer_runtime.AuditProducerError(
                        "consumed evidence changed before publication")
                batch_contract.validate_producer_receipt(
                    receipt, locked_registry)
                before = kblib.receipt_append_observation(
                    receipt_absolute, [receipt])
            outcome, error, _details = kblib.write_receipts_observed(
                receipt_absolute, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise audit_producer_runtime.AuditProducerError(
                    "batch-page review publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        _emit({
            "applied": False,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    try:
        require_exact_readback(receipt_absolute, receipt, registry)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        _emit({
            "applied": True,
            "errors": [str(exc)],
            "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    _emit({
        "applied": True,
        "errors": [],
        "status": "recorded",
        "receipt_id": receipt["receipt_id"],
        "receipt_path": DEFAULT_RECEIPTS,
        "review_variant": receipt["review_variant"],
    })
    return 0 if receipt["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
