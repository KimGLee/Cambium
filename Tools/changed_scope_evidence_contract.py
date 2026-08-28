"""Consumer-safe contract for plan-bound changed-scope evidence.

This module is deliberately below both the changed-scope producer CLI and the
AuditPlan evidence consumer.  It imports neither ``audit_evidence_runtime``
nor ``check_queue``.  Both sides can therefore validate the same closed record
shape, exact Kernel-registry projection, source producer identity, original
AuditPlan binding, and evidence-time contract fingerprint without a circular
dependency or a second interpretation of K12/05.

The contract covers the two record variants emitted by
``record_changed_scope_evidence``:

* dimensionless, plan-bound Gate evidence; and
* strict precursor evidence for a later dimension-specific AuditReceipt.

It does not make a Gate dimension-specific and it does not execute a judgment
algorithm.  Producer-time code separately re-runs the registered pure check
against admitted runtime inputs before publication.
"""

import os
import re

import audit_fingerprint
import audit_obligation_projection
import changed_scope_runtime_checks
import changed_scope_rendering_checks
import control_registry_contract
import kblib


TOOL = "record_changed_scope_evidence"
TOOL_VERSION = "1.0.0"
REGISTRY_PATH = audit_obligation_projection.CHANGED_SCOPE_REGISTRY_PATH

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

PLAN_BINDING_FIELDS = (
    "task_id", "batch_id", "opening_transition_receipt",
    "standards_version", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint",
)
SOURCE_SELECTOR_FIELDS = (
    "tool", "tool_version", "check", "mode", "dimensions",
    "lifecycle_states",
)
DIRECT_RECORD_FIELDS = frozenset((
    "receipt_id", "check", "target", "result", "details", "checked_at",
    "tool", "tool_version", "invalidated_by", "schema_version",
    "record_kind", "plan_id", "audit_plan_sha256", "obligation_id",
    "task_id", "batch_id", "opening_transition_receipt",
    "standards_version", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint", "owner_kind", "owner_rule_id",
    "kernel_extension_point", "partition", "due_stage", "scope",
    "applicability", "evidence_role", "evidence_kind", "dimension",
    "acceptance_predicate", "producer_check", "producer_capability",
    "producer_gate_id", "consumer_gate_id", "fingerprint_binding",
    "artifact_fingerprint", "dependency_fingerprint",
    "contract_fingerprint", "gate_id", "source_gate_id",
    "source_gate_selector", "source_scope", "source_exit_code",
    "source_summary_receipt_id", "source_receipt_set_sha256",
    "source_receipts",
))
AUDIT_PRODUCER_RECORD_FIELDS = frozenset((
    "receipt_id", "check", "target", "result", "details", "checked_at",
    "tool", "tool_version", "invalidated_by", "schema_version",
    "record_kind", "plan_id", "audit_plan_sha256", "obligation_id",
    "task_id", "batch_id", "opening_transition_receipt",
    "standards_version", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint", "owner_kind", "owner_rule_id",
    "kernel_extension_point", "partition", "due_stage", "scope",
    "applicability", "evidence_role", "evidence_kind", "dimension",
    "acceptance_predicate", "producer_check", "producer_capability",
    "producer_gate_id", "consumer_gate_id", "fingerprint_binding",
    "artifact_fingerprint", "dependency_fingerprint",
    "contract_fingerprint", "check_owner_tool",
    "check_owner_tool_version", "check_owner_source_sha256",
    "check_result_sha256", "check_result", "input_binding",
))
INPUT_BINDING_FIELDS = frozenset((
    "input_kind", "runtime_input_sha256", "repository_snapshot_sha256",
    "manifest_page_set_sha256",
))


class ChangedScopeEvidenceContractError(ValueError):
    """One changed-scope evidence record violates its closed contract."""


def _root(root=None):
    if root is None:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.realpath(os.path.abspath(os.fspath(root)))


def _nonempty(value, label):
    if (not isinstance(value, str) or not value or
            value.strip() != value):
        raise ChangedScopeEvidenceContractError(
            "%s must be a non-empty trimmed string" % label)
    return value


def load_registry(root=None, snapshots=None):
    """Load and strictly validate the sole K12/05 obligation registry."""
    return audit_obligation_projection.load_changed_scope_registry(
        _root(root), snapshots)


def normalized_base_rules(registry=None, root=None):
    registry = registry or load_registry(root)
    return audit_obligation_projection.validate_changed_scope_registry(
        registry)["base_rules"]


def load_control_registry(root=None):
    root = _root(root)
    path = os.path.join(
        root, *control_registry_contract.STANDARDS_GATE_REGISTRY_PATH.split(
            "/"))
    registry, errors = control_registry_contract.\
        parse_standards_gate_registry(kblib.read_text(path))
    if errors:
        raise ChangedScopeEvidenceContractError(
            "K00 Control registry is invalid: %s" % "; ".join(errors))
    return registry


def registry_sha256(registry):
    return kblib.sha256_bytes(
        kblib.canonical_yaml(registry).encode("utf-8"))


def source_gate_selector(predicate):
    selector = {
        "tool": predicate["tool"],
        "tool_version": predicate["tool_version"],
        "check": predicate["check"],
        "mode": predicate["mode"],
        "dimensions": list(predicate["dimensions"]),
        "lifecycle_states": list(predicate["lifecycle_states"]),
    }
    if tuple(selector) != SOURCE_SELECTOR_FIELDS:
        raise AssertionError("changed-scope Gate selector shape drifted")
    return selector


def registry_row(rule_id, registry=None, root=None):
    registry = registry or load_registry(root)
    matches = [row for row in normalized_base_rules(registry, root)
               if row["rule_id"] == rule_id]
    if len(matches) != 1:
        raise ChangedScopeEvidenceContractError(
            "changed-scope registry has no unique rule %s" % rule_id)
    return matches[0]


PURE_CHECK_MODULES = (
    changed_scope_runtime_checks,
    changed_scope_rendering_checks,
)


def pure_check_owner(rule_id, producer_check=None):
    """Resolve one exact pure-check owner without copying any predicate."""
    matches = []
    for module in PURE_CHECK_MODULES:
        check = module.CHECKS_BY_RULE_ID.get(rule_id)
        runners = getattr(module, "RUNNERS_BY_RULE_ID", None)
        runner = runners.get(rule_id) if runners is not None else None
        if module is changed_scope_runtime_checks:
            runner = {
                changed_scope_runtime_checks.GUIDANCE_RULE_ID:
                    changed_scope_runtime_checks.guidance_state_zero_counts,
                changed_scope_runtime_checks.COVERAGE_RULE_ID:
                    changed_scope_runtime_checks.coverage_routing_state,
                changed_scope_runtime_checks.TASK_CONTRACT_RULE_ID:
                    changed_scope_runtime_checks.
                    frozen_task_contract_references,
            }.get(rule_id)
        if (check is not None and callable(runner) and
                (producer_check is None or check == producer_check)):
            matches.append((module, runner, check))
    if len(matches) != 1:
        return None
    module, runner, check = matches[0]
    return {
        "module": module,
        "runner": runner,
        "check": check,
        "tool": module.TOOL,
        "tool_version": module.TOOL_VERSION,
        "validate_check_result": module.validate_check_result,
    }


def _definition_from_row(row, target):
    _nonempty(target, "obligation.target")
    definition = {
        "owner_kind": "kernel",
        "owner_rule_id": row["rule_id"],
        "kernel_extension_point": None,
        "partition": "changed-scope-deterministic",
        "due_stage": row["due_stage"],
        "target": target,
        "applicability": row["applicability"],
        "evidence_role": row["evidence_role"],
        "evidence_kind": row["evidence_kind"],
        "dimension": row["dimension"],
        "acceptance_predicate": row["rule_id"],
        "producer_capability": row.get("producer_capability"),
        "producer_gate_id": row.get("producer_gate_id"),
        "producer_check": row["producer_check"],
        "consumer_gate_id": row["consumer_gate_id"],
        "fingerprint_binding": "evidence-time",
    }
    return definition


def _obligation_definition_errors(obligation, row, root):
    if not isinstance(obligation, dict):
        return ["obligation"]
    try:
        definition = _definition_from_row(row, obligation.get("target"))
    except (KeyError, TypeError, ValueError):
        return ["registry-projection"]
    return [field for field, value in definition.items()
            if obligation.get(field) != value]


def runtime_check_source_sha256(rule_id=None, producer_check=None):
    owner = (pure_check_owner(rule_id, producer_check)
             if rule_id is not None else None)
    module = owner["module"] if owner is not None \
        else changed_scope_runtime_checks
    path = os.path.realpath(module.__file__)
    if not path.endswith(".py") or not os.path.isfile(path):
        raise ChangedScopeEvidenceContractError(
            "changed-scope runtime check source is not a Python file")
    return kblib.sha256_file(path)


def direct_dependency_fingerprint(target, selector, source_receipts):
    return kblib.sha256_bytes(kblib.canonical_json_bytes({
        "source_scope": target,
        "source_gate_selector": selector,
        "source_receipts": source_receipts,
    }))


def direct_contract_fingerprint(plan, obligation, registry, row, predicate):
    return audit_fingerprint.obligation_contract_fingerprint(
        plan, obligation, additional={
            "changed_scope_registry_sha256": registry_sha256(registry),
            "registry_rule": dict(row),
            "source_gate_selector": source_gate_selector(predicate),
        })


def runtime_contract_fingerprint(
        plan, obligation, registry, row, source_sha256=None):
    owner = pure_check_owner(row["rule_id"], row["producer_check"])
    if owner is None:
        raise ChangedScopeEvidenceContractError(
            "record rule has no exact changed-scope pure-check owner")
    source_sha256 = source_sha256 or runtime_check_source_sha256(
        row["rule_id"], row["producer_check"])
    return audit_fingerprint.obligation_contract_fingerprint(
        plan, obligation, additional={
            "changed_scope_registry_sha256": registry_sha256(registry),
            "registry_rule": dict(row),
            "check_owner_tool": owner["tool"],
            "check_owner_tool_version": owner["tool_version"],
            "check_owner_source_sha256": source_sha256,
        })


def source_summary(row, predicate, plan, source_exit_code,
                   source_receipts, *, target=None, root=None):
    """Return the one exact Gate summary after validating its receipt set."""
    if (not isinstance(source_exit_code, int) or
            isinstance(source_exit_code, bool) or
            source_exit_code not in (0, 1, 2)):
        raise ChangedScopeEvidenceContractError(
            "scoped Gate returned an unregistered exit code %s" %
            source_exit_code)
    if (not source_receipts or
            any(not isinstance(record, dict) for record in source_receipts)):
        raise ChangedScopeEvidenceContractError(
            "scoped Gate must emit a non-empty receipt object list")
    receipt_ids = [record.get("receipt_id") for record in source_receipts]
    if (any(not isinstance(value, str) or not value for value in receipt_ids)
            or len(receipt_ids) != len(set(receipt_ids))):
        raise ChangedScopeEvidenceContractError(
            "scoped Gate receipt IDs must be non-empty and unique")
    gate_id = row.get("producer_gate_id")
    expected_source_identity = {
        "tool": predicate["tool"],
        "tool_version": predicate["tool_version"],
        "gate_id": gate_id,
        "task_id": plan["task_id"],
        "standards_version": plan["standards_version"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "invalidated_by": None,
        "dimension": None,
    }
    invalid_receipts = []
    for record in source_receipts:
        invalid_fields = [
            field for field, value in expected_source_identity.items()
            if record.get(field) != value
        ]
        for field in ("check", "target", "details"):
            value = record.get(field)
            if (not isinstance(value, str) or not value or
                    value.strip() != value):
                invalid_fields.append(field)
        if record.get("result") not in ("pass", "fail", "candidate"):
            invalid_fields.append("result")
        checked_at = record.get("checked_at")
        if (not isinstance(checked_at, str) or
                UTC_RE.fullmatch(checked_at) is None):
            invalid_fields.append("checked_at")
        if invalid_fields:
            invalid_receipts.append(
                "%s[%s]" % (record.get("receipt_id"),
                              ",".join(sorted(set(invalid_fields)))))
    if invalid_receipts:
        raise ChangedScopeEvidenceContractError(
            "scoped Gate receipt identity is invalid: %s" %
            "; ".join(invalid_receipts))
    calculated_exit = kblib.exit_code(source_receipts)
    if source_exit_code != calculated_exit:
        raise ChangedScopeEvidenceContractError(
            "scoped Gate exit code differs from its emitted receipt set")
    summaries = [
        record for record in source_receipts
        if (record.get("tool") == predicate["tool"] and
            record.get("tool_version") == predicate["tool_version"] and
            record.get("gate_id") == gate_id and
            record.get("check") == row["producer_check"])
    ]
    if len(summaries) != 1:
        raise ChangedScopeEvidenceContractError(
            "scoped Gate must emit exactly one %s/%s summary, found %d" %
            (gate_id, row["producer_check"], len(summaries)))
    summary = summaries[0]
    mismatches = []
    if gate_id in {"page-contract", "frontmatter-vocabulary"}:
        expected_summary_identity = {
            "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                plan["profile_contract_fingerprint"],
        }
        mismatches.extend(
            field for field, value in expected_summary_identity.items()
            if summary.get(field) != value)
    compiled_field = {
        "page-contract": "compiled_page_contract_sha256",
        "frontmatter-vocabulary": "compiled_vocab_sha256",
    }.get(gate_id)
    required_fingerprints = (
        ("profile_load_inputs_sha256", compiled_field)
        if compiled_field is not None else ())
    for field in required_fingerprints:
        value = summary.get(field)
        if (not isinstance(value, str) or
                SHA256_RE.fullmatch(value) is None):
            mismatches.append(field)
    if target is not None:
        if gate_id == "page-contract":
            if summary.get("target") != "page-contract":
                mismatches.append("target")
            details = summary.get("details") or ""
            if re.search(r"(?:^|\s)pages=1(?:\s|$)", details) is None:
                mismatches.append("details.pages")
        elif gate_id == "frontmatter-vocabulary":
            if summary.get("target") != target:
                mismatches.append("target")
        elif gate_id == "wiki-link-integrity":
            if summary.get("target") != target:
                mismatches.append("target")
    allowed = {"pass"}
    if row["evidence_role"] == "triggers":
        allowed.add("candidate")
    if summary.get("result") not in allowed:
        mismatches.append("result")
    if source_exit_code == 1:
        mismatches.append("source_exit_code")
    if mismatches:
        raise ChangedScopeEvidenceContractError(
            "scoped Gate summary cannot satisfy the registered direct "
            "evidence route in: %s" %
            ", ".join(sorted(set(mismatches))))
    return summary


def validate_direct_record(record, registry=None, control_registry=None,
                           root=None):
    """Validate a closed, dimensionless changed-scope Gate record."""
    root = _root(root)
    registry = registry or load_registry(root)
    control_registry = control_registry or load_control_registry(root)
    if not isinstance(record, dict) or set(record) != DIRECT_RECORD_FIELDS:
        raise ChangedScopeEvidenceContractError(
            "changed-scope direct record fields are not closed")
    if record.get("schema_version") != 1:
        raise ChangedScopeEvidenceContractError(
            "changed-scope direct record schema_version must be 1")
    if (record.get("tool") != TOOL or
            record.get("tool_version") != TOOL_VERSION):
        raise ChangedScopeEvidenceContractError(
            "changed-scope direct record producer identity is invalid")
    row = registry_row(record.get("owner_rule_id"), registry, root)
    gate_id = row.get("producer_gate_id")
    predicate = control_registry.get(gate_id)
    if predicate is None or predicate.get("check") != row["producer_check"]:
        raise ChangedScopeEvidenceContractError(
            "changed-scope direct record has no exact registered Gate")
    expected = {
        "record_kind": row["evidence_kind"],
        "check": row["producer_check"],
        "owner_kind": "kernel",
        "kernel_extension_point": None,
        "partition": "changed-scope-deterministic",
        "due_stage": row["due_stage"],
        "applicability": row["applicability"],
        "evidence_role": row["evidence_role"],
        "evidence_kind": row["evidence_kind"],
        "dimension": None,
        "acceptance_predicate": row["rule_id"],
        "producer_check": row["producer_check"],
        "producer_capability": row.get("producer_capability"),
        "producer_gate_id": gate_id,
        "consumer_gate_id": row["consumer_gate_id"],
        "fingerprint_binding": "evidence-time",
        "gate_id": gate_id,
        "source_gate_id": gate_id,
        "source_scope": record.get("target"),
        "invalidated_by": None,
    }
    mismatches = [field for field, value in expected.items()
                  if record.get(field) != value]
    if record.get("scope") != [record.get("target")]:
        mismatches.append("scope")
    selector = source_gate_selector(predicate)
    if record.get("source_gate_selector") != selector:
        mismatches.append("source_gate_selector")
    pseudo_plan = {
        "task_id": record.get("task_id"),
        "standards_version": record.get("standards_version"),
        "selected_profile_manifest":
            record.get("selected_profile_manifest"),
        "profile_snapshot_sha256": record.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint":
            record.get("profile_contract_fingerprint"),
    }
    summary = source_summary(
        row, predicate, pseudo_plan, record.get("source_exit_code"),
        record.get("source_receipts"), target=record.get("target"), root=root)
    if record.get("source_summary_receipt_id") != summary.get("receipt_id"):
        mismatches.append("source_summary_receipt_id")
    source_set_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(record["source_receipts"]))
    if record.get("source_receipt_set_sha256") != source_set_sha:
        mismatches.append("source_receipt_set_sha256")
    dependency = direct_dependency_fingerprint(
        record["target"], selector, record["source_receipts"])
    if record.get("dependency_fingerprint") != dependency:
        mismatches.append("dependency_fingerprint")
    if record.get("result") != summary.get("result"):
        mismatches.append("result")
    for field in (
            "audit_plan_sha256", "artifact_fingerprint",
            "dependency_fingerprint", "contract_fingerprint",
            "source_receipt_set_sha256"):
        if (not isinstance(record.get(field), str) or
                SHA256_RE.fullmatch(record[field]) is None):
            mismatches.append(field)
    for field in (
            "receipt_id", "target", "details", "checked_at", "plan_id",
            "obligation_id", "task_id", "batch_id",
            "opening_transition_receipt", "standards_version",
            "selected_profile_manifest"):
        try:
            _nonempty(record.get(field), field)
        except ChangedScopeEvidenceContractError:
            mismatches.append(field)
    if (not isinstance(record.get("checked_at"), str) or
            UTC_RE.fullmatch(record["checked_at"]) is None):
        mismatches.append("checked_at")
    if mismatches:
        raise ChangedScopeEvidenceContractError(
            "changed-scope direct record is invalid in: %s" %
            ", ".join(sorted(set(mismatches))))
    return record


def validate_direct_record_for_plan(
        record, plan, plan_sha256, obligation, registry=None,
        control_registry=None, artifact_fingerprint=None, root=None):
    """Validate one direct record against its exact original AuditPlan row."""
    root = _root(root)
    registry = registry or load_registry(root)
    control_registry = control_registry or load_control_registry(root)
    validate_direct_record(record, registry, control_registry, root)
    row = registry_row(obligation.get("owner_rule_id"), registry, root)
    mismatches = _obligation_definition_errors(obligation, row, root)
    expected = {field: plan[field] for field in PLAN_BINDING_FIELDS}
    expected.update({
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "target": obligation["target"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "applicability": obligation["applicability"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        "dimension": None,
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
    })
    if artifact_fingerprint is not None:
        expected["artifact_fingerprint"] = artifact_fingerprint
    mismatches.extend(field for field, value in expected.items()
                      if record.get(field) != value)
    predicate = control_registry.get(obligation.get("producer_gate_id"))
    if predicate is None:
        mismatches.append("producer_gate_id")
    else:
        contract = direct_contract_fingerprint(
            plan, obligation, registry, row, predicate)
        if record.get("contract_fingerprint") != contract:
            mismatches.append("contract_fingerprint")
    if mismatches:
        raise ChangedScopeEvidenceContractError(
            "changed-scope direct record differs from AuditPlan in: %s" %
            ", ".join(sorted(set(mismatches))))
    return record


def validate_audit_producer_record(record, registry=None,
                                   control_registry=None, root=None):
    """Validate the closed precursor record without executing its check."""
    root = _root(root)
    registry = registry or load_registry(root)
    # Keep this argument in the public API so producer and consumers use one
    # signature; loading it also proves the active K00 registry is admissible.
    control_registry = control_registry or load_control_registry(root)
    if not isinstance(control_registry, dict):
        raise ChangedScopeEvidenceContractError(
            "K00 Control registry must be a mapping")
    if (not isinstance(record, dict) or
            set(record) != AUDIT_PRODUCER_RECORD_FIELDS):
        raise ChangedScopeEvidenceContractError(
            "changed-scope audit producer evidence fields are not closed")
    if (record.get("schema_version") != 1 or
            record.get("record_kind") != "audit-producer-evidence"):
        raise ChangedScopeEvidenceContractError(
            "changed-scope audit producer evidence schema is invalid")
    if (record.get("tool") != TOOL or
            record.get("tool_version") != TOOL_VERSION):
        raise ChangedScopeEvidenceContractError(
            "changed-scope audit producer identity is invalid")
    row = registry_row(record.get("owner_rule_id"), registry, root)
    owner = pure_check_owner(row["rule_id"], row["producer_check"])
    if (row.get("producer_capability") != "audit-receipt-producer-v1" or
            row.get("producer_gate_id") is not None or
            owner is None):
        raise ChangedScopeEvidenceContractError(
            "record rule has no exact changed-scope runtime producer")
    expected = {
        "check": row["producer_check"],
        "owner_kind": "kernel",
        "kernel_extension_point": None,
        "partition": "changed-scope-deterministic",
        "due_stage": row["due_stage"],
        "applicability": row["applicability"],
        "evidence_role": row["evidence_role"],
        "evidence_kind": row["evidence_kind"],
        "dimension": row["dimension"],
        "acceptance_predicate": row["rule_id"],
        "producer_check": row["producer_check"],
        "producer_capability": row.get("producer_capability"),
        "producer_gate_id": None,
        "consumer_gate_id": row["consumer_gate_id"],
        "fingerprint_binding": "evidence-time",
        "check_owner_tool": owner["tool"],
        "check_owner_tool_version": owner["tool_version"],
        "invalidated_by": None,
    }
    mismatches = [field for field, value in expected.items()
                  if record.get(field) != value]
    try:
        check_result = owner["validate_check_result"](
            record.get("check_result"))
    except (TypeError, ValueError) as exc:
        raise ChangedScopeEvidenceContractError(
            "changed-scope check_result is invalid: %s" % exc) from exc
    if (check_result["rule_id"] != row["rule_id"] or
            check_result["check_id"] != row["producer_check"]):
        mismatches.append("check_result")
    if record.get("result") != check_result["result"]:
        mismatches.append("result")
    scope = record.get("scope")
    target = record.get("target")
    expected_scope = (sorted(set(
        [target] + check_result["scope"]["targets"]))
        if isinstance(target, str) else None)
    if (expected_scope is None or not isinstance(scope, list) or
            scope != expected_scope or len(scope) != len(set(scope))):
        mismatches.append("scope")
    result_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(check_result))
    if record.get("check_result_sha256") != result_sha:
        mismatches.append("check_result_sha256")
    binding = record.get("input_binding")
    if not isinstance(binding, dict) or set(binding) != INPUT_BINDING_FIELDS:
        mismatches.append("input_binding")
    else:
        if (not isinstance(binding.get("input_kind"), str) or
                not binding["input_kind"]):
            mismatches.append("input_binding.input_kind")
        for field in (
                "runtime_input_sha256", "repository_snapshot_sha256",
                "manifest_page_set_sha256"):
            value = binding.get(field)
            if (field == "runtime_input_sha256" or value is not None) and (
                    not isinstance(value, str) or
                    SHA256_RE.fullmatch(value) is None):
                mismatches.append("input_binding.%s" % field)
        dependency = kblib.sha256_bytes(kblib.canonical_json_bytes({
            "input_binding": binding,
            "check_result": check_result,
        }))
        if record.get("dependency_fingerprint") != dependency:
            mismatches.append("dependency_fingerprint")
    if record.get("check_owner_source_sha256") != \
            runtime_check_source_sha256(
                row["rule_id"], row["producer_check"]):
        mismatches.append("check_owner_source_sha256")
    for field in (
            "audit_plan_sha256", "artifact_fingerprint",
            "dependency_fingerprint", "contract_fingerprint",
            "check_owner_source_sha256", "check_result_sha256"):
        if (not isinstance(record.get(field), str) or
                SHA256_RE.fullmatch(record[field]) is None):
            mismatches.append(field)
    for field in (
            "receipt_id", "target", "details", "checked_at", "plan_id",
            "obligation_id", "task_id", "batch_id",
            "opening_transition_receipt", "standards_version",
            "selected_profile_manifest"):
        try:
            _nonempty(record.get(field), field)
        except ChangedScopeEvidenceContractError:
            mismatches.append(field)
    if (not isinstance(record.get("checked_at"), str) or
            UTC_RE.fullmatch(record["checked_at"]) is None):
        mismatches.append("checked_at")
    if mismatches:
        raise ChangedScopeEvidenceContractError(
            "changed-scope audit producer evidence is invalid in: %s" %
            ", ".join(sorted(set(mismatches))))
    return record


def validate_audit_producer_record_for_plan(
        record, plan, plan_sha256, obligation, registry=None,
        control_registry=None, *, root=None, artifact_fingerprint=None,
        dependency_fingerprint=None, input_binding=None, check_result=None):
    """Validate precursor evidence against its exact original plan row.

    Optional producer-time values allow the writer to add live-input equality
    checks.  A later consumer can omit them and still receives the same closed
    shape, source-owner, source-hash, registry projection, plan-binding, and
    contract-fingerprint validation.
    """
    root = _root(root)
    registry = registry or load_registry(root)
    control_registry = control_registry or load_control_registry(root)
    validate_audit_producer_record(
        record, registry, control_registry, root)
    row = registry_row(obligation.get("owner_rule_id"), registry, root)
    mismatches = _obligation_definition_errors(obligation, row, root)
    expected = {field: plan[field] for field in PLAN_BINDING_FIELDS}
    expected.update({
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "target": obligation["target"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "applicability": obligation["applicability"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": obligation["evidence_kind"],
        "dimension": obligation["dimension"],
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
    })
    optional = {
        "artifact_fingerprint": artifact_fingerprint,
        "dependency_fingerprint": dependency_fingerprint,
        "input_binding": input_binding,
        "check_result": check_result,
    }
    expected.update({field: value for field, value in optional.items()
                     if value is not None})
    if check_result is not None:
        expected["check_result_sha256"] = kblib.sha256_bytes(
            kblib.canonical_json_bytes(check_result))
    expected["contract_fingerprint"] = runtime_contract_fingerprint(
        plan, obligation, registry, row)
    mismatches.extend(field for field, value in expected.items()
                      if record.get(field) != value)
    if mismatches:
        raise ChangedScopeEvidenceContractError(
            "changed-scope audit producer evidence differs from AuditPlan "
            "in: %s" % ", ".join(sorted(set(mismatches))))
    return record


def validate_record_for_plan(
        record, plan, plan_sha256, obligation, registry=None,
        control_registry=None, *, root=None, artifact_fingerprint=None):
    """Consumer entry point for either changed-scope evidence variant."""
    if not isinstance(record, dict):
        raise ChangedScopeEvidenceContractError(
            "changed-scope evidence must be a mapping")
    kind = record.get("record_kind")
    if kind == "audit-producer-evidence":
        return validate_audit_producer_record_for_plan(
            record, plan, plan_sha256, obligation, registry,
            control_registry, root=root,
            artifact_fingerprint=artifact_fingerprint)
    if kind in {"gate-receipt", "candidate-set-receipt"}:
        return validate_direct_record_for_plan(
            record, plan, plan_sha256, obligation, registry,
            control_registry, artifact_fingerprint, root)
    raise ChangedScopeEvidenceContractError(
        "record_kind is not changed-scope producer evidence")


__all__ = [
    "AUDIT_PRODUCER_RECORD_FIELDS", "ChangedScopeEvidenceContractError",
    "DIRECT_RECORD_FIELDS", "INPUT_BINDING_FIELDS", "PLAN_BINDING_FIELDS",
    "REGISTRY_PATH", "SHA256_RE", "SOURCE_SELECTOR_FIELDS", "TOOL",
    "TOOL_VERSION", "UTC_RE", "direct_contract_fingerprint",
    "direct_dependency_fingerprint", "load_control_registry",
    "load_registry", "normalized_base_rules", "registry_row",
    "pure_check_owner", "registry_sha256", "runtime_check_source_sha256",
    "runtime_contract_fingerprint", "source_gate_selector",
    "source_summary", "validate_audit_producer_record",
    "validate_audit_producer_record_for_plan", "validate_direct_record",
    "validate_direct_record_for_plan", "validate_record_for_plan",
]
