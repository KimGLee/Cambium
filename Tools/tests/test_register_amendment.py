from pathlib import Path
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import check_queue
import kblib
import register_amendment
from profile_fixture import install_loadable_profile


class RegisterAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        (self.root / ".cambium/deltas/amendments").mkdir(parents=True)
        (self.root / ".cambium/deltas/replans").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

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
                self.root / check_queue.COVERAGE_PATH),
            "progress": kblib.sha256_file(
                self.root / check_queue.PROGRESS_PATH),
            "queue": kblib.sha256_file(
                self.root / check_queue.QUEUE_PATH),
        }

    def command(self, operation, *operation_args, apply=False, shas=None,
                actor_role="worker", approval_reference="user:fixture-approval",
                decision_mode="auto"):
        shas = shas or self.shas()
        args = [
            sys.executable, str(TOOLS / "register_amendment.py"),
            str(self.root), "--operation", operation,
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
        return subprocess.run(
            args, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )

    def scope_proposal(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-05T00:00:00Z"
        coverage["batch_specs"].append({
            "id": "B3", "family": "Core", "order_hint": 3,
            "source_route": "R03", "execution_mode": "concurrent-worker",
            "depends_on": ["B2"], "confirmation_required": False,
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
        return coverage

    def cancel_proposal(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["scope_version"] = "s2"
        coverage["updated_at"] = "2026-08-05T00:00:00Z"
        coverage["batch_specs"] = [
            entry for entry in coverage["batch_specs"] if entry["id"] != "B2"
        ]
        page = next(entry for entry in coverage["pages"]
                    if entry["path"] == "Topics/B.md")
        page["coverage_disposition"] = "deferred"
        page["next_batch"] = None
        page["deferred_reason"] = "removed by approved Amendment"
        page["reentry_condition"] = "a successor Amendment restores scope"
        return coverage

    def cross_plan(self, operation):
        amendment_id = "A-SCOPE" if operation == "scope-replan" else "A-CANCEL"
        proposal = (self.scope_proposal() if operation == "scope-replan"
                    else self.cancel_proposal())
        proposal_relative = ".cambium/deltas/amendments/%s.coverage.yaml" % \
            amendment_id
        proposal_path = self.write_yaml(proposal_relative, proposal)
        queue = self.load(check_queue.QUEUE_PATH)
        plan = {
            "schema_version": 1,
            "amendment_id": amendment_id,
            "operation": operation,
            "affected_pages": (["Topics/C.md"] if operation == "scope-replan"
                               else ["Topics/B.md"]),
            "affected_batches": (["B3"] if operation == "scope-replan"
                                 else ["B2"]),
            "scope_version_before": queue["scope_version"],
            "scope_version_after": proposal["scope_version"],
            "queue_revision_before": queue["queue_revision"],
            "queue_revision_after": queue["queue_revision"] + 1,
            "state_revision_before": queue["state_revision"],
            "state_revision_after": (queue["state_revision"] + 1
                                     if operation == "cancel-batch"
                                     else queue["state_revision"]),
            "coverage_proposal_path": proposal_relative,
            "coverage_proposal_sha256": kblib.sha256_file(proposal_path),
            "cancel_batch_id": "B2" if operation == "cancel-batch" else None,
        }
        plan_relative = ".cambium/deltas/amendments/%s.yaml" % amendment_id
        plan_path = self.write_yaml(plan_relative, plan)
        return plan_relative, plan_path, proposal_relative

    def queue_proposal(self):
        coverage = self.load(check_queue.COVERAGE_PATH)
        spec = next(entry for entry in coverage["batch_specs"]
                    if entry["id"] == "B2")
        spec["execution_mode"] = "serial-integrator"
        relative = ".cambium/deltas/replans/A-QUEUE.coverage.yaml"
        self.write_yaml(relative, coverage)
        return relative

    def receipt(self):
        path = self.root / register_amendment.RECEIPT_PATH
        records = [json.loads(line) for line in path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(1, len(records))
        return records[0]

    def install_delegated_authority(self, *change_classes):
        """Re-anchor the copied origin fixture with a delegated contract.

        This is fixture construction, not a production mutation: the initial
        Queue receipt is the copied runtime's origin anchor, so both sides are
        rebuilt before the first validation in this test.
        """
        progress = self.load(check_queue.PROGRESS_PATH)
        progress["contract"]["amendment_authority"] = {
            "schema_version": 1,
            "authority_id": "AUTH-FIXTURE",
            "mode": "delegated-integrator",
            "allowed_change_classes": sorted(change_classes),
        }
        self.write_yaml(check_queue.PROGRESS_PATH, progress)
        receipt_path = self.root / \
            ".cambium/receipts/task-transitions.jsonl"
        receipts = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        origin = next(record for record in receipts
                      if record["receipt_id"] ==
                      progress["initial_queue_receipt"])
        origin["contract_sha256"] = check_queue._contract_sha256(progress)
        origin["after_progress_sha256"] = kblib.sha256_file(
            self.root / check_queue.PROGRESS_PATH)
        receipt_path.write_text(
            "".join(json.dumps(record) + "\n" for record in receipts),
            encoding="utf-8")

    def prepare_scope_registration(self):
        plan_relative, plan_path, _ = self.cross_plan("scope-replan")
        expected = self.shas()
        args = SimpleNamespace(
            operation="scope-replan", plan=plan_relative,
            amendment_id=None, coverage_proposal=None,
            date=time.strftime("%Y-%m-%d", time.gmtime()),
            summary="Approved fixture Amendment",
            approval_reference="user:fixture-approval",
        )
        prepared = register_amendment._prepare(
            str(self.root), args, expected)
        return plan_relative, plan_path, expected, prepared

    def assert_common_registration(self, amendment_id, operation, before):
        progress = self.load(check_queue.PROGRESS_PATH)
        self.assertEqual(1, len(progress["amendments"]))
        record = progress["amendments"][0]
        self.assertEqual(amendment_id, record["id"])
        self.assertEqual(operation, record["operation"])
        self.assertEqual("approved", record["status"])
        self.assertIs(record["writeback_done"], False)
        self.assertEqual("user:fixture-approval", record["approval_reference"])
        self.assertEqual("explicit-user", record["decision_mode"])
        self.assertIsNone(record["authority_id"])
        self.assertIsNone(record["authority_sha256"])
        self.assertTrue(record["change_classes"])
        self.assertRegex(record["amendment_impact_sha256"],
                         r"^sha256:[0-9a-f]{64}$")
        receipt = self.receipt()
        self.assertEqual(record["registration_receipt"], receipt["receipt_id"])
        self.assertEqual("register_amendment", receipt["tool"])
        self.assertEqual(register_amendment.TOOL_VERSION, receipt["tool_version"])
        for field in ("decision_mode", "authority_id", "authority_sha256",
                      "change_classes", "amendment_impact_sha256"):
            self.assertEqual(record[field], receipt[field])
        self.assertEqual("amendment_registration", receipt["check"])
        self.assertEqual(before["coverage"],
                         receipt["before_coverage_sha256"])
        self.assertEqual(before["coverage"],
                         receipt["after_coverage_sha256"])
        self.assertEqual(before["queue"],
                         receipt["before_required_queue_sha256"])
        self.assertEqual(before["queue"],
                         receipt["after_required_queue_sha256"])
        self.assertNotEqual(receipt["before_progress_sha256"],
                            receipt["after_progress_sha256"])
        self.assertEqual(self.shas()["progress"],
                         receipt["after_progress_sha256"])
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])
        return record, receipt

    def test_scope_replan_dry_run_is_non_mutating(self):
        plan_relative, _, _ = self.cross_plan("scope-replan")
        before = self.shas()
        completed = self.command(
            "scope-replan", "--plan", plan_relative,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("dry run", completed.stdout)
        self.assertEqual(before, self.shas())
        self.assertFalse((self.root / register_amendment.RECEIPT_PATH).exists())

    def test_scope_replan_registers_exact_plan_and_receipt(self):
        plan_relative, plan_path, proposal_relative = self.cross_plan(
            "scope-replan")
        before = self.shas()
        completed = self.command(
            "scope-replan", "--plan", plan_relative,
            apply=True, actor_role="integrator",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        record, receipt = self.assert_common_registration(
            "A-SCOPE", "scope-replan", before)
        self.assertEqual(plan_relative, record["plan_path"])
        self.assertEqual(kblib.sha256_file(plan_path), record["plan_sha256"])
        self.assertEqual(proposal_relative,
                         record["coverage_proposal_path"])
        self.assertEqual(record["plan_sha256"], receipt["plan_sha256"])
        self.assertEqual("s1", receipt["scope_version_before"])
        self.assertEqual("s2", receipt["scope_version_after"])

    def test_contract_delegation_registers_without_a_fresh_user_prompt(self):
        self.install_delegated_authority(
            "batch-add", "required-object-add")
        self.assertEqual([], check_queue.validate_runtime(
            self.root)["errors"])
        plan_relative, _, _ = self.cross_plan("scope-replan")

        completed = self.command(
            "scope-replan", "--plan", plan_relative,
            approval_reference=None, apply=True,
            actor_role="integrator")

        self.assertEqual(0, completed.returncode, completed.stdout)
        progress = self.load(check_queue.PROGRESS_PATH)
        record = progress["amendments"][-1]
        self.assertEqual("contract-delegated", record["decision_mode"])
        self.assertEqual("AUTH-FIXTURE", record["authority_id"])
        self.assertEqual("contract:AUTH-FIXTURE",
                         record["approval_reference"])
        self.assertEqual(
            ["batch-add", "required-object-add"],
            record["change_classes"])
        self.assertEqual([], check_queue.validate_runtime(
            self.root)["errors"])

    def test_registration_transaction_runs_profile_load_producer_once(self):
        producer = check_queue.check_profile.evaluate_profile_load
        receipt_path = self.root / register_amendment.RECEIPT_PATH
        with mock.patch.object(
                check_queue.check_profile, "evaluate_profile_load",
                wraps=producer) as evaluate:
            _, _, _, prepared = self.prepare_scope_registration()
            register_amendment._apply(
                str(self.root), prepared, str(receipt_path))

        self.assertEqual(1, evaluate.call_count)
        self.assertEqual([], check_queue.validate_runtime(self.root)["errors"])

    def test_registration_rejects_stale_admitted_profile_before_publication(self):
        _, _, before, prepared = self.prepare_scope_registration()
        progress_before = (self.root / check_queue.PROGRESS_PATH).read_bytes()
        profile_slot = self.root / "profiles/test-profile/slots.md"
        profile_slot.write_text(
            profile_slot.read_text(encoding="utf-8") +
            "\n<!-- changed after transaction admission -->\n",
            encoding="utf-8",
        )
        receipt_path = self.root / register_amendment.RECEIPT_PATH

        with self.assertRaisesRegex(
                ValueError, "changed after profile-load authorization"):
            register_amendment._apply(
                str(self.root), prepared, str(receipt_path))

        self.assertEqual(progress_before,
                         (self.root / check_queue.PROGRESS_PATH).read_bytes())
        self.assertEqual(before, self.shas())
        self.assertFalse(receipt_path.exists())
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_cancel_batch_registers_exact_plan(self):
        plan_relative, _, _ = self.cross_plan("cancel-batch")
        before = self.shas()
        completed = self.command(
            "cancel-batch", "--plan", plan_relative,
            apply=True, actor_role="integrator",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        record, receipt = self.assert_common_registration(
            "A-CANCEL", "cancel-batch", before)
        self.assertEqual("B2", record["cancel_batch_id"])
        self.assertEqual(["B2"], record["affected_batches"])
        self.assertEqual(["Topics/B.md"], record["affected_pages"])
        self.assertEqual(0, receipt["state_revision_before"])
        self.assertEqual(1, receipt["state_revision_after"])

    def test_queue_replan_derives_exact_deterministic_bindings(self):
        proposal = self.queue_proposal()
        before = self.shas()
        first = self.command(
            "queue-replan", "--amendment-id", "A-QUEUE",
            "--coverage-proposal", proposal,
        )
        second = self.command(
            "queue-replan", "--amendment-id", "A-QUEUE",
            "--coverage-proposal", proposal,
        )
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertEqual(0, second.returncode, second.stdout)
        self.assertEqual(before, self.shas())

        completed = self.command(
            "queue-replan", "--amendment-id", "A-QUEUE",
            "--coverage-proposal", proposal,
            apply=True, actor_role="integrator",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        record, receipt = self.assert_common_registration(
            "A-QUEUE", "queue-replan", before)
        self.assertEqual(["B2"], record["affected_batches"])
        self.assertEqual([], record["affected_pages"])
        self.assertRegex(record["replan_diff_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(record["replan_diff_sha256"],
                         receipt["replan_diff_sha256"])
        self.assertEqual(0, receipt["state_revision_before"])
        self.assertEqual(0, receipt["state_revision_after"])

    def test_apply_requires_integrator(self):
        plan_relative, _, _ = self.cross_plan("scope-replan")
        before = self.shas()
        completed = self.command(
            "scope-replan", "--plan", plan_relative, apply=True,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("only actor-role integrator", completed.stdout)
        self.assertEqual(before, self.shas())

    def test_user_only_contract_without_fresh_approval_is_refused(self):
        plan_relative, _, _ = self.cross_plan("scope-replan")

        completed = self.command(
            "scope-replan", "--plan", plan_relative,
            approval_reference=None)

        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("fresh user decision required", completed.stdout)

    def test_stale_any_state_sha_fails_closed(self):
        plan_relative, _, _ = self.cross_plan("scope-replan")
        for name in ("coverage", "progress", "queue"):
            with self.subTest(name=name):
                stale = self.shas()
                stale[name] = "sha256:" + "0" * 64
                completed = self.command(
                    "scope-replan", "--plan", plan_relative,
                    apply=True, actor_role="integrator", shas=stale,
                )
                self.assertEqual(1, completed.returncode, completed.stdout)
                self.assertIn("expected %s SHA" % name, completed.stdout)

    def test_rejects_second_pending_amendment(self):
        first_plan, _, _ = self.cross_plan("scope-replan")
        completed = self.command(
            "scope-replan", "--plan", first_plan,
            apply=True, actor_role="integrator",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        # A queue proposal is independently valid, but registration is
        # serialized until the prior authorization is consumed.
        proposal = self.queue_proposal()
        rejected = self.command(
            "queue-replan", "--amendment-id", "A-QUEUE",
            "--coverage-proposal", proposal,
        )
        self.assertEqual(1, rejected.returncode, rejected.stdout)
        self.assertIn("already has pending Amendment A-SCOPE", rejected.stdout)

    def withdraw(self, amendment_id, *extra, apply=False, shas=None,
                 actor_role="integrator",
                 reason="planned final state can no longer validate"):
        shas = shas or self.shas()
        args = [
            sys.executable, str(TOOLS / "register_amendment.py"),
            str(self.root), "--withdraw", amendment_id,
            "--reason", reason,
            "--expected-coverage-sha256", shas["coverage"],
            "--expected-progress-sha256", shas["progress"],
            "--expected-queue-sha256", shas["queue"],
            "--actor-role", actor_role,
            *extra,
        ]
        if apply:
            args.append("--apply")
        return subprocess.run(
            args, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )

    def test_withdrawal_unwedges_the_one_pending_rule(self):
        """K13/06: withdraw a pending registration, then register anew."""
        first_plan, _, _ = self.cross_plan("scope-replan")
        completed = self.command(
            "scope-replan", "--plan", first_plan,
            apply=True, actor_role="integrator",
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        withdrawn = self.withdraw("A-SCOPE", apply=True)
        self.assertEqual(0, withdrawn.returncode, withdrawn.stdout)
        self.assertIn("withdrawn", withdrawn.stdout)
        progress = self.load(check_queue.PROGRESS_PATH)
        row = next(r for r in progress["amendments"]
                   if r.get("id") == "A-SCOPE")
        self.assertEqual("withdrawn", row["status"])
        self.assertFalse(row["writeback_done"])
        self.assertTrue(row["withdrawal_receipt"])
        self.assertEqual("planned final state can no longer validate",
                         row["withdrawal_reason"])
        self.assertEqual([], check_queue.validate_runtime(
            str(self.root))["errors"])
        # A withdrawn row is final: it raises no resume/terminal
        # reconcile obligation.
        _, pending = check_queue._pending_control_ids(
            self.load(check_queue.PROGRESS_PATH))
        self.assertEqual([], pending)
        # The one-pending rule is unwedged; the burned ID stays refused.
        proposal = self.queue_proposal()
        second = self.command(
            "queue-replan", "--amendment-id", "A-QUEUE",
            "--coverage-proposal", proposal,
            apply=True, actor_role="integrator",
        )
        self.assertEqual(0, second.returncode, second.stdout)
        reused = self.command(
            "queue-replan", "--amendment-id", "A-SCOPE",
            "--coverage-proposal", self.queue_proposal(),
        )
        self.assertEqual(1, reused.returncode, reused.stdout)
        self.assertIn("already contains Amendment A-SCOPE", reused.stdout)

    def test_withdrawal_is_dry_run_first_and_integrator_only(self):
        first_plan, _, _ = self.cross_plan("scope-replan")
        self.command("scope-replan", "--plan", first_plan,
                     apply=True, actor_role="integrator")
        before = self.shas()
        dry = self.withdraw("A-SCOPE")
        self.assertEqual(0, dry.returncode, dry.stdout)
        self.assertIn("dry run", dry.stdout)
        self.assertEqual(before, self.shas())
        worker = self.withdraw("A-SCOPE", apply=True, actor_role="worker")
        self.assertEqual(1, worker.returncode, worker.stdout)

    def test_withdrawal_requires_a_pending_row_and_a_reason(self):
        missing = self.withdraw("A-ABSENT", apply=True)
        self.assertEqual(1, missing.returncode, missing.stdout)
        self.assertIn("no Amendment A-ABSENT", missing.stdout)
        first_plan, _, _ = self.cross_plan("scope-replan")
        self.command("scope-replan", "--plan", first_plan,
                     apply=True, actor_role="integrator")
        empty = self.withdraw("A-SCOPE", reason="  ", apply=True)
        self.assertEqual(1, empty.returncode, empty.stdout)
        withdrawn = self.withdraw("A-SCOPE", apply=True)
        self.assertEqual(0, withdrawn.returncode, withdrawn.stdout)
        again = self.withdraw("A-SCOPE", apply=True)
        self.assertEqual(1, again.returncode, again.stdout)
        self.assertIn("not pending", again.stdout)

    def test_unknown_historical_registration_version_fails_closed(self):
        """Producer-era handling is closed, not a license for any version."""
        first_plan, _, _ = self.cross_plan("scope-replan")
        self.command("scope-replan", "--plan", first_plan,
                     apply=True, actor_role="integrator")
        self.withdraw("A-SCOPE", apply=True)
        receipts_path = self.root / register_amendment.RECEIPT_PATH
        text = receipts_path.read_text(encoding="utf-8").replace(
            '"tool_version": "%s"' % register_amendment.TOOL_VERSION,
            '"tool_version": "0.9.0"')
        receipts_path.write_text(text, encoding="utf-8")
        errors = check_queue.validate_runtime(str(self.root))["errors"]
        self.assertTrue(any(
            "unsupported register_amendment producer version '0.9.0'" in error
            for error in errors), "\n".join(errors))

    def test_rejects_unknown_schema_instead_of_legacy_guessing(self):
        plan_relative, _, _ = self.cross_plan("scope-replan")
        coverage = self.load(check_queue.COVERAGE_PATH)
        coverage["schema_version"] = 0
        self.write_yaml(check_queue.COVERAGE_PATH, coverage)
        completed = self.command(
            "scope-replan", "--plan", plan_relative,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("current runtime is inconsistent", completed.stdout)

    def test_shared_writer_lock_blocks_registration(self):
        plan_relative, _, _ = self.cross_plan("scope-replan")
        lock = self.root / ".cambium/tmp/state-writer.lock"
        lock.mkdir()
        (lock / "owner.json").write_text(json.dumps({
            "lock_name": "state-writer", "pid": 999999,
            "created_at": "2026-08-05T00:00:00Z",
            "operation": {"tool": "fixture", "action": "write"},
        }) + "\n", encoding="utf-8")
        completed = self.command(
            "scope-replan", "--plan", plan_relative,
            apply=True, actor_role="integrator",
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("writer lock", completed.stdout)

    def test_locked_preflight_rejects_changed_staged_artifact(self):
        _, plan_path, before, prepared = self.prepare_scope_registration()
        progress_before = (self.root / check_queue.PROGRESS_PATH).read_bytes()
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        receipt_path = self.root / register_amendment.RECEIPT_PATH
        with self.assertRaisesRegex(
                ValueError, "staged artifact bytes changed"):
            register_amendment._apply(
                str(self.root), prepared, str(receipt_path))
        self.assertEqual(progress_before,
                         (self.root / check_queue.PROGRESS_PATH).read_bytes())
        self.assertEqual(before, self.shas())
        self.assertFalse(receipt_path.exists())
        self.assertFalse((self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_receipt_first_interruption_keeps_progress_valid_and_lock_visible(self):
        _, _, before, prepared = self.prepare_scope_registration()
        progress_before = (self.root / check_queue.PROGRESS_PATH).read_bytes()
        receipt_path = self.root / register_amendment.RECEIPT_PATH
        with mock.patch.object(
                kblib, "atomic_write_text",
                side_effect=OSError("simulated Progress publication failure")):
            with self.assertRaisesRegex(
                    OSError, "simulated Progress publication failure"):
                register_amendment._apply(
                    str(self.root), prepared, str(receipt_path))
        self.assertEqual(progress_before,
                         (self.root / check_queue.PROGRESS_PATH).read_bytes())
        self.assertEqual(before, self.shas())
        receipt = self.receipt()
        self.assertEqual("amendment_registration", receipt["check"])
        runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], runtime["pending_cross_ledger_amendments"])
        self.assertEqual(1, len(runtime["writer_locks"]))
        evidence = runtime["writer_locks"][0]["operation_receipt"]
        self.assertEqual("matching", evidence["status"])
        self.assertTrue(evidence["matching_receipt"])


if __name__ == "__main__":
    unittest.main()
