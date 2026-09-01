"""Loader and deterministic template projection for K12/16 Terminal Proof.

The Kernel YAML owns every Proof field, value class, and bounded Terminal
Audit input.  This module validates the contract's generic meta-shape and
derives all consumer projections from it; it does not maintain another field
list or a second example document.
"""
from Tools.platform.repository.path_contract import \
    canonical_repository_relative_path
from Tools.platform.repository.repository import repository_source_root

import argparse
import os
import re
import sys

import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.queue_runtime.canon as queue_canon
from Tools.platform.common.primitives import require_trimmed_string


TERMINAL_PROOF_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/terminal-proof-contract.yaml")
DEFAULT_TEMPLATE_PATH = "Tools/schemas/terminal_proof.template.yaml"
PRODUCER_TOOL = queue_canon.TERMINAL_PROOF_TOOL
PRODUCER_TOOL_VERSION = queue_canon.TERMINAL_PROOF_TOOL_VERSION
GATE_ID = "terminal-proof"
GATE_CHECK = "proof-check-summary"
GATE_RECEIPT_TYPE_ID = "terminal-proof-gate-v2"
DIAGNOSTIC_CHECK = "proof-diagnostic"
DIAGNOSTIC_RECEIPT_TYPE_ID = "terminal-proof-diagnostic-v1"
_CONTRACT_FIELDS = frozenset((
    "schema_version", "contract_id", "semantic_owner", "record_kind",
    "producer_capability", "consumer_gate_id", "serialization", "fields",
    "zero_fields", "passed_fields", "no_failure_token_fields",
    "path_fields", "canonical_path_values", "required_route_ids",
    "terminal_audit_input_fields",
))
_FIELD_SPEC_FIELDS = frozenset((
    "field", "type", "nullable", "source", "example",
))
_INPUT_SPEC_FIELDS = frozenset(("field", "type", "nullable"))
_FIELD_TYPES = frozenset((
    "commit-sha", "dimension-coverage", "integer", "list", "receipt-id",
    "repository-path", "repository-path-list", "result", "sha256",
    "string", "string-list", "string-map",
))
_FIELD_SOURCES = frozenset(("runtime", "derived", "terminal-audit"))
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
NOT_APPLICABLE_PREFIX = "not-applicable:"


def _closed_string_sequence(value, label, *, allow_empty=False):
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError("%s must be a%s string list" % (
            label, " possibly-empty" if allow_empty else " non-empty"))
    normalized = []
    for index, item in enumerate(value):
        normalized.append(require_trimmed_string(
            item, "%s[%d]" % (label, index)))
    if len(normalized) != len(set(normalized)):
        raise ValueError("%s must not contain duplicate values" % label)
    return tuple(normalized)


def _field_specs(value, label, *, include_source_and_example):
    if not isinstance(value, list) or not value:
        raise ValueError("%s must be a non-empty field list" % label)
    expected = (_FIELD_SPEC_FIELDS if include_source_and_example else
                _INPUT_SPEC_FIELDS)
    order = []
    specs = {}
    for index, row in enumerate(value):
        item_label = "%s[%d]" % (label, index)
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError("%s fields are not closed" % item_label)
        field = require_trimmed_string(
            row.get("field"), item_label + ".field")
        if field in specs:
            raise ValueError("%s repeats field %s" % (label, field))
        type_id = row.get("type")
        if type_id not in _FIELD_TYPES:
            raise ValueError("%s has unknown type %r" % (
                item_label, type_id))
        if not isinstance(row.get("nullable"), bool):
            raise ValueError("%s.nullable must be boolean" % item_label)
        spec = {"type": type_id, "nullable": row["nullable"]}
        if include_source_and_example:
            if row.get("source") not in _FIELD_SOURCES:
                raise ValueError("%s.source is invalid" % item_label)
            spec.update({
                "source": row["source"],
                "example": row.get("example"),
            })
        order.append(field)
        specs[field] = spec
    return tuple(order), specs


def _validate_value(value, spec, label):
    if value is None:
        if spec["nullable"]:
            return
        raise ValueError("%s must not be null" % label)
    type_id = spec["type"]
    if type_id == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("%s must be a non-negative integer" % label)
        return
    if type_id in {"string", "receipt-id", "result"}:
        require_trimmed_string(value, label)
        return
    if type_id == "sha256":
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise ValueError("%s must be sha256:<64 lowercase hex>" % label)
        return
    if type_id == "commit-sha":
        if not isinstance(value, str) or _COMMIT_RE.fullmatch(value) is None:
            raise ValueError("%s must be a full lowercase Git commit SHA" %
                             label)
        return
    if type_id == "repository-path":
        canonical_repository_relative_path(value, label)
        return
    if type_id in {"string-list", "repository-path-list"}:
        values = _closed_string_sequence(value, label, allow_empty=True)
        if type_id == "repository-path-list":
            for index, item in enumerate(values):
                canonical_repository_relative_path(
                    item, "%s[%d]" % (label, index))
        return
    if type_id == "list":
        if not isinstance(value, list):
            raise ValueError("%s must be a list" % label)
        return
    if type_id == "string-map":
        if not isinstance(value, dict):
            raise ValueError("%s must be a mapping" % label)
        for key, item in value.items():
            require_trimmed_string(key, label + " key")
            require_trimmed_string(item, "%s.%s" % (label, key))
        return
    if type_id == "dimension-coverage":
        if not isinstance(value, dict) or not value:
            raise ValueError("%s must be a non-empty mapping" % label)
        for dimension, evidence in value.items():
            require_trimmed_string(dimension, label + " dimension")
            item_label = "%s.%s" % (label, dimension)
            if isinstance(evidence, str):
                if (not evidence.startswith(NOT_APPLICABLE_PREFIX) or
                        not evidence[len(NOT_APPLICABLE_PREFIX):].strip()):
                    raise ValueError(
                        "%s must contain a reasoned not-applicable value" %
                        item_label)
            else:
                _closed_string_sequence(evidence, item_label)
        return
    raise ValueError("%s has unsupported type %s" % (label, type_id))


def validate_contract(document):
    """Validate generic contract structure and return derived projections."""
    if not isinstance(document, dict) or set(document) != _CONTRACT_FIELDS:
        raise ValueError("Terminal Proof contract fields are not closed")
    if document.get("schema_version") != 1:
        raise ValueError("Terminal Proof contract schema_version must be 1")
    for field in (
            "contract_id", "semantic_owner", "record_kind",
            "producer_capability", "consumer_gate_id", "serialization"):
        require_trimmed_string(document.get(field), field)
    field_order, fields = _field_specs(
        document.get("fields"), "fields", include_source_and_example=True)
    input_order, input_fields = _field_specs(
        document.get("terminal_audit_input_fields"),
        "terminal_audit_input_fields", include_source_and_example=False)
    for field, spec in fields.items():
        _validate_value(spec["example"], spec, "fields.%s.example" % field)

    referenced_groups = {}
    for key in (
            "zero_fields", "passed_fields", "no_failure_token_fields",
            "path_fields"):
        values = _closed_string_sequence(document.get(key), key)
        unknown = sorted(set(values) - set(fields))
        if unknown:
            raise ValueError("%s references unknown field(s): %s" %
                             (key, ", ".join(unknown)))
        referenced_groups[key] = values
    required_route_ids = _closed_string_sequence(
        document.get("required_route_ids"), "required_route_ids")
    canonical_paths = document.get("canonical_path_values")
    if not isinstance(canonical_paths, dict) or not canonical_paths:
        raise ValueError("canonical_path_values must be a non-empty mapping")
    unknown_canonical_paths = sorted(
        set(canonical_paths) - set(referenced_groups["path_fields"]))
    if unknown_canonical_paths:
        raise ValueError(
            "canonical_path_values references non-path field(s): %s" %
            ", ".join(unknown_canonical_paths))
    for field, value in canonical_paths.items():
        canonical_repository_relative_path(
            value, "canonical_path_values.%s" % field)
    return {
        "field_order": field_order,
        "fields": fields,
        "input_order": input_order,
        "input_fields": input_fields,
        "required_route_ids": required_route_ids,
        "canonical_path_values": dict(canonical_paths),
        **referenced_groups,
    }


def load_contract(root=None, snapshots=None):
    """Load the current Kernel-owned Terminal Proof contract."""
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(TERMINAL_PROOF_CONTRACT_PATH)
    if snapshot is None:
        text = kblib.read_text(os.path.join(
            os.fspath(root), *TERMINAL_PROOF_CONTRACT_PATH.split("/")))
    else:
        text = snapshot.read_text()
    document = kblib.parse_yaml_subset(text)
    validate_contract(document)
    return document


def contract_values(contract=None):
    return validate_contract(contract or _SHIPPED_CONTRACT)


def validate_proof(proof, contract=None):
    """Validate only the Kernel-owned closed shape and generic value types."""
    values = contract_values(contract)
    if not isinstance(proof, dict) or set(proof) != set(values["fields"]):
        raise ValueError("Terminal Proof fields are not closed")
    for field in values["field_order"]:
        _validate_value(proof.get(field), values["fields"][field],
                        "Terminal Proof.%s" % field)
    for field, expected in values["canonical_path_values"].items():
        if proof.get(field) != expected:
            raise ValueError(
                "Terminal Proof.%s must equal canonical path %s" %
                (field, expected))
    return proof


def validate_terminal_audit_input(value, contract=None):
    """Validate the exact semantic input boundary accepted by the assembler."""
    values = contract_values(contract)
    if not isinstance(value, dict) or set(value) != set(values["input_fields"]):
        raise ValueError("Terminal Audit input fields are not closed")
    for field in values["input_order"]:
        _validate_value(value.get(field), values["input_fields"][field],
                        "Terminal Audit input.%s" % field)
    return value


def template_projection(contract=None):
    """Return the example projection owned by the Kernel contract."""
    values = contract_values(contract)
    return {
        field: values["fields"][field]["example"]
        for field in values["field_order"]
    }


def render_template(contract=None):
    return (
        "# Generated from %s; do not edit by hand.\n" %
        TERMINAL_PROOF_CONTRACT_PATH +
        kblib.canonical_yaml(template_projection(contract))
    )


_BASE_RECEIPT_FIELDS = frozenset({
    "receipt_id", "receipt_type_id", "check", "target", "result",
    "details", "checked_at", "tool", "tool_version", "invalidated_by",
    "gate_id",
})
_DIAGNOSTIC_RECEIPT_FIELDS = _BASE_RECEIPT_FIELDS | {"diagnostic_id"}
_GATE_RECEIPT_FIELDS = _BASE_RECEIPT_FIELDS | frozenset({
    "task_id", "scope_version", "contract_version",
    "upstream_revision_id", "selected_profile_manifest",
    "coverage_ledger_sha256", "progress_ledger_sha256",
    "required_queue_path", "queue_revision", "queue_state_revision",
    "required_queue_sha256", "remaining_required_work_units",
    "queue_check_receipt", "corpus_plan_check_receipt",
    "terminal_proof_path", "terminal_proof_sha256",
    "repository_snapshot_sha256", "profile_snapshot_sha256",
    "profile_contract_fingerprint", "profile_load_inputs_sha256",
})


def current_receipt_errors(record, *, root=None):
    """Validate the two current check_proof Receipt machine objects."""
    del root
    if not isinstance(record, dict):
        return ["Terminal Receipt must be an object"]
    type_id = record.get("receipt_type_id")
    if type_id == GATE_RECEIPT_TYPE_ID:
        expected_fields = _GATE_RECEIPT_FIELDS
        expected_check = GATE_CHECK
        expected_result = "pass"
    elif type_id == DIAGNOSTIC_RECEIPT_TYPE_ID:
        expected_fields = _DIAGNOSTIC_RECEIPT_FIELDS
        expected_check = DIAGNOSTIC_CHECK
        expected_result = None
    else:
        return ["Terminal Receipt receipt_type_id is invalid"]
    errors = []
    if set(record) != expected_fields:
        errors.append("Terminal Receipt fields are not closed")
    expected = {
        "tool": PRODUCER_TOOL,
        "tool_version": PRODUCER_TOOL_VERSION,
        "check": expected_check,
        "gate_id": GATE_ID,
        "invalidated_by": None,
    }
    if expected_result is not None:
        expected["result"] = expected_result
    errors.extend(field for field, value in expected.items()
                  if record.get(field) != value)
    for field in ("receipt_id", "target", "details", "checked_at"):
        value = record.get(field)
        if not isinstance(value, str) or not value or value.strip() != value:
            errors.append(field)
    if type_id == DIAGNOSTIC_RECEIPT_TYPE_ID:
        if record.get("result") not in {"pass", "fail", "candidate"}:
            errors.append("result")
        value = record.get("diagnostic_id")
        if not isinstance(value, str) or not value or value.strip() != value:
            errors.append("diagnostic_id")
    return sorted(set(errors))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the K12/16 Terminal Proof example projection")
    parser.add_argument("--output", default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = repository_source_root(__file__)
    output = os.path.join(root, *args.output.split("/"))
    rendered = render_template(load_contract(root))
    if args.check:
        try:
            current = kblib.read_text(output)
        except OSError:
            return 1
        return 0 if current == rendered else 1
    kblib.atomic_write_text(output, rendered)
    return 0


_SHIPPED_CONTRACT = load_contract()


if __name__ == "__main__":
    sys.exit(main())
