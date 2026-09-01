"""Minimal repositories for the compiled CLI contract owner tests.

The fixture derives its policy envelope from the current machine owner and
derives each fixture tool's argument closure from that tool's own ``argparse``
parser.  Tests may then change only the policy relation they are exercising;
the fixture never maintains a second complete CLI or Host contract.
"""

import contextlib
import copy
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace

from Tools.platform.agent_interface import agent_interface_policy
from Tools.platform.agent_interface import compile_cli_contract as compiler
from Tools.platform.agent_interface import tool_availability
from Tools.platform.common import kblib


REPOSITORY = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY / "Tools/compile_cli_contract.py"


class CliContractFixture:
    """One isolated CLI surface with no copied repository lifecycle."""

    def __init__(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name).resolve() / "repository"
        self.tools = self.root / "Tools"
        self.implementations = self.tools / "fixture_implementations"
        self.implementations.mkdir(parents=True)
        self.output = self.root / compiler.SOURCE_DISTRIBUTION_OUTPUT

        boundary = {"schema_version": 1, "distribution_only": []}
        (self.root / "distribution-boundary.yaml").write_text(
            kblib.canonical_yaml(boundary), encoding="utf-8")

        registry = self.root / compiler.DEFAULT_RUNTIME_PATH_REGISTRY
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_bytes(
            (REPOSITORY / compiler.DEFAULT_RUNTIME_PATH_REGISTRY).read_bytes())

        receipt_owner = self.root / compiler.KBLIB_RECEIPT_SOURCE
        receipt_owner.parent.mkdir(parents=True, exist_ok=True)
        receipt_owner.write_bytes(
            (REPOSITORY / compiler.KBLIB_RECEIPT_SOURCE).read_bytes())

    def cleanup(self):
        self._temporary.cleanup()

    def write_tool(self, name, source):
        """Write one public adapter and its unique implementation owner."""
        implementation_module = "Tools.fixture_implementations.%s" % name
        implementation = self.implementations / (name + ".py")
        implementation.write_text(
            textwrap.dedent(source), encoding="utf-8")
        adapter = self.tools / (name + ".py")
        adapter.write_text(
            "IMPLEMENTATION_MODULE = %r\n\n"
            "def main(argv=None):\n"
            "    raise AssertionError('adapter is transport only')\n"
            % implementation_module,
            encoding="utf-8",
        )
        return implementation

    def write_library(self, relative_path, source):
        path = self.tools / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def policy_document(self):
        """Project the owner envelope over the fixture's parser identities."""
        owner, _raw = agent_interface_policy.load_policy(REPOSITORY)
        document = copy.deepcopy(owner)
        document["path_defaults"] = []
        document["path_overrides"] = []
        document["path_activation_overrides"] = []
        document["tools"] = []
        for name, _path, _source in compiler.discover_tools(self.root):
            parser = compiler.entrypoint_loader.capture_argument_parser(
                name, self.tools, require_marker=True)
            arguments = compiler.describe_arguments(self.root, parser)
            document["tools"].append({
                "tool": name,
                "exposure": "cli-only",
                "workspace_argument": None,
                "workspace_access": None,
                "value_arguments": [row["dest"] for row in arguments],
                "read_paths": [],
                "write_paths": [],
                "read_write_paths": [],
                "external_write": "none",
            })
        return document

    def write_policy(self, document=None):
        policy = copy.deepcopy(document or self.policy_document())
        path = self.root / compiler.DEFAULT_INTERFACE_POLICY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(policy), encoding="utf-8")
        return policy

    def compile(self, document=None):
        if document is not None or not (
                self.root / compiler.DEFAULT_INTERFACE_POLICY).is_file():
            self.write_policy(document)
        return compiler.compile_contract(
            self.root, tool_availability.SOURCE_DISTRIBUTION)

    def run_in_process(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = compiler.main([str(item) for item in arguments])
        return SimpleNamespace(
            returncode=int(code or 0),
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        )

    def run_cli(self, *arguments):
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=str(REPOSITORY), capture_output=True, text=True,
            env=environment, check=False)

__all__ = ["CliContractFixture"]
