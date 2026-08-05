import io
import json
import shlex
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS))

import check_batch_close
import check_queue
import kblib


class CheckBatchCloseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        for name in ("deltas", "receipts", "reports"):
            (self.root / ".cambium" / name).mkdir(exist_ok=True)
        self.install_profile_and_tools()
        self.prepare_applied_batch()

    def tearDown(self):
        self.temporary.cleanup()

    def run_tool(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def install_profile_and_tools(self):
        manifest = self.root / "profiles/test-profile/profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8") +
            "\n## Implemented Slots\n\n"
            "- `Registered Scan Registry`: `registries/registered-scans.md`\n"
            "\n## Execution Default Overrides\n\n"
            "| Override item ID from the registry | Non-default profile value |\n"
            "|---|---|\n",
            encoding="utf-8",
        )
        registry = manifest.parent / "registries/registered-scans.md"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            "# Registered Scan Registry\n\n## Scan Registrations\n\n"
            "| Stable Scan ID | Activation role | Whole-corpus scope/root | "
            "Deterministic verifier command/path | Candidate predicate/boundary | "
            "Judgment Item ID reference |\n"
            "|---|---|---|---|---|---|\n"
            "| `fixture-residuals` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `python3 Tools/fixture_residual.py . "
            "--scan-id fixture-residuals` | candidate-only | fixture-item |\n",
            encoding="utf-8",
        )
        tools = self.root / "Tools"
        tools.mkdir()
        shutil.copy2(TOOLS / "kblib.py", tools / "kblib.py")
        (tools / "fixture_residual.py").write_text(
            "#!/usr/bin/env python3\n"
            "import argparse, os, sys\n"
            "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
            "import kblib\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('root')\n"
            "p.add_argument('--scan-id', required=True)\n"
            "p.add_argument('--receipts')\n"
            "a=p.parse_args()\n"
            "r=kblib.make_receipt('fixture_residual','1.0.0',"
            "'residual-content-summary',a.root,'pass',"
            "'fixture residual scan passed',1)\n"
            "r['scan_id']=a.scan_id\n"
            "kblib.write_receipts(a.receipts,[r])\n",
            encoding="utf-8",
        )
        (tools / "vocab.yaml").write_text(
            "schema_version: 1\n"
            "composition_policy: fixture\n"
            "fields:\n"
            "  priority:\n"
            "    owner: fixture\n"
            "    values:\n"
            "      - P0\n"
            "      - P1\n"
            "      - P2\n",
            encoding="utf-8",
        )

    def queue(self):
        return kblib.load_yaml_file(self.root / check_queue.QUEUE_PATH)

    def transition(self, transition, *evidence):
        queue = self.queue()
        completed = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", transition,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--apply", *evidence,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)

    def prepare_applied_batch(self):
        ready_path = ".cambium/receipts/ready.jsonl"
        ready = self.run_tool(
            "check_queue.py", "--require-ready", "B1",
            "--receipts", ready_path)
        self.assertEqual(0, ready.returncode, ready.stdout)
        ready_id = json.loads((self.root / ready_path).read_text(
            encoding="utf-8"))["receipt_id"]
        self.transition("open", "--gate-receipt", ready_id)

        batch = kblib.make_receipt(
            "fixture_batch", "1.0.0", "batch_gate", "B1", "pass",
            "fixture in-batch gate", 1)
        kblib.write_receipts(
            self.root / ".cambium/receipts/batch.jsonl", [batch])
        delta_relative = ".cambium/deltas/B1.yaml"
        delta = {
            "batch": "B1",
            "generated_at": "2026-08-05T00:00:00Z",
            "pages": [{
                "path": "Topics/A.md",
                "authoring_status": "reviewed",
                "gate_receipts": [batch["receipt_id"]],
            }],
            "open_gaps_added": [],
            "open_gaps_closed": [],
            "next_batch_updates": [],
            "watermark_advance": None,
        }
        (self.root / delta_relative).write_text(
            kblib.canonical_yaml(delta), encoding="utf-8")
        self.transition(
            "merge-ready", "--delta-path", delta_relative,
            "--batch-receipt", batch["receipt_id"])

        applied_path = ".cambium/receipts/applied.jsonl"
        applied = subprocess.run(
            [
                sys.executable, str(TOOLS / "apply_delta.py"),
                check_queue.COVERAGE_PATH, delta_relative,
                "--root", str(self.root),
                "--expected-coverage-sha256",
                kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
                "--expected-queue-sha256",
                kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
                "--actor-role", "integrator", "--receipts", applied_path,
                "--apply",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, applied.returncode, applied.stdout)
        self.delta_apply_receipt = json.loads(
            (self.root / applied_path).read_text(encoding="utf-8"))[
                "receipt_id"]

    def batch_close(self, *extra):
        return self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "fixture-integrator",
            "--reviewer", "fixture-reviewer",
            "--review-attestation",
            "I reviewed the exact listed candidates and merged snapshot.",
            *extra,
        )

    @staticmethod
    def output_value(output, name):
        prefix = name + "="
        return next(line[len(prefix):] for line in output.splitlines()
                    if line.startswith(prefix))

    def test_production_cli_generates_bundle_consumed_by_close(self):
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        delta_apply = self.output_value(completed.stdout,
                                       "delta_apply_receipt")
        self.assertEqual(self.delta_apply_receipt, delta_apply)
        close_records = [json.loads(line) for line in
                         (self.root / ".cambium/receipts/batch-close.jsonl")
                         .read_text(encoding="utf-8").splitlines()]
        consistency_record = next(
            record for record in close_records
            if record.get("receipt_id") == consistency)
        self.assertEqual("check_queue", consistency_record["tool"])
        self.assertEqual(check_queue.TOOL_VERSION,
                         consistency_record["tool_version"])
        self.assertEqual("consistency",
                         consistency_record["queue_check_mode"])
        self.assertEqual(
            kblib.repository_snapshot_sha256(self.root),
            consistency_record["repository_snapshot_sha256"])
        self.transition(
            "closed", "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply)
        self.assertEqual("closed", self.queue()["required_queue"][0]["state"])
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_resume_recovers_published_bundle_when_producer_stdout_is_lost(self):
        published = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, published.returncode, published.stdout)
        consistency = self.output_value(
            published.stdout, "queue_consistency_receipt")
        close_gate = self.output_value(published.stdout, "close_gate_receipt")

        # Deliberately recover from durable state only.  None of the values
        # parsed from the producer stdout are supplied to the resume command.
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        expected_action = "close-applied-batch:B1:%s:%s:%s" % (
            consistency, close_gate, self.delta_apply_receipt)
        self.assertIn(
            "batch_close_recovery.status=ready-to-close batch=B1",
            resumed.stdout)
        self.assertIn(
            "batch_close_recovery.queue_consistency_receipt=%s" %
            consistency, resumed.stdout)
        self.assertIn(
            "batch_close_recovery.close_gate_receipt=%s" % close_gate,
            resumed.stdout)
        self.assertIn(
            "batch_close_recovery.delta_apply_receipt=%s" %
            self.delta_apply_receipt, resumed.stdout)
        self.assertIn("next_action=%s" % expected_action, resumed.stdout)

        command = next(
            line.split("=", 1)[1]
            for line in resumed.stdout.splitlines()
            if line.startswith(
                "  batch_close_recovery.update_queue_command="))
        closed = subprocess.run(
            shlex.split(command), cwd=str(TOOLS.parent), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, closed.returncode, closed.stdout)
        self.assertEqual("closed", self.queue()["required_queue"][0]["state"])
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_resume_requires_close_gate_when_only_apply_receipt_exists(self):
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("batch_close_recovery.status=gate-required batch=B1",
                      resumed.stdout)
        self.assertIn("batch_close_recovery.update_queue_command=none",
                      resumed.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      resumed.stdout)

    def test_resume_rejects_close_bundle_after_repository_snapshot_changes(self):
        published = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, published.returncode, published.stdout)
        close_gate = self.output_value(published.stdout, "close_gate_receipt")
        topic = self.root / "Topics/A.md"
        topic.write_text(
            topic.read_text(encoding="utf-8") + "\nchanged after gate\n",
            encoding="utf-8")

        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("batch_close_recovery.status=gate-required batch=B1",
                      resumed.stdout)
        self.assertIn("batch_close_recovery.compatible=none stale=%s" %
                      close_gate, resumed.stdout)
        self.assertIn("next_action=run-batch-close-gate:B1",
                      resumed.stdout)

    def test_resume_selects_latest_of_multiple_current_close_bundles(self):
        first = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, first.returncode, first.stdout)
        first_close = self.output_value(first.stdout, "close_gate_receipt")
        time.sleep(1.1)
        second = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, second.returncode, second.stdout)
        second_consistency = self.output_value(
            second.stdout, "queue_consistency_receipt")
        second_close = self.output_value(second.stdout, "close_gate_receipt")

        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn(
            "batch_close_recovery.compatible=%s,%s stale=none" %
            (first_close, second_close), resumed.stdout)
        self.assertIn(
            "batch_close_recovery.close_gate_receipt=%s" % second_close,
            resumed.stdout)
        self.assertIn(
            "next_action=close-applied-batch:B1:%s:%s:%s" % (
                second_consistency, second_close, self.delta_apply_receipt),
            resumed.stdout)

    def test_candidates_require_exact_id_or_type_disposition(self):
        completed = self.batch_close()
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("lack an explicit ID/type disposition", completed.stdout)
        self.assertIn("type=check_vocab:frontmatter-missing", completed.stdout)
        records = []
        for path in (self.root / ".cambium/receipts").glob("*.jsonl"):
            records.extend(json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip())
        attempts = [record for record in records
                    if record.get("tool") == "check_batch_close"]
        self.assertEqual(1, len(attempts))
        self.assertEqual("fail", attempts[0]["result"])
        self.assertNotIn("closed_list_evidence", attempts[0])
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_plain_json_and_scalar_json_fences_are_not_graph_inputs(self):
        ordinary = self.root / "application-data.json"
        ordinary.write_text("42", encoding="utf-8")
        example = self.root / "JSON Example.md"
        example.write_text(
            "# JSON Example\n\n```json\n42\n```\n", encoding="utf-8")

        first, first_json = check_batch_close._markdown_graph_projection(
            self.root)
        first_check = check_batch_close._graph_and_basename_check(self.root)
        ordinary.write_text('"a different scalar"', encoding="utf-8")
        example.write_text(
            "# JSON Example\n\n```json\n\"changed\"\n```\n", encoding="utf-8")
        second, second_json = check_batch_close._markdown_graph_projection(
            self.root)
        second_check = check_batch_close._graph_and_basename_check(self.root)

        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertEqual(first_check["details"], second_check["details"])
        self.assertEqual([], first_check["errors"])
        self.assertEqual([], second_check["errors"])
        self.assertNotIn("application-data.json", first_json)

    def test_graph_projection_is_stable_and_duplicate_basename_is_candidate(self):
        for directory in ("z-last", "a-first"):
            path = self.root / directory / "Same.md"
            path.parent.mkdir()
            path.write_text("# Same\n", encoding="utf-8")
        source = self.root / "Graph Source.md"
        source.write_text(
            "# Graph Source\n\n[[z-last/Same]] [[Missing]] [[Same]]\n",
            encoding="utf-8")

        first, first_json = check_batch_close._markdown_graph_projection(
            self.root)
        second, second_json = check_batch_close._markdown_graph_projection(
            self.root)
        result = check_batch_close._graph_and_basename_check(self.root)

        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertEqual(
            sorted(node["path"] for node in first["nodes"]),
            [node["path"] for node in first["nodes"]])
        self.assertEqual(
            ["z-last/Same"],
            [edge["resolved_target"] for edge in first["resolved_edges"]
             if edge["source"] == "Graph Source"])
        self.assertEqual(
            ["ambiguous", "missing"],
            sorted(edge["status"] for edge in first["unresolved_edges"]
                   if edge["source"] == "Graph Source"))
        self.assertEqual([], result["errors"])
        duplicate = next(
            candidate for candidate in result["candidates"]
            if candidate["check"] == "duplicate-markdown-basename" and
            candidate["target"] == "Same.md")
        self.assertIn("a-first/Same.md", duplicate["details"])
        self.assertIn("z-last/Same.md", duplicate["details"])

    def test_same_reviewer_and_integrator_fail_before_receipts(self):
        completed = self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "same", "--reviewer", "same",
            "--review-attestation", "Independent review statement.")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("must use different declared labels", completed.stdout)
        self.assertFalse((self.root / ".cambium/receipts/batch-close.jsonl").exists())

    def test_registered_check_cannot_mutate_around_a_self_reported_pass(self):
        script = self.root / "Tools/fixture_residual.py"
        script.write_text(
            script.read_text(encoding="utf-8") +
            "open(os.path.join(a.root,'MUTATED.txt'),'w',encoding='utf-8')"
            ".write('changed during gate')\n",
            encoding="utf-8",
        )
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("repository content changed while the Closed List ran",
                      completed.stdout)
        records = [json.loads(line) for line in
                   (self.root / ".cambium/receipts/batch-close.jsonl")
                   .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(records))
        self.assertEqual("fail", records[0]["result"])
        self.assertNotIn("closed_list_evidence", records[0])

    def _install_authoritative_state_mutating_verifier(self, exit_code):
        script = self.root / "Tools/fixture_residual.py"
        script.write_text(
            script.read_text(encoding="utf-8") +
            "with open(os.path.join(a.root,'.cambium/state/"
            "coverage_ledger.yaml'),'a',encoding='utf-8') as fh:\n"
            "    fh.write('\\n')\n" +
            ("raise SystemExit(%d)\n" % exit_code if exit_code else ""),
            encoding="utf-8",
        )

    def _assert_state_mutating_verifier_is_uncertain(self, exit_code):
        self._install_authoritative_state_mutating_verifier(exit_code)
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn(
            "authoritative state changed while the Closed List ran",
            completed.stdout)
        self.assertIn(
            "[RECOVERY] writer lock retained", completed.stdout)
        self.assertTrue(
            (self.root / ".cambium/tmp/state-writer.lock").is_dir())
        self.assertFalse(
            (self.root / ".cambium/receipts/batch-close.jsonl").exists())

    def test_failing_verifier_that_mutates_state_preserves_runtime_lock(self):
        self._assert_state_mutating_verifier_is_uncertain(1)

    def test_passing_verifier_that_mutates_state_preserves_runtime_lock(self):
        self._assert_state_mutating_verifier_is_uncertain(0)

    def test_uncertain_append_preserves_runtime_lock(self):
        target = self.root / ".cambium/receipts/uncertain.jsonl"
        receipt = kblib.make_receipt(
            "fixture", "1", "fixture", ".", "pass", "fixture", 1)
        with self.assertRaises(check_batch_close.ReceiptPublicationUncertain):
            with kblib.runtime_write_lock(self.root):
                with mock.patch.object(
                        kblib, "write_receipts_observed",
                        return_value=("uncertain", OSError("partial"), None)):
                    check_batch_close._append_receipts(target, [receipt])
        self.assertTrue((self.root / ".cambium/tmp/state-writer.lock").is_dir())

    def test_crashed_pass_bundle_recovery_detects_later_content_change(self):
        program = r'''
import os
import sys

sys.path.insert(0, sys.argv[1])
import check_batch_close

real_append = check_batch_close._append_receipts

def append_then_crash(path, receipts):
    real_append(path, receipts)
    if len(receipts) > 1:
        os._exit(23)

check_batch_close._append_receipts = append_then_crash
raise SystemExit(check_batch_close.main([
    sys.argv[2], "--batch", "B1",
    "--integrator", "fixture-integrator",
    "--reviewer", "fixture-reviewer",
    "--review-attestation",
    "I reviewed the exact listed candidates and merged snapshot.",
    "--accept-candidate-type", "check_vocab:frontmatter-missing",
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

        unchanged = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, unchanged.returncode, unchanged.stdout)
        self.assertIn("batch_close_recovery.status=writer-lock batch=none",
                      unchanged.stdout)
        self.assertIn("batch_close_recovery.update_queue_command=none",
                      unchanged.stdout)
        self.assertIn("next_action=reconcile-interrupted-write",
                      unchanged.stdout)
        self.assertIn('"matching_receipt": true', unchanged.stdout)
        self.assertIn(
            '"repository_snapshot": {"current_sha256": "sha256:',
            unchanged.stdout,
        )
        self.assertIn('"status": "matching"', unchanged.stdout)

        topic = self.root / "Topics/A.md"
        topic.write_text(
            topic.read_text(encoding="utf-8") +
            "\nchanged after interrupted close evidence\n",
            encoding="utf-8",
        )
        changed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, changed.returncode, changed.stdout)
        self.assertIn('"matching_receipt": false', changed.stdout)
        self.assertIn('"status": "semantic-mismatch"', changed.stdout)
        self.assertIn(
            '"mismatched_fields": '
            '["current_repository_snapshot_sha256"]',
            changed.stdout,
        )
        self.assertIn('"status": "changed"', changed.stdout)
        self.assertIn("next_action=reconcile-interrupted-write",
                      changed.stdout)


if __name__ == "__main__":
    unittest.main()
