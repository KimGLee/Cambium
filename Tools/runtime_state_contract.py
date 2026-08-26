#!/usr/bin/env python3
"""Load and project the Kernel-owned Cambium runtime state model.

The state identities, classes, current transition authorizations, historical
replay catalogs, and control-status closed sets belong to K13.  This module is
their only Tool-side parser and projection.  Writers and validators import the
projections below; they do not maintain private state lists or edge maps.

Current authorization and historical replay are deliberately separate.  A
future writer may move to a new edge catalog without making an already sealed
receipt illegal under the catalog its producer era recorded.
"""

from collections import deque
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType


MODEL_PATH = (
    "kernel/K13 Task Runtime and Execution Control/runtime-state-model.json")
MODEL_ID = "cambium-runtime-state-model-v1"
ORDINARY_QUEUE_TRANSITION_CAPABILITY = "ordinary-queue-transition-v1"
AMENDMENT_BATCH_CANCELLATION_CAPABILITY = \
    "amendment-batch-cancellation-v1"
QUEUE_TRANSITION_REPLAY_PROTOCOL = "queue-transition-receipt-v1"
TASK_TRANSITION_CAPABILITY = "task-state-transition-v1"
TASK_TRANSITION_REPLAY_PROTOCOL = "task-transition-receipt-v1"
CROSS_LEDGER_AMENDMENT_CAPABILITY = "cross-ledger-amendment-v1"
SAME_SCOPE_QUEUE_REPLAN_CAPABILITY = "same-scope-queue-replan-v1"

_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_OWNER_RE = re.compile(r"K13/[0-9]{2}\Z")
_FIELD_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
_QUEUE_STATE_CLASSES = frozenset((
    "terminal", "nonterminal", "active", "actionable-target", "delta-bound",
))
_TASK_STATE_CLASSES = frozenset((
    "terminal", "nonterminal", "active", "batch-activation-current",
    "build-proof-readable",
    "standards-adoption-current", "maintenance-completion-current",
    "maintenance-completion-replay",
))
_AMENDMENT_OPERATION_CLASSES = frozenset((
    "scope-preserving", "state-revision-preserving", "cancel-id-forbidden",
))


class RuntimeStateContractError(ValueError):
    """The Kernel-owned runtime state model is unsafe or malformed."""


def _object_without_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeStateContractError(
                "runtime state model repeats JSON key %r" % key)
        result[key] = value
    return result


def _closed_mapping(value, fields, label):
    if not isinstance(value, dict):
        raise RuntimeStateContractError("%s must be a mapping" % label)
    missing = sorted(set(fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing or extra:
        raise RuntimeStateContractError(
            "%s fields are not closed: missing=%s extra=%s" %
            (label, missing, extra))
    return value


def _string_list(value, label, *, identifiers=False, nonempty=True):
    if not isinstance(value, list):
        raise RuntimeStateContractError("%s must be a list" % label)
    if nonempty and not value:
        raise RuntimeStateContractError("%s must not be empty" % label)
    if any(not isinstance(item, str) or not item for item in value):
        raise RuntimeStateContractError(
            "%s must contain only non-empty strings" % label)
    if len(value) != len(set(value)):
        raise RuntimeStateContractError("%s contains duplicates" % label)
    if identifiers:
        invalid = [item for item in value if _ID_RE.fullmatch(item) is None]
        if invalid:
            raise RuntimeStateContractError(
                "%s contains invalid identifier(s): %s" %
                (label, ", ".join(invalid)))
    return tuple(value)


def _state_records(rows, label, *, allowed_classes,
                   completion_semantics=None):
    if not isinstance(rows, list) or not rows:
        raise RuntimeStateContractError("%s must be a non-empty list" % label)
    records = {}
    fields = {"state_id", "classes"}
    if completion_semantics is not None:
        fields.add("applicable_completion_semantics")
    for index, raw in enumerate(rows):
        item_label = "%s[%d]" % (label, index)
        row = _closed_mapping(raw, fields, item_label)
        state_id = row.get("state_id")
        if not isinstance(state_id, str) or _ID_RE.fullmatch(state_id) is None:
            raise RuntimeStateContractError(
                "%s.state_id is invalid" % item_label)
        if state_id in records:
            raise RuntimeStateContractError(
                "%s repeats state %s" % (label, state_id))
        classes = _string_list(
            row.get("classes"), item_label + ".classes", identifiers=True)
        unknown_classes = sorted(set(classes) - set(allowed_classes))
        if unknown_classes:
            raise RuntimeStateContractError(
                "%s has unknown state class(es): %s" %
                (item_label, ", ".join(unknown_classes)))
        terminal_classes = {"terminal", "nonterminal"}.intersection(classes)
        if len(terminal_classes) != 1:
            raise RuntimeStateContractError(
                "%s must be exactly one of terminal or nonterminal" %
                item_label)
        if "active" in classes and "nonterminal" not in classes:
            raise RuntimeStateContractError(
                "%s active state must be nonterminal" % item_label)
        record = {"classes": frozenset(classes)}
        if completion_semantics is not None:
            applicable = _string_list(
                row.get("applicable_completion_semantics"),
                item_label + ".applicable_completion_semantics",
                identifiers=True,
            )
            unknown = sorted(set(applicable) - set(completion_semantics))
            if unknown:
                raise RuntimeStateContractError(
                    "%s has unknown completion semantics: %s" %
                    (item_label, ", ".join(unknown)))
            record["applicable_completion_semantics"] = frozenset(applicable)
        records[state_id] = record
    unused_classes = sorted(
        set(allowed_classes) - {
            class_id
            for record in records.values()
            for class_id in record["classes"]
        })
    if unused_classes:
        raise RuntimeStateContractError(
            "%s has no member for state class(es): %s" %
            (label, ", ".join(unused_classes)))
    return records


def _ledger_records(rows):
    if not isinstance(rows, list) or not rows:
        raise RuntimeStateContractError(
            "runtime_ledgers must be a non-empty list")
    records = {}
    fields = {"ledger_id", "fingerprint_field"}
    seen_fingerprints = set()
    for index, raw in enumerate(rows):
        label = "runtime_ledgers[%d]" % index
        row = _closed_mapping(raw, fields, label)
        ledger_id = row.get("ledger_id")
        fingerprint = row.get("fingerprint_field")
        if not isinstance(ledger_id, str) or _ID_RE.fullmatch(ledger_id) is None:
            raise RuntimeStateContractError("%s.ledger_id is invalid" % label)
        if ledger_id in records:
            raise RuntimeStateContractError(
                "runtime_ledgers repeats %s" % ledger_id)
        if (not isinstance(fingerprint, str) or
                _FIELD_RE.fullmatch(fingerprint) is None):
            raise RuntimeStateContractError(
                "%s.fingerprint_field is invalid" % label)
        if fingerprint in seen_fingerprints:
            raise RuntimeStateContractError(
                "runtime_ledgers repeats fingerprint field %s" % fingerprint)
        seen_fingerprints.add(fingerprint)
        records[ledger_id] = fingerprint
    return records


def _amendment_operation_records(rows):
    if not isinstance(rows, list) or not rows:
        raise RuntimeStateContractError(
            "operational_amendment_operations must be a non-empty list")
    records = {}
    classes_by_operation = {}
    fields = {"operation_id", "execution_capability", "classes"}
    for index, raw in enumerate(rows):
        label = "progress_controls.operational_amendment_operations[%d]" % index
        row = _closed_mapping(raw, fields, label)
        operation_id = row.get("operation_id")
        capability = row.get("execution_capability")
        if (not isinstance(operation_id, str) or
                _ID_RE.fullmatch(operation_id) is None):
            raise RuntimeStateContractError(
                "%s.operation_id is invalid" % label)
        if operation_id in records:
            raise RuntimeStateContractError(
                "operational Amendment operation %s is repeated" %
                operation_id)
        if (not isinstance(capability, str) or
                _ID_RE.fullmatch(capability) is None):
            raise RuntimeStateContractError(
                "%s.execution_capability is invalid" % label)
        classes = _string_list(
            row.get("classes"), label + ".classes",
            identifiers=True, nonempty=False)
        unknown_classes = sorted(
            set(classes) - set(_AMENDMENT_OPERATION_CLASSES))
        if unknown_classes:
            raise RuntimeStateContractError(
                "%s has unknown operation class(es): %s" %
                (label, ", ".join(unknown_classes)))
        records[operation_id] = capability
        classes_by_operation[operation_id] = classes
    return records, classes_by_operation


def _amendment_finality_records(rows, statuses):
    if not isinstance(rows, list) or not rows:
        raise RuntimeStateContractError(
            "amendment_finality must be a non-empty list")
    records = {}
    fields = {"status_id", "required_writeback_done"}
    for index, raw in enumerate(rows):
        label = "progress_controls.amendment_finality[%d]" % index
        row = _closed_mapping(raw, fields, label)
        status_id = row.get("status_id")
        if status_id not in statuses:
            raise RuntimeStateContractError(
                "%s.status_id is not an Amendment status" % label)
        if status_id in records:
            raise RuntimeStateContractError(
                "amendment_finality repeats status %s" % status_id)
        required = row.get("required_writeback_done")
        if required is not None and not isinstance(required, bool):
            raise RuntimeStateContractError(
                "%s.required_writeback_done must be true, false, or null" %
                label)
        records[status_id] = required
    return records


def _edge_catalogs(rows, states, label, *, completion_semantics=None):
    if not isinstance(rows, list) or not rows:
        raise RuntimeStateContractError("%s must be a non-empty list" % label)
    catalogs = {}
    fields = {"catalog_id", "edges"}
    if completion_semantics is not None:
        fields.add("completion_semantics")
    for index, raw in enumerate(rows):
        item_label = "%s[%d]" % (label, index)
        row = _closed_mapping(raw, fields, item_label)
        catalog_id = row.get("catalog_id")
        if not isinstance(catalog_id, str) or _ID_RE.fullmatch(catalog_id) is None:
            raise RuntimeStateContractError(
                "%s.catalog_id is invalid" % item_label)
        if catalog_id in catalogs:
            raise RuntimeStateContractError(
                "%s repeats catalog %s" % (label, catalog_id))
        semantic = None
        if completion_semantics is not None:
            semantic = row.get("completion_semantics")
            if semantic not in completion_semantics:
                raise RuntimeStateContractError(
                    "%s.completion_semantics is unknown" % item_label)
        raw_edges = row.get("edges")
        if not isinstance(raw_edges, list) or not raw_edges:
            raise RuntimeStateContractError(
                "%s.edges must be a non-empty list" % item_label)
        edges = []
        seen = set()
        for edge_index, raw_edge in enumerate(raw_edges):
            edge_label = "%s.edges[%d]" % (item_label, edge_index)
            if (not isinstance(raw_edge, list) or len(raw_edge) != 2 or
                    any(not isinstance(value, str) or not value
                        for value in raw_edge)):
                raise RuntimeStateContractError(
                    "%s must be [before, after]" % edge_label)
            edge = tuple(raw_edge)
            if edge[0] == edge[1]:
                raise RuntimeStateContractError(
                    "%s may not be a no-op" % edge_label)
            unknown = sorted(set(edge) - set(states))
            if unknown:
                raise RuntimeStateContractError(
                    "%s names unknown state(s): %s" %
                    (edge_label, ", ".join(unknown)))
            if edge in seen:
                raise RuntimeStateContractError(
                    "%s repeats edge %s -> %s" %
                    (item_label, edge[0], edge[1]))
            if semantic is not None:
                for state_id in edge:
                    applicable = states[state_id][
                        "applicable_completion_semantics"]
                    if semantic not in applicable:
                        raise RuntimeStateContractError(
                            "%s uses state %s outside %s semantics" %
                            (edge_label, state_id, semantic))
            seen.add(edge)
            edges.append(edge)
        catalogs[catalog_id] = {
            "completion_semantics": semantic,
            "edges": frozenset(edges),
        }
    return catalogs


def _authorization_records(rows, catalogs, label, *, historical=False,
                           completion_semantics=None):
    if not isinstance(rows, list) or not rows:
        raise RuntimeStateContractError("%s must be a non-empty list" % label)
    id_field = "protocol_id" if historical else "capability_id"
    fields = {id_field, "edge_catalog_ids"}
    if completion_semantics is not None:
        fields.add("completion_semantics")
    records = {}
    referenced = set()
    for index, raw in enumerate(rows):
        item_label = "%s[%d]" % (label, index)
        row = _closed_mapping(raw, fields, item_label)
        identity = row.get(id_field)
        if not isinstance(identity, str) or _ID_RE.fullmatch(identity) is None:
            raise RuntimeStateContractError(
                "%s.%s is invalid" % (item_label, id_field))
        semantic = None
        if completion_semantics is not None:
            semantic = row.get("completion_semantics")
            if semantic not in completion_semantics:
                raise RuntimeStateContractError(
                    "%s.completion_semantics is unknown" % item_label)
        key = (identity, semantic) if completion_semantics is not None else identity
        if key in records:
            raise RuntimeStateContractError(
                "%s repeats authorization %r" % (label, key))
        catalog_ids = _string_list(
            row.get("edge_catalog_ids"), item_label + ".edge_catalog_ids",
            identifiers=True,
        )
        unknown = sorted(set(catalog_ids) - set(catalogs))
        if unknown:
            raise RuntimeStateContractError(
                "%s references unknown catalog(s): %s" %
                (item_label, ", ".join(unknown)))
        edges = set()
        for catalog_id in catalog_ids:
            catalog = catalogs[catalog_id]
            if (semantic is not None and
                    catalog["completion_semantics"] != semantic):
                raise RuntimeStateContractError(
                    "%s references %s for different completion semantics" %
                    (item_label, catalog_id))
            overlap = edges.intersection(catalog["edges"])
            if overlap:
                before, after = sorted(overlap)[0]
                raise RuntimeStateContractError(
                    "%s composes duplicate edge %s -> %s" %
                    (item_label, before, after))
            edges.update(catalog["edges"])
            referenced.add(catalog_id)
        records[key] = {
            "catalog_ids": tuple(catalog_ids),
            "edges": frozenset(edges),
        }
    return records, referenced


def validate_model(document):
    """Validate and return parsed state-model components."""
    root = _closed_mapping(document, {
        "schema_version", "model_id", "owner_refs", "runtime_ledgers",
        "queue", "task", "guidance", "progress_controls",
    }, "runtime state model")
    if root.get("schema_version") != 1:
        raise RuntimeStateContractError(
            "runtime state model schema_version must be 1")
    if root.get("model_id") != MODEL_ID:
        raise RuntimeStateContractError(
            "runtime state model model_id must be %s" % MODEL_ID)
    owner_refs = _string_list(root.get("owner_refs"), "owner_refs")
    if any(_OWNER_RE.fullmatch(value) is None for value in owner_refs):
        raise RuntimeStateContractError(
            "owner_refs must contain only K13/NN references")
    runtime_ledgers = _ledger_records(root.get("runtime_ledgers"))

    queue = _closed_mapping(root.get("queue"), {
        "states", "hold_states", "execution_modes", "edge_catalogs",
        "current_authorizations", "historical_replay",
    }, "queue")
    queue_states = _state_records(
        queue.get("states"), "queue.states",
        allowed_classes=_QUEUE_STATE_CLASSES)
    hold_states = _string_list(
        queue.get("hold_states"), "queue.hold_states", identifiers=True)
    execution_modes = _string_list(
        queue.get("execution_modes"), "queue.execution_modes",
        identifiers=True)
    queue_catalogs = _edge_catalogs(
        queue.get("edge_catalogs"), queue_states, "queue.edge_catalogs")
    queue_current, queue_current_refs = _authorization_records(
        queue.get("current_authorizations"), queue_catalogs,
        "queue.current_authorizations")
    queue_history, queue_history_refs = _authorization_records(
        queue.get("historical_replay"), queue_catalogs,
        "queue.historical_replay", historical=True)
    expected_queue_capabilities = {
        ORDINARY_QUEUE_TRANSITION_CAPABILITY,
        AMENDMENT_BATCH_CANCELLATION_CAPABILITY,
    }
    if set(queue_current) != expected_queue_capabilities:
        raise RuntimeStateContractError(
            "queue current authorization capabilities must be %s" %
            ", ".join(sorted(expected_queue_capabilities)))
    if set(queue_history) != {QUEUE_TRANSITION_REPLAY_PROTOCOL}:
        raise RuntimeStateContractError(
            "queue historical replay protocol must be %s" %
            QUEUE_TRANSITION_REPLAY_PROTOCOL)
    seen_current_edges = {}
    for capability, record in queue_current.items():
        for edge in record["edges"]:
            previous = seen_current_edges.get(edge)
            if previous is not None:
                raise RuntimeStateContractError(
                    "queue current edge %s -> %s is authorized by both %s "
                    "and %s" % (edge[0], edge[1], previous, capability))
            seen_current_edges[edge] = capability
    unreferenced = sorted(
        set(queue_catalogs) - queue_current_refs - queue_history_refs)
    if unreferenced:
        raise RuntimeStateContractError(
            "queue edge catalog(s) are unreferenced: %s" %
            ", ".join(unreferenced))
    current_queue_edges = set()
    for record in queue_current.values():
        current_queue_edges.update(record["edges"])
    terminal_queue_states = {
        state_id for state_id, row in queue_states.items()
        if "terminal" in row["classes"]
    }
    terminal_sources = sorted({
        before for before, _after in current_queue_edges
        if before in terminal_queue_states
    })
    if terminal_sources:
        raise RuntimeStateContractError(
            "terminal queue states have current outgoing edges: %s" %
            ", ".join(terminal_sources))

    task = _closed_mapping(root.get("task"), {
        "completion_semantics", "states", "edge_catalogs",
        "current_authorizations", "historical_replay",
    }, "task")
    completion_semantics = _string_list(
        task.get("completion_semantics"), "task.completion_semantics",
        identifiers=True)
    task_states = _state_records(
        task.get("states"), "task.states",
        allowed_classes=_TASK_STATE_CLASSES,
        completion_semantics=completion_semantics)
    task_catalogs = _edge_catalogs(
        task.get("edge_catalogs"), task_states, "task.edge_catalogs",
        completion_semantics=completion_semantics)
    task_current, task_current_refs = _authorization_records(
        task.get("current_authorizations"), task_catalogs,
        "task.current_authorizations",
        completion_semantics=completion_semantics)
    task_history, task_history_refs = _authorization_records(
        task.get("historical_replay"), task_catalogs,
        "task.historical_replay", historical=True,
        completion_semantics=completion_semantics)
    expected_task_current = {
        (TASK_TRANSITION_CAPABILITY, semantic)
        for semantic in completion_semantics
    }
    expected_task_history = {
        (TASK_TRANSITION_REPLAY_PROTOCOL, semantic)
        for semantic in completion_semantics
    }
    if set(task_current) != expected_task_current:
        raise RuntimeStateContractError(
            "task current authorization must use %s for every completion "
            "semantics" % TASK_TRANSITION_CAPABILITY)
    if set(task_history) != expected_task_history:
        raise RuntimeStateContractError(
            "task historical replay must use %s for every completion "
            "semantics" % TASK_TRANSITION_REPLAY_PROTOCOL)
    unreferenced = sorted(
        set(task_catalogs) - task_current_refs - task_history_refs)
    if unreferenced:
        raise RuntimeStateContractError(
            "task edge catalog(s) are unreferenced: %s" %
            ", ".join(unreferenced))
    for semantic in completion_semantics:
        current_matches = [
            key for key in task_current if key[1] == semantic]
        historical_matches = [
            key for key in task_history if key[1] == semantic]
        if len(current_matches) != 1 or len(historical_matches) != 1:
            raise RuntimeStateContractError(
                "task completion semantics %s must have exactly one current "
                "and one historical transition authorization" % semantic)
    terminal_task_states = {
        state_id for state_id, row in task_states.items()
        if "terminal" in row["classes"]
    }
    terminal_sources = sorted({
        before for record in task_current.values()
        for before, _after in record["edges"]
        if before in terminal_task_states
    })
    if terminal_sources:
        raise RuntimeStateContractError(
            "terminal task states have current outgoing edges: %s" %
            ", ".join(terminal_sources))

    guidance = _closed_mapping(root.get("guidance"), {
        "dispositions", "statuses", "final_statuses",
    }, "guidance")
    guidance_dispositions = _string_list(
        guidance.get("dispositions"), "guidance.dispositions",
        identifiers=True)
    guidance_statuses = _string_list(
        guidance.get("statuses"), "guidance.statuses", identifiers=True)
    final_guidance_statuses = _string_list(
        guidance.get("final_statuses"), "guidance.final_statuses",
        identifiers=True)
    if not set(final_guidance_statuses).issubset(guidance_statuses):
        raise RuntimeStateContractError(
            "guidance.final_statuses must be a subset of guidance.statuses")

    controls = _closed_mapping(root.get("progress_controls"), {
        "amendment_statuses", "amendment_finality",
        "terminal_audit_states", "maintenance_completion_states",
        "operational_amendment_operations",
    }, "progress_controls")
    amendment_statuses = _string_list(
        controls.get("amendment_statuses"),
        "progress_controls.amendment_statuses", identifiers=True)
    amendment_finality = _amendment_finality_records(
        controls.get("amendment_finality"), amendment_statuses)
    terminal_audit_states = _string_list(
        controls.get("terminal_audit_states"),
        "progress_controls.terminal_audit_states", identifiers=True)
    maintenance_completion_states = _string_list(
        controls.get("maintenance_completion_states"),
        "progress_controls.maintenance_completion_states", identifiers=True)
    amendment_operations, amendment_operation_classes = \
        _amendment_operation_records(
        controls.get("operational_amendment_operations"))
    unknown_amendment_capabilities = sorted(
        set(amendment_operations.values()) - {
            CROSS_LEDGER_AMENDMENT_CAPABILITY,
            SAME_SCOPE_QUEUE_REPLAN_CAPABILITY,
        })
    if unknown_amendment_capabilities:
        raise RuntimeStateContractError(
            "operational Amendment operations name unknown execution "
            "capability: %s" % ", ".join(unknown_amendment_capabilities))
    if not set(guidance_statuses).issubset(amendment_statuses):
        raise RuntimeStateContractError(
            "every Guidance status must also be a valid Amendment-log status")

    return {
        "document": document,
        "runtime_ledgers": runtime_ledgers,
        "queue_states": queue_states,
        "hold_states": hold_states,
        "execution_modes": execution_modes,
        "queue_catalogs": queue_catalogs,
        "queue_current": queue_current,
        "queue_history": queue_history,
        "completion_semantics": completion_semantics,
        "task_states": task_states,
        "task_catalogs": task_catalogs,
        "task_current": task_current,
        "task_history": task_history,
        "guidance_dispositions": guidance_dispositions,
        "guidance_statuses": guidance_statuses,
        "final_guidance_statuses": final_guidance_statuses,
        "amendment_statuses": amendment_statuses,
        "amendment_finality": amendment_finality,
        "terminal_audit_states": terminal_audit_states,
        "maintenance_completion_states": maintenance_completion_states,
        "amendment_operations": amendment_operations,
        "amendment_operation_classes": amendment_operation_classes,
    }


def _model_file(root):
    root_path = Path(root).resolve()
    candidate = root_path.joinpath(*MODEL_PATH.split("/"))
    try:
        candidate.relative_to(root_path)
    except ValueError:
        raise RuntimeStateContractError("runtime state model escapes root")
    current = root_path
    for part in MODEL_PATH.split("/"):
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise RuntimeStateContractError(
                "%s is missing or unreadable: %s" % (MODEL_PATH, exc))
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeStateContractError(
                "%s may not traverse a symlink" % MODEL_PATH)
    if not stat.S_ISREG(os.lstat(candidate).st_mode):
        raise RuntimeStateContractError("%s is not a regular file" % MODEL_PATH)
    return candidate


def load_model(root=None):
    """Load and strictly validate the Kernel-owned state model under ``root``."""
    if root is None:
        root = Path(__file__).resolve().parent.parent
    path = _model_file(root)
    try:
        text = path.read_text(encoding="utf-8")
        document = json.loads(
            text, object_pairs_hook=_object_without_duplicate_keys)
    except RuntimeStateContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeStateContractError(
            "%s is invalid JSON: %s" % (MODEL_PATH, exc))
    return validate_model(document)


def _class_members(states, class_id):
    return frozenset(
        state_id for state_id, row in states.items()
        if class_id in row["classes"])


def _transition_map(states, edges):
    values = {state_id: set() for state_id in states}
    for before, after in edges:
        values[before].add(after)
    return MappingProxyType({
        state_id: frozenset(values[state_id]) for state_id in states
    })


def reachable_batch_states(state):
    """Return transitive ordinary-writer destinations from one Queue state."""
    if state not in BATCH_LIFECYCLE_TRANSITIONS:
        return frozenset()
    found = set()
    pending = deque(BATCH_LIFECYCLE_TRANSITIONS[state])
    while pending:
        candidate = pending.pop()
        if candidate in found:
            continue
        found.add(candidate)
        pending.extend(BATCH_LIFECYCLE_TRANSITIONS.get(candidate, ()))
    return frozenset(found)


def task_transition_is_authorized(completion_semantics, before, after,
                                  *, historical=False):
    """Test one current writer edge or one producer-era replay edge."""
    source = (TASK_HISTORICAL_TRANSITIONS_BY_SEMANTICS if historical else
              TASK_TRANSITIONS_BY_SEMANTICS)
    return (before, after) in source.get(completion_semantics, frozenset())


def amendment_is_final(status, writeback_done):
    """Apply the Kernel-owned status and write-back finality predicate."""
    if status not in AMENDMENT_FINALITY_REQUIREMENTS:
        return False
    required = AMENDMENT_FINALITY_REQUIREMENTS[status]
    return required is None or writeback_done is required


_MODEL = load_model()

RUNTIME_LEDGER_IDS = tuple(_MODEL["runtime_ledgers"])
RUNTIME_LEDGER_FINGERPRINT_FIELDS = frozenset(
    _MODEL["runtime_ledgers"].values())
RUNTIME_LEDGER_FINGERPRINT_BY_ID = MappingProxyType(
    dict(_MODEL["runtime_ledgers"]))
RUNTIME_STANDARDS_IDENTITY_FIELDS = (
    "standards_version", "selected_profile_manifest",
)
RUNTIME_CONTROL_IDENTITY_FIELDS = (
    "task_id", "scope_version",
) + RUNTIME_STANDARDS_IDENTITY_FIELDS

QUEUE_STATE_ORDER = tuple(_MODEL["queue_states"])
QUEUE_STATES = frozenset(QUEUE_STATE_ORDER)
QUEUE_ACTIVE_STATES = _class_members(_MODEL["queue_states"], "active")
QUEUE_TERMINAL_STATES = _class_members(_MODEL["queue_states"], "terminal")
QUEUE_NONTERMINAL_STATES = _class_members(
    _MODEL["queue_states"], "nonterminal")
QUEUE_ACTIONABLE_TARGET_STATES = _class_members(
    _MODEL["queue_states"], "actionable-target")
QUEUE_DELTA_BOUND_STATES = _class_members(
    _MODEL["queue_states"], "delta-bound")
QUEUE_HOLD_STATES = frozenset(_MODEL["hold_states"])
EXECUTION_MODES = frozenset(_MODEL["execution_modes"])

BATCH_TRANSITIONS_BY_CAPABILITY = MappingProxyType({
    key: record["edges"] for key, record in _MODEL["queue_current"].items()
})
BATCH_HISTORICAL_LIFECYCLE_EDGES = _MODEL["queue_history"][
    QUEUE_TRANSITION_REPLAY_PROTOCOL]["edges"]
BATCH_LIFECYCLE_TRANSITIONS = _transition_map(
    QUEUE_STATES,
    BATCH_TRANSITIONS_BY_CAPABILITY[ORDINARY_QUEUE_TRANSITION_CAPABILITY],
)
BATCH_OPENING_SOURCE_STATES = frozenset(
    before
    for before, after in BATCH_TRANSITIONS_BY_CAPABILITY[
        ORDINARY_QUEUE_TRANSITION_CAPABILITY]
    if after == "open"
)
QUEUE_STARTED_STATES = reachable_batch_states("queued")
BATCH_CANCELLATION_SOURCE_STATES = frozenset(
    before
    for before, _after in BATCH_TRANSITIONS_BY_CAPABILITY[
        AMENDMENT_BATCH_CANCELLATION_CAPABILITY]
)

COMPLETION_SEMANTICS = frozenset(_MODEL["completion_semantics"])
TASK_STATE_ORDER = tuple(_MODEL["task_states"])
TASK_STATES = frozenset(TASK_STATE_ORDER)
TASK_ACTIVE_STATES = _class_members(_MODEL["task_states"], "active")
BATCH_ACTIVATION_TASK_STATES = _class_members(
    _MODEL["task_states"], "batch-activation-current")
TASK_TERMINAL_STATES = _class_members(_MODEL["task_states"], "terminal")
TASK_NONTERMINAL_STATES = _class_members(
    _MODEL["task_states"], "nonterminal")
BUILD_PROOF_TASK_STATES = _class_members(
    _MODEL["task_states"], "build-proof-readable")
STANDARDS_ADOPTION_TASK_STATES = _class_members(
    _MODEL["task_states"], "standards-adoption-current")
MAINTENANCE_COMPLETION_TASK_STATES = _class_members(
    _MODEL["task_states"], "maintenance-completion-current")
MAINTENANCE_COMPLETION_REPLAY_TASK_STATES = _class_members(
    _MODEL["task_states"], "maintenance-completion-replay")
TASK_TRANSITIONS_BY_SEMANTICS = MappingProxyType({
    semantic: record["edges"]
    for (capability, semantic), record in _MODEL["task_current"].items()
    if capability == TASK_TRANSITION_CAPABILITY
})
TASK_HISTORICAL_TRANSITIONS_BY_SEMANTICS = MappingProxyType({
    semantic: record["edges"]
    for (protocol, semantic), record in _MODEL["task_history"].items()
    if protocol == TASK_TRANSITION_REPLAY_PROTOCOL
})

GUIDANCE_DISPOSITIONS = frozenset(_MODEL["guidance_dispositions"])
GUIDANCE_STATUSES = frozenset(_MODEL["guidance_statuses"])
FINAL_GUIDANCE_STATUSES = frozenset(_MODEL["final_guidance_statuses"])
AMENDMENT_STATUSES = frozenset(_MODEL["amendment_statuses"])
AMENDMENT_FINALITY_REQUIREMENTS = MappingProxyType(
    dict(_MODEL["amendment_finality"]))
TERMINAL_AUDIT_STATES = frozenset(_MODEL["terminal_audit_states"])
MAINTENANCE_COMPLETION_STATES = frozenset(
    _MODEL["maintenance_completion_states"])
OPERATIONAL_AMENDMENT_OPERATIONS = frozenset(_MODEL["amendment_operations"])
AMENDMENT_OPERATIONS_BY_EXECUTION_CAPABILITY = MappingProxyType({
    capability: frozenset(
        operation_id
        for operation_id, registered_capability in
        _MODEL["amendment_operations"].items()
        if registered_capability == capability
    )
    for capability in frozenset(_MODEL["amendment_operations"].values())
})
AMENDMENT_OPERATIONS_BY_CLASS = MappingProxyType({
    class_id: frozenset(
        operation_id
        for operation_id, classes in
        _MODEL["amendment_operation_classes"].items()
        if class_id in classes
    )
    for class_id in _AMENDMENT_OPERATION_CLASSES
})
SCOPE_PRESERVING_AMENDMENT_OPERATIONS = \
    AMENDMENT_OPERATIONS_BY_CLASS["scope-preserving"]
STATE_REVISION_PRESERVING_AMENDMENT_OPERATIONS = \
    AMENDMENT_OPERATIONS_BY_CLASS["state-revision-preserving"]
CANCEL_ID_FORBIDDEN_AMENDMENT_OPERATIONS = \
    AMENDMENT_OPERATIONS_BY_CLASS["cancel-id-forbidden"]

# Compatibility projections for the long-standing queue_runtime facade.
STATES = QUEUE_STATES
HOLDS = QUEUE_HOLD_STATES
ACTIVE_STATES = QUEUE_ACTIVE_STATES
TERMINAL_STATES = QUEUE_TERMINAL_STATES
