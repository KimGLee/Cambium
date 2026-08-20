#!/usr/bin/env python3
"""Consume one typed Profile Gate receipt as a canonical metadata transition.

Only the Integrator may run ``--apply``.  The tool resolves the Gate from the
single current Profile contract, validates a current-catalog producer receipt,
updates Coverage's generic ``property_state`` owner record, and projects the
same value onto the page through ``project_page_state``'s composite
transaction API.  Profile, K00, metadata-contract, page and Coverage inputs
are compare-and-swapped under the shared runtime writer lock; a pre-commit
failure restores both Coverage and the exact page before-image.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib
import metadata_gate_runtime
import metadata_property_state
import project_page_state


TOOL = "apply_metadata_transition"
TOOL_VERSION = "1.0.0"
CHECK = "metadata-transition"


def _page_after_sha(plan, page_path):
    matches = [page for page in plan.pages if page.relative == page_path]
    if len(matches) != 1:
        raise ValueError("projection plan does not bind exactly one target page")
    page = matches[0]
    return (kblib.sha256_bytes(page.after_data)
            if page.after_data is not None else page.snapshot.sha256)


def _page_after_data(plan, page_path):
    matches = [page for page in plan.pages if page.relative == page_path]
    if len(matches) != 1:
        raise ValueError("projection plan does not bind exactly one target page")
    page = matches[0]
    return (page.after_data if page.after_data is not None
            else page.snapshot.data)


def prepare_transition(context, gate_receipt_id, requested_value,
                       actor_role="integrator", seq=1):
    """Return proposed Coverage, projection plan and Integrator receipt."""
    if actor_role != "integrator":
        raise ValueError("only actor-role integrator may apply metadata state")
    gate_receipt = metadata_gate_runtime.current_gate_receipt(
        context, gate_receipt_id, requested_value)
    proposed = metadata_property_state.apply_gate_transition(
        context.runtime["coverage"], context.page_path,
        context.gate.field_id, requested_value, gate_receipt_id,
        context.semantic_content_fingerprint,
        context.gate.completion_values)
    coverage_text = kblib.canonical_yaml(proposed)
    # Prove that the proposed owner state is both parseable and sufficient to
    # build the exact page after-image before taking the writer lock.
    parsed = kblib.parse_yaml_subset(coverage_text)
    if parsed != proposed:
        raise ValueError("canonical Coverage serialization changed owner state")
    plan = metadata_property_state.build_projection_plan(
        context.root, proposed, [context.page_path], rules=context.rules)
    after_coverage_sha = kblib.sha256_bytes(coverage_text)
    after_page_sha = _page_after_sha(plan, context.page_path)
    before_repository_sha = (
        context.repository_snapshot_sha256 or
        kblib.repository_snapshot_sha256(context.root))
    after_repository_sha = kblib.repository_snapshot_sha256(
        context.root,
        byte_overrides={
            context.page_path: _page_after_data(plan, context.page_path),
        })
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, CHECK, context.page_path, "pass",
        "typed Profile Extension Gate transition applied", seq,
        root=context.root)
    bindings = metadata_gate_runtime.receipt_bindings(
        context, requested_value)
    receipt.update({
        "gate_id": bindings["gate_id"],
        "transition_id": bindings["transition_id"],
        "judgment_item_id": bindings["judgment_item_id"],
        "property_field": bindings["property_field"],
        "requested_completion_value":
            bindings["requested_completion_value"],
        "pass_authority_role_id": bindings["pass_authority_role_id"],
        "actor_role": actor_role,
        "producer_kind": bindings["producer_kind"],
        "producer_capability": bindings["producer_capability"],
        "producer_reference": bindings["producer_reference"],
        "receipt_schema": bindings["receipt_schema"],
        "consumer_capability": bindings["consumer_capability"],
        "gate_receipt": gate_receipt_id,
        "gate_receipt_checked_at": gate_receipt.get("checked_at"),
        "semantic_content_fingerprint":
            bindings["semantic_content_fingerprint"],
        "selected_profile_manifest":
            bindings["selected_profile_manifest"],
        "selected_profile_manifest_sha256":
            bindings["selected_profile_manifest_sha256"],
        "profile_snapshot_sha256": bindings["profile_snapshot_sha256"],
        "profile_contract_fingerprint":
            bindings["profile_contract_fingerprint"],
        "profile_load_inputs_sha256":
            bindings["profile_load_inputs_sha256"],
        "active_standards_sha256": bindings["active_standards_sha256"],
        "metadata_execution_contract_fingerprint":
            bindings["metadata_execution_contract_fingerprint"],
        "before_coverage_sha256": context.runtime.get("coverage_sha256"),
        "after_coverage_sha256": after_coverage_sha,
        "before_required_queue_sha256": context.runtime.get("queue_sha256"),
        "after_required_queue_sha256": context.runtime.get("queue_sha256"),
        "before_progress_sha256": context.runtime.get("progress_sha256"),
        "after_progress_sha256": context.runtime.get("progress_sha256"),
        "before_page_sha256": context.page_snapshot.sha256,
        "after_page_sha256": after_page_sha,
        "before_repository_snapshot_sha256": before_repository_sha,
        "after_repository_snapshot_sha256": after_repository_sha,
    })
    return proposed, coverage_text, plan, receipt


def _current_receipt_from(runtime, context, receipt_id, value, *,
                          require_current_repository=True):
    copied = metadata_gate_runtime.GateRuntimeContext(
        root=context.root, runtime=runtime, authority=context.authority,
        gate=context.gate, rules=context.rules, page_path=context.page_path,
        page_snapshot=context.page_snapshot,
        semantic_content_fingerprint=context.semantic_content_fingerprint,
        selected_profile_manifest_sha256=(
            context.selected_profile_manifest_sha256),
        metadata_contract_fingerprint=(
            context.metadata_contract_fingerprint),
        repository_snapshot_sha256=context.repository_snapshot_sha256,
    )
    return metadata_gate_runtime.current_gate_receipt(
        copied, receipt_id, value,
        require_current_repository=require_current_repository)


def _post_state_errors(root, context, receipt, expected_coverage_sha,
                       expected_page_sha, expected_repository_sha,
                       authority_kwargs, transaction):
    errors = []
    post = check_queue.validate_runtime(
        root, extra_receipts=[receipt], **authority_kwargs)
    if post.get("errors"):
        errors.append("runtime: %s" % "; ".join(post["errors"]))
    if post.get("coverage_sha256") != expected_coverage_sha:
        errors.append("Coverage after-image fingerprint differs")
    if post.get("queue_sha256") != context.runtime.get("queue_sha256"):
        errors.append("Required Queue changed during metadata transition")
    if post.get("progress_sha256") != context.runtime.get("progress_sha256"):
        errors.append("Progress Ledger changed during metadata transition")
    try:
        repository_sha = kblib.repository_snapshot_sha256(
            root,
            excluded_paths=_transaction_artifact_paths(root, transaction))
    except (OSError, TypeError, ValueError) as exc:
        errors.append("repository after-image cannot be read: %s" % exc)
    else:
        if repository_sha != expected_repository_sha:
            errors.append("repository after-image fingerprint differs")
    try:
        page = kblib.repository_target_snapshot(
            root, context.page_path, suffixes=".md", singly_linked=True)
    except (OSError, ValueError) as exc:
        errors.append("page after-image cannot be read: %s" % exc)
    else:
        if not page.exists or page.sha256 != expected_page_sha:
            errors.append("page after-image fingerprint differs")
    try:
        metadata_gate_runtime.require_authorities_current(
            context, "metadata transition post-write authority")
    except ValueError as exc:
        errors.append(str(exc))
    return errors, post


def _same_snapshot(left, right):
    return (
        left.exists and right.exists and
        (left.dev, left.ino, left.mode, left.nlink, left.size,
         left.mtime_ns, left.ctime_ns, left.data) ==
        (right.dev, right.ino, right.mode, right.nlink, right.size,
         right.mtime_ns, right.ctime_ns, right.data)
    )


def _transaction_artifact_paths(root, transaction):
    """Return only live, exact projector-owned temporary artifact names."""
    paths = set()
    for staged in transaction.staged:
        parent = os.path.dirname(staged.projection.relative)
        for name in (staged.temporary_name, staged.backup_name):
            if not name:
                continue
            relative = (parent + "/" + name) if parent else name
            absolute = os.path.join(root, *relative.split("/"))
            if os.path.lexists(absolute):
                paths.add(relative)
    return paths


def _require_repository_snapshot(root, expected, phase, transaction=None):
    exclusions = (_transaction_artifact_paths(root, transaction)
                  if transaction is not None else None)
    current = kblib.repository_snapshot_sha256(
        root, excluded_paths=exclusions)
    if current != expected:
        raise ValueError(
            "%s: repository snapshot=%s, expected %s" %
            (phase, current, expected))


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Apply one receipt-backed Profile metadata transition")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--gate-id", required=True,
                        help="exact typed Profile Extension Gate ID")
    parser.add_argument("--page", required=True,
                        help="repository-relative Markdown target")
    parser.add_argument("--value", required=True,
                        help="requested registered completion value")
    parser.add_argument("--gate-receipt", required=True,
                        help="current producer receipt ID for this Gate")
    parser.add_argument("--actor-role", default="worker",
                        choices=("integrator", "worker"),
                        help="declared caller role; only integrator may write")
    parser.add_argument("--expected-coverage-sha256",
                        help="Coverage fingerprint observed by the caller")
    parser.add_argument("--expected-page-sha256",
                        help="target page fingerprint observed by the caller")
    parser.add_argument("--receipts",
                        help="fresh JSONL path under .cambium/receipts; "
                             "default is <receipt_id>.jsonl")
    parser.add_argument("--apply", action="store_true",
                        help="commit owner state and page projection")
    parser.add_argument("--json", action="store_true",
                        help="write the applied receipt as one JSON array")
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    try:
        context = metadata_gate_runtime.load_gate_context(
            root, args.gate_id, args.page)
        proposed, coverage_text, plan, receipt = prepare_transition(
            context, args.gate_receipt, args.value,
            actor_role=args.actor_role)
        receipt_relative = args.receipts or (
            ".cambium/receipts/%s.jsonl" % receipt["receipt_id"])
        receipt_path = kblib.managed_repository_path(
            root, receipt_relative, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False)
        if os.path.lexists(receipt_path):
            raise ValueError("transition receipt target already exists")
        receipt["receipt_path"] = receipt_relative
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    print("metadata transition plan: Gate=%s %s=%s page=%s Coverage %s -> %s" %
          (context.gate.gate_id, context.gate.field_id, args.value,
           context.page_path, context.runtime.get("coverage_sha256"),
           receipt["after_coverage_sha256"]))
    if not args.apply:
        if not args.json:
            print("dry run; add --apply --actor-role integrator with both "
                  "expected fingerprints")
        return 0
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply metadata state",
              file=sys.stderr)
        return 1
    if not args.expected_coverage_sha256 or not args.expected_page_sha256:
        print("[FAIL] --apply requires --expected-coverage-sha256 and "
              "--expected-page-sha256", file=sys.stderr)
        return 1
    if args.expected_coverage_sha256 != context.runtime.get("coverage_sha256"):
        print("[FAIL] expected Coverage fingerprint is stale", file=sys.stderr)
        return 1
    if args.expected_page_sha256 != context.page_snapshot.sha256:
        print("[FAIL] expected page fingerprint is stale", file=sys.stderr)
        return 1

    coverage_path = kblib.managed_repository_path(
        root, check_queue.COVERAGE_PATH, ".cambium/state",
        suffixes=(".yaml",), must_exist=True)
    coverage_snapshot = kblib.repository_target_snapshot(
        root, check_queue.COVERAGE_PATH, suffixes=".yaml",
        singly_linked=True)
    if coverage_snapshot.sha256 != context.runtime.get("coverage_sha256"):
        print("[FAIL] Coverage changed after transition planning",
              file=sys.stderr)
        return 1
    old_coverage_text = coverage_snapshot.read_text()
    operation = {
        "tool": TOOL,
        "action": "apply-profile-extension-gate-transition",
        "gate_id": context.gate.gate_id,
        "transition_id": context.gate.transition_id,
        "target": context.page_path,
        "before_coverage_sha256": context.runtime.get("coverage_sha256"),
        "planned_after_coverage_sha256":
            receipt["after_coverage_sha256"],
        "before_required_queue_sha256": context.runtime.get("queue_sha256"),
        "planned_after_required_queue_sha256":
            context.runtime.get("queue_sha256"),
        "before_progress_sha256": context.runtime.get("progress_sha256"),
        "planned_after_progress_sha256":
            context.runtime.get("progress_sha256"),
        "before_page_sha256": context.page_snapshot.sha256,
        "planned_after_page_sha256": receipt["after_page_sha256"],
        "before_repository_snapshot_sha256":
            receipt["before_repository_snapshot_sha256"],
        "planned_after_repository_snapshot_sha256":
            receipt["after_repository_snapshot_sha256"],
        "gate_receipt": args.gate_receipt,
        "receipt_id": receipt["receipt_id"],
        "receipt_path": receipt_relative,
        "metadata_execution_contract_fingerprint":
            context.metadata_contract_fingerprint,
    }
    operation.update(check_queue.runtime_authority_lock_fields(
        context.authority))
    transaction = None
    coverage_attempted = False
    receipt_attempted = False
    receipt_outcome = "not-attempted"
    try:
        authority_kwargs = check_queue.runtime_authority_validation_kwargs(
            context.authority)
        with kblib.runtime_write_lock(
                root, owner_metadata=operation) as lease:
            with kblib.no_authoritative_write_guard(lease):
                locked = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if locked.get("errors"):
                    raise ValueError(
                        "runtime changed before metadata write: %s" %
                        "; ".join(locked["errors"]))
                metadata_gate_runtime.require_context_current(
                    context, "metadata transition locked preflight",
                    runtime=locked)
                _current_receipt_from(
                    locked, context, args.gate_receipt, args.value)
                locked_coverage_snapshot = kblib.repository_target_snapshot(
                    root, check_queue.COVERAGE_PATH, suffixes=".yaml",
                    singly_linked=True)
                if not _same_snapshot(
                        coverage_snapshot, locked_coverage_snapshot):
                    raise ValueError(
                        "Coverage identity or bytes changed after planning")
                if os.path.lexists(receipt_path):
                    raise ValueError(
                        "transition receipt target appeared after planning")
                receipt_before = kblib.receipt_append_observation(
                    receipt_path, [receipt])
            # Staging writes a recovery journal and page-parent temporary
            # after-image.  It therefore sits outside the no-write guard; the
            # projector itself clears the journal only after proving cleanup.
            transaction = project_page_state.stage_projection_plan(
                root, plan, lease, receipt["receipt_id"])
            try:
                metadata_gate_runtime.require_context_current(
                    context, "metadata transition before owner write")
                _require_repository_snapshot(
                    root, receipt["before_repository_snapshot_sha256"],
                    "metadata transition before owner write", transaction)
                coverage_attempted = True
                kblib.atomic_write_text(
                    coverage_path, coverage_text,
                    validator=kblib.parse_yaml_subset)
                if kblib.sha256_file(coverage_path) != \
                        receipt["after_coverage_sha256"]:
                    raise ValueError("Coverage after-image was not published")
                metadata_gate_runtime.require_authorities_current(
                    context, "metadata transition after owner write")
                _require_repository_snapshot(
                    root, receipt["before_repository_snapshot_sha256"],
                    "metadata transition after owner write", transaction)
                transaction.publish()
                _require_repository_snapshot(
                    root, receipt["after_repository_snapshot_sha256"],
                    "metadata transition after page publication", transaction)
                post_errors, post = _post_state_errors(
                    root, context, receipt,
                    receipt["after_coverage_sha256"],
                    receipt["after_page_sha256"],
                    receipt["after_repository_snapshot_sha256"],
                    authority_kwargs, transaction)
                if post_errors:
                    raise ValueError(
                        "post-write reconciliation failed: %s" %
                        "; ".join(post_errors))
                _current_receipt_from(
                    post, context, args.gate_receipt, args.value,
                    require_current_repository=False)
                _require_repository_snapshot(
                    root, receipt["after_repository_snapshot_sha256"],
                    "metadata transition before receipt publication",
                    transaction)
                receipt_attempted = True
                receipt_outcome, receipt_error, _ = \
                    kblib.write_receipts_observed(
                        receipt_path, [receipt], exclusive=True,
                        before=receipt_before)
                if receipt_outcome != "present" or receipt_error is not None:
                    raise ValueError(
                        "transition receipt publication outcome=%s error=%s" %
                        (receipt_outcome, receipt_error))
                persisted = check_queue.validate_runtime(
                    root, **authority_kwargs)
                if persisted.get("errors"):
                    raise ValueError(
                        "persisted metadata transition is invalid: %s" %
                        "; ".join(persisted["errors"]))
                _current_receipt_from(
                    persisted, context, args.gate_receipt, args.value,
                    require_current_repository=False)
                metadata_gate_runtime.require_authorities_current(
                    context, "metadata transition before commit")
                _require_repository_snapshot(
                    root, receipt["after_repository_snapshot_sha256"],
                    "metadata transition before commit", transaction)
                transaction.commit()
                _require_repository_snapshot(
                    root, receipt["after_repository_snapshot_sha256"],
                    "metadata transition committed after-image")
            except Exception as write_error:
                rollback_failures = []
                if receipt_attempted and receipt_outcome != "absent":
                    rollback_failures.append(
                        "append-only transition receipt requires recovery: %s" %
                        receipt_outcome)
                if not rollback_failures and transaction is not None and \
                        transaction.state not in (
                            "rolled-back", "committed",
                            "commit-cleanup-failed"):
                    try:
                        transaction.rollback()
                    except Exception as exc:
                        rollback_failures.append("page projection: %s" % exc)
                if not rollback_failures and coverage_attempted:
                    try:
                        live_sha = kblib.sha256_file(coverage_path)
                        if live_sha == receipt["after_coverage_sha256"]:
                            kblib.atomic_write_text(
                                coverage_path, old_coverage_text,
                                validator=kblib.parse_yaml_subset)
                        elif live_sha != context.runtime.get("coverage_sha256"):
                            raise ValueError(
                                "Coverage is neither transaction before nor "
                                "after image")
                        if kblib.sha256_file(coverage_path) != \
                                context.runtime.get("coverage_sha256"):
                            raise ValueError(
                                "Coverage before-image could not be restored")
                    except Exception as exc:
                        rollback_failures.append("Coverage: %s" % exc)
                if rollback_failures:
                    raise ValueError(
                        "metadata transition failed and recovery is required: "
                        "%s; %s" %
                        (write_error, "; ".join(rollback_failures)))
                lease.mark_reconciled()
                raise
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] metadata transition was not committed: %s" % exc,
              file=sys.stderr)
        return 1

    if args.json:
        sys.stdout.write(
            kblib.canonical_json_bytes([receipt]).decode("utf-8") + "\n")
    else:
        print("[PASS] metadata transition committed; receipt=%s" %
              receipt["receipt_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
