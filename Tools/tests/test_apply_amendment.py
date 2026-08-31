"""Layered ownership tests for the current Amendment apply lifecycle.

The fast layers consume parsed plans, Progress rows, and transaction objects.
Repository-backed tests start at one process-local, contract-validated
registration checkpoint and exercise only the adjacent apply writer seam.
Only the public JSON transport test starts a subprocess; only durable Receipt
interruption remains in the slow recovery layer.
"""

from contextlib import redirect_stdout
import copy
import io
import json
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
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.task_runtime.amendment_plan as amendment_plan
import Tools.execution.task_runtime.apply_amendment as apply_amendment
import Tools.execution.task_runtime.check_queue as check_queue
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.register_amendment as register_amendment
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_fixture import install_loadable_profile


def _current_plan(operation="scope-replan"):
    """Return one complete current-schema plan without repository I/O."""
    amendment_id = {
        "scope-replan": "A-SCOPE-CONTRACT",
        "cancel-batch": "A-CANCEL-CONTRACT",
        "gap-routing-reconciliation": "A-GAP-CONTRACT",
    }[operation]
    cancel_batch_id = "B2" if operation == "cancel-batch" else None
    affected_pages = (
        ["Topics/B.md"] if operation == "cancel-batch"
        else ["Topics/A.md"] if operation == "gap-routing-reconciliation"
        else ["Topics/C.md"]
    )
    affected_batches = (
        ["B2"] if operation == "cancel-batch"
        else ["B1", "B2"] if operation == "gap-routing-reconciliation"
        else ["B3"]
    )
    return {
        "schema_version": 1,
        "amendment_id": amendment_id,
        "operation": operation,
        "affected_pages": affected_pages,
        "affected_batches": affected_batches,
        "scope_version_before": "s1",
        "scope_version_after": (
            "s1" if operation == "gap-routing-reconciliation" else "s2"),
        "queue_revision_before": 1,
        "queue_revision_after": 2,
        "state_revision_before": 0,
        "state_revision_after": 1 if operation == "cancel-batch" else 0,
        "coverage_proposal_path":
            ".cambium/deltas/amendments/%s.coverage.yaml" % amendment_id,
        "coverage_proposal_sha256": "sha256:" + "1" * 64,
        "cancel_batch_id": cancel_batch_id,
    }


def _registered_progress(plan):
    """Return the exact approved row consumed by the apply writer."""
    row = {
        "id": plan["amendment_id"],
        "status": "approved",
        "writeback_done": False,
        "approval_reference": "user:contract-approval",
        "registration_receipt": "R-REGISTER",
        "plan_path":
            ".cambium/deltas/amendments/%s.yaml" % plan["amendment_id"],
        "plan_sha256": "sha256:" + "2" * 64,
    }
    row.update({
        amendment_field: copy.deepcopy(plan[plan_field])
        for amendment_field, plan_field
        in amendment_plan.AMENDMENT_BINDINGS.items()
    })
    return {
        "contract": {"scope_version": plan["scope_version_before"]},
        "amendments": [row],
    }


class AmendmentPlanContractTests(unittest.TestCase):

    def test_current_operations_share_one_closed_plan_schema(self):
        for operation in amendment_plan.OPERATIONS:
            with self.subTest(operation=operation):
                amendment_plan.validate_plan(_current_plan(operation))

        plan = _current_plan()
        cases = (
            ("wrong-schema", {"schema_version": 2},
             "schema_version must be 1"),
            ("unknown-field", {"unexpected_field": "unsupported"},
             "unsupported field.*unexpected_field"),
            ("unknown-operation", {"operation": "unknown-operation"},
             "operation must be one of"),
        )
        for label, changes, expected in cases:
            with self.subTest(case=label):
                candidate = copy.deepcopy(plan)
                candidate.update(changes)
                with self.assertRaisesRegex(ValueError, expected):
                    amendment_plan.validate_plan(candidate)


class AmendmentRegistrationBindingContractTests(unittest.TestCase):

    def test_registered_amendment_is_one_exact_current_plan_binding(self):
        plan = _current_plan()
        progress = _registered_progress(plan)
        row = progress["amendments"][0]
        selected = apply_amendment._find_amendment(
            progress, plan,
            plan_path=row["plan_path"],
            plan_sha=row["plan_sha256"])
        self.assertIs(selected, row)

        cases = {}
        wrong_path = copy.deepcopy(progress)
        wrong_path["amendments"][0]["plan_path"] =             ".cambium/deltas/amendments/other.yaml"
        cases["plan-link"] = wrong_path
        wrong_binding = copy.deepcopy(progress)
        wrong_binding["amendments"][0]["scope_version_after"] = "s9"
        cases["plan-binding"] = wrong_binding
        second_pending = copy.deepcopy(progress)
        second_pending["amendments"].append({
            "id": "A-SECOND",
            "operation": "scope-replan",
            "status": "approved",
            "writeback_done": False,
        })
        cases["one-pending"] = second_pending

        for label, candidate in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                apply_amendment._find_amendment(
                    candidate, plan,
                    plan_path=row["plan_path"],
                    plan_sha=row["plan_sha256"])


class AmendmentTransactionProjectionUnitTests(unittest.TestCase):

    def test_transaction_chain_head_is_monotonic_and_exact_linked(self):
        self.assertEqual(
            (1, None), apply_amendment._transaction_chain_head({}))
        progress = {"amendments": [{
            "operation": "scope-replan",
            "status": "verified",
            "writeback_done": True,
            "transaction_sequence": 4,
            "verification_receipt": "R-COMMIT-4",
        }]}
        self.assertEqual(
            (5, "R-COMMIT-4"),
            apply_amendment._transaction_chain_head(progress))

        progress["amendments"][0]["transaction_sequence"] = 0
        with self.assertRaisesRegex(ValueError, "chain is malformed"):
            apply_amendment._transaction_chain_head(progress)

    def test_progress_projection_verifies_only_the_selected_amendment(self):
        plan = _current_plan()
        progress = _registered_progress(plan)
        original = copy.deepcopy(progress)
        queue = {"queue_revision": 2, "state_revision": 0}
        queue_text = kblib.canonical_yaml(queue)
        result = apply_amendment._sync_progress(
            progress, plan, queue, queue_text,
            "TX-1", "R-COMMIT-1", 1, None,
            progress["amendments"][0]["plan_path"],
            progress["amendments"][0]["plan_sha256"],
            plan["coverage_proposal_path"],
            plan["coverage_proposal_sha256"])

        self.assertEqual(original, progress)
        self.assertEqual("s2", result["contract"]["scope_version"])
        self.assertEqual(2, result["queue_revision"])
        self.assertEqual(0, result["queue_state_revision"])
        self.assertEqual(
            kblib.sha256_bytes(queue_text),
            result["required_queue_sha256"])
        amendment = result["amendments"][0]
        self.assertEqual("verified", amendment["status"])
        self.assertIs(amendment["writeback_done"], True)
        self.assertEqual("TX-1", amendment["transaction_id"])
        self.assertEqual("R-COMMIT-1", amendment["verification_receipt"])
        self.assertEqual(1, amendment["transaction_sequence"])


class AmendmentLockContractTests(unittest.TestCase):

    def test_lock_operation_binds_every_current_ledger_and_staged_byte(self):
        plan = _current_plan()
        before = {
            name: "sha256:" + str(index + 1) * 64
            for index, name in enumerate(
                sorted(runtime_state_contract.RUNTIME_LEDGER_IDS))
        }
        after = {
            name: "sha256:" + str(index + 4) * 64
            for index, name in enumerate(
                sorted(runtime_state_contract.RUNTIME_LEDGER_IDS))
        }
        operation = apply_amendment._lock_operation(
            plan, "TX-1", "sha256:" + "7" * 64,
            before, after, "R-PREPARE", 1, None, "T1",
            plan_path=".cambium/deltas/amendments/A-SCOPE-CONTRACT.yaml",
            receipt_path=apply_amendment.RECEIPT_PATH)

        self.assertEqual(apply_amendment.TOOL, operation["tool"])
        self.assertEqual(plan["operation"], operation["action"])
        self.assertEqual(
            plan["coverage_proposal_path"],
            operation["coverage_proposal_path"])
        self.assertEqual(
            plan["coverage_proposal_sha256"],
            operation["coverage_proposal_sha256"])
        for name in runtime_state_contract.RUNTIME_LEDGER_IDS:
            self.assertEqual(
                before[name], operation["before_%s_sha256" % name])
            self.assertEqual(
                after[name],
                operation["planned_after_%s_sha256" % name])


class AmendmentCancellationReceiptContractTests(unittest.TestCase):

    def test_cancellation_transition_has_one_current_receipt_identity(self):
        plan = _current_plan("cancel-batch")
        digest = "sha256:" + "1" * 64
        receipt = apply_amendment._new_queue_cancellation_receipt(
            plan, "T1", "2026-08-31T00:00:00Z")
        receipt.update({
            "before_state": "queued",
            "after_state": "cancelled",
            "before_hold_state": "none",
            "after_hold_state": "none",
            "before_state_revision": 0,
            "after_state_revision": 1,
            "before_required_queue_sha256": digest,
            "after_required_queue_sha256": digest,
            "queue_revision": 2,
        })
        self.assertEqual(
            [],
            apply_amendment.current_queue_cancellation_receipt_errors(
                receipt))

        wrong_kind = copy.deepcopy(receipt)
        wrong_kind["receipt_type_id"] = "another-receipt-kind-v1"
        self.assertTrue(
            apply_amendment.current_queue_cancellation_receipt_errors(
                wrong_kind))
        wrong_edge = copy.deepcopy(receipt)
        wrong_edge["after_state"] = "closed"
        self.assertIn(
            "cancellation transition after_state must be cancelled",
            apply_amendment.current_queue_cancellation_receipt_errors(
                wrong_edge))


class AmendmentFixture:
    """Minimal current lifecycle fixture for repository-backed connections."""

    def initialize_repository(self):
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        self.amendment_dir = self.root / ".cambium/deltas/amendments"
        self.amendment_dir.mkdir(parents=True)

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
                self.root / queue_runtime.COVERAGE_PATH),
            "progress": kblib.sha256_file(
                self.root / queue_runtime.PROGRESS_PATH),
            "queue": kblib.sha256_file(
                self.root / queue_runtime.QUEUE_PATH),
        }

    def make_plan(self, operation, proposal, affected_pages,
                  affected_batches, cancel_batch_id=None):
        amendment_id = {
            "cancel-batch": "A-CANCEL-001",
            "gap-routing-reconciliation": "A-GAP-001",
        }.get(operation, "A-SCOPE-001")
        proposal_rel = (
            ".cambium/deltas/amendments/%s.coverage.yaml" %
            amendment_id)
        proposal_path = self.write_yaml(proposal_rel, proposal)
        queue = self.load(queue_runtime.QUEUE_PATH)
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
            "state_revision_after": (
                queue["state_revision"] + 1
                if operation == "cancel-batch"
                else queue["state_revision"]),
            "coverage_proposal_path": proposal_rel,
            "coverage_proposal_sha256":
                kblib.sha256_file(proposal_path),
            "cancel_batch_id": cancel_batch_id,
        }
        plan_rel = (
            ".cambium/deltas/amendments/%s.yaml" % amendment_id)
        self.write_yaml(plan_rel, plan)
        return plan_rel, plan

    def scope_proposal(self):
        coverage = self.load(queue_runtime.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-04T12:00:00Z"
        coverage["batch_specs"].append({
            "id": "B3",
            "family": "Core",
            "order_hint": 3,
            "source_route": "R03",
            "execution_mode": "concurrent-worker",
            "depends_on": ["B2"],
            "confirmation_required": False,
            "work_spec_path": None,
            "work_spec_sha256": None,
        })
        coverage["pages"].append({
            "path": "Topics/C.md",
            "coverage_disposition": "required",
            "canonical_owner": "Topics/C.md",
            "type": "concept",
            "priority": "P1",
            "tier": "M",
            "prerequisites": ["Topics/B.md"],
            "batch": "B3",
            "next_batch": "B3",
            "deferred_reason": None,
            "reentry_condition": None,
        })
        return coverage

    def cancel_proposal(self):
        coverage = self.load(queue_runtime.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-04T12:00:00Z"
        coverage["batch_specs"] = [
            spec for spec in coverage["batch_specs"]
            if spec["id"] != "B2"
        ]
        page = next(
            entry for entry in coverage["pages"]
            if entry["path"] == "Topics/B.md")
        page["coverage_disposition"] = "deferred"
        page["next_batch"] = None
        page["deferred_reason"] =             "removed by approved scope Amendment"
        page["reentry_condition"] =             "a successor Amendment restores scope"
        return coverage

    def register_plan(self, plan_rel, plan):
        expected = self.shas()
        output = io.StringIO()
        with redirect_stdout(output):
            code = register_amendment.main([
                str(self.root),
                "--operation", plan["operation"],
                "--plan", plan_rel,
                "--date", time.strftime("%Y-%m-%d", time.gmtime()),
                "--summary", "approved cross-Ledger Amendment",
                "--approval-reference", "user:fixture-approval",
                "--expected-coverage-sha256", expected["coverage"],
                "--expected-progress-sha256", expected["progress"],
                "--expected-queue-sha256", expected["queue"],
                "--actor-role", "integrator",
                "--apply",
            ])
        self.assertEqual(0, code, output.getvalue())
        return output.getvalue()

    def resume_status(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = check_queue.main([
                str(self.root), "--resume-status"])
        return code, output.getvalue()

    def receipt_rows(self):
        return [
            json.loads(line)
            for line in (
                self.root / apply_amendment.RECEIPT_PATH
            ).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


class _CheckpointBuilder(AmendmentFixture, unittest.TestCase):

    def _walk(self):
        raise NotImplementedError("checkpoint builder is not a test")

    @classmethod
    def at(cls, root):
        builder = cls("_walk")
        builder.root = root
        return builder


_CHECKPOINTS = {}


def _checkpoint(name):
    """Build and validate each adjacent Amendment checkpoint once."""
    if name in _CHECKPOINTS:
        _holder, root, artifacts = _CHECKPOINTS[name]
        return root, artifacts
    if name not in ("base", "registered-scope", "registered-cancel"):
        raise KeyError(name)

    holder = tempfile.TemporaryDirectory()
    root = Path(holder.name) / "repo"
    builder = _CheckpointBuilder.at(root)
    if name == "base":
        builder.initialize_repository()
        initial = runtime_validation.validate_runtime(root)
        if initial["errors"]:
            raise AssertionError(
                "Amendment base checkpoint is not current: %s" %
                initial["errors"])
        artifacts = {}
        _CHECKPOINTS[name] = (holder, root, artifacts)
        return root, artifacts

    base_root, _base_artifacts = _checkpoint("base")
    shutil.copytree(base_root, root)
    if name == "registered-scope":
        plan_rel, plan = builder.make_plan(
            "scope-replan", builder.scope_proposal(),
            ["Topics/C.md"], ["B3"])
    else:
        plan_rel, plan = builder.make_plan(
            "cancel-batch", builder.cancel_proposal(),
            ["Topics/B.md"], ["B2"], cancel_batch_id="B2")
    builder.register_plan(plan_rel, plan)
    registered = runtime_validation.validate_runtime(root)
    if registered["errors"]:
        raise AssertionError(
            "Amendment registration checkpoint is not current: %s" %
            registered["errors"])

    artifacts = {"plan_rel": plan_rel, "plan": plan}
    _CHECKPOINTS[name] = (holder, root, artifacts)
    return root, dict(artifacts)


class _CheckpointBackedCase(AmendmentFixture, unittest.TestCase):
    CHECKPOINT = None

    def setUp(self):
        checkpoint_root, self.scenario = _checkpoint(self.CHECKPOINT)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(checkpoint_root, self.root)
        self.amendment_dir = \
            self.root / ".cambium/deltas/amendments"

    def tearDown(self):
        self.tmp.cleanup()


class AmendmentScopeIntegrationTests(_CheckpointBackedCase):
    CHECKPOINT = "registered-scope"

    def test_scope_replan_cli_json_commits_one_current_transaction(self):
        expected = self.shas()
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "apply_amendment.py"),
                str(self.root),
                "--plan", self.scenario["plan_rel"],
                "--expected-coverage-sha256", expected["coverage"],
                "--expected-progress-sha256", expected["progress"],
                "--expected-queue-sha256", expected["queue"],
                "--actor-role", "integrator",
                "--apply",
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        emitted = json.loads(completed.stdout)
        self.assertEqual(
            ["prepare", "commit"],
            [row["transaction_phase"] for row in emitted])

        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("s2", result["queue"]["scope_version"])
        self.assertEqual(["Topics/C.md"],
                         result["items_by_id"]["B3"]["manifest"])
        amendment = result["progress"]["amendments"][-1]
        self.assertEqual("verified", amendment["status"])
        self.assertIs(amendment["writeback_done"], True)
        self.assertEqual(
            ["prepare", "commit"],
            [row["transaction_phase"] for row in self.receipt_rows()
             if row.get("transaction_phase")])


class AmendmentCancellationIntegrationTests(_CheckpointBackedCase):
    CHECKPOINT = "registered-cancel"

    def test_cancel_batch_commits_its_distinct_transition_receipt(self):
        prepared = apply_amendment._prepare_result(
            str(self.root), self.scenario["plan_rel"], self.shas())
        apply_amendment._commit_transaction(
            str(self.root), prepared,
            str(self.root / apply_amendment.RECEIPT_PATH))

        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        cancelled = result["items_by_id"]["B2"]
        self.assertEqual("cancelled", cancelled["state"])
        self.assertEqual(
            self.scenario["plan"]["amendment_id"],
            cancelled["cancellation_amendment"])
        transition_id = cancelled["transition_receipts"][-1]
        transition = result["receipt_catalog"][transition_id][1]
        self.assertEqual(
            [],
            apply_amendment.current_queue_cancellation_receipt_errors(
                transition))
        page = next(
            entry for entry in result["coverage"]["pages"]
            if entry["path"] == "Topics/B.md")
        self.assertEqual("deferred", page["coverage_disposition"])
        self.assertIsNone(page["next_batch"])


class AmendmentCommitIntegrationTests(_CheckpointBackedCase):
    CHECKPOINT = "registered-scope"

    def prepared(self):
        return apply_amendment._prepare_result(
            str(self.root), self.scenario["plan_rel"], self.shas())

    def test_partial_write_rolls_back_and_records_abort(self):
        before = self.shas()
        prepared = self.prepared()
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
            with self.assertRaisesRegex(
                    OSError, "injected second-file"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        self.assertEqual(
            ["prepare", "abort"],
            [row["transaction_phase"] for row in self.receipt_rows()
             if row.get("transaction_phase")])
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())
        self.assertEqual(
            [], runtime_validation.validate_runtime(self.root)["errors"])


class AmendmentRecoverySlowTests(_CheckpointBackedCase):
    CHECKPOINT = "registered-scope"

    def prepared(self):
        return apply_amendment._prepare_result(
            str(self.root), self.scenario["plan_rel"], self.shas())

    def test_durable_commit_interruption_keeps_recovery_evidence(self):
        before = self.shas()
        prepared = self.prepared()
        receipt_path = self.root / apply_amendment.RECEIPT_PATH
        real_append = kblib.write_receipts

        def append_commit_then_fail(path, receipts, **kwargs):
            real_append(path, receipts, **kwargs)
            if any(
                    row.get("transaction_phase") == "commit"
                    for row in receipts):
                raise OSError(
                    "injected error after durable commit receipt")

        with mock.patch.object(
                apply_amendment.kblib, "write_receipts",
                side_effect=append_commit_then_fail):
            with self.assertRaisesRegex(
                    ValueError, "recovery was incomplete"):
                apply_amendment._commit_transaction(
                    str(self.root), prepared, str(receipt_path))

        self.assertEqual(before, self.shas())
        phases = [
            row["transaction_phase"] for row in self.receipt_rows()
            if row.get("transaction_phase")
        ]
        self.assertEqual(["prepare", "commit", "abort"], phases)
        self.assertTrue((
            self.root /
            ".cambium/tmp/state-writer.lock/owner.json"
        ).is_file())

        code, output = self.resume_status()
        self.assertNotEqual(0, code)
        self.assertIn(prepared["commit"]["receipt_id"], output)
        self.assertIn("transaction_phase=abort", output)
        self.assertIn(
            "next_action=reconcile-interrupted-write", output)


if __name__ == "__main__":
    unittest.main()
