"""Current quota-exception producer/consumer ownership contracts.

The registry and amendment writer own exception shape and mutation. Batch
close owns current selection and exact disposition. Runtime replay owns the
sealed decision contract. This suite tests only the relations unique to that
chain; generic amendment, batch-close, and full task lifecycles have their own
primary tests.
"""

import copy
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import Tools.execution.audit.check_batch_close as check_batch_close
from Tools.execution.task_runtime.queue_runtime import policy_exceptions
import Tools.governance.control.contract_exception_policy as exception_policy
import Tools.knowledge.metadata.check_vocab as check_vocab
from Tools.tests.fixtures.contract.priority_quota_objects import (
    CONFIGURED_PRIORITY_QUOTA_RUBRIC,
)


POLICY_FINGERPRINT = "sha256:" + "a" * 64
SNAPSHOT = "sha256:" + "b" * 64


def live_exception(*, decision_id="PE-1", policy_id="priority_quota.P0",
                   fingerprint=POLICY_FINGERPRINT, limit=60,
                   scope_kind="task", scope_ref="TASK-1"):
    return {
        "decision_id": decision_id,
        "policy_id": policy_id,
        "baseline_policy_fingerprint": fingerprint,
        "limit": limit,
        "scope_kind": scope_kind,
        "scope_ref": scope_ref,
        "rationale": "bounded current-contract exception",
        "approval_reference": "approval-1",
    }


def quota_candidate(*, pages=None, total=None, quota_class="P0", quota=20.0):
    candidate = {
        "candidate_id": "candidate-sha256:" + "0" * 64,
        "candidate_type": "check_vocab:priority-quota-%s" % quota_class,
        "member": "controlled_vocabulary",
        "target": "vault",
        "details": "measured priority quota excess",
    }
    if pages is not None and total is not None:
        candidate["priority_share"] = {
            "pages": pages,
            "total": total,
            "share": round(pages * 100.0 / total, 4),
            "quota": quota,
        }
    return candidate


class QuotaExceptionSelectionContractTests(unittest.TestCase):

    def test_only_current_scope_and_policy_bindings_are_selected(self):
        _policy, fingerprint, errors = \
            exception_policy.effective_priority_policy(
                CONFIGURED_PRIORITY_QUOTA_RUBRIC)
        self.assertEqual([], errors)
        current = live_exception(fingerprint=fingerprint)
        stale = live_exception(
            decision_id="PE-stale", fingerprint="sha256:" + "c" * 64)
        foreign = live_exception(
            decision_id="PE-foreign", policy_id="priority_quota.P1",
            fingerprint=fingerprint, scope_ref="TASK-OTHER")
        snapshot = live_exception(
            decision_id="PE-snapshot", policy_id="priority_quota.P1",
            fingerprint=fingerprint, scope_kind="repository-snapshot",
            scope_ref=SNAPSHOT)
        runtime = {
            "queue": {"task_id": "TASK-1"},
            "progress": {"contract": {
                "policy_exceptions": [current, stale, foreign, snapshot],
            }},
        }

        selected = check_batch_close._quota_exceptions(runtime, fingerprint)

        self.assertEqual([current], selected["P0"])
        self.assertEqual([snapshot], selected["P1"])

class QuotaDispositionContractTests(unittest.TestCase):

    def test_structured_share_decision_matrix_and_sealed_output(self):
        grant = live_exception(limit=24)
        grants = {"P0": [grant]}

        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [quota_candidate()], grants, SNAPSHOT, POLICY_FINGERPRINT)
        self.assertEqual([], accepted)
        self.assertIn("no structured share", errors[0])

        measured = quota_candidate(pages=1, total=4)
        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [measured], grants, SNAPSHOT, POLICY_FINGERPRINT)
        self.assertEqual([], accepted)
        self.assertIn("no valid contract policy exception", errors[0])

        covering = copy.deepcopy(grant)
        covering["limit"] = 26
        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [measured], {"P0": [covering]}, SNAPSHOT,
            POLICY_FINGERPRINT)
        self.assertEqual([], errors)
        self.assertEqual(1, len(accepted))
        self.assertEqual(
            {
                "decision_id": "PE-1",
                "policy_id": "priority_quota.P0",
                "limit": 26,
                "scope_kind": "task",
                "scope_ref": "TASK-1",
                "policy_fingerprint": POLICY_FINGERPRINT,
                "pages": 1,
                "total": 4,
            },
            accepted[0]["policy_exception"])

        snapshot_grant = live_exception(
            limit=60, scope_kind="repository-snapshot",
            scope_ref="sha256:" + "d" * 64)
        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [quota_candidate(pages=1, total=2)],
            {"P0": [snapshot_grant]}, SNAPSHOT, POLICY_FINGERPRINT)
        self.assertEqual([], accepted)
        self.assertIn("no valid contract policy exception", errors[0])

    def test_current_sealed_decision_replays_and_rejects_tamper(self):
        grant = live_exception(limit=60)
        errors, accepted = check_batch_close._quota_candidate_dispositions(
            [quota_candidate(pages=1, total=2)], {"P0": [grant]},
            SNAPSHOT, POLICY_FINGERPRINT)
        self.assertEqual([], errors)
        sealed = accepted[0]["policy_exception"]
        self.assertEqual(
            [],
            policy_exceptions.sealed_policy_exception_errors(
                sealed, "PE-1", "check_vocab:priority-quota-P0",
                "fixture"))

        cases = (
            (lambda value: value.update(policy_id="priority_quota.P1"),
             "exactly its own class"),
            (lambda value: value.update(policy_fingerprint="garbage"),
             "policy_fingerprint"),
            (lambda value: value.update(pages=str(value["pages"])),
             "must be an integer"),
            (lambda value: value.update(surplus_field=True),
             "unsupported field"),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                tampered = copy.deepcopy(sealed)
                mutate(tampered)
                replay_errors = \
                    policy_exceptions.sealed_policy_exception_errors(
                        tampered, "PE-1",
                        "check_vocab:priority-quota-P0", "fixture")
                self.assertTrue(any(expected in error
                                    for error in replay_errors),
                                replay_errors)


class QuotaDistributionProducerIntegrationTests(unittest.TestCase):

    @staticmethod
    def _scan(quota_p0, quota_p1, policy_fingerprint):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A.md").write_text(
                "---\npriority: P0\n---\n\n# A\n", encoding="utf-8")
            (root / "B.md").write_text(
                "---\npriority: P2\n---\n\n# B\n", encoding="utf-8")
            vocab = root / "fixture-vocab.yaml"
            vocab.write_text(
                "fields:\n"
                "  priority:\n"
                "    owner: fixture\n"
                "    values:\n"
                "      - P0\n"
                "      - P2\n",
                encoding="utf-8")
            args = SimpleNamespace(
                vault_root=str(root), scope=None, vocab=str(vocab),
                exclude=[], quota_p0=quota_p0, quota_p1=quota_p1,
                policy_fingerprint=policy_fingerprint, receipts=None,
                json=False)
            produced = []

            with redirect_stdout(io.StringIO()):
                code = check_vocab._run(args, produced, None)
        return code, produced

    def test_none_policy_has_no_candidate_or_quota_gate_receipt(self):
        code, produced = self._scan(None, None, None)

        self.assertEqual(0, code)
        self.assertFalse(any(
            receipt.get("check", "").startswith("priority-quota")
            for receipt in produced))
        summaries = [
            receipt for receipt in produced
            if receipt.get("check") == check_vocab.GATE_CHECK
        ]
        self.assertTrue(summaries)
        self.assertTrue(all(summary["priority_shares"] == {}
                            for summary in summaries))

    def test_configured_pair_publishes_exact_bound_distribution_evidence(self):
        code, produced = self._scan(20.0, 30.0, POLICY_FINGERPRINT)

        self.assertEqual(2, code)
        distributions = [
            receipt for receipt in produced
            if receipt.get("check") == "priority-quota-distribution"
        ]
        self.assertEqual(1, len(distributions))
        distribution = distributions[0]
        self.assertEqual("pass", distribution["result"])
        self.assertEqual(POLICY_FINGERPRINT,
                         distribution["policy_fingerprint"])
        self.assertEqual(["P0"], distribution["quota_exceeded"])
        self.assertEqual(
            {"pages": 1, "total": 2, "share": 50.0, "quota": 20.0},
            distribution["priority_shares"]["P0"])
        self.assertEqual(
            {"pages": 0, "total": 2, "share": 0.0, "quota": 30.0},
            distribution["priority_shares"]["P1"])
        summaries = [
            receipt for receipt in produced
            if receipt.get("check") == check_vocab.GATE_CHECK
        ]
        self.assertTrue(summaries)
        self.assertTrue(all(summary["priority_shares"]
                            for summary in summaries))


class QuotaCliPairContractTests(unittest.TestCase):

    def test_partial_configured_input_is_rejected_before_scanning(self):
        cases = (
            [".", "--quota-p0", "20"],
            [".", "--quota-p0", "20", "--quota-p1", "30"],
        )
        for argv in cases:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as raised:
                check_vocab.main(argv)
            self.assertEqual(1, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
