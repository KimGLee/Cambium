import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS))

import check_queue
import kblib


class UpdateTaskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(FIXTURE, self.root)

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
