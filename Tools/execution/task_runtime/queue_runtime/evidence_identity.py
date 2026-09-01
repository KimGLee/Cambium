"""Under which identity policy may a receipt stand as evidence.

A receipt is not evidence in general; it is evidence for one use.  The four
uses -- current authorization, active transaction, completed event, terminal
history -- differ in what they demand of the receipt's own identity and in
which live owner-state pointer the field must currently name.  Keeping the
policy table beside the check that reads it is what stops a fifth use from
being invented at a call site.

``evidence_identity_errors`` and ``property_receipt_utc_date`` are offered
deliberately: ``metadata_gate_runtime`` validates a persisted typed Gate
receipt by the identical identity policy, and the alternative to a declared
promise here is that module reading a private name.
"""

import Tools.knowledge.metadata.metadata_property_state as metadata_property_state
import Tools.governance.profile.profile_contract as profile_contract

from Tools.execution.task_runtime.queue_runtime.canon import SHA256_RE
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string


EVIDENCE_USE_CURRENT_AUTHORIZATION = "current-authorization"
EVIDENCE_USE_ACTIVE_TRANSACTION = "active-transaction"
EVIDENCE_USE_COMPLETED_EVENT = "completed-event"
EVIDENCE_USE_TERMINAL_HISTORY = "terminal-history"
EVIDENCE_IDENTITY_USES = frozenset((
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
    EVIDENCE_USE_COMPLETED_EVENT,
    EVIDENCE_USE_TERMINAL_HISTORY,
))
LIVE_IDENTITY_USES = frozenset((
    EVIDENCE_USE_CURRENT_AUTHORIZATION,
    EVIDENCE_USE_ACTIVE_TRANSACTION,
))


def current_property_receipt(catalog, receipt_id, label, errors):
    """Resolve one live owner-state pointer without consulting history.

    ``catalog`` is the adoption-filtered hot view assembled by
    :func:`validate_runtime`.  Looking up the mapping directly is important:
    the historical/sealed resolver is valid for current-contract history, but
    a current owner property may not silently promote an invalidated receipt
    back into live authority.
    """
    if not nonempty_string(receipt_id):
        errors.append("%s evidence_receipt must be a non-empty string" % label)
        return None
    entry = catalog.get(receipt_id)
    if not isinstance(entry, tuple) or len(entry) != 2 or not isinstance(
            entry[1], dict):
        errors.append(
            "%s evidence receipt %s is absent from the current receipt "
            "catalog" % (label, receipt_id))
        return None
    receipt = entry[1]
    if receipt.get("receipt_id") != receipt_id:
        errors.append(
            "%s evidence receipt catalog key differs from its record" %
            label)
        return None
    return receipt


def property_receipt_utc_date(receipt, label, errors):
    try:
        return metadata_property_state.receipt_utc_date(receipt)
    except ValueError as exc:
        errors.append("%s %s" % (label, exc))
        return None


def evidence_identity_errors(
        receipt, label, *, use, profile_view=None,
        metadata_contract_fingerprint=None, profile_bound=True):
    """Apply the one Profile/metadata identity policy for evidence use.

    Current authorization and an active transaction must match the live
    Profile and metadata implementation.  A completed event and terminal
    history keep the canonical identity their producer observed and are never
    reinterpreted through today's bytes.  Every caller must choose one of
    these four lifecycle meanings explicitly; adding another ad-hoc
    live-fingerprint comparison would recreate the upgrade deadlock this
    boundary exists to prevent.
    """
    errors = []
    if use not in EVIDENCE_IDENTITY_USES:
        return ["%s has unsupported evidence identity use %r" % (label, use)]
    if profile_bound:
        if not nonempty_string(receipt.get("selected_profile_manifest")):
            errors.append(
                "%s has no selected_profile_manifest" % label)
        for field in \
                profile_contract.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS:
            value = receipt.get(field)
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append(
                    "%s has invalid %s" % (label, field))
    fingerprint = receipt.get("metadata_execution_contract_fingerprint")
    if (not isinstance(fingerprint, str) or
            not SHA256_RE.fullmatch(fingerprint)):
        errors.append(
            "%s has invalid metadata execution fingerprint" %
            label)
    if use in LIVE_IDENTITY_USES:
        if profile_bound:
            if not isinstance(profile_view, dict):
                errors.append("%s has no authorized live Profile view" % label)
                profile_view = {}
            for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS:
                expected = profile_view.get(field)
                if receipt.get(field) != expected:
                    errors.append(
                        "%s has %s=%r, expected authorized Profile value %r" %
                        (label, field, receipt.get(field), expected))
        if (not isinstance(metadata_contract_fingerprint, str) or
                not SHA256_RE.fullmatch(metadata_contract_fingerprint)):
            errors.append(
                "%s has no authorized live metadata execution fingerprint" %
                label)
        elif fingerprint != metadata_contract_fingerprint:
            errors.append(
                "%s metadata execution fingerprint is stale relative to "
                "the live contract" % label)
    return errors
