"""Is one K13/02 bounded policy exception well formed.

The same exception is written twice -- once in the live Progress spelling and
once in the sealed close-time decision record -- and both are validated at
the same severity here.  Validating the sealed copy more loosely than the
live one would make sealing a way to launder a malformed exception.
"""

import contract_exception_policy
import kblib

from queue_runtime.canon import SHA256_RE
from queue_runtime.primitives import (
    _closed_mapping_errors,
    _nonempty_string,
)


POLICY_EXCEPTION_FIELDS = frozenset((
    "decision_id", "policy_id", "baseline_policy_fingerprint", "limit",
    "scope_kind", "scope_ref", "rationale", "approval_reference",
))
POLICY_EXCEPTION_SCOPE_KINDS = frozenset(("task", "repository-snapshot"))


SEALED_POLICY_EXCEPTION_FIELDS = frozenset((
    "decision_id", "policy_id", "limit", "scope_kind", "scope_ref",
    "policy_fingerprint", "pages", "total",
))


def _policy_exception_errors(value, label):
    """Validate the contract's bounded policy exceptions, K13/02 shape.

    Every entry is an answer a person already gave: which policy it excepts,
    the bound it grants, what it was granted against, and where the approval
    lives.  The baseline fingerprint is what makes an exception die with the
    policy it was judged against instead of surviving a Standards or Profile
    revision it never saw.
    """
    errors = []
    if not isinstance(value, list):
        return ["%s must be an explicit list" % label]
    seen = set()
    for index, entry in enumerate(value):
        entry_label = "%s[%d]" % (label, index)
        if not isinstance(entry, dict):
            errors.append("%s must be a mapping" % entry_label)
            continue
        errors.extend(_closed_mapping_errors(
            entry, entry_label, POLICY_EXCEPTION_FIELDS))
        if not isinstance(entry, dict) or set(entry) - POLICY_EXCEPTION_FIELDS:
            continue
        for field in ("decision_id", "policy_id", "scope_ref", "rationale",
                      "approval_reference"):
            if not _nonempty_string(entry.get(field)):
                errors.append("%s %s must be a non-empty string" %
                              (entry_label, field))
        decision = entry.get("decision_id")
        if _nonempty_string(decision):
            if decision in seen:
                errors.append("%s repeats decision_id %s" %
                              (label, decision))
            seen.add(decision)
        fingerprint = entry.get("baseline_policy_fingerprint")
        if (not isinstance(fingerprint, str) or
                not SHA256_RE.fullmatch(fingerprint)):
            errors.append(
                "%s baseline_policy_fingerprint must be sha256:<64 lowercase "
                "hex>; an exception unbound from the policy bytes it was "
                "judged against would survive revisions it never saw" %
                entry_label)
        policy_id = entry.get("policy_id")
        registered = (
            contract_exception_policy.POLICY_REGISTRY.get(policy_id)
            if isinstance(policy_id, str) else None)
        if _nonempty_string(policy_id) and registered is None:
            errors.append(
                "%s policy_id %r is not in the closed policy registry; an "
                "exception to a policy nobody registered is unbounded "
                "authorization" % (entry_label, policy_id))
        limit = entry.get("limit")
        domain = registered.get("limit_domain") if registered else None
        if (not isinstance(limit, (int, float)) or isinstance(limit, bool)):
            errors.append("%s limit must be a number" % entry_label)
        elif domain == "percent-share-under-100" and not 0 <= limit < 100:
            errors.append(
                "%s limit must be a corpus share at least 0 and under 100; "
                "%r is not a bound, per %s" %
                (entry_label, limit, registered["owner"]))
        elif domain == "record-count-ceiling" and (
                isinstance(limit, float) or limit < 0):
            errors.append(
                "%s limit must be a non-negative whole record count; %r "
                "cannot be compared to a number of records, per %s" %
                (entry_label, limit, registered["owner"]))
        if entry.get("scope_kind") not in POLICY_EXCEPTION_SCOPE_KINDS:
            errors.append(
                "%s scope_kind must be one of %s" %
                (entry_label,
                 ", ".join(sorted(POLICY_EXCEPTION_SCOPE_KINDS))))
    # Joint bound and conflict rules across the register: the granted P0 and
    # P1 ceilings partition the same corpus as the standing quotas do, and
    # two grants for the same policy in the same scope are a conflict, not a
    # choice the consumer may make.
    by_key = {}
    ceilings = {}
    for entry in value:
        if not isinstance(entry, dict):
            continue
        policy_id = entry.get("policy_id")
        limit = entry.get("limit")
        key = (policy_id, entry.get("scope_kind"), entry.get("scope_ref"))
        if all(key):
            if key in by_key:
                errors.append(
                    "%s carries conflicting grants for %s in the same scope; "
                    "one policy has one current bound" % (label, policy_id))
            by_key[key] = entry
        if (isinstance(limit, (int, float)) and not isinstance(limit, bool)
                and isinstance(policy_id, str) and
                policy_id in contract_exception_policy.POLICY_REGISTRY):
            ceilings[policy_id] = max(ceilings.get(policy_id, 0), limit)
    if (ceilings.get("priority_quota.P0", 0) +
            ceilings.get("priority_quota.P1", 0)) >= 100:
        errors.append(
            "%s granted quota ceilings sum to %.1f%%; K00/07 requires the "
            "pair to stay strictly below 100 so the P2 remainder class "
            "stays non-empty" %
            (label, ceilings.get("priority_quota.P0", 0) +
             ceilings.get("priority_quota.P1", 0)))
    return errors


def _sealed_policy_exception_errors(sealed, decision_id, candidate_type,
                                    label):
    """Validate one sealed policy-exception decision record, strictly.

    The sealed mapping is the durable record of an authorization; replay
    validates it with the same severity the close-time writer applied, and
    every check here FAILS CLOSED: a field of the wrong type is an error,
    never a skipped comparison.  In particular the share arithmetic is only
    meaningful over validated integers -- guarding it behind an isinstance
    test that silently skips on mismatch would let a string smuggle an
    unverified authorization through replay.
    """
    errors = []
    errors.extend(_closed_mapping_errors(
        sealed, "%s sealed policy exception" % label,
        SEALED_POLICY_EXCEPTION_FIELDS))
    if set(sealed) != set(SEALED_POLICY_EXCEPTION_FIELDS):
        return errors
    if sealed.get("decision_id") != decision_id:
        errors.append("%s sealed decision_id does not match accepted_by" %
                      label)
    policy_id = sealed.get("policy_id")
    registered = (contract_exception_policy.POLICY_REGISTRY.get(policy_id)
                  if isinstance(policy_id, str) else None)
    if registered is None:
        errors.append(
            "%s sealed policy_id %r is not in the closed policy registry" %
            (label, policy_id))
    else:
        # The candidate names its class in its type (`...:priority-quota-P0`)
        # and the exception names its policy; the two must be the same class.
        # A P0 excess accepted through a P1 grant is an authorization for a
        # different decision than the one the reviewer sealed.
        suffix = str(candidate_type or "").rsplit(":", 1)[-1]
        expected_suffix = "priority-quota-%s" % registered.get("quota_class")
        if suffix != expected_suffix:
            errors.append(
                "%s sealed policy %s covers class %s, but the candidate is "
                "%r; an exception authorizes exactly its own class" %
                (label, policy_id, registered.get("quota_class"),
                 candidate_type))
    fingerprint = sealed.get("policy_fingerprint")
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(
            fingerprint):
        errors.append(
            "%s sealed policy_fingerprint must be sha256:<64 lowercase "
            "hex>" % label)
    if sealed.get("scope_kind") not in POLICY_EXCEPTION_SCOPE_KINDS:
        errors.append("%s sealed scope_kind must be one of %s" %
                      (label, ", ".join(sorted(POLICY_EXCEPTION_SCOPE_KINDS))))
    if not _nonempty_string(sealed.get("scope_ref")):
        errors.append("%s sealed scope_ref must be a non-empty string" %
                      label)
    limit = sealed.get("limit")
    limit_ok = (not isinstance(limit, bool) and
                isinstance(limit, (int, float)))
    if not limit_ok:
        errors.append("%s sealed limit must be a number" % label)
    elif (registered is not None and
          registered.get("limit_domain") == "percent-share-under-100" and
          not 0 <= limit < 100):
        errors.append(
            "%s sealed limit %r is not a corpus share at least 0 and under "
            "100" % (label, limit))
        limit_ok = False
    counts_ok = True
    for field in ("pages", "total"):
        value = sealed.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append("%s sealed %s must be an integer" % (label, field))
            counts_ok = False
    if counts_ok:
        pages, total = sealed["pages"], sealed["total"]
        if not (0 <= pages <= total and total >= 1):
            errors.append(
                "%s sealed counts %r/%r are not a corpus share" %
                (label, pages, total))
            counts_ok = False
    if (counts_ok and limit_ok and
            not kblib.quota_share_within_limit(
                sealed["pages"], sealed["total"], limit)):
        errors.append(
            "%s sealed share %s/%s exceeds the sealed limit %r; the receipt "
            "claims an authorization its own numbers refute" %
            (label, sealed.get("pages"), sealed.get("total"), limit))
    return errors
