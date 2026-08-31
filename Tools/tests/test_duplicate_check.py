"""Scope and producer-owner closure for duplicate candidate scanning.

The shared repository-content enumerator owns which Markdown bytes are
managed.  ``duplicate_check`` owns only its candidate algorithm plus explicit
caller scope/exclusion inputs; it does not infer adopter directory policy.
"""

from argparse import Namespace
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest import mock

from Tools.knowledge.content import duplicate_check
from Tools.platform.common import kblib


class DuplicateCandidateUnitTests(unittest.TestCase):
    """In-process candidate and managed-input behavior."""

    def test_managed_content_owner_is_used_without_a_directory_default(self):
        managed = [
            ("/repo/active/A.md", "active/A.md"),
            ("/repo/legacy/B.md", "legacy/B.md"),
        ]
        with mock.patch.object(
                duplicate_check.kblib, "iter_managed_md_files",
                return_value=managed) as enumerate_managed:
            unfiltered = list(duplicate_check.iter_markdown_files(
                Path("/repo"), ()))
            explicit = list(duplicate_check.iter_markdown_files(
                Path("/repo"), ("legacy",)))

        self.assertEqual(
            [Path("/repo/active/A.md"), Path("/repo/legacy/B.md")],
            unfiltered)
        self.assertEqual([Path("/repo/active/A.md")], explicit)
        self.assertEqual(
            [mock.call(Path("/repo")), mock.call(Path("/repo"))],
            enumerate_managed.call_args_list)

    def test_identical_cross_file_paragraphs_are_candidates_not_same_file(self):
        paragraph = "A stable paragraph long enough to enter comparison."
        shingle_set = duplicate_check.shingles(paragraph)
        pairs = duplicate_check.find_duplicates([
            (Path("/repo/A.md"), paragraph, shingle_set),
            (Path("/repo/B.md"), paragraph, shingle_set),
            (Path("/repo/A.md"), paragraph, shingle_set),
        ])

        self.assertEqual(
            [("/repo/A.md", "/repo/B.md")], sorted(pairs))
        self.assertTrue(all(
            score == "jaccard=1.00 containment=1.00"
            for records in pairs.values()
            for score, _left, _right in records))

    def test_reporting_scope_is_resolved_by_the_same_managed_content_owner(self):
        with mock.patch.object(
                duplicate_check.kblib, "iter_managed_md_files",
                return_value=[
                    ("/repo/knowledge/A.md", "knowledge/A.md"),
                ]) as enumerate_managed:
            resolved = duplicate_check._scope_paths(
                Path("/repo"), "knowledge")

        self.assertEqual(frozenset(("/repo/knowledge/A.md",)), resolved)
        enumerate_managed.assert_called_once_with(
            Path("/repo"), "knowledge")


class DuplicateCandidateContractTests(unittest.TestCase):
    """CLI inputs and typed producer identity remain owner-defined."""

    def test_root_is_explicit_and_exclusion_has_no_implicit_policy(self):
        parser = duplicate_check._parser()
        actions = {action.dest: action for action in parser._actions}

        self.assertIsNone(actions["vault"].nargs)
        self.assertTrue(actions["vault"].required)
        self.assertEqual([], actions["exclude"].default)
        self.assertIsNone(actions["scope"].default)
        parsed = parser.parse_args(["/repo"])
        self.assertEqual("/repo", parsed.vault)
        self.assertEqual([], parsed.exclude)

    def test_run_passes_only_explicit_exclusions_to_the_algorithm(self):
        base = dict(
            vault="/repo", scope=None, receipts=None, json=False)
        output = io.StringIO()
        with mock.patch.object(
                duplicate_check, "collect_paragraphs",
                return_value=[]) as collect, redirect_stdout(output):
            self.assertEqual(0, duplicate_check._run(Namespace(
                **base, exclude=[])))
            self.assertEqual(0, duplicate_check._run(Namespace(
                **base, exclude=["archive"])))

        self.assertEqual(
            [
                mock.call(Path("/repo"), []),
                mock.call(Path("/repo"), ["archive"]),
            ],
            collect.call_args_list)

    def test_registered_receipt_validator_owns_exact_producer_identity(self):
        receipt = kblib.make_receipt(
            duplicate_check.TOOL, duplicate_check.TOOL_VERSION,
            "duplicate-check-summary", ". @ /repo", "pass",
            "no candidates", 1,
            receipt_type_id=duplicate_check.RECEIPT_TYPE_ID)
        self.assertEqual([], duplicate_check.current_receipt_errors(receipt))

        receipt["tool_version"] = "0.0.0"
        self.assertTrue(any(
            "tool_version" in error
            for error in duplicate_check.current_receipt_errors(receipt)))


if __name__ == "__main__":
    unittest.main()
