#!/usr/bin/env python3
"""Typed, fail-closed linker for one selected Cambium Profile.

The Profile manifest names its slot files, but three of those files contain
machine-active references of their own:

* Audit Dimension Registry judgment items point at predicate-owner files and
  optional headings.
* Registered Scan Registry rows point at verifier tools, optional Profile-owned
  configuration files, and judgment items.
* Routing And Gate Registry extension rows bind a transition to one semantic
  owner, pass-authority role, judgment item, producer, receipt schema, and
  runtime consumer capability.

This module is the one parser and resolver for that transitive contract.  It
does not select a Profile, execute a verifier, write a receipt, or judge the
quality of a predicate.  A partial parse is retained only for deterministic
diagnostics; ``authorized`` is false and command compilation/fingerprinting is
unavailable whenever any diagnostic exists.
"""
from Tools.platform.repository.path_contract import \
    canonical_repository_relative_path
from Tools.platform.repository.repository import repository_source_root

from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from types import MappingProxyType
from typing import Optional, Tuple

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.governance.control.control_registry_contract as control_registry_contract
import Tools.execution.planning.corpus_planning_contract as corpus_planning_contract
import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader
import Tools.platform.common.kblib as kblib
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.knowledge.metadata.vocabulary_contract as vocabulary_contract


PROFILE_INTERFACE_PATH = (
    "kernel/K00 Standards Control/profile-interface.yaml")
AUDIT_DIMENSION_BASE_PATH = \
    audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH
SCAN_CAPABILITY_PATH = "Tools/scan-capabilities.yaml"

# Public durable evidence emitted by one authorized ``profile-load``.  The
# parser/linker owns this shape because it is the producer of the typed Profile
# identity; runtime consumers project it instead of maintaining receipt-field
# quartets of their own.
PROFILE_LOAD_GATE_ID = "profile-load"
PROFILE_LOAD_EVIDENCE_FIELDS = (
    "selected_profile_manifest",
    "profile_snapshot_sha256",
    "profile_contract_fingerprint",
    "profile_load_inputs_sha256",
)
PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS = \
    PROFILE_LOAD_EVIDENCE_FIELDS[1:]

@dataclass(frozen=True)
class ProfileForm:
    """One Kernel-owned Profile file form.

    The form binds one canonical file location to either a Markdown form
    skeleton or a referenced Kernel-owned YAML shape contract. Candidate
    prose, template answers, and instance values remain outside this machine
    contract.
    """

    path: str
    required_headings: Tuple[str, ...]
    yaml_shape_owner: Optional[Tuple[str, str]]
    instance_subheading_containers: Tuple[
        Tuple[str, Tuple[str, ...]], ...]


def _profile_form(value, label):
    if not isinstance(value, dict) or "path" not in value:
        raise ValueError("%s fields are not closed" % label)
    path = canonical_repository_relative_path(
        value.get("path"), "%s path" % label)
    if not path.endswith((".md", ".yaml")):
        raise ValueError("%s path must end in .md or .yaml" % label)
    markdown = path.endswith(".md")
    expected_fields = (
        {"path", "required_headings", "instance_subheading_containers"}
        if markdown else {"path", "shape_owner"})
    if set(value) != expected_fields:
        raise ValueError(
            "%s fields are not closed for a %s form" %
            (label, "Markdown" if markdown else "YAML"))
    headings = value.get("required_headings", [])
    yaml_shape_owner = value.get("shape_owner")
    containers = value.get("instance_subheading_containers", [])
    if (not isinstance(headings, list) or
            any(not isinstance(item, str) for item in headings) or
            len(headings) != len(set(headings))):
        raise ValueError("%s required_headings must be a unique string list" %
                         label)
    if markdown and not headings:
        raise ValueError("%s Markdown form must declare headings" % label)
    parsed_yaml_shape_owner = None
    if not markdown:
        if not isinstance(yaml_shape_owner, dict) or set(yaml_shape_owner) != {
                "contract_id", "registry_reference"}:
            raise ValueError(
                "%s YAML shape_owner fields are not closed" % label)
        contract_id = yaml_shape_owner.get("contract_id")
        registry_reference = yaml_shape_owner.get("registry_reference")
        for field, item in (("contract_id", contract_id),
                            ("registry_reference", registry_reference)):
            if (not isinstance(item, str) or
                    re.fullmatch(r"[a-z][a-z0-9_-]*", item) is None):
                raise ValueError(
                    "%s YAML shape_owner %s is invalid" % (label, field))
        parsed_yaml_shape_owner = (contract_id, registry_reference)
    parsed = []
    for item in headings:
        heading = kblib.markdown_atx_heading(item)
        if (heading is None or heading[0] not in (1, 2) or
                item != "%s %s" % ("#" * heading[0], heading[1])):
            raise ValueError(
                "%s required heading %r must be one canonical H1/H2" %
                (label, item))
        parsed.append(heading)
    parsed_containers = []
    for index, item in enumerate(containers):
        if not isinstance(item, dict) or set(item) != {
                "heading", "reference_kinds"}:
            raise ValueError(
                "%s instance subheading container %d fields are not closed" %
                (label, index))
        heading_text = item.get("heading")
        reference_kinds = item.get("reference_kinds")
        if (not isinstance(reference_kinds, list) or not reference_kinds or
                any(not isinstance(kind, str) or
                    re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", kind)
                    is None for kind in reference_kinds) or
                len(reference_kinds) != len(set(reference_kinds))):
            raise ValueError(
                "%s instance subheading container %d reference_kinds must "
                "be a non-empty unique kebab-case list" % (label, index))
        heading = kblib.markdown_atx_heading(heading_text)
        if (heading is None or heading[0] != 2 or
                heading_text != "## %s" % heading[1] or
                heading_text not in headings):
            raise ValueError(
                "%s instance subheading container %r must name one required "
                "H2" % (label, heading_text))
        parsed_containers.append(
            (heading_text, tuple(reference_kinds)))
    if len({item[0] for item in parsed_containers}) != \
            len(parsed_containers):
        raise ValueError(
            "%s instance subheading container headings must be unique" %
            label)
    return ProfileForm(
        path=path,
        required_headings=tuple(headings),
        yaml_shape_owner=parsed_yaml_shape_owner,
        instance_subheading_containers=tuple(parsed_containers),
    )


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
    snapshot = (snapshots or {}).get(SCAN_CAPABILITY_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        text = kblib.read_text(
            os.path.join(root, *SCAN_CAPABILITY_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    scan_capability_records(document)
    return document


def scan_capability_implementation_paths(document):
    return tuple(sorted(
        row["implementation_path"]
        for row in scan_capability_records(document).values()))


def profile_interface_slots(document):
    """Validate one interface document and return its ordered slot names."""
    if not isinstance(document, dict):
        raise ValueError("Profile interface must be a mapping")
    required = {
        "schema_version", "interface_id", "semantic_owner", "slots",
        "registry_references", "tables", "closed_sets",
        "capability_bindings", "manifest_form", "scalar_carrier_types",
        "scalar_carriers",
    }
    missing = sorted(required - set(document))
    extra = sorted(set(document) - required)
    if missing or extra:
        raise ValueError(
            "Profile interface fields are not closed: missing=%s extra=%s" %
            (missing, extra))
    if document.get("schema_version") != 3:
        raise ValueError("Profile interface schema_version must be 3")
    if document.get("interface_id") != "cambium-profile-interface":
        raise ValueError("Profile interface_id must be cambium-profile-interface")
    if document.get("semantic_owner") != "K00/19":
        raise ValueError("Profile semantic_owner must be K00/19")
    references = document.get("registry_references")
    if not isinstance(references, dict) or set(references) != {
            "audit_dimension_base", "corpus_planning_contract",
            "metadata_profile_contract", "structure_registry_contract",
            "vocabulary_extensions_contract"}:
        raise ValueError("Profile registry_references fields are not closed")
    if references.get("audit_dimension_base") != \
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH:
        raise ValueError(
            "Profile audit_dimension_base reference must be %s" %
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH)
    if references.get("corpus_planning_contract") != \
            corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH:
        raise ValueError(
            "Profile corpus_planning_contract reference must be %s" %
            corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH)
    for reference_id, path in references.items():
        try:
            path = canonical_repository_relative_path(
                path, "Profile registry reference %s" % reference_id)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not path.endswith(".yaml"):
            raise ValueError(
                "Profile registry reference %s must name one YAML file" %
                reference_id)
    manifest_form = _profile_form(
        document.get("manifest_form"), "Profile manifest form")
    if manifest_form.path != profile_layout_contract.PROFILE_MANIFEST_NAME:
        raise ValueError(
            "Profile manifest form path must be %s" %
            profile_layout_contract.PROFILE_MANIFEST_NAME)

    slots = document.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("Profile interface slots must be a non-empty list")
    names = []
    identifiers = []
    for index, row in enumerate(slots):
        if not isinstance(row, dict):
            raise ValueError("Profile interface slot %d must be a mapping" % index)
        if set(row) != {
                "slot_id", "name", "binding", "kernel_owner", "form"}:
            raise ValueError(
                "Profile interface slot %d fields are not closed" % index)
        name = row.get("name")
        slot_id = row.get("slot_id")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Profile interface slot %d has no name" % index)
        if not isinstance(slot_id, str) or not slot_id.strip():
            raise ValueError("Profile interface slot %d has no slot_id" % index)
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slot_id):
            raise ValueError("Profile interface slot %d has invalid slot_id" % index)
        if row.get("binding") != "file":
            raise ValueError("Profile interface slot %d must bind one file" % index)
        if not isinstance(row.get("kernel_owner"), str) or not \
                row["kernel_owner"].strip():
            raise ValueError("Profile interface slot %d has no Kernel owner" % index)
        form = _profile_form(
            row.get("form"), "Profile interface slot %d form" % index)
        if form.yaml_shape_owner is not None:
            _contract_id, registry_reference = form.yaml_shape_owner
            if registry_reference not in references:
                raise ValueError(
                    "Profile interface slot %d YAML shape owner names unknown "
                    "registry_reference %r" %
                    (index, registry_reference))
        names.append(name)
        identifiers.append(slot_id)
    if len(set(names)) != len(names) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Profile interface slot names and IDs must be unique")
    form_paths = [manifest_form.path] + [
        _profile_form(row["form"], "Profile interface slot form").path
        for row in slots
    ]
    if len(form_paths) != len(set(form_paths)):
        raise ValueError("Profile interface form paths must be unique")

    tables = document.get("tables")
    closed_sets = document.get("closed_sets")
    if not isinstance(tables, dict) or not tables:
        raise ValueError("Profile interface tables must be a non-empty mapping")
    if not isinstance(closed_sets, dict):
        raise ValueError("Profile interface closed_sets must be a mapping")
    table_cardinalities = closed_sets.get("table_cardinalities")
    if (not isinstance(table_cardinalities, list) or
            table_cardinalities != ["exactly-one"]):
        raise ValueError(
            "Profile interface table_cardinalities must be exactly "
            "['exactly-one']")
    forms_by_id = {"profile-manifest": manifest_form}
    forms_by_id.update({
        row["slot_id"]: _profile_form(
            row["form"], "Profile interface slot %s form" % row["name"])
        for row in slots
    })
    carrier_types = document.get("scalar_carrier_types")
    if not isinstance(carrier_types, dict) or not carrier_types:
        raise ValueError(
            "Profile interface scalar_carrier_types must be a non-empty "
            "mapping")
    for carrier_type, row in carrier_types.items():
        if (not isinstance(carrier_type, str) or
                re.fullmatch(r"[a-z][a-z0-9_]*", carrier_type) is None):
            raise ValueError(
                "Profile interface scalar carrier type %r must be "
                "lower_snake_case" % carrier_type)
        if not isinstance(row, dict) or set(row) != {
                "label", "allowed_exact_values", "allowed_prefixes"}:
            raise ValueError(
                "Profile interface scalar carrier type %s fields are not "
                "closed" % carrier_type)
        label = row.get("label")
        exact = row.get("allowed_exact_values")
        prefixes = row.get("allowed_prefixes")
        if not isinstance(label, str) or not label or label.strip() != label:
            raise ValueError(
                "Profile interface scalar carrier type %s label is invalid" %
                carrier_type)
        for field, values in (("allowed_exact_values", exact),
                              ("allowed_prefixes", prefixes)):
            if (not isinstance(values, list) or
                    any(not isinstance(value, str) or not value
                        for value in values) or
                    len(values) != len(set(values))):
                raise ValueError(
                    "Profile interface scalar carrier type %s %s must be a "
                    "unique string list" % (carrier_type, field))
        if not exact and not prefixes:
            raise ValueError(
                "Profile interface scalar carrier type %s permits no value" %
                carrier_type)

    carriers = document.get("scalar_carriers")
    if not isinstance(carriers, dict) or not carriers:
        raise ValueError(
            "Profile interface scalar_carriers must be a non-empty mapping")
    carrier_owners = set()
    for carrier_id, row in carriers.items():
        if (not isinstance(carrier_id, str) or
                re.fullmatch(r"[a-z][a-z0-9_]*", carrier_id) is None):
            raise ValueError(
                "Profile interface scalar carrier ID %r must be "
                "lower_snake_case" % carrier_id)
        if not isinstance(row, dict) or set(row) != {
                "form_id", "section", "carrier_type", "cardinality"}:
            raise ValueError(
                "Profile interface scalar carrier %s fields are not closed" %
                carrier_id)
        form_id = row.get("form_id")
        form = forms_by_id.get(form_id)
        section = row.get("section")
        if form is None:
            raise ValueError(
                "Profile interface scalar carrier %s names unknown form_id "
                "%r" % (carrier_id, form_id))
        if (not isinstance(section, str) or
                "## %s" % section not in form.required_headings):
            raise ValueError(
                "Profile interface scalar carrier %s section %r is not a "
                "required H2 of form %s" %
                (carrier_id, section, form_id))
        if row.get("carrier_type") not in carrier_types:
            raise ValueError(
                "Profile interface scalar carrier %s names unknown type %r" %
                (carrier_id, row.get("carrier_type")))
        if row.get("cardinality") not in table_cardinalities:
            raise ValueError(
                "Profile interface scalar carrier %s has unsupported "
                "cardinality %r" %
                (carrier_id, row.get("cardinality")))
        owner = (form_id, section)
        if owner in carrier_owners:
            raise ValueError(
                "Profile interface form %s section %r owns more than one "
                "scalar carrier" % (form_id, section))
        carrier_owners.add(owner)

    row_policy_kinds = closed_sets.get("table_row_policy_kinds")
    supported_row_policy_kinds = {
        "open", "exactly-one", "fixed-key", "registration-open",
        "registration-fixed-key", "applicability-open",
    }
    if (not isinstance(row_policy_kinds, list) or
            set(row_policy_kinds) != supported_row_policy_kinds or
            any(not isinstance(kind, str) or not kind
                for kind in row_policy_kinds) or
            len(row_policy_kinds) != len(set(row_policy_kinds))):
        raise ValueError(
            "Profile interface table_row_policy_kinds must exactly match "
            "the implemented form policy kinds")
    section_owners = set()
    for table_id, row in tables.items():
        if (not isinstance(table_id, str) or
                re.fullmatch(r"[a-z][a-z0-9_]*", table_id) is None):
            raise ValueError(
                "Profile interface table ID %r must be lower_snake_case" %
                table_id)
        row = tables[table_id]
        if not isinstance(row, dict) or set(row) != {
                "form_id", "section", "cardinality", "header",
                "row_policy"}:
            raise ValueError(
                "Profile interface table %s fields are not closed" %
                table_id)
        form_id = row.get("form_id")
        form = forms_by_id.get(form_id)
        if form is None:
            raise ValueError(
                "Profile interface table %s names unknown form_id %r" %
                (table_id, form_id))
        section = row.get("section")
        header = row.get("header")
        if (not isinstance(section, str) or not section or
                section.strip() != section):
            raise ValueError(
                "Profile interface table %s section must be a non-empty "
                "trimmed string" % table_id)
        if "## %s" % section not in form.required_headings:
            raise ValueError(
                "Profile interface table %s section %r is not a required H2 "
                "of form %s" % (table_id, section, form_id))
        if row.get("cardinality") not in table_cardinalities:
            raise ValueError(
                "Profile interface table %s has unsupported cardinality %r" %
                (table_id, row.get("cardinality")))
        if (not isinstance(header, list) or not header or
                any(not isinstance(field, str) or not field or
                    field.strip() != field for field in header) or
                len(header) != len(set(header))):
            raise ValueError(
                "Profile interface table %s header must be a non-empty "
                "unique list of non-empty trimmed strings" % table_id)
        policy = row.get("row_policy")
        if not isinstance(policy, dict):
            raise ValueError(
                "Profile interface table %s row_policy must be a mapping" %
                table_id)
        kind = policy.get("kind")
        if kind not in row_policy_kinds:
            raise ValueError(
                "Profile interface table %s has unsupported row policy %r" %
                (table_id, kind))
        expected_policy_fields = {
            "open": {"kind"},
            "exactly-one": {"kind"},
            "fixed-key": {"kind", "key_column", "keys"},
            "registration-open": {"kind", "carrier_id"},
            "registration-fixed-key": {
                "kind", "carrier_id", "key_column", "keys"},
            "applicability-open": {"kind", "carrier_id"},
        }[kind]
        if set(policy) != expected_policy_fields:
            raise ValueError(
                "Profile interface table %s row_policy fields are not "
                "closed for %s" % (table_id, kind))
        if "key_column" in policy:
            key_column = policy.get("key_column")
            keys = policy.get("keys")
            if key_column not in header:
                raise ValueError(
                    "Profile interface table %s row key column %r is not in "
                    "its header" % (table_id, key_column))
            if (not isinstance(keys, list) or not keys or
                    any(not isinstance(key, str) or not key for key in keys) or
                    len(keys) != len(set(keys))):
                raise ValueError(
                    "Profile interface table %s fixed keys must be a "
                    "non-empty unique string list" % table_id)
        owner = (form_id, section)
        if "carrier_id" in policy:
            carrier_id = policy.get("carrier_id")
            carrier = carriers.get(carrier_id)
            if not isinstance(carrier, dict) or (
                    carrier.get("form_id"), carrier.get("section")) != owner:
                raise ValueError(
                    "Profile interface table %s carrier %r must own the same "
                    "form section" % (table_id, carrier_id))
            expected_type = (
                "applicability" if kind == "applicability-open" else
                "registration")
            if carrier.get("carrier_type") != expected_type:
                raise ValueError(
                    "Profile interface table %s carrier %r must have type "
                    "%s" % (table_id, carrier_id, expected_type))
        if owner in section_owners:
            raise ValueError(
                "Profile interface form %s section %r owns more than one "
                "table contract" % (form_id, section))
        section_owners.add(owner)
    table_carrier_owners = {
        (row["form_id"], row["section"])
        for row in tables.values()
        if "carrier_id" in row["row_policy"]
    }
    required_table_carrier_owners = {
        owner for owner in carrier_owners
        if carriers[next(
            carrier_id for carrier_id, carrier in carriers.items()
            if (carrier["form_id"], carrier["section"]) == owner
        )]["carrier_type"] != "content_length_unit"
    }
    if table_carrier_owners != required_table_carrier_owners:
        raise ValueError(
            "Profile interface scalar-controlled tables do not match scalar "
            "carrier sections: missing=%s extra=%s" %
            (sorted(required_table_carrier_owners - table_carrier_owners),
             sorted(table_carrier_owners - required_table_carrier_owners)))
    return tuple(names)


def profile_interface_forms(document):
    """Return the validated manifest form and slot-name form mapping."""
    profile_interface_slots(document)
    return (
        _profile_form(document["manifest_form"], "Profile manifest form"),
        {
            row["name"]: _profile_form(
                row["form"], "Profile interface slot %s form" % row["name"])
            for row in document["slots"]
        },
    )


def profile_interface_slot_names(document):
    """Return the validated ``slot_id -> display name`` machine mapping."""
    profile_interface_slots(document)
    return {
        row["slot_id"]: row["name"]
        for row in document["slots"]
    }


def load_profile_interface(root=None, snapshots=None):
    """Load the single Kernel-owned Profile interface registry.

    ``snapshots`` lets a caller bind this read to the same immutable input set
    used for the rest of profile admission.  The module-level constants below
    are read-only projections for callers that need the shipped interface;
    runtime admission reloads the registry from the adopting repository root.
    """
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(PROFILE_INTERFACE_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        path = os.path.join(root, *PROFILE_INTERFACE_PATH.split("/"))
        text = kblib.read_text(path)
    document = kblib.parse_yaml_subset(text)
    profile_interface_slots(document)
    return document


def profile_file_slots(root=None, snapshots=None):
    return profile_interface_slots(
        load_profile_interface(root, snapshots=snapshots))


_SHIPPED_PROFILE_INTERFACE = load_profile_interface()
_SHIPPED_SLOT_NAMES = profile_interface_slot_names(
    _SHIPPED_PROFILE_INTERFACE)


def _shipped_slot_name(slot_id):
    try:
        return _SHIPPED_SLOT_NAMES[slot_id]
    except KeyError as exc:
        raise ValueError(
            "Profile interface has no required slot_id %s" % slot_id) \
            from exc


def _table_contract(name):
    row = (_SHIPPED_PROFILE_INTERFACE.get("tables") or {}).get(name)
    if not isinstance(row, dict):
        raise ValueError("Profile interface has no table contract %s" % name)
    section = row.get("section")
    header = row.get("header")
    if not isinstance(section, str) or not isinstance(header, list):
        raise ValueError("Profile interface table %s is malformed" % name)
    return section, tuple(header)


def _closed_values(name):
    value = (_SHIPPED_PROFILE_INTERFACE.get("closed_sets") or {}).get(name)
    if not isinstance(value, list):
        raise ValueError("Profile interface closed set %s is malformed" % name)
    return frozenset(value)


def _capability_binding(name):
    value = (_SHIPPED_PROFILE_INTERFACE.get("capability_bindings") or {}).get(name)
    if not isinstance(value, str) or not value:
        raise ValueError("Profile interface capability binding %s is missing" % name)
    return value


PROFILE_SCOPE_SLOT = _shipped_slot_name("profile-scope")
CORPUS_PLANNING_SLOT = _shipped_slot_name("corpus-planning")
STRUCTURE_REGISTRY_SLOT = _shipped_slot_name("structure-registry")
METADATA_CONTRACT_SLOT = _shipped_slot_name("metadata-contract")
PRIORITY_RUBRIC_SLOT = _shipped_slot_name("priority-rubric")
VOCABULARY_EXTENSIONS_SLOT = _shipped_slot_name("vocabulary-extensions")
LANGUAGE_CONTRACT_SLOT = _shipped_slot_name("language-contract")
EXPRESSION_LAYER_ENTRY_SLOT = _shipped_slot_name("expression-layer-entry")
SOURCE_POLICY_SLOT = _shipped_slot_name("source-policy")
ROLE_REGISTRY_SLOT = _shipped_slot_name("role-registry")
AUDIT_DIMENSION_REGISTRY_SLOT = _shipped_slot_name(
    "audit-dimension-registry")
REGISTERED_SCAN_REGISTRY_SLOT = _shipped_slot_name(
    "registered-scan-registry")
ESCALATION_POLICY_SLOT = _shipped_slot_name("escalation-policy")
ROUTING_AND_GATE_REGISTRY_SLOT = _shipped_slot_name(
    "routing-and-gate-registry")

AUDIT_SLOT = AUDIT_DIMENSION_REGISTRY_SLOT
SCAN_SLOT = REGISTERED_SCAN_REGISTRY_SLOT
ROLE_SLOT = ROLE_REGISTRY_SLOT
VOCABULARY_SLOT = VOCABULARY_EXTENSIONS_SLOT
METADATA_SLOT = METADATA_CONTRACT_SLOT
ROUTING_SLOT = ROUTING_AND_GATE_REGISTRY_SLOT
KERNEL_APPLICABILITY_PATH = (
    "kernel/K08 Metadata and Status/applicability-base.yaml")
KERNEL_RELATIONSHIP_PATH = (
    "kernel/K08 Metadata and Status/relationship-base.yaml")
KERNEL_VOCABULARY_PATH = vocabulary_contract.VOCABULARY_BASE_PATH
PROFILE_FILE_SLOTS = profile_file_slots()

EXTENSION_SECTION, EXTENSION_HEADER = _table_contract("extension_dimensions")
REGISTERED_ARTIFACT_SECTION, REGISTERED_ARTIFACT_HEADER = _table_contract(
    "registered_artifacts")
JUDGMENT_SECTION, JUDGMENT_HEADER = _table_contract("judgment_items")
SCAN_SECTION, SCAN_HEADER = _table_contract("registered_scans")
EXTENSION_GATE_SECTION, EXTENSION_GATE_HEADER = _table_contract("extension_gates")
EXTENSION_ROLE_SECTION, EXTENSION_ROLE_HEADER = _table_contract("extension_roles")
BATCH_REVIEW_SECTION, BATCH_REVIEW_HEADER = _table_contract(
    "batch_review_requirements")
BATCH_REVIEW_TARGET_SELECTORS = _closed_values("batch_review_target_selectors")
BATCH_REVIEW_TRIGGERS = _closed_values("batch_review_triggers")
BATCH_REVIEW_PRODUCER_KINDS = _closed_values("batch_review_producer_kinds")
BATCH_REVIEW_RECEIPT_SCHEMAS = _closed_values("batch_review_receipt_schemas")

BASE_DIMENSION_ORDER = \
    audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER
BASE_DIMENSIONS = frozenset(BASE_DIMENSION_ORDER)
EXTENSION_TARGETS = dict(
    audit_dimension_contract.EXTENSION_TARGET_MAPPINGS)
EVIDENCE_ROLES = audit_dimension_contract.EVIDENCE_ROLES
DIMENSION_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
STABLE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
PROFILE_GATE_ID_RE = re.compile(
    r"P:([a-z0-9][a-z0-9_-]*):([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\Z")
FIELD_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
VOCABULARY_VALUE_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
REQUIRED_SCAN_RE = re.compile(r"(?<![A-Za-z0-9])K12/09\s+item\s+6(?![0-9])")
TABLE_SEPARATOR_RE = re.compile(r":?-{3,}:?\Z")
REGISTRATION_RE = re.compile(r"^\s*-\s+Registration:\s*(.*?)\s*$")
REGISTRATION_VALUES = frozenset(
    _SHIPPED_PROFILE_INTERFACE["scalar_carrier_types"]["registration"]
    ["allowed_exact_values"])
CONFIGURED_CARRIER_VALUE = "Configured"
if CONFIGURED_CARRIER_VALUE not in REGISTRATION_VALUES:
    raise ValueError(
        "Profile interface registration form must define Configured")
INACTIVE_REGISTRATION_VALUES = (
    REGISTRATION_VALUES - {CONFIGURED_CARRIER_VALUE})
KERNEL_ROLE_IDS = _closed_values("kernel_role_ids")
PRODUCER_KINDS = _closed_values("producer_kinds")
PRODUCER_CAPABILITY_BY_KIND = dict(
    (_SHIPPED_PROFILE_INTERFACE.get("capability_bindings") or {}).get(
        "producer_capability_by_kind", {}))
RECEIPT_SCHEMA_BY_KIND = dict(
    (_SHIPPED_PROFILE_INTERFACE.get("capability_bindings") or {}).get(
        "receipt_schema_by_kind", {}))
FIELD_GATE_CONSUMER_OPERATION = _capability_binding(
    "field_gate_consumer_operation")
NON_FIELD_GATE_CONSUMER_OPERATION = _capability_binding(
    "non_field_gate_consumer_operation")
PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION = _capability_binding(
    "profile_extension_enum_projection_operation")
PROFILE_EXTENSION_ENUM_WRITER_CAPABILITY = _capability_binding(
    "profile_extension_enum_writer_capability")
EXPRESSION_STATUS_AXIS_ROLE = "Expression Status Axis"


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
        return "%s:%d" % (self.path, self.line)


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
    profile_form_expected: int = 0
    profile_form_conformant: int = 0

    @property
    def authorized(self):
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
        """Fingerprint only a fully authorized typed dependency graph."""
        if not self.authorized:
            return None
        value = {
            "schema_version": 3,
            "manifest": self.manifest_repo_path,
            "profile_dir": self.profile_repo_dir,
            "edges": [
                {
                    "kind": edge.kind,
                    "owner_id": edge.owner_id,
                    "target_id": edge.target_id,
                    "path": edge.path,
                    "fragment": edge.fragment,
                }
                for edge in self.dependency_edges
            ],
            "extension_gates": [
                {
                    "gate_id": gate.gate_id,
                    "owner_gate_id": gate.owner_gate_id,
                    "owner_path": (
                        gate.owner_dependency.path
                        if gate.owner_dependency is not None else None),
                    "owner_fragment": (
                        gate.owner_dependency.heading
                        if gate.owner_dependency is not None else None),
                    "transition_id": gate.transition_id,
                    "pass_authority_role_id": gate.pass_authority_role_id,
                    "applicability": gate.applicability,
                    "field_id": gate.field_id,
                    "completion_values": list(gate.completion_values),
                    "field_values": list(gate.field_values),
                    "judgment_item_id": gate.judgment_item_id,
                    "producer_kind": gate.producer_kind,
                    "producer_capability": gate.producer_capability,
                    "producer_reference": gate.producer_reference,
                    "receipt_schema": gate.receipt_schema,
                    "consumer_capability": gate.consumer_capability,
                }
                for gate in self.extension_gates
            ],
        }
        if self.batch_review_requirements:
            # Conditional inclusion keeps every requirement-free Profile's
            # fingerprint byte-identical to its pre-requirement value, so
            # shipping this slot forces no adopter re-fingerprint.
            value["batch_review_requirements"] = [
                {
                    "judgment_item_id": row.judgment_item_id,
                    "target_selector": row.target_selector,
                    "trigger": row.trigger,
                    "producer_kind": row.producer_kind,
                    "receipt_schema": row.receipt_schema,
                    "pass_authority_role_id": row.pass_authority_role_id,
                }
                for row in self.batch_review_requirements
            ]
        role_fields = [
            {
                "field_id": field.field_id,
                "role": field.role,
                "values": list(field.values),
            }
            for field in self.vocabulary_fields
            if field.role is not None
        ]
        if role_fields:
            # Profile snapshot identity already binds the complete Vocabulary
            # Extensions bytes.  This semantic projection is included only
            # for role-bearing fields, whose role is consumed by the typed
            # contract rather than merely retained as inert source text.
            value["vocabulary_role_fields"] = role_fields
        value["expression_registration"] = self.expression_registration
        value["expression_artifacts"] = [
            {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type,
                "label": artifact.label,
                "entry_point": artifact.entry_point,
                "dependency_map_path": artifact.dependency_map_path,
                "binding_field_ids": list(artifact.binding_field_ids),
                "revalidation_trigger": artifact.revalidation_trigger,
                "contract_path": artifact.contract_owner.path,
                "contract_heading": artifact.contract_owner.heading,
                "readiness_field_id": artifact.readiness_field_id,
            }
            for artifact in self.expression_artifacts
        ]
        value["volatility_defaults"] = [
            {"domain": domain, "volatility": volatility}
            for domain, volatility in self.volatility_defaults
        ]
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @property
    def fingerprint(self):
        return self.profile_contract_fingerprint


@dataclass(frozen=True)
class _Section:
    heading: str
    line: int
    lines: Tuple[Tuple[int, str], ...]


@dataclass(frozen=True)
class _TableRow:
    line: int
    cells: Tuple[str, ...]


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


def _strict_read(path):
    return Path(path).read_text(encoding="utf-8", errors="strict")


def _canonical_repository_file(root, relative_path, *, singly_linked=False):
    """Resolve one canonical repo-relative regular file without symlinks."""
    relative_path = canonical_repository_relative_path(relative_path, "path")
    return kblib.canonical_repository_file(
        root, relative_path, singly_linked=singly_linked)


def _blank_fenced_lines(text):
    """Return visible authority lines using the shared Markdown scanner."""
    return kblib.markdown_authority_lines(text)


def _sections(text):
    sections = []
    current_heading = None
    current_line = 0
    current_body = []
    for line_number, line in _blank_fenced_lines(text):
        heading = kblib.markdown_atx_heading(line)
        if heading is not None and heading[0] <= 2:
            if current_heading is not None:
                sections.append(_Section(
                    current_heading, current_line, tuple(current_body)))
            current_heading = (
                heading[1] if heading[0] == 2 else None
            )
            current_line = line_number
            current_body = []
            continue
        if current_heading is not None:
            current_body.append((line_number, line))
    if current_heading is not None:
        sections.append(_Section(
            current_heading, current_line, tuple(current_body)))
    return tuple(sections)


def _split_pipe_row(line):
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return ()
    return tuple(
        cell.replace("\\|", "|").strip()
        for cell in re.split(r"(?<!\\)\|", stripped[1:-1])
    )


def _table_groups(section):
    groups = []
    current = []
    for line_number, line in section.lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current.append(_TableRow(line_number, _split_pipe_row(line)))
        else:
            if current:
                groups.append(tuple(current))
                current = []
    if current:
        groups.append(tuple(current))
    return tuple(groups)


def _literal(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "`":
        return value[1:-1].strip()
    return value


class _Builder:
    def __init__(self, root, manifest_path, sentinel):
        self.root_input = os.path.abspath(os.fspath(root))
        self.root = os.path.realpath(os.path.abspath(os.fspath(root)))
        self.manifest_input = os.fspath(manifest_path)
        self.sentinel = sentinel
        self.diagnostics = []
        self.source_cells = []
        self.edges = []
        self.profile_snapshot = None

    def add(self, check, target, details, source=None):
        if (check == "profile-contract-sentinel" and any(
                item.check == check and item.target == target
                for item in self.diagnostics)):
            return
        self.diagnostics.append(Diagnostic(check, target, details, source))

    def scan_text_sentinel(self, text, source_path, owner):
        """Bind unfilled markers in every strict-UTF-8 authority file.

        Profile-owned dependencies are not allowed to hide a template marker
        behind an uncommon filename suffix.  The outer checker may scan more
        human-facing text for diagnostics, but authorization is decided from
        every file the typed closure actually reads.
        """
        if not self.sentinel:
            return
        for line_number, line in enumerate(text.splitlines(), 1):
            if self.sentinel not in line:
                continue
            source = SourceCell(
                source_path, "Profile dependency closure", line_number, 0,
                owner, line.strip())
            self.source_cells.append(source)
            self.add(
                "profile-contract-sentinel", source.target,
                "%s contains the unfilled sentinel %r" %
                (owner, self.sentinel), source)

    def read_profile_text(self, repository_relative_path):
        if self.profile_snapshot is None:
            raise OSError(errno.EINVAL,
                          "Profile snapshot is not bound")
        return self.profile_snapshot.read_text(repository_relative_path)

    def section(self, text, heading, source_path, prefix):
        matches = [item for item in _sections(text) if item.heading == heading]
        if len(matches) != 1:
            self.add(
                "%s-section-count" % prefix,
                source_path,
                "expected exactly one `## %s` section; found %d" %
                (heading, len(matches)),
            )
            return None
        return matches[0]

    def table(self, section, header, source_path, prefix):
        groups = _table_groups(section)
        if len(groups) != 1:
            self.add(
                "%s-table-count" % prefix,
                source_path,
                "expected exactly one Markdown table in `## %s`; found %d" %
                (section.heading, len(groups)),
            )
            return ()
        rows = groups[0]
        if len(rows) < 2:
            self.add(
                "%s-table-shape" % prefix,
                "%s:%d" % (source_path, rows[0].line),
                "table must contain a header and separator row",
            )
            return ()
        if rows[0].cells != tuple(header):
            self.add(
                "%s-table-header" % prefix,
                "%s:%d" % (source_path, rows[0].line),
                "table header must be exactly `%s`; found `%s`" %
                (" | ".join(header), " | ".join(rows[0].cells)),
            )
        separator = rows[1].cells
        if len(separator) != len(header) or not all(
                TABLE_SEPARATOR_RE.fullmatch(cell.replace(" ", ""))
                for cell in separator):
            self.add(
                "%s-table-separator" % prefix,
                "%s:%d" % (source_path, rows[1].line),
                "table separator must contain exactly %d canonical cells" %
                len(header),
            )
        return rows[2:]

    def cells(self, row, header, source_path, section, row_number, prefix):
        if len(row.cells) != len(header):
            self.add(
                "%s-row-shape" % prefix,
                "%s:%d" % (source_path, row.line),
                "data row %d must contain exactly %d cells; found %d" %
                (row_number, len(header), len(row.cells)),
            )
            return None
        cells = tuple(
            SourceCell(source_path, section, row.line, row_number,
                       header[index], value)
            for index, value in enumerate(row.cells)
        )
        self.source_cells.extend(cells)
        if any(self.sentinel and self.sentinel in cell.raw for cell in cells):
            source = next(
                cell for cell in cells
                if self.sentinel and self.sentinel in cell.raw)
            self.add(
                "profile-contract-sentinel", source.target,
                "data row %d contains the unfilled sentinel %r; dependent "
                "parsing is suppressed" % (row_number, self.sentinel),
                source,
            )
            return None
        empty = [cell for cell in cells if not cell.raw.strip()]
        if empty:
            source = empty[0]
            self.add(
                "%s-row-empty" % prefix, source.target,
                "data row %d has an empty `%s` cell" %
                (row_number, source.field), source,
            )
            return None
        return cells

    def profile_dependency(self, kind, owner_id, raw, source,
                           profile_repo_dir, require_heading=False):
        literal = _literal(raw)
        path_value, marker, heading = literal.partition("#")
        path_value = path_value.strip()
        heading = heading.strip() if marker else None
        if marker and not heading:
            self.add(
                "%s-heading-empty" % kind, source.target,
                "%s %r has an empty heading fragment" % (kind, literal),
                source,
            )
            return None
        if require_heading and not heading:
            self.add(
                "%s-heading-missing" % kind, source.target,
                "%s %r must include a `#heading` fragment" % (kind, literal),
                source,
            )
            return None
        try:
            canonical_repository_relative_path(path_value, "path")
        except ValueError as exc:
            self.add(
                "%s-path-invalid" % kind, source.target,
                "%s %r is not a canonical repository-relative path: "
                "%s" % (kind, path_value, exc), source,
            )
            return None

        expected_prefix = profile_repo_dir + "/"
        if not path_value.startswith(expected_prefix):
            self.add(
                "%s-path-outside-profile" % kind, source.target,
                "%s %r must stay inside selected Profile directory `%s/`" %
                (kind, path_value, profile_repo_dir), source,
            )
            return None

        try:
            absolute = _canonical_repository_file(
                self.root, path_value, singly_linked=True)
        except (OSError, ValueError) as exc:
            self.add(
                "%s-path-invalid" % kind, source.target,
                "%s %r is not a canonical repository-relative regular file: "
                "%s" % (kind, path_value, exc), source,
            )
            return None

        profile_absolute = os.path.join(
            self.root, *profile_repo_dir.split("/"))
        try:
            inside = os.path.commonpath((
                os.path.realpath(profile_absolute), os.path.realpath(absolute)
            )) == os.path.realpath(profile_absolute)
        except ValueError:
            inside = False
        if not inside:
            self.add(
                "%s-path-outside-profile" % kind, source.target,
                "%s %r resolves outside selected Profile directory `%s/`" %
                (kind, path_value, profile_repo_dir), source,
            )
            return None

        try:
            target_text = self.read_profile_text(path_value)
        except (OSError, UnicodeError) as exc:
            self.add(
                "%s-unreadable" % kind, source.target,
                "cannot read %s %r as strict UTF-8: %s" %
                (kind, path_value, exc), source,
            )
            return None

        self.scan_text_sentinel(
            target_text, path_value, "%s `%s`" % (kind, owner_id))

        if heading is not None:
            if not path_value.lower().endswith(".md"):
                self.add(
                    "%s-heading-non-markdown" % kind, source.target,
                    "%s %r has a heading fragment but does not name Markdown" %
                    (kind, literal), source,
                )
                return None
            matches = [
                line_number for line_number, _level, title in
                kblib.headings_of("\n".join(
                    line for _number, line in _blank_fenced_lines(target_text)))
                if title == heading
            ]
            if len(matches) != 1:
                self.add(
                    "%s-heading-count" % kind, source.target,
                    "%s %r must resolve to exactly one Markdown heading; "
                    "found %d" % (kind, literal, len(matches)), source,
                )
                return None

        dependency = ProfileDependency(
            kind, owner_id, path_value, absolute, heading, source)
        self.edges.append(DependencyEdge(
            kind=kind,
            owner_id=owner_id,
            path=path_value,
            fragment=heading,
        ))
        return dependency

    def repository_dependency(self, kind, owner_id, raw, source,
                              profile_repo_dir, require_heading=False):
        """Resolve a semantic owner anywhere in this repository.

        Profile-local targets are read from the already-bound immutable
        Profile snapshot.  Kernel targets are canonical root authority files,
        so they are resolved directly and are retained as dependency edges.
        """
        literal = _literal(raw)
        path_value, marker, heading = literal.partition("#")
        path_value = path_value.strip()
        heading = heading.strip() if marker else None
        if marker and not heading:
            self.add(
                "extension-gate-owner-heading-empty", source.target,
                "%s %r has an empty heading fragment" % (kind, literal),
                source)
            return None
        if require_heading and not heading:
            self.add(
                "extension-gate-owner-heading-missing", source.target,
                "%s %r must include a `#heading` fragment" % (kind, literal),
                source)
            return None
        try:
            canonical_repository_relative_path(path_value, "path")
            absolute = _canonical_repository_file(
                self.root, path_value, singly_linked=True)
        except (OSError, ValueError) as exc:
            self.add(
                "extension-gate-owner-path-invalid", source.target,
                "%s %r is not a canonical repository-relative regular file: "
                "%s" % (kind, path_value, exc), source)
            return None
        try:
            if path_value.startswith(profile_repo_dir + "/"):
                target_text = self.read_profile_text(path_value)
                self.scan_text_sentinel(
                    target_text, path_value, "%s `%s`" % (kind, owner_id))
            else:
                target_text = _strict_read(absolute)
        except (OSError, UnicodeError) as exc:
            self.add(
                "extension-gate-owner-unreadable", source.target,
                "cannot read %s %r as strict UTF-8: %s" %
                (kind, path_value, exc), source)
            return None
        if heading is not None:
            if not path_value.lower().endswith(".md"):
                self.add(
                    "extension-gate-owner-heading-non-markdown", source.target,
                    "%s %r has a heading fragment but does not name Markdown"
                    % (kind, literal), source)
                return None
            matches = [
                line_number for line_number, _level, title in
                kblib.headings_of("\n".join(
                    line for _number, line in
                    _blank_fenced_lines(target_text)))
                if title == heading
            ]
            if len(matches) != 1:
                self.add(
                    "extension-gate-owner-heading-count", source.target,
                    "%s %r must resolve to exactly one Markdown heading; "
                    "found %d" % (kind, literal, len(matches)), source)
                return None
        dependency = ProfileDependency(
            kind, owner_id, path_value, absolute, heading, source)
        self.edges.append(DependencyEdge(
            kind=kind, owner_id=owner_id, path=path_value, fragment=heading))
        return dependency


def _manifest_location(root, manifest_path):
    root_display = os.path.abspath(os.fspath(root))
    root_real = os.path.realpath(root_display)
    value = os.fspath(manifest_path)
    if os.path.isabs(value):
        display_absolute = os.path.abspath(value)
        try:
            lexically_inside = os.path.commonpath(
                (root_display, display_absolute)) == root_display
        except ValueError:
            lexically_inside = False
        if lexically_inside:
            relative = os.path.relpath(
                display_absolute, root_display).replace(os.sep, "/")
        else:
            # Permit equivalent system aliases such as /var and /private/var,
            # but still derive one canonical repository-relative spelling.
            relative = _repo_relative(root_real, display_absolute)
        absolute = _canonical_repository_file(root_real, relative)
    else:
        absolute = _canonical_repository_file(root_real, value)
        relative = value
    return root_real, absolute, relative


def _slot_source(manifest_text, manifest_repo_path, slot_name):
    pattern = re.compile(r"^\s*-\s+`%s`\s*:" % re.escape(slot_name))
    for line_number, line in enumerate(
            _blank_fenced_lines(manifest_text), 1):
        # _blank_fenced_lines already carries source numbers.
        actual_line, value = line
        if pattern.match(value):
            return SourceCell(
                manifest_repo_path, "Implemented Slots", actual_line, 0,
                slot_name, value.strip())
    return None


def _load_bound_slot(builder, manifest_text, manifest_path,
                     manifest_repo_path, profile_root, slot_name):
    bindings, duplicates = kblib.profile_slot_bindings(
        manifest_text, include_duplicates=True)
    if slot_name in duplicates:
        builder.add(
            "profile-contract-slot-duplicate", manifest_repo_path,
            "Implemented Slots repeats `%s`" % slot_name,
            _slot_source(manifest_text, manifest_repo_path, slot_name),
        )
        return None, None
    binding = bindings.get(slot_name)
    if not binding:
        builder.add(
            "profile-contract-slot-missing", manifest_repo_path,
            "Implemented Slots has no `%s` binding" % slot_name,
        )
        return None, None
    source = _slot_source(manifest_text, manifest_repo_path, slot_name)
    if builder.sentinel and builder.sentinel in binding:
        builder.add(
            "profile-contract-sentinel",
            source.target if source else manifest_repo_path,
            "`%s` binding contains the unfilled sentinel %r" %
            (slot_name, builder.sentinel), source,
        )
        return None, None
    kind, resolved = kblib.resolve_profile_binding(
        binding, builder.root, profile_root)
    if kind != "path":
        check = ("profile-contract-slot-invalid" if kind == "invalid" else
                 "profile-contract-slot-unresolved")
        builder.add(
            check,
            source.target if source else manifest_repo_path,
            "`%s` binding must resolve to a file inside the selected Profile; "
            "resolver returned %s (%r)" % (slot_name, kind, resolved), source,
        )
        return None, None
    try:
        relative = os.path.relpath(
            os.path.abspath(resolved), builder.root).replace(os.sep, "/")
        if relative == "." or relative.startswith("../"):
            raise ValueError("slot path is outside the repository root")
        _canonical_repository_file(
            builder.root, relative, singly_linked=True)
    except (OSError, ValueError) as exc:
        builder.add(
            "profile-contract-slot-invalid",
            source.target if source else manifest_repo_path,
            "`%s` binding is not a canonical regular Profile file: %s" %
            (slot_name, exc), source,
        )
        return None, None
    profile_repo_dir = _repo_relative(builder.root, profile_root)
    if not relative.startswith(profile_repo_dir + "/"):
        builder.add(
            "profile-contract-slot-outside-profile",
            source.target if source else manifest_repo_path,
            "`%s` binding resolves outside `%s/`" %
            (slot_name, profile_repo_dir), source,
        )
        return None, None
    try:
        text = builder.read_profile_text(relative)
    except (OSError, UnicodeError) as exc:
        builder.add(
            "profile-contract-slot-unreadable", relative,
            "cannot read `%s` as strict UTF-8: %s" % (relative, exc), source,
        )
        return relative, None
    builder.scan_text_sentinel(text, relative, "slot `%s`" % slot_name)
    return relative, text


def _direct_h2_table_groups(text):
    """Return pipe-table groups together with their H2/H3 location."""
    groups = []
    current_h2 = None
    current_h3 = None
    current_rows = []

    def flush():
        if current_rows:
            groups.append((current_h2, current_h3, tuple(current_rows)))
            current_rows.clear()

    for line_number, line in _blank_fenced_lines(text):
        heading = kblib.markdown_atx_heading(line)
        if heading is not None:
            flush()
            level, title = heading
            if level == 1:
                current_h2 = None
                current_h3 = None
            elif level == 2:
                current_h2 = title
                current_h3 = None
            elif level == 3:
                current_h3 = title
            continue
        cells = _split_pipe_row(line)
        if cells:
            current_rows.append(_TableRow(line_number, cells))
        else:
            flush()
    flush()
    return tuple(groups)


def _scalar_form_values(text, scalar_contracts, scalar_types):
    """Validate common scalar carriers and return their exact instance values."""
    errors = []
    values = {}
    sections = {}
    for section in _sections(text):
        sections.setdefault(section.heading, []).append(section)
    for carrier_id, contract in scalar_contracts:
        carrier_type = scalar_types[contract["carrier_type"]]
        label = carrier_type["label"]
        matches = []
        for section in sections.get(contract["section"], ()):
            pattern = re.compile(
                r"^\s*-\s+%s:\s*(.*?)\s*$" % re.escape(label))
            matches.extend(
                (line_number, match.group(1).strip())
                for line_number, line in section.lines
                for match in (pattern.match(line),) if match is not None)
        if contract["cardinality"] == "exactly-one" and len(matches) != 1:
            errors.append((
                "profile-form-scalar-count",
                "expected exactly one `- %s:` carrier in `## %s`; found %d" %
                (label, contract["section"], len(matches)),
            ))
            continue
        _line_number, value = matches[0]
        exact = carrier_type["allowed_exact_values"]
        prefixes = carrier_type["allowed_prefixes"]
        if value not in exact and not any(
                value.startswith(prefix) and len(value) > len(prefix)
                for prefix in prefixes):
            permitted = list(exact) + [prefix + "<value>" for prefix in prefixes]
            errors.append((
                "profile-form-scalar-value",
                "`- %s:` in `## %s` must use one registered form %r; found "
                "%r" % (label, contract["section"], permitted, value),
            ))
            continue
        values[carrier_id] = value
    return tuple(errors), values


def _table_row_form_errors(section, contract, rows, scalar_values):
    """Validate only row shape and stable row identity, never answer values."""
    errors = []
    header = tuple(contract["header"])
    data_rows = rows[2:]
    malformed = [row for row in data_rows if len(row.cells) != len(header)]
    for row in malformed:
        errors.append((
            "profile-form-table-row-shape",
            "data row at line %d in `## %s` must contain exactly %d cells; "
            "found %d" %
            (row.line, section, len(header), len(row.cells)),
        ))
    if malformed:
        return tuple(errors)

    policy = contract["row_policy"]
    kind = policy["kind"]
    if kind == "exactly-one" and len(data_rows) != 1:
        errors.append((
            "profile-form-table-row-count",
            "`## %s` must contain exactly one value row; found %d" %
            (section, len(data_rows)),
        ))
    elif kind in ("fixed-key", "registration-fixed-key"):
        expected = tuple(policy["keys"])
        if kind == "registration-fixed-key":
            carrier = scalar_values.get(policy["carrier_id"])
            if carrier is None:
                return tuple(errors)
            expected = expected if carrier == CONFIGURED_CARRIER_VALUE else ()
        key_index = header.index(policy["key_column"])
        observed = tuple(_literal(row.cells[key_index]) for row in data_rows)
        if observed != expected:
            errors.append((
                "profile-form-table-row-identity",
                "stable `%s` rows in `## %s` must be exactly %r; found %r" %
                (policy["key_column"], section, expected, observed),
            ))
    elif kind in ("registration-open", "applicability-open"):
        carrier = scalar_values.get(policy["carrier_id"])
        active = carrier == CONFIGURED_CARRIER_VALUE
        # Invalid values are omitted by _scalar_form_values.  Therefore any
        # other present value is the inactive form registered by K00, without
        # restating `None` or the applicability prefix here.
        inactive = isinstance(carrier, str) and not active
        if not active and not inactive:
            return tuple(errors)
        if active and not data_rows:
            errors.append((
                "profile-form-table-row-count",
                "configured `## %s` must contain at least one value row" %
                section,
            ))
        elif inactive and data_rows:
            errors.append((
                "profile-form-table-row-count",
                "inactive `## %s` must keep its common-form table empty; "
                "found %d value row(s)" % (section, len(data_rows)),
            ))
    return tuple(errors)


def _markdown_form_errors(text, form, table_contracts=(),
                          scalar_contracts=(), scalar_types=None):
    """Return structural form errors without interpreting Profile answers."""
    headings = kblib.headings_of(kblib.blank_markdown_authority(text))
    actual_required = tuple(
        "%s %s" % ("#" * level, title)
        for _line, level, title in headings if level <= 2)
    errors = []
    if actual_required != form.required_headings:
        errors.append((
            "profile-form-heading-structure",
            "required H1/H2 sequence differs; expected=%r found=%r" %
            (form.required_headings, actual_required),
        ))
    allowed_h2 = {
        kblib.markdown_atx_heading(item)[1]: reference_kinds
        for item, reference_kinds in form.instance_subheading_containers
    }
    current_h2 = None
    current_h3 = None
    instance_subheadings = []
    for line_number, level, title in headings:
        if level == 1:
            current_h2 = None
            current_h3 = None
        elif level == 2:
            current_h2 = title
            current_h3 = None
        elif level == 3:
            if current_h2 not in allowed_h2:
                errors.append((
                    "profile-form-subheading-container",
                    "line %d heading %r is outside a registered instance "
                    "subheading container" % (line_number, title),
                ))
                current_h3 = None
            else:
                current_h3 = title
                instance_subheadings.append(
                    (line_number, title, allowed_h2[current_h2]))
        elif current_h2 not in allowed_h2 or current_h3 is None:
            errors.append((
                "profile-form-subheading-container",
                "line %d heading %r must be nested below a registered "
                "instance H3" % (line_number, title),
            ))

    scalar_errors, scalar_values = _scalar_form_values(
        text, scalar_contracts, scalar_types or {})
    errors.extend(scalar_errors)
    expected_tables = {
        row["section"]: row for row in table_contracts
    }
    observed_tables = {}
    for h2, h3, rows in _direct_h2_table_groups(text):
        if h3 is not None:
            continue
        observed_tables.setdefault(h2, []).append(rows)
    for section, groups in sorted(
            observed_tables.items(), key=lambda item: str(item[0])):
        if section not in expected_tables:
            errors.append((
                "profile-form-table-unexpected",
                "found %d direct table(s) in %s, which has no registered "
                "common form table" %
                (len(groups), "the document root" if section is None else
                 "`## %s`" % section),
            ))
    for section, contract in expected_tables.items():
        groups = observed_tables.get(section, ())
        if contract["cardinality"] == "exactly-one" and len(groups) != 1:
            errors.append((
                "profile-form-table-count",
                "expected exactly one direct Markdown table in `## %s`; "
                "found %d" % (section, len(groups)),
            ))
            continue
        rows = groups[0]
        if len(rows) < 2:
            errors.append((
                "profile-form-table-shape",
                "the table in `## %s` must contain a header and separator "
                "row" % section,
            ))
            continue
        header = tuple(contract["header"])
        if rows[0].cells != header:
            errors.append((
                "profile-form-table-header",
                "table header in `## %s` must be exactly `%s`; found `%s`" %
                (section, " | ".join(header),
                 " | ".join(rows[0].cells)),
            ))
        separator = rows[1].cells
        if len(separator) != len(header) or not all(
                TABLE_SEPARATOR_RE.fullmatch(cell.replace(" ", ""))
                for cell in separator):
            errors.append((
                "profile-form-table-separator",
                "table separator in `## %s` must contain exactly %d "
                "canonical cells" % (section, len(header)),
            ))
            continue
        errors.extend(_table_row_form_errors(
            section, contract, rows, scalar_values))
    return tuple(errors), tuple(instance_subheadings)


def _shape_owner_text(root, path, root_input_snapshots=None):
    snapshot = (root_input_snapshots or {}).get(path)
    if snapshot is not None:
        return snapshot.read_text()
    return kblib.read_text(os.path.join(root, *path.split("/")))


def _yaml_shape_owner_document(root, interface_document, shape_owner,
                               root_input_snapshots=None):
    contract_id, registry_reference = shape_owner
    path = interface_document["registry_references"][registry_reference]
    text = _shape_owner_text(root, path, root_input_snapshots)
    if registry_reference == "corpus_planning_contract":
        owner = corpus_planning_contract.load_corpus_planning_contract(
            root, text=text)
    elif registry_reference == "structure_registry_contract":
        owner = kblib.load_structure_registry_contract(root, text=text)
    elif registry_reference == "metadata_profile_contract":
        owner = kblib.load_metadata_profile_contract(root, text=text)
    elif registry_reference == "vocabulary_extensions_contract":
        owner = vocabulary_contract.load_vocabulary_extensions_contract(
            root, text=text)
    else:
        raise ValueError(
            "no Tool shape reader is registered for %s" %
            registry_reference)
    if owner.get("contract_id") != contract_id:
        raise ValueError(
            "shape owner %s declares contract_id %r, expected %r" %
            (path, owner.get("contract_id"), contract_id))
    return owner


def _yaml_shape_issues(shape_owner, owner_document, document):
    contract_id, _registry_reference = shape_owner
    if contract_id == "cambium-corpus-planning-contract":
        _normalized, issues = \
            corpus_planning_contract.validate_corpus_planning_envelope(
                document, contract=owner_document)
        return tuple("%s" % issue for issue in issues)
    if contract_id == "structure-registry-shape-v2":
        return tuple(
            "%s: %s" % (check, details)
            for check, _target, details in
            kblib.validate_structure_registry_shape(
                document, contract=owner_document))
    if contract_id == "metadata-contract-shape-v1":
        return tuple(
            "%s: %s" % (check, details)
            for check, _target, details in
            kblib.validate_metadata_contract_shape(
                document, contract=owner_document))
    if contract_id == "vocabulary-extensions-shape-v1":
        return vocabulary_contract.validate_vocabulary_extensions(
            document, contract=owner_document)
    return ("unsupported shape owner contract %r" % contract_id,)


def _yaml_form_errors(text, form, root, interface_document,
                      root_input_snapshots=None):
    """Validate a YAML form through its declared single shape owner."""
    try:
        document = kblib.parse_yaml_subset(text)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        return ((
            "profile-form-yaml-shape",
            "cannot parse restricted YAML: %s" % exc,
        ),)
    try:
        owner_document = _yaml_shape_owner_document(
            root, interface_document, form.yaml_shape_owner,
            root_input_snapshots)
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError,
            vocabulary_contract.VocabularyContractError) as exc:
        return ((
            "profile-form-yaml-owner",
            "cannot load declared shape owner: %s" % exc,
        ),)
    return tuple(
        ("profile-form-yaml-shape",
         "%s: %s" % (form.yaml_shape_owner[0], issue))
        for issue in _yaml_shape_issues(
            form.yaml_shape_owner, owner_document, document))


def _validate_profile_forms(builder, interface_document, manifest_text,
                            manifest_relative, profile_root,
                            root_input_snapshots=None):
    """Validate candidate files against the one Kernel-owned form registry."""
    manifest_form, slot_forms = profile_interface_forms(interface_document)
    expected = 1 + len(slot_forms)
    conformant = 0

    table_contracts = {}
    for row in interface_document["tables"].values():
        table_contracts.setdefault(row["form_id"], []).append(row)
    scalar_contracts = {}
    for carrier_id, row in interface_document["scalar_carriers"].items():
        scalar_contracts.setdefault(row["form_id"], []).append(
            (carrier_id, row))
    scalar_types = interface_document["scalar_carrier_types"]
    manifest_errors, _manifest_subheadings = _markdown_form_errors(
        manifest_text, manifest_form,
        table_contracts.get("profile-manifest", ()),
        scalar_contracts.get("profile-manifest", ()), scalar_types)
    for check, details in manifest_errors:
        builder.add(check, manifest_relative, details)
    if not manifest_errors:
        conformant += 1

    pending_subheadings = []
    bindings, duplicates = kblib.profile_slot_bindings(
        manifest_text, include_duplicates=True)
    for slot_name, form in slot_forms.items():
        binding = bindings.get(slot_name)
        if binding is None or slot_name in duplicates:
            continue
        kind, resolved = kblib.resolve_profile_binding(
            binding, builder.root, profile_root)
        if kind != "path":
            continue
        source = _slot_source(manifest_text, manifest_relative, slot_name)
        observed = os.path.relpath(
            os.path.abspath(resolved), profile_root).replace(os.sep, "/")
        path_ok = observed == form.path
        if not path_ok:
            builder.add(
                "profile-form-binding-path",
                source.target if source else manifest_relative,
                "`%s` must bind the canonical form path `%s`; found `%s`" %
                (slot_name, form.path, observed), source,
            )
            continue
        try:
            relative = os.path.relpath(
                os.path.abspath(resolved), builder.root).replace(os.sep, "/")
            text = builder.read_profile_text(relative)
        except (OSError, UnicodeError):
            continue
        form_id = next(
            row["slot_id"] for row in interface_document["slots"]
            if row["name"] == slot_name)
        if form.path.endswith(".md"):
            errors, instance_subheadings = _markdown_form_errors(
                text, form, table_contracts.get(form_id, ()),
                scalar_contracts.get(form_id, ()), scalar_types)
        else:
            errors = _yaml_form_errors(
                text, form, builder.root, interface_document,
                root_input_snapshots)
            instance_subheadings = ()
        for check, details in errors:
            builder.add(check, relative, details, source)
        if not errors:
            conformant += 1
            pending_subheadings.extend(
                (relative, line_number, title, reference_kinds)
                for line_number, title, reference_kinds
                in instance_subheadings)
    return expected, conformant, tuple(pending_subheadings)


def _validate_form_subheading_references(builder, pending_subheadings):
    """Require each admitted instance H3 to have at least one typed reference."""
    orphan_paths = set()
    for path, line_number, title, reference_kinds in pending_subheadings:
        consumers = [
            edge for edge in builder.edges
            if edge.path == path and edge.fragment == title and
            edge.kind in reference_kinds
        ]
        if not consumers:
            orphan_paths.add(path)
            builder.add(
                "profile-form-subheading-reference",
                "%s:%d" % (path, line_number),
                "instance H3 %r must be consumed by at least one typed owner "
                "reference of kind %s; found none" %
                (title, ", ".join(reference_kinds)),
            )
    return len(orphan_paths)


def _parse_extensions(builder, text, source_path):
    section = builder.section(
        text, EXTENSION_SECTION, source_path, "extension-dimensions")
    if section is None:
        return None, ()

    declarations = []
    for line_number, line in section.lines:
        match = REGISTRATION_RE.match(line)
        if match:
            declarations.append((line_number, match.group(1).strip()))
    registration = None
    if len(declarations) != 1:
        builder.add(
            "extension-dimensions-registration", source_path,
            "expected exactly one `- Registration:` declaration; found %d" %
            len(declarations),
        )
    else:
        line_number, raw = declarations[0]
        source = SourceCell(
            source_path, EXTENSION_SECTION, line_number, 0,
            "Registration", raw)
        builder.source_cells.append(source)
        if builder.sentinel and builder.sentinel in raw:
            builder.add(
                "profile-contract-sentinel", source.target,
                "Extension Dimensions registration contains the unfilled "
                "sentinel %r" % builder.sentinel, source,
            )
        elif raw not in REGISTRATION_VALUES:
            builder.add(
                "extension-dimensions-registration", source.target,
                "Registration must use one registered form %r; found %r" %
                (sorted(REGISTRATION_VALUES), raw), source,
            )
        else:
            registration = raw

    rows = builder.table(
        section, EXTENSION_HEADER, source_path, "extension-dimensions")
    parsed = []
    seen = set()
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, EXTENSION_HEADER, source_path, EXTENSION_SECTION,
            row_number, "extension-dimensions")
        if cells is None:
            continue
        dimension_id = _literal(cells[0].raw)
        target_literal = _literal(cells[1].raw)
        valid = True
        if not DIMENSION_ID_RE.fullmatch(dimension_id):
            builder.add(
                "extension-dimension-id-invalid", cells[0].target,
                "Dimension ID %r must be lower_snake_case starting with a "
                "letter" % dimension_id, cells[0])
            valid = False
        if dimension_id in seen:
            builder.add(
                "extension-dimension-id-duplicate", cells[0].target,
                "Dimension ID %r is registered more than once" % dimension_id,
                cells[0])
            valid = False
        seen.add(dimension_id)
        if dimension_id in BASE_DIMENSIONS:
            builder.add(
                "extension-dimension-base-collision", cells[0].target,
                "Dimension ID %r redefines a base receipt dimension" %
                dimension_id, cells[0])
            valid = False
        targets = EXTENSION_TARGETS.get(target_literal)
        if targets is None:
            builder.add(
                "extension-dimension-target-invalid", cells[1].target,
                "target must be exactly `review`, `receipt`, or "
                "`review + receipt`; found %r" % target_literal, cells[1])
            valid = False
            targets = ()
        if valid:
            parsed.append(ExtensionDimension(
                dimension_id, tuple(targets), cells[2].raw.strip(), cells[0]))

    if registration in INACTIVE_REGISTRATION_VALUES and rows:
        builder.add(
            "extension-dimensions-none-with-rows", source_path,
            "`Registration: None` requires an empty registration table; "
            "found %d data row(s)" % len(rows),
        )
    if registration == CONFIGURED_CARRIER_VALUE and not rows:
        builder.add(
            "extension-dimensions-configured-empty", source_path,
            "`Registration: Configured` requires at least one data row",
        )
    return registration, tuple(parsed)


def _parse_judgments(builder, text, source_path, profile_repo_dir,
                     extension_dimensions):
    section = builder.section(
        text, JUDGMENT_SECTION, source_path, "judgment-items")
    if section is None:
        return ()
    rows = builder.table(
        section, JUDGMENT_HEADER, source_path, "judgment-items")
    if not rows:
        builder.add(
            "judgment-items-empty", source_path,
            "Judgment Items requires at least one data row",
        )
    known_dimensions = BASE_DIMENSIONS.union(
        dimension.dimension_id for dimension in extension_dimensions)
    parsed = []
    seen = set()
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, JUDGMENT_HEADER, source_path, JUDGMENT_SECTION,
            row_number, "judgment-items")
        if cells is None:
            continue
        item_id = _literal(cells[0].raw)
        dimension_id = _literal(cells[1].raw)
        evidence_role = _literal(cells[4].raw)
        valid = True
        if not STABLE_ID_RE.fullmatch(item_id):
            builder.add(
                "judgment-item-id-invalid", cells[0].target,
                "Stable Judgment Item ID %r must be lowercase kebab-case" %
                item_id, cells[0])
            valid = False
        if item_id in seen:
            builder.add(
                "judgment-item-id-duplicate", cells[0].target,
                "Stable Judgment Item ID %r is registered more than once" %
                item_id, cells[0])
            valid = False
        seen.add(item_id)
        if dimension_id not in known_dimensions:
            builder.add(
                "judgment-item-dimension-unknown", cells[1].target,
                "Dimension ID %r is neither a base dimension nor a valid "
                "registered extension" % dimension_id, cells[1])
            valid = False
        if evidence_role not in EVIDENCE_ROLES:
            builder.add(
                "judgment-item-evidence-role-invalid", cells[4].target,
                "Evidence role must be `emits`, `consumes`, or `triggers`; "
                "found %r" % evidence_role, cells[4])
            valid = False
        dependency = builder.profile_dependency(
            "predicate-owner", item_id, cells[5].raw, cells[5],
            profile_repo_dir)
        if dependency is None:
            valid = False
        parsed.append(JudgmentItem(
            item_id, dimension_id, _literal(cells[2].raw),
            cells[3].raw.strip(), evidence_role, dependency, cells[0]))
        # Keep diagnostic IR even when invalid; authorization never consumes it.
        if not valid:
            continue
    return tuple(parsed)


def _scan_capability_spec(builder, scan_id, capability_raw, config_raw,
                          capability_source, config_source,
                          profile_repo_dir, capabilities):
    capability_id = _literal(capability_raw)
    capability = capabilities.get(capability_id)
    if capability is None:
        builder.add(
            "registered-scan-capability-unknown", capability_source.target,
            "verifier capability %r is not registered in %s" %
            (capability_id, SCAN_CAPABILITY_PATH), capability_source)
        return capability_id, None, None, None

    script_repo_path = capability["implementation_path"]
    try:
        script_absolute_path = _canonical_repository_file(
            builder.root, script_repo_path, singly_linked=True)
    except (OSError, ValueError) as exc:
        builder.add(
            "registered-scan-capability-implementation",
            capability_source.target,
            "capability %r implementation %r is invalid: %s" %
            (capability_id, script_repo_path, exc), capability_source)
        script_absolute_path = None

    config_literal = _literal(config_raw)
    config_dependency = None
    if config_literal != "None":
        config_dependency = builder.profile_dependency(
            "scan-config", scan_id, config_literal, config_source,
            profile_repo_dir)
    configuration = capability["configuration"]
    if configuration == "required" and config_literal == "None":
        builder.add(
            "registered-scan-config-required", config_source.target,
            "verifier capability %r requires one Profile configuration "
            "reference" % capability_id, config_source)
    elif configuration == "none" and config_literal != "None":
        builder.add(
            "registered-scan-config-forbidden", config_source.target,
            "verifier capability %r accepts no Profile configuration" %
            capability_id, config_source)

    if script_absolute_path is not None:
        builder.edges.append(DependencyEdge(
            kind="verifier-capability", owner_id=scan_id,
            target_id=capability_id, path=script_repo_path))
    return (capability_id, script_repo_path, script_absolute_path,
            config_dependency)


def _parse_scans(builder, text, source_path, profile_repo_dir, capabilities):
    section = builder.section(
        text, SCAN_SECTION, source_path, "registered-scans")
    if section is None:
        return ()
    rows = builder.table(
        section, SCAN_HEADER, source_path, "registered-scans")
    if not rows:
        builder.add(
            "registered-scans-empty", source_path,
            "Scan Registrations requires at least one data row",
        )
    parsed = []
    seen = set()
    suppressed = False
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, SCAN_HEADER, source_path, SCAN_SECTION,
            row_number, "registered-scans")
        if cells is None:
            if any(builder.sentinel and builder.sentinel in value
                   for value in row.cells):
                suppressed = True
            continue
        scan_id = _literal(cells[0].raw)
        activation = _literal(cells[1].raw)
        if not STABLE_ID_RE.fullmatch(scan_id):
            builder.add(
                "registered-scan-id-invalid", cells[0].target,
                "Stable Scan ID %r must be lowercase kebab-case" % scan_id,
                cells[0])
        if scan_id in seen:
            builder.add(
                "registered-scan-id-duplicate", cells[0].target,
                "Stable Scan ID %r is registered more than once" % scan_id,
                cells[0])
        seen.add(scan_id)
        capability = _scan_capability_spec(
            builder, scan_id, cells[3].raw, cells[4].raw,
            cells[3], cells[4], profile_repo_dir, capabilities)
        required = bool(REQUIRED_SCAN_RE.search(activation))
        parsed.append(RegisteredScan(
            scan_id=scan_id,
            activation_role=activation,
            scope=cells[2].raw.strip(),
            verifier_capability_id=capability[0],
            script_repo_path=capability[1],
            script_absolute_path=capability[2],
            config_dependency=capability[3],
            candidate_predicate=cells[5].raw.strip(),
            judgment_item_id=_literal(cells[6].raw),
            required_for_k12_item_6=required,
            source=cells[0],
        ))
    required = [scan for scan in parsed if scan.required_for_k12_item_6]
    if len(required) != 1 and not suppressed:
        builder.add(
            "registered-scans-required-count", source_path,
            "Scan Registrations must contain exactly one K12/09 item 6 row; "
            "found %d" % len(required),
        )
    return tuple(parsed)


def _section_registration(builder, section, source_path, prefix):
    if prefix == "extension-gates":
        check = "extension-gates-registration"
    elif prefix == "expression-artifacts":
        check = "expression-artifacts-registration"
    else:
        check = "extension-gate-role-registry"
    declarations = []
    for line_number, line in section.lines:
        match = REGISTRATION_RE.match(line)
        if match:
            declarations.append((line_number, match.group(1).strip()))
    if len(declarations) != 1:
        builder.add(
            check, source_path,
            "expected exactly one `- Registration:` declaration; found %d" %
            len(declarations))
        return None
    line_number, raw = declarations[0]
    source = SourceCell(
        source_path, section.heading, line_number, 0, "Registration", raw)
    builder.source_cells.append(source)
    if builder.sentinel and builder.sentinel in raw:
        builder.add(
            "profile-contract-sentinel", source.target,
            "%s registration contains the unfilled sentinel %r" %
            (section.heading, builder.sentinel), source)
        return None
    if raw not in REGISTRATION_VALUES:
        builder.add(
            check, source.target,
            "Registration must use one registered form %r; found %r" %
            (sorted(REGISTRATION_VALUES), raw), source)
        return None
    return raw


def _extension_role_ids(builder, text, source_path):
    """Return the closed Role IDs an extension Gate may reference.

    Full Role Registry validation remains with ``check_profile``.  This linker
    nevertheless parses the exact extension-role block it consumes, so a Gate
    cannot become authorized merely because a similar token appears in prose.
    """
    role_ids = set()
    kernel_sections = (
        ("Process Roles",
         ("Kernel role", "Bound actor or system ID/name"),
         frozenset(("proposer", "gatekeeper", "executor", "stopper"))),
        ("Knowledge Host",
         ("Kernel role", "Binding"),
         frozenset(("knowledge-host", "knowledge-host UI"))),
    )
    for heading, header, required_ids in kernel_sections:
        matches = [item for item in _sections(text) if item.heading == heading]
        if len(matches) != 1:
            builder.add(
                "extension-gate-role-registry", source_path,
                "configured extension Gates require exactly one `## %s` "
                "section; found %d" % (heading, len(matches)))
            continue
        groups = _table_groups(matches[0])
        if (len(groups) != 1 or len(groups[0]) < 2 or
                groups[0][0].cells != header):
            builder.add(
                "extension-gate-role-registry", source_path,
                "`## %s` does not contain its closed Role Registry table" %
                heading)
            continue
        found = set()
        for row in groups[0][2:]:
            if len(row.cells) != len(header) or not row.cells[1].strip():
                continue
            role_id = _literal(row.cells[0])
            if role_id in required_ids:
                found.add(role_id)
        missing = sorted(required_ids.difference(found))
        if missing:
            builder.add(
                "extension-gate-role-registry", source_path,
                "`## %s` does not bind required Role ID(s): %s" %
                (heading, ", ".join(missing)))
        role_ids.update(found)
    sections = [
        item for item in _sections(text)
        if item.heading == EXTENSION_ROLE_SECTION
    ]
    if len(sections) != 1:
        builder.add(
            "extension-gate-role-registry", source_path,
            "expected exactly one `## Extension Roles` section; found %d" %
            len(sections))
        return frozenset(role_ids)
    section = sections[0]
    registration = _section_registration(
        builder, section, source_path, "extension-gate-roles")
    groups = _table_groups(section)
    if len(groups) != 1 or len(groups[0]) < 2:
        builder.add(
            "extension-gate-role-registry", source_path,
            "Extension Roles must contain exactly one complete Markdown table")
        return frozenset(role_ids)
    rows = groups[0]
    if rows[0].cells != EXTENSION_ROLE_HEADER:
        builder.add(
            "extension-gate-role-registry",
            "%s:%d" % (source_path, rows[0].line),
            "Extension Roles table header is not the closed Role Registry "
            "header")
        return frozenset(role_ids)
    separator = rows[1].cells
    if len(separator) != len(EXTENSION_ROLE_HEADER) or not all(
            TABLE_SEPARATOR_RE.fullmatch(cell.replace(" ", ""))
            for cell in separator):
        builder.add(
            "extension-gate-role-registry",
            "%s:%d" % (source_path, rows[1].line),
            "Extension Roles table separator is not canonical")
        return frozenset(role_ids)
    data_rows = rows[2:]
    if registration in INACTIVE_REGISTRATION_VALUES and data_rows:
        builder.add(
            "extension-gate-role-registry", source_path,
            "Extension Roles `Registration: None` requires an empty table")
    if registration == CONFIGURED_CARRIER_VALUE and not data_rows:
        builder.add(
            "extension-gate-role-registry", source_path,
            "Extension Roles `Registration: Configured` requires a data row")
    seen = set()
    for row_number, row in enumerate(data_rows, 1):
        if len(row.cells) != len(EXTENSION_ROLE_HEADER):
            builder.add(
                "extension-gate-role-registry",
                "%s:%d" % (source_path, row.line),
                "Extension Roles row %d must contain exactly %d cells" %
                (row_number, len(EXTENSION_ROLE_HEADER)))
            continue
        source = SourceCell(
            source_path, EXTENSION_ROLE_SECTION, row.line, row_number,
            EXTENSION_ROLE_HEADER[0], row.cells[0])
        builder.source_cells.append(source)
        role_id = _literal(row.cells[0])
        if not STABLE_ID_RE.fullmatch(role_id):
            builder.add(
                "extension-gate-role-registry", source.target,
                "extension Role ID %r must be lowercase kebab-case" % role_id,
                source)
            continue
        if role_id in seen or role_id in KERNEL_ROLE_IDS:
            builder.add(
                "extension-gate-role-registry", source.target,
                "extension Role ID %r is duplicated or collides with a "
                "kernel Role ID" % role_id, source)
            continue
        seen.add(role_id)
        role_ids.add(role_id)
    return frozenset(role_ids)


def _vocabulary_extensions(builder, text, source_path,
                           root_input_snapshots=None):
    """Compile all typed Profile vocabulary policy from one frozen input.

    The Vocabulary Extensions slot is consumed once by the Profile linker.
    Gate validation, volatility policy, artifact composition, and later
    semantic projections share this result, so no consumer can rediscover
    fields or defaults from a second parse or from prose.
    """
    try:
        document = kblib.parse_yaml_subset(text)
    except (TypeError, ValueError) as exc:
        builder.add(
            "extension-gate-vocabulary-registry", source_path,
            "cannot parse Vocabulary Extensions as restricted YAML: %s" % exc)
        return (), ()
    if not isinstance(document, dict):
        builder.add(
            "extension-gate-vocabulary-registry", source_path,
            "Vocabulary Extensions must be a mapping")
        return (), ()
    owner_snapshot = (root_input_snapshots or {}).get(
        vocabulary_contract.VOCABULARY_EXTENSIONS_CONTRACT_PATH)
    try:
        owner_contract = vocabulary_contract.\
            load_vocabulary_extensions_contract(
                builder.root,
                text=owner_snapshot.read_text()
                if owner_snapshot is not None else None)
        shape_issues = vocabulary_contract.validate_vocabulary_extensions(
            document, contract=owner_contract)
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError,
            vocabulary_contract.VocabularyContractError) as exc:
        shape_issues = ("owner contract is unavailable: %s" % exc,)
    for issue in shape_issues:
        builder.add(
            "extension-gate-vocabulary-registry", source_path,
            "Vocabulary Extensions shape: %s" % issue)
    if shape_issues:
        return (), ()

    fields = document.get("fields") if isinstance(document, dict) else None
    if fields is None:
        # A Profile with no field extensions has no expression target.  This
        # is the same legal inactive form consumed by vocabulary composition.
        fields = {}
    if not isinstance(fields, dict):
        builder.add(
            "extension-gate-vocabulary-registry", source_path,
            "Vocabulary Extensions must expose a `fields` mapping")
        fields = {}
    compiled = []
    for field_id, declaration in fields.items():
        if not isinstance(field_id, str) or not FIELD_ID_RE.fullmatch(field_id):
            builder.add(
                "extension-gate-vocabulary-registry", source_path,
                "Vocabulary field ID %r must be lowercase snake_case" %
                field_id)
            continue
        if not isinstance(declaration, dict):
            builder.add(
                "extension-gate-vocabulary-registry", source_path,
                "Vocabulary field %r must be a mapping" % field_id)
            continue
        role = declaration.get("role")
        if role is not None and (
                not isinstance(role, str) or not role.strip()):
            builder.add(
                "extension-gate-vocabulary-registry", source_path,
                "Vocabulary field %r role must be a non-empty string or be "
                "absent" % field_id)
            continue
        values = declaration.get("values")
        if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values):
            builder.add(
                "extension-gate-vocabulary-registry", source_path,
                "Vocabulary field %r values must be a list of non-empty "
                "strings" % field_id)
            continue
        compiled.append(VocabularyField(
            field_id=field_id,
            role=role if isinstance(role, str) else None,
            values=tuple(values),
        ))

    snapshot = (root_input_snapshots or {}).get(KERNEL_VOCABULARY_PATH)
    try:
        vocabulary_base = vocabulary_contract.load_vocabulary_base(
            builder.root,
            text=snapshot.read_text() if snapshot is not None else None)
        allowed_volatilities = frozenset(
            vocabulary_base["volatility_values"])
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        builder.add(
            "extension-gate-vocabulary-registry", KERNEL_VOCABULARY_PATH,
            "cannot load the Kernel-owned volatility value contract: %s" %
            exc)
        allowed_volatilities = frozenset()

    defaults = document.get("volatility_defaults")
    compiled_defaults = []
    if not isinstance(defaults, dict) or not defaults:
        builder.add(
            "extension-gate-vocabulary-registry", source_path,
            "Vocabulary Extensions volatility_defaults must be a non-empty "
            "domain-to-volatility mapping")
    else:
        for domain, volatility in defaults.items():
            if (not isinstance(domain, str) or not domain or
                    domain.strip() != domain):
                builder.add(
                    "extension-gate-vocabulary-registry", source_path,
                    "volatility_defaults domain %r must be a non-empty "
                    "trimmed string" % domain)
                continue
            if (not isinstance(volatility, str) or
                    volatility not in allowed_volatilities):
                builder.add(
                    "extension-gate-vocabulary-registry", source_path,
                    "volatility_defaults.%s must be one of %s; found %r" %
                    (domain, ", ".join(sorted(allowed_volatilities)),
                     volatility))
                continue
            compiled_defaults.append((domain, volatility))
    return (
        tuple(sorted(compiled, key=lambda field: field.field_id)),
        tuple(compiled_defaults),
    )


def _metadata_binding_field_ids(
        builder, text, source_path, owner_document):
    """Return Profile metadata field declarations expression rows may use."""
    try:
        document = kblib.parse_yaml_subset(text)
    except (TypeError, ValueError) as exc:
        builder.add(
            "expression-artifact-metadata-contract", source_path,
            "cannot parse Metadata Contract as restricted YAML: %s" % exc)
        return {}
    if owner_document is None:
        return {}
    shape_errors = kblib.validate_metadata_contract_shape(
        document, target=source_path, contract=owner_document)
    for check, label, details in shape_errors:
        builder.add(
            "expression-artifact-metadata-contract", label,
            "%s: %s" % (check, details))
    if shape_errors:
        return {}
    return {
        entry["field"]: (name, entry)
        for name in ("extension_fields", "relationship_extensions")
        for entry in document.get(name, ())
        if isinstance(entry, dict) and isinstance(entry.get("field"), str)
    }


def _parse_registered_artifacts(builder, text, source_path,
                                profile_repo_dir, vocabulary_fields,
                                metadata_text, metadata_path,
                                metadata_owner_document, gates,
                                root_input_snapshots=None):
    """Compile the sole configured Expression Layer artifact registry."""
    section = builder.section(
        text, REGISTERED_ARTIFACT_SECTION, source_path,
        "expression-artifacts")
    if section is None:
        return None, ()
    registration = _section_registration(
        builder, section, source_path, "expression-artifacts")
    rows = builder.table(
        section, REGISTERED_ARTIFACT_HEADER, source_path,
        "expression-artifacts")
    if registration in INACTIVE_REGISTRATION_VALUES and rows:
        builder.add(
            "expression-artifacts-none-with-rows", source_path,
            "`Registration: None` requires an empty Registered Artifacts "
            "table; found %d data row(s)" % len(rows))
    if registration == CONFIGURED_CARRIER_VALUE and not rows:
        builder.add(
            "expression-artifacts-configured-empty", source_path,
            "`Registration: Configured` requires at least one Registered "
            "Artifacts row")
    if not rows:
        return registration, ()

    try:
        snapshot = (root_input_snapshots or {}).get(KERNEL_VOCABULARY_PATH)
        base = vocabulary_contract.load_vocabulary_base(
            builder.root,
            text=snapshot.read_text() if snapshot is not None else None)
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
    metadata_fields = (_metadata_binding_field_ids(
        builder, metadata_text, metadata_path, metadata_owner_document)
        if metadata_text is not None else {})
    if metadata_text is None:
        builder.add(
            "expression-artifact-metadata-contract", source_path,
            "configured Registered Artifacts require a readable Metadata "
            "Contract")
    gates_by_field = {}
    for gate in gates:
        if gate.field_id is not None:
            gates_by_field.setdefault(gate.field_id, []).append(gate)

    parsed = []
    seen = set()
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, REGISTERED_ARTIFACT_HEADER, source_path,
            REGISTERED_ARTIFACT_SECTION, row_number,
            "expression-artifacts")
        if cells is None:
            continue
        artifact_id = _literal(cells[0].raw)
        artifact_type = _literal(cells[1].raw)
        label = cells[2].raw.strip()
        entry_point = _literal(cells[3].raw)
        dependency_literal = _literal(cells[4].raw)
        dependency_map_path = (
            None if dependency_literal == "None" else dependency_literal)
        binding_literal = _literal(cells[5].raw)
        binding_field_ids = (
            () if binding_literal == "None" else
            _completion_values(cells[5].raw))
        revalidation_trigger = cells[6].raw.strip()
        readiness_literal = _literal(cells[8].raw)
        readiness_field_id = (
            None if readiness_literal == "None" else readiness_literal)
        valid = True

        if not STABLE_ID_RE.fullmatch(artifact_id):
            builder.add(
                "expression-artifact-id-invalid", cells[0].target,
                "Stable artifact ID %r must be lowercase kebab-case" %
                artifact_id, cells[0])
            valid = False
        if artifact_id in seen:
            builder.add(
                "expression-artifact-id-duplicate", cells[0].target,
                "Stable artifact ID %r is registered more than once" %
                artifact_id, cells[0])
            valid = False
        seen.add(artifact_id)
        if artifact_type not in allowed_types:
            builder.add(
                "expression-artifact-type-unknown", cells[1].target,
                "Artifact type %r is not in the composed Kernel + Profile "
                "`type` vocabulary" % artifact_type, cells[1])
            valid = False
        try:
            canonical_repository_relative_path(entry_point, "entry point")
        except ValueError as exc:
            builder.add(
                "expression-artifact-entry-invalid", cells[3].target,
                str(exc), cells[3])
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
                    cells[4].target, str(exc), cells[4])
                valid = False
            else:
                builder.edges.append(DependencyEdge(
                    kind="expression-dependency-map", owner_id=artifact_id,
                    path=dependency_map_path))
        if (len(binding_field_ids) != len(set(binding_field_ids)) or
                any(FIELD_ID_RE.fullmatch(field_id) is None
                    for field_id in binding_field_ids)):
            builder.add(
                "expression-artifact-binding-invalid", cells[5].target,
                "Metadata binding field IDs must be unique lowercase "
                "snake_case values", cells[5])
            valid = False
        unknown_bindings = sorted(
            set(binding_field_ids) - set(metadata_fields))
        if unknown_bindings:
            builder.add(
                "expression-artifact-binding-unknown", cells[5].target,
                "Metadata binding field ID(s) are not declared by the "
                "Profile Metadata Contract: %s" %
                ", ".join(unknown_bindings), cells[5])
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
                "expression-artifact-binding-shape", cells[5].target,
                "Metadata binding field ID(s) must be an extension `path` "
                "or an `expression-to-canonical` relationship with "
                "`list-of-paths` shape: %s" %
                ", ".join(invalid_binding_shapes), cells[5])
            valid = False
        for field_id in binding_field_ids:
            builder.edges.append(DependencyEdge(
                kind="expression-binding-field", owner_id=artifact_id,
                target_id=field_id))
        if dependency_map_path is None and not binding_field_ids:
            builder.add(
                "expression-artifact-binding-missing", cells[4].target,
                "each artifact requires a dependency-map path, at least one "
                "Metadata binding field ID, or both", cells[4])
            valid = False

        contract_owner = builder.profile_dependency(
            "expression-contract", artifact_id, cells[7].raw, cells[7],
            profile_repo_dir, require_heading=True)
        if contract_owner is None:
            valid = False
        if readiness_field_id is not None:
            field = fields_by_id.get(readiness_field_id)
            if (field is None or
                    field.role != EXPRESSION_STATUS_AXIS_ROLE):
                builder.add(
                    "expression-artifact-readiness-field", cells[8].target,
                    "Readiness field ID %r must name a Vocabulary field with "
                    "role `%s`" % (readiness_field_id,
                                   EXPRESSION_STATUS_AXIS_ROLE), cells[8])
                valid = False
            if readiness_field_id not in metadata_fields:
                builder.add(
                    "expression-artifact-readiness-metadata",
                    cells[8].target,
                    "Readiness field ID %r must be declared by the Profile "
                    "Metadata Contract" % readiness_field_id, cells[8])
                valid = False
            matching_gates = gates_by_field.get(readiness_field_id, ())
            if len(matching_gates) != 1:
                builder.add(
                    "expression-artifact-readiness-gate", cells[8].target,
                    "Readiness field ID %r must bind exactly one extension "
                    "Gate; found %d" %
                    (readiness_field_id, len(matching_gates)), cells[8])
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
                source=cells[0],
            ))
    return registration, tuple(parsed)


def _metadata_extension_fields(builder, text, source_path, owner_document):
    """Compile the Profile-owned page fields a typed Gate may project."""
    try:
        document = kblib.parse_yaml_subset(text)
    except (TypeError, ValueError) as exc:
        builder.add(
            "extension-gate-metadata-contract", source_path,
            "cannot parse Metadata Contract as restricted YAML: %s" % exc)
        return {}
    if owner_document is None:
        return {}
    shape_errors = kblib.validate_metadata_contract_shape(
        document, target=source_path, contract=owner_document)
    for check, label, details in shape_errors:
        builder.add(
            "extension-gate-metadata-contract", label,
            "%s: %s" % (check, details))
    if shape_errors:
        return {}
    fields = {}
    for entry in document.get("extension_fields", ()):
        field_id = entry.get("field")
        if (not isinstance(field_id, str) or
                FIELD_ID_RE.fullmatch(field_id) is None):
            continue
        fields[field_id] = entry
    return fields


def _kernel_metadata_fields(builder, source_path, root_input_snapshots=None):
    """Resolve the Kernel page-field namespace from one frozen root view."""
    fields = set()
    failed = False
    for path, mapping_name in (
            (KERNEL_APPLICABILITY_PATH, "fields"),
            (KERNEL_RELATIONSHIP_PATH, "relationships")):
        try:
            snapshot = (root_input_snapshots or {}).get(path)
            if snapshot is None:
                snapshot = kblib.repository_file_snapshot(
                    builder.root, path, singly_linked=True)
            document = kblib.parse_yaml_subset(snapshot.read_text())
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
        snapshot = ((root_input_snapshots or {}).get(source_path))
        if snapshot is not None:
            text = snapshot.read_text()
        else:
            absolute = _canonical_repository_file(
                builder.root, source_path, singly_linked=True)
            text = _strict_read(absolute)
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


def _completion_values(raw):
    value = raw.strip()
    literal = _literal(value)
    if literal == "None":
        return ()
    # Accept either one code span per value (`` `a`, `b` ``) or one code span
    # around the whole comma-delimited list (`` `a, b` ``), then normalize to
    # the same typed tuple.
    if value.startswith("`") and value.endswith("`") and value.count("`") == 2:
        value = value[1:-1]
    return tuple(
        _literal(part.strip())
        for part in value.split(",")
        if part.strip()
    )


def _capability_registry(builder, source_path, root_input_snapshots=None):
    """Load the canonical closed capability registry exactly once."""
    try:
        import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
        capability_path = "Tools/operation-capabilities.yaml"
        snapshot = ((root_input_snapshots or {}).get(capability_path))
        if snapshot is None:
            document = metadata_execution_contract.load_operation_capabilities(
                root=builder.root)
        else:
            document = kblib.parse_yaml_subset(snapshot.read_text())
            document = (
                metadata_execution_contract
                .validate_operation_capabilities_document(document))
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


def _parse_batch_review_requirements(builder, text, source_path,
                                     role_text, role_path, judgments):
    """Parse the Batch Review Requirements registry into typed IR.

    A configured row is an executable per-batch obligation, not a prose
    reminder: its Judgment Item must be registered, its role must resolve,
    and every enum cell comes from a closed first-version set.  Natural-
    language applicability is deliberately excluded so a declared rule can
    never again be one the machine does not know when to apply.
    """
    # An absent section is the unregistered state, not a defect: this slot
    # ships after profiles already exist, and forcing every routing registry
    # to grow an empty table would turn the rollout itself into a break.
    matches = [item for item in _sections(text)
               if item.heading == BATCH_REVIEW_SECTION]
    if not matches:
        return None, ()
    if len(matches) > 1:
        builder.add(
            "batch-review-requirements-section-count", source_path,
            "expected at most one `## %s` section; found %d" %
            (BATCH_REVIEW_SECTION, len(matches)))
        return None, ()
    section = matches[0]
    registration = _section_registration(
        builder, section, source_path, "batch-review-requirements")
    rows = builder.table(
        section, BATCH_REVIEW_HEADER, source_path,
        "batch-review-requirements")
    if registration in INACTIVE_REGISTRATION_VALUES and rows:
        builder.add(
            "batch-review-none-with-rows", source_path,
            "`Registration: None` requires an empty Batch Review "
            "Requirements table; found %d data row(s)" % len(rows))
    if registration == CONFIGURED_CARRIER_VALUE and not rows:
        builder.add(
            "batch-review-configured-empty", source_path,
            "`Registration: Configured` requires at least one Batch Review "
            "Requirement row")
    if not rows:
        return registration, ()

    if role_text is None:
        builder.add(
            "batch-review-role-registry", source_path,
            "configured Batch Review Requirements require a readable Role "
            "Registry")
        role_ids = frozenset(KERNEL_ROLE_IDS)
    else:
        role_ids = _extension_role_ids(builder, role_text, role_path)
    judgment_ids = {item.judgment_item_id for item in judgments}

    parsed = []
    seen = set()
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, BATCH_REVIEW_HEADER, source_path,
            BATCH_REVIEW_SECTION, row_number, "batch-review-requirements")
        if cells is None:
            continue
        judgment_id = _literal(cells[0].raw)
        target_selector = _literal(cells[1].raw)
        trigger = _literal(cells[2].raw)
        producer_kind = _literal(cells[3].raw)
        receipt_schema = _literal(cells[4].raw)
        role_id = _literal(cells[5].raw)
        valid = True
        if judgment_id not in judgment_ids:
            builder.add(
                "batch-review-judgment-reference", cells[0].target,
                "Judgment Item ID %r is not registered in this Profile's "
                "Judgment Items" % judgment_id, cells[0])
            valid = False
        if judgment_id in seen:
            builder.add(
                "batch-review-judgment-duplicate", cells[0].target,
                "Judgment Item ID %r is required more than once" %
                judgment_id, cells[0])
            valid = False
        seen.add(judgment_id)
        if target_selector not in BATCH_REVIEW_TARGET_SELECTORS:
            builder.add(
                "batch-review-target-selector", cells[1].target,
                "target selector %r must be one of: %s" %
                (target_selector,
                 ", ".join(sorted(BATCH_REVIEW_TARGET_SELECTORS))), cells[1])
            valid = False
        if trigger not in BATCH_REVIEW_TRIGGERS:
            builder.add(
                "batch-review-trigger", cells[2].target,
                "trigger %r must be one of: %s" %
                (trigger, ", ".join(sorted(BATCH_REVIEW_TRIGGERS))), cells[2])
            valid = False
        if producer_kind not in BATCH_REVIEW_PRODUCER_KINDS:
            builder.add(
                "batch-review-producer-kind", cells[3].target,
                "producer kind %r must be one of: %s" %
                (producer_kind,
                 ", ".join(sorted(BATCH_REVIEW_PRODUCER_KINDS))), cells[3])
            valid = False
        if receipt_schema not in BATCH_REVIEW_RECEIPT_SCHEMAS:
            builder.add(
                "batch-review-receipt-schema", cells[4].target,
                "receipt schema %r must be one of: %s" %
                (receipt_schema,
                 ", ".join(sorted(BATCH_REVIEW_RECEIPT_SCHEMAS))), cells[4])
            valid = False
        if role_id not in role_ids:
            builder.add(
                "batch-review-role-reference", cells[5].target,
                "Pass-authority Role ID %r is not a registered role" %
                role_id, cells[5])
            valid = False
        if not valid:
            continue
        builder.edges.append(DependencyEdge(
            kind="batch-review-judgment",
            owner_id="batch-review:%s" % judgment_id,
            target_id=judgment_id))
        parsed.append(BatchReviewRequirement(
            judgment_item_id=judgment_id,
            target_selector=target_selector,
            trigger=trigger,
            producer_kind=producer_kind,
            receipt_schema=receipt_schema,
            pass_authority_role_id=role_id,
            source=cells[0],
        ))
    return registration, tuple(parsed)


def _parse_extension_gates(builder, text, source_path, profile_repo_dir,
                           profile_id, role_text, role_path,
                           vocabulary_fields,
                           metadata_text, metadata_path,
                           metadata_owner_document,
                           judgments, scans, root_input_snapshots=None):
    section = builder.section(
        text, EXTENSION_GATE_SECTION, source_path, "extension-gates")
    if section is None:
        return None, ()
    registration = _section_registration(
        builder, section, source_path, "extension-gates")
    rows = builder.table(
        section, EXTENSION_GATE_HEADER, source_path, "extension-gates")
    if registration in INACTIVE_REGISTRATION_VALUES and rows:
        builder.add(
            "extension-gates-none-with-rows", source_path,
            "`Registration: None` requires an empty extension Gate table; "
            "found %d data row(s)" % len(rows))
    if registration == CONFIGURED_CARRIER_VALUE and not rows:
        builder.add(
            "extension-gates-configured-empty", source_path,
            "`Registration: Configured` requires at least one extension Gate")
    if not rows:
        return registration, ()

    role_ids = (_extension_role_ids(builder, role_text, role_path)
                if role_text is not None else frozenset(KERNEL_ROLE_IDS))
    vocabulary = {
        field.field_id: field.values for field in vocabulary_fields
    }
    metadata_fields = (_metadata_extension_fields(
        builder, metadata_text, metadata_path, metadata_owner_document)
        if metadata_text is not None else {})
    kernel_metadata_fields = _kernel_metadata_fields(
        builder, source_path, root_input_snapshots=root_input_snapshots)
    if role_text is None:
        builder.add(
            "extension-gate-role-registry", source_path,
            "configured extension Gates require a readable Role Registry")
    if metadata_text is None:
        builder.add(
            "extension-gate-metadata-contract", source_path,
            "configured extension Gates require a readable Metadata Contract")
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
    for row_number, row in enumerate(rows, 1):
        cells = builder.cells(
            row, EXTENSION_GATE_HEADER, source_path,
            EXTENSION_GATE_SECTION, row_number, "extension-gates")
        if cells is None:
            continue
        gate_id = _literal(cells[0].raw)
        owner_literal = _literal(cells[1].raw)
        transition_id = _literal(cells[2].raw)
        role_id = _literal(cells[3].raw)
        field_literal = _literal(cells[5].raw)
        field_id = None if field_literal == "None" else field_literal
        completion_values = _completion_values(cells[6].raw)
        judgment_id = _literal(cells[7].raw)
        producer_kind = _literal(cells[8].raw)
        producer_capability = _literal(cells[9].raw)
        receipt_schema = _literal(cells[10].raw)
        consumer_capability = _literal(cells[11].raw)
        valid = True

        gate_match = PROFILE_GATE_ID_RE.fullmatch(gate_id)
        if gate_match is None or gate_match.group(1) != profile_id:
            builder.add(
                "extension-gate-id-invalid", cells[0].target,
                "Gate ID %r must be `P:%s:<lowercase-kebab-name>`" %
                (gate_id, profile_id), cells[0])
            valid = False
        if gate_id in seen_gate_ids:
            builder.add(
                "extension-gate-id-duplicate", cells[0].target,
                "Gate ID %r is registered more than once" % gate_id,
                cells[0])
            valid = False
        seen_gate_ids.add(gate_id)

        if not STABLE_ID_RE.fullmatch(transition_id):
            builder.add(
                "extension-gate-transition-invalid", cells[2].target,
                "blocked transition/action ID %r must be lowercase kebab-case"
                % transition_id, cells[2])
            valid = False
        if transition_id in seen_transitions:
            builder.add(
                "extension-gate-transition-duplicate", cells[2].target,
                "blocked transition/action ID %r is already owned by another "
                "extension Gate" % transition_id, cells[2])
            valid = False
        seen_transitions.add(transition_id)

        owner_gate_id = None
        owner_dependency = None
        if "/" in owner_literal or "#" in owner_literal:
            owner_dependency = builder.repository_dependency(
                "extension-gate-owner", gate_id, cells[1].raw, cells[1],
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
                    "extension-gate-owner-reference", cells[1].target,
                    "owner Gate ID %r does not resolve in the kernel Stable "
                    "Gate ID Registry" % owner_literal, cells[1])
                valid = False
            else:
                owner_gate_id = owner_literal
                builder.edges.append(DependencyEdge(
                    kind="extension-gate-owner", owner_id=gate_id,
                    target_id=owner_gate_id))

        if role_id not in role_ids:
            builder.add(
                "extension-gate-role-reference", cells[3].target,
                "pass-authority Role ID %r is not registered by this Profile"
                % role_id, cells[3])
            valid = False

        if field_id is None:
            if completion_values:
                builder.add(
                    "extension-gate-field-completion", cells[6].target,
                    "completion values require a Vocabulary field ID",
                    cells[6])
                valid = False
        else:
            if not FIELD_ID_RE.fullmatch(field_id) or field_id not in vocabulary:
                builder.add(
                    "extension-gate-field-reference", cells[5].target,
                    "Vocabulary field ID %r is not a registered Profile field"
                    % field_id, cells[5])
                valid = False
            if kernel_metadata_fields is None:
                valid = False
            elif field_id in kernel_metadata_fields:
                builder.add(
                    "extension-gate-field-kernel-collision",
                    cells[5].target,
                    "typed Profile Gate field %r collides with the frozen "
                    "Kernel metadata namespace" % field_id, cells[5])
                valid = False
            if field_id not in metadata_fields:
                builder.add(
                    "extension-gate-field-applicability", cells[5].target,
                    "typed Gate field %r must be declared by this Profile's "
                    "Metadata Contract extension_fields; kernel-managed and "
                    "vocabulary-only fields cannot be projected by a Profile "
                    "Gate" % field_id, cells[5])
                valid = False
            elif metadata_fields[field_id].get("shape") != "nonempty-string":
                builder.add(
                    "extension-gate-field-shape", cells[5].target,
                    "typed Gate field %r must have Metadata Contract shape "
                    "nonempty-string for enum projection" % field_id,
                    cells[5])
                valid = False
            if not completion_values:
                builder.add(
                    "extension-gate-field-completion", cells[6].target,
                    "a Vocabulary field Gate requires at least one registered "
                    "completion value", cells[6])
                valid = False
            if len(set(completion_values)) != len(completion_values) or any(
                    not VOCABULARY_VALUE_RE.fullmatch(value)
                    for value in completion_values):
                builder.add(
                    "extension-gate-completion-invalid", cells[6].target,
                    "completion values must be unique lowercase vocabulary "
                    "tokens", cells[6])
                valid = False
            unknown_values = sorted(
                set(completion_values).difference(vocabulary.get(field_id, ())))
            if field_id in vocabulary and unknown_values:
                builder.add(
                    "extension-gate-completion-reference", cells[6].target,
                    "completion value(s) are not registered for %s: %s" %
                    (field_id, ", ".join(unknown_values)), cells[6])
                valid = False
            if not _capability_supports(
                    builder, supports,
                    PROFILE_EXTENSION_ENUM_WRITER_CAPABILITY,
                    PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION,
                    cells[5], kind="writer"):
                builder.add(
                    "extension-gate-writer-capability", cells[5].target,
                    "typed Profile Gate field %r requires installed writer "
                    "%r operation %r" %
                    (field_id, PROFILE_EXTENSION_ENUM_WRITER_CAPABILITY,
                     PROFILE_EXTENSION_ENUM_PROJECTION_OPERATION),
                    cells[5])
                valid = False

        judgment_matches = judgment_by_id.get(judgment_id, ())
        if len(judgment_matches) != 1:
            builder.add(
                "extension-gate-judgment-reference", cells[7].target,
                "Judgment Item reference %r must resolve exactly once; found "
                "%d" % (judgment_id, len(judgment_matches)), cells[7])
            valid = False

        if producer_kind not in PRODUCER_KINDS:
            builder.add(
                "extension-gate-producer-kind", cells[8].target,
                "producer kind must be `deterministic` or "
                "`manual-attestation`; found %r" % producer_kind, cells[8])
            valid = False
        expected_capability = PRODUCER_CAPABILITY_BY_KIND.get(producer_kind)
        if (not _capability_registered(
                builder, checker, producer_capability, "producer", cells[9]) or
                producer_capability != expected_capability):
            builder.add(
                "extension-gate-producer-capability", cells[9].target,
                "producer capability %r is not the registered capability for "
                "producer kind %r" % (producer_capability, producer_kind),
                cells[9])
            valid = False
        expected_schema = RECEIPT_SCHEMA_BY_KIND.get(producer_kind)
        if (not _capability_registered(
                builder, checker, receipt_schema, "receipt-schema", cells[10]) or
                receipt_schema != expected_schema):
            builder.add(
                "extension-gate-receipt-schema", cells[10].target,
                "receipt schema %r is not the registered schema for producer "
                "kind %r" % (receipt_schema, producer_kind), cells[10])
            valid = False
        consumer_operation = (
            FIELD_GATE_CONSUMER_OPERATION if field_id is not None else
            NON_FIELD_GATE_CONSUMER_OPERATION)
        consumer_registered = _capability_registered(
            builder, checker, consumer_capability, "consumer", cells[11])
        consumer_supports_transition = _capability_supports(
            builder, supports, consumer_capability,
            consumer_operation, cells[11])
        if not (consumer_registered and consumer_supports_transition):
            builder.add(
                "extension-gate-consumer-capability", cells[11].target,
                "consumer capability %r is not registered with the "
                "%r operation required by this Gate shape" %
                (consumer_capability, consumer_operation),
                cells[11])
            valid = False

        if (producer_kind == "deterministic" and field_id is not None and
                len(completion_values) != 1):
            builder.add(
                "extension-gate-deterministic-completion", cells[6].target,
                "a deterministic typed-field Gate must declare exactly one "
                "completion value, so scan pass has one closed projection",
                cells[6])
            valid = False

        producer_reference = None
        if producer_kind == "manual-attestation":
            producer_reference = role_id if role_id in role_ids else None
        elif producer_kind == "deterministic":
            producer_matches = scan_by_judgment.get(judgment_id, ())
            if len(producer_matches) != 1:
                builder.add(
                    "extension-gate-producer-reference", cells[9].target,
                    "deterministic Gate Judgment Item %r must be produced by "
                    "exactly one Registered Scan; found %d" %
                    (judgment_id, len(producer_matches)), cells[9])
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
            applicability=cells[4].raw.strip(),
            field_id=field_id,
            completion_values=completion_values,
            judgment_item_id=judgment_id,
            producer_kind=producer_kind,
            producer_capability=producer_capability,
            producer_reference=producer_reference,
            receipt_schema=receipt_schema,
            consumer_capability=consumer_capability,
            source=cells[0],
            field_values=(tuple(vocabulary.get(field_id, ()))
                          if field_id is not None else ()),
        ))
    return registration, tuple(parsed)


def _empty_contract(builder, manifest_path="", manifest_repo_path="",
                    profile_root="", profile_repo_dir=""):
    return ProfileContract(
        root=builder.root,
        manifest_path=manifest_path,
        manifest_repo_path=manifest_repo_path,
        profile_root=profile_root,
        profile_repo_dir=profile_repo_dir,
        audit_registry_path=None,
        scan_registry_path=None,
        routing_registry_path=None,
        extension_registration=None,
        extension_dimensions=(),
        judgment_items=(),
        registered_scans=(),
        extension_gate_registration=None,
        extension_gates=(),
        dependency_edges=(),
        source_cells=tuple(builder.source_cells),
        diagnostics=tuple(builder.diagnostics),
    )


def load_profile_contract(root, manifest_path, sentinel="TODO(profile)",
                          profile_snapshot=None, root_input_snapshots=None):
    """Load and link the machine-active contract of one Profile manifest.

    The return value always contains deterministic diagnostics and any safely
    parsed partial IR.  Only ``contract.authorized`` may be consumed as runtime
    authority.  Callers must not infer authorization from the presence of a
    row or dependency in an unauthorized contract.
    """
    builder = _Builder(root, manifest_path, sentinel)
    profile_form_expected = 0
    profile_form_conformant = 0
    try:
        root_real, manifest_absolute, manifest_relative = _manifest_location(
            builder.root_input, manifest_path)
    except (OSError, ValueError) as exc:
        builder.add(
            "profile-contract-manifest-path", os.fspath(manifest_path),
            "manifest path is invalid: %s" % exc,
        )
        return _empty_contract(builder)
    builder.root = root_real
    try:
        audit_dimension_contract.current_audit_dimension_values(
            builder.root, snapshots=root_input_snapshots)
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        builder.add(
            "profile-contract-audit-dimension-base-invalid",
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH,
            "cannot load the Kernel-owned audit-dimension base registry: %s" %
            exc,
        )
        return _empty_contract(builder)
    try:
        interface_document = load_profile_interface(
            builder.root, snapshots=root_input_snapshots)
        if interface_document != _SHIPPED_PROFILE_INTERFACE:
            raise ValueError(
                "adopting registry differs from the validator's deployed "
                "Kernel interface")
        interface_slots = profile_interface_slots(interface_document)
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        builder.add(
            "profile-contract-interface-invalid", PROFILE_INTERFACE_PATH,
            "cannot load the Kernel-owned Profile interface registry: %s" % exc,
        )
        return _empty_contract(builder)
    required_typed_slots = {
        AUDIT_SLOT, SCAN_SLOT, ROLE_SLOT, VOCABULARY_SLOT,
        METADATA_SLOT, ROUTING_SLOT, EXPRESSION_LAYER_ENTRY_SLOT,
    }
    missing_typed = sorted(required_typed_slots - set(interface_slots))
    if missing_typed:
        builder.add(
            "profile-contract-interface-incomplete", PROFILE_INTERFACE_PATH,
            "Profile interface omits typed slot(s): %s" %
            ", ".join(missing_typed),
        )
        return _empty_contract(builder)
    profile_root = os.path.dirname(manifest_absolute)
    try:
        profile_repo_dir = _repo_relative(builder.root, profile_root)
    except ValueError as exc:
        builder.add(
            "profile-contract-profile-root", manifest_relative,
            "selected Profile directory is invalid: %s" % exc,
        )
        return _empty_contract(
            builder, manifest_absolute, manifest_relative, profile_root)

    try:
        if profile_snapshot is None:
            profile_snapshot = kblib.repository_tree_snapshot(
                builder.root, profile_repo_dir)
        if (os.path.realpath(profile_snapshot.root) != builder.root or
                profile_snapshot.relative_directory != profile_repo_dir):
            raise ValueError(
                "supplied Profile snapshot does not bind %s under this root" %
                profile_repo_dir)
        builder.profile_snapshot = profile_snapshot
    except (OSError, ValueError) as exc:
        builder.add(
            "profile-contract-snapshot-invalid", manifest_relative,
            "cannot bind one immutable Profile byte snapshot: %s" % exc,
        )
        return _empty_contract(
            builder, manifest_absolute, manifest_relative,
            profile_root, profile_repo_dir)

    if (os.path.basename(manifest_absolute) !=
            profile_layout_contract.PROFILE_MANIFEST_NAME):
        builder.add(
            "profile-contract-manifest-name", manifest_relative,
            "Profile manifest must be named `%s`" %
            profile_layout_contract.PROFILE_MANIFEST_NAME,
        )
    try:
        _canonical_repository_file(
            builder.root, manifest_relative, singly_linked=True)
        manifest_text = builder.read_profile_text(manifest_relative)
    except (OSError, UnicodeError, ValueError) as exc:
        builder.add(
            "profile-contract-manifest-unreadable", manifest_relative,
            "cannot read Profile manifest as a canonical strict UTF-8 regular "
            "file: %s" % exc,
        )
        return _empty_contract(
            builder, manifest_absolute, manifest_relative,
            profile_root, profile_repo_dir)
    builder.scan_text_sentinel(
        manifest_text, manifest_relative, "Profile manifest")
    (profile_form_expected, profile_form_conformant,
     pending_form_subheadings) = _validate_profile_forms(
         builder, interface_document, manifest_text, manifest_relative,
         profile_root, root_input_snapshots)
    try:
        metadata_owner_path = interface_document["registry_references"][
            "metadata_profile_contract"]
        metadata_owner_text = _shape_owner_text(
            builder.root, metadata_owner_path,
            root_input_snapshots)
        metadata_owner_document = kblib.load_metadata_profile_contract(
            builder.root, text=metadata_owner_text)
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError):
        # The form pass already emitted the owner diagnostic. Typed consumers
        # must not silently fall back to an import-time owner projection.
        metadata_owner_document = None

    audit_path, audit_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, AUDIT_SLOT)
    scan_path, scan_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, SCAN_SLOT)
    role_path, role_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, ROLE_SLOT)
    vocabulary_path, vocabulary_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, VOCABULARY_SLOT)
    metadata_path, metadata_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, METADATA_SLOT)
    routing_path, routing_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, ROUTING_SLOT)
    expression_path, expression_text = _load_bound_slot(
        builder, manifest_text, manifest_absolute, manifest_relative,
        profile_root, EXPRESSION_LAYER_ENTRY_SLOT)

    # Bind every declared first-hop file, not only the two registries whose
    # contents this linker interprets transitively.  ``check_profile`` owns the
    # exact 14-slot cardinality; this layer owns the canonical path and typed
    # edge of each declared interface slot so the contract fingerprint cannot
    # omit the rest of the package graph.
    if audit_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=AUDIT_SLOT, path=audit_path))
    if scan_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=SCAN_SLOT, path=scan_path))
    if role_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=ROLE_SLOT, path=role_path))
    if vocabulary_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=VOCABULARY_SLOT,
            path=vocabulary_path))
    if metadata_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=METADATA_SLOT,
            path=metadata_path))
    if routing_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=ROUTING_SLOT, path=routing_path))
    if expression_path is not None:
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=EXPRESSION_LAYER_ENTRY_SLOT,
            path=expression_path))
    bindings, duplicate_bindings = kblib.profile_slot_bindings(
        manifest_text, include_duplicates=True)
    for slot_name in interface_slots:
        if slot_name in (
                AUDIT_SLOT, SCAN_SLOT, ROLE_SLOT, VOCABULARY_SLOT,
                METADATA_SLOT,
                ROUTING_SLOT, EXPRESSION_LAYER_ENTRY_SLOT):
            continue
        if slot_name in duplicate_bindings:
            source = _slot_source(
                manifest_text, manifest_relative, slot_name)
            builder.add(
                "profile-contract-slot-duplicate",
                source.target if source else manifest_relative,
                "Implemented Slots repeats `%s`" % slot_name, source)
            continue
        binding = bindings.get(slot_name)
        if binding is None:
            builder.add(
                "profile-contract-slot-missing", manifest_relative,
                "Implemented Slots has no `%s` binding" % slot_name)
            continue
        source = _slot_source(manifest_text, manifest_relative, slot_name)
        if sentinel and sentinel in binding:
            builder.add(
                "profile-contract-sentinel",
                source.target if source else manifest_relative,
                "`%s` binding contains the unfilled sentinel %r" %
                (slot_name, sentinel), source)
            continue
        kind, resolved = kblib.resolve_profile_binding(
            binding, builder.root, profile_root)
        if kind != "path":
            builder.add(
                "profile-contract-slot-invalid",
                source.target if source else manifest_relative,
                "`%s` binding is not one canonical file inside the selected "
                "Profile: resolver returned %s (%r)" %
                (slot_name, kind, resolved), source)
            continue
        try:
            relative = os.path.relpath(
                os.path.abspath(resolved), builder.root).replace(os.sep, "/")
            slot_text = builder.read_profile_text(relative)
        except (OSError, UnicodeError) as exc:
            builder.add(
                "profile-contract-slot-unreadable",
                source.target if source else manifest_relative,
                "`%s` binding cannot be read as strict UTF-8: %s" %
                (slot_name, exc), source)
            continue
        builder.scan_text_sentinel(
            slot_text, relative, "slot `%s`" % slot_name)
        builder.edges.append(DependencyEdge(
            kind="manifest-slot", owner_id=slot_name, path=relative))

    registration = None
    dimensions = ()
    judgments = ()
    scans = ()
    gate_registration = None
    gates = ()
    expression_registration = None
    expression_artifacts = ()
    vocabulary_fields = ()
    volatility_defaults = ()
    try:
        scan_capabilities = scan_capability_records(
            load_scan_capabilities(
                builder.root, snapshots=root_input_snapshots))
    except (OSError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        builder.add(
            "scan-capability-registry-invalid", SCAN_CAPABILITY_PATH,
            "cannot load the Tool-owned scan capability registry: %s" % exc)
        scan_capabilities = {}
    if audit_text is not None:
        registration, dimensions = _parse_extensions(
            builder, audit_text, audit_path)
        judgments = _parse_judgments(
            builder, audit_text, audit_path, profile_repo_dir, dimensions)
    if scan_text is not None:
        scans = _parse_scans(
            builder, scan_text, scan_path, profile_repo_dir,
            scan_capabilities)
    if vocabulary_text is not None:
        vocabulary_fields, volatility_defaults = _vocabulary_extensions(
            builder, vocabulary_text, vocabulary_path,
            root_input_snapshots=root_input_snapshots)

    judgment_ids = {}
    for item in judgments:
        judgment_ids.setdefault(item.judgment_item_id, []).append(item)
    for scan in scans:
        matches = judgment_ids.get(scan.judgment_item_id, ())
        if len(matches) != 1:
            builder.add(
                "registered-scan-judgment-reference", scan.source.target,
                "scan %r Judgment Item reference %r must resolve exactly once; "
                "found %d" %
                (scan.scan_id, scan.judgment_item_id, len(matches)), scan.source,
            )
        else:
            builder.edges.append(DependencyEdge(
                kind="scan-judgment",
                owner_id=scan.scan_id,
                target_id=scan.judgment_item_id,
            ))

    review_registration, review_requirements = None, ()
    if routing_text is not None:
        declared_profile_id, _identity_errors = kblib.profile_identity(
            manifest_text, os.path.basename(profile_repo_dir))
        gate_registration, gates = _parse_extension_gates(
            builder, routing_text, routing_path, profile_repo_dir,
            declared_profile_id or os.path.basename(profile_repo_dir),
            role_text, role_path, vocabulary_fields,
            metadata_text, metadata_path, metadata_owner_document,
            judgments, scans,
            root_input_snapshots=root_input_snapshots)
        review_registration, review_requirements = \
            _parse_batch_review_requirements(
                builder, routing_text, routing_path,
                role_text, role_path, judgments)

    if expression_text is not None:
        expression_registration, expression_artifacts = \
            _parse_registered_artifacts(
                builder, expression_text, expression_path,
                profile_repo_dir, vocabulary_fields,
                metadata_text, metadata_path, metadata_owner_document, gates,
                root_input_snapshots=root_input_snapshots)

    profile_form_conformant -= _validate_form_subheading_references(
        builder, pending_form_subheadings)

    edges = tuple(sorted(
        builder.edges,
        key=lambda edge: (
            edge.kind, edge.owner_id, edge.target_id or "",
            edge.path or "", edge.fragment or ""),
    ))
    return ProfileContract(
        root=builder.root,
        manifest_path=manifest_absolute,
        manifest_repo_path=manifest_relative,
        profile_root=profile_root,
        profile_repo_dir=profile_repo_dir,
        audit_registry_path=audit_path,
        scan_registry_path=scan_path,
        routing_registry_path=routing_path,
        extension_registration=registration,
        extension_dimensions=tuple(dimensions),
        judgment_items=tuple(judgments),
        registered_scans=tuple(scans),
        extension_gate_registration=gate_registration,
        extension_gates=tuple(gates),
        batch_review_registration=review_registration,
        batch_review_requirements=tuple(review_requirements),
        vocabulary_fields=tuple(vocabulary_fields),
        volatility_defaults=tuple(volatility_defaults),
        expression_registry_path=expression_path,
        expression_registration=expression_registration,
        expression_artifacts=tuple(expression_artifacts),
        profile_form_expected=profile_form_expected,
        profile_form_conformant=profile_form_conformant,
        dependency_edges=edges,
        source_cells=tuple(builder.source_cells),
        diagnostics=tuple(builder.diagnostics),
    )


def expression_status_target_projection(contract):
    """Project the selected Profile's exact expression completion target.

    This function consumes only one already-linked, authorized
    :class:`ProfileContract`; it performs no filesystem reads.  A Profile that
    registers no ``Expression Status Axis`` field has no expression target and
    therefore projects the legal empty tuple.  Once that role is registered,
    exactly one field and exactly one Gate for that field must resolve, or the
    projection fails closed instead of guessing which Gate or values apply.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    if not contract.authorized:
        raise ProfileContractError(
            "Profile contract is not authorized: %s" %
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
    if not contract.authorized:
        raise ProfileContractError(
            "Profile contract is not authorized: %s" %
            format_diagnostics(contract.diagnostics))
    return tuple(sorted({
        artifact.dependency_map_path
        for artifact in contract.expression_artifacts
        if artifact.dependency_map_path is not None
    }))


def terminal_receipt_dimensions_projection(contract):
    """Return the exact dimension namespace Terminal Proof must account for.

    The Kernel-owned base order is always present.  The selected Profile may
    extend that namespace only through authorized Extension Dimension rows
    whose typed target set includes ``receipt``.  Review-only registrations
    remain valid Profile review obligations, but they never become Terminal
    receipt dimensions merely because an AuditPlan records their judgment.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    if not contract.authorized:
        raise ProfileContractError(
            "Profile contract is not authorized: %s" %
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
    """Project the authorized Profile's domain-to-volatility policy.

    The Profile linker is the sole parser and validator for the selected
    Vocabulary Extensions slot.  Downstream planners and artifact compilers
    consume this immutable typed view rather than reopening Profile bytes.
    """
    if not isinstance(contract, ProfileContract):
        raise TypeError("contract must be a ProfileContract")
    if not contract.authorized:
        raise ProfileContractError(
            "Profile contract is not authorized: %s" %
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
    """Compile one authorized scan row to a shell-free subprocess argv.

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
    if not contract.authorized:
        raise ProfileContractError(
            "Profile contract is not authorized: %s" %
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


__all__ = [
    'ProfileContract',
    'ProfileContractError',
    'ProfileForm',
    'AUDIT_DIMENSION_BASE_PATH',
    'KERNEL_VOCABULARY_PATH',
    'SCAN_CAPABILITY_PATH',
    'compile_registered_scan_command',
    'expression_dependency_map_paths_projection',
    'format_diagnostics',
    'load_profile_interface',
    'load_profile_contract',
    'profile_interface_forms',
    'profile_interface_slots',
    'registered_scan_entrypoint',
    'scan_capability_implementation_paths',
    'terminal_receipt_dimensions_projection',
    'volatility_defaults_projection',
]
