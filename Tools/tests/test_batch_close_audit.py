from copy import deepcopy
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.audit.batch_close_audit as batch_close_audit
import Tools.execution.audit.check_batch_close as check_batch_close
from Tools.platform.common import kblib
from Tools.tests.fixtures.contract import post_delta_objects as objects
from Tools.tests.fixtures.contract.post_delta_objects import SHA_A, SHA_C, SHA_E, SHA_F


class PostDeltaAuditClosureTests(unittest.TestCase):
    def setUp(self):
        # The expected set is read independently, not copied from the Tool
        # projection under test or the shared fixture's resulting output.
        document = kblib.load_yaml_file(
            TOOLS.parent / "kernel/K12 Quality Assurance/batch-close-closed-list.yaml")
        self.rows = tuple(document["members"])
        self.profile = objects.profile_binding()
        self.stage = objects.plan_stage(self.rows)
        self.plan = self.stage["plan"]
        self.projection = batch_close_audit.resolve_post_delta_projection(
            self.stage, self.rows, self.profile)
        self.final_by_member = {}
        self.raw_by_member = {}
        for index, pair in enumerate(self.projection, 1):
            row = pair["member"]
            obligation = pair["obligation"]
            if row["evidence_kind"] == "gate-receipt":
                evidence = objects.gate_evidence()
            else:
                raw = objects.producer_evidence(self.stage, obligation, index)
                evidence = batch_close_audit.build_full_audit_receipt(
                    self.stage, pair, raw)
                audit_receipt_contract.validate_audit_receipt(evidence)
                self.raw_by_member[row["member_id"]] = raw
            self.final_by_member[row["member_id"]] = evidence
        self.closure = batch_close_audit.build_post_delta_evidence_set(
            self.stage, self.projection, self.final_by_member, SHA_F)
        self.by_id = {
            record["receipt_id"]: record
            for record in self.final_by_member.values()
        }

    def test_each_missing_plan_obligation_fails(self):
        expected = [(row["member_id"], row["rule_id"], row["evidence_kind"])
                    for row in self.rows]
        self.assertEqual(expected, [(pair["member"]["member_id"],
            pair["obligation"]["owner_rule_id"], pair["obligation"]["evidence_kind"])
            for pair in self.projection])
        for index, pair in enumerate(self.projection):
            with self.subTest(member=pair["member"]["member_id"]):
                stage = dict(self.stage)
                stage["obligations"] = tuple(
                    obligation for offset, obligation in enumerate(
                        self.stage["obligations"]) if offset != index)
                with self.assertRaisesRegex(
                        batch_close_audit.PostDeltaAuditError,
                        "must contain exactly"):
                    batch_close_audit.resolve_post_delta_projection(
                        stage, self.rows, self.profile)

    def test_each_missing_evidence_binding_fails(self):
        bindings = self.closure["bindings"]
        for index, pair in enumerate(self.projection):
            with self.subTest(member=pair["member"]["member_id"]):
                incomplete = bindings[:index] + bindings[index + 1:]
                with self.assertRaisesRegex(
                        batch_close_audit.PostDeltaAuditError,
                        "every registry member"):
                    batch_close_audit.validate_post_delta_evidence_set(
                        self.stage, self.projection, incomplete,
                        self.by_id, SHA_F)

    def test_mixed_merged_snapshot_fails(self):
        bindings = deepcopy(self.closure["bindings"])
        bindings[3]["merged_snapshot_sha256"] = SHA_A
        with self.assertRaisesRegex(
                batch_close_audit.PostDeltaAuditError,
                "merged_snapshot_sha256"):
            batch_close_audit.validate_post_delta_evidence_set(
                self.stage, self.projection, bindings, self.by_id, SHA_F)

    def test_full_receipt_requires_the_plan_fingerprint_boundary(self):
        pair = next(
            pair for pair in self.projection
            if pair["member"]["evidence_kind"] == "audit-receipt")
        member_id = pair["member"]["member_id"]
        raw = dict(self.raw_by_member[member_id])
        raw.pop("fingerprint_binding")
        with self.assertRaisesRegex(
                batch_close_audit.PostDeltaAuditError,
                "fingerprint_binding"):
            batch_close_audit.build_full_audit_receipt(
                self.stage, pair, raw)

    def test_terminal_pair_replays_the_same_precursor_projection(self):
        pair = next(
            pair for pair in self.projection
            if pair["member"]["evidence_kind"] == "audit-receipt")
        member_id = pair["member"]["member_id"]
        raw = self.raw_by_member[member_id]
        receipt = self.final_by_member[member_id]

        final_by_id = {receipt["receipt_id"]: receipt}
        binding = next(
            row for row in self.closure["bindings"]
            if row["member_id"] == member_id)
        batch_close_audit.validate_post_delta_evidence_set(
            self.stage, (pair,), (binding,), final_by_id, SHA_F,
            producer_evidence_by_member={member_id: raw},
            producer_tool="check_batch_close",
            producer_tool_version=check_batch_close.TOOL_VERSION)

        with self.assertRaisesRegex(
                batch_close_audit.PostDeltaAuditError,
                "producer evidence members"):
            batch_close_audit.validate_post_delta_evidence_set(
                self.stage, (pair,), (binding,), final_by_id, SHA_F,
                producer_evidence_by_member={},
                producer_tool="check_batch_close",
                producer_tool_version=check_batch_close.TOOL_VERSION)

        foreign = deepcopy(raw)
        foreign["obligation_id"] = "foreign-obligation"
        with self.assertRaisesRegex(
                batch_close_audit.PostDeltaAuditError,
                "obligation_id"):
            batch_close_audit.validate_post_delta_evidence_set(
                self.stage, (pair,), (binding,), final_by_id, SHA_F,
                producer_evidence_by_member={member_id: foreign},
                producer_tool="check_batch_close",
                producer_tool_version=check_batch_close.TOOL_VERSION)

        mismatched = deepcopy(raw)
        mismatched["contract_fingerprint"] = SHA_A
        with self.assertRaisesRegex(
                batch_close_audit.PostDeltaAuditError,
                "contract_fingerprint"):
            batch_close_audit.validate_post_delta_evidence_set(
                self.stage, (pair,), (binding,), final_by_id, SHA_F,
                producer_evidence_by_member={member_id: mismatched},
                producer_tool="check_batch_close",
                producer_tool_version=check_batch_close.TOOL_VERSION)

        rebound = deepcopy(receipt)
        rebound["evidence_ref"] = "missing-raw-receipt"
        with self.assertRaisesRegex(
                batch_close_audit.PostDeltaAuditError,
                "evidence_ref"):
            batch_close_audit.validate_post_delta_evidence_set(
                self.stage, (pair,), (binding,),
                {rebound["receipt_id"]: rebound}, SHA_F,
                producer_evidence_by_member={member_id: raw},
                producer_tool="check_batch_close",
                producer_tool_version=check_batch_close.TOOL_VERSION)

    def test_item8_consumes_dimensionless_gate_evidence(self):
        item8 = self.closure["bindings"][-1]
        gate = self.final_by_member["manifest_page_contract"]
        self.assertEqual("manifest_page_contract", item8["member_id"])
        self.assertEqual("consumes", item8["evidence_role"])
        self.assertEqual("gate-receipt", item8["evidence_kind"])
        self.assertIsNone(item8["dimension"])
        self.assertNotIn("dimension", gate)
        self.assertEqual(
            7,
            sum(binding["evidence_kind"] == "audit-receipt"
                for binding in self.closure["bindings"]),
        )

        poisoned = dict(gate, dimension="structure_and_links")
        by_id = dict(self.by_id, **{poisoned["receipt_id"]: poisoned})
        with self.assertRaisesRegex(
                batch_close_audit.PostDeltaAuditError,
                "evidence.dimension"):
            batch_close_audit.validate_post_delta_evidence_set(
                self.stage, self.projection, self.closure["bindings"],
                by_id, SHA_F)


if __name__ == "__main__":
    unittest.main()
