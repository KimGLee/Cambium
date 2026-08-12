"""Tests for the K08/07 page-state projector."""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[2]
TOOL = REPO / "Tools" / "project_page_state.py"
sys.path.insert(0, str(REPO / "Tools"))

import project_page_state

LEDGER = """schema_version: 1
pages:
  - path: "Domain/Closed.md"
    coverage_disposition: required
    authoring_status: reviewed
    next_batch:
  - path: "Domain/Routed.md"
    coverage_disposition: required
    authoring_status: drafted
    next_batch: T-002
  - path: "Domain/Bare.md"
    coverage_disposition: required
    authoring_status: drafted
    next_batch: T-003
"""

CLOSED = """---
type: concept
authoring_status: drafted
next_batch: T-001
---
# Closed
"""

ROUTED = """---
type: concept
authoring_status: drafted
next_batch: T-001
---
# Routed
"""

BARE = """---
type: concept
---
# Bare
"""


class ProjectPageStateTests(unittest.TestCase):
    def build(self):
        root = tempfile.mkdtemp()
        files = {
            ".cambium/state/coverage_ledger.yaml": LEDGER,
            "Domain/Closed.md": CLOSED,
            "Domain/Routed.md": ROUTED,
            "Domain/Bare.md": BARE,
        }
        for rel, body in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
        return root

    def run_tool(self, root, *argv):
        return subprocess.run(
            [sys.executable, str(TOOL), root, *argv],
            capture_output=True, text=True)

    def read(self, root, rel):
        with open(os.path.join(root, rel), encoding="utf-8") as handle:
            return handle.read()

    def test_dry_run_plans_but_writes_nothing(self):
        root = self.build()
        result = self.run_tool(root)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("PLAN", result.stdout)
        self.assertIn("dry run", result.stdout)
        self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))

    def test_apply_updates_removes_and_never_adds(self):
        root = self.build()
        result = self.run_tool(root, "--apply")
        self.assertEqual(0, result.returncode, result.stdout)
        closed = self.read(root, "Domain/Closed.md")
        # updated to the owner value
        self.assertIn("authoring_status: reviewed", closed)
        # removed: owner next_batch is empty (the closed-batch stale copy)
        self.assertNotIn("next_batch", closed)
        routed = self.read(root, "Domain/Routed.md")
        self.assertIn("next_batch: T-002", routed)
        # a page that never carried a projection field does not gain one
        bare = self.read(root, "Domain/Bare.md")
        self.assertNotIn("authoring_status", bare)
        self.assertNotIn("next_batch", bare)
        # idempotent: a second run plans zero changes
        again = self.run_tool(root, "--apply")
        self.assertIn("field_changes=0", again.stdout)

    def test_page_scope_and_unknown_page(self):
        root = self.build()
        result = self.run_tool(root, "--page", "Domain/Routed.md", "--apply")
        self.assertEqual(0, result.returncode, result.stdout)
        # only the scoped page was touched
        self.assertIn("next_batch: T-001", self.read(root, "Domain/Closed.md"))
        self.assertIn("next_batch: T-002", self.read(root, "Domain/Routed.md"))
        unknown = self.run_tool(root, "--page", "Domain/Absent.md")
        self.assertEqual(1, unknown.returncode, unknown.stdout)
        self.assertIn("not in the Coverage Ledger", unknown.stdout)

    def replace_ledger(self, root, paths):
        rows = []
        for path in paths:
            rows.append(
                "  - path: %s\n"
                "    coverage_disposition: required\n"
                "    authoring_status: reviewed\n"
                "    next_batch: null\n" % repr(path)
            )
        pathlib.Path(
            root, ".cambium/state/coverage_ledger.yaml"
        ).write_text("schema_version: 1\npages:\n" + "".join(rows),
                     encoding="utf-8")

    def test_parent_escape_is_rejected_without_writing_any_page(self):
        root = self.build()
        outside = pathlib.Path(root).parent / "outside.md"
        outside.write_text(CLOSED, encoding="utf-8")
        self.replace_ledger(root, ["Domain/Closed.md", "../outside.md"])

        result = self.run_tool(
            root, "--page", "Domain/Closed.md", "--page", "../outside.md",
            "--apply")

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("unsafe or invalid", result.stdout)
        self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))
        self.assertEqual(CLOSED, outside.read_text(encoding="utf-8"))
        outside.unlink()

    def test_absolute_page_path_is_rejected(self):
        root = self.build()
        outside = pathlib.Path(root).parent / "absolute.md"
        outside.write_text(CLOSED, encoding="utf-8")
        self.replace_ledger(root, [str(outside)])

        result = self.run_tool(root, "--apply")

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("repository-relative", result.stdout)
        self.assertEqual(CLOSED, outside.read_text(encoding="utf-8"))
        outside.unlink()

    def test_symlinked_page_and_parent_are_rejected(self):
        for parent_link in (False, True):
            with self.subTest(parent_link=parent_link):
                root = self.build()
                outside_dir = pathlib.Path(root).parent / (
                    "outside-parent" if parent_link else "outside-page")
                outside_dir.mkdir(exist_ok=True)
                outside = outside_dir / "Page.md"
                outside.write_text(CLOSED, encoding="utf-8")
                if parent_link:
                    shutil.rmtree(pathlib.Path(root, "Domain"))
                    pathlib.Path(root, "Domain").symlink_to(
                        outside_dir, target_is_directory=True)
                    relative = "Domain/Page.md"
                else:
                    relative = "Domain/Linked.md"
                    pathlib.Path(root, relative).symlink_to(outside)
                self.replace_ledger(root, [relative])

                result = self.run_tool(root, "--apply")

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertRegex(
                    result.stdout, "symlink|outside the repository root")
                self.assertEqual(CLOSED, outside.read_text(encoding="utf-8"))
                shutil.rmtree(outside_dir)

    def test_hard_linked_page_is_rejected(self):
        root = self.build()
        original = pathlib.Path(root, "Domain/Closed.md")
        linked = pathlib.Path(root, "Domain/Linked.md")
        os.link(original, linked)
        self.replace_ledger(root, ["Domain/Linked.md"])
        before = original.read_text(encoding="utf-8")

        result = self.run_tool(root, "--apply")

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("singly-linked", result.stdout)
        self.assertEqual(before, original.read_text(encoding="utf-8"))

    def test_unmaterialized_contained_page_remains_a_noop(self):
        root = self.build()
        self.replace_ledger(root, ["Domain/Missing.md"])

        result = self.run_tool(root, "--apply")

        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("pages=0 field_changes=0", result.stdout)

    def test_internal_symlink_components_are_rejected(self):
        for parent_link in (False, True):
            with self.subTest(parent_link=parent_link):
                root = self.build()
                if parent_link:
                    pathlib.Path(root, "Alias").symlink_to(
                        pathlib.Path(root, "Domain"), target_is_directory=True)
                    relative = "Alias/Closed.md"
                else:
                    relative = "Domain/Linked.md"
                    pathlib.Path(root, relative).symlink_to(
                        pathlib.Path(root, "Domain/Closed.md"))
                self.replace_ledger(root, [relative])

                result = self.run_tool(root, "--apply")

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("symlink", result.stdout)
                self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))

    def test_symlinked_coverage_ledger_is_rejected(self):
        root = self.build()
        ledger = pathlib.Path(root, ".cambium/state/coverage_ledger.yaml")
        outside = pathlib.Path(root).parent / "outside-ledger.yaml"
        outside.write_bytes(ledger.read_bytes())
        ledger.unlink()
        ledger.symlink_to(outside)

        result = self.run_tool(root, "--apply")

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertRegex(result.stdout, "symlink|outside the repository root")
        self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))
        outside.unlink()

    def test_last_moment_target_swap_is_rejected_without_touching_outside(self):
        root = self.build()
        page = pathlib.Path(root, "Domain/Closed.md")
        snapshot = project_page_state._page_snapshot(
            root, "Domain/Closed.md")
        new_text, _changes = project_page_state.project_page(
            snapshot.read_text(), {
                "path": "Domain/Closed.md",
                "coverage_disposition": "required",
                "authoring_status": "reviewed",
                "next_batch": None,
            })
        outside = pathlib.Path(root).parent / "swap-outside.md"
        outside.write_text(CLOSED, encoding="utf-8")
        original_open = project_page_state.os.open
        swapped = False

        def swap_before_target_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if (path == "Closed.md" and kwargs.get("dir_fd") is not None and
                    not swapped):
                page.unlink()
                page.symlink_to(outside)
                swapped = True
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(
                project_page_state.os, "open",
                side_effect=swap_before_target_open):
            with self.assertRaises(OSError):
                project_page_state._publish_page(
                    root, "Domain/Closed.md", snapshot, new_text)

        self.assertTrue(swapped)
        self.assertEqual(CLOSED, outside.read_text(encoding="utf-8"))
        outside.unlink()


if __name__ == "__main__":
    unittest.main()
