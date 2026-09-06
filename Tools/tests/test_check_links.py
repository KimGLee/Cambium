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

    def test_input_projection_tracks_deciding_facts_not_unrelated_bodies(self):
        base = {"A.md": "[[B#Heading]]\n[[history/B#Ignored]]\n",
                "active/B.md": "# Heading\nBody\n",
                "history/B.md": "# Anything\n",
                "Other.md": "Unrelated\n"}

        def projection(pages):
            active = [(p, p) for p in pages if not p.startswith("history/")]
            excluded = [(p, p) for p in pages if p.startswith("history/")]
            reads = []

            def read(path):
                reads.append(path)
                return pages[path]

            value = check_links.project_inputs(
                active, [("A.md", "A.md")], excluded,
                scope="A.md", excludes=("history",), read_text=read)
            self.assertEqual(len(reads), len(set(reads)))
            self.assertNotIn("Other.md", reads)
            self.assertNotIn("history/B.md", reads)
            return value

        original = projection(base)
        self.assertEqual(original, projection({
            **base, "active/B.md": "# Heading\nDifferent body\n",
            "history/B.md": "# Changed ignored heading\n",
            "Other.md": "Changed unrelated page\n"}))
        variants = (
            ({**base, "new/B.md": "# Heading\n"}, "ambiguous"),
            ({p: text for p, text in base.items() if p != "active/B.md"},
             "missing"),
            ({**base, "active/B.md": "# Renamed\n"}, "resolved"),
            ({**base, "active/B.md": "---\nlifecycle: retired\n"
              "superseded_by: Other.md\n---\n# Heading\n"}, "resolved"),
        )
        for pages, status in variants:
            with self.subTest(status=status, target=pages.get("active/B.md")):
                changed = projection(pages)
                self.assertNotEqual(original, changed)
                self.assertEqual(status, changed["sources"][0]["links"][0]["status"])

        # Removal of an excluded exact target also matters; its ignored body
        # does not. The normal active basename fallback then applies.
        removed = projection({p: t for p, t in base.items()
                              if p != "history/B.md"})
        self.assertNotEqual(original, removed)
        self.assertEqual("resolved", removed["sources"][0]["links"][1]["status"])


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
