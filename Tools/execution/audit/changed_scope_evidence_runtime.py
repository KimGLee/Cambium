"""Resolve current inputs for Kernel-owned changed-scope pure producers.

This application boundary is shared by the plan-bound producer and the
AuditPlan consumer.  It executes only the check already selected by the
immutable plan and returns its exact current input/result/fingerprint
projection.  Keeping this here prevents producer retry and final evidence
selection from maintaining separate notions of currentness.
"""

import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
from Tools.governance.profile import profile_admission
from Tools.knowledge.content import check_links
from Tools.knowledge.metadata import (
    compose_page_contract, compose_vocab, check_page_contract, check_vocab,
)
import Tools.knowledge.rendering.changed_scope_rendering_checks as changed_scope_rendering_checks
import Tools.execution.audit.changed_scope_runtime_checks as changed_scope_runtime_checks
import Tools.platform.common.kblib as kblib


INPUT_BINDING_FIELDS = changed_scope_evidence_contract.INPUT_BINDING_FIELDS


def _current_direct_input_binding(root, plan, obligation, *, result=None):
    """Resolve actual checker dependencies, never yesterday's result hash."""
    gate = obligation["producer_gate_id"]
    if gate == check_links.GATE_ID:
        inputs = check_links.capture_inputs(root, obligation["target"])
        return changed_scope_evidence_contract.direct_input_binding(gate, {
            "check_inputs_sha256": kblib.sha256_bytes(
                kblib.canonical_json_bytes(inputs)),
        })
    composers = {
        "page-contract": (compose_page_contract,
                          "compiled_page_contract_sha256"),
        "frontmatter-vocabulary": (compose_vocab, "compiled_vocab_sha256"),
    }
    if gate not in composers:
        raise ValueError("direct Gate has no current input owner")
    view = (result or {}).get("_profile_authorized_view") or {}
    admission, errors = profile_admission.admit_profile_manifest(
        root, plan["selected_profile_manifest"],
        evaluation=view.get("_evaluation"))
    if errors:
        raise ValueError("direct Gate Profile inputs: %s" % "; ".join(errors))
    evaluation = admission.evaluation
    for field in ("profile_snapshot_sha256", "profile_contract_fingerprint"):
        if getattr(evaluation, field) != plan[field]:
            raise ValueError("direct Gate Profile differs from AuditPlan: %s" % field)
    composer, field = composers[gate]
    snapshot, errors = composer.admitted_artifact(
        root, composer.DEFAULT_OUTPUT, admission)
    if errors or snapshot is None:
        raise ValueError("direct Gate compiled inputs: %s" % "; ".join(errors))
    inputs = (check_page_contract.capture_inputs(
        root, obligation["target"], admission, snapshot)
        if gate == "page-contract" else
        check_vocab.capture_inputs(root, obligation["target"]))
    return changed_scope_evidence_contract.direct_input_binding(gate, {
        "profile_load_inputs_sha256": evaluation.profile_load_inputs_sha256,
        field: snapshot.sha256,
        "check_inputs_sha256": kblib.sha256_bytes(kblib.canonical_json_bytes(inputs)),
    })


def validate_current_direct_record(record, *, root, plan, plan_sha256,
                                   obligation, result=None, registry=None,
                                   control_registry=None,
                                   artifact_fingerprint=None):
    """Shared producer/reuse/consumer acceptance of one direct Gate record."""
    if artifact_fingerprint is None:
        snapshot = kblib.repository_target_snapshot(
            root, obligation["target"], suffixes=(".md", ".MD"),
            singly_linked=True)
        if not snapshot.exists:
            raise ValueError("direct Gate target is missing")
        artifact_fingerprint = audit_fingerprint.page_artifact_fingerprint(
            obligation["target"], snapshot.read_text())
    changed_scope_evidence_contract.validate_direct_record_for_plan(
        record, plan, plan_sha256, obligation, registry, control_registry,
        artifact_fingerprint, root)
    binding = _current_direct_input_binding(
        root, plan, obligation, result=result)
    if binding != record["source_input_binding"]:
        raise ValueError("direct Gate source input binding is not current")
    return record


def _frozen_target(frozen, target):
    matches = [page for page in frozen if page.path == target]
    if len(matches) != 1:
        raise ValueError(
            "changed-scope target %s is not exactly one open-batch page" %
            target)
    return matches[0]


def _matching_coverage_row(coverage, target):
    matches = [row for row in (coverage.get("pages") or [])
               if isinstance(row, dict) and row.get("path") == target]
    if len(matches) != 1:
        raise ValueError(
            "coverage check target %s has no unique Coverage row" % target)
    return matches[0]


def pure_check_result(*, root, result, item, obligation, row, frozen):
    """Run the exact pure predicate selected by one frozen obligation."""
    rule_id = row["rule_id"]
    if rule_id == changed_scope_runtime_checks.GUIDANCE_RULE_ID:
        if obligation["target"] != "Progress.guidance_queue":
            raise ValueError(
                "guidance obligation target is not the canonical Progress "
                "guidance queue selector")
        value = changed_scope_runtime_checks.guidance_state_zero_counts(
            result.get("progress") or {})
    elif rule_id == changed_scope_runtime_checks.COVERAGE_RULE_ID:
        _frozen_target(frozen, obligation["target"])
        value = changed_scope_runtime_checks.coverage_routing_state(
            result.get("coverage") or {}, result.get("queue") or {},
            [obligation["target"]])
    elif rule_id == changed_scope_runtime_checks.TASK_CONTRACT_RULE_ID:
        if obligation["target"] != item["id"]:
            raise ValueError(
                "Task Contract reference obligation must target its batch")
        value = changed_scope_runtime_checks.frozen_task_contract_references(
            root, result.get("progress") or {}, item, result)
    elif rule_id in changed_scope_rendering_checks.CHECKS_BY_RULE_ID:
        page = _frozen_target(frozen, obligation["target"])
        value = changed_scope_rendering_checks.RUNNERS_BY_RULE_ID[rule_id](
            page.snapshot.read_text(), obligation["target"])
    else:
        raise ValueError(
            "no exact runtime check dispatch exists for %s" % rule_id)
    owner = changed_scope_evidence_contract.pure_check_owner(
        rule_id, row["producer_check"])
    if owner is None:
        raise ValueError("runtime check has no unique registered owner")
    owner["validate_check_result"](value)
    if (value["rule_id"] != rule_id or
            value["check_id"] != row["producer_check"]):
        raise ValueError(
            "runtime check result identity differs from the Kernel registry")
    return value


def pure_input_binding(*, root, result, item, obligation, row, frozen,
                       check_result):
    """Freeze the authoritative inputs observed by one pure check."""
    rule_id = row["rule_id"]
    target = obligation["target"]
    repository_snapshot = None
    manifest_page_set = None
    if rule_id == changed_scope_runtime_checks.GUIDANCE_RULE_ID:
        input_kind = "progress-guidance-queue-v1"
        material = {
            "guidance_queue": (result.get("progress") or {}).get(
                "guidance_queue"),
            "progress_ledger_sha256": result.get("progress_sha256"),
        }
        artifact = kblib.sha256_bytes(kblib.canonical_json_bytes(material))
    elif rule_id == changed_scope_runtime_checks.COVERAGE_RULE_ID:
        input_kind = "coverage-row-and-queue-routing-v1"
        target_page = _frozen_target(frozen, target)
        material = {
            "coverage_row": _matching_coverage_row(
                result.get("coverage") or {}, target),
            "required_queue": (result.get("queue") or {}).get(
                "required_queue"),
            "coverage_ledger_sha256": result.get("coverage_sha256"),
            "required_queue_sha256": result.get("queue_sha256"),
        }
        manifest_page_set = audit_producer_runtime.page_set_sha256(
            (target_page,))
        artifact = audit_producer_runtime.page_artifact_fingerprint(
            target_page)
    elif rule_id == changed_scope_runtime_checks.TASK_CONTRACT_RULE_ID:
        input_kind = "task-contract-component-references-v1"
        material = {
            "task_contract": (result.get("progress") or {}).get("contract"),
            "queue_item": item,
            "runtime_state": audit_producer_runtime.runtime_state_bindings(
                result),
            "profile": audit_producer_runtime.profile_bindings(result),
        }
        repository_snapshot = kblib.repository_snapshot_sha256(root)
        artifact = kblib.sha256_bytes(kblib.canonical_json_bytes({
            "task_contract": material["task_contract"],
            "queue_item": material["queue_item"],
        }))
    elif rule_id in changed_scope_rendering_checks.CHECKS_BY_RULE_ID:
        input_kind = "markdown-page-bytes-v1"
        target_page = _frozen_target(frozen, target)
        material = {
            "target": target,
            "page_sha256": target_page.page_sha256,
        }
        manifest_page_set = audit_producer_runtime.page_set_sha256(
            (target_page,))
        artifact = audit_producer_runtime.page_artifact_fingerprint(
            target_page)
    else:
        raise ValueError(
            "runtime input binding has no owner for %s" % rule_id)
    binding = {
        "input_kind": input_kind,
        "runtime_input_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(material)),
        "repository_snapshot_sha256": repository_snapshot,
        "manifest_page_set_sha256": manifest_page_set,
    }
    if set(binding) != INPUT_BINDING_FIELDS:
        raise AssertionError("runtime input binding shape drifted")
    dependency = kblib.sha256_bytes(kblib.canonical_json_bytes({
        "input_binding": binding,
        "check_result": check_result,
    }))
    return binding, artifact, dependency


def current_projection(*, root, result, item, plan, obligation, frozen=None,
                       registry=None):
    """Return the one current projection producer and consumer both prove."""
    registry = registry or changed_scope_evidence_contract.load_registry(root)
    row = changed_scope_evidence_contract.registry_row(
        obligation.get("owner_rule_id"), registry, root)
    if frozen is None:
        page_input = (row["rule_id"] == changed_scope_runtime_checks.COVERAGE_RULE_ID or
                      row["rule_id"] in changed_scope_rendering_checks.CHECKS_BY_RULE_ID)
        frozen = (audit_producer_runtime.freeze_manifest_pages(
            root, result, {**item, "manifest": [obligation["target"]]})
            if page_input else ())
    check_result = pure_check_result(
        root=root, result=result, item=item, obligation=obligation,
        row=row, frozen=frozen)
    binding, artifact, dependency = pure_input_binding(
        root=root, result=result, item=item, obligation=obligation,
        row=row, frozen=frozen, check_result=check_result)
    contract_fingerprint = \
        changed_scope_evidence_contract.runtime_contract_fingerprint(
            plan, obligation, registry, row)
    return {
        "row": row,
        "check_result": check_result,
        "input_binding": binding,
        "artifact_fingerprint": artifact,
        "dependency_fingerprint": dependency,
        "contract_fingerprint": contract_fingerprint,
    }


def validate_current_record(record, *, root, result, item, plan,
                            plan_sha256, obligation, frozen=None, registry=None,
                            control_registry=None):
    """Validate one pure producer record against the exact current inputs."""
    projection = current_projection(
        root=root, result=result, item=item, plan=plan,
        obligation=obligation, frozen=frozen, registry=registry)
    changed_scope_evidence_contract.validate_check_record_for_plan(
        record, plan, plan_sha256, obligation,
        registry or changed_scope_evidence_contract.load_registry(root),
        control_registry, root=root,
        artifact_fingerprint=projection["artifact_fingerprint"],
        dependency_fingerprint=projection["dependency_fingerprint"],
        input_binding=projection["input_binding"],
        check_result=projection["check_result"])
    return record


__all__ = [
    'validate_current_direct_record',
    'pure_check_result',
    'pure_input_binding',
    'validate_current_record',
]
