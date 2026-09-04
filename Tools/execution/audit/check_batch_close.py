#!/usr/bin/env python3
"""Produce the canonical merged-snapshot evidence needed to close one batch.

The command is the production counterpart of K12/09.  It runs the full
Closed List on the real repository, records an explicit declared-reviewer
attestation, obtains a canonical ``check_queue`` consistency receipt, and
publishes one batch-close aggregator that ``update_queue.py`` can consume.

All checks and receipt publication occur while the shared runtime writer lock
is held.  Repository content is hashed before and after checking, before
publication, and after publication.  A failed check publishes only one failed
attempt receipt, never a reusable subset of pass receipts.  An uncertain
append or a post-publication verification failure deliberately preserves the
writer lock for restart reconciliation.

Under the close lock, the command acquires one full ``profile-load``
authorized view and shares its immutable typed contract across runtime,
Corpus Planning, compiled-artifact checks, quota overrides, and registered
scan compilation.  A readable Audit/Scan registry cannot bypass a broken
identity or one of the other eleven Profile slots.

Exit codes:
  0  complete close-evidence bundle durably published
  1  invalid state, failed check, unreviewed candidate, or write failure

Usage:
  python3 Tools/check_batch_close.py ROOT --batch B1 \
      --integrator alice --reviewer bob \
      --review-attestation "Reviewed the listed candidates and global state."

Candidates are never swallowed by the prose attestation.  The reviewer must
accept each current stable candidate ID or its exact ``tool:check`` type with
``--accept-candidate-id`` / ``--accept-candidate-type``.  Unused selectors are
rejected so a stale attestation cannot silently authorize a different run.
``--accept-while-unchanged-id`` / ``--accept-while-unchanged-type`` grant the
same current acceptance plus bounded reuse by the immediately following close
when the exact observation and producer version remain unchanged.
"""
from Tools.platform.repository.repository import tools_source_root

import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_reconciliation_contract as audit_reconciliation_contract
import Tools.execution.audit.batch_close_audit as batch_close_audit
import Tools.execution.audit.batch_close_contract as batch_close_contract
import Tools.execution.task_runtime.batch_settlement as batch_settlement
import Tools.execution.context_delivery.card_contract as card_contract
import Tools.execution.evidence.candidate_lifecycle as candidate_lifecycle
import Tools.knowledge.content.check_links as check_links
import Tools.execution.planning.check_corpus_plan as check_corpus_plan
import Tools.knowledge.metadata.check_page_contract as check_page_contract
import Tools.governance.profile.check_profile as check_profile
from Tools.execution.task_runtime.queue_runtime.canon import (
    BATCH_CLOSE_TOOL as TOOL,
    BATCH_CLOSE_TOOL_VERSION as TOOL_VERSION,
    COVERAGE_PATH,
    PROGRESS_PATH,
    QUEUE_PATH,
)
import Tools.execution.task_runtime.queue_runtime.authority as runtime_authority
import Tools.execution.task_runtime.queue_runtime.close_gate as close_gate
import Tools.execution.task_runtime.queue_runtime.profile_view as profile_view_contract
import Tools.execution.task_runtime.queue_runtime.receipts as receipt_catalogs
import Tools.execution.task_runtime.queue_runtime.revalidation as revalidation
import Tools.execution.task_runtime.queue_runtime.work_spec as work_spec
import Tools.execution.task_runtime.queue_check_receipt as queue_check_receipt
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.knowledge.metadata.check_vocab as check_vocab
import Tools.governance.control.contract_exception_policy as contract_exception_policy
import Tools.execution.planning.corpus_planning_contract as corpus_planning_contract
import Tools.platform.common.kblib as kblib
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.knowledge.metadata.project_page_state as project_page_state
import Tools.governance.profile.profile_admission as profile_admission
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.knowledge.structure.repository_structure as repository_structure
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting
from Tools.platform.repository import repository
from Tools.platform.common.primitives import catalog_record


GATE_ID = batch_close_contract.GATE_ID
# The `Check` cell K00/12 registers for this Gate; every receipt this
# tool offers as gate evidence carries it verbatim.
GATE_CHECK = batch_close_contract.GATE_CHECK
DEFAULT_RECEIPTS = runtime_paths.BATCH_CLOSE_RECEIPT_PATH
MAX_CHECK_SECONDS = 60
IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]*\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
SCRIPT_DIR = Path(tools_source_root(__file__))

JSON_FLAG_HELP = reporting.JSON_CHECK_HELP
_JSON_REPORTER = reporting.RedirectedJsonReceipts()



def _make_receipt(tool, tool_version, check, target, result, details, seq,
                  *, receipt_type_id, root=None):
    """Build one current-contract batch-close receipt with its stable Gate ID.

    ``root`` binds the Required Queue identity a Gate consumer compares
    against; outside a Cambium runtime those fields stay absent.
    """
    if tool != TOOL or tool_version != TOOL_VERSION:
        raise ValueError("check_batch_close receipt producer identity drift")
    receipt = kblib.make_receipt(
        tool, tool_version, check, target, result, details, seq,
        receipt_type_id=receipt_type_id, root=root)
    receipt["gate_id"] = GATE_ID
    return receipt


class ReceiptPublicationUncertain(RuntimeError):
    """Receipt bytes could not be proven complete and durable."""


def _freeze_manifest_pages(root, manifest, projection_rules):
    """Freeze every exact manifest page and bind its semantic content.

    The full target snapshot is retained for the final publication CAS.  The
    semantic digest excludes the fields authorized by the Core plus the same
    typed Profile Gate contract used by the runtime, so writing a machine-
    owned copy cannot invalidate the human review while a body or user-owned
    frontmatter edit always does.
    """
    if (not isinstance(manifest, list) or
            any(not isinstance(value, str) or not value.strip()
                for value in manifest)):
        raise ValueError("batch manifest must be an explicit page-path list")
    if len(manifest) != len(set(manifest)):
        raise ValueError("batch manifest page paths must be unique")
    frozen = []
    for relative in sorted(manifest):
        snapshot = kblib.repository_target_snapshot(
            root, relative, suffixes=".md", singly_linked=True)
        if not snapshot.exists:
            raise ValueError("manifest page does not exist: %s" % relative)
        text = snapshot.read_text()
        frozen.append({
            "path": relative,
            "snapshot": snapshot,
            "semantic_content_sha256":
                project_page_state.semantic_content_fingerprint(
                    relative, text, projection_rules),
        })
    return tuple(frozen)


def _assert_manifest_pages_unchanged(root, frozen, *, uncertain=False):
    """Perform the exact page identity-and-bytes CAS before/after append."""
    changed = []
    for page in frozen:
        relative = page["path"]
        try:
            current = kblib.repository_target_snapshot(
                root, relative, suffixes=".md", singly_linked=True)
        except (OSError, ValueError) as exc:
            changed.append("%s (%s)" % (relative, exc))
            continue
        if not repository.same_existing_repository_target_snapshot(
                page["snapshot"], current):
            changed.append(relative)
    if changed:
        message = "manifest page changed before review evidence publication: %s" % \
            ", ".join(changed)
        if uncertain:
            raise ReceiptPublicationUncertain(message)
        raise ValueError(message)


def _receipt_id_set_sha256(receipt_ids):
    """Fingerprint an exact receipt-ID set with the shared set protocol."""
    return candidate_lifecycle.candidate_set_sha256(receipt_ids)


AUTHORITATIVE_STATE_FILES = (
    ("coverage", COVERAGE_PATH, "coverage_sha256"),
    ("required_queue", QUEUE_PATH, "queue_sha256"),
    ("progress", PROGRESS_PATH, "progress_sha256"),
)


def _authoritative_state_anchor(runtime):
    """Return the validated runtime's exact three-file state fingerprint."""
    anchor = {}
    for label, _relative, runtime_field in AUTHORITATIVE_STATE_FILES:
        digest = runtime.get(runtime_field)
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(
                "runtime has no valid %s authoritative-state fingerprint" %
                label)
        anchor[label] = digest
    return anchor


def _authoritative_file_sha256(root, relative):
    """Hash one singly-linked canonical state file without following links."""
    absolute = kblib.repository_path(
        root, relative, must_exist=True, reject_symlink=True)
    listed = os.lstat(absolute)
    if not stat.S_ISREG(listed.st_mode):
        raise ValueError("authoritative state must be a regular file: %s" %
                         relative)
    if listed.st_nlink != 1:
        raise ValueError(
            "authoritative state must have exactly one hard link: %s" %
            relative)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise OSError("authoritative-state verification requires O_NOFOLLOW")
    descriptor = os.open(absolute, os.O_RDONLY | nofollow)
    try:
        opened = os.fstat(descriptor)
        identity = (listed.st_dev, listed.st_ino, listed.st_mode,
                    listed.st_nlink)
        opened_identity = (opened.st_dev, opened.st_ino, opened.st_mode,
                           opened.st_nlink)
        if identity != opened_identity:
            raise ValueError(
                "authoritative state changed before it could be read: %s" %
                relative)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        read_end = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = os.lstat(absolute)
    stability_fields = ("st_dev", "st_ino", "st_mode", "st_nlink",
                        "st_size", "st_mtime_ns", "st_ctime_ns")
    if (tuple(getattr(opened, field) for field in stability_fields) !=
            tuple(getattr(read_end, field) for field in stability_fields) or
            tuple(getattr(read_end, field) for field in stability_fields) !=
            tuple(getattr(after, field) for field in stability_fields)):
        raise ValueError(
            "authoritative state changed while it was being read: %s" %
            relative)
    return "sha256:" + digest.hexdigest()


def _assert_authoritative_state_unchanged(root, anchor):
    """Fail uncertain when any canonical state byte differs from ``anchor``."""
    live = {}
    try:
        for label, relative, _runtime_field in AUTHORITATIVE_STATE_FILES:
            live[label] = _authoritative_file_sha256(root, relative)
    except (OSError, ValueError) as exc:
        raise ReceiptPublicationUncertain(
            "authoritative state could not be re-read after Closed List "
            "execution: %s" % exc) from exc
    changed = [
        "%s expected=%s live=%s" % (label, anchor.get(label), live[label])
        for label, _relative, _runtime_field in AUTHORITATIVE_STATE_FILES
        if live[label] != anchor.get(label)
    ]
    if changed:
        raise ReceiptPublicationUncertain(
            "authoritative state changed while the Closed List ran: %s" %
            "; ".join(changed))
    return live


def _assert_work_spec_unchanged(root, item):
    """Keep the Queue-bound complex-batch contract stable during close."""
    relative = item.get("work_spec_path")
    expected = item.get("work_spec_sha256")
    if relative is None and expected is None:
        return
    absolute = kblib.managed_repository_path(
        root, relative, work_spec.WORK_SPEC_PREFIX,
        suffixes=(".yaml",), must_exist=True,
    )
    actual = kblib.sha256_file(absolute)
    if actual != expected:
        raise ReceiptPublicationUncertain(
            "Batch Work Spec changed while the Closed List ran: "
            "%s expected=%s actual=%s" % (relative, expected, actual)
        )


def _load_jsonl(path):
    receipts = []
    with open(path, encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("malformed check receipt %s:%d: %s" %
                                 (path, line_number, exc))
            if not isinstance(value, dict):
                raise ValueError("check receipt %s:%d is not an object" %
                                 (path, line_number))
            receipts.append(value)
    return receipts


def _run_receipting_command(command, cwd, label):
    """Run a deterministic checker and return its actual script receipts."""
    with tempfile.TemporaryDirectory(prefix="cambium-batch-close-") as temp:
        receipt_path = os.path.join(temp, "receipts.jsonl")
        completed = kblib.run_cambium_subprocess(
            list(command) + ["--receipts", receipt_path],
            cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
            timeout=MAX_CHECK_SECONDS,
        )
        receipts = _load_jsonl(receipt_path) if os.path.exists(
            receipt_path) else []
    return _receipting_result(
        list(command), label, completed.returncode, completed.stdout,
        receipts)


def _receipting_result(command, label, returncode, stdout, receipts):
    """Normalize one in-process or subprocess checker result."""
    failures = [receipt for receipt in receipts
                if receipt.get("result") == "fail"]
    candidates = [receipt for receipt in receipts
                  if receipt.get("result") == "candidate"]
    # 0 and 2 are the two codes a checker may exit while still having reached a
    # verdict; 1 is a failure or unreliable evidence.  A usage error also exits
    # 1 (kblib.ArgumentParser), so a mis-typed command can no longer arrive here
    # wearing the HOLD code.  Nothing below rests on that alone: the receipts
    # this checker actually wrote are cross-checked against the code just after,
    # and a run that exits 2 without candidate receipts is reported either way.
    valid_exit = returncode in (0, 2)
    expected_exit = 2 if candidates and not failures else (1 if failures else 0)
    errors = []
    receipt_ids = []
    for index, receipt in enumerate(receipts):
        for field in ("receipt_id", "tool", "tool_version", "check",
                      "target", "details"):
            if not isinstance(receipt.get(field), str) or not receipt.get(field):
                errors.append("checker receipt %d has invalid %s" %
                              (index + 1, field))
        if receipt.get("result") not in ("pass", "fail", "candidate"):
            errors.append("checker receipt %d has unsupported result %r" %
                          (index + 1, receipt.get("result")))
        if receipt.get("invalidated_by") is not None:
            errors.append("checker receipt %d is already invalidated" %
                          (index + 1))
        if isinstance(receipt.get("receipt_id"), str):
            receipt_ids.append(receipt["receipt_id"])
    if len(receipt_ids) != len(set(receipt_ids)):
        errors.append("checker repeated a receipt_id")
    if not receipts:
        errors.append("checker produced no machine-readable receipts")
    if not valid_exit:
        errors.append("checker exited %d" % returncode)
    if failures:
        errors.extend("%s %s: %s" % (
            receipt.get("check"), receipt.get("target"),
            receipt.get("details")) for receipt in failures)
    if receipts and returncode != expected_exit:
        errors.append("checker exit %d disagrees with receipt results (expected %d)" %
                      (returncode, expected_exit))
    return {
        "label": label,
        "command": list(command),
        "returncode": returncode,
        "stdout": stdout,
        "receipts": receipts,
        "candidates": candidates,
        "errors": errors,
    }


def _run_inprocess_checker(command, cwd, label, invoke):
    """Run one admission-aware checker without losing its in-memory view."""
    with tempfile.TemporaryDirectory(prefix="cambium-batch-close-") as temp:
        receipt_path = os.path.join(temp, "receipts.jsonl")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            returncode = invoke(receipt_path)
        receipts = _load_jsonl(receipt_path) if os.path.exists(
            receipt_path) else []
    return _receipting_result(
        command, label, returncode, captured.getvalue(), receipts)


def _stable_candidate(receipt, member):
    source_tool = str(receipt.get("tool") or TOOL)
    check = str(receipt.get("check") or "unknown")
    target = str(receipt.get("target") or ".")
    details = str(receipt.get("details") or "")
    payload = json.dumps({
        "member": member,
        "source_tool": source_tool,
        "check": check,
        "target": target,
        "details": details,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    candidate = {
        "candidate_id": "candidate-sha256:%s" % digest,
        "candidate_type": "%s:%s" % (source_tool, check),
        "member": member,
        "target": target,
        "details": details,
        "producer_tool_version": str(receipt.get("tool_version") or "unknown"),
    }
    share = receipt.get("priority_share")
    if isinstance(share, dict):
        candidate["priority_share"] = dict(share)
    return candidate_lifecycle.with_observation(candidate)


def _structural_check(root, runtime):
    manifest = runtime.get("queue", {}).get("selected_profile_manifest")
    return repository_structure.check_repository_structure(root, manifest)


def _markdown_graph_projection(root):
    """Return the canonical in-memory graph derived from Markdown wiki links.

    The projection deliberately has no repository-JSON input.  Item 3 owns a
    graph *projection*, not every JSON document that an adopting repository
    may contain.  Link validity remains item 1's responsibility; unresolved
    edges are represented here as data rather than promoted to a second link
    failure.
    """
    files = list(repository_structure.repository_files(root, (".md",)))
    by_path, by_base = check_links.build_index(files)
    nodes = [
        {
            "id": relative[:-3],
            "path": relative,
            "basename": os.path.basename(relative),
        }
        for _, relative in files
    ]
    nodes.sort(key=lambda node: node["path"])

    resolved_edges = []
    unresolved_edges = []
    for absolute, relative in files:
        source = relative[:-3]
        text = Path(absolute).read_text(encoding="utf-8", errors="replace")
        text = kblib.strip_code(text)
        for line_number, line in enumerate(text.splitlines(), 1):
            for match in check_links.LINK_RE.finditer(line):
                target, heading = check_links.parse_link(match.group(1))
                if target == "":
                    status, resolution = "resolved", source
                else:
                    status, resolution = check_links.resolve(
                        target, by_path, by_base)
                common = {
                    "source": source,
                    "line": line_number,
                    "column": match.start() + 1,
                    "target": target,
                    "heading": heading,
                }
                if status == "resolved":
                    common["resolved_target"] = resolution
                    resolved_edges.append(common)
                else:
                    common["status"] = status
                    common["candidate_targets"] = (
                        sorted(resolution) if status == "ambiguous" else [])
                    unresolved_edges.append(common)

    edge_key = lambda edge: (
        edge["source"], edge["line"], edge["column"], edge["target"],
        edge["heading"], edge.get("resolved_target", ""),
        edge.get("status", ""), tuple(edge.get("candidate_targets", [])),
    )
    resolved_edges.sort(key=edge_key)
    unresolved_edges.sort(key=edge_key)
    projection = {
        "schema_version": 1,
        "nodes": nodes,
        "resolved_edges": resolved_edges,
        "unresolved_edges": unresolved_edges,
    }
    encoded = json.dumps(
        projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    decoded = json.loads(encoded)
    if decoded != projection:
        raise ValueError("Markdown graph JSON projection failed round-trip")
    if json.dumps(decoded, ensure_ascii=False, sort_keys=True,
                  separators=(",", ":")) != encoded:
        raise ValueError("Markdown graph JSON projection is not canonical")
    return projection, encoded


def _graph_and_basename_check(root):
    errors = []
    candidates = []
    try:
        projection, encoded = _markdown_graph_projection(root)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "errors": ["Markdown graph projection cannot be generated: %s" %
                       exc],
            "candidates": [],
            "details": "graph_projection=fail",
        }

    by_basename = defaultdict(list)
    for node in projection["nodes"]:
        by_basename[node["basename"].casefold()].append(node["path"])
    duplicates = [sorted(paths) for paths in by_basename.values()
                  if len(paths) > 1]
    for paths in sorted(duplicates):
        candidates.append({
            "tool": TOOL,
            "check": "duplicate-markdown-basename",
            "target": os.path.basename(paths[0]),
            "result": "candidate",
            "details": "duplicate Markdown basename: %s" % ", ".join(paths),
        })
    return {
        "errors": errors,
        "candidates": candidates,
        "details": (
            "graph_projection_nodes=%d resolved_edges=%d "
            "unresolved_edges=%d projection_sha256=sha256:%s "
            "duplicate_basename_groups=%d" %
            (len(projection["nodes"]), len(projection["resolved_edges"]),
             len(projection["unresolved_edges"]),
             hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
             len(duplicates))
        ),
    }


def _coverage_file_count_check(root, runtime, item):
    errors = []
    manifest = list(item.get("manifest") or [])
    records = {
        entry.get("path"): entry
        for entry in (runtime.get("coverage", {}).get("pages") or [])
        if isinstance(entry, dict)
    }
    projected = sorted(path for path, record in records.items()
                       if record.get("batch") == item.get("id") or
                       record.get("next_batch") == item.get("id"))
    if item.get("record_count") != len(manifest):
        errors.append("record_count=%r but manifest has %d object(s)" %
                      (item.get("record_count"), len(manifest)))
    if sorted(manifest) != projected:
        errors.append("Coverage projection differs from Queue manifest")
    existing = 0
    for relative in manifest:
        try:
            absolute = kblib.repository_path(
                root, relative, must_exist=True, reject_symlink=True)
            descriptor = os.lstat(absolute)
            if not stat.S_ISREG(descriptor.st_mode) or descriptor.st_nlink != 1:
                raise ValueError("not a singly-linked regular file")
            if not relative.lower().endswith(".md"):
                raise ValueError("knowledge object is not a Markdown file")
            existing += 1
        except (OSError, ValueError) as exc:
            errors.append("manifest object %s is not materialized safely: %s" %
                          (relative, exc))
    details = ("record_count=%s manifest=%d coverage_projection=%d "
               "materialized=%d" %
               (item.get("record_count"), len(manifest), len(projected),
                existing))
    return {"errors": errors, "candidates": [], "details": details}


def _guidance_contract_check(runtime):
    errors = list(runtime.get("errors") or [])
    task_runtime = runtime.get("task_runtime") or {}
    pending_guidance = task_runtime.get("pending_guidance") or []
    pending_amendments = task_runtime.get("pending_amendments") or []
    if pending_guidance:
        errors.append("pending guidance: %s" % ", ".join(pending_guidance))
    if pending_amendments:
        errors.append("pending amendments: %s" % ", ".join(pending_amendments))
    contract = (runtime.get("progress", {}).get("contract") or {})
    details = ("task_id=%s scope_version=%s contract_version=%s "
               "pending_guidance=%d pending_amendments=%d" %
               (runtime.get("queue", {}).get("task_id"),
                contract.get("scope_version"), contract.get("contract_version"),
                len(pending_guidance), len(pending_amendments)))
    return {"errors": errors, "candidates": [], "details": details}


def _corpus_plan_close_check(root, runtime, item, snapshot, *,
                             authorized_profile_view=None):
    """Return the conditional R13/planning-manifest close child receipt.

    Route selection is task-level in Progress.  A batch also becomes
    applicable when its exact Queue manifest changes the selected Corpus
    Planning slot, a bound planning artifact, or a path explicitly named by a
    validated planning relation.  Unrelated batches do not acquire a new gate
    merely because the repository contains a plan.
    """
    result = check_corpus_plan.validate_corpus_plan(
        root,
        profile=runtime.get("queue", {}).get("selected_profile_manifest"),
        authorized_profile_view=authorized_profile_view,
        authorized_active_standards_view=runtime.get(
            "_active_standards_authorized_view"))
    required, triggers = check_corpus_plan.close_requirement(
        runtime, item, result)
    if not required:
        return {
            "required": False,
            "triggers": [],
            "receipt": None,
            "binding": None,
            "errors": [],
        }

    errors = [
        "%s %s: %s" % (error["check"], error["target"], error["details"])
        for error in result.get("errors") or []
    ]
    if (corpus_planning_contract.CLOSE_ROUTE_TRIGGER in triggers and
            result.get("applicability") !=
            corpus_planning_contract.CONFIGURED_STATE):
        errors.append(
            "R13-selected batch requires Corpus Planning applicability.state=configured")
    receipt = None
    binding = None
    if not errors:
        try:
            receipt = check_corpus_plan.make_pass_receipt(
                result, repository_snapshot_sha256=snapshot, seq=10)
            errors.extend(check_corpus_plan.pass_receipt_errors(
                root, receipt, result=result,
                repository_snapshot_sha256=snapshot,
                require_runtime=True,
                require_configured=(
                    corpus_planning_contract.CLOSE_ROUTE_TRIGGER in triggers),
            ))
            if not errors:
                binding = {
                    field: receipt.get(field)
                    for field in
                    corpus_planning_contract.PASS_RECEIPT_BINDING_FIELDS
                }
        except (OSError, TypeError, ValueError) as exc:
            errors.append("Corpus Planning receipt cannot be bound: %s" % exc)
    return {
        "required": True,
        "triggers": triggers,
        "receipt": receipt,
        "binding": binding,
        "errors": errors,
    }


def manifest_path(root, runtime):
    relative = runtime.get("queue", {}).get("selected_profile_manifest")
    return kblib.repository_path(root, relative, must_exist=True,
                                 reject_symlink=True)


def _profile_evaluation(root, runtime, *, authorized_profile_view=None):
    root = os.path.realpath(os.path.abspath(os.fspath(root)))
    manifest_path(root, runtime)
    manifest_relative = runtime.get("queue", {}).get(
        "selected_profile_manifest")
    if authorized_profile_view is None:
        authorized_profile_view, errors = \
            profile_view_contract.profile_load_authorized_view(
                root, manifest_relative)
    else:
        errors = profile_view_contract.authorized_profile_view_errors(
            root, manifest_relative, authorized_profile_view)
    if errors or authorized_profile_view is None:
        raise ValueError(
            "selected Profile failed full profile-load before registered "
            "scan compilation: %s" % "; ".join(
                errors or ("no authorized evaluation",)))
    evaluation = authorized_profile_view.get("_evaluation")
    if not isinstance(evaluation, check_profile.ProfileLoadEvaluation):
        raise ValueError(
            "authorized Profile view carries no producer evaluation")
    if not evaluation.authorized:
        findings = "; ".join(
            "%s [%s]: %s" % (
                finding.get("check", "profile-load"),
                finding.get("target", manifest_path),
                finding.get("details", "Profile load was not authorized"),
            )
            for finding in evaluation.findings
        )
        raise ValueError(
            "selected Profile failed full profile-load before registered "
            "scan compilation: %s" %
            (findings or evaluation.output.strip() or
             "producer returned no authorized contract"))
    return evaluation


def _profile_scan_command(root, evaluation):
    scan = evaluation.contract.required_scan
    expected = {"scan_id": scan.scan_id}
    if scan.config_dependency is not None:
        expected["config_fingerprint"] = kblib.sha256_bytes(
            evaluation.profile_snapshot.read_bytes(
                scan.config_dependency.path))
    command = list(profile_contract.compile_registered_scan_command(
        root, evaluation.contract, scan=scan))
    return command, expected


def _rubric_text_for(evaluation):
    contract = evaluation.contract
    snapshot = evaluation.profile_snapshot
    manifest_text = snapshot.read_text(contract.manifest_repo_path)
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = (bindings.get("Priority Rubric") or "").strip("`").strip()
    if not binding:
        raise ValueError("the selected Profile binds no Priority Rubric slot")
    return snapshot.read_text(
        "%s/%s" % (contract.profile_repo_dir.rstrip("/"), binding))


def _priority_policy(evaluation):
    """Resolve the optional quota policy from the Priority Rubric slot.

    K00/07 owns the quota model and the selected Profile owns any configured
    values. ``Registration: None`` resolves to a fingerprinted inactive
    policy, not hidden Kernel defaults. This consumer reads the same slot bytes
    through the same resolver the profile-load Gate validates.
    """
    if not evaluation.authorized:
        raise ValueError("priority policy requires one authorized profile-load")
    contract = evaluation.contract
    snapshot = evaluation.profile_snapshot
    manifest_text = snapshot.read_text(contract.manifest_repo_path)
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = (bindings.get("Priority Rubric") or "").strip("`").strip()
    if not binding:
        raise ValueError("the selected Profile binds no Priority Rubric slot")
    rubric_repo_path = "%s/%s" % (contract.profile_repo_dir.rstrip("/"),
                                  binding)
    rubric_text = snapshot.read_text(rubric_repo_path)
    policy, fingerprint, errors = (
        contract_exception_policy.effective_priority_policy(rubric_text))
    if errors or fingerprint is None:
        raise ValueError(
            "the Priority Rubric quota registration does not resolve: %s" %
            "; ".join(errors))
    return policy, fingerprint


def _quota_exceptions(runtime, policy_fingerprint):
    """Return the contract's currently valid priority-quota exceptions.

    Validity is judged here, at consumption: the baseline fingerprint must
    equal the fingerprint of the current resolved policy object -- a Standards
    or Profile revision the exception never saw invalidates it rather than
    being silently covered -- and a task-scoped exception must name this task.
    Snapshot-scoped entries are returned with their scope for the caller to
    compare against the merged snapshot it is closing.
    """
    contract_state = (runtime.get("progress") or {}).get("contract") or {}
    entries = contract_state.get("policy_exceptions")
    if not isinstance(entries, list) or not entries:
        return {}
    task_id = (runtime.get("queue") or {}).get("task_id")
    valid = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        policy_id = entry.get("policy_id")
        if policy_id not in ("priority_quota.P0", "priority_quota.P1"):
            continue
        if entry.get("baseline_policy_fingerprint") != policy_fingerprint:
            # Stale against the live policy source: not an error, simply no
            # longer an authorization.
            continue
        if (entry.get("scope_kind") == "task" and
                entry.get("scope_ref") != task_id):
            continue
        valid.setdefault(policy_id.split(".")[1], []).append(entry)
    return valid


def _manifest_page_contract_member(run, manifest_paths, member):
    """Build the K12/09 item 8 member: page-contract debt on manifest pages.

    The full-corpus advisory backlog stays advisory — existing candidates on
    pages this batch never touched do not block anyone.  But a page in this
    batch's manifest has completed its pre-merge review obligations and is
    awaiting the close projection, so any page-contract candidate it still
    carries is unfinished batch work: it surfaces here as a stable candidate
    the integrator must either fix or explicitly accept with a recorded
    disposition, and a strict-mode fail on a manifest page is a member error
    outright.
    """
    manifest = {str(path) for path in manifest_paths if path}

    def _on_manifest(target):
        target = str(target or "")
        page = target.split(" @ ", 1)[0]
        for path in manifest:
            if page == path or page.startswith(path + ":"):
                return True
        return False

    candidates = [_stable_candidate(receipt, member)
                  for receipt in run.get("candidates") or []
                  if _on_manifest(receipt.get("target"))]
    errors = list(run.get("errors") or [])
    for receipt in run.get("receipts") or []:
        if (receipt.get("result") == "fail" and
                _on_manifest(receipt.get("target"))):
            errors.append(
                "manifest page fails the compiled page contract: %s (%s)" %
                (receipt.get("target"), receipt.get("details")))
    summaries = [
        receipt for receipt in run.get("receipts") or []
        if receipt.get("gate_id") == "page-contract" and
        receipt.get("check") == "page-contract-summary"
    ]
    gate_evidence = summaries[0] if len(summaries) == 1 else None
    if len(summaries) != 1:
        errors.append(
            "page-contract Gate must produce exactly one current summary "
            "receipt, found %d" % len(summaries))
    elif gate_evidence.get("dimension") is not None:
        errors.append(
            "page-contract Gate evidence for Closed List item 8 must be "
            "dimensionless")
    total = len(run.get("candidates") or [])
    details = ("%s exit=%s receipts=%d manifest_candidates=%d "
               "corpus_candidates=%d" % (
                   run.get("label"), run.get("returncode"),
                   len(run.get("receipts") or []), len(candidates), total))
    return {
        "errors": errors,
        "candidates": candidates,
        "details": details,
        "source_command": run.get("command"),
        "gate_evidence": gate_evidence,
    }


def _tool_member_run(run, member):
    candidates = [_stable_candidate(receipt, member)
                  for receipt in run.get("candidates") or []]
    details = "%s exit=%s receipts=%d candidates=%d" % (
        run.get("label"), run.get("returncode"),
        len(run.get("receipts") or []), len(candidates))
    output = (run.get("stdout") or "").strip().splitlines()
    if output:
        details += "; summary=" + output[-1][:500]
    return {
        "errors": list(run.get("errors") or []),
        "candidates": candidates,
        "details": details,
        "source_command": run.get("command"),
    }


POSITIVE_CONTROL_BINDING_FIELDS = (
    "tool", "tool_version", "check", "scan_id", "config_fingerprint",
    "positive_control_result", "positive_control_mode",
    "positive_control_count", "positive_control_fingerprint",
)


def _positive_control_summary_errors(run):
    """Validate one side of the verifier-neutral K12/09 control protocol."""
    receipts = run.get("receipts") or []
    if not receipts:
        return ["registered verifier emitted no positive-control summary"]
    summary = receipts[-1]
    errors = []
    if summary.get("result") != "pass":
        errors.append(
            "registered verifier final summary must be a pass receipt")
    scan_id = summary.get("scan_id")
    if not isinstance(scan_id, str) or not scan_id:
        errors.append(
            "registered verifier final summary must declare a non-empty "
            "scan_id")
    config_fingerprint = summary.get("config_fingerprint")
    if (not isinstance(config_fingerprint, str) or
            re.fullmatch(r"sha256:[0-9a-f]{64}",
                         config_fingerprint) is None):
        errors.append(
            "registered verifier final summary must declare a canonical "
            "config_fingerprint")
    if summary.get("positive_control_result") != "passed":
        errors.append(
            "registered verifier final summary must declare "
            "positive_control_result=passed")
    if summary.get("positive_control_mode") != "production-classifier":
        errors.append(
            "registered verifier final summary must declare "
            "positive_control_mode=production-classifier")
    count = summary.get("positive_control_count")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        errors.append(
            "registered verifier final summary must declare a positive "
            "positive_control_count value")
    fingerprint = summary.get("positive_control_fingerprint")
    if (not isinstance(fingerprint, str) or
            re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint) is None):
        errors.append(
            "registered verifier final summary must declare a canonical "
            "positive_control_fingerprint")
    return errors


def _positive_control_binding_errors(control_run, production_run,
                                     expected_binding=None):
    """Bind an explicit control invocation to the following production run."""
    errors = []
    errors.extend("positive-control invocation: %s" % error
                  for error in _positive_control_summary_errors(control_run))
    errors.extend("production invocation: %s" % error
                  for error in _positive_control_summary_errors(production_run))
    control_receipts = control_run.get("receipts") or []
    production_receipts = production_run.get("receipts") or []
    if not control_receipts or not production_receipts:
        return errors
    control = control_receipts[-1]
    production = production_receipts[-1]
    for field in POSITIVE_CONTROL_BINDING_FIELDS:
        if control.get(field) != production.get(field):
            errors.append(
                "registered verifier positive-control and production "
                "summaries disagree on %s" % field)
    for field, expected in sorted((expected_binding or {}).items()):
        for invocation, summary in (("positive-control", control),
                                    ("production", production)):
            if summary.get(field) != expected:
                errors.append(
                    "registered verifier %s summary %s=%r, expected %r from "
                    "the admitted Profile contract" %
                    (invocation, field, summary.get(field), expected))
    return errors


def _internal_member_run(run, member):
    return {
        "errors": list(run.get("errors") or []),
        "candidates": [_stable_candidate(receipt, member)
                       for receipt in run.get("candidates") or []],
        "details": run.get("details") or "",
        "source_command": None,
    }


def _write_close_evidence(root, batch, attempt_id, rows):
    """Persist full candidate detail once, born-cold (K12/09 compact).

    The evidence file carries every disposition row verbatim -- one JSON
    object per line, sorted keys -- under the cold namespace the hot
    catalog never deserializes.  The receipts that authorize the close
    bind it by path, byte size, record count, and content hash, so the
    detail stays auditable forever without ever again being a per-run
    parse cost.  Exclusive create: one attempt writes one evidence file.
    """
    token = attempt_id.rsplit("-", 2)[-2]
    relative = "%s/%s-%s.jsonl" % (
        kblib.RECEIPT_COLD_EVIDENCE_PREFIX, batch, token)
    full = os.path.join(root, relative)
    os.makedirs(os.path.dirname(full), mode=0o700, exist_ok=True)
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows)
    encoded = payload.encode("utf-8")
    with open(full, "x", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "candidate_evidence_path": relative,
        "candidate_evidence_sha256": kblib.sha256_bytes(encoded),
        "candidate_evidence_bytes": len(encoded),
        "candidate_evidence_records": len(rows),
    }


def _candidate_set_sha256(candidate_ids):
    """Fingerprint the exact accepted-candidate ID set, order-free."""
    return candidate_lifecycle.candidate_set_sha256(candidate_ids)


def _candidate_dispositions(candidates, accepted_ids, accepted_types,
                            durable_ids=None, durable_types=None):
    return candidate_lifecycle.disposition_candidates(
        candidates, accepted_ids, accepted_types,
        durable_ids or [], durable_types or [])


def _resolved_receipt(catalog, receipt_id):
    """Resolve a hot or sealed receipt body from the shared catalog."""
    if not isinstance(receipt_id, str) or not receipt_id:
        return None
    resolver = getattr(catalog, "resolve", None)
    entry = resolver(receipt_id) if callable(resolver) else catalog.get(receipt_id)
    return catalog_record(entry)


def _closed_transition_revision(catalog, item):
    revisions = []
    for receipt_id in item.get("transition_receipts") or []:
        receipt = _resolved_receipt(catalog, receipt_id)
        if (isinstance(receipt, dict) and
                receipt.get("after_state") == "closed" and
                isinstance(receipt.get("after_state_revision"), int) and
                not isinstance(receipt.get("after_state_revision"), bool)):
            revisions.append(receipt["after_state_revision"])
    return max(revisions) if revisions else None


def _load_candidate_evidence(root, attestation, label):
    relative = attestation.get("candidate_evidence_path")
    errors = close_gate.candidate_evidence_binding_errors(
        root, label, relative,
        attestation.get("candidate_evidence_sha256"),
        attestation.get("candidate_evidence_bytes"),
        attestation.get("candidate_evidence_records"),
    )
    if errors:
        return errors, []
    try:
        full = kblib.managed_repository_path(
            root, relative, kblib.RECEIPT_COLD_EVIDENCE_PREFIX,
            suffixes=(".jsonl",), must_exist=True)
        rows = _load_jsonl(full)
    except (OSError, UnicodeError, ValueError) as exc:
        return ["%s candidate evidence cannot be read: %s" % (label, exc)], []
    expected_count = attestation.get("accepted_candidate_count")
    if len(rows) != expected_count:
        errors.append("%s candidate evidence has %d row(s), expected %s" %
                      (label, len(rows), expected_count))
    ids = [row.get("candidate_id") for row in rows if isinstance(row, dict)]
    if (len(ids) != len(rows) or
            _candidate_set_sha256(ids) != attestation.get(
                "candidate_set_sha256")):
        errors.append("%s candidate evidence does not match its accepted-set "
                      "fingerprint" % label)
    return errors, rows


def _candidate_baseline(root, runtime, current_batch):
    """Resolve the immediately preceding successful close candidate set.

    Only current-contract close evidence may enter this runtime. A malformed
    baseline fails rather than falling back to an older close or format.
    """
    catalog = runtime.get("receipt_catalog") or {}
    closed = []
    for item_id, item in (runtime.get("items_by_id") or {}).items():
        if item_id == current_batch or item.get("state") != "closed":
            continue
        revision = _closed_transition_revision(catalog, item)
        if revision is not None:
            closed.append((revision, item_id, item))
    if not closed:
        return [], {
            "protocol": candidate_lifecycle.BASELINE_NONE,
            "attestation_receipt": None,
            "rows": [],
        }

    _revision, item_id, item = max(closed, key=lambda value: (value[0], value[1]))
    close_id = item.get("close_gate_receipt")
    close = _resolved_receipt(catalog, close_id)
    if not isinstance(close, dict):
        return ["latest closed batch %s close receipt %s is unresolvable" %
                (item_id, close_id)], None
    attestation_id = close.get("reviewer_attestation_receipt")
    attestation = _resolved_receipt(catalog, attestation_id)
    if not isinstance(attestation, dict):
        return ["latest closed batch %s reviewer attestation %s is "
                "unresolvable" % (item_id, attestation_id)], None
    if (close.get("tool") != TOOL or close.get("result") != "pass" or
            close.get("check") != GATE_CHECK):
        return ["latest closed batch %s does not bind a successful canonical "
                "close receipt" % item_id], None

    if (close.get("tool_version") != TOOL_VERSION or
            attestation.get("candidate_protocol") !=
            candidate_lifecycle.CANDIDATE_PROTOCOL):
        return [
            "latest closed batch %s uses a retired close or candidate "
            "contract" % item_id
        ], None

    label = "latest closed batch %s attestation %s" % (item_id, attestation_id)
    errors = candidate_lifecycle.continuation_attestation_errors(
        attestation, label)
    evidence_errors, rows = _load_candidate_evidence(root, attestation, label)
    errors.extend(evidence_errors)
    ordinary_rows = [
        row for row in rows
        if row.get("candidate_type") not in QUOTA_CANDIDATE_TYPES
    ]
    # Validate every ordinary row now, not only rows that happen to intersect
    # the current set.  A malformed baseline is not an invitation to select a
    # more convenient older close.
    _partition_errors, _carried, _fresh = \
        candidate_lifecycle.partition_against_baseline([], ordinary_rows)
    errors.extend(_partition_errors)
    if errors:
        return errors, None
    return [], {
        "protocol": candidate_lifecycle.BASELINE_CURRENT,
        "attestation_receipt": attestation_id,
        "rows": ordinary_rows,
    }


QUOTA_CANDIDATE_TYPES = frozenset((
    "check_vocab:priority-quota-P0", "check_vocab:priority-quota-P1",
))
def _quota_candidate_dispositions(candidates, exceptions, snapshot,
                                  policy_fingerprint):
    """Disposition priority-quota candidates through contract exceptions only.

    Authorization is an exact-arithmetic decision over the candidate's
    structured share -- `pages` and `total` as integers, cross-multiplied by
    `kblib.quota_share_within_limit` -- never a re-parse of display prose,
    where one rounding becomes a grant.  A candidate that arrives without its
    structured share fails closed.  Each accepted disposition seals the
    decision facts (decision ID, limit, scope, policy fingerprint, and the
    exact counts) so the close receipt carries what was authorized, by what
    bound, against which effective policy.
    """
    errors = []
    accepted = []
    for candidate in candidates:
        cls = candidate["candidate_type"].rsplit("-", 1)[1]
        share = candidate.get("priority_share")
        if (not isinstance(share, dict) or
                not isinstance(share.get("pages"), int) or
                not isinstance(share.get("total"), int)):
            errors.append(
                "priority-quota candidate (%s) carries no structured share; "
                "authorization never derives from display text" % cls)
            continue
        grants = exceptions.get(cls) or []
        chosen = None
        for entry in grants:
            if (entry.get("scope_kind") == "repository-snapshot" and
                    entry.get("scope_ref") != snapshot):
                continue
            if kblib.quota_share_within_limit(
                    share["pages"], share["total"], entry.get("limit")):
                chosen = entry
                break
        if chosen is None:
            errors.append(
                "priority-quota excess (%s, %d/%d) has no valid contract "
                "policy exception covering it; resolve by demotion, a "
                "profile quota registration, or a bounded policy exception "
                "via apply_contract_amendment" %
                (cls, share["pages"], share["total"]))
            continue
        disposition = dict(candidate)
        disposition["accepted_by"] = (
            "policy-exception:%s" % chosen.get("decision_id"))
        disposition["policy_exception"] = {
            "decision_id": chosen.get("decision_id"),
            "policy_id": chosen.get("policy_id"),
            "limit": chosen.get("limit"),
            "scope_kind": chosen.get("scope_kind"),
            "scope_ref": chosen.get("scope_ref"),
            "policy_fingerprint": policy_fingerprint,
            "pages": share["pages"],
            "total": share["total"],
        }
        accepted.append(disposition)
    return errors, accepted


def _member_receipt(field, run, snapshot, runtime, item, integrator,
                    reviewer, accepted_candidates, sequence, stage_plan,
                    obligation):
    plan = stage_plan["plan"]
    receipt = _make_receipt(
        TOOL, TOOL_VERSION, "closed_list_%s" % field,
        obligation["target"], "pass",
        run["details"], sequence,
        receipt_type_id=batch_close_contract.MEMBER_RECEIPT_TYPE_ID,
        root=runtime.get("root"),
    )
    type_counts = {}
    for entry in accepted_candidates:
        key = entry.get("candidate_type")
        type_counts[key] = type_counts.get(key, 0) + 1
    receipt.update({
        "task_id": runtime["queue"].get("task_id"),
        "batch_id": item.get("id"),
        "integrator_id": integrator,
        "reviewer_id": reviewer,
        "merged_snapshot_sha256": snapshot,
        "candidate_count": len(accepted_candidates),
        "candidate_type_counts": dict(sorted(type_counts.items())),
        "candidate_set_sha256": _candidate_set_sha256(
            [entry["candidate_id"] for entry in accepted_candidates]),
        "plan_id": stage_plan["audit_plan_id"],
        "audit_plan_path": stage_plan["audit_plan_path"],
        "audit_plan_sha256": stage_plan["audit_plan_sha256"],
        "obligation_id": obligation["obligation_id"],
        "opening_transition_receipt": plan["opening_transition_receipt"],
        "upstream_revision_id": plan["upstream_revision_id"],
        "active_standards_sha256": plan["active_standards_sha256"],
        "selected_profile_manifest": plan["selected_profile_manifest"],
        "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            plan["profile_contract_fingerprint"],
        # The raw producer evidence and its completed AuditReceipt discharge
        # one immutable AuditPlan obligation.  Persist the plan's fingerprint
        # mode here so every later consumer can prove the three digests were
        # taken at the required evidence boundary rather than merely finding
        # digest-shaped values on an otherwise unbound record.
        "fingerprint_binding": obligation["fingerprint_binding"],
        "artifact_fingerprint": snapshot,
        "dependency_fingerprint": plan["profile_snapshot_sha256"],
        "contract_fingerprint": plan["contract_snapshot_sha256"],
    })
    if run.get("source_command"):
        receipt["source_command"] = run["source_command"]
    return receipt


def _receipt_catalog_with(runtime, publications):
    """Project one unpublished multi-register close bundle.

    ``publications`` carries ``(relative_path, records)`` pairs in commit
    order.  The catalog records every candidate under its actual machine-owned
    register so the close consumer validates the same topology that will exist
    after publication.
    """
    # Build current-use validation from the adoption-filtered catalog, while
    # still reserving every historical ID so append-only evidence can never
    # collide with an invalidated record.
    full_catalog = runtime.get("receipt_catalog") or {}
    catalog = dict(receipt_catalogs.current_receipt_catalog(runtime))
    for relative_path, receipts in publications:
        for receipt in receipts:
            receipt_id = receipt.get("receipt_id")
            if receipt_id in full_catalog or receipt_id in catalog:
                raise ValueError(
                    "generated receipt ID collides with existing evidence")
            catalog[receipt_id] = (relative_path, receipt)
    return catalog


def _append_receipts(path, receipts):
    before = kblib.receipt_append_observation(path, receipts)
    outcome, error, _ = kblib.write_receipts_observed(
        path, receipts, before=before)
    # Recorded before the durability verdict is raised: these are the receipt
    # objects this run produced, and a `--json` caller that sees the failure
    # exit still learns exactly what was attempted.
    _JSON_REPORTER.record(receipts)
    if error is not None or outcome != "present":
        raise ReceiptPublicationUncertain(
            "receipt append outcome=%s error=%s" % (outcome, error))


def _publish_close_bundle(receipt_path, audit_receipt_path, close_records,
                          audit_records, commit_record):
    """Publish one close bundle with its aggregate as the final commit edge."""
    if not isinstance(commit_record, dict):
        raise ValueError("batch-close commit record must be a mapping")
    if close_records:
        _append_receipts(receipt_path, close_records)
    if audit_records:
        _append_receipts(audit_receipt_path, audit_records)
    _append_receipts(receipt_path, [commit_record])


def _failure_receipt(attempt_id, root, batch, details, snapshot=None,
                     runtime=None):
    receipt = _make_receipt(
        TOOL, TOOL_VERSION, GATE_CHECK, batch, "fail", details, 1,
        receipt_type_id=batch_close_contract.GATE_RECEIPT_TYPE_ID,
        root=root)
    receipt["receipt_id"] = attempt_id
    receipt["batch_id"] = batch
    if snapshot:
        receipt["merged_snapshot_sha256"] = snapshot
    if isinstance(runtime, dict) and runtime.get("queue"):
        receipt.update({
            "task_id": runtime["queue"].get("task_id"),
            "before_required_queue_sha256": runtime.get("queue_sha256"),
            "after_required_queue_sha256": runtime.get("queue_sha256"),
            "before_coverage_sha256": runtime.get("coverage_sha256"),
            "after_coverage_sha256": runtime.get("coverage_sha256"),
            "before_progress_sha256": runtime.get("progress_sha256"),
            "after_progress_sha256": runtime.get("progress_sha256"),
        })
    return receipt


def _print_candidates(candidates):
    for candidate in candidates:
        print("[CANDIDATE] %s" % candidate["candidate_id"])
        print("  type=%s" % candidate["candidate_type"])
        print("  member=%s target=%s" %
              (candidate["member"], candidate["target"]))
        print("  details=%s" % candidate["details"])


def main(argv=None):
    """CLI entry point; `--json` projects the produced receipts onto stdout."""
    return reporting.run_redirected_json(
        _JSON_REPORTER, lambda: _main(argv))


def _main(argv=None):
    parser = kblib.ArgumentParser(
        description="Run and publish the K12/09 batch-close evidence bundle")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True, help="merge-ready batch ID")
    parser.add_argument("--integrator", required=True,
                        help="declared integrator label recorded in the evidence")
    parser.add_argument("--reviewer", required=True,
                        help="declared reviewer label (must differ from integrator)")
    parser.add_argument("--review-attestation", required=True,
                        help="reviewer's explicit global-review statement")
    parser.add_argument("--accept-candidate-id", action="append", default=[],
                        help="accept this exact current candidate for this "
                        "close only")
    parser.add_argument("--accept-candidate-type", action="append", default=[],
                        help="accept every current candidate of this exact "
                        "tool:check type for this close only")
    parser.add_argument("--accept-while-unchanged-id", action="append",
                        default=[], help="accept this exact current candidate "
                        "and permit reuse while its observation is unchanged")
    parser.add_argument("--accept-while-unchanged-type", action="append",
                        default=[], help="expand this current exact type set "
                        "and permit those rows to be reused while unchanged")
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS,
                        help="repository-relative close evidence JSONL")
    parser.add_argument("--json", action="store_true", help=JSON_FLAG_HELP)
    args = parser.parse_args(argv)
    _JSON_REPORTER.begin(args.json)

    root = os.path.realpath(os.path.abspath(args.root))
    invocation_errors = []
    for label, value in (("integrator", args.integrator),
                         ("reviewer", args.reviewer)):
        if not IDENTITY_RE.fullmatch(value):
            invocation_errors.append("%s must match %s" %
                                     (label, IDENTITY_RE.pattern))
    if args.integrator.casefold() == args.reviewer.casefold():
        invocation_errors.append(
            "integrator and reviewer must use different declared labels")
    if len(args.review_attestation.strip()) < 8:
        invocation_errors.append("review attestation must be a substantive non-empty statement")
    if len(args.accept_candidate_id) != len(set(args.accept_candidate_id)):
        invocation_errors.append("--accept-candidate-id values must be unique")
    if len(args.accept_candidate_type) != len(set(args.accept_candidate_type)):
        invocation_errors.append("--accept-candidate-type values must be unique")
    if len(args.accept_while_unchanged_id) != len(set(
            args.accept_while_unchanged_id)):
        invocation_errors.append(
            "--accept-while-unchanged-id values must be unique")
    if len(args.accept_while_unchanged_type) != len(set(
            args.accept_while_unchanged_type)):
        invocation_errors.append(
            "--accept-while-unchanged-type values must be unique")
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
        audit_receipt_path = kblib.managed_repository_path(
            root, runtime_paths.AUDIT_RECEIPT_REGISTER_PATH,
            runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
    except (OSError, ValueError) as exc:
        invocation_errors.append("unsafe receipt path: %s" % exc)
        receipt_path = None
        audit_receipt_path = None
    if invocation_errors:
        for error in invocation_errors:
            print("[FAIL] %s" % error)
        return 1

    preflight = runtime_validation.validate_runtime(root)
    if preflight.get("errors"):
        for error in preflight["errors"]:
            print("[FAIL] runtime: %s" % error)
        return 1
    item = (preflight.get("items_by_id") or {}).get(args.batch)
    if item is None:
        print("[FAIL] batch %s does not exist" % args.batch)
        return 1
    standards_barrier = revalidation.current_attempt_evidence_barrier(
        preflight, args.batch)
    if standards_barrier:
        print("[FAIL] %s" % standards_barrier)
        return 1
    if item.get("state") != "merge-ready":
        print("[FAIL] batch %s is %s, not merge-ready" %
              (args.batch, item.get("state")))
        return 1
    pending = preflight.get("pending_delta_applies") or {}
    current = pending.get("current") or []
    if (pending.get("status") != "close-required" or len(current) != 1 or
            current[0].get("batch") != args.batch):
        print("[FAIL] batch %s has no unique current applied delta" %
              args.batch)
        return 1
    delta_apply_receipt = current[0].get("selected_receipt")
    pre_settlement = batch_settlement.current_settlement_report(
        preflight.get("coverage") or {}, args.batch)
    if pre_settlement["errors"]:
        for error in pre_settlement["errors"]:
            print("[FAIL] routed-gap settlement: %s" % error)
        return 1
    attempt_id = _make_receipt(
        TOOL, TOOL_VERSION, GATE_CHECK, args.batch, "candidate",
        "batch-close evidence is being produced", 9999,
        receipt_type_id=batch_close_contract.GATE_RECEIPT_TYPE_ID,
        root=root)["receipt_id"]
    pre_snapshot = kblib.repository_snapshot_sha256(root)
    operation = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "produce-batch-close-evidence",
        "task_id": preflight["queue"].get("task_id"),
        "batch_id": args.batch,
        "target": args.batch,
        "receipt_id": attempt_id,
        "receipt_path": args.receipts,
        "audit_receipt_path": runtime_paths.AUDIT_RECEIPT_REGISTER_PATH,
        "before_coverage_sha256": preflight.get("coverage_sha256"),
        "planned_after_coverage_sha256": preflight.get("coverage_sha256"),
        "before_queue_sha256": preflight.get("queue_sha256"),
        "planned_after_queue_sha256": preflight.get("queue_sha256"),
        "before_progress_sha256": preflight.get("progress_sha256"),
        "planned_after_progress_sha256": preflight.get("progress_sha256"),
        "repository_snapshot_sha256": pre_snapshot,
    }
    operation.update(batch_settlement.close_binding(pre_settlement))

    try:
        with kblib.runtime_write_lock(
                root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked_profile = preflight.get("queue", {}).get(
                    "selected_profile_manifest")
                profile_view, profile_view_errors = \
                    profile_view_contract.profile_load_authorized_view(
                        root, locked_profile)
                runtime = runtime_validation.validate_runtime(
                    root,
                    authorized_profile_view=(
                        profile_view if profile_view is not None else {}))
                state_anchor = _authoritative_state_anchor(runtime)
                own_relative = os.path.relpath(os.fspath(lease), root)
                locks = runtime.get("_writer_locks") or []
                own_locks = [lock for lock in locks
                             if lock.get("path") == own_relative]
                runtime_errors = list(profile_view_errors)
                runtime_errors.extend(runtime.get("errors") or [])
                if len(locks) != 1 or len(own_locks) != 1:
                    runtime_errors.append(
                        "runtime writer-lock inventory does not contain only "
                        "this invocation")
                if (runtime.get("coverage_sha256") !=
                        preflight.get("coverage_sha256") or
                        runtime.get("queue_sha256") !=
                        preflight.get("queue_sha256") or
                        runtime.get("progress_sha256") !=
                        preflight.get("progress_sha256")):
                    runtime_errors.append(
                        "canonical state changed before the close gate "
                        "acquired its lock")
                locked_settlement = batch_settlement.current_settlement_report(
                    runtime.get("coverage") or {}, args.batch)
                runtime_errors.extend(
                    "routed-gap settlement: %s" % error
                    for error in locked_settlement["errors"])
                if (batch_settlement.close_binding(locked_settlement) !=
                        batch_settlement.close_binding(pre_settlement)):
                    runtime_errors.append(
                        "routed-gap settlement changed before checks started")
                item = (runtime.get("items_by_id") or {}).get(args.batch)
                if item is None or item.get("state") != "merge-ready":
                    runtime_errors.append(
                        "batch is no longer merge-ready under lock")
                standards_barrier = \
                    revalidation.current_attempt_evidence_barrier(
                        runtime, args.batch)
                if standards_barrier:
                    runtime_errors.append(standards_barrier)
                locked_pending = runtime.get("pending_delta_applies") or {}
                locked_current = locked_pending.get("current") or []
                if (locked_pending.get("status") != "close-required" or
                        len(locked_current) != 1 or
                        locked_current[0].get("batch") != args.batch or
                        locked_current[0].get("selected_receipt") !=
                        delta_apply_receipt):
                    runtime_errors.append(
                        "current applied-delta binding changed under lock")
                snapshot = kblib.repository_snapshot_sha256(root)
                if snapshot != pre_snapshot:
                    runtime_errors.append(
                        "repository content changed before checks started")
                if profile_view is None:
                    corpus_plan_check = {
                        "required": False,
                        "triggers": [],
                        "receipt": None,
                        "binding": None,
                        "errors": ["selected Profile has no authorized view"],
                    }
                else:
                    corpus_plan_check = _corpus_plan_close_check(
                        root, runtime, item, snapshot,
                        authorized_profile_view=profile_view)
            _assert_authoritative_state_unchanged(root, state_anchor)
            if runtime_errors:
                failure = _failure_receipt(
                    attempt_id, root, args.batch,
                    "; ".join(runtime_errors), snapshot, runtime)
                _append_receipts(receipt_path, [failure])
                _assert_authoritative_state_unchanged(root, state_anchor)
                for error in runtime_errors:
                    print("[FAIL] %s" % error)
                return 1

            try:
                profile_evaluation = _profile_evaluation(
                    root, runtime, authorized_profile_view=profile_view)
                closed_list_registry = \
                    batch_close_contract.load_batch_close_closed_list(root)
                closed_list_rows = tuple(
                    dict(row) for row in closed_list_registry["members"])
                closed_list_fields = tuple(
                    row["member_id"] for row in closed_list_rows)
                if closed_list_fields != \
                        batch_close_contract.CLOSED_LIST_EVIDENCE_FIELDS:
                    raise ValueError(
                        "repository K12/09 registry differs from the current "
                        "batch-close producer contract")
                stage_plan = audit_evidence_runtime.resolve_stage_plan(
                    runtime, item, "post-delta-close",
                    required_state="merge-ready")
                post_delta_projection = \
                    batch_close_audit.resolve_post_delta_projection(
                        stage_plan, closed_list_rows,
                        profile_view["_contract"])
                metadata_contract = \
                    runtime_authority.runtime_metadata_execution_contract(
                        runtime)
                projection_rules = \
                    metadata_property_state.profile_gate_projection_rules(
                        root, profile_view["_contract"].extension_gates,
                        metadata_contract=metadata_contract,
                        authorized_profile_contract=
                            profile_view["_contract"])
                active_standards_view = runtime.get(
                    "_active_standards_authorized_view") or {}
                profile_consumer_admission, admission_errors = \
                    profile_admission.admission_from_evaluation(
                        root, profile_evaluation,
                        active_state_repo_path=active_standards_view.get(
                            "active_standards_path"),
                        active_state_sha256=active_standards_view.get(
                            "active_standards_sha256"))
                if admission_errors or profile_consumer_admission is None:
                    raise ValueError(
                        "cannot adapt shared Profile evaluation for batch "
                        "consumers: %s" % "; ".join(admission_errors))
                # One resolution, used everywhere in this close: whether the
                # optional Gate applies, the Configured values handed to
                # check_vocab, and exception currentness all come from this
                # single resolver call.
                quota_policy_object, quota_policy_fingerprint = \
                    _priority_policy(profile_evaluation)
                checks = {}
                links = _run_receipting_command(
                    [sys.executable, str(SCRIPT_DIR / "check_links.py"), root],
                    root, "check_links")
                checks["wiki_link_resolution"] = _tool_member_run(
                    links, "wiki_link_resolution")
                checks["structural_validity"] = _internal_member_run(
                    _structural_check(root, runtime), "structural_validity")
                checks["graph_and_duplicate_basenames"] = _internal_member_run(
                    _graph_and_basename_check(root),
                    "graph_and_duplicate_basenames")
                checks["coverage_file_count"] = _internal_member_run(
                    _coverage_file_count_check(root, runtime, item),
                    "coverage_file_count")
                checks["guidance_and_contract_continuity"] = \
                    _internal_member_run(
                        _guidance_contract_check(runtime),
                        "guidance_and_contract_continuity")
                residual_command, residual_binding = _profile_scan_command(
                    root, profile_evaluation)
                residual_control = _run_receipting_command(
                    residual_command + ["--positive-controls-only"], root,
                    "registered residual-content positive controls")
                residual = _run_receipting_command(
                    residual_command, root, "registered residual-content scan")
                residual_member = _tool_member_run(
                    residual, "registered_residual_content")
                residual_member["errors"].extend(
                    _positive_control_binding_errors(
                        residual_control, residual,
                        expected_binding=residual_binding))
                if residual_control.get("errors"):
                    residual_member["errors"].extend(
                        "positive-control invocation: %s" % error
                        for error in residual_control["errors"])
                checks["registered_residual_content"] = residual_member
                vocab_path = kblib.repository_path(
                    root, runtime_paths.VOCAB_ARTIFACT_PATH, must_exist=True,
                    reject_symlink=True)
                vocab_args = [
                    root, "--vocab", vocab_path,
                    # `profiles/` is excluded like `Card/`: both directories
                    # are governance control plane, and shipped
                    # example instances under profiles/examples/ carry their
                    # own vocabularies, so judging them against the selected
                    # profile's composed vocab.yaml fails every adopter's
                    # first close on foreign example values.
                    "--exclude", card_contract.load_schema(root)["directory"],
                    "--exclude", profile_layout_contract.PROFILES_DIRECTORY,
                ]
                if quota_policy_object["enabled"]:
                    vocab_args.extend([
                        "--quota-p0", str(quota_policy_object["resolved"][
                            "priority_quota.P0"]),
                        "--quota-p1", str(quota_policy_object["resolved"][
                            "priority_quota.P1"]),
                        "--policy-fingerprint",
                        str(quota_policy_fingerprint),
                    ])
                vocab = _run_inprocess_checker(
                    [sys.executable, str(SCRIPT_DIR / "check_vocab.py"),
                     *vocab_args], root, "check_vocab",
                    lambda receipt_path: check_vocab.main(
                        [*vocab_args, "--receipts", receipt_path],
                        authorized_admission=profile_consumer_admission))
                checks["controlled_vocabulary"] = _tool_member_run(
                    vocab, "controlled_vocabulary")
                contract_artifact = os.path.join(
                    root, *runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH.split("/"))
                if os.path.isfile(contract_artifact):
                    page_contract = _run_inprocess_checker(
                        [sys.executable,
                         str(SCRIPT_DIR / "check_page_contract.py"), root],
                        root, "check_page_contract",
                        lambda receipt_path: check_page_contract.run(
                            root, None,
                            runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH,
                            None, [],
                            False, receipt_path,
                            authorized_admission=
                                profile_consumer_admission))
                    checks["manifest_page_contract"] = \
                        _manifest_page_contract_member(
                            page_contract, item.get("manifest") or [],
                            "manifest_page_contract")
                else:
                    raise ValueError(
                        "Closed List item 8 requires a real current "
                        "page-contract-summary Gate receipt; compiled "
                        "contract %s is absent" %
                        runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH)
            except (OSError, UnicodeError, ValueError,
                    subprocess.SubprocessError) as exc:
                _assert_authoritative_state_unchanged(root, state_anchor)
                failure = _failure_receipt(
                    attempt_id, root, args.batch,
                    "batch-close checker invocation failed: %s" % exc,
                    snapshot, runtime)
                _append_receipts(receipt_path, [failure])
                _assert_authoritative_state_unchanged(root, state_anchor)
                print("[FAIL] %s" % exc)
                return 1

            check_errors = []
            check_errors.extend(
                "corpus_plan: %s" % error
                for error in corpus_plan_check["errors"])
            all_candidates = []
            for field in closed_list_fields:
                run = checks[field]
                check_errors.extend("%s: %s" % (field, error)
                                    for error in run["errors"])
                all_candidates.extend(run["candidates"])
            all_candidates.sort(
                key=lambda value: value["candidate_id"])
            candidate_ids = [entry["candidate_id"]
                             for entry in all_candidates]
            if len(candidate_ids) != len(set(candidate_ids)):
                check_errors.append(
                    "two checker findings produced the same stable "
                    "candidate ID")
            quota_candidates = [
                candidate for candidate in all_candidates
                if candidate["candidate_type"] in QUOTA_CANDIDATE_TYPES]
            ordinary_candidates = [
                candidate for candidate in all_candidates
                if candidate["candidate_type"] not in QUOTA_CANDIDATE_TYPES]
            baseline_errors, baseline = _candidate_baseline(
                root, runtime, args.batch)
            check_errors.extend(baseline_errors)
            if baseline is None:
                baseline = {
                    "protocol": candidate_lifecycle.BASELINE_NONE,
                    "attestation_receipt": None,
                    "rows": [],
                }
            partition_errors, carried, fresh_candidates = \
                candidate_lifecycle.partition_against_baseline(
                    ordinary_candidates, baseline["rows"])
            check_errors.extend(partition_errors)
            blocked_generic = sorted(
                (set(args.accept_candidate_type) |
                 set(args.accept_while_unchanged_type)) &
                QUOTA_CANDIDATE_TYPES)
            quota_ids = {candidate["candidate_id"]
                         for candidate in quota_candidates}
            blocked_generic += sorted(
                (set(args.accept_candidate_id) |
                 set(args.accept_while_unchanged_id)) & quota_ids)
            if blocked_generic:
                check_errors.append(
                    "priority-quota candidates cannot be accepted by the "
                    "generic disposition flags (%s); they resolve only "
                    "through a bounded contract policy exception" %
                    ", ".join(blocked_generic))
            disposition_errors, accepted, unaccepted = \
                _candidate_dispositions(
                    fresh_candidates, args.accept_candidate_id,
                    args.accept_candidate_type,
                    args.accept_while_unchanged_id,
                    args.accept_while_unchanged_type)
            check_errors.extend(disposition_errors)
            current_exceptions = _quota_exceptions(
                runtime, quota_policy_fingerprint)
            # Belt over the writer's braces: a configured policy's effective
            # ceilings -- exception where granted, configured quota where not
            # -- must be jointly admissible at CONSUMPTION too. An inactive
            # policy has no ceiling to relax, so a forged exception also fails
            # closed here (K00/07).
            quota_exception_inputs = [
                entry for entries in current_exceptions.values()
                for entry in entries
            ]
            if not quota_policy_object["enabled"]:
                # Inactivity invalidates the concept of a quota exception, not
                # merely exceptions carrying the current fingerprint. Leaving
                # a stale grant in the current Task Contract must not make it
                # silently legal; the amendment writer can remove it.
                quota_exception_inputs = (
                    ((runtime.get("progress") or {}).get("contract") or {}).get(
                        "policy_exceptions", []))
            _ceilings, ceiling_errors = (
                contract_exception_policy.effective_quota_ceilings(
                    quota_policy_object, quota_exception_inputs))
            check_errors.extend(ceiling_errors)
            quota_errors, quota_accepted = _quota_candidate_dispositions(
                quota_candidates, current_exceptions, snapshot,
                quota_policy_fingerprint)
            check_errors.extend(quota_errors)
            fresh_accepted = accepted + quota_accepted
            accepted = sorted(
                carried + fresh_accepted,
                key=lambda value: value["candidate_id"])
            after_checks = kblib.repository_snapshot_sha256(root)
            _assert_authoritative_state_unchanged(root, state_anchor)
            try:
                _assert_work_spec_unchanged(root, item)
            except (OSError, ValueError,
                    ReceiptPublicationUncertain) as exc:
                check_errors.append(str(exc))
            if after_checks != snapshot:
                check_errors.append("repository content changed while the Closed List ran")
            frozen_pages = ()
            if not check_errors:
                try:
                    frozen_pages = _freeze_manifest_pages(
                        root, item.get("manifest"), projection_rules)
                except (OSError, UnicodeError, ValueError) as exc:
                    check_errors.append(
                        "manifest review evidence could not be frozen: %s" %
                        exc)
            if check_errors:
                details = "; ".join(check_errors)
                failure = _failure_receipt(
                    attempt_id, root, args.batch, details, after_checks,
                    runtime)
                failure.update({
                    "task_id": runtime["queue"].get("task_id"),
                    "integrator_id": args.integrator,
                    "reviewer_id": args.reviewer,
                    "candidate_count": len(all_candidates),
                })
                try:
                    failure.update(_write_close_evidence(
                        root, args.batch, attempt_id, all_candidates))
                except OSError as exc:
                    failure["candidate_evidence_error"] = str(exc)
                _append_receipts(receipt_path, [failure])
                _assert_authoritative_state_unchanged(root, state_anchor)
                for error in check_errors:
                    print("[FAIL] %s" % error)
                _print_candidates(unaccepted or all_candidates)
                return 1

            # K12/09 raw producer evidence and the close aggregate belong to
            # the batch-close register.  Completed AuditReceipts have their
            # own canonical register.  Keep the groups separate from the
            # moment of construction so no later writer has to rediscover
            # ownership by inspecting record fields.
            close_records = []
            audit_records = []
            evidence = {}
            producer_evidence = {}
            final_evidence_records = {}
            for sequence, pair in enumerate(post_delta_projection, 1):
                field = pair["member"]["member_id"]
                member_candidates = [entry for entry in accepted
                                     if entry["member"] == field]
                if pair["member"]["evidence_kind"] == "gate-receipt":
                    receipt = checks[field].get("gate_evidence")
                    if not isinstance(receipt, dict):
                        raise ValueError(
                            "%s has no real Gate evidence" % field)
                    close_records.append(receipt)
                    producer_evidence[field] = receipt["receipt_id"]
                    final_evidence_records[field] = receipt
                else:
                    raw_receipt = _member_receipt(
                        field, checks[field], snapshot, runtime, item,
                        args.integrator, args.reviewer, member_candidates,
                        sequence, stage_plan, pair["obligation"])
                    full_receipt = \
                        batch_close_audit.build_full_audit_receipt(
                            stage_plan, pair, raw_receipt)
                    close_records.append(raw_receipt)
                    audit_records.append(full_receipt)
                    producer_evidence[field] = raw_receipt["receipt_id"]
                    final_evidence_records[field] = full_receipt
                evidence[field] = \
                    final_evidence_records[field]["receipt_id"]

            post_delta_closure = \
                batch_close_audit.build_post_delta_evidence_set(
                    stage_plan, post_delta_projection,
                    final_evidence_records, snapshot)
            producer_refs_by_obligation = {
                pair["obligation"]["obligation_id"]:
                    producer_evidence[pair["member"]["member_id"]]
                for pair in post_delta_projection
            }
            post_delta_reconciliation = \
                audit_evidence_runtime.reconciliation_from_bindings(
                    post_delta_closure["bindings"],
                    producer_refs_by_obligation)
            pre_merge_binding = audit_evidence_runtime.batch_review_evidence(
                runtime, item, required_state="merge-ready")
            pre_merge_reconciliation = {
                field: pre_merge_binding[field]
                for field in
                audit_reconciliation_contract.projection_fields()
            }
            complete_reconciliation = \
                audit_evidence_runtime.combine_plan_reconciliations(
                    pre_merge_reconciliation, post_delta_reconciliation)
            plan_binding = {
                "audit_plan_id": stage_plan["audit_plan_id"],
                "audit_plan_path": stage_plan["audit_plan_path"],
                "audit_plan_sha256": stage_plan["audit_plan_sha256"],
                "post_delta_evidence_bindings":
                    post_delta_closure["bindings"],
                "post_delta_evidence_count":
                    len(post_delta_closure["bindings"]),
                "post_delta_evidence_set_sha256":
                    post_delta_closure["evidence_set_sha256"],
                **complete_reconciliation,
            }

            attestation = _make_receipt(
                TOOL, TOOL_VERSION, "batch_global_review_attestation",
                args.batch, "pass", args.review_attestation.strip(),
                len(closed_list_fields) + 1,
                receipt_type_id=
                    batch_close_contract.REVIEW_ATTESTATION_RECEIPT_TYPE_ID,
                root=root)
            accepted_type_counts = {}
            for entry in accepted:
                key = entry.get("candidate_type")
                accepted_type_counts[key] = \
                    accepted_type_counts.get(key, 0) + 1
            evidence_binding = _write_close_evidence(
                root, args.batch, attempt_id, accepted)
            attestation.update({
                "task_id": runtime["queue"].get("task_id"),
                "batch_id": args.batch,
                "integrator_id": args.integrator,
                "reviewer_id": args.reviewer,
                "merged_snapshot_sha256": snapshot,
                "accepted_candidate_count": len(accepted),
                "accepted_candidate_types": sorted(set(
                    entry["candidate_type"] for entry in accepted)),
                "accepted_by_type_counts": dict(sorted(
                    accepted_type_counts.items())),
                "candidate_set_sha256": _candidate_set_sha256(
                    [entry["candidate_id"] for entry in accepted]),
                "candidate_protocol": candidate_lifecycle.CANDIDATE_PROTOCOL,
                "candidate_baseline_protocol": baseline["protocol"],
                "candidate_baseline_receipt":
                    baseline["attestation_receipt"],
                "carried_candidate_count": len(carried),
                "carried_candidate_set_sha256": _candidate_set_sha256(
                    [entry["candidate_id"] for entry in carried]),
                "fresh_candidate_count": len(fresh_accepted),
                "fresh_candidate_set_sha256": _candidate_set_sha256(
                    [entry["candidate_id"] for entry in fresh_accepted]),
                "candidate_dispositions": [
                    entry for entry in accepted
                    if str(entry.get("accepted_by", "")).startswith(
                        "policy-exception:")
                ],
            })
            attestation.update(plan_binding)
            attestation.update(evidence_binding)
            close_records.append(attestation)

            profile_bindings = {
                field: profile_view[field]
                for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS
            }
            page_review_receipts = []
            page_semantic_fingerprints = {
                page["path"]: page["semantic_content_sha256"]
                for page in frozen_pages
            }
            page_sequence = \
                len(closed_list_fields) + 2
            for offset, frozen_page in enumerate(frozen_pages):
                page_review = _make_receipt(
                    TOOL, TOOL_VERSION, "page_review_acceptance",
                    frozen_page["path"], "pass",
                    "declared reviewer accepted this exact semantic page "
                    "content in the merged-snapshot review",
                    page_sequence + offset,
                    receipt_type_id=
                        batch_close_contract.PAGE_REVIEW_RECEIPT_TYPE_ID,
                    root=root)
                checked_at = page_review.get("checked_at")
                if (not isinstance(checked_at, str) or
                        not checked_at.endswith("Z") or
                        len(checked_at) < 10):
                    raise ValueError(
                        "page review receipt has no canonical UTC checked_at")
                page_review.update({
                    "task_id": runtime["queue"].get("task_id"),
                    "batch_id": args.batch,
                    "integrator_id": args.integrator,
                    "reviewer_id": args.reviewer,
                    "reviewer_attestation_receipt":
                        attestation["receipt_id"],
                    "reviewed_on": checked_at[:10],
                    "semantic_content_sha256":
                        frozen_page["semantic_content_sha256"],
                    "metadata_execution_contract_fingerprint":
                        metadata_contract.contract_fingerprint,
                    "merged_snapshot_sha256": snapshot,
                    **profile_bindings,
                })
                close_records.append(page_review)
                page_review_receipts.append(page_review["receipt_id"])
            page_review_receipts = sorted(page_review_receipts)

            global_review = _make_receipt(
                TOOL, TOOL_VERSION, "batch_global_review", args.batch,
                "pass", "declared reviewer attestation recorded for the Closed List merged-snapshot review",
                (len(closed_list_fields) + 2 +
                 len(frozen_pages)),
                receipt_type_id=
                    batch_close_contract.GLOBAL_REVIEW_RECEIPT_TYPE_ID,
                root=root)
            global_review.update({
                "task_id": runtime["queue"].get("task_id"),
                "batch_id": args.batch,
                "integrator_id": args.integrator,
                "reviewer_id": args.reviewer,
                "merged_snapshot_sha256": snapshot,
                "reviewer_attestation_receipt": attestation["receipt_id"],
                "closed_list_evidence": evidence,
                "closed_list_producer_evidence": producer_evidence,
            })
            global_review.update(plan_binding)
            close_records.append(global_review)

            queue_details = "errors=0 candidates=0 remaining=%s ready=%s" % (
                runtime.get("remaining"),
                ",".join(runtime.get("ready") or []) or "none")
            consistency = queue_check_receipt.make_check_receipt(
                runtime, "pass", queue_details, "consistency")
            if consistency.get("repository_snapshot_sha256") != snapshot:
                raise ValueError(
                    "canonical Queue receipt observed a different "
                    "repository snapshot")
            close_records.append(consistency)

            corpus_plan_receipt = corpus_plan_check.get("receipt")
            if corpus_plan_receipt is not None:
                close_records.append(corpus_plan_receipt)

            aggregator = _make_receipt(
                TOOL, TOOL_VERSION, GATE_CHECK, args.batch, "pass",
                "Closed List checks passed and declared review attestation was recorded",
                len(closed_list_fields) + 4 +
                len(frozen_pages),
                receipt_type_id=batch_close_contract.GATE_RECEIPT_TYPE_ID,
                root=root)
            aggregator["receipt_id"] = attempt_id
            aggregator.update({
                "task_id": runtime["queue"].get("task_id"),
                "batch_id": args.batch,
                "integrator_id": args.integrator,
                "reviewer_id": args.reviewer,
                "queue_revision": runtime["queue"].get("queue_revision"),
                "queue_state_revision": runtime["queue"].get("state_revision"),
                "required_queue_sha256": runtime.get("queue_sha256"),
                "coverage_ledger_sha256": runtime.get("coverage_sha256"),
                "progress_ledger_sha256": runtime.get("progress_sha256"),
                "before_required_queue_sha256": runtime.get("queue_sha256"),
                "after_required_queue_sha256": runtime.get("queue_sha256"),
                "before_coverage_sha256": runtime.get("coverage_sha256"),
                "after_coverage_sha256": runtime.get("coverage_sha256"),
                "before_progress_sha256": runtime.get("progress_sha256"),
                "after_progress_sha256": runtime.get("progress_sha256"),
                "delta_sha256": item.get("delta_sha256"),
                "work_spec_path": item.get("work_spec_path"),
                "work_spec_sha256": item.get("work_spec_sha256"),
                "corpus_plan_required": corpus_plan_check["required"],
                "corpus_plan_triggers": corpus_plan_check["triggers"],
                "corpus_plan_receipt": (
                    corpus_plan_receipt.get("receipt_id")
                    if corpus_plan_receipt is not None else None),
                "delta_apply_receipt": delta_apply_receipt,
                "queue_consistency_receipt": consistency["receipt_id"],
                "merged_snapshot_sha256": snapshot,
                "reviewer_attestation_receipt": attestation["receipt_id"],
                "global_review_receipt": global_review["receipt_id"],
                "closed_list_evidence": evidence,
                "closed_list_producer_evidence": producer_evidence,
                "page_review_receipts": page_review_receipts,
                "page_review_receipt_count": len(page_review_receipts),
                "page_review_receipt_set_sha256":
                    _receipt_id_set_sha256(page_review_receipts),
                "metadata_execution_contract_fingerprint":
                    metadata_contract.contract_fingerprint,
                **profile_bindings,
            })
            aggregator.update(plan_binding)
            aggregator.update(batch_settlement.close_binding(
                locked_settlement))
            commit_records = [aggregator]

            _assert_authoritative_state_unchanged(root, state_anchor)
            _assert_work_spec_unchanged(root, item)
            before_publish = kblib.repository_snapshot_sha256(root)
            if before_publish != snapshot:
                raise ValueError(
                    "repository content changed before evidence publication")
            relative_receipt = os.path.relpath(receipt_path, root)
            relative_audit_receipt = os.path.relpath(
                audit_receipt_path, root)
            catalog = _receipt_catalog_with(
                runtime, (
                    (relative_receipt, close_records),
                    (relative_audit_receipt, audit_records),
                    (relative_receipt, commit_records),
                ))
            pre_errors = close_gate.close_gate_receipt_errors(
                catalog, attempt_id,
                item_id=args.batch,
                root=root,
                task_id=runtime["queue"].get("task_id"),
                queue_revision=runtime["queue"].get("queue_revision"),
                queue_state_revision=runtime["queue"].get(
                    "state_revision"),
                required_queue_sha256=runtime.get("queue_sha256"),
                coverage_ledger_sha256=runtime.get("coverage_sha256"),
                progress_ledger_sha256=runtime.get("progress_sha256"),
                delta_sha256=item.get("delta_sha256"),
                queue_consistency_receipt=consistency["receipt_id"],
                delta_apply_receipt=delta_apply_receipt,
                work_spec_path=item.get("work_spec_path"),
                work_spec_sha256=item.get("work_spec_sha256"),
                manifest=item.get("manifest"),
                selected_profile_manifest=runtime["queue"].get(
                    "selected_profile_manifest"),
                profile_snapshot_sha256=profile_view.get(
                    "profile_snapshot_sha256"),
                profile_contract_fingerprint=profile_view.get(
                    "profile_contract_fingerprint"),
                profile_load_inputs_sha256=profile_view.get(
                    "profile_load_inputs_sha256"),
                metadata_execution_contract_fingerprint=
                    metadata_contract.contract_fingerprint,
                authorized_profile_contract=profile_view.get("_contract"),
                authorized_metadata_contract=metadata_contract,
                authorized_page_semantic_fingerprints=
                    page_semantic_fingerprints,
                corpus_plan_required=corpus_plan_check["required"],
                corpus_plan_triggers=corpus_plan_check["triggers"],
                corpus_plan_expected_binding=corpus_plan_check["binding"],
                current_repository_snapshot_sha256=snapshot,
            )
            if pre_errors:
                raise ValueError(
                    "generated close evidence is invalid: %s" %
                    "; ".join(pre_errors))

            # This is the last potentially expensive step before append: the
            # exact inodes and bytes whose semantic digests appear in the
            # children must still be the objects frozen above.  Repository
            # content hashing alone cannot prove inode identity.
            try:
                _assert_manifest_pages_unchanged(root, frozen_pages)
            except ValueError as exc:
                failure = _failure_receipt(
                    attempt_id, root, args.batch, str(exc),
                    kblib.repository_snapshot_sha256(root), runtime)
                failure.update({
                    "task_id": runtime["queue"].get("task_id"),
                    "integrator_id": args.integrator,
                    "reviewer_id": args.reviewer,
                    "manifest_page_count": len(frozen_pages),
                    "metadata_execution_contract_fingerprint":
                        metadata_contract.contract_fingerprint,
                })
                _append_receipts(receipt_path, [failure])
                print("[FAIL] %s" % exc)
                return 1
            # Publish the aggregate last.  It is the only operation receipt
            # recognized by recovery and therefore the commit edge for this
            # multi-register bundle.  Any interruption before it leaves the
            # writer lock plus an absent operation receipt, which fails closed;
            # any escaping append/read-back error also preserves that lock.
            _publish_close_bundle(
                receipt_path, audit_receipt_path, close_records,
                audit_records, aggregator)
            _assert_manifest_pages_unchanged(
                root, frozen_pages, uncertain=True)
            _assert_authoritative_state_unchanged(root, state_anchor)
            _assert_work_spec_unchanged(root, item)
            after_publish = kblib.repository_snapshot_sha256(root)
            if after_publish != snapshot:
                raise ReceiptPublicationUncertain(
                    "repository content changed during evidence publication")
            persisted = runtime_validation.validate_runtime(
                root,
                authorized_profile_view=profile_view,
                authorized_active_standards_view=active_standards_view)
            _assert_authoritative_state_unchanged(root, state_anchor)
            persisted_errors = list(persisted.get("errors") or [])
            persisted_errors.extend(close_gate.close_gate_receipt_errors(
                receipt_catalogs.current_receipt_catalog(persisted), attempt_id,
                item_id=args.batch,
                root=root,
                task_id=runtime["queue"].get("task_id"),
                queue_revision=runtime["queue"].get("queue_revision"),
                queue_state_revision=runtime["queue"].get("state_revision"),
                required_queue_sha256=runtime.get("queue_sha256"),
                coverage_ledger_sha256=runtime.get("coverage_sha256"),
                progress_ledger_sha256=runtime.get("progress_sha256"),
                delta_sha256=item.get("delta_sha256"),
                queue_consistency_receipt=consistency["receipt_id"],
                delta_apply_receipt=delta_apply_receipt,
                work_spec_path=item.get("work_spec_path"),
                work_spec_sha256=item.get("work_spec_sha256"),
                manifest=item.get("manifest"),
                selected_profile_manifest=runtime["queue"].get(
                    "selected_profile_manifest"),
                profile_snapshot_sha256=profile_view.get(
                    "profile_snapshot_sha256"),
                profile_contract_fingerprint=profile_view.get(
                    "profile_contract_fingerprint"),
                profile_load_inputs_sha256=profile_view.get(
                    "profile_load_inputs_sha256"),
                metadata_execution_contract_fingerprint=
                    metadata_contract.contract_fingerprint,
                authorized_profile_contract=profile_view.get("_contract"),
                authorized_metadata_contract=metadata_contract,
                authorized_page_semantic_fingerprints=
                    page_semantic_fingerprints,
                corpus_plan_required=corpus_plan_check["required"],
                corpus_plan_triggers=corpus_plan_check["triggers"],
                corpus_plan_expected_binding=corpus_plan_check["binding"],
                current_repository_snapshot_sha256=after_publish,
            ))
            if persisted_errors:
                raise ReceiptPublicationUncertain(
                    "published evidence cannot be revalidated: %s" %
                    "; ".join(persisted_errors))

            _assert_authoritative_state_unchanged(root, state_anchor)
            print("[PASS] batch-close evidence published for %s" % args.batch)
            print("delta_apply_receipt=%s" % delta_apply_receipt)
            print("queue_consistency_receipt=%s" % consistency["receipt_id"])
            print("close_gate_receipt=%s" % attempt_id)
            print("reviewer_attestation_receipt=%s" %
                  attestation["receipt_id"])
            print("candidate_baseline_protocol=%s carried=%d fresh=%d" % (
                baseline["protocol"], len(carried), len(fresh_accepted)))
            print("update_queue_command=python3 Tools/update_queue.py %s --id %s --transition closed --gate-receipt %s --close-gate-receipt %s --delta-apply-receipt %s --expected-state-revision %s --expected-sha256 %s --actor-role integrator --apply" % (
                shlex.quote(root), shlex.quote(args.batch),
                shlex.quote(consistency["receipt_id"]),
                shlex.quote(attempt_id), shlex.quote(delta_apply_receipt),
                runtime["queue"].get("state_revision"),
                shlex.quote(runtime.get("queue_sha256"))))
            return 0
    except kblib.RuntimeStateLockedError as exc:
        print("[FAIL] %s" % exc)
        return 1
    except ReceiptPublicationUncertain as exc:
        print("[FAIL] %s" % exc)
        print("[RECOVERY] writer lock retained; run check_queue.py --resume-status before any new task")
        return 1
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        print("[FAIL] %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
