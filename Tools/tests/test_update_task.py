"""Layered tests for the canonical Task transition writer.

The fast tests consume already parsed Task state. Filesystem-backed tests
start at one current checkpoint and exercise only the adjacent writer seam.
Only the explicitly slow class creates competing processes or interrupts a
partially published build-completion transaction.
"""

import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"

from Tools.execution.audit import check_proof
from Tools.execution.audit import terminal_proof_contract
from Tools.execution.task_runtime import check_queue
from Tools.execution.task_runtime import queue_check_receipt
from Tools.execution.task_runtime import queue_runtime
from Tools.execution.task_runtime import runtime_validation
from Tools.execution.task_runtime import update_task
from Tools.execution.task_runtime.queue_runtime import canon as queue_canon
from Tools.execution.task_runtime.queue_runtime import task_record
from Tools.platform.common import kblib
from Tools.platform.distribution import stamp_cards
from Tools.tests.fixtures.integration.update_queue_checkpoints import (
    install_update_queue_checkpoint,
)
from Tools.tests.support.profile_fixture import install_loadable_profile


def _sha(character):
    return "sha256:" + character * 64


def transition_result(*, task_state="planned", checkpoint=None,
                      completion_semantics="build"):
    """Return the minimal parsed input owned by ``build_task_transition``."""
    return {
        "progress": {
            "task_id": "TASK-UNIT",
            "task_state": task_state,
            "task_transition_receipts": [],
            "guidance_queue": [],
            "amendments": [],
            "checkpoint": checkpoint,
            "terminal_audit": {
                "state": "not-started",
                "terminal_proof_path": None,
                "terminal_proof_sha256": None,
                "terminal_proof_receipt": None,
                "queue_check_receipt": None,
            },
            "maintenance_completion": {
                "state": "not-applicable",
                "completion_gate_receipt": None,
                "budget_manifest_receipt": None,
                "ledger_advance_receipt": None,
                "watermark_advance_receipt": None,
            },
            "contract": {
                "completion_semantics": completion_semantics,
                "selected_profile_manifest": "profiles/test/profile.toml",
            },
        },
        "queue": {
            "task_id": "TASK-UNIT",
            "queue_revision": 1,
            "state_revision": 0,
            "required_queue": [],
        },
        "remaining": 1,
        "coverage_sha256": _sha("a"),
        "queue_sha256": _sha("b"),
        "progress_sha256": _sha("c"),
    }


_RUNTIME_CHECKPOINT_TEMPORARIES = {}
_RUNTIME_CHECKPOINTS = {}


def current_runtime_checkpoint(name="current"):
    """Build the Profile dependency closure once, then return stable bytes."""
    if name not in _RUNTIME_CHECKPOINTS:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "repo"
        shutil.copytree(FIXTURE, root)
        install_loadable_profile(root)
        result = runtime_validation.validate_runtime(root)
        if result["errors"]:
            raise AssertionError(
                "update_task checkpoint is not current: %s" %
                result["errors"])
        _RUNTIME_CHECKPOINT_TEMPORARIES[name] = temporary
        _RUNTIME_CHECKPOINTS[name] = root
    return _RUNTIME_CHECKPOINTS[name]


class TaskTransitionProjectionUnitTests(unittest.TestCase):
    """Pure transition projections over already parsed Task state."""

    def test_transition_builder_enforces_owner_edges_reasons_and_time(self):
        with self.assertRaisesRegex(
                ValueError, "owned by update_queue.py"):
            update_task.build_task_transition(
                transition_result(), "active", "2026-08-04T00:00:00Z",
                "cannot bypass first open", None,
            )
        with self.assertRaisesRegex(
                ValueError, "paused transition requires"):
            update_task.build_task_transition(
                transition_result(), "paused", "2026-08-04T00:00:00Z",
                None, None,
            )
        with self.assertRaisesRegex(
                ValueError, "timezone-aware"):
            update_task.build_task_transition(
                transition_result(), "paused", "2026-08-04T00:00:00",
                "pause", None,
            )

        checkpoint = {
            "recorded_at": "2026-08-04T01:00:00+01:00",
        }
        update_task.build_task_transition(
            transition_result(checkpoint=checkpoint),
            "paused", "2026-08-04T00:00:01Z", "later instant", None,
        )
        with self.assertRaisesRegex(ValueError, "precedes checkpoint"):
            update_task.build_task_transition(
                transition_result(checkpoint=checkpoint),
                "paused", "2026-08-03T23:59:59Z", "earlier instant", None,
            )

    def test_build_completion_projects_only_the_consumed_terminal_proof(self):
        result = transition_result(task_state="completion-candidate")
        result["remaining"] = 0
        terminal = {
            "checked_at": "2026-08-04T00:30:00Z",
            "terminal_proof_path": ".cambium/receipts/proof.yaml",
            "terminal_proof_sha256": _sha("d"),
            "queue_check_receipt": "audit-queue-complete",
            "selected_profile_manifest": "profiles/test/profile.toml",
            "profile_snapshot_sha256": _sha("e"),
            "profile_contract_fingerprint": _sha("f"),
            "profile_load_inputs_sha256": _sha("1"),
            "repository_snapshot_sha256": _sha("2"),
        }
        with mock.patch.object(
                update_task, "_terminal_proof_receipt",
                return_value=terminal) as consume:
            progress, _text, receipt = update_task.build_task_transition(
                result, "complete", "2026-08-04T01:00:00Z", None,
                None, terminal_proof_receipt="audit-terminal-proof",
            )

        consume.assert_called_once_with(result, "audit-terminal-proof")
        self.assertEqual("complete", progress["task_state"])
        self.assertEqual("passed", progress["terminal_audit"]["state"])
        self.assertEqual(
            "audit-terminal-proof",
            progress["terminal_audit"]["terminal_proof_receipt"],
        )
        for field in update_task.TERMINAL_BINDING_FIELDS:
            self.assertEqual(terminal[field], receipt[field], field)

    def test_maintenance_completion_projects_only_the_consumed_gate(self):
        result = transition_result(completion_semantics="maintenance")
        result["remaining"] = 0
        gate = {
            "checked_at": "2026-08-04T00:30:00Z",
            "budget_manifest_receipt": "audit-budget",
            "ledger_advance_receipt": "audit-ledger",
            "watermark_advance_receipt": "audit-watermark",
        }
        with mock.patch.object(
                update_task, "_maintenance_completion_receipt",
                return_value=gate) as consume:
            progress, _text, receipt = update_task.build_task_transition(
                result, "complete", "2026-08-04T01:00:00Z", None,
                None, maintenance_completion_receipt="audit-maintenance",
            )

        consume.assert_called_once_with(result, "audit-maintenance")
        self.assertEqual("complete", progress["task_state"])
        self.assertEqual(
            {
                "state": "passed",
                "completion_gate_receipt": "audit-maintenance",
                "budget_manifest_receipt": "audit-budget",
                "ledger_advance_receipt": "audit-ledger",
                "watermark_advance_receipt": "audit-watermark",
            },
            progress["maintenance_completion"],
        )
        self.assertEqual("audit-maintenance", receipt["evidence_receipt"])


class TaskTransitionContractTests(unittest.TestCase):
    """Receipt and public writer-input contracts, without a runtime tree."""

    def test_writer_identity_and_receipt_envelope_are_canonical(self):
        self.assertEqual(queue_canon.TASK_TRANSITION_TOOL, update_task.TOOL)
        self.assertEqual(
            queue_canon.TASK_TRANSITION_TOOL_VERSION,
            update_task.TOOL_VERSION,
        )
        self.assertEqual(
            queue_canon.TASK_TRANSITION_CHECK,
            update_task.TASK_TRANSITION_CHECK,
        )

        progress, _text, receipt = update_task.build_task_transition(
            transition_result(), "paused", "2026-08-04T00:00:00Z",
            "operator pause", None,
        )
        self.assertEqual("paused", progress["task_state"])
        self.assertEqual(
            [], update_task.current_task_transition_receipt_errors(receipt))
        malformed = dict(receipt)
        malformed.pop("after_progress_sha256")
        self.assertIn(
            "task transition Receipt misses after_progress_sha256",
            update_task.current_task_transition_receipt_errors(malformed),
        )

    def test_produced_receipt_satisfies_task_progress_consumer_contract(self):
        _progress, _text, receipt = update_task.build_task_transition(
            transition_result(), "paused", "2026-08-04T00:00:00Z",
            "operator pause", None,
        )
        consumer_errors = task_record.task_transition_receipt_record_errors(
            {}, receipt["receipt_id"], receipt, "build",
            expected_contract_sha=receipt["contract_sha256"],
        )
        self.assertEqual([], consumer_errors)
        invalid = dict(receipt, after_task_state="complete")
        self.assertIn(
            "illegal edge 'planned' -> 'complete'",
            "\n".join(task_record.task_transition_receipt_record_errors(
                {}, receipt["receipt_id"], invalid, "build",
                expected_contract_sha=receipt["contract_sha256"],
            )),
        )

    def test_public_writer_rejects_role_and_stale_cas_before_writing(self):
        result = transition_result()
        result["errors"] = []

        def invoke(*, actor_role, progress_sha=None):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), mock.patch.object(
                    update_task.runtime_validation, "validate_runtime",
                    side_effect=[result, {"errors": []}]), \
                    mock.patch.object(
                        update_task.queue_runtime,
                        "runtime_authority_context", return_value={}), \
                    mock.patch.object(
                        update_task.queue_runtime,
                        "runtime_authority_validation_kwargs",
                        return_value={}), \
                    mock.patch.object(
                        update_task.kblib, "managed_repository_path",
                        return_value=Path("/not-written")):
                code = update_task.main([
                    "/not-read", "--transition", "paused",
                    "--checkpoint-summary", "operator pause",
                    "--expected-progress-sha256",
                    progress_sha or result["progress_sha256"],
                    "--expected-queue-sha256", result["queue_sha256"],
                    "--actor-role", actor_role,
                    "--at", "2026-08-04T01:00:00Z", "--apply",
                ])
            return code, output.getvalue()

        code, output = invoke(actor_role="worker")
        self.assertEqual(1, code)
        self.assertIn("only actor-role integrator", output)

        code, output = invoke(
            actor_role="integrator", progress_sha=_sha("0"))
        self.assertEqual(1, code)
        self.assertIn("expected Progress fingerprint", output)


class CurrentRuntimeCase(unittest.TestCase):
    """Private copy of one current runtime for an adjacent writer seam."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(current_runtime_checkpoint("current"), self.root)

    def result(self):
        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"], result["errors"])
        return result

    def progress(self):
        return kblib.load_yaml_file(
            self.root / queue_runtime.PROGRESS_PATH)

    def invoke(self, state, *, summary=None, at="2026-08-04T01:00:00Z",
               json_output=False):
        current = self.result()
        arguments = [
            str(self.root), "--transition", state,
            "--expected-progress-sha256",
            current["progress_sha256"],
            "--expected-queue-sha256", current["queue_sha256"],
            "--actor-role", "integrator", "--at", at, "--apply",
        ]
        if summary is not None:
            arguments.extend(["--checkpoint-summary", summary])
        if json_output:
            arguments.append("--json")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            returncode = update_task.main(arguments)
        return returncode, stdout.getvalue(), stderr.getvalue()


class TaskTransitionIntegrationTests(CurrentRuntimeCase):
    """One real Progress/Receipt writer-to-validator connection."""

    def test_pause_json_transport_and_persisted_readback(self):
        code, stdout, stderr = self.invoke(
            "paused", summary="operator interruption",
            json_output=True,
        )
        self.assertEqual(0, code, stderr)
        records = json.loads(stdout)
        self.assertEqual(1, len(records))
        self.assertEqual(
            update_task.TASK_TRANSITION_RECEIPT_TYPE_ID,
            records[0]["receipt_type_id"],
        )
        paused = self.result()
        self.assertEqual("paused", paused["progress"]["task_state"])
        self.assertEqual(
            "current", paused["task_runtime"]["checkpoint_binding"])


class OpenBatchCancellationIntegrationTests(unittest.TestCase):
    """Cancellation consumes one static open-batch checkpoint."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        install_update_queue_checkpoint(self.root, "merge-admission-b1")

    def test_cancel_preserves_incomplete_batch_and_terminates_resume(self):
        current = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], current["errors"], current["errors"])
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = update_task.main([
                str(self.root), "--transition", "cancelled",
                "--checkpoint-summary",
                "user terminated the current Task Contract",
                "--expected-progress-sha256", current["progress_sha256"],
                "--expected-queue-sha256", current["queue_sha256"],
                "--actor-role", "integrator", "--at",
                "2026-08-04T02:00:00Z", "--apply",
            ])
        self.assertEqual(0, code, stdout.getvalue() + stderr.getvalue())

        resumed = io.StringIO()
        with contextlib.redirect_stdout(resumed):
            resume_code = check_queue.main([
                str(self.root), "--resume-status",
            ])
        output = resumed.getvalue()
        self.assertEqual(0, resume_code, output)
        self.assertIn("task_state=cancelled", output)
        self.assertIn("batches.open=B1", output)
        self.assertIn("next_action=archive-terminal-runtime", output)
        self.assertIn("preserve any unfinished batch", output)
        self.assertNotIn("in-flight batch(es) require resume", output)


class BuildCompletionPublicationRecoverySlowTests(CurrentRuntimeCase):
    """Build-completion publication failures preserve exact recovery state."""

    def replace_profile_with_valid_revision(self):
        owner = (
            self.root /
            "profiles/test-profile/policies/residual-disposition.md"
        )
        text = owner.read_text(encoding="utf-8")
        before = "The fixture accepts no production candidate;"
        after = "The revised fixture accepts no production candidate;"
        self.assertIn(before, text)
        owner.write_text(text.replace(before, after), encoding="utf-8")

    def completion_context(self):
        """Produce one legal proof consumer input through machine owners."""
        result = self.result()
        result["root"] = str(self.root)
        receipt_result = dict(result)
        receipt_result["remaining"] = 0
        queue_receipt = queue_check_receipt.make_check_receipt(
            receipt_result, "pass", "fixture Queue completion",
            "require-complete",
        )
        queue_receipt["checked_at"] = "2026-08-04T00:20:00Z"

        proof_path = ".cambium/receipts/update-task-proof.yaml"
        absolute_proof = self.root / proof_path
        absolute_proof.write_text("proof: current\n", encoding="utf-8")
        terminal = check_proof._make_receipt(
            terminal_proof_contract.PRODUCER_TOOL,
            terminal_proof_contract.PRODUCER_TOOL_VERSION,
            terminal_proof_contract.GATE_CHECK,
            proof_path, "pass", "fixture Terminal Proof", 1,
        )
        terminal["checked_at"] = "2026-08-04T00:30:00Z"
        contract = result["progress"]["contract"]
        profile_view = result["_profile_authorized_view"]
        terminal.update({
            "task_id": result["progress"]["task_id"],
            "scope_version": contract["scope_version"],
            "contract_version": contract["contract_version"],
            "upstream_revision_id": contract["upstream_revision_id"],
            "selected_profile_manifest":
                contract["selected_profile_manifest"],
            "coverage_ledger_sha256": result["coverage_sha256"],
            "progress_ledger_sha256": result["progress_sha256"],
            "required_queue_path": queue_runtime.QUEUE_PATH,
            "queue_revision": result["queue"]["queue_revision"],
            "queue_state_revision": result["queue"]["state_revision"],
            "required_queue_sha256": result["queue_sha256"],
            "remaining_required_work_units": 0,
            "queue_check_receipt": queue_receipt["receipt_id"],
            "corpus_plan_check_receipt": "audit-fixture-corpus-plan",
            "terminal_proof_path": proof_path,
            "terminal_proof_sha256": kblib.sha256_file(absolute_proof),
            "repository_snapshot_sha256":
                kblib.repository_snapshot_sha256(self.root),
            "profile_snapshot_sha256":
                profile_view["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                profile_view["profile_contract_fingerprint"],
            "profile_load_inputs_sha256":
                profile_view["profile_load_inputs_sha256"],
        })
        self.assertEqual(
            [], terminal_proof_contract.current_receipt_errors(terminal))

        result["progress"] = copy.deepcopy(result["progress"])
        result["progress"]["task_state"] = "completion-candidate"
        result["remaining"] = 0
        catalog = {
            queue_receipt["receipt_id"]: ("fixture.jsonl", queue_receipt),
            terminal["receipt_id"]: ("fixture.jsonl", terminal),
        }
        return result, catalog, terminal["receipt_id"]

    def run_completion(self, result, catalog, receipt_id, *patches):
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(mock.patch.object(
                update_task.runtime_validation, "validate_runtime",
                return_value=result))
            stack.enter_context(mock.patch.object(
                update_task.queue_runtime, "current_receipt_catalog",
                return_value=catalog))
            for patch in patches:
                stack.enter_context(patch)
            returncode = update_task.main([
                str(self.root), "--transition", "complete",
                "--terminal-proof-receipt", receipt_id,
                "--expected-progress-sha256", result["progress_sha256"],
                "--expected-queue-sha256", result["queue_sha256"],
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z", "--apply",
            ])
        return returncode, output.getvalue()

    def test_profile_change_during_receipt_append_preserves_recovery_intent(self):
        result, catalog, receipt_id = self.completion_context()
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        receipt_path = self.root / update_task.RECEIPT_PATH
        progress_before = progress_path.read_bytes()
        receipts_before = receipt_path.read_text(
            encoding="utf-8").splitlines()
        real_write = kblib.write_receipts_observed
        mutated = False

        def mutate_during_transition_append(path, receipts, **kwargs):
            nonlocal mutated
            outcome = real_write(path, receipts, **kwargs)
            if (not mutated and any(
                    row.get("check") == update_task.TASK_TRANSITION_CHECK
                    for row in receipts)):
                mutated = True
                self.replace_profile_with_valid_revision()
            return outcome

        returncode, output = self.run_completion(
            result, catalog, receipt_id,
            mock.patch.object(
                kblib, "write_receipts_observed",
                side_effect=mutate_during_transition_append),
        )

        self.assertTrue(mutated)
        self.assertEqual(1, returncode, output)
        self.assertIn("runtime authority changed during task receipt", output)
        self.assertIn("recovery is incomplete", output)
        self.assertEqual(progress_before, progress_path.read_bytes())
        added = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()[len(receipts_before):]]
        self.assertEqual(
            [update_task.TASK_TRANSITION_CHECK, "task_transition_abort"],
            [row.get("check") for row in added],
        )
        self.assertEqual(
            added[0]["receipt_id"],
            added[1]["aborted_task_transition_receipt"],
        )
        self.assertEqual(
            "present", added[1]["task_transition_receipt_outcome"])
        lock_path = self.root / ".cambium/tmp/state-writer.lock"
        self.assertTrue(lock_path.is_dir())

    def test_repository_change_after_progress_write_rolls_back_before_receipt(self):
        result, catalog, receipt_id = self.completion_context()
        cards, _read_sets = stamp_cards.discover_cards(self.root)
        card = self.root / cards["R08"]["path"]
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        receipt_path = self.root / update_task.RECEIPT_PATH
        progress_before = progress_path.read_bytes()
        receipts_before = receipt_path.read_text(
            encoding="utf-8").splitlines()
        real_write = kblib.atomic_write_text
        mutated = False

        def mutate_after_progress_write(path, text, **kwargs):
            nonlocal mutated
            outcome = real_write(path, text, **kwargs)
            if not mutated:
                mutated = True
                card.write_text(
                    card.read_text(encoding="utf-8") +
                    "\n<!-- repository race -->\n",
                    encoding="utf-8",
                )
            return outcome

        returncode, output = self.run_completion(
            result, catalog, receipt_id,
            mock.patch.object(
                kblib, "atomic_write_text",
                side_effect=mutate_after_progress_write),
        )

        self.assertTrue(mutated)
        self.assertEqual(1, returncode, output)
        self.assertIn("repository_snapshot_sha256 changed", output)
        self.assertEqual(progress_before, progress_path.read_bytes())
        added = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()[len(receipts_before):]]
        self.assertEqual(
            ["task_transition_abort"],
            [row.get("check") for row in added],
        )
        self.assertEqual(
            "absent", added[0]["task_transition_receipt_outcome"])
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())


class TaskTransitionConcurrencySlowTests(CurrentRuntimeCase):
    """One real process race verifies the Task writer's locked CAS seam."""

    def test_two_prevalidated_writers_leave_one_winner_without_false_lock(self):
        barrier = self.root.parent / "update-task-prevalidated"
        barrier.mkdir()
        current = self.result()
        arguments = [
            "--transition", "paused",
            "--checkpoint-summary", "coordinated competing pause",
            "--expected-progress-sha256", current["progress_sha256"],
            "--expected-queue-sha256", current["queue_sha256"],
            "--actor-role", "integrator",
            "--at", "2026-08-04T01:00:00Z", "--apply",
        ]
        program = r'''
import contextlib
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
from Tools.platform.common import kblib
from Tools.execution.task_runtime import update_task

real_lock = kblib.runtime_write_lock
barrier = sys.argv[3]

@contextlib.contextmanager
def coordinated_lock(root, **kwargs):
    marker = os.path.join(barrier, str(os.getpid()))
    with open(marker, "x", encoding="utf-8") as handle:
        handle.write("ready\n")
    deadline = time.monotonic() + 10
    while len(os.listdir(barrier)) < 2:
        if time.monotonic() >= deadline:
            raise RuntimeError("competing writer did not reach barrier")
        time.sleep(0.01)
    with real_lock(root, timeout=10, poll_interval=0.01,
                   owner_metadata=kwargs.get("owner_metadata")) as lease:
        yield lease

kblib.runtime_write_lock = coordinated_lock
raise SystemExit(update_task.main([sys.argv[2]] + sys.argv[4:]))
'''
        command = [
            sys.executable, "-c", program, str(REPOSITORY), str(self.root),
            str(barrier), *arguments,
        ]
        writers = [
            subprocess.Popen(
                command, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            for _ in range(2)
        ]
        outputs = [writer.communicate(timeout=20)[0] for writer in writers]
        self.assertEqual(
            [0, 1], sorted(writer.returncode for writer in writers),
            "\n--- writer ---\n".join(outputs),
        )
        loser = outputs[
            [writer.returncode for writer in writers].index(1)]
        self.assertIn("changed after validation", loser)
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())
        self.assertEqual("paused", self.result()["progress"]["task_state"])


if __name__ == "__main__":
    unittest.main()
