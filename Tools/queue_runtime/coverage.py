"""Is the Coverage Ledger itself sound.

Record shape, dispositions, provenance of the materialized bytes, and drift
between a batch spec and what was materialized from it.  The legacy
reviewed-era exception lives here too, next to the records it exempts, so
that its scope is readable rather than inferred.
"""

import contract_exception_policy
import coverage_contract
import runtime_state_contract
import vocabulary_contract

from queue_runtime.canon import (
    BATCH_ID_RE,
    STANDARDS_ADOPTION_TOOL,
    TERMINAL_STATES,
)
from queue_runtime.primitives import nonempty_string
from queue_runtime.repofs import _path_error
from queue_runtime.work_spec import work_spec_binding_errors


COVERAGE_DISPOSITIONS = vocabulary_contract.COVERAGE_DISPOSITION_VALUES


COVERAGE_BATCH_SPEC_FIELDS = coverage_contract.COVERAGE_BATCH_SPEC_FIELDS


def coverage_reviewed_era_exception(progress, queue, count):
    """Return the contract exception that currently covers ``count``, or None.

    K02/01 offers three dispositions for legacy `reviewed` records, and one
    of them -- carry them under an explicit exception with a stated end --
    had no machine carrier: the declaration lived in a revision's prose, no
    consumer could read it, and the candidate it was meant to answer came
    back every run.  Because activation requires a passing readiness gate,
    choosing the disposition the kernel offers wedged the queue.

    The carrier is the contract's `policy_exceptions` register (K13/02),
    written by the K13/06 Contract Amendment transaction, with
    `coverage.reviewed_era` in the closed policy registry.  Its `limit` is a
    ceiling on how many records may still claim an era they cannot produce,
    which is why the grant cannot hide new ones: the count only legitimately
    falls as batches re-review, and any record beyond the ceiling reports as
    a candidate exactly as before.  The stated end is the ceiling reaching
    the scope's end -- a task-scoped grant dies with the task.

    Returns ``(entry, reason)``: ``entry`` is the covering exception or
    None, and ``reason`` explains a near miss for the operator.
    """
    contract = (progress or {}).get("contract")
    entries = contract.get("policy_exceptions") if isinstance(
        contract, dict) else None
    if not isinstance(entries, list) or not entries:
        return None, None
    _policy, fingerprint, _errors = (
        contract_exception_policy.effective_coverage_policy())
    task_id = (queue or {}).get("task_id")
    stale = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("policy_id") != "coverage.reviewed_era":
            continue
        if entry.get("baseline_policy_fingerprint") != fingerprint:
            # Judged against policy bytes that are no longer the rule.
            stale = True
            continue
        if (entry.get("scope_kind") == "task" and
                entry.get("scope_ref") != task_id):
            continue
        limit = entry.get("limit")
        if isinstance(limit, bool) or not isinstance(limit, int):
            continue
        if count <= limit:
            return entry, None
        return None, (
            "%d record(s) exceed the %d the exception %s bounds" %
            (count, limit, entry.get("decision_id")))
    if stale:
        return None, ("an exception exists but was judged against a "
                      "superseded statement of the rule")
    return None, None


def unsupported_reviewed_records(coverage):
    """Return Coverage paths claiming `reviewed` with no evidence era.

    K02/01: the status carries the era of the evidence that earned it.  A
    record naming no `gate_receipts` is claiming an era it cannot produce, so
    a page reviewed under a superseded Standards version is indistinguishable
    from one reviewed under the current one.  Reported as candidates, never
    errors: in a corpus with legacy records the honest disposition is a
    declared migration, and a hard failure would wedge the instance out of
    the very replan that performs it.
    """
    unsupported = []
    for page in (coverage or {}).get("pages") or []:
        if not isinstance(page, dict):
            continue
        if page.get("authoring_status") != "reviewed":
            continue
        receipts = page.get("gate_receipts")
        if not isinstance(receipts, list) or not any(
                nonempty_string(value) for value in receipts):
            path = page.get("path")
            if nonempty_string(path):
                unsupported.append(str(path))
    return sorted(unsupported)


def coverage_provenance_errors(progress, queue, catalog, coverage_sha,
                                queue_sha):
    """Bind materialized Coverage bytes to a qualified canonical writer.

    Before the first Queue materialization, initial Coverage is an adopter
    input.  Afterwards its ordinary write paths are transactional, so the live
    bytes must occur as the after-image of a semantically qualified receipt.
    Generic Guidance remains an authorized control input.  Executable
    operational Amendments are different: register_amendment must bind their
    approved bytes and current state before downstream writers may consume
    them.  Queue retains its own revision, fingerprint, and transition chain.
    """
    items = queue.get("required_queue")
    pre_materialization = (
        isinstance(items, list) and not items and
        queue.get("queue_revision") == 1 and
        queue.get("state_revision") == 0 and
        progress.get("initial_queue_receipt") is None
    )
    if pre_materialization:
        return []

    allowed = {
        ("compile_queue", "queue_structure"),
        ("compile_queue", "queue_replan"),
        ("update_queue", "queue_transition"),
        ("update_task", "task_transition"),
        ("apply_amendment", "amendment_transaction"),
        ("apply_delta", "delta_apply"),
        (STANDARDS_ADOPTION_TOOL, "standards_adoption"),
        ("apply_contract_amendment", "contract_amendment"),
    }
    writers = []
    # Writer receipts live in one collision-checked managed namespace.  Some
    # transactions (notably apply_delta before the following close edge) have
    # no canonical field in which to store their ID yet, so provenance may use
    # any semantically qualified receipt in that namespace.  Canonical state
    # references remain validated separately by their owning contracts.
    for receipt_id, entry in catalog.items():
        receipt = entry[1]
        if ((receipt.get("tool"), receipt.get("check")) not in allowed or
                receipt.get("result") != "pass" or
                receipt.get("invalidated_by") is not None or
                receipt.get("task_id") != queue.get("task_id") or
                receipt.get("actor_role") != "integrator"):
            continue
        tool = receipt.get("tool")
        if (tool in ("apply_amendment", STANDARDS_ADOPTION_TOOL,
                     "apply_contract_amendment") and
                receipt.get("transaction_phase") != "commit"):
            continue
        # Historical after-images remain valid evidence for history, but they
        # cannot authorize restoration of an older Coverage file.  A current
        # Coverage writer must be anchored to the exact live Queue point.
        if tool in ("apply_amendment", STANDARDS_ADOPTION_TOOL):
            receipt_queue_sha = receipt.get("after_queue_sha256")
        elif tool == "apply_delta":
            receipt_queue_sha = receipt.get("required_queue_sha256")
        else:
            receipt_queue_sha = receipt.get("after_required_queue_sha256")
        if receipt_queue_sha != queue_sha:
            continue
        if tool == "apply_delta":
            batch_id = receipt.get("batch_id")
            item = next((candidate for candidate in
                         queue.get("required_queue", [])
                         if isinstance(candidate, dict) and
                         candidate.get("id") == batch_id), None)
            if (item is None or item.get("state") not in
                    runtime_state_contract.QUEUE_DELTA_BOUND_STATES or
                    item.get("delta_path") != receipt.get("delta_path") or
                    item.get("delta_sha256") != receipt.get("delta_sha256")):
                continue
        writers.append((receipt_id, receipt))

    errors = []
    # Coverage has no ordinary direct-write phase after materialization.  By
    # contrast, Progress intentionally accepts new Guidance/Amendment control
    # inputs before their transactional write-back, and Queue already has its
    # own revision/fingerprint/transition chain.  Applying a blanket current-
    # byte rule to those two files would make legitimate control input
    # impossible without inventing a second writer API.
    for label, field, live_sha in (
            ("Coverage", "after_coverage_sha256", coverage_sha),):
        if not any(receipt.get(field) == live_sha for _, receipt in writers):
            errors.append(
                "%s current bytes are not the after-image of a qualified "
                "canonical writer receipt" % label
            )
    return errors


def coverage_records(root, coverage, errors,
                     allow_legacy_missing_property=False):
    pages = coverage.get("pages")
    if not isinstance(pages, list):
        errors.append("Coverage pages must be an explicit list")
        return {}, {}
    records = {}
    assignments = {}
    for index, page in enumerate(pages):
        label = "Coverage pages[%d]" % index
        if not isinstance(page, dict):
            errors.append("%s must be a mapping" % label)
            continue
        errors.extend(coverage_contract.page_shape_errors(
            page, label,
            allow_legacy_missing_property=allow_legacy_missing_property))
        planning_only = coverage_contract.is_planning_page(page)
        core_fields = (
            "path", "coverage_disposition", "canonical_owner",
            "prerequisites", "batch", "next_batch", "deferred_reason",
            "reentry_condition",
        )
        missing = [field for field in core_fields if field not in page]
        if missing:
            errors.append("%s misses core field(s): %s" %
                          (label, ", ".join(missing)))
        path = page.get("path")
        if not nonempty_string(path):
            errors.append("%s path must be a non-empty string" % label)
            continue
        if path in records:
            errors.append("Coverage repeats object path %s" % path)
            continue
        path_error_message = _path_error(root, path, must_exist=False)
        if path_error_message:
            errors.append("%s path %r is unsafe: %s" % (label, path, path_error_message))
        records[path] = page
        disposition = page.get("coverage_disposition")
        if disposition not in COVERAGE_DISPOSITIONS:
            errors.append("%s coverage_disposition must be one of %s; found %r" %
                          (label, ", ".join(sorted(COVERAGE_DISPOSITIONS)),
                           disposition))
        if not nonempty_string(page.get("canonical_owner")):
            errors.append("%s canonical_owner must be a non-empty string" % label)
        list_fields = ["prerequisites"]
        if not planning_only:
            list_fields.append("gate_receipts")
        for field in list_fields:
            values = page.get(field)
            if (not isinstance(values, list) or
                    not all(nonempty_string(value) for value in values)):
                errors.append("%s %s must be an explicit string list" %
                              (label, field))
            elif len(values) != len(set(values)):
                errors.append("%s %s must not contain duplicates" %
                              (label, field))
        for field in ("batch", "next_batch", "deferred_reason",
                      "reentry_condition"):
            value = page.get(field)
            if value is not None and not nonempty_string(value):
                errors.append("%s %s must be null or a non-empty string" %
                              (label, field))
        if disposition in ("deferred", "excluded") and not nonempty_string(
                page.get("deferred_reason")):
            errors.append("%s %s disposition requires a reason or scope basis" %
                          (label, disposition))
        if disposition == "deferred" and not nonempty_string(
                page.get("reentry_condition")):
            errors.append("%s deferred disposition requires reentry_condition" %
                          label)
        batch_ids = []
        for key in sorted(coverage_contract.COVERAGE_REROUTE_FIELDS):
            value = page.get(key)
            if value is None or value == "":
                continue
            if not nonempty_string(value):
                errors.append("%s %s must be a string or null" % (label, key))
                continue
            if value not in batch_ids:
                batch_ids.append(value)
        assignments[path] = batch_ids
        if page.get("coverage_disposition") == "required" and not batch_ids:
            errors.append("Required Coverage object %s has no batch/next_batch assignment" %
                          path)
    return records, assignments


def coverage_batch_spec_errors(coverage, items_by_id):
    """Detect direct edits to canonical compiler inputs after materialization."""
    errors = []
    specs = coverage.get("batch_specs")
    if not isinstance(specs, list):
        return ["Coverage batch_specs must be an explicit list"]
    seen = set()
    field_map = {
        "family": "family",
        "source_route": "source_route",
        "execution_mode": "execution_mode",
        "depends_on": "depends_on",
        "confirmation_required": "confirmation_required",
        "work_spec_path": "work_spec_path",
        "work_spec_sha256": "work_spec_sha256",
    }
    for index, spec in enumerate(specs):
        label = "Coverage batch_specs[%d]" % index
        if not isinstance(spec, dict):
            errors.append("%s must be a mapping" % label)
            continue
        missing = sorted(COVERAGE_BATCH_SPEC_FIELDS - set(spec))
        extra = sorted(set(spec) - COVERAGE_BATCH_SPEC_FIELDS)
        if missing:
            errors.append("%s misses required field(s): %s" %
                          (label, ", ".join(missing)))
        if extra:
            errors.append("%s has unsupported field(s): %s" %
                          (label, ", ".join(extra)))
        errors.extend(work_spec_binding_errors(
            spec.get("work_spec_path"), spec.get("work_spec_sha256"),
            label,
        ))
        batch_id = spec.get("id")
        if not nonempty_string(batch_id) or not BATCH_ID_RE.fullmatch(batch_id):
            errors.append("%s id must be a valid batch id" % label)
            continue
        if batch_id in seen:
            errors.append("Coverage repeats batch spec %s" % batch_id)
            continue
        seen.add(batch_id)
        item = items_by_id.get(batch_id)
        if item is None:
            # Assignment reconciliation reports a current zero/unknown batch;
            # terminal history is allowed to omit its old spec, not vice versa.
            errors.append("Coverage batch spec %s has no Queue item" % batch_id)
            continue
        for spec_field, queue_field in field_map.items():
            if spec.get(spec_field) != item.get(queue_field):
                errors.append(
                    "Coverage batch spec %s %s=%r does not match Queue %r" %
                    (batch_id, spec_field, spec.get(spec_field),
                     item.get(queue_field)))
        order_hint = spec.get("order_hint")
        if (order_hint is not None and
                (not isinstance(order_hint, int) or isinstance(order_hint, bool) or
                 order_hint < 1)):
            errors.append("Coverage batch spec %s order_hint must be a positive "
                          "integer or null" % batch_id)
        elif order_hint is not None and order_hint != item.get("order"):
            errors.append(
                "Coverage batch spec %s order_hint=%r does not match Queue order=%r" %
                (batch_id, order_hint, item.get("order"))
            )
    for batch_id, item in items_by_id.items():
        if item.get("state") not in TERMINAL_STATES and batch_id not in seen:
            errors.append("non-terminal Queue item %s has no Coverage batch spec" %
                          batch_id)
    return errors
