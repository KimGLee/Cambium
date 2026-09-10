from copy import deepcopy
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.batch_close_audit as batch_close_audit
import Tools.execution.audit.batch_close_contract as batch_close_contract
import Tools.execution.audit.check_batch_close as check_batch_close
from Tools.execution.audit import audit_obligation_projection
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.queue_runtime.close_gate as close_gate
from Tools.tests.fixtures.contract import post_delta_objects as objects
from Tools.tests.fixtures.contract.post_delta_objects import SHA_A, SHA_B, SHA_C, SHA_D, SHA_E, SHA_F


class PostDeltaCloseConsumerTests(unittest.TestCase):
    def setUp(self):
        self.profile = objects.profile_binding()
        self.evaluation = object()
        # This suite owns the post-Delta evidence closure, not Profile
        # admission. Supply its admitted input at that explicit boundary.
        admission_boundary = mock.patch.object(close_gate, "_admitted_profile",
            return_value=SimpleNamespace(
                contract=self.profile, manifest_repo_path="profiles/test/profile.toml",
                profile_snapshot_sha256=SHA_A, evaluation=SimpleNamespace(
                    summary_receipt={
                        "selected_profile_manifest": "profiles/test/profile.toml",
                        "profile_snapshot_sha256": SHA_A,
                        "profile_contract_fingerprint": SHA_A,
                        "profile_load_inputs_sha256": SHA_A},
                    metadata_execution_contract=SimpleNamespace(contract_fingerprint=SHA_A),
                    profile_load_inputs_sha256=SHA_A)))
        admission_boundary.start()
        self.addCleanup(admission_boundary.stop)
        self._install_closure(
            tuple(batch_close_contract.CLOSED_LIST_MEMBER_ROWS))

    def _install_closure(self, rows, obligations=None):
        """Build one producer output and its exact close-consumer fixture."""
        self.rows = tuple(dict(row) for row in rows)
        self.stage = objects.plan_stage(self.rows, obligations)
        self.plan = self.stage["plan"]
        self.projection = batch_close_audit.resolve_post_delta_projection(
            self.stage, self.rows, self.profile)
        self.records = {}
        self.final_by_member = {}
        for index, pair in enumerate(self.projection, 1):
            row = pair["member"]
            obligation = pair["obligation"]
            member_id = row["member_id"]
            if row["evidence_kind"] == "gate-receipt":
                final = objects.gate_evidence()
            else:
                final = objects.producer_evidence(self.stage, obligation, index)
            self.records[final["receipt_id"]] = final
            self.final_by_member[member_id] = final

        closure = batch_close_audit.build_post_delta_evidence_set(
            self.stage, self.projection, self.final_by_member, SHA_F)
        self.plan_binding = {
            "audit_plan_id": self.stage["audit_plan_id"],
            "audit_plan_path": self.stage["audit_plan_path"],
            "audit_plan_sha256": self.stage["audit_plan_sha256"],
            "post_delta_evidence_bindings": closure["bindings"],
            "post_delta_evidence_count": len(closure["bindings"]),
            "post_delta_evidence_set_sha256":
                closure["evidence_set_sha256"],
        }
        evidence = {
            member: record["receipt_id"]
            for member, record in self.final_by_member.items()
        }
        self.aggregate = {
            "receipt_id": "aggregate-1",
            "closed_list_evidence": evidence,
        }
        self.attestation = {
            "receipt_id": "attestation-1",
            **self.plan_binding,
        }

    def _plan_obligations(self, specs):
        """Resolve the same registry specs the AuditPlan producer freezes."""
        dimensions = audit_obligation_projection.registered_dimensions(
            specs, self.profile)
        profile_dimension = self.profile.judgment_items[0].dimension_id
        obligations = []
        for spec in specs:
            dimension = (profile_dimension if
                         spec["dimension_binding"] == "profile-registration"
                         else None)
            target = ("page-contract" if spec["producer_gate_id"] is not None
                      else ".")
            definition = audit_obligation_projection.\
                resolve_obligation_definition(
                    spec, target, dimension=dimension,
                    registered_dimensions=dimensions)
            obligations.append(
                audit_obligation_projection.required_obligation(definition))
        return obligations

    def _outer_close_errors(
            self, root, *, mutate_aggregate=None,
            work_spec_path=None, work_spec_sha256=None):
        """Drive the public close consumer far enough to consume K12/09."""
        aggregate = deepcopy(self.aggregate)
        aggregate.update({
            "tool": "check_batch_close",
            "tool_version": check_batch_close.TOOL_VERSION,
            "check": "batch_close_gate",
            "target": "B1",
            "batch_id": "B1",
            "task_id": "task-1",
            "queue_revision": 3,
            "queue_state_revision": 5,
            "required_queue_sha256": SHA_A,
            "coverage_ledger_sha256": SHA_B,
            "progress_ledger_sha256": SHA_C,
            "delta_sha256": SHA_D,
            "queue_consistency_receipt": "queue-consistency-1",
            "delta_apply_receipt": "delta-apply-1",
            "work_spec_path": None,
            "work_spec_sha256": None,
            "corpus_plan_required": False,
            "corpus_plan_triggers": [],
            "corpus_plan_receipt": None,
            "merged_snapshot_sha256": SHA_F,
            "integrator_id": "fixture-integrator",
            "reviewer_id": "fixture-reviewer",
            "reviewer_attestation_receipt": self.attestation["receipt_id"],
            "page_review_receipts": [],
            "result": "pass",
            "invalidated_by": None,
        })
        if mutate_aggregate is not None:
            mutate_aggregate(aggregate)
        attestation = deepcopy(self.attestation)
        attestation.update({
            "tool": "check_batch_close",
            "tool_version": check_batch_close.TOOL_VERSION,
            "check": "batch_global_review_attestation",
            "target": "B1",
            "batch_id": "B1",
            "task_id": "task-1",
            "integrator_id": "fixture-integrator",
            "reviewer_id": "fixture-reviewer",
            "merged_snapshot_sha256": SHA_F,
            "details": "fixture attestation",
            "result": "pass",
            "invalidated_by": None,
        })
        catalog = self.catalog()
        for record in (aggregate, attestation):
            catalog[record["receipt_id"]] = (
                ".cambium/receipts/batch-close.jsonl", record)
        return close_gate.close_gate_receipt_errors(
            catalog, aggregate["receipt_id"], item_id="B1", task_id="task-1",
            root=root, queue_revision=3, queue_state_revision=5,
            required_queue_sha256=SHA_A, coverage_ledger_sha256=SHA_B,
            progress_ledger_sha256=SHA_C, delta_sha256=SHA_D,
            queue_consistency_receipt="queue-consistency-1",
            delta_apply_receipt="delta-apply-1",
            work_spec_path=work_spec_path,
            work_spec_sha256=work_spec_sha256,
            profile_evaluation=self.evaluation,
            current_repository_snapshot_sha256=SHA_F,
            historical=False)

    def test_current_work_spec_binding_is_explicit_and_exact(self):
        cases = (
            (
                "missing",
                lambda receipt: (
                    receipt.pop("work_spec_path"),
                    receipt.pop("work_spec_sha256"),
                ),
                None,
                None,
            ),
            (
                "forged",
                lambda receipt: receipt.update({
                    "work_spec_path": ".cambium/work_specs/forged.yaml",
                    "work_spec_sha256": SHA_A,
                }),
                None,
                None,
            ),
            (
                "prior-binding",
                None,
                ".cambium/work_specs/B1.yaml",
                SHA_A,
            ),
        )
        for name, mutate, expected_path, expected_sha in cases:
            with self.subTest(name=name):
                errors = self._outer_close_errors(
                    None,
                    mutate_aggregate=mutate,
                    work_spec_path=expected_path,
                    work_spec_sha256=expected_sha,
                )
                self.assertTrue(any(
                    "work_spec_path" in error or
                    "work_spec_sha256" in error
                    for error in errors
                ), errors)

    def catalog(self):
        return {
            receipt_id: (
                ".cambium/receipts/batch-close.jsonl",
                record)
            for receipt_id, record in self.records.items()
        }

    def errors(self, aggregate=None, attestation=None,
               catalog=None, root=None):
        return close_gate._post_delta_close_evidence_errors(
            self.catalog() if catalog is None else catalog,
            self.aggregate if aggregate is None else aggregate,
            self.attestation if attestation is None else attestation,
            item_id="B1", task_id="task-1",
            merged_snapshot_sha256=SHA_F,
            root=root,
            profile_evaluation=self.evaluation, historical=False)

    def test_adopter_registry_root_is_shared_by_plan_producer_and_consumer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(REPOSITORY / "kernel", root / "kernel")
            registry_path = (
                root / batch_close_contract.BATCH_CLOSE_CLOSED_LIST_PATH)
            document = batch_close_contract.load_batch_close_closed_list(root)
            variant = next(
                row for row in document["members"]
                if row["dimension_binding"] == "fixed" and
                any(other["dimension_binding"] == "fixed" and
                    other["dimension"] != row["dimension"]
                    for other in document["members"]))
            original_dimension = variant["dimension"]
            variant["dimension"] = next(
                row["dimension"] for row in document["members"]
                if row["dimension_binding"] == "fixed" and
                row["dimension"] != original_dimension)
            registry_path.write_text(
                kblib.canonical_yaml(document), encoding="utf-8")

            rows = batch_close_contract.closed_list_member_rows(root)
            plan_specs = tuple(
                spec for spec in
                audit_obligation_projection.base_obligation_specs(root)
                if spec["source_registry"] ==
                audit_obligation_projection.BATCH_CLOSE_REGISTRY_PATH)
            obligations = self._plan_obligations(plan_specs)
            self._install_closure(rows, obligations)

            member_id = variant["member_id"]
            projected = next(
                pair for pair in self.projection
                if pair["member"]["member_id"] == member_id)
            self.assertEqual(
                variant["dimension"],
                projected["obligation"]["dimension"])

            adopter_errors = self._outer_close_errors(root)
            self.assertFalse(any(
                member_id in error and "registry/plan binding" in error
                for error in adopter_errors), adopter_errors)

            shipped_errors = self._outer_close_errors(None)
            self.assertTrue(any(
                member_id in error and "registry/plan binding" in error
                for error in shipped_errors), shipped_errors)

    def test_accepts_seven_direct_member_facts_and_original_gate(self):
        errors, evidence_ids = self.errors()
        self.assertEqual([], errors)
        self.assertEqual(8, len(evidence_ids))

    def test_current_member_must_use_its_canonical_register(self):
        catalog = self.catalog()
        member = "structural_validity"
        receipt_id = self.aggregate["closed_list_evidence"][member]
        record = catalog[receipt_id][1]
        catalog[receipt_id] = (
            ".cambium/receipts/foreign.jsonl", record)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            "must be stored in .cambium/receipts/batch-close.jsonl"
            in error for error in errors), errors)

    def test_manifest_page_contract_must_remain_original_gate_evidence(self):
        catalog = self.catalog()
        gate_id = self.aggregate["closed_list_evidence"][
            "manifest_page_contract"]
        wrapped = dict(catalog[gate_id][1])
        wrapped["dimension"] = "content_and_depth"
        catalog[gate_id] = (catalog[gate_id][0], wrapped)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            "evidence.dimension" in error
            for error in errors), errors)

    def test_registry_rule_dimension_and_evidence_kind_are_enforced(self):
        for field, value in (("rule_id", "invented-rule"), ("dimension", "rendering"),
                             ("evidence_kind", "invented-evidence")):
            with self.subTest(field=field):
                attestation = deepcopy(self.attestation)
                binding = next(row for row in attestation["post_delta_evidence_bindings"]
                               if row["member_id"] == "coverage_file_count")
                binding[field] = value
                errors, _ids = self.errors(attestation=attestation)
                self.assertTrue(any("registry/plan binding" in error or
                                    "post-Delta evidence closure" in error for error in errors), errors)

    def test_attestation_set_hash_count_and_plan_binding_are_validated(self):
        for field, value, diagnostic in (
                ("post_delta_evidence_set_sha256", SHA_B, "post_delta_evidence_set_sha256"),
                ("post_delta_evidence_count", 7, "post_delta_evidence_count"),
                ("audit_plan_sha256", SHA_B, "post-Delta evidence closure")):
            with self.subTest(field=field):
                attestation = dict(self.attestation, **{field: value})
                errors, _ids = self.errors(attestation=attestation)
                self.assertTrue(any(diagnostic in error for error in errors), errors)

    def test_direct_member_evidence_must_remain_resolvable(self):
        catalog = self.catalog()
        member = "controlled_vocabulary"
        raw_id = self.aggregate["closed_list_evidence"][member]
        catalog.pop(raw_id)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            member in error and "missing receipt" in error
            for error in errors), errors)

    def test_close_references_one_real_review_context(self):
        aggregate = dict(self.aggregate,
            reviewer_attestation_receipt=self.attestation["receipt_id"],
            task_id="task-1", batch_id="B1", merged_snapshot_sha256=SHA_F)
        context = dict(self.attestation,
            receipt_type_id=batch_close_contract.REVIEW_ATTESTATION_RECEIPT_TYPE_ID,
            check="batch_global_review_attestation", result="pass", invalidated_by=None,
            task_id="task-1", batch_id="B1", merged_snapshot_sha256=SHA_F)
        self.assertEqual([], batch_close_contract.review_context_errors(aggregate, context))
        self.assertTrue(batch_close_contract.review_context_errors(aggregate, None))
        for field in ("receipt_id", "receipt_type_id", "check", "result",
                      "invalidated_by", "task_id", "batch_id", "merged_snapshot_sha256"):
            with self.subTest(field=field):
                errors = batch_close_contract.review_context_errors(
                    aggregate, dict(context, **{field: "foreign"}))
                self.assertTrue(any(field in error for error in errors), errors)
        self.assertTrue(set(self.plan_binding).isdisjoint(aggregate))


if __name__ == "__main__":
    unittest.main()
