"""Owned tests for the batch-close producer and its adjacent consumers.

Contract predicates stay with their machine owners. Real writer seams start
from generated applied checkpoints; only crash, mutation and recovery tests
exercise isolated slow paths.
"""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.check_batch_close as check_batch_close
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.queue_runtime.resume as resume
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.execution.task_runtime.update_queue as update_queue
import Tools.platform.common.kblib as kblib
from Tools.tests.fixtures.integration.batch_close_checkpoints import (
    BatchCloseCheckpointCase,
    StateMutatingBatchCloseCheckpointCase,
)


def _invoke(entrypoint, arguments):
    """Run one Python entrypoint in-process and retain both projections."""
    output = io.StringIO()
    errors = io.StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        code = entrypoint(arguments)
    return code, output.getvalue(), errors.getvalue()


def _produce_close(root):
    return _invoke(check_batch_close.main, [
        str(root), "--batch", "B1",
        "--integrator", "fixture-integrator",
        "--reviewer", "fixture-reviewer",
        "--review-attestation",
        "I reviewed the exact listed candidates and merged snapshot.",
    ])


class InvocationContractTests(unittest.TestCase):
    """Validate invocation-only predicates without constructing a runtime."""

    def test_reviewer_and_integrator_must_be_distinct(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = check_batch_close._main([
                "/fixture/repository", "--batch", "B1",
                "--integrator", "same", "--reviewer", "same",
                "--review-attestation", "Independent review statement.",
            ])
        self.assertEqual(1, code, output.getvalue())
        self.assertIn(
            "integrator and reviewer must use different declared labels",
            output.getvalue(),
        )


class WorkSpecStabilityContractTests(unittest.TestCase):
    """Keep the close-time CAS contract independent of a Task lifecycle."""

    def test_bound_work_spec_bytes_must_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = ".cambium/work_specs/B1.yaml"
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_text(
                "schema_version: 1\nbatch_id: B1\nmanifest: []\n",
                encoding="utf-8",
            )
            item = {
                "work_spec_path": relative,
                "work_spec_sha256": kblib.sha256_file(path),
            }
            check_batch_close._assert_work_spec_unchanged(root, item)

            path.write_text(
                path.read_text(encoding="utf-8") + "changed: true\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                    check_batch_close.ReceiptPublicationUncertain,
                    "Batch Work Spec changed"):
                check_batch_close._assert_work_spec_unchanged(root, item)


class MultiRegisterPublicationContractTests(unittest.TestCase):
    """Own the mechanical publication order and catalog path topology."""

    def test_preflight_catalog_uses_each_machine_owned_register(self):
        close = {"receipt_id": "raw-1"}
        audit = {"receipt_id": "audit-1", "record_kind": "audit-receipt"}
        commit = {"receipt_id": "close-1"}
        catalog = check_batch_close._receipt_catalog_with(
            {"receipt_catalog": {}, "current_receipt_catalog": {}}, (
                (".cambium/receipts/batch-close.jsonl", [close]),
                (".cambium/receipts/audit-receipts.jsonl", [audit]),
                (".cambium/receipts/batch-close.jsonl", [commit]),
            ))
        self.assertEqual(
            ".cambium/receipts/batch-close.jsonl", catalog["raw-1"][0])
        self.assertEqual(
            ".cambium/receipts/audit-receipts.jsonl", catalog["audit-1"][0])
        self.assertEqual(
            ".cambium/receipts/batch-close.jsonl", catalog["close-1"][0])

    def test_aggregate_is_the_last_publication_edge(self):
        calls = []
        with mock.patch.object(
                check_batch_close, "_append_receipts",
                side_effect=lambda path, records: calls.append(
                    (path, [record["receipt_id"] for record in records]))):
            check_batch_close._publish_close_bundle(
                "/runtime/batch-close.jsonl",
                "/runtime/audit-receipts.jsonl",
                [{"receipt_id": "raw-1"}],
                [{"receipt_id": "audit-1"}],
                {"receipt_id": "close-1"})
        self.assertEqual([
            ("/runtime/batch-close.jsonl", ["raw-1"]),
            ("/runtime/audit-receipts.jsonl", ["audit-1"]),
            ("/runtime/batch-close.jsonl", ["close-1"]),
        ], calls)


class ManifestPageCasSlowTests(unittest.TestCase):
    """Own page identity-and-byte CAS without constructing a Task runtime."""

    def test_changed_page_rejects_pre_and_post_publication_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "Topics/A.md"
            page.parent.mkdir(parents=True)
            page.write_text("# A\n\nCurrent semantics.\n", encoding="utf-8")
            frozen = check_batch_close._freeze_manifest_pages(
                root, ["Topics/A.md"], ())
            check_batch_close._assert_manifest_pages_unchanged(root, frozen)

            page.write_text(
                "# A\n\nChanged semantics.\n", encoding="utf-8")
            with self.assertRaisesRegex(
                    ValueError,
                    "manifest page changed before review evidence"):
                check_batch_close._assert_manifest_pages_unchanged(
                    root, frozen)
            with self.assertRaisesRegex(
                    check_batch_close.ReceiptPublicationUncertain,
                    "manifest page changed before review evidence"):
                check_batch_close._assert_manifest_pages_unchanged(
                    root, frozen, uncertain=True)


class BatchCloseRecoveryProjectionTests(unittest.TestCase):
    """Own the pure resume projection over already validated receipts."""

    @staticmethod
    def _result():
        return {
            "_writer_locks": [],
            "root": "/fixture/repository",
            "pending_delta_applies": {
                "status": "close-required",
                "current": [{
                    "batch": "B1",
                    "compatible_receipts": ["delta-apply-1"],
                }],
            },
            "items_by_id": {
                "B1": {
                    "state": "merge-ready",
                    "delta_sha256": "sha256:delta",
                    "work_spec_path": None,
                    "work_spec_sha256": None,
                    "manifest": ["Topics/A.md"],
                },
            },
            "queue": {
                "task_id": "TASK-1",
                "queue_revision": 4,
                "state_revision": 7,
                "selected_profile_manifest": "profiles/test/profile.toml",
            },
            "queue_sha256": "sha256:queue",
            "coverage_sha256": "sha256:coverage",
            "progress_sha256": "sha256:progress",
            "_profile_authorized_view": {
                "profile_snapshot_sha256": "sha256:profile",
                "profile_contract_fingerprint": "sha256:contract",
                "profile_load_inputs_sha256": "sha256:inputs",
                "_contract": {},
            },
        }

    @staticmethod
    def _receipt(receipt_id, checked_at):
        return {
            "receipt_id": receipt_id,
            "tool": resume.BATCH_CLOSE_TOOL,
            "check": "batch_close_gate",
            "target": "B1",
            "checked_at": checked_at,
            "queue_consistency_receipt": "queue-%s" % receipt_id,
            "delta_apply_receipt": "delta-apply-1",
            "merged_snapshot_sha256": "sha256:repository",
        }

    def test_current_bundle_selection_and_staleness_are_deterministic(self):
        catalog = {
            "close-1": (
                ".cambium/receipts/batch-close.jsonl",
                self._receipt("close-1", "2026-08-31T01:00:00Z"),
            ),
            "close-2": (
                ".cambium/receipts/batch-close.jsonl",
                self._receipt("close-2", "2026-08-31T02:00:00Z"),
            ),
        }
        with mock.patch.object(
                resume, "current_receipt_catalog", return_value=catalog), \
                mock.patch.object(
                    resume.kblib, "repository_snapshot_sha256",
                    return_value="sha256:repository"), \
                mock.patch.object(
                    resume, "close_gate_receipt_errors", return_value=[]):
            inventory = resume.batch_close_recovery_inventory(self._result())
        self.assertEqual("ready-to-close", inventory["status"])
        self.assertEqual("close-2", inventory["selected"][
            "close_gate_receipt"])
        self.assertEqual(
            ["close-1", "close-2"],
            [row["close_gate_receipt"] for row in inventory["compatible"]],
        )
        self.assertIn("--close-gate-receipt close-2",
                      inventory["update_queue_command"])

        catalog = {
            "close-stale": (
                ".cambium/receipts/batch-close.jsonl",
                self._receipt(
                    "close-stale", "2026-08-31T01:00:00Z"),
            ),
        }
        with mock.patch.object(
                resume, "current_receipt_catalog", return_value=catalog), \
                mock.patch.object(
                    resume.kblib, "repository_snapshot_sha256",
                    return_value="sha256:changed"), \
                mock.patch.object(
                    resume, "close_gate_receipt_errors",
                    return_value=["repository snapshot is stale"]):
            inventory = resume.batch_close_recovery_inventory(self._result())
        self.assertEqual("gate-required", inventory["status"])
        self.assertEqual([], inventory["compatible"])
        self.assertEqual(
            ["close-stale"],
            [row["close_gate_receipt"] for row in inventory["stale"]],
        )
        self.assertIsNone(inventory["selected"])
        self.assertIsNone(inventory["update_queue_command"])


class AppliedBatchCloseTests(BatchCloseCheckpointCase):
    """Adjacent producer/consumer and durable-write seams."""

    def test_produced_bundle_is_accepted_by_the_close_consumer(self):
        real_cas = check_batch_close._assert_manifest_pages_unchanged
        with mock.patch.object(
                check_batch_close, "_assert_manifest_pages_unchanged",
                wraps=real_cas) as page_cas:
            code, output, errors = _produce_close(self.root)
        self.assertEqual(0, code, output + errors)
        self.assertEqual(
            {False, True},
            {call.kwargs.get("uncertain", False)
             for call in page_cas.call_args_list},
        )
        consistency = self.output_value(
            output, "queue_consistency_receipt")
        close_gate = self.output_value(
            output, "close_gate_receipt")
        batch_records = [json.loads(line) for line in (
            self.root / ".cambium/receipts/batch-close.jsonl"
        ).read_text(encoding="utf-8").splitlines()]
        audit_records = [json.loads(line) for line in (
            self.root / ".cambium/receipts/audit-receipts.jsonl"
        ).read_text(encoding="utf-8").splitlines()]
        self.assertTrue(audit_records)
        self.assertTrue(all(
            record.get("record_kind") == "audit-receipt"
            for record in audit_records))
        batch_ids = {record["receipt_id"] for record in batch_records}
        audit_ids = {record["receipt_id"] for record in audit_records}
        self.assertTrue(batch_ids.isdisjoint(audit_ids))
        self.assertIn(close_gate, batch_ids)
        close_record = next(
            record for record in batch_records
            if record["receipt_id"] == close_gate)
        self.assertTrue(
            set(close_record["closed_list_evidence"].values()) & audit_ids)
        runtime = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        errors = queue_runtime.close_gate_receipt_errors(
            runtime["current_receipt_catalog"], close_gate,
            **self.close_validation_kwargs(runtime, consistency))
        self.assertEqual([], errors)
        queue = self.queue()
        code, output, errors = _invoke(update_queue.main, [
            str(self.root), "--id", "B1", "--transition", "closed",
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
            "--actor-role", "integrator", "--apply",
            "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", self.delta_apply_receipt,
        ])
        self.assertEqual(0, code, output + errors)
        closed = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], closed["errors"])
        self.assertEqual("closed", closed["items_by_id"]["B1"]["state"])

    def test_partial_multi_register_publication_retains_fail_closed_lock(self):
        program = r'''
import os
import sys

sys.path.insert(0, sys.argv[1])
import Tools.execution.audit.check_batch_close as check_batch_close

real_append = check_batch_close._append_receipts
append_count = 0

def append_then_crash(path, receipts):
    global append_count
    real_append(path, receipts)
    append_count += 1
    if append_count == 2:
        os._exit(23)

check_batch_close._append_receipts = append_then_crash
raise SystemExit(check_batch_close.main([
    sys.argv[2], "--batch", "B1",
    "--integrator", "fixture-integrator",
    "--reviewer", "fixture-reviewer",
    "--review-attestation",
    "I reviewed the exact listed candidates and merged snapshot.",
]))
'''
        crashed = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS), str(self.root)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, crashed.returncode, crashed.stdout)
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock").is_dir())

        unchanged = runtime_validation.validate_runtime(self.root)
        self.assertEqual(
            "reconcile-interrupted-write",
            resume.resume_next_action(unchanged, unchanged["errors"]),
        )
        operation = unchanged["_writer_locks"][0]["operation_receipt"]
        self.assertFalse(operation["matching_receipt"])
        self.assertEqual("absent", operation["status"])
        self.assertTrue(
            (self.root / ".cambium/receipts/batch-close.jsonl").is_file())
        self.assertTrue(
            (self.root / ".cambium/receipts/audit-receipts.jsonl").is_file())
        batch_records = [json.loads(line) for line in (
            self.root / ".cambium/receipts/batch-close.jsonl"
        ).read_text(encoding="utf-8").splitlines()]
        self.assertNotIn(
            operation["receipt_id"],
            {record["receipt_id"] for record in batch_records})


class StateMutatingVerifierSlowTests(
        StateMutatingBatchCloseCheckpointCase):
    """Retain the real fail-closed lock path for a hostile verifier."""

    def test_state_mutating_verifier_preserves_runtime_lock(self):
        code, output, errors = _produce_close(self.root)
        self.assertEqual(1, code, output + errors)
        self.assertIn(
            "authoritative state changed while the Closed List ran",
            output,
        )
        self.assertIn(
            "[RECOVERY] writer lock retained", output)
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock").is_dir())
        self.assertFalse(
            (self.root / ".cambium/receipts/batch-close.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
