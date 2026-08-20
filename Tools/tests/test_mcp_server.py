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


TOOLS = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS.parent
SERVER_SOURCE = TOOLS / "mcp_server.py"

sys.path.insert(0, str(TOOLS))
import mcp_server  # noqa: E402


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
        "print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(),\n"
        "                  'workspace': os.environ.get("
        "'CAMBIUM_WORKSPACE_ROOT')}))\n"
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


def _string(description, option=None):
    schema = {"description": description, "type": "string"}
    schema["x-cambium-cli"] = {
        "action": "store",
        "option_strings": [option] if option else [],
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
            properties["scope"] = _string("scoped path", "--scope")
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
        })
    return {
        "artifact": "agent-interface-projection",
        "form": "mcp",
        "schema_version": 1,
        "tool_count": len(tools),
        "tools": tools,
        "transports": ["stdio", "streamable-http"],
    }


class SyntheticDistribution(object):
    """A distribution root holding only the fake tools and a projection."""

    def __init__(self, projection=None, tool_sources=None):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "dist"
        (self.root / "Tools" / "compiled").mkdir(parents=True)
        self.workspace = Path(self._tmp.name) / "corpus"
        self.workspace.mkdir()
        for name, source in (tool_sources or FAKE_TOOLS).items():
            (self.root / "Tools" / ("%s.py" % name)).write_text(
                source, encoding="utf-8")
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
        allowed = {"hashlib", "json", "os", "subprocess", "sys", "traceback"}

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
                          "arguments": {"first": "a", "second": "b"}})["result"]

        payload = result["structuredContent"]["stdout_json"]
        self.assertEqual(os.path.realpath(payload["cwd"]),
                         os.path.realpath(str(self.dist.workspace)))
        self.assertEqual(payload["workspace"], str(self.dist.workspace))


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
        expected = [
            {"name": tool["name"], "description": tool["description"],
             "inputSchema": tool["inputSchema"]}
            for tool in document["tools"]
        ]

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
    def envelope(self, name, arguments, server=None):
        server = server or started(self.dist)
        response = request(server, "tools/call",
                           {"name": name, "arguments": arguments})
        self.assertIn("result", response, response)
        return response["result"]["structuredContent"]

    def test_positionals_keep_their_declaration_order(self):
        """`required` preserves it; sorted `properties` keys do not."""
        payload = self.envelope(
            "echo_tool", {"second": "SECOND", "first": "FIRST"})["stdout_json"]

        self.assertEqual(payload["argv"][:2], ["FIRST", "SECOND"])

    def test_a_gap_in_the_positionals_is_refused_rather_than_rebound(self):
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "echo_tool",
                            "arguments": {"second": "SECOND"}})

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
                            "arguments": {"first": "a", "second": "b",
                                          "not_a_real_argument": "x"}})

        self.assertEqual(response["error"]["code"], mcp_server.INVALID_PARAMS)
        self.assertEqual(response["error"]["data"]["undeclared"],
                         ["not_a_real_argument"])

    def test_a_value_that_cannot_be_rendered_onto_argv_is_refused(self):
        server = started(self.dist)

        response = request(server, "tools/call",
                           {"name": "echo_tool",
                            "arguments": {"first": {"a": 1}, "second": "b"}})

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
