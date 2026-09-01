#!/usr/bin/env python3
"""Closed runtime bindings for typed Profile Extension Gates.

This module is intentionally a library, not a third Profile parser.  It
consumes the one snapshot-bound ``profile-load`` view admitted by
``check_queue``, resolves one exact :class:`profile_contract.ExtensionGate`,
and derives the only page-projection rule that the generic Integrator may add
to the Kernel metadata contract: an evidence-backed enum owned by Coverage.

Both the manual evidence producer and the Integrator use this module.  Keeping
receipt construction and receipt consumption on the same closed binding is
what prevents a prose Gate row, a stale Profile revision, or a role supplied
by a callback from becoming write authority.

The admission itself is not performed here.  ``check_queue`` owns runtime
validation, the authority context, the current receipt catalog and the
runtime-authority CAS; every one of those observations is passed in by the
caller that already holds it, so this module never imports the CLI facade.
"""

from dataclasses import dataclass
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.governance.profile.profile_contract as profile_contract
import Tools.knowledge.metadata.project_page_state as project_page_state
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.repository import repository
from Tools.platform.common.primitives import nonempty_string

# The Queue runtime's identity policy, read the way any consumer reads a
# declared surface.  This module owns whether a persisted typed Gate
# receipt is sound; it does not own what makes any receipt usable as
# evidence at all, and a second copy of that answer here would be a
# second answer.
from Tools.execution.task_runtime.queue_runtime import (
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    SHA256_RE,
    evidence_identity_errors,
    property_receipt_utc_date,
    runtime_metadata_execution_contract,
)


CONSUMER_OPERATION = "typed-field-metadata-transition"
MANUAL_GATE_RECEIPT_TYPE_ID = "profile-extension-manual-gate-receipt-v1"
DETERMINISTIC_GATE_RECEIPT_TYPE_ID = \
    "profile-extension-deterministic-gate-receipt-v1"
METADATA_TRANSITION_RECEIPT_TYPE_ID = "metadata-transition-receipt-v1"


@dataclass(frozen=True)
class ReceiptProducerIdentity:
    """One exact producer tuple shared by writer and current consumer."""

    tool: str
    tool_version: str
    check: str


MANUAL_GATE_PRODUCER_IDENTITY = ReceiptProducerIdentity(
    "record_gate_attestation", "1.0.0", "profile-extension-gate")
DETERMINISTIC_GATE_PRODUCER_IDENTITY = ReceiptProducerIdentity(
    "record_gate_result", "1.0.0", "profile-extension-gate")
METADATA_TRANSITION_PRODUCER_IDENTITY = ReceiptProducerIdentity(
    "apply_metadata_transition", "1.0.0", "metadata-transition")


def _typed_gate_receipt_errors(record, *, receipt_type_id, producer):
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=receipt_type_id,
        tool=producer.tool, tool_version=producer.tool_version,
        checks=producer.check)
    if isinstance(record, dict):
        required = (
            "gate_id", "transition_id", "judgment_item_id",
            "property_field", "requested_completion_value",
            "producer_capability", "receipt_schema",
            "consumer_capability", "semantic_content_fingerprint",
            "page_sha256", "selected_profile_manifest",
            "active_standards_sha256",
            "metadata_execution_contract_fingerprint",
        )
        for field in required:
            if field not in record:
                errors.append("typed Gate Receipt misses %s" % field)
    return errors


def current_manual_gate_receipt_errors(record, *, root=None):
    return _typed_gate_receipt_errors(
        record, receipt_type_id=MANUAL_GATE_RECEIPT_TYPE_ID,
        producer=MANUAL_GATE_PRODUCER_IDENTITY)


def current_deterministic_gate_receipt_errors(record, *, root=None):
    return _typed_gate_receipt_errors(
        record, receipt_type_id=DETERMINISTIC_GATE_RECEIPT_TYPE_ID,
        producer=DETERMINISTIC_GATE_PRODUCER_IDENTITY)


def current_metadata_transition_receipt_errors(record, *, root=None):
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=METADATA_TRANSITION_RECEIPT_TYPE_ID,
        tool=METADATA_TRANSITION_PRODUCER_IDENTITY.tool,
        tool_version=METADATA_TRANSITION_PRODUCER_IDENTITY.tool_version,
        checks=METADATA_TRANSITION_PRODUCER_IDENTITY.check)
    if isinstance(record, dict):
        for field in ("gate_id", "transition_id", "property_field",
                      "before_value", "after_value"):
            if field not in record:
                errors.append("metadata transition Receipt misses %s" % field)
    return errors


@dataclass(frozen=True)
class GateRuntimeContext:
    """One immutable authorization and state observation for one Gate target."""

    root: str
    runtime: dict
    authority: dict
    gate: object
    rules: tuple
    page_path: str
    page_snapshot: object
    semantic_content_fingerprint: str
    selected_profile_manifest_sha256: str
    metadata_contract_fingerprint: str
    repository_snapshot_sha256: str = None

    @property
    def profile_view(self):
        return self.authority["profile_view"]

    @property
    def active_standards_view(self):
        return self.authority["active_standards_view"]


def _exact_gate(contract, gate_id):
    matches = [gate for gate in contract.extension_gates
               if gate.gate_id == gate_id]
    if len(matches) != 1:
        raise ValueError(
            "Extension Gate %r must resolve exactly once in the authorized "
            "Profile; found %d" % (gate_id, len(matches)))
    gate = matches[0]
    if gate.field_id is None or not gate.completion_values:
        raise ValueError(
            "Extension Gate %s does not own a typed Vocabulary transition" %
            gate_id)
    return gate


def _projection_rules(metadata_contract, profile_contract):
    return metadata_property_state.profile_gate_projection_rules(
        profile_contract.root, profile_contract.extension_gates,
        metadata_contract=metadata_contract,
        authorized_profile_contract=profile_contract)


def _require_capability_linkage(root, gate):
    facts = (
        (gate.producer_capability, "producer"),
        (gate.receipt_schema, "receipt-schema"),
        (gate.consumer_capability, "consumer"),
    )
    for capability_id, kind in facts:
        if not metadata_execution_contract.capability_registered(
                capability_id, kind, root=root):
            raise ValueError(
                "Extension Gate capability is no longer installed: %s/%s" %
                (kind, capability_id))
    if not metadata_execution_contract.capability_supports(
            gate.consumer_capability, CONSUMER_OPERATION, root=root):
        raise ValueError(
            "Extension Gate consumer %s does not implement %s" %
            (gate.consumer_capability, CONSUMER_OPERATION))


def registered_scan_input_binding(root, profile_view, scan):
    """Freeze executable inputs for one admitted Profile registered scan.

    The Profile snapshot already owns config bytes.  The tool and its flat
    Tools Python runtime are descriptor-read once here, and both producer and
    consumer derive the same fingerprints from those exact bytes.  The
    producer executes materialized copies of the returned bytes; the consumer
    later rejects a receipt when the currently installed executable inputs no
    longer match what signed it.
    """
    command = tuple(profile_contract.compile_registered_scan_command(
        root, profile_view["_contract"], scan=scan))
    entrypoint = profile_contract.registered_scan_entrypoint(root, scan)
    if len(command) < 3:
        raise ValueError("registered scan compiled command is incomplete")
    expected_invocation = os.path.join(
        os.path.realpath(os.path.abspath(os.fspath(root))),
        *entrypoint.invocation_path.split("/"))
    if os.path.realpath(command[1]) != expected_invocation:
        raise ValueError(
            "registered scan command does not execute its public adapter")
    if any(token == "--receipts" or token.startswith("--receipts=") or
           token == "--json" for token in command):
        raise ValueError(
            "registered scan command contains Gate-owned output arguments")

    tool = kblib.repository_target_snapshot(
        root, scan.script_repo_path,
        suffixes=".py", singly_linked=True)
    if not tool.exists:
        raise ValueError("registered scan tool does not exist")
    invocation = kblib.repository_target_snapshot(
        root, entrypoint.invocation_path,
        suffixes=".py", singly_linked=True)
    if not invocation.exists:
        raise ValueError("registered scan invocation adapter does not exist")
    tools_tree = kblib.repository_tree_snapshot(root, "Tools")
    runtime_files = {
        path: data for path, data in tools_tree.files.items()
        if path.endswith(".py") and not path.startswith("Tools/tests/")
    }
    if not runtime_files:
        raise ValueError("registered scan has no frozen Tools Python runtime")
    runtime_tool = runtime_files.get(scan.script_repo_path)
    if runtime_tool is None or runtime_tool != tool.data:
        raise ValueError(
            "registered scan tool differs from its frozen Python runtime")
    runtime_invocation = runtime_files.get(entrypoint.invocation_path)
    if runtime_invocation is None or runtime_invocation != invocation.data:
        raise ValueError(
            "registered scan invocation adapter differs from its frozen "
            "Python runtime")
    runtime_records = [
        {"path": path,
         "sha256": kblib.sha256_bytes(runtime_files[path])}
        for path in sorted(runtime_files)
    ]
    python_runtime_sha256 = kblib.sha256_bytes(
        kblib.canonical_json_bytes({
            "protocol": "registered-scan-python-runtime-v1",
            "files": runtime_records,
        }))

    config_data = None
    config_sha256 = None
    config_suffix = None
    dependency = scan.config_dependency
    if dependency is not None:
        snapshot = profile_view.get("_profile_snapshot")
        if not isinstance(snapshot, kblib.RepositoryTreeSnapshot):
            raise ValueError(
                "authorized Profile view exposes no immutable scan-config "
                "bytes")
        try:
            config_data = snapshot.read_bytes(dependency.path)
        except (OSError, ValueError) as exc:
            raise ValueError(
                "registered scan config is absent from the authorized "
                "Profile snapshot: %s" % exc) from exc
        config_sha256 = kblib.sha256_bytes(config_data)
        config_suffix = Path(dependency.path).suffix or ".data"

    command_sha256 = kblib.sha256_bytes(kblib.canonical_json_bytes({
        "protocol": "registered-scan-v1",
        "argv": command,
    }))
    tool_sha256 = kblib.sha256_bytes(tool.data)
    invocation_sha256 = kblib.sha256_bytes(invocation.data)
    execution_input_sha256 = kblib.sha256_bytes(
        kblib.canonical_json_bytes({
            "protocol": "registered-scan-execution-input-v2",
            "command_sha256": command_sha256,
            "invocation_tool": entrypoint.tool,
            "invocation_path": entrypoint.invocation_path,
            "invocation_sha256": invocation_sha256,
            "implementation_path": scan.script_repo_path,
            "tool_sha256": tool_sha256,
            "config_sha256": config_sha256,
            "python_runtime_sha256": python_runtime_sha256,
        }))
    return {
        "command": command,
        "command_sha256": command_sha256,
        "tool_snapshot": tool,
        "tool_sha256": tool_sha256,
        "implementation_path": scan.script_repo_path,
        "invocation_tool": entrypoint.tool,
        "invocation_path": entrypoint.invocation_path,
        "invocation_snapshot": invocation,
        "invocation_sha256": invocation_sha256,
        "config_data": config_data,
        "config_sha256": config_sha256,
        "config_suffix": config_suffix,
        "python_runtime_files": runtime_files,
        "python_runtime_sha256": python_runtime_sha256,
        "execution_input_sha256": execution_input_sha256,
    }


def registered_scan_for_id(profile_view, scan_id):
    """Resolve one scan from the already-authorized typed Profile view."""
    contract = profile_view.get("_contract") \
        if isinstance(profile_view, dict) else None
    matches = [scan for scan in getattr(contract, "registered_scans", ())
               if scan.scan_id == scan_id]
    if len(matches) != 1:
        raise ValueError(
            "authorized Profile must resolve exactly one Registered Scan %s; "
            "found %d" % (scan_id, len(matches)))
    return matches[0]


def _write_read_only(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o444)


def _materialize_registered_scan_inputs(temporary, inputs):
    staged_root = os.path.join(temporary, "frozen-runtime")
    for relative, data in sorted(inputs["python_runtime_files"].items()):
        _write_read_only(
            os.path.join(staged_root, *relative.split("/")), data)
    script_path = os.path.join(
        staged_root, *inputs["invocation_path"].split("/"))
    if not os.path.isfile(script_path):
        raise ValueError(
            "registered scan invocation adapter is absent from frozen runtime")
    config_path = None
    if inputs["config_data"] is not None:
        config_path = os.path.join(
            temporary, "frozen-profile-input",
            "scan-config" + inputs["config_suffix"])
        _write_read_only(config_path, inputs["config_data"])
    return script_path, config_path


def _replace_registered_scan_config(command, config_path, expects_config):
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


def _read_registered_scan_receipts(path):
    records = []
    seen = set()
    try:
        with open(path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(
                        "line %d is not a JSON object" % line_number)
                receipt_id = record.get("receipt_id")
                if (not isinstance(receipt_id, str) or not receipt_id or
                        receipt_id in seen):
                    raise ValueError(
                        "line %d has missing or duplicate receipt_id" %
                        line_number)
                seen.add(receipt_id)
                records.append(record)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "registered scan receipts are unreadable: %s" % exc) from exc
    if not records:
        raise ValueError("registered scan produced no machine-readable receipt")
    return records


def validate_registered_scan_receipts(
        scan, records, exit_code, *, expected_tool,
        allowed_summary_results=("pass",)):
    """Validate one exact registered scan result without adding semantics."""
    allowed = tuple(allowed_summary_results)
    if (not allowed or len(allowed) != len(set(allowed)) or
            any(value not in {"pass", "candidate"} for value in allowed)):
        raise ValueError("registered scan allowed results are invalid")
    if (not isinstance(exit_code, int) or isinstance(exit_code, bool) or
            exit_code not in (0, 1, 2)):
        raise ValueError("registered scan returned an unregistered exit code")
    calculated = kblib.exit_code(records)
    if calculated != exit_code:
        raise ValueError(
            "registered scan exit code differs from its emitted receipt set")
    noncurrent = [record for record in records
                  if record.get("result") == "fail" or
                  record.get("invalidated_by") is not None]
    if noncurrent:
        raise ValueError(
            "registered scan emitted failed or invalidated evidence")
    if not isinstance(expected_tool, str) or not expected_tool:
        raise ValueError("registered scan expected public Tool is invalid")
    summary = records[-1]
    invalid = []
    for record in records:
        if record.get("scan_id") != scan.scan_id:
            invalid.append("scan_id")
        if record.get("tool") != expected_tool:
            invalid.append("tool")
        result = record.get("result")
        if result not in {"pass", "candidate"}:
            invalid.append("result")
        try:
            datetime.datetime.strptime(
                record.get("checked_at"), "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            invalid.append("checked_at")
    if invalid:
        raise ValueError(
            "registered scan receipt identity is invalid in: %s; expected "
            "the admitted scan %s and tool %s" %
            (", ".join(sorted(set(invalid))), scan.scan_id, expected_tool))
    expected_summary_result = "candidate" if exit_code == 2 else "pass"
    if (summary.get("result") != expected_summary_result or
            summary.get("result") not in allowed):
        if allowed == ("pass",):
            raise ValueError(
                "registered scan did not pass cleanly (exit %d)" % exit_code)
        raise ValueError(
            "registered scan summary result %r is not allowed" %
            summary.get("result"))
    return summary


def run_registered_scan(root, profile_view, scan, *,
                        allowed_summary_results=("pass",), timeout=60):
    """Execute one registered scan from immutable admitted inputs."""
    admitted = registered_scan_for_id(profile_view, scan.scan_id)
    if admitted is not scan:
        raise ValueError(
            "registered scan is not the admitted Profile instance")
    inputs = registered_scan_input_binding(root, profile_view, scan)
    command = list(inputs["command"])
    tool_before = inputs["tool_snapshot"]
    invocation_before = inputs["invocation_snapshot"]
    repository_before = kblib.repository_snapshot_sha256(root)
    scan_error = None
    completed = None
    records = None
    summary = None
    try:
        with tempfile.TemporaryDirectory(
                prefix="cambium-registered-scan-") as temporary:
            staged_script, staged_config = \
                _materialize_registered_scan_inputs(temporary, inputs)
            execution_command = list(command)
            execution_command[1] = staged_script
            execution_command = _replace_registered_scan_config(
                execution_command, staged_config,
                scan.config_dependency is not None)
            output_path = os.path.join(temporary, "receipts.jsonl")
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            environment.pop("PYTHONHOME", None)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONNOUSERSITE"] = "1"
            completed = kblib.run_cambium_subprocess(
                execution_command + ["--receipts", output_path],
                cwd=root, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=timeout, check=False)
            records = _read_registered_scan_receipts(output_path)
        summary = validate_registered_scan_receipts(
            scan, records, completed.returncode,
            expected_tool=inputs["invocation_tool"],
            allowed_summary_results=allowed_summary_results)
    except (OSError, subprocess.SubprocessError, TypeError,
            UnicodeError, ValueError) as exc:
        scan_error = exc
    repository_after = kblib.repository_snapshot_sha256(root)
    if repository_after != repository_before:
        raise ValueError(
            "repository changed while the registered scan was running") \
            from scan_error
    tool_after = kblib.repository_target_snapshot(
        root, scan.script_repo_path, suffixes=".py", singly_linked=True)
    if not repository.same_existing_target_snapshot(tool_before, tool_after):
        raise ValueError(
            "registered scan tool identity or bytes changed during execution") \
            from scan_error
    invocation_after = kblib.repository_target_snapshot(
        root, inputs["invocation_path"], suffixes=".py", singly_linked=True)
    if not repository.same_existing_target_snapshot(
            invocation_before, invocation_after):
        raise ValueError(
            "registered scan invocation adapter identity or bytes changed "
            "during execution") from scan_error
    inputs_after = registered_scan_input_binding(root, profile_view, scan)
    input_fields = (
        "command_sha256", "implementation_path", "tool_sha256",
        "invocation_tool", "invocation_path", "invocation_sha256",
        "config_sha256",
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
        "records": records,
        "exit_code": completed.returncode,
        "summary_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(summary)),
        "receipt_set_sha256": kblib.sha256_bytes(
            kblib.canonical_json_bytes(records)),
        "receipt_count": len(records),
        "command_sha256": inputs["command_sha256"],
        "implementation_path": inputs["implementation_path"],
        "tool_sha256": inputs["tool_sha256"],
        "invocation_tool": inputs["invocation_tool"],
        "invocation_path": inputs["invocation_path"],
        "invocation_sha256": inputs["invocation_sha256"],
        "config_sha256": inputs["config_sha256"],
        "python_runtime_sha256": inputs["python_runtime_sha256"],
        "execution_input_sha256": inputs["execution_input_sha256"],
        "repository_snapshot_sha256": repository_after,
        "output": completed.stdout,
    }


def validate_registered_scan_input_binding(
        root, profile_view, scan, record, *,
        expected_repository_snapshot=None, require_current_repository=False):
    """Rebind persisted registered-scan evidence to current inputs."""
    inputs = registered_scan_input_binding(root, profile_view, scan)
    mismatches = []
    for field, expected in (
            ("registered_scan_command_sha256", inputs["command_sha256"]),
            ("registered_scan_invocation_tool",
             inputs["invocation_tool"]),
            ("registered_scan_invocation_path",
             inputs["invocation_path"]),
            ("registered_scan_invocation_sha256",
             inputs["invocation_sha256"]),
            ("registered_scan_tool_sha256", inputs["tool_sha256"]),
            ("registered_scan_config_sha256", inputs["config_sha256"]),
            ("registered_scan_python_runtime_sha256",
             inputs["python_runtime_sha256"]),
            ("registered_scan_execution_input_sha256",
             inputs["execution_input_sha256"])):
        if record.get(field) != expected:
            mismatches.append(field)
    repository_value = record.get("repository_snapshot_sha256")
    if expected_repository_snapshot is not None and \
            repository_value != expected_repository_snapshot:
        mismatches.append("repository_snapshot_sha256")
    if require_current_repository and \
            repository_value != kblib.repository_snapshot_sha256(root):
        mismatches.append("repository_snapshot_sha256")
    if mismatches:
        raise ValueError(
            "registered scan evidence no longer matches current inputs in: %s"
            % ", ".join(sorted(set(mismatches))))
    return record


def require_admitted_runtime(runtime, *, allow_writer_lock=False):
    """Refuse a runtime observation that may not authorize a Gate decision.

    Running the admission is the facade's job; refusing its result is this
    module's.  The three refusals are kept in one place, and in the order
    they have always run, because the caller has to apply them before it
    builds the authority context: a runtime carrying errors must be reported
    as an invalid runtime, not as an unavailable authority context.
    """
    if not isinstance(runtime, dict):
        raise ValueError("runtime admission did not return a mapping")
    errors = runtime.get("errors") or []
    if errors:
        raise ValueError("current runtime is invalid: %s" % "; ".join(errors))
    if runtime.get("_writer_locks") and not allow_writer_lock:
        raise ValueError("runtime has an active or interrupted writer lock")
    return runtime


def require_paired_authority(runtime, authority):
    """Refuse an authority frozen from a different admission than ``runtime``.

    While this module derived the authority itself, the pairing was structural:
    the views could only come from the observation they were derived from.
    Taking both from the caller buys the one-way dependency at the cost of that
    guarantee, and the guarantee is not incidental -- the producer of this
    context exists to close a split-revision window, where a Profile view from
    one admission travels beside an active-Standards binding from another.

    Identity rather than equality is the right test here, and it is available:
    the producer passes both views out by reference from the result it read, so
    a pair that came from one admission shares those objects, and a pair
    assembled from two does not.  Equality would accept two admissions that
    merely happened to observe the same bytes -- which is the case this refuses
    to reason about, since the second observation was never admitted alongside
    this runtime.
    """
    for field, source in (
            ("profile_view", "_profile_authorized_view"),
            ("active_standards_view",
             "_active_standards_authorized_view"),
            ("metadata_execution_contract",
             "_metadata_execution_contract")):
        if authority.get(field) is not runtime.get(source):
            raise ValueError(
                "runtime authority was frozen from a different admission "
                "than the supplied runtime (%s)" % field)


def load_gate_context(root, gate_id, page_path, *, runtime, authority,
                      allow_writer_lock=False):
    """Load one current runtime/Profile/Gate/page authority observation.

    ``runtime`` and ``authority`` are the caller's own admitted observations:
    one ``check_queue.validate_runtime`` result and the
    ``check_queue.runtime_authority_context`` frozen from that same result.
    Both are mandatory, so a Gate decision cannot silently run against an
    admission this module fetched for itself.
    """
    canonical_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    require_admitted_runtime(runtime, allow_writer_lock=allow_writer_lock)
    if authority.get("root") != canonical_root:
        raise ValueError("runtime authority belongs to a different repository")
    require_paired_authority(runtime, authority)

    profile_view = authority.get("profile_view") or {}
    contract = profile_view.get("_contract")
    if contract is None or not getattr(contract, "authorized", False):
        raise ValueError("runtime exposes no authorized typed Profile contract")
    gate = _exact_gate(contract, gate_id)
    _require_capability_linkage(canonical_root, gate)

    metadata_contract = runtime_metadata_execution_contract(authority)
    rules = _projection_rules(metadata_contract, contract)
    page_snapshot = kblib.repository_target_snapshot(
        canonical_root, page_path, suffixes=".md", singly_linked=True)
    if not page_snapshot.exists:
        raise ValueError("Extension Gate target page does not exist")
    try:
        page_text = page_snapshot.read_text()
        semantic_fingerprint = \
            project_page_state.semantic_content_fingerprint(
                page_path, page_text, rules)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Extension Gate target page is invalid: %s" % exc)

    manifest = profile_view.get("selected_profile_manifest")
    manifest_snapshot = kblib.repository_file_snapshot(
        canonical_root, manifest, singly_linked=True)
    repository_snapshot_sha256 = kblib.repository_snapshot_sha256(
        canonical_root)
    return GateRuntimeContext(
        root=canonical_root,
        runtime=runtime,
        authority=authority,
        gate=gate,
        rules=rules,
        page_path=page_path,
        page_snapshot=page_snapshot,
        semantic_content_fingerprint=semantic_fingerprint,
        selected_profile_manifest_sha256=manifest_snapshot.sha256,
        metadata_contract_fingerprint=(
            metadata_contract.contract_fingerprint),
        repository_snapshot_sha256=repository_snapshot_sha256,
    )


def receipt_bindings(context, requested_value):
    """Return the closed Gate/profile/content binding shared by both CLIs."""
    gate = context.gate
    if requested_value not in gate.completion_values:
        raise ValueError(
            "completion value %r is not authorized by Gate %s (expected %s)" %
            (requested_value, gate.gate_id,
             ", ".join(gate.completion_values)))
    profile = context.profile_view
    active = context.active_standards_view
    return {
        "gate_id": gate.gate_id,
        "transition_id": gate.transition_id,
        "judgment_item_id": gate.judgment_item_id,
        "property_field": gate.field_id,
        "requested_completion_value": requested_value,
        "pass_authority_role_id": gate.pass_authority_role_id,
        "producer_kind": gate.producer_kind,
        "producer_capability": gate.producer_capability,
        "producer_reference": gate.producer_reference,
        "receipt_schema": gate.receipt_schema,
        "consumer_capability": gate.consumer_capability,
        "semantic_content_fingerprint": (
            context.semantic_content_fingerprint),
        "page_sha256": context.page_snapshot.sha256,
        "selected_profile_manifest": profile.get(
            "selected_profile_manifest"),
        "selected_profile_manifest_sha256": (
            context.selected_profile_manifest_sha256),
        "profile_snapshot_sha256": profile.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint": profile.get(
            "profile_contract_fingerprint"),
        "profile_load_inputs_sha256": profile.get(
            "profile_load_inputs_sha256"),
        "active_standards_sha256": active.get("active_standards_sha256"),
        "metadata_execution_contract_fingerprint": (
            context.metadata_contract_fingerprint),
    }


def validate_gate_receipt(context, receipt, requested_value, *,
                          require_current_repository=True,
                          allow_projected_page=False):
    """Validate one current-catalog receipt against the exact Gate context."""
    if not isinstance(receipt, dict):
        raise ValueError("Gate receipt must be a mapping")
    expected = receipt_bindings(context, requested_value)
    if allow_projected_page:
        expected.pop("page_sha256", None)
    expected.update({
        "check": MANUAL_GATE_PRODUCER_IDENTITY.check,
        "target": context.page_path,
        "result": "pass",
        "invalidated_by": None,
    })
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ValueError(
                "Gate receipt %s=%r, expected %r" %
                (field, receipt.get(field), value))
    if allow_projected_page:
        page_sha256 = receipt.get("page_sha256")
        if (not isinstance(page_sha256, str) or
                re.fullmatch(r"sha256:[0-9a-f]{64}", page_sha256) is None):
            raise ValueError(
                "persisted Gate receipt has invalid pre-projection page_sha256")
    checked_at = receipt.get("checked_at")
    try:
        datetime.datetime.strptime(
            checked_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Gate receipt checked_at must be canonical UTC") from exc
    if context.gate.producer_kind == "manual-attestation":
        if receipt.get("actor_role") != context.gate.pass_authority_role_id:
            raise ValueError(
                "manual Gate receipt actor_role is not the pass authority")
        if receipt.get("tool") != MANUAL_GATE_PRODUCER_IDENTITY.tool:
            raise ValueError(
                "manual Gate receipt was not produced by the registered "
                "attestation producer")
        if receipt.get("tool_version") != \
                MANUAL_GATE_PRODUCER_IDENTITY.tool_version:
            raise ValueError(
                "manual Gate receipt uses an unsupported producer protocol")
        statement = receipt.get("attestation_statement")
        if (not nonempty_string(statement) or
                receipt.get("details") != statement):
            raise ValueError(
                "manual Gate receipt has no exact bounded attestation")
    elif context.gate.producer_kind == "deterministic":
        if (receipt.get("tool") !=
                DETERMINISTIC_GATE_PRODUCER_IDENTITY.tool or
                receipt.get("tool_version") !=
                DETERMINISTIC_GATE_PRODUCER_IDENTITY.tool_version):
            raise ValueError(
                "deterministic Gate receipt was not produced by the "
                "registered-scan adapter protocol")
        if receipt.get("scan_id") != context.gate.producer_reference:
            raise ValueError(
                "deterministic Gate receipt does not name its registered scan")
        admitted_repository = context.repository_snapshot_sha256
        if allow_projected_page:
            repository_value = receipt.get("repository_snapshot_sha256")
            if (not isinstance(repository_value, str) or
                    re.fullmatch(
                        r"sha256:[0-9a-f]{64}", repository_value) is None):
                raise ValueError(
                    "persisted deterministic Gate receipt has invalid "
                    "pre-transition repository snapshot")
        else:
            if admitted_repository is None:
                admitted_repository = kblib.repository_snapshot_sha256(
                    context.root)
            if receipt.get(
                    "repository_snapshot_sha256") != admitted_repository:
                raise ValueError(
                    "deterministic Gate receipt repository snapshot does not "
                    "match the consumer's admitted scan input")
        if require_current_repository and not allow_projected_page:
            current_repository = kblib.repository_snapshot_sha256(
                context.root)
            if current_repository != admitted_repository:
                raise ValueError(
                    "repository changed after the deterministic Gate scan")
        source = receipt.get("registered_scan_receipt")
        if not isinstance(source, dict):
            raise ValueError(
                "deterministic Gate receipt has no embedded scan receipt")
        source_sha = kblib.sha256_bytes(kblib.canonical_json_bytes(source))
        if receipt.get("registered_scan_receipt_sha256") != source_sha:
            raise ValueError(
                "deterministic Gate embedded scan receipt hash is invalid")
        if (source.get("scan_id") != context.gate.producer_reference or
                source.get("result") != "pass" or
                source.get("invalidated_by") is not None):
            raise ValueError(
                "deterministic Gate embedded scan receipt is not its current "
                "registered pass")
        contract = context.profile_view.get("_contract")
        scans = [
            scan for scan in getattr(contract, "registered_scans", ())
            if scan.scan_id == context.gate.producer_reference
        ]
        if len(scans) != 1:
            raise ValueError(
                "deterministic Gate no longer resolves one registered scan")
        expected_tool = profile_contract.registered_scan_entrypoint(
            context.root, scans[0]).tool
        if source.get("tool") != expected_tool:
            raise ValueError(
                "deterministic Gate embedded scan receipt names the wrong "
                "tool")
        validate_registered_scan_input_binding(
            context.root, context.profile_view, scans[0], receipt)
        try:
            datetime.datetime.strptime(
                source.get("checked_at"), "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "deterministic Gate embedded scan checked_at is invalid") \
                from exc
        if not nonempty_string(source.get("receipt_id")):
            raise ValueError(
                "deterministic Gate embedded scan receipt has no receipt_id")
        for field in (
                "registered_scan_receipt_set_sha256",
                "repository_snapshot_sha256"):
            value = receipt.get(field)
            if (not isinstance(value, str) or
                    re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None):
                raise ValueError(
                    "deterministic Gate receipt has invalid %s" % field)
        count = receipt.get("registered_scan_receipt_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(
                "deterministic Gate receipt has invalid scan receipt count")
    else:
        raise ValueError("Extension Gate has an unsupported producer kind")
    receipt_id = receipt.get("receipt_id")
    if not nonempty_string(receipt_id):
        raise ValueError("Gate receipt has no receipt_id")
    return receipt


def current_gate_receipt(context, receipt_id, requested_value, *,
                         current_receipt_catalog,
                         require_current_repository=True):
    """Resolve only the filtered current receipt catalog, never history.

    The catalog is supplied by the caller as
    ``check_queue.current_receipt_catalog`` of the exact runtime observation
    carried by ``context``.  It is a pure projection of that already frozen
    result, so nothing here may reach past it into the historical catalog.
    """
    entry = current_receipt_catalog.get(receipt_id)
    if entry is None:
        raise ValueError(
            "Gate receipt %r is absent from the current receipt catalog" %
            receipt_id)
    receipt = entry[1]
    if receipt.get("receipt_id") != receipt_id:
        raise ValueError("Gate receipt catalog key differs from its record")
    return validate_gate_receipt(
        context, receipt, requested_value,
        require_current_repository=require_current_repository)


def validate_persisted_gate_owner(context, gate_receipt,
                                  transition_receipt, requested_value, *,
                                  invalidated_receipt_ids=()):
    """Validate the live owner graph after page-side projection.

    The producer's raw page/repository hashes describe the exact bytes before
    the Integrator projected the owner value.  They remain mandatory evidence
    but cannot equal the projected after-image.  The distinct transition
    receipt is therefore the unique bridge: it points back to the producer and
    binds those before hashes to the current owner/page after hashes, while the
    producer's semantic/Profile/tool/config/runtime bindings are revalidated
    through the same closed schema.
    """
    invalidated = set(invalidated_receipt_ids)
    gate_receipt_id = (gate_receipt.get("receipt_id")
                       if isinstance(gate_receipt, dict) else None)
    if gate_receipt_id in invalidated:
        raise ValueError(
            "Gate producer receipt is authoritatively invalidated")
    validate_gate_receipt(
        context, gate_receipt, requested_value,
        require_current_repository=False, allow_projected_page=True)
    if not isinstance(transition_receipt, dict):
        raise ValueError("persisted Gate owner has no Integrator receipt")
    expected = {
        "tool": METADATA_TRANSITION_PRODUCER_IDENTITY.tool,
        "tool_version": METADATA_TRANSITION_PRODUCER_IDENTITY.tool_version,
        "check": METADATA_TRANSITION_PRODUCER_IDENTITY.check,
        "target": context.page_path,
        "result": "pass",
        "invalidated_by": None,
        "actor_role": "integrator",
        "gate_id": context.gate.gate_id,
        "transition_id": context.gate.transition_id,
        "judgment_item_id": context.gate.judgment_item_id,
        "property_field": context.gate.field_id,
        "requested_completion_value": requested_value,
        "gate_receipt": gate_receipt_id,
        "gate_receipt_checked_at": gate_receipt.get("checked_at"),
        "semantic_content_fingerprint":
            context.semantic_content_fingerprint,
        "before_page_sha256": gate_receipt.get("page_sha256"),
        "after_page_sha256": context.page_snapshot.sha256,
        "metadata_execution_contract_fingerprint":
            context.metadata_contract_fingerprint,
    }
    bindings = receipt_bindings(context, requested_value)
    for field in (
            "pass_authority_role_id", "producer_kind",
            "producer_capability", "producer_reference", "receipt_schema",
            "consumer_capability", "selected_profile_manifest",
            "selected_profile_manifest_sha256", "profile_snapshot_sha256",
            "profile_contract_fingerprint", "profile_load_inputs_sha256",
            "active_standards_sha256"):
        expected[field] = bindings[field]
    if context.gate.producer_kind == "deterministic":
        expected["before_repository_snapshot_sha256"] = gate_receipt.get(
            "repository_snapshot_sha256")
    for field, value in expected.items():
        if transition_receipt.get(field) != value:
            raise ValueError(
                "Gate Integrator receipt %s=%r, expected %r" %
                (field, transition_receipt.get(field), value))
    transition_id = transition_receipt.get("receipt_id")
    if not nonempty_string(transition_id) or transition_id in invalidated:
        raise ValueError(
            "Gate Integrator receipt is missing or authoritatively invalidated")
    for field in (
            "before_coverage_sha256", "after_coverage_sha256",
            "before_required_queue_sha256", "after_required_queue_sha256",
            "before_progress_sha256", "after_progress_sha256",
            "before_page_sha256", "after_page_sha256",
            "before_repository_snapshot_sha256",
            "after_repository_snapshot_sha256"):
        value = transition_receipt.get(field)
        if (not isinstance(value, str) or
                re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None):
            raise ValueError(
                "Gate Integrator receipt has invalid %s" % field)
    if transition_receipt.get("after_coverage_sha256") != \
            context.runtime.get("coverage_sha256"):
        raise ValueError(
            "Gate Integrator receipt does not bind current Coverage bytes")
    if (transition_receipt.get("before_required_queue_sha256") !=
            transition_receipt.get("after_required_queue_sha256") or
            transition_receipt.get("before_progress_sha256") !=
            transition_receipt.get("after_progress_sha256")):
        raise ValueError(
            "Gate Integrator receipt changed Queue or Progress")
    return gate_receipt, transition_receipt


def require_authorities_current(context, phase, *, runtime=None):
    """CAS the Profile manifest and three Ledgers after shared authority CAS.

    The caller immediately runs the closed runtime-authority CAS before this
    function under the same ``phase`` label.  That CAS now includes the
    metadata contract as a Profile-load-covered derived authority, so opening
    the artifact again here would compare a second observation and repeat the
    whole implementation closure.  This local half retains only the exact
    manifest and mutable-ledger checks owned by the Gate context.
    """
    manifest = kblib.repository_file_snapshot(
        context.root, context.profile_view["selected_profile_manifest"],
        singly_linked=True)
    if manifest.sha256 != context.selected_profile_manifest_sha256:
        raise ValueError("%s: selected Profile manifest changed" % phase)
    if runtime is not None:
        for field in \
                runtime_state_contract.RUNTIME_LEDGER_FINGERPRINT_BY_ID.values():
            if runtime.get(field) != context.runtime.get(field):
                raise ValueError("%s: runtime %s changed" % (phase, field))


def require_context_current(context, phase, *, runtime=None):
    """CAS every authority and target first observed in ``context``."""
    require_authorities_current(context, phase, runtime=runtime)
    page = kblib.repository_target_snapshot(
        context.root, context.page_path, suffixes=".md", singly_linked=True)
    before = context.page_snapshot
    if (not page.exists or page.sha256 != before.sha256 or
            (page.dev, page.ino, page.mode, page.nlink) !=
            (before.dev, before.ino, before.mode, before.nlink)):
        raise ValueError("%s: target page identity or bytes changed" % phase)


__all__ = [
    'DETERMINISTIC_GATE_PRODUCER_IDENTITY',
    'GateRuntimeContext',
    'MANUAL_GATE_PRODUCER_IDENTITY',
    'METADATA_TRANSITION_PRODUCER_IDENTITY',
    'current_gate_receipt',
    'load_gate_context',
    'receipt_bindings',
    'require_admitted_runtime',
    'require_authorities_current',
    'require_context_current',
    'validate_gate_receipt',
]


def persisted_property_gate_errors(
        receipt, *, receipt_id, path, field, value, semantic_fingerprint,
        metadata_contract_fingerprint, profile_view,
        active_standards_view, gates_by_id, manifest_sha256, root,
        rules, current_catalog, coverage_sha256, projected_page_text=None):
    """Validate a current Profile Gate receipt after page-side projection.

    The producer receipt's exact ``page_sha256`` is its pre-projection page
    observation, so it remains a required fingerprint but is intentionally
    not compared with the current full page bytes.  The current semantic
    fingerprint *is* compared exactly; it excludes every field in the same
    composed rule set used by the projector.
    """
    label = "Coverage property_state.%s for %s" % (field, path)
    errors = []
    gate_id = receipt.get("gate_id")
    gate = gates_by_id.get(gate_id)
    if gate is None:
        return [
            "%s evidence receipt %s names Gate %r outside the authorized "
            "Profile contract" % (label, receipt_id, gate_id)]
    if gate.field_id != field or value not in gate.completion_values:
        errors.append(
            "%s value=%r is not authorized by receipt Gate %s" %
            (label, value, gate_id))
    expected = {
        "check": MANUAL_GATE_PRODUCER_IDENTITY.check,
        "target": path,
        "result": "pass",
        "invalidated_by": None,
        "gate_id": gate.gate_id,
        "transition_id": gate.transition_id,
        "judgment_item_id": gate.judgment_item_id,
        "property_field": gate.field_id,
        "requested_completion_value": value,
        "pass_authority_role_id": gate.pass_authority_role_id,
        "producer_kind": gate.producer_kind,
        "producer_capability": gate.producer_capability,
        "producer_reference": gate.producer_reference,
        "receipt_schema": gate.receipt_schema,
        "consumer_capability": gate.consumer_capability,
        "semantic_content_fingerprint": semantic_fingerprint,
        "selected_profile_manifest_sha256": manifest_sha256,
        "active_standards_sha256":
            (active_standards_view or {}).get("active_standards_sha256"),
    }
    for name, expected_value in expected.items():
        if receipt.get(name) != expected_value:
            errors.append(
                "%s evidence receipt %s has %s=%r, expected %r" %
                (label, receipt_id, name, receipt.get(name), expected_value))
    errors.extend(evidence_identity_errors(
        receipt, label, use=EVIDENCE_USE_CURRENT_AUTHORIZATION,
        profile_view=profile_view,
        metadata_contract_fingerprint=metadata_contract_fingerprint))
    if (not isinstance(receipt.get("page_sha256"), str) or
            not SHA256_RE.fullmatch(receipt["page_sha256"])):
        errors.append("%s evidence receipt has invalid page_sha256" % label)
    property_receipt_utc_date(receipt, label, errors)
    if gate.producer_kind == "manual-attestation":
        if (receipt.get("tool") != MANUAL_GATE_PRODUCER_IDENTITY.tool or
                receipt.get("tool_version") !=
                MANUAL_GATE_PRODUCER_IDENTITY.tool_version):
            errors.append(
                "%s manual evidence was not emitted by the registered "
                "producer protocol" % label)
        if receipt.get("actor_role") != gate.pass_authority_role_id:
            errors.append(
                "%s manual evidence actor is not the Gate pass authority" %
                label)
        statement = receipt.get("attestation_statement")
        if (not nonempty_string(statement) or
                receipt.get("details") != statement):
            errors.append(
                "%s manual evidence has no exact bounded attestation" %
                label)
    elif gate.producer_kind == "deterministic":
        if (receipt.get("tool") !=
                DETERMINISTIC_GATE_PRODUCER_IDENTITY.tool or
                receipt.get("tool_version") !=
                DETERMINISTIC_GATE_PRODUCER_IDENTITY.tool_version):
            errors.append(
                "%s deterministic evidence was not emitted by the "
                "registered-scan adapter protocol" % label)
        if receipt.get("scan_id") != gate.producer_reference:
            errors.append(
                "%s deterministic evidence does not name its registered "
                "scan" % label)
    else:
        errors.append("%s Gate has unsupported producer kind" % label)
    transition_matches = []
    for candidate_id, entry in current_catalog.items():
        candidate = (entry[1] if isinstance(entry, tuple) and len(entry) == 2
                     else None)
        if (isinstance(candidate, dict) and
                candidate.get("tool") ==
                METADATA_TRANSITION_PRODUCER_IDENTITY.tool and
                candidate.get("tool_version") ==
                METADATA_TRANSITION_PRODUCER_IDENTITY.tool_version and
                candidate.get("check") ==
                METADATA_TRANSITION_PRODUCER_IDENTITY.check and
                candidate.get("gate_receipt") == receipt_id and
                candidate.get("target") == path and
                candidate.get("property_field") == field):
            transition_matches.append((candidate_id, candidate))
    if len(transition_matches) != 1:
        errors.append(
            "%s evidence receipt %s must resolve exactly one current "
            "Integrator transition receipt; found %d" %
            (label, receipt_id, len(transition_matches)))
        return errors
    try:
        page_snapshot = kblib.repository_target_snapshot(
            root, path, suffixes=(".md", ".MD"), singly_linked=True)
        if not page_snapshot.exists:
            raise ValueError("persisted Gate owner target page is absent")
        page_binding = page_snapshot
        if projected_page_text is not None:
            page_binding = SimpleNamespace(sha256=kblib.sha256_bytes(
                projected_page_text.encode("utf-8")))
        context = GateRuntimeContext(
            root=os.path.realpath(os.path.abspath(root)),
            runtime={"coverage_sha256": coverage_sha256},
            authority={
                "root": os.path.realpath(os.path.abspath(root)),
                "profile_view": profile_view,
                "active_standards_view": active_standards_view or {},
            },
            gate=gate, rules=tuple(rules), page_path=path,
            page_snapshot=page_binding,
            semantic_content_fingerprint=semantic_fingerprint,
            selected_profile_manifest_sha256=manifest_sha256,
            metadata_contract_fingerprint=metadata_contract_fingerprint,
            repository_snapshot_sha256=None,
        )
        validate_persisted_gate_owner(
            context, receipt, transition_matches[0][1], value)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        errors.append(
            "%s persisted producer/Integrator evidence graph is invalid: %s" %
            (label, exc))
    return errors
