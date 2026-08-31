#!/usr/bin/env python3
"""Deterministically assemble one current K12/16 Terminal Proof.

The caller supplies only the bounded semantic results named by the
Kernel-owned Terminal Proof contract. Runtime identities, counters, loading
selection, Receipt references, reconciliation and fingerprints are resolved
from one admitted current runtime view. The produced Proof is still consumed
by ``check_proof``; assembly never grants completion authority.
"""

import json
import os
import sys

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.audit.terminal_proof_contract as terminal_proof_contract
import Tools.execution.planning.check_corpus_plan as check_corpus_plan
import Tools.execution.task_runtime.queue_runtime.gate_registry as gate_registry
import Tools.execution.task_runtime.queue_runtime.receipts as receipt_catalogs
import Tools.execution.task_runtime.queue_runtime.runtime as queue_state
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import catalog_record
from Tools.platform.common.reporting import write_canonical_json


TOOL = "assemble_terminal_proof"
TOOL_VERSION = "1.0.0"
CAPABILITY_ID = "terminal-proof-producer-v1"
DEFAULT_PROOF_PATH = runtime_paths.child_path(
    runtime_paths.RECEIPT_ROOT, "terminal-proof.yaml")
DEFAULT_RECEIPT_REGISTER = runtime_paths.AUDIT_RECEIPT_REGISTER_PATH


class TerminalProofAssemblyError(ValueError):
    """Current state cannot produce one closed Terminal Proof."""


def _input_path(root, relative):
    return kblib.managed_repository_path(
        root, relative, runtime_paths.TRANSIENT_ROOT,
        suffixes=(".yaml", ".json"), must_exist=True)


def _receipt_register_path(root, relative, *, must_exist=True):
    return kblib.managed_repository_path(
        root, relative, runtime_paths.RECEIPT_ROOT,
        suffixes=(".jsonl",), must_exist=must_exist)


def _proof_path(root, relative, *, must_exist=False):
    return kblib.managed_repository_path(
        root, relative, runtime_paths.RECEIPT_ROOT,
        suffixes=(".yaml",), must_exist=must_exist)


def _receipt(result, receipt_id, *, label, expected, gate_id=None):
    if not isinstance(receipt_id, str) or not receipt_id:
        raise TerminalProofAssemblyError("%s receipt ID is required" % label)
    record = catalog_record(
        receipt_catalogs.current_receipt_catalog(result).get(receipt_id))
    if not isinstance(record, dict):
        raise TerminalProofAssemblyError(
            "%s %s is not in the current receipt catalog" %
            (label, receipt_id))
    mismatches = [
        field for field, value in expected.items()
        if record.get(field) != value
    ]
    if mismatches:
        raise TerminalProofAssemblyError(
            "%s %s differs from the current contract in: %s" %
            (label, receipt_id, ", ".join(sorted(mismatches))))
    if gate_id is not None:
        registry, errors = gate_registry.standards_gate_registry(
            result["root"])
        if errors:
            raise TerminalProofAssemblyError(
                "%s Gate registry is invalid: %s" %
                (label, "; ".join(errors)))
        if not gate_registry.receipt_matches_gate_id(
                record, gate_id, registry):
            raise TerminalProofAssemblyError(
                "%s %s does not match the current %s Gate contract" %
                (label, receipt_id, gate_id))
    return record


def _register_records(root, relative):
    absolute = _receipt_register_path(root, relative)
    records = {}
    for line_number, line in enumerate(
            kblib.read_text(absolute).splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TerminalProofAssemblyError(
                "%s:%d is malformed JSONL: %s" %
                (relative, line_number, exc)) from exc
        if not isinstance(record, dict):
            raise TerminalProofAssemblyError(
                "%s:%d is not a receipt mapping" %
                (relative, line_number))
        receipt_id = record.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            raise TerminalProofAssemblyError(
                "%s:%d has no receipt_id" % (relative, line_number))
        if receipt_id in records:
            raise TerminalProofAssemblyError(
                "%s repeats receipt_id %s" % (relative, receipt_id))
        records[receipt_id] = record
    return records


def _profile_receipt_dimensions(result):
    view = result.get("_profile_authorized_view")
    evaluation = view.get("_evaluation") if isinstance(view, dict) else None
    if evaluation is None or not evaluation.authorized:
        raise TerminalProofAssemblyError(
            "current runtime exposes no authorized selected Profile")
    return tuple(sorted(
        row.dimension_id for row in evaluation.contract.extension_dimensions
        if "receipt" in row.targets))


def _dimension_coverage(result, register_records, semantic_input):
    dimensions = tuple(audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER) + \
        _profile_receipt_dimensions(result)
    if len(dimensions) != len(set(dimensions)):
        raise TerminalProofAssemblyError(
            "selected Profile repeats a Kernel-owned audit dimension")
    contract = audit_receipt_contract.load_contract(result["root"])
    current = receipt_catalogs.current_receipt_catalog(result)
    by_dimension = {dimension: [] for dimension in dimensions}
    for receipt_id in sorted(register_records):
        record = register_records[receipt_id]
        if (record.get("record_kind") != "audit-receipt" or
                record.get("result") != "passed" or
                record.get("invalidated_by") is not None):
            continue
        current_record = catalog_record(current.get(receipt_id))
        if current_record != record:
            continue
        try:
            audit_receipt_contract.validate_audit_receipt(
                record, contract=contract, dimensions=set(dimensions))
        except (TypeError, ValueError) as exc:
            raise TerminalProofAssemblyError(
                "current AuditReceipt %s is invalid: %s" %
                (receipt_id, exc)) from exc
        dimension = record.get("dimension")
        if dimension in by_dimension:
            by_dimension[dimension].append(receipt_id)

    reasons = semantic_input["dimension_not_applicable_reasons"]
    missing = {dimension for dimension, ids in by_dimension.items() if not ids}
    if set(reasons) != missing:
        absent = sorted(missing - set(reasons))
        extra = sorted(set(reasons) - missing)
        details = []
        if absent:
            details.append("missing reasons for %s" % ", ".join(absent))
        if extra:
            details.append("reasons supplied despite current receipts for %s" %
                           ", ".join(extra))
        raise TerminalProofAssemblyError(
            "dimension applicability input does not match current evidence: " +
            "; ".join(details))
    return {
        dimension: (receipt_ids if receipt_ids else
                    "not-applicable: %s" % reasons[dimension])
        for dimension, receipt_ids in by_dimension.items()
    }


def _semantic_acceptance_receipt(result, repository_snapshot_sha256):
    corpus = check_corpus_plan.validate_corpus_plan(
        result["root"],
        authorized_profile_view=result.get("_profile_authorized_view"),
        authorized_active_standards_view=
            result.get("_active_standards_authorized_view"))
    if corpus.get("errors"):
        raise TerminalProofAssemblyError(
            "Corpus Planning cannot be resolved: %s" % "; ".join(
                "%s: %s" % (row.get("check"), row.get("details"))
                for row in corpus["errors"]))
    status = check_corpus_plan.semantic_acceptance_status(
        corpus, repository_snapshot_sha256=repository_snapshot_sha256)
    if status.get("status") == "inactive":
        return None
    if status.get("status") != "current":
        raise TerminalProofAssemblyError(
            "configured Corpus Planning semantic acceptance is %s" %
            status.get("status"))
    return status.get("receipt_id")


def assemble_terminal_proof(
        root, semantic_input, *, queue_check_receipt,
        corpus_plan_check_receipt,
        audit_receipt_register=DEFAULT_RECEIPT_REGISTER,
        terminal_audit_receipt_register=
            runtime_paths.TERMINAL_AUDIT_RECEIPT_PATH,
        full_deterministic_results=DEFAULT_RECEIPT_REGISTER):
    """Return one closed Proof derived from one current runtime snapshot."""
    root = os.path.realpath(os.path.abspath(root))
    semantic_input = terminal_proof_contract.validate_terminal_audit_input(
        semantic_input)
    result = runtime_validation.validate_runtime(root)
    if result.get("errors"):
        raise TerminalProofAssemblyError(
            "runtime is not admitted: %s" % "; ".join(result["errors"]))
    progress = result.get("progress") or {}
    queue = result.get("queue") or {}
    coverage = result.get("coverage") or {}
    contract = progress.get("contract") or {}
    terminal = progress.get("terminal_audit") or {}
    if (progress.get("task_state") != "completion-candidate" or
            terminal.get("state") != "ready"):
        raise TerminalProofAssemblyError(
            "Terminal Proof requires completion-candidate with terminal_audit=ready")
    completion_errors = queue_state.required_queue_completion_errors(result)
    if completion_errors:
        raise TerminalProofAssemblyError(
            "Required Queue is not complete: %s" %
            "; ".join(completion_errors))
    open_gaps = coverage.get("open_gaps")
    if not isinstance(open_gaps, list):
        raise TerminalProofAssemblyError("Coverage open_gaps must be a list")

    queue_receipt = _receipt(
        result, queue_check_receipt, label="Required Queue completion",
        expected={
            "queue_check_mode": "require-complete",
            "result": "pass",
            "task_id": progress.get("task_id"),
            "progress_ledger_sha256": result.get("progress_sha256"),
            "required_queue_sha256": result.get("queue_sha256"),
        }, gate_id="required-queue-completion")
    corpus_receipt = _receipt(
        result, corpus_plan_check_receipt, label="Corpus Plan structure",
        expected={
            "result": "pass",
        }, gate_id="corpus-plan-structure")
    register_records = _register_records(root, audit_receipt_register)
    repository_snapshot = kblib.repository_snapshot_sha256(root)
    reconciliation = audit_evidence_runtime.terminal_plan_reconciliation(result)
    proof = {
        "schema_version": 1,
        "task_id": progress.get("task_id"),
        "scope_version": contract.get("scope_version"),
        "contract_version": contract.get("contract_version"),
        "coverage_ledger_sha256": result.get("coverage_sha256"),
        "progress_ledger_sha256": result.get("progress_sha256"),
        "required_queue_path": runtime_paths.QUEUE_PATH,
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
        "required_queue_sha256": result.get("queue_sha256"),
        "remaining_required_work_units": result.get("remaining"),
        "queue_check_receipt": queue_receipt["receipt_id"],
        "corpus_plan_check_receipt": corpus_receipt["receipt_id"],
        "corpus_plan_semantic_acceptance_receipt":
            _semantic_acceptance_receipt(result, repository_snapshot),
        "upstream_revision_id": contract.get("upstream_revision_id"),
        "selected_profile_manifest":
            contract.get("selected_profile_manifest"),
        "selected_route_ids": list(contract.get("selected_route_ids") or []),
        "selected_card_paths": list(contract.get("selected_card_paths") or []),
        "selected_profile_route_ids": list(
            contract.get("selected_profile_route_ids") or []),
        "selected_read_sets": list(contract.get("selected_read_sets") or []),
        "loaded_module_paths": list(contract.get("loaded_module_paths") or []),
        "guidance_cutoff_id": semantic_input["guidance_cutoff_id"],
        "guidance_reconciliation_result": "passed",
        "coverage_reconciliation_result": "passed",
        "required_authoring_gaps": len(open_gaps),
        "unverified_batches": 0,
        "automated_QA_result": "passed",
        "manual_review_result": semantic_input["manual_review_result"],
        "rendering_evidence": semantic_input["rendering_evidence"],
        "audit_snapshot_id": "snapshot-" + repository_snapshot[7:23],
        "dimension_coverage": _dimension_coverage(
            result, register_records, semantic_input),
        "audit_receipt_register": audit_receipt_register,
        "terminal_audit_receipt_register":
            terminal_audit_receipt_register,
        "reused_receipts": reconciliation["reused_receipts"],
        "superseded_receipts": reconciliation["superseded_receipts"],
        "invalidated_receipts": reconciliation["invalidated_receipts"],
        "unresolved_invalidations":
            reconciliation["unresolved_invalidations"],
        "full_deterministic_results": full_deterministic_results,
        "incremental_manual_scope":
            semantic_input["incremental_manual_scope"],
        "sampling_scope_and_result":
            semantic_input["sampling_scope_and_result"],
        "systemic_expansions": semantic_input["systemic_expansions"],
        "deferred_evidence_backlog":
            semantic_input["deferred_evidence_backlog"],
        "final_handoff": semantic_input["final_handoff"],
        "time_contract_result": semantic_input["time_contract_result"],
    }
    try:
        terminal_proof_contract.validate_proof(proof)
    except (TypeError, ValueError) as exc:
        raise TerminalProofAssemblyError(
            "assembled Terminal Proof is invalid: %s" % exc) from exc
    return proof


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Assemble one current K12/16 Terminal Proof")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--terminal-audit-input", required=True,
                        help="closed YAML/JSON below .cambium/tmp")
    parser.add_argument("--queue-check-receipt", required=True)
    parser.add_argument("--corpus-plan-check-receipt", required=True)
    parser.add_argument("--audit-receipt-register",
                        default=DEFAULT_RECEIPT_REGISTER)
    parser.add_argument(
        "--terminal-audit-receipt-register",
        default=runtime_paths.TERMINAL_AUDIT_RECEIPT_PATH)
    parser.add_argument("--full-deterministic-results",
                        default=DEFAULT_RECEIPT_REGISTER)
    parser.add_argument("--proof", default=DEFAULT_PROOF_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        input_absolute = _input_path(root, args.terminal_audit_input)
        semantic_input = kblib.load_yaml_file(input_absolute)
        _receipt_register_path(root, args.audit_receipt_register)
        _receipt_register_path(root, args.terminal_audit_receipt_register)
        _receipt_register_path(root, args.full_deterministic_results)
        proof_absolute = _proof_path(root, args.proof)
        proof = assemble_terminal_proof(
            root, semantic_input,
            queue_check_receipt=args.queue_check_receipt,
            corpus_plan_check_receipt=args.corpus_plan_check_receipt,
            audit_receipt_register=args.audit_receipt_register,
            terminal_audit_receipt_register=
                args.terminal_audit_receipt_register,
            full_deterministic_results=args.full_deterministic_results)
        rendered = kblib.canonical_yaml(proof)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        payload = {"applied": False, "errors": [str(exc)], "status": "invalid"}
        if args.json:
            write_canonical_json(payload)
        else:
            print("assemble_terminal_proof: %s" % exc)
        return 1

    if args.apply:
        kblib.atomic_write_text(proof_absolute, rendered)
        try:
            current = kblib.read_text(proof_absolute)
        except OSError as exc:
            payload = {"applied": True, "errors": [str(exc)],
                       "status": "uncertain"}
            if args.json:
                write_canonical_json(payload)
            else:
                print("assemble_terminal_proof: %s" % exc)
            return 1
        if current != rendered:
            payload = {"applied": True,
                       "errors": ["resulting Terminal Proof bytes differ"],
                       "status": "uncertain"}
            if args.json:
                write_canonical_json(payload)
            else:
                print("assemble_terminal_proof: resulting bytes differ")
            return 1
    payload = {
        "applied": bool(args.apply),
        "errors": [],
        "status": "produced",
        "capability_id": CAPABILITY_ID,
        "terminal_proof_path": args.proof,
        "terminal_proof_sha256": kblib.sha256_bytes(rendered.encode("utf-8")),
    }
    if args.json:
        write_canonical_json(payload)
    else:
        print("assemble_terminal_proof: %s" % args.proof)
    return 0


if __name__ == "__main__":
    sys.exit(main())
