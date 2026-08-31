"""Pure Kernel-registry projection for K12 AuditPlan obligation definitions.

This module composes the four Kernel-owned base sources without importing a
producer or consumer.  Registry rows remain authoritative for identities,
dimensions, stages, producer routes, consumers, and acceptance contracts.
Profile-owned rows enter only through :func:`compose_profile_extensions`.
"""
from Tools.platform.repository.repository import repository_source_root

from copy import deepcopy
from functools import lru_cache
import os

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.batch_close_contract as batch_close_contract
import Tools.execution.audit.batch_review_obligation_contract as batch_review_obligation_contract
import Tools.knowledge.rendering.deterministic_rendering_contract as deterministic_rendering_contract
import Tools.governance.profile.profile_batch_judgment_contract as profile_batch_judgment_contract
import Tools.platform.common.kblib as kblib
import Tools.knowledge.rendering.rendering_verification_contract as rendering_verification_contract
import Tools.execution.audit.substantive_review_contract as substantive_review_contract
from Tools.platform.common.primitives import require_trimmed_string


CHANGED_SCOPE_REGISTRY_PATH = (
    "kernel/K12 Quality Assurance/changed-scope-check-registry.yaml")
PROFILE_REGISTERED_SCAN_EXTENSION = "k12-05-registered-scan"
BATCH_CLOSE_REGISTRY_PATH = batch_close_contract.BATCH_CLOSE_CLOSED_LIST_PATH
BATCH_REVIEW_REGISTRY_PATH = (
    batch_review_obligation_contract.BATCH_REVIEW_OBLIGATION_REGISTRY_PATH)
SUBSTANTIVE_REGISTRY_PATH = (
    substantive_review_contract.SUBSTANTIVE_REVIEW_CONTRACT_PATH)

_CHANGED_TOP_FIELDS = {
    "schema_version", "registry_id", "semantic_owner", "base_rules",
    "extension_points",
}
_CHANGED_COMMON_FIELDS = {
    "rule_id", "applicability", "producer_check", "evidence_role",
    "evidence_kind", "dimension", "dimension_binding",
    "consumer_gate_id", "due_stage", "nonblocking",
}
_CHANGED_EXTENSION_COMMON_FIELDS = {
    "extension_point_id", "applicability", "producer_check_binding",
    "evidence_role", "evidence_kind", "dimension", "dimension_binding",
    "consumer_gate_id", "due_stage", "nonblocking",
}
_PRODUCER_FIELDS = {"producer_capability", "producer_gate_id"}
_SPEC_FIELDS = {
    "spec_id", "source_registry", "source_entry_id", "owner_kind",
    "owner_rule_id", "kernel_extension_point", "target_source", "tier",
    "applicability", "partition", "trigger_partition_mappings",
    "due_stage", "evidence_role", "evidence_kind", "dimension",
    "dimension_binding", "acceptance_predicate", "producer_capability",
    "producer_gate_id", "producer_check", "consumer_gate_id",
    "fingerprint_binding", "nonblocking",
}
_DEFINITION_FIELDS = {
    "owner_kind", "owner_rule_id", "kernel_extension_point", "partition",
    "due_stage", "target", "applicability", "evidence_role",
    "evidence_kind", "dimension", "acceptance_predicate",
    "producer_capability", "producer_gate_id", "producer_check",
    "consumer_gate_id", "fingerprint_binding",
}


def _root(root):
    if root is None:
        return repository_source_root(__file__)
    return os.path.realpath(os.path.abspath(os.fspath(root)))


class _TextSnapshot:
    """Minimal immutable snapshot adapter for exact-source cache entries."""

    __slots__ = ("_text",)

    def __init__(self, text):
        self._text = text

    def read_text(self):
        return self._text


def _source_text(path, root=None, snapshots=None):
    snapshot = (snapshots or {}).get(path)
    if snapshot is not None:
        return snapshot.read_text()
    return kblib.read_text(os.path.join(_root(root), *path.split("/")))


def _read_document(path, root=None, snapshots=None):
    text = _source_text(path, root, snapshots)
    return kblib.parse_yaml_subset(text), text


@lru_cache(maxsize=32)
def _plan_values_for_exact_sources(plan_text, dimension_text):
    snapshots = {
        audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH:
            _TextSnapshot(dimension_text),
    }
    document = kblib.parse_yaml_subset(plan_text)
    return audit_plan_contract.validate_contract(
        document, snapshots=snapshots)


def _plan_values(root=None, snapshots=None):
    return _plan_values_for_exact_sources(
        _source_text(
            audit_plan_contract.AUDIT_PLAN_CONTRACT_PATH, root, snapshots),
        _source_text(
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH,
            root, snapshots),
    )


@lru_cache(maxsize=32)
def _dimension_values_for_exact_source(text):
    values = audit_dimension_contract.validate_audit_dimension_base(
        kblib.parse_yaml_subset(text))
    return frozenset(values["base_receipt_dimensions"])


def _dimension_values(root=None, snapshots=None):
    return _dimension_values_for_exact_source(_source_text(
        audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH, root, snapshots))


def _producer_route(row, label):
    route_fields = set(row) & _PRODUCER_FIELDS
    if len(route_fields) != 1:
        raise ValueError(
            "%s must bind exactly one producer capability or Gate" % label)
    route_field = next(iter(route_fields))
    route = require_trimmed_string(row.get(route_field), "%s.%s" % (label, route_field))
    return (
        route if route_field == "producer_capability" else None,
        route if route_field == "producer_gate_id" else None,
    )


def _validate_changed_rule(row, label, plan_values, dimensions):
    if not isinstance(row, dict):
        raise ValueError("%s must be a mapping" % label)
    route_fields = set(row) & _PRODUCER_FIELDS
    if set(row) != _CHANGED_COMMON_FIELDS | route_fields or \
            len(route_fields) != 1:
        raise ValueError("%s fields are not closed" % label)
    for field in (
            "rule_id", "applicability", "producer_check", "evidence_role",
            "evidence_kind", "dimension_binding", "consumer_gate_id",
            "due_stage"):
        require_trimmed_string(row.get(field), "%s.%s" % (label, field))
    capability, gate_id = _producer_route(row, label)
    if row["evidence_role"] not in plan_values["evidence_roles"]:
        raise ValueError("%s evidence_role is not registered" % label)
    if row["evidence_kind"] not in plan_values["evidence_kinds"]:
        raise ValueError("%s evidence_kind is not registered" % label)
    if row["due_stage"] not in plan_values["due_stages"]:
        raise ValueError("%s due_stage is not registered" % label)
    if not isinstance(row.get("nonblocking"), bool):
        raise ValueError("%s.nonblocking must be boolean" % label)

    dimension = row.get("dimension")
    binding = row["dimension_binding"]
    if binding == "fixed":
        if dimension not in dimensions:
            raise ValueError("%s fixed dimension is not registered" % label)
    elif binding == "dimensionless-gate":
        if (dimension is not None or gate_id is None or
                row["evidence_kind"] != "gate-receipt"):
            raise ValueError(
                "%s dimensionless Gate binding is inconsistent" % label)
    elif binding == "profile-registration":
        if dimension is not None:
            raise ValueError(
                "%s Profile-bound dimension must remain unresolved" % label)
    else:
        raise ValueError("%s dimension_binding is not registered" % label)
    if (row["evidence_kind"] == "audit-receipt" and
            (row["evidence_role"] != "emits" or
             (dimension is None and binding != "profile-registration"))):
        raise ValueError(
            "%s AuditReceipt route must emit a dimension" % label)
    normalized = dict(row)
    normalized["producer_capability"] = capability
    normalized["producer_gate_id"] = gate_id
    return normalized


def _validate_changed_extension(row, label, plan_values):
    if not isinstance(row, dict):
        raise ValueError("%s must be a mapping" % label)
    route_fields = set(row) & _PRODUCER_FIELDS
    if set(row) != _CHANGED_EXTENSION_COMMON_FIELDS | route_fields or \
            len(route_fields) != 1:
        raise ValueError("%s fields are not closed" % label)
    for field in (
            "extension_point_id", "applicability",
            "producer_check_binding", "evidence_role", "evidence_kind",
            "dimension_binding", "consumer_gate_id", "due_stage"):
        require_trimmed_string(row.get(field), "%s.%s" % (label, field))
    capability, gate_id = _producer_route(row, label)
    if row["extension_point_id"] not in plan_values["extension_points"]:
        raise ValueError("%s extension point is not registered" % label)
    if row["evidence_role"] not in plan_values["evidence_roles"]:
        raise ValueError("%s evidence_role is not registered" % label)
    if row["evidence_kind"] not in plan_values["evidence_kinds"]:
        raise ValueError("%s evidence_kind is not registered" % label)
    if row["due_stage"] not in plan_values["due_stages"]:
        raise ValueError("%s due_stage is not registered" % label)
    if (row["dimension"] is not None or
            row["dimension_binding"] != "profile-registration"):
        raise ValueError("%s dimension must be Profile-bound" % label)
    if not isinstance(row.get("nonblocking"), bool):
        raise ValueError("%s.nonblocking must be boolean" % label)
    normalized = dict(row)
    normalized["producer_capability"] = capability
    normalized["producer_gate_id"] = gate_id
    return normalized


def validate_changed_scope_registry(document, *, plan_values=None,
                                    dimensions=None):
    """Strictly validate the K12/05 base and extension-point registry."""
    if not isinstance(document, dict) or set(document) != _CHANGED_TOP_FIELDS:
        raise ValueError("changed-scope registry fields are not closed")
    if document.get("schema_version") != 1:
        raise ValueError("changed-scope registry schema_version must be 1")
    if document.get("registry_id") != "changed-scope-check-registry":
        raise ValueError("changed-scope registry_id is invalid")
    if document.get("semantic_owner") != "K12/05":
        raise ValueError("changed-scope semantic_owner is invalid")
    plan_values = plan_values or _plan_values()
    dimensions = frozenset(dimensions or _dimension_values())
    normalized = {}
    for collection in ("base_rules", "extension_points"):
        rows = document.get(collection)
        if not isinstance(rows, list) or not rows:
            raise ValueError("changed-scope %s must be non-empty" % collection)
        projected = []
        for index, row in enumerate(rows):
            if collection == "base_rules":
                item = _validate_changed_rule(
                    row, "%s[%d]" % (collection, index), plan_values,
                    dimensions)
            else:
                item = _validate_changed_extension(
                    row, "%s[%d]" % (collection, index), plan_values)
            projected.append(item)
        normalized[collection] = tuple(projected)
    rule_ids = [row["rule_id"] for row in normalized["base_rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("changed-scope rule IDs must be unique")
    extension_ids = [row["extension_point_id"]
                     for row in normalized["extension_points"]]
    if len(extension_ids) != len(set(extension_ids)):
        raise ValueError("changed-scope extension points must be unique")
    if any(value not in plan_values["extension_points"]
           for value in extension_ids):
        raise ValueError(
            "changed-scope extension point is not registered by AuditPlan")
    return normalized


def load_changed_scope_registry(root=None, snapshots=None):
    """Load the Kernel-owned K12/05 changed-scope registry."""
    document, _text = _read_document(
        CHANGED_SCOPE_REGISTRY_PATH, root, snapshots)
    validate_changed_scope_registry(document)
    return document


def _mappings(value, label, plan_values):
    if value is None:
        value = ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("%s must be a trigger mapping sequence" % label)
    result = []
    triggers = set()
    for index, row in enumerate(value):
        row_label = "%s[%d]" % (label, index)
        if (not isinstance(row, dict) or
                set(row) != {"trigger", "partition"}):
            raise ValueError("%s fields are not closed" % row_label)
        trigger = require_trimmed_string(row.get("trigger"), row_label + ".trigger")
        partition = require_trimmed_string(
            row.get("partition"), row_label + ".partition")
        if trigger in triggers:
            raise ValueError("%s repeats trigger %s" % (label, trigger))
        if partition not in plan_values["partitions"]:
            raise ValueError("%s partition is not registered" % row_label)
        triggers.add(trigger)
        result.append({"trigger": trigger, "partition": partition})
    return tuple(result)


def _spec(_registered_dimensions=None, _plan_contract_values=None, **values):
    if set(values) != _SPEC_FIELDS:
        raise ValueError("base obligation spec fields are not closed")
    plan_values = _plan_contract_values or _plan_values()
    dimensions = frozenset(_registered_dimensions or _dimension_values())
    for field in (
            "spec_id", "source_registry", "source_entry_id", "owner_kind",
            "owner_rule_id", "target_source", "applicability", "due_stage",
            "evidence_role", "evidence_kind", "acceptance_predicate",
            "producer_check", "consumer_gate_id", "fingerprint_binding"):
        require_trimmed_string(values.get(field), "obligation spec.%s" % field)
    for field in ("kernel_extension_point", "tier", "partition",
                  "dimension", "dimension_binding", "producer_capability",
                  "producer_gate_id"):
        value = values.get(field)
        if value is not None:
            require_trimmed_string(value, "obligation spec.%s" % field)
    if values["owner_kind"] not in plan_values["owner_kinds"]:
        raise ValueError("obligation spec owner_kind is not registered")
    if values["owner_kind"] == "kernel":
        if values["kernel_extension_point"] is not None:
            raise ValueError("Kernel base spec cannot claim an extension point")
    elif values["kernel_extension_point"] not in \
            plan_values["extension_points"]:
        raise ValueError(
            "Profile spec requires a registered Kernel extension point")
    if values["due_stage"] not in plan_values["due_stages"]:
        raise ValueError("obligation spec due_stage is not registered")
    if values["evidence_role"] not in plan_values["evidence_roles"]:
        raise ValueError("obligation spec evidence_role is not registered")
    if values["evidence_kind"] not in plan_values["evidence_kinds"]:
        raise ValueError("obligation spec evidence_kind is not registered")
    if values["fingerprint_binding"] not in \
            plan_values["fingerprint_bindings"]:
        raise ValueError("obligation spec fingerprint binding is not registered")
    if (values["producer_capability"] is None) == \
            (values["producer_gate_id"] is None):
        raise ValueError(
            "obligation spec must bind exactly one producer capability or Gate")
    mappings = _mappings(
        values["trigger_partition_mappings"],
        "obligation spec.trigger_partition_mappings", plan_values)
    if (values["partition"] is None) == (not mappings):
        raise ValueError(
            "obligation spec must use either one fixed partition or trigger "
            "mappings")
    if (values["partition"] is not None and
            values["partition"] not in plan_values["partitions"]):
        raise ValueError("obligation spec partition is not registered")
    values["trigger_partition_mappings"] = mappings
    if values["dimension_binding"] == "fixed":
        if values["dimension"] not in dimensions:
            raise ValueError("obligation spec fixed dimension is not registered")
    elif values["dimension_binding"] == "dimensionless-gate":
        if (values["dimension"] is not None or
                values["producer_gate_id"] is None or
                values["evidence_kind"] != "gate-receipt"):
            raise ValueError("obligation spec dimensionless Gate is invalid")
    elif values["dimension_binding"] == "profile-registration":
        if values["dimension"] is not None:
            raise ValueError(
                "obligation spec Profile dimension must remain unresolved")
    elif values["dimension_binding"] is not None:
        raise ValueError("obligation spec dimension binding is unknown")
    elif values["dimension"] is not None and values["dimension"] not in dimensions:
        raise ValueError("obligation spec dimension is not registered")
    if (values["evidence_kind"] == "audit-receipt" and
            (values["evidence_role"] != "emits" or
             (values["dimension"] is None and
              values["dimension_binding"] != "profile-registration"))):
        raise ValueError("AuditReceipt spec must emit one dimension")
    if values["nonblocking"] is not None and not isinstance(
            values["nonblocking"], bool):
        raise ValueError("obligation spec nonblocking must be boolean or null")
    return values


def profile_registered_scan_spec(contract, scan, root=None, registry=None):
    """Project one admitted Profile scan through the K12/05 extension.

    This is the sole machine projection shared by AuditPlan production and
    candidate-set evidence validation.  The Profile supplies the concrete
    scan, candidate boundary, Judgment Item and dimension; the Kernel
    extension point supplies the producer/evidence/consumer lifecycle.
    """
    registry = registry or load_changed_scope_registry(root)
    values = validate_changed_scope_registry(registry)
    points = [row for row in values["extension_points"]
              if row["extension_point_id"] ==
              PROFILE_REGISTERED_SCAN_EXTENSION]
    if len(points) != 1:
        raise ValueError(
            "K12/05 registered-scan extension point is not unique")
    point = points[0]
    scans = [row for row in getattr(contract, "registered_scans", ())
             if row.scan_id == getattr(scan, "scan_id", None)]
    if len(scans) != 1 or scans[0] is not scan:
        raise ValueError(
            "Profile registered scan is not the unique admitted instance")
    if scan.required_for_k12_item_6:
        raise ValueError(
            "K12/09 item 6 scan is not a K12/05 Profile extension")
    judgments = [row for row in getattr(contract, "judgment_items", ())
                 if row.judgment_item_id == scan.judgment_item_id]
    if len(judgments) != 1:
        raise ValueError(
            "Profile registered scan has no unique Judgment Item")
    judgment = judgments[0]
    dimensions = set(_dimension_values())
    dimensions.update(
        row.dimension_id for row in getattr(
            contract, "extension_dimensions", ()))
    dimensions.update(
        row.dimension_id for row in getattr(contract, "judgment_items", ()))
    return _spec(
        _registered_dimensions=dimensions,
        spec_id="profile-scan:%s" % scan.scan_id,
        source_registry=(getattr(contract, "scan_registry_path", None) or
                         contract.manifest_repo_path),
        source_entry_id=scan.scan_id,
        owner_kind="profile-extension", owner_rule_id=scan.scan_id,
        kernel_extension_point=PROFILE_REGISTERED_SCAN_EXTENSION,
        target_source="changed-scope", tier=None,
        applicability=scan.candidate_predicate,
        partition="changed-scope-deterministic",
        trigger_partition_mappings=(), due_stage=point["due_stage"],
        evidence_role=point["evidence_role"],
        evidence_kind=point["evidence_kind"],
        dimension=judgment.dimension_id, dimension_binding="fixed",
        acceptance_predicate=judgment.judgment_item_id,
        producer_capability=point["producer_capability"],
        producer_gate_id=point["producer_gate_id"],
        producer_check=scan.scan_id,
        consumer_gate_id=point["consumer_gate_id"],
        fingerprint_binding="evidence-time",
        nonblocking=point["nonblocking"],
    )


def registered_dimensions(base_specs, contract):
    """Return the one dimension namespace shared by projection and reload."""
    values = {row["dimension"] for row in base_specs
              if row["dimension"] is not None}
    values.update(row.dimension_id for row in getattr(
        contract, "extension_dimensions", ()))
    values.update(row.dimension_id for row in getattr(
        contract, "judgment_items", ()))
    return frozenset(values)


def profile_extension_specs(contract, root=None):
    """Project all and only typed Profile registrations into plan specs.

    This neutral projection is used both when a plan is created and whenever
    its frozen definitions are consumed.  Keeping it here prevents producers
    and consumers from maintaining separate interpretations of the selected
    Profile's legal extension closure.
    """
    specs = []
    for scan in getattr(contract, "registered_scans", ()):
        if scan.required_for_k12_item_6:
            continue
        specs.append(profile_registered_scan_spec(
            contract, scan, root=root))

    for requirement in getattr(contract, "batch_review_requirements", ()):
        _required, _judgment_item, projection = \
            profile_batch_judgment_contract.expected_projection(
                contract, requirement.judgment_item_id)
        specs.append({
            "spec_id": "profile-batch-review:%s" %
                requirement.judgment_item_id,
            "source_registry": (
                getattr(contract, "routing_registry_path", None) or
                contract.manifest_repo_path),
            "source_entry_id": requirement.judgment_item_id,
            "owner_kind": projection["owner_kind"],
            "owner_rule_id": projection["owner_rule_id"],
            "kernel_extension_point": projection[
                "kernel_extension_point"],
            "target_source": requirement.target_selector,
            "tier": None,
            "applicability": projection["applicability"],
            "partition": projection["partition"],
            "trigger_partition_mappings": (),
            "due_stage": projection["due_stage"],
            "evidence_role": projection["evidence_role"],
            "evidence_kind": projection["evidence_kind"],
            "dimension": projection["dimension"],
            "dimension_binding": "fixed",
            "acceptance_predicate": projection["acceptance_predicate"],
            "producer_capability": projection["producer_capability"],
            "producer_gate_id": projection["producer_gate_id"],
            "producer_check": projection["producer_check"],
            "consumer_gate_id": projection["consumer_gate_id"],
            "fingerprint_binding": projection["fingerprint_binding"],
            "nonblocking": False,
        })
    return tuple(specs)


def composed_obligation_specs(contract, root=None, snapshots=None):
    """Return the unique Kernel plus selected-Profile definition closure."""
    base = base_obligation_specs(root, snapshots)
    dimensions = registered_dimensions(base, contract)
    extensions = profile_extension_specs(contract, root=root)
    return compose_profile_extensions(
        base, extensions, registered_dimensions=dimensions,
        root=root, snapshots=snapshots), dimensions


def obligation_id_for_definition(definition):
    """Derive the stable plan-row identity from exact definition fields."""
    if not isinstance(definition, dict) or set(definition) != \
            _DEFINITION_FIELDS:
        raise ValueError("obligation definition fields are not closed")
    identity = kblib.sha256_bytes(kblib.canonical_json_bytes(definition))
    return "audit-obligation-%s" % identity.split(":", 1)[1][:24]


def required_obligation(definition):
    """Wrap one resolved definition in its initial required-state fields."""
    row = deepcopy(definition)
    row.update({
        "obligation_id": obligation_id_for_definition(definition),
        "review_due": None,
        "status": "required",
        "evidence_ref": None,
        "reused_receipt_id": None,
        "reuse_reason": None,
    })
    return row


def validate_plan_definition_authority(plan, contract, root=None,
                                       snapshots=None):
    """Validate every frozen row against its sole registered owner.

    This intentionally checks definition authority, not target completeness.
    Completeness is proven at publication from opening-time inputs.  Reloading
    a plan must not reproject target membership from pages or Coverage that
    legitimately evolve after the batch opens.
    """
    if not isinstance(plan, dict) or not isinstance(
            plan.get("obligations"), list):
        raise ValueError("AuditPlan obligations are not available")
    specs, dimensions = composed_obligation_specs(
        contract, root=root, snapshots=snapshots)
    by_rule = {row["owner_rule_id"]: row for row in specs}
    if len(by_rule) != len(specs):
        raise ValueError("registered AuditPlan definitions repeat an owner rule")
    seen = set()
    for obligation in plan["obligations"]:
        rule_id = obligation["owner_rule_id"]
        spec = by_rule.get(rule_id)
        if spec is None:
            raise ValueError(
                "AuditPlan obligation %s has no registered owner rule %s" %
                (obligation["obligation_id"], rule_id))
        pair = (rule_id, obligation["target"])
        if pair in seen:
            raise ValueError("AuditPlan repeats owner/target %s/%s" % pair)
        seen.add(pair)
        mappings = spec["trigger_partition_mappings"]
        triggers = (None,)
        if mappings:
            if obligation["status"] == "reused":
                triggers = tuple(row["trigger"] for row in mappings)
            else:
                triggers = tuple(
                    row["trigger"] for row in mappings
                    if row["partition"] == obligation["partition"])
                if not triggers:
                    raise ValueError(
                        "AuditPlan obligation %s uses an unauthorized "
                        "partition" % obligation["obligation_id"])
        dimension = obligation["dimension"] \
            if spec["dimension_binding"] == "profile-registration" else None
        candidates = tuple(resolve_obligation_definition(
            spec, obligation["target"], trigger=trigger,
            dimension=dimension, registered_dimensions=dimensions)
            for trigger in triggers)
        if obligation["status"] == "reused":
            candidates = tuple(
                row for row in candidates
                if obligation_id_for_definition(row) ==
                obligation["obligation_id"])
            if len(candidates) != 1:
                raise ValueError(
                    "AuditPlan reused obligation %s has no unique original "
                    "registered definition" % obligation["obligation_id"])
        expected = candidates[0]
        comparison = dict(expected)
        if obligation["status"] == "reused":
            comparison["partition"] = "reusable-evidence"
            comparison["fingerprint_binding"] = "reused-receipt"
        drift = sorted(
            field for field, value in comparison.items()
            if obligation.get(field) != value)
        if obligation["obligation_id"] != \
                obligation_id_for_definition(expected):
            drift.append("obligation_id")
        if drift:
            raise ValueError(
                "AuditPlan obligation %s drifts from registered owner %s in: "
                "%s" % (obligation["obligation_id"], rule_id,
                         ", ".join(sorted(set(drift)))))
    return plan


def _substantive_specs(root, snapshots, plan_values, dimensions):
    contract = substantive_review_contract.load_contract(root, snapshots)
    projection = substantive_review_contract.validate_contract(
        contract)["obligation_projection"]
    return (_spec(
        _plan_contract_values=plan_values,
        _registered_dimensions=dimensions,
        spec_id="substantive:%s" % projection["owner_rule_id"],
        source_registry=SUBSTANTIVE_REGISTRY_PATH,
        source_entry_id=projection["owner_rule_id"],
        owner_kind=projection["owner_kind"],
        owner_rule_id=projection["owner_rule_id"],
        kernel_extension_point=projection["kernel_extension_point"],
        target_source=projection["target_source"], tier=projection["tier"],
        applicability=projection["applicability"], partition=None,
        trigger_partition_mappings=projection["trigger_partition_mappings"],
        due_stage=projection["due_stage"],
        evidence_role=projection["evidence_role"],
        evidence_kind=projection["evidence_kind"],
        dimension=projection["dimension"], dimension_binding=None,
        acceptance_predicate=projection["acceptance_predicate"],
        producer_capability=projection["producer_capability"],
        producer_gate_id=projection["producer_gate_id"],
        producer_check=projection["producer_check"],
        consumer_gate_id=projection["consumer_gate_id"],
        fingerprint_binding=projection["fingerprint_binding"],
        nonblocking=None),)


def _batch_review_specs(root, snapshots, plan_values, dimensions):
    registry = batch_review_obligation_contract.load_registry(root, snapshots)
    result = []
    for row in batch_review_obligation_contract.base_obligation_specs(registry):
        entry_id = row.get("item_id") or row["rule_id"]
        result.append(_spec(
            _plan_contract_values=plan_values,
            _registered_dimensions=dimensions,
            spec_id="batch-review:%s" % entry_id,
            source_registry=BATCH_REVIEW_REGISTRY_PATH,
            source_entry_id=entry_id, owner_kind=row["owner_kind"],
            owner_rule_id=row["owner_rule_id"],
            kernel_extension_point=row["kernel_extension_point"],
            target_source=row["target_source"], tier=row["tier"],
            applicability=row["applicability"], partition=row["partition"],
            trigger_partition_mappings=row["trigger_partition_mappings"],
            due_stage=row["due_stage"], evidence_role=row["evidence_role"],
            evidence_kind=row["evidence_kind"], dimension=row["dimension"],
            dimension_binding=None,
            acceptance_predicate=row["acceptance_predicate"],
            producer_capability=row["producer_capability"],
            producer_gate_id=row["producer_gate_id"],
            producer_check=row["producer_check"],
            consumer_gate_id=row["consumer_gate_id"],
            fingerprint_binding=row["fingerprint_binding"],
            nonblocking=None))
    return tuple(result)


def _changed_scope_specs(root, snapshots, plan_values, dimensions):
    registry = load_changed_scope_registry(root, snapshots)
    values = validate_changed_scope_registry(
        registry, plan_values=plan_values, dimensions=dimensions)
    deterministic_rendering_contract.validate_registry_projection(
        registry,
        deterministic_rendering_contract.load_contract(root, snapshots),
        root=root, snapshots=snapshots)
    result = []
    for row in values["base_rules"]:
        result.append(_spec(
            _plan_contract_values=plan_values,
            _registered_dimensions=dimensions,
            spec_id="changed-scope:%s" % row["rule_id"],
            source_registry=CHANGED_SCOPE_REGISTRY_PATH,
            source_entry_id=row["rule_id"], owner_kind="kernel",
            owner_rule_id=row["rule_id"], kernel_extension_point=None,
            target_source="changed-scope", tier=None,
            applicability=row["applicability"],
            partition="changed-scope-deterministic",
            trigger_partition_mappings=(), due_stage=row["due_stage"],
            evidence_role=row["evidence_role"],
            evidence_kind=row["evidence_kind"], dimension=row["dimension"],
            dimension_binding=row["dimension_binding"],
            acceptance_predicate=row["rule_id"],
            producer_capability=row["producer_capability"],
            producer_gate_id=row["producer_gate_id"],
            producer_check=row["producer_check"],
            consumer_gate_id=row["consumer_gate_id"],
            fingerprint_binding="evidence-time",
            nonblocking=row["nonblocking"]))
    return tuple(result)


def _batch_close_specs(root, snapshots, plan_values, dimensions):
    document, text = _read_document(BATCH_CLOSE_REGISTRY_PATH, root, snapshots)
    batch_close_contract.validate_batch_close_closed_list(document)
    rows = batch_close_contract.closed_list_member_rows(_root(root), text=text)
    result = []
    for row in rows:
        result.append(_spec(
            _plan_contract_values=plan_values,
            _registered_dimensions=dimensions,
            spec_id="batch-close:%s" % row["member_id"],
            source_registry=BATCH_CLOSE_REGISTRY_PATH,
            source_entry_id=row["member_id"], owner_kind="kernel",
            owner_rule_id=row["rule_id"], kernel_extension_point=None,
            target_source="post-delta-after-image", tier=None,
            applicability="mandatory",
            partition="mandatory-full-deterministic",
            trigger_partition_mappings=(), due_stage=row["due_stage"],
            evidence_role=row["evidence_role"],
            evidence_kind=row["evidence_kind"], dimension=row["dimension"],
            dimension_binding=row["dimension_binding"],
            acceptance_predicate=row["rule_id"],
            producer_capability=row.get("producer_capability"),
            producer_gate_id=row.get("producer_gate_id"),
            producer_check=row["producer_check"],
            consumer_gate_id=row["consumer_gate_id"],
            fingerprint_binding="evidence-time", nonblocking=False))
    return tuple(result)


def _reject_unadmitted_rendering_specs(specs, root, snapshots=None):
    """Reject K12/02 prose gaps at the one global AuditPlan boundary."""
    deterministic = deterministic_rendering_contract.validate_contract(
        deterministic_rendering_contract.load_contract(root, snapshots),
        root=root, snapshots=snapshots)
    gap_ids = frozenset(
        row["gap_id"] for row in deterministic["contract_gaps"])
    admitted_owner_ids = {
        row["predicate_id"] for row in deterministic["admitted_predicates"]}
    rendering = rendering_verification_contract.load_contract(
        root, snapshots)
    rendering_verification_contract.validate_contract(rendering)
    # Rendering contributes only its record-shape predicate identity here.
    # Applicability and the complete obligation projection come exclusively
    # from the changed-scope registry rows already present in ``specs``.
    admitted_owner_ids.add(rendering["acceptance_predicate"])

    for spec in specs:
        identities = {
            spec.get("owner_rule_id"), spec.get("acceptance_predicate"),
            spec.get("source_entry_id"),
        }
        prohibited = sorted(gap_ids & identities)
        if prohibited:
            raise ValueError(
                "AuditPlan projection promotes K12/02 contract gap: %s" %
                ", ".join(prohibited))
        owner = spec.get("owner_rule_id")
        if (spec.get("owner_kind") == "kernel" and
                isinstance(owner, str) and owner.startswith("k12-02-") and
                owner not in admitted_owner_ids):
            raise ValueError(
                "AuditPlan projection contains unadmitted K12/02 owner %s" %
                owner)
    return tuple(specs)


_BASE_PROJECTION_SOURCE_PATHS = (
    audit_plan_contract.AUDIT_PLAN_CONTRACT_PATH,
    audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH,
    SUBSTANTIVE_REGISTRY_PATH,
    BATCH_REVIEW_REGISTRY_PATH,
    CHANGED_SCOPE_REGISTRY_PATH,
    BATCH_CLOSE_REGISTRY_PATH,
    deterministic_rendering_contract.CONTRACT_PATH,
    rendering_verification_contract.RENDERING_VERIFICATION_CONTRACT_PATH,
)


def _base_projection_source_bundle(root, snapshots):
    # AuditPlan and dimension registries are installed Tool contracts, not
    # adopter runtime data. Existing callers may pass a partial runtime root
    # containing only the contracts they are exercising; explicit snapshots
    # still override these two owners for contract tests.
    installed_contracts = {
        audit_plan_contract.AUDIT_PLAN_CONTRACT_PATH,
        audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH,
    }
    return tuple(
        (path, _source_text(
            path, None if path in installed_contracts else root, snapshots))
        for path in _BASE_PROJECTION_SOURCE_PATHS)


@lru_cache(maxsize=32)
def _base_obligation_specs_for_exact_sources(root, source_bundle):
    """Build once for one complete immutable machine-source snapshot."""
    snapshots = {
        path: _TextSnapshot(text) for path, text in source_bundle}
    plan_values = _plan_values(root, snapshots)
    dimensions = _dimension_values(root, snapshots)
    specs = (
        _substantive_specs(root, snapshots, plan_values, dimensions) +
        _batch_review_specs(root, snapshots, plan_values, dimensions) +
        _changed_scope_specs(root, snapshots, plan_values, dimensions) +
        _batch_close_specs(root, snapshots, plan_values, dimensions)
    )
    spec_ids = [row["spec_id"] for row in specs]
    rule_ids = [row["owner_rule_id"] for row in specs]
    if len(spec_ids) != len(set(spec_ids)):
        raise ValueError("Kernel base projection repeats spec_id")
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Kernel base projection repeats owner_rule_id")
    if any(row["owner_kind"] != "kernel" or
           row["kernel_extension_point"] is not None for row in specs):
        raise ValueError("Kernel base projection contains a Profile extension")
    _reject_unadmitted_rendering_specs(specs, root, snapshots)
    return tuple(deepcopy(row) for row in specs)


def base_obligation_specs(root=None, snapshots=None):
    """Return the complete Kernel base set; never include Profile rows.

    The cache key contains every authoritative source byte used by the
    projection. A changed contract therefore produces a different cache
    entry; callers receive deep copies so no consumer can mutate the shared
    verified projection.
    """
    root = _root(root)
    specs = _base_obligation_specs_for_exact_sources(
        root, _base_projection_source_bundle(root, snapshots))
    return tuple(deepcopy(row) for row in specs)


def obligation_spec_for_rule(rule_id, root=None, snapshots=None):
    """Resolve exactly one base spec by stable owner rule ID."""
    rule_id = require_trimmed_string(rule_id, "rule_id")
    matches = [row for row in base_obligation_specs(root, snapshots)
               if row["owner_rule_id"] == rule_id]
    if len(matches) != 1:
        raise ValueError("unknown or ambiguous base obligation rule %s" % rule_id)
    return matches[0]


def resolve_obligation_definition(spec, target, trigger=None, dimension=None,
                                  registered_dimensions=None):
    """Resolve one base template into the frozen AuditPlan definition fields."""
    if not isinstance(spec, dict) or set(spec) != _SPEC_FIELDS:
        raise ValueError("obligation spec fields are not closed")
    dimensions = set(registered_dimensions or _dimension_values())
    spec = _spec(_registered_dimensions=dimensions, **deepcopy(spec))
    target = require_trimmed_string(target, "target")
    mappings = spec["trigger_partition_mappings"]
    if mappings:
        trigger = require_trimmed_string(trigger, "trigger")
        partitions = [row["partition"] for row in mappings
                      if row["trigger"] == trigger]
        if len(partitions) != 1:
            raise ValueError(
                "obligation spec has no unique partition for trigger %s" %
                trigger)
        partition = partitions[0]
    else:
        if trigger is not None:
            raise ValueError("fixed-partition obligation does not accept trigger")
        partition = spec["partition"]

    resolved_dimension = spec["dimension"]
    if spec["dimension_binding"] == "profile-registration":
        resolved_dimension = require_trimmed_string(dimension, "dimension")
    elif dimension is not None and dimension != resolved_dimension:
        raise ValueError("caller cannot change a fixed obligation dimension")
    if resolved_dimension is not None and resolved_dimension not in dimensions:
        raise ValueError("resolved obligation dimension is not registered")
    if (spec["evidence_kind"] == "audit-receipt" and
            (spec["evidence_role"] != "emits" or
             resolved_dimension is None)):
        raise ValueError("resolved AuditReceipt obligation needs one dimension")
    definition = {
        "owner_kind": spec["owner_kind"],
        "owner_rule_id": spec["owner_rule_id"],
        "kernel_extension_point": spec["kernel_extension_point"],
        "partition": partition,
        "due_stage": spec["due_stage"],
        "target": target,
        "applicability": spec["applicability"],
        "evidence_role": spec["evidence_role"],
        "evidence_kind": spec["evidence_kind"],
        "dimension": resolved_dimension,
        "acceptance_predicate": spec["acceptance_predicate"],
        "producer_capability": spec["producer_capability"],
        "producer_gate_id": spec["producer_gate_id"],
        "producer_check": spec["producer_check"],
        "consumer_gate_id": spec["consumer_gate_id"],
        "fingerprint_binding": spec["fingerprint_binding"],
    }
    if set(definition) != _DEFINITION_FIELDS:
        raise AssertionError("resolved obligation definition drifted")
    return definition


def compose_profile_extensions(base_specs, profile_specs,
                               registered_dimensions=None, root=None,
                               snapshots=None):
    """Compose already-registered Profile specs through a separate boundary."""
    if not isinstance(base_specs, (list, tuple)) or not isinstance(
            profile_specs, (list, tuple)):
        raise ValueError("base_specs and profile_specs must be sequences")
    dimensions = set(registered_dimensions or _dimension_values())
    base = tuple(_spec(_registered_dimensions=dimensions, **deepcopy(row))
                 for row in base_specs)
    if any(row["owner_kind"] != "kernel" for row in base):
        raise ValueError("base_specs must remain Kernel-owned")
    plan_values = _plan_values()
    profile = []
    for row in profile_specs:
        projected = _spec(
            _registered_dimensions=dimensions, **deepcopy(row))
        if (projected["owner_kind"] != "profile-extension" or
                projected["kernel_extension_point"] not in
                plan_values["extension_points"]):
            raise ValueError(
                "Profile spec must use a registered Kernel extension point")
        if (projected["dimension"] is not None and
                projected["dimension"] not in dimensions):
            raise ValueError("Profile spec dimension is not registered")
        profile.append(projected)
    combined = base + tuple(profile)
    spec_ids = [row["spec_id"] for row in combined]
    rule_ids = [row["owner_rule_id"] for row in combined]
    if len(spec_ids) != len(set(spec_ids)) or \
            len(rule_ids) != len(set(rule_ids)):
        raise ValueError("composed obligation specs repeat an identity")
    _reject_unadmitted_rendering_specs(
        combined, _root(root), snapshots)
    return tuple(deepcopy(row) for row in combined)


__all__ = [
    'BATCH_CLOSE_REGISTRY_PATH',
    'CHANGED_SCOPE_REGISTRY_PATH',
    'PROFILE_REGISTERED_SCAN_EXTENSION',
    'SUBSTANTIVE_REGISTRY_PATH',
    'composed_obligation_specs',
    'load_changed_scope_registry',
    'obligation_spec_for_rule',
    'profile_registered_scan_spec',
    'required_obligation',
    'resolve_obligation_definition',
    'validate_changed_scope_registry',
    'validate_plan_definition_authority',
]
