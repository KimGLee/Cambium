"""Profile typed-closure oracle tests for plan-bound batch judgments."""

from pathlib import Path
from types import SimpleNamespace
import copy
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.evidence.receipt_type_contract as receipt_type_contract
import Tools.governance.profile.profile_batch_judgment_contract as contract_module
import Tools.governance.profile.profile_contract as profile_contract
import Tools.execution.audit.record_batch_judgment as record_batch_judgment
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
SHA_E = "sha256:" + "e" * 64


class ProfileBatchJudgmentContractTests(unittest.TestCase):

    def test_profile_plan_and_receipt_registry_share_one_current_identity(self):
        self.assertEqual(
            frozenset((contract_module.RECORD_KIND,)),
            profile_contract.BATCH_REVIEW_RECEIPT_SCHEMAS)
        plan_contract = audit_plan_contract.load_contract(TOOLS.parent)
        self.assertIn(
            contract_module.RECORD_KIND,
            plan_contract["evidence_kind_values"])
        registrations = receipt_type_contract.load_receipt_type_registry(
            TOOLS.parent)
        registration = registrations[contract_module.RECEIPT_TYPE_ID]
        self.assertEqual(
            "manual-attestation-v1",
            registration.producer_capability_id)
        self.assertEqual(
            "Tools.governance.profile.profile_batch_judgment_contract:"
            "current_receipt_errors",
            registration.validator_owner)

    def setUp(self):
        self.requirement = SimpleNamespace(
            judgment_item_id="fixture-depth",
            target_selector="each-manifest-page",
            trigger="before-merge-ready",
            producer_kind="manual-attestation",
            receipt_schema=contract_module.RECORD_KIND,
            pass_authority_role_id="reviewer",
        )
        self.judgment = SimpleNamespace(
            judgment_item_id="fixture-depth",
            dimension_id="content_and_depth",
            audit_layer="Batch Review",
            audit_object="one manifest page",
            evidence_role="emits",
        )
        self.contract = SimpleNamespace(
            authorized=True,
            batch_review_requirements=(self.requirement,),
            judgment_items=(self.judgment,),
        )
        self.item = {
            "id": "B1",
            "state": "open",
            "manifest": ["Topics/A.md"],
            "activation_receipt": "activation-1",
        }
        projection = contract_module.expected_projection(
            self.contract, "fixture-depth")[2]
        self.obligation = dict(projection)
        self.obligation.update({
            "obligation_id": "obligation-profile-1",
            "target": "Topics/A.md",
        })
        self.plan = {
            "plan_id": "audit-plan-1",
            "task_id": "task-1",
            "batch_id": "B1",
            "opening_transition_receipt": "opening-1",
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/fixture/profile.md",
            "profile_snapshot_sha256": SHA_B,
            "profile_contract_fingerprint": SHA_C,
            "obligations": [self.obligation],
        }
        expanded = contract_module.expand_requirements(
            self.contract, self.item)
        self.requirement_sha = contract_module.requirement_set_sha256(expanded)
        self.activation = {
            "receipt_id": "activation-1",
            "activation_protocol":
                record_batch_judgment.card_activation.ACTIVATION_PROTOCOL,
            "review_requirement_set_sha256": self.requirement_sha,
        }
        self.runtime = {
            "root": "/fixture",
            "_profile_authorized_view": {"_contract": self.contract},
            "current_receipt_catalog": {
                "activation-1": ("receipts/gates.jsonl", self.activation),
            },
        }

    @staticmethod
    def _base_receipt(*_args, **_kwargs):
        return {
            "receipt_id": "judgment-1",
            "receipt_type_id": contract_module.RECEIPT_TYPE_ID,
            "tool": contract_module.PRODUCER_TOOL,
            "tool_version": contract_module.PRODUCER_TOOL_VERSION,
            "check": contract_module.PRODUCER_CHECK,
            "target": "Topics/A.md",
            "result": "pass",
            "details": "the registered content class is confirmed",
            "checked_at": "2026-08-28T00:00:00Z",
            "invalidated_by": None,
            "task_id": "task-1",
        }

    def build(self):
        with mock.patch.object(
                record_batch_judgment.kblib, "make_receipt",
                side_effect=self._base_receipt), mock.patch.object(
                    record_batch_judgment.queue_review,
                    "activation_phase_delivery_errors", return_value=[]), \
                mock.patch.object(
                    contract_module, "artifact_fingerprint",
                    return_value=SHA_E), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_D):
            return record_batch_judgment.build_judgment_receipt(
                self.runtime, self.contract, self.item, self.plan, SHA_A,
                "fixture-depth", "Topics/A.md", "reviewer",
                "the registered content class is confirmed")

    def test_writer_binds_the_unique_profile_audit_plan_obligation(self):
        receipt = self.build()

        self.assertEqual("audit-plan-1", receipt["plan_id"])
        self.assertEqual("obligation-profile-1", receipt["obligation_id"])
        self.assertEqual("profile-extension", receipt["owner_kind"])
        self.assertEqual(
            contract_module.EXTENSION_POINT,
            receipt["kernel_extension_point"])
        self.assertEqual(contract_module.RECORD_KIND, receipt["record_kind"])
        self.assertEqual(SHA_E, receipt["artifact_fingerprint"])
        self.assertEqual(SHA_D, receipt["semantic_content_sha256"])
        self.assertNotEqual(
            receipt["artifact_fingerprint"],
            receipt["semantic_content_sha256"])
        self.assertEqual(
            self.requirement_sha, receipt["dependency_fingerprint"])
        self.assertRegex(
            receipt["contract_fingerprint"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual("opening-1", receipt["opening_transition_receipt"])
        self.assertEqual("activation-1", receipt["activation_receipt_id"])

    def test_writer_never_reauthorizes_a_historical_activation(self):
        self.runtime["receipt_catalog"] = {
            "activation-1": ("receipts/history.jsonl", self.activation),
        }
        self.runtime["current_receipt_catalog"] = {}

        with self.assertRaisesRegex(
                ValueError, "no current activation receipt"):
            self.build()

    def test_wrong_or_duplicate_plan_obligation_is_rejected(self):
        duplicate = copy.deepcopy(self.obligation)
        duplicate["obligation_id"] = "obligation-profile-2"
        plan = dict(self.plan)
        plan["obligations"] = [self.obligation, duplicate]

        with self.assertRaisesRegex(ValueError, "exactly one"):
            contract_module.resolve_obligation(
                plan, self.contract, self.item, "Topics/A.md",
                "fixture-depth")

    def test_heterogeneous_stage_consumer_accepts_and_rejects_fingerprint_drift(self):
        receipt = self.build()
        result = {
            "root": "/fixture",
            "_profile_authorized_view": {"_contract": self.contract},
        }
        catalog = {"judgment-1": ("receipts/judgments.jsonl", receipt)}
        with mock.patch.object(
                contract_module, "artifact_fingerprint",
                return_value=SHA_E), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_D), mock.patch.object(
                        audit_evidence_runtime,
                        "_current_page_artifact_fingerprint",
                        return_value=SHA_E):
            selected = audit_evidence_runtime._required_stage_records(
                result, self.item, self.plan, SHA_A, catalog, "pre-merge",
                require_current=True)
        self.assertEqual("judgment-1", selected[0][1]["receipt_id"])

        drifted = copy.deepcopy(receipt)
        drifted["artifact_fingerprint"] = SHA_C
        catalog = {"judgment-1": ("receipts/judgments.jsonl", drifted)}
        with mock.patch.object(
                contract_module, "artifact_fingerprint",
                return_value=SHA_E), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_D), mock.patch.object(
                        audit_evidence_runtime,
                        "_current_page_artifact_fingerprint",
                        return_value=SHA_E):
            with self.assertRaisesRegex(
                    ValueError, "no current terminal"):
                audit_evidence_runtime._required_stage_records(
                    result, self.item, self.plan, SHA_A, catalog,
                    "pre-merge", require_current=True)

        drifted = copy.deepcopy(receipt)
        drifted["semantic_content_sha256"] = SHA_C
        catalog = {"judgment-1": ("receipts/judgments.jsonl", drifted)}
        with mock.patch.object(
                contract_module, "artifact_fingerprint",
                return_value=SHA_E), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_D), mock.patch.object(
                        audit_evidence_runtime,
                        "_current_page_artifact_fingerprint",
                        return_value=SHA_E):
            with self.assertRaisesRegex(
                    ValueError, "no current terminal"):
                audit_evidence_runtime._required_stage_records(
                    result, self.item, self.plan, SHA_A, catalog,
                    "pre-merge", require_current=True)

    def test_shared_attempt_resolver_allows_stale_successor(self):
        predecessor = self.build()
        successor = copy.deepcopy(predecessor)
        successor["receipt_id"] = "judgment-successor"
        successor["artifact_fingerprint"] = SHA_A
        successor["semantic_content_sha256"] = SHA_B
        catalog = {
            predecessor["receipt_id"]: predecessor,
            successor["receipt_id"]: successor,
        }
        with mock.patch.object(
                contract_module, "artifact_fingerprint",
                return_value=SHA_A), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_B):
            selected = contract_module.current_judgment_attempt(
                "/fixture", self.plan, SHA_A, self.contract, self.item,
                self.runtime["_profile_authorized_view"], catalog,
                "Topics/A.md", "fixture-depth")
        self.assertIs(successor, selected)

        result = {
            "root": "/fixture",
            "_profile_authorized_view": {"_contract": self.contract},
        }
        with mock.patch.object(
                contract_module, "artifact_fingerprint",
                return_value=SHA_A), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_B), mock.patch.object(
                        audit_evidence_runtime,
                        "_current_page_artifact_fingerprint",
                        return_value=SHA_A):
            terminal = audit_evidence_runtime._required_stage_records(
                result, self.item, self.plan, SHA_A, catalog, "pre-merge",
                require_current=True)
        self.assertEqual("judgment-successor",
                         terminal[0][1]["receipt_id"])

    def test_shared_attempt_resolver_rejects_duplicate_current(self):
        first = self.build()
        second = copy.deepcopy(first)
        second["receipt_id"] = "judgment-2"
        catalog = {first["receipt_id"]: first,
                   second["receipt_id"]: second}
        with mock.patch.object(
                contract_module, "artifact_fingerprint",
                return_value=SHA_E), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_D):
            with self.assertRaisesRegex(ValueError,
                                        "multiple current attempts"):
                contract_module.current_judgment_attempt(
                    "/fixture", self.plan, SHA_A, self.contract, self.item,
                    self.runtime["_profile_authorized_view"], catalog,
                    "Topics/A.md", "fixture-depth")

    def test_shared_attempt_resolver_rejects_invalid_stable_history(self):
        invalid = self.build()
        invalid["reviewer_role"] = "unauthorized-role"
        catalog = {invalid["receipt_id"]: invalid}
        with mock.patch.object(
                contract_module, "artifact_fingerprint",
                return_value=SHA_E), mock.patch.object(
                    contract_module, "semantic_content_fingerprint",
                    return_value=SHA_D):
            with self.assertRaisesRegex(ValueError,
                                        "invalid stable attempt"):
                contract_module.current_judgment_attempt(
                    "/fixture", self.plan, SHA_A, self.contract, self.item,
                    self.runtime["_profile_authorized_view"], catalog,
                    "Topics/A.md", "fixture-depth")

    def test_artifact_projection_delegates_to_shared_page_and_set_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Topics").mkdir()
            page_a = """---
type: knowledge
authoring_status: draft
---
# A
"""
            page_b = "# B\n"
            (root / "Topics/A.md").write_text(page_a, encoding="utf-8")
            (root / "Topics/B.md").write_text(page_b, encoding="utf-8")

            page_digest = contract_module.artifact_fingerprint(
                root, self.item, self.requirement, "Topics/A.md")
            self.assertEqual(
                page_digest,
                contract_module.audit_fingerprint.page_artifact_fingerprint(
                    "Topics/A.md", page_a))

            batch_requirement = SimpleNamespace(target_selector="batch")
            item = dict(self.item)
            item["manifest"] = ["Topics/B.md", "Topics/A.md"]
            set_digest = contract_module.artifact_fingerprint(
                root, item, batch_requirement, "B1")
            self.assertEqual(
                set_digest,
                contract_module.audit_fingerprint.
                page_set_artifact_fingerprint([
                    ("Topics/A.md", page_a),
                    ("Topics/B.md", page_b),
                ]))

    def test_semantic_fingerprint_uses_only_authorized_profile_rules(self):
        view = {"authorized": "opaque"}
        rules = ({"field": "fixture_projection"},)
        with mock.patch.object(
                contract_module.metadata_property_state,
                "authorized_profile_projection_rules",
                return_value=(object(), rules)) as authorized, \
                mock.patch.object(
                    contract_module.metadata_property_state,
                    "semantic_page_snapshot",
                    return_value=(object(), SHA_D)) as semantic:
            digest = contract_module.semantic_content_fingerprint(
                "/fixture", "Topics/A.md", view)
        self.assertEqual(SHA_D, digest)
        authorized.assert_called_once_with("/fixture", view)
        semantic.assert_called_once_with(
            "/fixture", "Topics/A.md", rules=rules)


if __name__ == "__main__":
    unittest.main()
