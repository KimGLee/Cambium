#!/usr/bin/env python3
"""Deterministically compile Required Queue structure from explicit Coverage data.

The compiler reads only declared Coverage assignments and top-level
``batch_specs``.  It does not inspect backlinks, page prose, or semantic
similarity.  By default it prints a proposal.  ``--apply`` materializes an
initial Queue; ``--apply-replan`` performs an Amendment-bound structural write
without rewriting lifecycle history.  A replan also re-derives its registered
change-class/authority binding from live state and the exact proposal bytes
under the shared writer lock.
"""

import copy
import os
import sys
import uuid

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.execution.task_runtime.amendment_policy as amendment_policy
import Tools.execution.planning.coverage_contract as coverage_contract
import Tools.execution.planning.queue_replan as queue_replan
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.knowledge.metadata.vocabulary_contract as vocabulary_contract
from Tools.platform.common import reporting

QUEUE_PATH = runtime_paths.QUEUE_PATH
COVERAGE_PATH = runtime_paths.COVERAGE_PATH
PROGRESS_PATH = runtime_paths.PROGRESS_PATH
REPLAN_PROPOSAL_PREFIX = runtime_paths.REPLAN_DELTA_ROOT
TOOL = queue_runtime.COMPILE_QUEUE_TOOL
TOOL_VERSION = queue_runtime.COMPILE_QUEUE_TOOL_VERSION
RECEIPT_TYPE_ID = "queue-materialization-receipt-v1"
RECEIPT_CHECKS = (
    "queue_structure", "queue_replan", "queue_replan_prepare",
    "queue_replan_abort",
)


def current_receipt_errors(record, *, root=None):
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=RECEIPT_CHECKS)
REPLAN_PAGE_FIELDS = coverage_contract.COVERAGE_REROUTE_FIELDS
COVERAGE_TOP_LEVEL_FIELDS = coverage_contract.COVERAGE_TOP_LEVEL_FIELDS
BATCH_SPEC_FIELDS = coverage_contract.COVERAGE_BATCH_SPEC_FIELDS


JSON_HELP = reporting.JSON_RECEIPT_HELP
_JSON_REPORTER = reporting.JsonReceiptCollector()


def _load(root, relative):
    path = kblib.managed_repository_path(
        root, relative, runtime_paths.STATE_ROOT,
        suffixes=(".yaml",), must_exist=True,
    )
    return path, kblib.load_yaml_file(path)


def _load_replan_proposal(root, relative):
    path = kblib.managed_repository_path(
        root, relative, REPLAN_PROPOSAL_PREFIX,
        suffixes=(".coverage.yaml",), must_exist=True,
    )
    raw = kblib.read_text(path)
    proposal = kblib.parse_yaml_subset(raw)
    if not isinstance(proposal, dict):
        raise ValueError("Coverage proposal must be a top-level mapping")
    return path, raw, proposal


def _records_by_path(pages, label):
    if not isinstance(pages, list):
        raise ValueError("%s pages must be a list" % label)
    result = {}
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError("%s pages[%d] must be a mapping" % (label, index))
        path = page.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("%s pages[%d] has no path" % (label, index))
        if path in result:
            raise ValueError("%s repeats page path %s" % (label, path))
        result[path] = page
    return result


def validate_same_scope_proposal(current, proposal):
    """Return exact changed page paths for a structural-only Coverage proposal.

    A same-scope replan may replace ``batch_specs`` and the explicit
    ``batch``/``next_batch`` routing on already-Required objects.  It may not
    add/remove objects, change their disposition or metadata, change gaps, or
    change any identity/scope field.  Those changes belong to
    ``apply_amendment.py`` instead.
    """
    if proposal.get("schema_version") != 2:
        raise ValueError("Coverage proposal schema_version must be 2")
    for field in ("schema_version", "task_id", "scope_version",
                  "upstream_revision_id", "selected_profile_manifest"):
        if proposal.get(field) != current.get(field):
            raise ValueError("same-scope Coverage proposal may not change %s" %
                             field)
    unsupported = sorted(
        field for field in set(current).union(proposal)
        if field not in COVERAGE_TOP_LEVEL_FIELDS and
        current.get(field) != proposal.get(field)
    )
    if unsupported:
        raise ValueError("Coverage proposal changes unsupported top-level "
                         "field(s): %s" % ", ".join(unsupported))
    if proposal.get("open_gaps") != current.get("open_gaps"):
        raise ValueError("same-scope Coverage proposal may not change open_gaps")
    if proposal.get("maintenance_candidates") != current.get(
            "maintenance_candidates"):
        raise ValueError(
            "same-scope Coverage proposal may not change maintenance_candidates"
        )

    current_pages = _records_by_path(current.get("pages"), "current Coverage")
    proposed_pages = _records_by_path(proposal.get("pages"), "Coverage proposal")
    if set(current_pages) != set(proposed_pages):
        added = sorted(set(proposed_pages) - set(current_pages))
        removed = sorted(set(current_pages) - set(proposed_pages))
        raise ValueError("same-scope Coverage proposal may not add/remove pages; "
                         "added=%r removed=%r" % (added, removed))
    changed_pages = []
    for path in sorted(current_pages):
        before = current_pages[path]
        after = proposed_pages[path]
        changed_fields = sorted(
            field for field in set(before).union(after)
            if before.get(field) != after.get(field)
        )
        forbidden = [field for field in changed_fields
                     if field not in REPLAN_PAGE_FIELDS]
        if forbidden:
            raise ValueError("same-scope Coverage proposal changes %s on %s; "
                             "only batch/next_batch may change" %
                             (", ".join(forbidden), path))
        if changed_fields:
            if (before.get("coverage_disposition") != "required" or
                    after.get("coverage_disposition") != "required"):
                raise ValueError("same-scope routing may change only Required "
                                 "Coverage objects: %s" % path)
            changed_pages.append(path)
    # Parse and validate batch_specs even before compilation so a proposal
    # with no structural Queue diff cannot smuggle malformed compiler input.
    _batch_specs(proposal)
    return changed_pages


def _batch_specs(coverage):
    raw_specs = coverage.get("batch_specs")
    if not isinstance(raw_specs, list):
        raise ValueError("Coverage batch_specs must be an explicit list")
    specs = {}
    for index, spec in enumerate(raw_specs):
        label = "Coverage batch_specs[%d]" % index
        if not isinstance(spec, dict):
            raise ValueError("%s must be a mapping" % label)
        missing = sorted(BATCH_SPEC_FIELDS - set(spec))
        extra = sorted(set(spec) - BATCH_SPEC_FIELDS)
        if missing:
            raise ValueError("%s misses required field(s): %s" %
                             (label, ", ".join(missing)))
        if extra:
            raise ValueError("%s has unsupported field(s): %s" %
                             (label, ", ".join(extra)))
        batch_id = spec.get("id")
        if not isinstance(batch_id, str) or not batch_id:
            raise ValueError("%s has no id" % label)
        if batch_id in specs:
            raise ValueError("Coverage repeats batch spec %s" % batch_id)
        family = spec.get("family")
        mode = spec.get("execution_mode")
        source_route = spec.get("source_route")
        confirmation = spec.get("confirmation_required")
        dependencies = spec.get("depends_on")
        order_hint = spec.get("order_hint")
        work_spec_path = spec.get("work_spec_path")
        work_spec_sha256 = spec.get("work_spec_sha256")
        if not isinstance(family, str) or not family:
            raise ValueError("%s family must be a non-empty string" % batch_id)
        if mode not in runtime_state_contract.EXECUTION_MODES:
            raise ValueError("%s execution_mode must be concurrent-worker or "
                             "serial-integrator" % batch_id)
        if source_route is not None and not isinstance(source_route, str):
            raise ValueError("%s source_route must be string or null" % batch_id)
        if not isinstance(confirmation, bool):
            raise ValueError("%s confirmation_required must be explicit boolean" %
                             batch_id)
        if not isinstance(dependencies, list) or not all(
                isinstance(dep, str) and dep for dep in dependencies):
            raise ValueError("%s depends_on must be an explicit string list" %
                             batch_id)
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("%s repeats a batch dependency" % batch_id)
        if order_hint is not None and (not isinstance(order_hint, int) or
                                       isinstance(order_hint, bool) or
                                       order_hint < 1):
            raise ValueError("%s order_hint must be a positive integer or null" %
                             batch_id)
        work_spec_errors = queue_runtime.work_spec_binding_errors(
            work_spec_path, work_spec_sha256, label)
        if work_spec_errors:
            raise ValueError("; ".join(work_spec_errors))
        specs[batch_id] = (
            family, source_route, mode, confirmation,
            tuple(dependencies), order_hint, work_spec_path,
            work_spec_sha256,
        )
    return specs


def _build_groups(coverage, terminal_history_ids=(), allow_empty=False):
    pages = coverage.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Coverage pages must be a list")
    specs = _batch_specs(coverage)
    terminal_history_ids = set(terminal_history_ids)
    groups = {}
    seen_paths = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError("Coverage pages[%d] must be a mapping" % index)
        path = page.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Coverage pages[%d] has no path" % index)
        if path in seen_paths:
            raise ValueError("Coverage repeats path %s" % path)
        seen_paths.add(path)
        if page.get("coverage_disposition") != "required":
            continue
        batch_bindings = []
        seen_batch_ids = set()
        for key in sorted(REPLAN_PAGE_FIELDS):
            value = page.get(key)
            if (isinstance(value, str) and value and
                    value not in seen_batch_ids):
                batch_bindings.append((key, value))
                seen_batch_ids.add(value)
        if not batch_bindings:
            raise ValueError("Required Coverage object %s has no explicit batch/next_batch" %
                             path)
        for binding, batch_id in batch_bindings:
            if batch_id not in specs:
                if binding == "batch" and batch_id in terminal_history_ids:
                    # ``batch`` may retain the immutable terminal owner while
                    # ``next_batch`` names the current proposal. Terminal
                    # history does not need a current batch_specs entry.
                    continue
                raise ValueError("Required Coverage object %s references batch %s "
                                 "without a top-level batch_specs entry" %
                                 (path, batch_id))
            priority = vocabulary_contract.PRIORITY_ORDER.get(
                page.get("priority"), 99)
            group = groups.setdefault(batch_id, {
                "config": specs[batch_id], "manifest": [], "priority": priority,
            })
            group["manifest"].append(path)
            group["priority"] = min(group["priority"], priority)
    if not groups and not allow_empty:
        raise ValueError("Coverage contains no Required objects to compile")
    unused = sorted(set(specs) - set(groups))
    if unused:
        raise ValueError("batch_specs contains zero-record batch(es): %s" %
                         ", ".join(unused))
    return groups


def _topological_order(groups, external_ids=()):
    # Existing terminal/in-flight ids may satisfy a proposal dependency, but a
    # proposal item cannot satisfy its own/cyclic edge merely because the same
    # id already exists in the Queue.
    external_ids = set(external_ids) - set(groups)
    for batch_id, group in groups.items():
        for dep in group["config"][4]:
            if dep == batch_id:
                raise ValueError("batch %s depends on itself" % batch_id)
            if dep not in groups and dep not in external_ids:
                raise ValueError("batch %s depends on unknown batch %s" %
                                 (batch_id, dep))
    remaining = set(groups)
    ordered = []
    while remaining:
        available = [batch_id for batch_id in remaining
                     if set(groups[batch_id]["config"][4]).issubset(
                         set(ordered).union(external_ids))]
        if not available:
            raise ValueError("explicit batch dependencies contain a cycle")
        available.sort(key=lambda batch_id: (
            groups[batch_id]["config"][5]
            if groups[batch_id]["config"][5] is not None else 10 ** 9,
            groups[batch_id]["priority"], batch_id,
        ))
        chosen = available[0]
        ordered.append(chosen)
        remaining.remove(chosen)
    return ordered


def _assign_replan_orders(queue, compiled):
    """Keep immutable/in-flight positions and order only movable proposal work.

    A non-empty Queue is historical state, while ``batch_specs`` is the current
    structural proposal.  Terminal items absent from that proposal remain in
    the final Queue.  Existing queued items that are still proposed, plus new
    items, are the only entries whose order may be assigned here.  Missing
    queued/in-flight items are retained for diff adjudication and make an apply
    fail later rather than disappearing implicitly.
    """
    existing_items = [item for item in queue.get("required_queue", [])
                      if isinstance(item, dict)]
    current = {item.get("id"): item for item in existing_items}
    proposed = {item.get("id"): item for item in compiled}
    all_ids = set(current).union(proposed)
    total = len(all_ids)

    # A queued item may move only while it remains in the current proposal.
    # All terminal and in-flight entries, and any missing queued entry awaiting
    # disposition, retain their exact historical position.
    fixed = {
        item_id: item for item_id, item in current.items()
        if not (item.get("state") == "queued" and item_id in proposed)
    }
    fixed_by_order = {}
    for item_id, item in fixed.items():
        order = item.get("order")
        if (not isinstance(order, int) or isinstance(order, bool) or
                order < 1 or order > total):
            raise ValueError("fixed Queue item %s has order %r outside 1..%d" %
                             (item_id, order, total))
        if order in fixed_by_order:
            raise ValueError("fixed Queue items %s and %s share order %d" %
                             (fixed_by_order[order], item_id, order))
        fixed_by_order[order] = item_id

    movable = set(proposed) - set(fixed)
    dependencies = {}
    for item_id in all_ids:
        source = proposed.get(item_id, current.get(item_id))
        raw = source.get("depends_on") if isinstance(source, dict) else None
        if not isinstance(raw, list):
            raise ValueError("Queue item %s depends_on must be a list" % item_id)
        unknown = sorted(set(raw) - all_ids)
        if unknown:
            raise ValueError("Queue item %s depends on missing batch(es): %s" %
                             (item_id, ", ".join(unknown)))
        dependencies[item_id] = set(raw)

    # Prefer work that must precede the earliest fixed item.  This avoids a
    # harmless order hint consuming the only slot needed by a fixed entry's
    # dependency, while retaining the compiler's stable proposal rank as the
    # tie-break for unconstrained work.
    fixed_deadline = {}
    for fixed_id, fixed_item in fixed.items():
        deadline = fixed_item["order"]
        stack = list(dependencies[fixed_id])
        seen = set()
        while stack:
            ancestor = stack.pop()
            if ancestor in seen:
                continue
            seen.add(ancestor)
            if ancestor in movable:
                fixed_deadline[ancestor] = min(
                    deadline, fixed_deadline.get(ancestor, total + 1))
            stack.extend(dependencies.get(ancestor, ()))

    proposal_rank = {
        item.get("id"): item.get("order", total + 1) for item in compiled
    }
    placed = set()
    assigned = {}
    remaining = set(movable)
    for position in range(1, total + 1):
        fixed_id = fixed_by_order.get(position)
        if fixed_id is not None:
            missing = sorted(dependencies[fixed_id] - placed)
            if missing:
                raise ValueError(
                    "fixed Queue item %s at order %d has dependency/dependencies "
                    "not ordered earlier: %s" %
                    (fixed_id, position, ", ".join(missing))
                )
            assigned[fixed_id] = position
            placed.add(fixed_id)
            continue
        available = [item_id for item_id in remaining
                     if dependencies[item_id].issubset(placed)]
        if not available:
            raise ValueError(
                "cannot assign contiguous Queue order without changing fixed history"
            )
        available.sort(key=lambda item_id: (
            fixed_deadline.get(item_id, total + 1),
            proposal_rank.get(item_id, total + 1), item_id,
        ))
        chosen = available[0]
        assigned[chosen] = position
        placed.add(chosen)
        remaining.remove(chosen)
    if remaining:
        raise ValueError("cannot order proposed Queue items: %s" %
                         ", ".join(sorted(remaining)))

    for item in compiled:
        item["order"] = assigned[item["id"]]
    return compiled


def _apply_explicit_successor_edges(groups, coverage):
    """Turn explicit Coverage batch -> next_batch handoffs into Queue edges."""
    predecessors = {}
    for page in coverage.get("pages", []):
        if not isinstance(page, dict) or page.get("coverage_disposition") != "required":
            continue
        batch = page.get("batch")
        successor = page.get("next_batch")
        if (isinstance(batch, str) and batch and isinstance(successor, str) and
                successor and successor != batch):
            predecessors.setdefault(successor, set()).add(batch)
    for successor, prior_ids in predecessors.items():
        if successor not in groups:
            raise ValueError("successor batch %s has no compiled group" % successor)
        if len(prior_ids) != 1:
            raise ValueError("successor batch %s has multiple predecessors; split or "
                             "adjudicate the relationship explicitly" % successor)
        predecessor = next(iter(prior_ids))
        dependencies = groups[successor]["config"][4]
        if predecessor not in dependencies:
            raise ValueError("successor batch %s must explicitly depend on %s in "
                             "batch_specs" % (successor, predecessor))
        groups[successor]["successor_of"] = predecessor


def compile_document(queue, coverage):
    existing = queue.get("required_queue")
    if not isinstance(existing, list):
        raise ValueError("existing required_queue must be a list")
    terminal_history_ids = {
        item.get("id") for item in existing
        if (isinstance(item, dict) and
            item.get("state") in
            runtime_state_contract.QUEUE_TERMINAL_STATES)
    }
    groups = _build_groups(
        coverage, terminal_history_ids, allow_empty=bool(existing))
    _apply_explicit_successor_edges(groups, coverage)
    existing_ids = {
        item.get("id") for item in queue.get("required_queue", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    order = _topological_order(groups, external_ids=existing_ids)
    compiled = []
    for position, batch_id in enumerate(order, 1):
        (family, source_route, mode, confirmation, dependencies, _,
         work_spec_path, work_spec_sha256) = \
            groups[batch_id]["config"]
        manifest = sorted(groups[batch_id]["manifest"])
        item = {
            "id": batch_id,
            "family": family,
            "order": position,
            "record_count": len(manifest),
            "manifest": manifest,
            "source_route": source_route,
            "execution_mode": mode,
            "depends_on": list(dependencies),
            "confirmation_required": confirmation,
            "work_spec_path": work_spec_path,
            "work_spec_sha256": work_spec_sha256,
            "state": "queued",
            "hold_state": "confirmation-required" if confirmation else "none",
        }
        if confirmation:
            item["hold_reason"] = "explicit confirmation is required before activation"
        if groups[batch_id].get("successor_of"):
            item["successor_of"] = groups[batch_id]["successor_of"]
        compiled.append(item)

    if queue.get("required_queue"):
        compiled = _assign_replan_orders(queue, compiled)

    result = copy.deepcopy(queue)
    existing_structure = []
    for item in existing:
        if not isinstance(item, dict):
            existing_structure.append(item)
            continue
        projected = {"id": item.get("id")}
        projected.update({field: copy.deepcopy(item.get(field))
                          for field in queue_replan.STRUCTURAL_FIELDS})
        existing_structure.append(projected)
    compiled_structure = []
    for item in compiled:
        projected = {"id": item.get("id")}
        projected.update({field: copy.deepcopy(item.get(field))
                          for field in queue_replan.STRUCTURAL_FIELDS})
        compiled_structure.append(projected)
    changed = existing_structure != compiled_structure
    result["queue_revision"] = result.get("queue_revision", 0) + 1
    result["required_queue"] = compiled
    return result, changed


def replan_diff(queue, proposal, base_sha):
    """Build a deterministic diff artifact without replacing lifecycle state."""
    current_items = {
        item["id"]: item for item in queue.get("required_queue", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    proposed_items = {
        item["id"]: item for item in proposal.get("required_queue", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    adds = []
    updates = []
    reorders = []
    removes = []
    conflicts = []
    stale_terminal_specs = []
    for item_id in sorted(proposed_items):
        proposed = proposed_items[item_id]
        current = current_items.get(item_id)
        structural = {field: copy.deepcopy(proposed.get(field))
                      for field in queue_replan.STRUCTURAL_FIELDS}
        if current is None:
            candidate = {"id": item_id, "initial_state": "queued"}
            candidate.update(structural)
            adds.append(candidate)
            continue
        changed_fields = queue_replan.changed_structural_fields(
            current, proposed)
        if changed_fields and current.get("state") in queue_runtime.TERMINAL_STATES:
            # Sealed item: the difference is between history and a stale spec
            # row, not a change anyone can apply.  Recorded, never proposed.
            stale_terminal_specs.append(item_id)
            continue
        if changed_fields:
            updates.append({
                "id": item_id,
                "current_state": current.get("state"),
                "changed_fields": changed_fields,
                "proposed_structure": structural,
            })
            work_spec_only = set(changed_fields).issubset(
                queue_replan.WORK_SPEC_FIELDS)
            open_spec_replan = (
                current.get("state") == "open" and work_spec_only and
                current.get("hold_state") == "revalidation-required"
            )
            if (current.get("state") == "open" and work_spec_only and
                    current.get("hold_state") != "revalidation-required"):
                conflicts.append(
                    "%s open Work Spec change requires a prior "
                    "update_queue transition to hold_state="
                    "revalidation-required" % item_id
                )
            elif current.get("state") in queue_runtime.TERMINAL_STATES:
                # K13/08 Batch Reference Settlement: a terminal batch keeps
                # its history and loses its live references.  Its Queue item
                # is sealed and its structure can never change again, so a
                # surviving batch_specs row is stale history, not a proposal
                # -- and recompiling it can produce a structure the sealed
                # item will never match (the 3.6.4 ownership transfer did
                # exactly that), wedging every later replan behind a conflict
                # no Amendment can resolve.  Absence of a terminal row is
                # already expected below; presence is now equally harmless
                # and reported for retirement instead of blocking.
                stale_terminal_specs.append(item_id)
            elif (current.get("state") != "queued" and
                  not open_spec_replan):
                conflicts.append(
                    "%s structure differs while state=%s; Amendment and successor-aware adjudication required"
                    % (item_id, current.get("state"))
                )
        if current.get("order") != proposed.get("order"):
            reorders.append({
                "id": item_id,
                "from_order": current.get("order"),
                "to_order": proposed.get("order"),
            })
    for item_id in sorted(set(current_items) - set(proposed_items)):
        current = current_items[item_id]
        if (current.get("state") in
                runtime_state_contract.QUEUE_TERMINAL_STATES):
            # batch_specs describes the current proposal, not immutable Queue
            # history.  Absence is therefore expected for terminal entries.
            continue
        removes.append({
            "id": item_id,
            "current_state": current.get("state"),
            "disposition": "blocked-amendment-required",
        })
        if current.get("state") == "queued":
            conflicts.append(
                "%s queued work is absent from the proposal; explicitly dispose it before replanning"
                % item_id
            )
        else:
            conflicts.append(
                "%s is absent from the proposal while state=%s; in-flight work cannot be removed"
                % (item_id, current.get("state"))
            )
    preserved = sorted(current_items,
                       key=lambda item_id: (current_items[item_id].get("order", 10 ** 9),
                                            item_id))
    preserved_closed = [item_id for item_id in preserved
                        if current_items[item_id].get("state") == "closed"]
    preserved_cancelled = [item_id for item_id in preserved
                           if current_items[item_id].get("state") == "cancelled"]
    preserved_inflight = [item_id for item_id in preserved
                          if current_items[item_id].get("state") in
                          runtime_state_contract.QUEUE_ACTIVE_STATES]
    has_changes = bool(adds or updates or reorders or removes)
    return {
        "schema_version": 1,
        "artifact_type": "required-queue-replan-diff",
        "task_id": queue.get("task_id"),
        "base_queue_revision": queue.get("queue_revision"),
        "base_state_revision": queue.get("state_revision"),
        "base_required_queue_sha256": base_sha,
        "proposed_queue_revision": (queue.get("queue_revision", 0) + 1
                                    if has_changes else queue.get("queue_revision")),
        "has_structural_changes": has_changes,
        "add_candidates": adds,
        "update_candidates": updates,
        "reorder_candidates": reorders,
        "remove_candidates": removes,
        "preserved_lifecycle_ids": preserved,
        "preserved_closed_ids": preserved_closed,
        "preserved_cancelled_ids": preserved_cancelled,
        "preserved_inflight_ids": preserved_inflight,
        "stale_terminal_spec_ids": sorted(stale_terminal_specs),
        "conflicts": conflicts,
    }


def _pending_replan_amendment(progress, amendment_id, queue, diff,
                              diff_text, proposal_path, proposal_sha,
                              affected_pages, impact):
    """Return one exact, approved authorization for this same-scope replan."""
    amendments = progress.get("amendments")
    if not isinstance(amendments, list):
        raise ValueError("Progress amendments must be an explicit list")
    matches = [entry for entry in amendments
               if isinstance(entry, dict) and entry.get("id") == amendment_id]
    if len(matches) != 1:
        raise ValueError("Progress must contain exactly one matching Amendment %s" %
                         amendment_id)
    amendment = matches[0]
    if not isinstance(amendment.get("approval_reference"), str) or not \
            amendment["approval_reference"].strip():
        raise ValueError(
            "Progress Amendment approval_reference must be non-empty")
    if not isinstance(amendment.get("registration_receipt"), str) or not \
            amendment["registration_receipt"].strip():
        raise ValueError(
            "Progress Amendment registration_receipt must be non-empty")
    expected = {
        "status": "approved",
        "writeback_done": False,
        "operation": "queue-replan",
        "coverage_proposal_path": proposal_path,
        "coverage_proposal_sha256": proposal_sha,
        "affected_pages": affected_pages,
        "affected_batches": queue_replan.changed_batch_ids(diff),
        "scope_version_before": queue.get("scope_version"),
        "scope_version_after": queue.get("scope_version"),
        "queue_revision_before": queue.get("queue_revision"),
        "queue_revision_after": queue.get("queue_revision", 0) + 1,
        "queue_state_revision_before": queue.get("state_revision"),
        "queue_state_revision_after": queue.get("state_revision"),
        "replan_diff_sha256": kblib.sha256_bytes(diff_text),
    }
    for field, value in expected.items():
        if amendment.get(field) != value:
            raise ValueError(
                "Progress Amendment %s does not bind current replan: "
                "%s=%r expected=%r" %
                (amendment_id, field, amendment.get(field), value)
            )
    amendment_policy.require_decision_binding(
        progress.get("contract") or {}, impact, amendment)
    return amendment


def _preflight_result(root, coverage, coverage_text, queue, queue_text,
                      progress, progress_text, authority,
                      pending_replan_receipt=None):
    """Validate proposed state against the transaction's immutable authority.

    A staged repository used to force a second Profile/K00 admission and could
    therefore validate a different revision from the transaction entry.  The
    runtime validator already supports byte-exact state overrides, so keep the
    real repository root and inject the one admitted view pair instead.
    """
    return runtime_validation.validate_runtime(
        root,
        state_overrides={
            COVERAGE_PATH: (coverage_text, coverage),
            QUEUE_PATH: (queue_text, queue),
            PROGRESS_PATH: (progress_text, progress),
        },
        extra_receipts=([pending_replan_receipt]
                        if pending_replan_receipt is not None else None),
        allow_pending_replan_receipts=(pending_replan_receipt is not None),
        **queue_runtime.runtime_authority_validation_kwargs(authority),
    )["errors"]


def _sync_progress(progress, queue, queue_text, amendment_id=None,
                   receipt_id=None, transaction_id=None,
                   coverage_sha=None, initial_queue_receipt=None):
    result = copy.deepcopy(progress)
    if not queue_runtime.nonempty_string(
            result.get("initial_task_plan_receipt")):
        raise ValueError(
            "Progress has no initial Task Plan Receipt for Queue "
            "materialization")
    retained_task_plan_receipt = result["initial_task_plan_receipt"]
    result["required_queue_path"] = QUEUE_PATH
    result["queue_revision"] = queue["queue_revision"]
    result["queue_state_revision"] = queue["state_revision"]
    result["required_queue_sha256"] = kblib.sha256_bytes(queue_text)
    if initial_queue_receipt is not None:
        if result.get("initial_queue_receipt") is not None:
            raise ValueError("Progress already records an initial Queue receipt")
        result["initial_queue_receipt"] = initial_queue_receipt
    if result.get("initial_task_plan_receipt") != retained_task_plan_receipt:
        raise ValueError(
            "Queue materialization may not replace initial Task Plan evidence")
    if amendment_id is not None:
        amendments = result.get("amendments")
        matches = [entry for entry in amendments
                   if isinstance(entry, dict) and entry.get("id") == amendment_id] \
            if isinstance(amendments, list) else []
        if len(matches) != 1:
            raise ValueError("cannot verify missing/duplicate Amendment %s" %
                             amendment_id)
        amendment = matches[0]
        amendment["status"] = "verified"
        amendment["writeback_done"] = True
        amendment["transaction_receipt_id"] = receipt_id
        amendment["transaction_id"] = transaction_id
        amendment["after_required_queue_sha256"] = \
            result["required_queue_sha256"]
        amendment["after_coverage_sha256"] = coverage_sha
    return result


def _restore_state(paths, before_text, names):
    failures = []
    for name in names:
        try:
            kblib.atomic_write_text(
                paths[name], before_text[name], validator=kblib.parse_yaml_subset)
        except Exception as exc:
            failures.append("%s restore: %s" % (name, exc))
    for name, path in paths.items():
        try:
            with open(path, encoding="utf-8") as fh:
                live = fh.read()
            if live != before_text[name]:
                failures.append("%s bytes differ after rollback" % name)
        except Exception as exc:
            failures.append("%s verification: %s" % (name, exc))
    return failures


def _commit_state(root, paths, before_text, after_text, write_names,
                  receipt_path, prepare_receipt, commit_receipt,
                  abort_receipt, operation, authority, lock_validator=None):
    """Publish one guarded state transaction and preserve crash evidence.

    Per-file replacement cannot be atomic across three files.  The shared
    lock records before/planned-after fingerprints; a durable prepare receipt
    precedes the first replacement.  An escaping failure leaves the lock
    unless every authoritative byte has been restored and verified.
    """
    operation = dict(operation)
    operation.update(queue_runtime.runtime_authority_lock_fields(authority))
    authority_kwargs = queue_runtime.runtime_authority_validation_kwargs(
        authority)
    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        with kblib.no_authoritative_write_guard(lease):
            for name, path in paths.items():
                with open(path, encoding="utf-8") as fh:
                    live = fh.read()
                if live != before_text[name]:
                    raise ValueError(
                        "%s changed after transaction planning" % name)
            locked = runtime_validation.validate_runtime(
                root, allow_unmaterialized_queue=True,
                **authority_kwargs,
            )
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            barrier = queue_runtime.delta_apply_write_barrier(
                locked, TOOL, operation.get("action"))
            if barrier:
                raise ValueError(barrier)
            queue_runtime.require_runtime_authority_current(
                root, authority, "runtime authority changed under lock")
            if lock_validator is not None:
                lock_validator(locked)
        outcomes = {
            "prepare": "not-attempted",
            "commit": "not-attempted",
            "abort": "not-attempted",
        }
        try:
            commit_before = kblib.receipt_append_observation(
                receipt_path, [commit_receipt]
            )
        except Exception:
            # The commit's absence cannot be proven, so any later failure must
            # retain the owner lock even if no state replacement occurs.
            commit_before = None
        try:
            if prepare_receipt is not None:
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed before prepare receipt")
                outcome, append_error, _ = kblib.write_receipts_observed(
                    receipt_path, _JSON_REPORTER.record([prepare_receipt])
                )
                outcomes["prepare"] = outcome
                if append_error is not None:
                    raise append_error
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed during prepare receipt")
            queue_runtime.require_runtime_authority_current(
                root, authority, "runtime authority changed before state write")
            for name in write_names:
                kblib.atomic_write_text(
                    paths[name], after_text[name],
                    validator=kblib.parse_yaml_subset,
                )
                queue_runtime.require_runtime_authority_current(
                    root, authority,
                    "runtime authority changed while writing %s" % name)
            postflight = runtime_validation.validate_runtime(
                root, extra_receipts=[commit_receipt],
                allow_pending_replan_receipts=True,
                **authority_kwargs,
            )["errors"]
            if postflight:
                raise ValueError("post-write check_queue failed: %s" %
                                 "; ".join(postflight))
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed before commit receipt")
            outcome, append_error, _ = kblib.write_receipts_observed(
                receipt_path, _JSON_REPORTER.record([commit_receipt]),
                before=commit_before
            )
            outcomes["commit"] = outcome
            if append_error is not None:
                raise append_error
            queue_runtime.require_runtime_authority_current(
                root, authority,
                "runtime authority changed during commit receipt")
            persisted = runtime_validation.validate_runtime(
                root, **authority_kwargs)["errors"]
            if persisted:
                raise ValueError("persisted transaction evidence failed "
                                 "check_queue: %s" % "; ".join(persisted))
        except Exception as exc:
            rollback_failures = _restore_state(
                paths, before_text, write_names)
            if outcomes["commit"] == "not-attempted":
                outcomes["commit"] = (
                    kblib.receipt_outcome_from(
                        receipt_path, [commit_receipt], commit_before
                    ) if commit_before is not None else "uncertain"
                )
            abort_error = None
            if (prepare_receipt is not None and
                    outcomes["prepare"] in ("present", "uncertain") and
                    abort_receipt is not None):
                abort_receipt["failure"] = str(exc)
                abort_receipt["rollback_failures"] = rollback_failures
                outcomes["abort"], abort_error, _ = (
                    kblib.write_receipts_observed(
                        receipt_path, _JSON_REPORTER.record([abort_receipt])
                    )
                )
            attempted = [
                value for value in outcomes.values()
                if value != "not-attempted"
            ]
            all_attempted_absent = (
                bool(attempted) and
                all(value == "absent" for value in attempted) and
                outcomes["commit"] == "absent"
            )
            handled_prepare_failure = (
                prepare_receipt is not None and
                outcomes["prepare"] == "present" and
                outcomes["abort"] == "present" and
                outcomes["commit"] == "absent"
            )
            receipt_recovery_closed = (
                all_attempted_absent or handled_prepare_failure
            )
            if rollback_failures or not receipt_recovery_closed:
                recovery = (
                    "receipt outcomes prepare=%s commit=%s abort=%s" %
                    (outcomes["prepare"], outcomes["commit"],
                     outcomes["abort"])
                )
                if abort_error is not None:
                    recovery += "; abort append: %s" % abort_error
                suffix = (("; " + "; ".join(rollback_failures))
                          if rollback_failures else "")
                raise ValueError(
                    "transaction failed and recovery was incomplete: %s; %s%s" %
                    (exc, recovery, suffix))
            lease.mark_reconciled()
            raise


def main(argv=None):
    parser = kblib.ArgumentParser(description="Compile Required Queue from explicit Coverage assignments")
    parser.add_argument("root", help="adopting repository root")
    parser.add_argument("--output", help="repository-relative proposal path")
    write_mode = parser.add_mutually_exclusive_group()
    write_mode.add_argument("--apply", action="store_true",
                            help="materialize an initially empty Queue")
    write_mode.add_argument("--apply-replan", action="store_true",
                            help="apply a controlled structural diff to a non-empty Queue")
    parser.add_argument(
        "--coverage-proposal",
        help="repository-contained %s/*.coverage.yaml input" %
        runtime_paths.REPLAN_DELTA_ROOT,
    )
    parser.add_argument("--replan-diff",
                        help="existing %s/*.yaml diff to consume" %
                        runtime_paths.TRANSIENT_ROOT)
    parser.add_argument("--amendment-id",
                        help="registered Amendment id authorizing the replan; "
                             "required with --apply-replan")
    parser.add_argument("--expected-queue-revision", type=int,
                        help="compare-and-swap guard: the queue_revision the "
                             "caller read from the current Queue; the write is "
                             "refused when the live value differs")
    parser.add_argument("--expected-state-revision", type=int,
                        help="compare-and-swap guard: the state_revision the "
                             "caller read from the current Queue; the replan "
                             "is refused when the live value differs")
    parser.add_argument("--expected-sha256",
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Queue; the write is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-coverage-sha256",
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Coverage; the replan is "
                             "refused when the live bytes differ")
    parser.add_argument("--expected-progress-sha256",
                        help="compare-and-swap guard: sha256:<hex> the caller "
                             "read from the current Progress; the replan is "
                             "refused when the live bytes differ")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker",
                        help="declared caller role; only integrator may apply "
                             "a Queue write or replan")
    parser.add_argument("--receipts",
                        default=runtime_paths.QUEUE_STRUCTURE_RECEIPT_PATH,
                        help="receipt JSONL path under %s" %
                        runtime_paths.RECEIPT_ROOT)
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    args = parser.parse_args(argv)
    if not args.json:
        return _run(args)
    return _JSON_REPORTER.run(lambda: _run(args))


def _run(args):
    """This tool's own run; `main` above owns only argument parsing."""
    root = os.path.realpath(os.path.abspath(args.root))
    try:
        queue_path, queue = _load(root, QUEUE_PATH)
        coverage_path, coverage = _load(root, COVERAGE_PATH)
        progress_path, progress = _load(root, PROGRESS_PATH)
        with open(queue_path, encoding="utf-8") as fh:
            old_queue_text = fh.read()
        with open(coverage_path, encoding="utf-8") as fh:
            coverage_text = fh.read()
        with open(progress_path, encoding="utf-8") as fh:
            old_progress_text = fh.read()
        current_sha = kblib.sha256_bytes(old_queue_text)
        current_coverage_sha = kblib.sha256_bytes(coverage_text)
        current_progress_sha = kblib.sha256_bytes(old_progress_text)
        existing = queue.get("required_queue") or []
        current_validation = runtime_validation.validate_runtime(
            root, allow_unmaterialized_queue=not bool(
                queue.get("required_queue")
            ),
        )
        if current_validation["errors"]:
            raise ValueError("current runtime state is inconsistent: %s" %
                             "; ".join(current_validation["errors"]))
        authority = queue_runtime.runtime_authority_context(current_validation)
        if args.apply or args.apply_replan:
            barrier = queue_runtime.delta_apply_write_barrier(
                current_validation, TOOL,
                "apply-replan" if args.apply_replan else "initial-compile",
            )
            if barrier:
                raise ValueError(barrier)
        proposal_coverage_path = None
        proposal_coverage_file = None
        proposal_coverage_text = coverage_text
        proposal_coverage = coverage
        proposal_coverage_sha = current_coverage_sha
        affected_pages = []
        amendment_impact = None
        if existing:
            if not args.coverage_proposal:
                raise ValueError(
                    "a non-empty Queue requires --coverage-proposal inside "
                    "%s/; never pre-edit canonical Coverage" %
                    runtime_paths.REPLAN_DELTA_ROOT)
            proposal_coverage_path = args.coverage_proposal
            proposal_coverage_file, proposal_coverage_text, proposal_coverage = \
                _load_replan_proposal(root, proposal_coverage_path)
            proposal_coverage_sha = kblib.sha256_bytes(
                proposal_coverage_text)
            affected_pages = validate_same_scope_proposal(
                coverage, proposal_coverage)
            amendment_impact = amendment_policy.derive_amendment_impact(
                coverage, proposal_coverage, queue)
            # A proposal-only run is also the diagnostic that explains why a
            # removal needs a different Amendment writer.  Do not suppress
            # that diff merely because it cannot be applied as queue-replan;
            # enforce the operation boundary only on the write path.
            if (args.apply_replan and
                    amendment_impact["writer_operation"] != "queue-replan"):
                raise ValueError(
                    "Coverage proposal requires %s, not queue-replan" %
                    amendment_impact["writer_operation"])
        elif args.coverage_proposal:
            raise ValueError("--coverage-proposal is only valid for a non-empty Queue")
        proposal, changed = compile_document(queue, proposal_coverage)
        proposal_text = kblib.canonical_yaml(proposal)
    except (OSError, ValueError, TypeError, kblib.YamlSubsetError) as exc:
        print("[FAIL] %s" % exc)
        return 1

    # A non-empty Queue is never represented as a replacement document.  Its
    # proposal is a diff artifact that names every preserved lifecycle item and
    # blocks removals pending an Amendment.  Applying it is a separate,
    # Amendment-bound integrator operation.
    if existing:
        diff = replan_diff(queue, proposal, current_sha)
        diff_text = kblib.canonical_yaml(diff)
        if args.output:
            try:
                output = kblib.managed_repository_path(
                    root, args.output, runtime_paths.TRANSIENT_ROOT,
                    suffixes=(".yaml",), must_exist=False,
                )
                kblib.atomic_write_text(output, diff_text,
                                        validator=kblib.parse_yaml_subset)
                print("replan diff written: %s" % args.output)
            except (OSError, ValueError, kblib.YamlSubsetError) as exc:
                print("[FAIL] cannot write replan diff: %s" % exc)
                return 1
        else:
            sys.stdout.write(diff_text)
        if args.apply:
            print("[FAIL] --apply is initial-Queue only; use --apply-replan "
                  "with an approved Amendment")
            return 1
        if not args.apply_replan:
            return 0
        if args.actor_role != "integrator":
            print("[FAIL] only actor-role integrator may apply a Queue replan")
            return 1
        if (args.expected_queue_revision is None or
                args.expected_state_revision is None or
                args.expected_sha256 is None or
                args.expected_coverage_sha256 is None or
                args.expected_progress_sha256 is None):
            print("[FAIL] --apply-replan requires expected Queue/state revisions "
                  "and Coverage/Queue/Progress SHAs")
            return 1
        if (args.expected_queue_revision != queue.get("queue_revision") or
                args.expected_state_revision != queue.get("state_revision") or
                args.expected_sha256 != current_sha or
                args.expected_coverage_sha256 != current_coverage_sha or
                args.expected_progress_sha256 != current_progress_sha):
            print("[FAIL] replan base revision/state or state-file SHA does not "
                  "match current canonical bytes")
            return 1
        if args.replan_diff:
            try:
                diff_path = kblib.managed_repository_path(
                    root, args.replan_diff, runtime_paths.TRANSIENT_ROOT,
                    suffixes=(".yaml",), must_exist=True,
                )
                supplied_diff = kblib.load_yaml_file(diff_path)
            except (OSError, ValueError, kblib.YamlSubsetError) as exc:
                print("[FAIL] cannot consume replan diff: %s" % exc)
                return 1
            if supplied_diff != diff:
                print("[FAIL] supplied replan diff does not match the current "
                      "Coverage inputs and base Queue")
                return 1
        if not diff.get("has_structural_changes"):
            print("[PASS] replan has no structural changes; no write")
            return 0
        if not args.amendment_id:
            print("[FAIL] --apply-replan requires an Amendment id")
            return 1
        try:
            amendment = _pending_replan_amendment(
                progress, args.amendment_id, queue, diff, diff_text,
                proposal_coverage_path, proposal_coverage_sha,
                affected_pages, amendment_impact)
            replanned = queue_replan.build_replanned_queue(
                queue, proposal, diff)
            replanned_text = kblib.canonical_yaml(replanned)
            final_coverage_text = kblib.canonical_yaml(proposal_coverage)
            final_coverage_sha = kblib.sha256_bytes(final_coverage_text)
            transaction_id = "txn-%s-%s" % (
                args.amendment_id, uuid.uuid4().hex)
            receipt = kblib.make_receipt(
                TOOL, TOOL_VERSION, "queue_replan", QUEUE_PATH, "pass",
                "amendment=%s items=%d queue_revision=%d" %
                (args.amendment_id, len(replanned["required_queue"]),
                 replanned["queue_revision"]), 1,
                receipt_type_id=RECEIPT_TYPE_ID,
            )
            receipt.update({
                "task_id": replanned.get("task_id"),
                "amendment_id": args.amendment_id,
                "transaction_id": transaction_id,
                "transaction_phase": "commit",
                "registration_receipt":
                    amendment.get("registration_receipt"),
                "coverage_proposal_path": proposal_coverage_path,
                "coverage_proposal_sha256": proposal_coverage_sha,
                "affected_pages": affected_pages,
                "affected_batches": queue_replan.changed_batch_ids(diff),
                "replan_diff_sha256": kblib.sha256_bytes(diff_text),
                "before_required_queue_sha256": current_sha,
                "after_required_queue_sha256":
                    kblib.sha256_bytes(replanned_text),
                "before_queue_revision": queue.get("queue_revision"),
                "after_queue_revision": replanned.get("queue_revision"),
                "queue_state_revision": replanned.get("state_revision"),
                "actor_role": args.actor_role,
            })
            progress_new = _sync_progress(
                progress, replanned, replanned_text,
                amendment_id=args.amendment_id,
                receipt_id=receipt.get("receipt_id"),
                transaction_id=transaction_id,
                coverage_sha=final_coverage_sha,
            )
            progress_text = kblib.canonical_yaml(progress_new)
            receipt.update({
                "before_coverage_sha256": kblib.sha256_bytes(coverage_text),
                "after_coverage_sha256": final_coverage_sha,
                "before_progress_sha256": kblib.sha256_bytes(old_progress_text),
                "after_progress_sha256": kblib.sha256_bytes(progress_text),
            })
            prepare_receipt = copy.deepcopy(receipt)
            prepare_receipt.update({
                "receipt_id": kblib.make_receipt(
                    TOOL, TOOL_VERSION, "queue_replan_prepare",
                    QUEUE_PATH, "candidate", "prepare %s" % transaction_id,
                    2, receipt_type_id=RECEIPT_TYPE_ID,
                )["receipt_id"],
                "check": "queue_replan_prepare",
                "result": "candidate",
                "transaction_phase": "prepare",
                "details": "prepare %s" % transaction_id,
            })
            abort_receipt = kblib.make_receipt(
                TOOL, TOOL_VERSION, "queue_replan_abort",
                QUEUE_PATH, "fail", "abort %s" % transaction_id, 3,
                receipt_type_id=RECEIPT_TYPE_ID,
            )
            abort_receipt.update({
                key: copy.deepcopy(value) for key, value in receipt.items()
                if key not in ("receipt_id", "check", "result", "details",
                               "checked_at")
            })
            abort_receipt["transaction_phase"] = "abort"
            preflight_errors = _preflight_result(
                root, proposal_coverage, final_coverage_text,
                replanned, replanned_text, progress_new, progress_text,
                authority,
                pending_replan_receipt=receipt,
            )
        except (OSError, TypeError, ValueError, kblib.YamlSubsetError) as exc:
            print("[FAIL] replan cannot be applied: %s" % exc)
            return 1
        if preflight_errors:
            print("[FAIL] proposed result fails check_queue: %s" %
                  "; ".join(preflight_errors))
            return 1
        try:
            receipt_path = kblib.managed_repository_path(
                root, args.receipts, runtime_paths.RECEIPT_ROOT,
                suffixes=(".jsonl",), must_exist=False,
            )
        except ValueError as exc:
            print("[FAIL] invalid receipt path: %s" % exc)
            return 1
        try:
            operation = {
                "tool": TOOL,
                "action": "apply-replan",
                "task_id": replanned.get("task_id"),
                "amendment_id": args.amendment_id,
                "registration_receipt":
                    amendment.get("registration_receipt"),
                "transaction_id": transaction_id,
                "coverage_proposal_path": proposal_coverage_path,
                "coverage_proposal_sha256": proposal_coverage_sha,
                "replan_diff_sha256": kblib.sha256_bytes(diff_text),
                "before_queue_revision": queue.get("queue_revision"),
                "before_state_revision": queue.get("state_revision"),
                "before_queue_sha256": current_sha,
                "before_coverage_sha256": kblib.sha256_bytes(coverage_text),
                "before_progress_sha256": kblib.sha256_bytes(old_progress_text),
                "planned_after_queue_revision": replanned.get("queue_revision"),
                "planned_after_state_revision": replanned.get("state_revision"),
                "planned_after_queue_sha256":
                    kblib.sha256_bytes(replanned_text),
                "planned_after_coverage_sha256": final_coverage_sha,
                "planned_after_progress_sha256": kblib.sha256_bytes(progress_text),
                "prepare_receipt_id": prepare_receipt.get("receipt_id"),
                "commit_receipt_id": receipt.get("receipt_id"),
                "abort_receipt_id": abort_receipt.get("receipt_id"),
                "receipt_id": prepare_receipt.get("receipt_id"),
                "receipt_path": args.receipts,
            }

            def revalidate_delegated_decision(locked):
                live_proposal_raw = kblib.read_bytes(proposal_coverage_file)
                if kblib.sha256_bytes(live_proposal_raw) != proposal_coverage_sha:
                    raise ValueError(
                        "Coverage proposal changed after transaction planning")
                live_proposal = kblib.parse_yaml_subset(
                    live_proposal_raw.decode("utf-8"))
                locked_impact = amendment_policy.derive_amendment_impact(
                    locked["coverage"], live_proposal, locked["queue"])
                locked_amendment = next(
                    (entry for entry in locked["progress"].get("amendments", [])
                     if isinstance(entry, dict) and
                     entry.get("id") == args.amendment_id), None)
                if locked_amendment is None:
                    raise ValueError("pending Amendment disappeared under lock")
                amendment_policy.require_decision_binding(
                    locked["progress"].get("contract") or {},
                    locked_impact, locked_amendment)
            _commit_state(
                root,
                {
                    "coverage": coverage_path,
                    "queue": queue_path,
                    "progress": progress_path,
                },
                {
                    "coverage": coverage_text,
                    "queue": old_queue_text,
                    "progress": old_progress_text,
                },
                {
                    "coverage": final_coverage_text,
                    "queue": replanned_text,
                    "progress": progress_text,
                },
                runtime_state_contract.RUNTIME_LEDGER_IDS,
                receipt_path, prepare_receipt, receipt, abort_receipt,
                operation, authority,
                lock_validator=revalidate_delegated_decision,
            )
        except (OSError, ValueError, kblib.YamlSubsetError,
                kblib.RuntimeStateLockedError) as exc:
            print("[FAIL] replan transaction aborted: %s" % exc)
            return 1
        print("[PASS] applied Queue replan; queue_revision=%d state_revision=%d" %
              (replanned["queue_revision"], replanned["state_revision"]))
        return 0
    if args.apply_replan:
        print("[FAIL] --apply-replan requires a non-empty Queue; use --apply "
              "for initial materialization")
        return 1
    if args.output:
        try:
            output = kblib.managed_repository_path(
                root, args.output, runtime_paths.TRANSIENT_ROOT,
                suffixes=(".yaml",), must_exist=False,
            )
            kblib.atomic_write_text(output, proposal_text,
                                    validator=kblib.parse_yaml_subset)
            print("proposal written: %s" % args.output)
        except (OSError, ValueError, kblib.YamlSubsetError) as exc:
            print("[FAIL] cannot write proposal: %s" % exc)
            return 1
    elif not args.apply:
        sys.stdout.write(proposal_text)

    if not args.apply:
        return 0
    if args.expected_queue_revision is None or args.expected_sha256 is None:
        print("[FAIL] --apply requires --expected-queue-revision and --expected-sha256")
        return 1
    if args.actor_role != "integrator":
        print("[FAIL] only actor-role integrator may apply a Queue write")
        return 1
    if args.expected_queue_revision != queue.get("queue_revision"):
        print("[FAIL] expected Queue revision does not match current revision")
        return 1
    if args.expected_sha256 != current_sha:
        print("[FAIL] expected Queue fingerprint does not match current bytes")
        return 1
    if not changed:
        print("[PASS] Queue structure is already current; no write")
        return 0
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, "queue_structure", QUEUE_PATH, "pass",
        "items=%d queue_revision=%d" %
        (len(proposal["required_queue"]), proposal["queue_revision"]), 1,
        receipt_type_id=RECEIPT_TYPE_ID,
    )
    try:
        progress_new = _sync_progress(
            progress, proposal, proposal_text,
            initial_queue_receipt=receipt.get("receipt_id"),
        )
        progress_text = kblib.canonical_yaml(progress_new)
    except ValueError as exc:
        print("[FAIL] cannot bind initial Queue receipt: %s" % exc)
        return 1
    receipt.update({
        "task_id": proposal.get("task_id"),
        "contract_sha256": queue_runtime.contract_sha256(progress),
        "contract_version": (progress.get("contract") or {}).get(
            "contract_version"),
        "contract_scope_version": (progress.get("contract") or {}).get(
            "scope_version"),
        "before_required_queue_sha256": current_sha,
        "after_required_queue_sha256": kblib.sha256_bytes(proposal_text),
        "before_coverage_sha256": kblib.sha256_bytes(coverage_text),
        "after_coverage_sha256": kblib.sha256_bytes(coverage_text),
        "before_progress_sha256": kblib.sha256_bytes(old_progress_text),
        "after_progress_sha256": kblib.sha256_bytes(progress_text),
        "before_queue_revision": queue.get("queue_revision"),
        "after_queue_revision": proposal.get("queue_revision"),
        "queue_state_revision": proposal.get("state_revision"),
        "actor_role": args.actor_role,
    })
    preflight_errors = _preflight_result(
        root, coverage, coverage_text, proposal, proposal_text,
        progress_new, progress_text, authority,
        pending_replan_receipt=receipt,
    )
    if preflight_errors:
        print("[FAIL] proposed initial Queue fails check_queue: %s" %
              "; ".join(preflight_errors))
        return 1
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, runtime_paths.RECEIPT_ROOT,
            suffixes=(".jsonl",), must_exist=False,
        )
    except ValueError as exc:
        print("[FAIL] invalid receipt path: %s" % exc)
        return 1
    try:
        operation = {
            "tool": TOOL,
            "action": "initial-compile",
            "task_id": proposal.get("task_id"),
            "before_queue_revision": queue.get("queue_revision"),
            "before_state_revision": queue.get("state_revision"),
            "before_queue_sha256": current_sha,
            "before_coverage_sha256": kblib.sha256_bytes(coverage_text),
            "before_progress_sha256": kblib.sha256_bytes(old_progress_text),
            "planned_after_queue_revision": proposal.get("queue_revision"),
            "planned_after_state_revision": proposal.get("state_revision"),
            "planned_after_queue_sha256":
                kblib.sha256_bytes(proposal_text),
            "planned_after_coverage_sha256": kblib.sha256_bytes(coverage_text),
            "planned_after_progress_sha256": kblib.sha256_bytes(progress_text),
            "receipt_id": receipt.get("receipt_id"),
            "receipt_path": args.receipts,
        }
        _commit_state(
            root,
            {
                "coverage": coverage_path,
                "queue": queue_path,
                "progress": progress_path,
            },
            {
                "coverage": coverage_text,
                "queue": old_queue_text,
                "progress": old_progress_text,
            },
            {
                "coverage": coverage_text,
                "queue": proposal_text,
                "progress": progress_text,
            },
            ("queue", "progress"), receipt_path, None, receipt, None,
            operation, authority,
        )
    except (OSError, ValueError, kblib.YamlSubsetError,
            kblib.RuntimeStateLockedError) as exc:
        print("[FAIL] write aborted and previous state restored: %s" % exc)
        return 1
    print("[PASS] compiled %d Required Queue item(s); queue_revision=%d" %
          (len(proposal["required_queue"]), proposal["queue_revision"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
