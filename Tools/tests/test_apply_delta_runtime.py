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

import apply_delta
import check_queue
import kblib
from profile_fixture import install_loadable_profile


class CanonicalApplyDeltaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def append_receipt(self, receipt_id, target, check="fixture"):
        receipt = {
            "receipt_id": receipt_id,
            "check": check,
            "target": target,
            "result": "pass",
            "invalidated_by": None,
        }
        if check == check_queue.BATCH_REVIEW_CHECK:
            receipt.update({
                "tool": check_queue.MANUAL_ATTESTATION_TOOL,
                "tool_version":
                    check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
                "task_id": "fixture-task", "batch_id": target,
                "delta_page_receipt_ids": ["audit-page-a"],
            })
        kblib.write_receipts(
            self.root / ".cambium/receipts/fixture.jsonl",
            [receipt],
        )

    def run_tool(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def queue_gate(self, *mode):
        relative = ".cambium/receipts/gates.jsonl"
        completed = self.run_tool(
            "check_queue.py", *mode, "--receipts", relative
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        records = [
            json.loads(line) for line in
            (self.root / relative).read_text(encoding="utf-8").splitlines()
        ]
        return records[-1]["receipt_id"]

    def queue_expected(self):
        queue = self.load(check_queue.QUEUE_PATH)
        return str(queue["state_revision"]), kblib.sha256_file(
            self.root / check_queue.QUEUE_PATH
        )

    def transition(self, *arguments):
        completed = self.run_tool("update_queue.py", *arguments)
        self.assertEqual(0, completed.returncode, completed.stdout)

    def make_merge_ready(self, page_fields=None):
        gate = self.queue_gate("--require-ready", "B1")
        revision, queue_sha = self.queue_expected()
        self.transition(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator",
            "--at", "2026-08-04T01:00:00Z", "--apply",
        )
        self.append_receipt("audit-page-a", "Topics/A.md")
        self.append_receipt("audit-batch-b1", "B1", check="batch_gate")
        page = {
            "path": "Topics/A.md",
            "authoring_status": "reviewed",
            "gate_receipts": ["audit-page-a"],
        }
        page.update(page_fields or {})
        delta = {
            "batch": "B1",
            "generated_at": "2026-08-04T02:00:00Z",
            "pages": [page],
            "open_gaps_added": [],
            "open_gaps_closed": [],
            "next_batch_updates": ["Topics/A.md -> B2"],
            "watermark_advance": None,
        }
        delta_path = self.root / ".cambium/deltas/B1.yaml"
        delta_path.parent.mkdir(parents=True, exist_ok=True)
        delta_path.write_text(kblib.canonical_yaml(delta), encoding="utf-8")
        revision, queue_sha = self.queue_expected()
        self.transition(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-b1",
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator",
            "--at", "2026-08-04T02:00:00Z", "--apply",
        )

    def apply_arguments(self, receipt=".cambium/receipts/applied.jsonl"):
        return [
            check_queue.COVERAGE_PATH, ".cambium/deltas/B1.yaml",
            "--root", str(self.root), "--apply",
            "--actor-role", "integrator",
            "--expected-coverage-sha256", kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH
            ),
            "--expected-queue-sha256", kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH
            ),
            "--receipts", receipt,
        ]

    def invoke(self, arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = apply_delta.main(arguments)
        return code, output.getvalue()

    def assert_no_write_debris(self):
        coverage = self.root / check_queue.COVERAGE_PATH
        self.assertFalse(Path(str(coverage) + ".bak").exists())
        self.assertFalse(Path(str(coverage) + ".tmp").exists())
        self.assertEqual([], list(self.root.rglob(".cambium-write-*")))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists()
        )

    def test_control_field_rejects_entire_delta_without_any_write(self):
        before = (self.root / check_queue.COVERAGE_PATH).read_bytes()
        with self.assertRaisesRegex(AssertionError, "control field"):
            self.make_merge_ready({"next_batch": None})
        self.assertEqual(before,
                         (self.root / check_queue.COVERAGE_PATH).read_bytes())
        self.assertFalse(
            (self.root / ".cambium/receipts/applied.jsonl").exists()
        )
        self.assert_no_write_debris()

    def test_every_declared_control_field_is_forbidden(self):
        for field in sorted(apply_delta.CONTROL_FIELDS):
            with self.subTest(field=field):
                errors = apply_delta._delta_policy_errors({
                    "batch": "B1",
                    "pages": [{"path": "Topics/A.md", field: None}],
                })
                self.assertTrue(any(field in error for error in errors), errors)

    def test_gap_delta_adds_and_closes_by_page_type_without_partial_guessing(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["open_gaps"] = [{
            "page": "Topics/A.md", "type": "link", "note": "old gap",
        }]
        merged = apply_delta._merge_coverage_sections(
            kblib.canonical_yaml(coverage), {
                "generated_at": "2026-08-04T03:00:00Z",
                "open_gaps_closed": [{
                    "page": "Topics/A.md", "type": "link",
                }],
                "open_gaps_added": [{
                    "page": "Topics/B.md", "type": "rereview",
                    "note": "downstream reasoning changed",
                }],
            },
        )
        result = kblib.parse_yaml_subset(merged)
        self.assertEqual("2026-08-04T03:00:00Z", result["updated_at"])
        self.assertEqual([{
            "page": "Topics/B.md", "type": "rereview",
            "note": "downstream reasoning changed",
        }], result["open_gaps"])
        with self.assertRaisesRegex(ValueError, "absent gap"):
            apply_delta._merge_coverage_sections(
                merged, {"open_gaps_added": [], "open_gaps_closed": [{
                    "page": "Topics/A.md", "type": "link",
                }]})

    def test_detached_mode_cannot_write_canonical_runtime_state(self):
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(kblib.canonical_yaml({
            "batch": "B1", "generated_at": "2026-08-04T00:00:00Z",
            "pages": [], "open_gaps_added": [],
            "open_gaps_closed": [], "next_batch_updates": [],
            "watermark_advance": None,
        }), encoding="utf-8")
        coverage = self.root / check_queue.COVERAGE_PATH
        before = coverage.read_bytes()
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "apply_delta.py"),
             str(coverage), str(delta), "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("canonical ledger access requires --root",
                      completed.stdout)
        self.assertEqual(before, coverage.read_bytes())
        self.assertFalse(Path(str(coverage) + ".bak").exists())

    def test_detached_receipt_cannot_overwrite_runtime_state(self):
        coverage_copy = self.root / "coverage-copy.yaml"
        delta_copy = self.root / "delta-copy.yaml"
        coverage_copy.write_bytes(
            (self.root / check_queue.COVERAGE_PATH).read_bytes())
        delta_copy.write_text(kblib.canonical_yaml({
            "batch": "B1", "generated_at": "2026-08-04T00:00:00Z",
            "pages": [], "open_gaps_added": [],
            "open_gaps_closed": [], "next_batch_updates": [],
            "watermark_advance": None,
        }), encoding="utf-8")
        state = self.root / check_queue.QUEUE_PATH
        before = state.read_bytes()
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "apply_delta.py"),
             str(coverage_copy), str(delta_copy),
             "--receipts", str(state)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("canonical receipt access requires --root",
                      completed.stdout)
        self.assertEqual(before, state.read_bytes())

    def test_existing_writer_lock_blocks_without_mutation(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        before = coverage_path.read_bytes()
        lock = self.root / ".cambium/tmp/state-writer.lock"
        lock.mkdir()
        (lock / "owner.json").write_text(
            json.dumps({"lock_name": "state-writer", "pid": 999999}) + "\n",
            encoding="utf-8",
        )

        code, output = self.invoke(self.apply_arguments())

        self.assertEqual(1, code, output)
        self.assertIn("active or interrupted writer lock", output)
        self.assertEqual(before, coverage_path.read_bytes())
        self.assertFalse(
            (self.root / ".cambium/receipts/applied.jsonl").exists()
        )

    def test_stale_coverage_or_queue_sha_fails_before_lock_and_write(self):
        self.make_merge_ready()
        coverage = self.root / check_queue.COVERAGE_PATH
        before = coverage.read_bytes()
        base = self.apply_arguments()
        cases = (
            ("--expected-coverage-sha256", "sha256:" + "0" * 64,
             "Coverage fingerprint is stale"),
            ("--expected-queue-sha256", "sha256:" + "1" * 64,
             "Queue fingerprint is stale"),
        )
        for option, stale, message in cases:
            with self.subTest(option=option):
                arguments = list(base)
                arguments[arguments.index(option) + 1] = stale
                code, output = self.invoke(arguments)
                self.assertEqual(1, code, output)
                self.assertIn(message, output)
                self.assertEqual(before, coverage.read_bytes())
                self.assertFalse(
                    (self.root / ".cambium/receipts/applied.jsonl").exists()
                )
                self.assert_no_write_debris()

    def test_locked_cas_rejection_does_not_leave_false_recovery_lock(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        concurrent = self.load(check_queue.COVERAGE_PATH)
        concurrent["updated_at"] = "2026-08-04T02:30:00Z"
        concurrent_text = kblib.canonical_yaml(concurrent)
        real_lock = apply_delta.kblib.runtime_write_lock

        @contextlib.contextmanager
        def competing_write_after_lock(root, **kwargs):
            with real_lock(root, **kwargs) as lease:
                coverage_path.write_text(concurrent_text, encoding="utf-8")
                yield lease

        with mock.patch.object(
                apply_delta.kblib, "runtime_write_lock",
                new=competing_write_after_lock):
            code, output = self.invoke(self.apply_arguments())

        self.assertEqual(1, code, output)
        self.assertIn("runtime changed before write", output)
        self.assertEqual(
            concurrent_text, coverage_path.read_text(encoding="utf-8"))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())
        self.assertFalse(
            (self.root / ".cambium/receipts/applied.jsonl").exists())

    def test_success_uses_writer_lock_merges_state_and_writes_bound_receipt(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        before_coverage_sha = kblib.sha256_file(coverage_path)
        queue_sha = kblib.sha256_file(self.root / check_queue.QUEUE_PATH)
        progress_sha = kblib.sha256_file(self.root / check_queue.PROGRESS_PATH)
        real_atomic = kblib.atomic_write_text
        observed_owner = {}

        def inspect_lock(path, text, validator=None):
            if Path(path).resolve() == coverage_path.resolve():
                owner_path = (
                    self.root / ".cambium/tmp/state-writer.lock/owner.json"
                )
                observed_owner.update(json.loads(
                    owner_path.read_text(encoding="utf-8")
                ))
            return real_atomic(path, text, validator=validator)

        with mock.patch.object(
                apply_delta.kblib, "atomic_write_text",
                side_effect=inspect_lock):
            code, output = self.invoke(self.apply_arguments())

        self.assertEqual(0, code, output)
        operation = observed_owner["operation"]
        self.assertEqual("B1", operation["batch_id"])
        self.assertEqual(before_coverage_sha,
                         operation["before_coverage_sha256"])
        self.assertEqual(queue_sha,
                         operation["before_required_queue_sha256"])
        self.assertEqual(queue_sha,
                         operation["planned_after_required_queue_sha256"])
        self.assertEqual(progress_sha,
                         operation["before_progress_sha256"])
        self.assertEqual(progress_sha,
                         operation["planned_after_progress_sha256"])
        self.assertEqual(queue_sha, operation["required_queue_sha256"])
        self.assertEqual(
            kblib.sha256_file(self.root / ".cambium/deltas/B1.yaml"),
            operation["delta_sha256"],
        )
        self.assertRegex(operation["planned_after_coverage_sha256"],
                         r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(operation["receipt_id"].startswith(
            "audit-apply_delta-"))
        self.assertEqual(".cambium/receipts/applied.jsonl",
                         operation["receipt_path"])

        coverage = self.load(check_queue.COVERAGE_PATH)
        page = coverage["pages"][0]
        self.assertEqual("reviewed", page["authoring_status"])
        self.assertEqual(["audit-page-a"], page["gate_receipts"])
        self.assertEqual("B1", page["next_batch"])
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        receipt = json.loads(
            (self.root / ".cambium/receipts/applied.jsonl")
            .read_text(encoding="utf-8")
        )
        self.assertEqual("delta_apply", receipt["check"])
        self.assertEqual("B1", receipt["batch_id"])
        self.assertEqual(before_coverage_sha,
                         receipt["before_coverage_sha256"])
        self.assertEqual(kblib.sha256_file(coverage_path),
                         receipt["after_coverage_sha256"])
        self.assertEqual(queue_sha, receipt["required_queue_sha256"])
        self.assertEqual(operation["delta_sha256"], receipt["delta_sha256"])
        self.assert_no_write_debris()

    def test_canonical_apply_runs_profile_load_producer_once(self):
        self.make_merge_ready()
        producer = check_queue.check_profile.evaluate_profile_load
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                wraps=producer) as evaluate:
            code, output = self.invoke(self.apply_arguments())
        self.assertEqual(0, code, output)
        self.assertEqual(1, evaluate.call_count)
        self.assert_no_write_debris()

    def test_hard_exit_records_three_ledger_recovery_state(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        queue_path = self.root / check_queue.QUEUE_PATH
        progress_path = self.root / check_queue.PROGRESS_PATH
        before_coverage_sha = kblib.sha256_file(coverage_path)
        before_queue_sha = kblib.sha256_file(queue_path)
        before_progress_sha = kblib.sha256_file(progress_path)
        program = """
import os
import sys

sys.path.insert(0, sys.argv[1])
import apply_delta

root = os.path.realpath(sys.argv[2])
coverage = os.path.realpath(os.path.join(
    root, apply_delta.check_queue.COVERAGE_PATH
))
real_atomic = apply_delta.kblib.atomic_write_text

def write_then_crash(path, text, validator=None):
    result = real_atomic(path, text, validator=validator)
    if os.path.realpath(path) == coverage:
        os._exit(23)
    return result

apply_delta.kblib.atomic_write_text = write_then_crash
raise SystemExit(apply_delta.main(sys.argv[3:]))
"""
        child = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS), str(self.root),
             *self.apply_arguments()],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, child.returncode, child.stdout)

        after_coverage_sha = kblib.sha256_file(coverage_path)
        self.assertNotEqual(before_coverage_sha, after_coverage_sha)
        self.assertEqual(before_queue_sha, kblib.sha256_file(queue_path))
        self.assertEqual(before_progress_sha, kblib.sha256_file(progress_path))

        lock = self.root / ".cambium/tmp/state-writer.lock/owner.json"
        self.assertTrue(lock.is_file())
        operation = json.loads(lock.read_text(encoding="utf-8"))["operation"]
        self.assertEqual(before_coverage_sha,
                         operation["before_coverage_sha256"])
        self.assertEqual(after_coverage_sha,
                         operation["planned_after_coverage_sha256"])
        self.assertEqual(before_queue_sha,
                         operation["before_required_queue_sha256"])
        self.assertEqual(before_queue_sha,
                         operation["planned_after_required_queue_sha256"])
        self.assertEqual(before_progress_sha,
                         operation["before_progress_sha256"])
        self.assertEqual(before_progress_sha,
                         operation["planned_after_progress_sha256"])

        resume = self.run_tool("check_queue.py", "--resume-status")
        self.assertIn(resume.returncode, (1, 2), resume.stdout)
        self.assertIn("state.coverage phase=planned-after", resume.stdout)
        self.assertIn("state.queue phase=before", resume.stdout)
        self.assertIn("state.progress phase=before", resume.stdout)
        self.assertIn("partial write is possible", resume.stdout)

    def test_receipt_failure_rolls_back_coverage(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        before = coverage_path.read_bytes()
        receipt_path = self.root / ".cambium/receipts/applied.jsonl"

        with mock.patch.object(
                apply_delta.kblib, "write_receipts",
                side_effect=OSError("injected receipt publication failure")):
            code, output = self.invoke(self.apply_arguments())

        self.assertEqual(1, code, output)
        self.assertIn("rollback attempted", output)
        self.assertEqual(before, coverage_path.read_bytes())
        self.assertFalse(receipt_path.exists())
        self.assert_no_write_debris()

    def test_concurrent_receipt_creator_is_not_overwritten_or_deleted(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        before = coverage_path.read_bytes()
        receipt_path = self.root / ".cambium/receipts/applied.jsonl"
        external = {
            "receipt_id": "audit-external-concurrent",
            "check": "external",
            "target": "unrelated",
            "result": "pass",
            "invalidated_by": None,
        }
        real_append = kblib.write_receipts

        def create_external_then_publish(path, receipts, exclusive=False):
            real_append(path, [external])
            return real_append(path, receipts, exclusive=exclusive)

        with mock.patch.object(
                apply_delta.kblib, "write_receipts",
                side_effect=create_external_then_publish):
            code, output = self.invoke(self.apply_arguments())

        self.assertEqual(1, code, output)
        self.assertEqual(before, coverage_path.read_bytes())
        self.assertEqual(
            [external],
            [json.loads(line) for line in
             receipt_path.read_text(encoding="utf-8").splitlines()],
        )
        self.assert_no_write_debris()

    def test_failure_after_own_receipt_preserves_both_records_and_lock(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        before = coverage_path.read_bytes()
        receipt_path = self.root / ".cambium/receipts/applied.jsonl"
        external = {
            "receipt_id": "audit-external-after-own",
            "check": "external",
            "target": "unrelated",
            "result": "pass",
            "invalidated_by": None,
        }
        own = {}
        real_append = kblib.write_receipts

        def own_and_external_then_fail(path, receipts, exclusive=False):
            own.update(receipts[0])
            real_append(path, receipts, exclusive=exclusive)
            real_append(path, [external])
            raise OSError("injected failure after durable own append")

        with mock.patch.object(
                apply_delta.kblib, "write_receipts",
                side_effect=own_and_external_then_fail):
            code, output = self.invoke(self.apply_arguments())

        self.assertEqual(1, code, output)
        self.assertEqual(before, coverage_path.read_bytes())
        records = [json.loads(line) for line in
                   receipt_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(
            [own["receipt_id"], external["receipt_id"]],
            [record["receipt_id"] for record in records],
        )
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock/owner.json").is_file()
        )
        recovery = check_queue.validate_runtime(self.root)
        lock = recovery["writer_locks"][0]
        self.assertEqual("matching",
                         lock["operation_receipt"]["status"])
        self.assertTrue(lock["operation_receipt"]["matching_receipt"])
        self.assertEqual(
            {"coverage": "before", "progress": "before", "queue": "before"},
            {name: phase["phase"] for name, phase in
             lock["state_phases"].items()},
        )

    def test_exclusive_creation_without_complete_record_preserves_lock(self):
        self.make_merge_ready()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        before = coverage_path.read_bytes()
        receipt_path = self.root / ".cambium/receipts/applied.jsonl"

        with mock.patch.object(apply_delta.kblib.os, "write", return_value=0):
            code, output = self.invoke(self.apply_arguments())

        self.assertEqual(1, code, output)
        self.assertEqual(before, coverage_path.read_bytes())
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(b"", receipt_path.read_bytes())
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock/owner.json").is_file()
        )


if __name__ == "__main__":
    unittest.main()
