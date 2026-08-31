"""Owner tests for residual-scan synthetic heading controls.

``mandated_headings`` is the bundled verifier's Profile-configured positive
control representation. It does not define repository page sections. These
tests therefore cover only the Tool-owned schema and the production-classifier
connection; Kernel prose, Profile meaning, corpus scanning, and CLI transport
remain with their own test owners.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Tools.knowledge.content import check_residual_content as residual


BASE_CONFIG = """residual_scan_config_version: 1
allowed_roots:
  - Accepted
excluded_roots: []
frontmatter_match:
  field: type
  values:
    - glossary-entry
heading_match:
  any:
    - Glossary Entry
  combination:
    - Definition
    - Source
    - Scope
  minimum_distinct: 2
mandated_headings:
  - Glossary Entry
  - Definition
  - Source
"""


def controls(*, any_headings=(), combination=(), mandated=(), minimum=0):
    return {
        "allowed_roots": ("Accepted",),
        "excluded_roots": (),
        "frontmatter_field": "type",
        "frontmatter_values": frozenset(),
        "any_headings": frozenset(any_headings),
        "combination_headings": frozenset(combination),
        "minimum_distinct": minimum,
        "mandated_headings": tuple(mandated),
    }


class ResidualPositiveControlContractTests(unittest.TestCase):
    """Pure acceptance predicate owned by the residual verifier."""

    def test_complete_controls_execute_the_production_classifier_once(self):
        config = controls(
            any_headings=("Glossary Entry（术语条目）",),
            combination=("Definition（定义）", "Source（来源）"),
            mandated=("Glossary Entry（术语条目）", "Definition（定义）",
                      "Source（来源）"),
            minimum=2,
        )

        with mock.patch.object(
                residual, "classify", wraps=residual.classify) as classifier:
            residual.check_mandated_coverage(config)

        self.assertEqual(1, classifier.call_count)
        probe, consumed = classifier.call_args.args
        for heading in config["mandated_headings"]:
            self.assertIn("## %s" % heading, probe)
        self.assertIs(config, consumed)

    def test_unrecognised_or_uncountable_controls_fail_closed(self):
        cases = (
            (
                "unrecognised-decorated-forms",
                controls(
                    any_headings=("Glossary Entry",),
                    combination=("Definition", "Source"),
                    mandated=("Glossary Entry（术语条目）", "Definition（定义）",
                              "Source（来源）"),
                    minimum=2,
                ),
                "does not recognise 3 of the 3 mandated_headings",
            ),
            (
                "registered-but-uncountable",
                controls(
                    combination=("A", "B", "C", "D"),
                    mandated=("A", "B"),
                    minimum=3,
                ),
                "does not classify as a residual-content candidate",
            ),
        )
        for name, config, message in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, message):
                    residual.check_mandated_coverage(config)


class ResidualControlSchemaContractTests(unittest.TestCase):
    """Restricted-YAML field shape owned by ``load_config``."""

    def test_mandated_heading_field_is_required_nonempty_and_unique(self):
        variants = (
            (
                "missing",
                BASE_CONFIG[:BASE_CONFIG.index("mandated_headings:")],
                "missing key.*mandated_headings",
            ),
            (
                "empty",
                BASE_CONFIG.replace(
                    "mandated_headings:\n"
                    "  - Glossary Entry\n"
                    "  - Definition\n"
                    "  - Source\n",
                    "mandated_headings: []\n"),
                "must contain at least one entry",
            ),
            (
                "duplicate",
                BASE_CONFIG.replace(
                    "mandated_headings:\n"
                    "  - Glossary Entry\n"
                    "  - Definition\n"
                    "  - Source\n",
                    "mandated_headings:\n"
                    "  - Glossary Entry\n"
                    "  - Definition\n"
                    "  - Source\n"
                    "  - Source\n"),
                "contains a duplicate",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "residual-scan.yaml"
            for name, document, message in variants:
                with self.subTest(case=name):
                    path.write_text(document, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        residual.load_config(path)


if __name__ == "__main__":
    unittest.main()
