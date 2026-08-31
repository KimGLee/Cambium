"""Strict loader for the Kernel-owned rendering-record shape contract.

The contract validates only the K12/02 and K12/13 escalation record.  A valid
record is not evidence that Level 0 or Level 1 ran, nor that a human or visual
observation was accurate.
"""
from Tools.platform.repository.repository import repository_source_root

import os

import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.audit_plan_contract as _support
import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import require_trimmed_string


RENDERING_VERIFICATION_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/rendering-verification-contract.yaml")
RECEIPT_TYPE_ID = "rendering-verification-evidence-v3"
CURRENT_PRODUCER_TOOL = "record_rendering_verification"
CURRENT_PRODUCER_VERSION = "2.0.0"
CURRENT_PRODUCER_CHECK = "changed_scope_rendering_escalation_record"

_CONTRACT_FIELDS = {
    "schema_version", "contract_id", "semantic_owner",
    "semantic_dependencies", "record_kind", "proof_boundary",
    "acceptance_predicate", "rendering_modes", "fields",
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


def _validate_modes(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("rendering_modes must be a non-empty list")
    actual = {}
    for index, row in enumerate(rows):
        label = "rendering_modes[%d]" % index
        if not isinstance(row, dict) or set(row) != _MODE_FIELDS:
            raise ValueError("%s fields are not closed" % label)
        mode = require_trimmed_string(
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
    return actual


def validate_contract(document):
    """Validate the closed Kernel machine contract and return projections."""
    if not isinstance(document, dict) or set(document) != _CONTRACT_FIELDS:
        raise ValueError("rendering-verification contract fields are not closed")
    if document.get("schema_version") != 3:
        raise ValueError("rendering-verification schema_version must be 3")
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
    modes = _validate_modes(document.get("rendering_modes"))
    field_order, fields = _support.field_specs(
        document.get("fields"), "fields", allowed_types=_FIELD_TYPES)
    return {
        "field_order": field_order,
        "fields": fields,
        "modes": modes,
    }


def load_contract(root=None, snapshots=None):
    """Load the current Kernel-owned rendering record contract."""
    if root is None:
        root = repository_source_root(__file__)
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
    """Validate generic plan binding after the chain owner chose this record.

    The changed-scope registry and :mod:`audit_producer_chain` own which
    obligation uses this shape.  This function does not project or select an
    obligation; it compares only the immutable binding and current contract
    fingerprint after a caller has derived the registered chain.
    """
    document = contract or _SHIPPED_CONTRACT
    validate_record(record, document)
    mismatches = audit_lifecycle_contract.attempt_binding_mismatches(
        record, plan, plan_sha256, obligation)
    expected_record = {"check": obligation.get("producer_check")}
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
        "schema_version": contract["schema_version"],
        "record_kind": contract["record_kind"],
        "receipt_type_id": RECEIPT_TYPE_ID,
        "tool": CURRENT_PRODUCER_TOOL,
        "check": CURRENT_PRODUCER_CHECK,
        "result": "pass",
        "invalidated_by": None,
    }
    mismatches = [field for field, expected in fixed.items()
                  if record.get(field) != expected]
    if record.get("tool_version") != CURRENT_PRODUCER_VERSION:
        mismatches.append("tool_version")
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


def current_receipt_errors(record, *, root=None):
    """Return current hard-cut rendering record errors."""
    try:
        validate_record(
            record, contract=load_contract(root) if root is not None else None)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return [str(exc)]
    return []
RENDERING_MODES = frozenset(_SHIPPED_VALUES["modes"])
RENDERING_VERIFICATION_FIELDS = _SHIPPED_VALUES["field_order"]


__all__ = [
    'CURRENT_PRODUCER_CHECK',
    'CURRENT_PRODUCER_TOOL',
    'CURRENT_PRODUCER_VERSION',
    'RECEIPT_TYPE_ID',
    'RENDERING_MODES',
    'RENDERING_VERIFICATION_CONTRACT_PATH',
    'contract_sha256',
    'current_receipt_errors',
    'load_contract',
    'record_dependency_fingerprint',
    'validate_contract',
    'validate_record',
    'validate_record_for_obligation',
]
