#!/usr/bin/env python3
"""Produce the canonical merged-snapshot evidence needed to close one batch.

The command is the production counterpart of K12/09.  It runs the seven-item
Closed List on the real repository, records an explicit declared-reviewer
attestation, obtains a canonical ``check_queue`` consistency receipt, and
publishes one batch-close aggregator that ``update_queue.py`` can consume.

All checks and receipt publication occur while the shared runtime writer lock
is held.  Repository content is hashed before and after checking, before
publication, and after publication.  A failed check publishes only one failed
attempt receipt, never a reusable subset of pass receipts.  An uncertain
append or a post-publication verification failure deliberately preserves the
writer lock for restart reconciliation.

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
"""

import argparse
import hashlib
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_links
import check_corpus_plan
import check_queue
import kblib


TOOL = "check_batch_close"
TOOL_VERSION = "1.4.0"
GATE_ID = "batch-close"
# The `Check` cell K00/12 registers for this Gate; every receipt this
# tool offers as gate evidence carries it verbatim.
GATE_CHECK = "batch_close_gate"
DEFAULT_RECEIPTS = ".cambium/receipts/batch-close.jsonl"
MAX_CHECK_SECONDS = 60
IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]*\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
SCRIPT_DIR = Path(__file__).resolve().parent


def _make_receipt(tool, tool_version, check, target, result, details, seq,
                  root=None):
    """Build one producer-era batch-close receipt with its stable Gate ID.

    ``root`` binds the Required Queue identity a Gate consumer compares
    against; outside a Cambium runtime those fields stay absent.
    """
    if tool != TOOL or tool_version != TOOL_VERSION:
        raise ValueError("check_batch_close receipt producer identity drift")
    receipt = kblib.make_receipt(
        tool, tool_version, check, target, result, details, seq, root=root)
    receipt["gate_id"] = GATE_ID
    return receipt


class ReceiptPublicationUncertain(RuntimeError):
    """Receipt bytes could not be proven complete and durable."""


AUTHORITATIVE_STATE_FILES = (
    ("coverage", check_queue.COVERAGE_PATH, "coverage_sha256"),
    ("required_queue", check_queue.QUEUE_PATH, "queue_sha256"),
    ("progress", check_queue.PROGRESS_PATH, "progress_sha256"),
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
        root, relative, check_queue.WORK_SPEC_PREFIX,
        suffixes=(".yaml",), must_exist=True,
    )
    actual = kblib.sha256_file(absolute)
    if actual != expected:
        raise ReceiptPublicationUncertain(
            "Batch Work Spec changed while the Closed List ran: "
            "%s expected=%s actual=%s" % (relative, expected, actual)
        )


def _repo_files(root, suffixes):
    """Yield deterministic repository files outside Git/Cambium state."""
    root = os.path.realpath(os.path.abspath(root))
    for current, directories, files in os.walk(root, topdown=True,
                                               followlinks=False):
        relative_dir = os.path.relpath(current, root)
        if relative_dir == ".":
            directories[:] = sorted(
                name for name in directories
                if name not in (".git", ".cambium")
            )
        else:
            directories[:] = sorted(directories)
        for name in sorted(files):
            if not name.lower().endswith(tuple(suffixes)):
                continue
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, root).replace(os.sep, "/")
            yield absolute, relative


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
        completed = subprocess.run(
            list(command) + ["--receipts", receipt_path],
            cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
            timeout=MAX_CHECK_SECONDS,
        )
        receipts = _load_jsonl(receipt_path) if os.path.exists(
            receipt_path) else []
    failures = [receipt for receipt in receipts
                if receipt.get("result") == "fail"]
    candidates = [receipt for receipt in receipts
                  if receipt.get("result") == "candidate"]
    valid_exit = completed.returncode in (0, 2)
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
        errors.append("checker exited %d" % completed.returncode)
    if failures:
        errors.extend("%s %s: %s" % (
            receipt.get("check"), receipt.get("target"),
            receipt.get("details")) for receipt in failures)
    if receipts and completed.returncode != expected_exit:
        errors.append("checker exit %d disagrees with receipt results (expected %d)" %
                      (completed.returncode, expected_exit))
    return {
        "label": label,
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "receipts": receipts,
        "candidates": candidates,
        "errors": errors,
    }


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
    return {
        "candidate_id": "candidate-sha256:%s" % digest,
        "candidate_type": "%s:%s" % (source_tool, check),
        "member": member,
        "target": target,
        "details": details,
    }


def _split_pipe_row(line):
    value = line.strip()
    if not value.startswith("|") or not value.endswith("|"):
        return []
    cells = re.split(r"(?<!\\)\|", value[1:-1])
    return [cell.replace("\\|", "|").strip() for cell in cells]


def _table_separator(cells):
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", ""))
        for cell in cells
    )


def _structural_check(root, runtime):
    errors = []
    markdown_count = yaml_count = table_count = 0
    manifest = runtime.get("queue", {}).get("selected_profile_manifest")
    profile_prefix = (os.path.dirname(manifest).strip("/") + "/"
                      if isinstance(manifest, str) and "/" in manifest
                      else "")
    for absolute, relative in _repo_files(root, (".md", ".yaml", ".yml")):
        lower = relative.lower()
        cambium_yaml = (
            bool(profile_prefix and relative.startswith(profile_prefix)) or
            relative.startswith("kernel/") or
            relative == "Tools/vocab.yaml"
        )
        if lower.endswith((".yaml", ".yml")) and not cambium_yaml:
            continue
        try:
            raw = Path(absolute).read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append("%s is not readable strict UTF-8: %s" %
                          (relative, exc))
            continue
        if lower.endswith((".yaml", ".yml")):
            # Cambium owns the restricted YAML grammar only for its own
            # machine contracts.  An adopter may keep unrelated application
            # YAML in the same Git repository; K12/09 must not silently turn
            # this gate into a general-purpose YAML policy.  Runtime state is
            # already parsed by check_queue and is outside the repository
            # snapshot, so this branch covers the selected profile, kernel
            # machine data, and the composed vocabulary only.
            yaml_count += 1
            try:
                value = kblib.parse_yaml_subset(text)
                if not isinstance(value, dict):
                    raise ValueError("top-level YAML must be a mapping")
            except (ValueError, kblib.YamlSubsetError) as exc:
                errors.append("%s has invalid restricted YAML: %s" %
                              (relative, exc))
            continue
        markdown_count += 1
        if text.startswith("---\n") or text.startswith("---\r\n"):
            frontmatter = kblib.extract_frontmatter(text)
            if frontmatter is None:
                errors.append("%s opens frontmatter without a closing fence" %
                              relative)
            else:
                try:
                    value = kblib.parse_yaml_subset(frontmatter)
                    if not isinstance(value, dict):
                        raise ValueError("frontmatter must be a mapping")
                except (ValueError, kblib.YamlSubsetError) as exc:
                    errors.append("%s has invalid frontmatter YAML: %s" %
                                  (relative, exc))

        fence = None
        fence_start = None
        fence_language = ""
        fence_body = []
        lines = text.splitlines()
        for line_number, line in enumerate(lines, 1):
            match = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", line)
            if not match:
                if fence is not None:
                    fence_body.append(line)
                continue
            marker, tail = match.groups()
            if fence is None:
                fence = marker
                fence_start = line_number
                fence_language = tail.strip().split(None, 1)[0].lower() \
                    if tail.strip() else ""
                fence_body = []
            elif (marker[0] == fence[0] and len(marker) >= len(fence) and
                  not tail.strip()):
                fence = None
                fence_start = None
                fence_language = ""
                fence_body = []
            else:
                fence_body.append(line)
        if fence is not None:
            errors.append("%s:%d has an unclosed %s fence" %
                          (relative, fence_start, fence[0] * len(fence)))

        table_lines = kblib.strip_code(text).splitlines()
        index = 0
        while index < len(table_lines):
            if not (table_lines[index].strip().startswith("|") and
                    table_lines[index].strip().endswith("|")):
                index += 1
                continue
            start = index
            block = []
            while (index < len(table_lines) and
                   table_lines[index].strip().startswith("|") and
                   table_lines[index].strip().endswith("|")):
                block.append(_split_pipe_row(table_lines[index]))
                index += 1
            if len(block) < 2:
                continue
            table_count += 1
            width = len(block[0])
            if not _table_separator(block[1]):
                errors.append("%s:%d table has no valid delimiter row" %
                              (relative, start + 1))
                continue
            for offset, cells in enumerate(block):
                if len(cells) != width:
                    errors.append("%s:%d table has %d columns, expected %d" %
                                  (relative, start + offset + 1,
                                   len(cells), width))
    details = ("strict_utf8=pass markdown=%d cambium_yaml=%d tables=%d "
               "structural_errors=%d" %
               (markdown_count, yaml_count, table_count, len(errors)))
    return {"errors": errors, "candidates": [], "details": details}


def _markdown_graph_projection(root):
    """Return the canonical in-memory graph derived from Markdown wiki links.

    The projection deliberately has no repository-JSON input.  Item 3 owns a
    graph *projection*, not every JSON document that an adopting repository
    may contain.  Link validity remains item 1's responsibility; unresolved
    edges are represented here as data rather than promoted to a second link
    failure.
    """
    files = list(_repo_files(root, (".md",)))
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


def _corpus_plan_close_check(root, runtime, item, snapshot):
    """Return the conditional R13/planning-manifest close child receipt.

    Route selection is task-level in Progress.  A batch also becomes
    applicable when its exact Queue manifest changes the selected Corpus
    Planning slot, a bound planning artifact, or a path explicitly named by a
    validated planning relation.  Unrelated batches do not acquire a new gate
    merely because the repository contains a plan.
    """
    result = check_corpus_plan.validate_corpus_plan(root)
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
    if "R13" in triggers and result.get("applicability") != "configured":
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
                require_configured="R13" in triggers,
            ))
            if not errors:
                binding = {
                    field: receipt.get(field)
                    for field in check_corpus_plan.PASS_RECEIPT_BINDING_FIELDS
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


def _manifest_path(root, runtime):
    relative = runtime.get("queue", {}).get("selected_profile_manifest")
    return kblib.repository_path(root, relative, must_exist=True,
                                 reject_symlink=True)


def _profile_scan_command(root, runtime):
    manifest_path = _manifest_path(root, runtime)
    manifest_text = Path(manifest_path).read_text(encoding="utf-8")
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = bindings.get("Registered Scan Registry")
    if not binding:
        raise ValueError("selected profile has no Registered Scan Registry binding")
    profile_dir = os.path.dirname(manifest_path)
    kind, resolved = kblib.resolve_profile_binding(binding, root, profile_dir)
    if kind != "path":
        raise ValueError("Registered Scan Registry binding is not a profile file: %s" %
                         kind)
    text = Path(resolved).read_text(encoding="utf-8")
    rows = [_split_pipe_row(line) for line in text.splitlines()
            if line.strip().startswith("|") and line.strip().endswith("|")]
    selected = []
    for cells in rows:
        if len(cells) < 6 or _table_separator(cells):
            continue
        if cells[0] == "Stable Scan ID":
            continue
        if "K12/09 item 6" in cells[1]:
            selected.append(cells)
    if len(selected) != 1:
        raise ValueError("Registered Scan Registry must contain exactly one K12/09 item 6 row; found %d" %
                         len(selected))
    cell = selected[0][3]
    matches = re.findall(r"`([^`]+)`", cell)
    command_text = matches[0] if len(matches) == 1 else cell.strip()
    tokens = shlex.split(command_text)
    if len(tokens) < 3 or os.path.basename(tokens[0]) not in (
            "python", "python3"):
        raise ValueError("registered verifier must be a Python command")
    script_relative = tokens[1]
    if (not script_relative.startswith("Tools/") or
            not script_relative.endswith(".py")):
        raise ValueError("registered verifier must be a repository Tools/*.py script")
    script = kblib.repository_path(root, script_relative, must_exist=True,
                                   reject_symlink=True)
    descriptor = os.lstat(script)
    if not stat.S_ISREG(descriptor.st_mode) or descriptor.st_nlink != 1:
        raise ValueError("registered verifier must be a singly-linked regular file")
    if tokens[2] != ".":
        raise ValueError("registered verifier must bind the whole repository root as '.'")
    if "--receipts" in tokens:
        raise ValueError("registered verifier command must leave --receipts to the gate")
    if "--positive-controls-only" in tokens:
        raise ValueError(
            "registered verifier command must leave --positive-controls-only "
            "to the gate")
    forbidden = {";", "&&", "||", "|", ">", ">>", "<"}
    if forbidden.intersection(tokens):
        raise ValueError("registered verifier command contains a shell operator")
    command = [sys.executable, script, os.path.realpath(os.path.abspath(root))]
    command.extend(tokens[3:])
    return command


def _priority_quotas(root, runtime):
    p0, p1 = 15.0, 35.0
    overrides = kblib.profile_execution_default_overrides(
        Path(_manifest_path(root, runtime)).read_text(encoding="utf-8"))
    for item in ("priority_quota.P0", "priority_quota.P1"):
        if item not in overrides:
            continue
        try:
            number = float(overrides[item].strip("% "))
        except ValueError:
            raise ValueError("%s override is not a numeric percent" % item)
        if not 0 <= number < 100:
            raise ValueError(
                "%s override is not a corpus share at least 0 and under 100"
                % item)
        if item.endswith("P0"):
            p0 = number
        else:
            p1 = number
    return p0, p1


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


def _positive_control_binding_errors(control_run, production_run):
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
    return errors


def _internal_member_run(run, member):
    return {
        "errors": list(run.get("errors") or []),
        "candidates": [_stable_candidate(receipt, member)
                       for receipt in run.get("candidates") or []],
        "details": run.get("details") or "",
        "source_command": None,
    }


def _candidate_dispositions(candidates, accepted_ids, accepted_types):
    current_ids = {candidate["candidate_id"] for candidate in candidates}
    current_types = {candidate["candidate_type"] for candidate in candidates}
    stale_ids = sorted(set(accepted_ids) - current_ids)
    stale_types = sorted(set(accepted_types) - current_types)
    unaccepted = [candidate for candidate in candidates
                  if candidate["candidate_id"] not in accepted_ids and
                  candidate["candidate_type"] not in accepted_types]
    errors = []
    if stale_ids:
        errors.append("accepted candidate IDs are absent from this snapshot: %s" %
                      ", ".join(stale_ids))
    if stale_types:
        errors.append("accepted candidate types are absent from this snapshot: %s" %
                      ", ".join(stale_types))
    if unaccepted:
        errors.append("%d current candidate(s) lack an explicit ID/type disposition" %
                      len(unaccepted))
    accepted = []
    for candidate in candidates:
        if candidate in unaccepted:
            continue
        disposition = dict(candidate)
        disposition["accepted_by"] = (
            "candidate-id" if candidate["candidate_id"] in accepted_ids
            else "candidate-type")
        accepted.append(disposition)
    return errors, accepted, unaccepted


def _member_receipt(field, run, snapshot, runtime, item, integrator,
                    reviewer, accepted_candidates, sequence):
    receipt = _make_receipt(
        TOOL, TOOL_VERSION, "closed_list_%s" % field, ".", "pass",
        run["details"], sequence, root=runtime.get("root"),
    )
    receipt.update({
        "task_id": runtime["queue"].get("task_id"),
        "batch_id": item.get("id"),
        "integrator_id": integrator,
        "reviewer_id": reviewer,
        "merged_snapshot_sha256": snapshot,
        "candidate_evidence": accepted_candidates,
    })
    if run.get("source_command"):
        receipt["source_command"] = run["source_command"]
    return receipt


def _receipt_catalog_with(runtime, relative_path, receipts):
    # Build current-use validation from the adoption-filtered catalog, while
    # still reserving every historical ID so append-only evidence can never
    # collide with an invalidated record.
    full_catalog = runtime.get("receipt_catalog") or {}
    catalog = dict(check_queue.current_receipt_catalog(runtime))
    for receipt in receipts:
        receipt_id = receipt.get("receipt_id")
        if receipt_id in full_catalog or receipt_id in catalog:
            raise ValueError("generated receipt ID collides with existing evidence")
        catalog[receipt_id] = (relative_path, receipt)
    return catalog


def _append_receipts(path, receipts):
    before = kblib.receipt_append_observation(path, receipts)
    outcome, error, _ = kblib.write_receipts_observed(
        path, receipts, before=before)
    if error is not None or outcome != "present":
        raise ReceiptPublicationUncertain(
            "receipt append outcome=%s error=%s" % (outcome, error))


def _failure_receipt(attempt_id, root, batch, details, snapshot=None,
                     runtime=None):
    receipt = _make_receipt(
        TOOL, TOOL_VERSION, GATE_CHECK, batch, "fail", details, 1,
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
    parser = argparse.ArgumentParser(
        description="Run and publish the K12/09 batch-close evidence bundle")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--batch", required=True, help="merge-ready batch ID")
    parser.add_argument("--integrator", required=True,
                        help="declared integrator label recorded in the evidence")
    parser.add_argument("--reviewer", required=True,
                        help="declared reviewer label (must differ from integrator)")
    parser.add_argument("--review-attestation", required=True,
                        help="reviewer's explicit global-review statement")
    parser.add_argument("--accept-candidate-id", action="append", default=[])
    parser.add_argument("--accept-candidate-type", action="append", default=[])
    parser.add_argument("--receipts", default=DEFAULT_RECEIPTS,
                        help="repository-relative close evidence JSONL")
    args = parser.parse_args(argv)

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
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
    except (OSError, ValueError) as exc:
        invocation_errors.append("unsafe receipt path: %s" % exc)
        receipt_path = None
    if invocation_errors:
        for error in invocation_errors:
            print("[FAIL] %s" % error)
        return 1

    preflight = check_queue.validate_runtime(root)
    if preflight.get("errors"):
        for error in preflight["errors"]:
            print("[FAIL] runtime: %s" % error)
        return 1
    item = (preflight.get("items_by_id") or {}).get(args.batch)
    if item is None:
        print("[FAIL] batch %s does not exist" % args.batch)
        return 1
    standards_barrier = check_queue.current_attempt_evidence_barrier(
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
        print("[FAIL] batch %s has no unique current-compatible applied delta" %
              args.batch)
        return 1
    delta_apply_receipt = current[0].get("selected_receipt")
    attempt_id = _make_receipt(
        TOOL, TOOL_VERSION, GATE_CHECK, args.batch, "candidate",
        "batch-close evidence is being produced", 9999,
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
        "before_coverage_sha256": preflight.get("coverage_sha256"),
        "planned_after_coverage_sha256": preflight.get("coverage_sha256"),
        "before_required_queue_sha256": preflight.get("queue_sha256"),
        "planned_after_required_queue_sha256": preflight.get("queue_sha256"),
        "before_progress_sha256": preflight.get("progress_sha256"),
        "planned_after_progress_sha256": preflight.get("progress_sha256"),
        "repository_snapshot_sha256": pre_snapshot,
    }

    try:
        with kblib.runtime_write_lock(
                root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                runtime = check_queue.validate_runtime(root)
                state_anchor = _authoritative_state_anchor(runtime)
                own_relative = os.path.relpath(os.fspath(lease), root)
                locks = runtime.get("writer_locks") or []
                own_locks = [lock for lock in locks
                             if lock.get("path") == own_relative]
                runtime_errors = list(runtime.get("errors") or [])
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
                item = (runtime.get("items_by_id") or {}).get(args.batch)
                if item is None or item.get("state") != "merge-ready":
                    runtime_errors.append(
                        "batch is no longer merge-ready under lock")
                standards_barrier = \
                    check_queue.current_attempt_evidence_barrier(
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
                corpus_plan_check = _corpus_plan_close_check(
                    root, runtime, item, snapshot)
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
                p0, p1 = _priority_quotas(root, runtime)
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
                residual_command = _profile_scan_command(root, runtime)
                residual_control = _run_receipting_command(
                    residual_command + ["--positive-controls-only"], root,
                    "registered residual-content positive controls")
                residual = _run_receipting_command(
                    residual_command, root, "registered residual-content scan")
                residual_member = _tool_member_run(
                    residual, "registered_residual_content")
                residual_member["errors"].extend(
                    _positive_control_binding_errors(
                        residual_control, residual))
                if residual_control.get("errors"):
                    residual_member["errors"].extend(
                        "positive-control invocation: %s" % error
                        for error in residual_control["errors"])
                checks["registered_residual_content"] = residual_member
                vocab_path = kblib.repository_path(
                    root, "Tools/vocab.yaml", must_exist=True,
                    reject_symlink=True)
                vocab = _run_receipting_command(
                    # `profiles/` is excluded like `kernel/Cards`: profile
                    # directories are governance control plane, and shipped
                    # example instances under profiles/examples/ carry their
                    # own vocabularies, so judging them against the selected
                    # profile's composed vocab.yaml fails every adopter's
                    # first close on foreign example values.
                    [sys.executable, str(SCRIPT_DIR / "check_vocab.py"), root,
                     "--vocab", vocab_path,
                     "--exclude", "kernel/Cards",
                     "--exclude", "profiles",
                     "--quota-p0", str(p0), "--quota-p1", str(p1)],
                    root, "check_vocab")
                checks["controlled_vocabulary"] = _tool_member_run(
                    vocab, "controlled_vocabulary")
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
            for field in check_queue.CLOSED_LIST_EVIDENCE_FIELDS:
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
            disposition_errors, accepted, unaccepted = \
                _candidate_dispositions(
                    all_candidates, args.accept_candidate_id,
                    args.accept_candidate_type)
            check_errors.extend(disposition_errors)
            after_checks = kblib.repository_snapshot_sha256(root)
            _assert_authoritative_state_unchanged(root, state_anchor)
            try:
                _assert_work_spec_unchanged(root, item)
            except (OSError, ValueError,
                    ReceiptPublicationUncertain) as exc:
                check_errors.append(str(exc))
            if after_checks != snapshot:
                check_errors.append("repository content changed while the Closed List ran")
            if check_errors:
                details = "; ".join(check_errors)
                failure = _failure_receipt(
                    attempt_id, root, args.batch, details, after_checks,
                    runtime)
                failure.update({
                    "task_id": runtime["queue"].get("task_id"),
                    "integrator_id": args.integrator,
                    "reviewer_id": args.reviewer,
                    "candidate_evidence": all_candidates,
                })
                _append_receipts(receipt_path, [failure])
                _assert_authoritative_state_unchanged(root, state_anchor)
                for error in check_errors:
                    print("[FAIL] %s" % error)
                _print_candidates(unaccepted or all_candidates)
                return 1

            records = []
            evidence = {}
            for sequence, field in enumerate(
                    check_queue.CLOSED_LIST_EVIDENCE_FIELDS, 1):
                member_candidates = [entry for entry in accepted
                                     if entry["member"] == field]
                receipt = _member_receipt(
                    field, checks[field], snapshot, runtime, item,
                    args.integrator, args.reviewer, member_candidates,
                    sequence)
                records.append(receipt)
                evidence[field] = receipt["receipt_id"]

            attestation = _make_receipt(
                TOOL, TOOL_VERSION, "batch_global_review_attestation",
                args.batch, "pass", args.review_attestation.strip(), 8,
                root=root)
            attestation.update({
                "task_id": runtime["queue"].get("task_id"),
                "batch_id": args.batch,
                "integrator_id": args.integrator,
                "reviewer_id": args.reviewer,
                "merged_snapshot_sha256": snapshot,
                "accepted_candidate_ids": [entry["candidate_id"]
                                           for entry in accepted],
                "accepted_candidate_types": sorted(set(
                    entry["candidate_type"] for entry in accepted)),
                "candidate_dispositions": accepted,
            })
            records.append(attestation)

            global_review = _make_receipt(
                TOOL, TOOL_VERSION, "batch_global_review", args.batch,
                "pass", "declared reviewer attestation recorded for the seven-member merged-snapshot review",
                9, root=root)
            global_review.update({
                "task_id": runtime["queue"].get("task_id"),
                "batch_id": args.batch,
                "integrator_id": args.integrator,
                "reviewer_id": args.reviewer,
                "merged_snapshot_sha256": snapshot,
                "reviewer_attestation_receipt": attestation["receipt_id"],
                "closed_list_evidence": evidence,
            })
            records.append(global_review)

            queue_details = "errors=0 candidates=0 remaining=%s ready=%s" % (
                runtime.get("remaining"),
                ",".join(runtime.get("ready") or []) or "none")
            consistency = check_queue.make_check_receipt(
                runtime, "pass", queue_details, "consistency")
            if consistency.get("repository_snapshot_sha256") != snapshot:
                raise ValueError(
                    "canonical Queue receipt observed a different "
                    "repository snapshot")
            records.append(consistency)

            corpus_plan_receipt = corpus_plan_check.get("receipt")
            if corpus_plan_receipt is not None:
                records.append(corpus_plan_receipt)

            aggregator = _make_receipt(
                TOOL, TOOL_VERSION, GATE_CHECK, args.batch, "pass",
                "seven Closed List checks passed and declared review attestation was recorded",
                11, root=root)
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
            })
            records.append(aggregator)

            _assert_authoritative_state_unchanged(root, state_anchor)
            _assert_work_spec_unchanged(root, item)
            before_publish = kblib.repository_snapshot_sha256(root)
            if before_publish != snapshot:
                raise ValueError(
                    "repository content changed before evidence publication")
            relative_receipt = os.path.relpath(receipt_path, root)
            catalog = _receipt_catalog_with(
                runtime, relative_receipt, records)
            pre_errors = check_queue.close_gate_receipt_errors(
                catalog, attempt_id,
                item_id=args.batch,
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
                selected_profile_manifest=runtime["queue"].get(
                    "selected_profile_manifest"),
                corpus_plan_required=corpus_plan_check["required"],
                corpus_plan_triggers=corpus_plan_check["triggers"],
                corpus_plan_expected_binding=corpus_plan_check["binding"],
                current_repository_snapshot_sha256=snapshot,
            )
            if pre_errors:
                raise ValueError(
                    "generated close evidence is invalid: %s" %
                    "; ".join(pre_errors))

            _append_receipts(receipt_path, records)
            _assert_authoritative_state_unchanged(root, state_anchor)
            _assert_work_spec_unchanged(root, item)
            after_publish = kblib.repository_snapshot_sha256(root)
            if after_publish != snapshot:
                raise ReceiptPublicationUncertain(
                    "repository content changed during evidence publication")
            persisted = check_queue.validate_runtime(root)
            _assert_authoritative_state_unchanged(root, state_anchor)
            persisted_errors = list(persisted.get("errors") or [])
            persisted_errors.extend(check_queue.close_gate_receipt_errors(
                check_queue.current_receipt_catalog(persisted), attempt_id,
                item_id=args.batch,
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
                selected_profile_manifest=runtime["queue"].get(
                    "selected_profile_manifest"),
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
