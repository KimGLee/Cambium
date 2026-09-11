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
import argparse
import importlib.util
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
import Tools.platform.repository.path_admission as path_admission  # noqa: E402
from Tools.tests.support.canonical_registry_fixture import (  # noqa: E402
    install_isolated_tool_registry_bundle,
)
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
            mcp_server.HOST_BOUNDARY_EXTENSION_KEY: False,
            mcp_server.WORKSPACE_EXTENSION_KEY: {
                "argument": "root", "access": "read"},
            mcp_server.OUTPUT_EXTENSION_KEY: {
                "mode": "text" if name == "silent_tool" else "json-option",
                "result_contract": "tool-payload",
                "json_argument": None if name == "silent_tool" else "json",
                "json_value": None if name == "silent_tool" else True,
                "json_inactive_when_any": [],
                "json_types": [] if name == "silent_tool" else ["object"] if name == "echo_tool" else ["array"],
                "required_keys": [],
                "empty_exit_codes": [1],
                "empty_success_disabled_by": [],
            },
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
            checkpoint_root = Path(production_checkpoint)
            for source in checkpoint_root.rglob("*"):
                if not source.is_file():
                    continue
                target = self.root / source.relative_to(checkpoint_root)
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
            "Tools.platform.repository.path_admission",
            "Tools.platform.common",
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
            "tempfile", "uuid", "contextlib", "py_compile", "Tools",
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
                {"name": entry["name"], "schema": entry["inputSchema"],
                 "output": entry[mcp_server.OUTPUT_EXTENSION_KEY]},
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

        with mcp_server._prepared_imports(self.dist.root):
            prepared_prefix = mcp_server._CAMBIUM_PYCACHE_PREFIX
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
            prepared_prefix,
            payload["pycache_prefix"])
        self.assertTrue(payload["dont_write_bytecode"])
        self.assertFalse(local_cache.exists())
        self.assertFalse(Path(prepared_prefix).exists())

    def test_prepared_code_reexecutes_defaults_and_checks_content_not_mtime(self):
        source = (self.dist.root / "Tools/import_probe.py").resolve()
        external = source.with_suffix(".txt")
        source.write_text(
            "from pathlib import Path\nvalue = 1\n"
            "external = Path(__file__).with_suffix('.txt').read_text()\n")
        external.write_text("first")
        initial = source.stat()
        previous_prefix = mcp_server._CAMBIUM_PYCACHE_PREFIX

        def execute_module():
            spec = importlib.util.spec_from_file_location("import_probe", source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.value, module.external

        with mcp_server._prepared_imports(self.dist.root):
            prefix = Path(mcp_server._CAMBIUM_PYCACHE_PREFIX)
            self.assertEqual(0o700, prefix.stat().st_mode & 0o777)
            self.assertNotIn(self.dist.root, prefix.parents)
            artifact = Path(importlib.util.cache_from_source(str(source)))
            bytecode = artifact.read_bytes()
            self.assertEqual(3, int.from_bytes(bytecode[4:8], "little"))
            self.assertEqual((1, "first"), execute_module())
            external.write_text("second")
            self.assertEqual((1, "second"), execute_module())
            source.write_text(source.read_text().replace("value = 1", "value = 2"))
            os.utime(source, ns=(initial.st_atime_ns, initial.st_mtime_ns))
            self.assertEqual(initial.st_size, source.stat().st_size)
            self.assertEqual((2, "second"), execute_module())
            # The stale code object is not rewritten or interpreted as a
            # validation result; a source miss executes the new bytes.
            self.assertEqual(bytecode, artifact.read_bytes())
        self.assertFalse(prefix.exists())
        self.assertEqual(previous_prefix, mcp_server._CAMBIUM_PYCACHE_PREFIX)

    def test_optional_import_preparation_failure_and_exception_cleanup(self):
        previous = (mcp_server._CAMBIUM_PYCACHE_PREFIX, sys.pycache_prefix,
                    os.environ.get("PYTHONPYCACHEPREFIX"))
        with mock.patch.object(mcp_server.tempfile, "TemporaryDirectory",
                               side_effect=PermissionError("unavailable")):
            with mcp_server._prepared_imports(self.dist.root):
                self.assertEqual(previous[0], mcp_server._CAMBIUM_PYCACHE_PREFIX)
        with mock.patch.object(mcp_server.py_compile, "compile",
                               side_effect=OSError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "stdio failure"):
                with mcp_server._prepared_imports(self.dist.root):
                    prefix = Path(mcp_server._CAMBIUM_PYCACHE_PREFIX)
                    self.assertTrue(prefix.is_dir())
                    self.assertFalse(list(prefix.rglob("*.pyc")))
                    raise RuntimeError("stdio failure")
        self.assertFalse(prefix.exists())
        self.assertEqual(previous, (mcp_server._CAMBIUM_PYCACHE_PREFIX,
                         sys.pycache_prefix, os.environ.get("PYTHONPYCACHEPREFIX")))

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
            ("missing-output", lambda doc: doc["tools"][0].pop(mcp_server.OUTPUT_EXTENSION_KEY), "output contract"),
            ("missing-host-boundary", lambda doc: doc["tools"][0].pop(mcp_server.HOST_BOUNDARY_EXTENSION_KEY), "boolean Host boundary"),
            ("nonboolean-host-boundary", lambda doc: doc["tools"][0].__setitem__(mcp_server.HOST_BOUNDARY_EXTENSION_KEY, "true"), "boolean Host boundary"),
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
            ({"second": "SECOND"}, {"fields": ["first"]}),
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

    def test_argparse_roundtrip_preserves_omission_null_and_empty_values(self):
        from Tools.platform.agent_interface import agent_interface_contract as interface
        from Tools.platform.agent_interface import compile_cli_contract as compiler
        from Tools.tests.support.mcp_stdio_session import MCPStdioSession
        parser = argparse.ArgumentParser()
        interface.nullable_argument(parser.add_argument("--reason"))
        parser.add_argument("--scope", action="append")
        parser.add_argument("--refs", action="extend", nargs="*", default=None)
        parser.add_argument("--tags", action="append", default=[])
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument("--apply", action="store_true")
        cli = {"tool": "shape", "arguments": compiler.describe_arguments(TOOLS.parent, parser)}
        schema = cli_argv_renderer.schema_from_compiled_tool(cli)
        driver = MCPStdioSession(REPO_ROOT)
        driver.tools = {"shape": {"inputSchema": schema}}
        cases = (({}, {"reason": None, "refs": None, "scope": None}),
                 ({"reason": None, "refs": []}, {"reason": None, "refs": []}),
                 ({"reason": "null", "refs": ["one", "two"], "tags": [], "limit": 0, "apply": False},
                  {"reason": "null", "refs": ["one", "two"], "tags": [], "limit": 0, "apply": False}),
                 ({"reason": "", "apply": True}, {"reason": "", "apply": True}),
                 ({"reason": "--statement", "refs": ["--ref", "plain"], "limit": -1},
                  {"reason": "--statement", "refs": ["--ref", "plain"], "limit": -1}))
        for supplied, expected in cases:
            with self.subTest(supplied=supplied):
                argv, _ = cli_argv_renderer.build_argv("shape", schema, supplied)
                result = vars(parser.parse_args(argv))
                for field, value in expected.items():
                    self.assertEqual(value, result[field])
                # The E2E host adapter must consume the same expression
                # contract, without starting a lifecycle to test conversion.
                with mock.patch.object(driver, "call", return_value={
                        "stdout_parse": "parsed", "stdout_json": {},
                        "exit_code": 0, "output_reliable": True,
                        "invocation_reliable": True}) as dispatch:
                    driver.run_cli("shape.py", *argv)
                transported = dispatch.call_args.args[1]
                restored, _ = cli_argv_renderer.build_argv("shape", schema, transported)
                self.assertEqual(result, vars(parser.parse_args(restored)))
        for invalid in ({"scope": []}, {"scope": None}, {"reason": 4}, {"limit": False},
                        {"refs": "one"}, {"apply": 0}, {"unknown": None}):
            with self.subTest(keys=sorted(invalid)), self.assertRaises(cli_argv_renderer.ArgvRenderError):
                cli_argv_renderer.build_argv("shape", schema, invalid)
        # Merely being optional with a None default does not authorize null.
        with self.assertRaises(ValueError):
            interface.nullable_argument(parser.add_argument("--required", required=True))


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
                    path_admission.capability_is_active(
                        capability, arguments),
                    expected)


class PathCapabilityUnitTests(unittest.TestCase):
    """The path-capability owner, without MCP transport or a child process."""

    def test_snapshot_roles_share_exact_physical_reads_and_acknowledgements(self):
        from Tools.platform.common import kblib
        for directory in (False, True):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                target = root / "input"
                target.mkdir() if directory else None
                file = target / "record.jsonl" if directory else target
                file.write_bytes(b'{"receipt_id":"current"}\n')
                prop = _string("role", "--role", path_access="read")
                tool = {"name": "shared-input", "workspace_argument": "root", "schema": {
                    "properties": {"root": _string("root"), "first": prop, "second": prop}}}
                args = {"root": str(root), "first": target.name, "second": target.name}
                fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    with path_admission.invocation(tool, args, str(root), fd, os.environ) as binding:
                        with mock.patch.dict(os.environ, binding["env"], clear=True), \
                                mock.patch.object(path_capability, "_MANIFEST_CACHE", None), \
                                mock.patch.object(path_capability, "_ACKNOWLEDGED", set()), \
                                mock.patch.object(path_capability, "_TREE_BYTES", {}), \
                                mock.patch.object(path_capability, "_TREE_METADATA", {}), \
                                mock.patch.object(path_capability, "_TREE_SNAPSHOTS", {}):
                            self.assertEqual(file.read_bytes(), kblib.read_bytes(file))
                            self.assertEqual(file.read_bytes(), kblib.read_bytes(file))
                            original = path_capability.records()
                            for field, value in (
                                    ("target_ino", original[1]["target_ino"] + 1),
                                    ("parent_ino", original[1]["parent_ino"] + 1),
                                    ("target_fd", None), ("kind", "missing"),
                                    ("exists", False), ("consumption", "append")):
                                rows = [dict(row) for row in original]
                                rows[1][field] = value
                                with self.subTest(mismatched=field), \
                                        mock.patch.object(path_capability, "records", return_value=rows), \
                                        self.assertRaisesRegex(ValueError, "ambiguous"):
                                    path_capability.inherited_capability(target)
                    self.assertEqual([], binding["missing"])
                    self.assertEqual(2, len(binding["acknowledged"]))
                finally:
                    os.close(fd)

    def test_receipt_observation_uses_after_image_not_initial_existence_or_cache(self):
        from Tools.platform.common import kblib
        from Tools.execution.audit import audit_producer_runtime
        from Tools.execution.task_runtime.queue_runtime import receipts
        for existing, declared in ((False, True), (True, True), (False, False)):
            with self.subTest(existing=existing, declared=declared), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                target = root / ".cambium/receipts/observed.jsonl"
                target.parent.mkdir(parents=True)
                relative = target.relative_to(root).as_posix()
                if existing:
                    target.write_text('{"receipt_id":"old"}\n', encoding="utf-8")
                prior = target.read_bytes() if existing else b""
                prop = _string("register", "--receipts", path_access="write")
                prop[mcp_server.PATH_EXTENSION_KEY]["consumption"] = "append"
                tool = {"name": "receipt-owner", "workspace_argument": "root",
                        "schema": {"properties": {"root": _string("root"),
                                                  **({"receipts": prop} if declared else {})}}}
                args = {"root": str(root), **({"receipts": relative} if declared else {})}
                fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                advanced = {}
                try:
                    with path_admission.invocation(tool, args, str(root), fd, os.environ) as binding:
                        with mock.patch.dict(os.environ, binding["env"], clear=True), \
                                mock.patch.object(path_capability, "_MANIFEST_CACHE", None), \
                                mock.patch.object(path_capability, "_ADVANCED_TARGETS", advanced), \
                                mock.patch.object(path_capability, "_ACKNOWLEDGED", set()), \
                                mock.patch.object(path_capability, "_TREE_BYTES", {relative: (b"stale", None)}):
                            if not existing:
                                with self.assertRaises(receipts.ReceiptRegisterError):
                                    receipts.read_receipt_register(root, relative)
                            publication = kblib.ReceiptPublication()
                            receipt = {"receipt_id": "new"}
                            outcome, error, _ = publication.append(target, [receipt])
                            self.assertEqual("present", outcome)
                            self.assertIsNone(error)
                            self.assertTrue(publication.observation.content.startswith(prior))
                            rows = audit_producer_runtime.read_receipt_records(
                                target, observation=publication.observation)
                            self.assertEqual(receipt, rows[-1])
                            self.assertEqual(target.read_bytes(), kblib.read_receipt_bytes(target)[1])
                            self.assertEqual(receipt, receipts.read_receipt_register(root, relative)["new"])
                            if declared:
                                with self.assertRaises(ValueError):
                                    path_capability.inherited_capability(target, "snapshot")
                    self.assertEqual([], binding["missing"])
                finally:
                    for entry in advanced.values():
                        os.close(entry["fd"])
                    os.close(fd)

    def test_child_admission_cannot_widen_or_replace_inherited_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "input.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            prop = _string("input", "--scope", path_access="read")
            tool = {"name": "child", "workspace_argument": "root",
                    "schema": {"properties": {"root": _string("root"), "scope": prop}}}
            args = {"root": str(root), "scope": target.name}
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with path_admission.invocation(tool, args, str(root), fd, os.environ) as parent:
                    with mock.patch.dict(os.environ, parent["env"], clear=True), \
                            mock.patch.object(path_capability, "_MANIFEST_CACHE", None):
                        with path_capability.child_invocation(tool, args, str(root), fd, os.environ) as child:
                            self.assertNotEqual(parent["rows"][0]["capability_id"],
                                                child["rows"][0]["capability_id"])
                        prop[mcp_server.PATH_EXTENSION_KEY]["consumption"] = "append"
                        with self.assertRaises(path_admission.PathAdmissionError):
                            with path_capability.child_invocation(tool, args, str(root), fd, os.environ):
                                self.fail("mode escalation admitted")
                        prop[mcp_server.PATH_EXTENSION_KEY]["consumption"] = "snapshot"
                        replacement = root / "replacement"
                        replacement.write_text("{}\n", encoding="utf-8")
                        replacement.replace(target)
                        with self.assertRaises(path_admission.PathAdmissionError):
                            with path_capability.child_invocation(tool, args, str(root), fd, os.environ):
                                self.fail("replacement admitted")
            finally:
                os.close(fd)

    def test_nested_read_settles_only_consumed_parent_inputs(self):
        from Tools.platform.common import kblib
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("input", "other"):
                (root / name).write_text(name)
            prop = _string("input", "--input", path_access="read")
            tool = {"name": "parent", "workspace_argument": "root", "schema": {
                "properties": {"root": _string("root"), "input": prop, "other": prop}}}
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with path_admission.invocation(tool, {"root": str(root), "input": "input", "other": "other"},
                                               str(root), fd, os.environ) as parent:
                    with mock.patch.dict(os.environ, parent["env"], clear=True), \
                            mock.patch.object(path_capability, "_MANIFEST_CACHE", None), \
                            mock.patch.object(path_capability, "_ACKNOWLEDGED", set()):
                        with path_capability.child_invocation(tool, {"root": str(root), "input": "input"},
                                                               str(root), fd, os.environ) as child:
                            with mock.patch.dict(os.environ, child["env"], clear=True), \
                                    mock.patch.object(path_capability, "_MANIFEST_CACHE", None), \
                                    mock.patch.object(path_capability, "_ACKNOWLEDGED", set()):
                                self.assertEqual("input", kblib.read_text(root / "input"))
                        self.assertEqual([], child["missing"])
                self.assertEqual([parent["rows"][1]["capability_id"]], parent["missing"])
            finally:
                os.close(fd)

    def test_delegation_does_not_complete_unread_writes_subtrees_or_bad_ack(self):
        from Tools.platform.common import kblib
        cases = ("unread", "subtree", "transaction", "append", "replace", "alias", "foreign", "partial")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                (root / "tree").mkdir()
                (root / "tree/input").write_text("payload")
                prop = _string("input", "--input", path_access="read")
                if case in ("transaction", "append", "replace"):
                    prop[mcp_server.PATH_EXTENSION_KEY].update(access="write", consumption=case)
                parent_tool = {"name": "parent", "workspace_argument": "root", "schema": {
                    "properties": {"root": _string("root"), "input": prop, "alias": prop}}}
                parent_args = {"root": str(root), "input": "tree" if case == "subtree" else "tree/input"}
                if case == "alias":
                    parent_args["alias"] = "tree/input"
                child_prop = _string("input", "--input", path_access="read")
                child_tool = {"name": "child", "workspace_argument": "root", "schema": {
                    "properties": {"root": _string("root"), "input": child_prop}}}
                fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    with path_admission.invocation(parent_tool, parent_args, str(root), fd, os.environ) as parent:
                        with mock.patch.dict(os.environ, parent["env"], clear=True), \
                                mock.patch.object(path_capability, "_MANIFEST_CACHE", None), \
                                mock.patch.object(path_capability, "_ACKNOWLEDGED", set()):
                            if case in ("append", "replace"):
                                with self.assertRaises(path_admission.PathAdmissionError):
                                    with path_capability.child_invocation(child_tool, {"root": str(root), "input": "tree/input"},
                                                                           str(root), fd, os.environ):
                                        self.fail("write scope admitted as a snapshot")
                            else:
                                with path_capability.child_invocation(child_tool, {"root": str(root), "input": "tree/input"},
                                                                       str(root), fd, os.environ) as child:
                                    with mock.patch.dict(os.environ, child["env"], clear=True), \
                                            mock.patch.object(path_capability, "_MANIFEST_CACHE", None), \
                                            mock.patch.object(path_capability, "_ACKNOWLEDGED", set()):
                                        if case not in ("unread", "partial"):
                                            self.assertEqual("payload", kblib.read_text(root / "tree/input"))
                                        ack_fd = int(child["env"][mcp_server.agent_interface_contract.PATH_CAPABILITIES_ACK_ENV])
                                        if case == "foreign":
                                            os.write(ack_fd, b"foreign\n")
                                        if case == "partial":
                                            os.write(ack_fd, child["rows"][0]["capability_id"].encode())
                                self.assertEqual(case in ("foreign", "partial"), bool(child["acknowledgement_error"]))
                    self.assertEqual(0 if case == "alias" else 1, len(parent["missing"]))
                finally:
                    os.close(fd)

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
    each security scenario. Build the Python and machine-contract checkpoint
    once, then give every scenario a private copy and workspace. The tests
    still cross the real process boundary; they no longer reconstruct the
    same distribution closure for every scenario.
    """

    @classmethod
    def setUpClass(cls):
        cls._production_checkpoint = tempfile.TemporaryDirectory()
        module_boundary_facts.stage_shipped_modules(
            str(REPO_ROOT), cls._production_checkpoint.name,
            ["platform.common.kblib"])
        install_isolated_tool_registry_bundle(
            cls._production_checkpoint.name)

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
        (admitted / "profile.toml").write_text("manifest", encoding="utf-8")
        (admitted / "slot.md").write_text("admitted", encoding="utf-8")
        displaced = distribution.workspace / "profile-admitted"
        outside = Path(self.dist._tmp.name) / "outside-profile"
        outside.mkdir()
        (outside / "profile.toml").write_text("outside", encoding="utf-8")
        (outside / "slot.md").write_text("outside", encoding="utf-8")

        def mutate():
            admitted.rename(displaced)
            admitted.symlink_to(outside, target_is_directory=True)

        with self._swap_during_spawn(mutate):
            response = self.call(server, "profile/profile.toml")

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
        self.assertTrue(payload["error"])
        self.assertEqual(
            {"receipt_id": "r1"},
            json.loads((receipts / "displaced.jsonl.displaced").read_text(
                encoding="utf-8")),
        )

    @catalog_effects(process_calls=3)
    def test_independent_nested_scopes_propagate_only_real_reads_through_hold(self):
        child_contract = {"name": "nested", "workspace_argument": "root", "schema": {
            "properties": {"root": _string("root"),
                           "scope": _string("scope", "--scope", path_access="read")}}}
        source = self.reader_source(
            "import os,sys\n"
            "from Tools.platform.repository import path_capability\n"
            "depth=2 if a.count is None else a.count\n"
            "if depth:\n"
            " tool=" + repr(child_contract) + "\n"
            " root=os.environ['CAMBIUM_WORKSPACE_ROOT']\n"
            " with path_capability.child_invocation(tool,{'root':root,'scope':a.scope},"
            "root,path_capability.controlled_root_fd(),os.environ) as binding:\n"
            "  c=kblib.run_cambium_subprocess([sys.executable,__file__,a.first,a.second,"
            "'--root',root,'--scope',a.scope,'--count',str(depth-1)],"
            "path_binding=binding,text=True,capture_output=True,check=False)\n"
            " print(json.dumps({'missing':binding['missing'],'ack_error':binding['acknowledgement_error'],"
            "'child':json.loads(c.stdout)}))\n"
            " sys.exit(c.returncode)\n"
            "print(json.dumps({'read':kblib.read_text(a.scope)}))\n"
            "sys.exit(2)\n")
        distribution, server = self.distribution_for(source, "read", "snapshot")
        (distribution.workspace / "input.txt").write_text("real input")
        response = self.call(server, "input.txt")["result"]
        envelope = response["structuredContent"]
        self.assertTrue(envelope["invocation_reliable"], envelope)
        self.assertTrue(envelope["output_reliable"], envelope)
        self.assertEqual(2, envelope["exit_code"])
        self.assertEqual({"missing": [], "ack_error": None, "child": {
            "missing": [], "ack_error": None, "child": {"read": "real input"}}}, envelope["stdout_json"])

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

        self.assertTrue(response["result"]["isError"])
        envelope = response["result"]["structuredContent"]
        self.assertEqual(0, envelope["exit_code"])
        self.assertFalse(envelope["invocation_reliable"])
        self.assertIn("ignored", envelope["stdout_json"])
        self.assertEqual(
            [value.rsplit(":", 1)[-1] for value in
             envelope["missing_path_capabilities"]],
            ["scope[0]"])


class PathCapabilityAdmissionContractTests(ArgvTests):
    """Path admission and result wiring without lifecycle reconstruction."""

    def admitted_records(self, server, arguments):
        records, descriptors = path_admission.admit_paths(
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

    def test_write_arguments_cannot_alias_one_consumption_identity(self):
        for access, mode in (("write", "append"), ("write", "replace"),
                             ("read-write", "transaction")):
            with self.subTest(mode=mode):
                prop = _string("write role", "--role", path_access=access)
                prop[mcp_server.PATH_EXTENSION_KEY]["consumption"] = mode
                tool = {"name": "write-alias", "workspace_argument": "root", "schema": {
                    "properties": {"root": _string("root"), "first": prop, "second": prop}}}
                fd = os.open(self.dist.workspace, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    with self.assertRaises(path_admission.PathAdmissionError) as caught:
                        path_admission.admit_paths(tool, {
                            "root": str(self.dist.workspace), "first": "note.md", "second": "note.md"},
                            str(self.dist.workspace), fd)
                    self.assertEqual(mode, caught.exception.data["consumption"])
                finally:
                    os.close(fd)

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
        self.assertEqual([value.rsplit(":", 1)[-1] for value in
                          write_run["consumed_path_capabilities"]],
                         ["scope[0]"])

    def test_a_namespace_constraint_requires_namespace_and_suffix(self):
        _distribution, server = self.server_with_scope_capability(
            "namespace", ".cambium/receipts", [".jsonl"])
        common = {"root": ".", "first": "a", "second": "b"}

        for scope in ("README.jsonl", ".cambium/receipts/ready.yaml"):
            with self.subTest(scope=scope), \
                    self.assertRaises(path_admission.PathAdmissionError) as caught:
                self.admitted_records(server, dict(common, scope=scope))
            self.assertEqual(caught.exception.data["argument"], "scope")
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

    def call(self, name, arguments=None, completion=None, output=None,
             host_boundary=False):
        server = started(self.dist)
        server.projection["by_name"][name]["host_environment_boundary"] = host_boundary
        if output is not None:
            server.projection["by_name"][name]["output"] = output
        code, stdout, stderr = completion or self.COMPLETIONS[name]
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
        self.assertFalse(envelope["output_reliable"])
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("could not be parsed", text)
        self.assertIn("nothing has been inferred from it", text)

    def test_declared_output_shapes_and_publication_facts_are_independent_of_exit(self):
        contract = dict(fake_projection()["tools"][0][mcp_server.OUTPUT_EXTENSION_KEY])
        contract.update(mode="always-json", json_argument=None, json_value=None,
                        json_types=["object"], required_keys=["status"],
                        empty_exit_codes=[])
        for raw, reliable in (("{}", False), ("[]", False), ("", False),
                              ('{"status":"recorded"}', True)):
            with self.subTest(raw=raw):
                result = self.call("clean_tool", completion=(0, raw, ""), output=contract)
                self.assertEqual(reliable, result["structuredContent"]["output_reliable"])
                self.assertEqual(not reliable, result["isError"])
                self.assertEqual(0, result["structuredContent"]["exit_code"])
        contract.update(result_contract="receipt-publication")
        payload = {"applied": True, "status": "recorded", "errors": [],
                   "result": "fail", "verdict": "changes-required",
                   "publication": {"append": "present", "record_confirmation": "confirmed", "reused": False}}
        result = self.call("clean_tool", completion=(1, json.dumps(payload), ""), output=contract)
        self.assertTrue(result["structuredContent"]["output_reliable"])
        self.assertEqual(payload, result["structuredContent"]["stdout_json"])
        self.assertTrue(result["isError"])
        payload["applied"] = False
        result = self.call("clean_tool", completion=(0, json.dumps(payload), ""), output=contract)
        self.assertFalse(result["structuredContent"]["output_reliable"])
        self.assertTrue(result["isError"])
        payload.update(applied=None, status="uncertain")
        payload["publication"].update(append="uncertain", record_confirmation="unconfirmed")
        result = self.call("clean_tool", completion=(0, json.dumps(payload), ""), output=contract)
        self.assertEqual("parsed", result["structuredContent"]["stdout_parse"])
        self.assertEqual(payload, result["structuredContent"]["stdout_json"])
        self.assertFalse(result["structuredContent"]["output_reliable"])
        self.assertTrue(result["isError"])
        contract.update(result_contract="tool-payload", empty_exit_codes=[0])
        result = self.call("clean_tool", completion=(0, "", "dry run"), output=contract)
        self.assertTrue(result["structuredContent"]["output_reliable"])
        self.assertEqual("empty", result["structuredContent"]["stdout_parse"])
        contract.update(empty_exit_codes=[0, 1],
                        empty_success_disabled_by=["apply", "apply_replan"])
        for arguments, code, reliable in (
                ({}, 0, True), ({"apply": False}, 0, True),
                ({"apply": True}, 0, False),
                ({"apply_replan": True}, 0, False),
                ({"apply": True}, 1, True), ({}, 2, False)):
            with self.subTest(arguments=arguments, exit_code=code):
                observed = mcp_server.agent_interface_contract.decode_output(
                    contract, b"", code, arguments)
                self.assertEqual(reliable, observed["output_reliable"])

    def test_declared_host_handoff_keeps_diagnosis_across_output_shapes(self):
        from Tools.platform.common import host_environment

        error = host_environment.HostEnvironmentUnavailable(
            "renderer unavailable", capability_id="static-markdown-render-v1",
            code="runtime-unavailable", constructs=["mermaid"])
        payload = host_environment.host_handoff(
            error.diagnostic(), prior_output="prior step returned\n")
        receipt_contract = dict(fake_projection()["tools"][0][mcp_server.OUTPUT_EXTENSION_KEY])
        receipt_contract.update(mode="always-json", json_argument=None,
                                json_value=None, json_types=["object"],
                                required_keys=["applied", "status"],
                                result_contract="receipt-publication")
        for name, output in (("clean_tool", receipt_contract),
                             ("clean_tool", None), ("silent_tool", None)):
            with self.subTest(tool=name, output=output):
                result = self.call(
                    name, completion=(1, json.dumps(payload), ""),
                    output=output, host_boundary=True)
                envelope = result["structuredContent"]
                self.assertEqual("parsed", envelope["stdout_parse"])
                self.assertEqual(payload, envelope["stdout_json"])
                self.assertFalse(envelope["output_reliable"])
                self.assertTrue(result["isError"])
                self.assertEqual(1, envelope["exit_code"])
        rejected = self.call(
            "clean_tool", completion=(0, json.dumps(payload), ""),
            output=receipt_contract, host_boundary=False)
        self.assertEqual("unparseable", rejected["structuredContent"]["stdout_parse"])
        self.assertFalse(rejected["structuredContent"]["output_reliable"])
        self.assertTrue(rejected["isError"])


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
        from Tools.tests.support.mcp_stdio_session import MCPStdioSession
        responses = []
        with MCPStdioSession(REPO_ROOT, env_overrides=env_overrides) as session:
            for message in messages:
                if "id" in message:
                    responses.append(session.request(message["method"], message.get("params")))
                else:
                    session.notify(message["method"], message.get("params"))
        self.assertEqual(0, session.process.returncode, list(session.diagnostics))
        return responses

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
        self.assertIn(envelope["verdict"], mcp_server.agent_interface_contract.PROCESS_VERDICTS.values())
        self.assertEqual(envelope["stdout_parse"], "parsed")
        self.assertEqual(responses[3]["error"]["code"],
                         mcp_server.METHOD_NOT_FOUND)

if __name__ == "__main__":
    unittest.main()
