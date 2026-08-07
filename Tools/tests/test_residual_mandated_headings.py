"""A registered residual scan must recognise the form its profile mandates.

K12/09 item 6 accepts a zero-candidate report as evidence only when the same
configuration "still recognises those structures where the profile declares
they legitimately live". Reading that as "recognises *some* file" is too weak:
a configuration whose matchers carry only bare heading text still fires on a
legacy page under its accepted root, passes the liveness probe, and reports
"clean" over exactly the decorated pages the profile's own structure rules
mandate -- the generic matcher strips Markdown heading syntax only, so
`Deep Dive Follow-up Tree` never fires on `Deep-Dive Follow-up Tree（深挖追问树）`.

`mandated_headings` closes that gap: the profile transcribes the forms its own
rules mandate, and the tool proves the matchers can recognise every one of them
before any scan result counts. The tool reports the disagreement between two
profile-owned declarations and fails closed; which one is right stays the
registering profile's judgment.

Only set/existence/equality/count judgments are made here.
"""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
AGENT_ATLAS = REPOSITORY / "profiles" / "examples" / "agent-atlas"
SCAN_CONFIG = AGENT_ATLAS / "scan-configs" / "interview-residuals.yaml"
EXPRESSION_LAYER = AGENT_ATLAS / "expression-layer.md"

sys.path.insert(0, str(TOOLS))
import kblib  # noqa: E402


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
    - interview-card
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


class MandatedHeadingCoverage(unittest.TestCase):
    """The predicate itself, exercised through `load_config`."""

    def load(self, text):
        with tempfile.TemporaryDirectory() as temporary:
            return MODULE.load_config(write_config(temporary, text))

    def test_a_config_covering_its_mandated_forms_loads(self):
        config, _fingerprint = self.load(render_config(
            any_headings=["Interview Card（面试卡片）"],
            combination=["Question（问题）", "Answer（回答）"],
            mandated=["Interview Card（面试卡片）", "Question（问题）",
                      "Answer（回答）"]))
        self.assertEqual(3, len(config["mandated_headings"]))

    def test_bare_matchers_that_miss_every_mandated_form_are_refused(self):
        """The pre-change failure shape, in one case.

        The matchers recognise the undecorated variants -- enough to fire on a
        legacy page and satisfy the liveness probe -- while being blind to all
        of the decorated forms the profile mandates.
        """
        with self.assertRaises(ValueError) as raised:
            self.load(render_config(
                any_headings=["Interview Card"],
                combination=["Question", "Answer"],
                mandated=["Interview Card（面试卡片）", "Question（问题）",
                          "Answer（回答）"]))
        message = str(raised.exception)
        self.assertIn("does not recognise 3 of the 3 mandated_headings",
                      message)
        self.assertIn("Interview Card（面试卡片）", message)

    def test_a_single_missing_mandated_form_is_refused(self):
        with self.assertRaises(ValueError) as raised:
            self.load(render_config(
                any_headings=["Interview Card（面试卡片）"],
                combination=["Question（问题）", "Answer（回答）"],
                mandated=["Interview Card（面试卡片）", "Question（问题）",
                          "Answer（回答）", "Scope（范围）"]))
        message = str(raised.exception)
        self.assertIn("1 of the 4 mandated_headings", message)
        self.assertIn("Scope（范围）", message)

    def test_the_key_is_required_rather_than_optional(self):
        """An omitted key must not silently restore the weak predicate."""
        text = render_config(
            any_headings=["Interview Card"], combination=["A", "B"],
            mandated=["Interview Card"])
        without = text[:text.index("mandated_headings:")]
        with self.assertRaises(ValueError) as raised:
            self.load(without)
        self.assertIn("missing key(s): mandated_headings", str(raised.exception))

    def test_an_empty_mandated_list_is_refused(self):
        text = render_config(
            any_headings=["Interview Card"], combination=["A", "B"],
            mandated=["Interview Card"])
        with self.assertRaises(ValueError):
            self.load(text.replace(
                "mandated_headings:\n  - Interview Card\n",
                "mandated_headings: []\n"))

    def test_duplicate_mandated_entries_are_refused(self):
        with self.assertRaises(ValueError):
            self.load(render_config(
                any_headings=["Interview Card"], combination=["A", "B"],
                mandated=["Interview Card", "Interview Card"]))

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


class AgentAtlasConfigMatchesItsOwnExpressionLayer(unittest.TestCase):
    """The shipped example is the case this check was written for."""

    @staticmethod
    def mandated_from_expression_layer():
        """The non-indented entries of `Required Card Structure`'s fence."""
        lines = EXPRESSION_LAYER.read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines)
                     if line.strip() == "### Required Card Structure")
        fence = next(index for index in range(start, len(lines))
                     if lines[index].startswith("```"))
        entries = []
        for line in lines[fence + 1:]:
            if line.startswith("```"):
                break
            if line and not line.startswith(" "):
                entries.append(line.strip())
        return entries

    def setUp(self):
        self.config, _fingerprint = MODULE.load_config(str(SCAN_CONFIG))

    def test_the_config_transcribes_every_mandated_section(self):
        declared = set(self.config["mandated_headings"])
        mandated = self.mandated_from_expression_layer()
        self.assertEqual(14, len(mandated),
                         "the Required Card Structure block changed shape; "
                         "re-check the scan configuration against it")
        missing = [entry for entry in mandated if entry not in declared]
        self.assertEqual(
            [], missing,
            "expression-layer.md mandates these sections but the scan "
            "configuration does not list them in mandated_headings, so the "
            "registered scan cannot see a page written the way this profile "
            "requires")

    def test_a_page_in_the_mandated_form_is_a_candidate(self):
        page = "".join("## %s\n\nbody\n\n" % heading
                       for heading in self.mandated_from_expression_layer())
        self.assertTrue(
            MODULE.classify(page, self.config),
            "a page carrying exactly the profile's mandated Interview Card "
            "sections must be recognised")

    def test_the_bare_form_still_matches(self):
        page = ("## Core Knowledge Links\n\nbody\n\n"
                "## Deep Dive Follow-up Tree\n\nbody\n")
        self.assertTrue(
            MODULE.classify(page, self.config),
            "legacy undecorated pages must keep matching; the decorated forms "
            "are added to the matcher lists, not swapped in")

    def test_the_config_is_restricted_yaml(self):
        kblib.parse_yaml_subset(SCAN_CONFIG.read_text(encoding="utf-8"))


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

    def test_the_shipped_config_now_sees_the_mandated_form_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = self.build(temporary)
            # The shipped configuration verbatim: its accepted root is the one
            # this fixture creates and its excluded roots simply do not exist
            # here, which the tool allows.
            completed = self.scan(tree, SCAN_CONFIG)
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
                any_headings=["Interview Card"],
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
