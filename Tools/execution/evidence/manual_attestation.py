"""Shared publication boundary for manual-attestation producers.

The semantic owner of an attestation remains the Gate or review contract that
builds it. This module owns only the deterministic publication mechanics the
manual producers share: statement admission, runtime-authority CAS, locked
rebuild, consumer self-check, append-only publication, and exact catalog
read-back. It never selects a Gate, invents a verdict, or changes Queue,
Coverage, Progress, page, or Delta bytes.
"""

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation
from Tools.execution.task_runtime.queue_runtime.authority import runtime_admission_errors
import Tools.platform.common.kblib as kblib


def require_statement(statement, label="manual attestation"):
    """Return one stripped, non-empty statement or reject it."""
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("%s requires a non-empty statement" % label)
    return statement.strip()


def _freeze_generated_identity(planned, rebuilt):
    """Keep the dry-run identity while rebuilding all semantic bindings."""
    if not isinstance(planned, dict) or not isinstance(rebuilt, dict):
        raise TypeError("manual attestation receipts must be mappings")
    frozen = dict(rebuilt)
    for field in ("receipt_id", "checked_at"):
        value = planned.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError("planned receipt has no %s" % field)
        frozen[field] = value
    return frozen


def publish_receipt(root, receipt_path, planned_receipt, *, authority,
                    operation, rebuild, validate, publication_label, publication):
    """Publish one locked, self-validating manual receipt and read it back.

    ``rebuild(locked_runtime)`` must derive a fresh receipt from the runtime and
    external bound inputs re-read while the cooperating-writer lock is held.
    ``validate(locked_runtime, receipt)`` must invoke the same consumer
    predicates that will later accept the evidence. The caller's first receipt
    supplies only its generated identity and timestamp; every other byte must
    match the locked rebuild.

    A failure before publication clears the lock through
    :func:`kblib.no_authoritative_write_guard`. Once append is attempted, the
    lock is retained unless absence is proven, preserving the existing recovery
    contract for an uncertain or semantically invalid durable write.
    """
    if not callable(rebuild) or not callable(validate):
        raise TypeError("rebuild and validate must be callable")
    if not isinstance(publication, kblib.ReceiptPublication):
        raise TypeError("publication requires invocation-local Receipt I/O facts")
    if not isinstance(publication_label, str) or not publication_label.strip():
        raise ValueError("publication_label must be non-empty text")

    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
    admission_purpose = (authority.get("admission_purpose", "current")
                         if isinstance(authority, dict) else "current")
    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        with kblib.no_authoritative_write_guard(lease):
            locked = runtime_validation.validate_runtime(root, **authority_kwargs)
            admission_errors = runtime_admission_errors(
                locked, purpose=admission_purpose)
            if admission_errors:
                raise ValueError(
                    "runtime changed before %s: %s" %
                    (publication_label, "; ".join(admission_errors)))
            queue_runtime.require_runtime_authority_current(
                root, authority, publication_label)
            locked_receipt = _freeze_generated_identity(
                planned_receipt, rebuild(locked))
            if locked_receipt != planned_receipt:
                raise ValueError(
                    "%s bindings changed before publication" %
                    publication_label)
            validate(locked, locked_receipt)
            existing = queue_runtime.current_receipt_catalog(locked).get(
                locked_receipt["receipt_id"])
            if existing is not None:
                observed = existing[1] if isinstance(existing, tuple) else existing
                if observed != locked_receipt:
                    raise ValueError("%s identity already binds different bytes" %
                                     publication_label)
                # Another cooperating invocation may have published this
                # exact operation before we acquired the lock. Confirm its
                # current object; never append the same identity twice.
                publication.confirmed = True
                return locked_receipt
            before = kblib.receipt_append_observation(
                receipt_path, [locked_receipt])

        outcome, error, _observation = publication.append(
            receipt_path, [locked_receipt], before=before)
        if outcome != "present" or error is not None:
            if outcome == "absent":
                lease.mark_reconciled()
            raise ValueError(
                "%s outcome=%s error=%s" %
                (publication_label, outcome, error))

        # A successful append syscall is not resulting-state evidence. Re-open
        # the runtime under the same authority view and require the exact object
        # to resolve through the ordinary current catalog.
        readback = runtime_validation.validate_runtime(root, **authority_kwargs)
        admission_errors = runtime_admission_errors(
            readback, purpose=admission_purpose)
        if admission_errors:
            raise ValueError(
                "%s read-back is inconsistent: %s" %
                (publication_label, "; ".join(admission_errors)))
        queue_runtime.require_runtime_authority_current(
            root, authority, "%s read-back" % publication_label)
        entry = queue_runtime.current_receipt_catalog(readback).get(
            locked_receipt["receipt_id"])
        observed = entry[1] if isinstance(entry, tuple) else entry
        if observed != locked_receipt:
            raise ValueError(
                "%s read-back did not resolve the exact receipt" %
                publication_label)
    publication.confirmed = True
    return locked_receipt


__all__ = ("publish_receipt", "require_statement")
