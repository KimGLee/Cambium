from pathlib import Path
from contextlib import redirect_stdout
import copy
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import check_queue
import compile_queue
import kblib
import register_amendment
import batch_settlement
import candidate_lifecycle
from profile_fixture import install_loadable_profile


class CompileQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        coverage["batch_specs"] = [
            {
                "id": "B1", "family": "Core", "order_hint": 1,
                "source_route": "R03", "execution_mode": "concurrent-worker",
                "depends_on": [], "confirmation_required": False,
                "work_spec_path": None, "work_spec_sha256": None,
            },
            {
                "id": "B2", "family": "Core", "order_hint": 2,
                "source_route": "R03", "execution_mode": "concurrent-worker",
                "depends_on": ["B1"], "confirmation_required": False,
                "work_spec_path": None, "work_spec_sha256": None,
            },
        ]
        coverage_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")

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

    def refresh_initial_origin(self):
        path = self.root / ".cambium/receipts/task-transitions.jsonl"
        records = [json.loads(line) for line in path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("receipt_id") == "audit-fixture-initial-queue":
                record["after_required_queue_sha256"] = kblib.sha256_file(
                    self.root / check_queue.QUEUE_PATH)
                record["after_coverage_sha256"] = kblib.sha256_file(
                    self.root / check_queue.COVERAGE_PATH)
                record["after_progress_sha256"] = kblib.sha256_file(
                    self.root / check_queue.PROGRESS_PATH)
        path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n"
                    for record in records),
            encoding="utf-8",
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

    def empty_queue(self):
        queue = self.load(check_queue.QUEUE_PATH)
        queue["required_queue"] = []
        self.write_queue(queue)
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        progress["initial_queue_receipt"] = None
        progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")

    def batch_spec(self, coverage, batch_id):
        return next(spec for spec in coverage["batch_specs"]
                    if spec["id"] == batch_id)

    def write_work_spec(self, batch_id="B1", manifest=None):
        if manifest is None:
            manifest = ["Topics/A.md"]
        relative = ".cambium/work_specs/%s.yaml" % batch_id
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": 1,
            "batch_id": batch_id,
            "manifest": manifest,
            "outcomes": [{
                "outcome_id": "OUT-001",
                "required_result": "The declared result exists.",
            }],
            "instructions": [{
                "instruction_id": "INS-001", "order": 1,
                "target_scope": list(manifest),
                "required_transformation": "Apply the approved change.",
                "depends_on": [],
            }],
            "acceptance_conditions": [{
                "condition_id": "ACC-001",
                "target_scope": list(manifest),
                "observable_predicate": "Every target passes review.",
                "evidence_requirement": "A current review receipt exists.",
            }],
            "constraints": [{
                "constraint_id": "CON-001", "target_scope": ["batch"],
                "requirement": "Preserve declared scope.",
            }],
        }
        path.write_text(kblib.canonical_yaml(data), encoding="utf-8")
        return relative, path

    def write_proposal(self, coverage, amendment_id="A-REPLAN"):
        relative = ".cambium/deltas/replans/%s.coverage.yaml" % amendment_id
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        return relative

    def add_amendment(self, proposal_relative, amendment_id="A-REPLAN",
                      overrides=None, expect_success=True):
        shas = {
            "coverage": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "progress": kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            "queue": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
        }
        registered = subprocess.run(
            [sys.executable, str(TOOLS / "register_amendment.py"),
             str(self.root), "--operation", "queue-replan",
             "--amendment-id", amendment_id,
             "--coverage-proposal", proposal_relative,
             "--date", time.strftime("%Y-%m-%d", time.gmtime()),
             "--summary", "approved Queue structural replan",
             "--approval-reference", "user:fixture-approval",
             "--expected-coverage-sha256", shas["coverage"],
             "--expected-progress-sha256", shas["progress"],
             "--expected-queue-sha256", shas["queue"],
             "--actor-role", "integrator", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        if expect_success:
            self.assertEqual(0, registered.returncode, registered.stdout)
        else:
            return registered
        if overrides:
            path = self.root / check_queue.PROGRESS_PATH
            progress = kblib.load_yaml_file(path)
            progress["amendments"][-1].update(overrides)
            path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")
            receipt_path = self.root / register_amendment.RECEIPT_PATH
            receipts = [json.loads(line) for line in receipt_path.read_text(
                encoding="utf-8").splitlines()]
            receipts[-1].update(overrides)
            receipts[-1]["after_progress_sha256"] = kblib.sha256_file(path)
            receipt_path.write_text(
                "".join(json.dumps(receipt) + "\n" for receipt in receipts),
                encoding="utf-8",
            )
        return registered

    def apply_replan(self, proposal_relative, amendment_id="A-REPLAN",
                     *extra):
        queue = self.load(check_queue.QUEUE_PATH)
        return self.command(
            "--coverage-proposal", proposal_relative,
            "--apply-replan", "--amendment-id", amendment_id,
            "--expected-queue-revision", str(queue["queue_revision"]),
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--expected-coverage-sha256",
            kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--actor-role", "integrator", *extra,
        )

    def close_b1(self):
        self.make_task_active_without_open()
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\npages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-1\n",
            encoding="utf-8",
        )
        delta_sha = kblib.sha256_file(delta)
        open_sha = "sha256:" + "a" * 64
        merge_sha = "sha256:" + "b" * 64
        close_sha = "sha256:" + "c" * 64
        preclose_coverage_sha = "sha256:" + "e" * 64
        progress_sha = "sha256:" + "f" * 64
        merged_snapshot_sha = "sha256:" + "7" * 64
        batch_close_version = check_queue.BATCH_CLOSE_TOOL_VERSION
        queue_gate_version = check_queue.TOOL_VERSION
        evidence_relative = "%s/B1-fixture.jsonl" % (
            kblib.RECEIPT_COLD_EVIDENCE_PREFIX)
        evidence_file = self.root / evidence_relative
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        if not evidence_file.exists():
            evidence_file.write_bytes(b"")
        receipts = [
            {
                "receipt_id": "audit-page-1", "result": "pass",
                "invalidated_by": None,
            },
            {
                "receipt_id": "audit-batch-1", "result": "pass",
                "invalidated_by": None,
                "tool": check_queue.MANUAL_ATTESTATION_TOOL,
                "tool_version":
                    check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
                "check": check_queue.BATCH_REVIEW_CHECK,
                "target": "B1", "task_id": "fixture-task",
                "batch_id": "B1",
                "delta_page_receipt_ids": ["audit-page-1"],
            },
            {
                "receipt_id": "audit-transition-open", "result": "pass",
                "invalidated_by": None, "tool": "update_queue",
                "tool_version": "1.2.0", "check": "queue_transition",
                "actor_role": "integrator",
                "checked_at": "2026-08-04T01:00:00Z",
                "evidence_receipt": "audit-ready-1",
                "target": "B1", "task_id": "fixture-task",
                "queue_revision": 1, "before_state": "queued",
                "after_state": "open", "before_hold_state": "none",
                "after_hold_state": "none", "before_state_revision": 0,
                "after_state_revision": 1,
                "before_required_queue_sha256": open_sha,
                "after_required_queue_sha256": merge_sha,
                "before_coverage_sha256": preclose_coverage_sha,
                "before_progress_sha256": progress_sha,
            },
            {
                "receipt_id": "audit-transition-merge", "result": "pass",
                "invalidated_by": None, "tool": "update_queue",
                "tool_version": "1.2.0", "check": "queue_transition",
                "actor_role": "integrator",
                "checked_at": "2026-08-04T02:00:00Z",
                "evidence_receipt": "audit-batch-1",
                "target": "B1", "task_id": "fixture-task",
                "queue_revision": 1, "before_state": "open",
                "after_state": "merge-ready", "before_hold_state": "none",
                "after_hold_state": "none", "before_state_revision": 1,
                "after_state_revision": 2,
                "before_required_queue_sha256": merge_sha,
                "after_required_queue_sha256": close_sha,
                "before_coverage_sha256": preclose_coverage_sha,
                "before_progress_sha256": progress_sha,
            },
            {
                "receipt_id": "audit-transition-close", "result": "pass",
                "invalidated_by": None, "tool": "update_queue",
                "tool_version": "1.2.0", "check": "queue_transition",
                "actor_role": "integrator",
                "checked_at": "2026-08-04T03:00:00Z",
                "evidence_receipt": "audit-close-gate-1",
                "delta_apply_receipt": "audit-delta-apply-b1",
                "queue_consistency_receipt": "audit-close-1",
                "close_gate_receipt": "audit-close-gate-1",
                "target": "B1", "task_id": "fixture-task",
                "queue_revision": 1, "before_state": "merge-ready",
                "after_state": "closed", "before_hold_state": "none",
                "after_hold_state": "none", "before_state_revision": 2,
                "after_state_revision": 3,
                "before_required_queue_sha256": close_sha,
                "after_required_queue_sha256": "sha256:" + "d" * 64,
                "before_coverage_sha256": preclose_coverage_sha,
                "before_progress_sha256": progress_sha,
            },
            {
                "receipt_id": "audit-delta-apply-b1", "result": "pass",
                "invalidated_by": None, "tool": "apply_delta",
                "tool_version": "1.4.0", "check": "delta_apply",
                "target": "B1", "task_id": "fixture-task",
                "batch_id": "B1", "actor_role": "integrator",
                "coverage_ledger_path": check_queue.COVERAGE_PATH,
                "delta_path": ".cambium/deltas/B1.yaml",
                "delta_sha256": delta_sha,
                "before_coverage_sha256": "sha256:" + "0" * 64,
                "after_coverage_sha256": preclose_coverage_sha,
                "required_queue_sha256": close_sha,
                "queue_revision": 1, "queue_state_revision": 2,
            },
            {
                "receipt_id": "audit-ready-1", "result": "pass",
                "invalidated_by": None, "tool": "check_queue",
                "tool_version": queue_gate_version,
                "check": "required_queue",
                "queue_check_mode": "require-ready:B1",
                "task_id": "fixture-task", "queue_revision": 1,
                "queue_state_revision": 0,
                "required_queue_sha256": open_sha,
                "coverage_ledger_sha256": preclose_coverage_sha,
                "progress_ledger_sha256": progress_sha,
            },
            {
                "receipt_id": "audit-close-1", "result": "pass",
                "invalidated_by": None, "tool": "check_queue",
                "tool_version": queue_gate_version,
                "check": "required_queue",
                "queue_check_mode": "consistency",
                "task_id": "fixture-task", "queue_revision": 1,
                "queue_state_revision": 2,
                "required_queue_sha256": close_sha,
                "coverage_ledger_sha256": preclose_coverage_sha,
                "progress_ledger_sha256": progress_sha,
                "repository_snapshot_sha256": merged_snapshot_sha,
            },
        ]
        closed_list_evidence = {}
        integrator_id = "fixture-integrator"
        reviewer_id = "fixture-reviewer"
        for field in check_queue.CLOSED_LIST_EVIDENCE_FIELDS:
            receipt_id = "audit-closed-list-%s" % field
            receipts.append({
                "receipt_id": receipt_id, "result": "pass",
                "invalidated_by": None,
                "tool": "check_batch_close",
                "tool_version": batch_close_version,
                "check": "closed_list_%s" % field,
                "target": ".", "batch_id": "B1",
                "task_id": "fixture-task",
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "merged_snapshot_sha256": merged_snapshot_sha,
                "candidate_evidence": [],
            })
            closed_list_evidence[field] = receipt_id
        receipts.extend((
            {
                "receipt_id": "audit-review-attestation-1",
                "result": "pass", "invalidated_by": None,
                "tool": "check_batch_close",
                "tool_version": batch_close_version,
                "check": "batch_global_review_attestation",
                "target": "B1", "batch_id": "B1",
                "task_id": "fixture-task",
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "details": "fixture independent review attestation",
                "merged_snapshot_sha256": merged_snapshot_sha,
                "accepted_candidate_count": 0,
                "accepted_candidate_types": [],
                "accepted_by_type_counts": {},
                "candidate_set_sha256": kblib.sha256_bytes(b""),
                "candidate_evidence_path": evidence_relative,
                "candidate_evidence_sha256": kblib.sha256_bytes(b""),
                "candidate_evidence_bytes": 0,
                "candidate_evidence_records": 0,
                "candidate_dispositions": [],
                "candidate_protocol":
                    candidate_lifecycle.CANDIDATE_PROTOCOL,
                "candidate_baseline_protocol":
                    candidate_lifecycle.BASELINE_NONE,
                "candidate_baseline_receipt": None,
                "carried_candidate_count": 0,
                "carried_candidate_set_sha256":
                    candidate_lifecycle.candidate_set_sha256([]),
                "fresh_candidate_count": 0,
                "fresh_candidate_set_sha256":
                    candidate_lifecycle.candidate_set_sha256([]),
            },
            {
                "receipt_id": "audit-global-review-1", "result": "pass",
                "invalidated_by": None,
                "tool": "check_batch_close",
                "tool_version": batch_close_version,
                "check": "batch_global_review",
                "target": "B1", "batch_id": "B1",
                "task_id": "fixture-task",
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "merged_snapshot_sha256": merged_snapshot_sha,
                "reviewer_attestation_receipt":
                    "audit-review-attestation-1",
                "closed_list_evidence": closed_list_evidence,
            },
            {
                "receipt_id": "audit-close-gate-1", "result": "pass",
                "invalidated_by": None,
                "tool": "check_batch_close",
                "tool_version": batch_close_version,
                "check": "batch_close_gate",
                "target": "B1", "batch_id": "B1",
                "task_id": "fixture-task", "queue_revision": 1,
                "integrator_id": integrator_id,
                "reviewer_id": reviewer_id,
                "queue_state_revision": 2,
                "required_queue_sha256": close_sha,
                "coverage_ledger_sha256": preclose_coverage_sha,
                "progress_ledger_sha256": progress_sha,
                "delta_sha256": delta_sha,
                "delta_apply_receipt": "audit-delta-apply-b1",
                "queue_consistency_receipt": "audit-close-1",
                "corpus_plan_required": False,
                "corpus_plan_triggers": [],
                "corpus_plan_receipt": None,
                "work_spec_path": None,
                "work_spec_sha256": None,
                "merged_snapshot_sha256": merged_snapshot_sha,
                "reviewer_attestation_receipt":
                    "audit-review-attestation-1",
                "global_review_receipt": "audit-global-review-1",
                "closed_list_evidence": closed_list_evidence,
                **batch_settlement.close_binding(
                    batch_settlement.current_settlement_report(
                        self.load(check_queue.COVERAGE_PATH), "B1")),
            },
        ))
        receipt_path = self.root / ".cambium/receipts/history.jsonl"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        queue = self.load(check_queue.QUEUE_PATH)
        item = queue["required_queue"][0]
        item.update({
            "state": "closed", "transition_receipts": [
                "audit-transition-open", "audit-transition-merge",
                "audit-transition-close",
            ],
            "opened_at": "2026-08-04T01:00:00Z",
            "activation_receipt": "audit-ready-1",
            "merge_ready_at": "2026-08-04T02:00:00Z",
            "delta_path": ".cambium/deltas/B1.yaml",
            "delta_sha256": delta_sha,
            "batch_receipts": ["audit-batch-1"],
            "closed_at": "2026-08-04T03:00:00Z",
            "queue_consistency_receipt": "audit-close-1",
            "close_gate_receipt": "audit-close-gate-1",
            "delta_apply_receipt": "audit-delta-apply-b1",
        })
        queue["state_revision"] = 3
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["pages"][0]["next_batch"] = None
        (self.root / check_queue.COVERAGE_PATH).write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        self.write_queue(queue)
        live_coverage_sha = kblib.sha256_file(
            self.root / check_queue.COVERAGE_PATH)
        receipts_by_id = {receipt["receipt_id"]: receipt
                          for receipt in receipts}
        receipts_by_id["audit-transition-close"]["before_coverage_sha256"] = \
            live_coverage_sha
        receipts_by_id["audit-transition-close"]["after_coverage_sha256"] = \
            live_coverage_sha
        receipts_by_id["audit-delta-apply-b1"]["after_coverage_sha256"] = \
            live_coverage_sha
        receipts_by_id["audit-close-1"]["coverage_ledger_sha256"] = \
            live_coverage_sha
        receipts_by_id["audit-close-gate-1"]["coverage_ledger_sha256"] = \
            live_coverage_sha
        receipts_by_id["audit-transition-close"]["after_required_queue_sha256"] = \
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH)
        receipt_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        return copy.deepcopy(item)

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "compile_queue.py"), str(self.root),
             *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def update_command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "update_queue.py"), str(self.root),
             *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def append_receipt(self, receipt_id, target="B1", check="fixture"):
        receipt = {
            "receipt_id": receipt_id, "check": check, "target": target,
            "result": "pass", "invalidated_by": None,
        }
        if check == check_queue.BATCH_REVIEW_CHECK:
            receipt.update({
                "tool": check_queue.MANUAL_ATTESTATION_TOOL,
                "tool_version":
                    check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                "gate_id": check_queue.BATCH_REVIEW_GATE_ID,
                "task_id": "fixture-task", "batch_id": target,
                "delta_page_receipt_ids": [
                    receipt_id.replace("-batch-", "-page-", 1)
                ],
            })
        path = self.root / ".cambium/receipts/fixture.jsonl"
        kblib.write_receipts(path, [receipt])

    def queue_gate(self, *mode):
        relative = ".cambium/receipts/replan-preflight-gates.jsonl"
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             *mode, "--receipts", relative], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        return json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]

    def transition(self, batch_id, target, at, *extra):
        queue = self.load(check_queue.QUEUE_PATH)
        completed = self.update_command(
            "--id", batch_id, "--transition", target,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", at, "--apply", *extra,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        return completed

    def merge_then_invalidate_b1(self):
        gate = self.queue_gate("--require-ready", "B1")
        self.transition(
            "B1", "open", "2026-08-04T01:00:00Z",
            "--gate-receipt", gate,
        )
        self.append_receipt("audit-replan-page-1", target="Topics/A.md")
        self.append_receipt("audit-replan-batch-1", check="batch_gate")
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: 2026-08-04T02:00:00Z\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-replan-page-1\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n",
            encoding="utf-8",
        )
        self.transition(
            "B1", "merge-ready", "2026-08-04T02:00:00Z",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-replan-batch-1",
        )
        self.transition(
            "B1", "open", "2026-08-04T03:00:00Z",
            "--reason", "global validation failed",
        )

    def apply_scope_amendment(self):
        amendment_id = "A-SCOPE-BEFORE-REPLAN"
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-04T04:00:00Z"
        coverage["batch_specs"].append({
            "id": "B3", "family": "Added by scope Amendment",
            "order_hint": 3, "source_route": "R03",
            "execution_mode": "concurrent-worker", "depends_on": ["B2"],
            "confirmation_required": False,
            "work_spec_path": None, "work_spec_sha256": None,
        })
        coverage["pages"].append({
            "path": "Topics/C.md", "coverage_disposition": "required",
            "canonical_owner": "Topics/C.md", "type": "concept",
            "priority": "P1", "tier": "M", "authoring_status": "drafted",
            "prerequisites": ["Topics/B.md"], "batch": "B3",
            "next_batch": "B3", "deferred_reason": None,
            "reentry_condition": None, "gate_receipts": [],
        })
        proposal_relative = (
            ".cambium/deltas/amendments/%s.coverage.yaml" % amendment_id)
        proposal_path = self.root / proposal_relative
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        queue = self.load(check_queue.QUEUE_PATH)
        plan = {
            "schema_version": 1, "amendment_id": amendment_id,
            "operation": "scope-replan", "affected_pages": ["Topics/C.md"],
            "affected_batches": ["B3"],
            "scope_version_before": queue["scope_version"],
            "scope_version_after": "s2",
            "queue_revision_before": queue["queue_revision"],
            "queue_revision_after": queue["queue_revision"] + 1,
            "state_revision_before": queue["state_revision"],
            "state_revision_after": queue["state_revision"],
            "coverage_proposal_path": proposal_relative,
            "coverage_proposal_sha256": kblib.sha256_file(proposal_path),
            "cancel_batch_id": None,
        }
        plan_relative = ".cambium/deltas/amendments/%s.yaml" % amendment_id
        plan_path = self.root / plan_relative
        plan_path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        progress_path = self.root / check_queue.PROGRESS_PATH
        registered = subprocess.run(
            [sys.executable, str(TOOLS / "register_amendment.py"),
             str(self.root), "--operation", "scope-replan",
             "--plan", plan_relative,
             "--date", time.strftime("%Y-%m-%d", time.gmtime()),
             "--summary", "approved scope expansion",
             "--approval-reference", "user:fixture-approval",
             "--expected-coverage-sha256",
             kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
             "--expected-progress-sha256", kblib.sha256_file(progress_path),
             "--expected-queue-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, registered.returncode, registered.stdout)
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "apply_amendment.py"), str(self.root),
             "--plan", plan_relative,
             "--expected-coverage-sha256",
             kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
             "--expected-progress-sha256", kblib.sha256_file(progress_path),
             "--expected-queue-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)

    def test_same_inputs_produce_identical_proposal(self):
        self.empty_queue()
        first = self.command()
        second = self.command()
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertEqual(first.stdout, second.stdout)
        self.assertIn("manifest:", first.stdout)
        self.assertLess(first.stdout.index("id: B1"), first.stdout.index("id: B2"))

    def test_batch_specs_are_a_closed_compiler_contract(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        missing = copy.deepcopy(coverage)
        del missing["batch_specs"][0]["source_route"]
        with self.assertRaisesRegex(
                ValueError,
                r"batch_specs\[0\] misses required field\(s\): source_route"):
            compile_queue._batch_specs(missing)

        extra = copy.deepcopy(coverage)
        extra["batch_specs"][0]["runtime_hint"] = "not-owned-here"
        with self.assertRaisesRegex(
                ValueError,
                r"batch_specs\[0\] has unsupported field\(s\): runtime_hint"):
            compile_queue._batch_specs(extra)

    def test_open_batch_work_spec_replan_requires_revalidation_hold(self):
        queue = self.load(check_queue.QUEUE_PATH)
        current = queue["required_queue"][0]
        current.update({
            "state": "open", "opened_at": "2026-08-04T01:00:00Z",
            "activation_receipt": "audit-old-admission",
            "transition_receipts": ["audit-open"],
        })
        proposal = copy.deepcopy(queue)
        proposed = proposal["required_queue"][0]
        proposed["work_spec_path"] = ".cambium/work_specs/B1.yaml"
        proposed["work_spec_sha256"] = "sha256:" + "a" * 64
        diff = compile_queue.replan_diff(
            queue, proposal, "sha256:" + "b" * 64)
        self.assertTrue(diff["conflicts"])
        self.assertIn("requires a prior update_queue transition",
                      diff["conflicts"][0])
        update = next(entry for entry in diff["update_candidates"]
                      if entry["id"] == "B1")
        self.assertEqual(
            ["work_spec_path", "work_spec_sha256"],
            update["changed_fields"],
        )
        already_held = copy.deepcopy(queue)
        already_held["required_queue"][0]["hold_state"] = \
            "revalidation-required"
        already_held["required_queue"][0]["hold_reason"] = \
            "pre-existing revalidation boundary"
        held_proposal = copy.deepcopy(proposal)
        held_diff = compile_queue.replan_diff(
            already_held, held_proposal, "sha256:" + "d" * 64)
        held_result = compile_queue._build_replanned_queue(
            already_held, held_proposal, held_diff)
        held_item = held_result["required_queue"][0]
        self.assertEqual("open", held_item["state"])
        self.assertEqual("revalidation-required", held_item["hold_state"])
        self.assertEqual("pre-existing revalidation boundary",
                         held_item["hold_reason"])
        self.assertEqual("audit-old-admission",
                         held_item["activation_receipt"])
        self.assertEqual(queue["queue_revision"] + 1,
                         held_result["queue_revision"])
        self.assertEqual(queue["state_revision"],
                         held_result["state_revision"])

        current["hold_state"] = "blocked"
        blocked_diff = compile_queue.replan_diff(
            queue, proposal, "sha256:" + "c" * 64)
        self.assertTrue(blocked_diff["conflicts"])

    def test_open_work_spec_amendment_invalidates_old_admission_gate(self):
        self.make_task_active_without_open()
        ready_relative = ".cambium/receipts/work-spec-ready.jsonl"
        ready = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--require-ready", "B1", "--receipts", ready_relative],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, ready.returncode, ready.stdout)
        ready_id = json.loads((self.root / ready_relative).read_text(
            encoding="utf-8"))["receipt_id"]
        queue = self.load(check_queue.QUEUE_PATH)
        opened = self.update_command(
            "--id", "B1", "--transition", "open",
            "--gate-receipt", ready_id,
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at",
            "2026-08-04T00:03:00Z", "--apply",
        )
        self.assertEqual(0, opened.returncode, opened.stdout)

        opened_runtime = check_queue.validate_runtime(self.root)
        held = self.update_command(
            "--id", "B1", "--hold-state", "revalidation-required",
            "--reason", "Work Spec change requires fresh admission evidence",
            "--expected-state-revision",
            str(opened_runtime["queue"]["state_revision"]),
            "--expected-sha256", opened_runtime["queue_sha256"],
            "--actor-role", "integrator", "--at",
            "2026-08-04T00:03:30Z", "--apply",
        )
        self.assertEqual(0, held.returncode, held.stdout)

        work_spec_relative, work_spec = self.write_work_spec()
        coverage = self.load(check_queue.COVERAGE_PATH)
        b1 = self.batch_spec(coverage, "B1")
        b1["work_spec_path"] = work_spec_relative
        b1["work_spec_sha256"] = kblib.sha256_file(work_spec)
        amendment_id = "A-OPEN-WORK-SPEC"
        proposal_relative = self.write_proposal(coverage, amendment_id)
        self.add_amendment(proposal_relative, amendment_id)
        replanned = self.apply_replan(proposal_relative, amendment_id)
        self.assertEqual(0, replanned.returncode, replanned.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual("open", item["state"])
        self.assertEqual("revalidation-required", item["hold_state"])
        self.assertIn("fresh admission evidence", item["hold_reason"])
        self.assertEqual(2, result["queue"]["queue_revision"])

        stale = self.update_command(
            "--id", "B1", "--hold-state", "none",
            "--gate-receipt", ready_id,
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at",
            "2026-08-04T00:04:00Z", "--apply",
        )
        self.assertEqual(1, stale.returncode, stale.stdout)
        self.assertIn("expected 'required-queue-consistency'", stale.stdout)

        consistency_relative = ".cambium/receipts/work-spec-consistency.jsonl"
        consistency = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--receipts", consistency_relative],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, consistency.returncode, consistency.stdout)
        consistency_id = json.loads((self.root / consistency_relative)
                                    .read_text(encoding="utf-8"))["receipt_id"]
        current = check_queue.validate_runtime(self.root)
        cleared = self.update_command(
            "--id", "B1", "--hold-state", "none",
            "--gate-receipt", consistency_id,
            "--expected-state-revision",
            str(current["queue"]["state_revision"]),
            "--expected-sha256", current["queue_sha256"],
            "--actor-role", "integrator", "--at",
            "2026-08-04T00:05:00Z", "--apply",
        )
        self.assertEqual(0, cleared.returncode, cleared.stdout)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("none", final["items_by_id"]["B1"]["hold_state"])

    def test_apply_materializes_initial_queue_and_syncs_progress(self):
        self.empty_queue()
        before = self.load(check_queue.QUEUE_PATH)
        fingerprint = kblib.sha256_file(self.root / check_queue.QUEUE_PATH)
        completed = self.command(
            "--apply", "--expected-queue-revision",
            str(before["queue_revision"]), "--expected-sha256", fingerprint,
            "--actor-role", "integrator",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(2, result["queue"]["queue_revision"])
        self.assertEqual(["Topics/A.md"],
                         result["items_by_id"]["B1"]["manifest"])
        self.assertEqual(["B1"], result["items_by_id"]["B2"]["depends_on"])
        initial_id = result["progress"]["initial_queue_receipt"]
        self.assertIsInstance(initial_id, str)
        receipt = result["receipt_catalog"][initial_id][1]
        self.assertEqual("queue_structure", receipt["check"])
        self.assertEqual(result["queue_sha256"],
                         receipt["after_required_queue_sha256"])
        self.assertEqual(result["coverage_sha256"],
                         receipt["after_coverage_sha256"])

    def test_initial_compile_runs_profile_load_producer_once(self):
        self.empty_queue()
        before = self.load(check_queue.QUEUE_PATH)
        fingerprint = kblib.sha256_file(self.root / check_queue.QUEUE_PATH)
        producer = check_queue.check_profile.evaluate_profile_load
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                wraps=producer) as evaluate:
            with redirect_stdout(io.StringIO()):
                code = compile_queue.main([
                    str(self.root), "--apply", "--expected-queue-revision",
                    str(before["queue_revision"]), "--expected-sha256",
                    fingerprint, "--actor-role", "integrator",
                ])
        self.assertEqual(0, code)
        self.assertEqual(1, evaluate.call_count)

    def test_initial_compile_materializes_complex_work_spec_binding(self):
        self.empty_queue()
        relative, path = self.write_work_spec()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = self.load(check_queue.COVERAGE_PATH)
        spec = self.batch_spec(coverage, "B1")
        spec["work_spec_path"] = relative
        spec["work_spec_sha256"] = kblib.sha256_file(path)
        coverage_path.write_text(kblib.canonical_yaml(coverage),
                                 encoding="utf-8")
        queue = self.load(check_queue.QUEUE_PATH)
        completed = self.command(
            "--apply", "--expected-queue-revision",
            str(queue["queue_revision"]), "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        item = result["items_by_id"]["B1"]
        self.assertEqual(relative, item["work_spec_path"])
        self.assertEqual(kblib.sha256_file(path), item["work_spec_sha256"])

    def test_materialized_queue_without_initial_receipt_is_rejected(self):
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["initial_queue_receipt"] = None
        progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")
        errors = "\n".join(check_queue.validate_runtime(self.root)["errors"])
        self.assertIn("initial Queue must identify a receipt", errors)

    def test_worker_cannot_apply_initial_structure(self):
        self.empty_queue()
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        queue = self.load(check_queue.QUEUE_PATH)
        completed = self.command(
            "--apply", "--expected-queue-revision",
            str(queue["queue_revision"]), "--expected-sha256",
            kblib.sha256_bytes(before),
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_inconsistent_progress_identity_blocks_compile(self):
        self.empty_queue()
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        progress["task_id"] = "other-task"
        progress_path.write_text(kblib.canonical_yaml(progress), encoding="utf-8")
        completed = self.command()
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("differs across Queue/Coverage/Progress", completed.stdout)

    def test_page_prerequisite_is_not_inferred_as_batch_dependency(self):
        self.empty_queue()
        coverage = self.load(check_queue.COVERAGE_PATH)
        self.batch_spec(coverage, "B2")["depends_on"] = []
        (self.root / check_queue.COVERAGE_PATH).write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        completed = self.command()
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("depends_on: []", completed.stdout)

    def test_dependency_cycle_fails(self):
        self.empty_queue()
        coverage = self.load(check_queue.COVERAGE_PATH)
        self.batch_spec(coverage, "B1")["depends_on"] = ["B2"]
        (self.root / check_queue.COVERAGE_PATH).write_text(
            kblib.canonical_yaml(coverage), encoding="utf-8")
        completed = self.command()
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("cycle", completed.stdout)

    def test_proposal_output_cannot_overwrite_state(self):
        self.empty_queue()
        queue_path = self.root / check_queue.QUEUE_PATH
        before = queue_path.read_bytes()
        completed = self.command(
            "--output", ".cambium/state/required_queue.yaml"
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual(before, queue_path.read_bytes())

    def test_existing_closed_history_is_not_replaced_or_proposed_as_queued(self):
        self.close_b1()
        proposal_relative = self.write_proposal(
            self.load(check_queue.COVERAGE_PATH))
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.command("--coverage-proposal", proposal_relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("artifact_type: required-queue-replan-diff", completed.stdout)
        self.assertIn("preserved_closed_ids:", completed.stdout)
        self.assertIn("- B1", completed.stdout)
        self.assertNotIn("state: queued", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_replan_removal_is_blocked_and_does_not_drop_existing_item(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["pages"][1]["batch"] = "B1"
        coverage["pages"][1]["next_batch"] = "B1"
        coverage["batch_specs"] = [spec for spec in coverage["batch_specs"]
                                   if spec["id"] != "B2"]
        proposal_relative = self.write_proposal(coverage)
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.command("--coverage-proposal", proposal_relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("remove_candidates:", completed.stdout)
        self.assertIn("id: B2", completed.stdout)
        self.assertIn("blocked-amendment-required", completed.stdout)
        self.assertIn("preserved_lifecycle_ids:", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_integrator_replan_adds_successor_and_preserves_closed_history(self):
        closed_b1 = self.close_b1()
        queue = self.load(check_queue.QUEUE_PATH)
        queue["required_queue"][0] = copy.deepcopy(closed_b1)
        self.write_queue(queue)
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        coverage["pages"][0]["next_batch"] = "B3"
        self.batch_spec(coverage, "B2")["order_hint"] = 3
        coverage["batch_specs"] = [
            spec for spec in coverage["batch_specs"] if spec["id"] != "B1"
        ]
        coverage["batch_specs"].append({
            "id": "B3", "family": "Follow-up", "order_hint": 2,
            "source_route": "R07", "execution_mode": "concurrent-worker",
            "depends_on": ["B1"], "confirmation_required": False,
            "work_spec_path": None, "work_spec_sha256": None,
        })
        proposal_relative = self.write_proposal(coverage)
        self.add_amendment(proposal_relative)
        queue_before = self.load(check_queue.QUEUE_PATH)
        fingerprint = kblib.sha256_file(self.root / check_queue.QUEUE_PATH)
        completed = self.apply_replan(proposal_relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(2, result["queue"]["queue_revision"])
        self.assertEqual(3, result["queue"]["state_revision"])
        self.assertEqual(closed_b1, result["items_by_id"]["B1"])
        self.assertEqual("queued", result["items_by_id"]["B3"]["state"])
        self.assertEqual("B1", result["items_by_id"]["B3"]["successor_of"])
        self.assertEqual(["B1"], result["items_by_id"]["B3"]["depends_on"])
        self.assertEqual(3, result["items_by_id"]["B2"]["order"])
        receipts = [json.loads(line) for line in (self.root /
                    ".cambium/receipts/queue-structure.jsonl")
                    .read_text(encoding="utf-8").splitlines()]
        receipt = next(entry for entry in receipts
                       if entry.get("transaction_phase") == "commit")
        self.assertEqual("A-REPLAN", receipt["amendment_id"])
        self.assertEqual(fingerprint,
                         receipt["before_required_queue_sha256"])
        progress = self.load(check_queue.PROGRESS_PATH)
        amendment = next(entry for entry in progress["amendments"]
                         if entry["id"] == "A-REPLAN")
        self.assertEqual("verified", amendment["status"])
        self.assertIs(True, amendment["writeback_done"])
        self.assertEqual(receipt["receipt_id"],
                         amendment["transaction_receipt_id"])
        self.assertEqual(receipt["after_required_queue_sha256"],
                         amendment["after_required_queue_sha256"])
        self.assertEqual(receipt["after_coverage_sha256"],
                         amendment["after_coverage_sha256"])
        self.assertEqual(
            kblib.canonical_yaml(coverage),
            (self.root / check_queue.COVERAGE_PATH).read_text(encoding="utf-8"),
        )

    def test_replan_preflight_reuses_real_root_evidence_with_state_overrides(self):
        """The proposed-state preflight must resolve the real-root Read Set
        closure and recorded Standards-adoption plans while overriding only
        the three proposed state documents.  Copying those inputs into a temp
        root would create a second Profile/K00 admission and split the
        transaction across revisions."""
        read_set_relative = "kernel/Read Sets/R99 Fixture Read Set.md"
        read_set_path = self.root / read_set_relative
        read_set_path.parent.mkdir(parents=True, exist_ok=True)
        read_set_path.write_text(
            "---\ntype: read-set\nroute_id: R99\n---\n\n## Purpose\n\n"
            "Fixture route.\n\n## Related\n\nNone.\n", encoding="utf-8")
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.load_yaml_file(progress_path)
        progress["contract"]["selected_read_sets"] = [read_set_relative]
        progress_path.write_text(kblib.canonical_yaml(progress),
                                 encoding="utf-8")
        # Re-anchor the initial Queue receipt to the edited fixture contract;
        # the anchor chain is byte-bound and this test is not about it.
        new_anchor = check_queue._contract_sha256(progress)
        for receipts_path in sorted(
                (self.root / ".cambium/receipts").rglob("*.jsonl")):
            rows = []
            for line in receipts_path.read_text(
                    encoding="utf-8").splitlines():
                row = json.loads(line)
                if row.get("contract_sha256"):
                    row["contract_sha256"] = new_anchor
                rows.append(json.dumps(row, ensure_ascii=False))
            receipts_path.write_text("\n".join(rows) + "\n",
                                     encoding="utf-8")
        baseline = check_queue.validate_runtime(self.root)
        self.assertEqual([], baseline["errors"])

        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        self.batch_spec(coverage, "B2")["execution_mode"] = \
            "serial-integrator"
        proposal_relative = self.write_proposal(coverage)
        self.add_amendment(proposal_relative)
        completed = self.apply_replan(proposal_relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(
            "serial-integrator",
            result["items_by_id"]["B2"]["execution_mode"])

        # The queue-replan bumped the live queue_revision without an anchor
        # event; a later contract-anchor event must continue from the same
        # contract identity across that gap instead of failing the chain.
        catalog = check_queue.historical_receipt_catalog(result)
        progress = result["progress"]
        chain, chain_errors = check_queue._contract_anchor_chain(
            progress, catalog)
        self.assertEqual([], chain_errors)
        head = chain[-1]
        live_revision = result["queue"]["queue_revision"]
        self.assertGreater(live_revision, head["queue_revision"])
        synthetic_id = "audit-adopt_standards-synthetic-0001"
        synthetic = dict(catalog[head["receipt_id"]][1])
        synthetic.update({
            "receipt_id": synthetic_id,
            "before_contract_sha256": head["contract_sha256"],
            "after_contract_sha256": head["contract_sha256"],
            "before_contract_version": head["contract_version"],
            "after_contract_version": head["contract_version"],
            "before_contract_scope_version": head["scope_version"],
            "after_contract_scope_version": head["scope_version"],
            "queue_revision_before": live_revision,
            "queue_revision_after": live_revision + 1,
        })
        catalog = dict(catalog)
        catalog[synthetic_id] = ("synthetic", synthetic)
        progress = copy.deepcopy(progress)
        progress.setdefault("standards_adoptions", []).append({
            "id": "SA-SYNTH-1",
            "verification_receipt": synthetic_id,
            "queue_revision_before": live_revision,
            "queue_revision_after": live_revision + 1,
            "contract_version_before": head["contract_version"],
            "contract_version_after": head["contract_version"],
        })
        progress["queue_revision"] = live_revision + 1
        chain2, chain2_errors = check_queue._contract_anchor_chain(
            progress, catalog)
        self.assertEqual([], chain2_errors)
        self.assertEqual(live_revision + 1, chain2[-1]["queue_revision"])

    def test_replan_requires_exact_pending_amendment(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        self.batch_spec(coverage, "B2")["family"] = "Changed"
        proposal_relative = self.write_proposal(coverage)
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.apply_replan(proposal_relative, "MISSING")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("exactly one matching Amendment", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_replan_rejects_unrelated_approved_amendment(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        self.batch_spec(coverage, "B2")["family"] = "Changed"
        proposal_relative = self.write_proposal(coverage)
        self.add_amendment(
            proposal_relative, overrides={"affected_batches": ["UNRELATED"]})
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.apply_replan(proposal_relative)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("does not bind current replan", completed.stdout)
        self.assertIn("affected_batches", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_replan_rejects_proposal_tampered_after_approval(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        self.batch_spec(coverage, "B2")["family"] = "Approved"
        proposal_relative = self.write_proposal(coverage)
        self.add_amendment(proposal_relative)
        self.batch_spec(coverage, "B2")["family"] = "Tampered"
        self.write_proposal(coverage)
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.apply_replan(proposal_relative)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("Coverage proposal SHA does not match", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_replan_rejects_legacy_written_back_amendment_as_authorization(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        self.batch_spec(coverage, "B2")["family"] = "Changed"
        proposal_relative = self.write_proposal(coverage)
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["amendments"].append({
            "id": "A-REPLAN", "date": "2026-08-04",
            "summary": "old unbound record", "writeback_done": True,
        })
        progress_path.write_text(
            kblib.canonical_yaml(progress), encoding="utf-8")
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.apply_replan(proposal_relative)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("misses explicit field(s): status", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_cancelled_history_absent_from_specs_is_preserved_when_adding_batch(self):
        queue = self.load(check_queue.QUEUE_PATH)
        cancelled_b1 = copy.deepcopy(queue["required_queue"][0])
        cancelled_b1.update({
            "state": "cancelled", "hold_state": "none",
            "cancelled_at": "2026-08-04T01:00:00Z",
            "cancellation_amendment": "A-CANCEL",
            "transition_receipts": ["audit-amendment-cancel-b1"],
        })
        queue["required_queue"][0] = copy.deepcopy(cancelled_b1)
        queue["state_revision"] = 1
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["pages"][0]["coverage_disposition"] = "deferred"
        coverage["pages"][0]["next_batch"] = None
        coverage["pages"][0]["deferred_reason"] = "approved cancellation"
        coverage["pages"][0]["reentry_condition"] = "new Amendment"
        coverage["batch_specs"] = [
            spec for spec in coverage["batch_specs"] if spec["id"] != "B1"
        ]
        coverage["batch_specs"].append({
            "id": "B3", "family": "Independent", "order_hint": 3,
            "source_route": "R07", "execution_mode": "concurrent-worker",
            "depends_on": ["B2"], "confirmation_required": False,
            "work_spec_path": None, "work_spec_sha256": None,
        })
        coverage["pages"][1]["next_batch"] = "B3"
        compiled, _ = compile_queue.compile_document(queue, coverage)
        diff = compile_queue.replan_diff(
            queue, compiled, "sha256:" + ("a" * 64))
        result = compile_queue._build_replanned_queue(queue, compiled, diff)
        items = {item["id"]: item for item in result["required_queue"]}
        self.assertEqual(cancelled_b1, items["B1"])
        self.assertEqual("queued", items["B3"]["state"])
        self.assertEqual(1, items["B1"]["order"])
        self.assertEqual([1, 2, 3], sorted(
            item["order"] for item in result["required_queue"]))

    def test_absent_inflight_item_is_an_explicit_conflict(self):
        queue = {
            "task_id": "t", "queue_revision": 4, "state_revision": 2,
            "required_queue": [{
                "id": "B1", "state": "open", "order": 1,
                "family": "Core", "record_count": 1,
                "manifest": ["Topics/A.md"], "source_route": "R03",
                "execution_mode": "concurrent-worker", "depends_on": [],
                "confirmation_required": False,
                "work_spec_path": None, "work_spec_sha256": None,
            }],
        }
        proposal = copy.deepcopy(queue)
        proposal["required_queue"] = []
        diff = compile_queue.replan_diff(
            queue, proposal, "sha256:" + "a" * 64)
        self.assertEqual("B1", diff["remove_candidates"][0]["id"])
        self.assertIn("in-flight work cannot be removed", diff["conflicts"][0])

    def test_terminal_only_history_needs_no_current_batch_spec(self):
        queue = self.load(check_queue.QUEUE_PATH)
        queue["required_queue"] = [copy.deepcopy(queue["required_queue"][0])]
        queue["required_queue"][0]["state"] = "closed"
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["batch_specs"] = []
        for page in coverage["pages"]:
            page["coverage_disposition"] = "deferred"
            page["next_batch"] = None
        proposal, _ = compile_queue.compile_document(queue, coverage)
        diff = compile_queue.replan_diff(
            queue, proposal, "sha256:" + "b" * 64)
        self.assertEqual([], proposal["required_queue"])
        self.assertIs(False, diff["has_structural_changes"])
        self.assertEqual(["B1"], diff["preserved_closed_ids"])
        self.assertEqual([], diff["remove_candidates"])

    def test_new_and_queued_orders_fill_around_fixed_terminal_order(self):
        queue = {
            "required_queue": [
                {"id": "Q", "state": "queued", "order": 1,
                 "depends_on": []},
                {"id": "H", "state": "closed", "order": 2,
                 "depends_on": []},
            ],
        }
        compiled = [
            {"id": "A", "state": "queued", "order": 1,
             "depends_on": []},
            {"id": "Q", "state": "queued", "order": 2,
             "depends_on": ["A"]},
        ]
        result = compile_queue._assign_replan_orders(queue, compiled)
        self.assertEqual({"A": 1, "Q": 3},
                         {item["id"]: item["order"] for item in result})
        self.assertEqual(2, queue["required_queue"][1]["order"])

    def test_registration_rejects_nonqueued_structure_change(self):
        # K13/08 Batch Reference Settlement: a sealed item's structure can
        # never change again, so the edit is history-versus-stale-row rather
        # than a proposal.  It is refused and named, and the Queue is
        # untouched -- but it does not become a conflict, because a conflict
        # on a terminal row wedges every later replan behind something no
        # Amendment can resolve (the 3.6.4 ownership transfer did exactly
        # that to a real adopter).
        self.close_b1()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        self.batch_spec(coverage, "B1")["family"] = "Changed after close"
        proposal_relative = self.write_proposal(coverage)
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.add_amendment(
            proposal_relative, expect_success=False)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("terminal batch(es) B1", completed.stdout)
        self.assertIn("K13/08", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_terminal_spec_row_does_not_block_an_unrelated_replan(self):
        # The incident this settles: a stale spec row on a closed batch made
        # every later scope replan fail with an unresolvable conflict.
        self.close_b1()
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        self.batch_spec(coverage, "B1")["family"] = "Changed after close"
        self.batch_spec(coverage, "B2")["family"] = "Legitimate change"
        proposal_relative = self.write_proposal(coverage)
        completed = self.add_amendment(proposal_relative)
        self.assertEqual(0, completed.returncode, completed.stdout)

    def test_registration_rejects_remove_candidate(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        coverage["pages"][1]["batch"] = "B1"
        coverage["pages"][1]["next_batch"] = "B1"
        coverage["batch_specs"] = [spec for spec in coverage["batch_specs"]
                                   if spec["id"] != "B2"]
        proposal_relative = self.write_proposal(coverage)
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.add_amendment(
            proposal_relative, expect_success=False)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("absent from the proposal", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_consumed_replan_diff_must_match_current_inputs(self):
        coverage_path = self.root / check_queue.COVERAGE_PATH
        coverage = kblib.load_yaml_file(coverage_path)
        self.batch_spec(coverage, "B2")["family"] = "First proposal"
        proposal_relative = self.write_proposal(coverage)
        proposed = self.command(
            "--coverage-proposal", proposal_relative,
            "--output", ".cambium/tmp/replan.yaml")
        self.assertEqual(0, proposed.returncode, proposed.stdout)
        coverage = self.load(proposal_relative)
        self.batch_spec(coverage, "B2")["family"] = "Changed after proposal"
        self.write_proposal(coverage)
        self.add_amendment(proposal_relative)
        before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.apply_replan(
            proposal_relative, "A-REPLAN",
            "--replan-diff", ".cambium/tmp/replan.yaml")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("does not match", completed.stdout)
        self.assertEqual(before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_proposal_dry_run_does_not_pre_edit_canonical_coverage(self):
        canonical_before = (self.root / check_queue.COVERAGE_PATH).read_bytes()
        coverage = self.load(check_queue.COVERAGE_PATH)
        self.batch_spec(coverage, "B2")["family"] = "Proposed only"
        proposal_relative = self.write_proposal(coverage)
        completed = self.command("--coverage-proposal", proposal_relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("has_structural_changes: true", completed.stdout)
        self.assertEqual(
            canonical_before,
            (self.root / check_queue.COVERAGE_PATH).read_bytes(),
        )

    def test_direct_canonical_coverage_edit_is_fail_closed(self):
        clean = self.load(check_queue.COVERAGE_PATH)
        proposal_relative = self.write_proposal(copy.deepcopy(clean))
        self.batch_spec(clean, "B2")["family"] = "Illicit direct edit"
        (self.root / check_queue.COVERAGE_PATH).write_text(
            kblib.canonical_yaml(clean), encoding="utf-8")
        queue_before = (self.root / check_queue.QUEUE_PATH).read_bytes()
        completed = self.command("--coverage-proposal", proposal_relative)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("current runtime state is inconsistent", completed.stdout)
        self.assertEqual(
            queue_before, (self.root / check_queue.QUEUE_PATH).read_bytes())

    def test_same_scope_proposal_rejects_page_metadata_change(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["pages"][1]["priority"] = "P0"
        proposal_relative = self.write_proposal(coverage)
        completed = self.command("--coverage-proposal", proposal_relative)
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("only batch/next_batch may change", completed.stdout)

    def test_same_scope_proposal_cannot_change_maintenance_candidates(self):
        current = self.load(check_queue.COVERAGE_PATH)
        proposal = copy.deepcopy(current)
        proposal["maintenance_candidates"] = [{
            "candidate_id": "candidate-sha256:" + "0" * 64,
            "object_path": "Topics/A.md",
        }]
        with self.assertRaisesRegex(
                ValueError, "may not change maintenance_candidates"):
            compile_queue.validate_same_scope_proposal(current, proposal)

    def test_replan_after_invalidation_copies_archived_delta_evidence(self):
        self.merge_then_invalidate_b1()
        before = check_queue.validate_runtime(self.root)
        self.assertEqual([], before["errors"])
        invalidation = before["items_by_id"]["B1"]["invalidation_history"][0]
        self.assertTrue((self.root / invalidation["delta_archive_path"]).is_file())

        coverage = self.load(check_queue.COVERAGE_PATH)
        self.batch_spec(coverage, "B2")["family"] = "Replanned after rollback"
        amendment_id = "A-AFTER-INVALIDATION"
        proposal_relative = self.write_proposal(coverage, amendment_id)
        self.add_amendment(proposal_relative, amendment_id)
        completed = self.apply_replan(proposal_relative, amendment_id)
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual(
            invalidation,
            result["items_by_id"]["B1"]["invalidation_history"][0],
        )
        self.assertEqual("Replanned after rollback",
                         result["items_by_id"]["B2"]["family"])

    def test_replan_after_scope_amendment_copies_plan_and_proposal(self):
        self.apply_scope_amendment()
        adopted = check_queue.validate_runtime(self.root)
        self.assertEqual([], adopted["errors"])
        cross_ledger = next(
            entry for entry in adopted["progress"]["amendments"]
            if entry.get("operation") == "scope-replan")
        self.assertTrue((self.root / cross_ledger["plan_path"]).is_file())
        self.assertTrue(
            (self.root / cross_ledger["coverage_proposal_path"]).is_file())

        coverage = self.load(check_queue.COVERAGE_PATH)
        self.batch_spec(coverage, "B3")["family"] = "Replanned after adoption"
        amendment_id = "A-AFTER-SCOPE"
        proposal_relative = self.write_proposal(coverage, amendment_id)
        self.add_amendment(proposal_relative, amendment_id)
        completed = self.apply_replan(proposal_relative, amendment_id)
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("Replanned after adoption",
                         result["items_by_id"]["B3"]["family"])

    def _transaction_fixture(self):
        paths = {
            "coverage": str(self.root / check_queue.COVERAGE_PATH),
            "queue": str(self.root / check_queue.QUEUE_PATH),
            "progress": str(self.root / check_queue.PROGRESS_PATH),
        }
        before = {
            name: Path(path).read_text(encoding="utf-8")
            for name, path in paths.items()
        }
        after = copy.deepcopy(before)
        coverage = kblib.parse_yaml_subset(after["coverage"])
        coverage["updated_at"] = "2026-08-05T00:00:00Z"
        after["coverage"] = kblib.canonical_yaml(coverage)
        queue = kblib.parse_yaml_subset(after["queue"])
        queue["queue_revision"] += 1
        after["queue"] = kblib.canonical_yaml(queue)
        progress = kblib.parse_yaml_subset(after["progress"])
        progress["queue_revision"] += 1
        after["progress"] = kblib.canonical_yaml(progress)
        receipt = {
            "receipt_id": "audit-commit", "result": "pass",
            "invalidated_by": None,
        }
        operation = {
            "tool": "compile_queue", "action": "apply-replan",
            "before_coverage_sha256": kblib.sha256_bytes(before["coverage"]),
            "before_required_queue_sha256": kblib.sha256_bytes(before["queue"]),
            "before_progress_sha256": kblib.sha256_bytes(before["progress"]),
            "planned_after_coverage_sha256": kblib.sha256_bytes(after["coverage"]),
            "planned_after_required_queue_sha256": kblib.sha256_bytes(after["queue"]),
            "planned_after_progress_sha256": kblib.sha256_bytes(after["progress"]),
            "receipt_id": "audit-prepare",
            "prepare_receipt_id": "audit-prepare",
            "commit_receipt_id": "audit-commit",
            "abort_receipt_id": "audit-abort",
            "receipt_path": ".cambium/receipts/queue-structure.jsonl",
        }
        validation = check_queue.validate_runtime(str(self.root))
        self.assertEqual([], validation["errors"])
        authority = check_queue.runtime_authority_context(validation)
        return paths, before, after, receipt, operation, authority

    def test_full_rollback_clears_lock_and_restores_all_state(self):
        paths, before, after, receipt, operation, authority = \
            self._transaction_fixture()
        original = kblib.atomic_write_text
        failed = {"progress": False}

        def flaky(path, text, validator=None):
            if (path == paths["progress"] and text == after["progress"] and
                    not failed["progress"]):
                failed["progress"] = True
                raise OSError("injected progress write failure")
            return original(path, text, validator=validator)

        with mock.patch.object(kblib, "atomic_write_text", side_effect=flaky):
            with self.assertRaises(OSError):
                compile_queue._commit_state(
                    str(self.root), paths, before, after,
                    ("coverage", "queue", "progress"),
                    self.root / ".cambium/receipts/queue-structure.jsonl",
                    {"receipt_id": "audit-prepare"}, receipt,
                    {"receipt_id": "audit-abort"}, operation, authority,
                )
        for name, path in paths.items():
            self.assertEqual(before[name], Path(path).read_text(encoding="utf-8"))
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_locked_prevalidation_rejection_clears_false_lock(self):
        paths, before, after, receipt, operation, authority = \
            self._transaction_fixture()
        with mock.patch.object(
                compile_queue.check_queue, "validate_runtime",
                return_value={"errors": ["injected concurrent drift"]}):
            with self.assertRaisesRegex(ValueError, "runtime changed before write"):
                compile_queue._commit_state(
                    str(self.root), paths, before, after,
                    ("coverage", "queue", "progress"),
                    self.root / ".cambium/receipts/queue-structure.jsonl",
                    {"receipt_id": "audit-prepare"}, receipt,
                    {"receipt_id": "audit-abort"}, operation, authority,
                )
        for name, path in paths.items():
            self.assertEqual(
                before[name], Path(path).read_text(encoding="utf-8"))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())
        self.assertFalse(
            (self.root / ".cambium/receipts/queue-structure.jsonl").exists())

    def test_incomplete_rollback_retains_lock_for_restart_reconciliation(self):
        paths, before, after, receipt, operation, authority = \
            self._transaction_fixture()
        original = kblib.atomic_write_text
        failed = {"progress": False}

        def flaky(path, text, validator=None):
            if (path == paths["progress"] and text == after["progress"] and
                    not failed["progress"]):
                failed["progress"] = True
                raise OSError("injected progress write failure")
            if (failed["progress"] and path == paths["coverage"] and
                    text == before["coverage"]):
                raise OSError("injected Coverage rollback failure")
            return original(path, text, validator=validator)

        with mock.patch.object(kblib, "atomic_write_text", side_effect=flaky):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                compile_queue._commit_state(
                    str(self.root), paths, before, after,
                    ("coverage", "queue", "progress"),
                    self.root / ".cambium/receipts/queue-structure.jsonl",
                    {"receipt_id": "audit-prepare"}, receipt,
                    {"receipt_id": "audit-abort"}, operation, authority,
                )
        lock = self.root / ".cambium/tmp/state-writer.lock/owner.json"
        self.assertTrue(lock.is_file())
        owner = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual("apply-replan", owner["operation"]["action"])
        resume = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, resume.returncode, resume.stdout)
        self.assertIn("state.coverage phase=planned-after", resume.stdout)
        self.assertIn("state.queue phase=before", resume.stdout)
        self.assertIn("state.progress phase=before", resume.stdout)
        self.assertIn("operation_receipt", resume.stdout)

    def test_durable_orphan_commit_receipt_retains_recovery_lock(self):
        paths, before, after, receipt, operation, authority = \
            self._transaction_fixture()
        receipt_path = (
            self.root / ".cambium/receipts/queue-structure.jsonl"
        )
        real_append = kblib.write_receipts

        def append_commit_then_fail(path, receipts, **kwargs):
            real_append(path, receipts, **kwargs)
            if any(record.get("receipt_id") == "audit-commit"
                   for record in receipts):
                raise OSError("injected error after durable commit receipt")

        with mock.patch.object(
                compile_queue.check_queue, "validate_runtime",
                return_value={"errors": []}), \
                mock.patch.object(
                    kblib, "write_receipts",
                    side_effect=append_commit_then_fail):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                compile_queue._commit_state(
                    str(self.root), paths, before, after,
                    ("coverage", "queue", "progress"), receipt_path,
                    {"receipt_id": "audit-prepare"}, receipt,
                    {"receipt_id": "audit-abort"}, operation, authority,
                )

        for name, path in paths.items():
            self.assertEqual(before[name], Path(path).read_text(encoding="utf-8"))
        records = [json.loads(line) for line in
                   receipt_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(
            ["audit-prepare", "audit-commit", "audit-abort"],
            [record["receipt_id"] for record in records],
        )
        self.assertTrue((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())
        resume = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertIn("audit-commit", resume.stdout)
        self.assertIn("state.coverage phase=before", resume.stdout)
        self.assertIn("state.queue phase=before", resume.stdout)
        self.assertIn("state.progress phase=before", resume.stdout)

    def test_partial_commit_receipt_retains_lock_and_corruption_evidence(self):
        paths, before, after, receipt, operation, authority = \
            self._transaction_fixture()
        receipt_path = (
            self.root / ".cambium/receipts/queue-structure.jsonl"
        )
        real_os_write = kblib.os.write

        def truncate_commit(fd, data):
            payload = bytes(data)
            if b'"receipt_id": "audit-commit"' in payload:
                fragment = payload[:max(1, len(payload) // 2)]
                real_os_write(fd, fragment)
                return len(fragment)
            return real_os_write(fd, payload)

        with mock.patch.object(
                compile_queue.check_queue, "validate_runtime",
                return_value={"errors": []}), \
                mock.patch.object(kblib.os, "write",
                                  side_effect=truncate_commit):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                compile_queue._commit_state(
                    str(self.root), paths, before, after,
                    ("coverage", "queue", "progress"), receipt_path,
                    {"receipt_id": "audit-prepare"}, receipt,
                    {"receipt_id": "audit-abort"}, operation, authority,
                )

        for name, path in paths.items():
            self.assertEqual(before[name], Path(path).read_text(encoding="utf-8"))
        self.assertIn(b'audit-commit', receipt_path.read_bytes())
        self.assertTrue((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())
        resume = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertIn("audit-commit", resume.stdout)
        self.assertIn("lock=.cambium/tmp/state-writer.lock", resume.stdout)

    def test_prepare_proven_absent_allows_clean_failure_unlock(self):
        paths, before, after, receipt, operation, authority = \
            self._transaction_fixture()
        receipt_path = (
            self.root / ".cambium/receipts/queue-structure.jsonl"
        )

        # Keep a non-recursive reference because the patched attribute is the
        # same shared module object used by compile_queue.
        real_append = kblib.write_receipts

        def guarded(path, receipts, **kwargs):
            if any(record.get("receipt_id") == "audit-prepare"
                   for record in receipts):
                raise OSError("injected pre-append prepare failure")
            return real_append(path, receipts, **kwargs)

        with mock.patch.object(kblib, "write_receipts", side_effect=guarded):
            with self.assertRaisesRegex(OSError, "pre-append prepare"):
                compile_queue._commit_state(
                    str(self.root), paths, before, after,
                    ("coverage", "queue", "progress"), receipt_path,
                    {"receipt_id": "audit-prepare"}, receipt,
                    {"receipt_id": "audit-abort"}, operation, authority,
                )

        for name, path in paths.items():
            self.assertEqual(before[name], Path(path).read_text(encoding="utf-8"))
        self.assertFalse(receipt_path.exists())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists()
        )

    def test_prepare_present_but_abort_absent_retains_lock(self):
        paths, before, after, receipt, operation, authority = \
            self._transaction_fixture()
        receipt_path = (
            self.root / ".cambium/receipts/queue-structure.jsonl"
        )
        real_atomic = kblib.atomic_write_text
        real_append = kblib.write_receipts
        failed = {"progress": False}

        def fail_state(path, text, validator=None):
            if (path == paths["progress"] and text == after["progress"] and
                    not failed["progress"]):
                failed["progress"] = True
                raise OSError("injected state failure")
            return real_atomic(path, text, validator=validator)

        def fail_abort(path, receipts, **kwargs):
            if any(record.get("receipt_id") == "audit-abort"
                   for record in receipts):
                raise OSError("injected abort append failure")
            return real_append(path, receipts, **kwargs)

        with mock.patch.object(kblib, "atomic_write_text",
                               side_effect=fail_state), \
                mock.patch.object(kblib, "write_receipts",
                                  side_effect=fail_abort):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                compile_queue._commit_state(
                    str(self.root), paths, before, after,
                    ("coverage", "queue", "progress"), receipt_path,
                    {"receipt_id": "audit-prepare"}, receipt,
                    {"receipt_id": "audit-abort"}, operation, authority,
                )

        for name, path in paths.items():
            self.assertEqual(before[name], Path(path).read_text(encoding="utf-8"))
        self.assertEqual(
            ["audit-prepare"],
            [json.loads(line)["receipt_id"] for line in
             receipt_path.read_text(encoding="utf-8").splitlines()],
        )
        self.assertTrue((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())


if __name__ == "__main__":
    unittest.main()
