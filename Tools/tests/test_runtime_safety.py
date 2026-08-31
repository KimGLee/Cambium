"""Owner-focused tests for the shared runtime safety primitives.

Writer-specific policy and full Task lifecycles belong to their writer test
modules. This suite retains the shared path, Receipt append, durable replace,
writer-lock, initial-publication, and repository-snapshot contracts. Slow
tests are reserved for real namespace aliases, concurrency, hard exits, and
recovery boundaries.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import Tools.execution.task_runtime.init_state as init_state
import Tools.execution.task_runtime.runtime_paths as runtime_paths
import Tools.platform.common.kblib as kblib


TOOLS = Path(__file__).resolve().parents[1]


class ReceiptSafetyTests(unittest.TestCase):
    def receipt_root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / ".cambium/receipts").mkdir(parents=True)
        (root / ".cambium/state").mkdir(parents=True)
        return root

    def test_receipt_append_outcome_is_one_three_state_contract(self):
        before = {
            "path": "/receipt.jsonl",
            "counts": [2],
            "structurally_valid": True,
        }
        cases = (
            (dict(before, counts=[3]), "present"),
            (dict(before, counts=[2]), "absent"),
            (dict(before, counts=[4]), "uncertain"),
            (dict(before, counts=[3], structurally_valid=False),
             "uncertain"),
            ({"path": "/other.jsonl", "counts": [3],
              "structurally_valid": True}, "uncertain"),
        )
        for after, expected in cases:
            with self.subTest(expected=expected, after=after):
                self.assertEqual(
                    expected, kblib.receipt_append_outcome(before, after))

    def test_receipt_writer_publishes_complete_jsonl_and_preserves_creator(self):
        root = self.receipt_root()
        receipt = root / ".cambium/receipts/queue.jsonl"
        kblib.write_receipts(receipt, [{"receipt_id": "r1"}])
        kblib.write_receipts(receipt, [{"receipt_id": "r2"}])
        self.assertEqual(
            ["r1", "r2"],
            [json.loads(line)["receipt_id"] for line in
             receipt.read_text(encoding="utf-8").splitlines()],
        )

        canonical = root / ".cambium/receipts/canonical.jsonl"
        external = {"receipt_id": "external"}
        kblib.write_receipts(canonical, [external], exclusive=True)
        with self.assertRaises(FileExistsError):
            kblib.write_receipts(
                canonical, [{"receipt_id": "replacement"}], exclusive=True)
        self.assertEqual(
            [external],
            [json.loads(line) for line in
             canonical.read_text(encoding="utf-8").splitlines()],
        )

    def test_receipt_writer_rejects_aliases_and_authoritative_targets(self):
        for mutation in (
                "hardlink", "final-symlink", "parent-symlink",
                "authority", "authority-alias"):
            with self.subTest(mutation=mutation):
                root = self.receipt_root()
                state = root / ".cambium/state/required_queue.yaml"
                state.write_text("sentinel\n", encoding="utf-8")
                before = state.read_bytes()
                if mutation == "hardlink":
                    target = root / ".cambium/receipts/queue.jsonl"
                    os.link(state, target)
                elif mutation == "final-symlink":
                    outside = root / "outside.jsonl"
                    outside.write_text("outside\n", encoding="utf-8")
                    target = root / ".cambium/receipts/queue.jsonl"
                    target.symlink_to(outside)
                elif mutation == "parent-symlink":
                    receipts = root / ".cambium/receipts"
                    receipts.rmdir()
                    outside = root / "outside-receipts"
                    outside.mkdir()
                    receipts.symlink_to(outside, target_is_directory=True)
                    target = receipts / "queue.jsonl"
                elif mutation == "authority":
                    target = state
                else:
                    alias = root / "receipt-alias"
                    alias.symlink_to(
                        root / ".cambium/state", target_is_directory=True)
                    target = alias / "required_queue.yaml"

                with self.assertRaises((OSError, ValueError)):
                    kblib.write_receipts(
                        target, [{"receipt_id": "attack"}])
                self.assertEqual(before, state.read_bytes())

    def test_concurrent_process_appenders_preserve_every_record(self):
        root = self.receipt_root()
        receipt = root / ".cambium/receipts/concurrent.jsonl"
        program = """
import sys
sys.path.insert(0, sys.argv[1])
import Tools.platform.common.kblib as kblib
path, prefix = sys.argv[2], sys.argv[3]
for index in range(40):
    kblib.write_receipts(path, [{"receipt_id": "%s-%02d" % (prefix, index)}])
"""
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", program, str(TOOLS.parent),
                 str(receipt), "writer-%d" % writer],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            for writer in range(4)
        ]
        outputs = [process.communicate(timeout=20) for process in processes]
        for process, (output, _) in zip(processes, outputs):
            self.assertEqual(0, process.returncode, output)
        records = [json.loads(line) for line in
                   receipt.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(160, len(records))
        self.assertEqual(160, len({record["receipt_id"] for record in records}))


class DurableReplaceContractTests(unittest.TestCase):
    def test_cross_directory_replace_fsyncs_both_namespace_changes(self):
        source = "/repo/source/delta.yaml"
        destination = "/repo/destination/delta.yaml"
        with mock.patch.object(
                kblib._pathcaps, "open_parent",
                return_value=(None, None, None)), \
                mock.patch.object(kblib.os, "replace") as replace, \
                mock.patch.object(
                    kblib.os, "open", side_effect=(41, 42)) as opened, \
                mock.patch.object(kblib.os, "fsync") as fsync, \
                mock.patch.object(kblib.os, "close") as close:
            kblib.durable_replace(source, destination)

        replace.assert_called_once_with(source, destination)
        self.assertEqual(
            ["/repo/destination", "/repo/source"],
            [call.args[0] for call in opened.call_args_list])
        self.assertEqual([41, 42],
                         [call.args[0] for call in fsync.call_args_list])
        self.assertEqual([41, 42],
                         [call.args[0] for call in close.call_args_list])

    def test_directory_fsync_failure_surfaces_after_atomic_rename(self):
        source = "/repo/source/delta.yaml"
        destination = "/repo/destination/delta.yaml"
        with mock.patch.object(
                kblib._pathcaps, "open_parent",
                return_value=(None, None, None)), \
                mock.patch.object(kblib.os, "replace") as replace, \
                mock.patch.object(kblib.os, "open", return_value=41), \
                mock.patch.object(
                    kblib.os, "fsync",
                    side_effect=OSError(
                        "injected directory fsync failure")), \
                mock.patch.object(kblib.os, "close") as close:
            with self.assertRaisesRegex(OSError, "directory fsync"):
                kblib.durable_replace(source, destination)

        replace.assert_called_once_with(source, destination)
        close.assert_called_once_with(41)


class RuntimeWriteLockTests(unittest.TestCase):
    def lock_root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / ".cambium/tmp").mkdir(parents=True)
        return root

    def test_lock_lifecycle_distinguishes_success_error_and_reconciliation(self):
        root = self.lock_root()
        with kblib.runtime_write_lock(root) as lease:
            lock_path = Path(lease)
            self.assertTrue(lock_path.is_dir())
            with self.assertRaises(kblib.RuntimeStateLockedError):
                with kblib.runtime_write_lock(root):
                    pass
        self.assertFalse(lock_path.exists())
        with kblib.runtime_write_lock(root):
            pass

        root = self.lock_root()
        with self.assertRaisesRegex(RuntimeError, "partial write"):
            with kblib.runtime_write_lock(
                    root, owner_metadata={"tool": "fixture"}) as lease:
                lock_path = Path(lease)
                raise RuntimeError("partial write")
        self.assertTrue(lock_path.is_dir())
        owner = json.loads(
            (lock_path / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual("fixture", owner["operation"]["tool"])

        root = self.lock_root()
        with self.assertRaisesRegex(RuntimeError, "rolled back"):
            with kblib.runtime_write_lock(root) as lease:
                lock_path = Path(lease)
                lease.mark_reconciled()
                raise RuntimeError("rolled back")
        self.assertFalse(lock_path.exists())

        root = self.lock_root()
        with self.assertRaisesRegex(ValueError, "stale preflight"):
            with kblib.runtime_write_lock(root) as lease:
                lock_path = Path(lease)
                with kblib.no_authoritative_write_guard(lease):
                    raise ValueError("stale preflight")
        self.assertFalse(lock_path.exists())

    def test_hard_process_exit_preserves_current_restart_evidence(self):
        root = self.lock_root()
        program = (
            "import os,sys; "
            "sys.path.insert(0, sys.argv[1]); "
            "import Tools.platform.common.kblib as kblib; "
            "cm=kblib.runtime_write_lock(sys.argv[2], "
            "owner_metadata={'tool':'hard-exit-fixture',"
            "'before_queue_sha256':'sha256:'+'0'*64,"
            "'planned_after_queue_sha256':'sha256:'+'1'*64}); "
            "cm.__enter__(); os._exit(23)"
        )
        child = subprocess.run(
            [sys.executable, "-c", program, str(TOOLS.parent), str(root)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, check=False,
        )
        self.assertEqual(23, child.returncode, child.stdout)
        owner = json.loads((
            root / ".cambium/tmp/state-writer.lock/owner.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual("hard-exit-fixture", owner["operation"]["tool"])
        self.assertIn("before_queue_sha256", owner["operation"])
        self.assertIn("planned_after_queue_sha256", owner["operation"])


class InitNamespaceContractTests(unittest.TestCase):
    def test_governance_namespace_accepts_only_plan_and_free_append_marker(self):
        root = "/repo"
        runtime = root + "/" + runtime_paths.RUNTIME_ROOT
        plan_path = runtime_paths.TASK_PLAN_DELTA_ROOT + "/TP-001.yaml"

        def runtime_relative(path):
            return path.removeprefix(runtime_paths.RUNTIME_ROOT + "/")

        allowed = {
            runtime_relative(path)
            for path in runtime_paths.PRE_TASK_REQUIRED_FILE_PATHS
        }
        allowed.update({
            runtime_relative(plan_path),
            runtime_relative(runtime_paths.RECEIPT_APPEND_FREE_PATH),
        })

        def walk_rows(files):
            directories = set()
            for relative in files:
                parent = os.path.dirname(relative)
                while parent:
                    directories.add(parent)
                    parent = os.path.dirname(parent)
            rows = []
            for relative in ("", *sorted(directories)):
                prefix = relative + os.sep if relative else ""
                children = {
                    candidate[len(prefix):].split(os.sep, 1)[0]
                    for candidate in directories
                    if candidate.startswith(prefix) and
                    os.sep not in candidate[len(prefix):]
                }
                names = {
                    candidate[len(prefix):]
                    for candidate in files
                    if candidate.startswith(prefix) and
                    os.sep not in candidate[len(prefix):]
                }
                rows.append((
                    os.path.join(runtime, relative),
                    sorted(children), sorted(names)))
            return rows, directories

        def validate(files):
            rows, directories = walk_rows(files)
            absolute_files = {
                os.path.join(runtime, *relative.split("/"))
                for relative in files
            }
            absolute_directories = {
                runtime,
                *(os.path.join(runtime, *relative.split("/"))
                  for relative in directories),
            }
            with mock.patch.object(
                    init_state.os.path, "lexists", return_value=True), \
                    mock.patch.object(
                        init_state.os.path, "islink", return_value=False), \
                    mock.patch.object(
                        init_state.os.path, "isdir",
                        side_effect=lambda path: path in absolute_directories), \
                    mock.patch.object(
                        init_state.os.path, "isfile",
                        side_effect=lambda path: path in absolute_files), \
                    mock.patch.object(
                        init_state.os, "walk", return_value=rows):
                return init_state._governance_only_namespace_errors(
                    root, allowed_plan_path=plan_path)

        self.assertEqual([], validate(allowed))
        held = set(allowed)
        held.remove(runtime_relative(runtime_paths.RECEIPT_APPEND_FREE_PATH))
        held.add(runtime_relative(runtime_paths.RECEIPT_APPEND_HELD_PATH))
        errors = validate(held)
        self.assertTrue(any("receipt-append.held" in value
                            for value in errors), errors)


class InitPublicationTests(unittest.TestCase):
    def publication_root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def documents(self):
        return {
            name: "fixture: true\n"
            for name in init_state._STATE_DOCUMENT_NAMES
        }

    def test_failed_postpublication_rollback_preserves_recovery_lock(self):
        root = self.publication_root()
        real_rename = init_state._rename_noreplace
        calls = {"count": 0}

        def fail_rollback(source, destination):
            calls["count"] += 1
            if calls["count"] == 1:
                real_rename(source, destination)
                return
            raise OSError("injected rollback rename failure")

        def reject_postpublication_state():
            raise ValueError("injected post-publication rejection")

        operation = {
            "tool": "fixture",
            "action": "minimal-publication",
        }
        with mock.patch.object(
                init_state, "_rename_noreplace",
                side_effect=fail_rollback):
            with self.assertRaisesRegex(ValueError, "rollback is incomplete"):
                init_state.publish_runtime(
                    root, self.documents(),
                    pre_publish_validator=lambda: None,
                    post_publish_validator=reject_postpublication_state,
                    lock_operation=operation)
        owner = json.loads((
            root / ".cambium/tmp/state-writer.lock/owner.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(operation, owner["operation"])

    def test_empty_runtime_winning_publication_race_is_not_replaced(self):
        root = self.publication_root()
        real_rename = init_state._rename_noreplace

        def competing_empty_runtime(source, destination):
            destination = Path(destination)
            destination.mkdir()
            return real_rename(source, str(destination))

        with mock.patch.object(
                init_state, "_rename_noreplace",
                side_effect=competing_empty_runtime):
            with self.assertRaises(FileExistsError):
                init_state.publish_runtime(
                    root, self.documents())
        runtime = root / ".cambium"
        self.assertTrue(runtime.is_dir())
        self.assertEqual([], list(runtime.iterdir()))
        self.assertEqual([], list(root.glob(".cambium-init-*")))


class RepositoryTargetSnapshotTests(unittest.TestCase):
    def target_root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        (root / "Domain").mkdir(parents=True)
        (root / "Domain/Page.md").write_text("page\n", encoding="utf-8")
        return root

    def test_target_snapshot_rejects_namespace_aliases(self):
        for mutation in ("symlink-parent", "hardlink", "case-alias"):
            with self.subTest(mutation=mutation):
                root = self.target_root()
                if mutation == "symlink-parent":
                    (root / "Alias").symlink_to(
                        root / "Domain", target_is_directory=True)
                    path = "Alias/Missing.md"
                    expected = "symlink"
                elif mutation == "hardlink":
                    os.link(root / "Domain/Page.md",
                            root / "Domain/Linked.md")
                    path = "Domain/Linked.md"
                    expected = "singly-linked"
                else:
                    alias = root / "Domain/page.md"
                    if not alias.exists():
                        continue
                    path = "Domain/page.md"
                    expected = "exactly match"
                with self.assertRaisesRegex(ValueError, expected):
                    kblib.repository_target_snapshot(
                        root, path, suffixes=".md")


class RepositorySnapshotTests(unittest.TestCase):
    def snapshot_root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        (root / ".git").mkdir(parents=True)
        (root / ".cambium/receipts").mkdir(parents=True)
        (root / "Topics").mkdir()
        (root / "Topics/A.md").write_text("alpha\n", encoding="utf-8")
        (root / ".git/index").write_text("git\n", encoding="utf-8")
        (root / ".cambium/receipts/run.jsonl").write_text(
            "runtime\n", encoding="utf-8")
        return root

    def test_snapshot_tracks_repository_bytes_but_excludes_control_and_cache(self):
        root = self.snapshot_root()
        baseline = kblib.repository_snapshot_sha256(root)
        (root / ".git/index").write_text(
            "changed git\n", encoding="utf-8")
        (root / ".cambium/receipts/run.jsonl").write_text(
            "changed runtime\n", encoding="utf-8")
        cache = root / "fixture_package/__pycache__"
        cache.mkdir(parents=True)
        (cache / "sample.synthetic.pyc").write_bytes(b"cache")
        self.assertEqual(baseline, kblib.repository_snapshot_sha256(root))

        topic = root / "Topics/A.md"
        topic.write_text("beta\n", encoding="utf-8")
        changed_content = kblib.repository_snapshot_sha256(root)
        self.assertNotEqual(baseline, changed_content)
        topic.rename(root / "Topics/B.md")
        self.assertNotEqual(
            changed_content, kblib.repository_snapshot_sha256(root))

    def test_snapshot_rejects_symlink_hardlink_and_special_files(self):
        for mutation in ("symlink", "hardlink", "fifo"):
            with self.subTest(mutation=mutation):
                root = self.snapshot_root()
                if mutation == "symlink":
                    target = root / "target.md"
                    target.write_text("target\n", encoding="utf-8")
                    (root / "linked.md").symlink_to(target)
                    expected = "regular file"
                elif mutation == "hardlink":
                    target = root / "target.md"
                    target.write_text("target\n", encoding="utf-8")
                    os.link(target, root / "linked.md")
                    expected = "hard-linked"
                else:
                    os.mkfifo(root / "pipe")
                    expected = "regular file"
                with self.assertRaisesRegex(ValueError, expected):
                    kblib.repository_snapshot_sha256(root)


class DirectoryListingScopeUnitTests(unittest.TestCase):
    def test_scope_reuses_listing_and_always_closes(self):
        with mock.patch.object(
                kblib.os, "listdir", return_value=["entry"]) as listdir:
            kblib._listdir_in_scope("/repo")
            kblib._listdir_in_scope("/repo")
            self.assertEqual(2, listdir.call_count)

            with kblib.directory_listing_scope():
                kblib._listdir_in_scope("/repo")
                kblib._listdir_in_scope("/repo")
                kblib._listdir_in_scope("/repo/other")
            self.assertEqual(4, listdir.call_count)

            with self.assertRaises(RuntimeError):
                with kblib.directory_listing_scope():
                    kblib._listdir_in_scope("/repo")
                    raise RuntimeError("boom")
            kblib._listdir_in_scope("/repo")
            self.assertEqual(6, listdir.call_count)
        self.assertEqual([], kblib._DIRECTORY_LISTING_SCOPE)


class CanonicalRepositoryFileSlowTests(unittest.TestCase):
    def test_exact_spelling_and_symlink_components_are_rejected_on_disk(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Tools").mkdir()
            (root / "Tools/mod0.py").write_text(
                "VALUE = 0\n", encoding="utf-8")
            (root / "link").symlink_to(
                root / "Tools", target_is_directory=True)

            with kblib.directory_listing_scope():
                kblib.canonical_repository_file(root, "Tools/mod0.py")
                with self.assertRaisesRegex(ValueError, "exactly match"):
                    kblib.canonical_repository_file(
                        root, "Tools/MOD0.py")
                with self.assertRaisesRegex(ValueError, "symlink"):
                    kblib.canonical_repository_file(
                        root, "link/mod0.py")


if __name__ == "__main__":
    unittest.main()
