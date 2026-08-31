#!/usr/bin/env python3
"""Current adopter Standards state to canonical adoption-evidence contract.

K00/03 owns the governance semantics: adopter state names one latest adoption
and the append-only Standards-adoption stream is the canonical history.  This
module is the single machine interpreter of that link.  It does not decide an
adoption, migrate history, or infer a missing receipt; it proves that the
current state is the after-image of one registered current producer and that
the adopted Profile fingerprints still name the admitted Profile bytes.
"""

import json
import os
import re

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.governance.control import control_registry_contract
import Tools.governance.profile.profile_contract as profile_contract


PROFILE_ADOPTION_TOOL = "apply_profile_adoption"
PROFILE_ADOPTION_TOOL_VERSION = "3.0.0"
STANDARDS_ADOPTION_TOOL = "adopt_standards"
STANDARDS_ADOPTION_TOOL_VERSION = "2.0.0"
PROFILE_LOAD_GATE_ID = profile_contract.PROFILE_LOAD_GATE_ID
STANDARDS_ADOPTION_GATE_ID = "standards-adoption"
PROFILE_ADOPTION_RECEIPT_TYPE_ID = "profile-adoption-receipt-v1"
STANDARDS_ADOPTION_RECEIPT_TYPE_ID = "standards-adoption-receipt-v1"
ADOPTION_RECEIPT_PATH = runtime_paths.STANDARDS_ADOPTION_RECEIPT_PATH
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


# Exact producer tuples authorized to establish the current adopter
# after-image. Current and historical catalogs accept this one contract only;
# an external archive containing retired formats is outside Cambium runtime.
CURRENT_PRODUCERS = {
    (PROFILE_ADOPTION_TOOL, PROFILE_ADOPTION_TOOL_VERSION): {
        "kind": "profile-adoption",
        "check": "profile_adoption",
        "state_sha256_field": "standards_state_sha256_after",
    },
    (STANDARDS_ADOPTION_TOOL, STANDARDS_ADOPTION_TOOL_VERSION): {
        "kind": "active-task-standards-adoption",
        "check": "standards_adoption",
        "state_sha256_field": "after_standards_state_sha256",
    },
}


def current_profile_adoption_receipt_errors(record, *, root=None):
    """Validate the current no-task Profile-adoption Receipt envelope."""
    return receipt_type_contract.base_receipt_errors(
        record,
        receipt_type_id=PROFILE_ADOPTION_RECEIPT_TYPE_ID,
        tool=PROFILE_ADOPTION_TOOL,
        tool_version=PROFILE_ADOPTION_TOOL_VERSION,
        checks="profile_adoption",
    )


def current_standards_adoption_receipt_errors(record, *, root=None):
    """Validate the current active-task Standards-adoption Receipt."""
    errors = receipt_type_contract.base_receipt_errors(
        record,
        receipt_type_id=STANDARDS_ADOPTION_RECEIPT_TYPE_ID,
        tool=STANDARDS_ADOPTION_TOOL,
        tool_version=STANDARDS_ADOPTION_TOOL_VERSION,
        checks="standards_adoption",
    )
    if isinstance(record, dict) and \
            record.get("gate_id") != STANDARDS_ADOPTION_GATE_ID:
        errors.append("gate_id must identify the standards-adoption Gate")
    return errors

# Profile load owns the durable typed-identity field set.  Adoption receipts
# carry the same fields as after-image bindings, so this projection must be
# derived rather than maintained as a second three-field contract.
PROFILE_BINDINGS = tuple(
    ("%s_after" % field, field)
    for field in profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS
)


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _catalog_entry(catalog, receipt_id):
    """Return one hot ``(path, body)`` catalog entry.

    Current adopter authority is a live-state dependency.  A sealed body is
    valid historical evidence, but it cannot silently become the current
    authority merely because a Catalog can resolve it from cold storage.
    """
    entry = catalog.get(receipt_id) if hasattr(catalog, "get") else None
    if (not isinstance(entry, tuple) or len(entry) != 2 or
            not isinstance(entry[0], str) or
            not isinstance(entry[1], dict)):
        return None
    return entry


def _is_cold_reference(catalog, receipt_id):
    cold = getattr(catalog, "cold", None)
    return isinstance(cold, dict) and receipt_id in cold


def _profile_load_gate_identity(root):
    """Resolve the exact current profile-load producer from K00/12."""
    if root is None:
        return None, [
            "profile-load Gate identity requires the adopting repository root"]
    registry, _capabilities, _metadata, errors = \
        control_registry_contract.load_current_control_contract(root)
    if errors:
        return None, [
            "current Control Registry is invalid: %s" % error
            for error in errors
        ]
    gate = registry.get(PROFILE_LOAD_GATE_ID)
    if not isinstance(gate, dict):
        return None, [
            "current Control Registry has no %s Gate" % PROFILE_LOAD_GATE_ID]
    return {
        "tool": gate.get("tool"),
        "tool_version": gate.get("tool_version"),
        "check": gate.get("check"),
        "gate_id": PROFILE_LOAD_GATE_ID,
        "dimensions": gate.get("dimensions"),
    }, []


def load_adoption_history(root):
    """Load the canonical hot adoption stream for pre-task consumers.

    Runtime consumers should pass their already integrity-checked Receipt
    Catalog to :func:`current_lineage_errors`.  Pre-task consumers have no
    runtime catalog yet, so this reader snapshots exactly the one K00/03
    history owner.  The current adoption is a live state reference and must
    remain materialized in this stream; sealing policy therefore treats it as
    a hot root rather than making every pre-task consumer understand cold
    storage internals.
    """
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    errors = []
    catalog = {}
    try:
        snapshot = kblib.repository_file_snapshot(
            root, ADOPTION_RECEIPT_PATH, singly_linked=True)
        text = snapshot.read_text()
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, [
            "canonical adoption history %s is unsafe, absent, or unreadable: "
            "%s" % (ADOPTION_RECEIPT_PATH, exc)]
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                "canonical adoption history %s:%d is malformed: %s" %
                (ADOPTION_RECEIPT_PATH, line_number, exc))
            continue
        if not isinstance(record, dict):
            errors.append(
                "canonical adoption history %s:%d must be a JSON object" %
                (ADOPTION_RECEIPT_PATH, line_number))
            continue
        receipt_id = record.get("receipt_id")
        if not _nonempty_string(receipt_id):
            errors.append(
                "canonical adoption history %s:%d has no receipt_id" %
                (ADOPTION_RECEIPT_PATH, line_number))
            continue
        if receipt_id in catalog:
            errors.append(
                "canonical adoption history repeats receipt_id %s" %
                receipt_id)
            continue
        admission_errors = []
        for lifecycle in ("hot", "historical"):
            admission_errors.extend(
                "%s: %s" % (lifecycle, error)
                for error in receipt_type_contract.current_receipt_errors(
                    record, lifecycle, root=root))
        if admission_errors:
            errors.extend(
                "canonical adoption history %s:%d is not a current-contract "
                "Receipt: %s" %
                (ADOPTION_RECEIPT_PATH, line_number, error)
                for error in admission_errors)
            continue
        catalog[receipt_id] = (ADOPTION_RECEIPT_PATH, record)
    return catalog, errors


def _binding_errors(receipt, active_view, profile_evidence, spec):
    errors = []
    for receipt_field, view_field in (
            ("upstream_revision_id_after", "upstream_revision_id"),
            ("selected_profile_manifest_after",
             "selected_profile_manifest"),
            ("standards_effective_date_after",
             "standards_effective_date"),
            ("upstream_source_ref", "upstream_source_ref"),
            (spec["state_sha256_field"], "active_standards_sha256")):
        if receipt.get(receipt_field) != active_view.get(view_field):
            errors.append(
                "latest adoption receipt %s does not bind current adopter "
                "state %s" % (receipt_field, view_field))
    if profile_evidence is not None:
        if not isinstance(profile_evidence, dict):
            errors.append("authorized Profile evidence must be a mapping")
        else:
            for receipt_field, evidence_field in PROFILE_BINDINGS:
                expected = profile_evidence.get(evidence_field)
                if (not isinstance(expected, str) or
                        SHA256_RE.fullmatch(expected) is None):
                    errors.append(
                        "authorized Profile evidence %s is invalid" %
                        evidence_field)
                elif receipt.get(receipt_field) != expected:
                    errors.append(
                        "latest adoption receipt %s does not bind current "
                        "authorized Profile %s" %
                        (receipt_field, evidence_field))
    return errors


def _profile_adoption_chain_errors(catalog, receipt, active_view,
                                   profile_evidence, root):
    errors = []
    gate_identity, identity_errors = _profile_load_gate_identity(root)
    errors.extend(identity_errors)
    if receipt.get("profile_load_gate_id") != PROFILE_LOAD_GATE_ID:
        errors.append(
            "profile-adoption receipt must consume the profile-load Gate")
    gate_id = receipt.get("profile_load_receipt_id")
    if not _nonempty_string(gate_id):
        errors.append(
            "profile-adoption receipt has no profile_load_receipt_id")
        return errors
    entry = _catalog_entry(catalog, gate_id)
    if entry is None:
        if _is_cold_reference(catalog, gate_id):
            errors.append(
                "profile-adoption receipt names cold profile-load evidence "
                "%s; current authority must remain hot" % gate_id)
        else:
            errors.append(
                "profile-adoption receipt names missing profile-load evidence "
                "%s" % gate_id)
        return errors
    path, gate = entry
    if path != ADOPTION_RECEIPT_PATH:
        errors.append(
            "profile-load evidence %s is outside canonical adoption history"
            % gate_id)
    expected_fields = {
        "result": "pass",
        "invalidated_by": None,
        "selected_profile_manifest":
            active_view.get("selected_profile_manifest"),
    }
    if gate_identity is not None:
        expected_fields.update({
            field: expected for field, expected in gate_identity.items()
            if field != "dimensions"
        })
    for field, expected in expected_fields.items():
        if gate.get(field) != expected:
            errors.append(
                "profile-load evidence %s has %s=%r, expected %r" %
                (gate_id, field, gate.get(field), expected))
    if gate_identity is not None:
        dimensions = gate_identity.get("dimensions") or ()
        if (control_registry_contract.UNNARROWED_GATE_DIMENSION not in
                dimensions and gate.get("dimension") not in dimensions):
            errors.append(
                "profile-load evidence %s has dimension=%r, expected one of "
                "%r" % (gate_id, gate.get("dimension"), dimensions))
    if profile_evidence is not None and isinstance(profile_evidence, dict):
        for _receipt_field, evidence_field in PROFILE_BINDINGS:
            if gate.get(evidence_field) != profile_evidence.get(evidence_field):
                errors.append(
                    "profile-load evidence %s does not bind current %s" %
                    (gate_id, evidence_field))
    return errors


def current_lineage_errors(active_view, *, profile_evidence=None,
                           catalog=None, root=None,
                           pending_receipt_id=None):
    """Validate the complete current-state adoption evidence chain.

    ``active_view`` is the immutable projection returned by
    ``standards_state.snapshot``.  ``profile_evidence`` is the public portion
    of one already-authorized ``profile-load`` view.  The function reads no
    Profile or task state itself, so callers cannot accidentally pair a
    verdict from one snapshot with another snapshot's bytes.  A transaction
    may name exactly one not-yet-appended Receipt through
    ``pending_receipt_id``.  That exception applies only when the catalog
    marks the same ID with the explicit ``<pending-write>`` sentinel; a
    boolean permission or an arbitrary noncanonical path is never enough.
    """
    if not isinstance(active_view, dict):
        return ["authorized active Standards view must be a mapping"]
    errors = []
    if (pending_receipt_id is not None and
            not _nonempty_string(pending_receipt_id)):
        errors.append(
            "pending adoption receipt identity must be a non-empty string")
    if catalog is None:
        if root is None:
            return ["current adoption lineage requires catalog or root"]
        catalog, load_errors = load_adoption_history(root)
        errors.extend(load_errors)
    receipt_id = active_view.get("latest_adoption_receipt")
    if not _nonempty_string(receipt_id):
        errors.append(
            "current adopter state has no latest adoption receipt identity")
        return errors
    entry = _catalog_entry(catalog, receipt_id)
    if entry is None:
        if _is_cold_reference(catalog, receipt_id):
            errors.append(
                "current adopter state names cold latest adoption receipt %s; "
                "current authority must remain hot" % receipt_id)
        else:
            errors.append(
                "current adopter state names missing latest adoption receipt %s"
                % receipt_id)
        return errors
    path, receipt = entry
    pending_entry = (
        path == "<pending-write>" and
        _nonempty_string(pending_receipt_id) and
        receipt_id == pending_receipt_id
    )
    if path != ADOPTION_RECEIPT_PATH and not pending_entry:
        errors.append(
            "latest adoption receipt %s is outside canonical adoption "
            "history" % receipt_id)
    producer = (receipt.get("tool"), receipt.get("tool_version"))
    spec = CURRENT_PRODUCERS.get(producer)
    if spec is None:
        errors.append(
            "latest adoption receipt %s has unregistered producer %r/%r"
            % (receipt_id, producer[0], producer[1]))
        return errors
    for field, expected in (
            ("check", spec["check"]),
            ("result", "pass"),
            ("invalidated_by", None)):
        if receipt.get(field) != expected:
            errors.append(
                "latest adoption receipt %s has %s=%r, expected %r" %
                (receipt_id, field, receipt.get(field), expected))
    errors.extend(_binding_errors(
        receipt, active_view, profile_evidence, spec))
    if spec["kind"] == "profile-adoption":
        errors.extend(_profile_adoption_chain_errors(
            catalog, receipt, active_view, profile_evidence, root))
    else:
        for field, expected in (
                ("gate_id", STANDARDS_ADOPTION_GATE_ID),
                ("transaction_phase", "commit"),
                ("actor_role", "integrator")):
            if receipt.get(field) != expected:
                errors.append(
                    "active-task adoption receipt %s has %s=%r, expected %r"
                    % (receipt_id, field, receipt.get(field), expected))
    return errors


__all__ = [
    'ADOPTION_RECEIPT_PATH',
    'PROFILE_ADOPTION_TOOL',
    'PROFILE_ADOPTION_TOOL_VERSION',
    'STANDARDS_ADOPTION_TOOL',
    'STANDARDS_ADOPTION_TOOL_VERSION',
    'current_lineage_errors',
    'load_adoption_history',
]
