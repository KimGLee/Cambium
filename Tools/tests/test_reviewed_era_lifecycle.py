"""The positive control for the disposition K02/01 offers.

The wedge this pins was found the only way it could be: by trying to
activate a batch for the first time since the K02/01 rule landed, and
failing. The rule offers three dispositions for legacy `reviewed` records
and one of them -- carry them under an explicit exception with a stated
end -- had no machine carrier. The declaration lived in a revision's
prose, `check_queue` re-raised the candidate every run, and because
`update_queue` activates a batch only on a PASSING readiness gate, the
corpus that chose that disposition could not run the very re-reviews that
resolve it.

Unit tests covered the detector and the resolver separately. Neither could
see the wedge, because the wedge lives in the JOIN: candidate -> readiness
receipt result -> activation refusal. This module executes that join end to
end on a real fixture with the real writers, so the next change to any one
link fails here rather than on an adopter's first batch.
"""

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))

import check_queue  # noqa: E402
import contract_exception_policy  # noqa: E402
import kblib  # noqa: E402
import test_check_batch_close  # noqa: E402  # module-qualified: see load_tests


def _load_amendment_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_aca_reviewed_era", TOOLS / "apply_contract_amendment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply_contract_amendment = _load_amendment_tool()


class ReviewedEraActivationTests(test_check_batch_close.CheckBatchCloseTests):
    """Wedge, grant, activation -- the join no unit test could see.

    What is shared here is a state, not a walk: the close suite's fixture
    with the profile installed and one Coverage record rewritten into the
    legacy pre-K02/01 shape, frozen once per process before any writer has
    run.  Sharing that prologue is safe because no test below reads
    anything a walk produced -- every test IS a walk, and the join order
    (wedge, grant, re-gate) is each test's subject, so each starts from a
    private copy of the template and drives its own writers end to end.
    """

    def runTest(self):  # pragma: no cover - harness artifact
        pass

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(legacy_template_root(), self.root, symlinks=True)
        self.unsupported = 1

    def reanchor_origin(self):
        """Re-anchor the fixture's origin receipt to the edited bytes.

        The legacy state this module needs predates every writer, so the
        fixture writes it directly; the origin receipt that binds Coverage
        bytes must follow, exactly as a real writer's after-image would.
        """
        import json
        receipt_path = self.root / ".cambium/receipts/task-transitions.jsonl"
        records = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("receipt_id") == "audit-fixture-initial-queue":
                record["after_coverage_sha256"] = kblib.sha256_file(
                    self.root / check_queue.COVERAGE_PATH)
        receipt_path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n"
                    for record in records), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    # ---- helpers -------------------------------------------------------

    def readiness_receipt(self, batch="B1"):
        """Run the admission gate and return (result, receipt_id)."""
        import json
        relative = ".cambium/receipts/ready-%s.jsonl" % batch.lower()
        completed = self.run_tool(
            "check_queue.py", "--require-ready", batch, "--receipts", relative)
        rows = [json.loads(line) for line in
                (self.root / relative).read_text(
                    encoding="utf-8").strip().splitlines()]
        del completed
        return rows[-1]["result"], rows[-1]["receipt_id"]

    def activate(self, receipt_id, batch="B1"):
        queue = kblib.parse_yaml_subset(
            (self.root / check_queue.QUEUE_PATH).read_text(encoding="utf-8"))
        return self.run_tool(
            "update_queue.py", "--id", batch, "--transition", "open",
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--actor-role", "integrator", "--gate-receipt", receipt_id,
            "--apply")

    def grant(self, limit, *, amendment_id="CA-COV-1",
              contract_version_after="c-cov-1", policy_id=None,
              fingerprint=None):
        """Register the exception through its only writer."""
        if fingerprint is None:
            _policy, fingerprint, _errors = (
                contract_exception_policy.effective_coverage_policy())
        progress_path = self.root / check_queue.PROGRESS_PATH
        plan = {
            "schema_version": 1,
            "amendment_id": amendment_id,
            "task_id": "fixture-task",
            "date": "2026-08-13",
            "summary": "record the declared K02/01 migration disposition",
            "approval_reference": "adoption Change Summary",
            "before": {
                "coverage_sha256": kblib.sha256_file(
                    self.root / check_queue.COVERAGE_PATH),
                "queue_sha256": kblib.sha256_file(
                    self.root / check_queue.QUEUE_PATH),
                "progress_sha256": kblib.sha256_file(progress_path),
            },
            "contract_version_after": contract_version_after,
            "policy_exceptions_after": [{
                "decision_id": "PE-COV-001",
                "policy_id": policy_id or "coverage.reviewed_era",
                "baseline_policy_fingerprint": fingerprint,
                "limit": limit,
                "scope_kind": "task",
                "scope_ref": "fixture-task",
                "rationale": "legacy reviewed records are re-reviewed as "
                             "their batches run; the exception ends at "
                             "queue exhaustion",
                "approval_reference": "adoption Change Summary",
            }],
        }
        relative = ".cambium/deltas/contract-amendments/%s.yaml" % amendment_id
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = apply_contract_amendment.main(
                [str(self.root), "--plan", relative,
                 "--actor-role", "integrator", "--apply"])
        return code, buffer.getvalue()

    # ---- the join ------------------------------------------------------

    def test_the_declared_disposition_no_longer_wedges_the_queue(self):
        """Wedge reproduced, then cleared by the writer that owns it."""
        result, receipt_id = self.readiness_receipt()
        self.assertEqual("candidate", result)
        refused = self.activate(receipt_id)
        self.assertIn("expected 'pass'", refused.stdout)
        queue = kblib.parse_yaml_subset(
            (self.root / check_queue.QUEUE_PATH).read_text(encoding="utf-8"))
        self.assertEqual("queued", {i["id"]: i["state"]
                                    for i in queue["required_queue"]}["B1"])

        code, output = self.grant(self.unsupported)
        self.assertEqual(0, code, output)
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"],
            "the amendment must leave a runtime that validates")

        result, receipt_id = self.readiness_receipt()
        self.assertEqual(
            "pass", result,
            "a bounded exception disposes of the candidate, so the gate "
            "that activation consumes can pass")
        activated = self.activate(receipt_id)
        self.assertEqual(0, activated.returncode, activated.stdout)
        queue = kblib.parse_yaml_subset(
            (self.root / check_queue.QUEUE_PATH).read_text(encoding="utf-8"))
        self.assertEqual("open", {i["id"]: i["state"]
                                  for i in queue["required_queue"]}["B1"])

    def test_the_grant_is_reported_not_hidden(self):
        self.grant(self.unsupported)
        completed = self.run_tool("check_queue.py")
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("[NOTE]", completed.stdout)
        self.assertIn("PE-COV-001", completed.stdout)
        self.assertIn("still claim authoring_status=reviewed",
                      completed.stdout)

    def test_a_ceiling_below_the_count_still_wedges(self):
        """The bound is the whole protection: it must actually bind."""
        code, output = self.grant(self.unsupported - 1)
        self.assertEqual(0, code, output)
        result, receipt_id = self.readiness_receipt()
        self.assertEqual("candidate", result)
        refused = self.activate(receipt_id)
        self.assertIn("expected 'pass'", refused.stdout)

    def test_the_writer_refuses_a_fingerprint_from_another_family(self):
        """A quota fingerprint cannot stand in for the kernel-owned rule."""
        _policy, quota_fingerprint, _errors = (
            contract_exception_policy.effective_priority_policy(
                (self.root / "profiles/test-profile/slots.md").read_text(
                    encoding="utf-8")))
        code, output = self.grant(self.unsupported,
                                  fingerprint=quota_fingerprint)
        self.assertEqual(1, code, output)
        self.assertIn("coverage.reviewed_era", output)
        self.assertIn("does not match the current effective policy", output)


# ---------------------------------------------------------------------------
# Scenario template.  The legacy prologue is built once per process, into a
# frozen tree held for the whole run; tests take copies, never the tree.
# ---------------------------------------------------------------------------

_TEMPLATE_DIRS = []  # TemporaryDirectory handles, alive for the run
_LEGACY_ROOT = None


def legacy_template_root():
    """Install the profile over the legacy state once, and freeze it.

    Every test in this module needs the same prologue: the close suite's
    fixture, a loadable profile, one Coverage record claiming an era whose
    receipt it cannot name, and an origin receipt re-anchored to those
    edited bytes.  No writer runs here -- the prologue is pure installation,
    so walking it once and copying the tree is byte-identical to building
    it fresh, minus three re-installations.
    """
    global _LEGACY_ROOT
    if _LEGACY_ROOT is None:
        holder = tempfile.TemporaryDirectory(prefix="reviewed-era-template-")
        _TEMPLATE_DIRS.append(holder)
        root = Path(holder.name) / "repo"
        shutil.copytree(test_check_batch_close.FIXTURE, root)
        for name in ("deltas", "receipts", "reports"):
            (root / ".cambium" / name).mkdir(exist_ok=True)
        builder = ReviewedEraActivationTests("runTest")
        builder.root = root
        builder.install_profile_and_tools()
        # The legacy state every corpus that predates K02/01 is in: a record
        # claiming an era whose receipt it cannot name.
        coverage_path = root / check_queue.COVERAGE_PATH
        coverage = kblib.parse_yaml_subset(
            coverage_path.read_text(encoding="utf-8"))
        coverage["pages"][0]["authoring_status"] = "reviewed"
        coverage["pages"][0]["gate_receipts"] = []
        coverage_path.write_text(kblib.canonical_yaml(coverage),
                                 encoding="utf-8")
        builder.reanchor_origin()
        _LEGACY_ROOT = root
    return _LEGACY_ROOT


def load_tests(loader, standard_tests, pattern):
    """Collect the join tests without replaying the close suite.

    ``ReviewedEraActivationTests`` inherits ``CheckBatchCloseTests`` for its
    profile installer and tool runner.  Default discovery also collects the
    imported base class and every inherited ``test_*`` method, so the close
    suite ran twice here in addition to its canonical run in
    ``test_check_batch_close.py``.  Only methods this class declares are the
    join coverage.
    """
    suite = loader.suiteClass()
    names = [
        name for name in loader.getTestCaseNames(ReviewedEraActivationTests)
        if name in ReviewedEraActivationTests.__dict__]
    suite.addTests(ReviewedEraActivationTests(name) for name in names)
    return suite


if __name__ == "__main__":
    unittest.main()
