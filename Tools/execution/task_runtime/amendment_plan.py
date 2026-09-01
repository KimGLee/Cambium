"""Public planning and validation contract for cross-ledger Amendments.

The functions here derive and validate Amendment plans and their deterministic
Coverage/Queue projections.  They do not authorize an Amendment, publish a
Receipt, acquire a writer lock, or write runtime state.
"""

import copy
import re

import Tools.execution.planning.coverage_contract as coverage_contract
import Tools.platform.common.kblib as kblib
import Tools.execution.planning.queue_replan as queue_replan
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
from Tools.platform.common.primitives import nonempty_string as _nonempty


SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


PLAN_PREFIX = runtime_paths.AMENDMENT_DELTA_ROOT
OPERATIONS = tuple(sorted(
    runtime_state_contract.AMENDMENT_OPERATIONS_BY_EXECUTION_CAPABILITY[
        runtime_state_contract.CROSS_LEDGER_AMENDMENT_CAPABILITY]))
PLAN_FIELDS = (
    "schema_version", "amendment_id", "operation", "affected_pages",
    "affected_batches", "scope_version_before", "scope_version_after",
    "queue_revision_before", "queue_revision_after",
    "state_revision_before", "state_revision_after",
    "coverage_proposal_path", "coverage_proposal_sha256", "cancel_batch_id",
)
AMENDMENT_BINDINGS = {
    field: field for field in PLAN_FIELDS
    if field not in ("schema_version", "amendment_id")
}


def _canonical_list(value, label):
    if (not isinstance(value, list) or
            not all(_nonempty(item) for item in value)):
        raise ValueError("%s must be an explicit string list" % label)
    if len(value) != len(set(value)):
        raise ValueError("%s must not contain duplicates" % label)
    if value != sorted(value):
        raise ValueError("%s must be sorted for deterministic matching" % label)
    return value


def validate_plan(plan):
    """Validate the closed cross-ledger Amendment plan contract."""
    missing = [field for field in PLAN_FIELDS if field not in plan]
    extra = sorted(set(plan) - set(PLAN_FIELDS))
    if missing:
        raise ValueError("plan misses field(s): %s" % ", ".join(missing))
    if extra:
        raise ValueError("plan has unsupported field(s): %s" % ", ".join(extra))
    if plan.get("schema_version") != 1:
        raise ValueError("plan schema_version must be 1")
    if not _nonempty(plan.get("amendment_id")):
        raise ValueError("plan amendment_id must be a non-empty string")
    if plan.get("operation") not in OPERATIONS:
        raise ValueError("plan operation must be one of %s" %
                         ", ".join(OPERATIONS))
    _canonical_list(plan.get("affected_pages"), "affected_pages")
    _canonical_list(plan.get("affected_batches"), "affected_batches")
    before_scope = plan.get("scope_version_before")
    after_scope = plan.get("scope_version_after")
    if not _nonempty(before_scope) or not _nonempty(after_scope):
        raise ValueError("scope versions must be non-empty strings")
    if (plan["operation"] in
            runtime_state_contract.SCOPE_PRESERVING_AMENDMENT_OPERATIONS and
            before_scope != after_scope):
        raise ValueError(
            "%s must preserve scope_version" % plan["operation"])
    if (plan["operation"] not in
            runtime_state_contract.SCOPE_PRESERVING_AMENDMENT_OPERATIONS and
            before_scope == after_scope):
        raise ValueError("a scope/cancel Amendment must change scope_version")
    for field in ("queue_revision_before", "queue_revision_after",
                  "state_revision_before", "state_revision_after"):
        value = plan.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("%s must be a non-negative integer" % field)
    if plan["queue_revision_before"] < 1:
        raise ValueError("queue_revision_before must be at least 1")
    expected_queue_after = plan["queue_revision_before"] + 1
    if plan["queue_revision_after"] != expected_queue_after:
        raise ValueError("queue_revision_after must increment by exactly one")
    if (plan["operation"] in
            runtime_state_contract.STATE_REVISION_PRESERVING_AMENDMENT_OPERATIONS):
        if plan["state_revision_after"] != plan["state_revision_before"]:
            raise ValueError("%s must preserve state_revision" %
                             plan["operation"])
        if (plan["operation"] in
                runtime_state_contract.CANCEL_ID_FORBIDDEN_AMENDMENT_OPERATIONS and
                plan.get("cancel_batch_id") is not None):
            raise ValueError("%s cancel_batch_id must be null" %
                             plan["operation"])
    else:
        cancel_id = plan.get("cancel_batch_id")
        if not _nonempty(cancel_id):
            raise ValueError("cancel-batch requires cancel_batch_id")
        if plan["affected_batches"] != [cancel_id]:
            raise ValueError(
                "cancel-batch affected_batches must contain only cancel_batch_id")
        if plan["state_revision_after"] != plan["state_revision_before"] + 1:
            raise ValueError(
                "cancel-batch state_revision_after must increment by one")
    if not _nonempty(plan.get("coverage_proposal_path")):
        raise ValueError(
            "coverage_proposal_path must be a non-empty string")
    if not SHA256_RE.fullmatch(
            str(plan.get("coverage_proposal_sha256", ""))):
        raise ValueError(
            "coverage_proposal_sha256 must be sha256:<64 lowercase hex>")


def records_by_id(values, field, label):
    """Return a unique identity map for a closed list of records."""
    if not isinstance(values, list):
        raise ValueError("%s must be an explicit list" % label)
    result = {}
    for index, value in enumerate(values):
        if not isinstance(value, dict) or not _nonempty(value.get(field)):
            raise ValueError("%s[%d] must have %s" % (label, index, field))
        key = value[field]
        if key in result:
            raise ValueError("%s repeats %s %s" % (label, field, key))
        result[key] = value
    return result


def _changed_keys(before, after):
    return sorted(key for key in set(before).union(after)
                  if before.get(key) != after.get(key))


def _changed_gap_pages(current, proposal):
    changed_entries = set()
    for coverage, side in ((current, "current"), (proposal, "proposal")):
        gaps = coverage.get("open_gaps")
        if not isinstance(gaps, list):
            raise ValueError(
                "%s Coverage open_gaps must be an explicit list" % side)
        encoded = []
        for index, gap in enumerate(gaps):
            if not isinstance(gap, dict) or not _nonempty(gap.get("page")):
                raise ValueError(
                    "%s Coverage open_gaps[%d] must name page" %
                    (side, index))
            encoded.append((kblib.canonical_yaml({"gap": gap}), gap["page"]))
        if len(encoded) != len({entry[0] for entry in encoded}):
            raise ValueError(
                "%s Coverage repeats an identical open gap" % side)
        if side == "current":
            current_entries = dict(encoded)
        else:
            proposal_entries = dict(encoded)
    for key in set(current_entries).symmetric_difference(proposal_entries):
        changed_entries.add(current_entries.get(key) or proposal_entries[key])
    return changed_entries


def validate_coverage_proposal(current, proposal, plan):
    """Validate and return the exact cross-ledger Coverage change set."""
    if proposal.get("schema_version") != 2:
        raise ValueError("Coverage proposal schema_version must be 2")
    for field in kblib.RECEIPT_IDENTITY_FIELDS:
        if proposal.get(field) != current.get(field):
            raise ValueError("Coverage proposal may not change %s" % field)
    if current.get("scope_version") != plan["scope_version_before"]:
        raise ValueError("current Coverage scope_version does not match plan")
    if proposal.get("scope_version") != plan["scope_version_after"]:
        raise ValueError("Coverage proposal scope_version does not match plan")
    unexpected = sorted(
        field for field in (set(current).union(proposal)) -
        coverage_contract.COVERAGE_TOP_LEVEL_FIELDS
        if current.get(field) != proposal.get(field)
    )
    if unexpected:
        raise ValueError(
            "Coverage proposal contains unsupported top-level field(s): %s" %
            ", ".join(unexpected))
    if proposal.get("maintenance_candidates") != current.get(
            "maintenance_candidates"):
        raise ValueError(
            "scope/disposition Amendment may not rewrite "
            "maintenance_candidates")
    current_pages = records_by_id(
        current.get("pages"), "path", "Coverage pages")
    proposed_pages = records_by_id(
        proposal.get("pages"), "path", "Coverage proposal pages")
    changed_pages = sorted(set(
        _changed_keys(current_pages, proposed_pages)).union(
            _changed_gap_pages(current, proposal)))
    if changed_pages != plan["affected_pages"]:
        raise ValueError(
            "affected_pages does not exactly match Coverage changes; "
            "found=%r expected=%r" %
            (changed_pages, plan["affected_pages"]))
    current_specs = records_by_id(
        current.get("batch_specs"), "id", "Coverage batch_specs")
    proposed_specs = records_by_id(
        proposal.get("batch_specs"), "id", "Coverage proposal batch_specs")
    changed_specs = _changed_keys(current_specs, proposed_specs)
    return current_pages, proposed_pages, changed_specs


def structural_changes(before_queue, compiled_queue):
    """Return Queue ids whose closed structural projection changes."""
    before = records_by_id(
        before_queue.get("required_queue"), "id", "Required Queue")
    after = records_by_id(
        compiled_queue.get("required_queue"), "id",
        "compiled Required Queue")
    changed = []
    for item_id in sorted(set(before).union(after)):
        left = before.get(item_id)
        right = after.get(item_id)
        if (right is None and left is not None and
                left.get("state") in
                runtime_state_contract.QUEUE_TERMINAL_STATES):
            continue
        if left is None or right is None or any(
                left.get(field) != right.get(field)
                for field in queue_replan.STRUCTURAL_FIELDS):
            changed.append(item_id)
    return changed


def project_cancelled_queue(queue, plan, now, transition_receipt):
    """Project a validated leaf-batch cancellation without writing it."""
    result = copy.deepcopy(queue)
    items = records_by_id(
        result.get("required_queue"), "id", "Required Queue")
    item_id = plan["cancel_batch_id"]
    item = items.get(item_id)
    if item is None:
        raise ValueError("cancel_batch_id %s is absent from Queue" % item_id)
    cancellation_edges = \
        runtime_state_contract.BATCH_TRANSITIONS_BY_CAPABILITY[
            runtime_state_contract.AMENDMENT_BATCH_CANCELLATION_CAPABILITY]
    if (item.get("state"), "cancelled") not in cancellation_edges:
        raise ValueError("cancel-batch requires a queued/open batch")
    dependents = sorted(
        other_id for other_id, other in items.items()
        if item_id in (other.get("depends_on") or []))
    if dependents:
        raise ValueError(
            "cancel-batch requires a leaf batch; depended on by %s" %
            ", ".join(dependents))
    history = item.get("transition_receipts")
    if history is None:
        history = []
    if not isinstance(history, list):
        raise ValueError(
            "cancelled batch transition_receipts must be a list")
    item["state"] = "cancelled"
    item["hold_state"] = "none"
    item.pop("hold_reason", None)
    item["cancelled_at"] = now
    item["cancellation_amendment"] = plan["amendment_id"]
    item["transition_receipts"] = history + [transition_receipt["receipt_id"]]
    result["scope_version"] = plan["scope_version_after"]
    result["queue_revision"] = plan["queue_revision_after"]
    result["state_revision"] = plan["state_revision_after"]
    return result, item
