#!/usr/bin/env python3
"""compile_cli_contract.py -- persistent CLI invocation-contract compiler.

Deterministically derives one machine-readable calling contract for every
CLI tool shipped under `Tools/`, closes the host-facing capability surface
against `Tools/agent-interface-policy.yaml`, and writes the result to the
registered CLI-contract artifact. The source distribution owns the tracked
`Tools/compiled/cli-contract.yaml`; an adopter carrying the runtime owns only
the derived `.cambium/derived/interfaces/cli-contract.yaml` projection.

Why this exists: an agent should not have to read every argparse block or
trust prose that restates them. Argparse is the single source of invocation
shape. The separate policy is the single source of capability shape: MCP
exposure, workspace binding, typed path access, and declared external effects.
This compiler requires both sets to close exactly.

Extraction:
  - Each public adapter is resolved through its literal
    `IMPLEMENTATION_MODULE` edge. That unique owner is loaded through
    `importlib` under its own name, with
    `argparse.ArgumentParser.parse_args` monkey-patched to raise as soon as
    the parser is complete. The tool's `main()` therefore builds its parser
    and stops; not one line of its own behaviour runs. The patch is removed
    again before this process does anything else.
  - Module import is side-effect free by construction here: the only
    top-level call in these modules is `sys.path.insert`. This compiler
    additionally disables bytecode writing, so it touches no file that any
    tool would write. It is read-only with respect to the repository.
  - The common Receipt envelope is projected directly from
    `kblib.make_receipt`, its current machine producer, and that owner's
    source bytes always join the manifest. Receipt extension fields are
    derived per tool by a static AST walk over the implementation owner and
    the imported `make_*receipt` functions it calls. The exact helper sources
    join the manifest. Factory input parameter names are never mistaken for
    output fields; a mapping write whose keys are computed at runtime is
    reported as `partial`, never as complete. No field list is copied from
    `schemas/receipt.template.jsonl`, whose examples are navigation-only and
    not exhaustive.
  - Agent-interface policy rows name every discovered CLI exactly once, and
    classify every argparse argument exactly once as workspace, path, or value.
    An MCP-exposed row may not declare an external-write capability; exact and
    namespace paths remain explicit data rather than server conventions.
    Runtime paths name their stable ``runtime_paths`` identity in policy and
    the compiler resolves it to the current physical path. Component-owned
    paths remain the responsibility of their own machine contract; they are
    not rebound through the agent-interface policy.

Determinism: `prog` is not recorded (argparse derives it from `sys.argv`),
and the auto-added `-h/--help` action is skipped (its help text is
gettext-translated and therefore locale-dependent). Absolute defaults are
rewritten to repository-relative spellings, and `choices` is recorded as a
canonically ordered set because several tools derive it from a Python set.
Serialization goes through the
shared `kblib.canonical_yaml` renderer and fingerprints through
`kblib.sha256_bytes`; this module owns no serializer of its own.

Modes:
  default  recompute and write --output with a generated header.
  --check  recompute and compare against the existing output; exit 0 when
           byte-identical, 2 otherwise.

Exit codes: 0 = ok / check passed; 1 = the evidence is unreliable (a tool
            failed to import, or its parser could not be recovered);
            2 = --check mismatch, which is a HOLD a person must read.

This tool registers no K00/12 Gate ID and emits no receipts. It is a
compiled-artifact freshness check that runs before any profile is selected,
which is exactly the position `run_gates` cannot reach.
"""
from Tools.platform.repository.repository import repository_source_root, tools_source_root

import argparse
import ast
import os
import sys

TOOLS_DIR = tools_source_root(__file__)
REPO_ROOT = repository_source_root(__file__)

import Tools.platform.agent_interface.agent_interface_policy as agent_interface_policy  # noqa: E402
import Tools.platform.agent_interface.entrypoint_loader as entrypoint_loader  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts  # noqa: E402
import Tools.execution.task_runtime.runtime_paths as runtime_paths  # noqa: E402
import Tools.platform.agent_interface.tool_availability as tool_availability  # noqa: E402

TOOL = "compile_cli_contract"
TOOL_VERSION = "1.8.0"

SCHEMA_VERSION = 9
INTERFACE_POLICY_SCHEMA_VERSION = agent_interface_policy.SCHEMA_VERSION
SOURCE_DISTRIBUTION_OUTPUT = "Tools/compiled/cli-contract.yaml"
CARRIED_RUNTIME_OUTPUT = runtime_paths.CLI_CONTRACT_ARTIFACT_PATH
DEFAULT_INTERFACE_POLICY = agent_interface_policy.POLICY_PATH
DEFAULT_RUNTIME_PATH_REGISTRY = (
    "Tools/execution/task_runtime/runtime_paths.py")
TOOLS_SUBDIR = "Tools"

# argparse action classes have no public name for the `action=` spelling that
# produced them, so the mapping is stated once here rather than at each use.
ACTION_NAMES = {
    "_StoreAction": "store",
    "_StoreTrueAction": "store_true",
    "_StoreFalseAction": "store_false",
    "_StoreConstAction": "store_const",
    "_AppendAction": "append",
    "_AppendConstAction": "append_const",
    "_CountAction": "count",
    "_HelpAction": "help",
    "_VersionAction": "version",
    "_SubParsersAction": "parsers",
    "_ExtendAction": "extend",
    "BooleanOptionalAction": "boolean_optional",
}

RECEIPT_FACTORY_PREFIX = "make_"
RECEIPT_FACTORY_SUFFIX = "receipt"
DYNAMIC_KEY = "<dynamic>"


class ContractError(Exception):
    """The evidence for one tool is unreliable; the run must exit 1."""


def fail(message):
    print("%s: %s" % (TOOL, message))
    return 1


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def is_cli_module(source_text):
    """True when the module builds an ArgumentParser and defines `main`.

    Decided statically, so a module that is a shared library rather than a
    command is never imported by this compiler at all.
    """
    try:
        return module_boundary_facts.is_cli_module(source_text)
    except SyntaxError as exc:
        raise ContractError("source does not parse: %s" % exc) from exc


def discover_tools(root):
    """Return public adapter triples after resolving their sole owners.

    Discovery is intentionally marker-first.  Looking for ``ArgumentParser``
    in each top-level file would rediscover the pre-layering hybrid command
    model and let a new command become its own unreviewed implementation
    owner.  ``entrypoint_loader`` owns the adapter-to-owner edge and rejects
    both a missing edge and two adapters naming the same owner.
    """
    directory = os.path.join(root, TOOLS_SUBDIR)
    if not os.path.isdir(directory):
        raise ContractError("no %s directory under %s" % (TOOLS_SUBDIR, root))
    try:
        descriptors = entrypoint_loader.discover_entrypoints(directory)
    except entrypoint_loader.EntrypointResolutionError as exc:
        raise ContractError(str(exc)) from exc
    return [
        (
            descriptor.tool,
            os.path.join(root, *descriptor.invocation_path.split("/")),
            descriptor.invocation_source,
        )
        for descriptor in descriptors
    ]


# ---------------------------------------------------------------------------
# argparse introspection
# ---------------------------------------------------------------------------


def normalize_text(value):
    """Collapse a declared help/description string to one canonical line."""
    if value is None:
        return None
    return " ".join(str(value).split()) or None


def relativize(root, value):
    """Rewrite an absolute in-repository default to its relative spelling."""
    if not isinstance(value, str) or not value:
        return value
    root = os.path.abspath(root)
    if value == root:
        return "."
    prefix = root + os.sep
    if value.startswith(prefix):
        return value[len(prefix):].replace(os.sep, "/")
    return value


def normalize_default(root, value):
    """Return (yaml value, python type name) for one evaluated default."""
    if value is argparse.SUPPRESS:
        return "==SUPPRESS==", "argparse.SUPPRESS"
    if value is None:
        return None, "NoneType"
    if isinstance(value, bool):
        return value, "bool"
    if isinstance(value, int):
        return value, "int"
    if isinstance(value, float):
        return value, "float"
    if isinstance(value, str):
        return relativize(root, value), "str"
    if isinstance(value, (list, tuple)):
        return ([normalize_default(root, item)[0] for item in value],
                type(value).__name__)
    if isinstance(value, (set, frozenset)):
        return (sorted(normalize_default(root, item)[0] for item in value),
                type(value).__name__)
    return repr(value), type(value).__name__


def normalize_choice(root, value):
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return relativize(root, value) if isinstance(value, str) else value
    if isinstance(value, bool) or value is None:
        return value
    return repr(value)


def normalize_choices(root, choices):
    """Return one tool's admissible values in a canonical, stable order.

    Declaration order is deliberately not preserved. Several tools build
    `choices` with `tuple(<some set>)`, and a set's iteration order varies
    between processes, so declaration order is not an observable property of
    those tools at all -- recording it would make this artifact differ from
    itself on the next run. What every tool does declare, unambiguously, is
    the admissible *set*, and that is what is written here.
    """
    if choices is None:
        return None
    normalized = [normalize_choice(root, item) for item in choices]
    return sorted(normalized,
                  key=lambda item: (type(item).__name__, str(item)))


def action_name(action):
    return ACTION_NAMES.get(type(action).__name__, type(action).__name__)


def type_name(action):
    declared = getattr(action, "type", None)
    if declared is None:
        return None
    return getattr(declared, "__name__", None) or repr(declared)


def is_auto_help(action):
    """The parser's own `-h/--help`, whose text argparse translates."""
    return (type(action).__name__ == "_HelpAction" and
            action.default is argparse.SUPPRESS)


def describe_arguments(root, parser):
    """One record per declared argument, in the tool's declaration order.

    A positional is distinguished from a flag by `option_strings` being
    empty; nothing else in the record encodes that difference.
    """
    records = []
    for action in parser._actions:
        if is_auto_help(action):
            continue
        default, default_type = normalize_default(root, action.default)
        choices = getattr(action, "choices", None)
        record = {
            "dest": str(action.dest),
            "option_strings": [str(item) for item in action.option_strings],
            "required": bool(action.required),
            "default": default,
            "default_type": default_type,
            "choices": normalize_choices(root, choices),
            "nargs": (None if action.nargs is None else
                      (action.nargs if isinstance(action.nargs, int)
                       else str(action.nargs))),
            "action": action_name(action),
            "type": type_name(action),
            "help": normalize_text(action.help),
        }
        records.append(record)
    return records


def describe_exclusive_groups(parser):
    """Each `add_mutually_exclusive_group` as (required, member dests)."""
    groups = []
    for group in parser._mutually_exclusive_groups:
        dests = [str(action.dest) for action in group._group_actions]
        if not dests:
            continue
        groups.append({"required": bool(group.required), "dests": dests})
    return groups


# ---------------------------------------------------------------------------
# Agent-interface capability policy
# ---------------------------------------------------------------------------


def load_interface_policy(root, records, availability):
    """Load and close the agent call-surface policy over every CLI tool.

    Argparse remains the invocation source.  This separate document owns the
    question argparse cannot answer: whether the operation may enter an agent
    transport, which argument establishes the bound workspace, and which
    caller-supplied arguments carry filesystem effects.  Exact tool and
    argument closure makes an unclassified new CLI or path capability fail the
    compiler instead of inheriting MCP exposure silently.
    """
    try:
        document, raw = agent_interface_policy.load_policy(root)
    except agent_interface_policy.AgentInterfacePolicyError as exc:
        raise ContractError(str(exc)) from exc

    consumption_defaults = document.get("consumption_defaults")
    expected_consumption_defaults = {
        "read": "snapshot",
        "write": "replace",
        "read-write": "transaction",
    }
    if consumption_defaults != expected_consumption_defaults:
        raise ContractError(
            "%s consumption_defaults must be exactly %r" %
            (DEFAULT_INTERFACE_POLICY, expected_consumption_defaults))

    def path_constraint(row, expected_keys, owner):
        binding_keys = {"value", "runtime_path_id"}
        present_bindings = set(row) & binding_keys \
            if isinstance(row, dict) else set()
        if (not isinstance(row, dict) or len(present_bindings) != 1 or
                set(row) != expected_keys | present_bindings):
            raise ContractError(
                "%s %s rows must carry exactly %s and exactly one of "
                "value/runtime_path_id" %
                (DEFAULT_INTERFACE_POLICY, owner,
                 ", ".join(sorted(expected_keys))))
        argument = row.get("argument")
        constraint = row.get("constraint")
        uses_runtime_path_id = "runtime_path_id" in row
        runtime_path_id = row.get("runtime_path_id") \
            if uses_runtime_path_id else None
        value = row.get("value") if "value" in row else None
        suffixes = row.get("suffixes")
        if not isinstance(argument, str) or not argument:
            raise ContractError("%s: %s carries no argument" %
                                (DEFAULT_INTERFACE_POLICY, owner))
        if constraint not in ("contained", "exact", "namespace"):
            raise ContractError(
                "%s: %s.%s has unknown path constraint %r" %
                (DEFAULT_INTERFACE_POLICY, owner, argument, constraint))
        if constraint == "contained":
            if uses_runtime_path_id:
                raise ContractError(
                    "%s: %s.%s registered path reference cannot be "
                    "contained" %
                    (DEFAULT_INTERFACE_POLICY, owner, argument))
            if value is not None or suffixes not in (None, []):
                raise ContractError(
                    "%s: contained path constraints carry no value or "
                    "suffixes" % DEFAULT_INTERFACE_POLICY)
            value = None
            suffixes = []
        else:
            if uses_runtime_path_id:
                if not isinstance(runtime_path_id, str) or \
                        not runtime_path_id:
                    raise ContractError(
                        "%s: %s.%s runtime_path_id must be a non-empty "
                        "string" %
                        (DEFAULT_INTERFACE_POLICY, owner, argument))
                try:
                    reference = runtime_paths.path_reference_for(
                        runtime_path_id)
                except KeyError as exc:
                    raise ContractError(
                        "%s: %s.%s names unknown runtime_path_id %s" %
                        (DEFAULT_INTERFACE_POLICY, owner, argument,
                         runtime_path_id)) from exc
                if reference.constraint != constraint:
                    raise ContractError(
                        "%s: %s.%s runtime path reference constraint "
                        "mismatch: %s is %s, not %s" %
                        (DEFAULT_INTERFACE_POLICY, owner, argument,
                         runtime_path_id, reference.constraint, constraint))
                value = reference.path
            else:
                if not isinstance(value, str) or not value or \
                        os.path.isabs(value) or "\\" in value or \
                        os.path.normpath(value).replace(os.sep, "/") != value or \
                        value.startswith("../") or value == "..":
                    raise ContractError(
                        "%s: %s.%s must name a canonical repository-relative "
                        "path" % (DEFAULT_INTERFACE_POLICY, owner, argument))
                if value == runtime_paths.RUNTIME_ROOT or value.startswith(
                        runtime_paths.RUNTIME_ROOT + "/"):
                    raise ContractError(
                        "%s: %s.%s runtime path must use runtime_path_id, "
                        "not literal value" %
                        (DEFAULT_INTERFACE_POLICY, owner, argument))
            if not isinstance(suffixes, list) or any(
                    not isinstance(suffix, str) or not suffix or
                    not suffix.startswith(".") or "/" in suffix or
                    "\\" in suffix for suffix in suffixes):
                raise ContractError(
                    "%s: %s.%s suffixes must be filename suffix strings" %
                    (DEFAULT_INTERFACE_POLICY, owner, argument))
            if constraint == "exact" and suffixes:
                raise ContractError(
                    "%s: exact path constraints do not need suffixes" %
                    DEFAULT_INTERFACE_POLICY)
        result = {
            "constraint": constraint,
            "value": value,
            "runtime_path_id": runtime_path_id,
            "suffixes": list(suffixes),
        }
        if "consumption" in expected_keys:
            consumption = row.get("consumption")
            if consumption not in ("snapshot", "append", "replace",
                                    "transaction"):
                raise ContractError(
                    "%s: %s.%s has unknown consumption mode %r" %
                    (DEFAULT_INTERFACE_POLICY, owner, argument, consumption))
            result["consumption"] = consumption
        return result

    defaults = {}
    default_rows = document.get("path_defaults")
    if not isinstance(default_rows, list):
        raise ContractError("%s carries no path_defaults list" %
                            DEFAULT_INTERFACE_POLICY)
    default_keys = {
        "argument", "constraint", "suffixes", "consumption",
    }
    for row in default_rows:
        capability = path_constraint(row, default_keys, "path_defaults")
        argument = row["argument"]
        if argument in defaults:
            raise ContractError("%s duplicates path default %s" %
                                (DEFAULT_INTERFACE_POLICY, argument))
        defaults[argument] = capability

    overrides = {}
    override_rows = document.get("path_overrides")
    if not isinstance(override_rows, list):
        raise ContractError("%s carries no path_overrides list" %
                            DEFAULT_INTERFACE_POLICY)
    override_keys = {"tool", "argument", "constraint", "suffixes"}
    for row in override_rows:
        capability = path_constraint(row, override_keys, "path_overrides")
        tool = row.get("tool")
        if not isinstance(tool, str) or not tool:
            raise ContractError("%s path override carries no tool" %
                                DEFAULT_INTERFACE_POLICY)
        key = (tool, row["argument"])
        if key in overrides:
            raise ContractError("%s duplicates path override %s.%s" %
                                (DEFAULT_INTERFACE_POLICY, key[0], key[1]))
        overrides[key] = capability

    activations = {}
    activation_rows = document.get("path_activation_overrides")
    if not isinstance(activation_rows, list):
        raise ContractError(
            "%s carries no path_activation_overrides list" %
            DEFAULT_INTERFACE_POLICY)
    activation_keys = {
        "tool", "argument", "active_when_any", "inactive_when_any",
    }
    for row in activation_rows:
        if not isinstance(row, dict) or set(row) != activation_keys:
            raise ContractError(
                "%s path_activation_overrides rows must carry exactly %s" %
                (DEFAULT_INTERFACE_POLICY,
                 ", ".join(sorted(activation_keys))))
        tool = row.get("tool")
        argument = row.get("argument")
        active_when_any = row.get("active_when_any")
        inactive_when_any = row.get("inactive_when_any")
        if not isinstance(tool, str) or not tool or \
                not isinstance(argument, str) or not argument:
            raise ContractError(
                "%s path activation override must name one tool argument" %
                DEFAULT_INTERFACE_POLICY)
        for label, flags in (
                ("active_when_any", active_when_any),
                ("inactive_when_any", inactive_when_any)):
            if (not isinstance(flags, list) or
                    any(not isinstance(flag, str) or not flag
                        for flag in flags) or
                    len(flags) != len(set(flags))):
                raise ContractError(
                    "%s: %s.%s %s must be a unique string list" %
                    (DEFAULT_INTERFACE_POLICY, tool, argument, label))
        if not active_when_any and not inactive_when_any:
            raise ContractError(
                "%s: %s.%s activation override changes no condition" %
                (DEFAULT_INTERFACE_POLICY, tool, argument))
        if set(active_when_any) & set(inactive_when_any):
            raise ContractError(
                "%s: %s.%s activation flag cannot both activate and "
                "deactivate the path" %
                (DEFAULT_INTERFACE_POLICY, tool, argument))
        key = (tool, argument)
        if key in activations:
            raise ContractError(
                "%s duplicates path activation override %s.%s" %
                (DEFAULT_INTERFACE_POLICY, tool, argument))
        activations[key] = {
            "active_when_any": list(active_when_any),
            "inactive_when_any": list(inactive_when_any),
        }

    rows = document.get("tools")
    if not isinstance(rows, list):
        raise ContractError("%s carries no tools list" %
                            DEFAULT_INTERFACE_POLICY)

    expected_keys = {
        "tool", "exposure", "workspace_argument", "workspace_access",
        "value_arguments", "read_paths", "write_paths",
        "read_write_paths", "external_write",
    }
    by_name = {}
    excluded_tools = []
    record_by_name = {record["tool"]: record for record in records}
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise ContractError(
                "%s tool rows must carry exactly %s" %
                (DEFAULT_INTERFACE_POLICY, ", ".join(sorted(expected_keys))))
        name = row.get("tool")
        if not isinstance(name, str) or not name or name in by_name:
            raise ContractError("%s carries an invalid or duplicate tool %r"
                                % (DEFAULT_INTERFACE_POLICY, name))
        if name not in record_by_name:
            # Absence means two opposite things.  The boundary is what tells
            # them apart: a module it names is excluded from this target by
            # public rule, and anything else is a tool that was supposed to
            # arrive and did not.
            if availability.permits_missing(name):
                excluded_tools.append(name)
                continue
            raise ContractError(
                "%s names CLI tool %s, which is neither present nor excluded "
                "by %s for projection target %s"
                % (DEFAULT_INTERFACE_POLICY, name,
                   availability.boundary_path, availability.target))
        if row.get("exposure") not in ("mcp", "cli-only"):
            raise ContractError("%s: exposure must be mcp or cli-only" % name)
        if row.get("workspace_access") not in (None, "read", "write"):
            raise ContractError(
                "%s: workspace_access must be read, write, or null" % name)
        workspace_argument = row.get("workspace_argument")
        if (workspace_argument is None) != \
                (row.get("workspace_access") is None):
            raise ContractError(
                "%s: workspace_argument and workspace_access must both be "
                "null or both be declared" % name)
        arguments = {item["dest"]: item for item in
                     record_by_name[name]["arguments"]}
        if workspace_argument is not None and workspace_argument not in arguments:
            raise ContractError("%s: unknown workspace_argument %s" %
                                (name, workspace_argument))
        if row["exposure"] == "mcp" and workspace_argument is None:
            raise ContractError(
                "%s: every MCP tool must bind a workspace argument" % name)
        if not isinstance(row.get("external_write"), str) or \
                not row["external_write"]:
            raise ContractError("%s: external_write must be explicit" % name)
        if row["exposure"] == "mcp" and row["external_write"] != "none":
            raise ContractError(
                "%s: an MCP tool may not inherit external-write capability"
                % name)

        seen = set()
        path_access = {}
        for key, access in (("read_paths", "read"),
                            ("write_paths", "write"),
                            ("read_write_paths", "read-write")):
            values = row.get(key)
            if not isinstance(values, list) or \
                    any(not isinstance(value, str) or not value
                        for value in values):
                raise ContractError("%s: %s must be a list of argument names"
                                    % (name, key))
            for value in values:
                if value == workspace_argument:
                    raise ContractError(
                        "%s: workspace_argument %s must not be repeated in %s"
                        % (name, value, key))
                if value not in arguments:
                    raise ContractError("%s: %s names unknown argument %s" %
                                        (name, key, value))
                if value in seen:
                    raise ContractError(
                        "%s: path argument %s is classified more than once"
                        % (name, value))
                seen.add(value)
                path_access[value] = access
        value_arguments = row.get("value_arguments")
        if not isinstance(value_arguments, list) or any(
                not isinstance(value, str) or not value
                for value in value_arguments):
            raise ContractError(
                "%s: value_arguments must be a list of argument names" %
                name)
        if len(value_arguments) != len(set(value_arguments)):
            raise ContractError("%s: value_arguments contains duplicates" %
                                name)
        for value in value_arguments:
            if value == workspace_argument or value in seen:
                raise ContractError(
                    "%s: argument %s is classified more than once" %
                    (name, value))
            if value not in arguments:
                raise ContractError(
                    "%s: value_arguments names unknown argument %s" %
                    (name, value))
        classified = seen | set(value_arguments)
        if workspace_argument is not None:
            classified.add(workspace_argument)
        actual_arguments = set(arguments)
        if classified != actual_arguments:
            raise ContractError(
                "%s: argument closure mismatch: unclassified=%s "
                "unexpected=%s" %
                (name,
                 ",".join(sorted(actual_arguments - classified)) or "none",
                 ",".join(sorted(classified - actual_arguments)) or "none"))
        if row["exposure"] == "mcp" and path_access and any(
                access in ("write", "read-write")
                for access in path_access.values()) and \
                row.get("workspace_access") != "write":
            raise ContractError(
                "%s: a tool with caller-supplied write paths must declare "
                "workspace_access write" % name)
        path_arguments = []
        for argument in sorted(path_access):
            argument_default = defaults.get(argument)
            capability = overrides.get(
                (name, argument), argument_default or {
                    "constraint": "contained", "value": None,
                    "runtime_path_id": None,
                    "suffixes": [],
                })
            default_consumption = (
                argument_default.get("consumption")
                if isinstance(argument_default, dict)
                else consumption_defaults[path_access[argument]])
            consumption = capability.get(
                "consumption", default_consumption)
            compatible = {
                "read": {"snapshot"},
                "write": {"append", "replace"},
                "read-write": {"transaction"},
            }
            if consumption not in compatible[path_access[argument]]:
                raise ContractError(
                    "%s.%s: consumption mode %s is incompatible with %s "
                    "access" % (name, argument, consumption,
                                path_access[argument]))
            activation = activations.get((name, argument), {
                "active_when_any": [], "inactive_when_any": [],
            })
            for condition_name in (
                    activation["active_when_any"] +
                    activation["inactive_when_any"]):
                condition_record = arguments.get(condition_name)
                if (condition_name not in value_arguments or
                        not isinstance(condition_record, dict) or
                        condition_record.get("action") != "store_true"):
                    raise ContractError(
                        "%s.%s: activation condition %s must name one "
                        "store_true "
                        "value argument of the same tool" %
                        (name, argument, condition_name))
            path_arguments.append({
                "argument": argument,
                "access": path_access[argument],
                "consumption": consumption,
                "constraint": capability["constraint"],
                "value": capability["value"],
                "runtime_path_id": capability["runtime_path_id"],
                "suffixes": list(capability["suffixes"]),
                "active_when_any": list(activation["active_when_any"]),
                "inactive_when_any": list(
                    activation["inactive_when_any"]),
            })
        by_name[name] = {
            "exposure": row["exposure"],
            "workspace_argument": workspace_argument,
            "workspace_access": row["workspace_access"],
            "value_arguments": sorted(value_arguments),
            "path_arguments": path_arguments,
            "external_write": row["external_write"],
        }

    declared = set(by_name)
    actual = set(record_by_name)
    if declared != actual:
        raise ContractError(
            "%s tool closure mismatch: missing=%s unexpected=%s" %
            (DEFAULT_INTERFACE_POLICY,
             ",".join(sorted(actual - declared)) or "none",
             ",".join(sorted(declared - actual)) or "none"))
    path_pairs = {
        (name, item["argument"])
        for name, interface in by_name.items()
        for item in interface["path_arguments"]
    }
    unused_defaults = sorted(
        argument for argument in defaults
        if not any(pair[1] == argument for pair in path_pairs))
    invalid_overrides = sorted(set(overrides) - path_pairs)
    invalid_activation_overrides = sorted(set(activations) - path_pairs)
    if unused_defaults:
        raise ContractError("%s has unused path defaults: %s" %
                            (DEFAULT_INTERFACE_POLICY,
                             ", ".join(unused_defaults)))
    if invalid_overrides:
        raise ContractError(
            "%s has overrides for unclassified path arguments: %s" %
            (DEFAULT_INTERFACE_POLICY, ", ".join(
                "%s.%s" % item for item in invalid_overrides)))
    if invalid_activation_overrides:
        raise ContractError(
            "%s has activation overrides for unclassified path arguments: %s"
            % (DEFAULT_INTERFACE_POLICY, ", ".join(
                "%s.%s" % item for item in invalid_activation_overrides)))
    return by_name, kblib.sha256_bytes(raw), sorted(excluded_tools)


# ---------------------------------------------------------------------------
# Receipt extension derivation (static, per tool)
# ---------------------------------------------------------------------------


def _is_receipt_factory(node):
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(
        func, "id", "")
    if not isinstance(name, str):
        return False
    bare = name[1:] if name.startswith("_") else name
    return (bare.startswith(RECEIPT_FACTORY_PREFIX) and
            bare.endswith(RECEIPT_FACTORY_SUFFIX))


KBLIB_MODULE = "Tools.platform.common.kblib"
KBLIB_RECEIPT_FACTORY = KBLIB_MODULE + ".make_receipt"
COMMON_RECEIPT_ENVELOPE_OWNER = KBLIB_MODULE + ":make_receipt"
KBLIB_RECEIPT_SOURCE = KBLIB_MODULE.replace(".", "/") + ".py"
QUEUE_RECEIPT_MODULE = "Tools.execution.task_runtime.queue_runtime.receipts"
QUEUE_RECEIPT_FACTORY = QUEUE_RECEIPT_MODULE + ".make_queue_receipt"


def _common_receipt_envelope_fields():
    """Project the unconditional field order from the current producer.

    The probe supplies no runtime identity, so the resulting keys are exactly
    the common envelope every typed Receipt receives. Values are deliberately
    discarded: only the factory-owned field shape enters the CLI contract.
    """
    receipt = kblib.make_receipt(
        "compile_cli_contract", TOOL_VERSION,
        "common-envelope-projection", "common-envelope", "pass",
        "shape projection only", 0,
        receipt_type_id="cli-contract-envelope-probe-v1", identity={},
    )
    return tuple(receipt)


def _attribute_parts(node):
    """Return a plain ``name.attr`` chain, or None for a computed receiver."""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return list(reversed(parts))


def _scope_nodes(scope):
    """Walk one lexical scope without charging nested definitions twice."""
    pending = list(reversed(getattr(scope, "body", ())))
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Lambda)):
            continue
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _assigned_names(node):
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return {
        target.id for target in targets if isinstance(target, ast.Name)
    }


def _factory_calls(value):
    return [
        node for node in ast.walk(value)
        if isinstance(node, ast.Call) and _is_receipt_factory(node)
    ]


class _ReceiptExtensionAnalyzer:
    """Resolve receipt construction through the implementation source graph.

    The public wrapper is never an analysis source.  Calls named
    ``make_*receipt`` are resolved through the implementation's imports; when
    the factory is another shipped module, that exact function is inspected
    and its bytes join the projection manifest.  Unknown mapping writes stay
    visible as ``partial`` instead of turning parameter names into invented
    receipt fields.
    """

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.modules = {}
        self.factory_cache = {}
        self.active_factories = set()
        self.common_envelope_fields = frozenset(
            _common_receipt_envelope_fields())

    @staticmethod
    def _relative_path(module_name):
        if not isinstance(module_name, str) or \
                not module_name.startswith("Tools."):
            return None
        return module_name.replace(".", "/") + ".py"

    def _absolute_path(self, relative_path):
        return os.path.join(self.root, *relative_path.split("/"))

    def _module_exists(self, module_name):
        relative = self._relative_path(module_name)
        return relative is not None and os.path.isfile(
            self._absolute_path(relative))

    @staticmethod
    def _import_from_owner(node, module_name):
        if not node.level:
            return node.module or ""
        package = module_name.rpartition(".")[0].split(".")
        ascend = node.level - 1
        if ascend > len(package):
            return ""
        if ascend:
            package = package[:-ascend]
        if node.module:
            package.extend(node.module.split("."))
        return ".".join(part for part in package if part)

    def _load_module(self, module_name, source_text=None):
        cached = self.modules.get(module_name)
        if cached is not None:
            return cached
        relative = self._relative_path(module_name)
        if relative is None:
            raise ContractError(
                "receipt source is not a qualified Tools module: %s" %
                module_name)
        if source_text is None:
            try:
                with open(self._absolute_path(relative), "r",
                          encoding="utf-8") as handle:
                    source_text = handle.read()
            except (OSError, UnicodeError) as exc:
                raise ContractError(
                    "cannot read receipt source %s: %s" %
                    (relative, exc)) from exc
        try:
            tree = ast.parse(source_text, filename=relative)
        except SyntaxError as exc:
            raise ContractError(
                "receipt source %s does not parse: %s" %
                (relative, exc)) from exc
        bindings = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        bindings[alias.asname] = alias.name
                    else:
                        root_name = alias.name.split(".")[0]
                        bindings[root_name] = root_name
            elif isinstance(node, ast.ImportFrom):
                owner = self._import_from_owner(node, module_name)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    qualified = "%s.%s" % (owner, alias.name) \
                        if owner else alias.name
                    bindings[alias.asname or alias.name] = qualified
        functions = {
            node.name: node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        info = {
            "module": module_name,
            "path": relative,
            "source": source_text,
            "tree": tree,
            "bindings": bindings,
            "functions": functions,
        }
        self.modules[module_name] = info
        return info

    @staticmethod
    def _merge(left, right):
        left["fields"].update(right["fields"])
        left["sources"].update(right["sources"])
        left["partial"] = left["partial"] or right["partial"]

    @staticmethod
    def _empty():
        return {"fields": set(), "sources": set(), "partial": False}

    def _qualify_call(self, info, call):
        parts = _attribute_parts(call.func)
        if not parts:
            return None
        first = parts[0]
        if first in info["bindings"]:
            return ".".join([info["bindings"][first]] + parts[1:])
        if len(parts) == 1 and first in info["functions"]:
            return "%s.%s" % (info["module"], first)
        if first == "Tools":
            return ".".join(parts)
        return None

    def _intrinsic(self, qualified, call):
        result = self._empty()
        if qualified not in (
                KBLIB_RECEIPT_FACTORY, QUEUE_RECEIPT_FACTORY):
            return None
        source_module = (KBLIB_MODULE if qualified == KBLIB_RECEIPT_FACTORY
                         else QUEUE_RECEIPT_MODULE)
        relative = self._relative_path(source_module)
        if relative is not None and os.path.isfile(
                self._absolute_path(relative)):
            result["sources"].add(relative)
        if qualified == KBLIB_RECEIPT_FACTORY:
            identity_arguments = {"root", "identity"}
            if any(keyword.arg in identity_arguments
                   for keyword in call.keywords):
                result["fields"].update(kblib.RECEIPT_IDENTITY_FIELDS)
            if any(keyword.arg is None for keyword in call.keywords):
                result["partial"] = True
            return result

        # ``make_queue_receipt`` is the Queue owner's factory whose **fields
        # parameter is itself the output extension mapping.  Its ordinary
        # formal parameters are inputs, just like every other receipt factory.
        ordinary = {"action", "target", "result", "details", "seq"}
        for keyword in call.keywords:
            if keyword.arg is None:
                result["partial"] = True
            elif keyword.arg not in ordinary:
                result["fields"].add(keyword.arg)
        return result

    def _factory(self, info, call):
        qualified = self._qualify_call(info, call)
        if qualified is None:
            return {"fields": set(), "sources": set(), "partial": True}
        intrinsic = self._intrinsic(qualified, call)
        if intrinsic is not None:
            return intrinsic
        cached = self.factory_cache.get(qualified)
        if cached is not None:
            return {
                "fields": set(cached["fields"]),
                "sources": set(cached["sources"]),
                "partial": cached["partial"],
            }
        module_name, _separator, function_name = qualified.rpartition(".")
        if not module_name or not self._module_exists(module_name):
            return {"fields": set(), "sources": set(), "partial": True}
        helper = self._load_module(module_name)
        function = helper["functions"].get(function_name)
        if function is None or qualified in self.active_factories:
            return {"fields": set(), "sources": set(), "partial": True}
        self.active_factories.add(qualified)
        try:
            result = self._analyze_scope(helper, function)
            result["sources"].add(helper["path"])
        finally:
            self.active_factories.remove(qualified)
        self.factory_cache[qualified] = {
            "fields": set(result["fields"]),
            "sources": set(result["sources"]),
            "partial": result["partial"],
        }
        return result

    @staticmethod
    def _literal_mapping_keys(value):
        if isinstance(value, ast.Dict):
            keys = set()
            complete = True
            for key in value.keys:
                if isinstance(key, ast.Constant) and isinstance(
                        key.value, str):
                    keys.add(key.value)
                else:
                    complete = False
            return keys, complete
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                and value.func.id == "dict" and not value.args:
            return ({keyword.arg for keyword in value.keywords
                     if keyword.arg is not None},
                    all(keyword.arg is not None
                        for keyword in value.keywords))
        return set(), False

    def _analyze_scope(self, info, scope):
        result = self._empty()
        nodes = list(_scope_nodes(scope))
        receipt_names = set()
        assignments = {}

        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                for name in _assigned_names(node):
                    assignments[name] = value
                calls = _factory_calls(value)
                if calls:
                    receipt_names.update(_assigned_names(node))
                    if not isinstance(value, ast.Call):
                        # A fallback expression such as ``existing or
                        # make_receipt`` may return an object whose earlier
                        # shape is not visible in this source.
                        result["partial"] = True

        # Receipt aliases are common in failure/abort branches.  Close them
        # before reading mutations so the alias cannot hide a write.
        changed = True
        while changed:
            changed = False
            for name, value in assignments.items():
                if isinstance(value, ast.Name) and \
                        value.id in receipt_names and \
                        name not in receipt_names:
                    receipt_names.add(name)
                    changed = True

        for node in nodes:
            if isinstance(node, ast.Call) and _is_receipt_factory(node):
                self._merge(result, self._factory(info, node))

            if isinstance(node, ast.Call) and \
                    isinstance(node.func, ast.Attribute) and \
                    node.func.attr == "update" and \
                    isinstance(node.func.value, ast.Name) and \
                    node.func.value.id in receipt_names:
                for argument in node.args:
                    keys, complete = self._literal_mapping_keys(argument)
                    result["fields"].update(keys)
                    if not complete:
                        result["partial"] = True
                for keyword in node.keywords:
                    if keyword.arg is None:
                        result["partial"] = True
                    else:
                        result["fields"].add(keyword.arg)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) \
                    else (node.target,)
                for target in targets:
                    if not isinstance(target, ast.Subscript) or \
                            not isinstance(target.value, ast.Name) or \
                            target.value.id not in receipt_names:
                        continue
                    index = target.slice
                    if isinstance(index, ast.Constant) and isinstance(
                            index.value, str):
                        result["fields"].add(index.value)
                    else:
                        result["partial"] = True

        result["fields"].difference_update(self.common_envelope_fields)
        return result

    def analyze(self, module_name, source_text):
        info = self._load_module(module_name, source_text)
        result = self._empty()
        # Analyze the module body and every top-level function.  This matches
        # the contract's existing producer-surface meaning: all receipt shapes
        # the implementation can emit, not only one selected argv branch.
        self._merge(result, self._analyze_scope(info, info["tree"]))
        for function in info["functions"].values():
            self._merge(result, self._analyze_scope(info, function))
        result["sources"].add(info["path"])
        result["fields"].difference_update(self.common_envelope_fields)
        return (
            sorted(result["fields"]),
            "partial" if result["partial"] else "complete",
            sorted(result["sources"]),
        )


def receipt_extensions(source_text, *, root, module_name):
    """Return fields, completeness, and sources for one implementation."""
    return _ReceiptExtensionAnalyzer(root).analyze(module_name, source_text)


# ---------------------------------------------------------------------------
# Composition and rendering
# ---------------------------------------------------------------------------


def compile_contract(root, projection_target):
    """Return the contract mapping compiled for one declared target.

    The target is an argument rather than something read off the filesystem.
    A distribution mid-checkout would otherwise present itself as an adopter
    runtime and excuse the absence that most needs reporting.
    """
    root = os.path.abspath(root)
    availability = tool_availability.resolve(root, projection_target)
    tools = discover_tools(root)
    registry_path = os.path.join(
        root, *DEFAULT_RUNTIME_PATH_REGISTRY.split("/"))
    try:
        with open(registry_path, "rb") as handle:
            runtime_path_registry_raw = handle.read()
    except OSError as exc:
        raise ContractError("cannot read %s: %s" %
                            (DEFAULT_RUNTIME_PATH_REGISTRY, exc))
    runtime_path_registry_hash = kblib.sha256_bytes(
        runtime_path_registry_raw)
    common_receipt_source_path = os.path.join(
        root, *KBLIB_RECEIPT_SOURCE.split("/"))
    try:
        with open(common_receipt_source_path, "rb") as handle:
            common_receipt_source_raw = handle.read()
    except OSError as exc:
        raise ContractError("cannot read common Receipt owner %s: %s" %
                            (KBLIB_RECEIPT_SOURCE, exc)) from exc
    common_receipt_source_hash = kblib.sha256_bytes(
        common_receipt_source_raw)

    records = []
    for module_name, path, source_text in tools:
        try:
            descriptor = entrypoint_loader.describe_entrypoint(
                module_name, os.path.join(root, TOOLS_SUBDIR),
                require_marker=True)
            parser = entrypoint_loader.capture_argument_parser(
                module_name, os.path.join(root, TOOLS_SUBDIR),
                require_marker=True)
        except entrypoint_loader.EntrypointResolutionError as exc:
            raise ContractError(str(exc)) from exc
        try:
            extensions, completeness, extension_paths = receipt_extensions(
                descriptor.implementation_source,
                root=root,
                module_name=descriptor.implementation_module,
            )
            extension_sources = []
            for relative in extension_paths:
                with open(os.path.join(root, *relative.split("/")),
                          "rb") as handle:
                    raw_extension_source = handle.read()
                extension_sources.append({
                    "path": relative,
                    "sha256": kblib.sha256_bytes(raw_extension_source),
                })
        except (OSError, TypeError, ValueError) as exc:
            raise ContractError(
                "%s: implementation analysis failed: %s" %
                (module_name, exc)) from exc
        records.append({
            "tool": module_name,
            "module": descriptor.invocation_path,
            "source_hash": kblib.sha256_bytes(
                descriptor.invocation_source.encode("utf-8")),
            "implementation_module": descriptor.implementation_module,
            "implementation_path": descriptor.implementation_path,
            "implementation_source_hash": kblib.sha256_bytes(
                descriptor.implementation_source.encode("utf-8")),
            "description": normalize_text(parser.description),
            "arguments": describe_arguments(root, parser),
            "mutually_exclusive_groups": describe_exclusive_groups(parser),
            "receipt_extensions": extensions,
            "receipt_extensions_extraction": completeness,
            "receipt_extension_sources": extension_sources,
        })

    interface_policy, interface_policy_hash, excluded_tools = \
        load_interface_policy(root, records, availability)
    for record in records:
        record["agent_interface"] = interface_policy[record["tool"]]

    manifest = "%s %s\n" % (
        DEFAULT_INTERFACE_POLICY, interface_policy_hash)
    manifest += "%s %s\n" % (
        DEFAULT_RUNTIME_PATH_REGISTRY, runtime_path_registry_hash)
    source_records = [
        (KBLIB_RECEIPT_SOURCE, common_receipt_source_hash),
    ]
    for record in records:
        source_records.append((record["module"], record["source_hash"]))
        if record["implementation_path"] != record["module"]:
            source_records.append((
                record["implementation_path"],
                record["implementation_source_hash"]))
        source_records.extend(
            (source["path"], source["sha256"])
            for source in record["receipt_extension_sources"])
    source_records = sorted(set(source_records))
    manifest += "".join(
        "%s %s\n" % (path, fingerprint)
        for path, fingerprint in source_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": "cli-invocation-contract",
        "generator": "%s/%s.py" % (TOOLS_SUBDIR, TOOL),
        "generator_version": TOOL_VERSION,
        "derived_from": "entrypoint-owner-argparse-and-receipt-analysis",
        "source_files": ([DEFAULT_INTERFACE_POLICY,
                          DEFAULT_RUNTIME_PATH_REGISTRY] +
                         [path for path, _fingerprint in source_records]),
        "source_hash": kblib.sha256_bytes(manifest),
        "agent_interface_policy": {
            "path": DEFAULT_INTERFACE_POLICY,
            "sha256": interface_policy_hash,
        },
        "runtime_path_registry": {
            "path": DEFAULT_RUNTIME_PATH_REGISTRY,
            "sha256": runtime_path_registry_hash,
        },
        # Binding these four is what makes the artifact answer "whose
        # projection is this, and against which boundary".  Without them a
        # copy from another repository reads as a local build, and a boundary
        # edit leaves every derived artifact silently describing the old set.
        "projection_target": availability.target,
        "distribution_boundary": {
            "path": availability.boundary_path,
            "sha256": availability.boundary_sha256,
        },
        "included_tools": [record["tool"] for record in records],
        "excluded_tools": excluded_tools,
        "receipt_shape": {
            "common_envelope_owner": COMMON_RECEIPT_ENVELOPE_OWNER,
            "common_envelope_fields": list(
                _common_receipt_envelope_fields()),
            "extension_policy":
                "derived-per-tool-from-implementation-source-closure",
        },
        "tool_count": len(records),
        "tools": records,
    }


def apply_gated_writer_tools(contract):
    """Return tools whose every declared write is activated only by apply.

    The compiled agent-interface contract is the machine owner of CLI
    argument and path effects.  Consumers that need to distinguish a
    read-only diagnostic invocation from a guarded transaction must derive
    that distinction from this projection instead of maintaining a second
    tool-name allowlist.
    """
    tools = contract.get("tools") if isinstance(contract, dict) else None
    if not isinstance(tools, list):
        raise ContractError(
            "compiled CLI contract carries no closed tools list")
    result = set()
    for record in tools:
        if not isinstance(record, dict) or not isinstance(
                record.get("tool"), str):
            raise ContractError(
                "compiled CLI contract carries an invalid tool record")
        interface = record.get("agent_interface")
        if not isinstance(interface, dict):
            raise ContractError(
                "%s carries no compiled agent interface" % record["tool"])
        paths = interface.get("path_arguments")
        values = interface.get("value_arguments")
        if not isinstance(paths, list) or not isinstance(values, list):
            raise ContractError(
                "%s carries an incomplete compiled agent interface" %
                record["tool"])
        writes = [
            item for item in paths
            if isinstance(item, dict) and
            item.get("access") in ("write", "read-write")
        ]
        if not writes or "apply" not in values:
            continue
        if all(
                item.get("active_when_any") == ["apply"] and
                item.get("inactive_when_any") == []
                for item in writes):
            result.add(record["tool"])
    return frozenset(result)


def build_header(contract):
    target = contract["projection_target"]
    command = (
        "python3 Tools/compile_cli_contract.py . --projection-target %s" %
        target)
    return [
        "# Generated artifact -- do not edit directly.",
        "# Compiled by Tools/compile_cli_contract.py from each CLI's argparse",
        "#   declaration plus Tools/agent-interface-policy.yaml. Invocation",
        "#   shape comes from argparse; capability shape comes from the closed",
        "#   policy. A hand edit is reported by --check as a HOLD.",
        "# regenerate with: %s" % command,
        "# verify with:     %s --check" % command,
        "# `source_hash` covers the policy, runtime path registry, and %d"
        % contract["tool_count"],
        "#   CLI tool sources listed under source_files.",
        "# A positional argument is one whose `option_strings` is empty.",
        "# `choices` is the admissible SET in canonical order, not the",
        "#   declaration order: several tools build it from a Python set,",
        "#   whose iteration order is not stable between processes.",
        "# The auto-added -h/--help action is omitted: argparse translates",
        "#   its help text, which would make this artifact locale-dependent.",
        "",
    ]


def render(contract):
    return "".join(
        line + "\n" for line in build_header(contract)
    ) + kblib.canonical_yaml(contract)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _recorded_projection_target(output):
    """The target a stored artifact declares, or None when it declares none."""
    try:
        stored = kblib.parse_yaml_subset(kblib.read_text(output))
    except (OSError, kblib.YamlSubsetError, ValueError):
        return None
    if not isinstance(stored, dict):
        return None
    recorded = stored.get("projection_target")
    return recorded if recorded in tool_availability.PROJECTION_TARGETS \
        else None


def output_for_projection_target(projection_target):
    """The one repository-relative artifact owned by ``projection_target``."""
    if projection_target == tool_availability.SOURCE_DISTRIBUTION:
        return SOURCE_DISTRIBUTION_OUTPUT
    if projection_target == tool_availability.CARRIED_RUNTIME:
        return CARRIED_RUNTIME_OUTPUT
    raise ValueError("unknown projection target: %r" % projection_target)


def _registered_check_output(root, requested_path):
    """Resolve an existing check target without guessing its projection.

    `--check` historically permits omitting `--projection-target` because the
    stored artifact declares it. There are now two registered locations, so
    the path must first match exactly one of them; arbitrary files still never
    become compiler outputs.
    """
    errors = []
    for registered in (SOURCE_DISTRIBUTION_OUTPUT, CARRIED_RUNTIME_OUTPUT):
        try:
            return kblib.registered_repository_artifact_path(
                root, requested_path, registered)
        except ValueError as exc:
            errors.append(str(exc))
    raise ValueError("artifact path is not a registered CLI contract: %s" %
                     "; ".join(errors))


def _recorded_binding_drift(existing_text, contract):
    """Name a binding mismatch between a stored artifact and this repository.

    A byte comparison already refuses a stale artifact, but it reports every
    cause as the same sentence.  These three have a different remedy: the
    artifact belongs to another target, another boundary, or another
    repository's tool set, and regenerating it in place would erase the
    evidence of that rather than resolve it.
    """
    try:
        stored = kblib.parse_yaml_subset(existing_text)
    except (kblib.YamlSubsetError, ValueError):
        return None  # unreadable is the byte comparison's finding, not ours
    if not isinstance(stored, dict):
        return None
    recorded_target = stored.get("projection_target")
    if recorded_target != contract["projection_target"]:
        return ("the stored artifact was compiled for projection target %r, "
                "not %r; it is another projection, not a stale copy of this "
                "one" % (recorded_target, contract["projection_target"]))
    stored_boundary = stored.get("distribution_boundary")
    stored_hash = (stored_boundary or {}).get("sha256") \
        if isinstance(stored_boundary, dict) else None
    if stored_hash != contract["distribution_boundary"]["sha256"]:
        return ("the distribution boundary changed since the stored artifact "
                "was compiled (%s -> %s); every derived artifact is stale "
                "until it is rebuilt"
                % (stored_hash, contract["distribution_boundary"]["sha256"]))
    stored_included = stored.get("included_tools")
    if isinstance(stored_included, list) and \
            sorted(stored_included) != sorted(contract["included_tools"]):
        return ("the stored artifact records a different tool set than this "
                "repository holds; it was compiled somewhere else and cannot "
                "stand in for this repository's own projection")
    return None


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Compile the machine-readable CLI invocation contract "
                    "from every Tools/*.py argparse declaration.")
    parser.add_argument(
        "root",
        help="repository root whose Tools/ directory is compiled")
    parser.add_argument(
        "--check", action="store_true",
        help="recompute and compare against the existing output; exit 0 "
             "when byte-identical, 2 when it is stale or hand-edited")
    parser.add_argument(
        "--output", default=None,
        help="artifact path to write or verify; the selected projection "
             "target fixes this path to <root>/%s or <root>/%s"
             % (SOURCE_DISTRIBUTION_OUTPUT, CARRIED_RUNTIME_OUTPUT))
    parser.add_argument(
        "--projection-target",
        choices=list(tool_availability.PROJECTION_TARGETS),
        default=None,
        help="which projection this repository is compiling: the "
             "distribution that owns every tool, or a runtime carrying only "
             "what the distribution boundary lets it carry. Required to "
             "write; with --check it defaults to the target the stored "
             "artifact records. Declared either way, never inferred from "
             "which files happen to be present")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        return fail("root is not a directory: %s" % args.root)
    projection_target = args.projection_target
    if projection_target is None:
        # Reading the target the artifact recorded is not inference: the
        # artifact states it.  Absent both, there is nothing to verify
        # against, and guessing is what this contract exists to prevent.
        if not args.check:
            return fail("--projection-target is required to write the "
                        "contract; declare %s"
                        % " or ".join(tool_availability.PROJECTION_TARGETS))
        requested_output = args.output or SOURCE_DISTRIBUTION_OUTPUT
        try:
            output = _registered_check_output(root, requested_output)
        except ValueError as exc:
            return fail("unsafe artifact output: %s" % exc)
        projection_target = _recorded_projection_target(output)
        if projection_target is None:
            return fail(
                "%s records no projection target, so there is nothing to "
                "check it against; recompile it with an explicit "
                "--projection-target" % output)
        expected_output = output_for_projection_target(projection_target)
        try:
            kblib.registered_repository_artifact_path(
                root, output, expected_output)
        except ValueError:
            return fail(
                "%s declares projection target %r but that target owns %s; "
                "a stored artifact cannot relocate its own authority"
                % (output, projection_target, expected_output))
    else:
        expected_output = output_for_projection_target(projection_target)
        requested_output = args.output or expected_output
        try:
            output = kblib.registered_repository_artifact_path(
                root, requested_output, expected_output)
        except ValueError as exc:
            return fail("unsafe artifact output for projection target %s: %s"
                        % (projection_target, exc))

    try:
        contract = compile_contract(root, projection_target)
        text = render(contract)
    except tool_availability.AvailabilityError as exc:
        return fail("cannot resolve tool availability: %s" % exc)
    except ContractError as exc:
        return fail("evidence is unreliable: %s" % exc)
    except (kblib.YamlSubsetError, TypeError, ValueError) as exc:
        return fail("the compiled contract is not renderable: %s" % exc)

    if args.check:
        try:
            existing = kblib.read_text(output)
        except OSError as exc:
            print("%s --check: cannot read %s: %s" % (TOOL, output, exc))
            return 2
        drift = _recorded_binding_drift(existing, contract)
        if drift:
            # Naming the specific mismatch matters more than "stale" here: a
            # target or boundary mismatch is an artifact describing a
            # different repository, which regenerating silently would hide.
            print("%s --check: %s" % (TOOL, drift))
            return 2
        if existing != text:
            print("%s --check: %s is stale or hand-edited; regenerate it "
                  "with `python3 Tools/compile_cli_contract.py . "
                  "--projection-target %s`"
                  % (TOOL, output, projection_target))
            return 2
        print("%s --check: %s is current (%d tool(s))"
              % (TOOL, output, contract["tool_count"]))
        return 0

    kblib.atomic_write_text(output, text, validator=kblib.parse_yaml_subset)
    print("%s: wrote %s (%d tool(s), %d argument(s))"
          % (TOOL, output, contract["tool_count"],
             sum(len(record["arguments"]) for record in contract["tools"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
