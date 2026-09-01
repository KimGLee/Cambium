"""Closed-contract tests for typed Task Runtime next actions."""

import copy
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.task_runtime.task_runtime_action as contract  # noqa: E402
import Tools.execution.task_runtime.task_runtime_runner as runner  # noqa: E402
import Tools.governance.control.metadata_execution_contract as operation_contract  # noqa: E402


class TaskRuntimeActionTests(unittest.TestCase):

    @staticmethod
    def route_token(route):
        values = {}
        for name in route.parameter_names:
            if name == "batch_id":
                values[name] = "B001"
            elif name == "batch_ids":
                values[name] = "B001,B002"
            else:
                values[name] = "receipt-001"
        return route.token_template.format(**values), values

    def fields(self, disposition="invoke"):
        common = {
            "schema_version": 1,
            "disposition": disposition,
            "token": "run-batch-close-gate:B001",
            "target": {"task_id": "TASK-001", "batch_id": "B001"},
            "binding": {
                "queue_revision": 4,
                "required_queue_sha256": "sha256:" + "a" * 64,
            },
            "reason_code": "batch-close-required",
        }
        if disposition == "invoke":
            common.update({
                "capability_id": "batch-close-gate-v1",
                "tool": "Tools/check_batch_close.py",
                "arguments": {
                    "root": ".",
                    "batch": "B001",
                    "strict": True,
                },
                "required_input": None,
            })
        elif disposition.startswith("await-"):
            common.update({
                "capability_id": None,
                "tool": None,
                "arguments": {},
                "required_input": {
                    "input_contract": "substantive-review-v1",
                    "target": "Knowledge/A.md",
                },
            })
        else:
            common.update({
                "capability_id": None,
                "tool": None,
                "arguments": {},
                "required_input": None,
            })
        return common

    def test_build_invoke_derives_a_stable_content_identity(self):
        fields = self.fields()
        action = contract.build_action(**fields)
        self.assertRegex(action["action_id"], r"^action-[0-9a-f]{64}$")
        self.assertEqual(action["action_id"],
                         contract.canonical_action_id(action))
        self.assertIs(action, contract.validate_action(action))

        reordered = {key: fields[key] for key in reversed(tuple(fields))}
        self.assertEqual(action["action_id"],
                         contract.build_action(**reordered)["action_id"])

    def test_action_id_binds_every_machine_field_but_not_itself(self):
        action = contract.build_action(**self.fields())
        with_different_id = dict(action, action_id="action-" + "f" * 64)
        self.assertEqual(action["action_id"],
                         contract.canonical_action_id(with_different_id))
        with self.assertRaisesRegex(ValueError, "does not bind"):
            contract.validate_action(with_different_id)

        changed = copy.deepcopy(action)
        changed["binding"]["queue_revision"] = 5
        self.assertNotEqual(action["action_id"],
                            contract.canonical_action_id(changed))
        with self.assertRaisesRegex(ValueError, "does not bind"):
            contract.validate_action(changed)

    def test_contract_fields_are_closed_for_build_and_validation(self):
        fields = self.fields()
        fields["command"] = "python3 Tools/check_batch_close.py"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.build_action(**fields)

        action = contract.build_action(**self.fields())
        action["command"] = "python3 Tools/check_batch_close.py"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_action(action)

    def test_invoke_requires_typed_capability_and_mapping_arguments(self):
        for field in ("capability_id", "tool"):
            fields = self.fields()
            fields[field] = None
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "requires capability_id and tool"):
                contract.build_action(**fields)

        for value in (
                "--root . --batch B001",
                ["--root", ".", "--batch", "B001"],
                None):
            fields = self.fields()
            fields["arguments"] = value
            with self.subTest(arguments=value), self.assertRaisesRegex(
                    ValueError, "arguments must be a mapping"):
                contract.build_action(**fields)

        fields = self.fields()
        fields["required_input"] = {"input_contract": "not-allowed"}
        with self.assertRaisesRegex(ValueError, "required_input must be null"):
            contract.build_action(**fields)

    def test_each_await_disposition_names_its_responsible_boundary(self):
        for disposition in (
                "await-agent", "await-user", "await-host"):
            with self.subTest(disposition=disposition):
                action = contract.build_action(**self.fields(disposition))
                self.assertEqual(disposition, action["disposition"])
                contract.validate_action(action)

        fields = self.fields("await-user")
        fields["required_input"] = {}
        with self.assertRaisesRegex(ValueError, "non-empty mapping"):
            contract.build_action(**fields)

        fields = self.fields("await-user")
        fields["tool"] = "Tools/record_substantive_review.py"
        with self.assertRaisesRegex(ValueError, "must be null"):
            contract.build_action(**fields)

        fields = self.fields("await-host")
        fields["arguments"] = {"command": "run this"}
        with self.assertRaisesRegex(ValueError, "empty mapping"):
            contract.build_action(**fields)

    def test_repair_and_terminal_are_non_invoking_terminal_boundaries(self):
        for disposition in ("repair", "terminal"):
            with self.subTest(disposition=disposition):
                action = contract.build_action(**self.fields(disposition))
                contract.validate_action(action)

                fields = self.fields(disposition)
                fields["required_input"] = {"input_contract": "unexpected"}
                with self.assertRaisesRegex(ValueError,
                                            "required_input must be null"):
                    contract.build_action(**fields)

    def test_common_fields_are_explicit_typed_and_machine_serializable(self):
        for field, value, message in (
                ("token", " ", "non-empty trimmed string"),
                ("target", None, "must be a mapping"),
                ("binding", None, "must be a mapping"),
                ("reason_code", "Needs Human", "stable code")):
            fields = self.fields()
            fields[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, message):
                contract.build_action(**fields)

        fields = self.fields()
        fields["binding"] = {"unsupported": object()}
        with self.assertRaisesRegex(ValueError, "canonical JSON values"):
            contract.build_action(**fields)

        fields = self.fields()
        fields["binding"] = {}
        fields["target"] = {}
        contract.validate_action(contract.build_action(**fields))

    def test_disposition_and_schema_are_closed(self):
        fields = self.fields("repair")
        fields["disposition"] = "await"
        with self.assertRaisesRegex(ValueError, "disposition must be one of"):
            contract.build_action(**fields)

        fields = self.fields()
        fields["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "schema_version must be 1"):
            contract.build_action(**fields)

    def test_build_rejects_a_caller_chosen_mismatched_id(self):
        fields = self.fields()
        fields["action_id"] = "action-" + "0" * 64
        with self.assertRaisesRegex(ValueError, "supplied.*does not bind"):
            contract.build_action(**fields)

        action = contract.build_action(**self.fields())
        rebuilt = contract.build_action(**action)
        self.assertEqual(action, rebuilt)

    def test_action_registry_has_one_producer_consumer_and_token_owner(self):
        route_ids = [route.route_id for route in contract.ACTION_ROUTES]
        patterns = [route.token_pattern for route in contract.ACTION_ROUTES]
        self.assertEqual(len(route_ids), len(set(route_ids)))
        self.assertEqual(len(patterns), len(set(patterns)))

        explicit_repairs = {
            "reconcile-interrupted-write",
            "repair-runtime",
            "repair-delta-settlement",
        }
        for route in contract.ACTION_ROUTES:
            with self.subTest(route=route.route_id):
                token, values = self.route_token(route)
                matches = [
                    candidate for candidate in contract.ACTION_ROUTES
                    if re.fullmatch(candidate.token_pattern, token)]
                self.assertEqual([route], matches)
                resolved, parameters = contract.action_route_for_token(token)
                self.assertEqual(route, resolved)
                self.assertEqual(values, parameters)
                self.assertTrue((REPOSITORY / route.producer_owner).is_file())
                self.assertTrue((REPOSITORY / route.consumer_owner).is_file())
                self.assertEqual(
                    "authoritative-runtime-reread", route.next_edge)
                if route.internal_dispatch:
                    self.assertIsNone(route.action_disposition)
                    self.assertTrue(route.resume_source)
                else:
                    self.assertIn(
                        route.action_disposition, contract.DISPOSITIONS)
                if route.resume_source:
                    self.assertEqual(
                        token,
                        contract.resume_action_token(route.route_id, **values))
                    if route.action_disposition == "repair":
                        self.assertIn(route.route_id, explicit_repairs)
                if route.capability_resolution == "registry-chain":
                    self.assertTrue(route.capability_chain)
                elif route.capability_resolution == "upstream-action":
                    self.assertEqual("audit-producer", route.runner_route)
                else:
                    self.assertEqual("none", route.capability_resolution)

    def test_runner_handler_map_exactly_closes_registered_runner_routes(self):
        expected = {route.runner_route for route in contract.ACTION_ROUTES}
        handlers = runner._RUNNER_ROUTE_HANDLERS

        self.assertEqual(expected, set(handlers))
        self.assertEqual(len(handlers), len({id(value)
                                             for value in handlers.values()}))
        for name, handler in handlers.items():
            with self.subTest(runner_route=name):
                phases = (
                    handler.resume, handler.await_input, handler.invoke)
                self.assertTrue(any(callable(value) for value in phases))
                self.assertTrue(all(
                    value is None or callable(value) for value in phases))
        for route in contract.ACTION_ROUTES:
            with self.subTest(route=route.route_id):
                handler = handlers[route.runner_route]
                if route.resume_source:
                    self.assertTrue(callable(handler.resume))
                elif route.action_disposition in contract.AWAIT_DISPOSITIONS:
                    self.assertTrue(callable(handler.await_input))
                elif route.action_disposition == "invoke":
                    self.assertTrue(callable(handler.invoke))

    def test_every_action_capability_resolves_to_one_real_entrypoint(self):
        document = operation_contract.load_operation_capabilities(REPOSITORY)
        by_id = {entry["capability_id"]: entry
                 for entry in document["capabilities"]}
        runner_path = "Tools/execution/task_runtime/task_runtime_runner.py"
        for route in contract.ACTION_ROUTES:
            for capability_id in route.capability_chain:
                with self.subTest(route=route.route_id,
                                  capability=capability_id):
                    entry = by_id[capability_id]
                    tool = operation_contract.capability_invocation_tool(
                        capability_id, root=REPOSITORY, document=document)
                    self.assertTrue((TOOLS / (tool + ".py")).is_file())
                    self.assertTrue(
                        entry["implementation_owner"] == runner_path or
                        runner_path in entry["consumers"], entry)

    def test_no_normal_resume_token_is_registered_as_repair(self):
        repairs = {
            route.route_id for route in contract.ACTION_ROUTES
            if route.resume_source and route.action_disposition == "repair"
        }
        self.assertEqual({
            "reconcile-interrupted-write",
            "repair-runtime",
            "repair-delta-settlement",
        }, repairs)
        for route_id in (
                "run-standards-revalidation",
                "resolve-holds-dependencies"):
            self.assertNotEqual(
                "repair", contract.action_route(route_id).action_disposition)

    def test_revalidation_chain_reads_each_producer_and_consumer_after_image(self):
        result = {
            "root": str(REPOSITORY),
            "queue": {
                "task_id": "TASK-001",
                "queue_revision": 2,
                "state_revision": 4,
                "upstream_revision_id": "a" * 40,
                "selected_profile_manifest": "profiles/example.yaml",
            },
            "progress": {"task_id": "TASK-001", "task_state": "active"},
            "_active_standards_authorized_view": {
                "upstream_revision_id": "a" * 40,
            },
            "_profile_authorized_view": {
                "selected_profile_manifest": "profiles/example.yaml",
                "profile_snapshot_sha256": "sha256:" + "4" * 64,
            },
            "items_by_id": {"B1": {
                "id": "B1", "state": "open",
                "hold_state": "revalidation-required",
            }},
            "queue_sha256": "sha256:" + "1" * 64,
            "coverage_sha256": "sha256:" + "2" * 64,
            "progress_sha256": "sha256:" + "3" * 64,
        }
        resume_token = "run-standards-revalidation:B1"
        with mock.patch.object(
                runner.queue_runtime, "resume_next_action",
                return_value=resume_token), mock.patch.object(
                    runner, "_current_standards_revalidation_aggregate",
                    return_value=None):
            produce = runner._resume_action(result)
        self.assertEqual(
            ("await-agent", resume_token),
            (produce["disposition"], produce["token"]))

        produced_process = subprocess.CompletedProcess(
            ["check_queue"], 0, "[]\n", "")
        with mock.patch.object(
                runner, "_run_command",
                return_value=produced_process) as run_producer, \
                mock.patch.object(
                    runner.runtime_validation, "validate_runtime",
                    return_value=result) as producer_readback, \
                mock.patch.object(
                    runner, "_current_standards_revalidation_aggregate",
                    return_value="aggregate-001"):
            completed = runner._continue_awaited(
                str(REPOSITORY), produce, {
                    "boundary_gate_receipts": {
                        "required-queue-consistency": "gate-001",
                    },
                })
        self.assertIs(produced_process, completed)
        producer_readback.assert_called_once_with(str(REPOSITORY))
        producer_arguments = run_producer.call_args.args[2]
        self.assertEqual("B1", producer_arguments["require_revalidation"])
        self.assertEqual(
            ["required-queue-consistency=gate-001"],
            producer_arguments["boundary_gate_receipt"])

        with mock.patch.object(
                runner.queue_runtime, "resume_next_action",
                return_value=resume_token), mock.patch.object(
                    runner, "_current_standards_revalidation_aggregate",
                    return_value="aggregate-001"):
            consume = runner._resume_action(result)
        self.assertEqual(
            ("invoke", "consume-standards-revalidation", "update_queue"),
            (consume["disposition"], consume["token"], consume["tool"]))
        self.assertEqual(
            "aggregate-001",
            consume["arguments"]["standards_revalidation_receipt"])

        queued = dict(result)
        queued["items_by_id"] = {"B1": {
            "id": "B1", "state": "queued", "hold_state": "none",
        }}
        with mock.patch.object(
                runner.queue_runtime, "resume_next_action",
                return_value=resume_token), mock.patch.object(
                    runner, "_current_standards_revalidation_aggregate",
                    return_value="aggregate-001"):
            activate = runner._resume_action(queued)
        self.assertEqual(
            ("invoke", "activate-revalidated-batch", "run_task"),
            (activate["disposition"], activate["token"], activate["tool"]))
        self.assertEqual(
            "aggregate-001",
            activate["arguments"]["standards_revalidation_receipt"])

        final = dict(result)
        final["items_by_id"] = {"B1": {
            "id": "B1", "state": "open", "hold_state": "none",
        }}
        consumed_process = subprocess.CompletedProcess(
            ["update_queue"], 0, "[]\n", "")
        with mock.patch.object(
                runner, "_run_command",
                return_value=consumed_process), mock.patch.object(
                    runner.runtime_validation, "validate_runtime",
                    return_value=final) as consumer_readback, \
                mock.patch.object(
                    runner.queue_runtime,
                    "outstanding_standards_revalidation",
                    return_value=[]):
            completed = runner._internal_step(str(REPOSITORY), consume)
        self.assertIs(consumed_process, completed)
        consumer_readback.assert_called_once_with(str(REPOSITORY))


if __name__ == "__main__":
    unittest.main()
