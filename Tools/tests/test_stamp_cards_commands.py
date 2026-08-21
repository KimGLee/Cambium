"""Card/Read Set command spans must satisfy the invoked tool's own interface.

These cover the deterministic command check added to stamp_cards.py: a code
span whose first token is `python3` is the copy-and-run form, so the named
tool must exist and every argument that tool declares as required must be
supplied. The tool's argparse source is the only authority consulted; no
argument list is restated here.
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
import standards_state  # noqa: E402


DEMO_TOOL = (
    "import argparse\n"
    "\n"
    "\n"
    "def main():\n"
    "    parser = argparse.ArgumentParser()\n"
    "    parser.add_argument('root')\n"
    "    parser.add_argument('--plan', required=True)\n"
    "    parser.add_argument('--receipts', default='x')\n"
    "    parser.add_argument('--json', action='store_true')\n"
)


class ToolArgumentContractTests(unittest.TestCase):
    def test_contract_is_read_from_the_tool_source_without_executing_it(self):
        positionals, required_options, reads_value = (
            stamp_cards.tool_argument_contract(DEMO_TOOL))

        self.assertEqual(positionals, ["root"])
        self.assertEqual(required_options, ["--plan"])
        self.assertEqual(
            {"--plan": True, "--receipts": True, "--json": False},
            reads_value)

    def test_optional_and_defaulted_positionals_are_not_required(self):
        source = (
            "import argparse\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('maybe', nargs='?')\n"
            "parser.add_argument('preset', default='p')\n"
            "parser.add_argument('--flag', action='store_true')\n"
        )

        positionals, required_options, reads_value = (
            stamp_cards.tool_argument_contract(source))

        self.assertEqual(positionals, [])
        self.assertEqual(required_options, [])
        self.assertEqual({"--flag": False}, reads_value)

    def test_real_kernel_tools_declare_the_contract_the_cards_satisfy(self):
        source = (TOOLS_DIR / "record_corpus_acceptance.py").read_text(
            encoding="utf-8"
        )

        positionals, required_options, reads_value = (
            stamp_cards.tool_argument_contract(source))

        self.assertEqual(positionals, ["root"])
        self.assertIn("--plan", required_options)
        self.assertTrue(reads_value["--plan"])
        self.assertFalse(reads_value["--apply"])


class CommandSpanFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Tools").mkdir()
        (self.root / "Tools" / "demo.py").write_text(DEMO_TOOL, encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def scan(self, body):
        return stamp_cards.command_span_failures(
            "kernel/Cards/Demo Card.md", body, self.root, {}
        )

    def test_complete_command_passes(self):
        body = "- [ ] Run `python3 Tools/demo.py . --plan <plan> --json`.\n"

        self.assertEqual(self.scan(body), [])

    def test_a_noncanonical_root_is_normalized_before_containment_check(self):
        (self.root / "alias-segment").mkdir()
        body = "- [ ] Run `python3 Tools/demo.py . --plan <plan> --json`.\n"

        failures = stamp_cards.command_span_failures(
            "kernel/Cards/Demo Card.md",
            body,
            self.root / "alias-segment" / "..",
            {},
        )

        self.assertEqual(failures, [])

    def test_noncanonical_root_still_rejects_symlink_escape(self):
        outside_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_tmp.cleanup)

        outside_tool = Path(outside_tmp.name) / "external.py"
        outside_tool.write_text(DEMO_TOOL, encoding="utf-8")

        link = self.root / "Tools" / "external.py"
        try:
            link.symlink_to(outside_tool)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable: %s" % exc)

        (self.root / "alias-segment").mkdir()
        noncanonical_root = self.root / "alias-segment" / ".."
        body = (
            "- [ ] Run "
            "`python3 Tools/external.py . --plan <plan> --json`.\n"
        )

        failures = stamp_cards.command_span_failures(
            "kernel/Cards/Demo Card.md",
            body,
            noncanonical_root,
            {},
        )

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("escapes the repository root", failures[0])

    def test_missing_root_positional_is_reported_with_a_locatable_line(self):
        body = (
            "## Gate\n"
            "\n"
            "- [ ] Run `python3 Tools/demo.py --plan <plan> --json`.\n"
        )

        failures = self.scan(body)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("kernel/Cards/Demo Card.md:3", failures[0])
        self.assertIn("root", failures[0])

    def test_missing_required_option_is_reported(self):
        body = "- [ ] Run `python3 Tools/demo.py . --json`.\n"

        failures = self.scan(body)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("--plan", failures[0])

    def test_option_value_is_not_counted_as_a_positional(self):
        body = "- [ ] Run `python3 Tools/demo.py --plan <plan>`.\n"

        failures = self.scan(body)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("root", failures[0])

    def test_a_store_true_flag_never_swallows_the_positional(self):
        """`--json .` supplies root; the flag declares that it reads nothing."""
        body = "- [ ] Run `python3 Tools/demo.py --plan <plan> --json .`.\n"

        self.assertEqual(self.scan(body), [])

    def test_the_flag_first_spelling_of_a_real_tool_is_accepted(self):
        """The reviewer's case: this exact command is legal and must pass."""
        shutil.copy(TOOLS_DIR / "stamp_cards.py", self.root / "Tools")
        body = "- [ ] Run `python3 Tools/stamp_cards.py --check .`.\n"

        self.assertEqual(self.scan(body), [])

    def test_a_value_reading_flag_still_consumes_its_value(self):
        body = "- [ ] Run `python3 Tools/demo.py --plan <plan> --receipts r`.\n"

        failures = self.scan(body)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("root", failures[0])

    def test_missing_tool_path_is_reported(self):
        body = "- [ ] Run `python3 Tools/absent.py . --plan <plan>`.\n"

        failures = self.scan(body)

        self.assertEqual(len(failures), 1, failures)
        self.assertIn("does not exist", failures[0])

    def test_prose_tool_reference_is_not_scanned_as_a_command(self):
        body = (
            "- [ ] Consume a current `Tools/demo.py` receipt.\n"
            "- [ ] Close with `demo.py --json`.\n"
        )

        self.assertEqual(self.scan(body), [])

    def test_scan_is_deterministic_for_the_same_bytes(self):
        body = "- [ ] Run `python3 Tools/demo.py --json`.\n"

        self.assertEqual(self.scan(body), self.scan(body))


class StampCardsCommandGateTests(unittest.TestCase):
    """End-to-end: a drifted Card command fails the Card layer, not just a lint."""

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
        return self.run_stamp("--check")

    def run_stamp(self, *arguments):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.root), *arguments],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def install_standards_state(self, version):
        path = self.root / standards_state.STATE_PATH
        path.parent.mkdir(parents=True)
        path.write_text(standards_state.canonical_text({
            "schema_version": 1,
            "state_revision": 1,
            "standards_version": version,
            "status": "approved",
            "effective_date": "2026-08-21",
            "selected_profile_manifest": "profiles/example/profile.md",
            "latest_adoption_receipt": "audit-adopt-current-0001",
            "upstream_source_ref": "https://example.invalid/upstream",
            "upstream_revision_id": "current-revision",
        }), encoding="utf-8")

    def test_current_card_layer_has_no_command_drift(self):
        result = self.run_check()

        self.assertNotIn("[FAIL]", result.stdout, result.stdout + result.stderr)
        self.assertIn("runtime_cards=13", result.stdout)

    def test_explicit_write_can_prepare_candidate_version_before_adoption(self):
        self.install_standards_state("current")
        current = self.run_stamp(
            "--set-version", "current", "--acknowledge-compiled")
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)

        candidate = self.run_stamp(
            "--set-version", "candidate", "--acknowledge-compiled")

        self.assertEqual(candidate.returncode, 0,
                         candidate.stdout + candidate.stderr)
        for card in (self.root / "kernel" / "Cards").glob("*.md"):
            self.assertIn("compiled_from: 'candidate'",
                          card.read_text(encoding="utf-8"))

        active_check = self.run_check()
        self.assertEqual(active_check.returncode, 2,
                         active_check.stdout + active_check.stderr)
        self.assertIn("compiled_from candidate -> current",
                      active_check.stdout)

        candidate_check = self.run_stamp(
            "--check", "--set-version", "candidate")
        self.assertEqual(candidate_check.returncode, 1,
                         candidate_check.stdout + candidate_check.stderr)
        self.assertIn("--check cannot judge candidate", candidate_check.stdout)

    def test_a_flag_before_the_positional_does_not_fail_the_layer(self):
        """Reordering a legal command must not turn into a Card layer failure."""
        card = self.root / "kernel" / "Cards" / "R13 Corpus Planning Card.md"
        text = card.read_text(encoding="utf-8")
        reordered = text.replace(
            "`python3 Tools/check_corpus_plan.py . --json`",
            "`python3 Tools/check_corpus_plan.py --json .`",
        )
        self.assertNotEqual(text, reordered, "R13 Card no longer carries the gate command")
        card.write_text(reordered, encoding="utf-8")

        result = self.run_check()

        self.assertNotIn("[FAIL]", result.stdout, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dropping_a_required_argument_from_a_card_command_fails_closed(self):
        card = self.root / "kernel" / "Cards" / "R13 Corpus Planning Card.md"
        text = card.read_text(encoding="utf-8")
        drifted = text.replace(
            "`python3 Tools/check_corpus_plan.py . --json`",
            "`python3 Tools/check_corpus_plan.py --json`",
        )
        self.assertNotEqual(text, drifted, "R13 Card no longer carries the gate command")
        card.write_text(drifted, encoding="utf-8")

        result = self.run_check()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("R13 Corpus Planning Card.md", result.stdout)
        self.assertIn("root", result.stdout)


if __name__ == "__main__":
    unittest.main()
