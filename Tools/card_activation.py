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


ACTIVATION_PROTOCOL = "card-first-readback-v1"
READBACK_PROTOCOL = "card-readback-addendum-v1"
EXECUTION_CONTEXT_ENV = "CAMBIUM_EXECUTION_CONTEXT_ID"
CARD_INDEX_PATH = "kernel/Cards/Card Index.md"
SHA12_RE = re.compile(r"[0-9a-f]{12}")
READBACK_POLICIES = frozenset(("none", "declared", "activation"))
ACTIVATION_CONTEXT_FIELDS = (
    "activation_protocol", "task_contract_sha256", "reading_plan_sha256",
    "readback_plan_sha256", "card_bundle_sha256",
    "activation_bundle_manifest", "delivery_mode", "delivery_assurance",
    "execution_context_id",
)
ACTIVATION_BUNDLE_FIELDS = ACTIVATION_CONTEXT_FIELDS[:6]
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


def _delivery_binding(execution_context_id=None):
    context_id = execution_context_id
    if context_id is None:
        context_id = os.environ.get(EXECUTION_CONTEXT_ENV)
    if isinstance(context_id, str) and context_id:
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
    """Project a delivery payload into its small content-addressed manifest."""
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


def build_activation_context(root, progress, item, *, runtime_state,
                             execution_context_id=None):
    """Return receipt extension fields for one exact activation delivery."""
    contract, contract_sha = _contract_fingerprint(progress)
    runtime_bindings = _runtime_bindings(runtime_state)
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
    source_route = item.get("source_route")
    if isinstance(source_route, str) and source_route and source_route not in routes:
        raise ActivationError(
            "batch %s source_route %s is absent from selected_route_ids" %
            (batch_id, source_route))
    declared_cards = _strings(contract.get("selected_card_paths"),
                              "selected_card_paths", nonempty=True)
    registry, registry_sha = _route_registry(root)
    unknown = sorted(set(routes) - set(registry))
    if unknown:
        raise ActivationError("selected route(s) are unregistered: %s" %
                              ", ".join(unknown))
    expected_paths = [registry[route]["path"] for route in routes]
    if sorted(declared_cards) != sorted(expected_paths):
        missing = sorted(set(expected_paths) - set(declared_cards))
        extra = sorted(set(declared_cards) - set(expected_paths))
        raise ActivationError(
            "selected_card_paths does not exactly match selected routes; "
            "missing=%s extra=%s" %
            (",".join(missing) or "none", ",".join(extra) or "none"))

    cards = []
    startup = []
    readback_plan = []
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
    bundle = {
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
        "cards": cards,
        "startup_readbacks": startup,
        "readback_plan": readback_plan,
    }
    manifest = _activation_bundle_manifest(bundle)
    bundle_sha = kblib.sha256_bytes(kblib.canonical_json_bytes(manifest))
    return {
        "activation_protocol": ACTIVATION_PROTOCOL,
        "task_contract_sha256": contract_sha,
        "reading_plan_sha256": reading_plan_sha,
        "readback_plan_sha256": readback_plan_sha,
        "card_bundle_sha256": bundle_sha,
        "activation_bundle_manifest": manifest,
        "activation_delivery_payload": bundle,
        **_delivery_binding(execution_context_id),
    }


def activation_context_errors(context):
    """Validate the self-contained shape and byte commitments of a context."""
    errors = []
    if not isinstance(context, dict):
        return ["activation context must be a mapping"]
    if context.get("activation_protocol") != ACTIVATION_PROTOCOL:
        errors.append("activation_protocol is not %s" % ACTIVATION_PROTOCOL)
    manifest = context.get("activation_bundle_manifest")
    if not isinstance(manifest, dict):
        return errors + ["activation_bundle_manifest must be a mapping"]
    if manifest.get("activation_protocol") != ACTIVATION_PROTOCOL:
        errors.append("activation bundle protocol is invalid")
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
    cards = manifest.get("cards")
    if not isinstance(cards, list) or not cards:
        errors.append("activation bundle must carry at least one Card")
    else:
        routes = []
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append("activation Card %d must be a mapping" % index)
                continue
            routes.append(card.get("route_id"))
            if "content" in card or not isinstance(card.get("sha256"), str):
                errors.append("activation Card %d manifest is malformed" %
                              index)
            if card.get("source_hash") != card.get("compiled_source_hash"):
                errors.append("activation Card %d semantic hashes disagree" %
                              index)
        if "R01" not in routes:
            errors.append("activation bundle omits R01")
    for index, row in enumerate(manifest.get("startup_readbacks") or []):
        if (not isinstance(row, dict) or "content" in row or
                not isinstance(row.get("sha256"), str)):
            errors.append("startup readback %d manifest is malformed" % index)

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
    if assurance == "machine-delivered":
        if mode != "host-context-injection" or not isinstance(
                context_id, str) or not context_id:
            errors.append("machine delivery requires one execution context")
    elif assurance == "degraded":
        if mode != "cli-tool-result" or context_id is not None:
            errors.append("degraded delivery must be an unbound CLI result")
    else:
        errors.append("delivery_assurance must be machine-delivered or degraded")
    return errors


def activation_receipt_binding(context):
    """Return the closed manifest fields persisted in receipt JSONL."""
    return {field: context.get(field) for field in ACTIVATION_CONTEXT_FIELDS}


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
    return {field: receipt.get(field) for field in ACTIVATION_CONTEXT_FIELDS}


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
