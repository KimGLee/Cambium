"""The MCP public wrapper and its layer-3 owner stay separate.

The top-level ``Tools/mcp_server.py`` owns only process bootstrap and delegates
through its implementation marker.  The transport behavior lives at
``Tools/platform/agent_interface/mcp_server.py``; layer assertions inspect
that owner rather than mistaking the wrapper for the implementation.

Three properties are worth more than the rest and each has its own class:

  * the transport imports no judgment module, checked statically on the
    source bytes so it cannot be edited away quietly;
  * the tool list is the compiled artifact and not a recomputation of it;
  * a tool's exit code arrives as the verdict it is -- 2 in particular is
    never rendered as a success or as a failure, and output the server
    cannot parse is reported as unparseable rather than resolved into a
    result.

Contract cases run against parsed state or completed-process objects from a
synthetic distribution.  Real child processes are reserved for descriptor
isolation, workspace binding, and one end-to-end stdio session.  That keeps
the verdict table exact without turning every result branch into another
transport test.
"""

import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS.parent
SERVER_SOURCE = TOOLS / "mcp_server.py"
OWNER_SERVER_SOURCE = TOOLS / "platform/agent_interface/mcp_server.py"

DISTRIBUTION_IMPORT_PROLOGUE = (
    "import os, sys\n"
    "sys.path.insert(0, os.path.dirname(os.path.dirname("
    "os.path.abspath(__file__))))\n"
)

sys.path.insert(0, str(TOOLS))
import Tools.platform.agent_interface.cli_argv_renderer as cli_argv_renderer  # noqa: E402
import Tools.platform.agent_interface.mcp_server as mcp_server  # noqa: E402
import Tools.execution.task_runtime.runtime_paths as runtime_paths  # noqa: E402
import Tools.platform.distribution.module_boundary_facts as module_boundary_facts  # noqa: E402
import Tools.platform.repository.path_capability as path_capability  # noqa: E402
from Tools.tests.support.test_effects import catalog_effects  # noqa: E402


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
        "'CAMBIUM_EXECUTION_CONTEXT_ID'),\n"
        "                  'pycache_prefix': sys.pycache_prefix,\n"
        "                  'dont_write_bytecode': "
        "sys.dont_write_bytecode}))\n"
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
        "projection_target": mcp_server.SOURCE_DISTRIBUTION_TARGET,
        "schema_version": mcp_server.PROJECTION_SCHEMA_VERSION,
        "tool_count": len(tools),
        "tools": tools,
        "transports": ["stdio", "streamable-http"],
    }


class SyntheticDistribution(object):
    """A distribution root holding only the fake tools and a projection."""

    def __init__(self, projection=None, tool_sources=None,
                 production_roots=(), production_checkpoint=None):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "dist"
        (self.root / "Tools" / "compiled").mkdir(parents=True)
        self.workspace = Path(self._tmp.name) / "corpus"
        self.workspace.mkdir()
        for name, source in (tool_sources or FAKE_TOOLS).items():
            target = self.root / "Tools" / ("%s.py" % name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        if production_checkpoint is not None:
            checkpoint_tools = Path(production_checkpoint) / "Tools"
            for source in checkpoint_tools.rglob("*"):
                if not source.is_file():
                    continue
                target = self.root / "Tools" / source.relative_to(
                    checkpoint_tools)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        elif production_roots:
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
        self.source = OWNER_SERVER_SOURCE.read_text(encoding="utf-8")
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

    def test_transport_imports_only_registered_platform_dependencies(self):
        imported = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name for alias in node.names
                    if alias.name.startswith("Tools."))
            elif isinstance(node, ast.ImportFrom) and node.module and \
                    node.module.startswith("Tools."):
                imported.add(node.module)

        self.assertEqual({
            "Tools.execution.task_runtime.runtime_paths",
            "Tools.platform.agent_interface.cli_argv_renderer",
            "Tools.platform.agent_interface.agent_interface_contract",
            "Tools.platform.repository.repository",
        }, imported)
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
        allowed = {
            "hashlib", "json", "os", "stat", "subprocess", "sys", "traceback",
            "tempfile", "uuid", "Tools",
        }

        self.assertEqual(self.imported_module_names() - allowed, set())
        dodges = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = (func.attr if isinstance(func, ast.Attribute)
                        else getattr(func, "id", ""))
                if name in ("__import__", "import_module", "exec", "eval"):
                    dodges.add(name)

        self.assertEqual(sorted(dodges), [])

    def test_shared_renderer_is_transport_neutral_and_rpc_adapted(self):
        source = (TOOLS / "platform/agent_interface/cli_argv_renderer.py").\
            read_text(encoding="utf-8")
        self.assertNotIn("RpcError", source)
        self.assertNotIn("INVALID_PARAMS", source)
        entry = next(row for row in fake_projection()["tools"]
                     if row["name"] == "echo_tool")
        error = cli_argv_renderer.ArgvRenderError(
            "cannot render fixture", {"argument": "first"})
        with mock.patch.object(
                cli_argv_renderer, "build_argv", side_effect=error), \
                self.assertRaises(mcp_server.RpcError) as caught:
            mcp_server.build_argv(
                {"name": entry["name"], "schema": entry["inputSchema"]},
                {"first": "a", "second": "b"})
        self.assertEqual(mcp_server.INVALID_PARAMS, caught.exception.code)
        self.assertEqual({"argument": "first"}, caught.exception.data)

class WrapperBoundaryTests(unittest.TestCase):
    """The stable public path owns bootstrap, never transport policy."""

    def setUp(self):
        self.source = SERVER_SOURCE.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_wrapper_has_one_owner_and_only_bootstrap_dependencies(self):
        imported = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertEqual({"os", "runpy", "sys", "tempfile"}, imported)
        markers = [
            node.value.value
            for node in self.tree.body
            if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and
                target.id == "IMPLEMENTATION_MODULE"
                for target in node.targets) and
            isinstance(node.value, ast.Constant) and
            isinstance(node.value.value, str)
        ]
        delegations = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and
            isinstance(node.func, ast.Attribute) and
            isinstance(node.func.value, ast.Name) and
            node.func.value.id == "runpy" and
            node.func.attr == "run_module"
        ]
        self.assertEqual(
            ["Tools.platform.agent_interface.mcp_server"], markers)
        self.assertEqual(1, len(delegations))
        self.assertIsInstance(delegations[0].args[0], ast.Name)
        self.assertEqual("IMPLEMENTATION_MODULE",
                         delegations[0].args[0].id)


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------


class InitializeTests(SyntheticCase):
    def test_response_and_version_negotiation_are_closed(self):
        response = request(self.dist.server(), "initialize", INITIALIZE)

        result = response["result"]
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(result["protocolVersion"], "2025-11-25")
        self.assertEqual(result["capabilities"], {"tools": {}})
        self.assertEqual(result["serverInfo"]["name"], "cambium")
        self.assertEqual(result["serverInfo"]["version"],
                         mcp_server.SERVER_VERSION)
        self.assertNotIn("listChanged", result["capabilities"]["tools"])
        for version in mcp_server.SUPPORTED_PROTOCOL_VERSIONS:
            with self.subTest(version=version):
                response = request(self.dist.server(), "initialize",
                                   dict(INITIALIZE, protocolVersion=version))

                self.assertEqual(response["result"]["protocolVersion"],
                                 version)
        response = request(self.dist.server(), "initialize",
                           dict(INITIALIZE, protocolVersion="1900-01-01"))
        self.assertEqual(response["result"]["protocolVersion"],
                         mcp_server.LATEST_PROTOCOL_VERSION)

class BindingTests(SyntheticCase):
    """`CAMBIUM_WORKSPACE_ROOT` or a clean refusal; never a cwd fallback."""

    def refusal(self, **overrides):
        response = request(self.dist.server(**overrides), "initialize",
                           INITIALIZE)
        self.assertIn("error", response, response)
        return response["error"]

    def test_invalid_workspace_bindings_fail_closed_without_cwd_fallback(self):
        cases = (
            (None, "host configuration must set it", True),
            ("   ", "host configuration must set it", True),
            ("<CAMBIUM_WORKSPACE_ROOT>", "not an absolute path", False),
            (".", "not an absolute path", False),
            (str(self.dist.root / "absent"),
             "not an existing directory", False),
        )
        for value, message, names_fallback in cases:
            with self.subTest(value=value):
                error = self.refusal(**{mcp_server.WORKSPACE_ENV: value})
                self.assertEqual(error["code"], mcp_server.NOT_BOUND)
                self.assertIn(message, error["message"])
                if names_fallback:
                    self.assertIn("no working-directory fallback",
                                  error["message"])
        self.assertEqual(error["data"]["variable"],
                         "CAMBIUM_WORKSPACE_ROOT")

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

    @catalog_effects(process_calls=1)
    def test_child_receives_bound_root_and_transport_owned_python_settings(self):
        local_cache = self.dist.root / "Tools/__pycache__/host-controlled"
        server = started(
            self.dist,
            PYTHONPYCACHEPREFIX=str(local_cache),
            PYTHONDONTWRITEBYTECODE="0")

        result = request(server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b"},
        })["result"]

        payload = result["structuredContent"]["stdout_json"]
        self.assertEqual(os.path.realpath(payload["cwd"]),
                         os.path.realpath(str(self.dist.workspace)))
        self.assertEqual(payload["workspace"],
                         os.path.realpath(str(self.dist.workspace)))
        self.assertEqual(
            mcp_server._CAMBIUM_PYCACHE_PREFIX,
            payload["pycache_prefix"])
        self.assertTrue(payload["dont_write_bytecode"])
        self.assertFalse(local_cache.exists())

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

    @catalog_effects(process_calls=1)
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

    def test_unusable_projection_inputs_fail_initialize(self):
        setup_cases = (
            ("missing", lambda dist: dist.projection_path.unlink(), None),
            ("unparseable", lambda dist: dist.projection_path.write_text(
                "{ not json", encoding="utf-8"), "not parseable JSON"),
        )
        for label, setup, message in setup_cases:
            with self.subTest(case=label):
                broken = SyntheticDistribution()
                self.addCleanup(broken.cleanup)
                setup(broken)
                response = request(
                    broken.server(), "initialize", INITIALIZE)
                self.assertEqual(
                    response["error"]["code"],
                    mcp_server.UNRELIABLE_EVIDENCE)
                if message:
                    self.assertIn(message, response["error"]["message"])

        mutations = (
            ("artifact", lambda doc: doc.__setitem__(
                "artifact", "something-else"), None),
            ("count", lambda doc: doc.__setitem__("tool_count", 99), None),
            ("phantom", lambda doc: (
                doc["tools"].append({
                    "description": "not shipped",
                    "inputSchema": {"properties": {}, "type": "object"},
                    "name": "phantom_tool",
                }),
                doc.__setitem__("tool_count", len(doc["tools"])))),
        )
        for case in mutations:
            label, mutate = case[:2]
            expected = case[2] if len(case) > 2 else "phantom_tool"
            with self.subTest(case=label):
                error = self.error_for(mutate)
                self.assertEqual(
                    error["code"], mcp_server.UNRELIABLE_EVIDENCE)
                if expected:
                    self.assertIn(expected, error["message"])

    def test_a_failed_initialize_leaves_no_tool_list_behind(self):
        self.dist.projection_path.unlink()
        server = self.dist.server()
        request(server, "initialize", INITIALIZE)

        response = request(server, "tools/list")

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_REQUEST)

    def test_source_projection_requires_and_honors_its_exact_hash_binding(self):
        response = request(
            self.dist.server(
                **{mcp_server.SOURCE_HASH_ENV: "sha256:" + "0" * 64}),
            "initialize", INITIALIZE)

        self.assertEqual(response["error"]["code"],
                         mcp_server.UNRELIABLE_EVIDENCE)
        self.assertIn("registered against", response["error"]["message"])
        digest = mcp_server.sha256_of(self.dist.projection_path.read_bytes())

        response = request(
            self.dist.server(**{mcp_server.SOURCE_HASH_ENV: digest}),
            "initialize", INITIALIZE)

        self.assertIn("result", response)

        foreign = self.dist.workspace / "foreign.json"
        foreign.write_text(json.dumps(fake_projection()), encoding="utf-8")
        response = request(
            self.dist.server(**{
                mcp_server.PROJECTION_PATH_ENV: str(foreign)}),
            "initialize", INITIALIZE)
        self.assertEqual(response["error"]["code"],
                         mcp_server.UNRELIABLE_EVIDENCE)
        self.assertIn(mcp_server.SOURCE_HASH_ENV,
                      response["error"]["message"])

        digest = mcp_server.sha256_of(foreign.read_bytes())
        response = request(
            self.dist.server(**{
                mcp_server.PROJECTION_PATH_ENV: str(foreign),
                mcp_server.SOURCE_HASH_ENV: digest}),
            "initialize", INITIALIZE)
        self.assertIn("result", response, response)

    def carried_projection(self, **overrides):
        path = self.dist.workspace / runtime_paths.MCP_TOOLS_ARTIFACT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tools = self.dist.workspace / "Tools"
        tools.mkdir(exist_ok=True)
        for name, source in FAKE_TOOLS.items():
            (tools / (name + ".py")).write_text(source, encoding="utf-8")
        document = fake_projection()
        document["projection_target"] = mcp_server.CARRIED_RUNTIME_TARGET
        document.update(overrides)
        path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        return path

    def test_carried_projection_is_bound_to_its_exact_adopter_location(self):
        path = self.carried_projection()
        digest = mcp_server.sha256_of(path.read_bytes())

        response = request(
            mcp_server.Server(
                distribution_root=str(self.dist.workspace),
                environ=self.dist.environ(**{
                    mcp_server.PROJECTION_PATH_ENV: str(path),
                    mcp_server.SOURCE_HASH_ENV: digest})),
            "initialize", INITIALIZE)

        self.assertIn("result", response, response)

        response = request(
            self.dist.server(**{
                mcp_server.PROJECTION_PATH_ENV: str(path),
                mcp_server.SOURCE_HASH_ENV: digest}),
            "initialize", INITIALIZE)

        self.assertEqual(response["error"]["code"],
                         mcp_server.UNRELIABLE_EVIDENCE)
        self.assertIn("may execute only the Tools carried",
                      response["error"]["message"])

        foreign = self.dist.workspace / "host-selected-projection.json"
        foreign.write_bytes(path.read_bytes())
        digest = mcp_server.sha256_of(foreign.read_bytes())

        response = request(
            mcp_server.Server(
                distribution_root=str(self.dist.workspace),
                environ=self.dist.environ(**{
                    mcp_server.PROJECTION_PATH_ENV: str(foreign),
                    mcp_server.SOURCE_HASH_ENV: digest})),
            "initialize", INITIALIZE)

        self.assertEqual(response["error"]["code"],
                         mcp_server.UNRELIABLE_EVIDENCE)
        self.assertIn("registered workspace artifact",
                      response["error"]["message"])


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


class ArgvRenderingContractTests(unittest.TestCase):
    """Pure compiled-schema to argv behavior; no MCP process is involved."""

    @staticmethod
    def tool():
        entry = next(row for row in fake_projection()["tools"]
                     if row["name"] == "echo_tool")
        return {"name": entry["name"], "schema": entry["inputSchema"]}

    def test_declared_order_actions_and_transport_owned_json_render_once(self):
        tool = self.tool()
        argv, ignored = cli_argv_renderer.build_argv(
            tool["name"], tool["schema"], {
            "second": "SECOND", "first": "FIRST", "scope": "kernel",
            "apply": True, "exclude": ["docs", "profiles"], "count": 15,
            "json": False,
            }, transport_owned_argument="json",
            transport_owned_flag="--json")
        self.assertEqual(["FIRST", "SECOND"], argv[:2])
        self.assertIn("--apply", argv)
        self.assertEqual("kernel", argv[argv.index("--scope") + 1])
        self.assertEqual("15", argv[argv.index("--count") + 1])
        self.assertEqual(
            ["docs", "profiles"],
            [argv[i + 1] for i, token in enumerate(argv)
             if token == "--exclude"])
        self.assertEqual("--json", argv[-1])
        self.assertEqual(["json"], ignored)

        without_flag, _ = cli_argv_renderer.build_argv(
            tool["name"], tool["schema"],
            {"first": "a", "second": "b", "apply": False},
            transport_owned_argument="json",
            transport_owned_flag="--json")
        self.assertNotIn("--apply", without_flag)

    def test_unrenderable_argument_shapes_share_one_typed_refusal(self):
        cases = (
            ({"second": "SECOND"}, {"missing": "first"}),
            ({"first": "a", "second": "b", "unknown": "x"},
             {"undeclared": ["unknown"]}),
            ({"first": {"a": 1}, "second": "b"}, None),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments), \
                    self.assertRaises(
                        cli_argv_renderer.ArgvRenderError) as caught:
                tool = self.tool()
                cli_argv_renderer.build_argv(
                    tool["name"], tool["schema"], arguments,
                    transport_owned_argument="json",
                    transport_owned_flag="--json")
            if expected:
                for key, value in expected.items():
                    self.assertEqual(value, caught.exception.data[key])


class PathActivationContractTests(unittest.TestCase):
    def test_path_activation_is_one_closed_predicate(self):
        cases = (
            ({"active_when_any": [], "inactive_when_any": []}, {}, True),
            ({"active_when_any": ["apply"], "inactive_when_any": []},
             {}, False),
            ({"active_when_any": ["apply"], "inactive_when_any": []},
             {"apply": True}, True),
            ({"active_when_any": [], "inactive_when_any": ["dry_run"]},
             {"dry_run": True}, False),
            ({"active_when_any": ["apply"],
              "inactive_when_any": ["blocked"]},
             {"apply": True, "blocked": True}, False),
        )
        for capability, arguments, expected in cases:
            with self.subTest(capability=capability, arguments=arguments):
                self.assertEqual(
                    mcp_server._path_capability_is_active(
                        capability, arguments),
                    expected)


class PathCapabilityUnitTests(unittest.TestCase):
    """The path-capability owner, without MCP transport or a child process."""

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

    def test_manifest_parser_rejects_noncurrent_or_incomplete_records(self):
        incomplete = {"schema_version": 1, "tool": "fixture",
                      "capabilities": [{"capability_id": "scope[0]"}]}
        unknown_mode = {
            "schema_version": 1,
            "tool": "fixture",
            "capabilities": [{
                "capability_id": "scope[0]", "argument": "scope",
                "value_index": 0, "spelling": "note.md", "access": "read",
                "consumption": "unsupported-read", "constraint": "contained",
                "exists": False, "kind": "missing", "target_fd": None,
                "parent_fd": None, "basename": "note.md",
                "missing_components": ["note.md"], "target_dev": None,
                "target_ino": None,
            }],
        }
        cases = ("{not-json", json.dumps({"schema_version": 0}),
                 json.dumps(incomplete), json.dumps(unknown_mode))
        for raw in cases:
            with self.subTest(raw=raw), \
                    mock.patch.object(path_capability, "_MANIFEST_CACHE", None), \
                    mock.patch.dict(os.environ, {
                        path_capability.PATH_CAPABILITIES_ENV: raw,
                    }, clear=False), self.assertRaises(ValueError):
                path_capability.records()

    def test_named_target_accepts_only_the_retained_unique_final_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            target = parent / "receipt.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            parent_fd = os.open(parent, os.O_RDONLY)
            target_fd = os.open(target, os.O_RDONLY)
            self.addCleanup(os.close, parent_fd)
            self.addCleanup(os.close, target_fd)
            parent_stat = os.fstat(parent_fd)
            target_stat = os.fstat(target_fd)
            capability = {
                "capability_id": "receipt[0]", "spelling": str(target),
                "consumption": "append", "parent_fd": parent_fd,
                "parent_dev": parent_stat.st_dev,
                "parent_ino": parent_stat.st_ino,
                "target_fd": target_fd, "target_dev": target_stat.st_dev,
                "target_ino": target_stat.st_ino,
                "basename": target.name,
            }

            path_capability.verify_named_target(capability, target)

            displaced = parent / "retained.jsonl"
            target.rename(displaced)
            target.write_text('{"foreign":true}\n', encoding="utf-8")
            with self.assertRaises(OSError):
                path_capability.verify_named_target(capability, target)

            target.unlink()
            displaced.rename(target)
            os.link(target, parent / "alias.jsonl")
            with self.assertRaises(OSError):
                path_capability.verify_named_target(capability, target)


class PathCapabilityIsolationTests(ArgvTests):
    """Descriptor-retention seams across a real child.

    Resolving the shipped dependency closure is a contract check, not part of
    each security scenario.  Build that four-file checkpoint once, then give
    every scenario a private copy and workspace.  The tests still cross the
    real process boundary; they no longer rerun the same global module scan.
    """

    @classmethod
    def setUpClass(cls):
        cls._production_checkpoint = tempfile.TemporaryDirectory()
        module_boundary_facts.stage_shipped_modules(
            str(REPO_ROOT), cls._production_checkpoint.name,
            ["platform.common.kblib"])

    @classmethod
    def tearDownClass(cls):
        cls._production_checkpoint.cleanup()

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
            production_checkpoint=self._production_checkpoint.name)
        self.addCleanup(distribution.cleanup)
        return distribution, started(distribution)

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
            DISTRIBUTION_IMPORT_PROLOGUE +
            "import argparse, json\n"
            "import Tools.platform.common.kblib as kblib\n"
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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
            DISTRIBUTION_IMPORT_PROLOGUE +
            "import json\n"
            "import Tools.platform.common.kblib as kblib\n"
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
            production_checkpoint=self._production_checkpoint.name)
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

    @catalog_effects(process_calls=1)
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

    @catalog_effects(process_calls=1)
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


class PathCapabilityAdmissionContractTests(ArgvTests):
    """Path admission and result wiring without lifecycle reconstruction."""

    def admitted_records(self, server, arguments):
        records, descriptors = mcp_server.enforce_workspace_capabilities(
            server.projection["by_name"]["echo_tool"], arguments,
            server.workspace_root, server.workspace_fd)
        for descriptor in descriptors:
            self.addCleanup(os.close, descriptor)
        return records

    @staticmethod
    def completed_child(argv, env, **_kwargs):
        manifest = json.loads(env[mcp_server.PATH_CAPABILITIES_ENV])
        acknowledge_fd = int(env[mcp_server.PATH_CAPABILITIES_ACK_ENV])
        for row in manifest["capabilities"]:
            os.write(acknowledge_fd,
                     (row["capability_id"] + "\n").encode("utf-8"))
        payload = {"argv": argv[2:]}
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")

    def test_calls_cannot_omit_or_replace_the_session_workspace(self):
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
        with tempfile.TemporaryDirectory() as outside:
            response = request(server, "tools/call", {
                "name": "echo_tool",
                "arguments": {"root": outside, "first": "a",
                              "second": "b"},
            })

        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("resolve exactly", response["error"]["message"])

    def test_typed_paths_require_contained_canonical_spelling(self):
        server = started(self.dist)
        cases = (
            ("../outside", None),
            (str(self.dist.workspace / "kernel"), "repository-relative"),
        )
        for spelling, message in cases:
            with self.subTest(spelling=spelling):
                response = request(server, "tools/call", {
                    "name": "echo_tool",
                    "arguments": {
                        "root": ".", "first": "a", "second": "b",
                        "scope": spelling,
                    },
                })
                self.assertEqual(
                    response["error"]["code"], mcp_server.INVALID_PARAMS)
                self.assertEqual(
                    response["error"]["data"]["argument"], "scope")
                if message:
                    self.assertIn(message, response["error"]["message"])

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

    def test_symlinks_are_never_canonical_path_capabilities(self):
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

        exact_distribution, exact_server = \
            self.server_with_scope_capability("exact", "Card")
        (exact_distribution.workspace / "alternate-cards").mkdir()
        (exact_distribution.workspace / "Card").symlink_to(
            "alternate-cards", target_is_directory=True)
        response = request(exact_server, "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b",
                          "scope": "Card"},
        })
        self.assertEqual(response["error"]["code"],
                         mcp_server.INVALID_PARAMS)
        self.assertIn("symlink", response["error"]["message"])

        projection = fake_projection()
        echo = next(tool for tool in projection["tools"]
                    if tool["name"] == "echo_tool")
        scope = echo["inputSchema"]["properties"]["scope"]
        scope["default"] = "Card"
        scope[mcp_server.PATH_EXTENSION_KEY] = {
            "access": "read-write", "consumption": "transaction",
            "constraint": "exact", "value": "Card", "suffixes": [],
            "active_when_any": [], "inactive_when_any": [],
        }
        default_distribution = SyntheticDistribution(projection=projection)
        self.addCleanup(default_distribution.cleanup)
        (default_distribution.workspace / "alternate-cards").mkdir()
        (default_distribution.workspace / "Card").symlink_to(
            "alternate-cards", target_is_directory=True)
        response = request(started(default_distribution), "tools/call", {
            "name": "echo_tool",
            "arguments": {"root": ".", "first": "a", "second": "b"},
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

    def test_default_paths_follow_their_declared_activation_mode(self):
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

        with mock.patch.object(
                mcp_server.subprocess, "run",
                side_effect=self.completed_child):
            envelope = self.envelope(
                "echo_tool",
                {"first": "a", "second": "b", "apply": True},
                server=server)

        self.assertIn("--apply", envelope["stdout_json"]["argv"])
        self.assertNotIn("--scope", envelope["stdout_json"]["argv"])
        self.assertEqual(envelope["path_capability_assurance"],
                         "descriptor-retained")
        self.assertEqual(envelope["consumed_path_capabilities"], [])
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

        with mock.patch.object(
                mcp_server.subprocess, "run",
                side_effect=self.completed_child):
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

        for scope in ("README.jsonl", ".cambium/receipts/ready.yaml"):
            with self.subTest(scope=scope), \
                    self.assertRaises(mcp_server.RpcError) as caught:
                self.admitted_records(server, dict(common, scope=scope))
            self.assertEqual(caught.exception.code, mcp_server.INVALID_PARAMS)
        records = self.admitted_records(
            server, dict(common, scope=".cambium/receipts/ready.jsonl"))
        self.assertEqual(["scope[0]"],
                         [row["capability_id"] for row in records])

    def test_an_unknown_tool_is_refused(self):
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "not_a_tool", "arguments": {}})

        self.assertEqual(response["error"]["code"], mcp_server.INVALID_PARAMS)
        self.assertIn("no such tool", response["error"]["message"])

    def test_one_mcp_session_injects_one_stable_execution_context(self):
        server = started(self.dist)
        other_server = started(self.dist)
        with mock.patch.object(
                mcp_server, "run_tool",
                return_value={"transport_probe": True}) as run:
            for active, first, second in (
                    (server, "a", "b"),
                    (server, "c", "d"),
                    (other_server, "e", "f")):
                response = request(active, "tools/call", {
                    "name": "echo_tool",
                    "arguments": {
                        "root": ".", "first": first, "second": second},
                })
                self.assertIn("result", response, response)
        contexts = [
            call.args[4][mcp_server.EXECUTION_CONTEXT_ENV]
            for call in run.call_args_list
        ]
        first, second, other = contexts

        self.assertTrue(first.startswith("mcp:"), first)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)


class SeamTests(SyntheticCase):
    """Process outcomes cross the transport without semantic rewriting.

    The real process seam is exercised once by ``LiveStdioTests``.  These
    table cases start from completed child results so every verdict and parse
    branch does not spawn another Python interpreter.
    """

    COMPLETIONS = {
        "clean_tool": (0, '[{"receipt_id": "r-clean"}]\n',
                       "clean_tool: nothing to report\n"),
        "fail_tool": (1, '[{"receipt_id": "r-fail"}]\n',
                      "fail_tool: one failure\n"),
        "hold_tool": (2, '[{"receipt_id": "r-hold"}]\n',
                      "hold_tool: 3 candidate(s) a person must read\n"),
        "noise_tool": (0, "this is not JSON at all\n",
                       "noise_tool: report\n"),
        "odd_tool": (9, "", ""),
        "silent_tool": (2, "silent_tool --check: one product is stale\n",
                        ""),
    }

    def call(self, name, arguments=None):
        server = started(self.dist)
        code, stdout, stderr = self.COMPLETIONS[name]
        completed = subprocess.CompletedProcess(
            [name], code, stdout=stdout.encode("utf-8"),
            stderr=stderr.encode("utf-8"))
        with mock.patch.object(
                mcp_server.subprocess, "run", return_value=completed):
            response = request(server, "tools/call",
                               {"name": name,
                                "arguments": arguments or {"root": "."}})
        self.assertIn("result", response, response)
        return response["result"]

    def test_exit_code_mapping_is_closed_and_preserves_tool_verdicts(self):
        expected = {
            "clean_tool": (0, "clean"),
            "fail_tool": (1, "failed_or_unreliable"),
            "hold_tool": (2, "hold"),
            "odd_tool": (9, "unreadable"),
        }
        for name, (code, verdict) in expected.items():
            with self.subTest(tool=name):
                result = self.call(name)
                envelope = result["structuredContent"]
                self.assertEqual(code, envelope["exit_code"])
                self.assertEqual(verdict, envelope["verdict"])
                if name == "hold_tool":
                    text = result["content"][0]["text"].lower()
                    self.assertEqual(
                        "process exit code", envelope["verdict_source"])
                    self.assertIn(
                        "3 candidate(s) a person must read",
                        envelope["report"])
                    self.assertEqual(
                        [{"receipt_id": "r-hold"}],
                        envelope["stdout_json"])
                    self.assertIn("verdict=hold", text)
                    for word in (
                            "success", "succeeded", "failure", "failed"):
                        self.assertNotIn(word, text)

    def test_text_and_unparseable_outputs_are_not_reinterpreted(self):
        result = self.call("silent_tool")
        envelope = result["structuredContent"]
        self.assertEqual("not_requested", envelope["stdout_parse"])
        self.assertNotIn("--json", envelope["argv"])
        self.assertEqual("silent_tool --check: one product is stale",
                         envelope["stdout_text"].strip())
        self.assertEqual((2, "hold"),
                         (envelope["exit_code"], envelope["verdict"]))

        result = self.call("noise_tool")
        envelope = result["structuredContent"]
        self.assertEqual("unparseable", envelope["stdout_parse"])
        self.assertIn("not JSON", envelope["stdout_parse_error"])
        self.assertNotIn("stdout_json", envelope)
        self.assertEqual("this is not JSON at all",
                         envelope["stdout_text"].strip())
        self.assertEqual((0, "clean"),
                         (envelope["exit_code"], envelope["verdict"]))
        text = result["content"][0]["text"]
        self.assertIn("could not be parsed", text)
        self.assertIn("nothing has been inferred from it", text)


# ---------------------------------------------------------------------------
# Protocol edges
# ---------------------------------------------------------------------------


class ProtocolTests(SyntheticCase):
    def test_request_dispatch_preserves_identity_and_refuses_unknown_methods(self):
        server = started(self.dist)

        for method in ("resources/list", "prompts/list", "completion/complete",
                       "server/discover", "nonsense"):
            with self.subTest(method=method):
                response = request(server, method)

                self.assertEqual(response["error"]["code"],
                                 mcp_server.METHOD_NOT_FOUND)
                self.assertEqual(response["error"]["data"]["method"], method)
        for message_id in (1, "abc", 99):
            with self.subTest(message_id=message_id):
                response = request(server, "ping", message_id=message_id)
                self.assertEqual({}, response["result"])
                self.assertEqual(message_id, response["id"])

    def test_notifications_are_never_answered(self):
        """JSON-RPC 2.0 permits no response to a notification at all."""
        server = started(self.dist)
        for method in ("notifications/initialized", "notifications/nonsense"):
            with self.subTest(method=method):
                response = mcp_server.handle_message(
                    server, {"jsonrpc": "2.0", "method": method})
                self.assertIsNone(response)

    def test_wire_framing_and_invalid_inputs_are_fail_closed(self):
        import io

        server = started(self.dist)
        messages = (
            [{"jsonrpc": "2.0"}],
            {"jsonrpc": "2.0", "id": 7},
            {"jsonrpc": "1.0", "id": 8, "method": "ping"},
        )
        for message in messages:
            with self.subTest(message=message):
                response = mcp_server.handle_message(server, message)
                self.assertEqual(mcp_server.INVALID_REQUEST,
                                 response["error"]["code"])

        stdout = io.StringIO()
        mcp_server.serve(io.StringIO("{ not json\n"), stdout,
                         self.dist.server())

        response = json.loads(stdout.getvalue())
        self.assertEqual(response["error"]["code"], mcp_server.PARSE_ERROR)
        self.assertIsNone(response["id"])

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

if __name__ == "__main__":
    unittest.main()
