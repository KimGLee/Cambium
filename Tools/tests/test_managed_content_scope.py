"""Ownership closure for the repository-managed content set.

The platform repository-content enumerator owns the tracked plus visible
untracked boundary and the exported-tree fallback. Knowledge consumers own
only their additional suffix, namespace, or MOC predicates. All owner and
consumer contracts run in-process; the public CLI retains one minimal adapter
seam without rebuilding a repository or starting another Python process.
"""

import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from Tools.knowledge.structure import check_moc
from Tools.knowledge.structure import repository_structure
from Tools.platform.common import kblib


class RepositoryContentFilesContractTests(unittest.TestCase):
    """Contract: kblib alone owns repository-content enumeration."""

    ROOT = "/workspace"

    def git_result(self, *, stdout=b"", stderr=b"", returncode=0):
        return mock.Mock(
            stdout=stdout, stderr=stderr, returncode=returncode)

    def test_git_worktree_uses_the_closed_git_content_set(self):
        existing = {
            "/workspace/.git",
            "/workspace/Tracked.md",
            "/workspace/visible/New.md",
        }
        completed = self.git_result(
            stdout=b"visible/New.md\0Tracked.md\0deleted.md\0")

        with mock.patch.object(kblib.os.path, "isdir", return_value=True), \
                mock.patch.object(
                    kblib.os.path, "lexists",
                    side_effect=lambda path: path in existing), \
                mock.patch.object(
                    kblib.subprocess, "run", return_value=completed) as run:
            result = kblib.repository_content_files(self.ROOT)

        self.assertEqual(
            [
                ("/workspace/Tracked.md", "Tracked.md"),
                ("/workspace/visible/New.md", "visible/New.md"),
            ],
            result)
        run.assert_called_once_with(
            ["git", "-C", self.ROOT, "ls-files", "-z", "--cached",
             "--others", "--exclude-standard"],
            stdout=kblib.subprocess.PIPE,
            stderr=kblib.subprocess.PIPE,
            check=False)

    def test_git_enumeration_failure_is_not_a_filesystem_fallback(self):
        completed = self.git_result(
            stderr=b"fixture enumeration failed", returncode=1)
        with mock.patch.object(kblib.os.path, "isdir", return_value=True), \
                mock.patch.object(kblib.os.path, "lexists", return_value=True), \
                mock.patch.object(
                    kblib.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(
                    ValueError, "fixture enumeration failed"):
                kblib.repository_content_files(self.ROOT)

    def test_git_paths_must_be_strict_unique_and_repository_relative(self):
        invalid_outputs = (
            b"../escape.md\0",
            b"/absolute.md\0",
            b"nested\\foreign.md\0",
            b"same.md\0same.md\0",
            b"bad-\xff.md\0",
        )
        with mock.patch.object(kblib.os.path, "isdir", return_value=True), \
                mock.patch.object(kblib.os.path, "lexists", return_value=True):
            for stdout in invalid_outputs:
                with self.subTest(stdout=stdout), mock.patch.object(
                        kblib.subprocess, "run",
                        return_value=self.git_result(stdout=stdout)):
                    with self.assertRaises(ValueError):
                        kblib.repository_content_files(self.ROOT)

    def test_exported_tree_uses_the_deterministic_filesystem_fallback(self):
        walk = [
            ("/workspace", ["z", "a"], ["Root.md"]),
            ("/workspace/a", [], ["Second.md", "First.md"]),
        ]
        with mock.patch.object(kblib.os.path, "isdir", return_value=True), \
                mock.patch.object(kblib.os.path, "lexists", return_value=False), \
                mock.patch.object(kblib.os, "walk", return_value=walk):
            result = kblib.repository_content_files(self.ROOT)

        self.assertEqual(
            [
                ("/workspace/Root.md", "Root.md"),
                ("/workspace/a/First.md", "a/First.md"),
                ("/workspace/a/Second.md", "a/Second.md"),
            ],
            result)
        self.assertEqual(["a", "z"], walk[0][1])

    def test_managed_markdown_scope_filters_hidden_directories_and_escapes(self):
        content = [
            ("/workspace/Root.md", "Root.md"),
            ("/workspace/visible/New.md", "visible/New.md"),
            ("/workspace/visible/.cache/Hidden.md",
             "visible/.cache/Hidden.md"),
            ("/workspace/visible/notes.txt", "visible/notes.txt"),
        ]
        with mock.patch.object(
                kblib, "inherited_path_capability", return_value=None), \
                mock.patch.object(
                    kblib, "repository_content_files", return_value=content):
            self.assertEqual(
                [("/workspace/visible/New.md", "visible/New.md")],
                kblib.iter_managed_md_files(self.ROOT, "visible"))
            with self.assertRaisesRegex(ValueError, "escapes"):
                kblib.iter_managed_md_files(self.ROOT, "../outside")


class RepositoryContentFilesGitIntegrationTests(unittest.TestCase):
    """Integration: one live Git seam proves index plus ignore behavior."""

    def test_git_index_and_ignore_rules_form_the_live_content_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "repo"
            root.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(root)], check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            (root / "Tracked.md").write_text(
                "# Tracked\n", encoding="utf-8")
            (root / "kept").mkdir()
            (root / "kept/Tracked.md").write_text(
                "# Tracked despite ignore\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "Tracked.md",
                 "kept/Tracked.md"], check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            (root / "visible").mkdir()
            (root / "visible/New.md").write_text(
                "# Visible\n", encoding="utf-8")
            (root / "ignored").mkdir()
            (root / "ignored/Local.md").write_text(
                "# Local only\n", encoding="utf-8")
            exclude = root / ".git/info/exclude"
            exclude.write_text(
                exclude.read_text(encoding="utf-8") +
                "\nignored/\nkept/\n", encoding="utf-8")

            result = [relative for _absolute, relative in
                      kblib.repository_content_files(root)]

        self.assertEqual(
            ["Tracked.md", "kept/Tracked.md", "visible/New.md"], result)


class RepositoryStructureUnitTests(unittest.TestCase):
    """Unit: repository_structure owns its narrower consumer predicates."""

    def test_repository_files_filters_control_state_and_suffixes(self):
        content = [
            ("/workspace/.git/config", ".git/config"),
            ("/workspace/.cambium/state.json", ".cambium/state.json"),
            ("/workspace/Notes.md", "Notes.md"),
            ("/workspace/profile.yaml", "profile.yaml"),
            ("/workspace/application.json", "application.json"),
        ]
        with mock.patch.object(
                repository_structure.kblib, "repository_content_files",
                return_value=content):
            result = list(repository_structure.repository_files(
                "/workspace", (".md", ".yaml")))

        self.assertEqual(
            [
                ("/workspace/Notes.md", "Notes.md"),
                ("/workspace/profile.yaml", "profile.yaml"),
            ],
            result)

    def test_yaml_scope_is_the_selected_profile_plus_kernel(self):
        files = [
            ("/workspace/profiles/selected/invalid.yaml",
             "profiles/selected/invalid.yaml"),
            ("/workspace/kernel/invalid.yaml", "kernel/invalid.yaml"),
            ("/workspace/application/invalid.yaml",
             "application/invalid.yaml"),
        ]
        payloads = {
            files[0][0]: b"- selected-is-not-a-mapping\n",
            files[1][0]: b"- kernel-is-not-a-mapping\n",
            files[2][0]: b"- application-is-not-a-mapping\n",
        }

        def read_bytes(path):
            return payloads[str(path)]

        with mock.patch.object(
                repository_structure, "repository_files",
                return_value=files), \
                mock.patch.object(
                    repository_structure.Path, "read_bytes",
                    autospec=True, side_effect=read_bytes):
            result = repository_structure.check_repository_structure(
                "/workspace", "profiles/selected/profile.toml")

        details = "\n".join(result["errors"])
        self.assertIn("profiles/selected/invalid.yaml", details)
        self.assertIn("kernel/invalid.yaml", details)
        self.assertNotIn("application/invalid.yaml", details)
        self.assertIn("cambium_yaml=2", result["details"])


class MocDiscoveryUnitTests(unittest.TestCase):
    """Unit: MOC discovery adds only MOC-specific content predicates."""

    def test_moc_discovery_consumes_the_repository_content_set(self):
        content = [
            ("/workspace/kept/MOC.md", "kept/MOC.md"),
            ("/workspace/.hidden/MOC.md", ".hidden/MOC.md"),
            ("/workspace/excluded/MOC.md", "excluded/MOC.md"),
            ("/workspace/Leaf.md", "Leaf.md"),
        ]
        payloads = {
            "/workspace/kept/MOC.md": "# Kept\n\n## Module Index\n",
            "/workspace/Leaf.md": "# Leaf\n",
        }

        def open_content(path, **_kwargs):
            return io.StringIO(payloads[path])

        with mock.patch.object(
                check_moc.kblib, "repository_content_files",
                return_value=content), \
                mock.patch("builtins.open", side_effect=open_content):
            result = check_moc.find_mocs("/workspace", {"excluded"})

        self.assertEqual(["kept/MOC.md"], result)


class RepositoryStructureCliIntegrationTests(unittest.TestCase):
    """Integration: retain one public adapter-to-application seam."""

    def test_cli_forwards_profile_reports_verdict_and_creates_no_state(self):
        output = io.StringIO()
        with mock.patch.object(
                repository_structure, "repository_files", return_value=[]), \
                mock.patch.object(
                    repository_structure, "check_repository_structure",
                    wraps=repository_structure.check_repository_structure
                ) as check, \
                mock.patch.object(
                    repository_structure.Path, "mkdir") as mkdir, \
                contextlib.redirect_stdout(output):
            result = repository_structure.main([
                "/workspace", "--profile-manifest",
                "profiles/selected/profile.toml",
            ])

        self.assertEqual(0, result)
        self.assertEqual("structural_errors = 0\n", output.getvalue())
        check.assert_called_once_with(
            "/workspace", "profiles/selected/profile.toml")
        mkdir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
