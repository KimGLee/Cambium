"""What evidence exists, and can this named receipt be resolved right now.

The hot register scans the live receipt files and deliberately excludes
``cold/``.  The K12/07 cold chain revalidates each sealed body against the
same current Receipt type registry before exposing its thin projection.  The
two are one admission contract and stay in one file, because a reader who
finds only half of it will conclude the hot scan is simply incomplete.

Every resolution goes through one fail-closed resolver.  A receipt that
cannot be resolved is not evidence, and no caller gets to decide otherwise.
"""

import json
import os
import stat

import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.execution.evidence import receipt_type_contract
from Tools.execution.evidence import receipt_reference_contract

from Tools.execution.task_runtime.queue_runtime.canon import (
    SEAL_TOOL,
    SEAL_TOOL_VERSION,
    SHA256_RE,
    UPDATE_QUEUE_TOOL_VERSION,
)
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string


QUEUE_TRANSITION_RECEIPT_TYPE_ID = \
    runtime_state_contract.QUEUE_TRANSITION_REPLAY_PROTOCOL


def make_queue_receipt(action, target, result, details, seq=1, **fields):
    """Build the sole current Queue-transition Receipt shape."""
    receipt = kblib.make_receipt(
        "update_queue", UPDATE_QUEUE_TOOL_VERSION, action, target, result,
        details, seq,
        receipt_type_id=QUEUE_TRANSITION_RECEIPT_TYPE_ID,
    )
    receipt.update(fields)
    return receipt


def current_queue_transition_receipt_errors(record, *, root=None):
    errors = receipt_type_contract.base_receipt_errors(
        record,
        receipt_type_id=QUEUE_TRANSITION_RECEIPT_TYPE_ID,
        tool="update_queue",
        tool_version=UPDATE_QUEUE_TOOL_VERSION,
        checks="queue_transition",
    )
    if isinstance(record, dict):
        for field in ("before_state", "after_state", "before_hold_state",
                      "after_hold_state", "before_state_revision",
                      "after_state_revision"):
            if field not in record:
                errors.append("Queue transition Receipt misses %s" % field)
        if runtime_state_contract.classify_queue_transition(
                runtime_state_contract.ORDINARY_QUEUE_TRANSITION_CAPABILITY,
                record.get("before_state"), record.get("after_state"),
                record.get("before_hold_state"),
                record.get("after_hold_state")) is None:
            errors.append(
                "Queue transition Receipt has no authorized lifecycle/hold "
                "transition classification")
    return errors


def current_receipt_catalog(result):
    """Return the adoption-filtered catalog for a new evidence decision.

    A present empty mapping is authoritative: falling back to the historical
    catalog in that case would re-enable every receipt explicitly declared
    invalidated.  There is deliberately no fallback to the historical catalog:
    a missing current view is an unavailable authorization source, not an
    invitation to reinterpret history as fresh evidence.
    """
    current = result.get("current_receipt_catalog")
    return _as_typed_catalog(current, CurrentReceiptCatalog)


def historical_receipt_catalog(result):
    """Return current-format immutable history for verification only."""
    historical = result.get("receipt_catalog")
    return _as_typed_catalog(historical, HistoricalReceiptCatalog)


def adoption_filtered_catalog(catalog, invalidated_receipt_ids):
    """Return the current-use view without rewriting historical evidence.

    The hot register and the verified cold projection are two materializations
    of the same Receipt namespace.  Filtering only the hot half would let an
    invalidated ID re-enter current authority merely because it had already
    been sealed.  Historical callers retain ``catalog`` unchanged; current
    callers receive a new view with the same IDs removed from both halves.
    """
    invalidated = frozenset(
        value for value in (invalidated_receipt_ids or ())
        if nonempty_string(value)
    )
    current = CurrentReceiptCatalog({
        receipt_id: entry for receipt_id, entry in catalog.items()
        if receipt_id not in invalidated
    })
    current.root = getattr(catalog, "root", None)
    current._type_registry = getattr(catalog, "_type_registry", None)
    current.cold = {
        receipt_id: projection
        for receipt_id, projection in (
            getattr(catalog, "cold", None) or {}).items()
        if receipt_id not in invalidated
    }
    return current


def delta_gate_receipt_ids(delta):
    """Return the deterministic receipt-ID set carried by delta pages."""
    if not isinstance(delta, dict):
        raise ValueError("delta document must be a mapping")
    pages = delta.get("pages")
    if not isinstance(pages, list):
        raise ValueError("delta pages must be an explicit list")
    receipt_ids = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError("delta pages[%d] must be a mapping" % index)
        gate_receipts = page.get("gate_receipts")
        if (not isinstance(gate_receipts, list) or not gate_receipts or
                not all(nonempty_string(value) for value in gate_receipts)):
            raise ValueError("delta pages[%d] gate_receipts must be a non-empty "
                             "string list" % index)
        if len(gate_receipts) != len(set(gate_receipts)):
            raise ValueError("delta pages[%d] gate_receipts must be unique" %
                             index)
        receipt_ids.update(gate_receipts)
    return sorted(receipt_ids)


class Catalog(dict):
    """The hot receipt catalog plus the sealed-receipt projection index.

    The hot map keeps ``receipt_id -> (relative_path, receipt)`` exactly as
    before.  ``cold`` carries the K12/07 sealed index --
    ``receipt_id -> thin projection`` -- so any consumer holding the catalog
    can resolve sealed existence without a second parameter threading
    through every historical-validation signature.
    """

    __slots__ = (
        "cold", "root", "_sealed_segments", "_sealed_bodies",
        "_type_registry",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cold = {}
        self.root = None
        self._sealed_segments = {}
        self._sealed_bodies = {}
        self._type_registry = None

    def resolve_sealed(self, receipt_id):
        """Return one sealed body, re-proving its bytes at the read.

        This is a sealed branch, not a hole in sealing.  Existence and
        identity consumers are served by the projection through
        :func:`require_receipt` and never come here; a consumer that must
        replay a *body* -- today the Standards-revalidation consumption
        replay, whose consumed keys live in ``revalidation_bindings`` and
        whose retraction test reads ``invalidated_by``, neither of which a
        projection carries -- has exactly two honest options under K12/07,
        an explicit sealed branch or failing closed.  Silently skipping an
        unresolvable reference is the third option, and taking it is what
        reopened bindings a Queue transition had already discharged.

        Catalog loading already parsed and validated every sealed body against
        the current typed owner.  This method still re-proves the requested
        line against its projection before returning it, then memoizes that
        body for consumers that require fields outside the thin projection.
        """
        if receipt_id in self._sealed_bodies:
            return self._sealed_bodies[receipt_id]
        self._sealed_bodies[receipt_id] = None
        row = self.cold.get(receipt_id)
        if not isinstance(row, dict) or not isinstance(self.root, str):
            return None
        segment = row.get("segment")
        line_number = row.get("line")
        if not nonempty_string(segment) or not isinstance(line_number, int) \
                or isinstance(line_number, bool) or line_number < 1:
            return None
        if segment not in self._sealed_segments:
            try:
                with open(os.path.join(self.root, segment), "rb") as handle:
                    self._sealed_segments[segment] = \
                        handle.read().splitlines(keepends=True)
            except OSError:
                self._sealed_segments[segment] = []
        lines = self._sealed_segments[segment]
        if line_number > len(lines):
            return None
        raw = lines[line_number - 1]
        if kblib.sha256_bytes(raw) != row.get("record_sha256"):
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            return None
        if not isinstance(body, dict) or body.get("receipt_id") != receipt_id:
            return None
        if body.get("receipt_type_id") != row.get("receipt_type_id"):
            return None
        if self._type_registry is None or \
                receipt_type_contract.current_receipt_errors(
                    body, "cold", root=self.root,
                    registry=self._type_registry):
            return None
        self._sealed_bodies[receipt_id] = (segment, body)
        return self._sealed_bodies[receipt_id]

    def resolve(self, receipt_id):
        """Resolve hot first, then through the sealed branch above."""
        entry = self.get(receipt_id)
        if entry is not None:
            return entry
        return self.resolve_sealed(receipt_id)

    def resolve_reference(self, receipt_id, edge_id):
        """Resolve one declared edge to a normalized typed result.

        ``resolve`` and ``resolve_sealed`` retain their tuple result for direct
        body callers.  Typed consumers use this method and never
        have to guess whether a sealed branch returned a tuple, projection, or
        body.  The graph decides whether the cold index is sufficient or the
        hash-reproved body must be loaded.
        """
        if not nonempty_string(receipt_id):
            return None
        spec = receipt_reference_contract.reference_spec(edge_id)
        entry = self.get(receipt_id)
        if isinstance(entry, tuple) and len(entry) == 2 and \
                isinstance(entry[1], dict):
            relative, body = entry
            return receipt_reference_contract.ResolvedReceipt(
                receipt_id=receipt_id,
                origin="hot-body",
                relative_path=relative,
                projection=body,
                body=body,
            )
        projection = self.cold.get(receipt_id)
        if not isinstance(projection, dict):
            return None
        if spec.materialization == \
                receipt_reference_contract.MATERIALIZATION_ID_ONLY:
            return receipt_reference_contract.ResolvedReceipt(
                receipt_id=receipt_id,
                origin="cold-identity",
                relative_path=projection.get("segment"),
                projection=projection,
                body=None,
            )
        if spec.materialization == \
                receipt_reference_contract.MATERIALIZATION_COLD_PROJECTION:
            if any(field not in projection for field in
                   spec.projection_fields):
                return None
            return receipt_reference_contract.ResolvedReceipt(
                receipt_id=receipt_id,
                origin="cold-projection",
                relative_path=projection.get("segment"),
                projection=projection,
                body=None,
            )
        sealed = self.resolve_sealed(receipt_id)
        if not (isinstance(sealed, tuple) and len(sealed) == 2 and
                isinstance(sealed[1], dict)):
            return None
        relative, body = sealed
        return receipt_reference_contract.ResolvedReceipt(
            receipt_id=receipt_id,
            origin="cold-body",
            relative_path=relative,
            projection=projection,
            body=body,
        )


class CurrentReceiptCatalog(Catalog):
    """Receipts admitted to current authorization after invalidation filters."""


class HistoricalReceiptCatalog(Catalog):
    """Current-contract receipts retained only for immutable history checks."""


def _as_typed_catalog(value, catalog_type):
    """Project one catalog into an explicit authority scope without fallback."""
    if isinstance(value, catalog_type):
        return value
    projected = catalog_type(value if isinstance(value, dict) else {})
    if isinstance(value, Catalog):
        projected.root = value.root
        projected._type_registry = value._type_registry
        projected.cold = dict(value.cold)
        projected._sealed_segments = value._sealed_segments
        projected._sealed_bodies = value._sealed_bodies
    return projected


def receipt_catalog(root, errors):
    """Load the repository receipt register into one collision-checked map.

    Queue references use receipt IDs rather than file paths.  The canonical
    receipt namespace is therefore scanned recursively; malformed JSONL,
    duplicate IDs, symlinks, and hard-linked files make the evidence set
    unreliable instead of being silently skipped.  The one deliberate
    exception is the ``cold/`` namespace: its files are not mixed into the
    recursive hot scan.  ``cold_receipt_store`` separately proves the sealed
    registers and bytes, then parses every body through the same current type
    registry before exposing any projection (K12/07).
    """
    relative_dir = runtime_paths.RECEIPT_ROOT
    receipt_dir = os.path.join(root, relative_dir)
    catalog = HistoricalReceiptCatalog()
    catalog.root = root
    if not os.path.exists(receipt_dir):
        return catalog
    if not os.path.isdir(receipt_dir) or os.path.islink(receipt_dir):
        errors.append("%s must be a real directory" % relative_dir)
        return catalog
    try:
        type_registry = receipt_type_contract.load_receipt_type_registry(root)
    except receipt_type_contract.ReceiptTypeContractError as exc:
        errors.append("current Receipt type registry is invalid: %s" % exc)
        return catalog
    catalog._type_registry = type_registry
    seen_receipt_paths = {}
    for dirpath, dirnames, filenames in os.walk(receipt_dir, topdown=True,
                                                followlinks=False):
        safe_dirs = []
        for name in sorted(dirnames):
            full = os.path.join(dirpath, name)
            if dirpath == receipt_dir and name == "cold":
                # The cold namespace is loaded by cold_receipt_store from
                # its manifest and index, never by this recursive scan.
                continue
            if os.path.islink(full):
                errors.append("receipt namespace contains symlink directory %s" %
                              os.path.relpath(full, root))
            else:
                safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in sorted(filenames):
            if not name.endswith(".jsonl"):
                continue
            full = os.path.join(dirpath, name)
            relative = os.path.relpath(full, root)
            try:
                stat_result = os.lstat(full)
            except OSError as exc:
                errors.append("cannot stat receipt register %s: %s" %
                              (relative, exc))
                continue
            if os.path.islink(full) or not os.path.isfile(full):
                errors.append("receipt register is not a regular file: %s" % relative)
                continue
            if stat_result.st_nlink != 1:
                errors.append("receipt register must not be hard-linked: %s" % relative)
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except (OSError, UnicodeError) as exc:
                errors.append("cannot read receipt register %s: %s" %
                              (relative, exc))
                continue
            for line_number, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    receipt = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append("malformed receipt %s:%d: %s" %
                                  (relative, line_number, exc))
                    continue
                if not isinstance(receipt, dict):
                    errors.append("receipt %s:%d must be a JSON object" %
                                  (relative, line_number))
                    continue
                receipt_id = receipt.get("receipt_id")
                if not nonempty_string(receipt_id):
                    errors.append("receipt %s:%d has no receipt_id" %
                                  (relative, line_number))
                    continue
                if receipt_id in seen_receipt_paths:
                    errors.append("duplicate receipt_id %s in %s and %s" %
                                  (receipt_id, seen_receipt_paths[receipt_id],
                                   relative))
                    continue
                seen_receipt_paths[receipt_id] = relative
                admission_errors = []
                for lifecycle in ("hot", "historical"):
                    admission_errors.extend(
                        "%s: %s" % (lifecycle, error)
                        for error in receipt_type_contract.current_receipt_errors(
                            receipt, lifecycle, root=root,
                            registry=type_registry))
                if admission_errors:
                    errors.extend(
                        "receipt %s:%d is not a current-contract Receipt: %s" %
                        (relative, line_number, error)
                        for error in admission_errors)
                    continue
                catalog[receipt_id] = (relative, receipt)
    return catalog


def _cold_register_lines(path, label, errors):
    """Read one append-only cold register as exact lines, or None."""
    try:
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
    except (OSError, UnicodeError) as exc:
        errors.append("cannot read %s: %s" % (label, exc))
        return None
    if content and not content.endswith("\n"):
        errors.append("%s does not end with a newline; a truncated append "
                      "leaves the cold chain unprovable (K12/07 fail-closed)"
                      % label)
        return None
    return content.splitlines()


def receipt_group_sha256(lines):
    """Hash one ordered group of receipt-register rows exactly as written."""
    payload = "".join(line + "\n" for line in lines)
    return kblib.sha256_bytes(payload.encode("utf-8"))


def _cold_journal_errors(root, errors):
    """Every seal transaction must have reached its ``complete`` row.

    The journal is what makes an interrupted seal loud.  ``begin`` lands
    before the first segment byte and ``complete`` lands after the hot
    rewrites, so an unmatched ``begin`` means a writer died mid-transaction
    and the operator must reconcile it against the recorded fingerprints
    rather than let a half-sealed archive validate.
    """
    journal_path = os.path.join(root, kblib.RECEIPT_COLD_JOURNAL_PATH)
    if not os.path.exists(journal_path):
        return
    if not os.path.isfile(journal_path) or os.path.islink(journal_path):
        errors.append("cold journal must be a regular file")
        return
    lines = _cold_register_lines(journal_path, "cold journal", errors)
    if lines is None:
        return
    open_seals = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append("malformed cold journal line %d: %s" %
                          (line_number, exc))
            continue
        if not isinstance(entry, dict):
            errors.append("cold journal line %d must be a JSON object" %
                          line_number)
            continue
        phase = entry.get("phase")
        seal_id = entry.get("seal_receipt")
        if phase not in ("begin", "complete") or not nonempty_string(seal_id):
            errors.append("cold journal line %d must record phase "
                          "begin/complete for one seal_receipt" % line_number)
            continue
        if phase == "begin":
            if seal_id in open_seals:
                errors.append("cold journal opens seal %s twice" % seal_id)
            open_seals[seal_id] = line_number
        else:
            open_seals.pop(seal_id, None)
    for seal_id, line_number in sorted(open_seals.items(),
                                       key=lambda pair: pair[1]):
        errors.append(
            "cold journal seal %s began at line %d and never completed; an "
            "interrupted seal must be reconciled against the journal's "
            "recorded fingerprints before the runtime validates again "
            "(K12/07 fail-closed)" % (seal_id, line_number))


def _cold_register_rows(lines, label, errors):
    """Parse one cold register into rows plus per-seal raw-line groups.

    Runs before any content check, because which rows count as evidence is
    decided by the seal binding and not by the rows themselves.
    """
    rows = []
    groups = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append("malformed %s line %d: %s" %
                          (label, line_number, exc))
            continue
        if not isinstance(entry, dict):
            errors.append("%s line %d must be a JSON object" %
                          (label, line_number))
            continue
        seal_id = entry.get("seal_receipt")
        if not nonempty_string(seal_id):
            errors.append("%s line %d does not name the seal receipt that "
                          "wrote it; an unattributed cold row has no root of "
                          "trust (K12/07 fail-closed)" % (label, line_number))
            continue
        groups.setdefault(seal_id, []).append(line)
        rows.append((line_number, seal_id, entry))
    return rows, groups


def cold_path_within_root(root, relative, errors):
    """Reject a cold path that leaves the repository by any component.

    Checking only the final component is not enough: a symlinked
    intermediate directory -- ``cold/segments`` pointed somewhere else, or
    ``cold`` itself -- moves the whole archive outside the repository while
    every per-file check still passes, and the sealed bytes then live
    somewhere the repository snapshot does not cover.

    This is containment detection for an ordinary mistake or a stale
    working copy, evaluated once per run.  It is not a defence against a
    party who can change the filesystem between the check and its use;
    that boundary is stated in K12/07 and the remaining hardening is
    registered in ROADMAP.md.
    """
    root_real = os.path.realpath(root)
    current = root_real
    for part in relative.split("/"):
        if part in ("", ".", ".."):
            errors.append("cold path %r is not a plain repository path" %
                          relative)
            return False
        current = os.path.join(current, part)
        if os.path.islink(current):
            errors.append("cold path %s traverses symlink %s; sealed evidence "
                          "must live inside the repository it is evidence "
                          "for (K12/07 fail-closed)" %
                          (relative, os.path.relpath(current, root_real)))
            return False
    resolved = os.path.realpath(os.path.join(root_real, relative))
    if resolved != current or not resolved.startswith(root_real + os.sep):
        errors.append("cold path %s resolves outside the repository "
                      "(K12/07 fail-closed)" % relative)
        return False
    return True


def _cold_namespace_errors(root, errors):
    """The cold namespace itself must be a real directory inside the root."""
    for relative in (kblib.RECEIPT_COLD_PREFIX,
                     kblib.RECEIPT_COLD_SEGMENT_PREFIX,
                     kblib.RECEIPT_COLD_EVIDENCE_PREFIX):
        full = os.path.join(root, relative)
        if not os.path.exists(full) and not os.path.islink(full):
            continue
        if not cold_path_within_root(root, relative, errors):
            return False
        if not os.path.isdir(full):
            errors.append("cold path %s must be a directory" % relative)
            return False
    return True


def _cold_manifest_entries(root, rows, bound, errors):
    """Prove each bound manifest row's segment presence and shape."""
    entries = {}
    named = set()
    for line_number, seal_id, entry in rows:
        if seal_id not in bound:
            continue
        segment = entry.get("segment")
        if (not nonempty_string(segment) or
                not (segment.startswith(
                    kblib.RECEIPT_COLD_SEGMENT_PREFIX + "/") or
                     segment.startswith(
                    kblib.RECEIPT_COLD_EVIDENCE_PREFIX + "/")) or
                not segment.endswith(".jsonl") or "/../" in segment):
            errors.append("cold manifest line %d has invalid segment path %r" %
                          (line_number, segment))
            continue
        named.add(segment)
        if segment in entries:
            errors.append("cold manifest repeats segment %s" % segment)
            continue
        sha_value = entry.get("segment_sha256")
        size_value = entry.get("segment_bytes")
        records = entry.get("records")
        if not isinstance(sha_value, str) or not SHA256_RE.fullmatch(sha_value):
            errors.append("cold manifest segment %s has invalid "
                          "segment_sha256" % segment)
            continue
        if (not isinstance(size_value, int) or isinstance(size_value, bool) or
                size_value < 0):
            errors.append("cold manifest segment %s has invalid "
                          "segment_bytes" % segment)
            continue
        if (not isinstance(records, int) or isinstance(records, bool) or
                records < 0):
            errors.append("cold manifest segment %s has invalid records" %
                          segment)
            continue
        if not cold_path_within_root(root, segment, errors):
            continue
        segment_path = os.path.join(root, segment)
        try:
            descriptor = os.lstat(segment_path)
        except OSError:
            errors.append("cold segment %s is missing; sealed evidence "
                          "must stay resolvable (K12/07 fail-closed)" %
                          segment)
            continue
        if os.path.islink(segment_path) or not stat.S_ISREG(descriptor.st_mode):
            errors.append("cold segment %s must be a regular file" % segment)
            continue
        if descriptor.st_nlink != 1:
            # Detection at validation time, not prevention: a second name
            # for sealed bytes is a second writer for them, and this run
            # refuses to vouch for the segment.  It does not stop a party
            # who can create links from doing so between runs.
            errors.append("cold segment %s has %d hard links; a second name "
                          "for sealed bytes is a second writer for them "
                          "(K12/07 fail-closed)" %
                          (segment, descriptor.st_nlink))
            continue
        if descriptor.st_size != size_value:
            errors.append("cold segment %s is %d bytes on disk but the "
                          "manifest sealed %d; sealed bytes may not drift "
                          "(K12/07 fail-closed)" %
                          (segment, descriptor.st_size, size_value))
            continue
        entries[segment] = entry
    return entries, named


def _cold_index_rows(rows, entries, bound, catalog, type_registry, errors):
    """Admit bound projections and bind each to a manifested segment."""
    index = {}
    by_segment = {}
    for line_number, seal_id, entry in rows:
        if seal_id not in bound:
            continue
        receipt_id = entry.get("receipt_id")
        if not nonempty_string(receipt_id):
            errors.append("cold index line %d has no receipt_id" % line_number)
            continue
        receipt_type_id = entry.get("receipt_type_id")
        registration = (type_registry.get(receipt_type_id)
                        if isinstance(receipt_type_id, str) else None)
        if registration is None:
            errors.append("cold index receipt %s has no current registered "
                          "receipt_type_id" % receipt_id)
            continue
        if "cold" not in registration.catalog_lifecycle:
            errors.append("cold index receipt %s has type %s, which is not "
                          "admitted to the cold catalog" %
                          (receipt_id, receipt_type_id))
            continue
        if receipt_id in catalog:
            errors.append("sealed receipt_id %s still present in hot "
                          "register %s; a sealed row must leave the hot "
                          "file it was sealed from" %
                          (receipt_id, catalog[receipt_id][0]))
            continue
        if receipt_id in index:
            errors.append("cold index repeats receipt_id %s" % receipt_id)
            continue
        segment = entry.get("segment")
        if segment not in entries:
            errors.append("cold index receipt %s names unknown segment %r" %
                          (receipt_id, segment))
            continue
        record_sha = entry.get("record_sha256")
        if (not isinstance(record_sha, str) or
                not SHA256_RE.fullmatch(record_sha)):
            errors.append("cold index receipt %s has invalid record_sha256" %
                          receipt_id)
            continue
        record_line = entry.get("line")
        if (not isinstance(record_line, int) or isinstance(record_line, bool)
                or record_line < 1 or
                record_line > entries[segment].get("records", 0)):
            errors.append("cold index receipt %s names line %r, which is "
                          "outside segment %s" %
                          (receipt_id, record_line, segment))
            continue
        index[receipt_id] = entry
        by_segment.setdefault(segment, []).append(entry)
    return index, by_segment


def _cold_verified_records(root, entries, by_segment, type_registry, errors):
    """Re-hash every sealed segment and return the projections it proves.

    This is the per-run cost sealing does not buy out.  Presence and size
    prove nothing about content: a same-length edit to a sealed verdict
    would pass a size check silently, and the projections that consumers
    read are derived from these bytes.  Measured on a 65 MB adopter
    archive this whole pass costs 0.42s; what sealing actually retires is
    typed current-only admission now deliberately parses each body.  Sealing
    retains its storage and integrity boundary, but no longer claims a body-
    parsing performance shortcut that would bypass the current contract.

    The return value is what makes the check load-bearing rather than
    advisory.  Reporting a hash failure while still handing the projection
    to consumers would leave the run resolving a receipt it has just proved
    it cannot vouch for, so an unproven projection is withheld, not warned
    about.
    """
    verified = set()
    for segment in sorted(entries):
        entry = entries[segment]
        try:
            with open(os.path.join(root, segment), "rb") as handle:
                payload = handle.read()
        except OSError as exc:
            errors.append("cold segment %s became unreadable: %s" %
                          (segment, exc))
            continue
        if kblib.sha256_bytes(payload) != entry["segment_sha256"]:
            errors.append("cold segment %s does not match the hash the "
                          "manifest sealed; sealed bytes may not change "
                          "(K12/07 fail-closed)" % segment)
            continue
        if payload.count(b"\n") != entry["records"]:
            errors.append("cold segment %s holds %d records but the manifest "
                          "sealed %d" %
                          (segment, payload.count(b"\n"), entry["records"]))
            continue
        rows = by_segment.get(segment)
        if not rows:
            continue
        try:
            lines = payload.decode("utf-8").splitlines(keepends=True)
        except UnicodeError as exc:
            errors.append("cold segment %s is not valid UTF-8: %s" %
                          (segment, exc))
            continue
        for row in rows:
            raw = lines[row["line"] - 1]
            if kblib.sha256_bytes(raw.encode("utf-8")) != row["record_sha256"]:
                errors.append(
                    "cold index receipt %s does not hash to the sealed record "
                    "at %s line %d; a projection that no longer names its own "
                    "record is an assertion, not evidence (K12/07 "
                          "fail-closed)" % (row["receipt_id"], segment, row["line"]))
                continue
            try:
                body = json.loads(raw)
            except ValueError as exc:
                errors.append("cold receipt %s at %s line %d is not JSON: %s" %
                              (row["receipt_id"], segment, row["line"], exc))
                continue
            if not isinstance(body, dict):
                errors.append("cold receipt %s at %s line %d must be a JSON "
                              "object" %
                              (row["receipt_id"], segment, row["line"]))
                continue
            if body.get("receipt_id") != row["receipt_id"]:
                errors.append("cold receipt %s projection does not match the "
                              "sealed body receipt_id" % row["receipt_id"])
                continue
            if body.get("receipt_type_id") != row.get("receipt_type_id"):
                errors.append("cold receipt %s projection does not match the "
                              "sealed body receipt_type_id" %
                              row["receipt_id"])
                continue
            admission_errors = receipt_type_contract.current_receipt_errors(
                body, "cold", root=root, registry=type_registry)
            if admission_errors:
                errors.extend(
                    "cold receipt %s is not a current-contract Receipt: %s" %
                    (row["receipt_id"], error)
                    for error in admission_errors)
                continue
            verified.add(row["receipt_id"])
    return verified


def _cold_orphan_segment_errors(root, named, errors):
    """A segment file no manifest row names is an interrupted seal.

    Only ``segments/`` is swept.  Born-cold close evidence is written by
    ``check_batch_close`` at close time and adopted into the manifest by
    the next seal, so an unmanifested evidence file is a normal interval
    state -- its integrity is bound by the close attestation that names
    its path, bytes and hash.
    """
    segment_dir = os.path.join(root, kblib.RECEIPT_COLD_SEGMENT_PREFIX)
    if not os.path.isdir(segment_dir):
        return
    for name in sorted(os.listdir(segment_dir)):
        relative = "%s/%s" % (kblib.RECEIPT_COLD_SEGMENT_PREFIX, name)
        if relative not in named:
            errors.append("cold segment file %s is in no manifest row; an "
                          "unreferenced segment is an interrupted seal, not "
                          "spare evidence (K12/07 fail-closed)" % relative)


def _cold_bound_seals(catalog, manifest_groups, index_groups, errors):
    """Bind both cold registers to the seal receipt that wrote them.

    Manifest and index are ordinary editable files with no producer of
    their own; the seal receipt is a receipt, it never seals, and it
    records the exact bytes of the rows one transaction appended.  That
    makes the cold chain terminate where every other claim in this runtime
    terminates -- in the hot receipt register -- instead of in a side table
    that anyone may rewrite.

    Returns the seal IDs whose rows are proven.  Rows of an unproven seal
    are not merely reported: they never enter the catalog, so a forged
    projection cannot resolve for a consumer inside the same run that
    rejects it.
    """
    bound = set()
    for seal_id in sorted(set(manifest_groups) | set(index_groups)):
        entry = catalog.get(seal_id)
        if entry is None:
            errors.append("cold registers name seal receipt %s, which is "
                          "absent from the hot catalog; the cold chain's root "
                          "of trust is its seal receipt and seal receipts "
                          "never seal (K12/07 fail-closed)" % seal_id)
            continue
        receipt = entry[1]
        if (receipt.get("tool") != SEAL_TOOL or
                receipt.get("check") != "receipt_seal" or
                receipt.get("result") != "pass" or
                receipt.get("invalidated_by") is not None):
            errors.append("cold registers name %s as a seal receipt, but that "
                          "receipt is not a passing %s receipt_seal" %
                          (seal_id, SEAL_TOOL))
            continue
        if receipt.get("tool_version") != SEAL_TOOL_VERSION:
            errors.append(
                "seal receipt %s was produced by %s %r, which is not a "
                "current sealing protocol %s; a cold archive is only as "
                "trustworthy as the writer that made it (K12/07 fail-closed)"
                % (seal_id, SEAL_TOOL, receipt.get("tool_version"),
                   SEAL_TOOL_VERSION))
            continue
        proven = True
        for kind, groups, field in (
                ("manifest", manifest_groups, "manifest_rows_sha256"),
                ("index", index_groups, "index_rows_sha256")):
            recorded = receipt.get(field)
            actual = receipt_group_sha256(groups.get(seal_id, []))
            if recorded != actual:
                proven = False
                errors.append(
                    "cold %s rows attributed to seal %s hash to %s but the "
                    "seal receipt recorded %r; a cold register is evidence "
                    "only while its seal receipt still binds its bytes "
                    "(K12/07 fail-closed)" % (kind, seal_id, actual, recorded))
        if proven:
            bound.add(seal_id)
    seen = set(manifest_groups) | set(index_groups)
    for receipt_id, (_relative, receipt) in catalog.items():
        if (receipt.get("tool") != SEAL_TOOL or
                receipt.get("check") != "receipt_seal" or
                receipt.get("result") != "pass" or
                receipt.get("invalidated_by") is not None):
            continue
        if receipt_id not in seen:
            errors.append("seal receipt %s recorded a seal whose manifest and "
                          "index rows are both gone; sealed rows are "
                          "append-only (K12/07 fail-closed)" % receipt_id)
    return bound


def cold_receipt_store(root, errors, catalog):
    """Load and fully verify the K12/07 cold chain, fail-closed.

    Sealing moves parse cost off the hot path.  It does not move integrity
    off it.  Every consistency run re-reads every sealed segment and proves
    its bytes against the manifest hash, proves each projection against the
    exact sealed line it names, proves both registers against the seal
    receipt that wrote them, refuses an unreferenced segment or an
    unfinished seal transaction, and refuses a sealed ``receipt_id`` that
    still has a hot twin.  Absence of the whole namespace means nothing is
    sealed and is not an error.
    """
    store = {"manifest": [], "index": {}, "seals": []}
    # A catalog can be revalidated after a seal, invalidation, or registry
    # update in the same process.  Its cold projection and body caches are a
    # performance detail, never an authority source: discard both before
    # rereading the current manifest/index and type registry.
    catalog.cold = {}
    catalog._sealed_segments.clear()
    catalog._sealed_bodies.clear()
    type_registry = getattr(catalog, "_type_registry", None)
    if type_registry is None:
        try:
            type_registry = \
                receipt_type_contract.load_receipt_type_registry(root)
        except receipt_type_contract.ReceiptTypeContractError as exc:
            errors.append("current Receipt type registry is invalid: %s" % exc)
            catalog.cold = store["index"]
            return store
        catalog._type_registry = type_registry
    manifest_path = os.path.join(root, kblib.RECEIPT_COLD_MANIFEST_PATH)
    index_path = os.path.join(root, kblib.RECEIPT_COLD_INDEX_PATH)
    segment_dir = os.path.join(root, kblib.RECEIPT_COLD_SEGMENT_PREFIX)
    # The journal is checked before anything else, and unconditionally: a
    # seal that died between its begin row and its first segment byte
    # leaves no manifest, no index and no segment at all, and that is
    # exactly the interruption a namespace-presence short-circuit would
    # have declared clean.
    _cold_journal_errors(root, errors)
    if not _cold_namespace_errors(root, errors):
        catalog.cold = store["index"]
        return store
    if (not os.path.exists(manifest_path) and
            not os.path.exists(index_path) and
            not os.path.isdir(segment_dir)):
        catalog.cold = store["index"]
        return store
    for label, path in (("cold manifest", manifest_path),
                        ("cold index", index_path)):
        if not os.path.isfile(path) or os.path.islink(path):
            errors.append("%s must exist as a regular file once the cold "
                          "namespace exists" % label)
            catalog.cold = store["index"]
            return store
    manifest_lines = _cold_register_lines(manifest_path, "cold manifest",
                                          errors)
    index_lines = _cold_register_lines(index_path, "cold index", errors)
    if manifest_lines is None or index_lines is None:
        catalog.cold = store["index"]
        return store
    manifest_rows, manifest_groups = _cold_register_rows(
        manifest_lines, "cold manifest", errors)
    index_rows, index_groups = _cold_register_rows(
        index_lines, "cold index", errors)
    bound = _cold_bound_seals(catalog, manifest_groups, index_groups, errors)
    entries, named = _cold_manifest_entries(root, manifest_rows, bound, errors)
    index, by_segment = _cold_index_rows(
        index_rows, entries, bound, catalog, type_registry, errors)
    verified = _cold_verified_records(
        root, entries, by_segment, type_registry, errors)
    _cold_orphan_segment_errors(root, named, errors)
    store["manifest"] = [entries[segment] for segment in sorted(entries)]
    store["index"] = {receipt_id: row for receipt_id, row in index.items()
                      if receipt_id in verified}
    store["seals"] = sorted(bound)
    catalog.cold = store["index"]
    return store


def require_receipt(catalog, receipt_id, label, errors, expected=None):
    """Resolve one receipt and verify common pass/invalidation bindings.

    A sealed receipt (K12/07 cold chain) can satisfy only bindings carried by
    its verified thin projection.  Existence never means "ID alone": result
    and invalidation are still checked, and an ``expected`` identity is
    checked field by field when the projection contains it.  A missing field
    fails closed and directs body-level consumers to their explicit sealed
    branch; sealing cannot silently weaken a consumer's predicate.
    """
    if not nonempty_string(receipt_id):
        errors.append("%s must identify a receipt" % label)
        return None
    entry = catalog.get(receipt_id)
    if entry is None:
        cold = getattr(catalog, "cold", None) or {}
        projection = cold.get(receipt_id)
        if projection is not None:
            common = {"result": "pass", "invalidated_by": None}
            if expected:
                common.update(expected)
            missing = [field for field in common if field not in projection]
            if missing:
                errors.append(
                    "%s requires field(s) %s from sealed receipt %s, but its "
                    "verified cold projection does not carry them; this "
                    "consumer requires an explicit sealed-body branch" %
                    (label, ", ".join(sorted(missing)), receipt_id))
                return None
            for field, value in common.items():
                actual = projection.get(field)
                if actual != value:
                    errors.append(
                        "%s sealed receipt %s has %s=%r, expected %r" %
                        (label, receipt_id, field, actual, value))
            # Body consumers use the explicit typed sealed-body resolver.
            # Here the absence of errors is only the projection verdict.
            return None
        errors.append("%s references missing receipt %s" % (label, receipt_id))
        return None
    receipt = entry[1]
    common = {"result": "pass", "invalidated_by": None}
    if expected:
        common.update(expected)
    for field, value in common.items():
        if receipt.get(field) != value:
            errors.append("%s receipt %s has %s=%r, expected %r" %
                          (label, receipt_id, field, receipt.get(field), value))
    return receipt
