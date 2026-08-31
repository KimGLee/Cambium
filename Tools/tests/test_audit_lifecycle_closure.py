"""Kernel obligation to producer, evidence, and final-consumer closure."""

from pathlib import Path
import copy
import importlib
import os
import shutil
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]

import Tools.execution.audit.audit_evidence_runtime as evidence_runtime
import Tools.execution.audit.audit_execution_runtime as execution_runtime
import Tools.execution.audit.audit_lifecycle_contract as lifecycle
import Tools.execution.audit.audit_obligation_projection as projection
import Tools.execution.audit.audit_plan_contract as audit_plan_contract
import Tools.execution.audit.audit_producer_chain as producer_chain
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope
import Tools.execution.audit.substantive_review_contract as substantive
import Tools.governance.control.metadata_execution_contract as capabilities
import Tools.governance.profile.profile_batch_judgment_contract as judgment
import Tools.knowledge.rendering.rendering_verification_contract as rendering
from Tools.platform.agent_interface.entrypoint_loader import describe_entrypoint


class AuditLifecycleClosureTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.specs = projection.base_obligation_specs(REPOSITORY)
        cls.capabilities = capabilities.load_operation_capabilities(REPOSITORY)

    def capability(self, capability_id):
        rows = [
            row for row in self.capabilities["capabilities"]
            if row["capability_id"] == capability_id
        ]
        self.assertEqual(1, len(rows), capability_id)
        return rows[0]

    def test_every_kernel_spec_has_one_tool_execution_route(self):
        routes = [execution_runtime.producer_route(row) for row in self.specs]

        self.assertNotIn(None, routes)
        for spec, route in zip(self.specs, routes):
            with self.subTest(rule=spec["owner_rule_id"]):
                if spec["due_stage"] == "post-delta-close":
                    self.assertEqual("batch-close-stage", route)
                else:
                    self.assertNotEqual("batch-close-stage", route)

    def test_premerge_audit_plans_freeze_actual_precursor_and_derive_finalizer(self):
        rows = [row for row in self.specs
                if row["due_stage"] == "pre-merge" and
                row["evidence_kind"] == "audit-receipt"]
        self.assertTrue(rows)
        for spec in rows:
            with self.subTest(rule=spec["owner_rule_id"]):
                self.assertIsNone(spec["producer_gate_id"])
                chain = producer_chain.precursor_chain_for_spec(
                    spec, root=REPOSITORY)
                self.assertEqual(spec["producer_capability"],
                                 chain["precursor_capability"])
                self.assertEqual(spec["producer_check"],
                                 chain["precursor_check"])
                self.assertEqual(
                    producer_chain.FINAL_AUDIT_RECEIPT_CAPABILITY,
                    chain["final_producer_capability"])
                self.assertNotEqual(chain["precursor_capability"],
                                    chain["final_producer_capability"])

    def test_complete_chain_resolves_from_one_capability_snapshot(self):
        spec = projection.obligation_spec_for_rule(
            "k12-02-level0-mermaid-fence-closure", REPOSITORY)
        original = capabilities.load_operation_capabilities
        with mock.patch.object(
                capabilities, "load_operation_capabilities",
                wraps=original) as load:
            chain = producer_chain.precursor_chain_for_spec(
                spec, root=REPOSITORY)
        self.assertEqual("changed-scope-evidence-adapter-v1",
                         chain["precursor_capability"])
        self.assertEqual(1, load.call_count)

    def test_changed_scope_contract_import_does_not_resolve_capabilities(self):
        with mock.patch.object(
                capabilities, "load_operation_capabilities",
                side_effect=AssertionError(
                    "capabilities may be resolved only at a call boundary")):
            reloaded = importlib.reload(changed_scope)
        self.assertEqual(
            "changed-scope-evidence-adapter-v1",
            reloaded.ADAPTER_CAPABILITY_ID)

    def test_precursor_owner_entrypoint_shape_and_finalizer_are_closed(self):
        final_consumer = "Tools/execution/audit/audit_evidence_runtime.py"
        finalizer = self.capability(
            producer_chain.FINAL_AUDIT_RECEIPT_CAPABILITY)
        self.assertEqual("producer", finalizer["kind"])
        self.assertEqual(
            "Tools/execution/audit/complete_audit_receipt.py",
            finalizer["implementation_owner"])
        finalizer_descriptor = describe_entrypoint(
            capabilities.capability_invocation_tool(
                producer_chain.FINAL_AUDIT_RECEIPT_CAPABILITY,
                root=REPOSITORY))
        self.assertEqual(finalizer["invocation_owner"],
                         finalizer_descriptor.invocation_path)
        self.assertEqual(finalizer["implementation_owner"],
                         finalizer_descriptor.implementation_path)
        self.assertIn(final_consumer, finalizer["consumers"])

        for spec in self.specs:
            if (spec["due_stage"] != "pre-merge" or
                    spec["evidence_kind"] != "audit-receipt"):
                continue
            with self.subTest(rule=spec["owner_rule_id"]):
                chain = producer_chain.precursor_chain_for_spec(
                    spec, root=REPOSITORY)
                entry = self.capability(chain["precursor_capability"])
                descriptor = describe_entrypoint(chain["precursor_tool"])
                self.assertEqual("producer", entry["kind"])
                self.assertEqual(entry["invocation_owner"],
                                 descriptor.invocation_path)
                self.assertEqual(entry["implementation_owner"],
                                 descriptor.implementation_path)
                self.assertEqual(
                    os.path.basename(entry["invocation_owner"])[:-3],
                    chain["precursor_tool"])
                self.assertIn(final_consumer, entry["consumers"])
                self.assertIn(
                    "Tools/execution/audit/complete_audit_receipt.py",
                    entry["consumers"])
                self.assertEqual(spec["producer_check"],
                                 chain["precursor_check"])
                if spec["source_registry"] == \
                        projection.SUBSTANTIVE_REGISTRY_PATH:
                    expected_kind = substantive.load_contract(
                        REPOSITORY)["record_kind"]
                elif spec["owner_rule_id"] == \
                        "k12-02-rendering-verification-record":
                    expected_kind = rendering.load_contract(
                        REPOSITORY)["record_kind"]
                else:
                    expected_kind = \
                        lifecycle.CHANGED_SCOPE_PRECURSOR_RECORD_KIND
                self.assertEqual(expected_kind,
                                 chain["precursor_record_kind"])

    def test_chain_and_runtime_route_use_the_same_explicit_authority_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            alternate = Path(temporary)
            shutil.copytree(REPOSITORY / "kernel", alternate / "kernel")
            registry = alternate / projection.CHANGED_SCOPE_REGISTRY_PATH
            text = registry.read_text(encoding="utf-8")
            registry.write_text(text.replace(
                "applicability: every-batch-close",
                "applicability: alternate-root-every-batch-close", 1),
                encoding="utf-8")
            spec = projection.obligation_spec_for_rule(
                "k12-05-guidance-state-zero-counts", alternate)
            chain = producer_chain.precursor_chain_for_spec(
                spec, root=alternate)
            self.assertEqual("changed-scope-evidence-adapter-v1",
                             chain["precursor_capability"])
            obligation = projection.resolve_obligation_definition(
                spec, "Progress.guidance_queue")
            self.assertEqual(
                "deterministic-audit-precursor",
                execution_runtime.producer_route(
                    obligation, root=alternate))
            with self.assertRaisesRegex(
                    producer_chain.AuditProducerChainError,
                    "differs from its (registered|Kernel registry)"):
                producer_chain.precursor_chain_for_spec(spec)

    def test_every_capability_route_has_one_registered_producer_and_consumer(self):
        execution_consumer = \
            "Tools/execution/audit/audit_execution_runtime.py"
        for spec in self.specs:
            capability_id = spec.get("producer_capability")
            if capability_id is None:
                continue
            entry = self.capability(capability_id)
            with self.subTest(rule=spec["owner_rule_id"]):
                self.assertEqual("producer", entry["kind"])
                if spec["due_stage"] == "pre-merge":
                    self.assertIn(execution_consumer, entry["consumers"])
                else:
                    self.assertEqual(
                        "batch-close-producer-v1", capability_id)

    def test_gate_routes_and_adapter_are_closed_without_a_second_gate_list(self):
        gate_specs = [row for row in self.specs
                      if row.get("producer_gate_id") is not None]
        registry = changed_scope.load_control_registry(REPOSITORY)
        self.assertEqual(
            {row["producer_gate_id"] for row in gate_specs},
            {row["producer_gate_id"] for row in gate_specs
             if row["producer_gate_id"] in registry},
        )
        adapter = self.capability(changed_scope.ADAPTER_CAPABILITY_ID)
        self.assertIn(
            "Tools/execution/audit/audit_execution_runtime.py",
            adapter["consumers"],
        )

    def test_final_consumer_kinds_equal_all_installed_obligation_kinds(self):
        expected = set(audit_plan_contract.AUDIT_EVIDENCE_KINDS)
        self.assertEqual(expected, evidence_runtime.terminal_evidence_kinds())
        self.assertEqual(
            expected,
            {row["evidence_kind"] for row in self.specs} |
            {"candidate-set-receipt", judgment.RECORD_KIND},
        )

    def test_each_consumer_status_has_one_next_action_interpretation(self):
        expected = {
            "satisfied": "terminal-evidence-complete",
            "ready-for-completion": "complete-precursor",
            "needs-confirmation": "confirm-substantive-review",
            "needs-correction": "external-correction",
            "escalated": "external-escalation",
            "ambiguous": "repair",
            "invalid": "repair",
            "missing": "produce",
        }
        self.assertEqual(
            expected,
            {status: execution_runtime.resolution_route(status)
             for status in expected},
        )
        self.assertEqual(set(expected), lifecycle.RESOLUTION_STATUSES)
        self.assertEqual(set(expected), set(lifecycle.RESOLUTION_ROUTES))
        self.assertIsNone(execution_runtime.resolution_route("future-state"))

    def test_unknown_or_mutated_producer_chain_fails_closed(self):
        spec = projection.obligation_spec_for_rule(
            "k12-02-level0-mermaid-fence-closure", REPOSITORY)
        obligation = projection.resolve_obligation_definition(
            spec, "Topics/Diagram.md")
        chain = producer_chain.precursor_chain_for_obligation(
            obligation, root=REPOSITORY)
        self.assertEqual(
            "audit-producer-evidence", chain["precursor_record_kind"])

        mutated = copy.deepcopy(obligation)
        mutated["producer_check"] = "nearby_unregistered_check"
        with self.assertRaisesRegex(
                producer_chain.AuditProducerChainError,
                "registered|chain"):
            producer_chain.precursor_chain_for_obligation(
                mutated, root=REPOSITORY)

        unknown = copy.deepcopy(obligation)
        unknown["owner_rule_id"] = "k12-02-nearby-unregistered-owner"
        with self.assertRaisesRegex(
                producer_chain.AuditProducerChainError,
                "unknown|chain"):
            producer_chain.precursor_chain_for_obligation(
                unknown, root=REPOSITORY)

    def test_changed_scope_registry_is_rendering_obligation_single_owner(self):
        document = rendering.load_contract(REPOSITORY)
        self.assertNotIn("obligation_projection", document)

        fake_second_owner = copy.deepcopy(document)
        fake_second_owner["obligation_projection"] = {
            "owner_rule_id": "k12-02-rendering-verification-record",
        }
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            rendering.validate_contract(fake_second_owner)

        spec = projection.obligation_spec_for_rule(
            "k12-02-rendering-verification-record", REPOSITORY)
        self.assertEqual(projection.CHANGED_SCOPE_REGISTRY_PATH,
                         spec["source_registry"])
        self.assertEqual("every-batch", spec["applicability"])
        self.assertEqual("rendering", spec["dimension"])

    def test_resolution_machine_rejects_an_unrouted_status(self):
        for status in lifecycle.RESOLUTION_STATUSES:
            self.assertIsNotNone(lifecycle.resolution_route(status))
            lifecycle.validate_resolution({"status": status})
        with self.assertRaisesRegex(
                lifecycle.AuditLifecycleContractError,
                "unregistered resolution status"):
            lifecycle.validate_resolution({"status": "future-state"})


if __name__ == "__main__":
    unittest.main()
