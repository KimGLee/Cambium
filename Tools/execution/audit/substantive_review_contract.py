"""Strict loader for the Kernel-owned K12/12 substantive-review contract."""
from Tools.platform.repository.repository import repository_source_root

import os

import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.audit_plan_contract as _support
import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import require_trimmed_string


SUBSTANTIVE_REVIEW_CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/substantive-review-contract.yaml")
RECEIPT_TYPE_ID = "substantive-review-evidence-v3"
CURRENT_PRODUCER_VERSION = "1.0.0"
_CONTRACT_FIELDS = {
    "schema_version", "contract_id", "semantic_owner", "record_kind",
    "acceptance_predicate", "round_cap", "obligation_projection", "fields",
    "finding_fields", "result_values", "verdict_result_mappings",
    "finding_severities", "blocking_severities", "finding_status_values",
}
_OBLIGATION_PROJECTION_FIELDS = {
    "owner_kind", "owner_rule_id", "kernel_extension_point", "tier",
    "target_source", "applicability", "trigger_partition_mappings",
    "due_stage", "producer_check", "producer_capability",
    "producer_gate_id", "consumer_gate_id", "evidence_kind",
    "evidence_role", "dimension", "acceptance_predicate",
    "fingerprint_binding",
}
_TRIGGER_PARTITION_FIELDS = {"trigger", "partition"}
_FIELD_TYPES = frozenset((
    "integer", "string", "sha256", "utc-timestamp", "finding-list",
))


def _projection_string(value, label, *, nullable=False):
    if value is None and nullable:
        return None
    return require_trimmed_string(value, label)


def _validate_obligation_projection(projection, acceptance_predicate):
    """Validate the K12/12 AuditPlan projection without restating values."""
    if (not isinstance(projection, dict) or
            set(projection) != _OBLIGATION_PROJECTION_FIELDS):
        raise ValueError(
            "substantive-review obligation_projection fields are not closed")

    plan_values = _support.validate_contract(_support.load_contract())
    for field in (
            "owner_kind", "owner_rule_id", "tier", "target_source",
            "applicability", "due_stage", "producer_check",
            "consumer_gate_id", "evidence_kind", "evidence_role",
            "acceptance_predicate", "fingerprint_binding"):
        _projection_string(
            projection.get(field), "obligation_projection.%s" % field)
    for field in ("kernel_extension_point", "producer_capability",
                  "producer_gate_id", "dimension"):
        _projection_string(
            projection.get(field), "obligation_projection.%s" % field,
            nullable=True)

    if projection["owner_kind"] not in plan_values["owner_kinds"]:
        raise ValueError("substantive-review owner_kind is not registered")
    if projection["owner_kind"] == "kernel":
        if projection["kernel_extension_point"] is not None:
            raise ValueError(
                "Kernel substantive-review cannot claim an extension point")
    elif projection["kernel_extension_point"] not in \
            plan_values["extension_points"]:
        raise ValueError(
            "Profile substantive-review requires a registered extension point")
    if projection["due_stage"] not in plan_values["due_stages"]:
        raise ValueError("substantive-review due_stage is not registered")
    if projection["evidence_role"] not in plan_values["evidence_roles"]:
        raise ValueError("substantive-review evidence_role is not registered")
    if projection["evidence_kind"] not in plan_values["evidence_kinds"]:
        raise ValueError("substantive-review evidence_kind is not registered")
    if projection["fingerprint_binding"] not in \
            plan_values["fingerprint_bindings"]:
        raise ValueError(
            "substantive-review fingerprint_binding is not registered")
    if (projection["producer_capability"] is None) == \
            (projection["producer_gate_id"] is None):
        raise ValueError(
            "substantive-review must bind exactly one producer capability "
            "or Gate")
    if projection["acceptance_predicate"] != acceptance_predicate:
        raise ValueError(
            "substantive-review projection changes its acceptance predicate")
    if (projection["evidence_kind"] == "audit-receipt" and
            (projection["evidence_role"] != "emits" or
             projection["dimension"] is None)):
        raise ValueError(
            "substantive-review AuditReceipt projection must emit one "
            "dimension")

    mappings = projection.get("trigger_partition_mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ValueError(
            "substantive-review trigger_partition_mappings must be non-empty")
    triggers = []
    for index, mapping in enumerate(mappings):
        label = "obligation_projection.trigger_partition_mappings[%d]" % index
        if (not isinstance(mapping, dict) or
                set(mapping) != _TRIGGER_PARTITION_FIELDS):
            raise ValueError("%s fields are not closed" % label)
        trigger = _projection_string(mapping.get("trigger"), label + ".trigger")
        partition = _projection_string(
            mapping.get("partition"), label + ".partition")
        if trigger in triggers:
            raise ValueError(
                "substantive-review repeats trigger %s" % trigger)
        if partition not in plan_values["partitions"]:
            raise ValueError("%s partition is not registered" % label)
        triggers.append(trigger)
    return projection


def validate_contract(document):
    """Validate one substantive-review contract and return projections."""
    if not isinstance(document, dict) or set(document) != _CONTRACT_FIELDS:
        raise ValueError("substantive-review contract fields are not closed")
    if document.get("schema_version") != 3:
        raise ValueError("substantive-review schema_version must be 3")
    if document.get("contract_id") != "cambium-substantive-review":
        raise ValueError(
            "substantive-review contract_id must be "
            "cambium-substantive-review")
    if document.get("semantic_owner") != "K12/12":
        raise ValueError("substantive-review semantic_owner must be K12/12")
    if document.get("record_kind") != "substantive-review-evidence":
        raise ValueError("substantive-review record_kind is invalid")
    if document.get("acceptance_predicate") != "content-correctness":
        raise ValueError(
            "substantive-review must use the existing content-correctness "
            "predicate")
    if document.get("round_cap") != 2:
        raise ValueError("substantive-review round_cap must be 2")
    projection = _validate_obligation_projection(
        document.get("obligation_projection"),
        document.get("acceptance_predicate"))
    field_order, fields = _support.field_specs(
        document.get("fields"), "fields", allowed_types=_FIELD_TYPES)
    finding_order, finding_fields = _support.field_specs(
        document.get("finding_fields"), "finding_fields",
        allowed_types=frozenset(("string",)))
    results = _support.closed_string_list(
        document.get("result_values"), "result_values")
    mappings = document.get("verdict_result_mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("verdict_result_mappings must be non-empty")
    verdict_results = {}
    for index, row in enumerate(mappings):
        if not isinstance(row, dict) or set(row) != {"verdict", "result"}:
            raise ValueError(
                "verdict_result_mappings[%d] fields are not closed" % index)
        verdict = require_trimmed_string(
            row.get("verdict"), "verdict_result_mappings.verdict")
        result = row.get("result")
        if verdict in verdict_results or result not in results:
            raise ValueError("verdict_result_mappings is invalid")
        verdict_results[verdict] = result
    severities = _support.closed_string_list(
        document.get("finding_severities"), "finding_severities")
    blocking = _support.closed_string_list(
        document.get("blocking_severities"), "blocking_severities")
    statuses = _support.closed_string_list(
        document.get("finding_status_values"), "finding_status_values")
    if not set(blocking).issubset(severities):
        raise ValueError(
            "substantive-review blocking severities must be registered")
    return {
        "field_order": field_order,
        "fields": fields,
        "finding_field_order": finding_order,
        "finding_fields": finding_fields,
        "results": frozenset(results),
        "verdict_results": verdict_results,
        "severities": frozenset(severities),
        "blocking": frozenset(blocking),
        "statuses": frozenset(statuses),
        "obligation_projection": projection,
    }


def load_contract(root=None, snapshots=None):
    """Load the current Kernel-owned substantive-review contract."""
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(SUBSTANTIVE_REVIEW_CONTRACT_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        text = kblib.read_text(os.path.join(
            root, *SUBSTANTIVE_REVIEW_CONTRACT_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_contract(document)
    return document


def validate_review_receipt(record, contract=None):
    """Validate one review evidence record and return it unchanged."""
    contract = contract or _SHIPPED_CONTRACT
    values = validate_contract(contract)
    if not isinstance(record, dict) or set(record) != set(values["fields"]):
        raise ValueError("substantive-review receipt fields are not closed")
    for field, spec in values["fields"].items():
        if field != "findings":
            _support.validate_value(
                record.get(field), spec,
                "substantive-review.%s" % field)
    if record.get("schema_version") != contract["schema_version"]:
        raise ValueError(
            "substantive-review schema_version must equal its Kernel contract")
    fixed = {
        "record_kind": contract["record_kind"],
        "receipt_type_id": RECEIPT_TYPE_ID,
        "tool": "record_substantive_review",
        "tool_version": CURRENT_PRODUCER_VERSION,
        "check": "substantive_review",
        "acceptance_predicate": contract["acceptance_predicate"],
        "fingerprint_binding":
            contract["obligation_projection"]["fingerprint_binding"],
    }
    for field, expected in fixed.items():
        if record.get(field) != expected:
            raise ValueError(
                "substantive-review %s must be %s" % (field, expected))
    verdict = record.get("verdict")
    if verdict not in values["verdict_results"]:
        raise ValueError("substantive-review verdict is invalid")
    if record.get("result") != values["verdict_results"][verdict]:
        raise ValueError("substantive-review result disagrees with verdict")
    if record.get("authoring_context_id") == record.get(
            "reviewer_context_id"):
        raise ValueError(
            "substantive-review reviewer context must differ from authoring "
            "context")
    round_number = record.get("round")
    if round_number not in range(1, contract["round_cap"] + 1):
        raise ValueError(
            "substantive-review round exceeds its Kernel contract")
    if round_number == 1 and record.get("round_1_receipt_id") is not None:
        raise ValueError("round 1 must not cite round_1_receipt_id")
    if round_number == 2 and record.get("round_1_receipt_id") is None:
        raise ValueError("round 2 must cite round_1_receipt_id")
    findings = record.get("findings")
    if not isinstance(findings, list):
        raise ValueError("substantive-review findings must be a list")
    if round_number == 2 and not findings:
        raise ValueError("round 2 must reconcile round 1 findings")
    finding_ids = []
    open_blocking = []
    for index, finding in enumerate(findings):
        label = "substantive-review.findings[%d]" % index
        if (not isinstance(finding, dict) or
                set(finding) != set(values["finding_fields"])):
            raise ValueError("%s fields are not closed" % label)
        for field, spec in values["finding_fields"].items():
            _support.validate_value(
                finding.get(field), spec, "%s.%s" % (label, field))
        finding_id = finding["finding_id"]
        if finding_id in finding_ids:
            raise ValueError("substantive-review repeats finding_id %s" %
                             finding_id)
        finding_ids.append(finding_id)
        severity = finding["severity"]
        status = finding["status"]
        if severity not in values["severities"]:
            raise ValueError("%s severity is invalid" % label)
        if status not in values["statuses"]:
            raise ValueError("%s status is invalid" % label)
        if round_number == 1:
            if finding["round_1_finding_id"] is not None:
                raise ValueError(
                    "%s round 1 finding must not cite itself" % label)
            expected_status = "open" if severity in values["blocking"] \
                else "recorded"
            if status != expected_status:
                raise ValueError(
                    "%s round 1 %s finding must be %s" %
                    (label, severity, expected_status))
        elif finding["round_1_finding_id"] is None:
            raise ValueError(
                "%s round 2 finding must cite a round 1 finding" % label)
        elif severity in values["blocking"] and status not in {
                "open", "closed"}:
            raise ValueError(
                "%s round 2 blocking finding must be open or closed" % label)
        elif severity == "minor" and status != "recorded":
            raise ValueError(
                "%s round 2 minor finding remains recorded" % label)
        if severity in values["blocking"] and status == "open":
            open_blocking.append(finding_id)
    if finding_ids != sorted(finding_ids):
        raise ValueError("substantive-review findings must be ordered by id")
    if verdict == "passed" and open_blocking:
        raise ValueError("a passing review cannot retain blocking findings")
    if verdict == "changes-required":
        if round_number != 1 or not open_blocking:
            raise ValueError(
                "changes-required is a round 1 verdict with open blocking "
                "findings")
    if verdict == "escalated":
        if round_number != 2 or not open_blocking:
            raise ValueError(
                "escalated is a round 2 verdict with unresolved blocking "
                "findings")
    return record


def validate_review_pair(first, second, contract=None):
    """Validate the exact round-1 to round-2 confirmation relationship.

    The immutable AuditPlan and review scope stay fixed across the pair, but
    round 2 intentionally observes the corrected after-image.  Page,
    semantic-content, source, artifact, and dependency fingerprints therefore
    belong to each round's own evidence and must not be forced equal.  Keeping
    them equal would make the Kernel's ``after fixes, confirm`` lifecycle
    impossible to execute.
    """
    validate_review_receipt(first, contract=contract)
    validate_review_receipt(second, contract=contract)
    if first["round"] != 1 or second["round"] != 2:
        raise ValueError("review pair must be ordered round 1 then round 2")
    if second["round_1_receipt_id"] != first["receipt_id"]:
        raise ValueError("round 2 cites a different round 1 receipt")
    binding_fields = audit_lifecycle_contract.ATTEMPT_IDENTITY_FIELDS + (
        "target", "contract_fingerprint", "fingerprint_binding",
        "acceptance_predicate", "authoring_context_id",
    )
    drift = [field for field in binding_fields if first[field] != second[field]]
    if drift:
        raise ValueError("round 2 binding drift: %s" % ", ".join(drift))
    first_by_id = {row["finding_id"]: row for row in first["findings"]}
    second_refs = [row["round_1_finding_id"] for row in second["findings"]]
    if len(second_refs) != len(set(second_refs)):
        raise ValueError("round 2 repeats a round 1 finding")
    if set(second_refs) != set(first_by_id):
        raise ValueError("round 2 must reconcile the exact round 1 finding set")
    for row in second["findings"]:
        first_row = first_by_id[row["round_1_finding_id"]]
        changed = [field for field in ("severity", "statement")
                   if row[field] != first_row[field]]
        if changed:
            raise ValueError(
                "round 2 changes finding identity in: %s" %
                ", ".join(changed))
    return second


_SHIPPED_CONTRACT = load_contract()
_SHIPPED_VALUES = validate_contract(_SHIPPED_CONTRACT)


def current_receipt_errors(record, *, root=None):
    """Return current hard-cut substantive-review record errors."""
    try:
        validate_review_receipt(
            record, contract=load_contract(root) if root is not None else None)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return [str(exc)]
    return []
REVIEW_RECEIPT_FIELDS = _SHIPPED_VALUES["field_order"]
FINDING_FIELDS = _SHIPPED_VALUES["finding_field_order"]
ROUND_CAP = _SHIPPED_CONTRACT["round_cap"]
OBLIGATION_PROJECTION = _SHIPPED_VALUES["obligation_projection"]


__all__ = [
    'OBLIGATION_PROJECTION',
    'SUBSTANTIVE_REVIEW_CONTRACT_PATH',
    'load_contract',
    'CURRENT_PRODUCER_VERSION',
    'RECEIPT_TYPE_ID',
    'current_receipt_errors',
    'validate_contract',
    'validate_review_pair',
    'validate_review_receipt',
]
