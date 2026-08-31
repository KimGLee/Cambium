"""Ownership tests for fixed-output CLI path policy.

The current CLI compiler discovers the public command surface from source.
This suite joins that surface to each producer's own output registry and the
runtime-path registry; it does not maintain a second producer allowlist.
"""

import ast
import functools
import importlib
import subprocess
import sys
import unittest
from pathlib import Path

import Tools.platform.common.kblib as kblib
from Tools.execution.task_runtime import runtime_paths
from Tools.platform.agent_interface import compile_cli_contract
from Tools.platform.agent_interface import tool_availability


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"


def _calls_registered_artifact_path(source_path):
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and \
                function.attr == "registered_repository_artifact_path":
            return True
        if isinstance(function, ast.Name) and \
                function.id == "registered_repository_artifact_path":
            return True
    return False


def _owner_registered_outputs(module):
    """Read one producer's fixed outputs from its current machine owner."""
    outputs = set()
    resolver = getattr(module, "output_for_projection_target", None)
    forms = getattr(module, "FORMS", None)
    if callable(resolver):
        if isinstance(forms, dict):
            for form in sorted(forms):
                for target in tool_availability.PROJECTION_TARGETS:
                    outputs.add(resolver(form, target))
        else:
            for target in tool_availability.PROJECTION_TARGETS:
                outputs.add(resolver(target))
    for attribute in ("DEFAULT_OUTPUT", "DEFAULT_COMPILED_PATH"):
        value = getattr(module, attribute, None)
        if isinstance(value, str) and value:
            outputs.add(value)
    return frozenset(outputs)


@functools.lru_cache(maxsize=1)
def _current_fixed_output_closure():
    """Return ``((CLI row, outputs), ...)`` from current source owners."""
    contract = compile_cli_contract.compile_contract(
        REPOSITORY, tool_availability.SOURCE_DISTRIBUTION)
    closure = []
    for row in contract["tools"]:
        if not any(argument["dest"] == "output"
                   for argument in row["arguments"]):
            continue
        implementation_path = REPOSITORY / row["implementation_path"]
        if not _calls_registered_artifact_path(implementation_path):
            continue
        module = importlib.import_module(row["implementation_module"])
        closure.append((row, _owner_registered_outputs(module)))
    return tuple(closure)


class CurrentFixedOutputOwnerContractTests(unittest.TestCase):
    def test_current_cli_consumers_join_to_unique_output_owners(self):
        closure = _current_fixed_output_closure()
        self.assertTrue(closure)
        runtime_registry = {
            entry.path for entry in runtime_paths.RUNTIME_OBJECTS.values()
        }
        owner_by_output = {}
        for row, outputs in closure:
            self.assertTrue(outputs, row["tool"])
            for output in outputs:
                self.assertNotIn(output, owner_by_output)
                owner_by_output[output] = row["tool"]
                if output.startswith(runtime_paths.RUNTIME_ROOT + "/"):
                    self.assertIn(output, runtime_registry)
                else:
                    self.assertTrue(
                        output.startswith("Tools/compiled/"),
                        "%s owns an unregistered source artifact %s" %
                        (row["tool"], output),
                    )


class RegisteredArtifactPathUnitTests(unittest.TestCase):
    def test_every_current_registered_output_rejects_other_destinations(self):
        registered_outputs = sorted({
            output
            for _row, outputs in _current_fixed_output_closure()
            for output in outputs
        })
        self.assertTrue(registered_outputs)
        forbidden = (
            "/__cambium_external_artifact__/output",
            "Tools/tests/unregistered-artifact",
            "Tools/apply_delta.py",
        )
        for registered in registered_outputs:
            accepted = kblib.registered_repository_artifact_path(
                REPOSITORY, registered, registered)
            self.assertEqual(REPOSITORY / registered, Path(accepted))
            for requested in forbidden:
                with self.subTest(registered=registered, requested=requested):
                    with self.assertRaisesRegex(ValueError, "artifact path"):
                        kblib.registered_repository_artifact_path(
                            REPOSITORY, requested, registered)


class FixedOutputCliTransportTests(unittest.TestCase):
    def test_public_cli_preserves_the_registered_output_boundary(self):
        target = TOOLS / "apply_delta.py"
        before = target.read_bytes()
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "metadata_execution_contract.py"),
                "--root", str(REPOSITORY),
                "--output", "Tools/apply_delta.py",
            ],
            cwd=str(REPOSITORY),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(1, completed.returncode,
                         completed.stdout + completed.stderr)
        self.assertIn("artifact path", completed.stdout + completed.stderr)
        self.assertEqual(before, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
