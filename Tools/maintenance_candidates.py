#!/usr/bin/env python3
"""Pure validation helpers for K00/08 maintenance candidate state.

Coverage owns the candidate state, a maintenance budget manifest freezes one
run's complete candidate set and selected/deferred partition, and Required
Queue owns only the selected work.  This module keeps that set algebra out of
the Queue lifecycle checker; it performs no writes and makes no semantic
decision about whether the four source scans found the right candidates.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib


CANDIDATE_FIELDS = frozenset((
    "candidate_id", "object_path", "source_kinds", "priority",
    "previous_deferred_runs", "consecutive_deferred_runs",
    "reentered_after_terminal", "selection", "disposition",
    "disposition_reason",
))
SOURCE_KINDS = frozenset((
    "freshness", "watermark", "needs-rereview", "candidate-pool",
))
PRIORITIES = ("P0", "P1", "P2")
SELECTIONS = frozenset(("selected", "deferred"))
TERMINAL_DISPOSITIONS = frozenset(("log-only", "retired"))
AGED_DISPOSITIONS = frozenset(("log-only", "retired", "retained"))


def candidate_id_for_path(path):
    """Return the stable candidate identity owned by one canonical path."""
    digest = kblib.sha256_bytes(path.encode("utf-8")).split(":", 1)[1]
    return "candidate-sha256:%s" % digest


def candidate_state_sha256(candidates):
    """Fingerprint one ordered candidate-state projection."""
    return kblib.sha256_bytes(kblib.canonical_yaml({
        "maintenance_candidates": candidates,
    }))


def closed_mapping_errors(value, label, fields):
    if not isinstance(value, dict):
        return ["%s must be a mapping" % label]
    errors = []
    missing = sorted(fields - set(value))
    extra = sorted(set(value) - fields)
    if missing:
        errors.append("%s misses explicit field(s): %s" %
                      (label, ", ".join(missing)))
    if extra:
        errors.append("%s has unsupported field(s): %s" %
                      (label, ", ".join(extra)))
    return errors


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _enum_member(value, allowed):
    """Return true only for a scalar string in one closed vocabulary.

    YAML permits sequences and mappings wherever a scalar was intended.  A
    validator must report those shapes rather than passing an unhashable value
    to a set membership operation and crashing before it can fail closed.
    """
    return isinstance(value, str) and value in allowed


def _prior_index(previous_candidates):
    if previous_candidates is None:
        return {}, []
    if not isinstance(previous_candidates, list):
        return {}, ["previous maintenance candidate state must be a list"]
    index = {}
    errors = []
    for position, record in enumerate(previous_candidates):
        label = "previous maintenance candidate[%d]" % position
        if not isinstance(record, dict):
            errors.append("%s must be a mapping" % label)
            continue
        candidate_id = record.get("candidate_id")
        if not _nonempty(candidate_id):
            errors.append("%s candidate_id must be non-empty" % label)
        elif candidate_id in index:
            errors.append("previous maintenance candidate repeats %s" %
                          candidate_id)
        else:
            index[candidate_id] = record
    return index, errors


def validate_candidates(root, candidates, *, previous_candidates=None,
                        validate_prior=True,
                        label="maintenance candidates"):
    """Validate records and return ``(errors, ordered context)``.

    ``previous_candidates`` is the projection bound by the prior maintenance
    completion receipt.  It is optional only for the first run.  A generic
    runtime-shape check may set ``validate_prior=False`` because it has not yet
    resolved the frozen manifest and its prior receipt; the completion gate
    always performs the full cross-run comparison.
    """
    errors = []
    if not isinstance(candidates, list):
        return ["%s must be an explicit list" % label], {
            "records": [], "selected_ids": [], "deferred_ids": [],
            "selected_objects": [], "candidate_state_sha256": None,
        }
    prior, prior_errors = _prior_index(previous_candidates)
    errors.extend(prior_errors)
    seen_ids = set()
    seen_paths = set()
    records = []
    for position, record in enumerate(candidates):
        item_label = "%s[%d]" % (label, position)
        errors.extend(closed_mapping_errors(
            record, item_label, CANDIDATE_FIELDS))
        if not isinstance(record, dict):
            continue
        candidate_id = record.get("candidate_id")
        object_path = record.get("object_path")
        if not _nonempty(object_path):
            errors.append("%s object_path must be non-empty" % item_label)
        else:
            try:
                kblib.repository_path(root, object_path, must_exist=False,
                                      reject_symlink=True)
            except (OSError, ValueError) as exc:
                errors.append("%s object_path is unsafe: %s" %
                              (item_label, exc))
            expected_id = candidate_id_for_path(object_path)
            if candidate_id != expected_id:
                errors.append("%s candidate_id must be %s" %
                              (item_label, expected_id))
        if not _nonempty(candidate_id):
            errors.append("%s candidate_id must be non-empty" % item_label)
        elif candidate_id in seen_ids:
            errors.append("%s repeats candidate_id %s" %
                          (label, candidate_id))
        else:
            seen_ids.add(candidate_id)
        if _nonempty(object_path):
            if object_path in seen_paths:
                errors.append("%s must fuse duplicate object_path %s" %
                              (label, object_path))
            else:
                seen_paths.add(object_path)

        source_kinds = record.get("source_kinds")
        valid_source_values = (
            isinstance(source_kinds, list) and bool(source_kinds) and
            all(_enum_member(value, SOURCE_KINDS)
                for value in source_kinds)
        )
        if (not valid_source_values or
                len(source_kinds) != len(set(source_kinds)) or
                source_kinds != sorted(source_kinds)):
            errors.append(
                "%s source_kinds must be a non-empty sorted unique subset of %s" %
                (item_label, ", ".join(sorted(SOURCE_KINDS))))
        priority = record.get("priority")
        if not _enum_member(priority, PRIORITIES):
            errors.append("%s priority must be P0, P1, or P2" % item_label)
        previous_runs = record.get("previous_deferred_runs")
        current_runs = record.get("consecutive_deferred_runs")
        for field, value in (("previous_deferred_runs", previous_runs),
                             ("consecutive_deferred_runs", current_runs)):
            if (not isinstance(value, int) or isinstance(value, bool) or
                    value < 0):
                errors.append("%s %s must be an integer >= 0" %
                              (item_label, field))
        reentered = record.get("reentered_after_terminal")
        if not isinstance(reentered, bool):
            errors.append("%s reentered_after_terminal must be boolean" %
                          item_label)
        selection = record.get("selection")
        if not _enum_member(selection, SELECTIONS):
            errors.append("%s selection must be selected or deferred" %
                          item_label)
        disposition = record.get("disposition")
        reason = record.get("disposition_reason")
        if (disposition is not None and
                not _enum_member(disposition, AGED_DISPOSITIONS)):
            errors.append("%s disposition has invalid value %r" %
                          (item_label, disposition))
        if reason is not None and not _nonempty(reason):
            errors.append("%s disposition_reason must be null or non-empty" %
                          item_label)

        if validate_prior:
            prior_record = prior.get(candidate_id) \
                if _nonempty(candidate_id) else None
            expected_previous = 0
            if prior_record is not None:
                prior_terminal = _enum_member(
                    prior_record.get("disposition"), TERMINAL_DISPOSITIONS)
                if prior_terminal and reentered is True:
                    expected_previous = 0
                else:
                    expected_previous = prior_record.get(
                        "consecutive_deferred_runs")
                    if prior_terminal:
                        errors.append(
                            "%s terminal prior candidate requires explicit re-entry" %
                            item_label)
                    elif reentered is True:
                        errors.append(
                            "%s may re-enter only after a terminal prior candidate" %
                            item_label)
            elif reentered is True:
                errors.append("%s cannot re-enter without prior candidate state" %
                              item_label)
            if (isinstance(previous_runs, int) and
                    not isinstance(previous_runs, bool) and
                    isinstance(expected_previous, int) and
                    previous_runs != expected_previous):
                errors.append("%s previous_deferred_runs=%d, expected %d" %
                              (item_label, previous_runs, expected_previous))

        if selection == "selected":
            if current_runs != 0:
                errors.append("%s selected candidate must reset consecutive_deferred_runs to 0" %
                              item_label)
            if disposition is not None or reason is not None:
                errors.append("%s selected candidate must have null disposition and reason" %
                              item_label)
        elif selection == "deferred" and isinstance(previous_runs, int) and \
                not isinstance(previous_runs, bool):
            expected_current = previous_runs + 1
            if current_runs != expected_current:
                errors.append("%s deferred consecutive_deferred_runs must be %d" %
                              (item_label, expected_current))
            if expected_current < 3:
                if disposition is not None or reason is not None:
                    errors.append("%s deferred age below 3 must have null disposition and reason" %
                                  item_label)
            elif expected_current == 3:
                if disposition != "log-only" or not _nonempty(reason):
                    errors.append("%s third consecutive deferral must be log-only with a reason" %
                                  item_label)
            elif (not _enum_member(disposition, AGED_DISPOSITIONS) or
                  not _nonempty(reason)):
                errors.append("%s deferred age above 3 requires log-only, retired, or retained with a reason" %
                              item_label)
        records.append(record)

    priority_rank = {value: position for position, value in
                     enumerate(PRIORITIES)}
    expected_order = sorted(records, key=lambda record: (
        (priority_rank.get(record.get("priority"), len(PRIORITIES))
         if isinstance(record.get("priority"), str) else len(PRIORITIES)),
        str(record.get("object_path")), str(record.get("candidate_id")),
    ))
    if records != expected_order:
        errors.append("%s must be ordered by priority, object_path, candidate_id" %
                      label)
    selected = [record for record in records
                if record.get("selection") == "selected"]
    deferred = [record for record in records
                if record.get("selection") == "deferred"]
    if validate_prior:
        carried_ids = {
            candidate_id for candidate_id, record in prior.items()
            if record.get("selection") == "deferred" and
            not _enum_member(record.get("disposition"),
                             TERMINAL_DISPOSITIONS)
        }
        silently_dropped = sorted(carried_ids - seen_ids)
        if silently_dropped:
            errors.append(
                "%s silently drops prior nonterminal deferred candidate(s): %s" %
                (label, ", ".join(silently_dropped))
            )
    try:
        state_sha256 = candidate_state_sha256(records)
    except (TypeError, ValueError, UnicodeError,
            kblib.YamlSubsetError) as exc:
        errors.append(
            "%s cannot be represented by canonical restricted YAML: %s" %
            (label, exc)
        )
        state_sha256 = None
    return errors, {
        "records": records,
        "selected_ids": [record.get("candidate_id") for record in selected
                         if _nonempty(record.get("candidate_id"))],
        "deferred_ids": [record.get("candidate_id") for record in deferred
                         if _nonempty(record.get("candidate_id"))],
        "selected_objects": [record.get("object_path") for record in selected
                             if _nonempty(record.get("object_path"))],
        "candidate_state_sha256": state_sha256,
    }


def validate_partition(manifest, context, *, queue_items,
                       coverage_candidates, coverage_pages):
    """Validate manifest/Coverage/Queue set equality for one closed run."""
    errors = []
    for field, expected in (
            ("selected_candidate_ids", context["selected_ids"]),
            ("deferred_candidate_ids", context["deferred_ids"]),
            ("selected_objects", context["selected_objects"])):
        value = manifest.get(field)
        if value != expected:
            errors.append("maintenance budget manifest %s must equal %r" %
                          (field, expected))
    if manifest.get("deferred_count") != len(context["deferred_ids"]):
        errors.append(
            "maintenance budget manifest deferred_count must equal %d" %
            len(context["deferred_ids"]))
    if coverage_candidates != context["records"]:
        errors.append(
            "Coverage maintenance_candidates must equal the frozen manifest candidates")

    queue_order = []
    queue_objects = []
    for item in sorted(queue_items, key=lambda value: value.get("order", 0)):
        queue_order.append(item.get("id"))
        queue_objects.extend(value for value in (item.get("manifest") or [])
                             if _nonempty(value))
    if manifest.get("required_batch_ids") != queue_order:
        errors.append("maintenance budget manifest required_batch_ids must equal %r" %
                      queue_order)
    if sorted(set(queue_objects)) != sorted(context["selected_objects"]):
        errors.append(
            "maintenance selected candidate objects must equal the Queue manifest union")
    page_paths = {record.get("path") for record in coverage_pages
                  if isinstance(record, dict) and
                  _nonempty(record.get("path"))}
    missing = sorted(set(
        record.get("object_path") for record in context["records"]
        if isinstance(record, dict) and
        _nonempty(record.get("object_path"))) - page_paths)
    if missing:
        errors.append("maintenance candidates are absent from Coverage pages: %s" %
                      ", ".join(missing))
    return errors
