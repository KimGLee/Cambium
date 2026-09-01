"""Classify append-only evidence attempts without confusing history with now.

The hot receipt catalog answers whether a record remains authorized for use
under the active adoption.  It does not prove that the record still observes
the current page, repository, or runtime inputs of one AuditPlan obligation.
Producers and consumers use this helper to apply those two proofs in order:

1. ``validate_stable`` proves the immutable record/plan/contract binding.
2. ``validate_current`` proves the same valid record against current inputs.

A record that passes (1) but not (2) is valid stale history and never blocks a
successor attempt.  A record that fails (1) is malformed evidence and fails
closed.  At most one record may pass both proofs.
"""


class EvidenceAttemptError(ValueError):
    """Evidence attempt history is malformed or has multiple current rows."""


def _receipt_id(record):
    value = record.get("receipt_id") if isinstance(record, dict) else None
    if not isinstance(value, str) or not value or value.strip() != value:
        raise EvidenceAttemptError(
            "evidence attempt must have a non-empty trimmed receipt_id")
    return value


def classify_attempts(records, *, validate_stable, validate_current, label):
    """Return stable stale/current attempts after two independent proofs.

    Validators return normally on success and raise ``ValueError`` (or a
    normal filesystem/decoding error) when their proof does not hold.  Stable
    failures are corruption, while current failures are the expected signal
    that an append-only predecessor no longer observes the live input.
    """
    if not isinstance(records, (list, tuple)):
        raise EvidenceAttemptError("%s attempts must be a sequence" % label)
    if not callable(validate_stable) or not callable(validate_current):
        raise EvidenceAttemptError("%s validators must be callable" % label)

    seen = set()
    stable = []
    stale = []
    current = []
    invalid = []
    for record in records:
        try:
            receipt_id = _receipt_id(record)
        except EvidenceAttemptError as exc:
            invalid.append(str(exc))
            continue
        if receipt_id in seen:
            invalid.append("duplicate receipt_id %s" % receipt_id)
            continue
        seen.add(receipt_id)
        try:
            validate_stable(record)
        except (OSError, TypeError, UnicodeError, ValueError) as exc:
            invalid.append("%s: %s" % (receipt_id, exc))
            continue
        stable.append(record)
        try:
            validate_current(record)
        except (OSError, TypeError, UnicodeError, ValueError):
            stale.append(record)
        else:
            current.append(record)

    if invalid:
        raise EvidenceAttemptError(
            "%s has invalid stable attempt(s): %s" %
            (label, "; ".join(invalid)))
    return {
        "stable": tuple(stable),
        "stale": tuple(stale),
        "current": tuple(current),
    }


def unique_current_attempt(records, *, validate_stable, validate_current,
                           label):
    """Return the sole input-current attempt, ``None`` when all are stale."""
    classified = classify_attempts(
        records, validate_stable=validate_stable,
        validate_current=validate_current, label=label)
    current = classified["current"]
    if len(current) > 1:
        raise EvidenceAttemptError(
            "%s has multiple current attempts: %s" % (
                label, ", ".join(sorted(
                    record["receipt_id"] for record in current))))
    return current[0] if current else None


__all__ = [
    'EvidenceAttemptError',
    'unique_current_attempt',
]
