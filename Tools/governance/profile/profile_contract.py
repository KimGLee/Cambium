#!/usr/bin/env python3
"""One structured Profile compiler and its immutable runtime model.

TOML is the sole instance answer format. Kernel-owned CUE sources validate its
shape; this Tool links real paths, semantic owners and installed capabilities.
The compiler does not select a Profile, execute a verifier, confirm an answer,
or publish adoption state. Draft inspection never yields runtime authority.
"""
from dataclasses import dataclass, field
import errno
import hashlib
import json
import os
import re
import sys
from types import MappingProxyType
from collections.abc import Mapping
from typing import Optional, Tuple

from Tools.platform.repository.path_contract import canonical_repository_relative_path
from Tools.platform.repository.repository import repository_source_root
import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.execution.planning.corpus_planning_contract as corpus_planning_contract
from Tools.governance.profile.profile_schema_projection import check_profile_schema_projections
import Tools.governance.control.control_registry_contract as control_registry_contract
import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader
import Tools.platform.common.kblib as kblib
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.governance.profile.profile_codec as profile_codec
import Tools.governance.profile.profile_cue as profile_cue
import Tools.governance.profile.rendering_contract as rendering_contract
from Tools.governance.profile.rendering_contract import RenderingContract, RenderingRule
import Tools.knowledge.metadata.vocabulary_contract as vocabulary_contract

PROFILE_INTERFACE_PATH = "kernel/K00 Standards Control/profile-interface.yaml"
PROFILE_ENCODING_PATH = "Tools/governance/profile/profile-encoding.yaml"
PROFILE_DEFAULTS_PATH = "Tools/schemas/execution_defaults.template.yaml"
PROFILE_TOOLCHAIN_PATH = "Tools/governance/profile/cue-toolchain.json"
PROFILE_REQUIREMENTS_PATH = "Tools/requirements-profile.txt"
AUDIT_DIMENSION_BASE_PATH = audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH
SCAN_CAPABILITY_PATH = "Tools/scan-capabilities.yaml"
KERNEL_APPLICABILITY_PATH = "kernel/K08 Metadata and Status/applicability-base.yaml"
KERNEL_RELATIONSHIP_PATH = "kernel/K08 Metadata and Status/relationship-base.yaml"
KERNEL_VOCABULARY_PATH = vocabulary_contract.VOCABULARY_BASE_PATH
PROFILE_LOAD_GATE_ID = "profile-load"
PROFILE_LOAD_EVIDENCE_FIELDS = (
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint", "profile_load_inputs_sha256",
)
PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS = PROFILE_LOAD_EVIDENCE_FIELDS[1:]


def freeze(value):
    """Detach JSON-shaped semantic values into a deeply immutable model."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value):
    """Return ordinary typed data for an owned compiler, never source text."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


def _root_text(root, path, snapshots=None):
    if snapshots is None:
        snapshot = kblib.repository_file_snapshot(root, path, singly_linked=True)
    else:
        snapshot = snapshots.get(path)
        if snapshot is None:
            raise ValueError("frozen Profile input is missing: " + path)
    return snapshot.read_text()


def profile_interface_slots(document):
    """Validate the Kernel interface envelope; CUE owns instance shapes."""
    required = {"schema_version", "interface_id", "semantic_owner",
                "semantic_definition", "contracts", "slots", "registry_references"}
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("Profile interface fields are not closed")
    if (document["schema_version"] != 4 or
            document["interface_id"] != "cambium-profile-interface" or
            document["semantic_owner"] != "K00/19"):
        raise ValueError("Profile interface identity is invalid")
    if document["semantic_definition"] != "#ProfileSlots":
        raise ValueError("Profile interface semantic definition is invalid")
    contracts = document["contracts"]
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("Profile interface requires semantic contracts")
    identities = []
    for contract in contracts:
        if (not isinstance(contract, dict) or set(contract) != {
                "contract_id", "semantic_owner"} or not all(
                    isinstance(value, str) and value.strip()
                    for value in contract.values())):
            raise ValueError("Profile semantic contract identity is invalid")
        identities.append(contract["contract_id"])
    if len(identities) != len(set(identities)):
        raise ValueError("Profile semantic contract identities must be unique")
    slots = document["slots"]
    if not isinstance(slots, list) or not slots:
        raise ValueError("Profile interface slots must be nonempty")
    names, ids = [], []
    for row in slots:
        if not isinstance(row, dict) or set(row) != {
                "slot_id", "name", "kernel_owner", "definition"}:
            raise ValueError("Profile slot definition fields are not closed")
        if (not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", row["slot_id"]) or
                not all(isinstance(row[key], str) and row[key]
                        for key in ("name", "kernel_owner", "definition")) or
                not row["definition"].startswith("#")):
            raise ValueError("Profile slot identity is invalid")
        names.append(row["name"])
        ids.append(row["slot_id"])
    if len(names) != len(set(names)) or len(ids) != len(set(ids)):
        raise ValueError("Profile slot identities must be unique")
    if not isinstance(document["registry_references"], dict):
        raise ValueError("Profile registry references must be a mapping")
    if not set(document["registry_references"].values()).issubset(identities):
        raise ValueError("Profile registry references must name registered semantic contracts")
    return tuple(names)


def load_profile_interface(root=None, snapshots=None):
    root = root or repository_source_root(__file__)
    document = kblib.parse_yaml_subset(_root_text(root, PROFILE_INTERFACE_PATH, snapshots))
    profile_interface_slots(document)
    return document


def profile_interface_slot_names(document):
    profile_interface_slots(document)
    return {row["slot_id"]: row["name"] for row in document["slots"]}


_SHIPPED_PROFILE_INTERFACE = load_profile_interface()
_SHIPPED_SLOT_NAMES = profile_interface_slot_names(_SHIPPED_PROFILE_INTERFACE)


def slot_id(value):
    if value in _SHIPPED_SLOT_NAMES:
        return value
    matches = [key for key, name in _SHIPPED_SLOT_NAMES.items() if name == value]
    if len(matches) != 1:
        raise KeyError("unregistered Profile slot %r" % value)
    return matches[0]


PROFILE_SCOPE_SLOT = _SHIPPED_SLOT_NAMES["profile-scope"]
CORPUS_PLANNING_SLOT = _SHIPPED_SLOT_NAMES["corpus-planning"]
STRUCTURE_REGISTRY_SLOT = _SHIPPED_SLOT_NAMES["structure-registry"]
METADATA_CONTRACT_SLOT = _SHIPPED_SLOT_NAMES["metadata-contract"]
PRIORITY_RUBRIC_SLOT = _SHIPPED_SLOT_NAMES["priority-rubric"]
VOCABULARY_EXTENSIONS_SLOT = _SHIPPED_SLOT_NAMES["vocabulary-extensions"]
LANGUAGE_CONTRACT_SLOT = _SHIPPED_SLOT_NAMES["language-contract"]
EXPRESSION_LAYER_ENTRY_SLOT = _SHIPPED_SLOT_NAMES["expression-layer-entry"]
RENDERING_CONTRACT_SLOT = _SHIPPED_SLOT_NAMES["rendering-contract"]
SOURCE_POLICY_SLOT = _SHIPPED_SLOT_NAMES["source-policy"]
ROLE_REGISTRY_SLOT = _SHIPPED_SLOT_NAMES["role-registry"]
AUDIT_DIMENSION_REGISTRY_SLOT = _SHIPPED_SLOT_NAMES["audit-dimension-registry"]
REGISTERED_SCAN_REGISTRY_SLOT = _SHIPPED_SLOT_NAMES["registered-scan-registry"]
ESCALATION_POLICY_SLOT = _SHIPPED_SLOT_NAMES["escalation-policy"]
ROUTING_AND_GATE_REGISTRY_SLOT = _SHIPPED_SLOT_NAMES["routing-and-gate-registry"]
BASE_DIMENSION_ORDER = audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER
BASE_DIMENSIONS = frozenset(BASE_DIMENSION_ORDER)
EVIDENCE_ROLES = audit_dimension_contract.EVIDENCE_ROLES
STABLE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
FIELD_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
VOCABULARY_VALUE_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
REQUIRED_SCAN_RE = re.compile(r"(?<![A-Za-z0-9])K12/09\s+item\s+6(?![0-9])")
EXPRESSION_STATUS_AXIS_ROLE = "Expression Status Axis"


def load_profile_encoding(root=None, snapshots=None):
    document = kblib.parse_yaml_subset(_root_text(
        root or repository_source_root(__file__), PROFILE_ENCODING_PATH, snapshots))
    required = {"schema_version", "entrypoint", "document_schema_version",
                "slot_container", "policy_reference_fragment", "capability_bindings",
                "interface_id", "cue_sources", "registry_references",
                "cue_definitions", "encoding_cue_sources"}
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("Profile Tool encoding fields are not closed")
    if (document["schema_version"] != 1 or document["document_schema_version"] != 1 or
            document["entrypoint"] != profile_layout_contract.PROFILE_MANIFEST_NAME or document["slot_container"] != "slots" or
            document["policy_reference_fragment"] != "slots.<slot_id>.<semantic_field>"):
        raise ValueError("Profile Tool encoding identity is invalid")
    if not isinstance(document["capability_bindings"], dict):
        raise ValueError("Profile encoding lacks capability bindings")
    if document["cue_definitions"] != {"profile": "#Profile", "draft": "#ProfileDraft"}:
        raise ValueError("Profile Tool encoding CUE definitions are invalid")
    wrappers = document["encoding_cue_sources"]
    if not isinstance(wrappers, list) or not wrappers:
        raise ValueError("Profile Tool encoding requires CUE document sources")
    for path in wrappers:
        canonical_repository_relative_path(path, "Profile encoding CUE source")
        if not path.startswith("Tools/") or not path.endswith(".cue"):
            raise ValueError("Profile document encoding must be Tool-owned CUE")
    if len(wrappers) != len(set(wrappers)):
        raise ValueError("Profile encoding sources must be unique")
    if not isinstance(document["registry_references"], dict):
        raise ValueError("Profile encoding requires registry source locations")
    for path in document["registry_references"].values():
        canonical_repository_relative_path(path, "Profile registry source")
    sources = document["cue_sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("Profile encoding requires CUE sources")
    paths, ids = [], []
    for source in sources:
        if (not isinstance(source, dict) or not {"path", "contract_id"}.issubset(source) or
                set(source) - {"path", "contract_id", "projection_of"}):
            raise ValueError("Profile CUE source fields are not closed")
        path = canonical_repository_relative_path(source["path"], "CUE source")
        if not path.endswith(".cue") or not isinstance(source["contract_id"], str):
            raise ValueError("Profile CUE source identity is invalid")
        if "projection_of" in source:
            canonical_repository_relative_path(source["projection_of"], "CUE projection source")
        paths.append(path)
        ids.append(source["contract_id"])
    if len(paths) != len(set(paths)) or len(ids) != len(set(ids)):
        raise ValueError("Profile CUE source paths and identities must be unique")
    if set(paths).intersection(wrappers):
        raise ValueError("Profile semantic and encoding CUE sources must be distinct")
    return document


def validate_profile_encoding(interface, encoding):
    """Bind Tool source locations to exactly the Kernel's semantic contracts."""
    if encoding["interface_id"] != interface["interface_id"]:
        raise ValueError("Profile encoding names a different Kernel interface")
    sources = {row["contract_id"]: row for row in encoding["cue_sources"]}
    if set(sources) != {row["contract_id"] for row in interface["contracts"]}:
        raise ValueError("Tool CUE source mapping must cover each Kernel contract exactly once")
    if set(encoding["registry_references"]) != set(interface["registry_references"]):
        raise ValueError("Tool registry source roles differ from the Kernel contract roles")
    for role, identity in interface["registry_references"].items():
        if sources[identity].get("projection_of") != encoding["registry_references"][role]:
            raise ValueError("Tool projection and registry source disagree for " + role)


def profile_draft_inputs(root):
    """Freeze candidate shape inputs without loading runtime implementations."""
    snapshots = {}
    with kblib.directory_listing_scope():
        for path in (PROFILE_INTERFACE_PATH, PROFILE_ENCODING_PATH,
                     PROFILE_DEFAULTS_PATH, PROFILE_TOOLCHAIN_PATH,
                     PROFILE_REQUIREMENTS_PATH):
            snapshots[path] = kblib.repository_file_snapshot(root, path, singly_linked=True)
        interface = load_profile_interface(root, snapshots)
        encoding = load_profile_encoding(root, snapshots)
        validate_profile_encoding(interface, encoding)
        paths = set(encoding["registry_references"].values()) | set(encoding["encoding_cue_sources"])
        for source in encoding["cue_sources"]:
            paths.add(source["path"])
            if "projection_of" in source:
                paths.add(source["projection_of"])
        for path in sorted(paths):
            snapshots[path] = kblib.repository_file_snapshot(root, path, singly_linked=True)
    return MappingProxyType(snapshots)


_ENCODING_BINDINGS = load_profile_encoding()["capability_bindings"]
PRODUCER_CAPABILITY_BY_KIND = dict(_ENCODING_BINDINGS["producer_capability_by_kind"])
RECEIPT_SCHEMA_BY_KIND = dict(_ENCODING_BINDINGS["receipt_schema_by_kind"])
FIELD_GATE_CONSUMER_OPERATION = _ENCODING_BINDINGS["field_gate_consumer_operation"]
NON_FIELD_GATE_CONSUMER_OPERATION = _ENCODING_BINDINGS["non_field_gate_consumer_operation"]
PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION = _ENCODING_BINDINGS["profile_extension_enum_projection_operation"]
PROFILE_EXTENSION_ENUM_WRITER_CAPABILITY = _ENCODING_BINDINGS["profile_extension_enum_writer_capability"]



class ProfileContractError(ValueError):
    """The Profile contract cannot authorize runtime consumption."""


@dataclass(frozen=True)
class SourceCell:
    """One machine-readable source cell with a stable source coordinate."""

    path: str
    section: str
    line: int
    row: int
    field: str
    raw: str

    @property
    def target(self):
        if self.section == "Profile dependency closure":
            return "%s:%d" % (self.path, self.line)
        return "%s#%s.%s" % (self.path, self.section, self.field)


@dataclass(frozen=True)
class Diagnostic:
    """One deterministic admission failure."""

    check: str
    target: str
    details: str
    source: Optional[SourceCell] = None


@dataclass(frozen=True)
class ProfileDependency:
    """A successfully linked contract file (and optional heading).

    Predicate owners and scan configs are Profile-owned; an extension Gate's
    semantic owner may instead be a canonical kernel file.
    """

    kind: str
    owner_id: str
    path: str
    absolute_path: str
    heading: Optional[str]
    source: SourceCell


@dataclass(frozen=True)
class DependencyEdge:
    """Canonical semantic edge used by the contract fingerprint."""

    kind: str
    owner_id: str
    target_id: Optional[str] = None
    path: Optional[str] = None
    fragment: Optional[str] = None


@dataclass(frozen=True)
class ExtensionDimension:
    dimension_id: str
    targets: Tuple[str, ...]
    meaning: str
    source: SourceCell


@dataclass(frozen=True)
class JudgmentItem:
    judgment_item_id: str
    dimension_id: str
    audit_layer: str
    audit_object: str
    evidence_role: str
    predicate_owner: Optional[ProfileDependency]
    source: SourceCell


@dataclass(frozen=True)
class RegisteredScan:
    scan_id: str
    activation_role: str
    scope: str
    verifier_capability_id: str
    script_repo_path: Optional[str]
    script_absolute_path: Optional[str]
    config_dependency: Optional[ProfileDependency]
    candidate_predicate: str
    judgment_item_id: str
    required_for_k12_item_6: bool
    source: SourceCell


@dataclass(frozen=True)
class ExtensionGate:
    """One fully linked Profile-owned extension Gate.

    A row is runtime authority only as part of an authorized
    :class:`ProfileContract`.  The producer reference is the unique registered
    scan for deterministic Gates and the pass-authority role for manual
    attestations.
    """

    gate_id: str
    owner_gate_id: Optional[str]
    owner_dependency: Optional[ProfileDependency]
    transition_id: str
    pass_authority_role_id: str
    applicability: str
    field_id: Optional[str]
    completion_values: Tuple[str, ...]
    judgment_item_id: str
    producer_kind: str
    producer_capability: str
    producer_reference: Optional[str]
    receipt_schema: str
    consumer_capability: str
    source: SourceCell
    field_values: Tuple[str, ...] = ()


@dataclass(frozen=True)
class VocabularyField:
    """One typed field from the selected Vocabulary Extensions snapshot.

    ``role`` is deliberately retained even when it is absent.  Runtime
    projections must distinguish a field explicitly registered as an
    expression status axis from an unrelated Profile extension that happens
    to use the same value shape.
    """

    field_id: str
    role: Optional[str]
    values: Tuple[str, ...]


@dataclass(frozen=True)
class RegisteredExpressionArtifact:
    """One Profile-owned expression artifact registration.

    The row binds stable instance semantics only.  Its entry and dependency
    map may name future corpus paths, so admission validates their canonical
    spelling without requiring the targets to exist yet.
    """

    artifact_id: str
    artifact_type: str
    label: str
    entry_point: str
    dependency_map_path: Optional[str]
    binding_field_ids: Tuple[str, ...]
    revalidation_trigger: str
    contract_owner: ProfileDependency
    readiness_field_id: Optional[str]
    source: SourceCell


@dataclass(frozen=True)
class ExpressionStatusTarget:
    """The exact Profile field and Gate that define one expression target."""

    gate_id: str
    field_id: str
    completion_values: Tuple[str, ...]


@dataclass(frozen=True)
class BatchReviewRequirement:
    """One Profile obligation the batch-review wrapper must prove complete.

    Unlike an Extension Gate, a requirement changes no persisted property.
    It declares that one registered Judgment Item must be judged for every
    applicable target of a batch before that batch may leave ``open``, and
    binds the producer class, receipt schema, and pass-authority role its
    per-target evidence must carry.
    """

    judgment_item_id: str
    target_selector: str
    trigger: str
    producer_kind: str
    receipt_schema: str
    pass_authority_role_id: str
    source: SourceCell


@dataclass(frozen=True)
class ProfileContract:
    root: str
    manifest_path: str
    manifest_repo_path: str
    profile_root: str
    profile_repo_dir: str
    audit_registry_path: Optional[str]
    scan_registry_path: Optional[str]
    routing_registry_path: Optional[str]
    extension_registration: Optional[str]
    extension_dimensions: Tuple[ExtensionDimension, ...]
    judgment_items: Tuple[JudgmentItem, ...]
    registered_scans: Tuple[RegisteredScan, ...]
    extension_gate_registration: Optional[str]
    extension_gates: Tuple[ExtensionGate, ...]
    dependency_edges: Tuple[DependencyEdge, ...]
    source_cells: Tuple[SourceCell, ...]
    diagnostics: Tuple[Diagnostic, ...]
    batch_review_registration: Optional[str] = None
    batch_review_requirements: Tuple[BatchReviewRequirement, ...] = ()
    vocabulary_fields: Tuple[VocabularyField, ...] = ()
    volatility_defaults: Tuple[Tuple[str, str], ...] = ()
    expression_registry_path: Optional[str] = None
    expression_registration: Optional[str] = None
    expression_artifacts: Tuple[RegisteredExpressionArtifact, ...] = ()
    rendering_contract: Optional[RenderingContract] = None
    profile_id: Optional[str] = None
    slot_values: object = field(default_factory=lambda: MappingProxyType({}))
    execution_default_overrides: Tuple[Tuple[str, object], ...] = ()
    cue_source_paths: Tuple[str, ...] = ()
    role_ids: frozenset = frozenset()

    def __post_init__(self):
        object.__setattr__(self, "slot_values", freeze(self.slot_values))
        object.__setattr__(self, "execution_default_overrides",
                           tuple((key, freeze(value)) for key, value in
                                 self.execution_default_overrides))
        object.__setattr__(self, "role_ids", frozenset(self.role_ids))

    def slot_document(self, name):
        """Return a defensive structured projection for owned domain validators."""
        identifier = slot_id(name)
        return _slot_document(identifier, self.slot_values.get(identifier))

    def slot(self, name):
        """Read one fully typed logical slot without reparsing source bytes."""
        return self.slot_values.get(slot_id(name))

    @property
    def valid(self):
        """Compilation validity only; never a Gate pass or adoption approval."""
        return not self.diagnostics

    @property
    def required_scan(self):
        selected = tuple(
            scan for scan in self.registered_scans
            if scan.required_for_k12_item_6
        )
        return selected[0] if len(selected) == 1 else None

    @property
    def profile_snapshot_paths(self):
        """Canonical files owned by this manifest's typed Profile closure.

        The manifest is always the root.  Dependency edges may also name
        Kernel- or Tool-owned targets; only paths physically contained by the
        selected Profile package belong to the Profile snapshot.  Root-owned
        machine inputs remain bound by ``profile_load_inputs_sha256``.
        """
        paths = {self.manifest_repo_path} if self.manifest_repo_path else set()
        prefix = self.profile_repo_dir.rstrip("/") + "/"
        for edge in self.dependency_edges:
            if edge.path and edge.path.startswith(prefix):
                paths.add(edge.path)
        return tuple(sorted(paths))

    @property
    def profile_contract_fingerprint(self):
        """Bind the complete typed answer model and its linked semantic edges."""
        if not self.valid:
            return None
        value = {
            "schema_version": 1, "manifest": self.manifest_repo_path,
            "profile_id": self.profile_id,
            "slots": thaw(self.slot_values),
            "execution_default_overrides": thaw(dict(self.execution_default_overrides)),
            "edges": [{
                "kind": edge.kind, "owner_id": edge.owner_id,
                "target_id": edge.target_id, "path": edge.path,
                "fragment": edge.fragment,
            } for edge in self.dependency_edges],
        }
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @property
    def fingerprint(self):
        return self.profile_contract_fingerprint


@dataclass(frozen=True)
class ProfileDraft:
    """Inspectable candidate answers. This type never authorizes a consumer."""
    profile_id: Optional[str]
    manifest_repo_path: str
    slot_values: object
    diagnostics: Tuple[Diagnostic, ...]
    unresolved_items: Tuple[str, ...]
    ready: bool = False

    def __post_init__(self):
        object.__setattr__(self, "slot_values", freeze(self.slot_values))

    def slot_document(self, name):
        """Return a defensive structured projection for owned domain validators."""
        identifier = slot_id(name)
        return _slot_document(identifier, self.slot_values.get(identifier))

    def slot(self, name):
        return self.slot_values.get(slot_id(name))




def scan_capability_records(document):
    """Return the closed Tool-owned verifier capability registry by ID."""
    if not isinstance(document, dict) or set(document) != {
            "schema_version", "capabilities"}:
        raise ValueError("scan capability registry fields are not closed")
    if document.get("schema_version") != 1:
        raise ValueError("scan capability registry schema_version must be 1")
    rows = document.get("capabilities")
    if not isinstance(rows, list) or not rows:
        raise ValueError("scan capability registry must be a non-empty list")
    records = {}
    required = {
        "capability_id", "invocation_contract", "implementation_path",
        "configuration",
    }
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError(
                "scan capability %d fields are not closed" % index)
        capability_id = row.get("capability_id")
        if not isinstance(capability_id, str) or not re.fullmatch(
                r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", capability_id):
            raise ValueError("scan capability %d has an invalid ID" % index)
        if capability_id in records:
            raise ValueError("duplicate scan capability %s" % capability_id)
        if row.get("invocation_contract") != "profile-registered-scan-v1":
            raise ValueError(
                "scan capability %s has an unsupported invocation contract" %
                capability_id)
        implementation = row.get("implementation_path")
        if (not isinstance(implementation, str) or
                not implementation.startswith("Tools/") or
                not implementation.endswith(".py") or
                any(part in ("", ".", "..")
                    for part in implementation.split("/"))):
            raise ValueError(
                "scan capability %s has an invalid implementation path" %
                capability_id)
        if row.get("configuration") not in ("required", "none"):
            raise ValueError(
                "scan capability %s configuration must be required or none" %
                capability_id)
        records[capability_id] = dict(row)
    return records


def load_scan_capabilities(root=None, snapshots=None):
    """Load the Tool-owned scan capability registry."""
    if root is None:
        root = repository_source_root(__file__)
    document = kblib.parse_yaml_subset(_root_text(root, SCAN_CAPABILITY_PATH, snapshots))
    scan_capability_records(document)
    return document


def scan_capability_implementation_paths(document):
    return tuple(sorted(
        row["implementation_path"]
        for row in scan_capability_records(document).values()))


def _repo_relative(root, path):
    root_real = os.path.realpath(os.path.abspath(os.fspath(root)))
    path_absolute = os.path.abspath(os.fspath(path))
    lexical_relative = os.path.relpath(
        path_absolute, os.path.abspath(os.fspath(root))).replace(os.sep, "/")
    if (lexical_relative != "." and
            not lexical_relative.startswith("../") and
            kblib.retained_tree_is_bound(lexical_relative)):
        return lexical_relative
    path_real = os.path.realpath(path_absolute)
    try:
        inside = os.path.commonpath((root_real, path_real)) == root_real
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("path resolves outside the repository root")
    # macOS exposes the temporary tree through both ``/var`` and
    # ``/private/var``.  Relativize canonical endpoints, not their display
    # aliases, or an actually contained absolute path appears to escape.
    relative = os.path.relpath(path_real, root_real).replace(os.sep, "/")
    if relative == "." or relative.startswith("../"):
        raise ValueError("path is not a repository file")
    return relative


def _canonical_repository_file(root, relative_path, *, singly_linked=False):
    """Resolve one canonical repo-relative regular file without symlinks."""
    relative_path = canonical_repository_relative_path(relative_path, "path")
    return kblib.canonical_repository_file(
        root, relative_path, singly_linked=singly_linked)


def _kernel_metadata_fields(builder, source_path, root_input_snapshots=None):
    """Resolve the Kernel page-field namespace from one frozen root view."""
    fields = set()
    failed = False
    for path, mapping_name in (
            (KERNEL_APPLICABILITY_PATH, "fields"),
            (KERNEL_RELATIONSHIP_PATH, "relationships")):
        try:
            document = kblib.parse_yaml_subset(_root_text(
                builder.root, path, root_input_snapshots))
            mapping = document.get(mapping_name) \
                if isinstance(document, dict) else None
            if not isinstance(mapping, dict):
                raise ValueError("missing %s mapping" % mapping_name)
            invalid = [
                field for field in mapping
                if (not isinstance(field, str) or
                    FIELD_ID_RE.fullmatch(field) is None)
            ]
            if invalid:
                raise ValueError(
                    "invalid field identifier(s): %s" %
                    ", ".join(map(str, invalid)))
            overlap = fields.intersection(mapping)
            if overlap:
                raise ValueError(
                    "duplicate Kernel field(s): %s" %
                    ", ".join(sorted(overlap)))
            fields.update(mapping)
        except (OSError, TypeError, UnicodeError, ValueError) as exc:
            builder.add(
                "extension-gate-kernel-metadata-registry", source_path,
                "cannot load frozen Kernel metadata field registry %s: %s" %
                (path, exc))
            failed = True
    return None if failed else frozenset(fields)


def _kernel_gate_ids(builder, root_input_snapshots=None):
    """Read the canonical Kernel Gate namespace through its sole parser.

    Profile admission needs only the structurally valid namespace. Runtime
    producer availability is deliberately checked by
    ``standards_gate_registry`` at the execution boundary, not imported into
    this frozen-root semantic reference check.
    """
    source_path = control_registry_contract.STANDARDS_GATE_REGISTRY_PATH
    try:
        text = _root_text(builder.root, source_path, root_input_snapshots)
        registry, errors = \
            control_registry_contract.parse_standards_gate_registry(text)
    except (OSError, UnicodeError, ValueError) as exc:
        builder.add(
            "extension-gate-owner-registry", source_path,
            "cannot read the kernel Gate registry: %s" % exc)
        return frozenset()
    if errors:
        for error in errors:
            builder.add(
                "extension-gate-owner-registry", source_path,
                "kernel Gate registry is invalid: %s" % error)
        return frozenset()
    return frozenset(registry)


def _capability_registry(builder, source_path, root_input_snapshots=None):
    """Load the canonical closed capability registry exactly once."""
    try:
        import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
        capability_path = "Tools/operation-capabilities.yaml"
        document = kblib.parse_yaml_subset(_root_text(
            builder.root, capability_path, root_input_snapshots))
        document = metadata_execution_contract.validate_operation_capabilities_document(document)
    except (AttributeError, ImportError, OSError, UnicodeError,
            ValueError) as exc:
        builder.add(
            "extension-gate-capability-registry", source_path,
            "the closed metadata capability registry is unavailable: %s" % exc)
        return (
            lambda _capability_id, _kind: False,
            lambda _capability_id, _operation, _kind="consumer": False,
        )
    entries = {
        (entry["capability_id"], entry["kind"]): entry
        for entry in document["capabilities"]
    }

    def registered(capability_id, kind):
        return (capability_id, kind) in entries

    def supports(capability_id, operation, kind="consumer"):
        entry = entries.get((capability_id, kind))
        return bool(
            entry is not None and
            {"operation": operation} in entry["operations"])

    return registered, supports


def _capability_registered(builder, checker, capability_id, kind, source):
    try:
        result = checker(capability_id, kind)
    except Exception as exc:
        builder.add(
            "extension-gate-capability-registry", source.target,
            "closed capability lookup failed for %r (%s): %s" %
            (capability_id, kind, exc), source)
        return False
    if not isinstance(result, bool):
        builder.add(
            "extension-gate-capability-registry", source.target,
            "closed capability lookup for %r (%s) returned non-boolean %r" %
            (capability_id, kind, result), source)
        return False
    return result


def _capability_supports(builder, supports, capability_id, operation, source,
                         *, kind="consumer"):
    try:
        result = supports(capability_id, operation, kind)
    except Exception as exc:
        builder.add(
            "extension-gate-capability-registry", source.target,
            "closed %s capability operation lookup failed for %r (%s): %s" %
            (kind, capability_id, operation, exc), source)
        return False
    if not isinstance(result, bool):
        builder.add(
            "extension-gate-capability-registry", source.target,
            "closed %s capability operation lookup for %r (%s) returned "
            "non-boolean %r" %
            (kind, capability_id, operation, result), source)
        return False
    return result


def expression_status_target_projection(contract):
    """Project the selected Profile's exact expression completion target.

    This function consumes only one already-linked, valid
    :class:`ProfileContract`; it performs no filesystem reads.  A Profile that
    registers no ``Expression Status Axis`` field has no expression target and
    therefore projects the legal empty tuple.  Once that role is registered,
    exactly one field and exactly one Gate for that field must resolve, or the
    projection fails closed instead of guessing which Gate or values apply.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    if not contract.valid:
        raise ProfileContractError(
            "Profile contract is invalid: %s" %
            format_diagnostics(contract.diagnostics))

    fields = tuple(
        field for field in contract.vocabulary_fields
        if field.role == EXPRESSION_STATUS_AXIS_ROLE
    )
    if not fields:
        return ()
    if len(fields) != 1:
        raise ProfileContractError(
            "Profile contract registers %d Expression Status Axis fields; "
            "exactly one is allowed" % len(fields))
    field = fields[0]
    gates = tuple(
        gate for gate in contract.extension_gates
        if gate.field_id == field.field_id
    )
    if len(gates) != 1:
        raise ProfileContractError(
            "Expression Status Axis field %r must bind exactly one extension "
            "Gate; found %d" % (field.field_id, len(gates)))
    gate = gates[0]
    if (not gate.completion_values or
            len(set(gate.completion_values)) != len(gate.completion_values) or
            not set(gate.completion_values).issubset(field.values)):
        raise ProfileContractError(
            "Expression Status Axis Gate %r has invalid completion values "
            "for field %r" % (gate.gate_id, field.field_id))
    return (ExpressionStatusTarget(
        gate_id=gate.gate_id,
        field_id=field.field_id,
        completion_values=gate.completion_values,
    ),)


def expression_dependency_map_paths_projection(contract):
    """Project registered Expression dependency maps without reopening bytes."""
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    if not contract.valid:
        raise ProfileContractError(
            "Profile contract is invalid: %s" %
            format_diagnostics(contract.diagnostics))
    return tuple(sorted({
        artifact.dependency_map_path
        for artifact in contract.expression_artifacts
        if artifact.dependency_map_path is not None
    }))


def terminal_receipt_dimensions_projection(contract):
    """Return the exact dimension namespace Terminal Proof must account for.

    The Kernel-owned base order is always present.  The selected Profile may
    extend that namespace only through valid Extension Dimension rows
    whose typed target set includes ``receipt``.  Review-only registrations
    remain valid Profile review obligations, but they never become Terminal
    receipt dimensions merely because an AuditPlan records their judgment.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    if not contract.valid:
        raise ProfileContractError(
            "Profile contract is invalid: %s" %
            format_diagnostics(contract.diagnostics))
    extensions = tuple(sorted(
        dimension.dimension_id
        for dimension in contract.extension_dimensions
        if "receipt" in dimension.targets
    ))
    dimensions = tuple(BASE_DIMENSION_ORDER) + extensions
    if len(dimensions) != len(set(dimensions)):
        raise ProfileContractError(
            "Terminal receipt dimension projection is not unique")
    return dimensions


def volatility_defaults_projection(contract):
    """Project the compiled Profile's domain-to-volatility policy.

    The Profile linker is the sole parser and validator for the selected
    Vocabulary Extensions slot.  Downstream planners and artifact compilers
    consume this immutable typed view rather than reopening Profile bytes.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    if not contract.valid:
        raise ProfileContractError(
            "Profile contract is invalid: %s" %
            format_diagnostics(contract.diagnostics))
    return MappingProxyType(dict(contract.volatility_defaults))


def format_diagnostics(diagnostics):
    """Render diagnostics without losing their stable check identifiers."""
    return "; ".join(
        "%s [%s]: %s" %
        (diagnostic.check, diagnostic.target, diagnostic.details)
        for diagnostic in diagnostics
    )


def registered_scan_entrypoint(root, scan):
    """Resolve one registered implementation owner to its public adapter."""
    implementation_path = getattr(scan, "script_repo_path", None)
    if not isinstance(implementation_path, str) or not implementation_path:
        raise ProfileContractError(
            "registered scan has no resolved verifier capability")
    try:
        return entrypoint_loader.entrypoint_for_implementation_path(
            implementation_path, os.path.join(os.fspath(root), "Tools"))
    except entrypoint_loader.EntrypointResolutionError as exc:
        raise ProfileContractError(
            "registered scan implementation has no unique invocation "
            "adapter: %s" % exc) from exc


def compile_registered_scan_command(root, contract, scan=None):
    """Compile one valid scan row to a shell-free subprocess argv.

    ``scan`` defaults to the unique K12/09 item 6 registration.  The root must
    be the same repository root used to link the contract.  Runtime consumers
    append gate-owned arguments such as ``--receipts`` and
    ``--positive-controls-only`` after this function returns.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    supplied_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if supplied_root != contract.root:
        raise ProfileContractError(
            "compile root does not match linked Profile contract root")
    if not contract.valid:
        raise ProfileContractError(
            "Profile contract is invalid: %s" %
            format_diagnostics(contract.diagnostics))
    selected = contract.required_scan if scan is None else scan
    if selected is None:
        raise ProfileContractError(
            "Profile contract has no unique K12/09 item 6 registration")
    if selected not in contract.registered_scans:
        raise ProfileContractError(
            "registered scan does not belong to this Profile contract")
    if not selected.script_absolute_path:
        raise ProfileContractError(
            "registered scan has no resolved verifier capability")
    entrypoint = registered_scan_entrypoint(contract.root, selected)
    invocation_path = os.path.join(
        contract.root, *entrypoint.invocation_path.split("/"))
    command = [
        sys.executable,
        invocation_path,
        contract.root,
        "--scan-id",
        selected.scan_id,
    ]
    if selected.config_dependency is not None:
        command.extend(("--config", selected.config_dependency.path))
    return tuple(command)


class _Builder:
    def __init__(self, root, manifest_path, sentinel, snapshots=None,
                 root_snapshot_resolver=None):
        self.root_input = os.path.abspath(os.fspath(root))
        self.root = os.path.realpath(self.root_input)
        self.manifest_input = os.fspath(manifest_path)
        self.sentinel = sentinel
        self.diagnostics = []
        self.source_cells = []
        self.edges = []
        self.profile_snapshot = None
        self.document = {}
        self.manifest_relative = ""
        self.root_input_snapshots = snapshots
        self.root_snapshot_resolver = root_snapshot_resolver

    def add(self, check, target, details, source=None):
        diagnostic = Diagnostic(check, target, details, source)
        if diagnostic not in self.diagnostics:
            self.diagnostics.append(diagnostic)

    def source(self, section, field_name, value, row=0):
        raw = value if isinstance(value, str) else json.dumps(
            thaw(value), ensure_ascii=False, sort_keys=True)
        source = SourceCell(self.manifest_relative, section, 1, row,
                            field_name, raw)
        self.source_cells.append(source)
        return source

    def record_sources(self, section, record, index):
        return {key: self.source("%s[%d]" % (section, index), key, value, index + 1)
                for key, value in record.items()}

    def scan_text_sentinel(self, text, source_path, owner):
        if not self.sentinel:
            return
        for line_number, line in enumerate(text.splitlines(), 1):
            if self.sentinel in line:
                source = SourceCell(source_path, "Profile dependency closure",
                                    line_number, 0, owner, line.strip())
                self.source_cells.append(source)
                self.add("profile-contract-sentinel", source.target,
                         "%s contains unresolved marker %r" % (owner, self.sentinel),
                         source)

    def read_profile_text(self, repository_relative_path):
        if self.profile_snapshot is None:
            raise OSError(errno.EINVAL, "Profile snapshot is not bound")
        return self.profile_snapshot.read_text(repository_relative_path)

    def _dependency(self, kind, owner_id, reference, source, profile_repo_dir,
                    *, profile_only, require_fragment=False):
        if not isinstance(reference, str):
            self.add(kind + "-path-invalid", source.target,
                     "owner reference must be a string", source)
            return None
        path, marker, fragment = reference.partition("#")
        if marker and not fragment or require_fragment and not fragment:
            self.add(kind + "-heading-missing", source.target,
                     "owner reference requires one nonempty fragment", source)
            return None
        if profile_only and not path.startswith(profile_repo_dir + "/"):
            self.add(kind + "-path-outside-profile", source.target,
                     "owner must stay inside this Profile package", source)
            return None
        try:
            absolute = _canonical_repository_file(self.root, path, singly_linked=True)
            profile_local = path.startswith(profile_repo_dir + "/")
            if profile_local:
                content = self.read_profile_text(path)
                self.scan_text_sentinel(content, path, kind)
            elif (self.root_input_snapshots is not None and
                  path not in self.root_input_snapshots and
                  self.root_snapshot_resolver is not None):
                snapshot = self.root_snapshot_resolver(path)
                if (snapshot.repository_path != path or
                        os.path.realpath(snapshot.path) != os.path.realpath(absolute)):
                    raise ValueError("dynamic owner snapshot does not bind its canonical path")
                content = snapshot.read_text()
            else:
                content = _root_text(self.root, path, self.root_input_snapshots)
        except (OSError, UnicodeError, ValueError) as exc:
            self.add(kind + "-path-invalid", source.target, str(exc), source)
            return None
        if marker:
            if path == self.manifest_relative:
                if not fragment.startswith("slots."):
                    self.add(kind + "-field-invalid", source.target,
                             "Profile TOML owner fragment must identify a slot field",
                             source)
                    return None
                target = self.document
                for part in fragment.split("."):
                    if not isinstance(target, Mapping) or part not in target:
                        self.add(kind + "-field-missing", source.target,
                                 "semantic owner field does not resolve: " + fragment,
                                 source)
                        return None
                    target = target[part]
            elif path.endswith(".md"):
                matches = [
                    line for line, _level, title in kblib.headings_of(
                        kblib.blank_markdown_authority(content))
                    if title == fragment
                ]
                if len(matches) != 1:
                    self.add(kind + "-heading-count", source.target,
                             "body owner heading must resolve exactly once; found %d"
                             % len(matches), source)
                    return None
            else:
                self.add(kind + "-fragment-invalid", source.target,
                         "fragment target must be this Profile TOML or a Markdown body",
                         source)
                return None
        dependency = ProfileDependency(
            kind, owner_id, path, absolute, fragment if marker else None, source)
        self.edges.append(DependencyEdge(kind=kind, owner_id=owner_id,
                                         path=path, fragment=dependency.heading))
        return dependency

    def profile_dependency(self, kind, owner_id, raw, source, profile_repo_dir,
                           require_heading=False):
        return self._dependency(kind, owner_id, raw, source, profile_repo_dir,
                                profile_only=True, require_fragment=require_heading)

    def repository_dependency(self, kind, owner_id, raw, source, profile_repo_dir,
                              require_heading=False):
        return self._dependency(kind, owner_id, raw, source, profile_repo_dir,
                                profile_only=False, require_fragment=require_heading)


def _manifest_location(root, manifest_path):
    root_display = os.path.abspath(os.fspath(root))
    root_real = os.path.realpath(root_display)
    value = os.fspath(manifest_path)
    if os.path.isabs(value):
        display_absolute = os.path.abspath(value)
        try:
            inside = os.path.commonpath((root_display, display_absolute)) == root_display
        except ValueError:
            inside = False
        relative = (os.path.relpath(display_absolute, root_display).replace(os.sep, "/")
                    if inside else _repo_relative(root_real, display_absolute))
    else:
        relative = canonical_repository_relative_path(value, "Profile manifest")
    profile_layout_contract.parse_profile_manifest_path(relative)
    absolute = _canonical_repository_file(root_real, relative, singly_linked=True)
    return root_real, absolute, relative


def _read_candidate(builder, profile_snapshot):
    root, absolute, relative = _manifest_location(builder.root_input, builder.manifest_input)
    builder.root, builder.manifest_relative = root, relative
    profile_dir = relative.rsplit("/", 1)[0]
    snapshot = profile_snapshot or kblib.repository_tree_snapshot(root, profile_dir)
    if (os.path.realpath(snapshot.root) != root or
            snapshot.relative_directory != profile_dir):
        raise ValueError("Profile snapshot does not bind the selected package")
    builder.profile_snapshot = snapshot
    text = builder.read_profile_text(relative)
    builder.document = profile_codec.loads_profile(text)
    return absolute, relative, profile_dir, text


def _cue_sources(builder, interface, encoding):
    sources = {}
    inputs = {path: _root_text(builder.root, path, builder.root_input_snapshots)
              for path in (PROFILE_INTERFACE_PATH, PROFILE_ENCODING_PATH)}
    owners = {row["contract_id"]: row["semantic_owner"] for row in interface["contracts"]}
    for path in encoding["registry_references"].values():
        inputs[path] = _root_text(builder.root, path, builder.root_input_snapshots)
    for item in encoding["cue_sources"]:
        path = item["path"]
        sources[path] = _root_text(builder.root, path, builder.root_input_snapshots)
        inputs[path] = sources[path]
        if "projection_of" in item and item["projection_of"] not in inputs:
            inputs[item["projection_of"]] = _root_text(
                builder.root, item["projection_of"], builder.root_input_snapshots)
        builder.edges.append(DependencyEdge(
            kind="profile-shape-owner", owner_id=owners[item["contract_id"]], path=path))
    for path in encoding["encoding_cue_sources"]:
        sources[path] = _root_text(builder.root, path, builder.root_input_snapshots)
        inputs[path] = sources[path]
        builder.edges.append(DependencyEdge(
            kind="profile-encoding-owner", owner_id="profile-document", path=path))
    check_profile_schema_projections(encoding, inputs)
    return sources


def _check_identity(builder, *, draft=False):
    profile_id = builder.document.get("profile_id")
    if profile_id is None and draft:
        return None
    source = builder.source("profile", "profile_id", profile_id)
    try:
        location = profile_layout_contract.parse_profile_manifest_path(builder.manifest_relative)
        profile_layout_contract.validate_manifest_identity(builder.document, location)
    except profile_layout_contract.ProfileLayoutError as exc:
        builder.add("profile-id-invalid", source.target,
                    str(exc), source)
        return None
    try:
        defaults = kblib.parse_yaml_subset(_root_text(
            builder.root, PROFILE_DEFAULTS_PATH, builder.root_input_snapshots))
        reserved = defaults["reserved_profile_ids"]
        if not isinstance(reserved, list):
            raise ValueError("reserved_profile_ids must be a list")
        if profile_id in reserved or profile_id in profile_layout_contract.RESERVED_PROFILE_IDS:
            builder.add("profile-id-placeholder", source.target,
                        "Profile ID is reserved for unfilled candidate material", source)
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        builder.add("profile-placeholder-registry", PROFILE_DEFAULTS_PATH, str(exc))
    return profile_id


def _schema_check(builder, *, draft=False):
    interface = load_profile_interface(builder.root, builder.root_input_snapshots)
    if interface != _SHIPPED_PROFILE_INTERFACE:
        raise ValueError("Profile interface differs from the deployed Kernel interface")
    encoding = load_profile_encoding(builder.root, builder.root_input_snapshots)
    validate_profile_encoding(interface, encoding)
    if encoding["capability_bindings"] != _ENCODING_BINDINGS:
        raise ValueError("Profile capability encoding differs from the deployed Tool contract")
    builder.encoding = encoding
    builder.toolchain = json.loads(_root_text(
        builder.root, PROFILE_TOOLCHAIN_PATH, builder.root_input_snapshots))
    sources = _cue_sources(builder, interface, encoding)
    result = profile_cue.validate_profile(
        builder.document, sources, draft=draft, toolchain=builder.toolchain)
    return interface, sources, result


def _empty_contract(builder, manifest_path="", manifest_repo_path="",
                    profile_root="", profile_repo_dir=""):
    return ProfileContract(
        root=builder.root, manifest_path=manifest_path,
        manifest_repo_path=manifest_repo_path, profile_root=profile_root,
        profile_repo_dir=profile_repo_dir,
        audit_registry_path=None, scan_registry_path=None, routing_registry_path=None,
        extension_registration=None, extension_dimensions=(), judgment_items=(),
        registered_scans=(), extension_gate_registration=None, extension_gates=(),
        dependency_edges=tuple(builder.edges), source_cells=tuple(builder.source_cells),
        diagnostics=tuple(builder.diagnostics),
        profile_id=builder.document.get("profile_id"),
        slot_values=builder.document.get("slots", {}) if isinstance(
            builder.document.get("slots", {}), Mapping) else {},
    )


def _draft_unresolved_markers(builder):
    """Locate existing unanswered markers, without granting link authority.

    Inspect only supplied answers and the same declared Profile-local body or
    configuration references consumed by the formal linker. Missing or unsafe
    references are not read here: formal reference validation still owns them.
    """
    if not builder.sentinel:
        return ()
    unresolved = []

    def visit(value, coordinate):
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(item, coordinate + "." + key if coordinate else key)
        elif isinstance(value, (tuple, list)):
            for index, item in enumerate(value):
                visit(item, "%s[%d]" % (coordinate, index))
        elif isinstance(value, str) and builder.sentinel in value:
            unresolved.append(builder.manifest_relative + "#" + coordinate)

    visit(builder.document, "")
    slots = builder.document.get("slots", {})
    if not isinstance(slots, Mapping):
        return tuple(unresolved)
    reference_fields = (
        ("audit-dimension-registry", "judgment_items", "predicate_owner"),
        ("registered-scan-registry", "scan_registrations", "configuration_ref"),
        ("routing-and-gate-registry", "extension_gates", "owner_ref"),
        ("expression-layer-entry", "registered_artifacts", "contract_ref"),
        ("expression-layer-entry", "artifact_contracts", "body_ref"),
    )
    references = set()
    for identifier, collection, key in reference_fields:
        slot = slots.get(identifier, {})
        rows = slot.get(collection, ()) if isinstance(slot, Mapping) else ()
        if isinstance(rows, Mapping):
            rows = rows.get("items", ())
        if isinstance(rows, (tuple, list)):
            references.update(row[key] for row in rows if isinstance(row, Mapping)
                              and isinstance(row.get(key), str))
    audit = slots.get("audit-dimension-registry", {})
    residual = audit.get("residual_disposition", {}) if isinstance(audit, Mapping) else {}
    if isinstance(residual, Mapping) and isinstance(residual.get("body_ref"), str):
        references.add(residual["body_ref"])
    prefix = builder.manifest_relative.rsplit("/", 1)[0] + "/"
    for reference in sorted(references):
        path = reference.partition("#")[0]
        if not path.startswith(prefix) or path == builder.manifest_relative:
            continue
        try:
            _canonical_repository_file(builder.root, path, singly_linked=True)
            content = builder.read_profile_text(path)
        except (OSError, UnicodeError, ValueError):
            continue
        for line_number, line in enumerate(content.splitlines(), 1):
            if builder.sentinel in line:
                unresolved.append("%s:%d" % (path, line_number))
    return tuple(unresolved)


def load_profile_draft(root, manifest_path, *, sentinel="TODO(profile)",
                       profile_snapshot=None, root_input_snapshots=None):
    """Inspect a draft through the same owner constraints; never authorize it."""
    builder = _Builder(root, manifest_path, sentinel, root_input_snapshots)
    unresolved = []
    ready = False
    try:
        if builder.root_input_snapshots is None:
            builder.root_input_snapshots = profile_draft_inputs(builder.root)
        _absolute, _relative, _profile_dir, _text = _read_candidate(builder, profile_snapshot)
        _check_identity(builder, draft=True)
        _interface, sources, result = _schema_check(builder, draft=True)
        if not result.valid:
            for detail in result.diagnostics:
                builder.add("profile-draft-shape", builder.manifest_relative, detail)
        else:
            complete = profile_cue.validate_profile(
                builder.document, sources, draft=False, toolchain=builder.toolchain)
            unresolved.extend(complete.diagnostics)
            unresolved.extend(_draft_unresolved_markers(builder))
            ready = complete.valid and not builder.diagnostics and not unresolved
        if builder.document.get("profile_id") is None:
            unresolved.append("profile_id")
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        builder.add("profile-draft-input", builder.manifest_input, str(exc))
    return ProfileDraft(
        profile_id=builder.document.get("profile_id"),
        manifest_repo_path=builder.manifest_relative,
        slot_values=builder.document.get("slots", {}) if isinstance(
            builder.document.get("slots", {}), Mapping) else {},
        diagnostics=tuple(builder.diagnostics),
        unresolved_items=tuple(dict.fromkeys(unresolved)), ready=ready,
    )




def _slot_document(identifier, value):
    """Project the owner's nullable semantics for existing domain validators.

    Only explicitly nullable fields of an already-declared branch are restored.
    An unanswered field never selects an inactive branch or becomes an answer.
    """
    document = thaw(value)
    if not isinstance(document, dict):
        return document
    if identifier == "corpus-planning":
        applicability = document.get("applicability", {})
        if applicability.get("state") == "configured":
            applicability.setdefault("reason", None)
        if document.get("applicability", {}).get("state") == "not-applicable":
            for container, keys in (
                    ("artifact_bindings", ("global_map", "capability_matrix", "gap_register")),
                    ("pass_authority", ("role_id", "decision_scope_id"))):
                if isinstance(document.get(container), dict):
                    for key in keys:
                        document[container].setdefault(key, None)
    elif identifier == "structure-registry":
        applicability = document.get("applicability", {})
        if applicability.get("state") == "configured":
            applicability.setdefault("reason", None)
        for unit in document.get("units", ()):
            if unit.get("kind") == "domain":
                unit.setdefault("parent", None)
            unit.setdefault("global_map_entry", None)
            if isinstance(unit.get("entry"), dict):
                unit["entry"].setdefault("expected_type", None)
        for layer in document.get("support_layers", ()):
            layer.setdefault("global_map_entry", None)
            if isinstance(layer.get("entry"), dict):
                layer["entry"].setdefault("expected_type", None)
            if layer.get("layout") == "flat":
                layer.setdefault("taxonomy", None)
    return document


def _rows(builder, slot, collection, rows):
    section = "slots.%s.%s" % (slot, collection)
    for index, row in enumerate(rows):
        yield row, builder.record_sources(section, row, index)


def _role_ids(builder, roles):
    ids = set(roles["process_roles"])
    if roles["knowledge_host"].get("host"):
        ids.add("knowledge-host")
    if roles["knowledge_host"].get("ui"):
        ids.add("knowledge-host UI")
    for row, sources in _rows(builder, "role-registry", "extension_roles.items",
                              roles["extension_roles"]["items"]):
        role_id = row["role_id"]
        if role_id in ids:
            builder.add("extension-gate-role-registry", sources["role_id"].target,
                        "extension role collides with an already bound role", sources["role_id"])
        ids.add(role_id)
    return frozenset(ids)


def _parse_extensions(builder, document):
    wrapper = document["extension_dimensions"]
    result, seen = [], set()
    for row, sources in _rows(builder, "audit-dimension-registry",
                              "extension_dimensions.items", wrapper["items"]):
        identity = row["dimension_id"]
        if identity in seen or identity in BASE_DIMENSIONS:
            builder.add("extension-dimension-id-collision", sources["dimension_id"].target,
                        "extension dimension is duplicated or redefines a Kernel dimension",
                        sources["dimension_id"])
        seen.add(identity)
        result.append(ExtensionDimension(identity, tuple(row["targets"]),
                                         row["meaning"], sources["dimension_id"]))
    return wrapper["mode"], tuple(result)


def _parse_judgments(builder, document, profile_repo_dir, extensions):
    known = BASE_DIMENSIONS | {item.dimension_id for item in extensions}
    result, seen = [], set()
    for row, sources in _rows(builder, "audit-dimension-registry",
                              "judgment_items", document["judgment_items"]):
        identity = row["item_id"]
        if identity in seen:
            builder.add("judgment-item-id-duplicate", sources["item_id"].target,
                        "Judgment Item ID is registered more than once", sources["item_id"])
        seen.add(identity)
        if row["dimension_id"] not in known:
            builder.add("judgment-item-dimension-unknown", sources["dimension_id"].target,
                        "dimension is neither Kernel-owned nor a registered extension",
                        sources["dimension_id"])
        dependency = builder.profile_dependency(
            "predicate-owner", identity, row["predicate_owner"], sources["predicate_owner"],
            profile_repo_dir)
        result.append(JudgmentItem(
            identity, row["dimension_id"], row["audit_layer"], row["audit_object"],
            row["evidence_role"], dependency, sources["item_id"]))
    return tuple(result)


def _parse_scans(builder, document, profile_repo_dir, capabilities):
    parsed, seen = [], set()
    for row, sources in _rows(builder, "registered-scan-registry",
                              "scan_registrations", document["scan_registrations"]):
        scan_id = row["scan_id"]
        if scan_id in seen:
            builder.add("registered-scan-id-duplicate", sources["scan_id"].target,
                        "Scan ID is registered more than once", sources["scan_id"])
        seen.add(scan_id)
        capability_id = row["verifier_capability"]
        capability = capabilities.get(capability_id)
        script_path = script_absolute = dependency = None
        config = row.get("configuration_ref")
        config_source = sources.get("configuration_ref") or builder.source(
            "slots.registered-scan-registry.scan_registrations",
            "configuration_ref", config)
        if capability is None:
            builder.add("registered-scan-capability-unknown",
                        sources["verifier_capability"].target,
                        "verifier capability is not registered", sources["verifier_capability"])
        else:
            script_path = capability["implementation_path"]
            try:
                script_absolute = _canonical_repository_file(
                    builder.root, script_path, singly_linked=True)
                builder.edges.append(DependencyEdge(
                    kind="verifier-capability", owner_id=scan_id,
                    target_id=capability_id, path=script_path))
            except (OSError, ValueError) as exc:
                builder.add("registered-scan-capability-implementation",
                            sources["verifier_capability"].target, str(exc),
                            sources["verifier_capability"])
            if capability["configuration"] == "required" and config is None:
                builder.add("registered-scan-config-required", config_source.target,
                            "selected verifier requires a configuration reference", config_source)
            elif capability["configuration"] == "none" and config is not None:
                builder.add("registered-scan-config-forbidden", config_source.target,
                            "selected verifier accepts no configuration", config_source)
        if config is not None:
            dependency = builder.profile_dependency(
                "scan-config", scan_id, config, config_source, profile_repo_dir)
        parsed.append(RegisteredScan(
            scan_id, row["activation_role"], row["scope"], capability_id,
            script_path, script_absolute, dependency, row["candidate_predicate"],
            row["judgment_item_id"], bool(REQUIRED_SCAN_RE.search(row["activation_role"])),
            sources["scan_id"]))
    if sum(item.required_for_k12_item_6 for item in parsed) != 1:
        builder.add("registered-scans-required-count", builder.manifest_relative,
                    "exactly one K12/09 item 6 scan must be registered")
    return tuple(parsed)


def _vocabulary_extensions(builder, document):
    fields = tuple(VocabularyField(key, value.get("role"), tuple(value["values"]))
                   for key, value in sorted(document["fields"].items()))
    defaults = tuple(sorted(document["volatility_defaults"].items()))
    base = vocabulary_contract.load_vocabulary_base(
        builder.root, text=_root_text(
            builder.root, KERNEL_VOCABULARY_PATH, builder.root_input_snapshots))
    allowed = frozenset(base["volatility_values"])
    for domain, volatility in defaults:
        if volatility not in allowed:
            builder.add("extension-gate-vocabulary-registry", builder.manifest_relative,
                        "volatility domain %r names an unknown Kernel value %r" %
                        (domain, volatility))
    return fields, defaults


def _metadata_binding_field_ids(document):
    return {entry["field"]: (collection, entry)
            for collection in ("extension_fields", "relationship_extensions")
            for entry in document[collection]}


def _parse_batch_review_requirements(builder, document, role_ids, judgments):
    wrapper = document["batch_review_requirements"]
    judgment_ids = {item.judgment_item_id for item in judgments}
    parsed, seen = [], set()
    for row, sources in _rows(builder, "routing-and-gate-registry",
                              "batch_review_requirements.items", wrapper["items"]):
        identity, role_id = row["judgment_item_id"], row["pass_authority_role_id"]
        if identity not in judgment_ids:
            builder.add("batch-review-judgment-reference", sources["judgment_item_id"].target,
                        "batch review Judgment Item is not registered", sources["judgment_item_id"])
        if identity in seen:
            builder.add("batch-review-judgment-duplicate", sources["judgment_item_id"].target,
                        "Judgment Item is required more than once", sources["judgment_item_id"])
        seen.add(identity)
        if role_id not in role_ids:
            builder.add("batch-review-role-reference", sources["pass_authority_role_id"].target,
                        "batch review pass-authority role is not registered",
                        sources["pass_authority_role_id"])
        builder.edges.append(DependencyEdge(
            kind="batch-review-judgment", owner_id="batch-review:" + identity,
            target_id=identity))
        parsed.append(BatchReviewRequirement(
            identity, row["target_selector"], row["trigger"], row["producer_kind"],
            row["receipt_schema"], role_id, sources["judgment_item_id"]))
    return wrapper["mode"], tuple(parsed)


def _rendering_contract(builder, document):
    capabilities = rendering_contract.rendering_capability_records(
        kblib.parse_yaml_subset(_root_text(
            builder.root, rendering_contract.CAPABILITY_REGISTRY_PATH,
            builder.root_input_snapshots)))
    rules = []
    for row, sources in _rows(builder, "rendering-contract", "rules", document["rules"]):
        capability = capabilities.get(row["capability_id"])
        if capability is None or not any(
                item["construct"] == row["construct"] and item["acceptance"] == row["acceptance"]
                for item in capability["acceptance_bindings"]):
            builder.add("profile-rendering-contract-invalid", sources["rule_id"].target,
                        "rendering rule has no registered capability/construct/acceptance tuple",
                        sources["rule_id"])
        rules.append(RenderingRule(**row))
    builder.edges.append(DependencyEdge(
        kind="rendering-capability-registry", owner_id=RENDERING_CONTRACT_SLOT,
        path=rendering_contract.CAPABILITY_REGISTRY_PATH))
    return RenderingContract(
        registration=document["registration"], rules=tuple(rules),
        source_path=builder.manifest_relative, fingerprint=kblib.sha256_bytes(
            builder.read_profile_text(builder.manifest_relative)))



def _validate_domain_slots(builder, interface, slots):
    """Invoke each retained Kernel owner's evaluator on its typed values."""
    references = builder.encoding["registry_references"]
    snapshots = builder.root_input_snapshots
    owner_text = lambda key: _root_text(builder.root, references[key], snapshots)
    corpus_owner = corpus_planning_contract.load_corpus_planning_contract(
        builder.root, text=owner_text("corpus_planning_contract"))
    _normalized, issues = corpus_planning_contract.validate_corpus_planning_envelope(
        _slot_document("corpus-planning", slots["corpus-planning"]), contract=corpus_owner)
    for issue in issues:
        builder.add("profile-corpus-planning-contract", builder.manifest_relative, str(issue))
    structure_owner = kblib.load_structure_registry_contract(
        builder.root, text=owner_text("structure_registry_contract"))
    for check, target, detail in kblib.validate_structure_registry_shape(
            _slot_document("structure-registry", slots["structure-registry"]),
            target=builder.manifest_relative + "#slots.structure-registry", contract=structure_owner):
        builder.add(check, target, detail)
    metadata_owner = kblib.load_metadata_profile_contract(
        builder.root, text=owner_text("metadata_profile_contract"))
    for check, target, detail in kblib.validate_metadata_contract_shape(
            _slot_document("metadata-contract", slots["metadata-contract"]),
            target=builder.manifest_relative + "#slots.metadata-contract", contract=metadata_owner):
        builder.add(check, target, detail)
    vocabulary_owner = vocabulary_contract.load_vocabulary_extensions_contract(
        builder.root, text=owner_text("vocabulary_extensions_contract"))
    for detail in vocabulary_contract.validate_vocabulary_extensions(
            thaw(slots["vocabulary-extensions"]), contract=vocabulary_owner):
        builder.add("extension-gate-vocabulary-registry", builder.manifest_relative, detail)
    rendering_owner = rendering_contract.load_rendering_shape(
        builder.root, text=owner_text("profile_rendering_contract"))
    for detail in rendering_contract.validate_rendering_shape(
            thaw(slots["rendering-contract"]), contract=rendering_owner):
        builder.add("profile-rendering-contract-invalid", builder.manifest_relative, detail)



def _parse_extension_gates(builder, document, profile_repo_dir, profile_id,
                           role_ids, vocabulary_fields, metadata_document, judgments, scans):
    wrapper = document["extension_gates"]
    registration, rows = wrapper["mode"], wrapper["items"]
    if not rows:
        return registration, ()
    source_path = builder.manifest_relative
    root_input_snapshots = builder.root_input_snapshots
    vocabulary = {item.field_id: item.values for item in vocabulary_fields}
    metadata_fields = {row["field"]: row for row in metadata_document["extension_fields"]}
    kernel_metadata_fields = _kernel_metadata_fields(
        builder, source_path, root_input_snapshots=root_input_snapshots)
    kernel_gate_ids = None
    checker, supports = _capability_registry(
        builder, source_path, root_input_snapshots=root_input_snapshots)
    judgment_by_id = {}
    for item in judgments:
        judgment_by_id.setdefault(item.judgment_item_id, []).append(item)
    scan_by_judgment = {}
    for scan in scans:
        scan_by_judgment.setdefault(scan.judgment_item_id, []).append(scan)

    parsed = []
    seen_gate_ids = set()
    seen_transitions = set()
    for row, sources in _rows(builder, "routing-and-gate-registry",
                              "extension_gates.items", rows):
        for optional in ("vocabulary_field",):
            sources.setdefault(optional, builder.source(
                "slots.routing-and-gate-registry.extension_gates", optional, row.get(optional)))
        gate_id = row["gate_id"]
        owner_literal = row["owner_ref"]
        transition_id = row["blocked_transition"]
        role_id = row["pass_authority_role_id"]
        field_id = row.get("vocabulary_field")
        completion_values = tuple(row["completion_values"])
        judgment_id = row["judgment_item_id"]
        producer_kind = row["producer_kind"]
        producer_capability = row["producer_capability"]
        receipt_schema = row["receipt_schema"]
        consumer_capability = row["consumer_capability"]
        valid = True

        if gate_id.split(":", 2)[1] != profile_id:
            builder.add(
                "extension-gate-id-invalid", sources["gate_id"].target,
                "Gate ID %r must be `P:%s:<lowercase-kebab-name>`" %
                (gate_id, profile_id), sources["gate_id"])
            valid = False
        if gate_id in seen_gate_ids:
            builder.add(
                "extension-gate-id-duplicate", sources["gate_id"].target,
                "Gate ID %r is registered more than once" % gate_id,
                sources["gate_id"])
            valid = False
        seen_gate_ids.add(gate_id)

        if transition_id in seen_transitions:
            builder.add(
                "extension-gate-transition-duplicate", sources["blocked_transition"].target,
                "blocked transition/action ID %r is already owned by another "
                "extension Gate" % transition_id, sources["blocked_transition"])
            valid = False
        seen_transitions.add(transition_id)

        owner_gate_id = None
        owner_dependency = None
        if "/" in owner_literal or "#" in owner_literal:
            owner_dependency = builder.repository_dependency(
                "extension-gate-owner", gate_id, row["owner_ref"], sources["owner_ref"],
                profile_repo_dir)
            if owner_dependency is None:
                valid = False
        else:
            if kernel_gate_ids is None:
                kernel_gate_ids = _kernel_gate_ids(
                    builder, root_input_snapshots=root_input_snapshots)
            if (not STABLE_ID_RE.fullmatch(owner_literal) or
                    owner_literal not in kernel_gate_ids):
                builder.add(
                    "extension-gate-owner-reference", sources["owner_ref"].target,
                    "owner Gate ID %r does not resolve in the kernel Stable "
                    "Gate ID Registry" % owner_literal, sources["owner_ref"])
                valid = False
            else:
                owner_gate_id = owner_literal
                builder.edges.append(DependencyEdge(
                    kind="extension-gate-owner", owner_id=gate_id,
                    target_id=owner_gate_id))

        if role_id not in role_ids:
            builder.add(
                "extension-gate-role-reference", sources["pass_authority_role_id"].target,
                "pass-authority Role ID %r is not registered by this Profile"
                % role_id, sources["pass_authority_role_id"])
            valid = False

        if field_id is None:
            if completion_values:
                builder.add(
                    "extension-gate-field-completion", sources["completion_values"].target,
                    "completion values require a Vocabulary field ID",
                    sources["completion_values"])
                valid = False
        else:
            if not FIELD_ID_RE.fullmatch(field_id) or field_id not in vocabulary:
                builder.add(
                    "extension-gate-field-reference", sources["vocabulary_field"].target,
                    "Vocabulary field ID %r is not a registered Profile field"
                    % field_id, sources["vocabulary_field"])
                valid = False
            if kernel_metadata_fields is None:
                valid = False
            elif field_id in kernel_metadata_fields:
                builder.add(
                    "extension-gate-field-kernel-collision",
                    sources["vocabulary_field"].target,
                    "typed Profile Gate field %r collides with the frozen "
                    "Kernel metadata namespace" % field_id, sources["vocabulary_field"])
                valid = False
            if field_id not in metadata_fields:
                builder.add(
                    "extension-gate-field-applicability", sources["vocabulary_field"].target,
                    "typed Gate field %r must be declared by this Profile's "
                    "Metadata Contract extension_fields; kernel-managed and "
                    "vocabulary-only fields cannot be projected by a Profile "
                    "Gate" % field_id, sources["vocabulary_field"])
                valid = False
            elif metadata_fields[field_id].get("shape") != "nonempty-string":
                builder.add(
                    "extension-gate-field-shape", sources["vocabulary_field"].target,
                    "typed Gate field %r must have Metadata Contract shape "
                    "nonempty-string for enum projection" % field_id,
                    sources["vocabulary_field"])
                valid = False
            if not completion_values:
                builder.add(
                    "extension-gate-field-completion", sources["completion_values"].target,
                    "a Vocabulary field Gate requires at least one registered "
                    "completion value", sources["completion_values"])
                valid = False
            if len(set(completion_values)) != len(completion_values) or any(
                    not VOCABULARY_VALUE_RE.fullmatch(value)
                    for value in completion_values):
                builder.add(
                    "extension-gate-completion-invalid", sources["completion_values"].target,
                    "completion values must be unique lowercase vocabulary "
                    "tokens", sources["completion_values"])
                valid = False
            unknown_values = sorted(
                set(completion_values).difference(vocabulary.get(field_id, ())))
            if field_id in vocabulary and unknown_values:
                builder.add(
                    "extension-gate-completion-reference", sources["completion_values"].target,
                    "completion value(s) are not registered for %s: %s" %
                    (field_id, ", ".join(unknown_values)), sources["completion_values"])
                valid = False
            if not _capability_supports(
                    builder, supports,
                    PROFILE_EXTENSION_ENUM_WRITER_CAPABILITY,
                    PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION,
                    sources["vocabulary_field"], kind="writer"):
                builder.add(
                    "extension-gate-writer-capability", sources["vocabulary_field"].target,
                    "typed Profile Gate field %r requires installed writer "
                    "%r operation %r" %
                    (field_id, PROFILE_EXTENSION_ENUM_WRITER_CAPABILITY,
                     PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION),
                    sources["vocabulary_field"])
                valid = False

        judgment_matches = judgment_by_id.get(judgment_id, ())
        if len(judgment_matches) != 1:
            builder.add(
                "extension-gate-judgment-reference", sources["judgment_item_id"].target,
                "Judgment Item reference %r must resolve exactly once; found "
                "%d" % (judgment_id, len(judgment_matches)), sources["judgment_item_id"])
            valid = False

        expected_capability = PRODUCER_CAPABILITY_BY_KIND.get(producer_kind)
        if (not _capability_registered(
                builder, checker, producer_capability, "producer", sources["producer_capability"]) or
                producer_capability != expected_capability):
            builder.add(
                "extension-gate-producer-capability", sources["producer_capability"].target,
                "producer capability %r is not the registered capability for "
                "producer kind %r" % (producer_capability, producer_kind),
                sources["producer_capability"])
            valid = False
        expected_schema = RECEIPT_SCHEMA_BY_KIND.get(producer_kind)
        if (not _capability_registered(
                builder, checker, receipt_schema, "receipt-schema", sources["receipt_schema"]) or
                receipt_schema != expected_schema):
            builder.add(
                "extension-gate-receipt-schema", sources["receipt_schema"].target,
                "receipt schema %r is not the registered schema for producer "
                "kind %r" % (receipt_schema, producer_kind), sources["receipt_schema"])
            valid = False
        consumer_operation = (
            FIELD_GATE_CONSUMER_OPERATION if field_id is not None else
            NON_FIELD_GATE_CONSUMER_OPERATION)
        consumer_registered = _capability_registered(
            builder, checker, consumer_capability, "consumer", sources["consumer_capability"])
        consumer_supports_transition = _capability_supports(
            builder, supports, consumer_capability,
            consumer_operation, sources["consumer_capability"])
        if not (consumer_registered and consumer_supports_transition):
            builder.add(
                "extension-gate-consumer-capability", sources["consumer_capability"].target,
                "consumer capability %r is not registered with the "
                "%r operation required by this Gate shape" %
                (consumer_capability, consumer_operation),
                sources["consumer_capability"])
            valid = False

        if (producer_kind == "deterministic" and field_id is not None and
                len(completion_values) != 1):
            builder.add(
                "extension-gate-deterministic-completion", sources["completion_values"].target,
                "a deterministic typed-field Gate must declare exactly one "
                "completion value, so scan pass has one closed projection",
                sources["completion_values"])
            valid = False

        producer_reference = None
        if producer_kind == "manual-attestation":
            producer_reference = role_id if role_id in role_ids else None
        elif producer_kind == "deterministic":
            producer_matches = scan_by_judgment.get(judgment_id, ())
            if len(producer_matches) != 1:
                builder.add(
                    "extension-gate-producer-reference", sources["producer_capability"].target,
                    "deterministic Gate Judgment Item %r must be produced by "
                    "exactly one Registered Scan; found %d" %
                    (judgment_id, len(producer_matches)), sources["producer_capability"])
                valid = False
            else:
                producer_reference = producer_matches[0].scan_id

        if not valid:
            continue
        builder.edges.extend((
            DependencyEdge(
                kind="extension-gate-transition", owner_id=gate_id,
                target_id=transition_id),
            DependencyEdge(
                kind="extension-gate-role", owner_id=gate_id,
                target_id=role_id),
            DependencyEdge(
                kind="extension-gate-judgment", owner_id=gate_id,
                target_id=judgment_id),
            DependencyEdge(
                kind="extension-gate-producer-capability", owner_id=gate_id,
                target_id=producer_capability),
            DependencyEdge(
                kind="extension-gate-producer", owner_id=gate_id,
                target_id=producer_reference),
            DependencyEdge(
                kind="extension-gate-receipt-schema", owner_id=gate_id,
                target_id=receipt_schema),
            DependencyEdge(
                kind="extension-gate-consumer-capability", owner_id=gate_id,
                target_id=consumer_capability),
        ))
        if field_id is not None:
            builder.edges.append(DependencyEdge(
                kind="extension-gate-field", owner_id=gate_id,
                target_id=field_id))
        parsed.append(ExtensionGate(
            gate_id=gate_id,
            owner_gate_id=owner_gate_id,
            owner_dependency=owner_dependency,
            transition_id=transition_id,
            pass_authority_role_id=role_id,
            applicability=row["applicability"],
            field_id=field_id,
            completion_values=completion_values,
            judgment_item_id=judgment_id,
            producer_kind=producer_kind,
            producer_capability=producer_capability,
            producer_reference=producer_reference,
            receipt_schema=receipt_schema,
            consumer_capability=consumer_capability,
            source=sources["gate_id"],
            field_values=(tuple(vocabulary.get(field_id, ()))
                          if field_id is not None else ()),
        ))
    return registration, tuple(parsed)



def _parse_registered_artifacts(builder, document, profile_repo_dir,
                                vocabulary_fields, metadata_document, gates):
    wrapper = document["registered_artifacts"]
    registration, rows = wrapper["mode"], wrapper["items"]
    source_path = builder.manifest_relative
    root_input_snapshots = builder.root_input_snapshots
    declared_contracts = {}
    for definition, definition_sources in _rows(
            builder, "expression-layer-entry", "artifact_contracts", document["artifact_contracts"]):
        contract_id = definition["contract_id"]
        if contract_id in declared_contracts:
            builder.add("expression-contract-id-duplicate", definition_sources["contract_id"].target,
                        "artifact contract ID is declared more than once",
                        definition_sources["contract_id"])
        declared_contracts[contract_id] = definition["body_ref"]
        builder.profile_dependency(
            "expression-contract-definition", contract_id, definition["body_ref"],
            definition_sources["body_ref"], profile_repo_dir, require_heading=True)
    registered_references = set(declared_contracts.values())
    consumed_references = {row["contract_ref"] for row in rows}
    if registered_references != consumed_references:
        builder.add("expression-contract-reference-closure", source_path,
                    "artifact contracts and registered artifact owner references must match")
    if not rows:
        return registration, ()

    try:
        base = vocabulary_contract.load_vocabulary_base(
            builder.root,
            text=_root_text(builder.root, KERNEL_VOCABULARY_PATH, root_input_snapshots))
        allowed_types = set(base["field_values"].get("type", ()))
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        builder.add(
            "expression-artifact-type-registry", source_path,
            "cannot load the Kernel-owned type vocabulary: %s" % exc)
        allowed_types = set()
    fields_by_id = {field.field_id: field for field in vocabulary_fields}
    type_extension = fields_by_id.get("type")
    if type_extension is not None:
        allowed_types.update(type_extension.values)
    metadata_fields = _metadata_binding_field_ids(metadata_document)
    gates_by_field = {}
    for gate in gates:
        if gate.field_id is not None:
            gates_by_field.setdefault(gate.field_id, []).append(gate)

    parsed = []
    seen = set()
    for row, sources in _rows(builder, "expression-layer-entry",
                              "registered_artifacts.items", rows):
        for optional in ("dependency_map", "readiness_field"):
            sources.setdefault(optional, builder.source(
                "slots.expression-layer-entry.registered_artifacts", optional, row.get(optional)))
        artifact_id, artifact_type = row["artifact_id"], row["artifact_type"]
        label, entry_point = row["label"], row["entry_point"]
        dependency_map_path = row.get("dependency_map")
        binding_field_ids = tuple(row["metadata_fields"])
        revalidation_trigger = row["revalidation_trigger"]
        readiness_field_id = row.get("readiness_field")
        valid = True

        if not STABLE_ID_RE.fullmatch(artifact_id):
            builder.add(
                "expression-artifact-id-invalid", sources["artifact_id"].target,
                "Stable artifact ID %r must be lowercase kebab-case" %
                artifact_id, sources["artifact_id"])
            valid = False
        if artifact_id in seen:
            builder.add(
                "expression-artifact-id-duplicate", sources["artifact_id"].target,
                "Stable artifact ID %r is registered more than once" %
                artifact_id, sources["artifact_id"])
            valid = False
        seen.add(artifact_id)
        if artifact_type not in allowed_types:
            builder.add(
                "expression-artifact-type-unknown", sources["artifact_type"].target,
                "Artifact type %r is not in the composed Kernel + Profile "
                "`type` vocabulary" % artifact_type, sources["artifact_type"])
            valid = False
        try:
            canonical_repository_relative_path(entry_point, "entry point")
        except ValueError as exc:
            builder.add(
                "expression-artifact-entry-invalid", sources["entry_point"].target,
                str(exc), sources["entry_point"])
            valid = False
        else:
            builder.edges.append(DependencyEdge(
                kind="expression-entry", owner_id=artifact_id,
                path=entry_point))
        if dependency_map_path is not None:
            try:
                canonical_repository_relative_path(
                    dependency_map_path, "dependency-map path")
            except ValueError as exc:
                builder.add(
                    "expression-artifact-dependency-map-invalid",
                    sources["dependency_map"].target, str(exc), sources["dependency_map"])
                valid = False
            else:
                builder.edges.append(DependencyEdge(
                    kind="expression-dependency-map", owner_id=artifact_id,
                    path=dependency_map_path))
        if (len(binding_field_ids) != len(set(binding_field_ids)) or
                any(FIELD_ID_RE.fullmatch(field_id) is None
                    for field_id in binding_field_ids)):
            builder.add(
                "expression-artifact-binding-invalid", sources["metadata_fields"].target,
                "Metadata binding field IDs must be unique lowercase "
                "snake_case values", sources["metadata_fields"])
            valid = False
        unknown_bindings = sorted(
            set(binding_field_ids) - set(metadata_fields))
        if unknown_bindings:
            builder.add(
                "expression-artifact-binding-unknown", sources["metadata_fields"].target,
                "Metadata binding field ID(s) are not declared by the "
                "Profile Metadata Contract: %s" %
                ", ".join(unknown_bindings), sources["metadata_fields"])
            valid = False
        invalid_binding_shapes = sorted(
            field_id for field_id in binding_field_ids
            if field_id in metadata_fields and
            not (
                (metadata_fields[field_id][0] == "extension_fields" and
                 metadata_fields[field_id][1].get("shape") == "path") or
                (metadata_fields[field_id][0] ==
                 "relationship_extensions" and
                 metadata_fields[field_id][1].get("shape") ==
                 "list-of-paths" and
                 metadata_fields[field_id][1].get("direction") ==
                 "expression-to-canonical")
            ))
        if invalid_binding_shapes:
            builder.add(
                "expression-artifact-binding-shape", sources["metadata_fields"].target,
                "Metadata binding field ID(s) must be an extension `path` "
                "or an `expression-to-canonical` relationship with "
                "`list-of-paths` shape: %s" %
                ", ".join(invalid_binding_shapes), sources["metadata_fields"])
            valid = False
        for field_id in binding_field_ids:
            builder.edges.append(DependencyEdge(
                kind="expression-binding-field", owner_id=artifact_id,
                target_id=field_id))
        if dependency_map_path is None and not binding_field_ids:
            builder.add(
                "expression-artifact-binding-missing", sources["dependency_map"].target,
                "each artifact requires a dependency-map path, at least one "
                "Metadata binding field ID, or both", sources["dependency_map"])
            valid = False

        contract_owner = builder.profile_dependency(
            "expression-contract", artifact_id, row["contract_ref"], sources["contract_ref"],
            profile_repo_dir, require_heading=True)
        if contract_owner is None:
            valid = False
        if readiness_field_id is not None:
            field = fields_by_id.get(readiness_field_id)
            if (field is None or
                    field.role != EXPRESSION_STATUS_AXIS_ROLE):
                builder.add(
                    "expression-artifact-readiness-field", sources["readiness_field"].target,
                    "Readiness field ID %r must name a Vocabulary field with "
                    "role `%s`" % (readiness_field_id,
                                   EXPRESSION_STATUS_AXIS_ROLE), sources["readiness_field"])
                valid = False
            if readiness_field_id not in metadata_fields:
                builder.add(
                    "expression-artifact-readiness-metadata",
                    sources["readiness_field"].target,
                    "Readiness field ID %r must be declared by the Profile "
                    "Metadata Contract" % readiness_field_id, sources["readiness_field"])
                valid = False
            matching_gates = gates_by_field.get(readiness_field_id, ())
            if len(matching_gates) != 1:
                builder.add(
                    "expression-artifact-readiness-gate", sources["readiness_field"].target,
                    "Readiness field ID %r must bind exactly one extension "
                    "Gate; found %d" %
                    (readiness_field_id, len(matching_gates)), sources["readiness_field"])
                valid = False
            builder.edges.append(DependencyEdge(
                kind="expression-readiness-field", owner_id=artifact_id,
                target_id=readiness_field_id))
        if valid and contract_owner is not None:
            parsed.append(RegisteredExpressionArtifact(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                label=label,
                entry_point=entry_point,
                dependency_map_path=dependency_map_path,
                binding_field_ids=tuple(binding_field_ids),
                revalidation_trigger=revalidation_trigger,
                contract_owner=contract_owner,
                readiness_field_id=readiness_field_id,
                source=sources["artifact_id"],
            ))
    return registration, tuple(parsed)




def _link_body_references(builder, slots, profile_repo_dir):
    residual = slots["audit-dimension-registry"]["residual_disposition"]
    source = builder.source("slots.audit-dimension-registry.residual_disposition",
                            "body_ref", residual["body_ref"])
    builder.profile_dependency("residual-policy", "residual-disposition",
                               residual["body_ref"], source, profile_repo_dir)


def load_profile_contract(root, manifest_path, sentinel="TODO(profile)",
                          profile_snapshot=None, root_input_snapshots=None,
                          root_snapshot_resolver=None):
    """Compile the only supported Profile format into a fully linked model.

    Shape validation is necessary, but CUE success alone never authorizes
    runtime consumption. Every real dependency and installed capability must
    also link. The outer profile-load Gate still owns its complete evaluation.
    """
    builder = _Builder(root, manifest_path, sentinel, root_input_snapshots,
                       root_snapshot_resolver)
    absolute = relative = profile_dir = ""
    try:
        absolute, relative, profile_dir, text = _read_candidate(builder, profile_snapshot)
        profile_id = _check_identity(builder)
        builder.scan_text_sentinel(text, relative, "Profile answers")
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        builder.add("profile-contract-input", builder.manifest_input, str(exc))
        return _empty_contract(builder, absolute, relative,
                               os.path.dirname(absolute), profile_dir)
    try:
        interface, sources, validation = _schema_check(builder)
        audit_dimension_contract.current_audit_dimension_values(
            builder.root, snapshots=root_input_snapshots)
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        builder.add("profile-contract-owner", relative, str(exc))
        return _empty_contract(builder, absolute, relative,
                               os.path.dirname(absolute), profile_dir)
    if not validation.valid:
        for detail in validation.diagnostics:
            builder.add("profile-contract-schema", relative, detail)
        return _empty_contract(builder, absolute, relative,
                               os.path.dirname(absolute), profile_dir)

    slots = builder.document["slots"]
    for identifier, values in slots.items():
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=_SHIPPED_SLOT_NAMES[identifier],
            path=relative, fragment="slots." + identifier))
    dimensions = judgments = scans = gates = requirements = artifacts = ()
    vocabulary_fields = volatility_defaults = ()
    registration = gate_registration = review_registration = expression_registration = None
    rendering = None
    roles = frozenset()
    try:
        _validate_domain_slots(builder, interface, slots)
        scan_capabilities = scan_capability_records(
            load_scan_capabilities(builder.root, snapshots=root_input_snapshots))
        registration, dimensions = _parse_extensions(
            builder, slots["audit-dimension-registry"])
        judgments = _parse_judgments(
            builder, slots["audit-dimension-registry"], profile_dir, dimensions)
        scans = _parse_scans(
            builder, slots["registered-scan-registry"], profile_dir, scan_capabilities)
        vocabulary_fields, volatility_defaults = _vocabulary_extensions(
            builder, slots["vocabulary-extensions"])
        judgment_ids = {}
        for item in judgments:
            judgment_ids.setdefault(item.judgment_item_id, []).append(item)
        for scan in scans:
            matches = judgment_ids.get(scan.judgment_item_id, ())
            if len(matches) != 1:
                builder.add("registered-scan-judgment-reference", scan.source.target,
                            "scan Judgment Item must resolve exactly once", scan.source)
            else:
                builder.edges.append(DependencyEdge(
                    kind="scan-judgment", owner_id=scan.scan_id,
                    target_id=scan.judgment_item_id))
        roles = _role_ids(builder, slots["role-registry"])
        gate_registration, gates = _parse_extension_gates(
            builder, slots["routing-and-gate-registry"], profile_dir, profile_id,
            roles, vocabulary_fields, slots["metadata-contract"], judgments, scans)
        review_registration, requirements = _parse_batch_review_requirements(
            builder, slots["routing-and-gate-registry"], roles, judgments)
        expression_registration, artifacts = _parse_registered_artifacts(
            builder, slots["expression-layer-entry"], profile_dir, vocabulary_fields,
            slots["metadata-contract"], gates)
        rendering = _rendering_contract(builder, slots["rendering-contract"])
        _link_body_references(builder, slots, profile_dir)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        builder.add("profile-contract-link", relative,
                    "cannot link the Profile against its owned inputs: %s" % exc)
    edges = tuple(sorted(builder.edges, key=lambda item: (
        item.kind, item.owner_id, item.target_id or "", item.path or "", item.fragment or "")))
    return ProfileContract(
        root=builder.root, manifest_path=absolute, manifest_repo_path=relative,
        profile_root=os.path.dirname(absolute), profile_repo_dir=profile_dir,
        audit_registry_path=relative, scan_registry_path=relative, routing_registry_path=relative,
        extension_registration=registration, extension_dimensions=tuple(dimensions),
        judgment_items=tuple(judgments), registered_scans=tuple(scans),
        extension_gate_registration=gate_registration, extension_gates=tuple(gates),
        batch_review_registration=review_registration, batch_review_requirements=tuple(requirements),
        vocabulary_fields=tuple(vocabulary_fields), volatility_defaults=tuple(volatility_defaults),
        expression_registry_path=relative, expression_registration=expression_registration,
        expression_artifacts=tuple(artifacts), rendering_contract=rendering,
        dependency_edges=edges, source_cells=tuple(builder.source_cells),
        diagnostics=tuple(builder.diagnostics), profile_id=profile_id, slot_values=slots,
        execution_default_overrides=tuple(sorted(
            builder.document.get("execution_default_overrides", {}).items())),
        cue_source_paths=tuple(sorted(sources)),
        role_ids=roles,
    )
