"""Owner-focused tests for the read-only Required Queue consumer.

Queue, Coverage, Progress, Receipt, Profile, AuditPlan, and transition
semantics are tested by their machine owners.  This suite starts from parsed
owner results or generated local checkpoints and tests only check_queue's
routing, reporting, gate-producer connections, and adjacent consumers.
"""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import Tools.execution.task_runtime.check_queue as check_queue
from Tools.execution.task_runtime import queue_check_receipt
from Tools.execution.task_runtime import queue_runtime
from Tools.execution.task_runtime.queue_runtime import resume as runtime_resume
from Tools.execution.task_runtime.queue_runtime import task_progress
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.platform.common.kblib as kblib
from Tools.tests.fixtures.contract import maintenance_completion
from Tools.tests.fixtures.integration.required_queue_checkpoints import (
    MaintenanceClosedCheckpointCase,
)


SHA_QUEUE = "sha256:" + "1" * 64
SHA_COVERAGE = "sha256:" + "2" * 64
SHA_PROGRESS = "sha256:" + "3" * 64


def runtime_result(*, items=None, ready=None, blocked=None,
                   task_state="active", errors=None, root="/memory/repo"):
    """Small parsed snapshot for check_queue connection tests.

    Queue validation, Coverage predicates, Receipt currency, and property-state
    semantics have their own owner suites. These objects exercise only the CLI
    producer's routing over an already-evaluated snapshot.
    """
    if items is None:
        items = [{
            "id": "B1",
            "order": 1,
            "state": "queued",
            "hold_state": "none",
            "work_spec_path": None,
            "work_spec_sha256": None,
        }]
    queue_items = [dict(item) for item in items]
    items_by_id = {item["id"]: item for item in queue_items}
    if ready is None:
        ready = [
            item["id"] for item in queue_items
            if item.get("state") == "queued"
        ]
    return {
        "root": str(root),
        "errors": list(errors or []),
        "queue": {
            "task_id": "task-1",
            "scope_version": "scope-1",
            "upstream_revision_id": "a" * 40,
            "selected_profile_manifest": "profiles/test/profile.toml",
            "queue_revision": 4,
            "state_revision": 7,
            "required_queue": queue_items,
        },
        "coverage": {"pages": []},
        "progress": {
            "task_state": task_state,
            "contract": {
                "contract_version": "c1",
                "completion_semantics": "build",
                "objective": "Exercise the Queue producer seam.",
                "exclusions": ["Do not replay a lifecycle."],
                "policy_exceptions": [],
            },
            "checkpoint": {},
            "terminal_audit": {},
            "maintenance_completion": {},
            "standards_adoptions": [],
        },
        "queue_sha256": SHA_QUEUE,
        "coverage_sha256": SHA_COVERAGE,
        "progress_sha256": SHA_PROGRESS,
        "items_by_id": items_by_id,
        "remaining": sum(
            item.get("state") not in ("closed", "cancelled")
            for item in queue_items
        ),
        "ready": list(ready),
        "blocked": dict(blocked or {}),
        "receipt_catalog": {},
        "structural_admission_defects": [],
        "hub_page_admission": {},
        "managed_deltas": [],
        "applied_delta_receipts": [],
        "pending_delta_applies": {},
        "batch_close_recovery": {},
        "standards_revalidation_outstanding": {},
        "standards_revalidation_barriers": {},
        "maintenance_candidate_context": {},
        "task_runtime": {
            "history": [],
            "pending_guidance": [],
            "pending_amendments": [],
            "contract_load_set_gaps": [],
        },
        "_writer_locks": [],
    }


def arguments(**overrides):
    values = {
        "root": "/memory/repo",
        "require_ready": None,
        "require_revalidation": None,
        "require_complete": False,
        "require_maintenance_complete": False,
        "resume_status": False,
        "deliver_readback": None,
        "deliver_phase": None,
        "ack_activation_phase": None,
        "readback_rule": None,
        "phase": None,
        "phase_part": 0,
        "phase_nonce": None,
        "phase_delivery_receipt": None,
        "confirmation_receipt": None,
        "boundary_gate_receipt": [],
        "budget_manifest_receipt": None,
        "ledger_advance_receipt": None,
        "watermark_advance_receipt": None,
        "receipts": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CheckQueueUnitTests(unittest.TestCase):
    def test_boundary_gate_pairs_are_exact_and_unique(self):
        mapping, errors = check_queue._parse_boundary_gate_arguments([
            "gate-a=receipt-a", "gate-b=receipt-b",
        ])
        self.assertEqual(
            {"gate-a": "receipt-a", "gate-b": "receipt-b"}, mapping)
        self.assertEqual([], errors)

        mapping, errors = check_queue._parse_boundary_gate_arguments([
            "missing-separator", "=receipt", "gate=", "gate=first",
            "gate=second", 7,
        ])
        self.assertEqual({"gate": "first"}, mapping)
        self.assertEqual(5, len(errors), errors)
        self.assertTrue(any("must be GATE_ID=RECEIPT_ID" in error
                            for error in errors), errors)
        self.assertTrue(any("empty gate/receipt" in error
                            for error in errors), errors)
        self.assertTrue(any("repeats Gate ID gate" in error
                            for error in errors), errors)

    def test_unwritten_receipt_is_lazy_and_delivery_only(self):
        result = runtime_result()
        with mock.patch.object(check_queue, "make_check_receipt") as builder:
            self.assertIsNone(check_queue._write_receipt(
                result["root"], None, result, "pass", "details",
                "consistency"))
            builder.assert_not_called()

            builder.return_value = {"receipt_id": "audit-check"}
            emitted = check_queue._write_receipt(
                result["root"], None, result, "pass", "details",
                "deliver-phase:B1:preflight:0",
                activation_context={"activation_only": "not-delivered"},
                readback_context={
                    "readback_delivery_payload": {"rule_id": "rule-1"},
                },
                phase_context={
                    "activation_phase_payload": {"phase_id": "preflight"},
                },
                build_unwritten=True,
            )

        self.assertEqual("audit-check", emitted["receipt_id"])
        self.assertEqual(
            {"rule_id": "rule-1"}, emitted["readback_delivery_payload"])
        self.assertEqual(
            {"phase_id": "preflight"}, emitted["activation_phase_payload"])
        self.assertNotIn("activation_only", emitted)
        builder.assert_called_once()

    def test_selected_resume_token_is_rendered_without_reselection(self):
        result = {
            "root": "/memory/repo",
            "queue": {"state_revision": 9},
            "queue_sha256": SHA_QUEUE,
        }
        with mock.patch.object(
                check_queue, "resume_next_action",
                side_effect=AssertionError("renderer re-selected token")):
            rendered = check_queue._resume_recommendation(
                result, "materialize-required-queue")
        self.assertIn("materializing its Required Queue", rendered)

        token = (
            "close-applied-batch:B1:queue-check:close-gate:delta-apply")
        with mock.patch.object(
                check_queue, "batch_close_update_command",
                return_value="python3 Tools/update_queue.py --fixture") as command:
            rendered = check_queue._resume_recommendation(result, token)
        self.assertIn("python3 Tools/update_queue.py --fixture", rendered)
        command.assert_called_once_with(result, {
            "batch": "B1",
            "queue_consistency_receipt": "queue-check",
            "close_gate_receipt": "close-gate",
            "delta_apply_receipt": "delta-apply",
        })

    def test_resume_status_selects_one_token_and_reports_live_snapshot(self):
        result = runtime_result(items=[])
        output = io.StringIO()
        with mock.patch.object(
                check_queue, "maintenance_gate_inventory",
                return_value={"selected": None, "compatible": [], "stale": []}), \
                mock.patch.object(
                    check_queue, "current_receipt_catalog", return_value={}), \
                mock.patch.object(
                    check_queue, "resume_next_action",
                    return_value="materialize-required-queue") as selector, \
                mock.patch.object(
                    check_queue, "_resume_recommendation",
                    return_value="materialize the Queue") as recommendation, \
                contextlib.redirect_stdout(output):
            check_queue._print_resume_status(result, [])

        selector.assert_called_once_with(result, [])
        recommendation.assert_called_once_with(
            result, "materialize-required-queue")
        text = output.getvalue()
        self.assertIn("live.required_queue_sha256=%s" % SHA_QUEUE, text)
        self.assertEqual(
            ["next_action=materialize-required-queue"],
            [line for line in text.splitlines()
             if line.startswith("next_action=")])
        self.assertIn("recommended_action=materialize the Queue", text)

    def test_json_mode_routes_human_output_and_one_canonical_receipt(self):
        def fake_run(parsed, produced):
            self.assertEqual("/memory/repo", parsed.root)
            self.assertIsInstance(produced, list)
            print("human report")
            produced.append({"receipt_id": "audit-json"})
            return 2

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(check_queue, "_run", side_effect=fake_run), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = check_queue.main(["/memory/repo", "--json"])

        self.assertEqual(2, code)
        self.assertEqual(
            [{"receipt_id": "audit-json"}], json.loads(stdout.getvalue()))
        self.assertIn("human report", stderr.getvalue())


class CheckQueueContractTests(unittest.TestCase):
    def run_case(self, result=None, **argument_overrides):
        result = result or runtime_result()
        output = io.StringIO()
        with mock.patch.object(
                check_queue, "validate_runtime", return_value=result), \
                mock.patch.object(
                    check_queue, "reviewed_without_current_evidence",
                    return_value=[]), \
                contextlib.redirect_stdout(output):
            code = check_queue._run(
                arguments(**argument_overrides), None)
        return code, output.getvalue()

    def test_related_options_fail_before_consumer_routing(self):
        cases = (
            ({"confirmation_receipt": "confirm"},
             "only valid with --require-ready"),
            ({"boundary_gate_receipt": ["gate=receipt"]},
             "only valid with --require-revalidation"),
            ({"readback_rule": "rule"},
             "only valid with --deliver-readback"),
            ({"deliver_readback": "B1"},
             "requires --readback-rule"),
            ({"phase": "preflight"},
             "only valid with --deliver-phase"),
            ({"deliver_phase": "B1"}, "requires --phase"),
            ({"ack_activation_phase": "B1", "phase": "preflight"},
             "requires --phase, --phase-nonce"),
            ({"phase_nonce": "nonce"},
             "--phase-nonce is only valid"),
            ({"phase_delivery_receipt": "delivery"},
             "--phase-delivery-receipt is only valid"),
            ({"phase_part": 1}, "--phase-part is only valid"),
            ({"deliver_phase": "B1", "phase": "preflight",
              "phase_part": -1}, "must not be negative"),
            ({"budget_manifest_receipt": "budget"},
             "maintenance evidence receipts are only valid"),
            ({"require_maintenance_complete": True,
              "budget_manifest_receipt": "budget"},
             "requires --budget-manifest-receipt"),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                code, output = self.run_case(**options)
                self.assertEqual(1, code, output)
                self.assertIn(expected, output)

    def test_status_projection_turns_only_open_work_facts_into_holds(self):
        cases = (
            (runtime_result(items=[]),
             "Queue is valid but empty"),
            (runtime_result(
                ready=[], blocked={"B1": ["dependency B0 is open"]}),
             "no executable batch"),
            (dict(runtime_result(), _writer_locks=[{
                "path": ".cambium/tmp/state-writer.lock",
            }]), "active or interrupted writer lock"),
        )
        for result, expected in cases:
            with self.subTest(expected=expected):
                code, output = self.run_case(result)
                self.assertEqual(2, code, output)
                self.assertIn("[HOLD]", output)
                self.assertIn(expected, output)

    def test_require_ready_classifies_missing_state_terminal_and_blocked(self):
        opened = [{
            "id": "B1", "order": 1, "state": "open",
            "hold_state": "none",
        }]
        cases = (
            (runtime_result(items=[]), 1, "does not exist"),
            (runtime_result(items=opened, ready=[]), 1, "open, not queued"),
            (runtime_result(task_state="complete"), 1,
             "is terminal and cannot activate"),
            (runtime_result(
                ready=[], blocked={"B1": ["dependency B0 is open"]}),
             2, "is not executable"),
        )
        for result, expected_code, expected in cases:
            with self.subTest(expected=expected):
                code, output = self.run_case(
                    result, require_ready="B1")
                self.assertEqual(expected_code, code, output)
                self.assertIn(expected, output)

    def test_require_ready_consumes_one_exact_confirmation_link(self):
        def confirmation_result():
            return runtime_result(
                ready=[], blocked={"B1": [
                    "confirmation receipt absent",
                    "hold=confirmation-required",
                ]})

        activation = {
            "card_bundle_sha256": "sha256:" + "4" * 64,
            "delivery_assurance": "fixture",
        }
        catalog = {"confirm-1": ("receipts.jsonl", {"receipt_id": "confirm-1"})}
        with mock.patch.object(
                check_queue, "current_receipt_catalog",
                return_value=catalog), \
                mock.patch.object(check_queue, "require_receipt") as exact, \
                mock.patch.object(
                    check_queue.card_activation, "build_activation_context",
                    return_value=activation) as build, \
                mock.patch.object(check_queue, "_write_receipt") as write:
            code, output = self.run_case(
                confirmation_result(), require_ready="B1",
                confirmation_receipt="confirm-1")

        self.assertEqual(0, code, output)
        exact.assert_called_once_with(
            catalog, "confirm-1", "B1 confirmation", mock.ANY,
            expected={"check": "confirmation", "target": "B1"})
        build.assert_called_once()
        self.assertEqual("require-ready:B1", write.call_args.args[5])
        self.assertEqual(activation,
                         write.call_args.kwargs["activation_context"])
        self.assertEqual("confirm-1",
                         write.call_args.kwargs["confirmation_receipt"])

        def stale_link(_catalog, _receipt_id, _label, errors, **_kwargs):
            errors.append("confirmation receipt is stale")

        with mock.patch.object(
                check_queue, "current_receipt_catalog",
                return_value=catalog), \
                mock.patch.object(
                    check_queue, "require_receipt", side_effect=stale_link), \
                mock.patch.object(
                    check_queue.card_activation,
                    "build_activation_context") as build:
            code, output = self.run_case(
                confirmation_result(), require_ready="B1",
                confirmation_receipt="confirm-1")
        self.assertEqual(1, code, output)
        self.assertIn("confirmation receipt is stale", output)
        build.assert_not_called()

    def test_completion_gate_delegates_without_repeating_owner_errors(self):
        result = runtime_result(errors=["existing completion error"])
        with mock.patch.object(
                check_queue, "required_queue_completion_errors",
                return_value=[
                    "existing completion error", "new completion error",
                ]) as predicate:
            code, output = self.run_case(
                result, require_complete=True)

        self.assertEqual(1, code, output)
        predicate.assert_called_once_with(result)
        self.assertEqual(1, output.count("existing completion error"))
        self.assertEqual(1, output.count("new completion error"))

    def test_revalidation_connects_boundary_ids_to_one_owner_context(self):
        context = {"gate_receipts": {"gate-a": "receipt-a"}}
        with mock.patch.object(
                check_queue, "standards_revalidation_producer_eligibility",
                return_value=None) as eligibility, \
                mock.patch.object(
                    check_queue, "standards_revalidation_context",
                    return_value=(context, [])) as build, \
                mock.patch.object(check_queue, "_write_receipt") as write:
            code, output = self.run_case(
                require_revalidation="B1",
                boundary_gate_receipt=["gate-a=receipt-a"])

        self.assertEqual(0, code, output)
        eligibility.assert_called_once_with(mock.ANY, "B1")
        build.assert_called_once_with(
            mock.ANY, "B1", {"gate-a": "receipt-a"})
        self.assertEqual("require-revalidation:B1", write.call_args.args[5])
        self.assertEqual(
            context,
            write.call_args.kwargs["standards_revalidation_context"])

        with mock.patch.object(
                check_queue, "standards_revalidation_producer_eligibility",
                return_value="revalidation evidence is stale"), \
                mock.patch.object(
                    check_queue, "standards_revalidation_context") as build:
            code, output = self.run_case(
                require_revalidation="B1",
                boundary_gate_receipt=["gate-a=receipt-a"])
        self.assertEqual(1, code, output)
        self.assertIn("revalidation evidence is stale", output)
        build.assert_not_called()

    def test_readback_requires_the_linked_current_activation_receipt(self):
        item = {
            "id": "B1", "order": 1, "state": "open",
            "hold_state": "none", "activation_receipt": "activate-1",
        }
        activation = {
            "receipt_id": "activate-1",
            "tool": queue_runtime.TOOL,
            "tool_version": queue_runtime.TOOL_VERSION,
        }
        result = runtime_result(items=[item], ready=[])
        readback = {
            "readback_delivery_payload": {"rule_id": "rule-1"},
            "readback_addendum_sha256": "sha256:" + "5" * 64,
            "delivery_assurance": "fixture",
        }
        with mock.patch.object(
                check_queue, "current_receipt_catalog",
                return_value={"activate-1": ("activation.jsonl", activation)}), \
                mock.patch.object(
                    check_queue.card_activation, "context_from_receipt",
                    return_value={"activation": "current"}), \
                mock.patch.object(
                    check_queue.card_activation, "build_readback_addendum",
                    return_value=readback) as build, \
                mock.patch.object(check_queue, "_write_receipt") as write:
            code, output = self.run_case(
                result, deliver_readback="B1", readback_rule="rule-1")

        self.assertEqual(0, code, output)
        build.assert_called_once_with(
            result["root"], {"activation": "current"}, "rule-1")
        self.assertEqual("deliver-readback:B1:rule-1",
                         write.call_args.args[5])
        self.assertEqual(readback,
                         write.call_args.kwargs["readback_context"])

        stale = dict(activation, tool_version="retired")
        with mock.patch.object(
                check_queue, "current_receipt_catalog",
                return_value={"activate-1": ("activation.jsonl", stale)}), \
                mock.patch.object(
                    check_queue.card_activation,
                    "build_readback_addendum") as build:
            code, output = self.run_case(
                runtime_result(items=[item], ready=[]),
                deliver_readback="B1", readback_rule="rule-1")
        self.assertEqual(1, code, output)
        self.assertIn("no current Card-first activation receipt", output)
        build.assert_not_called()

    def test_maintenance_gate_receives_one_indivisible_consumer_view(self):
        closed = [{
            "id": "B1", "order": 1, "state": "closed",
            "hold_state": "none",
        }]
        result = runtime_result(items=closed, ready=[])
        consumer = object()
        context = {"maintenance_run_id": "run-1"}
        with mock.patch.object(
                check_queue.MaintenanceConsumerContext, "from_runtime",
                return_value=consumer) as from_runtime, \
                mock.patch.object(
                    check_queue, "maintenance_completion_gate_errors",
                    return_value=([], context)) as predicate, \
                mock.patch.object(check_queue, "_write_receipt") as write:
            code, output = self.run_case(
                result, require_maintenance_complete=True,
                budget_manifest_receipt="budget-1",
                ledger_advance_receipt="ledger-1",
                watermark_advance_receipt="watermark-1")

        self.assertEqual(0, code, output)
        from_runtime.assert_called_once_with(result)
        predicate.assert_called_once_with(
            consumer, "budget-1", "ledger-1", "watermark-1")
        self.assertEqual("require-maintenance-complete",
                         write.call_args.args[5])
        self.assertEqual(context,
                         write.call_args.kwargs["maintenance_context"])

    def test_resume_status_connects_recovery_and_current_card_delivery(self):
        item = {
            "id": "B1", "order": 1, "state": "open",
            "hold_state": "none", "activation_receipt": "activate-1",
        }
        result = runtime_result(items=[item], ready=[])
        recorded = {"receipt_id": "activate-1"}
        recovery = {"status": "not-applicable", "selected": {}}
        delivery = {"card_bundle_sha256": "sha256:" + "6" * 64}
        with mock.patch.object(
                check_queue, "batch_close_recovery_inventory",
                return_value=recovery) as inventory, \
                mock.patch.object(
                    check_queue.card_activation, "build_activation_context",
                    return_value=delivery) as build, \
                mock.patch.object(
                    check_queue, "current_receipt_catalog",
                    return_value={
                        "activate-1": ("activation.jsonl", recorded),
                    }), \
                mock.patch.object(
                    check_queue.card_activation, "context_from_receipt",
                    return_value={"recorded": "current"}), \
                mock.patch.object(
                    check_queue.card_activation, "exact_bundle_errors",
                    return_value=[]) as exact, \
                mock.patch.object(check_queue, "_print_resume_status") as show, \
                mock.patch.object(check_queue, "_write_receipt") as write:
            code, output = self.run_case(result, resume_status=True)

        self.assertEqual(2, code, output)
        inventory.assert_called_once_with(result)
        build.assert_called_once_with(
            result["root"], result["progress"], result["items_by_id"]["B1"],
            runtime_state=result)
        exact.assert_called_once_with(delivery, {"recorded": "current"})
        show.assert_called_once_with(result, [])
        self.assertEqual("resume-status", write.call_args.args[5])
        self.assertEqual(
            [{
                "batch_id": "B1",
                "parent_activation_receipt": "activate-1",
                **delivery,
            }],
            write.call_args.kwargs["resume_activation_contexts"])

    def test_metadata_and_admission_owners_supply_candidate_facts_only(self):
        result = runtime_result()
        result["structural_admission_defects"] = [
            "hub page requires serial integration",
        ]
        output = io.StringIO()
        with mock.patch.object(
                check_queue, "validate_runtime", return_value=result), \
                mock.patch.object(
                    check_queue, "reviewed_without_current_evidence",
                    return_value=["Topics/A.md"]) as reviewed, \
                contextlib.redirect_stdout(output):
            code = check_queue._run(arguments(), None)

        self.assertEqual(2, code, output.getvalue())
        reviewed.assert_called_once_with(result["coverage"])
        self.assertIn("hub page requires serial integration",
                      output.getvalue())
        self.assertIn("Topics/A.md", output.getvalue())


class CheckQueueFileBoundaryTests(unittest.TestCase):
    def test_receipt_target_is_repository_contained_and_not_a_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            receipt_root = root / ".cambium/receipts"
            receipt_root.mkdir(parents=True)
            result = runtime_result(root=root)
            receipt = {"receipt_id": "audit-file-boundary", "result": "pass"}
            with mock.patch.object(
                    check_queue, "make_check_receipt",
                    return_value=receipt):
                emitted = check_queue._write_receipt(
                    root, ".cambium/receipts/checks.jsonl", result,
                    "pass", "details", "consistency")
            self.assertEqual(receipt, emitted)
            self.assertEqual(
                [receipt],
                [json.loads(line) for line in
                 (receipt_root / "checks.jsonl").read_text(
                     encoding="utf-8").splitlines()])

            outside = Path(directory) / "outside.jsonl"
            outside.write_text("outside\n", encoding="utf-8")
            (receipt_root / "escape.jsonl").symlink_to(outside)
            with self.assertRaisesRegex(
                    ValueError, "outside the repository root|symlink|regular file"):
                check_queue._write_receipt(
                    root, ".cambium/receipts/escape.jsonl", result,
                    "pass", "details", "consistency")


class TaskProgressTerminalStateUnitTests(unittest.TestCase):
    """The Progress owner rejects impossible terminal substates."""

    def test_noncomplete_task_cannot_claim_passed_maintenance_completion(self):
        progress = {
            "task_id": "task-1",
            "task_state": "planned",
            "contract": {"completion_semantics": "maintenance"},
            "task_transition_receipts": [],
            "checkpoint": {"recorded_at": None},
            "terminal_audit": {"state": "not-applicable"},
            "maintenance_completion": maintenance_completion(
                state="passed",
                completion_gate_receipt="audit-fake-gate",
                budget_manifest_receipt="audit-fake-budget",
                ledger_advance_receipt="audit-fake-ledger",
                watermark_advance_receipt="audit-fake-watermark",
            ),
        }
        with mock.patch.object(
                task_progress, "live_read_set_load_findings",
                return_value=([], [])), mock.patch.object(
                task_progress, "accounted_upstream_revision_ids",
                return_value=set()), mock.patch.object(
                task_progress, "contract_anchor_chain",
                return_value=([], [])), mock.patch.object(
                task_progress, "pending_control_ids",
                return_value=([], [])):
            errors, context = task_progress.task_transition_errors(
                "/unread", progress, {},
                {"queue_revision": 1, "state_revision": 0},
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                "sha256:" + "3" * 64,
                1, {}, {}, None,
            )
        self.assertEqual("initial", context["checkpoint_binding"])
        errors = "\n".join(errors)
        self.assertIn(
            "maintenance task_state=planned requires "
            "maintenance_completion.state=pending",
            errors,
        )
        self.assertIn(
            "non-complete maintenance task requires "
            "maintenance_completion.completion_gate_receipt=null",
            errors,
        )

    def test_complete_build_requires_persisted_terminal_proof_bytes(self):
        queue_sha = "sha256:" + "1" * 64
        coverage_sha = "sha256:" + "2" * 64
        progress_sha = "sha256:" + "3" * 64
        proof = {
            "receipt_id": "proof-1",
            "terminal_proof_path": ".cambium/receipts/proof.yaml",
            "terminal_proof_sha256": "sha256:" + "4" * 64,
            "progress_ledger_sha256": "sha256:" + "5" * 64,
        }
        transition = {
            "receipt_id": "transition-1",
            "before_task_state": "completion-candidate",
            "after_task_state": "complete",
            "checked_at": "2026-01-01T00:00:00Z",
            "before_progress_sha256": proof["progress_ledger_sha256"],
            "after_progress_sha256": progress_sha,
            "after_coverage_sha256": coverage_sha,
            "after_required_queue_sha256": queue_sha,
            "queue_revision": 1,
            "queue_state_revision": 2,
            "evidence_receipt": proof["receipt_id"],
        }
        progress = {
            "task_id": "task-1",
            "task_state": "complete",
            "contract": {"completion_semantics": "build"},
            "task_transition_receipts": [transition["receipt_id"]],
            "checkpoint": {
                "recorded_at": transition["checked_at"],
                "task_state": "complete",
                "task_transition_receipt": transition["receipt_id"],
                "coverage_sha256": coverage_sha,
                "required_queue_sha256": queue_sha,
                "queue_revision": 1,
                "queue_state_revision": 2,
                "summary": "complete",
            },
            "terminal_audit": {
                "state": "passed",
                "terminal_proof_path": proof["terminal_proof_path"],
                "terminal_proof_sha256": proof["terminal_proof_sha256"],
                "terminal_proof_receipt": proof["receipt_id"],
                "queue_check_receipt": "queue-1",
            },
            "maintenance_completion": {"state": "not-applicable"},
        }
        catalog = {
            transition["receipt_id"]: ("fixture.jsonl", transition),
            proof["receipt_id"]: ("fixture.jsonl", proof),
        }

        def admitted_receipt(catalog, receipt_id, _label, _errors,
                             expected=None):
            del expected
            return catalog.get(receipt_id, (None, None))[1]

        with contextlib.ExitStack() as stack:
            for patch in (
                    mock.patch.object(
                        task_progress, "live_read_set_load_findings",
                        return_value=([], [])),
                    mock.patch.object(
                        task_progress, "accounted_upstream_revision_ids",
                        return_value=set()),
                    mock.patch.object(
                        task_progress, "contract_anchor_chain",
                        return_value=([], [])),
                    mock.patch.object(
                        task_progress, "pending_control_ids",
                        return_value=([], [])),
                    mock.patch.object(
                        task_progress, "require_receipt",
                        side_effect=admitted_receipt),
                    mock.patch.object(
                        task_progress, "task_transition_receipt_record_errors",
                        return_value=[]),
                    mock.patch.object(
                        task_progress, "historical_receipt_identity_errors",
                        return_value=[]),
                    mock.patch.object(
                        task_progress,
                        "terminal_proof_profile_binding_errors",
                        return_value=[]),
                    mock.patch.object(
                        task_progress.kblib, "managed_repository_path",
                        side_effect=OSError("missing"))):
                stack.enter_context(patch)
            errors, context = task_progress.task_transition_errors(
                "/unread", progress, catalog,
                {"queue_revision": 1, "state_revision": 2},
                queue_sha, coverage_sha, progress_sha,
                0, {}, {}, None,
            )

        self.assertEqual("current", context["checkpoint_binding"])
        self.assertIn(
            "complete Terminal Proof is unsafe or missing: missing", errors)


def _maintenance_gate_errors(case):
    result = runtime_validation.validate_runtime(case.root)
    consumer = queue_runtime.MaintenanceConsumerContext.from_runtime(result)
    errors, gate_context = queue_runtime.maintenance_completion_gate_errors(
        consumer, *case.maintenance_evidence_ids())
    return result, errors, gate_context


class MaintenanceCompletionCheckpointIntegrationTests(
        MaintenanceClosedCheckpointCase):
    """Maintenance predicates consume one generated post-batch checkpoint."""

    def test_gate_binds_the_exact_budget_manifest_bytes(self):
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        budget_path.write_text(
            budget_path.read_text(encoding="utf-8").replace(
                "state: closed", "state: open"),
            encoding="utf-8",
        )
        _result, errors, _context = _maintenance_gate_errors(self)
        self.assertTrue(any(
            "does not bind current budget_manifest_path bytes" in error
            for error in errors), errors)

    def test_gate_binds_watermark_batch_to_the_budget_manifest(self):
        _budget_id, _ledger_id, watermark_id = self.maintenance_evidence_ids()
        watermark_path = self.root / runtime_paths.WATERMARK_PATH
        watermark = kblib.load_yaml_file(watermark_path)
        watermark["last_batch_id"] = "B-NOT-IN-QUEUE"
        watermark_path.write_text(
            kblib.canonical_yaml(watermark), encoding="utf-8")

        evidence_path = \
            self.root / ".cambium/receipts/maintenance-evidence.jsonl"
        receipts = [json.loads(line) for line in evidence_path.read_text(
            encoding="utf-8").splitlines()]
        receipt = next(value for value in receipts
                       if value["receipt_id"] == watermark_id)
        receipt["after_watermark_sha256"] = kblib.sha256_file(watermark_path)
        receipt["watermark_batch_id"] = watermark["last_batch_id"]
        evidence_path.write_text(
            "".join(json.dumps(value) + "\n" for value in receipts),
            encoding="utf-8",
        )

        _result, errors, _context = _maintenance_gate_errors(self)
        self.assertTrue(any(
            "last_batch_id is not one of the budget manifest "
            "required_batch_ids" in error for error in errors), errors)

    def test_gate_enforces_page_and_hour_budget(self):
        budget_id, _ledger_id, _watermark_id = \
            self.maintenance_evidence_ids()
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        budget = kblib.load_yaml_file(budget_path)
        budget["budget_limit"] = 1
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        _result, errors, _context = _maintenance_gate_errors(self)
        self.assertIn(
            "maintenance budget manifest selects 2 pages, exceeding "
            "budget_limit 1", errors)

        budget["budget_unit"] = "hours"
        budget["budget_limit"] = 1.5
        budget["consumed_hours"] = None
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        _result, errors, _context = _maintenance_gate_errors(self)
        self.assertTrue(any(
            "consumed_hours must be a number >= 0" in error
            for error in errors), errors)

        budget["consumed_hours"] = 2.0
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        _result, errors, _context = _maintenance_gate_errors(self)
        self.assertTrue(any(
            "consumed_hours 2.0 exceeds budget_limit 1.5" in error
            for error in errors), errors)

        budget["consumed_hours"] = 1.25
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        evidence_path = \
            self.root / ".cambium/receipts/maintenance-evidence.jsonl"
        receipts = [json.loads(line) for line in evidence_path.read_text(
            encoding="utf-8").splitlines()]
        next(receipt for receipt in receipts
             if receipt["receipt_id"] == budget_id)[
                 "budget_manifest_sha256"] = kblib.sha256_file(budget_path)
        evidence_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        _result, errors, _context = _maintenance_gate_errors(self)
        self.assertEqual([], errors)

    def test_resume_retires_gate_after_its_evidence_changes(self):
        result, errors, context = _maintenance_gate_errors(self)
        self.assertEqual([], errors)
        gate = queue_check_receipt.make_check_receipt(
            result, "pass", "current maintenance checkpoint",
            "require-maintenance-complete", maintenance_context=context,
        )
        kblib.write_receipts(
            self.root / ".cambium/receipts/maintenance-gate.jsonl", [gate])
        gate_id = gate["receipt_id"]
        current = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], current["errors"], current["errors"])
        inventory = queue_runtime.maintenance_gate_inventory(current)
        self.assertEqual(gate_id, inventory["selected"])

        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        budget = kblib.load_yaml_file(budget_path)
        budget["deferred_count"] = 1
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        changed = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], changed["errors"], changed["errors"])
        inventory = queue_runtime.maintenance_gate_inventory(changed)
        self.assertIsNone(inventory["selected"])
        self.assertEqual(
            [gate_id], [entry["receipt_id"] for entry in inventory["stale"]])
        self.assertEqual(
            "run-maintenance-completion-gate",
            runtime_resume.resume_next_action(changed, changed["errors"]),
        )


if __name__ == "__main__":
    unittest.main()
