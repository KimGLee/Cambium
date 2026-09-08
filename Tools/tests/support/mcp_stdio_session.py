"""One real, sequential stdio transport for MCP integration and E2E tests.

This driver supplies no governance fixture or verdict. It starts the shipped
server, waits for each JSON-RPC response before the next call, and preserves
the server's operation envelope. CLI-shaped scenario inputs are translated
using the actual tools/list projection, never a parallel argument registry.
"""

import argparse
from collections import deque
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from Tools.platform.agent_interface import agent_interface_contract as interface
from Tools.platform.agent_interface import cli_argv_renderer


TOOLS = Path(__file__).resolve().parents[2]
INITIALIZE = {
    "protocolVersion": "2025-11-25",
    "capabilities": {},
    "clientInfo": {"name": "cambium-lifecycle-test", "version": "1"},
}


class MCPStdioSession:
    """A bounded real host session, with one in-flight request at a time."""

    def __init__(self, workspace, *, server=None, timeout=120,
                 env_overrides=None):
        self.workspace = Path(workspace).resolve()
        self.server = Path(server or TOOLS / "mcp_server.py").resolve()
        self.timeout = timeout
        self.env_overrides = env_overrides or {}
        self.process = None
        self.responses = queue.Queue()
        self.diagnostics = deque(maxlen=200)
        self.next_id = 1
        self.tools = None
        self.calls = []

    def __enter__(self):
        environment = dict(os.environ)
        for key in (interface.PATH_CAPABILITIES_ENV,
                    interface.PATH_CAPABILITIES_ACK_ENV,
                    interface.WORKSPACE_FD_ENV,
                    interface.INTERFACE_SOURCE_HASH_ENV,
                    interface.INTERFACE_PROJECTION_ENV):
            environment.pop(key, None)
        environment[interface.WORKSPACE_ENV] = str(self.workspace)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for key, value in self.env_overrides.items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(self.server)],
            cwd=self.server.parent.parent, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self.readers = (
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        )
        for reader in self.readers:
            reader.start()
        return self

    def initialize(self, params=None):
        response = self.request("initialize", params or INITIALIZE)
        if "error" in response:
            raise AssertionError("MCP initialize failed: %s" % response)
        self.notify("notifications/initialized")
        return response

    def _read_stdout(self):
        try:
            for line in self.process.stdout:
                if line.strip():
                    self.responses.put(line)
        finally:
            self.responses.put(None)

    def _read_stderr(self):
        for line in self.process.stderr:
            self.diagnostics.append(line.rstrip())

    def _send(self, message):
        if self.process is None or self.process.poll() is not None:
            raise AssertionError("MCP server is not running: %s" %
                                 "\n".join(self.diagnostics))
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def notify(self, method, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def request(self, method, params=None):
        identity = self.next_id
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": identity, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)
        try:
            line = self.responses.get(timeout=self.timeout)
        except queue.Empty as exc:
            raise AssertionError(
                "MCP %s timed out after %ss; stderr: %s" %
                (method, self.timeout, "\n".join(self.diagnostics))) from exc
        if line is None:
            raise AssertionError("MCP ended before %s: %s" %
                                 (method, "\n".join(self.diagnostics)))
        response = json.loads(line)
        if response.get("id") != identity:
            raise AssertionError("MCP response ID differs: %s" % response)
        return response

    def call(self, name, arguments):
        response = self.request(
            "tools/call", {"name": name, "arguments": arguments})
        self.calls.append({"name": name, "response": response})
        if "error" in response:
            raise AssertionError("MCP %s transport error: %s" %
                                 (name, response["error"]))
        return response["result"]["structuredContent"]

    def _tool(self, name):
        if self.tools is None:
            response = self.request("tools/list")
            if "error" in response:
                raise AssertionError("MCP tools/list failed: %s" % response)
            self.tools = {tool["name"]: tool
                          for tool in response["result"]["tools"]}
        if name not in self.tools:
            raise AssertionError("scenario operation is not exposed: %s" % name)
        return self.tools[name]

    def run_cli(self, filename, *argv):
        """Reuse a scenario's inputs while executing only the real MCP path."""
        name = Path(filename).stem
        schema = self._tool(name)["inputSchema"]
        parser = argparse.ArgumentParser(add_help=False)
        properties = schema["properties"]
        positionals = cli_argv_renderer.positional_order(schema)
        names = positionals + [key for key in properties
                               if key not in positionals]
        for key in names:
            specification = properties[key]
            metadata = cli_argv_renderer.cli_metadata(specification)
            options = metadata.get("option_strings") or []
            settings = {"default": argparse.SUPPRESS}
            action = metadata.get("action", "store")
            if action != "store":
                settings["action"] = action
            if action not in {"store_true", "store_false", "count"}:
                # Parse CLI text from its argparse provenance, not the JSON
                # value union (which can also allow a literal null).
                settings["type"] = {"int": int, "float": float, "bool": bool}.get(
                    metadata.get("type"), str)
                if "nargs" in metadata:
                    settings["nargs"] = metadata["nargs"]
            if options:
                settings["dest"] = key
                parser.add_argument(*options, **settings)
            else:
                parser.add_argument(key, **settings)
        arguments = vars(parser.parse_args(argv))
        envelope = self.call(name, arguments)
        if envelope.get("stdout_parse") == "parsed":
            stdout = json.dumps(envelope["stdout_json"], sort_keys=True) + "\n"
        else:
            stdout = envelope.get("stdout_text", "")
        completed = subprocess.CompletedProcess(
            [filename, *argv], (envelope["exit_code"] if
             envelope.get("output_reliable") and envelope.get("invocation_reliable") else 1), stdout,
            envelope.get("report", ""))
        completed.tool_returncode = envelope["exit_code"]
        completed.mcp_result = envelope
        return completed

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self.process is None:
            return
        if not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for reader in self.readers:
            reader.join(timeout=5)
        self.process.stdout.close()
        self.process.stderr.close()
