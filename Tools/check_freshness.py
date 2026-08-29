#!/usr/bin/env python3
"""Deterministic, closed-world freshness (review_by) check.

Invocation tier (v2.0): maintenance-run only; not part of per-batch checks
(removed from the K12/05 per-batch checklist; run once at the start of a
maintenance run).

Method:
- scan the frontmatter of every .md file in the vault (restricted YAML
  subset parser, kblib);
- skip pages whose `lifecycle` is retired / merged;
- skip files whose path contains a component given via --exclude
  (repeatable; default: none);
- every active in-scope page receives exactly one typed outcome; malformed
  frontmatter, invalid/future completed-event dates, and unresolved policy are
  maintenance candidates rather than skipped observations;
- volatility: an explicit valid frontmatter declaration always wins; when a
  domain -> volatility mapping is supplied via --defaults (a flat file, or
  .cambium/derived/vocab.yaml / a profile's vocabulary-extensions.yaml via
  their
  volatility_defaults section), pages without an explicit declaration fall
  back to the mapping through their `domain`; otherwise (no --defaults, or
  domain missing / unmapped) the page is an unresolved-policy candidate;
- re-verification intervals come from the strict K08 vocabulary-base
  projection; a null interval means no recurring due date (and still requires
  one completed verification or review event and does not exempt invalid or
  future completed-event evidence);
- baseline date is `last_verified`, falling back to `last_reviewed`; when
  both are missing, the file's UTC modification date is retained only as a
  diagnostic and the page is flagged "pending first verification" (stable
  has no recurring due date, but is not exempt from this first event);
- every explicit non-empty `last_verified` / `last_reviewed` value is validated
  before baseline selection or volatility applicability; malformed or future
  completed events are candidates rather than freshness evidence;
- `review_by` = baseline + interval; --as-of (default: today) >= review_by
  counts as overdue;
- a zero-file scan reports NOTHING CHECKED as a candidate result.

Result semantics: every actionable or incomplete freshness outcome is
result=candidate -- it only feeds the maintenance-run candidate list and never
changes any status axis of a page. Output is sorted by priority (P0 first),
explicit candidate category, category severity, then path.  Every completed
scan emits a typed summary receipt, including runs that also emitted page
candidates.
Exit codes: 0 = no candidates, 2 = candidates found; this script never
produces fail.

Usage: python3 check_freshness.py <vault_root> [--scope SUBPATH]
       [--as-of YYYY-MM-DD] [--defaults FILE] [--exclude COMPONENT]
       [--receipts PATH] [--json]
"""

import contextlib
import datetime
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import compose_vocab
import freshness_engine
import maintenance_candidates
import profile_admission
import runtime_paths
import vocabulary_contract

TOOL = "check_freshness"
TOOL_VERSION = "2.1.0"

# Re-verification interval (days) per volatility tier.
INTERVAL_DAYS = vocabulary_contract.REVIEW_INTERVALS_DAYS


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
# write.  A run that writes no receipt -- a dry run, or a refusal -- emits the
# empty array; a usage error still exits through argparse before any of this,
# leaving stdout empty and the reason on stderr.
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



def parse_date(value):
    """Parse one strict ISO date for CLI compatibility."""
    return freshness_engine.parse_iso_date(value)


def load_frontmatter(path, raw_bytes=None):
    """Return (frontmatter dict or None, whether parsing failed)."""
    if raw_bytes is None:
        with open(path, "rb") as handle:
            raw_bytes = handle.read()
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, True
    fm_text = kblib.extract_frontmatter(text)
    if fm_text is None:
        return None, False
    try:
        fm = kblib.parse_yaml_subset(fm_text)
    except kblib.YamlSubsetError:
        return None, True
    if not isinstance(fm, dict):
        return None, True
    return fm, False


def load_defaults(path, text=None):
    """Load a domain -> volatility mapping (restricted YAML subset).

    Accepts either a flat `domain: volatility` file, or a composed vocabulary
    artifact / profile extensions file carrying a nested `volatility_defaults`
    mapping (.cambium/derived/vocab.yaml,
    profiles/*/vocabulary-extensions.yaml) -- in
    that case the nested mapping is used.

    Returns a dict; raises ValueError on a malformed file or on a volatility
    value outside fast / slow / stable.
    """
    if text is None:
        with open(path, "rb") as handle:
            text = handle.read().decode("utf-8", errors="strict")
    try:
        mapping = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        raise ValueError("defaults file is not parseable YAML subset: %s" % exc)
    if isinstance(mapping, dict) and isinstance(mapping.get("volatility_defaults"), dict):
        mapping = mapping["volatility_defaults"]
    if not isinstance(mapping, dict):
        raise ValueError("defaults file must be a flat domain -> volatility "
                         "mapping or contain a volatility_defaults mapping")
    result = {}
    for domain, volatility in mapping.items():
        volatility = str(volatility)
        if volatility not in INTERVAL_DAYS:
            raise ValueError(
                "defaults file maps domain %r to invalid volatility %r "
                "(expected fast / slow / stable)" % (domain, volatility))
        result[str(domain)] = volatility
    return result


def _date_text(value):
    return value.isoformat() if value is not None else None


def _fingerprint(value):
    return kblib.sha256_bytes(kblib.canonical_json_bytes(value))


_SCOPE_PROBE_PREFIX = ".__cambium_freshness_scope_probe_v1_"


def _utc_modified_on(mtime_ns):
    """Map a filesystem timestamp to one host-timezone-independent date."""
    # Keep the nanosecond-to-second boundary in integer arithmetic.  A float
    # rounds some instants immediately before UTC midnight up to the following
    # day, changing classification and scan identity across runtimes.
    epoch_seconds = mtime_ns // 1_000_000_000
    return datetime.datetime.fromtimestamp(
        epoch_seconds,
        tz=datetime.timezone.utc,
    ).date()


def _stable_external_file_snapshot(path):
    """Read one standalone defaults file without following its final link."""
    capability = kblib.inherited_path_capability(path, "snapshot")
    if capability is not None:
        if not capability["exists"] or capability["kind"] != "file":
            raise ValueError("standalone defaults must name a regular file")
        data = kblib.read_bytes(path)
        descriptor = os.fstat(capability["target_fd"])
        return data, {
            "dev": descriptor.st_dev,
            "ino": descriptor.st_ino,
            "mode": descriptor.st_mode,
            "nlink": descriptor.st_nlink,
            "size": descriptor.st_size,
            "mtime_ns": descriptor.st_mtime_ns,
            "ctime_ns": descriptor.st_ctime_ns,
            "sha256": kblib.sha256_bytes(data),
        }
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise OSError("standalone defaults snapshots require O_NOFOLLOW")
    listed = os.lstat(path)
    if not stat.S_ISREG(listed.st_mode):
        raise ValueError("standalone defaults must name a regular file")
    descriptor = os.open(
        path, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or
                (listed.st_dev, listed.st_ino) !=
                (before.st_dev, before.st_ino)):
            raise OSError("standalone defaults identity changed before read")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    named_after = os.lstat(path)
    fields = lambda value: (
        value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns,
    )
    if fields(before) != fields(after) or fields(after) != fields(named_after):
        raise OSError("standalone defaults changed while being read")
    data = b"".join(chunks)
    return data, {
        "dev": after.st_dev,
        "ino": after.st_ino,
        "mode": after.st_mode,
        "nlink": after.st_nlink,
        "size": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "sha256": kblib.sha256_bytes(data),
    }


def _directory_identity(path):
    descriptor = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(descriptor.st_mode):
        raise ValueError("scope must name a directory or one Markdown file")
    return {
        "kind": "directory",
        "dev": descriptor.st_dev,
        "ino": descriptor.st_ino,
    }


def _is_markdown_path(path):
    """Preserve the CLI's established case-insensitive Markdown suffix."""
    return isinstance(path, str) and path.lower().endswith(".md")


def _admit_scope(root, requested_scope):
    """Return canonical scope spelling and identity, or fail closed.

    ``repository_path`` owns lexical containment.  For a directory, a safely
    missing child target lets ``repository_target_snapshot`` verify every
    directory component with exact spelling and no symlink traversal without
    duplicating that primitive's descriptor walk here.
    """
    capability = (kblib.inherited_path_capability(
        requested_scope, "snapshot") if requested_scope is not None else None)
    if capability is not None:
        if not capability["exists"]:
            raise ValueError("scope path does not exist")
        descriptor = os.fstat(capability["target_fd"])
        if capability["kind"] == "directory":
            return requested_scope, {
                "kind": "directory", "dev": descriptor.st_dev,
                "ino": descriptor.st_ino,
            }
        if capability["kind"] == "file" and \
                _is_markdown_path(requested_scope):
            return requested_scope, {
                "kind": "file", "dev": descriptor.st_dev,
                "ino": descriptor.st_ino,
            }
        raise ValueError("scope must name a directory or one Markdown file")

    if requested_scope is None or requested_scope == ".":
        return ".", _directory_identity(root)

    absolute = kblib.repository_path(
        root, requested_scope, must_exist=True, reject_symlink=True)
    if os.path.isdir(absolute):
        # Select a child name observed missing in this directory.  The target
        # primitive then proves every existing scope component by exact name
        # and no-follow traversal.  No fixed repository name is reserved: if
        # a concurrent creator wins the tiny selection window, fail closed.
        entries = set(os.listdir(absolute))
        counter = 0
        while True:
            probe_name = "%s%d__" % (_SCOPE_PROBE_PREFIX, counter)
            if (probe_name not in entries and
                    not os.path.lexists(os.path.join(absolute, probe_name))):
                break
            counter += 1
        probe_path = requested_scope + "/" + probe_name
        probe = kblib.repository_target_snapshot(
            root, probe_path, singly_linked=True)
        if probe.exists:
            raise ValueError(
                "scope changed while its canonical boundary was admitted")
        if (probe.parent_repository_path != requested_scope or
                probe.missing_components != (probe_name,)):
            raise ValueError("cannot prove canonical scope boundary")
        return requested_scope, _directory_identity(absolute)

    if not _is_markdown_path(requested_scope):
        raise ValueError("scope must name a directory or one Markdown file")
    canonical = kblib.canonical_repository_file(
        root, requested_scope, singly_linked=True)
    descriptor = os.lstat(canonical)
    return requested_scope, {
        "kind": "file",
        "dev": descriptor.st_dev,
        "ino": descriptor.st_ino,
    }


def _scope_argument(scope):
    if scope == "." and kblib.inherited_path_capability(
            scope, "snapshot") is None:
        return None
    return scope


def _listed_markdown_paths(root, scope):
    root = os.path.realpath(os.path.abspath(root))
    scope_argument = _scope_argument(scope)
    admitted_scope, identity = _admit_scope(root, scope_argument)
    capability = (kblib.inherited_path_capability(
        scope_argument, "snapshot") if scope_argument else None)
    if capability is not None:
        if capability["kind"] == "file":
            return [admitted_scope]
        snapshot = kblib.repository_tree_snapshot(root, admitted_scope)
        prefix_length = 0 if admitted_scope == "." else len(admitted_scope)
        return sorted(path for path in snapshot.files
                      if _is_markdown_path(path) and
                      not any(component.startswith(".") for component in
                              path[prefix_length:].lstrip("/").split(
                                  "/")[:-1]))
    base = (root if admitted_scope == "." else
            kblib.repository_path(root, admitted_scope, must_exist=True,
                                   reject_symlink=True))
    if not os.path.isdir(base):
        return ([admitted_scope]
                if _is_markdown_path(admitted_scope) else [])

    def raise_walk_error(error):
        raise error

    result = []
    # This gate cannot use the convenience iterator's default ``onerror=None``:
    # silently skipping one unreadable or concurrently removed directory would
    # turn an incomplete observation into a closed-world expected set.  One
    # walk therefore owns error propagation, hidden-directory policy, visible
    # symlink rejection, and Markdown collection together.
    for dirpath, dirnames, filenames in os.walk(
            base, topdown=True, onerror=raise_walk_error,
            followlinks=False):
        visible_directories = sorted(
            name for name in dirnames if not name.startswith("."))
        for name in visible_directories:
            candidate = os.path.join(dirpath, name)
            descriptor = os.lstat(candidate)
            if stat.S_ISLNK(descriptor.st_mode):
                relative = os.path.relpath(
                    candidate, root).replace(os.sep, "/")
                raise ValueError(
                    "Markdown scope contains symlink directory: %s" %
                    relative)
        dirnames[:] = visible_directories
        for name in sorted(filenames):
            if _is_markdown_path(name):
                result.append(os.path.relpath(
                    os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(result)


def _is_excluded(path, exclude_components):
    return any(component in path.split("/")
               for component in exclude_components)


def _page_record(target, *, excluded):
    if excluded:
        # Exclusion is decided entirely from a canonical path plus the closed
        # exclude-component set.  Do not read or hash content outside the
        # admitted scan surface.
        return {"path": target, "excluded": True}
    return {
        "path": target.repository_path,
        "excluded": False,
        "dev": target.dev,
        "ino": target.ino,
        "mode": target.mode,
        "nlink": target.nlink,
        "size": target.size,
        "mtime_ns": target.mtime_ns,
        "ctime_ns": target.ctime_ns,
        "content_sha256": target.sha256,
        "modified_on": _utc_modified_on(target.mtime_ns).isoformat(),
    }


def _capture_scope(root, scope, exclude_components):
    """Capture one closed expected set and exact non-excluded page bytes."""
    snapshots = []
    input_entries = []
    records = []
    for path in _listed_markdown_paths(root, scope):
        excluded = _is_excluded(path, exclude_components)
        if excluded:
            # Validate exact spelling, regular-file shape, links, and every
            # path component without opening the excluded object.
            kblib.canonical_repository_file(
                root, path, singly_linked=True)
            record = _page_record(path, excluded=True)
            records.append(record)
            input_entries.append(record.copy())
            snapshots.append(freshness_engine.PageSnapshot(
                path=path,
                frontmatter={},
                modified_on=datetime.date.min,
                excluded=True,
            ))
            continue

        target = kblib.repository_target_snapshot(
            root, path, singly_linked=True)
        if not target.exists:
            raise OSError("page disappeared before snapshot: %s" % path)
        record = _page_record(target, excluded=False)
        records.append(record)
        input_entries.append({
            "path": path,
            "content_sha256": target.sha256,
            "modified_on": record["modified_on"],
            "excluded": False,
        })
        frontmatter, unparseable = load_frontmatter(
            target.path, raw_bytes=target.data)
        snapshots.append(freshness_engine.PageSnapshot(
            path=path,
            frontmatter=(None if unparseable else (frontmatter or {})),
            frontmatter_error=unparseable,
            modified_on=datetime.date.fromisoformat(record["modified_on"]),
        ))
    return snapshots, records, input_entries


def _scope_currency_errors(root, scope, expected_scope_identity,
                           expected_records, exclude_components):
    """Revalidate set, canonical paths, exact bytes, identity, and UTC mtime."""
    errors = []
    try:
        current_scope, current_identity = _admit_scope(
            root, _scope_argument(scope))
    except (OSError, ValueError) as exc:
        return ["scope is no longer canonical/current: %s" % exc]
    if current_scope != scope or current_identity != expected_scope_identity:
        errors.append("scope identity changed")

    expected_by_path = {
        record["path"]: record for record in expected_records
    }
    try:
        first_paths = _listed_markdown_paths(root, scope)
    except (OSError, ValueError) as exc:
        return errors + ["cannot enumerate final Markdown set: %s" % exc]
    expected_paths = sorted(expected_by_path)
    if first_paths != expected_paths:
        errors.append(
            "Markdown expected set changed: expected=%r observed=%r" %
            (expected_paths, first_paths))

    for path in first_paths:
        expected = expected_by_path.get(path)
        if expected is None:
            continue
        try:
            excluded = _is_excluded(path, exclude_components)
            if excluded != expected["excluded"]:
                errors.append("exclusion classification changed: %s" % path)
                continue
            if excluded:
                kblib.canonical_repository_file(
                    root, path, singly_linked=True)
                continue
            target = kblib.repository_target_snapshot(
                root, path, singly_linked=True)
            if not target.exists:
                errors.append("page disappeared: %s" % path)
                continue
            observed = _page_record(target, excluded=False)
            if observed != expected:
                errors.append("page bytes or identity changed: %s" % path)
        except (OSError, ValueError) as exc:
            errors.append("page is no longer canonical/current: %s: %s" %
                          (path, exc))

    # A second set read closes the window in which an entry could be added or
    # removed while the individual final snapshots were being validated.
    try:
        second_paths = _listed_markdown_paths(root, scope)
    except (OSError, ValueError) as exc:
        errors.append("cannot re-enumerate final Markdown set: %s" % exc)
    else:
        if second_paths != first_paths:
            errors.append(
                "Markdown set changed during final validation: first=%r "
                "second=%r" % (first_paths, second_paths))
    try:
        final_scope, final_identity = _admit_scope(
            root, _scope_argument(scope))
    except (OSError, ValueError) as exc:
        errors.append("scope changed at final boundary: %s" % exc)
    else:
        if final_scope != scope or final_identity != expected_scope_identity:
            errors.append("scope identity changed at final boundary")
    return errors


def _scan_bridge(run, *, scope, exclude_components, defaults_source_kind,
                 defaults_source, defaults_fingerprint,
                 input_snapshot_sha256):
    candidate_records = sorted(({
        "candidate_id": maintenance_candidates.candidate_id_for_path(
            outcome.path),
        "object_path": outcome.path,
        "candidate_kind": outcome.kind,
        "priority": outcome.priority or None,
    } for outcome in run.candidates), key=lambda record: record["object_path"])
    candidate_ids = sorted(
        record["candidate_id"] for record in candidate_records
    )
    candidate_set_sha256 = _fingerprint({
        "schema_version": 1,
        "basis": "sorted-candidate-records-v1",
        "candidate_records": candidate_records,
    })
    binding = {
        "schema_version": 1,
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "as_of": run.as_of.isoformat(),
        "scope": scope,
        "exclude_components": exclude_components,
        "defaults_source_kind": defaults_source_kind,
        "defaults_source": defaults_source,
        "defaults_fingerprint": defaults_fingerprint,
        "input_snapshot_sha256": input_snapshot_sha256,
        "candidate_set_sha256": candidate_set_sha256,
    }
    return {
        "scan_id": "freshness-scan-" + _fingerprint(binding),
        "candidate_ids": candidate_ids,
        "candidate_records": candidate_records,
        "candidate_set_basis": "sorted-candidate-records-v1",
        "candidate_set_sha256": candidate_set_sha256,
        "scope": scope,
        "exclude_components": exclude_components,
        "defaults_source_kind": defaults_source_kind,
        "defaults_source": defaults_source,
        "defaults_fingerprint": defaults_fingerprint,
        "input_snapshot_sha256": input_snapshot_sha256,
    }


def _candidate_details(outcome, as_of):
    """Render one typed engine outcome without re-deciding its semantics."""
    priority = outcome.priority or "no-priority"
    if outcome.kind == freshness_engine.FUTURE_BASELINE:
        events = ", ".join(
            "%s=%s" % (reason.field, _date_text(reason.date_value))
            for reason in outcome.reasons
            if reason.code == "future_completed_event_date"
        )
        return (
            "future-dated completed event: %s is later than as_of=%s; "
            "a completed review or verification event cannot provide "
            "evidence for an earlier reference date (priority=%s)"
            % (events, as_of.isoformat(), priority)
        )
    if outcome.kind == freshness_engine.INVALID_BASELINE:
        events = ", ".join(
            "%s=%r" % (reason.field, reason.raw_value)
            for reason in outcome.reasons
            if reason.code == "invalid_completed_event_date"
        )
        return (
            "invalid completed-event date: %s; every explicit "
            "last_content_modified / last_verified / last_reviewed value "
            "must be YYYY-MM-DD and an "
            "invalid value cannot fall back to another field (as_of=%s, "
            "priority=%s)" % (events, as_of.isoformat(), priority)
        )
    if outcome.kind == freshness_engine.MODIFIED_SINCE_REVIEW:
        modified = next(
            (reason for reason in outcome.reasons
             if reason.code == "content_modified_since_review"), None)
        return (
            "content modified since the current review: "
            "last_content_modified=%s is later than last_reviewed (or no "
            "current review exists); review evidence bound to the prior "
            "semantic content cannot authorize this page (as_of=%s, "
            "priority=%s)" % (
                _date_text(modified.date_value) if modified else "unknown",
                as_of.isoformat(), priority)
        )
    if outcome.kind == freshness_engine.UNPARSEABLE_FRONTMATTER:
        return (
            "unparseable frontmatter prevents lifecycle, completed-event, "
            "and volatility classification; this active-scope observation "
            "cannot support a freshness pass (as_of=%s)" % as_of.isoformat()
        )
    if outcome.kind == freshness_engine.INVALID_VOLATILITY:
        raw = outcome.reasons[0].raw_value if outcome.reasons else None
        return (
            "invalid explicit volatility=%r; expected fast / slow / stable; "
            "an invalid explicit policy cannot fall back to a domain default "
            "(as_of=%s, priority=%s)"
            % (raw, as_of.isoformat(), priority)
        )
    if outcome.kind == freshness_engine.UNRESOLVED_VOLATILITY:
        return (
            "unresolved volatility: no valid explicit value and no domain "
            "default match; the page cannot be classified as fresh "
            "(as_of=%s, priority=%s)" % (as_of.isoformat(), priority)
        )
    if outcome.kind == freshness_engine.PENDING_FIRST_VERIFICATION:
        interval = INTERVAL_DAYS[outcome.volatility]
        if interval is None:
            state = "no recurring review deadline"
            arithmetic = (
                "diagnostic %s=%s; volatility=stable" %
                (outcome.baseline_field, outcome.baseline.isoformat())
            )
        elif outcome.review_by is None:
            state = "due date is outside the representable calendar"
            arithmetic = (
                "diagnostic %s=%s + %d days" %
                (outcome.baseline_field, outcome.baseline.isoformat(),
                 interval)
            )
        else:
            state = (
                "overdue %d days" % (as_of - outcome.review_by).days
                if as_of >= outcome.review_by
                else "due %s" % outcome.review_by.isoformat()
            )
            arithmetic = "%s=%s + %d days" % (
                outcome.baseline_field, outcome.baseline.isoformat(),
                interval)
        return (
            "pending first verification, %s: no last_verified / "
            "last_reviewed; filesystem mtime is diagnostic only, not a "
            "completed event (%s; K08/05; volatility=%s, priority=%s)"
            % (state, arithmetic, outcome.volatility, priority)
        )
    if outcome.kind == freshness_engine.OVERDUE:
        interval = INTERVAL_DAYS[outcome.volatility]
        return (
            "overdue %d days: review_by=%s (%s=%s + %d days, "
            "volatility=%s, priority=%s)"
            % (outcome.overdue_days, outcome.review_by.isoformat(),
               outcome.baseline_field, outcome.baseline.isoformat(),
               interval, outcome.volatility, priority)
        )
    raise ValueError("cannot render non-candidate outcome %s" % outcome.kind)


def _add_outcome_fields(receipt, outcome, as_of, bridge):
    receipt.update({
        "freshness_schema_version": 1,
        "scan_id": bridge["scan_id"],
        "candidate_id": maintenance_candidates.candidate_id_for_path(
            outcome.path),
        "candidate_kind": outcome.kind,
        "reason_codes": [reason.code for reason in outcome.reasons],
        "reasons": [reason.as_dict() for reason in outcome.reasons],
        "as_of": as_of.isoformat(),
        "priority": outcome.priority or None,
        "volatility": outcome.volatility,
        "volatility_source": outcome.volatility_source,
        "baseline_field": outcome.baseline_field,
        "baseline": _date_text(outcome.baseline),
        "review_by": _date_text(outcome.review_by),
        "overdue_days": outcome.overdue_days,
    })
    return receipt


def _add_summary_fields(receipt, run, bridge):
    receipt.update({
        "freshness_schema_version": 1,
        "scan_id": bridge["scan_id"],
        "as_of": run.as_of.isoformat(),
        "scan_complete": run.complete,
        "discovered_count": run.discovered_count,
        "files_count": run.files_count,
        "candidate_count": run.candidate_count,
        "page_candidate_count": run.page_candidate_count,
        "scan_finding_codes": list(run.scan_finding_codes),
        "candidate_ids": bridge["candidate_ids"],
        "candidate_records": bridge["candidate_records"],
        "candidate_set_basis": bridge["candidate_set_basis"],
        "candidate_set_sha256": bridge["candidate_set_sha256"],
        "classification_counts": run.counts,
        "scope": bridge["scope"],
        "exclude_components": bridge["exclude_components"],
        "defaults_source_kind": bridge["defaults_source_kind"],
        "defaults_source": bridge["defaults_source"],
        "defaults_fingerprint": bridge["defaults_fingerprint"],
        "input_snapshot_sha256": bridge["input_snapshot_sha256"],
    })
    return receipt


def main():
    ap = kblib.ArgumentParser(
        description="Closed-world freshness / review_by candidate check")
    ap.add_argument("vault_root", help="vault root directory")
    ap.add_argument("--scope", help="only scan .md files under this subpath")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="reference date YYYY-MM-DD for overdue computation "
                         "(default: today)")
    ap.add_argument("--defaults", dest="defaults", default=None,
                    help="optional domain -> volatility mapping file "
                         "(restricted YAML subset); an active page with no "
                         "explicit or defaulted volatility is a candidate")
    ap.add_argument("--exclude", action="append", default=[],
                    metavar="COMPONENT",
                    help="skip files whose path contains this component "
                         "(repeatable; default: none)")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    ap.add_argument("--json", action="store_true", help=JSON_HELP)
    args = ap.parse_args()

    if not args.json:
        return _run(args)
    return _run_reporting_json(lambda: _run(args))


def _run(args):
    root_argument = os.path.abspath(args.vault_root)
    root = os.path.realpath(root_argument)

    as_of = parse_date(args.as_of) if args.as_of else datetime.date.today()
    if as_of is None:
        print("check_freshness: cannot parse --as-of (expected YYYY-MM-DD): %r"
              % args.as_of)
        return 1

    defaults_map = None
    defaults_source_kind = "none"
    defaults_source = None
    defaults_fingerprint = _fingerprint({
        "schema_version": 1,
        "volatility_defaults": None,
    })
    defaults_admission = None
    defaults_snapshot = None
    standalone_defaults_record = None
    if args.defaults:
        try:
            defaults_absolute = os.path.abspath(args.defaults)
            canonical_spellings = {
                os.path.abspath(os.path.join(
                    root_argument, compose_vocab.DEFAULT_OUTPUT)),
                os.path.abspath(os.path.join(
                    root, compose_vocab.DEFAULT_OUTPUT)),
            }
            if defaults_absolute in canonical_spellings:
                defaults_source_kind = "canonical"
                defaults_source = compose_vocab.DEFAULT_OUTPUT
                defaults_admission, admission_errors = \
                    profile_admission.admit_profile(root)
                if defaults_admission is None:
                    raise ValueError(
                        "canonical %s requires "
                        "selected Profile "
                        "admission: %s" % (
                            runtime_paths.VOCAB_ARTIFACT_PATH,
                            "; ".join(admission_errors)))
                defaults_snapshot, artifact_errors = \
                    compose_vocab.admitted_artifact(
                        root, args.defaults, defaults_admission)
                if artifact_errors or defaults_snapshot is None:
                    raise ValueError(
                        "canonical %s is not current: %s" % (
                            runtime_paths.VOCAB_ARTIFACT_PATH,
                            "; ".join(artifact_errors)))
                defaults_map = load_defaults(
                    args.defaults, defaults_snapshot.read_text())
                defaults_fingerprint = defaults_snapshot.sha256
            else:
                defaults_source_kind = "standalone"
                defaults_source = "standalone"
                defaults_bytes, standalone_defaults_record = \
                    _stable_external_file_snapshot(args.defaults)
                defaults_text = defaults_bytes.decode(
                    "utf-8", errors="strict")
                defaults_map = load_defaults(args.defaults, defaults_text)
                defaults_fingerprint = kblib.sha256_bytes(defaults_bytes)
        except (OSError, ValueError) as exc:
            print("check_freshness: cannot load --defaults file: %s" % exc)
            return 1

    exclude_components = sorted(set(
        e.strip("/") for e in args.exclude if e.strip("/")))
    try:
        scope_value, scope_identity = _admit_scope(root, args.scope)
        snapshots, page_records, input_entries = _capture_scope(
            root, scope_value, exclude_components)
    except (OSError, ValueError) as exc:
        print("check_freshness: cannot establish canonical page snapshot: %s"
              % exc)
        return 1

    input_snapshot_sha256 = _fingerprint({
        "schema_version": 1,
        "files": sorted(input_entries, key=lambda entry: entry["path"]),
    })

    run = freshness_engine.evaluate_freshness(
        snapshots,
        freshness_engine.FreshnessPolicy(
            as_of=as_of,
            volatility_defaults=defaults_map,
        ),
    )
    if not run.complete:
        print("check_freshness: internal classification did not account for "
              "every discovered page; refusing freshness evidence")
        return 1
    counts = run.counts
    bridge = _scan_bridge(
        run,
        scope=scope_value,
        exclude_components=exclude_components,
        defaults_source_kind=defaults_source_kind,
        defaults_source=defaults_source,
        defaults_fingerprint=defaults_fingerprint,
        input_snapshot_sha256=input_snapshot_sha256,
    )

    receipts = []
    seq = 0
    rendered_candidates = []
    for outcome in run.candidates:
        seq += 1
        details = _candidate_details(outcome, as_of)
        rendered_candidates.append((outcome, details))
        receipt = kblib.make_receipt(
            TOOL, TOOL_VERSION, "freshness", outcome.path, "candidate",
            details + "; enters the maintenance-run candidate list; "
                      "does not change any status axis", seq)
        receipts.append(_add_outcome_fields(
            receipt, outcome, as_of, bridge))

    seq += 1
    # Receipt targets are repository/vault-relative identities.  The exact
    # observed inputs are already content-bound below; persisting a machine-
    # local absolute checkout path would make otherwise identical evidence
    # non-portable without strengthening its identity.
    summary_target = scope_value
    if run.nothing_checked:
        summary_details = (
            "as_of=%s: zero Markdown files were discovered; this run checked "
            "nothing and is not evidence of freshness" % as_of.isoformat()
        )
    elif run.candidates:
        summary_details = (
            "as_of=%s scan_complete=true freshness_candidates=%d; a run with "
            "candidates cannot emit passing freshness evidence"
            % (as_of.isoformat(), len(run.candidates))
        )
    else:
        summary_details = (
            "as_of=%s scan_complete=true no freshness candidates"
            % as_of.isoformat()
        )
    summary = kblib.make_receipt(
        TOOL, TOOL_VERSION, "freshness-check-summary", summary_target,
        run.result, summary_details, seq)
    receipts.append(_add_summary_fields(summary, run, bridge))

    if defaults_admission is not None:
        currency_errors = compose_vocab.artifact_currency_errors(
            root, args.defaults, defaults_admission)
        if currency_errors:
            print("check_freshness: canonical --defaults changed during "
                  "validation: %s" % "; ".join(currency_errors))
            return 1
        evidence = {
            "selected_profile_manifest":
                defaults_admission.manifest_repo_path,
            "profile_snapshot_sha256":
                defaults_admission.evaluation.profile_snapshot_sha256,
            "profile_contract_fingerprint":
                defaults_admission.evaluation.profile_contract_fingerprint,
            "profile_load_inputs_sha256":
                defaults_admission.evaluation.profile_load_inputs_sha256,
            "compiled_vocab_sha256": defaults_snapshot.sha256,
        }
        for receipt in receipts:
            receipt.update(evidence)

    if standalone_defaults_record is not None:
        try:
            _defaults_bytes, current_defaults_record = \
                _stable_external_file_snapshot(args.defaults)
        except (OSError, ValueError) as exc:
            print("check_freshness: standalone --defaults changed during "
                  "validation: %s" % exc)
            return 1
        if current_defaults_record != standalone_defaults_record:
            print("check_freshness: standalone --defaults changed during "
                  "validation; retry from a stable snapshot")
            return 1

    page_currency_errors = _scope_currency_errors(
        root, scope_value, scope_identity, page_records,
        exclude_components)
    if page_currency_errors:
        print("check_freshness: page snapshot changed during validation: %s"
              % "; ".join(page_currency_errors))
        return 1

    print("check_freshness: as_of=%s observed %d in-scope files (%d "
          "retired/merged) plus %d excluded" %
          (as_of.isoformat(), run.files_count,
           counts[freshness_engine.INACTIVE],
           counts[freshness_engine.EXCLUDED]))
    print("  overdue=%(overdue)d future_baseline=%(future_baseline)d "
          "invalid_baseline=%(invalid_baseline)d "
          "pending_first_verification="
          "%(pending_first_verification)d fresh=%(fresh)d "
          "stable_no_due_date=%(stable)d "
          "invalid_volatility=%(invalid_volatility)d "
          "unresolved_volatility=%(unresolved_volatility)d "
          "unparseable_frontmatter=%(unparseable_frontmatter)d" % counts)
    for outcome, details in rendered_candidates:
        print("  [CANDIDATE] %s — %s" % (outcome.path, details))
    if run.nothing_checked:
        print("  Conclusion: NOTHING CHECKED — zero Markdown files were "
              "discovered. This is not evidence of freshness.")
    elif run.candidates:
        print("  Conclusion: %d maintenance-run freshness candidate(s); "
              "no passing freshness summary." % len(run.candidates))
    else:
        print("  Conclusion: no maintenance-run freshness candidates.")

    kblib.write_receipts(args.receipts, _record_receipts(receipts))
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
