"""What the two residual-scan invocations each prove, and what neither does.

`check_batch_close` runs the registered verifier twice: once with
`--positive-controls-only` and once as the registered production command. The
two prove different things, and the guidance that teaches an adopter how to
fill the Registered Scan Registry had drifted into treating them as one. The
claim that spread was that a fabricated matcher — one naming structures no
page carries — is caught by the non-inert positive control. It is not. The
bundled verifier synthesizes its controls from `mandated_headings` and runs
them through the production classifier without reading repository content, so
that invocation passes on an empty repository and would pass on any fabricated
matcher that is merely self-consistent.

The requirement the guidance meant is real but belongs to the other
invocation: the production scan refuses a configuration whose matchers
recognise nothing in the repository. That is what makes a declared structure
class have to be materialized rather than left on paper, and it is why a
corpus starting from zero pages must create the witness in its first batch
rather than at Profile adoption.

This module pins both halves as behavior, so the corrected prose has
counter-evidence standing behind it rather than only a more careful sentence,
and pins that the greenfield branch stays present in the interview that
conducts the fill.

What it cannot do is stop prose from drifting again. No assertion reads a
paragraph and decides it attributes a requirement to the right check. These
tests make a wrong paragraph refutable in one command; they do not make it
impossible.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
VERIFIER = REPOSITORY / "Tools" / "check_residual_content.py"
INTERVIEW = REPOSITORY / "profiles" / "interview.yaml"

ACCEPTED_ROOT = "Notes/Daily Log"

CONFIG = """residual_scan_config_version: 1

allowed_roots:
  - %s

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
""" % ACCEPTED_ROOT

WITNESS = """---
type: daily-log
---

# 2026-01-01

## Daily Log Entry

seed

## Scratch

-

## To Sort

-
"""

ORDINARY_PAGE = """---
type: note
---

# Ordinary

body
"""


def run_scan(root, config, positive_controls_only=False):
    command = [sys.executable, str(VERIFIER), str(root),
               "--scan-id", "semantics-under-test",
               "--config", str(config), "--time-limit", "55"]
    if positive_controls_only:
        command.append("--positive-controls-only")
    return subprocess.run(command, text=True, capture_output=True, check=False)


class ScanRoot:
    """A temporary vault plus the profile-owned config that scans it."""

    def __init__(self, stack):
        self.root = Path(stack.name)
        self.config = self.root / "residual-scan.yaml"
        self.config.write_text(CONFIG, encoding="utf-8")

    def page(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def accepted_root(self):
        (self.root / ACCEPTED_ROOT).mkdir(parents=True, exist_ok=True)


class PositiveControlProvesSelfConsistencyOnly(unittest.TestCase):
    def test_it_passes_on_an_empty_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = ScanRoot(type("S", (), {"name": tmp}))
            result = run_scan(vault.root, vault.config,
                              positive_controls_only=True)
            self.assertEqual(
                0, result.returncode,
                "the positive control synthesizes its inputs from "
                "mandated_headings and never reads repository content, so it "
                "passes with no pages at all. Any guidance claiming it catches "
                "a matcher that matches nothing real is refuted here:\n"
                + result.stdout + result.stderr)
            self.assertIn(
                "scanned 0 file(s)", result.stdout,
                "the control invocation must not have read repository content "
                "at all; if it scanned files, the two invocations no longer "
                "prove different things and this module's premise is wrong")

    def test_it_passes_even_with_no_accepted_root_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = ScanRoot(type("S", (), {"name": tmp}))
            result = run_scan(vault.root, vault.config,
                              positive_controls_only=True)
            self.assertEqual(0, result.returncode, result.stdout)


class ProductionScanProvesTheRepositoryBacksTheConfiguration(unittest.TestCase):
    def test_it_fails_when_the_accepted_root_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = ScanRoot(type("S", (), {"name": tmp}))
            vault.page("note.md", ORDINARY_PAGE)
            result = run_scan(vault.root, vault.config)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("accepted root", result.stdout)

    def test_it_fails_when_no_file_matches_anywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = ScanRoot(type("S", (), {"name": tmp}))
            vault.accepted_root()
            vault.page("note.md", ORDINARY_PAGE)
            result = run_scan(vault.root, vault.config)
            self.assertNotEqual(
                0, result.returncode,
                "an accepted root that exists but holds nothing the matchers "
                "recognise is an inert configuration, and creating the "
                "directory is therefore not enough to close a batch:\n"
                + result.stdout)
            self.assertIn("recognised no Markdown file", result.stdout)

    def test_it_passes_once_the_first_batch_materializes_the_witness(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = ScanRoot(type("S", (), {"name": tmp}))
            vault.page("note.md", ORDINARY_PAGE)
            vault.page("%s/2026-01-01.md" % ACCEPTED_ROOT, WITNESS)
            result = run_scan(vault.root, vault.config)
            self.assertEqual(
                0, result.returncode,
                "one page under the accepted root carrying the declared "
                "structure is the whole of what a corpus starting from zero "
                "owes this scan; if this fails, the greenfield path the "
                "interview teaches has no legal ending:\n"
                + result.stdout + result.stderr)
            self.assertIn("candidates=0", result.stdout)


class TheInterviewTeachesBothBranches(unittest.TestCase):
    """Structural, not editorial: the branch exists, whatever it says."""

    def setUp(self):
        text = INTERVIEW.read_text(encoding="utf-8")
        start = text.index("- id: C1")
        end = text.index("change_cost", start)
        self.step = text[start:end]

    def test_c1_branches_on_whether_the_corpus_has_pages(self):
        for marker in ("Existing corpus:", "Empty corpus:"):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker, self.step,
                    "C1 fills one slot for two situations that differ in kind "
                    "-- observing strings that exist, and declaring strings a "
                    "first batch will create. Collapsing them is what left an "
                    "empty corpus with no honest answer")

    def test_c1_obliges_bounded_founding_to_materialize_the_witness(self):
        self.assertIn(
            "bounded founding MUST materialize the declared class", self.step,
            "the declared class has to reach the repository or the production "
            "scan refuses the close; nothing else in the flow says so")
        self.assertIn(
            "at least one page under the accepted root", self.step,
            "the obligation must stay concrete: one real page under the "
            "accepted root, not a paper declaration")


if __name__ == "__main__":
    unittest.main()
