"""Primary owner tests for the current typed Profile machine contract.

The linker owns closed machine fields, exact Profile slot bindings, and the
typed dependency graph. Profile-load transport, filesystem races, template
parity, examples, onboarding, and adoption have separate primary suites.
"""

import copy
from pathlib import Path
import unittest
from unittest import mock

import Tools.execution.task_runtime.queue_runtime.control_plane as control_plane
import Tools.execution.task_runtime.queue_runtime.profile_view as profile_view
import Tools.governance.profile.profile_contract as profile_contract
import Tools.platform.common.kblib as kblib
from Tools.tests.support.profile_contract_fixture import (
    CurrentProfileContractFixture,
)


REPOSITORY = Path(__file__).resolve().parents[2]


def _write_yaml(path, document):
    kblib.atomic_write_text(
        path, kblib.canonical_yaml(document),
        validator=kblib.parse_yaml_subset)


class ProfileMachineOwnerUnitTests(unittest.TestCase):
    def test_runtime_expression_slot_alias_derives_from_profile_owner(self):
        self.assertEqual(
            profile_contract.EXPRESSION_LAYER_ENTRY_SLOT,
            profile_view.EXPRESSION_LAYER_SLOT)

    def test_interface_slots_and_scan_capabilities_derive_from_current_owners(self):
        interface = profile_contract.load_profile_interface(REPOSITORY)
        slots = profile_contract.profile_interface_slots(interface)
        manifest_form, forms = profile_contract.profile_interface_forms(
            interface)
        scan_registry = profile_contract.load_scan_capabilities(REPOSITORY)
        scans = profile_contract.scan_capability_records(scan_registry)

        self.assertEqual(profile_contract.PROFILE_FILE_SLOTS, slots)
        self.assertEqual(len(slots), len(set(slots)))
        self.assertEqual("profile.md", manifest_form.path)
        self.assertEqual(set(slots), set(forms))
        self.assertEqual(39, len(interface["tables"]))
        table_owners = [
            (row["form_id"], row["section"])
            for row in interface["tables"].values()
        ]
        self.assertEqual(len(table_owners), len(set(table_owners)))
        self.assertTrue(scans)
        for record in scans.values():
            self.assertTrue(
                (REPOSITORY / record["implementation_path"]).is_file())

    def test_unknown_machine_fields_are_rejected_by_their_closed_parsers(self):
        interface = profile_contract.load_profile_interface(REPOSITORY)
        scan_registry = profile_contract.load_scan_capabilities(REPOSITORY)
        cases = []

        unknown_interface = copy.deepcopy(interface)
        unknown_interface["unknown_field"] = None
        cases.append((profile_contract.profile_interface_slots,
                      unknown_interface, "fields are not closed"))

        unknown_slot = copy.deepcopy(interface)
        unknown_slot["slots"][0]["unknown_field"] = None
        cases.append((profile_contract.profile_interface_slots,
                      unknown_slot, "slot 0 fields are not closed"))

        unknown_table = copy.deepcopy(interface)
        unknown_table["tables"]["unknown_table"] = {
            "form_id": "profile-scope",
            "section": "Unknown",
            "cardinality": "exactly-one",
            "row_policy": {"kind": "open"},
            "header": ["Value"],
        }
        cases.append((profile_contract.profile_interface_slots,
                      unknown_table, "is not a required H2"))

        unknown_table_field = copy.deepcopy(interface)
        unknown_table_field["tables"]["registered_artifacts"][
            "unknown_field"] = None
        cases.append((profile_contract.profile_interface_slots,
                      unknown_table_field, "fields are not closed"))

        duplicate_table_header = copy.deepcopy(interface)
        duplicate_table_header["tables"]["registered_artifacts"][
            "header"].append("Artifact type")
        cases.append((profile_contract.profile_interface_slots,
                      duplicate_table_header, "header must be a non-empty"))

        duplicate_table_owner = copy.deepcopy(interface)
        duplicate_table_owner["tables"]["duplicate_goal"] = copy.deepcopy(
            duplicate_table_owner["tables"]["goal"])
        cases.append((profile_contract.profile_interface_slots,
                      duplicate_table_owner, "owns more than one table"))

        duplicate_form_path = copy.deepcopy(interface)
        duplicate_form_path["slots"][4]["form"]["path"] = \
            duplicate_form_path["slots"][0]["form"]["path"]
        cases.append((profile_contract.profile_interface_slots,
                      duplicate_form_path, "form paths must be unique"))

        unknown_form_container = copy.deepcopy(interface)
        unknown_form_container["slots"][0]["form"][
            "instance_subheading_containers"] = [{
                "heading": "## Not Registered",
                "reference_kinds": ["predicate-owner"],
            }]
        cases.append((profile_contract.profile_interface_slots,
                      unknown_form_container, "must name one required H2"))

        unknown_scan = copy.deepcopy(scan_registry)
        unknown_scan["capabilities"][0]["unknown_field"] = None
        cases.append((profile_contract.scan_capability_records,
                      unknown_scan, "fields are not closed"))

        for parser, document, expected in cases:
            with self.subTest(parser=parser.__name__):
                with self.assertRaisesRegex(ValueError, expected):
                    parser(document)

    def test_kernel_shape_contracts_reject_ignored_rule_mutations(self):
        structure = kblib.load_yaml_file(
            REPOSITORY / kblib.STRUCTURE_REGISTRY_CONTRACT_PATH)
        structure["external_reference_checks"][
            "profile_scope_layer_identity"] = False
        with self.assertRaisesRegex(ValueError, "enabled mapping"):
            kblib.validate_structure_registry_contract(structure)

        metadata = kblib.load_yaml_file(
            REPOSITORY / kblib.METADATA_PROFILE_CONTRACT_PATH)
        metadata["boundary_projection"]["label_shape"] = "arbitrary"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            kblib.validate_metadata_profile_contract(metadata)

        vocabulary = kblib.load_yaml_file(
            REPOSITORY / profile_contract.vocabulary_contract.
            VOCABULARY_EXTENSIONS_CONTRACT_PATH)
        vocabulary["composition_rules"]["fields_domain_forbidden"] = False
        with self.assertRaisesRegex(
                profile_contract.vocabulary_contract.VocabularyContractError,
                "unsupported"):
            profile_contract.vocabulary_contract.\
                validate_vocabulary_extensions_contract(vocabulary)

    def test_bound_structure_owner_drives_the_current_profile_load(self):
        fixture = CurrentProfileContractFixture(self)
        owner_path = fixture.root / kblib.STRUCTURE_REGISTRY_CONTRACT_PATH
        owner = kblib.load_yaml_file(owner_path)
        owner["unit"]["kinds"].append("collection")
        _write_yaml(owner_path, owner)
        document = {
            "schema_version": 2,
            "applicability": {"state": "configured", "reason": None},
            "units": [{
                "id": "U-COLLECTION",
                "kind": "collection",
                "parent": None,
                "root": "Knowledge",
                "entry": {"path": "Knowledge.md", "expected_type": None},
                "global_map_entry": None,
                "roles": {
                    role: {
                        "mode": "not-applicable",
                        "reason": "The synthetic collection has no %s view."
                                  % role,
                    }
                    for role in (
                        "sequence", "coverage", "quick_reference",
                        "expression")
                },
            }],
            "support_layers": [],
        }
        structure = fixture.profile / "structure-registry.yaml"
        _write_yaml(structure, document)

        self.assertTrue(any(
            check == "structure-registry-unit"
            for check, _label, _details in
            kblib.validate_structure_registry_shape(document)))
        contract = fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)

    def test_bound_metadata_owner_drives_the_current_profile_load(self):
        fixture = CurrentProfileContractFixture(self)
        owner_path = fixture.root / kblib.METADATA_PROFILE_CONTRACT_PATH
        owner = kblib.load_yaml_file(owner_path)
        owner["shape_values"].append("scalar")
        _write_yaml(owner_path, owner)
        document = {
            "schema_version": 1,
            "applicability": {"state": "configured"},
            "applicability_differences": [],
            "extension_fields": [{
                "field": "synthetic_scalar",
                "mode": "optional",
                "shape": "scalar",
                "owner": "profiles/test-profile/scope-and-architecture.md",
            }],
            "relationship_extensions": [],
            "section_roles": [],
        }
        _write_yaml(fixture.metadata, document)

        self.assertTrue(any(
            check == "metadata-contract-entry"
            for check, _label, _details in
            kblib.validate_metadata_contract_shape(document)))
        contract = fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)

    def test_bound_corpus_owner_drives_the_current_profile_load(self):
        fixture = CurrentProfileContractFixture(self)
        corpus_contract = profile_contract.corpus_planning_contract
        owner_path = fixture.root / corpus_contract.\
            CORPUS_PLANNING_CONTRACT_PATH
        owner = kblib.load_yaml_file(owner_path)
        owner["slot_envelope"]["applicability_branches"][
            "inactive"] = "deferred"
        _write_yaml(owner_path, owner)
        corpus = fixture.profile / "corpus-planning.yaml"
        document = kblib.load_yaml_file(corpus)
        document["applicability"]["state"] = "deferred"
        _write_yaml(corpus, document)

        _normalized, default_issues = \
            corpus_contract.validate_corpus_planning_envelope(document)
        self.assertIn(
            "applicability_state",
            {issue["code"] for issue in default_issues})
        contract = fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)


class ProfileTypedClosureContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)

    def test_current_profile_links_every_slot_and_typed_dependency(self):
        contract = self.fixture.load()
        repeated = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(contract.fingerprint, repeated.fingerprint)
        self.assertRegex(contract.fingerprint, r"^sha256:[0-9a-f]{64}$")
        slot_edges = {
            edge.owner_id for edge in contract.dependency_edges
            if edge.kind == "manifest-slot"
        }
        self.assertEqual(set(profile_contract.PROFILE_FILE_SLOTS), slot_edges)
        edge_kinds = {edge.kind for edge in contract.dependency_edges}
        self.assertTrue({
            "manifest-slot", "predicate-owner", "scan-config",
            "verifier-capability", "scan-judgment",
        }.issubset(edge_kinds))
        self.assertEqual(
            set(contract.profile_snapshot_paths),
            {contract.manifest_repo_path} | {
                edge.path for edge in contract.dependency_edges
                if edge.path and edge.path.startswith(
                    contract.profile_repo_dir + "/")
            })
        self.assertNotIn(
            "profiles/test-profile/slots.md",
            contract.profile_snapshot_paths,
        )
        self.assertTrue({
            "profiles/test-profile/scope-and-architecture.md",
            "profiles/test-profile/registries/audit-dimensions.md",
        }.issubset(set(contract.profile_snapshot_paths)))

    def test_slot_binding_rejections_are_one_table_driven_contract(self):
        original = self.fixture.manifest.read_text(encoding="utf-8")
        line = "- `Priority Rubric`: `priority-rubric.md`\n"
        cases = (
            (original.replace(line, "", 1),
             "profile-contract-slot-missing"),
            (original.replace(line, line + line, 1),
             "profile-contract-slot-duplicate"),
            (original.replace(
                line, "- `Priority Rubric`: `TODO(profile)`\n", 1),
             "profile-contract-sentinel"),
        )

        for manifest, expected in cases:
            with self.subTest(expected=expected):
                self.fixture.manifest.write_text(manifest, encoding="utf-8")
                contract = self.fixture.load()
                self.assertFalse(contract.authorized)
                self.assertIsNone(contract.fingerprint)
                self.assertIn(expected, self.fixture.checks(contract))
        self.fixture.manifest.write_text(original, encoding="utf-8")

    def test_unknown_interface_field_blocks_the_whole_typed_closure(self):
        path = self.fixture.root / profile_contract.PROFILE_INTERFACE_PATH
        document = kblib.load_yaml_file(path)
        document["unknown_field"] = "not-current-contract"
        _write_yaml(path, document)

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIsNone(contract.fingerprint)
        self.assertEqual(
            {"profile-contract-interface-invalid"},
            self.fixture.checks(contract))

    def test_form_drift_blocks_typed_authorization_without_judging_answers(self):
        contract = self.fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            contract.profile_form_expected,
            contract.profile_form_conformant)

        scope = self.fixture.profile / "scope-and-architecture.md"
        CurrentProfileContractFixture.replace(
            scope, "## Goal\n", "## Renamed Goal\n")
        drifted = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)

        self.assertFalse(drifted.authorized)
        self.assertIn(
            "profile-form-heading-structure", self.fixture.checks(drifted))

    def test_yaml_form_rejects_unknown_top_level_fields(self):
        with self.fixture.vocabulary.open("a", encoding="utf-8") as stream:
            stream.write("unknown_top_level: arbitrary\n")

        rejected = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)

        self.assertFalse(rejected.authorized)
        self.assertIn("profile-form-yaml-shape", self.fixture.checks(rejected))
        self.assertLess(
            rejected.profile_form_conformant,
            rejected.profile_form_expected)

    def test_interface_duplicate_keys_and_stable_row_forms_fail_closed(self):
        interface = self.fixture.root / profile_contract.PROFILE_INTERFACE_PATH
        text = interface.read_text(encoding="utf-8")
        interface.write_text(
            text.replace("schema_version: 3\n",
                         "schema_version: 3\nschema_version: 3\n", 1),
            encoding="utf-8")
        duplicate = self.fixture.load()
        self.assertEqual(
            {"profile-contract-interface-invalid"},
            self.fixture.checks(duplicate))
        interface.write_text(text, encoding="utf-8")

        self.fixture._materialize_form_files()
        cases = (
            (self.fixture.profile / "priority-rubric.md",
             "| `P0` | No grants | Not applicable |\n", "",
             "profile-form-table-row-identity"),
            (self.fixture.profile / "scope-and-architecture.md",
             "| fixture-value | fixture-value |\n",
             "| fixture-value | fixture-value |\n"
             "| second answer | second reader |\n",
             "profile-form-table-row-count"),
            (self.fixture.profile / "escalation-policy.md",
             "- Registration: None\n", "- Registration: Maybe\n",
             "profile-form-scalar-value"),
        )
        for path, old, new, expected in cases:
            with self.subTest(expected=expected):
                original = path.read_text(encoding="utf-8")
                self.assertIn(old, original)
                path.write_text(original.replace(old, new, 1),
                                encoding="utf-8")
                rejected = profile_contract.load_profile_contract(
                    self.fixture.root, self.fixture.manifest)
                self.assertFalse(rejected.authorized)
                self.assertIn(expected, self.fixture.checks(rejected))
                path.write_text(original, encoding="utf-8")

    def test_markdown_form_rejects_header_count_and_location_drift(self):
        path = self.fixture.profile / "escalation-policy.md"
        original = path.read_text(encoding="utf-8")
        header = (
            "| Trigger ID | Condition that fires it | `machine-checkable` or "
            "`review-checkable` | Deciding Role ID reference | Resume "
            "condition |\n")
        separator = "|---|---|---|---|---|\n"
        self.assertIn(header + separator, original)
        cases = {
            "header": (
                original.replace("| Trigger ID |", "| Arbitrary column |", 1),
                "profile-form-table-header"),
            "missing": (
                original.replace(header + separator, "", 1),
                "profile-form-table-count"),
            "multiple": (
                original + "\n" + header + separator,
                "profile-form-table-count"),
            "wrong-section": (
                original.replace(header + separator, "", 1).replace(
                    "# Escalation Policy\n",
                    "# Escalation Policy\n\n" + header + separator, 1),
                "profile-form-table-unexpected"),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(name=name):
                path.write_text(text, encoding="utf-8")
                rejected = profile_contract.load_profile_contract(
                    self.fixture.root, self.fixture.manifest)
                self.assertFalse(rejected.authorized)
                self.assertIn(expected, self.fixture.checks(rejected))
                self.assertLess(
                    rejected.profile_form_conformant,
                    rejected.profile_form_expected)
        path.write_text(original, encoding="utf-8")

    def test_instance_subheading_requires_the_registered_reference_kind(self):
        self.fixture.replace(
            self.fixture.slots,
            "`profiles/test-profile/scope-and-architecture.md"
            "#Foundation Depth Requirements`",
            "`profiles/test-profile/expression-layer.md"
            "#Fixture Artifact Contract`",
        )
        self.fixture._materialize_form_files()
        expression = self.fixture.profile / "expression-layer.md"
        expression.write_text(
            expression.read_text(encoding="utf-8") +
            "\n### Fixture Artifact Contract\n\n"
            "Only an unrelated predicate-owner edge references this H3.\n",
            encoding="utf-8")

        rejected = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)

        self.assertFalse(rejected.authorized)
        self.assertIn(
            "profile-form-subheading-reference",
            self.fixture.checks(rejected))

    def test_only_registered_containers_accept_instance_subheadings(self):
        self.fixture.configure_expression_artifacts((
            self.fixture.expression_artifact_row(
                contract_reference=(
                    "profiles/test-profile/expression-layer.md"
                    "#Fixture Artifact Contract")),
            self.fixture.expression_artifact_row(
                artifact_id="test-expression-roadmap",
                entry_point="Expression/Roadmap.md",
                dependency_map="Expression/Roadmap Overview.md",
                contract_reference=(
                    "profiles/test-profile/expression-layer.md"
                    "#Fixture Artifact Contract")),
        ))
        self.fixture._materialize_form_files()
        expression = self.fixture.profile / "expression-layer.md"
        expression.write_text(
            expression.read_text(encoding="utf-8") +
            "\n### Fixture Artifact Contract\n\nReader-facing fixture content.\n",
            encoding="utf-8")
        allowed = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)
        self.assertTrue(allowed.authorized, allowed.diagnostics)

        expression.write_text(
            expression.read_text(encoding="utf-8") +
            "\n### Orphan Artifact Contract\n\nNo registry row consumes this.\n",
            encoding="utf-8")
        orphaned = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)
        self.assertFalse(orphaned.authorized)
        self.assertIn(
            "profile-form-subheading-reference",
            self.fixture.checks(orphaned))
        expression.write_text(
            expression.read_text(encoding="utf-8").replace(
                "\n### Orphan Artifact Contract\n\n"
                "No registry row consumes this.\n", ""),
            encoding="utf-8")

        scope = self.fixture.profile / "scope-and-architecture.md"
        scope.write_text(
            scope.read_text(encoding="utf-8") +
            "\n### Unregistered Structure\n\nFixture content.\n",
            encoding="utf-8")
        rejected = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)
        self.assertFalse(rejected.authorized)
        self.assertIn(
            "profile-form-subheading-container",
            self.fixture.checks(rejected))

    def test_deep_heading_cannot_bypass_the_registered_h3_owner(self):
        self.fixture._materialize_form_files()
        expression = self.fixture.profile / "expression-layer.md"
        CurrentProfileContractFixture.replace(
            expression, "## Artifact Contracts\n",
            "## Artifact Contracts\n\n#### Direct H4\n")

        rejected = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)

        self.assertFalse(rejected.authorized)
        self.assertIn(
            "profile-form-subheading-container",
            self.fixture.checks(rejected))

    def test_scan_capability_and_configuration_fail_closed_as_one_table(self):
        original = self.fixture.slots.read_text(encoding="utf-8")
        capability = "`residual-content-scan-v1`"
        config = "`profiles/test-profile/scan-configs/residual-scan.yaml`"
        cases = (
            (original.replace(capability, "`unknown-capability-v1`", 1),
             "registered-scan-capability-unknown"),
            (original.replace(config, "`None`", 1),
             "registered-scan-config-required"),
        )

        for text, expected in cases:
            with self.subTest(expected=expected):
                self.fixture.slots.write_text(text, encoding="utf-8")
                contract = self.fixture.load()
                self.assertFalse(contract.authorized)
                self.assertIn(expected, self.fixture.checks(contract))
        self.fixture.slots.write_text(original, encoding="utf-8")

    def test_compilation_requires_one_authorized_contract_and_its_root(self):
        contract = self.fixture.load()
        with self.assertRaises(profile_contract.ProfileContractError):
            profile_contract.compile_registered_scan_command(
                self.fixture.root.parent, contract)

        line = "- `Priority Rubric`: `priority-rubric.md`\n"
        CurrentProfileContractFixture.replace(
            self.fixture.manifest, line, "")
        invalid = self.fixture.load()
        self.assertFalse(invalid.authorized)
        with self.assertRaises(profile_contract.ProfileContractError):
            profile_contract.compile_registered_scan_command(
                self.fixture.root, invalid)


class ProfileVolatilityDefaultsContractTests(unittest.TestCase):
    """Primary owner for the selected Profile's typed freshness policy."""

    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)

    def test_authorized_contract_projects_one_immutable_mapping(self):
        contract = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)
        projection = profile_contract.volatility_defaults_projection(contract)
        self.assertEqual({"general": "slow"}, dict(projection))
        with self.assertRaises(TypeError):
            projection["general"] = "fast"

        CurrentProfileContractFixture.replace(
            self.fixture.vocabulary, "  general: slow\n",
            "  general: fast\n")
        changed = self.fixture.load()
        self.assertTrue(changed.authorized, changed.diagnostics)
        self.assertEqual(
            {"general": "fast"},
            dict(profile_contract.volatility_defaults_projection(changed)))
        self.assertNotEqual(contract.fingerprint, changed.fingerprint)

    def test_invalid_or_missing_defaults_fail_the_typed_profile(self):
        original = self.fixture.vocabulary.read_text(encoding="utf-8")
        cases = (
            (original.replace("  general: slow\n", "  general: unknown\n"),
             "must be one of"),
            (original.replace(
                "volatility_defaults:\n  general: slow\n",
                "volatility_defaults:\n"),
             "must be a non-empty"),
        )

        for text, detail in cases:
            with self.subTest(detail=detail):
                self.fixture.vocabulary.write_text(text, encoding="utf-8")
                contract = self.fixture.load()
                self.assertFalse(contract.authorized)
                self.assertIn(
                    "extension-gate-vocabulary-registry",
                    self.fixture.checks(contract))
                self.assertTrue(any(
                    detail in diagnostic.details
                    for diagnostic in contract.diagnostics))
                with self.assertRaises(profile_contract.ProfileContractError):
                    profile_contract.volatility_defaults_projection(contract)
        self.fixture.vocabulary.write_text(original, encoding="utf-8")


class ProfileExtensionGateContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)
        self.fixture.enable_gate_contract()
        self.gate_base = self.fixture.slots.read_text(encoding="utf-8")
        self.metadata_base = self.fixture.metadata.read_text(encoding="utf-8")

    def configure(self, **overrides):
        self.fixture.slots.write_text(self.gate_base, encoding="utf-8")
        self.fixture.metadata.write_text(self.metadata_base, encoding="utf-8")
        self.fixture.configure_gate(**overrides)
        return self.fixture.load()

    def test_manual_and_deterministic_gates_compile_to_one_typed_ir(self):
        cases = (
            ({}, "stopper"),
            ({
                "judgment": "test-profile-residual-disposition",
                "producer_kind": "deterministic",
                "producer_capability": "registered-scan-v1",
                "receipt_schema": "deterministic-gate-result-v1",
            }, "test-profile-residuals"),
        )

        for overrides, producer_reference in cases:
            with self.subTest(kind=overrides.get(
                    "producer_kind", "manual-attestation")):
                contract = self.configure(**overrides)
                self.assertTrue(contract.authorized, contract.diagnostics)
                self.assertEqual(1, len(contract.extension_gates))
                gate = contract.extension_gates[0]
                self.assertEqual("expression_status", gate.field_id)
                self.assertEqual(("ready",), gate.completion_values)
                self.assertEqual(producer_reference,
                                 gate.producer_reference)
                edge_kinds = {
                    edge.kind for edge in contract.dependency_edges
                    if edge.owner_id == gate.gate_id
                }
                self.assertTrue({
                    "extension-gate-field",
                    "extension-gate-judgment",
                    "extension-gate-producer-capability",
                    "extension-gate-receipt-schema",
                    "extension-gate-consumer-capability",
                }.issubset(edge_kinds))

    def test_gate_references_and_capabilities_share_one_rejection_table(self):
        cases = (
            ({"role": "unknown-role"},
             "extension-gate-role-reference"),
            ({"field": "unknown_field"},
             "extension-gate-field-reference"),
            ({"completions": "unknown"},
             "extension-gate-completion-reference"),
            ({"judgment": "unknown-item"},
             "extension-gate-judgment-reference"),
            ({"producer_capability": "unknown-producer-v1"},
             "extension-gate-producer-capability"),
            ({"receipt_schema": "unknown-receipt-v1"},
             "extension-gate-receipt-schema"),
            ({"consumer_capability": "unknown-consumer-v1"},
             "extension-gate-consumer-capability"),
        )

        for overrides, expected in cases:
            with self.subTest(expected=expected):
                contract = self.configure(**overrides)
                self.assertFalse(contract.authorized)
                self.assertEqual((), contract.extension_gates)
                self.assertIn(expected, self.fixture.checks(contract))

    def test_gate_registration_and_table_fields_are_closed(self):
        self.fixture.slots.write_text(self.gate_base, encoding="utf-8")
        self.fixture.configure_gate()
        CurrentProfileContractFixture.replace(
            self.fixture.slots, "| Gate ID |", "| Unknown Field |")
        unknown_field = self.fixture.load()
        self.assertIn(
            "extension-gates-table-header",
            self.fixture.checks(unknown_field))

        self.fixture.slots.write_text(self.gate_base, encoding="utf-8")
        row = self.fixture.gate_row()
        separator = "|" + "---|" * len(
            profile_contract.EXTENSION_GATE_HEADER) + "\n"
        CurrentProfileContractFixture.replace(
            self.fixture.slots, separator, separator + row)
        none_with_rows = self.fixture.load()
        self.assertIn(
            "extension-gates-none-with-rows",
            self.fixture.checks(none_with_rows))

    def test_gate_field_requires_a_profile_owned_applicable_extension(self):
        self.fixture.slots.write_text(self.gate_base, encoding="utf-8")
        self.fixture.configure_gate()
        self.fixture.metadata.write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: kernel-defaults\n"
            "applicability_differences: []\n"
            "extension_fields: []\n"
            "relationship_extensions: []\n"
            "section_roles: []\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIn(
            "extension-gate-field-applicability",
            self.fixture.checks(contract))


class ExpressionStatusProjectionContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)

    def configured(self, *, role="Expression Status Axis",
                   second_field=False, duplicate_gate=False):
        self.fixture.enable_gate_contract(role=role)
        if second_field:
            text = self.fixture.vocabulary.read_text(encoding="utf-8")
            self.fixture.vocabulary.write_text(
                text.replace(
                    "volatility_defaults:",
                    "  second_status:\n"
                    "    role: Expression Status Axis\n"
                    "    values:\n"
                    "      - complete\n"
                    "volatility_defaults:", 1),
                encoding="utf-8")
        self.fixture.configure_gate()
        if duplicate_gate:
            first = self.fixture.gate_row()
            row = self.fixture.gate_row(
                gate_id="P:test-profile:second-ready",
                transition="second-ready")
            CurrentProfileContractFixture.replace(
                self.fixture.slots, first, first + row)
        return self.fixture.load()

    def test_exact_expression_field_and_gate_project_once(self):
        contract = self.configured()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            (profile_contract.ExpressionStatusTarget(
                gate_id="P:test-profile:expression-ready",
                field_id="expression_status",
                completion_values=("ready",)),),
            profile_contract.expression_status_target_projection(contract))

    def test_absent_or_non_expression_roles_project_nothing(self):
        baseline = self.fixture.load()
        self.assertEqual(
            (), profile_contract.expression_status_target_projection(
                baseline))

        non_expression = self.configured(role="Workflow Hint")
        self.assertTrue(non_expression.authorized,
                        non_expression.diagnostics)
        self.assertEqual(
            (), profile_contract.expression_status_target_projection(
                non_expression))

    def test_ambiguous_or_unauthorized_expression_contracts_fail_closed(self):
        multiple_fields = self.configured(second_field=True)
        with self.assertRaisesRegex(
                profile_contract.ProfileContractError,
                "registers 2 Expression Status Axis fields"):
            profile_contract.expression_status_target_projection(
                multiple_fields)

        self.fixture = CurrentProfileContractFixture(self)
        multiple_gates = self.configured(duplicate_gate=True)
        self.assertTrue(multiple_gates.authorized,
                        multiple_gates.diagnostics)
        with self.assertRaisesRegex(
                profile_contract.ProfileContractError,
                "must bind exactly one extension Gate; found 2"):
            profile_contract.expression_status_target_projection(
                multiple_gates)

        self.fixture = CurrentProfileContractFixture(self)
        self.fixture.enable_gate_contract()
        self.fixture.configure_gate()
        row = self.fixture.gate_row()
        CurrentProfileContractFixture.replace(
            self.fixture.slots, row, row + row)
        unauthorized = self.fixture.load()
        self.assertFalse(unauthorized.authorized)
        with self.assertRaisesRegex(
                profile_contract.ProfileContractError,
                "Profile contract is not authorized"):
            profile_contract.expression_status_target_projection(
                unauthorized)


class ExpressionArtifactRegistryContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)

    def test_none_and_configured_forms_share_one_typed_contract(self):
        inactive = self.fixture.load()
        self.assertTrue(inactive.authorized, inactive.diagnostics)
        self.assertEqual("None", inactive.expression_registration)
        self.assertEqual((), inactive.expression_artifacts)
        self.assertEqual(
            (), profile_contract.
            expression_dependency_map_paths_projection(inactive))

        row = self.fixture.expression_artifact_row()
        self.fixture.configure_expression_artifacts((row,))
        configured = self.fixture.load()

        self.assertTrue(configured.authorized, configured.diagnostics)
        self.assertEqual("Configured", configured.expression_registration)
        self.assertEqual(1, len(configured.expression_artifacts))
        artifact = configured.expression_artifacts[0]
        self.assertEqual("test-expression-guide", artifact.artifact_id)
        self.assertEqual("cheat-sheet", artifact.artifact_type)
        self.assertEqual("Expression/Guide.md", artifact.entry_point)
        self.assertIsNone(artifact.readiness_field_id)
        self.assertEqual(
            ("Expression/Overview.md",),
            profile_contract.expression_dependency_map_paths_projection(
                configured))
        self.assertNotEqual(inactive.fingerprint, configured.fingerprint)

    def test_metadata_binding_can_replace_dependency_map(self):
        self.fixture.metadata.write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: configured\n"
            "applicability_differences: []\n"
            "extension_fields:\n"
            "  - field: expression_guide\n"
            "    mode: optional\n"
            "    shape: path\n"
            "    owner: profiles/test-profile/slots.md\n"
            "relationship_extensions:\n"
            "  - field: canonical_bindings\n"
            "    mode: optional\n"
            "    direction: expression-to-canonical\n"
            "    target: page\n"
            "    shape: list-of-paths\n"
            "    owner: profiles/test-profile/slots.md\n"
            "section_roles: []\n",
            encoding="utf-8")
        row = self.fixture.expression_artifact_row(
            dependency_map="None",
            binding_fields="expression_guide, canonical_bindings")
        self.fixture.configure_expression_artifacts((row,))

        contract = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            ("expression_guide", "canonical_bindings"),
            contract.expression_artifacts[0].binding_field_ids)
        self.assertEqual(
            (), profile_contract.
            expression_dependency_map_paths_projection(contract))

    def test_non_path_metadata_fields_cannot_authorize_artifact_binding(self):
        cases = (
            (
                "extension_fields:\n"
                "  - field: case_class\n"
                "    mode: optional\n"
                "    shape: nonempty-string\n"
                "    owner: profiles/test-profile/slots.md\n"
                "relationship_extensions: []\n",
                "case_class",
            ),
            (
                "extension_fields: []\n"
                "relationship_extensions:\n"
                "  - field: reverse_links\n"
                "    mode: optional\n"
                "    direction: canonical-to-expression\n"
                "    target: page\n"
                "    shape: list-of-paths\n"
                "    owner: profiles/test-profile/slots.md\n",
                "reverse_links",
            ),
        )
        for declarations, field_id in cases:
            with self.subTest(field_id=field_id):
                self.fixture.metadata.write_text(
                    "schema_version: 1\n"
                    "applicability:\n"
                    "  state: configured\n"
                    "applicability_differences: []\n" + declarations +
                    "section_roles: []\n",
                    encoding="utf-8")
                self.fixture.configure_expression_artifacts((
                    self.fixture.expression_artifact_row(
                        dependency_map="None", binding_fields=field_id),))
                contract = self.fixture.load()
                self.assertFalse(contract.authorized)
                self.assertIn(
                    "expression-artifact-binding-shape",
                    self.fixture.checks(contract))
                self.fixture = CurrentProfileContractFixture(self)

    def test_existing_readiness_contract_may_be_referenced_optionally(self):
        self.fixture.enable_gate_contract()
        self.fixture.configure_gate()
        self.fixture.configure_expression_artifacts((
            self.fixture.expression_artifact_row(
                readiness="expression_status"),))

        contract = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            "expression_status",
            contract.expression_artifacts[0].readiness_field_id)

    def test_registry_rejects_parallel_legacy_shape_and_unlinked_rows(self):
        original = self.fixture.slots.read_text(encoding="utf-8")
        cases = (
            (original.replace(
                "| Stable artifact ID | Artifact type | Reader-facing label | "
                "Entry point | Dependency-map path or `None` | Metadata binding "
                "field ID(s) or `None` | Revalidation trigger | Contract "
                "reference (Profile path with `#heading`) | Readiness field ID "
                "or `None` |",
                "| Property | Value |", 1),
             "expression-artifacts-table-header"),
            (self.fixture.expression_artifact_row(
                dependency_map="None", binding_fields="None"),
             "expression-artifact-binding-missing"),
            (self.fixture.expression_artifact_row(
                artifact_type="unknown-expression-type"),
             "expression-artifact-type-unknown"),
            (self.fixture.expression_artifact_row(
                readiness="publication_readiness"),
             "expression-artifact-readiness-field"),
        )
        for value, expected in cases:
            with self.subTest(expected=expected):
                self.fixture.slots.write_text(original, encoding="utf-8")
                if expected == "expression-artifacts-table-header":
                    self.fixture.slots.write_text(value, encoding="utf-8")
                else:
                    self.fixture.configure_expression_artifacts((value,))
                contract = self.fixture.load()
                self.assertFalse(contract.authorized)
                self.assertIn(expected, self.fixture.checks(contract))

    def test_runtime_hub_consumer_uses_only_the_typed_projection(self):
        self.fixture.configure_expression_artifacts((
            self.fixture.expression_artifact_row(),))
        contract = self.fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)
        authorized_view = {"_contract": contract}

        with mock.patch.object(
                control_plane, "profile_view_read_scope_errors",
                return_value=[]):
            paths, errors = control_plane.profile_hub_paths(
                self.fixture.root,
                "profiles/test-profile/profile.md",
                authorized_view=authorized_view,
                profile_read_scope=object())

        self.assertEqual({"Expression/Overview.md"}, paths)
        self.assertEqual([], errors)
        self.assertNotIn("_profile_snapshot", authorized_view)

    def test_agent_atlas_example_projects_its_registered_interview_hub(self):
        manifest = "profiles/examples/agent-atlas/profile.md"
        contract = profile_contract.load_profile_contract(
            REPOSITORY, manifest)

        self.assertTrue(contract.authorized, contract.diagnostics)
        expected = ("Interview Preparation/Interview Overview.md",)
        self.assertEqual(
            expected,
            profile_contract.expression_dependency_map_paths_projection(
                contract))

        authorized_view = {"_contract": contract}
        with mock.patch.object(
                control_plane, "profile_view_read_scope_errors",
                return_value=[]):
            paths, errors = control_plane.profile_hub_paths(
                REPOSITORY, manifest,
                authorized_view=authorized_view,
                profile_read_scope=object())

        self.assertEqual(set(expected), paths)
        self.assertEqual([], errors)


class ProfileExtensionDimensionContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CurrentProfileContractFixture(self)
        self.original = self.fixture.slots.read_text(encoding="utf-8")

    def configure_dimension(self, target):
        self.fixture.slots.write_text(self.original, encoding="utf-8")
        text = self.fixture.slots.read_text(encoding="utf-8")
        start = text.index("## Extension Dimensions")
        end = text.index("\n## ", start + 4)
        section = text[start:end]
        section = section.replace(
            "- Registration: None", "- Registration: Configured", 1)
        separator = "|---|---|---|\n"
        section = section.replace(
            separator,
            separator + "| `custom` | `%s` | Custom fitness. |\n" % target,
            1)
        text = text[:start] + section + text[end:]
        text = text.replace(
            "| `test-profile-foundation-depth` | `content_and_depth` |",
            "| `test-profile-foundation-depth` | `custom` |", 1)
        text = text.replace(
            "| `emits` | `profiles/test-profile/scope-and-architecture.md"
            "#Foundation Depth Requirements` |",
            "| `consumes` | `profiles/test-profile/"
            "scope-and-architecture.md#Foundation Depth Requirements` |",
            1)
        self.fixture.slots.write_text(text, encoding="utf-8")
        return self.fixture.load()

    def test_extension_targets_are_derived_from_the_kernel_mapping(self):
        for declaration, expected in sorted(
                profile_contract.EXTENSION_TARGETS.items()):
            with self.subTest(declaration=declaration):
                contract = self.configure_dimension(declaration)
                self.assertTrue(contract.authorized, contract.diagnostics)
                self.assertEqual(
                    tuple(expected), contract.extension_dimensions[0].targets)

    def test_unknown_extension_target_is_rejected_by_closed_mapping(self):
        contract = self.configure_dimension("unknown-target")

        self.assertFalse(contract.authorized)
        self.assertIn(
            "extension-dimension-target-invalid",
            self.fixture.checks(contract))

    def test_terminal_receipt_projection_excludes_review_only_dimensions(self):
        self.fixture.configure_extension_dimensions((
            ("review_only", "review", "Review-only judgment."),
            ("terminal_receipt", "receipt", "Terminal receipt judgment."),
        ))
        contract = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            tuple(profile_contract.BASE_DIMENSION_ORDER) +
            ("terminal_receipt",),
            profile_contract.terminal_receipt_dimensions_projection(
                contract))


if __name__ == "__main__":
    unittest.main()
