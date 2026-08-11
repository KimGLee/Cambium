from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))

from profile_fixture import install_loadable_profile


class RenderQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root, profile_id="test-profile")

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "render_queue.py"), str(self.root),
             *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def test_render_is_deterministic_and_checkable(self):
        first = self.command()
        self.assertEqual(0, first.returncode, first.stdout)
        report = self.root / ".cambium/reports/required_queue.md"
        first_bytes = report.read_bytes()
        second = self.command()
        self.assertEqual(0, second.returncode, second.stdout)
        self.assertEqual(first_bytes, report.read_bytes())
        checked = self.command("--check")
        self.assertEqual(0, checked.returncode, checked.stdout)
        text = first_bytes.decode("utf-8")
        self.assertIn("Derived report only", text)
        self.assertIn("Objective: Complete fixture Required Queue batches", text)
        self.assertIn("Exclusions: Do not modify profile policy.", text)
        self.assertIn("`B1`", text)
        self.assertIn("Remaining required work units: `2`", text)

    def test_output_cannot_overwrite_authoritative_state(self):
        queue = self.root / ".cambium/state/required_queue.yaml"
        before = queue.read_bytes()
        completed = self.command(
            "--output", ".cambium/state/required_queue.yaml"
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual(before, queue.read_bytes())


if __name__ == "__main__":
    unittest.main()
