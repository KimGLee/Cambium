#!/usr/bin/env python3
"""Validate one selected Profile's explicit corpus-planning artifacts.

The checker is deliberately syntactic and referential.  It validates stable
IDs, declared paths, explicit relationships, and canonical runtime handoffs;
it never infers a capability, dependency, gap, or acceptance result from
prose, links, or semantic similarity.
"""

import json
import os
import re
import sys

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.canon as queue_canon
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.planning.corpus_planning_contract as corpus_planning_contract
import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.governance.profile.profile_admission as profile_admission
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.execution.task_runtime.queue_runtime.coverage import (
    promoted_coverage_projection,
)
import Tools.knowledge.metadata.vocabulary_contract as vocabulary_contract
from Tools.platform.common.primitives import catalog_receipt


TOOL = queue_canon.CORPUS_PLAN_TOOL
TOOL_VERSION = queue_canon.CORPUS_PLAN_TOOL_VERSION
# The Gate ID and the `Check` cell K00/12 registers for it; every receipt
# this tool offers as gate evidence carries both verbatim.
GATE_ID = "corpus-plan-structure"
GATE_CHECK = "corpus_plan"

SCOPE_SLOT_NAME = profile_contract.PROFILE_SCOPE_SLOT
ROLE_SLOT_NAME = profile_contract.ROLE_REGISTRY_SLOT
STATE_PATHS = (
    queue_runtime.COVERAGE_PATH,
    queue_runtime.QUEUE_PATH,
    queue_runtime.PROGRESS_PATH,
)

SEMANTIC_ACCEPTANCE_TOOL = "record_corpus_acceptance"
SEMANTIC_ACCEPTANCE_TOOL_VERSION = "1.0.0"
SEMANTIC_ACCEPTANCE_CHECK = "corpus_plan_semantic_acceptance"
GATE_RECEIPT_TYPE_ID = "corpus-plan-gate-receipt-v1"
DIAGNOSTIC_RECEIPT_TYPE_ID = "corpus-plan-diagnostic-receipt-v1"

_CONTRACT_VALUES_KEY = "_corpus_planning_contract_values"
_CONTRACT_SNAPSHOT_KEY = "_corpus_planning_contract_snapshot"


def _load_current_contract_context(root, result):
    """Project K02 values from the same evaluation that admitted the Profile."""
    relative = corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH
    try:
        view = result.get("_authorized_profile_view") or {}
        evaluation = view.get("_evaluation")
        if evaluation is None or not evaluation.authorized:
            raise ValueError("K02 consumption requires the authorized Profile evaluation")
        snapshot = evaluation.normative_snapshots[relative]
        values = corpus_planning_contract.\
            current_corpus_planning_contract_values(
                root, snapshots=evaluation.normative_snapshots)
    except (OSError, UnicodeError, TypeError, ValueError, KeyError,
            kblib.YamlSubsetError) as exc:
        _add_error(
            result, "corpus_planning_contract", relative,
            "cannot bind the current K02 Corpus Planning contract: %s" %
            exc)
        return None
    result[_CONTRACT_VALUES_KEY] = values
    result[_CONTRACT_SNAPSHOT_KEY] = snapshot
    return values


def _result_contract_values(result, contract_values=None):
    """Resolve explicit values, retaining a compatibility-only fallback."""
    if contract_values is not None:
        return contract_values
    if isinstance(result, dict):
        values = result.get(_CONTRACT_VALUES_KEY)
        if isinstance(values, dict):
            return values
    # Hand-built legacy/unit results do not carry an owner snapshot.  Their
    # compatibility path intentionally uses the contract shipped with this
    # Tool rather than pretending an arbitrary fixture root is authoritative.
    return corpus_planning_contract.current_corpus_planning_contract_values()


def _artifact_roles(contract_values):
    return tuple(
        contract_values["artifact_roles"][field]
        for field in contract_values["artifact_binding_fields"])


def current_gate_receipt_errors(record, *, root=None):
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=GATE_RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=GATE_CHECK)
    if isinstance(record, dict) and record.get("gate_id") != GATE_ID:
        errors.append("gate_id must identify corpus-plan-structure")
    return errors


def current_diagnostic_receipt_errors(record, *, root=None):
    check = record.get("check") if isinstance(record, dict) else None
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=DIAGNOSTIC_RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION,
        checks=check if isinstance(check, str) and check != GATE_CHECK else ())
SEMANTIC_ACCEPTANCE_PLAN_PREFIX = \
    runtime_paths.CORPUS_PLAN_ACCEPTANCE_DELTA_ROOT
SEMANTIC_ACCEPTANCE_DECISIONS = {"accepted", "rejected"}
SEMANTIC_ACCEPTANCE_PLAN_FIELDS = {
    "schema_version", "acceptance_id", "authority_role_id",
    "decision_scope_id", "decisions",
}
SEMANTIC_ACCEPTANCE_DECISION_FIELDS = {
    "capability_id", "decision", "rationale",
}

# A successful receipt is a reusable assertion only while every byte named by
# this closed binding remains current.  The planning artifacts live outside
# ``.cambium`` and are therefore also covered by the repository snapshot; the
# individual path/SHA pairs make the exact profile interface independently
# inspectable.  Runtime state is excluded from the repository snapshot and is
# consequently bound by its three canonical fingerprints.
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _add_error(result, check, target, details):
    result["errors"].append({
        "check": check,
        "target": target,
        "details": details,
    })


def _display_error(error):
    return "%s (%s): %s" % (
        error["check"], error["target"], error["details"])


def _relative(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _resolve_path(root, raw, label, result, *, must_exist=True,
                  markdown=False, yaml_file=False, directory=False):
    if not isinstance(raw, str):
        _add_error(result, "path", label, "must be a string path")
        return None
    value = raw
    if not value or value == "None":
        _add_error(result, "path", label,
                   "must be an explicit repository-relative path")
        return None
    if "\\" in value:
        _add_error(result, "path", label,
                   "must use forward slashes")
        return None
    if markdown and not value.lower().endswith(".md"):
        _add_error(result, "path", label, "must end with .md")
        return None
    if yaml_file and not value.lower().endswith(".yaml"):
        _add_error(result, "path", label, "must end with .yaml")
        return None
    try:
        path = kblib.repository_path(
            root, value, must_exist=must_exist, reject_symlink=True)
    except ValueError as exc:
        _add_error(result, "path", label, str(exc))
        return None
    if must_exist:
        if directory and not os.path.isdir(path):
            _add_error(result, "path", label, "must identify a directory")
            return None
        if not directory and not os.path.isfile(path):
            _add_error(result, "path", label, "must identify a regular file")
            return None
    return {"value": value, "path": path}


def _closed_mapping(value, expected, label, result):
    """Require one exact mapping field set and return a safe mapping."""
    if not isinstance(value, dict):
        _add_error(result, "yaml_contract", label, "must be a mapping")
        return {}
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        _add_error(result, "yaml_contract", label,
                   "missing field(s): %s" % ", ".join(missing))
    if extra:
        _add_error(result, "yaml_contract", label,
                   "unsupported field(s): %s" % ", ".join(extra))
    return value


def _schema_document(binding, expected_fields, label, result):
    try:
        snapshot = binding.get("_snapshot")
        if not isinstance(snapshot, kblib.RepositoryFileSnapshot):
            raise ValueError(
                "artifact has no immutable validation snapshot")
        document = kblib.parse_yaml_subset(snapshot.read_text())
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        _add_error(result, "yaml_parse", label, str(exc))
        return {}
    document = _closed_mapping(document, expected_fields, label, result)
    version = document.get("schema_version")
    if type(version) is not int or version != 1:
        _add_error(result, "yaml_contract", label,
                   "schema_version must be integer 1")
    return document


def _string(value, label, result, *, allow_empty=False):
    if not isinstance(value, str):
        _add_error(result, "yaml_type", label, "must be a string")
        return ""
    if not allow_empty and not value.strip():
        _add_error(result, "yaml_value", label, "must be non-empty")
    if "TODO(profile)" in value:
        _add_error(result, "template_sentinel", label,
                   "must replace TODO(profile) before validation")
    return value.strip()


def _string_list(value, label, result, *, allow_empty=True):
    if not isinstance(value, list):
        _add_error(result, "yaml_type", label, "must be a list")
        return []
    values = []
    for index, item in enumerate(value):
        parsed = _string(item, "%s[%d]" % (label, index), result)
        if parsed:
            values.append(parsed)
    if not allow_empty and not values:
        _add_error(result, "yaml_value", label,
                   "must contain at least one value")
    duplicates = sorted({item for item in values if values.count(item) > 1})
    if duplicates:
        _add_error(result, "yaml_value", label,
                   "repeats value(s): %s" % ", ".join(duplicates))
    return values


def _reject_runtime_path(resolved, label, result):
    """Keep semantic planning inputs outside the runtime namespace."""
    if not resolved:
        return
    value = resolved["value"].rstrip("/")
    if (value == runtime_paths.RUNTIME_ROOT or
            value.startswith(runtime_paths.RUNTIME_ROOT + "/")):
        _add_error(
            result, "planning_namespace", label,
            "semantic planning paths may not be inside %s/" %
            runtime_paths.RUNTIME_ROOT,
        )


def _valid_id(value, label, result):
    if not ID_RE.fullmatch(value or ""):
        _add_error(result, "stable_id", label,
                   "must match %s" % ID_RE.pattern)
        return False
    return True


def _resolve_manifest(root, profile, result):
    selected_from_progress = None
    if profile is None:
        progress_path = os.path.join(root, queue_runtime.PROGRESS_PATH)
        try:
            progress = kblib.load_yaml_file(progress_path)
        except (OSError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            _add_error(
                result, "profile_selection", queue_runtime.PROGRESS_PATH,
                "--profile was omitted and selected Profile could not be read: %s" %
                exc,
            )
            return None, None
        contract = progress.get("contract")
        if not isinstance(contract, dict):
            _add_error(result, "profile_selection", queue_runtime.PROGRESS_PATH,
                       "contract must be a mapping")
            return None, None
        profile = contract.get("selected_profile_manifest")
        selected_from_progress = profile
    if not isinstance(profile, str) or not profile.strip():
        _add_error(result, "profile_selection", str(profile),
                   "selected Profile must be a repository-relative path")
        return None, selected_from_progress
    profile = profile.strip()
    try:
        capability = kblib.inherited_path_capability(profile, "snapshot")
        if capability is not None:
            if not capability["exists"]:
                raise ValueError("path does not exist: %s" % profile)
            if capability["kind"] == "directory":
                kblib.repository_tree_snapshot(root, profile)
                profile = profile.rstrip("/") + "/" + profile_layout_contract.PROFILE_MANIFEST_NAME
            elif capability["kind"] == "file":
                if os.path.basename(profile) != profile_layout_contract.PROFILE_MANIFEST_NAME:
                    raise ValueError(
                        "must identify a structured Profile manifest")
                kblib.repository_parent_tree_snapshot(root, profile)
            else:
                raise ValueError(
                    "must identify a Profile directory or structured manifest")
            candidate = os.path.join(root, *profile.split("/"))
            if not kblib.retained_tree_contains(profile):
                raise ValueError("Profile manifest is absent from the "
                                 "retained package")
            return candidate, selected_from_progress
        candidate = kblib.repository_path(root, profile, must_exist=True,
                                          reject_symlink=True)
        if os.path.isdir(candidate):
            profile = profile.rstrip("/") + "/" + profile_layout_contract.PROFILE_MANIFEST_NAME
            candidate = kblib.repository_path(
                root, profile, must_exist=True, reject_symlink=True)
    except ValueError as exc:
        _add_error(result, "profile_selection", profile, str(exc))
        return None, selected_from_progress
    if not os.path.isfile(candidate) or os.path.basename(profile) != profile_layout_contract.PROFILE_MANIFEST_NAME:
        _add_error(result, "profile_selection", profile,
                   "must identify a structured Profile manifest")
        return None, selected_from_progress
    return candidate, selected_from_progress


def _authorized_profile_view(root, profile, result,
                             authorized_profile_view=None):
    """Resolve selection, then run one complete typed ``profile-load``."""
    manifest_path, selected_from_progress = _resolve_manifest(
        root, profile, result)
    if manifest_path is None:
        return None, None, selected_from_progress
    manifest_relative = _relative(root, manifest_path)
    if authorized_profile_view is None and selected_from_progress is None:
        admission, errors = profile_admission.admit_profile(
            root, os.path.dirname(manifest_relative))
        if admission is None:
            view = None
        else:
            evaluation = admission.evaluation
            view = {
                "selected_profile_manifest": admission.manifest_repo_path,
                "profile_snapshot_sha256":
                    evaluation.profile_snapshot_sha256,
                "profile_contract_fingerprint":
                    evaluation.profile_contract_fingerprint,
                "profile_load_inputs_sha256":
                    evaluation.profile_load_inputs_sha256,
                "metadata_execution_contract_fingerprint":
                    evaluation.metadata_execution_contract.
                        contract_fingerprint,
                "_contract": admission.contract,
                "_metadata_execution_contract":
                    evaluation.metadata_execution_contract,
                "_profile_snapshot": evaluation.profile_snapshot,
                "_evaluation": evaluation,
            }
    elif authorized_profile_view is None:
        view, errors = queue_runtime.profile_load_authorized_view(
            root, manifest_relative)
    else:
        view = authorized_profile_view
        errors = queue_runtime.authorized_profile_view_errors(
            root, manifest_relative, view)
    for error in errors:
        _add_error(result, "profile_load", manifest_relative, error)
    if view is None:
        return None, None, selected_from_progress
    if view.get("selected_profile_manifest") != manifest_relative:
        _add_error(
            result, "profile_load", manifest_relative,
            "authorized view selects %r" %
            view.get("selected_profile_manifest"))
        return None, None, selected_from_progress
    return manifest_path, view, selected_from_progress


def _profile_view_currency_errors(root, profile_view):
    return queue_runtime.profile_load_authorized_view_currency_errors(
        root, profile_view)


def _typed_slot_document(profile_view, slot_name, result):
    """Project a named slot from the already-authorized structured model."""
    contract = profile_view.get("_contract") if isinstance(profile_view, dict) else None
    if not isinstance(contract, profile_contract.ProfileContract) or not contract.valid:
        _add_error(result, "profile_binding",
                   result.get("profile_manifest") or "<unresolved>",
                   "Profile slot access requires the formal authorized model")
        return None
    document = contract.slot_document(slot_name)
    if document is None:
        _add_error(result, "profile_binding", contract.manifest_repo_path,
                   "authorized model has no %s slot" % slot_name)
    return document


def _role_ids(root, profile_view, result):
    """Use the role identities already linked by the Profile owner."""
    contract = profile_view.get("_contract")
    if not isinstance(contract, profile_contract.ProfileContract) or not contract.valid:
        _add_error(result, "pass_authority",
                   result.get("profile_manifest") or "<unresolved>",
                   "Role Registry requires the formal authorized model")
        return set()
    return set(contract.role_ids)


def _validate_slot(
        document, target, profile_view, root, result, contract_values=None):
    contract_values = _result_contract_values(result, contract_values)
    envelope, issues = \
        corpus_planning_contract.validate_corpus_planning_envelope(
            document, contract_values=contract_values)

    if issues:
        for issue in issues:
            selector = ".".join(str(item) for item in issue.get("path", ()))
            _add_error(result, "profile_slot_contract",
                       target + ("#" + selector if selector else ""),
                       str(issue))
        return None

    mode = envelope["mode"]
    reason = envelope["reason"]
    if mode == contract_values["inactive_state"]:
        return {"mode": mode, "reason": reason, "bindings": {},
                "scale": [], "authorities": []}
    if mode != contract_values["configured_state"]:
        return None

    bindings = {}
    for field in contract_values["artifact_binding_fields"]:
        role = contract_values["artifact_roles"][field]
        raw = envelope["artifact_bindings"].get(field)
        if raw is None:
            continue
        resolved = _resolve_path(
            root, raw, "%s:artifact_bindings.%s" % (target, field), result)
        if resolved:
            _reject_runtime_path(
                resolved, "%s:artifact_bindings.%s" % (target, field), result)
            try:
                resolved["_snapshot"] = kblib.repository_file_snapshot(
                    root, resolved["value"], singly_linked=True)
            except (OSError, ValueError) as exc:
                _add_error(
                    result, "artifact_snapshot", resolved["value"],
                    "cannot bind %s to one immutable file revision: %s" %
                    (role, exc))
            bindings[role] = resolved
    if (not any(issue["code"] == "artifact_bindings_distinct"
                for issue in issues) and
            len({value["value"] for value in bindings.values()}) !=
            len(bindings)):
        _add_error(result, "artifact_bindings", target,
                   "the three artifact roles must bind distinct files")

    scale = envelope["scale"]
    role = envelope["authority"].get("role_id", "")
    decision = envelope["authority"].get("decision_scope_id")
    registry_roles = _role_ids(root, profile_view, result)
    if role and role not in registry_roles:
        _add_error(result, "pass_authority",
                   target + ":pass_authority.role_id",
                   "role %r is not registered in Role Registry" % role)
    authorities = [{"role_id": role, "decision_scope_id": decision}]
    return {"mode": mode, "reason": reason, "bindings": bindings,
            "scale": scale, "authorities": authorities}


def _validate_profile_scope(root, profile_view, result):
    target = profile_view["selected_profile_manifest"]
    document = _typed_slot_document(profile_view, SCOPE_SLOT_NAME, result)
    if document is None:
        return {"path": target, "layers": []}
    rows = document["logical_architecture"]
    layers = []
    by_id = {}
    for index, row in enumerate(rows):
        layer_id = row["layer_id"]
        row_target = "%s#slots.profile-scope.logical_architecture[%d]" % (
            target, index)
        _valid_id(layer_id, row_target, result)
        if layer_id in by_id:
            _add_error(result, "profile_scope", row_target,
                       "duplicate Stable Layer ID: %s" % layer_id)
        directories = []
        for raw in row["directories"]:
            directory = _resolve_path(
                root, raw, row_target + ".directories", result, directory=True)
            _reject_runtime_path(directory, row_target + ".directories", result)
            if directory:
                directories.append(directory)
        record = {
            "id": layer_id, "directories": directories,
            "responsibility": row["responsibility"],
        }
        layers.append(record)
        by_id.setdefault(layer_id, record)
    return {"path": target, "layers": layers}


def _validate_global_map(
        root, binding, profile_scope, result, contract_values=None):
    contract_values = _result_contract_values(result, contract_values)
    target = binding["value"]
    contract = corpus_planning_contract.artifact_contract(
        "global_map", contract_values=contract_values)
    entries_contract = contract["entries"]
    edges_contract = contract["typed_dependencies"]
    document = _schema_document(
        binding, contract["document_fields"], target, result)
    entry_rows = document.get("entries")
    edge_rows = document.get("typed_dependencies")
    if not isinstance(entry_rows, list):
        _add_error(result, "yaml_type", target + ":entries",
                   "must be a list")
        entry_rows = []
    if len(entry_rows) < entries_contract["minimum_items"]:
        _add_error(result, "global_map", target,
                   "entries must contain at least %d item(s)" %
                   entries_contract["minimum_items"])
    if not isinstance(edge_rows, list):
        _add_error(result, "yaml_type", target + ":typed_dependencies",
                   "must be a list")
        edge_rows = []

    layer_by_id = {
        row["id"]: row for row in profile_scope.get("layers", [])
    }

    entries = []
    entry_by_id = {}
    entry_paths = set()
    for index, raw_row in enumerate(entry_rows):
        row_target = "%s:entries[%d]" % (target, index)
        row = _closed_mapping(
            raw_row, entries_contract["record_fields"],
            row_target, result)
        entry_id = _string(row.get("entry_id"), row_target + ":entry_id", result)
        layer_id = _string(row.get("layer_id"), row_target + ":layer_id", result)
        _valid_id(entry_id, row_target, result)
        if ("entry_id" in entries_contract["unique_fields"] and
                entry_id in entry_by_id):
            _add_error(result, "global_map", row_target,
                       "duplicate Entry ID: %s" % entry_id)
        if layer_id not in layer_by_id:
            _add_error(result, "global_map", row_target,
                       "unknown Layer ID: %s" % layer_id)
        path = _resolve_path(root, row.get("canonical_markdown_path"), row_target,
                             result, markdown=True)
        _reject_runtime_path(path, row_target, result)
        responsibility = _string(
            row.get("single_responsibility"),
            row_target + ":single_responsibility", result)
        if (path and "canonical_markdown_path" in
                entries_contract["unique_fields"] and
                path["value"] in entry_paths):
            _add_error(result, "global_map", row_target,
                       "duplicate canonical path: %s" % path["value"])
        if path:
            entry_paths.add(path["value"])
        layer = layer_by_id.get(layer_id)
        if path and layer and layer.get("directories"):
            inside = False
            matched_directories = []
            for directory in layer["directories"]:
                try:
                    if os.path.commonpath((
                            directory["path"], path["path"])) == directory["path"]:
                        inside = True
                        matched_directories.append(directory)
                except ValueError:
                    continue
            if not inside:
                _add_error(
                    result, "global_map", row_target,
                    "canonical path is outside its declared layer directory",
                )
        else:
            matched_directories = []
        record = {"id": entry_id, "layer_id": layer_id, "path": path,
                  "responsibility": responsibility,
                  "scope_directories": matched_directories}
        entries.append(record)
        entry_by_id.setdefault(entry_id, record)

    for layer_id in sorted(layer_by_id):
        if not any(row["layer_id"] == layer_id for row in entries):
            _add_error(
                result, "profile_map_reconciliation", layer_id,
                "every Profile Scope layer requires at least one Global Map entry",
            )

    edges = []
    edge_ids = set()
    for index, raw_row in enumerate(edge_rows):
        row_target = "%s:typed_dependencies[%d]" % (target, index)
        row = _closed_mapping(
            raw_row, edges_contract["record_fields"],
            row_target, result)
        edge_id = _string(row.get("edge_id"), row_target + ":edge_id", result)
        upstream = _string(
            row.get("upstream_entry_id"), row_target + ":upstream_entry_id", result)
        downstream = _string(
            row.get("downstream_entry_id"), row_target + ":downstream_entry_id", result)
        relation = _string(
            row.get("relation_type"), row_target + ":relation_type", result)
        _valid_id(edge_id, row_target, result)
        if ("edge_id" in edges_contract["unique_fields"] and
                edge_id in edge_ids):
            _add_error(result, "global_map", row_target,
                       "duplicate Edge ID: %s" % edge_id)
        edge_ids.add(edge_id)
        if upstream not in entry_by_id:
            _add_error(result, "global_map", row_target,
                       "unknown upstream Entry ID: %s" % upstream)
        if downstream not in entry_by_id:
            _add_error(result, "global_map", row_target,
                       "unknown downstream Entry ID: %s" % downstream)
        if upstream == downstream:
            _add_error(result, "global_map", row_target,
                       "upstream and downstream Entry IDs must differ")
        if relation not in contract["relation_types"]:
            _add_error(
                result, "global_map", row_target,
                "unknown relation_type %r; expected one of %s" %
                (relation, ", ".join(sorted(contract["relation_types"]))),
            )
        edges.append({"id": edge_id, "upstream": upstream,
                      "downstream": downstream, "relation": relation})
    return {"entries": entries, "edges": edges, "path": target}


def _validate_matrix(
        root, binding, scale, global_map, result, contract_values=None):
    contract_values = _result_contract_values(result, contract_values)
    target = binding["value"]
    contract = corpus_planning_contract.artifact_contract(
        "capability_matrix", contract_values=contract_values)
    collection = contract["capabilities"]
    document = _schema_document(
        binding, contract["document_fields"], target, result)
    rows = document.get("capabilities")
    if not isinstance(rows, list):
        _add_error(result, "yaml_type", target + ":capabilities",
                   "must be a list")
        rows = []
    if len(rows) < collection["minimum_items"]:
        _add_error(result, "capability_matrix", target,
                   "must declare at least %d capability item(s)" %
                   collection["minimum_items"])
    scale_index = {row["value"]: row["rank"] for row in scale
                   if isinstance(row.get("rank"), int)}
    target_eligible = {row["value"] for row in scale
                       if row.get("target_eligible") is True}
    map_entries = {
        entry["id"]: entry for entry in global_map.get("entries", [])
    }
    capabilities = []
    by_id = {}
    for index, raw_row in enumerate(rows):
        row_target = "%s:capabilities[%d]" % (target, index)
        row = _closed_mapping(
            raw_row, collection["record_fields"],
            row_target, result)
        capability_id = _string(
            row.get("capability_id"), row_target + ":capability_id", result)
        _valid_id(capability_id, row_target, result)
        if ("capability_id" in collection["unique_fields"] and
                capability_id in by_id):
            _add_error(result, "capability_matrix", row_target,
                       "duplicate Capability ID: %s" % capability_id)
        name = _string(row.get("capability"), row_target + ":capability", result)
        priority = _string(row.get("priority"), row_target + ":priority", result)
        if priority not in vocabulary_contract.PRIORITY_VALUES:
            _add_error(
                result, "capability_matrix", row_target,
                "priority must be exactly P0, P1, or P2; found %r" % priority,
            )
        map_entry_ids = _string_list(
            row.get("map_entry_ids"), row_target + ":map_entry_ids", result,
            allow_empty="map_entry_ids" not in
                collection["nonempty_list_fields"])
        linked_entries = []
        for entry_id in map_entry_ids:
            entry = map_entries.get(entry_id)
            if entry is None:
                _add_error(result, "capability_matrix", row_target,
                           "unknown Global Map Entry ID: %s" % entry_id)
            else:
                linked_entries.append(entry)
        canonical_values = _string_list(
            row.get("canonical_markdown_paths"),
            row_target + ":canonical_markdown_paths", result,
            allow_empty="canonical_markdown_paths" not in
                collection["nonempty_list_fields"])
        canonical = []
        for raw in canonical_values:
            path = _resolve_path(root, raw, row_target + ":canonical", result,
                                 markdown=True)
            if path:
                canonical.append(path)
                covered = False
                for entry in linked_entries:
                    for directory in entry.get("scope_directories", []):
                        try:
                            if os.path.commonpath((
                                    directory["path"], path["path"])) == directory["path"]:
                                covered = True
                                break
                        except ValueError:
                            continue
                    if covered:
                        break
                if not covered:
                    _add_error(
                        result, "capability_matrix", row_target,
                        "canonical path is not covered by any linked Global "
                        "Map Entry within the same Profile Scope directory: %s" %
                        path["value"],
                    )
        current = _string(
            row.get("current_level"), row_target + ":current_level", result)
        target_level = _string(
            row.get("target_level"), row_target + ":target_level", result)
        if current not in scale_index:
            _add_error(result, "capability_matrix", row_target,
                       "unknown current level: %s" % current)
        if target_level not in scale_index:
            _add_error(result, "capability_matrix", row_target,
                       "unknown target level: %s" % target_level)
        elif ("target_requires_eligible_scale_row" in contract["rules"] and
                target_level not in target_eligible):
            _add_error(result, "capability_matrix", row_target,
                       "target level is not Target eligible: %s" % target_level)
        evidence_values = _string_list(
            row.get("evidence_paths"), row_target + ":evidence_paths", result)
        evidence = []
        for raw in evidence_values:
            path = _resolve_path(root, raw, row_target + ":evidence", result)
            if path:
                _reject_runtime_path(path, row_target + ":evidence", result)
                evidence.append(path)
        gap_ids = _string_list(
            row.get("gap_ids"), row_target + ":gap_ids", result)
        if ("rank_above_zero_requires_evidence" in contract["rules"] and
                current in scale_index and scale_index[current] > 0 and
                not evidence):
            _add_error(result, "capability_matrix", row_target,
                       "a non-lowest current level requires evidence")
        if ("below_target_requires_gap" in contract["rules"] and
                current in scale_index and target_level in scale_index and
                scale_index[current] < scale_index[target_level] and
                not gap_ids):
            _add_error(result, "capability_matrix", row_target,
                       "a capability below target requires at least one Gap ID")
        record = {
            "id": capability_id, "capability": name, "priority": priority,
            "map_entry_ids": map_entry_ids,
            "canonical_paths": canonical, "current_level": current,
            "target_level": target_level, "evidence_paths": evidence,
            "gap_ids": gap_ids,
        }
        capabilities.append(record)
        by_id.setdefault(capability_id, record)
    return {"capabilities": capabilities, "path": target}


def _validate_gap_register(
        root, binding, global_map, matrix, runtime, result,
        contract_values=None):
    contract_values = _result_contract_values(result, contract_values)
    target = binding["value"]
    contract = corpus_planning_contract.artifact_contract(
        "gap_register", contract_values=contract_values)
    collection = contract["gaps"]
    document = _schema_document(
        binding, contract["document_fields"], target, result)
    rows = document.get("gaps")
    if not isinstance(rows, list):
        _add_error(result, "yaml_type", target + ":gaps", "must be a list")
        rows = []
    capability_by_id = {
        row["id"]: row for row in matrix.get("capabilities", [])
    }
    map_entry_ids = {
        row["id"] for row in global_map.get("entries", [])
    }
    gaps = []
    by_id = {}
    promotions = []
    for index, raw_row in enumerate(rows):
        row_target = "%s:gaps[%d]" % (target, index)
        row = _closed_mapping(
            raw_row, collection["record_fields"],
            row_target, result)
        gap_id = _string(row.get("gap_id"), row_target + ":gap_id", result)
        _valid_id(gap_id, row_target, result)
        if ("gap_id" in collection["unique_fields"] and
                gap_id in by_id):
            _add_error(result, "gap_register", row_target,
                       "duplicate Gap ID: %s" % gap_id)
        statement = _string(
            row.get("gap_statement"), row_target + ":gap_statement", result)
        capability_ids = _string_list(
            row.get("capability_ids"), row_target + ":capability_ids", result,
            allow_empty="capability_ids" not in
                collection["nonempty_list_fields"])
        for capability_id in capability_ids:
            if capability_id not in capability_by_id:
                _add_error(result, "gap_register", row_target,
                           "unknown Capability ID: %s" % capability_id)
        status = _string(row.get("status"), row_target + ":status", result)
        if status not in contract["statuses"]:
            _add_error(result, "gap_register", row_target,
                       "invalid status %r; expected one of %s" %
                       (status, ", ".join(sorted(contract["statuses"]))))
        candidate_owner = row.get("candidate_owner_entry_id")
        if candidate_owner is not None:
            candidate_owner = _string(
                candidate_owner, row_target + ":candidate_owner_entry_id", result)
            if candidate_owner not in map_entry_ids:
                _add_error(result, "gap_register", row_target,
                           "unknown candidate owner Entry ID: %s" %
                           candidate_owner)
        close_condition = _string(
            row.get("close_condition"), row_target + ":close_condition", result)
        target_raw = row.get("promoted_coverage_path")
        target_path = None
        if target_raw is None:
            if ("promoted_requires_coverage_path" in
                    contract["rules"] and
                    status in contract["promoted_statuses"]):
                _add_error(result, "gap_register", row_target,
                           "%s gap requires a Promoted Coverage path" % status)
        else:
            target_raw = _string(
                target_raw, row_target + ":promoted_coverage_path", result)
            if ("unpromoted_forbids_coverage_path" in
                    contract["rules"] and
                    status in contract["unpromoted_statuses"]):
                _add_error(
                    result, "gap_register", row_target,
                    "unpromoted %s gap must use Promoted Coverage path None" %
                    status,
                )
            target_path = _resolve_path(
                root, target_raw, row_target + ":target", result,
                must_exist=(status == contract["resolved_status"]),
                markdown=True)
            _reject_runtime_path(target_path, row_target + ":target", result)
        evidence_values = _string_list(
            row.get("evidence_paths"), row_target + ":evidence_paths", result)
        evidence = []
        for raw in evidence_values:
            path = _resolve_path(root, raw, row_target + ":evidence", result)
            if path:
                _reject_runtime_path(path, row_target + ":evidence", result)
                evidence.append(path)
        if ("resolved_requires_evidence" in
                contract["rules"] and
                status == contract["resolved_status"] and
                not evidence):
            _add_error(result, "gap_register", row_target,
                       "resolved gap requires at least one retained evidence path")
        rationale = _string(
            row.get("rationale"), row_target + ":rationale", result)
        record = {
            "id": gap_id, "statement": statement,
            "capability_ids": capability_ids,
            "candidate_owner": candidate_owner,
            "target_path": target_path, "status": status,
            "close_condition": close_condition,
            "evidence_paths": evidence, "rationale": rationale,
        }
        gaps.append(record)
        by_id.setdefault(gap_id, record)

        if (status in contract["promoted_statuses"] and
                target_path):
            promotion = _reconcile_promotion(
                target_path["value"], runtime, row_target, result)
            promotion["gap_id"] = gap_id
            promotions.append(promotion)

    if ("matrix_gap_links_bidirectional" in
            corpus_planning_contract.artifact_contract(
                "capability_matrix",
                contract_values=contract_values)["rules"] and
            "matrix_gap_links_bidirectional" in
            contract["rules"]):
        for capability in matrix.get("capabilities", []):
            for gap_id in capability["gap_ids"]:
                gap = by_id.get(gap_id)
                if gap is None:
                    _add_error(
                        result, "capability_gap_link", capability["id"],
                        "references unknown Gap ID: %s" % gap_id,
                    )
                elif capability["id"] not in gap["capability_ids"]:
                    _add_error(
                        result, "capability_gap_link", capability["id"],
                        "Gap %s does not link back to this capability" %
                        gap_id,
                    )
        for gap in gaps:
            for capability_id in gap["capability_ids"]:
                capability = capability_by_id.get(capability_id)
                if capability and gap["id"] not in capability["gap_ids"]:
                    _add_error(
                        result, "capability_gap_link", gap["id"],
                        "Capability %s does not link back to this gap" %
                        capability_id,
                    )
    return {"gaps": gaps, "promotions": promotions, "path": target}


def _reconcile_promotion(path, runtime, target, result):
    outcome = {"path": path, "coverage": None, "queue_item": None}
    if runtime is None:
        _add_error(result, "promoted_gap", target,
                   "promoted gap requires initialized canonical runtime state")
        return outcome
    if runtime.get("errors"):
        _add_error(result, "promoted_gap", target,
                   "runtime is invalid, so promotion cannot be reconciled")
        return outcome
    projection = promoted_coverage_projection(runtime, path)
    coverage_rows = projection["coverage_rows"]
    if len(coverage_rows) != 1:
        _add_error(result, "promoted_gap", target,
                   "target must have exactly one Coverage row; found %d" %
                   len(coverage_rows))
        return outcome
    outcome["coverage"] = projection["coverage"]
    outcome["queue_item"] = projection["queue_item"]
    return outcome


def runtime(root, result, authorized_profile_view=None,
             authorized_active_standards_view=None):
    present = [os.path.exists(os.path.join(root, path))
               for path in STATE_PATHS]
    if not any(present):
        return None
    if not all(present):
        missing = [path for path, exists in zip(STATE_PATHS, present)
                   if not exists]
        _add_error(result, "runtime", runtime_paths.STATE_ROOT,
                   "partial runtime; missing: %s" % ", ".join(missing))
        return {"errors": ["partial runtime"], "coverage": {}, "queue": {},
                "progress": {}}
    runtime = runtime_validation.validate_runtime(
        root,
        authorized_profile_view=authorized_profile_view,
        authorized_active_standards_view=
            authorized_active_standards_view)
    for error in runtime.get("errors", []):
        _add_error(result, "runtime", runtime_paths.STATE_ROOT, error)
    return runtime


def planning_artifact_paths(result, *, contract_values=None):
    """Return every explicit path that makes a batch planning-affected.

    The selected Profile manifest is included because it owns the slot
    values: changing that file can change Profile Scope or Corpus Planning.
    In addition to the manifest and three artifacts, the affected set contains only paths
    that the validator parsed from explicit planning relations: Global Map
    entries, Matrix canonical/evidence paths, and Gap promoted/evidence paths.
    No prose, backlink, similarity, or inferred dependency expands this set.
    """
    contract_values = _result_contract_values(result, contract_values)
    paths = []

    def add(candidate):
        value = (candidate.get("value")
                 if isinstance(candidate, dict) else candidate)
        if isinstance(value, str) and value:
            paths.append(value)

    add(result.get("profile_manifest"))
    slot_path = result.get("slot_path")
    add(slot_path)
    profile_scope = result.get("profile_scope")
    if isinstance(profile_scope, dict):
        add(profile_scope.get("path"))
    slot = result.get("slot")
    if isinstance(slot, dict):
        bindings = slot.get("bindings")
        if isinstance(bindings, dict):
            for role in _artifact_roles(contract_values):
                binding = bindings.get(role)
                add(binding)

    global_map = result.get("global_map")
    if isinstance(global_map, dict):
        for entry in global_map.get("entries") or []:
            if isinstance(entry, dict):
                add(entry.get("path"))

    matrix = result.get("matrix")
    if isinstance(matrix, dict):
        for capability in matrix.get("capabilities") or []:
            if not isinstance(capability, dict):
                continue
            for field in ("canonical_paths", "evidence_paths"):
                for candidate in capability.get(field) or []:
                    add(candidate)

    gap_register = result.get("gap_register")
    if isinstance(gap_register, dict):
        for gap in gap_register.get("gaps") or []:
            if not isinstance(gap, dict):
                continue
            add(gap.get("target_path"))
            for candidate in gap.get("evidence_paths") or []:
                add(candidate)
    return tuple(dict.fromkeys(paths))


def close_requirement(runtime, item, result, *, contract_values=None):
    """Return the deterministic Corpus Planning close-gate requirement.

    R13 selection is task-level.  Manifest applicability is exact path-set
    intersection against :func:`planning_artifact_paths`; it never infers a
    relationship from content or naming.
    """
    contract_values = _result_contract_values(result, contract_values)
    contract = {}
    if isinstance(runtime, dict):
        contract = (runtime.get("progress") or {}).get("contract") or {}
    selected_routes = contract.get("selected_route_ids")
    manifest = item.get("manifest") if isinstance(item, dict) else []
    return corpus_planning_contract.derive_close_requirement(
        selected_routes, manifest,
        planning_artifact_paths(result, contract_values=contract_values),
        contract_values=contract_values)


def _profile_snapshot_file_sha256(result, relative, label):
    """Hash Profile-owned bytes from the evaluation that authorized result."""
    view = result.get("_authorized_profile_view")
    snapshot = view.get("_profile_snapshot") \
        if isinstance(view, dict) else None
    if not isinstance(snapshot, kblib.RepositoryTreeSnapshot):
        raise ValueError("Corpus Planning result has no authorized Profile "
                         "snapshot")
    try:
        return kblib.sha256_bytes(snapshot.read_bytes(relative))
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("%s is absent from the authorized Profile snapshot: "
                         "%s" % (label, exc)) from exc


def _result_currency_errors(result):
    """Rebind every mutable input consumed by one validation result."""
    root = result.get("root")
    view = result.get("_authorized_profile_view")
    if not isinstance(root, str) or not isinstance(view, dict):
        return ["Corpus Planning result has no authorized Profile view"]
    errors = list(_profile_view_currency_errors(root, view))
    contract_snapshot = result.get(_CONTRACT_SNAPSHOT_KEY)
    has_contract_context = _CONTRACT_VALUES_KEY in result or \
        _CONTRACT_SNAPSHOT_KEY in result
    if has_contract_context and not isinstance(
            contract_snapshot, kblib.RepositoryFileSnapshot):
        errors.append("Corpus Planning result has no immutable K02 contract "
                      "snapshot")
    elif has_contract_context:
        try:
            current_contract = kblib.repository_file_snapshot(
                root,
                corpus_planning_contract.CORPUS_PLANNING_CONTRACT_PATH,
                singly_linked=True)
        except (OSError, ValueError) as exc:
            errors.append("cannot re-bind the K02 Corpus Planning contract: "
                          "%s" % exc)
        else:
            if current_contract.sha256 != contract_snapshot.sha256:
                errors.append("K02 Corpus Planning contract changed after "
                              "validation")

    runtime = result.get("runtime")
    if isinstance(runtime, dict):
        active_standards_view = runtime.get(
            "_active_standards_authorized_view")
        if isinstance(active_standards_view, dict):
            errors.extend(queue_runtime.active_standards_view_currency_errors(
                root, active_standards_view))
        for relative, field in (
                (queue_runtime.COVERAGE_PATH, "coverage_sha256"),
                (queue_runtime.QUEUE_PATH, "queue_sha256"),
                (queue_runtime.PROGRESS_PATH, "progress_sha256")):
            expected = runtime.get(field)
            try:
                current = kblib.repository_file_snapshot(
                    root, relative, singly_linked=True).sha256
            except (OSError, ValueError) as exc:
                errors.append("cannot re-bind %s: %s" % (relative, exc))
                continue
            if current != expected:
                errors.append("%s changed after Corpus Planning validation" %
                              relative)

    bindings = ((result.get("slot") or {}).get("bindings") or {})
    contract_values = _result_contract_values(result)
    for role in _artifact_roles(contract_values):
        artifact = bindings.get(role)
        if not isinstance(artifact, dict):
            continue
        snapshot = artifact.get("_snapshot")
        relative = artifact.get("value")
        if not isinstance(snapshot, kblib.RepositoryFileSnapshot):
            errors.append("%s has no immutable validation snapshot" % role)
            continue
        try:
            current = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
        except (OSError, ValueError) as exc:
            errors.append("cannot re-bind %s: %s" % (role, exc))
            continue
        if current.sha256 != snapshot.sha256:
            errors.append("%s changed after Corpus Planning validation" % role)
    return errors


def receipt_binding(result, *, repository_snapshot_sha256=None,
                    progress_ledger_sha256=None, contract_values=None):
    """Return the exact freshness binding for one successful validation.

    ``progress_ledger_sha256`` is an explicit terminal-only override.  A
    Terminal Proof is frozen in ``completion-candidate`` and remains
    recheckable after the sole transition to ``complete``; the proof checker
    supplies that receipt-bound before-image while requiring the transition's
    after-image to equal current Progress bytes.
    """
    contract_values = _result_contract_values(result, contract_values)
    if result.get("errors"):
        raise ValueError("cannot bind a failed Corpus Planning validation")
    currency = _result_currency_errors(result)
    if currency:
        raise ValueError("Corpus Planning validation inputs are stale: %s" %
                         "; ".join(currency))
    root = result.get("root")
    if not isinstance(root, str) or not os.path.isdir(root):
        raise ValueError("Corpus Planning result has no repository root")
    if repository_snapshot_sha256 is None:
        repository_snapshot_sha256 = kblib.repository_snapshot_sha256(root)
    if (not isinstance(repository_snapshot_sha256, str) or
            not SHA256_RE.fullmatch(repository_snapshot_sha256)):
        raise ValueError("repository snapshot must be sha256:<64 lowercase hex>")

    runtime = result.get("runtime")
    queue = runtime.get("queue") if isinstance(runtime, dict) else {}
    if not isinstance(queue, dict):
        queue = {}
    selected_profile = result.get("profile_manifest")
    if queue and queue.get("selected_profile_manifest") != selected_profile:
        raise ValueError(
            "runtime selected Profile does not match validated Profile")

    binding = {
        "task_id": queue.get("task_id") if queue else None,
        "queue_revision": queue.get("queue_revision") if queue else None,
        "queue_state_revision": queue.get("state_revision") if queue else None,
        "selected_profile_manifest": selected_profile,
        "selected_profile_manifest_sha256":
            _profile_snapshot_file_sha256(
                result, selected_profile, "selected Profile manifest"),
        "profile_snapshot_sha256": result[
            "_authorized_profile_view"]["profile_snapshot_sha256"],
        "profile_contract_fingerprint": result[
            "_authorized_profile_view"]["profile_contract_fingerprint"],
        "profile_load_inputs_sha256": result[
            "_authorized_profile_view"]["profile_load_inputs_sha256"],
        # These existing evidence fields name the real source container.
        # Embedded slot identity is carried by the typed contract fingerprint;
        # no consumer reads this path as an independent slot document.
        "corpus_planning_slot_path": result.get("slot_path"),
        "corpus_planning_slot_sha256":
            _profile_snapshot_file_sha256(
                result, result.get("slot_path"), "Corpus Planning slot"),
        "profile_scope_path": None,
        "profile_scope_sha256": None,
        "global_map_path": None,
        "global_map_sha256": None,
        "capability_matrix_path": None,
        "capability_matrix_sha256": None,
        "gap_register_path": None,
        "gap_register_sha256": None,
        "corpus_plan_applicability": result.get("applicability"),
        "coverage_ledger_sha256": (
            runtime.get("coverage_sha256") if isinstance(runtime, dict)
            else None),
        "required_queue_sha256": (
            runtime.get("queue_sha256") if isinstance(runtime, dict)
            else None),
        "progress_ledger_sha256": (
            runtime.get("progress_sha256") if isinstance(runtime, dict)
            else None),
        "repository_snapshot_sha256": repository_snapshot_sha256,
    }
    if progress_ledger_sha256 is not None:
        if (not isinstance(progress_ledger_sha256, str) or
                not SHA256_RE.fullmatch(progress_ledger_sha256)):
            raise ValueError(
                "terminal Progress binding must be sha256:<64 lowercase hex>")
        binding["progress_ledger_sha256"] = progress_ledger_sha256

    if result.get("applicability") == \
            contract_values["configured_state"]:
        profile_scope = result.get("profile_scope") or {}
        profile_scope_path = profile_scope.get("path")
        if not isinstance(profile_scope_path, str) or not profile_scope_path:
            raise ValueError("configured plan has no Profile Scope binding")
        binding["profile_scope_path"] = profile_scope_path
        binding["profile_scope_sha256"] = _profile_snapshot_file_sha256(
            result, profile_scope_path, "Profile Scope")
        slot = result.get("slot") or {}
        bindings = slot.get("bindings") or {}
        fields = {
            "Global Map": ("global_map_path", "global_map_sha256"),
            "Capability Matrix": (
                "capability_matrix_path", "capability_matrix_sha256"),
            "Gap Register": ("gap_register_path", "gap_register_sha256"),
        }
        for role in _artifact_roles(contract_values):
            artifact = bindings.get(role)
            if not isinstance(artifact, dict):
                raise ValueError("configured plan has no %s binding" % role)
            path_field, sha_field = fields[role]
            binding[path_field] = artifact.get("value")
            snapshot = artifact.get("_snapshot")
            if not isinstance(snapshot, kblib.RepositoryFileSnapshot):
                raise ValueError("configured plan has no immutable %s "
                                 "snapshot" % role)
            binding[sha_field] = snapshot.sha256
    elif result.get("applicability") != \
            contract_values["inactive_state"]:
        raise ValueError("Corpus Planning applicability is not resolved")
    binding_issues = \
        corpus_planning_contract.receipt_binding_shape_issues(
            binding, contract_values=contract_values)
    if binding_issues:
        raise ValueError(
            "Corpus Planning receipt binding violates the K02 contract: %r"
            % (binding_issues,))
    final_currency = _result_currency_errors(result)
    if final_currency:
        raise ValueError(
            "Corpus Planning validation inputs changed while receipt binding "
            "was assembled: %s" % "; ".join(final_currency))
    return binding


def make_pass_receipt(result, *, repository_snapshot_sha256=None,
                      progress_ledger_sha256=None, seq=1,
                      contract_values=None):
    """Build one reusable pass receipt bound to exact current bytes."""
    binding = receipt_binding(
        result,
        repository_snapshot_sha256=repository_snapshot_sha256,
        progress_ledger_sha256=progress_ledger_sha256,
        contract_values=contract_values,
    )
    details = (
        "applicability=%s; layers=%d; entries=%d; capabilities=%d; "
        "gaps=%d" % (
            result["applicability"],
            len(result.get("profile_scope", {}).get("layers", [])),
            len(result["global_map"].get("entries", [])),
            len(result["matrix"].get("capabilities", [])),
            len(result["gap_register"].get("gaps", [])),
        )
    )
    # The runtime identity is bound first so a Gate consumer can compare it;
    # the explicit artifact binding still owns every field it declares.
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, GATE_CHECK,
        result.get("profile_manifest") or "<unresolved>", "pass",
        details, seq, receipt_type_id=GATE_RECEIPT_TYPE_ID,
        root=result.get("root"))
    receipt["gate_id"] = GATE_ID
    receipt.update(binding)
    return receipt


def current_freshness_binding(root, selected_profile_manifest, *, task_id,
                              queue_revision, queue_state_revision,
                              coverage_ledger_sha256,
                              required_queue_sha256,
                              progress_ledger_sha256,
                              repository_snapshot_sha256,
                              terminal_progress_ledger_sha256=None,
                              authorized_profile_view=None):
    """Recompute the current bytes named by a prior pass receipt.

    Freshness consumption does not repeat the substantive map/matrix/gap
    decision.  It re-resolves the selected Profile and slot contract, hashes
    those exact current files, and binds current runtime/snapshot bytes.  The
    persisted receipt proves that this unchanged byte set previously passed
    the full validator. ``progress_ledger_sha256`` is always the live Progress
    currency input. ``terminal_progress_ledger_sha256`` may separately retain
    the receipt-bound completion-candidate before-image across the one legal
    transition to ``complete``; it never weakens live currency checking.
    """
    root = os.path.realpath(os.path.abspath(root))
    result = {
        "root": root,
        "profile_manifest": None,
        "slot_path": None,
        "applicability": None,
        "slot": None,
        "profile_scope": {"path": None, "layers": []},
        "runtime": None,
        "errors": [],
    }
    manifest_path, profile_view, _ = _authorized_profile_view(
        root, selected_profile_manifest, result,
        authorized_profile_view=authorized_profile_view)
    if manifest_path is None or profile_view is None:
        raise ValueError("; ".join(
            _display_error(error) for error in result["errors"]))
    result["_authorized_profile_view"] = profile_view
    result["profile_manifest"] = _relative(root, manifest_path)
    contract_values = _load_current_contract_context(root, result)
    if contract_values is None:
        raise ValueError("; ".join(
            _display_error(error) for error in result["errors"]))
    result["slot_path"] = result["profile_manifest"]
    slot_document = _typed_slot_document(
        profile_view, contract_values["slot_name"], result)
    if slot_document is None:
        raise ValueError("; ".join(
            _display_error(error) for error in result["errors"]))
    slot = _validate_slot(
        slot_document, result["profile_manifest"] + "#slots.corpus-planning",
        profile_view, root, result,
        contract_values=contract_values)
    result["slot"] = slot
    if slot:
        result["applicability"] = slot["mode"]
        if slot["mode"] == contract_values["configured_state"]:
            result["profile_scope"] = _validate_profile_scope(
                root, profile_view, result)
    if result["errors"] or not slot:
        raise ValueError("; ".join(
            _display_error(error) for error in result["errors"]) or
            "Corpus Planning slot is unresolved")
    for field, value in (
            ("coverage_ledger_sha256", coverage_ledger_sha256),
            ("required_queue_sha256", required_queue_sha256),
            ("progress_ledger_sha256", progress_ledger_sha256),
            ("repository_snapshot_sha256", repository_snapshot_sha256)):
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            raise ValueError("%s must be sha256:<64 lowercase hex>" % field)
    result["runtime"] = {
        "queue": {
            "task_id": task_id,
            "queue_revision": queue_revision,
            "state_revision": queue_state_revision,
            "selected_profile_manifest": result["profile_manifest"],
        },
        "coverage_sha256": coverage_ledger_sha256,
        "queue_sha256": required_queue_sha256,
        "progress_sha256": progress_ledger_sha256,
    }
    currency = _profile_view_currency_errors(root, profile_view)
    if currency:
        raise ValueError("; ".join(currency))
    return receipt_binding(
        result,
        repository_snapshot_sha256=repository_snapshot_sha256,
        progress_ledger_sha256=(
            terminal_progress_ledger_sha256
            if terminal_progress_ledger_sha256 is not None
            else progress_ledger_sha256),
        contract_values=contract_values,
    )


def pass_receipt_errors(root, receipt, *, result=None,
                        expected_binding=None,
                        repository_snapshot_sha256=None,
                        progress_ledger_sha256=None,
                        require_runtime=True,
                        require_configured=False,
                        contract_values=None):
    """Return freshness errors for one persisted Corpus Planning pass.

    Consumers rerun the structural/reconciliation validator only when they
    produce the receipt.  Reuse is checked by exact tool version plus the
    closed byte binding, so changed planning or runtime bytes cannot reuse an
    otherwise plausible old receipt.
    """
    errors = []
    if not isinstance(receipt, dict):
        return ["Corpus Planning receipt must be a mapping"]
    if result is None and expected_binding is None:
        result = validate_corpus_plan(root)
    if contract_values is None:
        if isinstance(result, dict):
            contract_values = _result_contract_values(result)
        else:
            try:
                contract_values = \
                    corpus_planning_contract.\
                    current_corpus_planning_contract_values(root)
            except (OSError, UnicodeError, TypeError, ValueError,
                    kblib.YamlSubsetError) as exc:
                return ["cannot bind the current K02 Corpus Planning "
                        "contract: %s" % exc]
    if result is not None and result.get("errors"):
        errors.append(
            "current Corpus Planning validation fails: %s" % "; ".join(
                _display_error(error) for error in result["errors"]))
        return errors
    applicability = (expected_binding.get("corpus_plan_applicability")
                     if isinstance(expected_binding, dict)
                     else result.get("applicability"))
    if require_configured and applicability != \
            contract_values["configured_state"]:
        errors.append("R13 requires Corpus Planning applicability.state=configured")
    if expected_binding is None:
        try:
            expected_binding = receipt_binding(
                result,
                repository_snapshot_sha256=repository_snapshot_sha256,
                progress_ledger_sha256=progress_ledger_sha256,
            )
        except (OSError, TypeError, ValueError) as exc:
            return ["cannot compute current Corpus Planning binding: %s" % exc]

    common = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "check": GATE_CHECK,
        "gate_id": GATE_ID,
        "target": expected_binding["selected_profile_manifest"],
        "result": "pass",
        "invalidated_by": None,
    }
    for field, expected in common.items():
        if receipt.get(field) != expected:
            errors.append("Corpus Planning receipt %s=%r, expected %r" %
                          (field, receipt.get(field), expected))
    for difference in corpus_planning_contract.receipt_binding_differences(
            receipt, expected_binding, contract_values=contract_values):
        errors.append("Corpus Planning receipt %s=%r, expected %r" %
                      (difference["field"], difference["actual"],
                       difference["expected"]))
    if require_runtime:
        for field in (
                "task_id", "queue_revision", "queue_state_revision",
                "coverage_ledger_sha256", "required_queue_sha256",
                "progress_ledger_sha256"):
            if expected_binding.get(field) is None:
                errors.append(
                    "Corpus Planning runtime binding %s may not be null" % field)
    return errors


def _plain_closed_mapping_errors(value, expected_fields, label):
    """Return closed-mapping errors without mutating a validation result."""
    if not isinstance(value, dict):
        return ["%s must be a mapping" % label]
    actual = set(value)
    errors = []
    missing = sorted(expected_fields - actual)
    extra = sorted(actual - expected_fields)
    if missing:
        errors.append("%s misses field(s): %s" %
                      (label, ", ".join(missing)))
    if extra:
        errors.append("%s has unsupported field(s): %s" %
                      (label, ", ".join(extra)))
    return errors


def acceptance_plan_errors(root, plan, result):
    """Validate one Agent-readable semantic-acceptance decision plan.

    This validates the decision envelope and the deterministic rank boundary.
    It does not make the semantic decision: every accepted/rejected value and
    rationale remains the declaration of the Profile-bound authority role.
    """
    contract_values = _result_contract_values(result)
    errors = _plain_closed_mapping_errors(
        plan, SEMANTIC_ACCEPTANCE_PLAN_FIELDS,
        "Corpus Planning semantic-acceptance plan")
    if not isinstance(plan, dict):
        return errors
    if result.get("errors"):
        errors.append("current Corpus Planning structure/reconciliation fails")
        return errors
    if result.get("applicability") != \
            contract_values["configured_state"]:
        errors.append(
            "semantic acceptance requires applicability.state=configured")
        return errors
    runtime = result.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("errors"):
        errors.append("semantic acceptance requires valid canonical runtime state")
    if plan.get("schema_version") != 1:
        errors.append("semantic-acceptance plan schema_version must be 1")

    acceptance_id = plan.get("acceptance_id")
    if (not isinstance(acceptance_id, str) or
            not ID_RE.fullmatch(acceptance_id)):
        errors.append("acceptance_id must be a stable identifier matching %s" %
                      ID_RE.pattern)

    authorities = (result.get("slot") or {}).get("authorities") or []
    expected_authority = (
        authorities[0].get("role_id") if len(authorities) == 1 else None)
    if plan.get("authority_role_id") != expected_authority:
        errors.append(
            "authority_role_id=%r, expected the Profile-bound role %r" %
            (plan.get("authority_role_id"), expected_authority))
    if plan.get("decision_scope_id") != \
            contract_values["semantic_acceptance_scope"]:
        errors.append("decision_scope_id must be exactly %s" %
                      contract_values["semantic_acceptance_scope"])

    decisions = plan.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        errors.append("decisions must be a non-empty list")
        decisions = []
    capabilities = (result.get("matrix") or {}).get("capabilities") or []
    expected_ids = [row.get("id") for row in capabilities]
    actual_ids = []
    scale = {
        row.get("value"): row.get("rank")
        for row in (result.get("slot") or {}).get("scale") or []
    }
    capability_by_id = {row.get("id"): row for row in capabilities}
    seen = set()
    for index, decision in enumerate(decisions):
        label = "semantic-acceptance plan decisions[%d]" % index
        errors.extend(_plain_closed_mapping_errors(
            decision, SEMANTIC_ACCEPTANCE_DECISION_FIELDS, label))
        if not isinstance(decision, dict):
            continue
        capability_id = decision.get("capability_id")
        actual_ids.append(capability_id)
        if not isinstance(capability_id, str) or not ID_RE.fullmatch(capability_id):
            errors.append("%s capability_id must be a stable identifier" % label)
        elif capability_id in seen:
            errors.append("%s repeats capability_id %s" %
                          (label, capability_id))
        seen.add(capability_id)
        value = decision.get("decision")
        if value not in SEMANTIC_ACCEPTANCE_DECISIONS:
            errors.append("%s decision must be accepted or rejected" % label)
        rationale = decision.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append("%s rationale must be a non-empty string" % label)
        elif "TODO" in rationale or "REPLACE-ME" in rationale:
            errors.append("%s rationale contains an unfilled sentinel" % label)
        capability = capability_by_id.get(capability_id)
        if capability is None:
            errors.append("%s names unknown capability_id %r" %
                          (label, capability_id))
        elif value == "accepted":
            current_rank = scale.get(capability.get("current_level"))
            target_rank = scale.get(capability.get("target_level"))
            if (not isinstance(current_rank, int) or
                    not isinstance(target_rank, int) or
                    current_rank < target_rank):
                errors.append(
                    "%s cannot accept capability below its target rank" % label)
    if actual_ids != expected_ids:
        errors.append(
            "decisions must name every current Capability Matrix row exactly "
            "once and in Matrix order; expected %r, found %r" %
            (expected_ids, actual_ids))
    return errors


def semantic_acceptance_receipt_errors(
        root, receipt, *, result=None, repository_snapshot_sha256=None,
        receipt_catalog=None, structural_receipt=None):
    """Return current-binding errors for one authority decision receipt."""
    errors = []
    if not isinstance(receipt, dict):
        return ["Corpus Planning semantic-acceptance receipt must be a mapping"]
    if result is None:
        result = validate_corpus_plan(root)
    contract_values = _result_contract_values(result)
    if result.get("errors"):
        return ["current Corpus Planning structure/reconciliation fails"]
    try:
        expected_binding = receipt_binding(
            result, repository_snapshot_sha256=repository_snapshot_sha256)
    except (OSError, TypeError, ValueError) as exc:
        return ["cannot compute current Corpus Planning binding: %s" % exc]
    if expected_binding.get("task_id") is None:
        errors.append("semantic acceptance requires current canonical runtime")

    common = {
        "tool": SEMANTIC_ACCEPTANCE_TOOL,
        "tool_version": SEMANTIC_ACCEPTANCE_TOOL_VERSION,
        "check": SEMANTIC_ACCEPTANCE_CHECK,
        "gate_id": contract_values["semantic_acceptance_scope"],
        "target": expected_binding["selected_profile_manifest"],
        "invalidated_by": None,
    }
    for field, expected in common.items():
        if receipt.get(field) != expected:
            errors.append("semantic-acceptance receipt %s=%r, expected %r" %
                          (field, receipt.get(field), expected))
    for difference in corpus_planning_contract.receipt_binding_differences(
            receipt, expected_binding, contract_values=contract_values):
        errors.append("semantic-acceptance receipt %s=%r, expected %r" %
                      (difference["field"], difference["actual"],
                       difference["expected"]))

    plan_path = receipt.get("acceptance_plan_path")
    plan = None
    if (not isinstance(plan_path, str) or
            os.path.dirname(plan_path) != SEMANTIC_ACCEPTANCE_PLAN_PREFIX or
            not plan_path.endswith(".yaml")):
        errors.append(
            "acceptance_plan_path must be one YAML file directly under %s/" %
            SEMANTIC_ACCEPTANCE_PLAN_PREFIX)
    else:
        try:
            absolute = kblib.managed_repository_path(
                root, plan_path, SEMANTIC_ACCEPTANCE_PLAN_PREFIX,
                suffixes=(".yaml",), must_exist=True)
            actual_sha = kblib.sha256_file(absolute)
            if receipt.get("acceptance_plan_sha256") != actual_sha:
                errors.append(
                    "acceptance_plan_sha256=%r, expected %r" %
                    (receipt.get("acceptance_plan_sha256"), actual_sha))
            plan = kblib.load_yaml_file(absolute)
        except (OSError, UnicodeError, ValueError,
                kblib.YamlSubsetError) as exc:
            errors.append("cannot load semantic-acceptance plan: %s" % exc)
    if plan is not None:
        errors.extend(acceptance_plan_errors(root, plan, result))
        comparisons = {
            "acceptance_id": plan.get("acceptance_id"),
            "authority_role_id": plan.get("authority_role_id"),
            "actor_role_id": plan.get("authority_role_id"),
            "decision_scope_id": plan.get("decision_scope_id"),
            "capability_decisions": plan.get("decisions"),
        }
        for field, expected in comparisons.items():
            if receipt.get(field) != expected:
                errors.append(
                    "semantic-acceptance receipt %s does not equal its plan" %
                    field)

    decisions = receipt.get("capability_decisions")
    if isinstance(decisions, list):
        expected_result = (
            "pass" if decisions and all(
                isinstance(row, dict) and row.get("decision") == "accepted"
                for row in decisions)
            else "fail")
        if receipt.get("result") != expected_result:
            errors.append("semantic-acceptance receipt result=%r, expected %r" %
                          (receipt.get("result"), expected_result))
    else:
        errors.append("semantic-acceptance receipt capability_decisions "
                      "must be a list")

    structural_id = receipt.get("structural_check_receipt")
    if structural_receipt is None:
        structural_receipt = catalog_receipt(
            receipt_catalog or {}, structural_id)
    if not isinstance(structural_id, str) or not structural_id:
        errors.append("structural_check_receipt must be a receipt ID")
    elif structural_receipt is None:
        errors.append("structural_check_receipt %r is not persisted" %
                      structural_id)
    elif structural_receipt.get("receipt_id") != structural_id:
        errors.append("structural_check_receipt ID does not match its record")
    else:
        errors.extend(pass_receipt_errors(
            root, structural_receipt, result=result,
            repository_snapshot_sha256=repository_snapshot_sha256,
            require_runtime=True, require_configured=True,
            contract_values=contract_values))
    return errors


def semantic_acceptance_status(result, *, repository_snapshot_sha256=None):
    """Return the current machine-readable authority-decision status."""
    contract_values = _result_contract_values(result)
    base = {
        "status": "not-recorded",
        "receipt_id": None,
        "authority_role_id": None,
        "decision_scope_id": contract_values["semantic_acceptance_scope"],
        "capability_decisions": [],
    }
    if result.get("errors") or result.get("applicability") != \
            contract_values["configured_state"] and \
            result.get("applicability") != \
            contract_values["inactive_state"]:
        base["status"] = "unavailable"
        return base
    runtime = result.get("runtime")
    if (not isinstance(runtime, dict) or runtime.get("errors") or
            not isinstance(runtime.get("current_receipt_catalog"), dict)):
        base["status"] = "unavailable"
        return base
    if result.get("applicability") == \
            contract_values["inactive_state"]:
        base["status"] = contract_values["inactive_state"]
        return base
    authorities = (result.get("slot") or {}).get("authorities") or []
    if len(authorities) == 1:
        base["authority_role_id"] = authorities[0].get("role_id")
    catalog = runtime.get("current_receipt_catalog")
    candidates = []
    for receipt_id, entry in catalog.items():
        receipt = catalog_receipt(catalog, receipt_id)
        if (not isinstance(receipt, dict) or
                receipt.get("tool") != SEMANTIC_ACCEPTANCE_TOOL or
                receipt.get("check") != SEMANTIC_ACCEPTANCE_CHECK):
            continue
        candidate_errors = semantic_acceptance_receipt_errors(
            result["root"], receipt, result=result,
            repository_snapshot_sha256=repository_snapshot_sha256,
            receipt_catalog=catalog)
        candidates.append((receipt, candidate_errors))
    current = [item for item in candidates if not item[1]]
    key = lambda item: (
        item[0].get("checked_at") if isinstance(
            item[0].get("checked_at"), str) else "",
        item[0].get("receipt_id") if isinstance(
            item[0].get("receipt_id"), str) else "",
    )
    if len(current) > 1:
        base["status"] = "ambiguous"
    elif current:
        receipt, _ = current[0]
        base.update({
            "status": ("current" if receipt.get("result") == "pass"
                       else "rejected"),
            "receipt_id": receipt.get("receipt_id"),
            "authority_role_id": receipt.get("authority_role_id"),
            "decision_scope_id": receipt.get("decision_scope_id"),
            "capability_decisions": receipt.get("capability_decisions") or [],
        })
    elif candidates:
        receipt, candidate_errors = max(candidates, key=key)
        base.update({
            "status": "stale",
            "receipt_id": receipt.get("receipt_id"),
            "stale_reason": candidate_errors[0] if candidate_errors else None,
        })
    return base


def validate_corpus_plan(root, profile=None, *, authorized_profile_view=None,
                         authorized_active_standards_view=None):
    """Return a structured validation result without writing repository state."""
    root = os.path.realpath(os.path.abspath(root))
    result = {
        "root": root,
        "profile_manifest": None,
        "slot_path": None,
        "applicability": None,
        "applicability_reason": None,
        "slot": None,
        "profile_scope": {"path": None, "layers": []},
        "global_map": {"entries": [], "edges": []},
        "matrix": {"capabilities": []},
        "gap_register": {"gaps": [], "promotions": []},
        "runtime": None,
        "_authorized_profile_view": None,
        "errors": [],
    }
    if not os.path.isdir(root):
        _add_error(result, "root", root, "repository root is not a directory")
        return result
    manifest_path, profile_view, _ = _authorized_profile_view(
        root, profile, result,
        authorized_profile_view=authorized_profile_view)
    if manifest_path is None or profile_view is None:
        return result
    result["_authorized_profile_view"] = profile_view
    result["profile_manifest"] = _relative(root, manifest_path)
    contract_values = _load_current_contract_context(root, result)
    if contract_values is None:
        return result
    result["slot_path"] = result["profile_manifest"]
    slot_document = _typed_slot_document(
        profile_view, contract_values["slot_name"], result)
    if slot_document is None:
        return result

    slot = _validate_slot(
        slot_document, result["profile_manifest"] + "#slots.corpus-planning",
        profile_view, root, result,
        contract_values=contract_values)
    result["slot"] = slot
    if slot:
        result["applicability"] = slot["mode"]
        result["applicability_reason"] = slot["reason"]

    runtime_result = runtime(
        root, result, authorized_profile_view=profile_view,
        authorized_active_standards_view=
            authorized_active_standards_view)
    result["runtime"] = runtime_result
    if runtime_result and not runtime_result.get("errors"):
        selected = ((runtime_result.get("progress") or {}).get("contract") or {}).get(
            "selected_profile_manifest")
        if selected != result["profile_manifest"]:
            _add_error(
                result, "profile_selection", result["profile_manifest"],
                "runtime_result selects %r" % selected,
            )

    if not slot or slot["mode"] != \
            contract_values["configured_state"]:
        for error in _profile_view_currency_errors(root, profile_view):
            _add_error(result, "profile_currency",
                       result["profile_manifest"], error)
        return result
    if set(slot["bindings"]) != set(
            _artifact_roles(contract_values)):
        for error in _profile_view_currency_errors(root, profile_view):
            _add_error(result, "profile_currency",
                       result["profile_manifest"], error)
        return result

    profile_scope = _validate_profile_scope(
        root, profile_view, result)
    result["profile_scope"] = profile_scope

    global_map = _validate_global_map(
        root, slot["bindings"]["Global Map"], profile_scope, result,
        contract_values=contract_values)
    result["global_map"] = global_map
    matrix = _validate_matrix(
        root, slot["bindings"]["Capability Matrix"], slot["scale"],
        global_map, result, contract_values=contract_values)
    result["matrix"] = matrix
    gap_register = _validate_gap_register(
        root, slot["bindings"]["Gap Register"], global_map, matrix,
        runtime_result, result, contract_values=contract_values)
    result["gap_register"] = gap_register
    for error in _profile_view_currency_errors(root, profile_view):
        _add_error(result, "profile_currency",
                   result["profile_manifest"], error)
    return result


def normalized_projection(result, *, repository_snapshot_sha256=None):
    """Return the compact deterministic Agent-facing validation projection."""
    profile_scope = result.get("profile_scope") or {}
    scope_layers = []
    for layer in profile_scope.get("layers") or []:
        scope_layers.append({
            "layer_id": layer.get("id"),
            "repository_relative_directories": [
                item.get("value") for item in layer.get("directories") or []
                if isinstance(item, dict)
            ],
            "single_layer_responsibility": layer.get("responsibility"),
        })
    global_map = result.get("global_map") or {}
    entries = []
    for entry in global_map.get("entries") or []:
        path = entry.get("path") or {}
        entries.append({
            "entry_id": entry.get("id"),
            "layer_id": entry.get("layer_id"),
            "canonical_markdown_path": path.get("value"),
            "single_responsibility": entry.get("responsibility"),
        })
    edges = [{
        "edge_id": edge.get("id"),
        "upstream_entry_id": edge.get("upstream"),
        "downstream_entry_id": edge.get("downstream"),
        "relation_type": edge.get("relation"),
    } for edge in global_map.get("edges") or []]
    matrix = result.get("matrix") or {}
    capabilities = []
    for row in matrix.get("capabilities") or []:
        capabilities.append({
            "capability_id": row.get("id"),
            "capability": row.get("capability"),
            "priority": row.get("priority"),
            "map_entry_ids": row.get("map_entry_ids") or [],
            "canonical_markdown_paths": [
                path.get("value") for path in row.get("canonical_paths") or []
                if isinstance(path, dict)
            ],
            "current_level": row.get("current_level"),
            "target_level": row.get("target_level"),
            "evidence_paths": [
                path.get("value") for path in row.get("evidence_paths") or []
                if isinstance(path, dict)
            ],
            "gap_ids": row.get("gap_ids") or [],
        })
    gap_register = result.get("gap_register") or {}
    gaps = []
    for row in gap_register.get("gaps") or []:
        target_path = row.get("target_path") or {}
        gaps.append({
            "gap_id": row.get("id"),
            "gap_statement": row.get("statement"),
            "capability_ids": row.get("capability_ids") or [],
            "candidate_owner_entry_id": row.get("candidate_owner"),
            "status": row.get("status"),
            "close_condition": row.get("close_condition"),
            "evidence_paths": [
                path.get("value") for path in row.get("evidence_paths") or []
                if isinstance(path, dict)
            ],
            "promoted_coverage_path": target_path.get("value"),
            "rationale": row.get("rationale"),
        })
    runtime = result.get("runtime")
    runtime_summary = None
    if isinstance(runtime, dict):
        queue = runtime.get("queue") or {}
        progress = runtime.get("progress") or {}
        runtime_summary = {
            "task_id": queue.get("task_id"),
            "task_state": progress.get("task_state"),
            "queue_revision": queue.get("queue_revision"),
            "queue_state_revision": queue.get("state_revision"),
            "coverage_ledger_sha256": runtime.get("coverage_sha256"),
            "required_queue_sha256": runtime.get("queue_sha256"),
            "progress_ledger_sha256": runtime.get("progress_sha256"),
            "errors": runtime.get("errors") or [],
        }
    return {
        "structural_reconciliation_valid": not bool(result.get("errors")),
        "profile_manifest": result.get("profile_manifest"),
        "slot_path": result.get("slot_path"),
        "applicability": result.get("applicability"),
        "applicability_reason": result.get("applicability_reason"),
        "profile_scope": {
            "path": profile_scope.get("path"),
            "layers": scope_layers,
        },
        "global_map": {"entries": entries,
                       "typed_dependencies": edges},
        "capability_matrix": {"capabilities": capabilities},
        "gap_register": {"gaps": gaps},
        "semantic_acceptance": semantic_acceptance_status(
            result,
            repository_snapshot_sha256=repository_snapshot_sha256,
        ),
        "runtime": runtime_summary,
        "errors": result.get("errors") or [],
    }


def _receipts_for(result, *, repository_snapshot_sha256=None):
    if not result["errors"]:
        try:
            return [make_pass_receipt(
                result,
                repository_snapshot_sha256=repository_snapshot_sha256,
                seq=1,
            )]
        except (OSError, TypeError, ValueError) as exc:
            _add_error(result, "receipt_binding", result.get(
                "profile_manifest") or "<unresolved>", str(exc))
    receipts = []
    for seq, error in enumerate(result["errors"], 1):
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, error["check"], error["target"], "fail",
            error["details"], seq,
            receipt_type_id=DIAGNOSTIC_RECEIPT_TYPE_ID,
            root=result.get("root")))
    return receipts


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Validate explicit Corpus Planning artifacts")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument(
        "--profile",
        help="repository-relative Profile manifest or Profile directory; "
             "default: selected Profile in Progress Ledger",
    )
    parser.add_argument("--receipts", help="append JSONL receipts here")
    parser.add_argument(
        "--json", action="store_true",
        help="write only the deterministic normalized result JSON to stdout",
    )
    args = parser.parse_args(argv)

    result = validate_corpus_plan(args.root, args.profile)
    try:
        snapshot = kblib.repository_snapshot_sha256(result["root"])
    except (OSError, ValueError) as exc:
        snapshot = None
        _add_error(result, "repository_snapshot", result["root"], str(exc))
    receipts = _receipts_for(
        result, repository_snapshot_sha256=snapshot)
    if args.receipts:
        try:
            receipt_path = kblib.repository_path(
                result["root"], args.receipts, must_exist=False,
                reject_symlink=True)
            kblib.write_receipts(receipt_path, receipts)
        except (OSError, ValueError) as exc:
            _add_error(result, "receipt_write", args.receipts, str(exc))
    for error in _result_currency_errors(result):
        _add_error(result, "publication_currency",
                   result.get("profile_manifest") or "<unresolved>", error)
    if args.json:
        print(json.dumps(normalized_projection(
            result, repository_snapshot_sha256=snapshot), sort_keys=True,
                         separators=(",", ":")))
        return 1 if result["errors"] else 0
    if result["errors"]:
        for error in result["errors"]:
            print("[FAIL] %s" % _display_error(error))
        print("[FAIL] Corpus Planning validation failed with %d issue(s)" %
              len(result["errors"]))
        return 1
    contract_values = _result_contract_values(result)
    if result["applicability"] == contract_values["inactive_state"]:
        print("[PASS] Corpus Planning structure: not applicable: %s" %
              result["applicability_reason"])
    else:
        semantic = semantic_acceptance_status(
            result, repository_snapshot_sha256=snapshot)
        print(
            "[PASS] Corpus Planning structure/reconciliation: %d layer(s), "
            "%d entry(ies), %d capability(ies), %d gap(s); "
            "semantic_acceptance=%s" % (
                len(result["profile_scope"]["layers"]),
                len(result["global_map"]["entries"]),
                len(result["matrix"]["capabilities"]),
                len(result["gap_register"]["gaps"]),
                semantic["status"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
