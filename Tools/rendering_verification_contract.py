"""Strict loader for the Kernel-owned rendering-record shape contract.

The contract validates only the K12/02 and K12/13 escalation record.  A valid
record is not evidence that Level 0 or Level 1 ran, nor that a human or visual
observation was accurate.
"""

import os

import audit_fingerprint
import audit_plan_contract as _support
import kblib


RENDERING_VERIFICATION_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/rendering-verification-contract.yaml")

_CONTRACT_FIELDS = {
    "schema_version", "contract_id", "semantic_owner",
    "semantic_dependencies", "record_kind", "proof_boundary",
    "acceptance_predicate", "obligation_projection", "rendering_modes",
    "fields",
}
_PROJECTION_FIELDS = {
    "owner_kind", "owner_rule_id", "kernel_extension_point",
    "target_source", "applicability", "partition", "due_stage",
    "producer_check", "producer_capability", "producer_gate_id",
    "consumer_gate_id", "evidence_kind", "evidence_role", "dimension",
    "acceptance_predicate", "fingerprint_binding",
}
_MODE_FIELDS = {"rendering_mode", "highest_level", "escalation"}
_FIELD_TYPES = frozenset((
    "integer", "string", "sha256", "utc-timestamp", "string-list",
))
_RECORD_INPUT_FIELDS = (
    "rendering_mode", "highest_level", "visual_trigger",
    "unresolved_question", "verification_target", "verification_result",
)


def _closed_list(value, label):
    return _support.closed_string_list(value, label)


def _validate_projection(projection, acceptance_predicate):
    if not isinstance(projection, dict) or \
            set(projection) != _PROJECTION_FIELDS:
        raise ValueError(
            "rendering-verification obligation_projection fields are not "
            "closed")
    expected = {
        "owner_kind": "kernel",
        "owner_rule_id": "k12-02-rendering-verification-record",
        "kernel_extension_point": None,
        "target_source": "batch",
        "applicability": "every-batch",
        "partition": "changed-scope-deterministic",
        "due_stage": "pre-merge",
        "producer_check": "changed_scope_rendering_escalation_record",
        "producer_capability": "audit-receipt-producer-v1",
        "producer_gate_id": None,
        "consumer_gate_id": "batch-review",
        "evidence_kind": "audit-receipt",
        "evidence_role": "emits",
        "dimension": "rendering",
        "acceptance_predicate": acceptance_predicate,
        "fingerprint_binding": "evidence-time",
    }
    mismatches = [field for field, value in expected.items()
                  if projection.get(field) != value]
    if mismatches:
        raise ValueError(
            "rendering-verification obligation_projection differs in: %s" %
            ", ".join(sorted(mismatches)))
    return projection


def _validate_modes(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("rendering_modes must be a non-empty list")
    actual = {}
    for index, row in enumerate(rows):
        label = "rendering_modes[%d]" % index
        if not isinstance(row, dict) or set(row) != _MODE_FIELDS:
            raise ValueError("%s fields are not closed" % label)
        mode = _support.nonempty_string(
            row.get("rendering_mode"), label + ".rendering_mode")
        level = row.get("highest_level")
        if (not isinstance(level, int) or isinstance(level, bool) or
                level < 0):
            raise ValueError("%s.highest_level must be non-negative" % label)
        escalation = row.get("escalation")
        if not isinstance(escalation, bool):
            raise ValueError("%s.escalation must be boolean" % label)
        if mode in actual:
            raise ValueError("rendering_modes repeats %s" % mode)
        actual[mode] = {"highest_level": level, "escalation": escalation}
    expected = {
        "source-only": {"highest_level": 0, "escalation": False},
        "deterministic-static": {"highest_level": 1, "escalation": False},
        "targeted-visual-exception": {
            "highest_level": 2, "escalation": True},
        "expanded-ui": {"highest_level": 3, "escalation": True},
        "temporal-recording": {"highest_level": 4, "escalation": True},
    }
    if actual != expected:
        raise ValueError("rendering_modes do not match K12/02 levels")
    return actual


def validate_contract(document):
    """Validate the closed Kernel machine contract and return projections."""
    if not isinstance(document, dict) or set(document) != _CONTRACT_FIELDS:
        raise ValueError("rendering-verification contract fields are not closed")
    if document.get("schema_version") != 1:
        raise ValueError("rendering-verification schema_version must be 1")
    if document.get("contract_id") != \
            "cambium-rendering-verification-record":
        raise ValueError("rendering-verification contract_id is invalid")
    if document.get("semantic_owner") != "K12/02":
        raise ValueError(
            "rendering-verification semantic owner must be K12/02")
    dependencies = _closed_list(
        document.get("semantic_dependencies"), "semantic_dependencies")
    if set(dependencies) != {"K12/08", "K12/13"}:
        raise ValueError(
            "rendering-verification semantic dependencies must be "
            "K12/08 and K12/13")
    if document.get("record_kind") != "rendering-verification-evidence":
        raise ValueError("rendering-verification record_kind is invalid")
    if document.get("proof_boundary") != "record-shape-only":
        raise ValueError(
            "rendering-verification must remain a record-shape proof")
    predicate = document.get("acceptance_predicate")
    if predicate != "k12-02-rendering-verification-record":
        raise ValueError(
            "rendering-verification acceptance predicate is invalid")
    projection = _validate_projection(
        document.get("obligation_projection"), predicate)
    modes = _validate_modes(document.get("rendering_modes"))
    field_order, fields = _support.field_specs(
        document.get("fields"), "fields", allowed_types=_FIELD_TYPES)
    required = {
        "schema_version", "record_kind", "receipt_id", "tool",
        "tool_version", "check", "target", "result", "details",
        "checked_at", "invalidated_by", "plan_id", "audit_plan_sha256",
        "obligation_id", "task_id", "batch_id",
        "opening_transition_receipt", "standards_version",
        "active_standards_sha256", "selected_profile_manifest",
        "profile_snapshot_sha256", "profile_contract_fingerprint", "scope",
        "artifact_fingerprint", "dependency_fingerprint",
        "contract_fingerprint", "fingerprint_binding",
        "acceptance_predicate", "dimension", "rendering_mode",
        "highest_level", "visual_trigger", "unresolved_question",
        "verification_target", "verification_result",
    }
    if set(fields) != required:
        raise ValueError(
            "rendering-verification instance fields do not match K12/02")
    return {
        "field_order": field_order,
        "fields": fields,
        "modes": modes,
        "obligation_projection": projection,
    }


def load_contract(root=None, snapshots=None):
    """Load the current Kernel-owned rendering record contract."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    snapshot = (snapshots or {}).get(RENDERING_VERIFICATION_CONTRACT_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        text = kblib.read_text(os.path.join(
            root, *RENDERING_VERIFICATION_CONTRACT_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_contract(document)
    return document


def contract_sha256(contract=None):
    """Return the canonical fingerprint of the machine contract."""
    document = contract or _SHIPPED_CONTRACT
    validate_contract(document)
    return kblib.sha256_bytes(
        kblib.canonical_yaml(document).encode("utf-8"))


def record_dependency_fingerprint(record, contract=None):
    """Fingerprint the exact K12/02 rendering-record evidence input."""
    document = contract or _SHIPPED_CONTRACT
    validate_contract(document)
    if not isinstance(record, dict):
        raise ValueError("rendering-verification record must be a mapping")
    material = {
        "proof_boundary": document["proof_boundary"],
        "rendering_record": {
            field: record.get(field) for field in _RECORD_INPUT_FIELDS
        },
    }
    return kblib.sha256_bytes(kblib.canonical_json_bytes(material))


def validate_record_for_obligation(record, plan, plan_sha256, obligation,
                                   contract=None):
    """Validate the closed record against one immutable AuditPlan row.

    This consumer-safe boundary validates only facts recoverable from the
    immutable plan and record. The publishing producer separately proves the
    live manifest bytes under lock before appending the record.
    """
    document = contract or _SHIPPED_CONTRACT
    validate_record(record, document)
    projection = validate_contract(document)["obligation_projection"]
    expected_obligation = {
        field: projection[field] for field in projection
        if field != "target_source"
    }
    expected_obligation.update({
        "target": plan.get("batch_id"),
        "review_due": None,
        "status": "required",
        "evidence_ref": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    })
    mismatches = [
        "obligation.%s" % field
        for field, value in expected_obligation.items()
        if obligation.get(field) != value
    ]
    expected_record = {
        "plan_id": plan.get("plan_id"),
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation.get("obligation_id"),
        "target": obligation.get("target"),
        "task_id": plan.get("task_id"),
        "batch_id": plan.get("batch_id"),
        "opening_transition_receipt":
            plan.get("opening_transition_receipt"),
        "standards_version": plan.get("standards_version"),
        "active_standards_sha256": plan.get("active_standards_sha256"),
        "selected_profile_manifest":
            plan.get("selected_profile_manifest"),
        "profile_snapshot_sha256": plan.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint":
            plan.get("profile_contract_fingerprint"),
        "fingerprint_binding": obligation.get("fingerprint_binding"),
        "acceptance_predicate": obligation.get("acceptance_predicate"),
        "dimension": obligation.get("dimension"),
    }
    mismatches.extend(
        field for field, value in expected_record.items()
        if record.get(field) != value)
    if record.get("dependency_fingerprint") != \
            record_dependency_fingerprint(record, document):
        mismatches.append("dependency_fingerprint")
    expected_contract = audit_fingerprint.obligation_contract_fingerprint(
        plan, obligation, additional={
            "rendering_verification_contract_sha256":
                contract_sha256(document),
        })
    if record.get("contract_fingerprint") != expected_contract:
        mismatches.append("contract_fingerprint")
    if mismatches:
        raise ValueError(
            "rendering-verification record differs from AuditPlan in: %s" %
            ", ".join(sorted(set(mismatches))))
    return record


def validate_record(record, contract=None):
    """Validate one record-shape evidence object, without judging visuals."""
    contract = contract or _SHIPPED_CONTRACT
    values = validate_contract(contract)
    if not isinstance(record, dict) or set(record) != set(values["fields"]):
        raise ValueError("rendering-verification record fields are not closed")
    for field, spec in values["fields"].items():
        _support.validate_value(
            record.get(field), spec, "rendering-verification.%s" % field)
    fixed = {
        "schema_version": 1,
        "record_kind": contract["record_kind"],
        "tool": "record_rendering_verification",
        "check": contract["obligation_projection"]["producer_check"],
        "result": "pass",
        "invalidated_by": None,
        "fingerprint_binding": "evidence-time",
        "acceptance_predicate": contract["acceptance_predicate"],
        "dimension": "rendering",
    }
    mismatches = [field for field, expected in fixed.items()
                  if record.get(field) != expected]
    scope = record.get("scope")
    if scope != sorted(scope) or len(scope) != len(set(scope)):
        mismatches.append("scope")
    mode = values["modes"].get(record.get("rendering_mode"))
    if mode is None:
        mismatches.append("rendering_mode")
    elif record.get("highest_level") != mode["highest_level"]:
        mismatches.append("highest_level")
    if mode is not None and mode["escalation"]:
        for field in (
                "visual_trigger", "unresolved_question",
                "verification_target", "verification_result"):
            value = record.get(field)
            if (not isinstance(value, str) or not value or
                    value.strip() != value or value == "not_applicable"):
                mismatches.append(field)
    elif mode is not None and record.get("visual_trigger") != \
            "not_applicable":
        mismatches.append("visual_trigger")
    if mismatches:
        raise ValueError(
            "rendering-verification record is invalid in: %s" %
            ", ".join(sorted(set(mismatches))))
    return record


_SHIPPED_CONTRACT = load_contract()
_SHIPPED_VALUES = validate_contract(_SHIPPED_CONTRACT)
RENDERING_MODES = frozenset(_SHIPPED_VALUES["modes"])
RENDERING_VERIFICATION_FIELDS = _SHIPPED_VALUES["field_order"]


__all__ = [
    "RENDERING_MODES", "RENDERING_VERIFICATION_CONTRACT_PATH",
    "RENDERING_VERIFICATION_FIELDS", "contract_sha256", "load_contract",
    "record_dependency_fingerprint", "validate_contract", "validate_record",
    "validate_record_for_obligation",
]
