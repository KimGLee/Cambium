"""Pure Coverage open-gap projection shared by Delta consumers.

The page-field editor in :mod:`apply_delta` still owns its line-preserving
worker format.  Once those page edits have produced valid Coverage bytes,
this module is the only implementation of ``open_gaps_added`` /
``open_gaps_closed`` reconciliation.  Writers and admission checks therefore
judge the same prospective after-image instead of approximating selectors.
"""

import copy

import kblib


def gap_key(value):
    """Return the stable identity used by the current open-gap protocol."""
    if isinstance(value, dict) and isinstance(value.get("id"), str) and \
            value["id"].strip():
        return ("id", value["id"])
    if isinstance(value, dict):
        return ("page-type", value.get("page"), value.get("type"))
    if isinstance(value, str):
        return ("id", value)
    return None


def gap_identity_text(value):
    key = gap_key(value)
    if key is None:
        return "<invalid>"
    if key[0] == "id":
        return str(key[1])
    return "%s#%s" % (key[1], key[2])


def _indexed_gaps(gaps, label):
    if not isinstance(gaps, list):
        raise ValueError("%s must be an explicit list" % label)
    indexed = {}
    for index, gap in enumerate(gaps):
        key = gap_key(gap)
        if key is None or (key[0] == "page-type" and
                           (not key[1] or not key[2])):
            raise ValueError("%s[%d] has no stable id or page+type" %
                             (label, index))
        if key in indexed:
            raise ValueError("%s repeats gap identity %r" % (label, key))
        indexed[key] = copy.deepcopy(gap)
    return indexed


def project_open_gaps(coverage, delta):
    """Return a complete Coverage object after applying Delta gap sections."""
    if not isinstance(coverage, dict):
        raise ValueError("Coverage Ledger top level must be a mapping")
    if not isinstance(delta, dict):
        raise ValueError("Coverage Delta top level must be a mapping")
    result = copy.deepcopy(coverage)
    indexed = _indexed_gaps(result.get("open_gaps"), "Coverage open_gaps")
    additions = delta.get("open_gaps_added")
    closures = delta.get("open_gaps_closed")
    if not isinstance(additions, list):
        raise ValueError("open_gaps_added must be an explicit list")
    if not isinstance(closures, list):
        raise ValueError("open_gaps_closed must be an explicit list")

    close_keys = [gap_key(selector) for selector in closures]
    if None in close_keys:
        raise ValueError("open_gaps_closed contains an invalid selector")
    if len(close_keys) != len(set(close_keys)):
        raise ValueError("open_gaps_closed repeats a gap identity")
    add_index = _indexed_gaps(additions, "open_gaps_added")
    overlap = set(close_keys).intersection(add_index)
    if overlap:
        raise ValueError("one delta cannot close and add the same gap: %r" %
                         sorted(overlap))
    for key in close_keys:
        if key not in indexed:
            raise ValueError("open_gaps_closed references absent gap %r" %
                             (key,))
        indexed.pop(key)

    page_paths = {
        page.get("path") for page in result.get("pages", [])
        if isinstance(page, dict)
    }
    for key, gap in add_index.items():
        if key in indexed:
            raise ValueError("open_gaps_added already exists: %r" % (key,))
        if gap.get("page") not in page_paths:
            raise ValueError("open gap page is absent from Coverage: %s" %
                             gap.get("page"))
        indexed[key] = gap
    result["open_gaps"] = list(indexed.values())
    if delta.get("generated_at") is not None:
        result["updated_at"] = delta["generated_at"]
    return result


def project_coverage_text(page_edited_text, delta):
    """Project gaps on page-edited Coverage bytes and return canonical bytes."""
    coverage = kblib.parse_yaml_subset(page_edited_text)
    return kblib.canonical_yaml(project_open_gaps(coverage, delta))
