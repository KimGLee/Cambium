#!/usr/bin/env python3
"""Deterministically apply one batch Coverage Delta.

Every mode rejects page-level attempts to mutate Coverage control fields.  The
legacy two-path mode remains available for detached ledgers.  Supplying
``--root`` selects the canonical runtime mode: paths and Queue state are
bound, writes use the shared runtime lock and optimistic fingerprints, and a
post-write Queue reconciliation must pass before a receipt is published.

Unlike the neighbouring tools, a canonical apply publishes its receipt into a
*new* file rather than appending to a shared JSONL, so that an interrupted
apply cannot be confused with a completed one.  Omitting ``--receipts`` names
``.cambium/receipts/<receipt_id>.jsonl`` automatically; an explicit
``--receipts`` path that already exists is refused.
"""

import contextlib
import copy
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import batch_settlement
import coverage_delta
import kblib
import metadata_execution_contract
import metadata_property_state
import project_page_state

TOOL, TOOL_VERSION = "apply_delta", "1.6.0"

# These fields are owned by Coverage reconciliation / Queue compilation, not
# by a worker-produced page delta.  Their presence is an operation-wide error
# even when the supplied value is identical to the current value.
CONTROL_FIELDS = frozenset((
    "coverage_disposition", "canonical_owner", "batch", "next_batch",
    "priority", "tier", "type", "prerequisites", "deferred_reason",
    "reentry_condition",
))

# Known non-control scalar fields in the generic Coverage contract.  Profile
# extension fields remain legal and visible through warnings.
KNOWN_SCALAR_KEYS = frozenset((
    "authoring_status", "lifecycle", "volatility", "review_by",
))


# ---------------------------------------------------------------------------
# `--json` output (machine-readable receipts)
#
# Purely additive: without the flag not one byte of this tool's behaviour
# moves.  With it, everything written for a person goes to stderr and stdout
# carries this run's receipt objects, serialized verbatim as one canonical
# JSON array.
#
# Nothing is filtered or renamed.  `schemas/receipt.template.jsonl` guarantees
# only the base fields every receipt carries; extension fields differ per
# producer and are discoverable from the receipt itself, which is why that
# template says in its own text that its examples are "not the complete set".
# A field allowlist here would silently drop exactly the fields a caller came
# for.
#
# This tool's receipts are written from inside its transaction helpers, well
# below `main`, so the run collects them where they are handed to the receipt
# writer rather than threading an accumulator through every frame.
# ---------------------------------------------------------------------------
JSON_HELP = ("write this run's receipt objects to stdout as one canonical "
             "JSON array and move the human-readable report to stderr; "
             "receipt writing, verdicts, and exit codes are unchanged")

_JSON_RECEIPTS = []


def _record_receipts(receipts):
    """Remember the exact receipt objects handed to the receipt writer."""
    _JSON_RECEIPTS.extend(receipts)
    return receipts


def emit_json_receipts(receipts):
    """Write the exact receipt objects this run produced to real stdout.

    The one canonical serializer is `kblib.canonical_json_bytes`; this module
    owns no serializer of its own.  A run that produced no receipt writes
    nothing, which keeps the already-settled rejection shape (empty stdout,
    one line of reason on stderr, exit 1) intact.
    """
    if not receipts:
        return
    sys.stdout.write(
        kblib.canonical_json_bytes(list(receipts)).decode("utf-8") + "\n")


def _run_reporting_json(runner):
    """Run `runner`, reserving stdout for JSON and giving stderr the prose."""
    with contextlib.redirect_stdout(sys.stderr):
        exit_code = runner()
    emit_json_receipts(_JSON_RECEIPTS)
    return exit_code


def _parse_delta_bytes(raw):
    text = raw.decode("utf-8")
    parseable = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    )
    value = kblib.parse_yaml_subset(parseable)
    if not isinstance(value, dict):
        raise kblib.YamlSubsetError("delta top level must be a mapping")
    return value



def find_page_block(lines, path):
    """Return the line range for one ``- path:`` Coverage entry."""
    pattern = re.compile(r'^(\s*)-\s+path:\s*(.*?)\s*$')
    for index, line in enumerate(lines):
        clean = kblib.strip_yaml_comment(line.rstrip("\r\n"))
        match = pattern.match(clean)
        if not match or str(kblib.parse_scalar(match.group(2))) != path:
            continue
        indent = len(match.group(1))
        end = index + 1
        while end < len(lines):
            candidate = lines[end]
            if re.match(r'^\s{%d}-\s' % indent, candidate):
                break
            if candidate.strip():
                candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                if candidate_indent <= indent:
                    break
            end += 1
        return index, end
    return None, None


def block_get(lines, start, end, key):
    pattern = re.compile(r'^(\s+)' + re.escape(key) + r':\s*(.*)$')
    for index in range(start + 1, end):
        match = pattern.match(lines[index])
        if match:
            raw = kblib.strip_yaml_comment(match.group(2)).strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
                raw = raw[1:-1]
            return index, match.group(1), raw
    return None, None, None


def get_receipt_ids(lines, start, end):
    """Read inline or block-list gate receipt ids from one page block."""
    line_index, indent, raw = block_get(lines, start, end, "gate_receipts")
    if line_index is None:
        return None, None, [], None
    if raw:
        values = [item.strip().strip("\"'")
                  for item in raw.strip("[]").split(",") if item.strip()]
        return line_index, indent, values, line_index
    values, last = [], line_index
    item_pattern = re.compile(r'^(\s+)-\s+(.*?)\s*$')
    for index in range(line_index + 1, end):
        match = item_pattern.match(lines[index])
        if not match or len(match.group(1)) <= len(indent):
            break
        raw_item = kblib.strip_yaml_comment(match.group(2)).strip()
        values.append(raw_item.strip("\"'"))
        last = index
    return line_index, indent, values, last


def _delta_policy_errors(delta):
    errors = []
    pages = delta.get("pages")
    if not isinstance(pages, list):
        return ["delta pages must be an explicit list"]
    seen_paths = set()
    for index, page in enumerate(pages):
        label = "pages[%d]" % index
        if not isinstance(page, dict):
            errors.append("%s must be a mapping" % label)
            continue
        forbidden = sorted(CONTROL_FIELDS.intersection(page))
        if forbidden:
            errors.append(
                "%s contains worker-forbidden Coverage control field(s): %s" %
                (label, ", ".join(forbidden))
            )
        path = page.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append("%s path must be a non-empty string" % label)
        elif path in seen_paths:
            errors.append("delta repeats page path %s" % path)
        else:
            seen_paths.add(path)
        receipts = page.get("gate_receipts")
        if receipts is not None and (
                not isinstance(receipts, list) or
                not all(isinstance(value, str) and value.strip()
                        for value in receipts)):
            errors.append("%s gate_receipts must be a list of non-empty ids" %
                          label)
    generated_at = delta.get("generated_at")
    if (not isinstance(generated_at, str) or
            not check_queue.valid_timestamp(generated_at)):
        errors.append("delta generated_at must be a timezone-aware RFC 3339 timestamp")
    additions = delta.get("open_gaps_added")
    closures = delta.get("open_gaps_closed")
    if not isinstance(additions, list):
        errors.append("open_gaps_added must be an explicit list")
        additions = []
    if not isinstance(closures, list):
        errors.append("open_gaps_closed must be an explicit list")
        closures = []
    for index, gap in enumerate(additions):
        label = "open_gaps_added[%d]" % index
        if not isinstance(gap, dict):
            errors.append("%s must be a mapping" % label)
            continue
        if not isinstance(gap.get("page"), str) or not gap["page"].strip():
            errors.append("%s page must be a non-empty string" % label)
        if not isinstance(gap.get("type"), str) or not gap["type"].strip():
            errors.append("%s type must be a non-empty string" % label)
        if "id" in gap and (not isinstance(gap["id"], str) or
                            not gap["id"].strip()):
            errors.append("%s id must be a non-empty string when present" % label)
    for index, selector in enumerate(closures):
        label = "open_gaps_closed[%d]" % index
        if isinstance(selector, str):
            if not selector.strip():
                errors.append("%s id must be non-empty" % label)
        elif isinstance(selector, dict):
            has_id = isinstance(selector.get("id"), str) and bool(
                selector["id"].strip())
            has_pair = (isinstance(selector.get("page"), str) and
                        bool(selector["page"].strip()) and
                        isinstance(selector.get("type"), str) and
                        bool(selector["type"].strip()))
            if not has_id and not has_pair:
                errors.append("%s must identify id or page+type" % label)
        else:
            errors.append("%s must be a gap id or mapping" % label)
    return errors



def _merge_coverage_sections(text, delta):
    """Apply canonical non-page Coverage sections declared by a delta."""
    return coverage_delta.project_coverage_text(text, delta)


def _build_plan(lines, delta, force=False):
    """Return ``(new_text, planned, rejected, unknown_keys)``."""
    batch = str(delta.get("batch", "")).strip()
    planned, rejected, unknown_keys = [], [], []
    for page in delta.get("pages") or []:
        path = page["path"]
        start, end = find_page_block(lines, path)
        if start is None:
            rejected.append((path, "not-found-in-ledger"))
            continue
        _, _, next_batch = block_get(lines, start, end, "next_batch")
        _, _, historical_batch = block_get(lines, start, end, "batch")
        if (batch and next_batch != batch and historical_batch != batch and
                not force):
            rejected.append((
                path,
                "manifest-mismatch(next_batch=%s,batch=%s)" %
                (next_batch, historical_batch),
            ))
            continue
        edits = []
        for key, value in page.items():
            if key == "path":
                continue
            if key == "gate_receipts":
                line_index, indent, current, last = get_receipt_ids(
                    lines, start, end
                )
                incoming = [str(item) for item in (value or [])]
                merged = current + [item for item in incoming
                                    if item not in current]
                if line_index is not None:
                    block = [f"{indent}gate_receipts:\n"] + [
                        f'{indent}  - "{item}"\n' for item in merged
                    ]
                    edits.append(("range", line_index, last + 1, block))
                else:
                    block = ["    gate_receipts:\n"] + [
                        f'      - "{item}"\n' for item in merged
                    ]
                    edits.append(("range", end, end, block))
                continue
            if key not in KNOWN_SCALAR_KEYS:
                unknown_keys.append((path, key))
            scalar = "" if value is None else str(value)
            line_index, indent, _ = block_get(lines, start, end, key)
            if line_index is not None:
                rendered = (f"{indent}{key}: {scalar}\n" if scalar else
                            f"{indent}{key}:\n")
                edits.append((line_index, rendered))
            else:
                edits.append((end, f"    {key}: {scalar}\n", "insert"))
        planned.append((path, edits))

    flat_edits = [edit for _, edits in planned for edit in edits]

    def edit_position(edit):
        return edit[1] if edit[0] == "range" else edit[0]

    new_lines = list(lines)
    for edit in sorted(flat_edits, key=lambda item: -edit_position(item)):
        if edit[0] == "range":
            _, begin, finish, block = edit
            new_lines[begin:finish] = block
        elif len(edit) == 3 and edit[2] == "insert":
            new_lines.insert(edit[0], edit[1])
        else:
            new_lines[edit[0]] = edit[1]
    return "".join(new_lines), planned, rejected, unknown_keys


def _print_plan(delta, planned, rejected, unknown_keys):
    batch = str(delta.get("batch", "")).strip()
    print("apply_delta: batch=%s planning to update %d page(s), rejected %d "
          "page(s)" % (batch, len(planned), len(rejected)))
    for path, edits in planned:
        print("  [PLAN] %s: %d field update(s)" % (path, len(edits)))
    for path, reason in rejected:
        print("  [REJECT] %s: %s" % (path, reason))
    for path, key in unknown_keys:
        print("  [WARN unknown-key] %s: scalar key %r is outside the "
              "Coverage Ledger core schema; verify its profile registration" %
              (path, key))
    for gap in delta.get("open_gaps_added") or []:
        print("  [PLAN gaps+] %s" % gap)
    for gap in delta.get("open_gaps_closed") or []:
        print("  [PLAN gaps-] %s" % gap)
    for suggestion in delta.get("next_batch_updates") or []:
        print("  [SUGGEST only; not applied] %s" % suggestion)
    for watermark in delta.get("watermark_advance") or []:
        print("  [TODO watermark] %s" % watermark)


def _canonical_paths(args, batch):
    expected_ledger = check_queue.COVERAGE_PATH
    expected_delta = ".cambium/deltas/%s.yaml" % batch
    errors = []
    if args.ledger != expected_ledger:
        errors.append("canonical ledger argument must be exactly %s" %
                      expected_ledger)
    if args.delta != expected_delta:
        errors.append("canonical delta argument must be exactly %s" %
                      expected_delta)
    return expected_ledger, expected_delta, errors


def pre_apply_coverage_archive_path(batch, queue_state_revision):
    """Return the canonical pre-apply Coverage archive path for one apply.

    The delta_apply receipt records ``before_coverage_sha256`` but not the
    bytes behind it, so a post-apply rollback would have nothing to restore
    byte-exactly.  Archiving the pre-apply Coverage under a path keyed by the
    batch and the Queue state revision observed at apply time makes the
    authorised ``merge-ready -> open`` rollback a byte-exact restore instead
    of a reconstruction.  The revision key keeps successive applies of the
    same batch from colliding.
    """
    return ".cambium/receipts/pre-apply-coverage/%s-r%d.yaml" % (
        batch, int(queue_state_revision or 0))


def _prepare_receipt(result, batch, delta_path, delta_sha,
                     before_coverage_sha, after_coverage_sha, actor_role,
                     before_coverage_archive, settlement=None):
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "delta_apply", batch, "pass",
        "canonical Coverage delta applied and Queue post-check passed", 1,
    )
    receipt.update({
        "task_id": result["queue"].get("task_id"),
        "batch_id": batch,
        "actor_role": actor_role,
        "coverage_ledger_path": check_queue.COVERAGE_PATH,
        "delta_path": delta_path,
        "delta_sha256": delta_sha,
        "before_coverage_sha256": before_coverage_sha,
        "before_coverage_archive_path": before_coverage_archive,
        "after_coverage_sha256": after_coverage_sha,
        "before_required_queue_sha256": result.get("queue_sha256"),
        "after_required_queue_sha256": result.get("queue_sha256"),
        "before_progress_sha256": result.get("progress_sha256"),
        "after_progress_sha256": result.get("progress_sha256"),
        "required_queue_sha256": result.get("queue_sha256"),
        "queue_revision": result["queue"].get("queue_revision"),
        "queue_state_revision": result["queue"].get("state_revision"),
    })
    if settlement is not None:
        receipt.update(batch_settlement.transition_binding(settlement))
    return receipt


def _canonical_apply(args, delta, new_text, planned, rejected,
                     planned_coverage_sha, planned_delta_sha):
    root = os.path.realpath(os.path.abspath(args.root))
    batch = str(delta.get("batch", "")).strip()
    _, expected_delta, path_errors = _canonical_paths(args, batch)
    if args.force:
        path_errors.append("--force is forbidden in canonical runtime mode")
    if delta.get("watermark_advance") not in (None, [], {}):
        path_errors.append(
            "watermark_advance needs a registered instance adapter; canonical "
            "Coverage apply cannot silently ignore it"
        )
    for error in path_errors:
        print("[FAIL] %s" % error)
    if path_errors:
        return 1

    try:
        ledger_path = kblib.managed_repository_path(
            root, args.ledger, ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        )
        delta_path = kblib.managed_repository_path(
            root, args.delta, ".cambium/deltas",
            suffixes=(".yaml",), must_exist=True,
        )
        if not os.path.isfile(ledger_path) or not os.path.isfile(delta_path):
            raise ValueError("canonical ledger and delta must be regular files")
        current = check_queue.validate_runtime(
            root,
            allowed_open_delta=(args.delta if args.preflight else None),
        )
    except (OSError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] canonical runtime cannot be loaded: %s" % exc)
        return 1
    if current["errors"]:
        for error in current["errors"]:
            print("[FAIL] current runtime state: %s" % error)
        return 1
    try:
        authority = check_queue.runtime_authority_context(current)
        authority_kwargs = \
            check_queue.runtime_authority_validation_kwargs(authority)
    except (TypeError, ValueError) as exc:
        print("[FAIL] current runtime authority: %s" % exc)
        return 1
    if args.apply:
        barrier = check_queue.delta_apply_write_barrier(
            current, TOOL, "apply", batch)
        if barrier:
            print("[FAIL] %s" % barrier)
            return 1
    if current.get("progress", {}).get("task_state") != "active":
        print("[FAIL] canonical delta apply requires task_state=active")
        return 1
    if current.get("_writer_locks"):
        print("[FAIL] runtime has an active or interrupted writer lock")
        return 1
    if (kblib.sha256_file(ledger_path) != planned_coverage_sha or
            kblib.sha256_file(delta_path) != planned_delta_sha):
        print("[FAIL] Coverage or delta changed while the merge plan was built")
        return 1
    item = current.get("items_by_id", {}).get(batch)
    if item is None:
        print("[FAIL] delta batch %s is absent from Required Queue" % batch)
        return 1
    allowed_states = (("open", "merge-ready") if args.preflight
                      else ("merge-ready",))
    if item.get("state") not in allowed_states:
        print("[FAIL] batch %s is %s, expected merge-ready" %
              (batch, item.get("state")))
        return 1
    # A held batch may not be applied.  `hold_state` is orthogonal to the
    # lifecycle (K13/08), but applying under a hold reaches a state the
    # runtime cannot leave: closing rejects held batches, and clearing the
    # hold is itself a Queue write the post-apply barrier forbids.  Refusing
    # at the entrance keeps that deadlock unreachable.
    if item.get("hold_state") not in (None, "none"):
        print("[FAIL] batch %s is held (hold_state=%s); canonical delta apply "
              "requires hold_state=none" % (batch, item.get("hold_state")))
        return 1
    if not args.preflight and item.get("delta_path") != expected_delta:
        print("[FAIL] batch delta_path does not match %s" % expected_delta)
        return 1
    if not args.preflight and item.get("delta_sha256") != planned_delta_sha:
        print("[FAIL] delta bytes do not match the SHA frozen at merge-ready")
        return 1
    delta_manifest = [page.get("path") for page in delta.get("pages", [])]
    frozen_manifest = item.get("manifest") or []
    if (rejected or not planned or len(delta_manifest) != len(frozen_manifest) or
            set(delta_manifest) != set(frozen_manifest)):
        print("[FAIL] canonical delta must update exactly every frozen manifest page")
        return 1
    try:
        opening_context = check_queue.current_opening_semantic_context(
            current, batch)
    except (TypeError, ValueError) as exc:
        print("[FAIL] canonical delta has no current opening semantic "
              "before-set: %s" % exc)
        return 1
    try:
        parsed_new = kblib.parse_yaml_subset(new_text)
        if not isinstance(parsed_new, dict):
            raise kblib.YamlSubsetError("merged Coverage must be a mapping")
    except kblib.YamlSubsetError as exc:
        print("[FAIL] merged Coverage does not parse: %s" % exc)
        return 1
    settlement = batch_settlement.delta_settlement_report(
        current["coverage"], parsed_new, delta, current["queue"], batch)
    if settlement["errors"]:
        for error in settlement["errors"]:
            print("[FAIL] routed-gap settlement: %s" % error)
        return 1
    if args.preflight:
        print("[PASS] routed-gap preflight clean: obligations=%d "
              "prospective_unsettled=0 coverage_after=%s" %
              (settlement["obligation_count_before"],
               kblib.sha256_bytes(new_text)))
        return 0

    before_coverage_sha = planned_coverage_sha
    before_queue_sha = current.get("queue_sha256")
    before_progress_sha = current.get("progress_sha256")
    delta_coverage = copy.deepcopy(parsed_new)
    after_coverage_sha = kblib.sha256_bytes(new_text)
    archive_relative = pre_apply_coverage_archive_path(
        batch, current["queue"].get("state_revision"))
    receipt = _prepare_receipt(
        current, batch, expected_delta, planned_delta_sha, before_coverage_sha,
        after_coverage_sha, args.actor_role, archive_relative, settlement,
    )
    try:
        metadata_contract = \
            metadata_execution_contract.load_metadata_execution_contract(root)
        profile_contract = current["_profile_authorized_view"]["_contract"]
        projection_rules = \
            metadata_property_state.profile_gate_projection_rules(
                root, profile_contract.extension_gates,
                metadata_contract=metadata_contract,
                authorized_profile_contract=profile_contract)
        parsed_new, property_paths, property_events = \
            metadata_property_state.apply_content_change(
                parsed_new, root, delta_manifest, receipt,
                rules=projection_rules,
                before_semantic_fingerprints=opening_context[
                    "before_semantic_fingerprints"])
        new_text = kblib.canonical_yaml(parsed_new)
        after_coverage_sha = kblib.sha256_bytes(new_text)
        receipt.update({
            "after_coverage_sha256": after_coverage_sha,
            "metadata_execution_contract_fingerprint":
                metadata_contract.contract_fingerprint,
            "metadata_execution_rule_fingerprint":
                project_page_state._rules_fingerprint(projection_rules),
            "selected_profile_manifest": current[
                "_profile_authorized_view"]["selected_profile_manifest"],
            "profile_snapshot_sha256": current[
                "_profile_authorized_view"]["profile_snapshot_sha256"],
            "profile_contract_fingerprint": current[
                "_profile_authorized_view"]["profile_contract_fingerprint"],
            "profile_load_inputs_sha256": current[
                "_profile_authorized_view"]["profile_load_inputs_sha256"],
            "semantic_content_protocol":
                project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
            "opening_transition_receipt": opening_context[
                "opening_transition_receipt"],
            "manifest_semantic_before_set_sha256": opening_context[
                "manifest_semantic_before_set_sha256"],
            "property_events": [dict(event) for event in property_events],
        })
    except (OSError, TypeError, ValueError,
            metadata_execution_contract.MetadataExecutionContractError) as exc:
        print("[FAIL] cannot bind semantic content-change events: %s" % exc)
        return 1
    receipt_relative = args.receipts or (
        ".cambium/receipts/%s.jsonl" % receipt["receipt_id"]
    )
    try:
        receipt_path = kblib.managed_repository_path(
            root, receipt_relative, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False,
        )
    except (OSError, ValueError) as exc:
        print("[FAIL] unsafe receipt path: %s" % exc)
        return 1
    if os.path.lexists(receipt_path):
        print("[FAIL] canonical receipt target already exists: %s" %
              receipt_relative)
        print("       A canonical apply writes one fresh receipt file rather "
              "than appending to a shared JSONL. Omit --receipts to let this "
              "run name .cambium/receipts/<receipt_id>.jsonl itself, or pass "
              "a path that does not exist yet.")
        return 1
    if not os.path.isdir(os.path.dirname(receipt_path)):
        print("[FAIL] canonical receipt parent must already exist")
        return 1
    receipt["receipt_path"] = receipt_relative

    print("canonical delta plan: batch=%s coverage %s -> %s queue=%s" %
          (batch, before_coverage_sha, after_coverage_sha, before_queue_sha))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with both expected hashes")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply canonical Coverage")
        return 1
    if not args.expected_coverage_sha256 or not args.expected_queue_sha256:
        print("[FAIL] --apply requires --expected-coverage-sha256 and "
              "--expected-queue-sha256")
        return 1
    if args.expected_coverage_sha256 != before_coverage_sha:
        print("[FAIL] expected Coverage fingerprint is stale")
        return 1
    if args.expected_queue_sha256 != before_queue_sha:
        print("[FAIL] expected Queue fingerprint is stale")
        return 1

    lock_operation = {
        "tool": TOOL,
        "action": "apply-canonical-coverage-delta",
        "batch_id": batch,
        "task_id": current["queue"].get("task_id"),
        "before_coverage_sha256": before_coverage_sha,
        "planned_after_coverage_sha256": after_coverage_sha,
        "before_required_queue_sha256": before_queue_sha,
        "planned_after_required_queue_sha256": before_queue_sha,
        "before_progress_sha256": before_progress_sha,
        "planned_after_progress_sha256": before_progress_sha,
        "delta_sha256": planned_delta_sha,
        # Retained as the receipt-era spelling consumed by existing tooling;
        # the explicit before/planned-after pair above owns recovery.
        "required_queue_sha256": before_queue_sha,
        "receipt_id": receipt["receipt_id"],
        "receipt_path": receipt_relative,
        "opening_transition_receipt": opening_context[
            "opening_transition_receipt"],
        "manifest_semantic_before_set_sha256": opening_context[
            "manifest_semantic_before_set_sha256"],
    }
    lock_operation.update(check_queue.runtime_authority_lock_fields(authority))
    try:
        with kblib.runtime_write_lock(root, owner_metadata=lock_operation) as lock:
            page_plan = None
            with kblib.no_authoritative_write_guard(lock):
                # Re-read under the lock.  Queue validation sees our own lock
                # but does not treat it as a state error; fingerprints provide
                # CAS.  Any rejection in this region is a proven no-write
                # outcome and must not manufacture an interrupted-write lock.
                locked = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if locked["errors"]:
                    raise ValueError("runtime changed before write: %s" %
                                     "; ".join(locked["errors"]))
                check_queue.require_runtime_authority_current(
                    root, authority, "runtime authority changed under lock")
                barrier = check_queue.delta_apply_write_barrier(
                    locked, TOOL, "apply", batch)
                if barrier:
                    raise ValueError(barrier)
                if kblib.sha256_file(ledger_path) != before_coverage_sha:
                    raise ValueError("Coverage changed after validation")
                if kblib.sha256_file(delta_path) != planned_delta_sha:
                    raise ValueError("delta changed after validation")
                if locked.get("queue_sha256") != before_queue_sha:
                    raise ValueError("Required Queue changed after validation")
                if locked.get("progress_sha256") != before_progress_sha:
                    raise ValueError("Progress Ledger changed after validation")
                if os.path.lexists(receipt_path):
                    raise ValueError("receipt target appeared after validation")
                locked_item = locked.get("items_by_id", {}).get(batch)
                if (locked_item is None or
                        locked_item.get("state") != "merge-ready" or
                        locked_item.get("hold_state") not in (None, "none") or
                        locked_item.get("delta_path") != expected_delta or
                        locked_item.get("delta_sha256") != planned_delta_sha):
                    raise ValueError(
                        "batch is no longer the validated unheld merge-ready "
                        "delta")
                if locked["queue"].get("state_revision") != \
                        current["queue"].get("state_revision"):
                    raise ValueError(
                        "Queue state revision changed after validation; the "
                        "pre-apply Coverage archive key is no longer current")
                locked_opening_context = \
                    check_queue.current_opening_semantic_context(
                        locked, batch)
                if locked_opening_context != opening_context:
                    raise ValueError(
                        "opening semantic before-set changed under lock")
                locked_coverage, locked_property_paths, locked_events = \
                    metadata_property_state.apply_content_change(
                        delta_coverage, root, delta_manifest, receipt,
                        rules=projection_rules,
                        before_semantic_fingerprints=locked_opening_context[
                            "before_semantic_fingerprints"])
                if (kblib.canonical_yaml(locked_coverage) != new_text or
                        tuple(locked_property_paths) != tuple(property_paths) or
                        tuple(locked_events) != tuple(property_events)):
                    raise ValueError(
                        "semantic content-change projection changed under lock")
                if locked_property_paths:
                    owner_removals = {
                        event["path"]: sorted(
                            field for field in event[
                                "invalidated_property_fields"]
                            if field !=
                            metadata_property_state.LAST_REVIEWED)
                        for event in locked_events
                        if any(
                            field != metadata_property_state.LAST_REVIEWED
                            for field in event[
                                "invalidated_property_fields"])
                    }
                    page_plan = metadata_property_state.build_projection_plan(
                        root, locked_coverage, locked_property_paths,
                        rules=projection_rules,
                        authorized_owner_removals=owner_removals)
                locked_settlement = batch_settlement.delta_settlement_report(
                    locked["coverage"], parsed_new, delta, locked["queue"],
                    batch)
                if locked_settlement["errors"]:
                    raise ValueError(
                        "routed-gap settlement changed under lock: %s" %
                        "; ".join(locked_settlement["errors"]))
                if (batch_settlement.transition_binding(locked_settlement) !=
                        batch_settlement.transition_binding(settlement)):
                    raise ValueError(
                        "routed-gap settlement binding changed under lock")

                with open(ledger_path, encoding="utf-8") as handle:
                    old_text = handle.read()
                archive_path = kblib.managed_repository_path(
                    root, archive_relative, ".cambium/receipts",
                    suffixes=(".yaml",), must_exist=False,
                )
                archive_exists = os.path.lexists(archive_path)
                if archive_exists:
                    # An identical archive is a resumed apply of the same
                    # revision and is reusable.  Different bytes under the
                    # same key would silently redefine what "before" means
                    # for the authorised rollback, so fail closed instead.
                    if (not os.path.isfile(archive_path) or
                            kblib.sha256_file(archive_path) !=
                            before_coverage_sha):
                        raise ValueError(
                            "pre-apply Coverage archive %s already exists and "
                            "does not hold the pre-apply bytes" %
                            archive_relative)
                receipt_before = kblib.receipt_append_observation(
                    receipt_path, [receipt]
                )
            wrote_coverage = False
            receipt_attempted = False
            wrote_archive = False
            page_transaction = None
            try:
                if page_plan is not None:
                    page_transaction = project_page_state.stage_projection_plan(
                        root, page_plan, lock,
                        transaction_id="delta-content-%s" %
                        receipt["receipt_id"])
                if not archive_exists:
                    check_queue.require_runtime_authority_current(
                        root, authority,
                        "runtime authority changed before Coverage archive")
                    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
                    kblib.atomic_write_text(
                        archive_path, old_text,
                        validator=kblib.parse_yaml_subset,
                    )
                    wrote_archive = True
                    check_queue.require_runtime_authority_current(
                        root, authority,
                        "runtime authority changed during Coverage archive")
                check_queue.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before Coverage write")
                kblib.atomic_write_text(
                    ledger_path, new_text, validator=kblib.parse_yaml_subset
                )
                wrote_coverage = True
                if page_transaction is not None:
                    page_transaction.publish()
                check_queue.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during Coverage write")
                post = check_queue.validate_runtime(
                    root, extra_receipts=[receipt], **authority_kwargs,
                )
                if post["errors"]:
                    raise ValueError("post-write Queue reconciliation failed: %s" %
                                     "; ".join(post["errors"]))
                if post.get("queue_sha256") != before_queue_sha:
                    raise ValueError("Queue changed during Coverage write")
                if post.get("progress_sha256") != before_progress_sha:
                    raise ValueError("Progress Ledger changed during Coverage write")
                if kblib.sha256_file(delta_path) != planned_delta_sha:
                    raise ValueError("delta changed during Coverage write")
                check_queue.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before delta receipt")
                receipt_attempted = True
                kblib.write_receipts(
                    receipt_path, _record_receipts([receipt]), exclusive=True
                )
                check_queue.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during delta receipt")
                persisted = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if persisted["errors"]:
                    raise ValueError("persisted runtime state: %s" %
                                     "; ".join(persisted["errors"]))
                if page_transaction is not None:
                    page_transaction.commit()
            except Exception as write_error:
                rollback_failures = []
                page_rollback_complete = True
                if (page_transaction is not None and
                        page_transaction.state not in (
                            "rolled-back", "committed")):
                    if page_transaction.state == "commit-cleanup-failed":
                        page_rollback_complete = False
                        rollback_failures.append(
                            "page projection committed but cleanup requires "
                            "recovery")
                    else:
                        try:
                            page_transaction.rollback()
                        except Exception as exc:
                            page_rollback_complete = False
                            rollback_failures.append(
                                "page projection: %s" % exc)
                if receipt_attempted:
                    try:
                        receipt_after = kblib.receipt_append_observation(
                            receipt_path, [receipt]
                        )
                        receipt_outcome = kblib.receipt_append_outcome(
                            receipt_before, receipt_after
                        )
                        # O_EXCL can create the name before a later write or
                        # fsync failure.  A new but exact-record-free file is
                        # therefore not proven external unless the append
                        # failed specifically because another creator won the
                        # name race.
                        if (receipt_outcome == "absent" and
                                not receipt_before.get("exists") and
                                receipt_after.get("exists") and
                                not isinstance(write_error, FileExistsError)):
                            receipt_outcome = "uncertain"
                    except Exception as exc:
                        receipt_outcome = "uncertain"
                        rollback_failures.append(
                            "receipt inspection: %s" % exc
                        )
                    if receipt_outcome != "absent":
                        rollback_failures.append(
                            "append-only receipt publication requires "
                            "recovery: %s" % receipt_outcome
                        )
                if wrote_coverage and page_rollback_complete:
                    try:
                        kblib.atomic_write_text(
                            ledger_path, old_text,
                            validator=kblib.parse_yaml_subset,
                        )
                    except Exception as exc:
                        rollback_failures.append("coverage: %s" % exc)
                elif wrote_coverage:
                    rollback_failures.append(
                        "Coverage retained because page rollback is "
                        "unproven")
                if wrote_archive and page_rollback_complete:
                    # The archive only ever describes a completed apply.  A
                    # failed apply that left it behind would advertise a
                    # rollback point for a delta that was never applied.
                    try:
                        os.remove(archive_path)
                    except OSError as exc:
                        rollback_failures.append(
                            "pre-apply coverage archive: %s" % exc)
                if rollback_failures:
                    raise ValueError(
                        "delta apply failed and rollback is incomplete: %s; %s" %
                        (write_error, "; ".join(rollback_failures))
                    )
                lock.mark_reconciled()
                raise
    except (OSError, ValueError, kblib.YamlSubsetError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] canonical delta write failed; rollback attempted: %s" % exc)
        return 1

    print("[PASS] canonical Coverage delta applied; receipt=%s" %
          receipt_relative)
    return 0


def _legacy_apply(args, _delta, new_text, planned, rejected):
    result = "fail" if rejected and not args.force else (
        "pass" if planned else "candidate"
    )
    wrote = False
    if args.apply and result != "fail":
        try:
            kblib.parse_yaml_subset(new_text)
        except kblib.YamlSubsetError as exc:
            print("apply_delta: ABORT — merged output no longer parses (%s); "
                  "the Ledger was NOT modified" % exc)
            result = "fail"
        else:
            shutil.copyfile(args.ledger, args.ledger + ".bak")
            temporary = args.ledger + ".tmp"
            try:
                with open(temporary, "w", encoding="utf-8") as handle:
                    handle.write(new_text)
                os.replace(temporary, args.ledger)
                wrote = True
            except Exception:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise
            print("apply_delta: written to disk (backup %s.bak; output "
                  "re-parsed OK)" % args.ledger)
    elif not args.apply:
        print("apply_delta: dry run (add --apply to write)")
    if args.receipts:
        receipt = kblib.make_receipt(
            TOOL, TOOL_VERSION, "delta_apply",
            "%s -> %s" % (os.path.basename(args.delta),
                           os.path.basename(args.ledger)),
            result,
            "planned=%d rejected=%d applied=%s" %
            (len(planned), len(rejected), bool(wrote)), 1,
        )
        kblib.write_receipts(args.receipts, _record_receipts([receipt]))
    return 0 if result == "pass" else (1 if result == "fail" else 2)


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Deterministic Coverage Delta application"
    )
    parser.add_argument("ledger",
                        help="Coverage ledger to merge into; canonical mode "
                             "requires exactly %s" % check_queue.COVERAGE_PATH)
    parser.add_argument("delta",
                        help="batch Coverage delta to apply; canonical mode "
                             "requires exactly .cambium/deltas/<batch>.yaml")
    parser.add_argument("--root", help="adopting repository root (canonical mode)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="write the merged Coverage; omit for a dry run")
    mode.add_argument(
        "--preflight", action="store_true",
        help="plan canonical Coverage and routed-gap settlement without writes; "
             "allows an open batch")
    parser.add_argument("--force", action="store_true",
                        help="legacy mode only: keep pages whose ledger "
                             "batch/next_batch does not match the delta batch")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may "
                             "apply canonical Coverage")
    parser.add_argument("--expected-coverage-sha256",
                        help="compare-and-swap guard for canonical --apply: "
                             "sha256:<hex> the caller read from the current "
                             "Coverage; the write is refused when the live "
                             "bytes differ")
    parser.add_argument("--expected-queue-sha256",
                        help="compare-and-swap guard for canonical --apply: "
                             "sha256:<hex> the caller read from the current "
                             "Queue; the write is refused when the live bytes "
                             "differ")
    parser.add_argument("--receipts",
                        help="receipt JSONL destination; canonical mode "
                             "defaults to a new .cambium/receipts/"
                             "<receipt_id>.jsonl and refuses an existing path")
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _run_reporting_json(lambda: _run(args))


def _run(args):
    """This tool's own run; `main` above owns only argument parsing."""
    if args.preflight and args.root is None:
        print("[FAIL] --preflight requires canonical --root mode")
        return 1

    if args.root is None:
        detached_paths = [("ledger", args.ledger), ("delta", args.delta)]
        if args.receipts:
            detached_paths.append(("receipt", args.receipts))
        for label, raw_path in detached_paths:
            lexical = os.path.abspath(raw_path).split(os.sep)
            resolved = os.path.realpath(os.path.abspath(raw_path)).split(os.sep)
            if ".cambium" in lexical or ".cambium" in resolved:
                print("[FAIL] detached mode may not access a .cambium namespace; "
                      "canonical %s access requires --root" % label)
                return 1

    try:
        if args.root is not None:
            root = os.path.realpath(os.path.abspath(args.root))
            delta_file = kblib.repository_path(root, args.delta, must_exist=True,
                                               reject_symlink=True)
            ledger_file = kblib.repository_path(root, args.ledger,
                                                must_exist=True,
                                                reject_symlink=True)
        else:
            delta_file, ledger_file = args.delta, args.ledger
        with open(delta_file, "rb") as handle:
            delta_raw = handle.read()
        delta = _parse_delta_bytes(delta_raw)
        with open(ledger_file, "rb") as handle:
            ledger_raw = handle.read()
        ledger_text = ledger_raw.decode("utf-8")
        lines = ledger_text.splitlines(keepends=True)
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot load Coverage delta inputs: %s" % exc)
        return 1

    policy_errors = _delta_policy_errors(delta)
    batch = delta.get("batch")
    if not isinstance(batch, str) or not check_queue.BATCH_ID_RE.fullmatch(batch):
        policy_errors.append("delta batch must be a path-safe Required Queue id")
    if policy_errors:
        for error in policy_errors:
            print("[FAIL] %s" % error)
        print("apply_delta: entire operation rejected; no files were written")
        return 1

    new_text, planned, rejected, unknown_keys = _build_plan(
        lines, delta, force=args.force
    )
    try:
        new_text = _merge_coverage_sections(new_text, delta)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] Coverage gap reconciliation failed: %s" % exc)
        return 1
    _print_plan(delta, planned, rejected, unknown_keys)
    if args.root is not None:
        return _canonical_apply(
            args, delta, new_text, planned, rejected,
            kblib.sha256_bytes(ledger_raw), kblib.sha256_bytes(delta_raw),
        )
    return _legacy_apply(args, delta, new_text, planned, rejected)


if __name__ == "__main__":
    sys.exit(main())
