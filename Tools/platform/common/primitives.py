"""Domain-free scalar and timestamp shape predicates.

These helpers are platform mechanics, not Queue policy.  They live below the
domain contracts that consume them so Coverage planning and Queue validation
share one implementation without introducing a dependency cycle.
"""

import datetime


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def catalog_record(entry):
    """Return the record mapping carried by one catalog entry, if present.

    Receipt catalogs normally map an identity to ``(source, record)`` while
    a few bounded tests and projections supply the record mapping directly.
    This helper only recognizes those two shapes; it does not decide whether
    the record is current, passing, correctly keyed, or otherwise admissible.
    """
    if isinstance(entry, tuple) and len(entry) == 2:
        return entry[1] if isinstance(entry[1], dict) else None
    return entry if isinstance(entry, dict) else None


def catalog_receipt(catalog, receipt_id):
    """Return a record from a plain mapping catalog, or ``None``."""
    entry = catalog.get(receipt_id) if isinstance(catalog, dict) else None
    return catalog_record(entry)


def require_trimmed_string(value, label):
    """Return one non-empty trimmed string or raise the shared shape error."""
    if (not isinstance(value, str) or not value or
            value.strip() != value):
        raise ValueError("%s must be a non-empty trimmed string" % label)
    return value


def timestamp_value(value):
    """Return one RFC 3339 instant normalized to UTC, or ``None``."""
    if not nonempty_string(value):
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(datetime.timezone.utc)


def valid_timestamp(value):
    """Return true for a timezone-aware RFC 3339 timestamp."""
    return timestamp_value(value) is not None
