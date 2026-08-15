"""Pure candidate continuation helpers for K12/09 batch close.

The close producer still scans the complete repository on every run.  This
module only answers the smaller question that follows the scan: which exact
observations were explicitly accepted for reuse by the immediately preceding
successful close, and which observations still require a current decision?

The v1 protocol is deliberately conservative.  A raw producer-version change
forces a fresh decision, legacy evidence never gains durability implicitly,
and manifest-local page-contract findings are always current-only.
"""

import hashlib
import re

import kblib


CANDIDATE_PROTOCOL = "exact-carry-v1"
BASELINE_NONE = "none"
BASELINE_LEGACY = "legacy"
BASELINE_CURRENT = CANDIDATE_PROTOCOL
BASELINE_PROTOCOLS = frozenset((
    BASELINE_NONE, BASELINE_LEGACY, BASELINE_CURRENT,
))

ACCEPT_CURRENT = "accept-current"
ACCEPT_WHILE_UNCHANGED = "accept-while-unchanged"
DISPOSITIONS = frozenset((ACCEPT_CURRENT, ACCEPT_WHILE_UNCHANGED))

# These rows describe debt local to the batch being closed.  Reusing an old
# decision for a different batch would turn an exact observation match into a
# scope escape.  Priority-quota candidates are separated before this module is
# called and remain owned by the bounded policy-exception path.
FRESH_ONLY_MEMBERS = frozenset(("manifest_page_contract",))

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DISPOSITION_FIELDS = frozenset((
    "accepted_by", "disposition", "observation_sha256",
))


def _sha256(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_json(value):
    return kblib.canonical_json_bytes(value)


def observation_payload(candidate):
    """Return the closed observation mapping whose bytes authorize reuse."""
    if not isinstance(candidate, dict):
        raise ValueError("candidate observation must be a mapping")
    return {
        key: candidate[key]
        for key in sorted(candidate)
        if key not in _DISPOSITION_FIELDS
    }


def observation_sha256(candidate):
    return _sha256(_canonical_json(observation_payload(candidate)))


def with_observation(candidate):
    row = dict(candidate)
    row["observation_sha256"] = observation_sha256(row)
    return row


def observation_errors(candidate, label="candidate"):
    errors = []
    if not isinstance(candidate, dict):
        return ["%s must be a mapping" % label]
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.startswith(
            "candidate-sha256:"):
        errors.append("%s has no stable candidate_id" % label)
    producer_version = candidate.get("producer_tool_version")
    if not isinstance(producer_version, str) or not producer_version.strip():
        errors.append("%s producer_tool_version must be a non-empty string" %
                      label)
    observed = candidate.get("observation_sha256")
    if not isinstance(observed, str) or not _SHA256_RE.fullmatch(observed):
        errors.append("%s observation_sha256 must be a sha256 fingerprint" %
                      label)
    elif observed != observation_sha256(candidate):
        errors.append("%s observation_sha256 does not match its exact row" %
                      label)
    return errors


def candidate_set_sha256(candidate_ids):
    values = sorted(candidate_ids)
    joined = "\n".join(values) + ("\n" if values else "")
    return _sha256(joined.encode("utf-8"))


def _evidence_row(candidate, disposition, accepted_by):
    row = dict(candidate)
    row["disposition"] = disposition
    row["accepted_by"] = accepted_by
    return row


def partition_against_baseline(candidates, baseline_rows):
    """Partition current observations into exact carried and fresh rows.

    The baseline is the immediately preceding successful close only.  Callers
    deliberately do not feed older evidence here, so a resolved candidate
    that later reappears cannot jump across the disappearance interval.
    """
    errors = []
    current_by_id = {}
    for index, candidate in enumerate(candidates):
        label = "current candidate[%d]" % index
        errors.extend(observation_errors(candidate, label))
        candidate_id = candidate.get("candidate_id") if isinstance(
            candidate, dict) else None
        if isinstance(candidate_id, str):
            if candidate_id in current_by_id:
                errors.append("current candidates repeat %s" % candidate_id)
            current_by_id[candidate_id] = candidate

    baseline_by_id = {}
    for index, row in enumerate(baseline_rows or []):
        label = "baseline candidate[%d]" % index
        errors.extend(observation_errors(row, label))
        disposition = row.get("disposition") if isinstance(row, dict) else None
        if disposition not in DISPOSITIONS:
            errors.append("%s disposition must be one of %s" % (
                label, ", ".join(sorted(DISPOSITIONS))))
        candidate_id = row.get("candidate_id") if isinstance(row, dict) else None
        if isinstance(candidate_id, str):
            if candidate_id in baseline_by_id:
                errors.append("baseline candidates repeat %s" % candidate_id)
            baseline_by_id[candidate_id] = row

    if errors:
        return errors, [], list(candidates)

    carried = []
    fresh = []
    for candidate in candidates:
        prior = baseline_by_id.get(candidate["candidate_id"])
        if (prior is not None and
                prior.get("disposition") == ACCEPT_WHILE_UNCHANGED and
                prior.get("observation_sha256") ==
                candidate.get("observation_sha256") and
                candidate.get("member") not in FRESH_ONLY_MEMBERS):
            carried.append(_evidence_row(
                candidate, ACCEPT_WHILE_UNCHANGED,
                prior.get("accepted_by")))
        else:
            fresh.append(candidate)
    return [], carried, fresh


def disposition_candidates(candidates, accepted_ids, accepted_types,
                           durable_ids, durable_types):
    """Apply current-only or exact durable selectors to fresh candidates."""
    current_ids = {candidate["candidate_id"] for candidate in candidates}
    current_types = {candidate["candidate_type"] for candidate in candidates}
    selected_ids = set(accepted_ids) | set(durable_ids)
    selected_types = set(accepted_types) | set(durable_types)
    errors = []
    stale_ids = sorted(selected_ids - current_ids)
    stale_types = sorted(selected_types - current_types)
    if stale_ids:
        errors.append("accepted candidate IDs are absent from this fresh "
                      "snapshot: %s" % ", ".join(stale_ids))
    if stale_types:
        errors.append("accepted candidate types are absent from this fresh "
                      "snapshot: %s" % ", ".join(stale_types))

    accepted = []
    unaccepted = []
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        candidate_type = candidate["candidate_type"]
        durable = (candidate_id in durable_ids or
                   candidate_type in durable_types)
        current = (candidate_id in accepted_ids or
                   candidate_type in accepted_types)
        if not durable and not current:
            unaccepted.append(candidate)
            continue
        if durable and candidate.get("member") in FRESH_ONLY_MEMBERS:
            errors.append(
                "%s candidate %s is manifest-local and cannot be accepted "
                "while unchanged" % (candidate.get("member"), candidate_id))
            continue
        accepted_by = "candidate-id" if (
            candidate_id in durable_ids or candidate_id in accepted_ids
        ) else "candidate-type"
        accepted.append(_evidence_row(
            candidate,
            ACCEPT_WHILE_UNCHANGED if durable else ACCEPT_CURRENT,
            accepted_by,
        ))
    if unaccepted:
        errors.append("%d fresh candidate(s) lack an explicit ID/type "
                      "disposition" % len(unaccepted))
    return errors, accepted, unaccepted


def continuation_attestation_errors(attestation, label):
    """Validate the compact exact-carry fields without parsing evidence."""
    errors = []
    if attestation.get("candidate_protocol") != CANDIDATE_PROTOCOL:
        errors.append("%s candidate_protocol must be %s" %
                      (label, CANDIDATE_PROTOCOL))
    baseline_protocol = attestation.get("candidate_baseline_protocol")
    if baseline_protocol not in BASELINE_PROTOCOLS:
        errors.append("%s candidate_baseline_protocol must be one of %s" % (
            label, ", ".join(sorted(BASELINE_PROTOCOLS))))
    baseline_id = attestation.get("candidate_baseline_receipt")
    if baseline_protocol == BASELINE_NONE:
        if baseline_id is not None:
            errors.append("%s candidate_baseline_receipt must be null when "
                          "the baseline protocol is none" % label)
    elif not isinstance(baseline_id, str) or not baseline_id.strip():
        errors.append("%s candidate_baseline_receipt must name the latest "
                      "closed attestation" % label)

    counts = {}
    for field in ("carried_candidate_count", "fresh_candidate_count"):
        value = attestation.get(field)
        if (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            errors.append("%s %s must be a non-negative integer" %
                          (label, field))
        else:
            counts[field] = value
    for field in ("carried_candidate_set_sha256",
                  "fresh_candidate_set_sha256"):
        value = attestation.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            errors.append("%s %s must be a sha256 fingerprint" %
                          (label, field))
    total = attestation.get("accepted_candidate_count")
    if (isinstance(total, int) and not isinstance(total, bool) and
            len(counts) == 2 and
            sum(counts.values()) != total):
        errors.append("%s carried_candidate_count + fresh_candidate_count "
                      "must equal accepted_candidate_count" % label)
    if (counts.get("carried_candidate_count", 0) > 0 and
            baseline_protocol != BASELINE_CURRENT):
        errors.append("%s carried candidates require an exact-carry-v1 "
                      "baseline" % label)
    return errors
