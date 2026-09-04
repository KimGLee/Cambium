"""Contract and one adjacent seam for the Gate sweep dispatcher.

Gate identity, producer identity, Receipt shape, and Receipt consumption have
their own machine owners and tests. This module therefore verifies only the
additional responsibility of ``run_gates``: derive the unscoped sweep from
the current Control registry, resolve each runnable producer to one command,
and dispatch a shared command once while preserving every diagnostic outcome.
The sweep does not create Gate evidence; typed Receipt production and
consumption remain with their respective owners.
"""

from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest import mock

from Tools.execution.task_runtime import queue_runtime
from Tools.governance.control import run_gates
from Tools.platform.agent_interface import compile_cli_contract
from Tools.platform.agent_interface import tool_availability


REPOSITORY = Path(__file__).resolve().parents[2]
EXAMPLE_PROFILE = "profiles/examples/agent-atlas/profile.md"
CONFIGURED_PROFILE = "profiles/examples/worked-planning/profile.md"


class RunGatesContractTests(unittest.TestCase):
    """Registry-to-command projection without subprocess or runtime state."""

    @classmethod
    def setUpClass(cls):
        cls.registry, errors = queue_runtime.standards_gate_registry(
            str(REPOSITORY))
        if errors:
            raise AssertionError("\n".join(errors))
        cls.recipes = run_gates._recipes(
            str(REPOSITORY), EXAMPLE_PROFILE, [])
        cls.interface_contract = compile_cli_contract.compile_contract(
            str(REPOSITORY), tool_availability.SOURCE_DISTRIBUTION)
        cls.transaction_writers = \
            compile_cli_contract.apply_gated_writer_tools(
                cls.interface_contract)

    def test_registry_projection_is_total_unique_and_position_bounded(self):
        derived, errors = run_gates.derive_verification_set(
            str(REPOSITORY), self.registry, self.recipes,
            self.transaction_writers)

        expected = {
            gate_id for gate_id, predicate in self.registry.items()
            if predicate["lifecycle_states"] == ("not-batch-scoped",)
        }
        identities = [gate_id for gate_id, _kind, _command in derived]
        self.assertEqual([], errors)
        self.assertEqual(expected, set(identities))
        self.assertEqual(len(identities), len(set(identities)))
        expected_transactions = {
            gate_id for gate_id, predicate in self.registry.items()
            if predicate["lifecycle_states"] == ("not-batch-scoped",) and
            predicate["tool"] in self.transaction_writers
        }
        self.assertEqual(
            expected_transactions,
            {gate_id for gate_id, kind, _command in derived
             if kind == "transaction"},
        )
        for _gate_id, kind, command in derived:
            self.assertIn(kind, ("run", "manual", "transaction"))
            if kind != "run":
                self.assertIsNone(command)

    def test_runnable_commands_follow_registry_tool_and_mode_groups(self):
        derived, errors = run_gates.derive_verification_set(
            str(REPOSITORY), self.registry, self.recipes,
            self.transaction_writers)
        self.assertEqual([], errors)

        commands_by_selector = {}
        for gate_id, kind, command in derived:
            predicate = self.registry[gate_id]
            if kind != "run" or command is None:
                continue
            self.assertGreaterEqual(len(command), 2)
            self.assertNotIn(
                "--receipts", command,
                "run_gates is a diagnostic sweep, not a Receipt producer",
            )
            self.assertEqual(
                predicate["tool"], Path(command[1]).stem,
                "the dispatcher must invoke the producer named by the "
                "registry, not a local Gate allowlist",
            )
            selector = (predicate["tool"], predicate["mode"])
            previous = commands_by_selector.setdefault(
                selector, tuple(command))
            self.assertEqual(previous, tuple(command))

    def test_profile_none_omits_quota_arguments_and_marks_gate_not_applicable(self):
        command = self.recipes[("check_vocab", "vocab-check-summary", "*")]
        self.assertNotIn("--quota-p0", command)
        self.assertNotIn("--quota-p1", command)
        self.assertNotIn("--policy-fingerprint", command)
        self.assertIsNone(
            self.recipes[(
                "check_vocab", "priority-quota-distribution", "*")])

    def test_profile_configured_projects_the_exact_pair_to_one_command(self):
        recipes = run_gates._recipes(
            str(REPOSITORY), CONFIGURED_PROFILE, [])
        command = recipes[(
            "check_vocab", "priority-quota-distribution", "*")]

        self.assertIsNotNone(command)
        self.assertEqual(
            command,
            recipes[("check_vocab", "vocab-check-summary", "*")])
        self.assertEqual(
            "10.0", command[command.index("--quota-p0") + 1])
        self.assertEqual(
            "30.0", command[command.index("--quota-p1") + 1])
        fingerprint = command[command.index("--policy-fingerprint") + 1]
        self.assertRegex(fingerprint, r"^sha256:[0-9a-f]{64}$")

    def test_missing_runnable_producer_recipe_fails_closed(self):
        registry = {
            "future-gate": {
                "tool": "future_producer",
                "mode": "*",
                "lifecycle_states": ("not-batch-scoped",),
            }
        }

        derived, errors = run_gates.derive_verification_set(
            "/synthetic", registry, {}, frozenset())

        self.assertEqual([], derived)
        self.assertEqual(1, len(errors))
        self.assertIn("future-gate", errors[0])
        self.assertIn("future_producer", errors[0])

    def test_preflight_projection_target_comes_from_profile_location(self):
        cases = (
            (EXAMPLE_PROFILE, tool_availability.SOURCE_DISTRIBUTION),
            ("profiles/selected/profile.md",
             tool_availability.CARRIED_RUNTIME),
        )
        for manifest, expected_target in cases:
            with self.subTest(manifest=manifest):
                rows = run_gates._preflight_commands(
                    str(REPOSITORY), manifest)
                interface_commands = [
                    command for _capability, label, command in rows
                    if label in (
                        "compile_cli_contract --check",
                        "render_interface_projection --check",
                    )
                ]
                self.assertEqual(2, len(interface_commands))
                for command in interface_commands:
                    index = command.index("--projection-target")
                    self.assertEqual(expected_target, command[index + 1])


class RunGatesDispatchIntegrationTests(unittest.TestCase):
    """One in-process registry -> dispatcher -> outcome-reporting seam."""

    def test_shared_producer_command_runs_once_for_multiple_gate_outcomes(self):
        command = ["python3", "/tools/shared_producer.py", "/repo"]
        registry = {
            gate_id: {
                "tool": "shared_producer",
                "mode": "*",
                "lifecycle_states": ("not-batch-scoped",),
            }
            for gate_id in ("gate-alpha", "gate-beta")
        }
        calls = []

        def run_once(actual):
            calls.append(tuple(actual))
            return 0, "producer passed\n"

        output = io.StringIO()
        with mock.patch.object(
                run_gates.queue_runtime, "standards_gate_registry",
                return_value=(registry, [])), mock.patch.object(
                run_gates.queue_runtime, "gate_registry_producer_errors",
                return_value=[]), mock.patch.object(
                run_gates, "_selected_profile",
                return_value="profiles/selected/profile.md"), \
                mock.patch.object(
                    run_gates, "_recipes",
                    return_value={("shared_producer", "*"): command}), \
                mock.patch.object(
                    run_gates.compile_cli_contract, "compile_contract",
                    return_value={"tools": []}), \
                mock.patch.object(
                    run_gates.compile_cli_contract,
                    "apply_gated_writer_tools",
                    return_value=frozenset()), \
                mock.patch.object(
                    run_gates, "_preflight_commands", return_value=[]), \
                mock.patch.object(
                    run_gates, "_boundary_findings",
                    return_value=([], [])), mock.patch.object(
                    run_gates, "_run", side_effect=run_once), \
                redirect_stdout(output):
            code = run_gates.main([
                "/repo", "--profile", "profiles/selected"])

        self.assertEqual(0, code)
        self.assertEqual([tuple(command)], calls)
        text = output.getvalue()
        self.assertIn("[PASS] gate-alpha", text)
        self.assertIn("[PASS] gate-beta (same run as above)", text)
        self.assertIn("gates=2 failures=0 holds=0", text)


if __name__ == "__main__":
    unittest.main()
