import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import check_proof
from profile_fixture import FIXTURE_UPSTREAM_REVISION


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
SHA_E = "sha256:" + "e" * 64
SHA_F = "sha256:" + "f" * 64


class TerminalProofAuditReceiptBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        contract = Path(
            "kernel/K12 Quality Assurance/audit-receipt-contract.yaml")
        deployed_contract = TOOLS.parent / contract
        local_contract = self.root / contract
        local_contract.parent.mkdir(parents=True)
        shutil.copy2(deployed_contract, local_contract)
        self.register_relative = ".cambium/receipts/terminal.jsonl"
        self.register = self.root / self.register_relative
        self.register.parent.mkdir(parents=True)
        self.plan = {
            "plan_id": "audit-plan-batch-1",
            "task_id": "task-1",
            "batch_id": "batch-1",
            "opening_transition_receipt": "open-1",
            "standards_version": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_B,
            "profile_contract_fingerprint": SHA_C,
        }
        self.obligation = {
            "obligation_id": "obligation-1",
            "owner_kind": "kernel",
            "owner_rule_id": "K12/09:closed-list-1",
            "kernel_extension_point": None,
            "due_stage": "pre-merge",
            "target": "Topics/Example.md",
            "evidence_role": "emits",
            "evidence_kind": "audit-receipt",
            "dimension": "content_and_depth",
            "acceptance_predicate": "fixture acceptance",
            "producer_check": "fixture-check",
            "producer_capability": "fixture-producer-v1",
            "producer_gate_id": None,
            "consumer_gate_id": "terminal-proof",
            "fingerprint_binding": "evidence-time",
            "review_due": None,
        }
        self.producer = {
            "receipt_id": "producer-1",
            "tool": "fixture_producer",
            "tool_version": "1.0.0",
            "check": "fixture-check",
            "target": self.obligation["target"],
            "plan_id": self.plan["plan_id"],
            "audit_plan_sha256": SHA_D,
            "obligation_id": self.obligation["obligation_id"],
            "task_id": self.plan["task_id"],
            "batch_id": self.plan["batch_id"],
            "opening_transition_receipt":
                self.plan["opening_transition_receipt"],
            "standards_version": self.plan["standards_version"],
            "active_standards_sha256":
                self.plan["active_standards_sha256"],
            "selected_profile_manifest":
                self.plan["selected_profile_manifest"],
            "profile_snapshot_sha256":
                self.plan["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                self.plan["profile_contract_fingerprint"],
            "fingerprint_binding": "evidence-time",
            "artifact_fingerprint": SHA_E,
            "dependency_fingerprint": SHA_F,
            "contract_fingerprint": SHA_A,
            "checked_at": "2026-08-28T00:00:00Z",
            "result": "pass",
            "invalidated_by": None,
        }
        self.receipt = {
            "schema_version": 1,
            "record_kind": "audit-receipt",
            "receipt_id": "audit-receipt-1",
            "plan_id": self.plan["plan_id"],
            "audit_plan_sha256": SHA_D,
            "obligation_id": self.obligation["obligation_id"],
            "owner_kind": self.obligation["owner_kind"],
            "owner_rule_id": self.obligation["owner_rule_id"],
            "kernel_extension_point": None,
            "task_id": self.plan["task_id"],
            "batch_id": self.plan["batch_id"],
            "opening_transition_receipt":
                self.plan["opening_transition_receipt"],
            "standards_version": self.plan["standards_version"],
            "active_standards_sha256":
                self.plan["active_standards_sha256"],
            "selected_profile_manifest":
                self.plan["selected_profile_manifest"],
            "profile_snapshot_sha256":
                self.plan["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                self.plan["profile_contract_fingerprint"],
            "due_stage": self.obligation["due_stage"],
            "evidence_role": self.obligation["evidence_role"],
            "evidence_kind": self.obligation["evidence_kind"],
            "dimension": self.obligation["dimension"],
            "scope": [self.obligation["target"]],
            "acceptance_predicate":
                self.obligation["acceptance_predicate"],
            "producer_check": self.obligation["producer_check"],
            "producer_capability":
                self.obligation["producer_capability"],
            "producer_gate_id": None,
            "consumer_gate_id": self.obligation["consumer_gate_id"],
            "fingerprint_binding": "evidence-time",
            "artifact_fingerprint": self.producer["artifact_fingerprint"],
            "dependency_fingerprint":
                self.producer["dependency_fingerprint"],
            "contract_fingerprint": self.producer["contract_fingerprint"],
            "verifier": self.producer["tool"],
            "method": "fixture_producer@1.0.0/fixture-check",
            "evidence_ref": self.producer["receipt_id"],
            "checked_at": self.producer["checked_at"],
            "review_due": None,
            "result": "passed",
            "invalidated_by": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }

    def write_register(self, record):
        self.register.write_text(
            json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    def runtime(self, record=None):
        record = self.receipt if record is None else record
        return {
            "items_by_id": {"batch-1": {"id": "batch-1"}},
            "current_receipt_catalog": {
                record["receipt_id"]: (self.register_relative, record),
                self.producer["receipt_id"]:
                    (".cambium/receipts/producer.jsonl", self.producer),
            },
            "invalidated_evidence_receipt_ids": [],
        }

    def resolved_plan(self, **overrides):
        result = {
            "audit_plan_id": self.plan["plan_id"],
            "audit_plan_path": (
                ".cambium/work_specs/audit-plans/audit-plan-batch-1.yaml"),
            "audit_plan_sha256": SHA_D,
            "plan": self.plan,
            "obligations": (self.obligation,),
        }
        result.update(overrides)
        return result

    def validate(self, record=None, runtime=None, resolved=None):
        record = self.receipt if record is None else record
        self.write_register(record)
        runtime = self.runtime(record) if runtime is None else runtime
        resolved = self.resolved_plan() if resolved is None else resolved
        with mock.patch.object(
                check_proof.audit_evidence_runtime, "resolve_stage_plan",
                return_value=resolved):
            return check_proof._validate_dimension_coverage_evidence(
                self.root,
                {"audit_receipt_register": self.register_relative},
                {record["receipt_id"]: self.obligation["dimension"]},
                runtime)

    def test_full_current_passed_receipt_discharge_is_accepted(self):
        self.assertEqual([], self.validate())

    def test_gate_or_generic_success_with_dimension_is_not_an_audit_receipt(self):
        gate = {
            "receipt_id": "gate-1",
            "record_kind": "gate-receipt",
            "dimension": "content_and_depth",
            "result": "pass",
        }
        failures = self.validate(gate)
        self.assertEqual(
            ["proof-dimension-receipt-contract-invalid"],
            [failure[0] for failure in failures])

        legacy = {
            "receipt_id": "legacy-1",
            "dimension": "content_and_depth",
            "result": "pass",
        }
        failures = self.validate(legacy)
        self.assertEqual(
            ["proof-dimension-receipt-contract-invalid"],
            [failure[0] for failure in failures])

    def test_register_bytes_must_equal_the_current_catalog_record(self):
        current = dict(self.receipt)
        current["method"] = "different@1.0.0/fixture-check"
        runtime = self.runtime(current)
        failures = self.validate(self.receipt, runtime=runtime)
        self.assertEqual(
            ["proof-dimension-receipt-catalog-mismatch"],
            [failure[0] for failure in failures])

    def test_failed_full_audit_receipt_cannot_prove_completion(self):
        failed = dict(self.receipt)
        failed["result"] = "failed"
        failures = self.validate(failed)
        self.assertEqual(
            ["proof-dimension-receipt-not-passed"],
            [failure[0] for failure in failures])

    def test_three_fingerprints_are_required_by_the_full_contract(self):
        incomplete = dict(self.receipt)
        incomplete.pop("dependency_fingerprint")
        failures = self.validate(incomplete)
        self.assertEqual(
            ["proof-dimension-receipt-contract-invalid"],
            [failure[0] for failure in failures])

    def test_receipt_must_bind_the_current_plan_identity(self):
        failures = self.validate(resolved=self.resolved_plan(
            audit_plan_id="different-plan"))
        self.assertEqual(
            ["proof-dimension-receipt-plan-mismatch"],
            [failure[0] for failure in failures])

    def test_owner_due_producer_consumer_and_fingerprints_use_shared_boundary(self):
        wrong = dict(self.receipt)
        wrong["consumer_gate_id"] = "different-consumer"
        failures = self.validate(wrong)
        self.assertEqual(
            ["proof-dimension-receipt-obligation-mismatch"],
            [failure[0] for failure in failures])
        self.assertIn("consumer_gate_id", failures[0][2])


if __name__ == "__main__":
    unittest.main()
