import copy
import unittest
from pathlib import Path
import sys


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import Tools.execution.evidence.candidate_lifecycle as candidate_lifecycle


class CandidateLifecycleTests(unittest.TestCase):
    def candidate(self, *, candidate_id="candidate-sha256:" + "a" * 64,
                  member="graph_projection", version="1.10.0",
                  details="duplicate basename"):
        return candidate_lifecycle.with_observation({
            "candidate_id": candidate_id,
            "candidate_type":
                "check_batch_close:duplicate-markdown-basename",
            "member": member,
            "target": "State.md",
            "details": details,
            "producer_tool_version": version,
        })

    def durable(self, candidate):
        row = copy.deepcopy(candidate)
        row["accepted_by"] = "candidate-type"
        row["disposition"] = \
            candidate_lifecycle.ACCEPT_WHILE_UNCHANGED
        return row

    def test_exact_unchanged_durable_observation_is_carried(self):
        candidate = self.candidate()
        errors, carried, fresh = \
            candidate_lifecycle.partition_against_baseline(
                [candidate], [self.durable(candidate)])
        self.assertEqual([], errors)
        self.assertEqual([], fresh)
        self.assertEqual([candidate["candidate_id"]],
                         [row["candidate_id"] for row in carried])

    def test_producer_or_fact_drift_requires_a_fresh_decision(self):
        baseline = self.candidate()
        for current in (
                self.candidate(version="1.11.0"),
                self.candidate(details="three duplicate basenames")):
            with self.subTest(current=current):
                errors, carried, fresh = \
                    candidate_lifecycle.partition_against_baseline(
                        [current], [self.durable(baseline)])
                self.assertEqual([], errors)
                self.assertEqual([], carried)
                self.assertEqual([current], fresh)

    def test_current_only_and_manifest_local_rows_never_carry(self):
        current_only = self.candidate()
        current_only_row = copy.deepcopy(current_only)
        current_only_row["accepted_by"] = "candidate-id"
        current_only_row["disposition"] = candidate_lifecycle.ACCEPT_CURRENT
        manifest = self.candidate(
            candidate_id="candidate-sha256:" + "b" * 64,
            member="manifest_page_contract")
        for candidate, baseline in (
                (current_only, current_only_row),
                (manifest, self.durable(manifest))):
            errors, carried, fresh = \
                candidate_lifecycle.partition_against_baseline(
                    [candidate], [baseline])
            self.assertEqual([], errors)
            self.assertEqual([], carried)
            self.assertEqual([candidate], fresh)

    def test_same_type_new_id_is_not_covered_by_prior_type_decision(self):
        prior = self.candidate()
        current = self.candidate(
            candidate_id="candidate-sha256:" + "c" * 64)
        errors, carried, fresh = \
            candidate_lifecycle.partition_against_baseline(
                [current], [self.durable(prior)])
        self.assertEqual([], errors)
        self.assertEqual([], carried)
        self.assertEqual([current], fresh)

    def test_durable_type_selector_expands_only_the_current_exact_rows(self):
        first = self.candidate()
        second = self.candidate(
            candidate_id="candidate-sha256:" + "d" * 64)
        errors, accepted, unaccepted = \
            candidate_lifecycle.disposition_candidates(
                [first, second], [], [], [], [first["candidate_type"]])
        self.assertEqual([], errors)
        self.assertEqual([], unaccepted)
        self.assertEqual(2, len(accepted))
        self.assertTrue(all(
            row["disposition"] ==
            candidate_lifecycle.ACCEPT_WHILE_UNCHANGED
            for row in accepted))

    def test_continuation_partition_must_close(self):
        attestation = {
            "candidate_protocol": candidate_lifecycle.CANDIDATE_PROTOCOL,
            "candidate_baseline_protocol": candidate_lifecycle.BASELINE_NONE,
            "candidate_baseline_receipt": None,
            "accepted_candidate_count": 1,
            "carried_candidate_count": 1,
            "carried_candidate_set_sha256":
                candidate_lifecycle.candidate_set_sha256(["one"]),
            "fresh_candidate_count": 1,
            "fresh_candidate_set_sha256":
                candidate_lifecycle.candidate_set_sha256(["two"]),
        }
        errors = candidate_lifecycle.continuation_attestation_errors(
            attestation, "fixture")
        self.assertTrue(any("must equal" in error for error in errors), errors)
        self.assertTrue(any("require an exact-carry" in error
                            for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
