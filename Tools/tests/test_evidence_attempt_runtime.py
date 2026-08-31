"""Tests for shared append-only evidence attempt currentness."""

from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import Tools.execution.evidence.evidence_attempt_runtime as attempts  # noqa: E402


class EvidenceAttemptRuntimeTests(unittest.TestCase):

    @staticmethod
    def stable(record):
        if record.get("contract") != "stable":
            raise ValueError("contract drift")

    @staticmethod
    def current(record):
        if record.get("input") != "now":
            raise ValueError("stale input")

    def test_stale_predecessor_does_not_block_current_successor(self):
        old = {"receipt_id": "receipt-old", "contract": "stable",
               "input": "before"}
        new = {"receipt_id": "receipt-new", "contract": "stable",
               "input": "now"}

        selected = attempts.unique_current_attempt(
            [old, new], validate_stable=self.stable,
            validate_current=self.current, label="fixture evidence")

        self.assertIs(new, selected)
        classified = attempts.classify_attempts(
            [old, new], validate_stable=self.stable,
            validate_current=self.current, label="fixture evidence")
        self.assertEqual((old,), classified["stale"])
        self.assertEqual((new,), classified["current"])

    def test_same_current_input_is_idempotently_selected(self):
        current = {"receipt_id": "receipt-current", "contract": "stable",
                   "input": "now"}
        self.assertIs(
            current,
            attempts.unique_current_attempt(
                [current], validate_stable=self.stable,
                validate_current=self.current, label="fixture evidence"))

    def test_multiple_current_attempts_are_ambiguous(self):
        records = [
            {"receipt_id": "receipt-a", "contract": "stable",
             "input": "now"},
            {"receipt_id": "receipt-b", "contract": "stable",
             "input": "now"},
        ]
        with self.assertRaisesRegex(
                attempts.EvidenceAttemptError, "multiple current attempts"):
            attempts.unique_current_attempt(
                records, validate_stable=self.stable,
                validate_current=self.current, label="fixture evidence")

    def test_invalid_stable_history_fails_closed(self):
        invalid = {"receipt_id": "receipt-invalid", "contract": "drifted",
                   "input": "before"}
        with self.assertRaisesRegex(
                attempts.EvidenceAttemptError, "invalid stable attempt"):
            attempts.unique_current_attempt(
                [invalid], validate_stable=self.stable,
                validate_current=self.current, label="fixture evidence")


if __name__ == "__main__":
    unittest.main()
