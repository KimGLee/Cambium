#!/usr/bin/env python3
"""Run one registered scan and record a typed deterministic Gate result.

This adapter closes the gap between a Profile's generic Registered Scan row
and ``deterministic-gate-result-v1``.  It resolves both from one authorized
Profile view, executes the shell-free registered command, accepts only a
clean final pass receipt for the exact scan ID, and wraps that receipt into a
self-contained Gate result bound to one target page and one unambiguous
completion value.  It never writes Coverage or page state.
"""

import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib
import metadata_gate_runtime


TOOL = "record_gate_result"
TOOL_VERSION = "1.0.0"
DEFAULT_RECEIPTS = ".cambium/receipts/gate-results.jsonl"
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _same_target_snapshot(left, right):
    """Return whether two observations name the same exact file generation."""
    return (
        left.exists and right.exists and
        (left.dev, left.ino, left.mode, left.nlink, left.size,
         left.mtime_ns, left.ctime_ns, left.data) ==
        (right.dev, right.ino, right.mode, right.nlink, right.size,
         right.mtime_ns, right.ctime_ns, right.data)
    )


def _write_read_only(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o444)


def _materialize_execution_inputs(temporary, runtime_files, scan,
                                  config_data):
    """Materialize immutable observations, never live source paths."""
    staged_root = os.path.join(temporary, "frozen-runtime")
    for relative, data in sorted(runtime_files.items()):
        _write_read_only(
            os.path.join(staged_root, *relative.split("/")), data)
    script_path = os.path.join(
        staged_root, *scan.script_repo_path.split("/"))
    if not os.path.isfile(script_path):
        raise ValueError(
            "registered scan entry script is absent from frozen runtime")
    config_path = None
    if config_data is not None:
        suffix = Path(scan.config_dependency.path).suffix or ".data"
        config_path = os.path.join(
            temporary, "frozen-profile-input", "scan-config" + suffix)
        _write_read_only(config_path, config_data)
    return script_path, config_path


def _replace_config_argument(command, config_path, expects_config):
    output = list(command)
    indexes = []
    index = 3
    while index < len(output):
        token = output[index]
        if token == "--config":
            if index + 1 >= len(output):
                raise ValueError("registered scan --config has no value")
            indexes.append((index + 1, False))
            index += 2
            continue
        if token.startswith("--config="):
            indexes.append((index, True))
        index += 1
    expected_count = 1 if expects_config else 0
    if len(indexes) != expected_count:
        raise ValueError(
            "registered scan compiled command has %d config argument(s), "
            "expected %d" % (len(indexes), expected_count))
    if indexes:
        position, inline = indexes[0]
        output[position] = (
            "--config=" + config_path if inline else config_path)
    return output


def _scan_for_gate(context):
    contract = context.profile_view.get("_contract")
    matches = [scan for scan in contract.registered_scans
               if scan.scan_id == context.gate.producer_reference]
    if len(matches) != 1:
        raise ValueError(
            "deterministic Gate must resolve exactly one Registered Scan; "
            "found %d" % len(matches))
    return matches[0]


def _parse_scan_receipts(path):
    records = []
    seen = set()
    try:
        with open(path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("line %d is not a JSON object" % line_number)
                receipt_id = record.get("receipt_id")
                if (not isinstance(receipt_id, str) or not receipt_id or
                        receipt_id in seen):
                    raise ValueError(
                        "line %d has missing or duplicate receipt_id" %
                        line_number)
                seen.add(receipt_id)
                records.append(record)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("registered scan receipts are unreadable: %s" % exc)
    if not records:
        raise ValueError("registered scan produced no machine-readable receipt")
    return records


def _validate_scan_pass(scan, records, exit_code):
    if exit_code != 0:
        raise ValueError(
            "registered scan did not pass cleanly (exit %d)" % exit_code)
    nonpasses = [record for record in records
                 if record.get("result") != "pass" or
                 record.get("invalidated_by") is not None]
    if nonpasses:
        raise ValueError(
            "registered scan emitted non-pass or invalidated evidence")
    summary = records[-1]
    if summary.get("scan_id") != scan.scan_id:
        raise ValueError(
            "registered scan final receipt names scan_id=%r, expected %r" %
            (summary.get("scan_id"), scan.scan_id))
    expected_tool = Path(scan.script_repo_path).stem
    if summary.get("tool") != expected_tool:
        raise ValueError(
            "registered scan final receipt tool=%r, expected %r" %
            (summary.get("tool"), expected_tool))
    try:
        datetime.datetime.strptime(
            summary.get("checked_at"), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "registered scan final receipt has invalid checked_at") from exc
    return summary


def run_registered_gate_scan(context):
    """Execute the exact registered scan and return its bound pass evidence."""
    gate = context.gate
    if gate.producer_kind != "deterministic":
        raise ValueError("Gate %s is not deterministic" % gate.gate_id)
    if gate.field_id is None or len(gate.completion_values) != 1:
        raise ValueError(
            "deterministic metadata Gate must own exactly one completion value")
    scan = _scan_for_gate(context)
    inputs = metadata_gate_runtime.deterministic_scan_input_binding(
        context, scan)
    command = list(inputs["command"])
    tool_before = inputs["tool_snapshot"]
    repository_before = kblib.repository_snapshot_sha256(context.root)
    scan_error = None
    completed = None
    records = None
    summary = None
    try:
        with tempfile.TemporaryDirectory(
                prefix="cambium-gate-scan-") as temporary:
            staged_script, staged_config = _materialize_execution_inputs(
                temporary, inputs["python_runtime_files"], scan,
                inputs["config_data"])
            execution_command = list(command)
            execution_command[1] = staged_script
            execution_command = _replace_config_argument(
                execution_command, staged_config,
                scan.config_dependency is not None)
            output_path = os.path.join(temporary, "receipts.jsonl")
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            environment.pop("PYTHONHOME", None)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONNOUSERSITE"] = "1"
            completed = subprocess.run(
                execution_command + ["--receipts", output_path],
                cwd=context.root, env=environment,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=60, check=False)
            records = _parse_scan_receipts(output_path)
        summary = _validate_scan_pass(scan, records, completed.returncode)
    except (OSError, subprocess.SubprocessError, TypeError,
            UnicodeError, ValueError) as exc:
        scan_error = exc
    repository_after = kblib.repository_snapshot_sha256(context.root)
    if repository_after != repository_before:
        raise ValueError(
            "repository changed while the registered Gate scan was running") \
            from scan_error
    tool_after = kblib.repository_target_snapshot(
        context.root, scan.script_repo_path,
        suffixes=".py", singly_linked=True)
    if not _same_target_snapshot(tool_before, tool_after):
        raise ValueError(
            "registered scan tool identity or bytes changed during execution") \
            from scan_error
    inputs_after = metadata_gate_runtime.deterministic_scan_input_binding(
        context, scan)
    input_fields = (
        "command_sha256", "tool_sha256", "config_sha256",
        "python_runtime_sha256", "execution_input_sha256",
    )
    if any(inputs_after[field] != inputs[field] for field in input_fields):
        raise ValueError(
            "registered scan executable inputs changed during execution") \
            from scan_error
    if scan_error is not None:
        raise scan_error
    return {
        "scan": scan,
        "summary": summary,
        "summary_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(summary)),
        "receipt_set_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(records)),
        "receipt_count": len(records),
        "command_sha256": inputs["command_sha256"],
        "tool_sha256": inputs["tool_sha256"],
        "config_sha256": inputs["config_sha256"],
        "python_runtime_sha256": inputs["python_runtime_sha256"],
        "execution_input_sha256": inputs["execution_input_sha256"],
        "repository_snapshot_sha256": repository_after,
        "output": completed.stdout,
    }


def build_gate_result_receipt(context, scan_result, seq=1, base_receipt=None):
    """Wrap one validated scan pass in deterministic-gate-result-v1."""
    value = context.gate.completion_values[0]
    bindings = metadata_gate_runtime.receipt_bindings(context, value)
    summary = scan_result["summary"]
    receipt = base_receipt or kblib.make_receipt(
        TOOL, TOOL_VERSION, metadata_gate_runtime.GATE_CHECK,
        context.page_path, "pass",
        "registered scan %s passed the typed Extension Gate" %
        context.gate.producer_reference, seq, root=context.root)
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
                        help="receipt JSONL path under .cambium/receipts")
    parser.add_argument("--apply", action="store_true",
                        help="run and append the bound Gate result")
    parser.add_argument("--json", action="store_true",
                        help="write the applied receipt as one JSON array")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        context = metadata_gate_runtime.load_gate_context(
            root, args.gate_id, args.page)
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    if not args.apply:
        try:
            result, _receipt = _produce(context)
            metadata_gate_runtime.require_context_current(
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
        TOOL, TOOL_VERSION, metadata_gate_runtime.GATE_CHECK,
        context.page_path, "pass",
        "registered scan %s passed the typed Extension Gate" %
        context.gate.producer_reference, 1, root=context.root)
    operation = {
        "tool": TOOL,
        "action": "record-deterministic-profile-extension-gate-result",
        "gate_id": context.gate.gate_id,
        "transition_id": context.gate.transition_id,
        "target": context.page_path,
        "before_coverage_sha256": context.runtime.get("coverage_sha256"),
        "planned_after_coverage_sha256":
            context.runtime.get("coverage_sha256"),
        "before_required_queue_sha256": context.runtime.get("queue_sha256"),
        "planned_after_required_queue_sha256":
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
    operation.update(check_queue.runtime_authority_lock_fields(
        context.authority))
    try:
        authority_kwargs = check_queue.runtime_authority_validation_kwargs(
            context.authority)
        with kblib.runtime_write_lock(
                root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if locked.get("errors"):
                    raise ValueError(
                        "runtime changed before registered Gate scan: %s" %
                        "; ".join(locked["errors"]))
                metadata_gate_runtime.require_context_current(
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
                        metadata_gate_runtime.require_context_current(
                            context,
                            "failed deterministic Gate scan reconciliation")
                except (OSError, TypeError, UnicodeError, ValueError):
                    pass
                else:
                    lease.mark_reconciled()
                raise
            metadata_gate_runtime.require_context_current(
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
