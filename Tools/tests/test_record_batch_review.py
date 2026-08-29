from types import SimpleNamespace
import sys
import unittest
from unittest import mock

from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import card_activation
import record_batch_review
from queue_runtime.receipts import Catalog


class RecordBatchReviewBuilderTests(unittest.TestCase):
    """The producer builds the exact sets its transition consumers accept."""

    def setUp(self):
        self.requirement = SimpleNamespace(
            judgment_item_id="fixture-depth",
            target_selector="batch",
            trigger="before-merge-ready",
            producer_kind="manual-attestation",
            receipt_schema="batch-judgment-v1",
            pass_authority_role_id="reviewer",
        )
        self.contract = SimpleNamespace(
            authorized=True,
            batch_review_requirements=(self.requirement,),
        )
        self.item = {
            "id": "B1",
            "state": "open",
            "manifest": ["Topics/A.md"],
            "activation_receipt": "activation-1",
        }
        expected = card_activation.expand_batch_review_requirements(
            self.contract, self.item)
        expected_sha = card_activation.review_requirement_set_sha256(expected)
        activation = {
            "receipt_id": "activation-1",
            "result": "pass",
            "invalidated_by": None,
            "activation_protocol": card_activation.ACTIVATION_PROTOCOL,
            "review_requirement_set_sha256": expected_sha,
        }
        page = {
            "receipt_id": "page-1",
            "result": "pass",
            "invalidated_by": None,
            "target": "Topics/A.md",
        }
        judgment = {
            "receipt_id": "judgment-1",
            "tool": "record_batch_judgment",
            "check": "profile_batch_judgment",
            "record_kind": "page-batch-judgment-v1",
            "result": "pass",
            "invalidated_by": None,
            "task_id": "task-1",
            "batch_id": "B1",
            "target": "B1",
            "judgment_item_id": "fixture-depth",
            "target_selector": "batch",
            "receipt_schema": "batch-judgment-v1",
            "reviewer_role": "reviewer",
            "opening_transition_receipt": "opening-1",
            "activation_receipt_id": "activation-1",
            "review_requirement_set_sha256": expected_sha,
            "profile_contract_fingerprint": "sha256:profile",
        }
        catalog = Catalog({
            "activation-1": ("activation.jsonl", activation),
            "page-1": ("page.jsonl", page),
            "judgment-1": ("judgment.jsonl", judgment),
        })
        self.result = {
            "root": "/fixture",
            "queue": {"task_id": "task-1"},
            "coverage": {
                "pages": [{"path": "Topics/A.md", "tier": "S"}],
            },
            "current_receipt_catalog": catalog,
            "_profile_authorized_view": {
                "_contract": self.contract,
                "profile_contract_fingerprint": "sha256:profile",
            },
        }
        self.delta = {
            "path": ".cambium/deltas/B1.yaml",
            "sha256": "sha256:" + "1" * 64,
            "page_receipt_ids": ["page-1"],
        }
        self.audit = {
            "audit_plan_id": "audit-plan-1",
            "audit_plan_path":
                ".cambium/work_specs/audit-plans/audit-plan-1.yaml",
            "audit_plan_sha256": "sha256:" + "2" * 64,
            "audit_evidence_bindings": [{
                "obligation_id": "obligation-1",
                "evidence_ref": "audit-full-1",
            }],
            "audit_evidence_set_sha256": "sha256:" + "4" * 64,
            "audit_receipt_ids": ["audit-full-1"],
            "audit_receipt_set_sha256": "sha256:" + "3" * 64,
        }

    @staticmethod
    def _base_receipt(*_args, **_kwargs):
        return {
            "receipt_id": "wrapper-1",
            "check": "batch_gate",
            "target": "B1",
            "result": "pass",
            "details": "all current obligations were inspected",
            "checked_at": "2026-08-28T00:00:00Z",
            "tool": "manual-attestation",
            "tool_version": "1.0.0",
            "invalidated_by": None,
            "task_id": "task-1",
        }

    def build(self):
        with mock.patch.object(
                record_batch_review.kblib, "make_receipt",
                side_effect=self._base_receipt):
            return record_batch_review.build_batch_review_receipt(
                self.result, self.item, self.delta, self.audit,
                "integrator", "all current obligations were inspected")

    def test_builder_derives_and_consumer_accepts_exact_sets(self):
        receipt = self.build()

        self.assertEqual(["page-1"], receipt["delta_page_receipt_ids"])
        self.assertEqual(["judgment-1"], receipt["judgment_receipt_ids"])
        self.assertEqual(["audit-full-1"], receipt["audit_receipt_ids"])
        self.assertEqual("audit-plan-1", receipt["audit_plan_id"])
        with mock.patch.object(
                record_batch_review.check_queue,
                "batch_review_judgment_errors", return_value=[]), mock.patch(
                "audit_evidence_runtime.wrapper_binding_errors",
                return_value=[]):
            record_batch_review.validate_batch_review_receipt(
                self.result, self.item, receipt, delta_binding=self.delta,
                audit_binding=self.audit)

    def test_existing_consumer_rejects_missing_delta_member(self):
        receipt = self.build()
        receipt["delta_page_receipt_ids"] = ["missing-page-receipt"]

        with mock.patch.object(
                record_batch_review.check_queue,
                "batch_review_judgment_errors", return_value=[]), mock.patch(
                "audit_evidence_runtime.wrapper_binding_errors",
                return_value=[]):
            with self.assertRaisesRegex(ValueError, "missing-page-receipt"):
                record_batch_review.validate_batch_review_receipt(
                    self.result, self.item, receipt,
                    delta_binding=self.delta, audit_binding=self.audit)

    def test_self_check_rejects_audit_plan_binding_drift(self):
        receipt = self.build()
        receipt["audit_plan_sha256"] = "sha256:" + "9" * 64

        with mock.patch.object(
                record_batch_review.check_queue,
                "batch_review_judgment_errors", return_value=[]), mock.patch(
                "audit_evidence_runtime.wrapper_binding_errors",
                return_value=[]):
            with self.assertRaisesRegex(ValueError, "audit_plan_sha256"):
                record_batch_review.validate_batch_review_receipt(
                    self.result, self.item, receipt,
                    delta_binding=self.delta, audit_binding=self.audit)

    def test_non_integrator_cannot_record_wrapper(self):
        with mock.patch.object(
                record_batch_review.kblib, "make_receipt",
                side_effect=self._base_receipt):
            with self.assertRaisesRegex(ValueError, "integrator"):
                record_batch_review.build_batch_review_receipt(
                    self.result, self.item, self.delta, self.audit,
                    "worker", "reviewed")

    def test_audit_binding_delegates_to_runtime_consumer(self):
        consumer = SimpleNamespace(batch_review_evidence=mock.Mock(
            return_value=dict(self.audit)))
        with mock.patch.dict(sys.modules, {
                "audit_evidence_runtime": consumer}):
            binding = record_batch_review._audit_plan_evidence(
                self.result, self.item)

        self.assertEqual(self.audit, binding)
        consumer.batch_review_evidence.assert_called_once_with(
            self.result, self.item)


if __name__ == "__main__":
    unittest.main()
