import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
SYNTHETIC_PROFILE = TOOLS / "tests" / "fixtures" / "synthetic_profile"
sys.path.insert(0, str(TOOLS))

import check_queue
import kblib
import maintenance_candidates


class RequiredQueueEndToEndTests(unittest.TestCase):
    """Exercise the public control path, not internal state shortcuts."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        for name in ("deltas", "receipts", "reports"):
            (self.root / ".cambium" / name).mkdir(exist_ok=True)

    def tearDown(self):
        self.temporary.cleanup()

    def run_tool(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(TOOLS / name), str(self.root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def assert_resume_envelope(self, completed, next_action):
        """Assert the one-command restart contract, not only its action token."""
        output = completed.stdout
        result = check_queue.validate_runtime(self.root)
        for expected in (
                "task_id=fixture-task",
                'objective="Complete fixture Required Queue batches with durable evidence."',
                'exclusions=["Do not modify profile policy."]',
                "live.coverage_sha256=%s" % result.get("coverage_sha256"),
                "live.progress_sha256=%s" % result.get("progress_sha256"),
                "live.required_queue_sha256=%s" % result.get("queue_sha256"),
                "checkpoint.recorded_at=",
                "checkpoint.summary=",
                "checkpoint.binding=",
        ):
            self.assertIn(expected, output)
        self.assertTrue(any(
            line.startswith("  deltas=") or line.startswith("  delta=")
            for line in output.splitlines()), output)
        self.assertTrue(any(
            line.startswith("  locks=") or line.startswith("  lock=")
            for line in output.splitlines()), output)
        actions = [line for line in output.splitlines()
                   if line.startswith("next_action=")]
        self.assertEqual(["next_action=%s" % next_action], actions, output)

    def queue(self):
        return kblib.load_yaml_file(self.root / check_queue.QUEUE_PATH)

    def write_batch_receipt(self, batch_id, page_receipt_id):
        receipt = kblib.make_receipt(
            check_queue.MANUAL_ATTESTATION_TOOL,
            check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            check_queue.BATCH_REVIEW_CHECK, batch_id,
            "pass", "fixture batch evidence", 1 if batch_id == "B1" else 2,
        )
        receipt.update({
            "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
            "task_id": "fixture-task", "batch_id": batch_id,
            "delta_page_receipt_ids": [page_receipt_id],
        })
        path = self.root / ".cambium/receipts/batch-evidence.jsonl"
        kblib.write_receipts(path, [receipt])
        return receipt["receipt_id"]

    def ready_receipt(self, batch_id):
        relative = ".cambium/receipts/ready-%s.jsonl" % batch_id
        result = self.run_tool(
            "check_queue.py", "--require-ready", batch_id,
            "--receipts", relative,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        record = json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])
        return record["receipt_id"]

    def close_gate_receipt(self, batch_id, consistency_receipt):
        queue = self.queue()
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
        records = []
        integrator_id = "fixture-integrator"
        reviewer_id = "fixture-reviewer"
        for field in check_queue.CLOSED_LIST_EVIDENCE_FIELDS:
            receipt_id = "audit-e2e-closed-list-%s-r%d-%s" % (
                batch_id, revision, field)
            records.append({
                "receipt_id": receipt_id,
                "tool": "check_batch_close",
                "tool_version": check_queue.BATCH_CLOSE_TOOL_VERSION,
                "check": "closed_list_%s" % field,
                "target": ".",
                "batch_id": batch_id,
                "task_id": queue["task_id"],
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "result": "pass",
                "invalidated_by": None,
                "merged_snapshot_sha256": merged_snapshot_sha256,
                "candidate_evidence": [],
            })
            evidence[field] = receipt_id
        attestation_id = "audit-e2e-review-attestation-%s-r%d" % (
            batch_id, revision)
        records.append({
            "receipt_id": attestation_id,
            "tool": "check_batch_close",
            "tool_version": check_queue.BATCH_CLOSE_TOOL_VERSION,
            "check": "batch_global_review_attestation",
            "target": batch_id,
            "batch_id": batch_id,
            "task_id": queue["task_id"],
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "result": "pass",
            "invalidated_by": None,
            "checked_at": "2026-08-04T02:30:00Z",
            "details": "fixture independent review attestation",
            "merged_snapshot_sha256": merged_snapshot_sha256,
            "accepted_candidate_ids": [],
            "accepted_candidate_types": [],
            "candidate_dispositions": [],
        })
        global_review_id = "audit-e2e-global-review-%s-r%d" % (
            batch_id, revision)
        records.append({
            "receipt_id": global_review_id,
            "tool": "check_batch_close",
            "tool_version": check_queue.BATCH_CLOSE_TOOL_VERSION,
            "check": "batch_global_review",
            "target": batch_id,
            "batch_id": batch_id,
            "task_id": queue["task_id"],
            "integrator_id": integrator_id,
            "reviewer_id": reviewer_id,
            "result": "pass",
            "invalidated_by": None,
            "merged_snapshot_sha256": merged_snapshot_sha256,
            "reviewer_attestation_receipt": attestation_id,
            "closed_list_evidence": evidence,
        })
        close_id = "audit-e2e-batch-close-%s-r%d" % (batch_id, revision)
        records.append({
            "receipt_id": close_id,
            "tool": "check_batch_close",
            "tool_version": check_queue.BATCH_CLOSE_TOOL_VERSION,
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
            "corpus_plan_required": False,
            "corpus_plan_triggers": [],
            "corpus_plan_receipt": None,
            "work_spec_path": item["work_spec_path"],
            "work_spec_sha256": item["work_spec_sha256"],
            "merged_snapshot_sha256": merged_snapshot_sha256,
            "reviewer_attestation_receipt": attestation_id,
            "global_review_receipt": global_review_id,
            "closed_list_evidence": evidence,
        })
        kblib.write_receipts(
            self.root / ".cambium/receipts/close-gates.jsonl", records)
        return close_id

    def transition(self, batch_id, transition, *evidence):
        queue = self.queue()
        result = self.run_tool(
            "update_queue.py", "--id", batch_id,
            "--transition", transition,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--apply", *evidence,
        )
        self.assertEqual(0, result.returncode, result.stdout)

    def task_transition(self, transition, *evidence):
        result = self.run_tool(
            "update_task.py", "--transition", transition,
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--apply", *evidence,
        )
        self.assertEqual(0, result.returncode, result.stdout)

    def use_maintenance_completion(self):
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        progress["contract"]["completion_semantics"] = "maintenance"
        progress["contract"]["completion_gate"] = (
            "maintenance budget manifest closed AND ledger advanced AND "
            "watermark advanced AND remaining_required_work_units=0 AND "
            "all applicable batch gates persisted"
        )
        progress["terminal_audit"] = {
            "state": "not-applicable",
            "terminal_proof_path": None,
            "terminal_proof_sha256": None,
            "terminal_proof_receipt": None,
            "queue_check_receipt": None,
        }
        progress["maintenance_completion"] = {
            "state": "pending",
            "completion_gate_receipt": None,
            "budget_manifest_receipt": None,
            "ledger_advance_receipt": None,
            "watermark_advance_receipt": None,
        }
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        candidates = []
        for page in coverage["pages"]:
            path = page["path"]
            candidates.append({
                "candidate_id":
                    maintenance_candidates.candidate_id_for_path(path),
                "object_path": path,
                "source_kinds": ["freshness"],
                "priority": page["priority"],
                "previous_deferred_runs": 0,
                "consecutive_deferred_runs": 0,
                "reentered_after_terminal": False,
                "selection": "selected",
                "disposition": None,
                "disposition_reason": None,
            })
        coverage["maintenance_candidates"] = candidates
        coverage_path.write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        coverage_sha = kblib.sha256_file(coverage_path)
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        for receipt in receipts:
            if receipt.get("receipt_id") == "audit-fixture-initial-queue":
                receipt["contract_sha256"] = \
                    check_queue._contract_sha256(progress)
                receipt["before_coverage_sha256"] = coverage_sha
                receipt["after_coverage_sha256"] = coverage_sha
        receipt_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def write_maintenance_evidence(self):
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        queue = result["queue"]
        contract = result["progress"]["contract"]
        identity = {
            "task_id": queue["task_id"],
            "scope_version": contract["scope_version"],
            "standards_version": contract["standards_version"],
            "selected_profile_manifest":
                contract["selected_profile_manifest"],
        }

        budget_path = ".cambium/receipts/maintenance-budget.yaml"
        budget_receipt = kblib.make_receipt(
            "fixture_maintenance", "1.0.0", "maintenance_budget_manifest",
            budget_path, "pass", "closed bounded maintenance manifest", 1,
        )
        candidates = result["coverage"]["maintenance_candidates"]
        candidate_errors, candidate_context = \
            maintenance_candidates.validate_candidates(
                self.root, candidates, validate_prior=False)
        self.assertEqual([], candidate_errors)
        selected_objects = candidate_context["selected_objects"]
        run_id = "fixture-maintenance-run-1"
        required_batch_ids = [
            item["id"] for item in sorted(
                queue["required_queue"], key=lambda value: value["order"])
        ]
        budget = dict(identity)
        budget.update({
            "schema_version": 2,
            "run_id": run_id,
            "previous_maintenance_completion_receipt": None,
            "budget_unit": "pages",
            "budget_limit": len(selected_objects),
            "consumed_hours": None,
            "candidates": candidates,
            "selected_candidate_ids": candidate_context["selected_ids"],
            "deferred_candidate_ids": candidate_context["deferred_ids"],
            "selected_objects": selected_objects,
            "required_batch_ids": required_batch_ids,
            "deferred_count": 0,
            "open_items": 0,
            "state": "closed",
            "closed_at": budget_receipt["checked_at"],
        })
        (self.root / budget_path).write_text(
            kblib.canonical_yaml(budget), encoding="utf-8")
        budget_receipt.update(identity)
        budget_receipt.update({
            "budget_manifest_path": budget_path,
            "budget_manifest_sha256": kblib.sha256_file(
                self.root / budget_path),
            "budget_manifest_state": "closed",
            "manifest_open_items": 0,
            "budget_manifest_closed_at": budget["closed_at"],
            "maintenance_run_id": run_id,
            "previous_maintenance_completion_receipt": None,
            "maintenance_candidate_state_sha256":
                candidate_context["candidate_state_sha256"],
            "selected_candidate_ids": candidate_context["selected_ids"],
            "deferred_candidate_ids": candidate_context["deferred_ids"],
        })

        coverage = result["coverage"]
        ledger_receipt = kblib.make_receipt(
            "fixture_maintenance", "1.0.0", "maintenance_ledger_advanced",
            check_queue.COVERAGE_PATH, "pass", "Coverage Ledger advanced", 2,
        )
        ledger_receipt.update(identity)
        ledger_receipt.update({
            "advanced": True,
            "coverage_ledger_path": check_queue.COVERAGE_PATH,
            "before_coverage_sha256": "sha256:" + "0" * 64,
            "after_coverage_sha256": result["coverage_sha256"],
            "coverage_updated_at": coverage["updated_at"],
            "maintenance_run_id": run_id,
            "previous_maintenance_completion_receipt": None,
            "before_maintenance_candidate_state_sha256":
                maintenance_candidates.candidate_state_sha256([]),
            "after_maintenance_candidate_state_sha256":
                candidate_context["candidate_state_sha256"],
        })

        watermark_path = "Tools/state/watermark.yaml"
        (self.root / "Tools/state").mkdir(parents=True, exist_ok=True)
        watermark_receipt = kblib.make_receipt(
            "fixture_maintenance", "1.0.0",
            "maintenance_watermark_advanced", watermark_path, "pass",
            "watermark advanced", 3,
        )
        watermark = {
            "updated_at": watermark_receipt["checked_at"],
            "last_run_id": run_id,
            "last_batch_id": required_batch_ids[-1],
        }
        (self.root / watermark_path).write_text(
            kblib.canonical_yaml(watermark), encoding="utf-8")
        watermark_receipt.update(identity)
        watermark_receipt.update({
            "advanced": True,
            "watermark_path": watermark_path,
            "before_watermark_sha256": "sha256:" + "1" * 64,
            "after_watermark_sha256": kblib.sha256_file(
                self.root / watermark_path),
            "watermark_updated_at": watermark["updated_at"],
            "watermark_run_id": watermark["last_run_id"],
            "watermark_batch_id": watermark["last_batch_id"],
            "maintenance_run_id": run_id,
        })
        evidence_path = \
            self.root / ".cambium/receipts/maintenance-evidence.jsonl"
        kblib.write_receipts(
            evidence_path,
            [budget_receipt, ledger_receipt, watermark_receipt],
        )
        return tuple(receipt["receipt_id"] for receipt in
                     (budget_receipt, ledger_receipt, watermark_receipt))

    def rebind_maintenance_budget_receipt(self, budget_receipt_id):
        evidence_path = \
            self.root / ".cambium/receipts/maintenance-evidence.jsonl"
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        receipts = [json.loads(line) for line in evidence_path.read_text(
            encoding="utf-8").splitlines()]
        receipt = next(value for value in receipts
                       if value["receipt_id"] == budget_receipt_id)
        receipt["budget_manifest_sha256"] = kblib.sha256_file(budget_path)
        evidence_path.write_text(
            "".join(json.dumps(value) + "\n" for value in receipts),
            encoding="utf-8",
        )

    def write_delta(self, batch_id, object_path, receipt_id):
        delta = {
            "batch": batch_id,
            "generated_at": "2026-08-04T00:00:00Z",
            "pages": [{
                "path": object_path,
                "authoring_status": "reviewed",
                "gate_receipts": [receipt_id],
            }],
            "open_gaps_added": [],
            "open_gaps_closed": [],
            "next_batch_updates": [],
            "watermark_advance": None,
        }
        relative = ".cambium/deltas/%s.yaml" % batch_id
        (self.root / relative).write_text(
            kblib.canonical_yaml(delta), encoding="utf-8")
        return relative

    def install_terminal_proof_environment(self):
        shutil.copytree(REPOSITORY / "kernel", self.root / "kernel")
        (self.root / "profiles").mkdir(exist_ok=True)
        shutil.copy2(
            REPOSITORY / "profiles/README.md",
            self.root / "profiles/README.md",
        )
        target_profile = self.root / "profiles/test-profile"
        shutil.copytree(SYNTHETIC_PROFILE, target_profile, dirs_exist_ok=True)
        tools_root = self.root / "Tools"
        (tools_root / "schemas").mkdir(parents=True)
        for name in ("check_profile.py", "check_queue.py", "kblib.py",
                     "maintenance_candidates.py"):
            shutil.copy2(TOOLS / name, tools_root / name)
        shutil.copy2(
            TOOLS / "schemas/execution_defaults.template.yaml",
            tools_root / "schemas/execution_defaults.template.yaml")

        manifest = "profiles/test-profile/profile.md"
        active_path = (
            self.root /
            "kernel/K00 Standards Control/03 Standards Governance.md"
        )
        active = active_path.read_text(encoding="utf-8")
        for placeholder, value in (
                ("{{ standards_version }}", "3.0.0"),
                ("{{ standards_status }}", "approved"),
                ("{{ standards_effective_date }}", "2026-08-04"),
                ("{{ selected_profile_manifest }}", manifest)):
            active = active.replace(placeholder, value)
        active_path.write_text(active, encoding="utf-8")

        coverage_path = self.root / check_queue.COVERAGE_PATH
        queue_path = self.root / check_queue.QUEUE_PATH
        progress_path = self.root / check_queue.PROGRESS_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        queue = kblib.load_yaml_file(queue_path)
        progress = kblib.load_yaml_file(progress_path)
        coverage["selected_profile_manifest"] = manifest
        queue["selected_profile_manifest"] = manifest
        progress["contract"]["selected_profile_manifest"] = manifest
        coverage_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        queue_text = kblib.canonical_yaml(queue)
        queue_path.write_text(queue_text, encoding="utf-8")
        queue_sha = kblib.sha256_bytes(queue_text)
        coverage_sha = kblib.sha256_file(coverage_path)
        progress["required_queue_sha256"] = queue_sha
        progress["checkpoint"]["required_queue_sha256"] = queue_sha
        progress["checkpoint"]["coverage_sha256"] = coverage_sha
        progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")

        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        for receipt in receipts:
            if receipt.get("receipt_id") == "audit-fixture-initial-queue":
                receipt["after_required_queue_sha256"] = queue_sha
                receipt["after_coverage_sha256"] = coverage_sha
                receipt["contract_sha256"] = \
                    check_queue._contract_sha256(progress)
        receipt_path.write_text("".join(json.dumps(receipt) + "\n"
                                        for receipt in receipts),
                                encoding="utf-8")
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def merge_and_apply(self, batch_id, object_path):
        ready = self.ready_receipt(batch_id)
        self.transition(batch_id, "open", "--gate-receipt", ready)
        page_receipt = kblib.make_receipt(
            "fixture_page_evidence", "0.9.0", "page_review", object_path,
            "pass", "reusable historical page evidence",
            1 if batch_id == "B1" else 2,
        )
        kblib.write_receipts(
            self.root / ".cambium/receipts/page-evidence.jsonl",
            [page_receipt])
        batch_receipt = self.write_batch_receipt(
            batch_id, page_receipt["receipt_id"])
        delta = self.write_delta(
            batch_id, object_path, page_receipt["receipt_id"])
        self.transition(
            batch_id, "merge-ready", "--delta-path", delta,
            "--batch-receipt", batch_receipt,
        )

        coverage_path = self.root / check_queue.COVERAGE_PATH
        queue_path = self.root / check_queue.QUEUE_PATH
        applied = subprocess.run(
            [
                sys.executable, str(TOOLS / "apply_delta.py"),
                check_queue.COVERAGE_PATH, delta, "--root", str(self.root),
                "--expected-coverage-sha256",
                kblib.sha256_file(coverage_path),
                "--expected-queue-sha256", kblib.sha256_file(queue_path),
                "--actor-role", "integrator",
                "--receipts",
                ".cambium/receipts/delta-%s.jsonl" % batch_id,
                "--apply",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, applied.returncode, applied.stdout)
        delta_apply_receipt = json.loads(
            (self.root / (".cambium/receipts/delta-%s.jsonl" % batch_id))
            .read_text(encoding="utf-8").splitlines()[-1]
        )["receipt_id"]

        close_register = ".cambium/receipts/close-%s.jsonl" % batch_id
        checked = self.run_tool(
            "check_queue.py", "--receipts", close_register)
        self.assertEqual(0, checked.returncode, checked.stdout)
        close_receipt = json.loads((self.root / close_register).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]
        close_gate = self.close_gate_receipt(batch_id, close_receipt)
        return delta_apply_receipt, close_receipt, close_gate

    def merge_and_close(self, batch_id, object_path):
        delta_apply_receipt, close_receipt, close_gate = self.merge_and_apply(
            batch_id, object_path)
        self.transition(
            batch_id, "closed", "--gate-receipt", close_receipt,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_apply_receipt,
        )

    def test_two_batch_lifecycle_is_resumable_and_completes(self):
        initial_resume = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, initial_resume.returncode, initial_resume.stdout)
        self.assertIn("task_id=fixture-task", initial_resume.stdout)
        self.assertIn("batches.queued=B1,B2", initial_resume.stdout)
        self.assert_resume_envelope(
            initial_resume, "activate-ready-batch:B1")

        self.merge_and_close("B1", "Topics/A.md")
        after_first = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, after_first.returncode, after_first.stdout)
        self.assertIn("batches.closed=B1", after_first.stdout)
        self.assertIn("batches.queued=B2", after_first.stdout)
        self.assert_resume_envelope(
            after_first, "activate-ready-batch:B2")

        self.merge_and_close("B2", "Topics/B.md")
        complete = self.run_tool(
            "check_queue.py", "--require-complete", "--receipts",
            ".cambium/receipts/queue-complete.jsonl",
        )
        self.assertEqual(0, complete.returncode, complete.stdout)
        self.assertIn("remaining=0", complete.stdout)
        completion_receipt = json.loads(
            (self.root / ".cambium/receipts/queue-complete.jsonl")
            .read_text(encoding="utf-8").splitlines()[-1]
        )["receipt_id"]
        self.task_transition(
            "completion-candidate", "--queue-check-receipt",
            completion_receipt,
            "--checkpoint-summary", "all Required work units are terminal",
        )
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("task_state=completion-candidate", resumed.stdout)
        self.assertIn("next_action=run-terminal-audit", resumed.stdout)
        self.assertIn("preserve the frozen candidate and run the Terminal Audit",
                      resumed.stdout)
        self.assertIn("terminal_audit.queue_check_receipt=%s" %
                      completion_receipt, resumed.stdout)
        self.assert_resume_envelope(resumed, "run-terminal-audit")

        rendered = self.run_tool("render_queue.py")
        self.assertEqual(0, rendered.returncode, rendered.stdout)
        report = (self.root / ".cambium/reports/required_queue.md").read_text(
            encoding="utf-8")
        self.assertIn("Remaining required work units: `0`", report)
        self.assertIn("`B1`: `closed`", report)
        self.assertIn("`B2`: `closed`", report)

    def test_live_writer_lock_blocks_silent_restart(self):
        queue_sha = kblib.sha256_file(self.root / check_queue.QUEUE_PATH)
        operation = {
            "tool": "update_queue",
            "action": "transition:open",
            "target": "B1",
            "before_required_queue_sha256": queue_sha,
            "planned_after_required_queue_sha256": queue_sha,
            "receipt_id": "not-yet-written",
            "receipt_path": ".cambium/receipts/queue-transitions.jsonl",
        }
        with kblib.runtime_write_lock(self.root, owner_metadata=operation):
            resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("active or interrupted writer lock", resumed.stdout)
        self.assertIn("operation_receipt=", resumed.stdout)
        self.assertIn('"status": "absent"', resumed.stdout)
        self.assert_resume_envelope(
            resumed, "reconcile-interrupted-write")

    def test_blocked_task_restart_has_one_durable_next_action(self):
        self.task_transition(
            "blocked", "--checkpoint-summary",
            "external dependency unavailable",
            "--at", "2026-08-04T01:00:00Z",
        )
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("task_state=blocked", resumed.stdout)
        self.assertIn(
            'checkpoint.summary="external dependency unavailable"',
            resumed.stdout,
        )
        self.assert_resume_envelope(resumed, "resolve-blocked-task")

    def test_interrupted_close_exposes_all_planned_state_and_repairs(self):
        delta_receipt, consistency_receipt, close_gate = \
            self.merge_and_apply("B1", "Topics/A.md")
        queue = self.queue()
        arguments = [
            str(self.root), "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency_receipt,
            "--close-gate-receipt", close_gate,
            "--delta-apply-receipt", delta_receipt,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at",
            "2099-01-01T03:00:00Z", "--apply",
        ]
        program = """
import os
import sys
sys.path.insert(0, sys.argv[1])
import update_queue

def crash_before_receipt(*args, **kwargs):
    os._exit(23)

update_queue.kblib.write_receipts = crash_before_receipt
raise SystemExit(update_queue.main(sys.argv[2:]))
"""
        child = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, child.returncode, child.stdout)

        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(1, resumed.returncode, resumed.stdout)
        self.assertIn("task_state=active", resumed.stdout)
        self.assertIn("batches.closed=B1", resumed.stdout)
        self.assertIn("state.coverage phase=planned-after", resumed.stdout)
        self.assertIn("state.queue phase=planned-after", resumed.stdout)
        self.assertIn("state.progress phase=planned-after", resumed.stdout)
        self.assertIn('"status": "absent"', resumed.stdout)
        self.assert_resume_envelope(resumed,
                                    "reconcile-interrupted-write")

    def test_interrupted_completion_transition_is_not_mistaken_for_complete(self):
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        gate_path = ".cambium/receipts/queue-complete-crash.jsonl"
        gate = self.run_tool(
            "check_queue.py", "--require-complete", "--receipts", gate_path)
        self.assertEqual(0, gate.returncode, gate.stdout)
        gate_id = json.loads((self.root / gate_path).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]
        arguments = [
            str(self.root), "--transition", "completion-candidate",
            "--queue-check-receipt", gate_id,
            "--checkpoint-summary", "all Required work closed",
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at",
            "2099-01-01T04:00:00Z", "--apply",
        ]
        program = """
import os
import sys
sys.path.insert(0, sys.argv[1])
import update_task

def crash_before_receipt(*args, **kwargs):
    os._exit(23)

update_task.kblib.write_receipts = crash_before_receipt
raise SystemExit(update_task.main(sys.argv[2:]))
"""
        child = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(23, child.returncode, child.stdout)

        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(1, resumed.returncode, resumed.stdout)
        self.assertIn("task_state=completion-candidate", resumed.stdout)
        self.assertIn("state.coverage phase=before", resumed.stdout)
        self.assertIn("state.queue phase=before", resumed.stdout)
        self.assertIn("state.progress phase=planned-after", resumed.stdout)
        self.assertIn('"status": "absent"', resumed.stdout)
        self.assert_resume_envelope(resumed,
                                    "reconcile-interrupted-write")

    def test_cancelled_task_archives_incomplete_batch_history_without_resume(self):
        ready = self.ready_receipt("B1")
        self.transition(
            "B1", "open", "--gate-receipt", ready,
            "--at", "2026-08-04T01:00:00Z",
        )
        self.task_transition(
            "cancelled", "--checkpoint-summary",
            "user terminated the current Task Contract",
            "--at", "2026-08-04T02:00:00Z",
        )
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(0, resumed.returncode, resumed.stdout)
        self.assertIn("task_state=cancelled", resumed.stdout)
        self.assertIn("batches.open=B1", resumed.stdout)
        self.assertIn("next_action=archive-terminal-runtime", resumed.stdout)
        self.assertIn("preserve any unfinished batch", resumed.stdout)
        self.assertNotIn("in-flight batch(es) require resume", resumed.stdout)
        self.assertNotIn("resume existing task", resumed.stdout)
        self.assert_resume_envelope(resumed, "archive-terminal-runtime")

    def test_require_ready_respects_task_lifecycle(self):
        self.task_transition(
            "paused", "--checkpoint-summary", "operator pause",
            "--at", "2026-08-04T01:00:00Z",
        )
        held = self.run_tool("check_queue.py", "--require-ready", "B1")
        self.assertEqual(2, held.returncode, held.stdout)
        self.assertIn("task_state=paused forbids activation", held.stdout)
        self.task_transition(
            "active", "--checkpoint-summary", "operator resumed",
            "--at", "2026-08-04T02:00:00Z",
        )
        self.task_transition(
            "cancelled", "--checkpoint-summary", "task cancelled",
            "--at", "2026-08-04T03:00:00Z",
        )
        rejected = self.run_tool("check_queue.py", "--require-ready", "B1")
        self.assertEqual(1, rejected.returncode, rejected.stdout)
        self.assertIn("task_state=cancelled is terminal", rejected.stdout)

    def test_first_open_persists_restartable_task_activation_binding(self):
        ready = self.ready_receipt("B1")
        self.transition(
            "B1", "open", "--gate-receipt", ready,
            "--at", "2026-08-04T01:00:00Z",
        )
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        task_receipt_id = result["progress"]["task_transition_receipts"][0]
        task_receipt = result["receipt_catalog"][task_receipt_id][1]
        item = result["items_by_id"]["B1"]
        self.assertEqual("B1", task_receipt["first_open_batch_id"])
        self.assertEqual(
            item["transition_receipts"][0],
            task_receipt["first_open_transition_receipt"],
        )
        self.assertEqual(1, task_receipt["queue_state_revision"])
        self.assertEqual(
            check_queue._contract_sha256(result["progress"]),
            task_receipt["contract_sha256"],
        )

    def test_noncomplete_maintenance_task_cannot_claim_passed_completion(self):
        self.use_maintenance_completion()
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        progress["maintenance_completion"] = {
            "state": "passed",
            "completion_gate_receipt": "audit-fake-gate",
            "budget_manifest_receipt": "audit-fake-budget",
            "ledger_advance_receipt": "audit-fake-ledger",
            "watermark_advance_receipt": "audit-fake-watermark",
        }
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn(
            "maintenance task_state=planned requires "
            "maintenance_completion.state=pending",
            errors,
        )
        self.assertIn(
            "non-complete maintenance task requires "
            "maintenance_completion.completion_gate_receipt=null",
            errors,
        )

    def test_real_terminal_proof_receipt_completes_task(self):
        self.install_terminal_proof_environment()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        completion_register = ".cambium/receipts/queue-complete.jsonl"
        completed_queue = self.run_tool(
            "check_queue.py", "--require-complete", "--receipts",
            completion_register)
        self.assertEqual(0, completed_queue.returncode, completed_queue.stdout)
        completion_receipt = json.loads(
            (self.root / completion_register).read_text(
                encoding="utf-8").splitlines()[-1]
        )["receipt_id"]
        self.task_transition(
            "completion-candidate", "--queue-check-receipt",
            completion_receipt, "--checkpoint-summary",
            "all Required work units are terminal")
        proof_queue_check = self.run_tool(
            "check_queue.py", "--require-complete", "--receipts",
            completion_register)
        self.assertEqual(0, proof_queue_check.returncode,
                         proof_queue_check.stdout)
        proof_queue_receipt = json.loads(
            (self.root / completion_register).read_text(
                encoding="utf-8").splitlines()[-1]
        )["receipt_id"]
        self.assertNotEqual(completion_receipt, proof_queue_receipt)
        corpus_plan_check = self.run_tool(
            "check_corpus_plan.py", "--receipts", completion_register)
        self.assertEqual(0, corpus_plan_check.returncode,
                         corpus_plan_check.stdout)
        corpus_plan_receipt = json.loads(
            (self.root / completion_register).read_text(
                encoding="utf-8").splitlines()[-1]
        )["receipt_id"]

        proof = kblib.parse_yaml_subset((
            TOOLS / "schemas/terminal_proof.template.yaml"
        ).read_text(encoding="utf-8"))
        proof.update({
            "task_id": "fixture-task",
            "scope_version": "s1",
            "contract_version": "c1",
            "coverage_ledger_sha256": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "progress_ledger_sha256": kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            "required_queue_path": check_queue.QUEUE_PATH,
            "queue_revision": self.queue()["queue_revision"],
            "queue_state_revision": self.queue()["state_revision"],
            "required_queue_sha256": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
            "remaining_required_work_units": 0,
            "queue_check_receipt": proof_queue_receipt,
            "corpus_plan_check_receipt": corpus_plan_receipt,
            "corpus_plan_semantic_acceptance_receipt": None,
            "standards_version": "3.0.0",
            "selected_profile_manifest": "profiles/test-profile/profile.md",
            "selected_route_ids": ["R01", "R08", "R12"],
            "selected_card_paths": [
                "kernel/Cards/R01 Core Bootstrap Card.md",
                "kernel/Cards/R08 Audit and Completion Card.md",
                "kernel/Cards/R12 Targeted and Specialized Audit Card.md",
            ],
            "selected_profile_route_ids": [],
            "selected_read_sets": [],
            "loaded_module_paths": [
                "kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md"],
            "guidance_cutoff_id": "G-000",
            "audit_receipt_register": completion_register,
            "full_deterministic_results": completion_register,
            "incremental_manual_scope": [],
            # K12/16 per-dimension accounting: the two dimensions this fixture
            # actually produced receipts for cite them; the rest carry an
            # explicit not-applicable declaration rather than silence.
            "dimension_coverage": {
                "coverage_and_integration": [proof_queue_receipt],
                "guidance_and_contract": [corpus_plan_receipt],
                "structure_and_links":
                    "not-applicable: the frozen fixture scope holds no "
                    "authored knowledge page to review for links",
                "content_and_depth":
                    "not-applicable: the frozen fixture scope holds no "
                    "authored knowledge page",
                "formula_and_numeric":
                    "not-applicable: the frozen fixture scope states no "
                    "formula, symbol, numeric example, or metric provenance",
                "source_and_currentness":
                    "not-applicable: the frozen fixture scope cites no "
                    "external source",
                "rendering":
                    "not-applicable: visual_trigger: not_applicable",
            },
        })
        proof_relative = ".cambium/receipts/terminal-proof.yaml"
        (self.root / proof_relative).write_text(
            kblib.canonical_yaml(proof), encoding="utf-8")
        proof_register = ".cambium/receipts/proof-pass.jsonl"
        proof_command = [
            sys.executable, str(TOOLS / "check_proof.py"), proof_relative,
            "--root", str(self.root), "--progress-ledger",
            check_queue.PROGRESS_PATH, "--ledger", check_queue.COVERAGE_PATH,
            "--receipts", proof_register,
        ]
        proof_check = subprocess.run(
            proof_command, cwd=self.root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, proof_check.returncode, proof_check.stdout)
        proof_receipt = json.loads((self.root / proof_register).read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertEqual("proof-check-summary", proof_receipt["check"])

        self.task_transition(
            "complete", "--terminal-proof-receipt",
            proof_receipt["receipt_id"], "--checkpoint-summary",
            "Terminal Proof passed")
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("complete", result["progress"]["task_state"])
        self.assertEqual("passed",
                         result["progress"]["terminal_audit"]["state"])
        self.assertEqual(
            proof_receipt["terminal_proof_sha256"],
            result["progress"]["terminal_audit"]["terminal_proof_sha256"],
        )
        proof_recheck = subprocess.run(
            proof_command, cwd=self.root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, proof_recheck.returncode, proof_recheck.stdout)
        (self.root / proof_relative).unlink()
        missing_proof = check_queue.validate_runtime(self.root)
        self.assertTrue(any("Terminal Proof is unsafe or missing" in error
                            for error in missing_proof["errors"]),
                        missing_proof["errors"])

    def test_maintenance_gate_is_resumable_and_completes_without_terminal_proof(self):
        self.use_maintenance_completion()
        wrong_gate = self.run_tool("check_queue.py", "--require-complete")
        self.assertEqual(1, wrong_gate.returncode, wrong_gate.stdout)
        self.assertIn("maintenance tasks must use --require-maintenance-complete",
                      wrong_gate.stdout)
        candidate = self.run_tool(
            "update_task.py", "--transition", "completion-candidate",
            "--queue-check-receipt", "not-a-gate",
            "--checkpoint-summary", "must not enter build candidate",
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--apply",
        )
        self.assertEqual(1, candidate.returncode, candidate.stdout)
        self.assertIn("maintenance tasks may not enter completion-candidate",
                      candidate.stdout)
        early = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", "missing-budget",
            "--ledger-advance-receipt", "missing-ledger",
            "--watermark-advance-receipt", "missing-watermark",
        )
        self.assertEqual(1, early.returncode, early.stdout)
        self.assertIn("zero remaining Required work", early.stdout)

        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()
        gate_register = ".cambium/receipts/maintenance-gate.jsonl"
        gate = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
            "--receipts", gate_register,
        )
        self.assertEqual(0, gate.returncode, gate.stdout)
        gate_receipt = json.loads((self.root / gate_register).read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertEqual("maintenance", gate_receipt["completion_semantics"])
        self.assertEqual(["B1", "B2"], gate_receipt["terminal_batch_ids"])
        self.assertEqual(
            check_queue.maintenance_candidates.candidate_state_sha256(
                check_queue.validate_runtime(self.root)["coverage"][
                    "maintenance_candidates"]),
            gate_receipt["maintenance_candidate_state_sha256"],
        )
        self.assertEqual(2, len(gate_receipt["maintenance_candidate_states"]))
        self.assertEqual([], gate_receipt["deferred_candidate_ids"])

        # An interruption may leave more than one still-current gate.  Resume
        # must pick one deterministically instead of treating multiplicity as
        # corruption or consuming an arbitrary line from the register.
        duplicate_gate = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
            "--receipts", gate_register,
        )
        self.assertEqual(0, duplicate_gate.returncode, duplicate_gate.stdout)
        persisted_gates = [json.loads(line) for line in
                           (self.root / gate_register).read_text(
                               encoding="utf-8").splitlines()]
        self.assertEqual(2, len(persisted_gates))
        self.assertNotEqual(
            persisted_gates[0]["receipt_id"], persisted_gates[1]["receipt_id"])
        gate_receipt = max(
            persisted_gates,
            key=lambda receipt: (receipt["checked_at"], receipt["receipt_id"]),
        )

        interrupted = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, interrupted.returncode, interrupted.stdout)
        self.assertIn(
            "next_action=complete-maintenance-task:%s" %
            gate_receipt["receipt_id"], interrupted.stdout,
        )
        self.assertIn(
            "maintenance_gate.selected=%s" % gate_receipt["receipt_id"],
            interrupted.stdout,
        )
        self.assertIn(
            "maintenance_candidates.sha256=%s" %
            gate_receipt["maintenance_candidate_state_sha256"],
            interrupted.stdout,
        )
        self.assert_resume_envelope(
            interrupted,
            "complete-maintenance-task:%s" % gate_receipt["receipt_id"],
        )

        consumed_gate_receipt = next(
            receipt for receipt in persisted_gates
            if receipt["receipt_id"] != gate_receipt["receipt_id"]
        )
        self.task_transition(
            "complete", "--maintenance-completion-receipt",
            consumed_gate_receipt["receipt_id"], "--checkpoint-summary",
            "bounded maintenance completion gate passed",
        )
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("complete", result["progress"]["task_state"])
        self.assertEqual(
            "not-applicable", result["progress"]["terminal_audit"]["state"])
        self.assertEqual(
            "passed", result["progress"]["maintenance_completion"]["state"])
        terminal_resume = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(0, terminal_resume.returncode, terminal_resume.stdout)
        self.assertIn("next_action=archive-terminal-runtime",
                      terminal_resume.stdout)
        self.assertIn(
            "maintenance_gate.selected=%s" %
            consumed_gate_receipt["receipt_id"],
            terminal_resume.stdout,
        )
        compatible_line = next(
            line for line in terminal_resume.stdout.splitlines()
            if "maintenance_gate.current_compatible=" in line
        )
        self.assertIn(consumed_gate_receipt["receipt_id"], compatible_line)
        self.assertIn("maintenance_gate.stale=none", terminal_resume.stdout)
        self.assert_resume_envelope(
            terminal_resume, "archive-terminal-runtime")

    def test_maintenance_gate_rejects_tampered_budget_manifest(self):
        self.use_maintenance_completion()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        budget_path.write_text(
            budget_path.read_text(encoding="utf-8").replace(
                "state: closed", "state: open"),
            encoding="utf-8",
        )
        gate = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(1, gate.returncode, gate.stdout)
        self.assertIn("does not bind current budget_manifest_path bytes",
                      gate.stdout)

    def test_maintenance_gate_rejects_watermark_batch_outside_manifest(self):
        self.use_maintenance_completion()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()

        watermark_path = self.root / "Tools/state/watermark.yaml"
        watermark = kblib.load_yaml_file(watermark_path)
        watermark["last_batch_id"] = "B-NOT-IN-QUEUE"
        watermark_path.write_text(
            kblib.canonical_yaml(watermark), encoding="utf-8")

        evidence_path = \
            self.root / ".cambium/receipts/maintenance-evidence.jsonl"
        receipts = [json.loads(line) for line in evidence_path.read_text(
            encoding="utf-8").splitlines()]
        receipt = next(value for value in receipts
                       if value["receipt_id"] == watermark_id)
        receipt["after_watermark_sha256"] = kblib.sha256_file(watermark_path)
        receipt["watermark_batch_id"] = watermark["last_batch_id"]
        evidence_path.write_text(
            "".join(json.dumps(value) + "\n" for value in receipts),
            encoding="utf-8",
        )

        gate = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(1, gate.returncode, gate.stdout)
        self.assertIn(
            "last_batch_id is not one of the budget manifest "
            "required_batch_ids",
            gate.stdout,
        )

    def test_maintenance_gate_rejects_fake_deferred_count_after_rebinding(self):
        self.use_maintenance_completion()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        budget = kblib.load_yaml_file(budget_path)
        budget["deferred_count"] = 999
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        self.rebind_maintenance_budget_receipt(budget_id)
        gate = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(1, gate.returncode, gate.stdout)
        self.assertIn(
            "maintenance budget manifest deferred_count must equal 0",
            gate.stdout,
        )

    def test_maintenance_gate_rejects_schema_v1_after_rebinding(self):
        self.use_maintenance_completion()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        budget = kblib.load_yaml_file(budget_path)
        budget["schema_version"] = 1
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        self.rebind_maintenance_budget_receipt(budget_id)
        gate = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(1, gate.returncode, gate.stdout)
        self.assertIn(
            "maintenance budget manifest schema_version must be 2",
            gate.stdout,
        )

    def test_maintenance_gate_enforces_page_and_hour_budget(self):
        self.use_maintenance_completion()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"

        budget = kblib.load_yaml_file(budget_path)
        budget["budget_limit"] = 1
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        page_overflow = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(1, page_overflow.returncode, page_overflow.stdout)
        self.assertIn("selects 2 pages, exceeding budget_limit 1",
                      page_overflow.stdout)

        budget["budget_unit"] = "hours"
        budget["budget_limit"] = 1.5
        budget["consumed_hours"] = None
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        missing_actual = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(1, missing_actual.returncode, missing_actual.stdout)
        self.assertIn("consumed_hours must be a number >= 0",
                      missing_actual.stdout)

        budget["consumed_hours"] = 2.0
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        hour_overflow = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(1, hour_overflow.returncode, hour_overflow.stdout)
        self.assertIn("consumed_hours 2.0 exceeds budget_limit 1.5",
                      hour_overflow.stdout)

        budget["consumed_hours"] = 1.25
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        evidence_path = \
            self.root / ".cambium/receipts/maintenance-evidence.jsonl"
        receipts = [json.loads(line) for line in evidence_path.read_text(
            encoding="utf-8").splitlines()]
        next(receipt for receipt in receipts
             if receipt["receipt_id"] == budget_id)[
                 "budget_manifest_sha256"] = kblib.sha256_file(budget_path)
        evidence_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        hours_within_budget = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
        )
        self.assertEqual(
            0, hours_within_budget.returncode, hours_within_budget.stdout)

    def test_resume_ignores_stale_maintenance_gate_after_evidence_changes(self):
        self.use_maintenance_completion()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()
        gate_register = ".cambium/receipts/maintenance-gate.jsonl"
        gate = self.run_tool(
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
            "--receipts", gate_register,
        )
        self.assertEqual(0, gate.returncode, gate.stdout)
        gate_id = json.loads((self.root / gate_register).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]

        # Simulate a crash followed by an external maintenance-input update.
        # The old gate remains durable history but is no longer consumable.
        budget_path = self.root / ".cambium/receipts/maintenance-budget.yaml"
        budget = kblib.load_yaml_file(budget_path)
        budget["deferred_count"] = 1
        budget_path.write_text(kblib.canonical_yaml(budget), encoding="utf-8")
        resumed = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, resumed.returncode, resumed.stdout)
        self.assertIn("next_action=run-maintenance-completion-gate",
                      resumed.stdout)
        self.assertIn("maintenance_gate.selected=none", resumed.stdout)
        self.assertIn("maintenance_gate.stale=%s" % gate_id, resumed.stdout)
        self.assert_resume_envelope(
            resumed, "run-maintenance-completion-gate")


if __name__ == "__main__":
    unittest.main()
