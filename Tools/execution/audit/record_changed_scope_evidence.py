#!/usr/bin/env python3
"""Produce plan-bound evidence for implemented K12/05 changed-scope rules.

The Kernel registry is the only list of obligations.  This adapter does not
fill gaps in that list with new predicates: it exposes every base row in a
producer trace, executes only an already-registered scoped Gate whose exact
producer is installed, and refuses rows for which no exact producer exists.

Gate evidence remains Gate evidence.  The direct record deliberately carries
``dimension: null``; the AuditPlan dimension classifies the obligation and is
not a claim that the underlying Gate emitted dimension evidence.
"""
from Tools.platform.repository.repository import (
    repository_source_root,
    tools_source_root,
)

import json
import os
import sys

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_lifecycle_contract as audit_lifecycle_contract
import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.execution.audit.audit_producer_chain as audit_producer_chain
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
import Tools.execution.audit.changed_scope_evidence_runtime as changed_scope_evidence_runtime
import Tools.knowledge.rendering.changed_scope_rendering_checks as changed_scope_rendering_checks
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.profile_contract as profile_contract
import Tools.platform.common.kblib as kblib
import Tools.execution.evidence.metadata_gate_runtime as metadata_gate_runtime
import Tools.knowledge.rendering.rendering_verification_contract as rendering_verification_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.agent_interface.entrypoint_loader import (
    EntrypointResolutionError,
    capture_argument_parser,
    describe_entrypoint,
    load_tool_implementation,
)
from Tools.platform.common import reporting
from Tools.platform.common.primitives import catalog_record


TOOL = changed_scope_evidence_contract.TOOL
TOOL_VERSION = changed_scope_evidence_contract.TOOL_VERSION
DEFAULT_RECEIPTS = runtime_paths.CHANGED_SCOPE_EVIDENCE_RECEIPT_PATH
REGISTRY_PATH = changed_scope_evidence_contract.REGISTRY_PATH

_PLAN_BINDING_FIELDS = changed_scope_evidence_contract.PLAN_BINDING_FIELDS
_TRACE_FIELDS = {
    "rule_id", "producer_check", "producer_route_kind",
    "producer_route_id", "evidence_kind", "status", "adapter_id",
    "existing_tool", "existing_tool_version", "existing_check", "reason",
}


ChangedScopeProducerError = \
    changed_scope_evidence_contract.ChangedScopeEvidenceContractError


def load_registry(root=None, snapshots=None):
    """Load the sole K12/05 base/extension registry strictly."""
    return changed_scope_evidence_contract.load_registry(root, snapshots)


def normalized_base_rules(registry=None, root=None):
    return changed_scope_evidence_contract.normalized_base_rules(
        registry, root)


def load_control_registry(root=None):
    return changed_scope_evidence_contract.load_control_registry(root)


def _selector(predicate):
    return changed_scope_evidence_contract.source_gate_selector(predicate)


def _installed_gate_identity_errors(gate_id, predicate):
    errors = []
    try:
        module = load_tool_implementation(predicate["tool"])
    except (EntrypointResolutionError, ImportError, OSError, ValueError) as exc:
        # A broken producer is unavailable; never infer a similarly named
        # package module or require the public adapter to re-export identity.
        return ["installed producer cannot import: %s" % exc]
    if getattr(module, "TOOL", None) != predicate["tool"]:
        errors.append("installed Tool identity differs from K00")
    if getattr(module, "TOOL_VERSION", None) != predicate["tool_version"]:
        errors.append("installed Tool version differs from K00")
    mapping = getattr(module, "GATE_CHECKS", None)
    declared_check = mapping.get(gate_id) if isinstance(mapping, dict) \
        else getattr(module, "GATE_CHECK", None)
    if declared_check != predicate["check"]:
        errors.append("installed Check identity differs from K00")
    declared_gate = getattr(module, "GATE_ID", None)
    if declared_gate is not None and declared_gate != gate_id and not (
            isinstance(mapping, dict) and gate_id in mapping):
        errors.append("installed Gate identity differs from K00")
    return errors


def _scoped_gate_interface_errors(tool):
    """Prove the registered producer exposes the exact read-only adapter.

    The Kernel registry selects the Gate. The public Tool's real argparse
    declaration selects whether that Gate can accept one frozen page and emit
    structured evidence. No private Gate whitelist is maintained here.
    """
    try:
        parser = capture_argument_parser(tool)
    except (EntrypointResolutionError, ImportError, OSError, ValueError) as exc:
        return ["installed producer interface cannot be read: %s" % exc]
    options = {
        option
        for action in parser._actions  # argparse has no public action iterator
        for option in action.option_strings
    }
    missing = sorted({"--scope", "--json"} - options)
    if missing:
        return ["installed producer lacks %s" % ", ".join(missing)]
    positionals = [
        action for action in parser._actions
        if not action.option_strings and action.dest != "help"
    ]
    if not positionals:
        return ["installed producer has no repository target argument"]
    return []


def _dedicated_capability_producer(row, root):
    """Resolve an exact dedicated producer through its own strict contract."""
    try:
        spec = audit_obligation_projection.obligation_spec_for_rule(
            row["rule_id"], root)
        chain = audit_producer_chain.precursor_chain_for_spec(
            spec, root=root)
        if chain["execution_route"] != "rendering-verification":
            return None
        capability_id = chain["precursor_capability"]
        contract = rendering_verification_contract.load_contract(root)
        rendering_verification_contract.validate_contract(contract)
        capability = metadata_execution_contract.capability_entry_by_id(
            capability_id, root=root)
        invocation_tool = metadata_execution_contract.\
            capability_invocation_tool(capability_id, root=root)
        descriptor = describe_entrypoint(invocation_tool)
        producer_module = load_tool_implementation(invocation_tool)
    except (EntrypointResolutionError, ImportError, OSError, TypeError,
            UnicodeError, ValueError, kblib.YamlSubsetError):
        return None
    if (not isinstance(capability, dict) or
            capability.get("kind") != "producer" or
            capability.get("implementation_owner") !=
            descriptor.implementation_path):
        return None
    if (getattr(producer_module, "TOOL", None) != invocation_tool or
            invocation_tool != chain["precursor_tool"] or
            getattr(producer_module, "TOOL_VERSION", None) !=
            rendering_verification_contract.CURRENT_PRODUCER_VERSION or
            getattr(producer_module, "CHECK", None) !=
            chain["precursor_check"] or
            not callable(getattr(producer_module, "build_record", None)) or
            not callable(getattr(
                producer_module, "validate_record_for_plan", None))):
        return None
    return {
        "adapter_id": capability_id,
        "tool": producer_module.TOOL,
        "tool_version": producer_module.TOOL_VERSION,
        "check": producer_module.CHECK,
    }


def producer_trace(root=None, registry=None, control_registry=None):
    """Trace every registry row without pretending a nearby check is exact."""
    root = repository_source_root(__file__, root)
    registry = registry or load_registry(root)
    control_registry = control_registry or load_control_registry(root)
    trace = []
    for row in normalized_base_rules(registry, root):
        capability = row.get("producer_capability")
        gate_id = row.get("producer_gate_id")
        route_kind = "gate" if gate_id is not None else "capability"
        route_id = gate_id if gate_id is not None else capability
        predicate = control_registry.get(gate_id) if gate_id else None
        existing_tool = predicate.get("tool") if predicate else None
        existing_version = predicate.get("tool_version") \
            if predicate else None
        existing_check = predicate.get("check") if predicate else None
        adapter_id = None
        status = "missing-exact-producer"
        if gate_id is None:
            pure_owner = changed_scope_evidence_contract.pure_check_owner(
                row["rule_id"], row["producer_check"])
            dedicated = _dedicated_capability_producer(row, root)
            try:
                spec = audit_obligation_projection.obligation_spec_for_rule(
                    row["rule_id"], root)
                chain = audit_producer_chain.precursor_chain_for_spec(
                    spec, root=root)
            except (TypeError, ValueError):
                chain = None
            if (pure_owner is not None and isinstance(chain, dict) and
                    chain["execution_route"] ==
                    "deterministic-audit-precursor" and
                    chain["precursor_capability"] == capability):
                status = "available"
                adapter_id = chain["precursor_capability"]
                existing_tool = pure_owner["tool"]
                existing_version = pure_owner["tool_version"]
                existing_check = pure_owner["check"]
                reason = (
                    "exact registered pure runtime check and its plan-bound "
                    "evidence adapter are installed")
            elif dedicated is not None:
                status = "available"
                adapter_id = dedicated["adapter_id"]
                existing_tool = dedicated["tool"]
                existing_version = dedicated["tool_version"]
                existing_check = dedicated["check"]
                reason = (
                    "exact dedicated producer and strict Kernel projection "
                    "contract are installed")
            elif capability == "registered-scan-v1":
                reason = (
                    "no Kernel base scan registration supplies the command "
                    "for exact check %s; record_gate_result executes only a "
                    "selected Profile's registered scan" %
                    row["producer_check"])
            else:
                reason = (
                    "no installed callable emits exact check %s for "
                    "capability %s" % (row["producer_check"], capability))
        elif predicate is None:
            reason = "producer Gate %s is absent from K00" % gate_id
        elif predicate["check"] != row["producer_check"]:
            reason = (
                "K00 Gate %s emits %s, not registry check %s" %
                (gate_id, predicate["check"], row["producer_check"]))
        else:
            identity_errors = _installed_gate_identity_errors(
                gate_id, predicate)
            interface_errors = _scoped_gate_interface_errors(
                predicate["tool"])
            if identity_errors or interface_errors:
                reason = "; ".join(identity_errors + interface_errors)
            else:
                status = "available"
                adapter_id = "scoped-%s-v1" % gate_id
                reason = "exact K00 Gate producer is installed and scopeable"
        record = {
            "rule_id": row["rule_id"],
            "producer_check": row["producer_check"],
            "producer_route_kind": route_kind,
            "producer_route_id": route_id,
            "evidence_kind": row["evidence_kind"],
            "status": status,
            "adapter_id": adapter_id,
            "existing_tool": existing_tool,
            "existing_tool_version": existing_version,
            "existing_check": existing_check,
            "reason": reason,
        }
        if set(record) != _TRACE_FIELDS:
            raise AssertionError("changed-scope producer trace drifted")
        trace.append(record)
    return tuple(trace)


def _trace_for_rule(rule_id, trace):
    matches = [row for row in trace if row["rule_id"] == rule_id]
    if len(matches) != 1:
        raise ChangedScopeProducerError(
            "changed-scope rule %s has no unique producer trace" % rule_id)
    row = matches[0]
    if row["status"] != "available":
        raise ChangedScopeProducerError(
            "changed-scope rule %s has no exact callable producer: %s" %
            (rule_id, row["reason"]))
    return row


def _registry_row(rule_id, registry, root=None):
    matches = [row for row in normalized_base_rules(registry, root)
               if row["rule_id"] == rule_id]
    if len(matches) != 1:
        raise ChangedScopeProducerError(
            "changed-scope registry has no unique rule %s" % rule_id)
    return matches[0]


def resolve_obligation(root, plan, obligation_id, registry=None,
                       control_registry=None, profile=None):
    """Resolve one required plan row back to its unchanged registry source."""
    registry = registry or load_registry(root)
    control_registry = control_registry or load_control_registry(root)
    matches = [row for row in plan.get("obligations") or []
               if isinstance(row, dict) and
               row.get("obligation_id") == obligation_id]
    if len(matches) != 1:
        raise ChangedScopeProducerError(
            "AuditPlan must contain exactly one obligation %s" %
            obligation_id)
    obligation = matches[0]
    expected_state = {
        "status": "required", "evidence_ref": None,
        "reused_receipt_id": None, "reuse_reason": None,
    }
    state_mismatches = [
        field for field, value in expected_state.items()
        if obligation.get(field) != value
    ]
    if state_mismatches:
        raise ChangedScopeProducerError(
            "obligation %s differs from its frozen required state in: %s" %
            (obligation_id, ", ".join(sorted(state_mismatches))))

    if (obligation.get("owner_kind") == "profile-extension" and
            obligation.get("kernel_extension_point") ==
            changed_scope_evidence_contract.PROFILE_SCAN_EXTENSION):
        contract, scan, _spec = changed_scope_evidence_contract.\
            authorized_profile_scan(
                plan, obligation, root=root, contract=profile)
        point = changed_scope_evidence_contract.profile_scan_extension_point(
            registry, root)
        if obligation.get("evidence_kind") != point["evidence_kind"]:
            raise ChangedScopeProducerError(
                "Profile registered-scan adapter expects %s, not %s" %
                (point["evidence_kind"], obligation.get("evidence_kind")))
        try:
            entrypoint = profile_contract.registered_scan_entrypoint(
                root, scan)
        except profile_contract.ProfileContractError as exc:
            raise ChangedScopeProducerError(str(exc)) from exc
        trace = {
            "rule_id": scan.scan_id,
            "producer_check": scan.scan_id,
            "producer_route_kind": "capability",
            "producer_route_id": point["producer_capability"],
            "evidence_kind": point["evidence_kind"],
            "status": "available",
            "adapter_id": "profile-registered-scan-v1",
            "existing_tool": entrypoint.tool,
            "existing_tool_version": None,
            "existing_check": scan.scan_id,
            "reason": (
                "the selected Profile's admitted registered scan is the "
                "exact K12/05 extension producer"),
        }
        if set(trace) != _TRACE_FIELDS:
            raise AssertionError("Profile registered-scan trace drifted")
        return obligation, scan, trace

    rule_id = obligation.get("owner_rule_id")
    row = _registry_row(rule_id, registry, root)
    spec = audit_obligation_projection.obligation_spec_for_rule(
        rule_id, root)
    if spec["source_registry"] != REGISTRY_PATH:
        raise ChangedScopeProducerError(
            "obligation %s is not owned by the changed-scope registry" %
            obligation_id)
    definition = audit_obligation_projection.resolve_obligation_definition(
        spec, obligation.get("target"))
    mismatches = [field for field, value in definition.items()
                  if obligation.get(field) != value]
    if mismatches:
        raise ChangedScopeProducerError(
            "obligation %s differs from its frozen K12/05 definition in: %s"
            % (obligation_id, ", ".join(sorted(set(mismatches)))))
    trace = _trace_for_rule(
        rule_id, producer_trace(root, registry, control_registry))
    expected_kind = (
        "gate-receipt" if trace["producer_route_kind"] == "gate"
        else "audit-receipt")
    if obligation["evidence_kind"] != expected_kind:
        raise ChangedScopeProducerError(
            "installed adapter route expects %s, not %s" %
            (expected_kind, obligation["evidence_kind"]))
    if expected_kind == "audit-receipt":
        try:
            audit_producer_chain.precursor_chain_for_obligation(
                obligation, root=root)
        except audit_producer_chain.AuditProducerChainError as exc:
            raise ChangedScopeProducerError(str(exc)) from exc
    return obligation, row, trace


def _frozen_target(frozen, target):
    matches = [page for page in frozen if page.path == target]
    if len(matches) != 1:
        raise ChangedScopeProducerError(
            "changed-scope Gate target %s is not exactly one open-batch page"
            % target)
    return matches[0]


def gate_command(root, plan, target, trace):
    """Return the shell-free exact scoped invocation for one available Gate."""
    tool = trace["existing_tool"]
    script = os.path.join(tools_source_root(__file__), "%s.py" % tool)
    if not os.path.isfile(script):
        raise ChangedScopeProducerError(
            "installed Gate script is absent: %s" % script)
    command = [sys.executable or "python3", script, root,
               "--scope", target, "--json"]
    if trace["producer_route_id"] == "page-contract":
        profile_dir = os.path.dirname(plan["selected_profile_manifest"])
        command.extend(["--profile", os.path.join(root, profile_dir)])
    return command


def run_source_gate(root, plan, target, trace):
    command = gate_command(root, plan, target, trace)
    completed = kblib.run_cambium_subprocess(
        command, cwd=root, text=True, capture_output=True, check=False)
    try:
        receipts = json.loads(completed.stdout.strip())
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        detail = completed.stderr.strip().replace("\n", " | ")[-2000:]
        raise ChangedScopeProducerError(
            "scoped Gate emitted no readable receipt array: %s; stderr=%s" %
            (exc, detail or "<empty>"))
    if not isinstance(receipts, list):
        raise ChangedScopeProducerError(
            "scoped Gate JSON output must be one receipt array")
    return select_source_gate_receipts(
        receipts, trace["producer_route_id"])


def select_source_gate_receipts(receipts, gate_id):
    """Project one multi-Gate Tool run onto the registered Gate identity.

    Some deterministic producers expose more than one independently
    registered Gate in one invocation (for example vocabulary legality and
    priority distribution).  A direct AuditPlan evidence record owns only
    the receipts for its exact Gate.  Sibling Gate results remain available
    to their own consumers, but cannot change this Gate's result or enter its
    evidence fingerprint.
    """
    if (not isinstance(receipts, list) or
            any(not isinstance(receipt, dict) for receipt in receipts)):
        raise ChangedScopeProducerError(
            "scoped Gate JSON output must contain receipt objects")
    selected = [
        receipt for receipt in receipts
        if receipt.get("gate_id") == gate_id
    ]
    if not selected:
        raise ChangedScopeProducerError(
            "scoped producer emitted no receipt for Gate %s" % gate_id)
    return kblib.exit_code(selected), selected


def _dependency_fingerprint(target, selector, source_receipts):
    return changed_scope_evidence_contract.direct_dependency_fingerprint(
        target, selector, source_receipts)


def _contract_fingerprint(plan, obligation, registry, row, predicate):
    return changed_scope_evidence_contract.direct_contract_fingerprint(
        plan, obligation, registry, row, predicate)


def build_direct_record(*, root, plan, plan_sha256, obligation, row, trace,
                        registry, control_registry, frozen,
                        source_exit_code, source_receipts, seq=1):
    """Bind one exact scoped Gate run without manufacturing a dimension."""
    target = _frozen_target(frozen, obligation["target"])
    predicate = control_registry[trace["producer_route_id"]]
    summary = changed_scope_evidence_contract.source_summary(
        row, predicate, plan, source_exit_code, source_receipts,
        target=obligation["target"], root=root)
    selector = _selector(predicate)
    source_set_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(source_receipts))
    identity = {
        "task_id": plan["task_id"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
    }
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, row["producer_check"], obligation["target"],
        summary["result"],
        "plan-bound changed-scope evidence from scoped Gate %s receipt %s" %
        (trace["producer_route_id"], summary["receipt_id"]),
        seq,
        receipt_type_id=
            changed_scope_evidence_contract.DIRECT_RECEIPT_TYPE_ID,
        root=root, identity=identity)
    receipt.update({
        "schema_version": changed_scope_evidence_contract.SCHEMA_VERSION,
        "record_kind": row["evidence_kind"],
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt": plan["opening_transition_receipt"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "scope": [obligation["target"]],
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
        "artifact_fingerprint":
            audit_producer_runtime.page_artifact_fingerprint(target),
        "dependency_fingerprint": _dependency_fingerprint(
            obligation["target"], selector, source_receipts),
        "contract_fingerprint": _contract_fingerprint(
            plan, obligation, registry, row, predicate),
        "gate_id": trace["producer_route_id"],
        "source_gate_id": trace["producer_route_id"],
        "source_gate_selector": selector,
        "source_scope": obligation["target"],
        "source_exit_code": source_exit_code,
        "source_summary_receipt_id": summary["receipt_id"],
        "source_receipt_set_sha256": source_set_sha,
        "source_receipts": source_receipts,
    })
    validate_direct_record_for_plan(
        receipt, plan, plan_sha256, obligation, registry, control_registry,
        audit_producer_runtime.page_artifact_fingerprint(target), root)
    return receipt


def build_candidate_set_record(*, context, scan_result, seq=1):
    """Bind one admitted Profile scan as dimensionless trigger evidence."""
    plan = context["plan"]
    obligation = context["obligation"]
    scan = context["scan"]
    if scan_result.get("scan") is not scan:
        raise ChangedScopeProducerError(
            "registered-scan result is not owned by the admitted Profile scan")
    records = scan_result.get("records")
    exit_code = scan_result.get("exit_code")
    try:
        entrypoint = profile_contract.registered_scan_entrypoint(
            context["root"], scan)
    except profile_contract.ProfileContractError as exc:
        raise ChangedScopeProducerError(str(exc)) from exc
    invocation_mismatches = [
        field for field, expected in (
            ("invocation_tool", entrypoint.tool),
            ("invocation_path", entrypoint.invocation_path),
        ) if scan_result.get(field) != expected
    ]
    if invocation_mismatches:
        raise ChangedScopeProducerError(
            "registered-scan result names the wrong public invocation in: %s"
            % ", ".join(invocation_mismatches))
    summary = metadata_gate_runtime.validate_registered_scan_receipts(
        scan, records, exit_code,
        expected_tool=entrypoint.tool,
        allowed_summary_results=("pass", "candidate"))
    if (scan_result.get("summary") != summary or
            scan_result.get("receipt_count") != len(records) or
            scan_result.get("receipt_set_sha256") != kblib.sha256_bytes(
                kblib.canonical_json_bytes(records))):
        raise ChangedScopeProducerError(
            "registered-scan result projection differs from its receipt set")
    identity = {
        "task_id": plan["task_id"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
    }
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, scan.scan_id, obligation["target"],
        summary["result"],
        "plan-bound candidate set from Profile registered scan %s receipt %s" %
        (scan.scan_id, summary["receipt_id"]),
        seq,
        receipt_type_id=
            changed_scope_evidence_contract.CANDIDATE_SET_RECEIPT_TYPE_ID,
        root=context["root"], identity=identity)
    receipt.update({
        "schema_version": changed_scope_evidence_contract.SCHEMA_VERSION,
        "record_kind": "candidate-set-receipt",
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": context["plan_sha256"],
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt": plan["opening_transition_receipt"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "scope": [obligation["target"]],
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
        "artifact_fingerprint":
            scan_result["repository_snapshot_sha256"],
        "dependency_fingerprint": None,
        "contract_fingerprint": None,
        "source_scan_selector":
            changed_scope_evidence_contract.profile_scan_selector(scan),
        "source_exit_code": exit_code,
        "source_summary_receipt_id": summary["receipt_id"],
        "source_receipt_set_sha256": scan_result["receipt_set_sha256"],
        "source_receipts": records,
        "registered_scan_receipt_count": scan_result["receipt_count"],
        "registered_scan_command_sha256": scan_result["command_sha256"],
        "registered_scan_invocation_tool": scan_result["invocation_tool"],
        "registered_scan_invocation_path": scan_result["invocation_path"],
        "registered_scan_invocation_sha256":
            scan_result["invocation_sha256"],
        "registered_scan_tool_sha256": scan_result["tool_sha256"],
        "registered_scan_config_sha256": scan_result["config_sha256"],
        "registered_scan_python_runtime_sha256":
            scan_result["python_runtime_sha256"],
        "registered_scan_execution_input_sha256":
            scan_result["execution_input_sha256"],
        "repository_snapshot_sha256":
            scan_result["repository_snapshot_sha256"],
    })
    receipt["dependency_fingerprint"] = \
        changed_scope_evidence_contract.candidate_set_dependency_fingerprint(
            receipt)
    receipt["contract_fingerprint"] = \
        changed_scope_evidence_contract.candidate_set_contract_fingerprint(
            plan, obligation, context["registry"], scan, receipt)
    validate_candidate_set_record_for_context(receipt, context)
    return receipt


def _runtime_check_source_sha256(row=None):
    if row is None:
        return changed_scope_evidence_contract.runtime_check_source_sha256()
    return changed_scope_evidence_contract.runtime_check_source_sha256(
        row["rule_id"], row["producer_check"])


def _runtime_check_result(context):
    """Execute the shared current pure-check projection."""
    return changed_scope_evidence_runtime.pure_check_result(
        root=context["root"], result=context["result"],
        item=context["item"], obligation=context["obligation"],
        row=context["row"], frozen=context["frozen"])


def _runtime_input_binding(context, check_result):
    """Freeze the shared producer/consumer current input projection."""
    return changed_scope_evidence_runtime.pure_input_binding(
        root=context["root"], result=context["result"],
        item=context["item"], obligation=context["obligation"],
        row=context["row"], frozen=context["frozen"],
        check_result=check_result)


def _runtime_contract_fingerprint(
        plan, obligation, registry, row, source_sha256):
    return changed_scope_evidence_contract.runtime_contract_fingerprint(
        plan, obligation, registry, row, source_sha256)


def build_audit_producer_record(*, context, check_result, seq=1):
    """Wrap one exact pure result for complete_audit_receipt."""
    plan = context["plan"]
    obligation = context["obligation"]
    row = context["row"]
    registry = context["registry"]
    input_binding, artifact, dependency = _runtime_input_binding(
        context, check_result)
    owner = changed_scope_evidence_contract.pure_check_owner(
        row["rule_id"], row["producer_check"])
    if owner is None:
        raise ChangedScopeProducerError(
            "AuditPlan rule has no unique pure-check producer")
    source_sha = _runtime_check_source_sha256(row)
    result_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(check_result))
    scope = sorted(set(
        [obligation["target"]] + check_result["scope"]["targets"]))
    identity = {
        "task_id": plan["task_id"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
    }
    seed = kblib.make_receipt(
        TOOL, TOOL_VERSION, row["producer_check"], obligation["target"],
        check_result["result"],
        "plan-bound producer evidence from %s@%s" % (
            owner["tool"], owner["tool_version"]),
        seq,
        receipt_type_id=
            changed_scope_evidence_contract.AUDIT_PRECURSOR_RECEIPT_TYPE_ID,
        root=context["root"], identity=identity)
    seed.update({
        "schema_version": changed_scope_evidence_contract.SCHEMA_VERSION,
        "record_kind":
            audit_producer_chain.precursor_chain_for_obligation(
                obligation, root=context["root"])["precursor_record_kind"],
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": context["plan_sha256"],
        "obligation_id": obligation["obligation_id"],
        "task_id": plan["task_id"],
        "batch_id": plan["batch_id"],
        "opening_transition_receipt": plan["opening_transition_receipt"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "partition": obligation["partition"],
        "due_stage": obligation["due_stage"],
        "scope": scope,
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
        "artifact_fingerprint": artifact,
        "dependency_fingerprint": dependency,
        "contract_fingerprint": _runtime_contract_fingerprint(
            plan, obligation, registry, row, source_sha),
        "check_owner_tool": owner["tool"],
        "check_owner_tool_version": owner["tool_version"],
        "check_owner_source_sha256": source_sha,
        "check_result_sha256": result_sha,
        "check_result": check_result,
        "input_binding": input_binding,
    })
    validate_audit_producer_record_for_context(seed, context)
    return seed


def validate_audit_producer_record_for_context(record, context):
    """Re-run the pure check and prove exact current-plan/input binding."""
    plan = context["plan"]
    obligation = context["obligation"]
    current_result = _runtime_check_result(context)
    binding, artifact, dependency = _runtime_input_binding(
        context, current_result)
    changed_scope_evidence_contract.\
        validate_audit_producer_record_for_plan(
            record, plan, context["plan_sha256"], obligation,
            context["registry"], context["control_registry"],
            root=context["root"], artifact_fingerprint=artifact,
            dependency_fingerprint=dependency, input_binding=binding,
            check_result=current_result)
    expected = {field: plan[field] for field in _PLAN_BINDING_FIELDS}
    expected.update({
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": context["plan_sha256"],
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
        "artifact_fingerprint": artifact,
        "dependency_fingerprint": dependency,
        "input_binding": binding,
        "check_result": current_result,
        "check_result_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(current_result)),
    })
    source_sha = _runtime_check_source_sha256(context["row"])
    expected["contract_fingerprint"] = _runtime_contract_fingerprint(
        plan, obligation, context["registry"], context["row"], source_sha)
    mismatches = [field for field, value in expected.items()
                  if record.get(field) != value]
    if mismatches:
        raise ChangedScopeProducerError(
            "changed-scope audit producer evidence differs from current "
            "AuditPlan/input in: %s" %
            ", ".join(sorted(set(mismatches))))
    return record


# The producer and both central consumers share these exact shape/plan
# validators.  Keeping the public names here preserves the CLI/test API while
# the implementation remains below audit_evidence_runtime in the import graph.
validate_direct_record = \
    changed_scope_evidence_contract.validate_direct_record
validate_direct_record_for_plan = \
    changed_scope_evidence_contract.validate_direct_record_for_plan
validate_audit_producer_record = \
    changed_scope_evidence_contract.validate_audit_producer_record


def validate_candidate_set_record_for_context(record, context):
    """Prove one candidate set still matches its plan and executable inputs."""
    changed_scope_evidence_contract.validate_candidate_set_record_for_plan(
        record, context["plan"], context["plan_sha256"],
        context["obligation"], context["registry"], root=context["root"],
        contract=context["profile_contract"])
    metadata_gate_runtime.validate_registered_scan_input_binding(
        context["root"], context["profile_view"], context["scan"], record,
        expected_repository_snapshot=record["artifact_fingerprint"],
        require_current_repository=True)
    return record


def existing_direct_record(result, plan, plan_sha256, obligation, registry,
                           control_registry, artifact_fingerprint):
    matches = audit_producer_runtime.obligation_attempt_records(
        result, tool=TOOL, plan_id=plan["plan_id"],
        obligation_id=obligation["obligation_id"])
    return evidence_attempt_runtime.unique_current_attempt(
        matches,
        validate_stable=lambda record: validate_direct_record_for_plan(
            record, plan, plan_sha256, obligation, registry,
            control_registry, None, result["root"]),
        validate_current=lambda record: validate_direct_record_for_plan(
            record, plan, plan_sha256, obligation, registry,
            control_registry, artifact_fingerprint, result["root"]),
        label="AuditPlan obligation %s direct evidence" %
              obligation["obligation_id"])


def existing_audit_producer_record(context):
    matches = audit_producer_runtime.obligation_attempt_records(
        context["result"], tool=TOOL,
        plan_id=context["plan"]["plan_id"],
        obligation_id=context["obligation"]["obligation_id"])
    return evidence_attempt_runtime.unique_current_attempt(
        matches,
        validate_stable=lambda record:
            changed_scope_evidence_contract.validate_audit_producer_record_for_plan(
                record, context["plan"], context["plan_sha256"],
                context["obligation"], context["registry"],
                context["control_registry"], root=context["root"]),
        validate_current=lambda record:
            changed_scope_evidence_runtime.validate_current_record(
                record, root=context["root"], result=context["result"],
                item=context["item"], plan=context["plan"],
                plan_sha256=context["plan_sha256"],
                obligation=context["obligation"], frozen=context["frozen"],
                registry=context["registry"],
                control_registry=context["control_registry"]),
        label="AuditPlan obligation %s audit-producer evidence" %
              context["obligation"]["obligation_id"])


def existing_candidate_set_record(context):
    matches = audit_producer_runtime.obligation_attempt_records(
        context["result"], tool=TOOL,
        plan_id=context["plan"]["plan_id"],
        obligation_id=context["obligation"]["obligation_id"])
    return evidence_attempt_runtime.unique_current_attempt(
        matches,
        validate_stable=lambda record:
            changed_scope_evidence_contract.validate_candidate_set_record_for_plan(
                record, context["plan"], context["plan_sha256"],
                context["obligation"], context["registry"],
                root=context["root"], contract=context["profile_contract"]),
        validate_current=lambda record:
            validate_candidate_set_record_for_context(record, context),
        label="AuditPlan obligation %s candidate-set evidence" %
              context["obligation"]["obligation_id"])


def existing_evidence_record(context):
    if context["obligation"]["evidence_kind"] == "candidate-set-receipt":
        return existing_candidate_set_record(context)
    if context["obligation"]["evidence_kind"] == "gate-receipt":
        page = context.get("target_page")
        if page is None:
            raise ChangedScopeProducerError(
                "scoped Gate obligation has no frozen page target")
        return existing_direct_record(
            context["result"], context["plan"], context["plan_sha256"],
            context["obligation"], context["registry"],
            context["control_registry"],
            audit_producer_runtime.page_artifact_fingerprint(page))
    return existing_audit_producer_record(context)


def require_exact_evidence_readback(path, receipt, context):
    matches = [row for row in audit_producer_runtime.read_receipt_records(path)
               if row.get("receipt_id") == receipt["receipt_id"]]
    if len(matches) != 1 or matches[0] != receipt:
        raise ChangedScopeProducerError(
            "published changed-scope evidence did not read back exactly")
    if receipt["record_kind"] == \
            audit_lifecycle_contract.CHANGED_SCOPE_PRECURSOR_RECORD_KIND:
        validate_audit_producer_record_for_context(matches[0], context)
    elif receipt["record_kind"] == "candidate-set-receipt":
        validate_candidate_set_record_for_context(matches[0], context)
    else:
        page = context.get("target_page")
        validate_direct_record_for_plan(
            matches[0], context["plan"], context["plan_sha256"],
            context["obligation"], context["registry"],
            context["control_registry"],
            audit_producer_runtime.page_artifact_fingerprint(page),
            context["root"])
    return matches[0]


def _context(root_arg, batch_id, plan_path, obligation_id):
    root, result, authority = audit_producer_runtime.admitted_runtime(root_arg)
    item, _activation = audit_producer_runtime.open_batch(result, batch_id)
    stage = audit_evidence_runtime.resolve_stage_plan(
        result, item, "pre-merge", required_state="open")
    if stage["audit_plan_path"] != plan_path:
        raise ChangedScopeProducerError(
            "current AuditPlan path is %s, not %s" %
            (stage["audit_plan_path"], plan_path))
    registry = load_registry(root)
    control_registry = load_control_registry(root)
    profile_view = result.get("_profile_authorized_view")
    profile = profile_view.get("_contract") \
        if isinstance(profile_view, dict) else None
    obligation, row, trace = resolve_obligation(
        root, stage["plan"], obligation_id, registry, control_registry,
        profile)
    frozen = audit_producer_runtime.freeze_manifest_pages(root, result, item)
    target_matches = [page for page in frozen
                      if page.path == obligation["target"]]
    if len(target_matches) > 1:
        raise ChangedScopeProducerError(
            "changed-scope target repeats in the frozen manifest")
    target_page = target_matches[0] if target_matches else None
    if trace["producer_route_kind"] == "gate" and target_page is None:
        raise ChangedScopeProducerError(
            "scoped Gate target is not a frozen manifest page")
    scan = row if trace["adapter_id"] == "profile-registered-scan-v1" \
        else None
    return {
        "root": root, "result": result, "authority": authority,
        "item": item, "stage": stage, "plan": stage["plan"],
        "plan_sha256": stage["audit_plan_sha256"],
        "registry": registry, "control_registry": control_registry,
        "obligation": obligation, "row": row, "trace": trace,
        "frozen": frozen, "target_page": target_page,
        "profile_view": profile_view, "profile_contract": profile,
        "scan": scan,
    }


def _context_with_runtime(context, result, item, stage):
    current = dict(context)
    current.update({
        "result": result,
        "item": item,
        "stage": stage,
        "plan": stage["plan"],
        "plan_sha256": stage["audit_plan_sha256"],
    })
    return current


def produce_evidence(context):
    if context["trace"]["adapter_id"] == "profile-registered-scan-v1":
        scan_result = metadata_gate_runtime.run_registered_scan(
            context["root"], context["profile_view"], context["scan"],
            allowed_summary_results=("pass", "candidate"))
        return build_candidate_set_record(
            context=context, scan_result=scan_result)
    if context["trace"]["producer_route_kind"] == "gate":
        source_exit, source_receipts = run_source_gate(
            context["root"], context["plan"],
            context["obligation"]["target"], context["trace"])
        return build_direct_record(
            root=context["root"], plan=context["plan"],
            plan_sha256=context["plan_sha256"],
            obligation=context["obligation"], row=context["row"],
            trace=context["trace"], registry=context["registry"],
            control_registry=context["control_registry"],
            frozen=context["frozen"], source_exit_code=source_exit,
            source_receipts=source_receipts)
    if context["trace"]["adapter_id"].startswith("dedicated-"):
        raise ChangedScopeProducerError(
            "obligation %s is produced only by %s@%s/%s; use that "
            "dedicated producer because its registered evidence inputs are "
            "not free-form changed-scope adapter arguments" % (
                context["obligation"]["obligation_id"],
                context["trace"]["existing_tool"],
                context["trace"]["existing_tool_version"],
                context["trace"]["existing_check"]))
    check_result = _runtime_check_result(context)
    return build_audit_producer_record(
        context=context, check_result=check_result)


def _evidence_exit_code(receipt):
    return {"pass": 0, "fail": 1, "candidate": 2}.get(
        receipt.get("result"), 1)


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record exact plan-bound K12/05 changed-scope evidence")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--list-producers", action="store_true",
                        help="report every Kernel base row and exact producer availability")
    parser.add_argument("--batch")
    parser.add_argument("--plan")
    parser.add_argument("--obligation-id")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if args.list_producers:
        try:
            trace = producer_trace(args.root)
        except (OSError, TypeError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            reporting.write_canonical_json(
                {"errors": [str(exc)], "status": "invalid"})
            return 1
        reporting.write_canonical_json({
            "errors": [], "status": "producer-trace",
            "rules": list(trace),
        })
        return 0

    missing_args = [name for name, value in (
        ("--batch", args.batch), ("--plan", args.plan),
        ("--obligation-id", args.obligation_id)) if not value]
    if missing_args:
        reporting.write_canonical_json({
            "applied": False,
            "errors": ["required argument(s): %s" %
                       ", ".join(missing_args)],
            "status": "invalid",
        })
        return 1
    try:
        context = _context(
            args.root, args.batch, args.plan, args.obligation_id)
        existing = existing_evidence_record(context)
        receipt_absolute = audit_producer_runtime.managed_receipt_path(
            context["root"], args.receipts)
        if existing is None:
            receipt = produce_evidence(context)
        else:
            receipt = existing
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        reporting.write_canonical_json(
            {"applied": False, "errors": [str(exc)], "status": "invalid"})
        return 1

    if existing is not None:
        reporting.write_canonical_json({
            "applied": args.apply, "errors": [],
            "status": "already-present", "receipt_id": receipt["receipt_id"],
            "receipt_path": args.receipts, "result": receipt["result"],
        })
        return _evidence_exit_code(receipt)
    if not args.apply:
        reporting.write_canonical_json({
            "applied": False, "errors": [], "status": "planned",
            "receipt_id": receipt["receipt_id"],
            "receipt_path": args.receipts, "result": receipt["result"],
        })
        return _evidence_exit_code(receipt)

    operation = audit_producer_runtime.runtime_lock_metadata(
        TOOL, "record-changed-scope-evidence", context["result"],
        context["authority"], batch_id=args.batch,
        plan_id=context["plan"]["plan_id"],
        obligation_id=context["obligation"]["obligation_id"])
    try:
        with kblib.runtime_write_lock(
                context["root"], owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = audit_producer_runtime.require_runtime_current(
                    context["root"], context["authority"],
                    "before changed-scope evidence publication")
                locked_item, _ = audit_producer_runtime.open_batch(
                    locked, args.batch)
                locked_stage = audit_evidence_runtime.resolve_stage_plan(
                    locked, locked_item, "pre-merge", required_state="open")
                for field in (
                        "audit_plan_id", "audit_plan_path",
                        "audit_plan_sha256"):
                    if locked_stage[field] != context["stage"][field]:
                        raise ChangedScopeProducerError(
                            "AuditPlan changed before publication in %s" % field)
                audit_producer_runtime.require_pages_current(
                    context["root"], context["frozen"],
                    "before changed-scope evidence publication")
                locked_context = _context_with_runtime(
                    context, locked, locked_item, locked_stage)
                if existing_evidence_record(locked_context) is not None:
                    raise ChangedScopeProducerError(
                        "changed-scope evidence appeared before publication")
                receipt = produce_evidence(locked_context)
                audit_producer_runtime.require_pages_current(
                    context["root"], context["frozen"],
                    "after changed-scope evidence production")
                after = audit_producer_runtime.require_runtime_current(
                    context["root"], context["authority"],
                    "after changed-scope evidence production")
                after_item, _ = audit_producer_runtime.open_batch(
                    after, args.batch)
                after_stage = audit_evidence_runtime.resolve_stage_plan(
                    after, after_item, "pre-merge", required_state="open")
                for field in (
                        "audit_plan_id", "audit_plan_path",
                        "audit_plan_sha256"):
                    if after_stage[field] != context["stage"][field]:
                        raise ChangedScopeProducerError(
                            "AuditPlan changed after evidence production in %s"
                            % field)
                before = kblib.receipt_append_observation(
                    receipt_absolute, [receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_absolute, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise ChangedScopeProducerError(
                    "changed-scope publication outcome=%s error=%s" %
                    (outcome, error))
    except (OSError, TypeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        reporting.write_canonical_json({
            "applied": False, "errors": [str(exc)], "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1

    try:
        require_exact_evidence_readback(
            receipt_absolute, receipt, context)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        reporting.write_canonical_json({
            "applied": True, "errors": [str(exc)], "status": "uncertain",
            "receipt_id": receipt["receipt_id"],
        })
        return 1
    reporting.write_canonical_json({
        "applied": True, "errors": [], "status": "recorded",
        "receipt_id": receipt["receipt_id"],
        "receipt_path": args.receipts, "result": receipt["result"],
    })
    return _evidence_exit_code(receipt)


if __name__ == "__main__":
    raise SystemExit(main())
