"""Tests for the K08/07 page-state projector."""

import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager, redirect_stdout
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
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, ".cambium/tmp"), exist_ok=True)
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

    def run_main(self, root, *argv):
        output = io.StringIO()
        with redirect_stdout(output):
            code = project_page_state.main([root, *argv])
        return code, output.getvalue()

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

    def test_unmaterialized_page_created_after_plan_is_rejected(self):
        """A typed missing target remains part of the final CAS set."""
        root = self.build()
        self.replace_ledger(root, ["Domain/Missing.md"])
        original_snapshot = project_page_state._page_snapshot
        materialized = False

        def materialize_after_first_missing_snapshot(root_path, relative):
            nonlocal materialized
            snapshot = original_snapshot(root_path, relative)
            if relative == "Domain/Missing.md" and not materialized:
                pathlib.Path(root, "Domain/Missing.md").write_text(
                    CLOSED, encoding="utf-8")
                materialized = True
            return snapshot

        with mock.patch.object(
                project_page_state, "_page_snapshot",
                side_effect=materialize_after_first_missing_snapshot):
            code, output = self.run_main(root, "--apply")

        self.assertTrue(materialized)
        self.assertEqual(1, code, output)
        self.assertEqual(CLOSED, self.read(root, "Domain/Missing.md"))
        self.assertFalse(pathlib.Path(
            root, ".cambium/tmp/state-writer.lock").exists())

    def test_unmaterialized_page_through_symlink_parent_is_rejected(self):
        """A missing leaf does not excuse a symlink in its parent chain."""
        for external in (False, True):
            with self.subTest(external=external):
                root = self.build()
                if external:
                    outside = pathlib.Path(tempfile.mkdtemp())
                    target = outside
                else:
                    outside = None
                    target = pathlib.Path(root, "Domain")
                pathlib.Path(root, "Alias").symlink_to(
                    target, target_is_directory=True)
                self.replace_ledger(root, ["Alias/Missing.md"])

                result = self.run_tool(root, "--apply")

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertRegex(
                    result.stdout, "symlink|outside the repository root")
                self.assertFalse(pathlib.Path(target, "Missing.md").exists())
                if outside is not None:
                    shutil.rmtree(outside)

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

    def test_same_bytes_different_inode_swap_rejects_stale_plan(self):
        """A replacement inode is drift even when it carries equal bytes."""
        root = self.build()
        page = pathlib.Path(root, "Domain/Closed.md")
        replacement = pathlib.Path(root, "Domain/Closed.replacement")
        replacement.write_bytes(page.read_bytes())
        original_snapshot = project_page_state._page_snapshot
        page_snapshots = 0
        swapped = False

        def swap_after_planning(root_path, relative):
            nonlocal page_snapshots, swapped
            snapshot = original_snapshot(root_path, relative)
            if relative == "Domain/Closed.md":
                page_snapshots += 1
                if page_snapshots == 1:
                    os.replace(replacement, page)
                    swapped = True
            return snapshot

        with mock.patch.object(
                project_page_state, "_page_snapshot",
                side_effect=swap_after_planning):
            code, output = self.run_main(
                root, "--page", "Domain/Closed.md", "--apply")

        self.assertTrue(swapped)
        self.assertEqual(1, code, output)
        self.assertEqual(CLOSED, page.read_text(encoding="utf-8"))

    def test_same_inode_change_after_staging_is_not_overwritten(self):
        """The final CAS must compare bytes after the staged file is durable."""
        root = self.build()
        page = pathlib.Path(root, "Domain/Closed.md")
        concurrent = CLOSED.replace("# Closed", "# Concurrent edit")
        original_stage = project_page_state._stage_page
        changed = False

        def change_after_stage(root_path, projection):
            nonlocal changed
            staged = original_stage(root_path, projection)
            if projection.relative == "Domain/Closed.md" and not changed:
                inode = page.stat().st_ino
                page.write_text(concurrent, encoding="utf-8")
                self.assertEqual(inode, page.stat().st_ino)
                changed = True
            return staged

        with mock.patch.object(
                project_page_state, "_stage_page",
                side_effect=change_after_stage):
            code, output = self.run_main(
                root, "--page", "Domain/Closed.md", "--apply")

        self.assertTrue(changed)
        self.assertEqual(1, code, output)
        self.assertEqual(concurrent, page.read_text(encoding="utf-8"))

    def test_staged_after_image_swap_is_rejected(self):
        """A staged name cannot be replaced by bytes or a symlink."""
        for replacement in ("bytes", "symlink"):
            with self.subTest(replacement=replacement):
                root = self.build()
                original_stage = project_page_state._stage_page
                outside = pathlib.Path(root).parent / (
                    "stage-outside-%s" % uuid.uuid4().hex)
                outside.write_text("outside\n", encoding="utf-8")

                def replace_staged_name(root_path, projection):
                    staged = original_stage(root_path, projection)
                    path = pathlib.Path(
                        root, "Domain", staged.temporary_name)
                    path.unlink()
                    if replacement == "bytes":
                        path.write_text("corrupted stage\n", encoding="utf-8")
                    else:
                        path.symlink_to(outside)
                    return staged

                with mock.patch.object(
                        project_page_state, "_stage_page",
                        side_effect=replace_staged_name):
                    code, output = self.run_main(
                        root, "--page", "Domain/Closed.md", "--apply")

                self.assertEqual(1, code, output)
                self.assertEqual(CLOSED,
                                 self.read(root, "Domain/Closed.md"))
                self.assertEqual("outside\n",
                                 outside.read_text(encoding="utf-8"))
                outside.unlink()

    def test_staged_bytes_changed_during_install_are_rejected(self):
        root = self.build()
        original_link = project_page_state.os.link
        changed = False

        def corrupt_before_install_link(source, destination, *args, **kwargs):
            nonlocal changed
            if (str(source).startswith(
                    project_page_state.TEMP_PREFIX + "after-") and
                    destination == "Closed.md" and not changed):
                parent_fd = kwargs["src_dir_fd"]
                fd = os.open(source, os.O_WRONLY | os.O_TRUNC,
                             dir_fd=parent_fd)
                try:
                    os.write(fd, b"corrupted during install\n")
                    os.fsync(fd)
                finally:
                    os.close(fd)
                changed = True
            return original_link(source, destination, *args, **kwargs)

        with mock.patch.object(
                project_page_state.os, "link",
                side_effect=corrupt_before_install_link):
            code, output = self.run_main(
                root, "--page", "Domain/Closed.md", "--apply")

        self.assertTrue(changed)
        self.assertEqual(1, code, output)
        self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))

    def test_later_publication_failure_restores_earlier_page(self):
        """A multi-page failure must not leave an earlier projection behind."""
        root = self.build()
        original_link = project_page_state.os.link
        routed_install_attempted = False

        def fail_second_after_claim(source, destination, *args, **kwargs):
            nonlocal routed_install_attempted
            if (str(source).startswith(
                    project_page_state.TEMP_PREFIX + "after-") and
                    destination == "Routed.md"):
                routed_install_attempted = True
                raise OSError("injected second-page publication failure")
            return original_link(source, destination, *args, **kwargs)

        with mock.patch.object(
                project_page_state.os, "link",
                side_effect=fail_second_after_claim):
            code, output = self.run_main(root, "--apply")

        self.assertEqual(1, code, output)
        self.assertTrue(routed_install_attempted)
        self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))
        self.assertEqual(ROUTED, self.read(root, "Domain/Routed.md"))
        self.assertFalse(pathlib.Path(
            root, ".cambium/tmp/state-writer.lock").exists())
        self.assertEqual([], list(pathlib.Path(root).rglob(
            ".cambium-page-state-*")))

    def test_later_failure_does_not_overwrite_concurrent_published_edit(self):
        """Rollback is a CAS: a changed after-image belongs to its writer."""
        root = self.build()
        page = pathlib.Path(root, "Domain/Closed.md")
        concurrent = "Concurrent edit after page-state publication.\n"
        original_publish = project_page_state._publish_staged
        publications = 0

        def edit_first_then_fail_second(root_path, staged):
            nonlocal publications
            publications += 1
            if publications == 1:
                result = original_publish(root_path, staged)
                # An uncooperative writer can change the installed inode while
                # the projector moves on to the next page.  A later rollback
                # must not erase those bytes merely because the inode still
                # belongs to this transaction's published after-image.
                page.write_text(concurrent, encoding="utf-8")
                return result
            raise OSError("injected later-page publication failure")

        with mock.patch.object(
                project_page_state, "_publish_staged",
                side_effect=edit_first_then_fail_second):
            code, output = self.run_main(root, "--apply")

        self.assertEqual(1, code, output)
        self.assertGreaterEqual(publications, 2)
        self.assertEqual(concurrent, page.read_text(encoding="utf-8"))
        self.assertIn("rollback is incomplete", output)
        lock = pathlib.Path(root, ".cambium/tmp/state-writer.lock")
        self.assertTrue(lock.is_dir())
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual("rollback-required",
                         owner.get("operation", {}).get("status"))
        journal = json.loads(
            (lock / project_page_state.JOURNAL_NAME).read_text(
                encoding="utf-8"))
        artifact = next(
            row for row in journal.get("artifacts", [])
            if row.get("path") == "Domain/Closed.md")
        self.assertIsNone(artifact.get("staged_after_image_active"))
        self.assertTrue(artifact.get("after_image_verified"))
        self.assertTrue(artifact.get("published"))
        self.assertTrue(artifact.get("claimed"))
        backup = pathlib.Path(root, "Domain", artifact["rollback_image"])
        self.assertTrue(backup.is_file())
        self.assertEqual(CLOSED.encode("utf-8"), backup.read_bytes())

    def test_late_coverage_change_rolls_back_all_pages(self):
        """A stale Ledger owner cannot leave a successful projection."""
        root = self.build()
        original_publish = project_page_state._publish_staged
        changed = False

        def change_ledger_after_first_publish(root_path, staged):
            nonlocal changed
            result = original_publish(root_path, staged)
            if not changed:
                pathlib.Path(
                    root, ".cambium/state/coverage_ledger.yaml"
                ).write_text(
                    LEDGER.replace("authoring_status: reviewed",
                                   "authoring_status: drafted", 1),
                    encoding="utf-8")
                changed = True
            return result

        with mock.patch.object(
                project_page_state, "_publish_staged",
                side_effect=change_ledger_after_first_publish):
            code, output = self.run_main(root, "--apply")

        self.assertTrue(changed)
        self.assertEqual(1, code, output)
        self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))
        self.assertEqual(ROUTED, self.read(root, "Domain/Routed.md"))
        self.assertFalse(pathlib.Path(
            root, ".cambium/tmp/state-writer.lock").exists())

    def test_failed_rollback_retains_lock_and_recovery_evidence(self):
        """An unproven rollback leaves exact transaction intent fail-closed."""
        root = self.build()
        original_publish = project_page_state._publish_staged
        original_restore = project_page_state._restore_staged
        publications = 0
        restorations = 0

        def fail_second_publication(root_path, staged):
            nonlocal publications
            publications += 1
            if publications == 2:
                raise OSError("injected second-page publication failure")
            return original_publish(root_path, staged)

        def fail_first_restore(root_path, staged):
            nonlocal restorations
            restorations += 1
            if restorations == 1:
                raise OSError("injected rollback failure")
            return original_restore(root_path, staged)

        with mock.patch.object(project_page_state, "_publish_staged",
                               side_effect=fail_second_publication), \
                mock.patch.object(project_page_state, "_restore_staged",
                                  side_effect=fail_first_restore):
            code, output = self.run_main(root, "--apply")

        self.assertEqual(1, code, output)
        self.assertGreaterEqual(publications, 2)
        self.assertGreaterEqual(restorations, 1)
        self.assertIn("rollback", output.lower())
        owner_path = pathlib.Path(
            root, ".cambium/tmp/state-writer.lock/owner.json")
        self.assertTrue(owner_path.is_file())
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        operation = owner.get("operation", {})
        self.assertEqual("project_page_state", operation.get("tool"))
        evidence = json.dumps(operation, sort_keys=True)
        self.assertIn("Domain/Closed.md", evidence)
        self.assertIn("Domain/Routed.md", evidence)
        self.assertIn("before", evidence)
        self.assertIn("after", evidence)
        self.assertEqual("rollback-required", operation.get("status"))
        journal_path = owner_path.with_name(
            project_page_state.JOURNAL_NAME)
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual("rollback-required", journal.get("status"))
        closed_artifact = next(
            artifact for artifact in journal.get("artifacts", [])
            if artifact.get("path") == "Domain/Closed.md")
        backup_name = closed_artifact.get("rollback_image")
        self.assertIsInstance(backup_name, str)
        backup = pathlib.Path(root, "Domain", backup_name)
        self.assertTrue(backup.is_file())
        self.assertEqual(CLOSED.encode("utf-8"), backup.read_bytes())

    def test_success_uses_one_writer_lock_and_cleans_transaction_files(self):
        root = self.build()
        real_lock = project_page_state.kblib.runtime_write_lock
        observed = []

        @contextmanager
        def observing_lock(*args, **kwargs):
            observed.append(kwargs.get("owner_metadata"))
            with real_lock(*args, **kwargs) as lease:
                yield lease

        with mock.patch.object(
                project_page_state.kblib, "runtime_write_lock",
                side_effect=observing_lock):
            code, output = self.run_main(root, "--apply")

        self.assertEqual(0, code, output)
        self.assertEqual(1, len(observed))
        self.assertEqual("project_page_state", observed[0].get("tool"))
        self.assertFalse(pathlib.Path(
            root, ".cambium/tmp/state-writer.lock").exists())
        self.assertEqual([], list(pathlib.Path(root).rglob(
            ".cambium-page-state-*")))

    def test_artifact_names_are_journaled_before_first_claim(self):
        root = self.build()
        real_publish = project_page_state._publish_staged
        observed = []

        def inspect_journal_before_claim(root_path, staged):
            journal = json.loads(pathlib.Path(
                root, ".cambium/tmp/state-writer.lock",
                project_page_state.JOURNAL_NAME
            ).read_text(encoding="utf-8"))
            self.assertEqual("staged" if not observed else "publishing",
                             journal.get("status"))
            artifacts = {
                artifact["path"]: artifact
                for artifact in journal.get("artifacts", [])
            }
            self.assertEqual({"Domain/Closed.md", "Domain/Routed.md"},
                             set(artifacts))
            for artifact in artifacts.values():
                self.assertIsInstance(artifact.get("staged_after_image"), str)
                self.assertIsInstance(artifact.get("rollback_image"), str)
                self.assertIsInstance(artifact.get("staged_after_inode"), int)
            observed.append(staged.projection.relative)
            return real_publish(root_path, staged)

        with mock.patch.object(
                project_page_state, "_publish_staged",
                side_effect=inspect_journal_before_claim):
            code, output = self.run_main(root, "--apply")

        self.assertEqual(0, code, output)
        self.assertEqual(["Domain/Closed.md", "Domain/Routed.md"], observed)

    def test_changed_page_has_only_plan_and_final_cas_descriptor_opens(self):
        """One changed page descriptor is opened once per logical phase."""
        root = self.build()
        original_open = project_page_state.os.open
        page_opens = 0

        def count_page_opens(path, flags, *args, **kwargs):
            nonlocal page_opens
            basename = os.path.basename(os.fspath(path))
            is_directory = bool(flags & getattr(os, "O_DIRECTORY", 0))
            access = flags & getattr(os, "O_ACCMODE", 3)
            if (basename == "Closed.md" and not is_directory and
                    access == os.O_RDONLY):
                page_opens += 1
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(
                project_page_state.os, "open",
                side_effect=count_page_opens):
            code, output = self.run_main(
                root, "--page", "Domain/Closed.md", "--apply")

        self.assertEqual(0, code, output)
        self.assertEqual(2, page_opens)


if __name__ == "__main__":
    unittest.main()
