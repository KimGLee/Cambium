"""Layered ownership tests for the current Amendment registration lifecycle.

Pure registration predicates run in memory.  Current writer, Progress, and
Receipt seams consume one cached runtime checkpoint with a private copy per
method.  Only the JSON transport test executes the public CLI wrapper.
"""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.register_amendment as register_amendment
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_fixture import install_loadable_profile


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests/fixtures/runtime_state/valid"
REGISTER_CLI = TOOLS / "register_amendment.py"
_CHECKPOINTS = {}


def _capture(callable_, *args, **kwargs):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        returncode = callable_(*args, **kwargs)
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )


def amendment_checkpoint(name="current"):
    """Build the module's one current runtime/Profile checkpoint."""
    if name in _CHECKPOINTS:
        return _CHECKPOINTS[name][1]
    if name != "current":
        raise KeyError(name)
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name) / "repo"
    shutil.copytree(FIXTURE, root)
    install_loadable_profile(root)
    (root / ".cambium/deltas/amendments").mkdir(parents=True)
    (root / ".cambium/deltas/replans").mkdir(parents=True)
    _CHECKPOINTS[name] = (temporary, root)
    return root


def _valid_invocation(**overrides):
    values = {
        "root": "/unused",
        "withdraw": None,
        "reason": None,
        "operation": "scope-replan",
        "plan": ".cambium/deltas/amendments/A-SCOPE.yaml",
        "amendment_id": None,
        "coverage_proposal": None,
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "summary": "Approved fixture Amendment",
        "approval_reference": "user:fixture-approval",
        "decision_mode": "auto",
        "expected_coverage_sha256": "sha256:" + "1" * 64,
        "expected_progress_sha256": "sha256:" + "2" * 64,
        "expected_queue_sha256": "sha256:" + "3" * 64,
        "actor_role": "worker",
        "receipts": register_amendment.RECEIPT_PATH,
        "apply": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AmendmentRegistrationContractTests(unittest.TestCase):
    """Current closed predicates, with no runtime or subprocess."""

    def test_receipt_predicate_accepts_only_current_registration_checks(self):
        for check in register_amendment.RECEIPT_CHECKS:
            with self.subTest(check=check):
                receipt = kblib.make_receipt(
                    register_amendment.TOOL,
                    register_amendment.TOOL_VERSION,
                    check,
                    "A-001",
                    "pass",
                    "fixture",
                    1,
                    receipt_type_id=register_amendment.RECEIPT_TYPE_ID,
                )
                self.assertEqual(
                    [], register_amendment.current_receipt_errors(receipt))
        receipt["check"] = "another-registration-check"
        self.assertTrue(register_amendment.current_receipt_errors(receipt))

    def test_invocation_cross_fields_refuse_before_runtime_access(self):
        cases = (
            (_valid_invocation(summary=None), "requires --summary"),
            (_valid_invocation(date="31-08-2026"), "YYYY-MM-DD"),
            (_valid_invocation(
                decision_mode="explicit-user", approval_reference=None),
             "requires a non-empty --approval-reference"),
            (_valid_invocation(
                withdraw="A-001", reason="reason", operation="scope-replan"),
             "--withdraw takes no registration argument"),
            (_valid_invocation(
                withdraw="A-001", reason=" ", operation=None, plan=None,
                date=None, summary=None, approval_reference=None),
             "requires a nonempty --reason"),
            (_valid_invocation(expected_queue_sha256="not-a-sha"),
             "expected queue SHA"),
        )
        for invocation, message in cases:
            with self.subTest(message=message), \
                    mock.patch.object(
                        register_amendment, "_prepare",
                        side_effect=AssertionError("runtime must not load")), \
                    mock.patch.object(
                        register_amendment, "_prepare_withdrawal",
                        side_effect=AssertionError("runtime must not load")):
                result = _capture(register_amendment._run, invocation, None)
                self.assertEqual(1, result.returncode)
                self.assertIn(message, result.stdout)


class AmendmentRuntimeMixin:
    """One process checkpoint; one private current runtime per method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.checkpoint = amendment_checkpoint("current")

    def setUp(self):
        super().setUp()
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name) / "repo"
        shutil.copytree(self.checkpoint, self.root)
        self._invocation_timestamp = time.time()

    def invoke(self, args):
        """Run one logical CLI invocation without paying for a subprocess.

        The public CLI initializes a distinct receipt run token per process.
        In-process Integration calls instead advance the receipt second, so
        multiple logical invocations cannot reuse one process-local identity.
        """
        self._invocation_timestamp += 2
        with mock.patch.object(
                kblib.time, "time", return_value=self._invocation_timestamp):
            return _capture(register_amendment.main, args)

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def write_yaml(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(value), encoding="utf-8")
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

    def registration_args(
            self, operation, *operation_args, apply=False, shas=None,
            actor_role="worker", approval_reference="user:fixture-approval",
            decision_mode="auto", json_output=False):
        shas = shas or self.shas()
        args = [
            str(self.root),
            "--operation", operation,
            "--date", time.strftime("%Y-%m-%d", time.gmtime()),
            "--summary", "Approved fixture Amendment",
            "--expected-coverage-sha256", shas["coverage"],
            "--expected-progress-sha256", shas["progress"],
            "--expected-queue-sha256", shas["queue"],
            "--actor-role", actor_role,
            *operation_args,
        ]
        if approval_reference is not None:
            args.extend(["--approval-reference", approval_reference])
        if decision_mode != "auto":
            args.extend(["--decision-mode", decision_mode])
        if apply:
            args.append("--apply")
        if json_output:
            args.append("--json")
        return args

    def register(self, operation, *operation_args, **kwargs):
        return self.invoke(
            self.registration_args(operation, *operation_args, **kwargs))

    def withdrawal_args(
            self, amendment_id, *, reason="planned final state invalid",
            apply=False, shas=None, actor_role="integrator"):
        shas = shas or self.shas()
        args = [
            str(self.root), "--withdraw", amendment_id,
            "--reason", reason,
            "--expected-coverage-sha256", shas["coverage"],
            "--expected-progress-sha256", shas["progress"],
            "--expected-queue-sha256", shas["queue"],
            "--actor-role", actor_role,
        ]
        if apply:
            args.append("--apply")
        return args

    def withdraw(self, amendment_id, **kwargs):
        return self.invoke(self.withdrawal_args(amendment_id, **kwargs))

    def scope_proposal(self):
        coverage = self.load(queue_runtime.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-05T00:00:00Z"
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

    def scope_plan(self):
        amendment_id = "A-SCOPE"
        operation = "scope-replan"
        proposal = self.scope_proposal()
        proposal_relative = \
            ".cambium/deltas/amendments/%s.coverage.yaml" % amendment_id
        proposal_path = self.write_yaml(proposal_relative, proposal)
        queue = self.load(queue_runtime.QUEUE_PATH)
        plan = {
            "schema_version": 1,
            "amendment_id": amendment_id,
            "operation": operation,
            "affected_pages": ["Topics/C.md"],
            "affected_batches": ["B3"],
            "scope_version_before": queue["scope_version"],
            "scope_version_after": proposal["scope_version"],
            "queue_revision_before": queue["queue_revision"],
            "queue_revision_after": queue["queue_revision"] + 1,
            "state_revision_before": queue["state_revision"],
            "state_revision_after": queue["state_revision"],
            "coverage_proposal_path": proposal_relative,
            "coverage_proposal_sha256": kblib.sha256_file(proposal_path),
            "cancel_batch_id": None,
        }
        plan_relative = ".cambium/deltas/amendments/%s.yaml" % amendment_id
        plan_path = self.write_yaml(plan_relative, plan)
        return plan_relative, plan_path, proposal_relative

    def records(self):
        path = self.root / register_amendment.RECEIPT_PATH
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def prepare_scope_registration(self):
        plan_relative, plan_path, _ = self.scope_plan()
        expected = self.shas()
        args = SimpleNamespace(
            operation="scope-replan",
            plan=plan_relative,
            amendment_id=None,
            coverage_proposal=None,
            date=time.strftime("%Y-%m-%d", time.gmtime()),
            summary="Approved fixture Amendment",
            approval_reference="user:fixture-approval",
            decision_mode="auto",
        )
        prepared = register_amendment._prepare(
            str(self.root), args, expected)
        return plan_path, expected, prepared

    def assert_registration(self, amendment_id, operation, before):
        progress = self.load(queue_runtime.PROGRESS_PATH)
        row = next(entry for entry in progress["amendments"]
                   if entry["id"] == amendment_id)
        receipt = next(record for record in self.records()
                       if record["receipt_id"] == row["registration_receipt"])
        self.assertEqual(operation, row["operation"])
        self.assertEqual("approved", row["status"])
        self.assertIs(row["writeback_done"], False)
        self.assertEqual("amendment_registration", receipt["check"])
        self.assertEqual(row["approval_reference"],
                         receipt["approval_reference"])
        for field in (
                "decision_mode", "authority_id", "authority_sha256",
                "change_classes", "amendment_impact_sha256"):
            self.assertEqual(row[field], receipt[field])
        self.assertEqual(before["coverage"], receipt["before_coverage_sha256"])
        self.assertEqual(before["coverage"], receipt["after_coverage_sha256"])
        self.assertEqual(before["queue"],
                         receipt["before_required_queue_sha256"])
        self.assertEqual(before["queue"],
                         receipt["after_required_queue_sha256"])
        self.assertEqual(self.shas()["progress"],
                         receipt["after_progress_sha256"])
        self.assertEqual([], runtime_validation.validate_runtime(
            self.root)["errors"])
        return row, receipt


class AmendmentRegistrationIntegrationTests(AmendmentRuntimeMixin,
                                            unittest.TestCase):
    """One current writer/transport seam, beginning at a static checkpoint."""

    def test_cli_registration_and_withdrawal_publish_current_receipts(self):
        plan_relative, plan_path, proposal_relative = self.scope_plan()
        before = self.shas()
        args = self.registration_args(
            "scope-replan", "--plan", plan_relative,
            apply=True,
            actor_role="integrator",
            json_output=True,
        )
        registered = subprocess.run(
            [sys.executable, str(REGISTER_CLI), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            0, registered.returncode, registered.stdout + registered.stderr)
        projected = json.loads(registered.stdout)
        self.assertEqual(1, len(projected))
        row, receipt = self.assert_registration(
            "A-SCOPE", "scope-replan", before)
        self.assertEqual(receipt["receipt_id"], projected[0]["receipt_id"])
        self.assertEqual(plan_relative, row["plan_path"])
        self.assertEqual(kblib.sha256_file(plan_path), row["plan_sha256"])
        self.assertEqual(proposal_relative, row["coverage_proposal_path"])
        self.assertEqual("s1", receipt["scope_version_before"])
        self.assertEqual("s2", receipt["scope_version_after"])

        withdrawn = self.withdraw("A-SCOPE", apply=True)
        self.assertEqual(
            0, withdrawn.returncode, withdrawn.stdout + withdrawn.stderr)

        progress = self.load(queue_runtime.PROGRESS_PATH)
        row = next(entry for entry in progress["amendments"]
                   if entry["id"] == "A-SCOPE")
        receipt = next(record for record in self.records()
                       if record["receipt_id"] == row["withdrawal_receipt"])
        self.assertEqual("withdrawn", row["status"])
        self.assertIs(row["writeback_done"], False)
        self.assertEqual("amendment_withdrawal", receipt["check"])
        self.assertEqual(row["registration_receipt"],
                         receipt["registration_receipt"])
        self.assertEqual([], runtime_validation.validate_runtime(
            self.root)["errors"])


class AmendmentRegistrationSlowTests(AmendmentRuntimeMixin,
                                     unittest.TestCase):
    """Writer-specific staged-input currentness and interruption evidence."""

    def test_locked_publication_revalidates_staged_plan_bytes(self):
        plan_path, before, prepared = self.prepare_scope_registration()
        progress_before = (self.root / queue_runtime.PROGRESS_PATH).read_bytes()
        receipt_path = self.root / register_amendment.RECEIPT_PATH
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "staged artifact bytes changed"):
            register_amendment._apply(
                str(self.root), prepared, str(receipt_path))
        self.assertEqual(progress_before,
                         (self.root / queue_runtime.PROGRESS_PATH).read_bytes())
        self.assertEqual(before, self.shas())
        self.assertFalse(receipt_path.exists())
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_receipt_first_interruption_retains_recovery_evidence(self):
        _plan_path, before, prepared = self.prepare_scope_registration()
        progress_before = (self.root / queue_runtime.PROGRESS_PATH).read_bytes()
        receipt_path = self.root / register_amendment.RECEIPT_PATH
        with mock.patch.object(
                kblib, "atomic_write_text",
                side_effect=OSError("simulated Progress publication failure")):
            with self.assertRaisesRegex(
                    OSError, "simulated Progress publication failure"):
                register_amendment._apply(
                    str(self.root), prepared, str(receipt_path))
        self.assertEqual(progress_before,
                         (self.root / queue_runtime.PROGRESS_PATH).read_bytes())
        self.assertEqual(before, self.shas())
        records = self.records()
        self.assertEqual(1, len(records))
        self.assertEqual("amendment_registration", records[0]["check"])
        runtime = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], runtime["pending_cross_ledger_amendments"])
        self.assertEqual(1, len(runtime["_writer_locks"]))
        evidence = runtime["_writer_locks"][0]["operation_receipt"]
        self.assertEqual("matching", evidence["status"])
        self.assertTrue(evidence["matching_receipt"])


if __name__ == "__main__":
    unittest.main()
