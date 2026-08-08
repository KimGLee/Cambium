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
            "| Gate ID | Tool | Tool version | Check | Mode | Dimension "
            "| Lifecycle |\n"
            "|---|---|---|---|---|---|---|\n"
            "| required-queue-consistency | check_queue | 1.7.0 | required_queue | consistency | * | not-batch-scoped |\n"
            "| required-queue-admission | check_queue | 1.7.0 | required_queue | require-ready:* | * | queued |\n"
            "| batch-close | check_batch_close | 1.3.0 | batch_close_gate | * | * | merge-ready |\n",
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

    # --- Boundary gates against the target batch's lifecycle position ------
    #
    # `required-queue-admission` is producible only while a batch is `queued`
    # and `batch-close` only while it is `merge-ready`, so an `open` batch
    # named by a boundary carrying either can produce neither.  Requiring the
    # whole union at hold-discharge time therefore deadlocked the hold: the
    # only exit from `open` is `merge-ready`, which refuses a held batch, and
    # the hold refuses to clear without an aggregate naming every gate.
    LIFECYCLE_GATES = ["batch-close", "required-queue-admission",
                       "wiki-link-integrity"]
    LINK_RECEIPTS = ".cambium/receipts/links.jsonl"

    def register_link_gate(self):
        """Add the one boundary gate an `open` batch can still produce."""
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            registry.read_text(encoding="utf-8") +
            "| wiki-link-integrity | check_links | 1.5.0 "
            "| link-check-summary | * | * | not-batch-scoped |\n",
            encoding="utf-8")

    def lifecycle_boundary_plan(self, invalidated_gate):
        """Adopt a boundary naming one producible gate and two that are not."""
        self.register_link_gate()
        self.plan(invalidated_receipt=invalidated_gate, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-LIFECYCLE-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": list(self.LIFECYCLE_GATES),
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_gate,
                "predicate_ids": ["PRED-LIFECYCLE-001"],
                "dimension_ids": ["coverage_and_integration"],
                "boundary_ids": ["INV-B1-LIFECYCLE"],
                "reason_code": "predicate-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-LIFECYCLE",
                "predicate_ids": ["PRED-LIFECYCLE-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": list(self.LIFECYCLE_GATES),
            }],
            "boundary_gate_reruns": list(self.LIFECYCLE_GATES),
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

    def link_gate_receipt(self):
        """Produce the `wiki-link-integrity` receipt the boundary is owed."""
        receipts = self.root / self.LINK_RECEIPTS
        completed = self.run_tool(
            "check_links.py", "--receipts", str(receipts))
        self.assertEqual(0, completed.returncode, completed.stdout)
        return json.loads(receipts.read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]

    def revalidation_aggregate(self, link_receipt):
        """Run the aggregate with only the producible gate supplied."""
        relative = ".cambium/receipts/revalidation.jsonl"
        completed = self.run_tool(
            "check_queue.py", "--require-revalidation", "B1",
            "--boundary-gate-receipt", "wiki-link-integrity=%s" % link_receipt,
            "--receipts", relative)
        self.assertEqual(0, completed.returncode, completed.stdout)
        return json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])

    @staticmethod
    def seconds_after(stamp, seconds):
        """Return ``stamp`` advanced by ``seconds``, in receipt format.

        Transition timestamps may not move backward, so every step after the
        aggregate is derived from the aggregate's own clock rather than fixed.
        """
        return (datetime.fromisoformat(stamp.replace("Z", "+00:00")) +
                timedelta(seconds=seconds)).astimezone(
                    timezone.utc).isoformat().replace("+00:00", "Z")

    def clear_b1_hold(self, aggregate):
        """Discharge the `revalidation-required` hold with that aggregate."""
        transition_at = self.seconds_after(aggregate["checked_at"], 1)
        result = check_queue.validate_runtime(self.root)
        completed = self.run_tool(
            "update_queue.py", "--id", "B1", "--hold-state", "none",
            "--standards-revalidation-receipt", aggregate["receipt_id"],
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at", transition_at, "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        return transition_at

    def test_neither_unreachable_boundary_gate_has_a_producer_to_run(self):
        """The deadlock's two halves, stated against the tools themselves."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        self.assertEqual(
            "open",
            check_queue.validate_runtime(self.root)["items_by_id"]["B1"]
            ["state"])

        admission = self.run_tool("check_queue.py", "--require-ready", "B1")
        self.assertEqual(1, admission.returncode, admission.stdout)
        self.assertIn("B1 is open, not queued", admission.stdout)

        close = self.run_tool(
            "check_batch_close.py", "--batch", "B1",
            "--integrator", "fixture-integrator",
            "--reviewer", "fixture-reviewer",
            "--review-attestation", "audit-absent-attestation")
        self.assertEqual(1, close.returncode, close.stdout)
        self.assertIn("B1 is open, not merge-ready", close.stdout)

    def test_an_open_batch_clears_on_the_gates_its_position_can_produce(self):
        """The hold clears with the one producible receipt supplied."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        aggregate = self.revalidation_aggregate(self.link_gate_receipt())

        self.assertEqual(self.LIFECYCLE_GATES, aggregate["required_gate_ids"])
        self.assertEqual(["wiki-link-integrity"], aggregate["due_gate_ids"])
        self.assertEqual(["batch-close"],
                         aggregate["deferred_to_later_transition_gate_ids"])
        self.assertEqual(["required-queue-admission"],
                         aggregate["unrepeatable_passed_gate_ids"])
        self.assertEqual("open", aggregate["target_batch_state"])
        self.assertEqual(
            [row["required_gate_id"]
             for row in aggregate["boundary_gate_receipts"]],
            ["wiki-link-integrity"])

        self.clear_b1_hold(aggregate)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("none", final["items_by_id"]["B1"]["hold_state"])
        self.assertEqual([], check_queue.outstanding_standards_revalidation(
            final, "B1"))

    def test_requiring_the_whole_union_regardless_of_position_deadlocks(self):
        """Counterfactual: the pre-change requirement, run in this process.

        Reverting only the partition -- every named gate due, nothing
        deferred or unrepeatable -- must make the same aggregate refuse.  A
        regression that passed either way would prove nothing.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        supplied = {"wiki-link-integrity": self.link_gate_receipt()}
        result = check_queue.validate_runtime(self.root)

        context, errors = check_queue.standards_revalidation_context(
            result, "B1", supplied)
        self.assertEqual([], errors)
        self.assertIsNotNone(context)

        def whole_union(gate_ids, state, registry):
            return sorted({value for value in gate_ids if value}), [], []

        with mock.patch.object(
                check_queue, "partition_boundary_gates_by_lifecycle",
                whole_union):
            _reverted, reverted_errors = \
                check_queue.standards_revalidation_context(
                    result, "B1", supplied)
        demanded = [error for error in reverted_errors
                    if "boundary gate receipt IDs must be exactly" in error]
        self.assertEqual(1, len(demanded), reverted_errors)
        for gate_id in ("batch-close", "required-queue-admission"):
            self.assertIn(gate_id, demanded[0])

    def test_the_partition_never_becomes_a_way_to_require_nothing(self):
        """`due` is still enforced exactly as before the partition."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        link_receipt = self.link_gate_receipt()
        result = check_queue.validate_runtime(self.root)

        _context, absent = check_queue.standards_revalidation_context(
            result, "B1", {})
        self.assertTrue(any(
            "boundary gate receipt IDs must be exactly "
            "['wiki-link-integrity']" in error for error in absent), absent)

        _context, unknown = check_queue.standards_revalidation_context(
            result, "B1", {"wiki-link-integrity": "audit-not-a-receipt"})
        self.assertTrue(any("references missing current receipt" in error
                            for error in unknown), unknown)

        _context, mismatched = check_queue.standards_revalidation_context(
            result, "B1", {"batch-close": link_receipt})
        self.assertTrue(any(
            "boundary gate receipt IDs must be exactly" in error
            for error in mismatched), mismatched)

        # A receipt of the right Gate whose bound identity was stripped is
        # still refused: the partition narrows which gates are owed, never
        # what a receipt for one of them must carry.
        rows = [json.loads(line) for line in
                (self.root / self.LINK_RECEIPTS).read_text(
                    encoding="utf-8").splitlines()]
        for row in rows:
            row.pop("standards_version", None)
        (self.root / self.LINK_RECEIPTS).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n"
                    for row in rows), encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        _context, stripped = check_queue.standards_revalidation_context(
            result, "B1", {"wiki-link-integrity": link_receipt})
        self.assertTrue(any("standards_version" in error
                            for error in stripped), stripped)

    def append_fixture_receipt(self, receipt_id, **fields):
        """Append one hand-written receipt to the fixture register."""
        receipt = {"receipt_id": receipt_id, "result": "pass",
                   "invalidated_by": None}
        receipt.update(fields)
        kblib.write_receipts(
            self.root / ".cambium/receipts/fixture.jsonl", [receipt])
        return receipt_id

    def merge_and_apply_b1(self, at):
        """Carry the cleared batch to `merge-ready` and apply its Delta."""
        queue = self.load(check_queue.QUEUE_PATH)
        self.append_fixture_receipt(
            "audit-page-1", check="fixture", target="Topics/A.md")
        self.append_fixture_receipt(
            "audit-batch-1", check=check_queue.BATCH_REVIEW_CHECK,
            target="B1", tool=check_queue.MANUAL_ATTESTATION_TOOL,
            tool_version=check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
            gate_id=check_queue.BATCH_REVIEW_GATE_ID,
            task_id=queue["task_id"], batch_id="B1",
            delta_page_receipt_ids=["audit-page-1"])
        delta = self.root / ".cambium/deltas/B1.yaml"
        delta.parent.mkdir(parents=True, exist_ok=True)
        delta.write_text(
            "batch: B1\ngenerated_at: %s\n"
            "pages:\n  - path: Topics/A.md\n"
            "    gate_receipts:\n      - audit-page-1\n"
            "open_gaps_added: []\nopen_gaps_closed: []\n"
            "next_batch_updates: []\nwatermark_advance: null\n" % at,
            encoding="utf-8")
        result = check_queue.validate_runtime(self.root)
        merged = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "merge-ready",
            "--delta-path", ".cambium/deltas/B1.yaml",
            "--batch-receipt", "audit-batch-1",
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at", at, "--apply")
        self.assertEqual(0, merged.returncode, merged.stdout)
        relative = ".cambium/receipts/delta-B1.jsonl"
        applied = subprocess.run(
            [sys.executable, str(TOOLS / "apply_delta.py"),
             check_queue.COVERAGE_PATH, ".cambium/deltas/B1.yaml",
             "--root", str(self.root),
             "--expected-coverage-sha256",
             kblib.sha256_file(self.root / check_queue.COVERAGE_PATH),
             "--expected-queue-sha256",
             kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
             "--actor-role", "integrator", "--receipts", relative, "--apply"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        self.assertEqual(0, applied.returncode, applied.stdout)
        return json.loads((self.root / relative).read_text(
            encoding="utf-8").splitlines()[-1])["receipt_id"]

    def test_a_deferred_gate_is_still_required_at_the_transition_it_defers_to(
            self):
        """Deferral moves the claim; it does not waive it.

        `batch-close` was recorded as deferred rather than required, so the
        close transition -- which is where that Gate's producer can run --
        must still refuse without it.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.lifecycle_boundary_plan(invalidated_gate)
        aggregate = self.revalidation_aggregate(self.link_gate_receipt())
        self.assertEqual(["batch-close"],
                         aggregate["deferred_to_later_transition_gate_ids"])
        cleared_at = self.clear_b1_hold(aggregate)
        delta_apply_receipt = self.merge_and_apply_b1(
            self.seconds_after(cleared_at, 1))

        consistency = self.run_tool(
            "check_queue.py", "--receipts", ".cambium/receipts/close.jsonl")
        self.assertEqual(0, consistency.returncode, consistency.stdout)
        consistency_receipt = json.loads(
            (self.root / ".cambium/receipts/close.jsonl").read_text(
                encoding="utf-8").splitlines()[-1])["receipt_id"]
        result = check_queue.validate_runtime(self.root)
        self.assertEqual("merge-ready", result["items_by_id"]["B1"]["state"])
        attempted = self.run_tool(
            "update_queue.py", "--id", "B1", "--transition", "closed",
            "--gate-receipt", consistency_receipt,
            "--delta-apply-receipt", delta_apply_receipt,
            "--expected-state-revision",
            str(result["queue"]["state_revision"]),
            "--expected-sha256", result["queue_sha256"],
            "--actor-role", "integrator", "--at",
            self.seconds_after(cleared_at, 2), "--apply")
        self.assertEqual(1, attempted.returncode, attempted.stdout)
        self.assertIn("requires --close-gate-receipt", attempted.stdout)
        self.assertEqual(
            "merge-ready",
            self.load(check_queue.QUEUE_PATH)["required_queue"][0]["state"])

    def test_a_queue_exhaustion_gate_is_deferred_not_demanded_now(self):
        """A gate whose position is Queue exhaustion, not a batch state.

        `required-queue-completion` takes no batch, so it is not batch-scoped
        in the narrow sense -- but its producer refuses while any non-terminal
        batch remains, which every live batch is.  Treating it as producible
        now would deadlock the hold exactly as `batch-close` did.
        """
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            registry.read_text(encoding="utf-8") +
            "| required-queue-completion | check_queue | 1.7.0 "
            "| required_queue | require-complete | * | queue-exhausted |\n",
            encoding="utf-8")
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        gates = ["required-queue-completion", "wiki-link-integrity"]
        self.register_link_gate()
        self.plan(invalidated_receipt=invalidated_gate, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-EXHAUSTION-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": gates,
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_gate,
                "predicate_ids": ["PRED-EXHAUSTION-001"],
                "dimension_ids": ["coverage_and_integration"],
                "boundary_ids": ["INV-B1-EXHAUSTION"],
                "reason_code": "predicate-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-EXHAUSTION",
                "predicate_ids": ["PRED-EXHAUSTION-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": gates,
            }],
            "boundary_gate_reruns": gates,
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

        # The producer refuses while B1 is non-terminal, so this gate is as
        # unreachable from `open` as `batch-close` is.
        refused = self.run_tool("check_queue.py", "--require-complete")
        self.assertEqual(1, refused.returncode, refused.stdout)
        self.assertIn("remaining_required_work_units=2", refused.stdout)

        aggregate = self.revalidation_aggregate(self.link_gate_receipt())
        self.assertEqual(["wiki-link-integrity"], aggregate["due_gate_ids"])
        self.assertEqual(["required-queue-completion"],
                         aggregate["deferred_to_later_transition_gate_ids"])
        self.assertEqual([], aggregate["unrepeatable_passed_gate_ids"])
        self.clear_b1_hold(aggregate)
        final = check_queue.validate_runtime(self.root)
        self.assertEqual([], final["errors"])
        self.assertEqual("none", final["items_by_id"]["B1"]["hold_state"])

    def passed_only_boundary_plan(self, invalidated_gate, target_ids):
        """A boundary naming only a gate its targets have already left."""
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["changed_predicates"][0]["affected_gate_ids"] = [
            "required-queue-admission"]
        plan["invalidation_boundaries"][0].update({
            "required_gate_ids": ["required-queue-admission"],
            "target_ids": list(target_ids),
        })
        plan["boundary_gate_reruns"] = ["required-queue-admission"]
        return plan

    def test_a_boundary_of_only_passed_gates_is_refused_at_admission(self):
        """Every named gate is behind the batch, so nothing would apply."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.passed_only_boundary_plan(invalidated_gate, ["B1"])
        dead = [error for error in self.plan_errors(plan)
                if "records protection nothing will ever apply" in error]

        self.assertEqual(1, len(dead), dead)
        self.assertIn("INV-B1-READY", dead[0])
        self.assertIn("required-queue-admission", dead[0])
        self.assertIn("open batch B1", dead[0])

    def test_one_reached_batch_that_can_still_claim_it_keeps_the_boundary(
            self):
        """The rule reads each reached batch's position, not a gate blacklist.

        This boundary reaches `queued` B2 as a declared target and `open` B1
        through its invalidated evidence's revalidation scope.  B1 has left
        the gate's position, but B2 has not, so the boundary still protects
        something and stands.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.passed_only_boundary_plan(invalidated_gate, ["B2"])
        self.assertEqual(["B1"],
                         plan["invalidated_evidence"][0][
                             "revalidation_scope_ids"])
        items = check_queue.validate_runtime(self.root)["items_by_id"]
        self.assertEqual("queued", items["B2"]["state"])
        self.assertEqual("open", items["B1"]["state"])
        self.assertEqual([], [error for error in self.plan_errors(plan)
                              if "records protection nothing" in error])

    def evidence_scoped_boundary_plan(self, invalidated_gate, scope_ids):
        """Reach a batch only through invalidated-evidence scope."""
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["changed_predicates"][0]["affected_gate_ids"] = [
            "required-queue-admission"]
        plan["invalidation_boundaries"][0].update({
            "required_gate_ids": ["required-queue-admission"],
            "target_kind": "terminal-audit",
            "target_ids": ["terminal-audit"],
        })
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = list(
            scope_ids)
        plan["boundary_gate_reruns"] = ["required-queue-admission"]
        return plan

    def test_a_boundary_reached_only_by_evidence_scope_is_judged_too(self):
        """Enforcement is per boundary, so the refusal must be too.

        A non-`batch` boundary binds a batch through its invalidated
        evidence's revalidation scope exactly as a batch target does, so a
        dead-gate refusal scoped to declared targets alone would miss it.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.evidence_scoped_boundary_plan(invalidated_gate, ["B1"])
        errors = self.plan_errors(plan)
        self.assertEqual([], [error for error in errors
                              if "no gate rerun" in error])
        dead = [error for error in errors
                if "records protection nothing will ever apply" in error]

        self.assertEqual(1, len(dead), errors)
        self.assertIn("INV-B1-READY", dead[0])
        self.assertIn("required-queue-admission", dead[0])
        self.assertIn("open batch B1", dead[0])

    def test_an_evidence_scoped_boundary_a_batch_can_claim_still_stands(self):
        """Same route, live position: nothing is refused."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.evidence_scoped_boundary_plan(invalidated_gate, ["B2"])
        self.assertEqual([], [error for error in self.plan_errors(plan)
                              if "records protection nothing" in error])

    def test_a_sealed_plan_of_only_passed_gates_still_replays_clean(self):
        """History is replayed under the rules of its own day.

        A completed adoption's plan bytes are fingerprinted inside append-only
        receipts, so an instance whose earlier boundary named only gates its
        batch has left has no sanctioned way to rewrite them.  Judging that
        plan here would strand it.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.passed_only_boundary_plan(invalidated_gate, ["B1"])
        self.assertEqual(1, len([error for error in self.plan_errors(plan)
                                 if "records protection nothing" in error]))
        runtime = check_queue.validate_runtime(self.root)
        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=False)
        self.assertEqual([], [error for error in replay
                              if "records protection nothing" in error])

    def test_deterministic_boundary_gate_receipt_satisfies_revalidation(self):
        """A named `check_links` boundary must be satisfiable, not a deadlock.

        The boundary consumer requires the Gate receipt to carry `task_id`,
        `standards_version`, and `selected_profile_manifest` equal to the
        post-adoption Queue.  A producer that omits them can never clear the
        boundary it was named for.
        """
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            registry.read_text(encoding="utf-8") +
            "| wiki-link-integrity | check_links | 1.5.0 "
            "| link-check-summary | * | * | not-batch-scoped |\n",
            encoding="utf-8")
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.plan(invalidated_receipt=invalidated_gate, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-LINK-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": ["wiki-link-integrity"],
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_gate,
                "predicate_ids": ["PRED-LINK-001"],
                "dimension_ids": ["coverage_and_integration"],
                "boundary_ids": ["INV-B1-LINKS"],
                "reason_code": "predicate-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-LINKS",
                "predicate_ids": ["PRED-LINK-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": ["wiki-link-integrity"],
            }],
            "boundary_gate_reruns": ["wiki-link-integrity"],
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

        receipts = self.root / ".cambium/receipts/links.jsonl"
        completed = self.run_tool(
            "check_links.py", "--receipts", str(receipts))
        self.assertEqual(0, completed.returncode, completed.stdout)
        summary = [
            json.loads(line) for line in
            receipts.read_text(encoding="utf-8").splitlines()
        ][-1]
        self.assertEqual("link-check-summary", summary["check"])

        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        for field in ("task_id", "standards_version",
                      "selected_profile_manifest"):
            self.assertEqual(result["queue"].get(field), summary.get(field),
                             field)
        self.assertEqual("3.1.0", summary["standards_version"])
        context, errors = check_queue.standards_revalidation_context(
            result, "B1", {"wiki-link-integrity": summary["receipt_id"]})
        self.assertEqual([], errors)
        self.assertEqual(
            [{"required_gate_id": "wiki-link-integrity",
              "receipt_id": summary["receipt_id"]}],
            context["boundary_gate_receipts"])

    def dimension_boundary_plan(self, invalidated_gate, dimension):
        """Name `content-correctness` at a boundary raised in one dimension."""
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            registry.read_text(encoding="utf-8") +
            "| content-correctness | manual-attestation | 1.0.0 "
            "| content-correctness | * "
            "| content_and_depth, formula_and_numeric, rendering, "
            "source_and_currentness, structure_and_links "
            "| not-batch-scoped |\n",
            encoding="utf-8")
        self.plan(invalidated_receipt=invalidated_gate, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-CONTENT-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": ["content-correctness"],
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_gate,
                "predicate_ids": ["PRED-CONTENT-001"],
                "dimension_ids": [dimension],
                "boundary_ids": ["INV-B1-CONTENT"],
                "reason_code": "predicate-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-CONTENT",
                "predicate_ids": ["PRED-CONTENT-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": ["content-correctness"],
            }],
            "boundary_gate_reruns": ["content-correctness"],
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)

    def attestation(self, receipt_id, dimension):
        """Record one hand-written `content-correctness` attestation."""
        queue = self.load(check_queue.QUEUE_PATH)
        kblib.write_receipts(
            self.root / ".cambium/receipts/attestations.jsonl", [{
                "receipt_id": receipt_id,
                "gate_id": "content-correctness",
                "tool": check_queue.MANUAL_ATTESTATION_TOOL,
                "tool_version":
                    check_queue.MANUAL_ATTESTATION_TOOL_VERSION,
                "check": "content-correctness",
                "dimension": dimension,
                "target": "B1", "result": "pass", "invalidated_by": None,
                "details": "re-reviewed after adoption",
                "checked_at": "2026-08-09T00:00:00Z",
                "task_id": queue["task_id"],
                "standards_version": queue["standards_version"],
                "selected_profile_manifest":
                    queue["selected_profile_manifest"],
            }])
        return receipt_id

    def test_a_boundary_is_owed_the_dimension_it_was_raised_in(self):
        """F01-F03: one Gate ID, several dimensions, one obligation.

        `content-correctness` covers five receipt dimensions, so its producer
        tuple is the same for all five.  An attestation filed under one of
        them used to satisfy a boundary raised over another.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.dimension_boundary_plan(invalidated_gate, "formula_and_numeric")
        result = check_queue.validate_runtime(self.root)
        self.assertEqual([], result["errors"])

        wrong = self.attestation("attest-structure", "structure_and_links")
        result = check_queue.validate_runtime(self.root)
        _, errors = check_queue.standards_revalidation_context(
            result, "B1", {"content-correctness": wrong})
        self.assertTrue(
            any("does not match registered Gate ID content-correctness"
                in error for error in errors), errors)

        right = self.attestation("attest-formula", "formula_and_numeric")
        result = check_queue.validate_runtime(self.root)
        context, errors = check_queue.standards_revalidation_context(
            result, "B1", {"content-correctness": right})
        self.assertEqual([], errors)
        self.assertEqual(
            [{"required_gate_id": "content-correctness",
              "receipt_id": right}],
            context["boundary_gate_receipts"])

    def test_a_boundary_naming_an_unregisterable_dimension_fails_closed(self):
        """The plan and the registry cannot both hold, so neither is guessed."""
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.dimension_boundary_plan(
            invalidated_gate, "coverage_and_integration")
        receipt = self.attestation("attest-coverage",
                                   "coverage_and_integration")
        result = check_queue.validate_runtime(self.root)
        _, errors = check_queue.standards_revalidation_context(
            result, "B1", {"content-correctness": receipt})
        self.assertTrue(
            any("which K00/12 does not register for it" in error
                for error in errors), errors)

    def test_boundary_gate_receipt_without_identity_cannot_clear(self):
        """Dropping the bound identity must fail closed, not silently pass."""
        registry = (self.root /
                    "kernel/K00 Standards Control/12 Control Registry.md")
        registry.write_text(
            registry.read_text(encoding="utf-8") +
            "| wiki-link-integrity | check_links | 1.5.0 "
            "| link-check-summary | * | * | not-batch-scoped |\n",
            encoding="utf-8")
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        self.plan(invalidated_receipt=invalidated_gate, overrides={
            "changed_predicates": [{
                "predicate_id": "PRED-LINK-001",
                "owner_path": self.GOVERNANCE,
                "change_kind": "modified",
                "affected_gate_ids": ["wiki-link-integrity"],
            }],
            "invalidated_evidence": [{
                "receipt_id": invalidated_gate,
                "predicate_ids": ["PRED-LINK-001"],
                "dimension_ids": ["coverage_and_integration"],
                "boundary_ids": ["INV-B1-LINKS"],
                "reason_code": "predicate-changed",
                "revalidation_scope_ids": ["B1"],
            }],
            "invalidation_boundaries": [{
                "boundary_id": "INV-B1-LINKS",
                "predicate_ids": ["PRED-LINK-001"],
                "target_kind": "batch",
                "target_ids": ["B1"],
                "required_gate_ids": ["wiki-link-integrity"],
            }],
            "boundary_gate_reruns": ["wiki-link-integrity"],
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        receipts = self.root / ".cambium/receipts/links.jsonl"
        completed = self.run_tool(
            "check_links.py", "--receipts", str(receipts))
        self.assertEqual(0, completed.returncode, completed.stdout)
        # Reproduce the pre-fix producer byte-for-byte: same Gate ID, same
        # producer tuple, no bound Queue identity.
        rows = [json.loads(line) for line in
                receipts.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            for field in kblib.RECEIPT_IDENTITY_FIELDS:
                row.pop(field, None)
        receipts.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n"
                    for row in rows), encoding="utf-8")
        summary = rows[-1]
        result = check_queue.validate_runtime(self.root)
        _context, errors = check_queue.standards_revalidation_context(
            result, "B1", {"wiki-link-integrity": summary["receipt_id"]})
        self.assertTrue(any("standards_version" in error for error in errors),
                        errors)

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

    def plan_errors(self, plan):
        runtime = check_queue.validate_runtime(self.root)
        return check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=True)

    def test_boundary_without_any_enforcement_path_is_refused(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        for kind, targets in (
                ("terminal-audit", ["terminal-audit"]),
                ("maintenance-completion", ["maintenance-completion"]),
                ("profile-load", ["profiles/test-profile/profile.md"]),
                ("task", ["fixture-task"]),
                ("receipt", [invalidated_gate])):
            with self.subTest(target_kind=kind):
                plan = self.plan(invalidated_receipt=invalidated_gate)
                plan["invalidation_boundaries"][0].update({
                    "target_kind": kind, "target_ids": targets,
                })
                plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []
                self.assertTrue(any(
                    "boundary INV-B1-READY has target_kind %r and no "
                    "invalidated evidence scoping it to a Queue batch" % kind
                    in error for error in self.plan_errors(plan)),
                    self.plan_errors(plan))

    def test_non_batch_boundary_stays_valid_when_evidence_scopes_a_batch(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidation_boundaries"][0].update({
            "target_kind": "terminal-audit",
            "target_ids": ["terminal-audit"],
        })
        self.assertEqual(["B1"],
                         plan["invalidated_evidence"][0]["revalidation_scope_ids"])
        self.assertEqual([], [error for error in self.plan_errors(plan)
                              if "no gate rerun" in error])
        # Enforcement is per boundary, not per target_kind: this
        # `terminal-audit` boundary binds B1 exactly as a batch boundary would.
        requirements = check_queue.standards_revalidation_requirements(
            self.root, {"standards_adoptions": [{
                "plan_path": self.PLAN,
                "plan_sha256": kblib.sha256_file(self.root / self.PLAN),
                "adopted_at": "2026-08-04T00:05:00Z",
            }]})
        self.assertEqual(["INV-B1-READY"],
                         [row["boundary_id"] for row in requirements["B1"]])

    def test_a_historical_plan_is_not_refused_by_this_admission_rule(self):
        """A sealed adoption cannot be repaired, so it is not re-judged.

        The plan bytes of a completed adoption are fingerprinted inside
        append-only receipts (K13/15: the writer never edits historical
        receipt bytes), so an instance whose earlier plan carries an
        unreachable boundary has no sanctioned way to rewrite it.  Applying
        the admission rule to history would strand that instance
        permanently.  A live instance hit exactly this during an upgrade.
        """
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidation_boundaries"][0].update({
            "target_kind": "profile-load",
            "target_ids": ["profiles/example/profile.md"],
        })
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []

        admission = [error for error in self.plan_errors(plan)
                     if "no gate rerun" in error]
        self.assertEqual(1, len(admission), admission)

        runtime = check_queue.validate_runtime(self.root)
        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=False)
        self.assertEqual([], [error for error in replay
                              if "no gate rerun" in error])

    READ_SET = "kernel/Read Sets/R99 Fixture Read Set.md"
    CROSS_READ_SET = "kernel/Read Sets/R98 Cross Referenced Read Set.md"
    PROFILE_READ_SET = "profiles/test-profile/P Supplemental Read Set.md"
    READ_SET_INDEX = "kernel/Read Sets/Fixture Route Index.md"
    LEAF_DIRECT = "kernel/K99 Fixture Family/01 Direct Leaf.md"
    LEAF_NESTED = "kernel/K99 Fixture Family/02 Nested Leaf.md"
    LEAF_PROFILE = "kernel/K99 Fixture Family/03 Profile Leaf.md"
    LEAF_RELATED = "kernel/K99 Fixture Family/04 Related Only Leaf.md"
    ORDINARY_SELECTED = "profiles/test-profile/ordinary.md"
    BOUND_PROFILE_FILE = "profiles/test-profile/profile.md"
    BOUND_TOOL_FILE = "Tools/fixture_tool.py"
    MODULE_OMISSION = "loaded_module_paths_after omits"
    READ_SET_OMISSION = "selected_read_sets_after omits"

    def load_set_baseline_errors(self):
        """Errors a plan of this fixture carries before any load set is set.

        The fixture task is `planned`, so `plan_errors` always reports that;
        comparing against this baseline states exactly what declaring a load
        set adds and nothing else.
        """
        return set(self.plan_errors(
            self.plan(overrides={"contract_version_after": "c2"})))

    def write_boundary_fixture(self):
        """Lay down a cycle-safe kernel/profile Read Set closure."""
        for relative in (self.LEAF_DIRECT, self.LEAF_NESTED,
                         self.LEAF_PROFILE, self.LEAF_RELATED):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("## Purpose\n\nFixture leaf.\n", encoding="utf-8")
        index = self.root / self.READ_SET_INDEX
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            "---\ntype: route-index\n---\n\n## Purpose\n\nNot a Read Set.\n",
            encoding="utf-8")
        tool = self.root / self.BOUND_TOOL_FILE
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text("# Extra bound tool.\n", encoding="utf-8")

        read_set = self.root / self.READ_SET
        read_set.parent.mkdir(parents=True, exist_ok=True)
        read_set.write_text(
            "---\ntype: read-set\nroute_id: R99\n---\n\n"
            "## Purpose\n\n"
            "Applicability only, so [[%s|Related Only Leaf]] here is not a\n"
            "loading boundary target.\n\n"
            "## Start\n\n"
            "- [[%s|Direct Leaf]]\n"
            "- First read [[%s|Cross Referenced]].\n"
            "- Consult [[%s|Route Index]].\n"
            "- Run `python3 Tools/check_queue.py .` before closing.\n\n"
            "## Related\n\n"
            "- [[%s|Related Only Leaf]]\n"
            % (self.LEAF_RELATED[:-3], self.LEAF_DIRECT[:-3],
               self.CROSS_READ_SET[:-3], self.READ_SET_INDEX[:-3],
               self.LEAF_RELATED[:-3]),
            encoding="utf-8")

        cross = self.root / self.CROSS_READ_SET
        cross.write_text(
            "---\ntype: read-set\nroute_id: R98\n---\n\n"
            "## Purpose\n\nKernel supplemental fixture.\n\n"
            "## Start\n\n"
            "- [[%s|Nested Leaf]]\n"
            "- [[%s|Profile Supplemental Read Set]]\n"
            % (self.LEAF_NESTED[:-3], self.PROFILE_READ_SET[:-3]),
            encoding="utf-8")

        profile = self.root / self.PROFILE_READ_SET
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            "---\ntype: profile-read-set\n"
            "route_id: P:test-profile:supplemental\nsupplements: R98\n---\n\n"
            "## Purpose\n\nProfile supplemental fixture.\n\n"
            "## Start\n\n"
            "- [[%s|Profile Leaf]]\n"
            "- [[%s|Cycle Back To Root]]\n"
            % (self.LEAF_PROFILE[:-3], self.READ_SET[:-3]),
            encoding="utf-8")

    def test_boundary_read_sets_form_a_transitive_cycle_safe_closure(self):
        """Referenced kernel and profile Read Sets must also be declared."""
        self.write_boundary_fixture()
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": [self.READ_SET],
            "loaded_module_paths_after": sorted(
                (self.LEAF_DIRECT, self.LEAF_NESTED, self.LEAF_PROFILE,
                 self.READ_SET_INDEX)),
        })
        errors = self.plan_errors(plan)
        omissions = [error for error in errors
                     if self.READ_SET_OMISSION in error]

        self.assertEqual(2, len(omissions), errors)
        self.assertTrue(any(self.CROSS_READ_SET in error
                            for error in omissions), omissions)
        self.assertTrue(any(self.PROFILE_READ_SET in error
                            for error in omissions), omissions)
        self.assertEqual([], [error for error in errors
                              if self.MODULE_OMISSION in error])
        self.assertEqual(baseline | set(omissions), set(errors))

    def test_every_non_read_set_target_in_the_closure_must_be_loaded(self):
        """Nested leaves and a non-Read-Set index cannot disappear."""
        self.write_boundary_fixture()
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": sorted(
                (self.READ_SET, self.CROSS_READ_SET, self.PROFILE_READ_SET)),
            "loaded_module_paths_after": sorted(
                (self.LEAF_DIRECT, self.BOUND_PROFILE_FILE,
                 self.BOUND_TOOL_FILE)),
        })
        errors = self.plan_errors(plan)
        omissions = [error for error in errors
                     if self.MODULE_OMISSION in error]

        self.assertEqual(3, len(omissions), errors)
        for target in (self.LEAF_NESTED, self.LEAF_PROFILE,
                       self.READ_SET_INDEX):
            self.assertTrue(any(target in error for error in omissions),
                            omissions)
        self.assertFalse(any(self.LEAF_RELATED in error for error in errors),
                         errors)
        self.assertEqual(baseline | set(omissions), set(errors))

        runtime = check_queue.validate_runtime(self.root)
        replay = check_queue.standards_adoption_plan_errors(
            self.root, plan, catalog=runtime["receipt_catalog"],
            queue=runtime["queue"], progress=runtime["progress"],
            validate_current=False)
        self.assertEqual([], [error for error in replay if "_after omits" in error])

    def test_a_complete_closure_allows_additional_tool_and_profile_paths(self):
        """Containment allows route-bound files that no boundary names."""
        self.write_boundary_fixture()
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": sorted(
                (self.READ_SET, self.CROSS_READ_SET, self.PROFILE_READ_SET)),
            "loaded_module_paths_after": sorted(
                (self.BOUND_PROFILE_FILE, self.BOUND_TOOL_FILE,
                 self.LEAF_DIRECT, self.LEAF_NESTED, self.LEAF_PROFILE,
                 self.READ_SET_INDEX)),
        })
        self.assertEqual(baseline, set(self.plan_errors(plan)))

    def test_a_selected_read_set_must_prove_its_document_type(self):
        """Ordinary Markdown is refused and its links are not traversed."""
        self.write_boundary_fixture()
        ordinary = self.root / self.ORDINARY_SELECTED
        ordinary.write_text(
            "## Start\n\n- [[%s|Not A Read Set Boundary]]\n" %
            self.LEAF_DIRECT[:-3], encoding="utf-8")
        baseline = self.load_set_baseline_errors()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [self.ORDINARY_SELECTED],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        type_errors = [error for error in errors
                       if "does not prove frontmatter type" in error]

        self.assertEqual(1, len(type_errors), errors)
        self.assertIn(self.ORDINARY_SELECTED, type_errors[0])
        self.assertEqual([], [error for error in errors
                              if self.MODULE_OMISSION in error])
        self.assertEqual(baseline | set(type_errors), set(errors))

    def test_an_unreadable_read_set_is_reported_once_not_per_module(self):
        """A Read Set path that does not resolve is already reported."""
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": ["kernel/Read Sets/R99 Absent.md"],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertEqual(1, len([error for error in errors
                                 if "selected_read_sets_after path" in error]),
                         errors)
        self.assertEqual([], [error for error in errors
                              if "_after omits" in error])

    def test_invalid_utf8_read_set_fails_closed(self):
        """A present but undecodable Read Set cannot shrink the closure."""
        relative = "kernel/Read Sets/R99 Invalid UTF8.md"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"---\ntype: read-set\n---\n\xff")
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [relative],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            relative in error and "unreadable UTF-8" in error
            for error in errors), errors)

    def test_invalid_utf8_boundary_target_fails_closed(self):
        read_set = self.root / self.READ_SET
        read_set.parent.mkdir(parents=True, exist_ok=True)
        target = "kernel/K99 Fixture Family/Invalid UTF8.md"
        read_set.write_text(
            "---\ntype: read-set\nroute_id: R99\n---\n\n"
            "## Start\n\n- [[%s|Broken Target]]\n" % target[:-3],
            encoding="utf-8")
        target_path = self.root / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"\xff")
        errors = self.plan_errors(self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [self.READ_SET],
            "loaded_module_paths_after": [],
        }))
        self.assertTrue(any(
            target in error and "unreadable UTF-8" in error
            for error in errors), errors)

    def test_read_set_type_must_be_a_scalar_string(self):
        """Malformed YAML types are rejected without raising TypeError."""
        text = "---\ntype: [read-set]\n---\n\n## Start\n"
        self.assertIsNone(kblib.read_set_document_type(text))

    def test_malformed_load_lists_fail_without_validator_traceback(self):
        """Shape errors remain evidence even when elements are unhashable."""
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [{"path": self.READ_SET}],
            "loaded_module_paths_after": [{"path": self.LEAF_DIRECT}],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            "selected_read_sets_after must contain only non-empty strings"
            in error for error in errors), errors)
        self.assertTrue(any(
            "loaded_module_paths_after must contain only non-empty strings"
            in error for error in errors), errors)

    def test_profile_read_set_cannot_cross_the_selected_profile(self):
        """A supplemental route belongs only to its selected profile."""
        relative = "profiles/other-profile/P Other Read Set.md"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntype: profile-read-set\n"
            "route_id: P:test-profile:supplemental\n---\n\n"
            "## Start\n\n- [[%s|Leaf]]\n" % self.LEAF_DIRECT[:-3],
            encoding="utf-8")
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [
                "P:test-profile:supplemental"],
            "selected_read_sets_after": [relative],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            relative in error and "outside the selected profile directory"
            in error for error in errors), errors)

    def test_profile_read_set_route_must_be_selected(self):
        self.write_boundary_fixture()
        plan = self.plan(overrides={
            "contract_version_after": "c2",
            "selected_profile_route_ids_after": [],
            "selected_read_sets_after": [self.PROFILE_READ_SET],
            "loaded_module_paths_after": [],
        })
        errors = self.plan_errors(plan)
        self.assertTrue(any(
            self.PROFILE_READ_SET in error and
            "not present in selected_profile_route_ids" in error
            for error in errors), errors)

    def test_boundary_parser_ignores_fences_and_accepts_indented_h2(self):
        text = (
            "## Purpose\n\n[[Ignored/Purpose]]\n\n"
            "  ## Start\n\n[[Included/Leaf]]\n\n"
            "[[Included/WithSuffix.md|Explicit suffix]]\n\n"
            "| Target |\n|---|\n| [[Included/Table\\|Alias]] |\n\n"
            "```markdown\n## Triggered\n[[Ignored/Fenced]]\n```\n\n"
            "   ## Gate\n\n[[Included/Gate]]\n\n"
            "## Related\n\n[[Ignored/Related]]\n")
        self.assertEqual(
            ["Included/Gate.md", "Included/Leaf.md", "Included/Table.md",
             "Included/WithSuffix.md"],
            kblib.read_set_boundary_targets(text))

    def test_batch_boundary_needs_no_invalidated_evidence_scope(self):
        invalidated_gate = self.open_b1_and_hold_for_revalidation()
        plan = self.plan(invalidated_receipt=invalidated_gate)
        plan["invalidated_evidence"][0]["revalidation_scope_ids"] = []
        self.assertEqual([], [error for error in self.plan_errors(plan)
                              if "no gate rerun" in error])

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

    UNDER_DECLARING_READ_SET = "kernel/Read Sets/R97 Live Contract Fixture.md"
    UNDER_DECLARED_LEAF = "kernel/K97 Fixture Family/01 Boundary Leaf.md"

    def under_declare_live_contract(self):
        """Leave the live contract declaring a Read Set but not its leaf.

        This reproduces the state a past adoption can seal in: the contract's
        five load fields are written only by this tool, so an instance whose
        earlier adoption wrote an incomplete declaration cannot repair it
        anywhere else.
        """
        read_set = self.root / self.UNDER_DECLARING_READ_SET
        read_set.parent.mkdir(parents=True, exist_ok=True)
        read_set.write_text(
            "---\ntype: read-set\nroute_id: R97\n---\n\n"
            "## Start\n\n- [[%s|Boundary Leaf]]\n" %
            self.UNDER_DECLARED_LEAF[:-3], encoding="utf-8")
        leaf = self.root / self.UNDER_DECLARED_LEAF
        leaf.parent.mkdir(parents=True, exist_ok=True)
        leaf.write_text("## Purpose\n\nFixture leaf.\n", encoding="utf-8")
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["contract"]["selected_read_sets"] = [
            self.UNDER_DECLARING_READ_SET]
        progress["contract"]["loaded_module_paths"] = []
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress_path.write_text(kblib.canonical_yaml(progress),
                                 encoding="utf-8")
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        rows = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            if row.get("receipt_id") == "audit-fixture-initial-queue":
                row["contract_sha256"] = kblib.sha256_bytes(
                    kblib.canonical_yaml(progress["contract"]))
                row["after_progress_sha256"] = kblib.sha256_file(progress_path)
        receipt_path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n"
                    for row in rows), encoding="utf-8")

    def test_an_under_declared_live_contract_does_not_block_the_sole_writer(
            self):
        """The writer that alone can re-declare the load set may still run.

        `_prepare_result` refuses to start while `validate_runtime` reports an
        error, so making the live contract's closure gap an error would leave
        the instance with an under-declaration it has no legal way to repair.
        The gap is reported instead, and the adoption that repairs it applies.
        """
        self.under_declare_live_contract()
        self.pause()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["errors"])
        self.assertTrue(any(
            self.UNDER_DECLARED_LEAF in gap for gap in
            runtime["task_runtime"]["contract_load_set_gaps"]),
            runtime["task_runtime"]["contract_load_set_gaps"])

        # Admission still judges the declaration the plan writes: the plan
        # that omits the leaf is refused at plan validation, not at the
        # runtime precheck.
        self.plan(overrides={
            "selected_read_sets_after": [self.UNDER_DECLARING_READ_SET],
            "loaded_module_paths_after": [],
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(1, code, output)
        self.assertNotIn("current runtime is inconsistent", output)
        self.assertIn("invalid Standards adoption plan", output)
        self.assertIn("loaded_module_paths_after omits %s" %
                      self.UNDER_DECLARED_LEAF, output)

        # And the complete declaration applies, so the sole writer really is
        # the repair path for the field only it can write.
        self.plan(overrides={
            "contract_version_after": "c2",
            "selected_read_sets_after": [self.UNDER_DECLARING_READ_SET],
            "loaded_module_paths_after": [self.UNDER_DECLARED_LEAF],
        })
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        repaired = check_queue.validate_runtime(self.root)
        self.assertEqual([], repaired["errors"])
        self.assertEqual(
            [], repaired["task_runtime"]["contract_load_set_gaps"])
        self.assertEqual(
            [self.UNDER_DECLARED_LEAF],
            repaired["progress"]["contract"]["loaded_module_paths"])

    def rewrite_adoption_receipts(self, **field_overrides):
        """Restamp the persisted adoption receipts and return the errors.

        Receipts are append-only evidence, so an instance cannot rewrite them
        to satisfy a constant that moved after they were written; the fixture
        edits them only to stand in for bytes a past producer left behind.
        """
        receipt_path = self.root / self.RECEIPTS
        rows = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            for field, by_tool in field_overrides.items():
                if row.get("tool") in by_tool:
                    row[field] = by_tool[row["tool"]]
        receipt_path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n"
                    for row in rows), encoding="utf-8")
        return check_queue.validate_runtime(self.root)["errors"]

    def commit_one_adoption(self):
        self.pause()
        self.plan()
        code, output = self.command(apply=True, actor="integrator")
        self.assertEqual(0, code, output)
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_superseded_producer_versions_do_not_invalidate_adoption_history(
            self):
        """A producer version bump cannot void the transactions it recorded.

        K00/03 requires a producer's `Tool version` cell to move in the
        revision that changes its accept or reject set, so every past receipt
        was stamped with a constant that revision retires.  The commit receipt
        and the immediate Queue gate it consumed are sealed history, and this
        instance passed through the era they claim.
        """
        self.commit_one_adoption()
        errors = self.rewrite_adoption_receipts(tool_version={
            adopt_standards.TOOL: "1.1.0",
            check_queue.TOOL: "1.5.0",
        })
        self.assertEqual([], errors)

    def test_an_adoption_receipt_era_nothing_accounts_for_is_refused(self):
        """The replacement check has teeth without today's constants.

        The chain accounts for the version before and the version after every
        adoption this instance recorded, plus the live identity.  A commit
        receipt claiming anything else describes a transaction that never
        happened here.
        """
        self.commit_one_adoption()
        errors = self.rewrite_adoption_receipts(
            tool_version={adopt_standards.TOOL: "1.1.0"},
            standards_version={adopt_standards.TOOL: "9.9.9"})
        self.assertEqual(1, len(errors), errors)
        self.assertIn("commit receipt", errors[0])
        self.assertIn("claims standards_version='9.9.9'", errors[0])
        self.assertIn("no Standards adoption record or live identity",
                      errors[0])

    def test_the_accounted_era_set_is_the_instance_own_adoption_chain(self):
        """Both ends of every recorded step, plus the live identity."""
        self.commit_one_adoption()
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual(
            {"3.0.0", "3.1.0"},
            check_queue.accounted_standards_versions(
                runtime["progress"], runtime["queue"]))
        self.assertEqual(
            {"3.0.0"},
            check_queue.accounted_standards_versions(
                {"contract": {"standards_version": "3.0.0"},
                 "standards_adoptions": []}))


if __name__ == "__main__":
    unittest.main()
