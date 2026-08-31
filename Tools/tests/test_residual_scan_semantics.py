"""One local lifecycle seam for the registered residual-scan producer.

Matcher behavior and positive-control acceptance are owned by their pure
tests. Profile configuration meaning, Kernel rules, Receipt type dispatch,
and public CLI transport also remain with their own owners. This module only
proves that the current producer connects those contracts to a real, minimal
corpus and emits current-contract evidence for each outcome.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from Tools.knowledge.content import check_residual_content as residual


CONFIG = """residual_scan_config_version: 1
allowed_roots:
  - Accepted
excluded_roots: []
frontmatter_match:
  field: type
  values:
    - daily-log
heading_match:
  any:
    - Daily Log Entry
  combination:
    - Scratch
    - To Sort
  minimum_distinct: 2
mandated_headings:
  - Daily Log Entry
  - Scratch
  - To Sort
"""

WITNESS = """---
type: daily-log
---
# Daily Log

## Daily Log Entry

seed

## Scratch

-

## To Sort

-
"""

ORDINARY = """---
type: note
---
# Ordinary

body
"""


def run_producer(root, config, *, controls_only=False):
    receipts = []
    arguments = SimpleNamespace(
        vault_root=str(root),
        scan_id="residual-lifecycle-test",
        config=str(config),
        receipts=None,
        time_limit=5.0,
        positive_controls_only=controls_only,
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), \
            contextlib.redirect_stderr(stderr):
        code = residual._run(arguments, receipts)
    return code, receipts, stdout.getvalue(), stderr.getvalue()


class ResidualScanProducerIntegrationTests(unittest.TestCase):
    """Integration from one current Profile configuration checkpoint."""

    def assert_current(self, root, receipts):
        for receipt in receipts:
            self.assertEqual(
                [], residual.current_receipt_errors(receipt, root=root),
                receipt,
            )

    def test_controls_liveness_and_candidate_outcomes_share_one_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "residual-scan.yaml"
            config.write_text(CONFIG, encoding="utf-8")

            code, receipts, stdout, stderr = run_producer(
                root, config, controls_only=True)
            self.assertEqual(0, code, stdout + stderr)
            self.assertEqual(1, len(receipts))
            self.assertEqual(residual.GATE_CHECK, receipts[0]["check"])
            self.assertEqual("passed", receipts[0]["positive_control_result"])
            self.assertEqual(
                "production-classifier",
                receipts[0]["positive_control_mode"],
            )
            self.assertEqual(3, receipts[0]["positive_control_count"])
            self.assertIn("scanned 0 file(s)", stdout)
            self.assert_current(root, receipts)

            ordinary = root / "ordinary.md"
            ordinary.write_text(ORDINARY, encoding="utf-8")
            code, receipts, stdout, stderr = run_producer(root, config)
            self.assertEqual(1, code, stdout + stderr)
            self.assertIn(
                "residual-content-allowed-root",
                {receipt["check"] for receipt in receipts},
            )
            self.assert_current(root, receipts)

            accepted = root / "Accepted"
            accepted.mkdir()
            code, receipts, stdout, stderr = run_producer(root, config)
            self.assertEqual(1, code, stdout + stderr)
            self.assertIn(
                "residual-content-inert-matcher",
                {receipt["check"] for receipt in receipts},
            )
            self.assert_current(root, receipts)

            witness = accepted / "witness.md"
            witness.write_text(WITNESS, encoding="utf-8")
            code, receipts, stdout, stderr = run_producer(root, config)
            self.assertEqual(0, code, stdout + stderr)
            summary = receipts[-1]
            self.assertEqual(residual.GATE_CHECK, summary["check"])
            self.assertIn("Accepted/witness.md", summary["details"])
            self.assert_current(root, receipts)

            leaked = root / "Loose" / "leaked.md"
            leaked.parent.mkdir()
            leaked.write_text(WITNESS, encoding="utf-8")
            code, receipts, stdout, stderr = run_producer(root, config)
            self.assertEqual(2, code, stdout + stderr)
            candidates = [
                receipt for receipt in receipts
                if receipt["result"] == "candidate"
            ]
            self.assertEqual(1, len(candidates))
            self.assertTrue(candidates[0]["target"].startswith(
                "Loose/leaked.md:"))
            self.assert_current(root, receipts)


if __name__ == "__main__":
    unittest.main()
