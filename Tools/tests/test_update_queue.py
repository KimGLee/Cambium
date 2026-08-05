import json
from contextlib import contextmanager, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS))

import check_queue
import kblib
import update_queue


class UpdateQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def write_queue(self, queue):
        text = kblib.canonical_yaml(queue)
        (self.root / check_queue.QUEUE_PATH).write_text(text, encoding="utf-8")
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["queue_revision"] = queue["queue_revision"]
        progress["queue_state_revision"] = queue["state_revision"]
        progress["required_queue_sha256"] = kblib.sha256_bytes(text)
        (self.root / check_queue.PROGRESS_PATH).write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "update_queue.py"), str(self.root),
             *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def make_task_active_without_open(self):
        for state, summary, at in (
                ("paused", "fixture pre-activation interruption",
                 "2026-08-04T00:01:00Z"),
                ("active", "fixture pre-activation resume",
                 "2026-08-04T00:02:00Z")):
            completed = subprocess.run(
                [sys.executable, str(TOOLS / "update_task.py"), str(self.root),
                 "--transition", state, "--checkpoint-summary", summary,
                 "--expected-progress-sha256",
                 kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
                 "--expected-queue-sha256",
                 kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
                 "--actor-role", "integrator", "--at", at, "--apply"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout)

    def expected(self):
        queue = self.load(check_queue.QUEUE_PATH)
        return str(queue["state_revision"]), kblib.sha256_file(
            self.root / check_queue.QUEUE_PATH)

    def assert_resume_envelope(self, completed, next_action):
        result = check_queue.validate_runtime(self.root)
        for expected in (
                "task_id=fixture-task",
                'objective="Complete fixture Required Queue batches with durable evidence."',
                'exclusions=["Do not modify profile policy."]',
                "live.coverage_sha256=%s" % result.get("coverage_sha256"),
                "live.progress_sha256=%s" % result.get("progress_sha256"),
                "live.required_queue_sha256=%s" % result.get("queue_sha256"),
                "checkpoint.recorded_at=", "checkpoint.summary=",
                "checkpoint.binding="):
            self.assertIn(expected, completed.stdout)
        self.assertTrue(any(
            line.startswith("  deltas=") or line.startswith("  delta=")
            for line in completed.stdout.splitlines()), completed.stdout)
        self.assertTrue(any(
            line.startswith("  locks=") or line.startswith("  lock=")
            for line in completed.stdout.splitlines()), completed.stdout)
        self.assertEqual(
            ["next_action=%s" % next_action],
            [line for line in completed.stdout.splitlines()
             if line.startswith("next_action=")],
            completed.stdout,
        )

    def append_receipt(self, receipt_id, check="fixture", target="B1",
                       **fields):
        path = self.root / ".cambium/receipts/fixture.jsonl"
        receipt = {
            "receipt_id": receipt_id,
            "check": check,
            "target": target,
            "result": "pass",
            "invalidated_by": None,
        }
        receipt.update(fields)
        kblib.write_receipts(path, [receipt])

    def rewrite_receipt_for_negative_test(self, receipt_id, mutate):
        for path in (self.root / ".cambium/receipts").rglob("*.jsonl"):
            records = [json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip()]
            matched = False
            for record in records:
                if record.get("receipt_id") == receipt_id:
                    mutate(record)
                    matched = True
            if matched:
                path.write_text("".join(json.dumps(record) + "\n"
                                        for record in records), encoding="utf-8")
                return
        self.fail("receipt %s was not found" % receipt_id)

    def refresh_initial_origin(self):
        path = self.root / ".cambium/receipts/task-transitions.jsonl"
        records = [json.loads(line) for line in path.read_text(
            encoding="utf-8").splitlines()]
        for record in records:
            if record.get("receipt_id") == "audit-fixture-initial-queue":
                record["after_required_queue_sha256"] = kblib.sha256_file(
                    self.root / check_queue.QUEUE_PATH)
                record["after_coverage_sha256"] = kblib.sha256_file(
                    self.root / check_queue.COVERAGE_PATH)
        path.write_text("".join(json.dumps(record) + "\n"
                                for record in records), encoding="utf-8")

    def queue_gate(self, *mode):
        relative = ".cambium/receipts/gates.jsonl"
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             *mode, "--receipts", relative], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        records = [json.loads(line) for line in
                   (self.root / relative).read_text(encoding="utf-8").splitlines()]
        return records[-1]["receipt_id"]

    def close_gate(self, batch_id, consistency_receipt, *, mutate=None):
        """Persist a seven-member merged-snapshot gate for the current bytes."""
        queue = self.load(check_queue.QUEUE_PATH)
        item = next(entry for entry in queue["required_queue"]
                    if entry["id"] == batch_id)
        revision = queue["state_revision"]
        runtime = check_queue.validate_runtime(self.root)
        applied = next(
            entry for entry in runtime["applied_delta_receipts"]
            if entry.get("batch") == batch_id)
        delta_apply_receipt = applied["selected_receipt"]
        merged_snapshot_sha256 = kblib.repository_snapshot_sha256(self.root)
        evidence = {}
        integrator_id = "fixture-integrator"
        reviewer_id = "fixture-reviewer"
        for field in check_queue.CLOSED_LIST_EVIDENCE_FIELDS:
            receipt_id = "audit-closed-list-%s-r%d-%s" % (
                batch_id, revision, field)
            self.append_receipt(
                receipt_id, check="closed_list_%s" % field, target=".",
                tool="check_batch_close", tool_version="1.0.0",
                batch_id=batch_id, task_id=queue["task_id"],
                integrator_id=integrator_id, reviewer_id=reviewer_id,
                merged_snapshot_sha256=merged_snapshot_sha256,
                candidate_evidence=[])
            evidence[field] = receipt_id
        attestation_id = "audit-batch-review-attestation-%s-r%d" % (
            batch_id, revision)
        self.append_receipt(
            attestation_id, check="batch_global_review_attestation",
            target=batch_id, tool="check_batch_close", tool_version="1.0.0",
            batch_id=batch_id, task_id=queue["task_id"],
            integrator_id=integrator_id, reviewer_id=reviewer_id,
            merged_snapshot_sha256=merged_snapshot_sha256,
            details="fixture independent review attestation",
            accepted_candidate_ids=[], accepted_candidate_types=[],
            candidate_dispositions=[])
        global_review_id = "audit-batch-global-review-%s-r%d" % (
            batch_id, revision)
        self.append_receipt(
            global_review_id, check="batch_global_review", target=batch_id,
            tool="check_batch_close", tool_version="1.0.0",
            batch_id=batch_id, task_id=queue["task_id"],
            integrator_id=integrator_id, reviewer_id=reviewer_id,
            merged_snapshot_sha256=merged_snapshot_sha256,
            reviewer_attestation_receipt=attestation_id,
            closed_list_evidence=evidence,
        )
        receipt_id = "audit-batch-close-%s-r%d" % (batch_id, revision)
        receipt = {
            "receipt_id": receipt_id,
            "tool": "check_batch_close",
            "tool_version": "1.0.0",
            "check": "batch_close_gate",
            "target": batch_id,
            "batch_id": batch_id,
            "task_id": queue["task_id"],
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "result": "pass",
            "invalidated_by": None,
            "checked_at": "2026-08-04T02:30:00Z",
            "queue_revision": queue["queue_revision"],
            "queue_state_revision": queue["state_revision"],
            "required_queue_sha256": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
            "coverage_ledger_sha256": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "progress_ledger_sha256": kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            "delta_sha256": item["delta_sha256"],
            "delta_apply_receipt": delta_apply_receipt,
            "queue_consistency_receipt": consistency_receipt,
            "merged_snapshot_sha256": merged_snapshot_sha256,
            "reviewer_attestation_receipt": attestation_id,
            "global_review_receipt": global_review_id,
            "closed_list_evidence": evidence,
        }
        if mutate is not None:
            mutate(receipt)
        path = self.root / ".cambium/receipts/close-gates.jsonl"
        kblib.write_receipts(path, [receipt])
        return receipt_id

    def open_b1(self):
        gate = self.queue_gate("--require-ready", "B1")
        revision, fingerprint = self.expected()
        completed = self.command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T01:00:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        return completed

    def merge_b1(self):
        self.open_b1()
        self.append_receipt("audit-page-1", target="Topics/A.md")
        self.append_receipt("audit-batch-1", check="batch_gate")
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T02:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-1\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        revision, fingerprint = self.expected()
        completed = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T02:00:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        return completed

    def apply_batch(self, batch):
        relative = ".cambium/receipts/delta-%s.jsonl" % batch
        completed = subprocess.run(
            [
                sys.executable, str(TOOLS / "apply_delta.py"),
                check_queue.COVERAGE_PATH,
                ".cambium/deltas/%s.yaml" % batch,
                "--root", str(self.root),
                "--expected-coverage-sha256",
                kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
                "--expected-queue-sha256",
                kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
                "--actor-role", "integrator", "--receipts", relative,
                "--apply",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        return json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]

    def apply_b1(self):
        return self.apply_batch("B1")

    def close_b1(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        previous_batch = self.load(check_queue.COVERAGE_PATH)["pages"][0]["batch"]
        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        revision, fingerprint = self.expected()
        completed = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T03:00:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        coverage = self.load(check_queue.COVERAGE_PATH)
        self.assertEqual(previous_batch, coverage["pages"][0]["batch"])
        return completed

    def test_dry_run_does_not_write(self):
        path = self.root / check_queue.QUEUE_PATH
        before = path.read_bytes()
        gate = self.queue_gate("--require-ready", "B1")
        completed = self.command("--id", "B1", "--transition", "open",
                                 "--gate-receipt", gate,
                                 "--actor-role", "integrator")
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertEqual(before, path.read_bytes())

    def test_integrator_applies_open_and_syncs_progress_and_receipt(self):
        gate = self.queue_gate("--require-ready", "B1")
        revision, fingerprint = self.expected()
        completed = self.command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T01:00:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual("open", item["state"])
        self.assertEqual("none", item["hold_state"])
        self.assertEqual(gate, item["activation_receipt"])
        self.assertTrue(item["transition_receipts"][-1].startswith(
            "audit-update_queue-"))
        receipt_path = self.root / ".cambium/receipts/queue-transitions.jsonl"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(fingerprint, receipt["before_required_queue_sha256"])
        self.assertEqual(result["queue_sha256"],
                         receipt["after_required_queue_sha256"])

    def test_worker_and_stale_revision_cannot_apply(self):
        gate = self.queue_gate("--require-ready", "B1")
        revision, fingerprint = self.expected()
        worker = self.command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint, "--apply",
        )
        self.assertEqual(1, worker.returncode, worker.stdout)
        stale = self.command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate,
            "--expected-state-revision", "99",
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--apply",
        )
        self.assertEqual(1, stale.returncode, stale.stdout)
        self.assertEqual("queued", self.load(check_queue.QUEUE_PATH)
                         ["required_queue"][0]["state"])

    def test_invalid_timestamp_never_writes_invalid_state(self):
        gate = self.queue_gate("--require-ready", "B1")
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate, "--at", "",
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("RFC 3339", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_merge_ready_cannot_predate_open(self):
        self.open_b1()
        self.append_receipt("audit-page-1", target="Topics/A.md")
        self.append_receipt("audit-batch-1", check="batch_gate")
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T02:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-1\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        revision, fingerprint = self.expected()
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T00:59:59Z", "--apply",
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("time", completed.stdout)
        self.assertEqual(before,
                         (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_confirmation_receipt_is_part_of_ready_gate(self):
        queue = self.load(check_queue.QUEUE_PATH)
        item = queue["required_queue"][0]
        item["confirmation_required"] = True
        item["hold_state"] = "confirmation-required"
        item["hold_reason"] = "user must approve activation"
        self.write_queue(queue)
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["batch_specs"][0]["confirmation_required"] = True
        (self.root / check_queue.COVERAGE_PATH).write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        self.refresh_initial_origin()
        self.append_receipt("confirm-b1", check="confirmation")
        gate = self.queue_gate(
            "--require-ready", "B1", "--confirmation-receipt", "confirm-b1"
        )
        revision, fingerprint = self.expected()
        completed = self.command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate, "--confirmation-receipt", "confirm-b1",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T01:00:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("confirm-b1",
                         result["items_by_id"]["B1"]["confirmation_receipt"])

    def test_direct_cancelled_transition_is_not_exposed_by_cli(self):
        before = {
            relative: (self.root / relative).read_bytes()
            for relative in (check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
                             check_queue.PROGRESS_PATH)
        }
        completed = self.command(
            "--id", "B1", "--transition", "cancelled",
        )
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("invalid choice: 'cancelled'", completed.stdout)
        for relative, content in before.items():
            self.assertEqual(content, (self.root / relative).read_bytes())

    def test_close_projects_coverage_and_receipt_binds_both_fingerprints(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        before_coverage_sha = kblib.sha256_file(coverage_path)
        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        revision, fingerprint = self.expected()
        completed = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T03:00:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        page = result["coverage"]["pages"][0]
        self.assertEqual("B1", page["batch"])
        self.assertIsNone(page["next_batch"])
        receipts = [json.loads(line) for line in
                    (self.root / ".cambium/receipts/queue-transitions.jsonl")
                    .read_text(encoding="utf-8").splitlines()]
        receipt = receipts[-1]
        self.assertEqual(before_coverage_sha,
                         receipt["before_coverage_sha256"])
        self.assertEqual(kblib.sha256_file(coverage_path),
                         receipt["after_coverage_sha256"])

    def test_close_requires_the_exact_delta_apply_receipt(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        gate = self.queue_gate()
        revision, fingerprint = self.expected()
        missing = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, missing.returncode, missing.stdout)
        self.assertIn("requires --delta-apply-receipt", missing.stdout)
        wrong = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--delta-apply-receipt", "audit-not-the-apply-receipt",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, wrong.returncode, wrong.stdout)
        self.assertIn("does not exist", wrong.stdout)
        self.assertNotIn(
            "delta_apply_receipt",
            self.load(check_queue.QUEUE_PATH)["required_queue"][0],
        )

    def test_close_requires_an_independent_batch_close_gate(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("requires --close-gate-receipt", attempted.stdout)
        item = self.load(check_queue.QUEUE_PATH)["required_queue"][0]
        self.assertNotIn("close_gate_receipt", item)

    def test_close_rejects_a_handwritten_aggregator_producer(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate(
            "B1", consistency,
            mutate=lambda receipt: receipt.__setitem__(
                "tool", "handwritten_close_bundle"),
        )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--apply",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("expected 'check_batch_close'", attempted.stdout)

    def test_close_gate_requires_exact_batch_binding(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate(
            "B1", consistency,
            mutate=lambda receipt: receipt.__setitem__("batch_id", "B2"),
        )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("batch_id='B2', expected 'B1'", attempted.stdout)

    def test_close_gate_rejects_stale_post_apply_snapshot(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate(
            "B1", consistency,
            mutate=lambda receipt: receipt.__setitem__(
                "coverage_ledger_sha256", "sha256:" + "0" * 64),
        )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("coverage_ledger_sha256", attempted.stdout)

    def test_close_gate_requires_all_seven_closed_list_members(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()

        def omit_member(receipt):
            receipt["closed_list_evidence"].pop("controlled_vocabulary")

        close_gate = self.close_gate("B1", consistency, mutate=omit_member)
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("closed_list_evidence misses: controlled_vocabulary",
                      attempted.stdout)

    def test_close_gate_rejects_mixed_merged_snapshots(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate(
            "B1", consistency,
            mutate=lambda receipt: receipt.__setitem__(
                "merged_snapshot_sha256", "sha256:" + "9" * 64),
        )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("merged_snapshot_sha256", attempted.stdout)

    def test_close_gate_rejects_content_changed_after_global_checks(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate("B1", consistency)
        topic = self.root / "Topics/A.md"
        topic.write_text(
            topic.read_text(encoding="utf-8") + "\nchanged after gate\n",
            encoding="utf-8",
        )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("does not match the current repository snapshot",
                      attempted.stdout)

    def test_close_gate_rejects_consistently_forged_snapshot(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate("B1", consistency)
        gate_record = next(
            json.loads(line)
            for line in (self.root / ".cambium/receipts/close-gates.jsonl")
            .read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("receipt_id") == close_gate
        )
        forged = "sha256:" + "9" * 64
        self.rewrite_receipt_for_negative_test(
            consistency,
            lambda receipt: receipt.__setitem__(
                "repository_snapshot_sha256", forged),
        )
        for receipt_id in [
                gate_record["global_review_receipt"],
                *gate_record["closed_list_evidence"].values(),
                close_gate]:
            self.rewrite_receipt_for_negative_test(
                receipt_id,
                lambda receipt: receipt.__setitem__(
                    "merged_snapshot_sha256", forged),
            )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("does not match the current repository snapshot",
                      attempted.stdout)

    def test_close_gate_requires_independent_global_review(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate(
            "B1", consistency,
            mutate=lambda receipt: receipt.__setitem__(
                "global_review_receipt", "audit-missing-global-review"),
        )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("global review references missing receipt",
                      attempted.stdout)

    def test_close_gate_rejects_missing_member_receipt(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()

        def replace_member(receipt):
            receipt["closed_list_evidence"]["structural_validity"] = \
                "audit-missing-structure"

        close_gate = self.close_gate("B1", consistency, mutate=replace_member)
        revision, fingerprint = self.expected()
        missing = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, missing.returncode, missing.stdout)
        self.assertIn("references missing receipt audit-missing-structure",
                      missing.stdout)

    def test_close_gate_member_receipts_have_stable_semantics(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate("B1", consistency)
        gate_record = next(
            json.loads(line)
            for line in (self.root / ".cambium/receipts/close-gates.jsonl")
            .read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("receipt_id") == close_gate
        )
        member_id = gate_record["closed_list_evidence"]["structural_validity"]
        self.rewrite_receipt_for_negative_test(
            member_id,
            lambda receipt: receipt.__setitem__("check", "unrelated_check"),
        )
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("check='unrelated_check', expected "
                      "'closed_list_structural_validity'", attempted.stdout)

    def test_close_gate_rejects_invalidated_aggregator(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate(
            "B1", consistency,
            mutate=lambda receipt: receipt.__setitem__(
                "invalidated_by", "audit-superseding-close"),
        )
        revision, fingerprint = self.expected()
        invalidated = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, invalidated.returncode, invalidated.stdout)
        self.assertIn("invalidated_by='audit-superseding-close'",
                      invalidated.stdout)

    def test_close_gate_cannot_be_reused_for_another_batch(self):
        self.merge_b1()
        self.apply_b1()
        consistency = self.queue_gate()
        close_gate = self.close_gate("B1", consistency)
        runtime = check_queue.validate_runtime(self.root)
        delta_apply_receipt = runtime["pending_delta_applies"]["current"][0][
            "selected_receipt"]
        errors = check_queue.close_gate_receipt_errors(
            runtime["receipt_catalog"],
            close_gate,
            item_id="B2",
            task_id="fixture-task",
            queue_revision=self.load(check_queue.QUEUE_PATH)["queue_revision"],
            queue_state_revision=self.load(
                check_queue.QUEUE_PATH)["state_revision"],
            required_queue_sha256=kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
            coverage_ledger_sha256=kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            progress_ledger_sha256=kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            delta_sha256="sha256:" + "f" * 64,
            queue_consistency_receipt=consistency,
            delta_apply_receipt=delta_apply_receipt,
        )
        self.assertTrue(any("expected 'B2'" in error for error in errors), errors)

    def test_merge_ready_freezes_delta_bytes(self):
        self.merge_b1()
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        queue = self.load(check_queue.QUEUE_PATH)
        frozen = queue["required_queue"][0]["delta_sha256"]
        self.assertEqual(frozen, kblib.sha256_file(delta))
        delta.write_text(delta.read_text(encoding="utf-8") + "# replaced\n",
                         encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("do not match frozen delta_sha256" in error
                            for error in result["errors"]), result["errors"])

    def test_merge_ready_rejects_invalid_gap_delta_at_admission(self):
        self.open_b1()
        self.append_receipt("audit-page-1", target="Topics/A.md")
        self.append_receipt("audit-batch-1", check="batch_gate")
        delta_data = {
            "batch": "B1",
            "generated_at": "2026-08-04T02:00:00Z",
            "pages": [{
                "path": "Topics/A.md",
                "gate_receipts": ["audit-page-1"],
            }],
            "open_gaps_added": [{"page": "Topics/A.md"}],
            "open_gaps_closed": [],
            "next_batch_updates": [],
            "watermark_advance": None,
        }
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(kblib.canonical_yaml(delta_data), encoding="utf-8")
        revision, fingerprint = self.expected()
        attempted = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("open_gaps_added[0] type", attempted.stdout)
        self.assertEqual("open", self.load(check_queue.QUEUE_PATH)
                         ["required_queue"][0]["state"])

    def test_batch_receipt_must_be_batch_gate_for_exact_batch(self):
        self.open_b1()
        self.append_receipt("audit-page-only", target="Topics/A.md")
        self.append_receipt("audit-confirmation-only", check="confirmation")
        self.append_receipt("audit-wrong-batch", check="batch_gate", target="B2")
        receipt_path = self.root / ".cambium/receipts/invalid-batch.jsonl"
        kblib.write_receipts(receipt_path, [{
            "receipt_id": "audit-invalidated-batch", "check": "batch_gate",
            "target": "B1", "result": "pass",
            "invalidated_by": "audit-revocation",
        }, {
            "receipt_id": "audit-revocation", "check": "revocation",
            "target": "audit-invalidated-batch", "result": "pass",
            "invalidated_by": None,
        }])
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T02:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-only\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        cases = (
            ("audit-page-only", "expected 'batch_gate'"),
            ("audit-confirmation-only", "expected 'batch_gate'"),
            ("audit-wrong-batch", "expected 'B1'"),
            ("audit-invalidated-batch", "invalidated_by='audit-revocation'"),
        )
        for receipt_id, expected in cases:
            with self.subTest(receipt_id=receipt_id):
                attempted = self.command(
                    "--id", "B1", "--transition", "merge-ready",
                    "--delta-path", ".cambium/deltas/B1.yaml",
                    "--batch-receipt", receipt_id,
                )
                self.assertEqual(1, attempted.returncode, attempted.stdout)
                self.assertIn(expected, attempted.stdout)
        self.assertEqual("open", self.load(check_queue.QUEUE_PATH)
                         ["required_queue"][0]["state"])

    def test_persistent_state_rejects_unrelated_current_and_historical_batch_receipts(self):
        self.merge_b1()
        queue = self.load(check_queue.QUEUE_PATH)
        queue["required_queue"][0]["batch_receipts"] = ["audit-page-1"]
        self.write_queue(queue)
        current_errors = "\n".join(
            check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("batch evidence receipt audit-page-1 has check='fixture', "
                      "expected 'batch_gate'", current_errors)

        # Restore the valid materialized state, then create one append-only
        # invalidation and tamper only its frozen batch-evidence list.
        queue["required_queue"][0]["batch_receipts"] = ["audit-batch-1"]
        self.write_queue(queue)
        revision, fingerprint = self.expected()
        rolled_back = self.command(
            "--id", "B1", "--transition", "open",
            "--reason", "global validation failed",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, rolled_back.returncode, rolled_back.stdout)
        queue = self.load(check_queue.QUEUE_PATH)
        queue["required_queue"][0]["invalidation_history"][0][
            "batch_receipts"] = ["audit-page-1"]
        self.write_queue(queue)
        historical_errors = "\n".join(
            check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("invalidation_history[0] batch evidence receipt "
                      "audit-page-1 has check='fixture', expected 'batch_gate'",
                      historical_errors)

    def test_receipt_failure_restores_state_and_receipt_bytes(self):
        self.make_task_active_without_open()
        gate = self.queue_gate("--require-ready", "B1")
        revision, fingerprint = self.expected()
        tracked = {
            path: (self.root / path).read_bytes()
            for path in (check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
                         check_queue.PROGRESS_PATH)
        }
        with mock.patch.object(
                update_queue.kblib, "write_receipts",
                side_effect=OSError("injected receipt failure")):
            with redirect_stdout(io.StringIO()):
                exit_code = update_queue.main([
                    str(self.root), "--id", "B1", "--transition", "open",
                    "--gate-receipt", gate,
                    "--expected-state-revision", revision,
                    "--expected-sha256", fingerprint,
                    "--actor-role", "integrator", "--apply",
                ])
        self.assertEqual(1, exit_code)
        for path, before in tracked.items():
            self.assertEqual(before, (self.root / path).read_bytes())
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())
        self.assertFalse((self.root /
                          ".cambium/receipts/queue-transitions.jsonl").exists())

    def test_receipt_failure_does_not_clobber_concurrent_external_append(self):
        self.make_task_active_without_open()
        gate = self.queue_gate("--require-ready", "B1")
        revision, fingerprint = self.expected()
        tracked = {
            path: (self.root / path).read_bytes()
            for path in (check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
                         check_queue.PROGRESS_PATH)
        }
        external = {
            "receipt_id": "audit-external-concurrent",
            "check": "external",
            "target": "unrelated",
            "result": "pass",
            "invalidated_by": None,
        }
        real_append = kblib.write_receipts

        def external_then_fail(path, receipts, **kwargs):
            real_append(path, [external])
            raise OSError("injected failure after external append")

        with mock.patch.object(update_queue.kblib, "write_receipts",
                               side_effect=external_then_fail):
            with redirect_stdout(io.StringIO()):
                exit_code = update_queue.main([
                    str(self.root), "--id", "B1", "--transition", "open",
                    "--gate-receipt", gate,
                    "--expected-state-revision", revision,
                    "--expected-sha256", fingerprint,
                    "--actor-role", "integrator", "--apply",
                ])

        self.assertEqual(1, exit_code)
        for path, before in tracked.items():
            self.assertEqual(before, (self.root / path).read_bytes())
        receipt_path = (self.root /
                        ".cambium/receipts/queue-transitions.jsonl")
        self.assertEqual(
            [external],
            [json.loads(line) for line in
             receipt_path.read_text(encoding="utf-8").splitlines()],
        )
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists()
        )

    def test_failure_after_own_receipt_append_preserves_log_and_lock(self):
        self.make_task_active_without_open()
        gate = self.queue_gate("--require-ready", "B1")
        revision, fingerprint = self.expected()
        tracked = {
            path: (self.root / path).read_bytes()
            for path in (check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
                         check_queue.PROGRESS_PATH)
        }
        external = {
            "receipt_id": "audit-external-after-own",
            "check": "external",
            "target": "unrelated",
            "result": "pass",
            "invalidated_by": None,
        }
        own = {}
        real_append = kblib.write_receipts

        def own_and_external_then_fail(path, receipts, **kwargs):
            own.update(receipts[0])
            real_append(path, receipts, **kwargs)
            real_append(path, [external])
            raise OSError("injected failure after durable own append")

        with mock.patch.object(update_queue.kblib, "write_receipts",
                               side_effect=own_and_external_then_fail):
            with redirect_stdout(io.StringIO()):
                exit_code = update_queue.main([
                    str(self.root), "--id", "B1", "--transition", "open",
                    "--gate-receipt", gate,
                    "--expected-state-revision", revision,
                    "--expected-sha256", fingerprint,
                    "--actor-role", "integrator", "--apply",
                ])

        self.assertEqual(1, exit_code)
        for path, before in tracked.items():
            self.assertEqual(before, (self.root / path).read_bytes())
        records = [
            json.loads(line) for line in
            (self.root / ".cambium/receipts/queue-transitions.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
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

    def test_incomplete_rollback_preserves_recovery_lock(self):
        gate = self.queue_gate("--require-ready", "B1")
        revision, fingerprint = self.expected()
        real_write_state = update_queue._write_state
        calls = {"count": 0}

        def fail_restore(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return real_write_state(*args, **kwargs)
            raise OSError("injected rollback failure")

        with mock.patch.object(update_queue, "_write_state",
                               side_effect=fail_restore), \
                mock.patch.object(
                    update_queue.kblib, "write_receipts",
                    side_effect=OSError("injected receipt failure")):
            with redirect_stdout(io.StringIO()):
                exit_code = update_queue.main([
                    str(self.root), "--id", "B1", "--transition", "open",
                    "--gate-receipt", gate,
                    "--expected-state-revision", revision,
                    "--expected-sha256", fingerprint,
                    "--actor-role", "integrator", "--apply",
                ])
        self.assertEqual(1, exit_code)
        lock = self.root / ".cambium/tmp/state-writer.lock/owner.json"
        self.assertTrue(lock.is_file())
        owner = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual("update_queue", owner["operation"]["tool"])

    def test_close_lock_owner_binds_coverage_before_and_after(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        before_coverage_sha = kblib.sha256_file(coverage_path)
        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        revision, fingerprint = self.expected()
        captured = {}
        real_lock = update_queue.kblib.runtime_write_lock

        @contextmanager
        def capturing_lock(root, **kwargs):
            captured.update(kwargs.get("owner_metadata") or {})
            with real_lock(root, **kwargs) as lock_path:
                yield lock_path

        with mock.patch.object(update_queue.kblib, "runtime_write_lock",
                               new=capturing_lock):
            with redirect_stdout(io.StringIO()):
                exit_code = update_queue.main([
                    str(self.root), "--id", "B1", "--transition", "closed",
                    "--gate-receipt", gate,
                    "--close-gate-receipt", close_gate,
                    "--delta-apply-receipt", delta_apply_receipt,
                    "--expected-state-revision", revision,
                    "--expected-sha256", fingerprint,
                    "--actor-role", "integrator",
                    "--at", "2026-08-04T03:00:00Z", "--apply",
                ])
        self.assertEqual(0, exit_code)
        self.assertEqual(before_coverage_sha,
                         captured["before_coverage_sha256"])
        self.assertEqual(kblib.sha256_file(coverage_path),
                         captured["planned_after_coverage_sha256"])

    def test_close_preserves_one_explicit_queued_successor_route(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = self.load(check_queue.COVERAGE_PATH)
        page = coverage["pages"][0]
        queue = self.load(check_queue.QUEUE_PATH)
        queue["required_queue"].append({
            "id": "B3", "family": "Core", "order": 3,
            "record_count": 1, "manifest": ["Topics/A.md"],
            "source_route": "R03", "execution_mode": "concurrent-worker",
            "depends_on": ["B1"], "confirmation_required": False,
            "state": "queued", "hold_state": "none", "successor_of": "B1",
        })
        coverage["batch_specs"].append({
            "id": "B3", "family": "Core", "order_hint": 3,
            "source_route": "R03", "execution_mode": "concurrent-worker",
            "depends_on": ["B1"], "confirmation_required": False,
        })
        # The exact Coverage/Queue relation records the queued successor before
        # lifecycle close; close preserves that declared route rather than
        # manufacturing a new assignment.
        page["next_batch"] = "B3"
        coverage_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        self.write_queue(queue)
        self.refresh_initial_origin()
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        self.close_b1()
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        page = result["coverage"]["pages"][0]
        self.assertEqual("B1", page["batch"])
        self.assertEqual("B3", page["next_batch"])

    def test_close_rejects_multiple_queued_successors(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        queue = self.load(check_queue.QUEUE_PATH)
        for order, item_id in ((3, "B3"), (4, "B4")):
            queue["required_queue"].append({
                "id": item_id, "family": "Core", "order": order,
                "record_count": 1, "manifest": ["Topics/A.md"],
                "source_route": "R03",
                "execution_mode": "concurrent-worker",
                "depends_on": ["B1"], "confirmation_required": False,
                "state": "queued", "hold_state": "none",
                "successor_of": "B1",
            })
        with self.assertRaisesRegex(ValueError, "multiple queued successors"):
            update_queue._project_closed_coverage(coverage, queue, "B1")

    def test_receipt_path_cannot_overwrite_authoritative_state(self):
        queue_path = self.root / check_queue.QUEUE_PATH
        before = queue_path.read_bytes()
        gate = self.queue_gate("--require-ready", "B1")
        completed = self.command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", gate,
            "--receipts", ".cambium/state/required_queue.yaml",
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual(before, queue_path.read_bytes())

    def test_closed_item_rejects_hold_only_mutation(self):
        self.close_b1()
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        completed = self.command("--id", "B1", "--hold-state", "paused",
                                 "--reason", "do not mutate history")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("immutable", completed.stdout)

    def test_held_open_cannot_skip_revalidation_to_merge_ready(self):
        self.open_b1()
        revision, fingerprint = self.expected()
        held = self.command(
            "--id", "B1", "--hold-state", "revalidation-required",
            "--reason", "receipt invalidated",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T01:30:00Z",
            "--apply",
        )
        self.assertEqual(0, held.returncode, held.stdout)
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text("batch: B1\npages: []\n", encoding="utf-8")
        completed = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("held open batch", completed.stdout)

    def test_hold_noop_does_not_bump_state_revision(self):
        self.make_task_active_without_open()
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.command(
            "--id", "B1", "--hold-state", "none"
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("no-op", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_merge_ready_rejects_wrong_delta_path_and_batch_binding(self):
        self.open_b1()
        self.append_receipt("audit-batch-1", check="batch_gate")
        delta_dir = self.root / ".cambium/deltas"
        delta_dir.mkdir(parents=True, exist_ok=True)
        (delta_dir / "other.yaml").write_text("batch: B1\npages: []\n",
                                               encoding="utf-8")
        wrong_path = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/other.yaml",
            "--batch-receipt", "audit-batch-1",
        )
        self.assertEqual(1, wrong_path.returncode, wrong_path.stdout)
        self.assertIn("exactly .cambium/deltas/B1.yaml", wrong_path.stdout)
        (delta_dir / "other.yaml").unlink()
        (delta_dir / "B1.yaml").write_text("batch: B2\npages: []\n",
                                            encoding="utf-8")
        wrong_batch = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
        )
        self.assertEqual(1, wrong_batch.returncode, wrong_batch.stdout)
        self.assertTrue("batch" in wrong_batch.stdout and
                        ("B1" in wrong_batch.stdout or "B2" in wrong_batch.stdout),
                        wrong_batch.stdout)

    def test_merge_ready_rejects_delta_outside_frozen_manifest(self):
        self.open_b1()
        self.append_receipt("audit-page-outside", target="Topics/B.md")
        self.append_receipt("audit-batch-1", check="batch_gate")
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\npages:\n  - path: Topics/B.md\n"
            "    gate_receipts:\n      - audit-page-outside\n",
            encoding="utf-8",
        )
        completed = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("frozen manifest", completed.stdout)

    def test_resume_admits_complete_open_delta_handoff(self):
        self.open_b1()
        self.append_receipt("audit-page-handoff", target="Topics/A.md")
        self.append_receipt("audit-batch-handoff", check="batch_gate")
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T02:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-handoff\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        resume = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status", "--receipts",
             ".cambium/receipts/resume-handoff.jsonl"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, resume.returncode, resume.stdout)
        self.assertIn("handoff_status=candidate", resume.stdout)
        self.assertIn("next_action=admit-delta:B1", resume.stdout)
        self.assert_resume_envelope(resume, "admit-delta:B1")
        resume_receipt = json.loads((
            self.root / ".cambium/receipts/resume-handoff.jsonl"
        ).read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("admit-delta:B1", resume_receipt["next_action"])

        revision, fingerprint = self.expected()
        admitted = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-handoff",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T02:00:00Z", "--apply",
        )
        self.assertEqual(0, admitted.returncode, admitted.stdout)
        self.assertEqual("merge-ready", self.load(
            check_queue.QUEUE_PATH)["required_queue"][0]["state"])

    def test_resume_rejects_incomplete_open_delta_handoff(self):
        self.open_b1()
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T02:00:00Z\n"
            "pages: []\nopen_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        resume = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, resume.returncode, resume.stdout)
        self.assertIn("handoff_status=invalid", resume.stdout)
        self.assertIn("pages must equal the frozen manifest exactly",
                      resume.stdout)
        self.assertIn("next_action=repair-runtime", resume.stdout)
        self.assert_resume_envelope(resume, "repair-runtime")

    def test_resume_derives_apply_then_deterministic_close_receipt(self):
        self.merge_b1()
        before_apply = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, before_apply.returncode, before_apply.stdout)
        self.assertIn("next_action=apply-delta:B1", before_apply.stdout)
        self.assert_resume_envelope(before_apply, "apply-delta:B1")

        original_id = self.apply_b1()
        original_path = self.root / ".cambium/receipts/delta-B1.jsonl"
        original = json.loads(original_path.read_text(
            encoding="utf-8").splitlines()[-1])
        duplicate_id = "audit-apply_delta-0000-compatible"
        duplicate_path = ".cambium/receipts/delta-B1-compatible.jsonl"
        duplicate = dict(original)
        duplicate["receipt_id"] = duplicate_id
        duplicate["receipt_path"] = duplicate_path
        kblib.write_receipts(self.root / duplicate_path, [duplicate])

        after_apply = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status", "--receipts",
             ".cambium/receipts/resume-applied.jsonl"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, after_apply.returncode, after_apply.stdout)
        compatible = ",".join(sorted((duplicate_id, original_id)))
        self.assertIn("selected_receipt=%s" % duplicate_id,
                      after_apply.stdout)
        self.assertIn("compatible_receipts=%s" % compatible,
                      after_apply.stdout)
        self.assertIn("batch_close_recovery.status=gate-required batch=B1",
                      after_apply.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      after_apply.stdout)
        self.assert_resume_envelope(after_apply,
                                    "run-batch-close-gate:B1")
        resume_receipt = json.loads((
            self.root / ".cambium/receipts/resume-applied.jsonl"
        ).read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("run-batch-close-gate:B1",
                         resume_receipt["next_action"])

        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        after_gate = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        recovered_action = "close-applied-batch:B1:%s:%s:%s" % (
            gate, close_gate, duplicate_id)
        self.assertEqual(2, after_gate.returncode, after_gate.stdout)
        self.assertIn("batch_close_recovery.status=ready-to-close batch=B1",
                      after_gate.stdout)
        self.assertIn("next_action=%s" % recovered_action,
                      after_gate.stdout)
        self.assert_resume_envelope(after_gate, recovered_action)
        revision, fingerprint = self.expected()
        closed = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", duplicate_id,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, closed.returncode, closed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(duplicate_id,
                         result["items_by_id"]["B1"]["delta_apply_receipt"])

    def test_applied_delta_blocks_all_state_writers_until_exact_close(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        state_paths = (
            check_queue.COVERAGE_PATH,
            check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH,
            ".cambium/deltas/B1.yaml",
        )
        before = {path: (self.root / path).read_bytes()
                  for path in state_paths}
        revision, queue_sha = self.expected()
        coverage_sha = kblib.sha256_file(
            self.root / check_queue.COVERAGE_PATH)
        progress_sha = kblib.sha256_file(
            self.root / check_queue.PROGRESS_PATH)

        attempts = [
            subprocess.run(
                [sys.executable, str(TOOLS / "apply_delta.py"),
                 check_queue.COVERAGE_PATH, ".cambium/deltas/B1.yaml",
                 "--root", str(self.root),
                 "--expected-coverage-sha256", coverage_sha,
                 "--expected-queue-sha256", queue_sha,
                 "--actor-role", "integrator", "--apply"],
                text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False),
            self.command(
                "--id", "B2", "--transition", "open",
                "--expected-state-revision", revision,
                "--expected-sha256", queue_sha,
                "--actor-role", "integrator", "--apply"),
            subprocess.run(
                [sys.executable, str(TOOLS / "compile_queue.py"),
                 str(self.root), "--apply-replan",
                 "--actor-role", "integrator"],
                text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False),
            subprocess.run(
                [sys.executable, str(TOOLS / "apply_amendment.py"),
                 str(self.root), "--plan",
                 ".cambium/deltas/amendments/not-loaded.yaml",
                 "--expected-coverage-sha256", coverage_sha,
                 "--expected-progress-sha256", progress_sha,
                 "--expected-queue-sha256", queue_sha,
                 "--actor-role", "integrator", "--apply"],
                text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False),
        ]
        for attempted in attempts:
            self.assertEqual(1, attempted.returncode, attempted.stdout)
            self.assertIn("the only allowed Queue/Coverage write is "
                          "update_queue merge-ready->closed",
                          attempted.stdout)
            self.assertIn(delta_apply_receipt, attempted.stdout)
        for path, content in before.items():
            self.assertEqual(content, (self.root / path).read_bytes(), path)

        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        revision, queue_sha = self.expected()
        closed = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, closed.returncode, closed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("closed", result["items_by_id"]["B1"]["state"])
        self.assertEqual("clear", result["pending_delta_applies"]["status"])

    def test_cancelled_task_closes_an_already_applied_batch_before_archive(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()
        cancelled = subprocess.run(
            [sys.executable, str(TOOLS / "update_task.py"), str(self.root),
             "--transition", "cancelled", "--checkpoint-summary",
             "operator cancelled after delta application",
             "--expected-progress-sha256",
             kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
             "--expected-queue-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--at",
             "2026-08-04T02:30:00Z", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, cancelled.returncode, cancelled.stdout)
        resumed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, resumed.returncode, resumed.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      resumed.stdout)
        self.assertIn("before any Queue close, control input, another batch, "
                      "or terminal archival", resumed.stdout)

        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        revision, queue_sha = self.expected()
        closed = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, closed.returncode, closed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("cancelled", result["progress"]["task_state"])
        self.assertEqual("closed", result["items_by_id"]["B1"]["state"])

    def test_paused_task_resumes_before_closing_an_applied_batch(self):
        self.merge_b1()
        delta_apply_receipt = self.apply_b1()

        def transition_task(state, summary, at):
            return subprocess.run(
                [sys.executable, str(TOOLS / "update_task.py"),
                 str(self.root), "--transition", state,
                 "--checkpoint-summary", summary,
                 "--expected-progress-sha256",
                 kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
                 "--expected-queue-sha256",
                 kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
                 "--actor-role", "integrator", "--at", at, "--apply"],
                text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False,
            )

        paused = transition_task(
            "paused", "operator interruption after apply",
            "2026-08-04T02:30:00Z")
        self.assertEqual(0, paused.returncode, paused.stdout)
        resumed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("next_action=resume-paused-task", resumed.stdout)
        self.assertIn("then rerun resume-status and close applied batch B1",
                      resumed.stdout)
        self.assert_resume_envelope(resumed, "resume-paused-task")
        active = transition_task(
            "active", "operator resumed to close applied batch",
            "2026-08-04T02:45:00Z")
        self.assertEqual(0, active.returncode, active.stdout)
        close_status = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, close_status.returncode, close_status.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      close_status.stdout)
        self.assert_resume_envelope(close_status,
                                    "run-batch-close-gate:B1")
        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        revision, queue_sha = self.expected()
        closed = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, closed.returncode, closed.stdout)

    def test_two_merge_ready_batches_apply_and_close_in_serial_critical_sections(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        next(spec for spec in coverage["batch_specs"]
             if spec["id"] == "B2")["depends_on"] = []
        (self.root / check_queue.COVERAGE_PATH).write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        queue = self.load(check_queue.QUEUE_PATH)
        next(item for item in queue["required_queue"]
             if item["id"] == "B2")["depends_on"] = []
        self.write_queue(queue)
        self.refresh_initial_origin()
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

        self.open_b1()
        ready_b2 = self.queue_gate("--require-ready", "B2")
        revision, queue_sha = self.expected()
        opened_b2 = self.command(
            "--id", "B2", "--transition", "open",
            "--gate-receipt", ready_b2,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T01:05:00Z", "--apply",
        )
        self.assertEqual(0, opened_b2.returncode, opened_b2.stdout)

        for batch, page, minute in (("B1", "Topics/A.md", "00"),
                                    ("B2", "Topics/B.md", "05")):
            page_receipt = "audit-page-%s" % batch.lower()
            batch_receipt = "audit-batch-%s" % batch.lower()
            self.append_receipt(page_receipt, target=page)
            self.append_receipt(batch_receipt, check="batch_gate",
                                target=batch)
            delta = self.root / (".cambium/deltas/%s.yaml" % batch)
            delta.parent.mkdir(parents=True, exist_ok=True)
            delta.write_text(kblib.canonical_yaml({
                "batch": batch,
                "generated_at": "2026-08-04T02:%s:00Z" % minute,
                "pages": [{"path": page,
                           "gate_receipts": [page_receipt]}],
                "open_gaps_added": [{
                    "page": page, "type": "rereview",
                    "note": "non-idempotent gap from %s" % batch,
                }],
                "open_gaps_closed": [],
                "next_batch_updates": [],
                "watermark_advance": None,
            }), encoding="utf-8")
            revision, queue_sha = self.expected()
            merged = self.command(
                "--id", batch, "--transition", "merge-ready",
                "--delta-path", ".cambium/deltas/%s.yaml" % batch,
                "--batch-receipt", batch_receipt,
                "--expected-state-revision", revision,
                "--expected-sha256", queue_sha,
                "--actor-role", "integrator", "--at",
                "2026-08-04T02:%s:00Z" % minute, "--apply",
            )
            self.assertEqual(0, merged.returncode, merged.stdout)

        b1_receipt = self.apply_batch("B1")
        coverage_after_b1 = (self.root / check_queue.COVERAGE_PATH).read_bytes()
        queue_after_b1 = (self.root / check_queue.QUEUE_PATH).read_bytes()
        blocked_b2 = subprocess.run(
            [sys.executable, str(TOOLS / "apply_delta.py"),
             check_queue.COVERAGE_PATH, ".cambium/deltas/B2.yaml",
             "--root", str(self.root),
             "--expected-coverage-sha256",
             kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
             "--expected-queue-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, blocked_b2.returncode, blocked_b2.stdout)
        self.assertIn("merge-ready->closed", blocked_b2.stdout)
        self.assertEqual(coverage_after_b1,
                         (self.root / check_queue.COVERAGE_PATH).read_bytes())
        self.assertEqual(queue_after_b1,
                         (self.root / check_queue.QUEUE_PATH).read_bytes())
        self.assertEqual(["Topics/A.md"], [
            gap["page"] for gap in self.load(
                check_queue.COVERAGE_PATH)["open_gaps"]])

        resumed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      resumed.stdout)
        gate = self.queue_gate()
        close_gate = self.close_gate("B1", gate)
        revision, queue_sha = self.expected()
        closed_b1 = self.command(
            "--id", "B1", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", b1_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, closed_b1.returncode, closed_b1.stdout)

        b2_receipt = self.apply_batch("B2")
        gate = self.queue_gate()
        close_gate = self.close_gate("B2", gate)
        revision, queue_sha = self.expected()
        closed_b2 = self.command(
            "--id", "B2", "--transition", "closed",
            "--gate-receipt", gate,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", b2_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:05:00Z", "--apply",
        )
        self.assertEqual(0, closed_b2.returncode, closed_b2.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(["closed", "closed"], [
            result["items_by_id"][batch]["state"]
            for batch in ("B1", "B2")])
        self.assertEqual(["Topics/A.md", "Topics/B.md"], [
            gap["page"] for gap in result["coverage"]["open_gaps"]])

    def test_stale_unconsumed_delta_apply_receipt_forces_repair(self):
        self.merge_b1()
        self.apply_b1()
        original_path = self.root / ".cambium/receipts/delta-B1.jsonl"
        stale = json.loads(original_path.read_text(
            encoding="utf-8").splitlines()[-1])
        stale["receipt_id"] = "audit-apply_delta-stale-binding"
        stale["receipt_path"] = ".cambium/receipts/delta-B1-stale.jsonl"
        stale["required_queue_sha256"] = "sha256:" + "0" * 64
        kblib.write_receipts(self.root / stale["receipt_path"], [stale])

        result = check_queue.validate_runtime(self.root)
        self.assertEqual("repair", result["pending_delta_applies"]["status"])
        errors = "\n".join(result["errors"])
        self.assertIn("stale unconsumed delta_apply receipt", errors)
        self.assertIn("required_queue_sha256", errors)
        resumed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, resumed.returncode, resumed.stdout)
        self.assertIn("pending_delta_applies.status=repair", resumed.stdout)
        self.assertIn("next_action=repair-runtime", resumed.stdout)

    def test_old_attempt_apply_receipt_does_not_poison_revalidated_delta(self):
        self.merge_b1()
        old_delta_sha = kblib.sha256_file(
            self.root / ".cambium/deltas/B1.yaml")
        old_queue = self.load(check_queue.QUEUE_PATH)
        old_receipt_path = ".cambium/receipts/delta-B1-old-attempt.jsonl"
        old_receipt = {
            "receipt_id": "audit-apply_delta-old-attempt",
            "tool": "apply_delta",
            "tool_version": "1.4.0",
            "check": "delta_apply",
            "target": "B1",
            "batch_id": "B1",
            "task_id": old_queue["task_id"],
            "actor_role": "integrator",
            "result": "pass",
            "invalidated_by": None,
            "coverage_ledger_path": check_queue.COVERAGE_PATH,
            "delta_path": ".cambium/deltas/B1.yaml",
            "delta_sha256": old_delta_sha,
            "before_coverage_sha256": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "after_coverage_sha256": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "required_queue_sha256": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
            "queue_revision": old_queue["queue_revision"],
            "queue_state_revision": old_queue["state_revision"],
            "receipt_path": old_receipt_path,
        }

        revision, queue_sha = self.expected()
        rolled_back = self.command(
            "--id", "B1", "--transition", "open",
            "--reason", "first delta failed global validation",
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, rolled_back.returncode, rolled_back.stdout)
        invalidation = self.load(check_queue.QUEUE_PATH)[
            "required_queue"][0]["invalidation_history"][0]
        self.assertEqual(old_delta_sha, invalidation["delta_sha256"])

        revalidation_gate = self.queue_gate()
        revision, queue_sha = self.expected()
        cleared = self.command(
            "--id", "B1", "--hold-state", "none",
            "--gate-receipt", revalidation_gate,
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T04:00:00Z", "--apply",
        )
        self.assertEqual(0, cleared.returncode, cleared.stdout)

        self.append_receipt("audit-page-new-attempt", target="Topics/A.md")
        self.append_receipt("audit-batch-new-attempt", check="batch_gate")
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T05:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-new-attempt\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        self.assertNotEqual(old_delta_sha, kblib.sha256_file(delta))
        revision, queue_sha = self.expected()
        merged = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-new-attempt",
            "--expected-state-revision", revision,
            "--expected-sha256", queue_sha,
            "--actor-role", "integrator", "--at",
            "2026-08-04T05:00:00Z", "--apply",
        )
        self.assertEqual(0, merged.returncode, merged.stdout)
        kblib.write_receipts(self.root / old_receipt_path, [old_receipt])

        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("clear", result["pending_delta_applies"]["status"])
        self.assertEqual([], result["pending_delta_applies"]["stale"])
        resumed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("next_action=apply-delta:B1", resumed.stdout)
        current_receipt = self.apply_b1()
        current = check_queue.validate_runtime(self.root)
        self.assertEqual([], current["errors"])
        self.assertEqual("close-required",
                         current["pending_delta_applies"]["status"])
        self.assertEqual(current_receipt,
                         current["pending_delta_applies"]["current"][0]
                         ["selected_receipt"])

    def test_merge_failure_returns_to_open_and_archives_invalidated_delta(self):
        self.merge_b1()
        delta = self.root / ".cambium/deltas/B1.yaml"
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        revision, fingerprint = self.expected()
        completed = self.command(
            "--id", "B1", "--transition", "open",
            "--reason", "global validation failed",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T03:00:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual("open", item["state"])
        self.assertEqual("revalidation-required", item["hold_state"])
        self.assertFalse(delta.exists())
        self.assertEqual(1, len(item["invalidation_history"]))
        invalidation = item["invalidation_history"][0]
        archive = self.root / invalidation["delta_archive_path"]
        self.assertTrue(archive.is_file())
        self.assertEqual(kblib.sha256_file(archive),
                         invalidation["delta_sha256"])
        transition = result["receipt_catalog"][
            invalidation["transition_receipt"]][1]
        self.assertEqual(invalidation, transition["invalidation"])

    def test_invalidated_delta_and_receipts_cannot_be_replayed(self):
        self.merge_b1()
        revision, fingerprint = self.expected()
        rolled_back = self.command(
            "--id", "B1", "--transition", "open",
            "--reason", "global validation failed",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        )
        self.assertEqual(0, rolled_back.returncode, rolled_back.stdout)
        invalidation = check_queue.validate_runtime(self.root)[
            "items_by_id"]["B1"]["invalidation_history"][0]
        self.assertEqual(["audit-batch-1"], invalidation["batch_receipts"])
        self.assertEqual(["audit-page-1"],
                         invalidation["delta_gate_receipts"])
        self.assertEqual([], invalidation["revalidation_receipts"])

        revalidation_gate = self.queue_gate()
        revision, fingerprint = self.expected()
        cleared = self.command(
            "--id", "B1", "--hold-state", "none",
            "--gate-receipt", revalidation_gate,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T04:00:00Z", "--apply",
        )
        self.assertEqual(0, cleared.returncode, cleared.stdout)

        delta = self.root / ".cambium/deltas/B1.yaml"
        shutil.copy2(self.root / invalidation["delta_archive_path"], delta)
        revision, fingerprint = self.expected()
        replayed = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T05:00:00Z", "--apply",
        )
        self.assertEqual(1, replayed.returncode, replayed.stdout)
        self.assertIn("reuses invalidated receipt(s)", replayed.stdout)
        self.assertIn("audit-batch-1", replayed.stdout)
        self.assertIn("audit-page-1", replayed.stdout)

        self.append_receipt("audit-page-fresh", target="Topics/A.md")
        self.append_receipt("audit-batch-fresh", check="batch_gate")
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T06:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-fresh\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        revision, fingerprint = self.expected()
        fresh = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-fresh",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T06:00:00Z", "--apply",
        )
        self.assertEqual(0, fresh.returncode, fresh.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(["audit-batch-fresh"],
                         result["items_by_id"]["B1"]["batch_receipts"])

        # The persistent validator independently rejects the same replay even
        # if a non-cooperating writer bypasses update_queue.
        shutil.copy2(self.root / invalidation["delta_archive_path"], delta)
        queue = result["queue"]
        current = next(entry for entry in queue["required_queue"]
                       if entry["id"] == "B1")
        current["delta_sha256"] = invalidation["delta_sha256"]
        current["batch_receipts"] = ["audit-batch-1"]
        self.write_queue(queue)
        replay_errors = "\n".join(
            check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("current batch_receipts reuse invalidated ID(s): "
                      "audit-batch-1", replay_errors)
        self.assertIn("current delta gate_receipts reuse invalidated ID(s): "
                      "audit-page-1", replay_errors)

    def test_hard_exit_after_delta_move_exposes_exact_archive_recovery(self):
        self.merge_b1()
        source = self.root / ".cambium/deltas/B1.yaml"
        queue_path = self.root / check_queue.QUEUE_PATH
        coverage_path = self.root / check_queue.COVERAGE_PATH
        progress_path = self.root / check_queue.PROGRESS_PATH
        before_queue_sha = kblib.sha256_file(queue_path)
        before_coverage_sha = kblib.sha256_file(coverage_path)
        before_progress_sha = kblib.sha256_file(progress_path)
        delta_sha = kblib.sha256_file(source)
        revision, fingerprint = self.expected()
        archive_relative = (
            ".cambium/receipts/invalidated-deltas/B1-r%d.yaml" %
            (int(revision) + 1)
        )
        archive = self.root / archive_relative
        arguments = [
            str(self.root), "--id", "B1", "--transition", "open",
            "--reason", "global validation failed",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at",
            "2026-08-04T03:00:00Z", "--apply",
        ]
        program = """
import os
import sys

sys.path.insert(0, sys.argv[1])
import update_queue

root = os.path.realpath(sys.argv[2])
source = os.path.realpath(os.path.join(
    root, ".cambium/deltas/B1.yaml"
))
archive = os.path.realpath(os.path.join(
    root, sys.argv[3]
))
real_replace = update_queue.os.replace

def move_then_crash(src, dst):
    result = real_replace(src, dst)
    if os.path.realpath(src) == source and os.path.realpath(dst) == archive:
        os._exit(23)
    return result

update_queue.os.replace = move_then_crash
raise SystemExit(update_queue.main(sys.argv[4:]))
"""
        child = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS), str(self.root),
             archive_relative, *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, child.returncode, child.stdout)

        self.assertFalse(source.exists())
        self.assertTrue(archive.is_file())
        self.assertEqual(delta_sha, kblib.sha256_file(archive))
        self.assertEqual(before_queue_sha, kblib.sha256_file(queue_path))
        self.assertEqual(before_coverage_sha, kblib.sha256_file(coverage_path))
        self.assertEqual(before_progress_sha, kblib.sha256_file(progress_path))

        owner = json.loads((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).read_text(encoding="utf-8"))["operation"]
        self.assertEqual(".cambium/deltas/B1.yaml",
                         owner["delta_archive_source"])
        self.assertEqual(archive_relative, owner["delta_archive_path"])
        self.assertEqual(delta_sha, owner["delta_sha256"])

        resume = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertIn(resume.returncode, (1, 2), resume.stdout)
        self.assertIn("state.coverage phase=before", resume.stdout)
        self.assertIn("state.queue phase=before", resume.stdout)
        self.assertIn("state.progress phase=before", resume.stdout)
        self.assertIn("delta_archive status=archived", resume.stdout)
        self.assertIn("recovery_fact=archive-moved-state-before", resume.stdout)
        self.assertIn("restore the archive to its declared source",
                      resume.stdout)

        archive.write_bytes(archive.read_bytes() + b"# altered after crash\n")
        mismatched = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertIn("delta_archive status=archive-sha-mismatch",
                      mismatched.stdout)
        self.assertIn("recovery_fact=archive-state-conflict",
                      mismatched.stdout)

    def test_archive_directory_fsync_failure_rolls_move_back_durably(self):
        self.merge_b1()
        revision, fingerprint = self.expected()
        source = self.root / ".cambium/deltas/B1.yaml"
        archive = self.root / (
            ".cambium/receipts/invalidated-deltas/B1-r%d.yaml" %
            (int(revision) + 1)
        )
        state_paths = (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH,
        )
        before = {path: (self.root / path).read_bytes()
                  for path in state_paths}
        real_replace = update_queue.kblib.durable_replace
        calls = {"count": 0}

        def fail_after_forward_move(source_path, archive_path):
            calls["count"] += 1
            result = real_replace(source_path, archive_path)
            if calls["count"] == 1:
                raise OSError("injected archive directory fsync failure")
            return result

        with mock.patch.object(
                update_queue.kblib, "durable_replace",
                side_effect=fail_after_forward_move):
            with redirect_stdout(io.StringIO()):
                code = update_queue.main([
                    str(self.root), "--id", "B1", "--transition", "open",
                    "--reason", "global validation failed",
                    "--expected-state-revision", revision,
                    "--expected-sha256", fingerprint,
                    "--actor-role", "integrator", "--at",
                    "2026-08-04T03:00:00Z", "--apply",
                ])
        self.assertEqual(1, code)
        self.assertEqual(2, calls["count"])
        self.assertTrue(source.is_file())
        self.assertFalse(archive.exists())
        for path, content in before.items():
            self.assertEqual(content, (self.root / path).read_bytes())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_archive_restore_fsync_failure_preserves_recovery_lock(self):
        self.merge_b1()
        revision, fingerprint = self.expected()
        source = self.root / ".cambium/deltas/B1.yaml"
        archive = self.root / (
            ".cambium/receipts/invalidated-deltas/B1-r%d.yaml" %
            (int(revision) + 1)
        )
        state_paths = (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH,
        )
        before = {path: (self.root / path).read_bytes()
                  for path in state_paths}
        real_replace = update_queue.kblib.durable_replace
        calls = {"count": 0}

        def fail_after_restore(source_path, archive_path):
            calls["count"] += 1
            result = real_replace(source_path, archive_path)
            if calls["count"] == 2:
                raise OSError("injected restore directory fsync failure")
            return result

        with mock.patch.object(
                update_queue.kblib, "durable_replace",
                side_effect=fail_after_restore), \
                mock.patch.object(
                    update_queue.kblib, "write_receipts",
                    side_effect=OSError("injected receipt failure")):
            with redirect_stdout(io.StringIO()):
                code = update_queue.main([
                    str(self.root), "--id", "B1", "--transition", "open",
                    "--reason", "global validation failed",
                    "--expected-state-revision", revision,
                    "--expected-sha256", fingerprint,
                    "--actor-role", "integrator", "--at",
                    "2026-08-04T03:00:00Z", "--apply",
                ])
        self.assertEqual(1, code)
        self.assertEqual(2, calls["count"])
        self.assertTrue(source.is_file())
        self.assertFalse(archive.exists())
        for path, content in before.items():
            self.assertEqual(content, (self.root / path).read_bytes())
        self.assertTrue((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())

    def test_two_merge_failures_preserve_append_only_invalidation_history(self):
        self.merge_b1()
        revision, fingerprint = self.expected()
        first = self.command(
            "--id", "B1", "--transition", "open",
            "--reason", "first global validation failure",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T03:00:00Z",
            "--apply",
        )
        self.assertEqual(0, first.returncode, first.stdout)

        revalidation_gate = self.queue_gate()
        revision, fingerprint = self.expected()
        cleared = self.command(
            "--id", "B1", "--hold-state", "none",
            "--gate-receipt", revalidation_gate,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T04:00:00Z",
            "--apply",
        )
        self.assertEqual(0, cleared.returncode, cleared.stdout)

        self.append_receipt("audit-page-2", target="Topics/A.md")
        self.append_receipt("audit-batch-2", check="batch_gate")
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T05:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-2\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        revision, fingerprint = self.expected()
        merged = self.command(
            "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-2",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T05:00:00Z",
            "--apply",
        )
        self.assertEqual(0, merged.returncode, merged.stdout)
        revision, fingerprint = self.expected()
        second = self.command(
            "--id", "B1", "--transition", "open",
            "--reason", "second global validation failure",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--at", "2026-08-04T06:00:00Z",
            "--apply",
        )
        self.assertEqual(0, second.returncode, second.stdout)

        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        history = result["items_by_id"]["B1"]["invalidation_history"]
        self.assertEqual(2, len(history))
        self.assertEqual([], history[0]["revalidation_receipts"])
        self.assertEqual([revalidation_gate],
                         history[1]["revalidation_receipts"])
        self.assertEqual(2, len({entry["transition_receipt"] for entry in history}))
        self.assertEqual(2, len({entry["delta_archive_path"] for entry in history}))
        for entry in history:
            archive = self.root / entry["delta_archive_path"]
            self.assertTrue(archive.is_file())
            self.assertEqual(kblib.sha256_file(archive), entry["delta_sha256"])
            transition = result["receipt_catalog"][
                entry["transition_receipt"]][1]
            self.assertEqual(entry, transition["invalidation"])


if __name__ == "__main__":
    unittest.main()
