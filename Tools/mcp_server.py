#!/usr/bin/env python3
"""mcp_server.py -- the stdio entry point the host configurations name.

`Tools/compiled/mcp-tools.json` states what the server offers and
`Tools/compiled/host-configs/` states where the server is and which corpus
it governs.  Neither of them is a server: a host holding those files still
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

It also imports nothing from this distribution -- not a check, not an
applier, not even `kblib`.  Every import below is from the standard
library.  This is the executable form of "layer 3 only carries": a module
that cannot reach a judgment module cannot make a judgment, and
`Tools/tests/test_mcp_server.py` asserts the import set statically so the
property survives future edits.  The cost is a hand-rolled sha256 and a
hand-rolled canonical `json.dumps`; both are three lines, and both are
cheaper than a seam that can be crossed by accident.

Protocol
--------
JSON-RPC 2.0, one message per line, over stdin/stdout.

The MCP specification's current revision is `2026-07-28`, and that revision
has no `initialize` at all: it is stateless, carries version and
capabilities as per-request `_meta`, and requires `server/discover`.  The
`initialize` handshake belongs to what that revision calls the *legacy*
era, whose latest revision is `2025-11-25`.  This server implements the
legacy era at `2025-11-25`, which is what every host configuration under
`Tools/compiled/host-configs/` is written for today.

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
`Tools/compiled/mcp-tools.json`.  This module does not read
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
It refuses only calls for which no argv can be formed at all: an undeclared
argument name, a JSON value whose type cannot be rendered onto argv, and a
missing positional that would silently rebind a later positional's value
onto an earlier parameter.  It does not check `enum` membership, does not
check that required arguments are present, and does not check any path.
Every one of those is a judgment the tool itself already makes, and letting
the tool make it is how "the kernel's refusal arrives as the kernel's
refusal" stays true instead of being asserted.

The binding
-----------
`CAMBIUM_WORKSPACE_ROOT` names the corpus this session governs, and it is
read from the environment only.  There is no fall back to the working
directory: cwd inheritance is undocumented best-effort in all four hosts --
`render_host_configs.py` says so at length -- and an undocumented
best-effort is not something a binding may rest on.  An unset, relative, or
un-substituted value fails `initialize` with a message naming the variable
the host has to set.

The bound root becomes the child process's working directory, so a
repository-relative argument such as `.` resolves against the corpus.
Arguments are never rewritten to point at it: choosing a caller's paths for
them would be this layer deciding what may run, and each tool already owns
that question through its own containment checks.
"""

import hashlib
import json
import os
import subprocess
import sys
import uuid
import traceback

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

# The same name the five host configuration products register, spelled the
# same way. `render_host_configs.SERVER_NAME` is the declaration; this is
# the server answering to it.
SERVER_NAME = "cambium"
SERVER_VERSION = "1.0.0"
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

# What the projection must claim about itself before it is served.
PROJECTION_ARTIFACT = "agent-interface-projection"
PROJECTION_FORM = "mcp"
PROJECTION_SCHEMA_VERSION = 1

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
    return value


# ---------------------------------------------------------------------------
# The projection
# ---------------------------------------------------------------------------


def load_projection(distribution_root, environ):
    """Read, check and pin `compiled/mcp-tools.json`.

    Only existence and agreement are checked. Nothing here recomputes a
    schema, and nothing here repairs one: an artifact that does not agree
    with itself is unreliable evidence and this server does not start on it.
    """
    path = os.path.join(distribution_root, *PROJECTION_RELATIVE.split("/"))
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
        by_name[name] = {"name": name, "schema": schema, "script": script}
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


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def interpreter():
    """The interpreter running this server, so the child matches the host."""
    return sys.executable or "python3"


def run_tool(tool, arguments, workspace_root, environ):
    """Run one tool as a child process and report exactly what came back."""
    tail, ignored = build_argv(tool, arguments)
    argv = [interpreter(), tool["script"]] + tail

    child_env = dict(environ)
    child_env[WORKSPACE_ENV] = workspace_root

    try:
        completed = subprocess.run(
            argv,
            cwd=workspace_root,
            env=child_env,
            # The server's own stdin is the JSON-RPC stream. A child that
            # inherited it could consume the protocol.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise RpcError(
            INTERNAL_ERROR,
            "%s could not be started: %s" % (tool["name"], exc),
            {"tool": tool["name"], "argv": argv})

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
        self.projection = None
        self.execution_context_id = None
        self.client_name = None
        self.client_version = None

    # -- lifecycle --------------------------------------------------------

    def handle_initialize(self, params):
        # Both preconditions are settled here, so a session never comes up
        # advertising an interface it cannot serve.
        self.workspace_root = resolve_workspace_root(self.environ)
        self.projection = load_projection(self.distribution_root,
                                          self.environ)
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
        if self.projection is None or self.workspace_root is None:
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
        # Re-read the binding: the directory can go away between calls, and
        # a stale root would run the corpus's tools somewhere else.
        workspace_root = resolve_workspace_root(self.environ)
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
        return run_tool(tool, arguments, workspace_root, execution_env)

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
