"""Owner-focused Terminal Proof dimension-evidence consumer tests.

Closed shapes stay in process and derive their expected values from the
Kernel-owned machine contracts.  Native evidence acceptance is tested by its owner. This module verifies the
closed-plan projection seam without replaying a lifecycle or copying records.
"""

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.check_proof as check_proof
import Tools.execution.audit.assemble_terminal_proof as assemble_terminal_proof
import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.execution.audit.terminal_proof_contract as terminal_proof_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64


def semantic_input():
    """Return caller-owned semantic input, not a duplicate proof shape."""
    return {
        "guidance_cutoff_id": "G-001",
        "manual_review_result": "passed",
        "rendering_evidence": "source and deterministic checks passed",
        "dimension_not_applicable_reasons": {},
        "incremental_manual_scope": ["Topics/Example.md"],
        "sampling_scope_and_result": "bounded sample passed",
        "systemic_expansions": [],
        "deferred_evidence_backlog": [],
        "final_handoff": "handoff-record",
        "time_contract_result": "minimum run satisfied",
    }


class TerminalProofDimensionCoverageUnitTests(unittest.TestCase):
    """Own the process-local Terminal dimension accounting contract.

    The base namespace comes from the Kernel-owned audit-dimension registry;
    the proof shape comes from the Kernel-owned Terminal Proof contract.  These
    tests deliberately pass already-resolved Profile extension outputs into the
    consumer.  Profile parsing itself remains owned by ``test_profile_contract``.
    """

    def setUp(self):
        contract = terminal_proof_contract.load_contract()
        self.proof = terminal_proof_contract.template_projection(contract)
        self.base_dimensions = \
            audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER

    def evaluate(self, proof=None, *, receipt_dimensions=(),
                 all_dimensions=(), authoritative=False):
        failures, cited = check_proof._dimension_coverage_failures(
            self.proof if proof is None else proof,
            receipt_dimensions,
            all_dimensions,
            authoritative,
        )
        return [failure[0] for failure in failures], cited

    def test_base_registry_drives_required_shape_and_atomic_values(self):
        self.assertEqual([], self.evaluate()[0])

        for dimension in self.base_dimensions:
            with self.subTest(case="missing-base", dimension=dimension):
                proof = copy.deepcopy(self.proof)
                proof["dimension_coverage"].pop(dimension)
                checks, _cited = self.evaluate(proof)
                self.assertIn("proof-dimension-missing", checks)

        first, second = self.base_dimensions[:2]
        invalid_values = (
            ("not-applicable:", "proof-dimension-declaration-invalid"),
            ("not in scope", "proof-dimension-declaration-invalid"),
            ([], "proof-dimension-empty"),
            ([None], "proof-dimension-receipt-invalid"),
            ([""], "proof-dimension-receipt-invalid"),
        )
        for value, expected in invalid_values:
            with self.subTest(case="invalid-value", value=value):
                proof = copy.deepcopy(self.proof)
                proof["dimension_coverage"][first] = value
                checks, _cited = self.evaluate(proof)
                self.assertIn(expected, checks)

        proof = copy.deepcopy(self.proof)
        receipt_id = "audit-fixture-shared"
        proof["dimension_coverage"][first] = [receipt_id]
        proof["dimension_coverage"][second] = [receipt_id]
        checks, cited = self.evaluate(proof)
        self.assertIn("proof-dimension-receipt-duplicate", checks)
        self.assertEqual(sorted((first, second))[0], cited[receipt_id])

    def test_resolved_profile_outputs_extend_but_do_not_redefine_shape(self):
        extension = "glossary"
        receipt_dimensions = (extension,)
        all_dimensions = (extension,)

        checks, _cited = self.evaluate(
            receipt_dimensions=receipt_dimensions,
            all_dimensions=all_dimensions,
            authoritative=True,
        )
        self.assertIn("proof-dimension-missing", checks)

        proof = copy.deepcopy(self.proof)
        proof["dimension_coverage"][extension] = (
            "not-applicable: the frozen scope has no glossary object")
        self.assertEqual([], self.evaluate(
            proof,
            receipt_dimensions=receipt_dimensions,
            all_dimensions=all_dimensions,
            authoritative=True,
        )[0])

        proof["dimension_coverage"][extension] = ["audit-glossary-1"]
        checks, cited = self.evaluate(
            proof,
            receipt_dimensions=receipt_dimensions,
            all_dimensions=all_dimensions,
            authoritative=True,
        )
        self.assertEqual([], checks)
        self.assertEqual(extension, cited["audit-glossary-1"])

        review_only = copy.deepcopy(self.proof)
        checks, _cited = self.evaluate(
            review_only,
            all_dimensions=all_dimensions,
            authoritative=True,
        )
        self.assertEqual([], checks)
        review_only["dimension_coverage"][extension] = ["audit-glossary-1"]
        checks, _cited = self.evaluate(
            review_only,
            all_dimensions=all_dimensions,
            authoritative=True,
        )
        self.assertIn("proof-dimension-review-only", checks)
        review_only["dimension_coverage"][extension] = (
            "not-applicable: the frozen scope has no glossary object")
        checks, _cited = self.evaluate(
            review_only,
            all_dimensions=all_dimensions,
            authoritative=True,
        )
        self.assertIn("proof-dimension-review-only", checks)

        invented = copy.deepcopy(self.proof)
        invented["dimension_coverage"]["invented_dimension"] = (
            "not-applicable: no object in the frozen scope")
        checks, _cited = self.evaluate(
            invented,
            all_dimensions=all_dimensions,
            authoritative=True,
        )
        self.assertIn("proof-dimension-unregistered", checks)


class TerminalProofEvidenceConsumerTests(unittest.TestCase):
    """Test the final projection seam; native acceptance has its own owner."""

    def test_plan_selected_evidence_is_exact_and_closure_errors_propagate(self):
        rows = ({
            "batch_id": "B1", "plan_id": "plan-1",
            "obligation_id": "m-content", "dimension": "content_and_depth",
            "evidence_kind": "batch-page-review-record",
            "evidence_ref": "m-current",
        }, {
            "batch_id": "B1", "plan_id": "plan-1",
            "obligation_id": "profile-language", "dimension": "language_quality",
            "evidence_kind": "page-batch-judgment-v2",
            "evidence_ref": "profile-current",
        })
        exact = {row["evidence_ref"]: row["dimension"] for row in rows}
        cases = (
            (exact, []),
            ({"m-current": "content_and_depth"}, ["proof-dimension-evidence-missing"]),
            ({**exact, "foreign-current": "structure_and_links"},
             ["proof-dimension-evidence-foreign"]),
            ({**exact, "dimensionless-page-contract": "structure_and_links"},
             ["proof-dimension-evidence-foreign"]),
            ({**exact, "m-current": "structure_and_links"},
             ["proof-dimension-evidence-missing", "proof-dimension-evidence-mismatch"]),
        )
        runtime = {"test": "already validated closed runtime"}
        for cited, expected in cases:
            with self.subTest(cited=cited), mock.patch.object(
                    check_proof.audit_evidence_runtime,
                    "terminal_dimension_evidence", return_value=rows) as resolve:
                failures = check_proof._validate_dimension_coverage_evidence(
                    cited, runtime)
                self.assertEqual(expected, [row[0] for row in failures])
                resolve.assert_called_once_with(runtime)
        for reason in ("stale input", "withdrawn evidence", "conflicting selection"):
            with self.subTest(reason=reason), mock.patch.object(
                    check_proof.audit_evidence_runtime,
                    "terminal_dimension_evidence", side_effect=ValueError(reason)):
                failures = check_proof._validate_dimension_coverage_evidence(
                    exact, runtime)
                self.assertEqual("proof-dimension-evidence-closure-invalid", failures[0][0])


class TerminalProofContractTests(unittest.TestCase):
    def test_kernel_contract_is_the_template_and_input_shape_owner(self):
        contract = terminal_proof_contract.load_contract()
        terminal_proof_contract.validate_contract(contract)
        projection = terminal_proof_contract.template_projection(contract)
        terminal_proof_contract.validate_proof(projection, contract)
        self.assertEqual(
            set(audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER),
            set(projection["dimension_coverage"]),
        )
        self.assertEqual(
            terminal_proof_contract.render_template(contract),
            (TOOLS / "schemas/terminal_proof.template.yaml").read_text(
                encoding="utf-8"),
        )
        invalid = dict(semantic_input(), task_id="caller-chosen-task")
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            terminal_proof_contract.validate_terminal_audit_input(
                invalid, contract)


    def test_closed_fields_and_fingerprints_derive_from_kernel_contract(self):
        contract = terminal_proof_contract.load_contract()
        values = terminal_proof_contract.contract_values(contract)
        proof = terminal_proof_contract.template_projection(contract)

        for field in values["field_order"]:
            with self.subTest(case="missing-field", field=field):
                incomplete = dict(proof)
                incomplete.pop(field)
                with self.assertRaisesRegex(ValueError, "fields are not closed"):
                    terminal_proof_contract.validate_proof(
                        incomplete, contract)

        sha_fields = [
            field for field, spec in values["fields"].items()
            if spec["type"] == "sha256"
        ]
        self.assertTrue(sha_fields)
        for field in sha_fields:
            with self.subTest(case="invalid-sha", field=field):
                invalid = dict(proof)
                invalid[field] = "sha256:not-a-fingerprint"
                with self.assertRaisesRegex(ValueError, "sha256"):
                    terminal_proof_contract.validate_proof(invalid, contract)


class TerminalProofAssemblerUnitTests(unittest.TestCase):
    def test_semantic_acceptance_uses_corpus_planning_status_owner(self):
        semantic_record = {
            "receipt_id": "semantic-current",
            "structural_check_receipt": "corpus-current",
        }
        corpus = {"errors": [], "runtime": {
            "current_receipt_catalog": {
                semantic_record["receipt_id"]: semantic_record,
            },
        }}
        runtime = {
            "root": "/fixture",
            "_profile_authorized_view": {},
            "_active_standards_authorized_view": {},
        }
        with mock.patch.object(
                assemble_terminal_proof.check_corpus_plan,
                "validate_corpus_plan", return_value=corpus), \
                mock.patch.object(
                    assemble_terminal_proof.check_corpus_plan,
                    "semantic_acceptance_status",
                    return_value={"status": "not-applicable",
                                  "receipt_id": None}):
            self.assertIsNone(
                assemble_terminal_proof._semantic_acceptance_receipt(
                    runtime, SHA_A,
                    structural_receipt_id="corpus-current",
                    terminal_register_records={}))

        with mock.patch.object(
                assemble_terminal_proof.check_corpus_plan,
                "validate_corpus_plan", return_value=corpus), \
                mock.patch.object(
                    assemble_terminal_proof.check_corpus_plan,
                    "semantic_acceptance_status",
                    return_value={"status": "current",
                                  "receipt_id": "semantic-current"}):
            self.assertEqual(
                "semantic-current",
                assemble_terminal_proof._semantic_acceptance_receipt(
                    runtime, SHA_A,
                    structural_receipt_id="corpus-current",
                    terminal_register_records={
                        "semantic-current": semantic_record}))

        with mock.patch.object(
                assemble_terminal_proof.check_corpus_plan,
                "validate_corpus_plan", return_value=corpus), \
                mock.patch.object(
                    assemble_terminal_proof.check_corpus_plan,
                    "semantic_acceptance_status",
                    return_value={"status": "current",
                                  "receipt_id": "semantic-current"}):
            for structural_id, register, expected in (
                    ("different-structural",
                     {"semantic-current": semantic_record}, "linked to"),
                    ("corpus-current", {}, "Terminal Audit receipt register")):
                with self.subTest(expected=expected), self.assertRaisesRegex(
                        assemble_terminal_proof.TerminalProofAssemblyError,
                        expected):
                    assemble_terminal_proof._semantic_acceptance_receipt(
                        runtime, SHA_A,
                        structural_receipt_id=structural_id,
                        terminal_register_records=register)

        for status in (
                "not-recorded", "unavailable", "rejected", "stale",
                "ambiguous"):
            with self.subTest(status=status), mock.patch.object(
                    assemble_terminal_proof.check_corpus_plan,
                    "validate_corpus_plan", return_value=corpus), \
                    mock.patch.object(
                        assemble_terminal_proof.check_corpus_plan,
                        "semantic_acceptance_status",
                        return_value={"status": status, "receipt_id": None}):
                with self.assertRaisesRegex(
                        assemble_terminal_proof.TerminalProofAssemblyError,
                        "semantic acceptance is %s" % status):
                    assemble_terminal_proof._semantic_acceptance_receipt(
                        runtime, SHA_A,
                        structural_receipt_id="corpus-current",
                        terminal_register_records={})

    def test_dimension_coverage_uses_only_closed_plan_selected_evidence(self):
        m_record = {
            "receipt_id": "m-content-current",
            "record_kind": "batch-page-review-record",
        }
        profile_record = {
            "receipt_id": "profile-language-current",
            "record_kind": "page-batch-judgment-v2",
        }
        runtime = {
            "root": str(TOOLS.parent),
            "current_receipt_catalog": {
                m_record["receipt_id"]: m_record,
                profile_record["receipt_id"]: profile_record,
                "foreign-current": {
                    "receipt_id": "foreign-current",
                    "record_kind": "batch-page-review-record",
                },
            },
        }
        rows = ({
            "batch_id": "B001",
            "plan_id": "audit-plan-B001",
            "obligation_id": "m-content",
            "dimension": "content_and_depth",
            "evidence_kind": "batch-page-review-record",
            "evidence_ref": m_record["receipt_id"],
        }, {
            "batch_id": "B001",
            "plan_id": "audit-plan-B001",
            "obligation_id": "profile-language",
            "dimension": "language_quality",
            "evidence_kind": "page-batch-judgment-v2",
            "evidence_ref": profile_record["receipt_id"],
        })
        uncovered = set(
            audit_dimension_contract.BASE_RECEIPT_DIMENSION_ORDER) - {
                "content_and_depth"}
        semantic = semantic_input()
        semantic["dimension_not_applicable_reasons"] = {
            dimension: "the complete closed plans have no applicable object"
            for dimension in uncovered
        }
        with mock.patch.object(
                assemble_terminal_proof,
                "_profile_receipt_dimensions",
                return_value=("language_quality",)), mock.patch.object(
                assemble_terminal_proof.audit_evidence_runtime,
                "terminal_dimension_evidence", return_value=rows):
            coverage = assemble_terminal_proof._dimension_coverage(
                runtime, semantic)
        self.assertEqual(
            [m_record["receipt_id"]], coverage["content_and_depth"])
        self.assertEqual(
            [profile_record["receipt_id"]],
            coverage["language_quality"])
        self.assertNotIn("foreign-current", repr(coverage))

        semantic["dimension_not_applicable_reasons"][
            "content_and_depth"] = "incorrectly declared absent"
        with mock.patch.object(
                assemble_terminal_proof,
                "_profile_receipt_dimensions",
                return_value=("language_quality",)), mock.patch.object(
                assemble_terminal_proof.audit_evidence_runtime,
                "terminal_dimension_evidence", return_value=rows):
            with self.assertRaisesRegex(
                    assemble_terminal_proof.TerminalProofAssemblyError,
                    "reasons supplied despite current receipts"):
                assemble_terminal_proof._dimension_coverage(
                    runtime, semantic)

    def test_assembler_derives_runtime_and_reconciliation_fields(self):
        runtime = {
            "root": "/fixture",
            "errors": [],
            "progress": {
                "task_id": "task-1",
                "task_state": "completion-candidate",
                "terminal_audit": {"state": "ready"},
                "contract": {
                    "scope_version": "scope-1",
                    "contract_version": "contract-1",
                    "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
                    "selected_profile_manifest": "profiles/test/profile.toml",
                    "selected_route_ids": ["R01", "R08", "R12"],
                    "selected_card_paths": ["Card/R01.md"],
                    "selected_profile_route_ids": [],
                    "selected_read_sets": ["Read Set/R01.md"],
                    "loaded_module_paths": [
                        "kernel/K12 Quality Assurance/16 Terminal Proof "
                        "Contract.md",
                    ],
                },
            },
            "queue": {"queue_revision": 3, "state_revision": 7},
            "coverage": {"open_gaps": []},
            "coverage_sha256": SHA_A,
            "progress_sha256": SHA_B,
            "queue_sha256": SHA_C,
            "remaining": 0,
        }
        receipts = [
            {"receipt_id": "queue-pass"},
            {"receipt_id": "corpus-pass"},
        ]
        reconciliation = {
            "reused_receipts": [],
            "superseded_receipts": [],
            "invalidated_receipts": [],
            "unresolved_invalidations": 0,
        }
        with mock.patch.object(
                assemble_terminal_proof.runtime_validation,
                "validate_runtime", return_value=runtime), mock.patch.object(
                assemble_terminal_proof.queue_state,
                "required_queue_completion_errors", return_value=[]), \
                mock.patch.object(
                    assemble_terminal_proof, "_receipt",
                    side_effect=receipts), mock.patch.object(
                    assemble_terminal_proof.receipt_catalogs, "read_receipt_register",
                    side_effect=lambda _root, relative: (
                        {row["receipt_id"]: row for row in receipts}
                        if relative == runtime_paths.
                        TERMINAL_AUDIT_RECEIPT_PATH else {})), mock.patch.object(
                    assemble_terminal_proof, "_dimension_coverage",
                    return_value={"structure_and_links": ["audit-1"]}), \
                mock.patch.object(
                    assemble_terminal_proof,
                    "_semantic_acceptance_receipt", return_value=None), \
                mock.patch.object(
                    assemble_terminal_proof.audit_evidence_runtime,
                    "terminal_plan_reconciliation",
                    return_value=reconciliation), mock.patch.object(
                    assemble_terminal_proof.kblib,
                    "repository_snapshot_sha256", return_value=SHA_D):
            proof = assemble_terminal_proof.assemble_terminal_proof(
                "/fixture", semantic_input(),
                queue_check_receipt="queue-pass",
                corpus_plan_check_receipt="corpus-pass")

        terminal_proof_contract.validate_proof(proof)
        self.assertEqual("task-1", proof["task_id"])
        self.assertEqual(FIXTURE_UPSTREAM_REVISION,
                         proof["upstream_revision_id"])
        self.assertEqual("queue-pass", proof["queue_check_receipt"])
        self.assertEqual("corpus-pass", proof["corpus_plan_check_receipt"])
        self.assertEqual(0, proof["remaining_required_work_units"])


if __name__ == "__main__":
    unittest.main()
