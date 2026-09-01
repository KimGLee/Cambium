"""Current-contract identity checks for immutable runtime history.

Historical objects use the same machine shape as current objects.  This
module never interprets retired producer or schema eras; an external archive
containing an older contract is outside the current Cambium runtime.
"""

from Tools.execution.task_runtime.queue_runtime.canon import SHA256_RE
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string


TERMINAL_PROOF_PROFILE_BINDING_FIELDS = (
    "profile_snapshot_sha256",
    "profile_contract_fingerprint",
    "profile_load_inputs_sha256",
    "repository_snapshot_sha256",
)


def accounted_upstream_revision_ids(progress, queue=None):
    """Return upstream identities frozen by the current runtime history."""
    revisions = set()
    if isinstance(queue, dict) and nonempty_string(
            queue.get("upstream_revision_id")):
        revisions.add(queue["upstream_revision_id"])
    if not isinstance(progress, dict):
        return revisions
    contract = progress.get("contract")
    if isinstance(contract, dict) and nonempty_string(
            contract.get("upstream_revision_id")):
        revisions.add(contract["upstream_revision_id"])
    records = progress.get("standards_adoptions")
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        for field in (
                "upstream_revision_id_before",
                "upstream_revision_id_after"):
            if nonempty_string(record.get(field)):
                revisions.add(record[field])
    return revisions


def historical_receipt_identity_errors(
        receipt, receipt_id, label, accounted,
        *, revision_field="upstream_revision_id"):
    """Require immutable history to use an accounted current identity."""
    if not isinstance(receipt, dict):
        return []
    revision = receipt.get(revision_field)
    if not nonempty_string(revision):
        return [
            "%s receipt %s has no %s" %
            (label, receipt_id, revision_field)
        ]
    if revision in accounted:
        return []
    return [
        "%s receipt %s claims %s=%r, which no Standards "
        "adoption record or live identity of this instance accounts for" %
        (label, receipt_id, revision_field, revision)
    ]


def terminal_proof_profile_binding_errors(receipt, receipt_id):
    """Validate the complete current Terminal Proof identity binding."""
    if not isinstance(receipt, dict):
        return []
    errors = []
    for field in TERMINAL_PROOF_PROFILE_BINDING_FIELDS:
        if not SHA256_RE.fullmatch(str(receipt.get(field))):
            errors.append(
                "complete Terminal Proof receipt %s lacks canonical %s" %
                (receipt_id, field)
            )
    return errors
