import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import init_state
import kblib


class ReceiptSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".cambium/receipts").mkdir(parents=True)
        (self.root / ".cambium/state").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_receipt_append_rejects_hard_link_to_authoritative_state(self):
        state = self.root / ".cambium/state/required_queue.yaml"
        state.write_text("required_queue: []\n", encoding="utf-8")
        receipt = self.root / ".cambium/receipts/queue.jsonl"
        os.link(state, receipt)
        before = state.read_bytes()

        with self.assertRaisesRegex(ValueError, "hard link"):
            kblib.write_receipts(receipt, [{"receipt_id": "r1"}])

        self.assertEqual(before, state.read_bytes())
        with self.assertRaisesRegex(ValueError, "hard link"):
            kblib.managed_repository_path(
                self.root, ".cambium/receipts/queue.jsonl",
                ".cambium/receipts", must_exist=True,
            )

    def test_receipt_append_rejects_final_symlink(self):
        outside = self.root / "outside.jsonl"
        outside.write_text("", encoding="utf-8")
        receipt = self.root / ".cambium/receipts/queue.jsonl"
        receipt.symlink_to(outside)

        with self.assertRaises(OSError):
            kblib.write_receipts(receipt, [{"receipt_id": "r1"}])

        self.assertEqual("", outside.read_text(encoding="utf-8"))

    def test_receipt_append_rejects_symlinked_parent(self):
        receipts = self.root / ".cambium/receipts"
        receipts.rmdir()
        outside = self.root / "outside-receipts"
        outside.mkdir()
        receipts.symlink_to(outside, target_is_directory=True)

        with self.assertRaises(OSError):
            kblib.write_receipts(receipts / "queue.jsonl",
                                  [{"receipt_id": "r1"}])

        self.assertFalse((outside / "queue.jsonl").exists())

    def test_receipt_append_is_complete_jsonl(self):
        receipt = self.root / ".cambium/receipts/queue.jsonl"
        kblib.write_receipts(receipt, [{"receipt_id": "r1"}])
        kblib.write_receipts(receipt, [{"receipt_id": "r2"}])
        records = [json.loads(line) for line in
                   receipt.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["r1", "r2"],
                         [record["receipt_id"] for record in records])

    def test_exact_append_observation_ignores_unrelated_concurrent_record(self):
        receipt = self.root / ".cambium/receipts/queue.jsonl"
        own = {"receipt_id": "own"}
        external = {"receipt_id": "external"}
        before = kblib.receipt_append_observation(receipt, [own])

        kblib.write_receipts(receipt, [external])

        after = kblib.receipt_append_observation(receipt, [own])
        self.assertEqual("absent",
                         kblib.receipt_append_outcome(before, after))
        self.assertEqual(
            [external],
            [json.loads(line) for line in
             receipt.read_text(encoding="utf-8").splitlines()],
        )

    def test_exact_append_observation_detects_own_record_among_concurrency(self):
        receipt = self.root / ".cambium/receipts/queue.jsonl"
        own = {"receipt_id": "own"}
        external = {"receipt_id": "external"}
        before = kblib.receipt_append_observation(receipt, [own])

        kblib.write_receipts(receipt, [own])
        kblib.write_receipts(receipt, [external])

        after = kblib.receipt_append_observation(receipt, [own])
        self.assertEqual("present",
                         kblib.receipt_append_outcome(before, after))
        self.assertEqual(
            ["own", "external"],
            [json.loads(line)["receipt_id"] for line in
             receipt.read_text(encoding="utf-8").splitlines()],
        )

    def test_exact_own_record_with_any_truncated_tail_is_uncertain(self):
        receipt = self.root / ".cambium/receipts/queue.jsonl"
        own = {"receipt_id": "own"}
        before = kblib.receipt_append_observation(receipt, [own])
        kblib.write_receipts(receipt, [own])
        with open(receipt, "ab") as handle:
            handle.write(b'{"receipt_id":"truncated"')

        after = kblib.receipt_append_observation(receipt, [own])
        self.assertEqual("uncertain",
                         kblib.receipt_append_outcome(before, after))

    def test_exclusive_append_never_overwrites_concurrent_creator(self):
        receipt = self.root / ".cambium/receipts/canonical.jsonl"
        own = {"receipt_id": "own"}
        external = {"receipt_id": "external"}
        before = kblib.receipt_append_observation(receipt, [own])
        kblib.write_receipts(receipt, [external])

        with self.assertRaises(FileExistsError):
            kblib.write_receipts(receipt, [own], exclusive=True)

        after = kblib.receipt_append_observation(receipt, [own])
        self.assertEqual("absent",
                         kblib.receipt_append_outcome(before, after))
        self.assertEqual(
            [external],
            [json.loads(line) for line in
             receipt.read_text(encoding="utf-8").splitlines()],
        )

    def test_concurrent_process_appenders_preserve_every_record(self):
        receipt = self.root / ".cambium/receipts/concurrent.jsonl"
        program = """
import sys
sys.path.insert(0, sys.argv[1])
import kblib
path, prefix = sys.argv[2], sys.argv[3]
for index in range(40):
    kblib.write_receipts(path, [{"receipt_id": "%s-%02d" % (prefix, index)}])
"""
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", program, str(TOOLS), str(receipt),
                 "writer-%d" % writer],
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

    def test_receipt_append_cannot_target_runtime_authority(self):
        targets = (
            self.root / ".cambium/state/required_queue.yaml",
            self.root / ".cambium/deltas/B1.yaml",
            self.root / ".cambium/tmp/state-writer.lock/owner.json",
        )
        for target in targets:
            with self.subTest(target=target):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("sentinel\n", encoding="utf-8")
                before = target.read_bytes()
                with self.assertRaisesRegex(ValueError, r"\.cambium/receipts"):
                    kblib.write_receipts(target, [{"receipt_id": "attack"}])
                self.assertEqual(before, target.read_bytes())

    def test_receipt_append_rejects_alias_into_runtime_authority(self):
        state = self.root / ".cambium/state/required_queue.yaml"
        state.write_text("sentinel\n", encoding="utf-8")
        alias_parent = self.root / "receipt-alias"
        alias_parent.symlink_to(self.root / ".cambium/state",
                                target_is_directory=True)
        alias = alias_parent / "required_queue.yaml"
        before = state.read_bytes()
        with self.assertRaisesRegex(ValueError, r"\.cambium/receipts"):
            kblib.write_receipts(alias, [{"receipt_id": "attack"}])
        self.assertEqual(before, state.read_bytes())


class DurableReplaceTests(unittest.TestCase):
    def test_cross_directory_replace_fsyncs_destination_then_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_parent = root / "source"
            destination_parent = root / "destination"
            source_parent.mkdir()
            destination_parent.mkdir()
            source = source_parent / "delta.yaml"
            destination = destination_parent / "delta.yaml"
            source.write_text("batch: B1\n", encoding="utf-8")
            events = []
            opened = {}
            real_replace = kblib.os.replace
            real_open = kblib.os.open
            real_fsync = kblib.os.fsync

            def observed_replace(src, dst):
                events.append(("replace", os.path.realpath(src),
                               os.path.realpath(dst)))
                return real_replace(src, dst)

            def observed_open(path, flags, *args):
                fd = real_open(path, flags, *args)
                opened[fd] = os.path.realpath(path)
                return fd

            def observed_fsync(fd):
                events.append(("fsync", opened[fd]))
                return real_fsync(fd)

            with mock.patch.object(kblib.os, "replace",
                                   side_effect=observed_replace), \
                    mock.patch.object(kblib.os, "open",
                                      side_effect=observed_open), \
                    mock.patch.object(kblib.os, "fsync",
                                      side_effect=observed_fsync):
                kblib.durable_replace(source, destination)

            self.assertEqual("replace", events[0][0])
            self.assertEqual([
                ("fsync", os.path.realpath(destination_parent)),
                ("fsync", os.path.realpath(source_parent)),
            ], events[1:])
            self.assertFalse(source.exists())
            self.assertEqual("batch: B1\n",
                             destination.read_text(encoding="utf-8"))

    def test_directory_fsync_failure_is_reported_after_atomic_rename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source/delta.yaml"
            destination = root / "destination/delta.yaml"
            source.parent.mkdir()
            destination.parent.mkdir()
            source.write_text("batch: B1\n", encoding="utf-8")
            with mock.patch.object(
                    kblib.os, "fsync",
                    side_effect=OSError("injected directory fsync failure")):
                with self.assertRaisesRegex(OSError, "directory fsync"):
                    kblib.durable_replace(source, destination)
            self.assertFalse(source.exists())
            self.assertTrue(destination.is_file())


class RuntimeWriteLockTests(unittest.TestCase):
    def test_lock_is_exclusive_and_reusable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".cambium/tmp").mkdir(parents=True)
            with kblib.runtime_write_lock(root) as lock_path:
                self.assertTrue(Path(lock_path).is_dir())
                owner = json.loads(
                    (Path(lock_path) / "owner.json").read_text(encoding="utf-8")
                )
                self.assertEqual("state-writer", owner["lock_name"])
                self.assertEqual(os.getpid(), owner["pid"])
                self.assertRegex(owner["created_at"], r"^\d{4}-\d{2}-\d{2}T")
                with self.assertRaises(kblib.RuntimeStateLockedError):
                    with kblib.runtime_write_lock(root):
                        pass
            self.assertFalse(Path(lock_path).exists())
            with kblib.runtime_write_lock(root):
                pass

    def test_escaping_error_preserves_lock_until_recovery_is_proven(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".cambium/tmp").mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, "partial write"):
                with kblib.runtime_write_lock(
                        root, owner_metadata={"tool": "fixture"}) as lease:
                    lock_path = Path(lease)
                    raise RuntimeError("partial write")
            self.assertTrue(lock_path.is_dir())
            owner = json.loads(
                (lock_path / "owner.json").read_text(encoding="utf-8")
            )
            self.assertEqual("fixture", owner["operation"]["tool"])
            with self.assertRaises(kblib.RuntimeStateLockedError):
                with kblib.runtime_write_lock(root):
                    pass
            (lock_path / "owner.json").unlink()
            lock_path.rmdir()

    def test_proven_rollback_may_clear_lock_while_error_propagates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".cambium/tmp").mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                with kblib.runtime_write_lock(root) as lease:
                    lock_path = Path(lease)
                    lease.mark_reconciled()
                    raise RuntimeError("rolled back")
            self.assertFalse(lock_path.exists())

    def test_proven_prewrite_rejection_clears_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".cambium/tmp").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "stale preflight"):
                with kblib.runtime_write_lock(root) as lease:
                    lock_path = Path(lease)
                    with kblib.no_authoritative_write_guard(lease):
                        raise ValueError("stale preflight")
            self.assertFalse(lock_path.exists())

    def test_hard_process_exit_leaves_restart_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".cambium/tmp").mkdir(parents=True)
            program = (
                "import os,sys; "
                "sys.path.insert(0, sys.argv[1]); "
                "import kblib; "
                "cm=kblib.runtime_write_lock(sys.argv[2], "
                "owner_metadata={'tool':'hard-exit-fixture',"
                "'before_required_queue_sha256':'sha256:'+'0'*64,"
                "'planned_after_required_queue_sha256':'sha256:'+'1'*64}); "
                "cm.__enter__(); os._exit(23)"
            )
            child = subprocess.run(
                [sys.executable, "-c", program, str(TOOLS), str(root)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, check=False,
            )
            self.assertEqual(23, child.returncode, child.stdout)

            lock_path = root / ".cambium/tmp/state-writer.lock"
            self.assertTrue(lock_path.is_dir())
            owner = json.loads(
                (lock_path / "owner.json").read_text(encoding="utf-8")
            )
            self.assertEqual("hard-exit-fixture", owner["operation"]["tool"])
            self.assertIn("before_required_queue_sha256", owner["operation"])
            self.assertIn(
                "planned_after_required_queue_sha256", owner["operation"])
            with self.assertRaises(kblib.RuntimeStateLockedError):
                with kblib.runtime_write_lock(root):
                    pass


class InitPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        (self.root / "profiles/sample").mkdir(parents=True)
        (self.root / "profiles/sample/profile.md").write_text(
            "# Profile\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n", encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def command(self):
        return [
            sys.executable, str(TOOLS / "init_state.py"), str(self.root),
            "--task-id", "new-task", "--objective",
            "Exercise safe runtime publication", "--exclude",
            "Do not create Required work", "--scope-version", "s1",
            "--completion-semantics", "build",
            "--standards-version", "3.0.0", "--profile-manifest",
            "profiles/sample/profile.md", "--at", "2026-08-04T00:00:00Z",
            "--apply",
        ]

    def test_competing_initializers_publish_exactly_one_complete_tree(self):
        first = subprocess.Popen(
            self.command(), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        second = subprocess.Popen(
            self.command(), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        first_output, _ = first.communicate()
        second_output, _ = second.communicate()
        self.assertEqual([0, 1], sorted((first.returncode, second.returncode)),
                         first_output + "\n" + second_output)

        runtime = self.root / ".cambium"
        self.assertEqual(
            {"state", "work_specs", "deltas", "receipts", "reports", "tmp"},
            {entry.name for entry in runtime.iterdir()},
        )
        state_names = {entry.name for entry in (runtime / "state").iterdir()}
        self.assertEqual({
            "coverage_ledger.yaml", "required_queue.yaml",
            "progress_ledger.yaml",
        }, state_names)
        coverage = kblib.load_yaml_file(runtime / "state/coverage_ledger.yaml")
        self.assertEqual([], coverage["batch_specs"])
        self.assertEqual([], list(self.root.glob(".cambium-init-*")))

    def test_staging_write_failure_leaves_no_runtime_or_staging_tree(self):
        arguments = SimpleNamespace(
            task_id="new-task", scope_version="s1", standards_version="3.0.0",
            profile_manifest="profiles/sample/profile.md", at="2026-08-04T00:00:00Z",
            contract_version="c1", concurrency_cap=2,
            completion_semantics="build",
            objective="Exercise safe runtime publication",
            exclusions=["Do not create Required work"],
        )
        documents = init_state.build_documents(arguments)
        real_write = kblib.atomic_write_text
        calls = []

        def fail_second(path, text, validator=None):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("injected staging failure")
            return real_write(path, text, validator=validator)

        with mock.patch.object(init_state.kblib, "atomic_write_text",
                               side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected staging failure"):
                init_state.publish_runtime(str(self.root), documents)

        self.assertFalse((self.root / ".cambium").exists())
        self.assertEqual([], list(self.root.glob(".cambium-init-*")))

    def test_empty_runtime_winning_publication_race_is_never_replaced(self):
        arguments = SimpleNamespace(
            task_id="new-task", scope_version="s1", standards_version="3.0.0",
            profile_manifest="profiles/sample/profile.md",
            at="2026-08-04T00:00:00Z", contract_version="c1",
            concurrency_cap=2, completion_semantics="build",
            objective="Exercise safe runtime publication",
            exclusions=["Do not create Required work"],
        )
        documents = init_state.build_documents(arguments)
        real_rename_noreplace = init_state._rename_noreplace

        def competing_empty_runtime(source, destination):
            destination = Path(destination)
            destination.mkdir()
            return real_rename_noreplace(source, str(destination))

        with mock.patch.object(
                init_state, "_rename_noreplace",
                side_effect=competing_empty_runtime):
            with self.assertRaises(FileExistsError):
                init_state.publish_runtime(str(self.root), documents)

        runtime = self.root / ".cambium"
        self.assertTrue(runtime.is_dir())
        self.assertEqual([], list(runtime.iterdir()))
        self.assertEqual([], list(self.root.glob(".cambium-init-*")))

    def test_invalid_timestamp_is_rejected_before_publication(self):
        command = self.command()
        command[command.index("--at") + 1] = "nonsense"
        completed = subprocess.run(
            command, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("timezone-aware RFC 3339", completed.stdout)
        self.assertFalse((self.root / ".cambium").exists())
        self.assertEqual([], list(self.root.glob(".cambium-init-*")))

    def test_missing_or_invalid_task_contract_never_publishes(self):
        cases = []
        missing = self.command()
        objective_index = missing.index("--objective")
        del missing[objective_index:objective_index + 2]
        cases.append(("missing objective", missing))
        blank = self.command()
        blank[blank.index("--objective") + 1] = ""
        cases.append(("blank objective", blank))
        duplicate = self.command() + ["--exclude", "Do not create Required work"]
        cases.append(("duplicate exclusion", duplicate))
        empty_exclusion = self.command() + ["--exclude", ""]
        cases.append(("empty exclusion", empty_exclusion))

        for label, command in cases:
            with self.subTest(label=label):
                completed = subprocess.run(
                    command, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False,
                )
                self.assertNotEqual(0, completed.returncode, completed.stdout)
                self.assertFalse((self.root / ".cambium").exists())
                self.assertEqual([], list(self.root.glob(".cambium-init-*")))

    def test_preexisting_empty_namespace_is_not_replaced(self):
        (self.root / ".cambium").mkdir()
        completed = subprocess.run(
            self.command(), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertEqual([], list((self.root / ".cambium").iterdir()))
        self.assertIn("existing_runtime_summary=unavailable", completed.stdout)
        self.assertIn("Tools/check_queue.py", completed.stdout)
        self.assertIn("--resume-status", completed.stdout)


class RepositorySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        (self.root / ".git").mkdir(parents=True)
        (self.root / ".cambium/receipts").mkdir(parents=True)
        (self.root / "Topics").mkdir()
        (self.root / "Topics/A.md").write_text("alpha\n", encoding="utf-8")
        (self.root / ".git/index").write_text("git\n", encoding="utf-8")
        (self.root / ".cambium/receipts/run.jsonl").write_text(
            "runtime\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_tracks_paths_and_content_but_excludes_control_state(self):
        baseline = kblib.repository_snapshot_sha256(self.root)
        (self.root / ".git/index").write_text("changed git\n", encoding="utf-8")
        (self.root / ".cambium/receipts/run.jsonl").write_text(
            "changed runtime\n", encoding="utf-8")
        self.assertEqual(baseline, kblib.repository_snapshot_sha256(self.root))

        topic = self.root / "Topics/A.md"
        topic.write_text("beta\n", encoding="utf-8")
        changed_content = kblib.repository_snapshot_sha256(self.root)
        self.assertNotEqual(baseline, changed_content)
        topic.rename(self.root / "Topics/B.md")
        self.assertNotEqual(
            changed_content, kblib.repository_snapshot_sha256(self.root))

    def test_snapshot_rejects_symlinked_content(self):
        target = self.root / "target.md"
        target.write_text("target\n", encoding="utf-8")
        (self.root / "linked.md").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "regular file"):
            kblib.repository_snapshot_sha256(self.root)

    def test_snapshot_rejects_hard_linked_content(self):
        target = self.root / "target.md"
        target.write_text("target\n", encoding="utf-8")
        os.link(target, self.root / "linked.md")
        with self.assertRaisesRegex(ValueError, "hard-linked"):
            kblib.repository_snapshot_sha256(self.root)

    def test_snapshot_rejects_special_file(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaisesRegex(ValueError, "regular file"):
            kblib.repository_snapshot_sha256(self.root)


if __name__ == "__main__":
    unittest.main()
