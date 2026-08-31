"""Owner-focused contracts and writer-boundary checks for Delta apply.

Pure path, Receipt, and rejection contracts stay in process. Integration and
recovery cases consume the one generated merge-ready checkpoint; this module
does not recreate the Task, AuditPlan, Queue-open, or merge-admission prologue.
Generic lock and Receipt algorithms remain owned by ``test_runtime_safety``;
post-apply rollback remains owned by ``test_update_queue``; and close
consumption remains owned by ``test_check_batch_close``.
"""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.task_runtime.apply_delta as apply_delta
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
from Tools.tests.fixtures.integration.update_queue_checkpoints import (  # noqa: E402
    install_update_queue_checkpoint,
)


class ApplyDeltaCliContractTests(unittest.TestCase):
    """Parser contradictions stop before any repository input is consumed."""

    def test_invalid_invocations_never_reach_the_writer(self):
        cases = (
            ("missing-root", [".cambium/deltas/B1.yaml"],
             "the following arguments are required: --root"),
            ("contradictory-mode", [
                ".cambium/deltas/B1.yaml", "--root", "/unused",
                "--preflight", "--apply",
            ], "not allowed with argument"),
        )
        for label, arguments, expected in cases:
            with self.subTest(case=label), \
                    mock.patch.object(apply_delta, "_run") as writer:
                output = io.StringIO()
                with contextlib.redirect_stderr(output):
                    with self.assertRaises(SystemExit) as raised:
                        apply_delta.main(arguments)
                self.assertEqual(1, raised.exception.code)
                self.assertIn(expected, output.getvalue())
                writer.assert_not_called()


class ApplyDeltaProducerContractTests(unittest.TestCase):
    """Own the current path and Receipt projections without a repository."""

    def test_delta_path_is_derived_from_batch(self):
        expected, errors = apply_delta._canonical_delta_path(
            SimpleNamespace(delta=".cambium/deltas/B1.yaml"), "B1")
        self.assertEqual(".cambium/deltas/B1.yaml", expected)
        self.assertEqual([], errors)

        expected, errors = apply_delta._canonical_delta_path(
            SimpleNamespace(delta="elsewhere/B1.yaml"), "B1")
        self.assertEqual(".cambium/deltas/B1.yaml", expected)
        self.assertEqual([
            "canonical delta argument must be exactly "
            ".cambium/deltas/B1.yaml",
        ], errors)

    def test_pre_apply_archive_path_is_derived_from_queue_revision(self):
        self.assertEqual(
            ".cambium/receipts/pre-apply-coverage/B1-r7.yaml",
            apply_delta.pre_apply_coverage_archive_path("B1", 7),
        )

    def test_receipt_binds_delta_after_image_and_unchanged_queue_state(self):
        result = {
            "queue": {
                "task_id": "T1",
                "queue_revision": "rev-1",
                "state_revision": 7,
            },
            "queue_sha256": "sha256:" + "3" * 64,
            "progress_sha256": "sha256:" + "4" * 64,
        }
        settlement = {
            "protocol": "routed-gap-settlement/1",
            "obligation_count_before": 1,
            "obligation_set_sha256_before": "sha256:" + "5" * 64,
            "obligation_record_set_sha256_before": "sha256:" + "6" * 64,
            "unsettled_count_after": 0,
            "unsettled_set_sha256_after": "sha256:" + "7" * 64,
        }
        with mock.patch.object(
                apply_delta.kblib, "make_receipt",
                return_value={"receipt_id": "audit-apply-delta"}):
            receipt = apply_delta._prepare_receipt(
                result, "B1", ".cambium/deltas/B1.yaml",
                "sha256:" + "0" * 64,
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                "integrator",
                ".cambium/receipts/pre-apply-coverage/B1-r7.yaml",
                settlement,
            )

        self.assertEqual("T1", receipt["task_id"])
        self.assertEqual("B1", receipt["batch_id"])
        self.assertEqual("sha256:" + "1" * 64,
                         receipt["before_coverage_sha256"])
        self.assertEqual("sha256:" + "2" * 64,
                         receipt["after_coverage_sha256"])
        self.assertEqual(
            result["queue_sha256"],
            receipt["before_required_queue_sha256"])
        self.assertEqual(
            result["queue_sha256"],
            receipt["after_required_queue_sha256"])
        self.assertEqual(
            result["progress_sha256"], receipt["before_progress_sha256"])
        self.assertEqual(
            result["progress_sha256"], receipt["after_progress_sha256"])
        self.assertEqual(7, receipt["queue_state_revision"])
        self.assertEqual(
            "routed-gap-settlement/1", receipt["settlement_protocol"])
        self.assertEqual(0, receipt["prospective_unsettled_count"])


class ApplyDeltaRunContractTests(unittest.TestCase):
    """Input and producer-policy failures stop before the writer seam."""

    def run_arguments(self):
        return SimpleNamespace(
            root="/repo", delta=".cambium/deltas/B1.yaml")

    def test_unsafe_input_path_stops_before_the_writer(self):
        with mock.patch.object(
                apply_delta.kblib, "repository_path",
                side_effect=ValueError("unsafe path")), \
                mock.patch.object(apply_delta, "_canonical_apply") as writer:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = apply_delta._run(self.run_arguments())

        self.assertEqual(1, code)
        self.assertIn("cannot load Coverage delta inputs: unsafe path",
                      output.getvalue())
        writer.assert_not_called()

    def test_delta_policy_rejection_stops_before_the_writer(self):
        delta = {
            "batch": "B1",
            "pages": [{"path": "Topics/A.md", "next_batch": None}],
        }
        with mock.patch.object(
                apply_delta.kblib, "repository_path",
                side_effect=("/repo/delta.yaml", "/repo/coverage.yaml")), \
                mock.patch.object(
                    apply_delta.kblib, "read_bytes",
                    side_effect=(b"delta", b"pages: []\n")), \
                mock.patch.object(
                    apply_delta, "_parse_delta_bytes", return_value=delta), \
                mock.patch.object(apply_delta, "_canonical_apply") as writer:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = apply_delta._run(self.run_arguments())

        self.assertEqual(1, code)
        self.assertIn("control field", output.getvalue())
        writer.assert_not_called()


class CanonicalApplyDeltaTests(unittest.TestCase):
    """Consume one validated merge-ready checkpoint at the writer boundary."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        install_update_queue_checkpoint(self.root, "merged-b1")
        delta = self.load(".cambium/deltas/B1.yaml")
        self.delta_gate_receipts = list(delta["pages"][0]["gate_receipts"])

    def tearDown(self):
        self.temporary.cleanup()

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def apply_arguments(self, receipt=".cambium/receipts/applied.jsonl"):
        return [
            ".cambium/deltas/B1.yaml",
            "--root", str(self.root), "--apply",
            "--actor-role", "integrator",
            "--expected-coverage-sha256", kblib.sha256_file(
                self.root / queue_runtime.COVERAGE_PATH
            ),
            "--expected-queue-sha256", kblib.sha256_file(
                self.root / queue_runtime.QUEUE_PATH
            ),
            "--receipts", receipt,
        ]

    def invoke(self, arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = apply_delta.main(arguments)
        return code, output.getvalue()

    def assert_no_write_debris(self):
        coverage = self.root / queue_runtime.COVERAGE_PATH
        self.assertFalse(Path(str(coverage) + ".bak").exists())
        self.assertFalse(Path(str(coverage) + ".tmp").exists())
        self.assertEqual([], list(self.root.rglob(".cambium-write-*")))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists()
        )

    def test_stale_coverage_or_queue_sha_fails_before_lock_and_write(self):
        coverage = self.root / queue_runtime.COVERAGE_PATH
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
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        concurrent = self.load(queue_runtime.COVERAGE_PATH)
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
        # Exercise the writer's metadata handoff in the one successful
        # transaction.  The metadata owner's complete predicate matrix stays
        # in test_metadata_property_state; this test only proves that the
        # canonical Delta writer binds and publishes its result atomically.
        page_path = self.root / "Topics/A.md"
        page_path.write_text(
            page_path.read_text(encoding="utf-8")
            + "\nSemantic content changed after opening.\n",
            encoding="utf-8",
        )
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        before_coverage = coverage_path.read_bytes()
        before_coverage_sha = kblib.sha256_file(coverage_path)
        queue_sha = kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH)
        progress_sha = kblib.sha256_file(self.root / queue_runtime.PROGRESS_PATH)
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
                         operation["before_queue_sha256"])
        self.assertEqual(queue_sha,
                         operation["planned_after_queue_sha256"])
        self.assertEqual(progress_sha,
                         operation["before_progress_sha256"])
        self.assertEqual(progress_sha,
                         operation["planned_after_progress_sha256"])
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

        coverage = self.load(queue_runtime.COVERAGE_PATH)
        page = coverage["pages"][0]
        self.assertEqual("drafted", page["authoring_status"])
        self.assertEqual(self.delta_gate_receipts, page["gate_receipts"])
        self.assertEqual("B1", page["next_batch"])
        self.assertEqual(
            [], runtime_validation.validate_runtime(self.root)["errors"])
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
        self.assertEqual(queue_sha, kblib.sha256_file(
            self.root / queue_runtime.QUEUE_PATH))
        self.assertEqual(progress_sha, kblib.sha256_file(
            self.root / queue_runtime.PROGRESS_PATH))
        self.assertEqual(operation["delta_sha256"], receipt["delta_sha256"])
        self.assertEqual(
            ["Topics/A.md"],
            [event["path"] for event in receipt["property_events"]],
        )
        property_state = page["property_state"]["last_content_modified"]
        self.assertEqual(receipt["receipt_id"],
                         property_state["evidence_receipt"])
        self.assertIn(
            "last_content_modified: %s" % receipt["checked_at"][:10],
            page_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            operation["opening_transition_receipt"],
            receipt["opening_transition_receipt"])
        self.assertEqual(
            operation["manifest_semantic_before_set_sha256"],
            receipt["manifest_semantic_before_set_sha256"])
        archive = self.root / receipt["before_coverage_archive_path"]
        self.assertEqual(before_coverage, archive.read_bytes())
        self.assert_no_write_debris()

    def test_hard_exit_records_three_ledger_recovery_state(self):
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
        queue_path = self.root / queue_runtime.QUEUE_PATH
        progress_path = self.root / queue_runtime.PROGRESS_PATH
        before_coverage_sha = kblib.sha256_file(coverage_path)
        before_queue_sha = kblib.sha256_file(queue_path)
        before_progress_sha = kblib.sha256_file(progress_path)
        program = """
import os
import sys

sys.path.insert(0, sys.argv[1])
import Tools.execution.task_runtime.apply_delta as apply_delta

root = os.path.realpath(sys.argv[2])
coverage = os.path.realpath(os.path.join(
    root, apply_delta.queue_runtime.COVERAGE_PATH
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
                         operation["before_queue_sha256"])
        self.assertEqual(before_queue_sha,
                         operation["planned_after_queue_sha256"])
        self.assertEqual(before_progress_sha,
                         operation["before_progress_sha256"])
        self.assertEqual(before_progress_sha,
                         operation["planned_after_progress_sha256"])

        recovery = runtime_validation.validate_runtime(self.root)
        self.assertEqual(1, len(recovery["_writer_locks"]))
        interrupted = recovery["_writer_locks"][0]
        self.assertEqual(
            {"coverage": "planned-after", "progress": "before",
             "queue": "before", "standards": "before"},
            {name: phase["phase"] for name, phase in
             interrupted["state_phases"].items()},
        )
        self.assertIn("partial write is possible",
                      interrupted["reconciliation_hint"])

    def test_external_receipt_race_rolls_back_without_deleting_winner(self):
        page_path = self.root / "Topics/A.md"
        page_path.write_text(
            "---\ntitle: A\n---\nChanged body\n", encoding="utf-8")
        before_page = page_path.read_bytes()
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
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
        self.assertEqual(before_page, page_path.read_bytes())
        self.assertNotIn(
            "last_content_modified:", page_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [external],
            [json.loads(line) for line in
             receipt_path.read_text(encoding="utf-8").splitlines()],
        )
        self.assert_no_write_debris()

    def test_failure_after_own_receipt_preserves_both_records_and_lock(self):
        coverage_path = self.root / queue_runtime.COVERAGE_PATH
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
        recovery = runtime_validation.validate_runtime(self.root)
        lock = recovery["_writer_locks"][0]
        self.assertEqual("matching",
                         lock["operation_receipt"]["status"])
        self.assertTrue(lock["operation_receipt"]["matching_receipt"])
        self.assertEqual(
            {"coverage": "before", "progress": "before", "queue": "before",
             "standards": "before"},
            {name: phase["phase"] for name, phase in
             lock["state_phases"].items()},
        )


if __name__ == "__main__":
    unittest.main()
