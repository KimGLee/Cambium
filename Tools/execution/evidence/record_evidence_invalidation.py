#!/usr/bin/env python3
"""Append one authorized correction; never edit evidence or roll back state."""

from datetime import datetime, timezone
import os

from Tools.execution.evidence import evidence_invalidation_contract as contract
from Tools.execution.evidence import manual_attestation
from Tools.execution.task_runtime import queue_runtime, runtime_paths, runtime_validation
from Tools.execution.task_runtime.queue_runtime import authority as authority_owner
from Tools.platform.common import kblib, reporting


TOOL = contract.TOOL
TOOL_VERSION = contract.TOOL_VERSION
DEFAULT_RECEIPTS = runtime_paths.EVIDENCE_INVALIDATION_RECEIPT_PATH
ADMISSION_PURPOSE = "record-evidence-invalidation"


def prepare_event(runtime, authority, *, event_id, reason, decision,
                  subject_ids, checked_at):
    """Bind an externally decided correction to exact proved historical bodies."""
    errors = authority_owner.runtime_admission_errors(
        runtime, purpose=ADMISSION_PURPOSE)
    if errors:
        raise ValueError("correction admission failed: %s" % "; ".join(errors))
    if (not isinstance(subject_ids, (list, tuple)) or not subject_ids or
            any(not isinstance(value, str) or not value for value in subject_ids) or
            len(set(subject_ids)) != len(subject_ids)):
        raise ValueError("correction subjects must be non-empty unique receipt IDs")
    catalog = queue_runtime.historical_receipt_catalog(runtime)
    subjects = [contract.resolve_body(catalog, value) for value in subject_ids]
    if any(body is None for body in subjects):
        raise ValueError("correction subject is absent or cannot be proved")
    event = contract.build_event(
        event_id=event_id, reason=reason, decision=decision, subjects=subjects,
        authority=queue_runtime.runtime_authority_lock_fields(authority),
        checked_at=checked_at, root=runtime["root"])
    contract.validate_subjects(event, catalog, root=runtime["root"])
    existing = contract.resolve_body(catalog, event["receipt_id"])
    if existing is not None:
        # A retry's wall-clock timestamp is not a second semantic decision.
        event["checked_at"] = existing.get("checked_at")
        if existing != event:
            raise ValueError("event_id already binds a different correction decision")
    return event, existing is not None


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Record an authorized evidence invalidation without changing historical bytes")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--event-id", required=True, help="stable identity for this correction decision")
    parser.add_argument("--subject", action="append", required=True,
                        help="exact Receipt ID to invalidate; repeat for one bounded decision")
    policy = contract.load_policy()
    parser.add_argument("--reason", required=True, choices=policy["decision_reasons"])
    parser.add_argument("--decision-mode", required=True, choices=policy["decision_modes"])
    parser.add_argument("--actor-role", required=True, help="decision role, not the Integrator role")
    parser.add_argument("--reviewer-context-id", help="original reviewer context for own-declaration")
    parser.add_argument("--authority-reference", required=True,
                        help="reference to the actual operator/Host-attested decision; not authentication")
    parser.add_argument("--statement", required=True, help="exact bounded correction statement")
    parser.add_argument("--apply", action="store_true", help="append the event; omit for dry-run")
    parser.add_argument("--json", action="store_true", help="return publication facts as JSON")
    args = parser.parse_args(argv)
    root = os.path.realpath(os.path.abspath(args.root))
    publication = kblib.ReceiptPublication()
    decision = {
        "mode": args.decision_mode, "actor_role": args.actor_role,
        "reviewer_context_id": args.reviewer_context_id,
        "authority_reference": args.authority_reference, "statement": args.statement,
    }
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        runtime = runtime_validation.validate_runtime(root)
        authority = authority_owner.runtime_authority_context(
            runtime, purpose=ADMISSION_PURPOSE)
        def prepare(observation):
            return prepare_event(
                observation, authority, event_id=args.event_id,
                reason=args.reason, decision=decision, subject_ids=args.subject,
                checked_at=checked_at)
        event, reused = prepare(runtime)
        receipt_path = kblib.managed_repository_path(
            root, DEFAULT_RECEIPTS, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False)
        if reused:
            queue_runtime.require_runtime_authority_current(root, authority, "correction retry")
            publication.confirmed = True
            reporting.write_publication_result(
                publication, json_output=args.json, status="recorded", reused=True,
                receipt_id=event["receipt_id"], receipt_path=DEFAULT_RECEIPTS,
                receipts=[event], current_evidence_deficits=runtime.get("current_evidence_deficits", []))
            return 0
        # Prove the resulting event and its downstream view before attempting
        # any append. Unmet review obligations are not a structural failure.
        proposed = runtime_validation.validate_runtime(
            root, extra_receipts=[event],
            **queue_runtime.runtime_authority_validation_kwargs(authority))
        proposed_errors = authority_owner.runtime_admission_errors(
            proposed, purpose=ADMISSION_PURPOSE)
        if proposed_errors:
            raise ValueError("proposed correction is invalid: %s" % "; ".join(proposed_errors))
        if not args.apply:
            reporting.write_publication_result(
                publication, json_output=args.json, status="planned",
                receipt_id=event["receipt_id"], receipt_path=DEFAULT_RECEIPTS,
                receipts=[event],
                current_evidence_deficits=proposed.get("current_evidence_deficits", []))
            return 0
        operation = {
            "tool": TOOL, "action": ADMISSION_PURPOSE,
            "receipt_id": event["receipt_id"], "receipt_path": DEFAULT_RECEIPTS,
            **queue_runtime.runtime_authority_lock_fields(authority),
        }
        for ledger in ("coverage", "queue", "progress"):
            operation["before_%s_sha256" % ledger] = runtime["%s_sha256" % ledger]
            operation["planned_after_%s_sha256" % ledger] = runtime["%s_sha256" % ledger]
        def validate(locked, candidate):
            contract.validate_subjects(
                candidate, queue_runtime.historical_receipt_catalog(locked), root=root)
            for ledger in ("coverage", "queue", "progress"):
                if locked.get("%s_sha256" % ledger) != runtime.get("%s_sha256" % ledger):
                    raise ValueError("correction observed changed %s state" % ledger)
        event = manual_attestation.publish_receipt(
            root, receipt_path, event, authority=authority, operation=operation,
            rebuild=lambda locked: prepare(locked)[0], validate=validate,
            publication_label="evidence invalidation", publication=publication)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        reporting.write_publication_result(
            publication, json_output=args.json, status="invalid", errors=[str(exc)])
        return 1
    reporting.write_publication_result(
        publication, json_output=args.json, status="recorded",
        reused=publication.confirmed and publication.outcome == "not-attempted",
        receipt_id=event["receipt_id"], receipt_path=DEFAULT_RECEIPTS,
        receipts=[event], current_evidence_deficits=proposed.get("current_evidence_deficits", []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
