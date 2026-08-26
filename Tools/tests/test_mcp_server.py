"""`Tools/mcp_server.py` is layer 3, and these tests hold it to that.

Three properties are worth more than the rest and each has its own class:

  * the transport imports no judgment module, checked statically on the
    source bytes so it cannot be edited away quietly;
  * the tool list is the compiled artifact and not a recomputation of it;
  * a tool's exit code arrives as the verdict it is -- 2 in particular is
    never rendered as a success or as a failure, and output the server
    cannot parse is reported as unparseable rather than resolved into a
    result.

Most cases run against a synthetic distribution: a handful of one-line
tools with exactly the exit codes and stdout shapes under test, and a
projection that lists them. That keeps the exit-code table exact and
hermetic. A final class runs the real thing end to end, driving the shipped
server as a child process over a pipe against this repository.
"""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS.parent
SERVER_SOURCE = TOOLS / "mcp_server.py"

sys.path.insert(0, str(TOOLS))
import mcp_server  # noqa: E402
import module_boundary_facts  # noqa: E402
import path_capability  # noqa: E402


# ---------------------------------------------------------------------------
# The synthetic distribution
# ---------------------------------------------------------------------------

# Each fake tool writes a receipt-shaped array on stdout under `--json` and
# its human report on stderr, which is the split the real tools use.
FAKE_TOOLS = {
    "clean_tool": (
        "import sys\n"
        "sys.stderr.write('clean_tool: nothing to report\\n')\n"
        "print('[{\"receipt_id\": \"r-clean\"}]')\n"
        "sys.exit(0)\n"
    ),
    "fail_tool": (
        "import sys\n"
        "sys.stderr.write('fail_tool: one failure\\n')\n"
        "print('[{\"receipt_id\": \"r-fail\"}]')\n"
        "sys.exit(1)\n"
    ),
    "hold_tool": (
        "import sys\n"
        "sys.stderr.write('hold_tool: 3 candidate(s) a person must read\\n')\n"
        "print('[{\"receipt_id\": \"r-hold\"}]')\n"
        "sys.exit(2)\n"
    ),
    "noise_tool": (
        "import sys\n"
        "sys.stderr.write('noise_tool: report\\n')\n"
        "print('this is not JSON at all')\n"
        "sys.exit(0)\n"
    ),
    "echo_tool": (
        "import json, os, sys\n"
        "manifest=json.loads(os.environ.get('CAMBIUM_PATH_CAPABILITIES', "
        "'{}'))\n"
        "ack=os.environ.get('CAMBIUM_PATH_CAPABILITIES_ACK_FD')\n"
        "if ack is not None:\n"
        "    for row in manifest.get('capabilities', []):\n"
        "        os.write(int(ack), (row['capability_id']+'\\n').encode())\n"
        "print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(),\n"
        "                  'workspace': os.environ.get("
        "'CAMBIUM_WORKSPACE_ROOT'),\n"
        "                  'execution_context': os.environ.get("
        "'CAMBIUM_EXECUTION_CONTEXT_ID')}))\n"
        "sys.exit(0)\n"
    ),
    "odd_tool": (
        "import sys\n"
        "sys.exit(9)\n"
    ),
    # Declares no --json: several real tools emit no receipts and write
    # their whole report to stdout.
    "silent_tool": (
        "import sys\n"
        "print('silent_tool --check: one product is stale')\n"
        "sys.exit(2)\n"
    ),
}


def _string(description, option=None, path_access=None,
            path_constraint="contained", path_value=None, suffixes=None):
    schema = {"description": description, "type": "string"}
    schema["x-cambium-cli"] = {
        "action": "store",
        "option_strings": [option] if option else [],
    }
    if path_access is not None:
        schema[mcp_server.PATH_EXTENSION_KEY] = {
            "access": path_access,
            "consumption": {
                "read": "snapshot",
                "write": "replace",
                "read-write": "transaction",
            }[path_access],
            "constraint": path_constraint,
            "value": path_value,
            "suffixes": list(suffixes or []),
            "active_when_any": [],
            "inactive_when_any": [],
        }
    return schema


def _flag(description, option):
    return {
        "default": False,
        "description": description,
        "type": "boolean",
        "x-cambium-cli": {"action": "store_true", "nargs": 0,
                          "option_strings": [option]},
    }


def _appended(description, option):
    return {
        "description": description,
        "items": {"type": "string"},
        "type": "array",
        "x-cambium-cli": {"action": "append", "option_strings": [option]},
    }


def fake_projection():
    """A projection with the shape `load_projection` insists on."""
    common = {
        "json": _flag("machine-readable receipts on stdout", "--json"),
    }
    tools = []
    for name in sorted(FAKE_TOOLS):
        properties = {} if name == "silent_tool" else dict(common)
        required = []
        if name == "echo_tool":
            properties["first"] = _string("first positional")
            properties["second"] = _string("second positional")
            properties["root"] = _string(
                "repository root", "--root")
            properties["scope"] = _string(
                "scoped path", "--scope", path_access="read")
            properties["apply"] = _flag("write the transaction", "--apply")
            properties["exclude"] = _appended("excluded tree", "--exclude")
            properties["count"] = {
                "description": "a number",
                "type": "integer",
                "x-cambium-cli": {"action": "store",
                                  "option_strings": ["--count"]},
            }
            # Declaration order, not sorted order: `first` before `second`.
            required = ["first", "second"]
        else:
            properties["root"] = _string("repository root")
            required = ["root"]
        tools.append({
            "description": "synthetic %s" % name,
            "inputSchema": {
                "additionalProperties": False,
                "properties": properties,
                "required": required,
                "type": "object",
            },
            "name": name,
            mcp_server.WORKSPACE_EXTENSION_KEY: {
                "argument": "root", "access": "read"},
        })
    return {
        "artifact": "agent-interface-projection",
        "form": "mcp",
        "schema_version": mcp_server.PROJECTION_SCHEMA_VERSION,
        "tool_count": len(tools),
        "tools": tools,
        "transports": ["stdio", "streamable-http"],
    }


class SyntheticDistribution(object):
    """A distribution root holding only the fake tools and a projection."""

    def __init__(self, projection=None, tool_sources=None,
                 production_roots=()):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "dist"
        (self.root / "Tools" / "compiled").mkdir(parents=True)
        self.workspace = Path(self._tmp.name) / "corpus"
        self.workspace.mkdir()
        for name, source in (tool_sources or FAKE_TOOLS).items():
            target = self.root / "Tools" / ("%s.py" % name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        if production_roots:
            module_boundary_facts.stage_shipped_modules(
                str(REPO_ROOT), str(self.root), list(production_roots))
        document = fake_projection() if projection is None else projection
        self.projection_path = self.root / "Tools/compiled/mcp-tools.json"
        self.projection_path.write_text(
            json.dumps(document, sort_keys=True), encoding="utf-8")

    def environ(self, **overrides):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "TMPDIR": os.environ.get("TMPDIR", "/private/tmp"),
            mcp_server.WORKSPACE_ENV: str(self.workspace),
        }
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def server(self, **overrides):
        return mcp_server.Server(distribution_root=str(self.root),
                                 environ=self.environ(**overrides))

    def cleanup(self):
        self._tmp.cleanup()


INITIALIZE = {"protocolVersion": "2025-11-25", "capabilities": {},
              "clientInfo": {"name": "test", "version": "0"}}


def request(server, method, params=None, message_id=1):
    return mcp_server.handle_message(server, {
        "jsonrpc": "2.0", "id": message_id, "method": method,
        "params": {} if params is None else params,
    })


def started(distribution, **overrides):
    server = distribution.server(**overrides)
    response = request(server, "initialize", INITIALIZE)
    assert "result" in response, response
    return server


class SyntheticCase(unittest.TestCase):
    def setUp(self):
        self.dist = SyntheticDistribution()
        self.addCleanup(self.dist.cleanup)


# ---------------------------------------------------------------------------
# Layer 3 carries; it does not judge
# ---------------------------------------------------------------------------


class LayerBoundaryTests(unittest.TestCase):
    """The transport must not be able to reach a judgment module at all."""

    def setUp(self):
        self.source = SERVER_SOURCE.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def imported_module_names(self):
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    names.add(".")
                if node.module:
                    names.add(node.module.split(".")[0])
        return names

    def test_no_module_shipped_under_tools_is_imported(self):
        shipped = {path.stem for path in TOOLS.glob("*.py")}

        self.assertEqual(sorted(self.imported_module_names() & shipped), [])

    def test_no_judgment_module_is_imported_by_name(self):
        judgment_prefixes = ("check_", "apply_", "update_", "compile_",
                             "compose_", "render_", "adopt_", "register_",
                             "record_", "run_", "seal_", "stamp_",
                             "project_", "profile_", "scaffold_", "init_",
                             "duplicate_", "coverage_", "batch_",
                             "candidate_", "amendment_", "maintenance_")
        offenders = sorted(
            name for name in self.imported_module_names()
            if name == "kblib" or name.startswith(judgment_prefixes)
        )

        self.assertEqual(offenders, [])

    def test_every_import_is_standard_library(self):
        allowed = {
            "hashlib", "json", "os", "stat", "subprocess", "sys", "traceback",
            "uuid",
        }

        self.assertEqual(self.imported_module_names() - allowed, set())

    def test_the_import_check_cannot_be_dodged_dynamically(self):
        """A dynamic import would make the static check meaningless."""
        dodges = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = (func.attr if isinstance(func, ast.Attribute)
                        else getattr(func, "id", ""))
                if name in ("__import__", "import_module", "exec", "eval"):
                    dodges.add(name)

        self.assertEqual(sorted(dodges), [])

    def test_the_server_declares_no_cli_and_is_not_a_compiled_tool(self):
        """The transport must never appear in its own tool list."""
        sys.path.insert(0, str(TOOLS))
        import compile_cli_contract

        self.assertFalse(compile_cli_contract.is_cli_module(self.source))

        projection = json.loads(
            (TOOLS / "compiled/mcp-tools.json").read_text(encoding="utf-8"))

        self.assertNotIn("mcp_server",
                         {tool["name"] for tool in projection["tools"]})

    def test_the_shipped_projection_is_servable_as_it_stands(self):
        """Every tool the real artifact lists resolves to a real script."""
        loaded = mcp_server.load_projection(
            str(REPO_ROOT), {mcp_server.WORKSPACE_ENV: str(REPO_ROOT)})
        projection = json.loads(
            (TOOLS / "compiled/mcp-tools.json").read_text(encoding="utf-8"))
        self.assertEqual(len(loaded["listed"]), len(projection["tools"]))


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------


class InitializeTests(SyntheticCase):
    def test_response_carries_the_three_required_fields(self):
        response = request(self.dist.server(), "initialize", INITIALIZE)

        result = response["result"]
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(result["protocolVersion"], "2025-11-25")
        self.assertEqual(result["capabilities"], {"tools": {}})
        self.assertEqual(result["serverInfo"]["name"], "cambium")
        self.assertEqual(result["serverInfo"]["version"],
                         mcp_server.SERVER_VERSION)

    def test_a_supported_version_is_echoed_back_unchanged(self):
        for version in mcp_server.SUPPORTED_PROTOCOL_VERSIONS:
            with self.subTest(version=version):
                response = request(self.dist.server(), "initialize",
                                   dict(INITIALIZE, protocolVersion=version))

                self.assertEqual(response["result"]["protocolVersion"],
                                 version)

    def test_an_unsupported_version_negotiates_down_to_the_latest(self):
        """The 2025-11-25 rule: answer with a version this server supports."""
        response = request(self.dist.server(), "initialize",
                           dict(INITIALIZE, protocolVersion="1900-01-01"))

        self.assertEqual(response["result"]["protocolVersion"],
                         mcp_server.LATEST_PROTOCOL_VERSION)

    def test_no_listChanged_is_claimed(self):
        """Nothing here ever sends notifications/tools/list_changed."""
        response = request(self.dist.server(), "initialize", INITIALIZE)

        self.assertNotIn("listChanged",
                         response["result"]["capabilities"]["tools"])

    def test_the_initialized_notification_is_answered_with_nothing(self):
        server = started(self.dist)

        response = mcp_server.handle_message(server, {
            "jsonrpc": "2.0", "method": "notifications/initialized"})

        self.assertIsNone(response)


class BindingTests(SyntheticCase):
    """`CAMBIUM_WORKSPACE_ROOT` or a clean refusal; never a cwd fallback."""

    def refusal(self, **overrides):
        response = request(self.dist.server(**overrides), "initialize",
                           INITIALIZE)
        self.assertIn("error", response, response)
        return response["error"]

    def test_an_unset_workspace_root_refuses_at_initialize(self):
        error = self.refusal(**{mcp_server.WORKSPACE_ENV: None})

        self.assertEqual(error["code"], mcp_server.NOT_BOUND)
        self.assertIn("CAMBIUM_WORKSPACE_ROOT", error["message"])
        self.assertEqual(error["data"]["variable"], "CAMBIUM_WORKSPACE_ROOT")

    def test_a_platform_without_no_follow_descriptors_refuses_initialize(self):
        original = mcp_server.os.O_NOFOLLOW
        delattr(mcp_server.os, "O_NOFOLLOW")
        try:
            error = self.refusal()
        finally:
            setattr(mcp_server.os, "O_NOFOLLOW", original)

        self.assertEqual(error["code"], mcp_server.NOT_BOUND)
        self.assertIn("cannot hold a no-follow workspace directory",
                      error["message"])

    def test_the_refusal_says_the_host_must_set_the_variable(self):
        error = self.refusal(**{mcp_server.WORKSPACE_ENV: None})

        self.assertIn("host configuration must set it", error["message"])
        self.assertIn("no working-directory fallback", error["message"])

    def test_an_empty_workspace_root_is_not_treated_as_unset_silently(self):
        error = self.refusal(**{mcp_server.WORKSPACE_ENV: "   "})

        self.assertEqual(error["code"], mcp_server.NOT_BOUND)

    def test_the_unsubstituted_placeholder_refuses(self):
        error = self.refusal(
            **{mcp_server.WORKSPACE_ENV: "<CAMBIUM_WORKSPACE_ROOT>"})

        self.assertEqual(error["code"], mcp_server.NOT_BOUND)
        self.assertIn("not an absolute path", error["message"])

    def test_a_relative_workspace_root_does_not_become_the_cwd(self):
        error = self.refusal(**{mcp_server.WORKSPACE_ENV: "."})

        self.assertEqual(error["code"], mcp_server.NOT_BOUND)

    def test_a_workspace_root_that_is_not_a_directory_refuses(self):
        error = self.refusal(
            **{mcp_server.WORKSPACE_ENV: str(self.dist.root / "absent")})

        self.assertEqual(error["code"], mcp_server.NOT_BOUND)

    def test_the_bound_root_is_the_child_working_directory(self):
        server = started(self.dist)

        result = request(server, "tools/call",
                         {"name": "echo_tool",
                          "arguments": {"root": ".", "first": "a",
                                        "second": "b"}})["result"]

        payload = result["structuredContent"]["stdout_json"]
        self.assertEqual(os.path.realpath(payload["cwd"]),
                         os.path.realpath(str(self.dist.workspace)))
        self.assertEqual(payload["workspace"],
                         os.path.realpath(str(self.dist.workspace)))

    def test_a_session_refuses_a_replaced_workspace_directory(self):
        server = started(self.dist)
        original = self.dist.workspace
        displaced = original.with_name("corpus-initialized")
        original.rename(displaced)
        original.mkdir()

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b"},
        })

        self.assertEqual(response["error"]["code"], mcp_server.NOT_BOUND)
        self.assertIn("changed after initialize", response["error"]["message"])

    def test_one_call_cannot_race_into_a_replacement_workspace(self):
        server = started(self.dist)
        original = self.dist.workspace
        displaced = original.with_name("corpus-authorized")
        actual_run_tool = mcp_server.run_tool

        def replace_after_binding_check(tool, arguments, workspace_root,
                                        workspace_fd, environ):
            original.rename(displaced)
            original.mkdir()
            return actual_run_tool(
                tool, arguments, workspace_root, workspace_fd, environ)

        with mock.patch.object(
                mcp_server, "run_tool", side_effect=replace_after_binding_check):
            response = request(server, "tools/call", {
                "name": "echo_tool",
                "arguments": {"root": ".", "first": "a", "second": "b"},
            })

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(os.path.realpath(payload["cwd"]),
                         os.path.realpath(str(displaced)))


class ProjectionLoadTests(SyntheticCase):
    """A tool table that cannot be trusted fails initialize, not a call."""

    def error_for(self, mutate):
        document = fake_projection()
        mutate(document)
        broken = SyntheticDistribution(projection=document)
        self.addCleanup(broken.cleanup)
        response = request(broken.server(), "initialize", INITIALIZE)
        self.assertIn("error", response, response)
        return response["error"]

    def test_a_missing_projection_fails_initialize(self):
        self.dist.projection_path.unlink()

        response = request(self.dist.server(), "initialize", INITIALIZE)

        self.assertEqual(response["error"]["code"],
                         mcp_server.UNRELIABLE_EVIDENCE)

    def test_an_unparseable_projection_fails_initialize(self):
        self.dist.projection_path.write_text("{ not json", encoding="utf-8")

        response = request(self.dist.server(), "initialize", INITIALIZE)

        self.assertEqual(response["error"]["code"],
                         mcp_server.UNRELIABLE_EVIDENCE)
        self.assertIn("not parseable JSON", response["error"]["message"])

    def test_a_failed_initialize_leaves_no_tool_list_behind(self):
        self.dist.projection_path.unlink()
        server = self.dist.server()
        request(server, "initialize", INITIALIZE)

        response = request(server, "tools/list")

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_REQUEST)

    def test_a_projection_that_is_not_the_declared_artifact_fails(self):
        error = self.error_for(
            lambda doc: doc.__setitem__("artifact", "something-else"))

        self.assertEqual(error["code"], mcp_server.UNRELIABLE_EVIDENCE)

    def test_a_tool_count_that_disagrees_with_the_list_fails(self):
        error = self.error_for(lambda doc: doc.__setitem__("tool_count", 99))

        self.assertEqual(error["code"], mcp_server.UNRELIABLE_EVIDENCE)

    def test_a_listed_tool_with_no_script_fails(self):
        def add_phantom(document):
            document["tools"].append({
                "description": "not shipped",
                "inputSchema": {"properties": {}, "type": "object"},
                "name": "phantom_tool",
            })
            document["tool_count"] = len(document["tools"])

        error = self.error_for(add_phantom)

        self.assertEqual(error["code"], mcp_server.UNRELIABLE_EVIDENCE)
        self.assertIn("phantom_tool", error["message"])

    def test_a_registered_source_hash_that_does_not_match_fails(self):
        response = request(
            self.dist.server(
                **{mcp_server.SOURCE_HASH_ENV: "sha256:" + "0" * 64}),
            "initialize", INITIALIZE)

        self.assertEqual(response["error"]["code"],
                         mcp_server.UNRELIABLE_EVIDENCE)
        self.assertIn("registered against", response["error"]["message"])

    def test_the_matching_source_hash_starts_normally(self):
        digest = mcp_server.sha256_of(self.dist.projection_path.read_bytes())

        response = request(
            self.dist.server(**{mcp_server.SOURCE_HASH_ENV: digest}),
            "initialize", INITIALIZE)

        self.assertIn("result", response)


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------


class ToolsListTests(SyntheticCase):
    def test_the_list_is_the_artifact(self):
        server = started(self.dist)
        document = json.loads(
            self.dist.projection_path.read_text(encoding="utf-8"))
        expected = document["tools"]

        listed = request(server, "tools/list")["result"]["tools"]

        self.assertEqual(sorted(listed, key=lambda row: row["name"]),
                         sorted(expected, key=lambda row: row["name"]))

    def test_the_shipped_artifact_projects_verbatim(self):
        """No schema is adjusted on the way past."""
        artifact = json.loads(
            (TOOLS / "compiled/mcp-tools.json").read_text(encoding="utf-8"))
        loaded = mcp_server.load_projection(
            str(REPO_ROOT), {mcp_server.WORKSPACE_ENV: str(REPO_ROOT)})

        by_name = {row["name"]: row for row in loaded["listed"]}
        self.assertEqual(sorted(by_name), sorted(
            tool["name"] for tool in artifact["tools"]))
        for tool in artifact["tools"]:
            with self.subTest(tool=tool["name"]):
                row = by_name[tool["name"]]

                self.assertEqual(row["inputSchema"], tool["inputSchema"])
                self.assertEqual(row["description"], tool["description"])


# ---------------------------------------------------------------------------
# tools/call: argv, and the seam
# ---------------------------------------------------------------------------


class ArgvTests(SyntheticCase):
    def server_with_scope_capability(self, constraint, value=None,
                                     suffixes=None, access="read",
                                     consumption="snapshot"):
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        echo["inputSchema"]["properties"]["scope"][
            mcp_server.PATH_EXTENSION_KEY] = {
                "access": access, "consumption": consumption,
                "constraint": constraint,
                "value": value, "suffixes": list(suffixes or []),
                "active_when_any": [], "inactive_when_any": [],
            }
        distribution = SyntheticDistribution(projection=projection)
        self.addCleanup(distribution.cleanup)
        return distribution, started(distribution)

    def envelope(self, name, arguments, server=None):
        server = server or started(self.dist)
        arguments = dict(arguments)
        arguments.setdefault("root", ".")
        response = request(server, "tools/call",
                           {"name": name, "arguments": arguments})
        self.assertIn("result", response, response)
        return response["result"]["structuredContent"]


class StableConsumptionTests(ArgvTests):
    """Admission descriptors, not reopened names, reach shared tool I/O."""

    def distribution_for(self, source, access, consumption):
        sources = dict(FAKE_TOOLS)
        sources["echo_tool"] = source
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        echo["inputSchema"]["properties"]["scope"][
            mcp_server.PATH_EXTENSION_KEY] = {
                "access": access,
                "consumption": consumption,
                "constraint": "contained",
                "value": None,
                "suffixes": [],
                "active_when_any": [],
                "inactive_when_any": [],
            }
        distribution = SyntheticDistribution(
            projection=projection, tool_sources=sources,
            production_roots=("kblib",))
        self.addCleanup(distribution.cleanup)
        return distribution, started(distribution)

    def test_acknowledgement_names_only_the_exact_consumed_record(self):
        rows = (
            {"capability_id": "first[0]", "spelling": "same.md",
             "consumption": "snapshot"},
            {"capability_id": "second[0]", "spelling": "same.md",
             "consumption": "snapshot"},
        )
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        with mock.patch.object(path_capability, "_MANIFEST_CACHE", rows), \
                mock.patch.object(path_capability, "_ACKNOWLEDGED", set()), \
                mock.patch.dict(os.environ, {
                    path_capability.PATH_CAPABILITIES_ACK_ENV: str(write_fd),
                }, clear=False):
            path_capability.acknowledge(rows[0])
        os.close(write_fd)

        self.assertEqual(os.read(read_fd, 1024), b"first[0]\n")

    def test_advanced_targets_are_isolated_by_exact_capability(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            target = parent / "same.jsonl"
            spelling = path_capability.logical_spelling(target)
            append = {
                "capability_id": "append[0]", "spelling": spelling,
                "consumption": "append",
            }
            transaction = {
                "capability_id": "transaction[0]", "spelling": spelling,
                "consumption": "transaction",
            }
            parent_fd = os.open(parent, os.O_RDONLY)
            writer_fd = os.open(target, os.O_WRONLY | os.O_CREAT, 0o600)
            advanced = {}
            try:
                written = os.fstat(writer_fd)
                with mock.patch.object(
                        path_capability, "_ADVANCED_TARGETS", advanced):
                    path_capability.record_append_target(
                        append, parent_fd, target.name, target, written)
                    os.close(writer_fd)
                    writer_fd = None
                    replacement = parent / "replacement"
                    replacement.write_text("replacement", encoding="utf-8")
                    os.replace(replacement, target)
                    path_capability.record_replacement(
                        transaction, parent_fd, target.name, target)

                    append_target = path_capability.effective_target(append)
                    transaction_target = path_capability.effective_target(
                        transaction)
                    self.assertEqual(
                        append_target[1:], (written.st_dev, written.st_ino))
                    self.assertNotEqual(
                        append_target[1:], transaction_target[1:])
            finally:
                if writer_fd is not None:
                    os.close(writer_fd)
                for row in advanced.values():
                    os.close(row["fd"])
                os.close(parent_fd)

    @staticmethod
    def call(server, scope):
        return request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {
                "root": ".", "first": "a", "second": "b",
                "scope": scope,
            },
        })

    @staticmethod
    def reader_source(body):
        return (
            "import argparse, json, kblib\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('first'); p.add_argument('second')\n"
            "p.add_argument('--root'); p.add_argument('--scope')\n"
            "p.add_argument('--apply', action='store_true')\n"
            "p.add_argument('--exclude', action='append')\n"
            "p.add_argument('--count', type=int)\n"
            "p.add_argument('--json', action='store_true')\n"
            "a=p.parse_args()\n" + body
        )

    def _swap_during_spawn(self, mutate):
        real_run = mcp_server.subprocess.run
        fired = {"value": False}

        def barrier(*args, **kwargs):
            if not fired["value"]:
                fired["value"] = True
                mutate()
            return real_run(*args, **kwargs)
        return mock.patch.object(mcp_server.subprocess, "run",
                                 side_effect=barrier)

    def test_snapshot_file_reads_the_admitted_inode_after_final_swap(self):
        source = self.reader_source(
            "print(json.dumps({'content': kblib.read_text(a.scope)}))\n")
        distribution, server = self.distribution_for(
            source, "read", "snapshot")
        admitted = distribution.workspace / "note.md"
        admitted.write_text("admitted", encoding="utf-8")
        outside_dir = Path(self.dist._tmp.name) / "outside-read"
        outside_dir.mkdir()
        outside = outside_dir / "secret.md"
        outside.write_text("outside", encoding="utf-8")
        displaced = distribution.workspace / "note-admitted.md"

        def mutate():
            admitted.rename(displaced)
            admitted.symlink_to(outside)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "note.md")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["content"], "admitted")

    def test_repeatable_paths_retain_and_consume_each_admitted_object(self):
        source = (
            "import argparse, json, kblib\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('first'); p.add_argument('second')\n"
            "p.add_argument('--root'); p.add_argument('--scope', "
            "action='append')\n"
            "p.add_argument('--apply', action='store_true')\n"
            "p.add_argument('--exclude', action='append')\n"
            "p.add_argument('--count', type=int)\n"
            "p.add_argument('--json', action='store_true')\n"
            "a=p.parse_args()\n"
            "print(json.dumps({'content': [kblib.read_text(path) "
            "for path in a.scope]}))\n"
        )
        sources = dict(FAKE_TOOLS)
        sources["echo_tool"] = source
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        scope = _appended("scoped path", "--scope")
        scope[mcp_server.PATH_EXTENSION_KEY] = {
            "access": "read", "consumption": "snapshot",
            "constraint": "contained", "value": None, "suffixes": [],
            "active_when_any": [], "inactive_when_any": [],
        }
        echo["inputSchema"]["properties"]["scope"] = scope
        distribution = SyntheticDistribution(
            projection=projection, tool_sources=sources,
            production_roots=("kblib",))
        self.addCleanup(distribution.cleanup)
        server = started(distribution)
        first = distribution.workspace / "first.md"
        second = distribution.workspace / "second.md"
        first.write_text("first-admitted", encoding="utf-8")
        second.write_text("second-admitted", encoding="utf-8")
        displaced = distribution.workspace / "second-admitted.md"
        outside = Path(self.dist._tmp.name) / "outside-repeatable.md"
        outside.write_text("outside", encoding="utf-8")

        def mutate():
            second.rename(displaced)
            second.symlink_to(outside)

        with self._swap_during_spawn(mutate):
            response = self.call(server, ["first.md", "second.md"])

        self.assertIn("result", response, response)
        structured = response["result"]["structuredContent"]
        self.assertEqual(
            structured["stdout_json"]["content"],
            ["first-admitted", "second-admitted"])
        self.assertEqual(
            structured["consumed_path_capabilities"],
            ["scope[0]", "scope[1]"])

    def test_snapshot_tree_reads_the_admitted_directory_after_parent_swap(self):
        source = self.reader_source(
            "s=kblib.repository_tree_snapshot(a.root,a.scope)\n"
            "print(json.dumps({'content': s.read_text(a.scope+'/note.md')}))\n")
        distribution, server = self.distribution_for(
            source, "read", "snapshot")
        admitted = distribution.workspace / "scope"
        admitted.mkdir()
        (admitted / "note.md").write_text("admitted", encoding="utf-8")
        outside = Path(self.dist._tmp.name) / "outside-tree"
        outside.mkdir()
        (outside / "note.md").write_text("outside", encoding="utf-8")
        displaced = distribution.workspace / "scope-admitted"

        def mutate():
            admitted.rename(displaced)
            admitted.symlink_to(outside, target_is_directory=True)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "scope")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["content"], "admitted")

    def test_manifest_file_binds_its_admitted_profile_package_parent(self):
        source = self.reader_source(
            "s=kblib.repository_parent_tree_snapshot(a.root,a.scope)\n"
            "print(json.dumps({'content': "
            "s.read_text('profile/slot.md')}))\n")
        distribution, server = self.distribution_for(
            source, "read", "snapshot")
        admitted = distribution.workspace / "profile"
        admitted.mkdir()
        (admitted / "profile.md").write_text("manifest", encoding="utf-8")
        (admitted / "slot.md").write_text("admitted", encoding="utf-8")
        displaced = distribution.workspace / "profile-admitted"
        outside = Path(self.dist._tmp.name) / "outside-profile"
        outside.mkdir()
        (outside / "profile.md").write_text("outside", encoding="utf-8")
        (outside / "slot.md").write_text("outside", encoding="utf-8")

        def mutate():
            admitted.rename(displaced)
            admitted.symlink_to(outside, target_is_directory=True)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "profile/profile.md")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["content"], "admitted")

    def test_nested_cambium_process_keeps_the_same_retained_object(self):
        parent = self.reader_source(
            "import os, subprocess, sys\n"
            "child=os.path.join(os.path.dirname(__file__),'child_tool.py')\n"
            "c=kblib.run_cambium_subprocess([sys.executable,child,a.scope],"
            "text=True,stdout=subprocess.PIPE,check=True,"
            ")\n"
            "print(c.stdout.strip())\n")
        child = (
            "import json,sys\n"
            "import kblib\n"
            "print(json.dumps({'content':kblib.read_text(sys.argv[1])}))\n"
        )
        sources = dict(FAKE_TOOLS)
        sources["echo_tool"] = parent
        sources["child_tool"] = child
        projection = fake_projection()
        distribution = SyntheticDistribution(
            projection=projection, tool_sources=sources,
            production_roots=("kblib",))
        self.addCleanup(distribution.cleanup)
        server = started(distribution)
        admitted = distribution.workspace / "note.md"
        admitted.write_text("admitted", encoding="utf-8")
        displaced = distribution.workspace / "note-admitted.md"
        outside = Path(self.dist._tmp.name) / "outside-child.md"
        outside.write_text("outside", encoding="utf-8")

        def mutate():
            admitted.rename(displaced)
            admitted.symlink_to(outside)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "note.md")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["content"], "admitted")

    def test_replace_uses_the_admitted_parent_after_parent_swap(self):
        source = self.reader_source(
            "kblib.atomic_write_text(a.scope,'published')\n"
            "print(json.dumps({'written': True}))\n")
        distribution, server = self.distribution_for(
            source, "write", "replace")
        admitted_parent = distribution.workspace / "reports"
        admitted_parent.mkdir()
        displaced = distribution.workspace / "reports-admitted"
        outside = Path(self.dist._tmp.name) / "outside-write"
        outside.mkdir()

        def mutate():
            admitted_parent.rename(displaced)
            admitted_parent.symlink_to(outside, target_is_directory=True)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "reports/result.md")

        self.assertIn("result", response, response)
        self.assertEqual((displaced / "result.md").read_text(), "published")
        self.assertFalse((outside / "result.md").exists())

    def test_append_uses_the_admitted_parent_after_parent_swap(self):
        source = self.reader_source(
            "kblib.write_receipts(a.scope,[{'receipt_id':'r1'}])\n"
            "print(json.dumps({'written': True}))\n")
        distribution, server = self.distribution_for(
            source, "write", "append")
        admitted_parent = distribution.workspace / "receipts"
        admitted_parent.mkdir()
        displaced = distribution.workspace / "receipts-admitted"
        outside = Path(self.dist._tmp.name) / "outside-append"
        outside.mkdir()

        def mutate():
            admitted_parent.rename(displaced)
            admitted_parent.symlink_to(outside, target_is_directory=True)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "receipts/result.jsonl")

        self.assertIn("result", response, response)
        self.assertIn('"receipt_id": "r1"',
                      (displaced / "result.jsonl").read_text())
        self.assertFalse((outside / "result.jsonl").exists())

    def test_first_append_to_missing_path_proves_exact_publication(self):
        source = self.reader_source(
            "first={'receipt_id':'r1'}\n"
            "second={'receipt_id':'r2'}\n"
            "o1,e1,_=kblib.write_receipts_observed(a.scope,[first])\n"
            "o2,e2,_=kblib.write_receipts_observed(a.scope,[second])\n"
            "print(json.dumps({'outcomes':[o1,o2],'errors':[str(e) "
            "if e else None for e in (e1,e2)]}))\n")
        distribution, server = self.distribution_for(
            source, "write", "append")
        receipts = distribution.workspace / "receipts"
        receipts.mkdir()

        response = self.call(server, "receipts/first.jsonl")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(
            payload,
            {"outcomes": ["present", "present"],
             "errors": [None, None]},
        )
        self.assertEqual(
            [{"receipt_id": "r1"}, {"receipt_id": "r2"}],
            [json.loads(line) for line in
             (receipts / "first.jsonl").read_text(
                 encoding="utf-8").splitlines()],
        )

    def test_created_append_is_still_present_after_parent_fsync_error(self):
        source = self.reader_source(
            "import os,stat\n"
            "real_fsync=kblib.os.fsync\n"
            "def fail_parent(fd):\n"
            " if stat.S_ISDIR(os.fstat(fd).st_mode):\n"
            "  raise OSError(5,'parent fsync failed')\n"
            " return real_fsync(fd)\n"
            "kblib.os.fsync=fail_parent\n"
            "receipt={'receipt_id':'r1'}\n"
            "outcome,error,_=kblib.write_receipts_observed("
            "a.scope,[receipt])\n"
            "print(json.dumps({'outcome':outcome,'error':str(error) "
            "if error else None}))\n")
        distribution, server = self.distribution_for(
            source, "write", "append")
        receipts = distribution.workspace / "receipts"
        receipts.mkdir()

        response = self.call(server, "receipts/uncertain-name.jsonl")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["outcome"], "present")
        self.assertIn("parent fsync failed", payload["error"])
        self.assertEqual(
            [{"receipt_id": "r1"}],
            [json.loads(line) for line in
             (receipts / "uncertain-name.jsonl").read_text(
                 encoding="utf-8").splitlines()],
        )

    def test_partial_first_append_is_uncertain_not_absent(self):
        source = self.reader_source(
            "import os,stat\n"
            "real_write=kblib.os.write\n"
            "def short_regular(fd,data):\n"
            " if stat.S_ISREG(os.fstat(fd).st_mode):\n"
            "  part=data[:max(1,len(data)//2)]\n"
            "  return real_write(fd,part)\n"
            " return real_write(fd,data)\n"
            "kblib.os.write=short_regular\n"
            "receipt={'receipt_id':'r1'}\n"
            "outcome,error,_=kblib.write_receipts_observed("
            "a.scope,[receipt])\n"
            "print(json.dumps({'outcome':outcome,'error':str(error) "
            "if error else None}))\n")
        distribution, server = self.distribution_for(
            source, "write", "append")
        receipts = distribution.workspace / "receipts"
        receipts.mkdir()

        response = self.call(server, "receipts/partial.jsonl")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["outcome"], "uncertain")
        self.assertIn("receipt append was partial", payload["error"])
        self.assertGreater((receipts / "partial.jsonl").stat().st_size, 0)

    def test_created_append_displaced_before_observation_is_uncertain(self):
        source = self.reader_source(
            "import os,stat\n"
            "real_fsync=kblib.os.fsync\n"
            "fired={'value':False}\n"
            "def displace_on_parent_fsync(fd):\n"
            " if stat.S_ISDIR(os.fstat(fd).st_mode) and not fired['value']:\n"
            "  fired['value']=True\n"
            "  os.replace(a.scope,a.scope+'.displaced')\n"
            "  with open(a.scope,'w',encoding='utf-8') as foreign:\n"
            "   foreign.write('{\\\"receipt_id\\\":\\\"foreign\\\"}\\n')\n"
            " return real_fsync(fd)\n"
            "kblib.os.fsync=displace_on_parent_fsync\n"
            "receipt={'receipt_id':'r1'}\n"
            "outcome,error,_=kblib.write_receipts_observed("
            "a.scope,[receipt])\n"
            "print(json.dumps({'outcome':outcome,'error':str(error) "
            "if error else None}))\n")
        distribution, server = self.distribution_for(
            source, "write", "append")
        receipts = distribution.workspace / "receipts"
        receipts.mkdir()

        response = self.call(server, "receipts/displaced.jsonl")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["outcome"], "uncertain")
        self.assertIn("could not be proven durable", payload["error"])
        self.assertEqual(
            {"receipt_id": "r1"},
            json.loads((receipts / "displaced.jsonl.displaced").read_text(
                encoding="utf-8")),
        )

    def test_existing_append_displaced_before_observation_is_uncertain(self):
        source = self.reader_source(
            "import os,stat\n"
            "real_fsync=kblib.os.fsync\n"
            "fired={'value':False}\n"
            "def displace_on_parent_fsync(fd):\n"
            " if stat.S_ISDIR(os.fstat(fd).st_mode) and not fired['value']:\n"
            "  fired['value']=True\n"
            "  os.replace(a.scope,a.scope+'.displaced')\n"
            "  with open(a.scope,'w',encoding='utf-8') as foreign:\n"
            "   foreign.write('{\\\"receipt_id\\\":\\\"foreign\\\"}\\n')\n"
            " return real_fsync(fd)\n"
            "kblib.os.fsync=displace_on_parent_fsync\n"
            "receipt={'receipt_id':'r1'}\n"
            "outcome,error,_=kblib.write_receipts_observed("
            "a.scope,[receipt])\n"
            "print(json.dumps({'outcome':outcome,'error':str(error) "
            "if error else None}))\n")
        distribution, server = self.distribution_for(
            source, "write", "append")
        receipts = distribution.workspace / "receipts"
        receipts.mkdir()
        target = receipts / "existing.jsonl"
        target.write_text(
            json.dumps({"receipt_id": "before"}) + "\n", encoding="utf-8")

        response = self.call(server, "receipts/existing.jsonl")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["outcome"], "uncertain")
        self.assertIn("could not be proven durable", payload["error"])
        self.assertEqual(
            [{"receipt_id": "before"}, {"receipt_id": "r1"}],
            [json.loads(line) for line in
             (receipts / "existing.jsonl.displaced").read_text(
                 encoding="utf-8").splitlines()],
        )

    def test_created_append_hard_linked_before_observation_is_uncertain(self):
        source = self.reader_source(
            "import os,stat\n"
            "real_fsync=kblib.os.fsync\n"
            "fired={'value':False}\n"
            "def link_on_parent_fsync(fd):\n"
            " if stat.S_ISDIR(os.fstat(fd).st_mode) and not fired['value']:\n"
            "  fired['value']=True\n"
            "  os.link(a.scope,a.scope+'.alias')\n"
            " return real_fsync(fd)\n"
            "kblib.os.fsync=link_on_parent_fsync\n"
            "receipt={'receipt_id':'r1'}\n"
            "outcome,error,_=kblib.write_receipts_observed("
            "a.scope,[receipt])\n"
            "print(json.dumps({'outcome':outcome,'error':str(error) "
            "if error else None}))\n")
        distribution, server = self.distribution_for(
            source, "write", "append")
        receipts = distribution.workspace / "receipts"
        receipts.mkdir()

        response = self.call(server, "receipts/linked.jsonl")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["outcome"], "uncertain")
        self.assertIn("could not be proven durable", payload["error"])
        self.assertEqual((receipts / "linked.jsonl").stat().st_nlink, 2)

    def test_nested_child_receives_advanced_append_capability(self):
        parent = self.reader_source(
            "import os,subprocess,sys\n"
            "first={'receipt_id':'r1'}\n"
            "o1,e1,_=kblib.write_receipts_observed(a.scope,[first])\n"
            "child=os.path.join(os.path.dirname(__file__),'child_tool.py')\n"
            "c=kblib.run_cambium_subprocess([sys.executable,child,a.scope],"
            "text=True,stdout=subprocess.PIPE,check=True,"
            "env={'CUSTOM_SENTINEL':'kept',"
            "'CAMBIUM_PATH_CAPABILITIES':'forged'})\n"
            "print(json.dumps({'parent_outcome':o1,'parent_error':str(e1) "
            "if e1 else None,'child':json.loads(c.stdout)}))\n")
        child = (
            "import json,sys\n"
            "import kblib\n"
            "second={'receipt_id':'r2'}\n"
            "outcome,error,_=kblib.write_receipts_observed("
            "sys.argv[1],[second])\n"
            "print(json.dumps({'outcome':outcome,'error':str(error) "
            "if error else None,'custom':__import__('os').environ.get("
            "'CUSTOM_SENTINEL')}))\n"
        )
        sources = dict(FAKE_TOOLS)
        sources["echo_tool"] = parent
        sources["child_tool"] = child
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        echo["inputSchema"]["properties"]["scope"][
            mcp_server.PATH_EXTENSION_KEY] = {
                "access": "write", "consumption": "append",
                "constraint": "contained", "value": None,
                "suffixes": [], "active_when_any": [],
                "inactive_when_any": [],
            }
        distribution = SyntheticDistribution(
            projection=projection, tool_sources=sources,
            production_roots=("kblib",))
        self.addCleanup(distribution.cleanup)
        server = started(distribution)
        receipts = distribution.workspace / "receipts"
        receipts.mkdir()

        response = self.call(server, "receipts/nested.jsonl")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload, {
            "parent_outcome": "present", "parent_error": None,
            "child": {"outcome": "present", "error": None,
                      "custom": "kept"},
        })
        self.assertEqual(
            [{"receipt_id": "r1"}, {"receipt_id": "r2"}],
            [json.loads(line) for line in
             (receipts / "nested.jsonl").read_text(
                 encoding="utf-8").splitlines()],
        )

    def test_transaction_reads_before_and_replaces_name_without_following_swap(self):
        source = self.reader_source(
            "before=kblib.read_text(a.scope)\n"
            "kblib.atomic_write_text(a.scope,before+'+published')\n"
            "print(json.dumps({'content': kblib.read_text(a.scope)}))\n")
        distribution, server = self.distribution_for(
            source, "read-write", "transaction")
        page = distribution.workspace / "page.md"
        page.write_text("admitted", encoding="utf-8")
        displaced = distribution.workspace / "page-admitted.md"
        outside = Path(self.dist._tmp.name) / "outside-transaction.md"
        outside.write_text("outside", encoding="utf-8")

        def mutate():
            page.rename(displaced)
            page.symlink_to(outside)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "page.md")

        self.assertIn("result", response, response)
        payload = response["result"]["structuredContent"]["stdout_json"]
        self.assertEqual(payload["content"], "admitted+published")
        self.assertEqual(outside.read_text(), "outside")
        self.assertEqual(page.read_text(), "admitted+published")

    def test_success_without_consuming_a_typed_path_is_refused(self):
        source = self.reader_source(
            "print(json.dumps({'ignored': a.scope}))\n")
        distribution, server = self.distribution_for(
            source, "read", "snapshot")
        (distribution.workspace / "note.md").write_text(
            "admitted", encoding="utf-8")

        response = self.call(server, "note.md")

        self.assertEqual(response["error"]["code"],
                         mcp_server.INTERNAL_ERROR)
        self.assertEqual(
            response["error"]["data"]["missing_path_capabilities"],
            ["scope[0]"])

    def test_success_without_consuming_a_write_path_is_refused(self):
        source = self.reader_source(
            "print(json.dumps({'ignored': a.scope}))\n")
        distribution, server = self.distribution_for(
            source, "write", "replace")
        (distribution.workspace / "reports").mkdir()

        response = self.call(server, "reports/result.md")

        self.assertEqual(response["error"]["code"],
                         mcp_server.INTERNAL_ERROR)
        self.assertEqual(
            response["error"]["data"]["missing_path_capabilities"],
            ["scope[0]"])

    def test_positionals_keep_their_declaration_order(self):
        """`required` preserves it; sorted `properties` keys do not."""
        payload = self.envelope(
            "echo_tool", {"second": "SECOND", "first": "FIRST"})["stdout_json"]

        self.assertEqual(payload["argv"][:2], ["FIRST", "SECOND"])

    def test_a_missing_workspace_argument_is_refused_before_execution(self):
        server = started(self.dist)

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"first": "a", "second": "b"},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertEqual(
            response["error"]["data"]["required_workspace_argument"],
            "root")

    def test_a_different_root_cannot_replace_the_session_binding(self):
        server = started(self.dist)
        with tempfile.TemporaryDirectory() as outside:
            response = request(server, "tools/call", {
                "name": "echo_tool",
                "arguments": {"root": outside, "first": "a",
                              "second": "b"},
            })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("resolve exactly", response["error"]["message"])

    def test_a_typed_path_cannot_escape_the_bound_workspace(self):
        server = started(self.dist)

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b",
                          "scope": "../outside"},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertEqual(response["error"]["data"]["argument"], "scope")

    def test_two_active_arguments_cannot_alias_one_consumption_identity(self):
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        echo["inputSchema"]["properties"]["other"] = _string(
            "second scoped path", "--other", path_access="read")
        distribution = SyntheticDistribution(projection=projection)
        self.addCleanup(distribution.cleanup)
        (distribution.workspace / "note.md").write_text(
            "admitted", encoding="utf-8")
        server = started(distribution)

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {
                "root": ".", "first": "a", "second": "b",
                "scope": "note.md", "other": "note.md",
            },
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertEqual(
            {response["error"]["data"]["argument"],
             response["error"]["data"]["aliased_argument"]},
            {"scope", "other"})
        self.assertEqual(response["error"]["data"]["consumption"],
                         "snapshot")

    def test_a_symlink_cannot_redirect_a_typed_path_outside(self):
        server = started(self.dist)
        with tempfile.TemporaryDirectory() as outside:
            link = self.dist.workspace / "redirect"
            link.symlink_to(outside, target_is_directory=True)
            response = request(server, "tools/call", {
                "name": "echo_tool",
                "arguments": {"root": ".", "first": "a", "second": "b",
                              "scope": "redirect/file.md"},
            })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertEqual(response["error"]["data"]["argument"], "scope")

    def test_an_in_workspace_symlink_is_still_not_a_canonical_artifact(self):
        server = started(self.dist)
        (self.dist.workspace / "real").mkdir()
        (self.dist.workspace / "alias").symlink_to(
            self.dist.workspace / "real", target_is_directory=True)

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b",
                          "scope": "alias/page.md"},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("symlink", response["error"]["message"])

    def test_a_multiply_linked_file_is_not_a_unique_workspace_artifact(self):
        server = started(self.dist)
        source = self.dist.workspace / "source.md"
        source.write_text("source", encoding="utf-8")
        os.link(str(source), str(self.dist.workspace / "alias.md"))

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b",
                          "scope": "alias.md"},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("multiply-linked", response["error"]["message"])

    def test_a_typed_path_must_use_repository_relative_canonical_spelling(self):
        server = started(self.dist)

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b",
                          "scope": str(self.dist.workspace / "kernel")},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("repository-relative", response["error"]["message"])

    def test_an_exact_path_constraint_refuses_an_alternate_artifact(self):
        _distribution, server = self.server_with_scope_capability(
            "exact", "Card")

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b",
                          "scope": "kernel/Other"},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertEqual(response["error"]["data"]["expected"],
                         "Card")

    def test_an_exact_registered_path_cannot_be_a_symlink(self):
        distribution, server = self.server_with_scope_capability(
            "exact", "Card")
        (distribution.workspace / "alternate-cards").mkdir()
        (distribution.workspace / "Card").symlink_to(
            "alternate-cards", target_is_directory=True)

        response = request(server, "tools/call", {
            "name": "echo_tool",
                          "arguments": {"root": ".", "first": "a", "second": "b",
                          "scope": "Card"},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("symlink", response["error"]["message"])

    def test_an_omitted_path_default_is_still_capability_checked(self):
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        scope = echo["inputSchema"]["properties"]["scope"]
        scope["default"] = "Card"
        scope[mcp_server.PATH_EXTENSION_KEY] = {
            "access": "read-write", "consumption": "transaction",
            "constraint": "exact",
            "value": "Card", "suffixes": [],
            "active_when_any": [], "inactive_when_any": [],
        }
        distribution = SyntheticDistribution(projection=projection)
        self.addCleanup(distribution.cleanup)
        (distribution.workspace / "alternate-cards").mkdir()
        (distribution.workspace / "Card").symlink_to(
            "alternate-cards", target_is_directory=True)
        server = started(distribution)

        response = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b"},
        })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("symlink", response["error"]["message"])

    def test_a_declared_mode_can_make_an_omitted_output_inactive(self):
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        scope = echo["inputSchema"]["properties"]["scope"]
        scope["default"] = "reports/result.md"
        scope[mcp_server.PATH_EXTENSION_KEY] = {
            "access": "read-write", "consumption": "transaction",
            "constraint": "contained", "value": None, "suffixes": [],
            "active_when_any": [], "inactive_when_any": ["apply"],
        }
        distribution = SyntheticDistribution(projection=projection)
        self.addCleanup(distribution.cleanup)
        server = started(distribution)

        envelope = self.envelope(
            "echo_tool",
            {"first": "a", "second": "b", "apply": True},
            server=server)

        self.assertIn("--apply", envelope["stdout_json"]["argv"])
        self.assertNotIn("--scope", envelope["stdout_json"]["argv"])
        self.assertEqual(envelope["path_capability_assurance"],
                         "descriptor-retained")
        self.assertEqual(envelope["consumed_path_capabilities"], [])

    def test_a_default_output_activates_only_in_its_declared_write_mode(self):
        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        scope = echo["inputSchema"]["properties"]["scope"]
        scope["default"] = "reports/result.md"
        scope[mcp_server.PATH_EXTENSION_KEY] = {
            "access": "write", "consumption": "replace",
            "constraint": "contained", "value": None, "suffixes": [],
            "active_when_any": ["apply"], "inactive_when_any": [],
        }
        distribution = SyntheticDistribution(projection=projection)
        self.addCleanup(distribution.cleanup)
        server = started(distribution)

        dry_run = self.envelope(
            "echo_tool", {"first": "a", "second": "b"}, server=server)
        write_run = self.envelope(
            "echo_tool", {"first": "a", "second": "b", "apply": True},
            server=server)

        self.assertNotIn("--scope", dry_run["stdout_json"]["argv"])
        self.assertEqual(dry_run["consumed_path_capabilities"], [])
        self.assertIn("--scope", write_run["stdout_json"]["argv"])
        self.assertEqual(write_run["consumed_path_capabilities"],
                         ["scope[0]"])

    def test_a_namespace_constraint_requires_namespace_and_suffix(self):
        _distribution, server = self.server_with_scope_capability(
            "namespace", ".cambium/receipts", [".jsonl"])
        common = {"root": ".", "first": "a", "second": "b"}

        outside = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": dict(common, scope="README.jsonl"),
        })
        wrong_suffix = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": dict(
                common, scope=".cambium/receipts/ready.yaml"),
        })
        accepted = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": dict(
                common, scope=".cambium/receipts/ready.jsonl"),
        })

        self.assertEqual(outside["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertEqual(wrong_suffix["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("result", accepted, accepted)

    def test_a_gap_in_the_positionals_is_refused_rather_than_rebound(self):
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "echo_tool",
                            "arguments": {"root": ".",
                                          "second": "SECOND"}})

        self.assertEqual(response["error"]["code"], mcp_server.INVALID_PARAMS)
        self.assertEqual(response["error"]["data"]["missing"], "first")

    def test_options_render_by_declared_action(self):
        payload = self.envelope("echo_tool", {
            "first": "a", "second": "b",
            "scope": "kernel",
            "apply": True,
            "exclude": ["docs", "profiles"],
            "count": 15,
        })["stdout_json"]

        argv = payload["argv"]
        self.assertEqual(argv[:2], ["a", "b"])
        self.assertIn("--apply", argv)
        self.assertEqual(argv[argv.index("--scope") + 1], "kernel")
        self.assertEqual(argv[argv.index("--count") + 1], "15")
        self.assertEqual([argv[i + 1] for i, token in enumerate(argv)
                          if token == "--exclude"], ["docs", "profiles"])

    def test_a_false_flag_writes_nothing(self):
        payload = self.envelope("echo_tool", {
            "first": "a", "second": "b", "apply": False})["stdout_json"]

        self.assertNotIn("--apply", payload["argv"])

    def test_json_is_appended_for_every_tool_that_declares_it(self):
        payload = self.envelope("echo_tool",
                                {"first": "a", "second": "b"})["stdout_json"]

        self.assertEqual(payload["argv"][-1], "--json")

    def test_a_caller_supplied_json_is_reported_as_ignored(self):
        envelope = self.envelope("echo_tool",
                                 {"first": "a", "second": "b", "json": False})

        self.assertEqual(envelope["transport_owned_arguments_ignored"],
                         ["json"])
        self.assertEqual(envelope["stdout_json"]["argv"][-1], "--json")

    def test_an_undeclared_argument_is_refused(self):
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "echo_tool",
                            "arguments": {"root": ".", "first": "a",
                                          "second": "b",
                                          "not_a_real_argument": "x"}})

        self.assertEqual(response["error"]["code"], mcp_server.INVALID_PARAMS)
        self.assertEqual(response["error"]["data"]["undeclared"],
                         ["not_a_real_argument"])

    def test_a_value_that_cannot_be_rendered_onto_argv_is_refused(self):
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "echo_tool",
                            "arguments": {"root": ".", "first": {"a": 1},
                                          "second": "b"}})

        self.assertEqual(response["error"]["code"], mcp_server.INVALID_PARAMS)

    def test_an_unknown_tool_is_refused(self):
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "not_a_tool", "arguments": {}})

        self.assertEqual(response["error"]["code"], mcp_server.INVALID_PARAMS)
        self.assertIn("no such tool", response["error"]["message"])

    def test_the_child_is_the_interpreter_running_this_server(self):
        envelope = self.envelope("echo_tool", {"first": "a", "second": "b"})

        self.assertEqual(envelope["argv"][0], mcp_server.interpreter())
        self.assertTrue(envelope["argv"][1].endswith("echo_tool.py"))

    def test_one_mcp_session_injects_one_stable_execution_context(self):
        server = started(self.dist)

        first = self.envelope(
            "echo_tool", {"first": "a", "second": "b"},
            server=server)["stdout_json"]["execution_context"]
        second = self.envelope(
            "echo_tool", {"first": "c", "second": "d"},
            server=server)["stdout_json"]["execution_context"]
        other = self.envelope(
            "echo_tool", {"first": "e", "second": "f"})[
                "stdout_json"]["execution_context"]

        self.assertTrue(first.startswith("mcp:"), first)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)


class SeamTests(SyntheticCase):
    """§1.4: the kernel's answer arrives as the kernel's answer."""

    def call(self, name, arguments=None):
        server = started(self.dist)
        response = request(server, "tools/call",
                           {"name": name,
                            "arguments": arguments or {"root": "."}})
        self.assertIn("result", response, response)
        return response["result"]

    def test_exit_zero_is_a_clean_success(self):
        result = self.call("clean_tool")

        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertEqual(result["structuredContent"]["verdict"], "clean")
        self.assertFalse(result["isError"])

    def test_exit_one_is_not_split_into_failure_or_unreliable(self):
        """One code covers two outcomes; only the tool knows which."""
        result = self.call("fail_tool")

        self.assertEqual(result["structuredContent"]["exit_code"], 1)
        self.assertEqual(result["structuredContent"]["verdict"],
                         "failed_or_unreliable")

    def test_exit_two_is_reported_as_hold(self):
        result = self.call("hold_tool")

        self.assertEqual(result["structuredContent"]["exit_code"], 2)
        self.assertEqual(result["structuredContent"]["verdict"], "hold")

    def test_exit_two_is_never_mapped_onto_success_or_failure(self):
        hold = self.call("hold_tool")["structuredContent"]
        clean = self.call("clean_tool")["structuredContent"]
        failed = self.call("fail_tool")["structuredContent"]

        self.assertNotEqual(hold["verdict"], clean["verdict"])
        self.assertNotEqual(hold["verdict"], failed["verdict"])
        self.assertNotIn(hold["verdict"], ("clean", "failed_or_unreliable"))

    def test_the_hold_text_never_calls_the_run_a_success_or_a_failure(self):
        text = self.call("hold_tool")["content"][0]["text"].lower()

        for word in ("success", "succeeded", "failure", "failed", "error"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)
        self.assertIn("verdict=hold", text)

    def test_the_verdict_is_read_from_a_field_not_from_the_report(self):
        result = self.call("hold_tool")

        self.assertEqual(result["structuredContent"]["verdict_source"],
                         "process exit code")

    def test_the_hold_report_reaches_the_caller_verbatim(self):
        result = self.call("hold_tool")

        self.assertIn("3 candidate(s) a person must read",
                      result["structuredContent"]["report"])

    def test_a_hold_is_not_rewritten_into_a_jsonrpc_error(self):
        """A refusal is a result carrying a verdict, never a protocol fault."""
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "hold_tool", "arguments": {"root": "."}})

        self.assertNotIn("error", response)
        self.assertIn("result", response)

    def test_an_undefined_exit_code_is_reported_as_unreadable(self):
        result = self.call("odd_tool")

        self.assertEqual(result["structuredContent"]["exit_code"], 9)
        self.assertEqual(result["structuredContent"]["verdict"], "unreadable")
        self.assertIn("no defined meaning",
                      result["content"][0]["text"])

    def test_the_receipts_of_a_held_run_still_arrive(self):
        result = self.call("hold_tool")

        self.assertEqual(result["structuredContent"]["stdout_json"],
                         [{"receipt_id": "r-hold"}])

    def test_a_tool_without_json_keeps_its_stdout_report(self):
        """Several real tools emit no receipts and report on stdout."""
        result = self.call("silent_tool")
        envelope = result["structuredContent"]

        self.assertEqual(envelope["stdout_parse"], "not_requested")
        self.assertEqual(envelope["stdout_text"].strip(),
                         "silent_tool --check: one product is stale")
        self.assertIn("one product is stale", result["content"][0]["text"])

    def test_a_tool_without_json_is_not_asked_for_it(self):
        result = self.call("silent_tool")

        self.assertNotIn("--json", result["structuredContent"]["argv"])

    def test_a_hold_on_stdout_is_still_read_as_a_hold(self):
        envelope = self.call("silent_tool")["structuredContent"]

        self.assertEqual(envelope["exit_code"], 2)
        self.assertEqual(envelope["verdict"], "hold")


class UnparseableOutputTests(SyntheticCase):
    """Reporting "I could not read this" is always available."""

    def envelope(self):
        server = started(self.dist)
        response = request(server, "tools/call",
                           {"name": "noise_tool", "arguments": {"root": "."}})
        return response["result"]

    def test_unparseable_stdout_is_named_as_such(self):
        envelope = self.envelope()["structuredContent"]

        self.assertEqual(envelope["stdout_parse"], "unparseable")
        self.assertIn("not JSON", envelope["stdout_parse_error"])

    def test_no_result_is_invented_from_unparseable_stdout(self):
        envelope = self.envelope()["structuredContent"]

        self.assertNotIn("stdout_json", envelope)

    def test_the_raw_bytes_travel_verbatim(self):
        envelope = self.envelope()["structuredContent"]

        self.assertEqual(envelope["stdout_text"].strip(),
                         "this is not JSON at all")

    def test_the_caller_is_told_in_the_text_content_too(self):
        text = self.envelope()["content"][0]["text"]

        self.assertIn("could not be parsed", text)
        self.assertIn("nothing has been inferred from it", text)

    def test_the_exit_code_is_still_read_as_the_verdict(self):
        """Unreadable stdout does not make the exit code unreadable."""
        envelope = self.envelope()["structuredContent"]

        self.assertEqual(envelope["exit_code"], 0)
        self.assertEqual(envelope["verdict"], "clean")


# ---------------------------------------------------------------------------
# Protocol edges
# ---------------------------------------------------------------------------


class ProtocolTests(SyntheticCase):
    def test_an_unknown_method_is_method_not_found(self):
        server = started(self.dist)

        for method in ("resources/list", "prompts/list", "completion/complete",
                       "server/discover", "nonsense"):
            with self.subTest(method=method):
                response = request(server, method)

                self.assertEqual(response["error"]["code"],
                                 mcp_server.METHOD_NOT_FOUND)
                self.assertEqual(response["error"]["data"]["method"], method)

    def test_a_modern_discover_probe_gets_a_non_modern_error(self):
        """So a dual-era client falls back to the handshake we do speak."""
        server = started(self.dist)

        response = request(server, "server/discover")

        self.assertEqual(response["error"]["code"],
                         mcp_server.METHOD_NOT_FOUND)
        self.assertNotEqual(response["error"]["code"], -32022)

    def test_ping_answers_an_empty_result(self):
        server = started(self.dist)

        self.assertEqual(request(server, "ping")["result"], {})

    def test_an_unknown_notification_is_never_answered(self):
        """JSON-RPC 2.0 permits no response to a notification at all."""
        server = started(self.dist)

        response = mcp_server.handle_message(
            server, {"jsonrpc": "2.0", "method": "notifications/nonsense"})

        self.assertIsNone(response)

    def test_a_batch_array_is_an_invalid_request(self):
        server = started(self.dist)

        response = mcp_server.handle_message(server, [{"jsonrpc": "2.0"}])

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_REQUEST)

    def test_a_message_without_a_method_is_an_invalid_request(self):
        server = started(self.dist)

        response = mcp_server.handle_message(
            server, {"jsonrpc": "2.0", "id": 7})

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_REQUEST)
        self.assertEqual(response["id"], 7)

    def test_a_wrong_jsonrpc_version_is_an_invalid_request(self):
        server = started(self.dist)

        response = mcp_server.handle_message(
            server, {"jsonrpc": "1.0", "id": 8, "method": "ping"})

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_REQUEST)

    def test_invalid_json_on_the_wire_is_a_parse_error(self):
        import io

        stdout = io.StringIO()
        mcp_server.serve(io.StringIO("{ not json\n"), stdout,
                         self.dist.server())

        response = json.loads(stdout.getvalue())
        self.assertEqual(response["error"]["code"], mcp_server.PARSE_ERROR)
        self.assertIsNone(response["id"])

    def test_every_response_carries_its_request_id(self):
        server = started(self.dist)

        for message_id in (1, "abc", 99):
            with self.subTest(id=message_id):
                response = request(server, "ping", message_id=message_id)

                self.assertEqual(response["id"], message_id)

    def test_only_one_line_is_written_per_response(self):
        import io

        stdout = io.StringIO()
        mcp_server.serve(
            io.StringIO(
                json.dumps({"jsonrpc": "2.0", "id": 1,
                            "method": "initialize", "params": INITIALIZE})
                + "\n"
                + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
                + "\n"),
            stdout, self.dist.server())

        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual([json.loads(line)["id"] for line in lines], [1, 2])


# ---------------------------------------------------------------------------
# The shipped server, driven as a host would drive it
# ---------------------------------------------------------------------------


class LiveStdioTests(unittest.TestCase):
    """One real round trip: the shipped file, a pipe, and a real tool."""

    def drive(self, messages, env_overrides=None):
        env = dict(os.environ)
        env[mcp_server.WORKSPACE_ENV] = str(REPO_ROOT)
        env.setdefault("TMPDIR", "/private/tmp")
        for key, value in (env_overrides or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        completed = subprocess.run(
            [sys.executable, str(SERVER_SOURCE)],
            input="".join(json.dumps(m) + "\n" for m in messages),
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return [json.loads(line)
                for line in completed.stdout.splitlines() if line.strip()]

    def test_a_full_session_over_a_pipe(self):
        responses = self.drive([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": INITIALIZE},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "check_moc", "arguments": {"root": "."}}},
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        ])

        # The initialized notification produced no line of its own.
        self.assertEqual([response["id"] for response in responses],
                         [1, 2, 3, 4])
        self.assertEqual(responses[0]["result"]["protocolVersion"],
                         "2025-11-25")
        artifact = json.loads(
            (TOOLS / "compiled/mcp-tools.json").read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(row["name"] for row in responses[1]["result"]["tools"]),
            sorted(tool["name"] for tool in artifact["tools"]))
        envelope = responses[2]["result"]["structuredContent"]
        self.assertEqual(envelope["tool"], "check_moc")
        self.assertIn(envelope["verdict"], mcp_server.VERDICTS.values())
        self.assertEqual(envelope["stdout_parse"], "parsed")
        self.assertEqual(responses[3]["error"]["code"],
                         mcp_server.METHOD_NOT_FOUND)

    def test_the_shipped_server_refuses_an_unbound_launch(self):
        responses = self.drive(
            [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": INITIALIZE}],
            env_overrides={mcp_server.WORKSPACE_ENV: None})

        self.assertEqual(responses[0]["error"]["code"], mcp_server.NOT_BOUND)

    def test_the_shipped_server_takes_no_command_line_arguments(self):
        completed = subprocess.run(
            [sys.executable, str(SERVER_SOURCE), "."],
            input="", capture_output=True, text=True, cwd=str(REPO_ROOT))

        self.assertEqual(completed.returncode, 1)
        self.assertIn("takes no command-line arguments", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_stdout_carries_json_rpc_and_nothing_else(self):
        env = dict(os.environ)
        env[mcp_server.WORKSPACE_ENV] = str(REPO_ROOT)
        completed = subprocess.run(
            [sys.executable, str(SERVER_SOURCE)],
            input=json.dumps({"jsonrpc": "2.0",
                              "method": "notifications/nonsense"}) + "\n"
                  + json.dumps({"jsonrpc": "2.0", "method":
                                "notifications/initialized"}) + "\n",
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))

        self.assertEqual(completed.stdout, "")
        self.assertIn("ignored notification", completed.stderr)


if __name__ == "__main__":
    unittest.main()
