import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
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
sys.path.insert(0, str(TOOLS))

import adopt_standards
import check_queue
import kblib
import update_queue


class AdoptStandardsTests(unittest.TestCase):
    GOVERNANCE = "kernel/K00 Standards Control/03 Standards Governance.md"
    PLAN = ".cambium/deltas/standards-adoptions/SA-001.yaml"
    RECEIPTS = ".cambium/receipts/standards-adoptions.jsonl"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        governance = self.root / self.GOVERNANCE
        governance.parent.mkdir(parents=True)
        governance.write_text(
            "## Standards Control\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| Standards version | `3.1.0` |\n"
            "| Status | `approved` |\n"
            "| Effective date | `2026-08-05` |\n"
            "| Selected profile manifest | "
            "`profiles/test-profile/profile.md` |\n",
            encoding="utf-8",
        )
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            "## Stable Gate ID Registry\n\n"
            "| Gate ID | Tool | Tool version | Check | Mode |\n"
            "|---|---|---|---|---|\n"
            "| required-queue-consistency | check_queue | 1.4.0 | required_queue | consistency |\n"
            "| required-queue-admission | check_queue | 1.4.0 | required_queue | require-ready:* |\n"
            "| batch-close | check_batch_close | 1.2.0 | batch_close_gate | * |\n",
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def run_tool(self, tool, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / tool), str(self.root), *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def pause(self):
        completed = self.run_tool(
            "update_task.py", "--transition", "paused",
            "--checkpoint-summary", "pause before Standards adoption",
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / check_queue.PROGRESS_PATH),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", "2026-08-05T00:03:00Z",
            "--apply",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)

    def open_b1_and_hold_for_revalidation(self):
        gate_run = self.run_tool(
            "check_queue.py", "--require-ready", "B1", "--receipts",
            ".cambium/receipts/gates.jsonl")
        self.assertEqual(0, gate_run.returncode, gate_run.stdout)
        gate = json.loads((self.root / ".cambium/receipts/gates.jsonl")
                          .read_text(encoding="utf-8").splitlines()[-1])
        queue = self.load(check_queue.QUEUE_PATH)
        opened = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "open",
            "--gate-receipt", gate["receipt_id"],
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", "2026-08-05T00:01:00Z",
            "--apply")
        self.assertEqual(0, opened.returncode, opened.stdout)
        queue = self.load(check_queue.QUEUE_PATH)
        held = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state",
            "revalidation-required", "--reason",
            "Standards predicate changed",
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--at", "2026-08-05T00:02:00Z",
            "--apply")
        self.assertEqual(0, held.returncode, held.stdout)
        return gate["receipt_id"]

    def plan(self, *, invalidated_receipt=None, overrides=None):
        queue = self.load(check_queue.QUEUE_PATH)
        progress = self.load(check_queue.PROGRESS_PATH)
        contract = progress["contract"]
        semantic = invalidated_receipt is not None
        plan = {
            "schema_version": 1,
            "adoption_id": "SA-001",
            "task_id": queue["task_id"],
            "task_state_before": progress["task_state"],
            "contract_version_before": contract["contract_version"],
            "contract_version_after": "c2" if semantic else
                contract["contract_version"],
            "standards_version_before": queue["standards_version"],
            "standards_version_after": "3.1.0",
            "selected_profile_manifest_before":
                queue["selected_profile_manifest"],
            "selected_profile_manifest_after":
                queue["selected_profile_manifest"],
            "governance_revision_ref": self.GOVERNANCE,
            "governance_revision_sha256": kblib.sha256_file(
                self.root / self.GOVERNANCE),
            "standards_snapshot_sha256_after":
                kblib.repository_tree_sha256(self.root, "kernel"),
            "profile_snapshot_sha256_after":
                kblib.repository_tree_sha256(
                    self.root, "profiles/test-profile"),
            "selected_route_ids_after": copy.deepcopy(
                contract["selected_route_ids"]),
            "selected_card_paths_after": copy.deepcopy(
                contract["selected_card_paths"]),
            "selected_profile_route_ids_after": copy.deepcopy(
                contract["selected_profile_route_ids"]),
            "selected_read_sets_after": copy.deepcopy(
                contract["selected_read_sets"]),
            "loaded_module_paths_after": copy.deepcopy(
                contract["loaded_module_paths"]),
            "queue_revision_before": queue["queue_revision"],
            "queue_revision_after": queue["queue_revision"] + 1,
            "queue_state_revision_before": queue["state_revision"],
            "coverage_sha256_before": kblib.sha256_file(
                self.root / check_queue.COVERAGE_PATH),
            "required_queue_sha256_before": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
            "progress_sha256_before": kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            "changed_predicates": [],
            "invalidated_evidence": [],
            "invalidation_boundaries": [],
            "immediate_gate_reruns": ["required-queue-consistency"],
            "boundary_gate_reruns": [],
        }
        if semantic:
            plan.update({
                "changed_predicates": [{
                    "predicate_id": "PRED-READY-001",
                    "owner_path": self.GOVERNANCE,
                    "change_kind": "modified",
                    "affected_gate_ids": ["required-queue-consistency"],
                }],
                "invalidated_evidence": [{
                    "receipt_id": invalidated_receipt,
                    "predicate_ids": ["PRED-READY-001"],
                    "dimension_ids": ["coverage_and_integration"],
                    "boundary_ids": ["INV-B1-READY"],
                    "reason_code": "predicate-changed",
                    "revalidation_scope_ids": ["B1"],
                }],
                "invalidation_boundaries": [{
                    "boundary_id": "INV-B1-READY",
                    "predicate_ids": ["PRED-READY-001"],
                    "target_kind": "batch",
                    "target_ids": ["B1"],
                    "required_gate_ids": ["required-queue-consistency"],
                }],
                "boundary_gate_reruns": ["required-queue-consistency"],
            })
        if overrides:
            plan.update(copy.deepcopy(overrides))
        path = self.root / self.PLAN
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        return plan

    def command(self, *, apply=False, actor="worker"):
        args = [str(self.root), "--plan", self.PLAN]
        if apply:
            args.extend(["--apply", "--actor-role", actor])
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = adopt_standards.main(args)
        return code, stdout.getvalue()

    def test_noop_dry_run_and_missing_register_apply(self):
        self.pause()
        self.plan()
        state_paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in state_paths]
        code, output = self.command()
        self.assertEqual(0, code, output)
        self.assertEqual(before, [path.read_bytes() for path in state_paths])
        self.assertFalse((self.root / self.RECEIPTS).exists())

        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("paused", result["progress"]["task_state"])
        self.assertEqual(2, result["queue"]["queue_revision"])
        self.assertEqual(0, result["queue"]["state_revision"])
        record = result["progress"]["standards_adoptions"][0]
        self.assertNotIn("after_progress_sha256", record)
        lines = [json.loads(line) for line in (self.root / self.RECEIPTS)
                 .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(3, len(lines))
        self.assertEqual("prepare", lines[0]["transaction_phase"])
        self.assertEqual("required_queue", lines[1]["check"])
        self.assertEqual("commit", lines[2]["transaction_phase"])
        adoption_rows = [row for row in lines
                         if row.get("tool") == adopt_standards.TOOL]
        self.assertEqual(
            {adopt_standards.TOOL_VERSION},
            {row.get("tool_version") for row in adoption_rows})
        self.assertEqual(
            {adopt_standards.GATE_ID},
            {row.get("gate_id") for row in adoption_rows})

    def test_apply_appends_to_existing_receipt_register(self):
        self.pause()
        existing = kblib.make_receipt(
            "fixture", "1", "fixture", "before", "pass", "existing", 1)
        receipt_path = self.root / self.RECEIPTS
        kblib.write_receipts(receipt_path, [existing])
        self.plan()
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        rows = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(existing["receipt_id"], rows[0]["receipt_id"])
        self.assertEqual(4, len(rows))

    def test_state_write_failure_restores_before_bytes_and_records_abort(self):
        self.pause()
        self.plan()
        paths = [self.root / path for path in (
            check_queue.COVERAGE_PATH, check_queue.QUEUE_PATH,
            check_queue.PROGRESS_PATH)]
        before = [path.read_bytes() for path in paths]
        original = kblib.atomic_write_text
        state_writes = {"count": 0}

        def fail_second_state_write(path, text, validator=None):
            if ".cambium/state" in str(path):
                state_writes["count"] += 1
                if state_writes["count"] == 2:
                    raise OSError("injected state write failure")
            return original(path, text, validator=validator)

        with mock.patch.object(
                adopt_standards.kblib, "atomic_write_text",
                side_effect=fail_second_state_write):
            code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(1, code, output)
        self.assertEqual(before, [path.read_bytes() for path in paths])
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())
        rows = [json.loads(line) for line in (self.root / self.RECEIPTS)
                .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["prepare", "abort"],
                         [row["transaction_phase"] for row in rows])
        self.assertEqual(
            {adopt_standards.GATE_ID},
            {row.get("gate_id") for row in rows})
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_closed_schema_stale_hash_and_contract_bump_fail_closed(self):
        self.pause()
        base = self.plan()
        cases = (
            (dict(base, task_state_before="completion-candidate"),
             "active or paused"),
            (dict(base, objective="mutate forbidden state"),
             "unsupported field"),
            (dict(base, coverage_sha256_before="sha256:" + "0" * 64),
             "SHA does not match current bytes"),
            (dict(base, selected_route_ids_after=["R01"]),
             "requires a new contract_version"),
        )
        for candidate, expected in cases:
            with self.subTest(expected=expected):
                (self.root / self.PLAN).write_text(
                    kblib.canonical_yaml(candidate), encoding="utf-8")
                code, output = self.command()
                self.assertEqual(1, code, output)
                self.assertIn(expected, output)

    def test_governance_or_snapshot_drift_rejects_plan(self):
        self.pause()
        self.plan()
        governance = self.root / self.GOVERNANCE
        governance.write_text(
            governance.read_text(encoding="utf-8") + "\nchanged after plan\n",
            encoding="utf-8")
        code, output = self.command()
        self.assertEqual(1, code, output)
        self.assertTrue(
            "governance_revision_sha256" in output or
            "standards_snapshot_sha256_after" in output, output)

    def test_semantic_adoption_preserves_history_but_filters_current_use(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.plan(invalidated_receipt=invalidated_gate)
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertIn(invalidated_gate, result["receipt_catalog"])
        self.assertNotIn(invalidated_gate, result["current_receipt_catalog"])
        item = result["items_by_id"]["B1"]
        self.assertEqual("open", item["state"])
        self.assertEqual("revalidation-required", item["hold_state"])
        self.assertEqual(invalidated_gate, item["activation_receipt"])
        self.assertEqual("run-standards-revalidation:B1",
                         check_queue._resume_next_action(result, []))
        for consumer in (
                "activation gate", "merge-ready batch gate",
                "delta application", "revalidation hold clear"):
            with self.subTest(consumer=consumer):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    update_queue._receipt(result, invalidated_gate, consumer)
        close_errors = check_queue.close_gate_receipt_errors(
            result["current_receipt_catalog"], invalidated_gate,
            item_id="B1", task_id=result["queue"]["task_id"],
            queue_revision=result["queue"]["queue_revision"],
            queue_state_revision=result["queue"]["state_revision"],
            required_queue_sha256=result["queue_sha256"],
            coverage_ledger_sha256=result["coverage_sha256"],
            progress_ledger_sha256=result["progress_sha256"],
            delta_sha256=None, queue_consistency_receipt=None,
            delta_apply_receipt=None)
        self.assertTrue(any(
            "does not exist" in error or "references missing receipt" in error
                            for error in close_errors), close_errors)

        cleared = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state", "none",
            "--gate-receipt", invalidated_gate,
            "--expected-state-revision", str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at", "2026-08-05T00:03:00Z",
            "--apply")
        self.assertEqual(1, cleared.returncode, cleared.stdout)
        self.assertIn("--standards-revalidation-receipt", cleared.stdout)

        boundary_run = self.run_tool(
            "check_queue.py", "--receipts",
            ".cambium/receipts/post-adoption-consistency.jsonl")
        self.assertEqual(0, boundary_run.returncode, boundary_run.stdout)
        boundary = json.loads((
            self.root / ".cambium/receipts/post-adoption-consistency.jsonl"
        ).read_text(encoding="utf-8").splitlines()[-1])
        aggregate_run = self.run_tool(
            "check_queue.py", "--require-revalidation", "B1",
            "--boundary-gate-receipt",
            "required-queue-consistency=%s" % boundary["receipt_id"],
            "--receipts", ".cambium/receipts/revalidation.jsonl")
        self.assertEqual(0, aggregate_run.returncode, aggregate_run.stdout)
        aggregate = json.loads((
            self.root / ".cambium/receipts/revalidation.jsonl"
        ).read_text(encoding="utf-8").splitlines()[-1])
        transition_at = (datetime.fromisoformat(
            aggregate["checked_at"].replace("Z", "+00:00")) +
            timedelta(seconds=1)).astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z")
        refreshed = check_queue.validate_runtime(self.root)
        clear_current = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state", "none",
            "--standards-revalidation-receipt", aggregate["receipt_id"],
            "--expected-state-revision",
            str(refreshed["queue"]["state_revision"]),
            "--expected-sha256", refreshed["queue_sha256"],
            "--actor-role", "integrator", "--at", transition_at, "--apply")
        self.assertEqual(0, clear_current.returncode, clear_current.stdout)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("none", final["items_by_id"]["B1"]["hold_state"])
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            final, "B1"))
        poisoned = copy.deepcopy(final)
        poisoned_item = poisoned["items_by_id"]["B1"]
        poisoned_item["state"] = "merge-ready"
        poisoned_item["batch_receipts"] = [invalidated_gate]
        self.assertIn("current attempt references invalidated receipt",
                      check_queue.current_attempt_evidence_barrier(
                          poisoned, "B1"))

    def test_affected_open_and_merge_ready_batches_fail_without_safe_state(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        runtime = check_queue.validate_runtime(self.root)
        queue = copy.deepcopy(runtime["queue"])
        item = next(row for row in queue["required_queue"]
                    if row["id"] == "B1")
        item["hold_state"] = "none"
        errors = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=queue, progress=runtime["progress"], validate_current=True)
        self.assertTrue(any("must already have hold_state" in error
                            for error in errors), errors)
        item["state"] = "merge-ready"
        errors = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=queue, progress=runtime["progress"], validate_current=True)
        self.assertTrue(any("roll it back" in error for error in errors), errors)

    def test_invalidated_consumer_must_be_bound_by_its_own_scope(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidation_boundaries"][0].update({
            "target_kind": "receipt",
            "target_ids": [invalidated_gate],
        })
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []
        runtime = check_queue.validate_runtime(self.root)
        errors = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=True)
        self.assertTrue(any(
            "omitted from its own boundaries/revalidation scope: B1" in error
            for error in errors), errors)

    def test_current_catalog_and_gate_identity_never_fall_back(self):
        historical = {
            "OLD": (".cambium/receipts/old.jsonl", {
                "receipt_id": "OLD", "tool": check_queue.TOOL,
            })
        }
        self.assertEqual({}, check_queue.current_receipt_catalog({
            "receipt_catalog": historical,
        }))
        registry = {
            "required-queue-consistency": {
                "tool": check_queue.TOOL,
                "tool_version": check_queue.TOOL_VERSION,
                "check": "required_queue",
                "mode": "consistency",
            },
        }
        receipt = {
            "tool": check_queue.TOOL,
            "tool_version": check_queue.TOOL_VERSION,
            "check": "required_queue",
            "queue_check_mode": "consistency",
        }
        self.assertFalse(check_queue.receipt_matches_gate_id(
            receipt, "required-queue-consistency", registry))
        receipt["gate_id"] = "required-queue-consistency"
        self.assertTrue(check_queue.receipt_matches_gate_id(
            receipt, "required-queue-consistency", registry))

    def test_paused_task_must_resume_before_state_bound_revalidation(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.pause()
        self.plan(invalidated_receipt=invalidated_gate)
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual("resume-paused-task",
                         check_queue._resume_next_action(runtime, []))
        attempted = self.run_tool(
            "check_queue.py", "--require-revalidation", "B1")
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("requires task_state=active", attempted.stdout)

if __name__ == "__main__":
    unittest.main()
