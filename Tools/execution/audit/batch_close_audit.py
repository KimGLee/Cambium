"""Pure K12/09 post-Delta AuditPlan and evidence-set bindings.

The batch-close command owns execution and publication.  This module performs
only deterministic projection, full AuditReceipt construction, and closure
validation over objects already supplied by that command.  It never scans for
an AuditPlan, reads a registry, runs a checker, or writes evidence.
"""

import hashlib

import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.audit.audit_receipt_finalizer as audit_receipt_finalizer
import Tools.platform.common.kblib as kblib


class PostDeltaAuditError(ValueError):
    """The K12/09 post-Delta plan or its evidence set is incomplete."""


_SHA256_PREFIX = "sha256:"
_BINDING_FIELDS = {
    "member_id", "rule_id", "obligation_id", "audit_plan_id",
    "audit_plan_path", "audit_plan_sha256", "merged_snapshot_sha256",
    "evidence_ref", "evidence_role", "evidence_kind", "dimension",
}


def _nonempty(value, label):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise PostDeltaAuditError("%s must be a non-empty string" % label)
    return value


def _sha256(value, label):
    _nonempty(value, label)
    if (not value.startswith(_SHA256_PREFIX) or len(value) != 71 or
            any(character not in "0123456789abcdef" for character in value[7:])):
        raise PostDeltaAuditError("%s must be sha256:<64 lowercase hex>" % label)
    return value


def _profile_registered_dimension(selected_profile_contract):
    scan = getattr(selected_profile_contract, "required_scan", None)
    if scan is None:
        raise PostDeltaAuditError(
            "selected Profile has no unique K12/09 item 6 registration")
    judgment_id = getattr(scan, "judgment_item_id", None)
    matches = [
        item for item in
        getattr(selected_profile_contract, "judgment_items", ())
        if getattr(item, "judgment_item_id", None) == judgment_id
    ]
    if len(matches) != 1:
        raise PostDeltaAuditError(
            "K12/09 item 6 registration must resolve exactly one Judgment "
            "Item, found %d" % len(matches))
    dimension = getattr(matches[0], "dimension_id", None)
    _nonempty(dimension, "K12/09 item 6 Profile dimension")
    if getattr(matches[0], "evidence_role", None) != "emits":
        raise PostDeltaAuditError(
            "K12/09 item 6 Profile Judgment Item must emit evidence")
    return dimension


def resolve_post_delta_projection(stage_plan, registry_rows,
                                  selected_profile_contract):
    """Match the immutable stage plan exactly to the ordered K12/09 registry."""
    if not isinstance(stage_plan, dict):
        raise PostDeltaAuditError("stage plan resolution must be a mapping")
    plan = stage_plan.get("plan")
    if not isinstance(plan, dict):
        raise PostDeltaAuditError("stage plan resolution has no raw AuditPlan")
    plan_id = _nonempty(stage_plan.get("audit_plan_id"), "AuditPlan ID")
    _nonempty(stage_plan.get("audit_plan_path"), "AuditPlan path")
    _sha256(stage_plan.get("audit_plan_sha256"), "AuditPlan hash")
    if plan.get("plan_id") != plan_id:
        raise PostDeltaAuditError("resolved AuditPlan ID differs from raw plan")

    rows = tuple(registry_rows or ())
    obligations = tuple(stage_plan.get("obligations") or ())
    if not rows:
        raise PostDeltaAuditError("K12/09 registry has no members")
    if len(obligations) != len(rows):
        raise PostDeltaAuditError(
            "post-delta-close AuditPlan must contain exactly %d K12/09 "
            "obligations, found %d" % (len(rows), len(obligations)))
    if any(not isinstance(row, dict) for row in rows):
        raise PostDeltaAuditError("K12/09 registry members must be mappings")
    if any(not isinstance(row, dict) for row in obligations):
        raise PostDeltaAuditError(
            "post-delta-close AuditPlan obligations must be mappings")

    obligations_by_rule = {}
    for obligation in obligations:
        rule_id = obligation.get("owner_rule_id")
        if rule_id in obligations_by_rule:
            raise PostDeltaAuditError(
                "post-delta-close AuditPlan repeats owner_rule_id %r" %
                rule_id)
        obligations_by_rule[rule_id] = obligation

    dynamic_dimension = _profile_registered_dimension(
        selected_profile_contract)
    projection = []
    expected_rule_ids = []
    for row in rows:
        member_id = _nonempty(row.get("member_id"), "Closed List member ID")
        rule_id = _nonempty(row.get("rule_id"), "%s rule ID" % member_id)
        expected_rule_ids.append(rule_id)
        obligation = obligations_by_rule.get(rule_id)
        if obligation is None:
            raise PostDeltaAuditError(
                "AuditPlan misses K12/09 member %s (%s)" %
                (member_id, rule_id))
        expected = {
            "owner_kind": "kernel",
            "kernel_extension_point": None,
            "partition": "mandatory-full-deterministic",
            "due_stage": row.get("due_stage"),
            "evidence_role": row.get("evidence_role"),
            "evidence_kind": row.get("evidence_kind"),
            "producer_check": row.get("producer_check"),
            "producer_capability": row.get("producer_capability"),
            "producer_gate_id": row.get("producer_gate_id"),
            "consumer_gate_id": row.get("consumer_gate_id"),
            "fingerprint_binding": "evidence-time",
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        mismatches = [field for field, value in expected.items()
                      if obligation.get(field) != value]
        binding = row.get("dimension_binding")
        if binding == "fixed":
            expected_dimension = row.get("dimension")
        elif binding == "profile-registration":
            expected_dimension = dynamic_dimension
        elif binding == "dimensionless-gate":
            expected_dimension = None
        else:
            raise PostDeltaAuditError(
                "K12/09 member %s has unknown dimension binding %r" %
                (member_id, binding))
        if obligation.get("dimension") != expected_dimension:
            mismatches.append("dimension")
        if mismatches:
            raise PostDeltaAuditError(
                "AuditPlan obligation for %s differs from the K12/09 "
                "registry in: %s" %
                (member_id, ", ".join(sorted(set(mismatches)))))
        _nonempty(obligation.get("obligation_id"),
                  "%s obligation ID" % member_id)
        _nonempty(obligation.get("target"), "%s target" % member_id)
        _nonempty(obligation.get("acceptance_predicate"),
                  "%s acceptance predicate" % member_id)
        projection.append({"member": dict(row),
                           "obligation": dict(obligation)})

    if set(obligations_by_rule) != set(expected_rule_ids):
        extras = sorted(set(obligations_by_rule) - set(expected_rule_ids))
        raise PostDeltaAuditError(
            "post-delta-close AuditPlan contains non-K12/09 obligations: %s" %
            ", ".join(str(value) for value in extras))
    return tuple(projection)


def build_full_audit_receipt(stage_plan, pair, producer_evidence):
    """Complete one emitting K12/09 member inside the close producer."""
    if not isinstance(pair, dict):
        raise PostDeltaAuditError("post-Delta projection pair must be a mapping")
    row = pair.get("member") or {}
    obligation = pair.get("obligation") or {}
    if row.get("evidence_kind") != "audit-receipt":
        raise PostDeltaAuditError(
            "only an audit-receipt member may be completed as AuditReceipt")
    if not isinstance(producer_evidence, dict):
        raise PostDeltaAuditError("producer evidence must be a mapping")
    plan = stage_plan["plan"]
    expected = {
        "check": obligation.get("producer_check"),
        "target": obligation.get("target"),
        "plan_id": stage_plan.get("audit_plan_id"),
        "audit_plan_path": stage_plan.get("audit_plan_path"),
        "audit_plan_sha256": stage_plan.get("audit_plan_sha256"),
        "obligation_id": obligation.get("obligation_id"),
        "task_id": plan.get("task_id"),
        "batch_id": plan.get("batch_id"),
        "opening_transition_receipt": plan.get("opening_transition_receipt"),
        "upstream_revision_id": plan.get("upstream_revision_id"),
        "active_standards_sha256": plan.get("active_standards_sha256"),
        "selected_profile_manifest": plan.get("selected_profile_manifest"),
        "profile_snapshot_sha256": plan.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint":
            plan.get("profile_contract_fingerprint"),
        "fingerprint_binding": obligation.get("fingerprint_binding"),
        "result": "pass",
        "invalidated_by": None,
    }
    mismatches = [field for field, value in expected.items()
                  if producer_evidence.get(field) != value]
    for field in ("artifact_fingerprint", "dependency_fingerprint",
                  "contract_fingerprint"):
        try:
            _sha256(producer_evidence.get(field),
                    "producer evidence %s" % field)
        except PostDeltaAuditError:
            mismatches.append(field)
    if mismatches:
        raise PostDeltaAuditError(
            "producer evidence for %s differs from its AuditPlan binding in: "
            "%s" % (row.get("member_id"),
                     ", ".join(sorted(set(mismatches)))))
    for field in ("receipt_id", "tool", "tool_version", "checked_at"):
        _nonempty(producer_evidence.get(field),
                  "producer evidence %s" % field)

    receipt_seed = kblib.canonical_json_bytes({
        "plan_id": stage_plan["audit_plan_id"],
        "obligation_id": obligation["obligation_id"],
        "evidence_ref": producer_evidence["receipt_id"],
    })
    receipt_id = "audit-check_batch_close-%s" % hashlib.sha256(
        receipt_seed).hexdigest()
    try:
        receipt = audit_receipt_finalizer.finalize_audit_receipt_record(
            receipt_id=receipt_id,
            scope=[obligation["target"]],
            plan=plan,
            plan_sha256=stage_plan["audit_plan_sha256"],
            obligation=obligation,
            evidence=producer_evidence,
        )
    except (TypeError, ValueError) as exc:
        raise PostDeltaAuditError(
            "constructed full AuditReceipt is invalid: %s" % exc) from exc
    return receipt


def _validate_full_audit_receipt_pair(
        stage_plan, pair, receipt, producer_evidence, *,
        producer_tool=None, producer_tool_version=None,
        merged_snapshot_sha256=None):
    """Validate one persisted post-Delta finalizer/precursor pair.

    Construction and terminal replay intentionally share the exact same
    deterministic projection.  Rebuilding the expected AuditReceipt from the
    persisted raw evidence proves both that the precursor still satisfies the
    frozen plan and that no field of the final wrapper was rewritten, omitted,
    or rebound after production.
    """
    if not isinstance(receipt, dict):
        raise PostDeltaAuditError("full AuditReceipt must be a mapping")
    if not isinstance(producer_evidence, dict):
        raise PostDeltaAuditError("persisted producer evidence is unavailable")
    row = pair.get("member") or {}
    obligation = pair.get("obligation") or {}
    precursor_mismatches = []
    precursor_expected = {
        "receipt_id": receipt.get("evidence_ref"),
        "check": row.get("producer_check"),
        "plan_id": stage_plan.get("audit_plan_id"),
        "audit_plan_path": stage_plan.get("audit_plan_path"),
        "audit_plan_sha256": stage_plan.get("audit_plan_sha256"),
        "obligation_id": obligation.get("obligation_id"),
        "task_id": receipt.get("task_id"),
        "batch_id": receipt.get("batch_id"),
        "opening_transition_receipt":
            receipt.get("opening_transition_receipt"),
        "upstream_revision_id": receipt.get("upstream_revision_id"),
        "active_standards_sha256":
            receipt.get("active_standards_sha256"),
        "selected_profile_manifest":
            receipt.get("selected_profile_manifest"),
        "profile_snapshot_sha256":
            receipt.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint":
            receipt.get("profile_contract_fingerprint"),
        "fingerprint_binding": receipt.get("fingerprint_binding"),
        "artifact_fingerprint": receipt.get("artifact_fingerprint"),
        "dependency_fingerprint": receipt.get("dependency_fingerprint"),
        "contract_fingerprint": receipt.get("contract_fingerprint"),
        "result": "pass",
        "invalidated_by": None,
    }
    precursor_mismatches.extend(
        "evidence_ref" if field == "receipt_id" else field
        for field, value in precursor_expected.items()
        if producer_evidence.get(field) != value)
    if (producer_tool is not None and
            producer_evidence.get("tool") != producer_tool):
        precursor_mismatches.append("tool")
    if (producer_tool_version is not None and
            producer_evidence.get("tool_version") != producer_tool_version):
        precursor_mismatches.append("tool_version")
    if (merged_snapshot_sha256 is not None and
            producer_evidence.get("merged_snapshot_sha256") !=
            merged_snapshot_sha256):
        precursor_mismatches.append("merged_snapshot_sha256")
    if receipt.get("scope") != [producer_evidence.get("target")]:
        precursor_mismatches.append("target/scope")
    if receipt.get("verifier") != producer_evidence.get("tool"):
        precursor_mismatches.append("verifier")
    method = "%s@%s/%s" % (
        producer_evidence.get("tool"),
        producer_evidence.get("tool_version"),
        producer_evidence.get("check"))
    if receipt.get("method") != method:
        precursor_mismatches.append("method")
    if receipt.get("checked_at") != producer_evidence.get("checked_at"):
        precursor_mismatches.append("checked_at")
    if precursor_mismatches:
        raise PostDeltaAuditError(
            "persisted producer evidence differs from its close producer "
            "in: %s" % ", ".join(precursor_mismatches))
    # A current close admission carries the immutable raw plan and therefore
    # replays the sole deterministic finalizer byte-for-byte. The lower-level
    # receipt-graph validator may omit that plan; the current transition
    # consumer always supplies it through ``closed_plan_closure_errors``.
    if isinstance(stage_plan.get("plan"), dict):
        expected = build_full_audit_receipt(
            stage_plan, pair, producer_evidence)
        if receipt != expected:
            fields = sorted({
                field for field in set(receipt) | set(expected)
                if receipt.get(field) != expected.get(field)
            })
            raise PostDeltaAuditError(
                "full AuditReceipt differs from its persisted producer "
                "evidence in: %s" % ", ".join(fields))
    return receipt


def _binding_entry(stage_plan, pair, evidence, snapshot):
    row = pair["member"]
    obligation = pair["obligation"]
    return {
        "member_id": row["member_id"],
        "rule_id": row["rule_id"],
        "obligation_id": obligation["obligation_id"],
        "audit_plan_id": stage_plan["audit_plan_id"],
        "audit_plan_path": stage_plan["audit_plan_path"],
        "audit_plan_sha256": stage_plan["audit_plan_sha256"],
        "merged_snapshot_sha256": snapshot,
        "evidence_ref": evidence["receipt_id"],
        "evidence_role": row["evidence_role"],
        "evidence_kind": row["evidence_kind"],
        "dimension": obligation["dimension"],
    }


def validate_post_delta_evidence_set(
        stage_plan, projection, bindings, evidence_by_id,
        merged_snapshot_sha256, *, producer_evidence_by_member=None,
        producer_tool=None, producer_tool_version=None):
    """Validate the registry's exact ordered heterogeneous evidence set."""
    snapshot = _sha256(
        merged_snapshot_sha256, "merged repository snapshot")
    pairs = tuple(projection or ())
    entries = tuple(bindings or ())
    if len(entries) != len(pairs):
        raise PostDeltaAuditError(
            "post-Delta evidence set must contain every registry member: "
            "expected %d, found %d" % (len(pairs), len(entries)))
    if not isinstance(evidence_by_id, dict):
        raise PostDeltaAuditError("evidence catalog must be a mapping")
    producer_rows = producer_evidence_by_member
    if producer_rows is not None:
        expected_members = {
            pair["member"]["member_id"] for pair in pairs
        }
        if (not isinstance(producer_rows, dict) or
                set(producer_rows) != expected_members):
            raise PostDeltaAuditError(
                "producer evidence members must equal the post-Delta "
                "registry")
    seen_refs = []
    seen_producer_refs = []
    for index, (pair, entry) in enumerate(zip(pairs, entries)):
        if not isinstance(entry, dict) or set(entry) != _BINDING_FIELDS:
            raise PostDeltaAuditError(
                "post-Delta evidence binding %d fields are not closed" %
                (index + 1))
        row = pair["member"]
        obligation = pair["obligation"]
        expected = {
            "member_id": row["member_id"],
            "rule_id": row["rule_id"],
            "obligation_id": obligation["obligation_id"],
            "audit_plan_id": stage_plan["audit_plan_id"],
            "audit_plan_path": stage_plan["audit_plan_path"],
            "audit_plan_sha256": stage_plan["audit_plan_sha256"],
            "merged_snapshot_sha256": snapshot,
            "evidence_role": row["evidence_role"],
            "evidence_kind": row["evidence_kind"],
            "dimension": obligation["dimension"],
        }
        mismatches = [field for field, value in expected.items()
                      if entry.get(field) != value]
        evidence_ref = entry.get("evidence_ref")
        evidence = evidence_by_id.get(evidence_ref)
        if not isinstance(evidence, dict) or evidence.get(
                "receipt_id") != evidence_ref:
            mismatches.append("evidence_ref")
        elif row["evidence_kind"] == "audit-receipt":
            try:
                audit_receipt_contract.validate_audit_receipt(evidence)
            except (TypeError, ValueError) as exc:
                raise PostDeltaAuditError(
                    "%s full AuditReceipt is invalid: %s" %
                    (row["member_id"], exc)) from exc
            receipt_expected = {
                "plan_id": stage_plan["audit_plan_id"],
                "audit_plan_sha256": stage_plan["audit_plan_sha256"],
                "obligation_id": obligation["obligation_id"],
                "owner_rule_id": row["rule_id"],
                "due_stage": "post-delta-close",
                "evidence_role": "emits",
                "evidence_kind": "audit-receipt",
                "dimension": obligation["dimension"],
                "consumer_gate_id": "batch-close",
                "artifact_fingerprint": snapshot,
                "result": "passed",
                "invalidated_by": None,
            }
            mismatches.extend(
                "evidence.%s" % field
                for field, value in receipt_expected.items()
                if evidence.get(field) != value)
            if producer_rows is not None:
                producer_evidence = producer_rows.get(row["member_id"])
                if not isinstance(producer_evidence, dict):
                    mismatches.append("producer_evidence")
                else:
                    try:
                        _validate_full_audit_receipt_pair(
                            stage_plan, pair, evidence, producer_evidence,
                            producer_tool=producer_tool,
                            producer_tool_version=producer_tool_version,
                            merged_snapshot_sha256=snapshot)
                    except PostDeltaAuditError as exc:
                        raise PostDeltaAuditError(
                            "%s producer/final evidence pair is invalid: %s" %
                            (row["member_id"], exc)) from exc
                    seen_producer_refs.append(
                        producer_evidence.get("receipt_id"))
        else:
            gate_expected = {
                "gate_id": row.get("producer_gate_id"),
                "check": row["producer_check"],
                "invalidated_by": None,
            }
            mismatches.extend(
                "evidence.%s" % field
                for field, value in gate_expected.items()
                if evidence.get(field) != value)
            if evidence.get("result") not in ("pass", "candidate"):
                mismatches.append("evidence.result")
            if evidence.get("dimension") is not None:
                mismatches.append("evidence.dimension")
            if entry.get("dimension") is not None:
                mismatches.append("dimension")
            if producer_rows is not None:
                producer_evidence = producer_rows.get(row["member_id"])
                if producer_evidence != evidence:
                    mismatches.append("producer_evidence")
                else:
                    seen_producer_refs.append(evidence_ref)
        if mismatches:
            raise PostDeltaAuditError(
                "post-Delta evidence for %s differs in: %s" %
                (row["member_id"], ", ".join(sorted(set(mismatches)))))
        seen_refs.append(evidence_ref)
    if len(seen_refs) != len(set(seen_refs)):
        raise PostDeltaAuditError(
            "post-Delta evidence set repeats an evidence receipt")
    if producer_rows is not None and \
            len(seen_producer_refs) != len(set(seen_producer_refs)):
        raise PostDeltaAuditError(
            "post-Delta evidence set repeats producer evidence")
    evidence_set_sha256 = kblib.sha256_bytes(
        kblib.canonical_json_bytes(list(entries)))
    return {
        "bindings": list(entries),
        "evidence_set_sha256": evidence_set_sha256,
    }


def build_post_delta_evidence_set(stage_plan, projection,
                                  evidence_by_member,
                                  merged_snapshot_sha256):
    """Build and validate the complete ordered post-Delta evidence closure."""
    pairs = tuple(projection or ())
    if not isinstance(evidence_by_member, dict):
        raise PostDeltaAuditError("member evidence must be a mapping")
    member_ids = [pair["member"]["member_id"] for pair in pairs]
    if set(evidence_by_member) != set(member_ids):
        missing = sorted(set(member_ids) - set(evidence_by_member))
        extra = sorted(set(evidence_by_member) - set(member_ids))
        raise PostDeltaAuditError(
            "post-Delta member evidence is incomplete: missing=%s extra=%s" %
            (missing, extra))
    entries = []
    evidence_by_id = {}
    for pair in pairs:
        member_id = pair["member"]["member_id"]
        evidence = evidence_by_member[member_id]
        if not isinstance(evidence, dict):
            raise PostDeltaAuditError(
                "%s evidence must be a mapping" % member_id)
        receipt_id = evidence.get("receipt_id")
        _nonempty(receipt_id, "%s evidence receipt ID" % member_id)
        if receipt_id in evidence_by_id:
            raise PostDeltaAuditError(
                "post-Delta member evidence repeats receipt %s" % receipt_id)
        evidence_by_id[receipt_id] = evidence
        entries.append(_binding_entry(
            stage_plan, pair, evidence, merged_snapshot_sha256))
    return validate_post_delta_evidence_set(
        stage_plan, pairs, entries, evidence_by_id,
        merged_snapshot_sha256)


__all__ = [
    'build_full_audit_receipt',
    'build_post_delta_evidence_set',
    'resolve_post_delta_projection',
    'validate_post_delta_evidence_set',
]
