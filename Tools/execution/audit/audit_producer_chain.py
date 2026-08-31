"""Resolve one Kernel-owned audit producer through its complete chain.

The frozen AuditPlan names the actual producer of the intermediate evidence.
For an ``audit-receipt`` obligation, the final AuditReceipt producer is a
deterministic consequence of that evidence kind; it is not substituted into
the plan in place of the real producer. Kernel registries own the precursor
identity and check, ``operation-capabilities.yaml`` owns its implementation
and public entrypoint, record contracts own the intermediate shape, and the
AuditReceipt contract owns the terminal shape.

This module is the sole Tool-side interpretation that joins those independent
authorities. It does not create obligations or maintain a second producer-ID
map.
"""

from copy import deepcopy

import Tools.execution.audit.audit_lifecycle_contract as lifecycle
import Tools.execution.audit.audit_obligation_projection as projection
import Tools.execution.audit.substantive_review_contract as substantive
import Tools.governance.control.metadata_execution_contract as capabilities
import Tools.knowledge.rendering.rendering_verification_contract as rendering


class AuditProducerChainError(ValueError):
    """A registered audit obligation has no unique executable evidence chain."""


FINAL_AUDIT_RECEIPT_CAPABILITY = "audit-receipt-producer-v1"

_CHAIN_FIELDS = (
    "execution_route", "final_evidence_kind", "final_producer_capability",
    "precursor_record_kind", "precursor_tool", "precursor_capability",
    "precursor_check",
)


def _definition_candidates(spec, obligation):
    mappings = spec.get("trigger_partition_mappings") or ()
    if mappings:
        triggers = [row["trigger"] for row in mappings
                    if row["partition"] == obligation.get("partition")]
        if not triggers:
            return ()
    else:
        triggers = [None]
    dimension = (obligation.get("dimension")
                 if spec.get("dimension_binding") == "profile-registration"
                 else None)
    return tuple(projection.resolve_obligation_definition(
        spec, obligation.get("target"), trigger=trigger,
        dimension=dimension) for trigger in triggers)


def validated_spec(spec, *, root=None, snapshots=None):
    """Return the canonical base spec exactly named by ``spec``.

    A caller cannot pass a nearby dictionary and have this layer infer the
    intended producer family. The complete spec must equal the current
    Kernel-registry projection at the data-model level.
    """
    if not isinstance(spec, dict):
        raise AuditProducerChainError(
            "AuditReceipt producer-chain spec must be a mapping")
    rule_id = spec.get("owner_rule_id")
    try:
        canonical = projection.obligation_spec_for_rule(
            rule_id, root=root, snapshots=snapshots)
    except (TypeError, ValueError) as exc:
        raise AuditProducerChainError(
            "unknown AuditReceipt producer chain owner %r: %s" %
            (rule_id, exc)) from exc
    if spec != canonical:
        drift = sorted({
            field for field in set(spec) | set(canonical)
            if spec.get(field) != canonical.get(field)
        })
        raise AuditProducerChainError(
            "producer-chain spec differs from its Kernel registry in: %s" %
            ", ".join(drift))
    return deepcopy(canonical)


def validated_spec_for_obligation(obligation, *, root=None, snapshots=None):
    """Return the sole base spec that exactly produced ``obligation``."""
    if not isinstance(obligation, dict):
        raise AuditProducerChainError("AuditPlan obligation must be a mapping")
    rule_id = obligation.get("owner_rule_id")
    try:
        spec = projection.obligation_spec_for_rule(
            rule_id, root=root, snapshots=snapshots)
        candidates = _definition_candidates(spec, obligation)
    except (TypeError, ValueError) as exc:
        raise AuditProducerChainError(
            "unknown AuditReceipt producer chain owner %r: %s" %
            (rule_id, exc)) from exc
    matches = [candidate for candidate in candidates
               if all(obligation.get(field) == value
                      for field, value in candidate.items())]
    if not matches:
        drift = sorted({
            field for candidate in candidates
            for field, value in candidate.items()
            if obligation.get(field) != value
        })
        detail = (" in: %s" % ", ".join(drift)) if drift else ""
        raise AuditProducerChainError(
            "obligation differs from its registered producer-chain spec%s" %
            detail)
    if any(candidate != matches[0] for candidate in matches[1:]):
        raise AuditProducerChainError(
            "obligation has an ambiguous registered producer-chain spec")
    return deepcopy(spec)


def finalizer_capability_for_spec(spec):
    """Derive the terminal producer from the registered evidence kind."""
    if spec.get("evidence_kind") != lifecycle.AUDIT_RECEIPT_RECORD_KIND:
        raise AuditProducerChainError(
            "producer chain does not terminate in an AuditReceipt")
    return FINAL_AUDIT_RECEIPT_CAPABILITY


def _registered_producer(capability_id, capability_document, *, root=None):
    # ``root`` is the adopting repository whose frozen Kernel projection is
    # being validated. The executable capability registry belongs to this
    # installed Tool package, so it resolves from the module's source root
    # rather than assuming every read-only fixture mirrors the Tool tree.
    del root
    try:
        entry = capabilities.capability_entry_by_id(
            capability_id, document=capability_document)
        tool = capabilities.capability_invocation_tool(
            capability_id, document=capability_document)
    except (TypeError, ValueError) as exc:
        raise AuditProducerChainError(
            "producer capability %r has no unique public entrypoint: %s" %
            (capability_id, exc)) from exc
    if not isinstance(entry, dict) or entry.get("kind") != "producer":
        raise AuditProducerChainError(
            "producer capability %r is not registered exactly once" %
            capability_id)
    return entry, tool


def _record_contract(spec, *, root=None, snapshots=None):
    """Return execution route and intermediate shape from its sole owner."""
    source = spec.get("source_registry")
    if source == projection.SUBSTANTIVE_REGISTRY_PATH:
        contract = substantive.load_contract(root, snapshots=snapshots)
        substantive.validate_contract(contract)
        return "substantive-review", contract["record_kind"]
    if source == projection.CHANGED_SCOPE_REGISTRY_PATH:
        if spec.get("owner_rule_id") == \
                "k12-02-rendering-verification-record":
            contract = rendering.load_contract(root, snapshots=snapshots)
            rendering.validate_contract(contract)
            return "rendering-verification", contract["record_kind"]
        return ("deterministic-audit-precursor",
                lifecycle.CHANGED_SCOPE_PRECURSOR_RECORD_KIND)
    raise AuditProducerChainError(
        "registered AuditReceipt spec has no installed precursor record "
        "contract")


def precursor_chain_for_spec(spec, *, root=None, snapshots=None):
    """Resolve one validated precursor and its derived finalizer."""
    spec = validated_spec(spec, root=root, snapshots=snapshots)
    capability_id = spec.get("producer_capability")
    if capability_id is None or spec.get("producer_gate_id") is not None:
        raise AuditProducerChainError(
            "AuditReceipt obligation does not freeze one precursor capability")
    finalizer = finalizer_capability_for_spec(spec)
    if capability_id == finalizer:
        raise AuditProducerChainError(
            "AuditPlan freezes the finalizer instead of the actual producer")
    # Precursor and finalizer must resolve from the same installed capability
    # registry snapshot.  Reopening the file between these lookups could join
    # identities from two revisions into a chain that never existed.
    capability_document = capabilities.load_operation_capabilities()
    _entry, tool = _registered_producer(
        capability_id, capability_document, root=root)
    _registered_producer(finalizer, capability_document, root=root)
    route, record_kind = _record_contract(
        spec, root=root, snapshots=snapshots)
    chain = {
        "execution_route": route,
        "final_evidence_kind": spec["evidence_kind"],
        "final_producer_capability": finalizer,
        "precursor_record_kind": record_kind,
        "precursor_tool": tool,
        "precursor_capability": capability_id,
        "precursor_check": spec["producer_check"],
    }
    if tuple(chain) != _CHAIN_FIELDS:
        raise AssertionError("AuditReceipt producer-chain fields drifted")
    return chain


def precursor_chain_for_obligation(obligation, *, root=None,
                                    snapshots=None):
    """Validate a frozen obligation and resolve its complete producer chain."""
    spec = validated_spec_for_obligation(
        obligation, root=root, snapshots=snapshots)
    return precursor_chain_for_spec(
        spec, root=root, snapshots=snapshots)


def precursor_record_matches(record, chain):
    """Return whether a record has the exact registered producer identity."""
    return (isinstance(record, dict) and isinstance(chain, dict) and
            record.get("record_kind") == chain.get("precursor_record_kind") and
            record.get("tool") == chain.get("precursor_tool") and
            record.get("check") == chain.get("precursor_check"))


def require_precursor_record(record, obligation, *, root=None,
                             snapshots=None):
    """Return the chain or reject evidence from another registered producer."""
    chain = precursor_chain_for_obligation(
        obligation, root=root, snapshots=snapshots)
    if not precursor_record_matches(record, chain):
        raise AuditProducerChainError(
            "producer evidence does not match the registered precursor chain")
    return chain


__all__ = [
    'AuditProducerChainError',
    'FINAL_AUDIT_RECEIPT_CAPABILITY',
    'precursor_chain_for_obligation',
    'precursor_chain_for_spec',
    'precursor_record_matches',
    'require_precursor_record',
]
