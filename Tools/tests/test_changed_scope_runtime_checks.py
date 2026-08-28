import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import audit_obligation_projection
import changed_scope_runtime_checks as checks
import check_queue
import kblib
import runtime_state_contract
from profile_fixture import install_loadable_profile


class KernelIdentityTests(unittest.TestCase):
    def test_implemented_check_ids_are_derived_from_kernel_registry(self):
        registry = audit_obligation_projection.load_changed_scope_registry(ROOT)
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
            self.assertEqual("audit-receipt-producer-v1",
                             row["producer_capability"])
            self.assertEqual("pre-merge", row["due_stage"])


class GuidanceStateCheckTests(unittest.TestCase):
    def record(self, guidance_id, status):
        return {
            "guidance_id": guidance_id,
            "disposition": "apply-to-current-batch",
            "status": status,
        }

    def test_three_kernel_counters_follow_registered_lifecycle_statuses(self):
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

    def test_mapped_and_machine_registered_final_statuses_are_zero(self):
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

    def test_unknown_status_fails_against_machine_owned_closed_set(self):
        result = checks.guidance_state_zero_counts({
            "guidance_queue": [self.record("G-001", "almost-verified")],
        })

        self.assertEqual("fail", result["result"])
        diagnostic = result["diagnostics"][0]
        self.assertEqual("guidance-status-invalid",
                         diagnostic["diagnostic_id"])
        self.assertEqual(sorted(runtime_state_contract.GUIDANCE_STATUSES),
                         diagnostic["expected"])

    def test_explicit_incremental_scope_reports_missing_identity(self):
        result = checks.guidance_state_zero_counts(
            {"guidance_queue": [self.record("G-001", "verified")]},
            ["G-002"])

        self.assertEqual("fail", result["result"])
        self.assertEqual(["G-002"], result["scope"]["targets"])
        self.assertEqual("guidance-target-missing",
                         result["diagnostics"][0]["diagnostic_id"])


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

    def test_exact_three_coverage_findings_are_structured(self):
        coverage = {"pages": [
            self.page("Topics/Unassessed.md", authoring_status="unassessed"),
            self.page("Topics/Unrouted.md", next_batch=None),
            self.page("Topics/Deferred.md", disposition="deferred",
                      batch=None, next_batch=None, reason=None),
            self.page("Topics/Excluded.md", disposition="excluded",
                      batch=None, next_batch=None, reason=None),
        ]}

        result = checks.coverage_routing_state(
            coverage, self.queue(("B1", "open")))

        self.assertEqual("fail", result["result"])
        self.assertEqual({
            "unassessed": 1,
            "required_without_current_next_batch": 1,
            "deferred_or_excluded_without_reason": 2,
        }, result["metrics"])
        self.assertEqual(
            {"coverage-unassessed",
             "required-next-batch-missing-or-terminal",
             "coverage-disposition-reason-missing"},
            {row["diagnostic_id"] for row in result["diagnostics"]})

    def test_closed_historical_required_assignment_needs_no_next_batch(self):
        coverage = {"pages": [
            self.page("Topics/Done.md", authoring_status="reviewed",
                      batch="B1", next_batch=None),
            self.page("Topics/Deferred.md", disposition="deferred",
                      batch=None, next_batch=None, reason="await source"),
            self.page("Topics/Excluded.md", disposition="excluded",
                      batch=None, next_batch=None, reason="outside scope"),
        ]}

        result = checks.coverage_routing_state(
            coverage, self.queue(("B1", "closed")))

        self.assertEqual("pass", result["result"])
        self.assertEqual([], result["diagnostics"])

    def test_target_scope_does_not_scan_unchanged_records(self):
        coverage = {"pages": [
            self.page("Topics/Changed.md", authoring_status="reviewed"),
            self.page("Topics/Elsewhere.md", authoring_status="unassessed"),
        ]}

        result = checks.coverage_routing_state(
            coverage, self.queue(("B1", "open")), ["Topics/Changed.md"])

        self.assertEqual("pass", result["result"])
        self.assertEqual(["Topics/Changed.md"], result["scope"]["targets"])

    def test_terminal_or_unknown_next_batch_is_not_current_routing(self):
        for queue, expected_state in (
                (self.queue(("B1", "closed")), "closed"),
                (self.queue(), None)):
            with self.subTest(expected_state=expected_state):
                result = checks.coverage_routing_state(
                    {"pages": [self.page("Topics/A.md")]}, queue)
                self.assertEqual("fail", result["result"])
                actual = result["diagnostics"][0]["actual"]
                self.assertEqual(expected_state, actual["state"])

    def test_unknown_historical_batch_cannot_excuse_missing_next_batch(self):
        coverage = {"pages": [
            self.page("Topics/A.md", batch="B-UNKNOWN", next_batch=None),
        ]}

        result = checks.coverage_routing_state(coverage, self.queue())

        self.assertEqual("fail", result["result"])
        actual = result["diagnostics"][0]["actual"]
        self.assertEqual("B-UNKNOWN", actual["batch"])
        self.assertIsNone(actual["batch_state"])


class FrozenTaskContractReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        self.runtime = check_queue.validate_runtime(self.root)
        self.assertEqual([], self.runtime["errors"], self.runtime["errors"])

    def run_check(self, progress=None, runtime=None):
        runtime = runtime or self.runtime
        progress = progress or runtime["progress"]
        return checks.frozen_task_contract_references(
            self.root, progress, runtime["items_by_id"]["B1"], runtime)

    def runtime_with_progress(self, progress):
        # The authorized Profile view deliberately contains immutable
        # mappingproxy contracts, so preserve the admitted opaque authority
        # objects and replace only the two values this test changes.
        runtime = dict(self.runtime)
        runtime["progress"] = progress
        runtime["progress_sha256"] = kblib.sha256_bytes(
            kblib.canonical_yaml(progress))
        return runtime

    def test_valid_frozen_references_pass_both_canonical_consumers(self):
        result = self.run_check()

        self.assertEqual("pass", result["result"], result["diagnostics"])
        self.assertTrue(result["metrics"]["activation_context_valid"])
        self.assertEqual(0,
                         result["metrics"]["read_set_reference_error_count"])
        self.assertEqual(0,
                         result["metrics"]["read_set_load_closure_gap_count"])

    def test_route_card_reference_uses_activation_contract(self):
        progress = copy.deepcopy(self.runtime["progress"])
        progress["contract"]["selected_card_paths"].append(
            "Card/Unregistered.md")
        runtime = self.runtime_with_progress(progress)

        result = self.run_check(progress, runtime)

        self.assertEqual("fail", result["result"])
        self.assertIn("activation-reference-invalid",
                      {row["diagnostic_id"]
                       for row in result["diagnostics"]})

    def test_read_set_closure_omission_uses_task_contract_resolver(self):
        progress = copy.deepcopy(self.runtime["progress"])
        progress["contract"]["loaded_module_paths"] = []
        runtime = self.runtime_with_progress(progress)

        result = self.run_check(progress, runtime)

        self.assertEqual("fail", result["result"])
        self.assertIn("read-set-load-closure-omission",
                      {row["diagnostic_id"]
                       for row in result["diagnostics"]})
        self.assertGreater(
            result["metrics"]["read_set_load_closure_gap_count"], 0)


class ResultContractTests(unittest.TestCase):
    def test_result_validator_rejects_check_identity_drift(self):
        value = checks.guidance_state_zero_counts({"guidance_queue": []})
        value["check_id"] = checks.COVERAGE_CHECK_ID

        with self.assertRaisesRegex(ValueError, "check_id differs"):
            checks.validate_check_result(value)


if __name__ == "__main__":
    unittest.main()
