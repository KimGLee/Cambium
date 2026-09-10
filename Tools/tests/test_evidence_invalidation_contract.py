"""Correction decision, identity and dependency projection owner tests.

The object factory models the already-admitted catalog boundary. It is not a
runtime initializer or an alternative producer fixture. Producer body formats
and full lifecycle execution remain tested by their existing owners.
"""

import copy
import unittest

from Tools.execution.audit import batch_review_obligation_contract
from Tools.execution.evidence import evidence_invalidation_contract as contract
from Tools.execution.evidence import receipt_reference_contract as graph
from Tools.execution.evidence import receipt_type_contract
from Tools.execution.task_runtime.queue_runtime import receipts


class EvidenceInvalidationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = contract.load_policy()
        cls.registry = receipt_type_contract.load_receipt_type_registry()

    def setUp(self):
        self.binding = {
            "upstream_revision_id": "a" * 40,
            "active_standards_sha256": contract.digest("standards"),
            "selected_profile_manifest": "profiles/test/profile.toml",
            "profile_snapshot_sha256": contract.digest("profile"),
            "profile_contract_fingerprint": contract.digest("profile-contract"),
        }
        self.subject = {
            "receipt_id": "review-one",
            "receipt_type_id": batch_review_obligation_contract.RECEIPT_TYPE_ID,
            "target": "Topic.md", "task_id": "TASK", "batch_id": "B1",
            "plan_id": "PLAN", "obligation_id": "OBL",
            "audit_plan_sha256": contract.digest("plan"),
            "reviewer_context_id": "reviewer-context", "reviewer_role": "reviewer",
            "opening_transition_receipt": "opened",
            "consumed_evidence_refs": [], **self.binding,
        }
        self.decision = {
            "mode": "own-declaration", "actor_role": "reviewer",
            "reviewer_context_id": "reviewer-context",
            "authority_reference": "user-confirmed-correction",
            "statement": "I withdraw my earlier assessment of the table.",
        }
        self.event = contract.build_event(
            event_id="correction-one", reason=self.policy["decision_reasons"][0],
            decision=self.decision, subjects=[self.subject], authority=self.binding,
            checked_at="2026-09-08T00:00:00Z")
        self.catalog = receipts.HistoricalReceiptCatalog({
            "review-one": self.subject,
            self.event["receipt_id"]: self.event,
        })

    def test_kernel_modes_bind_exact_original_authority(self):
        expected = set(self.policy["decision_modes"])
        exercised = set()
        for mode in self.policy["decision_modes"]:
            subject = dict(self.subject)
            decision = dict(self.decision, mode=mode)
            if mode == "semantic-authority":
                subject["pass_authority_role_id"] = "reviewer"
            elif mode == "explicit-user":
                decision.update(actor_role="user", reviewer_context_id=None)
            contract.validate_decision(decision, [subject], self.policy)
            exercised.add(mode)
            wrong = dict(decision, actor_role="integrator")
            with self.assertRaises(ValueError):
                contract.validate_decision(wrong, [subject], self.policy)
        self.assertEqual(expected, exercised)
        with self.assertRaisesRegex(ValueError, "another reviewer"):
            contract.validate_decision(
                dict(self.decision, reviewer_context_id="different"),
                [self.subject], self.policy)

    def test_subject_identity_scope_and_record_bytes_are_bound(self):
        contract.validate_subjects(self.event, self.catalog, registry=self.registry)
        for field, value in (("target", "Other.md"), ("task_id", "OTHER"),
                             ("obligation_id", "OTHER"), ("reviewer_role", "author")):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.catalog)
                changed["review-one"][field] = value
                with self.assertRaisesRegex(ValueError, "absent or changed"):
                    contract.validate_subjects(self.event, changed, registry=self.registry)
        foreign = dict(self.event, profile_snapshot_sha256=contract.digest("other"))
        with self.assertRaisesRegex(ValueError, "another profile_snapshot"):
            contract.validate_subjects(foreign, self.catalog, registry=self.registry)

    def test_event_is_not_a_replacement_pass_or_state_rollback(self):
        registration = self.registry[contract.RECEIPT_TYPE_ID]
        self.assertFalse(registration.correction_subject)
        self.assertEqual(contract.CAPABILITY_ID, registration.producer_capability_id)
        self.assertEqual([], receipt_type_contract.current_receipt_errors(
            self.event, "historical", registry=self.registry))
        state = dict(self.subject, receipt_type_id="queue-transition-receipt-v1")
        state_event = contract.build_event(
            event_id="state-correction", reason=self.event["reason"],
            decision=self.decision, subjects=[state], authority=self.binding,
            checked_at=self.event["checked_at"])
        with self.assertRaisesRegex(ValueError, "executed state"):
            contract.validate_subjects(state_event, {"review-one": state}, registry=self.registry)
        with self.assertRaisesRegex(ValueError, "cannot be reversed"):
            contract.build_event(
                event_id="undo", reason=self.event["reason"],
                decision=dict(self.decision, mode="explicit-user", actor_role="user",
                              reviewer_context_id=None),
                subjects=[self.event], authority=self.binding,
                checked_at=self.event["checked_at"])

    def test_transitive_acceptance_not_history_or_custody(self):
        wrapper = {"receipt_id": "wrapper", "receipt_type_id": "batch-review-wrapper-v2",
                   "audit_evidence_bindings": [{"evidence_ref": "review-one"}]}
        close = {"receipt_id": "close", "receipt_type_id": "batch-close-gate-v1",
                 "queue_consistency_receipt": "unrelated",
                 "delta_apply_receipt": "state-write",
                 "reviewer_attestation_receipt": "attestation"}
        attestation = {"receipt_id": "attestation",
                       "receipt_type_id": "batch-close-review-attestation-v1",
                       "audit_evidence_reconciliation": [{"selected_evidence_ref": "review-one"}]}
        unrelated = dict(self.subject, receipt_id="unrelated", consumed_evidence_refs=[])
        self.catalog.update(wrapper=wrapper, close=close,
                            attestation=attestation, unrelated=unrelated)
        before = copy.deepcopy(self.catalog)
        view = contract.invalidation_view(self.catalog, registry=self.registry)
        self.assertEqual({"review-one", "wrapper", "attestation", "close"}, set(view["affected"]))
        self.assertEqual({"review-one"}, set(view["direct"]))
        self.assertNotIn(self.event["receipt_id"], view["affected"])
        self.assertEqual(before, self.catalog)
        self.assertTrue(receipts.adoption_filtered_catalog(self.catalog, view["affected"]).get("unrelated"))
        deficits = contract.current_reference_deficits(
            {"id": "B1", "batch_receipts": ["wrapper"], "invalidation_history": [
                {"batch_receipts": ["wrapper"]}]}, graph.SOURCE_ITEM, view, scope="B1")
        self.assertEqual(1, len(deficits))
        self.assertEqual("queue-item.batch-review", deficits[0]["edge_id"])

    def test_unknown_or_missing_dependency_is_not_zero_impact(self):
        self.catalog["consumer"] = {
            "receipt_id": "consumer", "receipt_type_id": "batch-page-review-record-v3",
            "consumed_evidence_refs": ["missing"]}
        with self.assertRaisesRegex(ValueError, "dependency is absent"):
            contract.invalidation_view(self.catalog, registry=self.registry)
        self.catalog["consumer"]["receipt_type_id"] = "unknown-format"
        with self.assertRaisesRegex(ValueError, "no current producer"):
            contract.invalidation_view(self.catalog, registry=self.registry)
        self.catalog["consumer"].update(
            receipt_type_id="batch-page-review-record-v3", consumed_evidence_refs=["review-one"])
        self.catalog["review-one"]["consumed_evidence_refs"] = ["consumer"]
        self.event["subjects"] = [contract.subject_binding(self.catalog["review-one"])]
        with self.assertRaisesRegex(ValueError, "circular proof"):
            contract.invalidation_view(self.catalog, registry=self.registry)

    def test_event_contract_rejects_mutable_or_unbound_forms(self):
        for changes in (
                {"force": True}, {"invalidated_by": "reverse-event"},
                {"checked_at": "2026-09-08"}, {"policy_sha256": contract.digest("other")},
                {"event_id": "../other"}, {"subjects": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                contract.validate_event(dict(self.event, **changes))

if __name__ == "__main__":
    unittest.main()
