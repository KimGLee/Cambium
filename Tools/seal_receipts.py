#!/usr/bin/env python3
"""Seal verified frozen receipt history into the cold chain (K12/07).

The incident this tool exists for: an adopter's shared close register grew
past sixty megabytes because every close attempt appended full candidate
detail, and every later state transition re-deserialized all of it -- the
audit trail's own weight priced the runtime out of its execution channel.
Append-only is a property of records, not of parse cost; this tool moves
already-verified rows out of the hot path while keeping every byte and
every receipt ID resolvable forever.

What sealing IS: a verified checkpoint.  The tool refuses to run unless the
complete runtime validation -- which revalidates every closed batch's
frozen bundle field by field -- passes right now.  Only then does it move
rows verbatim into ``cold/segments/``, append one manifest entry per
segment and one thin projection per receipt, and rewrite each hot register
without the sealed rows.  What drops from the per-run cost afterwards is
the *deserialization* of those bodies; their integrity does not drop from
it.  Every later consistency run re-hashes every segment, re-proves every
projection against the sealed line it names, and re-proves both cold
registers against this tool's own receipt, which is the chain's root of
trust and never seals.

What sealing is NOT: deletion, redaction, or a second chance.  A sealed row
that later goes missing or changes fails every consistency run closed.
Rows this version never seals: the global transition history, Standards
adoptions, contract and operational amendments, this tool's own receipts,
the Standards-revalidation aggregate a recorded Queue transition consumed,
any receipt bound to a batch that is not terminally closed, and every receipt
currently referenced by Coverage ``property_state``.  A producer batch may be
closed while its review/content-change receipt is still live owner evidence;
only a later owner transition that replaces the pointer makes that row cold.

SUPPORTED OPERATING BOUNDARY -- read before ``--apply``.

Sealing is a MAINTENANCE-WINDOW operation, not a concurrent one.  It is the
only operation in this runtime that removes bytes from a register, and this
version does not attempt to be safe against arbitrary concurrent writers.
``--apply`` may be run only during a declared quiet window, and the operator
is responsible for confirming beforehand that no other Cambium or adopter
writer, checker, or receipt appender is running anywhere against this
repository.

The receipt append mutex (:func:`kblib.receipt_append_mutex`) is retained as
a guard against accidental concurrent operation.  It makes the common
mistake fail loudly instead of corrupting evidence.  It is NOT a proof of
mutual exclusion under arbitrary concurrency, and this tool does not claim
one: it is re-entrant per process, so it does not separate threads or
forked children of one process; it binds only writers that go through
``kblib.write_receipts``; and it does not defend its own marker paths
against aliasing.  Read it as a seatbelt, not as a concurrency protocol.

Interruption.  The plan is computed from a clean full validation and every
byte it was computed from is compared again inside the writer lock, so
drift aborts before the first write.  Publication is journalled: a
``begin`` row and a hash-bound pending record land before the first segment
byte, and ``complete`` lands only after every postcondition is re-proved.
``--reconcile --apply`` is AUTOMATIC RECOVERY OVER THE IMPLEMENTED PATHS --
the publication steps this tool itself performs.  Any other interruption is
required only to fail closed and preserve recoverable evidence; finishing
it is an operator task, and the runbook is in ``Tools/README.md`` under
"Sealing maintenance window and recovery runbook".

Scope (v1 seal classes):
  close-bundles   rows in shared registers whose ``batch_id``/``target``
                  is a closed, transition-anchored batch (the aggregate
                  close registers -- where the weight lives)
  batch-files     whole per-batch registers of closed batches
                  (``delta-apply-*``, single-receipt ``audit-*`` files)
  page-snapshots  page-contract snapshot registers (advisory history)

Review registers (``batch-*-review``, ``batch-*-checks``) deliberately
stay hot in v1: they carry activation gates and page evidence whose
consumers still perform live field revalidation, and they are small.
"""

import contextlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import check_queue

TOOL = "seal_receipts"
TOOL_VERSION = "1.4.0"
SEAL_RECEIPTS_PATH = ".cambium/receipts/seal-receipts.jsonl"
COLD_PENDING_PREFIX = ".cambium/receipts/cold/pending"
RECEIPTS_ROOT = ".cambium/receipts"

NEVER_SEAL_BASENAMES = frozenset((
    "queue-transitions.jsonl",
    "standards-adoptions.jsonl",
    "contract-amendments.jsonl",
    "amendments.jsonl",
    "seal-receipts.jsonl",
))
REVIEW_REGISTER_RE = re.compile(
    r"batch-.*-(review|checks|links)\.jsonl\Z")
PAGE_SNAPSHOT_RE = re.compile(r"page-contract-.*\.jsonl\Z")
BATCH_FILE_RE = re.compile(
    r"(delta-apply-(?P<delta_batch>.+)|audit-[a-z_]+-[0-9TZ]+-[0-9a-f]+-[0-9]{4})"
    r"\.jsonl\Z")


# ---------------------------------------------------------------------------
# `--json` output (machine-readable receipts)
#
# Purely additive: without the flag not one byte of this tool's behaviour
# moves.  With it, everything written for a person goes to stderr and stdout
# carries exactly one canonical JSON array -- the receipt objects this run
# handed to the receipt writer, serialized verbatim.
#
# Nothing is filtered or renamed.  `schemas/receipt.template.jsonl` guarantees
# only the base fields every receipt carries; extension fields differ per
# producer and are discoverable from the receipt itself, which is why that
# template says its examples are "not the complete set".  A field allowlist
# here would silently drop exactly the fields a caller came for.
#
# Serialization goes through `kblib.canonical_json_bytes`; this module owns no
# serializer.  The flag changes no verdict, no exit code, and no receipt
# write.  A run that writes no receipt -- a dry run, a --verify pass, or a
# refusal -- emits the empty array; a usage error still exits through argparse
# before any of this, leaving stdout empty and the reason on stderr.
# ---------------------------------------------------------------------------
JSON_HELP = ("write the receipts this run produced to stdout as one canonical "
             "JSON array and move the human-readable report to stderr; "
             "receipts written, verdicts, and exit codes are unchanged")

_JSON_RECEIPTS = []


def _record_receipts(receipts):
    """Remember the exact receipt objects handed to the receipt writer."""
    _JSON_RECEIPTS.extend(receipts)
    return receipts


def _run_reporting_json(runner):
    """Run `runner`, reserving stdout for JSON and giving stderr the prose."""
    stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        exit_code = runner()
    stdout.write(kblib.canonical_json_bytes(_JSON_RECEIPTS).decode("utf-8"))
    stdout.write("\n")
    stdout.flush()
    return exit_code



# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def _closed_anchored_batches(result):
    """Batches whose closed state is anchored by a hot close transition."""
    closed = set()
    for item_id, item in (result.get("items_by_id") or {}).items():
        if item.get("state") != "closed":
            continue
        transitions = item.get("transition_receipts") or []
        catalog = result.get("receipt_catalog") or {}
        anchored = any(
            (catalog.get(rid) or (None, {}))[1].get("after_state") == "closed"
            for rid in transitions if isinstance(rid, str))
        if anchored:
            closed.add(item_id)
    return closed


def _row_batch(receipt):
    batch = receipt.get("batch_id")
    if isinstance(batch, str) and batch.strip():
        return batch
    target = receipt.get("target")
    if isinstance(target, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9-]+", target):
        return target
    return None


def _closed_bundle_trios(result, closed):
    """The evidence trio of every closed batch, sealed as one unit.

    The Queue consistency snapshot carries no batch identity of its own --
    it is a runtime-wide gate the close merely consumed -- so per-row
    classification would strand it hot while its two companions seal.
    ``check_queue`` rejects exactly that half state, so the trio is
    enumerated from the closed items themselves.
    """
    trio_ids = set()
    for item_id, item in (result.get("items_by_id") or {}).items():
        if item_id not in closed:
            continue
        for field in ("close_gate_receipt", "queue_consistency_receipt",
                      "delta_apply_receipt"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                trio_ids.add(value)
    return trio_ids


def _hot_closed_bundle_receipts(result, closed, hot_references):
    """Keep a hot trio and every body its hot replay must still read.

    The sealed replay deliberately treats the close gate, Queue consistency,
    and Delta application as one unit.  Coverage commonly points
    ``last_content_modified`` at the Delta application, so honoring that hot
    reference by itself would create the forbidden half-hot/half-cold shape.

    Keeping only the trio is still insufficient: while its close gate is hot,
    ``check_queue`` revalidates the complete producer-era bundle through the
    receipt bodies (global review, reviewer attestation, page-review children,
    Closed List members, and the optional Corpus Planning child).  Those rows
    may use the cold projection only after the trio itself takes the sealed
    branch.  Retain that exact one-hop dependency closure with the trio; a
    later owner transition that supersedes the Coverage pointer makes the
    whole old bundle sealable again.
    """
    keep = set()
    catalog = result.get("receipt_catalog") or {}
    for item_id, item in (result.get("items_by_id") or {}).items():
        if item_id not in closed:
            continue
        trio = {
            item.get(field) for field in (
                "close_gate_receipt", "queue_consistency_receipt",
                "delta_apply_receipt")
            if isinstance(item.get(field), str) and item.get(field).strip()
        }
        close_id = item.get("close_gate_receipt")
        entry = catalog.get(close_id)
        close = entry[1] if isinstance(entry, tuple) and len(entry) == 2 \
            else None
        replay_ids = set()
        if isinstance(close, dict):
            for field in (
                    "global_review_receipt", "reviewer_attestation_receipt",
                    "corpus_plan_receipt"):
                value = close.get(field)
                if isinstance(value, str) and value.strip():
                    replay_ids.add(value)
            for value in close.get("page_review_receipts") or []:
                if isinstance(value, str) and value.strip():
                    replay_ids.add(value)
            evidence = close.get("closed_list_evidence")
            if isinstance(evidence, dict):
                for value in evidence.values():
                    if isinstance(value, str) and value.strip():
                        replay_ids.add(value)

        # A Coverage owner may be a child of the close gate (most commonly a
        # page-review acceptance), not one of the trio records themselves.
        # Reachability therefore has to be tested against the complete replay
        # unit before any member of that unit is made cold.
        if not (trio | replay_ids).intersection(hot_references):
            continue
        keep.update(trio)
        keep.update(replay_ids)
    return keep


def _transition_bound_aggregates(catalog, transition_id):
    """Aggregates a transition binds that a later replay reads field by field.

    A transition receipt is not the only thing a transition binds.  The
    Standards-revalidation aggregate it consumed is re-read on every run to
    replay which plan bindings that batch already discharged, and that
    replay needs the *body*: the consumed keys live in
    ``revalidation_bindings`` and the retraction test reads
    ``invalidated_by``, neither of which a cold projection carries.

    Sealing these was the defect this rule exists to prevent.  It left the
    transitions hot and moved what they bind, so the replay stopped
    resolving them and reopened bindings a Queue transition had legitimately
    discharged -- on batches by then closed, which
    ``--require-revalidation`` refuses, so nothing could ever discharge them
    again.  ``check_queue`` now also resolves these through an explicit
    sealed branch, which repairs an archive already in that state; keeping
    them hot is what stops a new seal from depending on the repair.

    Deliberately narrow.  The other receipt IDs a transition names --
    ``evidence_receipt``, the close bundle, and the ``revalidation_receipts``
    an ``invalidation`` record lists -- have existence-only or
    identity-only consumers that the projection already serves through
    ``require_receipt``.  Keeping those hot would give up sealing for
    references that are not broken; what draws this boundary correctly is
    the reachability assertion in the tests, not a wider guess here.
    """
    entry = catalog.get(transition_id)
    transition = entry[1] if entry is not None else None
    if not isinstance(transition, dict):
        return ()
    value = transition.get("standards_revalidation_receipt")
    return {value} if isinstance(value, str) else ()


def _hot_reference_ids(result):
    """Receipt IDs that must stay hot because live consumers bind them.

    Activation and confirmation gates, batch-review wrappers, transition
    evidence of every item, the aggregates those transitions bind (see
    :func:`_transition_bound_aggregates`), and anything referenced by a
    batch that is not terminally closed.  Coverage property-state evidence is
    also current owner state, even after its producing batch closes: its body
    is revalidated for property value, content fingerprint, and invalidation,
    so it stays hot until some later owner transition supersedes the pointer.
    A closed trio is not retained merely because the batch is closed; its
    consumers have the K12/07 sealed branch.  If one of its members is a live
    property reference, :func:`_hot_closed_bundle_receipts` expands that
    direct reference into the complete hot replay closure.
    """
    keep = set()
    property_evidence = set()
    catalog = result.get("receipt_catalog") or {}
    coverage = result.get("coverage") or {}
    for page in coverage.get("pages") or []:
        if not isinstance(page, dict):
            continue
        property_state = page.get("property_state")
        if not isinstance(property_state, dict):
            continue
        for record in property_state.values():
            if not isinstance(record, dict):
                continue
            receipt_id = record.get("evidence_receipt")
            if isinstance(receipt_id, str) and receipt_id.strip():
                keep.add(receipt_id)
                property_evidence.add(receipt_id)
    # A live review property validates both the page-review body and the
    # declared reviewer attestation it names.  The latter is not itself a
    # Coverage pointer, but sealing it would still break the current owner
    # loop.  Other current property receipt kinds are self-contained.
    for receipt_id in property_evidence:
        entry = catalog.get(receipt_id)
        receipt = entry[1] if isinstance(entry, tuple) and len(entry) == 2 \
            else None
        if (isinstance(receipt, dict) and
                receipt.get("check") == "page_review_acceptance"):
            attestation_id = receipt.get("reviewer_attestation_receipt")
            if isinstance(attestation_id, str) and attestation_id.strip():
                keep.add(attestation_id)
    for item_id, item in (result.get("items_by_id") or {}).items():
        state = item.get("state")
        for field in ("activation_receipt", "confirmation_receipt"):
            value = item.get(field)
            if isinstance(value, str):
                keep.add(value)
        for value in item.get("batch_receipts") or []:
            if isinstance(value, str):
                keep.add(value)
        for value in item.get("transition_receipts") or []:
            if isinstance(value, str):
                keep.add(value)
                keep.update(_transition_bound_aggregates(catalog, value))
        if state != "closed":
            for field in ("close_gate_receipt", "queue_consistency_receipt",
                          "delta_apply_receipt"):
                value = item.get(field)
                if isinstance(value, str):
                    keep.add(value)
        for record in item.get("invalidation_history") or []:
            if not isinstance(record, dict):
                continue
            for field in ("transition_receipt", "delta_apply_receipt"):
                value = record.get(field)
                if isinstance(value, str):
                    keep.add(value)
            for value in (record.get("batch_receipts") or []) + \
                    (record.get("delta_gate_receipts") or []):
                if isinstance(value, str):
                    keep.add(value)
    progress = result.get("progress") or {}
    for adoption in progress.get("standards_adoptions") or []:
        if not isinstance(adoption, dict):
            continue
        for field in ("adoption_receipt", "consistency_receipt",
                      "profile_load_receipt"):
            value = adoption.get(field)
            if isinstance(value, str):
                keep.add(value)
    return keep


def plan_seal(root, result):
    """Return {relative_path: [(receipt_id, receipt)]} to seal."""
    catalog = result.get("receipt_catalog") or {}
    closed = _closed_anchored_batches(result)
    referenced_hot = _hot_reference_ids(result)
    trio_ids = _closed_bundle_trios(result, closed)
    hot_bundle_ids = _hot_closed_bundle_receipts(
        result, closed, referenced_hot)
    by_file = {}
    for receipt_id, (relative, receipt) in catalog.items():
        basename = os.path.basename(relative)
        if basename in NEVER_SEAL_BASENAMES:
            continue
        if receipt_id in hot_bundle_ids:
            continue
        if receipt_id in trio_ids:
            by_file.setdefault(relative, []).append((receipt_id, receipt))
            continue
        if REVIEW_REGISTER_RE.search(basename):
            continue
        if receipt_id in referenced_hot:
            continue
        sealable = False
        if PAGE_SNAPSHOT_RE.search(basename):
            sealable = True
        else:
            match = BATCH_FILE_RE.search(basename)
            row_batch = _row_batch(receipt)
            if match and match.group("delta_batch"):
                sealable = match.group("delta_batch") in closed
            elif row_batch is not None:
                sealable = row_batch in closed
        if sealable:
            by_file.setdefault(relative, []).append((receipt_id, receipt))
    return by_file


def _plan_signature(by_file):
    """A comparable shape of one plan, for the under-lock CAS."""
    return {relative: sorted(receipt_id for receipt_id, _ in rows)
            for relative, rows in by_file.items()}


# ---------------------------------------------------------------------------
# Byte helpers
# ---------------------------------------------------------------------------

def _jsonl_line(row):
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def _group_sha256(lines):
    """Hash one seal's register rows exactly as they are written."""
    payload = "".join(line + "\n" for line in lines)
    return kblib.sha256_bytes(payload.encode("utf-8"))


def _file_sha256(root, relative):
    try:
        with open(os.path.join(root, relative), "rb") as handle:
            return kblib.sha256_bytes(handle.read())
    except FileNotFoundError:
        return None


def _receipt_tree_fingerprint(root):
    """Hash every file under ``.cambium/receipts``, hot and cold alike.

    The seal plan is a function of the whole receipt tree -- which rows are
    referenced, which batches are closed, what is already sealed -- so the
    compare half of the compare-and-swap has to cover the whole tree.  A
    receipt appended by a concurrent writer between planning and the lock
    would otherwise be dropped by a rewrite computed before it existed.
    """
    fingerprint = {}
    receipts_root = os.path.join(root, RECEIPTS_ROOT)
    for dirpath, dirnames, filenames in os.walk(receipts_root):
        dirnames.sort()
        for name in sorted(filenames):
            relative = os.path.relpath(
                os.path.join(dirpath, name), root).replace(os.sep, "/")
            fingerprint[relative] = _file_sha256(root, relative)
    return fingerprint


def _append_lines(path, lines):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line)
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _existing_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


def _write_atomic(path, text):
    """Replace one register's bytes, durably, on hostile filesystems too.

    ``os.replace`` is the correct primitive and is tried first.  Some
    adopter mounts (the desktop bridge among them) refuse to replace an
    existing entry; there the durable temporary written first is what makes
    the in-place fallback recoverable -- an interrupted rewrite can always
    be finished from it, which a bare truncate-and-write could not offer.
    """
    temporary = path + ".seal-rewrite"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
        return
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------

def _projection(receipt_id, segment, line_number, raw_line, receipt):
    row = {
        "receipt_id": receipt_id,
        "segment": segment,
        "line": line_number,
        "record_sha256": kblib.sha256_bytes(raw_line.encode("utf-8")),
    }
    for field in kblib.RECEIPT_COLD_PROJECTION_FIELDS:
        if field in receipt:
            row[field] = receipt[field]
    if "result" in receipt:
        row["result"] = receipt["result"]
    return row


def log(message):
    print(message)


def _bound_evidence(result):
    """Map each born-cold evidence path to the hash an attestation bound."""
    bound = {}
    for _receipt_id, (_relative, receipt) in (
            result.get("receipt_catalog") or {}).items():
        path = receipt.get("candidate_evidence_path")
        digest = receipt.get("candidate_evidence_sha256")
        if isinstance(path, str) and isinstance(digest, str):
            bound[path] = digest
    return bound


def _plan_payload(root, result, by_file, stamp):
    """Build segments, manifest rows, index rows and hot rewrites."""
    queue = result.get("queue") or {}
    manifest_rows = []
    index_rows = []
    file_edits = []
    skipped = []
    for relative in sorted(by_file):
        seal_ids = {receipt_id for receipt_id, _ in by_file[relative]}
        with open(os.path.join(root, relative), encoding="utf-8") as handle:
            original = handle.read()
        segment = "%s/%s-%s.jsonl" % (
            kblib.RECEIPT_COLD_SEGMENT_PREFIX,
            os.path.basename(relative)[:-len(".jsonl")], stamp)
        sealed_lines = []
        kept_lines = []
        projections = []
        for line in original.splitlines(keepends=True):
            body = line.strip()
            if not body:
                kept_lines.append(line)
                continue
            receipt = json.loads(body)
            receipt_id = receipt.get("receipt_id")
            if receipt_id in seal_ids:
                if not line.endswith("\n"):
                    line = line + "\n"
                projections.append(_projection(
                    receipt_id, segment, len(sealed_lines) + 1, line, receipt))
                sealed_lines.append(line)
            else:
                kept_lines.append(line)
        if not sealed_lines:
            continue
        payload = "".join(sealed_lines).encode("utf-8")
        kept = "".join(kept_lines)
        manifest_rows.append({
            "kind": "sealed-receipts",
            "segment": segment,
            "segment_sha256": kblib.sha256_bytes(payload),
            "segment_bytes": len(payload),
            "records": len(sealed_lines),
            "source_path": relative,
            "source_sha256_before": kblib.sha256_bytes(
                original.encode("utf-8")),
            "source_sha256_after": kblib.sha256_bytes(kept.encode("utf-8")),
            "task_id": queue.get("task_id"),
            "sealed_at_state_revision": queue.get("state_revision"),
            "sealed_at": _now(),
            "tool": TOOL,
            "tool_version": TOOL_VERSION,
        })
        index_rows.extend(projections)
        file_edits.append({
            "source_path": relative,
            "segment": segment,
            "source_chars_before": len(original),
            "source_sha256_before": kblib.sha256_bytes(
                original.encode("utf-8")),
            "source_sha256_after": kblib.sha256_bytes(kept.encode("utf-8")),
        })

    # Adopt born-cold close-evidence files into the manifest so the per-run
    # hash guard covers them too -- but only files an attestation already
    # binds by hash.  Manifesting an unbound file would mint a manifest hash
    # for bytes nothing vouches for, which is how a tampered evidence file
    # becomes permanent evidence.
    evidence_dir = os.path.join(root, kblib.RECEIPT_COLD_EVIDENCE_PREFIX)
    already = {entry.get("segment")
               for entry in (result.get("cold_receipts") or {}).get(
                   "manifest", [])}
    bound = _bound_evidence(result)
    if os.path.isdir(evidence_dir):
        for name in sorted(os.listdir(evidence_dir)):
            if not name.endswith(".jsonl"):
                continue
            relative = "%s/%s" % (kblib.RECEIPT_COLD_EVIDENCE_PREFIX, name)
            if relative in already:
                continue
            with open(os.path.join(root, relative), "rb") as handle:
                payload = handle.read()
            expected = bound.get(relative)
            if expected is None:
                skipped.append(relative)
                continue
            if kblib.sha256_bytes(payload) != expected:
                raise RuntimeError(
                    "close evidence %s does not match the hash its "
                    "attestation bound; refusing to seal tampered evidence"
                    % relative)
            manifest_rows.append({
                "kind": "close-evidence",
                "segment": relative,
                "segment_sha256": kblib.sha256_bytes(payload),
                "segment_bytes": len(payload),
                "records": payload.count(b"\n"),
                "source_path": relative,
                "task_id": queue.get("task_id"),
                "sealed_at_state_revision": queue.get("state_revision"),
                "sealed_at": _now(),
                "tool": TOOL,
                "tool_version": TOOL_VERSION,
            })
    for relative in skipped:
        log("[SKIP] close evidence %s is bound by no current attestation; "
            "leaving it unmanifested rather than minting a hash for bytes "
            "nothing vouches for" % relative)
    return manifest_rows, index_rows, file_edits


def _pending_record(root, result, receipts_path, manifest_rows, index_rows,
                    file_edits):
    """Everything ``--reconcile`` needs to finish an interrupted seal.

    Deliberately small: the sealed bytes themselves are never copied here.
    Until the hot rewrite lands the source register still holds every
    sealed row, and each manifest row names its ``source_path``, so a
    missing segment is rebuilt from the source and proved against the
    manifest hash.  After the rewrite lands the segment is already durable.
    """
    queue = result.get("queue") or {}
    seal_receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "receipt_seal", ".", "pass",
        "sealed %d receipt(s) into %d segment(s); pre-seal full runtime "
        "revalidation passed with zero errors" % (
            len(index_rows),
            sum(1 for row in manifest_rows
                if row["kind"] == "sealed-receipts")),
        1, root=root)
    seal_id = seal_receipt["receipt_id"]
    for row in manifest_rows:
        row["seal_receipt"] = seal_id
    for row in index_rows:
        row["seal_receipt"] = seal_id
    manifest_lines = [_jsonl_line(row) for row in manifest_rows]
    index_lines = [_jsonl_line(row) for row in index_rows]
    seal_receipt.update({
        "sealed_segments": [row["segment"] for row in manifest_rows],
        "sealed_records": len(index_rows),
        "manifest_rows": len(manifest_rows),
        "index_rows": len(index_rows),
        "manifest_rows_sha256": _group_sha256(manifest_lines),
        "index_rows_sha256": _group_sha256(index_lines),
        "queue_state_revision": queue.get("state_revision"),
        "queue_revision": queue.get("queue_revision"),
    })
    return {
        "seal_receipt": seal_id,
        "receipt": seal_receipt,
        "receipt_path": receipts_path,
        "manifest_lines": manifest_lines,
        "index_lines": index_lines,
        "manifest_rows": manifest_rows,
        "edits": file_edits,
        "planned_at": _now(),
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
    }


# ---------------------------------------------------------------------------
# Publication (idempotent; shared by --apply and --reconcile)
# ---------------------------------------------------------------------------

def _segment_payload_from_source(root, manifest_row, index_lines):
    """Re-extract a segment's exact bytes from its still-intact source."""
    order = []
    for line in index_lines:
        row = json.loads(line)
        if row.get("segment") == manifest_row["segment"]:
            order.append((row["line"], row["receipt_id"]))
    order.sort()
    slots = [None] * len(order)
    positions = {receipt_id: index
                 for index, (_line, receipt_id) in enumerate(order)}
    source = os.path.join(root, manifest_row["source_path"])
    if not os.path.exists(source):
        return None
    with open(source, encoding="utf-8") as handle:
        for raw in handle:
            body = raw.strip()
            if not body:
                continue
            receipt_id = json.loads(body).get("receipt_id")
            position = positions.get(receipt_id)
            if position is None:
                continue
            slots[position] = raw if raw.endswith("\n") else raw + "\n"
    if any(slot is None for slot in slots):
        return None
    return "".join(slots).encode("utf-8")


def _publish(root, pending):
    """Run every publication step that has not already landed.

    Ordered so that no step destroys an input a later step needs: segments
    first, then the seal receipt that will be their root of trust, then the
    cold registers that reference it, and only last the hot rewrites that
    make the segments the sole copy.
    """
    seal_id = pending["seal_receipt"]
    for row in pending["manifest_rows"]:
        if row["kind"] != "sealed-receipts":
            continue
        segment_full = os.path.join(root, row["segment"])
        if os.path.exists(segment_full):
            with open(segment_full, "rb") as handle:
                if kblib.sha256_bytes(handle.read()) == row["segment_sha256"]:
                    continue
            raise RuntimeError(
                "cold segment %s already exists with different bytes" %
                row["segment"])
        payload = _segment_payload_from_source(
            root, row, pending["index_lines"])
        if payload is None or kblib.sha256_bytes(
                payload) != row["segment_sha256"]:
            raise RuntimeError(
                "cannot rebuild cold segment %s from %s; reconcile this seal "
                "by hand against the journal" %
                (row["segment"], row["source_path"]))
        os.makedirs(os.path.dirname(segment_full), mode=0o700, exist_ok=True)
        with open(segment_full, "xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    receipt_full = os.path.join(root, pending["receipt_path"])
    already = any(json.loads(line).get("receipt_id") == seal_id
                  for line in _existing_lines(receipt_full) if line.strip())
    if not already:
        outcome, error, _ = kblib.write_receipts_observed(
            receipt_full, _record_receipts([pending["receipt"]]))
        if error is not None or outcome != "present":
            raise RuntimeError(
                "seal receipt append outcome=%s error=%s" % (outcome, error))

    # Both registers are created even when this seal has no rows for one of
    # them: a first seal that adopts only born-cold evidence writes manifest
    # rows and no projections, and a cold namespace with a manifest and no
    # index.jsonl is invalid by the loader's own rule.
    for path, lines in (
            (os.path.join(root, kblib.RECEIPT_COLD_MANIFEST_PATH),
             pending["manifest_lines"]),
            (os.path.join(root, kblib.RECEIPT_COLD_INDEX_PATH),
             pending["index_lines"])):
        _repair_partial_tail(path)
        present = set(_existing_lines(path))
        missing = [line for line in lines if line not in present]
        _append_lines(path, missing)

    for edit in pending["edits"]:
        full = os.path.join(root, edit["source_path"])
        _finish_interrupted_rewrite(full, edit)
        current = _file_sha256(root, edit["source_path"])
        if current == edit["source_sha256_after"]:
            continue
        with open(full, encoding="utf-8") as handle:
            original = handle.read()
        planned_before = original[:edit["source_chars_before"]]
        if kblib.sha256_bytes(
                planned_before.encode("utf-8")) != edit["source_sha256_before"]:
            raise RuntimeError(
                "source register %s is neither its pre-seal nor its post-seal "
                "image and is not an append-extension of either; reconcile "
                "this seal by hand" % edit["source_path"])
        # Defence in depth behind the append mutex: if some writer appended
        # without taking it, the tail is carried into the rewritten image
        # rather than truncated away.  A seal may remove only the rows it
        # sealed.
        tail = original[len(planned_before):]
        sealed_ids = {json.loads(line)["receipt_id"]
                      for line in pending["index_lines"]
                      if json.loads(line)["segment"] == edit["segment"]}
        kept = []
        for raw in planned_before.splitlines(keepends=True):
            body = raw.strip()
            if body and json.loads(body).get("receipt_id") in sealed_ids:
                continue
            kept.append(raw)
        text = "".join(kept)
        if kblib.sha256_bytes(
                text.encode("utf-8")) != edit["source_sha256_after"]:
            raise RuntimeError(
                "recomputed rewrite of %s does not match the planned "
                "after-image" % edit["source_path"])
        _write_atomic(full, text + tail)

    _require_publication_complete(root, pending)
    _append_lines(os.path.join(root, kblib.RECEIPT_COLD_JOURNAL_PATH),
                  [_jsonl_line({"phase": "complete",
                                "seal_receipt": seal_id,
                                "at": _now()})])


def _repair_partial_tail(path):
    """Drop a torn final line left by an interrupted append.

    A register with no newline at all is not a file with a good prefix: the
    single fragment in it is the torn record, and keeping it would turn an
    interrupted write into a well-formed lie.
    """
    if not os.path.exists(path):
        return
    with open(path, "rb") as handle:
        payload = handle.read()
    if not payload or payload.endswith(b"\n"):
        return
    keep = payload.rsplit(b"\n", 1)[0] + b"\n" if b"\n" in payload else b""
    _write_atomic(path, keep.decode("utf-8"))


def _finish_interrupted_rewrite(full, edit):
    """Install a durable ``.seal-rewrite`` left by an interrupted fallback.

    ``_write_atomic`` writes and fsyncs the temporary before it touches the
    live name, precisely so this case is finishable: on a mount that refuses
    ``os.replace`` the in-place fallback can tear, and the intact planned
    image is still sitting beside it.
    """
    temporary = full + ".seal-rewrite"
    if not os.path.exists(temporary):
        return
    with open(temporary, "rb") as handle:
        payload = handle.read()
    if kblib.sha256_bytes(payload) != edit["source_sha256_after"]:
        return
    with open(full, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _require_publication_complete(root, pending):
    """Prove every postcondition before the journal may say complete."""
    failures = []
    for row in pending["manifest_rows"]:
        digest = _file_sha256(root, row["segment"])
        if digest != row["segment_sha256"]:
            failures.append("segment %s is %s, expected %s" %
                            (row["segment"], digest, row["segment_sha256"]))
    for path, lines in (
            (kblib.RECEIPT_COLD_MANIFEST_PATH, pending["manifest_lines"]),
            (kblib.RECEIPT_COLD_INDEX_PATH, pending["index_lines"])):
        present = set(_existing_lines(os.path.join(root, path)))
        absent = [line for line in lines if line not in present]
        if absent:
            failures.append("%s is missing %d row(s) of this seal" %
                            (path, len(absent)))
    receipts = _existing_lines(os.path.join(root, pending["receipt_path"]))
    if not any(json.loads(line).get("receipt_id") == pending["seal_receipt"]
               for line in receipts if line.strip()):
        failures.append("seal receipt %s never landed" %
                        pending["seal_receipt"])
    for edit in pending["edits"]:
        current = _file_sha256(root, edit["source_path"])
        if current == edit["source_sha256_after"]:
            continue
        sealed_ids = {json.loads(line)["receipt_id"]
                      for line in pending["index_lines"]
                      if json.loads(line)["segment"] == edit["segment"]}
        live = {json.loads(line).get("receipt_id")
                for line in _existing_lines(
                    os.path.join(root, edit["source_path"])) if line.strip()}
        if sealed_ids & live:
            failures.append("%s still holds %d sealed row(s)" %
                            (edit["source_path"], len(sealed_ids & live)))
    if failures:
        raise RuntimeError(
            "seal publication is incomplete, so the journal stays open: %s" %
            "; ".join(failures))


def _require_unchanged(root, planned, by_file, before_tree):
    """Compare-and-swap every byte the plan was computed from."""
    current = check_queue.validate_runtime(root)
    if current["errors"]:
        raise ValueError("runtime changed before write: %s" %
                         "; ".join(current["errors"]))
    for field in ("queue_sha256", "coverage_sha256", "progress_sha256"):
        if current.get(field) != planned.get(field):
            raise ValueError("%s changed between planning and the writer "
                             "lock" % field)
    after_tree = _receipt_tree_fingerprint(root)
    if after_tree != before_tree:
        changed = sorted(
            set(after_tree) ^ set(before_tree)) or sorted(
            path for path in after_tree
            if after_tree[path] != before_tree.get(path))
        raise ValueError(
            "the receipt tree changed between planning and the writer lock "
            "(%s); a seal computed from stale bytes would drop a concurrent "
            "append" % ", ".join(changed[:5]))
    if _plan_signature(plan_seal(root, current)) != _plan_signature(by_file):
        raise ValueError("the seal plan changed between planning and the "
                         "writer lock")


def apply_seal(root, result, by_file, receipts_path, before_tree=None):
    """Seal under both locks, planning only once appends are excluded.

    Maintenance-window operation: the caller is responsible for having
    established that no other writer, checker or appender is running.

    The receipt append mutex is taken before the plan is read, not after,
    because a receipt appended between the read and the rewrite would be
    dropped -- and dropped invisibly, since the post-seal validation reads
    the evidence set the row is now missing from.  Taking it early makes
    the ordinary version of that mistake fail rather than corrupt; it does
    not make the tool safe to run beside an active writer, and nothing here
    should be read as claiming that.  Lock order is always
    runtime_write_lock then receipt_append_mutex.
    """
    if before_tree is None:
        before_tree = _receipt_tree_fingerprint(root)
    queue = result.get("queue") or {}
    metadata = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "action": "seal-receipts",
        "receipt_path": receipts_path,
        "task_id": queue.get("task_id"),
        "before_state_revision": queue.get("state_revision"),
        "before_required_queue_sha256": result.get("queue_sha256"),
        "before_coverage_sha256": result.get("coverage_sha256"),
        "before_progress_sha256": result.get("progress_sha256"),
        "planned_sources": sorted(by_file),
        "recovery": "the cold journal's begin row and its hash-bound pending "
                    "record carry this transaction's exact intent",
    }
    with kblib.runtime_write_lock(
            root, owner_metadata=metadata, timeout=0.0) as lease:
        with kblib.receipt_append_mutex(root, note="seal_receipts"):
            pending = None
            with kblib.no_authoritative_write_guard(lease):
                _require_unchanged(root, result, by_file, before_tree)
                stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                manifest_rows, index_rows, file_edits = _plan_payload(
                    root, result, by_file, stamp)
                if manifest_rows:
                    pending = _pending_record(
                        root, result, receipts_path, manifest_rows,
                        index_rows, file_edits)
                    pending_path = "%s/%s.json" % (
                        COLD_PENDING_PREFIX, pending["seal_receipt"])
                    payload = json.dumps(pending, ensure_ascii=False,
                                         sort_keys=True)
                    pending["pending_sha256"] = kblib.sha256_bytes(
                        payload.encode("utf-8"))
                    full = os.path.join(root, pending_path)
                    os.makedirs(os.path.dirname(full), mode=0o700,
                                exist_ok=True)
                    with open(full, "x", encoding="utf-8") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
            if pending is None:
                return None
            _append_lines(
                os.path.join(root, kblib.RECEIPT_COLD_JOURNAL_PATH),
                [_jsonl_line({"phase": "begin",
                              "seal_receipt": pending["seal_receipt"],
                              "pending_path": pending_path,
                              "pending_sha256": pending["pending_sha256"],
                              "segments": [row["segment"]
                                           for row in manifest_rows],
                              "manifest_rows_sha256":
                                  pending["receipt"]["manifest_rows_sha256"],
                              "index_rows_sha256":
                                  pending["receipt"]["index_rows_sha256"],
                              "at": _now()})])
            _publish(root, pending)
    return pending["receipt"]


# ---------------------------------------------------------------------------
# Verification and recovery
# ---------------------------------------------------------------------------

def _cold_errors(root):
    errors = []
    catalog = check_queue.receipt_catalog(root, errors)
    store = check_queue.cold_receipt_store(root, errors, catalog)
    return store, errors


def verify(root):
    """Prove the whole cold chain, not just segment bytes.

    An absent manifest is only innocent when the journal is also balanced.
    A seal that died between its begin row and its first segment byte leaves
    exactly the manifest-absent state, and reporting that as "nothing
    sealed" would be this command declaring the one failure it is run to
    catch a clean bill of health.
    """
    store, errors = _cold_errors(root)
    for error in errors:
        print("[FAIL] %s" % error)
    if errors:
        return 1
    if not os.path.exists(os.path.join(root, kblib.RECEIPT_COLD_MANIFEST_PATH)):
        print("[PASS] cold manifest absent and the cold journal is balanced; "
              "nothing is sealed")
        return 0
    print("[PASS] %d sealed segment(s) match their manifest hashes, %d "
          "projection(s) match their sealed records, and %d seal receipt(s) "
          "still bind both cold registers" %
          (len(store["manifest"]), len(store["index"]),
           len(store.get("seals") or [])))
    return 0


def _unfinished_seals(root):
    """Seal IDs with a ``begin`` row and no ``complete`` row."""
    journal_path = os.path.join(root, kblib.RECEIPT_COLD_JOURNAL_PATH)
    open_seals = {}
    for line in _existing_lines(journal_path):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("phase") == "begin":
            open_seals[entry["seal_receipt"]] = entry
        elif entry.get("phase") == "complete":
            open_seals.pop(entry.get("seal_receipt"), None)
    return open_seals


def _adopt_own_lock(root, seal_id, errors):
    """Take over the writer lock this exact seal left behind, if it is dead.

    An interrupted writer leaves its lock standing on purpose, and an
    operator may clear it only after proving no writer remains.
    ``--reconcile`` performs that proof mechanically or not at all: the
    owner record must name this tool and this seal, and its recorded pid
    must no longer exist.  A lock whose owner is still running is a live
    seal, not a corpse -- stealing it would put two writers inside the one
    window this whole protocol exists to keep single-occupancy.  The
    directory is renamed rather than removed, because the mounts this tool
    has to survive refuse ``unlink`` and the owner record is evidence.
    """
    lock_path = os.path.join(root, ".cambium/tmp/state-writer.lock")
    owner_path = os.path.join(lock_path, "owner.json")
    if not os.path.isdir(lock_path):
        return False
    try:
        with open(owner_path, encoding="utf-8") as handle:
            owner = json.load(handle)
    except (OSError, ValueError):
        errors.append("a writer lock stands with no readable owner record; "
                      "reconcile it by hand before finishing this seal")
        return False
    operation = owner.get("operation") or {}
    if operation.get("tool") != TOOL:
        errors.append("the standing writer lock belongs to %r, not this seal" %
                      operation.get("tool"))
        return False
    if operation.get("action") not in ("seal-receipts", "reconcile-seal"):
        errors.append("the standing writer lock records action %r" %
                      operation.get("action"))
        return False
    if kblib.process_is_alive(owner.get("pid")):
        errors.append(
            "the writer lock's owner (pid %r) is still running; a live seal "
            "is not an interrupted one, and --reconcile will not take a lock "
            "out from under a running writer" % owner.get("pid"))
        return False
    retired = os.path.join(
        root, ".cambium/tmp/state-writer.lock.reconciled-%s" % seal_id)
    if os.path.exists(retired):
        errors.append("a previous reconciliation of %s is already recorded at "
                      "%s" % (seal_id, os.path.basename(retired)))
        return False
    os.rename(lock_path, retired)
    return True


def _load_pending(root, entry, errors):
    """Load one seal's pending record, bound to the journal that names it."""
    relative = entry.get("pending_path")
    if not _nonempty(relative):
        errors.append("journal begin row for %s names no pending record" %
                      entry.get("seal_receipt"))
        return None
    full = os.path.join(root, relative)
    try:
        with open(full, "rb") as handle:
            payload = handle.read()
    except OSError as exc:
        errors.append("pending record %s is unreadable (%s); this seal cannot "
                      "be finished mechanically" % (relative, exc))
        return None
    recorded = entry.get("pending_sha256")
    actual = kblib.sha256_bytes(payload)
    if recorded != actual:
        errors.append(
            "pending record %s hashes to %s but the journal bound %r; a "
            "recovery plan that no longer matches the transaction that wrote "
            "it is not a recovery plan" % (relative, actual, recorded))
        return None
    try:
        pending = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        errors.append("pending record %s does not parse: %s" % (relative, exc))
        return None
    if pending.get("seal_receipt") != entry.get("seal_receipt"):
        errors.append("pending record %s names a different seal" % relative)
        return None
    receipt = pending.get("receipt") or {}
    if (_group_sha256(pending.get("manifest_lines") or []) !=
            receipt.get("manifest_rows_sha256") or
            _group_sha256(pending.get("index_lines") or []) !=
            receipt.get("index_rows_sha256")):
        errors.append("pending record %s carries rows its own seal receipt "
                      "does not bind" % relative)
        return None
    return pending


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def reconcile(root, apply_it):
    """Finish or report an interrupted seal transaction."""
    open_seals = _unfinished_seals(root)
    if not open_seals:
        print("no interrupted seal; the cold journal is balanced")
        return 0
    for seal_id, entry in sorted(open_seals.items()):
        print("[HOLD] seal %s began and never completed" % seal_id)
        errors = []
        pending = _load_pending(root, entry, errors)
        for error in errors:
            print("[FAIL] %s" % error)
        if pending is None:
            return 1
        if not apply_it:
            print("       %d manifest row(s), %d index row(s), %d rewrite(s)"
                  % (len(pending["manifest_lines"]),
                     len(pending["index_lines"]), len(pending["edits"])))
            print("       dry run; add --apply to finish it")
            continue
        adopt_errors = []
        if _adopt_own_lock(root, seal_id, adopt_errors):
            print("       adopted the writer lock this seal left behind")
        elif adopt_errors:
            for error in adopt_errors:
                print("[FAIL] %s" % error)
            return 1
        with kblib.runtime_write_lock(
                root, owner_metadata={"tool": TOOL,
                                      "tool_version": TOOL_VERSION,
                                      "action": "reconcile-seal",
                                      "receipt_id": seal_id},
                timeout=0.0):
            with kblib.receipt_append_mutex(root, note="reconcile-seal"):
                _publish(root, pending)
        print("[PASS] seal %s finished" % seal_id)
    if not apply_it:
        return 0
    return verify(root)


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Seal verified frozen receipt history (K12/07). "
                    "--apply is a maintenance-window operation: run it only "
                    "with no other Cambium or adopter writer, checker or "
                    "receipt appender active against this repository.")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--apply", action="store_true",
                        help="write the seal, or with --reconcile finish the "
                             "interrupted one; omit for a dry run")
    parser.add_argument("--verify", action="store_true",
                        help="re-prove every sealed segment, projection and "
                             "seal-receipt binding, then exit")
    parser.add_argument("--reconcile", action="store_true",
                        help="finish an interrupted seal over the "
                             "publication paths this tool implements; other "
                             "interruptions fail closed and are resolved by "
                             "the runbook in Tools/README.md")
    parser.add_argument("--receipts", default=SEAL_RECEIPTS_PATH,
                        help="repository-relative JSONL path for this tool's "
                             "own seal receipts, which never seal "
                             "(default: %s)" % SEAL_RECEIPTS_PATH)
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)

    if not args.json:
        return _run(args)
    return _run_reporting_json(lambda: _run(args))


def _run(args):
    root = os.path.realpath(os.path.abspath(args.root))

    if args.verify:
        return verify(root)
    if args.reconcile:
        return reconcile(root, args.apply)

    result = check_queue.validate_runtime(root)
    before_tree = _receipt_tree_fingerprint(root)
    if result["errors"]:
        for error in result["errors"]:
            print("[FAIL] pre-seal runtime validation: %s" % error)
        print("[FAIL] sealing requires a clean full revalidation; a bundle "
              "that cannot replay hot cannot claim the sealed shortcut")
        return 1
    if result.get("_writer_locks"):
        print("[FAIL] runtime has an active or interrupted writer lock")
        return 1
    if (result.get("pending_delta_applies") or {}).get("current"):
        print("[FAIL] a pending Coverage delta application is unconsumed")
        return 1

    by_file = plan_seal(root, result)
    total = sum(len(rows) for rows in by_file.values())
    for relative in sorted(by_file):
        print("[PLAN] %s: seal %d receipt(s)" %
              (relative, len(by_file[relative])))
    print("[PLAN] total %d receipt(s) across %d register(s)" %
          (total, len(by_file)))
    if total == 0:
        print("nothing sealable; hot registers already minimal")
    if not args.apply:
        print("dry run; add --apply to seal %d receipt(s)" % total)
        return 0
    print("[MAINTENANCE] --apply assumes a quiet window: no other Cambium or "
          "adopter writer, checker or receipt appender may be running. The "
          "append mutex guards against the accident, not against arbitrary "
          "concurrency.")
    receipt = apply_seal(root, result, by_file, args.receipts, before_tree)
    if receipt is None:
        print("nothing sealed")
        return 0
    print("[PASS] sealed %d receipt(s); seal receipt %s" %
          (total, receipt["receipt_id"]))
    after = check_queue.validate_runtime(root)
    if after["errors"]:
        for error in after["errors"]:
            print("[FAIL] post-seal runtime validation: %s" % error)
        return 1
    print("[PASS] post-seal full runtime validation is clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
