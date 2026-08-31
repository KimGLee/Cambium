"""Owner tests for the typed Task Runtime Runner control loop.

The Queue runtime owns state-to-token selection, ``task_runtime_action`` owns
the route and action closed sets, individual Tools own their evidence and
state transitions, and Required Queue E2E tests own complete Task lifecycles.
This file owns only the Runner's projection, dispatch, authoritative read-back,
and stop behavior between those boundaries.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]

import Tools.execution.task_runtime.task_runtime_action as action_contract  # noqa: E402
import Tools.execution.task_runtime.task_runtime_runner as runner  # noqa: E402
from Tools.execution.task_runtime import queue_runtime  # noqa: E402
from Tools.tests.support.task_runtime_object_factory import (  # noqa: E402
    parsed_runtime_state,
)


def resume_action(token, result=None):
    """Project one registered Queue token over an admitted memory state."""
    current = parsed_runtime_state() if result is None else result
    with mock.patch.object(
            runner.queue_runtime, "resume_next_action",
            return_value=token), mock.patch.object(
                runner, "_capability_tool", return_value="fixture-tool"):
        return runner._resume_action(current)


def completed(returncode=0, stdout="{}\n", stderr=""):
    """Return the Tool-process result shape consumed by the Runner."""
    return SimpleNamespace(
        returncode=returncode, stdout=stdout, stderr=stderr)


class TaskRuntimeRunnerUnitTests(unittest.TestCase):
    """Pure decisions over already-admitted, in-memory runtime states."""

    def test_next_action_projects_representative_runtime_boundaries(self):
        base = parsed_runtime_state()
        hold = parsed_runtime_state(
            blocked=[{"id": "B1", "reason": "dependency"}], remaining=1)
        cases = (
            ("invoke", base, "activate-ready-batch:B1", "invoke",
             "activate-ready-batch"),
            ("hold", hold, "resolve-holds-dependencies", "await-agent",
             "resolve-holds-dependencies"),
            ("repair", base, "repair-runtime", "repair",
             "repair-runtime"),
            ("closed", base, "archive-terminal-runtime", "terminal",
             "archive-terminal-runtime"),
        )
        for label, state, token, disposition, projected_token in cases:
            with self.subTest(label=label), mock.patch.object(
                    runner.runtime_validation, "validate_runtime",
                    return_value=state), mock.patch.object(
                        runner.queue_runtime, "resume_next_action",
                        return_value=token), mock.patch.object(
                            runner, "_capability_tool",
                            return_value="fixture-tool"):
                first = runner.next_action("/fixture")
                second = runner.next_action("/fixture")

            self.assertEqual(first, second)
            self.assertEqual(disposition, first["disposition"])
            self.assertEqual(projected_token, first["token"])
            self.assertEqual(
                "task-runtime-runner-v1" if disposition == "invoke" else None,
                first["capability_id"])
            self.assertEqual(state["queue_sha256"],
                             first["binding"]["required_queue_sha256"])
            action_contract.validate_action(first)

    def test_stale_action_identity_is_refused_before_dispatch(self):
        current = {
            "action_id": "action-" + "1" * 64,
            "disposition": "invoke",
        }
        with mock.patch.object(
                runner, "next_action", return_value=current), \
                mock.patch.object(runner, "_internal_step") as dispatch, \
                self.assertRaisesRegex(
                    runner.RunnerError, "next action changed"):
            runner.execute("/fixture", "action-" + "0" * 64)

        dispatch.assert_not_called()

    def test_open_batch_internal_route_preserves_audit_owner_outcome(self):
        state = parsed_runtime_state()
        state["items_by_id"]["B1"]["state"] = "open"
        for token, outcome in (
                ("admit-delta:B1", {
                    "disposition": "await-agent", "token": "await-review"}),
                ("resume-in-flight-batches:B1", {
                    "disposition": "invoke", "token": "invoke-producer"})):
            with self.subTest(token=token), mock.patch.object(
                    runner.queue_runtime, "resume_next_action",
                    return_value=token), mock.patch.object(
                        runner, "_audit_action",
                        return_value=outcome) as audit_owner:
                projected = runner._resume_action(state)

            self.assertIs(outcome, projected)
            audit_owner.assert_called_once_with(
                state, state["items_by_id"]["B1"])

    def test_close_action_consumes_queue_owned_transition_arguments(self):
        state = parsed_runtime_state()
        token = ("close-applied-batch:B1:queue-consistency-1:"
                 "close-gate-1:delta-apply-1")
        selected = {
            "batch": "B1",
            "queue_consistency_receipt": "queue-consistency-1",
            "close_gate_receipt": "close-gate-1",
            "delta_apply_receipt": "delta-apply-1",
        }
        expected = queue_runtime.batch_close_transition_arguments(
            state, selected)
        expected["json"] = True

        with mock.patch.object(
                runner.queue_runtime, "resume_next_action",
                return_value=token), mock.patch.object(
                    runner, "_capability_tool",
                    return_value="update_queue"):
            action = runner._resume_action(state)

        self.assertEqual(expected, action["arguments"])

    def test_run_until_boundary_stops_on_semantics_failure_and_nonprogress(self):
        invoke = resume_action("materialize-required-queue")
        boundaries = (
            resume_action("resolve-holds-dependencies"),
            resume_action("repair-runtime"),
            resume_action("archive-terminal-runtime"),
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary["disposition"]), \
                    mock.patch.object(
                        runner, "next_action", return_value=boundary), \
                    mock.patch.object(runner, "execute") as execute:
                result = runner.run_until_boundary("/fixture")
            self.assertEqual([], result["executed"])
            self.assertIs(boundary, result["next_action"])
            execute.assert_not_called()

        failed = {
            "returncode": 7,
            "output": "",
            "diagnostics": "producer refused",
            "next_action": invoke,
            "next_action_error": None,
        }
        with mock.patch.object(
                runner, "next_action", return_value=invoke), \
                mock.patch.object(
                    runner, "execute", return_value=failed):
            stopped = runner.run_until_boundary("/fixture")
        self.assertEqual(1, len(stopped["executed"]))
        self.assertEqual(7, stopped["executed"][0]["returncode"])
        self.assertIs(invoke, stopped["next_action"])

        unchanged = dict(failed, returncode=0, diagnostics="")
        with mock.patch.object(
                runner, "next_action", return_value=invoke), \
                mock.patch.object(
                    runner, "execute", return_value=unchanged), \
                self.assertRaisesRegex(
                    runner.RunnerError, "did not advance"):
            runner.run_until_boundary("/fixture")


class TaskRuntimeRunnerContractTests(unittest.TestCase):
    """One representative compiled-CLI consumption contract."""

    def test_command_consumes_compiled_positionals_and_transport_once(self):
        delta = ".cambium/deltas/B1.yaml"
        command = runner._command(
            "/fixture", "apply_delta", {
                "delta": delta,
                "apply": True,
                "json": False,
            })

        self.assertEqual(sys.executable, command[0])
        self.assertEqual(
            os.path.realpath(str(TOOLS / "apply_delta.py")), command[1])
        self.assertEqual(delta, command[2])
        self.assertNotIn("--delta", command)
        self.assertIn("--apply", command)
        self.assertEqual("/fixture",
                         command[command.index("--root") + 1])
        self.assertEqual("--json", command[-1])
        self.assertEqual(1, command.count("--json"))


class TaskRuntimeRunnerCheckpointIntegrationTests(unittest.TestCase):
    """Adjacent dispatch/read-back seams from legal memory checkpoints."""

    def test_execute_dispatches_invoke_and_await_then_returns_readback(self):
        invoke = resume_action("materialize-required-queue")
        awaiting = resume_action("resume-paused-task")
        after = resume_action("activate-ready-batch:B1")
        tool_result = completed(stdout='{"applied": true}\n')
        cases = (
            ("invoke", invoke, None),
            ("await", awaiting, {
                "task_transition": "active",
                "checkpoint_summary": "user resumes current task",
            }),
        )

        for label, action, supplied in cases:
            with self.subTest(label=label), mock.patch.object(
                    runner, "next_action",
                    side_effect=(action, after)) as readback, \
                    mock.patch.object(
                        runner, "_run_command",
                        return_value=tool_result) as dispatched, \
                    mock.patch.object(
                        runner.runtime_validation, "validate_runtime",
                        return_value=parsed_runtime_state()), \
                    mock.patch.object(
                        runner.metadata_execution_contract,
                        "capability_invocation_tool",
                        return_value="update_task"):
                outcome = runner.execute(
                    "/fixture", action["action_id"],
                    input_record=supplied)

            self.assertEqual(2, readback.call_count)
            dispatched.assert_called_once()
            self.assertEqual(action["action_id"],
                             outcome["executed_action_id"])
            self.assertEqual(0, outcome["returncode"])
            self.assertIs(after, outcome["next_action"])
            self.assertIsNone(outcome["next_action_error"])

    def test_terminal_chain_orders_producers_consumer_and_closed_readback(self):
        route = action_contract.action_route("run-terminal-audit")
        queue_receipt = {"receipt_id": "queue-pass"}
        corpus_receipt = {"receipt_id": "corpus-pass"}
        proof_receipt = {"receipt_id": "proof-pass"}
        tool_results = (
            completed(stdout=json.dumps([queue_receipt])),
            completed(stdout=json.dumps([corpus_receipt])),
            completed(stdout=json.dumps({
                "status": "produced",
                "terminal_proof_path": runner.TERMINAL_PROOF_PATH,
            })),
            completed(stdout=json.dumps([proof_receipt])),
            completed(stdout=json.dumps({"applied": True})),
        )
        admitted = {
            "errors": [],
            "progress_sha256": "sha256:" + "1" * 64,
            "queue_sha256": "sha256:" + "2" * 64,
            "progress": {"task_state": "completion-candidate"},
        }
        closed = {"errors": [], "progress": {"task_state": "complete"}}
        tools = {
            "required-queue-gate-v1": "check_queue",
            "corpus-plan-structure-gate-v1": "check_corpus_plan",
            "terminal-proof-producer-v1": "assemble_terminal_proof",
            "terminal-proof-gate-v1": "check_proof",
            "task-state-transition-v1": "update_task",
        }

        with mock.patch.object(
                runner.metadata_execution_contract,
                "capability_invocation_tool",
                side_effect=lambda capability, root=None: tools[capability]), \
                mock.patch.object(
                    runner, "_run_command",
                    side_effect=tool_results) as dispatched, \
                mock.patch.object(
                    runner, "_registered_gate_predicate",
                    return_value=object()), \
                mock.patch.object(
                    runner, "_single_json_receipt",
                    side_effect=(queue_receipt, corpus_receipt,
                                 proof_receipt)), \
                mock.patch.object(
                    runner.runtime_validation, "validate_runtime",
                    side_effect=(admitted, closed)) as readback:
            result = runner._await_terminal_audit(
                "/fixture", {}, {
                    "terminal_audit_input":
                        ".cambium/tmp/terminal-audit.yaml",
                }, route)

        self.assertEqual(0, result.returncode)
        self.assertEqual(2, readback.call_count)
        self.assertEqual(
            ["check_queue", "check_corpus_plan", "assemble_terminal_proof",
             "check_proof", "update_task"],
            [call.args[1] for call in dispatched.call_args_list])
        assembler = dispatched.call_args_list[2].args[2]
        self.assertEqual(
            runner.runtime_paths.AUDIT_RECEIPT_REGISTER_PATH,
            assembler["audit_receipt_register"])
        self.assertEqual(
            runner.TERMINAL_RECEIPT_PATH,
            assembler["terminal_audit_receipt_register"])
        writer = dispatched.call_args_list[4].args[2]
        self.assertEqual("proof-pass", writer["terminal_proof_receipt"])


if __name__ == "__main__":
    unittest.main()
