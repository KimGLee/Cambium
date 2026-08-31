"""Is this scalar, mapping, timestamp or graph well formed at all.

The domain-free refusals every validator opens with.  Nothing here knows what
a Queue, a Batch or a receipt is; each function answers a question about
shape alone, which is why they can be shared by every layer above without
carrying any of them into the others.  The public names remain here as Queue
runtime imports, while their single implementation lives in the platform
primitive module below every domain consumer.
"""

from Tools.platform.common.primitives import (
    nonempty_string,
    timestamp_value,
    valid_timestamp,
)


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
