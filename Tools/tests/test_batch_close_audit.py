from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_receipt_contract as audit_receipt_contract
import Tools.execution.audit.batch_close_audit as batch_close_audit
import Tools.execution.audit.batch_close_contract as batch_close_contract
import Tools.execution.audit.check_batch_close as check_batch_close
import Tools.knowledge.metadata.check_page_contract as check_page_contract
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
SHA_E = "sha256:" + "e" * 64
SHA_F = "sha256:" + "f" * 64


class PostDeltaAuditClosureTests(unittest.TestCase):
    def setUp(self):
        self.rows = tuple(batch_close_contract.CLOSED_LIST_MEMBER_ROWS)
        scan = SimpleNamespace(judgment_item_id="fixture-residual-judgment")
        judgment = SimpleNamespace(
            judgment_item_id="fixture-residual-judgment",
            dimension_id="content_and_depth",
            evidence_role="emits",
        )
        self.profile = SimpleNamespace(
            required_scan=scan, judgment_items=(judgment,))
        obligations = []
        for row in self.rows:
            binding = row["dimension_binding"]
            dimension = (row["dimension"] if binding == "fixed" else
                         ("content_and_depth"
                          if binding == "profile-registration" else None))
            obligations.append({
                "obligation_id": "post-delta-%s" % row["member_id"],
                "owner_kind": "kernel",
                "owner_rule_id": row["rule_id"],
                "kernel_extension_point": None,
                "partition": "mandatory-full-deterministic",
                "due_stage": "post-delta-close",
                "target": ("page-contract" if
                           row["member_id"] == "manifest_page_contract"
                           else "."),
                "applicability": "always",
                "evidence_role": row["evidence_role"],
                "evidence_kind": row["evidence_kind"],
                "dimension": dimension,
                "acceptance_predicate": "fixture-%s-passes" %
                    row["member_id"],
                "producer_check": row["producer_check"],
                "producer_capability": row.get("producer_capability"),
                "producer_gate_id": row.get("producer_gate_id"),
                "consumer_gate_id": "batch-close",
                "fingerprint_binding": "evidence-time",
                "review_due": None,
                "status": "required",
                "evidence_ref": None,
                "reused_receipt_id": None,
                "reuse_reason": None,
            })
        self.plan = {
            "plan_id": "plan-b1",
            "task_id": "task-1",
            "batch_id": "B1",
            "opening_transition_receipt": "opening-b1",
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": SHA_B,
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_C,
            "profile_contract_fingerprint": SHA_D,
            "contract_snapshot_sha256": SHA_E,
            "obligations": obligations,
        }
        self.stage = {
            "audit_plan_id": "plan-b1",
            "audit_plan_path": ".cambium/audit-plans/plan-b1.yaml",
            "audit_plan_sha256": SHA_A,
            "plan": self.plan,
            "obligations": tuple(obligations),
        }
        self.projection = batch_close_audit.resolve_post_delta_projection(
            self.stage, self.rows, self.profile)
        self.final_by_member = {}
        self.raw_by_member = {}
        for index, pair in enumerate(self.projection, 1):
            row = pair["member"]
            obligation = pair["obligation"]
            if row["evidence_kind"] == "gate-receipt":
                evidence = {
                    "receipt_id": "page-contract-gate",
                    "tool": "check_page_contract",
                    "tool_version": check_page_contract.TOOL_VERSION,
                    "check": "page-contract-summary",
                    "target": "page-contract",
                    "result": "pass",
                    "details": "fixture Gate passed",
                    "checked_at": "2026-08-28T00:00:00Z",
                    "invalidated_by": None,
                    "gate_id": "page-contract",
                }
            else:
                raw = {
                    "receipt_id": "raw-%02d" % index,
                    "tool": "check_batch_close",
                    "tool_version": check_batch_close.TOOL_VERSION,
                    "check": obligation["producer_check"],
                    "target": obligation["target"],
                    "result": "pass",
                    "details": "fixture producer evidence",
                    "checked_at": "2026-08-28T00:00:00Z",
                    "invalidated_by": None,
                    "plan_id": self.stage["audit_plan_id"],
                    "audit_plan_path": self.stage["audit_plan_path"],
                    "audit_plan_sha256": self.stage["audit_plan_sha256"],
                    "obligation_id": obligation["obligation_id"],
                    "task_id": self.plan["task_id"],
                    "batch_id": self.plan["batch_id"],
                    "opening_transition_receipt":
                        self.plan["opening_transition_receipt"],
                    "upstream_revision_id": self.plan["upstream_revision_id"],
                    "active_standards_sha256":
                        self.plan["active_standards_sha256"],
                    "selected_profile_manifest":
                        self.plan["selected_profile_manifest"],
                    "profile_snapshot_sha256":
                        self.plan["profile_snapshot_sha256"],
                    "profile_contract_fingerprint":
                        self.plan["profile_contract_fingerprint"],
                    "fingerprint_binding":
                        obligation["fingerprint_binding"],
                    "merged_snapshot_sha256": SHA_F,
                    "artifact_fingerprint": SHA_F,
                    "dependency_fingerprint": SHA_C,
                    "contract_fingerprint": SHA_E,
                }
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
