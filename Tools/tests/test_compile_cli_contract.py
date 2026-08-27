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

import copy
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
import card_contract  # noqa: E402
import compile_cli_contract as compiler  # noqa: E402
import tool_availability  # noqa: E402
import kblib  # noqa: E402
import runtime_paths  # noqa: E402


def write_distribution_boundary(root, entries=()):
    """A workspace needs a boundary before any projection can be compiled.

    The default declares nothing excluded, so both targets resolve to the
    same effective tool set and these cases keep testing what they were
    written to test rather than the exclusion rule.
    """
    lines = ["schema_version: 1"]
    if entries:
        lines.append("distribution_only:")
        for path in entries:
            lines.append("  - path: %s" % path)
            lines.append("    reason: fixture entry")
    else:
        lines.append("distribution_only: []")
    with open(os.path.join(root, "distribution-boundary.yaml"), "w",
              encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


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
        "schema_version": compiler.INTERFACE_POLICY_SCHEMA_VERSION,
        "artifact": "agent-interface-policy",
        "consumption_defaults": {
            "read": "snapshot",
            "write": "replace",
            "read-write": "transaction",
        },
        "path_defaults": [],
        "path_overrides": [],
        "path_activation_overrides": [],
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
        contract = compiler.compile_contract(str(REPO_ROOT),
            tool_availability.SOURCE_DISTRIBUTION)

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
            expected | {
                compiler.DEFAULT_INTERFACE_POLICY,
                compiler.DEFAULT_RUNTIME_PATH_REGISTRY,
                card_contract.SCHEMA_PATH,
            })
        self.assertEqual(contract["tool_count"], len(expected))

    def test_each_section_records_the_source_it_was_read_from(self):
        contract = compiler.compile_contract(str(REPO_ROOT),
            tool_availability.SOURCE_DISTRIBUTION)

        for record in contract["tools"]:
            with self.subTest(tool=record["tool"]):
                source = (REPO_ROOT / record["module"]).read_bytes()

                self.assertEqual(record["source_hash"],
                                 kblib.sha256_bytes(source))

    def test_the_artifact_is_readable_by_the_shared_subset_parser(self):
        parsed = kblib.parse_yaml_subset(ARTIFACT.read_text(encoding="utf-8"))

        self.assertEqual(parsed["artifact"], "cli-invocation-contract")
        self.assertTrue(parsed["tools"])

    def test_adoption_writers_classify_the_resolved_upstream_identity(self):
        contract = compiler.compile_contract(str(REPO_ROOT),
            tool_availability.SOURCE_DISTRIBUTION)
        by_tool = {record["tool"]: record for record in contract["tools"]}

        for tool in ("adopt_standards", "apply_profile_adoption"):
            with self.subTest(tool=tool):
                interface = by_tool[tool]["agent_interface"]
                self.assertIn("upstream_root", interface["value_arguments"])
                self.assertIn("upstream_ref", interface["value_arguments"])


class DeterminismTests(unittest.TestCase):
    def test_two_runs_agree_across_hash_seeds(self):
        with tempfile.TemporaryDirectory() as workspace:
            shutil.copytree(TOOLS_DIR, Path(workspace) / "Tools")
            # CLI imports now validate several Kernel-owned machine contracts
            # at module load. The isolated determinism fixture must stage the
            # real owner tree, not replace those validations with test stubs.
            shutil.copytree(REPO_ROOT / "kernel", Path(workspace) / "kernel")
            shutil.copytree(REPO_ROOT / "Card", Path(workspace) / "Card")
            shutil.copytree(
                REPO_ROOT / "Read Set", Path(workspace) / "Read Set")
            write_distribution_boundary(workspace)
            artifact = Path(workspace) / compiler.DEFAULT_OUTPUT
            first_run = run(workspace, "--projection-target", tool_availability.SOURCE_DISTRIBUTION,
                            env={"PYTHONHASHSEED": "0"})
            self.assertEqual(first_run.returncode, 0,
                             first_run.stdout + first_run.stderr)
            first = artifact.read_bytes()
            second_run = run(workspace, "--projection-target", tool_availability.SOURCE_DISTRIBUTION,
                             env={"PYTHONHASHSEED": "12345"})
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
        shutil.copy(str(TOOLS_DIR / "runtime_paths.py"), self.tools)
        shutil.copy(str(TOOLS_DIR / "tool_availability.py"), self.tools)
        write_distribution_boundary(self.workspace)

    def write_tool(self, name, body):
        path = os.path.join(self.tools, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(body))
        return path

    def compile(self):
        names = [name for name, _path, _source in
                 compiler.discover_tools(self.workspace)]
        write_interface_policy(self.workspace, names)
        return compiler.compile_contract(self.workspace,
            tool_availability.SOURCE_DISTRIBUTION)

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
            compiler.compile_contract(self.workspace,
            tool_availability.SOURCE_DISTRIBUTION)

    def test_path_activation_is_closed_over_same_tool_boolean_modes(self):
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root", help="where to look")
                parser.add_argument("--output", default="reports/out.md")
                parser.add_argument("--apply", action="store_true")
                parser.add_argument("--label")
                return parser.parse_args(argv)
        """)
        write_interface_policy(self.workspace, ["sample"])
        policy_path = Path(self.workspace) / compiler.DEFAULT_INTERFACE_POLICY
        policy = kblib.parse_yaml_subset(
            policy_path.read_text(encoding="utf-8"))
        row = policy["tools"][0]
        row.update({
            "exposure": "mcp",
            "workspace_argument": "root",
            "workspace_access": "write",
            "value_arguments": ["apply", "label"],
            "write_paths": ["output"],
        })
        policy["path_activation_overrides"] = [{
            "tool": "sample", "argument": "output",
            "active_when_any": ["apply"], "inactive_when_any": [],
        }]
        policy_path.write_text(
            kblib.canonical_yaml(policy), encoding="utf-8")

        compiled = compiler.compile_contract(self.workspace,
            tool_availability.SOURCE_DISTRIBUTION)
        capability = compiled["tools"][0]["agent_interface"][
            "path_arguments"][0]
        self.assertEqual(capability["active_when_any"], ["apply"])

        policy["path_activation_overrides"][0]["active_when_any"] = [
            "label"]
        policy_path.write_text(
            kblib.canonical_yaml(policy), encoding="utf-8")
        with self.assertRaisesRegex(
                compiler.ContractError, "must name one store_true"):
            compiler.compile_contract(self.workspace,
            tool_availability.SOURCE_DISTRIBUTION)

    def test_runtime_path_id_resolves_value_and_retains_source_identity(self):
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root")
                parser.add_argument("--output")
                return parser.parse_args(argv)
        """)
        write_interface_policy(self.workspace, ["sample"])
        policy_path = Path(self.workspace) / compiler.DEFAULT_INTERFACE_POLICY
        policy = kblib.parse_yaml_subset(
            policy_path.read_text(encoding="utf-8"))
        policy["tools"][0].update({
            "exposure": "mcp",
            "workspace_argument": "root",
            "workspace_access": "write",
            "value_arguments": [],
            "write_paths": ["output"],
        })
        policy["path_overrides"] = [{
            "tool": "sample",
            "argument": "output",
            "constraint": "namespace",
            "runtime_path_id": "report-root",
            "suffixes": [".md"],
        }]
        policy_path.write_text(
            kblib.canonical_yaml(policy), encoding="utf-8")

        compiled = compiler.compile_contract(
            self.workspace, tool_availability.SOURCE_DISTRIBUTION)
        capability = compiled["tools"][0]["agent_interface"][
            "path_arguments"][0]

        self.assertEqual("report-root", capability["runtime_path_id"])
        self.assertEqual(runtime_paths.REPORT_ROOT, capability["value"])
        self.assertEqual(
            compiler.DEFAULT_RUNTIME_PATH_REGISTRY,
            compiled["runtime_path_registry"]["path"],
        )

    def test_component_path_id_tracks_card_schema_path_prefix(self):
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root")
                parser.add_argument("--cards-dir")
                return parser.parse_args(argv)
        """)
        card_directory = Path(self.workspace) / "Card"
        card_directory.mkdir()
        schema_path = Path(self.workspace) / "Tools/schemas/card.schema.yaml"
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / "Tools/schemas/card.schema.yaml", schema_path)
        write_interface_policy(self.workspace, ["sample"])
        policy_path = Path(self.workspace) / compiler.DEFAULT_INTERFACE_POLICY
        policy = kblib.parse_yaml_subset(
            policy_path.read_text(encoding="utf-8"))
        policy["tools"][0].update({
            "exposure": "mcp",
            "workspace_argument": "root",
            "workspace_access": "write",
            "value_arguments": [],
            "read_write_paths": ["cards_dir"],
        })
        policy["path_overrides"] = [{
            "tool": "sample",
            "argument": "cards_dir",
            "constraint": "exact",
            "component_path_id": compiler.CARD_DIRECTORY_COMPONENT_PATH_ID,
            "suffixes": [],
        }]
        policy_path.write_text(
            kblib.canonical_yaml(policy), encoding="utf-8")

        before = compiler.compile_contract(
            self.workspace, tool_availability.SOURCE_DISTRIBUTION)
        before_path = before["tools"][0]["agent_interface"][
            "path_arguments"][0]
        before_hash = before["component_path_registries"][
            compiler.CARD_DIRECTORY_COMPONENT_PATH_ID]["sha256"]
        self.assertEqual("Card", before_path["value"])
        self.assertEqual(
            compiler.CARD_DIRECTORY_COMPONENT_PATH_ID,
            before_path["component_path_id"],
        )

        schema = kblib.parse_yaml_subset(
            schema_path.read_text(encoding="utf-8"))
        schema["path_prefix"] = "Flight-Cards/"
        schema_path.write_text(
            kblib.canonical_yaml(schema), encoding="utf-8")
        after = compiler.compile_contract(
            self.workspace, tool_availability.SOURCE_DISTRIBUTION)
        after_path = after["tools"][0]["agent_interface"][
            "path_arguments"][0]
        after_hash = after["component_path_registries"][
            compiler.CARD_DIRECTORY_COMPONENT_PATH_ID]["sha256"]

        self.assertEqual("Flight-Cards", after_path["value"])
        self.assertNotEqual(before_hash, after_hash)
        self.assertNotEqual(before["source_hash"], after["source_hash"])

    def test_runtime_path_binding_shape_and_identity_fail_closed(self):
        self.write_tool("sample.py", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Sample tool")
                parser.add_argument("root")
                parser.add_argument("--output")
                return parser.parse_args(argv)
        """)
        write_interface_policy(self.workspace, ["sample"])
        policy_path = Path(self.workspace) / compiler.DEFAULT_INTERFACE_POLICY
        base = kblib.parse_yaml_subset(
            policy_path.read_text(encoding="utf-8"))
        base["tools"][0].update({
            "exposure": "mcp",
            "workspace_argument": "root",
            "workspace_access": "write",
            "value_arguments": [],
            "write_paths": ["output"],
        })
        valid_row = {
            "tool": "sample",
            "argument": "output",
            "constraint": "namespace",
            "runtime_path_id": "report-root",
            "suffixes": [".md"],
        }
        cases = []
        both = dict(valid_row, value="reports")
        cases.append((both, "exactly one of value/runtime_path_id"))
        both_registries = dict(
            valid_row,
            component_path_id=compiler.CARD_DIRECTORY_COMPONENT_PATH_ID,
        )
        cases.append((both_registries,
                      "exactly one of value/runtime_path_id"))
        neither = dict(valid_row)
        del neither["runtime_path_id"]
        cases.append((neither, "exactly one of value/runtime_path_id"))
        cases.append((
            dict(valid_row, runtime_path_id="not-registered"),
            "unknown runtime_path_id not-registered",
        ))
        cases.append((
            dict(valid_row, runtime_path_id=None),
            "runtime_path_id must be a non-empty string",
        ))
        cases.append((
            dict(valid_row, runtime_path_id="effective-vocabulary"),
            "constraint mismatch",
        ))
        literal_runtime = dict(valid_row)
        del literal_runtime["runtime_path_id"]
        literal_runtime["value"] = ".cambium/reports"
        cases.append((literal_runtime, "must use runtime_path_id"))

        for row, message in cases:
            with self.subTest(message=message):
                policy = copy.deepcopy(base)
                policy["path_overrides"] = [row]
                policy_path.write_text(
                    kblib.canonical_yaml(policy), encoding="utf-8")

                with self.assertRaisesRegex(
                        compiler.ContractError, message):
                    compiler.compile_contract(
                        self.workspace,
                        tool_availability.SOURCE_DISTRIBUTION,
                    )


class ExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.tools = os.path.join(self.workspace, "Tools")
        os.makedirs(self.tools)
        shutil.copy(str(TOOLS_DIR / "kblib.py"), self.tools)
        shutil.copy(str(TOOLS_DIR / "runtime_paths.py"), self.tools)
        shutil.copy(str(TOOLS_DIR / "tool_availability.py"), self.tools)
        write_distribution_boundary(self.workspace)
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
        return run(self.workspace, "--projection-target", tool_availability.SOURCE_DISTRIBUTION)

    def test_write_then_check_passes(self):
        self.assertEqual(self.compile_once().returncode, 0)

        result = run(self.workspace, "--check", "--projection-target", tool_availability.SOURCE_DISTRIBUTION)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_carried_runtime_writes_only_the_registered_derived_contract(self):
        result = run(
            self.workspace, "--projection-target",
            tool_availability.CARRIED_RUNTIME)

        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        runtime_output = Path(
            self.workspace, runtime_paths.CLI_CONTRACT_ARTIFACT_PATH)
        self.assertTrue(runtime_output.is_file())
        self.assertFalse(Path(self.output).exists())
        contract = kblib.parse_yaml_subset(
            runtime_output.read_text(encoding="utf-8"))
        self.assertEqual(contract["projection_target"],
                         tool_availability.CARRIED_RUNTIME)
        header = runtime_output.read_text(encoding="utf-8").splitlines()[:12]
        self.assertTrue(any(
            "--projection-target carried-runtime" in line
            for line in header))
        self.assertFalse(any(
            "compile_cli_contract.py . --check" in line
            for line in header))

    def test_carried_runtime_refuses_the_distribution_output(self):
        result = run(
            self.workspace, "--projection-target",
            tool_availability.CARRIED_RUNTIME,
            "--output", self.output)

        self.assertEqual(result.returncode, 1,
                         result.stdout + result.stderr)
        self.assertFalse(Path(self.output).exists())

    def test_a_hand_edited_artifact_holds_with_2(self):
        self.compile_once()
        text = Path(self.output).read_text(encoding="utf-8")
        Path(self.output).write_text(
            text.replace("tool_count: 1", "tool_count: 2"), encoding="utf-8")

        result = run(self.workspace, "--check", "--projection-target", tool_availability.SOURCE_DISTRIBUTION)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_missing_artifact_holds_with_2(self):
        result = run(self.workspace, "--check", "--projection-target", tool_availability.SOURCE_DISTRIBUTION)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_stale_artifact_holds_with_2(self):
        self.compile_once()
        with open(os.path.join(self.tools, "sample.py"), "a",
                  encoding="utf-8") as handle:
            handle.write("\n# a later edit to the tool\n")

        result = run(self.workspace, "--check", "--projection-target", tool_availability.SOURCE_DISTRIBUTION)

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

        result = run(self.workspace, "--check", "--projection-target", tool_availability.SOURCE_DISTRIBUTION)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_parse_args_is_restored_after_a_run(self):
        import argparse

        before = argparse.ArgumentParser.parse_args
        compiler.compile_contract(self.workspace,
            tool_availability.SOURCE_DISTRIBUTION)

        self.assertIs(argparse.ArgumentParser.parse_args, before)


if __name__ == "__main__":
    unittest.main()
