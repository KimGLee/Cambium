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
ACTIVATION_PROTOCOL = "card-first-readback-v3"
V2_ACTIVATION_PROTOCOL = "card-first-readback-v2"
LEGACY_ACTIVATION_PROTOCOL = "card-first-readback-v1"
SUPPORTED_ACTIVATION_PROTOCOLS = frozenset((
    LEGACY_ACTIVATION_PROTOCOL, V2_ACTIVATION_PROTOCOL, ACTIVATION_PROTOCOL))
EMBEDDED_PAYLOAD_PROTOCOLS = frozenset((
    LEGACY_ACTIVATION_PROTOCOL, V2_ACTIVATION_PROTOCOL))
PIECE_PROTOCOL = "activation-piece-v1"
PIECE_ACK_PROTOCOL = "activation-piece-ack-v1"
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
ACTIVATION_BUNDLE_FIELDS = ACTIVATION_CONTEXT_FIELDS[:7]


def activation_context_fields(context_or_protocol):
    """Return the closed field tuple for one activation era."""
    protocol = context_or_protocol
    if isinstance(context_or_protocol, dict):
        protocol = context_or_protocol.get("activation_protocol")
    if protocol == LEGACY_ACTIVATION_PROTOCOL:
        return LEGACY_ACTIVATION_CONTEXT_FIELDS
    return ACTIVATION_CONTEXT_FIELDS
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


def _piece_records(cards, startup):
    """Freeze one addressable record per deliverable file.

    A piece is always a whole file.  Splitting one file across results would
    break the only verification the receiving end can perform: the frozen
    SHA binds the complete file, a model cannot rehash fragments, and no
    party could then prove a reassembly was faithful.
    """
    pieces = []
    for card in cards:
        pieces.append({
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
        })
    for row in startup:
        pieces.append({
            "piece_id": "readback:%s" % row["rule_id"],
            "kind": "activation-readback",
            "path": row["path"],
            "sha256": row["sha256"],
            "bytes": len(row["content"].encode("utf-8")),
            "route_id": row["route_id"],
            "rule_id": row["rule_id"],
        })
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
    pieces = _piece_records(cards, startup)
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
    # Fail closed at admission rather than at delivery: a manifest that
    # cannot be delivered inside the budget is a governance problem for the
    # oversized leaf, not a transport accident to discover mid-batch.
    oversized = []
    # The stand-ins are length-exact: the real delivery carries a 71-character
    # bundle hash, a 32-character nonce and a 32-character attempt id, so
    # measuring with None here would under-report the envelope and let a piece
    # on the boundary pass admission and fail delivery.
    sha_placeholder = "sha256:" + ("0" * 64)
    for record, text in zip(pieces, _piece_texts(cards, startup, pieces)):
        envelope = _piece_envelope_bytes(
            _piece_delivery_payload(manifest, record, text, nonce="0" * 32,
                                    delivery_attempt_id="0" * 32,
                                    card_bundle_sha256=sha_placeholder))
        if envelope > MAX_ACTIVATION_PIECE_ENVELOPE_BYTES:
            oversized.append("%s (%d bytes)" % (record["piece_id"], envelope))
    if oversized:
        raise ActivationError(
            "activation piece(s) exceed the %d-byte delivery budget: %s" %
            (MAX_ACTIVATION_PIECE_ENVELOPE_BYTES, ", ".join(oversized)))
    bundle_sha = kblib.sha256_bytes(kblib.canonical_json_bytes(manifest))
    return {
        "activation_protocol": ACTIVATION_PROTOCOL,
        "task_contract_sha256": contract_sha,
        "reading_plan_sha256": reading_plan_sha,
        "readback_plan_sha256": readback_plan_sha,
        "review_requirement_set_sha256": review_set_sha,
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
    if protocol == ACTIVATION_PROTOCOL:
        errors.extend(_piece_manifest_errors(manifest))
        for field in ("cards", "startup_readbacks"):
            if field in manifest:
                errors.append(
                    "a %s bundle must not embed %s; content travels as "
                    "budgeted pieces" % (ACTIVATION_PROTOCOL, field))
        if "activation_delivery_payload" in context:
            errors.append(
                "a %s admission must not carry an embedded delivery payload" %
                ACTIVATION_PROTOCOL)
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
    if protocol == ACTIVATION_PROTOCOL:
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
                "completion is earned by the Assignment delivery gate" %
                ACTIVATION_PROTOCOL)
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


def _piece_manifest_errors(manifest):
    """Validate the frozen piece set of a v3 bundle."""
    errors = []
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
    return {field: context.get(field) for field in ACTIVATION_BUNDLE_FIELDS}


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
    if activation_context.get("activation_protocol") != ACTIVATION_PROTOCOL:
        raise ActivationError(
            "piece delivery requires a %s activation" % ACTIVATION_PROTOCOL)
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
