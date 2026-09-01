"""Strict K12/14 batch-review registry loader and Tool projection.

The Kernel YAML owns the M atomic set, the S sampling count, obligation
bindings, and the producer-record shape.  This module validates and projects
that document mechanically.  It does not restate the 34 current M items or
the seven display groups.
"""
from Tools.platform.repository.repository import repository_source_root

from copy import deepcopy
from datetime import datetime, timezone
import os
import re

import Tools.execution.audit.audit_fingerprint as audit_fingerprint
import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.evidence.evidence_attempt_runtime as evidence_attempt_runtime
import Tools.platform.common.kblib as kblib
from Tools.platform.common.primitives import catalog_record, require_trimmed_string


BATCH_REVIEW_OBLIGATION_REGISTRY_PATH = (
    "kernel/K12 Quality Assurance/batch-review-obligation-registry.yaml")
PRODUCER_TOOL = "record_batch_page_review"
PRODUCER_TOOL_VERSION = "2.0.0"
RECEIPT_TYPE_ID = "batch-page-review-record-v3"
S_SELECTION_ALGORITHM_ID = "batch-s-sha256-rank-v1"

_TOP_FIELDS = {
    "schema_version", "registry_id", "semantic_owner",
    "machine_projection_owner", "closed_world", "audit_plan_projection",
    "m_applicability_contract", "m_consumption_contracts",
    "m_tier_source_groups", "m_tier_atomic_items", "s_tier_sampling",
    "producer_evidence_contract",
}
_CLOSED_WORLD_FIELDS = {
    "m_tier_atomic_items", "source_groups_are_obligations",
    "profile_extensions_in_base_set", "unknown_item_fields",
}
_PLAN_PROJECTION_FIELDS = {
    "owner_kind", "kernel_extension_point", "target_source",
    "acceptance_predicate_source", "evidence_kind", "consumer_gate_id",
    "due_stage", "fingerprint_binding", "trigger_partition_mappings",
    "trigger_meanings",
}
_TRIGGER_PARTITION_FIELDS = {"trigger", "partition"}
_M_APPLICABILITY_FIELDS = {
    "unconditional_predicate", "disposition_values", "applicable_reason",
    "not_applicable_reason", "plan_definition_policy",
}
_M_CONSUMPTION_FIELDS = {
    "item_id", "resolution", "selector", "hold_reason",
}
_M_CONSUMPTION_SELECTOR_FIELDS = {
    "selector_id", "source", "owner_kind", "owner_rule_ids",
    "kernel_extension_point", "partition", "due_stage", "target_binding",
    "evidence_role", "obligation_status", "consumer_gate_id",
    "evidence_currency", "evidence_result_values", "match_cardinality",
}
_SOURCE_GROUP_FIELDS = {"group_id", "display_order", "source_text"}
_M_ITEM_FIELDS = {
    "item_id", "rule_id", "source_group", "applicability",
    "acceptance_contract", "evidence_role", "evidence_kind", "dimension",
    "producer_capability", "producer_check", "consumer_gate_id",
    "due_stage", "trigger_partition_mappings",
}
_ACCEPTANCE_CONTRACT_FIELDS = {"contract_id", "text"}
_S_SAMPLING_FIELDS = {
    "rule_id", "population", "sample_count", "selection_execution",
    "sampled_review_obligation",
}
_S_POPULATION_FIELDS = {"target_source", "tier", "variable"}
_S_COUNT_FIELDS = {
    "when_n_less_than_minimum", "minimum_count", "percentage_numerator",
    "percentage_denominator", "rounding", "otherwise",
    "integer_equivalent",
}
_S_SELECTION_EXECUTION_FIELDS = {
    "authority", "kernel_meaning", "requirements",
}
_S_OBLIGATION_FIELDS = {
    "applicability", "acceptance_contract", "evidence_role",
    "evidence_kind", "dimension", "producer_capability", "producer_check",
    "consumer_gate_id", "due_stage", "partition", "fingerprint_binding",
}
_PRODUCER_CONTRACT_FIELDS = {
    "contract_id", "record_kind", "unknown_fields", "fields",
    "required_common_fields", "variants", "result_values",
    "verdict_result_mappings",
}
_PRODUCER_FIELD_FIELDS = {"field", "type"}
_PRODUCER_VARIANT_FIELDS = {
    "review_variant", "tier", "required_fields", "forbidden_fields",
    "invariants",
}
_VERDICT_MAPPING_FIELDS = {"verdict", "result"}
_PRODUCER_FIELD_TYPES = {
    "integer", "string", "sha256", "utc-timestamp", "nullable-string",
    "string-list",
}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_UTC_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z\Z")


def _closed_mapping(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("%s fields are not closed" % label)
    return value


def _string_list(value, label, *, allow_empty=False, sorted_unique=False):
    if (not isinstance(value, list) or (not value and not allow_empty) or
            any(not isinstance(item, str) or not item or
                item.strip() != item for item in value)):
        raise ValueError("%s must be a%s string list" % (
            label, " possibly empty" if allow_empty else " non-empty"))
    if len(value) != len(set(value)):
        raise ValueError("%s must not contain duplicates" % label)
    if sorted_unique and value != sorted(value):
        raise ValueError("%s must be sorted" % label)
    return tuple(value)


def _acceptance_contract(value, label):
    _closed_mapping(value, _ACCEPTANCE_CONTRACT_FIELDS, label)
    return {
        "contract_id": require_trimmed_string(
            value.get("contract_id"), label + ".contract_id"),
        "text": require_trimmed_string(value.get("text"), label + ".text"),
    }


def _trigger_mappings(value, label, plan_values):
    if not isinstance(value, list) or not value:
        raise ValueError("%s must be a non-empty list" % label)
    mappings = []
    triggers = set()
    for index, row in enumerate(value):
        row_label = "%s[%d]" % (label, index)
        _closed_mapping(row, _TRIGGER_PARTITION_FIELDS, row_label)
        trigger = require_trimmed_string(row.get("trigger"), row_label + ".trigger")
        partition = require_trimmed_string(
            row.get("partition"), row_label + ".partition")
        if trigger in triggers:
            raise ValueError("%s repeats trigger %s" % (label, trigger))
        if partition not in plan_values["partitions"]:
            raise ValueError("%s uses an unregistered partition" % row_label)
        triggers.add(trigger)
        mappings.append({"trigger": trigger, "partition": partition})
    return tuple(mappings)


def _producer_field_specs(value):
    if not isinstance(value, list) or not value:
        raise ValueError("producer_evidence_contract.fields must be non-empty")
    order = []
    specs = {}
    for index, row in enumerate(value):
        label = "producer_evidence_contract.fields[%d]" % index
        _closed_mapping(row, _PRODUCER_FIELD_FIELDS, label)
        field = require_trimmed_string(row.get("field"), label + ".field")
        type_id = row.get("type")
        if field in specs:
            raise ValueError("producer evidence repeats field %s" % field)
        if type_id not in _PRODUCER_FIELD_TYPES:
            raise ValueError("%s has unknown type %r" % (label, type_id))
        order.append(field)
        specs[field] = type_id
    return tuple(order), specs


def _producer_contract(value):
    label = "producer_evidence_contract"
    _closed_mapping(value, _PRODUCER_CONTRACT_FIELDS, label)
    if value.get("contract_id") != "cambium-batch-page-review-record":
        raise ValueError("batch-page producer contract_id is invalid")
    if value.get("record_kind") != "batch-page-review-record":
        raise ValueError("batch-page record_kind is invalid")
    if value.get("unknown_fields") != "reject":
        raise ValueError("batch-page producer must reject unknown fields")
    field_order, fields = _producer_field_specs(value.get("fields"))
    common = _string_list(
        value.get("required_common_fields"),
        label + ".required_common_fields")
    if any(field not in fields for field in common):
        raise ValueError("producer common fields must be declared")

    variants = value.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError("producer variants must be non-empty")
    by_variant = {}
    covered = set(common)
    for index, row in enumerate(variants):
        row_label = "%s.variants[%d]" % (label, index)
        _closed_mapping(row, _PRODUCER_VARIANT_FIELDS, row_label)
        variant = require_trimmed_string(
            row.get("review_variant"), row_label + ".review_variant")
        tier = require_trimmed_string(row.get("tier"), row_label + ".tier")
        required = _string_list(
            row.get("required_fields"), row_label + ".required_fields")
        forbidden = _string_list(
            row.get("forbidden_fields"), row_label + ".forbidden_fields")
        invariants = _string_list(
            row.get("invariants"), row_label + ".invariants")
        if variant in by_variant:
            raise ValueError("producer repeats review_variant %s" % variant)
        if set(required).intersection(forbidden):
            raise ValueError("%s required/forbidden fields overlap" % row_label)
        if any(field not in fields for field in required + forbidden):
            raise ValueError("%s names an undeclared producer field" % row_label)
        if set(common).intersection(forbidden):
            raise ValueError("%s forbids a required common field" % row_label)
        expected = set(common).union(required)
        unexpected = set(fields) - expected - set(forbidden)
        if unexpected:
            raise ValueError(
                "%s leaves producer fields unclassified: %s" %
                (row_label, ", ".join(sorted(unexpected))))
        covered.update(required)
        by_variant[variant] = {
            "tier": tier,
            "required_fields": required,
            "forbidden_fields": forbidden,
            "invariants": invariants,
            "instance_fields": frozenset(expected),
        }
    if covered != set(fields):
        raise ValueError("producer variants do not cover every declared field")

    results = _string_list(
        value.get("result_values"), label + ".result_values")
    mappings = value.get("verdict_result_mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("producer verdict mappings must be non-empty")
    verdict_results = {}
    for index, row in enumerate(mappings):
        row_label = "%s.verdict_result_mappings[%d]" % (label, index)
        _closed_mapping(row, _VERDICT_MAPPING_FIELDS, row_label)
        verdict = require_trimmed_string(row.get("verdict"), row_label + ".verdict")
        result = require_trimmed_string(row.get("result"), row_label + ".result")
        if verdict in verdict_results or result not in results:
            raise ValueError("%s is invalid" % row_label)
        verdict_results[verdict] = result
    if set(verdict_results.values()) != set(results):
        raise ValueError("every producer result needs a verdict mapping")
    return {
        "field_order": field_order,
        "fields": fields,
        "common_fields": common,
        "variants": by_variant,
        "results": frozenset(results),
        "verdict_results": verdict_results,
    }


def validate_registry(document):
    """Validate the complete Kernel registry and return derived values."""
    _closed_mapping(document, _TOP_FIELDS, "batch-review registry")
    if document.get("schema_version") != 3:
        raise ValueError("batch-review registry schema_version must be 3")
    if document.get("registry_id") != "cambium-batch-review-obligations":
        raise ValueError("batch-review registry_id is invalid")
    if document.get("semantic_owner") != "K12/01-K12/14":
        raise ValueError("batch-review semantic_owner is invalid")
    if document.get("machine_projection_owner") != "K12/14":
        raise ValueError("batch-review machine projection owner is invalid")

    closed = _closed_mapping(
        document.get("closed_world"), _CLOSED_WORLD_FIELDS, "closed_world")
    if closed != {
            "m_tier_atomic_items": True,
            "source_groups_are_obligations": False,
            "profile_extensions_in_base_set": False,
            "unknown_item_fields": "reject"}:
        raise ValueError("batch-review closed-world declaration is invalid")

    applicability_contract = _closed_mapping(
        document.get("m_applicability_contract"),
        _M_APPLICABILITY_FIELDS, "m_applicability_contract")
    disposition_values = _string_list(
        applicability_contract.get("disposition_values"),
        "m_applicability_contract.disposition_values")
    if (applicability_contract.get("unconditional_predicate") != "always" or
            set(disposition_values) != {"applicable", "not-applicable"} or
            applicability_contract.get("applicable_reason") is not None or
            applicability_contract.get("not_applicable_reason") !=
            "nonempty" or
            applicability_contract.get("plan_definition_policy") !=
            "freeze-all-registered-atoms"):
        raise ValueError("M applicability disposition contract is invalid")

    plan_contract = audit_plan_contract.validate_contract(
        audit_plan_contract.load_contract())
    dimension_contract = audit_dimension_contract.\
        validate_audit_dimension_base(
            audit_dimension_contract.load_audit_dimension_base())
    dimensions = set(dimension_contract["base_receipt_dimensions"])
    roles = set(dimension_contract["evidence_roles"])

    projection = _closed_mapping(
        document.get("audit_plan_projection"), _PLAN_PROJECTION_FIELDS,
        "audit_plan_projection")
    for field in (
            "owner_kind", "target_source", "acceptance_predicate_source",
            "evidence_kind", "consumer_gate_id", "due_stage",
            "fingerprint_binding"):
        require_trimmed_string(projection.get(field), "audit_plan_projection.%s" % field)
    if projection.get("kernel_extension_point") is not None:
        raise ValueError("Kernel batch review cannot claim an extension point")
    if projection["owner_kind"] not in plan_contract["owner_kinds"]:
        raise ValueError("batch-review owner_kind is not registered")
    if projection["owner_kind"] != "kernel":
        raise ValueError("base batch-review obligations must be Kernel-owned")
    if projection["evidence_kind"] not in plan_contract["evidence_kinds"]:
        raise ValueError("batch-review evidence_kind is not registered")
    if projection["due_stage"] not in plan_contract["due_stages"]:
        raise ValueError("batch-review due_stage is not registered")
    if projection["fingerprint_binding"] not in \
            plan_contract["fingerprint_bindings"]:
        raise ValueError("batch-review fingerprint binding is not registered")
    if projection["acceptance_predicate_source"] != \
            "acceptance_contract.contract_id":
        raise ValueError("batch-review acceptance projection is invalid")
    mappings = _trigger_mappings(
        projection.get("trigger_partition_mappings"),
        "audit_plan_projection.trigger_partition_mappings", plan_contract)
    meanings = projection.get("trigger_meanings")
    if (not isinstance(meanings, dict) or
            set(meanings) != {row["trigger"] for row in mappings}):
        raise ValueError("batch-review trigger_meanings do not match mappings")
    for trigger, meaning in meanings.items():
        require_trimmed_string(meaning, "trigger_meanings.%s" % trigger)

    groups = document.get("m_tier_source_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("m_tier_source_groups must be non-empty")
    groups_by_id = {}
    for index, row in enumerate(groups):
        label = "m_tier_source_groups[%d]" % index
        _closed_mapping(row, _SOURCE_GROUP_FIELDS, label)
        group_id = require_trimmed_string(row.get("group_id"), label + ".group_id")
        if group_id in groups_by_id:
            raise ValueError("batch-review repeats source group %s" % group_id)
        if row.get("display_order") != index + 1:
            raise ValueError("M source-group display order must be contiguous")
        require_trimmed_string(row.get("source_text"), label + ".source_text")
        groups_by_id[group_id] = deepcopy(row)

    items = document.get("m_tier_atomic_items")
    if not isinstance(items, list) or not items:
        raise ValueError("m_tier_atomic_items must be non-empty")
    items_by_id = {}
    items_by_rule = {}
    contract_ids = set()
    used_groups = set()
    normalized_items = []
    for index, row in enumerate(items):
        label = "m_tier_atomic_items[%d]" % index
        _closed_mapping(row, _M_ITEM_FIELDS, label)
        item_id = require_trimmed_string(row.get("item_id"), label + ".item_id")
        rule_id = require_trimmed_string(row.get("rule_id"), label + ".rule_id")
        group_id = require_trimmed_string(
            row.get("source_group"), label + ".source_group")
        applicability = require_trimmed_string(
            row.get("applicability"), label + ".applicability")
        acceptance = _acceptance_contract(
            row.get("acceptance_contract"), label + ".acceptance_contract")
        if item_id in items_by_id or rule_id in items_by_rule:
            raise ValueError("M item_id and rule_id must be unique")
        if acceptance["contract_id"] in contract_ids:
            raise ValueError("M acceptance contract IDs must be unique")
        if group_id not in groups_by_id:
            raise ValueError("M item names an unknown source group")
        role = row.get("evidence_role")
        dimension = row.get("dimension")
        if role not in roles:
            raise ValueError("%s evidence_role is not registered" % label)
        if dimension not in dimensions:
            raise ValueError("%s must bind exactly one base dimension" % label)
        if row.get("evidence_kind") != projection["evidence_kind"]:
            raise ValueError("%s changes the projected evidence kind" % label)
        capability = require_trimmed_string(
            row.get("producer_capability"), label + ".producer_capability")
        if row.get("producer_check") != "batch_page_review:" + item_id:
            raise ValueError("%s producer_check must derive from item_id" % label)
        if row.get("consumer_gate_id") != projection["consumer_gate_id"]:
            raise ValueError("%s changes the projected consumer" % label)
        if row.get("due_stage") != projection["due_stage"]:
            raise ValueError("%s changes the projected due stage" % label)
        item_mappings = _trigger_mappings(
            row.get("trigger_partition_mappings"),
            label + ".trigger_partition_mappings", plan_contract)
        if item_mappings != mappings:
            raise ValueError("%s changes trigger partition routing" % label)
        normalized = {
            "item_id": item_id,
            "rule_id": rule_id,
            "source_group": group_id,
            "applicability": applicability,
            "acceptance_contract": acceptance,
            "evidence_role": role,
            "evidence_kind": row["evidence_kind"],
            "dimension": dimension,
            "producer_capability": capability,
            "producer_check": row["producer_check"],
            "consumer_gate_id": row["consumer_gate_id"],
            "due_stage": row["due_stage"],
            "trigger_partition_mappings": item_mappings,
        }
        items_by_id[item_id] = normalized
        items_by_rule[rule_id] = normalized
        contract_ids.add(acceptance["contract_id"])
        used_groups.add(group_id)
        normalized_items.append(normalized)
    if used_groups != set(groups_by_id):
        raise ValueError("every M source group must own an atomic item")

    consumption_rows = document.get("m_consumption_contracts")
    if not isinstance(consumption_rows, list) or not consumption_rows:
        raise ValueError("m_consumption_contracts must be non-empty")
    consumption_by_item_id = {}
    for index, row in enumerate(consumption_rows):
        label = "m_consumption_contracts[%d]" % index
        _closed_mapping(row, _M_CONSUMPTION_FIELDS, label)
        item_id = require_trimmed_string(row.get("item_id"), label + ".item_id")
        if item_id in consumption_by_item_id:
            raise ValueError("M consumption contracts repeat item_id")
        item = items_by_id.get(item_id)
        if item is None or item["evidence_role"] != "consumes":
            raise ValueError(
                "%s must name a consumes-role M item" % label)
        resolution = row.get("resolution")
        if resolution not in {"resolved", "hold"}:
            raise ValueError("%s resolution must be resolved or hold" % label)
        selector = row.get("selector")
        hold_reason = row.get("hold_reason")
        if resolution == "hold":
            if selector is not None:
                raise ValueError("%s HOLD cannot declare a selector" % label)
            hold_reason = require_trimmed_string(
                hold_reason, label + ".hold_reason")
        else:
            if hold_reason is not None:
                raise ValueError(
                    "%s resolved selector cannot declare a HOLD reason" %
                    label)
            selector = _closed_mapping(
                selector, _M_CONSUMPTION_SELECTOR_FIELDS,
                label + ".selector")
            for field in (
                    "selector_id", "source", "owner_kind", "partition", "due_stage",
                    "target_binding", "evidence_role", "obligation_status",
                    "consumer_gate_id", "evidence_currency",
                    "match_cardinality"):
                require_trimmed_string(selector.get(field),
                          label + ".selector." + field)
            result_values = _string_list(
                selector.get("evidence_result_values"),
                label + ".selector.evidence_result_values")
            owner_rule_ids = selector.get("owner_rule_ids")
            if owner_rule_ids is not None:
                owner_rule_ids = _string_list(
                    owner_rule_ids,
                    label + ".selector.owner_rule_ids",
                    sorted_unique=True)
            cardinality = selector.get("match_cardinality")
            if (selector["source"] != "audit-plan-obligation-evidence" or
                    selector["owner_kind"] != "kernel" or
                    selector["kernel_extension_point"] is not None or
                    selector["partition"] not in plan_contract["partitions"] or
                    selector["due_stage"] not in plan_contract["due_stages"] or
                    selector["target_binding"] != "same-page" or
                    selector["evidence_role"] != "emits" or
                    selector["obligation_status"] != "required" or
                    selector["consumer_gate_id"] !=
                    projection["consumer_gate_id"] or
                    selector["evidence_currency"] != "current" or
                    set(result_values) != {"pass", "passed"} or
                    cardinality not in {
                        "exactly-one",
                        "one-or-more-all-matching-required"} or
                    (cardinality == "exactly-one" and
                     (owner_rule_ids is None or len(owner_rule_ids) != 1))):
                raise ValueError(
                    "%s selector is not the admitted exact AuditPlan selector"
                    % label)
            selector = deepcopy(selector)
            selector["owner_rule_ids"] = owner_rule_ids
            selector["evidence_result_values"] = result_values
        consumption_by_item_id[item_id] = {
            "item_id": item_id,
            "resolution": resolution,
            "selector": deepcopy(selector),
            "hold_reason": hold_reason,
        }
    consumes_item_ids = {
        item["item_id"] for item in normalized_items
        if item["evidence_role"] == "consumes"
    }
    if set(consumption_by_item_id) != consumes_item_ids:
        raise ValueError(
            "M consumption contracts must cover exactly every consumes item")

    sampling = _closed_mapping(
        document.get("s_tier_sampling"), _S_SAMPLING_FIELDS,
        "s_tier_sampling")
    s_rule_id = require_trimmed_string(
        sampling.get("rule_id"), "s_tier_sampling.rule_id")
    if s_rule_id in items_by_rule:
        raise ValueError("S sampling rule_id collides with an M item")
    population = _closed_mapping(
        sampling.get("population"), _S_POPULATION_FIELDS,
        "s_tier_sampling.population")
    if (population.get("target_source") != "current-batch-manifest-pages" or
            population.get("tier") != "S" or population.get("variable") != "n"):
        raise ValueError("S sampling population projection is invalid")
    count = _closed_mapping(
        sampling.get("sample_count"), _S_COUNT_FIELDS,
        "s_tier_sampling.sample_count")
    for field in (
            "minimum_count", "percentage_numerator",
            "percentage_denominator"):
        if (not isinstance(count.get(field), int) or
                isinstance(count.get(field), bool) or count[field] <= 0):
            raise ValueError("S sample count parameters must be positive")
    minimum = count["minimum_count"]
    numerator = count["percentage_numerator"]
    denominator = count["percentage_denominator"]
    if numerator > denominator:
        raise ValueError("S sample percentage cannot exceed the population")
    if count.get("when_n_less_than_minimum") != "all":
        raise ValueError("S undersized population must be checked in full")
    if count.get("rounding") != "ceiling":
        raise ValueError("S percentage rounding must be ceiling")
    if count.get("otherwise") != "max(%d, ceil(n * %d / %d))" % (
            minimum, numerator, denominator):
        raise ValueError("S sample expression disagrees with its parameters")
    if count.get("integer_equivalent") != \
            "max(%d, (n * %d + %d) // %d)" % (
                minimum, numerator, denominator - 1, denominator):
        raise ValueError("S integer sample expression is not ceiling")

    execution = _closed_mapping(
        sampling.get("selection_execution"),
        _S_SELECTION_EXECUTION_FIELDS,
        "s_tier_sampling.selection_execution")
    if execution.get("authority") != "tool" or \
            execution.get("kernel_meaning") != "none":
        raise ValueError("S concrete selection must remain Tool-owned")
    _string_list(
        execution.get("requirements"),
        "s_tier_sampling.selection_execution.requirements")

    s_obligation = _closed_mapping(
        sampling.get("sampled_review_obligation"), _S_OBLIGATION_FIELDS,
        "s_tier_sampling.sampled_review_obligation")
    applicability = require_trimmed_string(
        s_obligation.get("applicability"),
        "sampled_review_obligation.applicability")
    acceptance = _acceptance_contract(
        s_obligation.get("acceptance_contract"),
        "sampled_review_obligation.acceptance_contract")
    if acceptance["contract_id"] in contract_ids:
        raise ValueError("S acceptance contract collides with an M contract")
    if s_obligation.get("evidence_role") not in roles:
        raise ValueError("S sampled review evidence_role is not registered")
    if s_obligation.get("evidence_kind") != projection["evidence_kind"]:
        raise ValueError("S sampled review changes the projected evidence kind")
    if s_obligation.get("dimension") is not None:
        raise ValueError("S sampled page evidence must remain dimensionless")
    if s_obligation.get("consumer_gate_id") != projection["consumer_gate_id"]:
        raise ValueError("S sampled review changes the projected consumer")
    if s_obligation.get("due_stage") != projection["due_stage"]:
        raise ValueError("S sampled review changes the projected due stage")
    if s_obligation.get("partition") not in plan_contract["partitions"]:
        raise ValueError("S sampled review partition is not registered")
    if s_obligation.get("fingerprint_binding") != \
            projection["fingerprint_binding"]:
        raise ValueError("S sampled review changes fingerprint binding")
    require_trimmed_string(
        s_obligation.get("producer_capability"),
        "sampled_review_obligation.producer_capability")
    require_trimmed_string(
        s_obligation.get("producer_check"),
        "sampled_review_obligation.producer_check")

    producer = _producer_contract(document.get("producer_evidence_contract"))
    if set(producer["variants"]) != {"m-atomic-item", "s-sampled-page"}:
        raise ValueError("producer variants must cover M atomic and sampled S")
    if (producer["variants"]["m-atomic-item"]["tier"] != "M" or
            producer["variants"]["s-sampled-page"]["tier"] != "S"):
        raise ValueError("producer variants bind the wrong tier")

    return {
        "projection": deepcopy(projection),
        "m_applicability": {
            "unconditional_predicate":
                applicability_contract["unconditional_predicate"],
            "disposition_values": disposition_values,
            "applicable_reason": None,
            "not_applicable_reason": "nonempty",
            "plan_definition_policy": "freeze-all-registered-atoms",
        },
        "m_consumption_by_item_id": consumption_by_item_id,
        "trigger_partition_mappings": mappings,
        "groups_by_id": groups_by_id,
        "m_items": tuple(normalized_items),
        "m_items_by_id": items_by_id,
        "m_items_by_rule": items_by_rule,
        "s_rule_id": s_rule_id,
        "s_population": deepcopy(population),
        "s_count": deepcopy(count),
        "s_obligation": {
            "applicability": applicability,
            "acceptance_contract": acceptance,
            "evidence_role": s_obligation["evidence_role"],
            "evidence_kind": s_obligation["evidence_kind"],
            "dimension": None,
            "producer_capability": s_obligation["producer_capability"],
            "producer_check": s_obligation["producer_check"],
            "consumer_gate_id": s_obligation["consumer_gate_id"],
            "due_stage": s_obligation["due_stage"],
            "partition": s_obligation["partition"],
            "fingerprint_binding": s_obligation["fingerprint_binding"],
        },
        "producer": producer,
    }


def load_registry(root=None, snapshots=None):
    """Load the current Kernel-owned K12/14 registry."""
    if root is None:
        root = repository_source_root(__file__)
    snapshot = (snapshots or {}).get(BATCH_REVIEW_OBLIGATION_REGISTRY_PATH)
    if snapshot is not None:
        text = snapshot.read_text()
    else:
        text = kblib.read_text(os.path.join(
            root, *BATCH_REVIEW_OBLIGATION_REGISTRY_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_registry(document)
    return document


def _base_spec(values, *, tier, rule_id, applicability, acceptance,
               evidence_role, evidence_kind, dimension, producer_capability,
               producer_check, consumer_gate_id, due_stage,
               fingerprint_binding, trigger_mappings=None, partition=None,
               item_id=None, source_group=None, consumption_contract=None):
    projection = values["projection"]
    return {
        "tier": tier,
        "item_id": item_id,
        "rule_id": rule_id,
        "source_group": source_group,
        "owner_kind": projection["owner_kind"],
        "owner_rule_id": rule_id,
        "kernel_extension_point": projection["kernel_extension_point"],
        "target_source": projection["target_source"],
        "applicability": applicability,
        "trigger_partition_mappings": tuple(trigger_mappings or ()),
        "partition": partition,
        "due_stage": due_stage,
        "evidence_role": evidence_role,
        "evidence_kind": evidence_kind,
        "dimension": dimension,
        "acceptance_predicate": acceptance["contract_id"],
        "acceptance_contract_text": acceptance["text"],
        "producer_check": producer_check,
        "producer_capability": producer_capability,
        "producer_gate_id": None,
        "consumer_gate_id": consumer_gate_id,
        "fingerprint_binding": fingerprint_binding,
        "review_due": None,
        # Producer/consumer-only metadata.  AuditPlan projection deliberately
        # ignores this field; it resolves an existing `consumes` arrow and is
        # not an additional obligation definition.
        "consumption_contract": deepcopy(consumption_contract),
    }


def base_obligation_specs(registry=None):
    """Return the complete M/S base spec set without inventing IDs/targets."""
    registry = registry or _SHIPPED_REGISTRY
    values = validate_registry(registry)
    projection = values["projection"]
    specs = []
    for item in values["m_items"]:
        specs.append(_base_spec(
            values, tier="M", item_id=item["item_id"],
            rule_id=item["rule_id"], source_group=item["source_group"],
            applicability=item["applicability"],
            acceptance=item["acceptance_contract"],
            evidence_role=item["evidence_role"],
            evidence_kind=item["evidence_kind"],
            dimension=item["dimension"],
            producer_capability=item["producer_capability"],
            producer_check=item["producer_check"],
            consumer_gate_id=item["consumer_gate_id"],
            due_stage=item["due_stage"],
            fingerprint_binding=projection["fingerprint_binding"],
            trigger_mappings=item["trigger_partition_mappings"],
            consumption_contract=values["m_consumption_by_item_id"].get(
                item["item_id"])))
    s = values["s_obligation"]
    specs.append(_base_spec(
        values, tier="S", item_id=None,
        rule_id=values["s_rule_id"], source_group=None,
        applicability=s["applicability"],
        acceptance=s["acceptance_contract"],
        evidence_role=s["evidence_role"], evidence_kind=s["evidence_kind"],
        dimension=None, producer_capability=s["producer_capability"],
        producer_check=s["producer_check"],
        consumer_gate_id=s["consumer_gate_id"], due_stage=s["due_stage"],
        fingerprint_binding=s["fingerprint_binding"],
        partition=s["partition"]))
    return tuple(specs)


def obligation_spec_for_rule(rule_id, registry=None):
    """Resolve exactly one Kernel base spec by its stable rule ID."""
    rule_id = require_trimmed_string(rule_id, "rule_id")
    matches = [row for row in base_obligation_specs(registry)
               if row["rule_id"] == rule_id]
    if len(matches) != 1:
        raise ValueError("unknown or ambiguous batch-review rule %s" % rule_id)
    return matches[0]


def validate_applicability_disposition(spec, disposition, reason,
                                       registry=None):
    """Validate the explicit M-atom applicability disposition.

    The AuditPlan continues to freeze every atom definition.  This is the
    evidence-time disposition of a conditional definition, not a plan status
    and not a Tool interpretation of the underlying judgment predicate.
    """
    values = validate_registry(registry or _SHIPPED_REGISTRY)
    if not isinstance(spec, dict) or spec.get("tier") != "M":
        raise ValueError("applicability disposition requires an M atom")
    if disposition not in values["m_applicability"]["disposition_values"]:
        raise ValueError("M applicability disposition is not registered")
    unconditional = (
        spec.get("applicability") ==
        values["m_applicability"]["unconditional_predicate"])
    if unconditional and disposition != "applicable":
        raise ValueError("an always-applicable M atom cannot be not-applicable")
    if disposition == "applicable":
        if reason is not None:
            raise ValueError("an applicable M atom must have a null reason")
    else:
        require_trimmed_string(reason, "not-applicable reason")
    return {
        "applicability_disposition": disposition,
        "applicability_reason": reason,
    }


def _matches_consumed_obligation(record, plan, plan_sha256, obligation,
                                 selector):
    """Match evidence through its native record contract and plan binding."""
    evidence_kind = obligation["evidence_kind"]
    if evidence_kind == "audit-receipt":
        try:
            audit_receipt_contract.validate_audit_receipt(record)
        except (TypeError, ValueError):
            return False

    expected = {
        "record_kind": evidence_kind,
        "plan_id": plan["plan_id"],
        "audit_plan_sha256": plan_sha256,
        "obligation_id": obligation["obligation_id"],
        "owner_kind": obligation["owner_kind"],
        "owner_rule_id": obligation["owner_rule_id"],
        "kernel_extension_point": obligation["kernel_extension_point"],
        "due_stage": obligation["due_stage"],
        "evidence_role": obligation["evidence_role"],
        "evidence_kind": evidence_kind,
        "acceptance_predicate": obligation["acceptance_predicate"],
        "producer_check": obligation["producer_check"],
        "producer_capability": obligation["producer_capability"],
        "producer_gate_id": obligation["producer_gate_id"],
        "consumer_gate_id": obligation["consumer_gate_id"],
        "fingerprint_binding": obligation["fingerprint_binding"],
        "invalidated_by": None,
    }
    if evidence_kind == "audit-receipt":
        expected["dimension"] = obligation["dimension"]
        scope = record.get("scope")
        target_matches = isinstance(scope, list) and \
            obligation["target"] in scope
    else:
        # Native changed-scope Gate evidence carries the plan partition and a
        # direct target.  Full AuditReceipt deliberately carries neither: its
        # governed target is represented by the closed `scope` field above.
        expected["partition"] = obligation["partition"]
        expected["target"] = obligation["target"]
        expected["dimension"] = None
        target_matches = True
    return (target_matches and
            all(record.get(field) == value
                for field, value in expected.items()) and
            record.get("result") in selector["evidence_result_values"])


def _consumption_dependency_obligations(obligations, spec, target,
                                        registry):
    """Resolve the frozen obligations one M atom consumes.

    This is the single selector interpretation shared by execution ordering,
    evidence production, and final consumption validation.  It returns no
    dependency for emitting atoms or for an explicit contract-gap/HOLD: the
    latter still needs the Agent's applicability judgment before the producer
    can either record ``not-applicable`` or surface the existing HOLD.
    """
    if not isinstance(obligations, (list, tuple)):
        raise ValueError("AuditPlan obligations must be a sequence")
    target = require_trimmed_string(target, "consumption target")
    if spec.get("tier") != "M" or spec.get("evidence_role") != "consumes":
        return ()
    consumption = spec.get("consumption_contract")
    if not isinstance(consumption, dict):
        raise ValueError("consumes-role M item has no consumption contract")
    if consumption.get("resolution") == "hold":
        return ()
    selector = consumption.get("selector")
    if not isinstance(selector, dict):
        raise ValueError("resolved M consumption contract has no selector")

    expected = []
    for obligation in obligations:
        if not isinstance(obligation, dict):
            raise ValueError("AuditPlan obligation must be a mapping")
        if (obligation.get("owner_kind") == selector["owner_kind"] and
                (selector["owner_rule_ids"] is None or
                 obligation.get("owner_rule_id") in
                 selector["owner_rule_ids"]) and
                obligation.get("kernel_extension_point") ==
                selector["kernel_extension_point"] and
                obligation.get("partition") == selector["partition"] and
                obligation.get("due_stage") == selector["due_stage"] and
                obligation.get("target") == target and
                obligation.get("evidence_role") ==
                selector["evidence_role"] and
                obligation.get("status") ==
                selector["obligation_status"] and
                obligation.get("consumer_gate_id") ==
                selector["consumer_gate_id"]):
            expected.append(obligation)
    expected.sort(key=lambda row: row.get("obligation_id") or "")
    if any(not isinstance(row.get("obligation_id"), str) or
           not row["obligation_id"] for row in expected):
        raise ValueError(
            "M consumption selector matched an obligation without identity")
    cardinality = selector["match_cardinality"]
    if cardinality == "exactly-one" and len(expected) != 1:
        raise ValueError(
            "M consumption selector %s requires exactly one AuditPlan "
            "obligation, found %d" %
            (selector["selector_id"], len(expected)))
    if cardinality == "one-or-more-all-matching-required" and not expected:
        raise ValueError(
            "M consumption selector %s matched no required AuditPlan evidence"
            % selector["selector_id"])
    return tuple(expected)


def consumption_dependency_obligation_ids(obligations,
                                          consuming_obligation,
                                          registry=None):
    """Return machine-derived dependencies for one frozen M obligation."""
    registry = registry or _SHIPPED_REGISTRY
    validate_registry(registry)
    if not isinstance(consuming_obligation, dict):
        raise ValueError("consuming obligation must be a mapping")
    if (consuming_obligation.get("evidence_kind") !=
            "batch-page-review-record" or
            consuming_obligation.get("evidence_role") != "consumes"):
        return ()
    spec = obligation_spec_for_rule(
        consuming_obligation.get("owner_rule_id"), registry)
    errors = plan_projection_errors(consuming_obligation, spec)
    if errors:
        raise ValueError(
            "AuditPlan batch-review obligation %s drifts in: %s" %
            (consuming_obligation.get("obligation_id"),
             ", ".join(errors)))
    return tuple(
        row["obligation_id"] for row in
        _consumption_dependency_obligations(
            obligations, spec, consuming_obligation.get("target"), registry))


def resolve_consumed_evidence(plan, plan_sha256, spec, target, catalog,
                              referenced_receipt_ids, disposition,
                              registry=None, *, current_receipt_ids=None):
    """Resolve exactly the canonical evidence for one M `consumes` atom.

    The selector comes only from the Kernel registry.  The function accepts a
    stable catalog view plus an explicit live-current identity set and returns
    the exact sorted evidence rows; callers cannot substitute an unrelated or
    stale passing receipt.  ``current_receipt_ids=None`` is retained only for
    pure construction tests whose synthetic catalog contains no history.
    Production producers and consumers must pass the IDs resolved by the
    runtime AuditPlan currentness owner.  An unresolved selector is an
    explicit HOLD, not a permissive fallback.
    """
    registry = registry or _SHIPPED_REGISTRY
    validate_registry(registry)
    audit_plan_contract.validate_plan(plan)
    if audit_plan_contract.plan_sha256(plan) != plan_sha256:
        raise ValueError("consumed evidence binds a different AuditPlan")
    target = require_trimmed_string(target, "consumption target")
    if not isinstance(catalog, dict):
        raise ValueError("current evidence catalog must be a mapping")
    if current_receipt_ids is None:
        current_ids = None
    else:
        if (not isinstance(current_receipt_ids,
                           (set, frozenset, list, tuple)) or
                isinstance(current_receipt_ids, (str, bytes))):
            raise ValueError("current receipt IDs must be a collection")
        current_values = list(current_receipt_ids)
        if any(not isinstance(value, str) or not value or
               value.strip() != value for value in current_values):
            raise ValueError(
                "current receipt IDs must be non-empty unique strings")
        if len(current_values) != len(set(current_values)):
            raise ValueError(
                "current receipt IDs must be non-empty unique strings")
        current_ids = frozenset(current_values)
    refs = _string_list(
        list(referenced_receipt_ids or ()), "consumed evidence references",
        allow_empty=True, sorted_unique=True)
    if spec.get("tier") != "M":
        if refs:
            raise ValueError("sampled S evidence cannot consume evidence")
        return ()
    disposition_values = validate_applicability_disposition(
        spec, disposition,
        None if disposition == "applicable" else "selector-validation",
        registry)
    if disposition_values["applicability_disposition"] == "not-applicable":
        if refs:
            raise ValueError(
                "a not-applicable M atom cannot consume evidence")
        return ()
    if spec.get("evidence_role") == "emits":
        if refs:
            raise ValueError("an emitting M item cannot consume evidence")
        return ()
    if spec.get("evidence_role") != "consumes":
        raise ValueError("M item has no admitted consumption role")
    consumption = spec.get("consumption_contract")
    if not isinstance(consumption, dict):
        raise ValueError("consumes-role M item has no consumption contract")
    if consumption.get("resolution") == "hold":
        raise ValueError(
            "M consumption selector is HOLD for %s: %s" %
            (spec.get("item_id"), consumption.get("hold_reason")))
    selector = consumption.get("selector")
    if not isinstance(selector, dict):
        raise ValueError("resolved M consumption contract has no selector")
    expected_obligations = _consumption_dependency_obligations(
        plan.get("obligations") or (), spec, target, registry)

    records_by_obligation = {
        obligation["obligation_id"]: []
        for obligation in expected_obligations
    }
    for catalog_id, entry in catalog.items():
        record = catalog_record(entry)
        if not isinstance(record, dict) or record.get("receipt_id") != \
                catalog_id:
            continue
        obligation_id = record.get("obligation_id")
        if obligation_id not in records_by_obligation:
            continue
        obligation = next(
            row for row in expected_obligations
            if row["obligation_id"] == obligation_id)
        if _matches_consumed_obligation(
                record, plan, plan_sha256, obligation, selector):
            records_by_obligation[obligation_id].append(record)

    resolved = []
    for obligation in expected_obligations:
        matches = records_by_obligation[obligation["obligation_id"]]
        def validate_current(record):
            if (current_ids is not None and
                    record["receipt_id"] not in current_ids):
                raise ValueError("receipt does not observe current inputs")

        try:
            selected = evidence_attempt_runtime.unique_current_attempt(
                matches,
                validate_stable=lambda record: record,
                validate_current=validate_current,
                label="M consumption selector %s obligation %s" % (
                    selector["selector_id"], obligation["obligation_id"]))
        except evidence_attempt_runtime.EvidenceAttemptError as exc:
            raise ValueError(
                "M consumption selector %s requires exactly one current "
                "passing record for obligation %s: %s" % (
                    selector["selector_id"], obligation["obligation_id"],
                    exc)) from exc
        if selected is None:
            raise ValueError(
                "M consumption selector %s requires exactly one current "
                "passing record for obligation %s, found %d" %
                (selector["selector_id"], obligation["obligation_id"],
                 0))
        resolved.append(selected)
    resolved.sort(key=lambda row: row["receipt_id"])
    expected_refs = tuple(row["receipt_id"] for row in resolved)
    if refs != expected_refs:
        raise ValueError(
            "consumed evidence references differ from selector %s: "
            "expected=%s actual=%s" %
            (selector["selector_id"], list(expected_refs), list(refs)))
    return tuple(resolved)


def validate_receipt_consumption(plan, plan_sha256, record, catalog,
                                 registry=None, *, current_receipt_ids=None):
    """Consumer-safe strict revalidation for one persisted M record."""
    registry = registry or _SHIPPED_REGISTRY
    validate_producer_receipt(record, registry)
    if record.get("review_variant") != "m-atomic-item":
        if record.get("consumed_evidence_refs"):
            raise ValueError("sampled S evidence cannot consume evidence")
        return ()
    spec = obligation_spec_for_rule(record["rule_id"], registry)
    return resolve_consumed_evidence(
        plan, plan_sha256, spec, record["target"], catalog,
        record["consumed_evidence_refs"],
        record["applicability_disposition"], registry,
        current_receipt_ids=current_receipt_ids)


def plan_projection_errors(obligation, spec):
    """Return AuditPlan fields that differ from one review obligation spec."""
    expected = {
        "owner_kind": spec["owner_kind"],
        "owner_rule_id": spec["owner_rule_id"],
        "kernel_extension_point": spec["kernel_extension_point"],
        "applicability": spec["applicability"],
        "due_stage": spec["due_stage"],
        "evidence_role": spec["evidence_role"],
        "evidence_kind": spec["evidence_kind"],
        "dimension": spec["dimension"],
        "acceptance_predicate": spec["acceptance_predicate"],
        "producer_check": spec["producer_check"],
        "producer_capability": spec["producer_capability"],
        "producer_gate_id": spec["producer_gate_id"],
        "consumer_gate_id": spec["consumer_gate_id"],
        "fingerprint_binding": spec["fingerprint_binding"],
        "review_due": spec["review_due"],
    }
    errors = [field for field, value in expected.items()
              if obligation.get(field) != value]
    if spec["tier"] == "M":
        allowed = {row["partition"]
                   for row in spec["trigger_partition_mappings"]}
        if obligation.get("partition") not in allowed:
            errors.append("partition")
    elif obligation.get("partition") != spec["partition"]:
        errors.append("partition")
    return sorted(set(errors))


def validate_plan_base_closure(plan, manifest, tiers, registry=None):
    """Prove the plan has every and only applicable K12/14 base target.

    All registered M atoms are definitions frozen for every M manifest page;
    their conditional applicability is discharged explicitly by the review
    details, never by omitting a plan row.  Concrete S targets are the
    deterministic Tool sample.
    """
    registry = registry or _SHIPPED_REGISTRY
    audit_plan_contract.validate_plan(plan)
    if (not isinstance(manifest, list) or manifest != sorted(manifest) or
            len(manifest) != len(set(manifest)) or
            any(not isinstance(path, str) or not path for path in manifest)):
        raise ValueError("batch manifest must be sorted and unique")
    if not isinstance(tiers, dict):
        raise ValueError("coverage tiers must be a path mapping")
    missing_tiers = [path for path in manifest if tiers.get(path) not in {
        "L", "M", "S"}]
    if missing_tiers:
        raise ValueError("manifest pages lack a registered tier: %s" %
                         ", ".join(missing_tiers))

    specs = base_obligation_specs(registry)
    by_rule = {spec["rule_id"]: spec for spec in specs}
    m_specs = tuple(spec for spec in specs if spec["tier"] == "M")
    s_spec = next(spec for spec in specs if spec["tier"] == "S")
    m_pages = sorted(path for path in manifest if tiers[path] == "M")
    s_population = sorted(path for path in manifest if tiers[path] == "S")
    selection = select_s_targets(
        s_population, task_id=plan["task_id"], batch_id=plan["batch_id"],
        opening_transition_receipt=plan["opening_transition_receipt"],
        registry=registry)
    expected = {
        (page, spec["rule_id"])
        for page in m_pages for spec in m_specs
    }
    expected.update(
        (page, s_spec["rule_id"])
        for page in selection["sample_selected_targets"])

    actual = {}
    for obligation in plan["obligations"]:
        rule_id = obligation.get("owner_rule_id")
        spec = by_rule.get(rule_id)
        if spec is None:
            continue
        pair = (obligation.get("target"), rule_id)
        if pair in actual:
            raise ValueError(
                "AuditPlan repeats batch-review target/rule %s/%s" % pair)
        errors = plan_projection_errors(obligation, spec)
        if errors:
            raise ValueError(
                "AuditPlan batch-review obligation %s drifts in: %s" %
                (obligation.get("obligation_id"), ", ".join(errors)))
        if obligation.get("target") not in manifest:
            raise ValueError("batch-review obligation target is outside manifest")
        if tiers[obligation["target"]] != spec["tier"]:
            raise ValueError("batch-review obligation targets the wrong tier")
        actual[pair] = obligation
    if set(actual) != expected:
        missing = sorted(expected - set(actual))
        extra = sorted(set(actual) - expected)
        raise ValueError(
            "AuditPlan batch-review base closure differs: missing=%s extra=%s"
            % (missing, extra))
    return {
        "obligations_by_target_rule": actual,
        "s_selection": selection,
    }


def s_sample_count(population_count, registry=None):
    """Compute the registered ceiling count from structured parameters."""
    if (not isinstance(population_count, int) or
            isinstance(population_count, bool) or population_count < 0):
        raise ValueError("S population count must be a non-negative integer")
    values = validate_registry(registry or _SHIPPED_REGISTRY)
    count = values["s_count"]
    minimum = count["minimum_count"]
    if population_count < minimum:
        return population_count
    numerator = count["percentage_numerator"]
    denominator = count["percentage_denominator"]
    percentage = (
        population_count * numerator + denominator - 1) // denominator
    return max(minimum, percentage)


def _set_sha256(values):
    return kblib.sha256_bytes(kblib.canonical_json_bytes(list(values)))


def select_s_targets(population, *, task_id, batch_id,
                     opening_transition_receipt, registry=None):
    """Deterministically select and freeze Tool-owned S review targets."""
    registry = registry or _SHIPPED_REGISTRY
    values = validate_registry(registry)
    task_id = require_trimmed_string(task_id, "task_id")
    batch_id = require_trimmed_string(batch_id, "batch_id")
    opening_transition_receipt = require_trimmed_string(
        opening_transition_receipt, "opening_transition_receipt")
    if not isinstance(population, (list, tuple, set, frozenset)):
        raise ValueError("S population must be a finite path collection")
    raw_population = list(population)
    if (any(not isinstance(path, str) or not path or path.strip() != path
            for path in raw_population) or
            len(raw_population) != len(set(raw_population))):
        raise ValueError("S population paths must be unique non-empty strings")
    normalized = sorted(raw_population)
    population_sha256 = _set_sha256(normalized)
    required = s_sample_count(len(normalized), registry)
    ranked = []
    for path in normalized:
        rank = kblib.sha256_bytes(kblib.canonical_json_bytes({
            "algorithm_id": S_SELECTION_ALGORITHM_ID,
            "rule_id": values["s_rule_id"],
            "task_id": task_id,
            "batch_id": batch_id,
            "opening_transition_receipt": opening_transition_receipt,
            "population_sha256": population_sha256,
            "target": path,
        }))
        ranked.append((rank, path))
    selected = sorted(path for _rank, path in sorted(ranked)[:required])
    selected_sha256 = _set_sha256(selected)
    selection_material = {
        "algorithm_id": S_SELECTION_ALGORITHM_ID,
        "rule_id": values["s_rule_id"],
        "task_id": task_id,
        "batch_id": batch_id,
        "opening_transition_receipt": opening_transition_receipt,
        "population_targets": normalized,
        "population_sha256": population_sha256,
        "required_count": required,
        "selected_targets": selected,
        "selected_set_sha256": selected_sha256,
    }
    return {
        "sample_rule_id": values["s_rule_id"],
        "sample_population_count": len(normalized),
        "sample_population_targets": normalized,
        "sample_population_sha256": population_sha256,
        "sample_required_count": required,
        "sample_selected_targets": selected,
        "sample_selected_set_sha256": selected_sha256,
        "selection_algorithm_id": S_SELECTION_ALGORITHM_ID,
        "selection_fingerprint": kblib.sha256_bytes(
            kblib.canonical_json_bytes(selection_material)),
    }


def registry_sha256(registry=None):
    registry = registry or _SHIPPED_REGISTRY
    validate_registry(registry)
    return kblib.sha256_bytes(kblib.canonical_json_bytes(registry))


def contract_fingerprint(spec, bindings, registry=None):
    """Bind the current atomic contract and governed Profile identities."""
    registry = registry or _SHIPPED_REGISTRY
    material = {
        "registry_sha256": registry_sha256(registry),
        "rule_id": spec["rule_id"],
        "owner_kind": spec["owner_kind"],
        "target_source": spec["target_source"],
        "applicability": spec["applicability"],
        "due_stage": spec["due_stage"],
        "evidence_role": spec["evidence_role"],
        "evidence_kind": spec["evidence_kind"],
        "dimension": spec["dimension"],
        "acceptance_predicate": spec["acceptance_predicate"],
        "acceptance_contract_text": spec["acceptance_contract_text"],
        "producer_check": spec["producer_check"],
        "producer_capability": spec["producer_capability"],
        "consumer_gate_id": spec["consumer_gate_id"],
        "fingerprint_binding": spec["fingerprint_binding"],
        "consumption_contract": spec.get("consumption_contract"),
        "upstream_revision_id": bindings.get("upstream_revision_id"),
        "active_standards_sha256": bindings.get("active_standards_sha256"),
        "selected_profile_manifest": bindings.get(
            "selected_profile_manifest"),
        "profile_snapshot_sha256": bindings.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint": bindings.get(
            "profile_contract_fingerprint"),
    }
    for field, value in material.items():
        if field not in {"dimension", "consumption_contract"} and value is None:
            raise ValueError("contract fingerprint lacks %s" % field)
    return kblib.sha256_bytes(kblib.canonical_json_bytes(material))


def dependency_fingerprint(sources_sha256, consumed_records=(),
                           selection_fingerprint=None):
    """Bind current Sources, consumed evidence bytes, and S selection."""
    if not isinstance(sources_sha256, str) or \
            _SHA256_RE.fullmatch(sources_sha256) is None:
        raise ValueError("sources_sha256 must be a canonical sha256")
    if not isinstance(consumed_records, (list, tuple)):
        raise ValueError("consumed_records must be a list or tuple")
    rows = []
    for index, record in enumerate(consumed_records):
        if not isinstance(record, dict):
            raise ValueError("consumed record %d is not an object" % index)
        receipt_id = require_trimmed_string(
            record.get("receipt_id"), "consumed record receipt_id")
        rows.append({
            "receipt_id": receipt_id,
            "record_sha256": kblib.sha256_bytes(
                kblib.canonical_json_bytes(record)),
        })
    rows.sort(key=lambda row: row["receipt_id"])
    if len({row["receipt_id"] for row in rows}) != len(rows):
        raise ValueError("consumed_records repeat receipt_id")
    if selection_fingerprint is not None and (
            not isinstance(selection_fingerprint, str) or
            _SHA256_RE.fullmatch(selection_fingerprint) is None):
        raise ValueError("selection_fingerprint must be sha256 or null")
    return kblib.sha256_bytes(kblib.canonical_json_bytes({
        "sources_sha256": sources_sha256,
        "consumed_records": rows,
        "selection_fingerprint": selection_fingerprint,
    }))


def validate_page_fingerprint_binding(record, relative_path, text,
                                      semantic_content_fingerprint):
    """Validate distinct K12/07 artifact and semantic page bindings.

    This helper is consumer-safe: a caller with the current target bytes can
    re-run the same projection without importing the producer CLI.
    """
    expected_artifact = audit_fingerprint.page_artifact_fingerprint(
        relative_path, text)
    if record.get("artifact_fingerprint") != expected_artifact:
        raise ValueError(
            "batch-page artifact fingerprint is not the current K12/07 page projection")
    if record.get("semantic_content_fingerprint") != \
            semantic_content_fingerprint:
        raise ValueError(
            "batch-page semantic content fingerprint is not current")
    return record


def _validate_producer_value(value, type_id, label):
    if type_id == "nullable-string":
        if value is not None:
            require_trimmed_string(value, label)
        return
    if type_id == "string":
        require_trimmed_string(value, label)
    elif type_id == "integer":
        if (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ValueError("%s must be a non-negative integer" % label)
    elif type_id == "sha256":
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise ValueError("%s must be sha256:<64 lowercase hex>" % label)
    elif type_id == "utc-timestamp":
        if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
            raise ValueError("%s must be a UTC timestamp ending in Z" % label)
    elif type_id == "string-list":
        _string_list(value, label, allow_empty=True, sorted_unique=True)
    else:
        raise ValueError("%s has unsupported producer type %s" %
                         (label, type_id))


def _timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc)


def validate_producer_receipt(record, registry=None):
    """Validate one closed M-atomic or sampled-S producer record."""
    registry = registry or _SHIPPED_REGISTRY
    values = validate_registry(registry)
    producer = values["producer"]
    if not isinstance(record, dict):
        raise ValueError("batch-page review record must be an object")
    variant_id = record.get("review_variant")
    variant = producer["variants"].get(variant_id)
    if variant is None:
        raise ValueError("batch-page review variant is not registered")
    if set(record) != set(variant["instance_fields"]):
        raise ValueError("batch-page review record fields are not closed")
    for field in producer["field_order"]:
        if field in record:
            _validate_producer_value(
                record.get(field), producer["fields"][field],
                "batch-page-review.%s" % field)
    if record.get("schema_version") != registry["schema_version"]:
        raise ValueError(
            "batch-page review schema_version must equal its Kernel registry")
    if record.get("record_kind") != "batch-page-review-record":
        raise ValueError("batch-page review record_kind is invalid")
    if record.get("receipt_type_id") != RECEIPT_TYPE_ID:
        raise ValueError("batch-page review receipt_type_id is invalid")
    if record.get("tool") != PRODUCER_TOOL:
        raise ValueError("batch-page review tool identity is invalid")
    if record.get("tool_version") != PRODUCER_TOOL_VERSION:
        raise ValueError("batch-page review tool version is invalid")
    if record.get("tier") != variant["tier"]:
        raise ValueError("batch-page review tier disagrees with variant")
    verdict = record.get("verdict")
    if verdict not in producer["verdict_results"]:
        raise ValueError("batch-page review verdict is invalid")
    if record.get("result") != producer["verdict_results"][verdict]:
        raise ValueError("batch-page review result disagrees with verdict")
    if record.get("invalidated_by") is not None:
        raise ValueError("new batch-page review evidence must be current")
    if variant_id == "m-atomic-item":
        item = values["m_items_by_id"].get(record.get("item_id"))
        if item is None:
            raise ValueError("M batch-page record names an unknown item")
        spec = obligation_spec_for_rule(item["rule_id"], registry)
        expected = {
            "tier": "M",
            "rule_id": item["rule_id"],
            "source_group": item["source_group"],
            "check": spec["producer_check"],
            "partition": record.get("partition"),
            "due_stage": spec["due_stage"],
            "evidence_role": spec["evidence_role"],
            "evidence_kind": spec["evidence_kind"],
            "dimension": spec["dimension"],
            "acceptance_predicate": spec["acceptance_predicate"],
            "producer_capability": spec["producer_capability"],
            "consumer_gate_id": spec["consumer_gate_id"],
            "fingerprint_binding": spec["fingerprint_binding"],
        }
        allowed_partitions = {
            row["partition"] for row in spec["trigger_partition_mappings"]}
        if record.get("partition") not in allowed_partitions:
            raise ValueError("M batch-page record partition is not registered")
        mismatches = [field for field, expected_value in expected.items()
                      if record.get(field) != expected_value]
        if mismatches:
            raise ValueError("M batch-page record drifts in: %s" %
                             ", ".join(sorted(mismatches)))
        disposition = validate_applicability_disposition(
            spec, record.get("applicability_disposition"),
            record.get("applicability_reason"), registry)
        refs = record.get("consumed_evidence_refs")
        if disposition["applicability_disposition"] == "not-applicable":
            if refs:
                raise ValueError(
                    "a not-applicable M item cannot consume evidence refs")
        elif spec["evidence_role"] == "emits" and refs:
            raise ValueError("an emitting M item cannot consume evidence refs")
        elif spec["evidence_role"] == "consumes":
            consumption = spec.get("consumption_contract") or {}
            if consumption.get("resolution") == "hold":
                raise ValueError(
                    "M consumption selector is HOLD for %s: %s" %
                    (spec.get("item_id"),
                     consumption.get("hold_reason")))
            if not refs:
                raise ValueError(
                    "an applicable consuming M item requires evidence refs")
    else:
        spec = obligation_spec_for_rule(values["s_rule_id"], registry)
        expected = {
            "tier": "S",
            "sample_rule_id": values["s_rule_id"],
            "check": spec["producer_check"],
            "partition": spec["partition"],
            "due_stage": spec["due_stage"],
            "evidence_role": spec["evidence_role"],
            "evidence_kind": spec["evidence_kind"],
            "dimension": None,
            "acceptance_predicate": spec["acceptance_predicate"],
            "producer_capability": spec["producer_capability"],
            "consumer_gate_id": spec["consumer_gate_id"],
            "fingerprint_binding": spec["fingerprint_binding"],
        }
        mismatches = [field for field, expected_value in expected.items()
                      if record.get(field) != expected_value]
        if mismatches:
            raise ValueError("S batch-page record drifts in: %s" %
                             ", ".join(sorted(mismatches)))
        if record.get("consumed_evidence_refs"):
            raise ValueError("sampled S evidence cannot consume evidence refs")
        selection = select_s_targets(
            record["sample_population_targets"],
            task_id=record["task_id"], batch_id=record["batch_id"],
            opening_transition_receipt=record["opening_transition_receipt"],
            registry=registry)
        selection_mismatches = [
            field for field, expected_value in selection.items()
            if record.get(field) != expected_value]
        if selection_mismatches:
            raise ValueError("S selection binding drifts in: %s" %
                             ", ".join(sorted(selection_mismatches)))
        if record["target"] not in record["sample_selected_targets"]:
            raise ValueError("S review target is outside the frozen sample")
        if _timestamp(record["selection_frozen_at"]) > _timestamp(
                record["checked_at"]):
            raise ValueError("S selection must freeze before review evidence")

    expected_contract_fingerprint = contract_fingerprint(
        spec, record, registry)
    if record.get("contract_fingerprint") != expected_contract_fingerprint:
        raise ValueError("batch-page contract fingerprint is not current")
    return record


def current_receipt_errors(record, *, root=None):
    """Return current hard-cut batch-page review record errors."""
    try:
        validate_producer_receipt(
            record, registry=load_registry(root) if root is not None else None)
    except (OSError, TypeError, UnicodeError, ValueError,
            kblib.YamlSubsetError) as exc:
        return [str(exc)]
    return []


_SHIPPED_REGISTRY = load_registry()
_SHIPPED_VALUES = validate_registry(_SHIPPED_REGISTRY)
BATCH_PAGE_REVIEW_RECORD_FIELDS = _SHIPPED_VALUES["producer"]["field_order"]
M_ATOMIC_ITEM_IDS = tuple(
    item["item_id"] for item in _SHIPPED_VALUES["m_items"])
M_ATOMIC_RULE_IDS = tuple(
    item["rule_id"] for item in _SHIPPED_VALUES["m_items"])
S_SAMPLING_RULE_ID = _SHIPPED_VALUES["s_rule_id"]


__all__ = [
    'BATCH_REVIEW_OBLIGATION_REGISTRY_PATH',
    'PRODUCER_TOOL',
    'PRODUCER_TOOL_VERSION',
    'RECEIPT_TYPE_ID',
    'base_obligation_specs',
    'consumption_dependency_obligation_ids',
    'contract_fingerprint',
    'dependency_fingerprint',
    'load_registry',
    'obligation_spec_for_rule',
    'registry_sha256',
    'select_s_targets',
    'validate_plan_base_closure',
    'resolve_consumed_evidence',
    'validate_applicability_disposition',
    'current_receipt_errors',
    'validate_page_fingerprint_binding',
    'validate_producer_receipt',
    'validate_receipt_consumption',
]
