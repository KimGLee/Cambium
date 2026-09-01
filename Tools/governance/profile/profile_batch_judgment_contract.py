"""Shared machine contract for Profile Batch Review judgments.

The selected Profile's typed ``Batch Review Requirements`` closure is the
only source of these obligations.  This module does not add a Kernel base
obligation: it joins one already-authorized Profile requirement to the one
``k12-14-batch-review-requirement`` row frozen in an AuditPlan, and validates
the resulting evidence record for every producer and consumer.
"""

import os

import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.batch_review_receipt_contract as batch_review_receipt_contract
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.platform.common.kblib as kblib
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.governance.profile.profile_contract as profile_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common.primitives import catalog_record, require_trimmed_string


RECEIPT_TYPE_ID = "page-batch-judgment-v2"
RECORD_KIND = RECEIPT_TYPE_ID
SCHEMA_VERSION = 2
EXTENSION_POINT = "k12-14-batch-review-requirement"
PARTITION = "profile-registered-review"
DUE_STAGE = "pre-merge"
PRODUCER_TOOL = "record_batch_judgment"
PRODUCER_TOOL_VERSION = "2.0.0"
PRODUCER_CHECK = "profile_batch_judgment"
CONSUMER_GATE_ID = batch_review_receipt_contract.GATE_ID
FINGERPRINT_BINDING = "evidence-time"


_PLAN_BINDING_FIELDS = audit_lifecycle_contract.PLAN_BINDING_FIELDS


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
    require_trimmed_string(batch_id, "review expansion batch id")
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
                           profile_view, *, require_current=True):
    """Return stable-contract and, optionally, live-input differences."""
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
            "dependency_fingerprint": requirement_set_sha256(expanded),
            "contract_fingerprint": contract_fingerprint(
                plan, obligation, required,
                judgment_item(contract, required.judgment_item_id)),
        }
        if require_current:
            fingerprints["artifact_fingerprint"] = artifact_fingerprint(
                root, item, required, receipt.get("target"))
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        return ["profile/AuditPlan binding: %s" % exc]
    expected = {field: plan[field] for field in _PLAN_BINDING_FIELDS}
    expected.update({
        "schema_version": SCHEMA_VERSION,
        "record_kind": RECORD_KIND,
        "receipt_type_id": RECEIPT_TYPE_ID,
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
    })
    if required.target_selector == "each-manifest-page":
        if not audit_plan_contract.is_sha256(
                receipt.get("semantic_content_sha256")):
            errors.append("semantic_content_sha256")
        elif require_current:
            try:
                expected["semantic_content_sha256"] = \
                    semantic_content_fingerprint(
                        root, obligation["target"], profile_view)
            except (OSError, TypeError, UnicodeError, ValueError) as exc:
                errors.append("semantic_content_sha256: %s" % exc)
    else:
        expected["semantic_content_sha256"] = None
    if not audit_plan_contract.is_sha256(
            receipt.get("artifact_fingerprint")):
        errors.append("artifact_fingerprint")
    expected.update(fingerprints)
    errors.extend(field for field, value in expected.items()
                  if receipt.get(field) != value)
    details = receipt.get("details")
    if not isinstance(details, str) or not details.strip():
        errors.append("details")
    return sorted(set(errors))


_RECEIPT_FIELDS = frozenset({
    "receipt_id", "receipt_type_id", "check", "target", "result",
    "details", "checked_at", "tool", "tool_version", "invalidated_by",
    "schema_version", "record_kind", "plan_id", "audit_plan_sha256",
    "obligation_id", "task_id", "batch_id", "owner_kind",
    "owner_rule_id", "kernel_extension_point", "partition", "due_stage",
    "evidence_role", "evidence_kind", "dimension",
    "acceptance_predicate", "producer_check", "producer_capability",
    "producer_gate_id", "consumer_gate_id", "fingerprint_binding",
    "judgment_item_id", "target_selector", "trigger", "producer_kind",
    "receipt_schema", "pass_authority_role_id", "reviewer_role",
    "opening_transition_receipt", "activation_receipt_id",
    "review_requirement_set_sha256", "semantic_content_sha256",
    "upstream_revision_id", "active_standards_sha256",
    "selected_profile_manifest", "profile_contract_fingerprint",
    "profile_snapshot_sha256", "artifact_fingerprint",
    "dependency_fingerprint", "contract_fingerprint",
})


def current_receipt_errors(record, *, root=None):
    """Validate the closed current Profile-judgment record envelope.

    Full Profile/AuditPlan currentness remains the responsibility of
    :func:`receipt_binding_errors`; the generic Receipt catalog must not
    recreate that runtime join.
    """
    if not isinstance(record, dict):
        return ["Profile judgment receipt must be an object"]
    errors = []
    if set(record) != _RECEIPT_FIELDS:
        errors.append("Profile judgment receipt fields are not closed")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "record_kind": RECORD_KIND,
        "receipt_type_id": RECEIPT_TYPE_ID,
        "tool": PRODUCER_TOOL,
        "tool_version": PRODUCER_TOOL_VERSION,
        "check": PRODUCER_CHECK,
        "result": "pass",
        "invalidated_by": None,
    }
    errors.extend(field for field, value in expected.items()
                  if record.get(field) != value)
    for field in ("receipt_id", "target", "details", "checked_at"):
        value = record.get(field)
        if not isinstance(value, str) or not value or value.strip() != value:
            errors.append(field)
    return sorted(set(errors))


def current_judgment_attempt(root, plan, plan_sha256, contract, item,
                             profile_view, catalog, target,
                             judgment_item_id):
    """Return the sole live-current attempt for one Profile obligation."""
    if not isinstance(catalog, dict):
        raise ValueError("Profile judgment catalog must be a mapping")
    obligation, _required, _judgment, _record, _expanded = \
        resolve_obligation(
            plan, contract, item, target, judgment_item_id)
    attempts = []
    for catalog_id, entry in catalog.items():
        record = catalog_record(entry)
        if not isinstance(record, dict):
            continue
        if (record.get("receipt_id") == catalog_id and
                record.get("tool") == PRODUCER_TOOL and
                record.get("check") == PRODUCER_CHECK and
                record.get("record_kind") == RECORD_KIND and
                record.get("batch_id") == item.get("id") and
                record.get("activation_receipt_id") ==
                item.get("activation_receipt") and
                record.get("target") == target and
                record.get("judgment_item_id") == judgment_item_id):
            attempts.append(record)

    def validate(record, require_current):
        errors = receipt_binding_errors(
            root, plan, plan_sha256, contract, item, record, profile_view,
            require_current=require_current)
        if errors:
            raise ValueError(", ".join(errors))

    try:
        return evidence_attempt_runtime.unique_current_attempt(
            attempts,
            validate_stable=lambda record: validate(record, False),
            validate_current=lambda record: validate(record, True),
            label="Profile judgment (%s, %s)" %
                  (target, judgment_item_id))
    except evidence_attempt_runtime.EvidenceAttemptError as exc:
        raise ValueError(str(exc)) from exc


def current_judgment_receipts(root, plan, plan_sha256, contract, item,
                              profile_view, catalog):
    """Resolve the complete unique current Profile judgment set."""
    expected = expand_requirements(contract, item)
    expected_keys = sorted(
        (row["target"], row["judgment_item_id"]) for row in expected)
    selected = []
    for target, judgment_item_id in expected_keys:
        record = current_judgment_attempt(
            root, plan, plan_sha256, contract, item, profile_view, catalog,
            target, judgment_item_id)
        if record is None:
            raise ValueError(
                "Profile judgment (%s, %s) needs exactly one current %s, "
                "found 0" %
                (target, judgment_item_id, RECORD_KIND))
        selected.append(record)

    expected_key_set = set(expected_keys)
    for catalog_id, entry in catalog.items():
        record = catalog_record(entry)
        if not isinstance(record, dict) or record.get("receipt_id") != \
                catalog_id:
            continue
        if (record.get("tool") == PRODUCER_TOOL and
                record.get("check") == PRODUCER_CHECK and
                record.get("record_kind") == RECORD_KIND and
                record.get("batch_id") == item.get("id") and
                record.get("activation_receipt_id") ==
                item.get("activation_receipt") and
                (record.get("target"), record.get("judgment_item_id")) not in
                expected_key_set):
            raise ValueError(
                "current activation contains an unexpected Profile judgment "
                "attempt (%s, %s)" %
                (record.get("target"), record.get("judgment_item_id")))
    return tuple(sorted(
        selected,
        key=lambda record: (
            record["judgment_item_id"], record["target"],
            record["receipt_id"])))


__all__ = [
    'DUE_STAGE',
    'EXTENSION_POINT',
    'PRODUCER_CHECK',
    'PRODUCER_TOOL',
    'PRODUCER_TOOL_VERSION',
    'RECEIPT_TYPE_ID',
    'RECORD_KIND',
    'SCHEMA_VERSION',
    'evidence_fingerprints',
    'current_judgment_attempt',
    'current_judgment_receipts',
    'expand_requirements',
    'expected_projection',
    'load_bound_plan',
    'current_receipt_errors',
    'receipt_binding_errors',
    'requirement_set_sha256',
    'resolve_obligation',
    'semantic_content_fingerprint',
]
