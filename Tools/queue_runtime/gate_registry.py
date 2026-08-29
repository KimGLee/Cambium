"""What the K00/12 Stable Gate ID Registry says about one Gate.

Which producer tuple writes it, which check name, which dimensions, which
lifecycle position it may be claimed at, and which owner it blocks.  Every
question about a Gate's identity is answered from the registry document, so
the registry stays the single statement and no module carries a second copy
of a Gate's shape.

``producer_module`` resolves a producer by name through ``importlib`` against
the Tools root.  That indirection is deliberate: it is what keeps the six
rows naming ``check_queue`` from becoming a package-to-façade import.  The
root is derived from this file's grandparent directory, not its parent --
anchoring it on the caller would find no producer from in here, and a missing
producer reads as "nothing to check".
"""

import importlib
import os
import re

import check_profile
import runtime_state_contract
from control_registry_contract import (
    BASE_RECEIPT_DIMENSIONS,
    LEGACY_STANDARDS_GATE_REGISTRY_PATH,
    NOT_BATCH_SCOPED_GATE,
    QUEUE_EXHAUSTED_GATE,
    STANDARDS_GATE_REGISTRY_PATH,
    UNDIMENSIONED_GATE,
    UNNARROWED_GATE_DIMENSION,
    UNSCOPED_GATE_POSITIONS,
    load_current_control_contract,
    parse_control_registry_document,
    parse_legacy_standards_gate_registry_markdown,
    parse_standards_gate_registry,
)

from queue_runtime.canon import (
    BATCH_CLOSE_TOOL,
    BATCH_CLOSE_TOOL_VERSION,
    BATCH_REVIEW_GATE_ID,
    CORPUS_PLAN_TOOL,
    CORPUS_PLAN_TOOL_VERSION,
    MANUAL_ATTESTATION_TOOL,
    MANUAL_ATTESTATION_TOOL_VERSION,
    STANDARDS_ADOPTION_TOOL,
    STANDARDS_ADOPTION_TOOL_VERSION,
    TERMINAL_PROOF_TOOL,
    TERMINAL_PROOF_TOOL_VERSION,
    TERMINAL_STATES,
    TOOL,
)
from queue_runtime.primitives import nonempty_string




# --- Registered producer identity -------------------------------------------
# K00/12 registers one producer tuple per Gate ID and K12/17 requires every
# receipt offered for that Gate to carry it exactly.  Nothing deterministic
# used to compare the registered tuple against the producer that actually
# writes it, so a `Check` or `Mode` cell could disagree with its tool and the
# only symptom would be a receipt that silently misses every boundary it was
# recorded for.  Producer exports and the consumer-owned identity table below
# give the comparison its source outside the registry.
#
# Gates whose receipts this module consumes against its own producer-identity
# constants.  A registry row that disagrees with one of these would register a
# producer whose receipts this consumer rejects.
CONSUMED_PRODUCER_IDENTITY = {
    "profile-load": (check_profile.TOOL, check_profile.TOOL_VERSION),
    "batch-close": (BATCH_CLOSE_TOOL, BATCH_CLOSE_TOOL_VERSION),
    "corpus-plan-structure": (CORPUS_PLAN_TOOL, CORPUS_PLAN_TOOL_VERSION),
    "terminal-proof": (TERMINAL_PROOF_TOOL, TERMINAL_PROOF_TOOL_VERSION),
    "standards-adoption": (STANDARDS_ADOPTION_TOOL,
                           STANDARDS_ADOPTION_TOOL_VERSION),
    BATCH_REVIEW_GATE_ID: (MANUAL_ATTESTATION_TOOL,
                           MANUAL_ATTESTATION_TOOL_VERSION),
}
PRODUCER_MODULE_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
# The tools root, which is this file's grandparent: a producer is a
# sibling of the tools tree, not of whichever module happens to ask.
# Anchored on the package directory instead, every lookup would find no
# producer and return None -- and a missing producer reads as "nothing
# to check", so all six K00/12 rows naming check_queue would stop being
# verified in silence.
_TOOLS_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
_PRODUCER_MODULE_CACHE = {}




def standards_gate_registry(root):
    """Load current Gate selectors and validate each installed producer."""
    registry, _capabilities, _metadata, errors = \
        load_current_control_contract(root)
    if registry:
        errors.extend(gate_registry_producer_errors(registry))
    return registry, errors


def standards_revalidation_capabilities(root, gate_registry=None):
    """Load current revalidation projections from the same Gate rows."""
    registry, capabilities, _metadata, errors = \
        load_current_control_contract(root)
    if gate_registry is not None and registry != gate_registry:
        errors.append(
            "supplied Gate registry differs from the current Control registry")
    return capabilities, errors


def standards_gate_capability_registry(root, gate_registry=None):
    """Public spelling for the current Gate capability projection."""
    return standards_revalidation_capabilities(root, gate_registry)


def is_revalidation_boundary_owner(capability):
    """Return whether one parsed capability may own a blocking boundary."""
    return isinstance(capability, dict) and capability.get("role") in (
        "special-owner", "immediate-owner", "native-owner")


def is_special_revalidation_owner(capability):
    """Return whether after-image Profile admission owns this boundary."""
    return isinstance(capability, dict) and \
        capability.get("role") == "special-owner"


def is_immediate_revalidation_owner(capability):
    """Return whether adoption commit immediately consumes this owner."""
    return isinstance(capability, dict) and \
        capability.get("role") == "immediate-owner"


def is_native_revalidation_owner(capability):
    """Return whether the ordinary transition consumes this owner."""
    return isinstance(capability, dict) and \
        capability.get("role") == "native-owner"


def standards_revalidation_owner(gate_id, capabilities):
    """Return the blocking owner of one semantic Gate, or ``None``.

    ``None`` is reserved for advisory/mechanism-only Gates that intentionally
    create no blocking claim.  Unsupported and unknown Gates raise a value
    error so a new plan cannot convert an absent capability into a waiver.
    """
    capability = capabilities.get(gate_id)
    if not isinstance(capability, dict):
        raise ValueError("Gate ID %s has no Standards revalidation capability"
                         % gate_id)
    role = capability.get("role")
    if is_revalidation_boundary_owner(capability):
        return gate_id
    if role == "semantic-leaf":
        return capability.get("owner")
    if role == "advisory":
        return None
    if role == "mechanism-only":
        raise ValueError(
            "Gate ID %s has Role mechanism-only and cannot be used as an "
            "adoption boundary Gate" % gate_id)
    raise ValueError(
        "Gate ID %s has Role unsupported and cannot be used as an adoption "
        "boundary Gate" % gate_id)


def projected_revalidation_owners(gate_ids, capabilities):
    """Project semantic Gate IDs to the exact sorted blocking owner set."""
    owners = set()
    errors = []
    for gate_id in sorted({value for value in gate_ids
                           if nonempty_string(value)}):
        try:
            owner = standards_revalidation_owner(gate_id, capabilities)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if owner is not None:
            owners.add(owner)
    return sorted(owners), errors


def project_adoption_gate_ids(gate_ids, capabilities):
    """Return the immediate and native owner closure for affected Gate IDs.

    Profile admission is evaluated against the writable after-image before an
    adoption commits, so it deliberately belongs to neither runtime list.
    Advisory observations likewise create no blocking owner.  Any unsupported
    or mechanism-only input remains an explicit error.
    """
    owners, errors = projected_revalidation_owners(gate_ids, capabilities)
    immediate = []
    native = []
    for gate_id in owners:
        role = (capabilities.get(gate_id) or {}).get("role")
        if is_immediate_revalidation_owner(capabilities.get(gate_id)):
            immediate.append(gate_id)
        elif is_native_revalidation_owner(capabilities.get(gate_id)):
            native.append(gate_id)
    return immediate, native, errors


def producer_module(tool):
    """Return the installed module a registry ``Tool`` cell names, or None.

    The producer is resolved next to this file rather than under the
    repository being checked: the module that will actually run is the one
    whose constants end up in the receipt, and an adopter's copy of the
    Standards text never redefines that identity.
    """
    if tool in _PRODUCER_MODULE_CACHE:
        return _PRODUCER_MODULE_CACHE[tool]
    module = None
    # Anchored on the Tools root, not on this file's directory.  A producer is
    # a sibling of the tools tree, not of whichever module happens to ask; if
    # this resolved relative to the caller it would find nothing from inside a
    # package and every lookup would return None -- and a missing producer is
    # read as "nothing to check", so the failure would be silent.
    if isinstance(tool, str) and PRODUCER_MODULE_RE.match(tool) and \
            os.path.isfile(os.path.join(_TOOLS_ROOT, tool + ".py")):
        try:
            module = importlib.import_module(tool)
        except Exception:  # pragma: no cover - a broken producer is an error
            module = None
    _PRODUCER_MODULE_CACHE[tool] = module
    return module


def registered_gate_check(gate_id, module):
    """Return the check name the producer of ``gate_id`` actually writes."""
    # A producer registering several Gates exports the whole mapping; the
    # single GATE_CHECK export remains the one-Gate spelling.
    mapping = getattr(module, "GATE_CHECKS", None) if module else None
    declared = None
    if isinstance(mapping, dict):
        declared = mapping.get(gate_id)
    if declared is None:
        declared = getattr(module, "GATE_CHECK", None) if module else None
    return declared


def gate_registry_producer_errors(registry):
    """Return every K00/12 row whose producer tuple its producer contradicts.

    All five selector columns are compared against a source outside the table:

    * ``Tool`` names either the ``manual-attestation`` producer class or an
      installed module whose ``TOOL`` equals the cell.
    * ``Tool version`` equals that module's ``TOOL_VERSION`` -- the value it
      stamps on every receipt -- or, for a hand-recorded receipt, the single
      current ``manual-attestation`` protocol version K00/12 states.
    * ``Check`` equals the check name the producer writes for this Gate, and
      ``Gate ID`` equals the Gate the producer binds, where the module
      exports them.
    * ``Mode`` narrows on ``queue_check_mode``, a field only ``check_queue``
      writes.  A ``check_queue`` row therefore carries a mode that
      :func:`queue_gate_id_for_mode` maps back to the same Gate ID, and every
      other row carries ``*``: a narrower mode elsewhere could never match.
    * ``Dimension`` narrows on ``dimension``.  A named producer that exports
      ``GATE_DIMENSION`` must register that exact base dimension; other named
      producers carry ``*`` because they do not write the field.  A manual
      attestation may select one or more base dimensions, and ``none`` says
      the Gate's own receipt has no dimension.

    The five cells together are the receipt selector, so two Gate IDs may not
    share one tuple either.  This is a judgment, not an adjudication: the
    caller is told the two sides disagree, never which side to change.
    """
    errors = []
    selectors = {}
    for gate_id in sorted(registry):
        predicate = registry[gate_id]
        tool = predicate["tool"]
        mode = predicate["mode"]
        dimensions = predicate.get("dimensions") or ()
        module = (None if tool == MANUAL_ATTESTATION_TOOL
                  else producer_module(tool))
        declared_dimension = getattr(module, "GATE_DIMENSION", None)
        selector = (tool, predicate["tool_version"], predicate["check"], mode,
                    ",".join(dimensions))
        selectors.setdefault(selector, []).append(gate_id)
        if UNNARROWED_GATE_DIMENSION in dimensions or \
                UNDIMENSIONED_GATE in dimensions:
            if len(dimensions) != 1:
                errors.append(
                    "Gate ID %s registers Dimension %s, which mixes %r with "
                    "named dimensions" % (
                        gate_id, "/".join(dimensions), dimensions[0]))
            elif dimensions[0] == UNNARROWED_GATE_DIMENSION:
                if (tool == MANUAL_ATTESTATION_TOOL or
                        declared_dimension is not None):
                    errors.append(
                        "Gate ID %s registers Dimension %s against Tool %s, "
                        "but that producer %s" % (
                            gate_id, dimensions[0], tool,
                            "declares %s" % declared_dimension
                            if declared_dimension is not None else
                            "is manually dimensioned"))
            elif tool != MANUAL_ATTESTATION_TOOL:
                errors.append(
                    "Gate ID %s registers Dimension none against named "
                    "producer %s%s" % (
                        gate_id, tool,
                        ", which declares %s" % declared_dimension
                        if declared_dimension is not None else ""))
        else:
            unknown = sorted(set(dimensions) - BASE_RECEIPT_DIMENSIONS)
            if unknown:
                errors.append(
                    "Gate ID %s registers Dimension %s, which K12/07 does not "
                    "fix as a base receipt dimension" % (
                        gate_id, ", ".join(unknown)))
            if tool != MANUAL_ATTESTATION_TOOL:
                if declared_dimension is None:
                    errors.append(
                        "Gate ID %s narrows Dimension to %s, but its producer "
                        "%s writes no dimension field" % (
                            gate_id, ", ".join(dimensions), tool))
                elif dimensions != (declared_dimension,):
                    errors.append(
                        "Gate ID %s registers Dimension %s but producer %s "
                        "emits %s" % (
                            gate_id, ", ".join(dimensions), tool,
                            declared_dimension))
        consumed = CONSUMED_PRODUCER_IDENTITY.get(gate_id)
        if consumed is not None and consumed != (tool,
                                                 predicate["tool_version"]):
            errors.append(
                "Gate ID %s registers producer %s/%s but this checker "
                "consumes its receipts as %s/%s" % (
                    gate_id, tool, predicate["tool_version"], *consumed))
        if tool == TOOL:
            probe = mode[:-1] if mode.endswith("*") else mode
            if queue_gate_id_for_mode(probe) != gate_id:
                errors.append(
                    "Gate ID %s registers Mode %s, which %s does not emit for "
                    "that Gate" % (gate_id, mode, TOOL))
        elif mode != "*":
            errors.append(
                "Gate ID %s registers Mode %s, but only %s receipts carry "
                "queue_check_mode" % (gate_id, mode, TOOL))
        if tool == MANUAL_ATTESTATION_TOOL:
            if predicate["tool_version"] != MANUAL_ATTESTATION_TOOL_VERSION:
                errors.append(
                    "Gate ID %s registers manual-attestation protocol version "
                    "%s, not the current %s" % (
                        gate_id, predicate["tool_version"],
                        MANUAL_ATTESTATION_TOOL_VERSION))
            continue
        if module is None or getattr(module, "TOOL", None) != tool:
            errors.append(
                "Gate ID %s registers Tool %s, which is not an installed "
                "producer of that name" % (gate_id, tool))
            continue
        if getattr(module, "TOOL_VERSION", None) != predicate["tool_version"]:
            errors.append(
                "Gate ID %s registers Tool version %s but %s stamps %s" % (
                    gate_id, predicate["tool_version"], tool,
                    getattr(module, "TOOL_VERSION", None)))
        declared_gate = getattr(module, "GATE_ID", None)
        declared_gates = getattr(module, "GATE_CHECKS", None)
        admitted = (isinstance(declared_gates, dict) and
                    gate_id in declared_gates)
        if (declared_gate is not None and tool != TOOL and
                declared_gate != gate_id and not admitted):
            errors.append(
                "Gate ID %s registers Tool %s, which binds %s to its receipts"
                % (gate_id, tool, declared_gate))
        expected_check = registered_gate_check(gate_id, module)
        if expected_check is None:
            errors.append(
                "Gate ID %s registers Check %s against %s, which declares no "
                "check name for it" % (gate_id, predicate["check"], tool))
        elif expected_check != predicate["check"]:
            errors.append(
                "Gate ID %s registers Check %s but %s writes %s" % (
                    gate_id, predicate["check"], tool, expected_check))
    for selector, gate_ids in sorted(selectors.items()):
        if len(gate_ids) > 1:
            errors.append(
                "Gate IDs %s share one receipt selector %s" % (
                    ", ".join(gate_ids), "/".join(selector)))
    return errors


def registered_gate_dimensions(gate_id, registry):
    """Return the receipt dimensions K00/12 admits for ``gate_id``.

    ``None`` means the row is not narrowed on dimension at all.  An empty
    frozenset means the Gate's receipt carries no ``dimension`` field.
    """
    predicate = registry.get(gate_id)
    if not isinstance(predicate, dict):
        return None
    dimensions = predicate.get("dimensions") or ()
    if UNNARROWED_GATE_DIMENSION in dimensions:
        return None
    if dimensions == (UNDIMENSIONED_GATE,):
        return frozenset()
    return frozenset(dimensions)


def registered_gate_position(gate_id, registry):
    """Return the position K00/12 registers ``gate_id``'s producer for.

    One of three forms, matching the three forms of the Lifecycle cell:

    * ``None`` -- unpositioned.  The producer takes no batch and nothing about
      the Queue constrains it, so every batch is always at this position.  An
      unregistered Gate ID answers the same way, which is the fail-closed
      answer here: an unknown Gate is treated as producible now and therefore
      still owed a receipt, which the registry match then rejects.
    * ``QUEUE_EXHAUSTED_GATE`` -- the position the Queue reaches when it holds
      no non-terminal batch.
    * a ``frozenset`` of batch lifecycle states -- the positions of the batch
      itself at which the producer runs.
    """
    predicate = registry.get(gate_id)
    if not isinstance(predicate, dict):
        return None
    states = predicate.get("lifecycle_states") or ()
    if not states or NOT_BATCH_SCOPED_GATE in states:
        return None
    if QUEUE_EXHAUSTED_GATE in states:
        return QUEUE_EXHAUSTED_GATE
    return frozenset(states)


def partition_boundary_gates_by_lifecycle(gate_ids, state, registry):
    """Split boundary Gate IDs by where a batch at ``state`` can claim them.

    A boundary's required gates are claimed at the transition each one belongs
    to, not all at once when a hold is discharged.  Every Gate ID has one
    registered position; judged against one target batch's own position, it
    falls in exactly one of three sets:

    * **due** -- the batch is at that position now, so the gate can be
      produced and its receipt is required by the revalidation aggregate.  An
      unpositioned Gate is always due.
    * **deferred** -- the position is still ahead of the batch, so the gate is
      claimed at the transition that reaches it.  That transition already
      requires the gate natively, so nothing new enforces this.
    * **passed** -- the position is behind the batch and no sanctioned
      transition returns to it, so the evidence cannot be remade.  The batch
      proceeds carrying what it has, recorded as unrepeatable.

    The comparison is the same question for all three kinds of position; only
    how "ahead" is read differs.  For a batch-state position it is the forward
    closure of the Kernel-owned runtime state model, so this cannot disagree
    with the writer that applies the transitions. Queue exhaustion is ahead
    of every non-terminal batch -- that batch must reach a terminal state
    before the Queue can hold none -- and behind none, because a terminal
    batch never returns to non-terminal. A batch whose ``state`` is not a
    known lifecycle state has no reachable successor, so every Gate is due
    and nothing is waived.
    """
    due, deferred, passed = [], [], []
    known_state = state in runtime_state_contract.QUEUE_STATES
    reachable = runtime_state_contract.reachable_batch_states(state)
    for gate_id in sorted({value for value in gate_ids
                           if nonempty_string(value)}):
        position = registered_gate_position(gate_id, registry)
        if position is None or not known_state:
            due.append(gate_id)
        elif position == QUEUE_EXHAUSTED_GATE:
            (due if state in TERMINAL_STATES else deferred).append(gate_id)
        elif state in position:
            due.append(gate_id)
        elif position & reachable:
            deferred.append(gate_id)
        else:
            passed.append(gate_id)
    return due, deferred, passed


def partition_revalidation_owner_claims(owner_gate_ids, state, registry,
                                        capabilities):
    """Partition owner Gates by their *claim edge*, not producer availability.

    K00/12 Lifecycle says where a producer accepts an invocation.  A native
    transition Gate may accept one while the batch is queued/open/merge-ready,
    but a Standards hold must not demand it in the source state: the receipt
    belongs to the transition itself, after the hold has cleared.  Conflating
    those two facts made ``required-queue-admission`` due while its own
    producer refused a held batch and made semantic leaf checks block content
    before the lifecycle allowed content to be repaired.

    Immediate owners are the only raw receipts due in the aggregate.  Native
    owners at their position or ahead are deferred to their mandatory edge;
    an owner whose edge the batch already passed is unrepeatable here and a
    current plan is refused before it can create such a claim.
    """
    due, deferred, passed = [], [], []
    known_state = state in runtime_state_contract.QUEUE_STATES
    reachable = runtime_state_contract.reachable_batch_states(state)
    for gate_id in sorted({value for value in owner_gate_ids
                           if nonempty_string(value)}):
        capability = capabilities.get(gate_id) or {}
        role = capability.get("role")
        if is_immediate_revalidation_owner(capability):
            due.append(gate_id)
            continue
        if not is_native_revalidation_owner(capability):
            # A malformed projection is due so the exact receipt set cannot
            # silently shrink.  The capability error reported alongside it
            # explains why no receipt can satisfy the claim.
            due.append(gate_id)
            continue
        position = registered_gate_position(gate_id, registry)
        if position is None or not known_state:
            passed.append(gate_id)
        elif position == QUEUE_EXHAUSTED_GATE:
            (passed if state in TERMINAL_STATES else deferred).append(gate_id)
        elif state in position or position & reachable:
            deferred.append(gate_id)
        else:
            passed.append(gate_id)
    return due, deferred, passed


def receipt_matches_gate_id(receipt, gate_id, registry, dimension=None):
    """Return whether one receipt satisfies the registered producer tuple.

    ``dimension``, when given, is the single receipt dimension the consumer's
    own obligation was raised in.  A Gate ID whose canonical gate files
    verdicts under several dimensions -- `content-correctness` and `rendering`
    are the live cases -- is not identified by the producer tuple alone: every
    dimension's attestation carries the same tool, version, check, and mode,
    so without this argument evidence re-established in one dimension
    discharges an obligation raised in another.
    """
    predicate = registry.get(gate_id)
    if not isinstance(receipt, dict) or not isinstance(predicate, dict):
        return False
    # A new revalidation aggregate never infers identity from descriptive
    # fields.  Every raw input must bind the registry key explicitly.  Older
    # receipts without ``gate_id`` remain available to historical validators,
    # but this function is a current-action predicate and must reject them.
    if receipt.get("gate_id") != gate_id:
        return False
    if predicate["tool"] != "*" and receipt.get("tool") != predicate["tool"]:
        return False
    if (predicate["tool_version"] != "*" and
            receipt.get("tool_version") != predicate["tool_version"]):
        return False
    if predicate["check"] != "*" and receipt.get("check") != predicate["check"]:
        return False
    registered = registered_gate_dimensions(gate_id, registry)
    if registered is not None:
        actual_dimension = receipt.get("dimension")
        if registered:
            # A missing field is a rejection, not a wildcard: an attestation
            # that never said which dimension it filed under has not been
            # narrowed by anyone, and reading silence as agreement is exactly
            # the hole this closes.
            if actual_dimension not in registered:
                return False
        elif actual_dimension is not None:
            return False
        if dimension is not None and actual_dimension != dimension:
            return False
    expected_mode = predicate["mode"]
    if expected_mode == "*":
        return True
    actual_mode = receipt.get("queue_check_mode")
    if expected_mode.endswith("*"):
        return isinstance(actual_mode, str) and actual_mode.startswith(
            expected_mode[:-1])
    return actual_mode == expected_mode


def queue_gate_id_for_mode(mode):
    """Return the stable Gate ID for a gate-producing Queue mode."""
    if mode == "consistency":
        return "required-queue-consistency"
    if isinstance(mode, str) and mode.startswith("require-ready:"):
        return "required-queue-admission"
    if isinstance(mode, str) and mode.startswith("require-revalidation:"):
        return "standards-revalidation"
    if mode == "require-complete":
        return "required-queue-completion"
    if mode == "require-maintenance-complete":
        return "maintenance-completion"
    if mode == "resume-status":
        return "runtime-startup-recovery"
    return None
