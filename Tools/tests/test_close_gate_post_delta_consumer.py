from copy import deepcopy
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.batch_close_audit as batch_close_audit
import Tools.execution.audit.batch_close_contract as batch_close_contract
import Tools.execution.audit.check_batch_close as check_batch_close
import Tools.knowledge.metadata.check_page_contract as check_page_contract
from Tools.execution.audit import audit_obligation_projection
import Tools.platform.common.kblib as kblib
import Tools.execution.task_runtime.queue_runtime.close_gate as close_gate
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
SHA_E = "sha256:" + "e" * 64
SHA_F = "sha256:" + "f" * 64


class PostDeltaCloseConsumerTests(unittest.TestCase):
    def setUp(self):
        scan = SimpleNamespace(judgment_item_id="residual-judgment")
        judgment = SimpleNamespace(
            judgment_item_id="residual-judgment",
            dimension_id="content_and_depth",
            evidence_role="emits",
        )
        self.profile = SimpleNamespace(
            required_scan=scan, judgment_items=(judgment,))
        self._install_closure(
            tuple(batch_close_contract.CLOSED_LIST_MEMBER_ROWS))

    def _install_closure(self, rows, obligations=None):
        """Build one producer output and its exact close-consumer fixture."""
        self.rows = tuple(dict(row) for row in rows)
        if obligations is None:
            obligations = []
            for row in self.rows:
                binding = row["dimension_binding"]
                dimension = (row["dimension"] if binding == "fixed" else
                             ("content_and_depth" if
                              binding == "profile-registration" else None))
                obligations.append({
                    "obligation_id": "post-delta-%s" % row["member_id"],
                    "owner_kind": "kernel",
                    "owner_rule_id": row["rule_id"],
                    "kernel_extension_point": None,
                    "partition": "mandatory-full-deterministic",
                    "due_stage": row["due_stage"],
                    "target": (
                        "page-contract" if
                        row["evidence_kind"] == "gate-receipt" else "."),
                    "applicability": "always",
                    "evidence_role": row["evidence_role"],
                    "evidence_kind": row["evidence_kind"],
                    "dimension": dimension,
                    "acceptance_predicate": "fixture-%s-passes" %
                        row["member_id"],
                    "producer_check": row["producer_check"],
                    "producer_capability": row.get("producer_capability"),
                    "producer_gate_id": row.get("producer_gate_id"),
                    "consumer_gate_id": row["consumer_gate_id"],
                    "fingerprint_binding": "evidence-time",
                    "review_due": None,
                    "status": "required",
                    "evidence_ref": None,
                    "reused_receipt_id": None,
                    "reuse_reason": None,
                })
        obligations = list(obligations)
        self.plan = {
            "plan_id": "plan-b1",
            "task_id": "task-1",
            "batch_id": "B1",
            "opening_transition_receipt": "open-b1",
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": SHA_B,
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_C,
            "profile_contract_fingerprint": SHA_D,
            "obligations": obligations,
        }
        self.stage = {
            "audit_plan_id": self.plan["plan_id"],
            "audit_plan_path": (
                ".cambium/work_specs/audit-plans/plan-b1.yaml"),
            "audit_plan_sha256": SHA_A,
            "plan": self.plan,
            "obligations": tuple(obligations),
        }
        self.projection = batch_close_audit.resolve_post_delta_projection(
            self.stage, self.rows, self.profile)
        self.records = {}
        self.final_by_member = {}
        self.producer_by_member = {}
        for index, pair in enumerate(self.projection, 1):
            row = pair["member"]
            obligation = pair["obligation"]
            member_id = row["member_id"]
            if row["evidence_kind"] == "gate-receipt":
                final = {
                    "receipt_id": "page-contract-gate",
                    "tool": "check_page_contract",
                    "tool_version": check_page_contract.TOOL_VERSION,
                    "check": "page-contract-summary",
                    "target": "page-contract",
                    "result": "pass",
                    "details": "fixture Gate passed",
                    "checked_at": "2026-08-28T00:00:00Z",
                    "invalidated_by": None,
                    "gate_id": "page-contract",
                }
                raw = final
            else:
                raw = {
                    "receipt_id": "raw-%02d" % index,
                    "tool": "check_batch_close",
                    "tool_version": check_batch_close.TOOL_VERSION,
                    "check": obligation["producer_check"],
                    "target": obligation["target"],
                    "result": "pass",
                    "details": "fixture producer evidence",
                    "checked_at": "2026-08-28T00:00:00Z",
                    "invalidated_by": None,
                    "plan_id": self.stage["audit_plan_id"],
                    "audit_plan_path": self.stage["audit_plan_path"],
                    "audit_plan_sha256": self.stage["audit_plan_sha256"],
                    "obligation_id": obligation["obligation_id"],
                    "task_id": self.plan["task_id"],
                    "batch_id": self.plan["batch_id"],
                    "opening_transition_receipt":
                        self.plan["opening_transition_receipt"],
                    "upstream_revision_id": self.plan["upstream_revision_id"],
                    "active_standards_sha256":
                        self.plan["active_standards_sha256"],
                    "selected_profile_manifest":
                        self.plan["selected_profile_manifest"],
                    "profile_snapshot_sha256":
                        self.plan["profile_snapshot_sha256"],
                    "profile_contract_fingerprint":
                        self.plan["profile_contract_fingerprint"],
                    "fingerprint_binding":
                        obligation["fingerprint_binding"],
                    "merged_snapshot_sha256": SHA_F,
                    "artifact_fingerprint": SHA_F,
                    "dependency_fingerprint": SHA_C,
                    "contract_fingerprint": SHA_E,
                }
                final = batch_close_audit.build_full_audit_receipt(
                    self.stage, pair, raw)
            self.records[raw["receipt_id"]] = raw
            self.records[final["receipt_id"]] = final
            self.final_by_member[member_id] = final
            self.producer_by_member[member_id] = raw

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
        producer_evidence = {
            member: record["receipt_id"]
            for member, record in self.producer_by_member.items()
        }
        self.aggregate = {
            "receipt_id": "aggregate-1",
            "closed_list_evidence": evidence,
            "closed_list_producer_evidence": producer_evidence,
            **self.plan_binding,
        }
        self.global_review = {
            "receipt_id": "global-1",
            "closed_list_evidence": evidence,
            **self.plan_binding,
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
            "global_review_receipt": self.global_review["receipt_id"],
            "reviewer_attestation_receipt": self.attestation["receipt_id"],
            "page_review_receipts": [],
            "result": "pass",
            "invalidated_by": None,
        })
        if mutate_aggregate is not None:
            mutate_aggregate(aggregate)
        global_review = deepcopy(self.global_review)
        global_review.update({
            "tool": "check_batch_close",
            "tool_version": check_batch_close.TOOL_VERSION,
            "check": "batch_global_review",
            "target": "B1",
            "batch_id": "B1",
            "task_id": "task-1",
            "merged_snapshot_sha256": SHA_F,
            "integrator_id": "fixture-integrator",
            "reviewer_id": "fixture-reviewer",
            "reviewer_attestation_receipt": self.attestation["receipt_id"],
            "result": "pass",
            "invalidated_by": None,
        })
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
        for record in (aggregate, global_review, attestation):
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
            authorized_profile_contract=self.profile,
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
            receipt_id: (".cambium/receipts/batch-close.jsonl", record)
            for receipt_id, record in self.records.items()
        }

    def errors(self, aggregate=None, global_review=None, attestation=None,
               catalog=None, root=None):
        return close_gate._post_delta_close_evidence_errors(
            self.catalog() if catalog is None else catalog,
            self.aggregate if aggregate is None else aggregate,
            self.global_review if global_review is None else global_review,
            self.attestation if attestation is None else attestation,
            item_id="B1", task_id="task-1",
            merged_snapshot_sha256=SHA_F,
            receipt_version=check_batch_close.TOOL_VERSION,
            root=root,
            authorized_profile_contract=self.profile, historical=False)

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

    def test_accepts_seven_full_audit_receipts_and_original_gate(self):
        errors, evidence_ids = self.errors()
        self.assertEqual([], errors)
        self.assertEqual(8, len(evidence_ids))

    def test_manifest_page_contract_must_remain_original_gate_evidence(self):
        catalog = self.catalog()
        gate_id = self.aggregate["closed_list_evidence"][
            "manifest_page_contract"]
        wrapped = dict(catalog[gate_id][1])
        wrapped["record_kind"] = "audit-receipt"
        catalog[gate_id] = (catalog[gate_id][0], wrapped)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            "original dimensionless Gate record" in error
            for error in errors), errors)

    def test_raw_producer_receipt_cannot_replace_full_audit_receipt(self):
        catalog = self.catalog()
        member = "structural_validity"
        receipt_id = self.aggregate["closed_list_evidence"][member]
        raw = dict(self.producer_by_member[member])
        raw["receipt_id"] = receipt_id
        catalog[receipt_id] = (catalog[receipt_id][0], raw)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            "full AuditReceipt" in error for error in errors), errors)

    def test_registry_rule_dimension_and_evidence_kind_are_enforced(self):
        catalog = self.catalog()
        member = "coverage_file_count"
        receipt_id = self.aggregate["closed_list_evidence"][member]
        changed = dict(catalog[receipt_id][1])
        changed["owner_rule_id"] = "invented-rule"
        changed["dimension"] = "rendering"
        catalog[receipt_id] = (catalog[receipt_id][0], changed)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            "registry/plan binding" in error or
            "post-Delta evidence closure" in error
            for error in errors), errors)

    def test_aggregate_set_hashes_are_recomputed(self):
        aggregate = deepcopy(self.aggregate)
        aggregate["post_delta_evidence_set_sha256"] = SHA_B
        errors, _ids = self.errors(aggregate=aggregate)
        self.assertTrue(any(
            "post_delta_evidence_set_sha256" in error
            for error in errors), errors)

    def test_global_review_and_attestation_bind_same_plan_closure(self):
        global_review = deepcopy(self.global_review)
        global_review["audit_plan_sha256"] = SHA_B
        attestation = deepcopy(self.attestation)
        attestation["post_delta_evidence_count"] = 7
        errors, _ids = self.errors(
            global_review=global_review, attestation=attestation)
        self.assertTrue(any(
            "global review audit_plan_sha256" in error for error in errors),
            errors)
        self.assertTrue(any(
            "reviewer attestation post_delta_evidence_count" in error
            for error in errors), errors)

    def test_full_receipt_must_bind_its_raw_producer_evidence(self):
        catalog = self.catalog()
        member = "controlled_vocabulary"
        raw_id = self.aggregate["closed_list_producer_evidence"][member]
        changed = dict(catalog[raw_id][1])
        changed["contract_fingerprint"] = SHA_B
        catalog[raw_id] = (catalog[raw_id][0], changed)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            member in error and "producer evidence" in error
            for error in errors), errors)

    def test_raw_producer_evidence_must_remain_resolvable(self):
        catalog = self.catalog()
        member = "controlled_vocabulary"
        raw_id = self.aggregate["closed_list_producer_evidence"][member]
        catalog.pop(raw_id)
        errors, _ids = self.errors(catalog=catalog)
        self.assertTrue(any(
            member in error and "producer evidence" in error
            for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
