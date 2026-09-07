"""Independent tests for the K12/02 rendering record-shape producer."""

import copy
import contextlib
import io
import json
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
import Tools.knowledge.rendering.profile_rendering_evidence_contract as profile_evidence  # noqa: E402
import Tools.knowledge.rendering.record_profile_rendering as profile_producer  # noqa: E402
import Tools.knowledge.rendering.static_render_runtime as static_render_runtime  # noqa: E402
from Tools.governance.profile.rendering_contract import RenderingContract, RenderingRule  # noqa: E402
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION  # noqa: E402
from Tools.platform.common.host_environment import HostEnvironmentUnavailable


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


class _ProfileRenderingFixture:
    """The binding owner never substitutes a record shape for compiler proof."""

    def setUp(self):
        self.text = "# Diagram\n\n```mermaid\ngraph LR\n A-->B\n```\n"
        self.rule = RenderingRule("profile-mermaid", "mermaid-fence",
                                  "static-markdown-render-v1", "mermaid-svg")
        self.profile = SimpleNamespace(fingerprint=SHA_A, rendering_contract=RenderingContract(
            "configured", (self.rule,), "profiles/test/profile.toml", SHA_A))
        self.evaluation = object()
        # Isolate compiler/report acceptance with an admitted machine input.
        # The real Gate and stale-snapshot boundary have Profile owner tests.
        admitted = SimpleNamespace(contract=self.profile, evaluation=self.evaluation,
                                   profile_snapshot_sha256=SHA_A)
        boundary = mock.patch.object(profile_evidence, "load_profile_admission",
                                     return_value=admitted)
        boundary.start()
        self.addCleanup(boundary.stop)
        chain_boundary = mock.patch(
            "Tools.governance.profile.profile_admission.admission_from_evaluation",
            return_value=(admitted, []))
        chain_boundary.start()
        self.addCleanup(chain_boundary.stop)

    def _record(self):
        spec = audit_obligation_projection.profile_rendering_specs(self.profile, REPOSITORY)[0]
        obligation = audit_obligation_projection.required_obligation(
            audit_obligation_projection.resolve_obligation_definition(spec, "Topics/A.md"))
        plan = RenderingVerificationContractTests().plan(obligation)
        report = {
            "schema_version": 1, "target": "Topics/A.md",
            "source_sha256": kblib.sha256_bytes(self.text),
            "selector_id": static_render_runtime.SELECTOR_ID,
            "bindings_sha256": SHA_A, "runtime_fingerprint": {},
            "runtime_sha256": SHA_B,
            "constructs": [{"kind": "mermaid-fence", "acceptance": "mermaid-svg"}],
            "artifacts": [], "result": "pass", "diagnostics": [],
        }
        report["report_sha256"] = kblib.sha256_bytes(kblib.canonical_json_bytes(report))
        page = audit_producer_runtime.FrozenPage(
            "Topics/A.md", kblib.sha256_bytes(self.text), SHA_B,
            SimpleNamespace(read_text=lambda: self.text))
        # Renderer execution/DOM tests belong to static_render_runtime. This
        # unit fixture isolates the report's independent plan/currentness seam.
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=("mermaid-fence",)), \
                mock.patch.object(static_render_runtime, "validate_render_result", return_value=[]):
            record = profile_producer.build_record(
                root=REPOSITORY, plan=plan, plan_sha256=audit_plan_contract.plan_sha256(plan),
                obligation=obligation, evaluation=self.evaluation, page=page, report=report)
        return record, plan, obligation

class ProfileRenderingEvidenceTests(_ProfileRenderingFixture, unittest.TestCase):
    def test_profile_rules_project_blocking_receipts_without_changing_base(self):
        before = audit_obligation_projection.base_obligation_specs(REPOSITORY)
        specs = audit_obligation_projection.profile_rendering_specs(self.profile, REPOSITORY)
        self.assertEqual(1, len(specs))
        row = specs[0]
        self.assertEqual(("profile-extension", "rendering", "audit-receipt", "pre-merge", False),
                         (row["owner_kind"], row["dimension"], row["evidence_kind"],
                          row["due_stage"], row["nonblocking"]))
        self.assertEqual(before, audit_obligation_projection.base_obligation_specs(REPOSITORY))
        self.assertNotIn(self.rule.rule_id, {value["owner_rule_id"] for value in before})

    def test_unconfigured_plain_profile_needs_no_renderer_but_retains_known_gap(self):
        with mock.patch.object(static_render_runtime, "select_constructs") as selector:
            self.assertEqual({"A.md": ()}, profile_evidence.require_bindings(
                [("A.md", "# Plain\n")], None, root=REPOSITORY))
            with self.assertRaisesRegex(ValueError, "contract-gap/HOLD"):
                profile_evidence.require_bindings([("A.md", self.text)], None, root=REPOSITORY)
        selector.assert_not_called()

    def test_configured_math_without_its_profile_rule_remains_a_gap(self):
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=("dollar-math",)):
            with self.assertRaisesRegex(ValueError, "dollar-math"):
                profile_evidence.require_bindings(
                    [("A.md", "$x$")], self.profile, root=REPOSITORY)

    def test_unconfigured_dollar_candidate_uses_ast_and_missing_math_binding_holds(self):
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=("dollar-math",)) as selector:
            with self.assertRaisesRegex(ValueError, "contract-gap/HOLD.*dollar-math"):
                profile_evidence.require_bindings(
                    [("A.md", "$x$")], None, root=REPOSITORY)
        selector.assert_called_once_with("$x$", root=REPOSITORY)

    def test_unconfigured_dollar_candidate_is_not_itself_a_math_verdict(self):
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=()) as selector:
            self.assertEqual({"A.md": ()}, profile_evidence.require_bindings(
                [("A.md", "`$x$` costs $5")], None, root=REPOSITORY))
        selector.assert_called_once_with("`$x$` costs $5", root=REPOSITORY)

    def test_unconfigured_dollar_candidate_cannot_pass_without_parser(self):
        with mock.patch.object(static_render_runtime, "select_constructs", side_effect=ValueError("renderer Host unavailable")):
            with self.assertRaisesRegex(ValueError, "renderer Host unavailable"):
                profile_evidence.require_bindings(
                    [("A.md", "$x$")], None, root=REPOSITORY)

    def test_frozen_plan_requires_exact_current_rendering_applicability(self):
        _record, plan, _obligation = self._record()
        before = copy.deepcopy(plan)
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=("mermaid-fence",)):
            self.assertEqual({"Topics/A.md": ("mermaid-fence",)},
                profile_evidence.require_plan_applicability(
                    plan, [("Topics/A.md", self.text)], self.profile, root=REPOSITORY))
        self.assertEqual(before, plan)

    def test_newly_applicable_registered_construct_cannot_bypass_frozen_plan(self):
        _record, plan, _obligation = self._record()
        math = RenderingRule("profile-math", "dollar-math",
                             "static-markdown-render-v1", "katex-html-mathml")
        profile = SimpleNamespace(rendering_contract=RenderingContract(
            "configured", (self.rule, math), "profiles/test/rendering-contract.yaml", SHA_A))
        before = copy.deepcopy(plan)
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=("mermaid-fence", "dollar-math")):
            with self.assertRaisesRegex(ValueError, "missing=.*profile-math"):
                profile_evidence.require_plan_applicability(
                    plan, [("Topics/A.md", self.text + "$x$")], profile, root=REPOSITORY)
        self.assertEqual(before, plan)

    def test_removed_construct_does_not_silently_drop_frozen_obligation(self):
        _record, plan, _obligation = self._record()
        before = copy.deepcopy(plan)
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=()):
            with self.assertRaisesRegex(ValueError, "obsolete=.*profile-mermaid"):
                profile_evidence.require_plan_applicability(
                    plan, [("Topics/A.md", "# Plain\n")], self.profile, root=REPOSITORY)
        self.assertEqual(before, plan)

    def test_finalizer_consumer_preserves_invalid_artifacts_vs_unavailable_observation(self):
        record, plan, obligation = self._record()
        digest = audit_plan_contract.plan_sha256(plan)
        self.assertEqual([], profile_evidence.current_receipt_errors(record))
        result = {"root": str(REPOSITORY), "current_receipt_catalog": {
            record["receipt_id"]: ("fixture", record)},
            "_profile_authorized_view": {"_contract": self.profile,
                                         "_evaluation": self.evaluation}}
        item = {"id": plan["batch_id"], "manifest": [obligation["target"]]}
        result["items_by_id"] = {item["id"]: item}
        unavailable = HostEnvironmentUnavailable("Node absent",
            capability_id="static-markdown-render-v1", code="node-unavailable")
        for outcome, exception in ((["compiler artifact is invalid"], ValueError),
                                   (unavailable, HostEnvironmentUnavailable)):
            with self.subTest(exception=exception), mock.patch.object(kblib, "repository_target_snapshot", return_value=SimpleNamespace(
                        exists=True, read_text=lambda: self.text)), \
                    mock.patch.object(static_render_runtime, "select_constructs", return_value=("mermaid-fence",)), \
                    mock.patch.object(static_render_runtime, "validate_render_result",
                        side_effect=outcome if isinstance(outcome, Exception) else None,
                        return_value=outcome):
                with self.assertRaises(exception):
                    audit_evidence_runtime.require_completion_evidence(
                        result, item, plan, digest, obligation, record["receipt_id"])

    def test_report_and_source_drift_cannot_reuse_current_evidence(self):
        record, plan, obligation = self._record()
        changed = copy.deepcopy(record)
        changed["render_report"]["target"] = "Topics/B.md"
        self.assertIn("render_report.report_sha256", profile_evidence.current_receipt_errors(changed))
        with mock.patch.object(static_render_runtime, "select_constructs", return_value=("mermaid-fence",)), \
                mock.patch.object(static_render_runtime, "validate_render_result", return_value=[]):
            with self.assertRaisesRegex(ValueError, "artifact_fingerprint"):
                profile_evidence.validate_record_for_obligation(
                    record, plan, audit_plan_contract.plan_sha256(plan), obligation,
                    root=REPOSITORY, evaluation=self.evaluation, text=self.text + "changed\n")


class ProfileRenderingPublicationTests(_ProfileRenderingFixture, unittest.TestCase):
    def test_rendering_publication_confirms_only_after_its_exact_record_readback(self):
        # Reuse an independently validated object, not a renderer or runtime fixture.
        record, plan, obligation = self._record()
        page = audit_producer_runtime.FrozenPage(
            "Topics/A.md", kblib.sha256_bytes(self.text), SHA_B,
            SimpleNamespace(read_text=lambda: self.text))
        result = {"_profile_authorized_view": {"_evaluation": self.evaluation}}
        stage = {"plan": plan, "audit_plan_sha256": audit_plan_contract.plan_sha256(plan)}
        context = (REPOSITORY, result, object(), {}, stage, obligation, (page,), page, self.profile)
        path = str(REPOSITORY / ".cambium/receipts/unit-rendering.jsonl")
        for copies in (1, 2):
            with self.subTest(readback_record_count=copies), contextlib.ExitStack() as stack:
                def append(publication, actual_path, receipts, *, before):
                    self.assertEqual(path, actual_path)
                    publication.outcome = "present"
                    publication.observation = kblib.ReceiptObservation(
                        {"path": path}, (kblib.canonical_json_bytes(receipts[0]) + b"\n") * copies)
                    return "present", None, before
                for owner, name, value in (
                        (profile_producer, "_context", context),
                        (profile_producer, "build_record", record),
                        (static_render_runtime, "render_pages", [record["render_report"]]),
                        (audit_producer_runtime, "computation_binding", object()),
                        (audit_producer_runtime, "managed_receipt_path", path),
                        (audit_producer_runtime, "runtime_lock_metadata", {}),
                        (audit_producer_runtime, "require_runtime_current", result),
                        (audit_producer_runtime, "open_batch", ({}, {})),
                        (audit_producer_runtime, "require_pages_current", None),
                        (audit_producer_runtime, "require_computation_current", None),
                        (audit_evidence_runtime, "resolve_stage_plan", stage),
                        (profile_evidence, "validate_record_for_obligation", record),
                        (kblib, "receipt_append_observation", {})):
                    stack.enter_context(mock.patch.object(owner, name, return_value=value))
                stack.enter_context(mock.patch.object(kblib, "runtime_write_lock",
                    side_effect=lambda *args, **kwargs: contextlib.nullcontext(object())))
                stack.enter_context(mock.patch.object(kblib, "no_authoritative_write_guard",
                    side_effect=lambda lease: contextlib.nullcontext()))
                stack.enter_context(mock.patch.object(kblib.ReceiptPublication, "append",
                    autospec=True, side_effect=append))
                stack.enter_context(mock.patch.object(kblib, "read_receipt_bytes",
                    side_effect=AssertionError("confirmation must share the append observation")))
                output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                code = profile_producer.main([
                    str(REPOSITORY), "--batch", "B1", "--plan", "unused.yaml",
                    "--obligation-id", obligation["obligation_id"], "--apply"])
            answer = json.loads(output.getvalue())
            self.assertTrue(answer["applied"])
            self.assertEqual("present", answer["publication"]["append"])
            self.assertEqual(0 if copies == 1 else 1, code)
            self.assertEqual("published" if copies == 1 else "uncertain", answer["status"])
            self.assertEqual("confirmed" if copies == 1 else "unconfirmed",
                             answer["publication"]["record_confirmation"])


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
            "selected_profile_manifest": "profiles/test/profile.toml",
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
        item = {"id": plan["batch_id"], "manifest": [row.path for row in self.frozen()]}
        result = {"root": str(REPOSITORY), "items_by_id": {item["id"]: item},
                  "current_receipt_catalog": {evidence["receipt_id"]: evidence}}
        # This contract test supplies retained page inputs, not a repository.
        pages = {row.path: row.snapshot.read_text() for row in self.frozen()}
        snapshots = mock.patch.object(kblib, "repository_target_snapshot",
            side_effect=lambda root, relative, **kwargs: SimpleNamespace(
                exists=relative in pages, read_text=lambda: pages[relative]))
        snapshots.start()
        self.addCleanup(snapshots.stop)
        observed, existing = audit_evidence_runtime.require_completion_evidence(
            result, item, plan, plan_sha, obligation, evidence["receipt_id"])
        self.assertIs(evidence, observed)
        self.assertIsNone(existing)

        drifted = copy.deepcopy(evidence)
        drifted["highest_level"] = 0
        result["current_receipt_catalog"] = {drifted["receipt_id"]: drifted}
        with self.assertRaisesRegex(ValueError, "rendering-verification contract"):
            audit_evidence_runtime.require_completion_evidence(
                result, item, plan, plan_sha, obligation, drifted["receipt_id"])

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
