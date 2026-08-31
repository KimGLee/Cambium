"""Representative current Required Queue lifecycles.

Only this suite starts at the base Task runtime and walks every producer to
Task completion.  Local predicates, writer edges, and recovery branches are
owned by Unit, Contract, Integration, or Slow tests at their machine owners.
"""

import json
from pathlib import Path
import subprocess
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.platform.common.kblib as kblib
import Tools.knowledge.content.maintenance_candidates as maintenance_candidates
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION
from Tools.tests.fixtures.e2e import RequiredQueueE2EScenarioCase


class RequiredQueueLifecycleEndToEndTests(RequiredQueueE2EScenarioCase):
    """One representative real lifecycle through Terminal Proof."""

    def test_real_terminal_proof_receipt_completes_task(self):
        self.install_terminal_proof_environment()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        # Terminal Gate receipts and full dimension AuditReceipts have
        # distinct machine owners.  The former are written to the terminal
        # register; the latter remain in the AuditReceipt register produced
        # by the real AuditPlan closure.
        terminal_register = runtime_paths.TERMINAL_AUDIT_RECEIPT_PATH
        audit_register = runtime_paths.AUDIT_RECEIPT_REGISTER_PATH
        completed_queue = self.run_tool(
            "check_queue.py", "--require-complete", "--receipts",
            terminal_register)
        self.assertEqual(0, completed_queue.returncode, completed_queue.stdout)
        completion_receipt = json.loads(
            (self.root / terminal_register).read_text(
                encoding="utf-8").splitlines()[-1]
        )["receipt_id"]
        self.task_transition(
            "completion-candidate", "--queue-check-receipt",
            completion_receipt, "--checkpoint-summary",
            "all Required work units are terminal")
        proof_queue_check = self.run_tool(
            "check_queue.py", "--require-complete", "--receipts",
            terminal_register)
        self.assertEqual(0, proof_queue_check.returncode,
                         proof_queue_check.stdout)
        proof_queue_receipt = json.loads(
            (self.root / terminal_register).read_text(
                encoding="utf-8").splitlines()[-1]
        )["receipt_id"]
        self.assertNotEqual(completion_receipt, proof_queue_receipt)
        corpus_plan_check = self.run_tool(
            "check_corpus_plan.py", "--receipts", terminal_register)
        self.assertEqual(0, corpus_plan_check.returncode,
                         corpus_plan_check.stdout)
        corpus_plan_receipt = json.loads(
            (self.root / terminal_register).read_text(
                encoding="utf-8").splitlines()[-1]
        )["receipt_id"]

        # Dimension coverage consumes the full Kernel-owned AuditReceipts
        # produced by B2's real post-Delta AuditPlan closure.  Queue and Corpus
        # Gate receipts remain their own evidence kinds; they are never
        # relabelled as dimension-specific AuditReceipts merely to satisfy the
        # Terminal Proof schema.
        dimension_receipts = {
            "coverage_and_integration": [],
            "guidance_and_contract": [],
        }
        for line in (self.root / audit_register).read_text(
                encoding="utf-8").splitlines():
            record = json.loads(line)
            dimension = record.get("dimension")
            if (record.get("record_kind") == "audit-receipt" and
                    record.get("batch_id") == "B2" and
                    record.get("result") == "passed" and
                    dimension in dimension_receipts):
                dimension_receipts[dimension].append(record["receipt_id"])
        for dimension, receipt_ids in dimension_receipts.items():
            self.assertTrue(
                receipt_ids,
                "B2 close produced no full AuditReceipt for %s" % dimension,
            )

        proof = kblib.parse_yaml_subset((
            TOOLS / "schemas/terminal_proof.template.yaml"
        ).read_text(encoding="utf-8"))
        progress_contract = kblib.load_yaml_file(
            self.root / queue_runtime.PROGRESS_PATH)["contract"]
        proof.update({
            "task_id": "fixture-task",
            "scope_version": "s1",
            "contract_version": "c1",
            "coverage_ledger_sha256": kblib.sha256_file(
                self.root / queue_runtime.COVERAGE_PATH),
            "progress_ledger_sha256": kblib.sha256_file(
                self.root / queue_runtime.PROGRESS_PATH),
            "required_queue_path": queue_runtime.QUEUE_PATH,
            "queue_revision": self.queue()["queue_revision"],
            "queue_state_revision": self.queue()["state_revision"],
            "required_queue_sha256": kblib.sha256_file(
                self.root / queue_runtime.QUEUE_PATH),
            "remaining_required_work_units": 0,
            "queue_check_receipt": proof_queue_receipt,
            "corpus_plan_check_receipt": corpus_plan_receipt,
            "corpus_plan_semantic_acceptance_receipt": None,
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "selected_profile_manifest": "profiles/test-profile/profile.md",
            **{
                field: progress_contract[field]
                for field in (
                    "selected_route_ids", "selected_card_paths",
                    "selected_profile_route_ids", "selected_read_sets",
                    "loaded_module_paths",
                )
            },
            "guidance_cutoff_id": "G-000",
            "audit_receipt_register": audit_register,
            "terminal_audit_receipt_register": terminal_register,
            "full_deterministic_results": audit_register,
            "incremental_manual_scope": [],
            # K12/16 per-dimension accounting: the two dimensions this fixture
            # actually produced receipts for cite them; the rest carry an
            # explicit not-applicable declaration rather than silence.
            "dimension_coverage": {
                "coverage_and_integration": [
                    *dimension_receipts["coverage_and_integration"]],
                "guidance_and_contract": [
                    *dimension_receipts["guidance_and_contract"]],
                "structure_and_links":
                    "not-applicable: the frozen fixture scope holds no "
                    "authored knowledge page to review for links",
                "content_and_depth":
                    "not-applicable: the frozen fixture scope holds no "
                    "authored knowledge page",
                "formula_and_numeric":
                    "not-applicable: the frozen fixture scope states no "
                    "formula, symbol, numeric example, or metric provenance",
                "source_and_currentness":
                    "not-applicable: the frozen fixture scope cites no "
                    "external source",
                "rendering":
                    "not-applicable: visual_trigger: not_applicable",
            },
        })
        proof_relative = ".cambium/receipts/terminal-proof.yaml"
        (self.root / proof_relative).write_text(
            kblib.canonical_yaml(proof), encoding="utf-8")
        proof_register = ".cambium/receipts/proof-pass.jsonl"
        proof_command = [
            sys.executable, str(TOOLS / "check_proof.py"), proof_relative,
            "--root", str(self.root), "--progress-ledger",
            queue_runtime.PROGRESS_PATH, "--ledger", queue_runtime.COVERAGE_PATH,
            "--receipts", proof_register,
        ]
        proof_check = subprocess.run(
            proof_command, cwd=self.root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, proof_check.returncode, proof_check.stdout)
        proof_receipt = json.loads((self.root / proof_register).read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertEqual("proof-check-summary", proof_receipt["check"])

        self.task_transition(
            "complete", "--terminal-proof-receipt",
            proof_receipt["receipt_id"], "--checkpoint-summary",
            "Terminal Proof passed")
        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("complete", result["progress"]["task_state"])
        self.assertEqual("passed",
                         result["progress"]["terminal_audit"]["state"])
        self.assertEqual(
            proof_receipt["terminal_proof_sha256"],
            result["progress"]["terminal_audit"]["terminal_proof_sha256"],
        )


class MaintenanceCompletionEndToEndTests(RequiredQueueE2EScenarioCase):
    """The sole real maintenance Task lifecycle, from base to completion."""

    def test_maintenance_gate_is_resumable_and_completes_without_terminal_proof(self):
        self.use_maintenance_completion()
        self.merge_and_close("B1", "Topics/A.md")
        self.merge_and_close("B2", "Topics/B.md")
        budget_id, ledger_id, watermark_id = self.write_maintenance_evidence()
        gate_register = ".cambium/receipts/maintenance-gate.jsonl"
        gate_arguments = (
            "check_queue.py", "--require-maintenance-complete",
            "--budget-manifest-receipt", budget_id,
            "--ledger-advance-receipt", ledger_id,
            "--watermark-advance-receipt", watermark_id,
            "--receipts", gate_register,
        )
        first = self.run_tool(*gate_arguments)
        second = self.run_tool(*gate_arguments)
        self.assertEqual(0, first.returncode, first.stdout)
        self.assertEqual(0, second.returncode, second.stdout)
        gates = [json.loads(line) for line in
                 (self.root / gate_register).read_text(
                     encoding="utf-8").splitlines()]
        self.assertEqual(2, len(gates))
        selected = max(
            gates,
            key=lambda receipt: (receipt["checked_at"], receipt["receipt_id"]),
        )
        consumed = next(
            receipt for receipt in gates
            if receipt["receipt_id"] != selected["receipt_id"])
        self.assertEqual("maintenance", selected["completion_semantics"])
        self.assertEqual(["B1", "B2"], selected["terminal_batch_ids"])
        self.assertEqual(
            maintenance_candidates.candidate_state_sha256(
                runtime_validation.validate_runtime(self.root)["coverage"][
                    "maintenance_candidates"]),
            selected["maintenance_candidate_state_sha256"],
        )

        interrupted = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(2, interrupted.returncode, interrupted.stdout)
        self.assertIn(
            "next_action=complete-maintenance-task:%s" %
            selected["receipt_id"], interrupted.stdout)

        self.task_transition(
            "complete", "--maintenance-completion-receipt",
            consumed["receipt_id"], "--checkpoint-summary",
            "bounded maintenance completion gate passed",
        )
        result = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], result["errors"])
        self.assertEqual("complete", result["progress"]["task_state"])
        self.assertEqual(
            "not-applicable", result["progress"]["terminal_audit"]["state"])
        self.assertEqual(
            "passed", result["progress"]["maintenance_completion"]["state"])
        terminal_resume = self.run_tool("check_queue.py", "--resume-status")
        self.assertEqual(0, terminal_resume.returncode, terminal_resume.stdout)
        self.assertIn("next_action=archive-terminal-runtime",
                      terminal_resume.stdout)
        self.assertIn(
            "maintenance_gate.selected=%s" % consumed["receipt_id"],
            terminal_resume.stdout)


if __name__ == "__main__":
    unittest.main()
