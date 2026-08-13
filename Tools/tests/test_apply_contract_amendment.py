"""The guarded writer for a frozen Task Contract's one amendable field.

K13/06 acknowledged this gap in so many words: with no guarded writer for a
non-scope Contract change, the operator must pause or cancel the task and
carry the change into a successor.  This module pins the writer that closes
it, and the properties that keep a contract amendment from becoming a way to
rewrite a task's identity.

The anchor chain is the heart of it.  Once the Queue materializes, the
contract fingerprint is frozen and every consumer carries it; a mutation
outside a chained writer fails the whole runtime closed.  The happy-path test
therefore does not merely check the field changed -- it checks the runtime
validates *afterward with no allowance*, which is only possible if the commit
receipt is a well-formed anchor event continuing the chain.

Placement is the other half.  An exception lives in the contract because it
is current authorization: the amendment row is history, and K13/06 says
history never authorizes.  The row born in any state but verified is pinned
as an error, because this writer has no pending phase to be interrupted in.
"""

import contextlib
import copy
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent

for path in (str(TOOLS), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import check_queue  # noqa: E402
import kblib  # noqa: E402
from test_apply_task_plan import (  # noqa: E402
    TaskPlanTransactionTests, PLAN_RELATIVE)


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "_apply_contract_amendment_under_test",
        TOOLS / "apply_contract_amendment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply_contract_amendment = _load_tool()

AMENDMENT_RELATIVE = ".cambium/deltas/contract-amendments/CA-001.yaml"

EXCEPTION = {
    "decision_id": "PE-001",
    "policy_id": "priority_quota.P0",
    "baseline_policy_fingerprint": "sha256:" + "a" * 64,
    "limit": 18,
    "scope_kind": "task",
    "scope_ref": "new-task",
    "rationale": "migration retains validated P0 owners this task",
    "approval_reference": "operator approval 2026-08-13",
}


class ContractAmendmentTests(TaskPlanTransactionTests):
    """Runs on a materialized runtime built by the initial-planning tests.

    Inheriting the fixture is deliberate: the contract this writer amends is
    the one apply_task_plan wrote and compile_queue froze, so the two
    transactions are exercised in the order a real task lives them.
    """

    def materialize(self):
        self.write_plan(self.plan())
        import test_apply_task_plan as planning
        prepared_plan = planning.apply_task_plan.prepare(
            str(self.root), PLAN_RELATIVE)
        self.assertEqual(0, self.run_tool(apply=True))
        self.compile_the_queue(prepared_plan)
        self.assertEqual([], check_queue.validate_runtime(
            str(self.root))["errors"])
        # The amendment applies only to a running task; planned -> paused is
        # the lightest legal transition (activation is owned by the batch
        # opening path and needs a readiness receipt this fixture does not).
        result = subprocess.run(
            [sys.executable, str(TOOLS / "update_task.py"), str(self.root),
             "--transition", "paused", "--checkpoint-summary",
             "admitted; paused pending first batch",
             "--actor-role", "integrator",
             "--expected-progress-sha256",
             self.state_sha(check_queue.PROGRESS_PATH),
             "--expected-queue-sha256",
             self.state_sha(check_queue.QUEUE_PATH),
             "--apply"],
            text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)

    def amendment_plan(self, **overrides):
        plan = {
            "schema_version": 1,
            "amendment_id": "CA-001",
            "task_id": "new-task",
            "date": "2026-08-13",
            "summary": "grant a bounded P0 quota exception for this task",
            "approval_reference": "operator approval 2026-08-13",
            "before": {
                "coverage_sha256": self.state_sha(check_queue.COVERAGE_PATH),
                "queue_sha256": self.state_sha(check_queue.QUEUE_PATH),
                "progress_sha256": self.state_sha(check_queue.PROGRESS_PATH),
            },
            "contract_version_after": "c2",
            "policy_exceptions_after": [copy.deepcopy(EXCEPTION)],
        }
        plan.update(overrides)
        return plan

    def write_amendment(self, plan):
        path = self.root / AMENDMENT_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        return AMENDMENT_RELATIVE

    def run_amendment(self, apply=False):
        command = [str(self.root), "--plan", AMENDMENT_RELATIVE,
                   "--actor-role", "integrator"]
        if apply:
            command.append("--apply")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = apply_contract_amendment.main(command)
        self.printed = buffer.getvalue()
        return code

    def amendment_error(self, plan):
        self.write_amendment(plan)
        with self.assertRaises(apply_contract_amendment.Refusal) as caught:
            apply_contract_amendment.prepare(str(self.root),
                                             AMENDMENT_RELATIVE)
        return str(caught.exception)

    # ---- the edge it closes --------------------------------------------

    def test_the_frozen_contract_is_amended_and_the_chain_follows(self):
        self.materialize()
        self.write_amendment(self.amendment_plan())
        self.assertEqual(0, self.run_amendment(apply=True))

        contract = self.document(check_queue.PROGRESS_PATH)["contract"]
        self.assertEqual("c2", contract["contract_version"])
        self.assertEqual(
            ["PE-001"],
            [entry["decision_id"]
             for entry in contract["policy_exceptions"]])

        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"],
            "the runtime validates with no allowance only if the commit "
            "receipt is a well-formed anchor event; a contract mutated "
            "outside the chain fails closed, which is the entire point")

    def test_a_dry_run_writes_nothing(self):
        self.materialize()
        before = {name: self.state_sha(path) for name, path in (
            ("coverage", check_queue.COVERAGE_PATH),
            ("queue", check_queue.QUEUE_PATH),
            ("progress", check_queue.PROGRESS_PATH))}
        self.write_amendment(self.amendment_plan())
        self.assertEqual(0, self.run_amendment())
        for name, path in (("coverage", check_queue.COVERAGE_PATH),
                           ("queue", check_queue.QUEUE_PATH),
                           ("progress", check_queue.PROGRESS_PATH)):
            self.assertEqual(before[name], self.state_sha(path), name)

    def test_removing_an_exception_is_the_same_transaction(self):
        """The after-image is complete, so revocation is not a new verb."""
        self.materialize()
        self.write_amendment(self.amendment_plan())
        self.assertEqual(0, self.run_amendment(apply=True))

        second = self.amendment_plan(
            amendment_id="CA-002",
            contract_version_after="c3",
            policy_exceptions_after=[],
            summary="revoke PE-001; the excess was resolved by demotion")
        path = self.root / ".cambium/deltas/contract-amendments/CA-002.yaml"
        path.write_text(kblib.canonical_yaml(second), encoding="utf-8")
        self.assertEqual(0, apply_contract_amendment.main(
            [str(self.root), "--plan",
             ".cambium/deltas/contract-amendments/CA-002.yaml",
             "--actor-role", "integrator", "--apply"]))
        contract = self.document(check_queue.PROGRESS_PATH)["contract"]
        self.assertEqual([], contract["policy_exceptions"])
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"])

    # ---- refusals -------------------------------------------------------

    def test_an_unmaterialized_runtime_is_refused(self):
        self.write_plan(self.plan())
        self.assertEqual(0, self.run_tool(apply=True))
        # Coverage and Contract are filled; the Queue is not materialized.
        message = self.amendment_error(self.amendment_plan())
        self.assertIn("not materialized", message)
        self.assertIn("amend the task plan", message)

    def test_a_moved_runtime_is_refused_rather_than_merged(self):
        self.materialize()
        plan = self.amendment_plan()
        plan["before"]["progress_sha256"] = "sha256:" + "0" * 64
        self.assertIn("prepared against", self.amendment_error(plan))

    def test_an_unchanged_contract_version_is_refused(self):
        self.materialize()
        plan = self.amendment_plan(contract_version_after="c1")
        self.assertIn("must advance", self.amendment_error(plan))

    def test_a_malformed_exception_is_refused_in_the_validator_s_words(self):
        self.materialize()
        exception = copy.deepcopy(EXCEPTION)
        exception["scope_kind"] = "forever"
        del exception["rationale"]
        plan = self.amendment_plan(policy_exceptions_after=[exception])
        message = self.amendment_error(plan)
        self.assertIn("K13/02 shape", message)
        self.assertIn("scope_kind", message)

    def test_an_unfilled_template_sentinel_is_refused(self):
        self.materialize()
        plan = self.amendment_plan(
            approval_reference=apply_contract_amendment.SENTINEL)
        self.assertIn("sentinel", self.amendment_error(plan))

    def test_a_bypassed_row_fails_the_runtime_closed(self):
        """A contract-amendment row not born verified is a bypassed writer."""
        self.materialize()
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.parse_yaml_subset(
            progress_path.read_text(encoding="utf-8"))
        progress["amendments"].append({
            "id": "CA-999", "date": "2026-08-13",
            "summary": "hand-inserted", "status": "approved",
            "writeback_done": False, "operation": "contract-amendment",
        })
        progress_path.write_text(kblib.canonical_yaml(progress),
                                 encoding="utf-8")
        errors = check_queue.validate_runtime(str(self.root))["errors"]
        self.assertTrue(
            any("Progress amendments[" in error for error in errors),
            "a hand-appended contract-amendment row must fail closed; the "
            "writer has no pending phase, so this shape is a bypass, not an "
            "interruption:\n" + "\n".join(errors[:6]))

    def test_an_unknown_operation_still_fails_closed_beside_the_new_one(self):
        """Adding a known operation must not reopen the fail-open hole."""
        self.materialize()
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.parse_yaml_subset(
            progress_path.read_text(encoding="utf-8"))
        progress["amendments"].append({
            "id": "CA-998", "date": "2026-08-13",
            "summary": "novel", "status": "approved",
            "writeback_done": False, "operation": "policy-exception",
        })
        progress_path.write_text(kblib.canonical_yaml(progress),
                                 encoding="utf-8")
        errors = check_queue.validate_runtime(str(self.root))["errors"]
        self.assertTrue(any("unknown operation" in error for error in errors),
                        "\n".join(errors[:6]))



if __name__ == "__main__":
    unittest.main()
