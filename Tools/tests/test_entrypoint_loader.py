"""The public Tool adapter-to-implementation edge has one machine owner."""

import ast
import argparse
from pathlib import Path
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]

from Tools.platform.agent_interface import entrypoint_loader
from Tools.platform.agent_interface import agent_interface_policy
from Tools.platform.distribution import module_boundary_facts


class EntrypointLoaderTests(unittest.TestCase):

    def test_adoption_wrappers_isolate_bytecode_before_owner_import(self):
        """The three adoption-boundary adapters protect their own imports."""
        expected = {
            "adopt_standards",
            "apply_profile_adoption",
            "check_upstream_components",
        }
        policy, _raw = agent_interface_policy.load_policy(REPOSITORY)
        descriptors = {
            row["tool"]: entrypoint_loader.describe_entrypoint(row["tool"])
            for row in policy["tools"]
            if row["tool"] in expected
        }
        self.assertEqual(expected, set(descriptors))

        for tool, descriptor in sorted(descriptors.items()):
            with self.subTest(tool=tool):
                path = REPOSITORY / descriptor.invocation_path
                tree = ast.parse(path.read_text(encoding="utf-8"))
                owner_import = [
                    index for index, node in enumerate(tree.body)
                    if isinstance(node, ast.ImportFrom) and
                    node.module == descriptor.implementation_module
                ]
                self.assertEqual(1, len(owner_import))
                owner_index = owner_import[0]
                prelude = ast.Module(
                    body=tree.body[:owner_index], type_ignores=[])
                assignments = {
                    ast.unparse(target): ast.unparse(node.value)
                    for node in prelude.body
                    if isinstance(node, ast.Assign)
                    for target in node.targets
                }
                self.assertEqual(
                    "_external_pycache_prefix()",
                    assignments.get("_CAMBIUM_PYCACHE_PREFIX"))
                self.assertEqual(
                    "_CAMBIUM_PYCACHE_PREFIX",
                    assignments.get(
                        "os.environ['PYTHONPYCACHEPREFIX']"))
                self.assertEqual(
                    "'1'",
                    assignments.get(
                        "os.environ['PYTHONDONTWRITEBYTECODE']"))
                self.assertEqual(
                    "_CAMBIUM_PYCACHE_PREFIX",
                    assignments.get("sys.pycache_prefix"))
                self.assertEqual(
                    "True", assignments.get("sys.dont_write_bytecode"))

                helpers = [
                    node for node in prelude.body
                    if isinstance(node, ast.FunctionDef) and
                    node.name == "_external_pycache_prefix"
                ]
                self.assertEqual(1, len(helpers))
                calls = {
                    ast.unparse(node.func)
                    for node in ast.walk(helpers[0])
                    if isinstance(node, ast.Call)
                }
                self.assertLessEqual({
                    "tempfile.gettempdir",
                    "os.path.commonpath",
                    "os.path.lexists",
                }, calls)

    def test_every_registered_cli_resolves_one_distinct_implementation(self):
        policy, _raw = agent_interface_policy.load_policy(REPOSITORY)
        descriptors = [
            entrypoint_loader.describe_entrypoint(row["tool"])
            for row in policy["tools"]
        ]

        self.assertEqual(len(descriptors), len(policy["tools"]))
        self.assertEqual(
            len(descriptors),
            len({row.implementation_path for row in descriptors}),
        )
        for descriptor in descriptors:
            with self.subTest(tool=descriptor.tool):
                self.assertEqual(
                    "Tools/%s.py" % descriptor.tool,
                    descriptor.invocation_path)
                self.assertNotEqual(
                    descriptor.invocation_path,
                    descriptor.implementation_path)
                self.assertTrue(
                    (REPOSITORY / descriptor.implementation_path).is_file())
                self.assertEqual(
                    descriptor,
                    entrypoint_loader.entrypoint_for_implementation_path(
                        descriptor.implementation_path),
                )

    def test_wrappers_alone_own_the_external_cli_surface(self):
        policy, _raw = agent_interface_policy.load_policy(REPOSITORY)
        descriptors = entrypoint_loader.discover_entrypoints(
            REPOSITORY / "Tools")
        facts = module_boundary_facts.collect(REPOSITORY)

        self.assertEqual(
            {row["tool"] for row in policy["tools"]},
            set(module_boundary_facts.cli_modules(facts)),
        )
        for descriptor in descriptors:
            implementation = descriptor.implementation_module[len("Tools."):]
            with self.subTest(tool=descriptor.tool):
                self.assertTrue(facts[descriptor.tool]["cli_entrypoint"])
                self.assertFalse(facts[implementation]["cli_entrypoint"])

    def test_runtime_identity_is_loaded_from_owner_not_public_adapter(self):
        public_source = (REPOSITORY / "Tools/check_profile.py").read_text(
            encoding="utf-8")
        public_names = {
            target.id
            for node in ast.parse(public_source).body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (node.targets if isinstance(node, ast.Assign)
                           else (node.target,))
            if isinstance(target, ast.Name)
        }
        self.assertNotIn("TOOL", public_names)

        implementation = entrypoint_loader.load_tool_implementation(
            "check_profile")
        self.assertEqual("check_profile", implementation.TOOL)

    def test_missing_marker_is_optional_only_for_a_direct_fixture(self):
        with tempfile.TemporaryDirectory() as workspace:
            tools = Path(workspace) / "Tools"
            tools.mkdir()
            (tools / "sample.py").write_text(
                "VALUE = 1\n",
                encoding="utf-8")

            with self.assertRaisesRegex(
                    entrypoint_loader.EntrypointResolutionError,
                    "exactly one IMPLEMENTATION_MODULE"):
                entrypoint_loader.describe_entrypoint(
                    "sample", tools, require_marker=True)
            descriptor = entrypoint_loader.describe_entrypoint(
                "sample", tools, require_marker=False)
            self.assertEqual("Tools/sample.py", descriptor.implementation_path)

    def test_optional_mode_never_hides_a_malformed_marker(self):
        cases = {
            "duplicate": (
                "IMPLEMENTATION_MODULE = 'Tools.a.b'\n"
                "IMPLEMENTATION_MODULE = 'Tools.a.c'\n",
                "exactly one IMPLEMENTATION_MODULE"),
            "nonliteral": (
                "IMPLEMENTATION_MODULE = choose_owner()\n",
                "must be one literal module name"),
            "invalid": (
                "IMPLEMENTATION_MODULE = 'elsewhere.owner'\n",
                "not a qualified Tools module"),
        }
        with tempfile.TemporaryDirectory() as workspace:
            tools = Path(workspace) / "Tools"
            tools.mkdir()
            for name, (source, message) in cases.items():
                with self.subTest(name=name):
                    (tools / "sample.py").write_text(
                        source, encoding="utf-8")
                    with self.assertRaisesRegex(
                            entrypoint_loader.EntrypointResolutionError,
                            message):
                        entrypoint_loader.describe_entrypoint(
                            "sample", tools, require_marker=False)

    def test_parser_is_captured_from_the_unique_implementation_owner(self):
        with tempfile.TemporaryDirectory() as workspace:
            tools = Path(workspace) / "Tools"
            owner = tools / "area" / "sample.py"
            owner.parent.mkdir(parents=True)
            (tools / "sample.py").write_text(
                "IMPLEMENTATION_MODULE = 'Tools.area.sample'\n"
                "def main(argv=None):\n"
                "    parser = __import__('argparse').ArgumentParser()\n"
                "    parser.add_argument('--wrapper-only')\n"
                "    return parser.parse_args(argv)\n",
                encoding="utf-8")
            owner.write_text(
                "import argparse\n"
                "def main(argv=None):\n"
                "    parser = argparse.ArgumentParser()\n"
                "    parser.add_argument('--implementation-only')\n"
                "    return parser.parse_args(argv)\n",
                encoding="utf-8")

            original_parse_args = argparse.ArgumentParser.parse_args
            parser = entrypoint_loader.capture_argument_parser(
                "sample", tools)
            destinations = {action.dest for action in parser._actions}

            self.assertIn("implementation_only", destinations)
            self.assertNotIn("wrapper_only", destinations)
            self.assertIs(argparse.ArgumentParser.parse_args,
                          original_parse_args)

    def test_discovery_rejects_a_direct_hybrid_cli(self):
        with tempfile.TemporaryDirectory() as workspace:
            tools = Path(workspace) / "Tools"
            tools.mkdir()
            (tools / "sample.py").write_text(
                "def main(argv=None):\n"
                "    return 0\n",
                encoding="utf-8")

            with self.assertRaisesRegex(
                    entrypoint_loader.EntrypointResolutionError,
                    "exactly one IMPLEMENTATION_MODULE"):
                entrypoint_loader.discover_entrypoints(tools)


if __name__ == "__main__":
    unittest.main()
