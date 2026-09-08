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
from Tools.execution.audit import audit_execution_runtime, batch_review_obligation_contract, check_batch_close
import Tools.execution.task_runtime.runtime_validation as runtime_validation  # noqa: E402
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.tests.fixtures.e2e import RequiredQueueE2EScenarioCase


class RequiredQueueLifecycleEndToEndTests(RequiredQueueE2EScenarioCase):
    """One representative real lifecycle through Terminal Proof."""

    START_SCENARIO = "initial-plan"
    MCP_TRANSPORT = True
    TASK_PAGE_TIERS = {"Topics/A.md": "M"}

    def invoke_tool(self, name, *arguments):
        if name == "check_batch_close.py":
            # The real carried surface includes two intentional, fully
            # qualified README owners. Review exactly that observed candidate,
            # not every duplicate basename or a fabricated passing Receipt.
            graph = check_batch_close._graph_and_basename_check(str(self.root))
            self.assertEqual([], graph["errors"])
            self.assertEqual([{
                "tool": "check_batch_close", "check": "duplicate-markdown-basename",
                "target": "README.md", "result": "candidate",
                "details": "duplicate Markdown basename: Tools/README.md, Tools/knowledge/rendering/README.md",
            }], graph["candidates"])
            candidate = check_batch_close._stable_candidate(
                graph["candidates"][0], "graph_and_duplicate_basenames")
            arguments += ("--accept-candidate-id", candidate["candidate_id"])
        return super().invoke_tool(name, *arguments)

    def prepare_premerge_audit_evidence(self, batch_id):
        if batch_id != "B1":
            return super().prepare_premerge_audit_evidence(batch_id)
        self._drain_activation_delivery()
        prepared = self.run_tool("prepare_audit_plan.py", "--batch", batch_id, "--apply")
        self.assertEqual(0, prepared.returncode, prepared.stdout)
        plan_path = json.loads(prepared.stdout)["plan_path"]
        plan = kblib.load_yaml_file(self.root / plan_path)
        obligations = {row["obligation_id"]: row for row in plan["obligations"]}
        original_bytes = {relative: (self.root / relative).read_bytes()
                          for relative in (plan_path, "Topics/A.md", "profiles/test-profile/profile.toml")}
        reviewed = {}
        withdrew = False
        old_review = None
        # One representative lifecycle uses the real execution projection.
        # These are the fixture reviewer's semantic inputs, not a second
        # obligation registry or a production auto-approval algorithm.
        applicable_fixture_conditions = {
            "always", "when-status-fields-apply",
            "when-failure-behavior-is-genuinely-not-applicable",
        }
        for _ in range(2 * len(obligations) + 10):
            runtime = runtime_validation.validate_runtime(self.root)
            self.assertEqual([], runtime["errors"])
            step = audit_execution_runtime.next_stage_step(
                runtime, runtime["items_by_id"][batch_id], "pre-merge", required_state="open")
            if step["status"] == "complete":
                if withdrew:
                    self.assertNotEqual(old_review["receipt_id"],
                                        reviewed[old_review["obligation_id"]]["receipt_id"])
                    self.assertNotIn(old_review["receipt_id"],
                                     queue_runtime.current_receipt_catalog(runtime))
                    for relative, content in original_bytes.items():
                        self.assertEqual(content, (self.root / relative).read_bytes(), relative)
                    return plan_path, reviewed[old_review["obligation_id"]]["receipt_id"]
                old_review = next(row for row in reviewed.values()
                    if obligations[row["obligation_id"]]["owner_rule_id"] ==
                        "k12-01-m-tier-key-mechanism-or-causal-chain")
                register = self.root / runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH
                history = register.read_bytes()
                arguments = {
                    "root": str(self.root), "event_id": "e2e-correction-one",
                    "subject": [old_review["receipt_id"]], "reason": "incorrect-result",
                    "decision_mode": "own-declaration",
                    "actor_role": old_review["reviewer_role"],
                    "reviewer_context_id": old_review["reviewer_context_id"],
                    "authority_reference": "fixture-reviewer-correction-decision",
                    "statement": "Withdraw the prior mechanism assessment; it omitted the declared boundary.",
                }
                dry = self.mcp_session.call("record_evidence_invalidation", arguments)
                self.assertEqual(0, dry["exit_code"], dry)
                self.assertEqual("planned", dry["stdout_json"]["status"])
                for _retry in range(2):
                    applied = self.mcp_session.call("record_evidence_invalidation", dict(arguments, apply=True))
                    self.assertEqual(0, applied["exit_code"], applied)
                    self.assertEqual("confirmed", applied["stdout_json"]["publication"]["record_confirmation"], applied)
                self.assertEqual(history, register.read_bytes())
                withdrew = True
                continue
            if step["status"] == "invoke":
                tool, arguments = step["tool"], dict(step["arguments"])
                outcome = self.mcp_session.call(tool, dict(arguments, root=str(self.root), apply=True))
            else:
                self.assertIn(step["token"], ("record-batch-page-review", "record-rendering-verification"), step)
                tool, arguments = step["resume_tool"], {}
                if step["token"] == "record-rendering-verification":
                    arguments["rendering_mode"] = "source-only"
                else:
                    obligation = obligations[step["resume_arguments"]["obligation_id"]]
                    spec = batch_review_obligation_contract.obligation_spec_for_rule(obligation["owner_rule_id"])
                    constraints = step["target"]["review_input_constraints"]
                    applicable = (spec["applicability"] in applicable_fixture_conditions or
                                  constraints["required_consumption_obligation_ids"])
                    arguments.update(
                        reviewer_context_id="fixture-review-context", reviewer_role="reviewer",
                        verdict="passed", statement="The synthetic fixture entry meets this bounded checklist item.",
                        applicability_disposition="applicable" if applicable else "not-applicable",
                        applicability_reason=None)
                    if not applicable:
                        arguments["applicability_reason"] = "This isolated synthetic concept contains no corresponding construct or external claim."
                self._drain_activation_delivery()
                observed = self.mcp_session.call("run_task", {"root": str(self.root)})
                self.assertEqual(0, observed["exit_code"], observed)
                action = observed["stdout_json"]
                self.assertEqual(step["token"], action["token"], action)
                relative_input = runtime_paths.TRANSIENT_ROOT + "/e2e-audit-input.json"
                (self.root / relative_input).write_text(json.dumps(arguments), encoding="utf-8")
                outcome = self.mcp_session.call("run_task", {
                    "root": str(self.root), "execute": action["action_id"], "input": relative_input})
                self.assertEqual(0, outcome["exit_code"], outcome)
                execution = outcome["stdout_json"]
                self.assertEqual(0, execution["returncode"], execution)
                self.assertEqual(tool, execution["substeps"][-1]["tool"])
                outcome = dict(outcome, stdout_json=json.loads(execution["output"]))
            self.assertEqual(0, outcome["exit_code"], outcome)
            if tool == "record_batch_page_review":
                receipt_id = outcome["stdout_json"]["receipt_id"]
                body = next(json.loads(line) for line in
                    (self.root / runtime_paths.BATCH_PAGE_REVIEW_RECEIPT_PATH).read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["receipt_id"] == receipt_id)
                reviewed[body["obligation_id"]] = body
        self.fail("M evidence lifecycle did not converge within its frozen obligation bound")

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
