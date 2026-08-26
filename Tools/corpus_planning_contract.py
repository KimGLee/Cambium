"""Strict projection of the Kernel-owned Corpus Planning machine contract.

``kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml``
owns the Profile-slot envelope, applicability branches, artifact-role map,
receipt freshness binding, and close-trigger identities already defined by
K02/03 and K02/04.  This runtime-independent module only validates that
registry, projects its closed values, and implements the shared mechanical
branch/binding algorithms.  It does not inspect planning artifacts, select a
Profile or route, decide semantic acceptance, or write state.
"""

import os
import re

import kblib


CORPUS_PLANNING_CONTRACT_PATH = (
    "kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml")

_DOCUMENT_FIELDS = {
    "schema_version", "contract_id", "semantic_owner", "slot_envelope",
    "receipt_binding", "close_triggers",
}
_SLOT_ENVELOPE_FIELDS = {
    "slot_name", "schema_version", "fields", "applicability_fields",
    "artifact_binding_fields", "capability_scale_fields",
    "pass_authority_fields", "applicability_branches", "artifact_roles",
    "semantic_acceptance_scope",
}
_SLOT_FIELDS = {
    "schema_version", "applicability", "artifact_bindings",
    "capability_scale", "pass_authority",
}
_APPLICABILITY_FIELDS = {"state", "reason"}
_CAPABILITY_SCALE_FIELDS = {
    "rank", "value", "predicate", "target_eligible",
}
_PASS_AUTHORITY_FIELDS = {"role_id", "decision_scope_id"}
_APPLICABILITY_BRANCH_ROLES = {"configured", "inactive"}
_RECEIPT_BINDING_FIELDS = {"fields", "path_sha_bindings"}
_PATH_SHA_BINDING_FIELDS = {
    "path_field", "sha256_field", "requirement",
}
_PATH_SHA_REQUIREMENTS = {"always", "configured"}
_CLOSE_TRIGGER_ROLES = {"selected_route", "affected_manifest"}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _closed_mapping(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        missing = sorted(set(fields) - set(value or {})) \
            if isinstance(value, dict) else sorted(fields)
        extra = sorted(set(value) - set(fields)) \
            if isinstance(value, dict) else []
        raise ValueError(
            "%s fields are not closed: missing=%s extra=%s" %
            (label, missing, extra))
    return value


def _unique_string_list(value, label, *, allow_empty=False):
    if (not isinstance(value, list) or
            (not allow_empty and not value) or
            any(not isinstance(item, str) or not item or
                item.strip() != item for item in value)):
        qualifier = "a string list" if allow_empty else \
            "a non-empty string list"
        raise ValueError("%s must be %s" % (label, qualifier))
    if len(value) != len(set(value)):
        raise ValueError("%s must not contain duplicate values" % label)
    return tuple(value)


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def validate_corpus_planning_contract(document):
    """Strictly validate one registry and return its mechanical projection."""
    _closed_mapping(document, _DOCUMENT_FIELDS,
                    "Corpus Planning contract")
    if document.get("schema_version") != 1:
        raise ValueError("Corpus Planning contract schema_version must be 1")
    if document.get("contract_id") != "cambium-corpus-planning-contract":
        raise ValueError(
            "Corpus Planning contract_id must be "
            "cambium-corpus-planning-contract")
    if document.get("semantic_owner") != "K02/03+K02/04":
        raise ValueError(
            "Corpus Planning semantic_owner must be K02/03+K02/04")

    slot = _closed_mapping(
        document.get("slot_envelope"), _SLOT_ENVELOPE_FIELDS,
        "Corpus Planning slot_envelope")
    if not _nonempty_string(slot.get("slot_name")):
        raise ValueError("Corpus Planning slot_name must be non-empty")
    if slot.get("schema_version") != 1:
        raise ValueError(
            "Corpus Planning slot schema_version must be integer 1")
    slot_fields = _unique_string_list(
        slot.get("fields"), "Corpus Planning slot fields")
    if set(slot_fields) != _SLOT_FIELDS:
        raise ValueError(
            "Corpus Planning slot fields must describe the closed envelope")
    applicability_fields = _unique_string_list(
        slot.get("applicability_fields"),
        "Corpus Planning applicability fields")
    if set(applicability_fields) != _APPLICABILITY_FIELDS:
        raise ValueError(
            "Corpus Planning applicability fields must describe state/reason")
    artifact_fields = _unique_string_list(
        slot.get("artifact_binding_fields"),
        "Corpus Planning artifact binding fields")
    scale_fields = _unique_string_list(
        slot.get("capability_scale_fields"),
        "Corpus Planning capability scale fields")
    if set(scale_fields) != _CAPABILITY_SCALE_FIELDS:
        raise ValueError(
            "Corpus Planning capability scale fields are incomplete")
    authority_fields = _unique_string_list(
        slot.get("pass_authority_fields"),
        "Corpus Planning pass authority fields")
    if set(authority_fields) != _PASS_AUTHORITY_FIELDS:
        raise ValueError(
            "Corpus Planning pass authority fields are incomplete")

    branches = _closed_mapping(
        slot.get("applicability_branches"),
        _APPLICABILITY_BRANCH_ROLES,
        "Corpus Planning applicability branches")
    if (not all(_nonempty_string(value) and value.strip() == value
                for value in branches.values()) or
            len(set(branches.values())) != len(branches)):
        raise ValueError(
            "Corpus Planning applicability branches must be distinct "
            "non-empty strings")
    roles = _closed_mapping(
        slot.get("artifact_roles"), set(artifact_fields),
        "Corpus Planning artifact roles")
    if (not all(_nonempty_string(value) and value.strip() == value
                for value in roles.values()) or
            len(set(roles.values())) != len(roles)):
        raise ValueError(
            "Corpus Planning artifact roles must be distinct non-empty "
            "strings")
    scope = slot.get("semantic_acceptance_scope")
    if not _nonempty_string(scope) or scope.strip() != scope:
        raise ValueError(
            "Corpus Planning semantic_acceptance_scope must be non-empty")

    receipt = _closed_mapping(
        document.get("receipt_binding"), _RECEIPT_BINDING_FIELDS,
        "Corpus Planning receipt binding")
    receipt_fields = _unique_string_list(
        receipt.get("fields"), "Corpus Planning receipt binding fields")
    if "corpus_plan_applicability" not in receipt_fields:
        raise ValueError(
            "Corpus Planning receipt binding must carry applicability")
    path_rows = receipt.get("path_sha_bindings")
    if not isinstance(path_rows, list) or not path_rows:
        raise ValueError(
            "Corpus Planning path/SHA bindings must be a non-empty list")
    path_sha_bindings = []
    path_fields = set()
    sha_fields = set()
    for index, raw in enumerate(path_rows):
        row = _closed_mapping(
            raw, _PATH_SHA_BINDING_FIELDS,
            "Corpus Planning path/SHA binding %d" % index)
        path_field = row.get("path_field")
        sha_field = row.get("sha256_field")
        requirement = row.get("requirement")
        if path_field not in receipt_fields or sha_field not in receipt_fields:
            raise ValueError(
                "Corpus Planning path/SHA binding %d names an unknown "
                "receipt field" % index)
        if path_field in path_fields or sha_field in sha_fields:
            raise ValueError(
                "Corpus Planning path/SHA binding fields must be unique")
        if requirement not in _PATH_SHA_REQUIREMENTS:
            raise ValueError(
                "Corpus Planning path/SHA binding %d has an unknown "
                "requirement" % index)
        path_fields.add(path_field)
        sha_fields.add(sha_field)
        path_sha_bindings.append((path_field, sha_field, requirement))

    triggers = _closed_mapping(
        document.get("close_triggers"), _CLOSE_TRIGGER_ROLES,
        "Corpus Planning close triggers")
    if (not all(_nonempty_string(value) and value.strip() == value
                for value in triggers.values()) or
            len(set(triggers.values())) != len(triggers)):
        raise ValueError(
            "Corpus Planning close triggers must be distinct non-empty "
            "strings")

    return {
        "slot_name": slot["slot_name"],
        "slot_schema_version": slot["schema_version"],
        "slot_fields": frozenset(slot_fields),
        "applicability_fields": frozenset(applicability_fields),
        "artifact_binding_fields": tuple(artifact_fields),
        "capability_scale_fields": frozenset(scale_fields),
        "pass_authority_fields": frozenset(authority_fields),
        "configured_state": branches["configured"],
        "inactive_state": branches["inactive"],
        "artifact_roles": dict(roles),
        "semantic_acceptance_scope": scope,
        "receipt_binding_fields": tuple(receipt_fields),
        "path_sha_bindings": tuple(path_sha_bindings),
        "close_route_trigger": triggers["selected_route"],
        "close_manifest_trigger": triggers["affected_manifest"],
    }


def load_corpus_planning_contract(root=None, *, snapshots=None, text=None):
    """Load and validate the K02 registry from text, a snapshot, or a root."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if text is None:
        snapshot = (snapshots or {}).get(CORPUS_PLANNING_CONTRACT_PATH)
        if snapshot is not None:
            text = snapshot.read_text()
        else:
            text = kblib.read_text(os.path.join(
                root, *CORPUS_PLANNING_CONTRACT_PATH.split("/")))
    document = kblib.parse_yaml_subset(text)
    validate_corpus_planning_contract(document)
    return document


_SHIPPED_DOCUMENT = load_corpus_planning_contract()
_SHIPPED_VALUES = validate_corpus_planning_contract(_SHIPPED_DOCUMENT)

SLOT_NAME = _SHIPPED_VALUES["slot_name"]
SLOT_SCHEMA_VERSION = _SHIPPED_VALUES["slot_schema_version"]
SLOT_FIELDS = _SHIPPED_VALUES["slot_fields"]
APPLICABILITY_FIELDS = _SHIPPED_VALUES["applicability_fields"]
ARTIFACT_BINDING_FIELDS = _SHIPPED_VALUES["artifact_binding_fields"]
CAPABILITY_SCALE_FIELDS = _SHIPPED_VALUES["capability_scale_fields"]
PASS_AUTHORITY_FIELDS = _SHIPPED_VALUES["pass_authority_fields"]
CONFIGURED_STATE = _SHIPPED_VALUES["configured_state"]
INACTIVE_STATE = _SHIPPED_VALUES["inactive_state"]
APPLICABILITY_STATES = frozenset((CONFIGURED_STATE, INACTIVE_STATE))
ARTIFACT_FIELD_ROLES = _SHIPPED_VALUES["artifact_roles"]
ARTIFACT_ROLES = tuple(
    ARTIFACT_FIELD_ROLES[field] for field in ARTIFACT_BINDING_FIELDS)
SEMANTIC_ACCEPTANCE_SCOPE = _SHIPPED_VALUES[
    "semantic_acceptance_scope"]
PASS_RECEIPT_BINDING_FIELDS = _SHIPPED_VALUES[
    "receipt_binding_fields"]
PASS_RECEIPT_PATH_SHA_BINDINGS = _SHIPPED_VALUES["path_sha_bindings"]
CLOSE_ROUTE_TRIGGER = _SHIPPED_VALUES["close_route_trigger"]
CLOSE_MANIFEST_TRIGGER = _SHIPPED_VALUES["close_manifest_trigger"]
CLOSE_TRIGGERS = frozenset((CLOSE_ROUTE_TRIGGER, CLOSE_MANIFEST_TRIGGER))


def current_corpus_planning_contract_values(root=None, *, snapshots=None):
    """Return current values and reject drift from the deployed projection."""
    document = load_corpus_planning_contract(root, snapshots=snapshots)
    if document != _SHIPPED_DOCUMENT:
        raise ValueError(
            "adopting Corpus Planning registry differs from the validator's "
            "deployed Kernel contract")
    return validate_corpus_planning_contract(document)


def _issue(code, path=(), **values):
    issue = {"code": code, "path": tuple(path)}
    issue.update(values)
    return issue


def _envelope_mapping(value, fields, path, issues):
    if not isinstance(value, dict):
        issues.append(_issue("mapping_type", path))
        return {}
    missing = sorted(set(fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing:
        issues.append(_issue("missing_fields", path, fields=tuple(missing)))
    if extra:
        issues.append(_issue("unsupported_fields", path,
                             fields=tuple(extra)))
    return value


def validate_corpus_planning_envelope(document, *, normalize_strings=True):
    """Validate the shared slot envelope and its two existing branches.

    Returns ``(normalized, issues)``.  Issues are neutral structural records;
    producer adapters retain their historical check codes and wording.  Deep
    artifact existence/containment, Role Registry membership, and the three
    artifact record contracts intentionally remain outside this function.
    """
    issues = []
    document = _envelope_mapping(document, SLOT_FIELDS, (), issues)
    if type(document.get("schema_version")) is not int or \
            document.get("schema_version") != SLOT_SCHEMA_VERSION:
        issues.append(_issue("schema_version"))

    applicability = _envelope_mapping(
        document.get("applicability"), APPLICABILITY_FIELDS,
        ("applicability",), issues)
    artifacts = _envelope_mapping(
        document.get("artifact_bindings"), ARTIFACT_BINDING_FIELDS,
        ("artifact_bindings",), issues)
    authority = _envelope_mapping(
        document.get("pass_authority"), PASS_AUTHORITY_FIELDS,
        ("pass_authority",), issues)
    scale_rows = document.get("capability_scale")
    if not isinstance(scale_rows, list):
        issues.append(_issue("scale_list", ("capability_scale",)))
        scale_rows = []

    mode = applicability.get("state")
    raw_reason = applicability.get("reason")
    reason = (raw_reason.strip() if normalize_strings and
              isinstance(raw_reason, str) else raw_reason)
    normalized = {
        "mode": mode if mode in APPLICABILITY_STATES else None,
        "reason": reason,
        "artifact_bindings": {},
        "scale": [],
        "authority": {},
    }
    if mode not in APPLICABILITY_STATES:
        issues.append(_issue("applicability_state",
                             ("applicability", "state")))
        return normalized, tuple(issues)

    if mode == INACTIVE_STATE:
        if not isinstance(raw_reason, str) or not raw_reason.strip():
            issues.append(_issue("inactive_reason",
                                 ("applicability", "reason")))
        nonnull_artifacts = tuple(
            field for field in ARTIFACT_BINDING_FIELDS
            if artifacts.get(field) is not None)
        if nonnull_artifacts:
            issues.append(_issue(
                "inactive_artifacts", ("artifact_bindings",),
                fields=nonnull_artifacts))
        if scale_rows:
            issues.append(_issue("inactive_scale", ("capability_scale",)))
        nonnull_authority = tuple(
            field for field in PASS_AUTHORITY_FIELDS
            if authority.get(field) is not None)
        if nonnull_authority:
            issues.append(_issue(
                "inactive_authority", ("pass_authority",),
                fields=nonnull_authority))
        return normalized, tuple(issues)

    if raw_reason is not None:
        issues.append(_issue("configured_reason",
                             ("applicability", "reason")))

    artifact_identities = []
    for field in ARTIFACT_BINDING_FIELDS:
        value = artifacts.get(field)
        if (not isinstance(value, str) or not value.strip() or
                not value.lower().endswith(".yaml")):
            issues.append(_issue(
                "configured_artifact_path", ("artifact_bindings", field),
                value=value))
            continue
        # Both historical producers compared artifact identities after
        # trimming the YAML scalar; ``normalize_strings`` exists only for the
        # older Profile producer's scale-value compatibility behavior.
        normalized_value = value.strip()
        normalized["artifact_bindings"][field] = normalized_value
        artifact_identities.append(normalized_value)
    if len(artifact_identities) != len(set(artifact_identities)):
        issues.append(_issue("artifact_bindings_distinct",
                             ("artifact_bindings",)))

    if not scale_rows:
        issues.append(_issue("configured_scale_empty",
                             ("capability_scale",)))
    values = set()
    target_eligible = False
    for index, raw in enumerate(scale_rows):
        row_path = ("capability_scale", index)
        row = _envelope_mapping(
            raw, CAPABILITY_SCALE_FIELDS, row_path, issues)
        rank = row.get("rank")
        if type(rank) is not int or rank < 0:
            issues.append(_issue("scale_rank_type", row_path + ("rank",),
                                 index=index, value=rank))
            normalized_rank = None
        elif rank != index:
            issues.append(_issue("scale_rank_position",
                                 row_path + ("rank",), index=index,
                                 value=rank))
            normalized_rank = rank
        else:
            normalized_rank = rank

        raw_value = row.get("value")
        if not isinstance(raw_value, str):
            issues.append(_issue("scale_value_type",
                                 row_path + ("value",), value=raw_value))
            value = ""
        elif not raw_value.strip():
            issues.append(_issue("scale_value_empty",
                                 row_path + ("value",), value=raw_value))
            value = ""
        else:
            value = raw_value.strip() if normalize_strings else raw_value
        if value in values and value:
            issues.append(_issue("scale_value_duplicate",
                                 row_path + ("value",), value=value))
        elif value:
            values.add(value)

        raw_predicate = row.get("predicate")
        if not isinstance(raw_predicate, str):
            issues.append(_issue("scale_predicate_type",
                                 row_path + ("predicate",),
                                 value=raw_predicate))
            predicate = ""
        elif not raw_predicate.strip():
            issues.append(_issue("scale_predicate_empty",
                                 row_path + ("predicate",),
                                 value=raw_predicate))
            predicate = ""
        else:
            predicate = (raw_predicate.strip() if normalize_strings else
                         raw_predicate)

        eligible = row.get("target_eligible")
        if type(eligible) is not bool:
            issues.append(_issue("scale_target_eligible_type",
                                 row_path + ("target_eligible",),
                                 value=eligible))
            normalized_eligible = False
        else:
            normalized_eligible = eligible
        target_eligible = target_eligible or eligible is True
        normalized["scale"].append({
            "rank": normalized_rank,
            "value": value,
            "predicate": predicate,
            "target_eligible": normalized_eligible,
        })
    if scale_rows and not target_eligible:
        issues.append(_issue("configured_target_eligible",
                             ("capability_scale",)))

    raw_role = authority.get("role_id")
    if not isinstance(raw_role, str):
        issues.append(_issue("authority_role_type",
                             ("pass_authority", "role_id"),
                             value=raw_role))
        role = ""
    elif not raw_role.strip():
        issues.append(_issue("authority_role_empty",
                             ("pass_authority", "role_id"),
                             value=raw_role))
        role = ""
    else:
        role = raw_role.strip() if normalize_strings else raw_role
    raw_decision = authority.get("decision_scope_id")
    if not isinstance(raw_decision, str):
        issues.append(_issue("authority_decision_type",
                             ("pass_authority", "decision_scope_id"),
                             value=raw_decision))
        decision = ""
    elif not raw_decision.strip():
        issues.append(_issue("authority_decision_empty",
                             ("pass_authority", "decision_scope_id"),
                             value=raw_decision))
        decision = ""
    else:
        decision = (raw_decision.strip() if normalize_strings else
                    raw_decision)
    if decision != SEMANTIC_ACCEPTANCE_SCOPE:
        issues.append(_issue("authority_decision_scope",
                             ("pass_authority", "decision_scope_id"),
                             value=decision))
    normalized["authority"] = {
        "role_id": role,
        "decision_scope_id": decision,
    }
    return normalized, tuple(issues)


def receipt_binding_differences(receipt, expected_binding, *, fields=None):
    """Return exact field-level differences for one currentness comparison."""
    if not isinstance(receipt, dict):
        raise TypeError("receipt must be a mapping")
    if not isinstance(expected_binding, dict):
        raise TypeError("expected_binding must be a mapping")
    selected = tuple(fields) if fields is not None else \
        PASS_RECEIPT_BINDING_FIELDS
    return tuple({
        "field": field,
        "missing": field not in receipt,
        "actual": receipt.get(field),
        "expected": expected_binding.get(field),
    } for field in selected
        if field not in receipt or
        receipt.get(field) != expected_binding.get(field))


def receipt_path_currentness_issues(receipt, applicability):
    """Validate applicability-dependent path/SHA presence and hash shape."""
    if not isinstance(receipt, dict):
        raise TypeError("receipt must be a mapping")
    issues = []
    for path_field, sha_field, requirement in PASS_RECEIPT_PATH_SHA_BINDINGS:
        required = (requirement == "always" or
                    applicability == CONFIGURED_STATE)
        path_value = receipt.get(path_field)
        sha_value = receipt.get(sha_field)
        if required:
            if not _nonempty_string(path_value):
                issues.append({"code": "required_path", "path_field":
                               path_field, "sha256_field": sha_field})
            if not isinstance(sha_value, str) or not _SHA256_RE.fullmatch(
                    sha_value):
                issues.append({"code": "required_sha256", "path_field":
                               path_field, "sha256_field": sha_field})
        elif path_field not in receipt or sha_field not in receipt:
            issues.append({"code": "inactive_pair_missing", "path_field":
                           path_field, "sha256_field": sha_field})
        elif path_value is not None or sha_value is not None:
            issues.append({"code": "inactive_pair_nonnull", "path_field":
                           path_field, "sha256_field": sha_field})
    return tuple(issues)


def receipt_binding_shape_issues(binding):
    """Return closed-field and path/SHA issues for a producer binding."""
    if not isinstance(binding, dict):
        return ({"code": "binding_type"},)
    issues = []
    missing = tuple(
        field for field in PASS_RECEIPT_BINDING_FIELDS
        if field not in binding)
    extra = tuple(sorted(set(binding) - set(PASS_RECEIPT_BINDING_FIELDS)))
    if missing:
        issues.append({"code": "binding_fields_missing", "fields": missing})
    if extra:
        issues.append({"code": "binding_fields_extra", "fields": extra})
    issues.extend(receipt_path_currentness_issues(
        binding, binding.get("corpus_plan_applicability")))
    return tuple(issues)


def derive_close_requirement(selected_route_ids, manifest, affected_paths):
    """Project the existing route/manifest applicability triggers."""
    routes = selected_route_ids if isinstance(selected_route_ids, list) else []
    manifest = manifest if isinstance(manifest, list) else []
    triggers = []
    if CLOSE_ROUTE_TRIGGER in routes:
        triggers.append(CLOSE_ROUTE_TRIGGER)
    if set(affected_paths).intersection(manifest):
        triggers.append(CLOSE_MANIFEST_TRIGGER)
    triggers = sorted(set(triggers))
    return bool(triggers), triggers


def close_trigger_issues(required, triggers):
    """Return neutral issues for a persisted close-trigger projection."""
    issues = []
    if (not isinstance(triggers, list) or
            any(not _nonempty_string(value) for value in triggers)):
        issues.append({"code": "trigger_list"})
        normalized = []
    else:
        normalized = triggers
        if normalized != sorted(set(normalized)):
            issues.append({"code": "trigger_order"})
        unsupported = tuple(sorted(set(normalized) - CLOSE_TRIGGERS))
        if unsupported:
            issues.append({"code": "trigger_unsupported",
                           "values": unsupported})
    if required is False and normalized:
        issues.append({"code": "inactive_triggers"})
    elif required is True and not normalized:
        issues.append({"code": "required_trigger_missing"})
    return tuple(issues)


__all__ = [
    "APPLICABILITY_FIELDS",
    "APPLICABILITY_STATES",
    "ARTIFACT_BINDING_FIELDS",
    "ARTIFACT_FIELD_ROLES",
    "ARTIFACT_ROLES",
    "CAPABILITY_SCALE_FIELDS",
    "CLOSE_MANIFEST_TRIGGER",
    "CLOSE_ROUTE_TRIGGER",
    "CLOSE_TRIGGERS",
    "CONFIGURED_STATE",
    "CORPUS_PLANNING_CONTRACT_PATH",
    "INACTIVE_STATE",
    "PASS_AUTHORITY_FIELDS",
    "PASS_RECEIPT_BINDING_FIELDS",
    "PASS_RECEIPT_PATH_SHA_BINDINGS",
    "SEMANTIC_ACCEPTANCE_SCOPE",
    "SLOT_FIELDS",
    "SLOT_NAME",
    "SLOT_SCHEMA_VERSION",
    "close_trigger_issues",
    "current_corpus_planning_contract_values",
    "derive_close_requirement",
    "load_corpus_planning_contract",
    "receipt_binding_differences",
    "receipt_binding_shape_issues",
    "receipt_path_currentness_issues",
    "validate_corpus_planning_contract",
    "validate_corpus_planning_envelope",
]
