"""Is a complex batch's immutable Agent-readable Work Spec well formed.

A closed grammar, checked closed: an unknown field is a refusal, not an
ignored key.  The simple/complex declaration is checked here too, and it must
be exactly one of the two legal spellings -- a third spelling would let a
complex batch pass as simple, which is the failure the Work Spec exists to
prevent.
"""

import os
import re
from pathlib import Path

import kblib
import runtime_paths
import work_spec_contract

from queue_runtime.canon import SHA256_RE
from queue_runtime.primitives import nonempty_string


WORK_SPEC_PREFIX = runtime_paths.WORK_SPEC_ROOT
WORK_SPEC_FIELDS = work_spec_contract.WORK_SPEC_BINDING_FIELDS
WORK_SPEC_TOP_LEVEL_FIELDS = frozenset((
    "schema_version", "batch_id", "manifest", "outcomes", "instructions",
    "acceptance_conditions", "constraints",
))
WORK_SPEC_OUTCOME_FIELDS = frozenset(("outcome_id", "required_result"))
WORK_SPEC_INSTRUCTION_FIELDS = frozenset((
    "instruction_id", "order", "target_scope", "required_transformation",
    "depends_on",
))
WORK_SPEC_ACCEPTANCE_FIELDS = frozenset((
    "condition_id", "target_scope", "observable_predicate",
    "evidence_requirement",
))
WORK_SPEC_CONSTRAINT_FIELDS = frozenset((
    "constraint_id", "target_scope", "requirement",
))
WORK_SPEC_QUEUE_OWNED_FIELDS = frozenset((
    "id", "family", "order", "record_count", "source_route",
    "execution_mode", "depends_on", "confirmation_required", "state",
    "lifecycle", "hold", "hold_state", "opened_at", "activation_receipt",
    "confirmation_receipt", "merge_ready_at", "delta_path",
    "delta_sha256", "closed_at", "queue_consistency_receipt",
    "close_gate_receipt", "delta_apply_receipt", "cancelled_at",
    "cancellation_amendment", "hold_reason", "successor_of",
    "invalidation_history",
    "queue_revision", "state_revision", "revision", "receipts",
    "transition_receipts", "batch_receipts", "revalidation_receipts",
)).union(WORK_SPEC_FIELDS)
WORK_SPEC_RECORD_ID_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\Z"
)
WORK_SPEC_SENTINELS = ("TODO(batch)", "REPLACE-ME")


def work_spec_binding_errors(path, fingerprint, label):
    """Validate one explicit simple/complex batch declaration.

    Null/null is the only spelling for a simple batch.  A complex batch must
    bind both a managed restricted-YAML path and exact lowercase SHA-256.  The pair
    intentionally carries no inferred complexity flag: omission is invalid.
    """
    errors = []
    if path is None and fingerprint is None:
        return errors
    if path is None or fingerprint is None:
        errors.append(
            "%s work_spec_path and work_spec_sha256 must both be null or "
            "both be non-null" % label
        )
        return errors
    if not nonempty_string(path):
        errors.append("%s work_spec_path must be null or a non-empty string" %
                      label)
    elif (not path.startswith(WORK_SPEC_PREFIX + "/") or
          not path.endswith(".yaml") or
          Path(path).parent.as_posix() != WORK_SPEC_PREFIX):
        errors.append(
            "%s work_spec_path must be a YAML file directly inside %s/" %
            (label, WORK_SPEC_PREFIX)
        )
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
        errors.append(
            "%s work_spec_sha256 must be null or sha256:<64 lowercase hex>" %
            label
        )
    return errors


def _closed_work_spec_mapping_errors(value, expected_fields, label):
    """Validate one mapping node in the closed Work Spec grammar."""
    if not isinstance(value, dict):
        return ["%s must be a mapping" % label]
    actual = set(value)
    missing = sorted(expected_fields - actual)
    extra = sorted(actual - expected_fields)
    errors = []
    if missing:
        errors.append("%s misses field(s): %s" % (label, ", ".join(missing)))
    if extra:
        queue_owned = sorted(set(extra).intersection(
            WORK_SPEC_QUEUE_OWNED_FIELDS))
        if queue_owned:
            errors.append(
                "%s must not declare Queue-owned field(s): %s" %
                (label, ", ".join(queue_owned))
            )
        errors.append("%s has unsupported field(s): %s" %
                      (label, ", ".join(extra)))
    return errors


def _work_spec_id_errors(value, label):
    if (not isinstance(value, str) or
            not WORK_SPEC_RECORD_ID_RE.fullmatch(value)):
        return ["%s must match %s" %
                (label, WORK_SPEC_RECORD_ID_RE.pattern.replace("\\Z", ""))]
    return []


def _work_spec_target_scope_errors(value, manifest, label):
    errors = []
    if (not isinstance(value, list) or not value or
            not all(nonempty_string(entry) for entry in value)):
        return [
            "%s must be a non-empty explicit string list containing "
            "'batch' or Queue manifest paths" % label
        ]
    if len(set(value)) != len(value):
        errors.append("%s must not contain duplicate targets" % label)
    has_batch = "batch" in value
    if has_batch and value != ["batch"]:
        errors.append(
            "%s must be exactly ['batch'] or contain only Queue manifest "
            "paths; batch and paths cannot be mixed" % label
        )
    elif not has_batch:
        unknown = [entry for entry in value if entry not in manifest]
        if unknown:
            errors.append(
                "%s contains target(s) outside the Queue manifest: %s" %
                (label, ", ".join(unknown))
            )
    return errors


def _nested_queue_owned_work_spec_fields(value, path=()):
    """Return Queue-owned keys hidden below otherwise scalar/list fields.

    ``instructions[].order`` and ``instructions[].depends_on`` are the only
    intentional spelling overlaps with Queue item keys.  Exact mapping checks
    govern those positions; every other occurrence is a forbidden second
    source of runtime state.
    """
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            allowed_overlap = (
                len(path) == 2 and path[0] == "instructions" and
                isinstance(path[1], int) and key in ("order", "depends_on")
            )
            if key in WORK_SPEC_QUEUE_OWNED_FIELDS and not allowed_overlap:
                found.append(".".join(str(part) for part in path + (key,)))
            found.extend(_nested_queue_owned_work_spec_fields(
                child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_nested_queue_owned_work_spec_fields(
                child, path + (index,)))
    return found


def _work_spec_sentinel_paths(value, path=()):
    """Return scalar locations containing an unfilled Work Spec sentinel."""
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(_work_spec_sentinel_paths(child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_work_spec_sentinel_paths(child, path + (index,)))
    elif isinstance(value, str) and any(
            sentinel in value for sentinel in WORK_SPEC_SENTINELS):
        found.append(".".join(str(part) for part in path))
    return found


def work_spec_errors(root, item):
    """Validate a complex batch's immutable Agent-readable work contract."""
    item_id = item.get("id", "<unknown>")
    label = "Queue item %s" % item_id
    path = item.get("work_spec_path")
    fingerprint = item.get("work_spec_sha256")
    errors = work_spec_binding_errors(path, fingerprint, label)
    if errors or path is None:
        return errors
    try:
        absolute = kblib.managed_repository_path(
            root, path, WORK_SPEC_PREFIX, suffixes=(".yaml",), must_exist=True,
        )
        if not os.path.isfile(absolute):
            raise ValueError("path is not a regular file")
        with open(absolute, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append("%s Work Spec is unsafe or unreadable: %s" %
                      (label, exc))
        return errors
    actual = kblib.sha256_file(absolute)
    if actual != fingerprint:
        errors.append(
            "%s Work Spec SHA mismatch: Queue=%s actual=%s" %
            (label, fingerprint, actual)
        )
    try:
        metadata = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        errors.append("%s Work Spec is invalid restricted YAML: %s" %
                      (label, exc))
        return errors
    if not isinstance(metadata, dict):
        errors.append("%s Work Spec must be a top-level mapping" % label)
        return errors
    queue_owned = sorted(set(
        _nested_queue_owned_work_spec_fields(metadata)))
    if queue_owned:
        errors.append(
            "%s Work Spec must not declare Queue-owned field path(s): %s" %
            (label, ", ".join(queue_owned))
        )
    errors.extend(_closed_work_spec_mapping_errors(
        metadata, WORK_SPEC_TOP_LEVEL_FIELDS, "%s Work Spec" % label))
    schema_version = metadata.get("schema_version")
    if (not isinstance(schema_version, int) or
            isinstance(schema_version, bool) or schema_version != 1):
        errors.append("%s Work Spec schema_version must be 1" % label)
    if metadata.get("batch_id") != item_id:
        errors.append(
            "%s Work Spec batch_id=%r does not equal Queue id %r" %
            (label, metadata.get("batch_id"), item_id)
        )
    manifest = metadata.get("manifest")
    queue_manifest = item.get("manifest")
    scope_manifest = queue_manifest if isinstance(queue_manifest, list) else []
    if (not isinstance(manifest, list) or
            not all(nonempty_string(value) for value in manifest)):
        errors.append("%s Work Spec manifest must be an explicit string list" %
                      label)
    elif manifest != queue_manifest:
        errors.append(
            "%s Work Spec manifest must exactly equal Queue manifest in "
            "membership and order" % label
        )
    outcomes = metadata.get("outcomes")
    instructions = metadata.get("instructions")
    conditions = metadata.get("acceptance_conditions")
    constraints = metadata.get("constraints")
    list_contracts = (
        ("outcomes", outcomes, WORK_SPEC_OUTCOME_FIELDS),
        ("instructions", instructions, WORK_SPEC_INSTRUCTION_FIELDS),
        ("acceptance_conditions", conditions, WORK_SPEC_ACCEPTANCE_FIELDS),
        ("constraints", constraints, WORK_SPEC_CONSTRAINT_FIELDS),
    )
    for list_name, records, fields in list_contracts:
        if not isinstance(records, list) or not records:
            errors.append(
                "%s Work Spec %s must be a non-empty list" %
                (label, list_name)
            )
            continue
        for index, record in enumerate(records, 1):
            errors.extend(_closed_work_spec_mapping_errors(
                record, fields, "%s Work Spec %s[%d]" %
                (label, list_name, index)))

    id_contracts = (
        ("outcomes", outcomes, "outcome_id"),
        ("instructions", instructions, "instruction_id"),
        ("acceptance_conditions", conditions, "condition_id"),
        ("constraints", constraints, "constraint_id"),
    )
    for list_name, records, id_field in id_contracts:
        if not isinstance(records, list):
            continue
        seen = set()
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict):
                continue
            identifier = record.get(id_field)
            errors.extend(_work_spec_id_errors(
                identifier, "%s Work Spec %s[%d].%s" %
                (label, list_name, index, id_field)))
            if isinstance(identifier, str):
                if identifier in seen:
                    errors.append(
                        "%s Work Spec %s has duplicate %s %r" %
                        (label, list_name, id_field, identifier)
                    )
                seen.add(identifier)

    if isinstance(outcomes, list):
        for index, record in enumerate(outcomes, 1):
            if isinstance(record, dict) and not nonempty_string(
                    record.get("required_result")):
                errors.append(
                    "%s Work Spec outcomes[%d].required_result must be a "
                    "non-empty string" % (label, index)
                )

    instruction_by_id = {}
    if isinstance(instructions, list):
        orders = []
        for index, record in enumerate(instructions, 1):
            if not isinstance(record, dict):
                continue
            identifier = record.get("instruction_id")
            order = record.get("order")
            if not isinstance(order, int) or isinstance(order, bool):
                errors.append(
                    "%s Work Spec instructions[%d].order must be an integer" %
                    (label, index)
                )
            else:
                orders.append(order)
            if isinstance(identifier, str):
                instruction_by_id[identifier] = order
            errors.extend(_work_spec_target_scope_errors(
                record.get("target_scope"), scope_manifest,
                "%s Work Spec instructions[%d].target_scope" %
                (label, index)))
            if not nonempty_string(record.get("required_transformation")):
                errors.append(
                    "%s Work Spec instructions[%d].required_transformation "
                    "must be a non-empty string" % (label, index)
                )
            dependencies = record.get("depends_on")
            if (not isinstance(dependencies, list) or
                    not all(isinstance(dep, str) and
                            WORK_SPEC_RECORD_ID_RE.fullmatch(dep)
                            for dep in dependencies)):
                errors.append(
                    "%s Work Spec instructions[%d].depends_on must be an "
                    "explicit list of stable instruction IDs" %
                    (label, index)
                )
            elif len(set(dependencies)) != len(dependencies):
                errors.append(
                    "%s Work Spec instructions[%d].depends_on must not "
                    "contain duplicates" % (label, index)
                )
        expected_orders = list(range(1, len(instructions) + 1))
        if orders != expected_orders:
            errors.append(
                "%s Work Spec instruction order must be unique, contiguous, "
                "and match list order 1..%d" % (label, len(instructions))
            )
        for index, record in enumerate(instructions, 1):
            if not isinstance(record, dict):
                continue
            order = record.get("order")
            dependencies = record.get("depends_on")
            if not isinstance(dependencies, list):
                continue
            for dependency in dependencies:
                if (not isinstance(dependency, str) or
                        not WORK_SPEC_RECORD_ID_RE.fullmatch(dependency)):
                    continue
                dependency_order = instruction_by_id.get(dependency)
                if dependency_order is None:
                    errors.append(
                        "%s Work Spec instructions[%d].depends_on references "
                        "unknown instruction %r" % (label, index, dependency)
                    )
                elif (isinstance(order, int) and not isinstance(order, bool) and
                      (not isinstance(dependency_order, int) or
                       isinstance(dependency_order, bool) or
                       dependency_order >= order)):
                    errors.append(
                        "%s Work Spec instructions[%d].depends_on must "
                        "reference only earlier instructions; %r has order %r" %
                        (label, index, dependency, dependency_order)
                    )

    if isinstance(conditions, list):
        for index, record in enumerate(conditions, 1):
            if not isinstance(record, dict):
                continue
            errors.extend(_work_spec_target_scope_errors(
                record.get("target_scope"), scope_manifest,
                "%s Work Spec acceptance_conditions[%d].target_scope" %
                (label, index)))
            for field in ("observable_predicate", "evidence_requirement"):
                if not nonempty_string(record.get(field)):
                    errors.append(
                        "%s Work Spec acceptance_conditions[%d].%s must be "
                        "a non-empty string" % (label, index, field)
                    )

    if isinstance(constraints, list):
        for index, record in enumerate(constraints, 1):
            if not isinstance(record, dict):
                continue
            errors.extend(_work_spec_target_scope_errors(
                record.get("target_scope"), scope_manifest,
                "%s Work Spec constraints[%d].target_scope" %
                (label, index)))
            if not nonempty_string(record.get("requirement")):
                errors.append(
                    "%s Work Spec constraints[%d].requirement must be a "
                    "non-empty string" % (label, index)
                )

    sentinel_paths = _work_spec_sentinel_paths(metadata)
    if sentinel_paths:
        errors.append(
            "%s Work Spec contains unfilled template sentinel(s) at: %s" %
            (label, ", ".join(sentinel_paths))
        )
    return errors
