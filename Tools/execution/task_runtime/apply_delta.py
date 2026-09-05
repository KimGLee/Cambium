#!/usr/bin/env python3
"""Deterministically apply one canonical batch Coverage Delta.

The adopting repository root and one canonical Delta path are the complete
input boundary.  The Coverage path is derived from the runtime contract;
callers cannot substitute an alternate ledger.  Every run binds paths and Queue
state, and every write uses the shared runtime lock, optimistic fingerprints,
atomic publication, and post-write read-back before a receipt is published.

Unlike the neighbouring tools, a canonical apply publishes its receipt into a
*new* file rather than appending to a shared JSONL, so that an interrupted
apply cannot be confused with a completed one.  Omitting ``--receipts`` names
``.cambium/receipts/<receipt_id>.jsonl`` automatically; an explicit
``--receipts`` path that already exists is refused.
"""

import copy
import os
import sys

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.canon as queue_canon
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.task_runtime.batch_settlement as batch_settlement
import Tools.execution.planning.coverage_delta as coverage_delta
import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.knowledge.metadata.metadata_page_state_contract as metadata_page_state_contract
import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.knowledge.metadata.project_page_state as project_page_state
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.common import reporting

TOOL = queue_canon.APPLY_DELTA_TOOL
TOOL_VERSION = queue_canon.APPLY_DELTA_TOOL_VERSION
RECEIPT_TYPE_ID = "delta-application-receipt-v1"


def current_receipt_errors(record, *, root=None):
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks="delta_apply")


JSON_HELP = reporting.JSON_RECEIPT_HELP
_JSON_REPORTER = reporting.JsonReceiptCollector()


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


def _canonical_delta_path(args, batch):
    expected_delta = runtime_paths.child_path(
        runtime_paths.DELTA_ROOT, "%s.yaml" % batch)
    errors = []
    if args.delta != expected_delta:
        errors.append("canonical delta argument must be exactly %s" %
                      expected_delta)
    return expected_delta, errors


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
    return runtime_paths.child_path(
        runtime_paths.PRE_APPLY_COVERAGE_RECEIPT_ROOT,
        "%s-r%d.yaml" % (batch, int(queue_state_revision or 0)))


def _prepare_receipt(result, batch, delta_path, delta_sha,
                     before_coverage_sha, after_coverage_sha, actor_role,
                     before_coverage_archive, settlement=None):
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "delta_apply", batch, "pass",
        "canonical Coverage delta applied and Queue post-check passed", 1,
        receipt_type_id=RECEIPT_TYPE_ID,
    )
    receipt.update({
        "task_id": result["queue"].get("task_id"),
        "batch_id": batch,
        "actor_role": actor_role,
        "coverage_ledger_path": queue_runtime.COVERAGE_PATH,
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
    expected_delta, path_errors = _canonical_delta_path(args, batch)
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
            root, queue_runtime.COVERAGE_PATH, runtime_paths.STATE_ROOT,
            suffixes=(".yaml",), must_exist=True,
        )
        delta_path = kblib.managed_repository_path(
            root, args.delta, runtime_paths.DELTA_ROOT,
            suffixes=(".yaml",), must_exist=True,
        )
        if not os.path.isfile(ledger_path) or not os.path.isfile(delta_path):
            raise ValueError("canonical ledger and delta must be regular files")
        current = runtime_validation.validate_runtime(
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
        authority = queue_runtime.runtime_authority_context(current)
        authority_kwargs = \
            queue_runtime.runtime_authority_validation_kwargs(authority)
    except (TypeError, ValueError) as exc:
        print("[FAIL] current runtime authority: %s" % exc)
        return 1
    if args.apply:
        barrier = queue_runtime.delta_apply_write_barrier(
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
    allowed_states = (runtime_state_contract.QUEUE_ACTIVE_STATES
                      if args.preflight
                      else frozenset(("merge-ready",)))
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
        opening_context = queue_runtime.current_opening_semantic_context(
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
            queue_runtime.runtime_metadata_execution_contract(current)
        profile_contract = current["_profile_authorized_view"]["_contract"]
        projection_rules = \
            metadata_property_state.profile_gate_projection_rules(
                root, profile_contract.extension_gates,
                metadata_contract=metadata_contract,
                typed_profile_contract=profile_contract)
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
                metadata_page_state_contract.rules_fingerprint(
                    projection_rules),
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
    receipt_relative = args.receipts or runtime_paths.child_path(
        runtime_paths.RECEIPT_ROOT,
        "%s.jsonl" % receipt["receipt_id"])
    try:
        receipt_path = kblib.managed_repository_path(
            root, receipt_relative, runtime_paths.RECEIPT_ROOT,
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
              "run name %s/<receipt_id>.jsonl itself, or pass a path that "
              "does not exist yet." % runtime_paths.RECEIPT_ROOT)
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
        "before_queue_sha256": before_queue_sha,
        "planned_after_queue_sha256": before_queue_sha,
        "before_progress_sha256": before_progress_sha,
        "planned_after_progress_sha256": before_progress_sha,
        "delta_sha256": planned_delta_sha,
        "receipt_id": receipt["receipt_id"],
        "receipt_path": receipt_relative,
        "opening_transition_receipt": opening_context[
            "opening_transition_receipt"],
        "manifest_semantic_before_set_sha256": opening_context[
            "manifest_semantic_before_set_sha256"],
    }
    lock_operation.update(queue_runtime.runtime_authority_lock_fields(authority))
    try:
        with kblib.runtime_write_lock(root, owner_metadata=lock_operation) as lock:
            page_plan = None
            with kblib.no_authoritative_write_guard(lock):
                # Re-read under the lock.  Queue validation sees our own lock
                # but does not treat it as a state error; fingerprints provide
                # CAS.  Any rejection in this region is a proven no-write
                # outcome and must not manufacture an interrupted-write lock.
                locked = runtime_validation.validate_runtime(
                    root, **authority_kwargs)
                if locked["errors"]:
                    raise ValueError("runtime changed before write: %s" %
                                     "; ".join(locked["errors"]))
                queue_runtime.require_runtime_authority_current(
                    root, authority, "runtime authority changed under lock")
                barrier = queue_runtime.delta_apply_write_barrier(
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
                    queue_runtime.current_opening_semantic_context(
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
                owner_removals = {}
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
                # Delta application changes the complete manifest's current
                # Coverage owner state, not only evidence-backed property
                # rows. Reconcile every manifest page in this same guarded
                # transaction so authoring_status and the other ledger-owned
                # projections cannot lag behind their new owner values.
                page_plan = metadata_property_state.build_projection_plan(
                    root, locked_coverage, delta_manifest,
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

                old_text = kblib.read_text(ledger_path)
                archive_path = kblib.managed_repository_path(
                    root, archive_relative, runtime_paths.RECEIPT_ROOT,
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
                    queue_runtime.require_runtime_authority_current(
                        root, authority,
                        "runtime authority changed before Coverage archive")
                    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
                    kblib.atomic_write_text(
                        archive_path, old_text,
                        validator=kblib.parse_yaml_subset,
                    )
                    wrote_archive = True
                    queue_runtime.require_runtime_authority_current(
                        root, authority,
                        "runtime authority changed during Coverage archive")
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before Coverage write")
                kblib.atomic_write_text(
                    ledger_path, new_text, validator=kblib.parse_yaml_subset
                )
                wrote_coverage = True
                if page_transaction is not None:
                    page_transaction.publish()
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during Coverage write")
                post = runtime_validation.validate_runtime(
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
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before delta receipt")
                receipt_attempted = True
                kblib.write_receipts(
                    receipt_path, _JSON_REPORTER.record([receipt]),
                    exclusive=True
                )
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during delta receipt")
                persisted = runtime_validation.validate_runtime(
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


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Deterministic Coverage Delta application"
    )
    parser.add_argument("delta",
                        help="canonical batch Coverage delta; must be exactly "
                             "%s/<batch>.yaml" %
                        runtime_paths.DELTA_ROOT)
    parser.add_argument("--root", required=True,
                        help="adopting repository root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="write the merged Coverage; omit for a dry run")
    mode.add_argument(
        "--preflight", action="store_true",
        help="plan canonical Coverage and routed-gap settlement without writes; "
             "allows an open batch")
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
                             "defaults to a new %s/"
                             "<receipt_id>.jsonl and refuses an existing path" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _JSON_REPORTER.run(lambda: _run(args))


def _run(args):
    """This tool's own run; `main` above owns only argument parsing."""
    try:
        root = os.path.realpath(os.path.abspath(args.root))
        delta_file = kblib.repository_path(
            root, args.delta, must_exist=True, reject_symlink=True)
        ledger_file = kblib.repository_path(
            root, queue_runtime.COVERAGE_PATH, must_exist=True,
            reject_symlink=True)
        delta_raw = kblib.read_bytes(delta_file)
        delta = _parse_delta_bytes(delta_raw)
        ledger_raw = kblib.read_bytes(ledger_file)
        ledger_text = ledger_raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] cannot load Coverage delta inputs: %s" % exc)
        return 1

    policy_errors = coverage_delta.delta_policy_errors(delta)
    batch = delta.get("batch")
    if not isinstance(batch, str) or not queue_runtime.BATCH_ID_RE.fullmatch(batch):
        policy_errors.append("delta batch must be a path-safe Required Queue id")
    if policy_errors:
        for error in policy_errors:
            print("[FAIL] %s" % error)
        print("apply_delta: entire operation rejected; no files were written")
        return 1

    new_text, planned, rejected, unknown_keys = \
        coverage_delta.plan_page_updates(ledger_text, delta)
    try:
        new_text = coverage_delta.project_coverage_text(new_text, delta)
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        print("[FAIL] Coverage gap reconciliation failed: %s" % exc)
        return 1
    _print_plan(delta, planned, rejected, unknown_keys)
    return _canonical_apply(
        args, delta, new_text, planned, rejected,
        kblib.sha256_bytes(ledger_raw), kblib.sha256_bytes(delta_raw),
    )


if __name__ == "__main__":
    sys.exit(main())
