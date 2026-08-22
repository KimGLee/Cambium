"""Compile and validate Card-first execution-context deliveries.

This module owns no lifecycle state and writes no receipt.  It turns the
already-frozen Task Contract plus one queued batch into a content-addressed
activation bundle.  ``check_queue`` carries that bundle in its admission
receipt/tool result; ``update_queue`` independently recompiles it before the
``queued -> open`` edge.  A host transport may bind the delivery to one
execution context through ``CAMBIUM_EXECUTION_CONTEXT_ID``.

Runtime Cards are the startup payload.  Sources deliberately left in a Card's
``readback_sources`` become either startup payloads (the Card declares
``readback_policy: activation``) or individually addressable declared
addenda.  Kernel source remains authoritative; this module merely makes the
delivery boundary exact and observable.
"""

import os
import re

import kblib


# v1 delivered the Card Bundle alone.  v2 additionally freezes the Profile's
# Batch Review Requirement expansion at admission and carries its set hash, so
# `open` can bind the exact judgment obligations the batch was activated with.
# Sealed v1 receipts replay under their own era and never gain the field.
# v3 stops embedding Card and read-back bytes in the admission result.  A
# host that externalizes an oversized tool result leaves the payload outside
# the model context while the receipt still claims delivery, and nothing in
# v1/v2 could detect that divergence.  v3 therefore freezes a small piece
# manifest at admission, delivers one file per tool result inside a protocol
# byte budget, and leaves `machine-delivery-complete` to be earned by the
# Assignment delivery gate rather than asserted here.
# v4 keeps every v3 commitment and moves one thing: *when* a frozen piece
# travels.  v3 owed the whole task's route union before `running`, so a
# single-page corrective batch paid for the governance route it never
# entered.  v4 freezes the same identities at the same moment -- plus the
# phase each belongs to and the environment they were resolved under -- and
# delivers one phase at a time, each phase gate still an exact set equality.
ACTIVATION_PROTOCOL = "card-first-phased-readback-v4"
V3_ACTIVATION_PROTOCOL = "card-first-readback-v3"
V2_ACTIVATION_PROTOCOL = "card-first-readback-v2"
LEGACY_ACTIVATION_PROTOCOL = "card-first-readback-v1"
SUPPORTED_ACTIVATION_PROTOCOLS = frozenset((
    LEGACY_ACTIVATION_PROTOCOL, V2_ACTIVATION_PROTOCOL,
    V3_ACTIVATION_PROTOCOL, ACTIVATION_PROTOCOL))
EMBEDDED_PAYLOAD_PROTOCOLS = frozenset((
    LEGACY_ACTIVATION_PROTOCOL, V2_ACTIVATION_PROTOCOL))
# Protocols that carry a frozen piece manifest and deliver it afterwards.
PIECE_DELIVERY_PROTOCOLS = frozenset((
    V3_ACTIVATION_PROTOCOL, ACTIVATION_PROTOCOL))
# Protocols that additionally partition that manifest into phases.
PHASED_PROTOCOLS = frozenset((ACTIVATION_PROTOCOL,))
PIECE_PROTOCOL = "activation-piece-v1"
PIECE_ACK_PROTOCOL = "activation-piece-ack-v1"
PHASE_PLAN_PROTOCOL = "phase-plan-v1"
PHASE_DELIVERY_PROTOCOL = "activation-phase-v1"
PHASE_ACK_PROTOCOL = "activation-phase-ack-v1"
# The resolver identity travels in the frozen environment: a later phase is
# materialized by whatever build is running then, so replay needs to know
# which rule set produced the plan it is replaying.
PHASE_RESOLVER_VERSION = "phase-resolver-1.0.0"

# Phase closed set.  Two layers: three batch phases every batch walks, and
# two task-level conditional phases only a real transition enters.
PHASE_BATCH_PREFLIGHT = "batch-preflight"
PHASE_BATCH_RUNNING = "batch-running"
PHASE_BATCH_GATE = "batch-gate"
PHASE_GOVERNANCE = "governance"
PHASE_TASK_COMPLETION = "task-completion"
PHASE_ORDER = (
    PHASE_BATCH_PREFLIGHT, PHASE_BATCH_RUNNING, PHASE_BATCH_GATE,
    PHASE_GOVERNANCE, PHASE_TASK_COMPLETION,
)
PHASES = frozenset(PHASE_ORDER)
# A conditional phase is materialized only when its predicate holds; its
# pieces are frozen at admission either way, so entering one later proves
# what it always would have been rather than resolving it afresh.
CONDITIONAL_PHASES = frozenset((PHASE_GOVERNANCE, PHASE_TASK_COMPLETION))
# A standard phase must fit one part.  Needing two is not a transport
# accident to route around; it means the phase set was cut too wide.
STANDARD_PHASES = frozenset((PHASE_BATCH_PREFLIGHT, PHASE_BATCH_GATE))
PHASE_TRIGGERS = {
    PHASE_BATCH_PREFLIGHT: "batch admitted (queued -> open)",
    PHASE_BATCH_RUNNING: "route or read-back condition declared during work",
    PHASE_BATCH_GATE: "first judgment or merge-ready request",
    PHASE_GOVERNANCE: "in-batch Standards governance transition",
    PHASE_TASK_COMPLETION: "completion-candidate task transition",
}
# Routes whose phase is fixed by what the route is for, not by the batch.
# R01 is every task's common boundary; the other three are the routes their
# own Cards say ordinary work must not enter implicitly.
ROUTE_PHASE_OVERRIDES = {
    "R01": PHASE_BATCH_PREFLIGHT,
    "R08": PHASE_TASK_COMPLETION,
    "R09": PHASE_GOVERNANCE,
    "R12": PHASE_BATCH_GATE,
}
# One delivered piece must fit one tool result.  The measured object is the
# canonical serialization of the whole delivery, not the source file: the
# 2026-08-22 host measurement saw 50,495 bytes of Card source arrive as a
# 231,164-byte result, so envelope overhead exceeded the payload itself.
MAX_ACTIVATION_PIECE_ENVELOPE_BYTES = 49152
PIECE_KINDS = frozenset(("card", "activation-readback"))
BATCH_REVIEW_PLAN_PROTOCOL = "batch-review-plan-v1"
READBACK_PROTOCOL = "card-readback-addendum-v1"
EXECUTION_CONTEXT_ENV = "CAMBIUM_EXECUTION_CONTEXT_ID"
CARD_INDEX_PATH = "kernel/Cards/Card Index.md"
SHA12_RE = re.compile(r"[0-9a-f]{12}")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
READBACK_POLICIES = frozenset(("none", "declared", "activation"))
LEGACY_ACTIVATION_CONTEXT_FIELDS = (
    "activation_protocol", "task_contract_sha256", "reading_plan_sha256",
    "readback_plan_sha256", "card_bundle_sha256",
    "activation_bundle_manifest", "delivery_mode", "delivery_assurance",
    "execution_context_id",
)
ACTIVATION_CONTEXT_FIELDS = (
    "activation_protocol", "task_contract_sha256", "reading_plan_sha256",
    "readback_plan_sha256", "review_requirement_set_sha256",
    "card_bundle_sha256",
    "activation_bundle_manifest", "delivery_mode", "delivery_assurance",
    "execution_context_id",
)
PHASED_ACTIVATION_CONTEXT_FIELDS = (
    "activation_protocol", "task_contract_sha256", "reading_plan_sha256",
    "readback_plan_sha256", "review_requirement_set_sha256",
    "phase_plan_sha256", "card_bundle_sha256",
    "activation_bundle_manifest", "delivery_mode", "delivery_assurance",
    "execution_context_id",
)
ACTIVATION_BUNDLE_FIELDS = ACTIVATION_CONTEXT_FIELDS[:7]
PHASED_ACTIVATION_BUNDLE_FIELDS = PHASED_ACTIVATION_CONTEXT_FIELDS[:8]


def activation_context_fields(context_or_protocol):
    """Return the closed field tuple for one activation era."""
    protocol = context_or_protocol
    if isinstance(context_or_protocol, dict):
        protocol = context_or_protocol.get("activation_protocol")
    if protocol == LEGACY_ACTIVATION_PROTOCOL:
        return LEGACY_ACTIVATION_CONTEXT_FIELDS
    if protocol in PHASED_PROTOCOLS:
        return PHASED_ACTIVATION_CONTEXT_FIELDS
    return ACTIVATION_CONTEXT_FIELDS


def activation_bundle_fields(context_or_protocol):
    """Return the delivery-independent commitment fields for one era."""
    protocol = context_or_protocol
    if isinstance(context_or_protocol, dict):
        protocol = context_or_protocol.get("activation_protocol")
    if protocol in PHASED_PROTOCOLS:
        return PHASED_ACTIVATION_BUNDLE_FIELDS
    return ACTIVATION_BUNDLE_FIELDS
RUNTIME_STATE_BINDING_FIELDS = (
    "required_queue_sha256", "coverage_ledger_sha256",
    "progress_ledger_sha256", "queue_revision", "queue_state_revision",
)
READBACK_CONTEXT_FIELDS = (
    "readback_protocol", "parent_card_bundle_sha256", "readback_rule_id",
    "readback_addendum_sha256", "readback_addendum_manifest", "delivery_mode",
    "delivery_assurance", "execution_context_id",
)


class ActivationError(ValueError):
    """The frozen reading plan cannot produce a trustworthy delivery."""


def _strings(value, label, *, nonempty=False):
    if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value):
        raise ActivationError("%s must be an explicit string list" % label)
    if len(value) != len(set(value)):
        raise ActivationError("%s must not repeat values" % label)
    if nonempty and not value:
        raise ActivationError("%s must not be empty at batch activation" % label)
    return list(value)


def _snapshot_text(root, relative):
    try:
        snapshot = kblib.repository_target_snapshot(
            root, relative, suffixes=(".md",))
        if not snapshot.exists:
            raise ActivationError("%s is missing" % relative)
        return snapshot, snapshot.read_text()
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ActivationError):
            raise
        raise ActivationError("%s is not a safe UTF-8 repository file: %s" %
                              (relative, exc))


def _frontmatter(text, label):
    raw = kblib.extract_frontmatter(text)
    if raw is None:
        raise ActivationError("%s has no YAML frontmatter" % label)
    try:
        value = kblib.parse_yaml_subset(raw)
    except (ValueError, kblib.YamlSubsetError) as exc:
        raise ActivationError("%s frontmatter is invalid: %s" % (label, exc))
    if not isinstance(value, dict):
        raise ActivationError("%s frontmatter must be a mapping" % label)
    return value


def _route_registry(root):
    snapshot, text = _snapshot_text(root, CARD_INDEX_PATH)
    document = _frontmatter(text, CARD_INDEX_PATH)
    if document.get("type") != "card-index":
        raise ActivationError("%s must declare type card-index" %
                              CARD_INDEX_PATH)
    rows = document.get("route_registry")
    if not isinstance(rows, list) or not rows:
        raise ActivationError("%s has no route_registry" % CARD_INDEX_PATH)
    result = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
                "route_id", "path", "read_set"}:
            raise ActivationError(
                "%s route_registry[%d] must contain only route_id, path, "
                "and read_set" % (CARD_INDEX_PATH, index))
        route_id = row.get("route_id")
        path = row.get("path")
        read_set = row.get("read_set")
        if not all(isinstance(value, str) and value
                   for value in (route_id, path, read_set)):
            raise ActivationError("%s route_registry[%d] is incomplete" %
                                  (CARD_INDEX_PATH, index))
        if route_id in result:
            raise ActivationError("%s repeats route %s" %
                                  (CARD_INDEX_PATH, route_id))
        result[route_id] = {"path": path, "read_set": read_set}
    return result, snapshot.sha256


def _contract_fingerprint(progress):
    contract = progress.get("contract") if isinstance(progress, dict) else None
    if not isinstance(contract, dict):
        raise ActivationError("Progress has no frozen Task Contract")
    try:
        fingerprint = kblib.sha256_bytes(kblib.canonical_yaml(contract))
    except (TypeError, ValueError, kblib.YamlSubsetError) as exc:
        raise ActivationError("Task Contract is not canonical: %s" % exc)
    return contract, fingerprint


def _runtime_bindings(runtime_state):
    if not isinstance(runtime_state, dict):
        raise ActivationError("activation requires one validated runtime view")
    queue = runtime_state.get("queue")
    profile = runtime_state.get("_profile_authorized_view")
    standards = runtime_state.get("_active_standards_authorized_view")
    if not all(isinstance(value, dict)
               for value in (queue, profile, standards)):
        raise ActivationError(
            "activation runtime view lacks Queue, Profile, or Standards authority")
    bindings = {
        "required_queue_sha256": runtime_state.get("queue_sha256"),
        "coverage_ledger_sha256": runtime_state.get("coverage_sha256"),
        "progress_ledger_sha256": runtime_state.get("progress_sha256"),
        "queue_revision": queue.get("queue_revision"),
        "queue_state_revision": queue.get("state_revision"),
        "active_standards_sha256": standards.get("active_standards_sha256"),
        "profile_snapshot_sha256": profile.get("profile_snapshot_sha256"),
        "profile_contract_fingerprint": profile.get(
            "profile_contract_fingerprint"),
        "profile_load_inputs_sha256": profile.get(
            "profile_load_inputs_sha256"),
    }
    for field in (
            "required_queue_sha256", "coverage_ledger_sha256",
            "progress_ledger_sha256", "active_standards_sha256",
            "profile_snapshot_sha256", "profile_contract_fingerprint",
            "profile_load_inputs_sha256"):
        if not isinstance(bindings[field], str) or not bindings[field]:
            raise ActivationError("activation runtime view lacks %s" % field)
    for field in ("queue_revision", "queue_state_revision"):
        if isinstance(bindings[field], bool) or not isinstance(
                bindings[field], int) or bindings[field] < 0:
            raise ActivationError("activation runtime view lacks %s" % field)
    return bindings


def _delivery_binding(execution_context_id=None, *, protocol=None):
    """Record what this result is, not what a later reader will receive.

    Under v1/v2 an admission that reached a bound host context claimed
    `machine-delivered` outright.  That claim was minted before the result
    left the server, so it survived a host that never put the bytes in the
    model context.  v3 records only the preparation state: `host-bound` when
    an execution context is bound, `prepared` otherwise.  Completion is
    earned per piece and recorded by the Assignment delivery gate.
    """
    context_id = execution_context_id
    if context_id is None:
        context_id = os.environ.get(EXECUTION_CONTEXT_ENV)
    bound = isinstance(context_id, str) and bool(context_id)
    if protocol in EMBEDDED_PAYLOAD_PROTOCOLS:
        if bound:
            return {
                "delivery_mode": "host-context-injection",
                "delivery_assurance": "machine-delivered",
                "execution_context_id": context_id,
            }
        return {
            "delivery_mode": "cli-tool-result",
            "delivery_assurance": "degraded",
            "execution_context_id": None,
        }
    if bound:
        return {
            "delivery_mode": "host-context-injection",
            "delivery_assurance": "host-bound",
            "execution_context_id": context_id,
        }
    return {
        "delivery_mode": "cli-tool-result",
        "delivery_assurance": "prepared",
        "execution_context_id": None,
    }


def _card_record(root, route_id, registered, declared_path):
    if declared_path != registered["path"]:
        raise ActivationError(
            "selected Card for %s is %s, registered path is %s" %
            (route_id, declared_path, registered["path"]))
    snapshot, text = _snapshot_text(root, declared_path)
    document = _frontmatter(text, declared_path)
    expected_keys = ("type", "route_id", "read_set", "source_hash",
                     "compiled_source_hash", "readback_sources",
                     "readback_policy")
    missing = [key for key in expected_keys if key not in document]
    if missing:
        raise ActivationError("%s lacks %s" %
                              (declared_path, ", ".join(missing)))
    if document.get("type") != "runtime-card":
        raise ActivationError("%s must declare type runtime-card" %
                              declared_path)
    if document.get("route_id") != route_id:
        raise ActivationError("%s route_id does not match %s" %
                              (declared_path, route_id))
    if document.get("read_set") != registered["read_set"]:
        raise ActivationError("%s read_set does not match the Card Index" %
                              declared_path)
    observed = document.get("source_hash")
    compiled = document.get("compiled_source_hash")
    if not (isinstance(observed, str) and SHA12_RE.fullmatch(observed) and
            isinstance(compiled, str) and SHA12_RE.fullmatch(compiled)):
        raise ActivationError("%s has invalid semantic source hashes" %
                              declared_path)
    if observed != compiled:
        raise ActivationError(
            "%s has unacknowledged semantic source drift (%s != %s)" %
            (declared_path, observed, compiled))
    readbacks = _strings(document.get("readback_sources"),
                         "%s readback_sources" % declared_path)
    policy = document.get("readback_policy")
    if policy not in READBACK_POLICIES:
        raise ActivationError("%s readback_policy must be one of %s" %
                              (declared_path,
                               ", ".join(sorted(READBACK_POLICIES))))
    if (not readbacks and policy != "none") or (
            readbacks and policy == "none"):
        raise ActivationError(
            "%s readback_policy %s disagrees with readback_sources" %
            (declared_path, policy))
    read_set_snapshot, _ = _snapshot_text(root, registered["read_set"])
    return {
        "route_id": route_id,
        "path": declared_path,
        "sha256": snapshot.sha256,
        "source_hash": observed,
        "compiled_source_hash": compiled,
        "read_set": registered["read_set"],
        "read_set_sha256": read_set_snapshot.sha256,
        "readback_policy": policy,
        "readback_sources": readbacks,
        "content": text,
    }


def _activation_bundle_manifest(bundle):
    """Project a v1/v2 delivery payload into its content-addressed manifest."""
    manifest = {
        key: value for key, value in bundle.items()
        if key not in ("cards", "startup_readbacks")
    }
    manifest["cards"] = [
        {key: value for key, value in card.items() if key != "content"}
        for card in bundle.get("cards", [])
    ]
    manifest["startup_readbacks"] = [
        {key: value for key, value in row.items() if key != "content"}
        for row in bundle.get("startup_readbacks", [])
    ]
    return manifest


def _piece_envelope_bytes(piece):
    """Measure one delivery exactly as it will be serialized to the host."""
    return len(kblib.canonical_json_bytes(piece))


def work_spec_route_narrowing(root, item):
    """Return the routes one batch's Work Spec declares it actually needs.

    A batch that says nothing keeps the whole non-conditional route set: an
    absent declaration is silence, never a claim that fewer routes suffice.
    Declaring the field is how a batch buys a smaller startup, and the
    declaration is itself frozen -- the Work Spec hash is already bound by
    the Queue, so narrowing cannot drift underneath the plan.
    """
    if not isinstance(item, dict):
        return None
    relative = item.get("work_spec_path")
    expected_sha = item.get("work_spec_sha256")
    if not isinstance(relative, str) or not relative:
        return None
    snapshot = kblib.repository_target_snapshot(
        root, relative, suffixes=(".yaml",))
    if not snapshot.exists:
        raise ActivationError("work spec %s is missing" % relative)
    if isinstance(expected_sha, str) and expected_sha and \
            snapshot.sha256 != expected_sha:
        raise ActivationError(
            "work spec %s drifted from the Queue binding" % relative)
    try:
        document = kblib.parse_yaml_subset(snapshot.read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        raise ActivationError("work spec %s is unreadable: %s" %
                              (relative, exc))
    if not isinstance(document, dict):
        raise ActivationError("work spec %s must be a mapping" % relative)
    declared = document.get("required_route_ids")
    if declared is None:
        return None
    routes = _strings(declared, "%s required_route_ids" % relative)
    if not routes:
        raise ActivationError(
            "%s declares an empty required_route_ids; omit the field instead "
            "of claiming a batch needs no work route" % relative)
    return sorted(set(routes))


def resolve_route_phases(routes, *, narrowing=None):
    """Assign every selected route to exactly one phase.

    Three routes carry their own phase because their Cards already say so:
    R09 and R08 are entered by a governance or completion transition, R12 by
    a targeted-audit predicate.  R01 is the common boundary every phase
    presumes.  Everything else is work: it starts in preflight unless the
    batch narrowed itself, and a narrowed-away route stays available on
    demand during `batch-running` rather than disappearing.
    """
    narrowed = narrowing is not None
    keep = set(narrowing or ())
    assignment = {}
    for route_id in routes:
        override = ROUTE_PHASE_OVERRIDES.get(route_id)
        if override is not None:
            assignment[route_id] = override
            continue
        if narrowed and route_id not in keep:
            assignment[route_id] = PHASE_BATCH_RUNNING
        else:
            assignment[route_id] = PHASE_BATCH_PREFLIGHT
    return assignment


def _piece_records(cards, startup, phase_of=None):
    """Freeze one addressable record per deliverable file.

    A piece is always a whole file.  Splitting one file across results would
    break the only verification the receiving end can perform: the frozen
    SHA binds the complete file, a model cannot rehash fragments, and no
    party could then prove a reassembly was faithful.

    Under a phased protocol each record also carries the phase that will
    deliver it, decided here at admission so no later reader has to re-derive
    it from the route table.
    """
    def _phase(route_id, default=PHASE_BATCH_PREFLIGHT):
        if phase_of is None:
            return None
        return phase_of.get(route_id, default)

    pieces = []
    for card in cards:
        record = {
            "piece_id": "card:%s" % card["route_id"],
            "kind": "card",
            "path": card["path"],
            "sha256": card["sha256"],
            "bytes": len(card["content"].encode("utf-8")),
            "route_id": card["route_id"],
            "read_set": card["read_set"],
            "read_set_sha256": card["read_set_sha256"],
            "source_hash": card["source_hash"],
            "compiled_source_hash": card["compiled_source_hash"],
            "readback_policy": card["readback_policy"],
            "readback_sources": list(card["readback_sources"]),
        }
        phase = _phase(card["route_id"])
        if phase is not None:
            record["phase"] = phase
        pieces.append(record)
    for row in startup:
        record = {
            "piece_id": "readback:%s" % row["rule_id"],
            "kind": "activation-readback",
            "path": row["path"],
            "sha256": row["sha256"],
            "bytes": len(row["content"].encode("utf-8")),
            "route_id": row["route_id"],
            "rule_id": row["rule_id"],
        }
        # A read-back travels with the Card that declared it; the Card Index
        # belongs to no route, so it waits for the dispute that needs it.
        phase = _phase(row["route_id"], PHASE_BATCH_RUNNING)
        if phase is not None:
            record["phase"] = phase
        pieces.append(record)
    pieces.sort(key=lambda row: row["piece_id"])
    identifiers = [row["piece_id"] for row in pieces]
    if len(identifiers) != len(set(identifiers)):
        raise ActivationError("activation piece identifiers are not unique")
    return pieces


def expand_batch_review_requirements(profile_contract, item):
    """Expand the Profile's requirements against one frozen batch manifest.

    The result is deterministic: sorted records of exactly the (batch,
    target, judgment item) obligations this batch must answer before
    `merge-ready`.  A page-selector row expands over the manifest; a
    batch-selector row expands to the batch itself.  No natural-language
    applicability exists by construction.
    """
    batch_id = item.get("id") if isinstance(item, dict) else None
    if not isinstance(batch_id, str) or not batch_id:
        raise ActivationError("review expansion batch has no id")
    requirements = ()
    if profile_contract is not None:
        if not getattr(profile_contract, "authorized", False):
            raise ActivationError(
                "review expansion requires one authorized typed Profile "
                "contract")
        requirements = getattr(
            profile_contract, "batch_review_requirements", ())
    manifest = item.get("manifest")
    if not isinstance(manifest, list) or not all(
            isinstance(page, str) and page for page in manifest):
        raise ActivationError("review expansion manifest must be a string list")
    records = []
    for requirement in requirements:
        if requirement.target_selector == "each-manifest-page":
            targets = sorted(set(manifest))
        elif requirement.target_selector == "batch":
            targets = [batch_id]
        else:
            raise ActivationError(
                "review expansion target selector %r is unsupported" %
                requirement.target_selector)
        for target in targets:
            records.append({
                "batch_id": batch_id,
                "target": target,
                "judgment_item_id": requirement.judgment_item_id,
                "target_selector": requirement.target_selector,
                "trigger": requirement.trigger,
                "producer_kind": requirement.producer_kind,
                "receipt_schema": requirement.receipt_schema,
                "pass_authority_role_id": requirement.pass_authority_role_id,
            })
    records.sort(key=lambda row: (row["judgment_item_id"], row["target"]))
    return records


def review_requirement_set_sha256(records):
    """Hash only the closed obligation identity of one expansion."""
    identity = [
        {
            "batch_id": row["batch_id"],
            "target": row["target"],
            "judgment_item_id": row["judgment_item_id"],
        }
        for row in records
    ]
    return kblib.sha256_bytes(kblib.canonical_json_bytes(identity))


def build_activation_context(root, progress, item, *, runtime_state,
                             execution_context_id=None,
                             profile_contract=None):
    """Return receipt extension fields for one exact activation delivery."""
    contract, contract_sha = _contract_fingerprint(progress)
    runtime_bindings = _runtime_bindings(runtime_state)
    if profile_contract is None:
        view = runtime_state.get("_profile_authorized_view")
        profile_contract = (view or {}).get("_contract") if isinstance(
            view, dict) else None
    if profile_contract is None or not getattr(
            profile_contract, "authorized", False):
        raise ActivationError(
            "activation requires one authorized typed Profile contract")
    batch_id = item.get("id") if isinstance(item, dict) else None
    if not isinstance(batch_id, str) or not batch_id:
        raise ActivationError("activation batch has no id")
    if runtime_state.get("progress") != progress:
        raise ActivationError(
            "activation Progress differs from the validated runtime view")
    if runtime_bindings["progress_ledger_sha256"] != kblib.sha256_bytes(
            kblib.canonical_yaml(progress)):
        raise ActivationError(
            "activation Progress bytes differ from the runtime fingerprint")
    if (runtime_state.get("items_by_id") or {}).get(batch_id) != item:
        raise ActivationError(
            "activation batch differs from the validated Queue view")
    routes = sorted(_strings(contract.get("selected_route_ids"),
                             "selected_route_ids", nonempty=True))
    if "R01" not in routes:
        raise ActivationError("selected_route_ids must include R01")
    declared_cards = _strings(contract.get("selected_card_paths"),
                              "selected_card_paths", nonempty=True)
    registry, registry_sha = _route_registry(root)
    unknown = sorted(set(routes) - set(registry))
    if unknown:
        raise ActivationError("selected route(s) are unregistered: %s" %
                              ", ".join(unknown))
    expected_paths = [registry[route]["path"] for route in routes]
    # Older adopting contracts may explicitly freeze the Card Index itself in
    # selected_card_paths.  It is the navigation registry, not an Rxx Card, so
    # it must not be interpreted as a route or silently discarded.  Permit
    # only that one canonical extra path and deliver its exact bytes below.
    allowed_paths = set(expected_paths) | {CARD_INDEX_PATH}
    missing = sorted(set(expected_paths) - set(declared_cards))
    extra = sorted(set(declared_cards) - allowed_paths)
    if missing or extra:
        raise ActivationError(
            "selected_card_paths does not exactly match selected routes; "
            "missing=%s extra=%s" %
            (",".join(missing) or "none", ",".join(extra) or "none"))

    cards = []
    startup = []
    readback_plan = []
    if CARD_INDEX_PATH in declared_cards:
        index_snapshot, index_text = _snapshot_text(root, CARD_INDEX_PATH)
        startup.append({
            "rule_id": "kernel:activation:card-index",
            "route_id": "kernel-card-index",
            "path": CARD_INDEX_PATH,
            "sha256": index_snapshot.sha256,
            "content": index_text,
        })
    for route_id in routes:
        card = _card_record(root, route_id, registry[route_id],
                            registry[route_id]["path"])
        cards.append(card)
        if card["readback_policy"] == "activation":
            for source in card["readback_sources"]:
                source_snapshot, source_text = _snapshot_text(root, source)
                startup.append({
                    "rule_id": "%s:activation:%s" % (route_id, source),
                    "route_id": route_id,
                    "path": source,
                    "sha256": source_snapshot.sha256,
                    "content": source_text,
                })
        elif card["readback_policy"] == "declared":
            for source in card["readback_sources"]:
                source_snapshot, _ = _snapshot_text(root, source)
                readback_plan.append({
                    "rule_id": "%s:declared:%s" % (route_id, source),
                    "route_id": route_id,
                    "phase": "triggered",
                    "evaluator": "declared",
                    "source_paths": [{
                        "path": source,
                        "sha256": source_snapshot.sha256,
                    }],
                })

    # A Profile supplemental Read Set has no kernel Card.  Its own compact
    # route document is therefore part of startup context, while transitive
    # kernel Read Sets remain governed by the selected Cards above.
    profile_routes = set(_strings(contract.get("selected_profile_route_ids"),
                                  "selected_profile_route_ids"))
    for relative in sorted(_strings(contract.get("selected_read_sets"),
                                    "selected_read_sets")):
        snapshot, text = _snapshot_text(root, relative)
        document = _frontmatter(text, relative)
        if document.get("type") != "profile-read-set":
            continue
        route_id = document.get("route_id")
        if route_id not in profile_routes:
            raise ActivationError(
                "%s profile route %r is not selected" % (relative, route_id))
        startup.append({
            "rule_id": "%s:activation:%s" % (route_id, relative),
            "route_id": route_id,
            "path": relative,
            "sha256": snapshot.sha256,
            "content": text,
        })

    cards.sort(key=lambda row: (row["route_id"], row["path"]))
    startup.sort(key=lambda row: (row["route_id"], row["path"]))
    readback_plan.sort(key=lambda row: row["rule_id"])
    reading_plan = {
        "selected_route_ids": routes,
        "selected_card_paths": sorted(declared_cards),
        "selected_profile_route_ids": sorted(profile_routes),
        "selected_read_sets": sorted(_strings(
            contract.get("selected_read_sets"), "selected_read_sets")),
        "loaded_module_paths": sorted(_strings(
            contract.get("loaded_module_paths"), "loaded_module_paths")),
    }
    reading_plan_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(reading_plan))
    readback_plan_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(readback_plan))
    review_records = expand_batch_review_requirements(profile_contract, item)
    review_set_sha = review_requirement_set_sha256(review_records)
    narrowing = work_spec_route_narrowing(root, item)
    if narrowing is not None:
        unknown_narrowed = sorted(set(narrowing) - set(routes))
        if unknown_narrowed:
            raise ActivationError(
                "work spec narrows to route(s) the contract did not select: "
                "%s" % ", ".join(unknown_narrowed))
    phase_of = resolve_route_phases(routes, narrowing=narrowing)
    for route_id in sorted(profile_routes):
        phase_of.setdefault(
            route_id,
            PHASE_BATCH_RUNNING if narrowing is not None
            else PHASE_BATCH_PREFLIGHT)
    pieces = _piece_records(cards, startup, phase_of)
    manifest = {
        "activation_protocol": ACTIVATION_PROTOCOL,
        "task_id": progress.get("task_id"),
        "batch_id": batch_id,
        "standards_version": contract.get("standards_version"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"),
        **runtime_bindings,
        "task_contract_sha256": contract_sha,
        "card_index_sha256": registry_sha,
        "reading_plan_sha256": reading_plan_sha,
        "readback_plan_sha256": readback_plan_sha,
        "reading_plan": reading_plan,
        "pieces": pieces,
        "piece_count": len(pieces),
        "max_piece_envelope_bytes": MAX_ACTIVATION_PIECE_ENVELOPE_BYTES,
        "readback_plan": readback_plan,
        "batch_review_plan": {
            "protocol": BATCH_REVIEW_PLAN_PROTOCOL,
            "review_requirement_set_sha256": review_set_sha,
            "requirements": review_records,
        },
    }
    # Freeze what resolved this plan next to the plan itself.  A later phase
    # is materialized by a later run, so replay has to be able to see the
    # Standards, Profile, resolver and Work Spec the membership was computed
    # under -- otherwise "the same phase" silently means two things.
    environment = {
        "standards_version": contract.get("standards_version"),
        "selected_profile_manifest": contract.get(
            "selected_profile_manifest"),
        "profile_snapshot_sha256": runtime_bindings.get(
            "profile_snapshot_sha256"),
        "profile_contract_fingerprint": runtime_bindings.get(
            "profile_contract_fingerprint"),
        "profile_load_inputs_sha256": runtime_bindings.get(
            "profile_load_inputs_sha256"),
        "resolver_version": PHASE_RESOLVER_VERSION,
        "card_index_sha256": registry_sha,
        "task_contract_sha256": contract_sha,
        "work_spec_path": item.get("work_spec_path"),
        "work_spec_sha256": item.get("work_spec_sha256"),
    }
    # Packing measures the real serialization, so it also performs v3's
    # fail-closed budget check: an oversized leaf raises here, at its own
    # admission boundary, instead of surfacing as a transport accident.
    texts_by_id = dict(zip(
        [row["piece_id"] for row in pieces],
        _piece_texts(cards, startup, pieces)))
    phase_plan = _build_phase_plan(manifest, pieces, texts_by_id, phase_of,
                                   environment=environment,
                                   narrowing=narrowing)
    phase_plan_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(phase_plan))
    manifest["phase_plan"] = phase_plan
    manifest["phase_plan_sha256"] = phase_plan_sha
    bundle_sha = kblib.sha256_bytes(kblib.canonical_json_bytes(manifest))
    return {
        "activation_protocol": ACTIVATION_PROTOCOL,
        "task_contract_sha256": contract_sha,
        "reading_plan_sha256": reading_plan_sha,
        "readback_plan_sha256": readback_plan_sha,
        "review_requirement_set_sha256": review_set_sha,
        "phase_plan_sha256": phase_plan_sha,
        "card_bundle_sha256": bundle_sha,
        "activation_bundle_manifest": manifest,
        **_delivery_binding(execution_context_id,
                            protocol=ACTIVATION_PROTOCOL),
    }


def _piece_texts(cards, startup, pieces):
    """Return each piece's exact text in the frozen piece order."""
    by_id = {}
    for card in cards:
        by_id["card:%s" % card["route_id"]] = card["content"]
    for row in startup:
        by_id["readback:%s" % row["rule_id"]] = row["content"]
    return [by_id[record["piece_id"]] for record in pieces]


def _piece_delivery_payload(manifest, record, text, *, nonce,
                            delivery_attempt_id, card_bundle_sha256=None):
    """Assemble one piece delivery exactly as the host will receive it.

    The nonce sits after the content.  That placement is defence in depth
    against the specific failure this protocol exists to catch -- a host that
    shows only a leading preview -- and nothing more: an ack proves the
    delivery reached this context, never that the whole body was read.  The
    complete guarantee needs the server SHA, a conformant Host Adapter, and
    this ack together.
    """
    return {
        "piece_protocol": PIECE_PROTOCOL,
        "card_bundle_sha256": card_bundle_sha256,
        "batch_id": manifest.get("batch_id"),
        "task_id": manifest.get("task_id"),
        "piece_id": record["piece_id"],
        "kind": record["kind"],
        "path": record["path"],
        "sha256": record["sha256"],
        "bytes": record["bytes"],
        "delivery_attempt_id": delivery_attempt_id,
        "content": text,
        "delivery_nonce": nonce,
    }


def _phase_delivery_payload(manifest, phase_id, part_index, part_count,
                            records, texts, *, nonce, delivery_attempt_id,
                            card_bundle_sha256=None, phase_plan_sha256=None):
    """Assemble one phase part exactly as the host will receive it.

    The structure is v3's single-piece delivery with one field widened: the
    part carries a list of whole files instead of one, and the nonce still
    sits last.  The proof is therefore the same proof -- the nonce shows the
    part reached this context, the conformant Adapter shows a within-budget
    result is not truncated, and each file keeps its own frozen SHA so the
    grouping never becomes a way to smuggle an unverified body.
    """
    return {
        "phase_protocol": PHASE_DELIVERY_PROTOCOL,
        "card_bundle_sha256": card_bundle_sha256,
        "phase_plan_sha256": phase_plan_sha256,
        "batch_id": manifest.get("batch_id"),
        "task_id": manifest.get("task_id"),
        "phase_id": phase_id,
        "part_index": part_index,
        "part_count": part_count,
        "delivery_attempt_id": delivery_attempt_id,
        "pieces": [
            {
                "piece_id": record["piece_id"],
                "kind": record["kind"],
                "path": record["path"],
                "sha256": record["sha256"],
                "bytes": record["bytes"],
                "content": text,
            }
            for record, text in zip(records, texts)
        ],
        "delivery_nonce": nonce,
    }


def _pack_phase_parts(manifest, phase_id, records, texts_by_id):
    """Greedily pack one phase into the fewest budgeted parts.

    Packing happens at admission, with length-exact placeholders, so the
    part boundaries are frozen with everything else: two contexts delivering
    the same phase deliver the same parts, and a phase whose standard form
    needs more than one part is visible as a plan defect before any work
    starts rather than as a delivery surprise.
    """
    placeholder_sha = "sha256:" + ("0" * 64)

    def _measure(rows):
        return _piece_envelope_bytes(_phase_delivery_payload(
            manifest, phase_id, 0, 1, rows,
            [texts_by_id[row["piece_id"]] for row in rows],
            nonce="0" * 32, delivery_attempt_id="0" * 32,
            card_bundle_sha256=placeholder_sha,
            phase_plan_sha256=placeholder_sha))

    # Two separable judgements, in this order.  First: can each file be
    # delivered at all?  A piece is never split across parts, so a file that
    # cannot fit a part alone can never be delivered -- that is the oversized
    # leaf's own governance problem and it fails closed here, exactly as it
    # did in v3.  Deciding this before packing is what keeps an undeliverable
    # leaf from being reported later as a phase that was merely cut too wide.
    oversized = []
    for record in records:
        envelope = _measure([record])
        if envelope > MAX_ACTIVATION_PIECE_ENVELOPE_BYTES:
            oversized.append("%s (%d bytes)" % (record["piece_id"], envelope))
    if oversized:
        raise ActivationError(
            "activation piece(s) exceed the %d-byte delivery budget: %s" %
            (MAX_ACTIVATION_PIECE_ENVELOPE_BYTES, ", ".join(oversized)))

    # Second: pack the deliverable files into as few parts as the budget
    # allows.  Every singleton is now known to fit, so a part is never empty
    # and the loop always makes progress.
    parts = []
    current = []
    for record in records:
        if current and _measure(current + [record]) > \
                MAX_ACTIVATION_PIECE_ENVELOPE_BYTES:
            parts.append(current)
            current = [record]
        else:
            current = current + [record]
    if current:
        parts.append(current)
    return [
        {
            "part_index": index,
            "piece_ids": [row["piece_id"] for row in rows],
            "envelope_bytes": _measure(rows),
        }
        for index, rows in enumerate(parts)
    ]


def _build_phase_plan(manifest, pieces, texts_by_id, phase_of, *,
                      environment, narrowing):
    """Freeze the phase closed set, its membership, and what resolved it."""
    by_phase = {phase_id: [] for phase_id in PHASE_ORDER}
    for record in pieces:
        phase_id = record.get("phase")
        if phase_id not in by_phase:
            raise ActivationError(
                "activation piece %s carries an unregistered phase %r" %
                (record.get("piece_id"), phase_id))
        by_phase[phase_id].append(record)
    phases = []
    for phase_id in PHASE_ORDER:
        records = by_phase[phase_id]
        parts = _pack_phase_parts(manifest, phase_id, records, texts_by_id)
        route_ids = sorted({row["route_id"] for row in records
                            if isinstance(row.get("route_id"), str)})
        if phase_id in STANDARD_PHASES and len(parts) > 1:
            raise ActivationError(
                "standard phase %s needs %d parts; a standard phase that does "
                "not fit one delivery was cut too wide" %
                (phase_id, len(parts)))
        phases.append({
            "phase_id": phase_id,
            "conditional": phase_id in CONDITIONAL_PHASES,
            "standard": phase_id in STANDARD_PHASES,
            "trigger": PHASE_TRIGGERS[phase_id],
            "route_ids": route_ids,
            "piece_ids": [row["piece_id"] for row in records],
            "piece_count": len(records),
            "parts": parts,
            "part_count": len(parts),
        })
    return {
        "protocol": PHASE_PLAN_PROTOCOL,
        "phases": phases,
        "route_phases": dict(sorted(phase_of.items())),
        "work_route_ids": list(narrowing) if narrowing is not None else None,
        "narrowed_by_work_spec": narrowing is not None,
        "environment": environment,
    }


def phase_record(activation_context, phase_id):
    """Return one frozen phase record, or None when the era has no plan."""
    manifest = (activation_context or {}).get("activation_bundle_manifest")
    plan = (manifest or {}).get("phase_plan")
    if not isinstance(plan, dict):
        return None
    for row in plan.get("phases") or []:
        if isinstance(row, dict) and row.get("phase_id") == phase_id:
            return row
    return None


def phase_piece_ids(activation_context, phase_id):
    """Return the exact piece identity set one phase must deliver."""
    record = phase_record(activation_context, phase_id)
    if record is None:
        return []
    return sorted(
        piece_id for piece_id in record.get("piece_ids") or []
        if isinstance(piece_id, str))


def expected_delivery_attempt_id(card_bundle_sha256, execution_context_id):
    """Derive the one attempt id a given bundle and context can produce.

    This is the authoritative pointer, and it needs no stored field: an ack
    chain belongs to the current attempt exactly when its recorded id equals
    the value this function derives from the current activation's bundle and
    the acting context.  A complete chain from a superseded bundle or from
    somebody else's context therefore fails the same equality, which is what
    stops a stale-but-self-consistent chain from being reused.
    """
    return kblib.sha256_bytes(kblib.canonical_json_bytes([
        card_bundle_sha256, execution_context_id]))[7:39]


def activation_context_errors(context):
    """Validate the self-contained shape and byte commitments of a context."""
    errors = []
    if not isinstance(context, dict):
        return ["activation context must be a mapping"]
    protocol = context.get("activation_protocol")
    if protocol not in SUPPORTED_ACTIVATION_PROTOCOLS:
        errors.append("activation_protocol is not one of %s" %
                      ", ".join(sorted(SUPPORTED_ACTIVATION_PROTOCOLS)))
        return errors
    manifest = context.get("activation_bundle_manifest")
    if not isinstance(manifest, dict):
        return errors + ["activation_bundle_manifest must be a mapping"]
    if manifest.get("activation_protocol") != protocol:
        errors.append("activation bundle protocol is invalid")
    if protocol == LEGACY_ACTIVATION_PROTOCOL:
        # Sealed v1 evidence replays under its own era: the review fields
        # must be absent rather than null, exactly as they were written.
        if "review_requirement_set_sha256" in context:
            errors.append(
                "a %s context must not carry review_requirement_set_sha256" %
                LEGACY_ACTIVATION_PROTOCOL)
        if "batch_review_plan" in manifest:
            errors.append(
                "a %s bundle must not carry batch_review_plan" %
                LEGACY_ACTIVATION_PROTOCOL)
    else:
        review_sha = context.get("review_requirement_set_sha256")
        plan = manifest.get("batch_review_plan")
        if not isinstance(review_sha, str) or not SHA256_RE.fullmatch(
                review_sha or ""):
            errors.append(
                "review_requirement_set_sha256 must be a sha256 value")
        if not isinstance(plan, dict):
            errors.append("activation bundle batch_review_plan must be a "
                          "mapping")
        else:
            if plan.get("protocol") != BATCH_REVIEW_PLAN_PROTOCOL:
                errors.append("batch_review_plan protocol is invalid")
            records = plan.get("requirements")
            if not isinstance(records, list):
                errors.append("batch_review_plan requirements must be a list")
            else:
                try:
                    recomputed = review_requirement_set_sha256(records)
                except (KeyError, TypeError) as exc:
                    recomputed = None
                    errors.append(
                        "batch_review_plan requirements are malformed: %s" %
                        exc)
                if recomputed is not None and (
                        plan.get("review_requirement_set_sha256") !=
                        recomputed or review_sha != recomputed):
                    errors.append(
                        "review_requirement_set_sha256 does not bind the "
                        "frozen requirement expansion")
    if protocol in PHASED_PROTOCOLS:
        errors.extend(_phase_plan_errors(context, manifest))
    elif "phase_plan_sha256" in context or "phase_plan" in manifest:
        errors.append(
            "a %s activation must not carry a phase plan" % protocol)
    expected_bundle_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(manifest))
    if context.get("card_bundle_sha256") != expected_bundle_sha:
        errors.append("card_bundle_sha256 does not bind the bundle manifest")
    for field in ("task_contract_sha256", "reading_plan_sha256",
                  "readback_plan_sha256"):
        if context.get(field) != manifest.get(field):
            errors.append("%s does not match the bundle manifest" % field)
    reading_plan = manifest.get("reading_plan")
    if not isinstance(reading_plan, dict):
        errors.append("activation bundle reading_plan must be a mapping")
    elif manifest.get("reading_plan_sha256") != kblib.sha256_bytes(
            kblib.canonical_json_bytes(reading_plan)):
        errors.append("reading_plan_sha256 does not bind reading_plan")
    plan = manifest.get("readback_plan")
    if not isinstance(plan, list):
        errors.append("activation bundle readback_plan must be a list")
    elif manifest.get("readback_plan_sha256") != kblib.sha256_bytes(
            kblib.canonical_json_bytes(plan)):
        errors.append("readback_plan_sha256 does not bind readback_plan")
    # The question here is which era's shape the bundle has, not whether it
    # is the newest protocol: v3 and v4 both freeze a piece manifest and
    # embed nothing, so testing against the current constant would silently
    # re-file every sealed v3 receipt under the embedded-payload rules the
    # moment a v4 lands.
    if protocol in PIECE_DELIVERY_PROTOCOLS:
        errors.extend(_piece_manifest_errors(manifest))
        for field in ("cards", "startup_readbacks"):
            if field in manifest:
                errors.append(
                    "a %s bundle must not embed %s; content travels as "
                    "budgeted pieces" % (protocol, field))
        if "activation_delivery_payload" in context:
            errors.append(
                "a %s admission must not carry an embedded delivery payload" %
                protocol)
    else:
        cards = manifest.get("cards")
        if not isinstance(cards, list) or not cards:
            errors.append("activation bundle must carry at least one Card")
        else:
            routes = []
            for index, card in enumerate(cards):
                if not isinstance(card, dict):
                    errors.append("activation Card %d must be a mapping" %
                                  index)
                    continue
                routes.append(card.get("route_id"))
                if "content" in card or not isinstance(card.get("sha256"),
                                                       str):
                    errors.append(
                        "activation Card %d manifest is malformed" % index)
                if card.get("source_hash") != card.get(
                        "compiled_source_hash"):
                    errors.append(
                        "activation Card %d semantic hashes disagree" % index)
            if "R01" not in routes:
                errors.append("activation bundle omits R01")
        for index, row in enumerate(manifest.get("startup_readbacks") or []):
            if (not isinstance(row, dict) or "content" in row or
                    not isinstance(row.get("sha256"), str)):
                errors.append(
                    "startup readback %d manifest is malformed" % index)

    payload = context.get("activation_delivery_payload")
    if payload is not None:
        if not isinstance(payload, dict) or \
                _activation_bundle_manifest(payload) != manifest:
            errors.append("activation delivery payload does not match manifest")
        else:
            for index, card in enumerate(payload.get("cards") or []):
                content = card.get("content") if isinstance(card, dict) else None
                if not isinstance(content, str) or card.get("sha256") != \
                        kblib.sha256_bytes(content):
                    errors.append(
                        "activation Card %d bytes do not match sha256" % index)
            for index, row in enumerate(
                    payload.get("startup_readbacks") or []):
                content = row.get("content") if isinstance(row, dict) else None
                if not isinstance(content, str) or row.get("sha256") != \
                        kblib.sha256_bytes(content):
                    errors.append(
                        "startup readback %d bytes do not match sha256" % index)
    assurance = context.get("delivery_assurance")
    mode = context.get("delivery_mode")
    context_id = context.get("execution_context_id")
    if protocol in PIECE_DELIVERY_PROTOCOLS:
        if assurance == "host-bound":
            if mode != "host-context-injection" or not isinstance(
                    context_id, str) or not context_id:
                errors.append(
                    "host-bound admission requires one execution context")
        elif assurance == "prepared":
            if mode != "cli-tool-result" or context_id is not None:
                errors.append(
                    "prepared admission must be an unbound CLI result")
        else:
            errors.append(
                "a %s admission records host-bound or prepared; delivery "
                "completion is earned by the phase delivery gate" % protocol)
    elif assurance == "machine-delivered":
        if mode != "host-context-injection" or not isinstance(
                context_id, str) or not context_id:
            errors.append("machine delivery requires one execution context")
    elif assurance == "degraded":
        if mode != "cli-tool-result" or context_id is not None:
            errors.append("degraded delivery must be an unbound CLI result")
    else:
        errors.append("delivery_assurance must be machine-delivered or degraded")
    return errors


def _phase_plan_errors(context, manifest):
    """Validate that a phased bundle freezes a complete, exact phase plan."""
    errors = []
    plan = manifest.get("phase_plan")
    plan_sha = context.get("phase_plan_sha256")
    if not isinstance(plan, dict):
        return ["activation bundle must freeze a phase_plan"]
    if plan.get("protocol") != PHASE_PLAN_PROTOCOL:
        errors.append("phase_plan protocol is invalid")
    recomputed = kblib.sha256_bytes(kblib.canonical_json_bytes(plan))
    if not isinstance(plan_sha, str) or not SHA256_RE.fullmatch(
            plan_sha or ""):
        errors.append("phase_plan_sha256 must be a sha256 value")
    elif plan_sha != recomputed or manifest.get(
            "phase_plan_sha256") != recomputed:
        errors.append("phase_plan_sha256 does not bind the frozen phase plan")
    environment = plan.get("environment")
    if not isinstance(environment, dict):
        errors.append("phase_plan must freeze its resolving environment")
    else:
        for field in ("standards_version", "selected_profile_manifest",
                      "profile_snapshot_sha256",
                      "profile_contract_fingerprint", "resolver_version",
                      "card_index_sha256", "task_contract_sha256"):
            if not isinstance(environment.get(field), str) or not \
                    environment.get(field):
                errors.append(
                    "phase_plan environment lacks %s" % field)
    phases = plan.get("phases")
    if not isinstance(phases, list) or [
            row.get("phase_id") if isinstance(row, dict) else None
            for row in phases] != list(PHASE_ORDER):
        return errors + [
            "phase_plan must carry the closed phase set in canonical order"]
    planned = []
    for row in phases:
        phase_id = row.get("phase_id")
        piece_ids = row.get("piece_ids")
        if not isinstance(piece_ids, list):
            errors.append("phase %s has no piece list" % phase_id)
            continue
        planned.extend(piece_ids)
        if row.get("piece_count") != len(piece_ids):
            errors.append("phase %s piece_count is inconsistent" % phase_id)
        if row.get("conditional") is not (phase_id in CONDITIONAL_PHASES):
            errors.append("phase %s misdeclares its conditionality" % phase_id)
        parts = row.get("parts")
        if not isinstance(parts, list) or row.get("part_count") != len(parts):
            errors.append("phase %s part_count is inconsistent" % phase_id)
            continue
        if phase_id in STANDARD_PHASES and len(parts) > 1:
            errors.append(
                "standard phase %s is split across %d parts" %
                (phase_id, len(parts)))
        packed = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict) or part.get("part_index") != index:
                errors.append("phase %s part %d is malformed" %
                              (phase_id, index))
                continue
            part_ids = part.get("piece_ids")
            if not isinstance(part_ids, list) or not part_ids:
                errors.append("phase %s part %d carries no piece" %
                              (phase_id, index))
                continue
            envelope = part.get("envelope_bytes")
            if not isinstance(envelope, int) or isinstance(envelope, bool) \
                    or envelope > MAX_ACTIVATION_PIECE_ENVELOPE_BYTES:
                errors.append(
                    "phase %s part %d exceeds or omits the delivery budget" %
                    (phase_id, index))
            packed.extend(part_ids)
        if packed != piece_ids:
            errors.append(
                "phase %s parts do not partition its piece list exactly" %
                phase_id)
    frozen_ids = [row.get("piece_id") for row in manifest.get("pieces") or []
                  if isinstance(row, dict)]
    if sorted(planned) != sorted(frozen_ids):
        errors.append(
            "phase plan membership is not exactly the frozen piece set")
    if len(planned) != len(set(planned)):
        errors.append("a frozen piece is planned into more than one phase")
    return errors


def _piece_manifest_errors(manifest):
    """Validate the frozen piece set of a v3 bundle."""
    errors = []
    phased = manifest.get("activation_protocol") in PHASED_PROTOCOLS
    pieces = manifest.get("pieces")
    if not isinstance(pieces, list) or not pieces:
        return ["activation bundle must freeze at least one piece"]
    budget = manifest.get("max_piece_envelope_bytes")
    if budget != MAX_ACTIVATION_PIECE_ENVELOPE_BYTES:
        errors.append("activation bundle binds a foreign delivery budget")
    if manifest.get("piece_count") != len(pieces):
        errors.append("piece_count does not match the frozen piece list")
    seen = set()
    routes = []
    for index, row in enumerate(pieces):
        if not isinstance(row, dict):
            errors.append("activation piece %d must be a mapping" % index)
            continue
        piece_id = row.get("piece_id")
        if not isinstance(piece_id, str) or not piece_id:
            errors.append("activation piece %d has no identity" % index)
            continue
        if piece_id in seen:
            errors.append("activation piece %s is duplicated" % piece_id)
        seen.add(piece_id)
        if row.get("kind") not in PIECE_KINDS:
            errors.append("activation piece %s has an unregistered kind" %
                          piece_id)
        if "content" in row:
            errors.append("activation piece %s must not embed content" %
                          piece_id)
        if not isinstance(row.get("sha256"), str) or not isinstance(
                row.get("bytes"), int):
            errors.append("activation piece %s manifest is malformed" %
                          piece_id)
        if phased and row.get("phase") not in PHASES:
            errors.append("activation piece %s carries no registered phase" %
                          piece_id)
        elif not phased and "phase" in row:
            errors.append("activation piece %s carries a phase in a "
                          "pre-phase era" % piece_id)
        if row.get("kind") == "card":
            routes.append(row.get("route_id"))
            if row.get("source_hash") != row.get("compiled_source_hash"):
                errors.append("activation piece %s semantic hashes disagree" %
                              piece_id)
    if sorted(seen) != [row.get("piece_id") for row in pieces
                        if isinstance(row, dict)]:
        errors.append("activation pieces are not in canonical order")
    if "R01" not in routes:
        errors.append("activation bundle omits R01")
    return errors


def activation_receipt_binding(context):
    """Return the closed manifest fields persisted in receipt JSONL."""
    return {field: context.get(field)
            for field in activation_context_fields(context)}


def activation_bundle_binding(context):
    """Return the delivery-independent frozen Bundle commitment."""
    return {field: context.get(field)
            for field in activation_bundle_fields(context)}


def _delivery_material_manifest(context):
    manifest = context.get("activation_bundle_manifest")
    if not isinstance(manifest, dict):
        return None
    material = dict(manifest)
    for field in RUNTIME_STATE_BINDING_FIELDS:
        material.pop(field, None)
    return material


def exact_context_errors(expected, actual):
    errors = activation_context_errors(actual)
    if not errors and actual != activation_receipt_binding(expected):
        errors.append("activation context does not match current Card/Read Set bytes")
    return errors


def exact_bundle_errors(expected, actual):
    errors = activation_context_errors(actual)
    if not errors and _delivery_material_manifest(actual) != \
            _delivery_material_manifest(expected):
        errors.append("activation Bundle differs from current Card/Read Set bytes")
    return errors


def context_from_receipt(receipt):
    """Project only the closed activation extension from a gate receipt."""
    if not isinstance(receipt, dict):
        return None
    return {field: receipt.get(field)
            for field in activation_context_fields(receipt)}


def build_readback_addendum(root, activation_context, rule_id, *,
                            execution_context_id=None):
    """Materialize one declared read-back rule from an activation bundle."""
    errors = activation_context_errors(activation_context)
    if errors:
        raise ActivationError("activation context is invalid: %s" %
                              "; ".join(errors))
    manifest = activation_context["activation_bundle_manifest"]
    rules = [row for row in manifest["readback_plan"]
             if isinstance(row, dict) and row.get("rule_id") == rule_id]
    if len(rules) != 1:
        raise ActivationError("readback rule %s is not uniquely registered" %
                              rule_id)
    sources = []
    for binding in rules[0].get("source_paths") or []:
        if not isinstance(binding, dict):
            raise ActivationError("readback rule %s is malformed" % rule_id)
        snapshot, text = _snapshot_text(root, binding.get("path"))
        if snapshot.sha256 != binding.get("sha256"):
            raise ActivationError(
                "readback source %s drifted since activation" %
                binding.get("path"))
        sources.append({
            "path": binding["path"], "sha256": snapshot.sha256,
            "content": text,
        })
    payload = {
        "readback_protocol": READBACK_PROTOCOL,
        "parent_card_bundle_sha256": activation_context[
            "card_bundle_sha256"],
        "readback_rule_id": rule_id,
        "rule": rules[0],
        "sources": sources,
    }
    addendum_manifest = dict(payload)
    addendum_manifest["sources"] = [
        {key: value for key, value in source.items() if key != "content"}
        for source in sources
    ]
    addendum_sha = kblib.sha256_bytes(
        kblib.canonical_json_bytes(addendum_manifest))
    return {
        "readback_protocol": READBACK_PROTOCOL,
        "parent_card_bundle_sha256": activation_context[
            "card_bundle_sha256"],
        "readback_rule_id": rule_id,
        "readback_addendum_sha256": addendum_sha,
        "readback_addendum_manifest": addendum_manifest,
        "readback_delivery_payload": payload,
        **_delivery_binding(execution_context_id),
    }


def readback_receipt_binding(context):
    """Return the content-addressed Addendum manifest stored in JSONL."""
    return {field: context.get(field) for field in READBACK_CONTEXT_FIELDS}


def build_activation_piece(root, activation_context, piece_id, *,
                           execution_context_id=None,
                           delivery_attempt_id=None, nonce=None):
    """Deliver one frozen piece as its own budgeted tool result."""
    errors = activation_context_errors(activation_context)
    if errors:
        raise ActivationError("activation context is invalid: %s" %
                              "; ".join(errors))
    protocol = activation_context.get("activation_protocol")
    if protocol not in PIECE_DELIVERY_PROTOCOLS:
        raise ActivationError(
            "piece delivery requires one of %s" %
            ", ".join(sorted(PIECE_DELIVERY_PROTOCOLS)))
    manifest = activation_context["activation_bundle_manifest"]
    records = [row for row in manifest.get("pieces") or []
               if isinstance(row, dict) and row.get("piece_id") == piece_id]
    if len(records) != 1:
        raise ActivationError("activation piece %s is not uniquely frozen" %
                              piece_id)
    record = records[0]
    # Re-prove the object against current bytes.  v1/v2 performed this
    # equality once, at `queued -> open`; delivering file by file moves the
    # same check onto every piece, so a source that drifts mid-delivery is
    # refused instead of silently shipped.
    snapshot, text = _snapshot_text(root, record["path"])
    if snapshot.sha256 != record["sha256"]:
        raise ActivationError(
            "activation piece %s drifted since admission (%s)" %
            (piece_id, record["path"]))
    attempt = delivery_attempt_id or kblib.sha256_bytes(
        kblib.canonical_json_bytes([
            activation_context["card_bundle_sha256"],
            execution_context_id or os.environ.get(EXECUTION_CONTEXT_ENV),
        ]))[7:39]
    payload = _piece_delivery_payload(
        manifest, record, text, nonce=nonce or _mint_nonce(),
        delivery_attempt_id=attempt,
        card_bundle_sha256=activation_context["card_bundle_sha256"])
    envelope = _piece_envelope_bytes(payload)
    if envelope > MAX_ACTIVATION_PIECE_ENVELOPE_BYTES:
        raise ActivationError(
            "activation piece %s serializes to %d bytes, over the %d-byte "
            "delivery budget" %
            (piece_id, envelope, MAX_ACTIVATION_PIECE_ENVELOPE_BYTES))
    return {
        "piece_protocol": PIECE_PROTOCOL,
        "card_bundle_sha256": activation_context["card_bundle_sha256"],
        "piece_id": piece_id,
        "piece_sha256": record["sha256"],
        "piece_envelope_bytes": envelope,
        "delivery_attempt_id": attempt,
        "delivery_nonce": payload["delivery_nonce"],
        "activation_piece_payload": payload,
        **_delivery_binding(execution_context_id,
                            protocol=ACTIVATION_PROTOCOL),
    }


def build_phase_delivery(root, activation_context, phase_id, part_index=0, *,
                         execution_context_id=None,
                         delivery_attempt_id=None, nonce=None):
    """Deliver one frozen phase part as its own budgeted tool result."""
    errors = activation_context_errors(activation_context)
    if errors:
        raise ActivationError("activation context is invalid: %s" %
                              "; ".join(errors))
    if activation_context.get("activation_protocol") not in PHASED_PROTOCOLS:
        raise ActivationError(
            "phase delivery requires a %s activation" % ACTIVATION_PROTOCOL)
    if phase_id not in PHASES:
        raise ActivationError("phase %r is not a registered phase" % phase_id)
    record = phase_record(activation_context, phase_id)
    if record is None:
        raise ActivationError("activation freezes no plan for phase %s" %
                              phase_id)
    parts = record.get("parts") or []
    if not parts:
        raise ActivationError(
            "phase %s freezes no deliverable part; it carries no piece" %
            phase_id)
    if not isinstance(part_index, int) or isinstance(part_index, bool) or \
            part_index < 0 or part_index >= len(parts):
        raise ActivationError(
            "phase %s has %d part(s); part %r does not exist" %
            (phase_id, len(parts), part_index))
    part = parts[part_index]
    manifest = activation_context["activation_bundle_manifest"]
    frozen = {row.get("piece_id"): row for row in manifest.get("pieces") or []
              if isinstance(row, dict)}
    records = []
    texts = []
    for piece_id in part.get("piece_ids") or []:
        frozen_record = frozen.get(piece_id)
        if not isinstance(frozen_record, dict):
            raise ActivationError(
                "phase %s part %d names unfrozen piece %s" %
                (phase_id, part_index, piece_id))
        # Re-prove every file against current bytes, exactly as v3 does per
        # piece: grouping files into one result must not weaken the per-file
        # drift check that makes the frozen SHA meaningful.
        snapshot, text = _snapshot_text(root, frozen_record["path"])
        if snapshot.sha256 != frozen_record["sha256"]:
            raise ActivationError(
                "activation piece %s drifted since admission (%s)" %
                (piece_id, frozen_record["path"]))
        records.append(frozen_record)
        texts.append(text)
    attempt = delivery_attempt_id or expected_delivery_attempt_id(
        activation_context["card_bundle_sha256"],
        execution_context_id or os.environ.get(EXECUTION_CONTEXT_ENV))
    payload = _phase_delivery_payload(
        manifest, phase_id, part_index, len(parts), records, texts,
        nonce=nonce or _mint_nonce(), delivery_attempt_id=attempt,
        card_bundle_sha256=activation_context["card_bundle_sha256"],
        phase_plan_sha256=activation_context.get("phase_plan_sha256"))
    envelope = _piece_envelope_bytes(payload)
    if envelope > MAX_ACTIVATION_PIECE_ENVELOPE_BYTES:
        raise ActivationError(
            "phase %s part %d serializes to %d bytes, over the %d-byte "
            "delivery budget" %
            (phase_id, part_index, envelope,
             MAX_ACTIVATION_PIECE_ENVELOPE_BYTES))
    return {
        "phase_protocol": PHASE_DELIVERY_PROTOCOL,
        "card_bundle_sha256": activation_context["card_bundle_sha256"],
        "phase_plan_sha256": activation_context.get("phase_plan_sha256"),
        "phase_id": phase_id,
        "part_index": part_index,
        "part_count": len(parts),
        "phase_piece_ids": list(part.get("piece_ids") or []),
        "phase_envelope_bytes": envelope,
        "delivery_attempt_id": attempt,
        "delivery_nonce": payload["delivery_nonce"],
        "activation_phase_payload": payload,
        **_delivery_binding(execution_context_id,
                            protocol=ACTIVATION_PROTOCOL),
    }


def build_phase_ack(delivery_receipt, nonce, *, execution_context_id=None):
    """Turn one returned phase nonce into same-context delivery evidence.

    Same three-part model as a single piece: this is the third part only.
    It shows the part reached this context; it never shows the bodies ahead
    of the nonce were read.
    """
    if not isinstance(delivery_receipt, dict):
        raise ActivationError("phase ack requires one delivery receipt")
    if delivery_receipt.get("phase_protocol") != PHASE_DELIVERY_PROTOCOL:
        raise ActivationError("phase ack requires a %s delivery" %
                              PHASE_DELIVERY_PROTOCOL)
    expected = delivery_receipt.get("delivery_nonce")
    if not isinstance(expected, str) or not expected or nonce != expected:
        raise ActivationError(
            "phase ack nonce does not match delivery %s part %s" %
            (delivery_receipt.get("phase_id"),
             delivery_receipt.get("part_index")))
    bound = delivery_receipt.get("execution_context_id")
    current = execution_context_id
    if current is None:
        current = os.environ.get(EXECUTION_CONTEXT_ENV)
    if bound != current:
        raise ActivationError(
            "phase ack must return to the delivering execution context")
    return {
        "phase_ack_protocol": PHASE_ACK_PROTOCOL,
        "card_bundle_sha256": delivery_receipt.get("card_bundle_sha256"),
        "phase_plan_sha256": delivery_receipt.get("phase_plan_sha256"),
        "phase_id": delivery_receipt.get("phase_id"),
        "part_index": delivery_receipt.get("part_index"),
        "part_count": delivery_receipt.get("part_count"),
        "phase_piece_ids": list(delivery_receipt.get("phase_piece_ids") or []),
        "delivery_attempt_id": delivery_receipt.get("delivery_attempt_id"),
        "acked_nonce": nonce,
        "delivery_receipt_id": delivery_receipt.get("receipt_id"),
        **_delivery_binding(execution_context_id,
                            protocol=ACTIVATION_PROTOCOL),
    }


PHASE_RECEIPT_FIELDS = (
    "phase_protocol", "card_bundle_sha256", "phase_plan_sha256", "phase_id",
    "part_index", "part_count", "phase_piece_ids", "phase_envelope_bytes",
    "delivery_attempt_id", "delivery_nonce",
    "delivery_mode", "delivery_assurance", "execution_context_id",
)
PHASE_ACK_RECEIPT_FIELDS = (
    "phase_ack_protocol", "card_bundle_sha256", "phase_plan_sha256",
    "phase_id", "part_index", "part_count", "phase_piece_ids",
    "delivery_attempt_id", "acked_nonce", "delivery_receipt_id",
    "delivery_mode", "delivery_assurance", "execution_context_id",
)


def phase_receipt_binding(context):
    """Return the closed phase-delivery fields persisted in receipt JSONL."""
    return {field: context.get(field) for field in PHASE_RECEIPT_FIELDS}


def phase_ack_receipt_binding(context):
    """Return the closed phase ack fields persisted in receipt JSONL."""
    return {field: context.get(field) for field in PHASE_ACK_RECEIPT_FIELDS}


def _mint_nonce():
    return os.urandom(16).hex()


PIECE_RECEIPT_FIELDS = (
    "piece_protocol", "card_bundle_sha256", "piece_id", "piece_sha256",
    "piece_envelope_bytes", "delivery_attempt_id", "delivery_nonce",
    "delivery_mode", "delivery_assurance", "execution_context_id",
)
PIECE_ACK_RECEIPT_FIELDS = (
    "piece_ack_protocol", "card_bundle_sha256", "piece_id", "piece_sha256",
    "delivery_attempt_id", "acked_nonce", "delivery_receipt_id",
    "delivery_mode", "delivery_assurance", "execution_context_id",
)


def piece_receipt_binding(context):
    """Return the closed piece-delivery fields persisted in receipt JSONL."""
    return {field: context.get(field) for field in PIECE_RECEIPT_FIELDS}


def build_piece_ack(delivery_receipt, nonce, *, execution_context_id=None):
    """Turn one returned nonce into same-context delivery evidence.

    This is the third of three parts, never the whole proof.  It shows the
    delivery was consumed by this execution context; it cannot show that the
    body ahead of the nonce entered the model context.  Only a Host Adapter
    that has passed inline-delivery conformance supplies that half.
    """
    if not isinstance(delivery_receipt, dict):
        raise ActivationError("piece ack requires one delivery receipt")
    if delivery_receipt.get("piece_protocol") != PIECE_PROTOCOL:
        raise ActivationError("piece ack requires a %s delivery" %
                              PIECE_PROTOCOL)
    expected = delivery_receipt.get("delivery_nonce")
    if not isinstance(expected, str) or not expected or nonce != expected:
        raise ActivationError(
            "piece ack nonce does not match delivery %s" %
            delivery_receipt.get("piece_id"))
    bound = delivery_receipt.get("execution_context_id")
    current = execution_context_id
    if current is None:
        current = os.environ.get(EXECUTION_CONTEXT_ENV)
    if bound != current:
        raise ActivationError(
            "piece ack must return to the delivering execution context")
    return {
        "piece_ack_protocol": PIECE_ACK_PROTOCOL,
        "card_bundle_sha256": delivery_receipt.get("card_bundle_sha256"),
        "piece_id": delivery_receipt.get("piece_id"),
        "piece_sha256": delivery_receipt.get("piece_sha256"),
        "delivery_attempt_id": delivery_receipt.get("delivery_attempt_id"),
        "acked_nonce": nonce,
        "delivery_receipt_id": delivery_receipt.get("receipt_id"),
        **_delivery_binding(execution_context_id,
                            protocol=ACTIVATION_PROTOCOL),
    }


def piece_ack_receipt_binding(context):
    """Return the closed ack fields persisted in receipt JSONL."""
    return {field: context.get(field) for field in PIECE_ACK_RECEIPT_FIELDS}


def frozen_piece_ids(activation_context):
    """Return the exact piece identity set one activation must deliver."""
    manifest = (activation_context or {}).get("activation_bundle_manifest")
    if not isinstance(manifest, dict):
        return []
    return sorted(
        row.get("piece_id") for row in manifest.get("pieces") or []
        if isinstance(row, dict) and isinstance(row.get("piece_id"), str))
