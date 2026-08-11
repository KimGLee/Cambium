import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import check_queue
import kblib
import update_task
from profile_fixture import install_loadable_profile


class UpdateTaskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def run_tool(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def progress(self):
        return kblib.load_yaml_file(self.root / check_queue.PROGRESS_PATH)

    def transition(self, state, *arguments, at="2026-08-04T01:00:00Z"):
        completed = self.run_tool(
            "update_task.py", "--transition", state,
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", at, "--apply",
            *arguments,
        )
        return completed

    def make_task_active_without_open(self):
        paused = self.transition(
            "paused", "--checkpoint-summary",
            "fixture pre-activation interruption",
            at="2026-08-04T00:00:00Z",
        )
        self.assertEqual(0, paused.returncode, paused.stdout)
        active = self.transition(
            "active", "--checkpoint-summary", "fixture pre-activation resume",
            at="2026-08-04T00:00:01Z",
        )
        self.assertEqual(0, active.returncode, active.stdout)

    def reset_to_planned(self):
        progress = self.progress()
        progress["task_state"] = "planned"
        progress["task_transition_receipts"] = []
        progress["checkpoint"] = {
            "recorded_at": None,
            "summary": None,
            "task_state": "planned",
            "task_transition_receipt": None,
            "coverage_sha256": None,
            "required_queue_sha256": None,
            "queue_revision": progress["queue_revision"],
            "queue_state_revision": progress["queue_state_revision"],
        }
        (self.root / check_queue.PROGRESS_PATH).write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        retained = [line for line in receipt_path.read_text(
            encoding="utf-8").splitlines()
                    if json.loads(line).get("receipt_id") !=
                    "audit-update_task-fixture-active-0001"]
        receipt_path.write_text("\n".join(retained) + "\n", encoding="utf-8")

    def terminal_proof_fixture(self):
        """Return one current proof/catalog pair for the consumer boundary."""
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        result["root"] = str(self.root)
        progress = result["progress"]
        contract = progress["contract"]
        profile_evidence, profile_errors = check_queue.profile_load_evidence(
            self.root, contract["selected_profile_manifest"])
        self.assertEqual([], profile_errors)

        proof_path = ".cambium/receipts/consumer-proof.yaml"
        absolute_proof = self.root / proof_path
        absolute_proof.write_text("proof: fixture\n", encoding="utf-8")
        queue_receipt_id = "audit-update-task-profile-queue"
        proof_receipt_id = "audit-update-task-profile-proof"
        queue_receipt = {
            "receipt_id": queue_receipt_id,
            "tool": check_queue.TOOL,
            "tool_version": check_queue.TOOL_VERSION,
            "gate_id": "required-queue-completion",
            "check": "required_queue",
            "queue_check_mode": "require-complete",
            "task_id": result["queue"]["task_id"],
            "queue_revision": result["queue"]["queue_revision"],
            "queue_state_revision": result["queue"]["state_revision"],
            "required_queue_sha256": result["queue_sha256"],
            "coverage_ledger_sha256": result["coverage_sha256"],
            "progress_ledger_sha256": result["progress_sha256"],
            "remaining_required_work_units": 0,
            "result": "pass", "invalidated_by": None,
        }
        proof_receipt = {
            "receipt_id": proof_receipt_id,
            "tool": update_task.TERMINAL_PROOF_TOOL,
            "tool_version": update_task.TERMINAL_PROOF_TOOL_VERSION,
            "gate_id": update_task.TERMINAL_PROOF_GATE_ID,
            "check": "proof-check-summary",
            "target": proof_path,
            "terminal_proof_path": proof_path,
            "terminal_proof_sha256": kblib.sha256_file(absolute_proof),
            "queue_check_receipt": queue_receipt_id,
            "task_id": progress["task_id"],
            "scope_version": contract["scope_version"],
            "contract_version": contract["contract_version"],
            "standards_version": contract["standards_version"],
            "selected_profile_manifest":
                contract["selected_profile_manifest"],
            "coverage_ledger_sha256": result["coverage_sha256"],
            "progress_ledger_sha256": result["progress_sha256"],
            "required_queue_path": check_queue.QUEUE_PATH,
            "queue_revision": result["queue"]["queue_revision"],
            "queue_state_revision": result["queue"]["state_revision"],
            "required_queue_sha256": result["queue_sha256"],
            "remaining_required_work_units": 0,
            "profile_snapshot_sha256":
                profile_evidence["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                profile_evidence["profile_contract_fingerprint"],
            "profile_load_inputs_sha256":
                profile_evidence["profile_load_inputs_sha256"],
            "repository_snapshot_sha256":
                kblib.repository_snapshot_sha256(self.root),
            "result": "pass", "invalidated_by": None,
        }
        catalog = {
            queue_receipt_id: ("fixture.jsonl", queue_receipt),
            proof_receipt_id: ("fixture.jsonl", proof_receipt),
        }
        return result, catalog, proof_receipt_id, proof_receipt

    def replace_profile_with_valid_revision(self):
        """Change both Profile snapshot and typed graph while staying valid."""
        slots = self.root / "profiles/test-profile/slots.md"
        text = slots.read_text(encoding="utf-8")
        before = "test-profile-residual-disposition"
        after = "test-profile-residual-disposition-v2"
        self.assertIn(before, text)
        slots.write_text(text.replace(before, after), encoding="utf-8")

    def completion_main_fixture(self):
        result, catalog, receipt_id, receipt = self.terminal_proof_fixture()
        result["progress"]["task_state"] = "completion-candidate"
        result["remaining"] = 0
        receipt["checked_at"] = "2026-08-04T00:30:00Z"
        return result, catalog, receipt_id, receipt

    def test_current_completion_reuses_the_runtime_profile_view(self):
        result, catalog, receipt_id, expected = self.terminal_proof_fixture()
        real_load = check_queue.profile_load_evidence
        with mock.patch.object(
                check_queue, "current_receipt_catalog",
                return_value=catalog), mock.patch.object(
                    check_queue, "profile_load_evidence",
                    wraps=real_load) as load:
            actual = update_task._terminal_proof_receipt(result, receipt_id)
        self.assertIs(expected, actual)
        load.assert_not_called()

    def test_current_completion_rejects_missing_profile_proof_bindings(self):
        for field in ("profile_snapshot_sha256",
                      "profile_contract_fingerprint",
                      "profile_load_inputs_sha256"):
            with self.subTest(field=field):
                result, catalog, receipt_id, receipt = \
                    self.terminal_proof_fixture()
                receipt.pop(field)
                with mock.patch.object(
                        check_queue, "current_receipt_catalog",
                        return_value=catalog):
                    with self.assertRaisesRegex(
                            ValueError, "lacks canonical %s" % field):
                        update_task._terminal_proof_receipt(result, receipt_id)

    def test_current_completion_rejects_forged_profile_proof_bindings(self):
        for field in ("profile_snapshot_sha256",
                      "profile_contract_fingerprint",
                      "profile_load_inputs_sha256"):
            with self.subTest(field=field):
                result, catalog, receipt_id, receipt = \
                    self.terminal_proof_fixture()
                receipt[field] = "sha256:" + "0" * 64
                with mock.patch.object(
                        check_queue, "current_receipt_catalog",
                        return_value=catalog):
                    with self.assertRaisesRegex(
                            ValueError,
                            "%s does not match the current selected Profile" %
                            field):
                        update_task._terminal_proof_receipt(result, receipt_id)

    def test_current_completion_rejects_changed_profile_load_inputs(self):
        """Root-owned profile-load policy is part of current authorization."""
        result, catalog, receipt_id, receipt = self.terminal_proof_fixture()
        interface = self.root / "profiles/README.md"
        interface.write_text(
            interface.read_text(encoding="utf-8") +
            "\nCanonical interface revision B.\n",
            encoding="utf-8",
        )
        replacement, errors = check_queue.profile_load_evidence(
            self.root,
            result["progress"]["contract"]["selected_profile_manifest"],
        )
        self.assertEqual([], errors)
        self.assertEqual(receipt["profile_snapshot_sha256"],
                         replacement["profile_snapshot_sha256"])
        self.assertEqual(receipt["profile_contract_fingerprint"],
                         replacement["profile_contract_fingerprint"])
        self.assertNotEqual(receipt["profile_load_inputs_sha256"],
                            replacement["profile_load_inputs_sha256"])
        with mock.patch.object(
                check_queue, "current_receipt_catalog",
                return_value=catalog):
            with self.assertRaisesRegex(
                    ValueError,
                    "selected Profile authorization is stale"):
                update_task._terminal_proof_receipt(result, receipt_id)

    def test_current_completion_rejects_changed_kernel_read_set(self):
        """A Proof cannot survive a repository revision before consumption."""
        read_set = self.root / "kernel/Read Sets/R08 Audit Read Set.md"
        read_set.parent.mkdir(parents=True, exist_ok=True)
        read_set.write_text("# R08\n\nRevision A.\n", encoding="utf-8")
        result, catalog, receipt_id, _ = self.terminal_proof_fixture()
        read_set.write_text("# R08\n\nRevision B.\n", encoding="utf-8")

        with mock.patch.object(
                check_queue, "current_receipt_catalog",
                return_value=catalog):
            with self.assertRaisesRegex(
                    ValueError,
                    "repository_snapshot_sha256 does not match the current "
                    "repository"):
                update_task._terminal_proof_receipt(result, receipt_id)

    def test_ordinary_transition_loads_profile_once_for_whole_transaction(self):
        """Proposed, locked, and post-write validation reuse one view pair."""
        initial = check_queue.validate_runtime(self.root)
        self.assertEqual([], initial["errors"])
        real_evaluate = check_queue.check_profile.evaluate_profile_load
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                wraps=real_evaluate) as evaluate:
            returncode = update_task.main([
                str(self.root), "--transition", "paused",
                "--checkpoint-summary", "single authority view",
                "--expected-progress-sha256", initial["progress_sha256"],
                "--expected-queue-sha256", initial["queue_sha256"],
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z", "--apply",
            ])

        self.assertEqual(0, returncode, output.getvalue())
        self.assertEqual(1, evaluate.call_count)
        self.assertEqual("paused", self.progress()["task_state"])

    def test_ordinary_transition_rejects_profile_change_during_state_write(self):
        """A valid A -> B Profile race rolls back an ordinary transition."""
        initial = check_queue.validate_runtime(self.root)
        self.assertEqual([], initial["errors"])
        progress_path = self.root / check_queue.PROGRESS_PATH
        receipt_path = self.root / update_task.RECEIPT_PATH
        progress_before = progress_path.read_bytes()
        receipts_before = receipt_path.read_bytes()
        real_evaluate = check_queue.check_profile.evaluate_profile_load
        real_write = kblib.atomic_write_text
        mutated = False

        def mutate_after_state_write(path, text, **kwargs):
            nonlocal mutated
            result = real_write(path, text, **kwargs)
            if not mutated:
                mutated = True
                self.replace_profile_with_valid_revision()
            return result

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                wraps=real_evaluate) as evaluate, mock.patch.object(
                    kblib, "atomic_write_text",
                    side_effect=mutate_after_state_write):
            returncode = update_task.main([
                str(self.root), "--transition", "paused",
                "--checkpoint-summary", "Profile race",
                "--expected-progress-sha256", initial["progress_sha256"],
                "--expected-queue-sha256", initial["queue_sha256"],
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z", "--apply",
            ])

        self.assertTrue(mutated)
        self.assertEqual(1, returncode, output.getvalue())
        self.assertEqual(1, evaluate.call_count)
        self.assertIn("runtime authority changed during Progress write",
                      output.getvalue())
        self.assertEqual(progress_before, progress_path.read_bytes())
        self.assertEqual(receipts_before, receipt_path.read_bytes())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_build_completion_rechecks_profile_under_write_lock(self):
        """A valid Profile replacement after prevalidation must fail closed."""
        result, catalog, receipt_id, receipt = \
            self.completion_main_fixture()
        original_profile = {
            field: receipt[field]
            for field in ("profile_snapshot_sha256",
                          "profile_contract_fingerprint")
        }
        progress_before = (
            self.root / check_queue.PROGRESS_PATH).read_bytes()
        receipts_path = (
            self.root / update_task.RECEIPT_PATH)
        receipts_before = receipts_path.read_bytes()
        real_lock = kblib.runtime_write_lock

        @contextlib.contextmanager
        def replace_profile_under_lock(root, **kwargs):
            with real_lock(root, **kwargs) as lease:
                self.replace_profile_with_valid_revision()
                yield lease

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                check_queue, "validate_runtime",
                side_effect=(result, {"errors": []}, result)), \
                mock.patch.object(
                    check_queue, "current_receipt_catalog",
                    return_value=catalog), mock.patch.object(
                        kblib, "runtime_write_lock",
                        replace_profile_under_lock):
            returncode = update_task.main([
                str(self.root), "--transition", "complete",
                "--terminal-proof-receipt", receipt_id,
                "--expected-progress-sha256", result["progress_sha256"],
                "--expected-queue-sha256", result["queue_sha256"],
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z", "--apply",
            ])

        self.assertEqual(1, returncode, output.getvalue())
        self.assertIn(
            "Profile-load authority",
            output.getvalue(),
        )
        replacement, errors = check_queue.profile_load_evidence(
            self.root,
            result["progress"]["contract"]["selected_profile_manifest"],
        )
        self.assertEqual([], errors)
        for field, before in original_profile.items():
            self.assertNotEqual(before, replacement[field], field)
        self.assertEqual(
            progress_before,
            (self.root / check_queue.PROGRESS_PATH).read_bytes(),
        )
        self.assertEqual(receipts_before, receipts_path.read_bytes())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_build_completion_detects_profile_change_after_locked_recheck(self):
        """The Progress-write boundary closes the post-recheck race."""
        result, catalog, receipt_id, _ = self.completion_main_fixture()
        progress_path = self.root / check_queue.PROGRESS_PATH
        receipt_path = self.root / update_task.RECEIPT_PATH
        progress_before = progress_path.read_bytes()
        receipts_before = receipt_path.read_text(
            encoding="utf-8").splitlines()
        real_write = kblib.atomic_write_text
        mutated = False

        def mutate_after_progress_write(path, text, **kwargs):
            nonlocal mutated
            result = real_write(path, text, **kwargs)
            if not mutated:
                mutated = True
                self.replace_profile_with_valid_revision()
            return result

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                check_queue, "validate_runtime",
                return_value=result), \
                mock.patch.object(
                    check_queue, "current_receipt_catalog",
                    return_value=catalog), mock.patch.object(
                        kblib, "atomic_write_text",
                        side_effect=mutate_after_progress_write):
            returncode = update_task.main([
                str(self.root), "--transition", "complete",
                "--terminal-proof-receipt", receipt_id,
                "--expected-progress-sha256", result["progress_sha256"],
                "--expected-queue-sha256", result["queue_sha256"],
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z", "--apply",
            ])

        self.assertEqual(1, returncode, output.getvalue())
        self.assertTrue(mutated)
        self.assertIn("runtime authority changed during Progress write",
                      output.getvalue())
        self.assertEqual(progress_before, progress_path.read_bytes())
        self.assertNotEqual("complete", self.progress()["task_state"])
        added = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()[len(receipts_before):]]
        self.assertEqual(["task_transition_abort"],
                         [row.get("check") for row in added])
        self.assertEqual("absent",
                         added[0]["task_transition_receipt_outcome"])
        self.assertEqual([], added[0]["rollback_failures"])
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_build_completion_detects_profile_change_during_receipt_append(self):
        """A durable stale pass receipt leaves rollback plus recovery intent."""
        result, catalog, receipt_id, _ = self.completion_main_fixture()
        progress_path = self.root / check_queue.PROGRESS_PATH
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
                    row.get("check") == "task_transition"
                    for row in receipts)):
                mutated = True
                self.replace_profile_with_valid_revision()
            return outcome

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                check_queue, "validate_runtime",
                return_value=result), \
                mock.patch.object(
                    check_queue, "current_receipt_catalog",
                    return_value=catalog), mock.patch.object(
                        kblib, "write_receipts_observed",
                        side_effect=mutate_during_transition_append):
            returncode = update_task.main([
                str(self.root), "--transition", "complete",
                "--terminal-proof-receipt", receipt_id,
                "--expected-progress-sha256", result["progress_sha256"],
                "--expected-queue-sha256", result["queue_sha256"],
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z", "--apply",
            ])

        self.assertTrue(mutated)
        self.assertEqual(1, returncode, output.getvalue())
        self.assertIn("runtime authority changed during task receipt",
                      output.getvalue())
        self.assertIn("recovery is incomplete", output.getvalue())
        self.assertEqual(progress_before, progress_path.read_bytes())
        self.assertNotEqual("complete", self.progress()["task_state"])
        added = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()[len(receipts_before):]]
        self.assertEqual(["task_transition", "task_transition_abort"],
                         [row.get("check") for row in added])
        self.assertEqual(
            added[0]["receipt_id"],
            added[1]["aborted_task_transition_receipt"],
        )
        self.assertEqual("present",
                         added[1]["task_transition_receipt_outcome"])
        self.assertEqual([], added[1]["rollback_failures"])
        lock_path = self.root / ".cambium/tmp/state-writer.lock"
        self.assertTrue(lock_path.is_dir())
        owner = json.loads((lock_path / "owner.json").read_text(
            encoding="utf-8"))
        self.assertEqual(added[1]["receipt_id"],
                         owner["operation"]["abort_receipt_id"])

    def test_build_completion_detects_card_change_after_progress_write(self):
        """The Proof's repository snapshot is CASed after state publication."""
        card = self.root / "kernel/Cards/R08 Audit Card.md"
        card.parent.mkdir(parents=True, exist_ok=True)
        card.write_text("# R08\n\nRevision A.\n", encoding="utf-8")
        result, catalog, receipt_id, _ = self.completion_main_fixture()
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress_before = progress_path.read_bytes()
        receipt_path = self.root / update_task.RECEIPT_PATH
        receipts_before = receipt_path.read_text(
            encoding="utf-8").splitlines()
        real_write = kblib.atomic_write_text
        mutated = False

        def mutate_card_after_progress(path, text, **kwargs):
            nonlocal mutated
            outcome = real_write(path, text, **kwargs)
            if not mutated:
                mutated = True
                card.write_text("# R08\n\nRevision B.\n", encoding="utf-8")
            return outcome

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
                check_queue, "validate_runtime", return_value=result), \
                mock.patch.object(
                    check_queue, "current_receipt_catalog",
                    return_value=catalog), mock.patch.object(
                        kblib, "atomic_write_text",
                        side_effect=mutate_card_after_progress):
            returncode = update_task.main([
                str(self.root), "--transition", "complete",
                "--terminal-proof-receipt", receipt_id,
                "--expected-progress-sha256", result["progress_sha256"],
                "--expected-queue-sha256", result["queue_sha256"],
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z", "--apply",
            ])

        self.assertTrue(mutated)
        self.assertEqual(1, returncode, output.getvalue())
        self.assertIn("repository_snapshot_sha256 changed",
                      output.getvalue())
        self.assertEqual(progress_before, progress_path.read_bytes())
        added = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()[len(receipts_before):]]
        self.assertEqual(["task_transition_abort"],
                         [row.get("check") for row in added])
        self.assertEqual("absent",
                         added[0]["task_transition_receipt_outcome"])
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_pause_and_resume_are_receipt_backed_and_restart_visible(self):
        paused = self.transition(
            "paused", "--checkpoint-summary", "operator interruption")
        self.assertEqual(0, paused.returncode, paused.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("paused", result["progress"]["task_state"])
        self.assertEqual("current",
                         result["task_runtime"]["checkpoint_binding"])
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("next_action=resume-paused-task", resumed.stdout)
        self.assertIn("checkpoint.binding=current", resumed.stdout)
        self.assertIn("task_transition.count=1", resumed.stdout)

        active = self.transition(
            "active", "--checkpoint-summary", "operator resumed",
            at="2026-08-04T02:00:00Z")
        self.assertEqual(0, active.returncode, active.stdout)
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        self.assertEqual("active", self.progress()["task_state"])

    def test_planned_interruption_persists_checkpoint(self):
        self.reset_to_planned()
        paused = self.transition(
            "paused", "--checkpoint-summary", "interrupted during planning")
        self.assertEqual(0, paused.returncode, paused.stdout)
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn('checkpoint.summary="interrupted during planning"',
                      resumed.stdout)
        self.assertIn("next_action=resume-paused-task", resumed.stdout)

    def test_first_open_atomically_activates_planned_task(self):
        self.reset_to_planned()
        gate_path = ".cambium/receipts/ready.jsonl"
        ready = self.run_tool(
            "check_queue.py", "--require-ready", "B1",
            "--receipts", gate_path)
        self.assertEqual(0, ready.returncode, ready.stdout)
        gate = json.loads((self.root / gate_path).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]
        queue = kblib.load_yaml_file(self.root / check_queue.QUEUE_PATH)
        opened = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "open",
            "--gate-receipt", gate,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at",
            "2026-08-04T01:00:00Z", "--apply",
        )
        self.assertEqual(0, opened.returncode, opened.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("active", result["progress"]["task_state"])
        self.assertEqual("open", result["items_by_id"]["B1"]["state"])
        self.assertEqual(1, len(result["progress"][
            "task_transition_receipts"]))

    def test_planned_task_cannot_be_activated_directly(self):
        self.reset_to_planned()
        attempted = self.transition(
            "active", "--checkpoint-summary", "must not bypass first open")
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("owned by update_queue.py", attempted.stdout)
        self.assertEqual("planned", self.progress()["task_state"])

    def test_paused_or_blocked_task_cannot_mutate_queue(self):
        for state in ("paused", "blocked"):
            with self.subTest(state=state):
                self.tearDown()
                self.setUp()
                changed = self.transition(
                    state, "--checkpoint-summary", "%s checkpoint" % state)
                self.assertEqual(0, changed.returncode, changed.stdout)
                attempted = self.run_tool(
                    "update_queue.py", "--id", "B1",
                    "--hold-state", "paused", "--reason", "must fail")
                self.assertEqual(1, attempted.returncode, attempted.stdout)
                self.assertIn("forbids Queue lifecycle/hold writes",
                              attempted.stdout)

    def test_worker_stale_hash_and_time_regression_fail_closed(self):
        self.make_task_active_without_open()
        before = (self.root / check_queue.PROGRESS_PATH).read_bytes()
        worker = self.run_tool(
            "update_task.py", "--transition", "paused",
            "--checkpoint-summary", "worker cannot pause",
            "--expected-progress-sha256", kblib.sha256_bytes(before),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--apply",
        )
        self.assertEqual(1, worker.returncode, worker.stdout)
        stale = self.run_tool(
            "update_task.py", "--transition", "paused",
            "--checkpoint-summary", "stale writer",
            "--expected-progress-sha256", "sha256:" + "0" * 64,
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--apply",
        )
        self.assertEqual(1, stale.returncode, stale.stdout)
        backwards = self.transition(
            "paused", "--checkpoint-summary", "past timestamp",
            at="2026-08-03T23:59:59Z")
        self.assertEqual(1, backwards.returncode, backwards.stdout)
        self.assertEqual(before,
                         (self.root / check_queue.PROGRESS_PATH).read_bytes())

    def test_task_time_order_uses_instants_not_timestamp_spelling(self):
        paused = self.transition(
            "paused", "--checkpoint-summary", "offset pause",
            at="2026-08-03T20:01:00-04:00")
        self.assertEqual(0, paused.returncode, paused.stdout)
        active = self.transition(
            "active", "--checkpoint-summary", "offset resume",
            at="2026-08-04T01:02:00+01:00")
        self.assertEqual(0, active.returncode, active.stdout)
        before = (self.root / check_queue.PROGRESS_PATH).read_bytes()
        backwards = self.transition(
            "paused", "--checkpoint-summary", "absolute regression",
            at="2026-08-04T00:01:30Z")
        self.assertEqual(1, backwards.returncode, backwards.stdout)
        self.assertIn("precedes", backwards.stdout)
        self.assertEqual(before,
                         (self.root / check_queue.PROGRESS_PATH).read_bytes())

    def test_two_prevalidated_writers_leave_one_winner_and_no_false_lock(self):
        """The losing CAS writer must not look like an interrupted write."""
        barrier = self.root.parent / "update-task-prevalidated"
        barrier.mkdir()
        progress_sha = kblib.sha256_file(
            self.root / check_queue.PROGRESS_PATH)
        queue_sha = kblib.sha256_file(self.root / check_queue.QUEUE_PATH)
        arguments = [
            "--transition", "paused",
            "--checkpoint-summary", "coordinated competing pause",
            "--expected-progress-sha256", progress_sha,
            "--expected-queue-sha256", queue_sha,
            "--actor-role", "integrator",
            "--at", "2026-08-04T01:00:00Z", "--apply",
        ]
        program = r'''
import contextlib
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
import kblib
import update_task

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
            raise RuntimeError("competing writer did not reach prevalidated barrier")
        time.sleep(0.01)
    with real_lock(root, timeout=10, poll_interval=0.01,
                   owner_metadata=kwargs.get("owner_metadata")) as lease:
        yield lease

kblib.runtime_write_lock = coordinated_lock
raise SystemExit(update_task.main([sys.argv[2]] + sys.argv[4:]))
'''
        command = [
            sys.executable, "-c", program, str(TOOLS), str(self.root),
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
        loser_output = outputs[
            [writer.returncode for writer in writers].index(1)]
        self.assertIn("changed after validation", loser_output)
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("paused", result["progress"]["task_state"])

    def test_direct_task_state_edit_is_not_a_valid_transition(self):
        progress = self.progress()
        progress["task_state"] = "blocked"
        (self.root / check_queue.PROGRESS_PATH).write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("requires task transition evidence" in error
                            for error in result["errors"]), result["errors"])


if __name__ == "__main__":
    unittest.main()
