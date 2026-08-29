#!/usr/bin/env python3
"""render_host_configs.py -- host registration and corpus binding for the
Cambium MCP server, rendered once per host from one server definition.

The selected target's registered `mcp-tools.json` states what the server
offers. It does not
state where the server is or which corpus this run governs, and no host
reads it: a host reads its own configuration file. This tool renders those
files from one definition body, so "how Cambium is launched" is written
once rather than five times in five syntaxes that drift apart.

Registration and binding are two things
---------------------------------------
  registration  where the server is and how it starts -- `command`, `args`,
                `cwd`, and, for dsh, its connection-resilience block. Once
                per machine.
  binding       which corpus this server governs -- the
                `CAMBIUM_WORKSPACE_ROOT` environment variable. Once per
                corpus.

Three of the four hosts happen to write both into the same file, which
makes the distinction easy to miss. `dsh` separates them by force: the
registration lives in a profile under `$DSH_HOME` and the binding lives in
a `.env` beside the corpus. That separation is the reason this tool models
them as two things and lets each host recombine them, rather than modeling
one blob per host.

`CAMBIUM_WORKSPACE_ROOT` is the contract path for the binding. MCP's
2026-07-28 revision, when it deprecated roots, named server configuration
as the migration direction; an environment variable set by the host
configuration is that direction.

`cwd` is a fallback and nothing more. All four hosts start a stdio server
with the session's own working directory, and none of their plugin
packaging documentation mentions a `cwd` or an environment field at all --
so this tool does not rest on either. The load-bearing path is the
absolute one inside `args`; `cwd` is written for the case where a host
resolves a relative launch itself, and is marked undocumented wherever the
file format allows a comment.

Five products, five builders
----------------------------
`HOSTS` is a registry. Each entry names its own output file, its own
destination in an adopter's corpus, its own format, and its own builder.
Claude Code and Kimi Code are given separate entries writing separate
files even though their JSON shapes agree today: two hosts sharing one
file is a claim that they will keep agreeing, and nothing here can hold
them to it.

  claude-code        -> <corpus>/.mcp.json                registration + binding
  kimi-code          -> <corpus>/.kimi-code/mcp.json      registration + binding
  codex              -> <corpus>/.codex/config.toml       registration + binding
  dsh-env            -> <corpus>/.env                     binding only
  dsh-profile-patch  -> $DSH_HOME/profiles/<name>/        registration only

These are templates for an *adopter's* corpus repository, not files for
this repository. Source-distribution templates are rendered under
`Tools/compiled/host-configs/`. A carried interface may be rendered only into
an explicitly selected staging directory inside the adopter workspace but
outside `.cambium`; the adopted component root and workspace root must already
be bound. The staging directory is not runtime state and is not itself a path
a host loads.

Upstream binding
----------------
Every product carries `CAMBIUM_INTERFACE_SOURCE_HASH`, the sha256 of the
exact registered `mcp-tools.json` bytes it was rendered against, in
the environment the server is launched with -- so a server can refuse to
serve a tool list it was not registered against, and so one upstream
change makes all five products stale at once. It travels as an
environment value rather than a comment because two of the five formats
are JSON, which has no comment syntax, and a provenance field that only
three products can carry would bind only three.

Placeholders
------------
The shipped templates carry `<CAMBIUM_DISTRIBUTION_ROOT>` and
`<CAMBIUM_WORKSPACE_ROOT>`. Neither is a valid absolute path on any of
these hosts, so an un-substituted template fails loudly at launch instead
of resolving to something. `--distribution-root` and `--workspace-root`
substitute them for an onboarding flow that writes a bound copy directly.

Exit codes
----------
  0  written / `--check` passed.
  1  the evidence is unreliable: the compiled projection is missing,
     unparseable, or not the artifact it claims to be; it changed
     underneath this run; a rendered field could not be bound to a
     declaration source; the declared server name violates the host name
     intersection; or a skill manifest was found where the packaging rule
     forbids one.
  2  `--check` mismatch: a product is stale or hand-edited. A HOLD a
     person must read. Usage errors are 1, through `kblib.ArgumentParser`.

This tool registers no K00/12 Gate ID and emits no receipts, for the same
reason `compile_cli_contract.py` and `render_interface_projection.py` do
not: it depends on no selected profile, so `run_gates` -- which cannot
start before a profile is selected -- could never sweep it, and the kernel
requires an unclassifiable registry row to fail the run closed. `make
check` runs it directly, after its own upstream.
"""

import json
import os
import re
import shlex
import sys
import textwrap

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)

import kblib  # noqa: E402
import runtime_paths  # noqa: E402
import tool_availability  # noqa: E402

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - older interpreters
    tomllib = None

TOOL = "render_host_configs"
TOOL_VERSION = "1.3.0"

DEFAULT_PROJECTION = "Tools/compiled/mcp-tools.json"
DEFAULT_OUTPUT_DIR = "Tools/compiled/host-configs"
CARRIED_RUNTIME_PROJECTION = runtime_paths.MCP_TOOLS_ARTIFACT_PATH
UPSTREAM_ARTIFACT = "agent-interface-projection"
UPSTREAM_FORM = "mcp"
UPSTREAM_SCHEMA_VERSION = 4

# ---------------------------------------------------------------------------
# The server name
# ---------------------------------------------------------------------------

# One name, spelled the same in all four hosts. The permitted shape is the
# *intersection* of what the four accept, not the union: lowercase letters
# and digits joined by single hyphens, starting and ending on a letter or
# digit, no spaces, no consecutive hyphens. `NAME_ENVELOPE_RE` is the
# outer envelope the hosts state (underscores and 64 characters are inside
# it); `NAME_INTERSECTION_RE` is the narrower shape every one of them
# accepts. A name must satisfy both, and this run exits 1 if it does not,
# so the constraint is executable rather than a remark.
SERVER_NAME = "cambium"
NAME_ENVELOPE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
NAME_INTERSECTION_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# ---------------------------------------------------------------------------
# The one canonical server definition body
# ---------------------------------------------------------------------------

# Where this lives, and why it is a constant here rather than a compiled
# artifact under `Tools/compiled/`:
#
# `Tools/compiled/` holds generated artifacts, and this distribution
# defines a generated artifact as "a reproducible projection of its
# declared inputs" that owns no independent rule. Not one of `command`,
# `args`, `cwd`, or the resilience values below is derivable from
# `cli-contract.yaml` or `mcp-tools.json`: they are a decision about how
# this server is launched. A file in `Tools/compiled/` carrying them would
# have to advertise a `source_hash` binding it to an upstream that does
# not contain a single one of its fields -- a false binding, and a
# generated artifact holding an independent rule.
#
# The sibling projection already holds exactly this kind of value exactly
# this way: `render_interface_projection.MCP_TRANSPORTS` is "the one value
# in the projection that the compiled contract does not contain", declared
# as a constant with the observation it rests on. This is the same case
# one file over, so it gets the same treatment, and the constant stays a
# single source because every product below is built from it and every
# rendered field is admitted through `FIELD_SOURCES`.
DISTRIBUTION_PLACEHOLDER = "<CAMBIUM_DISTRIBUTION_ROOT>"
WORKSPACE_PLACEHOLDER = "<CAMBIUM_WORKSPACE_ROOT>"
SOURCE_HASH_PLACEHOLDER = "<CAMBIUM_INTERFACE_SOURCE_HASH>"

# The stdio entry point, resolved under the distribution root. It is named
# here as a path rather than assembled in a builder so that all five
# products name the same one.
# -- how `dsh` registers, which is not how the other three register --------
#
# The other three hosts take a server map: a name, and under it a command.
# `dsh` has no server map. Its profile is an ordered list of Cordis plugin
# entries, and one MCP server is one entry of the plugin
# `@deepseek-ai/dsh-mcp-client`, whose own config carries the transport,
# the namespace, and the command. The plugin is not in any shipped profile,
# so the patch must insert the entry rather than override a row that is
# already there -- and a patch entry with `insert` and no `id` appends at
# the top level, which is the placement this registration wants.
DSH_PLUGIN_NAME = "@deepseek-ai/dsh-mcp-client"
DSH_ENTRY_ID = "cambium-mcp"
# The transport arm of that plugin's discriminated union. `stdio` is the
# only arm a local subprocess server can take; the other arm is a URL.
DSH_TRANSPORT = "stdio"
# `serverName` is required, is the namespace every tool of this server is
# published under, and must match /^[A-Za-z0-9_-]{1,32}$/.
DSH_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

SERVER_COMMAND = "python3"
SERVER_ENTRY_POINT = "Tools/mcp_server.py"

WORKSPACE_ENV = "CAMBIUM_WORKSPACE_ROOT"
SOURCE_HASH_ENV = "CAMBIUM_INTERFACE_SOURCE_HASH"
PROJECTION_PATH_ENV = "CAMBIUM_INTERFACE_PROJECTION"
PROJECTION_PATH_PLACEHOLDER = "<CAMBIUM_INTERFACE_PROJECTION>"

MCP_SERVER = {
    # -- registration -----------------------------------------------------
    "command": SERVER_COMMAND,
    "args": ["%s/%s" % (DISTRIBUTION_PLACEHOLDER, SERVER_ENTRY_POINT)],
    "cwd": DISTRIBUTION_PLACEHOLDER,
    # -- binding ----------------------------------------------------------
    "env": {
        WORKSPACE_ENV: WORKSPACE_PLACEHOLDER,
        SOURCE_HASH_ENV: SOURCE_HASH_PLACEHOLDER,
        PROJECTION_PATH_ENV: PROJECTION_PATH_PLACEHOLDER,
    },
    # -- the dsh superset -------------------------------------------------
    # Three connection-resilience fields only `dsh` accepts. They are a
    # superset, not a disagreement: no other host contradicts them, they
    # simply have nowhere to put them, so the three products that cannot
    # carry them drop them rather than encoding a different intent.
    "resilience": {
        # A Cambium check scans a whole corpus; the slowest shipped scan is
        # a link check over every page. Two minutes is a ceiling above that,
        # chosen so a real scan is never cut off and a hung process still
        # ends.
        "toolCallTimeoutMs": 120000,
        # A session that quietly lost its governance surface is worse than
        # a session that refuses to start: the agent proceeds believing the
        # checks are there. Fail the startup instead.
        "failOnStartupError": True,
        "reconnect": {
            "enabled": True,
            # A stdio server that died three times in a row died for a
            # reason a retry will not fix.
            "maxAttempts": 3,
            # `dsh-mcp-client` names the backoff pair `initialDelayMs` and
            # `maxDelayMs`; there is no `delayMs` in its schema, and a name
            # it does not accept is a load-time validation failure.
            "initialDelayMs": 1000,
            "maxDelayMs": 30000,
        },
    },
}

REGISTRATION_FIELDS = ("command", "args", "cwd")
RESILIENCE_FIELD = "resilience"
ENV_FIELD = "env"

# ---------------------------------------------------------------------------
# Packaging rules that are enforced, not merely stated
# ---------------------------------------------------------------------------

# No skills ship with this registration, and no `SKILL.md` may sit at the
# root of what is packaged: Kimi Code reads a package root containing one
# as a single-skill bundle and stops looking for anything else in it. The
# rule is checked against the rendered tree and against every rendered
# document rather than written down and hoped for.
SKILL_MANIFEST = "SKILL.md"
FORBIDDEN_DOCUMENT_KEYS = frozenset(("skill", "skills"))

# ---------------------------------------------------------------------------
# Header text
# ---------------------------------------------------------------------------

NOTICE = (
    "Generated artifact -- do not edit. Every value here is rendered by "
    "Tools/%s.py from one server definition; a hand edit is reported by "
    "--check as a HOLD." % TOOL
)
BASE_INVOCATION = "python3 Tools/%s.py ." % TOOL
# Which flag substituted which placeholder. A header that named the bare
# command would be wrong for every bound render: re-running it would put
# the placeholders back, and `--check` would call the substituted file
# stale. The header therefore echoes the run that produced the file.
PLACEHOLDER_FLAGS = (
    (DISTRIBUTION_PLACEHOLDER, "--distribution-root"),
    (WORKSPACE_PLACEHOLDER, "--workspace-root"),
)


def invocation(context, check=False):
    """The command that reproduces this file, with this run's roots.

    A placeholder left unsubstituted contributes no flag, so an unbound
    render still prints the short form it is actually reproduced by.
    """
    carried = context["projection_target"] != \
        tool_availability.SOURCE_DISTRIBUTION
    if carried:
        script = os.path.join(context["root"], "Tools", TOOL + ".py")
        parts = ["python3 %s %s" % (
            shlex.quote(script), shlex.quote(context["root"]))]
        parts.append("--projection-target %s" %
                     context["projection_target"])
        parts.append("--output-dir %s" %
                     shlex.quote(context["output_dir"]))
    else:
        parts = [BASE_INVOCATION]
    if check:
        parts.append("--check")
    bound = dict(context["bindings"])
    for placeholder, flag in PLACEHOLDER_FLAGS:
        replacement = bound.get(placeholder, placeholder)
        if replacement != placeholder:
            parts.append("%s %s" % (flag, shlex.quote(replacement)))
    return " ".join(parts)

CWD_NOTE = (
    "cwd is a fallback only. All four hosts start a stdio server in the "
    "session's own working directory, and none of them document a cwd or "
    "an environment field in their plugin packaging contract at all. What "
    "this registration rests on is the absolute path inside args, and what "
    "binds the server to a corpus is %s -- never an inherited working "
    "directory." % WORKSPACE_ENV
)
SOURCE_HASH_NOTE = (
    "%s is the sha256 of the compiled tool projection this file was "
    "rendered against. It is carried so a server can refuse a tool list it "
    "was not registered against, and so one upstream change makes every "
    "host product stale at once." % SOURCE_HASH_ENV
)
PLACEHOLDER_NOTE_TEMPLATE = (
    "%s still to be substituted. A placeholder is not a valid absolute "
    "path on any of these hosts, so an un-substituted copy fails at launch "
    "instead of resolving to something."
)

# One manual step per host, and it is the host's security model rather
# than a gap in this line: none of these three can be completed by a
# repository on its own behalf.
MANUAL_STEPS = {
    "claude-code":
        "First contact is manual. Claude Code asks a person to trust this "
        "workspace before it loads a project-level .mcp.json; a repository "
        "that was just cloned cannot approve itself, and that is the point.",
    "kimi-code":
        "First contact is manual. Kimi Code ships no non-interactive "
        "registration command; the entry point is /mcp-config inside its "
        "TUI, so a person installs this once.",
    "codex":
        "First contact is manual. Codex reads a project-level "
        ".codex/config.toml only while the project is trusted, and only a "
        "person grants that trust.",
    "dsh-env":
        "This file is the binding half only: which corpus this session "
        "governs. The registration half is installed once per machine "
        "under $DSH_HOME/profiles/<name>/.",
    "dsh-profile-patch":
        "This is the registration half only, and it is installed once per "
        "machine rather than once per corpus. It is a loader patch list: "
        "append its entry to the profile's own cordis.patch.yml, or pass "
        "this file to --patch. The corpus binding travels separately in "
        "that corpus's .env, which dsh reads from the invoking directory "
        "and forwards to this server through the ordinary parent "
        "environment.",
}

HEADER_WIDTH = 72

# ---------------------------------------------------------------------------
# Declaration sources for every rendered field (self-checked below)
# ---------------------------------------------------------------------------

# Each key is a normalized path into one rendered product; each value names
# where that field comes from. Nothing may be rendered that is not bound
# here: `unbound_field_paths` walks what this run actually built and
# reports any path this table does not cover, which exits 1. The server
# name appears literally in these paths, so renaming the server also fails
# the run until the table is updated -- the name is a bound field, not a
# free string.

_SERVER_SOURCE = {
    "command":
        "Tools/render_host_configs.py: MCP_SERVER['command'] "
        "(SERVER_COMMAND)",
    "args[]":
        "Tools/render_host_configs.py: MCP_SERVER['args'], the distribution "
        "root placeholder joined to SERVER_ENTRY_POINT; --distribution-root "
        "substitutes the placeholder",
    "cwd":
        "Tools/render_host_configs.py: MCP_SERVER['cwd'], the distribution "
        "root placeholder; a documented fallback only (see CWD_NOTE)",
    "env.%s" % WORKSPACE_ENV:
        "Tools/render_host_configs.py: MCP_SERVER['env'][%r], the workspace "
        "placeholder; --workspace-root substitutes it. This is the binding, "
        "and the migration direction MCP 2026-07-28 named when it "
        "deprecated roots" % WORKSPACE_ENV,
    "env.%s" % SOURCE_HASH_ENV:
        "sha256 of the selected mcp-tools.json bytes this run read "
        "(kblib.sha256_bytes), substituted for MCP_SERVER['env'][%r]"
        % SOURCE_HASH_ENV,
    "env.%s" % PROJECTION_PATH_ENV:
        "Tools/render_host_configs.py: projection_path_binding() selects "
        "the registered source-distribution or adopter-runtime projection; "
        "substituted for MCP_SERVER['env'][%r]" % PROJECTION_PATH_ENV,
}

_RESILIENCE_SOURCE = {
    "toolCallTimeoutMs":
        "Tools/render_host_configs.py: MCP_SERVER['resilience'] -- dsh-only "
        "superset field, with the ceiling stated at the constant",
    "failOnStartupError":
        "Tools/render_host_configs.py: MCP_SERVER['resilience'] -- dsh-only "
        "superset field; true, with the reason stated at the constant",
    "reconnect.enabled":
        "Tools/render_host_configs.py: MCP_SERVER['resilience']['reconnect']",
    "reconnect.maxAttempts":
        "Tools/render_host_configs.py: MCP_SERVER['resilience']['reconnect']",
    "reconnect.initialDelayMs":
        "Tools/render_host_configs.py: MCP_SERVER['resilience']['reconnect']",
    "reconnect.maxDelayMs":
        "Tools/render_host_configs.py: MCP_SERVER['resilience']['reconnect']",
}

_HEADER_SOURCE = (
    "Tools/render_host_configs.py: header_lines() -- NOTICE, the HOSTS row's "
    "own destination and carried halves, SERVER_ENTRY_POINT, the upstream "
    "path and its sha256, the regenerate/verify commands this run "
    "reproduces itself with, MANUAL_STEPS[host], CWD_NOTE, "
    "SOURCE_HASH_NOTE and PLACEHOLDER_NOTE_TEMPLATE over the placeholders "
    "this run left unsubstituted, wrapped at HEADER_WIDTH"
)


def _server_paths(prefix, keys, extra=()):
    """Bind one server body's fields under one product path prefix."""
    bound = {}
    for key in keys:
        bound["%s.%s" % (prefix, key)] = _SERVER_SOURCE[key]
    for key in extra:
        bound["%s.%s" % (prefix, key)] = _RESILIENCE_SOURCE[key]
    return bound


def _header_paths(host, carried):
    """Bind the comment header of one product (empty for JSON)."""
    if carried:
        return {"%s.header[]" % host: _HEADER_SOURCE}
    return {"%s.header" % host:
            "Tools/render_host_configs.py: JSON carries no comment syntax, "
            "so this product renders no header and the list is empty"}


FIELD_SOURCES = {}
FIELD_SOURCES.update(_header_paths("claude-code", False))
FIELD_SOURCES.update(_server_paths(
    "claude-code.document.mcpServers.%s" % SERVER_NAME,
    ("command", "args[]", "cwd",
     "env.%s" % WORKSPACE_ENV, "env.%s" % SOURCE_HASH_ENV,
     "env.%s" % PROJECTION_PATH_ENV)))
FIELD_SOURCES.update(_header_paths("kimi-code", False))
FIELD_SOURCES.update(_server_paths(
    "kimi-code.document.mcpServers.%s" % SERVER_NAME,
    ("command", "args[]", "cwd",
     "env.%s" % WORKSPACE_ENV, "env.%s" % SOURCE_HASH_ENV,
     "env.%s" % PROJECTION_PATH_ENV)))
FIELD_SOURCES.update(_header_paths("codex", True))
FIELD_SOURCES.update(_server_paths(
    "codex.document.mcp_servers.%s" % SERVER_NAME,
    ("command", "args[]", "cwd",
     "env.%s" % WORKSPACE_ENV, "env.%s" % SOURCE_HASH_ENV,
     "env.%s" % PROJECTION_PATH_ENV)))
FIELD_SOURCES.update(_header_paths("dsh-env", True))
FIELD_SOURCES.update({
    "dsh-env.document.%s" % WORKSPACE_ENV:
        _SERVER_SOURCE["env.%s" % WORKSPACE_ENV],
    "dsh-env.document.%s" % SOURCE_HASH_ENV:
        _SERVER_SOURCE["env.%s" % SOURCE_HASH_ENV],
    "dsh-env.document.%s" % PROJECTION_PATH_ENV:
        _SERVER_SOURCE["env.%s" % PROJECTION_PATH_ENV],
})
FIELD_SOURCES.update(_header_paths("dsh-profile-patch", True))
_DSH_ENTRY = "dsh-profile-patch.document[].insert[]"
FIELD_SOURCES.update({
    "%s.id" % _DSH_ENTRY:
        "Tools/render_host_configs.py: DSH_ENTRY_ID -- the Cordis entry id "
        "this registration inserts into the profile tree",
    "%s.name" % _DSH_ENTRY:
        "Tools/render_host_configs.py: DSH_PLUGIN_NAME -- the plugin that "
        "connects one MCP server; dsh has no server map",
    "%s.config.transport" % _DSH_ENTRY:
        "Tools/render_host_configs.py: DSH_TRANSPORT -- the stdio arm of "
        "that plugin's discriminated config union",
    "%s.config.serverName" % _DSH_ENTRY:
        "Tools/render_host_configs.py: SERVER_NAME, checked against "
        "DSH_SERVER_NAME_RE -- the namespace this server's tools publish "
        "under, and dsh's equivalent of the other hosts' map key",
})
FIELD_SOURCES.update(_server_paths(
    "%s.config" % _DSH_ENTRY,
    ("command", "args[]", "cwd"),
    ("toolCallTimeoutMs", "failOnStartupError",
     "reconnect.enabled", "reconnect.maxAttempts",
     "reconnect.initialDelayMs", "reconnect.maxDelayMs")))


class RenderError(Exception):
    """The evidence for this run is unreliable; it must exit 1."""


def fail(message):
    print("%s: %s" % (TOOL, message))
    return 1


# ---------------------------------------------------------------------------
# Upstream
# ---------------------------------------------------------------------------


def read_projection(path):
    """Return (parsed interface projection, sha256 of its exact bytes)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise RenderError(
            "cannot read the compiled interface projection %s: %s -- render "
            "it with `python3 Tools/render_interface_projection.py .`"
            % (path, exc))
    try:
        projection = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RenderError(
            "the compiled interface projection %s does not parse: %s"
            % (path, exc))
    if not isinstance(projection, dict):
        raise RenderError(
            "the compiled interface projection %s is not an object" % path)
    if projection.get("artifact") != UPSTREAM_ARTIFACT:
        raise RenderError(
            "%s is not the %s artifact (it declares %r)"
            % (path, UPSTREAM_ARTIFACT, projection.get("artifact")))
    if projection.get("form") != UPSTREAM_FORM:
        raise RenderError(
            "%s is the %r form; this tool registers the %r form"
            % (path, projection.get("form"), UPSTREAM_FORM))
    if projection.get("schema_version") != UPSTREAM_SCHEMA_VERSION:
        raise RenderError(
            "%s declares schema_version %r; these host configurations are "
            "written against %d" % (path, projection.get("schema_version"),
                                    UPSTREAM_SCHEMA_VERSION))
    if not isinstance(projection.get("source_hash"), str):
        raise RenderError("%s carries no source_hash" % path)
    if projection.get("projection_target") not in \
            tool_availability.PROJECTION_TARGETS:
        raise RenderError("%s carries no valid projection_target" % path)
    tools = projection.get("tools")
    if not isinstance(tools, list) or not tools:
        raise RenderError(
            "%s lists no tools; registering a server that offers nothing is "
            "not a registration" % path)
    return projection, kblib.sha256_bytes(raw)


def projection_bytes_hash(path):
    with open(path, "rb") as handle:
        return kblib.sha256_bytes(handle.read())


def relativize(root, path):
    """Repository-relative spelling of a path inside `root`, else as given."""
    root = os.path.abspath(root)
    path = os.path.abspath(path)
    prefix = root + os.sep
    if path.startswith(prefix):
        return path[len(prefix):].replace(os.sep, "/")
    return path


def path_is_within(path, directory):
    """Return whether ``path`` resolves at or below ``directory``.

    String-prefix checks do not prove this on case-insensitive filesystems:
    ``.CAMBIUM`` and ``.cambium`` may name the same directory while retaining
    different input spellings.  Walk existing ancestors by file identity, then
    use the resolved spelling for the not-yet-created suffix.
    """
    path = os.path.realpath(os.path.abspath(path))
    directory = os.path.realpath(os.path.abspath(directory))
    current = path
    while True:
        if os.path.lexists(current) and os.path.lexists(directory):
            try:
                if os.path.samefile(current, directory):
                    return True
            except OSError:
                pass
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    try:
        return os.path.commonpath((path, directory)) == directory
    except ValueError:
        return False


def unsafe_output_component(root, output_dir):
    """Return an existing symlink/non-directory component below ``root``."""
    root = os.path.abspath(root)
    output_dir = os.path.abspath(output_dir)
    relative = os.path.relpath(output_dir, root)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return None
    current = root
    for part in relative.split(os.sep):
        if part in ("", "."):
            continue
        current = os.path.join(current, part)
        if not os.path.lexists(current):
            continue
        if os.path.islink(current) or not os.path.isdir(current):
            return current
    return None


def projection_for_target(projection_target):
    if projection_target == tool_availability.SOURCE_DISTRIBUTION:
        return DEFAULT_PROJECTION
    if projection_target == tool_availability.CARRIED_RUNTIME:
        return CARRIED_RUNTIME_PROJECTION
    raise ValueError("unknown projection target: %r" % projection_target)


def output_dir_for_target(projection_target):
    if projection_target == tool_availability.SOURCE_DISTRIBUTION:
        return DEFAULT_OUTPUT_DIR
    if projection_target == tool_availability.CARRIED_RUNTIME:
        return None
    raise ValueError("unknown projection target: %r" % projection_target)


def projection_path_binding(root, projection_path, projection_target):
    """Host-visible absolute projection path without component mutation."""
    expected = os.path.join(root, projection_for_target(projection_target))
    if os.path.realpath(os.path.abspath(projection_path)) == \
            os.path.realpath(os.path.abspath(expected)):
        if projection_target == tool_availability.SOURCE_DISTRIBUTION:
            return "%s/%s" % (
                DISTRIBUTION_PLACEHOLDER, DEFAULT_PROJECTION)
        return "%s/%s" % (WORKSPACE_PLACEHOLDER,
                           CARRIED_RUNTIME_PROJECTION)
    # Source-distribution fixture and installation renders may bind a
    # different explicit projection. Carried runtime is forced to its
    # adopter-owned registered path in main(), so it never reaches this arm.
    return os.path.abspath(projection_path)


# ---------------------------------------------------------------------------
# The definition body -> one host's document
# ---------------------------------------------------------------------------


def substitute(value, bindings):
    """Replace every declared placeholder token throughout one value."""
    if isinstance(value, dict):
        return {key: substitute(item, bindings)
                for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, bindings) for item in value]
    if isinstance(value, str):
        for placeholder, replacement in bindings:
            value = value.replace(placeholder, replacement)
        return value
    return value


def server_body(context, include_env=True, include_resilience=False):
    """One host's view of the canonical definition, placeholders resolved."""
    body = {key: MCP_SERVER[key] for key in REGISTRATION_FIELDS}
    if include_env:
        body[ENV_FIELD] = dict(MCP_SERVER[ENV_FIELD])
    if include_resilience:
        resilience = MCP_SERVER[RESILIENCE_FIELD]
        for key, value in resilience.items():
            body[key] = dict(value) if isinstance(value, dict) else value
    return substitute(body, context["bindings"])


def header_lines(host, context):
    """The comment header for one product, before any comment prefix.

    A product is told only about the halves it carries: the registration
    lines and the `cwd` caveat are written for a product that registers,
    and are absent from one that only binds. A header that described a
    field the file does not contain would be the drift this tool exists to
    prevent, one layer up.
    """
    entry = HOSTS[host]
    registers = "registration" in entry["carries"]
    lines = [NOTICE, ""]
    lines.append("destination: %s" % entry["destination"])
    lines.append("carries: %s" % ", ".join(entry["carries"]))
    lines.append("server name: %s" % SERVER_NAME)
    if registers:
        lines.append("server entry point: %s (under the distribution root)"
                     % SERVER_ENTRY_POINT)
    lines.append("source: %s" % context["source"])
    lines.append("source_hash: %s" % context["source_hash"])
    lines.append("regenerate: %s" % invocation(context))
    lines.append("verify: %s" % invocation(context, check=True))
    paragraphs = [MANUAL_STEPS[host]]
    if registers:
        paragraphs.append(CWD_NOTE)
    paragraphs.append(SOURCE_HASH_NOTE)
    remaining = [name for name in context["unsubstituted"]
                 if registers or name in (
                     WORKSPACE_PLACEHOLDER, PROJECTION_PATH_PLACEHOLDER)]
    if remaining:
        paragraphs.append(PLACEHOLDER_NOTE_TEMPLATE % " and ".join(remaining))
    for paragraph in paragraphs:
        lines.append("")
        lines.extend(textwrap.wrap(paragraph, HEADER_WIDTH))
    return lines


# ---------------------------------------------------------------------------
# One builder per host
# ---------------------------------------------------------------------------


def build_claude_code(host, context):
    """Claude Code reads `mcpServers` from a project-level `.mcp.json`."""
    return {
        "header": [],
        "document": {"mcpServers": {SERVER_NAME: server_body(context)}},
    }


def build_kimi_code(host, context):
    """Kimi Code reads the same object from `.kimi-code/mcp.json`.

    Deliberately a second builder writing a second file. The two shapes
    agree today; nothing in either host promises they will keep agreeing,
    and one shared file would quietly make that promise on their behalf.
    """
    return {
        "header": [],
        "document": {"mcpServers": {SERVER_NAME: server_body(context)}},
    }


def build_codex(host, context):
    """Codex reads `mcp_servers` from a project-level `.codex/config.toml`."""
    return {
        "header": header_lines(host, context),
        "document": {"mcp_servers": {SERVER_NAME: server_body(context)}},
    }


def build_dsh_env(host, context):
    """dsh reads the corpus binding, and only the binding, from `.env`."""
    body = server_body(context)
    return {
        "header": header_lines(host, context),
        "document": dict(body[ENV_FIELD]),
    }


def build_dsh_profile_patch(host, context):
    """dsh reads the registration, and only the registration, from a profile.

    This is the one product that carries the resilience superset, and the
    one product that is installed once per machine rather than once per
    corpus.
    """
    if not DSH_SERVER_NAME_RE.match(SERVER_NAME):
        raise RenderError(
            "dsh rejects serverName %r: it must match %s"
            % (SERVER_NAME, DSH_SERVER_NAME_RE.pattern))
    config = {"transport": DSH_TRANSPORT, "serverName": SERVER_NAME}
    config.update(
        server_body(context, include_env=False, include_resilience=True))
    return {
        "header": header_lines(host, context),
        "document": [{"insert": [{
            "id": DSH_ENTRY_ID,
            "name": DSH_PLUGIN_NAME,
            "config": config,
        }]}],
    }


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def comment_block(lines, prefix="#"):
    return [prefix if line == "" else "%s %s" % (prefix, line)
            for line in lines]


def render_json(product):
    """JSON through the shared canonical serializer, and no header.

    JSON has no comment syntax, so this product carries no header at all
    rather than a header smuggled into a key some host may reject.
    """
    if product["header"]:
        raise RenderError(
            "a JSON product cannot carry a comment header")
    return kblib.canonical_json_bytes(
        product["document"]).decode("utf-8") + "\n"


TOML_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def toml_scalar(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[%s]" % ", ".join(toml_scalar(item) for item in value)
    if not isinstance(value, str):
        raise RenderError(
            "unsupported TOML value type: %s" % type(value).__name__)
    if any(ord(character) < 32 or ord(character) == 127
           for character in value):
        raise RenderError("TOML strings must not contain control characters")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % escaped


def toml_table_lines(document, path=()):
    """Deterministic TOML for the restricted shape these products use.

    Keys are emitted in sorted order, scalars before sub-tables, and a
    table header is written only when the table has values of its own --
    an intermediate table is left implicit rather than emitted empty.
    """
    scalars = []
    tables = []
    for key in sorted(document):
        if not isinstance(key, str) or not TOML_BARE_KEY_RE.fullmatch(key):
            raise RenderError("unsupported TOML key: %r" % (key,))
        child = document[key]
        if isinstance(child, dict):
            tables.append((key, child))
        else:
            scalars.append((key, child))
    lines = []
    if path and (scalars or not tables):
        lines.append("[%s]" % ".".join(path))
        for key, value in scalars:
            lines.append("%s = %s" % (key, toml_scalar(value)))
    elif scalars:
        raise RenderError(
            "a top-level TOML scalar would be read by Codex as a global "
            "setting rather than part of this server's registration")
    for key, table in tables:
        if lines:
            lines.append("")
        lines.extend(toml_table_lines(table, path + (key,)))
    return lines


def render_toml(product):
    lines = comment_block(product["header"])
    body = toml_table_lines(product["document"])
    if body:
        lines.append("")
        lines.extend(body)
    return "\n".join(lines) + "\n"


DOTENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def dotenv_lines(document):
    """Deterministic dotenv rows.

    Values are always double-quoted, because a real corpus path may contain
    a space. A value containing a quote, a backslash, or a control
    character is refused rather than escaped: the escape grammar of a
    dotenv file is not agreed between readers, so an escaped value would be
    a guess about which reader is on the other side.
    """
    lines = []
    for key in sorted(document):
        if not isinstance(key, str) or not DOTENV_KEY_RE.fullmatch(key):
            raise RenderError("unsupported environment variable name: %r"
                              % (key,))
        value = document[key]
        if not isinstance(value, str):
            raise RenderError(
                "an environment value is text; %s is %s"
                % (key, type(value).__name__))
        if any(ord(character) < 32 for character in value) or \
                '"' in value or "\\" in value:
            raise RenderError(
                "%s carries a quote, a backslash, or a control character, "
                "which this dotenv writer refuses rather than escapes" % key)
        lines.append('%s="%s"' % (key, value))
    return lines


def render_dotenv(product):
    lines = comment_block(product["header"])
    body = dotenv_lines(product["document"])
    if body:
        lines.append("")
        lines.extend(body)
    return "\n".join(lines) + "\n"


def yaml_body_lines(document):
    """The document as YAML lines, mapping or top-level sequence.

    `kblib.canonical_yaml` renders a mapping. A dsh patch list is a
    top-level sequence of mappings, so each element is rendered through
    that same canonical renderer and then indented under its own `- `,
    which keeps one serializer responsible for every scalar and every
    nested level rather than growing a second YAML writer here.
    """
    if isinstance(document, dict):
        return kblib.canonical_yaml(document).rstrip("\n").split("\n")
    if not isinstance(document, list):
        raise RenderError(
            "a YAML product must be a mapping or a sequence of mappings")
    lines = []
    for element in document:
        if not isinstance(element, dict):
            raise RenderError(
                "a top-level YAML sequence must hold mappings")
        rendered = kblib.canonical_yaml(element).rstrip("\n").split("\n")
        lines.append("- %s" % rendered[0])
        lines.extend("  %s" % line for line in rendered[1:])
    return lines


def render_yaml(product):
    """YAML through the shared canonical renderer, with a comment header."""
    lines = comment_block(product["header"])
    body = yaml_body_lines(product["document"])
    if body:
        lines.append("")
        lines.extend(body)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Validators: every product is re-read through a parser for its own format
# ---------------------------------------------------------------------------


def parse_dotenv(text):
    data = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            raise ValueError("dotenv row without an assignment: %r" % line)
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        data[key] = value
    return data


def validator_for(fmt, document):
    """A parser that must read back exactly the document that was written."""
    def check_json(text):
        if json.loads(text) != document:
            raise ValueError("JSON did not round-trip")

    def check_toml(text):
        if tomllib is None:  # pragma: no cover - older interpreters
            return
        if tomllib.loads(text) != document:
            raise ValueError("TOML did not round-trip")

    def check_dotenv(text):
        if parse_dotenv(text) != document:
            raise ValueError("dotenv did not round-trip")

    def check_yaml(text):
        parsed = kblib.parse_yaml_subset(text)
        if parsed != document:
            raise ValueError("YAML did not round-trip")

    return {
        "json": check_json,
        "toml": check_toml,
        "dotenv": check_dotenv,
        "yaml": check_yaml,
    }[fmt]


SERIALIZERS = {
    "json": render_json,
    "toml": render_toml,
    "dotenv": render_dotenv,
    "yaml": render_yaml,
}


# ---------------------------------------------------------------------------
# The host registry
# ---------------------------------------------------------------------------

HOSTS = {
    "claude-code": {
        "output": "claude-code.mcp.json",
        "destination": "<corpus>/.mcp.json",
        "carries": ("registration", "binding"),
        "format": "json",
        "build": build_claude_code,
        "summary": "Claude Code project-level MCP server registration",
    },
    "kimi-code": {
        "output": "kimi-code.mcp.json",
        "destination": "<corpus>/.kimi-code/mcp.json",
        "carries": ("registration", "binding"),
        "format": "json",
        "build": build_kimi_code,
        "summary": "Kimi Code project-level MCP server registration",
    },
    "codex": {
        "output": "codex.config.toml",
        "destination": "<corpus>/.codex/config.toml",
        "carries": ("registration", "binding"),
        "format": "toml",
        "build": build_codex,
        "summary": "Codex project-level configuration (trusted projects only)",
    },
    "dsh-env": {
        "output": "dsh.env",
        "destination": "<corpus>/.env",
        "carries": ("binding",),
        "format": "dotenv",
        "build": build_dsh_env,
        "summary": "dsh corpus binding, one per corpus",
    },
    "dsh-profile-patch": {
        "output": "dsh-profile-patch.yaml",
        "destination":
            "$DSH_HOME/profiles/<name>/cordis.patch.yml (append this entry) "
            "or dsh --patch <path>",
        "carries": ("registration",),
        "format": "yaml",
        "build": build_dsh_profile_patch,
        "summary": "dsh profile registration rows, once per machine",
    },
}


# ---------------------------------------------------------------------------
# Field-source self-check
# ---------------------------------------------------------------------------


def artifact_field_paths(node, path=""):
    """Every normalized field path present in one built product."""
    if isinstance(node, dict):
        if not node:
            return {path}
        found = set()
        for key in sorted(node):
            found |= artifact_field_paths(
                node[key], "%s.%s" % (path, key) if path else key)
        return found
    if isinstance(node, list):
        if not node:
            return {path}
        found = set()
        for item in node:
            found |= artifact_field_paths(item, path + "[]")
        return found
    return {path}


def unbound_field_paths(products):
    """Paths these products render that no declaration source covers."""
    found = set()
    for host, product in products:
        found |= artifact_field_paths(product, host)
    return sorted(found - set(FIELD_SOURCES))


def forbidden_document_keys(products):
    """Keys the packaging rule forbids, anywhere in any rendered document."""
    found = set()
    for host, product in products:
        stack = [product["document"]]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    if key.lower() in FORBIDDEN_DOCUMENT_KEYS:
                        found.add("%s: %s" % (host, key))
                    stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
    return sorted(found)


def skill_manifests(directory):
    """Every `SKILL.md` under the rendered tree, which must be none."""
    found = []
    for current, directories, files in os.walk(directory):
        directories.sort()
        for name in sorted(files):
            if name == SKILL_MANIFEST:
                found.append(os.path.join(current, name))
    return found


def name_violations(name):
    problems = []
    if not NAME_ENVELOPE_RE.fullmatch(name):
        problems.append("outside the host name envelope %s"
                        % NAME_ENVELOPE_RE.pattern)
    if not NAME_INTERSECTION_RE.fullmatch(name):
        problems.append("outside the four-host intersection %s"
                        % NAME_INTERSECTION_RE.pattern)
    return problems


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def print_sources():
    print("%s: %d rendered field path(s), each bound to a declaration source"
          % (TOOL, len(FIELD_SOURCES)))
    for path in sorted(FIELD_SOURCES):
        print("  %s\n      <- %s" % (path, FIELD_SOURCES[path]))


def entry_point_note(root):
    if os.path.isfile(os.path.join(root, SERVER_ENTRY_POINT)):
        return None
    return ("note: the declared stdio entry point %s is not present in this "
            "repository yet, so what is rendered is the registration shape "
            "for it; the tool surface it will serve is already compiled in "
            "%s" % (SERVER_ENTRY_POINT, DEFAULT_PROJECTION))


def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Render the Cambium MCP server's registration and corpus "
                    "binding into the configuration file each supported host "
                    "reads.")
    parser.add_argument(
        "root",
        help="repository root holding the compiled interface projection")
    parser.add_argument(
        "--host", choices=sorted(HOSTS), default=None,
        help="render only this host's product (default: every host)")
    parser.add_argument(
        "--projection", default=None,
        help="compiled interface projection to bind to; defaults to the one "
             "owned by --projection-target")
    parser.add_argument(
        "--projection-target",
        choices=list(tool_availability.PROJECTION_TARGETS),
        default=tool_availability.SOURCE_DISTRIBUTION,
        help="render tracked distribution templates or products bound to an "
             "adopter's carried interface (default: source-distribution)")
    parser.add_argument(
        "--output-dir", default=None,
        help="directory to write or verify the products in; carried-runtime "
             "requires an explicit repository-contained staging directory "
             "outside %s"
             % runtime_paths.RUNTIME_ROOT)
    parser.add_argument(
        "--distribution-root", default=None,
        help="absolute path of the Cambium checkout the server is launched "
             "from; substituted for %s (default: leave the placeholder)"
             % DISTRIBUTION_PLACEHOLDER)
    parser.add_argument(
        "--workspace-root", default=None,
        help="absolute path of the corpus repository this registration is "
             "bound to; substituted for %s (default: leave the placeholder)"
             % WORKSPACE_PLACEHOLDER)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true",
        help="re-render and compare against the existing products; exit 0 "
             "when byte-identical, 2 when one is stale or hand-edited")
    mode.add_argument(
        "--sources", action="store_true",
        help="print the declaration source of every rendered field and exit "
             "without reading or writing any product")
    args = parser.parse_args(argv)

    if args.sources:
        print_sources()
        return 0

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        return fail("root is not a directory: %s" % args.root)

    for label, value in (("--distribution-root", args.distribution_root),
                         ("--workspace-root", args.workspace_root)):
        if value is not None and not os.path.isabs(value):
            parser.error(
                "%s must be an absolute path: a host starts this server from "
                "its own session directory, so a relative path names nothing "
                "the host can resolve" % label)

    if args.projection_target == tool_availability.CARRIED_RUNTIME:
        missing = [
            flag for flag, value in (
                ("--output-dir", args.output_dir),
                ("--distribution-root", args.distribution_root),
                ("--workspace-root", args.workspace_root),
            ) if not value
        ]
        if missing:
            parser.error(
                "carried-runtime host products require explicit %s; host "
                "installation configuration is not adopter runtime state"
                % ", ".join(missing))
        if not os.path.isabs(args.output_dir):
            parser.error(
                "--output-dir must be absolute for carried-runtime host "
                "configuration staging")
        if os.path.realpath(args.workspace_root) != os.path.realpath(root):
            parser.error(
                "--workspace-root must name the same adopter workspace as "
                "root when binding its carried interface projection")
        if os.path.realpath(args.distribution_root) != os.path.realpath(root):
            parser.error(
                "--distribution-root must name the same adopted component "
                "root as root; binding another Cambium checkout would split "
                "the server implementation from the adopted interface")
        entry_point = os.path.join(
            args.distribution_root, SERVER_ENTRY_POINT)
        if os.path.islink(entry_point) or not os.path.isfile(entry_point):
            parser.error(
                "--distribution-root must contain the regular server entry "
                "point %s" % SERVER_ENTRY_POINT)

    problems = name_violations(SERVER_NAME)
    if problems:
        return fail("the declared server name %r is %s; the four hosts do "
                    "not all accept it" % (SERVER_NAME, "; ".join(problems)))

    projection_relative = projection_for_target(args.projection_target)
    projection_path = args.projection or os.path.join(
        root, projection_relative)
    if not os.path.isabs(projection_path):
        projection_path = os.path.join(root, projection_path)

    if args.projection_target == tool_availability.CARRIED_RUNTIME:
        try:
            projection_path = kblib.registered_repository_artifact_path(
                root, projection_path, CARRIED_RUNTIME_PROJECTION)
        except ValueError as exc:
            return fail("unsafe carried-runtime projection input: %s" % exc)

    try:
        projection, projection_hash = read_projection(projection_path)
    except RenderError as exc:
        return fail("evidence is unreliable: %s" % exc)
    if projection["projection_target"] != args.projection_target:
        return fail(
            "evidence is unreliable: %s was built for projection target %r, "
            "not requested target %r"
            % (relativize(root, projection_path),
               projection["projection_target"], args.projection_target))

    output_relative = output_dir_for_target(args.projection_target)
    output_dir = args.output_dir or os.path.join(root, output_relative)
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(root, output_dir)
    if (not path_is_within(output_dir, root) or
            path_is_within(root, output_dir)):
        return fail(
            "unsafe host-config output: staging must be a directory inside "
            "the repository root")
    unsafe_component = unsafe_output_component(root, output_dir)
    if unsafe_component is not None:
        return fail(
            "unsafe host-config output: staging traverses a symlink or file: "
            "%s" % relativize(root, unsafe_component))
    runtime_root = os.path.realpath(os.path.join(
        root, runtime_paths.RUNTIME_ROOT))
    if path_is_within(output_dir, runtime_root):
        return fail(
            "unsafe host-config output: installation and MCP transport "
            "configuration must remain outside %s"
            % runtime_paths.RUNTIME_ROOT)
    if args.projection_target == tool_availability.CARRIED_RUNTIME:
        protected_outputs = {
            os.path.realpath(os.path.join(candidate, DEFAULT_OUTPUT_DIR))
            for candidate in (root, args.distribution_root)
        }
        if any(path_is_within(output_dir, protected)
               for protected in protected_outputs):
            return fail(
                "unsafe carried-runtime host-config output: the tracked "
                "source-distribution products under %s cannot be overwritten"
                % DEFAULT_OUTPUT_DIR)

    bindings = (
        (PROJECTION_PATH_PLACEHOLDER, projection_path_binding(
            root, projection_path, args.projection_target)),
        (DISTRIBUTION_PLACEHOLDER,
         args.distribution_root or DISTRIBUTION_PLACEHOLDER),
        (WORKSPACE_PLACEHOLDER,
         args.workspace_root or WORKSPACE_PLACEHOLDER),
        (SOURCE_HASH_PLACEHOLDER, projection_hash),
    )
    context = {
        "source": relativize(root, projection_path),
        "source_hash": projection_hash,
        "projection_target": args.projection_target,
        "root": root,
        "output_dir": output_dir,
        "bindings": bindings,
        # Named so a header speaks only of the placeholders its own file
        # still carries; a bound render says nothing about substitution.
        "unsubstituted": tuple(
            placeholder for placeholder, replacement in bindings
            if placeholder == replacement),
    }

    hosts = [args.host] if args.host else sorted(HOSTS)
    products = []
    for host in hosts:
        entry = HOSTS[host]
        try:
            product = entry["build"](host, context)
        except RenderError as exc:
            return fail("evidence is unreliable: the %s product could not be "
                        "built: %s" % (host, exc))
        products.append((host, product))

    unbound = unbound_field_paths(products)
    if unbound:
        return fail(
            "evidence is unreliable: field(s) no declaration source covers: "
            "%s -- add the source to FIELD_SOURCES or stop rendering the "
            "field; a configuration layer decides nothing on its own"
            % ", ".join(unbound))

    forbidden = forbidden_document_keys(products)
    if forbidden:
        return fail(
            "evidence is unreliable: this registration ships no skills, and "
            "these product(s) declare one: %s" % ", ".join(forbidden))

    rendered = []
    for host, product in products:
        entry = HOSTS[host]
        try:
            text = SERIALIZERS[entry["format"]](product)
        except (RenderError, ValueError, TypeError,
                kblib.YamlSubsetError) as exc:
            return fail("evidence is unreliable: the %s product is not "
                        "renderable as %s: %s" % (host, entry["format"], exc))
        rendered.append((host, os.path.join(output_dir, entry["output"]),
                         text, product))

    # Time-of-check / time-of-use: everything above was rendered against the
    # projection bytes read once at the start. If it has moved since, this
    # run observed two upstreams and its verdict would describe neither.
    try:
        recheck = projection_bytes_hash(projection_path)
    except OSError as exc:
        return fail("evidence is unreliable: the compiled interface "
                    "projection became unreadable during this run: %s" % exc)
    if recheck != projection_hash:
        return fail(
            "evidence is unreliable: %s changed while this run was reading "
            "it (%s -> %s); nothing was written and no verdict is reported"
            % (relativize(root, projection_path), projection_hash, recheck))

    note = entry_point_note(args.distribution_root or root)
    if note:
        print("%s: %s" % (TOOL, note))

    if args.check:
        intruders = skill_manifests(output_dir) \
            if os.path.isdir(output_dir) else []
        if intruders:
            return fail(
                "evidence is unreliable: a %s under %s makes this package "
                "root a single-skill bundle to Kimi Code: %s"
                % (SKILL_MANIFEST, relativize(root, output_dir),
                   ", ".join(relativize(root, path) for path in intruders)))
        stale = 0
        for host, output, text, _product in rendered:
            try:
                existing = kblib.read_text(output)
            except OSError as exc:
                print("%s --check: cannot read %s: %s" % (TOOL, output, exc))
                stale += 1
                continue
            if existing != text:
                print("%s --check: %s is stale or hand-edited; regenerate "
                      "it with `%s`"
                      % (TOOL, output, invocation(context)))
                stale += 1
                continue
            print("%s --check: %s is current (%s, %s)"
                  % (TOOL, output, host, "+".join(HOSTS[host]["carries"])))
        return 2 if stale else 0

    for host, output, text, product in rendered:
        entry = HOSTS[host]
        kblib.atomic_write_text(
            output, text,
            validator=validator_for(entry["format"], product["document"]))
        print("%s: wrote %s (%s -> %s, %s, %d byte(s))"
              % (TOOL, output, host, entry["destination"],
                 "+".join(entry["carries"]), len(text)))

    intruders = skill_manifests(output_dir)
    if intruders:
        return fail(
            "evidence is unreliable: a %s under %s makes this package root a "
            "single-skill bundle to Kimi Code: %s"
            % (SKILL_MANIFEST, relativize(root, output_dir),
               ", ".join(relativize(root, path) for path in intruders)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
