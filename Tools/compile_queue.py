#!/usr/bin/env python3
"""Deterministically compile Required Queue structure from explicit Coverage data.

The compiler reads only declared Coverage assignments and top-level
``batch_specs``.  It does not inspect backlinks, page prose, or semantic
similarity.  By default it prints a proposal.  ``--apply`` materializes an
initial Queue; ``--apply-replan`` performs an Amendment-bound structural write
without rewriting lifecycle history.
"""

import argparse
import copy
import os
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_queue
import kblib

QUEUE_PATH = ".cambium/state/required_queue.yaml"
COVERAGE_PATH = ".cambium/state/coverage_ledger.yaml"
PROGRESS_PATH = ".cambium/state/progress_ledger.yaml"
REPLAN_PROPOSAL_PREFIX = ".cambium/deltas/replans"
TOOL_VERSION = "1.2.0"
PRIORITY = {"P0": 0, "P1": 1, "P2": 2}
STRUCTURAL_FIELDS = (
    "family", "order", "record_count", "manifest", "source_route",
    "execution_mode", "depends_on", "confirmation_required", "successor_of",
    "work_spec_path", "work_spec_sha256",
)
WORK_SPEC_FIELDS = check_queue.WORK_SPEC_FIELDS
REPLAN_PAGE_FIELDS = frozenset(("batch", "next_batch"))
COVERAGE_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "task_id", "updated_at", "scope_version",
    "standards_version", "selected_profile_manifest", "batch_specs",
    "maintenance_candidates", "pages", "open_gaps",
))
BATCH_SPEC_FIELDS = check_queue.COVERAGE_BATCH_SPEC_FIELDS


def _load(root, relative):
    path = kblib.managed_repository_path(
        root, relative, ".cambium/state",
        suffixes=(".yaml",), must_exist=True,
    )
    return path, kblib.load_yaml_file(path)


def _load_replan_proposal(root, relative):
    path = kblib.managed_repository_path(
        root, relative, REPLAN_PROPOSAL_PREFIX,
        suffixes=(".coverage.yaml",), must_exist=True,
    )
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
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
    if proposal.get("schema_version") != 1:
        raise ValueError("Coverage proposal schema_version must be 1")
    for field in ("schema_version", "task_id", "scope_version",
                  "standards_version", "selected_profile_manifest"):
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
        if mode not in ("concurrent-worker", "serial-integrator"):
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
        work_spec_errors = check_queue._work_spec_binding_errors(
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
        for key in ("batch", "next_batch"):
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
            priority = PRIORITY.get(page.get("priority"), 99)
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
        if isinstance(item, dict) and item.get("state") in ("closed", "cancelled")
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
                          for field in STRUCTURAL_FIELDS})
        existing_structure.append(projected)
    compiled_structure = []
    for item in compiled:
        projected = {"id": item.get("id")}
        projected.update({field: copy.deepcopy(item.get(field))
                          for field in STRUCTURAL_FIELDS})
        compiled_structure.append(projected)
    changed = existing_structure != compiled_structure
    result["queue_revision"] = result.get("queue_revision", 0) + 1
    result["required_queue"] = compiled
    return result, changed


def _changed_structural_fields(current, proposed):
    """Return value or explicit-presence changes in the closed structure."""
    return [
        field for field in STRUCTURAL_FIELDS
        if ((field in current) != (field in proposed) or
            current.get(field) != proposed.get(field))
    ]


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
    for item_id in sorted(proposed_items):
        proposed = proposed_items[item_id]
        current = current_items.get(item_id)
        structural = {field: copy.deepcopy(proposed.get(field))
                      for field in STRUCTURAL_FIELDS}
        if current is None:
            candidate = {"id": item_id, "initial_state": "queued"}
            candidate.update(structural)
            adds.append(candidate)
            continue
        changed_fields = _changed_structural_fields(current, proposed)
        if changed_fields:
            updates.append({
                "id": item_id,
                "current_state": current.get("state"),
                "changed_fields": changed_fields,
                "proposed_structure": structural,
            })
            work_spec_only = set(changed_fields).issubset(WORK_SPEC_FIELDS)
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
        if current.get("state") in ("closed", "cancelled"):
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
                          ("open", "merge-ready")]
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
        "conflicts": conflicts,
    }


def _changed_batch_ids(diff):
    changed = set()
    for field in ("add_candidates", "update_candidates",
                  "reorder_candidates", "remove_candidates"):
        for entry in diff.get(field, []):
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                changed.add(entry["id"])
    return sorted(changed)


def _pending_replan_amendment(progress, amendment_id, queue, diff,
                              diff_text, proposal_path, proposal_sha,
                              affected_pages):
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
    expected = {
        "status": "approved",
        "writeback_done": False,
        "operation": "queue-replan",
        "coverage_proposal_path": proposal_path,
        "coverage_proposal_sha256": proposal_sha,
        "affected_pages": affected_pages,
        "affected_batches": _changed_batch_ids(diff),
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
    return amendment


def _build_replanned_queue(queue, proposal, diff):
    """Apply only safe structural candidates while preserving lifecycle data."""
    if diff.get("remove_candidates"):
        removed = ", ".join(entry.get("id", "<unknown>")
                            for entry in diff["remove_candidates"]
                            if isinstance(entry, dict))
        raise ValueError("replan cannot delete Queue history/items: %s" % removed)
    if diff.get("conflicts"):
        raise ValueError("replan has unresolved conflict(s): %s" %
                         "; ".join(str(value) for value in diff["conflicts"]))

    current = {item.get("id"): item for item in queue.get("required_queue", [])
               if isinstance(item, dict)}
    desired = {item.get("id"): item
               for item in proposal.get("required_queue", [])
               if isinstance(item, dict)}
    result_items = []
    for item in queue.get("required_queue", []):
        item_id = item.get("id")
        proposed = desired.get(item_id)
        if proposed is None:
            result_items.append(copy.deepcopy(item))
            continue
        changed = _changed_structural_fields(item, proposed)
        work_spec_only = bool(changed) and set(changed).issubset(
            WORK_SPEC_FIELDS)
        open_spec_replan = (
            item.get("state") == "open" and work_spec_only and
            item.get("hold_state") == "revalidation-required"
        )
        if (changed and item.get("state") != "queued" and
                not open_spec_replan):
            raise ValueError("cannot change structure of %s item %s" %
                             (item.get("state"), item_id))
        merged = copy.deepcopy(item)
        if item.get("state") == "queued":
            for field in STRUCTURAL_FIELDS:
                if field in proposed:
                    merged[field] = copy.deepcopy(proposed[field])
                else:
                    merged.pop(field, None)
        elif open_spec_replan:
            for field in WORK_SPEC_FIELDS:
                merged[field] = copy.deepcopy(proposed.get(field))
        result_items.append(merged)

    for proposed in proposal.get("required_queue", []):
        item_id = proposed.get("id")
        if item_id in current:
            continue
        if proposed.get("state") != "queued":
            raise ValueError("new Queue item %s must start queued" % item_id)
        result_items.append(copy.deepcopy(proposed))

    result_items.sort(key=lambda item: (item.get("order", 10 ** 9),
                                        item.get("id", "")))
    orders = [item.get("order") for item in result_items]
    if orders != list(range(1, len(result_items) + 1)):
        raise ValueError("replanned Queue order must remain contiguous from 1")
    positions = {item.get("id"): item.get("order") for item in result_items}
    for item in result_items:
        for dependency in item.get("depends_on", []):
            if dependency not in positions:
                raise ValueError("%s depends on missing batch %s" %
                                 (item.get("id"), dependency))
            if positions[dependency] >= item.get("order"):
                raise ValueError("%s dependency %s is not ordered earlier" %
                                 (item.get("id"), dependency))

    result = copy.deepcopy(queue)
    result["queue_revision"] = queue.get("queue_revision", 0) + 1
    result["state_revision"] = queue.get("state_revision")
    result["required_queue"] = result_items
    return result


def _copy_result_evidence(root, temporary_root, queue, progress):
    """Copy only files check_queue needs for a proposed-state preflight."""
    profile = queue.get("selected_profile_manifest")
    if isinstance(profile, str) and profile:
        source = kblib.repository_path(
            root, profile, must_exist=True, reject_symlink=True)
        target = os.path.join(temporary_root, *profile.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)

    artifacts = {}

    def register(relative, expected_sha, prefix, suffixes, label):
        if not isinstance(relative, str) or not relative:
            return
        contract = (expected_sha, prefix, tuple(suffixes))
        prior = artifacts.get(relative)
        if prior is not None and prior[:3] != contract:
            raise ValueError("conflicting evidence bindings for %s" % relative)
        artifacts[relative] = contract + (label,)

    for item in queue.get("required_queue", []):
        if not isinstance(item, dict):
            continue
        register(
            item.get("work_spec_path"), item.get("work_spec_sha256"),
            check_queue.WORK_SPEC_PREFIX, (".yaml",),
            "Queue %s Batch Work Spec" % item.get("id", "<unknown>"),
        )
        register(
            item.get("delta_path"), item.get("delta_sha256"),
            ".cambium/deltas", (".yaml", ".yml"),
            "Queue %s current delta" % item.get("id", "<unknown>"),
        )
        history = item.get("invalidation_history")
        if isinstance(history, list):
            for index, invalidation in enumerate(history):
                if not isinstance(invalidation, dict):
                    continue
                register(
                    invalidation.get("delta_archive_path"),
                    invalidation.get("delta_sha256"),
                    ".cambium/receipts", (".yaml", ".yml"),
                    "Queue %s invalidation_history[%d] delta archive" %
                    (item.get("id", "<unknown>"), index),
                )
    for amendment in progress.get("amendments", []) if isinstance(
            progress.get("amendments"), list) else []:
        if not isinstance(amendment, dict):
            continue
        operation = amendment.get("operation")
        if operation == "queue-replan":
            proposal_prefix = REPLAN_PROPOSAL_PREFIX
            proposal_suffixes = (".coverage.yaml",)
        elif operation in ("scope-replan", "cancel-batch"):
            proposal_prefix = ".cambium/deltas/amendments"
            proposal_suffixes = (".yaml", ".yml")
            register(
                amendment.get("plan_path"), amendment.get("plan_sha256"),
                ".cambium/deltas/amendments", (".yaml", ".yml"),
                "Progress Amendment %s plan" % amendment.get("id", "<unknown>"),
            )
        else:
            continue
        register(
            amendment.get("coverage_proposal_path"),
            amendment.get("coverage_proposal_sha256"),
            proposal_prefix, proposal_suffixes,
            "Progress Amendment %s Coverage proposal" %
            amendment.get("id", "<unknown>"),
        )

    for relative in sorted(artifacts):
        expected_sha, prefix, suffixes, label = artifacts[relative]
        if (not isinstance(expected_sha, str) or
                not check_queue.SHA256_RE.fullmatch(expected_sha)):
            raise ValueError("%s has invalid SHA binding" % label)
        source = kblib.managed_repository_path(
            root, relative, prefix, suffixes=suffixes, must_exist=True,
        )
        actual_sha = kblib.sha256_file(source)
        if actual_sha != expected_sha:
            raise ValueError("%s bytes differ from bound SHA" % label)
        target = os.path.join(temporary_root, *relative.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
    receipt_root = os.path.join(root, ".cambium", "receipts")
    if os.path.isdir(receipt_root):
        for dirpath, dirnames, filenames in os.walk(receipt_root):
            dirnames[:] = sorted(name for name in dirnames
                                 if not os.path.islink(os.path.join(dirpath, name)))
            for name in sorted(filenames):
                if not name.endswith(".jsonl"):
                    continue
                source = os.path.join(dirpath, name)
                relative = os.path.relpath(source, root)
                target = os.path.join(temporary_root, *relative.split(os.sep))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)


def _preflight_result(root, coverage_text, queue, queue_text, progress,
                      progress_text, pending_replan_receipt=None):
    with tempfile.TemporaryDirectory(prefix="cambium-replan-") as temporary:
        state = os.path.join(temporary, ".cambium", "state")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, "coverage_ledger.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(coverage_text)
        with open(os.path.join(state, "required_queue.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(queue_text)
        with open(os.path.join(state, "progress_ledger.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(progress_text)
        _copy_result_evidence(root, temporary, queue, progress)
        return check_queue.validate_runtime(
            temporary,
            extra_receipts=([pending_replan_receipt]
                            if pending_replan_receipt is not None else None),
            allow_pending_replan_receipts=(pending_replan_receipt is not None),
        )["errors"]


def _sync_progress(progress, queue, queue_text, amendment_id=None,
                   receipt_id=None, transaction_id=None,
                   coverage_sha=None, initial_queue_receipt=None):
    result = copy.deepcopy(progress)
    result["required_queue_path"] = QUEUE_PATH
    result["queue_revision"] = queue["queue_revision"]
    result["queue_state_revision"] = queue["state_revision"]
    result["required_queue_sha256"] = kblib.sha256_bytes(queue_text)
    if initial_queue_receipt is not None:
        if result.get("initial_queue_receipt") is not None:
            raise ValueError("Progress already records an initial Queue receipt")
        result["initial_queue_receipt"] = initial_queue_receipt
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
                  abort_receipt, operation):
    """Publish one guarded state transaction and preserve crash evidence.

    Per-file replacement cannot be atomic across three files.  The shared
    lock records before/planned-after fingerprints; a durable prepare receipt
    precedes the first replacement.  An escaping failure leaves the lock
    unless every authoritative byte has been restored and verified.
    """
    with kblib.runtime_write_lock(root, owner_metadata=operation) as lease:
        with kblib.no_authoritative_write_guard(lease):
            for name, path in paths.items():
                with open(path, encoding="utf-8") as fh:
                    live = fh.read()
                if live != before_text[name]:
                    raise ValueError(
                        "%s changed after transaction planning" % name)
            locked = check_queue.validate_runtime(
                root, allow_unmaterialized_queue=True,
            )
            if locked["errors"]:
                raise ValueError("runtime changed before write: %s" %
                                 "; ".join(locked["errors"]))
            barrier = check_queue.delta_apply_write_barrier(
                locked, "compile_queue", operation.get("action"))
            if barrier:
                raise ValueError(barrier)
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
                outcome, append_error, _ = kblib.write_receipts_observed(
                    receipt_path, [prepare_receipt]
                )
                outcomes["prepare"] = outcome
                if append_error is not None:
                    raise append_error
            for name in write_names:
                kblib.atomic_write_text(
                    paths[name], after_text[name],
                    validator=kblib.parse_yaml_subset,
                )
            postflight = check_queue.validate_runtime(
                root, extra_receipts=[commit_receipt],
                allow_pending_replan_receipts=True,
            )["errors"]
            if postflight:
                raise ValueError("post-write check_queue failed: %s" %
                                 "; ".join(postflight))
            outcome, append_error, _ = kblib.write_receipts_observed(
                receipt_path, [commit_receipt], before=commit_before
            )
            outcomes["commit"] = outcome
            if append_error is not None:
                raise append_error
            persisted = check_queue.validate_runtime(root)["errors"]
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
                        receipt_path, [abort_receipt]
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
    parser = argparse.ArgumentParser(description="Compile Required Queue from explicit Coverage assignments")
    parser.add_argument("root")
    parser.add_argument("--output", help="repository-relative proposal path")
    write_mode = parser.add_mutually_exclusive_group()
    write_mode.add_argument("--apply", action="store_true",
                            help="materialize an initially empty Queue")
    write_mode.add_argument("--apply-replan", action="store_true",
                            help="apply a controlled structural diff to a non-empty Queue")
    parser.add_argument(
        "--coverage-proposal",
        help="repository-contained .cambium/deltas/replans/*.coverage.yaml input",
    )
    parser.add_argument("--replan-diff",
                        help="existing .cambium/tmp/*.yaml diff to consume")
    parser.add_argument("--amendment-id")
    parser.add_argument("--expected-queue-revision", type=int)
    parser.add_argument("--expected-state-revision", type=int)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-coverage-sha256")
    parser.add_argument("--expected-progress-sha256")
    parser.add_argument("--actor-role", choices=("worker", "integrator"),
                        default="worker")
    parser.add_argument("--receipts",
                        default=".cambium/receipts/queue-structure.jsonl")
    args = parser.parse_args(argv)

    root = os.path.realpath(os.path.abspath(args.root))
    try:
        queue_path, queue = _load(root, QUEUE_PATH)
        coverage_path, coverage = _load(root, COVERAGE_PATH)
        progress_path, progress = _load(root, PROGRESS_PATH)
        old_queue_text = open(queue_path, encoding="utf-8").read()
        coverage_text = open(coverage_path, encoding="utf-8").read()
        old_progress_text = open(progress_path, encoding="utf-8").read()
        current_sha = kblib.sha256_bytes(old_queue_text)
        current_coverage_sha = kblib.sha256_bytes(coverage_text)
        current_progress_sha = kblib.sha256_bytes(old_progress_text)
        existing = queue.get("required_queue") or []
        current_validation = check_queue.validate_runtime(
            root, allow_unmaterialized_queue=not bool(
                queue.get("required_queue")
            ),
        )
        if current_validation["errors"]:
            raise ValueError("current runtime state is inconsistent: %s" %
                             "; ".join(current_validation["errors"]))
        if args.apply or args.apply_replan:
            barrier = check_queue.delta_apply_write_barrier(
                current_validation, "compile_queue",
                "apply-replan" if args.apply_replan else "initial-compile",
            )
            if barrier:
                raise ValueError(barrier)
        proposal_coverage_path = None
        proposal_coverage_text = coverage_text
        proposal_coverage = coverage
        proposal_coverage_sha = current_coverage_sha
        affected_pages = []
        if existing:
            if not args.coverage_proposal:
                raise ValueError(
                    "a non-empty Queue requires --coverage-proposal inside "
                    ".cambium/deltas/replans/; never pre-edit canonical Coverage"
                )
            proposal_coverage_path = args.coverage_proposal
            _, proposal_coverage_text, proposal_coverage = \
                _load_replan_proposal(root, proposal_coverage_path)
            proposal_coverage_sha = kblib.sha256_bytes(
                proposal_coverage_text)
            affected_pages = validate_same_scope_proposal(
                coverage, proposal_coverage)
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
                    root, args.output, ".cambium/tmp",
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
                    root, args.replan_diff, ".cambium/tmp",
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
            _pending_replan_amendment(
                progress, args.amendment_id, queue, diff, diff_text,
                proposal_coverage_path, proposal_coverage_sha,
                affected_pages)
            replanned = _build_replanned_queue(queue, proposal, diff)
            replanned_text = kblib.canonical_yaml(replanned)
            final_coverage_text = kblib.canonical_yaml(proposal_coverage)
            final_coverage_sha = kblib.sha256_bytes(final_coverage_text)
            transaction_id = "txn-%s-%s" % (
                args.amendment_id, uuid.uuid4().hex)
            receipt = kblib.make_receipt(
                "compile_queue", TOOL_VERSION, "queue_replan", QUEUE_PATH, "pass",
                "amendment=%s items=%d queue_revision=%d" %
                (args.amendment_id, len(replanned["required_queue"]),
                 replanned["queue_revision"]), 1,
            )
            receipt.update({
                "task_id": replanned.get("task_id"),
                "amendment_id": args.amendment_id,
                "transaction_id": transaction_id,
                "transaction_phase": "commit",
                "coverage_proposal_path": proposal_coverage_path,
                "coverage_proposal_sha256": proposal_coverage_sha,
                "affected_pages": affected_pages,
                "affected_batches": _changed_batch_ids(diff),
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
                    "compile_queue", TOOL_VERSION, "queue_replan_prepare",
                    QUEUE_PATH, "candidate", "prepare %s" % transaction_id,
                    2,
                )["receipt_id"],
                "check": "queue_replan_prepare",
                "result": "candidate",
                "transaction_phase": "prepare",
                "details": "prepare %s" % transaction_id,
            })
            abort_receipt = kblib.make_receipt(
                "compile_queue", TOOL_VERSION, "queue_replan_abort",
                QUEUE_PATH, "fail", "abort %s" % transaction_id, 3,
            )
            abort_receipt.update({
                key: copy.deepcopy(value) for key, value in receipt.items()
                if key not in ("receipt_id", "check", "result", "details",
                               "checked_at")
            })
            abort_receipt["transaction_phase"] = "abort"
            preflight_errors = _preflight_result(
                root, final_coverage_text, replanned, replanned_text,
                progress_new, progress_text,
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
                root, args.receipts, ".cambium/receipts",
                suffixes=(".jsonl",), must_exist=False,
            )
        except ValueError as exc:
            print("[FAIL] invalid receipt path: %s" % exc)
            return 1
        try:
            operation = {
                "tool": "compile_queue",
                "action": "apply-replan",
                "task_id": replanned.get("task_id"),
                "amendment_id": args.amendment_id,
                "transaction_id": transaction_id,
                "coverage_proposal_path": proposal_coverage_path,
                "coverage_proposal_sha256": proposal_coverage_sha,
                "replan_diff_sha256": kblib.sha256_bytes(diff_text),
                "before_queue_revision": queue.get("queue_revision"),
                "before_state_revision": queue.get("state_revision"),
                "before_required_queue_sha256": current_sha,
                "before_coverage_sha256": kblib.sha256_bytes(coverage_text),
                "before_progress_sha256": kblib.sha256_bytes(old_progress_text),
                "planned_after_queue_revision": replanned.get("queue_revision"),
                "planned_after_state_revision": replanned.get("state_revision"),
                "planned_after_required_queue_sha256":
                    kblib.sha256_bytes(replanned_text),
                "planned_after_coverage_sha256": final_coverage_sha,
                "planned_after_progress_sha256": kblib.sha256_bytes(progress_text),
                "prepare_receipt_id": prepare_receipt.get("receipt_id"),
                "commit_receipt_id": receipt.get("receipt_id"),
                "abort_receipt_id": abort_receipt.get("receipt_id"),
                "receipt_id": prepare_receipt.get("receipt_id"),
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
                    "coverage": final_coverage_text,
                    "queue": replanned_text,
                    "progress": progress_text,
                },
                ("coverage", "queue", "progress"),
                receipt_path, prepare_receipt, receipt, abort_receipt,
                operation,
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
                root, args.output, ".cambium/tmp",
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
        "compile_queue", TOOL_VERSION, "queue_structure", QUEUE_PATH, "pass",
        "items=%d queue_revision=%d" %
        (len(proposal["required_queue"]), proposal["queue_revision"]), 1,
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
        "contract_sha256": check_queue._contract_sha256(progress),
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
        root, coverage_text, proposal, proposal_text, progress_new, progress_text,
        pending_replan_receipt=receipt,
    )
    if preflight_errors:
        print("[FAIL] proposed initial Queue fails check_queue: %s" %
              "; ".join(preflight_errors))
        return 1
    try:
        receipt_path = kblib.managed_repository_path(
            root, args.receipts, ".cambium/receipts",
            suffixes=(".jsonl",), must_exist=False,
        )
    except ValueError as exc:
        print("[FAIL] invalid receipt path: %s" % exc)
        return 1
    try:
        operation = {
            "tool": "compile_queue",
            "action": "initial-compile",
            "task_id": proposal.get("task_id"),
            "before_queue_revision": queue.get("queue_revision"),
            "before_state_revision": queue.get("state_revision"),
            "before_required_queue_sha256": current_sha,
            "before_coverage_sha256": kblib.sha256_bytes(coverage_text),
            "before_progress_sha256": kblib.sha256_bytes(old_progress_text),
            "planned_after_queue_revision": proposal.get("queue_revision"),
            "planned_after_state_revision": proposal.get("state_revision"),
            "planned_after_required_queue_sha256":
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
            operation,
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
