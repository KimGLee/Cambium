import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "check_links.py"


class CheckLinksExcludedResolutionTests(unittest.TestCase):
    def run_check(self, files, *args):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(root), *args],
                text=True,
                capture_output=True,
                check=False,
            )

    def test_exact_excluded_path_wins_before_active_basename_fallback(self):
        result = self.run_check(
            {
                "source.md": "[[legacy/Target#Legacy Heading]]\n",
                "active/Target.md": "# Active Heading\n",
                "legacy/Target.md": "# Legacy Heading\n",
            },
            "--exclude",
            "legacy",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("bad_heading=0", result.stdout)
        self.assertIn("excluded_target(resolved)=1", result.stdout)

    def test_bare_basename_uses_only_active_disambiguation_index(self):
        result = self.run_check(
            {
                "source.md": "[[Target#Active Heading]]\n",
                "active/Target.md": "# Active Heading\n",
                "legacy/Target.md": "# Legacy Heading\n",
            },
            "--exclude",
            "legacy",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("bad_heading=0", result.stdout)
        self.assertIn("excluded_target(resolved)=0", result.stdout)

    def test_missing_explicit_path_does_not_fall_into_excluded_index(self):
        result = self.run_check(
            {
                "source.md": "[[other/Target#Active Heading]]\n",
                "active/Target.md": "# Active Heading\n",
                "legacy/Target.md": "# Legacy Heading\n",
            },
            "--exclude",
            "legacy",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("bad_heading=0", result.stdout)
        self.assertIn("excluded_target(resolved)=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
