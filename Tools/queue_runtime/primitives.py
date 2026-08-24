"""Is this scalar, mapping, timestamp or graph well formed at all.

The domain-free refusals every validator opens with.  Nothing here knows what
a Queue, a Batch or a receipt is; each function answers a question about
shape alone, which is why they can be shared by every layer above without
carrying any of them into the others.  ``nonempty_string`` has eighty-eight
callers, and the point of this file is that all eighty-eight refuse in the
same words.
"""

import datetime


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


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


def closed_mapping_errors(value, label, fields, optional_fields=()):
    """Require one explicit mapping with exactly the declared field set."""
    if not isinstance(value, dict):
        return ["%s must be a mapping" % label]
    errors = []
    missing = sorted(set(fields) - set(optional_fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing:
        errors.append("%s misses explicit field(s): %s" %
                      (label, ", ".join(missing)))
    if extra:
        errors.append("%s has unsupported field(s): %s" %
                      (label, ", ".join(extra)))
    return errors


def explicit_string_list_errors(value, label):
    if not isinstance(value, list):
        return ["%s must be an explicit list" % label]
    errors = []
    if not all(nonempty_string(entry) for entry in value):
        errors.append("%s must contain only non-empty strings" % label)
    if len(value) != len(set(entry for entry in value if isinstance(entry, str))):
        errors.append("%s must not contain duplicates" % label)
    return errors


def identity(data, key, nested=False):
    if nested:
        contract = data.get("contract")
        return contract.get(key) if isinstance(contract, dict) else None
    return data.get(key)


def acyclic(items_by_id):
    colors = {}
    cycle = []

    def visit(item_id, trail):
        color = colors.get(item_id, 0)
        if color == 1:
            cycle.extend(trail[trail.index(item_id):] + [item_id])
            return False
        if color == 2:
            return True
        colors[item_id] = 1
        for dep in items_by_id[item_id].get("depends_on", []):
            if dep in items_by_id and not visit(dep, trail + [dep]):
                return False
        colors[item_id] = 2
        return True

    for item_id in items_by_id:
        if not visit(item_id, [item_id]):
            return cycle
    return []
