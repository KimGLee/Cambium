"""The compiled CLI invocation contract and the compiler that derives it.

These cover the properties the artifact is only useful for having: that it is
derived from each tool's own argparse declaration rather than restated, that
two runs of the compiler agree byte for byte (including across hash seeds,
because several tools build `choices` from a Python set), that `--check`
separates a stale artifact (2, a HOLD) from unreliable evidence (1), and that
introspecting a tool runs none of that tool's behaviour.

No flag, default, or help string is restated here. Every expectation is read
either from the repository's own tools or from a fixture built inside the
test, so this file cannot drift into a second declaration of the contract.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
SCRIPT = TOOLS_DIR / "compile_cli_contract.py"
ARTIFACT = TOOLS_DIR / "compiled" / "cli-contract.yaml"

sys.path.insert(0, str(TOOLS_DIR))
import compile_cli_contract as compiler  # noqa: E402
import kblib  # noqa: E402


def write_interface_policy(root, tool_names):
    arguments = {}
    original_parse_args = compiler.argparse.ArgumentParser.parse_args
    original_argv = list(sys.argv)

    def capture(parser, _args=None, _namespace=None):
        raise compiler._CapturedParser(parser)

    compiler.argparse.ArgumentParser.parse_args = capture
    try:
        for name, path, _source in compiler.discover_tools(root):
            sys.argv = [os.path.basename(path)]
            parser = compiler.load_parser(
                "_cambium_test_policy_%s" % name, path)
            arguments[name] = [
                item["dest"] for item in
                compiler.describe_arguments(root, parser)
            ]
    finally:
        compiler.argparse.ArgumentParser.parse_args = original_parse_args
        sys.argv = original_argv
    rows = []
    for name in sorted(tool_names):
        rows.append({
            "tool": name,
            "exposure": "cli-only",
            "workspace_argument": None,
            "workspace_access": None,
            "value_arguments": arguments[name],
            "read_paths": [],
            "write_paths": [],
            "read_write_paths": [],
            "external_write": "none",
        })
    path = Path(root) / compiler.DEFAULT_INTERFACE_POLICY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kblib.canonical_yaml({
        "schema_version": 1,
        "artifact": "agent-interface-policy",
        "path_defaults": [],
        "path_overrides": [],
        "tools": rows,
    }), encoding="utf-8")


def run(*arguments, env=None, cwd=None):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(arguments),
        capture_output=True, text=True, env=environment,
        cwd=str(cwd or REPO_ROOT), check=False)


class ShippedArtifactTests(unittest.TestCase):
    """The artifact in the tree must be what the tools currently declare."""

    def test_check_accepts_the_shipped_artifact(self):
        result = run(".", "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_shipped_cli_has_a_section(self):
        contract = compiler.compile_contract(str(REPO_ROOT))

        modules = {record["module"] for record in contract["tools"]}
        expected = {
            "Tools/%s" % path.name
            for path in sorted(TOOLS_DIR.glob("*.py"))
            if not path.name.startswith("_") and
            compiler.is_cli_module(path.read_text(encoding="utf-8"))
        }

        self.assertEqual(modules, expected)
        self.assertEqual(
            set(contract["source_files"]),
            expected | {compiler.DEFAULT_INTERFACE_POLICY})
        self.assertEqual(contract["tool_count"], len(expected))

    def test_each_section_records_the_source_it_was_read_from(self):
        contract = compiler.compile_contract(str(REPO_ROOT))

        for record in contract["tools"]:
            with self.subTest(tool=record["tool"]):
                source = (REPO_ROOT / record["module"]).read_bytes()

                self.assertEqual(record["source_hash"],
                                 kblib.sha256_bytes(source))

    def test_the_artifact_is_readable_by_the_shared_subset_parser(self):
        parsed = kblib.parse_yaml_subset(ARTIFACT.read_text(encoding="utf-8"))

        self.assertEqual(parsed["artifact"], "cli-invocation-contract")
        self.assertTrue(parsed["tools"])


class DeterminismTests(unittest.TestCase):
    def test_two_runs_agree_across_hash_seeds(self):
        with tempfile.TemporaryDirectory() as workspace:
            shutil.copytree(TOOLS_DIR, Path(workspace) / "Tools")
            artifact = Path(workspace) / compiler.DEFAULT_OUTPUT
            first_run = run(workspace, env={"PYTHONHASHSEED": "0"})
            self.assertEqual(first_run.returncode, 0,
                             first_run.stdout + first_run.stderr)
            first = artifact.read_bytes()
            second_run = run(workspace, env={"PYTHONHASHSEED": "12345"})
            self.assertEqual(second_run.returncode, 0,
                             second_run.stdout + second_run.stderr)

            self.assertEqual(first, artifact.read_bytes())

    def test_choices_are_recorded_in_one_canonical_order(self):
        root = str(REPO_ROOT)

        self.assertEqual(
            compiler.normalize_choices(root, ("gamma", "alpha", "beta")),
            compiler.normalize_choices(root, {"beta", "gamma", "alpha"}),
        )


class FixtureTests(unittest.TestCase):
    """Behaviour that the shipped tools do not happen to exercise."""

    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.tools = os.path.join(self.workspace, "Tools")
        os.makedirs(self.tools)
        shutil.copy(str(TOOLS_DIR / "kblib.py"), self.tools)

    def write_tool(self, name, body):
        path = os.path.join(self.tools, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(body))
        return path

    def compile(self):
        names = [name for name, _path, _source in
                 compiler.discover_tools(self.workspace)]
        write_interface_policy(self.workspace, names)
        return compiler.compile_contract(self.workspace)

    def only_tool(self):
        tools = self.compile()["tools"]
        self.assertEqual(len(tools), 1)
        return tools[0]

    def test_a_positional_is_the_argument_with_no_option_strings(self):
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root", help="where to look")
                parser.add_argument("--check", action="store_true",
                                    help="verify only")
                return parser.parse_args(argv)
        """)

        arguments = {record["dest"]: record for record in
                     self.only_tool()["arguments"]}

        self.assertEqual(arguments["root"]["option_strings"], [])
        self.assertEqual(arguments["check"]["option_strings"], ["--check"])
        self.assertEqual(arguments["check"]["action"], "store_true")
        self.assertEqual(arguments["root"]["help"], "where to look")

    def test_mutually_exclusive_groups_are_recorded_with_their_members(self):
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                group = parser.add_mutually_exclusive_group(required=True)
                group.add_argument("--apply", action="store_true", help="a")
                group.add_argument("--revert", action="store_true", help="b")
                return parser.parse_args(argv)
        """)

        groups = self.only_tool()["mutually_exclusive_groups"]

        self.assertEqual(groups, [{"required": True,
                                   "dests": ["apply", "revert"]}])

    def test_defaults_are_evaluated_and_made_repository_relative(self):
        self.write_tool("sample.py", """
            import argparse
            import os

            ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("--out", default=os.path.join(
                    ROOT, "Tools", "out.yaml"), help="where to write")
                parser.add_argument("--limit", type=int, default=3,
                                    help="how many")
                return parser.parse_args(argv)
        """)

        arguments = {record["dest"]: record for record in
                     self.only_tool()["arguments"]}

        self.assertEqual(arguments["out"]["default"], "Tools/out.yaml")
        self.assertEqual(arguments["limit"]["default"], 3)
        self.assertEqual(arguments["limit"]["default_type"], "int")
        self.assertEqual(arguments["limit"]["type"], "int")

    def test_no_tool_behaviour_runs_during_introspection(self):
        marker = os.path.join(self.workspace, "ran")
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root", help="where to look")
                args = parser.parse_args(argv)
                open(%r, "w").write("the tool body ran")
                return 0
        """ % marker)

        self.compile()

        self.assertFalse(os.path.exists(marker))

    def test_receipt_extension_fields_come_from_the_tool_source(self):
        self.write_tool("sample.py", """
            import argparse
            import kblib

            def emit():
                receipt = kblib.make_receipt(
                    "sample", "1.0.0", "c", "t", "pass", "d", 1)
                receipt.update({"scan_id": "s", "checked_at": "z"})
                receipt["gate_id"] = "g"
                return receipt

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root", help="where to look")
                return parser.parse_args(argv)
        """)

        record = self.only_tool()

        self.assertEqual(record["receipt_extensions"], ["gate_id", "scan_id"])
        self.assertEqual(record["receipt_extensions_extraction"], "complete")

    def test_a_runtime_computed_receipt_key_is_reported_as_partial(self):
        self.write_tool("sample.py", """
            import argparse
            import kblib

            def emit(name):
                receipt = kblib.make_receipt(
                    "sample", "1.0.0", "c", "t", "pass", "d", 1)
                receipt[name] = "value"
                return receipt

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root", help="where to look")
                return parser.parse_args(argv)
        """)

        record = self.only_tool()

        self.assertEqual(record["receipt_extensions"], [])
        self.assertEqual(record["receipt_extensions_extraction"], "partial")

    def test_a_library_module_is_not_treated_as_a_command(self):
        self.write_tool("helper.py", """
            def helper():
                return 1
        """)
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root", help="where to look")
                return parser.parse_args(argv)
        """)

        self.assertEqual([record["tool"] for record in
                          self.compile()["tools"]], ["sample"])

    def test_an_unclassified_new_argument_fails_policy_compilation(self):
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root", help="where to look")
                parser.add_argument("--new-capability", help="new surface")
                return parser.parse_args(argv)
        """)
        write_interface_policy(self.workspace, ["sample"])
        policy_path = Path(self.workspace) / compiler.DEFAULT_INTERFACE_POLICY
        policy = kblib.parse_yaml_subset(
            policy_path.read_text(encoding="utf-8"))
        policy["tools"][0]["value_arguments"].remove("new_capability")
        policy_path.write_text(kblib.canonical_yaml(policy), encoding="utf-8")

        with self.assertRaisesRegex(
                compiler.ContractError, "unclassified=new_capability"):
            compiler.compile_contract(self.workspace)


class ExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.tools = os.path.join(self.workspace, "Tools")
        os.makedirs(self.tools)
        shutil.copy(str(TOOLS_DIR / "kblib.py"), self.tools)
        with open(os.path.join(self.tools, "sample.py"), "w",
                  encoding="utf-8") as handle:
            handle.write(textwrap.dedent("""
                import argparse

                def main(argv=None):
                    parser = argparse.ArgumentParser(description="Sample")
                    parser.add_argument("root", help="where to look")
                    return parser.parse_args(argv)
            """))
        write_interface_policy(self.workspace, ["sample"])
        self.output = os.path.join(
            self.workspace, compiler.DEFAULT_OUTPUT)
        os.makedirs(os.path.dirname(self.output), exist_ok=True)

    def compile_once(self):
        return run(self.workspace)

    def test_write_then_check_passes(self):
        self.assertEqual(self.compile_once().returncode, 0)

        result = run(self.workspace, "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_hand_edited_artifact_holds_with_2(self):
        self.compile_once()
        text = Path(self.output).read_text(encoding="utf-8")
        Path(self.output).write_text(
            text.replace("tool_count: 1", "tool_count: 2"), encoding="utf-8")

        result = run(self.workspace, "--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_missing_artifact_holds_with_2(self):
        result = run(self.workspace, "--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_stale_artifact_holds_with_2(self):
        self.compile_once()
        with open(os.path.join(self.tools, "sample.py"), "a",
                  encoding="utf-8") as handle:
            handle.write("\n# a later edit to the tool\n")

        result = run(self.workspace, "--check")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_unreliable_evidence_fails_with_1_not_2(self):
        with open(os.path.join(self.tools, "broken.py"), "w",
                  encoding="utf-8") as handle:
            handle.write(textwrap.dedent("""
                import argparse
                raise RuntimeError("import side effect")

                def main(argv=None):
                    parser = argparse.ArgumentParser(description="Broken")
                    return parser.parse_args(argv)
            """))

        result = run(self.workspace, "--check")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_parse_args_is_restored_after_a_run(self):
        import argparse

        before = argparse.ArgumentParser.parse_args
        compiler.compile_contract(self.workspace)

        self.assertIs(argparse.ArgumentParser.parse_args, before)


if __name__ == "__main__":
    unittest.main()
