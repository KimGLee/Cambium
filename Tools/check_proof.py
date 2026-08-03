#!/usr/bin/env python3
"""Terminal Proof completeness check script.

Rule owners:
- "kernel/K12 Quality Assurance/15 Terminal Audit and Convergence.md"
  (the complete Terminal Proof field list, including
   selected_route_ids, selected_card_paths, and full_deterministic_results);
- "kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md"
  (completion conditions: the three open guidance counts are 0,
   required_authoring_gaps=0, unverified_batches=0,
   unresolved_invalidations=0, and all applicable gates pass);
- "kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md"
  (Terminal Reconciliation Rules: unresolved_invalidations must be 0).

Method:
- The required-field list comes from the top-level keys of
  Tools/schemas/terminal_proof.template.yaml (the template copies K12/15 field
  by field as this script's machine-readable projection; K12/15 remains the
  normative field-list owner; --template overrides the projection path);
- a missing or empty proof field -> fail (Terminal Proof incomplete);
- selected_profile_manifest must be one exact
  profiles/<profile_id>/profile.md path; with --root its manifest identity is
  validated, check_profile.py must accept the filled profile, every profile
  path must stay within it, and every supplemental route must use its id;
- selected_route_ids must be a non-empty list of unique Runtime Route IDs in
  the closed range R01-R12 and, because this is terminal evidence, must include
  R01 Core Bootstrap, R12 Targeted and Specialized Audit, and R08 Audit and
  Completion;
- selected_card_paths must be a non-empty list of unique Card paths;
- selected_profile_route_ids must be a list of unique namespaced supplemental
  route IDs; an empty list records that no profile route was combined;
- selected_read_sets is the possibly empty, unique list of Read Sets actually
  read back, not a second declaration of every selected route. Kernel Read Set
  paths are registry-checked; profile Read Set paths receive existence and
  uniqueness checks only because the profile registry is prose, not a
  machine-readable canonical map;
- a zero-condition field (required_authoring_gaps / unverified_batches /
  unresolved_invalidations) that is not 0 -> fail;
- a top-level proof field outside the list -> candidate (whether it is
  reasonable is a human call);
- semantic checks (K12/06 completion conditions are semantic, not just
  structural): guidance_reconciliation_result /
  coverage_reconciliation_result / automated_QA_result / manual_review_result
  must be exactly "passed" -> otherwise fail; rendering_evidence /
  time_contract_result containing an explicit fail/failed/failure statement
  -> fail;
- when --root (vault root) is given, path-valued fields, including every path
  in incremental_manual_scope, must exist under it;
  the canonical Card and Read Set indexes are parsed, every selected route must
  have exactly its registered Card path, and every recorded Read Set must be
  registered to a selected route -> otherwise fail;
- without --root, only proof structure is checked; no route-registry agreement
  is claimed;
- when --ledger (Coverage Ledger) is given, cross-check: open_gaps non-empty
  while the proof claims required_authoring_gaps=0 -> fail;
- --root requires an instantiated, approved K00/03 active state and
  --progress-ledger; the active state, frozen contract, and Terminal Proof must
  carry the same standards_version and selected_profile_manifest.

This script verifies proof consistency, not the work itself: a proof can
still lie consistently. The receipts, ledgers, and snapshots it references
are the actual evidence; K12/15 owns the human side of the terminal audit.

Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_proof.py <proof.yaml> [--ledger coverage_ledger.yaml]
       [--root VAULT_ROOT --progress-ledger progress_ledger.yaml]
       [--template PATH] [--receipts PATH]
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_proof"
TOOL_VERSION = "1.6.0"

# K12/06: fields that must be 0 among the completion conditions (the three open
# guidance counts are covered by the review of guidance_reconciliation_result
# and get no numeric assertion here)
ZERO_FIELDS = ("required_authoring_gaps", "unverified_batches",
               "unresolved_invalidations")

# Result fields whose value must be exactly "passed" for completion (K12/06
# condition; procedures in K12/15 steps 3, 4, and 7 plus automated checks in
# K12/05). Any other value fails.
PASSED_FIELDS = ("guidance_reconciliation_result",
                 "coverage_reconciliation_result",
                 "automated_QA_result",
                 "manual_review_result")

# Free-text evidence fields: deterministically reject an explicit failure
# statement; anything else stays a human call.
NO_FAIL_TOKEN_FIELDS = ("rendering_evidence", "time_contract_result")

# Fields whose values are vault-relative paths that must exist when --root is
# given (K12/15 steps 1-2 and 7: loaded sources, evidence, and incremental
# manual-review scope).
PATH_FIELDS = ("selected_profile_manifest", "selected_card_paths",
               "selected_read_sets", "loaded_module_paths",
               "audit_receipt_register", "full_deterministic_results",
               "incremental_manual_scope")

# Kernel Runtime Route IDs are a closed registry. Index documents do not occupy
# R00; the twelve executable routes are R01-R12.
RUNTIME_ROUTE_ID_RE = re.compile(r"R(?:0[1-9]|1[0-2])\Z")
PROFILE_ROUTE_ID_RE = re.compile(r"P:[^:\s]+:[^:\s]+\Z")
EXPECTED_ROUTE_IDS = tuple("R%02d" % number for number in range(1, 13))
TERMINAL_REQUIRED_ROUTE_IDS = frozenset(("R01", "R08", "R12"))
REGISTRY_ID = "kernel-runtime-routes"
CARD_INDEX_PATH = "kernel/Cards/Card Index.md"
READ_SET_INDEX_PATH = "kernel/Read Sets/Read Sets Index.md"
EXECUTION_DEFAULTS_PATH = "Tools/schemas/execution_defaults.template.yaml"
ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
UNINSTANTIATED_RE = re.compile(r"\{\{.*?\}\}")


def _resolve_under_root(root, raw_path):
    """Resolve one repository-relative path without allowing root escape."""
    syntax_error = _repo_relative_path_error(raw_path)
    if syntax_error:
        return None, syntax_error
    candidate = Path(raw_path)
    try:
        resolved = (root / candidate).resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        return None, "path cannot be resolved under the repository root: %s" % exc
    return resolved, None


def _repo_relative_path_error(raw_path):
    """Return a structural error for a non-canonical vault-relative path."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return "path must be a non-empty string"
    if raw_path != raw_path.strip():
        return "path must not have leading or trailing whitespace"
    candidate = Path(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return "path must be repository-relative; '..' segments are forbidden"
    return None


def _selected_profile_manifest_error(raw_path):
    """Require the one canonical profile-manifest path shape."""
    path_error = _repo_relative_path_error(raw_path)
    if path_error:
        return path_error
    parts = Path(raw_path).parts
    if (len(parts) != 3 or parts[0] != "profiles" or
            parts[2] != "profile.md"):
        return ("path must be exactly profiles/<profile_id>/profile.md; "
                "directories, globs, candidate lists, and nested manifests "
                "do not select a profile")
    return None


def _uninstantiated_value(raw_value):
    return (not isinstance(raw_value, str) or not raw_value.strip() or
            UNINSTANTIATED_RE.search(raw_value) is not None)


def _load_active_standards_state(root):
    """Read the canonical four-field state table from K00/03."""
    state = {}
    path, resolve_error = _resolve_under_root(root, ACTIVE_STATE_PATH)
    if resolve_error or not path.is_file():
        return state, [
            "%s is missing or unsafe: %s" %
            (ACTIVE_STATE_PATH, resolve_error or "not a regular file")
        ]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return state, ["cannot read %s: %s" % (ACTIVE_STATE_PATH, exc)]

    state, parse_errors = kblib.active_standards_state(text)
    errors = ["%s: %s" % (ACTIVE_STATE_PATH, error)
              for error in parse_errors]
    for label, key in kblib.ACTIVE_STANDARDS_STATE_LABELS.items():
        if key in state and _uninstantiated_value(state[key]):
            errors.append("%s %s is still uninstantiated: %r" %
                          (ACTIVE_STATE_PATH, label, state[key]))
    if ("standards_status" in state and
            not _uninstantiated_value(state["standards_status"]) and
            state["standards_status"] != "approved"):
        errors.append("%s Status must be approved for a content task; found %r"
                      % (ACTIVE_STATE_PATH, state["standards_status"]))
    if ("selected_profile_manifest" in state and
            not _uninstantiated_value(state["selected_profile_manifest"])):
        path_error = _selected_profile_manifest_error(
            state["selected_profile_manifest"]
        )
        if path_error:
            errors.append("%s Selected profile manifest is invalid: %s" %
                          (ACTIVE_STATE_PATH, path_error))
    return state, errors


def _load_index(root, relative_path, expected_type):
    """Parse one canonical route index and return its frontmatter mapping."""
    errors = []
    path, resolve_error = _resolve_under_root(root, relative_path)
    if resolve_error:
        return None, ["%s: %s" % (relative_path, resolve_error)]
    if not path.is_file():
        return None, ["required index is missing: %s" % relative_path]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, ["cannot read %s as UTF-8: %s" % (relative_path, exc)]
    front = kblib.extract_frontmatter(text)
    if front is None:
        return None, ["%s has no fenced frontmatter" % relative_path]
    try:
        data = kblib.parse_yaml_subset(front)
    except kblib.YamlSubsetError as exc:
        return None, ["cannot parse %s frontmatter: %s" % (relative_path, exc)]
    if not isinstance(data, dict):
        return None, ["%s frontmatter must be a mapping" % relative_path]
    errors.extend(_duplicate_registry_key_errors(front, relative_path))
    if data.get("type") != expected_type:
        errors.append("%s must declare type: %s" % (relative_path, expected_type))
    if data.get("registry_id") != REGISTRY_ID:
        errors.append("%s must declare registry_id: %s" %
                      (relative_path, REGISTRY_ID))
    if "route_id" in data:
        errors.append("%s must not declare route_id; an index is not a route" %
                      relative_path)
    if "card_id" in data or "card_registry" in data:
        errors.append("%s contains retired Card identity fields" % relative_path)
    registry = data.get("route_registry")
    if not isinstance(registry, list) or not registry:
        errors.append("%s must declare a non-empty route_registry" % relative_path)
    return data, errors


def _duplicate_registry_key_errors(front, relative_path):
    """Reject duplicate top-level and route-registry-entry identity keys."""
    errors = []
    prepared = []
    for line_number, raw in enumerate(front.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        prepared.append((len(raw) - len(raw.lstrip(" ")), stripped,
                         line_number))

    def key_of(content):
        match = re.match(r"^([^:\s][^:]*):(?:\s|$)", content)
        return match.group(1).strip() if match else ""

    top_keys = set()
    registry_starts = []
    for item_index, (indent, content, line_number) in enumerate(prepared):
        if indent or content == "-" or content.startswith("- "):
            continue
        key = key_of(content)
        if not key:
            continue
        if key in top_keys:
            errors.append("%s repeats top-level key %s at line %d" %
                          (relative_path, key, line_number))
        else:
            top_keys.add(key)
        if key == "route_registry":
            registry_starts.append(item_index)

    for start in registry_starts:
        base_indent = prepared[start][0]
        entry_number = 0
        entry_keys = None
        for indent, content, line_number in prepared[start + 1:]:
            if indent <= base_indent:
                break
            if content == "-" or content.startswith("- "):
                entry_number += 1
                entry_keys = set()
                content = content[1:].strip()
            if entry_keys is None or not content:
                continue
            key = key_of(content)
            if not key:
                continue
            if key in entry_keys:
                errors.append(
                    "%s route_registry entry %d repeats key %s at line %d"
                    % (relative_path, entry_number, key, line_number))
            else:
                entry_keys.add(key)
    return errors


def _registry_map(data, relative_path, card_index):
    """Return route -> canonical path data while rejecting registry anomalies."""
    errors = []
    result = {}
    paths = set()
    read_sets = set()
    registry = data.get("route_registry") if isinstance(data, dict) else None
    if not isinstance(registry, list):
        return result, errors

    for index, entry in enumerate(registry):
        label = "%s route_registry[%d]" % (relative_path, index)
        if not isinstance(entry, dict):
            errors.append("%s must be a mapping" % label)
            continue
        route_id = entry.get("route_id")
        path = entry.get("path")
        read_set = entry.get("read_set") if card_index else None
        if not isinstance(route_id, str) or not RUNTIME_ROUTE_ID_RE.fullmatch(route_id):
            errors.append("%s has invalid route_id %r; expected R01-R12" %
                          (label, route_id))
            continue
        if route_id in result:
            errors.append("%s repeats route_id %s" % (relative_path, route_id))
            continue
        if not isinstance(path, str) or not path:
            errors.append("%s has no canonical path" % label)
            continue
        expected_path_prefix = (
            "kernel/Cards/%s " if card_index else
            "kernel/Read Sets/%s ") % route_id
        if (not path.startswith(expected_path_prefix) or
                not path.endswith(".md") or Path(path).is_absolute() or
                ".." in Path(path).parts):
            errors.append(
                "%s path %r is not the canonical %s path for %s"
                % (label, path, "Card" if card_index else "Read Set", route_id))
            continue
        if path in paths:
            errors.append("%s repeats canonical path %s" % (relative_path, path))
            continue
        if card_index:
            if not isinstance(read_set, str) or not read_set:
                errors.append("%s has no read_set path" % label)
                continue
            expected_read_set_prefix = "kernel/Read Sets/%s " % route_id
            if (not read_set.startswith(expected_read_set_prefix) or
                    not read_set.endswith(".md") or Path(read_set).is_absolute() or
                    ".." in Path(read_set).parts):
                errors.append(
                    "%s read_set %r is not the canonical Read Set path for %s"
                    % (label, read_set, route_id))
                continue
            if read_set in read_sets:
                errors.append("%s repeats read_set path %s" %
                              (relative_path, read_set))
                continue
            read_sets.add(read_set)
        paths.add(path)
        result[route_id] = {"path": path, "read_set": read_set}

    actual_routes = set(result)
    expected_routes = set(EXPECTED_ROUTE_IDS)
    if actual_routes != expected_routes:
        errors.append(
            "%s route coverage must be exactly R01-R12; missing=%s extra=%s"
            % (relative_path,
               sorted(expected_routes - actual_routes),
               sorted(actual_routes - expected_routes)))
    return result, errors


def _load_route_registry(root):
    """Load and cross-check the canonical Card and Read Set index pair."""
    errors = []
    card_data, card_errors = _load_index(root, CARD_INDEX_PATH, "card-index")
    read_data, read_errors = _load_index(root, READ_SET_INDEX_PATH, "route-index")
    errors.extend(card_errors)
    errors.extend(read_errors)

    card_map, card_map_errors = _registry_map(card_data, CARD_INDEX_PATH, True)
    read_map, read_map_errors = _registry_map(
        read_data, READ_SET_INDEX_PATH, False)
    errors.extend(card_map_errors)
    errors.extend(read_map_errors)

    for route_id in sorted(set(card_map) & set(read_map)):
        card_read_set = card_map[route_id]["read_set"]
        canonical_read_set = read_map[route_id]["path"]
        if card_read_set != canonical_read_set:
            errors.append(
                "%s binds %s to %s, but %s registers %s"
                % (CARD_INDEX_PATH, route_id, card_read_set,
                   READ_SET_INDEX_PATH, canonical_read_set))
    return card_map, read_map, errors


def main():
    ap = argparse.ArgumentParser(description="Terminal Proof completeness and zero-condition check")
    ap.add_argument("proof", help="path to the terminal proof YAML file")
    ap.add_argument("--ledger", help="Coverage Ledger YAML, for the open_gaps cross-check")
    ap.add_argument("--progress-ledger", help="Progress Ledger YAML; required "
                    "with --root to prove that the Terminal Proof uses the "
                    "same frozen Standards version and selected profile")
    ap.add_argument("--template",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "schemas", "terminal_proof.template.yaml"),
                    help="field-list template (default Tools/schemas/terminal_proof.template.yaml)")
    ap.add_argument("--root", help="vault root; when given, path-valued proof "
                    "fields must exist and selected routes, Cards, and kernel "
                    "Read Sets must agree with the canonical route indexes")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    template = kblib.parse_yaml_subset(open(args.template, encoding="utf-8").read())
    required_fields = list(template.keys())

    receipts = []
    seq = 0
    proof_name = os.path.basename(args.proof)

    try:
        proof = kblib.parse_yaml_subset(open(args.proof, encoding="utf-8").read())
    except (OSError, kblib.YamlSubsetError) as exc:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-unreadable", args.proof, "fail",
            "cannot read/parse proof: %s" % exc, seq))
        kblib.write_receipts(args.receipts, receipts)
        print("check_proof: cannot read or parse %s: %s" % (args.proof, exc))
        return 1
    if not isinstance(proof, dict):
        proof = {}

    missing = []
    for field in required_fields:
        value = proof.get(field, None)
        # Note: an empty list [] is generally legal for list-valued fields
        # (e.g. systemic_expansions: []) and does not count as structurally
        # missing. selected_route_ids and selected_card_paths have their own
        # non-empty semantic checks.
        if field not in proof or value is None or value == "":
            missing.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-field-missing",
                "%s#%s" % (proof_name, field), "fail",
                "Terminal Proof is missing required field %s (K12/15 field list)" % field, seq))

    frozen_string_bad = 0
    if "standards_version" not in missing:
        value = proof.get("standards_version")
        if _uninstantiated_value(value):
            frozen_string_bad += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-standards-version-invalid",
                "%s#standards_version" % proof_name, "fail",
                "standards_version must be an instantiated non-empty string "
                "copied exactly from the frozen Task Contract", seq))

    profile_manifest_bad = 0
    selected_profile_manifest = proof.get("selected_profile_manifest")
    if "selected_profile_manifest" not in missing:
        manifest_error = _selected_profile_manifest_error(
            selected_profile_manifest
        )
        if manifest_error:
            profile_manifest_bad += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-profile-manifest-invalid",
                "%s#selected_profile_manifest" % proof_name, "fail",
                "selected_profile_manifest %r is invalid: %s" %
                (selected_profile_manifest, manifest_error), seq))

    route_id_bad = 0
    valid_route_ids = set()
    route_ids = proof.get("selected_route_ids")
    if "selected_route_ids" not in missing:
        if not isinstance(route_ids, list) or not route_ids:
            route_id_bad += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-route-ids-empty",
                "%s#selected_route_ids" % proof_name, "fail",
                "selected_route_ids must be a non-empty list of kernel "
                "Runtime Route IDs (R01-R12)", seq))
        else:
            seen_route_ids = set()
            for index, route_id in enumerate(route_ids):
                target = "%s#selected_route_ids[%d]" % (proof_name, index)
                if not isinstance(route_id, str) or not RUNTIME_ROUTE_ID_RE.fullmatch(route_id):
                    route_id_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-route-id-invalid",
                        target, "fail",
                        "route ID %r is invalid; expected one of R01-R12"
                        % route_id, seq))
                else:
                    valid_route_ids.add(route_id)
                route_key = repr(route_id)
                if route_key in seen_route_ids:
                    route_id_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-route-id-duplicate",
                        target, "fail",
                        "route ID %r is duplicated; selected_route_ids must "
                        "contain unique IDs" % route_id, seq))
                else:
                    seen_route_ids.add(route_key)

            missing_terminal_routes = TERMINAL_REQUIRED_ROUTE_IDS - valid_route_ids
            if missing_terminal_routes:
                route_id_bad += len(missing_terminal_routes)
                for route_id in sorted(missing_terminal_routes):
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-terminal-route-missing",
                        "%s#selected_route_ids" % proof_name, "fail",
                        "%s is mandatory in Terminal Proof: R01 establishes "
                        "the common control boundary, R12 owns the bounded "
                        "targeted/specialized review scope, and R08 is the "
                        "terminal audit/completion route" % route_id, seq))

    profile_route_id_bad = 0
    profile_route_ids = proof.get("selected_profile_route_ids")
    valid_profile_route_ids = []
    if "selected_profile_route_ids" not in missing:
        if not isinstance(profile_route_ids, list):
            profile_route_id_bad += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-profile-route-ids-not-list",
                "%s#selected_profile_route_ids" % proof_name, "fail",
                "selected_profile_route_ids must be a list; use [] when no "
                "supplemental profile route was combined", seq))
        else:
            seen_profile_route_ids = set()
            for index, route_id in enumerate(profile_route_ids):
                target = "%s#selected_profile_route_ids[%d]" % (proof_name, index)
                if (not isinstance(route_id, str) or
                        not PROFILE_ROUTE_ID_RE.fullmatch(route_id)):
                    profile_route_id_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-profile-route-id-invalid",
                        target, "fail",
                        "profile route ID %r is invalid; expected "
                        "P:<profile_id>:<route_name> with non-empty colon-free "
                        "segments" % route_id, seq))
                elif route_id in seen_profile_route_ids:
                    profile_route_id_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-profile-route-id-duplicate",
                        target, "fail",
                        "profile route ID %r is duplicated; supplemental "
                        "route IDs must be unique" % route_id, seq))
                else:
                    seen_profile_route_ids.add(route_id)
                    valid_profile_route_ids.append(route_id)

    card_path_bad = 0
    path_structure_bad = 0
    selected_card_paths = proof.get("selected_card_paths")
    valid_card_paths = []
    if "selected_card_paths" not in missing:
        if not isinstance(selected_card_paths, list) or not selected_card_paths:
            card_path_bad += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-card-paths-empty",
                "%s#selected_card_paths" % proof_name, "fail",
                "selected_card_paths must be a non-empty list with one "
                "canonical Runtime Card path for every selected Rxx route", seq))
        else:
            seen_card_paths = set()
            for index, card_path in enumerate(selected_card_paths):
                target = "%s#selected_card_paths[%d]" % (proof_name, index)
                path_error = _repo_relative_path_error(card_path)
                if path_error:
                    card_path_bad += 1
                    path_structure_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-card-path-invalid",
                        target, "fail",
                        "Card path %r is invalid: %s" %
                        (card_path, path_error), seq))
                elif card_path in seen_card_paths:
                    card_path_bad += 1
                    path_structure_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-card-path-duplicate",
                        target, "fail",
                        "Card path %r is duplicated; selected_card_paths "
                        "must be unique" % card_path, seq))
                else:
                    seen_card_paths.add(card_path)
                    valid_card_paths.append(card_path)

    read_set_bad = 0
    selected_read_sets = proof.get("selected_read_sets")
    valid_read_set_paths = []
    if "selected_read_sets" not in missing:
        if not isinstance(selected_read_sets, list):
            read_set_bad += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-read-sets-not-list",
                "%s#selected_read_sets" % proof_name, "fail",
                "selected_read_sets must be a list; use [] when no Read Set "
                "was read back", seq))
        else:
            seen_read_set_paths = set()
            for index, read_set_path in enumerate(selected_read_sets):
                target = "%s#selected_read_sets[%d]" % (proof_name, index)
                path_error = _repo_relative_path_error(read_set_path)
                if path_error:
                    read_set_bad += 1
                    path_structure_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-read-set-path-invalid",
                        target, "fail",
                        "Read Set path %r is invalid: %s" %
                        (read_set_path, path_error), seq))
                elif read_set_path in seen_read_set_paths:
                    read_set_bad += 1
                    path_structure_bad += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-read-set-path-duplicate",
                        target, "fail",
                        "Read Set path %r is duplicated; selected_read_sets "
                        "records each actual readback once" % read_set_path, seq))
                else:
                    seen_read_set_paths.add(read_set_path)
                    valid_read_set_paths.append(read_set_path)

    # Every remaining path-bearing field uses the same repository-relative
    # syntax boundary even without --root. Lists additionally carry each path
    # once. Existence, regular-file, and symlink-escape checks need --root.
    for field in PATH_FIELDS:
        if field in ("selected_profile_manifest", "selected_card_paths",
                     "selected_read_sets"):
            continue
        if field in missing or field not in proof:
            continue
        value = proof.get(field)
        values = value if isinstance(value, list) else [value]
        seen_paths = set()
        for index, raw_path in enumerate(values):
            target = "%s#%s" % (proof_name, field)
            if isinstance(value, list):
                target += "[%d]" % index
            path_error = _repo_relative_path_error(raw_path)
            if path_error:
                path_structure_bad += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "proof-path-invalid",
                    target, "fail",
                    "path %r recorded in %s is invalid: %s"
                    % (raw_path, field, path_error), seq))
            elif raw_path in seen_paths:
                path_structure_bad += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "proof-path-duplicate",
                    target, "fail",
                    "path %r is duplicated in %s" % (raw_path, field), seq))
            else:
                seen_paths.add(raw_path)

    if (isinstance(route_ids, list) and route_ids and
            isinstance(selected_card_paths, list) and selected_card_paths and
            len(route_ids) != len(selected_card_paths)):
        card_path_bad += 1
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-card-route-cardinality",
            "%s#selected_card_paths" % proof_name, "fail",
            "selected_card_paths has %d item(s) for %d selected_route_ids; "
            "Terminal Proof requires one Card path per selected Rxx route"
            % (len(selected_card_paths), len(route_ids)), seq))

    zero_bad = []
    for field in ZERO_FIELDS:
        if field in missing or field not in proof:
            continue
        value = proof.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            zero_bad.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-zero-field",
                "%s#%s" % (proof_name, field), "fail",
                "zero-condition field %s = %r; the completion conditions require it to be 0 (K12/06)" % (field, value), seq))

    if "selected_profile_id" in proof:
        profile_manifest_bad += 1
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-duplicate-profile-identity",
            "%s#selected_profile_id" % proof_name, "fail",
            "selected_profile_id is forbidden: profile identity is derived "
            "only from selected_profile_manifest", seq))

    extra = [k for k in proof
             if k not in required_fields and k != "selected_profile_id"]
    for field in extra:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-extra-field",
            "%s#%s" % (proof_name, field), "candidate",
            "field %s is not in the K12/15 field list (the list is an 'at least' "
            "list; whether extra fields are reasonable is a human call)"
            % field, seq))

    # ---- semantic checks: statuses, failure tokens, path existence ----
    # (K12/06 completion conditions are semantic, not just structural; a proof
    # whose reconciliation says "failed" must never pass this script.)
    status_bad = []
    for field in PASSED_FIELDS:
        if field in missing or field not in proof:
            continue
        value = str(proof.get(field)).strip()
        if value != "passed":
            status_bad.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-status-not-passed",
                "%s#%s" % (proof_name, field), "fail",
                "%s = %r; completion requires this result to be \"passed\" "
                "(K12/06)" % (field, value), seq))
    for field in NO_FAIL_TOKEN_FIELDS:
        if field in missing or field not in proof:
            continue
        value = str(proof.get(field))
        if re.search(r"\bfail(ed|ure)?\b", value, re.IGNORECASE):
            status_bad.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-evidence-declares-failure",
                "%s#%s" % (proof_name, field), "fail",
                "%s contains an explicit failure statement: %r (K12/06: "
                "evidence recording a failure cannot support completion)"
                % (field, value), seq))

    path_bad = 0
    registry_bad = 0
    registry_checked = False
    active_state_bad = 0
    active_state_checked = False
    profile_identity_checked = False
    profile_manifest_checked = False
    selected_profile_id = None
    if args.root:
        root = Path(args.root).resolve()
        if not root.is_dir():
            path_bad += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-root-invalid", str(root), "fail",
                "--root must resolve to an existing directory", seq))
        else:
            active_state, active_state_errors = _load_active_standards_state(root)
            for index, details in enumerate(active_state_errors):
                active_state_bad += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "proof-active-state-invalid",
                    "%s#active_state[%d]" % (proof_name, index), "fail",
                    details, seq))
            if not active_state_errors:
                active_state_checked = True
                for field in ("standards_version",
                              "selected_profile_manifest"):
                    if field in missing:
                        continue
                    if active_state.get(field) != proof.get(field):
                        active_state_checked = False
                        active_state_bad += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION,
                            "proof-active-state-mismatch",
                            "%s#%s" % (proof_name, field), "fail",
                            "Terminal Proof %s=%r does not match active "
                            "Standards state %r in %s" %
                            (field, proof.get(field), active_state.get(field),
                             ACTIVE_STATE_PATH), seq))

            for field in PATH_FIELDS:
                if field in missing or field not in proof:
                    continue
                value = proof.get(field)
                values = value if isinstance(value, list) else [value]
                for index, raw_path in enumerate(values):
                    target = "%s#%s" % (proof_name, field)
                    if isinstance(value, list):
                        target += "[%d]" % index
                    if _repo_relative_path_error(raw_path):
                        # The root-independent structural pass already emitted
                        # the precise failure for this value.
                        continue
                    resolved, resolve_error = _resolve_under_root(root, raw_path)
                    if resolve_error:
                        path_bad += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION, "proof-path-invalid",
                            target, "fail",
                            "path %r recorded in %s is invalid: %s"
                            % (raw_path, field, resolve_error), seq))
                    elif not resolved.is_file():
                        path_bad += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION, "proof-path-missing",
                            target, "fail",
                            "path %r recorded in %s is not a regular file "
                            "under root %s (K12/15 requires recorded path "
                            "references to be resolvable files)" %
                            (raw_path, field, root), seq))

            if ("selected_profile_manifest" not in missing and
                    not _selected_profile_manifest_error(
                        selected_profile_manifest)):
                manifest_path, manifest_resolve_error = _resolve_under_root(
                    root, selected_profile_manifest
                )
                if (not manifest_resolve_error and manifest_path.is_file()):
                    defaults_path, defaults_resolve_error = _resolve_under_root(
                        root, EXECUTION_DEFAULTS_PATH
                    )
                    try:
                        if defaults_resolve_error or not defaults_path.is_file():
                            raise OSError(
                                defaults_resolve_error or
                                "required defaults registry is missing"
                            )
                        defaults = kblib.parse_yaml_subset(
                            defaults_path.read_text(encoding="utf-8")
                        )
                        manifest_text = manifest_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError,
                            kblib.YamlSubsetError) as exc:
                        profile_manifest_bad += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION,
                            "proof-profile-identity-unreadable",
                            "%s#selected_profile_manifest" % proof_name,
                            "fail",
                            "cannot validate the selected profile identity: %s"
                            % exc, seq))
                    else:
                        reserved_ids = (
                            defaults.get("reserved_profile_ids") or []
                            if isinstance(defaults, dict) else []
                        )
                        selected_profile_id, identity_errors = (
                            kblib.profile_identity(
                                manifest_text,
                                Path(selected_profile_manifest).parts[1],
                                reserved_ids
                            )
                        )
                        for check, details in identity_errors:
                            profile_manifest_bad += 1
                            seq += 1
                            receipts.append(kblib.make_receipt(
                                TOOL, TOOL_VERSION,
                                "proof-%s" % check,
                                "%s#selected_profile_manifest" % proof_name,
                                "fail", details, seq))
                        if not identity_errors:
                            profile_identity_checked = True
                            profile_check_path = root / "Tools/check_profile.py"
                            try:
                                declared_profile_dir = (
                                    root / Path(selected_profile_manifest).parent
                                )
                                completed = subprocess.run(
                                    [sys.executable, str(profile_check_path),
                                     str(declared_profile_dir), "--root",
                                     str(root)],
                                    capture_output=True, text=True, timeout=60,
                                    check=False,
                                )
                            except (OSError, subprocess.TimeoutExpired) as exc:
                                completed = None
                                profile_manifest_bad += 1
                                seq += 1
                                receipts.append(kblib.make_receipt(
                                    TOOL, TOOL_VERSION,
                                    "proof-profile-check-unavailable",
                                    "%s#selected_profile_manifest" % proof_name,
                                    "fail", "cannot run check_profile.py: %s" %
                                    exc, seq))
                            if completed is not None:
                                if completed.returncode == 0:
                                    profile_manifest_checked = True
                                else:
                                    profile_manifest_bad += 1
                                    output_lines = [
                                        line.strip()
                                        for line in (completed.stdout + "\n" +
                                                     completed.stderr).splitlines()
                                        if line.strip()
                                    ]
                                    detail = (output_lines[-1]
                                              if output_lines else
                                              "no diagnostic output")
                                    seq += 1
                                    receipts.append(kblib.make_receipt(
                                        TOOL, TOOL_VERSION,
                                        "proof-profile-not-loadable",
                                        "%s#selected_profile_manifest" %
                                        proof_name, "fail",
                                        "check_profile.py exited %d: %s" %
                                        (completed.returncode, detail), seq))

            if profile_identity_checked:
                expected_prefix = "P:%s:" % selected_profile_id
                for index, route_id in enumerate(profile_route_ids or []):
                    if (isinstance(route_id, str) and
                            PROFILE_ROUTE_ID_RE.fullmatch(route_id) and
                            not route_id.startswith(expected_prefix)):
                        profile_route_id_bad += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION,
                            "proof-profile-route-id-mismatch",
                            "%s#selected_profile_route_ids[%d]" %
                            (proof_name, index), "fail",
                            "profile route ID %r belongs to another profile; "
                            "the selected manifest declares profile_id %r" %
                            (route_id, selected_profile_id), seq))

                selected_profile_dir = Path(selected_profile_manifest).parts[1]
                for field in ("selected_read_sets", "loaded_module_paths"):
                    value = proof.get(field)
                    values = value if isinstance(value, list) else [value]
                    for index, raw_path in enumerate(values):
                        if not isinstance(raw_path, str):
                            continue
                        parts = Path(raw_path).parts
                        if (len(parts) >= 3 and parts[0] == "profiles" and
                                parts[1] != selected_profile_dir):
                            profile_manifest_bad += 1
                            seq += 1
                            receipts.append(kblib.make_receipt(
                                TOOL, TOOL_VERSION,
                                "proof-profile-path-mismatch",
                                "%s#%s[%d]" % (proof_name, field, index),
                                "fail", "profile-owned path %r belongs to %r, "
                                "but selected_profile_manifest chooses %r" %
                                (raw_path, parts[1], selected_profile_dir),
                                seq))

            card_map, read_map, registry_errors = _load_route_registry(root)
            registry_bad = len(registry_errors)
            for index, details in enumerate(registry_errors):
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "proof-route-registry-invalid",
                    "%s#route_registry[%d]" % (proof_name, index), "fail",
                    details, seq))

            # Registry-dependent proof checks only run against a structurally
            # sound index pair. stamp_cards.py remains the full Card-layer
            # verifier; this check owns only the proof-to-registry binding.
            if not registry_errors:
                registry_checked = True
                selected_card_set = set(valid_card_paths)
                expected_card_set = {
                    card_map[route_id]["path"]
                    for route_id in valid_route_ids
                    if route_id in card_map
                }
                for card_path in sorted(expected_card_set - selected_card_set):
                    card_path_bad += 1
                    route_id = next(
                        route for route, entry in card_map.items()
                        if entry["path"] == card_path)
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-card-path-missing-for-route",
                        "%s#selected_card_paths" % proof_name, "fail",
                        "selected route %s requires canonical Card path %s"
                        % (route_id, card_path), seq))
                for card_path in sorted(selected_card_set - expected_card_set):
                    card_path_bad += 1
                    registered_route = next(
                        (route for route, entry in card_map.items()
                         if entry["path"] == card_path), None)
                    if registered_route:
                        details = (
                            "Card path %s is registered to %s, which is not in "
                            "selected_route_ids" % (card_path, registered_route))
                    else:
                        details = "Card path %s is not registered" % card_path
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "proof-card-route-mismatch",
                        "%s#selected_card_paths" % proof_name, "fail",
                        details, seq))

                read_set_to_route = {
                    entry["path"]: route_id
                    for route_id, entry in read_map.items()
                }
                for read_set_path in valid_read_set_paths:
                    if read_set_path.startswith("kernel/Read Sets/"):
                        registered_route = read_set_to_route.get(read_set_path)
                        if registered_route is None:
                            read_set_bad += 1
                            seq += 1
                            receipts.append(kblib.make_receipt(
                                TOOL, TOOL_VERSION,
                                "proof-kernel-read-set-unregistered",
                                "%s#selected_read_sets" % proof_name, "fail",
                                "kernel Read Set path %s is not registered in %s"
                                % (read_set_path, READ_SET_INDEX_PATH), seq))
                        elif registered_route not in valid_route_ids:
                            read_set_bad += 1
                            seq += 1
                            receipts.append(kblib.make_receipt(
                                TOOL, TOOL_VERSION,
                                "proof-read-set-route-mismatch",
                                "%s#selected_read_sets" % proof_name, "fail",
                                "Read Set path %s belongs to %s, which is not "
                                "in selected_route_ids"
                                % (read_set_path, registered_route), seq))
                    elif read_set_path.startswith("profiles/"):
                        if not valid_profile_route_ids:
                            read_set_bad += 1
                            seq += 1
                            receipts.append(kblib.make_receipt(
                                TOOL, TOOL_VERSION,
                                "proof-profile-read-set-without-route",
                                "%s#selected_read_sets" % proof_name, "fail",
                                "profile Read Set path %s requires at least one "
                                "selected_profile_route_ids entry; exact "
                                "route-to-path mapping remains a manual check "
                                "because the profile registry is prose"
                                % read_set_path, seq))
                    else:
                        read_set_bad += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION,
                            "proof-read-set-path-outside-registry",
                            "%s#selected_read_sets" % proof_name, "fail",
                            "Read Set path %s is neither a canonical kernel "
                            "Read Set nor a profile supplemental Read Set"
                            % read_set_path, seq))

    progress_cross_fail = 0
    if args.root and not args.progress_ledger:
        progress_cross_fail += 1
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "progress-ledger-required", proof_name,
            "fail", "--progress-ledger is required with --root; without the "
            "frozen Task Contract snapshot this run cannot support complete",
            seq))

    if args.progress_ledger:
        try:
            progress_ledger = kblib.parse_yaml_subset(
                open(args.progress_ledger, encoding="utf-8").read()
            )
        except (OSError, kblib.YamlSubsetError) as exc:
            progress_cross_fail += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "progress-ledger-unreadable",
                args.progress_ledger, "fail",
                "cannot read/parse Progress Ledger: %s" % exc, seq))
            progress_ledger = None

        if isinstance(progress_ledger, dict):
            progress_contract = progress_ledger.get("contract")
            if not isinstance(progress_contract, dict):
                progress_cross_fail += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "progress-contract-missing",
                    "%s#contract" % os.path.basename(args.progress_ledger),
                    "fail", "Progress Ledger must contain a contract mapping "
                    "with the frozen Standards version and profile selection",
                    seq))
            else:
                for field in ("standards_version",
                              "selected_profile_manifest"):
                    ledger_value = progress_contract.get(field)
                    target = "%s#contract.%s" % (
                        os.path.basename(args.progress_ledger), field
                    )
                    invalid = _uninstantiated_value(ledger_value)
                    if (field == "selected_profile_manifest" and
                            not invalid and
                            _selected_profile_manifest_error(ledger_value)):
                        invalid = True
                    if invalid:
                        progress_cross_fail += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION,
                            "progress-contract-field-invalid", target,
                            "fail", "%s must be a non-empty canonical string "
                            "in the frozen Progress Ledger contract" % field,
                            seq))
                    elif ledger_value != proof.get(field):
                        progress_cross_fail += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION,
                            "proof-progress-contract-mismatch", target,
                            "fail", "Progress Ledger %s=%r does not exactly "
                            "match Terminal Proof %s=%r" %
                            (field, ledger_value, field, proof.get(field)),
                            seq))
        elif progress_ledger is not None:
            progress_cross_fail += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "progress-ledger-not-mapping",
                args.progress_ledger, "fail",
                "Progress Ledger root must be a mapping", seq))

    coverage_cross_fail = 0
    if args.ledger:
        try:
            ledger = kblib.parse_yaml_subset(open(args.ledger, encoding="utf-8").read())
        except (OSError, kblib.YamlSubsetError) as exc:
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "ledger-unreadable", args.ledger, "fail",
                "cannot read/parse Coverage Ledger: %s" % exc, seq))
            ledger = None
        if isinstance(ledger, dict):
            open_gaps = ledger.get("open_gaps") or []
            gaps_claim = proof.get("required_authoring_gaps")
            if open_gaps and gaps_claim == 0:
                coverage_cross_fail += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "proof-ledger-mismatch",
                    "%s#required_authoring_gaps" % proof_name, "fail",
                    "Coverage Ledger open_gaps has %d unclosed gap(s), but the "
                    "proof claims required_authoring_gaps=0 (K02/03: the "
                    "Coverage Ledger is the authoritative record)"
                    % len(open_gaps), seq))

    if not any(r["result"] == "fail" for r in receipts):
        route_summary = (
            ", selected routes/Card paths and kernel Read Set readbacks "
            "match the canonical indexes" if registry_checked else
            ", route and path-list structure valid; registry cross-check "
            "not run because --root was not supplied")
        profile_summary = (
            ", %d supplemental profile route(s) recorded; profile "
            "route-to-path mapping remains a manual check"
            % len(valid_profile_route_ids)
            if valid_profile_route_ids else
            ", no supplemental profile route recorded")
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-check-summary", proof_name, "pass",
            "fields complete (%d/%d), all zero-condition fields are 0%s%s%s%s%s" % (
                len(required_fields), len(required_fields),
                route_summary, profile_summary,
                ", consistent with the active K00/03 Standards state"
                if active_state_checked else "",
                ", consistent with the frozen Progress Ledger contract"
                if args.progress_ledger else "",
                ", consistent with Coverage Ledger open_gaps"
                if args.ledger else ""), seq))

    print("check_proof: checking %s against %d required template field(s)" % (args.proof, len(required_fields)))
    print("  missing_fields=%d route_id_violations=%d "
          "profile_route_id_violations=%d card_path_violations=%d "
          "read_set_violations=%d registry_violations=%d "
          "path_structure_violations=%d "
          "frozen_field_violations=%d profile_manifest_violations=%d "
          "active_state_violations=%d "
          "zero_condition_violations=%d status_violations=%d "
          "path_failures=%d extra_fields(candidate)=%d "
          "progress_cross_failures=%d coverage_cross_failures=%d "
          "registry_cross_check=%s active_state_check=%s "
          "profile_manifest_check=%s"
          % (len(missing), route_id_bad, profile_route_id_bad, card_path_bad,
             read_set_bad, registry_bad, path_structure_bad,
             frozen_string_bad, profile_manifest_bad, active_state_bad,
             len(zero_bad),
             len(status_bad), path_bad, len(extra), progress_cross_fail,
             coverage_cross_fail,
             "passed" if registry_checked else
             ("failed" if args.root else "not_run"),
             "passed" if active_state_checked else
             ("failed" if args.root else "not_run"),
             "passed" if profile_manifest_checked else
             ("failed" if args.root else "not_run")))
    for r in receipts:
        if r["result"] != "pass":
            print("  [%s %s] %s — %s" % (r["result"].upper()[:4], r["check"],
                                         r["target"], r["details"]))
    if not any(r["result"] == "fail" for r in receipts):
        if args.root:
            print("  Conclusion: Terminal Proof consistency check passed with "
                  "active Standards state, filled profile, frozen Progress "
                  "Ledger, and repository registry validation.")
        else:
            print("  Conclusion: structural lint passed; without --root this "
                  "is not Terminal Completion Gate evidence.")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
