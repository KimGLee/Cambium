"""Admit immutable Profile rendering bindings without executing a renderer.

The Kernel shape owns answer fields and registration constraints. The Tool
registry solely owns concrete capability/construct/acceptance tuples.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Tuple

import Tools.platform.common.kblib as kblib
from Tools.platform.repository.path_contract import canonical_repository_relative_path


CONTRACT_PATH = "kernel/K12 Quality Assurance/profile-rendering-contract.yaml"
CONTRACT_ID = "cambium-profile-rendering-contract"
CAPABILITY_REGISTRY_PATH = "Tools/rendering-capabilities.yaml"


@dataclass(frozen=True)
class RenderingRule:
    rule_id: str
    construct: str
    capability_id: str
    acceptance: str


@dataclass(frozen=True)
class RenderingContract:
    registration: str
    rules: Tuple[RenderingRule, ...]
    source_path: str
    fingerprint: str

    def binding_for_construct(self, construct_id):
        return next((rule for rule in self.rules
                     if rule.construct == construct_id), None)

    def semantic_projection(self):
        return {
            "registration": self.registration,
            "source_path": self.source_path,
            "rules": [{
                "rule_id": rule.rule_id, "construct": rule.construct,
                "capability_id": rule.capability_id,
                "acceptance": rule.acceptance,
            } for rule in self.rules],
        }


def _read(root, path, snapshots=None):
    snapshot = (snapshots or {}).get(path)
    return snapshot.read_text() if snapshot is not None else kblib.read_text(
        Path(root).joinpath(*path.split("/")))


def load_rendering_shape(root, *, text=None, snapshots=None):
    document = kblib.parse_yaml_subset(
        _read(root, CONTRACT_PATH, snapshots) if text is None else text)
    if not isinstance(document, dict) or set(document) != {
            "schema_version", "contract_id", "semantic_owner",
            "extension_point_id", "profile_shape"}:
        raise ValueError("Profile rendering shape owner fields are not closed")
    if (type(document["schema_version"]) is not int or
            document["schema_version"] != 1 or
            document["contract_id"] != CONTRACT_ID or
            document["semantic_owner"] != "K12/02" or
            document["extension_point_id"] != "k12-02-profile-rendering"):
        raise ValueError("Profile rendering shape owner identity is invalid")
    shape = document["profile_shape"]
    if not isinstance(shape, dict) or set(shape) != {
            "schema_version", "fields", "registration_values",
            "inactive_registration", "configured_registration",
            "rule_fields", "identifier_pattern", "unique_rule_fields"}:
        raise ValueError("Profile rendering shape definition fields are not closed")
    for field in ("fields", "registration_values", "rule_fields",
                  "unique_rule_fields"):
        values = shape[field]
        if (not isinstance(values, list) or not values or
                any(not isinstance(value, str) or not value for value in values)
                or len(values) != len(set(values))):
            raise ValueError("Profile rendering shape %s is invalid" % field)
    if (type(shape["schema_version"]) is not int or
            not set(shape["unique_rule_fields"]).issubset(shape["rule_fields"])
            or not isinstance(shape["inactive_registration"], str)
            or not isinstance(shape["configured_registration"], str)
            or shape["inactive_registration"] == shape["configured_registration"]
            or set(shape["registration_values"]) != {
                shape["inactive_registration"], shape["configured_registration"]}):
        raise ValueError("Profile rendering shape constraints are invalid")
    try:
        re.compile(shape["identifier_pattern"])
    except (TypeError, re.error) as exc:
        raise ValueError("Profile rendering identifier pattern is invalid") from exc
    return document


def validate_rendering_shape(document, *, contract):
    """Validate answer fields only through their Kernel-owned definitions."""
    shape = contract["profile_shape"]
    if not isinstance(document, dict) or set(document) != set(shape["fields"]):
        return ("Profile rendering fields are not closed",)
    issues = []
    if (type(document.get("schema_version")) is not int or
            document["schema_version"] != shape["schema_version"]):
        issues.append("Profile rendering schema_version is invalid")
    registration = document.get("registration")
    if registration not in shape["registration_values"]:
        issues.append("Profile rendering registration is invalid")
    rules = document.get("rules")
    if not isinstance(rules, list):
        return tuple(issues + ["Profile rendering rules must be a list"])
    if registration == shape["inactive_registration"] and rules:
        issues.append("inactive Profile rendering must have no rules")
    if registration == shape["configured_registration"] and not rules:
        issues.append("configured Profile rendering requires at least one rule")
    seen = {field: set() for field in shape["unique_rule_fields"]}
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or set(rule) != set(shape["rule_fields"]):
            issues.append("rendering rule %d fields are not closed" % index)
            continue
        for field, value in rule.items():
            if (not isinstance(value, str) or
                    re.fullmatch(shape["identifier_pattern"], value) is None):
                issues.append("rendering rule %d has invalid %s" % (index, field))
                continue
            if field in seen:
                if value in seen[field]:
                    issues.append("rendering rule repeats %s %s" % (field, value))
                seen[field].add(value)
    return tuple(issues)


def rendering_capability_records(document):
    """Validate the sole Tool registry; no independent supported-tuple list."""
    if (not isinstance(document, dict) or
            set(document) != {"schema_version", "capabilities"} or
            type(document.get("schema_version")) is not int or
            document["schema_version"] != 1):
        raise ValueError("rendering capability registry shape is invalid")
    rows = document["capabilities"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("rendering capabilities must be a non-empty list")
    records = {}
    pattern = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
                "capability_id", "implementation_path", "selector_id",
                "acceptance_bindings"}:
            raise ValueError("rendering capability fields are not closed")
        for field in ("capability_id", "selector_id"):
            if (not isinstance(row[field], str) or
                    re.fullmatch(pattern, row[field]) is None):
                raise ValueError("rendering capability %s is invalid" % field)
        capability_id = row["capability_id"]
        if capability_id in records:
            raise ValueError("duplicate rendering capability %s" % capability_id)
        path = canonical_repository_relative_path(
            row["implementation_path"], "rendering capability implementation")
        if not path.startswith("Tools/") or not path.endswith(".py"):
            raise ValueError("rendering capability implementation must name a Tool")
        bindings = row["acceptance_bindings"]
        if not isinstance(bindings, list) or not bindings:
            raise ValueError("rendering acceptance bindings must be non-empty")
        seen = set()
        for binding in bindings:
            if not isinstance(binding, dict) or set(binding) != {
                    "construct", "acceptance"}:
                raise ValueError("rendering acceptance binding fields are not closed")
            if any(not isinstance(value, str) or
                   re.fullmatch(pattern, value) is None
                   for value in binding.values()):
                raise ValueError("rendering acceptance binding identifier is invalid")
            key = (binding["construct"], binding["acceptance"])
            if key in seen:
                raise ValueError("rendering acceptance binding is duplicated")
            seen.add(key)
        records[capability_id] = row
    return records


def capability_implementation_paths(document):
    return tuple(sorted({row["implementation_path"]
                         for row in rendering_capability_records(document).values()}))


def load_rendering_capabilities(root, *, snapshots=None):
    return rendering_capability_records(kblib.parse_yaml_subset(
        _read(root, CAPABILITY_REGISTRY_PATH, snapshots)))


def parse_rendering_contract(text, source_path, *, root, snapshots=None):
    owner = load_rendering_shape(root, snapshots=snapshots)
    document = kblib.parse_yaml_subset(text)
    issues = validate_rendering_shape(document, contract=owner)
    if issues:
        raise ValueError("; ".join(issues))
    capabilities = load_rendering_capabilities(root, snapshots=snapshots)
    rules = []
    for row in document["rules"]:
        capability = capabilities.get(row["capability_id"])
        if capability is None or not any(
                binding["construct"] == row["construct"] and
                binding["acceptance"] == row["acceptance"]
                for binding in capability["acceptance_bindings"]):
            raise ValueError("rendering rule %s has no registered capability/"
                             "construct/acceptance binding" % row["rule_id"])
        rules.append(RenderingRule(**row))
    return RenderingContract(
        registration=document["registration"], rules=tuple(rules),
        source_path=source_path, fingerprint=kblib.sha256_bytes(text))
