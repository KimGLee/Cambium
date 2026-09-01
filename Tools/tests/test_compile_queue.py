"""Owner-focused tests for deterministic Required Queue materialization.

The compiler's schema, ordering, and diff predicates are tested in process.
One current planning checkpoint owns the adjacent state seam, and one JSON
CLI materialization is the only real subprocess. Replan currentness starts at
a local three-ledger checkpoint. Lock, append, rollback, and interrupted-write
isolation stays in Slow tests.
"""

import contextlib
import copy
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Tools.execution.planning import compile_queue
from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation
import Tools.platform.common.kblib as kblib
from Tools.tests.support.initial_task_plan_fixture import \
    reset_to_initial_task_plan_fixture
from Tools.tests.support.profile_fixture import install_loadable_profile


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
CLI = TOOLS / "compile_queue.py"


def fixture_document(relative):
    return kblib.load_yaml_file(FIXTURE / relative)


def fixture_queue(*, empty=False):
    queue = copy.deepcopy(fixture_document(queue_runtime.QUEUE_PATH))
    if empty:
        queue["required_queue"] = []
        queue["queue_revision"] = 1
        queue["state_revision"] = 0
    return queue


def fixture_coverage():
    return copy.deepcopy(fixture_document(queue_runtime.COVERAGE_PATH))


def batch_spec(coverage, batch_id):
    return next(spec for spec in coverage["batch_specs"]
                if spec["id"] == batch_id)


class CompileQueueContractTests(unittest.TestCase):
    def test_batch_spec_identity_is_unique_at_the_compiler_boundary(self):
        coverage = fixture_coverage()
        parsed = compile_queue._batch_specs(coverage)
        self.assertEqual({"B1", "B2"}, set(parsed))

        duplicate = copy.deepcopy(coverage)
        duplicate["batch_specs"].append(
            copy.deepcopy(duplicate["batch_specs"][0]))
        with self.assertRaisesRegex(ValueError, "repeats batch spec B1"):
            compile_queue._batch_specs(duplicate)

    def test_compile_document_materializes_only_declared_structure(self):
        queue = fixture_queue(empty=True)
        coverage = fixture_coverage()
        first, changed = compile_queue.compile_document(queue, coverage)
        second, repeated_changed = compile_queue.compile_document(
            queue, coverage)
        self.assertTrue(changed)
        self.assertTrue(repeated_changed)
        self.assertEqual(first, second)
        items = {item["id"]: item for item in first["required_queue"]}
        self.assertEqual(["Topics/A.md"], items["B1"]["manifest"])
        self.assertEqual(["B1"], items["B2"]["depends_on"])
        self.assertEqual([1, 2], [items["B1"]["order"], items["B2"]["order"]])

        no_inference = copy.deepcopy(coverage)
        batch_spec(no_inference, "B2")["depends_on"] = []
        no_inference["pages"][1]["prerequisites"] = ["Topics/A.md"]
        compiled, _ = compile_queue.compile_document(queue, no_inference)
        b2 = next(item for item in compiled["required_queue"]
                  if item["id"] == "B2")
        self.assertEqual([], b2["depends_on"])

        bound = copy.deepcopy(coverage)
        spec = batch_spec(bound, "B1")
        spec["work_spec_path"] = ".cambium/work_specs/B1.yaml"
        spec["work_spec_sha256"] = "sha256:" + "a" * 64
        compiled, _ = compile_queue.compile_document(queue, bound)
        b1 = compiled["required_queue"][0]
        self.assertEqual(spec["work_spec_path"], b1["work_spec_path"])
        self.assertEqual(spec["work_spec_sha256"], b1["work_spec_sha256"])

    def test_explicit_dependency_cycle_is_rejected(self):
        coverage = fixture_coverage()
        batch_spec(coverage, "B1")["depends_on"] = ["B2"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            compile_queue.compile_document(fixture_queue(empty=True), coverage)

    def test_same_scope_proposal_changes_only_registered_routing_fields(self):
        current = fixture_coverage()
        allowed = copy.deepcopy(current)
        allowed["pages"][1]["batch"] = "B1"
        allowed["pages"][1]["next_batch"] = "B1"
        self.assertEqual(
            ["Topics/B.md"],
            compile_queue.validate_same_scope_proposal(current, allowed),
        )

        violations = []
        metadata = copy.deepcopy(current)
        metadata["pages"][1]["priority"] = "P0"
        violations.append((metadata, "only batch/next_batch may change"))
        maintenance = copy.deepcopy(current)
        maintenance["maintenance_candidates"] = [{
            "candidate_id": "candidate-sha256:" + "0" * 64,
            "object_path": "Topics/A.md",
        }]
        violations.append((maintenance, "may not change maintenance_candidates"))
        added = copy.deepcopy(current)
        added["pages"].append(copy.deepcopy(added["pages"][0]))
        added["pages"][-1]["path"] = "Topics/C.md"
        violations.append((added, "may not add/remove pages"))
        for proposal, expected in violations:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    compile_queue.validate_same_scope_proposal(
                        current, proposal)

    def test_open_work_spec_change_requires_revalidation_hold(self):
        queue = fixture_queue()
        current = queue["required_queue"][0]
        current.update({
            "state": "open",
            "opened_at": "2026-08-04T01:00:00Z",
            "activation_receipt": "audit-current-admission",
            "transition_receipts": ["audit-open"],
        })
        proposal = copy.deepcopy(queue)
        proposed = proposal["required_queue"][0]
        proposed["work_spec_path"] = ".cambium/work_specs/B1.yaml"
        proposed["work_spec_sha256"] = "sha256:" + "a" * 64

        diff = compile_queue.replan_diff(
            queue, proposal, "sha256:" + "b" * 64)
        self.assertEqual(
            ["work_spec_path", "work_spec_sha256"],
            diff["update_candidates"][0]["changed_fields"],
        )
        self.assertIn("requires a prior update_queue transition",
                      diff["conflicts"][0])

        queue["required_queue"][0]["hold_state"] = "revalidation-required"
        held = compile_queue.replan_diff(
            queue, proposal, "sha256:" + "c" * 64)
        self.assertEqual([], held["conflicts"])

    def test_replan_diff_preserves_terminal_history_and_reports_inflight_removal(self):
        queue = fixture_queue()
        queue["required_queue"][0].update({
            "state": "closed", "closed_at": "2026-08-04T01:00:00Z",
            "transition_receipts": ["audit-close-b1"],
        })
        queue["required_queue"][1].update({
            "state": "open", "opened_at": "2026-08-04T02:00:00Z",
            "transition_receipts": ["audit-open-b2"],
        })
        proposal = copy.deepcopy(queue)
        proposal["required_queue"] = []
        diff = compile_queue.replan_diff(
            queue, proposal, "sha256:" + "d" * 64)
        self.assertEqual(["B1"], diff["preserved_closed_ids"])
        self.assertEqual(["B2"], [row["id"]
                                  for row in diff["remove_candidates"]])
        self.assertIn("in-flight work cannot be removed",
                      diff["conflicts"][0])

    def test_replan_order_fills_around_fixed_history(self):
        queue = {
            "required_queue": [
                {"id": "Q", "state": "queued", "order": 1,
                 "depends_on": []},
                {"id": "H", "state": "closed", "order": 2,
                 "depends_on": []},
            ],
        }
        compiled = [
            {"id": "A", "state": "queued", "order": 1,
             "depends_on": []},
            {"id": "Q", "state": "queued", "order": 2,
             "depends_on": ["A"]},
        ]
        result = compile_queue._assign_replan_orders(queue, compiled)
        self.assertEqual(
            {"A": 1, "Q": 3},
            {item["id"]: item["order"] for item in result},
        )
        self.assertEqual(2, queue["required_queue"][1]["order"])


class CompileQueueCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._template_tmp = tempfile.TemporaryDirectory()
        cls.template_root = Path(cls._template_tmp.name) / "repo"
        shutil.copytree(FIXTURE, cls.template_root)
        install_loadable_profile(cls.template_root)
        reset_to_initial_task_plan_fixture(cls.template_root)

    @classmethod
    def tearDownClass(cls):
        cls._template_tmp.cleanup()

    @staticmethod
    def load(root, relative):
        return kblib.load_yaml_file(root / relative)

    def command(self, root, *arguments):
        return subprocess.run(
            [sys.executable, str(CLI), str(root), *arguments],
            text=True, capture_output=True, check=False,
        )

    def test_cli_json_materializes_one_current_planning_checkpoint(self):
        root = self.template_root
        checkpoint = runtime_validation.validate_runtime(
            root, allow_unmaterialized_queue=True)
        self.assertEqual([], checkpoint["errors"])
        self.assertEqual([], checkpoint["queue"]["required_queue"])
        self.assertIsNone(checkpoint["progress"]["initial_queue_receipt"])

        queue = self.load(root, queue_runtime.QUEUE_PATH)
        result = self.command(
            root, "--apply", "--actor-role", "integrator",
            "--expected-queue-revision", str(queue["queue_revision"]),
            "--expected-sha256",
            kblib.sha256_file(root / queue_runtime.QUEUE_PATH),
            "--json",
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        receipts = json.loads(result.stdout)
        self.assertEqual(1, len(receipts), receipts)
        self.assertEqual("queue_structure", receipts[0]["check"])
        self.assertEqual(
            [], compile_queue.current_receipt_errors(
                receipts[0], root=str(root)))

        result_state = runtime_validation.validate_runtime(root)
        self.assertEqual([], result_state["errors"])
        self.assertEqual(
            ["B1", "B2"],
            [item["id"] for item in result_state["queue"]["required_queue"]],
        )
        progress = result_state["progress"]
        self.assertTrue(progress["initial_task_plan_receipt"])
        self.assertEqual(
            receipts[0]["receipt_id"], progress["initial_queue_receipt"])


class CompileQueueReplanCurrentnessIntegrationTests(unittest.TestCase):
    """Exercise diff consumption without Profile or runtime construction."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        for relative in (
                queue_runtime.COVERAGE_PATH,
                queue_runtime.QUEUE_PATH,
                queue_runtime.PROGRESS_PATH):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(FIXTURE / relative, target)
        (self.root / ".cambium/tmp").mkdir(parents=True, exist_ok=True)
        patches = (
            mock.patch.object(
                compile_queue.runtime_validation, "validate_runtime",
                return_value={"errors": []}),
            mock.patch.object(
                queue_runtime, "runtime_authority_context",
                return_value={}),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def load(self, relative):
        return kblib.load_yaml_file(self.root / relative)

    def state_bytes(self):
        return {
            relative: (self.root / relative).read_bytes()
            for relative in (
                queue_runtime.COVERAGE_PATH,
                queue_runtime.QUEUE_PATH,
                queue_runtime.PROGRESS_PATH,
            )
        }

    def invoke(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = compile_queue.main([str(self.root), *arguments])
        return code, output.getvalue()

    def write_proposal(self, coverage):
        relative = ".cambium/deltas/replans/A-REPLAN.coverage.yaml"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kblib.canonical_yaml(coverage), encoding="utf-8")
        return relative

    def test_consumed_replan_diff_is_bound_to_current_proposal_bytes(self):
        coverage = self.load(queue_runtime.COVERAGE_PATH)
        batch_spec(coverage, "B2")["family"] = "First proposal"
        proposal = self.write_proposal(coverage)
        code, output = self.invoke(
            "--coverage-proposal", proposal,
            "--output", ".cambium/tmp/replan.yaml")
        self.assertEqual(0, code, output)

        changed = self.load(proposal)
        batch_spec(changed, "B2")["family"] = "Changed after projection"
        self.write_proposal(changed)
        queue = self.load(queue_runtime.QUEUE_PATH)
        before = self.state_bytes()
        code, output = self.invoke(
            "--coverage-proposal", proposal,
            "--apply-replan", "--amendment-id", "A-REPLAN",
            "--replan-diff", ".cambium/tmp/replan.yaml",
            "--expected-queue-revision", str(queue["queue_revision"]),
            "--expected-state-revision", str(queue["state_revision"]),
            "--expected-sha256",
            kblib.sha256_file(self.root / queue_runtime.QUEUE_PATH),
            "--expected-coverage-sha256",
            kblib.sha256_file(self.root / queue_runtime.COVERAGE_PATH),
            "--expected-progress-sha256",
            kblib.sha256_file(self.root / queue_runtime.PROGRESS_PATH),
            "--actor-role", "integrator",
        )
        self.assertEqual(1, code, output)
        self.assertIn("does not match the current Coverage inputs", output)
        self.assertEqual(before, self.state_bytes())


class CompileQueueTransactionRecoverySlowTests(unittest.TestCase):
    """Exercise this writer's transaction boundary without a full runtime."""

    def setUp(self):
        patches = (
            mock.patch.object(
                compile_queue.runtime_validation, "validate_runtime",
                return_value={"errors": []}),
            mock.patch.object(
                queue_runtime, "runtime_authority_validation_kwargs",
                return_value={}),
            mock.patch.object(
                queue_runtime, "runtime_authority_lock_fields",
                return_value={}),
            mock.patch.object(
                queue_runtime, "require_runtime_authority_current",
                return_value=None),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.root = self.fresh_root()

    def fresh_root(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "repo"
        documents = {
            queue_runtime.COVERAGE_PATH: {
                "schema_version": 1,
                "updated_at": "2026-08-04T00:00:00Z",
                "pages": [],
                "batch_specs": [],
                "maintenance_candidates": [],
            },
            queue_runtime.QUEUE_PATH: {
                "schema_version": 1,
                "task_id": "fixture-task",
                "queue_revision": 1,
                "state_revision": 0,
                "required_queue": [],
            },
            queue_runtime.PROGRESS_PATH: {
                "schema_version": 1,
                "task_id": "fixture-task",
                "queue_revision": 1,
                "queue_state_revision": 0,
            },
        }
        for relative, document in documents.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                kblib.canonical_yaml(document), encoding="utf-8")
        (root / ".cambium/tmp").mkdir(parents=True, exist_ok=True)
        (root / runtime_paths_path()).parent.mkdir(
            parents=True, exist_ok=True)
        return root

    def transaction_fixture(self, root):
        paths = {
            "coverage": str(root / queue_runtime.COVERAGE_PATH),
            "queue": str(root / queue_runtime.QUEUE_PATH),
            "progress": str(root / queue_runtime.PROGRESS_PATH),
        }
        before = {
            name: Path(path).read_text(encoding="utf-8")
            for name, path in paths.items()
        }
        after = copy.deepcopy(before)
        coverage = kblib.parse_yaml_subset(after["coverage"])
        coverage["updated_at"] = "2026-08-05T00:00:00Z"
        after["coverage"] = kblib.canonical_yaml(coverage)
        queue = kblib.parse_yaml_subset(after["queue"])
        queue["queue_revision"] += 1
        after["queue"] = kblib.canonical_yaml(queue)
        progress = kblib.parse_yaml_subset(after["progress"])
        progress["queue_revision"] += 1
        after["progress"] = kblib.canonical_yaml(progress)

        common = {
            "task_id": queue["task_id"],
            "transaction_id": "txn-test-replan",
            "amendment_id": "A-TEST",
            "before_required_queue_sha256":
                kblib.sha256_bytes(before["queue"]),
            "after_required_queue_sha256":
                kblib.sha256_bytes(after["queue"]),
            "before_coverage_sha256":
                kblib.sha256_bytes(before["coverage"]),
            "after_coverage_sha256":
                kblib.sha256_bytes(after["coverage"]),
            "before_progress_sha256":
                kblib.sha256_bytes(before["progress"]),
            "after_progress_sha256":
                kblib.sha256_bytes(after["progress"]),
            "before_queue_revision": queue["queue_revision"] - 1,
            "after_queue_revision": queue["queue_revision"],
            "queue_state_revision": queue["state_revision"],
            "actor_role": "integrator",
        }
        commit = kblib.make_receipt(
            compile_queue.TOOL, compile_queue.TOOL_VERSION,
            "queue_replan", compile_queue.QUEUE_PATH, "pass",
            "test replan commit", 1,
            receipt_type_id=compile_queue.RECEIPT_TYPE_ID,
        )
        commit.update(common)
        commit["transaction_phase"] = "commit"
        prepare = kblib.make_receipt(
            compile_queue.TOOL, compile_queue.TOOL_VERSION,
            "queue_replan_prepare", compile_queue.QUEUE_PATH, "candidate",
            "test replan prepare", 2,
            receipt_type_id=compile_queue.RECEIPT_TYPE_ID,
        )
        prepare.update(common)
        prepare["transaction_phase"] = "prepare"
        abort = kblib.make_receipt(
            compile_queue.TOOL, compile_queue.TOOL_VERSION,
            "queue_replan_abort", compile_queue.QUEUE_PATH, "fail",
            "test replan abort", 3,
            receipt_type_id=compile_queue.RECEIPT_TYPE_ID,
        )
        abort.update(common)
        abort["transaction_phase"] = "abort"
        operation = {
            "tool": compile_queue.TOOL,
            "action": "apply-replan",
            "before_coverage_sha256": common["before_coverage_sha256"],
            "before_required_queue_sha256":
                common["before_required_queue_sha256"],
            "before_progress_sha256": common["before_progress_sha256"],
            "planned_after_coverage_sha256":
                common["after_coverage_sha256"],
            "planned_after_required_queue_sha256":
                common["after_required_queue_sha256"],
            "planned_after_progress_sha256":
                common["after_progress_sha256"],
            "receipt_id": prepare["receipt_id"],
            "prepare_receipt_id": prepare["receipt_id"],
            "commit_receipt_id": commit["receipt_id"],
            "abort_receipt_id": abort["receipt_id"],
            "receipt_path": runtime_paths_path(),
        }
        return paths, before, after, prepare, commit, abort, operation, {}

    def commit(self, root, fixture):
        paths, before, after, prepare, commit, abort, operation, authority = \
            fixture
        compile_queue._commit_state(
            str(root), paths, before, after,
            ("coverage", "queue", "progress"),
            root / runtime_paths_path(), prepare, commit, abort,
            operation, authority,
        )

    def test_clean_rollback_restores_every_state_byte_and_unlocks(self):
        fixture = self.transaction_fixture(self.root)
        paths, before, after = fixture[:3]
        original = kblib.atomic_write_text
        failed = {"progress": False}

        def fail_progress(path, text, validator=None):
            if (path == paths["progress"] and text == after["progress"] and
                    not failed["progress"]):
                failed["progress"] = True
                raise OSError("injected progress write failure")
            return original(path, text, validator=validator)

        with mock.patch.object(
                kblib, "atomic_write_text", side_effect=fail_progress):
            with self.assertRaisesRegex(OSError, "progress write failure"):
                self.commit(self.root, fixture)
        for name, path in paths.items():
            self.assertEqual(before[name], Path(path).read_text(encoding="utf-8"))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_locked_prevalidation_cas_rejection_writes_nothing(self):
        fixture = self.transaction_fixture(self.root)
        paths, before = fixture[:2]
        with mock.patch.object(
                compile_queue.runtime_validation, "validate_runtime",
                return_value={"errors": ["injected concurrent drift"]}):
            with self.assertRaisesRegex(ValueError,
                                        "runtime changed before write"):
                self.commit(self.root, fixture)
        for name, path in paths.items():
            self.assertEqual(before[name], Path(path).read_text(encoding="utf-8"))
        self.assertFalse(
            (self.root / ".cambium/tmp/state-writer.lock").exists())

    def test_incomplete_rollback_retains_current_recovery_lock(self):
        fixture = self.transaction_fixture(self.root)
        paths, before, after = fixture[:3]
        original = kblib.atomic_write_text
        failed = {"progress": False}

        def fail_write_and_restore(path, text, validator=None):
            if (path == paths["progress"] and text == after["progress"] and
                    not failed["progress"]):
                failed["progress"] = True
                raise OSError("injected progress write failure")
            if (failed["progress"] and path == paths["coverage"] and
                    text == before["coverage"]):
                raise OSError("injected Coverage rollback failure")
            return original(path, text, validator=validator)

        with mock.patch.object(
                kblib, "atomic_write_text", side_effect=fail_write_and_restore):
            with self.assertRaisesRegex(ValueError, "recovery was incomplete"):
                self.commit(self.root, fixture)
        lock = self.root / ".cambium/tmp/state-writer.lock/owner.json"
        self.assertTrue(lock.is_file())
        owner = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual("apply-replan", owner["operation"]["action"])
        self.assertEqual(
            kblib.sha256_bytes(after["coverage"]),
            kblib.sha256_file(paths["coverage"]),
        )

    def test_uncertain_commit_append_variants_retain_lock_and_evidence(self):
        for mode in ("durable-then-error", "partial-write"):
            root = self.root if mode == "durable-then-error" else \
                self.fresh_root()
            fixture = self.transaction_fixture(root)
            paths, before, _after, _prepare, commit = fixture[:5]
            receipt_path = root / runtime_paths_path()
            with self.subTest(mode=mode):
                if mode == "durable-then-error":
                    real_append = kblib.write_receipts

                    def append_then_fail(path, receipts, **kwargs):
                        real_append(path, receipts, **kwargs)
                        if any(row.get("receipt_id") == commit["receipt_id"]
                               for row in receipts):
                            raise OSError("error after durable commit")

                    patcher = mock.patch.object(
                        kblib, "write_receipts", side_effect=append_then_fail)
                else:
                    real_write = kblib.os.write
                    marker = commit["receipt_id"].encode("utf-8")

                    def truncate_commit(fd, data):
                        payload = bytes(data)
                        if marker in payload:
                            fragment = payload[:max(1, len(payload) // 2)]
                            real_write(fd, fragment)
                            return len(fragment)
                        return real_write(fd, payload)

                    patcher = mock.patch.object(
                        kblib.os, "write", side_effect=truncate_commit)
                with patcher:
                    with self.assertRaisesRegex(
                            ValueError, "recovery was incomplete"):
                        self.commit(root, fixture)
                for name, path in paths.items():
                    self.assertEqual(
                        before[name], Path(path).read_text(encoding="utf-8"))
                self.assertIn(commit["receipt_id"].encode("utf-8"),
                              receipt_path.read_bytes())
                self.assertTrue((
                    root / ".cambium/tmp/state-writer.lock/owner.json"
                ).is_file())

    def test_prepare_and_abort_append_boundaries_choose_unlock_or_lock(self):
        for mode in ("prepare-absent", "abort-absent"):
            root = self.root if mode == "prepare-absent" else self.fresh_root()
            fixture = self.transaction_fixture(root)
            paths, before, after, prepare, _commit, abort = fixture[:6]
            real_append = kblib.write_receipts
            real_atomic = kblib.atomic_write_text
            failed = {"progress": False}

            def guarded_append(path, receipts, **kwargs):
                ids = {row.get("receipt_id") for row in receipts}
                target = (prepare["receipt_id"] if mode == "prepare-absent"
                          else abort["receipt_id"])
                if target in ids:
                    raise OSError("injected %s append failure" % mode)
                return real_append(path, receipts, **kwargs)

            def fail_progress(path, text, validator=None):
                if (mode == "abort-absent" and
                        path == paths["progress"] and
                        text == after["progress"] and
                        not failed["progress"]):
                    failed["progress"] = True
                    raise OSError("injected state failure")
                return real_atomic(path, text, validator=validator)

            with self.subTest(mode=mode), \
                    mock.patch.object(
                        kblib, "write_receipts", side_effect=guarded_append), \
                    mock.patch.object(
                        kblib, "atomic_write_text", side_effect=fail_progress):
                if mode == "prepare-absent":
                    with self.assertRaisesRegex(OSError, "prepare-absent"):
                        self.commit(root, fixture)
                else:
                    with self.assertRaisesRegex(
                            ValueError, "recovery was incomplete"):
                        self.commit(root, fixture)
                for name, path in paths.items():
                    self.assertEqual(
                        before[name], Path(path).read_text(encoding="utf-8"))
                lock = root / ".cambium/tmp/state-writer.lock"
                self.assertEqual(mode == "abort-absent", lock.exists())


def runtime_paths_path():
    return ".cambium/receipts/queue-structure.jsonl"


if __name__ == "__main__":
    unittest.main()
