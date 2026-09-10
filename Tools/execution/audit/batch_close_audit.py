"""Pure K12/09 post-Delta AuditPlan and evidence-set bindings.

The batch-close command owns execution and publication.  This module performs
only deterministic projection, first-publication acceptance, and closure
validation over objects already supplied by that command.  It never scans for
an AuditPlan, reads a registry, runs a checker, or writes evidence.
"""

import Tools.execution.audit.batch_close_contract as batch_close_contract
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


def validate_member_evidence(stage_plan, pair, evidence, merged_snapshot_sha256):
    """Accept a check fact directly against its immutable due-stage obligation.

    The first publisher and later close consumers call this same predicate.
    No second full Receipt is generated. The stage owner supplies the raw
    AuditPlan at publication and current/Terminal closure; the lower-level
    stored-reference graph can check the named bindings without selecting a
    plan or reconstructing a synthetic one.
    """
    row, obligation = pair["member"], pair["obligation"]
    if row["evidence_kind"] != "batch-close-member-evidence":
        raise PostDeltaAuditError("member must use its direct evidence kind")
    errors = batch_close_contract.current_receipt_errors(evidence)
    if errors:
        raise PostDeltaAuditError("member evidence body is invalid: %s" % "; ".join(errors))
    snapshot = _sha256(merged_snapshot_sha256, "merged repository snapshot")
    expected = {
        "receipt_type_id": batch_close_contract.MEMBER_RECEIPT_TYPE_ID,
        "check": row["producer_check"],
        "plan_id": stage_plan["audit_plan_id"],
        "audit_plan_path": stage_plan["audit_plan_path"],
        "audit_plan_sha256": stage_plan["audit_plan_sha256"],
        "obligation_id": obligation["obligation_id"],
        "fingerprint_binding": "evidence-time",
        "artifact_fingerprint": snapshot,
        "merged_snapshot_sha256": snapshot,
        "result": "pass", "invalidated_by": None,
    }
    plan = stage_plan.get("plan")
    if isinstance(plan, dict):
        expected.update({field: plan[field] for field in (
            "task_id", "batch_id", "opening_transition_receipt",
            "upstream_revision_id", "active_standards_sha256",
            "selected_profile_manifest", "profile_snapshot_sha256",
            "profile_contract_fingerprint")})
        expected.update(target=obligation["target"],
            dependency_fingerprint=plan["profile_snapshot_sha256"],
            contract_fingerprint=plan["contract_snapshot_sha256"])
    mismatches = [field for field, value in expected.items() if evidence.get(field) != value]
    for field in ("artifact_fingerprint", "dependency_fingerprint", "contract_fingerprint"):
        try:
            _sha256(evidence.get(field), "member evidence %s" % field)
        except PostDeltaAuditError:
            mismatches.append(field)
    if mismatches:
        raise PostDeltaAuditError("member evidence differs from its plan/after-image in: %s" %
                                 ", ".join(sorted(set(mismatches))))
    return evidence


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
        merged_snapshot_sha256):
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
    seen_refs = []
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
        elif row["evidence_kind"] == "batch-close-member-evidence":
            validate_member_evidence(stage_plan, pair, evidence, snapshot)
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
        if mismatches:
            raise PostDeltaAuditError(
                "post-Delta evidence for %s differs in: %s" %
                (row["member_id"], ", ".join(sorted(set(mismatches)))))
        seen_refs.append(evidence_ref)
    if len(seen_refs) != len(set(seen_refs)):
        raise PostDeltaAuditError(
            "post-Delta evidence set repeats an evidence receipt")
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
    'validate_member_evidence',
    'build_post_delta_evidence_set',
    'resolve_post_delta_projection',
    'validate_post_delta_evidence_set',
]
