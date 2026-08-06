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

        page = kblib.make_receipt(
            "fixture_page", "0.9.0", "page_review", "Topics/A.md", "pass",
            "fixture historical page evidence", 1)
        batch = kblib.make_receipt(
            check_queue.MANUAL_ATTESTATION_TOOL,
            check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            check_queue.BATCH_REVIEW_CHECK, "B1", "pass",
            "fixture current in-batch review authorization", 1)
        batch.update({
            "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
            "task_id": "fixture-task",
            "batch_id": "B1",
            "delta_page_receipt_ids": [page["receipt_id"]],
        })
        kblib.write_receipts(
            self.root / ".cambium/receipts/batch.jsonl", [page, batch])
        delta_relative = ".cambium/deltas/B1.yaml"
        delta = {
            "batch": "B1",
            "generated_at": "2026-08-05T00:00:00Z",
            "pages": [{
                "path": "Topics/A.md",
                "authoring_status": "reviewed",
                "gate_receipts": [page["receipt_id"]],
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

    def install_inactive_corpus_plan(self):
        manifest = self.root / "profiles/test-profile/profile.md"
        text = manifest.read_text(encoding="utf-8")
        marker = (
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n")
        self.assertIn(marker, text)
        manifest.write_text(text.replace(
            marker, marker +
            "- `Corpus Planning`: `corpus-planning.yaml`\n", 1),
            encoding="utf-8")
        (manifest.parent / "corpus-planning.yaml").write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: not-applicable\n"
            "  reason: bounded fixture batch has no corpus-wide planning decision\n"
            "artifact_bindings:\n"
            "  global_map: null\n"
            "  capability_matrix: null\n"
            "  gap_register: null\n"
            "capability_scale: []\n"
            "pass_authority:\n"
            "  role_id: null\n"
            "  decision_scope_id: null\n",
            encoding="utf-8")

    def install_configured_corpus_plan(self):
        manifest = self.root / "profiles/test-profile/profile.md"
        text = manifest.read_text(encoding="utf-8")
        marker = (
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n")
        self.assertIn(marker, text)
        manifest.write_text(text.replace(
            marker, marker +
            "- `Profile Scope`: `scope-and-architecture.md`\n"
            "- `Role Registry`: `roles.md`\n"
            "- `Corpus Planning`: `corpus-planning.yaml`\n", 1),
            encoding="utf-8")
        (manifest.parent / "scope-and-architecture.md").write_text(
            "# Scope And Architecture\n\n## Logical Architecture\n\n"
            "| Stable Layer ID | Repository-relative directories | "
            "Single layer responsibility |\n|---|---|---|\n"
            "| `L1` | `Topics` | Canonical fixture topics. |\n",
            encoding="utf-8")
        (manifest.parent / "roles.md").write_text(
            "# Role Registry\n\n## Process Roles\n\n"
            "| Kernel role | Bound actor or system ID/name |\n|---|---|\n"
            "| `stopper` | Fixture authority |\n",
            encoding="utf-8")
        (manifest.parent / "corpus-planning.yaml").write_text(
            "schema_version: 1\n"
            "applicability:\n  state: configured\n  reason: null\n"
            "artifact_bindings:\n"
            "  global_map: planning/global-map.yaml\n"
            "  capability_matrix: planning/capability-matrix.yaml\n"
            "  gap_register: planning/gap-register.yaml\n"
            "capability_scale:\n"
            "  - rank: 0\n    value: Missing\n"
            "    predicate: No canonical owner exists.\n"
            "    target_eligible: false\n"
            "  - rank: 1\n    value: Core\n"
            "    predicate: Core explanation has accepted evidence.\n"
            "    target_eligible: true\n"
            "pass_authority:\n  role_id: stopper\n"
            "  decision_scope_id: corpus-plan-semantic-acceptance\n",
            encoding="utf-8")
        planning = self.root / "planning"
        planning.mkdir()
        (planning / "global-map.yaml").write_text(
            "schema_version: 1\nentries:\n"
            "  - entry_id: E-A\n    layer_id: L1\n"
            "    canonical_markdown_path: Topics/A.md\n"
            "    single_responsibility: Own topic A.\n"
            "  - entry_id: E-B\n    layer_id: L1\n"
            "    canonical_markdown_path: Topics/B.md\n"
            "    single_responsibility: Own topic B.\n"
            "typed_dependencies:\n"
            "  - edge_id: D-1\n    upstream_entry_id: E-A\n"
            "    downstream_entry_id: E-B\n"
            "    relation_type: prerequisite-for\n",
            encoding="utf-8")
        (planning / "capability-matrix.yaml").write_text(
            "schema_version: 1\ncapabilities:\n"
            "  - capability_id: C-1\n"
            "    capability: Explain the fixture topic path.\n"
            "    priority: P0\n    map_entry_ids: [E-A, E-B]\n"
            "    canonical_markdown_paths: [Topics/A.md, Topics/B.md]\n"
            "    current_level: Core\n    target_level: Core\n"
            "    evidence_paths: [Topics/A.md]\n    gap_ids: []\n",
            encoding="utf-8")
        (planning / "gap-register.yaml").write_text(
            "schema_version: 1\ngaps: []\n", encoding="utf-8")

    def test_manifest_hit_requires_current_corpus_plan_child(self):
        self.install_inactive_corpus_plan()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        item = dict(next(row for row in runtime["queue"]["required_queue"]
                         if row["id"] == "B1"))
        item["manifest"] = ["profiles/test-profile/corpus-planning.yaml"]
        snapshot = kblib.repository_snapshot_sha256(self.root)
        outcome = check_batch_close._corpus_plan_close_check(
            self.root, runtime, item, snapshot)
        self.assertTrue(outcome["required"])
        self.assertEqual(["manifest"], outcome["triggers"])
        self.assertEqual([], outcome["errors"])
        self.assertEqual("pass", outcome["receipt"]["result"])
        self.assertEqual("not-applicable",
                         outcome["receipt"]["corpus_plan_applicability"])

    def test_r13_cannot_close_with_not_applicable_corpus_plan(self):
        self.install_inactive_corpus_plan()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        runtime["progress"]["contract"]["selected_route_ids"] = ["R13"]
        item = next(row for row in runtime["queue"]["required_queue"]
                    if row["id"] == "B1")
        outcome = check_batch_close._corpus_plan_close_check(
            self.root, runtime, item,
            kblib.repository_snapshot_sha256(self.root))
        self.assertTrue(outcome["required"])
        self.assertEqual(["R13"], outcome["triggers"])
        self.assertTrue(any("applicability.state=configured" in error
                            for error in outcome["errors"]), outcome)
        self.assertIsNone(outcome["receipt"])

    def test_configured_corpus_plan_child_is_consumed_by_batch_close(self):
        self.install_configured_corpus_plan()
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        rows = [
            json.loads(line)
            for line in (self.root / ".cambium/receipts/batch-close.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        close = next(row for row in rows
                     if row.get("receipt_id") == close_gate)
        self.assertTrue(close["corpus_plan_required"])
        self.assertEqual(["manifest"], close["corpus_plan_triggers"])
        child = next(row for row in rows
                     if row.get("receipt_id") == close["corpus_plan_receipt"])
        self.assertEqual("check_corpus_plan", child["tool"])
        self.assertEqual("1.5.0", child["tool_version"])
        self.assertEqual("configured", child["corpus_plan_applicability"])
        runtime = check_queue.validate_runtime(self.root)
        item = runtime["items_by_id"]["B1"]
        errors = check_queue.close_gate_receipt_errors(
            runtime["current_receipt_catalog"], close_gate,
            item_id="B1", task_id=runtime["queue"]["task_id"],
            queue_revision=runtime["queue"]["queue_revision"],
            queue_state_revision=runtime["queue"]["state_revision"],
            required_queue_sha256=runtime["queue_sha256"],
            coverage_ledger_sha256=runtime["coverage_sha256"],
            progress_ledger_sha256=runtime["progress_sha256"],
            delta_sha256=item["delta_sha256"],
            queue_consistency_receipt=consistency,
            delta_apply_receipt=self.delta_apply_receipt,
            work_spec_path=item["work_spec_path"],
            work_spec_sha256=item["work_spec_sha256"],
            selected_profile_manifest=runtime["queue"][
                "selected_profile_manifest"],
            corpus_plan_required=True,
            corpus_plan_triggers=["manifest"],
            current_repository_snapshot_sha256=
                kblib.repository_snapshot_sha256(self.root),
        )
        self.assertEqual([], errors)

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
        own_records = [record for record in close_records
                       if record.get("tool") == check_batch_close.TOOL]
        self.assertTrue(own_records)
        self.assertEqual(
            {check_batch_close.TOOL_VERSION},
            {record.get("tool_version") for record in own_records})
        self.assertEqual(
            {check_batch_close.GATE_ID},
            {record.get("gate_id") for record in own_records})
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
        close_record = next(
            record for record in close_records
            if record.get("receipt_id") == close_gate)
        self.assertIn("work_spec_path", close_record)
        self.assertIn("work_spec_sha256", close_record)
        self.assertIsNone(close_record["work_spec_path"])
        self.assertIsNone(close_record["work_spec_sha256"])
        self.transition(
            "closed", "--gate-receipt", consistency,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply)
        self.assertEqual("closed", self.queue()["required_queue"][0]["state"])
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_complex_work_spec_stability_guard_detects_byte_change(self):
        relative = ".cambium/work_specs/B1.yaml"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "---\nschema_version: 1\nbatch_id: B1\nmanifest:\n"
            "  - Topics/A.md\n---\n\n# Work\n"
        )
        path.write_text(text, encoding="utf-8")
        item = {
            "work_spec_path": relative,
            "work_spec_sha256": kblib.sha256_file(path),
        }
        check_batch_close._assert_work_spec_unchanged(self.root, item)
        path.write_text(text + "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(
                check_batch_close.ReceiptPublicationUncertain,
                "Batch Work Spec changed"):
            check_batch_close._assert_work_spec_unchanged(self.root, item)

    def test_simple_batch_close_receipt_must_bind_explicit_null_work_spec(self):
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        runtime = check_queue.validate_runtime(self.root)
        item = runtime["items_by_id"]["B1"]

        for mode in ("missing", "forged"):
            with self.subTest(mode=mode):
                catalog = {
                    receipt_id: (path, dict(receipt))
                    for receipt_id, (path, receipt) in
                    runtime["receipt_catalog"].items()
                }
                receipt = catalog[close_gate][1]
                if mode == "missing":
                    receipt.pop("work_spec_path", None)
                    receipt.pop("work_spec_sha256", None)
                else:
                    receipt["work_spec_path"] = \
                        ".cambium/work_specs/forged.yaml"
                    receipt["work_spec_sha256"] = "sha256:" + "a" * 64
                errors = check_queue.close_gate_receipt_errors(
                    catalog, close_gate,
                    item_id="B1", task_id=runtime["queue"]["task_id"],
                    queue_revision=runtime["queue"]["queue_revision"],
                    queue_state_revision=runtime["queue"]["state_revision"],
                    required_queue_sha256=runtime["queue_sha256"],
                    coverage_ledger_sha256=runtime["coverage_sha256"],
                    progress_ledger_sha256=runtime["progress_sha256"],
                    delta_sha256=item["delta_sha256"],
                    queue_consistency_receipt=consistency,
                    delta_apply_receipt=self.delta_apply_receipt,
                    work_spec_path=None, work_spec_sha256=None,
                )
                self.assertTrue(any("work_spec_" in error
                                    for error in errors), errors)

    def test_close_evidence_from_prior_work_spec_binding_is_not_reusable(self):
        completed = self.batch_close(
            "--accept-candidate-type", "check_vocab:frontmatter-missing")
        self.assertEqual(0, completed.returncode, completed.stdout)
        close_gate = self.output_value(completed.stdout, "close_gate_receipt")
        consistency = self.output_value(
            completed.stdout, "queue_consistency_receipt")
        runtime = check_queue.validate_runtime(self.root)
        item = runtime["items_by_id"]["B1"]
        errors = check_queue.close_gate_receipt_errors(
            runtime["receipt_catalog"], close_gate,
            item_id="B1", task_id=runtime["queue"]["task_id"],
            queue_revision=runtime["queue"]["queue_revision"],
            queue_state_revision=runtime["queue"]["state_revision"],
            required_queue_sha256=runtime["queue_sha256"],
            coverage_ledger_sha256=runtime["coverage_sha256"],
            progress_ledger_sha256=runtime["progress_sha256"],
            delta_sha256=item["delta_sha256"],
            queue_consistency_receipt=consistency,
            delta_apply_receipt=self.delta_apply_receipt,
            work_spec_path=".cambium/work_specs/B1.yaml",
            work_spec_sha256="sha256:" + "a" * 64,
        )
        self.assertTrue(any("work_spec_path" in error or
                            "work_spec_sha256" in error
                            for error in errors), errors)

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

    def set_override_rows(self, rows):
        manifest = self.root / "profiles/test-profile/profile.md"
        text = manifest.read_text(encoding="utf-8")
        head, _, _ = text.partition("\n## Execution Default Overrides\n")
        manifest.write_text(
            head + "\n## Execution Default Overrides\n\n"
            "| Override item ID from the registry | Non-default profile value |\n"
            "|---|---|\n" + rows, encoding="utf-8")
        return {"queue": {
            "selected_profile_manifest": "profiles/test-profile/profile.md",
        }}

    def test_priority_quotas_read_the_shared_override_table(self):
        runtime = self.set_override_rows("")
        self.assertEqual((15.0, 35.0),
                         check_batch_close._priority_quotas(self.root, runtime))
        runtime = self.set_override_rows(
            "| `concurrency_cap` | `4` |\n"
            "| `priority_quota.P0` | `20%` |\n"
            "| `priority_quota.P1` | `40` |\n")
        self.assertEqual((20.0, 40.0),
                         check_batch_close._priority_quotas(self.root, runtime))
        manifest_text = (
            self.root / "profiles/test-profile/profile.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            {"concurrency_cap": "4", "priority_quota.P0": "20%",
             "priority_quota.P1": "40"},
            kblib.profile_execution_default_overrides(manifest_text))

    def test_priority_quota_override_still_fails_closed_on_a_bad_value(self):
        runtime = self.set_override_rows("| `priority_quota.P0` | `many` |\n")
        with self.assertRaises(ValueError) as caught:
            check_batch_close._priority_quotas(self.root, runtime)
        self.assertIn("not a numeric percent", str(caught.exception))
        runtime = self.set_override_rows("| `priority_quota.P1` | `140` |\n")
        with self.assertRaises(ValueError) as caught:
            check_batch_close._priority_quotas(self.root, runtime)
        self.assertIn("outside 0..100", str(caught.exception))

    def test_override_reader_ignores_fenced_examples_and_other_sections(self):
        manifest_text = (
            "# Profile\n\n"
            "## Execution Default Overrides\n\n"
            "```text\n"
            "| `concurrency_cap` | `99` |\n"
            "```\n\n"
            "| Override item ID from the registry | Non-default profile value |\n"
            "|---|---|\n"
            "| `concurrency_cap` | `7` |\n"
            "| `maintenance.incoming_retarget_divisor` | `a \\| b` |\n\n"
            "## Implemented Slots\n\n"
            "| `priority_quota.P0` | `99` |\n"
        )
        self.assertEqual(
            {"concurrency_cap": "7",
             "maintenance.incoming_retarget_divisor": "a | b"},
            kblib.profile_execution_default_overrides(manifest_text))

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
