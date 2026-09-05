"""Owner tests for structured Profile compilation, not adoption authorization.

The production codec, real CUE and retained domain evaluators validate typed
fixtures. No Markdown carrier is synthesized. Selection/currency and complete
Gate exposure belong to test_profile_admission.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from Tools.governance.profile import profile_codec, profile_contract as model
from Tools.governance.profile import profile_cue
from Tools.platform.common import kblib
from Tools.tests.support.profile_contract_fixture import CurrentProfileContractFixture

REPOSITORY = Path(__file__).resolve().parents[2]


class ProfileMachineOwnerTests(unittest.TestCase):
    def test_kernel_identity_and_tool_source_mapping_are_separate(self):
        interface = model.load_profile_interface(REPOSITORY)
        encoding = model.load_profile_encoding(REPOSITORY)
        model.validate_profile_encoding(interface, encoding)
        self.assertNotIn("cue_sources", interface)
        self.assertEqual(15, len(model.profile_interface_slots(interface)))
        self.assertEqual({row["contract_id"] for row in interface["contracts"]},
                         {row["contract_id"] for row in encoding["cue_sources"]})
        self.assertNotIn("tables", interface)
        self.assertNotIn("manifest_form", interface)

    def test_unknown_interface_or_unmapped_contract_is_rejected(self):
        interface = model.load_profile_interface(REPOSITORY)
        encoding = model.load_profile_encoding(REPOSITORY)
        unknown = deepcopy(interface)
        unknown["unknown"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            model.profile_interface_slots(unknown)
        for mutate in (
                lambda d: d["cue_sources"].pop(),
                lambda d: d["registry_references"].update(
                    audit_dimension_base="Tools/not-the-owner.yaml")):
            altered = deepcopy(encoding)
            mutate(altered)
            with self.assertRaises(ValueError):
                model.validate_profile_encoding(interface, altered)

    def test_draft_inputs_freeze_only_shape_owners_not_producer_implementations(self):
        snapshots = model.profile_draft_inputs(REPOSITORY)
        self.assertIn(model.PROFILE_TOOLCHAIN_PATH, snapshots)
        self.assertIn(model.PROFILE_DEFAULTS_PATH, snapshots)
        self.assertNotIn("Tools/operation-capabilities.yaml", snapshots)
        self.assertNotIn("Tools/knowledge/content/check_residual_content.py", snapshots)
        with self.assertRaises(TypeError):
            snapshots["new"] = None

    def test_scan_registry_rejects_unknown_fields(self):
        registry = model.load_scan_capabilities(REPOSITORY)
        registry["capabilities"][0]["unknown"] = True
        with self.assertRaisesRegex(ValueError, "fields are not closed"):
            model.scan_capability_records(registry)


class ProfileTypedModelTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)

    def assert_invalid(self, check=None):
        contract = self.fixture.load()
        self.assertFalse(contract.valid)
        self.assertIsNone(contract.fingerprint)
        if check:
            self.assertIn(check, self.fixture.checks(contract))
        return contract

    def test_complete_model_is_immutable_and_does_not_claim_authority(self):
        contract = self.fixture.load()
        self.assertTrue(contract.valid, contract.diagnostics)
        self.assertEqual(15, len(contract.slot_values))
        self.assertIn("stopper", contract.role_ids)
        self.assertFalse(hasattr(contract, "authorized"))
        self.assertFalse(hasattr(contract, "slot_paths"))
        self.assertFalse(hasattr(contract, "profile_form_expected"))
        self.assertFalse(hasattr(model, "profile_interface_forms"))
        with self.assertRaises(TypeError):
            contract.slot("Profile Scope")["goal"]["statement"] = "other"
        plain = contract.slot_document("Profile Scope")
        plain["goal"]["statement"] = "other"
        self.assertNotEqual("other", contract.slot("Profile Scope")["goal"]["statement"])

    def test_semantic_fingerprint_binds_all_slots_but_not_encoding_order(self):
        contract = self.fixture.load()
        self.fixture.document = dict(reversed(list(self.fixture.document.items())))
        self.assertEqual(contract.fingerprint, self.fixture.load().fingerprint)
        self.fixture.slot("source-policy")["staleness_triggers"][0]["event"] += " changed"
        self.assertNotEqual(contract.fingerprint, self.fixture.load().fingerprint)

    def test_toml_scalar_types_are_not_string_coercions(self):
        self.fixture.document["execution_default_overrides"] = {"concurrency_cap": 2}
        contract = self.fixture.load()
        self.assertTrue(contract.valid, contract.diagnostics)
        self.assertEqual((("concurrency_cap", 2),), contract.execution_default_overrides)
        self.fixture.slot("profile-scope")["content_priority_factors"][0]["rank"] = True
        self.assert_invalid("profile-contract-schema")

    def test_unknown_missing_and_whitespace_answers_fail_real_cue(self):
        baseline = deepcopy(self.fixture.document)
        mutations = (
            lambda d: d.update(unknown="ignored"),
            lambda d: d["slots"].pop("language-contract"),
            lambda d: d["slots"]["profile-scope"].update(unknown="ignored"),
            lambda d: d["slots"]["profile-scope"]["goal"].update(statement=" \n\u3000"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.fixture.document = deepcopy(baseline)
                mutate(self.fixture.document)
                self.assert_invalid("profile-contract-schema")

    def test_identity_uses_layout_owner(self):
        self.fixture.document["profile_id"] = "other-profile"
        self.assert_invalid("profile-id-invalid")

    def test_nullable_projection_requires_an_explicit_owned_branch(self):
        contract = self.fixture.load()
        raw = contract.slot("Corpus Planning")
        self.assertEqual({}, dict(raw["artifact_bindings"]))
        projected = contract.slot_document("Corpus Planning")
        self.assertIsNone(projected["artifact_bindings"]["global_map"])
        self.assertEqual({}, dict(raw["artifact_bindings"]))
        draft = model.ProfileDraft(None, "profiles/test-profile/profile.toml",
                                   {"corpus-planning": {}}, (), ("missing",))
        self.assertEqual({}, draft.slot_document("Corpus Planning"))

    def test_cue_unavailability_cannot_fall_back_to_python_success(self):
        self.fixture.save()
        with mock.patch.dict("os.environ", {"CAMBIUM_CUE": "/missing/cue"}):
            self.assert_invalid("profile-contract-schema")

    def test_exact_frozen_toolchain_reaches_both_draft_validations(self):
        self.fixture.save()
        snapshots = model.profile_draft_inputs(self.fixture.root)
        actual = profile_cue.validate_profile
        with mock.patch.object(profile_cue, "validate_profile", wraps=actual) as validate:
            draft = model.load_profile_draft(self.fixture.root, self.fixture.manifest,
                                             root_input_snapshots=snapshots)
        self.assertTrue(draft.ready, draft.diagnostics)
        self.assertEqual(2, validate.call_count)
        self.assertEqual(validate.call_args_list[0].kwargs["toolchain"],
                         validate.call_args_list[1].kwargs["toolchain"])
        self.assertFalse(hasattr(draft, "authorized"))

    def test_stale_generated_owner_projection_is_rejected(self):
        encoding = model.load_profile_encoding(self.fixture.root)
        path = next(row["path"] for row in encoding["cue_sources"] if "projection_of" in row)
        target = self.fixture.root / path
        target.write_text(target.read_text() + "\n// stale projection\n")
        self.assert_invalid("profile-contract-owner")

    def test_absent_root_snapshot_cannot_reopen_live_owner(self):
        contract = model.load_profile_contract(
            self.fixture.root, self.fixture.manifest, root_input_snapshots={})
        self.assertFalse(contract.valid)
        self.assertIn("frozen Profile input is missing", model.format_diagnostics(contract.diagnostics))

    def test_draft_missing_wrong_type_and_sentinel_are_distinct(self):
        baseline = deepcopy(self.fixture.document)
        self.fixture.document = {"schema_version": 1, "slots": {}}
        self.fixture.save()
        draft = model.load_profile_draft(self.fixture.root, self.fixture.manifest)
        self.assertFalse(draft.ready)
        self.assertFalse(draft.diagnostics)
        self.assertTrue(draft.unresolved_items)
        self.fixture.document = deepcopy(baseline)
        self.fixture.slot("profile-scope")["goal"]["statement"] = 3
        self.fixture.save()
        draft = model.load_profile_draft(self.fixture.root, self.fixture.manifest)
        self.assertFalse(draft.ready)
        self.assertTrue(draft.diagnostics)
        self.fixture.document = baseline
        self.fixture.slot("profile-scope")["goal"]["statement"] = "TODO(profile)"
        self.fixture.save()
        draft = model.load_profile_draft(self.fixture.root, self.fixture.manifest)
        self.assertFalse(draft.ready)
        self.assertFalse(draft.diagnostics)
        self.assertTrue(draft.unresolved_items)

    def test_referenced_body_marker_is_unanswered_but_unbound_file_is_not(self):
        unbound = self.fixture.profile / "notes.md"
        unbound.write_text("TODO(profile)\n")
        self.assertTrue(self.fixture.load().valid)
        self.fixture.residual_policy.write_text(
            self.fixture.residual_policy.read_text() + "\nTODO(profile)\n")
        self.assert_invalid("profile-contract-sentinel")
        draft = model.load_profile_draft(self.fixture.root, self.fixture.manifest)
        self.assertFalse(draft.ready)
        self.assertTrue(any("residual-disposition.md:" in item for item in draft.unresolved_items))

    def test_reference_coordinates_and_closure_are_structured(self):
        contract = self.fixture.load()
        self.assertTrue(contract.valid, contract.diagnostics)
        self.assertIn("profiles/test-profile/profile.toml", contract.profile_snapshot_paths)
        self.assertIn("profiles/test-profile/policies/residual-disposition.md", contract.profile_snapshot_paths)
        self.assertNotIn("profiles/test-profile/slots.md", contract.profile_snapshot_paths)
        owners = [edge for edge in contract.dependency_edges if edge.kind == "predicate-owner"]
        self.assertTrue(any(edge.fragment.startswith("slots.") for edge in owners if edge.fragment))

    def test_typed_owner_field_and_path_resolution_fail_closed(self):
        rows = self.fixture.slot("audit-dimension-registry")["judgment_items"]
        cases = (
            ("profiles/test-profile/profile.toml#slots.profile-scope.missing", "predicate-owner-field-missing"),
            ("profiles/test-profile/profile.toml#not-slots", "predicate-owner-field-invalid"),
            ("profiles/other/profile.toml#slots.profile-scope", "predicate-owner-path-outside-profile"),
            ("profiles/test-profile/../outside.md", "predicate-owner-path-invalid"),
            ("profiles/test-profile/policies/residual-disposition.md#Absent", "predicate-owner-heading-count"),
        )
        for reference, check in cases:
            with self.subTest(reference=reference):
                rows[0]["predicate_owner"] = reference
                self.assert_invalid(check)

    def test_scan_identity_config_and_judgment_require_real_linkage(self):
        row = self.fixture.slot("registered-scan-registry")["scan_registrations"][0]
        baseline = deepcopy(row)
        cases = (
            ("scan_id", "Bad ID", "profile-contract-schema"),
            ("verifier_capability", "unregistered", "registered-scan-capability-unknown"),
            ("configuration_ref", "profiles/other/config.yaml", "scan-config-path-outside-profile"),
            ("judgment_item_id", "unregistered", "registered-scan-judgment-reference"),
            ("activation_role", "an optional scan", "registered-scans-required-count"),
        )
        for field, value, check in cases:
            with self.subTest(field=field):
                row.clear()
                row.update(baseline)
                row[field] = value
                self.assert_invalid(check)
        row.clear()
        row.update(baseline)
        del row["configuration_ref"]
        self.assert_invalid("registered-scan-config-required")

    def test_duplicate_identities_are_not_positional_records(self):
        rows = self.fixture.slot("audit-dimension-registry")["judgment_items"]
        rows.append(deepcopy(rows[0]))
        self.assert_invalid("judgment-item-id-duplicate")

    def test_command_compiler_requires_valid_model_and_its_root(self):
        contract = self.fixture.load()
        entrypoint = model.registered_scan_entrypoint(REPOSITORY, contract.required_scan)
        with mock.patch.object(model, "registered_scan_entrypoint", return_value=entrypoint):
            command = model.compile_registered_scan_command(self.fixture.root, contract)
        self.assertIn("--scan-id", command)
        self.assertIn(contract.required_scan.scan_id, command)
        with self.assertRaises(model.ProfileContractError):
            model.compile_registered_scan_command(self.fixture.root.parent, contract)
        invalid = replace(contract, diagnostics=(model.Diagnostic("invalid", "source", "test"),))
        with self.assertRaises(model.ProfileContractError):
            model.compile_registered_scan_command(self.fixture.root, invalid)

    def test_volatility_projection_is_immutable_and_checks_base_values(self):
        contract = self.fixture.load()
        projected = model.volatility_defaults_projection(contract)
        self.assertEqual("slow", projected["general"])
        with self.assertRaises(TypeError):
            projected["general"] = "other"
        self.fixture.slot("vocabulary-extensions")["volatility_defaults"]["general"] = "other"
        self.assertFalse(self.fixture.load().valid)


class ProfileSemanticRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)

    def test_gate_producers_share_one_typed_ir_and_completion_projection(self):
        self.fixture.enable_gate_contract()
        for kind, producer, receipt in (
                ("manual-attestation", "manual-attestation-v1", "manual-gate-attestation-v1"),
                ("deterministic", "registered-scan-v1", "deterministic-gate-result-v1")):
            with self.subTest(kind=kind):
                self.fixture.configure_gate(
                    producer_kind=kind, producer_capability=producer, receipt_schema=receipt,
                    judgment="test-profile-residual-disposition")
                contract = self.fixture.load()
                self.assertTrue(contract.valid, contract.diagnostics)
                self.assertEqual(kind, contract.extension_gates[0].producer_kind)
                self.assertEqual(("ready",), model.expression_status_target_projection(contract)[0].completion_values)

    def test_gate_references_capabilities_and_namespace_are_closed(self):
        self.fixture.enable_gate_contract()
        cases = (
            {"gate_id": "P:other:expression-ready"},
            {"owner": "absent-kernel-gate"},
            {"role": "unregistered-role"},
            {"judgment": "unregistered-judgment"},
            {"field": "missing_field"},
            {"completions": ("unregistered-value",)},
            {"producer_capability": "unregistered"},
            {"receipt_schema": "unregistered"},
            {"consumer_capability": "unregistered"},
            {"transition": "not a stable id"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.fixture.configure_gate(**overrides)
                self.assertFalse(self.fixture.load().valid)

    def test_batch_receipt_schema_is_not_arbitrary_text(self):
        self.fixture.slot("routing-and-gate-registry")["batch_review_requirements"] = {
            "mode": "configured", "items": [{
                "judgment_item_id": "test-profile-foundation-depth", "target_selector": "batch",
                "trigger": "before-merge-ready", "producer_kind": "manual-attestation",
                "receipt_schema": "unregistered", "pass_authority_role_id": "stopper"}]}
        self.assertFalse(self.fixture.load().valid)

    def test_expression_artifact_is_linked_to_independent_body(self):
        self.fixture.configure_expression_artifacts([self.fixture.expression_artifact_row()])
        contract = self.fixture.load()
        self.assertTrue(contract.valid, contract.diagnostics)
        self.assertEqual(("Expression/Overview.md",),
                         model.expression_dependency_map_paths_projection(contract))
        artifact = contract.expression_artifacts[0]
        self.assertEqual("Synthetic Predicate", artifact.contract_owner.heading)
        self.fixture.slot("expression-layer-entry")["artifact_contracts"] = []
        self.assertFalse(self.fixture.load().valid)

    def test_expression_metadata_path_bindings_and_readiness_are_semantic(self):
        self.fixture.enable_gate_contract()
        self.fixture.configure_gate()
        row = self.fixture.expression_artifact_row(readiness="expression_status")
        self.fixture.configure_expression_artifacts([row])
        contract = self.fixture.load()
        self.assertTrue(contract.valid, contract.diagnostics)
        row = self.fixture.expression_artifact_row(dependency_map=None,
                                                   binding_fields=("expression_status",))
        self.fixture.configure_expression_artifacts([row])
        self.assertFalse(self.fixture.load().valid)

    def test_expression_artifact_unknown_type_and_unsafe_paths_fail(self):
        for overrides in ({"artifact_type": "unknown"}, {"entry_point": "../escape.md"},
                          {"artifact_id": "Bad ID"}, {"dependency_map": None},
                          {"contract_reference": "profiles/other/body.md#Policy"}):
            with self.subTest(overrides=overrides):
                self.fixture.configure_expression_artifacts([
                    self.fixture.expression_artifact_row(**overrides)])
                self.assertFalse(self.fixture.load().valid)

    def test_extension_dimension_targets_use_owned_unique_values(self):
        self.fixture.configure_extension_dimensions([
            {"dimension_id": "review_extra", "targets": ["review"], "meaning": "Review only."},
            {"dimension_id": "receipt_extra", "targets": ["review", "receipt"], "meaning": "Both."}])
        contract = self.fixture.load()
        self.assertTrue(contract.valid, contract.diagnostics)
        dimensions = model.terminal_receipt_dimensions_projection(contract)
        self.assertIn("receipt_extra", dimensions)
        self.assertNotIn("review_extra", dimensions)
        for targets in (["other"], ["review", "review"]):
            self.fixture.configure_extension_dimensions([
                {"dimension_id": "extra", "targets": targets, "meaning": "Fixture meaning."}])
            self.assertFalse(self.fixture.load().valid)

    def test_rendering_rules_bind_exact_capability_tuple_and_source_bytes(self):
        inactive = self.fixture.load()
        self.assertEqual("none", inactive.rendering_contract.registration)
        self.fixture.slot("rendering-contract").update(registration="configured", rules=[{
            "rule_id": "fixture-mermaid", "construct": "mermaid-fence",
            "capability_id": "static-markdown-render-v1", "acceptance": "mermaid-svg"}])
        contract = self.fixture.load()
        self.assertTrue(contract.valid, contract.diagnostics)
        self.assertEqual(contract.manifest_repo_path, contract.rendering_contract.source_path)
        self.assertEqual(kblib.sha256_bytes(self.fixture.manifest.read_bytes()),
                         contract.rendering_contract.fingerprint)
        self.fixture.slot("rendering-contract")["rules"][0]["capability_id"] = "unregistered"
        self.assertFalse(self.fixture.load().valid)


if __name__ == "__main__":
    unittest.main()
