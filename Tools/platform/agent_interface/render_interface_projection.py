#!/usr/bin/env python3
"""render_interface_projection.py -- agent-facing form projections of the
compiled CLI invocation contract.

The selected target's registered `cli-contract.yaml` states, once, how every
shipped CLI is called. An agent runtime does not read that statement in that shape: it
reads a tool list in the shape its own protocol defines. This tool
projects the one contract into those shapes, so a protocol-shaped list is
a *derived view* of the compiled contract rather than a second, hand-kept
declaration of the same interface that can drift away from it.

It follows the projection pattern the distribution already uses for the
K08/09 page boundary block (`Tools/render_boundary_projection.py`): one
declaration source, one generator, and a `--check` mode that reports a
hand edit rather than silently re-adopting it. What differs is the
destination. Source-distribution projections remain tracked compiled artifacts
under `Tools/compiled/`. Carried-runtime projections are adopter-owned derived
state under `.cambium/derived/interfaces/`; they never overwrite a distributed
component.

Forms
-----
`FORMS` is a registry, not a special case. Each entry names its own
output path and its own builder, and `--form` selects one; with no
`--form` every registered form is written or checked in the same run, so
a second protocol shape joins `make check` by being registered here and
nowhere else. One form ships today:

  mcp   Model Context Protocol tool list -> the target's registered
        mcp-tools.json artifact

JSON, not YAML: the payload of the `mcp` form is JSON Schema. Carrying
JSON Schema inside the restricted YAML subset would add one lossy shape
conversion between the schema and every consumer of it, so the artifact
is serialized directly through `kblib.canonical_json_bytes`.

Upstream binding
----------------
Every artifact this tool writes carries `source_hash`, the sha256 of the
exact `cli-contract.yaml` bytes it was projected from, and
`source_manifest_hash`, that contract's own fingerprint of the tool
sources behind it. Downstream forms are never compared with each other:
they each bind the same upstream, so one upstream change invalidates all
of them at once and no pairwise agreement has to be maintained.

Exit codes
----------
  0  written / `--check` passed.
  1  the evidence is unreliable: the compiled contract is missing,
     unparseable, or not the artifact it claims to be; the contract
     changed underneath this run (see below); or a projected field could
     not be bound to a declaration source.
  2  `--check` mismatch: an output is stale or hand-edited. A HOLD a
     person must read, never a usage error -- usage errors are 1 through
     `kblib.ArgumentParser`.

The exit-1 "changed underneath this run" case is a time-of-check /
time-of-use guard: the contract bytes are re-read after the projection is
built and compared with the bytes it was built from. If they differ, this
run observed two different upstreams and its verdict -- pass or hold --
would describe neither, so it reports unreliable evidence instead of a
result.

This tool registers no K00/12 Gate ID and emits no receipts, for the same
reason `compile_cli_contract.py` does not: it depends on no selected
profile, so `run_gates` -- which cannot start before a profile is
selected -- could never sweep it, and the kernel requires an
unclassifiable registry row to fail the run closed. `make check` runs it
directly instead.
"""
from Tools.platform.repository.repository import repository_source_root, tools_source_root

import json
import os
import re
import sys

TOOLS_DIR = tools_source_root(__file__)
REPO_ROOT = repository_source_root(__file__)

import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.agent_interface.cli_argv_renderer as cli_argv_renderer  # noqa: E402
import Tools.platform.agent_interface.agent_interface_contract as agent_interface_contract  # noqa: E402
import Tools.execution.task_runtime.runtime_paths as runtime_paths  # noqa: E402
import Tools.platform.agent_interface.tool_availability as tool_availability  # noqa: E402
from Tools.platform.repository.repository import (  # noqa: E402
    file_bytes_sha256,
    repository_relative_spelling,
)

TOOL = "render_interface_projection"
TOOL_VERSION = "1.6.0"

SCHEMA_VERSION = agent_interface_contract.PROJECTION_SCHEMA_VERSION
ARTIFACT_KIND = agent_interface_contract.PROJECTION_ARTIFACT_KIND
DEFAULT_CONTRACT = "Tools/compiled/cli-contract.yaml"
CARRIED_RUNTIME_CONTRACT = runtime_paths.CLI_CONTRACT_ARTIFACT_PATH
UPSTREAM_ARTIFACT = "cli-invocation-contract"
UPSTREAM_SCHEMA_VERSION = 9
UPSTREAM_FIELDS = frozenset((
    "schema_version", "artifact", "generator", "generator_version",
    "derived_from", "source_files", "source_hash",
    "agent_interface_policy", "runtime_path_registry", "projection_target",
    "distribution_boundary", "included_tools", "excluded_tools",
    "receipt_shape", "tool_count", "tools",
))
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

# The transports the `mcp` form declares. Deliberately two, and
# deliberately not four.
#
# Declaration source: this constant. It is the one value in the projection
# that the compiled contract does not contain -- the compiled contract
# describes argv, and says nothing about how an agent runtime reaches a
# process -- so rather than being decided silently inside the builder it is
# declared here, with the observation it rests on:
#
#   - the Codex client reports, verbatim, `legacy SSE transport is not
#     supported`; and
#   - `dsh` offers exactly `stdio|streamable-http`.
#
# A shape no reachable client accepts is not a projection of anything, so
# no `sse` and no `websocket` branch is emitted. Their absence is
# structural: there is no key for them to be false in.
MCP_TRANSPORTS = ("stdio", "streamable-http")

# argparse `type=` names -> JSON Schema `type`. A name that is not here --
# any custom converter callable -- projects as the default below, which is
# what argv actually carries; the declared converter name travels intact in
# `x-cambium-cli.type` so nothing is lost by the fallback.
JSON_SCALAR_TYPES = cli_argv_renderer.JSON_SCALAR_TYPES
# argparse hands an argument's `type` callable a string, and 268 of the 275
# declared arguments declare no `type` at all. `string` is therefore the
# accurate projection of an undeclared type, not a weak one.
DEFAULT_SCALAR_TYPE = cli_argv_renderer.DEFAULT_SCALAR_TYPE

LIST_ACTIONS = cli_argv_renderer.LIST_ACTIONS
COUNT_ACTIONS = cli_argv_renderer.COUNT_ACTIONS

CLI_EXTENSION_KEY = cli_argv_renderer.CLI_EXTENSION_KEY
EXCLUSIVE_EXTENSION_KEY = "x-cambium-mutually-exclusive"
PATH_EXTENSION_KEY = agent_interface_contract.PATH_EXTENSION_KEY
WORKSPACE_EXTENSION_KEY = agent_interface_contract.WORKSPACE_EXTENSION_KEY

NOTICE = (
    "Generated artifact -- do not edit. Every value here is projected from "
    "the selected target's compiled CLI contract by Tools/%s.py; a hand edit "
    "is reported by --check as a HOLD." % TOOL
)
NOT_A_REVISION_BASIS = (
    "This file is downstream of each tool's own argparse declaration and is "
    "never the basis for revising one. To change what an agent may call, "
    "change the tool's argparse block or the closed agent-interface policy, "
    "recompile %s, then regenerate this "
    "file." % DEFAULT_CONTRACT
)
REGENERATE = "python3 Tools/%s.py ." % TOOL
VERIFY = "python3 Tools/%s.py . --check" % TOOL


def invocation_for_projection_target(projection_target, check=False):
    parts = ["python3 Tools/%s.py ." % TOOL]
    if projection_target != tool_availability.SOURCE_DISTRIBUTION:
        parts.append("--projection-target %s" % projection_target)
    if check:
        parts.append("--check")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Declaration sources for every projected field (self-checked below)
# ---------------------------------------------------------------------------

# Each key is a normalized path into a produced artifact; each value names
# where that field comes from. Nothing may be emitted that is not bound
# here: `unbound_field_paths` walks the artifact this run actually built
# and reports any path this table does not cover, which exits 1. The table
# is therefore not documentation about the projection -- it is the
# projection's own admission rule, and a field invented in the builder
# fails the run rather than reaching the artifact.
FIELD_SOURCES = {
    # -- envelope ---------------------------------------------------------
    "schema_version":
        "Tools/render_interface_projection.py: SCHEMA_VERSION (this "
        "artifact's own shape version)",
    "artifact":
        "Tools/platform/agent_interface/agent_interface_contract.py: "
        "PROJECTION_ARTIFACT_KIND",
    "form":
        "Tools/render_interface_projection.py: the selected FORMS key",
    "generator":
        "Tools/render_interface_projection.py: module path",
    "generator_version":
        "Tools/render_interface_projection.py: TOOL_VERSION",
    "source":
        "the --contract path this run read, repository-relative",
    "source_artifact":
        "Tools/compiled/cli-contract.yaml: artifact",
    "source_schema_version":
        "Tools/compiled/cli-contract.yaml: schema_version",
    "source_hash":
        "sha256 of the selected cli-contract.yaml bytes this run "
        "read (kblib.sha256_bytes)",
    "source_manifest_hash":
        "selected cli-contract.yaml: source_hash (its own manifest "
        "of the tool sources it was compiled from)",
    "projection_target":
        "selected cli-contract.yaml: projection_target",
    "tool_count":
        "count of Tools/compiled/cli-contract.yaml: tools[] whose "
        "agent_interface.exposure is mcp",
    "generated.notice":
        "Tools/render_interface_projection.py: NOTICE; rule owner "
        "kernel/K08 Metadata and Status/07 Frontmatter Writer and "
        "Projection Authority (a projection is regenerated, never "
        "hand-edited)",
    "generated.not_a_revision_basis":
        "Tools/render_interface_projection.py: NOT_A_REVISION_BASIS; same "
        "rule owner, direction half",
    "generated.regenerate":
        "Tools/render_interface_projection.py: "
        "invocation_for_projection_target",
    "generated.verify":
        "Tools/render_interface_projection.py: "
        "invocation_for_projection_target(check=True)",

    # -- mcp form ---------------------------------------------------------
    "transports[]":
        "Tools/render_interface_projection.py: MCP_TRANSPORTS (client "
        "support observed, see the constant's comment)",
    "tools[].name":
        "Tools/compiled/cli-contract.yaml: tools[].tool",
    "tools[].description":
        "Tools/compiled/cli-contract.yaml: tools[].description (omitted "
        "when the tool declares none)",
    "tools[].inputSchema.type":
        "JSON Schema: an MCP inputSchema is an object schema",
    "tools[].inputSchema.additionalProperties":
        "argparse rejects an option it did not declare, and "
        "kblib.ArgumentParser spends 1 on that rejection",
    "tools[].inputSchema.required[]":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].dest where "
        "required is true (omitted when no argument is required)",
    "tools[].inputSchema.properties":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].dest "
        "(recorded as an empty object for a tool with no arguments)",
    "tools[].inputSchema.properties.*.type":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].type via "
        "JSON_SCALAR_TYPES, DEFAULT_SCALAR_TYPE for an undeclared or "
        "custom converter; boolean/integer/array from action and nargs",
    "tools[].inputSchema.properties.*.description":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].help "
        "(omitted when the argument declares none)",
    "tools[].inputSchema.properties.*.enum[]":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].choices "
        "(omitted when the argument declares none)",
    "tools[].inputSchema.properties.*.default":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].default "
        "(omitted when it is null or argparse.SUPPRESS)",
    "tools[].inputSchema.properties.*.items.type":
        "same as .type, for the element of a list-valued argument",
    "tools[].inputSchema.properties.*.items.enum[]":
        "same as .enum, for the element of a list-valued argument",
    "tools[].inputSchema.properties.*.minItems":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].nargs -- "
        "'+' consumes one or more, an integer n consumes exactly n",
    "tools[].inputSchema.properties.*.maxItems":
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].nargs -- "
        "an integer n consumes exactly n",
    "tools[].inputSchema.properties.*.%s.option_strings[]"
    % CLI_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].arguments[].option_strings, verbatim; empty exactly for a "
        "positional, which is that artifact's own stated rule",
    "tools[].inputSchema.properties.*.%s.option_strings"
    % CLI_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].arguments[].option_strings, verbatim; the empty list is "
        "the positional case",
    "tools[].inputSchema.properties.*.%s.action" % CLI_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].action, "
        "verbatim",
    "tools[].inputSchema.properties.*.%s.nargs" % CLI_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].nargs, "
        "verbatim (omitted when the argument declares none)",
    "tools[].inputSchema.properties.*.%s.type" % CLI_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: tools[].arguments[].type, "
        "verbatim (omitted when the argument declares none)",
    "tools[].inputSchema.properties.*.%s.access" % PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].access for the matching "
        "argument",
    "tools[].inputSchema.properties.*.%s.consumption" % PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].consumption for the "
        "matching argument",
    "tools[].inputSchema.properties.*.%s.constraint" % PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].constraint for the "
        "matching argument",
    "tools[].inputSchema.properties.*.%s.value" % PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].value for the matching "
        "argument",
    "tools[].inputSchema.properties.*.%s.suffixes[]" % PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].suffixes for the matching "
        "argument",
    "tools[].inputSchema.properties.*.%s.suffixes" % PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].suffixes for the matching "
        "argument; the empty list is the no-suffix-constraint case",
    "tools[].inputSchema.properties.*.%s.active_when_any[]" %
        PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].active_when_any for the "
        "matching argument; the empty list means no positive mode condition",
    "tools[].inputSchema.properties.*.%s.active_when_any" %
        PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].active_when_any for the "
        "matching argument",
    "tools[].inputSchema.properties.*.%s.inactive_when_any[]" %
        PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].inactive_when_any for the "
        "matching argument; the empty list means no excluding mode condition",
    "tools[].inputSchema.properties.*.%s.inactive_when_any" %
        PATH_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.path_arguments[].inactive_when_any for the "
        "matching argument",
    "tools[].%s.argument" % WORKSPACE_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.workspace_argument",
    "tools[].%s.access" % WORKSPACE_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].agent_interface.workspace_access",
    "tools[].%s[].required" % EXCLUSIVE_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].mutually_exclusive_groups[].required",
    "tools[].%s[].dests[]" % EXCLUSIVE_EXTENSION_KEY:
        "Tools/compiled/cli-contract.yaml: "
        "tools[].mutually_exclusive_groups[].dests",
}

# A default is copied out of the compiled contract whole; its interior is
# that artifact's shape, not a shape this projection composes, so the walk
# stops there rather than pretending to bind each element separately.
OPAQUE_PATHS = frozenset({
    "tools[].inputSchema.properties.*.default",
})

# Mappings whose keys are data (argument names), not field names. Their
# children collapse to `*` so one entry in FIELD_SOURCES covers every
# argument of every tool.
DATA_KEYED_PATHS = frozenset({
    "tools[].inputSchema.properties",
})


class ProjectionError(Exception):
    """The evidence for this run is unreliable; it must exit 1."""


def fail(message):
    print("%s: %s" % (TOOL, message))
    return 1


# ---------------------------------------------------------------------------
# Upstream
# ---------------------------------------------------------------------------


def read_contract(path):
    """Return (parsed contract, sha256 of the bytes it was parsed from)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ProjectionError(
            "cannot read the compiled CLI contract %s: %s -- compile it with "
            "`python3 Tools/compile_cli_contract.py . --projection-target <target>`" % (path, exc))
    try:
        contract = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except (UnicodeError, kblib.YamlSubsetError) as exc:
        raise ProjectionError(
            "the compiled CLI contract %s does not parse: %s" % (path, exc))
    if not isinstance(contract, dict):
        raise ProjectionError(
            "the compiled CLI contract %s is not a mapping" % path)
    if contract.get("artifact") != UPSTREAM_ARTIFACT:
        raise ProjectionError(
            "%s is not the %s artifact (it declares %r)"
            % (path, UPSTREAM_ARTIFACT, contract.get("artifact")))
    if contract.get("schema_version") != UPSTREAM_SCHEMA_VERSION:
        raise ProjectionError(
            "%s declares schema_version %r; this projection is written "
            "against %d" % (path, contract.get("schema_version"),
                            UPSTREAM_SCHEMA_VERSION))
    if set(contract) != UPSTREAM_FIELDS:
        raise ProjectionError(
            "%s does not carry the closed schema_version %d field set" %
            (path, UPSTREAM_SCHEMA_VERSION))
    if not isinstance(contract.get("source_hash"), str):
        raise ProjectionError("%s carries no source_hash" % path)
    if contract.get("projection_target") not in \
            tool_availability.PROJECTION_TARGETS:
        raise ProjectionError(
            "%s carries no valid projection_target" % path)
    tools = contract.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ProjectionError("%s carries no tools" % path)
    for record in tools:
        if not isinstance(record, dict) or not record.get("tool"):
            raise ProjectionError("%s carries an unnamed tool record" % path)
        if not isinstance(record.get("arguments"), list):
            raise ProjectionError(
                "%s: tool %r carries no arguments list"
                % (path, record.get("tool")))
        interface = record.get("agent_interface")
        if not isinstance(interface, dict) or \
                set(interface) != {
                    "exposure", "workspace_argument", "workspace_access",
                    "value_arguments", "path_arguments", "external_write",
                } or interface.get("exposure") not in ("mcp", "cli-only"):
            raise ProjectionError(
                "%s: tool %r carries no closed agent-interface policy"
                % (path, record.get("tool")))
        arguments = {item.get("dest") for item in record["arguments"]}
        values = interface.get("value_arguments")
        paths = interface.get("path_arguments")
        if not isinstance(values, list) or not isinstance(paths, list):
            raise ProjectionError(
                "%s: tool %r carries no closed argument classification" %
                (path, record.get("tool")))
        path_names = set()
        for item in paths:
            if not isinstance(item, dict) or set(item) != {
                    "argument", "access", "consumption", "constraint", "value",
                    "runtime_path_id", "suffixes",
                    "active_when_any",
                    "inactive_when_any"}:
                raise ProjectionError(
                    "%s: tool %r carries a malformed path capability" %
                    (path, record.get("tool")))
            runtime_path_id = item.get("runtime_path_id")
            if runtime_path_id is not None and (
                    not isinstance(runtime_path_id, str) or
                    not runtime_path_id):
                raise ProjectionError(
                    "%s: tool %r carries a malformed runtime_path_id" %
                    (path, record.get("tool")))
            path_names.add(item.get("argument"))
        classified = set(values) | path_names
        workspace_argument = interface.get("workspace_argument")
        if workspace_argument is not None:
            classified.add(workspace_argument)
        if classified != arguments or len(path_names) != len(paths) or \
                len(set(values)) != len(values) or set(values) & path_names:
            raise ProjectionError(
                "%s: tool %r agent-interface arguments do not close over "
                "its argparse contract" % (path, record.get("tool")))
        if workspace_argument is not None and \
                (workspace_argument in values or
                 workspace_argument in path_names):
            raise ProjectionError(
                "%s: tool %r classifies its workspace argument twice" %
                (path, record.get("tool")))
        if interface["exposure"] == "mcp" and \
                (workspace_argument not in arguments or
                 interface.get("workspace_access") not in ("read", "write")):
            raise ProjectionError(
                "%s: MCP tool %r carries no valid workspace binding" %
                (path, record.get("tool")))
    return contract, kblib.sha256_bytes(raw)


# ---------------------------------------------------------------------------
# argparse -> JSON Schema
# ---------------------------------------------------------------------------


def scalar_type(argument):
    declared = argument.get("type")
    if declared is None:
        return DEFAULT_SCALAR_TYPE
    return JSON_SCALAR_TYPES.get(declared, DEFAULT_SCALAR_TYPE)


def scalar_schema(argument):
    schema = {"type": scalar_type(argument)}
    choices = argument.get("choices")
    if choices:
        schema["enum"] = list(choices)
    return schema


def is_list_valued(argument):
    """True when one occurrence of this argument yields a list.

    `append`/`extend` accumulate across occurrences; an `nargs` of `*`,
    `+`, or an integer consumes several argv words into a list. `nargs` 0
    is the zero-value presence flag handled before this is consulted.
    """
    nargs = argument.get("nargs")
    if argument.get("action") in LIST_ACTIONS:
        return True
    if nargs in ("*", "+"):
        return True
    return isinstance(nargs, int) and not isinstance(nargs, bool) and nargs >= 1


def property_schema(argument, path_capability=None):
    """One JSON Schema property for one declared argument."""
    action = argument.get("action")
    nargs = argument.get("nargs")

    if action in COUNT_ACTIONS:
        schema = {"type": "integer"}
    elif nargs == 0:
        # An action consuming zero argv words is a presence flag: what a
        # caller decides is whether to pass it.
        schema = {"type": "boolean"}
    elif is_list_valued(argument):
        schema = {"type": "array", "items": scalar_schema(argument)}
        if nargs == "+":
            schema["minItems"] = 1
        elif isinstance(nargs, int) and not isinstance(nargs, bool):
            schema["minItems"] = nargs
            schema["maxItems"] = nargs
    else:
        schema = scalar_schema(argument)

    help_text = argument.get("help")
    if help_text:
        schema["description"] = help_text
    if argument.get("default") is not None and \
            argument.get("default_type") != "argparse.SUPPRESS":
        schema["default"] = argument["default"]

    extension = {
        "option_strings": list(argument.get("option_strings") or []),
        "action": action,
    }
    if nargs is not None:
        extension["nargs"] = nargs
    if argument.get("type") is not None:
        extension["type"] = argument["type"]
    schema[CLI_EXTENSION_KEY] = extension
    if path_capability is not None:
        schema[PATH_EXTENSION_KEY] = {
            "access": path_capability["access"],
            "consumption": path_capability["consumption"],
            "constraint": path_capability["constraint"],
            "value": path_capability["value"],
            "suffixes": list(path_capability["suffixes"]),
            "active_when_any": list(path_capability["active_when_any"]),
            "inactive_when_any": list(
                path_capability["inactive_when_any"]),
        }
    return schema


def input_schema(record):
    """The MCP `inputSchema` for one tool record of the compiled contract."""
    properties = {}
    required = []
    path_capabilities = {
        item["argument"]: item
        for item in record["agent_interface"].get("path_arguments") or []
    }
    for argument in record["arguments"]:
        dest = argument["dest"]
        properties[dest] = property_schema(
            argument, path_capability=path_capabilities.get(dest))
        if argument.get("required"):
            required.append(dest)
    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def mcp_tool(record):
    tool = {"name": record["tool"], "inputSchema": input_schema(record)}
    tool[WORKSPACE_EXTENSION_KEY] = {
        "argument": record["agent_interface"]["workspace_argument"],
        "access": record["agent_interface"]["workspace_access"],
    }
    if record.get("description"):
        tool["description"] = record["description"]
    groups = [
        {"required": bool(group.get("required")),
         "dests": list(group.get("dests") or [])}
        for group in record.get("mutually_exclusive_groups") or []
        if group.get("dests")
    ]
    if groups:
        tool[EXCLUSIVE_EXTENSION_KEY] = groups
    return tool


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def build_envelope(form_name, contract, contract_hash, source_spelling):
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": ARTIFACT_KIND,
        "form": form_name,
        "generator": "Tools/%s.py" % TOOL,
        "generator_version": TOOL_VERSION,
        "source": source_spelling,
        "source_artifact": contract["artifact"],
        "source_schema_version": contract["schema_version"],
        "source_hash": contract_hash,
        "source_manifest_hash": contract["source_hash"],
        "projection_target": contract["projection_target"],
        "tool_count": len(contract["tools"]),
        "generated": {
            "notice": NOTICE,
            "not_a_revision_basis": NOT_A_REVISION_BASIS,
            "regenerate": invocation_for_projection_target(
                contract["projection_target"]),
            "verify": invocation_for_projection_target(
                contract["projection_target"], check=True),
        },
    }


def build_mcp(form_name, contract, contract_hash, source_spelling):
    records = [
        record for record in contract["tools"]
        if record["agent_interface"]["exposure"] == "mcp"
    ]
    artifact = build_envelope(
        form_name, contract, contract_hash, source_spelling)
    artifact["tool_count"] = len(records)
    artifact["transports"] = list(MCP_TRANSPORTS)
    artifact["tools"] = [mcp_tool(record) for record in records]
    return artifact


FORMS = {
    "mcp": {
        "output": "Tools/compiled/mcp-tools.json",
        "runtime_output": runtime_paths.MCP_TOOLS_ARTIFACT_PATH,
        "build": build_mcp,
        "summary": "Model Context Protocol tool list (name, description, "
                   "inputSchema)",
    },
}


def contract_for_projection_target(projection_target):
    if projection_target == tool_availability.SOURCE_DISTRIBUTION:
        return DEFAULT_CONTRACT
    if projection_target == tool_availability.CARRIED_RUNTIME:
        return CARRIED_RUNTIME_CONTRACT
    raise ValueError("unknown projection target: %r" % projection_target)


def output_for_projection_target(form, projection_target):
    entry = FORMS[form]
    if projection_target == tool_availability.SOURCE_DISTRIBUTION:
        return entry["output"]
    if projection_target == tool_availability.CARRIED_RUNTIME:
        return entry["runtime_output"]
    raise ValueError("unknown projection target: %r" % projection_target)


# ---------------------------------------------------------------------------
# Field-source self-check
# ---------------------------------------------------------------------------


def artifact_field_paths(node, path=""):
    """Every normalized field path present in one built artifact."""
    if path in OPAQUE_PATHS:
        return {path}
    if isinstance(node, dict):
        if not node:
            return {path}
        found = set()
        for key in sorted(node):
            child = "%s.*" % path if path in DATA_KEYED_PATHS else \
                ("%s.%s" % (path, key) if path else key)
            found |= artifact_field_paths(node[key], child)
        return found
    if isinstance(node, list):
        if not node:
            return {path}
        found = set()
        for item in node:
            found |= artifact_field_paths(item, path + "[]")
        return found
    return {path}


def unbound_field_paths(artifact):
    """Paths this artifact emits that no declaration source covers."""
    return sorted(artifact_field_paths(artifact) - set(FIELD_SOURCES))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def render(artifact):
    return kblib.canonical_json_bytes(artifact).decode("utf-8") + "\n"


def validate_json(text):
    json.loads(text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def print_sources():
    print("%s: %d projected field path(s), each bound to a declaration "
          "source" % (TOOL, len(FIELD_SOURCES)))
    for path in sorted(FIELD_SOURCES):
        print("  %s\n      <- %s" % (path, FIELD_SOURCES[path]))


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Project the compiled CLI invocation contract into the "
                    "agent-facing interface forms registered in this tool.")
    parser.add_argument(
        "root",
        help="repository root holding the compiled CLI contract")
    parser.add_argument(
        "--form", choices=sorted(FORMS), default=None,
        help="project only this form (default: every registered form)")
    parser.add_argument(
        "--contract", default=None,
        help="compiled CLI contract to project; defaults to the one owned "
             "by --projection-target")
    parser.add_argument(
        "--projection-target",
        choices=list(tool_availability.PROJECTION_TARGETS),
        default=tool_availability.SOURCE_DISTRIBUTION,
        help="project the tracked source distribution or adopter-owned "
             "carried runtime (default: source-distribution)")
    parser.add_argument(
        "--output", default=None,
        help="artifact path to write or verify; requires --form, because "
             "one path cannot hold two forms")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true",
        help="recompute and compare against the existing artifacts; exit 0 "
             "when byte-identical, 2 when one is stale or hand-edited")
    mode.add_argument(
        "--sources", action="store_true",
        help="print the declaration source of every projected field and "
             "exit without reading or writing any artifact")
    args = parser.parse_args(argv)

    if args.sources:
        print_sources()
        return 0

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        return fail("root is not a directory: %s" % args.root)
    forms = [args.form] if args.form else sorted(FORMS)
    if args.output and args.form is None:
        parser.error("--output names one artifact; pass --form to say which "
                     "form it holds")
    contract_relative = contract_for_projection_target(args.projection_target)
    contract_path = args.contract or os.path.join(root, contract_relative)
    if not os.path.isabs(contract_path):
        contract_path = os.path.join(root, contract_path)
    if args.projection_target == tool_availability.CARRIED_RUNTIME:
        try:
            contract_path = kblib.registered_repository_artifact_path(
                root, contract_path, CARRIED_RUNTIME_CONTRACT)
        except ValueError as exc:
            return fail("unsafe carried-runtime contract input: %s" % exc)

    try:
        contract, contract_hash = read_contract(contract_path)
    except ProjectionError as exc:
        return fail("evidence is unreliable: %s" % exc)
    if contract["projection_target"] != args.projection_target:
        return fail(
            "evidence is unreliable: %s was compiled for projection target "
            "%r, not requested target %r"
            % (repository_relative_spelling(root, contract_path),
               contract["projection_target"], args.projection_target))

    outputs = {}
    for form_name in forms:
        registered_output = output_for_projection_target(
            form_name, args.projection_target)
        try:
            outputs[form_name] = kblib.registered_repository_artifact_path(
                root, args.output or registered_output, registered_output)
        except ValueError as exc:
            return fail(
                "unsafe %s artifact output for projection target %s: %s"
                % (form_name, args.projection_target, exc))

    source_spelling = repository_relative_spelling(root, contract_path)
    rendered = []
    for form_name in forms:
        form = FORMS[form_name]
        artifact = form["build"](
            form_name, contract, contract_hash, source_spelling)
        unbound = unbound_field_paths(artifact)
        if unbound:
            return fail(
                "evidence is unreliable: the %s form emits field(s) no "
                "declaration source covers: %s -- add the source to "
                "FIELD_SOURCES or stop emitting the field; a projection "
                "layer decides nothing on its own"
                % (form_name, ", ".join(unbound)))
        try:
            text = render(artifact)
        except (TypeError, ValueError) as exc:
            return fail("the %s form is not renderable: %s"
                        % (form_name, exc))
        output = outputs[form_name]
        rendered.append((form_name, output, text, artifact))

    # Time-of-check / time-of-use: everything above was projected from the
    # bytes read once at the start. If the contract has moved since, this
    # run holds no reliable evidence about either version of it.
    try:
        recheck = file_bytes_sha256(contract_path)
    except OSError as exc:
        return fail("evidence is unreliable: the compiled CLI contract "
                    "became unreadable during this run: %s" % exc)
    if recheck != contract_hash:
        return fail(
            "evidence is unreliable: %s changed while this run was reading "
            "it (%s -> %s); nothing was written and no verdict is reported"
            % (repository_relative_spelling(root, contract_path),
               contract_hash, recheck))

    if args.check:
        stale = 0
        for form_name, output, text, artifact in rendered:
            try:
                existing = kblib.read_text(output)
            except OSError as exc:
                print("%s --check: cannot read %s: %s" % (TOOL, output, exc))
                stale += 1
                continue
            if existing != text:
                print("%s --check: %s is stale or hand-edited; regenerate it "
                      "with `%s`" %
                      (TOOL, output, artifact["generated"]["regenerate"]))
                stale += 1
                continue
            print("%s --check: %s is current (%s form, %d tool(s))"
                  % (TOOL, output, form_name, artifact["tool_count"]))
        return 2 if stale else 0

    for form_name, output, text, artifact in rendered:
        kblib.atomic_write_text(output, text, validator=validate_json)
        print("%s: wrote %s (%s form, %d tool(s), %d byte(s))"
              % (TOOL, output, form_name, artifact["tool_count"], len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
