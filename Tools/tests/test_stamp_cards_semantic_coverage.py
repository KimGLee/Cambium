"""Runtime Card semantic acknowledgement and Read Set disposition closure."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
SCRIPT = TOOLS_DIR / "stamp_cards.py"

sys.path.insert(0, str(TOOLS_DIR))
import stamp_cards  # noqa: E402


READ_SET_TEXT = """\
---
type: read-set
route_id: R02
---
# Demo

## Purpose

Demo.

## Start

- [[kernel/K01 Demo/01 Direct|Direct]]
- [[kernel/K01 Demo/02 Read Back|Read Back]]
"""


def runtime_record(source_rels, readback_rels):
    return {
        "rel": "kernel/Cards/R02 Demo Card.md",
        "read_set": "kernel/Read Sets/R02 Demo Read Set.md",
        "source_rels": list(source_rels),
        "readback_rels": list(readback_rels),
    }


class ReadbackDispositionTests(unittest.TestCase):
    def setUp(self):
        self.read_sets = [{
            "rel": "kernel/Read Sets/R02 Demo Read Set.md",
            "text": READ_SET_TEXT,
        }]

    def failures(self, source_rels, readback_rels):
        return stamp_cards.card_readback_source_failures(
            self.read_sets, [runtime_record(source_rels, readback_rels)]
        )

    def test_direct_and_readback_exactly_partition_the_boundary(self):
        self.assertEqual(
            self.failures(
                ["kernel/K01 Demo/01 Direct.md"],
                ["kernel/K01 Demo/02 Read Back.md"],
            ),
            [],
        )

    def test_an_unclassified_boundary_leaf_is_rejected(self):
        failures = self.failures(["kernel/K01 Demo/01 Direct.md"], [])

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("without a compiled or read-back disposition", failures[0])

    def test_overlap_is_rejected(self):
        failures = self.failures(
            [
                "kernel/K01 Demo/01 Direct.md",
                "kernel/K01 Demo/02 Read Back.md",
            ],
            ["kernel/K01 Demo/02 Read Back.md"],
        )

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("both compiled and read-back", failures[0])

    def test_a_readback_outside_the_paired_boundary_is_rejected(self):
        failures = self.failures(
            [
                "kernel/K01 Demo/01 Direct.md",
                "kernel/K01 Demo/02 Read Back.md",
            ],
            ["kernel/K01 Demo/03 Extra.md"],
        )

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("names in no loading boundary", failures[0])


class SemanticAcknowledgementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir(parents=True)
        shutil.copytree(REPO_ROOT / "kernel", self.root / "kernel")
        shutil.copytree(
            REPO_ROOT / "Tools",
            self.root / "Tools",
            ignore=shutil.ignore_patterns("tests", "__pycache__"),
        )
        self.addCleanup(self.tmp.cleanup)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def run_stamp(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.root), *args],
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
        )

    def test_source_stamping_cannot_silently_acknowledge_semantic_compilation(self):
        baseline = self.run_stamp("--check")
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)

        source = (
            self.root
            / "kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority.md"
        )
        source.write_text(
            source.read_text(encoding="utf-8")
            + "\nSemantic acknowledgement test input.\n",
            encoding="utf-8",
        )

        observed = self.run_stamp()
        self.assertEqual(observed.returncode, 2, observed.stdout + observed.stderr)
        self.assertIn("semantic_stale=", observed.stdout)

        still_stale = self.run_stamp("--check")
        self.assertEqual(
            still_stale.returncode, 2, still_stale.stdout + still_stale.stderr
        )
        self.assertIn("compiled_source_hash", still_stale.stdout)

        acknowledged = self.run_stamp("--acknowledge-compiled")
        self.assertEqual(
            acknowledged.returncode,
            0,
            acknowledged.stdout + acknowledged.stderr,
        )
        final = self.run_stamp("--check")
        self.assertEqual(final.returncode, 0, final.stdout + final.stderr)

    def test_check_cannot_mutate_semantic_acknowledgement(self):
        result = self.run_stamp("--check", "--acknowledge-compiled")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("mutually exclusive", result.stdout)


if __name__ == "__main__":
    unittest.main()
