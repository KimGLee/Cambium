#!/usr/bin/env python3
"""The sole complete profile-load Gate evaluator for a structured Profile.

The Profile linker reads one profile.toml, validates its Kernel-owned CUE
contract and typed references, and exposes immutable slot values. This module
binds that result to the canonical metadata execution contract and stable
Profile/Kernel snapshots, checks runtime capability and override semantics,
and emits the registered Gate evidence only for one complete evaluation.

Draft inspection belongs to profile_contract.load_profile_draft; it never
produces this Gate's pass evidence or admits a runtime consumer.
"""
from Tools.platform.repository.repository import repository_source_root

from collections.abc import Mapping
import contextlib
from dataclasses import dataclass
import io
import json
import os
import re
import sys
from types import MappingProxyType
from typing import Optional, Tuple

import Tools.governance.control.control_registry_contract as control_registry_contract
import Tools.governance.control.contract_exception_policy as contract_exception_policy
import Tools.execution.planning.corpus_planning_contract as corpus_planning_contract
import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.profile.rendering_contract as rendering_contract
import Tools.governance.profile.profile_layout_contract as profile_layout_contract

TOOL = "check_profile"
TOOL_VERSION = "2.2.0"
GATE_ID = profile_contract.PROFILE_LOAD_GATE_ID
GATE_CHECK = "profile-check-summary"
GATE_DIMENSION = "guidance_and_contract"
GATE_RECEIPT_TYPE_ID = "profile-load-gate-receipt-v1"
DIAGNOSTIC_RECEIPT_TYPE_ID = "profile-load-diagnostic-receipt-v1"


def current_gate_receipt_errors(record, *, root=None):
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=GATE_RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=GATE_CHECK)
    if isinstance(record, dict):
        if record.get("gate_id") != GATE_ID:
            errors.append("gate_id must identify profile-load")
        if record.get("dimension") != GATE_DIMENSION:
            errors.append("dimension must identify guidance_and_contract")
    return errors


def current_diagnostic_receipt_errors(record, *, root=None):
    """Validate a non-authorizing diagnostic emitted by check_profile."""
    check = record.get("check") if isinstance(record, dict) else None
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=DIAGNOSTIC_RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION,
        checks=check if isinstance(check, str) and check != GATE_CHECK else ())
    if isinstance(record, dict):
        if record.get("gate_id") != GATE_ID:
            errors.append("gate_id must identify profile-load")
        if record.get("dimension") != GATE_DIMENSION:
            errors.append("dimension must identify guidance_and_contract")
    return errors

# ``None`` has a public meaning for :func:`evaluate_profile_load`: omit Queue
# identity from the in-memory receipts.  The CLI still needs its historical
# behaviour of reading live identity from ``--root``, so an internal sentinel
# distinguishes that default from an explicit identity-free evaluation.
_LIVE_RUNTIME_RECEIPT_IDENTITY = object()


@dataclass(frozen=True)
class ProfileLoadEvaluation:
    """One complete, in-memory evaluation of the ``profile-load`` Gate.

    ``contract`` and ``metadata_execution_contract`` are exposed only when the
    same invocation emitted the passing Gate summary.  Consumers therefore
    cannot accidentally authorize a typed Profile from one observation beside
    metadata rules from another, or consume either object from a
    fail/candidate evaluation.  ``findings`` contains only non-pass receipts;
    the authoritative pass receipt, when present, is available separately as
    ``summary_receipt``.
    """

    exit_code: int
    findings: Tuple[dict, ...]
    contract: Optional[profile_contract.ProfileContract]
    metadata_execution_contract: Optional[
        metadata_execution_contract.CompiledMetadataExecutionContract]
    profile_id: Optional[str]
    profile_snapshot_sha256: Optional[str]
    profile_contract_fingerprint: Optional[str]
    execution_default_overrides: Tuple[Tuple[str, object], ...]
    profile_snapshot: Optional[object]
    profile_load_inputs_sha256: Optional[str]
    summary_receipt: Optional[dict]
    output: str
    normative_snapshots: Optional[Mapping] = None

    @property
    def authorized(self):
        complete = (
            self.exit_code == 0 and
            isinstance(self.contract, profile_contract.ProfileContract) and
            self.contract.valid and
            isinstance(self.metadata_execution_contract,
                       metadata_execution_contract.CompiledMetadataExecutionContract) and
            self.profile_id is not None and
            self.summary_receipt is not None and
            self.profile_snapshot_sha256 is not None and
            self.profile_contract_fingerprint is not None and
            self.profile_load_inputs_sha256 is not None
            and isinstance(self.normative_snapshots, Mapping)
            and bool(self.normative_snapshots)
        )
        if not complete or not isinstance(self.summary_receipt, dict):
            return False
        return (
            not self.findings and
            isinstance(self.profile_snapshot, kblib.RepositoryTreeSnapshot) and
            self.profile_snapshot.sha256 == self.profile_snapshot_sha256 and
            self.profile_id == self.contract.profile_id and
            self.profile_contract_fingerprint == self.contract.fingerprint and
            self.summary_receipt.get("tool") == TOOL and
            self.summary_receipt.get("check") == GATE_CHECK and
            self.summary_receipt.get("result") == "pass" and
            self.summary_receipt.get("selected_profile_manifest") ==
                self.contract.manifest_repo_path and
            all(self.summary_receipt.get(name) == getattr(self, name)
                for name in profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS) and
            self.summary_receipt.get("metadata_execution_contract_fingerprint") ==
                self.metadata_execution_contract.contract_fingerprint
        )

    def rebind_profile_snapshot(self, root=None):
        """Re-read only the typed Profile closure authorized by this view."""
        if not self.authorized:
            raise ValueError(
                "cannot re-bind a Profile snapshot from an unauthorized "
                "evaluation")
        effective_root = self.contract.root if root is None else os.path.realpath(
            os.path.abspath(os.fspath(root)))
        if effective_root != os.path.realpath(self.contract.root):
            raise ValueError(
                "Profile evaluation belongs to a different repository root")
        candidate_tree = kblib.repository_tree_snapshot(
            effective_root, self.contract.profile_repo_dir)
        return candidate_tree.project(self.contract.profile_snapshot_paths)

    def rebind_normative_inputs(self, root=None):
        """Rebind the complete fixed and linked owner input set for currency."""
        if not self.authorized:
            raise ValueError("cannot re-bind inputs from an unauthorized evaluation")
        effective_root = self.contract.root if root is None else os.path.realpath(
            os.path.abspath(os.fspath(root)))
        if effective_root != os.path.realpath(self.contract.root):
            raise ValueError("Profile evaluation belongs to a different repository root")
        return canonical_profile_load_inputs(
            effective_root, additional_paths=self.normative_snapshots.keys())


REPO_ROOT = repository_source_root(__file__)

DEFAULT_INTERFACE = profile_contract.PROFILE_INTERFACE_PATH
DEFAULT_AUDIT_DIMENSION_BASE = \
    profile_contract.AUDIT_DIMENSION_BASE_PATH
DEFAULT_CORPUS_PLANNING_CONTRACT = \
    corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH
DEFAULT_DEFAULTS = "Tools/schemas/execution_defaults.template.yaml"
DEFAULT_EXECUTION_DEFAULTS = (
    "kernel/K00 Standards Control/execution-defaults-base.yaml"
)
DEFAULT_OPERATION_CAPABILITIES = "Tools/operation-capabilities.yaml"
DEFAULT_RUNTIME_PATH_REGISTRY = (
    "Tools/execution/task_runtime/runtime_paths.py")
DEFAULT_SCAN_CAPABILITIES = profile_contract.SCAN_CAPABILITY_PATH
DEFAULT_METADATA_AUTHORITY = (
    "kernel/K08 Metadata and Status/metadata-authority-base.yaml")
DEFAULT_METADATA_CONTRACT = (
    "Tools/compiled/metadata-execution-contract.json")
DEFAULT_APPLICABILITY_BASE = profile_contract.KERNEL_APPLICABILITY_PATH
DEFAULT_RELATIONSHIP_BASE = profile_contract.KERNEL_RELATIONSHIP_PATH
DEFAULT_VOCABULARY_BASE = profile_contract.KERNEL_VOCABULARY_PATH
DEFAULT_GATE_REGISTRY = \
    control_registry_contract.STANDARDS_GATE_REGISTRY_PATH
_BASE_CANONICAL_PROFILE_LOAD_INPUTS = (
    DEFAULT_INTERFACE,
    DEFAULT_AUDIT_DIMENSION_BASE,
    DEFAULT_CORPUS_PLANNING_CONTRACT,
    DEFAULT_DEFAULTS,
    DEFAULT_EXECUTION_DEFAULTS,
    DEFAULT_OPERATION_CAPABILITIES,
    DEFAULT_RUNTIME_PATH_REGISTRY,
    DEFAULT_SCAN_CAPABILITIES,
    rendering_contract.CAPABILITY_REGISTRY_PATH,
    DEFAULT_METADATA_AUTHORITY,
    DEFAULT_METADATA_CONTRACT,
    DEFAULT_APPLICABILITY_BASE,
    DEFAULT_RELATIONSHIP_BASE,
    DEFAULT_VOCABULARY_BASE,
    DEFAULT_GATE_REGISTRY,
    contract_exception_policy.POLICY_REGISTRY_PATH,
    "Tools/governance/profile/profile_codec.py",
    "Tools/governance/profile/profile_cue.py",
    "Tools/governance/profile/cue-toolchain.json",
    profile_contract.PROFILE_REQUIREMENTS_PATH,
    "Tools/governance/profile/profile-encoding.yaml",
    "Tools/governance/profile/profile_schema_projection.py",
)
CANONICAL_PROFILE_LOAD_INPUTS = _BASE_CANONICAL_PROFILE_LOAD_INPUTS

STRUCTURE_REGISTRY_SLOT = profile_contract.STRUCTURE_REGISTRY_SLOT
PRIORITY_RUBRIC_SLOT = profile_contract.PRIORITY_RUBRIC_SLOT
METADATA_CONTRACT_SLOT = profile_contract.METADATA_CONTRACT_SLOT

AUDIT_DIMENSION_SLOT = profile_contract.AUDIT_DIMENSION_REGISTRY_SLOT

# Classification affects diagnostic presentation only. Candidate completeness
# comes from the draft model; only this evaluator emits profile-load evidence.
# Unrecognized diagnostics remain unresolved rather than being auto-repaired.
MECHANICAL = "mechanical"
SEMANTIC_UNRESOLVED = "semantic-unresolved"

_SEMANTIC_UNRESOLVED_CHECKS = frozenset((
    "expression-artifact-binding-missing",
    "override-choice-empty",
    "override-value-domain",
    "unfilled-placeholder",
))

_MECHANICAL_CHECKS = frozenset((
    "batch-review-judgment-duplicate",
    "batch-review-judgment-reference",
    "batch-review-role-reference",
    "corpus-planning-contract-invalid",
    "expression-artifact-binding-invalid",
    "expression-artifact-binding-shape",
    "expression-artifact-binding-unknown",
    "expression-artifact-dependency-map-invalid",
    "expression-artifact-entry-invalid",
    "expression-artifact-id-duplicate",
    "expression-artifact-id-invalid",
    "expression-artifact-readiness-field",
    "expression-artifact-readiness-gate",
    "expression-artifact-readiness-metadata",
    "expression-artifact-type-registry",
    "expression-artifact-type-unknown",
    "expression-contract-definition-field-invalid",
    "expression-contract-definition-field-missing",
    "expression-contract-definition-fragment-invalid",
    "expression-contract-definition-heading-count",
    "expression-contract-definition-heading-missing",
    "expression-contract-definition-path-invalid",
    "expression-contract-definition-path-outside-profile",
    "expression-contract-field-invalid",
    "expression-contract-field-missing",
    "expression-contract-fragment-invalid",
    "expression-contract-heading-count",
    "expression-contract-heading-missing",
    "expression-contract-id-duplicate",
    "expression-contract-path-invalid",
    "expression-contract-path-outside-profile",
    "expression-contract-reference-closure",
    "extension-dimension-id-collision",
    "extension-gate-capability-registry",
    "extension-gate-completion-invalid",
    "extension-gate-completion-reference",
    "extension-gate-consumer-capability",
    "extension-gate-deterministic-completion",
    "extension-gate-field-applicability",
    "extension-gate-field-completion",
    "extension-gate-field-kernel-collision",
    "extension-gate-field-reference",
    "extension-gate-field-shape",
    "extension-gate-id-duplicate",
    "extension-gate-id-invalid",
    "extension-gate-judgment-reference",
    "extension-gate-kernel-metadata-registry",
    "extension-gate-owner-field-invalid",
    "extension-gate-owner-field-missing",
    "extension-gate-owner-fragment-invalid",
    "extension-gate-owner-heading-count",
    "extension-gate-owner-heading-missing",
    "extension-gate-owner-path-invalid",
    "extension-gate-owner-path-outside-profile",
    "extension-gate-owner-reference",
    "extension-gate-owner-registry",
    "extension-gate-producer-capability",
    "extension-gate-producer-reference",
    "extension-gate-receipt-schema",
    "extension-gate-role-reference",
    "extension-gate-role-registry",
    "extension-gate-transition-duplicate",
    "extension-gate-vocabulary-registry",
    "extension-gate-writer-capability",
    "interface-unreadable",
    "judgment-item-dimension-unknown",
    "judgment-item-id-duplicate",
    "manifest-missing",
    "metadata-contract-applicability",
    "metadata-contract-boundary-projection",
    "metadata-contract-condition",
    "metadata-contract-entry",
    "metadata-contract-schema",
    "metadata-contract-section-role",
    "override-constitutional-item",
    "override-item-unknown",
    "override-redundant-default",
    "override-value-domain-unknown",
    "predicate-owner-field-invalid",
    "predicate-owner-field-missing",
    "predicate-owner-fragment-invalid",
    "predicate-owner-heading-count",
    "predicate-owner-heading-missing",
    "predicate-owner-path-invalid",
    "predicate-owner-path-outside-profile",
    "priority-quota-policy",
    "profile-contract-incomplete",
    "profile-contract-input",
    "profile-contract-link",
    "profile-contract-manifest-unreadable",
    "profile-contract-owner",
    "profile-contract-schema",
    "profile-corpus-planning-contract",
    "profile-dir-missing",
    "profile-draft-input",
    "profile-draft-shape",
    "profile-id-invalid",
    "profile-id-placeholder",
    "profile-load-input-changed",
    "profile-load-input-unreadable",
    "profile-load-metadata-contract-invalid",
    "profile-load-noncanonical-input",
    "profile-placeholder-registry",
    "profile-receipt-path-inside-profile",
    "profile-rendering-contract-invalid",
    "profile-snapshot-changed-during-check",
    "profile-snapshot-invalid",
    "registered-scan-capability-implementation",
    "registered-scan-capability-unknown",
    "registered-scan-config-forbidden",
    "registered-scan-config-required",
    "registered-scan-id-duplicate",
    "registered-scan-judgment-reference",
    "registered-scans-required-count",
    "residual-policy-field-invalid",
    "residual-policy-field-missing",
    "residual-policy-fragment-invalid",
    "residual-policy-heading-count",
    "residual-policy-heading-missing",
    "residual-policy-path-invalid",
    "residual-policy-path-outside-profile",
    "scan-config-field-invalid",
    "scan-config-field-missing",
    "scan-config-fragment-invalid",
    "scan-config-heading-count",
    "scan-config-heading-missing",
    "scan-config-path-invalid",
    "scan-config-path-outside-profile",
    "structure-registry-applicability",
    "structure-registry-capability",
    "structure-registry-input-owner",
    "structure-registry-layer",
    "structure-registry-layout",
    "structure-registry-parent",
    "structure-registry-role",
    "structure-registry-schema",
    "structure-registry-unit",
))

if _MECHANICAL_CHECKS & _SEMANTIC_UNRESOLVED_CHECKS:
    raise AssertionError(
        "finding category defined twice: %s" %
        sorted(_MECHANICAL_CHECKS & _SEMANTIC_UNRESOLVED_CHECKS))

FINDING_CATEGORIES = {
    **{check: MECHANICAL for check in sorted(_MECHANICAL_CHECKS)},
    **{check: SEMANTIC_UNRESOLVED
       for check in sorted(_SEMANTIC_UNRESOLVED_CHECKS)},
}


def finding_category(check):
    """Classify diagnostics without granting repair or adoption authority."""
    return FINDING_CATEGORIES.get(check, SEMANTIC_UNRESOLVED)


def profile_load_inputs_fingerprint(snapshots):
    """Hash the exact immutable input set; linked owner files are included."""
    return kblib.sha256_bytes(
        "\0".join(
            "%s\0%s" % (relative, snapshots[relative].sha256)
            for relative in sorted(snapshots)))


def canonical_profile_load_inputs(root, *, additional_paths=()):
    """Return immutable canonical producer inputs and their aggregate hash."""
    snapshots = {}
    # This walks the same capability implementations the contract compiler
    # walks, independently and in the same process, so it pays the same
    # repeated directory listings.  It means one consistent view too.
    with kblib.directory_listing_scope():
        snapshots[DEFAULT_INTERFACE] = kblib.repository_file_snapshot(
            root, DEFAULT_INTERFACE, singly_linked=True)
        interface = profile_contract.load_profile_interface(
            root, snapshots=snapshots)
        snapshots[profile_contract.PROFILE_ENCODING_PATH] = kblib.repository_file_snapshot(
            root, profile_contract.PROFILE_ENCODING_PATH, singly_linked=True)
        encoding = profile_contract.load_profile_encoding(root, snapshots=snapshots)
        profile_contract.validate_profile_encoding(interface, encoding)
        owner_paths = set(encoding["registry_references"].values()) | set(encoding["encoding_cue_sources"])
        for source in encoding["cue_sources"]:
            owner_paths.add(source["path"])
            if source.get("projection_of"):
                owner_paths.add(source["projection_of"])
        if isinstance(additional_paths, (str, bytes)):
            raise TypeError("additional input paths must be a collection")
        owner_paths.update(additional_paths)
        for relative in sorted(set(CANONICAL_PROFILE_LOAD_INPUTS) | owner_paths):
            if relative in snapshots:
                continue
            snapshots[relative] = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
        capabilities = kblib.parse_yaml_subset(
            snapshots[DEFAULT_OPERATION_CAPABILITIES].read_text())
        capabilities = metadata_execution_contract.\
            validate_operation_capabilities_document(capabilities)
        for relative in metadata_execution_contract.\
                capability_implementation_paths(capabilities):
            snapshots[relative] = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
        scan_capabilities = kblib.parse_yaml_subset(
            snapshots[DEFAULT_SCAN_CAPABILITIES].read_text())
        for relative in profile_contract.\
                scan_capability_implementation_paths(scan_capabilities):
            snapshots[relative] = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
        rendering_capabilities = kblib.parse_yaml_subset(
            snapshots[rendering_contract.CAPABILITY_REGISTRY_PATH].read_text())
        for relative in rendering_contract.capability_implementation_paths(
                rendering_capabilities):
            snapshots[relative] = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
    return snapshots, profile_load_inputs_fingerprint(snapshots)


def _positive_integer_domain(value):
    """A whole count of one or more, written without sign, unit, or decimals."""
    if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
        return "expected a positive integer"
    return None


def _percent_share_under_100_domain(value):
    """A share of a corpus its owner also partitions, so under the whole.

    The upper end is open because the owner module that fixes this form keeps
    a remainder class outside the quota: a share of 100% leaves that class
    empty and leaves nothing able to exceed the quota it registers. The bound
    belongs to that owner; this function only implements the form it names.
    """
    number = value[:-1].strip() if value.endswith("%") else value
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", number):
        return "expected a number, optionally followed by `%`"
    if not 0 <= float(number) < 100:
        return "expected a percentage share that is at least 0 and under 100"
    return None


# Admissible value forms a `value_domain` in the kernel execution-default
# registry may name.  The registry decides which item carries which form; this
# table only implements the form, and an unknown name is reported rather than
# silently treated as "anything goes".
VALUE_DOMAINS = {
    "positive-integer": _positive_integer_domain,
    "percent-share-under-100": _percent_share_under_100_domain,
}


def main(argv=None, *, _evaluation_out=None,
         _receipt_identity=_LIVE_RUNTIME_RECEIPT_IDENTITY,
         _write_receipts=True):
    ap = kblib.ArgumentParser(
        description="Complete structured Profile validation and profile-load Gate")
    ap.add_argument("profile_dir", help="the profile directory to check "
                                        "(e.g. profiles/<profile-id>)")
    ap.add_argument("--root", default=REPO_ROOT,
                    help="vault root that vault-relative bindings resolve "
                         "against (default: this script's repository root)")
    ap.add_argument("--interface", default=None,
                    help="normative slot interface file "
                         "(default: %s under --root)" % DEFAULT_INTERFACE)
    ap.add_argument("--defaults", default=None,
                    help="machine-readable unresolved-input marker registry "
                         "(default: %s under --root)" % DEFAULT_DEFAULTS)
    ap.add_argument("--execution-defaults", default=None,
                    help="kernel execution-default override registry "
                         "(default: %s under --root)"
                         % DEFAULT_EXECUTION_DEFAULTS)
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    ap.add_argument("--json", action="store_true",
                    help="write one deterministic JSON object (tool, root, "
                         "result, findings each carrying a closed "
                         "mechanical/semantic-unresolved category) to stdout "
                         "instead of the human summary; receipts and exit "
                         "codes are unchanged")
    args = ap.parse_args(argv)

    def say(message):
        """Human summary line; silenced when --json owns stdout."""
        if not args.json:
            print(message)

    # Canonicalize both endpoints before relativizing.  macOS exposes the
    # same temporary tree as both /var and /private/var; mixing those aliases
    # must not make a contained Profile appear to escape its repository.
    root = os.path.realpath(os.path.abspath(args.root))
    profile_input = os.path.abspath(args.profile_dir)
    lexical_profile = os.path.relpath(
        profile_input, root).replace(os.sep, "/")
    if (kblib.inherited_path_capability(args.profile_dir, "snapshot") is not
            None or kblib.retained_tree_is_bound(lexical_profile)):
        profile_dir = os.path.join(root, *lexical_profile.split("/"))
    else:
        profile_dir = os.path.realpath(profile_input)
    profile_disp = os.path.relpath(profile_dir, root).replace(os.sep, "/")
    interface_path = args.interface or os.path.join(root, DEFAULT_INTERFACE)
    defaults_path = args.defaults or os.path.join(root, DEFAULT_DEFAULTS)
    execution_defaults_path = (args.execution_defaults or
                               os.path.join(root, DEFAULT_EXECUTION_DEFAULTS))

    checked_manifest_identity = (
        profile_layout_contract.PROFILE_MANIFEST_NAME
        if profile_disp == "." else
        "%s/%s" % (
            profile_disp, profile_layout_contract.PROFILE_MANIFEST_NAME)
    )
    if _receipt_identity is _LIVE_RUNTIME_RECEIPT_IDENTITY:
        live_identity = kblib.runtime_receipt_identity(root)
        if (live_identity.get("selected_profile_manifest") and
                live_identity.get("selected_profile_manifest") !=
                checked_manifest_identity):
            # Candidate Profile evaluation while a different Profile is live
            # must not combine the live Task/Standards identity with the
            # candidate manifest.  K12/17 permits a pre-Task profile-load
            # receipt to claim only the exact manifest it actually checked.
            effective_receipt_identity = {
                "selected_profile_manifest": checked_manifest_identity,
            }
        else:
            effective_receipt_identity = dict(live_identity)
    else:
        effective_receipt_identity = dict(_receipt_identity or {})

    receipts = []
    seq = 0
    contract = None
    compiled_metadata = None
    profile_id = None
    profile_snapshot_sha256 = None
    profile_snapshot = None
    profile_tree_snapshot = None
    profile_snapshot_before = None
    profile_load_inputs_sha256 = None
    normative_snapshots = {}
    resolved_overrides = ()
    summary = None

    def add(check, target, result, details):
        nonlocal seq
        seq += 1
        receipt = kblib.make_receipt(
            TOOL, TOOL_VERSION, check, target, result, details, seq,
            receipt_type_id=(GATE_RECEIPT_TYPE_ID
                             if check == GATE_CHECK
                             else DIAGNOSTIC_RECEIPT_TYPE_ID),
            identity=effective_receipt_identity)
        receipt["gate_id"] = GATE_ID
        receipt["dimension"] = GATE_DIMENSION
        receipts.append(receipt)

    def finish(*, write_receipts=True):
        """Close one invocation and optionally expose its exact in-memory IR."""
        exit_code = kblib.exit_code(receipts)
        if write_receipts and _write_receipts:
            kblib.write_receipts(args.receipts, receipts)
        if args.json:
            # One deterministic structured-diagnostics object: same checks,
            # same order, same exit semantics as the human summary, plus the
            # closed mechanical/semantic-unresolved category per finding.
            print(json.dumps({
                "tool": TOOL,
                "tool_version": TOOL_VERSION,
                "profile_dir": profile_disp,
                "root": root,
                "result": {0: "pass", 1: "fail", 2: "candidate"}[exit_code],
                "findings": [
                    {
                        "check": receipt["check"],
                        "target": receipt["target"],
                        "details": receipt["details"],
                        "category": finding_category(receipt["check"]),
                    }
                    for receipt in receipts
                    if receipt["result"] != "pass"
                ],
            }, ensure_ascii=False, sort_keys=True, indent=2))
        if _evaluation_out is not None:
            authorized_contract = (
                contract
                if (exit_code == 0 and contract is not None and
                    contract.valid and summary is not None)
                else None
            )
            authorized_metadata = (
                compiled_metadata
                if (authorized_contract is not None and isinstance(
                    compiled_metadata,
                    metadata_execution_contract.
                        CompiledMetadataExecutionContract))
                else None
            )
            _evaluation_out.update({
                "exit_code": exit_code,
                "receipts": tuple(receipts),
                "contract": authorized_contract,
                "metadata_execution_contract": authorized_metadata,
                "profile_id": (
                    profile_id if authorized_contract is not None else None
                ),
                "profile_snapshot_sha256": profile_snapshot_sha256,
                "profile_contract_fingerprint": (
                    authorized_contract.fingerprint
                    if authorized_contract is not None else None
                ),
                "execution_default_overrides": (
                    resolved_overrides
                    if authorized_contract is not None else ()
                ),
                "profile_snapshot": (
                    profile_snapshot
                    if authorized_contract is not None else None
                ),
                "profile_load_inputs_sha256": (
                    profile_load_inputs_sha256
                    if authorized_contract is not None else None
                ),
                "summary_receipt": summary,
                "normative_snapshots": (
                    MappingProxyType(dict(normative_snapshots))
                    if authorized_contract is not None else None),
            })
        return exit_code

    if args.receipts:
        receipt_spellings = (
            os.path.abspath(os.fspath(args.receipts)),
            os.path.realpath(os.path.abspath(os.fspath(args.receipts))),
        )
        inside_profile = False
        for spelling in receipt_spellings:
            try:
                inside_profile = (
                    os.path.commonpath((profile_dir, spelling)) == profile_dir)
            except ValueError:
                inside_profile = False
            if inside_profile:
                break
        if inside_profile:
            add("profile-receipt-path-inside-profile", profile_disp, "fail",
                "--receipts must stay outside the Profile directory so "
                "validation cannot mutate the package whose snapshot it "
                "binds")
            say("check_profile: FAIL — receipt output cannot be written "
                  "inside the selected Profile")
            return finish(write_receipts=False)

    # ``profile-load`` is one registered Gate, not a caller-defined lint.
    # Its three normative inputs are fixed under the checked repository root;
    # allowing an invocation to substitute a smaller interface, a different
    # sentinel registry, or a broader override registry would produce an
    # indistinguishable but weaker pass receipt.
    normative_inputs = (
        ("interface", args.interface, DEFAULT_INTERFACE),
        ("defaults", args.defaults, DEFAULT_DEFAULTS),
        ("execution-defaults", args.execution_defaults,
         DEFAULT_EXECUTION_DEFAULTS),
    )
    for label, supplied, expected_relative in normative_inputs:
        if supplied is None:
            continue
        expected_absolute = os.path.join(
            root, *expected_relative.split("/"))
        supplied_absolute = os.path.abspath(os.fspath(supplied))
        if supplied_absolute != expected_absolute:
            add("profile-load-noncanonical-input", supplied_absolute, "fail",
                "--%s cannot replace the registered profile-load input `%s`; "
                "custom inputs may be inspected separately but cannot "
                "authorize this Gate" % (label, expected_relative))
    interface_path = os.path.join(root, *DEFAULT_INTERFACE.split("/"))
    defaults_path = os.path.join(root, *DEFAULT_DEFAULTS.split("/"))
    execution_defaults_path = os.path.join(
        root, *DEFAULT_EXECUTION_DEFAULTS.split("/"))

    normative_snapshots = {}
    try:
        normative_snapshots, profile_load_inputs_sha256 = \
            canonical_profile_load_inputs(root)
    except (OSError, ValueError) as exc:
        add("profile-load-input-unreadable", root, "fail",
            "cannot bind canonical profile-load inputs: %s" % exc)
        say("check_profile: FAIL — canonical profile-load input is not a "
              "stable singly-linked file: %s" % exc)
        return finish()
    try:
        metadata_authority = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_METADATA_AUTHORITY].read_text())
        operation_capabilities = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_OPERATION_CAPABILITIES].read_text())
        operation_capabilities = metadata_execution_contract.\
            validate_operation_capabilities_document(operation_capabilities)
        compiled_metadata = \
            metadata_execution_contract.compile_metadata_execution_document(
                metadata_authority, operation_capabilities,
                implementation_snapshots={
                    path: normative_snapshots[path]
                    for path in metadata_execution_contract.
                        capability_implementation_paths(
                            operation_capabilities)
                })
        if (normative_snapshots[DEFAULT_METADATA_CONTRACT].read_text() !=
                compiled_metadata.canonical_bytes.decode("utf-8")):
            raise ValueError(
                "compiled metadata execution contract is stale")
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError,
            metadata_execution_contract.MetadataExecutionContractError) as exc:
        add("profile-load-metadata-contract-invalid",
            DEFAULT_METADATA_CONTRACT, "fail",
            "canonical metadata authority/capability bundle cannot be "
            "compiled from the same root-input snapshot: %s" % exc)
        return finish()
    try:
        corpus_planning_contract.current_corpus_planning_contract_values(
            root, snapshots=normative_snapshots)
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        add("corpus-planning-contract-invalid",
            DEFAULT_CORPUS_PLANNING_CONTRACT, "fail",
            "cannot load the K02-owned Corpus Planning machine contract: %s"
            % exc)
        return finish()

    # Bind the candidate Profile bytes before any existence judgment or read.
    # The typed linker below projects the public manifest/dependency closure;
    # unrelated package files never enter the Profile authority fingerprint.
    # A pathname-level isdir/isfile preflight after MCP admission would merely
    # reopen the race before this snapshot.
    # A second digest below must match before a pass receipt can describe this
    # snapshot; otherwise the run combined observations from two revisions.
    try:
        profile_tree_snapshot = kblib.repository_tree_snapshot(
            root, profile_disp)
    except (OSError, ValueError) as exc:
        missing = (isinstance(exc, FileNotFoundError) or
                   "does not exist" in str(exc) or
                   "real directory" in str(exc))
        if missing:
            details = ("profile directory does not exist; a scan with "
                       "nothing to check is an invocation error, never a "
                       "pass")
            add("profile-dir-missing", profile_disp, "fail", details)
        else:
            details = (
                "cannot bind the selected Profile directory snapshot: %s" %
                exc)
            add("profile-snapshot-invalid", profile_disp, "fail", details)
        say("check_profile: FAIL — %s" % details)
        return finish()
    manifest_path = os.path.join(
        profile_dir, profile_layout_contract.PROFILE_MANIFEST_NAME)
    manifest_relative = (
        profile_layout_contract.PROFILE_MANIFEST_NAME
        if profile_disp == "." else
        "%s/%s" % (
            profile_disp, profile_layout_contract.PROFILE_MANIFEST_NAME))
    if manifest_relative not in profile_tree_snapshot.files:
        add("manifest-missing", manifest_relative, "fail",
            "the profile manifest %s is missing; every slot binding is "
            "declared there, so nothing about this profile can be verified"
            % profile_layout_contract.PROFILE_MANIFEST_NAME)
        say("check_profile: FAIL — %s has no %s" %
            (profile_disp, profile_layout_contract.PROFILE_MANIFEST_NAME))
        return finish()

    try:
        interface_document = profile_contract.load_profile_interface(
            root, snapshots=normative_snapshots)
        slots = profile_contract.profile_interface_slots(interface_document)
        defaults = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_DEFAULTS].read_text())
        execution_defaults = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_EXECUTION_DEFAULTS].read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        add("interface-unreadable", DEFAULT_INTERFACE, "fail",
            "cannot read canonical Profile contract inputs: %s" % exc)
        return finish()

    sentinel = str(defaults.get("unfilled_sentinel") or "TODO(profile)")

    def root_owner_snapshot(relative):
        """Bind a real owner dependency discovered by this same typed link."""
        if relative not in normative_snapshots:
            normative_snapshots[relative] = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
        return normative_snapshots[relative]

    try:
        contract = profile_contract.load_profile_contract(
            root, manifest_path, sentinel=sentinel,
            profile_snapshot=profile_tree_snapshot,
            root_input_snapshots=normative_snapshots,
            root_snapshot_resolver=root_owner_snapshot)
    except (OSError, UnicodeError, ValueError) as exc:
        add("profile-contract-manifest-unreadable", manifest_relative, "fail",
            "cannot compile the structured Profile: %s" % exc)
        return finish()

    profile_id = contract.profile_id
    profile_load_inputs_sha256 = profile_load_inputs_fingerprint(
        normative_snapshots)
    for diagnostic in contract.diagnostics:
        check = ("unfilled-placeholder"
                 if diagnostic.check == "profile-contract-sentinel"
                 else diagnostic.check)
        add(check, diagnostic.target, "fail", diagnostic.details)
    if not contract.valid and not contract.diagnostics:
        add("profile-contract-incomplete", manifest_relative, "fail",
            "the structured Profile linker did not return a complete contract")

    try:
        profile_snapshot = profile_tree_snapshot.project(
            contract.profile_snapshot_paths)
        profile_snapshot_before = profile_snapshot.sha256
    except (OSError, UnicodeError, ValueError) as exc:
        add("profile-snapshot-invalid", profile_disp, "fail",
            "cannot project the typed Profile dependency closure from "
            "its immutable candidate tree: %s" % exc)

    # Shape validation has one owner in the linker. These checks connect the
    # already-typed instance values with installed runtime capabilities.
    if contract.valid:
        structure = contract.slot_document(STRUCTURE_REGISTRY_SLOT)
        projection_capabilities = {
            entry["capability_id"]: entry
            for entry in operation_capabilities["capabilities"]
            if entry["kind"] == "projection"
        }
        for check, label, details in kblib.validate_structure_registry_references(
                structure, projection_capabilities,
                manifest_relative + "#slots.structure-registry"):
            add(check, label, "fail", details)
        try:
            policy_registry = contract_exception_policy.load_policy_registry(
                root, text=normative_snapshots[
                    contract_exception_policy.POLICY_REGISTRY_PATH].read_text(),
                require_owner_files=False)
            _quotas, _configured, policy_errors = \
                contract_exception_policy.priority_quota_policy(
                    contract.slot_document(PRIORITY_RUBRIC_SLOT),
                    registry=policy_registry)
        except (OSError, UnicodeError, ValueError) as exc:
            policy_errors = ["cannot evaluate the frozen quota policy: %s" % exc]
        for details in policy_errors:
            add("priority-quota-policy", manifest_relative +
                "#slots.priority-rubric.priority_quota", "fail", details)

    # Override values are parsed once by the linker. The canonical K00
    # registry still owns which values may override which defaults.
    overridable = {str(entry["item"]): entry
                   for entry in execution_defaults.get("overridable", ())
                   if isinstance(entry, dict) and entry.get("item")}
    constitutional = {str(entry["item"]): entry
                      for entry in execution_defaults.get("constitutional", ())
                      if isinstance(entry, dict) and entry.get("item")}
    registered = tuple(contract.execution_default_overrides)
    for item, value in registered:
        target = "%s#execution_default_overrides.%s" % (
            manifest_relative, item)
        if item in constitutional:
            add("override-constitutional-item", target, "fail",
                "%s is a constitutional constant (owner: %s)" %
                (item, constitutional[item].get("owner", "kernel")))
        elif item not in overridable:
            add("override-item-unknown", target, "fail",
                "%s is not in the closed overridable registry" % item)
        elif value is None or value == "":
            add("override-choice-empty", target, "fail",
                "%s has no explicit Profile value" % item)
        elif value == "use-kernel-default":
            add("override-redundant-default", target, "fail",
                "remove %s; unlisted items already use the Kernel default" %
                item)
        else:
            entry = overridable[item]
            domain = entry.get("value_domain")
            if domain is None:
                continue
            validate = VALUE_DOMAINS.get(str(domain))
            if validate is None:
                add("override-value-domain-unknown", target, "fail",
                    "the registered value domain %r for %s has no validator" %
                    (domain, item))
                continue
            reason = validate(str(value))
            if reason:
                add("override-value-domain", target, "fail",
                    "value %r for %s leaves registered domain %r "
                    "(owner: %s): %s" %
                    (value, item, domain, entry.get("owner", "kernel"), reason))
    resolved_overrides = tuple(sorted(registered))

    if profile_snapshot_before is not None:
        try:
            current_profile_tree = kblib.repository_tree_snapshot(
                root, contract.profile_repo_dir or profile_disp)
            profile_snapshot_after = current_profile_tree.project(
                contract.profile_snapshot_paths).sha256
        except (OSError, ValueError) as exc:
            add("profile-snapshot-invalid", profile_disp, "fail",
                "cannot re-bind the selected Profile dependency closure: %s"
                % exc)
        else:
            if profile_snapshot_after != profile_snapshot_before:
                add("profile-snapshot-changed-during-check", profile_disp,
                    "fail", "selected Profile dependency bytes changed "
                    "while profile-load was deriving its contract; rerun "
                    "against one stable snapshot")
            else:
                profile_snapshot_sha256 = profile_snapshot_after

    for relative, expected in sorted(normative_snapshots.items()):
        try:
            observed = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
        except (OSError, ValueError) as exc:
            add("profile-load-input-changed", relative, "fail",
                "canonical input became unreadable during profile-load: %s" %
                exc)
            continue
        if observed.sha256 != expected.sha256:
            add("profile-load-input-changed", relative, "fail",
                "canonical input bytes changed while profile-load was "
                "deriving its contract")

    fails = [r for r in receipts if r["result"] == "fail"]
    candidates = [r for r in receipts if r["result"] == "candidate"]
    if not fails and not candidates:
        add(GATE_CHECK, contract.manifest_repo_path, "pass",
            "profile_id=%s; structured_slots=%d; explicit_overrides=%d; "
            "typed_closure=%d dependency edge(s); this proves machine "
            "structure and reference closure, not semantic quality or "
            "user confirmation"
            % (profile_id, len(contract.slot_values), len(registered),
               len(contract.dependency_edges)))
        summary = receipts[-1]
        summary["selected_profile_manifest"] = contract.manifest_repo_path
        summary["profile_snapshot_sha256"] = profile_snapshot_sha256
        summary["profile_contract_fingerprint"] = contract.fingerprint
        summary["profile_load_inputs_sha256"] = profile_load_inputs_sha256
        summary["metadata_execution_contract_fingerprint"] = \
            compiled_metadata.contract_fingerprint

    # ---- human-readable summary ----
    say("check_profile: %s (profile_id=%s)"
          % (profile_disp, profile_id if profile_id else "<none>"))
    say("  interface=%s slots=%d explicit_overrides=%d"
        % (os.path.relpath(interface_path, root).replace(os.sep, "/"),
           len(contract.slot_values), len(registered)))
    for r in receipts:
        if r["result"] == "fail":
            say("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))
        elif r["result"] == "candidate":
            say("  [CAND %s] %s — %s" % (r["check"], r["target"], r["details"]))
    if fails:
        say("  Conclusion: NOT LOADABLE — %d failure(s). This profile is "
              "incomplete; the composed standard must not be judged fully "
              "loaded." % len(fails))
    elif candidates:
        say("  Conclusion: REVIEW REQUIRED — %d candidate finding(s); no "
              "profile-load pass receipt was emitted." % len(candidates))
    else:
        say("  Conclusion: Profile load authorized; structured values and "
              "the typed dependency closure pass. This "
              "checks machine structure, not whether answers are good or "
              "whether the user confirmed them.")

    return finish()


def evaluate_profile_load(profile_dir, *, root, interface=None, defaults=None,
                          execution_defaults=None, receipt_identity=None):
    """Evaluate ``profile-load`` once and return its exact contract snapshot.

    This is the shared producer API for Terminal Proof, batch close, and other
    Gate consumers.  It executes the same code path as the CLI but never writes
    receipts.  ``receipt_identity=None`` deliberately disables Queue identity
    injection; callers evaluating a planned/candidate state may instead pass an
    explicit mapping whose values describe that state.
    """
    if receipt_identity is not None and not isinstance(receipt_identity, Mapping):
        raise TypeError("receipt_identity must be a mapping or None")

    argv = [os.fspath(profile_dir), "--root", os.fspath(root)]
    for option, value in (
            ("--interface", interface),
            ("--defaults", defaults),
            ("--execution-defaults", execution_defaults)):
        if value is not None:
            argv.extend((option, os.fspath(value)))

    captured = io.StringIO()
    evaluation = {}
    with contextlib.redirect_stdout(captured):
        exit_code = main(
            argv,
            _evaluation_out=evaluation,
            _receipt_identity=(
                {} if receipt_identity is None else dict(receipt_identity)
            ),
            _write_receipts=False,
        )
    receipts = evaluation.get("receipts", ())
    return ProfileLoadEvaluation(
        exit_code=exit_code,
        findings=tuple(
            receipt for receipt in receipts
            if receipt.get("result") != "pass"
        ),
        contract=evaluation.get("contract"),
        metadata_execution_contract=evaluation.get(
            "metadata_execution_contract"),
        profile_id=evaluation.get("profile_id"),
        profile_snapshot_sha256=evaluation.get("profile_snapshot_sha256"),
        profile_contract_fingerprint=evaluation.get(
            "profile_contract_fingerprint"),
        execution_default_overrides=tuple(
            evaluation.get("execution_default_overrides", ())),
        profile_snapshot=evaluation.get("profile_snapshot"),
        profile_load_inputs_sha256=evaluation.get(
            "profile_load_inputs_sha256"),
        summary_receipt=evaluation.get("summary_receipt"),
        output=captured.getvalue(),
        normative_snapshots=evaluation.get("normative_snapshots"),
    )


if __name__ == "__main__":
    sys.exit(main())
