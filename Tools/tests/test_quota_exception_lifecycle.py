"""The positive control this feature shipped without, written before the fix.

Six merge blockers in d738a03 share one property: every one of them lives on
the path that was never executed end to end -- excess found, exception
registered, batch closed through it, receipt replayed, exception revoked,
history still verifiable.  1140 component tests were green around a main path
that fails on first real use.  This module is that path, written to fail on
the current bytes for the blockers' exact reasons, so the rebuild turns it
green by fixing causes rather than symptoms.

Blockers pinned here:
1. The close writes ``accepted_by: policy-exception:<id>`` and check_queue's
   disposition vocabulary rejects it -- the tool refuses its own receipt.
2. ``limit`` is unbounded: 1000 passes the shape check.
3. The share is re-parsed from one-decimal prose, so 15.04% under a limit of
   15 is accepted; authorization must compare pages*100 against limit*total
   as integers.
5a. A plan modified between prepare and commit is committed anyway; the
   runtime then fails on the plan SHA the row sealed.
5c. The amendment commit receipt is replayed without tool/tool_version/
   task_id/actor_role binding, so a stripped receipt still validates.

Blocker 4 (the fingerprint must bind the *effective* policy, kernel defaults
included, not the rubric file alone) is pinned where the resolver lands; its
red form here is the resolver's absence.
"""

import copy
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))

import check_batch_close  # noqa: E402
import check_queue  # noqa: E402
import contract_exception_policy  # noqa: E402
import kblib  # noqa: E402
import runtime_paths  # noqa: E402
from test_check_batch_close import CheckBatchCloseTests  # noqa: E402


def _load_amendment_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_aca_lifecycle", TOOLS / "apply_contract_amendment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply_contract_amendment = _load_amendment_tool()


class QuotaExceptionLifecycleTests(CheckBatchCloseTests):
    """Runs on the full close fixture; the corpus is made quota-exceeding."""

    # Finding 7 (this test's own first discovery): the amendment advances
    # the Queue revision, which strands a merge-ready batch's delta_apply
    # binding, so the writer refuses once B1 is merge-ready.  The fixture
    # therefore installs everything, grants nothing, and each test chooses
    # when in the batch lifecycle to grant.
    def setUp(self):
        self.temporary = __import__("tempfile").TemporaryDirectory()
        import shutil
        from test_check_batch_close import FIXTURE
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        for name in ("deltas", "receipts", "reports"):
            (self.root / ".cambium" / name).mkdir(exist_ok=True)
        self.install_profile_and_tools()
        page = self.root / "Topics/A.md"
        page.write_text("---\npriority: P0\n---\n\n# A\n", encoding="utf-8")
        # B stays P2 so the P0 share is 1/2 = 50%: over the 15% default, and
        # coverable by a bounded limit -- a corpus whose only counted page is
        # P0 sits at 100%, which no valid limit (< 100) may cover.
        other = self.root / "Topics/B.md"
        other.write_text("---\npriority: P2\n---\n\n# B\n",
                         encoding="utf-8")
        # The task stays planned: batch activation owns planned -> active,
        # and a bounded exception is grantable at planning time -- that is
        # exactly when a known migration excess should be declared.

    def activate_task(self):
        progress_path = self.root / check_queue.PROGRESS_PATH
        progress = kblib.parse_yaml_subset(
            progress_path.read_text(encoding="utf-8"))
        if progress.get("task_state") in ("active", "paused"):
            return
        result = self.run_tool(
            "update_task.py", "--transition", "paused",
            "--checkpoint-summary", "lifecycle fixture",
            "--actor-role", "integrator",
            "--expected-progress-sha256",
            kblib.sha256_file(progress_path),
            "--expected-queue-sha256",
            kblib.sha256_file(self.root / check_queue.QUEUE_PATH),
            "--apply")
        self.assertEqual(0, result.returncode, result.stdout)

    def rubric_fingerprint(self):
        # The effective-policy fingerprint: resolved values + protocol, not
        # the rubric file bytes -- a kernel default change moves this even
        # when the rubric does not (blocker 4's fix).
        rubric = self.root / "profiles/test-profile/slots.md"
        _policy, fingerprint, errors = (
            contract_exception_policy.effective_priority_policy(
                rubric.read_text(encoding="utf-8")))
        self.assertEqual([], errors)
        return fingerprint

    def register_exception(self, amendment_id="CA-100", limit=60,
                           contract_version_after="c-exc-1",
                           exceptions=None):
        progress_path = self.root / check_queue.PROGRESS_PATH
        entries = exceptions if exceptions is not None else [{
            "decision_id": "PE-001",
            "policy_id": "priority_quota.P0",
            "baseline_policy_fingerprint": self.rubric_fingerprint(),
            "limit": limit,
            "scope_kind": "task",
            "scope_ref": "fixture-task",
            "rationale": "lifecycle positive control",
            "approval_reference": "operator approval",
        }]
        plan = {
            "schema_version": 1,
            "amendment_id": amendment_id,
            "task_id": "fixture-task",
            "date": "2026-08-13",
            "summary": "lifecycle exception grant",
            "approval_reference": "operator approval",
            "before": {
                "coverage_sha256": kblib.sha256_file(
                    self.root / check_queue.COVERAGE_PATH),
                "queue_sha256": kblib.sha256_file(
                    self.root / check_queue.QUEUE_PATH),
                "progress_sha256": kblib.sha256_file(progress_path),
            },
            "contract_version_after": contract_version_after,
            "policy_exceptions_after": [copy.deepcopy(entry)
                                        for entry in entries],
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

    def close_the_batch(self):
        """Drive B1 merge-ready -> closed through the sanctioned recovery
        command, so the sealed dispositions enter the historical replay path
        (`closed_gate_errors`) instead of stopping at the gate receipt."""
        import shlex
        import subprocess
        resumed = self.run_tool("check_queue.py", "--resume-status")
        command = next(
            (line.split("=", 1)[1]
             for line in resumed.stdout.splitlines()
             if line.strip().startswith(
                 "batch_close_recovery.update_queue_command=")),
            None)
        self.assertIsNotNone(command, resumed.stdout)
        completed = subprocess.run(
            shlex.split(command), cwd=str(TOOLS.parent), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, completed.returncode, completed.stdout)
        queue = kblib.parse_yaml_subset(
            (self.root / check_queue.QUEUE_PATH).read_text(encoding="utf-8"))
        states = {item.get("id"): item.get("state")
                  for item in queue.get("required_queue") or []}
        self.assertEqual("closed", states.get("B1"), states)

    # ---- the lifecycle -------------------------------------------------

    def test_the_whole_lifecycle_closes_and_replays(self):
        """Excess -> grant -> close -> Queue closed -> revoke -> history.

        The terminal states are the point: the batch actually reaches
        `closed`, the grant is then revoked through the same writer, and the
        historical close must STILL replay -- the sealed disposition, not
        the (now gone) contract entry, is what authorizes history.
        """
        code, output = self.register_exception()
        self.assertEqual(0, code, output)
        self.assertEqual([], check_queue.validate_runtime(
            str(self.root))["errors"])
        self.prepare_applied_batch()

        closed = self.batch_close()
        self.assertEqual(0, closed.returncode, closed.stdout)
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"],
            "the close's own receipt must survive the consumer that replays "
            "it; a disposition vocabulary that rejects policy-exception "
            "refuses the tool's own output")
        self.close_the_batch()
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"],
            "the closed batch's sealed dispositions must replay")

        # Revocation: the same transaction with an empty after-image.
        code, output = self.register_exception(
            amendment_id="CA-101", contract_version_after="c-exc-2",
            exceptions=[])
        self.assertEqual(0, code, output)
        contract = kblib.parse_yaml_subset(
            (self.root / check_queue.PROGRESS_PATH).read_text(
                encoding="utf-8"))["contract"]
        self.assertEqual([], contract.get("policy_exceptions"))
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"],
            "history closed under a then-valid exception must survive its "
            "revocation; the disposition sealed the decision facts")

    def test_an_uncovered_excess_refuses_and_a_late_grant_names_why(self):
        """No exception -> close refuses; grant at merge-ready -> finding 7."""
        self.prepare_applied_batch()
        refused = self.batch_close()
        self.assertEqual(1, refused.returncode, refused.stdout)
        self.assertIn("no valid contract policy exception", refused.stdout)

        bypass = self.batch_close(
            "--accept-candidate-type", "check_vocab:priority-quota-P0")
        self.assertEqual(1, bypass.returncode, bypass.stdout)
        self.assertIn("generic disposition", bypass.stdout)

        code, output = self.register_exception()
        self.assertEqual(1, code, output)
        self.assertIn("merge-ready", output)

    def test_a_limit_below_the_actual_share_is_refused(self):
        code, output = self.register_exception(limit=20)
        self.assertEqual(0, code, output)
        self.prepare_applied_batch()
        refused = self.batch_close()
        self.assertEqual(1, refused.returncode, refused.stdout)
        self.assertIn("no valid contract policy exception", refused.stdout)

    # ---- the bounds (blockers 2 and 3) ---------------------------------

    def test_an_unbounded_limit_is_refused_at_the_writer(self):
        code, output = self.register_exception(limit=1000)
        self.assertEqual(
            1, code,
            "limit=1000 is not a corpus share; a bounded exception whose "
            "bound is unchecked is unbounded authorization:\n" + output)

    def test_authorization_compares_integers_not_prose(self):
        """37/246 = 15.04065%; a limit of 15 must NOT cover it."""
        base = {
            "candidate_id": "candidate-sha256:" + "0" * 64,
            "candidate_type": "check_vocab:priority-quota-P0",
            "member": "controlled_vocabulary",
            "target": "vault",
            "details": "P0 share 15.0% (37/246) exceeds the K00/07 Priority "
                       "Quota target <=15%; resolve by demotion",
        }
        exceptions = {"P0": [{
            "decision_id": "PE-R", "policy_id": "priority_quota.P0",
            "limit": 15, "scope_kind": "task", "scope_ref": "fixture-task",
        }]}
        fingerprint = "sha256:" + "e" * 64

        # No structured share: fail closed, never fall back to prose.
        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [dict(base)], exceptions, "sha256:" + "0" * 64, fingerprint)
        self.assertEqual([], accepted)
        self.assertIn("no structured share", errors[0])

        # Structured share present: exact cross-multiplication refuses.
        candidate = dict(base)
        candidate["priority_share"] = {
            "pages": 37, "total": 246, "share": 15.0407, "quota": 15.0}
        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [candidate], exceptions, "sha256:" + "0" * 64, fingerprint)
        self.assertEqual(
            [], accepted,
            "pages*100 (3700) > limit*total (3690): the true share exceeds "
            "the bound and display rounding must not become authorization")
        self.assertTrue(errors)

        # A limit that genuinely covers it seals the decision facts.
        exceptions["P0"][0]["limit"] = 15.1
        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [candidate], exceptions, "sha256:" + "0" * 64, fingerprint)
        self.assertEqual([], errors)
        sealed = accepted[0]["policy_exception"]
        self.assertEqual(
            {"decision_id": "PE-R", "policy_id": "priority_quota.P0",
             "limit": 15.1, "scope_kind": "task", "scope_ref": "fixture-task",
             "policy_fingerprint": fingerprint, "pages": 37, "total": 246},
            sealed)

    def test_the_distribution_receipt_carries_shares_not_an_empty_dict(self):
        """Blocker 6: the pass summary sealed `priority_shares: {}` forever.

        The name was rebound to a fresh dict after the summary captured the
        old one.  Both the summary and the new whole-corpus distribution
        Gate receipt must carry the real measured shares, and the
        distribution receipt must bind the policy fingerprint it was handed
        instead of leaving consumers to re-derive the policy.
        """
        import json
        import subprocess
        fingerprint = self.rubric_fingerprint()
        receipts_path = self.root / ".cambium/receipts/vocab-check.jsonl"
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "check_vocab.py"), str(self.root),
             "--vocab", str(self.root / runtime_paths.VOCAB_ARTIFACT_PATH),
             "--exclude", "Card", "--exclude", "profiles",
             "--quota-p0", "15", "--quota-p1", "35",
             "--policy-fingerprint", fingerprint,
             "--receipts", str(receipts_path)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        self.assertEqual(2, completed.returncode, completed.stdout)
        records = [json.loads(line) for line in
                   receipts_path.read_text(encoding="utf-8").splitlines()]
        distribution = [record for record in records
                        if record.get("check") == "priority-quota-distribution"]
        self.assertEqual(1, len(distribution))
        record = distribution[0]
        self.assertEqual("pass", record["result"])
        self.assertEqual(fingerprint, record["policy_fingerprint"])
        self.assertEqual(["P0"], record["quota_exceeded"])
        share = record["priority_shares"]["P0"]
        self.assertEqual(1, share["pages"])
        self.assertEqual(2, share["total"])
        summaries = [r for r in records
                     if isinstance(r.get("priority_shares"), dict)
                     and r.get("check") != "priority-quota-distribution"]
        for summary in summaries:
            self.assertNotEqual(
                {}, summary["priority_shares"],
                "a summary that seals an empty dict measures nothing")

    # ---- the transaction holes (blockers 5a and 5c) --------------------

    def test_a_plan_modified_between_prepare_and_commit_is_refused(self):
        relative = ".cambium/deltas/contract-amendments/CA-200.yaml"
        progress_path = self.root / check_queue.PROGRESS_PATH
        plan = {
            "schema_version": 1, "amendment_id": "CA-200",
            "task_id": "fixture-task", "date": "2026-08-13",
            "summary": "race", "approval_reference": "operator approval",
            "before": {
                "coverage_sha256": kblib.sha256_file(
                    self.root / check_queue.COVERAGE_PATH),
                "queue_sha256": kblib.sha256_file(
                    self.root / check_queue.QUEUE_PATH),
                "progress_sha256": kblib.sha256_file(progress_path),
            },
            "contract_version_after": "c-race",
            "policy_exceptions_after": [],
        }
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(plan), encoding="utf-8")
        # ``main`` canonicalizes the repository root before calling
        # ``prepare``.  Mirror that boundary here: on macOS TemporaryDirectory
        # may spell the path through /var while managed_repository_path
        # resolves it through /private/var, and mixing those spellings makes
        # os.path.relpath manufacture a forbidden ``..`` plan path.
        prepared = apply_contract_amendment.prepare(
            str(self.root.resolve()), relative)
        # The race: the plan file changes after prepare bound its bytes.
        path.write_text(path.read_text(encoding="utf-8") + "# moved\n",
                        encoding="utf-8")
        with self.assertRaises(apply_contract_amendment.Refusal):
            apply_contract_amendment.commit(
                prepared, str(self.root / apply_contract_amendment.
                              RECEIPT_PATH))
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"],
            "a refused commit must leave the runtime untouched")

    def test_a_tampered_sealed_exception_fails_replay(self):
        """The sealed record replays with close-time severity, fail-closed.

        Each tamper is one the pre-rebuild validator accepted: a P0 candidate
        re-sealed under a P1 grant, a garbage fingerprint, string counts
        (which used to SKIP the arithmetic instead of failing it), an opened
        mapping, and a pre-1.8 producer era claiming a disposition its
        protocol did not have.
        """
        import json
        code, output = self.register_exception()
        self.assertEqual(0, code, output)
        self.prepare_applied_batch()
        closed = self.batch_close()
        self.assertEqual(0, closed.returncode, closed.stdout)
        self.close_the_batch()
        receipt_file = self.root / ".cambium/receipts/batch-close.jsonl"
        pristine = receipt_file.read_text(encoding="utf-8")
        self.assertEqual(
            [], check_queue.validate_runtime(str(self.root))["errors"])

        def tampered_errors(mutate):
            lines = pristine.strip().splitlines()
            records = [json.loads(line) for line in lines]
            hits = 0
            for record in records:
                dispositions = record.get("candidate_dispositions")
                if not isinstance(dispositions, list):
                    continue
                for disposition in dispositions:
                    sealed = disposition.get("policy_exception")
                    if isinstance(sealed, dict):
                        mutate(record, disposition, sealed)
                        hits += 1
            self.assertEqual(1, hits, "fixture seals exactly one exception")
            receipt_file.write_text(
                "\n".join(json.dumps(record, ensure_ascii=False,
                                     sort_keys=True) for record in records)
                + "\n", encoding="utf-8")
            errors = check_queue.validate_runtime(str(self.root))["errors"]
            receipt_file.write_text(pristine, encoding="utf-8")
            self.assertTrue(errors, "the tamper must not replay as valid")
            return "\n".join(errors)

        message = tampered_errors(
            lambda r, d, s: s.update(policy_id="priority_quota.P1"))
        self.assertIn("exactly its own class", message)
        message = tampered_errors(
            lambda r, d, s: s.update(policy_fingerprint="garbage"))
        self.assertIn("policy_fingerprint", message)
        message = tampered_errors(
            lambda r, d, s: s.update(pages=str(s["pages"]),
                                     total=str(s["total"])))
        self.assertIn("must be an integer", message)
        message = tampered_errors(
            lambda r, d, s: s.update(surplus_field=True))
        self.assertIn("unsupported field", message)

        # The era gate reads the close bundle's own producer version, so the
        # forgery re-brands the WHOLE bundle as 1.7 -- a consistent-looking
        # historical bundle that carries a disposition its protocol lacked.
        lines = pristine.strip().splitlines()
        records = [json.loads(line) for line in lines]
        for record in records:
            if record.get("tool") == "check_batch_close":
                record["tool_version"] = "1.7.0"
        receipt_file.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True)
                      for record in records) + "\n", encoding="utf-8")
        errors = check_queue.validate_runtime(str(self.root))["errors"]
        receipt_file.write_text(pristine, encoding="utf-8")
        self.assertIn("predates that protocol", "\n".join(errors))

    def test_a_stripped_amendment_receipt_fails_replay(self):
        code, output = self.register_exception(amendment_id="CA-300",
                                               contract_version_after="c-s1")
        self.assertEqual(0, code, output)
        receipt_file = self.root / apply_contract_amendment.RECEIPT_PATH
        import json
        lines = receipt_file.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[-1])
        del record["tool_version"]
        record["standards_version"] = "9.9.9"
        lines[-1] = json.dumps(record, ensure_ascii=False, sort_keys=True)
        receipt_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        errors = check_queue.validate_runtime(str(self.root))["errors"]
        self.assertTrue(
            errors,
            "an amendment commit receipt with no producer identity and a "
            "fabricated Standards version must not replay as valid evidence")


# The parent's own tests run in their own module; under this class's
# quota-exceeding corpus they would all fail for an unrelated reason.
def _skip(self):
    self.skipTest("parent test; runs in test_check_batch_close")


for _name in [name for name in vars(CheckBatchCloseTests)
              if name.startswith("test_")]:
    setattr(QuotaExceptionLifecycleTests, _name, _skip)

del CheckBatchCloseTests


if __name__ == "__main__":
    unittest.main()
