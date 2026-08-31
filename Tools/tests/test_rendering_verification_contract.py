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

import Tools.execution.audit.audit_plan_contract as audit_plan_contract  # noqa: E402
import Tools.execution.audit.audit_obligation_projection as audit_obligation_projection  # noqa: E402
import Tools.execution.audit.audit_evidence_runtime as audit_evidence_runtime  # noqa: E402
import Tools.execution.audit.audit_producer_runtime as audit_producer_runtime  # noqa: E402
import Tools.execution.audit.complete_audit_receipt as complete_audit_receipt  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
import Tools.knowledge.rendering.record_rendering_verification as producer  # noqa: E402
import Tools.knowledge.rendering.rendering_verification_contract as contract  # noqa: E402
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION  # noqa: E402


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


class RenderingVerificationContractTests(unittest.TestCase):

    def obligation(self):
        spec = audit_obligation_projection.obligation_spec_for_rule(
            "k12-02-rendering-verification-record", REPOSITORY)
        definition = audit_obligation_projection.\
            resolve_obligation_definition(spec, "B001")
        return audit_obligation_projection.required_obligation(definition)

    def plan(self, obligation=None):
        obligation = obligation or self.obligation()
        value = {
            "schema_version": 2,
            "plan_id": "audit-plan-B001",
            "task_id": "task-test",
            "batch_id": "B001",
            "generated_at": "2026-08-28T00:00:00Z",
            "queue_revision": 1,
            "queue_state_revision": 2,
            "required_queue_sha256": SHA_A,
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
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

    def test_contract_is_record_shape_only(self):
        document = contract.load_contract()
        contract.validate_contract(document)
        self.assertEqual("K12/02", document["semantic_owner"])
        self.assertEqual(
            {"K12/08", "K12/13"},
            set(document["semantic_dependencies"]))
        self.assertNotIn("obligation_projection", document)
        self.assertEqual("record-shape-only",
                         document["proof_boundary"])

    def test_changed_scope_registry_solely_projects_rendering_obligation(self):
        spec = audit_obligation_projection.obligation_spec_for_rule(
            "k12-02-rendering-verification-record")
        self.assertEqual(
            audit_obligation_projection.CHANGED_SCOPE_REGISTRY_PATH,
            spec["source_registry"])
        self.assertEqual("every-batch", spec["applicability"])
        self.assertEqual("rendering", spec["dimension"])

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

    def test_rendering_full_receipt_keeps_precursor_chain_visible(self):
        frozen = []
        for relative in ("README.md", "README.zh-CN.md"):
            snapshot = kblib.repository_target_snapshot(
                str(REPOSITORY), relative, suffixes=(".md", ".MD"),
                singly_linked=True)
            frozen.append(audit_producer_runtime.FrozenPage(
                path=relative, page_sha256=snapshot.sha256,
                semantic_content_fingerprint=SHA_A, snapshot=snapshot))
        frozen = tuple(frozen)
        evidence, plan, obligation = self.build(frozen=frozen)
        plan_sha = audit_plan_contract.plan_sha256(plan)
        full = complete_audit_receipt.build_audit_receipt(
            plan=plan, plan_sha256=plan_sha,
            obligation=obligation, evidence=evidence)
        catalog = {
            evidence["receipt_id"]: evidence,
            full["receipt_id"]: full,
        }
        item = {"id": plan["batch_id"],
                "manifest": [row.path for row in frozen]}
        result = {
            "root": str(REPOSITORY),
            "items_by_id": {item["id"]: item},
            "current_receipt_catalog": catalog,
        }

        resolution = audit_evidence_runtime._required_obligation_resolution(
            result, item, plan, plan_sha, catalog, obligation,
            require_current=True)
        row = audit_evidence_runtime._reconciliation_row(
            result, plan, obligation, resolution)

        self.assertEqual("satisfied", resolution["status"])
        self.assertEqual(full["receipt_id"], row["selected_evidence_ref"])
        self.assertEqual(
            sorted([full["receipt_id"], evidence["receipt_id"]]),
            row["produced_evidence_refs"])
        self.assertFalse(row["unresolved"])

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

    def test_retry_ignores_stale_rendering_history_but_not_current(self):
        evidence, plan, obligation = self.build(
            rendering_mode="deterministic-static")
        plan_sha = audit_plan_contract.plan_sha256(plan)
        runtime = {
            "current_receipt_catalog": {
                evidence["receipt_id"]: evidence,
            },
        }
        with self.assertRaisesRegex(ValueError, "already has current"):
            producer._reject_existing(
                runtime, plan, plan_sha, obligation, self.frozen(),
                contract.load_contract(), str(REPOSITORY))

        changed_frozen = list(self.frozen())
        changed_frozen[0] = audit_producer_runtime.FrozenPage(
            path=changed_frozen[0].path, page_sha256="sha256:" + "c" * 64,
            semantic_content_fingerprint=
                changed_frozen[0].semantic_content_fingerprint,
            snapshot=SimpleNamespace(read_text=lambda: "# A changed\n"))
        producer._reject_existing(
            runtime, plan, plan_sha, obligation, tuple(changed_frozen),
            contract.load_contract(), str(REPOSITORY))

        sibling = copy.deepcopy(evidence)
        sibling["receipt_id"] = "second-current-rendering-receipt"
        runtime["current_receipt_catalog"][sibling["receipt_id"]] = sibling
        with self.assertRaisesRegex(ValueError, "multiple current attempts"):
            producer._reject_existing(
                runtime, plan, plan_sha, obligation, self.frozen(),
                contract.load_contract(), str(REPOSITORY))

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
