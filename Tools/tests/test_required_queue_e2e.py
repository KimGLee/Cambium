"""Representative current Required Queue lifecycles.

Only this suite starts at the base Task runtime and walks every producer to
Task completion.  Local predicates, writer edges, and recovery branches are
owned by Unit, Contract, Integration, or Slow tests at their machine owners.
"""

import json
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

from Tools.execution.task_runtime import queue_runtime
import Tools.execution.audit.assemble_terminal_proof as assemble_terminal_proof
import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime
from Tools.execution.audit import batch_review_obligation_contract, check_batch_close
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.tests.fixtures.e2e import RequiredQueueE2EScenarioCase


class RequiredQueueLifecycleEndToEndTests(RequiredQueueE2EScenarioCase):
    """One representative real lifecycle through Terminal Proof."""

    TASK_PAGE_TIERS = {"Topics/A.md": "M"}

    def fixture_review_input(self, action, obligations):
        # The fixture supplies a real semantic judgment about its deliberately
        # simple concept page; expected obligations come from the frozen plan.
        obligation = obligations[action["target"]["obligation_id"]]
        spec = batch_review_obligation_contract.obligation_spec_for_rule(obligation["owner_rule_id"])
        values = dict(reviewer_context_id="fixture-review-context", reviewer_role="reviewer",
                      verdict="passed", statement="The synthetic concept meets this bounded checklist item.")
        if spec["tier"] == "M":
            constraints = action["target"]["review_input_constraints"]
            applicable = (spec["applicability"] in {
                "always", "when-status-fields-apply",
                "when-failure-behavior-is-genuinely-not-applicable",
            } or bool(constraints["required_consumption_obligation_ids"]))
            values.update(applicability_disposition="applicable" if applicable else "not-applicable",
                          applicability_reason=None if applicable else
                          "The synthetic concept has no corresponding construct or external claim.")
        return values

    def fixture_close_input(self):
        # Review exactly the known, fully qualified README pair. A newly
        # observed candidate is a failure here, not automatically approved.
        graph = check_batch_close._graph_and_basename_check(str(self.root))
        self.assertEqual([], graph["errors"])
        self.assertEqual([{
            "tool": "check_batch_close", "check": "duplicate-markdown-basename",
            "target": "README.md", "result": "candidate",
            "details": "duplicate Markdown basename: Tools/README.md, Tools/knowledge/rendering/README.md",
        }], graph["candidates"])
        candidate = check_batch_close._stable_candidate(
            graph["candidates"][0], "graph_and_duplicate_basenames")
        return dict(integrator="fixture-integrator", reviewer="fixture-reviewer",
                    review_attestation="The independent reviewer confirms this merged fixture batch.",
                    accept_candidate_id=[candidate["candidate_id"]])

    def merge_and_close(self, batch_id, object_path):
        """One real MCP Runner path; never reconstruct owner CLI arguments."""
        if not hasattr(self, "runner_trace"):
            self.runner_trace = []
        initial_call = len(self.mcp_session.calls)
        action = self.mcp_session.call_checked("run_task", {"root": str(self.root)})["stdout_json"]
        deliveries, obligations, reviews = {}, {}, {}
        withdrawn = False
        seen = set()
        original_review = None
        original_plan = None
        # Bound a malfunctioning loop, not the number of Kernel obligations.
        for _ in range(512):
            token, target = action["token"], action["target"]
            self.assertEqual(batch_id, target.get("batch_id"), action)
            # A deliberate semantic withdrawal makes the same frozen
            # obligation due again. Nonprogress is checked within one such
            # externally changed epoch, not across the corrective write.
            position = (action["action_id"], withdrawn)
            self.assertNotIn(position, seen, action)
            seen.add(position)
            semantic, proposal = None, None
            if token == "publish-candidate-delta":
                if batch_id == "B1" and not withdrawn:
                    original_review = next(row for row in reviews.values()
                        if obligations[row["obligation_id"]]["owner_rule_id"] ==
                            "k12-01-m-tier-key-mechanism-or-causal-chain")
                    register = self.root / runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH
                    history = register.read_bytes()
                    # One genuine correction seam; idempotency, dry-run and
                    # permission combinations remain with the invalidation owner.
                    self.mcp_session.call_checked("record_evidence_invalidation", {
                        "root": str(self.root), "event_id": "e2e-correction-one",
                        "subject": [original_review["receipt_id"]], "reason": "incorrect-result",
                        "decision_mode": "own-declaration", "actor_role": original_review["reviewer_role"],
                        "reviewer_context_id": original_review["reviewer_context_id"],
                        "authority_reference": "fixture-reviewer-correction-decision",
                        "statement": "Withdraw the mechanism assessment which omitted the declared boundary.",
                        "apply": True})
                    self.assertEqual(history, register.read_bytes())
                    withdrawn = True
                    action = self.mcp_session.call_checked("run_task", {"root": str(self.root)})["stdout_json"]
                    continue
                proposal = self.proposal_path(batch_id, object_path)
            elif token == "ack-activation-phase":
                key = (target["phase_id"], target["part_index"])
                delivered = deliveries[key]
                semantic = {"phase_nonce": delivered["delivery_nonce"],
                            "phase_delivery_receipt": delivered["receipt_id"]}
            elif token == "record-batch-page-review":
                semantic = self.fixture_review_input(action, obligations)
            elif token == "record-rendering-verification":
                semantic = {"rendering_mode": "source-only"}
            elif token == "record-batch-review":
                semantic = {"statement": "All applicable pre-merge obligations for the fixture were reviewed."}
            elif token == "run-batch-close-gate":
                semantic = self.fixture_close_input()
            else:
                self.assertEqual("invoke", action["disposition"], action)
            execution = self.execute_runner(action, semantic_input=semantic, proposal=proposal)
            child_output = json.loads(execution["output"])
            if token == "prepare-audit-plan":
                plan_path = self.root / child_output["plan_path"]
                original_plan = plan_path.read_bytes()
                plan = kblib.load_yaml_file(plan_path)
                obligations = {row["obligation_id"]: row for row in plan["obligations"]}
            elif token == "deliver-activation-phase":
                self.assertEqual(1, len(child_output))
                delivered = child_output[0]
                self.assertEqual(delivered["delivery_nonce"], delivered["activation_phase_payload"]["delivery_nonce"])
                deliveries[(target["phase_id"], target["part_index"])] = delivered
            elif token == "record-batch-page-review":
                receipt_id = child_output["receipt_id"]
                row = next(json.loads(line) for line in
                    (self.root / runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH).read_text().splitlines()
                    if json.loads(line)["receipt_id"] == receipt_id)
                reviews[row["obligation_id"]] = row
            elif token == "close-applied-batch":
                runtime = runtime_validation.validate_runtime(self.root)
                self.assertEqual([], runtime["errors"])
                self.assertEqual("closed", runtime["items_by_id"][batch_id]["state"])
                self.assertEqual(original_plan, plan_path.read_bytes())
                if original_review is not None:
                    self.assertNotEqual(original_review["receipt_id"],
                                        reviews[original_review["obligation_id"]]["receipt_id"])
                    self.assertNotIn(original_review["receipt_id"], queue_runtime.current_receipt_catalog(runtime))
                trace = [row for row in self.runner_trace if row["batch"] == batch_id]
                tokens = [row["action"] for row in trace]
                for required in ("activate-ready-batch", "prepare-audit-plan", "deliver-activation-phase",
                                 "ack-activation-phase", "publish-candidate-delta", "record-batch-review",
                                 "transition-batch-merge-ready", "apply-delta", "run-batch-close-gate",
                                 "close-applied-batch"):
                    self.assertIn(required, tokens, tokens)
                self.assertLess(tokens.index("publish-candidate-delta"), tokens.index("record-batch-review"))
                self.assertLess(tokens.index("transition-batch-merge-ready"), tokens.index("apply-delta"))
                # No direct producer, publisher or close bypass inside a batch.
                self.assertLessEqual({call["name"] for call in self.mcp_session.calls[initial_call:]},
                                     {"run_task", "record_evidence_invalidation"})
                return
            action = execution["next_action"]
        self.fail("MCP Runner did not reach closed within the bounded lifecycle")

    def test_real_terminal_proof_receipt_completes_task(self):
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

        # The production projection owns the complete two-batch heterogeneous
        # binding.  E2E supplies only the semantic not-applicable reasons; it
        # does not hand-pick evidence IDs from one physical register.
        terminal_runtime = runtime_validation.validate_runtime(self.root)
        self.assertEqual([], terminal_runtime["errors"])
        evidence_rows = audit_evidence_runtime.terminal_dimension_evidence(
            terminal_runtime)
        terminal_dimensions = set(
            audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER)
        terminal_dimensions.update(
            assemble_terminal_proof._profile_receipt_dimensions(
                terminal_runtime))
        covered_dimensions = {row["dimension"] for row in evidence_rows}
        semantic_input = {
            "guidance_cutoff_id": "G-000",
            "manual_review_result": "passed",
            "rendering_evidence":
                "current rendering checks and visual applicability recorded",
            "dimension_not_applicable_reasons": {
                dimension:
                    "the complete closed AuditPlans contain no applicable "
                    "obligation in this dimension"
                for dimension in sorted(
                    terminal_dimensions - covered_dimensions)
            },
            "incremental_manual_scope": [],
            "sampling_scope_and_result":
                "the frozen fixture sampling scope passed",
            "systemic_expansions": [],
            "deferred_evidence_backlog": [],
            "final_handoff": "fixture completion handoff",
            "time_contract_result": "minimum run satisfied",
        }
        input_relative = runtime_paths.TRANSIENT_ROOT + "/terminal-audit-input.yaml"
        input_path = self.root / input_relative
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(kblib.canonical_yaml(semantic_input), encoding="utf-8")
        proof_relative = ".cambium/receipts/terminal-proof.yaml"
        assembled = self.run_tool(
            "assemble_terminal_proof.py", "--terminal-audit-input", input_relative,
            "--queue-check-receipt", proof_queue_receipt,
            "--corpus-plan-check-receipt", corpus_plan_receipt,
            "--audit-receipt-register", audit_register,
            "--terminal-audit-receipt-register", terminal_register,
            "--full-deterministic-results", audit_register,
            "--proof", proof_relative, "--apply", "--json")
        self.assertEqual(0, assembled.returncode,
                         (assembled.stdout, assembled.stderr))
        proof_register = ".cambium/receipts/proof-pass.jsonl"
        proof_check = self.invoke_tool(
            "check_proof.py", proof_relative,
            "--root", str(self.root), "--progress-ledger",
            queue_runtime.PROGRESS_PATH, "--ledger", queue_runtime.COVERAGE_PATH,
            "--receipts", proof_register,
        )
        self.assertEqual(0, proof_check.returncode,
                         (proof_check.stdout, proof_check.stderr))
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
        # Every operation that built this runtime used the same sequential
        # host session. This is not an installation/adoption test: those
        # preconditions still come from the existing Profile fixture owner.
        self.assertTrue(self.mcp_session.calls)
        for call in self.mcp_session.calls:
            envelope = call["response"]["result"]["structuredContent"]
            self.assertEqual("descriptor-retained",
                             envelope["path_capability_assurance"], call)




if __name__ == "__main__":
    unittest.main()
