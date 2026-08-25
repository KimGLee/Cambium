#!/usr/bin/env python3
"""compile_cli_contract.py -- persistent CLI invocation-contract compiler.

Deterministically derives one machine-readable calling contract for every
CLI tool shipped under `Tools/`, closes the host-facing capability surface
against `Tools/agent-interface-policy.yaml`, and writes the result to the
registered `Tools/compiled/cli-contract.yaml` artifact.

Why this exists: an agent should not have to read every argparse block or
trust prose that restates them. Argparse is the single source of invocation
shape. The separate policy is the single source of capability shape: MCP
exposure, workspace binding, typed path access, and declared external effects.
This compiler requires both sets to close exactly.

Extraction:
  - Each CLI module is loaded through `importlib` under its own name, with
    `argparse.ArgumentParser.parse_args` monkey-patched to raise as soon as
    the parser is complete. The tool's `main()` therefore builds its parser
    and stops; not one line of its own behaviour runs. The patch is removed
    again before this process does anything else.
  - Module import is side-effect free by construction here: the only
    top-level call in these modules is `sys.path.insert`. This compiler
    additionally disables bytecode writing, so it touches no file that any
    tool would write. It is read-only with respect to the repository.
  - Receipt extension fields are derived per tool by a static AST walk over
    that tool's own source: the keys it adds to a `make_*receipt(...)`
    result through `.update({...})` or subscript assignment. They are NOT
    copied from `schemas/receipt.template.jsonl`, which says in its own text
    that its examples are not the complete set. A tool that computes a key
    name at runtime is reported as `partial`, never as complete.
  - Agent-interface policy rows name every discovered CLI exactly once, and
    classify every argparse argument exactly once as workspace, path, or value.
    An MCP-exposed row may not declare an external-write capability; exact and
    namespace paths remain explicit data rather than server conventions.

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

import argparse
import ast
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)

import kblib  # noqa: E402

TOOL = "compile_cli_contract"
TOOL_VERSION = "1.0.0"

SCHEMA_VERSION = 2
DEFAULT_OUTPUT = "Tools/compiled/cli-contract.yaml"
DEFAULT_INTERFACE_POLICY = "Tools/agent-interface-policy.yaml"
TOOLS_SUBDIR = "Tools"

# The nine fields `kblib.make_receipt` writes unconditionally, plus the one
# conditional field named in the `schemas/receipt.template.jsonl` header.
# Both lists are read from that header's own vocabulary; the per-tool
# extension lists below are derived from the tools instead.
RECEIPT_BASE_FIELDS = (
    "receipt_id", "check", "target", "result", "details",
    "checked_at", "tool", "tool_version", "invalidated_by",
)
RECEIPT_CONDITIONAL_FIELDS = ("gate_id",)

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


class _CapturedParser(Exception):
    """Carries a fully built parser out of the tool's own `main()`."""

    def __init__(self, parser):
        super().__init__("parser captured")
        self.parser = parser


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
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        raise ContractError("source does not parse: %s" % exc)
    has_main = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
        node.name == "main"
        for node in tree.body
    )
    if not has_main:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(
            func, "id", "")
        if name == "ArgumentParser":
            return True
    return False


def discover_tools(root):
    """Return sorted (module name, absolute path, source text) CLI triples."""
    directory = os.path.join(root, TOOLS_SUBDIR)
    if not os.path.isdir(directory):
        raise ContractError("no %s directory under %s" % (TOOLS_SUBDIR, root))
    found = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                source_text = handle.read()
        except (OSError, UnicodeError) as exc:
            raise ContractError("cannot read %s: %s" % (name, exc))
        if is_cli_module(source_text):
            found.append((name[: -len(".py")], path, source_text))
    if not found:
        raise ContractError("no CLI tool found under %s" % directory)
    return found


# ---------------------------------------------------------------------------
# argparse introspection
# ---------------------------------------------------------------------------


def load_parser(module_name, path):
    """Build one tool's parser without running any of its behaviour.

    `parse_args` is patched to raise the instant the parser is complete, so
    `main()` returns control here having done nothing but declare its own
    interface. The caller restores the patch.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ContractError("%s: no import spec" % module_name)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            # A module that exits at import time has still defined `main`.
            pass
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            raise ContractError(
                "%s: import failed: %s: %s"
                % (module_name, type(exc).__name__, exc))
        entry = getattr(module, "main", None)
        if entry is None:
            raise ContractError("%s: no main() to build a parser" % module_name)
        try:
            entry()
        except _CapturedParser as captured:
            return captured.parser
        except SystemExit as exc:
            raise ContractError(
                "%s: main() exited (%r) before declaring a parser"
                % (module_name, exc.code))
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            raise ContractError(
                "%s: main() raised before declaring a parser: %s: %s"
                % (module_name, type(exc).__name__, exc))
        raise ContractError(
            "%s: main() returned without calling parse_args" % module_name)
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous


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


def load_interface_policy(root, records):
    """Load and close the agent call-surface policy over every CLI tool.

    Argparse remains the invocation source.  This separate document owns the
    question argparse cannot answer: whether the operation may enter an agent
    transport, which argument establishes the bound workspace, and which
    caller-supplied arguments carry filesystem effects.  Exact tool and
    argument closure makes an unclassified new CLI or path capability fail the
    compiler instead of inheriting MCP exposure silently.
    """
    path = os.path.join(root, *DEFAULT_INTERFACE_POLICY.split("/"))
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ContractError("cannot read %s: %s" %
                            (DEFAULT_INTERFACE_POLICY, exc))
    try:
        document = kblib.parse_yaml_subset(raw.decode("utf-8"))
    except (UnicodeError, kblib.YamlSubsetError) as exc:
        raise ContractError("%s is not parseable: %s" %
                            (DEFAULT_INTERFACE_POLICY, exc))
    if not isinstance(document, dict) or \
            document.get("artifact") != "agent-interface-policy" or \
            document.get("schema_version") != 1:
        raise ContractError(
            "%s must be agent-interface-policy schema_version 1"
            % DEFAULT_INTERFACE_POLICY)
    document_keys = {
        "schema_version", "artifact", "path_defaults", "path_overrides",
        "tools",
    }
    if set(document) != document_keys:
        raise ContractError(
            "%s must carry exactly %s" %
            (DEFAULT_INTERFACE_POLICY, ", ".join(sorted(document_keys))))

    def path_constraint(row, expected_keys, owner):
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise ContractError(
                "%s %s rows must carry exactly %s" %
                (DEFAULT_INTERFACE_POLICY, owner,
                 ", ".join(sorted(expected_keys))))
        argument = row.get("argument")
        constraint = row.get("constraint")
        value = row.get("value")
        suffixes = row.get("suffixes")
        if not isinstance(argument, str) or not argument:
            raise ContractError("%s: %s carries no argument" %
                                (DEFAULT_INTERFACE_POLICY, owner))
        if constraint not in ("contained", "exact", "namespace"):
            raise ContractError(
                "%s: %s.%s has unknown path constraint %r" %
                (DEFAULT_INTERFACE_POLICY, owner, argument, constraint))
        if constraint == "contained":
            if value is not None or suffixes not in (None, []):
                raise ContractError(
                    "%s: contained path constraints carry no value or "
                    "suffixes" % DEFAULT_INTERFACE_POLICY)
            value = None
            suffixes = []
        else:
            if not isinstance(value, str) or not value or \
                    os.path.isabs(value) or "\\" in value or \
                    os.path.normpath(value).replace(os.sep, "/") != value or \
                    value.startswith("../") or value == "..":
                raise ContractError(
                    "%s: %s.%s must name a canonical repository-relative "
                    "path" % (DEFAULT_INTERFACE_POLICY, owner, argument))
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
        return {
            "constraint": constraint,
            "value": value,
            "suffixes": list(suffixes),
        }

    defaults = {}
    default_rows = document.get("path_defaults")
    if not isinstance(default_rows, list):
        raise ContractError("%s carries no path_defaults list" %
                            DEFAULT_INTERFACE_POLICY)
    default_keys = {"argument", "constraint", "value", "suffixes"}
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
    override_keys = {"tool", "argument", "constraint", "value", "suffixes"}
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
            raise ContractError("%s names unknown CLI tool %s" %
                                (DEFAULT_INTERFACE_POLICY, name))
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
            capability = overrides.get(
                (name, argument), defaults.get(argument, {
                    "constraint": "contained", "value": None,
                    "suffixes": [],
                }))
            path_arguments.append({
                "argument": argument,
                "access": path_access[argument],
                "constraint": capability["constraint"],
                "value": capability["value"],
                "suffixes": list(capability["suffixes"]),
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
    if unused_defaults:
        raise ContractError("%s has unused path defaults: %s" %
                            (DEFAULT_INTERFACE_POLICY,
                             ", ".join(unused_defaults)))
    if invalid_overrides:
        raise ContractError(
            "%s has overrides for unclassified path arguments: %s" %
            (DEFAULT_INTERFACE_POLICY, ", ".join(
                "%s.%s" % item for item in invalid_overrides)))
    return by_name, kblib.sha256_bytes(raw)


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


def receipt_extensions(source_text):
    """Return (sorted extension field names, "complete" | "partial").

    Derived from the tool's own source: the names bound to a
    `make_*receipt(...)` result, then every constant key that source later
    writes onto one of those names. Base receipt fields are excluded --
    re-stamping `checked_at` is not an extension. A key computed at runtime
    cannot be named here, and downgrades the tool to `partial` rather than
    being silently dropped.
    """
    tree = ast.parse(source_text)
    receipt_names = set()
    keys = set()
    dynamic = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if isinstance(node.value, ast.Call) and _is_receipt_factory(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    receipt_names.add(target.id)
    if not receipt_names:
        # A factory call that is never bound to a name -- appended straight
        # into a list, passed on as an argument -- leaves nothing to trace
        # writes onto. Reporting "complete" here would assert that the tool
        # adds no extension field, which is exactly the claim this scan
        # cannot support. Say so.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_receipt_factory(node):
                return [], "partial"
        return [], "complete"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "update" \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in receipt_names:
            for argument in node.args:
                if isinstance(argument, ast.Dict):
                    for key in argument.keys:
                        if isinstance(key, ast.Constant) and isinstance(
                                key.value, str):
                            keys.add(key.value)
                        else:
                            dynamic = True
                else:
                    dynamic = True
            for keyword in node.keywords:
                if keyword.arg:
                    keys.add(keyword.arg)
                else:
                    dynamic = True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Subscript):
                    continue
                if not isinstance(target.value, ast.Name) or \
                        target.value.id not in receipt_names:
                    continue
                index = target.slice
                if isinstance(index, ast.Constant) and isinstance(
                        index.value, str):
                    keys.add(index.value)
                else:
                    dynamic = True
    for node in ast.walk(tree):
        # Extensions passed at the factory call itself, e.g.
        # make_pass_receipt(result, repository_snapshot_sha256=...).
        if isinstance(node, ast.Call) and _is_receipt_factory(node):
            for keyword in node.keywords:
                if keyword.arg:
                    keys.add(keyword.arg)
                else:
                    dynamic = True
    keys.difference_update(RECEIPT_BASE_FIELDS)
    return sorted(keys), ("partial" if dynamic else "complete")


# ---------------------------------------------------------------------------
# Composition and rendering
# ---------------------------------------------------------------------------


def compile_contract(root):
    """Return the contract mapping compiled from the repository's own tools."""
    root = os.path.abspath(root)
    tools = discover_tools(root)

    original_parse_args = argparse.ArgumentParser.parse_args
    original_dont_write = sys.dont_write_bytecode
    original_argv = list(sys.argv)
    sys.dont_write_bytecode = True

    def _capture(self, _args=None, _namespace=None):
        raise _CapturedParser(self)

    argparse.ArgumentParser.parse_args = _capture
    try:
        records = []
        for module_name, path, source_text in tools:
            # A tool may read sys.argv while declaring its parser; give every
            # tool the same neutral argv so the artifact cannot vary with how
            # this compiler was invoked.
            sys.argv = [os.path.basename(path)]
            parser = load_parser(module_name, path)
            extensions, completeness = receipt_extensions(source_text)
            records.append({
                "tool": module_name,
                "module": "%s/%s.py" % (TOOLS_SUBDIR, module_name),
                "source_hash": kblib.sha256_bytes(
                    source_text.encode("utf-8")),
                "description": normalize_text(parser.description),
                "arguments": describe_arguments(root, parser),
                "mutually_exclusive_groups": describe_exclusive_groups(parser),
                "receipt_extensions": extensions,
                "receipt_extensions_extraction": completeness,
            })
    finally:
        argparse.ArgumentParser.parse_args = original_parse_args
        sys.dont_write_bytecode = original_dont_write
        sys.argv = original_argv

    interface_policy, interface_policy_hash = load_interface_policy(
        root, records)
    for record in records:
        record["agent_interface"] = interface_policy[record["tool"]]

    manifest = "%s %s\n" % (
        DEFAULT_INTERFACE_POLICY, interface_policy_hash)
    manifest += "".join(
        "%s %s\n" % (record["module"], record["source_hash"])
        for record in records
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": "cli-invocation-contract",
        "generator": "%s/%s.py" % (TOOLS_SUBDIR, TOOL),
        "generator_version": TOOL_VERSION,
        "derived_from": "argparse-introspection",
        "source_files": ([DEFAULT_INTERFACE_POLICY] +
                         [record["module"] for record in records]),
        "source_hash": kblib.sha256_bytes(manifest),
        "agent_interface_policy": {
            "path": DEFAULT_INTERFACE_POLICY,
            "sha256": interface_policy_hash,
        },
        "receipt_shape": {
            "base_fields": list(RECEIPT_BASE_FIELDS),
            "conditional_fields": list(RECEIPT_CONDITIONAL_FIELDS),
            "extension_policy": "derived-per-tool-from-source",
        },
        "tool_count": len(records),
        "tools": records,
    }


def build_header(contract):
    return [
        "# Generated artifact -- do not edit directly.",
        "# Compiled by Tools/compile_cli_contract.py from each CLI's argparse",
        "#   declaration plus Tools/agent-interface-policy.yaml. Invocation",
        "#   shape comes from argparse; capability shape comes from the closed",
        "#   policy. A hand edit is reported by --check as a HOLD.",
        "# regenerate with: python3 Tools/compile_cli_contract.py .",
        "# verify with:     python3 Tools/compile_cli_contract.py . --check",
        "# `source_hash` covers the manifest of the %d tool sources listed"
        % contract["tool_count"],
        "#   under source_files, each with its own sha256.",
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
        help="artifact path to write or verify (default: <root>/%s)"
             % DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        return fail("root is not a directory: %s" % args.root)
    requested_output = args.output or DEFAULT_OUTPUT
    try:
        output = kblib.registered_repository_artifact_path(
            root, requested_output, DEFAULT_OUTPUT)
    except ValueError as exc:
        return fail("unsafe artifact output: %s" % exc)

    try:
        contract = compile_contract(root)
        text = render(contract)
    except ContractError as exc:
        return fail("evidence is unreliable: %s" % exc)
    except (kblib.YamlSubsetError, TypeError, ValueError) as exc:
        return fail("the compiled contract is not renderable: %s" % exc)

    if args.check:
        try:
            with open(output, "r", encoding="utf-8") as handle:
                existing = handle.read()
        except OSError as exc:
            print("%s --check: cannot read %s: %s" % (TOOL, output, exc))
            return 2
        if existing != text:
            print("%s --check: %s is stale or hand-edited; regenerate it "
                  "with `python3 Tools/compile_cli_contract.py .`"
                  % (TOOL, output))
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
