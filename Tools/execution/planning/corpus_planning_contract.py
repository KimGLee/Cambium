"""Strict projection of the Kernel-owned Corpus Planning machine contract.

``kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml``
owns the Profile-slot envelope, applicability branches, artifact-role map,
receipt freshness binding, close-trigger identities, and the three registered
artifact record contracts already defined by K02/03 through K02/07.  This
runtime-independent module only validates that registry, projects its closed
values, and implements the shared mechanical branch/binding algorithms.  It
does not inspect planning artifacts, select a Profile or route, decide
semantic acceptance, or write state.
"""
from Tools.platform.repository.repository import repository_source_root

import os
import re
from types import MappingProxyType

import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import nonempty_string


CORPUS_PLANNING_CONTRACT_PATH = (
    "kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml")

_DOCUMENT_FIELDS = {
    "schema_version", "contract_id", "semantic_owner", "slot_envelope",
    "receipt_binding", "close_triggers", "artifact_contracts",
}
_SLOT_ENVELOPE_FIELDS = {
    "slot_name", "schema_version", "fields", "applicability_fields",
    "artifact_binding_fields", "capability_scale_fields",
    "pass_authority_fields", "applicability_branches", "artifact_roles",
    "semantic_acceptance_scope",
}
_SLOT_FIELDS = {
    "schema_version", "applicability", "artifact_bindings",
    "capability_scale", "pass_authority",
}
_APPLICABILITY_FIELDS = {"state", "reason"}
_CAPABILITY_SCALE_FIELDS = {
    "rank", "value", "predicate", "target_eligible",
}
_PASS_AUTHORITY_FIELDS = {"role_id", "decision_scope_id"}
_APPLICABILITY_BRANCH_ROLES = {"configured", "inactive"}
_RECEIPT_BINDING_FIELDS = {"fields", "path_sha_bindings"}
_PATH_SHA_BINDING_FIELDS = {
    "path_field", "sha256_field", "requirement",
}
_PATH_SHA_REQUIREMENTS = {"always", "configured"}
_CLOSE_TRIGGER_ROLES = {"selected_route", "affected_manifest"}
_ARTIFACT_CONTRACT_ROLES = {
    "global_map", "capability_matrix", "gap_register",
}
_GLOBAL_MAP_CONTRACT_FIELDS = {
    "contract_id", "semantic_owner", "document_schema_version",
    "document_fields", "collections", "relation_types",
}
_GLOBAL_MAP_COLLECTION_ROLES = {"entries", "typed_dependencies"}
_COLLECTION_FIELDS = {
    "record_fields", "minimum_items", "unique_fields",
    "nonempty_list_fields",
}
_CAPABILITY_CONTRACT_FIELDS = {
    "contract_id", "semantic_owner", "document_schema_version",
    "document_fields", "collection", "priority_values_owner",
    "scale_owner", "conditional_rules",
}
_CAPABILITY_COLLECTION_FIELDS = _COLLECTION_FIELDS | {"name", "list_fields"}
_CAPABILITY_RULE_FIELDS = {
    "target_requires_eligible_scale_row",
    "rank_above_zero_requires_evidence",
    "below_target_requires_gap",
    "matrix_gap_links_bidirectional",
}
_GAP_CONTRACT_FIELDS = {
    "contract_id", "semantic_owner", "document_schema_version",
    "document_fields", "collection", "statuses", "promoted_statuses",
    "unpromoted_statuses", "resolved_status", "conditional_rules",
}
_GAP_COLLECTION_FIELDS = _CAPABILITY_COLLECTION_FIELDS
_GAP_RULE_FIELDS = {
    "promoted_requires_coverage_path",
    "unpromoted_forbids_coverage_path",
    "resolved_requires_evidence",
    "matrix_gap_links_bidirectional",
}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _closed_mapping(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        missing = sorted(set(fields) - set(value or {})) \
            if isinstance(value, dict) else sorted(fields)
        extra = sorted(set(value) - set(fields)) \
            if isinstance(value, dict) else []
        raise ValueError(
            "%s fields are not closed: missing=%s extra=%s" %
            (label, missing, extra))
    return value


def _unique_string_list(value, label, *, allow_empty=False):
    if (not isinstance(value, list) or
            (not allow_empty and not value) or
            any(not isinstance(item, str) or not item or
                item.strip() != item for item in value)):
        qualifier = "a string list" if allow_empty else \
            "a non-empty string list"
        raise ValueError("%s must be %s" % (label, qualifier))
    if len(value) != len(set(value)):
        raise ValueError("%s must not contain duplicate values" % label)
    return tuple(value)


def _positive_or_zero_integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("%s must be a non-negative integer" % label)
    return value


def _collection_contract(value, fields, label):
    row = _closed_mapping(value, fields, label)
    record_fields = _unique_string_list(
        row.get("record_fields"), "%s record_fields" % label)
    unique_fields = _unique_string_list(
        row.get("unique_fields"), "%s unique_fields" % label,
        allow_empty=True)
    nonempty_list_fields = _unique_string_list(
        row.get("nonempty_list_fields"),
        "%s nonempty_list_fields" % label, allow_empty=True)
    list_fields = tuple(nonempty_list_fields)
    if "list_fields" in fields:
        list_fields = _unique_string_list(
            row.get("list_fields"), "%s list_fields" % label,
            allow_empty=True)
        if not set(nonempty_list_fields).issubset(list_fields):
            raise ValueError(
                "%s nonempty_list_fields must be a subset of list_fields" %
                label)
    unknown = (set(unique_fields) | set(list_fields)) - set(record_fields)
    if unknown:
        raise ValueError(
            "%s field constraints name unknown record fields: %s" %
            (label, ", ".join(sorted(unknown))))
    minimum_items = _positive_or_zero_integer(
        row.get("minimum_items"), "%s minimum_items" % label)
    return {
        "record_fields": frozenset(record_fields),
        "minimum_items": minimum_items,
        "unique_fields": tuple(unique_fields),
        "nonempty_list_fields": tuple(nonempty_list_fields),
        "list_fields": tuple(list_fields),
    }


def _true_rules(value, fields, label):
    row = _closed_mapping(value, fields, label)
    if any(row.get(field) is not True for field in fields):
        raise ValueError("%s rules must all be enabled" % label)
    return frozenset(fields)


def _artifact_contract_values(value):
    artifacts = _closed_mapping(
        value, _ARTIFACT_CONTRACT_ROLES,
        "Corpus Planning artifact contracts")

    global_map = _closed_mapping(
        artifacts.get("global_map"), _GLOBAL_MAP_CONTRACT_FIELDS,
        "Global Map contract")
    if (global_map.get("contract_id") != "global-map" or
            global_map.get("semantic_owner") != "K02/05" or
            global_map.get("document_schema_version") != 1):
        raise ValueError("Global Map contract identity is invalid")
    global_fields = _unique_string_list(
        global_map.get("document_fields"), "Global Map document_fields")
    global_collections = _closed_mapping(
        global_map.get("collections"), _GLOBAL_MAP_COLLECTION_ROLES,
        "Global Map collections")
    entry_contract = _collection_contract(
        global_collections.get("entries"), _COLLECTION_FIELDS,
        "Global Map entries")
    edge_contract = _collection_contract(
        global_collections.get("typed_dependencies"), _COLLECTION_FIELDS,
        "Global Map typed_dependencies")
    if not _GLOBAL_MAP_COLLECTION_ROLES.issubset(global_fields):
        raise ValueError(
            "Global Map document_fields must name both collections")
    relation_types = _unique_string_list(
        global_map.get("relation_types"), "Global Map relation_types")

    capability = _closed_mapping(
        artifacts.get("capability_matrix"), _CAPABILITY_CONTRACT_FIELDS,
        "Capability Matrix contract")
    if (capability.get("contract_id") != "capability-matrix" or
            capability.get("semantic_owner") != "K02/06" or
            capability.get("document_schema_version") != 1):
        raise ValueError("Capability Matrix contract identity is invalid")
    capability_fields = _unique_string_list(
        capability.get("document_fields"),
        "Capability Matrix document_fields")
    capability_collection = _collection_contract(
        capability.get("collection"), _CAPABILITY_COLLECTION_FIELDS,
        "Capability Matrix capabilities")
    if capability.get("collection", {}).get("name") != "capabilities" or \
            "capabilities" not in capability_fields:
        raise ValueError(
            "Capability Matrix collection must be capabilities")
    if capability.get("priority_values_owner") != \
            "K08-vocabulary.priority":
        raise ValueError(
            "Capability Matrix priority owner must be K08 vocabulary")
    if capability.get("scale_owner") != \
            "selected-profile.Corpus-Planning.capability_scale":
        raise ValueError(
            "Capability Matrix scale owner must be the selected Profile")
    capability_rules = _true_rules(
        capability.get("conditional_rules"), _CAPABILITY_RULE_FIELDS,
        "Capability Matrix conditional rules")

    gap = _closed_mapping(
        artifacts.get("gap_register"), _GAP_CONTRACT_FIELDS,
        "Gap Register contract")
    if (gap.get("contract_id") != "gap-register" or
            gap.get("semantic_owner") != "K02/07" or
            gap.get("document_schema_version") != 1):
        raise ValueError("Gap Register contract identity is invalid")
    gap_fields = _unique_string_list(
        gap.get("document_fields"), "Gap Register document_fields")
    gap_collection = _collection_contract(
        gap.get("collection"), _GAP_COLLECTION_FIELDS,
        "Gap Register gaps")
    if gap.get("collection", {}).get("name") != "gaps" or \
            "gaps" not in gap_fields:
        raise ValueError("Gap Register collection must be gaps")
    statuses = _unique_string_list(
        gap.get("statuses"), "Gap Register statuses")
    promoted = _unique_string_list(
        gap.get("promoted_statuses"), "Gap Register promoted_statuses")
    unpromoted = _unique_string_list(
        gap.get("unpromoted_statuses"),
        "Gap Register unpromoted_statuses")
    if set(promoted) | set(unpromoted) != set(statuses) or \
            set(promoted).intersection(unpromoted):
        raise ValueError(
            "Gap Register promoted/unpromoted statuses must partition status")
    resolved = gap.get("resolved_status")
    if resolved not in promoted:
        raise ValueError(
            "Gap Register resolved_status must be promoted")
    gap_rules = _true_rules(
        gap.get("conditional_rules"), _GAP_RULE_FIELDS,
        "Gap Register conditional rules")

    return {
        "global_map_document_fields": frozenset(global_fields),
        "global_map_entry_contract": entry_contract,
        "global_map_edge_contract": edge_contract,
        "global_map_relation_types": frozenset(relation_types),
        "capability_matrix_document_fields": frozenset(capability_fields),
        "capability_contract": capability_collection,
        "capability_rules": capability_rules,
        "gap_register_document_fields": frozenset(gap_fields),
        "gap_contract": gap_collection,
        "gap_statuses": frozenset(statuses),
        "gap_promoted_statuses": frozenset(promoted),
        "gap_unpromoted_statuses": frozenset(unpromoted),
        "gap_resolved_status": resolved,
        "gap_rules": gap_rules,
    }


def validate_corpus_planning_contract(document):
    """Strictly validate one registry and return its mechanical projection."""
    _closed_mapping(document, _DOCUMENT_FIELDS,
                    "Corpus Planning contract")
    if document.get("schema_version") != 2:
        raise ValueError("Corpus Planning contract schema_version must be 2")
    if document.get("contract_id") != "cambium-corpus-planning-contract":
        raise ValueError(
            "Corpus Planning contract_id must be "
            "cambium-corpus-planning-contract")
    if document.get("semantic_owner") != \
            "K02/03+K02/04+K02/05+K02/06+K02/07":
        raise ValueError(
            "Corpus Planning semantic_owner must cover K02/03 through K02/07")

    slot = _closed_mapping(
        document.get("slot_envelope"), _SLOT_ENVELOPE_FIELDS,
        "Corpus Planning slot_envelope")
    if not nonempty_string(slot.get("slot_name")):
        raise ValueError("Corpus Planning slot_name must be non-empty")
    if slot.get("schema_version") != 1:
        raise ValueError(
            "Corpus Planning slot schema_version must be integer 1")
    slot_fields = _unique_string_list(
        slot.get("fields"), "Corpus Planning slot fields")
    if set(slot_fields) != _SLOT_FIELDS:
        raise ValueError(
            "Corpus Planning slot fields must describe the closed envelope")
    applicability_fields = _unique_string_list(
        slot.get("applicability_fields"),
        "Corpus Planning applicability fields")
    if set(applicability_fields) != _APPLICABILITY_FIELDS:
        raise ValueError(
            "Corpus Planning applicability fields must describe state/reason")
    artifact_fields = _unique_string_list(
        slot.get("artifact_binding_fields"),
        "Corpus Planning artifact binding fields")
    scale_fields = _unique_string_list(
        slot.get("capability_scale_fields"),
        "Corpus Planning capability scale fields")
    if set(scale_fields) != _CAPABILITY_SCALE_FIELDS:
        raise ValueError(
            "Corpus Planning capability scale fields are incomplete")
    authority_fields = _unique_string_list(
        slot.get("pass_authority_fields"),
        "Corpus Planning pass authority fields")
    if set(authority_fields) != _PASS_AUTHORITY_FIELDS:
        raise ValueError(
            "Corpus Planning pass authority fields are incomplete")

    branches = _closed_mapping(
        slot.get("applicability_branches"),
        _APPLICABILITY_BRANCH_ROLES,
        "Corpus Planning applicability branches")
    if (not all(nonempty_string(value) and value.strip() == value
                for value in branches.values()) or
            len(set(branches.values())) != len(branches)):
        raise ValueError(
            "Corpus Planning applicability branches must be distinct "
            "non-empty strings")
    roles = _closed_mapping(
        slot.get("artifact_roles"), set(artifact_fields),
        "Corpus Planning artifact roles")
    if (not all(nonempty_string(value) and value.strip() == value
                for value in roles.values()) or
            len(set(roles.values())) != len(roles)):
        raise ValueError(
            "Corpus Planning artifact roles must be distinct non-empty "
            "strings")
    scope = slot.get("semantic_acceptance_scope")
    if not nonempty_string(scope) or scope.strip() != scope:
        raise ValueError(
            "Corpus Planning semantic_acceptance_scope must be non-empty")

    receipt = _closed_mapping(
        document.get("receipt_binding"), _RECEIPT_BINDING_FIELDS,
        "Corpus Planning receipt binding")
    receipt_fields = _unique_string_list(
        receipt.get("fields"), "Corpus Planning receipt binding fields")
    if "corpus_plan_applicability" not in receipt_fields:
        raise ValueError(
            "Corpus Planning receipt binding must carry applicability")
    path_rows = receipt.get("path_sha_bindings")
    if not isinstance(path_rows, list) or not path_rows:
        raise ValueError(
            "Corpus Planning path/SHA bindings must be a non-empty list")
    path_sha_bindings = []
    path_fields = set()
    sha_fields = set()
    for index, raw in enumerate(path_rows):
        row = _closed_mapping(
            raw, _PATH_SHA_BINDING_FIELDS,
            "Corpus Planning path/SHA binding %d" % index)
        path_field = row.get("path_field")
        sha_field = row.get("sha256_field")
        requirement = row.get("requirement")
        if path_field not in receipt_fields or sha_field not in receipt_fields:
            raise ValueError(
                "Corpus Planning path/SHA binding %d names an unknown "
                "receipt field" % index)
        if path_field in path_fields or sha_field in sha_fields:
            raise ValueError(
                "Corpus Planning path/SHA binding fields must be unique")
        if requirement not in _PATH_SHA_REQUIREMENTS:
            raise ValueError(
                "Corpus Planning path/SHA binding %d has an unknown "
                "requirement" % index)
        path_fields.add(path_field)
        sha_fields.add(sha_field)
        path_sha_bindings.append((path_field, sha_field, requirement))

    triggers = _closed_mapping(
        document.get("close_triggers"), _CLOSE_TRIGGER_ROLES,
        "Corpus Planning close triggers")
    if (not all(nonempty_string(value) and value.strip() == value
                for value in triggers.values()) or
            len(set(triggers.values())) != len(triggers)):
        raise ValueError(
            "Corpus Planning close triggers must be distinct non-empty "
            "strings")

    values = {
        "slot_name": slot["slot_name"],
        "slot_schema_version": slot["schema_version"],
        "slot_fields": frozenset(slot_fields),
        "applicability_fields": frozenset(applicability_fields),
        "artifact_binding_fields": tuple(artifact_fields),
        "capability_scale_fields": frozenset(scale_fields),
        "pass_authority_fields": frozenset(authority_fields),
        "configured_state": branches["configured"],
        "inactive_state": branches["inactive"],
        "artifact_roles": dict(roles),
        "semantic_acceptance_scope": scope,
        "receipt_binding_fields": tuple(receipt_fields),
        "path_sha_bindings": tuple(path_sha_bindings),
        "close_route_trigger": triggers["selected_route"],
        "close_manifest_trigger": triggers["affected_manifest"],
    }
    values.update(_artifact_contract_values(document.get(
        "artifact_contracts")))
    return values


def load_corpus_planning_contract(root=None, *, snapshots=None, text=None):
    """Load and validate the K02 registry from text, a snapshot, or a root."""
    if root is None:
        root = repository_source_root(__file__)
    if text is None:
        snapshot = (snapshots or {}).get(CORPUS_PLANNING_CONTRACT_PATH)
        if snapshot is not None:
            text = snapshot.read_text()
        else:
            text = kblib.read_text(os.path.join(
                root, *CORPUS_PLANNING_CONTRACT_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_corpus_planning_contract(document)
    return document


_SHIPPED_DOCUMENT = load_corpus_planning_contract()
_SHIPPED_VALUES = validate_corpus_planning_contract(_SHIPPED_DOCUMENT)

SLOT_NAME = _SHIPPED_VALUES["slot_name"]
SLOT_SCHEMA_VERSION = _SHIPPED_VALUES["slot_schema_version"]
SLOT_FIELDS = _SHIPPED_VALUES["slot_fields"]
APPLICABILITY_FIELDS = _SHIPPED_VALUES["applicability_fields"]
ARTIFACT_BINDING_FIELDS = _SHIPPED_VALUES["artifact_binding_fields"]
CAPABILITY_SCALE_FIELDS = _SHIPPED_VALUES["capability_scale_fields"]
PASS_AUTHORITY_FIELDS = _SHIPPED_VALUES["pass_authority_fields"]
CONFIGURED_STATE = _SHIPPED_VALUES["configured_state"]
INACTIVE_STATE = _SHIPPED_VALUES["inactive_state"]
APPLICABILITY_STATES = frozenset((CONFIGURED_STATE, INACTIVE_STATE))
ARTIFACT_FIELD_ROLES = _SHIPPED_VALUES["artifact_roles"]
ARTIFACT_ROLES = tuple(
    ARTIFACT_FIELD_ROLES[field] for field in ARTIFACT_BINDING_FIELDS)
SEMANTIC_ACCEPTANCE_SCOPE = _SHIPPED_VALUES[
    "semantic_acceptance_scope"]
PASS_RECEIPT_BINDING_FIELDS = _SHIPPED_VALUES[
    "receipt_binding_fields"]
PASS_RECEIPT_PATH_SHA_BINDINGS = _SHIPPED_VALUES["path_sha_bindings"]
CLOSE_ROUTE_TRIGGER = _SHIPPED_VALUES["close_route_trigger"]
CLOSE_MANIFEST_TRIGGER = _SHIPPED_VALUES["close_manifest_trigger"]
CLOSE_TRIGGERS = frozenset((CLOSE_ROUTE_TRIGGER, CLOSE_MANIFEST_TRIGGER))
def _resolved_contract_values(contract_values=None):
    """Return one already validated projection or validate a raw owner.

    Public helpers keep their historical no-argument behaviour for callers
    that intentionally validate the contract shipped beside this module.
    Runtime entrypoints should instead load one current K02 snapshot and pass
    its projected values explicitly through the complete validation run.
    """
    if contract_values is None:
        return _SHIPPED_VALUES
    if not isinstance(contract_values, dict):
        raise TypeError("Corpus Planning contract values must be a mapping")
    if "slot_envelope" in contract_values:
        return validate_corpus_planning_contract(contract_values)
    missing = sorted(set(_SHIPPED_VALUES) - set(contract_values))
    if missing:
        raise ValueError(
            "Corpus Planning contract projection misses value(s): %s" %
            ", ".join(missing))
    return contract_values


def _artifact_contract_projection(values):
    return MappingProxyType({
        "global_map": MappingProxyType({
            "document_fields": values["global_map_document_fields"],
            "entries": MappingProxyType(values[
                "global_map_entry_contract"]),
            "typed_dependencies": MappingProxyType(values[
                "global_map_edge_contract"]),
            "relation_types": values["global_map_relation_types"],
        }),
        "capability_matrix": MappingProxyType({
            "document_fields": values[
                "capability_matrix_document_fields"],
            "capabilities": MappingProxyType(values[
                "capability_contract"]),
            "rules": values["capability_rules"],
        }),
        "gap_register": MappingProxyType({
            "document_fields": values["gap_register_document_fields"],
            "gaps": MappingProxyType(values["gap_contract"]),
            "statuses": values["gap_statuses"],
            "promoted_statuses": values["gap_promoted_statuses"],
            "unpromoted_statuses": values["gap_unpromoted_statuses"],
            "resolved_status": values["gap_resolved_status"],
            "rules": values["gap_rules"],
        }),
    })


def artifact_contract(role, contract_values=None):
    """Return one immutable K02/05-07 artifact contract projection."""
    contracts = _artifact_contract_projection(
        _resolved_contract_values(contract_values))
    try:
        return contracts[role]
    except KeyError as exc:
        raise ValueError(
            "unknown Corpus Planning artifact contract %r" % role) from exc


def current_corpus_planning_contract_values(root=None, *, snapshots=None):
    """Return current values and reject drift from the deployed projection."""
    document = load_corpus_planning_contract(root, snapshots=snapshots)
    if document != _SHIPPED_DOCUMENT:
        raise ValueError(
            "adopting Corpus Planning registry differs from the validator's "
            "deployed Kernel contract")
    return validate_corpus_planning_contract(document)


def _issue(code, path=(), **values):
    issue = {"code": code, "path": tuple(path)}
    issue.update(values)
    return issue


def _envelope_mapping(value, fields, path, issues):
    if not isinstance(value, dict):
        issues.append(_issue("mapping_type", path))
        return {}
    missing = sorted(set(fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing:
        issues.append(_issue("missing_fields", path, fields=tuple(missing)))
    if extra:
        issues.append(_issue("unsupported_fields", path,
                             fields=tuple(extra)))
    return value


def validate_corpus_planning_envelope(
        document, contract=None, *, contract_values=None):
    """Validate the current shared slot envelope and its two branches.

    Returns ``(normalized, issues)``.  Issues are neutral structural records;
    producer adapters retain their own diagnostic codes and wording.  Deep
    artifact existence/containment, Role Registry membership, and the three
    artifact record contracts intentionally remain outside this function.
    """
    if contract is not None and contract_values is not None:
        raise ValueError(
            "pass either contract or contract_values, not both")
    contract_values = _resolved_contract_values(
        contract if contract is not None else contract_values)
    slot_fields = contract_values["slot_fields"]
    applicability_fields = contract_values["applicability_fields"]
    artifact_binding_fields = contract_values["artifact_binding_fields"]
    capability_scale_fields = contract_values["capability_scale_fields"]
    pass_authority_fields = contract_values["pass_authority_fields"]
    configured_state = contract_values["configured_state"]
    inactive_state = contract_values["inactive_state"]
    applicability_states = frozenset((configured_state, inactive_state))
    semantic_acceptance_scope = contract_values[
        "semantic_acceptance_scope"]
    issues = []
    document = _envelope_mapping(document, slot_fields, (), issues)
    if type(document.get("schema_version")) is not int or \
            document.get("schema_version") != \
            contract_values["slot_schema_version"]:
        issues.append(_issue("schema_version"))

    applicability = _envelope_mapping(
        document.get("applicability"), applicability_fields,
        ("applicability",), issues)
    artifacts = _envelope_mapping(
        document.get("artifact_bindings"), artifact_binding_fields,
        ("artifact_bindings",), issues)
    authority = _envelope_mapping(
        document.get("pass_authority"), pass_authority_fields,
        ("pass_authority",), issues)
    scale_rows = document.get("capability_scale")
    if not isinstance(scale_rows, list):
        issues.append(_issue("scale_list", ("capability_scale",)))
        scale_rows = []

    mode = applicability.get("state")
    raw_reason = applicability.get("reason")
    reason = raw_reason.strip() if isinstance(raw_reason, str) else raw_reason
    normalized = {
        "mode": mode if mode in applicability_states else None,
        "reason": reason,
        "artifact_bindings": {},
        "scale": [],
        "authority": {},
    }
    if mode not in applicability_states:
        issues.append(_issue("applicability_state",
                             ("applicability", "state")))
        return normalized, tuple(issues)

    if mode == inactive_state:
        if not isinstance(raw_reason, str) or not raw_reason.strip():
            issues.append(_issue("inactive_reason",
                                 ("applicability", "reason")))
        nonnull_artifacts = tuple(
            field for field in artifact_binding_fields
            if artifacts.get(field) is not None)
        if nonnull_artifacts:
            issues.append(_issue(
                "inactive_artifacts", ("artifact_bindings",),
                fields=nonnull_artifacts))
        if scale_rows:
            issues.append(_issue("inactive_scale", ("capability_scale",)))
        nonnull_authority = tuple(
            field for field in pass_authority_fields
            if authority.get(field) is not None)
        if nonnull_authority:
            issues.append(_issue(
                "inactive_authority", ("pass_authority",),
                fields=nonnull_authority))
        return normalized, tuple(issues)

    if raw_reason is not None:
        issues.append(_issue("configured_reason",
                             ("applicability", "reason")))

    artifact_identities = []
    for field in artifact_binding_fields:
        value = artifacts.get(field)
        if (not isinstance(value, str) or not value.strip() or
                not value.lower().endswith(".yaml")):
            issues.append(_issue(
                "configured_artifact_path", ("artifact_bindings", field),
                value=value))
            continue
        normalized_value = value.strip()
        normalized["artifact_bindings"][field] = normalized_value
        artifact_identities.append(normalized_value)
    if len(artifact_identities) != len(set(artifact_identities)):
        issues.append(_issue("artifact_bindings_distinct",
                             ("artifact_bindings",)))

    if not scale_rows:
        issues.append(_issue("configured_scale_empty",
                             ("capability_scale",)))
    values = set()
    target_eligible = False
    for index, raw in enumerate(scale_rows):
        row_path = ("capability_scale", index)
        row = _envelope_mapping(
            raw, capability_scale_fields, row_path, issues)
        rank = row.get("rank")
        if type(rank) is not int or rank < 0:
            issues.append(_issue("scale_rank_type", row_path + ("rank",),
                                 index=index, value=rank))
            normalized_rank = None
        elif rank != index:
            issues.append(_issue("scale_rank_position",
                                 row_path + ("rank",), index=index,
                                 value=rank))
            normalized_rank = rank
        else:
            normalized_rank = rank

        raw_value = row.get("value")
        if not isinstance(raw_value, str):
            issues.append(_issue("scale_value_type",
                                 row_path + ("value",), value=raw_value))
            value = ""
        elif not raw_value.strip():
            issues.append(_issue("scale_value_empty",
                                 row_path + ("value",), value=raw_value))
            value = ""
        else:
            value = raw_value.strip()
        if value in values and value:
            issues.append(_issue("scale_value_duplicate",
                                 row_path + ("value",), value=value))
        elif value:
            values.add(value)

        raw_predicate = row.get("predicate")
        if not isinstance(raw_predicate, str):
            issues.append(_issue("scale_predicate_type",
                                 row_path + ("predicate",),
                                 value=raw_predicate))
            predicate = ""
        elif not raw_predicate.strip():
            issues.append(_issue("scale_predicate_empty",
                                 row_path + ("predicate",),
                                 value=raw_predicate))
            predicate = ""
        else:
            predicate = raw_predicate.strip()

        eligible = row.get("target_eligible")
        if type(eligible) is not bool:
            issues.append(_issue("scale_target_eligible_type",
                                 row_path + ("target_eligible",),
                                 value=eligible))
            normalized_eligible = False
        else:
            normalized_eligible = eligible
        target_eligible = target_eligible or eligible is True
        normalized["scale"].append({
            "rank": normalized_rank,
            "value": value,
            "predicate": predicate,
            "target_eligible": normalized_eligible,
        })
    if scale_rows and not target_eligible:
        issues.append(_issue("configured_target_eligible",
                             ("capability_scale",)))

    raw_role = authority.get("role_id")
    if not isinstance(raw_role, str):
        issues.append(_issue("authority_role_type",
                             ("pass_authority", "role_id"),
                             value=raw_role))
        role = ""
    elif not raw_role.strip():
        issues.append(_issue("authority_role_empty",
                             ("pass_authority", "role_id"),
                             value=raw_role))
        role = ""
    else:
        role = raw_role.strip()
    raw_decision = authority.get("decision_scope_id")
    if not isinstance(raw_decision, str):
        issues.append(_issue("authority_decision_type",
                             ("pass_authority", "decision_scope_id"),
                             value=raw_decision))
        decision = ""
    elif not raw_decision.strip():
        issues.append(_issue("authority_decision_empty",
                             ("pass_authority", "decision_scope_id"),
                             value=raw_decision))
        decision = ""
    else:
        decision = raw_decision.strip()
    if decision != semantic_acceptance_scope:
        issues.append(_issue("authority_decision_scope",
                             ("pass_authority", "decision_scope_id"),
                             value=decision))
    normalized["authority"] = {
        "role_id": role,
        "decision_scope_id": decision,
    }
    return normalized, tuple(issues)


def receipt_binding_differences(
        receipt, expected_binding, *, fields=None, contract_values=None):
    """Return exact field-level differences for one currentness comparison."""
    if not isinstance(receipt, dict):
        raise TypeError("receipt must be a mapping")
    if not isinstance(expected_binding, dict):
        raise TypeError("expected_binding must be a mapping")
    values = _resolved_contract_values(contract_values)
    selected = tuple(fields) if fields is not None else \
        values["receipt_binding_fields"]
    return tuple({
        "field": field,
        "missing": field not in receipt,
        "actual": receipt.get(field),
        "expected": expected_binding.get(field),
    } for field in selected
        if field not in receipt or
        receipt.get(field) != expected_binding.get(field))


def receipt_path_currentness_issues(
        receipt, applicability, *, contract_values=None):
    """Validate applicability-dependent path/SHA presence and hash shape."""
    if not isinstance(receipt, dict):
        raise TypeError("receipt must be a mapping")
    issues = []
    values = _resolved_contract_values(contract_values)
    for path_field, sha_field, requirement in values["path_sha_bindings"]:
        required = (requirement == "always" or
                    applicability == values["configured_state"])
        path_value = receipt.get(path_field)
        sha_value = receipt.get(sha_field)
        if required:
            if not nonempty_string(path_value):
                issues.append({"code": "required_path", "path_field":
                               path_field, "sha256_field": sha_field})
            if not isinstance(sha_value, str) or not _SHA256_RE.fullmatch(
                    sha_value):
                issues.append({"code": "required_sha256", "path_field":
                               path_field, "sha256_field": sha_field})
        elif path_field not in receipt or sha_field not in receipt:
            issues.append({"code": "inactive_pair_missing", "path_field":
                           path_field, "sha256_field": sha_field})
        elif path_value is not None or sha_value is not None:
            issues.append({"code": "inactive_pair_nonnull", "path_field":
                           path_field, "sha256_field": sha_field})
    return tuple(issues)


def receipt_binding_shape_issues(binding, *, contract_values=None):
    """Return closed-field and path/SHA issues for a producer binding."""
    if not isinstance(binding, dict):
        return ({"code": "binding_type"},)
    issues = []
    values = _resolved_contract_values(contract_values)
    binding_fields = values["receipt_binding_fields"]
    missing = tuple(
        field for field in binding_fields
        if field not in binding)
    extra = tuple(sorted(set(binding) - set(binding_fields)))
    if missing:
        issues.append({"code": "binding_fields_missing", "fields": missing})
    if extra:
        issues.append({"code": "binding_fields_extra", "fields": extra})
    issues.extend(receipt_path_currentness_issues(
        binding, binding.get("corpus_plan_applicability"),
        contract_values=values))
    return tuple(issues)


def derive_close_requirement(
        selected_route_ids, manifest, affected_paths, *,
        contract_values=None):
    """Project the existing route/manifest applicability triggers."""
    routes = selected_route_ids if isinstance(selected_route_ids, list) else []
    manifest = manifest if isinstance(manifest, list) else []
    triggers = []
    values = _resolved_contract_values(contract_values)
    route_trigger = values["close_route_trigger"]
    manifest_trigger = values["close_manifest_trigger"]
    if route_trigger in routes:
        triggers.append(route_trigger)
    if set(affected_paths).intersection(manifest):
        triggers.append(manifest_trigger)
    triggers = sorted(set(triggers))
    return bool(triggers), triggers


def close_trigger_issues(required, triggers, *, contract_values=None):
    """Return neutral issues for a persisted close-trigger projection."""
    values = _resolved_contract_values(contract_values)
    close_triggers = frozenset((
        values["close_route_trigger"], values["close_manifest_trigger"]))
    issues = []
    if (not isinstance(triggers, list) or
            any(not nonempty_string(value) for value in triggers)):
        issues.append({"code": "trigger_list"})
        normalized = []
    else:
        normalized = triggers
        if normalized != sorted(set(normalized)):
            issues.append({"code": "trigger_order"})
        unsupported = tuple(sorted(set(normalized) - close_triggers))
        if unsupported:
            issues.append({"code": "trigger_unsupported",
                           "values": unsupported})
    if required is False and normalized:
        issues.append({"code": "inactive_triggers"})
    elif required is True and not normalized:
        issues.append({"code": "required_trigger_missing"})
    return tuple(issues)


__all__ = [
    'APPLICABILITY_STATES',
    'ARTIFACT_BINDING_FIELDS',
    'ARTIFACT_FIELD_ROLES',
    'ARTIFACT_ROLES',
    'CLOSE_ROUTE_TRIGGER',
    'CONFIGURED_STATE',
    'CORPUS_PLANNING_CONTRACT_PATH',
    'INACTIVE_STATE',
    'PASS_RECEIPT_BINDING_FIELDS',
    'SEMANTIC_ACCEPTANCE_SCOPE',
    'SLOT_NAME',
    'artifact_contract',
    'close_trigger_issues',
    'current_corpus_planning_contract_values',
    'derive_close_requirement',
    'receipt_binding_differences',
    'receipt_binding_shape_issues',
    'receipt_path_currentness_issues',
    'validate_corpus_planning_envelope',
]
