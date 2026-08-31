"""Current Receipt type dispatch derived from producer-owned contracts.

``Tools/operation-capabilities.yaml`` names exactly one producer capability
and exactly one existing typed validator for every Receipt type admitted to a
Cambium runtime.  This module owns only that dispatch closure.  It does not
repeat a producer's tool/version/check tuple or its payload predicate: the
referenced validator remains the machine owner of those facts.

The contract is deliberately stricter than the Receipt reference graph.  The
graph says which IDs an object may reference; this registry first proves that
the object itself is a current-contract Receipt.  Unknown, multiply-owned, or
invalid types never enter hot, historical, or cold catalogs.
"""

from dataclasses import dataclass
import importlib
import re
from types import MappingProxyType

from Tools.execution.evidence import receipt_reference_contract
from Tools.governance.control import metadata_execution_contract


_DEFAULT_REGISTRY_PATH = "Tools/operation-capabilities.yaml"
_SUPPORTED_LIFECYCLES = frozenset(("hot", "historical", "cold"))
NONE_SOURCE_KIND = "none"

_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_OWNER_RE = re.compile(
    r"Tools(?:\.[a-z][a-z0-9_]*)+:[a-z][a-z0-9_]*\Z")
_RECEIPT_CONTRACT_KEYS = frozenset((
    "receipt_type_id", "validator_owner", "catalog_lifecycle",
    "reference_source_kind",
))


class ReceiptTypeContractError(ValueError):
    """The current Receipt dispatch registry is incomplete or ambiguous."""


@dataclass(frozen=True)
class ReceiptTypeRegistration:
    """One dispatch row; semantic predicates stay behind validator_owner."""

    receipt_type_id: str
    producer_capability_id: str
    validator_owner: str
    catalog_lifecycle: tuple
    reference_source_kind: str


def _closed_mapping(value, fields, label):
    if not isinstance(value, dict):
        raise ReceiptTypeContractError("%s must be a mapping" % label)
    missing = sorted(set(fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing or extra:
        raise ReceiptTypeContractError(
            "%s fields are not closed: missing=%s extra=%s" %
            (label, missing, extra))
    return value


def _string_list(value, label, *, allowed=None):
    if not isinstance(value, list) or not value:
        raise ReceiptTypeContractError("%s must be a non-empty list" % label)
    if any(not isinstance(item, str) or not item for item in value):
        raise ReceiptTypeContractError(
            "%s must contain only non-empty strings" % label)
    if len(value) != len(set(value)):
        raise ReceiptTypeContractError("%s contains duplicates" % label)
    if allowed is not None:
        unknown = sorted(set(value) - set(allowed))
        if unknown:
            raise ReceiptTypeContractError(
                "%s contains unknown values: %s" %
                (label, ", ".join(unknown)))
    return tuple(value)


def load_receipt_type_registry(root=None,
                               relative_path=_DEFAULT_REGISTRY_PATH):
    """Load the unique producer-to-validator dispatch registry."""
    try:
        document = metadata_execution_contract.load_operation_capabilities(
            root, relative_path)
    except metadata_execution_contract.MetadataExecutionContractError as exc:
        raise ReceiptTypeContractError(
            "cannot load Receipt type registry: %s" % exc) from exc
    capabilities = document.get("capabilities")

    registrations = {}
    producer_counts = {}
    for capability_index, capability in enumerate(capabilities):
        label = "capabilities[%d]" % capability_index
        capability_id = capability.get("capability_id")
        rows = capability.get("receipt_contracts", [])
        if not isinstance(rows, list):
            raise ReceiptTypeContractError(
                "%s receipt_contracts must be a list" % label)
        for row_index, row in enumerate(rows):
            row_label = "%s receipt_contracts[%d]" % (label, row_index)
            _closed_mapping(row, _RECEIPT_CONTRACT_KEYS, row_label)
            receipt_type_id = row.get("receipt_type_id")
            if not isinstance(receipt_type_id, str) or not _ID_RE.fullmatch(
                    receipt_type_id):
                raise ReceiptTypeContractError(
                    "%s receipt_type_id is invalid" % row_label)
            validator_owner = row.get("validator_owner")
            if not isinstance(validator_owner, str) or not _OWNER_RE.fullmatch(
                    validator_owner):
                raise ReceiptTypeContractError(
                    "%s validator_owner is invalid" % row_label)
            lifecycle = _string_list(
                row.get("catalog_lifecycle"),
                "%s catalog_lifecycle" % row_label,
                allowed=_SUPPORTED_LIFECYCLES,
            )
            source_kind = row.get("reference_source_kind")
            if not isinstance(source_kind, str) or not source_kind:
                raise ReceiptTypeContractError(
                    "%s reference_source_kind must be non-empty" % row_label)
            if source_kind != NONE_SOURCE_KIND:
                try:
                    receipt_reference_contract.reference_specs(source_kind)
                except receipt_reference_contract.ReceiptReferenceError as exc:
                    raise ReceiptTypeContractError(
                        "%s reference_source_kind is not registered: %s" %
                        (row_label, exc)) from exc
            producer_counts[receipt_type_id] = \
                producer_counts.get(receipt_type_id, 0) + 1
            if receipt_type_id in registrations:
                continue
            registrations[receipt_type_id] = ReceiptTypeRegistration(
                receipt_type_id=receipt_type_id,
                producer_capability_id=capability_id,
                validator_owner=validator_owner,
                catalog_lifecycle=lifecycle,
                reference_source_kind=source_kind,
            )
    duplicates = sorted(
        receipt_type_id for receipt_type_id, count in producer_counts.items()
        if count != 1)
    if duplicates:
        raise ReceiptTypeContractError(
            "Receipt type(s) must have exactly one producer capability: %s" %
            ", ".join(duplicates))
    if not registrations:
        raise ReceiptTypeContractError(
            "operation capability registry declares no Receipt contracts")
    return MappingProxyType(registrations)


def _validator(owner):
    module_name, separator, symbol = owner.partition(":")
    if not separator:
        raise ReceiptTypeContractError(
            "Receipt validator owner is malformed: %s" % owner)
    try:
        module = importlib.import_module(module_name)
        validator = getattr(module, symbol)
    except (ImportError, AttributeError) as exc:
        raise ReceiptTypeContractError(
            "Receipt validator owner is unavailable: %s" % owner) from exc
    if not callable(validator):
        raise ReceiptTypeContractError(
            "Receipt validator owner is not callable: %s" % owner)
    return validator


def current_receipt_errors(record, lifecycle, *, root=None, registry=None):
    """Validate one body for one current-contract catalog lifecycle."""
    errors = []
    if lifecycle not in _SUPPORTED_LIFECYCLES:
        return ["unknown Receipt catalog lifecycle %r" % lifecycle]
    if not isinstance(record, dict):
        return ["Receipt body must be a mapping"]
    receipt_type_id = record.get("receipt_type_id")
    if not isinstance(receipt_type_id, str) or not _ID_RE.fullmatch(
            receipt_type_id):
        return ["Receipt has no valid current receipt_type_id"]
    if registry is None:
        try:
            registry = load_receipt_type_registry(root)
        except ReceiptTypeContractError as exc:
            return [str(exc)]
    registration = registry.get(receipt_type_id)
    if registration is None:
        return ["Receipt type %s is not registered by a current producer" %
                receipt_type_id]
    if lifecycle not in registration.catalog_lifecycle:
        return ["Receipt type %s is not admitted to the %s catalog" %
                (receipt_type_id, lifecycle)]
    try:
        validator = _validator(registration.validator_owner)
        owned_errors = validator(record, root=root)
    except Exception as exc:
        return ["Receipt type %s validator failed: %s" %
                (receipt_type_id, exc)]
    if not isinstance(owned_errors, (list, tuple)) or any(
            not isinstance(item, str) for item in owned_errors):
        return ["Receipt type %s validator returned an invalid result" %
                receipt_type_id]
    errors.extend(owned_errors)
    return errors


def reference_source_kind(record, *, root=None, registry=None):
    """Return the registered reference-graph kind for a typed Receipt."""
    if not isinstance(record, dict):
        raise ReceiptTypeContractError("Receipt body must be a mapping")
    if registry is None:
        registry = load_receipt_type_registry(root)
    receipt_type_id = record.get("receipt_type_id")
    registration = registry.get(receipt_type_id)
    if registration is None:
        raise ReceiptTypeContractError(
            "Receipt type %r has no current producer" % receipt_type_id)
    if registration.reference_source_kind == NONE_SOURCE_KIND:
        return None
    return registration.reference_source_kind


def base_receipt_errors(record, *, receipt_type_id, tool, tool_version,
                        checks):
    """Validate the shared envelope plus owner-supplied exact identities.

    ``checks`` is passed by the typed owner.  It may contain one authorizing
    check or an owner-derived closed diagnostic set; this helper never creates
    or widens that set.
    """
    errors = []
    if not isinstance(record, dict):
        return ["Receipt body must be a mapping"]
    expected = {
        "receipt_type_id": receipt_type_id,
        "tool": tool,
        "tool_version": tool_version,
    }
    for field, value in expected.items():
        if record.get(field) != value:
            errors.append("%s must equal %r" % (field, value))
    if isinstance(checks, str):
        checks = (checks,)
    checks = tuple(checks)
    if not checks or record.get("check") not in checks:
        errors.append("check is not in the owner-defined current set")
    for field in (
            "receipt_id", "target", "details", "checked_at", "result",
            "invalidated_by"):
        if field not in record:
            errors.append("Receipt misses %s" % field)
    if record.get("result") not in ("pass", "fail", "candidate"):
        errors.append("Receipt result is invalid")
    if record.get("invalidated_by") is not None and not isinstance(
            record.get("invalidated_by"), str):
        errors.append("Receipt invalidated_by must be null or text")
    return errors


__all__ = (
    "ReceiptTypeContractError", "base_receipt_errors",
    "current_receipt_errors", "load_receipt_type_registry",
    "reference_source_kind",
)
