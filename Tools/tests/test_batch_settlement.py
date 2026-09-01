#!/usr/bin/env python3
"""Focused tests for the shared routed-gap settlement protocol."""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import Tools.execution.task_runtime.batch_settlement as batch_settlement
import Tools.execution.planning.coverage_delta as coverage_delta
import Tools.platform.common.kblib as kblib


class BatchSettlementTests(unittest.TestCase):
    def setUp(self):
        self.coverage = {
            "schema_version": 1,
            "updated_at": "2026-08-15T00:00:00Z",
            "pages": [{"path": "A.md"}, {"path": "B.md"}],
            "open_gaps": [{
                "id": "gap-a", "page": "A.md", "type": "review",
                "next_batch": "B1",
            }],
        }
        self.queue = {"required_queue": [
            {"id": "B1", "state": "open"},
            {"id": "B2", "state": "queued"},
            {"id": "B3", "state": "merge-ready"},
        ]}

    def delta(self, *, closures=None, additions=None):
        return {
            "batch": "B1",
            "generated_at": "2026-08-15T01:00:00Z",
            "open_gaps_closed": closures or [],
            "open_gaps_added": additions or [],
        }

    def test_unsettled_gap_is_reported_on_the_prospective_after_image(self):
        delta = self.delta()
        after = coverage_delta.project_open_gaps(self.coverage, delta)
        report = batch_settlement.delta_settlement_report(
            self.coverage, after, delta, self.queue, "B1")
        self.assertEqual(1, report["unsettled_count_after"])
        self.assertIn("routed-gap-unsettled", report["errors"][0])

    def test_closing_every_owned_gap_is_clean(self):
        delta = self.delta(closures=["gap-a"])
        after = coverage_delta.project_open_gaps(self.coverage, delta)
        report = batch_settlement.delta_settlement_report(
            self.coverage, after, delta, self.queue, "B1")
        self.assertEqual([], report["errors"])
        self.assertEqual(0, report["unsettled_count_after"])
        self.assertEqual(1, report["obligation_count_before"])

    def test_delta_may_not_close_another_batchs_gap(self):
        coverage = dict(self.coverage)
        coverage["open_gaps"] = list(self.coverage["open_gaps"]) + [{
            "id": "gap-b", "page": "B.md", "type": "review",
            "next_batch": "B2",
        }]
        delta = self.delta(closures=["gap-a", "gap-b"])
        after = coverage_delta.project_open_gaps(coverage, delta)
        report = batch_settlement.delta_settlement_report(
            coverage, after, delta, self.queue, "B1")
        self.assertTrue(any("gap-close-not-routed-to-batch" in error
                            for error in report["errors"]))

    def test_new_target_must_be_a_later_queued_or_open_batch(self):
        for target, code in (("B1", "gap-target-self"),
                             ("B3", "gap-target-frozen"),
                             ("missing", "gap-target-unknown")):
            with self.subTest(target=target):
                delta = self.delta(
                    closures=["gap-a"],
                    additions=[{
                        "id": "gap-next-%s" % target,
                        "page": "A.md", "type": "review",
                        "next_batch": target,
                    }])
                after = coverage_delta.project_open_gaps(self.coverage, delta)
                report = batch_settlement.delta_settlement_report(
                    self.coverage, after, delta, self.queue, "B1")
                self.assertTrue(any(code in error
                                    for error in report["errors"]))

        good = self.delta(
            closures=["gap-a"],
            additions=[{
                "id": "gap-next", "page": "A.md", "type": "review",
                "next_batch": "B2",
            }])
        after = coverage_delta.project_open_gaps(self.coverage, good)
        self.assertEqual([], batch_settlement.delta_settlement_report(
            self.coverage, after, good, self.queue, "B1")["errors"])

    def test_canonical_json_has_one_stable_spelling(self):
        self.assertEqual(b'{"a":2,"z":1}',
                         kblib.canonical_json_bytes({"z": 1, "a": 2}))

    def test_amendment_may_close_or_reroute_an_existing_gap(self):
        closed = dict(self.coverage, open_gaps=[])
        report = batch_settlement.amendment_gap_reconciliation_report(
            self.coverage, closed, self.queue)
        self.assertEqual([], report["errors"])
        self.assertEqual(1, report["changed_gap_count"])

        rerouted = dict(self.coverage, open_gaps=[dict(
            self.coverage["open_gaps"][0], next_batch="B2")])
        report = batch_settlement.amendment_gap_reconciliation_report(
            self.coverage, rerouted, self.queue)
        self.assertEqual([], report["errors"])
        self.assertEqual(["B1", "B2"], report["changed_batches"])

    def test_amendment_rejects_new_gap_and_nonactionable_target(self):
        added = dict(self.coverage, open_gaps=list(
            self.coverage["open_gaps"]) + [{
                "id": "gap-new", "page": "B.md", "type": "review",
                "next_batch": "B2",
            }])
        self.assertIn(
            "gap-reconciliation-may-not-create",
            "\n".join(batch_settlement.amendment_gap_reconciliation_report(
                self.coverage, added, self.queue)["errors"]))

        frozen = dict(self.coverage, open_gaps=[dict(
            self.coverage["open_gaps"][0], next_batch="B3")])
        self.assertIn(
            "gap-target-not-actionable",
            "\n".join(batch_settlement.amendment_gap_reconciliation_report(
                self.coverage, frozen, self.queue)["errors"]))


if __name__ == "__main__":
    unittest.main()
