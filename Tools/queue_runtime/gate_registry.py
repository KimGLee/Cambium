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
import kblib

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


# K12/07 fixes these seven base receipt dimensions and K12/08 / K12/18 file
# every judgment item and Gate under one of them.  Like the Kxx numbers this
# only projects a closed kernel set into the checker; `check_proof` carries the
# same projection for the Terminal Proof, and a test asserts the two agree.
BASE_RECEIPT_DIMENSIONS = frozenset((
    "structure_and_links", "content_and_depth", "formula_and_numeric",
    "source_and_currentness", "coverage_and_integration", "rendering",
    "guidance_and_contract",
))
# The two Dimension cells that are not a dimension: `none` says the Gate's
# receipt carries no `dimension` because its members hold the verdicts, and
# `*` says a named producer's identity already fixes what its receipt means.
UNDIMENSIONED_GATE = "none"
UNNARROWED_GATE_DIMENSION = "*"
# The two Lifecycle cells that are not a batch lifecycle state.  Both name a
# position the same way a batch state does, so the partition stays one rule:
# `not-batch-scoped` is the position every batch is always at, because the
# Gate's producer takes no batch and nothing about the Queue constrains it;
# `queue-exhausted` is the position reached only once the Queue holds no
# non-terminal batch, which is ahead of every live batch and behind none.
NOT_BATCH_SCOPED_GATE = "not-batch-scoped"
QUEUE_EXHAUSTED_GATE = "queue-exhausted"
UNSCOPED_GATE_POSITIONS = frozenset((NOT_BATCH_SCOPED_GATE,
                                     QUEUE_EXHAUSTED_GATE))


STANDARDS_GATE_REGISTRY_PATH = \
    "kernel/K00 Standards Control/12 Control Registry.md"


STANDARDS_REVALIDATION_CAPABILITY_HEADING = \
    "Standards Revalidation Capability Registry"
STANDARDS_REVALIDATION_CAPABILITY_ROLES = frozenset((
    "special-owner", "immediate-owner", "native-owner", "semantic-leaf",
    "mechanism-only", "unsupported", "advisory",
))
STANDARDS_REVALIDATION_CAPABILITY_EDGES = frozenset((
    "after-image-admission", "adoption-commit", "native-transition",
    "project-to-owner", "mechanism-input-only", "advisory-only", "none",
))
STANDARDS_REVALIDATION_SCOPE_PROTOCOLS = frozenset((
    "profile-after-image", "runtime-after-image", "native-owner-scope",
    "inherit-owner-scope", "diagnostic-scope", "none",
))
STANDARDS_REVALIDATION_BINDING_PROTOCOLS = frozenset((
    "profile-fingerprints", "runtime-state-fingerprints",
    "native-owner-receipt", "owner-member-chain", "not-authorizing",
))
STANDARDS_REVALIDATION_ROLE_CONTRACTS = {
    "special-owner": (
        "after-image-admission", "profile-after-image",
        "profile-fingerprints"),
    "immediate-owner": (
        "adoption-commit", "runtime-after-image",
        "runtime-state-fingerprints"),
    "native-owner": (
        "native-transition", "native-owner-scope",
        "native-owner-receipt"),
    "semantic-leaf": (
        "project-to-owner", "inherit-owner-scope", "owner-member-chain"),
    "mechanism-only": (
        "mechanism-input-only", "none", "not-authorizing"),
    "unsupported": ("none", "none", "not-authorizing"),
    "advisory": (
        "advisory-only", "diagnostic-scope", "not-authorizing"),
}


# --- Registered producer identity -------------------------------------------
# K00/12 registers one producer tuple per Gate ID and K12/17 requires every
# receipt offered for that Gate to carry it exactly.  Nothing deterministic
# used to compare the registered tuple against the producer that actually
# writes it, so a `Check` or `Mode` cell could disagree with its tool and the
# only symptom would be a receipt that silently misses every boundary it was
# recorded for.  The two tables below give the comparison its second source.
#
# `Check` for a Gate whose producer module does not export the name itself.
# The value is the one this module's own consumers compare a receipt against,
# so a drift is caught exactly where it would reject the receipt.  A module
# that later exports `GATE_CHECK` wins, and the two are required to agree.
CONSUMED_GATE_CHECKS = {
    "profile-load": "profile-check-summary",
    "terminal-proof": "proof-check-summary",
    "registered-residual-content": "residual-content-summary",
}
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
    """Parse the canonical Gate ID -> receipt predicate registry.

    K00/12 owns the table.  Plans cannot invent an opaque gate name: every
    affected/required gate must resolve to one stable producer identity that
    the revalidation aggregator can check without interpreting prose.
    """
    errors = []
    registry = {}
    try:
        path = kblib.repository_path(
            root, STANDARDS_GATE_REGISTRY_PATH, must_exist=True,
            reject_symlink=True)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, ["Gate ID registry is unsafe or unreadable: %s" % exc]
    inside = False
    seen_section = 0
    for line in text.splitlines():
        heading = re.match(r"^(#{2,3})\s+(.*?)\s*#*\s*$", line)
        if heading:
            is_registry = heading.group(2).strip() == "Stable Gate ID Registry"
            if is_registry:
                seen_section += 1
            inside = is_registry and seen_section == 1
            continue
        if not inside or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if cells == ["Gate ID", "Tool", "Tool version", "Check", "Mode",
                     "Dimension", "Lifecycle"]:
            continue
        if cells and all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) != 7:
            errors.append("Stable Gate ID Registry row must have seven cells")
            continue
        gate_id, tool, tool_version, check, mode, dimension, lifecycle = cells
        if not all(nonempty_string(value) for value in cells):
            errors.append("Stable Gate ID Registry row has an empty cell")
            continue
        if "*" in (tool, tool_version, check):
            errors.append(
                "Stable Gate ID Registry Tool, Tool version, and Check must "
                "be exact for %s; only Mode may use *" % gate_id)
            continue
        if gate_id in registry:
            errors.append("Stable Gate ID Registry repeats %s" % gate_id)
            continue
        # The Dimension cell is a list, so it is tokenized rather than taken
        # whole: a Gate whose canonical gate files verdicts under several
        # dimensions registers all of them, and the consumer narrows to the
        # one its obligation names.
        dimensions = tuple(sorted({
            token.strip().strip("`")
            for token in re.split(r"[,\s]+", dimension) if token.strip()
        }))
        # The Lifecycle cell is tokenized the same way: a producer that
        # genuinely accepts several batch positions registers all of them.
        # It is not part of the receipt selector -- it says when the Gate can
        # be produced, not which receipt satisfies it -- so it is validated
        # here rather than in the producer-tuple agreement check.
        lifecycle_states = tuple(sorted({
            token.strip().strip("`")
            for token in re.split(r"[,\s]+", lifecycle) if token.strip()
        }))
        unknown_states = sorted(
            set(lifecycle_states) - set(kblib.BATCH_LIFECYCLE_TRANSITIONS) -
            UNSCOPED_GATE_POSITIONS)
        if unknown_states:
            errors.append(
                "Gate ID %s registers Lifecycle %s, which is neither a batch "
                "lifecycle state nor one of %s" % (
                    gate_id, ", ".join(unknown_states),
                    ", ".join(sorted(UNSCOPED_GATE_POSITIONS))))
            continue
        marker = sorted(set(lifecycle_states) & UNSCOPED_GATE_POSITIONS)
        if marker and len(lifecycle_states) != 1:
            errors.append(
                "Gate ID %s registers Lifecycle %s, which mixes %s with "
                "another position" % (
                    gate_id, ", ".join(lifecycle_states), marker[0]))
            continue
        registry[gate_id] = {
            "tool": tool,
            "tool_version": tool_version,
            "check": check,
            "mode": mode,
            "dimensions": dimensions,
            "lifecycle_states": lifecycle_states,
        }
    if seen_section != 1:
        errors.append("K00/12 must contain exactly one Stable Gate ID Registry")
    if not registry:
        errors.append("Stable Gate ID Registry has no gate rows")
    errors.extend(gate_registry_producer_errors(registry))
    return registry, errors


def standards_revalidation_capabilities(root, gate_registry=None):
    """Parse the closed Gate leaf-to-owner capability registry in K00/12.

    The Stable Gate ID Registry answers which receipt identifies a Gate and
    where its producer can run.  It does *not* answer whether a raw receipt is
    allowed to authorize a Standards-adoption boundary.  Keeping that second
    question in its own closed table prevents a semantic leaf from becoming a
    boundary authority merely because both happen to use the word ``Gate``.

    Every stable Gate occurs exactly once.  The role fixes the remaining four
    cells, and every semantic leaf points to a real native owner.  This makes
    the planner -> owner -> transition path machine-checkable before an
    adoption writes state.
    """
    errors = []
    capabilities = {}
    if gate_registry is None:
        gate_registry, gate_errors = standards_gate_registry(root)
        errors.extend(gate_errors)
    try:
        path = kblib.repository_path(
            root, STANDARDS_GATE_REGISTRY_PATH, must_exist=True,
            reject_symlink=True)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, errors + [
            "Standards revalidation capability registry is unsafe or "
            "unreadable: %s" % exc]

    inside = False
    seen_section = 0
    expected_header = [
        "Gate ID", "Role", "Owner", "Claim edge", "Scope protocol",
        "Binding protocol",
    ]
    for line in text.splitlines():
        heading = re.match(r"^(#{2,3})\s+(.*?)\s*#*\s*$", line)
        if heading:
            is_registry = heading.group(2).strip() == \
                STANDARDS_REVALIDATION_CAPABILITY_HEADING
            if is_registry:
                seen_section += 1
            inside = is_registry and seen_section == 1
            continue
        if not inside or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("`")
                 for cell in line.strip().strip("|").split("|")]
        if cells == expected_header:
            continue
        if cells and all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) != 6:
            errors.append(
                "Standards Revalidation Capability Registry row must have "
                "six cells")
            continue
        gate_id, role, owner, edge, scope, binding = cells
        if not all(nonempty_string(value) for value in cells):
            errors.append(
                "Standards Revalidation Capability Registry row has an "
                "empty cell")
            continue
        if gate_id in capabilities:
            errors.append(
                "Standards Revalidation Capability Registry repeats %s" %
                gate_id)
            continue
        if role not in STANDARDS_REVALIDATION_CAPABILITY_ROLES:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Role %s" %
                (gate_id, role))
            continue
        if edge not in STANDARDS_REVALIDATION_CAPABILITY_EDGES:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Claim edge "
                "%s" % (gate_id, edge))
            continue
        if scope not in STANDARDS_REVALIDATION_SCOPE_PROTOCOLS:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Scope "
                "protocol %s" % (gate_id, scope))
            continue
        if binding not in STANDARDS_REVALIDATION_BINDING_PROTOCOLS:
            errors.append(
                "Gate ID %s has unknown Standards revalidation Binding "
                "protocol %s" % (gate_id, binding))
            continue
        expected_contract = STANDARDS_REVALIDATION_ROLE_CONTRACTS[role]
        if (edge, scope, binding) != expected_contract:
            errors.append(
                "Gate ID %s Role %s requires Claim edge / Scope protocol / "
                "Binding protocol %s / %s / %s, found %s / %s / %s" % (
                    gate_id, role, *expected_contract, edge, scope, binding))
            continue
        capabilities[gate_id] = {
            "role": role,
            "owner": owner,
            "claim_edge": edge,
            "scope_protocol": scope,
            "binding_protocol": binding,
        }

    if seen_section != 1:
        errors.append(
            "K00/12 must contain exactly one Standards Revalidation "
            "Capability Registry")
    stable_ids = set(gate_registry or {})
    capability_ids = set(capabilities)
    missing = sorted(stable_ids - capability_ids)
    extra = sorted(capability_ids - stable_ids)
    if missing:
        errors.append(
            "Standards Revalidation Capability Registry omits stable Gate "
            "ID(s): %s" % ", ".join(missing))
    if extra:
        errors.append(
            "Standards Revalidation Capability Registry names unknown Gate "
            "ID(s): %s" % ", ".join(extra))
    for gate_id, capability in sorted(capabilities.items()):
        role = capability["role"]
        owner = capability["owner"]
        if role in ("special-owner", "immediate-owner", "native-owner"):
            if owner != gate_id:
                errors.append(
                    "Standards revalidation owner Gate %s must own itself, "
                    "not %s" % (gate_id, owner))
        elif role == "semantic-leaf":
            owner_capability = capabilities.get(owner)
            if owner == gate_id or not isinstance(owner_capability, dict) or \
                    owner_capability.get("role") != "native-owner":
                errors.append(
                    "Standards revalidation semantic leaf %s must project "
                    "to a distinct native owner; found %s" %
                    (gate_id, owner))
        elif owner != "none":
            errors.append(
                "Standards revalidation Gate %s Role %s must use Owner none, "
                "not %s" % (gate_id, role, owner))
    return capabilities, errors


def standards_gate_capability_registry(root, gate_registry=None):
    """Public spelling for the Gate capability registry.

    The longer internal name predates the registry's canonical heading.  Keep
    one implementation and expose the name used by callers that reason about
    Gate identity and Gate authority as two different registries.
    """
    return standards_revalidation_capabilities(root, gate_registry)


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
    if role in ("special-owner", "immediate-owner", "native-owner"):
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
        if role == "immediate-owner":
            immediate.append(gate_id)
        elif role == "native-owner":
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
    consumed = CONSUMED_GATE_CHECKS.get(gate_id)
    if declared is not None and consumed is not None and declared != consumed:
        return None
    return declared if declared is not None else consumed


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
    closure of the one lifecycle map in ``kblib``, so this cannot disagree with
    the writer that applies the transitions.  Queue exhaustion is ahead of
    every non-terminal batch -- that batch must reach a terminal state before
    the Queue can hold none -- and behind none, because a terminal batch never
    returns to non-terminal.  A batch whose ``state`` is not a known lifecycle
    state has no reachable successor, so every Gate is due and nothing is
    waived.
    """
    due, deferred, passed = [], [], []
    known_state = state in kblib.BATCH_LIFECYCLE_TRANSITIONS
    reachable = kblib.reachable_batch_states(state)
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
    known_state = state in kblib.BATCH_LIFECYCLE_TRANSITIONS
    reachable = kblib.reachable_batch_states(state)
    for gate_id in sorted({value for value in owner_gate_ids
                           if nonempty_string(value)}):
        capability = capabilities.get(gate_id) or {}
        role = capability.get("role")
        if role == "immediate-owner":
            due.append(gate_id)
            continue
        if role != "native-owner":
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
