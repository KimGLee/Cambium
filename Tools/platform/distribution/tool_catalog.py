"""Build the non-authoritative Tool hierarchy and interface projection.

The catalog deliberately owns no classification and no interface rule.  It
joins the reviewed machine declarations with the static facts already
derived by :mod:`module_boundary_facts`:

* ``tool-taxonomy.yaml`` supplies Area, Domain, and Layer vocabulary;
* ``module-boundaries.yaml`` supplies each module's reviewed placement and
  declared public surface;
* ``agent-interface-policy.yaml`` supplies CLI, MCP, and shared Host transport
  exposure;
* ``operation-capabilities.yaml`` supplies registered capability relationships;
  and
* ``module_boundary_facts`` supplies shipped modules, static symbol consumers,
  private consumption, and dependency graphs for Python imports.

Both Markdown and JSON are rendered from the same in-memory value.  Neither
projection can change a module responsibility or make an interface public.
"""

import argparse
import collections
import os
import sys

import Tools.platform.agent_interface.agent_interface_policy as agent_interface_policy
import Tools.platform.common.kblib as kblib
import Tools.execution.evidence.receipt_type_contract as receipt_type_contract
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts
import Tools.platform.distribution.module_boundary_report as module_boundary_report


CATALOG_SCHEMA_VERSION = 1
MARKDOWN_OUTPUT = "Tools/TOOL_CATALOG.md"
JSON_OUTPUT = "Tools/compiled/tool-catalog.json"
TAXONOMY_PATH = "Tools/tool-taxonomy.yaml"
BOUNDARIES_PATH = "Tools/module-boundaries.yaml"
INTERFACE_POLICY_PATH = "Tools/agent-interface-policy.yaml"
CAPABILITIES_PATH = "Tools/operation-capabilities.yaml"
SOURCE_PATHS = (
    TAXONOMY_PATH, BOUNDARIES_PATH, INTERFACE_POLICY_PATH, CAPABILITIES_PATH)
TAXONOMY_SCHEMA_VERSION = 1
TOOL = "generate_tool_catalog"


class ToolCatalogError(Exception):
    """The declared or observed inputs cannot produce a reliable catalog."""


def _read_yaml(root, relative_path):
    path = os.path.join(root, *relative_path.split("/"))
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ToolCatalogError("cannot read %s: %s" % (
            relative_path, exc)) from exc
    try:
        document = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except (UnicodeError, kblib.YamlSubsetError) as exc:
        raise ToolCatalogError("cannot parse %s: %s" % (
            relative_path, exc)) from exc
    if not isinstance(document, dict):
        raise ToolCatalogError("%s must contain one mapping" % relative_path)
    return document, raw


def _unique_rows(rows, key, owner):
    if not isinstance(rows, list):
        raise ToolCatalogError("%s must contain a list" % owner)
    found = {}
    for row in rows:
        value = row.get(key) if isinstance(row, dict) else None
        if not isinstance(value, str) or not value or value in found:
            raise ToolCatalogError(
                "%s has an invalid or duplicate %s %r" % (owner, key, value))
        found[value] = row
    return found


def _taxonomy(document):
    if document.get("schema_version") != TAXONOMY_SCHEMA_VERSION:
        raise ToolCatalogError(
            "%s schema_version must be %d" % (
                TAXONOMY_PATH, TAXONOMY_SCHEMA_VERSION))
    areas = _unique_rows(document.get("areas"), "area_id", TAXONOMY_PATH)
    layers = _unique_rows(
        document.get("layers"), "layer_id", TAXONOMY_PATH)
    area_domains = {}
    for area, row in areas.items():
        domains = row.get("domains")
        if not isinstance(domains, list) or any(
                not isinstance(value, str) or not value for value in domains):
            raise ToolCatalogError(
                "%s area %s has no valid domains" % (TAXONOMY_PATH, area))
        if len(domains) != len(set(domains)):
            raise ToolCatalogError(
                "%s area %s duplicates a domain" % (TAXONOMY_PATH, area))
        area_domains[area] = set(domains)
    return areas, layers, area_domains


def _source_type(relative_path):
    return "python-package" if relative_path.endswith("/__init__.py") \
        else "python-module"


def _classification(row, area_domains, layers):
    values = {
        key: row.get(key, "unclassified") if row else "unclassified"
        for key in ("area", "domain", "layer")
    }
    reasons = []
    area = values["area"]
    domain = values["domain"]
    layer = values["layer"]
    if area == "unclassified" or domain == "unclassified" or \
            layer == "unclassified":
        reasons.append("unclassified-value")
    if area not in area_domains:
        reasons.append("unknown-area")
    elif domain not in area_domains[area]:
        reasons.append("unknown-domain")
    if layer not in layers:
        reasons.append("unknown-layer")
    values["resolved"] = not reasons
    values["problems"] = sorted(set(reasons))
    return values


def _cycles(facts):
    module_cycles = module_boundary_facts.strongly_connected(
        module_boundary_facts.import_graph(facts))
    package_cycles = []
    packages = sorted(
        name for name, row in facts.items()
        if row["path"].endswith("/__init__.py"))
    for package in packages:
        for members in module_boundary_facts.strongly_connected(
                module_boundary_facts.package_layers(facts, package)):
            package_cycles.append({"package": package, "members": members})
    return {
        "module_cycles": module_cycles,
        "package_cycles": sorted(
            package_cycles,
            key=lambda row: (row["package"], row["members"])),
    }


def _hierarchy(modules, areas, layers):
    grouped = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    for module in modules:
        classification = module["classification"]
        grouped[classification["area"]][classification["domain"]][
            classification["layer"]].append(module["module"])

    hierarchy = []
    for area in sorted(grouped):
        domain_rows = []
        for domain in sorted(grouped[area]):
            layer_rows = []
            for layer in sorted(grouped[area][domain]):
                layer_rows.append({
                    "layer": layer,
                    "purpose": (layers.get(layer) or {}).get("purpose"),
                    "modules": sorted(grouped[area][domain][layer]),
                })
            domain_rows.append({"domain": domain, "layers": layer_rows})
        hierarchy.append({
            "area": area,
            "purpose": (areas.get(area) or {}).get("purpose"),
            "domains": domain_rows,
        })
    return hierarchy


def _module_by_path(facts):
    return {"Tools/" + row["path"]: name for name, row in facts.items()}


def _registered_capability_relationships(document, facts):
    """Project the validated capability registry without inventing symbols."""
    modules = _module_by_path(facts)
    rows = []
    unresolved = []
    for capability in document["capabilities"]:
        capability_id = capability["capability_id"]
        owner_path = capability.get("implementation_owner")
        owner_module = modules.get(owner_path)
        if owner_module is None:
            unresolved.append({
                "capability_id": capability_id,
                "role": "implementation-owner",
                "path": owner_path,
            })
        relationships = []
        invocation_owner = capability.get("invocation_owner")
        if invocation_owner is not None:
            relationships.append(("invocation-owner", invocation_owner))
        for role in metadata_execution_contract.IMPLEMENTATION_ROLE_KEYS:
            relationships.extend((role[:-1], path)
                                 for path in capability.get(role) or ())
        for role, path in sorted(set(relationships)):
            consumer_module = modules.get(path)
            if consumer_module is None:
                unresolved.append({
                    "capability_id": capability_id,
                    "role": role,
                    "path": path,
                })
            rows.append({
                "capability_id": capability_id,
                "capability_kind": capability["kind"],
                "owner_module": owner_module,
                "owner_path": owner_path,
                "relationship": role,
                "consumer_module": consumer_module,
                "consumer_path": path,
                "same_module": owner_path == path,
            })
    return (
        sorted(rows, key=lambda row: (
            row["capability_id"], row["relationship"],
            row["consumer_path"] or "")),
        sorted(unresolved, key=lambda row: (
            row["capability_id"], row["role"], row["path"] or "")),
    )


def _registered_symbol_relationships(document, receipt_registry, facts):
    """Project dynamic symbol reads that static imports cannot observe.

    Public CLI adapters resolve their implementation ``main`` through the
    literal implementation marker. Receipt catalogs resolve their typed
    validators through the unique producer registry. Both are real symbol
    consumers, but neither appears as a Python import in the caller. Keeping
    these edges beside the static scan prevents a live interface from being
    mislabeled as unused without pretending that the registry is a static
    import graph.
    """
    modules = _module_by_path(facts)
    rows = []
    unresolved = []
    for capability in document["capabilities"]:
        invocation_path = capability.get("invocation_owner")
        if invocation_path is None:
            continue
        consumer = modules.get(invocation_path)
        implementation = (
            facts.get(consumer, {}).get("implementation_module")
            if consumer is not None else None)
        row = {
            "identity": capability["capability_id"],
            "relationship": "entrypoint-main",
            "owner_module": implementation,
            "symbol": "main",
            "consumer_module": consumer,
            "consumer_path": invocation_path,
        }
        rows.append(row)
        owner_fact = facts.get(implementation)
        if (consumer is None or owner_fact is None or
                "main" not in owner_fact["top_level_defs"]):
            unresolved.append(dict(row))

    dispatcher = "execution.evidence.receipt_type_contract"
    for receipt_type_id, registration in sorted(receipt_registry.items()):
        qualified_module, separator, symbol = \
            registration.validator_owner.partition(":")
        owner = qualified_module[len("Tools."):] \
            if qualified_module.startswith("Tools.") else None
        row = {
            "identity": receipt_type_id,
            "relationship": "receipt-validator",
            "owner_module": owner,
            "symbol": symbol if separator else None,
            "consumer_module": dispatcher,
            "consumer_path": "Tools/execution/evidence/receipt_type_contract.py",
            "producer_capability_id":
                registration.producer_capability_id,
        }
        rows.append(row)
        owner_fact = facts.get(owner)
        if (owner_fact is None or symbol not in owner_fact["top_level_defs"]):
            unresolved.append(dict(row))

    key = lambda row: (
        row["relationship"], row["identity"],
        row.get("owner_module") or "", row.get("symbol") or "")
    return sorted(rows, key=key), sorted(unresolved, key=key)


def build_catalog(repo_root):
    """Return one deterministic navigation value for ``repo_root``."""
    root = os.path.realpath(os.path.abspath(os.fspath(repo_root)))
    taxonomy_doc, taxonomy_raw = _read_yaml(root, TAXONOMY_PATH)
    boundaries_doc, boundaries_raw = _read_yaml(root, BOUNDARIES_PATH)
    capabilities_doc, capabilities_raw = _read_yaml(root, CAPABILITIES_PATH)
    try:
        facts = module_boundary_facts.collect(root)
        policy_doc, policy_raw = agent_interface_policy.load_policy(root)
        validated_capabilities = \
            metadata_execution_contract.load_operation_capabilities(root)
        receipt_registry = receipt_type_contract.load_receipt_type_registry(
            root)
    except (OSError, UnicodeError, SyntaxError,
            agent_interface_policy.AgentInterfacePolicyError,
            metadata_execution_contract.MetadataExecutionContractError,
            receipt_type_contract.ReceiptTypeContractError) as exc:
        raise ToolCatalogError(
            "cannot validate Tool catalog sources: %s" % exc) from exc
    cli_modules = set(module_boundary_facts.cli_modules(facts))
    if capabilities_doc != validated_capabilities:
        raise ToolCatalogError(
            "%s changed while the catalog was reading it" % CAPABILITIES_PATH)
    boundary_errors = module_boundary_report.manifest_errors(boundaries_doc)
    if boundary_errors:
        raise ToolCatalogError("%s is invalid: %s" % (
            BOUNDARIES_PATH, "; ".join(boundary_errors)))
    areas, layers, area_domains = _taxonomy(taxonomy_doc)
    boundary_rows = _unique_rows(
        boundaries_doc.get("modules"), "module", BOUNDARIES_PATH)
    policy_rows = _unique_rows(
        policy_doc.get("tools"), "tool", INTERFACE_POLICY_PATH)
    transport_rows = tuple(policy_doc["host_transports"])
    transports_by_module = collections.defaultdict(list)
    for row in transport_rows:
        transports_by_module[row["module"]].append(row)
    registry_relationships, unresolved_registry_paths = \
        _registered_capability_relationships(validated_capabilities, facts)
    registered_symbol_relationships, unresolved_registered_symbols = \
        _registered_symbol_relationships(
            validated_capabilities, receipt_registry, facts)

    public_consumers = collections.defaultdict(set)
    private_consumption = []
    for consumer, owner, symbol in module_boundary_facts.consumption_pairs(
            facts):
        if symbol.startswith("_"):
            private_consumption.append((consumer, owner, symbol))
        else:
            public_consumers[(owner, symbol)].add(consumer)

    declared_public = {}
    declared_exceptions = {}
    for module, row in boundary_rows.items():
        values = row.get("public") or []
        if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values):
            raise ToolCatalogError(
                "%s module %s has an invalid public list" % (
                    BOUNDARIES_PATH, module))
        if len(values) != len(set(values)):
            raise ToolCatalogError(
                "%s module %s duplicates a public symbol" % (
                    BOUNDARIES_PATH, module))
        declared_public[module] = set(values)
        for exception in row.get("exceptions") or ():
            if not isinstance(exception, dict):
                raise ToolCatalogError(
                    "%s module %s has an invalid exception" % (
                        BOUNDARIES_PATH, module))
            key = (exception.get("consumer"), module, exception.get("symbol"))
            if not all(isinstance(value, str) and value for value in key) or \
                    key in declared_exceptions:
                raise ToolCatalogError(
                    "%s module %s has an invalid or duplicate exception" % (
                        BOUNDARIES_PATH, module))
            declared_exceptions[key] = exception

    public_interfaces = []
    public_keys = set(public_consumers)
    for module, symbols in declared_public.items():
        if module in facts:
            public_keys.update((module, symbol) for symbol in symbols)
    for module, symbol in sorted(public_keys):
        consumers = sorted(public_consumers.get((module, symbol), ()))
        is_declared = symbol in declared_public.get(module, set())
        public_interfaces.append({
            "module": module,
            "symbol": symbol,
            "declared": is_declared,
            "consumers": consumers,
            "status": (
                "consumed" if consumers and is_declared else
                "undeclared-consumption" if consumers else
                "declared-unused"),
        })

    registered_symbol_consumers = collections.defaultdict(set)
    for row in registered_symbol_relationships:
        owner = row.get("owner_module")
        symbol = row.get("symbol")
        consumer = row.get("consumer_module")
        if owner is not None and symbol is not None and consumer is not None:
            registered_symbol_consumers[(owner, symbol)].add(consumer)
    observed_public_keys = set(public_keys) | set(registered_symbol_consumers)
    observed_public_interfaces = []
    for module, symbol in sorted(observed_public_keys):
        static_consumers = sorted(
            public_consumers.get((module, symbol), ()))
        registered_consumers = sorted(
            registered_symbol_consumers.get((module, symbol), ()))
        consumers = sorted(set(static_consumers) | set(registered_consumers))
        is_declared = symbol in declared_public.get(module, set())
        observed_public_interfaces.append({
            "module": module,
            "symbol": symbol,
            "declared": is_declared,
            "static_consumers": static_consumers,
            "registered_consumers": registered_consumers,
            "consumers": consumers,
            "status": (
                "consumed" if consumers and is_declared else
                "undeclared-consumption" if consumers else
                "declared-unused"),
        })

    source_public_exports = []
    for module, fact in sorted(facts.items()):
        for symbol in fact.get("source_public_exports") or ():
            static_consumers = sorted(
                public_consumers.get((module, symbol), ()))
            registered_consumers_for_symbol = sorted(
                registered_symbol_consumers.get((module, symbol), ()))
            source_public_exports.append({
                "module": module,
                "symbol": symbol,
                "boundary_declared": (
                    symbol in declared_public.get(module, set())),
                "static_consumers": static_consumers,
                "registered_consumers": registered_consumers_for_symbol,
                "consumers": sorted(set(static_consumers) | set(
                    registered_consumers_for_symbol)),
            })

    private_rows = []
    actual_private_keys = set(private_consumption)
    for consumer, module, symbol in sorted(actual_private_keys):
        exception = declared_exceptions.get((consumer, module, symbol))
        private_rows.append({
            "module": module,
            "symbol": symbol,
            "consumer": consumer,
            "declaration_present": bool(exception),
            "content_sha256": (exception or {}).get("content_sha256"),
            "necessity": (exception or {}).get("necessity"),
            "retires_when": (exception or {}).get("retires_when"),
        })
    stale_exceptions = []
    for (consumer, module, symbol), exception in sorted(
            declared_exceptions.items()):
        if (consumer, module, symbol) in actual_private_keys:
            continue
        stale_exceptions.append({
            "module": module,
            "symbol": symbol,
            "consumer": consumer,
            "content_sha256": exception.get("content_sha256"),
            "necessity": exception.get("necessity"),
            "retires_when": exception.get("retires_when"),
        })

    module_consumers = collections.defaultdict(set)
    module_symbols = collections.defaultdict(set)
    for (module, symbol), consumers in public_consumers.items():
        module_consumers[module].update(consumers)
        module_symbols[module].add(symbol)
    for consumer, module, symbol in actual_private_keys:
        module_consumers[module].add(consumer)
        module_symbols[module].add(symbol)

    registered_capabilities = collections.defaultdict(set)
    registered_consumers = collections.defaultdict(set)
    for row in registry_relationships:
        owner = row["owner_module"]
        consumer = row["consumer_module"]
        if owner is None:
            continue
        registered_capabilities[owner].add(row["capability_id"])
        if consumer is not None and consumer != owner:
            registered_consumers[owner].add(consumer)

    registered_symbol_consumption = collections.defaultdict(set)
    for row in registered_symbol_relationships:
        owner = row.get("owner_module")
        consumer = row.get("consumer_module")
        symbol = row.get("symbol")
        if owner is not None and consumer is not None and symbol is not None:
            registered_symbol_consumption[owner].add((consumer, symbol))

    modules = []
    unclassified = []
    for name in sorted(facts):
        fact = facts[name]
        boundary = boundary_rows.get(name)
        classification = _classification(boundary, area_domains, layers)
        if boundary is None:
            classification["problems"].append("missing-boundary-entry")
            classification["problems"] = sorted(
                set(classification["problems"]))
            classification["resolved"] = False
        policy = policy_rows.get(name)
        exposure = policy.get("exposure") if policy else None
        owned_transports = sorted(
            transports_by_module.get(name, ()),
            key=lambda row: row["transport_id"])
        transport_ids = [row["transport_id"] for row in owned_transports]
        shared_mcp_transport_ids = sorted(
            row["transport_id"] for row in transport_rows
            if row["protocol"] == "mcp" and
            row["host_exposure"] == "shared-bridge")
        actual_consumers = sorted(module_consumers.get(name, ()))
        actual_symbols = sorted(module_symbols.get(name, ()))
        interface = {
            "cli": name in cli_modules,
            "cli_policy_declared": policy is not None,
            "mcp_tool": exposure == "mcp",
            "mcp_transport": any(
                row["protocol"] == "mcp" for row in owned_transports),
            "host": (
                "shared-bridge:%s" % ",".join(transport_ids)
                if owned_transports else
                "via:%s" % ",".join(shared_mcp_transport_ids)
                if exposure == "mcp" else "none"),
            "static_internal": bool(actual_consumers),
            "static_internal_symbol_count": len(actual_symbols),
            "static_internal_consumer_count": len(actual_consumers),
            "registered_internal": bool(registered_consumers.get(name)),
            "registered_capability_count": len(
                registered_capabilities.get(name, ())),
            "registered_consumer_count": len(
                registered_consumers.get(name, ())),
            "registered_symbol_consumer_count": len(
                registered_symbol_consumption.get(name, ())),
            "transport_ids": transport_ids,
            "policy_exposure": exposure,
            "workspace_access": policy.get("workspace_access")
            if policy else None,
            "external_write": policy.get("external_write")
            if policy else None,
        }
        module_row = {
            "module": name,
            "path": "Tools/" + fact["path"],
            "type": _source_type(fact["path"]),
            "classification": classification,
            "interface": interface,
            "declared_public_symbol_count": len(
                declared_public.get(name, ())),
            "source_public_exports": fact.get("source_public_exports"),
        }
        modules.append(module_row)
        if not classification["resolved"]:
            unclassified.append({
                "module": name,
                "path": module_row["path"],
                "problems": classification["problems"],
            })

    external_interfaces = []
    shared_mcp_transport_ids = sorted(
        row["transport_id"] for row in transport_rows
        if row["protocol"] == "mcp" and
        row["host_exposure"] == "shared-bridge")
    for tool, row in sorted(policy_rows.items()):
        exposure = row.get("exposure")
        external_interfaces.append({
            "tool": tool,
            "module_present": tool in facts,
            "cli": tool in cli_modules,
            "cli_policy_declared": True,
            "mcp": exposure == "mcp",
            "host": (
                "via:%s" % ",".join(shared_mcp_transport_ids)
                if exposure == "mcp" else "none"),
            "policy_exposure": exposure,
            "workspace_access": row.get("workspace_access"),
            "external_write": row.get("external_write"),
        })

    host_transports = []
    facts_by_path = _module_by_path(facts)
    for row in sorted(transport_rows, key=lambda value: value["transport_id"]):
        actual_module = facts_by_path.get(row["path"])
        host_transports.append({
            "transport_id": row["transport_id"],
            "protocol": row["protocol"],
            "mode": row["mode"],
            "host_exposure": row["host_exposure"],
            "module": row["module"],
            "path": row["path"],
            "server_name": row["server_name"],
            "command": row["command"],
            "module_present": row["module"] in facts,
            "path_matches_module": actual_module == row["module"],
        })

    declared_transport_consumption = [
        {
            "tool": row["tool"],
            "consumer_module": transport["module"],
            "transport_id": transport["transport_id"],
            "consumption_kind": "mcp-subprocess",
        }
        for row in external_interfaces if row["mcp"]
        for transport in host_transports if transport["protocol"] == "mcp"
    ]

    manifest_missing = sorted(set(facts) - set(boundary_rows))
    manifest_stale = sorted(set(boundary_rows) - set(facts))
    manifest_path_mismatches = []
    manifest_missing_public_symbols = []
    invalid_source_public_exports = []
    source_public_exports_undeclared = []
    for module in sorted(set(facts) & set(boundary_rows)):
        declared_path = boundary_rows[module].get("path")
        observed_path = "Tools/" + facts[module]["path"]
        if declared_path != observed_path:
            manifest_path_mismatches.append({
                "module": module,
                "declared_path": declared_path,
                "observed_path": observed_path,
            })
        for symbol in sorted(
                declared_public.get(module, set()) -
                set(facts[module]["top_level_symbols"])):
            manifest_missing_public_symbols.append({
                "module": module,
                "symbol": symbol,
            })
        if facts[module].get("source_public_export_errors"):
            invalid_source_public_exports.append({
                "module": module,
                "errors": facts[module]["source_public_export_errors"],
            })
        for symbol in sorted(
                set(facts[module].get("source_public_exports") or ()) -
                declared_public.get(module, set())):
            source_public_exports_undeclared.append({
                "module": module,
                "symbol": symbol,
            })
    cli_modules_missing_policy = sorted(cli_modules - set(policy_rows))
    policy_tools_missing_cli_module = sorted(set(policy_rows) - cli_modules)
    invalid_host_transports = [
        row for row in host_transports
        if not row["module_present"] or not row["path_matches_module"]
    ]
    undeclared_public = [
        row for row in public_interfaces
        if row["status"] == "undeclared-consumption"
    ]
    undeclared_registered_public = [
        row for row in observed_public_interfaces
        if row["status"] == "undeclared-consumption" and
        row["registered_consumers"]
    ]
    declared_unused = [
        {"module": row["module"], "symbol": row["symbol"]}
        for row in public_interfaces if row["status"] == "declared-unused"
    ]
    declared_without_observed_consumers = [
        {"module": row["module"], "symbol": row["symbol"]}
        for row in observed_public_interfaces
        if row["status"] == "declared-unused"
    ]
    missing_private_exceptions = [
        {"module": row["module"], "symbol": row["symbol"],
         "consumer": row["consumer"]}
        for row in private_rows if not row["declaration_present"]
    ]
    cycles = _cycles(facts)

    sources = []
    for path, raw in (
            (TAXONOMY_PATH, taxonomy_raw),
            (BOUNDARIES_PATH, boundaries_raw),
            (INTERFACE_POLICY_PATH, policy_raw),
            (CAPABILITIES_PATH, capabilities_raw)):
        sources.append({
            "path": path,
            "sha256": kblib.sha256_bytes(raw),
        })

    summary = {
        "shipped_modules": len(modules),
        "source_cli_tools": len(cli_modules),
        "declared_cli_tools": len(policy_rows),
        "mcp_tools": sum(1 for row in external_interfaces if row["mcp"]),
        "host_transports": len(host_transports),
        "static_public_api_symbols": len(public_interfaces),
        "declared_unused_static_public_apis": len(declared_unused),
        "declared_public_apis_without_observed_consumers": len(
            declared_without_observed_consumers),
        "registered_capability_relationships": len(registry_relationships),
        "registered_symbol_relationships": len(
            registered_symbol_relationships),
        "source_public_exports": len(source_public_exports),
        "source_public_exports_undeclared": len(
            source_public_exports_undeclared),
        "declared_transport_consumptions": len(
            declared_transport_consumption),
        "static_private_consumptions": len(private_rows),
        "missing_private_exceptions": len(missing_private_exceptions),
        "unclassified_modules": len(unclassified),
        "dependency_cycles": (
            len(cycles["module_cycles"]) + len(cycles["package_cycles"])),
    }

    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "artifact": "tool-catalog-projection",
        "authority": "navigation-only",
        "generated_by": "Tools/generate_tool_catalog.py",
        "sources": sources,
        "static_scan": {
            "owner": (
                "Tools/platform/distribution/module_boundary_facts.py"),
            "scope": "shipped production Python modules",
            "excluded_directories": sorted(
                module_boundary_facts.EXCLUDED_DIRS),
            "excluded_consumption_forms": list(
                module_boundary_facts.EXCLUDED_CONSUMPTION_FORMS),
        },
        "summary": summary,
        "taxonomy": {
            "areas": [
                {"area": area, "purpose": row.get("purpose"),
                 "domains": list(row.get("domains") or ())}
                for area, row in sorted(areas.items())
            ],
            "layers": [
                {"layer": layer, "purpose": row.get("purpose")}
                for layer, row in sorted(layers.items())
            ],
        },
        "hierarchy": _hierarchy(modules, areas, layers),
        "modules": modules,
        "static_public_interfaces": public_interfaces,
        "declared_unused_static_public_apis": declared_unused,
        "public_interfaces": observed_public_interfaces,
        "declared_public_apis_without_observed_consumers":
            declared_without_observed_consumers,
        "registered_capability_relationships": registry_relationships,
        "registered_symbol_relationships": registered_symbol_relationships,
        "source_public_exports": source_public_exports,
        "declared_transport_consumption": declared_transport_consumption,
        "external_interfaces": external_interfaces,
        "host_transports": host_transports,
        "private_consumption": {
            "actual": private_rows,
            "missing_exceptions": missing_private_exceptions,
            "stale_exceptions": stale_exceptions,
        },
        "unclassified_modules": unclassified,
        "cycles": cycles,
        "integrity": {
            "manifest_missing_modules": manifest_missing,
            "manifest_stale_modules": manifest_stale,
            "manifest_path_mismatches": manifest_path_mismatches,
            "manifest_missing_public_symbols":
                manifest_missing_public_symbols,
            "invalid_source_public_exports": invalid_source_public_exports,
            "source_public_exports_undeclared":
                source_public_exports_undeclared,
            "cli_modules_missing_policy": cli_modules_missing_policy,
            "policy_tools_missing_cli_module":
                policy_tools_missing_cli_module,
            "invalid_host_transports": invalid_host_transports,
            "unresolved_registry_paths": unresolved_registry_paths,
            "unresolved_registered_symbols":
                unresolved_registered_symbols,
            "undeclared_public_consumption": undeclared_public,
            "undeclared_registered_symbol_consumption":
                undeclared_registered_public,
        },
    }


def _cell(value):
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _code(value):
    if value is None:
        return "—"
    return "`%s`" % str(value).replace("`", "\\`")


def _list_or_none(values):
    materialized = tuple(values)
    return ", ".join(_code(value) for value in materialized) \
        if materialized else "—"


def _interfaces(module):
    interface = module["interface"]
    values = []
    if interface["cli"]:
        values.append("CLI")
    if interface["mcp_tool"]:
        values.append("MCP tool (%s)" % interface["host"])
    if interface["mcp_transport"]:
        values.append("MCP Host transport (%s)" % interface["host"])
    if interface["static_internal"]:
        values.append("static Python (%d symbols / %d consumers)" % (
            interface["static_internal_symbol_count"],
            interface["static_internal_consumer_count"]))
    if interface["registered_internal"]:
        values.append("registered capability (%d capabilities / %d consumers)"
                      % (interface["registered_capability_count"],
                         interface["registered_consumer_count"]))
    if interface["registered_symbol_consumer_count"]:
        values.append("registered Python symbol (%d consumers)" %
                      interface["registered_symbol_consumer_count"])
    return ", ".join(values) if values else "none observed"


def _table(lines, headings, rows):
    lines.append("| %s |" % " | ".join(headings))
    lines.append("|%s|" % "|".join("---" for _ in headings))
    for row in rows:
        lines.append("| %s |" % " | ".join(_cell(value) for value in row))


def render_markdown(catalog):
    """Render ``catalog`` as one stable, human-navigation projection."""
    lines = [
        "<!-- Generated by Tools/generate_tool_catalog.py. Do not edit. -->",
        "# Tool Catalog",
        "",
        "This file is a generated summary and navigation view. It does not "
        "define module responsibilities, public APIs, or interface authority. "
        "Those remain in the source contracts listed below and in the shipped "
        "Python source facts they classify.",
        "",
        "Regenerate with `python3 Tools/generate_tool_catalog.py .`. Verify "
        "without writing with `python3 Tools/generate_tool_catalog.py . "
        "--check`.",
        "",
        "## Sources",
        "",
    ]
    _table(lines, ("Source", "Exact-byte SHA-256"), [
        (_code(row["path"]), _code(row["sha256"]))
        for row in catalog["sources"]
    ])
    lines.extend([
        "",
        "Static consumption, private access, and dependency facts come from "
        "%s over %s; its excluded directories are %s. CLI and MCP exposure "
        "and the shared Host transport come only from `%s`. The static Python "
        "scan deliberately excludes %s; registered capability relationships "
        "and MCP subprocess routes are listed separately below rather than "
        "being mislabeled as Python symbol imports." % (
            _code(catalog["static_scan"]["owner"]),
            catalog["static_scan"]["scope"],
            _list_or_none(catalog["static_scan"]["excluded_directories"]),
            INTERFACE_POLICY_PATH,
            _list_or_none(
                catalog["static_scan"]["excluded_consumption_forms"])),
        "",
        "## Summary",
        "",
    ])
    summary = catalog["summary"]
    _table(lines, ("Measure", "Count"), [
        (key.replace("_", " "), value)
        for key, value in summary.items()
    ])

    lines.extend(["", "## Taxonomy", "", "### Areas", ""])
    _table(lines, ("Area", "Domains", "Declared purpose"), [
        (_code(row["area"]), _list_or_none(row["domains"]),
         row["purpose"] or "—")
        for row in catalog["taxonomy"]["areas"]
    ])
    lines.extend(["", "### Layers", ""])
    _table(lines, ("Layer", "Declared purpose"), [
        (_code(row["layer"]), row["purpose"] or "—")
        for row in catalog["taxonomy"]["layers"]
    ])

    module_by_name = {row["module"]: row for row in catalog["modules"]}
    lines.extend(["", "## Area → Domain → Layer → Module", ""])
    for area in catalog["hierarchy"]:
        lines.append("### Area: `%s`" % area["area"])
        lines.append("")
        if area["purpose"]:
            lines.append(area["purpose"])
            lines.append("")
        for domain in area["domains"]:
            lines.append("#### Domain: `%s`" % domain["domain"])
            lines.append("")
            for layer in domain["layers"]:
                lines.append("##### Layer: `%s`" % layer["layer"])
                lines.append("")
                if layer["purpose"]:
                    lines.append(layer["purpose"])
                    lines.append("")
                rows = []
                for name in layer["modules"]:
                    module = module_by_name[name]
                    classification = module["classification"]
                    responsibility = "%s / %s / %s" % (
                        classification["area"], classification["domain"],
                        classification["layer"])
                    rows.append((
                        _code(name), _code(module["path"]), module["type"],
                        _code(responsibility), _interfaces(module),
                    ))
                _table(lines, (
                    "Module", "Path", "Type", "Responsibility class",
                    "Interface exposure"), rows)
                lines.append("")

    lines.extend(["## Static Python symbol consumption", ""])
    public_rows = [
        (_code("%s.%s" % (row["module"], row["symbol"])),
         _list_or_none(row["consumers"]),
         "declared" if row["declared"] else "undeclared")
        for row in catalog["static_public_interfaces"]
        if row["consumers"]
    ]
    if public_rows:
        _table(lines, (
            "Owner and symbol", "Static Python consumers", "Boundary status"),
            public_rows)
    else:
        lines.append(
            "No static Python public-symbol consumption is declared or observed.")

    lines.extend(["", "## Registered Python symbol consumption", ""])
    registered_symbols = catalog["registered_symbol_relationships"]
    if registered_symbols:
        _table(lines, (
            "Registry identity", "Relationship", "Owner and symbol",
            "Consumer"), [
            (_code(row["identity"]), _code(row["relationship"]),
             _code("%s.%s" % (row["owner_module"], row["symbol"])),
             _code(row["consumer_module"]))
            for row in registered_symbols
        ])
    else:
        lines.append("None.")

    lines.extend(["", "## Source-declared Python exports", ""])
    source_exports = catalog["source_public_exports"]
    if source_exports:
        _table(lines, (
            "Owner and symbol", "Boundary declared", "Observed consumers"), [
            (_code("%s.%s" % (row["module"], row["symbol"])),
             "yes" if row["boundary_declared"] else "no",
             _list_or_none(row["consumers"]))
            for row in source_exports
        ])
    else:
        lines.append("None.")

    lines.extend([
        "", "## Declared public APIs without observed consumers", ""])
    unused = catalog["declared_public_apis_without_observed_consumers"]
    if unused:
        _table(lines, ("Owner module", "Symbol"), [
            (_code(row["module"]), _code(row["symbol"])) for row in unused
        ])
    else:
        lines.append("None.")

    lines.extend(["", "## Registered capability relationships", ""])
    registered = catalog["registered_capability_relationships"]
    if registered:
        _table(lines, (
            "Capability", "Kind", "Owner", "Relationship", "Consumer/route",
            "Same module"), [
            (_code(row["capability_id"]), _code(row["capability_kind"]),
             _code(row["owner_module"] or row["owner_path"]),
             _code(row["relationship"]),
             _code(row["consumer_module"] or row["consumer_path"]),
             "yes" if row["same_module"] else "no")
            for row in registered
        ])
    else:
        lines.append("None.")

    lines.extend(["", "## Declared CLI transport consumption", ""])
    transport_consumption = catalog["declared_transport_consumption"]
    if transport_consumption:
        _table(lines, ("CLI tool", "Consumer transport", "Transport", "Kind"), [
            (_code(row["tool"]), _code(row["consumer_module"]),
             _code(row["transport_id"]), _code(row["consumption_kind"]))
            for row in transport_consumption
        ])
    else:
        lines.append("None.")

    lines.extend(["", "## Host transports", ""])
    _table(lines, (
        "Transport", "Protocol", "Mode", "Host exposure", "Module", "Path",
        "Server", "Command", "Source match"), [
        (_code(row["transport_id"]), _code(row["protocol"]),
         _code(row["mode"]), _code(row["host_exposure"]),
         _code(row["module"]), _code(row["path"]),
         _code(row["server_name"]), _code(row["command"]),
         "yes" if row["module_present"] and row["path_matches_module"]
         else "no")
        for row in catalog["host_transports"]
    ])

    lines.extend(["", "## CLI, MCP, and Host exposure", ""])
    _table(lines, (
        "Tool", "Module present", "CLI", "MCP", "Host", "Policy exposure",
        "Workspace access", "External write"), [
        (_code(row["tool"]), "yes" if row["module_present"] else "no",
         "yes" if row["cli"] else "no", "yes" if row["mcp"] else "no",
         row["host"],
         _code(row["policy_exposure"]), _code(row["workspace_access"]),
         _code(row["external_write"]))
        for row in catalog["external_interfaces"]
    ])

    lines.extend(["", "## Private consumption and exceptions", ""])
    private = catalog["private_consumption"]
    if private["actual"]:
        _table(lines, (
            "Owner module", "Private symbol", "Consumer",
            "Exception declaration present",
            "Necessity", "Retires when"), [
            (_code(row["module"]), _code(row["symbol"]),
             _code(row["consumer"]),
             "yes" if row["declaration_present"] else "no",
             row["necessity"] or "—",
             row["retires_when"] or "—")
            for row in private["actual"]
        ])
    else:
        lines.append("No private cross-module consumption is observed.")
    lines.extend(["", "### Stale exception declarations", ""])
    if private["stale_exceptions"]:
        _table(lines, ("Owner module", "Private symbol", "Consumer"), [
            (_code(row["module"]), _code(row["symbol"]),
             _code(row["consumer"]))
            for row in private["stale_exceptions"]
        ])
    else:
        lines.append("None.")

    lines.extend(["", "## Unclassified modules", ""])
    if catalog["unclassified_modules"]:
        _table(lines, ("Module", "Path", "Problems"), [
            (_code(row["module"]), _code(row["path"]),
             _list_or_none(row["problems"]))
            for row in catalog["unclassified_modules"]
        ])
    else:
        lines.append("None.")

    lines.extend(["", "## Circular dependencies", ""])
    cycles = catalog["cycles"]
    cycle_rows = [
        ("module", "—", " → ".join(_code(value) for value in members))
        for members in cycles["module_cycles"]
    ] + [
        ("package", _code(row["package"]),
         " → ".join(_code(value) for value in row["members"]))
        for row in cycles["package_cycles"]
    ]
    if cycle_rows:
        _table(lines, ("Scope", "Package", "Cycle members"), cycle_rows)
    else:
        lines.append("None.")

    lines.extend(["", "## Integrity deviations", ""])
    integrity_rows = []
    for key in (
            "manifest_missing_modules", "manifest_stale_modules",
            "cli_modules_missing_policy", "policy_tools_missing_cli_module"):
        values = catalog["integrity"][key]
        integrity_rows.append((key.replace("_", " "),
                               _list_or_none(values)))
    integrity_rows.append((
        "manifest path mismatches",
        _list_or_none(
            "%s: %s != %s" % (
                row["module"], row["declared_path"], row["observed_path"])
            for row in catalog["integrity"]["manifest_path_mismatches"])))
    integrity_rows.append((
        "manifest public symbols missing from source",
        _list_or_none(
            "%s.%s" % (row["module"], row["symbol"])
            for row in catalog["integrity"][
                "manifest_missing_public_symbols"])))
    integrity_rows.append((
        "invalid source public export declarations",
        _list_or_none(
            "%s: %s" % (row["module"], "; ".join(row["errors"]))
            for row in catalog["integrity"][
                "invalid_source_public_exports"])))
    integrity_rows.append((
        "source public exports absent from boundary contract",
        _list_or_none(
            "%s.%s" % (row["module"], row["symbol"])
            for row in catalog["integrity"][
                "source_public_exports_undeclared"])))
    integrity_rows.append((
        "invalid host transports",
        _list_or_none(
            "%s: %s" % (row["transport_id"], row["path"])
            for row in catalog["integrity"]["invalid_host_transports"])))
    integrity_rows.append((
        "unresolved registry paths",
        _list_or_none(
            "%s.%s: %s" % (
                row["capability_id"], row["role"], row["path"])
            for row in catalog["integrity"]["unresolved_registry_paths"])))
    integrity_rows.append((
        "unresolved registered symbols",
        _list_or_none(
            "%s: %s.%s" % (
                row["identity"], row["owner_module"], row["symbol"])
            for row in catalog["integrity"][
                "unresolved_registered_symbols"])))
    integrity_rows.append((
        "undeclared public consumption",
        _list_or_none(
            "%s.%s" % (row["module"], row["symbol"])
            for row in catalog["integrity"][
                "undeclared_public_consumption"])))
    integrity_rows.append((
        "undeclared registered symbol consumption",
        _list_or_none(
            "%s.%s" % (row["module"], row["symbol"])
            for row in catalog["integrity"][
                "undeclared_registered_symbol_consumption"])))
    integrity_rows.append((
        "private consumption missing exception",
        _list_or_none(
            "%s.%s <- %s" % (
                row["module"], row["symbol"], row["consumer"])
            for row in private["missing_exceptions"])))
    _table(lines, ("Finding", "Members"), integrity_rows)
    lines.append("")
    return "\n".join(lines)


def render_json(catalog):
    """Render the machine projection with Cambium's canonical JSON bytes."""
    return kblib.canonical_json_bytes(catalog).decode("utf-8") + "\n"


def correctness_integrity_findings(catalog):
    """Return defects that make the observed Tool boundary non-conformant.

    The Catalog is deliberately a generated view, so generation must still be
    able to render a broken tree for diagnosis.  A freshness check has a
    stronger job: it must not turn a faithfully rendered defect into a green
    boundary verdict merely because the Markdown and JSON bytes are current.

    Observational facts such as a declared-but-unused public API remain in the
    Catalog without failing this gate.  Every row below instead represents a
    broken owner, classification, dependency, or declared interface edge.
    """
    if not isinstance(catalog, dict):
        raise ToolCatalogError("Tool catalog must be a mapping")
    findings = []
    integrity = catalog.get("integrity") or {}
    for key in (
            "manifest_missing_modules", "manifest_stale_modules",
            "manifest_path_mismatches", "manifest_missing_public_symbols",
            "invalid_source_public_exports",
            "source_public_exports_undeclared",
            "cli_modules_missing_policy",
            "policy_tools_missing_cli_module", "invalid_host_transports",
            "unresolved_registry_paths", "unresolved_registered_symbols",
            "undeclared_public_consumption",
            "undeclared_registered_symbol_consumption"):
        rows = integrity.get(key) or []
        if rows:
            findings.append({"kind": key, "count": len(rows)})

    unclassified = catalog.get("unclassified_modules") or []
    if unclassified:
        findings.append({
            "kind": "unclassified_modules", "count": len(unclassified)})

    cycles = catalog.get("cycles") or {}
    for key in ("module_cycles", "package_cycles"):
        rows = cycles.get(key) or []
        if rows:
            findings.append({"kind": key, "count": len(rows)})

    private = catalog.get("private_consumption") or {}
    for key in ("missing_exceptions", "stale_exceptions"):
        rows = private.get(key) or []
        if rows:
            findings.append({
                "kind": "private_%s" % key, "count": len(rows)})
    return findings


def _output_path(root, relative_path):
    return os.path.join(root, *relative_path.split("/"))


def _matches(path, expected):
    try:
        with open(path, "rb") as handle:
            return handle.read() == expected.encode("utf-8")
    except OSError:
        return False


def project_catalog(repo_root, *, check=False):
    """Write or byte-check both generated projections.

    Returns ``(exit_code, statuses)``.  Exit ``2`` means one or both tracked
    projections drifted.  Exit ``3`` means the projections are current but
    the observed Tool boundary contains a correctness-grade integrity defect.
    Source/input failures raise :class:`ToolCatalogError`.
    """
    root = os.path.realpath(os.path.abspath(os.fspath(repo_root)))
    catalog = build_catalog(root)
    outputs = (
        (MARKDOWN_OUTPUT, render_markdown(catalog)),
        (JSON_OUTPUT, render_json(catalog)),
    )
    statuses = []
    if check:
        for relative, rendered in outputs:
            current = _matches(_output_path(root, relative), rendered)
            statuses.append({"path": relative,
                             "status": "current" if current else "drift"})
        if not all(row["status"] == "current" for row in statuses):
            return 2, statuses
        findings = correctness_integrity_findings(catalog)
        if findings:
            statuses.append({
                "path": "<tool-boundary-integrity>",
                "status": "invalid",
                "findings": findings,
            })
            return 3, statuses
        return 0, statuses

    for relative, rendered in outputs:
        path = _output_path(root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            kblib.atomic_write_text(path, rendered)
        except OSError as exc:
            raise ToolCatalogError("cannot write %s: %s" % (
                relative, exc)) from exc
        statuses.append({"path": relative, "status": "written"})
    return 0, statuses


def main(argv=None):
    """Generate or byte-check both catalog projections."""
    parser = argparse.ArgumentParser(
        description=(
            "generate the non-authoritative Tool hierarchy and interface "
            "catalog from machine contracts and static source facts"))
    parser.add_argument(
        "root", nargs="?", default=os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))),
        help="Cambium repository root (default: source repository root)")
    parser.add_argument(
        "--check", action="store_true",
        help="compare both projections byte-for-byte without writing")
    args = parser.parse_args(argv)

    try:
        code, statuses = project_catalog(args.root, check=args.check)
    except ToolCatalogError as exc:
        print("%s: %s" % (TOOL, exc), file=sys.stderr)
        return 1
    for row in statuses:
        print("%s: %s: %s" % (TOOL, row["status"], row["path"]))
        for finding in row.get("findings") or ():
            print("%s: integrity: %s=%d" % (
                TOOL, finding["kind"], finding["count"]), file=sys.stderr)
    return code
