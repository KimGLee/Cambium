"""Owner-focused tests for K12 changed-scope runtime predicates.

The Kernel registry owns rule/check identities and applicability. This file
owns only the three pure runtime predicates and their closed result shape.
AuditPlan selection, evidence/Receipt binding, rendering predicates, and batch
close are exercised by their own primary suites. Card and Read Set parsers
also have their own contract/integration owners; the frozen-reference test
below verifies only how their already-owned findings are projected into this
producer's result.
"""

from pathlib import Path
import sys
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))

import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.execution.audit.changed_scope_evidence_contract as changed_scope_evidence_contract
import Tools.execution.audit.changed_scope_runtime_checks as checks
import Tools.execution.task_runtime.runtime_state_contract as runtime_state_contract


class KernelRegistryBindingContractTests(unittest.TestCase):
    def test_runtime_check_ids_are_an_exact_projection_of_owned_rows(self):
        registry = audit_obligation_projection.load_changed_scope_registry(
            ROOT)
        rows = audit_obligation_projection.validate_changed_scope_registry(
            registry)["base_rules"]
        expected = {
            row["rule_id"]: row["producer_check"]
            for row in rows
            if row["rule_id"] in checks.CHECKS_BY_RULE_ID
        }

        self.assertEqual(dict(checks.CHECKS_BY_RULE_ID), expected)
        self.assertEqual(3, len(expected))
        for row in rows:
            if row["rule_id"] not in expected:
                continue
            self.assertEqual("audit-receipt", row["evidence_kind"])
            self.assertEqual(
                changed_scope_evidence_contract.ADAPTER_CAPABILITY_ID,
                row["producer_capability"])
            self.assertEqual("pre-merge", row["due_stage"])


class GuidanceStateCheckTests(unittest.TestCase):
    @staticmethod
    def record(guidance_id, status):
        return {
            "guidance_id": guidance_id,
            "disposition": "apply-to-current-batch",
            "status": status,
        }

    def test_open_lifecycle_positions_map_to_the_three_owned_counters(self):
        progress = {"guidance_queue": [
            self.record("G-001", "received"),
            self.record("G-002", "classified"),
            self.record("G-003", "mapped"),
            self.record("G-004", "in-progress"),
            self.record("G-005", "verified"),
        ]}

        result = checks.guidance_state_zero_counts(progress)

        self.assertEqual("fail", result["result"])
        self.assertEqual({
            "unclassified_guidance": 1,
            "accepted_unmapped_guidance": 1,
            "implemented_unverified_guidance": 1,
        }, result["metrics"])
        self.assertEqual(
            {"guidance-unclassified", "guidance-accepted-unmapped",
             "guidance-implemented-unverified"},
            {row["diagnostic_id"] for row in result["diagnostics"]})

    def test_mapped_and_machine_owned_final_statuses_clear_all_counters(self):
        statuses = ["mapped", *sorted(
            runtime_state_contract.FINAL_GUIDANCE_STATUSES)]
        progress = {"guidance_queue": [
            self.record("G-%03d" % index, status)
            for index, status in enumerate(statuses, start=1)
        ]}

        result = checks.guidance_state_zero_counts(progress)

        self.assertEqual("pass", result["result"])
        self.assertEqual([], result["diagnostics"])
        self.assertEqual({
            "unclassified_guidance": 0,
            "accepted_unmapped_guidance": 0,
            "implemented_unverified_guidance": 0,
        }, result["metrics"])

    def test_invalid_status_and_missing_explicit_target_fail_closed(self):
        progress = {"guidance_queue": [
            self.record("G-001", "almost-verified"),
        ]}

        invalid = checks.guidance_state_zero_counts(progress)
        missing = checks.guidance_state_zero_counts(progress, ["G-002"])

        diagnostic = invalid["diagnostics"][0]
        self.assertEqual("guidance-status-invalid",
                         diagnostic["diagnostic_id"])
        self.assertEqual(sorted(runtime_state_contract.GUIDANCE_STATUSES),
                         diagnostic["expected"])
        self.assertEqual(["G-002"], missing["scope"]["targets"])
        self.assertEqual("guidance-target-missing",
                         missing["diagnostics"][0]["diagnostic_id"])


class CoverageRoutingCheckTests(unittest.TestCase):
    @staticmethod
    def page(path, disposition="required", authoring_status="drafted",
             batch="B1", next_batch="B1", reason=None):
        return {
            "path": path,
            "coverage_disposition": disposition,
            "authoring_status": authoring_status,
            "batch": batch,
            "next_batch": next_batch,
            "deferred_reason": reason,
        }

    @staticmethod
    def queue(*items):
        return {"required_queue": [
            {"id": item_id, "state": state} for item_id, state in items
        ]}

    def test_routing_failures_are_structured_and_selector_scoped(self):
        coverage = {"pages": [
            self.page("Topics/Changed.md", next_batch=None),
            self.page("Topics/Deferred.md", disposition="deferred",
                      batch=None, next_batch=None, reason=None),
            self.page("Topics/Elsewhere.md", disposition="excluded",
                      batch=None, next_batch=None, reason=None),
        ]}

        complete = checks.coverage_routing_state(
            coverage, self.queue(("B1", "open")))
        selected = checks.coverage_routing_state(
            coverage, self.queue(("B1", "open")), ["Topics/Changed.md"])

        self.assertEqual("fail", complete["result"])
        self.assertEqual({
            "required_without_current_next_batch": 1,
            "deferred_or_excluded_without_reason": 2,
        }, complete["metrics"])
        self.assertEqual(
            {"required-next-batch-missing-or-terminal",
             "coverage-disposition-reason-missing"},
            {row["diagnostic_id"] for row in complete["diagnostics"]})
        self.assertEqual(["Topics/Changed.md"], selected["scope"]["targets"])
        self.assertEqual(
            {"required-next-batch-missing-or-terminal"},
            {row["diagnostic_id"] for row in selected["diagnostics"]})

    def test_opening_and_closed_historical_assignments_are_legal(self):
        opening = checks.coverage_routing_state(
            {"pages": [self.page(
                "Topics/Opening.md", authoring_status="unassessed")]},
            self.queue(("B1", "open")))
        historical = checks.coverage_routing_state(
            {"pages": [
                self.page("Topics/Done.md", authoring_status="reviewed",
                          batch="B1", next_batch=None),
                self.page("Topics/Deferred.md", disposition="deferred",
                          batch=None, next_batch=None,
                          reason="await source"),
                self.page("Topics/Excluded.md", disposition="excluded",
                          batch=None, next_batch=None,
                          reason="outside scope"),
            ]},
            self.queue(("B1", "closed")))

        self.assertEqual("pass", opening["result"])
        self.assertEqual([], opening["diagnostics"])
        self.assertEqual("pass", historical["result"])
        self.assertEqual([], historical["diagnostics"])

    def test_terminal_unknown_and_unregistered_routes_are_not_current(self):
        cases = (
            (self.page("Topics/A.md"), self.queue(("B1", "closed")),
             "closed"),
            (self.page("Topics/A.md"), self.queue(), None),
            (self.page("Topics/A.md", batch="B-UNKNOWN", next_batch=None),
             self.queue(), "B-UNKNOWN"),
        )
        for page, queue, expected in cases:
            with self.subTest(expected=expected):
                result = checks.coverage_routing_state(
                    {"pages": [page]}, queue)
                self.assertEqual("fail", result["result"])
                actual = result["diagnostics"][0]["actual"]
                if expected == "B-UNKNOWN":
                    self.assertEqual(expected, actual["batch"])
                    self.assertIsNone(actual["batch_state"])
                else:
                    self.assertEqual(expected, actual["state"])


class FrozenTaskContractReferenceTests(unittest.TestCase):
    def test_owned_consumer_findings_map_to_one_closed_producer_result(self):
        progress = {"contract": {}}
        item = {"id": "B1"}
        runtime = {"queue": {"task_id": "T1"}}

        with mock.patch.object(
                checks.card_activation, "build_activation_context",
                return_value={"activation_protocol": "current"}) as build, \
                mock.patch.object(
                    checks.card_activation, "activation_context_errors",
                    return_value=[]), \
                mock.patch.object(
                    checks, "live_read_set_load_findings",
                    return_value=([], [])) as read_set_findings:
            passed = checks.frozen_task_contract_references(
                ROOT, progress, item, runtime)

        build.assert_called_once_with(
            ROOT, progress, item, runtime_state=runtime,
            profile_contract=None)
        read_set_findings.assert_called_once_with(ROOT, progress["contract"])
        self.assertEqual("pass", passed["result"])
        self.assertEqual(["B1", "T1"], passed["scope"]["targets"])
        self.assertEqual({
            "activation_context_valid": True,
            "read_set_reference_error_count": 0,
            "read_set_load_closure_gap_count": 0,
        }, passed["metrics"])

        with mock.patch.object(
                checks.card_activation, "build_activation_context",
                return_value={"activation_protocol": "current"}), \
                mock.patch.object(
                    checks.card_activation, "activation_context_errors",
                    return_value=["foreign Card route"]), \
                mock.patch.object(
                    checks, "live_read_set_load_findings",
                    return_value=(["invalid Read Set"], ["missing target"])):
            failed = checks.frozen_task_contract_references(
                ROOT, progress, item, runtime)

        self.assertEqual("fail", failed["result"])
        self.assertEqual(
            {"activation-reference-invalid", "read-set-reference-invalid",
             "read-set-load-closure-omission"},
            {row["diagnostic_id"] for row in failed["diagnostics"]})
        self.assertEqual({
            "activation_context_valid": False,
            "read_set_reference_error_count": 1,
            "read_set_load_closure_gap_count": 1,
        }, failed["metrics"])


class ResultContractTests(unittest.TestCase):
    def test_result_validator_rejects_check_identity_drift(self):
        value = checks.guidance_state_zero_counts({"guidance_queue": []})
        value["check_id"] = checks.COVERAGE_CHECK_ID

        with self.assertRaisesRegex(ValueError, "check_id differs"):
            checks.validate_check_result(value)


if __name__ == "__main__":
    unittest.main()
