"""Focused tests for the AuditPlan-to-Batch-Review evidence consumer."""

import copy
from pathlib import Path
import os
import shutil
import sys
import tempfile
import types
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import audit_evidence_runtime
import audit_fingerprint
import audit_plan_contract
import audit_receipt_contract
import changed_scope_evidence_contract
import check_page_contract
import kblib
import metadata_execution_contract
import metadata_property_state
import project_page_state
import record_changed_scope_evidence
import runtime_paths
import substantive_review_contract

from queue_runtime import UPDATE_QUEUE_TOOL_VERSION


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
AT = "2026-08-28T00:00:00Z"


class AuditEvidenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        kernel = self.root / "kernel" / "K12 Quality Assurance"
        kernel.mkdir(parents=True)
        for name in (
                "audit-plan-contract.yaml",
                "audit-receipt-contract.yaml",
                "batch-review-obligation-registry.yaml",
                "changed-scope-check-registry.yaml",
                "deterministic-rendering-contract.yaml",
                "rendering-verification-contract.yaml",
                "substantive-review-contract.yaml"):
            shutil.copy2(
                REPOSITORY / "kernel" / "K12 Quality Assurance" / name,
                kernel / name)
        k00 = self.root / "kernel" / "K00 Standards Control"
        k00.mkdir(parents=True)
        shutil.copy2(
            REPOSITORY / "kernel" / "K00 Standards Control" /
            "control-registry.yaml",
            k00 / "control-registry.yaml")
        self.plan_root = self.root / runtime_paths.AUDIT_PLAN_ROOT
        self.plan_root.mkdir(parents=True)
        page = self.root / "Topics" / "L.md"
        page.parent.mkdir(parents=True)
        page.write_text("# L\n\nCurrent governed content.\n", encoding="utf-8")
        self.page_snapshot = kblib.repository_target_snapshot(
            str(self.root), "Topics/L.md", suffixes=(".md", ".MD"),
            singly_linked=True)
        self.semantic_before_records = [{
            "path": "Topics/L.md",
            "page_sha256": self.page_snapshot.sha256,
            "semantic_content_sha256": SHA_A,
        }]
        self.semantic_before_set_sha = \
            metadata_property_state.semantic_baseline_set_sha256(
                self.semantic_before_records)
        self.metadata_contract = \
            metadata_execution_contract.CompiledMetadataExecutionContract(
                artifact={}, field_rules=(), writer_capabilities=(),
                contract_fingerprint=SHA_A, canonical_bytes=b"")
        self.page_artifact = audit_fingerprint.page_artifact_fingerprint(
            "Topics/L.md", self.page_snapshot.read_text())
        self.item = {
            "id": "B001",
            "state": "open",
            "manifest": ["Topics/L.md"],
            "activation_receipt": "activation-1",
            "transition_receipts": ["opening-1"],
        }
        self.obligation = {
            "obligation_id": "substantive-review-0001",
            "owner_kind": "kernel",
            "owner_rule_id": "k12-12-substantive-correctness-review",
            "kernel_extension_point": None,
            "partition": "invalidated-semantic-review",
            "due_stage": "pre-merge",
            "target": "Topics/L.md",
            "applicability":
                "tier=L AND trigger in [new,needs_rereview,review_by_expired]",
            "evidence_role": "emits",
            "evidence_kind": "audit-receipt",
            "dimension": "content_and_depth",
            "acceptance_predicate": "content-correctness",
            "producer_check": "substantive_review",
            "producer_capability": "substantive-review-attestation-v1",
            "producer_gate_id": None,
            "consumer_gate_id": "batch-review",
            "fingerprint_binding": "evidence-time",
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        self.plan = {
            "schema_version": 1,
            "plan_id": "audit-plan-1",
            "task_id": "task-1",
            "batch_id": "B001",
            "generated_at": AT,
            "queue_revision": 3,
            "queue_state_revision": 5,
            "required_queue_sha256": SHA_A,
            "standards_version": "3.17.0",
            "active_standards_sha256": SHA_B,
            "selected_profile_manifest": "profiles/atlas/profile.md",
            "profile_snapshot_sha256": SHA_C,
            "profile_contract_fingerprint": SHA_D,
            "opening_transition_receipt": "opening-1",
            "artifact_snapshot_sha256": SHA_B,
            "contract_snapshot_sha256": SHA_C,
            "accepted_baseline_sha256": self.semantic_before_set_sha,
            "obligations": [self.obligation],
        }
        self._write_plan(self.plan)
        self.plan_sha = audit_plan_contract.plan_sha256(self.plan)
        self.contract_fingerprint = \
            audit_fingerprint.obligation_contract_fingerprint(
                self.plan, self.obligation)
        self.review = {
            "schema_version": 1,
            "record_kind": "substantive-review-evidence",
            "receipt_id": "review-1",
            "tool": "record_substantive_review",
            "tool_version": "1.0.0",
            "check": "substantive_review",
            "target": "Topics/L.md",
            "result": "pass",
            "details": "independent review passed",
            "checked_at": AT,
            "invalidated_by": None,
            "plan_id": "audit-plan-1",
            "audit_plan_sha256": self.plan_sha,
            "obligation_id": "substantive-review-0001",
            "task_id": "task-1",
            "batch_id": "B001",
            "opening_transition_receipt": "opening-1",
            "standards_version": "3.17.0",
            "active_standards_sha256": SHA_B,
            "selected_profile_manifest": "profiles/atlas/profile.md",
            "profile_snapshot_sha256": SHA_C,
            "profile_contract_fingerprint": SHA_D,
            "page_sha256": self.page_snapshot.sha256,
            "sources_sha256": SHA_C,
            "semantic_content_fingerprint": SHA_B,
            "artifact_fingerprint": self.page_artifact,
            "dependency_fingerprint": SHA_C,
            "contract_fingerprint": self.contract_fingerprint,
            "fingerprint_binding": "evidence-time",
            "acceptance_predicate": "content-correctness",
            "authoring_context_id": "author-1",
            "reviewer_context_id": "reviewer-1",
            "reviewer_role": "reviewer",
            "round": 1,
            "round_1_receipt_id": None,
            "verdict": "passed",
            "findings": [],
        }
        substantive_review_contract.validate_review_receipt(self.review)
        self.full = {
            "schema_version": 1,
            "record_kind": "audit-receipt",
            "receipt_id": "audit-full-1",
            "plan_id": "audit-plan-1",
            "audit_plan_sha256": self.plan_sha,
            "obligation_id": "substantive-review-0001",
            "owner_kind": "kernel",
            "owner_rule_id": "k12-12-substantive-correctness-review",
            "kernel_extension_point": None,
            "task_id": "task-1",
            "batch_id": "B001",
            "opening_transition_receipt": "opening-1",
            "standards_version": "3.17.0",
            "active_standards_sha256": SHA_B,
            "selected_profile_manifest": "profiles/atlas/profile.md",
            "profile_snapshot_sha256": SHA_C,
            "profile_contract_fingerprint": SHA_D,
            "due_stage": "pre-merge",
            "evidence_role": "emits",
            "evidence_kind": "audit-receipt",
            "dimension": "content_and_depth",
            "scope": ["Topics/L.md"],
            "acceptance_predicate": "content-correctness",
            "artifact_fingerprint": self.page_artifact,
            "dependency_fingerprint": SHA_C,
            "contract_fingerprint": self.contract_fingerprint,
            "producer_check": "substantive_review",
            "producer_capability": "substantive-review-attestation-v1",
            "producer_gate_id": None,
            "consumer_gate_id": "batch-review",
            "fingerprint_binding": "evidence-time",
            "verifier": "record_substantive_review",
            "method": "record_substantive_review@1.0.0/substantive_review",
            "evidence_ref": "review-1",
            "checked_at": AT,
            "review_due": None,
            "result": "passed",
            "invalidated_by": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        audit_receipt_contract.validate_audit_receipt(self.full)
        self.catalog = {
            "activation-1": ("receipts/activation.jsonl", {
                "receipt_id": "activation-1",
                "result": "pass",
                "invalidated_by": None,
                "card_bundle_sha256": SHA_A,
            }),
            "opening-1": ("receipts/transitions.jsonl", {
                "receipt_id": "opening-1",
                "tool": "update_queue",
                "tool_version": UPDATE_QUEUE_TOOL_VERSION,
                "result": "pass",
                "invalidated_by": None,
                "before_state": "queued",
                "after_state": "open",
                "target": "B001",
                "task_id": "task-1",
                "semantic_content_protocol":
                    project_page_state.SEMANTIC_FINGERPRINT_PROTOCOL,
                "manifest_semantic_before_records":
                    self.semantic_before_records,
                "manifest_semantic_before_count": 1,
                "manifest_semantic_before_set_sha256":
                    self.semantic_before_set_sha,
                "selected_profile_manifest": "profiles/atlas/profile.md",
                "profile_snapshot_sha256": SHA_C,
                "profile_contract_fingerprint": SHA_D,
                "profile_load_inputs_sha256": SHA_B,
                "metadata_execution_contract_fingerprint": SHA_A,
            }),
            "review-1": ("receipts/reviews.jsonl", self.review),
            "audit-full-1": ("receipts/audit.jsonl", self.full),
        }
        self.result = {
            "root": str(self.root),
            "errors": [],
            "queue": {
                "task_id": "task-1",
                "queue_revision": 3,
                "state_revision": 5,
            },
            "queue_sha256": SHA_A,
            "items_by_id": {"B001": self.item},
            "current_receipt_catalog": self.catalog,
            "_active_standards_authorized_view": {
                "standards_version": "3.17.0",
                "active_standards_sha256": SHA_B,
            },
            "_profile_authorized_view": {
                "selected_profile_manifest": "profiles/atlas/profile.md",
                "profile_snapshot_sha256": SHA_C,
                "profile_contract_fingerprint": SHA_D,
                "profile_load_inputs_sha256": SHA_B,
                "metadata_execution_contract_fingerprint": SHA_A,
                "_metadata_execution_contract": self.metadata_contract,
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _write_plan(self, plan, *, canonical=True):
        path = self.plan_root / (plan["plan_id"] + ".yaml")
        text = kblib.canonical_yaml(plan)
        if not canonical:
            text = "# noncanonical\n" + text
        path.write_text(text, encoding="utf-8")
        return path

    def test_resolves_exact_current_plan_and_receipt_closure(self):
        binding = audit_evidence_runtime.batch_review_evidence(
            self.result, self.item)

        self.assertEqual("audit-plan-1", binding["audit_plan_id"])
        self.assertEqual(
            ".cambium/work_specs/audit-plans/audit-plan-1.yaml",
            binding["audit_plan_path"])
        self.assertEqual(self.plan_sha, binding["audit_plan_sha256"])
        self.assertEqual(["audit-full-1"], binding["audit_receipt_ids"])
        self.assertEqual(
            audit_receipt_contract.receipt_set_sha256([self.full]),
            binding["audit_receipt_set_sha256"])

    def test_open_to_open_hold_clear_does_not_replace_opening_baseline(self):
        result = copy.deepcopy(self.result)
        item = result["items_by_id"]["B001"]
        item["transition_receipts"].append("hold-clear-1")
        result["current_receipt_catalog"]["hold-clear-1"] = (
            "receipts/transitions.jsonl", {
                "receipt_id": "hold-clear-1",
                "tool": "update_queue",
                "tool_version": UPDATE_QUEUE_TOOL_VERSION,
                "result": "pass",
                "invalidated_by": None,
                "before_state": "open",
                "after_state": "open",
                "manifest_semantic_before_set_sha256": SHA_A,
            })

        binding = audit_evidence_runtime.batch_review_evidence(result, item)

        self.assertEqual("audit-plan-1", binding["audit_plan_id"])
        self.assertEqual(
            "opening-1",
            audit_evidence_runtime.current_opening_semantic_context(
                result, "B001")["opening_transition_receipt"])

    def test_post_open_selector_owned_construct_holds_every_stage(self):
        page = self.root / "Topics" / "L.md"
        page.write_text(
            "# L\n\n| A |\n|---|\n| current |\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "contract-gap/HOLD"):
            audit_evidence_runtime.resolve_stage_plan(
                self.result, self.item, "pre-merge", required_state="open")
        with self.assertRaisesRegex(ValueError, "contract-gap/HOLD"):
            audit_evidence_runtime.batch_review_evidence(
                self.result, self.item)

    def test_noncanonical_plan_bytes_fail_closed(self):
        self._write_plan(self.plan, canonical=False)

        with self.assertRaisesRegex(ValueError, "not canonical"):
            audit_evidence_runtime.batch_review_evidence(
                self.result, self.item)

    def test_multiple_current_plans_are_rejected(self):
        second = copy.deepcopy(self.plan)
        second["plan_id"] = "audit-plan-2"
        self._write_plan(second)

        with self.assertRaisesRegex(ValueError, "exactly one.*found 2"):
            audit_evidence_runtime.batch_review_evidence(
                self.result, self.item)

    def test_symlink_plan_is_rejected(self):
        source = self.plan_root / "audit-plan-1.yaml"
        alias = self.plan_root / "alias.yaml"
        try:
            os.symlink(source.name, alias)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")

        with self.assertRaisesRegex(ValueError, "symlink"):
            audit_evidence_runtime.batch_review_evidence(
                self.result, self.item)

    def test_failed_or_invalidated_full_receipt_does_not_satisfy(self):
        for field, value in (("result", "failed"),
                             ("invalidated_by", "superseded-1")):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.full)
                changed[field] = value
                result = copy.deepcopy(self.result)
                result["current_receipt_catalog"]["audit-full-1"] = (
                    "receipts/audit.jsonl", changed)
                with self.assertRaisesRegex(
                        ValueError, "does not discharge"):
                    audit_evidence_runtime.batch_review_evidence(
                        result, result["items_by_id"]["B001"])

    def test_historical_catalog_is_never_used_as_current_evidence(self):
        result = copy.deepcopy(self.result)
        historical = result["current_receipt_catalog"].pop("audit-full-1")
        result["receipt_catalog"] = {"audit-full-1": historical}

        with self.assertRaisesRegex(ValueError, "exactly one current audit-receipt"):
            audit_evidence_runtime.batch_review_evidence(
                result, result["items_by_id"]["B001"])

    def test_duplicate_passing_full_receipts_are_rejected(self):
        duplicate = copy.deepcopy(self.full)
        duplicate["receipt_id"] = "audit-full-2"
        result = copy.deepcopy(self.result)
        result["current_receipt_catalog"]["audit-full-2"] = (
            "receipts/audit.jsonl", duplicate)

        with self.assertRaisesRegex(ValueError, "found 2"):
            audit_evidence_runtime.batch_review_evidence(
                result, result["items_by_id"]["B001"])

    def test_substantive_evidence_fingerprint_must_match_obligation(self):
        result = copy.deepcopy(self.result)
        result["current_receipt_catalog"]["review-1"][1][
            "sources_sha256"] = SHA_A

        with self.assertRaisesRegex(ValueError, "sources_sha256"):
            audit_evidence_runtime.batch_review_evidence(
                result, result["items_by_id"]["B001"])

    def test_round_two_review_requires_current_round_one_evidence(self):
        result = copy.deepcopy(self.result)
        review = result["current_receipt_catalog"]["review-1"][1]
        review["round"] = 2
        review["round_1_receipt_id"] = "review-round-1"
        review["findings"] = [{
            "finding_id": "finding-confirmation-1",
            "severity": "major",
            "statement": "resolved",
            "status": "closed",
            "round_1_finding_id": "finding-1",
        }]

        with self.assertRaisesRegex(ValueError, "round-1.*absent"):
            audit_evidence_runtime.batch_review_evidence(
                result, result["items_by_id"]["B001"])

    def test_wrapper_binding_reports_every_drifted_field(self):
        binding = audit_evidence_runtime.batch_review_evidence(
            self.result, self.item)
        self.assertEqual(
            [], audit_evidence_runtime.wrapper_binding_errors(
                self.result, self.item, dict(binding)))
        wrapper = dict(binding)
        wrapper["audit_plan_path"] = ".cambium/work_specs/wrong.yaml"
        wrapper["audit_receipt_ids"] = []

        errors = audit_evidence_runtime.wrapper_binding_errors(
            self.result, self.item, wrapper)

        self.assertEqual(2, len(errors))
        self.assertTrue(any("audit_plan_path" in row for row in errors))
        self.assertTrue(any("audit_receipt_ids" in row for row in errors))

    def test_dimensionless_gate_evidence_keeps_plan_dimension_only_in_binding(self):
        gate_obligation = {
            "obligation_id": "changed-scope-page-contract",
            "owner_kind": "kernel",
            "owner_rule_id": "k12-05-page-contract-candidates",
            "kernel_extension_point": None,
            "partition": "changed-scope-deterministic",
            "due_stage": "pre-merge",
            "target": "Topics/L.md",
            "applicability":
                "changed-scope-includes-page-contract-applicable-markdown",
            "evidence_role": "triggers",
            "evidence_kind": "gate-receipt",
            "dimension": "structure_and_links",
            "acceptance_predicate": "k12-05-page-contract-candidates",
            "producer_check": "page-contract-summary",
            "producer_capability": None,
            "producer_gate_id": "page-contract",
            "consumer_gate_id": "batch-review",
            "fingerprint_binding": "evidence-time",
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }
        plan = copy.deepcopy(self.plan)
        plan["obligations"] = [gate_obligation]
        self._write_plan(plan)
        plan_sha = audit_plan_contract.plan_sha256(plan)
        registry = changed_scope_evidence_contract.load_registry(self.root)
        control = changed_scope_evidence_contract.load_control_registry(
            self.root)
        row = changed_scope_evidence_contract.registry_row(
            gate_obligation["owner_rule_id"], registry, self.root)
        trace = next(
            entry for entry in record_changed_scope_evidence.producer_trace(
                self.root, registry, control)
            if entry["rule_id"] == row["rule_id"])
        predicate = control[check_page_contract.GATE_ID]
        source = {
            "receipt_id": "raw-page-contract",
            "tool": predicate["tool"],
            "tool_version": predicate["tool_version"],
            "gate_id": check_page_contract.GATE_ID,
            "check": predicate["check"],
            "target": "page-contract",
            "result": "candidate",
            "details": "pages=1 checked=1 fail=0 candidate=0 mode=advisory",
            "checked_at": AT,
            "invalidated_by": None,
            "task_id": plan["task_id"],
            "standards_version": plan["standards_version"],
            "selected_profile_manifest": plan["selected_profile_manifest"],
            "profile_snapshot_sha256": plan["profile_snapshot_sha256"],
            "profile_contract_fingerprint":
                plan["profile_contract_fingerprint"],
            "profile_load_inputs_sha256": SHA_A,
            "compiled_page_contract_sha256": SHA_B,
        }
        frozen = (types.SimpleNamespace(
            path="Topics/L.md", page_sha256=self.page_snapshot.sha256,
            semantic_content_fingerprint=SHA_A,
            snapshot=self.page_snapshot),)
        direct = record_changed_scope_evidence.build_direct_record(
            root=str(self.root), plan=plan, plan_sha256=plan_sha,
            obligation=gate_obligation, row=row, trace=trace,
            registry=registry, control_registry=control, frozen=frozen,
            source_exit_code=2, source_receipts=[source])
        result = copy.deepcopy(self.result)
        result["current_receipt_catalog"].pop("review-1")
        result["current_receipt_catalog"].pop("audit-full-1")
        result["current_receipt_catalog"][direct["receipt_id"]] = (
            "receipts/gates.jsonl", direct)

        binding = audit_evidence_runtime.batch_review_evidence(
            result, result["items_by_id"]["B001"])

        self.assertEqual([], binding["audit_receipt_ids"])
        self.assertEqual(
            "structure_and_links",
            binding["audit_evidence_bindings"][0]["dimension"])
        self.assertIsNone(direct["dimension"])

        tampered = copy.deepcopy(result)
        tampered_record = tampered["current_receipt_catalog"][
            direct["receipt_id"]][1]
        tampered_record["source_receipts"][0]["check"] = "nearby-check"
        with self.assertRaisesRegex(ValueError, "changed-scope direct"):
            audit_evidence_runtime.batch_review_evidence(
                tampered, tampered["items_by_id"]["B001"])


if __name__ == "__main__":
    unittest.main()
