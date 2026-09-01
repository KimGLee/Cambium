"""Architectural regression tests for the shared AuditPlan resolver boundary."""

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime  # noqa: E402
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime  # noqa: E402
import Tools.execution.audit.complete_audit_receipt as complete_audit_receipt  # noqa: E402
import Tools.execution.audit.record_batch_page_review as record_batch_page_review  # noqa: E402
import Tools.execution.audit.record_substantive_review as record_substantive_review  # noqa: E402
import Tools.execution.task_runtime.runtime_paths as runtime_paths  # noqa: E402


PLAN_PATH = runtime_paths.AUDIT_PLAN_ROOT + "/audit-plan-test.yaml"
PLAN_SHA256 = "sha256:" + "a" * 64


class AuditPlanLoaderUnificationTests(unittest.TestCase):

    def setUp(self):
        self.plan = {
            "plan_id": "audit-plan-test",
            "obligations": [{"due_stage": "pre-merge"}],
        }
        self.item = {"id": "B001", "manifest": ["Topics/Page.md"]}
        self.result = {
            "root": "/repo",
            "queue": {
                "task_id": "task-test",
                "queue_revision": 99,
                "state_revision": 100,
            },
            "queue_sha256": "sha256:" + "b" * 64,
        }
        self.resolved = {
            "audit_plan_id": self.plan["plan_id"],
            "audit_plan_path": PLAN_PATH,
            "audit_plan_sha256": PLAN_SHA256,
            "plan": self.plan,
            "obligations": tuple(self.plan["obligations"]),
        }

    def test_stage_resolver_rejects_a_different_requested_plan_path(self):
        with mock.patch.object(
                audit_evidence_runtime.audit_plan_contract, "load_contract",
                return_value={}), mock.patch.object(
                    audit_evidence_runtime.audit_plan_contract,
                    "validate_contract",
                    return_value={"due_stages": {"pre-merge"}}), \
                mock.patch.object(
                    audit_evidence_runtime, "current_receipt_catalog",
                    return_value={}), mock.patch.object(
                        audit_evidence_runtime, "_resolve_current_plan",
                        return_value=(PLAN_PATH, self.plan, PLAN_SHA256)):
            with self.assertRaisesRegex(
                    ValueError, "differs from requested"):
                audit_evidence_runtime.resolve_stage_plan(
                    self.result, self.item, "pre-merge",
                    required_state="open",
                    plan_path=(runtime_paths.AUDIT_PLAN_ROOT +
                               "/other-plan.yaml"))

    def test_substantive_loader_delegates_currentness_to_stage_resolver(self):
        frozen = (object(),)
        with mock.patch.object(
                audit_producer_runtime, "managed_plan_path",
                return_value="/repo/" + PLAN_PATH), mock.patch.object(
                    record_substantive_review.audit_evidence_runtime,
                    "resolve_stage_plan", return_value=self.resolved) as resolver, \
                mock.patch.object(
                    record_substantive_review.kblib, "sha256_file",
                    return_value=PLAN_SHA256), mock.patch.object(
                        audit_producer_runtime, "freeze_manifest_pages",
                        return_value=frozen):
            absolute, plan, digest, actual_frozen = \
                record_substantive_review.load_current_plan(
                    "/repo", PLAN_PATH, self.result, self.item,
                    activation={"receipt_id": "ignored"})

        self.assertEqual("/repo/" + PLAN_PATH, absolute)
        self.assertIs(self.plan, plan)
        self.assertEqual(PLAN_SHA256, digest)
        self.assertIs(frozen, actual_frozen)
        resolver.assert_called_once_with(
            self.result, self.item, "pre-merge", required_state="open",
            plan_path=PLAN_PATH)

    def test_completion_loader_delegates_directly_to_stage_resolver(self):
        frozen = (object(),)
        with mock.patch.object(
                audit_producer_runtime, "managed_plan_path",
                return_value="/repo/" + PLAN_PATH), mock.patch.object(
                    complete_audit_receipt.audit_evidence_runtime,
                    "resolve_stage_plan", return_value=self.resolved) as resolver, \
                mock.patch.object(
                    complete_audit_receipt.kblib, "sha256_file",
                    return_value=PLAN_SHA256), mock.patch.object(
                        audit_producer_runtime, "freeze_manifest_pages",
                        return_value=frozen):
            absolute, plan, digest, actual_frozen = \
                complete_audit_receipt._load_current_plan(
                    "/repo", PLAN_PATH, self.result, self.item)

        self.assertEqual("/repo/" + PLAN_PATH, absolute)
        self.assertIs(self.plan, plan)
        self.assertEqual(PLAN_SHA256, digest)
        self.assertIs(frozen, actual_frozen)
        resolver.assert_called_once_with(
            self.result, self.item, "pre-merge", required_state="open",
            plan_path=PLAN_PATH)

    def test_batch_page_loader_does_not_reinterpret_live_queue_revision(self):
        snapshot = SimpleNamespace(exists=True, sha256=PLAN_SHA256)
        with mock.patch.object(
                audit_producer_runtime, "managed_plan_path",
                return_value="/repo/" + PLAN_PATH), mock.patch.object(
                    record_batch_page_review.audit_evidence_runtime,
                    "resolve_stage_plan", return_value=self.resolved) as resolver, \
                mock.patch.object(
                    record_batch_page_review.kblib,
                    "repository_target_snapshot", return_value=snapshot), \
                mock.patch.object(
                    record_batch_page_review.kblib, "sha256_file",
                    return_value=PLAN_SHA256), mock.patch.object(
                        audit_producer_runtime, "runtime_state_bindings",
                        side_effect=AssertionError(
                            "batch loader must not compare live Queue state")):
            absolute, plan, digest, actual_snapshot = \
                record_batch_page_review._resolve_current_plan(
                    "/repo", PLAN_PATH, self.result, self.item)

        self.assertEqual("/repo/" + PLAN_PATH, absolute)
        self.assertIs(self.plan, plan)
        self.assertEqual(PLAN_SHA256, digest)
        self.assertIs(snapshot, actual_snapshot)
        resolver.assert_called_once_with(
            self.result, self.item, "pre-merge", required_state="open",
            plan_path=PLAN_PATH)

    def test_producers_do_not_depend_on_plan_producer_currentness(self):
        self.assertNotIn(
            "prepare_audit_plan", record_substantive_review.__dict__)
        self.assertNotIn(
            "prepare_audit_plan", complete_audit_receipt.__dict__)
        self.assertNotIn(
            "record_substantive_review", complete_audit_receipt.__dict__)
        self.assertFalse(hasattr(
            record_batch_page_review, "_require_plan_runtime_binding"))


if __name__ == "__main__":
    unittest.main()
