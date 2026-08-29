"""Does the transaction still hold the exact admission it froze.

An opaque authority context, its compare-and-swap against current bytes, and
its projection into writer-lock metadata.  The context is opaque on purpose:
a caller that could read it apart would be able to reconstruct a weaker
version of the same claim.
"""

from dataclasses import dataclass
import os
from typing import Optional

import metadata_execution_contract
import profile_contract
from queue_runtime.primitives import nonempty_string
from queue_runtime.profile_view import (
    active_standards_view_currency_errors,
    profile_load_authorized_view_currency_errors,
)


@dataclass(frozen=True)
class RuntimeAuthoritySpec:
    """One member of the closed transaction-authority topology."""

    authority_id: str
    kind: str
    result_key: str
    context_key: str
    covered_by: Optional[str]
    validation_kwarg: Optional[str]


RUNTIME_AUTHORITY_REGISTRY = (
    RuntimeAuthoritySpec(
        authority_id="active-standards",
        kind="primary",
        result_key="_active_standards_authorized_view",
        context_key="active_standards_view",
        covered_by=None,
        validation_kwarg="authorized_active_standards_view",
    ),
    RuntimeAuthoritySpec(
        authority_id="profile-load",
        kind="primary",
        result_key="_profile_authorized_view",
        context_key="profile_view",
        covered_by=None,
        validation_kwarg="authorized_profile_view",
    ),
    RuntimeAuthoritySpec(
        authority_id="metadata-execution-contract",
        kind="derived",
        result_key="_metadata_execution_contract",
        context_key="metadata_execution_contract",
        covered_by="profile-load",
        validation_kwarg=None,
    ),
)

_AUTHORITY_BY_ID = {
    spec.authority_id: spec for spec in RUNTIME_AUTHORITY_REGISTRY}
if len(_AUTHORITY_BY_ID) != len(RUNTIME_AUTHORITY_REGISTRY):
    raise RuntimeError("runtime authority registry has duplicate IDs")
for _field in ("result_key", "context_key"):
    _values = [getattr(spec, _field) for spec in RUNTIME_AUTHORITY_REGISTRY]
    if len(set(_values)) != len(_values):
        raise RuntimeError(
            "runtime authority registry has duplicate %s values" % _field)
if {spec.kind for spec in RUNTIME_AUTHORITY_REGISTRY} != {
        "primary", "derived"}:
    raise RuntimeError("runtime authority registry must contain both kinds")
for _spec in RUNTIME_AUTHORITY_REGISTRY:
    if (_spec.kind == "primary") != (_spec.validation_kwarg is not None):
        raise RuntimeError(
            "primary runtime authorities alone own validation kwargs")
    if _spec.kind == "primary" and _spec.covered_by is not None:
        raise RuntimeError(
            "primary runtime authorities cannot be covered by another member")
    if (_spec.kind == "derived" and (
            _spec.covered_by not in _AUTHORITY_BY_ID or
            _AUTHORITY_BY_ID[_spec.covered_by].kind != "primary")):
        raise RuntimeError(
            "derived runtime authority has no registered primary covering "
            "authority")

_CURRENCY_CHECKERS = {
    "active-standards": (
        "active Standards authority", active_standards_view_currency_errors),
    "profile-load": (
        "Profile-load authority",
        profile_load_authorized_view_currency_errors),
}
_PRIMARY_AUTHORITY_IDS = {
    spec.authority_id for spec in RUNTIME_AUTHORITY_REGISTRY
    if spec.kind == "primary"}
if set(_CURRENCY_CHECKERS) != _PRIMARY_AUTHORITY_IDS:
    raise RuntimeError(
        "every primary runtime authority must own one currency checker")

_LOCK_FIELD_PROJECTORS = {
    "active-standards": lambda view: {
        "standards_version": view.get("standards_version"),
        "active_standards_sha256": view.get("active_standards_sha256"),
    },
    "profile-load": lambda view: {
        field: view.get(field)
        for field in profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS
    },
    "metadata-execution-contract": lambda contract: {
        "metadata_execution_contract_fingerprint":
            contract.contract_fingerprint,
    },
}
if set(_LOCK_FIELD_PROJECTORS) != set(_AUTHORITY_BY_ID):
    raise RuntimeError(
        "every runtime authority must own one lock-evidence projection")


def runtime_authority_registry():
    """Return the closed, immutable primary/derived authority registry."""
    return RUNTIME_AUTHORITY_REGISTRY


def runtime_metadata_execution_contract(observation):
    """Return the exact metadata object carried by one admitted observation."""
    if not isinstance(observation, dict):
        raise TypeError("runtime authority observation must be a mapping")
    contract = observation.get("metadata_execution_contract")
    if contract is None:
        contract = observation.get("_metadata_execution_contract")
    if not isinstance(
            contract,
            metadata_execution_contract.CompiledMetadataExecutionContract):
        raise ValueError(
            "runtime authority has no admitted metadata execution contract")
    return contract


def runtime_authority_context(result):
    """Freeze one successful runtime admission for a complete transaction.

    Ordinary writers call :func:`validate_runtime` once without injected
    views, then carry this opaque context through every proposed, locked, and
    post-write validation.  The primary Profile/K00 views and the
    Profile-covered metadata object are deliberately kept together: accepting
    any member from another admission would recreate the split-revision window
    this API is intended to close.
    """
    if not isinstance(result, dict):
        raise TypeError("runtime validation result must be a mapping")
    if result.get("errors"):
        raise ValueError(
            "runtime authority context requires a successful validation")
    root = result.get("root")
    queue = result.get("queue")
    values = {spec.authority_id: result.get(spec.result_key)
              for spec in RUNTIME_AUTHORITY_REGISTRY}
    profile_view = values["profile-load"]
    active_view = values["active-standards"]
    metadata_contract = values["metadata-execution-contract"]
    if not nonempty_string(root) or not isinstance(queue, dict):
        raise ValueError("runtime validation result has no canonical root or Queue")
    if not isinstance(profile_view, dict):
        raise ValueError("runtime validation result has no authorized Profile view")
    if not isinstance(active_view, dict):
        raise ValueError(
            "runtime validation result has no authorized active Standards view")
    if not isinstance(
            metadata_contract,
            metadata_execution_contract.CompiledMetadataExecutionContract):
        raise ValueError(
            "runtime validation result has no authorized metadata contract")
    if profile_view.get("_metadata_execution_contract") is not metadata_contract:
        raise ValueError(
            "runtime metadata contract was not produced by its Profile-load "
            "covering authority")
    if profile_view.get("metadata_execution_contract_fingerprint") != \
            metadata_contract.contract_fingerprint:
        raise ValueError(
            "runtime metadata contract fingerprint differs from Profile-load")
    expected_profile = queue.get("selected_profile_manifest")
    expected_standards = queue.get("standards_version")
    if (profile_view.get("selected_profile_manifest") != expected_profile or
            active_view.get("selected_profile_manifest") != expected_profile):
        raise ValueError(
            "runtime authority views do not select the validated Queue Profile")
    if active_view.get("standards_version") != expected_standards:
        raise ValueError(
            "runtime active Standards view does not select the validated "
            "Queue version")
    context = {"root": os.path.realpath(os.path.abspath(root))}
    for spec in RUNTIME_AUTHORITY_REGISTRY:
        context[spec.context_key] = values[spec.authority_id]
    return context


def runtime_authority_validation_kwargs(context):
    """Return the indivisible view pair for a later runtime validation."""
    if not isinstance(context, dict):
        raise TypeError("runtime authority context must be a mapping")
    kwargs = {}
    for spec in RUNTIME_AUTHORITY_REGISTRY:
        value = context.get(spec.context_key)
        if spec.kind == "derived":
            continue
        if not isinstance(value, dict):
            raise ValueError(
                "runtime authority context has no %s primary view" %
                spec.authority_id)
        kwargs[spec.validation_kwarg] = value
    metadata_contract = runtime_metadata_execution_contract(context)
    profile_view = context.get("profile_view")
    if profile_view.get("_metadata_execution_contract") is not \
            metadata_contract:
        raise ValueError(
            "derived metadata authority differs from its Profile-load view")
    return kwargs


def runtime_authority_currency_errors(root, context):
    """Return CAS failures for every root authority bound by ``context``."""
    if not isinstance(context, dict):
        return ["runtime authority context must be a mapping"]
    canonical_root = os.path.realpath(os.path.abspath(os.fspath(root)))
    if context.get("root") != canonical_root:
        return ["runtime authority context belongs to a different repository root"]
    try:
        runtime_authority_validation_kwargs(context)
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    errors = []
    for spec in RUNTIME_AUTHORITY_REGISTRY:
        if spec.kind != "primary":
            continue
        label, checker = _CURRENCY_CHECKERS[spec.authority_id]
        for detail in checker(canonical_root, context[spec.context_key]):
            errors.append("%s: %s" % (label, detail))
    return errors


def require_runtime_authority_current(root, context, phase):
    """Raise when a transaction no longer sees its admitted authority bytes."""
    errors = runtime_authority_currency_errors(root, context)
    if errors:
        raise ValueError("%s: %s" % (phase, "; ".join(errors)))


def runtime_authority_lock_fields(context):
    """Project one transaction authority binding into writer-lock metadata."""
    runtime_authority_validation_kwargs(context)
    fields = {}
    for spec in RUNTIME_AUTHORITY_REGISTRY:
        fields.update(_LOCK_FIELD_PROJECTORS[spec.authority_id](
            context[spec.context_key]))
    return fields
