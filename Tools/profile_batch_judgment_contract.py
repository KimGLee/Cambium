"""Shared machine contract for Profile Batch Review judgments.

The selected Profile's typed ``Batch Review Requirements`` closure is the
only source of these obligations.  This module does not add a Kernel base
obligation: it joins one already-authorized Profile requirement to the one
``k12-14-batch-review-requirement`` row frozen in an AuditPlan, and validates
the resulting evidence record for every producer and consumer.
"""

import os

import audit_fingerprint
import audit_plan_contract
import kblib
import metadata_property_state
import profile_contract
import runtime_paths


RECORD_KIND = "page-batch-judgment-v1"
EXTENSION_POINT = "k12-14-batch-review-requirement"
PARTITION = "profile-registered-review"
DUE_STAGE = "pre-merge"
PRODUCER_TOOL = "record_batch_judgment"
PRODUCER_TOOL_VERSION = "2.0.0"
PRODUCER_CHECK = "profile_batch_judgment"
CONSUMER_GATE_ID = "batch-review"
FINGERPRINT_BINDING = "evidence-time"


_PLAN_BINDING_FIELDS = (
    "task_id", "batch_id", "opening_transition_receipt",
    "standards_version", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint",
)


def _nonempty(value, label):
    if (not isinstance(value, str) or not value or
            value.strip() != value):
        raise ValueError("%s must be a non-empty trimmed string" % label)
    return value


def requirement(contract, judgment_item_id):
    """Return the unique typed requirement for one Judgment Item."""
    rows = [row for row in getattr(contract, "batch_review_requirements", ())
            if row.judgment_item_id == judgment_item_id]
    if len(rows) != 1:
        raise ValueError(
            "Judgment Item %r must resolve to exactly one selected Profile "
            "Batch Review Requirement; found %d" %
            (judgment_item_id, len(rows)))
    return rows[0]


def judgment_item(contract, judgment_item_id):
    """Return the unique typed Judgment Item referenced by a requirement."""
    rows = [row for row in getattr(contract, "judgment_items", ())
            if row.judgment_item_id == judgment_item_id]
    if len(rows) != 1:
        raise ValueError(
            "Judgment Item %r must resolve exactly once in the selected "
            "Profile; found %d" % (judgment_item_id, len(rows)))
    return rows[0]


def expand_requirements(contract, item):
    """Expand the typed requirements over one frozen Queue manifest.

    This is the single expansion used at activation, AuditPlan evidence
    production, and transition consumption.  It intentionally supports only
    the closed selectors already admitted by the Profile interface.
    """
    batch_id = item.get("id") if isinstance(item, dict) else None
    _nonempty(batch_id, "review expansion batch id")
    if contract is None or not getattr(contract, "authorized", False):
        raise ValueError(
            "review expansion requires one authorized typed Profile contract")
    manifest = item.get("manifest")
    if (not isinstance(manifest, list) or
            any(not isinstance(page, str) or not page for page in manifest)):
        raise ValueError("review expansion manifest must be a string list")
    records = []
    for row in getattr(contract, "batch_review_requirements", ()):
        if row.target_selector == "each-manifest-page":
            targets = sorted(set(manifest))
        elif row.target_selector == "batch":
            targets = [batch_id]
        else:
            raise ValueError(
                "review expansion target selector %r is unsupported" %
                row.target_selector)
        for target in targets:
            records.append({
                "batch_id": batch_id,
                "target": target,
                "judgment_item_id": row.judgment_item_id,
                "target_selector": row.target_selector,
                "trigger": row.trigger,
                "producer_kind": row.producer_kind,
                "receipt_schema": row.receipt_schema,
                "pass_authority_role_id": row.pass_authority_role_id,
            })
    records.sort(key=lambda value: (
        value["judgment_item_id"], value["target"]))
    return records


def requirement_set_sha256(records):
    """Hash only the closed obligation identity of one expansion."""
    identity = [{
        "batch_id": row["batch_id"],
        "target": row["target"],
        "judgment_item_id": row["judgment_item_id"],
    } for row in records]
    return kblib.sha256_bytes(kblib.canonical_json_bytes(identity))


def expected_projection(contract, judgment_item_id):
    """Return the AuditPlan fields admitted by the typed Profile row."""
    required = requirement(contract, judgment_item_id)
    judgment = judgment_item(contract, judgment_item_id)
    capability = profile_contract.PRODUCER_CAPABILITY_BY_KIND.get(
        required.producer_kind)
    if not isinstance(capability, str) or not capability:
        raise ValueError(
            "Batch Review Requirement %s has no registered producer "
            "capability" % judgment_item_id)
    return required, judgment, {
        "owner_kind": "profile-extension",
        "owner_rule_id": judgment_item_id,
        "kernel_extension_point": EXTENSION_POINT,
        "partition": PARTITION,
        "due_stage": DUE_STAGE,
        "applicability": required.trigger,
        "evidence_role": judgment.evidence_role,
        "evidence_kind": required.receipt_schema,
        "dimension": judgment.dimension_id,
        "acceptance_predicate": judgment.judgment_item_id,
        "producer_check": PRODUCER_CHECK,
        "producer_capability": capability,
        "producer_gate_id": None,
        "consumer_gate_id": CONSUMER_GATE_ID,
        "fingerprint_binding": FINGERPRINT_BINDING,
        "review_due": None,
        "status": "required",
        "evidence_ref": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    }


def load_bound_plan(root, relative, plan_id, plan_sha256):
    """Load exactly the immutable plan identity named by a wrapper."""
    if (not isinstance(relative, str) or
            os.path.dirname(relative) != runtime_paths.AUDIT_PLAN_ROOT or
            not relative.endswith(".yaml")):
        raise ValueError(
            "batch-review wrapper AuditPlan path must name one direct YAML "
            "member of %s" % runtime_paths.AUDIT_PLAN_ROOT)
    path = kblib.managed_repository_path(
        root, relative, runtime_paths.AUDIT_PLAN_ROOT,
        suffixes=(".yaml",), must_exist=True)
    snapshot = kblib.repository_target_snapshot(
        root, relative, suffixes=(".yaml",), singly_linked=True)
    text = snapshot.read_text()
    plan = kblib.parse_yaml_subset(text)
    plan_contract = audit_plan_contract.load_contract(root)
    audit_plan_contract.validate_plan(plan, plan_contract)
    if text != kblib.canonical_yaml(plan):
        raise ValueError("batch-review wrapper AuditPlan is not canonical")
    digest = audit_plan_contract.plan_sha256(plan, plan_contract)
    if digest != snapshot.sha256 or digest != kblib.sha256_file(path):
        raise ValueError("batch-review wrapper AuditPlan byte identity drifted")
    if plan.get("plan_id") != plan_id:
        raise ValueError("batch-review wrapper binds a different plan_id")
    if digest != plan_sha256:
        raise ValueError("batch-review wrapper binds a different AuditPlan hash")
    if os.path.basename(relative) != "%s.yaml" % plan_id:
        raise ValueError("batch-review wrapper AuditPlan filename drifted")
    return plan


def resolve_obligation(plan, contract, item, target, judgment_item_id,
                       obligation_id=None):
    """Resolve exactly one authorized Profile obligation from an AuditPlan."""
    expected_records = expand_requirements(contract, item)
    record_matches = [row for row in expected_records
                      if row["target"] == target and
                      row["judgment_item_id"] == judgment_item_id]
    if len(record_matches) != 1:
        raise ValueError(
            "(%s, %s) is not exactly one typed Batch Review Requirement of "
            "batch %s" % (target, judgment_item_id, item.get("id")))
    required, judgment, projection = expected_projection(
        contract, judgment_item_id)
    rows = [row for row in plan.get("obligations") or []
            if isinstance(row, dict) and
            row.get("target") == target and
            row.get("owner_kind") == "profile-extension" and
            row.get("owner_rule_id") == judgment_item_id and
            row.get("kernel_extension_point") == EXTENSION_POINT]
    if len(rows) != 1:
        raise ValueError(
            "AuditPlan must contain exactly one %s obligation for (%s, %s); "
            "found %d" %
            (EXTENSION_POINT, target, judgment_item_id, len(rows)))
    obligation = rows[0]
    if (obligation_id is not None and
            obligation.get("obligation_id") != obligation_id):
        raise ValueError(
            "receipt obligation_id does not identify the unique Profile "
            "Batch Review obligation")
    mismatches = [field for field, value in projection.items()
                  if obligation.get(field) != value]
    if mismatches:
        raise ValueError(
            "AuditPlan Profile judgment obligation differs from the typed "
            "Profile projection in: %s" %
            ", ".join(sorted(mismatches)))
    return obligation, required, judgment, record_matches[0], expected_records


def semantic_content_fingerprint(root, target, profile_view):
    """Return the Profile projection-neutral semantic page identity.

    This is deliberately not the K12/07 artifact fingerprint. It remains a
    separate Profile judgment binding used by the existing page-review
    consumer. Rules come only from the admitted runtime's immutable Profile
    view; this function never reselects or recompiles a Profile from disk.
    """
    _metadata_contract, rules = \
        metadata_property_state.authorized_profile_projection_rules(
            root, profile_view)
    _snapshot, digest = metadata_property_state.semantic_page_snapshot(
        root, target, rules=rules)
    return digest


def _page_text(root, target):
    snapshot = kblib.repository_target_snapshot(
        root, target, suffixes=(".md", ".MD"), singly_linked=True)
    if not snapshot.exists:
        raise ValueError(
            "Profile judgment target is not materialized: %s" % target)
    return snapshot.read_text()


def artifact_fingerprint(root, item, requirement_row, target):
    """Freeze the review target with the sole K12/07 artifact protocol."""
    if requirement_row.target_selector == "each-manifest-page":
        return audit_fingerprint.page_artifact_fingerprint(
            target, _page_text(root, target))
    if requirement_row.target_selector == "batch":
        pages = [(path, _page_text(root, path))
                 for path in sorted(set(item.get("manifest") or []))]
        return audit_fingerprint.page_set_artifact_fingerprint(pages)
    raise ValueError(
        "unsupported Batch Review target selector %r" %
        requirement_row.target_selector)


def contract_fingerprint(plan, obligation, required, judgment):
    """Bind the exact typed Profile acceptance contract for this row."""
    additional = {
        "profile_batch_review_requirement": {
            "judgment_item_id": required.judgment_item_id,
            "target_selector": required.target_selector,
            "trigger": required.trigger,
            "producer_kind": required.producer_kind,
            "receipt_schema": required.receipt_schema,
            "pass_authority_role_id": required.pass_authority_role_id,
        },
        "profile_judgment_item": {
            "judgment_item_id": judgment.judgment_item_id,
            "dimension_id": judgment.dimension_id,
            "audit_layer": judgment.audit_layer,
            "audit_object": judgment.audit_object,
            "evidence_role": judgment.evidence_role,
        },
    }
    return audit_fingerprint.obligation_contract_fingerprint(
        plan, obligation, additional=additional)


def evidence_fingerprints(root, plan, obligation, contract, item, target,
                          judgment_item_id):
    """Resolve all three K12/07 evidence-time fingerprints."""
    obligation, required, judgment, _record, expanded = resolve_obligation(
        plan, contract, item, target, judgment_item_id,
        obligation_id=obligation.get("obligation_id"))
    return {
        "artifact_fingerprint": artifact_fingerprint(
            root, item, required, target),
        "dependency_fingerprint": requirement_set_sha256(expanded),
        "contract_fingerprint": contract_fingerprint(
            plan, obligation, required, judgment),
    }


def receipt_binding_errors(root, plan, plan_sha256, contract, item, receipt,
                           profile_view):
    """Return all differences between one record and its sole plan row."""
    if not isinstance(receipt, dict):
        return ["receipt"]
    errors = []
    try:
        obligation, required, _judgment, _record, expanded = \
            resolve_obligation(
                plan, contract, item, receipt.get("target"),
                receipt.get("judgment_item_id"),
                obligation_id=receipt.get("obligation_id"))
        fingerprints = {
            "artifact_fingerprint": artifact_fingerprint(
                root, item, required, receipt.get("target")),
            "dependency_fingerprint": requirement_set_sha256(expanded),
            "contract_fingerprint": contract_fingerprint(
                plan, obligation, required,
                judgment_item(contract, required.judgment_item_id)),
        }
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        return ["profile/AuditPlan binding: %s" % exc]
    expected = {field: plan[field] for field in _PLAN_BINDING_FIELDS}
    expected.update({
        "schema_version": 1,
        "record_kind": RECORD_KIND,
        "tool": PRODUCER_TOOL,
        "tool_version": PRODUCER_TOOL_VERSION,
        "check": PRODUCER_CHECK,
        "target": obligation["target"],
        "result": "pass",
        "invalidated_by": None,
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        "dimension": obligation["dimension"],
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "judgment_item_id": required.judgment_item_id,
        "target_selector": required.target_selector,
        "trigger": required.trigger,
        "producer_kind": required.producer_kind,
        "receipt_schema": required.receipt_schema,
        "pass_authority_role_id": required.pass_authority_role_id,
        "reviewer_role": required.pass_authority_role_id,
        "activation_receipt_id": item.get("activation_receipt"),
        "review_requirement_set_sha256":
            requirement_set_sha256(expanded),
        "semantic_content_sha256": (
            semantic_content_fingerprint(
                root, obligation["target"], profile_view)
            if required.target_selector == "each-manifest-page"
            else None),
    })
    expected.update(fingerprints)
    errors.extend(field for field, value in expected.items()
                  if receipt.get(field) != value)
    details = receipt.get("details")
    if not isinstance(details, str) or not details.strip():
        errors.append("details")
    return sorted(set(errors))


__all__ = [
    "CONSUMER_GATE_ID", "DUE_STAGE", "EXTENSION_POINT",
    "FINGERPRINT_BINDING", "PARTITION", "PRODUCER_CHECK", "PRODUCER_TOOL",
    "PRODUCER_TOOL_VERSION", "RECORD_KIND",
    "artifact_fingerprint", "contract_fingerprint", "evidence_fingerprints",
    "expand_requirements", "expected_projection", "judgment_item",
    "load_bound_plan",
    "receipt_binding_errors", "requirement", "requirement_set_sha256",
    "resolve_obligation", "semantic_content_fingerprint",
]
