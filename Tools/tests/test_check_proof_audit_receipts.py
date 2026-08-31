"""Owner-focused Terminal Proof and AuditReceipt consumer tests.

Closed shapes stay in process and derive their expected values from the
Kernel-owned machine contracts.  The only temporary repository in this module
joins one current full AuditReceipt to the Terminal Proof consumer; it does not
replay Task, Queue, or Batch lifecycle setup.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.check_proof as check_proof
import Tools.execution.audit.assemble_terminal_proof as assemble_terminal_proof
import Tools.execution.audit.audit_dimension_contract as audit_dimension_contract
import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime
import Tools.execution.audit.complete_audit_receipt as complete_audit_receipt
import Tools.execution.audit.record_substantive_review as record_substantive_review
import Tools.execution.audit.terminal_proof_contract as terminal_proof_contract
from Tools.tests.support.canonical_registry_fixture import install_isolated_tool_registry_bundle
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

        invented = copy.deepcopy(self.proof)
        invented["dimension_coverage"]["invented_dimension"] = (
            "not-applicable: no object in the frozen scope")
        checks, _cited = self.evaluate(
            invented,
            all_dimensions=all_dimensions,
            authoritative=True,
        )
        self.assertIn("proof-dimension-unregistered", checks)


class TerminalProofAuditReceiptConsumerIntegrationTests(unittest.TestCase):
    """Join one current AuditReceipt chain to its Terminal Proof consumer."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        install_isolated_tool_registry_bundle(cls.root)
        cls.register_relative = ".cambium/receipts/audit-receipts.jsonl"
        cls.register = cls.root / cls.register_relative
        cls.register.parent.mkdir(parents=True)
        cls.plan = {
            "plan_id": "audit-plan-batch-1",
            "task_id": "task-1",
            "batch_id": "batch-1",
            "opening_transition_receipt": "open-1",
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_B,
            "profile_contract_fingerprint": SHA_C,
        }
        substantive = audit_obligation_projection.obligation_spec_for_rule(
            "k12-12-substantive-correctness-review", root=cls.root)
        definition = audit_obligation_projection.resolve_obligation_definition(
            substantive, "Topics/Example.md", trigger="needs_rereview")
        cls.obligation = audit_obligation_projection.required_obligation(
            definition)
        page_text = "# Example\n\nCurrent semantics.\n\n## Sources\n\n- source\n"
        frozen_page = audit_producer_runtime.FrozenPage(
            path=cls.obligation["target"],
            page_sha256=SHA_A,
            semantic_content_fingerprint=SHA_B,
            snapshot=SimpleNamespace(read_text=lambda: page_text),
        )
        cls.producer = record_substantive_review.build_review_receipt(
            root=cls.root,
            result={},
            plan=cls.plan,
            plan_sha256=SHA_D,
            obligation=cls.obligation,
            page=cls.obligation["target"],
            frozen=(frozen_page,),
            authoring_context_id="author-1",
            reviewer_context_id="reviewer-1",
            reviewer_role="reviewer",
            round_number=1,
            verdict="passed",
            findings=[],
            statement="independent substantive review passed",
        )
        cls.receipt = complete_audit_receipt.build_audit_receipt(
            plan=cls.plan,
            plan_sha256=SHA_D,
            obligation=cls.obligation,
            evidence=cls.producer,
        )

    def write_register(self, record):
        self.register.write_text(
            json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    def runtime(self, record=None):
        record = self.receipt if record is None else record
        return {
            "items_by_id": {"batch-1": {"id": "batch-1"}},
            "current_receipt_catalog": {
                record["receipt_id"]: (self.register_relative, record),
                self.producer["receipt_id"]:
                    (".cambium/receipts/producer.jsonl", self.producer),
            },
            "invalidated_evidence_receipt_ids": [],
        }

    def resolved_plan(self, **overrides):
        result = {
            "audit_plan_id": self.plan["plan_id"],
            "audit_plan_path": (
                ".cambium/work_specs/audit-plans/audit-plan-batch-1.yaml"),
            "audit_plan_sha256": SHA_D,
            "plan": self.plan,
            "obligations": (self.obligation,),
        }
        result.update(overrides)
        return result

    def validate(self, record=None, runtime=None, resolved=None, *, write=True,
                 cited_dimension=None):
        record = self.receipt if record is None else record
        if write:
            self.write_register(record)
        runtime = self.runtime(record) if runtime is None else runtime
        resolved = self.resolved_plan() if resolved is None else resolved
        with mock.patch.object(
                check_proof.audit_evidence_runtime, "resolve_stage_plan",
                return_value=resolved):
            return check_proof._validate_dimension_coverage_evidence(
                self.root,
                {"audit_receipt_register": self.register_relative},
                {record["receipt_id"]: (
                    self.obligation["dimension"] if cited_dimension is None
                    else cited_dimension)},
                runtime)

    def test_full_current_audit_receipt_is_the_only_dimension_discharge(self):
        """Exercise the sole Proof -> AuditReceipt -> current-plan seam."""
        self.assertEqual([], self.validate())

        gate = {
            "receipt_id": "gate-1",
            "record_kind": "gate-receipt",
            "dimension": "content_and_depth",
            "result": "pass",
        }
        failures = self.validate(gate)
        self.assertEqual(
            ["proof-dimension-receipt-contract-invalid"],
            [failure[0] for failure in failures])

        self.register.write_text("", encoding="utf-8")
        failures = self.validate(write=False)
        self.assertEqual(
            ["proof-dimension-receipt-missing"],
            [failure[0] for failure in failures],
        )

        current_only_producer = self.runtime()
        current_only_producer["current_receipt_catalog"] = {
            self.producer["receipt_id"]:
                (".cambium/receipts/producer.jsonl", self.producer),
        }
        reference_cases = (
            (
                "not-current",
                current_only_producer,
                "proof-dimension-receipt-not-current",
            ),
            (
                "catalog-bytes",
                self.runtime(dict(
                    self.receipt,
                    method="different@1.0.0/current-record")),
                "proof-dimension-receipt-catalog-mismatch",
            ),
            (
                "adoption-invalidated",
                dict(
                    self.runtime(),
                    invalidated_evidence_receipt_ids=[
                        self.receipt["receipt_id"]],
                ),
                "proof-dimension-receipt-invalidated-evidence",
            ),
        )
        for label, runtime, expected in reference_cases:
            with self.subTest(boundary=label):
                failures = self.validate(runtime=runtime)
                self.assertEqual(expected, failures[0][0], failures)

        discharge_cases = (
            (
                "dimension",
                dict(self.receipt),
                self.resolved_plan(),
                "rendering",
                "proof-dimension-receipt-mismatch",
            ),
            (
                "local-invalidation",
                dict(self.receipt, invalidated_by="superseding-review"),
                self.resolved_plan(),
                None,
                "proof-dimension-receipt-invalidated",
            ),
            (
                "failed-result",
                dict(self.receipt, result="failed"),
                self.resolved_plan(),
                None,
                "proof-dimension-receipt-not-passed",
            ),
            (
                "plan",
                dict(self.receipt),
                self.resolved_plan(audit_plan_id="different-plan"),
                None,
                "proof-dimension-receipt-plan-mismatch",
            ),
            (
                "obligation",
                dict(self.receipt, consumer_gate_id="different-consumer"),
                self.resolved_plan(),
                None,
                "proof-dimension-receipt-obligation-mismatch",
            ),
        )
        for label, record, resolved, cited_dimension, expected in \
                discharge_cases:
            with self.subTest(discharge=label):
                failures = self.validate(
                    record, resolved=resolved,
                    cited_dimension=cited_dimension)
                self.assertEqual(expected, failures[0][0], failures)


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
        self.assertNotEqual(
            projection["audit_receipt_register"],
            projection["terminal_audit_receipt_register"],
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

        conflated = dict(projection)
        conflated["audit_receipt_register"] = \
            conflated["terminal_audit_receipt_register"]
        with self.assertRaisesRegex(ValueError, "canonical path"):
            terminal_proof_contract.validate_proof(conflated, contract)

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
                    "selected_profile_manifest": "profiles/test/profile.md",
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
                    assemble_terminal_proof, "_register_records",
                    return_value={}), mock.patch.object(
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
