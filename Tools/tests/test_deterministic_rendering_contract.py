from pathlib import Path
import copy
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import audit_obligation_projection
import deterministic_rendering_contract as contract


class DeterministicRenderingContractTests(unittest.TestCase):
    def setUp(self):
        self.document = contract.load_contract(REPOSITORY)
        self.values = contract.validate_contract(self.document)
        self.registry = audit_obligation_projection.\
            load_changed_scope_registry(REPOSITORY)

    def test_admitted_predicates_are_exactly_projected_by_registry(self):
        self.assertTrue(contract.validate_registry_projection(
            self.registry, self.document, root=REPOSITORY))
        rows = {row["rule_id"]: row
                for row in self.registry["base_rules"]}
        for predicate in self.values["admitted_predicates"]:
            row = rows[predicate["predicate_id"]]
            self.assertEqual(predicate["dimension"], row["dimension"])
            self.assertEqual("pre-merge", row["due_stage"])
            self.assertEqual("batch-review", row["consumer_gate_id"])

    def test_contract_gaps_cannot_be_projected_as_runnable_passes(self):
        gap_ids = {row["gap_id"] for row in self.values["contract_gaps"]}
        active = {row["rule_id"] for row in self.registry["base_rules"]}
        self.assertTrue(gap_ids)
        self.assertEqual(set(), gap_ids & active)

        invalid = copy.deepcopy(self.registry)
        gap = self.values["contract_gaps"][0]
        invalid["base_rules"].append({
            "rule_id": gap["gap_id"],
            "applicability": "every-changed-markdown-page",
            "producer_capability": "audit-receipt-producer-v1",
            "producer_check": "invented-gap-pass",
            "evidence_role": "emits",
            "evidence_kind": "audit-receipt",
            "dimension": gap["dimension"],
            "dimension_binding": "fixed",
            "consumer_gate_id": "batch-review",
            "due_stage": "pre-merge",
            "nonblocking": False,
        })
        with self.assertRaisesRegex(ValueError, "unresolved K12/02 gaps"):
            contract.validate_registry_projection(
                invalid, self.document, root=REPOSITORY)

    def test_unadmitted_k12_02_rule_cannot_bypass_the_gap_ids(self):
        invalid = copy.deepcopy(self.registry)
        row = copy.deepcopy(invalid["base_rules"][0])
        row.update({
            "rule_id": "k12-02-nearby-invented-pass",
            "producer_check": "nearby-invented-pass",
        })
        invalid["base_rules"].append(row)
        with self.assertRaisesRegex(ValueError, "unadmitted K12/02"):
            contract.validate_registry_projection(
                invalid, self.document, root=REPOSITORY)

    def test_contract_rejects_unregistered_dimension(self):
        invalid = copy.deepcopy(self.document)
        invalid["admitted_predicates"][0]["dimension"] = "layout-ish"
        with self.assertRaisesRegex(ValueError, "dimension is not registered"):
            contract.validate_contract(invalid)


if __name__ == "__main__":
    unittest.main()
