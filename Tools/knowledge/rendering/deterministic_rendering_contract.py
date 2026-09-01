"""Strict loader for the Kernel-owned K12/02 deterministic contract."""
from Tools.platform.repository.repository import repository_source_root

import os

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.platform.common.kblib as kblib
import Tools.knowledge.rendering.rendering_verification_contract as rendering_verification_contract
from Tools.platform.common.primitives import require_trimmed_string


CONTRACT_PATH = (
    "kernel/K12 Quality Assurance/deterministic-rendering-contract.yaml")

_TOP_FIELDS = frozenset((
    "schema_version", "contract_id", "semantic_owner",
    "admitted_predicates", "contract_gaps",
))
_PREDICATE_FIELDS = frozenset((
    "predicate_id", "level", "dimension", "acceptance",
))
_GAP_FIELDS = frozenset((
    "gap_id", "level", "dimension", "source_item", "missing_contract",
    "resolution_owner", "runtime_disposition",
))
_LEVELS = frozenset(("level-0", "level-1"))
_RESOLUTION_OWNERS = frozenset((
    "page-contract-or-profile", "profile-or-semantic-review",
    "profile-rendering-contract", "semantic-review",
))
_RUNTIME_DISPOSITIONS = frozenset((
    "conditional-contract-gap", "not-kernel-base-obligation",
    "unresolved-selector-no-runtime-verdict",
))


def load_contract(root=None, snapshots=None):
    snapshot = (snapshots or {}).get(CONTRACT_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        path = os.path.join(
            repository_source_root(__file__, root), *CONTRACT_PATH.split("/"))
        text = kblib.read_text(path)
    return kblib.parse_yaml_subset(text)


def validate_contract(document, *, root=None, snapshots=None):
    if not isinstance(document, dict) or set(document) != _TOP_FIELDS:
        raise ValueError("deterministic rendering contract fields are not closed")
    if document.get("schema_version") != 1:
        raise ValueError("deterministic rendering schema_version must be 1")
    if document.get("contract_id") != \
            "k12-02-deterministic-rendering-contract":
        raise ValueError("deterministic rendering contract_id is invalid")
    if document.get("semantic_owner") != "K12/02":
        raise ValueError("deterministic rendering semantic_owner is invalid")
    dimensions = set(audit_dimension_contract.validate_audit_dimension_base(
        audit_dimension_contract.load_audit_dimension_base(
            root, snapshots=snapshots))[
            "base_receipt_dimensions"])
    normalized = {}
    for collection, fields, id_field in (
            ("admitted_predicates", _PREDICATE_FIELDS, "predicate_id"),
            ("contract_gaps", _GAP_FIELDS, "gap_id")):
        rows = document.get(collection)
        if not isinstance(rows, list) or not rows:
            raise ValueError("deterministic rendering %s must be non-empty" %
                             collection)
        identifiers = []
        for index, row in enumerate(rows):
            label = "%s[%d]" % (collection, index)
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError("%s fields are not closed" % label)
            for field in fields:
                require_trimmed_string(row.get(field), "%s.%s" % (label, field))
            if row["level"] not in _LEVELS:
                raise ValueError("%s level is not registered" % label)
            if row["dimension"] not in dimensions:
                raise ValueError("%s dimension is not registered" % label)
            if collection == "contract_gaps":
                if row["resolution_owner"] not in _RESOLUTION_OWNERS:
                    raise ValueError(
                        "%s resolution_owner is not registered" % label)
                if row["runtime_disposition"] not in \
                        _RUNTIME_DISPOSITIONS:
                    raise ValueError(
                        "%s runtime_disposition is not registered" % label)
                if (row["resolution_owner"] ==
                        "profile-rendering-contract" and
                        row["runtime_disposition"] not in {
                            "conditional-contract-gap",
                            "unresolved-selector-no-runtime-verdict"}):
                    raise ValueError(
                        "%s Profile rendering gap boundary is inconsistent" %
                        label)
                if (row["resolution_owner"] !=
                        "profile-rendering-contract" and
                        row["runtime_disposition"] !=
                        "not-kernel-base-obligation"):
                    raise ValueError(
                        "%s nonbase gap cannot create a runtime verdict" %
                        label)
            identifiers.append(row[id_field])
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("deterministic rendering %s IDs repeat" %
                             collection)
        normalized[collection] = tuple(dict(row) for row in rows)
    overlap = (
        {row["predicate_id"] for row in normalized["admitted_predicates"]} &
        {row["gap_id"] for row in normalized["contract_gaps"]})
    if overlap:
        raise ValueError("predicate and gap identities overlap")
    return normalized


def validate_registry_projection(registry_document, contract=None, root=None,
                                 snapshots=None):
    """Require admitted predicates, and only admitted predicates, to project.

    The changed-scope registry owns execution routing.  This cross-check keeps
    a known contract gap from being relabelled as a runnable pass merely by
    adding a registry row.
    """
    values = validate_contract(
        contract or load_contract(root, snapshots),
        root=root, snapshots=snapshots)
    rows = registry_document.get("base_rules") \
        if isinstance(registry_document, dict) else None
    if not isinstance(rows, list):
        raise ValueError("changed-scope registry has no base_rules list")
    by_id = {
        row.get("rule_id"): row for row in rows
        if isinstance(row, dict) and isinstance(row.get("rule_id"), str)
    }
    admitted = {row["predicate_id"]: row
                for row in values["admitted_predicates"]}
    gaps = {row["gap_id"] for row in values["contract_gaps"]}
    record_shape = rendering_verification_contract.load_contract(
        root, snapshots)
    rendering_verification_contract.validate_contract(record_shape)
    # This identity names the separately validated record shape only.  The
    # changed-scope registry remains the sole owner of whether, where, and how
    # that record becomes an AuditPlan obligation.
    separately_owned = {record_shape["acceptance_predicate"]}
    missing = sorted(set(admitted) - set(by_id))
    if missing:
        raise ValueError(
            "changed-scope registry omits admitted K12/02 predicates: %s" %
            ", ".join(missing))
    projected_gaps = sorted(gaps & set(by_id))
    if projected_gaps:
        raise ValueError(
            "changed-scope registry projects unresolved K12/02 gaps: %s" %
            ", ".join(projected_gaps))
    unexpected_k12_02 = sorted(
        rule_id for rule_id in by_id
        if rule_id.startswith("k12-02-") and
        rule_id not in admitted and rule_id not in separately_owned)
    if unexpected_k12_02:
        raise ValueError(
            "changed-scope registry projects unadmitted K12/02 predicates: %s" %
            ", ".join(unexpected_k12_02))
    for predicate_id, predicate in admitted.items():
        row = by_id[predicate_id]
        if row.get("dimension") != predicate["dimension"]:
            raise ValueError(
                "changed-scope dimension differs for %s" % predicate_id)
        if row.get("evidence_role") != "emits" or \
                row.get("due_stage") != "pre-merge" or \
                row.get("consumer_gate_id") != "batch-review" or \
                row.get("nonblocking") is not False:
            raise ValueError(
                "changed-scope execution boundary differs for %s" %
                predicate_id)
    return True


__all__ = [
    "CONTRACT_PATH", "load_contract", "validate_contract",
    "validate_registry_projection",
]
