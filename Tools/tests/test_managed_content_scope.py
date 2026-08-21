from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import check_batch_close
import check_moc
import kblib


class ManagedContentScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        self.root.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(self.root)], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        (self.root / "Tracked.md").write_text(
            "# Tracked\n", encoding="utf-8")
        kept = self.root / "kept"
        kept.mkdir()
        (kept / "Tracked MOC.md").write_text(
            "## Module Index\n\n| Module | Sections |\n"
            "|---|---|\n| [[Tracked]] | Tracked |\n",
            encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.root), "add", "Tracked.md",
             "kept/Tracked MOC.md"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        visible = self.root / "visible"
        visible.mkdir()
        (visible / "New.md").write_text("# Visible\n", encoding="utf-8")

        ignored = self.root / "ignored"
        ignored.mkdir()
        (ignored / "Malformed.md").write_text(
            "| A | B |\n|---|---|\n| one | two | three |\n\n"
            "## Module Index\n",
            encoding="utf-8")
        exclude = self.root / ".git/info/exclude"
        exclude.write_text(
            exclude.read_text(encoding="utf-8") +
            "\nignored/\nkept/\n",
            encoding="utf-8")

    def test_tracked_and_visible_untracked_files_form_the_content_set(self):
        paths = [
            relative for _absolute, relative
            in kblib.repository_content_files(self.root)
            if relative.endswith(".md")
        ]

        self.assertEqual(
            ["Tracked.md", "kept/Tracked MOC.md", "visible/New.md"],
            paths)
        self.assertEqual(
            paths,
            [relative for _absolute, relative
             in kblib.iter_managed_md_files(self.root)])

    def test_all_content_gates_exclude_ignored_untracked_markdown(self):
        structural = check_batch_close._structural_check(
            self.root, {"queue": {}})
        graph_paths = [
            relative for _absolute, relative
            in check_batch_close._repo_files(self.root, (".md",))
        ]

        self.assertEqual([], structural["errors"])
        self.assertNotIn("ignored/Malformed.md", graph_paths)
        self.assertEqual(
            ["kept/Tracked MOC.md"],
            check_moc.find_mocs(self.root, set()))

    def test_exported_tree_without_git_keeps_filesystem_fallback(self):
        exported = Path(self.temporary.name).resolve() / "exported"
        (exported / "ignored").mkdir(parents=True)
        (exported / "ignored/Still Content.md").write_text(
            "# Exported\n", encoding="utf-8")

        self.assertEqual(
            ["ignored/Still Content.md"],
            [relative for _absolute, relative
             in kblib.repository_content_files(exported)])


if __name__ == "__main__":
    unittest.main()
