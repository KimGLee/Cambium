"""Ownership tests for the compiled CLI invocation contract.

``argparse`` and ``agent-interface-policy.yaml`` remain the machine owners of
the invocation and capability inputs. This suite tests the compiler's join,
source closure, deterministic projection, and write/check lifecycle without
copying the current CLI dictionary into test code. MCP and Host projections
have their own consumer suites; one test here alone owns compiler CLI
transport.
"""

import argparse
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

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
        for declaration in self.policy["tools"]:
            self.assertEqual(self.policy["output_contracts"][declaration["output"]],
                             records[declaration["tool"]]["agent_interface"]["output"])
        self.assertEqual(self.contract["tool_count"], len(records))
        self.assertEqual(
            self.contract["agent_interface_policy"]["sha256"],
            kblib.sha256_bytes(self.policy_raw))

        expected_sources = {
            compiler.DEFAULT_INTERFACE_POLICY,
            compiler.DEFAULT_RUNTIME_PATH_REGISTRY,
            compiler.KBLIB_RECEIPT_SOURCE,
            "Tools/platform/agent_interface/agent_interface_contract.py",
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

    def test_runner_cli_modes_share_transport_shape_not_business_fields(self):
        from Tools.execution.task_runtime import task_runtime_action
        from Tools.execution.task_runtime import task_runtime_runner
        from Tools.platform.common import reporting

        # One current action object, not a copied Runner response schema.
        action_fields = dict(
            schema_version=task_runtime_action.SCHEMA_VERSION,
            disposition="invoke", token="activate-ready-batch:B1",
            capability_id="task-runtime-runner-v1", tool="run_task",
            target={}, arguments={}, required_input=None, binding={},
            reason_code="mode-fixture")
        action = task_runtime_action.build_action(**action_fields)
        action_fields.update(disposition="terminal", token="archive-terminal-runtime",
                             capability_id=None, tool=None)
        boundary = task_runtime_action.build_action(**action_fields)
        record = by_tool(self.contract)["run_task"]
        modes = ([], ["--execute", action["action_id"]],
                 ["--run-until-boundary"], ["--input", "unused"])
        for arguments in modes:
            with self.subTest(arguments=arguments), \
                    mock.patch.object(task_runtime_runner, "next_action",
                                      side_effect=[action, boundary]), \
                    mock.patch.object(task_runtime_runner, "_internal_step",
                                      return_value=subprocess.CompletedProcess(
                                          [], 0, stdout="{}\n", stderr="")), \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = task_runtime_runner.main(["/fixture", *arguments])
            raw = stdout.getvalue().encode("utf-8")
            observed = reporting.observe_tool_output(
                record["agent_interface"]["output"], raw, code, {},
                host_boundary=record["host_environment_boundary"])
            self.assertTrue(observed["output_reliable"], observed)
            self.assertEqual("parsed", observed["stdout_parse"])
            self.assertEqual(json.loads(raw), observed["stdout_json"])


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
        # The negative syntax index must not suppress normalized Python
        # identifiers or mistake a Unicode line separator inside a string
        # for a source line. Nested imports retain their lexical BFS binding.
        source = (
            'marker = "first\u2028second"\n'
            'def build():\n'
            '    from Tools.platform.common import kblib as receipts\n'
            '    value = receipts.ｍake_receipt("x", "1", "c", "t", "pass", "d", 0)\n'
            '    value["normalized_field"] = True\n'
            '    return value\n')
        fields, extraction, _sources = compiler._ReceiptExtensionAnalyzer(
            str(self.fixture.root), {}).analyze("Tools.normalized", source)
        self.assertEqual((["normalized_field"], "complete"), (fields, extraction))

    def test_same_owner_inputs_render_identically_without_process_replay(self):
        first = compiler.render(self.contract)
        original = compiler._ReceiptExtensionAnalyzer._load_module
        extracted = []
        analyzers = []
        def load(analyzer, module_name, source_text=None):
            analyzers.append(analyzer)
            if module_name not in analyzer.modules:
                extracted.append(module_name)
            return original(analyzer, module_name, source_text)
        with mock.patch.object(compiler._ReceiptExtensionAnalyzer, "_load_module", load), \
                mock.patch.object(compiler, "_scope_nodes", wraps=compiler._scope_nodes) as walk:
            second = compiler.render(self.fixture.compile())
            # Reading the same helper from another CLI may reuse syntax, not
            # graph-dependent resolution or another tool's mutable result.
            shared = analyzers[0].modules
            source = shared["Tools.fixture_receipts"]["source"]
            separate = compiler._ReceiptExtensionAnalyzer(str(self.fixture.root), shared)
            expected = separate.analyze("Tools.fixture_receipts", source)
            count = walk.call_count
            self.assertEqual(expected, compiler._ReceiptExtensionAnalyzer(
                str(self.fixture.root), shared).analyze("Tools.fixture_receipts", source))
            self.assertEqual(count, walk.call_count)
            scopes = [id(call.args[0]) for call in walk.call_args_list]
            self.assertEqual(len(scopes), len(set(scopes)))
            # Parser-only scopes were already classified during source
            # discovery. They do not pay another full AST receipt walk.
            self.assertNotIn("main", [getattr(call.args[0], "name", None)
                                      for call in walk.call_args_list])
        self.assertEqual(first, second)
        self.assertEqual(len(extracted), len(set(extracted)))
        self.assertEqual(1, len({id(analyzer.modules) for analyzer in analyzers}))
        self.assertGreater(len({id(analyzer.factory_cache) for analyzer in analyzers}), 1)

    def test_host_boundary_is_derived_from_the_actual_wrapper_import(self):
        path = self.fixture.tools / "shape.py"
        original = path.read_text(encoding="utf-8")
        variants = (
            ("from Tools.platform.common.reporting import host_environment_boundary as bound\n",
             "@bound\n", True),
            ("import Tools.platform.common.reporting as reporter\n",
             "@reporter.host_environment_boundary\n", True),
            ("from unrelated import host_environment_boundary as bound\n",
             "@bound\n", False),
            ("from Tools.platform.common.reporting import host_environment_boundary as bound\nbound = None\n",
             "@bound\n", False),
            ("from Tools.platform.common.reporting import host_environment_boundary as bound\n",
             "", False),
        )
        try:
            for imports, decorator, expected in variants:
                with self.subTest(imports=imports, decorator=decorator):
                    path.write_text(imports + original.replace(
                        "def main(argv=None):", decorator + "def main(argv=None):"),
                        encoding="utf-8")
                    contract = self.fixture.compile()
                    self.assertEqual(expected, by_tool(contract)["shape"]["host_environment_boundary"])
        finally:
            path.write_text(original, encoding="utf-8")


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

        def remove_output(document):
            document["tools"][0].pop("output")

        def invent_json_selector(document):
            output = document["output_contracts"][document["tools"][0]["output"]]
            output.update(mode="json-option", json_argument="label", json_value=True,
                          json_types=["object"])

        def duplicate_output(document):
            document["output_contracts"]["duplicate"] = copy.deepcopy(next(iter(document["output_contracts"].values())))

        def unused_output(document):
            output = copy.deepcopy(next(iter(document["output_contracts"].values())))
            output["empty_exit_codes"] = []
            document["output_contracts"]["unused"] = output

        def non_boolean_empty_success_condition(document):
            output = document["output_contracts"][document["tools"][0]["output"]]
            output.update(mode="always-json", json_types=["object"],
                          empty_exit_codes=[0, 1],
                          empty_success_disabled_by=["label"])

        cases = (
            (unclassify, "unclassified=label"),
            (use_non_boolean_activation, "must name one store_true"),
            (use_unknown_runtime_identity,
             "unknown runtime_path_id not-registered"),
            (use_literal_runtime_path, "must use runtime_path_id"),
            (remove_output, "must reference one declared output contract"),
            (invent_json_selector, "boolean selector must use store_true"),
            (duplicate_output, "duplicate output contract"),
            (unused_output, "unused output contracts"),
            (non_boolean_empty_success_condition,
             "empty_success_disabled_by must name a store_true option"),
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

    def test_checked_view_rechecks_components_discovery_environment_and_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Tools" / "owner.py"
            source.parent.mkdir()
            source.write_text("value = 1\n", encoding="utf-8")
            validator = mock.Mock(return_value={
                "artifact": "cli-invocation-contract", "source_hash": "source",
                "projection_target": "carried-runtime",
                "tools": [{"tool": "sample", "arguments": []},
                          {"tool": "other", "arguments": []}]})
            def load(target="carried-runtime", raw=b"projection"):
                validator.return_value["projection_target"] = target
                return compiler.checked_tool(root, target, raw, "sample", validator, lambda: raw)
            with compiler.checked_view_scope():
                load()["arguments"].append("forged")
                self.assertEqual({"tool": "sample", "arguments": [],
                                  "invocation_contract_source_hash": "source"}, load())
                self.assertEqual(1, validator.call_count)
                with mock.patch.object(compiler, "deepcopy", wraps=copy.deepcopy) as detach:
                    load()
                self.assertEqual([mock.call({"tool": "sample", "arguments": []})],
                                 detach.call_args_list)
                # Runtime writes do not change the compiler's immutable input.
                (root / ".cambium").mkdir()
                (root / ".cambium" / "receipt").write_text("new", encoding="utf-8")
                load()
                self.assertEqual(1, validator.call_count)
                for relative in ("Tools/owner.py", "Tools/new_adapter.py",
                                 "Tools/policy.yaml", "kernel/registry.yaml",
                                 "distribution-boundary.yaml"):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("changed", encoding="utf-8")
                    before = validator.call_count
                    load()
                    self.assertEqual(before + 1, validator.call_count)
                (root / "Tools/new_adapter.py").unlink()
                load()
                load(raw=b"new projection")
                load(target="source-distribution")
                with mock.patch.dict(os.environ, {"CAMBIUM_TEST_VIEW": "changed"}):
                    load()
                self.assertEqual(10, validator.call_count)
            load()
            self.assertEqual(11, validator.call_count)
            # A mutation during validation does not seed an accepted view.
            def unstable():
                source.write_text("changed again", encoding="utf-8")
                return {}
            with compiler.checked_view_scope():
                with self.assertRaisesRegex(compiler.ContractError, "inputs changed"):
                    compiler.checked_tool(root, "carried-runtime", b"x", "sample", unstable, lambda: b"x")
                load()
            self.assertEqual(12, validator.call_count)
            with self.assertRaisesRegex(compiler.ContractError, "0 entries"):
                compiler.checked_tool(root, "carried-runtime", b"projection", "absent",
                                      validator, lambda: b"projection")
            for invalid in ({}, dict(validator.return_value, projection_target="wrong"),
                            dict(validator.return_value, tools=[{"tool": "sample"}] * 2)):
                with self.assertRaises(compiler.ContractError):
                    compiler.checked_tool(root, "carried-runtime", b"x", "sample",
                                          lambda: invalid, lambda: b"x")
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
