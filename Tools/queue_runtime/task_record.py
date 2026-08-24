"""The history-independent contract for one task-state transition receipt.

Shared verbatim by the live Progress validator and by historical
maintenance-predecessor replay.  One record shape, checked the same way in
both directions of time -- a replay that accepted a shape the live validator
refuses would let history contain states the present cannot produce.
"""

from queue_runtime.canon import SHA256_RE
from queue_runtime.primitives import (
    _nonempty_string,
    _valid_timestamp,
)
from queue_runtime.receipts import _require_receipt


TASK_LIFECYCLE_EDGES = frozenset((
    ("planned", "active"),
    ("planned", "paused"),
    ("planned", "blocked"),
    ("planned", "completion-candidate"),
    ("planned", "complete"),
    ("planned", "cancelled"),
    ("active", "paused"),
    ("active", "blocked"),
    ("active", "completion-candidate"),
    ("active", "complete"),
    ("active", "cancelled"),
    ("paused", "active"),
    ("paused", "blocked"),
    ("paused", "cancelled"),
    ("blocked", "active"),
    ("blocked", "paused"),
    ("blocked", "cancelled"),
    ("completion-candidate", "active"),
    ("completion-candidate", "paused"),
    ("completion-candidate", "blocked"),
    ("completion-candidate", "complete"),
    ("completion-candidate", "cancelled"),
))
FINAL_CONTROL_STATUSES = frozenset((
    "verified", "deferred", "superseded", "not-applicable",
    # K13/06: a withdrawn operational Amendment is final — it authorizes
    # nothing and is never resumed, so it raises no reconcile obligation.
    "withdrawn",
))


def _pending_control_ids(progress):
    """Return pending Guidance and Amendment identifiers for resume/terminal gates."""
    pending_guidance = []
    guidance = progress.get("guidance_queue")
    if isinstance(guidance, list):
        for index, entry in enumerate(guidance):
            if (not isinstance(entry, dict) or
                    entry.get("status") not in FINAL_CONTROL_STATUSES):
                pending_guidance.append(str(
                    entry.get("guidance_id") if isinstance(entry, dict) else
                    "#%d" % index))
    pending_amendments = []
    amendments = progress.get("amendments")
    if isinstance(amendments, list):
        for index, entry in enumerate(amendments):
            if not isinstance(entry, dict):
                pending_amendments.append("#%d" % index)
                continue
            status = entry.get("status")
            if (status not in FINAL_CONTROL_STATUSES or
                    (status == "verified" and
                     entry.get("writeback_done") is not True)):
                pending_amendments.append(str(entry.get("id") or "#%d" % index))
    return pending_guidance, pending_amendments


def _last_reconciled_guidance_id(progress):
    """Derive the incremental guidance boundary named by K00/10 and K12/04.

    K13/07 keeps Pending/reconciled Guidance in Progress but forbids Progress
    holding a second authority for anything the owned records already
    determine.  ``last_reconciled_guidance_id`` is exactly such a value: it is
    the last entry of the longest recorded prefix that has left ``received``,
    so it is a projection of ``guidance_queue`` rather than an independently
    editable cursor.  ``guidance_id`` is task-local and monotonically
    increasing (K13/06), and no status transition returns to ``received``, so
    the projection never moves backwards.  Batch-close reconciliation still
    carries the existing open items separately (K12/04); this boundary only
    bounds what is *new*.
    """
    guidance = progress.get("guidance_queue")
    if not isinstance(guidance, list):
        return None
    boundary = None
    for entry in guidance:
        if not isinstance(entry, dict) or entry.get("status") == "received":
            break
        entry_id = entry.get("guidance_id")
        if not _nonempty_string(entry_id):
            break
        boundary = entry_id
    return boundary


def _task_transition_receipt_record_errors(
        catalog, receipt_id, receipt, completion_semantics,
        *, expected_contract_sha=None):
    """Validate the canonical, history-independent transition fields.

    The live Progress validator and historical maintenance-predecessor
    validation share this exact record contract.  History ordering and the
    live checkpoint remain the caller's responsibility; receipt shape, edge
    semantics, fingerprints, and evidence binding do not get a weaker
    historical substitute.
    """
    errors = []
    before = receipt.get("before_task_state")
    after = receipt.get("after_task_state")
    if (before, after) not in TASK_LIFECYCLE_EDGES:
        errors.append("task transition receipt %s has illegal edge %r -> %r" %
                      (receipt_id, before, after))
    elif (completion_semantics == "build" and after == "complete" and
          before != "completion-candidate"):
        errors.append(
            "build task transition %s may not bypass completion-candidate" %
            receipt_id
        )
    elif (completion_semantics == "maintenance" and
          "completion-candidate" in (before, after)):
        errors.append(
            "maintenance task transition %s may not enter or leave "
            "completion-candidate" % receipt_id
        )
    elif (completion_semantics == "maintenance" and after == "complete" and
          before not in ("planned", "active")):
        errors.append(
            "maintenance task transition %s must be planned/active -> "
            "complete" % receipt_id
        )
    checked_at = receipt.get("checked_at")
    if not _valid_timestamp(checked_at):
        errors.append("task transition receipt %s has invalid checked_at" %
                      receipt_id)
    for field in (
            "before_coverage_sha256", "after_coverage_sha256",
            "before_required_queue_sha256",
            "after_required_queue_sha256", "before_progress_sha256",
            "after_progress_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append("task transition receipt %s has invalid %s" %
                          (receipt_id, field))
    contract_sha = receipt.get("contract_sha256")
    if not isinstance(contract_sha, str) or not SHA256_RE.fullmatch(
            contract_sha):
        errors.append("task transition receipt %s has invalid "
                      "contract_sha256" % receipt_id)
    elif (expected_contract_sha is not None and
          contract_sha != expected_contract_sha):
        errors.append("task transition receipt %s does not bind the "
                      "Task Contract active at Queue revision %r" %
                      (receipt_id, receipt.get("queue_revision")))
    if receipt.get("before_coverage_sha256") != receipt.get(
            "after_coverage_sha256"):
        errors.append("task transition receipt %s must not mutate Coverage" %
                      receipt_id)
    if (isinstance(receipt.get("before_progress_sha256"), str) and
            isinstance(receipt.get("after_progress_sha256"), str) and
            receipt.get("before_progress_sha256") ==
            receipt.get("after_progress_sha256")):
        errors.append("task transition receipt %s must change Progress bytes" %
                      receipt_id)
    for field, minimum in (("queue_revision", 1),
                           ("queue_state_revision", 0)):
        value = receipt.get(field)
        if (not isinstance(value, int) or isinstance(value, bool) or
                value < minimum):
            errors.append("task transition receipt %s has invalid %s" %
                          (receipt_id, field))
    evidence = receipt.get("evidence_receipt")
    if after in ("completion-candidate", "complete"):
        if not _nonempty_string(evidence):
            errors.append("task transition %s requires evidence_receipt" %
                          receipt_id)
        else:
            _require_receipt(
                catalog, evidence, "task transition %s evidence" % receipt_id,
                errors,
            )
    return errors
