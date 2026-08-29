"""Independent tests for the K12/02 rendering record-shape producer."""

import copy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import audit_plan_contract  # noqa: E402
import audit_obligation_projection  # noqa: E402
import audit_producer_runtime  # noqa: E402
import complete_audit_receipt  # noqa: E402
import record_rendering_verification as producer  # noqa: E402
import rendering_verification_contract as contract  # noqa: E402
from profile_fixture import FIXTURE_UPSTREAM_REVISION  # noqa: E402


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


class RenderingVerificationContractTests(unittest.TestCase):

    def obligation(self):
        return {
            "obligation_id": "rendering-record-001",
            "owner_kind": "kernel",
            "owner_rule_id": "k12-02-rendering-verification-record",
            "kernel_extension_point": None,
            "partition": "changed-scope-deterministic",
            "due_stage": "pre-merge",
            "target": "B001",
            "applicability": "every-batch",
            "evidence_role": "emits",
            "evidence_kind": "audit-receipt",
            "dimension": "rendering",
            "acceptance_predicate":
                "k12-02-rendering-verification-record",
            "producer_check":
                "changed_scope_rendering_escalation_record",
            "producer_capability": "audit-receipt-producer-v1",
            "producer_gate_id": None,
            "consumer_gate_id": "batch-review",
            "fingerprint_binding": "evidence-time",
            "review_due": None,
            "status": "required",
            "evidence_ref": None,
            "reused_receipt_id": None,
            "reuse_reason": None,
        }

    def plan(self, obligation=None):
        obligation = obligation or self.obligation()
        value = {
            "schema_version": 1,
            "plan_id": "audit-plan-B001",
            "task_id": "task-test",
            "batch_id": "B001",
            "generated_at": "2026-08-28T00:00:00Z",
            "queue_revision": 1,
            "queue_state_revision": 2,
            "required_queue_sha256": SHA_A,
            "standards_version": FIXTURE_UPSTREAM_REVISION,
            "active_standards_sha256": SHA_A,
            "selected_profile_manifest": "profiles/test/profile.md",
            "profile_snapshot_sha256": SHA_A,
            "profile_contract_fingerprint": SHA_A,
            "opening_transition_receipt": "audit-update_queue-open-1",
            "artifact_snapshot_sha256": SHA_A,
            "contract_snapshot_sha256": SHA_A,
            "accepted_baseline_sha256": SHA_A,
            "obligations": [obligation],
        }
        audit_plan_contract.validate_plan(value)
        return value

    def frozen(self):
        return (
            audit_producer_runtime.FrozenPage(
                path="Topics/A.md", page_sha256=SHA_A,
                semantic_content_fingerprint=SHA_B,
                snapshot=SimpleNamespace(read_text=lambda: "# A\n")),
            audit_producer_runtime.FrozenPage(
                path="Topics/B.md", page_sha256=SHA_B,
                semantic_content_fingerprint=SHA_A,
                snapshot=SimpleNamespace(read_text=lambda: "# B\n")),
        )

    def build(self, **values):
        obligation = self.obligation()
        plan = self.plan(obligation)
        defaults = {
            "root": str(REPOSITORY),
            "plan": plan,
            "plan_sha256": audit_plan_contract.plan_sha256(plan),
            "obligation": obligation,
            "frozen": self.frozen(),
            "rendering_mode": "source-only",
        }
        defaults.update(values)
        return producer.build_record(**defaults), plan, obligation

    def test_contract_projects_every_batch_rendering_record_only(self):
        document = contract.load_contract()
        values = contract.validate_contract(document)
        projection = values["obligation_projection"]
        self.assertEqual("K12/02", document["semantic_owner"])
        self.assertEqual(
            {"K12/08", "K12/13"},
            set(document["semantic_dependencies"]))
        self.assertEqual("every-batch", projection["applicability"])
        self.assertEqual("batch", projection["target_source"])
        self.assertEqual("rendering", projection["dimension"])
        self.assertEqual("record-shape-only",
                         document["proof_boundary"])

    def test_kernel_registry_and_record_contract_have_one_projection(self):
        projection = contract.validate_contract(
            contract.load_contract())["obligation_projection"]
        spec = audit_obligation_projection.obligation_spec_for_rule(
            "k12-02-rendering-verification-record")
        for field in (
                "owner_kind", "owner_rule_id", "applicability", "partition",
                "due_stage", "producer_check", "producer_capability",
                "producer_gate_id", "consumer_gate_id", "evidence_kind",
                "evidence_role", "dimension", "acceptance_predicate",
                "fingerprint_binding"):
            with self.subTest(field=field):
                self.assertEqual(projection[field], spec[field])

    def test_nonvisual_modes_record_not_applicable_without_visual_claim(self):
        for mode, level in (("source-only", 0),
                            ("deterministic-static", 1)):
            with self.subTest(mode=mode):
                record, plan, obligation = self.build(rendering_mode=mode)
                contract.validate_record(record)
                producer.validate_record_for_plan(
                    record, plan, audit_plan_contract.plan_sha256(plan),
                    obligation, self.frozen(), root=str(REPOSITORY))
                self.assertEqual("not_applicable", record["visual_trigger"])
                self.assertEqual(level, record["highest_level"])
                self.assertIn("does not attest Level 0/1", record["details"])

    def test_nonvisual_mode_rejects_a_visual_trigger(self):
        with self.assertRaisesRegex(ValueError, "visual_trigger"):
            self.build(
                rendering_mode="deterministic-static",
                visual_trigger="I opened the UI anyway")

    def test_escalated_modes_require_all_four_record_fields(self):
        complete = {
            "visual_trigger": "static evidence leaves viewport clipping open",
            "unresolved_question": "does the diagram clip at 1024px",
            "verification_target": "Topics/A.md diagram at 1024px",
            "verification_result": "no clipping observed",
        }
        for mode, level in (
                ("targeted-visual-exception", 2),
                ("expanded-ui", 3),
                ("temporal-recording", 4)):
            record, _plan, _obligation = self.build(
                rendering_mode=mode, **complete)
            self.assertEqual(level, record["highest_level"])
            contract.validate_record(record)
            for missing in complete:
                with self.subTest(mode=mode, missing=missing):
                    incomplete = dict(complete)
                    incomplete[missing] = None
                    with self.assertRaisesRegex(ValueError, missing):
                        self.build(rendering_mode=mode, **incomplete)

    def test_plan_cannot_file_record_under_structure_dimension(self):
        obligation = self.obligation()
        obligation["dimension"] = "structure_and_links"
        plan = self.plan(obligation)
        with self.assertRaisesRegex(ValueError, "dimension"):
            producer.resolve_obligation(plan, obligation["obligation_id"])

    def test_full_audit_receipt_consumes_record_without_changing_boundary(self):
        evidence, plan, obligation = self.build(
            rendering_mode="targeted-visual-exception",
            visual_trigger="deterministic evidence conflicts",
            unresolved_question="which output is displayed",
            verification_target="Topics/A.md diagram",
            verification_result="the compiled artifact is displayed")
        full = complete_audit_receipt.build_audit_receipt(
            plan=plan, plan_sha256=audit_plan_contract.plan_sha256(plan),
            obligation=obligation, evidence=evidence)
        self.assertEqual("rendering", full["dimension"])
        self.assertEqual(
            "k12-02-rendering-verification-record",
            full["acceptance_predicate"])
        self.assertEqual(evidence["receipt_id"], full["evidence_ref"])
        self.assertIn(obligation["target"], full["scope"])

    def test_completion_revalidates_the_unique_rendering_contract(self):
        evidence, plan, obligation = self.build(
            rendering_mode="deterministic-static")
        plan_sha = audit_plan_contract.plan_sha256(plan)
        with mock.patch.object(
                audit_producer_runtime, "receipt_by_id",
                return_value=evidence):
            observed = complete_audit_receipt._producer_evidence(
                str(REPOSITORY), {}, evidence["receipt_id"], plan,
                plan_sha, obligation, self.frozen())
        self.assertIs(evidence, observed)

        drifted = copy.deepcopy(evidence)
        drifted["highest_level"] = 0
        with mock.patch.object(
                audit_producer_runtime, "receipt_by_id",
                return_value=drifted):
            with self.assertRaisesRegex(
                    ValueError, "rendering-verification contract"):
                complete_audit_receipt._producer_evidence(
                    str(REPOSITORY), {}, drifted["receipt_id"], plan,
                    plan_sha, obligation, self.frozen())

    def test_contract_and_record_shapes_are_closed(self):
        changed = copy.deepcopy(contract.load_contract())
        changed["extra"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_contract(changed)
        record, _plan, _obligation = self.build()
        record["level_zero_passed"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            contract.validate_record(record)


if __name__ == "__main__":
    unittest.main()
