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

    def test_a_noncanonical_root_is_normalized_before_relativizing(self):
        (self.root / "alias-segment").mkdir()
        text = (
            "## Start\n\n"
            "- [[kernel/K02 Demo Family/01 Covered Leaf|Covered Leaf]]\n"
            "- [[kernel/K02 Demo Family/02 Other Leaf|Other Leaf]]\n"
        )

        failures = stamp_cards.leaf_coverage_failures(
            self.root / "alias-segment" / "..", self.records(text)
        )

        self.assertEqual(failures, [])

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


class CardRouteLoadTests(unittest.TestCase):
    """A Card names no route its own Read Set's boundaries leave out.

    The rule is the loading-boundary owner's: a Card compiles its route's
    boundaries and owns none of them. These cases fix the two edges that
    matter -- a Card-only route is reported wherever in the Card it appears,
    and a boundary the Card does not repeat is not.
    """

    def records(self, read_set_body, card_body, read_set_extra=()):
        read_sets = [
            {
                "rel": "kernel/Read Sets/R03 Demo Read Set.md",
                "route_id": "R03",
                "text": read_set_body,
            },
            {
                "rel": "kernel/Read Sets/R02 Other Read Set.md",
                "route_id": "R02",
                "text": "## Purpose\n\nother\n",
            },
            {
                "rel": "kernel/Read Sets/R11 Admission Read Set.md",
                "route_id": "R11",
                "text": "## Purpose\n\nadmission\n",
            },
        ]
        read_sets.extend(read_set_extra)
        cards = [
            {
                "rel": "kernel/Cards/R03 Demo Card.md",
                "route_id": "R03",
                "read_set": "kernel/Read Sets/R03 Demo Read Set.md",
                "text": card_body,
            },
            {
                "rel": "kernel/Cards/R02 Other Card.md",
                "route_id": "R02",
                "read_set": "kernel/Read Sets/R02 Other Read Set.md",
                "text": "## Use When\n\nother\n",
            },
            {
                "rel": "kernel/Cards/R11 Admission Card.md",
                "route_id": "R11",
                "read_set": "kernel/Read Sets/R11 Admission Read Set.md",
                "text": "## Use When\n\nadmission\n",
            },
        ]
        return read_sets, cards

    def failures(self, read_set_body, card_body):
        read_sets, cards = self.records(read_set_body, card_body)
        return stamp_cards.card_route_load_failures(read_sets, cards)

    def test_a_route_both_sides_name_is_not_reported(self):
        read_set = (
            "## Triggered\n\n"
            "- Authoring a page: combine "
            "[[kernel/Read Sets/R02 Other Read Set|Other]].\n"
        )
        card = (
            "## Use When\n\n"
            "Load [[kernel/Cards/R02 Other Card|Other]] for pages authored.\n"
        )

        self.assertEqual(self.failures(read_set, card), [])

    def test_a_route_only_the_card_names_is_reported_with_both_paths(self):
        read_set = "## Triggered\n\n- Nothing conditional here.\n"
        card = (
            "## Use When\n\n"
            "Load [[kernel/Cards/R02 Other Card|Other]] for pages authored.\n"
        )

        failures = self.failures(read_set, card)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("kernel/Cards/R03 Demo Card.md", failures[0])
        self.assertIn("R02", failures[0])
        self.assertIn("kernel/Read Sets/R03 Demo Read Set.md", failures[0])

    def test_a_route_named_only_outside_a_boundary_is_still_reported(self):
        read_set = (
            "## Purpose\n\n"
            "Pairs with [[kernel/Read Sets/R02 Other Read Set|Other]].\n\n"
            "## Related\n\n"
            "- [[kernel/Read Sets/R02 Other Read Set|Other]]\n"
        )
        card = "## Use When\n\nLoad [[kernel/Cards/R02 Other Card|Other]].\n"

        failures = self.failures(read_set, card)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("R02", failures[0])

    def test_a_boundary_the_card_does_not_repeat_is_not_reported(self):
        read_set = (
            "## Triggered\n\n"
            "- Large-scale work: pass "
            "[[kernel/Read Sets/R11 Admission Read Set|Admission]].\n"
            "- Authoring: combine "
            "[[kernel/Read Sets/R02 Other Read Set|Other]].\n"
        )
        card = "## Use When\n\nBuild a module.\n"

        self.assertEqual(self.failures(read_set, card), [])

    def test_the_cards_own_route_is_never_reported_against_itself(self):
        read_set = "## Triggered\n\n- Nothing conditional here.\n"
        card = (
            "## Read Back When\n\n"
            "Read [[kernel/Read Sets/R03 Demo Read Set|this route]] for a "
            "dispute.\n"
        )

        self.assertEqual(self.failures(read_set, card), [])

    def test_every_card_section_is_scanned_not_only_the_first(self):
        read_set = "## Triggered\n\n- Nothing conditional here.\n"
        card = (
            "## Use When\n\nBuild a module.\n\n"
            "## Gate\n\n"
            "- [ ] A completion candidate loads "
            "[[kernel/Cards/R11 Admission Card|Admission]].\n"
        )

        failures = self.failures(read_set, card)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("R11", failures[0])

    def test_an_artifact_without_a_route_identity_names_no_route(self):
        read_set = "## Triggered\n\n- Nothing conditional here.\n"
        card = (
            "## Use When\n\n"
            "Select the task Card in [[kernel/Cards/Card Index|Card Index]] "
            "listed in [[kernel/Read Sets/Read Sets Index|Read Sets Index]].\n"
        )

        self.assertEqual(self.failures(read_set, card), [])

    def test_a_heading_link_still_names_the_route(self):
        read_set = "## Triggered\n\n- Nothing conditional here.\n"
        card = (
            "## Use When\n\n"
            "See [[kernel/Cards/R02 Other Card#Use When|Other]].\n"
        )

        failures = self.failures(read_set, card)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("R02", failures[0])

    def test_the_same_records_give_the_same_report(self):
        read_set = "## Triggered\n\n- Nothing conditional here.\n"
        card = (
            "## Use When\n\nLoad [[kernel/Cards/R11 Admission Card|A]].\n\n"
            "## Gate\n\n- [ ] Then [[kernel/Cards/R02 Other Card|O]].\n"
        )

        self.assertEqual(self.failures(read_set, card),
                         self.failures(read_set, card))


class DelegatedLeafReachabilityTests(unittest.TestCase):
    """A delegated rule is loadable on every route that reads its delegator.

    `K12/03 Module and Coverage Review` sends status separation to
    `K11/06 Sequence and Progress Semantics`. A route whose boundary names the
    delegator but not the delegate reaches the delegation and cannot follow
    it, which is what the loading-boundary owner means by one link not being a
    substitute. No tool can tell a delegation from navigation, so the edge is
    pinned here instead.
    """

    DELEGATOR = "kernel/K12 Quality Assurance/03 Module and Coverage Review"
    DELEGATE = "kernel/K11 Expression Layer/06 Sequence and Progress Semantics"

    def boundary_text(self, path):
        section = ""
        kept = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if section and section not in stamp_cards.NON_BOUNDARY_SECTIONS:
                kept.append(line)
        return "\n".join(kept)

    def test_the_delegate_is_in_every_boundary_that_names_the_delegator(self):
        directory = REPO_ROOT / "kernel" / "Read Sets"
        read_sets = sorted(
            path for path in directory.glob("*.md")
            if path.name.split(" ", 1)[0] in stamp_cards.EXPECTED_ROUTE_IDS
        )
        self.assertEqual(
            len(read_sets), len(stamp_cards.EXPECTED_ROUTE_IDS), read_sets)
        naming_delegator = []
        for path in read_sets:
            text = self.boundary_text(path)
            if self.DELEGATOR in text:
                naming_delegator.append(path.name)
                self.assertIn(
                    self.DELEGATE, text,
                    "%s loads %s but no boundary of it can reach %s"
                    % (path.name, self.DELEGATOR, self.DELEGATE))
        self.assertTrue(naming_delegator, "no route loads the delegator")


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

    def test_a_route_dropped_from_the_paired_boundary_fails_closed(self):
        read_set = (
            self.root / "kernel" / "Read Sets" / "R03 Module Build Read Set.md"
        )
        text = read_set.read_text(encoding="utf-8")
        kept = [
            line for line in text.splitlines(keepends=True)
            if "R02 Single Note Authoring Read Set" not in line
        ]
        self.assertNotEqual(len(kept), len(text.splitlines()))
        read_set.write_text("".join(kept), encoding="utf-8")

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("kernel/Cards/R03 Module Build Card.md", result.stdout)
        self.assertIn("tells its reader to load R02", result.stdout)

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
