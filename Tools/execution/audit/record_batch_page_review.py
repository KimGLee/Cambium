#!/usr/bin/env python3
"""Publish explicit same-page M/S results through one original producer.

The existing reviews collection shares frozen material and preparation.
Every independent fact still has its own guarded append and exact read-back;
a later refusal never rolls back or conceals earlier confirmed publications.
"""

import sys

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.batch_review_obligation_contract as batch_contract
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.execution.task_runtime.queue_runtime.receipts as receipt_catalogs
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting


TOOL = batch_contract.PRODUCER_TOOL
TOOL_VERSION = batch_contract.PRODUCER_TOOL_VERSION
DEFAULT_RECEIPTS = runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH


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


def _resolve_current_plan(root, relative, result, item):
    absolute = audit_producer_runtime.managed_plan_path(
        root, relative, must_exist=True)
    resolved = audit_evidence_runtime.resolve_stage_plan(
        result, item, "pre-merge", required_state="open",
        plan_path=relative)
    snapshot = kblib.repository_target_snapshot(
        root, relative, suffixes=(".yaml",), singly_linked=True)
    if not snapshot.exists:
        raise audit_producer_runtime.AuditProducerError(
            "AuditPlan file is absent")
    plan = resolved["plan"]
    digest = resolved["audit_plan_sha256"]
    if digest != snapshot.sha256 or digest != kblib.sha256_file(absolute):
        raise audit_producer_runtime.AuditProducerError(
            "resolved AuditPlan digest differs from stored bytes")
    return absolute, plan, digest, snapshot


def load_current_plan(root, relative, result, item):
    absolute, plan, digest, snapshot = _resolve_current_plan(
        root, relative, result, item)
    tiers = _coverage_tiers(result, item["manifest"])
    registry = batch_contract.load_registry(root, cache_projection=True)
    closure = batch_contract.validate_plan_base_closure(
        plan, item["manifest"], tiers, registry)
    frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
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


def _required_obligation(plan, obligation_id, page, tier, registry):
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
    if tier != spec["tier"]:
        raise audit_producer_runtime.AuditProducerError(
            "Coverage tier %s disagrees with plan rule %s" %
            (tier, spec["rule_id"]))
    if obligation.get("status") != "required":
        raise audit_producer_runtime.AuditProducerError(
            "batch-page producer accepts only a required obligation")
    if any(obligation.get(field) is not None for field in (
            "evidence_ref", "reused_receipt_id", "reuse_reason")):
        raise audit_producer_runtime.AuditProducerError(
            "required obligation already predeclares evidence")
    return obligation, spec


def _current_consumed_records(result, item, receipt_ids, *, plan,
                              plan_sha256, obligation, spec, page, disposition,
                              registry):
    if receipt_ids is not None:
        if (len(receipt_ids) != len(set(receipt_ids)) or
                any(not isinstance(value, str) or not value
                    for value in receipt_ids)):
            raise audit_producer_runtime.AuditProducerError(
                "consumed evidence references must be unique IDs")
        receipt_ids = sorted(receipt_ids)
    try:
        current_receipt_ids = frozenset()
        if batch_contract.consumption_dependency_obligation_ids(
                plan["obligations"], obligation, registry):
            current_receipt_ids = \
                audit_evidence_runtime.current_consumption_evidence_ids(
                    result, item, plan, plan_sha256, obligation, registry)
        return list(batch_contract.resolve_consumed_evidence(
            plan, plan_sha256, spec, page,
            receipt_catalogs.current_receipt_catalog(result), receipt_ids,
            disposition, registry,
            current_receipt_ids=current_receipt_ids))
    except ValueError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc


def current_review_attempt(result, item, plan, plan_sha256, obligation, spec,
                           page_snapshot, registry):
    """Return the sole M/S review attempt bound to all current inputs."""
    attempts = audit_producer_runtime.obligation_attempt_records(
        result, tool=TOOL, plan_id=plan["plan_id"],
        obligation_id=obligation["obligation_id"],
        record_kind="batch-page-review-record")

    def validate_stable(record):
        batch_contract.validate_producer_receipt(record, registry)
        batch_contract.validate_record_plan_binding(record, plan, plan_sha256, obligation, registry)
        batch_contract.validate_plan_applicability(
            plan["obligations"], spec, obligation["target"],
            record.get("applicability_disposition"), registry)
        return record

    def validate_current(record):
        # unique_current_attempt already proved the stable Plan/variant and
        # applicability contract. Only the still-independent live inputs
        # remain here; stable rejection must never be classified as stale.
        text = page_snapshot.snapshot.read_text()
        consumed = _current_consumed_records(
            result, item, record.get("consumed_evidence_refs"),
            plan=plan, plan_sha256=plan_sha256, obligation=obligation,
            spec=spec,
            page=page_snapshot.path,
            disposition=record.get("applicability_disposition"),
            registry=registry)
        batch_contract.validate_input_binding(
            record, page_snapshot.path, text,
            page_snapshot.semantic_content_fingerprint,
            consumed_records=consumed)
        return record

    try:
        return evidence_attempt_runtime.unique_current_attempt(
            attempts, validate_stable=validate_stable,
            validate_current=validate_current,
            label="AuditPlan obligation %s batch-page review" %
                  obligation["obligation_id"])
    except evidence_attempt_runtime.EvidenceAttemptError as exc:
        raise audit_producer_runtime.AuditProducerError(str(exc)) from exc


def _require_no_current_attempt(result, item, plan, plan_sha256, obligation,
                                spec, page_snapshot, registry):
    existing = current_review_attempt(
        result, item, plan, plan_sha256, obligation, spec, page_snapshot,
        registry)
    if existing is not None:
        raise audit_producer_runtime.AuditProducerError(
            "batch-page obligation already has current evidence: %s" %
            existing["receipt_id"])


def build_review_receipt(*, root, plan, plan_sha256, obligation, spec,
                         page_snapshot, reviewer_context_id, reviewer_role,
                         verdict, statement, consumed_records=(),
                         applicability_disposition=None,
                         applicability_reason=None,
                         selection=None, registry=None, identity=None, seq=1):
    """Build one closed record from evidence-time page/dependency bytes."""
    registry = (batch_contract.load_registry(root, cache_projection=True)
                if registry is None else registry)
    reviewer_context_id = audit_producer_runtime.require_nonempty_string(
        reviewer_context_id, "reviewer context ID")
    reviewer_role = audit_producer_runtime.require_nonempty_string(
        reviewer_role, "reviewer role")
    statement = audit_producer_runtime.require_nonempty_string(
        statement, "review statement")
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
    sources_digest = audit_fingerprint.sources_sha256(text)
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
        receipt_type_id=batch_contract.RECEIPT_TYPE_ID,
        root=root, identity=identity)
    receipt.update({
        "schema_version": registry["schema_version"],
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
        "upstream_revision_id": plan["upstream_revision_id"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "tier": spec["tier"],
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
            "covered_obligation_ids": list(batch_contract.covered_obligation_ids(
                plan, spec, page_snapshot.path, disposition["applicability_disposition"],
                verdict, registry)),
        })
    else:
        if selection is None:
            raise audit_producer_runtime.AuditProducerError(
                "sampled S evidence requires the frozen selection")
        receipt.update({
        "partition": obligation["partition"],
        "due_stage": spec["due_stage"],
        "evidence_role": spec["evidence_role"],
        "evidence_kind": spec["evidence_kind"],
        "dimension": spec["dimension"],
        "acceptance_predicate": spec["acceptance_predicate"],
        "producer_capability": spec["producer_capability"],
        "consumer_gate_id": spec["consumer_gate_id"],
        "fingerprint_binding": spec["fingerprint_binding"],
        })
        receipt.update(selection)
        receipt["selection_frozen_at"] = plan["generated_at"]
    batch_contract.validate_producer_receipt(receipt, registry)
    batch_contract.validate_record_plan_binding(receipt, plan, plan_sha256, obligation, registry)
    batch_contract.validate_input_binding(
        receipt, page_snapshot.path, text,
        page_snapshot.semantic_content_fingerprint,
        consumed_records=consumed_records)
    return receipt


def require_exact_readback(receipt_absolute, receipt, registry, *, observation=None):
    """Prove resulting append-only state contains one exact valid record."""
    persisted = [
        row for row in audit_producer_runtime.read_receipt_records(
            receipt_absolute, observation=observation)
        if row.get("receipt_id") == receipt["receipt_id"]]
    if len(persisted) != 1 or persisted[0] != receipt:
        raise audit_producer_runtime.AuditProducerError(
            "published batch-page review receipt did not read back exactly")
    batch_contract.validate_producer_receipt(persisted[0], registry)
    return persisted[0]


def main(argv=None):
    import json
    from Tools.execution.task_runtime.task_runtime_action import page_review_answers
    parser = kblib.ArgumentParser(
        description="Record explicit same-page M/S answers with independent publications")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--review", dest="reviews", action="append", required=True,
                        help="one JSON {obligation_id, input} row from the existing reviews collection")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    outcomes = []
    remaining = {}
    try:
        remaining = page_review_answers([json.loads(value) for value in args.reviews])
        root, initial, authority = audit_producer_runtime.admitted_runtime(args.root)
        item, _activation = audit_producer_runtime.open_batch(initial, args.batch)
        (_absolute, plan, plan_sha256, frozen, tiers, registry,
         closure, plan_snapshot) = load_current_plan(root, args.plan, initial, item)
        page_snapshot = audit_producer_runtime.frozen_manifest_page(frozen, args.page)
        if page_snapshot is None:
            raise audit_producer_runtime.AuditProducerError("page is not a frozen manifest member")
        definitions = {row["obligation_id"]: row for row in plan["obligations"]}
        registry_digest = batch_contract.registry_sha256(registry)
        receipt_absolute = audit_producer_runtime.managed_receipt_path(root, DEFAULT_RECEIPTS)
        # Existing condition dependencies, not a second lifecycle scheduler.
        # Independent supplied answers stay in input order; their prerequisite
        # is delivered first if it is also present in this same collection.
        ordered = sorted(remaining, key=lambda identity: len(
            batch_contract.consumption_dependency_obligation_ids(
                plan["obligations"], definitions[identity], registry))
            if identity in definitions else 0)
    except (OSError, TypeError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        reporting.write_canonical_json([reporting.publication_result(
            kblib.ReceiptPublication(), status="invalid", errors=[str(exc)],
            remaining_input_ids=sorted(remaining))])
        return 1

    covered = set()
    for sequence, obligation_id in enumerate(ordered, 1):
        if obligation_id in covered:
            # The input was not executed or converted into another claim.
            # Its original obligation is already covered by the common fact.
            continue
        supplied = remaining.pop(obligation_id)
        publication = kblib.ReceiptPublication()
        receipt = None
        try:
            row = definitions.get(obligation_id)
            if row is None:
                raise ValueError("review names an obligation outside the frozen plan")
            obligation, spec = _required_obligation(
                plan, obligation_id, args.page, tiers[args.page], registry)
            input_shape = batch_contract.review_input_shape(registry)["items"]["properties"]["input"]
            allowed = input_shape["properties"]
            if set(supplied) - set(allowed):
                raise ValueError("review answer has unregistered fields")
            required = set(input_shape["required"])
            if not required.issubset(supplied):
                raise ValueError("review answer is missing required semantic inputs")
            dependencies = batch_contract.consumption_dependency_obligation_ids(
                plan["obligations"], obligation, registry)
            if dependencies:
                supplied.setdefault("applicability_disposition", "applicable")
            constraints = batch_contract.review_input_constraints(plan["obligations"], obligation, registry)
            batch_contract.validate_review_input(
                constraints, supplied.get("applicability_disposition"),
                supplied.get("applicability_reason"), registry)

            def prepare(current):
                current_item, _ = audit_producer_runtime.open_batch(current, args.batch)
                consumed = _current_consumed_records(
                    current, current_item, None, plan=plan, plan_sha256=plan_sha256,
                    obligation=obligation, spec=spec, page=args.page,
                    disposition=supplied.get("applicability_disposition"), registry=registry)
                _require_no_current_attempt(
                    current, current_item, plan, plan_sha256, obligation, spec, page_snapshot, registry)
                return build_review_receipt(
                    root=root, plan=plan, plan_sha256=plan_sha256, obligation=obligation, spec=spec,
                    page_snapshot=page_snapshot, consumed_records=consumed, registry=registry,
                    selection=closure["s_selection"] if spec["tier"] == "S" else None,
                    seq=sequence, **supplied)

            if args.apply:
                pending = []
                operation = audit_producer_runtime.runtime_lock_metadata(
                    TOOL, "record-batch-page-review", initial, authority,
                    batch_id=args.batch, plan_id=plan["plan_id"], obligation_id=obligation_id)

                def verify():
                    require_exact_readback(receipt_absolute, pending[0], registry,
                                           observation=publication.observation)
                    publication.confirmed = True

                with publication.locked_append(
                        root, receipt_absolute, pending, operation=operation,
                        label="record_batch_page_review publication", verify=verify):
                    locked = audit_producer_runtime.require_runtime_current(
                        root, authority, "before batch-page review publication")
                    locked_item, _ = audit_producer_runtime.open_batch(locked, args.batch)
                    (_, locked_plan, locked_digest, _) = _resolve_current_plan(
                        root, args.plan, locked, locked_item)
                    if locked_plan != plan or locked_digest != plan_sha256:
                        raise ValueError("resolved AuditPlan changed before evidence publication")
                    _require_plan_bytes_current(root, args.plan, plan_snapshot)
                    if (_coverage_tiers(locked, locked_item["manifest"]) != tiers or
                            locked_item["manifest"] != item["manifest"]):
                        raise ValueError("frozen review population or tiers changed")
                    current_registry = batch_contract.load_registry(root, cache_projection=True)
                    if batch_contract.registry_sha256(current_registry) != registry_digest:
                        raise ValueError("batch-review registry changed before publication")
                    audit_producer_runtime.require_pages_current(
                        root, (page_snapshot,), "before batch-page review publication")
                    # All candidate construction is read-only under the same
                    # currentness boundary. The original writer appends only
                    # this item after validation, then performs exact read-back.
                    receipt = prepare(locked)
                    pending.append(receipt)
            else:
                receipt = prepare(initial)
            outcomes.append(reporting.publication_result(
                publication, status="recorded" if args.apply else "planned",
                result=receipt["result"], receipt_id=receipt["receipt_id"],
                obligation_id=obligation_id, receipt_path=DEFAULT_RECEIPTS,
                review_variant=receipt["review_variant"]))
            if args.apply:
                covered.update(receipt.get("covered_obligation_ids") or ())
            if receipt["result"] != "pass":
                outcomes[-1]["remaining_input_ids"] = sorted(remaining)
                reporting.write_canonical_json(outcomes)
                return 1
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.RuntimeStateLockedError, kblib.YamlSubsetError) as exc:
            outcomes.append(reporting.publication_result(
                publication, status="invalid", errors=[str(exc)],
                obligation_id=obligation_id, remaining_input_ids=sorted(remaining)))
            reporting.write_canonical_json(outcomes)
            return 1
    outcomes[-1]["remaining_input_ids"] = sorted(remaining)
    reporting.write_canonical_json(outcomes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
