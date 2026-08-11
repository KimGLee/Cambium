#!/usr/bin/env python3
"""Apply one optimistic, validated Required Queue lifecycle/hold transition.

The default is a dry run.  Write mode requires ``--apply``, an explicit
integrator role, the expected state revision and Queue fingerprint.  Queue and
Progress references are replaced under one cooperating-writer lock.  Closing
a batch also projects its Coverage ``next_batch`` route in that same guarded
transaction; all written state is restored if any replacement fails.
"""

import argparse
import copy
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import check_corpus_plan
import kblib
import update_task
import apply_delta

TOOL_VERSION = "1.5.0"
# The lifecycle map moved to `kblib` so `check_queue` can read it without
# importing this writer, which imports it.  The name stays here because it is
# this tool's transition guard and every existing reference reads it here.
TRANSITIONS = kblib.BATCH_LIFECYCLE_TRANSITIONS


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _receipt(result, receipt_id, label, expected=None):
    """Resolve one already-validated receipt and enforce operation bindings."""
    # Current transitions may not consume evidence explicitly invalidated by
    # a Standards adoption.  validate_runtime retains the full catalog for
    # historical-chain validation and exposes this filtered view for every
    # new admission/hold-clear/close decision.
    catalog = check_queue.current_receipt_catalog(result)
    entry = catalog.get(receipt_id)
    if entry is None:
        raise ValueError("%s receipt %r does not exist" % (label, receipt_id))
    receipt = entry[1]
    requirements = {"result": "pass", "invalidated_by": None}
    if expected:
        requirements.update(expected)
    for field, value in requirements.items():
        if receipt.get(field) != value:
            raise ValueError("%s receipt %s has %s=%r, expected %r" %
                             (label, receipt_id, field,
                              receipt.get(field), value))
    return receipt


def _pre_apply_coverage_restore(result, apply_receipt):
    """Resolve the byte-exact Coverage restore for an applied-delta rollback.

    ``apply_delta`` archives the pre-apply Coverage bytes before it writes the
    merged ledger and names the archive in its receipt.  Rolling back an
    applied batch therefore restores bytes rather than reconstructing them.
    Every failure here is fail-closed: without the archive the tool cannot
    prove what "before" was, and guessing would put Coverage and the Queue out
    of agreement in a way no later gate re-derives.
    """
    manual = ("The runtime cannot restore the pre-apply Coverage bytes "
              "automatically; an integrator must recover Coverage manually "
              "before this batch can reopen.")
    relative = apply_receipt.get("before_coverage_archive_path")
    expected_sha = apply_receipt.get("before_coverage_sha256")
    if not _nonempty(relative) or not _nonempty(expected_sha):
        raise ValueError(
            "delta application %s does not name a pre-apply Coverage archive. "
            "%s" % (apply_receipt.get("receipt_id"), manual))
    try:
        archive_path = kblib.managed_repository_path(
            result["root"], relative, ".cambium/receipts",
            suffixes=(".yaml",), must_exist=True,
        )
        with open(archive_path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(
            "pre-apply Coverage archive %s is missing or unreadable (%s). %s" %
            (relative, exc, manual))
    actual_sha = kblib.sha256_bytes(text)
    if actual_sha != expected_sha:
        raise ValueError(
            "pre-apply Coverage archive %s holds %s, but delta application %s "
            "recorded %s. %s" %
            (relative, actual_sha, apply_receipt.get("receipt_id"),
             expected_sha, manual))
    try:
        parsed = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        raise ValueError(
            "pre-apply Coverage archive %s does not parse (%s). %s" %
            (relative, exc, manual))
    if not isinstance(parsed, dict):
        raise ValueError(
            "pre-apply Coverage archive %s is not a mapping. %s" %
            (relative, manual))
    return relative, text, actual_sha, parsed


def _corpus_plan_close_expectation(result, item):
    """Derive the non-bypassable current Corpus Planning close condition."""
    plan = check_corpus_plan.validate_corpus_plan(result["root"])
    required, triggers = check_corpus_plan.close_requirement(
        result, item, plan)
    if required:
        plan_errors = [
            "%s %s: %s" % (
                error.get("check"), error.get("target"), error.get("details"))
            for error in plan.get("errors") or []
        ]
        if "R13" in triggers and plan.get("applicability") != "configured":
            plan_errors.append(
                "R13-selected batch requires Corpus Planning "
                "applicability.state=configured")
        if plan_errors:
            raise ValueError(
                "Corpus Planning close requirement fails: %s" %
                "; ".join(plan_errors))
    return required, triggers, plan


def _invalidated_receipt_ids(item):
    """Return every receipt frozen by prior append-only invalidations."""
    result = set()
    history = item.get("invalidation_history")
    if history is None:
        return result
    if not isinstance(history, list):
        raise ValueError("invalidation_history must be an explicit list")
    for index, invalidation in enumerate(history):
        if not isinstance(invalidation, dict):
            raise ValueError("invalidation_history[%d] must be a mapping" % index)
        for field in ("batch_receipts", "delta_gate_receipts",
                      "revalidation_receipts"):
            values = invalidation.get(field)
            if (not isinstance(values, list) or
                    not all(_nonempty(value) for value in values)):
                raise ValueError("invalidation_history[%d] %s must be an "
                                 "explicit string list" % (index, field))
            result.update(values)
    return result


def _current_attempt_revalidation_receipts(item, result):
    """Return hold-clear gate IDs since the most recent rollback."""
    transition_ids = item.get("transition_receipts")
    if not isinstance(transition_ids, list):
        return []
    history = item.get("invalidation_history")
    last_rollback_id = (history[-1].get("transition_receipt")
                        if isinstance(history, list) and history and
                        isinstance(history[-1], dict) else None)
    start = 0
    if last_rollback_id is not None:
        try:
            start = transition_ids.index(last_rollback_id) + 1
        except ValueError:
            raise ValueError("latest invalidation transition is absent from history")
    catalog = result.get("receipt_catalog", {})
    for transition_id in transition_ids:
        if catalog.get(transition_id) is None:
            raise ValueError("transition receipt %s is missing" % transition_id)
    # The hold machine is replayed over the whole history and the discharges
    # filtered to the current attempt: the rollback that opened this attempt's
    # revalidation obligation is the transition immediately before the window,
    # so seeding the replay at the window would read every later clear as
    # discharging nothing.
    window = set(transition_ids[start:])
    receipts = []
    for transition in check_queue.item_revalidation_discharges(item, catalog):
        if transition.get("receipt_id") not in window:
            continue
        if transition.get("before_state") != transition.get("after_state"):
            continue
        evidence = transition.get("evidence_receipt")
        if not _nonempty(evidence):
            raise ValueError("revalidation transition has no evidence receipt")
        receipts.append(evidence)
    if len(receipts) != len(set(receipts)):
        raise ValueError("current attempt repeats revalidation evidence")
    return receipts


def _current_delta_gate_receipts(item, result):
    delta_path = item.get("delta_path")
    if not _nonempty(delta_path):
        raise ValueError("merge-ready batch has no canonical delta")
    delta = kblib.managed_repository_path(
        result["root"], delta_path, ".cambium/deltas",
        suffixes=(".yaml",), must_exist=True,
    )
    if kblib.sha256_file(delta) != item.get("delta_sha256"):
        raise ValueError("merge-ready delta bytes differ from frozen SHA")
    return check_queue.delta_gate_receipt_ids(kblib.load_yaml_file(delta))


def _sync_progress(progress, queue, queue_text):
    result = copy.deepcopy(progress)
    result["required_queue_path"] = check_queue.QUEUE_PATH
    result["queue_revision"] = queue["queue_revision"]
    result["queue_state_revision"] = queue["state_revision"]
    result["required_queue_sha256"] = kblib.sha256_bytes(queue_text)
    return result


def _write_state(coverage_path, coverage_text, queue_path, queue_text,
                 progress_path, progress_text, old_coverage_text,
                 old_queue_text, old_progress_text, write_coverage=False):
    """Replace canonical state files and restore their prior bytes on error.

    Per-file replacement is atomic.  The shared writer lock held by the caller
    prevents cooperating writers from observing or overwriting the
    compare/write/rollback window.  Coverage is written first on close: an
    interruption can then never leave a terminal Queue item named as its own
    future route without the crash-preserved lock exposing the transaction.
    """
    try:
        if write_coverage:
            kblib.atomic_write_text(coverage_path, coverage_text,
                                    validator=kblib.parse_yaml_subset)
        kblib.atomic_write_text(queue_path, queue_text,
                                validator=kblib.parse_yaml_subset)
        kblib.atomic_write_text(progress_path, progress_text,
                                validator=kblib.parse_yaml_subset)
    except Exception:
        try:
            if write_coverage:
                kblib.atomic_write_text(coverage_path, old_coverage_text,
                                        validator=kblib.parse_yaml_subset)
            kblib.atomic_write_text(queue_path, old_queue_text,
                                    validator=kblib.parse_yaml_subset)
            kblib.atomic_write_text(progress_path, old_progress_text,
                                    validator=kblib.parse_yaml_subset)
        finally:
            raise


def _project_closed_coverage(coverage, queue, closing_id):
    """Return the deterministic ownership-and-route projection for one close.

    Closing transfers ``batch`` ownership: every manifest page leaves the
    close with ``batch`` naming the closing batch, so Coverage always reads
    as the most recent closed owner (K12/03).  For an ordinary batch this is
    a no-op; for a successor batch it moves ownership forward.  The complete
    ownership history is not lost by the move — every closed Queue item's
    manifest is immutable, and the consistency checker resolves a closed
    predecessor's manifest through the ``successor_of`` chain.

    Routing is projected as before: a valid canonical pre-state already
    materializes a queued successor in ``next_batch``; that route is
    preserved.  If this pure projection helper sees the closing id instead,
    it can only advance to one explicit queued ``successor_of`` as a
    defensive rule.  Any other route or ambiguous successor set is a
    structural conflict, not something this lifecycle command may guess
    through.
    """
    result = copy.deepcopy(coverage)
    items = {
        entry.get("id"): entry
        for entry in queue.get("required_queue", [])
        if isinstance(entry, dict) and _nonempty(entry.get("id"))
    }
    closing = items.get(closing_id)
    if closing is None:
        raise ValueError("closing batch %s is absent from Queue" % closing_id)
    pages = {
        entry.get("path"): entry
        for entry in result.get("pages", [])
        if isinstance(entry, dict) and _nonempty(entry.get("path"))
    }
    for object_path in closing.get("manifest", []):
        page = pages.get(object_path)
        if page is None:
            raise ValueError("closing manifest object %s has no Coverage record" %
                             object_path)
        successors = sorted(
            item_id for item_id, item in items.items()
            if item_id != closing_id and
            item.get("state") == "queued" and
            item.get("successor_of") == closing_id and
            object_path in (item.get("manifest") or [])
        )
        if len(successors) > 1:
            raise ValueError(
                "Coverage object %s has multiple queued successors of %s: %s" %
                (object_path, closing_id, ", ".join(successors))
            )
        successor = successors[0] if successors else None
        page["batch"] = closing_id
        current_route = page.get("next_batch")
        if current_route == closing_id:
            page["next_batch"] = successor
        elif current_route is None:
            # Keep an explicitly pre-projected terminal route stable.
            page["next_batch"] = None
        elif successor is not None and current_route == successor:
            pass
        else:
            expected = successor if successor is not None else "null"
            raise ValueError(
                "Coverage object %s next_batch %r is neither %s nor %r" %
                (object_path, current_route, closing_id, expected)
            )
    return result


def _transition_item(item, args, result):
    before = item.get("state")
    after = args.transition or before
    if before in ("closed", "cancelled"):
        raise ValueError("%s item is immutable; create a successor batch" % before)
    if args.transition is not None and args.hold_state is not None:
        raise ValueError("lifecycle and hold transitions are separate writes")
    if args.transition and after not in TRANSITIONS.get(before, frozenset()):
        raise ValueError("illegal transition %s -> %s" % (before, after))
    if not args.transition and args.hold_state is None:
        raise ValueError("provide --transition or --hold-state")
    now = args.at

    def require_standards_revalidation():
        outstanding = check_queue.outstanding_standards_revalidation(
            result, item["id"])
        if not outstanding:
            return
        if not _nonempty(args.standards_revalidation_receipt):
            raise ValueError(
                "batch has outstanding Standards revalidation; supply "
                "--standards-revalidation-receipt from "
                "check_queue --require-revalidation")
        receipt_errors = check_queue.standards_revalidation_receipt_errors(
            result, item["id"], args.standards_revalidation_receipt)
        if receipt_errors:
            raise ValueError("invalid Standards revalidation receipt: %s" %
                             "; ".join(receipt_errors))

    if args.transition == "open" and before == "queued":
        require_standards_revalidation()
        blocked = dict(result.get("blocked", [])).get(item["id"], [])
        ignorable = {"confirmation receipt absent"}
        remaining = [reason for reason in blocked
                     if reason not in ignorable and not reason.startswith("hold=")]
        if item.get("hold_state") not in ("none", "confirmation-required"):
            remaining.append("hold=%s" % item.get("hold_state"))
        if remaining:
            raise ValueError("batch is not ready: %s" % "; ".join(remaining))
        if not _nonempty(args.gate_receipt):
            raise ValueError("queued -> open requires --gate-receipt")
        _receipt(result, args.gate_receipt, "activation gate", expected={
            "tool": check_queue.TOOL,
            "tool_version": check_queue.TOOL_VERSION,
            "gate_id": "required-queue-admission",
            "check": "required_queue",
            "queue_check_mode": "require-ready:%s" % item["id"],
            "task_id": result["queue"].get("task_id"),
            "queue_revision": result["queue"].get("queue_revision"),
            "queue_state_revision": result["queue"].get("state_revision"),
            "required_queue_sha256": result.get("queue_sha256"),
            "coverage_ledger_sha256": result.get("coverage_sha256"),
            "progress_ledger_sha256": result.get("progress_sha256"),
            **({"confirmation_receipt": args.confirmation_receipt}
               if item.get("confirmation_required") else {}),
        })
        if item.get("confirmation_required") and not _nonempty(
                args.confirmation_receipt):
            raise ValueError("queued -> open requires --confirmation-receipt")
        if item.get("confirmation_required"):
            _receipt(result, args.confirmation_receipt, "confirmation",
                     expected={"check": "confirmation", "target": item["id"]})
        item["state"] = "open"
        item["hold_state"] = "none"
        item.pop("hold_reason", None)
        item["opened_at"] = now
        item["activation_receipt"] = args.gate_receipt
        if args.confirmation_receipt:
            item["confirmation_receipt"] = args.confirmation_receipt

    elif args.transition == "merge-ready":
        barrier = check_queue.current_attempt_evidence_barrier(
            result, item["id"])
        if barrier:
            raise ValueError(barrier)
        if item.get("hold_state") != "none":
            raise ValueError("held open batch cannot become merge-ready")
        if not _nonempty(args.delta_path):
            raise ValueError("open -> merge-ready requires --delta-path")
        expected_delta = ".cambium/deltas/%s.yaml" % item["id"]
        if args.delta_path != expected_delta:
            raise ValueError("delta path must be exactly %s" % expected_delta)
        try:
            delta = kblib.managed_repository_path(
                result["root"], args.delta_path, ".cambium/deltas",
                suffixes=(".yaml",), must_exist=True,
            )
        except (OSError, ValueError) as exc:
            raise ValueError("delta path is unsafe or missing: %s" % exc)
        if not os.path.isfile(delta):
            raise ValueError("delta path is not a regular file")
        try:
            delta_data = kblib.load_yaml_file(delta)
        except (OSError, ValueError, kblib.YamlSubsetError) as exc:
            raise ValueError("delta cannot be parsed: %s" % exc)
        if delta_data.get("batch") != item["id"]:
            raise ValueError("delta document batch must equal %s" % item["id"])
        policy_errors = apply_delta._delta_policy_errors(delta_data)
        try:
            delta_gate_receipts = check_queue.delta_gate_receipt_ids(delta_data)
        except ValueError as exc:
            delta_gate_receipts = []
            policy_errors.append(str(exc))
        if delta_data.get("watermark_advance") not in (None, [], {}):
            policy_errors.append(
                "watermark_advance needs a registered instance adapter")
        if not isinstance(delta_data.get("next_batch_updates"), list):
            policy_errors.append(
                "next_batch_updates must be an explicit suggestion list")
        coverage_source = result.get("coverage_text")
        if not isinstance(coverage_source, str):
            policy_errors.append("canonical Coverage source bytes are unavailable")
        else:
            try:
                apply_delta._merge_coverage_sections(
                    coverage_source, delta_data)
                _, planned, rejected, _ = apply_delta._build_plan(
                    coverage_source.splitlines(True), delta_data, force=False)
                if rejected or len(planned) != len(item.get("manifest") or []):
                    policy_errors.append(
                        "delta does not apply exactly to the frozen manifest")
            except (KeyError, TypeError, ValueError,
                    kblib.YamlSubsetError) as exc:
                policy_errors.append("delta apply policy failed: %s" % exc)
        if policy_errors:
            raise ValueError("delta policy: %s" % "; ".join(policy_errors))
        if not args.batch_receipt or not all(_nonempty(value)
                                             for value in args.batch_receipt):
            raise ValueError("open -> merge-ready requires --batch-receipt")
        if len(args.batch_receipt) != 1:
            raise ValueError(
                "open -> merge-ready requires exactly one current "
                "batch-review gate")
        batch_receipt_errors = check_queue.batch_review_receipt_errors(
            check_queue.current_receipt_catalog(result),
            args.batch_receipt[0], item_id=item["id"],
            task_id=result["queue"].get("task_id"),
            delta_page_receipt_ids=delta_gate_receipts,
        )
        if batch_receipt_errors:
            raise ValueError("invalid batch-review gate: %s" %
                             "; ".join(batch_receipt_errors))
        invalidated = _invalidated_receipt_ids(item)
        attempted = set(args.batch_receipt).union(delta_gate_receipts)
        replayed = sorted(attempted.intersection(invalidated))
        if replayed:
            raise ValueError("open -> merge-ready reuses invalidated receipt(s): %s" %
                             ", ".join(replayed))
        # K12/12: substantive correctness review is mandatory for L-tier
        # pages and MUST be produced by a context other than the author.
        # The obligation existed only as prose until here — nothing counted
        # the receipts, and a batch could reach merge-ready with the review
        # skipped (the distillation-erosion class).  A write-time guard on
        # the transition, not a runtime-wide validation: sealed history
        # closed before this guard shipped is never re-judged by it.
        review_errors = check_queue.substantive_review_errors(
            result, item)
        if review_errors:
            raise ValueError(
                "open -> merge-ready requires the K12/12 substantive "
                "review evidence: %s" % "; ".join(review_errors))
        item["state"] = "merge-ready"
        item["merge_ready_at"] = now
        item["delta_path"] = args.delta_path
        item["delta_sha256"] = kblib.sha256_file(delta)
        item["batch_receipts"] = list(args.batch_receipt)

    elif args.transition == "closed":
        barrier = check_queue.current_attempt_evidence_barrier(
            result, item["id"])
        if barrier:
            raise ValueError(barrier)
        if not _nonempty(args.gate_receipt):
            raise ValueError(
                "merge-ready -> closed requires --gate-receipt for Queue "
                "consistency")
        _receipt(result, args.gate_receipt, "Queue consistency gate", expected={
            "tool": check_queue.TOOL,
            "tool_version": check_queue.TOOL_VERSION,
            "gate_id": "required-queue-consistency",
            "check": "required_queue",
            "queue_check_mode": "consistency",
            "task_id": result["queue"].get("task_id"),
            "queue_revision": result["queue"].get("queue_revision"),
            "queue_state_revision": result["queue"].get("state_revision"),
            "required_queue_sha256": result.get("queue_sha256"),
            "coverage_ledger_sha256": result.get("coverage_sha256"),
            "progress_ledger_sha256": result.get("progress_sha256"),
        })
        if item.get("hold_state") != "none":
            raise ValueError("held batch cannot close")
        if not _nonempty(args.delta_apply_receipt):
            raise ValueError(
                "merge-ready -> closed requires --delta-apply-receipt")
        _receipt(result, args.delta_apply_receipt, "delta application", expected={
            "tool": "apply_delta",
            "tool_version": "1.4.0",
            "check": "delta_apply",
            "target": item["id"],
            "task_id": result["queue"].get("task_id"),
            "batch_id": item["id"],
            "actor_role": "integrator",
            "coverage_ledger_path": check_queue.COVERAGE_PATH,
            "delta_path": item.get("delta_path"),
            "delta_sha256": item.get("delta_sha256"),
            "after_coverage_sha256": result.get("coverage_sha256"),
            "required_queue_sha256": result.get("queue_sha256"),
            "queue_revision": result["queue"].get("queue_revision"),
            "queue_state_revision": result["queue"].get("state_revision"),
        })
        if not _nonempty(args.close_gate_receipt):
            raise ValueError(
                "merge-ready -> closed requires --close-gate-receipt")
        corpus_plan_required, corpus_plan_triggers, corpus_plan_result = \
            _corpus_plan_close_expectation(result, item)
        repository_snapshot_sha256 = kblib.repository_snapshot_sha256(
            result["root"])
        corpus_plan_expected_binding = None
        if corpus_plan_required:
            corpus_plan_expected_binding = check_corpus_plan.receipt_binding(
                corpus_plan_result,
                repository_snapshot_sha256=repository_snapshot_sha256)
        close_gate_errors = check_queue.close_gate_receipt_errors(
            check_queue.current_receipt_catalog(result),
            args.close_gate_receipt,
            item_id=item["id"],
            task_id=result["queue"].get("task_id"),
            queue_revision=result["queue"].get("queue_revision"),
            queue_state_revision=result["queue"].get("state_revision"),
            required_queue_sha256=result.get("queue_sha256"),
            coverage_ledger_sha256=result.get("coverage_sha256"),
            progress_ledger_sha256=result.get("progress_sha256"),
            delta_sha256=item.get("delta_sha256"),
            queue_consistency_receipt=args.gate_receipt,
            delta_apply_receipt=args.delta_apply_receipt,
            work_spec_path=item.get("work_spec_path"),
            work_spec_sha256=item.get("work_spec_sha256"),
            selected_profile_manifest=result["queue"].get(
                "selected_profile_manifest"),
            corpus_plan_required=corpus_plan_required,
            corpus_plan_triggers=corpus_plan_triggers,
            corpus_plan_expected_binding=corpus_plan_expected_binding,
            current_repository_snapshot_sha256=
                repository_snapshot_sha256,
        )
        settlement_errors = check_queue.batch_reference_settlement_errors(
            result, item)
        if settlement_errors:
            raise ValueError(
                "merge-ready -> closed refused by the K13/08 Batch Reference "
                "Settlement: %s" % "; ".join(settlement_errors))
        if close_gate_errors:
            raise ValueError("invalid batch-close gate: %s" %
                             "; ".join(close_gate_errors))
        item["state"] = "closed"
        item["closed_at"] = now
        item["queue_consistency_receipt"] = args.gate_receipt
        item["close_gate_receipt"] = args.close_gate_receipt
        item["delta_apply_receipt"] = args.delta_apply_receipt
        args.close_repository_snapshot_sha256 = \
            repository_snapshot_sha256

    elif args.transition == "open" and before == "merge-ready":
        if not _nonempty(args.reason):
            raise ValueError("merge-ready -> open requires --reason")
        previous = list(item.get("batch_receipts") or [])
        delta_gate_receipts = _current_delta_gate_receipts(item, result)
        revalidation_receipts = _current_attempt_revalidation_receipts(
            item, result)
        source_delta = item.get("delta_path")
        expected_source = ".cambium/deltas/%s.yaml" % item["id"]
        if source_delta != expected_source:
            raise ValueError("merge-ready batch has no canonical delta to invalidate")
        # A rollback taken after the delta was applied must additionally undo
        # the Coverage write.  Binding it to the exact unconsumed application
        # keeps the tool from deciding which apply is being undone -- the
        # integrator names it, the tool only verifies the evidence is present
        # and matches.
        pending = result.get("pending_delta_applies") or {}
        pending_current = pending.get("current") or []
        applied_entry = None
        if (pending.get("status") == "close-required" and
                len(pending_current) == 1 and
                pending_current[0].get("batch") == item["id"]):
            applied_entry = pending_current[0]
        applied_receipt_id = None
        coverage_restore = None
        if applied_entry is not None:
            applied_receipt_id = applied_entry.get("selected_receipt")
            if not _nonempty(args.delta_apply_receipt):
                raise ValueError(
                    "batch %s has an unconsumed delta application; rolling it "
                    "back requires --delta-apply-receipt %s" %
                    (item["id"], applied_receipt_id))
            if args.delta_apply_receipt != applied_receipt_id:
                raise ValueError(
                    "--delta-apply-receipt %s does not name the unconsumed "
                    "delta application %s being rolled back" %
                    (args.delta_apply_receipt, applied_receipt_id))
            apply_receipt = _receipt(
                result, args.delta_apply_receipt, "delta application",
                expected={
                    "tool": apply_delta.TOOL,
                    "check": "delta_apply",
                    "target": item["id"],
                    "batch_id": item["id"],
                    "task_id": result["queue"].get("task_id"),
                    "actor_role": "integrator",
                    "coverage_ledger_path": check_queue.COVERAGE_PATH,
                    "delta_path": source_delta,
                    "delta_sha256": item.get("delta_sha256"),
                    "after_coverage_sha256": result.get("coverage_sha256"),
                },
            )
            coverage_restore = _pre_apply_coverage_restore(
                result, apply_receipt)
            args.coverage_restore = coverage_restore
        elif _nonempty(args.delta_apply_receipt):
            raise ValueError(
                "--delta-apply-receipt is valid only when rolling back a "
                "batch whose delta was applied")
        archive_delta = (
            ".cambium/receipts/invalidated-deltas/%s-r%d.yaml" %
            (item["id"], result["queue"].get("state_revision", 0) + 1)
        )
        args.delta_archive_move = (source_delta, archive_delta)
        history = item.get("invalidation_history")
        if history is None:
            history = []
        if not isinstance(history, list):
            raise ValueError("invalidation_history must be an explicit list")
        invalidation_record = {
            "transition_receipt": None,
            "invalidated_at": now,
            "reason": args.reason,
            "delta_archive_path": archive_delta,
            "delta_sha256": item.get("delta_sha256"),
            "batch_receipts": previous,
            "delta_gate_receipts": delta_gate_receipts,
            "revalidation_receipts": revalidation_receipts,
        }
        if coverage_restore is not None:
            invalidation_record.update({
                "delta_apply_receipt": applied_receipt_id,
                "coverage_restored_from": coverage_restore[0],
                "coverage_restored_sha256": coverage_restore[2],
            })
        item["invalidation_history"] = history + [invalidation_record]
        item["state"] = "open"
        item["hold_state"] = "revalidation-required"
        item["hold_reason"] = args.reason
        for key in ("merge_ready_at", "delta_path", "delta_sha256",
                    "batch_receipts", "delta_apply_receipt"):
            item.pop(key, None)

    if args.hold_state is not None and args.transition not in ("open",):
        if args.hold_state not in check_queue.HOLDS:
            raise ValueError("invalid hold state %s" % args.hold_state)
        if args.hold_state == item.get("hold_state"):
            raise ValueError("hold transition is a no-op")
        # The obligation, not the edge.  Guarding only the adjacent
        # `revalidation-required -> none` edge left
        # `revalidation-required -> paused -> none` open: two writes each
        # legal on their own cleared a hold neither one discharged.  The
        # predicate is the item's own transition history, so it holds for a
        # return to `none` through any number of intermediate holds.
        if (args.hold_state == "none" and
                check_queue.item_undischarged_revalidation_hold(
                    item, result.get("receipt_catalog") or {})):
            outstanding = check_queue.outstanding_standards_revalidation(
                result, item["id"])
            if outstanding:
                require_standards_revalidation()
            else:
                if not _nonempty(args.gate_receipt):
                    raise ValueError(
                        "clearing revalidation-required needs --gate-receipt")
                _receipt(result, args.gate_receipt, "revalidation gate", expected={
                    "tool": check_queue.TOOL,
                    "tool_version": check_queue.TOOL_VERSION,
                    "gate_id": "required-queue-consistency",
                    "check": "required_queue",
                    "queue_check_mode": "consistency",
                    "task_id": result["queue"].get("task_id"),
                    "queue_revision": result["queue"].get("queue_revision"),
                    "queue_state_revision": result["queue"].get("state_revision"),
                    "required_queue_sha256": result.get("queue_sha256"),
                    "coverage_ledger_sha256": result.get("coverage_sha256"),
                    "progress_ledger_sha256": result.get("progress_sha256"),
                })
                if args.gate_receipt in _invalidated_receipt_ids(item):
                    raise ValueError(
                        "revalidation gate reuses invalidated receipt %s" %
                        args.gate_receipt)
        item["hold_state"] = args.hold_state
        if args.hold_state == "none":
            item.pop("hold_reason", None)
        elif not _nonempty(args.reason):
            raise ValueError("non-none hold requires --reason")
        else:
            item["hold_reason"] = args.reason
    return before, item.get("state")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply one Required Queue transition")
    parser.add_argument("root")
    parser.add_argument("--id", required=True)
    parser.add_argument("--transition", choices=("open", "merge-ready", "closed"))
    parser.add_argument("--hold-state", choices=tuple(check_queue.HOLDS))
    parser.add_argument("--expected-state-revision", type=int)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker")
    parser.add_argument("--gate-receipt")
    parser.add_argument("--standards-revalidation-receipt")
    parser.add_argument("--close-gate-receipt")
    parser.add_argument("--confirmation-receipt")
    parser.add_argument("--delta-path")
    parser.add_argument("--delta-apply-receipt")
    parser.add_argument("--batch-receipt", action="append", default=[])
    parser.add_argument("--reason")
    parser.add_argument("--at", default=None)
    parser.add_argument("--receipts",
                        default=".cambium/receipts/queue-transitions.jsonl")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.at is None:
        args.at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not check_queue._valid_timestamp(args.at):
        print("[FAIL] --at must be a timezone-aware RFC 3339 timestamp")
        return 1
    if args.transition == "cancelled":
        print("[FAIL] direct cancellation is disabled; use apply_amendment.py "
              "so Coverage, Queue, and Progress change in one transaction")
        return 1

    allowed_delta = args.delta_path if args.transition == "merge-ready" else None
    result = check_queue.validate_runtime(
        args.root, allowed_open_delta=allowed_delta,
        allow_standards_rollback_batch=(
            args.id if args.transition == "open" else None),
    )
    if result["errors"]:
        for error in result["errors"]:
            print("[FAIL] current runtime state: %s" % error)
        return 1
    item = result.get("items_by_id", {}).get(args.id)
    if item is None:
        print("[FAIL] unknown Queue id %s" % args.id)
        return 1
    if args.standards_revalidation_receipt:
        consumes_revalidation = (
            (args.transition == "open" and item.get("state") == "queued") or
            (args.transition is None and args.hold_state == "none" and
             item.get("hold_state") == "revalidation-required")
        )
        if not consumes_revalidation:
            print("[FAIL] --standards-revalidation-receipt is valid only for "
                  "queued -> open or revalidation-required -> none")
            return 1
    if args.apply:
        barrier = check_queue.delta_apply_write_barrier(
            result, "update_queue", args.transition or "hold", args.id)
        if barrier:
            print("[FAIL] %s" % barrier)
            return 1
    opening_first_batch = (
        args.transition == "open" and item.get("state") == "queued"
    )
    pending_applies = result.get("pending_delta_applies") or {}
    current_applies = pending_applies.get("current") or []
    closing_applied_batch = (
        args.transition == "closed" and
        pending_applies.get("status") == "close-required" and
        len(current_applies) == 1 and
        current_applies[0].get("batch") == args.id
    )
    task_state = result.get("progress", {}).get("task_state")
    task_allows_write = (
        task_state == "active" or
        (task_state == "planned" and opening_first_batch) or
        closing_applied_batch
    )
    if not task_allows_write:
        print("[FAIL] task_state=%s forbids Queue lifecycle/hold writes; use "
              "update_task.py to enter active first" % task_state)
        return 1

    root = os.path.realpath(os.path.abspath(args.root))
    try:
        coverage_path = kblib.managed_repository_path(
            root, check_queue.COVERAGE_PATH, ".cambium/state",
            suffixes=(".yaml",), must_exist=True,
        )
        with open(coverage_path, encoding="utf-8") as fh:
            before_coverage_text = fh.read()
    except (OSError, ValueError) as exc:
        print("[FAIL] cannot read Coverage bytes: %s" % exc)
        return 1
    before_coverage_sha = kblib.sha256_bytes(before_coverage_text)
    queue_new = copy.deepcopy(result["queue"])
    target = next(entry for entry in queue_new["required_queue"]
                  if entry.get("id") == args.id)
    transition_context = dict(result)
    transition_context["root"] = root
    transition_context["coverage_text"] = before_coverage_text
    try:
        before_state, after_state = _transition_item(
            target, args, transition_context
        )
    except ValueError as exc:
        print("[FAIL] %s" % exc)
        return 1

    coverage_restore = getattr(args, "coverage_restore", None)
    write_coverage = args.transition == "closed" or coverage_restore is not None
    try:
        if args.transition == "closed":
            coverage_new = _project_closed_coverage(
                result["coverage"], queue_new, args.id)
            coverage_text = kblib.canonical_yaml(coverage_new)
        elif coverage_restore is not None:
            # Byte-exact restore, not a re-projection: the archived bytes are
            # the only representation of the pre-apply Coverage that is
            # provably what the delta was applied on top of.
            coverage_text = coverage_restore[1]
            coverage_new = copy.deepcopy(coverage_restore[3])
        else:
            coverage_new = copy.deepcopy(result["coverage"])
            coverage_text = before_coverage_text
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot project Coverage close route: %s" % exc)
        return 1
    if args.actor_role != "integrator":
        print("[FAIL] Queue transition planning and apply require "
              "actor-role integrator")
        return 1

    before_revision = result["queue"].get("state_revision")
    before_sha = result["queue_sha256"]
    queue_new["state_revision"] = before_revision + 1
    receipt = kblib.make_queue_receipt(
        "queue_transition", args.id, "pass",
        "%s -> %s; hold=%s" %
        (before_state, after_state, target.get("hold_state")),
        task_id=result["queue"].get("task_id"),
        before_state=before_state, after_state=after_state,
        before_hold_state=item.get("hold_state"),
        after_hold_state=target.get("hold_state"),
        before_state_revision=before_revision,
        after_state_revision=queue_new["state_revision"],
        before_required_queue_sha256=before_sha,
        before_coverage_sha256=before_coverage_sha,
        evidence_receipt=(
            args.close_gate_receipt if args.transition == "closed" else
            args.batch_receipt[0] if args.transition == "merge-ready" else
            (args.standards_revalidation_receipt or args.gate_receipt or
             args.confirmation_receipt)
        ),
        actor_role=args.actor_role,
    )
    receipt["checked_at"] = args.at
    if args.standards_revalidation_receipt:
        receipt["standards_revalidation_receipt"] = \
            args.standards_revalidation_receipt
    if before_state == "merge-ready" and after_state == "open":
        invalidation = target["invalidation_history"][-1]
        invalidation["transition_receipt"] = receipt["receipt_id"]
        receipt["invalidation"] = copy.deepcopy(invalidation)
    if args.transition == "closed":
        receipt["delta_apply_receipt"] = args.delta_apply_receipt
        receipt["queue_consistency_receipt"] = args.gate_receipt
        receipt["close_gate_receipt"] = args.close_gate_receipt
    history = target.get("transition_receipts")
    if history is None:
        history = []
    if not isinstance(history, list):
        print("[FAIL] transition_receipts must be a list")
        return 1
    target["transition_receipts"] = history + [receipt["receipt_id"]]
    try:
        queue_text = kblib.canonical_yaml(queue_new)
        after_sha = kblib.sha256_bytes(queue_text)
        after_coverage_sha = kblib.sha256_bytes(coverage_text)
        task_receipt = None
        if opening_first_batch and task_state == "planned":
            task_context = dict(result)
            task_context["root"] = root
            progress_new, progress_text, task_receipt = (
                update_task.build_task_transition(
                    task_context, "active", args.at,
                    "first Required Queue batch %s opened" % args.id,
                    args.gate_receipt, queue=queue_new,
                    queue_text=queue_text,
                    first_open_batch_id=args.id,
                )
            )
        else:
            progress_new = _sync_progress(
                result["progress"], queue_new, queue_text)
            progress_text = kblib.canonical_yaml(progress_new)
        before_progress_sha = result.get("progress_sha256")
        after_progress_sha = kblib.sha256_bytes(progress_text)
        receipt["after_required_queue_sha256"] = after_sha
        receipt["after_coverage_sha256"] = after_coverage_sha
        receipt["before_progress_sha256"] = before_progress_sha
        receipt["after_progress_sha256"] = after_progress_sha
        receipt["queue_revision"] = queue_new["queue_revision"]
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False,
        )
        task_receipt_path = (kblib.managed_repository_path(
            root, update_task.RECEIPT_PATH, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False,
        ) if task_receipt is not None else None)
    except (OSError, TypeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot prepare transition: %s" % exc)
        return 1

    delta_move = getattr(args, "delta_archive_move", None)
    if not delta_move:
        proposed = check_queue.validate_runtime(
            root,
            state_overrides={
                check_queue.COVERAGE_PATH: (coverage_text, coverage_new),
                check_queue.QUEUE_PATH: (queue_text, queue_new),
                check_queue.PROGRESS_PATH: (progress_text, progress_new),
            },
            extra_receipts=([receipt, task_receipt]
                            if task_receipt is not None else [receipt]),
        )
        if proposed["errors"]:
            for error in proposed["errors"]:
                print("[FAIL] proposed runtime state: %s" % error)
            return 1

    print("transition plan: %s %s -> %s; state_revision %d -> %d" %
          (args.id, before_state, after_state, before_revision,
           queue_new["state_revision"]))
    if not args.apply:
        print("dry run; add --apply --actor-role integrator with expected revision/hash")
        return 0
    if args.expected_state_revision is None or args.expected_sha256 is None:
        print("[FAIL] --apply requires --expected-state-revision and --expected-sha256")
        return 1
    if args.expected_state_revision != before_revision:
        print("[FAIL] expected state revision does not match current Queue")
        return 1
    if args.expected_sha256 != before_sha:
        print("[FAIL] expected fingerprint does not match current Queue bytes")
        return 1

    try:
        lock_operation = {
            "tool": "update_queue",
            "action": ("transition:%s" % args.transition
                       if args.transition else
                       "hold:%s" % args.hold_state),
            "target": args.id,
            "task_id": result["queue"].get("task_id"),
            "before_queue_revision": result["queue"].get("queue_revision"),
            "before_state_revision": before_revision,
            "before_required_queue_sha256": before_sha,
            "before_coverage_sha256": before_coverage_sha,
            "before_progress_sha256": before_progress_sha,
            "planned_after_queue_revision": queue_new.get("queue_revision"),
            "planned_after_state_revision": queue_new.get("state_revision"),
            "planned_after_required_queue_sha256": after_sha,
            "planned_after_coverage_sha256": after_coverage_sha,
            "planned_after_progress_sha256": after_progress_sha,
            "receipt_id": receipt.get("receipt_id"),
            "receipt_path": args.receipts,
        }
        if delta_move:
            lock_operation.update({
                "delta_archive_source": delta_move[0],
                "delta_archive_path": delta_move[1],
                "delta_sha256": receipt["invalidation"]["delta_sha256"],
            })
        if task_receipt is not None:
            lock_operation["task_transition_receipt_id"] = task_receipt[
                "receipt_id"]
            lock_operation["task_transition_receipt_path"] = (
                update_task.RECEIPT_PATH)
        with kblib.runtime_write_lock(root, owner_metadata=lock_operation) as lock:
            with kblib.no_authoritative_write_guard(lock):
                queue_path = result["queue_path"]
                progress_path = kblib.managed_repository_path(
                    root, check_queue.PROGRESS_PATH, ".cambium/state",
                    suffixes=(".yaml",), must_exist=True,
                )
                with open(queue_path, encoding="utf-8") as fh:
                    old_queue_text = fh.read()
                with open(coverage_path, encoding="utf-8") as fh:
                    old_coverage_text = fh.read()
                with open(progress_path, encoding="utf-8") as fh:
                    old_progress_text = fh.read()
                receipt_observations = {}
                receipt_batches = {}
                for candidate, records in (
                        (task_receipt_path,
                         [task_receipt] if task_receipt is not None else []),
                        (receipt_path, [receipt])):
                    if candidate is None:
                        continue
                    receipt_batches.setdefault(candidate, []).extend(records)
                for candidate, records in receipt_batches.items():
                    receipt_observations[candidate] = (
                        kblib.receipt_append_observation(candidate, records)
                    )
                current = check_queue.validate_runtime(
                    root, allowed_open_delta=allowed_delta,
                    allow_standards_rollback_batch=(
                        args.id if args.transition == "open" else None),
                )
                if current["errors"]:
                    raise ValueError("runtime changed before write: %s" %
                                     "; ".join(current["errors"]))
                barrier = check_queue.delta_apply_write_barrier(
                    current, "update_queue", args.transition or "hold",
                    args.id)
                if barrier:
                    raise ValueError(barrier)
                if (current.get("queue_sha256") != before_sha or
                        current.get("progress_sha256") !=
                        result.get("progress_sha256") or
                        kblib.sha256_bytes(old_coverage_text) !=
                        before_coverage_sha or
                        current.get("coverage") != result.get("coverage")):
                    raise ValueError(
                        "Queue, Coverage, or Progress changed after validation")
                if args.transition == "closed":
                    locked_snapshot = kblib.repository_snapshot_sha256(root)
                    if locked_snapshot != getattr(
                            args, "close_repository_snapshot_sha256", None):
                        raise ValueError(
                            "repository content changed after batch-close gate "
                            "validation"
                        )
                    locked_item = next(
                        entry for entry in current["queue"]["required_queue"]
                        if entry.get("id") == args.id
                    )
                    (locked_corpus_required, locked_corpus_triggers,
                     locked_corpus_result) = \
                        _corpus_plan_close_expectation(current, locked_item)
                    locked_corpus_binding = None
                    if locked_corpus_required:
                        locked_corpus_binding = \
                            check_corpus_plan.receipt_binding(
                                locked_corpus_result,
                                repository_snapshot_sha256=locked_snapshot)
                    locked_close_errors = check_queue.close_gate_receipt_errors(
                        check_queue.current_receipt_catalog(current),
                        args.close_gate_receipt,
                        item_id=args.id,
                        task_id=current["queue"].get("task_id"),
                        queue_revision=current["queue"].get("queue_revision"),
                        queue_state_revision=current["queue"].get(
                            "state_revision"),
                        required_queue_sha256=current.get("queue_sha256"),
                        coverage_ledger_sha256=current.get("coverage_sha256"),
                        progress_ledger_sha256=current.get("progress_sha256"),
                        delta_sha256=locked_item.get("delta_sha256"),
                        queue_consistency_receipt=args.gate_receipt,
                        delta_apply_receipt=args.delta_apply_receipt,
                        work_spec_path=locked_item.get("work_spec_path"),
                        work_spec_sha256=locked_item.get(
                            "work_spec_sha256"),
                        selected_profile_manifest=current["queue"].get(
                            "selected_profile_manifest"),
                        corpus_plan_required=locked_corpus_required,
                        corpus_plan_triggers=locked_corpus_triggers,
                        corpus_plan_expected_binding=locked_corpus_binding,
                        current_repository_snapshot_sha256=locked_snapshot,
                    )
                    if locked_close_errors:
                        raise ValueError(
                            "batch-close gate changed before write: %s" %
                            "; ".join(locked_close_errors)
                        )
                if args.transition == "closed":
                    locked_projection = _project_closed_coverage(
                        current["coverage"], queue_new, args.id
                    )
                    if (locked_projection != coverage_new or
                            kblib.canonical_yaml(locked_projection) !=
                            coverage_text):
                        raise ValueError(
                            "Coverage close projection changed under lock")
                elif coverage_restore is not None:
                    locked_restore = _pre_apply_coverage_restore(
                        dict(current, root=root),
                        _receipt(current, args.delta_apply_receipt,
                                 "delta application"),
                    )
                    if (locked_restore[1] != coverage_text or
                            locked_restore[2] != coverage_restore[2]):
                        raise ValueError(
                            "pre-apply Coverage archive changed under lock")

            moved_delta = None
            attempted_receipts = []
            try:
                if delta_move:
                    source_delta = kblib.managed_repository_path(
                        root, delta_move[0], ".cambium/deltas",
                        suffixes=(".yaml",), must_exist=True,
                    )
                    archive_delta = kblib.managed_repository_path(
                        root, delta_move[1], ".cambium/receipts",
                        suffixes=(".yaml",), must_exist=False,
                    )
                    if os.path.lexists(archive_delta):
                        raise FileExistsError(
                            "invalidated delta archive already exists")
                    os.makedirs(os.path.dirname(archive_delta), exist_ok=True)
                    moved_delta = (source_delta, archive_delta)
                    kblib.durable_replace(source_delta, archive_delta)
                    proposed = check_queue.validate_runtime(
                        root,
                        state_overrides={
                            check_queue.COVERAGE_PATH:
                                (coverage_text, coverage_new),
                            check_queue.QUEUE_PATH: (queue_text, queue_new),
                            check_queue.PROGRESS_PATH:
                                (progress_text, progress_new),
                        },
                        extra_receipts=([receipt, task_receipt]
                                        if task_receipt is not None
                                        else [receipt]),
                    )
                    if proposed["errors"]:
                        raise ValueError("proposed runtime state: %s" %
                                         "; ".join(proposed["errors"]))
                _write_state(
                    coverage_path, coverage_text,
                    queue_path, queue_text,
                    progress_path, progress_text,
                    old_coverage_text, old_queue_text, old_progress_text,
                    write_coverage=write_coverage,
                )
                if args.transition == "closed":
                    after_write_snapshot = \
                        kblib.repository_snapshot_sha256(root)
                    if after_write_snapshot != getattr(
                            args, "close_repository_snapshot_sha256", None):
                        raise ValueError(
                            "repository content changed while closing batch"
                        )
                if task_receipt is not None:
                    attempted_receipts.append(task_receipt_path)
                    kblib.write_receipts(task_receipt_path, [task_receipt])
                attempted_receipts.append(receipt_path)
                kblib.write_receipts(receipt_path, [receipt])
            except Exception as write_error:
                rollback_failures = []
                try:
                    _write_state(
                        coverage_path, old_coverage_text,
                        queue_path, old_queue_text,
                        progress_path, old_progress_text,
                        coverage_text, queue_text, progress_text,
                        write_coverage=write_coverage,
                    )
                except Exception as exc:
                    rollback_failures.append("state: %s" % exc)
                if moved_delta and os.path.exists(moved_delta[1]):
                    try:
                        kblib.durable_replace(moved_delta[1], moved_delta[0])
                    except OSError as exc:
                        rollback_failures.append("delta archive: %s" % exc)
                receipt_outcomes = {}
                for path in attempted_receipts:
                    if path in receipt_outcomes:
                        continue
                    try:
                        after_observation = kblib.receipt_append_observation(
                            path, receipt_batches[path]
                        )
                        receipt_outcomes[path] = kblib.receipt_append_outcome(
                            receipt_observations[path], after_observation
                        )
                    except Exception as exc:
                        receipt_outcomes[path] = "uncertain"
                        rollback_failures.append(
                            "receipt inspection %s: %s" %
                            (os.path.relpath(path, root), exc))
                unresolved_receipts = [
                    "%s=%s" % (os.path.relpath(path, root), outcome)
                    for path, outcome in receipt_outcomes.items()
                    if outcome != "absent"
                ]
                if unresolved_receipts:
                    rollback_failures.append(
                        "append-only receipt publication requires recovery: %s" %
                        ", ".join(unresolved_receipts)
                    )
                expected_state = {
                    coverage_path: before_coverage_sha,
                    queue_path: before_sha,
                    progress_path: before_progress_sha,
                }
                for path, expected_sha in expected_state.items():
                    try:
                        if kblib.sha256_file(path) != expected_sha:
                            rollback_failures.append(
                                "%s fingerprint not restored" %
                                os.path.relpath(path, root))
                    except OSError as exc:
                        rollback_failures.append(
                            "%s verification: %s" %
                            (os.path.relpath(path, root), exc))
                if moved_delta:
                    if (not os.path.isfile(moved_delta[0]) or
                            os.path.lexists(moved_delta[1])):
                        rollback_failures.append("delta archive move not restored")
                if rollback_failures:
                    raise ValueError(
                        "transition failed and rollback is incomplete: %s; %s" %
                        (write_error, "; ".join(rollback_failures)))
                lock.mark_reconciled()
                raise
    except (OSError, ValueError, kblib.YamlSubsetError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] transition write failed; restoration attempted: %s" % exc)
        return 1
    print("[PASS] transition applied; state_revision=%d sha256=%s" %
          (queue_new["state_revision"], after_sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
