"""Profile Gate exposure, typed admission and frozen-source currency tests.

Most adapter tests reuse one real in-memory Gate result. They do not construct
adoption or task lifecycles. Dynamic owner tests exercise the real producer.
"""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from Tools.governance.profile import check_profile, profile_admission
from Tools.governance.profile import profile_contract as model
from Tools.governance.standards import standards_state
from Tools.platform.common import kblib
from Tools.tests.support.profile_contract_fixture import CurrentProfileContractFixture


class ProfileAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)
        self.evaluation = self.evaluate()
        self.assertTrue(self.evaluation.authorized, self.evaluation.findings)

    def evaluate(self):
        self.fixture.save()
        return check_profile.evaluate_profile_load(
            self.fixture.profile, root=self.fixture.root, receipt_identity=None)

    def admission(self, evaluation=None):
        admission, errors = profile_admission.admission_from_evaluation(
            self.fixture.root, evaluation or self.evaluation)
        self.assertEqual([], errors)
        self.assertIsNotNone(admission)
        return admission

    def install_active_state(self):
        target = self.fixture.root / standards_state.STATE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(standards_state.canonical_text({
            "schema_version": standards_state.SCHEMA_VERSION,
            "state_revision": 1,
            "upstream_revision_id": "0123456789abcdef0123456789abcdef01234567",
            "status": "approved", "effective_date": "2026-09-05",
            "selected_profile_manifest": self.evaluation.contract.manifest_repo_path,
            "latest_adoption_receipt": "audit-profile-admission-fixture",
            "upstream_source_ref": "fixture://cambium",
        }))
        return target

    def test_adapter_evaluates_once_and_reads_immutable_structured_values(self):
        with mock.patch.object(check_profile, "evaluate_profile_load",
                               return_value=self.evaluation) as evaluate:
            admission, errors = profile_admission.admit_profile(
                self.fixture.root, self.fixture.profile)
        self.assertEqual([], errors)
        evaluate.assert_called_once()
        self.assertEqual("Keep synthetic knowledge pages usable.",
                         admission.value("profile-scope", "goal", "statement"))
        with self.assertRaises(TypeError):
            admission.slot("profile-scope")["goal"]["statement"] = "other"
        self.assertEqual("test-profile-foundation-depth",
                         admission.record("audit-dimension-registry", "judgment_items",
                             "test-profile-foundation-depth", id_field="item_id")["item_id"])
        for name in ("slot_paths", "slot_path", "slot_text", "slot_bytes"):
            self.assertFalse(hasattr(admission, name))

    def test_raw_compilation_cannot_substitute_for_gate_evaluation(self):
        contract = self.fixture.load()
        self.assertTrue(contract.valid)
        admission, errors = profile_admission.admit_profile_manifest(
            self.fixture.root, contract.manifest_repo_path, evaluation=contract)
        self.assertIsNone(admission)
        self.assertTrue(errors)

    def test_runtime_view_reuses_the_same_result_without_repeating_gate(self):
        evaluation = self.evaluation
        view = {
            "_evaluation": evaluation, "_contract": evaluation.contract,
            "_profile_snapshot": evaluation.profile_snapshot,
            "_metadata_execution_contract": evaluation.metadata_execution_contract,
            "selected_profile_manifest": evaluation.contract.manifest_repo_path,
            "metadata_execution_contract_fingerprint":
                evaluation.metadata_execution_contract.contract_fingerprint,
            **{name: getattr(evaluation, name)
               for name in model.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS},
        }
        with mock.patch.object(check_profile, "evaluate_profile_load",
                               side_effect=AssertionError("must reuse")):
            self.assertIs(evaluation.contract,
                profile_admission.contract_from_admitted_view(self.fixture.root, view))
        for field in ("_contract", "_profile_snapshot", "_metadata_execution_contract",
                      "profile_snapshot_sha256", "_evaluation"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                profile_admission.contract_from_admitted_view(
                    self.fixture.root, {**view, field: None})

    def test_current_close_evidence_requires_evaluation_not_compiler_validity(self):
        from Tools.execution.task_runtime.queue_runtime.close_gate import _admitted_profile
        admitted = _admitted_profile(self.fixture.root, self.evaluation)
        self.assertIs(self.evaluation.contract, admitted.contract)
        with self.assertRaises(ValueError):
            _admitted_profile(self.fixture.root, self.evaluation.contract)

    def test_rendering_chain_reuses_admission_and_cannot_infer_a_gate(self):
        from Tools.execution.audit import audit_obligation_projection, audit_producer_chain
        self.fixture.slot("rendering-contract").update(
            registration="configured", rules=[{
                "rule_id": "profile-mermaid", "construct": "mermaid-fence",
                "capability_id": "static-markdown-render-v1", "acceptance": "mermaid-svg"}])
        evaluation = self.evaluate()
        self.assertTrue(evaluation.authorized, evaluation.findings)
        spec = audit_obligation_projection.profile_rendering_specs(
            evaluation.contract, self.fixture.root)[0]
        with mock.patch.object(check_profile, "evaluate_profile_load",
                               side_effect=AssertionError("must reuse")):
            chain = audit_producer_chain.precursor_chain_for_spec(
                spec, root=self.fixture.root, evaluation=evaluation)
            self.assertEqual("profile-rendering", chain["execution_route"])
            with self.assertRaises(audit_producer_chain.AuditProducerChainError):
                audit_producer_chain.precursor_chain_for_spec(spec, root=self.fixture.root)

    def test_reuse_requires_same_manifest_root_and_exact_gate_summary(self):
        manifest = self.evaluation.contract.manifest_repo_path
        with mock.patch.object(check_profile, "evaluate_profile_load",
                               side_effect=AssertionError("must reuse")):
            admission, errors = profile_admission.admit_profile_manifest(
                self.fixture.root, manifest, evaluation=self.evaluation)
        self.assertEqual([], errors)
        self.assertIs(admission.contract, self.evaluation.contract)
        admission, errors = profile_admission.admit_profile_manifest(
            self.fixture.root, "profiles/other/profile.toml", evaluation=self.evaluation)
        self.assertIsNone(admission)
        self.assertTrue(errors)
        _admission, errors = profile_admission.admission_from_evaluation(
            self.fixture.root.parent, self.evaluation)
        self.assertTrue(errors)
        forged = replace(self.evaluation, summary_receipt={
            **self.evaluation.summary_receipt, "profile_contract_fingerprint": "sha256:" + "0" * 64})
        self.assertFalse(forged.authorized)

    def test_compile_success_does_not_expose_contract_after_gate_failure(self):
        self.fixture.document["execution_default_overrides"] = {"unregistered_item": 1}
        self.assertTrue(self.fixture.load().valid)
        evaluation = self.evaluate()
        self.assertFalse(evaluation.authorized)
        self.assertIsNone(evaluation.contract)
        self.assertIsNone(evaluation.metadata_execution_contract)
        self.assertIsNone(evaluation.summary_receipt)

    def test_live_manifest_change_leaves_admitted_values_intact_but_stale(self):
        admission = self.admission()
        before = admission.value("profile-scope", "goal", "statement")
        self.fixture.slot("profile-scope")["goal"]["statement"] = "Later candidate."
        self.fixture.save()
        self.assertEqual(before, admission.value("profile-scope", "goal", "statement"))
        self.assertIn("selected Profile changed after profile-load",
                      "; ".join(profile_admission.currency_errors(admission)))

    def test_reference_body_change_is_stale_but_unbound_notes_are_not(self):
        admission = self.admission()
        (self.fixture.profile / "unbound.md").write_text("Unbound candidate notes.\n")
        self.assertEqual([], profile_admission.currency_errors(admission))
        self.fixture.residual_policy.write_text(
            self.fixture.residual_policy.read_text() + "\nChanged policy.\n")
        self.assertIn("selected Profile changed", "; ".join(profile_admission.currency_errors(admission)))

    def test_static_normative_source_change_invalidates_admission(self):
        admission = self.admission()
        target = self.fixture.root / model.PROFILE_TOOLCHAIN_PATH
        target.write_text(target.read_text() + "\n")
        self.assertIn("canonical profile-load inputs changed",
                      "; ".join(profile_admission.currency_errors(admission)))

    def test_decoder_requirements_are_in_draft_and_gate_currency(self):
        path = model.PROFILE_REQUIREMENTS_PATH
        self.assertIn(path, model.profile_draft_inputs(self.fixture.root))
        self.assertIn(path, self.evaluation.normative_snapshots)
        admission = self.admission()
        target = self.fixture.root / path
        target.write_text(target.read_text() + "\n# changed package contract\n")
        self.assertIn("canonical profile-load inputs changed",
                      "; ".join(profile_admission.currency_errors(admission)))

    def test_selected_state_is_frozen_before_and_after_evaluation(self):
        state = self.install_active_state()
        with mock.patch.object(check_profile, "evaluate_profile_load",
                               return_value=self.evaluation):
            admission, errors = profile_admission.admit_profile(self.fixture.root)
        self.assertEqual([], errors)
        state.write_text(state.read_text().replace("status: approved", "status: draft"))
        self.assertIn("active Standards state changed",
                      "; ".join(profile_admission.currency_errors(admission)))

    def test_selection_race_during_evaluation_cannot_admit(self):
        state = self.install_active_state()
        def mutate(*args, **kwargs):
            state.write_text(state.read_text().replace("status: approved", "status: draft"))
            return self.evaluation
        with mock.patch.object(check_profile, "evaluate_profile_load", side_effect=mutate):
            admission, errors = profile_admission.admit_profile(self.fixture.root)
        self.assertIsNone(admission)
        self.assertIn("active Standards state changed", "; ".join(errors))

    def test_snapshot_evidence_fields_are_owned_by_the_same_result(self):
        admission = self.admission()
        for name in model.PROFILE_LOAD_EVIDENCE_FINGERPRINT_FIELDS:
            self.assertEqual(getattr(self.evaluation, name),
                             self.evaluation.summary_receipt[name])
        self.assertEqual(self.evaluation.profile_snapshot_sha256,
                         admission.evaluation.rebind_profile_snapshot().sha256)
        self.assertEqual(self.evaluation.profile_load_inputs_sha256,
                         admission.evaluation.rebind_normative_inputs()[1])


class DynamicOwnerSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)
        self.fixture.enable_gate_contract()
        self.path = "kernel/custom-profile-owner.md"
        self.target = self.fixture.root / self.path
        self.target.write_text("# Custom Owner\n\n## Rule\n\nConcrete policy.\n")
        self.fixture.configure_gate(owner=self.path + "#Rule")
        # A complete Gate seam uses the real shared implementation registry;
        # the smaller linker fixture's synthetic capability subset is not one.
        self.fixture.install_profile_load_inputs()

    def evaluate(self):
        return check_profile.evaluate_profile_load(
            self.fixture.profile, root=self.fixture.root, receipt_identity=None)

    def test_dynamic_owner_is_in_the_same_normative_hash_and_currency_set(self):
        static, _ = check_profile.canonical_profile_load_inputs(self.fixture.root)
        self.assertNotIn(self.path, static)
        evaluation = self.evaluate()
        self.assertTrue(evaluation.authorized, evaluation.findings)
        self.assertIn(self.path, evaluation.normative_snapshots)
        self.assertEqual(evaluation.profile_load_inputs_sha256,
                         check_profile.profile_load_inputs_fingerprint(evaluation.normative_snapshots))
        admission, errors = profile_admission.admission_from_evaluation(self.fixture.root, evaluation)
        self.assertEqual([], errors)
        self.target.write_text(self.target.read_text() + "\nNew owner text.\n")
        self.assertIn("canonical profile-load inputs changed",
                      "; ".join(profile_admission.currency_errors(admission)))

    def test_dynamic_owner_change_while_gate_runs_is_rejected(self):
        original = kblib.repository_file_snapshot
        changed = []
        def snapshot(root, relative, *args, **kwargs):
            result = original(root, relative, *args, **kwargs)
            if relative == self.path and not changed:
                changed.append(relative)
                self.target.write_text(self.target.read_text() + "\nChanged during evaluation.\n")
            return result
        with mock.patch.object(kblib, "repository_file_snapshot", side_effect=snapshot):
            evaluation = self.evaluate()
        self.assertTrue(changed)
        self.assertFalse(evaluation.authorized)
        self.assertIsNone(evaluation.contract)
        self.assertIn("profile-load-input-changed",
                      {item["check"] for item in evaluation.findings})

    def test_static_snapshot_missing_owner_never_falls_back_to_live_reads(self):
        snapshots, _ = check_profile.canonical_profile_load_inputs(self.fixture.root)
        compiled = model.load_profile_contract(self.fixture.root, self.fixture.manifest,
                                               root_input_snapshots=snapshots)
        self.assertFalse(compiled.valid)
        self.assertIn("frozen Profile input is missing",
                      model.format_diagnostics(compiled.diagnostics))


if __name__ == "__main__":
    unittest.main()
