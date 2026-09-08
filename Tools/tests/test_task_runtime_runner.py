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
import tempfile
from types import SimpleNamespace
import sys
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]

import Tools.execution.task_runtime.task_runtime_action as action_contract  # noqa: E402
import Tools.execution.task_runtime.task_runtime_runner as runner  # noqa: E402
from Tools.execution.task_runtime import queue_runtime  # noqa: E402
from Tools.execution.task_runtime import runtime_paths  # noqa: E402
from Tools.platform.agent_interface import compile_cli_contract  # noqa: E402
from Tools.platform.agent_interface import tool_availability  # noqa: E402
from Tools.tests.support.task_runtime_object_factory import (  # noqa: E402
    parsed_runtime_state,
)


def resume_action(token, result=None, tool="fixture-tool"):
    """Project one registered Queue token over an admitted memory state."""
    current = parsed_runtime_state() if result is None else result
    with mock.patch.object(
            runner.queue_runtime, "resume_next_action",
            return_value=token), mock.patch.object(
                runner, "_capability_tool", return_value=tool):
        with mock.patch.object(runner, "_rendering_boundary", return_value=None):
            return runner._resume_action(current)


def completed(returncode=0, stdout="{}\n", stderr=""):
    """Return the Tool-process result shape consumed by the Runner."""
    return SimpleNamespace(
        returncode=returncode, stdout=stdout, stderr=stderr)


class TaskRuntimeRunnerUnitTests(unittest.TestCase):
    def test_audit_recheck_reuses_only_authorized_sources_before_dispatch(self):
        prior = parsed_runtime_state()
        current = parsed_runtime_state()
        current["items_by_id"]["B1"]["state"] = "open"
        action = {"target": {"batch_id": "B1"}}
        authority = object()
        views = {"authorized_profile_view": {"current": "profile"},
                 "authorized_active_standards_view": {"current": "standards"}}
        token = runner._ADMISSION_OBSERVATION.set({"/fixture": prior})
        try:
            with mock.patch.object(runner.queue_runtime, "runtime_admission_errors", return_value=[]), \
                    mock.patch.object(runner.queue_runtime, "runtime_authority_context", return_value=authority) as owner, \
                    mock.patch.object(runner.queue_runtime, "runtime_authority_validation_kwargs", return_value=views), \
                    mock.patch.object(runner.runtime_validation, "validate_runtime", return_value=current) as validate, \
                    mock.patch.object(runner.audit_execution_runtime, "next_stage_step", return_value={"token": "current"}) as step:
                self.assertEqual({"token": "current"}, runner._recheck_audit_step("/fixture", action))
                owner.assert_called_once_with(prior)
                validate.assert_called_once_with("/fixture", **views)
                step.assert_called_once_with(current, current["items_by_id"]["B1"], "pre-merge", required_state="open")
                validate.side_effect = ValueError("owner refuses changed source")
                with self.assertRaisesRegex(ValueError, "changed source"):
                    runner._recheck_audit_step("/fixture", action)
                self.assertEqual(1, step.call_count)
            with mock.patch.object(runner, "_command_inputs", side_effect=ValueError("stop before child")):
                with self.assertRaises(ValueError):
                    runner._run_command("/fixture", "sample", {})
                self.assertEqual({}, runner._ADMISSION_OBSERVATION.get())
        finally:
            runner._ADMISSION_OBSERVATION.reset(token)
        self.assertIsNone(runner._ADMISSION_OBSERVATION.get())

    def test_withdrawn_consumed_proof_is_an_explicit_owned_continuation(self):
        state = parsed_runtime_state()
        deficits = [{"code": "evidence-invalidated", "scope": "B1",
                     "receipt_id": "old-review", "event_ids": ["decision-1"]}]
        state.update(errors=["proof no longer usable"], structural_errors=[],
                     current_evidence_deficits=deficits)
        action = resume_action("repair-runtime", state)
        self.assertEqual("repair", action["disposition"])
        self.assertEqual("withdrawn-evidence-needs-owned-continuation", action["reason_code"])
        self.assertEqual(deficits, action["target"]["current_evidence_deficits"])
        self.assertTrue(action["target"]["recorded_state_preserved"])
        state["structural_errors"] = ["corrupt ledger"]
        self.assertEqual("repair-runtime", resume_action("repair-runtime", state)["reason_code"])

    def test_main_preserves_step_failure_and_observation_failure(self):
        cases = (({"returncode": 2, "next_action_error": None}, 2),
                 ({"returncode": 0, "next_action_error": "unreadable after action"}, 1),
                 ({"returncode": 0, "next_action_error": None}, 0))
        for step, expected in cases:
            for mode, function, result in (
                    (["--execute", "a1"], "execute", step),
                    (["--run-until-boundary"], "run_until_boundary",
                     {"executed": [step], "next_action_error": step["next_action_error"]})):
                with self.subTest(step=step, mode=mode), \
                        mock.patch.object(runner, function, return_value=result), \
                        mock.patch.object(runner, "write_canonical_json") as emit:
                    self.assertEqual(expected, runner.main(["/fixture"] + mode))
                    emit.assert_called_once_with(result)

    def test_host_failure_after_execution_preserves_completed_tool_result(self):
        action = {"action_id": "a1", "token": "sample", "disposition": "invoke"}
        failure = runner.HostEnvironmentUnavailable("missing", capability_id="sample",
                                                     code="dependency-unavailable")
        with mock.patch.object(runner, "_internal_step", return_value=completed(stdout='{"applied":true}')), \
                mock.patch.object(runner, "next_action", side_effect=failure):
            outcome = runner._execute_observed("/fixture", action)
        self.assertEqual("a1", outcome["executed_action_id"])
        self.assertEqual(0, outcome["returncode"])
        self.assertEqual('{"applied":true}', outcome["output"])
        self.assertIsNone(outcome["next_action"])
        self.assertEqual("await-host", outcome["next_action_error"]["status"])

    def test_environment_wait_preserves_open_batch_and_requeries_original_state(self):
        state = parsed_runtime_state()
        state["items_by_id"]["B1"]["state"] = "open"
        failure = runner.HostEnvironmentUnavailable("browser absent",
            capability_id="static-markdown-render-v1", code="browser-unavailable",
            constructs=("mermaid-fence",))
        with mock.patch.object(runner.runtime_validation, "validate_runtime", return_value=state), \
                mock.patch.object(runner, "_resume_action", side_effect=[failure, {"restored": True}]), \
                mock.patch.object(runner, "_capability_tool", return_value="prepare_rendering_runtime"):
            action = runner.next_action("/fixture")
            self.assertEqual("await-host", action["disposition"])
            self.assertIsNone(action["required_input"])
            self.assertEqual(["mermaid-fence"], action["target"]["host_preparation"]["arguments"]["construct"])
            self.assertEqual("open", state["items_by_id"]["B1"]["state"])
            self.assertEqual({"restored": True}, runner.next_action("/fixture"))

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
                            return_value="fixture-tool"), mock.patch.object(
                                runner, "_rendering_boundary", return_value=None):
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
                    mock.patch.object(runner, "_execute_observed") as execute:
                result = runner.run_until_boundary("/fixture")
            self.assertEqual([], result["executed"])
            self.assertIs(boundary, result["next_action"])
            execute.assert_not_called()

        failed = {
            "execution_status": "returned", "failure": None, "substeps": [],
            "returncode": 7,
            "output": "",
            "diagnostics": "producer refused",
            "next_action": invoke,
            "next_action_error": None,
        }
        with mock.patch.object(
                runner, "next_action", return_value=invoke), \
                mock.patch.object(
                    runner, "_execute_observed", return_value=failed):
            stopped = runner.run_until_boundary("/fixture")
        self.assertEqual(1, len(stopped["executed"]))
        self.assertEqual(7, stopped["executed"][0]["returncode"])
        self.assertIs(invoke, stopped["next_action"])

        unchanged = dict(failed, returncode=0, diagnostics="")
        with mock.patch.object(
                runner, "next_action", return_value=invoke), \
                mock.patch.object(
                    runner, "_execute_observed", return_value=unchanged), \
                self.assertRaisesRegex(
                    runner.RunnerError, "did not advance"):
            runner.run_until_boundary("/fixture")

        boundary = boundaries[0]
        with mock.patch.object(runner, "next_action", side_effect=[invoke, boundary]) as observe, \
                mock.patch.object(runner, "_internal_step", return_value=SimpleNamespace(
                    returncode=0, stdout="", stderr="")):
            result = runner.run_until_boundary("/fixture")
        self.assertIs(boundary, result["next_action"])
        self.assertEqual(2, observe.call_count)  # One before and one resulting-state observation.


class TaskRuntimeRunnerContractTests(unittest.TestCase):
    """One representative compiled-CLI consumption contract."""

    def test_page_review_binding_roundtrips_null_and_exact_consumption(self):
        from Tools.execution.audit import audit_obligation_projection as projection
        from Tools.execution.audit import audit_execution_runtime as execution
        from Tools.platform.agent_interface import cli_argv_renderer as renderer
        registry = execution.batch_review_obligation_contract
        parser = runner.entrypoint_loader.capture_argument_parser(
            "record_batch_page_review", TOOLS, require_marker=True)
        cli = {"tool": "record_batch_page_review", "arguments":
               compile_cli_contract.describe_arguments(TOOLS.parent, parser)}
        owner = projection.obligation_spec_for_rule(registry.M_ATOMIC_RULE_IDS[0], root=TOOLS.parent)
        obligation = projection.required_obligation(projection.resolve_obligation_definition(
            owner, "Topics/A.md", trigger="new"))
        obligation["obligation_id"] = "obligation-one"
        status = {"audit_plan_path": ".cambium/work_specs/audit-plans/p.yaml",
                  "audit_plan_sha256": "sha256:" + "a" * 64,
                  "obligations": [{"obligation": obligation, "status": "missing"}]}
        result = {"root": str(TOOLS.parent)}
        step = execution._missing_step(result, {"id": "B1"}, status, obligation)
        with mock.patch.object(runner, "_compiled_cli_tool", return_value=cli):
            shape = runner._producer_input(result, step)
        with mock.patch.object(runner, "_compiled_cli_tool", return_value=dict(
                cli, invocation_contract_source_hash="sha256:" + "b" * 64)):
            changed_shape = runner._producer_input(result, step)
        self.assertEqual(shape["properties"], changed_shape["properties"])
        self.assertNotEqual(shape["x-cambium-binding"]["source_fingerprint"],
                            changed_shape["x-cambium-binding"]["source_fingerprint"])
        supplied = {"reviewer_context_id": "reviewer-one", "reviewer_role": "reviewer",
                    "verdict": "passed", "statement": "Bounded review result.",
                    "applicability_disposition": "applicable", "applicability_reason": None}
        action = {"token": step["token"], "required_input": shape}
        bound = runner._require_input(action, supplied)
        captured = []

        def parse_command(_root, tool, arguments):
            argv, _ = renderer.build_argv(tool, renderer.schema_from_compiled_tool(cli),
                                         dict(arguments, root=str(TOOLS.parent)))
            captured.append(parser.parse_args(argv))
            return completed()

        with mock.patch.object(runner, "_recheck_audit_step", return_value=step), \
                mock.patch.object(runner, "_run_command", side_effect=parse_command):
            runner._await_audit_producer(TOOLS.parent, action, bound, None)
        self.assertIsNone(captured[0].applicability_reason)
        self.assertEqual([], captured[0].consumed_evidence_ref)
        self.assertEqual("obligation-one", captured[0].obligation_id)
        self.assertTrue(captured[0].apply)
        for invalid in (dict(supplied, batch="B2"), dict(supplied, consumed_evidence_ref=[]),
                        dict(supplied, reviewer_role=0), {}):
            with self.subTest(keys=sorted(invalid)), self.assertRaises(ValueError):
                runner._require_input(action, invalid)

    def test_execute_preserves_predispatch_and_partial_substep_failure(self):
        action = resume_action("materialize-required-queue")
        # Only IO is replaced. The same dispatch/result observation path runs
        # twice and the second command fails before process creation.
        from contextlib import contextmanager

        @contextmanager
        def admission(*_args, **_kwargs):
            yield {"arguments": {"root": str(TOOLS.parent)}, "missing": [], "acknowledgement_error": None}

        schema = {"type": "object", "properties": {"root": {"type": "string",
                  "x-cambium-cli": {"option_strings": [], "action": "store"}}}, "required": ["root"]}
        output_contract = {"unused": "observation supplied below"}
        inputs = ("fixture-tool.py", schema, {"root": str(TOOLS.parent)}, "root", output_contract, None)

        def two_steps(root, _action):
            runner._run_command(root, "producer-one", {})
            runner._run_command(root, "producer-two", {})

        for command_inputs, expected_calls in (([ValueError("invalid field")], 0),
                                               ([inputs, ValueError("invalid field")], 1)):
            with mock.patch.object(runner, "_internal_step", side_effect=two_steps), \
                    mock.patch.object(runner, "_command_inputs", side_effect=command_inputs), \
                    mock.patch.object(runner.path_admission, "invocation", side_effect=admission), \
                    mock.patch.object(runner.kblib, "run_cambium_subprocess",
                                      return_value=completed(stdout='{"receipt_id":"committed-one"}\n')) as process, \
                    mock.patch.object(runner, "observe_tool_output", return_value={"output_reliable": True}), \
                    mock.patch.object(runner, "next_action", side_effect=ValueError("read-back unavailable")):
                outcome = runner._execute_observed(str(TOOLS.parent), action)
            self.assertEqual(expected_calls, process.call_count)
            self.assertEqual(expected_calls, len(outcome["substeps"]))
            self.assertIsNone(outcome["tool_returncode"])
            self.assertEqual("parameter-admission", outcome["failure"]["stage"])
            self.assertEqual("read-back unavailable", outcome["next_action_error"])
            if expected_calls:
                self.assertIn("committed-one", outcome["substeps"][0]["output"])
                self.assertEqual(0, outcome["substeps"][0]["tool_returncode"])
            self.assertIsNone(runner._EXECUTION_OBSERVATION.get())

    def test_command_consumes_compiled_positionals_and_transport_once(self):
        root = TOOLS.parent
        contract = compile_cli_contract.compile_contract(
            root, tool_availability.CARRIED_RUNTIME)
        with mock.patch.object(
                runner, "_compiled_cli_contract", return_value=contract):
            delta = ".cambium/deltas/B1.yaml"
            inputs = runner._command_inputs(
                root, "apply_delta", {
                    "delta": delta,
                    "apply": True,
                    "json": False,
                })
            command = runner._render_command("apply_delta", *inputs[:3])

        self.assertEqual(sys.executable, command[0])
        self.assertEqual(
            os.path.realpath(str(TOOLS / "apply_delta.py")), command[1])
        self.assertEqual(delta, command[2])
        self.assertNotIn("--delta", command)
        self.assertIn("--apply", command)
        self.assertEqual(str(root),
                         command[command.index("--root") + 1])
        self.assertEqual("--json", command[-1])
        self.assertEqual(1, command.count("--json"))

    def test_runner_does_not_fall_back_to_distribution_contract(self):
        with tempfile.TemporaryDirectory() as directory, \
                self.assertRaisesRegex(
                    runner.RunnerError,
                    "generate it with .*--projection-target carried-runtime"):
            runner._command_inputs(
                Path(directory).resolve(), "apply_delta", {
                    "delta": ".cambium/deltas/B1.yaml",
                    "apply": True,
                    "json": False,
                })

    def test_stale_or_hand_edited_contract_is_refused_before_route_use(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / runtime_paths.CLI_CONTRACT_ARTIFACT_PATH
            path.parent.mkdir(parents=True)
            path.write_text(
                "artifact: cli-invocation-contract\n"
                "projection_target: carried-runtime\n"
                "tools:\n"
                "  - tool: apply_delta\n"
                "    module: Tools/check_links.py\n",
                encoding="utf-8")
            refused = completed(
                returncode=2,
                stdout="compile_cli_contract --check: stale or hand-edited\n")
            with mock.patch.object(
                    runner, "_carried_cli_contract_currentness_check",
                    return_value=refused), mock.patch.object(
                        runner, "_repository_tool_entrypoint") as dispatch, \
                    self.assertRaisesRegex(
                        runner.RunnerError, "not current"):
                runner._command_inputs(root, "apply_delta", {
                    "delta": ".cambium/deltas/B1.yaml",
                    "apply": True,
                    "json": False,
                })

            dispatch.assert_not_called()

    def test_contract_reuse_is_operation_scoped_and_rechecks_input_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / runtime_paths.CLI_CONTRACT_ARTIFACT_PATH
            path.parent.mkdir(parents=True)
            first = {
                "artifact": "cli-invocation-contract",
                "projection_target": "carried-runtime",
                "tools": [],
            }
            second = dict(first, tools=[{"tool": "sample"}])
            current = completed(returncode=0)
            with mock.patch.object(
                    runner, "_carried_cli_contract_currentness_check",
                    return_value=current) as check, compile_cli_contract.checked_view_scope():
                path.write_text(
                    compile_cli_contract.kblib.canonical_yaml(first),
                    encoding="utf-8")
                loaded_first = runner._compiled_cli_contract(root)
                self.assertEqual(loaded_first, runner._compiled_cli_contract(root))
                self.assertEqual(1, check.call_count)
                path.write_text(
                    compile_cli_contract.kblib.canonical_yaml(second),
                    encoding="utf-8")
                loaded_second = runner._compiled_cli_contract(root)
                self.assertEqual(2, check.call_count)

            self.assertEqual([], loaded_first["tools"])
            self.assertEqual([{"tool": "sample"}], loaded_second["tools"])


class TaskRuntimeRunnerCheckpointIntegrationTests(unittest.TestCase):
    """Adjacent dispatch/read-back seams from legal memory checkpoints."""

    def test_rendering_preflight_reuses_admitted_profile_and_selector_owner(self):
        state = parsed_runtime_state()
        state["root"] = str(TOOLS.parent)
        state["items_by_id"]["B1"]["manifest"] = [
            "Knowledge/A.md", "Knowledge/Not-written-yet.md"]
        profile = object()
        snapshot = SimpleNamespace(exists=True, read_text=lambda: "source")
        absent = SimpleNamespace(exists=False)
        ready = {"result": "ready", "bindings": {}, "findings": []}
        for constructs in ((), ("mermaid-fence",), ("dollar-math",)):
            with self.subTest(constructs=constructs), mock.patch.object(
                    runner.profile_admission, "contract_from_admitted_view",
                    return_value=profile) as admission, mock.patch.object(
                        runner.kblib, "repository_target_snapshot",
                        side_effect=(snapshot, absent)), mock.patch.object(
                            runner.profile_rendering, "require_bindings",
                            return_value={"Knowledge/A.md": constructs}) as selector, \
                    mock.patch.object(
                        runner.static_render_runtime, "probe_runtime",
                        return_value=ready) as probe:
                boundary = runner._rendering_boundary(state, "B1")
            self.assertIsNone(boundary)
            admission.assert_called_once_with(
                state["root"], state["_profile_authorized_view"])
            selector.assert_called_once_with(
                [("Knowledge/A.md", "source")], profile, root=state["root"])
            if constructs:
                probe.assert_called_once_with(state["root"], require_browser=constructs != ("dollar-math",))
            else:
                probe.assert_not_called()

    def test_unready_selector_stops_next_action_without_evidence_or_writes(self):
        state = parsed_runtime_state()
        state["items_by_id"]["B1"]["manifest"] = ["Knowledge/A.md"]
        snapshot = SimpleNamespace(exists=True, read_text=lambda: "$x$")
        unavailable = {
            "result": "needs-preparation", "bindings": {},
            "findings": ["Pinned renderer dependencies absent"],
        }
        with mock.patch.object(
                runner.runtime_validation, "validate_runtime", return_value=state), \
                mock.patch.object(runner.queue_runtime, "resume_next_action",
                                  return_value="activate-ready-batch:B1"), \
                mock.patch.object(runner.profile_admission,
                                  "contract_from_admitted_view", return_value=object()), \
                mock.patch.object(runner.kblib, "repository_target_snapshot",
                                  return_value=snapshot), \
                mock.patch.object(runner.profile_rendering, "require_bindings",
                                  side_effect=runner.HostEnvironmentUnavailable(
                                      "dependencies absent", capability_id="static-markdown-render-v1",
                                      code="dependencies-unavailable")), \
                mock.patch.object(runner.static_render_runtime, "probe_runtime",
                                  return_value=unavailable) as probe, \
                mock.patch.object(runner, "_capability_tool",
                                  return_value="prepare_rendering_runtime"), \
                mock.patch.object(runner, "_run_command") as command:
            action = runner.next_action("/fixture")
            self.assertEqual("await-host", action["disposition"])
            self.assertEqual(action_contract.action_route("prepare-host-environment").token_template, action["token"])
            self.assertEqual("prepare_rendering_runtime",
                             action["target"]["host_preparation"]["tool"])
            with self.assertRaisesRegex(runner.RunnerError, "no submittable input"):
                runner._continue_awaited("/fixture", action, {"ready": True})
            with self.assertRaisesRegex(runner.RunnerError, "no submittable input"):
                runner._continue_awaited("/fixture", action, {})
        probe.assert_not_called()
        command.assert_not_called()
        self.assertEqual("queued", state["items_by_id"]["B1"]["state"])

    def test_missing_profile_binding_is_not_treated_as_host_readiness(self):
        state = parsed_runtime_state()
        state["items_by_id"]["B1"]["manifest"] = ["Knowledge/A.md"]
        snapshot = SimpleNamespace(exists=True, read_text=lambda: "| table |")
        with mock.patch.object(
                runner.profile_admission, "contract_from_admitted_view",
                return_value=object()), mock.patch.object(
                    runner.kblib, "repository_target_snapshot", return_value=snapshot), \
                mock.patch.object(runner.profile_rendering, "require_bindings",
                                  side_effect=ValueError("table contract-gap/HOLD")), \
                mock.patch.object(runner.static_render_runtime, "probe_runtime") as probe:
            action = runner._rendering_boundary(state, "B1")
        self.assertEqual("repair", action["disposition"])
        self.assertEqual("profile-rendering-contract-gap", action["reason_code"])
        probe.assert_not_called()

    def test_activation_rechecks_host_before_receipt_and_before_open_writer(self):
        state = parsed_runtime_state()
        opened = parsed_runtime_state()
        opened["items_by_id"]["B1"]["state"] = "open"
        gate = completed(stdout=json.dumps([{
            "queue_check_mode": "require-ready:B1", "receipt_id": "ready-1",
        }]))
        hold = {"disposition": "await-host", "reason_code": "host-environment-not-ready"}
        # These checkpoints exercise the Runner seam only. No fixture opens a
        # real batch or reconstructs any earlier lifecycle to obtain them.
        for boundaries, expected_commands, succeeds in (
                ((hold,), 0, False),
                ((None, hold), 1, False),
                ((None, None), 2, True)):
            with self.subTest(boundaries=boundaries), mock.patch.object(
                    runner.runtime_validation, "validate_runtime",
                    side_effect=(state, state, opened)), mock.patch.object(
                        runner, "_rendering_boundary", side_effect=boundaries) as preflight, \
                    mock.patch.object(runner, "_run_command",
                                      side_effect=(gate, completed())) as command, \
                    mock.patch.object(runner.metadata_execution_contract,
                                      "capability_invocation_tool",
                                      return_value="existing-tool"):
                if succeeds:
                    self.assertEqual(0, runner._activate_ready_batch("/fixture", "B1").returncode)
                else:
                    with self.assertRaisesRegex(runner.RunnerError, "activation prerequisite"):
                        runner._activate_ready_batch("/fixture", "B1")
            self.assertEqual(expected_commands, command.call_count)
            self.assertEqual(len(boundaries), preflight.call_count)
            if succeeds:
                self.assertEqual("open", command.call_args_list[-1].args[2]["transition"])

    def test_execute_dispatches_invoke_and_await_then_returns_readback(self):
        invoke = resume_action("materialize-required-queue")
        parser = runner.entrypoint_loader.capture_argument_parser("update_task", TOOLS, require_marker=True)
        cli = {"tool": "update_task", "arguments": compile_cli_contract.describe_arguments(TOOLS.parent, parser)}
        paused = parsed_runtime_state()
        paused["progress"]["task_state"] = "paused"
        with mock.patch.object(runner, "_compiled_cli_tool", return_value=cli):
            awaiting = resume_action("resume-paused-task", paused, tool="update_task")
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
                    side_effect=(admitted, closed)) as readback, mock.patch.object(
                    runner.assemble_terminal_proof, "read_terminal_audit_input", return_value={}) as preflight:
            result = runner._await_terminal_audit(
                "/fixture", {}, {
                    "terminal_audit_input":
                        ".cambium/tmp/terminal-audit.yaml",
                }, route)

        self.assertEqual(0, result.returncode)
        preflight.assert_called_once_with("/fixture", ".cambium/tmp/terminal-audit.yaml")
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
        with mock.patch.object(runner.assemble_terminal_proof, "read_terminal_audit_input",
                               side_effect=ValueError("invalid terminal input")), \
                mock.patch.object(runner, "_run_command") as dispatched:
            with self.assertRaisesRegex(ValueError, "invalid terminal input"):
                runner._await_terminal_audit("/fixture", {}, {
                    "terminal_audit_input": ".cambium/tmp/terminal-audit.yaml"}, route)
        dispatched.assert_not_called()


if __name__ == "__main__":
    unittest.main()
