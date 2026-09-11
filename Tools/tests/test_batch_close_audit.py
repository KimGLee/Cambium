from copy import deepcopy
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.batch_close_audit as batch_close_audit
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
        for index, pair in enumerate(self.projection, 1):
            row = pair["member"]
            obligation = pair["obligation"]
            if row["evidence_kind"] == "gate-receipt":
                evidence = objects.gate_evidence()
            else:
                evidence = objects.producer_evidence(self.stage, obligation, index)
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

    def test_member_acceptance_preserves_plan_and_input_boundaries(self):
        pair = next(pair for pair in self.projection
                    if pair["member"]["evidence_kind"] == "batch-close-member-evidence")
        record = self.final_by_member[pair["member"]["member_id"]]
        self.assertIs(record, batch_close_audit.validate_member_evidence(
            self.stage, pair, record, SHA_F))
        for field in ("task_id", "batch_id", "target", "plan_id", "obligation_id",
                      "opening_transition_receipt", "upstream_revision_id",
                      "active_standards_sha256", "selected_profile_manifest",
                      "profile_snapshot_sha256", "profile_contract_fingerprint",
                      "audit_plan_path", "audit_plan_sha256", "fingerprint_binding",
                      "artifact_fingerprint", "dependency_fingerprint", "contract_fingerprint"):
            with self.subTest(field=field):
                changed = dict(record, **{field: "foreign"})
                with self.assertRaisesRegex(batch_close_audit.PostDeltaAuditError, field):
                    batch_close_audit.validate_member_evidence(self.stage, pair, changed, SHA_F)

    def test_direct_fact_must_remain_resolvable_and_unmodified(self):
        for pair, binding in zip(self.projection, self.closure["bindings"]):
            with self.subTest(member=pair["member"]["member_id"]):
                missing = dict(self.by_id)
                missing.pop(binding["evidence_ref"])
                with self.assertRaisesRegex(batch_close_audit.PostDeltaAuditError, "evidence_ref"):
                    batch_close_audit.validate_post_delta_evidence_set(
                        self.stage, self.projection, self.closure["bindings"], missing, SHA_F)
        pair = self.projection[0]
        record = self.final_by_member[pair["member"]["member_id"]]
        for field in ("receipt_type_id", "check", "tool", "tool_version", "result", "invalidated_by"):
            with self.subTest(field=field):
                changed = dict(record, **{field: "foreign"})
                with self.assertRaises(batch_close_audit.PostDeltaAuditError):
                    batch_close_audit.validate_member_evidence(self.stage, pair, changed, SHA_F)

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
            sum(binding["evidence_kind"] == "batch-close-member-evidence"
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
