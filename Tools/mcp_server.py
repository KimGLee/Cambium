#!/usr/bin/env python3
"""mcp_server.py -- the stdio entry point the host configurations name.

The interface projection named by `CAMBIUM_INTERFACE_PROJECTION` states what
the server offers. A source distribution normally binds
`Tools/compiled/mcp-tools.json`; a carried runtime binds the adopter-owned
`.cambium/derived/interfaces/mcp-tools.json`. Host configurations state where
the server is and which corpus it governs. None of them is a server: a host
holding those files still
has nothing to connect to.  This module is the missing half -- layer 3, and
only layer 3: how an operation is called, how its arguments get in, and how
its result gets back out.

What this file is not
---------------------
It is not a tool.  It declares no `argparse` parser and defines no `main()`,
so `compile_cli_contract.discover_tools` does not see it and it never
appears in its own tool list.  That is deliberate rather than incidental: a
transport that advertised itself as a callable operation would be the exact
layer smear this file exists to avoid.  It is started by a host, reads
JSON-RPC on stdin and writes JSON-RPC on stdout, and takes no command-line
arguments at all.

It imports no check, applier, or judgment module. Its sole Cambium import is
`runtime_paths`, the machine owner of adopter-runtime path spellings. This is
the executable form of "layer 3 only carries": the transport can enforce the
registered projection location without gaining access to a governance
judgment. `Tools/tests/test_mcp_server.py` asserts that narrow import boundary
statically so it survives future edits. The remaining imports are from the
standard library; sha256 and canonical `json.dumps` stay local so no judgment
seam can be crossed by accident.

Protocol
--------
JSON-RPC 2.0, one message per line, over stdin/stdout.

The MCP specification's current revision is `2026-07-28`, and that revision
has no `initialize` at all: it is stateless, carries version and
capabilities as per-request `_meta`, and requires `server/discover`.  The
`initialize` handshake belongs to what that revision calls the *legacy*
era, whose latest revision is `2025-11-25`.  This server implements the
legacy era at `2025-11-25`, which is what every generated host configuration
is written for today.

That choice is compatible in the direction that matters.  The `2026-07-28`
backward-compatibility rule for stdio says a modern client probes with
`server/discover` and falls back to `initialize` on any error that is not a
recognized modern error.  `server/discover` is not implemented here, so it
receives `-32601 Method not found` -- not a modern error -- and a dual-era
client falls back to the handshake this server does implement.  Returning
an error for it is therefore the correct behaviour, not a gap to paper
over.

Version negotiation follows the `2025-11-25` lifecycle rule verbatim: if
the client's requested version is one this server supports, respond with
that same version; otherwise respond with the latest version this server
supports and let the client decide whether to continue or disconnect.
`SUPPORTED_PROTOCOL_VERSIONS` lists only revisions whose wire shape was
actually read, because claiming a revision on the strength of a guess is
the same defect as guessing a verdict.

Methods answered: `initialize`, `notifications/initialized`, `tools/list`,
`tools/call`, `ping`.  Every other *request* receives `-32601`.  Every
other *notification* receives nothing, because JSON-RPC 2.0 forbids
responding to a notification at all; it is reported on stderr instead.
That is the one place where "answer with an error" is not available, and it
is a rule of the base protocol rather than a decision taken here.

The tool list is a projection, never a recomputation
----------------------------------------------------
`tools/list` returns `name`, `description` and `inputSchema` straight out of
the projection pinned for this session. This module does not read
`cli-contract.yaml`, does not introspect any parser, and does not adjust a
schema on the way past.

The projection is loaded, validated and pinned during `initialize`, and a
failure there fails `initialize`: a server that came up with an empty or
half-read tool table would be advertising an interface it cannot honour.
Validation is existence and agreement only -- the artifact says what it
claims to be, its `tool_count` matches the list it carries, every tool names
a script that is actually present under `Tools/`, and, when the host passed
`CAMBIUM_INTERFACE_SOURCE_HASH`, the bytes hash to the value the host was
registered against.  That last check is the one the renderer wrote the
variable for: "so a server can refuse to serve a tool list it was not
registered against".

Execution is a subprocess, always
---------------------------------
`tools/call` runs `python3 Tools/<tool>.py <args...> --json` as a child
process.  It never imports the tool and calls a function.

Importing would be faster and would be wrong.  Every gate, every lock,
every receipt write, every exit code in this distribution is expressed at
the process boundary; a tool reached through an import runs inside this
process's interpreter state, with this process's `sys.path`, working
directory, and already-imported modules, and any of those can change what
the tool does.  The subprocess is the conservative form because it is the
same form a person gets from the README, and because the only thing it
shares with this server is the environment it was handed.

`--json` is appended whenever the tool declares it, so the receipt objects
arrive on stdout as one canonical JSON array and the human-readable report
arrives on stderr -- which is exactly the split that flag was added for.
The flag is owned by this layer; a caller-supplied `json` argument changes
nothing and is reported back as ignored rather than silently dropped.

Not every tool declares it: several emit no receipts and write their whole
report to stdout. Neither stream is ever discarded on that account. When
`--json` was requested, stdout is the receipt array and stderr the report;
when it was not, stdout is carried through as text alongside stderr. A
transport that dropped a stream because it did not know what was in it
would be losing the tool's answer, which is the one thing it exists to
carry.

The seam rule
-------------
A refusal by the kernel must reach the caller as that refusal.  A failure
must not be dressed up as a refusal, and a refusal must not be rewritten
into a failure.  Telling them apart here is done by *reading a field*, never
by inspecting prose:

    exit 0  clean success
    exit 1  a failure, or evidence the tool judged unreliable -- one code
            covering two outcomes, and this layer does not split it,
            because only the tool knows which one it meant
    exit 2  HOLD: no failure, but something a person must read

`isError` is a two-valued field and there are more than two outcomes, so
this server does not use it as the verdict channel and no reader should.
The verdict travels verbatim as `exit_code` and `verdict` in
`structuredContent`, and as the first line of the text content.  `isError`
is set for any non-zero exit for one narrow reason: so that no host renders
a held or failed run as a clean one.  A HOLD is never labelled a success and
never labelled a failure anywhere in the payload -- it is labelled `hold`,
which is what it is.

An exit code outside {0, 1, 2} has no defined meaning in this distribution,
so it is reported as `unreadable` with the raw code attached.  Likewise, if
a `--json` run's stdout cannot be parsed, the payload says `unparseable`,
carries the raw bytes verbatim, and infers nothing from them.  Reporting
"I could not read this" is always available; guessing a result never is.

What this layer refuses, and what it does not
---------------------------------------------
It refuses calls for which no argv can be formed and calls that contradict the
host binding carried by the compiled interface policy.  Every MCP operation
must supply its declared workspace argument, that argument must resolve to the
session's `CAMBIUM_WORKSPACE_ROOT`, and every effective filesystem path -- an
explicit value or an omitted argparse default -- must remain inside its typed
envelope.  These are transport capabilities, not domain judgments: enum
membership, state transitions, evidence sufficiency, and the meaning of a
tool's result remain with the tool.

The binding
-----------
`CAMBIUM_WORKSPACE_ROOT` names the corpus this session governs, and it is
read from the environment only.  There is no fall back to the working
directory: cwd inheritance is undocumented best-effort in all four hosts --
`render_host_configs.py` says so at length -- and an undocumented
best-effort is not something a binding may rest on.  An unset, relative, or
un-substituted value fails `initialize` with a message naming the variable
the host has to set.

Initialize opens and pins the canonical directory object.  That descriptor,
not a pathname resolved a second time, becomes every child process's working
directory, so replacing or retargeting the configured path cannot transfer an
in-flight session to another corpus.  The closed projection also declares
which argument must resolve back to that same root and which arguments are
filesystem capabilities.  The server refuses a missing or alternate root and
refuses typed paths outside their declared contained, exact, or namespace
envelope before a child exists.  The child receives `.` for the workspace
argument so it resolves from the pinned object; ordinary path argument values
are preserved.  Tools still own state authorization, evidence sufficiency,
and verdicts.
"""

import os
import sys
import tempfile

# Bootstrap before the sole repository-local import below.  A carried MCP
# server is itself part of the immutable component set; starting it must not
# create or consume adopter-local bytecode that would make the next trusted
# component check fail.  Children inherit the exported boundary.
def _external_pycache_prefix():
    repository_root = os.path.realpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir))
    for raw_root in (tempfile.gettempdir(), "/var/tmp", "/tmp"):
        candidate_root = os.path.realpath(os.path.abspath(raw_root))
        if not os.path.isdir(candidate_root):
            continue
        try:
            if os.path.commonpath(
                    (repository_root, candidate_root)) == repository_root:
                continue
        except ValueError:
            pass
        candidate = os.path.join(
            candidate_root,
            "cambium-adoption-pycache-%s" % os.urandom(16).hex())
        if not os.path.lexists(candidate):
            return candidate
    raise RuntimeError("no repository-external Python cache root is available")


_CAMBIUM_PYCACHE_PREFIX = _external_pycache_prefix()
os.environ["PYTHONPYCACHEPREFIX"] = _CAMBIUM_PYCACHE_PREFIX
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.pycache_prefix = _CAMBIUM_PYCACHE_PREFIX
sys.dont_write_bytecode = True

import hashlib
import json
import stat
import subprocess
import uuid
import traceback

import runtime_paths

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

# The same name the five host configuration products register, spelled the
# same way. `render_host_configs.SERVER_NAME` is the declaration; this is
# the server answering to it.
SERVER_NAME = "cambium"
SERVER_VERSION = "1.2.0"
SERVER_TITLE = "Cambium"

# Every protocol revision whose wire shape was read before being claimed.
# The first entry is the latest, and is what an unrecognized request
# negotiates down to per the 2025-11-25 lifecycle rule.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25",)
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

# ---------------------------------------------------------------------------
# Where things are
# ---------------------------------------------------------------------------

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
DISTRIBUTION_ROOT = os.path.dirname(TOOLS_DIR)
PROJECTION_RELATIVE = "Tools/compiled/mcp-tools.json"
CARRIED_PROJECTION_RELATIVE = runtime_paths.MCP_TOOLS_ARTIFACT_PATH

WORKSPACE_ENV = "CAMBIUM_WORKSPACE_ROOT"
EXECUTION_CONTEXT_ENV = "CAMBIUM_EXECUTION_CONTEXT_ID"
# The host's own identity, taken from `initialize`.  Inline-delivery
# conformance is established by test against one adapter build, while a host
# updates itself underneath a passing registration.  Exporting the declared
# name and version lets delivery evidence bind the adapter it actually ran
# against, so an unregistered build degrades instead of inheriting a stale
# pass.  These are declared labels, not authentication.
HOST_CLIENT_NAME_ENV = "CAMBIUM_HOST_CLIENT_NAME"
HOST_CLIENT_VERSION_ENV = "CAMBIUM_HOST_CLIENT_VERSION"
SOURCE_HASH_ENV = "CAMBIUM_INTERFACE_SOURCE_HASH"
PROJECTION_PATH_ENV = "CAMBIUM_INTERFACE_PROJECTION"
PATH_CAPABILITIES_ENV = "CAMBIUM_PATH_CAPABILITIES"
PATH_CAPABILITIES_ACK_ENV = "CAMBIUM_PATH_CAPABILITIES_ACK_FD"

# What the projection must claim about itself before it is served.
PROJECTION_ARTIFACT = "agent-interface-projection"
PROJECTION_FORM = "mcp"
PROJECTION_SCHEMA_VERSION = 4
SOURCE_DISTRIBUTION_TARGET = "source-distribution"
CARRIED_RUNTIME_TARGET = "carried-runtime"
PATH_EXTENSION_KEY = "x-cambium-path"
WORKSPACE_EXTENSION_KEY = "x-cambium-workspace"

# The flag this layer owns. It is appended to every tool that declares it,
# and a caller-supplied value for it is reported back as ignored.
TRANSPORT_OWNED_ARGUMENT = "json"
TRANSPORT_OWNED_FLAG = "--json"

# ---------------------------------------------------------------------------
# Verdict vocabulary
# ---------------------------------------------------------------------------

# The whole of this layer's understanding of a tool's outcome. Nothing else
# in this file decides what a run meant.
VERDICTS = {
    0: "clean",
    1: "failed_or_unreliable",
    2: "hold",
}
UNREADABLE_VERDICT = "unreadable"

# A stream is echoed back for a person to read, not stored, so a runaway
# scan does not have to travel through the host intact. Parsing happens
# before truncation, so a truncated echo can never produce a parsed result.
MAX_ECHO_CHARS = 100000

# ---------------------------------------------------------------------------
# JSON-RPC codes
# ---------------------------------------------------------------------------

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Server-defined range (-32000..-32099). Two conditions live here because
# neither is a bad request and neither is an internal fault: the server is
# not bound to a corpus, or the compiled projection it must serve is not
# usable evidence.
NOT_BOUND = -32001
UNRELIABLE_EVIDENCE = -32002


class RpcError(Exception):
    """One JSON-RPC error, raised where it is discovered."""

    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# ---------------------------------------------------------------------------
# Standard-library-only helpers
# ---------------------------------------------------------------------------


def canonical_json(value):
    """Deterministic JSON text: sorted keys, no incidental whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def sha256_of(data):
    """`sha256:<hex>`, the spelling every artifact in this repository uses."""
    return "sha256:%s" % hashlib.sha256(data).hexdigest()


def log(message):
    """Diagnostics go to stderr; stdout carries JSON-RPC and nothing else."""
    sys.stderr.write("%s: %s\n" % (SERVER_NAME, message))
    sys.stderr.flush()


def clip(text):
    """Return (text, truncated?) with the echo ceiling applied."""
    if len(text) <= MAX_ECHO_CHARS:
        return text, False
    return text[:MAX_ECHO_CHARS], True


# ---------------------------------------------------------------------------
# The binding
# ---------------------------------------------------------------------------


def resolve_workspace_root(environ):
    """Return the bound corpus root, or raise the refusal that says why.

    The refusal names the variable, because a host that did not set it
    cannot act on "not configured".
    """
    raw = environ.get(WORKSPACE_ENV)
    detail = {"variable": WORKSPACE_ENV}
    if raw is None or not raw.strip():
        raise RpcError(
            NOT_BOUND,
            "%s is not set: this server governs the corpus named by that "
            "environment variable, and the host configuration must set it "
            "to an absolute path. There is no working-directory fallback."
            % WORKSPACE_ENV,
            detail)
    value = raw.strip()
    if not os.path.isabs(value):
        # `<CAMBIUM_WORKSPACE_ROOT>` lands here, which is the whole point of
        # shipping a placeholder that is not a valid path.
        raise RpcError(
            NOT_BOUND,
            "%s is %r, which is not an absolute path. An un-substituted "
            "placeholder or a relative value cannot bind a corpus."
            % (WORKSPACE_ENV, value),
            detail)
    if not os.path.isdir(value):
        raise RpcError(
            NOT_BOUND,
            "%s is %r, which is not an existing directory."
            % (WORKSPACE_ENV, value),
            detail)
    return os.path.realpath(os.path.abspath(value))


def workspace_identity(workspace_root):
    """Return the filesystem identity currently named by a root path."""
    try:
        metadata = os.stat(workspace_root)
    except OSError as exc:
        raise RpcError(
            NOT_BOUND,
            "the configured workspace cannot be identified safely: %s" %
            exc,
            {"variable": WORKSPACE_ENV, "workspace_root": workspace_root})
    if not stat.S_ISDIR(metadata.st_mode):
        raise RpcError(
            NOT_BOUND,
            "the configured workspace is no longer a directory",
            {"variable": WORKSPACE_ENV, "workspace_root": workspace_root})
    return (metadata.st_dev, metadata.st_ino)


def open_workspace_directory(workspace_root):
    """Open and verify the stable directory object used by one session."""
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required) or \
            not hasattr(os, "fchdir"):
        raise RpcError(
            NOT_BOUND,
            "this platform cannot hold a no-follow workspace directory "
            "through the subprocess execution boundary",
            {"variable": WORKSPACE_ENV, "workspace_root": workspace_root})
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = None
    try:
        descriptor = os.open(workspace_root, flags)
        metadata = os.fstat(descriptor)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise RpcError(
            NOT_BOUND,
            "the configured workspace cannot be opened safely: %s" % exc,
            {"variable": WORKSPACE_ENV, "workspace_root": workspace_root})
    identity = (metadata.st_dev, metadata.st_ino)
    if workspace_identity(workspace_root) != identity:
        os.close(descriptor)
        raise RpcError(
            NOT_BOUND,
            "the configured workspace changed while initialize was "
            "binding it; retry with a stable workspace",
            {"variable": WORKSPACE_ENV, "workspace_root": workspace_root})
    return descriptor, identity


# ---------------------------------------------------------------------------
# The projection
# ---------------------------------------------------------------------------


def resolve_projection_path(distribution_root, environ):
    """Return the only projection path this session is allowed to pin.

    An absent variable retains the source-distribution default for existing
    registrations. An explicit absolute path is accepted only together with
    the exact source hash the renderer bound. Source-distribution fixtures may
    select another such path; after parsing, a carried-runtime projection is
    additionally constrained to the runtime registry's exact path under the
    bound workspace.
    """
    distribution_path = os.path.join(
        os.path.abspath(distribution_root),
        *PROJECTION_RELATIVE.split("/"))
    raw = (environ.get(PROJECTION_PATH_ENV) or "").strip()
    if not raw:
        return distribution_path, SOURCE_DISTRIBUTION_TARGET
    if not os.path.isabs(raw):
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "%s must be an absolute path, not %r" %
            (PROJECTION_PATH_ENV, raw),
            {"variable": PROJECTION_PATH_ENV, "path": raw})
    registered_hash = (environ.get(SOURCE_HASH_ENV) or "").strip()
    if not registered_hash:
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "%s is explicit but %s is absent; an unbound path is not an "
            "interface authority" %
            (PROJECTION_PATH_ENV, SOURCE_HASH_ENV),
            {"variable": PROJECTION_PATH_ENV, "path": raw,
             "required_binding": SOURCE_HASH_ENV})
    return os.path.abspath(raw), None


def load_projection(distribution_root, environ, workspace_root=None):
    """Read, check and pin the registered interface projection.

    Only existence and agreement are checked. Nothing here recomputes a
    schema, and nothing here repairs one: an artifact that does not agree
    with itself is unreliable evidence and this server does not start on it.
    """
    workspace_root = workspace_root or resolve_workspace_root(environ)
    path, location_target = resolve_projection_path(
        distribution_root, environ)
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "the compiled tool projection could not be read at %s: %s"
            % (path, exc),
            {"path": path})
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "the compiled tool projection at %s is not parseable JSON: %s"
            % (path, exc),
            {"path": path})

    if not isinstance(document, dict):
        raise RpcError(UNRELIABLE_EVIDENCE,
                       "the compiled tool projection at %s is not an object"
                       % path, {"path": path})
    claims = (
        ("artifact", PROJECTION_ARTIFACT),
        ("form", PROJECTION_FORM),
        ("schema_version", PROJECTION_SCHEMA_VERSION),
    )
    for key, expected in claims:
        if document.get(key) != expected:
            raise RpcError(
                UNRELIABLE_EVIDENCE,
                "the compiled tool projection at %s declares %s=%r, not %r"
                % (path, key, document.get(key), expected),
                {"path": path})
    declared_target = document.get("projection_target")
    if declared_target not in (
            SOURCE_DISTRIBUTION_TARGET, CARRIED_RUNTIME_TARGET):
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "the tool projection at %s carries no valid projection_target"
            % path,
            {"path": path, "declared": declared_target})
    if declared_target == CARRIED_RUNTIME_TARGET:
        expected = os.path.join(
            workspace_root, *CARRIED_PROJECTION_RELATIVE.split("/"))
        if os.path.realpath(os.path.abspath(path)) != \
                os.path.realpath(os.path.abspath(expected)):
            raise RpcError(
                UNRELIABLE_EVIDENCE,
                "the carried-runtime tool projection must be the registered "
                "workspace artifact %s, not %s" % (expected, path),
                {"path": path, "expected": expected,
                 "projection_target": declared_target})
        if os.path.realpath(os.path.abspath(distribution_root)) != \
                os.path.realpath(os.path.abspath(workspace_root)):
            raise RpcError(
                UNRELIABLE_EVIDENCE,
                "a carried-runtime projection may execute only the Tools "
                "carried by its bound workspace; distribution root %s is not "
                "workspace root %s" % (distribution_root, workspace_root),
                {"distribution_root": distribution_root,
                 "workspace_root": workspace_root,
                 "projection_target": declared_target})
    if location_target is not None and declared_target != location_target:
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "the tool projection at %s declares projection_target=%r, but "
            "that registered location belongs to %r"
            % (path, document.get("projection_target"), location_target),
            {"path": path, "declared": declared_target,
             "location_target": location_target})

    tools = document.get("tools")
    if not isinstance(tools, list) or not tools:
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "the compiled tool projection at %s carries no tool list" % path,
            {"path": path})
    if document.get("tool_count") != len(tools):
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "the compiled tool projection at %s declares tool_count=%r for "
            "%d tools" % (path, document.get("tool_count"), len(tools)),
            {"path": path})

    actual_hash = sha256_of(raw)
    registered = (environ.get(SOURCE_HASH_ENV) or "").strip()
    if registered and registered != actual_hash:
        # The variable exists for exactly this refusal.
        raise RpcError(
            UNRELIABLE_EVIDENCE,
            "the compiled tool projection at %s hashes to %s, but this "
            "server was registered against %s (%s). Re-render the host "
            "configuration against the current projection."
            % (path, actual_hash, registered, SOURCE_HASH_ENV),
            {"path": path, "actual": actual_hash, "registered": registered})

    listed = []
    by_name = {}
    for entry in tools:
        if not isinstance(entry, dict):
            raise RpcError(UNRELIABLE_EVIDENCE,
                           "the compiled tool projection at %s carries a "
                           "non-object tool entry" % path, {"path": path})
        name = entry.get("name")
        description = entry.get("description")
        schema = entry.get("inputSchema")
        if not isinstance(name, str) or not name:
            raise RpcError(UNRELIABLE_EVIDENCE,
                           "the compiled tool projection at %s carries a "
                           "tool with no name" % path, {"path": path})
        if not isinstance(schema, dict) or \
                not isinstance(schema.get("properties"), dict):
            raise RpcError(UNRELIABLE_EVIDENCE,
                           "the compiled tool projection at %s carries no "
                           "inputSchema properties for %s" % (path, name),
                           {"path": path, "tool": name})
        if name in by_name:
            raise RpcError(UNRELIABLE_EVIDENCE,
                           "the compiled tool projection at %s lists %s "
                           "twice" % (path, name), {"path": path})
        script = os.path.join(distribution_root, "Tools", "%s.py" % name)
        if not os.path.isfile(script):
            # A tool list this server could not run is not a tool list.
            raise RpcError(
                UNRELIABLE_EVIDENCE,
                "the compiled tool projection at %s lists %s, but %s is not "
                "present" % (path, name, script),
                {"path": path, "tool": name})
        workspace = entry.get(WORKSPACE_EXTENSION_KEY)
        if not isinstance(workspace, dict) or \
                set(workspace) != {"argument", "access"} or \
                workspace.get("access") not in ("read", "write"):
            raise RpcError(
                UNRELIABLE_EVIDENCE,
                "the compiled tool projection at %s carries no valid "
                "workspace binding for %s" % (path, name),
                {"path": path, "tool": name})
        workspace_argument = workspace.get("argument")
        if not isinstance(workspace_argument, str) or \
                workspace_argument not in schema["properties"]:
            raise RpcError(
                UNRELIABLE_EVIDENCE,
                "the compiled tool projection at %s binds %s to unknown "
                "workspace argument %r" %
                (path, name, workspace_argument),
                {"path": path, "tool": name})
        for argument, property_schema in schema["properties"].items():
            path_capability = property_schema.get(PATH_EXTENSION_KEY)
            if path_capability is None:
                continue
            if not isinstance(path_capability, dict) or \
                    set(path_capability) != {
                        "access", "consumption", "constraint", "value",
                        "suffixes", "active_when_any", "inactive_when_any",
                    } or \
                    path_capability.get("access") not in \
                    ("read", "write", "read-write") or \
                    path_capability.get("consumption") not in \
                    ("snapshot", "append", "replace", "transaction") or \
                    path_capability.get("constraint") not in \
                    ("contained", "exact", "namespace"):
                raise RpcError(
                    UNRELIABLE_EVIDENCE,
                    "the compiled tool projection at %s carries an invalid "
                    "path capability for %s.%s" % (path, name, argument),
                    {"path": path, "tool": name, "argument": argument})
            constraint = path_capability["constraint"]
            consumption = path_capability["consumption"]
            access = path_capability["access"]
            compatible = {
                "read": {"snapshot"},
                "write": {"append", "replace"},
                "read-write": {"transaction"},
            }
            if consumption not in compatible[access]:
                raise RpcError(
                    UNRELIABLE_EVIDENCE,
                    "the compiled tool projection at %s carries an "
                    "incompatible consumption mode for %s.%s" %
                    (path, name, argument),
                    {"path": path, "tool": name, "argument": argument})
            value = path_capability["value"]
            suffixes = path_capability["suffixes"]
            active_when_any = path_capability["active_when_any"]
            inactive_when_any = path_capability["inactive_when_any"]
            for label, conditions in (
                    ("active_when_any", active_when_any),
                    ("inactive_when_any", inactive_when_any)):
                if (not isinstance(conditions, list) or
                        len(conditions) != len(set(conditions)) or
                        any(not isinstance(condition, str) or
                            condition not in schema["properties"] or
                            schema["properties"][condition].get("type") !=
                            "boolean" or
                            cli_metadata(
                                schema["properties"][condition]).get(
                                    "action") != "store_true"
                            for condition in conditions)):
                    raise RpcError(
                        UNRELIABLE_EVIDENCE,
                        "the compiled tool projection at %s carries invalid "
                        "%s conditions for %s.%s" %
                        (path, label, name, argument),
                        {"path": path, "tool": name,
                         "argument": argument})
            if set(active_when_any) & set(inactive_when_any):
                raise RpcError(
                    UNRELIABLE_EVIDENCE,
                    "the compiled tool projection at %s activates and "
                    "deactivates %s.%s on the same condition" %
                    (path, name, argument),
                    {"path": path, "tool": name, "argument": argument})
            if not isinstance(suffixes, list) or any(
                    not isinstance(suffix, str) or not suffix or
                    not suffix.startswith(".") or "/" in suffix or
                    "\\" in suffix for suffix in suffixes):
                raise RpcError(
                    UNRELIABLE_EVIDENCE,
                    "the compiled tool projection at %s carries invalid "
                    "suffix constraints for %s.%s" %
                    (path, name, argument),
                    {"path": path, "tool": name, "argument": argument})
            if constraint == "contained":
                valid_constraint = value is None and not suffixes
            else:
                valid_constraint = isinstance(value, str) and value and \
                    not os.path.isabs(value) and "\\" not in value and \
                    os.path.normpath(value).replace(os.sep, "/") == value and \
                    value != ".." and not value.startswith("../")
                if constraint == "exact" and suffixes:
                    valid_constraint = False
            if not valid_constraint:
                raise RpcError(
                    UNRELIABLE_EVIDENCE,
                    "the compiled tool projection at %s carries an invalid "
                    "%s constraint for %s.%s" %
                    (path, constraint, name, argument),
                    {"path": path, "tool": name, "argument": argument})
        by_name[name] = {
            "name": name,
            "schema": schema,
            "script": script,
            "workspace_argument": workspace_argument,
        }
        # Pass the compiled entry through as-is. Rebuilding it from a
        # whitelist would silently drop any field the projection carries
        # that this server does not itself read -- the mutual-exclusion
        # groups, for one -- and the claim made here and in Tools/README.md
        # is that the tool list is projected verbatim. Validation above
        # decides whether the entry is admissible; it does not decide what
        # the entry contains.
        listed.append(dict(entry))

    return {
        "path": path,
        "source_hash": actual_hash,
        "listed": listed,
        "by_name": by_name,
    }


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------


def cli_metadata(property_schema):
    """The `x-cambium-cli` block the projection carries verbatim."""
    meta = property_schema.get("x-cambium-cli")
    return meta if isinstance(meta, dict) else {}


def option_flag(option_strings):
    """The spelling to write on argv: the long form when there is one."""
    for candidate in option_strings:
        if candidate.startswith("--"):
            return candidate
    return option_strings[0]


def positional_order(schema):
    """Positional dests in the order argparse declared them.

    `properties` is serialized with sorted keys, so declaration order is not
    recoverable from it. The `required` array is not sorted -- it preserves
    the order argparse reported -- so required positionals take their order
    from there, and a positional argparse did not mark required (there is
    one today, `duplicate_check`'s optional `vault`) follows in key order.
    """
    properties = schema["properties"]
    positionals = [
        key for key in sorted(properties)
        if not cli_metadata(properties[key]).get("option_strings")
    ]
    required = [
        key for key in schema.get("required", [])
        if key in positionals
    ]
    return required + [key for key in positionals if key not in required]


def render_value(name, declared_type, value):
    """One JSON value as the argv token(s) it becomes, or a refusal.

    A refusal here means no argv exists for this call, which is the only
    kind of rejection this layer is entitled to make.
    """
    if declared_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise RpcError(INVALID_PARAMS,
                           "%s is declared integer; %r cannot be rendered "
                           "onto argv" % (name, value))
        return str(value)
    if declared_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RpcError(INVALID_PARAMS,
                           "%s is declared number; %r cannot be rendered "
                           "onto argv" % (name, value))
        return str(value)
    # An undeclared type projects as string, which is what argv carries.
    if not isinstance(value, str):
        raise RpcError(INVALID_PARAMS,
                       "%s is declared string; %r cannot be rendered onto "
                       "argv" % (name, value))
    return value


def build_argv(tool, arguments):
    """Return (argv tail, ignored transport-owned argument names).

    The tail is positionals in declaration order, then options in a stable
    key order, then `--json` when the tool declares it.
    """
    schema = tool["schema"]
    properties = schema["properties"]

    undeclared = [key for key in sorted(arguments) if key not in properties]
    if undeclared:
        raise RpcError(
            INVALID_PARAMS,
            "%s does not declare %s"
            % (tool["name"], ", ".join(undeclared)),
            {"tool": tool["name"], "undeclared": undeclared})

    ignored = []
    order = positional_order(schema)
    positional_tokens = []
    missing_before_supplied = None
    for key in order:
        if key not in arguments:
            if missing_before_supplied is None:
                missing_before_supplied = key
            continue
        if missing_before_supplied is not None:
            # Emitting this value now would bind it to the parameter that
            # was skipped. There is no argv that means what was asked for.
            raise RpcError(
                INVALID_PARAMS,
                "%s takes %s before %s; %s was supplied without it, and no "
                "argv can carry that"
                % (tool["name"], missing_before_supplied, key, key),
                {"tool": tool["name"],
                 "missing": missing_before_supplied,
                 "supplied": key})
        positional_tokens.append(
            render_value(key, properties[key].get("type"), arguments[key]))

    option_tokens = []
    for key in sorted(arguments):
        meta = cli_metadata(properties[key])
        option_strings = meta.get("option_strings") or []
        if not option_strings:
            continue  # already placed as a positional
        if key == TRANSPORT_OWNED_ARGUMENT:
            ignored.append(key)
            continue
        flag = option_flag(option_strings)
        value = arguments[key]
        declared_type = properties[key].get("type")
        if meta.get("action") == "store_true" or declared_type == "boolean":
            if not isinstance(value, bool):
                raise RpcError(INVALID_PARAMS,
                               "%s is a flag; %r cannot be rendered onto "
                               "argv" % (key, value))
            if value:
                option_tokens.append(flag)
            continue
        if meta.get("action") == "append" or declared_type == "array":
            if not isinstance(value, list):
                raise RpcError(INVALID_PARAMS,
                               "%s is a repeatable option; %r cannot be "
                               "rendered onto argv" % (key, value))
            item_type = (properties[key].get("items") or {}).get("type")
            for item in value:
                option_tokens.append(flag)
                option_tokens.append(render_value(key, item_type, item))
            continue
        option_tokens.append(flag)
        option_tokens.append(render_value(key, declared_type, value))

    tail = positional_tokens + option_tokens
    if TRANSPORT_OWNED_ARGUMENT in properties:
        tail.append(TRANSPORT_OWNED_FLAG)
    return tail, ignored


def _path_values(tool_name, argument, value):
    """Yield path strings from one scalar or list-valued path argument."""
    values = value if isinstance(value, list) else [value]
    for item in values:
        if not isinstance(item, str) or not item or item != item.strip() or \
                "\x00" in item:
            raise RpcError(
                INVALID_PARAMS,
                "%s.%s must carry non-empty canonical path strings" %
                (tool_name, argument),
                {"tool": tool_name, "argument": argument})
        yield item


def _bound_path(workspace_root, spelling):
    candidate = spelling if os.path.isabs(spelling) else \
        os.path.join(workspace_root, spelling)
    return os.path.realpath(os.path.abspath(candidate))


def _canonical_workspace_spelling(tool_name, argument, spelling):
    """Require one stable repository-relative spelling at the MCP boundary."""
    if os.path.isabs(spelling) or "\\" in spelling or \
            os.path.normpath(spelling).replace(os.sep, "/") != spelling or \
            spelling == ".." or spelling.startswith("../"):
        raise RpcError(
            INVALID_PARAMS,
            "%s.%s must use a canonical repository-relative path" %
            (tool_name, argument),
            {"tool": tool_name, "argument": argument})
    return spelling


def _path_capability_is_active(capability, arguments):
    """Evaluate one compiled, closed operation-mode predicate."""
    active_when_any = capability.get("active_when_any") or []
    inactive_when_any = capability.get("inactive_when_any") or []
    positive = (not active_when_any or
                any(arguments.get(name) is True
                    for name in active_when_any))
    excluded = any(arguments.get(name) is True
                   for name in inactive_when_any)
    return positive and not excluded


def _retain_path_capability(tool_name, argument, workspace_fd, spelling,
                            capability, value_index):
    """Retain the admitted target and parent objects for one typed path.

    Validation that closes a descriptor has only moved a pathname race.  This
    walk returns the exact descriptors a cooperating tool must consume: the
    existing target object for a snapshot, and the stable parent object for a
    create, append, replacement, or transaction.  The original spelling is
    retained only as display/lookup identity; it grants no filesystem reach.
    """
    if spelling == ".":
        components = []
    else:
        components = spelling.split("/")
    current_fd = os.dup(workspace_fd)
    retained = []
    try:
        if not components:
            target_fd = os.dup(current_fd)
            retained.append(target_fd)
            descriptor = os.fstat(target_fd)
            return ({
                "capability_id": "%s[%d]" % (argument, value_index),
                "argument": argument,
                "value_index": value_index,
                "spelling": spelling,
                "access": capability["access"],
                "consumption": capability["consumption"],
                "constraint": capability["constraint"],
                "exists": True,
                "kind": "directory",
                "target_fd": target_fd,
                "parent_fd": None,
                "basename": ".",
                "missing_components": [],
                "target_dev": descriptor.st_dev,
                "target_ino": descriptor.st_ino,
            }, retained)
        for index, component in enumerate(components):
            try:
                metadata = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                # A may-create path is anchored by the deepest existing
                # parent opened from the frozen workspace directory.
                parent_fd = os.dup(current_fd)
                retained.append(parent_fd)
                parent = os.fstat(parent_fd)
                return ({
                    "capability_id": "%s[%d]" % (argument, value_index),
                    "argument": argument,
                    "value_index": value_index,
                    "spelling": spelling,
                    "access": capability["access"],
                    "consumption": capability["consumption"],
                    "constraint": capability["constraint"],
                    "exists": False,
                    "kind": "missing",
                    "target_fd": None,
                    "parent_fd": parent_fd,
                    "basename": components[-1],
                    "missing_components": components[index:],
                    "target_dev": None,
                    "target_ino": None,
                    "parent_dev": parent.st_dev,
                    "parent_ino": parent.st_ino,
                }, retained)
            except OSError as exc:
                raise RpcError(
                    INVALID_PARAMS,
                    "%s.%s cannot be inspected safely: %s" %
                    (tool_name, argument, exc),
                    {"tool": tool_name, "argument": argument})
            if stat.S_ISLNK(metadata.st_mode):
                raise RpcError(
                    INVALID_PARAMS,
                    "%s.%s traverses a symlink, which is not a canonical "
                    "workspace artifact" % (tool_name, argument),
                    {"tool": tool_name, "argument": argument})
            if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
                raise RpcError(
                    INVALID_PARAMS,
                    "%s.%s names a multiply-linked file, so its repository "
                    "identity is ambiguous" % (tool_name, argument),
                    {"tool": tool_name, "argument": argument})
            if index == len(components) - 1:
                if stat.S_ISDIR(metadata.st_mode):
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                elif stat.S_ISREG(metadata.st_mode):
                    if capability["consumption"] == "append":
                        flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW
                    else:
                        flags = os.O_RDONLY | os.O_NOFOLLOW
                else:
                    raise RpcError(
                        INVALID_PARAMS,
                        "%s.%s must name a regular file or directory" %
                        (tool_name, argument),
                        {"tool": tool_name, "argument": argument})
                if hasattr(os, "O_CLOEXEC"):
                    flags |= os.O_CLOEXEC
                try:
                    target_fd = os.open(
                        component, flags, dir_fd=current_fd)
                except OSError as exc:
                    raise RpcError(
                        INVALID_PARAMS,
                        "%s.%s changed while its target was being retained: "
                        "%s" % (tool_name, argument, exc),
                        {"tool": tool_name, "argument": argument})
                opened = os.fstat(target_fd)
                if ((metadata.st_dev, metadata.st_ino) !=
                        (opened.st_dev, opened.st_ino)):
                    os.close(target_fd)
                    raise RpcError(
                        INVALID_PARAMS,
                        "%s.%s changed while its target was being retained" %
                        (tool_name, argument),
                        {"tool": tool_name, "argument": argument})
                target_kind = ("directory" if stat.S_ISDIR(opened.st_mode)
                               else "file")
                parent_fd = os.dup(current_fd)
                retained.extend((target_fd, parent_fd))
                parent = os.fstat(parent_fd)
                return ({
                    "capability_id": "%s[%d]" % (argument, value_index),
                    "argument": argument,
                    "value_index": value_index,
                    "spelling": spelling,
                    "access": capability["access"],
                    "consumption": capability["consumption"],
                    "constraint": capability["constraint"],
                    "exists": True,
                    "kind": target_kind,
                    "target_fd": target_fd,
                    "parent_fd": parent_fd,
                    "basename": component,
                    "missing_components": [],
                    "target_dev": opened.st_dev,
                    "target_ino": opened.st_ino,
                    "parent_dev": parent.st_dev,
                    "parent_ino": parent.st_ino,
                }, retained)
            if not stat.S_ISDIR(metadata.st_mode):
                raise RpcError(
                    INVALID_PARAMS,
                    "%s.%s has a non-directory parent component" %
                    (tool_name, argument),
                    {"tool": tool_name, "argument": argument})
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except OSError as exc:
                raise RpcError(
                    INVALID_PARAMS,
                    "%s.%s changed while its path was being inspected: %s" %
                    (tool_name, argument, exc),
                    {"tool": tool_name, "argument": argument})
            os.close(current_fd)
            current_fd = next_fd
        raise RpcError(
            INTERNAL_ERROR,
            "%s.%s capability retention reached no terminal state" %
            (tool_name, argument),
            {"tool": tool_name, "argument": argument})
    except Exception:
        for descriptor in retained:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    finally:
        os.close(current_fd)


def enforce_workspace_capabilities(tool, arguments, workspace_root,
                                   workspace_fd):
    """Validate and retain every effective typed path capability."""
    root_real = os.path.realpath(os.path.abspath(workspace_root))
    workspace_argument = tool["workspace_argument"]
    if workspace_argument not in arguments:
        raise RpcError(
            INVALID_PARAMS,
            "%s requires %s over MCP so the operation is bound to this "
            "session's workspace" % (tool["name"], workspace_argument),
            {"tool": tool["name"], "required_workspace_argument":
             workspace_argument})
    workspace_values = list(_path_values(
        tool["name"], workspace_argument, arguments[workspace_argument]))
    if len(workspace_values) != 1 or \
            _bound_path(root_real, workspace_values[0]) != root_real:
        raise RpcError(
            INVALID_PARAMS,
            "%s.%s must resolve exactly to the session workspace %s" %
            (tool["name"], workspace_argument, workspace_root),
            {"tool": tool["name"], "argument": workspace_argument,
             "workspace_root": workspace_root})

    properties = tool["schema"]["properties"]
    records = []
    descriptors = []
    semantic_slots = {}
    try:
        for argument, property_schema in properties.items():
            if argument == workspace_argument:
                continue
            capability = property_schema.get(PATH_EXTENSION_KEY)
            if capability is None:
                continue
            if not _path_capability_is_active(capability, arguments):
                continue
            if argument in arguments:
                value = arguments[argument]
            elif "default" in property_schema and \
                    property_schema["default"] is not None:
                # An omitted option still has an effective path. Validate and
                # retain the compiled default before the child can use it.
                value = property_schema["default"]
            else:
                continue
            for value_index, spelling in enumerate(
                    _path_values(tool["name"], argument, value)):
                spelling = _canonical_workspace_spelling(
                    tool["name"], argument, spelling)
                semantic_slot = (spelling, capability["consumption"])
                prior = semantic_slots.get(semantic_slot)
                if prior is not None:
                    raise RpcError(
                        INVALID_PARAMS,
                        "%s.%s aliases active path capability %s at %s "
                        "with the same consumption mode" %
                        (tool["name"], argument, prior, spelling),
                        {"tool": tool["name"], "argument": argument,
                         "aliased_argument": prior, "path": spelling,
                         "consumption": capability["consumption"]})
                semantic_slots[semantic_slot] = argument
                constraint = capability["constraint"]
                registered = capability["value"]
                if constraint == "exact":
                    if spelling != registered:
                        raise RpcError(
                            INVALID_PARAMS,
                            "%s.%s must name exactly %s" %
                            (tool["name"], argument, registered),
                            {"tool": tool["name"], "argument": argument,
                             "expected": registered})
                elif constraint == "namespace":
                    in_namespace = spelling.startswith(registered + "/")
                    if not in_namespace:
                        raise RpcError(
                            INVALID_PARAMS,
                            "%s.%s must name an artifact under %s" %
                            (tool["name"], argument, registered),
                            {"tool": tool["name"], "argument": argument,
                             "namespace": registered})
                    suffixes = capability["suffixes"]
                    if suffixes and not any(
                            spelling.endswith(suffix) for suffix in suffixes):
                        raise RpcError(
                            INVALID_PARAMS,
                            "%s.%s must end in one of %s" %
                            (tool["name"], argument, ", ".join(suffixes)),
                            {"tool": tool["name"], "argument": argument,
                             "suffixes": suffixes})
                record, opened = _retain_path_capability(
                    tool["name"], argument, workspace_fd, spelling,
                    capability, value_index)
                records.append(record)
                descriptors.extend(opened)
    except Exception:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    return records, descriptors


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def interpreter():
    """The interpreter running this server, so the child matches the host."""
    return sys.executable or "python3"


def run_tool(tool, arguments, workspace_root, workspace_fd, environ):
    """Run one tool as a child process and report exactly what came back."""
    capability_records, capability_fds = enforce_workspace_capabilities(
        tool, arguments, workspace_root, workspace_fd)
    execution_arguments = dict(arguments)
    # The caller must name the right binding, but the child consumes `.` from
    # the already-open directory object. It can therefore never reopen a
    # replaced pathname between authorization and subprocess startup.
    execution_arguments[tool["workspace_argument"]] = "."
    # Effective typed defaults were admitted and retained above. Materialize
    # them onto argv so argparse cannot reconstruct an absolute default from
    # the distribution checkout and bypass the workspace capability object.
    for argument, property_schema in tool["schema"]["properties"].items():
        if argument in execution_arguments or \
                property_schema.get(PATH_EXTENSION_KEY) is None:
            continue
        capability = property_schema[PATH_EXTENSION_KEY]
        if not _path_capability_is_active(
                capability, execution_arguments):
            continue
        if property_schema.get("default") is not None:
            execution_arguments[argument] = property_schema["default"]
    tail, ignored = build_argv(tool, execution_arguments)
    argv = [interpreter(), tool["script"]] + tail

    child_env = dict(environ)
    child_env["PYTHONPYCACHEPREFIX"] = _CAMBIUM_PYCACHE_PREFIX
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    child_env[WORKSPACE_ENV] = workspace_root
    ack_read_fd, ack_write_fd = os.pipe()
    child_env[PATH_CAPABILITIES_ACK_ENV] = str(ack_write_fd)
    child_env[PATH_CAPABILITIES_ENV] = canonical_json({
        "schema_version": 1,
        "tool": tool["name"],
        "workspace_dev": os.fstat(workspace_fd).st_dev,
        "workspace_ino": os.fstat(workspace_fd).st_ino,
        "capabilities": capability_records,
    })

    try:
        try:
            completed = subprocess.run(
                argv,
                env=child_env,
                # The server's own stdin is the JSON-RPC stream. A child that
                # inherited it could consume the protocol.
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=tuple(
                    [workspace_fd, ack_write_fd] + capability_fds),
                preexec_fn=lambda: os.fchdir(workspace_fd),
            )
        finally:
            os.close(ack_write_fd)
            for descriptor in capability_fds:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        acknowledged_raw = b""
        while True:
            chunk = os.read(ack_read_fd, 65536)
            if not chunk:
                break
            acknowledged_raw += chunk
        acknowledged = set(
            line for line in acknowledged_raw.decode(
                "utf-8", errors="replace").splitlines() if line)
        # Every active typed path must reach a descriptor-backed consumer.
        # A mode that does not consume an otherwise effective path must declare
        # its activation predicate in the compiled interface; silently
        # treating all write paths as optional would let an unmigrated writer
        # reopen argv names and still return a clean result with no
        # acknowledgement.
        required_consumption = {
            row["capability_id"] for row in capability_records
        }
        missing_consumption = sorted(required_consumption - acknowledged)
    except OSError as exc:
        raise RpcError(
            INTERNAL_ERROR,
            "%s could not be started: %s" % (tool["name"], exc),
            {"tool": tool["name"], "argv": argv})
    finally:
        try:
            os.close(ack_read_fd)
        except OSError:
            pass

    if completed.returncode in (0, 2) and missing_consumption:
        raise RpcError(
            INTERNAL_ERROR,
            "%s completed without consuming retained path capability(s): %s"
            % (tool["name"], ", ".join(missing_consumption)),
            {"tool": tool["name"],
             "missing_path_capabilities": missing_consumption})

    report_text = completed.stderr.decode("utf-8", errors="replace")
    report, report_truncated = clip(report_text)

    # A tool that declares `--json` puts its receipts on stdout and its
    # report on stderr. A tool that does not declare it -- several emit no
    # receipts at all -- puts its report on stdout, so stdout is never
    # discarded: it is either parsed as receipts or carried as text.
    declares_json = TRANSPORT_OWNED_ARGUMENT in tool["schema"]["properties"]
    payload = None
    parse_state = "not_requested"
    parse_error = None
    stdout_echo = None
    stdout_truncated = False
    decoded = completed.stdout.decode("utf-8", errors="replace")
    if not declares_json:
        if decoded.strip():
            stdout_echo, stdout_truncated = clip(decoded)
    else:
        try:
            stdout_text = completed.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            parse_state = "unparseable"
            parse_error = "stdout is not UTF-8: %s" % exc
            stdout_echo, stdout_truncated = clip(decoded)
        else:
            if not stdout_text.strip():
                parse_state = "empty"
            else:
                try:
                    payload = json.loads(stdout_text)
                except ValueError as exc:
                    parse_state = "unparseable"
                    parse_error = "stdout is not JSON: %s" % exc
                    stdout_echo, stdout_truncated = clip(stdout_text)
                else:
                    parse_state = "parsed"

    code = completed.returncode
    verdict = VERDICTS.get(code, UNREADABLE_VERDICT)

    envelope = {
        "tool": tool["name"],
        "argv": argv,
        "workspace_root": workspace_root,
        "exit_code": code,
        "verdict": verdict,
        "verdict_source": "process exit code",
        "stdout_parse": parse_state,
        "report": report,
        "report_truncated": report_truncated,
        "transport": "%s-mcp-server/%s" % (SERVER_NAME, SERVER_VERSION),
        "path_capability_assurance": "descriptor-retained",
        "consumed_path_capabilities": sorted(acknowledged),
    }
    if parse_state == "parsed":
        envelope["stdout_json"] = payload
    if parse_state == "unparseable":
        envelope["stdout_parse_error"] = parse_error
    if stdout_echo is not None:
        envelope["stdout_text"] = stdout_echo
        envelope["stdout_truncated"] = stdout_truncated
    if ignored:
        envelope["transport_owned_arguments_ignored"] = ignored

    lines = ["%s/%s: exit_code=%d verdict=%s"
             % (SERVER_NAME, tool["name"], code, verdict)]
    if verdict == UNREADABLE_VERDICT:
        lines.append(
            "exit code %d has no defined meaning in this distribution; it "
            "has not been read as a verdict." % code)
    if parse_state == "unparseable":
        lines.append(
            "the --json stdout of this run could not be parsed: %s. It is "
            "carried verbatim under stdout_text and nothing has been "
            "inferred from it." % parse_error)
    if ignored:
        lines.append(
            "argument(s) %s are owned by this transport and were ignored; "
            "%s is always requested." % (", ".join(ignored),
                                         TRANSPORT_OWNED_FLAG))
    if stdout_echo:
        lines.append(stdout_echo)
    if report:
        lines.append(report)

    return {
        "content": [
            {"type": "text", "text": "\n".join(lines)},
            {"type": "text", "text": canonical_json(envelope)},
        ],
        "structuredContent": envelope,
        # Not the verdict channel. See the module docstring: a non-zero exit
        # is flagged so no host renders a held or failed run as a clean one,
        # and the verdict itself is `verdict`/`exit_code` above.
        "isError": code != 0,
    }


# ---------------------------------------------------------------------------
# Method handlers
# ---------------------------------------------------------------------------


class Server(object):
    """One stdio session. Holds the binding and the pinned projection."""

    def __init__(self, distribution_root=None, environ=None):
        self.distribution_root = distribution_root or DISTRIBUTION_ROOT
        self.environ = dict(os.environ if environ is None else environ)
        self.workspace_root = None
        self.workspace_identity = None
        self.workspace_fd = None
        self.projection = None
        self.execution_context_id = None
        self.client_name = None
        self.client_version = None

    # -- lifecycle --------------------------------------------------------

    def handle_initialize(self, params):
        # Both preconditions are settled here, so a session never comes up
        # advertising an interface it cannot serve.
        candidate_root = resolve_workspace_root(self.environ)
        candidate_fd, candidate_identity = \
            open_workspace_directory(candidate_root)
        try:
            candidate_projection = load_projection(
                self.distribution_root, self.environ, candidate_root)
        except Exception:
            os.close(candidate_fd)
            raise
        self.close()
        self.workspace_root = candidate_root
        self.workspace_fd = candidate_fd
        self.workspace_identity = candidate_identity
        self.projection = candidate_projection
        self.execution_context_id = "mcp:%s" % uuid.uuid4().hex
        client = params.get("clientInfo")
        if isinstance(client, dict):
            name = client.get("name")
            version = client.get("version")
            self.client_name = name if isinstance(name, str) and name else None
            self.client_version = (version if isinstance(version, str) and
                                   version else None)
        requested = params.get("protocolVersion")
        agreed = (requested if requested in SUPPORTED_PROTOCOL_VERSIONS
                  else LATEST_PROTOCOL_VERSION)
        return {
            "protocolVersion": agreed,
            # No `listChanged`: this server never emits
            # notifications/tools/list_changed, and claiming it would be a
            # promise nothing here keeps.
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": SERVER_NAME,
                "title": SERVER_TITLE,
                "version": SERVER_VERSION,
            },
            "instructions": (
                "Cambium governance tools, run as subprocesses. Read the "
                "verdict from structuredContent: exit_code 0 is a clean "
                "success, 1 is a failure or evidence the tool judged "
                "unreliable, and 2 is a HOLD -- no failure, but something a "
                "person must read before the work continues. A HOLD is "
                "neither a success nor a failure; do not treat it as "
                "either. isError is set for any non-zero exit and is not "
                "the verdict."
            ),
        }

    def require_session(self):
        if self.projection is None or self.workspace_root is None or \
                self.workspace_identity is None or self.workspace_fd is None:
            raise RpcError(
                INVALID_REQUEST,
                "initialize has not completed on this session; the tool "
                "list and the corpus binding are established there.")

    # -- tools ------------------------------------------------------------

    def handle_tools_list(self, _params):
        self.require_session()
        # Straight out of the artifact. Nothing is computed here.
        return {"tools": self.projection["listed"]}

    def handle_tools_call(self, params):
        self.require_session()
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise RpcError(INVALID_PARAMS, "tools/call requires a tool name")
        tool = self.projection["by_name"].get(name)
        if tool is None:
            raise RpcError(INVALID_PARAMS, "no such tool: %s" % name,
                           {"tool": name})
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise RpcError(INVALID_PARAMS,
                           "tools/call arguments must be an object")
        # Re-read and compare the binding. A pathname can be renamed,
        # replaced or have a symlink retargeted after initialize; the session
        # remains authorized only for the canonical directory object it
        # originally pinned.
        current_root = resolve_workspace_root(self.environ)
        current_identity = workspace_identity(current_root)
        if current_root != self.workspace_root or \
                current_identity != self.workspace_identity:
            raise RpcError(
                NOT_BOUND,
                "the configured workspace changed after initialize; start "
                "a new MCP session for the new workspace",
                {"variable": WORKSPACE_ENV,
                 "workspace_root": self.workspace_root,
                 "current_workspace_root": current_root})
        workspace_root = self.workspace_root
        execution_env = dict(self.environ)
        execution_env[EXECUTION_CONTEXT_ENV] = self.execution_context_id
        # Absent rather than empty: an unset variable claims nothing, while an
        # empty one would satisfy a consumer that only tests presence.
        for name, value in ((HOST_CLIENT_NAME_ENV, self.client_name),
                            (HOST_CLIENT_VERSION_ENV, self.client_version)):
            if value:
                execution_env[name] = value
            else:
                execution_env.pop(name, None)
        return run_tool(
            tool, arguments, workspace_root, self.workspace_fd, execution_env)

    def close(self):
        """Release the session's stable workspace directory object."""
        descriptor = self.workspace_fd
        self.workspace_fd = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def __del__(self):
        self.close()

    def handle_ping(self, _params):
        return {}

    # -- dispatch ---------------------------------------------------------

    REQUESTS = {
        "initialize": handle_initialize,
        "tools/list": handle_tools_list,
        "tools/call": handle_tools_call,
        "ping": handle_ping,
    }

    # Notifications this server recognizes and deliberately answers with
    # nothing, because JSON-RPC 2.0 permits no response to a notification.
    NOTIFICATIONS = ("notifications/initialized",)

    def dispatch(self, method, params):
        handler = self.REQUESTS.get(method)
        if handler is None:
            raise RpcError(METHOD_NOT_FOUND, "method not found: %s" % method,
                           {"method": method})
        return handler(self, params)


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------


def error_response(message_id, code, message, data=None):
    body = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": message_id, "error": body}


def handle_message(server, message):
    """Return one response object, or None when nothing may be sent back."""
    if not isinstance(message, dict):
        # A JSON-RPC 2.0 batch is an array, and MCP removed batching; either
        # way this is not a message this server can answer.
        return error_response(None, INVALID_REQUEST,
                              "a JSON-RPC message must be an object")
    has_id = "id" in message
    message_id = message.get("id")
    method = message.get("method")
    if message.get("jsonrpc") != "2.0":
        if not has_id:
            return None
        return error_response(message_id, INVALID_REQUEST,
                              "jsonrpc must be \"2.0\"")
    if not isinstance(method, str) or not method:
        if not has_id:
            return None
        return error_response(message_id, INVALID_REQUEST,
                              "a request must name a method")
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        if not has_id:
            return None
        return error_response(message_id, INVALID_PARAMS,
                              "params must be an object")

    if not has_id:
        # A notification. JSON-RPC 2.0 forbids a response to one, so an
        # unrecognized method is reported on stderr rather than answered.
        if method not in server.NOTIFICATIONS:
            log("ignored notification: %s" % method)
        return None

    try:
        return {"jsonrpc": "2.0", "id": message_id,
                "result": server.dispatch(method, params)}
    except RpcError as exc:
        return error_response(message_id, exc.code, exc.message, exc.data)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        log("unhandled error in %s: %s"
            % (method, traceback.format_exc().strip()))
        return error_response(message_id, INTERNAL_ERROR,
                              "%s: %s" % (type(exc).__name__, exc))


def serve(stdin=None, stdout=None, server=None):
    """Read one JSON-RPC message per line and answer on stdout."""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    server = Server() if server is None else server

    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError as exc:
            response = error_response(None, PARSE_ERROR,
                                      "invalid JSON: %s" % exc)
        else:
            response = handle_message(server, message)
        if response is None:
            continue
        stdout.write(canonical_json(response) + "\n")
        stdout.flush()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # There is no command-line surface to get wrong. Saying so is
        # better than accepting arguments that do nothing.
        log("takes no command-line arguments; it is a stdio MCP server "
            "started by a host. Received: %s" % " ".join(sys.argv[1:]))
        sys.exit(1)
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n")
    sys.exit(serve())
