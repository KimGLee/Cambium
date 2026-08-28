import copy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import audit_obligation_projection
import audit_evidence_runtime
import audit_producer_runtime
import changed_scope_evidence_contract
import changed_scope_rendering_checks
import changed_scope_runtime_checks
import check_links
import check_queue
import check_page_contract
import check_vocab
import complete_audit_receipt
import kblib
import record_changed_scope_evidence as producer
import record_rendering_verification
import rendering_verification_contract

sys.path.insert(0, os.path.join(TOOLS, "tests"))
from profile_fixture import install_loadable_profile


RUNTIME_FIXTURE = os.path.join(
    TOOLS, "tests", "fixtures", "runtime_state", "valid")


def digest(label):
    return kblib.sha256_bytes(label)


class ChangedScopeEvidenceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.registry = producer.load_registry(ROOT)
        cls.control = producer.load_control_registry(ROOT)
        cls.rules = tuple(producer.normalized_base_rules(
            cls.registry, ROOT))
        cls.trace = tuple(producer.producer_trace(
            ROOT, cls.registry, cls.control))

    def row_for_gate(self, gate_id):
        matches = [row for row in self.rules
                   if row.get("producer_gate_id") == gate_id]
        self.assertEqual(1, len(matches))
        return matches[0]

    def context_for_gate(self, gate_id, result):
        row = self.row_for_gate(gate_id)
        trace = next(item for item in self.trace
                     if item["rule_id"] == row["rule_id"])
        spec = audit_obligation_projection.obligation_spec_for_rule(
            row["rule_id"], ROOT)
        target = "README.md"
        definition = audit_obligation_projection.\
            resolve_obligation_definition(spec, target)
        obligation = {
            "obligation_id": "obligation-%s" % gate_id,
            **definition,
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        plan = {
            "plan_id": "audit-plan-test",
            "task_id": "T-1",
            "batch_id": "B-1",
            "opening_transition_receipt": "open-1",
            "standards_version": "K-1",
            "active_standards_sha256": digest("standards"),
            "selected_profile_manifest":
                "profiles/examples/minimal-notes/profile.md",
            "profile_snapshot_sha256": digest("profile"),
            "profile_contract_fingerprint": digest("profile-contract"),
        }
        predicate = self.control[gate_id]
        source = {
            "receipt_id": "raw-%s" % gate_id,
            "tool": predicate["tool"],
            "tool_version": predicate["tool_version"],
            "gate_id": gate_id,
            "check": predicate["check"],
            "target": ("page-contract"
                       if gate_id == check_page_contract.GATE_ID else
                       target),
            "result": result,
            "details": ("pages=1 checked=1 fail=0 candidate=0 mode=advisory"
                        if gate_id == check_page_contract.GATE_ID else
                        "raw exact Gate result"),
            "checked_at": "2026-08-28T00:00:00Z",
            "invalidated_by": None,
            "task_id": plan["task_id"],
            "standards_version": plan["standards_version"],
            "selected_profile_manifest": plan["selected_profile_manifest"],
            "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                plan["profile_contract_fingerprint"],
            "profile_load_inputs_sha256": digest("profile-load-inputs"),
            ("compiled_page_contract_sha256"
             if gate_id == check_page_contract.GATE_ID
             else "compiled_vocab_sha256"): digest("compiled-contract"),
        }
        snapshot = kblib.repository_target_snapshot(
            ROOT, target, suffixes=(".md", ".MD"), singly_linked=True)
        frozen = (types.SimpleNamespace(
            path=target,
            page_sha256=snapshot.sha256,
            semantic_content_fingerprint=digest("page"),
            snapshot=snapshot),)
        return row, trace, plan, obligation, frozen, [source]

    def build(self, gate_id, result, source_exit_code):
        row, trace, plan, obligation, frozen, sources = \
            self.context_for_gate(gate_id, result)
        receipt = producer.build_direct_record(
            root=ROOT, plan=plan, plan_sha256=digest("plan"),
            obligation=obligation, row=row, trace=trace,
            registry=self.registry, control_registry=self.control,
            frozen=frozen, source_exit_code=source_exit_code,
            source_receipts=sources)
        return receipt, row, trace, plan, obligation, frozen, sources

    def test_trace_expected_set_is_derived_from_kernel_registry(self):
        expected = {row["rule_id"] for row in self.rules}
        actual = {row["rule_id"] for row in self.trace}
        self.assertEqual(expected, actual)
        self.assertEqual(len(expected), len(self.trace))

    def test_available_set_is_derived_from_exact_installed_producers(self):
        installed_scopeable = {
            check_page_contract.GATE_ID: (
                check_page_contract.TOOL,
                check_page_contract.TOOL_VERSION,
                check_page_contract.GATE_CHECK),
            check_vocab.GATE_ID: (
                check_vocab.TOOL, check_vocab.TOOL_VERSION,
                check_vocab.GATE_CHECK),
            check_links.GATE_ID: (
                check_links.TOOL, check_links.TOOL_VERSION,
                check_links.GATE_CHECK),
        }
        rendering_projection = rendering_verification_contract.\
            validate_contract(
                rendering_verification_contract.load_contract(ROOT))[
                    "obligation_projection"]
        expected = set()
        for row in self.rules:
            gate_id = row.get("producer_gate_id")
            predicate = self.control.get(gate_id)
            if (gate_id in installed_scopeable and predicate is not None and
                    (predicate["tool"], predicate["tool_version"],
                     predicate["check"]) == installed_scopeable[gate_id] and
                    row["producer_check"] == predicate["check"]):
                expected.add(row["rule_id"])
            pure_owner = changed_scope_evidence_contract.pure_check_owner(
                row["rule_id"], row["producer_check"])
            if (row.get("producer_capability") ==
                    "audit-receipt-producer-v1" and
                    pure_owner is not None):
                expected.add(row["rule_id"])
            if (row["rule_id"] ==
                    rendering_projection["owner_rule_id"] and
                    row["producer_check"] ==
                    rendering_projection["producer_check"] and
                    row["producer_check"] ==
                    record_rendering_verification.CHECK and
                    record_rendering_verification.TOOL ==
                    "record_rendering_verification" and
                    callable(record_rendering_verification.build_record) and
                    callable(record_rendering_verification.
                             validate_record_for_plan)):
                expected.add(row["rule_id"])
        actual = {row["rule_id"] for row in self.trace
                  if row["status"] == "available"}
        self.assertEqual(expected, actual)

    def test_rendering_row_traces_only_to_its_dedicated_strict_producer(self):
        projection = rendering_verification_contract.validate_contract(
            rendering_verification_contract.load_contract(ROOT))[
                "obligation_projection"]
        matches = [row for row in self.trace
                   if row["rule_id"] == projection["owner_rule_id"]]
        self.assertEqual(1, len(matches))
        self.assertEqual("available", matches[0]["status"])
        self.assertEqual("dedicated-rendering-verification-v1",
                         matches[0]["adapter_id"])
        self.assertEqual(record_rendering_verification.TOOL,
                         matches[0]["existing_tool"])
        self.assertEqual(record_rendering_verification.TOOL_VERSION,
                         matches[0]["existing_tool_version"])
        self.assertEqual(record_rendering_verification.CHECK,
                         matches[0]["existing_check"])

    def runtime_context(self, rule_id, *, failing=False):
        row = next(row for row in self.rules if row["rule_id"] == rule_id)
        trace = next(item for item in self.trace
                     if item["rule_id"] == rule_id)
        spec = audit_obligation_projection.obligation_spec_for_rule(
            rule_id, ROOT)
        target = ("Progress.guidance_queue"
                  if rule_id == changed_scope_runtime_checks.GUIDANCE_RULE_ID
                  else "Topics/Changed.md")
        definition = audit_obligation_projection.\
            resolve_obligation_definition(spec, target)
        obligation = {
            "obligation_id": "obligation-%s" % rule_id,
            **definition,
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        plan = {
            "plan_id": "audit-plan-test",
            "task_id": "T-1",
            "batch_id": "B-1",
            "opening_transition_receipt": "open-1",
            "standards_version": "K-1",
            "active_standards_sha256": digest("standards"),
            "selected_profile_manifest":
                "profiles/examples/minimal-notes/profile.md",
            "profile_snapshot_sha256": digest("profile"),
            "profile_contract_fingerprint": digest("profile-contract"),
        }
        frozen = (types.SimpleNamespace(
            path="Topics/Changed.md", page_sha256=digest("page-bytes"),
            semantic_content_fingerprint=digest("page"),
            snapshot=types.SimpleNamespace(
                read_text=lambda: "# Changed\n\n| A |\n|---|\n| ok |\n")),)
        progress = {
            "guidance_queue": [{
                "guidance_id": "G-1",
                "disposition": "apply-to-current-batch",
                "status": "received" if failing else "verified",
            }],
        }
        coverage = {"pages": [{
            "path": "Topics/Changed.md",
            "coverage_disposition": "required",
            "authoring_status": "unassessed" if failing else "drafted",
            "batch": "B-1", "next_batch": "B-1",
            "deferred_reason": None,
        }]}
        queue = {
            "task_id": "T-1",
            "required_queue": [{"id": "B-1", "state": "open"}],
        }
        runtime = {
            "root": ROOT, "progress": progress, "coverage": coverage,
            "queue": queue, "progress_sha256": digest("progress"),
            "coverage_sha256": digest("coverage"),
            "queue_sha256": digest("queue"),
        }
        return {
            "root": ROOT, "result": runtime,
            "item": {"id": "B-1", "manifest": ["Topics/Changed.md"]},
            "plan": plan, "plan_sha256": digest("plan"),
            "registry": self.registry, "control_registry": self.control,
            "obligation": obligation, "row": row, "trace": trace,
            "frozen": frozen,
        }

    def test_missing_exact_producers_are_not_synthesized(self):
        missing = [row for row in self.trace
                   if row["status"] == "missing-exact-producer"]
        self.assertEqual(
            {row["rule_id"] for row in self.rules} -
            {row["rule_id"] for row in self.trace
             if row["status"] == "available"},
            {row["rule_id"] for row in missing})
        for row in missing:
            with self.assertRaisesRegex(
                    producer.ChangedScopeProducerError,
                    "no exact callable producer"):
                producer._trace_for_rule(row["rule_id"], self.trace)

    def test_runtime_check_trace_binds_unique_owner_identity(self):
        for rule_id, check_id in \
                changed_scope_runtime_checks.CHECKS_BY_RULE_ID.items():
            row = next(item for item in self.trace
                       if item["rule_id"] == rule_id)
            self.assertEqual("available", row["status"])
            self.assertEqual(changed_scope_runtime_checks.TOOL,
                             row["existing_tool"])
            self.assertEqual(changed_scope_runtime_checks.TOOL_VERSION,
                             row["existing_tool_version"])
            self.assertEqual(check_id, row["existing_check"])

    def test_rendering_pure_checks_produce_exact_owner_bound_evidence(self):
        for rule_id, check_id in \
                changed_scope_rendering_checks.CHECKS_BY_RULE_ID.items():
            context = self.runtime_context(rule_id)
            result = producer._runtime_check_result(context)
            evidence = producer.build_audit_producer_record(
                context=context, check_result=result)
            self.assertEqual(check_id, evidence["check"])
            self.assertEqual(changed_scope_rendering_checks.TOOL,
                             evidence["check_owner_tool"])
            self.assertEqual(changed_scope_rendering_checks.TOOL_VERSION,
                             evidence["check_owner_tool_version"])
            changed_scope_evidence_contract.\
                validate_audit_producer_record_for_plan(
                    evidence, context["plan"], context["plan_sha256"],
                    context["obligation"], self.registry, self.control,
                    root=ROOT)

    def test_producer_exports_the_consumer_safe_contract_validators(self):
        self.assertIs(changed_scope_evidence_contract.validate_direct_record,
                      producer.validate_direct_record)
        self.assertIs(
            changed_scope_evidence_contract.validate_direct_record_for_plan,
            producer.validate_direct_record_for_plan)
        self.assertIs(
            changed_scope_evidence_contract.validate_audit_producer_record,
            producer.validate_audit_producer_record)

    def test_runtime_result_becomes_strict_completeable_producer_evidence(self):
        for rule_id in (
                changed_scope_runtime_checks.GUIDANCE_RULE_ID,
                changed_scope_runtime_checks.COVERAGE_RULE_ID):
            context = self.runtime_context(rule_id)
            check_result = producer._runtime_check_result(context)
            evidence = producer.build_audit_producer_record(
                context=context, check_result=check_result)
            catalog = {evidence["receipt_id"]: evidence}
            runtime = {"current_receipt_catalog": catalog}
            observed = complete_audit_receipt._producer_evidence(
                ROOT, runtime, evidence["receipt_id"], context["plan"],
                context["plan_sha256"], context["obligation"])
            self.assertEqual(evidence, observed)
            self.assertEqual("audit-producer-evidence",
                             evidence["record_kind"])
            self.assertEqual(context["obligation"]["dimension"],
                             evidence["dimension"])
            changed_scope_evidence_contract.\
                validate_audit_producer_record_for_plan(
                    evidence, context["plan"], context["plan_sha256"],
                    context["obligation"], self.registry, self.control,
                    root=ROOT)

    def test_consumer_contract_rejects_forged_runtime_owner(self):
        context = self.runtime_context(
            changed_scope_runtime_checks.GUIDANCE_RULE_ID)
        evidence = producer.build_audit_producer_record(
            context=context,
            check_result=producer._runtime_check_result(context))
        evidence["check_owner_tool"] = "nearby-check-owner"
        with self.assertRaisesRegex(
                changed_scope_evidence_contract.
                ChangedScopeEvidenceContractError,
                "check_owner_tool"):
            changed_scope_evidence_contract.\
                validate_audit_producer_record_for_plan(
                    evidence, context["plan"], context["plan_sha256"],
                    context["obligation"], self.registry, self.control,
                    root=ROOT)

    def test_runtime_evidence_rejects_changed_exact_result(self):
        context = self.runtime_context(
            changed_scope_runtime_checks.COVERAGE_RULE_ID)
        evidence = producer.build_audit_producer_record(
            context=context,
            check_result=producer._runtime_check_result(context))
        evidence["check_result"]["metrics"]["unassessed"] = 99
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError,
                "check_result_sha256"):
            producer.validate_audit_producer_record(
                evidence, self.registry, self.control, ROOT)

    def test_task_contract_check_is_wrapped_from_admitted_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = os.path.realpath(os.path.join(temporary, "repo"))
            shutil.copytree(RUNTIME_FIXTURE, root)
            install_loadable_profile(Path(root))
            result = check_queue.validate_runtime(root)
            self.assertEqual([], result["errors"], result["errors"])
            item = result["items_by_id"]["B1"]
            rule_id = changed_scope_runtime_checks.TASK_CONTRACT_RULE_ID
            row = next(row for row in self.rules
                       if row["rule_id"] == rule_id)
            trace = next(row for row in self.trace
                         if row["rule_id"] == rule_id)
            spec = audit_obligation_projection.obligation_spec_for_rule(
                rule_id, ROOT)
            obligation = {
                "obligation_id": "obligation-%s" % rule_id,
                **audit_obligation_projection.resolve_obligation_definition(
                    spec, item["id"]),
                "review_due": None,
                "status": "required",
                "evidence_ref": None,
                "reused_receipt_id": None,
                "reuse_reason": None,
            }
            standards = audit_producer_runtime.standards_bindings(result)
            profile = audit_producer_runtime.profile_bindings(result)
            plan = {
                "plan_id": "audit-plan-test",
                "task_id": result["queue"]["task_id"],
                "batch_id": item["id"],
                "opening_transition_receipt": "open-1",
                "standards_version": standards["standards_version"],
                "active_standards_sha256":
                    standards["active_standards_sha256"],
                "selected_profile_manifest":
                    profile["selected_profile_manifest"],
                "profile_snapshot_sha256":
                    profile["profile_snapshot_sha256"],
                "profile_contract_fingerprint":
                    profile["profile_contract_fingerprint"],
            }
            context = {
                "root": root,
                "result": result,
                "item": item,
                "plan": plan,
                "plan_sha256": digest("plan"),
                "registry": self.registry,
                "control_registry": self.control,
                "obligation": obligation,
                "row": row,
                "trace": trace,
                "frozen": audit_producer_runtime.freeze_manifest_pages(
                    root, result, item),
            }

            evidence = producer.produce_evidence(context)

            self.assertEqual("pass", evidence["result"])
            self.assertEqual(rule_id, evidence["check_result"]["rule_id"])
            producer.validate_audit_producer_record_for_context(
                evidence, context)

    def test_page_contract_candidate_stays_dimensionless_gate_evidence(self):
        receipt, row, _trace, _plan, obligation, _frozen, _sources = \
            self.build(check_page_contract.GATE_ID, "candidate", 2)
        self.assertEqual("gate-receipt", receipt["record_kind"])
        self.assertEqual(row["evidence_kind"], receipt["evidence_kind"])
        self.assertIsNone(receipt["dimension"])
        self.assertIsNotNone(obligation["dimension"])
        self.assertEqual("candidate", receipt["result"])

    def test_vocabulary_pass_stays_dimensionless_gate_evidence(self):
        receipt, row, _trace, _plan, obligation, _frozen, _sources = \
            self.build(check_vocab.GATE_ID, "pass", 0)
        self.assertEqual(row["producer_gate_id"],
                         receipt["source_gate_id"])
        self.assertIsNone(receipt["dimension"])
        self.assertIsNotNone(obligation["dimension"])
        self.assertEqual("pass", receipt["result"])

    def test_multi_gate_tool_output_is_projected_to_exact_gate(self):
        _row, _trace, _plan, _obligation, _frozen, sources = \
            self.context_for_gate(check_vocab.GATE_ID, "pass")
        sibling = copy.deepcopy(sources[0])
        sibling.update({
            "receipt_id": "raw-priority-distribution",
            "gate_id": "priority-quota-distribution",
            "check": "priority-quota-distribution",
            "result": "candidate",
        })

        exit_code, selected = producer.select_source_gate_receipts(
            [sources[0], sibling], check_vocab.GATE_ID)

        self.assertEqual(0, exit_code)
        self.assertEqual(sources, selected)

    def test_multi_gate_projection_requires_the_registered_gate(self):
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError,
                "no receipt for Gate frontmatter-vocabulary"):
            producer.select_source_gate_receipts([
                {
                    "receipt_id": "raw-priority-distribution",
                    "gate_id": "priority-quota-distribution",
                }
            ], check_vocab.GATE_ID)

    def test_records_satisfy_the_central_direct_binding_contract(self):
        for gate_id, result, source_exit_code in (
                (check_page_contract.GATE_ID, "candidate", 2),
                (check_vocab.GATE_ID, "pass", 0),
                (check_links.GATE_ID, "pass", 0)):
            receipt, _row, _trace, plan, obligation, _frozen, _sources = \
                self.build(gate_id, result, source_exit_code)
            self.assertEqual(gate_id, receipt["gate_id"])
            self.assertEqual([], audit_evidence_runtime.
                             _direct_binding_errors(
                                 ROOT, plan, digest("plan"), obligation,
                                 receipt))

    def test_direct_record_rejects_manufactured_dimension(self):
        receipt, _row, _trace, _plan, _obligation, _frozen, _sources = \
            self.build(check_page_contract.GATE_ID, "pass", 0)
        receipt["dimension"] = "structure_and_links"
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError, "dimension"):
            producer.validate_direct_record(
                receipt, self.registry, self.control, ROOT)

    def test_direct_record_rejects_wrong_raw_gate_identity(self):
        receipt, _row, _trace, _plan, _obligation, _frozen, _sources = \
            self.build(check_vocab.GATE_ID, "pass", 0)
        receipt["source_receipts"][0]["check"] = "nearby-check"
        receipt["source_receipt_set_sha256"] = kblib.sha256_bytes(
            kblib.canonical_json_bytes(receipt["source_receipts"]))
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError, "exactly one"):
            producer.validate_direct_record(
                receipt, self.registry, self.control, ROOT)

    def test_direct_record_rejects_wrong_non_summary_receipt_identity(self):
        receipt, _row, _trace, _plan, _obligation, _frozen, _sources = \
            self.build(check_page_contract.GATE_ID, "pass", 0)
        sibling = copy.deepcopy(receipt["source_receipts"][0])
        sibling["receipt_id"] = "raw-page-contract-sibling"
        sibling["check"] = "page-contract-finding"
        sibling["task_id"] = "other-task"
        receipt["source_receipts"].insert(0, sibling)
        receipt["source_receipt_set_sha256"] = kblib.sha256_bytes(
            kblib.canonical_json_bytes(receipt["source_receipts"]))
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError,
                "receipt identity is invalid"):
            producer.validate_direct_record(
                receipt, self.registry, self.control, ROOT)

    def test_direct_record_rejects_noncanonical_source_timestamp(self):
        receipt, _row, _trace, _plan, _obligation, _frozen, _sources = \
            self.build(check_vocab.GATE_ID, "pass", 0)
        receipt["source_receipts"][0]["checked_at"] = "yesterday"
        receipt["source_receipt_set_sha256"] = kblib.sha256_bytes(
            kblib.canonical_json_bytes(receipt["source_receipts"]))
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError,
                "receipt identity is invalid"):
            producer.validate_direct_record(
                receipt, self.registry, self.control, ROOT)

    def test_direct_record_rejects_boolean_source_exit_code(self):
        row, trace, plan, obligation, frozen, sources = \
            self.context_for_gate(check_vocab.GATE_ID, "fail")
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError,
                "unregistered exit code"):
            producer.build_direct_record(
                root=ROOT, plan=plan, plan_sha256=digest("plan"),
                obligation=obligation, row=row, trace=trace,
                registry=self.registry, control_registry=self.control,
                frozen=frozen, source_exit_code=True,
                source_receipts=sources)

    def test_direct_record_rejects_raw_exit_receipt_disagreement(self):
        row, trace, plan, obligation, frozen, sources = \
            self.context_for_gate(check_page_contract.GATE_ID, "candidate")
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError, "exit code differs"):
            producer.build_direct_record(
                root=ROOT, plan=plan, plan_sha256=digest("plan"),
                obligation=obligation, row=row, trace=trace,
                registry=self.registry, control_registry=self.control,
                frozen=frozen, source_exit_code=0,
                source_receipts=sources)

    def test_plan_binding_rejects_changed_obligation_definition(self):
        receipt, _row, _trace, plan, obligation, frozen, _sources = \
            self.build(check_page_contract.GATE_ID, "pass", 0)
        changed = copy.deepcopy(obligation)
        changed["acceptance_predicate"] = "invented-weaker-predicate"
        with self.assertRaisesRegex(
                producer.ChangedScopeProducerError, "AuditPlan"):
            producer.validate_direct_record_for_plan(
                receipt, plan, digest("plan"), changed, self.registry,
                self.control,
                audit_producer_runtime.page_artifact_fingerprint(frozen[0]),
                ROOT)

    def test_commands_are_scoped_and_never_append_raw_gate_receipts(self):
        for gate_id in (
                check_page_contract.GATE_ID, check_vocab.GATE_ID,
                check_links.GATE_ID):
            _row, trace, plan, obligation, _frozen, _sources = \
                self.context_for_gate(gate_id, "pass")
            command = producer.gate_command(
                ROOT, plan, obligation["target"], trace)
            self.assertIn("--scope", command)
            self.assertEqual(
                obligation["target"], command[command.index("--scope") + 1])
            self.assertIn("--json", command)
            self.assertNotIn("--receipts", command)


if __name__ == "__main__":
    unittest.main()
