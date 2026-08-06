#!/usr/bin/env python3
"""Terminal Proof completeness check script.

Rule owners:
- "kernel/K12 Quality Assurance/16 Terminal Proof Contract.md"
  (the complete Terminal Proof field list, including
   selected_route_ids, selected_card_paths, and full_deterministic_results);
- "kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md"
  (completion conditions: the three open guidance counts are 0,
   required_authoring_gaps=0, unverified_batches=0,
   unresolved_invalidations=0, and all applicable gates pass);
- "kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md"
  (Terminal Reconciliation Rules: unresolved_invalidations must be 0).
- "kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md"
  (the Queue path, structure/state revisions, byte fingerprint, completion
   receipt, and remaining Required work-unit count).

Method:
- The required-field list comes from the top-level keys of
  Tools/schemas/terminal_proof.template.yaml (the template copies K12/16 field
  by field as this script's machine-readable projection; K12/16 remains the
  normative field-list owner; --template overrides the projection path);
- a missing or empty proof field -> fail (Terminal Proof incomplete);
- selected_profile_manifest must be one exact
  profiles/<profile_id>/profile.md path; with --root its manifest identity is
  validated, check_profile.py must accept the filled profile, every profile
  path must stay within it, and every supplemental route must use its id;
- selected_route_ids must be a non-empty list of unique Runtime Route IDs in
  the closed range R01-R13 and, because this is terminal evidence, must include
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
  remaining_required_work_units / unresolved_invalidations) that is not 0 ->
  fail;
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
- --root requires an instantiated, approved K00/03 active state,
  --progress-ledger, and --ledger; the active state, frozen contract,
  Coverage, Queue, and Terminal Proof must carry the same task, scope,
  Standards, and profile identity, while Proof and Progress also agree on the
  contract version.  Proof records the exact Coverage, Progress, and Queue
  byte fingerprints, and a pass receipt also binds the Proof bytes.  The two
  Ledger arguments must identify the exact
  canonical files under .cambium/state/; aliases and symlinks are rejected.
  Progress must be completion-candidate or complete and contain no pending
  Guidance or Amendment.  The canonical Required Queue is
  then checked live in completion mode, and its revisions, SHA-256, remaining
  count, and current check_queue receipt must match the proof and Progress
  Ledger.

This script verifies local proof consistency, not the work itself or the
provenance of the evidence: a proof can still lie consistently. Producer and
version fields are declared labels, actor/reviewer fields are assertions, and
SHA-256 values bind bytes without authenticating the executable, OS principal,
or human that produced them. Without an external signature or controlled
execution attestation, a writer who controls the repository, tools, and
evidence can construct an internally consistent history. K12/15 owns the human
audit and K12/16 owns the proof contract and trust boundary.

Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_proof.py <proof.yaml> [--ledger coverage_ledger.yaml]
       [--root REPOSITORY_ROOT
        --progress-ledger .cambium/state/progress_ledger.yaml
        --ledger .cambium/state/coverage_ledger.yaml]
       [--template PATH] [--receipts PATH]
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import check_corpus_plan
import check_queue

TOOL = "check_proof"
TOOL_VERSION = "1.14.0"
GATE_ID = "terminal-proof"


def _make_receipt(tool, tool_version, check, target, result, details, seq):
    """Build one producer-era proof receipt with its stable Gate ID."""
    if tool != TOOL or tool_version != TOOL_VERSION:
        raise ValueError("check_proof receipt producer identity drift")
    receipt = kblib.make_receipt(
        tool, tool_version, check, target, result, details, seq)
    receipt["gate_id"] = GATE_ID
    return receipt

# K12/06: fields that must be 0 among the completion conditions (the three open
# guidance counts are covered by the review of guidance_reconciliation_result
# and get no numeric assertion here)
ZERO_FIELDS = ("required_authoring_gaps", "unverified_batches",
               "remaining_required_work_units", "unresolved_invalidations")

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
               "required_queue_path",
               "audit_receipt_register", "full_deterministic_results",
               "incremental_manual_scope")

# Kernel Runtime Route IDs are a closed registry. Index documents do not occupy
# R00; the thirteen executable routes are R01-R13.
RUNTIME_ROUTE_ID_RE = re.compile(r"R(?:0[1-9]|1[0-3])\Z")
PROFILE_ROUTE_ID_RE = re.compile(r"P:[^:\s]+:[^:\s]+\Z")
EXPECTED_ROUTE_IDS = tuple("R%02d" % number for number in range(1, 14))
TERMINAL_REQUIRED_ROUTE_IDS = frozenset(("R01", "R08", "R12"))
REGISTRY_ID = "kernel-runtime-routes"
CARD_INDEX_PATH = "kernel/Cards/Card Index.md"
READ_SET_INDEX_PATH = "kernel/Read Sets/Read Sets Index.md"
EXECUTION_DEFAULTS_PATH = "Tools/schemas/execution_defaults.template.yaml"
ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
UNINSTANTIATED_RE = re.compile(r"\{\{.*?\}\}")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
CANONICAL_COVERAGE_PATH = ".cambium/state/coverage_ledger.yaml"
CANONICAL_QUEUE_PATH = ".cambium/state/required_queue.yaml"
CANONICAL_PROGRESS_PATH = ".cambium/state/progress_ledger.yaml"
NULLABLE_REQUIRED_FIELDS = frozenset((
    "corpus_plan_semantic_acceptance_receipt",
))
TERMINAL_TASK_STATES = frozenset(("completion-candidate", "complete"))
FINAL_GUIDANCE_STATUSES = frozenset(
    ("verified", "deferred", "superseded", "not-applicable")
)


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


def _canonical_state_argument(root, raw_path, canonical_relative):
    """Resolve one CLI state argument to its sole canonical runtime object.

    Terminal validation is not allowed to substitute a caller-selected Ledger
    that merely has plausible bytes.  Relative arguments therefore name the
    exact repository-relative contract path; absolute arguments are accepted
    only when they are the exact lexical absolute path to that same object.
    Symlinks in any managed component are rejected even when they resolve back
    inside the repository.
    """
    root = Path(root).resolve()
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, "path must be a non-empty string"
    if raw_path != raw_path.strip():
        return None, "path must not have leading or trailing whitespace"

    supplied = Path(raw_path)
    expected = root / Path(canonical_relative)
    if ".." in supplied.parts:
        return None, "'..' segments are forbidden"
    if supplied.is_absolute():
        if supplied != expected:
            return None, "must be exactly %s" % expected
        candidate = supplied
    else:
        if supplied.as_posix() != canonical_relative:
            return None, "must be exactly %s" % canonical_relative
        candidate = root / supplied

    current = root
    for component in Path(canonical_relative).parts:
        current = current / component
        if current.is_symlink():
            return None, "canonical state path contains symlink component %s" % current
    try:
        if not candidate.is_file():
            return None, "canonical state object is not a regular file"
        if candidate.resolve(strict=True) != expected:
            return None, "canonical state object does not resolve to %s" % expected
    except (OSError, RuntimeError, ValueError) as exc:
        return None, "canonical state object cannot be resolved: %s" % exc
    return candidate, None


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
            errors.append("%s has invalid route_id %r; expected R01-R13" %
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
            "%s route coverage must be exactly R01-R13; missing=%s extra=%s"
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


def _queue_linkage_failure(check, target, details):
    """Return one check_proof failure tuple for Queue linkage validation."""
    return check, target, details


def _catalog_receipt(catalog, receipt_id):
    """Return one receipt mapping from a check_queue catalog entry."""
    entry = catalog.get(receipt_id) if isinstance(catalog, dict) else None
    if (isinstance(entry, tuple) and len(entry) == 2 and
            isinstance(entry[1], dict)):
        return entry[1]
    if isinstance(entry, dict):
        return entry
    return None


def _current_receipt_evidence(root, receipt_id, *, field, check_prefix,
                              runtime=None):
    """Resolve a new proof decision only through the current receipt view.

    Standards adoption deliberately keeps the full receipt catalog available
    for verifying immutable history while removing invalidated evidence from the
    current-use catalog.  Terminal Proof is a new completion decision, so it
    must never fall back to the historical catalog when the filtered view is
    missing or empty.
    """
    if runtime is None:
        runtime = check_queue.validate_runtime(str(Path(root).resolve()))
    current = check_queue.current_receipt_catalog(runtime)
    invalidated = set(
        runtime.get("invalidated_evidence_receipt_ids") or [])
    target = "Terminal Proof#%s" % field
    if receipt_id in invalidated:
        return None, [_queue_linkage_failure(
            "%s-invalidated-evidence" % check_prefix, target,
            "%s is listed as invalidated evidence by the current Standards "
            "adoption and cannot support a new Terminal Proof" % field,
        )]
    receipt = _catalog_receipt(current, receipt_id)
    if receipt is None:
        return None, [_queue_linkage_failure(
            "%s-not-current" % check_prefix, target,
            "%s %r is absent from the adoption-filtered current receipt "
            "catalog; historical evidence is not a fallback" %
            (field, receipt_id),
        )]
    return receipt, []


def _reused_receipt_evidence_failures(root, proof, runtime=None):
    """Require every explicitly reused receipt to remain current evidence."""
    failures = []
    reused = proof.get("reused_receipts")
    if not isinstance(reused, list):
        return [_queue_linkage_failure(
            "proof-reused-receipts-invalid", "Terminal Proof#reused_receipts",
            "reused_receipts must be an explicit list",
        )]
    seen = set()
    for index, value in enumerate(reused):
        if isinstance(value, str):
            receipt_id = value
        elif isinstance(value, dict):
            receipt_id = value.get("receipt_id")
        else:
            receipt_id = None
        target = "Terminal Proof#reused_receipts[%d]" % index
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            failures.append(_queue_linkage_failure(
                "proof-reused-receipt-id-invalid", target,
                "each reused_receipts entry must identify a non-empty "
                "receipt_id",
            ))
            continue
        if receipt_id in seen:
            failures.append(_queue_linkage_failure(
                "proof-reused-receipt-duplicate", target,
                "reused receipt_id %r appears more than once" % receipt_id,
            ))
            continue
        seen.add(receipt_id)
        _, membership_failures = _current_receipt_evidence(
            root, receipt_id, field="reused_receipts[%d]" % index,
            check_prefix="proof-reused-receipt", runtime=runtime,
        )
        failures.extend(membership_failures)
    return failures


def _validate_required_queue_linkage(root, proof, progress_ledger,
                                     coverage_sha256,
                                     proof_progress_sha256):
    """Validate the live Required Queue evidence bound into Terminal Proof.

    The Queue location is deliberately not caller-selectable.  ``--root``
    means that completion evidence is checked against the canonical runtime
    object at ``.cambium/state/required_queue.yaml`` even when a malformed
    proof attempts to name another path.  The return value is
    ``(failures, live_check_passed)``; every failure is a
    ``(check, target, details)`` tuple suitable for a check_proof receipt.
    """
    failures = []
    root = Path(root).resolve()
    adoption_runtime = check_queue.validate_runtime(str(root))
    queue_path, queue_path_error = _canonical_state_argument(
        root, CANONICAL_QUEUE_PATH, CANONICAL_QUEUE_PATH
    )
    queue = None
    queue_sha256 = None
    remaining = None

    if queue_path_error or not queue_path.is_file():
        failures.append(_queue_linkage_failure(
            "proof-required-queue-unreadable", CANONICAL_QUEUE_PATH,
            "canonical Required Queue is missing or unsafe: %s" %
            (queue_path_error or "not a regular file"),
        ))
    else:
        try:
            queue_bytes = queue_path.read_bytes()
            queue_text = queue_bytes.decode("utf-8")
            queue = kblib.parse_yaml_subset(queue_text)
        except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
            failures.append(_queue_linkage_failure(
                "proof-required-queue-unreadable", CANONICAL_QUEUE_PATH,
                "cannot read/parse the canonical Required Queue: %s" % exc,
            ))
        else:
            if not isinstance(queue, dict):
                failures.append(_queue_linkage_failure(
                    "proof-required-queue-not-mapping", CANONICAL_QUEUE_PATH,
                    "canonical Required Queue top level must be a mapping",
                ))
                queue = None
            else:
                queue_sha256 = kblib.sha256_bytes(queue_bytes)
                items = queue.get("required_queue")
                if not isinstance(items, list):
                    failures.append(_queue_linkage_failure(
                        "proof-required-queue-items-invalid",
                        CANONICAL_QUEUE_PATH + "#required_queue",
                        "required_queue must be an explicit list",
                    ))
                else:
                    remaining = sum(
                        1 for item in items
                        if (not isinstance(item, dict) or
                            item.get("state") not in ("closed", "cancelled"))
                    )

    if queue is not None:
        queue_expected = {
            "task_id": queue.get("task_id"),
            "scope_version": queue.get("scope_version"),
            "standards_version": queue.get("standards_version"),
            "selected_profile_manifest":
                queue.get("selected_profile_manifest"),
            "required_queue_path": CANONICAL_QUEUE_PATH,
            "queue_revision": queue.get("queue_revision"),
            "queue_state_revision": queue.get("state_revision"),
            "required_queue_sha256": queue_sha256,
            "remaining_required_work_units": remaining,
        }
        for field, expected in queue_expected.items():
            if proof.get(field) != expected:
                failures.append(_queue_linkage_failure(
                    "proof-required-queue-mismatch", "Terminal Proof#" + field,
                    "Terminal Proof %s=%r does not match the canonical "
                    "Required Queue value %r" %
                    (field, proof.get(field), expected),
                ))

        if not isinstance(progress_ledger, dict):
            failures.append(_queue_linkage_failure(
                "proof-queue-progress-unavailable", "Progress Ledger",
                "a parsed Progress Ledger mapping is required to bind "
                "Terminal Proof to the canonical Required Queue",
            ))
        else:
            progress_contract = progress_ledger.get("contract")
            if not isinstance(progress_contract, dict):
                progress_contract = {}
            progress_expected = {
                "task_id": progress_ledger.get("task_id"),
                "scope_version": progress_contract.get("scope_version"),
                "standards_version":
                    progress_contract.get("standards_version"),
                "selected_profile_manifest":
                    progress_contract.get("selected_profile_manifest"),
                "required_queue_path":
                    progress_ledger.get("required_queue_path"),
                "queue_revision": progress_ledger.get("queue_revision"),
                "queue_state_revision":
                    progress_ledger.get("queue_state_revision"),
                "required_queue_sha256":
                    progress_ledger.get("required_queue_sha256"),
            }
            current_expected = {
                "task_id": queue.get("task_id"),
                "scope_version": queue.get("scope_version"),
                "standards_version": queue.get("standards_version"),
                "selected_profile_manifest":
                    queue.get("selected_profile_manifest"),
                "required_queue_path": CANONICAL_QUEUE_PATH,
                "queue_revision": queue.get("queue_revision"),
                "queue_state_revision": queue.get("state_revision"),
                "required_queue_sha256": queue_sha256,
            }
            for field, actual in progress_expected.items():
                expected = current_expected[field]
                if actual != expected:
                    failures.append(_queue_linkage_failure(
                        "progress-required-queue-mismatch",
                        "Progress Ledger#" + field,
                        "Progress Ledger %s=%r does not match the canonical "
                        "Required Queue value %r" % (field, actual, expected),
                    ))

    # Completion is not inferred from the proof's counters.  Re-run the one
    # canonical Queue gate over the current repository bytes.
    live_check_passed = False
    checker_path, checker_path_error = _resolve_under_root(
        root, "Tools/check_queue.py"
    )
    if checker_path_error or not checker_path.is_file():
        failures.append(_queue_linkage_failure(
            "proof-queue-live-check-unavailable", "Tools/check_queue.py",
            "canonical Queue checker is missing or unsafe: %s" %
            (checker_path_error or "not a regular file"),
        ))
    else:
        try:
            completed = subprocess.run(
                [sys.executable, str(checker_path), str(root),
                 "--require-complete"],
                cwd=str(root), capture_output=True, text=True, timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(_queue_linkage_failure(
                "proof-queue-live-check-unavailable", "Tools/check_queue.py",
                "cannot run the canonical Queue completion gate: %s" % exc,
            ))
        else:
            if completed.returncode != 0:
                output_lines = [
                    line.strip()
                    for line in (completed.stdout + "\n" +
                                 completed.stderr).splitlines()
                    if line.strip()
                ]
                detail = (" | ".join(output_lines[-3:])
                          if output_lines else "no diagnostic output")
                failures.append(_queue_linkage_failure(
                    "proof-queue-live-check-failed", "Tools/check_queue.py",
                    "check_queue.py --require-complete exited %d: %s" %
                    (completed.returncode, detail),
                ))
            else:
                live_check_passed = True

    # The cited receipt is immutable evidence for the exact bytes just
    # checked.  A missing, malformed, duplicated, invalidated, or stale receipt
    # fails closed even when a fresh live run happens to pass.
    receipt_path_raw = proof.get("audit_receipt_register")
    receipt_id = proof.get("queue_check_receipt")
    current_receipt, membership_failures = _current_receipt_evidence(
        root, receipt_id, field="queue_check_receipt",
        check_prefix="proof-queue-receipt", runtime=adoption_runtime,
    )
    failures.extend(membership_failures)
    try:
        receipt_path = Path(kblib.managed_repository_path(
            str(root), receipt_path_raw, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=True,
        ))
        receipt_path_error = None
    except (OSError, TypeError, ValueError) as exc:
        receipt_path = None
        receipt_path_error = str(exc)
    matching_receipts = []
    if receipt_path_error or receipt_path is None or not receipt_path.is_file():
        failures.append(_queue_linkage_failure(
            "proof-queue-receipt-register-unreadable",
            str(receipt_path_raw),
            "audit_receipt_register is missing or unsafe: %s" %
            (receipt_path_error or "not a regular file"),
        ))
    else:
        try:
            receipt_lines = receipt_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            failures.append(_queue_linkage_failure(
                "proof-queue-receipt-register-unreadable",
                str(receipt_path_raw),
                "cannot read audit_receipt_register: %s" % exc,
            ))
        else:
            seen_receipt_ids = set()
            register_reliable = True
            for line_number, line in enumerate(receipt_lines, 1):
                if not line.strip():
                    continue
                try:
                    receipt = json.loads(line)
                except json.JSONDecodeError as exc:
                    register_reliable = False
                    failures.append(_queue_linkage_failure(
                        "proof-queue-receipt-register-invalid",
                        "%s:%d" % (receipt_path_raw, line_number),
                        "malformed JSONL receipt: %s" % exc,
                    ))
                    continue
                if not isinstance(receipt, dict):
                    register_reliable = False
                    failures.append(_queue_linkage_failure(
                        "proof-queue-receipt-register-invalid",
                        "%s:%d" % (receipt_path_raw, line_number),
                        "receipt line must be a JSON object",
                    ))
                    continue
                current_id = receipt.get("receipt_id")
                if current_id in seen_receipt_ids:
                    register_reliable = False
                    failures.append(_queue_linkage_failure(
                        "proof-queue-receipt-id-duplicate",
                        "%s:%d" % (receipt_path_raw, line_number),
                        "receipt_id %r appears more than once" % current_id,
                    ))
                seen_receipt_ids.add(current_id)
                if current_id == receipt_id:
                    matching_receipts.append(receipt)

            if register_reliable and len(matching_receipts) != 1:
                failures.append(_queue_linkage_failure(
                    "proof-queue-receipt-missing", str(receipt_path_raw),
                    "queue_check_receipt %r must identify exactly one receipt; "
                    "found %d" % (receipt_id, len(matching_receipts)),
                ))

    if len(matching_receipts) == 1 and queue is not None:
        receipt = matching_receipts[0]
        if current_receipt is not None and receipt != current_receipt:
            failures.append(_queue_linkage_failure(
                "proof-queue-receipt-catalog-mismatch",
                "%s#%s" % (receipt_path_raw, receipt_id),
                "the named register record differs from the same receipt_id "
                "in the current receipt catalog",
            ))
        for field, expected in (
                ("tool", "check_queue"),
                ("tool_version", check_queue.TOOL_VERSION),
                ("gate_id", "required-queue-completion"),
                ("check", "required_queue"),
                ("queue_check_mode", "require-complete"),
                ("result", "pass"),
                ("invalidated_by", None),
                ("task_id", queue.get("task_id")),
                ("queue_revision", queue.get("queue_revision")),
                ("queue_state_revision", queue.get("state_revision")),
                ("required_queue_sha256", queue_sha256),
                ("coverage_ledger_sha256", coverage_sha256),
                ("progress_ledger_sha256", proof_progress_sha256),
                ("remaining_required_work_units", remaining)):
            if field not in receipt or receipt.get(field) != expected:
                failures.append(_queue_linkage_failure(
                    "proof-queue-receipt-stale",
                    "%s#%s" % (receipt_path_raw, receipt_id),
                    "Queue receipt %s=%r does not match required current "
                    "value %r" % (field, receipt.get(field), expected),
                ))

    return failures, live_check_passed


def _validate_corpus_plan_linkage(root, proof, proof_progress_sha256):
    """Consume one current Corpus Planning receipt at Terminal Proof.

    The named receipt must live in the Proof's canonical audit register and
    bind the exact selected Profile, slot, three configured artifacts (or
    explicit inactive nulls), canonical runtime bytes, and current repository
    snapshot.  Re-running only a live check without consuming this persisted
    receipt is insufficient terminal evidence.
    """
    failures = []
    root = Path(root).resolve()
    receipt_path_raw = proof.get("audit_receipt_register")
    receipt_id = proof.get("corpus_plan_check_receipt")
    adoption_runtime = check_queue.validate_runtime(str(root))
    current_structural, membership_failures = _current_receipt_evidence(
        root, receipt_id, field="corpus_plan_check_receipt",
        check_prefix="proof-corpus-plan-receipt",
        runtime=adoption_runtime,
    )
    failures.extend(membership_failures)
    try:
        receipt_path = Path(kblib.managed_repository_path(
            str(root), receipt_path_raw, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=True,
        ))
        receipt_path_error = None
    except (OSError, TypeError, ValueError) as exc:
        receipt_path = None
        receipt_path_error = str(exc)
    if receipt_path_error or receipt_path is None or not receipt_path.is_file():
        return [(_queue_linkage_failure(
            "proof-corpus-plan-receipt-register-unreadable",
            str(receipt_path_raw),
            "audit_receipt_register is missing or unsafe: %s" %
            (receipt_path_error or "not a regular file")))], False

    matches = []
    semantic_id = proof.get("corpus_plan_semantic_acceptance_receipt")
    semantic_matches = []
    seen = set()
    register_reliable = True
    try:
        lines = receipt_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [(_queue_linkage_failure(
            "proof-corpus-plan-receipt-register-unreadable",
            str(receipt_path_raw),
            "cannot read audit_receipt_register: %s" % exc))], False
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            receipt = json.loads(line)
        except json.JSONDecodeError as exc:
            register_reliable = False
            failures.append(_queue_linkage_failure(
                "proof-corpus-plan-receipt-register-invalid",
                "%s:%d" % (receipt_path_raw, line_number),
                "malformed JSONL receipt: %s" % exc))
            continue
        if not isinstance(receipt, dict):
            register_reliable = False
            failures.append(_queue_linkage_failure(
                "proof-corpus-plan-receipt-register-invalid",
                "%s:%d" % (receipt_path_raw, line_number),
                "receipt line must be a JSON object"))
            continue
        current_id = receipt.get("receipt_id")
        if current_id in seen:
            register_reliable = False
            failures.append(_queue_linkage_failure(
                "proof-corpus-plan-receipt-id-duplicate",
                "%s:%d" % (receipt_path_raw, line_number),
                "receipt_id %r appears more than once" % current_id))
        seen.add(current_id)
        if current_id == receipt_id:
            matches.append(receipt)
        if semantic_id is not None and current_id == semantic_id:
            semantic_matches.append(receipt)
    if register_reliable and len(matches) != 1:
        failures.append(_queue_linkage_failure(
            "proof-corpus-plan-receipt-missing", str(receipt_path_raw),
            "corpus_plan_check_receipt %r must identify exactly one receipt; "
            "found %d" % (receipt_id, len(matches))))
    if len(matches) != 1:
        return failures, False

    if current_structural is not None and matches[0] != current_structural:
        failures.append(_queue_linkage_failure(
            "proof-corpus-plan-receipt-catalog-mismatch",
            "%s#%s" % (receipt_path_raw, receipt_id),
            "the named register record differs from the same receipt_id in "
            "the current receipt catalog"))

    try:
        snapshot = kblib.repository_snapshot_sha256(str(root))
    except (OSError, ValueError) as exc:
        failures.append(_queue_linkage_failure(
            "proof-corpus-plan-snapshot-unavailable", str(root), str(exc)))
        return failures, False
    try:
        expected_binding = check_corpus_plan.current_freshness_binding(
            str(root), proof.get("selected_profile_manifest"),
            task_id=proof.get("task_id"),
            queue_revision=proof.get("queue_revision"),
            queue_state_revision=proof.get("queue_state_revision"),
            coverage_ledger_sha256=proof.get("coverage_ledger_sha256"),
            required_queue_sha256=proof.get("required_queue_sha256"),
            progress_ledger_sha256=proof_progress_sha256,
            repository_snapshot_sha256=snapshot,
        )
    except (OSError, TypeError, ValueError) as exc:
        failures.append(_queue_linkage_failure(
            "proof-corpus-plan-live-binding-failed",
            "Tools/check_corpus_plan.py",
            "cannot resolve current Corpus Planning bytes: %s" % exc))
        return failures, False
    receipt_errors = check_corpus_plan.pass_receipt_errors(
        str(root), matches[0], expected_binding=expected_binding,
        require_runtime=True)
    for detail in receipt_errors:
        failures.append(_queue_linkage_failure(
            "proof-corpus-plan-receipt-stale",
            "%s#%s" % (receipt_path_raw, receipt_id), detail))

    applicability = expected_binding.get("corpus_plan_applicability")
    if applicability == "not-applicable":
        if semantic_id is not None:
            failures.append(_queue_linkage_failure(
                "proof-corpus-plan-semantic-receipt-not-applicable",
                "Terminal Proof#corpus_plan_semantic_acceptance_receipt",
                "semantic acceptance receipt must be null when the current "
                "Corpus Planning applicability.state is not-applicable"))
    elif applicability == "configured":
        if not isinstance(semantic_id, str) or not semantic_id.strip():
            failures.append(_queue_linkage_failure(
                "proof-corpus-plan-semantic-receipt-required",
                "Terminal Proof#corpus_plan_semantic_acceptance_receipt",
                "a configured Corpus Planning slot requires one current "
                "semantic-acceptance receipt"))
        else:
            current_semantic, semantic_membership_failures = \
                _current_receipt_evidence(
                    root, semantic_id,
                    field="corpus_plan_semantic_acceptance_receipt",
                    check_prefix="proof-corpus-plan-semantic-receipt",
                    runtime=adoption_runtime,
                )
            failures.extend(semantic_membership_failures)
            if len(semantic_matches) != 1:
                failures.append(_queue_linkage_failure(
                    "proof-corpus-plan-semantic-receipt-missing",
                    str(receipt_path_raw),
                    "corpus_plan_semantic_acceptance_receipt %r must "
                    "identify exactly one receipt; found %d" %
                    (semantic_id, len(semantic_matches))))
            else:
                semantic = semantic_matches[0]
                if current_semantic is not None and semantic != current_semantic:
                    failures.append(_queue_linkage_failure(
                        "proof-corpus-plan-semantic-receipt-catalog-mismatch",
                        "%s#%s" % (receipt_path_raw, semantic_id),
                        "the named register record differs from the same "
                        "receipt_id in the current receipt catalog"))
                for field, expected in (
                        ("tool", "record_corpus_acceptance"),
                        ("tool_version",
                         check_corpus_plan.SEMANTIC_ACCEPTANCE_TOOL_VERSION),
                        ("gate_id", "corpus-plan-semantic-acceptance"),
                        ("check", "corpus_plan_semantic_acceptance"),
                        ("result", "pass"),
                        ("invalidated_by", None),
                        ("structural_check_receipt", receipt_id)):
                    if semantic.get(field) != expected:
                        failures.append(_queue_linkage_failure(
                            "proof-corpus-plan-semantic-receipt-stale",
                            "%s#%s" % (receipt_path_raw, semantic_id),
                            "semantic receipt %s=%r, expected %r" %
                            (field, semantic.get(field), expected)))
                for field in check_corpus_plan.PASS_RECEIPT_BINDING_FIELDS:
                    expected = expected_binding.get(field)
                    if semantic.get(field) != expected:
                        failures.append(_queue_linkage_failure(
                            "proof-corpus-plan-semantic-receipt-stale",
                            "%s#%s" % (receipt_path_raw, semantic_id),
                            "semantic receipt %s=%r, expected %r" %
                            (field, semantic.get(field), expected)))
                decisions = semantic.get("capability_decisions")
                if (not isinstance(decisions, list) or not decisions or
                        any(not isinstance(row, dict) or
                            row.get("decision") != "accepted"
                            for row in decisions)):
                    failures.append(_queue_linkage_failure(
                        "proof-corpus-plan-semantic-receipt-rejected",
                        "%s#%s" % (receipt_path_raw, semantic_id),
                        "semantic receipt must contain a non-empty all-accepted "
                        "capability_decisions list"))
    return failures, not failures


def _terminal_progress_binding(root, progress_ledger, current_progress_sha256):
    """Return the Progress fingerprint that a durable proof must bind.

    A proof is created from frozen ``completion-candidate`` bytes.  The sole
    subsequent ``complete`` transition necessarily changes Progress.  In that
    terminal state the transition's receipt-recorded before-image remains the
    proof binding, while its after-image must equal current Progress bytes.
    """
    if (not isinstance(progress_ledger, dict) or
            progress_ledger.get("task_state") != "complete"):
        return current_progress_sha256, []
    runtime = check_queue.validate_runtime(str(root))
    if runtime.get("errors"):
        return current_progress_sha256, [(
            "complete-runtime-invalid", CANONICAL_PROGRESS_PATH,
            "complete runtime cannot establish the Terminal Proof transition: %s" %
            "; ".join(runtime["errors"]),
        )]
    latest = (runtime.get("task_runtime") or {}).get("latest_receipt")
    if (not isinstance(latest, dict) or
            latest.get("after_task_state") != "complete" or
            latest.get("after_progress_sha256") != current_progress_sha256 or
            not SHA256_RE.fullmatch(str(latest.get(
                "before_progress_sha256", "")))):
        return current_progress_sha256, [(
            "complete-transition-binding-invalid", CANONICAL_PROGRESS_PATH,
            "latest task transition must bind candidate Progress as before-image "
            "and current complete Progress as after-image",
        )]
    return latest["before_progress_sha256"], []


def _validate_terminal_progress_state(proof, progress_ledger,
                                      progress_sha256=None):
    """Require a terminal-candidate Progress state with no pending controls."""
    failures = []
    if not isinstance(progress_ledger, dict):
        return [(
            "progress-ledger-not-mapping", "Progress Ledger",
            "canonical Progress Ledger root must be a mapping",
        )]

    task_state = progress_ledger.get("task_state")
    if task_state not in TERMINAL_TASK_STATES:
        failures.append((
            "progress-task-state-not-terminal-candidate",
            "Progress Ledger#task_state",
            "Terminal Proof requires task_state completion-candidate or "
            "complete; found %r" % task_state,
        ))

    if (progress_sha256 is not None and
            proof.get("progress_ledger_sha256") != progress_sha256):
        failures.append((
            "proof-progress-fingerprint-mismatch",
            "Terminal Proof#progress_ledger_sha256",
            "Terminal Proof progress_ledger_sha256=%r does not match the "
            "canonical Progress Ledger bytes %r" %
            (proof.get("progress_ledger_sha256"), progress_sha256),
        ))

    contract = progress_ledger.get("contract")
    if not isinstance(contract, dict):
        failures.append((
            "progress-contract-missing", "Progress Ledger#contract",
            "canonical Progress Ledger must contain a contract mapping",
        ))
        contract = {}
    if contract.get("completion_semantics") != "build":
        failures.append((
            "progress-completion-semantics-not-build",
            "Progress Ledger#contract.completion_semantics",
            "Terminal Proof applies only to completion_semantics=build; "
            "maintenance tasks must use the maintenance completion gate",
        ))

    progress_values = {
        "task_id": progress_ledger.get("task_id"),
        "scope_version": contract.get("scope_version"),
        "contract_version": contract.get("contract_version"),
        "standards_version": contract.get("standards_version"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"
        ),
    }
    for field, actual in progress_values.items():
        expected = proof.get(field)
        if actual != expected:
            failures.append((
                "proof-progress-contract-mismatch",
                "Progress Ledger#%s" % (
                    field if field == "task_id" else "contract." + field
                ),
                "Progress Ledger %s=%r does not match Terminal Proof value "
                "%r" % (field, actual, expected),
            ))

    guidance = progress_ledger.get("guidance_queue")
    if not isinstance(guidance, list):
        failures.append((
            "progress-guidance-queue-invalid",
            "Progress Ledger#guidance_queue",
            "guidance_queue must be an explicit list",
        ))
    else:
        for index, entry in enumerate(guidance):
            if not isinstance(entry, dict):
                failures.append((
                    "progress-guidance-entry-invalid",
                    "Progress Ledger#guidance_queue[%d]" % index,
                    "guidance entry must be a mapping",
                ))
                continue
            status = entry.get("status")
            if status not in FINAL_GUIDANCE_STATUSES:
                failures.append((
                    "progress-guidance-pending",
                    "Progress Ledger#guidance_queue[%d]" % index,
                    "guidance %r has non-final status %r" %
                    (entry.get("guidance_id"), status),
                ))

    amendments = progress_ledger.get("amendments")
    if not isinstance(amendments, list):
        failures.append((
            "progress-amendments-invalid",
            "Progress Ledger#amendments",
            "amendments must be an explicit list",
        ))
    else:
        for index, entry in enumerate(amendments):
            if not isinstance(entry, dict):
                failures.append((
                    "progress-amendment-entry-invalid",
                    "Progress Ledger#amendments[%d]" % index,
                    "Amendment entry must be a mapping",
                ))
                continue
            status = entry.get("status")
            if status not in FINAL_GUIDANCE_STATUSES:
                failures.append((
                    "progress-amendment-pending",
                    "Progress Ledger#amendments[%d]" % index,
                    "Amendment %r has non-final status %r" %
                    (entry.get("id"), status),
                ))
            elif (status == "verified" and
                  entry.get("writeback_done") is not True):
                failures.append((
                    "progress-amendment-writeback-pending",
                    "Progress Ledger#amendments[%d]" % index,
                    "verified Amendment %r has not completed Progress "
                    "write-back" % entry.get("id"),
                ))
    return failures


def _validate_terminal_coverage_state(proof, progress_ledger, coverage_ledger,
                                      coverage_sha256=None):
    """Bind Terminal Proof to canonical Coverage identity and open-gap state."""
    failures = []
    if not isinstance(coverage_ledger, dict):
        return [(
            "coverage-ledger-not-mapping", "Coverage Ledger",
            "canonical Coverage Ledger root must be a mapping",
        )]

    if (coverage_sha256 is not None and
            proof.get("coverage_ledger_sha256") != coverage_sha256):
        failures.append((
            "proof-coverage-fingerprint-mismatch",
            "Terminal Proof#coverage_ledger_sha256",
            "Terminal Proof coverage_ledger_sha256=%r does not match the "
            "canonical Coverage Ledger bytes %r" %
            (proof.get("coverage_ledger_sha256"), coverage_sha256),
        ))

    progress_contract = (
        progress_ledger.get("contract")
        if isinstance(progress_ledger, dict) and
        isinstance(progress_ledger.get("contract"), dict)
        else {}
    )
    progress_values = {
        "task_id": (progress_ledger.get("task_id")
                    if isinstance(progress_ledger, dict) else None),
        "scope_version": progress_contract.get("scope_version"),
        "standards_version": progress_contract.get("standards_version"),
        "selected_profile_manifest": progress_contract.get(
            "selected_profile_manifest"
        ),
    }
    for field in ("task_id", "scope_version", "standards_version",
                  "selected_profile_manifest"):
        actual = coverage_ledger.get(field)
        expected = proof.get(field)
        if actual != expected:
            failures.append((
                "proof-coverage-identity-mismatch",
                "Coverage Ledger#%s" % field,
                "Coverage Ledger %s=%r does not match Terminal Proof value "
                "%r" % (field, actual, expected),
            ))
        progress_value = progress_values[field]
        if actual != progress_value:
            failures.append((
                "coverage-progress-identity-mismatch",
                "Coverage Ledger#%s" % field,
                "Coverage Ledger %s=%r does not match Progress Ledger value "
                "%r" % (field, actual, progress_value),
            ))

    open_gaps = coverage_ledger.get("open_gaps")
    if not isinstance(open_gaps, list):
        failures.append((
            "coverage-open-gaps-invalid", "Coverage Ledger#open_gaps",
            "open_gaps must be an explicit list",
        ))
    elif open_gaps:
        failures.append((
            "coverage-open-gaps-remaining", "Coverage Ledger#open_gaps",
            "canonical Coverage Ledger still has %d open gap(s); Terminal "
            "Proof cannot claim completion" % len(open_gaps),
        ))
    return failures


def main():
    ap = argparse.ArgumentParser(description="Terminal Proof completeness and zero-condition check")
    ap.add_argument("proof", help="path to the terminal proof YAML file")
    ap.add_argument("--ledger", help="Coverage Ledger YAML; with --root this "
                    "must be exactly .cambium/state/coverage_ledger.yaml")
    ap.add_argument("--progress-ledger", help="Progress Ledger YAML; required "
                    "with --root and must be exactly .cambium/state/"
                    "progress_ledger.yaml")
    ap.add_argument("--template",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "schemas", "terminal_proof.template.yaml"),
                    help="field-list template (default Tools/schemas/terminal_proof.template.yaml)")
    ap.add_argument("--root", help="vault root; when given, path-valued proof "
                    "fields must exist and selected routes, Cards, and kernel "
                    "Read Sets must agree with the canonical route indexes")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    receipt_output = args.receipts
    if receipt_output:
        try:
            if args.root:
                receipt_output = kblib.managed_repository_path(
                    os.path.realpath(os.path.abspath(args.root)),
                    receipt_output, ".cambium/receipts",
                    suffixes=(".jsonl",), must_exist=False,
                )
            else:
                receipt_output = kblib.validate_receipt_output_path(
                    receipt_output)
        except (OSError, ValueError) as exc:
            print("[FAIL] unsafe receipt path: %s" % exc)
            return 1

    template = kblib.parse_yaml_subset(open(args.template, encoding="utf-8").read())
    required_fields = list(template.keys())

    receipts = []
    seq = 0
    proof_name = os.path.basename(args.proof)
    proof_sha256 = None

    try:
        proof_bytes = Path(args.proof).read_bytes()
        proof_sha256 = kblib.sha256_bytes(proof_bytes)
        proof = kblib.parse_yaml_subset(proof_bytes.decode("utf-8"))
    except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
        seq += 1
        receipts.append(_make_receipt(
            TOOL, TOOL_VERSION, "proof-unreadable", args.proof, "fail",
            "cannot read/parse proof: %s" % exc, seq))
        kblib.write_receipts(receipt_output, receipts)
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
        if (field not in proof or value == "" or
                (value is None and field not in NULLABLE_REQUIRED_FIELDS)):
            missing.append(field)
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-field-missing",
                "%s#%s" % (proof_name, field), "fail",
                "Terminal Proof is missing required field %s (K12/16 field list)" % field, seq))

    frozen_string_bad = 0
    if "standards_version" not in missing:
        value = proof.get("standards_version")
        if _uninstantiated_value(value):
            frozen_string_bad += 1
            seq += 1
            receipts.append(_make_receipt(
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
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-profile-manifest-invalid",
                "%s#selected_profile_manifest" % proof_name, "fail",
                "selected_profile_manifest %r is invalid: %s" %
                (selected_profile_manifest, manifest_error), seq))

    queue_structure_bad = 0
    if "task_id" not in missing and _uninstantiated_value(proof.get("task_id")):
        queue_structure_bad += 1
        seq += 1
        receipts.append(_make_receipt(
            TOOL, TOOL_VERSION, "proof-task-id-invalid",
            "%s#task_id" % proof_name, "fail",
            "task_id must be an instantiated non-empty string", seq))

    if "required_queue_path" not in missing:
        queue_path = proof.get("required_queue_path")
        if queue_path != CANONICAL_QUEUE_PATH:
            queue_structure_bad += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-queue-path-noncanonical",
                "%s#required_queue_path" % proof_name, "fail",
                "required_queue_path must be exactly %s; found %r" %
                (CANONICAL_QUEUE_PATH, queue_path), seq))

    for field, minimum in (("queue_revision", 1),
                           ("queue_state_revision", 0)):
        if field in missing:
            continue
        value = proof.get(field)
        if (not isinstance(value, int) or isinstance(value, bool) or
                value < minimum):
            queue_structure_bad += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-queue-revision-invalid",
                "%s#%s" % (proof_name, field), "fail",
                "%s must be an integer >= %d; found %r" %
                (field, minimum, value), seq))

    for field, check in (
            ("coverage_ledger_sha256", "proof-coverage-fingerprint-invalid"),
            ("progress_ledger_sha256", "proof-progress-fingerprint-invalid"),
            ("required_queue_sha256", "proof-queue-fingerprint-invalid")):
        if field in missing:
            continue
        value = proof.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            queue_structure_bad += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, check,
                "%s#%s" % (proof_name, field), "fail",
                "%s must use sha256:<64 lowercase hex>; found %r" %
                (field, value), seq))

    if "queue_check_receipt" not in missing:
        value = proof.get("queue_check_receipt")
        if (not isinstance(value, str) or
                not value.startswith("audit-check_queue-")):
            queue_structure_bad += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-queue-receipt-id-invalid",
                "%s#queue_check_receipt" % proof_name, "fail",
                "queue_check_receipt must be a check_queue receipt_id; "
                "found %r" % value, seq))

    route_id_bad = 0
    valid_route_ids = set()
    route_ids = proof.get("selected_route_ids")
    if "selected_route_ids" not in missing:
        if not isinstance(route_ids, list) or not route_ids:
            route_id_bad += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-route-ids-empty",
                "%s#selected_route_ids" % proof_name, "fail",
                "selected_route_ids must be a non-empty list of kernel "
                "Runtime Route IDs (R01-R13)", seq))
        else:
            seen_route_ids = set()
            for index, route_id in enumerate(route_ids):
                target = "%s#selected_route_ids[%d]" % (proof_name, index)
                if not isinstance(route_id, str) or not RUNTIME_ROUTE_ID_RE.fullmatch(route_id):
                    route_id_bad += 1
                    seq += 1
                    receipts.append(_make_receipt(
                        TOOL, TOOL_VERSION, "proof-route-id-invalid",
                        target, "fail",
                        "route ID %r is invalid; expected one of R01-R13"
                        % route_id, seq))
                else:
                    valid_route_ids.add(route_id)
                route_key = repr(route_id)
                if route_key in seen_route_ids:
                    route_id_bad += 1
                    seq += 1
                    receipts.append(_make_receipt(
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
                    receipts.append(_make_receipt(
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
            receipts.append(_make_receipt(
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
                    receipts.append(_make_receipt(
                        TOOL, TOOL_VERSION, "proof-profile-route-id-invalid",
                        target, "fail",
                        "profile route ID %r is invalid; expected "
                        "P:<profile_id>:<route_name> with non-empty colon-free "
                        "segments" % route_id, seq))
                elif route_id in seen_profile_route_ids:
                    profile_route_id_bad += 1
                    seq += 1
                    receipts.append(_make_receipt(
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
            receipts.append(_make_receipt(
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
                    receipts.append(_make_receipt(
                        TOOL, TOOL_VERSION, "proof-card-path-invalid",
                        target, "fail",
                        "Card path %r is invalid: %s" %
                        (card_path, path_error), seq))
                elif card_path in seen_card_paths:
                    card_path_bad += 1
                    path_structure_bad += 1
                    seq += 1
                    receipts.append(_make_receipt(
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
            receipts.append(_make_receipt(
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
                    receipts.append(_make_receipt(
                        TOOL, TOOL_VERSION, "proof-read-set-path-invalid",
                        target, "fail",
                        "Read Set path %r is invalid: %s" %
                        (read_set_path, path_error), seq))
                elif read_set_path in seen_read_set_paths:
                    read_set_bad += 1
                    path_structure_bad += 1
                    seq += 1
                    receipts.append(_make_receipt(
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
                receipts.append(_make_receipt(
                    TOOL, TOOL_VERSION, "proof-path-invalid",
                    target, "fail",
                    "path %r recorded in %s is invalid: %s"
                    % (raw_path, field, path_error), seq))
            elif raw_path in seen_paths:
                path_structure_bad += 1
                seq += 1
                receipts.append(_make_receipt(
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
        receipts.append(_make_receipt(
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
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-zero-field",
                "%s#%s" % (proof_name, field), "fail",
                "zero-condition field %s = %r; the completion conditions require it to be 0 (K12/06)" % (field, value), seq))

    if "selected_profile_id" in proof:
        profile_manifest_bad += 1
        seq += 1
        receipts.append(_make_receipt(
            TOOL, TOOL_VERSION, "proof-duplicate-profile-identity",
            "%s#selected_profile_id" % proof_name, "fail",
            "selected_profile_id is forbidden: profile identity is derived "
            "only from selected_profile_manifest", seq))

    extra = [k for k in proof
             if k not in required_fields and k != "selected_profile_id"]
    for field in extra:
        seq += 1
        receipts.append(_make_receipt(
            TOOL, TOOL_VERSION, "proof-extra-field",
            "%s#%s" % (proof_name, field), "candidate",
            "field %s is not in the K12/16 field list (the list is an 'at least' "
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
            receipts.append(_make_receipt(
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
            receipts.append(_make_receipt(
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
    current_evidence_bad = 0
    selected_profile_id = None
    root = None
    if args.root:
        root = Path(args.root).resolve()
        if not root.is_dir():
            path_bad += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "proof-root-invalid", str(root), "fail",
                "--root must resolve to an existing directory", seq))
        else:
            current_runtime = check_queue.validate_runtime(str(root))
            current_evidence_failures = _reused_receipt_evidence_failures(
                root, proof, runtime=current_runtime)
            current_evidence_bad = len(current_evidence_failures)
            for check, target, details in current_evidence_failures:
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, check, target, "fail", details, seq
                ))

            active_state, active_state_errors = _load_active_standards_state(root)
            for index, details in enumerate(active_state_errors):
                active_state_bad += 1
                seq += 1
                receipts.append(_make_receipt(
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
                        receipts.append(_make_receipt(
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
                        receipts.append(_make_receipt(
                            TOOL, TOOL_VERSION, "proof-path-invalid",
                            target, "fail",
                            "path %r recorded in %s is invalid: %s"
                            % (raw_path, field, resolve_error), seq))
                    elif not resolved.is_file():
                        path_bad += 1
                        seq += 1
                        receipts.append(_make_receipt(
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
                        receipts.append(_make_receipt(
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
                            receipts.append(_make_receipt(
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
                                receipts.append(_make_receipt(
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
                                    receipts.append(_make_receipt(
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
                        receipts.append(_make_receipt(
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
                            receipts.append(_make_receipt(
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
                receipts.append(_make_receipt(
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
                    receipts.append(_make_receipt(
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
                    receipts.append(_make_receipt(
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
                            receipts.append(_make_receipt(
                                TOOL, TOOL_VERSION,
                                "proof-kernel-read-set-unregistered",
                                "%s#selected_read_sets" % proof_name, "fail",
                                "kernel Read Set path %s is not registered in %s"
                                % (read_set_path, READ_SET_INDEX_PATH), seq))
                        elif registered_route not in valid_route_ids:
                            read_set_bad += 1
                            seq += 1
                            receipts.append(_make_receipt(
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
                            receipts.append(_make_receipt(
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
                        receipts.append(_make_receipt(
                            TOOL, TOOL_VERSION,
                            "proof-read-set-path-outside-registry",
                            "%s#selected_read_sets" % proof_name, "fail",
                            "Read Set path %s is neither a canonical kernel "
                            "Read Set nor a profile supplemental Read Set"
                            % read_set_path, seq))

    progress_cross_fail = 0
    progress_ledger = None
    progress_sha256 = None
    proof_progress_sha256 = None
    if args.root and not args.progress_ledger:
        progress_cross_fail += 1
        seq += 1
        receipts.append(_make_receipt(
            TOOL, TOOL_VERSION, "progress-ledger-required", proof_name,
            "fail", "--progress-ledger is required with --root; without the "
            "frozen Task Contract snapshot this run cannot support complete",
            seq))

    if args.progress_ledger:
        progress_path = Path(args.progress_ledger)
        progress_path_error = None
        if args.root and root is not None and root.is_dir():
            progress_path, progress_path_error = _canonical_state_argument(
                root, args.progress_ledger, CANONICAL_PROGRESS_PATH
            )
        if progress_path_error:
            progress_cross_fail += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "progress-ledger-noncanonical",
                args.progress_ledger, "fail",
                "--progress-ledger must identify the canonical %s without "
                "aliases or symlinks: %s" %
                (CANONICAL_PROGRESS_PATH, progress_path_error), seq))
            progress_path = None
        try:
            if progress_path is not None:
                progress_bytes = progress_path.read_bytes()
                progress_sha256 = kblib.sha256_bytes(progress_bytes)
                progress_ledger = kblib.parse_yaml_subset(
                    progress_bytes.decode("utf-8")
                )
        except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
            progress_cross_fail += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "progress-ledger-unreadable",
                args.progress_ledger, "fail",
                "cannot read/parse Progress Ledger: %s" % exc, seq))
            progress_ledger = None

        if progress_path is not None:
            proof_progress_sha256 = progress_sha256
            binding_failures = []
            if args.root and root is not None and root.is_dir():
                proof_progress_sha256, binding_failures = (
                    _terminal_progress_binding(
                        root, progress_ledger, progress_sha256
                    )
                )
            progress_failures = binding_failures + \
                _validate_terminal_progress_state(
                    proof, progress_ledger, proof_progress_sha256
                )
            progress_cross_fail += len(progress_failures)
            for check, target, details in progress_failures:
                seq += 1
                receipts.append(_make_receipt(
                    TOOL, TOOL_VERSION, check, target, "fail", details, seq
                ))

        if (isinstance(progress_ledger, dict) and
                isinstance(progress_ledger.get("contract"), dict)):
            for field in ("standards_version", "selected_profile_manifest"):
                ledger_value = progress_ledger["contract"].get(field)
                invalid = _uninstantiated_value(ledger_value)
                if (field == "selected_profile_manifest" and not invalid and
                        _selected_profile_manifest_error(ledger_value)):
                    invalid = True
                if invalid:
                    progress_cross_fail += 1
                    seq += 1
                    receipts.append(_make_receipt(
                        TOOL, TOOL_VERSION, "progress-contract-field-invalid",
                        "Progress Ledger#contract.%s" % field, "fail",
                        "%s must be an instantiated canonical string" % field,
                        seq))
    coverage_cross_fail = 0
    ledger = None
    coverage_sha256 = None
    if args.root and not args.ledger:
        coverage_cross_fail += 1
        seq += 1
        receipts.append(_make_receipt(
            TOOL, TOOL_VERSION, "coverage-ledger-required", proof_name,
            "fail", "--ledger is required with --root so "
            "required_authoring_gaps is checked against current Coverage",
            seq,
        ))
    if args.ledger:
        ledger_path = Path(args.ledger)
        ledger_path_error = None
        if args.root and root is not None and root.is_dir():
            ledger_path, ledger_path_error = _canonical_state_argument(
                root, args.ledger, CANONICAL_COVERAGE_PATH
            )
        if ledger_path_error:
            coverage_cross_fail += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "coverage-ledger-noncanonical",
                args.ledger, "fail",
                "--ledger must identify the canonical %s without aliases or "
                "symlinks: %s" %
                (CANONICAL_COVERAGE_PATH, ledger_path_error), seq))
            ledger_path = None
        try:
            if ledger_path is not None:
                coverage_bytes = ledger_path.read_bytes()
                coverage_sha256 = kblib.sha256_bytes(coverage_bytes)
                ledger = kblib.parse_yaml_subset(
                    coverage_bytes.decode("utf-8")
                )
        except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
            coverage_cross_fail += 1
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, "ledger-unreadable", args.ledger, "fail",
                "cannot read/parse Coverage Ledger: %s" % exc, seq))
            ledger = None

        if args.root and ledger_path is not None:
            coverage_failures = _validate_terminal_coverage_state(
                proof, progress_ledger, ledger, coverage_sha256
            )
            coverage_cross_fail += len(coverage_failures)
            for check, target, details in coverage_failures:
                seq += 1
                receipts.append(_make_receipt(
                    TOOL, TOOL_VERSION, check, target, "fail", details, seq
                ))
        elif isinstance(ledger, dict):
            open_gaps = ledger.get("open_gaps")
            if isinstance(open_gaps, list) and open_gaps:
                coverage_cross_fail += 1
                seq += 1
                receipts.append(_make_receipt(
                    TOOL, TOOL_VERSION, "proof-ledger-mismatch",
                    "%s#required_authoring_gaps" % proof_name, "fail",
                    "Coverage Ledger open_gaps has %d unclosed gap(s), but "
                    "the proof claims completion" % len(open_gaps), seq))

    queue_cross_fail = 0
    queue_linkage_checked = False
    if args.root and root is not None and root.is_dir():
        queue_failures, queue_live_check_passed = (
            _validate_required_queue_linkage(
                root, proof, progress_ledger,
                coverage_sha256, proof_progress_sha256,
            )
        )
        queue_cross_fail = len(queue_failures)
        for check, target, details in queue_failures:
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, check, target, "fail", details, seq
            ))
        queue_linkage_checked = (
            queue_live_check_passed and not queue_failures
        )

    corpus_plan_cross_fail = 0
    corpus_plan_linkage_checked = False
    if args.root and root is not None and root.is_dir():
        corpus_failures, corpus_plan_linkage_checked = (
            _validate_corpus_plan_linkage(
                root, proof, proof_progress_sha256))
        corpus_plan_cross_fail = len(corpus_failures)
        for check, target, details in corpus_failures:
            seq += 1
            receipts.append(_make_receipt(
                TOOL, TOOL_VERSION, check, target, "fail", details, seq
            ))

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
        proof_receipt_path = proof_name
        if args.root and root is not None and root.is_dir():
            try:
                proof_receipt_path = Path(args.proof).resolve().relative_to(
                    root
                ).as_posix()
            except (OSError, RuntimeError, ValueError):
                proof_receipt_path = str(Path(args.proof).resolve())
        seq += 1
        summary_receipt = _make_receipt(
            TOOL, TOOL_VERSION, "proof-check-summary", proof_receipt_path,
            "pass",
            "fields complete (%d/%d), all zero-condition fields are 0%s%s%s%s%s%s%s" % (
                len(required_fields), len(required_fields),
                route_summary, profile_summary,
                ", consistent with the active K00/03 Standards state"
                if active_state_checked else "",
                ", consistent with the frozen Progress Ledger contract"
                if args.progress_ledger else "",
                ", bound to the current completed Required Queue and receipt"
                if queue_linkage_checked else "",
                ", bound to the current Corpus Planning receipt"
                if corpus_plan_linkage_checked else "",
                ", consistent with Coverage Ledger open_gaps"
                if args.ledger else ""), seq)
        if args.root and queue_linkage_checked:
            for field in (
                    "task_id", "scope_version", "contract_version",
                    "standards_version", "selected_profile_manifest",
                    "coverage_ledger_sha256", "progress_ledger_sha256",
                    "required_queue_path", "queue_revision",
                    "queue_state_revision", "required_queue_sha256",
                    "remaining_required_work_units", "queue_check_receipt",
                    "corpus_plan_check_receipt"):
                summary_receipt[field] = proof.get(field)
            summary_receipt["terminal_proof_path"] = proof_receipt_path
            summary_receipt["terminal_proof_sha256"] = proof_sha256
        receipts.append(summary_receipt)

    print("check_proof: checking %s against %d required template field(s)" % (args.proof, len(required_fields)))
    print("  missing_fields=%d route_id_violations=%d "
          "profile_route_id_violations=%d card_path_violations=%d "
          "read_set_violations=%d registry_violations=%d "
          "path_structure_violations=%d "
          "frozen_field_violations=%d profile_manifest_violations=%d "
          "queue_structure_violations=%d "
          "active_state_violations=%d "
          "zero_condition_violations=%d status_violations=%d "
          "path_failures=%d extra_fields(candidate)=%d "
          "progress_cross_failures=%d queue_cross_failures=%d "
          "coverage_cross_failures=%d corpus_plan_cross_failures=%d "
          "current_evidence_failures=%d "
          "registry_cross_check=%s active_state_check=%s "
          "profile_manifest_check=%s queue_completion_check=%s "
          "corpus_plan_check=%s"
          % (len(missing), route_id_bad, profile_route_id_bad, card_path_bad,
             read_set_bad, registry_bad, path_structure_bad,
             frozen_string_bad, profile_manifest_bad, queue_structure_bad,
             active_state_bad,
             len(zero_bad),
             len(status_bad), path_bad, len(extra), progress_cross_fail,
             queue_cross_fail, coverage_cross_fail, corpus_plan_cross_fail,
             current_evidence_bad,
             "passed" if registry_checked else
             ("failed" if args.root else "not_run"),
             "passed" if active_state_checked else
             ("failed" if args.root else "not_run"),
             "passed" if profile_manifest_checked else
             ("failed" if args.root else "not_run"),
             "passed" if queue_linkage_checked else
             ("failed" if args.root else "not_run"),
             "passed" if corpus_plan_linkage_checked else
             ("failed" if args.root else "not_run")))
    for r in receipts:
        if r["result"] != "pass":
            print("  [%s %s] %s — %s" % (r["result"].upper()[:4], r["check"],
                                         r["target"], r["details"]))
    if not any(r["result"] == "fail" for r in receipts):
        if args.root:
            print("  Conclusion: Terminal Proof consistency check passed with "
                  "active Standards state, filled profile, frozen Progress "
                  "Ledger, current Required Queue completion evidence, and "
                  "current Corpus Planning evidence, and repository registry "
                  "validation.")
        else:
            print("  Conclusion: structural lint passed; without --root this "
                  "is not Terminal Completion Gate evidence.")

    kblib.write_receipts(receipt_output, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
