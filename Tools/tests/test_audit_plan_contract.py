"""Closed-contract tests for the Kernel-owned K12/19 AuditPlan."""

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract  # noqa: E402
import Tools.execution.audit.audit_plan_contract as contract  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.platform.distribution.upstream_identity as upstream_identity  # noqa: E402


class AuditPlanContractTests(unittest.TestCase):

    def plan(self):
        return copy.deepcopy(kblib.load_yaml_file(
            TOOLS / "schemas/audit_plan.template.yaml"))

    def test_shipped_contract_and_template_are_valid(self):
        values = contract.validate_contract(contract.load_contract())
        plan = contract.validate_plan(self.plan())
        self.assertEqual(tuple(plan), values["field_order"])
        self.assertEqual(
            ("obligation-001",), contract.required_obligation_ids(plan))
        self.assertTrue(upstream_identity.is_full_commit_sha(
            plan["upstream_revision_id"]))
        self.assertRegex(contract.plan_sha256(plan), r"^sha256:[0-9a-f]{64}$")
        expected = kblib.sha256_bytes(kblib.canonical_yaml(plan).encode("utf-8"))
        material = {}
        def memo(key, compute):
            if key not in material:
                material[key] = compute()
            return material[key]
        with mock.patch.object(kblib, "canonical_yaml", wraps=kblib.canonical_yaml) as serialize, \
                mock.patch.object(contract, "validate_plan", wraps=contract.validate_plan) as validate:
            with contract.serialization_observation(memo):
                self.assertEqual(expected, contract.plan_sha256(plan))
                self.assertEqual(expected, contract.plan_sha256(copy.deepcopy(plan)))
                self.assertEqual(1, serialize.call_count)
                self.assertEqual(2, validate.call_count)
                with self.assertRaisesRegex(ValueError, "dimension is not registered"):
                    contract.plan_sha256(plan, dimensions=())
                plan["plan_id"] = "changed-plan-identity"
                changed = contract.plan_sha256(plan)
                self.assertNotEqual(expected, changed)
                self.assertEqual(2, serialize.call_count)
                plan["obligations"][0]["command"] = "not-a-plan-field"
                with self.assertRaisesRegex(ValueError, "fields are not closed"):
                    contract.plan_sha256(plan)
                del plan["obligations"][0]["command"]
            # No serialized value survives as an implicit cross-operation cache.
            self.assertEqual(changed, contract.plan_sha256(plan))
            self.assertEqual(3, serialize.call_count)

    def test_evidence_roles_resolve_from_the_canonical_registry(self):
        document = contract.load_contract()
        self.assertNotIn("evidence_role_values", document)
        self.assertEqual({
            "audit_dimension_base":
                audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH,
        }, document["registry_references"])
        values = contract.validate_contract(document)
        self.assertEqual(
            audit_dimension_contract.EVIDENCE_ROLES,
            values["evidence_roles"])

    def test_root_snapshot_supplies_the_evidence_role_registry(self):
        path = REPOSITORY / \
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH
        changed = path.read_text(encoding="utf-8").replace(
            "  - triggers\n", "  - snapshot-only-role\n")
        snapshots = {
            audit_dimension_contract.AUDIT_DIMENSION_BASE_PATH:
                SimpleNamespace(read_text=lambda: changed),
        }
        with self.assertRaisesRegex(
                ValueError, "differs from the validator's deployed"):
            contract.load_contract(REPOSITORY, snapshots=snapshots)

    def test_partition_uses_the_k12_19_overdue_vocabulary(self):
        self.assertIn("overdue-targeted-review", contract.PARTITION_IDS)
        self.assertNotIn("high-risk-targeted-review", contract.PARTITION_IDS)
        plan = self.plan()
        plan["obligations"][0]["partition"] = "high-risk-targeted-review"
        with self.assertRaisesRegex(ValueError, "partition is not registered"):
            contract.validate_plan(plan)

    def test_instance_and_obligation_fields_are_closed(self):
        plan = self.plan()
        plan["plan_path"] = ".cambium/work_specs/audit-plans/example.yaml"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_plan(plan)

        plan = self.plan()
        plan["obligations"][0]["command"] = "free text"
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_plan(plan)

    def test_required_obligation_cannot_predeclare_evidence(self):
        plan = self.plan()
        plan["obligations"][0]["evidence_ref"] = "audit-evidence-1"
        with self.assertRaisesRegex(ValueError, "must not predeclare"):
            contract.validate_plan(plan)

    def test_reused_obligation_is_explicit_and_uses_reusable_partition(self):
        plan = self.plan()
        row = plan["obligations"][0]
        row.update({
            "partition": "reusable-evidence",
            "status": "reused",
            "evidence_ref": "audit-existing-1",
            "reused_receipt_id": "audit-existing-1",
            "reuse_reason": "all three fingerprints remain current",
            "fingerprint_binding": "reused-receipt",
        })
        contract.validate_plan(plan)
        self.assertEqual((), contract.required_obligation_ids(plan))

        row["evidence_ref"] = "audit-other-1"
        with self.assertRaisesRegex(ValueError, "must equal"):
            contract.validate_plan(plan)

    def test_obligations_are_unique_and_canonically_ordered(self):
        plan = self.plan()
        second = copy.deepcopy(plan["obligations"][0])
        second["obligation_id"] = "obligation-000"
        plan["obligations"].append(second)
        with self.assertRaisesRegex(ValueError, "ordered"):
            contract.validate_plan(plan)

        plan["obligations"][1]["obligation_id"] = "obligation-001"
        with self.assertRaisesRegex(ValueError, "repeats"):
            contract.validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
