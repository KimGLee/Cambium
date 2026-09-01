#!/usr/bin/env python3
"""Run one registered scan and record a typed deterministic Gate result.

This adapter closes the gap between a Profile's generic Registered Scan row
and ``deterministic-gate-result-v1``.  It resolves both from one authorized
Profile view, executes the shell-free registered command, accepts only a
clean final pass receipt for the exact scan ID, and wraps that receipt into a
self-contained Gate result bound to one target page and one unambiguous
completion value.  It never writes Coverage or page state.
"""

import os
import subprocess
import sys

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
import Tools.execution.evidence.metadata_gate_runtime as metadata_gate_runtime
import Tools.execution.task_runtime.runtime_paths as runtime_paths


PRODUCER_IDENTITY = metadata_gate_runtime.DETERMINISTIC_GATE_PRODUCER_IDENTITY
TOOL = PRODUCER_IDENTITY.tool
TOOL_VERSION = PRODUCER_IDENTITY.tool_version
CHECK = PRODUCER_IDENTITY.check
DEFAULT_RECEIPTS = runtime_paths.GATE_RESULT_RECEIPT_PATH


def _scan_for_gate(context):
    contract = context.profile_view.get("_contract")
    matches = [scan for scan in contract.registered_scans
               if scan.scan_id == context.gate.producer_reference]
    if len(matches) != 1:
        raise ValueError(
            "deterministic Gate must resolve exactly one Registered Scan; "
            "found %d" % len(matches))
    return matches[0]


def run_registered_gate_scan(context):
    """Execute the exact registered scan and return its bound pass evidence."""
    gate = context.gate
    if gate.producer_kind != "deterministic":
        raise ValueError("Gate %s is not deterministic" % gate.gate_id)
    if gate.field_id is None or len(gate.completion_values) != 1:
        raise ValueError(
            "deterministic metadata Gate must own exactly one completion value")
    scan = _scan_for_gate(context)
    return metadata_gate_runtime.run_registered_scan(
        context.root, context.profile_view, scan,
        allowed_summary_results=("pass",))


def build_gate_result_receipt(context, scan_result, seq=1, base_receipt=None):
    """Wrap one validated scan pass in deterministic-gate-result-v1."""
    value = context.gate.completion_values[0]
    bindings = metadata_gate_runtime.receipt_bindings(context, value)
    summary = scan_result["summary"]
    receipt = base_receipt or kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK,
        context.page_path, "pass",
        "registered scan %s passed the typed Extension Gate" %
        context.gate.producer_reference, seq,
        receipt_type_id=
            metadata_gate_runtime.DETERMINISTIC_GATE_RECEIPT_TYPE_ID,
        root=context.root)
    receipt.update({
        "gate_id": bindings["gate_id"],
        "transition_id": bindings["transition_id"],
        "judgment_item_id": bindings["judgment_item_id"],
        "property_field": bindings["property_field"],
        "requested_completion_value":
            bindings["requested_completion_value"],
        "pass_authority_role_id": bindings["pass_authority_role_id"],
        "producer_kind": bindings["producer_kind"],
        "producer_capability": bindings["producer_capability"],
        "producer_reference": bindings["producer_reference"],
        "receipt_schema": bindings["receipt_schema"],
        "consumer_capability": bindings["consumer_capability"],
        "scan_id": context.gate.producer_reference,
        "registered_scan_receipt": summary,
        "registered_scan_receipt_sha256": scan_result["summary_sha256"],
        "registered_scan_receipt_set_sha256":
            scan_result["receipt_set_sha256"],
        "registered_scan_receipt_count": scan_result["receipt_count"],
        "registered_scan_command_sha256": scan_result["command_sha256"],
        "registered_scan_invocation_tool":
            scan_result["invocation_tool"],
        "registered_scan_invocation_path":
            scan_result["invocation_path"],
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
        "semantic_content_fingerprint":
            bindings["semantic_content_fingerprint"],
        "page_sha256": bindings["page_sha256"],
        "selected_profile_manifest":
            bindings["selected_profile_manifest"],
        "selected_profile_manifest_sha256":
            bindings["selected_profile_manifest_sha256"],
        "profile_snapshot_sha256": bindings["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            bindings["profile_contract_fingerprint"],
        "profile_load_inputs_sha256":
            bindings["profile_load_inputs_sha256"],
        "active_standards_sha256": bindings["active_standards_sha256"],
        "metadata_execution_contract_fingerprint":
            bindings["metadata_execution_contract_fingerprint"],
    })
    metadata_gate_runtime.validate_gate_receipt(context, receipt, value)
    return receipt


def _produce(context, base_receipt=None):
    result = run_registered_gate_scan(context)
    receipt = build_gate_result_receipt(
        context, result, base_receipt=base_receipt)
    return result, receipt


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Run a registered scan and record a deterministic "
                    "Extension Gate result")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--gate-id", required=True,
                        help="exact deterministic typed Profile Gate ID")
    parser.add_argument("--page", required=True,
                        help="repository-relative Markdown target")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--apply", action="store_true",
                        help="run and append the bound Gate result")
    parser.add_argument("--json", action="store_true",
                        help="write the applied receipt as one JSON array")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        runtime = runtime_validation.validate_runtime(root)
        metadata_gate_runtime.require_admitted_runtime(runtime)
        authority = queue_runtime.runtime_authority_context(runtime)
        context = metadata_gate_runtime.load_gate_context(
            root, args.gate_id, args.page, runtime=runtime,
            authority=authority)
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    if not args.apply:
        try:
            result, _receipt = _produce(context)
            runtime_validation.require_gate_context_current(
                context, "deterministic Gate dry-run completion")
        except (OSError, subprocess.SubprocessError, TypeError,
                UnicodeError, ValueError) as exc:
            print("[FAIL] %s" % exc, file=sys.stderr)
            return 1
        if not args.json:
            print("[PLAN] registered scan %s passed; Gate %s permits %s=%s" %
                  (context.gate.producer_reference, context.gate.gate_id,
                   context.gate.field_id, context.gate.completion_values[0]))
            if result["output"].strip():
                print("  scan: " + result["output"].strip().splitlines()[-1])
            print("dry run; add --apply to publish the typed Gate result")
        return 0

    receipt_seed = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK,
        context.page_path, "pass",
        "registered scan %s passed the typed Extension Gate" %
        context.gate.producer_reference, 1,
        receipt_type_id=
            metadata_gate_runtime.DETERMINISTIC_GATE_RECEIPT_TYPE_ID,
        root=context.root)
    operation = {
        "tool": TOOL,
        "action": "record-deterministic-profile-extension-gate-result",
        "gate_id": context.gate.gate_id,
        "transition_id": context.gate.transition_id,
        "target": context.page_path,
        "before_coverage_sha256": context.runtime.get("coverage_sha256"),
        "planned_after_coverage_sha256":
            context.runtime.get("coverage_sha256"),
        "before_queue_sha256": context.runtime.get("queue_sha256"),
        "planned_after_queue_sha256":
            context.runtime.get("queue_sha256"),
        "before_progress_sha256": context.runtime.get("progress_sha256"),
        "planned_after_progress_sha256":
            context.runtime.get("progress_sha256"),
        "page_sha256": context.page_snapshot.sha256,
        "metadata_execution_contract_fingerprint":
            context.metadata_contract_fingerprint,
        "receipt_id": receipt_seed["receipt_id"],
        "receipt_path": args.receipts,
    }
    operation.update(queue_runtime.runtime_authority_lock_fields(
        context.authority))
    try:
        authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
            context.authority)
        with kblib.runtime_write_lock(
                root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = runtime_validation.validate_runtime(
                    root, **authority_kwargs)
                if locked.get("errors"):
                    raise ValueError(
                        "runtime changed before registered Gate scan: %s" %
                        "; ".join(locked["errors"]))
                runtime_validation.require_gate_context_current(
                    context, "deterministic Gate locked preflight",
                    runtime=locked)
            scan_boundary = kblib.repository_snapshot_sha256(root)
            try:
                result, receipt = _produce(
                    context, base_receipt=receipt_seed)
            except (OSError, subprocess.SubprocessError, TypeError,
                    UnicodeError, ValueError):
                # A registered verifier is contractually read-only, but it is
                # still an external process.  Clear the lock after a rejected
                # scan only when both ordinary repository bytes and every
                # bound authority/target remain exact.  A mutation or an
                # uncertain recheck preserves the recovery lock.
                try:
                    unchanged = (
                        kblib.repository_snapshot_sha256(root) ==
                        scan_boundary)
                    if unchanged:
                        runtime_validation.require_gate_context_current(
                            context,
                            "failed deterministic Gate scan reconciliation")
                except (OSError, TypeError, UnicodeError, ValueError):
                    pass
                else:
                    lease.mark_reconciled()
                raise
            runtime_validation.require_gate_context_current(
                context, "deterministic Gate scan completion")
            before = kblib.receipt_append_observation(
                receipt_path, [receipt])
            outcome, error, _ = kblib.write_receipts_observed(
                receipt_path, [receipt], before=before)
            if outcome != "present" or error is not None:
                if outcome == "absent":
                    lease.mark_reconciled()
                raise ValueError(
                    "deterministic Gate receipt publication outcome=%s "
                    "error=%s" % (outcome, error))
    except (OSError, subprocess.SubprocessError, TypeError,
            UnicodeError, ValueError, kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        sys.stdout.write(
            kblib.canonical_json_bytes([receipt]).decode("utf-8") + "\n")
    else:
        print("[PASS] deterministic Gate result recorded: %s" %
              receipt["receipt_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
