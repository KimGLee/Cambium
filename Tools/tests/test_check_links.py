from contextlib import redirect_stderr, redirect_stdout
import io
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from Tools.knowledge.content import check_links


class ActiveResolutionIndexUnitTests(unittest.TestCase):
    """The active index alone owns basename and missing-path fallback."""

    def test_active_index_resolves_bare_and_missing_explicit_paths(self):
        active_path = Path("/repo/active/Target.md")
        excluded_path = Path("/repo/history/Target.md")
        by_path, by_base = check_links.build_index([
            (active_path, "active/Target.md"),
        ])
        excluded_by_path, excluded_by_base = check_links.build_index([
            (excluded_path, "history/Target.md"),
        ])

        self.assertEqual({"active/Target": active_path}, by_path)
        self.assertEqual(["active/Target"], by_base["Target"])
        self.assertEqual(
            {"history/Target": excluded_path}, excluded_by_path)
        self.assertEqual(["history/Target"], excluded_by_base["Target"])

        for target in ("Target", "other/Target"):
            with self.subTest(target=target):
                self.assertEqual(
                    ("resolved", "active/Target"),
                    check_links.resolve(target, by_path, by_base),
                )


class ExcludedHistoryResolutionIntegrationTests(unittest.TestCase):
    """One in-process CLI seam for the current excluded-content policy."""

    def test_exact_excluded_history_path_wins_before_active_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in {
                "source.md": "[[history/Target#Historical Heading]]\n",
                "active/Target.md": "# Active Heading\n",
                "history/Target.md": "# Historical Heading\n",
            }.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(
                    sys, "argv",
                    ["check_links.py", str(root), "--exclude", "history"]), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                code = check_links.main()

        self.assertEqual(code, 0, stdout.getvalue() + stderr.getvalue())
        self.assertIn("bad_heading=0", stdout.getvalue())
        self.assertIn("excluded_target(resolved)=1", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
