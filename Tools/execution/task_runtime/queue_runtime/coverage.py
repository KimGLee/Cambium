"""Is the Coverage Ledger itself sound.

Record shape, dispositions, provenance of the materialized bytes, and drift
between a batch spec and what was materialized from it.
"""

import Tools.execution.planning.coverage_contract as coverage_contract
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.knowledge.metadata.vocabulary_contract as vocabulary_contract
from Tools.governance.standards.adoption_lineage_contract import (
    STANDARDS_ADOPTION_TOOL,
)

from Tools.execution.task_runtime.queue_runtime.canon import (
    BATCH_ID_RE,
    TERMINAL_STATES,
)
from Tools.execution.task_runtime.queue_runtime.primitives import nonempty_string
from Tools.execution.task_runtime.queue_runtime.repofs import repository_path_refusal
from Tools.execution.task_runtime.queue_runtime.work_spec import work_spec_binding_errors


COVERAGE_DISPOSITIONS = vocabulary_contract.COVERAGE_DISPOSITION_VALUES


COVERAGE_BATCH_SPEC_FIELDS = coverage_contract.COVERAGE_BATCH_SPEC_FIELDS


def reviewed_without_current_evidence(coverage):
    """Return pages whose ``reviewed`` status lacks its exact owner link.

    K02/01 makes ``reviewed`` evidence-bound.  The deterministic Coverage
    invariant is therefore not "some gate receipt exists": the non-empty
    ``last_reviewed`` owner record and ``gate_receipts`` must name the same
    Receipt.  The property-state validator separately proves that the named
    body is a current typed ``page_review_acceptance`` bound to this page and
    semantic fingerprint.
    """
    missing = []
    for page in (coverage or {}).get("pages") or []:
        if not isinstance(page, dict):
            continue
        if page.get("authoring_status") != "reviewed":
            continue
        receipts = page.get("gate_receipts")
        state = page.get("property_state")
        reviewed = state.get("last_reviewed") \
            if isinstance(state, dict) else None
        evidence = reviewed.get("evidence_receipt") \
            if isinstance(reviewed, dict) and reviewed.get("value") is not None \
            else None
        if (not isinstance(receipts, list) or
                not nonempty_string(evidence) or evidence not in receipts):
            path = page.get("path")
            if nonempty_string(path):
                missing.append(str(path))
    return sorted(missing)


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


def coverage_records(root, coverage, errors):
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
        errors.extend(coverage_contract.page_shape_errors(page, label))
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
        path_error_message = repository_path_refusal(
            root, path, must_exist=False)
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


def promoted_coverage_projection(runtime, path):
    """Project one promoted corpus target from an already-valid runtime.

    ``validate_runtime`` owns the Coverage-disposition, ``next_batch``, and
    Queue-manifest consistency predicates.  Corpus Planning only needs the
    resulting relation, so it consumes this read-only projection instead of
    reimplementing those predicates under a second owner.
    """
    coverage_rows = [
        row for row in (runtime.get("coverage") or {}).get("pages", [])
        if isinstance(row, dict) and row.get("path") == path
    ]
    if len(coverage_rows) != 1:
        return {
            "coverage_rows": tuple(coverage_rows),
            "coverage": None,
            "queue_item": None,
        }
    coverage = coverage_rows[0]
    next_batch = coverage.get("next_batch")
    queue_item = next((
        item for item in (runtime.get("queue") or {}).get(
            "required_queue", [])
        if isinstance(item, dict) and item.get("id") == next_batch
    ), None) if nonempty_string(next_batch) else None
    return {
        "coverage_rows": tuple(coverage_rows),
        "coverage": coverage,
        "queue_item": queue_item,
    }


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
