"""The leaf module size budget check stamp_cards.py reads out of the kernel.

These cover the deterministic size check: the target, the soft cap, and the KB
unit are read from `Leaf Module Size Budget` in kernel/K00 Standards Control/03
Standards Governance, the approved exceptions and outside-the-cap declarations
are read from kernel/K00 Standards Control/16 Leaf Module Size Register, and
every kernel leaf module is measured against them. Exceeding a registered
growth cap is an error; standing over the soft cap undeclared, and a registered
measured value that no longer matches the file, are candidates. No byte count,
cap, or leaf path is restated here: the shipped assertions read the kernel.
"""

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


BUDGET_TEXT = (
    "## Standards Control\n"
    "\n"
    "- Leaf module target ≤99KB, soft cap 99KB; KB means 7 bytes.\n"
    "\n"
    "## Leaf Module Size Budget\n"
    "\n"
    "- Leaf module target ≤5KB, soft cap 6KB; KB means 1024 bytes.\n"
    "- Each approved exception MUST register the object.\n"
)

REGISTER_TEXT = (
    "## Purpose\n"
    "\n"
    "| [[kernel/K01 Decoy/01 Decoy\\|Decoy]] | 1 bytes | n | 1KB | f |\n"
    "\n"
    "## Leaf Module Size Register\n"
    "\n"
    "| Exception register | Active entries |\n"
    "|---|---|\n"
    "| Leaf module exceptions | 2 active; registered below |\n"
    "| Control-plane exceptions | None; register is open |\n"
    "\n"
    "| Leaf module exception | Measured | Necessity | Growth cap | Follow-up |\n"
    "|---|---|---|---|---|\n"
    "| [[kernel/K01 Demo/01 Big\\|Big]] | 7000 bytes | one answer | 7KB | re-measure |\n"
    "| [[kernel/K01 Demo/02 Bigger\\|Bigger]] (this page) | 9000 bytes | one list | 8.5KB | re-measure |\n"
    "\n"
    "| Outside the cap | Reason |\n"
    "|---|---|\n"
    "| [[kernel/K01 Demo/03 Registry\\|Registry]] | a registry: it owns no rule text |\n"
)


def leaf(root, name, size):
    """Write one kernel leaf module of an exact byte size."""
    path = root / "kernel" / "K01 Demo" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


class BudgetParseTests(unittest.TestCase):
    def test_the_numbers_are_read_only_from_the_named_owner_section(self):
        budget, errors = stamp_cards.parse_size_budget(BUDGET_TEXT)

        self.assertEqual(errors, [])
        self.assertEqual(budget, (5 * 1024, 6 * 1024, 1024))

    def test_a_renamed_budget_section_fails_closed(self):
        text = BUDGET_TEXT.replace(
            "## Leaf Module Size Budget", "## Page Size Policy"
        )

        budget, errors = stamp_cards.parse_size_budget(text)

        self.assertIsNone(budget)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("does not state", errors[0])

    def test_a_missing_kb_unit_fails_closed(self):
        text = BUDGET_TEXT.replace("; KB means 1024 bytes", "")

        budget, errors = stamp_cards.parse_size_budget(text)

        self.assertIsNone(budget)
        self.assertEqual(len(errors), 1, errors)

    def test_a_soft_cap_below_the_target_is_rejected(self):
        text = BUDGET_TEXT.replace("soft cap 6KB", "soft cap 4KB")

        budget, errors = stamp_cards.parse_size_budget(text)

        self.assertIsNone(budget)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("unusable", errors[0])

    def test_the_shipped_owner_states_a_readable_budget(self):
        text = (REPO_ROOT / stamp_cards.SIZE_BUDGET_OWNER_PATH).read_text(
            encoding="utf-8"
        )

        budget, errors = stamp_cards.parse_size_budget(text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(budget)
        target, soft_cap, factor = budget
        self.assertLess(0, target)
        self.assertLessEqual(target, soft_cap)
        self.assertLess(0, factor)


class RegisterParseTests(unittest.TestCase):
    def parse(self, text=REGISTER_TEXT):
        return stamp_cards.parse_size_register(text, 1024)

    def test_rows_outside_the_register_section_are_ignored(self):
        entries, _outside, _declared, errors = self.parse()

        self.assertEqual(errors, [])
        self.assertNotIn("kernel/K01 Decoy/01 Decoy.md", entries)

    def test_the_escaped_alias_pipe_does_not_truncate_the_path(self):
        entries, _outside, _declared, _errors = self.parse()

        self.assertIn("kernel/K01 Demo/01 Big.md", entries)
        self.assertEqual(entries["kernel/K01 Demo/01 Big.md"]["measured"], 7000)
        self.assertEqual(entries["kernel/K01 Demo/01 Big.md"]["cap"], 7 * 1024)

    def test_a_fractional_growth_cap_is_read_in_the_declared_unit(self):
        entries, _outside, _declared, _errors = self.parse()

        self.assertEqual(
            entries["kernel/K01 Demo/02 Bigger.md"]["cap"], int(8.5 * 1024)
        )

    def test_the_two_tables_and_the_active_count_are_separated(self):
        entries, outside, declared, errors = self.parse()

        self.assertEqual(errors, [])
        self.assertEqual(sorted(outside), ["kernel/K01 Demo/03 Registry.md"])
        self.assertEqual(declared, 2)
        self.assertEqual(len(entries), 2)

    def test_a_repeated_registration_is_rejected(self):
        text = REGISTER_TEXT.replace("02 Bigger\\|Bigger", "01 Big\\|Big")

        _entries, _outside, _declared, errors = self.parse(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("more than once", errors[0])

    def test_an_unreadable_measured_value_is_rejected(self):
        text = REGISTER_TEXT.replace("| 7000 bytes |", "| about 7000 |")

        _entries, _outside, _declared, errors = self.parse(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("readable measured value", errors[0])

    def test_a_truncated_exception_row_is_an_error_not_a_skip(self):
        """A short row must not silently drop the page's growth cap."""
        text = REGISTER_TEXT.replace(
            "| [[kernel/K01 Demo/01 Big\\|Big]] | 7000 bytes | one answer "
            "| 7KB | re-measure |",
            "| [[kernel/K01 Demo/01 Big\\|Big]] | 7000 bytes | one answer |",
        )

        entries, outside, _declared, errors = self.parse(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("3 cell(s)", errors[0])
        self.assertIn("kernel/K01 Demo/01 Big.md", errors[0])
        # The page is left with neither disposition, which is exactly why the
        # row may not be skipped.
        self.assertNotIn("kernel/K01 Demo/01 Big.md", entries)
        self.assertNotIn("kernel/K01 Demo/01 Big.md", outside)

    def test_a_row_missing_two_cells_is_not_read_as_outside_the_cap(self):
        """Two survivors of a truncated exception row are not a declaration."""
        text = REGISTER_TEXT.replace(
            "| [[kernel/K01 Demo/01 Big\\|Big]] | 7000 bytes | one answer "
            "| 7KB | re-measure |",
            "| [[kernel/K01 Demo/01 Big\\|Big]] | 7000 bytes | one answer "
            "| 7KB |",
        )

        entries, outside, _declared, errors = self.parse(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("4 cell(s)", errors[0])
        self.assertNotIn("kernel/K01 Demo/01 Big.md", entries)
        self.assertNotIn("kernel/K01 Demo/01 Big.md", outside)

    def test_an_over_wide_row_is_an_error(self):
        text = REGISTER_TEXT.replace(
            "| 7KB | re-measure |", "| 7KB | re-measure | extra |")

        entries, _outside, _declared, errors = self.parse(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("6 cell(s)", errors[0])
        self.assertNotIn("kernel/K01 Demo/01 Big.md", entries)

    def test_the_shipped_register_parses_without_error(self):
        budget, _errors = stamp_cards.parse_size_budget(
            (REPO_ROOT / stamp_cards.SIZE_BUDGET_OWNER_PATH).read_text(
                encoding="utf-8"
            )
        )
        text = (REPO_ROOT / stamp_cards.SIZE_REGISTER_OWNER_PATH).read_text(
            encoding="utf-8"
        )

        entries, outside, declared, errors = stamp_cards.parse_size_register(
            text, budget[2]
        )

        self.assertEqual(errors, [])
        self.assertEqual(declared, len(entries))
        self.assertTrue(outside)


class BudgetFindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "kernel").mkdir()
        self.addCleanup(self.tmp.cleanup)
        self.budget = (5 * 1024, 6 * 1024, 1024)

    def register(self, measured, cap):
        return {"kernel/K01 Demo/01 Big.md": {"measured": measured, "cap": cap}}

    def test_a_leaf_inside_the_soft_cap_needs_no_disposition(self):
        leaf(self.root, "01 Big.md", 100)

        errors, candidates = stamp_cards.size_budget_findings(
            self.root, self.budget, {}, {}, 0
        )

        self.assertEqual(errors, [])
        self.assertEqual(candidates, [])

    def test_a_noncanonical_root_is_normalized_before_relativizing(self):
        leaf(self.root, "01 Big.md", 100)
        (self.root / "alias-segment").mkdir()

        errors, candidates = stamp_cards.size_budget_findings(
            self.root / "alias-segment" / "..", self.budget, {}, {}, 0
        )

        self.assertEqual(errors, [])
        self.assertEqual(candidates, [])

    def test_over_a_registered_growth_cap_is_an_error(self):
        leaf(self.root, "01 Big.md", 7 * 1024 + 1)

        errors, candidates = stamp_cards.size_budget_findings(
            self.root, self.budget, self.register(7 * 1024 + 1, 7 * 1024), {}, 1
        )

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("growth cap", errors[0])
        self.assertIn("01 Big.md", errors[0])
        self.assertEqual(candidates, [])

    def test_over_the_soft_cap_with_no_disposition_is_a_candidate(self):
        leaf(self.root, "01 Big.md", 6 * 1024 + 1)

        errors, candidates = stamp_cards.size_budget_findings(
            self.root, self.budget, {}, {}, 0
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(candidates), 1, candidates)
        self.assertIn("soft cap", candidates[0])

    def test_a_measured_value_that_drifted_is_a_candidate(self):
        leaf(self.root, "01 Big.md", 6500)

        errors, candidates = stamp_cards.size_budget_findings(
            self.root, self.budget, self.register(6400, 7 * 1024), {}, 1
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(candidates), 1, candidates)
        self.assertIn("re-measure", candidates[0])

    def test_an_outside_the_cap_leaf_is_never_measured(self):
        leaf(self.root, "03 Registry.md", 20 * 1024)

        errors, candidates = stamp_cards.size_budget_findings(
            self.root,
            self.budget,
            {},
            {"kernel/K01 Demo/03 Registry.md": "a registry"},
            0,
        )

        self.assertEqual(errors, [])
        self.assertEqual(candidates, [])

    def test_the_two_dispositions_are_exclusive(self):
        leaf(self.root, "01 Big.md", 100)

        errors, _candidates = stamp_cards.size_budget_findings(
            self.root,
            self.budget,
            self.register(100, 7 * 1024),
            {"kernel/K01 Demo/01 Big.md": "a registry"},
            1,
        )

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("exclusive", errors[0])

    def test_registering_a_page_that_is_not_a_leaf_is_an_error(self):
        errors, _candidates = stamp_cards.size_budget_findings(
            self.root, self.budget, self.register(100, 7 * 1024), {}, 1
        )

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("not a kernel leaf module", errors[0])

    def test_a_stale_active_count_is_a_candidate(self):
        leaf(self.root, "01 Big.md", 100)

        errors, candidates = stamp_cards.size_budget_findings(
            self.root, self.budget, self.register(100, 7 * 1024), {}, 4
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(candidates), 1, candidates)
        self.assertIn("active", candidates[0])

    def test_a_missing_active_count_fails_closed(self):
        errors, _candidates = stamp_cards.size_budget_findings(
            self.root, self.budget, {}, {}, None
        )

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("how many", errors[0])

    def test_the_shipped_kernel_has_no_size_error_and_no_size_candidate(self):
        budget, budget_errors = stamp_cards.parse_size_budget(
            (REPO_ROOT / stamp_cards.SIZE_BUDGET_OWNER_PATH).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(budget_errors, [])
        entries, outside, declared, register_errors = (
            stamp_cards.parse_size_register(
                (REPO_ROOT / stamp_cards.SIZE_REGISTER_OWNER_PATH).read_text(
                    encoding="utf-8"
                ),
                budget[2],
            )
        )
        self.assertEqual(register_errors, [])

        errors, candidates = stamp_cards.size_budget_findings(
            REPO_ROOT, budget, entries, outside, declared
        )

        self.assertEqual(errors, [])
        self.assertEqual(candidates, [])


class ShippedBudgetGateTests(unittest.TestCase):
    """End-to-end: a cap breach fails the layer, a soft-cap breach does not."""

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

    def run_check(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.root), "--check"],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def registered_leaf(self):
        budget, _errors = stamp_cards.parse_size_budget(
            (self.root / stamp_cards.SIZE_BUDGET_OWNER_PATH).read_text(
                encoding="utf-8"
            )
        )
        entries, _outside, _declared, _errors = stamp_cards.parse_size_register(
            (self.root / stamp_cards.SIZE_REGISTER_OWNER_PATH).read_text(
                encoding="utf-8"
            ),
            budget[2],
        )
        rel = sorted(entries)[0]
        return budget, rel, entries[rel]

    def test_the_shipped_layer_reports_no_size_finding(self):
        result = self.run_check()

        self.assertNotIn("[FAIL]", result.stdout, result.stdout + result.stderr)
        self.assertNotIn("soft cap", result.stdout)
        self.assertNotIn("growth cap", result.stdout)

    def test_growing_a_leaf_past_its_registered_cap_fails_the_layer(self):
        _budget, rel, entry = self.registered_leaf()
        path = self.root / rel
        path.write_bytes(path.read_bytes() + b"\n" * (entry["cap"] + 1))

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("[FAIL]", result.stdout)
        self.assertIn("growth cap", result.stdout)
        self.assertIn(Path(rel).name, result.stdout)

    def test_growing_an_undeclared_leaf_past_the_soft_cap_is_a_candidate(self):
        budget, _rel, _entry = self.registered_leaf()
        path = self.root / "kernel" / "K01 Scope and Architecture" / "01 Scope Boundaries.md"
        self.assertTrue(path.is_file(), path)
        path.write_bytes(path.read_bytes() + b"\n" * (budget[1] + 1))

        result = self.run_check()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("[FAIL]", result.stdout)
        self.assertIn("[CAND]", result.stdout)
        self.assertIn("soft cap", result.stdout)

    def test_a_missing_size_register_fails_closed(self):
        (self.root / stamp_cards.SIZE_REGISTER_OWNER_PATH).unlink()

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("[FAIL]", result.stdout)

    def truncate_register_row(self, rel, keep):
        """Cut the register row naming ``rel`` down to ``keep`` cells."""
        path = self.root / stamp_cards.SIZE_REGISTER_OWNER_PATH
        lines = path.read_text(encoding="utf-8").splitlines()
        cut = 0
        for index, line in enumerate(lines):
            if not line.startswith("|"):
                continue
            cells = stamp_cards.table_cells(line)
            if cells and stamp_cards.registered_target(cells[0]) == rel and \
                    len(cells) == 5:
                lines[index] = "| %s |" % " | ".join(cells[:keep])
                cut += 1
        self.assertEqual(1, cut, rel)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_a_broken_register_row_cannot_downgrade_a_cap_breach(self):
        """The reviewer's bypass: a short row plus a leaf past its cap."""
        _budget, rel, entry = self.registered_leaf()
        self.truncate_register_row(rel, 3)
        path = self.root / rel
        path.write_bytes(path.read_bytes() + b"\n" * (entry["cap"] + 1))

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("[FAIL]", result.stdout)
        self.assertIn("3 cell(s)", result.stdout)
        self.assertIn(rel, result.stdout)

    def test_a_broken_register_row_alone_fails_the_layer(self):
        """Even with every leaf inside its cap, the register must be readable."""
        _budget, rel, _entry = self.registered_leaf()
        self.truncate_register_row(rel, 3)

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("[FAIL]", result.stdout)
        self.assertIn("outside-the-cap declaration", result.stdout)


if __name__ == "__main__":
    unittest.main()
