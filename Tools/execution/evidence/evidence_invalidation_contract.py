"""Append-only correction events; decision policy remains Kernel-owned.

This contract checks a declared, externally attested decision and exact
evidence bindings. It is not identity authentication or a semantic reviewer.
An event's successful publication is never an audit pass for its subjects.
"""

import os
import re
from collections import defaultdict, deque

from Tools.platform.common import kblib
from Tools.platform.common.primitives import (
    catalog_record, require_trimmed_string, valid_timestamp,
)
from Tools.platform.repository.repository import repository_source_root
from Tools.execution.evidence import receipt_reference_contract, receipt_type_contract


POLICY_PATH = "kernel/K12 Quality Assurance/evidence-invalidation-contract.yaml"
CAPABILITY_ID = "evidence-invalidation-v1"
RECEIPT_TYPE_ID = "evidence-invalidation-event-v1"
TOOL = "record_evidence_invalidation"
TOOL_VERSION = "1.0.0"
CHECK = "evidence_invalidation"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DECISION_FIELDS = frozenset((
    "mode", "actor_role", "reviewer_context_id", "authority_reference",
    "statement",
))
_SUBJECT_BINDING_FIELDS = (
    "target", "task_id", "batch_id", "plan_id", "audit_plan_sha256",
    "obligation_id", "gate_id", "receipt_type_id",
)
_SUBJECT_FIELDS = frozenset(("receipt_id", "receipt_sha256", "binding"))
_EVENT_FIELDS = frozenset((
    "receipt_id", "receipt_type_id", "tool", "tool_version", "check",
    "target", "result", "details", "checked_at", "invalidated_by",
    "event_id", "record_kind", "policy_sha256", "reason", "decision",
    "subjects", "upstream_revision_id", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint", "decision_assurance",
))
_AUTHORITY_FIELDS = (
    "upstream_revision_id", "active_standards_sha256",
    "selected_profile_manifest", "profile_snapshot_sha256",
    "profile_contract_fingerprint",
)


def load_policy(root=None):
    root = os.fspath(root or repository_source_root(__file__))
    policy = kblib.load_yaml_file(os.path.join(root, POLICY_PATH))
    if (not isinstance(policy, dict) or policy.get("schema_version") != 1 or
            policy.get("contract_id") != CAPABILITY_ID or
            policy.get("semantic_owner") != "K12/07"):
        raise ValueError("unrecognized evidence invalidation policy")
    for field in ("decision_modes", "decision_reasons"):
        values = policy.get(field)
        if (not isinstance(values, list) or not values or
                any(not isinstance(value, str) or not value for value in values) or
                len(set(values)) != len(values)):
            raise ValueError("invalid evidence invalidation policy %s" % field)
    if set(policy) != {
            "schema_version", "contract_id", "semantic_owner", "decision_modes",
            "decision_reasons", "authority_boundary", "effects"}:
        raise ValueError("invalidation policy fields are not closed")
    # This adapter supports only the approved decision and result boundary.
    # Unknown policy is HOLD, not permission to infer a new correction power.
    supported = {
        "decision_source": "operator-or-host-attested",
        "actor_labels_are_authentication": False,
        "integrator_has_judgment_authority": False,
        "own_declaration": "exact-original-reviewer-binding",
        "semantic_authority": "existing-target-authority",
        "explicit_user": "exact-target-bound-user-decision",
    }
    if policy["authority_boundary"] != supported:
        raise ValueError("invalidation authority policy has no installed adapter")
    if policy["effects"] != {
            "original_evidence": "immutable",
            "current_usability": "invalidated",
            "propagation": "acceptance-dependencies-only",
            "replacement_evidence": "original-producer-and-obligation",
            "state_rollback": "separate-existing-transition",
            "restore_old_authority": "forbidden",
            "l_review_restart": "forbidden",
            "l_unprovided_continuation": "escalate-under-k12-12",
            "s_sample": "preserve-frozen-selection"}:
        raise ValueError("invalidation effects have no installed adapter")
    return policy


def digest(value):
    """Exact canonical record identity used by typed evidence bindings."""
    return kblib.sha256_bytes(kblib.canonical_json_bytes(value))


def subject_binding(record):
    return {
        "receipt_id": record["receipt_id"], "receipt_sha256": digest(record),
        "binding": {field: record.get(field) for field in _SUBJECT_BINDING_FIELDS},
    }


def validate_decision(decision, subjects, policy):
    """Check permitted scope of an operator/Host-attested decision.

    Matching labels are necessary bindings, never proof of who operated the
    interface. The operator must actually obtain the named decision; no tool
    invocation or freely chosen integrator label supplies it automatically.
    """
    if not isinstance(decision, dict) or set(decision) != _DECISION_FIELDS:
        raise ValueError("invalidation decision fields are not closed")
    mode = decision["mode"]
    if mode not in policy["decision_modes"]:
        raise ValueError("invalidation decision mode is not authorized")
    for field in ("actor_role", "authority_reference", "statement"):
        require_trimmed_string(decision[field], "decision.%s" % field)
    context = decision["reviewer_context_id"]
    if context is not None:
        require_trimmed_string(context, "decision.reviewer_context_id")
    if mode == "own-declaration":
        if not context:
            raise ValueError("own-declaration requires the original reviewer binding")
        for subject in subjects:
            if (subject.get("reviewer_context_id") != context or
                    subject.get("reviewer_role") != decision["actor_role"]):
                raise ValueError("own-declaration cannot withdraw another reviewer")
    elif mode == "semantic-authority":
        for subject in subjects:
            role = subject.get("pass_authority_role_id")
            if not role or role != decision["actor_role"]:
                raise ValueError("target has no matching existing semantic authority")
    elif mode == "explicit-user":
        if decision["actor_role"] != "user" or context is not None:
            raise ValueError("explicit-user decision must declare user, not an executor")
    else:
        raise ValueError("decision policy has no installed interpretation")


def validate_event(record, *, root=None):
    policy = load_policy(root)
    if not isinstance(record, dict) or set(record) != _EVENT_FIELDS:
        raise ValueError("evidence invalidation event fields are not closed")
    expected = {
        "receipt_type_id": RECEIPT_TYPE_ID, "tool": TOOL,
        "tool_version": TOOL_VERSION, "check": CHECK,
        "record_kind": "evidence-invalidation-event", "result": "pass",
        "invalidated_by": None, "policy_sha256": digest(policy),
        "decision_assurance": policy["authority_boundary"]["decision_source"],
    }
    if any(record.get(field) != value for field, value in expected.items()):
        raise ValueError("invalidation event identity/policy binding is invalid")
    if not isinstance(record["event_id"], str) or not _ID.fullmatch(record["event_id"]):
        raise ValueError("invalidation event_id is invalid")
    if (record["receipt_id"] != "evidence-invalidation-" + record["event_id"] or
            record["target"] != record["event_id"]):
        raise ValueError("invalidation event identity does not match its operation")
    if record["reason"] not in policy["decision_reasons"]:
        raise ValueError("invalidation reason is not registered")
    for field in ("checked_at", "details") + _AUTHORITY_FIELDS:
        require_trimmed_string(record[field], "event.%s" % field)
    if not valid_timestamp(record["checked_at"]):
        raise ValueError("event checked_at must be a timezone-aware timestamp")
    if re.fullmatch(r"[0-9a-f]{40}", record["upstream_revision_id"]) is None:
        raise ValueError("event upstream_revision_id must be a complete commit SHA")
    for field in _AUTHORITY_FIELDS:
        if field.endswith("sha256") or field.endswith("fingerprint"):
            if not _SHA.fullmatch(record[field]):
                raise ValueError("event.%s must bind a sha256" % field)
    subjects = record["subjects"]
    if not isinstance(subjects, list) or not subjects:
        raise ValueError("invalidation requires exact subjects")
    ids = []
    for subject in subjects:
        if not isinstance(subject, dict) or set(subject) != _SUBJECT_FIELDS:
            raise ValueError("invalidation subject is not closed")
        ids.append(require_trimmed_string(subject["receipt_id"], "subject identity"))
        if (not isinstance(subject["receipt_sha256"], str) or
                not _SHA.fullmatch(subject["receipt_sha256"])):
            raise ValueError("invalidation subject must bind exact record bytes")
        if (not isinstance(subject["binding"], dict) or
                set(subject["binding"]) != set(_SUBJECT_BINDING_FIELDS)):
            raise ValueError("invalidation subject binding is not closed")
        for field, value in subject["binding"].items():
            if value is not None:
                require_trimmed_string(value, "subject.binding.%s" % field)
        for field in ("target", "receipt_type_id"):
            require_trimmed_string(
                subject["binding"][field], "subject.binding.%s" % field)
        if subject["binding"].get("receipt_type_id") == RECEIPT_TYPE_ID:
            raise ValueError("an invalidation event cannot be reversed by invalidation")
    if ids != sorted(set(ids)) or record["receipt_id"] in ids:
        raise ValueError("invalidation subjects must be sorted, unique, and nonrecursive")
    # Scope is revalidated against the exact historical bodies below. This
    # first check validates the envelope without pretending to have those bodies.
    validate_decision(record["decision"], (), policy)
    if record["details"] != record["decision"]["statement"]:
        raise ValueError("event statement differs from its decision")
    return record


def validate_subjects(record, catalog, *, root=None, registry=None):
    """Read exact current-format history, never require subjects to be current."""
    validate_event(record, root=root)
    registry = registry or receipt_type_contract.load_receipt_type_registry(root)
    bodies = []
    for subject in record["subjects"]:
        body = resolve_body(catalog, subject["receipt_id"])
        if not isinstance(body, dict) or subject_binding(body) != subject:
            raise ValueError("invalidation subject body is absent or changed: %s" %
                             subject["receipt_id"])
        if body.get("receipt_type_id") == RECEIPT_TYPE_ID:
            raise ValueError("invalidation cannot restore a prior authority")
        registration = registry.get(body.get("receipt_type_id"))
        if registration is None or not registration.correction_subject:
            raise ValueError("target type is not correction evidence; "
                             "executed state requires its own transition")
        for field in _AUTHORITY_FIELDS:
            if field in body and body[field] != record[field]:
                raise ValueError("invalidation subject belongs to another %s" % field)
        bodies.append(body)
    validate_decision(record["decision"], bodies, load_policy(root))
    return tuple(bodies)


def resolve_body(catalog, receipt_id):
    """Resolve an exact current-format body, including a proved cold body."""
    resolver = getattr(catalog, "resolve", catalog.get)
    return catalog_record(resolver(receipt_id))


def invalidation_view(catalog, *, root=None, registry=None):
    """Evaluate append-only decisions and true acceptance edges once.

    Custody, transition history and correction-subject references never
    propagate. A result is only a current-use projection; no historical body
    or ledger is changed. No persistent valid-evidence list is produced.
    """
    ids = set(catalog) | set(getattr(catalog, "cold", {}))
    event_ids = []
    for receipt_id in sorted(ids):
        row = catalog_record(catalog.get(receipt_id))
        if row is None:
            row = getattr(catalog, "cold", {}).get(receipt_id)
        if isinstance(row, dict) and row.get("receipt_type_id") == RECEIPT_TYPE_ID:
            event_ids.append(receipt_id)
    if not event_ids:
        return {"events": (), "direct": {}, "affected": {}}
    registry = registry or receipt_type_contract.load_receipt_type_registry(root)
    direct = defaultdict(set)
    for event_id in event_ids:
        event = resolve_body(catalog, event_id)
        validate_subjects(event, catalog, root=root, registry=registry)
        for subject in event["subjects"]:
            direct[subject["receipt_id"]].add(event_id)

    consumers = defaultdict(set)
    incoming = {receipt_id: 0 for receipt_id in ids}
    for receipt_id in sorted(ids):
        body = resolve_body(catalog, receipt_id)
        if not isinstance(body, dict):
            raise ValueError("invalidation closure cannot resolve %s" % receipt_id)
        kind = receipt_type_contract.reference_source_kind(
            body, root=root, registry=registry)
        if kind is None:
            continue
        for reference in receipt_reference_contract.iter_receipt_references(body, kind):
            if not reference.spec.acceptance_dependency:
                continue
            if reference.receipt_id not in ids:
                raise ValueError("acceptance dependency is absent: %s -> %s" %
                                 (receipt_id, reference.receipt_id))
            if receipt_id not in consumers[reference.receipt_id]:
                consumers[reference.receipt_id].add(receipt_id)
                incoming[receipt_id] += 1

    ready = deque(sorted(key for key, count in incoming.items() if count == 0))
    visited = 0
    while ready:
        source = ready.popleft()
        visited += 1
        for consumer in sorted(consumers[source]):
            incoming[consumer] -= 1
            if incoming[consumer] == 0:
                ready.append(consumer)
    if visited != len(ids):
        raise ValueError("acceptance dependencies contain a circular proof")

    affected = {key: set(values) for key, values in direct.items()}
    pending = deque(sorted(direct))
    while pending:
        source = pending.popleft()
        for consumer in sorted(consumers[source]):
            known = affected.setdefault(consumer, set())
            difference = affected[source] - known
            if difference:
                known.update(difference)
                pending.append(consumer)
    return {
        "events": tuple(event_ids),
        "direct": {key: tuple(sorted(values)) for key, values in sorted(direct.items())},
        "affected": {key: tuple(sorted(values)) for key, values in sorted(affected.items())},
    }


def build_event(*, event_id, reason, decision, subjects, authority,
                checked_at, root=None):
    """Build an exact event from already-resolved immutable target bodies."""
    policy = load_policy(root)
    validate_decision(decision, subjects, policy)
    event = {
        "receipt_id": "evidence-invalidation-" + event_id,
        "receipt_type_id": RECEIPT_TYPE_ID, "tool": TOOL,
        "tool_version": TOOL_VERSION, "check": CHECK,
        "target": event_id, "result": "pass", "details": decision["statement"],
        "checked_at": checked_at, "invalidated_by": None,
        "event_id": event_id, "record_kind": "evidence-invalidation-event",
        "policy_sha256": digest(policy), "reason": reason,
        "decision": dict(decision),
        "subjects": sorted((subject_binding(body) for body in subjects),
                           key=lambda row: row["receipt_id"]),
        "decision_assurance": policy["authority_boundary"]["decision_source"],
        **{field: authority[field] for field in _AUTHORITY_FIELDS},
    }
    return validate_event(event, root=root)


def current_reference_deficits(record, source_kind, view, *, scope):
    """Report unusable current references, without changing recorded state."""
    deficits = []
    for reference in receipt_reference_contract.iter_receipt_references(
            record, source_kind, recursive=False):
        events = view["affected"].get(reference.receipt_id)
        if reference.spec.acceptance_dependency and events:
            deficits.append({
                "code": "evidence-invalidated", "scope": scope,
                "receipt_id": reference.receipt_id,
                "edge_id": reference.spec.edge_id,
                "event_ids": list(events),
            })
    return deficits


def current_receipt_errors(record, *, root=None):
    try:
        validate_event(record, root=root)
    except (OSError, TypeError, KeyError, UnicodeError, ValueError) as exc:
        return [str(exc)]
    return []


__all__ = (
    "CAPABILITY_ID", "RECEIPT_TYPE_ID", "TOOL", "TOOL_VERSION",
    "current_receipt_errors", "load_policy", "validate_subjects", "build_event",
    "resolve_body", "invalidation_view", "current_reference_deficits",
)
