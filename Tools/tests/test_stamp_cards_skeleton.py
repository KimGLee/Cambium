"""Card and Read Set section skeletons, and leaf coverage of the boundaries.

These cover the two deterministic checks stamp_cards.py reads out of
`kernel/K00 Standards Control/01 Operating Role and Reading Protocol.md`:
every Runtime Card and kernel Read Set carries the H2 sequence registered for
it there, and every kernel leaf module is named by some Read Set loading
boundary. The kernel leaf is the only authority consulted; no section name or
route shape is restated in this module or in tool code.
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


OWNER_TEXT = (
    "## Card-first Reading Mode\n"
    "\n"
    "| Artifact | H2 sequence | Class |\n"
    "|---|---|---|\n"
    "| `Card default` | `Decoy` | outside the skeleton section |\n"
    "\n"
    "## Card And Read Set Skeleton\n"
    "\n"
    "| Role | Runtime Card | Kernel Read Set |\n"
    "|---|---|---|\n"
    "| When the route applies | `Use When` | `Purpose` |\n"
    "\n"
    "| Artifact | H2 sequence | Class |\n"
    "|---|---|---|\n"
    "| `Card default` | `Use When`, `Before Start`, `Gate` | default |\n"
    "| `Read Set default` | `Purpose`, `Start`, `Gate` | default |\n"
    "| `R11 Card` | `Use When`, `Admission Checklist`, `Gate` | `admission-only` |\n"
    "\n"
    "## Default Read Sets\n"
    "\n"
    "| `R12 Card` | `Nope` | outside the skeleton section |\n"
)


class SkeletonContractParseTests(unittest.TestCase):
    def test_registry_is_read_only_from_the_named_owner_section(self):
        contract, errors = stamp_cards.parse_skeleton_contract(OWNER_TEXT)

        self.assertEqual(errors, [])
        self.assertEqual(
            contract["Card default"], ("Use When", "Before Start", "Gate")
        )
        self.assertEqual(contract["Read Set default"], ("Purpose", "Start", "Gate"))
        self.assertEqual(
            contract["R11 Card"], ("Use When", "Admission Checklist", "Gate")
        )
        self.assertNotIn("R12 Card", contract)

    def test_role_mapping_rows_are_not_mistaken_for_registrations(self):
        contract, _errors = stamp_cards.parse_skeleton_contract(OWNER_TEXT)

        self.assertEqual(sorted(contract), ["Card default", "R11 Card", "Read Set default"])

    def test_a_missing_default_fails_closed(self):
        text = (
            "## Card And Read Set Skeleton\n"
            "\n"
            "| `Card default` | `Use When`, `Gate` |\n"
        )

        _contract, errors = stamp_cards.parse_skeleton_contract(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Read Set default", errors[0])

    def test_a_route_outside_the_closed_set_is_rejected(self):
        text = OWNER_TEXT.replace("| `R11 Card` |", "| `R14 Card` |")

        _contract, errors = stamp_cards.parse_skeleton_contract(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("R14", errors[0])

    def test_a_repeated_registration_is_rejected(self):
        text = OWNER_TEXT.replace(
            "| `R11 Card` | `Use When`, `Admission Checklist`, `Gate` | `admission-only` |",
            "| `R11 Card` | `Use When`, `Gate` | x |\n| `R11 Card` | `Use When`, `Gate` | x |",
        )

        _contract, errors = stamp_cards.parse_skeleton_contract(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("more than once", errors[0])

    def test_an_empty_sequence_cell_is_rejected(self):
        text = OWNER_TEXT.replace(
            "| `R11 Card` | `Use When`, `Admission Checklist`, `Gate` |",
            "| `R11 Card` |  |",
        )

        _contract, errors = stamp_cards.parse_skeleton_contract(text)

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("empty section sequence", errors[0])

    def test_the_shipped_owner_registers_both_defaults(self):
        text = (REPO_ROOT / stamp_cards.SKELETON_OWNER_PATH).read_text(
            encoding="utf-8"
        )

        contract, errors = stamp_cards.parse_skeleton_contract(text)

        self.assertEqual(errors, [])
        self.assertIn("Card default", contract)
        self.assertIn("Read Set default", contract)


class SkeletonComparisonTests(unittest.TestCase):
    def setUp(self):
        self.contract, _errors = stamp_cards.parse_skeleton_contract(OWNER_TEXT)

    def body(self, *sections):
        return "".join("## %s\n\ntext\n\n" % name for name in sections)

    def test_a_default_shaped_card_passes(self):
        failure = stamp_cards.skeleton_failure(
            "Card",
            "R03",
            "kernel/Cards/R03 Demo Card.md",
            self.body("Use When", "Before Start", "Gate"),
            self.contract,
        )

        self.assertIsNone(failure)

    def test_a_renamed_section_is_reported_with_both_sequences(self):
        failure = stamp_cards.skeleton_failure(
            "Card",
            "R03",
            "kernel/Cards/R03 Demo Card.md",
            self.body("Use When", "Preflight", "Gate"),
            self.contract,
        )

        self.assertIsNotNone(failure)
        self.assertIn("kernel/Cards/R03 Demo Card.md", failure)
        self.assertIn("Preflight", failure)
        self.assertIn("Before Start", failure)

    def test_a_registered_variant_replaces_the_default_for_that_route(self):
        variant = self.body("Use When", "Admission Checklist", "Gate")

        self.assertIsNone(
            stamp_cards.skeleton_failure(
                "Card", "R11", "kernel/Cards/R11 Demo Card.md", variant, self.contract
            )
        )
        self.assertIsNotNone(
            stamp_cards.skeleton_failure(
                "Card", "R03", "kernel/Cards/R03 Demo Card.md", variant, self.contract
            )
        )

    def test_order_is_part_of_the_registered_sequence(self):
        failure = stamp_cards.skeleton_failure(
            "Card",
            "R03",
            "kernel/Cards/R03 Demo Card.md",
            self.body("Before Start", "Use When", "Gate"),
            self.contract,
        )

        self.assertIsNotNone(failure)

    def test_an_extra_section_is_reported(self):
        failure = stamp_cards.skeleton_failure(
            "Read Set",
            "R03",
            "kernel/Read Sets/R03 Demo Read Set.md",
            self.body("Purpose", "Start", "Gate", "Appendix"),
            self.contract,
        )

        self.assertIsNotNone(failure)
        self.assertIn("Appendix", failure)

    def test_comparison_is_deterministic_for_the_same_bytes(self):
        body = self.body("Use When", "Preflight", "Gate")
        args = ("Card", "R03", "kernel/Cards/R03 Demo Card.md", body, self.contract)

        self.assertEqual(
            stamp_cards.skeleton_failure(*args), stamp_cards.skeleton_failure(*args)
        )


class LeafCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        family = self.root / "kernel" / "K02 Demo Family"
        family.mkdir(parents=True)
        (family / "01 Covered Leaf.md").write_text("x", encoding="utf-8")
        (family / "02 Other Leaf.md").write_text("x", encoding="utf-8")
        (self.root / "kernel" / "K02 Demo Family Standard.md").write_text(
            "moc", encoding="utf-8"
        )
        self.addCleanup(self.tmp.cleanup)

    def records(self, text):
        return [{"rel": "kernel/Read Sets/R07 Demo Read Set.md", "text": text}]

    def test_a_leaf_named_in_a_boundary_is_covered(self):
        text = (
            "## Start\n\n"
            "- [[kernel/K02 Demo Family/01 Covered Leaf|Covered Leaf]]\n\n"
            "## Triggered\n\n"
            "- Condition: read [[kernel/K02 Demo Family/02 Other Leaf|Other Leaf]].\n"
        )

        self.assertEqual(
            stamp_cards.leaf_coverage_failures(self.root, self.records(text)), []
        )

    def test_a_leaf_no_boundary_names_is_reported_by_path(self):
        text = "## Start\n\n- [[kernel/K02 Demo Family/01 Covered Leaf|Covered Leaf]]\n"

        failures = stamp_cards.leaf_coverage_failures(self.root, self.records(text))

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("kernel/K02 Demo Family/02 Other Leaf.md", failures[0])

    def test_purpose_and_related_are_not_loading_boundaries(self):
        text = (
            "## Purpose\n\n"
            "- [[kernel/K02 Demo Family/01 Covered Leaf|Covered Leaf]]\n\n"
            "## Start\n\n"
            "- [[kernel/K02 Demo Family/02 Other Leaf|Other Leaf]]\n\n"
            "## Related\n\n"
            "- [[kernel/K02 Demo Family/01 Covered Leaf|Covered Leaf]]\n"
        )

        failures = stamp_cards.leaf_coverage_failures(self.root, self.records(text))

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("01 Covered Leaf.md", failures[0])

    def test_a_heading_link_still_names_the_leaf(self):
        text = (
            "## Start\n\n"
            "- [[kernel/K02 Demo Family/01 Covered Leaf#Some Heading|Covered]]\n"
            "- [[kernel/K02 Demo Family/02 Other Leaf|Other Leaf]]\n"
        )

        self.assertEqual(
            stamp_cards.leaf_coverage_failures(self.root, self.records(text)), []
        )

    def test_module_mocs_are_not_leaf_modules(self):
        text = (
            "## Start\n\n"
            "- [[kernel/K02 Demo Family/01 Covered Leaf|Covered Leaf]]\n"
            "- [[kernel/K02 Demo Family/02 Other Leaf|Other Leaf]]\n"
        )

        self.assertEqual(
            stamp_cards.leaf_coverage_failures(self.root, self.records(text)), []
        )


class ShippedLayerGateTests(unittest.TestCase):
    """End-to-end: a drifted section name or an orphaned leaf fails the layer."""

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

    def test_the_shipped_layer_has_no_skeleton_or_coverage_failure(self):
        result = self.run_check()

        self.assertNotIn("[FAIL]", result.stdout, result.stdout + result.stderr)
        self.assertIn("runtime_cards=13", result.stdout)

    def test_an_unregistered_card_section_name_fails_closed(self):
        card = self.root / "kernel" / "Cards" / "R03 Module Build Card.md"
        text = card.read_text(encoding="utf-8")
        drifted = text.replace("\n## Before Start\n", "\n## Preflight\n")
        self.assertNotEqual(text, drifted, "R03 Card no longer has a Before Start")
        card.write_text(drifted, encoding="utf-8")

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("R03 Module Build Card.md", result.stdout)
        self.assertIn("Preflight", result.stdout)

    def test_an_unregistered_read_set_section_name_fails_closed(self):
        read_set = self.root / "kernel" / "Read Sets" / "R03 Module Build Read Set.md"
        text = read_set.read_text(encoding="utf-8")
        drifted = text.replace("\n## Triggered\n", "\n## Conditional\n")
        self.assertNotEqual(text, drifted, "R03 Read Set no longer has a Triggered")
        read_set.write_text(drifted, encoding="utf-8")

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Conditional", result.stdout)

    def test_a_leaf_dropped_from_every_boundary_fails_closed(self):
        read_set = self.root / "kernel" / "Read Sets" / "R07 Long-running Execution Read Set.md"
        text = read_set.read_text(encoding="utf-8")
        kept = [
            line for line in text.splitlines(keepends=True)
            if "16 Resume Next Action Vocabulary" not in line
        ]
        self.assertNotEqual(len(kept), len(text.splitlines()))
        read_set.write_text("".join(kept), encoding="utf-8")

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("16 Resume Next Action Vocabulary.md", result.stdout)
        self.assertIn("named by no Read Set loading boundary", result.stdout)

    def test_an_unreadable_skeleton_owner_fails_closed(self):
        owner = self.root / stamp_cards.SKELETON_OWNER_PATH
        text = owner.read_text(encoding="utf-8")
        owner.write_text(
            text.replace("## Card And Read Set Skeleton", "## Section Shapes"),
            encoding="utf-8",
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("does not register", result.stdout)


if __name__ == "__main__":
    unittest.main()
