"""The interface compile chain must honour the distribution boundary.

The boundary declaration says which files never reach an adopter runtime.
Until the resolver existed, nothing in the compile chain read it, so the
closed interface policy asked every adopter for a tool the same repository
had excluded, and the compiler refused when the adopter correctly did not
have it -- a refusal no test here could see, because this repository holds
every tool it declares.

Every fixture below is derived from the boundary declaration itself.  None
names an adopter, and none hard-codes which tool is excluded: a test that
spelled the name would keep passing after the declaration changed and would
be asserting its own memory rather than the rule.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
for path in (str(TOOLS_DIR / "tests"), str(TOOLS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import kblib  # noqa: E402
import tool_availability  # noqa: E402
from canonical_registry_fixture import (  # noqa: E402
    install_isolated_tool_registry_bundle,
)

COMPILER = TOOLS_DIR / "compile_cli_contract.py"
SERVER = TOOLS_DIR / "mcp_server.py"
CONTRACT = "Tools/compiled/cli-contract.yaml"


def boundary_excluded_tools():
    """The tool modules the declaration keeps out of an adopter runtime."""
    document = kblib.parse_yaml_subset(
        (REPO_ROOT / tool_availability.DEFAULT_BOUNDARY_PATH)
        .read_text(encoding="utf-8"))
    return tool_availability.excluded_tool_modules(document)


class AvailabilityResolution(unittest.TestCase):
    """The resolver answers one question and refuses to guess at it."""

    def test_the_declaration_excludes_at_least_one_tool_module(self):
        """Every case below is vacuous if the boundary excludes no tool."""
        self.assertTrue(
            boundary_excluded_tools(),
            "distribution-boundary.yaml declares no Tools/*.py entry, so "
            "nothing in this file is exercising the rule it claims to test")

    def test_the_source_distribution_may_not_be_missing_anything(self):
        resolved = tool_availability.resolve(
            REPO_ROOT, tool_availability.SOURCE_DISTRIBUTION)
        self.assertEqual(frozenset(), resolved.excluded)

    def test_a_carried_runtime_may_be_missing_exactly_the_declared_set(self):
        resolved = tool_availability.resolve(
            REPO_ROOT, tool_availability.CARRIED_RUNTIME)
        self.assertEqual(boundary_excluded_tools(), set(resolved.excluded))

    def test_an_undeclared_target_is_refused_rather_than_defaulted(self):
        with self.assertRaises(tool_availability.AvailabilityError):
            tool_availability.resolve(REPO_ROOT, "whatever-is-on-disk")

    def test_partition_separates_an_excluded_tool_from_a_lost_one(self):
        resolved = tool_availability.resolve(
            REPO_ROOT, tool_availability.CARRIED_RUNTIME)
        excluded_name = sorted(boundary_excluded_tools())[0]
        included, excluded, unregistered = resolved.partition(
            [excluded_name, "carried_tool", "vanished_tool"],
            ["carried_tool"])
        self.assertEqual(["carried_tool"], included)
        self.assertEqual([excluded_name], excluded)
        self.assertEqual(["vanished_tool"], unregistered)


class CarriedRuntimeFixture(unittest.TestCase):
    """A generic runtime carrying only what the boundary lets it carry.

    The fixture is built once and cloned per test.  Building it walks the
    whole Tools tree, and every case below needs the same starting shape.
    """

    @classmethod
    def setUpClass(cls):
        cls._template = tempfile.mkdtemp(prefix="carried-runtime-")
        root = Path(cls._template)
        shutil.copytree(TOOLS_DIR, root / "Tools",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
        shutil.copy2(REPO_ROOT / tool_availability.DEFAULT_BOUNDARY_PATH,
                     root / tool_availability.DEFAULT_BOUNDARY_PATH)
        # Copied production modules load Kernel/Component machine authorities
        # from the carried root.  Install the distribution's canonical
        # registry manifest rather than adding fixture-local fallbacks or
        # growing a second, hand-maintained dependency list here.
        install_isolated_tool_registry_bundle(root)
        # Apply the declaration rather than a list written here, so the
        # fixture keeps matching the rule when the declaration changes.
        for name in boundary_excluded_tools():
            (root / "Tools" / ("%s.py" % name)).unlink(missing_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._template, ignore_errors=True)

    def clone(self):
        target = tempfile.mkdtemp(prefix="carried-clone-")
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        root = Path(target) / "runtime"
        shutil.copytree(self._template, root)
        return root

    def compile_in(self, root, target=tool_availability.CARRIED_RUNTIME,
                   check=False):
        argv = [sys.executable, str(root / "Tools" / "compile_cli_contract.py"),
                str(root), "--projection-target", target]
        if check:
            argv.append("--check")
        return subprocess.run(argv, capture_output=True, text=True)

    def compiled(self, root):
        return kblib.parse_yaml_subset(
            (root / CONTRACT).read_text(encoding="utf-8"))

    # -- the boundary is honoured -------------------------------------------

    def test_the_source_projection_keeps_every_declared_tool(self):
        """The distribution owns them, so its own projection carries them."""
        contract = kblib.parse_yaml_subset(
            (REPO_ROOT / CONTRACT).read_text(encoding="utf-8"))
        self.assertEqual(tool_availability.SOURCE_DISTRIBUTION,
                         contract["projection_target"])
        included = set(contract["included_tools"])
        for name in boundary_excluded_tools():
            self.assertIn(name, included)
        self.assertEqual([], contract["excluded_tools"])

    def test_a_carried_runtime_compiles_without_the_declared_tools(self):
        root = self.clone()
        result = self.compile_in(root)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        contract = self.compiled(root)
        self.assertEqual(tool_availability.CARRIED_RUNTIME,
                         contract["projection_target"])
        self.assertEqual(sorted(boundary_excluded_tools()),
                         sorted(contract["excluded_tools"]))
        for name in boundary_excluded_tools():
            self.assertNotIn(name, contract["included_tools"])

    # -- absence is not blanket permission ----------------------------------

    def test_losing_a_carried_tool_still_fails_the_compile(self):
        """The rule must not degrade into "skip whatever is absent"."""
        root = self.clone()
        first = self.compile_in(root)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        carried = [name for name in self.compiled(root)["included_tools"]
                   if name not in boundary_excluded_tools()]
        victim = sorted(carried)[0]
        (root / "Tools" / ("%s.py" % victim)).unlink()

        result = self.compile_in(root)
        self.assertNotEqual(0, result.returncode,
                            "a carried tool disappeared and the compile "
                            "still succeeded")
        self.assertIn(victim, result.stdout + result.stderr)

    def test_the_refusal_names_the_tool_and_the_boundary(self):
        root = self.clone()
        self.compile_in(root)
        carried = [name for name in self.compiled(root)["included_tools"]
                   if name not in boundary_excluded_tools()]
        (root / "Tools" / ("%s.py" % sorted(carried)[0])).unlink()
        output = self.compile_in(root)
        combined = output.stdout + output.stderr
        self.assertIn(tool_availability.DEFAULT_BOUNDARY_PATH, combined)
        self.assertIn(tool_availability.CARRIED_RUNTIME, combined)

    # -- the artifact says whose projection it is ---------------------------

    def test_boundary_drift_makes_the_artifact_stale(self):
        root = self.clone()
        self.assertEqual(0, self.compile_in(root).returncode)
        self.assertEqual(0, self.compile_in(root, check=True).returncode)

        path = root / tool_availability.DEFAULT_BOUNDARY_PATH
        path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n",
                        encoding="utf-8")
        after = self.compile_in(root, check=True)
        self.assertEqual(2, after.returncode)
        self.assertIn("boundary changed", after.stdout + after.stderr)

    def test_another_targets_artifact_is_not_a_stale_copy_of_this_one(self):
        """Checked where both targets compile, so only the binding differs.

        A carried runtime cannot compile a source projection at all -- the
        excluded tool really is absent there -- so that direction would test
        the absence, not the recorded binding.  This repository holds every
        tool, so both targets compile and the stored target is the only
        thing that can disagree.
        """
        mismatched = subprocess.run(
            [sys.executable, str(COMPILER), str(REPO_ROOT), "--check",
             "--projection-target", tool_availability.CARRIED_RUNTIME],
            capture_output=True, text=True)
        self.assertEqual(2, mismatched.returncode,
                         mismatched.stdout + mismatched.stderr)
        self.assertIn("projection target",
                      mismatched.stdout + mismatched.stderr)

    def test_a_source_projection_cannot_be_compiled_where_a_tool_is_absent(
            self):
        """The permission belongs to the target, not to the repository."""
        root = self.clone()
        refused = self.compile_in(
            root, target=tool_availability.SOURCE_DISTRIBUTION)
        self.assertNotEqual(0, refused.returncode)
        combined = refused.stdout + refused.stderr
        self.assertTrue(
            any(name in combined for name in boundary_excluded_tools()),
            "the fail-closed compiler did not identify any source-only tool "
            "that the carried fixture omits:\n%s" % combined)
        for name in boundary_excluded_tools():
            self.assertFalse(
                (root / "Tools" / ("%s.py" % name)).exists(), name)

    def test_a_foreign_artifact_cannot_pass_as_the_local_projection(self):
        """A compiled artifact copied in from elsewhere must be refused."""
        root = self.clone()
        self.assertEqual(0, self.compile_in(root).returncode)
        local = self.compiled(root)

        foreign = dict(local)
        foreign["included_tools"] = [
            name for name in local["included_tools"]][:-1]
        (root / CONTRACT).write_text(
            kblib.canonical_yaml(foreign), encoding="utf-8")

        result = self.compile_in(root, check=True)
        self.assertEqual(2, result.returncode)
        self.assertIn("compiled somewhere else",
                      result.stdout + result.stderr)

    # -- the projection actually serves ------------------------------------

    def test_the_fixture_serves_a_real_mcp_initialize_and_enumeration(self):
        root = self.clone()
        self.assertEqual(0, self.compile_in(root).returncode)
        render = subprocess.run(
            [sys.executable,
             str(root / "Tools" / "render_interface_projection.py"),
             str(root)], capture_output=True, text=True)
        self.assertEqual(0, render.returncode,
                         render.stdout + render.stderr)

        environment = dict(os.environ)
        environment["CAMBIUM_WORKSPACE_ROOT"] = str(root)
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "boundary-probe",
                                       "version": "0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        server = subprocess.run(
            [sys.executable, str(root / "Tools" / "mcp_server.py")],
            input="\n".join(json.dumps(item) for item in requests) + "\n",
            capture_output=True, text=True, timeout=120, env=environment,
            cwd=str(root))

        replies = {}
        for line in server.stdout.splitlines():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and "id" in message:
                replies[message["id"]] = message

        self.assertIn(1, replies, server.stdout + server.stderr)
        self.assertNotIn("error", replies[1],
                         "initialize was refused: %s" % replies[1])
        self.assertIn(2, replies, server.stdout + server.stderr)
        offered = [tool["name"]
                   for tool in replies[2]["result"]["tools"]]
        self.assertTrue(offered)
        for name in boundary_excluded_tools():
            self.assertNotIn(name, offered)
        for name in offered:
            self.assertTrue(
                (root / "Tools" / ("%s.py" % name)).is_file(),
                "the served table offers %s with no implementation" % name)


if __name__ == "__main__":
    unittest.main()
