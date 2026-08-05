from pathlib import Path
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS))

import apply_amendment
import check_queue
import kblib


class ApplyAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        self.amendment_dir = self.root / ".cambium/deltas/amendments"
        self.amendment_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def write_yaml(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(data), encoding="utf-8")
        return path

    def shas(self):
        return {
            "coverage": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "progress": kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            "queue": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
        }

    def assert_resume_envelope(self, completed, next_action="repair-runtime"):
        """Assert that one fresh resume read exposes the whole recovery fact."""
        result = check_queue.validate_runtime(self.root)
        for expected in (
                "task_id=fixture-task",
                'objective="Complete fixture Required Queue batches with durable evidence."',
                'exclusions=["Do not modify profile policy."]',
                "live.coverage_sha256=%s" % result.get("coverage_sha256"),
                "live.progress_sha256=%s" % result.get("progress_sha256"),
                "live.required_queue_sha256=%s" % result.get("queue_sha256"),
                "checkpoint.recorded_at=", "checkpoint.summary=",
                "checkpoint.binding=", "lock=.cambium/tmp/state-writer.lock"):
            self.assertIn(expected, completed.stdout)
        self.assertTrue(any(
            line.startswith("  deltas=") or line.startswith("  delta=")
            for line in completed.stdout.splitlines()), completed.stdout)
        self.assertEqual(
            ["next_action=%s" % next_action],
            [line for line in completed.stdout.splitlines()
             if line.startswith("next_action=")],
            completed.stdout,
        )

    def add_progress_amendment(self, plan, amendment_id=None, **overrides):
        progress = self.load(check_queue.PROGRESS_PATH)
        amendment = {
            "id": amendment_id or plan["amendment_id"],
            "date": "2026-08-04",
            "summary": "approved cross-Ledger Amendment",
            "status": "approved",
            "writeback_done": False,
        }
        for amendment_field, plan_field in \
                apply_amendment.AMENDMENT_BINDINGS.items():
            amendment[amendment_field] = copy.deepcopy(plan[plan_field])
        amendment.update(overrides)
        progress["amendments"].append(amendment)
        self.write_yaml(check_queue.PROGRESS_PATH, progress)

    def make_plan(self, operation, proposal, affected_pages,
                  affected_batches, cancel_batch_id=None):
        amendment_id = ("A-CANCEL-001" if operation == "cancel-batch"
                        else "A-SCOPE-001")
        proposal_rel = ".cambium/deltas/amendments/%s.coverage.yaml" % amendment_id
        proposal_path = self.write_yaml(proposal_rel, proposal)
        queue = self.load(check_queue.QUEUE_PATH)
        plan = {
            "schema_version": 1,
            "amendment_id": amendment_id,
            "operation": operation,
            "affected_pages": sorted(affected_pages),
            "affected_batches": sorted(affected_batches),
            "scope_version_before": queue["scope_version"],
            "scope_version_after": proposal["scope_version"],
            "queue_revision_before": queue["queue_revision"],
            "queue_revision_after": queue["queue_revision"] + 1,
            "state_revision_before": queue["state_revision"],
            "state_revision_after": (queue["state_revision"] + 1
                                     if operation == "cancel-batch"
                                     else queue["state_revision"]),
            "coverage_proposal_path": proposal_rel,
            "coverage_proposal_sha256": kblib.sha256_file(proposal_path),
            "cancel_batch_id": cancel_batch_id,
        }
        plan_rel = ".cambium/deltas/amendments/%s.yaml" % amendment_id
        self.write_yaml(plan_rel, plan)
        return plan_rel, plan

    def command(self, plan_rel, shas, *extra):
        return subprocess.run(
            [sys.executable, str(TOOLS / "apply_amendment.py"),
             str(self.root), "--plan", plan_rel,
             "--expected-coverage-sha256", shas["coverage"],
             "--expected-progress-sha256", shas["progress"],
             "--expected-queue-sha256", shas["queue"], *extra],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def scope_proposal(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-04T12:00:00Z"
        coverage["batch_specs"].append({
            "id": "B3", "family": "Core", "order_hint": 3,
            "source_route": "R03", "execution_mode": "concurrent-worker",
            "depends_on": ["B2"], "confirmation_required": False,
        })
        coverage["pages"].append({
            "path": "Topics/C.md", "coverage_disposition": "required",
            "canonical_owner": "Topics/C.md", "type": "concept",
            "priority": "P1", "tier": "M", "authoring_status": "drafted",
            "prerequisites": ["Topics/B.md"], "batch": "B3",
            "next_batch": "B3", "deferred_reason": None,
            "reentry_condition": None, "gate_receipts": [],
        })
        return coverage

    def cancel_proposal(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-04T12:00:00Z"
        coverage["batch_specs"] = [
            spec for spec in coverage["batch_specs"] if spec["id"] != "B2"
        ]
        page = next(entry for entry in coverage["pages"]
                    if entry["path"] == "Topics/B.md")
        page["coverage_disposition"] = "deferred"
        page["next_batch"] = None
        page["deferred_reason"] = "removed by approved scope Amendment"
        page["reentry_condition"] = "a successor Amendment restores scope"
        return coverage

    def open_b2(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        next(spec for spec in coverage["batch_specs"]
             if spec["id"] == "B2")["depends_on"] = []
        self.write_yaml(check_queue.COVERAGE_PATH, coverage)
        queue = self.load(check_queue.QUEUE_PATH)
        next(item for item in queue["required_queue"]
             if item["id"] == "B2")["depends_on"] = []
        queue_text = kblib.canonical_yaml(queue)
        (self.root / check_queue.QUEUE_PATH).write_text(
            queue_text, encoding="utf-8")
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["required_queue_sha256"] = kblib.sha256_bytes(queue_text)
        self.write_yaml(check_queue.PROGRESS_PATH, progress)
        origin_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        origin_records = [json.loads(line) for line in origin_path.read_text(
            encoding="utf-8").splitlines()]
        for record in origin_records:
            if record.get("receipt_id") == "audit-fixture-initial-queue":
                record["after_required_queue_sha256"] = kblib.sha256_file(
                    self.root / check_queue.QUEUE_PATH)
                record["after_coverage_sha256"] = kblib.sha256_file(
                    self.root / check_queue.COVERAGE_PATH)
        origin_path.write_text("".join(json.dumps(record) + "\n"
                                       for record in origin_records),
                               encoding="utf-8")

        ready_path = self.root / ".cambium/receipts/open-ready.jsonl"
        ready = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--require-ready", "B2", "--receipts",
             ".cambium/receipts/open-ready.jsonl"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        self.assertEqual(0, ready.returncode, ready.stdout)
        ready_receipt = json.loads(ready_path.read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]
        queue = self.load(check_queue.QUEUE_PATH)
        opened = subprocess.run(
            [sys.executable, str(TOOLS / "update_queue.py"), str(self.root),
             "--id", "B2", "--transition", "open", "--gate-receipt",
             ready_receipt, "--expected-state-revision",
             str(queue["state_revision"]), "--expected-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        self.assertEqual(0, opened.returncode, opened.stdout)

    def install_interrupted_prepare(self, mutate_receipt=None):
        """Materialize one recoverable amendment crash fixture."""
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        prepared = apply_amendment._prepare_result(
            str(self.root), plan_rel, self.shas())
        receipt = copy.deepcopy(prepared["prepare"])
        if mutate_receipt is not None:
            mutate_receipt(receipt)
        kblib.write_receipts(
            self.root / apply_amendment.RECEIPT_PATH, [receipt])
        (self.root / check_queue.COVERAGE_PATH).write_text(
            prepared["after_text"]["coverage"], encoding="utf-8")
        operation = apply_amendment._lock_operation(
            plan, prepared["transaction_id"], prepared["plan_sha"],
            prepared["before_sha"], prepared["after_sha"],
            prepared["prepare"]["receipt_id"],
            prepared["transaction_sequence"],
            prepared["previous_transaction_commit_receipt"],
            prepared["task_id"], plan_path=plan_rel,
            receipt_path=apply_amendment.RECEIPT_PATH,
        )
        lock = self.root / ".cambium/tmp/state-writer.lock"
        lock.mkdir()
        (lock / "owner.json").write_text(json.dumps({
            "lock_name": "state-writer", "pid": 999999,
            "created_at": "2026-08-04T12:00:00Z",
            "operation": operation,
        }) + "\n", encoding="utf-8")
        return plan_rel, plan, prepared, operation

    def test_scope_replan_adds_new_required_object_atomically(self):
        # This test intentionally starts from queued-only history.  Preservation
        # of terminal items is compile_queue's separate history-merge contract;
        # apply_amendment consumes that helper instead of duplicating it here.
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        dry = self.command(plan_rel, before)
        self.assertEqual(0, dry.returncode, dry.stdout)
        self.assertIn("dry run", dry.stdout)
        self.assertEqual(before, self.shas())

        completed = self.command(
            plan_rel, before, "--actor-role", "integrator", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("s2", result["queue"]["scope_version"])
        self.assertEqual(2, result["queue"]["queue_revision"])
        self.assertEqual(0, result["queue"]["state_revision"])
        self.assertEqual(["Topics/C.md"],
                         result["items_by_id"]["B3"]["manifest"])
        amendment = next(entry for entry in result["progress"]["amendments"]
                         if entry.get("id") == plan["amendment_id"])
        self.assertEqual("verified", amendment["status"])
        self.assertIs(True, amendment["writeback_done"])
        self.assertEqual(plan_rel, amendment["plan_path"])
        self.assertEqual(kblib.sha256_file(self.root / plan_rel),
                         amendment["plan_sha256"])
        self.assertEqual(plan["coverage_proposal_path"],
                         amendment["coverage_proposal_path"])
        self.assertEqual(kblib.sha256_file(
            self.root / plan["coverage_proposal_path"]),
            amendment["coverage_proposal_sha256"])
        receipts = [json.loads(line) for line in (
            self.root / apply_amendment.RECEIPT_PATH).read_text(
                encoding="utf-8").splitlines()]
        self.assertEqual(["prepare", "commit"],
                         [receipt["transaction_phase"]
                          for receipt in receipts])
        commit = receipts[-1]
        for field in ("plan_path", "plan_sha256",
                      "coverage_proposal_path",
                      "coverage_proposal_sha256"):
            self.assertEqual(amendment[field], commit[field])

    def test_verified_amendment_receipt_revision_must_match_plan(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        completed = self.command(
            plan_rel, self.shas(), "--actor-role", "integrator", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        commit = next(receipt for receipt in receipts
                      if receipt.get("transaction_phase") == "commit")
        commit["queue_revision_after"] = 999
        receipt_path.write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        errors = check_queue.validate_runtime(self.root)["errors"]
        self.assertTrue(any(
            "queue_revision_after=999" in error or
            "queue revision does not match its Amendment" in error or
            "points beyond the live Queue revision" in error
            for error in errors), errors)

    def test_plan_and_proposal_must_stay_in_amendment_namespace(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        outside_plan = ".cambium/deltas/A-SCOPE-OUTSIDE.yaml"
        self.write_yaml(outside_plan, plan)
        rejected = self.command(outside_plan, self.shas())
        self.assertEqual(1, rejected.returncode, rejected.stdout)
        self.assertIn("inside .cambium/deltas/amendments", rejected.stdout)

        outside_proposal = ".cambium/deltas/A-SCOPE-OUTSIDE.coverage.yaml"
        proposal_path = self.write_yaml(outside_proposal, self.scope_proposal())
        plan["coverage_proposal_path"] = outside_proposal
        plan["coverage_proposal_sha256"] = kblib.sha256_file(proposal_path)
        self.write_yaml(plan_rel, plan)
        rejected = self.command(plan_rel, self.shas())
        self.assertEqual(1, rejected.returncode, rejected.stdout)
        self.assertIn("inside .cambium/deltas/amendments", rejected.stdout)

    def test_tampered_coverage_proposal_is_rejected_before_transaction(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        proposal_path = self.root / plan["coverage_proposal_path"]
        proposal_path.write_text(
            proposal_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        before = self.shas()
        rejected = self.command(plan_rel, before)
        self.assertEqual(1, rejected.returncode, rejected.stdout)
        self.assertIn("Coverage proposal SHA does not match plan",
                      rejected.stdout)
        self.assertEqual(before, self.shas())

    def test_cancel_leaf_batch_updates_all_three_ledgers(self):
        plan_rel, plan = self.make_plan(
            "cancel-batch", self.cancel_proposal(),
            ["Topics/B.md"], ["B2"], cancel_batch_id="B2")
        self.add_progress_amendment(plan)
        before = self.shas()
        completed = self.command(
            plan_rel, before, "--actor-role", "integrator", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        cancelled = result["items_by_id"]["B2"]
        self.assertEqual("cancelled", cancelled["state"])
        self.assertEqual(plan["amendment_id"],
                         cancelled["cancellation_amendment"])
        self.assertEqual(1, result["queue"]["state_revision"])
        transition_id = cancelled["transition_receipts"][-1]
        transition = result["receipt_catalog"][transition_id][1]
        self.assertEqual("apply_amendment", transition["tool"])
        page = next(entry for entry in result["coverage"]["pages"]
                    if entry["path"] == "Topics/B.md")
        self.assertEqual("deferred", page["coverage_disposition"])
        self.assertIsNone(page["next_batch"])

    def test_planned_all_cancelled_task_can_enter_build_completion_candidate(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["batch_specs"] = [
            spec for spec in coverage["batch_specs"] if spec["id"] == "B2"
        ]
        coverage["batch_specs"][0]["order_hint"] = 1
        coverage["batch_specs"][0]["depends_on"] = []
        coverage["pages"] = [
            page for page in coverage["pages"] if page["path"] == "Topics/B.md"
        ]
        queue = self.load(check_queue.QUEUE_PATH)
        queue["required_queue"] = [
            item for item in queue["required_queue"] if item["id"] == "B2"
        ]
        queue["required_queue"][0]["order"] = 1
        queue["required_queue"][0]["depends_on"] = []
        self.write_yaml(check_queue.COVERAGE_PATH, coverage)
        queue_text = kblib.canonical_yaml(queue)
        (self.root / check_queue.QUEUE_PATH).write_text(
            queue_text, encoding="utf-8")

        progress = self.load(check_queue.PROGRESS_PATH)
        progress["task_state"] = "planned"
        progress["task_transition_receipts"] = []
        progress["required_queue_sha256"] = kblib.sha256_bytes(queue_text)
        progress["checkpoint"] = {
            "recorded_at": None,
            "summary": None,
            "task_state": "planned",
            "task_transition_receipt": None,
            "coverage_sha256": None,
            "required_queue_sha256": None,
            "queue_revision": queue["queue_revision"],
            "queue_state_revision": queue["state_revision"],
        }
        self.write_yaml(check_queue.PROGRESS_PATH, progress)
        progress_sha = kblib.sha256_file(
            self.root / check_queue.PROGRESS_PATH)
        receipts_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        records = [json.loads(line) for line in receipts_path.read_text(
            encoding="utf-8").splitlines()]
        records = [record for record in records
                   if record.get("tool") != "update_task"]
        initial = next(record for record in records
                       if record.get("receipt_id") ==
                       "audit-fixture-initial-queue")
        initial["after_required_queue_sha256"] = kblib.sha256_file(
            self.root / check_queue.QUEUE_PATH)
        initial["after_coverage_sha256"] = kblib.sha256_file(
            self.root / check_queue.COVERAGE_PATH)
        initial["after_progress_sha256"] = progress_sha
        receipts_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

        plan_rel, plan = self.make_plan(
            "cancel-batch", self.cancel_proposal(),
            ["Topics/B.md"], ["B2"], cancel_batch_id="B2")
        self.add_progress_amendment(plan)
        completed = self.command(
            plan_rel, self.shas(), "--actor-role", "integrator", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        self.assertEqual("planned", runtime["progress"]["task_state"])
        self.assertEqual(0, runtime["remaining"])

        register = ".cambium/receipts/planned-complete.jsonl"
        gate = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--require-complete", "--receipts", register],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, gate.returncode, gate.stdout)
        gate_id = json.loads((self.root / register).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]
        transition = subprocess.run(
            [sys.executable, str(TOOLS / "update_task.py"), str(self.root),
             "--transition", "completion-candidate",
             "--queue-check-receipt", gate_id,
             "--checkpoint-summary", "all planned work cancelled by Amendment",
             "--expected-progress-sha256",
             kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
             "--expected-queue-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, transition.returncode, transition.stdout)
        resumed = check_queue.validate_runtime(self.root)
        self.assertEqual([], resumed["errors"])
        self.assertEqual(
            "completion-candidate", resumed["progress"]["task_state"])

    def test_cancel_open_leaf_batch_preserves_transition_history(self):
        self.open_b2()
        plan_rel, plan = self.make_plan(
            "cancel-batch", self.cancel_proposal(),
            ["Topics/B.md"], ["B2"], cancel_batch_id="B2")
        self.add_progress_amendment(plan)
        completed = self.command(
            plan_rel, self.shas(), "--actor-role", "integrator", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        cancelled = result["items_by_id"]["B2"]
        self.assertEqual("cancelled", cancelled["state"])
        self.assertEqual(2, len(cancelled["transition_receipts"]))
        self.assertEqual(2, result["queue"]["state_revision"])

    def test_replan_after_cancellation_preserves_terminal_history(self):
        cancel_rel, cancel_plan = self.make_plan(
            "cancel-batch", self.cancel_proposal(),
            ["Topics/B.md"], ["B2"], cancel_batch_id="B2")
        self.add_progress_amendment(cancel_plan)
        cancelled = self.command(
            cancel_rel, self.shas(), "--actor-role", "integrator", "--apply")
        self.assertEqual(0, cancelled.returncode, cancelled.stdout)

        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["scope_version"] = "s3"
        coverage["updated_at"] = "2026-08-04T13:00:00Z"
        coverage["batch_specs"].append({
            "id": "B3", "family": "Core", "order_hint": 3,
            "source_route": "R03", "execution_mode": "concurrent-worker",
            "depends_on": ["B1"], "confirmation_required": False,
        })
        coverage["pages"].append({
            "path": "Topics/C.md", "coverage_disposition": "required",
            "canonical_owner": "Topics/C.md", "type": "concept",
            "priority": "P1", "tier": "M", "authoring_status": "drafted",
            "prerequisites": ["Topics/A.md"], "batch": "B3",
            "next_batch": "B3", "deferred_reason": None,
            "reentry_condition": None, "gate_receipts": [],
        })
        replan_rel, replan_plan = self.make_plan(
            "scope-replan", coverage, ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(replan_plan)
        replanned = self.command(
            replan_rel, self.shas(), "--actor-role", "integrator", "--apply")
        self.assertEqual(0, replanned.returncode, replanned.stdout)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("cancelled", result["items_by_id"]["B2"]["state"])
        self.assertEqual(["Topics/C.md"],
                         result["items_by_id"]["B3"]["manifest"])
        transactions = [entry for entry in result["progress"]["amendments"]
                        if entry.get("operation") in
                        ("scope-replan", "cancel-batch")]
        self.assertEqual([1, 2], [entry["transaction_sequence"]
                                  for entry in transactions])
        self.assertIsNone(
            transactions[0]["previous_transaction_commit_receipt"])
        self.assertEqual(
            transactions[0]["verification_receipt"],
            transactions[1]["previous_transaction_commit_receipt"])
        transactions[1]["previous_transaction_commit_receipt"] = \
            "audit-not-the-prior-commit"
        self.write_yaml(check_queue.PROGRESS_PATH, result["progress"])
        tampered = check_queue.validate_runtime(self.root)
        self.assertTrue(any("previous transaction commit" in error
                            for error in tampered["errors"]),
                        tampered["errors"])

    def test_unrelated_progress_amendment_is_rejected(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan, amendment_id="A-OTHER")
        completed = self.command(plan_rel, self.shas())
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("exactly one matching Amendment", completed.stdout)

    def test_stale_sha_is_rejected_without_writing(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        stale = dict(before)
        stale["coverage"] = "sha256:" + "0" * 64
        completed = self.command(
            plan_rel, stale, "--actor-role", "integrator", "--apply")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("expected coverage SHA", completed.stdout)
        self.assertEqual(before, self.shas())

    def test_worker_cannot_apply_transaction(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        completed = self.command(plan_rel, before, "--apply")
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("only actor-role integrator", completed.stdout)
        self.assertEqual(before, self.shas())
        self.assertFalse((self.root / apply_amendment.RECEIPT_PATH).exists())

    def test_verified_amendment_cannot_outlive_commit_receipt(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        completed = self.command(
            plan_rel, self.shas(), "--actor-role", "integrator", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        retained = [line for line in receipt_path.read_text(
            encoding="utf-8").splitlines()
            if json.loads(line).get("transaction_phase") != "commit"]
        receipt_path.write_text("\n".join(retained) + "\n", encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        self.assertTrue(any("verification" in error and "missing receipt" in error
                            for error in result["errors"]), result["errors"])

    def test_simulated_crash_leaves_prepare_and_lock_discoverable(self):
        # Simulate a process dying after prepare and the first serial replace.
        plan_rel, plan, prepared, operation = \
            self.install_interrupted_prepare()
        self.assertEqual(plan_rel, operation["plan_path"])
        self.assertEqual(plan["coverage_proposal_path"],
                         operation["coverage_proposal_path"])
        self.assertEqual(plan["coverage_proposal_sha256"],
                         operation["coverage_proposal_sha256"])

        status = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False)
        self.assertEqual(1, status.returncode, status.stdout)
        self.assertIn(prepared["transaction_id"], status.stdout)
        self.assertIn(prepared["prepare"]["receipt_id"], status.stdout)
        self.assertIn("transaction_phase=prepare", status.stdout)
        self.assertIn("planned_after_coverage_sha256", status.stdout)
        self.assertIn("reconcile Queue/Progress/deltas", status.stdout)
        self.assert_resume_envelope(status,
                                    "reconcile-interrupted-write")

    def test_recovery_rejects_semantically_tampered_prepare_receipt(self):
        def corrupt(receipt):
            receipt["result"] = "pass"
            receipt["plan_sha256"] = "sha256:" + "0" * 64

        _, _, prepared, _ = self.install_interrupted_prepare(corrupt)
        status = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False)
        self.assertEqual(1, status.returncode, status.stdout)
        self.assertIn("transaction_phase=receipt-semantic-mismatch",
                      status.stdout)
        self.assertIn("prepare_receipt_matches_owner=False", status.stdout)
        self.assertIn('"plan_sha256"', status.stdout)
        self.assertIn('"result"', status.stdout)
        self.assertIn(prepared["prepare"]["receipt_id"], status.stdout)

    def test_ordinary_partial_write_rolls_back_and_records_abort(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        prepared = apply_amendment._prepare_result(
            str(self.root), plan_rel, before)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        original_write = kblib.atomic_write_text
        calls = {"count": 0}

        def fail_second_replace(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected second-file failure")
            return original_write(*args, **kwargs)

        with mock.patch.object(
                apply_amendment.kblib, "atomic_write_text",
                side_effect=fail_second_replace):
            with self.assertRaisesRegex(OSError, "injected second-file"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        phases = [json.loads(line)["transaction_phase"]
                  for line in receipt_path.read_text(
                      encoding="utf-8").splitlines()]
        self.assertEqual(["prepare", "abort"], phases)
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_durable_orphan_commit_receipt_retains_recovery_lock(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        prepared = apply_amendment._prepare_result(
            str(self.root), plan_rel, before)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        real_append = kblib.write_receipts

        def append_commit_then_fail(path, receipts, **kwargs):
            real_append(path, receipts, **kwargs)
            if any(record.get("transaction_phase") == "commit"
                   for record in receipts):
                raise OSError("injected error after durable commit receipt")

        with mock.patch.object(
                apply_amendment.kblib, "write_receipts",
                side_effect=append_commit_then_fail):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        records = [json.loads(line) for line in
                   receipt_path.read_text(encoding="utf-8").splitlines()]
        phases = [record.get("transaction_phase") for record in records]
        self.assertIn("prepare", phases)
        self.assertIn("commit", phases)
        self.assertIn("abort", phases)
        self.assertTrue((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())
        status = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertIn(prepared["commit"]["receipt_id"], status.stdout)
        self.assertIn("state.coverage phase=before", status.stdout)
        self.assertIn("state.queue phase=before", status.stdout)
        self.assertIn("state.progress phase=before", status.stdout)
        self.assertIn("transaction_phase=abort", status.stdout)
        self.assert_resume_envelope(
            status, next_action="reconcile-interrupted-write")

    def test_commit_without_durable_abort_remains_restart_visible(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        prepared = apply_amendment._prepare_result(
            str(self.root), plan_rel, before)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        real_append = kblib.write_receipts

        def commit_then_refuse_abort(path, receipts, **kwargs):
            phases = {record.get("transaction_phase") for record in receipts}
            if "commit" in phases:
                real_append(path, receipts, **kwargs)
                raise OSError("injected failure after durable commit")
            if "abort" in phases:
                raise OSError("injected abort publication failure")
            return real_append(path, receipts, **kwargs)

        with mock.patch.object(
                apply_amendment.kblib, "write_receipts",
                side_effect=commit_then_refuse_abort):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        phases = [json.loads(line).get("transaction_phase") for line in
                  receipt_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["prepare", "commit"], phases)
        status = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(2, status.returncode, status.stdout)
        self.assertIn("transaction_phase=commit", status.stdout)
        self.assertIn(prepared["commit"]["receipt_id"], status.stdout)
        self.assert_resume_envelope(
            status, next_action="reconcile-interrupted-write")

    def test_partial_commit_receipt_retains_lock_and_corruption_evidence(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        prepared = apply_amendment._prepare_result(
            str(self.root), plan_rel, before)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        commit_id = prepared["commit"]["receipt_id"]
        real_os_write = kblib.os.write

        def truncate_commit(fd, data):
            payload = bytes(data)
            if (commit_id.encode("utf-8") in payload and
                    b'"transaction_phase": "commit"' in payload):
                fragment = payload[:max(1, len(payload) // 2)]
                real_os_write(fd, fragment)
                return len(fragment)
            return real_os_write(fd, payload)

        with mock.patch.object(apply_amendment.kblib.os, "write",
                               side_effect=truncate_commit):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        self.assertIn(commit_id.encode("utf-8"), receipt_path.read_bytes())
        self.assertTrue((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())
        status = subprocess.run(
            [sys.executable, str(TOOLS / "check_queue.py"), str(self.root),
             "--resume-status"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertIn(commit_id, status.stdout)
        self.assertIn("lock=.cambium/tmp/state-writer.lock", status.stdout)

    def test_prepare_proven_absent_allows_clean_failure_unlock(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        prepared = apply_amendment._prepare_result(
            str(self.root), plan_rel, before)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        real_append = kblib.write_receipts

        def fail_prepare(path, receipts, **kwargs):
            if any(record.get("transaction_phase") == "prepare"
                   for record in receipts):
                raise OSError("injected pre-append prepare failure")
            return real_append(path, receipts, **kwargs)

        with mock.patch.object(apply_amendment.kblib, "write_receipts",
                               side_effect=fail_prepare):
            with self.assertRaisesRegex(OSError, "pre-append prepare"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        self.assertFalse(receipt_path.exists())
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists()
        )

    def test_prepare_present_but_abort_absent_retains_lock(self):
        plan_rel, plan = self.make_plan(
            "scope-replan", self.scope_proposal(),
            ["Topics/C.md"], ["B3"])
        self.add_progress_amendment(plan)
        before = self.shas()
        prepared = apply_amendment._prepare_result(
            str(self.root), plan_rel, before)
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        real_atomic = kblib.atomic_write_text
        real_append = kblib.write_receipts
        calls = {"count": 0}

        def fail_second_state(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected second-file failure")
            return real_atomic(*args, **kwargs)

        def fail_abort(path, receipts, **kwargs):
            if any(record.get("transaction_phase") == "abort"
                   for record in receipts):
                raise OSError("injected abort append failure")
            return real_append(path, receipts, **kwargs)

        with mock.patch.object(apply_amendment.kblib, "atomic_write_text",
                               side_effect=fail_second_state), \
                mock.patch.object(apply_amendment.kblib, "write_receipts",
                                  side_effect=fail_abort):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        phases = [json.loads(line)["transaction_phase"] for line in
                  receipt_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["prepare"], phases)
        self.assertTrue((
            self.root / ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())


if __name__ == "__main__":
    unittest.main()
