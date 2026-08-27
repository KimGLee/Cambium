import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import upstream_identity  # noqa: E402


class UpstreamIdentityTests(unittest.TestCase):
    def repository(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "upstream"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "contract.txt").write_text("immutable\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "contract.txt"],
                       check=True)
        subprocess.run([
            "git", "-C", str(root), "-c", "user.name=Cambium Test",
            "-c", "user.email=cambium@example.test", "commit", "-qm",
            "fixture",
        ], check=True)
        return root

    def test_ref_resolves_to_one_full_commit_sha(self):
        root = self.repository()
        expected = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, text=True, capture_output=True).stdout.strip()
        self.assertEqual(
            expected, upstream_identity.resolve_revision(root, "HEAD"))
        self.assertTrue(upstream_identity.is_full_commit_sha(expected))

    def test_non_repository_and_non_commit_ref_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(upstream_identity.UpstreamIdentityError):
                upstream_identity.resolve_revision(directory, "HEAD")
        root = self.repository()
        with self.assertRaises(upstream_identity.UpstreamIdentityError):
            upstream_identity.resolve_revision(root, "--help")


if __name__ == "__main__":
    unittest.main()
