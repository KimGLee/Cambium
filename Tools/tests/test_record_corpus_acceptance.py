import json
from pathlib import Path
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))

import check_corpus_plan
import kblib
from test_check_corpus_plan import CorpusPlanFixture


class RecordCorpusAcceptanceTests(CorpusPlanFixture):
    def setUp(self):
        super().setUp()
        self.plan_relative = (
            ".cambium/deltas/corpus-plan-acceptances/CPA-001.yaml")
        self.plan_path = self.root / self.plan_relative
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        self.plan = {
            "schema_version": 1,
            "acceptance_id": "CPA-001",
            "authority_role_id": "stopper",
            "decision_scope_id": "corpus-plan-semantic-acceptance",
            "decisions": [{
                "capability_id": "C-1",
                "decision": "accepted",
                "rationale": "The current evidence supports the target outcome.",
            }],
        }
        matrix = self.load_yaml(self.matrix)
        matrix["capabilities"][0]["current_level"] = "Defensible"
        self.write_yaml(self.matrix, matrix)
        self.write_plan()

    def write_plan(self):
        self.plan_path.write_text(
            kblib.canonical_yaml(self.plan), encoding="utf-8")

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "record_corpus_acceptance.py"),
             str(self.root), "--plan", self.plan_relative, *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )

    def test_dry_run_is_json_and_writes_nothing(self):
        completed = self.command()
        self.assertEqual(0, completed.returncode, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["applied"])
        self.assertEqual("current", payload["status"])
        self.assertFalse((
            self.root / ".cambium/receipts/corpus-plan-acceptance.jsonl"
        ).exists())

    def test_apply_writes_distinct_structural_and_semantic_receipts(self):
        completed = self.command("--actor-role", "stopper", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["applied"])
        self.assertEqual("current", payload["status"]["status"])

        receipt_path = (
            self.root / ".cambium/receipts/corpus-plan-acceptance.jsonl")
        rows = [json.loads(line) for line in receipt_path.read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(2, len(rows))
        structural, semantic = rows
        self.assertEqual("check_corpus_plan", structural["tool"])
        self.assertEqual("corpus-plan-structure", structural["gate_id"])
        self.assertEqual("record_corpus_acceptance", semantic["tool"])
        self.assertEqual("corpus-plan-semantic-acceptance",
                         semantic["gate_id"])
        self.assertEqual(structural["receipt_id"],
                         semantic["structural_check_receipt"])
        self.assertEqual("stopper", semantic["authority_role_id"])
        self.assertEqual(self.plan["decisions"],
                         semantic["capability_decisions"])

        projected = subprocess.run(
            [sys.executable, str(TOOLS / "check_corpus_plan.py"),
             str(self.root), "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, projected.returncode, projected.stdout)
        projection = json.loads(projected.stdout)
        self.assertTrue(projection["structural_reconciliation_valid"])
        self.assertNotIn("valid", projection)
        self.assertEqual("current",
                         projection["semantic_acceptance"]["status"])
        self.assertEqual(semantic["receipt_id"],
                         projection["semantic_acceptance"]["receipt_id"])

    def test_apply_requires_exact_profile_authority_role(self):
        completed = self.command("--actor-role", "gatekeeper", "--apply")
        self.assertEqual(1, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertIn("does not equal", " ".join(payload["errors"]))
        self.assertFalse((
            self.root / ".cambium/receipts/corpus-plan-acceptance.jsonl"
        ).exists())

    def test_authority_cannot_accept_capability_below_target(self):
        matrix = self.load_yaml(self.matrix)
        matrix["capabilities"][0]["current_level"] = "Core"
        self.write_yaml(self.matrix, matrix)
        completed = self.command()
        self.assertEqual(1, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertIn("below its target rank", " ".join(payload["errors"]))

    def test_rejected_decision_is_current_failure_evidence(self):
        self.plan["decisions"][0]["decision"] = "rejected"
        self.plan["decisions"][0]["rationale"] = (
            "The evidence does not establish the target outcome.")
        self.write_plan()
        completed = self.command("--actor-role", "stopper", "--apply")
        self.assertEqual(1, completed.returncode, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["applied"])
        self.assertEqual("rejected", payload["status"]["status"])

    def test_artifact_change_makes_prior_acceptance_stale(self):
        completed = self.command("--actor-role", "stopper", "--apply")
        self.assertEqual(0, completed.returncode, completed.stdout)
        global_map = self.load_yaml(self.global_map)
        global_map["entries"][0]["single_responsibility"] = (
            "Own the revised topic A contract.")
        self.write_yaml(self.global_map, global_map)
        result = check_corpus_plan.validate_corpus_plan(self.root)
        self.assertEqual([], result["errors"])
        status = check_corpus_plan.semantic_acceptance_status(result)
        self.assertEqual("stale", status["status"])

    def test_decision_set_must_equal_matrix_order(self):
        self.plan["decisions"] = []
        self.write_plan()
        completed = self.command()
        self.assertEqual(1, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertIn("every current Capability Matrix row",
                      " ".join(payload["errors"]))


if __name__ == "__main__":
    import unittest
    unittest.main()
