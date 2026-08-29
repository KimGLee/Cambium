"""Behavior and ownership checks for the bundled residual-scan controls."""

import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
KERNEL = REPOSITORY / "kernel"
OWNER = KERNEL / "K12 Quality Assurance" / "09 Batch-close Closed List.md"
OWNER_RELATIVE = "kernel/K12 Quality Assurance/09 Batch-close Closed List.md"
OWNER_ANCHOR = "batch-close-closed-list"
RULE_ID = "registered-verifier-positive-controls"
RULE_MARKER = "Rule ID: `%s`" % RULE_ID


def squeezed(text):
    """Line wrapping differs between Markdown and a Python docstring."""
    return " ".join(text.split())


def canonical_rule_body():
    """Read the complete rule body from its one owner without copying it."""
    text = OWNER.read_text(encoding="utf-8")
    if text.count(RULE_MARKER) != 1:
        raise AssertionError("the Kernel owner must carry exactly one rule ID")
    tail = text.split(RULE_MARKER, 1)[1].lstrip()
    body = tail.split("\n\n", 1)[0].strip()
    if not body or "MUST" not in body:
        raise AssertionError("the rule ID must be followed by its rule body")
    return squeezed(body)


def active_distribution_text_paths():
    """Return text candidates in Git, with an export-safe fallback."""
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=REPOSITORY)
    except (OSError, subprocess.CalledProcessError):
        excluded = {".cambium", ".git", "__pycache__", "docs"}
        return sorted(
            path for path in REPOSITORY.rglob("*")
            if path.is_file() and not excluded.intersection(
                path.relative_to(REPOSITORY).parts))
    return [
        REPOSITORY / raw.decode("utf-8")
        for raw in output.split(b"\0") if raw
    ]

def load_module():
    specification = importlib.util.spec_from_file_location(
        "_residual_under_test", TOOLS / "check_residual_content.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


MODULE = load_module()

BASE_CONFIG = """residual_scan_config_version: 1
allowed_roots:
  - Accepted
excluded_roots: []
frontmatter_match:
  field: type
  values:
    - glossary-entry
heading_match:
%(any)s%(combination)s  minimum_distinct: %(minimum)d
%(mandated)s"""


def render_config(any_headings, combination, mandated, minimum=2):
    def block(key, values, indent="  "):
        if not values:
            return "%s%s: []\n" % (indent, key)
        return "%s%s:\n%s" % (indent, key, "".join(
            "%s  - %s\n" % (indent, value) for value in values))
    return BASE_CONFIG % {
        "any": block("any", any_headings),
        "combination": block("combination", combination),
        "minimum": minimum,
        "mandated": block("mandated_headings", mandated, indent=""),
    }


def write_config(directory, text):
    path = Path(directory) / "residual.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


class ThePositiveControlContractHasOneKernelOwner(unittest.TestCase):
    """No judgment rule may live only in code, and each rule has one owner.

    The Kernel owns the cross-verifier evidence rule without imposing one
    implementation's field layout. These assertions fail if the owner is
    dropped, duplicated, or coupled to ``mandated_headings``.
    """

    def test_the_complete_rule_body_has_one_active_distribution_owner(self):
        rule_body = canonical_rule_body()
        owners = []
        for path in active_distribution_text_paths():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            count = squeezed(text).count(rule_body)
            owners.extend([path] * count)
        self.assertEqual(
            [OWNER], owners,
            "the complete rule body must occur only in its Kernel owner")

    def test_kernel_does_not_require_the_bundled_tools_field(self):
        self.assertNotIn(
            "mandated_headings", OWNER.read_text(encoding="utf-8"),
            "mandated_headings is this bundled verifier's configuration, not "
            "a field every registered verifier must implement")

    def test_the_tool_binds_the_stable_rule_id_and_owner(self):
        self.assertEqual(RULE_ID, MODULE.POSITIVE_CONTROL_RULE_ID)
        self.assertEqual(
            OWNER_RELATIVE + "#" + OWNER_ANCHOR,
            MODULE.POSITIVE_CONTROL_RULE_OWNER)
        self.assertTrue((REPOSITORY / OWNER_RELATIVE).is_file())
        self.assertIn(
            "## Batch-close Closed List",
            OWNER.read_text(encoding="utf-8"))


class MandatedHeadingCoverage(unittest.TestCase):
    """The predicate itself, exercised through `load_config`."""

    def load(self, text):
        with tempfile.TemporaryDirectory() as temporary:
            return MODULE.load_config(write_config(temporary, text))

    def test_a_config_covering_its_mandated_forms_loads(self):
        config, _fingerprint = self.load(render_config(
            any_headings=["Glossary Entry（术语条目）"],
            combination=["Definition（定义）", "Source（来源）"],
            mandated=["Glossary Entry（术语条目）", "Definition（定义）",
                      "Source（来源）"]))
        self.assertEqual(3, len(config["mandated_headings"]))

    def test_positive_controls_execute_the_production_classifier(self):
        with mock.patch.object(
                MODULE, "classify", wraps=MODULE.classify) as classifier:
            self.load(render_config(
                any_headings=["Glossary Entry（术语条目）"],
                combination=["Definition（定义）", "Source（来源）"],
                mandated=["Glossary Entry（术语条目）", "Definition（定义）",
                          "Source（来源）"]))
        self.assertEqual(1, classifier.call_count)

    def test_bare_matchers_that_miss_every_mandated_form_are_refused(self):
        """The pre-change failure shape, in one case.

        The matchers recognise the undecorated variants -- enough to fire on a
        legacy page and satisfy the liveness probe -- while being blind to all
        of the decorated forms the profile mandates.
        """
        with self.assertRaises(ValueError) as raised:
            self.load(render_config(
                any_headings=["Glossary Entry"],
                combination=["Definition", "Source"],
                mandated=["Glossary Entry（术语条目）", "Definition（定义）",
                          "Source（来源）"]))
        message = str(raised.exception)
        self.assertIn("does not recognise 3 of the 3 mandated_headings",
                      message)
        self.assertIn("Glossary Entry（术语条目）", message)

    def test_a_single_missing_mandated_form_is_refused(self):
        with self.assertRaises(ValueError) as raised:
            self.load(render_config(
                any_headings=["Glossary Entry（术语条目）"],
                combination=["Definition（定义）", "Source（来源）"],
                mandated=["Glossary Entry（术语条目）", "Definition（定义）",
                          "Source（来源）", "Scope（范围）"]))
        message = str(raised.exception)
        self.assertIn("1 of the 4 mandated_headings", message)
        self.assertIn("Scope（范围）", message)

    def test_the_key_is_required_rather_than_optional(self):
        """An omitted key must not silently restore the weak predicate."""
        text = render_config(
            any_headings=["Glossary Entry"], combination=["A", "B"],
            mandated=["Glossary Entry"])
        without = text[:text.index("mandated_headings:")]
        with self.assertRaises(ValueError) as raised:
            self.load(without)
        self.assertIn("missing key(s): mandated_headings", str(raised.exception))

    def test_an_empty_mandated_list_is_refused(self):
        text = render_config(
            any_headings=["Glossary Entry"], combination=["A", "B"],
            mandated=["Glossary Entry"])
        with self.assertRaises(ValueError):
            self.load(text.replace(
                "mandated_headings:\n  - Glossary Entry\n",
                "mandated_headings: []\n"))

    def test_duplicate_mandated_entries_are_refused(self):
        with self.assertRaises(ValueError):
            self.load(render_config(
                any_headings=["Glossary Entry"], combination=["A", "B"],
                mandated=["Glossary Entry", "Glossary Entry"]))

    def test_minimum_distinct_above_the_mandated_count_is_refused(self):
        """Registered but uncountable is still blind."""
        with self.assertRaises(ValueError) as raised:
            self.load(render_config(
                any_headings=[], combination=["A", "B", "C", "D"],
                mandated=["A", "B"], minimum=3))
        self.assertIn("does not classify as a residual-content candidate",
                      str(raised.exception))

    def test_a_countable_combination_only_config_loads(self):
        config, _fingerprint = self.load(render_config(
            any_headings=[], combination=["A", "B", "C"],
            mandated=["A", "B", "C"], minimum=3))
        self.assertEqual(3, config["minimum_distinct"])


class EndToEndSilentPass(unittest.TestCase):
    """The reported symptom: a mandated-form page escaping the whole scan."""

    MANDATED = ["Scope（范围）", "Knowledge Prerequisites（知识前置）",
                "Core Knowledge Links（核心知识链接）",
                "30-Second Answer（30 秒回答）", "90-Second Answer（90 秒回答）",
                "Deep-Dive Follow-up Tree（深挖追问树）",
                "Follow-up Answers（追问答案）", "Common Misconceptions（常见误解）",
                "Strong Answer Signals（强回答信号）",
                "Weak Answer Signals（弱回答信号）",
                "Comparison Questions（比较类问题）",
                "Scenario Questions（场景类问题）",
                "Self-test Questions（自测问题）",
                "Related Interview Cards（相关面试卡片）"]
    BARE = ["Core Knowledge Links", "Deep Dive Follow-up Tree",
            "Common Misconceptions", "Comparison Questions"]

    @staticmethod
    def page(headings):
        return "# Card\n\n" + "".join(
            "## %s\n\nbody\n\n" % heading for heading in headings)

    def scan(self, tree, config):
        return subprocess.run(
            [sys.executable, str(TOOLS / "check_residual_content.py"),
             str(tree), "--scan-id", "fixture-residual",
             "--config", str(config), "--time-limit", "55"],
            capture_output=True, text=True, check=False)

    def build(self, temporary):
        """An accepted root that satisfies the old liveness probe on its own."""
        tree = Path(temporary)
        accepted = tree / "Interview Preparation"
        accepted.mkdir()
        (accepted / "witness.md").write_text(self.page(self.BARE),
                                             encoding="utf-8")
        loose = tree / "Loose Notes"
        loose.mkdir()
        (loose / "leaked.md").write_text(self.page(self.MANDATED),
                                         encoding="utf-8")
        return tree

    def test_a_complete_synthetic_config_sees_the_mandated_form_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = self.build(temporary)
            accepted = tree / "Accepted"
            accepted.mkdir()
            (accepted / "witness.md").write_text(
                self.page(self.BARE), encoding="utf-8")
            config = Path(temporary) / "complete.yaml"
            config.write_text(render_config(
                any_headings=self.MANDATED,
                combination=self.BARE,
                mandated=self.MANDATED), encoding="utf-8")
            completed = self.scan(tree, config)
            self.assertEqual(
                2, completed.returncode,
                "a page written in the profile's own mandated form must be "
                "reported as a candidate:\n" + completed.stdout)
            self.assertIn("Loose Notes/leaked.md", completed.stdout)

    def test_a_config_blind_to_the_mandated_form_fails_instead_of_passing(self):
        """Before this check, the same input produced candidates=0, exit 0."""
        with tempfile.TemporaryDirectory() as temporary:
            tree = self.build(temporary)
            config = Path(temporary) / "blind.yaml"
            config.write_text(render_config(
                any_headings=["Glossary Entry"],
                combination=self.BARE,
                mandated=self.MANDATED), encoding="utf-8")
            # The accepted root has to line up with this narrower config.
            (tree / "Accepted").mkdir()
            (tree / "Accepted" / "witness.md").write_text(
                self.page(self.BARE), encoding="utf-8")
            completed = self.scan(tree, config)
            self.assertEqual(
                1, completed.returncode,
                "a configuration blind to every form its profile mandates "
                "produced no reliable evidence and must fail closed:\n"
                + completed.stdout)
            self.assertIn("mandated_headings", completed.stdout)


if __name__ == "__main__":
    unittest.main()
