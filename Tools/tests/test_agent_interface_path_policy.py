"""The agent call surface never turns a typed path into ambient filesystem access."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"


class RegisteredProducerOutputTests(unittest.TestCase):
    """Fixed artifact producers may publish only their registered artifact."""

    def run_tool(self, tool, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / (tool + ".py")), *arguments],
            cwd=str(REPOSITORY), capture_output=True, text=True, check=False)

    def assertions_for(self, tool, arguments):
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / "escaped-artifact"
            completed = self.run_tool(
                tool, *arguments, "--output", str(outside))

            self.assertEqual(completed.returncode, 1,
                             completed.stdout + completed.stderr)
            self.assertFalse(outside.exists())
            self.assertIn("artifact", completed.stdout + completed.stderr)

    def test_all_five_reported_producers_reject_an_external_output(self):
        cases = {
            "compile_cli_contract": ["."],
            "metadata_execution_contract": ["--root", "."],
            "compose_vocab": [],
            "compose_page_contract": ["--root", "."],
            "render_interface_projection": [".", "--form", "mcp"],
        }
        for tool, arguments in cases.items():
            with self.subTest(tool=tool):
                self.assertions_for(tool, arguments)

    def test_a_fixed_producer_cannot_overwrite_a_tool_module(self):
        target = TOOLS / "apply_delta.py"
        before = target.read_bytes()

        completed = self.run_tool(
            "metadata_execution_contract", "--root", ".", "--output",
            "Tools/apply_delta.py")

        self.assertEqual(completed.returncode, 1,
                         completed.stdout + completed.stderr)
        self.assertEqual(target.read_bytes(), before)

    def test_all_five_reject_an_alternate_in_repository_output(self):
        cases = {
            "compile_cli_contract": ["."],
            "metadata_execution_contract": ["--root", "."],
            "compose_vocab": [],
            "compose_page_contract": ["--root", "."],
            "render_interface_projection": [".", "--form", "mcp"],
        }
        with tempfile.TemporaryDirectory(dir=str(REPOSITORY)) as temporary:
            target = Path(temporary) / "alternate-artifact"
            relative = target.relative_to(REPOSITORY).as_posix()
            for tool, arguments in cases.items():
                with self.subTest(tool=tool):
                    completed = self.run_tool(
                        tool, *arguments, "--output", relative)
                    self.assertEqual(
                        completed.returncode, 1,
                        completed.stdout + completed.stderr)
                    self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
