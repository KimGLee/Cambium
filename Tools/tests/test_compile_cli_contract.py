"""Ownership tests for the compiled CLI invocation contract.

``argparse`` and ``agent-interface-policy.yaml`` remain the machine owners of
the invocation and capability inputs. This suite tests the compiler's join,
source closure, deterministic projection, and write/check lifecycle without
copying the current CLI dictionary into test code. MCP and Host projections
have their own consumer suites; one test here alone owns compiler CLI
transport.
"""

import argparse
import copy
from pathlib import Path
import unittest

from Tools.execution.task_runtime import runtime_paths
from Tools.platform.agent_interface import agent_interface_policy
from Tools.platform.agent_interface import compile_cli_contract as compiler
from Tools.platform.agent_interface import entrypoint_loader
from Tools.platform.agent_interface import tool_availability
from Tools.platform.common import kblib
from Tools.tests.support.cli_contract_fixture import CliContractFixture


REPOSITORY = Path(__file__).resolve().parents[2]


def by_tool(contract):
    return {record["tool"]: record for record in contract["tools"]}


class CurrentCliOwnerClosureTests(unittest.TestCase):
    """Contract: current parser, policy, and implementation owners join once."""

    @classmethod
    def setUpClass(cls):
        cls.contract = compiler.compile_contract(
            REPOSITORY, tool_availability.SOURCE_DISTRIBUTION)
        cls.policy, cls.policy_raw = agent_interface_policy.load_policy(
            REPOSITORY)
        cls.descriptors = entrypoint_loader.discover_entrypoints(
            REPOSITORY / "Tools")

    def test_compiled_surface_is_the_exact_join_of_current_machine_owners(self):
        records = by_tool(self.contract)
        descriptors = {row.tool: row for row in self.descriptors}
        policy_tools = {row["tool"] for row in self.policy["tools"]}

        self.assertEqual(set(records), set(descriptors))
        self.assertEqual(set(records), policy_tools)
        self.assertEqual(self.contract["tool_count"], len(records))
        self.assertEqual(
            self.contract["agent_interface_policy"]["sha256"],
            kblib.sha256_bytes(self.policy_raw))

        expected_sources = {
            compiler.DEFAULT_INTERFACE_POLICY,
            compiler.DEFAULT_RUNTIME_PATH_REGISTRY,
            compiler.KBLIB_RECEIPT_SOURCE,
        }
        for tool, descriptor in descriptors.items():
            record = records[tool]
            expected_sources.update((
                descriptor.invocation_path,
                descriptor.implementation_path,
            ))
            expected_sources.update(
                row["path"] for row in record["receipt_extension_sources"])
            with self.subTest(tool=tool):
                self.assertEqual(record["module"], descriptor.invocation_path)
                self.assertEqual(
                    record["implementation_path"],
                    descriptor.implementation_path)
                self.assertEqual(
                    record["source_hash"],
                    kblib.sha256_bytes(
                        descriptor.invocation_source.encode("utf-8")))
                self.assertEqual(
                    record["implementation_source_hash"],
                    kblib.sha256_bytes(
                        descriptor.implementation_source.encode("utf-8")))
        self.assertEqual(set(self.contract["source_files"]), expected_sources)

    def test_receipt_shape_is_projected_from_the_common_envelope_owner(self):
        owner_record = kblib.make_receipt(
            "owner-probe", "0", "shape", "shape", "pass", "shape", 0,
            receipt_type_id="owner-probe-receipt-v1", identity={},
        )
        shape = self.contract["receipt_shape"]

        self.assertEqual(
            set(shape), {
                "common_envelope_owner", "common_envelope_fields",
                "extension_policy",
            })
        self.assertEqual(
            shape["common_envelope_owner"],
            compiler.COMMON_RECEIPT_ENVELOPE_OWNER)
        self.assertEqual(
            shape["common_envelope_fields"], list(owner_record))
        self.assertIn("receipt_type_id", shape["common_envelope_fields"])
        self.assertNotIn("gate_id", shape["common_envelope_fields"])
        self.assertIn(compiler.KBLIB_RECEIPT_SOURCE,
                      self.contract["source_files"])


class CliContractUnitTests(unittest.TestCase):

    def test_choice_sets_have_one_canonical_projection_order(self):
        self.assertEqual(
            compiler.normalize_choices(
                REPOSITORY, ("gamma", "alpha", "beta")),
            compiler.normalize_choices(
                REPOSITORY, {"beta", "gamma", "alpha"}),
        )


class CompilerFixtureContractTests(unittest.TestCase):
    """Contract: one parser checkpoint covers compiler-only derivations."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = CliContractFixture()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.marker = cls.fixture.root / "tool-body-ran"
        cls.fixture.write_tool("shape", """
            import argparse
            import os

            ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Shape fixture")
                parser.add_argument("root", help="workspace")
                parser.add_argument("--output", default=os.path.join(
                    ROOT, "Tools", "out.yaml"), help="projection")
                parser.add_argument("--limit", type=int, default=3)
                group = parser.add_mutually_exclusive_group(required=True)
                group.add_argument("--apply", action="store_true")
                group.add_argument("--revert", action="store_true")
                args = parser.parse_args(argv)
                open(%r, "w").write("unexpected execution")
                return args
        """ % str(cls.marker))
        cls.fixture.write_tool("static_receipt", """
            import argparse
            from Tools.platform.common import kblib

            def emit():
                receipt = kblib.make_receipt(
                    "sample", "1.0.0", "c", "t", "pass", "d", 1,
                    receipt_type_id="fixture-receipt-v1")
                receipt.update({"scan_id": "s", "checked_at": "z"})
                receipt["gate_id"] = "g"
                return receipt

            def main(argv=None):
                parser = argparse.ArgumentParser()
                return parser.parse_args(argv)
        """)
        cls.fixture.write_tool("dynamic_receipt", """
            import argparse
            from Tools.platform.common import kblib

            def emit(name):
                receipt = kblib.make_receipt(
                    "sample", "1.0.0", "c", "t", "pass", "d", 1,
                    receipt_type_id="fixture-receipt-v1")
                receipt[name] = "value"
                return receipt

            def main(argv=None):
                parser = argparse.ArgumentParser()
                return parser.parse_args(argv)
        """)
        cls.fixture.write_library("fixture_receipts.py", """
            from Tools.platform.common import kblib

            def make_fixture_receipt(payload=None, runtime_errors=None):
                receipt = kblib.make_receipt(
                    "sample", "1.0.0", "c", "t", "pass", "d", 1,
                    receipt_type_id="fixture-receipt-v1")
                receipt["helper_field"] = payload
                if runtime_errors:
                    receipt.update(runtime_errors)
                return receipt
        """)
        cls.fixture.write_tool("imported_receipt", """
            import argparse
            from Tools.fixture_receipts import make_fixture_receipt

            def emit():
                return make_fixture_receipt(
                    payload="value", runtime_errors={"dynamic": True})

            def main(argv=None):
                parser = argparse.ArgumentParser()
                return parser.parse_args(argv)
        """)
        cls.fixture.write_library("helper.py", """
            def helper():
                return 1
        """)
        cls.policy = cls.fixture.write_policy()
        cls.contract = cls.fixture.compile()

    def test_argument_and_group_shape_are_derived_from_argparse(self):
        record = by_tool(self.contract)["shape"]
        parser = entrypoint_loader.capture_argument_parser(
            "shape", self.fixture.tools, require_marker=True)
        actions = [
            action for action in parser._actions
            if not (type(action).__name__ == "_HelpAction" and
                    action.default is argparse.SUPPRESS)
        ]
        self.assertEqual(
            [item["dest"] for item in record["arguments"]],
            [action.dest for action in actions])
        self.assertEqual(
            [item["option_strings"] for item in record["arguments"]],
            [list(action.option_strings) for action in actions])

        arguments = {item["dest"]: item for item in record["arguments"]}
        self.assertEqual(arguments["output"]["default"], "Tools/out.yaml")
        self.assertEqual(
            (arguments["limit"]["default"],
             arguments["limit"]["default_type"],
             arguments["limit"]["type"]),
            (3, "int", "int"))
        expected_groups = [
            {"required": bool(group.required),
             "dests": [action.dest for action in group._group_actions]}
            for group in parser._mutually_exclusive_groups
            if group._group_actions
        ]
        self.assertEqual(record["mutually_exclusive_groups"], expected_groups)

    def test_introspection_stops_before_behavior_and_ignores_libraries(self):
        self.assertFalse(self.marker.exists())
        self.assertNotIn("helper", by_tool(self.contract))
        self.assertNotIn("fixture_receipts", by_tool(self.contract))

    def test_receipt_source_closure_classifies_static_and_dynamic_fields(self):
        records = by_tool(self.contract)
        expected = {
            "static_receipt": (["gate_id", "scan_id"], "complete"),
            "dynamic_receipt": ([], "partial"),
            "imported_receipt": (["helper_field"], "partial"),
        }
        for tool, result in expected.items():
            with self.subTest(tool=tool):
                record = records[tool]
                self.assertEqual(
                    (record["receipt_extensions"],
                     record["receipt_extensions_extraction"]),
                    result)
        imported_sources = {
            row["path"]
            for row in records["imported_receipt"][
                "receipt_extension_sources"]
        }
        self.assertIn("Tools/fixture_receipts.py", imported_sources)

    def test_same_owner_inputs_render_identically_without_process_replay(self):
        first = compiler.render(self.contract)
        second = compiler.render(self.fixture.compile())
        self.assertEqual(first, second)


class AgentInterfaceJoinContractTests(unittest.TestCase):
    """Contract: compiler closes parser arguments over the policy relation."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = CliContractFixture()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.fixture.write_tool("sample", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Policy fixture")
                parser.add_argument("root")
                parser.add_argument("--output", default="reports/out.md")
                parser.add_argument("--apply", action="store_true")
                parser.add_argument("--label")
                return parser.parse_args(argv)
        """)
        cls.policy = cls.fixture.policy_document()
        row = cls.policy["tools"][0]
        row.update({
            "exposure": "mcp",
            "workspace_argument": "root",
            "workspace_access": "write",
            "value_arguments": ["apply", "label"],
            "write_paths": ["output"],
        })
        cls.policy["path_overrides"] = [{
            "tool": "sample",
            "argument": "output",
            "constraint": "namespace",
            "runtime_path_id": "report-root",
            "suffixes": [".md"],
        }]
        cls.policy["path_activation_overrides"] = [{
            "tool": "sample",
            "argument": "output",
            "active_when_any": ["apply"],
            "inactive_when_any": [],
        }]
        cls.fixture.write_policy(cls.policy)
        cls.contract = cls.fixture.compile()
        cls.records = copy.deepcopy(cls.contract["tools"])
        cls.availability = tool_availability.resolve(
            cls.fixture.root, tool_availability.SOURCE_DISTRIBUTION)

    def test_policy_identity_resolves_to_one_compiled_path_capability(self):
        interface = self.contract["tools"][0]["agent_interface"]
        capability, = interface["path_arguments"]
        owner = runtime_paths.path_reference_for("report-root")

        self.assertEqual(interface["value_arguments"], ["apply", "label"])
        self.assertEqual(capability["argument"], "output")
        self.assertEqual(capability["access"], "write")
        self.assertEqual(capability["consumption"], "replace")
        self.assertEqual(capability["runtime_path_id"], owner.runtime_path_id)
        self.assertEqual(capability["constraint"], owner.constraint)
        self.assertEqual(capability["value"], owner.path)
        self.assertEqual(capability["active_when_any"], ["apply"])

    def test_apply_gated_writers_are_derived_from_compiled_path_effects(self):
        self.assertEqual(
            frozenset(("sample",)),
            compiler.apply_gated_writer_tools(self.contract),
        )

        unguarded = copy.deepcopy(self.contract)
        unguarded["tools"][0]["agent_interface"]["path_arguments"][0][
            "active_when_any"] = []
        self.assertEqual(
            frozenset(), compiler.apply_gated_writer_tools(unguarded))

    def test_policy_join_fails_closed_without_redeclaring_policy_shape(self):
        def unclassify(document):
            document["tools"][0]["value_arguments"].remove("label")

        def use_non_boolean_activation(document):
            document["path_activation_overrides"][0][
                "active_when_any"] = ["label"]

        def use_unknown_runtime_identity(document):
            document["path_overrides"][0][
                "runtime_path_id"] = "not-registered"

        def use_literal_runtime_path(document):
            row = document["path_overrides"][0]
            row.pop("runtime_path_id")
            row["value"] = ".cambium/reports"

        cases = (
            (unclassify, "unclassified=label"),
            (use_non_boolean_activation, "must name one store_true"),
            (use_unknown_runtime_identity,
             "unknown runtime_path_id not-registered"),
            (use_literal_runtime_path, "must use runtime_path_id"),
        )
        try:
            for mutate, message in cases:
                with self.subTest(message=message):
                    document = copy.deepcopy(self.policy)
                    mutate(document)
                    self.fixture.write_policy(document)
                    with self.assertRaisesRegex(
                            compiler.ContractError, message):
                        compiler.load_interface_policy(
                            self.fixture.root,
                            self.records,
                            self.availability,
                        )
        finally:
            self.fixture.write_policy(self.policy)


class CompilerProjectionLifecycleTests(unittest.TestCase):
    """Integration: one local artifact distinguishes HOLD from bad evidence."""

    def test_write_check_stale_and_unreliable_evidence_share_one_lifecycle(self):
        fixture = CliContractFixture()
        self.addCleanup(fixture.cleanup)
        implementation = fixture.write_tool("sample", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Lifecycle")
                parser.add_argument("root")
                return parser.parse_args(argv)
        """)
        fixture.write_policy()
        args = (
            fixture.root, "--projection-target",
            tool_availability.SOURCE_DISTRIBUTION,
        )

        missing = fixture.run_in_process(
            fixture.root, "--check", "--projection-target",
            tool_availability.SOURCE_DISTRIBUTION)
        self.assertEqual(missing.returncode, 2)

        generated = fixture.run_in_process(*args)
        current = fixture.run_in_process(
            fixture.root, "--check", "--projection-target",
            tool_availability.SOURCE_DISTRIBUTION)
        self.assertEqual(generated.returncode, 0, generated.stdout)
        self.assertEqual(current.returncode, 0, current.stdout)

        fixture.output.write_text(
            fixture.output.read_text(encoding="utf-8").replace(
                "tool_count: 1", "tool_count: 2"),
            encoding="utf-8")
        self.assertEqual(
            fixture.run_in_process(
                fixture.root, "--check", "--projection-target",
                tool_availability.SOURCE_DISTRIBUTION).returncode,
            2)

        self.assertEqual(fixture.run_in_process(*args).returncode, 0)
        implementation.write_text(
            implementation.read_text(encoding="utf-8") + "\n# drift\n",
            encoding="utf-8")
        self.assertEqual(
            fixture.run_in_process(
                fixture.root, "--check", "--projection-target",
                tool_availability.SOURCE_DISTRIBUTION).returncode,
            2)

        fixture.write_tool("sample", """
            import argparse
            raise RuntimeError("unreliable fixture")

            def main(argv=None):
                parser = argparse.ArgumentParser()
                return parser.parse_args(argv)
        """)
        unreliable = fixture.run_in_process(
            fixture.root, "--check", "--projection-target",
            tool_availability.SOURCE_DISTRIBUTION)
        self.assertEqual(unreliable.returncode, 1)
        self.assertIn("evidence is unreliable", unreliable.stdout)

    def test_projection_identity_fixes_the_current_artifact_path(self):
        fixture = CliContractFixture()
        self.addCleanup(fixture.cleanup)
        fixture.write_tool("sample", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Projection")
                parser.add_argument("root")
                return parser.parse_args(argv)
        """)
        fixture.write_policy()
        carried = fixture.root / runtime_paths.CLI_CONTRACT_ARTIFACT_PATH

        generated = fixture.run_in_process(
            fixture.root, "--projection-target",
            tool_availability.CARRIED_RUNTIME)
        self.assertEqual(generated.returncode, 0, generated.stdout)
        self.assertTrue(carried.is_file())
        self.assertFalse(fixture.output.exists())

        inferred_check = fixture.run_in_process(
            fixture.root, "--check", "--output", carried)
        self.assertEqual(
            inferred_check.returncode, 0,
            inferred_check.stdout + inferred_check.stderr)

        wrong_owner = fixture.run_in_process(
            fixture.root, "--projection-target",
            tool_availability.CARRIED_RUNTIME,
            "--output", fixture.output)
        self.assertEqual(wrong_owner.returncode, 1)
        self.assertIn("unsafe artifact output", wrong_owner.stdout)
        self.assertFalse(fixture.output.exists())


class CompilerCliTransportTests(unittest.TestCase):
    """Integration: the public compiler wrapper transports one current check."""

    def test_public_cli_transports_one_current_projection_check(self):
        fixture = CliContractFixture()
        self.addCleanup(fixture.cleanup)
        fixture.write_tool("sample", """
            import argparse

            def main(argv=None):
                parser = argparse.ArgumentParser(description="Transport")
                parser.add_argument("root")
                return parser.parse_args(argv)
        """)
        fixture.write_policy()
        generated = fixture.run_in_process(
            fixture.root, "--projection-target",
            tool_availability.SOURCE_DISTRIBUTION)
        self.assertEqual(generated.returncode, 0, generated.stdout)

        checked = fixture.run_cli(
            fixture.root, "--check", "--projection-target",
            tool_availability.SOURCE_DISTRIBUTION)
        self.assertEqual(
            checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("is current", checked.stdout)


if __name__ == "__main__":
    unittest.main()
