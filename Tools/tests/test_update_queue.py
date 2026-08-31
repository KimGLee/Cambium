"""Owner-focused tests for the current Required Queue transition writer.

The expensive AuditPlan/review/Delta producer chain is generated once into
validated Integration checkpoints. Tests start at the adjacent legal state
for the transition they own; only explicit Slow recovery probes cross a
process boundary besides the single public CLI/JSON transport check.
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS.parent))
sys.path.insert(0, str(TOOLS))

from Tools.execution.task_runtime import queue_runtime  # noqa: E402
import Tools.execution.audit.check_batch_close as check_batch_close  # noqa: E402
import Tools.execution.task_runtime.check_queue as check_queue  # noqa: E402
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.execution.task_runtime.update_queue as update_queue  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.tests.fixtures.integration.update_queue_checkpoints import (  # noqa: E402
    install_update_queue_checkpoint,
)
from Tools.tests.fixtures.integration.batch_close_checkpoints import (  # noqa: E402
    BatchCloseCheckpointCase,
)
from Tools.tests.support.test_effects import catalog_effects  # noqa: E402


def _invoke_update_queue(*arguments):
    """Call the implementation in-process and retain both report channels."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = update_queue.main(list(arguments))
    return code, stdout.getvalue(), stderr.getvalue()


def _invoke_resume_status(root):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = check_queue.main([str(root), "--resume-status"])
    return code, stdout.getvalue() + stderr.getvalue()


def _invoke_batch_close(root, *arguments):
    """Run the adjacent close-evidence producer without a CLI subprocess."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = check_batch_close.main([
            str(root), "--batch", "B1",
            "--integrator", "fixture-integrator",
            "--reviewer", "fixture-reviewer",
            "--review-attestation",
            "I reviewed the exact listed candidates and merged snapshot.",
            *arguments,
        ])
    return code, stdout.getvalue(), stderr.getvalue()


class _CheckpointCase(unittest.TestCase):
    """Give every mutating test a private copy of one validated checkpoint."""

    CHECKPOINT = None

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.scenario = install_update_queue_checkpoint(
            self.root, self.CHECKPOINT)

    def expected(self):
        queue = kblib.load_yaml_file(
            self.root / queue_runtime.QUEUE_PATH)
        return str(queue["state_revision"]), kblib.sha256_file(
            self.root / queue_runtime.QUEUE_PATH)


class UpdateQueueCliContractTests(unittest.TestCase):
    """The parser exposes only the current, exclusive writer operation."""

    def _parse_failure(self, *arguments):
        stderr = io.StringIO()
        with mock.patch.object(update_queue, "_run") as run, \
                redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                update_queue.main(["/unused", "--id", "B1", *arguments])
        run.assert_not_called()
        return raised.exception.code, stderr.getvalue()

    def test_cli_requires_one_current_writer_action(self):
        cases = (
            (("--transition", "open", "--hold-state", "paused"),
             "not allowed with argument"),
            ((), "one of the arguments --transition --hold-state is required"),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                code, output = self._parse_failure(*arguments)
                self.assertEqual(1, code)
                self.assertIn(expected, output)


class UpdateQueueProjectionUnitTests(unittest.TestCase):
    """The close projection is a pure ownership-transfer calculation."""

    @staticmethod
    def _coverage(*, batch="B1", next_batch=None):
        return {"pages": [{
            "path": "Topics/A.md", "batch": batch,
            "next_batch": next_batch,
        }]}

    @staticmethod
    def _batch(batch_id, state, *, successor_of=None):
        item = {
            "id": batch_id,
            "state": state,
            "manifest": ["Topics/A.md"],
        }
        if successor_of is not None:
            item["successor_of"] = successor_of
        return item

    def test_close_projection_preserves_or_transfers_one_successor(self):
        cases = (
            (
                self._coverage(next_batch="B3"),
                {"required_queue": [
                    self._batch("B1", "merge-ready"),
                    self._batch("B3", "queued", successor_of="B1"),
                ]},
                "B1", ("B1", "B3"),
            ),
            (
                self._coverage(batch="B1", next_batch="B3"),
                {"required_queue": [
                    self._batch("B1", "closed"),
                    self._batch("B3", "merge-ready", successor_of="B1"),
                ]},
                "B3", ("B3", None),
            ),
        )
        for coverage, queue, closing_id, expected in cases:
            with self.subTest(closing_id=closing_id):
                projected = update_queue._project_closed_coverage(
                    coverage, queue, closing_id)
                page = projected["pages"][0]
                self.assertEqual(expected, (page["batch"], page["next_batch"]))

    def test_close_projection_rejects_ambiguous_successors(self):
        with self.assertRaisesRegex(ValueError, "multiple queued successors"):
            update_queue._project_closed_coverage(
                self._coverage(next_batch="B1"),
                {"required_queue": [
                    self._batch("B1", "merge-ready"),
                    self._batch("B3", "queued", successor_of="B1"),
                    self._batch("B4", "queued", successor_of="B1"),
                ]},
                "B1",
            )


class OpenWriterIntegrationTests(_CheckpointCase):
    """One public CLI/JSON probe connects the ready gate to the writer."""

    CHECKPOINT = "planning-ready"

    def test_json_transport_persists_the_current_open_receipt(self):
        revision, fingerprint = self.expected()
        completed = subprocess.run(
            [
                sys.executable, str(TOOLS / "update_queue.py"), str(self.root),
                "--id", "B1", "--transition", "open",
                "--gate-receipt", self.scenario["ready_gate"],
                "--expected-state-revision", revision,
                "--expected-sha256", fingerprint,
                "--actor-role", "integrator",
                "--at", "2026-08-04T01:00:00Z",
                "--apply", "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        produced = json.loads(completed.stdout)
        receipt = next(
            record for record in produced
            if record.get("check") == "queue_transition"
        )
        self.assertEqual(
            {"task_transition", "queue_transition"},
            {record.get("check") for record in produced},
        )

        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual("open", item["state"])
        self.assertEqual(self.scenario["ready_gate"], item["activation_receipt"])
        self.assertEqual(receipt["receipt_id"], item["transition_receipts"][-1])
        self.assertEqual(fingerprint, receipt["before_required_queue_sha256"])
        self.assertEqual(result["queue_sha256"],
                         receipt["after_required_queue_sha256"])
        opening = queue_runtime.current_opening_semantic_context(result, "B1")
        self.assertEqual(receipt["receipt_id"],
                         opening["opening_transition_receipt"])
        task_receipt_id = result["progress"]["task_transition_receipts"][0]
        task_receipt = result["receipt_catalog"][task_receipt_id][1]
        self.assertEqual("B1", task_receipt["first_open_batch_id"])
        self.assertEqual(
            receipt["receipt_id"],
            task_receipt["first_open_transition_receipt"],
        )
        self.assertEqual(1, task_receipt["queue_state_revision"])
        self.assertEqual(
            queue_runtime.contract_sha256(result["progress"]),
            task_receipt["contract_sha256"],
        )


class MergeAdmissionIntegrationTests(_CheckpointCase):
    """Consume the one static open + complete pre-merge evidence checkpoint."""

    CHECKPOINT = "merge-admission-b1"

    def _merge_arguments(self, *extra):
        revision, fingerprint = self.expected()
        return (
            str(self.root), "--id", "B1", "--transition", "merge-ready",
            "--delta-path", self.scenario["delta_path"],
            *extra,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--apply",
        )

    def test_current_premerge_checkpoint_admits_one_writer_transition(self):
        before_sha = kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH)
        code, output, errors = _invoke_update_queue(*self._merge_arguments(
            "--batch-receipt", self.scenario["batch_receipt"]))
        self.assertEqual(0, code, output + errors)

        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual("merge-ready", item["state"])
        self.assertEqual([self.scenario["batch_receipt"]],
                         item["batch_receipts"])
        self.assertEqual(
            kblib.sha256_file(self.root / self.scenario["delta_path"]),
            item["delta_sha256"],
        )
        receipt = result["receipt_catalog"][
            item["transition_receipts"][-1]][1]
        self.assertEqual(before_sha, receipt["before_required_queue_sha256"])
        self.assertEqual(result["queue_sha256"],
                         receipt["after_required_queue_sha256"])

    def test_admission_refuses_missing_evidence_or_nonmonotonic_time(self):
        queue_path = self.root / queue_runtime.QUEUE_PATH
        before = queue_path.read_bytes()
        cases = (
            ((), "batch"),
            (("--batch-receipt", self.scenario["batch_receipt"],
              "--at", "2026-08-04T00:30:00Z"), "timestamp"),
        )
        for extra, expected in cases:
            with self.subTest(expected=expected):
                code, output, errors = _invoke_update_queue(
                    *self._merge_arguments(*extra))
                self.assertEqual(1, code, output + errors)
                self.assertIn(expected, (output + errors).lower())
                self.assertEqual(before, queue_path.read_bytes())

    def test_hold_substate_is_written_as_one_current_transition_edge(self):
        revision, fingerprint = self.expected()
        code, output, errors = _invoke_update_queue(
            str(self.root), "--id", "B1", "--hold-state", "paused",
            "--reason", "operator pause",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
            "--at", "2026-08-04T01:30:00Z", "--apply",
        )
        self.assertEqual(0, code, output + errors)
        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual(("open", "paused"),
                         (item["state"], item["hold_state"]))
        receipt = result["receipt_catalog"][
            item["transition_receipts"][-1]][1]
        self.assertEqual(("none", "paused"),
                         (receipt["before_hold_state"],
                          receipt["after_hold_state"]))


class MergeRollbackIntegrationTests(_CheckpointCase):
    """The merge-ready writer owns one adjacent pre-apply rollback seam."""

    CHECKPOINT = "merged-b1"

    def test_preapply_rollback_archives_delta_and_records_invalidation(self):
        revision, fingerprint = self.expected()
        coverage_before = (
            self.root / queue_runtime.COVERAGE_PATH).read_bytes()
        code, output, errors = _invoke_update_queue(
            str(self.root), "--id", "B1", "--transition", "open",
            "--reason", "global validation failed",
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--apply",
        )
        self.assertEqual(0, code, output + errors)

        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual(("open", "revalidation-required"),
                         (item["state"], item["hold_state"]))
        self.assertEqual(coverage_before,
                         (self.root / queue_runtime.COVERAGE_PATH).read_bytes())
        self.assertFalse((self.root / ".cambium/deltas/B1.yaml").exists())
        invalidation = item["invalidation_history"][-1]
        archive = self.root / invalidation["delta_archive_path"]
        self.assertEqual(invalidation["delta_sha256"],
                         kblib.sha256_file(archive))
        receipt = result["receipt_catalog"][
            invalidation["transition_receipt"]][1]
        self.assertEqual(invalidation, receipt["invalidation"])


class AppliedRollbackIntegrationTests(BatchCloseCheckpointCase):
    """Consume the batch-close owner's applied checkpoint at the rollback edge."""

    def test_applied_rollback_restores_the_exact_preapply_coverage(self):
        archives = sorted(
            (self.root / ".cambium/receipts/pre-apply-coverage").glob(
                "B1-r*.yaml"))
        self.assertEqual(1, len(archives), archives)
        coverage_before = archives[0].read_bytes()
        self.assertNotEqual(
            coverage_before,
            (self.root / queue_runtime.COVERAGE_PATH).read_bytes(),
        )
        queue = kblib.load_yaml_file(
            self.root / queue_runtime.QUEUE_PATH)
        revision = str(queue["state_revision"])
        fingerprint = kblib.sha256_file(
            self.root / queue_runtime.QUEUE_PATH)
        code, output, errors = _invoke_update_queue(
            str(self.root), "--id", "B1", "--transition", "open",
            "--reason", "batch-close rejected the applied snapshot",
            "--delta-apply-receipt", self.delta_apply_receipt,
            "--expected-state-revision", revision,
            "--expected-sha256", fingerprint,
            "--actor-role", "integrator", "--apply",
        )
        self.assertEqual(0, code, output + errors)
        self.assertEqual(
            coverage_before,
            (self.root / queue_runtime.COVERAGE_PATH).read_bytes(),
        )
        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("clear", result["pending_delta_applies"]["status"])
        item = result["items_by_id"]["B1"]
        invalidation = item["invalidation_history"][-1]
        self.assertEqual(self.delta_apply_receipt,
                         invalidation["delta_apply_receipt"])
        self.assertEqual(invalidation["coverage_restored_sha256"],
                         result["coverage_sha256"])


class ClosePublicationRecoverySlowTests(BatchCloseCheckpointCase):
    """A hard exit during close is owned by the Queue writer recovery seam."""

    @catalog_effects(process_calls=1)
    def test_close_state_without_receipt_exposes_exact_recovery_plan(self):
        code, output, errors = _invoke_batch_close(self.root, "--json")
        self.assertEqual(0, code, output + errors)
        rows = json.loads(next(
            line for line in output.splitlines()
            if line.startswith("[{")
        ))
        close_gate = next(
            row for row in rows if row.get("check") == "batch_close_gate")
        queue = kblib.load_yaml_file(
            self.root / queue_runtime.QUEUE_PATH)
        arguments = [
            str(self.root), "--id", "B1", "--transition", "closed",
            "--gate-receipt", close_gate["queue_consistency_receipt"],
            "--close-gate-receipt", close_gate["receipt_id"],
            "--delta-apply-receipt", self.delta_apply_receipt,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
            "--actor-role", "integrator", "--at",
            "2099-01-01T03:00:00Z", "--apply",
        ]
        program = r'''
import os
import sys

sys.path.insert(0, sys.argv[1])
from Tools.execution.task_runtime import update_queue

def crash_before_receipt(*args, **kwargs):
    os._exit(23)

update_queue.kblib.write_receipts = crash_before_receipt
raise SystemExit(update_queue.main(sys.argv[2:]))
'''
        child = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS.parent), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, child.returncode, child.stdout)

        code, resume = _invoke_resume_status(self.root)
        self.assertEqual(1, code, resume)
        self.assertIn("task_state=active", resume)
        self.assertIn("batches.closed=B1", resume)
        for ledger in ("coverage", "queue", "progress"):
            self.assertIn("state.%s phase=planned-after" % ledger, resume)
        self.assertIn('"status": "absent"', resume)
        self.assertIn("next_action=reconcile-interrupted-write", resume)


class OpenWriterCasSlowTests(_CheckpointCase):
    """A concurrent page edit must survive the writer's failed publication."""

    CHECKPOINT = "planning-ready"

    def test_page_change_after_state_write_aborts_without_losing_the_edit(self):
        revision, fingerprint = self.expected()
        tracked = {
            relative: (self.root / relative).read_bytes()
            for relative in (
                queue_runtime.COVERAGE_PATH,
                queue_runtime.QUEUE_PATH,
                queue_runtime.PROGRESS_PATH,
            )
        }
        page = self.root / "Topics/A.md"
        concurrent = page.read_text(encoding="utf-8") + \
            "\nConcurrent semantic edit\n"
        real_write_state = update_queue._write_state

        def write_then_edit_page(*args, **kwargs):
            result = real_write_state(*args, **kwargs)
            page.write_text(concurrent, encoding="utf-8")
            return result

        with mock.patch.object(
                update_queue, "_write_state", side_effect=write_then_edit_page):
            code, output, errors = _invoke_update_queue(
                str(self.root), "--id", "B1", "--transition", "open",
                "--gate-receipt", self.scenario["ready_gate"],
                "--expected-state-revision", revision,
                "--expected-sha256", fingerprint,
                "--actor-role", "integrator", "--apply",
            )
        self.assertEqual(1, code, output + errors)
        self.assertTrue(
            "opening semantic baseline changed" in output or
            "page identity or bytes changed before publication" in output,
            output + errors,
        )
        for relative, before in tracked.items():
            self.assertEqual(before, (self.root / relative).read_bytes(),
                             relative)
        self.assertEqual(concurrent, page.read_text(encoding="utf-8"))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())


class ReceiptAppendRecoverySlowTests(_CheckpointCase):
    """A foreign append prevents unsafe rollback and leaves exact recovery."""

    CHECKPOINT = "planning-ready"

    def test_foreign_append_after_own_receipt_preserves_log_and_lock(self):
        revision, fingerprint = self.expected()
        external = {
            "receipt_id": "audit-external-after-own",
            "check": "external",
            "target": "unrelated",
            "result": "pass",
            "invalidated_by": None,
        }
        own = {}
        real_append = kblib.write_receipts

        def append_own_and_foreign_then_fail(path, receipts, **kwargs):
            if Path(path).name != "queue-transitions.jsonl":
                return real_append(path, receipts, **kwargs)
            own.update(receipts[0])
            real_append(path, receipts, **kwargs)
            real_append(path, [external])
            raise OSError("injected failure after durable own append")

        with mock.patch.object(
                update_queue.kblib, "write_receipts",
                side_effect=append_own_and_foreign_then_fail):
            code, output, errors = _invoke_update_queue(
                str(self.root), "--id", "B1", "--transition", "open",
                "--gate-receipt", self.scenario["ready_gate"],
                "--expected-state-revision", revision,
                "--expected-sha256", fingerprint,
                "--actor-role", "integrator", "--apply",
            )
        self.assertEqual(1, code, output + errors)
        records = [
            json.loads(line) for line in
            (self.root / ".cambium/receipts/queue-transitions.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [own["receipt_id"], external["receipt_id"]],
            [record["receipt_id"] for record in records],
        )
        result = runtime_validation.validate_runtime(self.root)
        lock = result["_writer_locks"][0]
        self.assertEqual("matching", lock["operation_receipt"]["status"])
        self.assertTrue(lock["operation_receipt"]["matching_receipt"])
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock/owner.json").is_file())


class ArchiveRecoverySlowTests(_CheckpointCase):
    """A real hard exit exposes the archive move to the recovery consumer."""

    CHECKPOINT = "merged-b1"

    def test_hard_exit_after_delta_move_exposes_exact_archive_recovery(self):
        source = self.root / ".cambium/deltas/B1.yaml"
        queue_path = self.root / queue_runtime.QUEUE_PATH
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        before_hashes = {
            "queue": kblib.sha256_file(queue_path),
            "coverage": kblib.sha256_file(coverage_path),
            "progress": kblib.sha256_file(progress_path),
        }
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
import Tools.execution.task_runtime.update_queue as update_queue

root = os.path.realpath(sys.argv[2])
source = os.path.realpath(os.path.join(root, ".cambium/deltas/B1.yaml"))
archive = os.path.realpath(os.path.join(root, sys.argv[3]))
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
            [sys.executable, "-c", program, str(TOOLS.parent), str(self.root),
             archive_relative, *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, child.returncode, child.stdout)
        self.assertFalse(source.exists())
        self.assertEqual(delta_sha, kblib.sha256_file(archive))
        self.assertEqual(before_hashes["queue"], kblib.sha256_file(queue_path))
        self.assertEqual(before_hashes["coverage"],
                         kblib.sha256_file(coverage_path))
        self.assertEqual(before_hashes["progress"],
                         kblib.sha256_file(progress_path))

        code, resume = _invoke_resume_status(self.root)
        self.assertIn(code, (1, 2), resume)
        self.assertIn("recovery_fact=archive-moved-state-before", resume)
        self.assertIn("delta_archive status=archived", resume)

        archive.write_bytes(archive.read_bytes() + b"# altered after crash\n")
        _code, mismatched = _invoke_resume_status(self.root)
        self.assertIn("delta_archive status=archive-sha-mismatch", mismatched)


if __name__ == "__main__":
    unittest.main()
