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
"""

from dataclasses import dataclass
import datetime
import os
from pathlib import Path
import re

import check_queue
import kblib
import metadata_execution_contract
import metadata_property_state
import profile_contract
import project_page_state


CONSUMER_OPERATION = "typed-field-metadata-transition"
GATE_CHECK = "profile-extension-gate"


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


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


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


def synthetic_projection_rule(gate, *, allowed_values=None):
    """Derive the sole generic rule shape authorized by an Extension Gate.

    The field and enum are not supplied by the caller.  They are taken from
    the authorized typed Gate, while the owner, source adapter and write
    protocol remain fixed by Cambium Core.
    """
    if not _nonempty(getattr(gate, "field_id", None)):
        raise ValueError("Extension Gate has no Vocabulary field")
    values = (getattr(gate, "completion_values", ())
              if allowed_values is None else allowed_values)
    return metadata_property_state.gate_projection_rule(
        gate.field_id, values)


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


def deterministic_scan_input_binding(context, scan):
    """Freeze the executable inputs for one registered deterministic Gate.

    The Profile snapshot already owns config bytes.  The tool and its flat
    Tools Python runtime are descriptor-read once here, and both producer and
    consumer derive the same fingerprints from those exact bytes.  The
    producer executes materialized copies of the returned bytes; the consumer
    later rejects a receipt when the currently installed executable inputs no
    longer match what signed it.
    """
    command = tuple(profile_contract.compile_registered_scan_command(
        context.root, context.profile_view["_contract"], scan=scan))
    if len(command) < 3:
        raise ValueError("registered scan compiled command is incomplete")
    if any(token == "--receipts" or token.startswith("--receipts=") or
           token == "--json" for token in command):
        raise ValueError(
            "registered scan command contains Gate-owned output arguments")

    tool = kblib.repository_target_snapshot(
        context.root, scan.script_repo_path,
        suffixes=".py", singly_linked=True)
    if not tool.exists:
        raise ValueError("registered scan tool does not exist")
    tools_tree = kblib.repository_tree_snapshot(context.root, "Tools")
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
    dependency = scan.config_dependency
    if dependency is not None:
        snapshot = context.profile_view.get("_profile_snapshot")
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

    command_sha256 = kblib.sha256_bytes(kblib.canonical_json_bytes({
        "protocol": "registered-scan-v1",
        "argv": command,
    }))
    tool_sha256 = kblib.sha256_bytes(tool.data)
    execution_input_sha256 = kblib.sha256_bytes(
        kblib.canonical_json_bytes({
            "protocol": "registered-scan-execution-input-v1",
            "command_sha256": command_sha256,
            "tool_sha256": tool_sha256,
            "config_sha256": config_sha256,
            "python_runtime_sha256": python_runtime_sha256,
        }))
    return {
        "command": command,
        "command_sha256": command_sha256,
        "tool_snapshot": tool,
        "tool_sha256": tool_sha256,
        "config_data": config_data,
        "config_sha256": config_sha256,
        "python_runtime_files": runtime_files,
        "python_runtime_sha256": python_runtime_sha256,
        "execution_input_sha256": execution_input_sha256,
    }


def load_gate_context(root, gate_id, page_path, *, runtime=None,
                      authority=None, allow_writer_lock=False):
    """Load one current runtime/Profile/Gate/page authority observation."""
    canonical_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if runtime is None:
        runtime = check_queue.validate_runtime(canonical_root)
    if not isinstance(runtime, dict):
        raise ValueError("runtime admission did not return a mapping")
    errors = runtime.get("errors") or []
    if errors:
        raise ValueError("current runtime is invalid: %s" % "; ".join(errors))
    if runtime.get("writer_locks") and not allow_writer_lock:
        raise ValueError("runtime has an active or interrupted writer lock")
    if authority is None:
        authority = check_queue.runtime_authority_context(runtime)
    if authority.get("root") != canonical_root:
        raise ValueError("runtime authority belongs to a different repository")

    profile_view = authority.get("profile_view") or {}
    contract = profile_view.get("_contract")
    if contract is None or not getattr(contract, "authorized", False):
        raise ValueError("runtime exposes no authorized typed Profile contract")
    gate = _exact_gate(contract, gate_id)
    _require_capability_linkage(canonical_root, gate)

    metadata_contract = \
        metadata_execution_contract.load_metadata_execution_contract(
            canonical_root)
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
        "check": GATE_CHECK,
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
        if receipt.get("tool") != "record_gate_attestation":
            raise ValueError(
                "manual Gate receipt was not produced by the registered "
                "attestation producer")
        if receipt.get("tool_version") != "1.0.0":
            raise ValueError(
                "manual Gate receipt uses an unsupported producer protocol")
        statement = receipt.get("attestation_statement")
        if (not _nonempty(statement) or
                receipt.get("details") != statement):
            raise ValueError(
                "manual Gate receipt has no exact bounded attestation")
    elif context.gate.producer_kind == "deterministic":
        if receipt.get("tool") != "record_gate_result" or \
                receipt.get("tool_version") != "1.0.0":
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
        expected_tool = Path(scans[0].script_repo_path).stem
        if source.get("tool") != expected_tool:
            raise ValueError(
                "deterministic Gate embedded scan receipt names the wrong "
                "tool")
        inputs = deterministic_scan_input_binding(context, scans[0])
        for field, expected_value in (
                ("registered_scan_command_sha256",
                 inputs["command_sha256"]),
                ("registered_scan_tool_sha256", inputs["tool_sha256"]),
                ("registered_scan_config_sha256", inputs["config_sha256"]),
                ("registered_scan_python_runtime_sha256",
                 inputs["python_runtime_sha256"]),
                ("registered_scan_execution_input_sha256",
                 inputs["execution_input_sha256"])):
            if receipt.get(field) != expected_value:
                raise ValueError(
                    "deterministic Gate receipt %s no longer matches its "
                    "authorized executable input" % field)
        try:
            datetime.datetime.strptime(
                source.get("checked_at"), "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "deterministic Gate embedded scan checked_at is invalid") \
                from exc
        if not _nonempty(source.get("receipt_id")):
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
    if not _nonempty(receipt_id):
        raise ValueError("Gate receipt has no receipt_id")
    return receipt


def current_gate_receipt(context, receipt_id, requested_value, *,
                         require_current_repository=True):
    """Resolve only the filtered current receipt catalog, never history."""
    catalog = check_queue.current_receipt_catalog(context.runtime)
    entry = catalog.get(receipt_id)
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
        "tool": "apply_metadata_transition",
        "tool_version": "1.0.0",
        "check": "metadata-transition",
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
    if not _nonempty(transition_id) or transition_id in invalidated:
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
    """CAS Profile, K00, metadata-contract and the three runtime Ledgers."""
    check_queue.require_runtime_authority_current(
        context.root, context.authority, phase)
    metadata_contract = \
        metadata_execution_contract.load_metadata_execution_contract(
            context.root)
    if metadata_contract.contract_fingerprint != \
            context.metadata_contract_fingerprint:
        raise ValueError("%s: metadata execution contract changed" % phase)
    manifest = kblib.repository_file_snapshot(
        context.root, context.profile_view["selected_profile_manifest"],
        singly_linked=True)
    if manifest.sha256 != context.selected_profile_manifest_sha256:
        raise ValueError("%s: selected Profile manifest changed" % phase)
    if runtime is not None:
        for field in ("coverage_sha256", "queue_sha256", "progress_sha256"):
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
    "CONSUMER_OPERATION", "GATE_CHECK", "GateRuntimeContext",
    "current_gate_receipt", "deterministic_scan_input_binding",
    "load_gate_context", "receipt_bindings",
    "require_authorities_current", "require_context_current",
    "synthetic_projection_rule",
    "validate_gate_receipt", "validate_persisted_gate_owner",
]
