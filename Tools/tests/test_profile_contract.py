"""Primary owner tests for the current typed Profile machine contract.

The linker owns closed machine fields, exact Profile slot bindings, and the
typed dependency graph. Profile-load transport, filesystem races, template
parity, examples, onboarding, and adoption have separate primary suites.
"""

import copy
from pathlib import Path
import unittest

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
    def test_interface_slots_and_scan_capabilities_derive_from_current_owners(self):
        interface = profile_contract.load_profile_interface(REPOSITORY)
        slots = profile_contract.profile_interface_slots(interface)
        scan_registry = profile_contract.load_scan_capabilities(REPOSITORY)
        scans = profile_contract.scan_capability_records(scan_registry)

        self.assertEqual(profile_contract.PROFILE_FILE_SLOTS, slots)
        self.assertEqual(len(slots), len(set(slots)))
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

        unknown_scan = copy.deepcopy(scan_registry)
        unknown_scan["capabilities"][0]["unknown_field"] = None
        cases.append((profile_contract.scan_capability_records,
                      unknown_scan, "fields are not closed"))

        for parser, document, expected in cases:
            with self.subTest(parser=parser.__name__):
                with self.assertRaisesRegex(ValueError, expected):
                    parser(document)


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

    def test_slot_binding_rejections_are_one_table_driven_contract(self):
        original = self.fixture.manifest.read_text(encoding="utf-8")
        line = "- `Priority Rubric`: `slots.md`\n"
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

        line = "- `Priority Rubric`: `slots.md`\n"
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
            "| `emits` | `profiles/test-profile/slots.md#Synthetic Predicate` |",
            "| `consumes` | `profiles/test-profile/slots.md#Synthetic Predicate` |",
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


if __name__ == "__main__":
    unittest.main()
