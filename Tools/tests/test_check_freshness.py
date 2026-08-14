import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]


class FreshnessFutureBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.page = self.root / "Topic.md"
        self.receipts = self.root / "freshness.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def write_page(self, *, last_verified=None, last_reviewed=None,
                   volatility="fast"):
        fields = [
            "---",
            "type: concept",
            "priority: P0",
            "volatility: %s" % volatility,
        ]
        if last_verified is not None:
            fields.append("last_verified: %s" % last_verified)
        if last_reviewed is not None:
            fields.append("last_reviewed: %s" % last_reviewed)
        fields.extend(("---", "# Topic", ""))
        self.page.write_text("\n".join(fields), encoding="utf-8")

    def run_check(self, as_of="2026-08-14"):
        return subprocess.run(
            [
                sys.executable,
                str(TOOLS / "check_freshness.py"),
                str(self.root),
                "--as-of", as_of,
                "--receipts", str(self.receipts),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def receipt_rows(self):
        return [
            json.loads(line)
            for line in self.receipts.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def assert_future_candidate(self, field):
        completed = self.run_check()
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("future_baseline=1", completed.stdout)
        self.assertIn("fresh=0", completed.stdout)
        rows = self.receipt_rows()
        self.assertEqual(1, len(rows), rows)
        self.assertEqual("candidate", rows[0]["result"])
        self.assertEqual("freshness", rows[0]["check"])
        self.assertIn("%s=2099-01-01" % field, rows[0]["details"])
        self.assertIn("as_of=2026-08-14", rows[0]["details"])
        self.assertFalse(any(
            row.get("check") == "freshness-check-summary" and
            row.get("result") == "pass"
            for row in rows
        ))

    def test_future_last_verified_is_a_candidate_not_freshness_evidence(self):
        self.write_page(last_verified="2099-01-01")
        self.assert_future_candidate("last_verified")

    def test_future_last_reviewed_fallback_is_a_candidate(self):
        self.write_page(last_reviewed="2099-01-01")
        self.assert_future_candidate("last_reviewed")

    def test_baseline_equal_to_as_of_remains_valid(self):
        self.write_page(last_verified="2026-08-14")
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("future_baseline=0", completed.stdout)
        self.assertIn("fresh=1", completed.stdout)
        rows = self.receipt_rows()
        self.assertEqual(1, len(rows), rows)
        self.assertEqual("pass", rows[0]["result"])
        self.assertEqual("freshness-check-summary", rows[0]["check"])

    def test_stable_page_does_not_hide_a_future_event_date(self):
        self.write_page(last_verified="2099-01-01", volatility="stable")
        self.assert_future_candidate("last_verified")


if __name__ == "__main__":
    unittest.main()
