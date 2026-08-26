"""Typed Profile-contract linker tests.

These tests exercise the transitive authority boundary directly.  They do not
run ``check_profile`` or batch close, so a consumer cannot accidentally make a
weak parser look correct.
"""

import copy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import kblib
import profile_contract
import control_registry_contract


EXTENSION_HEADER = (
    "| Dimension ID | Target list(s): `review`, `receipt`, or "
    "`review + receipt` | Meaning |\n"
    "|---|---|---|\n"
)
JUDGMENT_HEADER = (
    "| Stable Judgment Item ID | Base or registered receipt Dimension ID | "
    "Exact kernel audit-layer name | Bounded audit object one run proves | "
    "Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner "
    "(repo-relative path; optional `#heading`) |\n"
    "|---|---|---|---|---|---|\n"
)
SCAN_HEADER = (
    "| Stable Scan ID | Activation role | Whole-corpus scope/root | "
    "Verifier capability ID | Profile configuration reference or `None` | "
    "Candidate predicate/boundary | "
    "Judgment Item ID reference |\n"
    "|---|---|---|---|---|---|---|\n"
)
GATE_HEADER = (
    "| " + " | ".join(profile_contract.EXTENSION_GATE_HEADER) + " |\n" +
    "|" + "---|" * len(profile_contract.EXTENSION_GATE_HEADER) + "\n"
)

# Derived from the linker's own registry rather than re-listed: `check_profile`
# refuses a repository whose interface and this registry disagree, so a slot
# added to the interface reaches these fixtures automatically instead of
# waiting for someone to remember five hand-written manifests.
SPECIAL_BINDINGS = {
    profile_contract.AUDIT_SLOT: "registries/audit-dimensions.md",
    profile_contract.SCAN_SLOT: "registries/registered-scans.md",
    profile_contract.ROLE_SLOT: "registries/roles.md",
    profile_contract.VOCABULARY_SLOT: "vocabulary-extensions.yaml",
    profile_contract.METADATA_SLOT: "metadata-contract.yaml",
    profile_contract.ROUTING_SLOT: "registries/routing-and-gates.md",
}
BINDING_BLOCK = "".join(
    "- `%s`: `%s`\n" % (name, SPECIAL_BINDINGS.get(name, "slots.md"))
    for name in profile_contract.PROFILE_FILE_SLOTS
)


class ProfileContractFixture:
    def __init__(self, owner):
        self.temporary = tempfile.TemporaryDirectory()
        owner.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.profile = self.root / "profiles/sample"
        (self.profile / "registries").mkdir(parents=True)
        (self.profile / "scan-configs").mkdir()
        (self.root / "Tools").mkdir()
        self.manifest = self.profile / "profile.md"
        self.audit = self.profile / "registries/audit-dimensions.md"
        self.scans = self.profile / "registries/registered-scans.md"
        self.roles = self.profile / "registries/roles.md"
        self.vocabulary = self.profile / "vocabulary-extensions.yaml"
        self.metadata = self.profile / "metadata-contract.yaml"
        self.routing = self.profile / "registries/routing-and-gates.md"
        self.owner = self.profile / "predicate.md"
        self.config = self.profile / "scan-configs/residual.yaml"
        self.generic_slot = self.profile / "slots.md"
        self.custom_tool = self.root / "Tools/custom_scan.py"
        self.bundled_tool = self.root / "Tools/check_residual_content.py"
        self.capabilities = self.root / "Tools/operation-capabilities.yaml"
        self.scan_capabilities = self.root / profile_contract.SCAN_CAPABILITY_PATH
        self.write_defaults()

    def write_defaults(self):
        for relative in (
                profile_contract.PROFILE_INTERFACE_PATH,
                profile_contract.AUDIT_DIMENSION_BASE_PATH,
                profile_contract.KERNEL_APPLICABILITY_PATH,
                profile_contract.KERNEL_RELATIONSHIP_PATH):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY / relative, target)
        self.manifest.write_text(
            "# Sample\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "## Implemented Slots\n\n" + BINDING_BLOCK,
            encoding="utf-8",
        )
        self.generic_slot.write_text(
            "# Shared fixture slot\n", encoding="utf-8")
        self.owner.write_text(
            "# Predicate\n\n## Acceptance\n\nBounded predicate.\n",
            encoding="utf-8",
        )
        self.config.write_text("schema_version: 1\n", encoding="utf-8")
        for path in (self.custom_tool, self.bundled_tool):
            path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self.write_audit()
        self.write_scans()
        self.write_roles()
        self.write_vocabulary()
        self.write_metadata()
        self.write_gates()
        self.write_capabilities()
        self.write_scan_capabilities()

    def write_audit(self, *, registration="None", extension_rows="",
                    judgment_rows=None, extension_header=EXTENSION_HEADER,
                    judgment_header=JUDGMENT_HEADER, suffix=""):
        if judgment_rows is None:
            judgment_rows = (
                "| `sample-item` | `coverage_and_integration` | "
                "`Batch Review` | One run proves the predicate. | `emits` | "
                "`profiles/sample/predicate.md#Acceptance` |\n"
            )
        self.audit.write_text(
            "# Audit Dimension Registry\n\n"
            "## Extension Dimensions\n\n"
            "- Registration: %s\n\n%s%s\n"
            "## Judgment Items\n\n%s%s%s" %
            (registration, extension_header, extension_rows,
             judgment_header, judgment_rows, suffix),
            encoding="utf-8",
        )

    def write_scans(self, capability="custom-scan-v1", config="None",
                    rows=None, prefix="", suffix=""):
        if rows is None:
            rows = (
                "| `sample-scan` | `K12/09 item 6 — residual-content scan` | "
                "Whole repository | `%s` | `%s` | candidate-only | "
                "`sample-item` |\n" % (capability, config)
            )
        self.scans.write_text(
            "# Registered Scan Registry\n\n%s"
            "## Scan Registrations\n\n%s%s%s" %
            (prefix, SCAN_HEADER, rows, suffix),
            encoding="utf-8",
        )

    def write_roles(self, registration="None", rows=""):
        self.roles.write_text(
            "# Role Registry\n\n"
            "## Process Roles\n\n"
            "| Kernel role | Bound actor or system ID/name |\n"
            "|---|---|\n"
            "| `proposer` | Agent |\n"
            "| `gatekeeper` | Maintainer |\n"
            "| `executor` | Agent |\n"
            "| `stopper` | Maintainer |\n\n"
            "## Knowledge Host\n\n"
            "| Kernel role | Binding |\n"
            "|---|---|\n"
            "| `knowledge-host` | Markdown tree |\n"
            "| `knowledge-host UI` | Headless |\n\n"
            "## Extension Roles\n\n"
            "- Registration: %s\n\n"
            "| Role ID | Bound actor or system ID/name | Responsibility |\n"
            "|---|---|---|\n%s" % (registration, rows),
            encoding="utf-8")

    def write_vocabulary(self, fields=(
            "fields:\n"
            "  unused_state:\n"
            "    values:\n"
            "      - unused\n")):
        self.vocabulary.write_text(
            "schema_version: 1\n" + fields, encoding="utf-8")

    def write_metadata(self, field="unused_state", shape="nonempty-string"):
        self.metadata.write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: configured\n"
            "applicability_differences: []\n"
            "extension_fields:\n"
            "  - field: %s\n"
            "    mode: optional\n"
            "    shape: %s\n"
            "    owner: profiles/sample/predicate.md\n"
            "relationship_extensions: []\n"
            "section_roles: []\n" % (field, shape),
            encoding="utf-8")

    def write_gates(self, registration="None", rows="", header=GATE_HEADER,
                    prefix="", suffix=""):
        self.routing.write_text(
            "# Routing And Gate Registry\n\n%s"
            "## Extension Gates\n\n"
            "- Registration: %s\n\n%s%s%s" %
            (prefix, registration, header, rows, suffix),
            encoding="utf-8")

    def write_capabilities(self):
        self.capabilities.write_text(
            "schema_version: 1\n\n"
            "capabilities:\n"
            "  - capability_id: project-page-state-v2\n"
            "    kind: writer\n"
            "    capability_version: 2.0.0\n"
            "    implementation_paths:\n"
            "      - Tools/custom_scan.py\n"
            "    operations:\n"
            "      - operation: profile-extension-enum-owner-projection-v1\n"
            "  - capability_id: typed-metadata-transition-v1\n"
            "    kind: consumer\n"
            "    capability_version: 1.0.0\n"
            "    implementation_paths:\n"
            "      - Tools/custom_scan.py\n"
            "    operations:\n"
            "      - operation: typed-field-metadata-transition\n"
            "  - capability_id: manual-attestation-v1\n"
            "    kind: producer\n"
            "    capability_version: 1.0.0\n"
            "    implementation_paths:\n"
            "      - Tools/custom_scan.py\n"
            "    operations: []\n"
            "  - capability_id: registered-scan-v1\n"
            "    kind: producer\n"
            "    capability_version: 1.0.0\n"
            "    implementation_paths:\n"
            "      - Tools/custom_scan.py\n"
            "    operations: []\n"
            "  - capability_id: manual-gate-attestation-v1\n"
            "    kind: receipt-schema\n"
            "    capability_version: 1.0.0\n"
            "    implementation_paths:\n"
            "      - Tools/custom_scan.py\n"
            "    operations: []\n"
            "  - capability_id: deterministic-gate-result-v1\n"
            "    kind: receipt-schema\n"
            "    capability_version: 1.0.0\n"
            "    implementation_paths:\n"
            "      - Tools/custom_scan.py\n"
            "    operations: []\n",
            encoding="utf-8")

    def write_scan_capabilities(self):
        self.scan_capabilities.parent.mkdir(parents=True, exist_ok=True)
        self.scan_capabilities.write_text(
            "schema_version: 1\n\n"
            "capabilities:\n"
            "  - capability_id: custom-scan-v1\n"
            "    invocation_contract: profile-registered-scan-v1\n"
            "    implementation_path: Tools/custom_scan.py\n"
            "    configuration: none\n"
            "  - capability_id: residual-content-scan-v1\n"
            "    invocation_contract: profile-registered-scan-v1\n"
            "    implementation_path: Tools/check_residual_content.py\n"
            "    configuration: required\n",
            encoding="utf-8")

    def gate_row(self, *, gate_id="P:sample:readiness",
                 owner="profiles/sample/predicate.md#Acceptance",
                 transition="readiness-promotion", role="stopper",
                 applicability="A readiness promotion is requested.",
                 field="unused_state", completions="unused",
                 judgment="sample-item", producer_kind="manual-attestation",
                 producer_capability="manual-attestation-v1",
                 receipt_schema="manual-gate-attestation-v1",
                 consumer_capability="typed-metadata-transition-v1"):
        return (
            "| `%s` | `%s` | `%s` | `%s` | %s | `%s` | `%s` | `%s` | "
            "`%s` | `%s` | `%s` | `%s` |\n" %
            (gate_id, owner, transition, role, applicability, field,
             completions, judgment, producer_kind, producer_capability,
             receipt_schema, consumer_capability))

    def load(self, manifest=None, sentinel="TODO(profile)"):
        return profile_contract.load_profile_contract(
            self.root, manifest or self.manifest, sentinel=sentinel)


class AuthorizedContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ProfileContractFixture(self)

    def test_custom_verifier_without_config_is_authorized(self):
        contract = self.fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual("profiles/sample/profile.md",
                         contract.manifest_repo_path)
        self.assertEqual("profiles/sample", contract.profile_repo_dir)
        self.assertEqual("sample-scan", contract.required_scan.scan_id)
        command = profile_contract.compile_registered_scan_command(
            self.fixture.root, contract)
        self.assertEqual(str(self.fixture.custom_tool.resolve()), command[1])
        self.assertEqual(str(self.fixture.root.resolve()), command[2])
        self.assertEqual(("--scan-id", "sample-scan"), command[3:])

    def test_profile_interface_must_close_over_the_k12_registry_reference(self):
        interface = (self.fixture.root /
                     profile_contract.PROFILE_INTERFACE_PATH)
        document = kblib.load_yaml_file(interface)
        document["registry_references"]["audit_dimension_base"] = \
            "kernel/K12 Quality Assurance/unknown.yaml"
        kblib.atomic_write_yaml(interface, document)
        contract = self.fixture.load()
        checks = {item.check for item in contract.diagnostics}
        self.assertIn("profile-contract-interface-invalid", checks)
        self.assertTrue(any(
            profile_contract.AUDIT_DIMENSION_BASE_PATH in item.details
            for item in contract.diagnostics), contract.diagnostics)

    def test_required_profile_configuration_is_resolved(self):
        self.fixture.write_scans(
            "residual-content-scan-v1",
            "profiles/sample/scan-configs/residual.yaml")
        contract = self.fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            "profiles/sample/scan-configs/residual.yaml",
            contract.required_scan.config_dependency.path)

    def test_source_coordinates_and_typed_edges_are_preserved(self):
        self.fixture.write_scans(
            "residual-content-scan-v1",
            "profiles/sample/scan-configs/residual.yaml")
        contract = self.fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)
        edges = {
            (edge.kind, edge.owner_id, edge.target_id,
             edge.path, edge.fragment)
            for edge in contract.dependency_edges
        }
        self.assertIn((
            "predicate-owner", "sample-item", None,
            "profiles/sample/predicate.md", "Acceptance"), edges)
        self.assertIn((
            "scan-config", "sample-scan", None,
            "profiles/sample/scan-configs/residual.yaml", None), edges)
        self.assertIn((
            "verifier-capability", "sample-scan", "residual-content-scan-v1",
            "Tools/check_residual_content.py", None), edges)
        self.assertIn((
            "scan-judgment", "sample-scan", "sample-item", None, None),
            edges)
        owner_cell = contract.judgment_items[0].predicate_owner.source
        self.assertEqual("Judgment Items", owner_cell.section)
        self.assertEqual(
            "Predicate owner (repo-relative path; optional `#heading`)",
            owner_cell.field)
        self.assertGreater(owner_cell.line, 0)

    def test_fingerprint_is_deterministic_and_only_authorizes_complete_ir(self):
        first = self.fixture.load()
        second = self.fixture.load()
        self.assertRegex(first.fingerprint, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.fixture.write_scans("unregistered-scan-v1")
        invalid = self.fixture.load()
        self.assertFalse(invalid.authorized)
        self.assertIsNone(invalid.fingerprint)
        with self.assertRaises(profile_contract.ProfileContractError):
            profile_contract.compile_registered_scan_command(
                self.fixture.root, invalid)

    def test_shipped_examples_link(self):
        for relative in (
                "profiles/examples/minimal-notes/profile.md",
                "profiles/examples/worked-planning/profile.md",
                "profiles/examples/agent-atlas/profile.md"):
            with self.subTest(profile=relative):
                contract = profile_contract.load_profile_contract(
                    REPOSITORY, relative)
                self.assertTrue(contract.authorized, contract.diagnostics)
                self.assertIsNotNone(contract.required_scan)
                self.assertIsNotNone(contract.fingerprint)

        atlas = profile_contract.load_profile_contract(
            REPOSITORY, "profiles/examples/agent-atlas/profile.md")
        self.assertEqual("Configured", atlas.extension_gate_registration)
        self.assertEqual(1, len(atlas.extension_gates))
        gate = atlas.extension_gates[0]
        self.assertEqual("interview-readiness-promotion", gate.transition_id)
        self.assertEqual("manual-attestation", gate.producer_kind)
        self.assertEqual("interview-reviewer", gate.producer_reference)
        self.assertEqual(("interview-ready",), gate.completion_values)

        language = (REPOSITORY / "profiles/examples/agent-atlas/"
                    "language-contract.md").read_text(encoding="utf-8")
        for value in (
                "`contract-enumeration`", "`native-structure`",
                "`compressed-narrative`", "`natural-prose`",
                "`retain`", "`rewrite`", "`source-gap`"):
            self.assertIn(value, language)
        self.assertIn(
            "`source-gap` is a rewrite disposition, not a fifth form class",
            language)
        self.assertNotIn(
            "is judged by\nwhether it explains the mechanism",
            language)
        requirement = atlas.batch_review_requirements[0]
        self.assertEqual(
            "agent-atlas-content-form-classification",
            requirement.judgment_item_id)
        item = next(row for row in atlas.judgment_items
                    if row.judgment_item_id ==
                    requirement.judgment_item_id)
        self.assertIn("`form_class`", item.audit_object)
        self.assertIn("`rewrite_disposition`", item.audit_object)
        self.assertIn("`source-gap`", item.audit_object)


class ExtensionGateContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ProfileContractFixture(self)

    def checks(self, contract=None):
        contract = contract or self.fixture.load()
        return {diagnostic.check for diagnostic in contract.diagnostics}

    def configure_manual_gate(self, **overrides):
        self.fixture.write_gates(
            registration="Configured",
            rows=self.fixture.gate_row(**overrides))
        return self.fixture.load()

    def test_manual_gate_compiles_to_typed_ir_and_fingerprint_edges(self):
        baseline = self.fixture.load()
        contract = self.configure_manual_gate()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertNotEqual(baseline.fingerprint, contract.fingerprint)
        self.assertEqual("Configured", contract.extension_gate_registration)
        self.assertEqual(1, len(contract.extension_gates))
        gate = contract.extension_gates[0]
        self.assertEqual("P:sample:readiness", gate.gate_id)
        self.assertEqual("readiness-promotion", gate.transition_id)
        self.assertEqual("stopper", gate.pass_authority_role_id)
        self.assertEqual("unused_state", gate.field_id)
        self.assertEqual(("unused",), gate.completion_values)
        self.assertEqual("stopper", gate.producer_reference)
        edge_kinds = {
            edge.kind for edge in contract.dependency_edges
            if edge.owner_id == gate.gate_id
        }
        self.assertTrue({
            "extension-gate-owner", "extension-gate-transition",
            "extension-gate-role", "extension-gate-field",
            "extension-gate-judgment",
            "extension-gate-producer-capability",
            "extension-gate-producer", "extension-gate-receipt-schema",
            "extension-gate-consumer-capability",
        }.issubset(edge_kinds))

        self.fixture.write_gates(
            registration="Configured",
            rows=self.fixture.gate_row(
                applicability="A different bounded predicate applies."))
        changed_semantics = self.fixture.load()
        self.assertTrue(changed_semantics.authorized,
                        changed_semantics.diagnostics)
        self.assertNotEqual(contract.fingerprint,
                            changed_semantics.fingerprint)

    def test_typed_gate_requires_generic_profile_enum_writer_operation(self):
        text = self.fixture.capabilities.read_text(encoding="utf-8")
        self.fixture.capabilities.write_text(
            text.replace(
                "      - operation: "
                "profile-extension-enum-owner-projection-v1\n", ""),
            encoding="utf-8")
        contract = self.configure_manual_gate()
        self.assertFalse(contract.authorized)
        self.assertIn("extension-gate-writer-capability",
                      self.checks(contract))
        self.assertEqual((), contract.extension_gates)

    def test_extension_role_is_linked_as_manual_producer(self):
        self.fixture.write_roles(
            registration="Configured",
            rows=(
                "| `release-reviewer` | Human reviewer | Authorize release. |\n"))
        contract = self.configure_manual_gate(role="release-reviewer")
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            "release-reviewer", contract.extension_gates[0].producer_reference)

    def test_non_field_gate_requires_a_separate_implemented_consumer(self):
        contract = self.configure_manual_gate(
            field="None", completions="None",
            producer_kind="deterministic",
            producer_capability="registered-scan-v1",
            receipt_schema="deterministic-gate-result-v1")
        self.assertIn(
            "extension-gate-consumer-capability", self.checks(contract))
        self.assertEqual((), contract.extension_gates)

    def test_deterministic_typed_field_binds_one_scan_and_one_value(self):
        contract = self.configure_manual_gate(
            producer_kind="deterministic",
            producer_capability="registered-scan-v1",
            receipt_schema="deterministic-gate-result-v1")
        self.assertTrue(contract.authorized, contract.diagnostics)
        gate = contract.extension_gates[0]
        self.assertEqual("sample-scan", gate.producer_reference)
        self.assertEqual(("unused",), gate.completion_values)

    def test_deterministic_typed_field_rejects_ambiguous_pass_value(self):
        self.fixture.write_vocabulary(
            "fields:\n"
            "  unused_state:\n"
            "    values:\n"
            "      - unused\n"
            "      - ready\n")
        contract = self.configure_manual_gate(
            completions="unused, ready",
            producer_kind="deterministic",
            producer_capability="registered-scan-v1",
            receipt_schema="deterministic-gate-result-v1")
        self.assertIn(
            "extension-gate-deterministic-completion",
            self.checks(contract))
        self.assertEqual((), contract.extension_gates)

    def test_typed_gate_field_requires_metadata_extension_applicability(self):
        self.fixture.metadata.write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: kernel-defaults\n"
            "applicability_differences: []\n"
            "extension_fields: []\n"
            "relationship_extensions: []\n"
            "section_roles: []\n",
            encoding="utf-8")
        contract = self.configure_manual_gate()
        self.assertIn(
            "extension-gate-field-applicability", self.checks(contract))
        self.assertEqual((), contract.extension_gates)

        self.fixture.write_metadata(shape="date")
        contract = self.configure_manual_gate()
        self.assertIn("extension-gate-field-shape", self.checks(contract))
        self.assertEqual((), contract.extension_gates)

    def test_kernel_managed_metadata_difference_cannot_be_profile_gate_field(self):
        self.fixture.write_vocabulary(
            "fields:\n"
            "  learning_status:\n"
            "    values:\n"
            "      - reviewed\n")
        self.fixture.metadata.write_text(
            "schema_version: 1\n"
            "applicability:\n"
            "  state: configured\n"
            "applicability_differences:\n"
            "  - field: learning_status\n"
            "    mode: required\n"
            "extension_fields: []\n"
            "relationship_extensions: []\n"
            "section_roles: []\n",
            encoding="utf-8")
        contract = self.configure_manual_gate(
            field="learning_status", completions="reviewed")
        self.assertIn(
            "extension-gate-field-applicability", self.checks(contract))
        self.assertIn(
            "extension-gate-field-kernel-collision", self.checks(contract))
        self.assertEqual((), contract.extension_gates)

    def test_gate_and_transition_identities_are_each_unique(self):
        first = self.fixture.gate_row()
        second = self.fixture.gate_row(
            gate_id="P:sample:other", transition="other-transition")
        self.fixture.write_gates(
            registration="Configured", rows=first + first)
        self.assertIn("extension-gate-id-duplicate", self.checks())
        self.assertIn("extension-gate-transition-duplicate", self.checks())
        self.fixture.write_gates(
            registration="Configured", rows=first + second.replace(
                "`other-transition`", "`readiness-promotion`"))
        self.assertIn("extension-gate-transition-duplicate", self.checks())

    def test_gate_id_must_use_selected_profile_namespace(self):
        contract = self.configure_manual_gate(
            gate_id="P:foreign:readiness")
        self.assertIn("extension-gate-id-invalid", self.checks(contract))
        self.assertEqual((), contract.extension_gates)

    def test_role_field_value_and_judgment_references_are_closed(self):
        cases = (
            ({"role": "unknown-role"}, "extension-gate-role-reference"),
            ({"field": "unknown_field"}, "extension-gate-field-reference"),
            ({"completions": "unknown"},
             "extension-gate-completion-reference"),
            ({"judgment": "unknown-item"},
             "extension-gate-judgment-reference"),
            ({"field": "None", "completions": "unused"},
             "extension-gate-field-completion"),
            ({"field": "unused_state", "completions": "None"},
             "extension-gate-field-completion"),
        )
        for overrides, expected in cases:
            with self.subTest(expected=expected):
                contract = self.configure_manual_gate(**overrides)
                self.assertIn(expected, self.checks(contract))
                self.assertEqual((), contract.extension_gates)

    def test_multiple_completion_values_normalize_to_one_typed_tuple(self):
        self.fixture.write_vocabulary(
            "fields:\n"
            "  unused_state:\n"
            "    values:\n"
            "      - unused\n"
            "      - ready\n")
        contract = self.configure_manual_gate(completions="unused, ready")
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(
            ("unused", "ready"),
            contract.extension_gates[0].completion_values)

    def test_owner_path_and_kernel_gate_references_must_resolve(self):
        contract = self.configure_manual_gate(
            owner="profiles/sample/predicate.md#Missing")
        self.assertIn("extension-gate-owner-heading-count",
                      self.checks(contract))

        registry = (self.fixture.root /
                    control_registry_contract.STANDARDS_GATE_REGISTRY_PATH)
        registry.parent.mkdir(parents=True, exist_ok=True)
        document = copy.deepcopy(kblib.load_yaml_file(
            REPOSITORY /
            control_registry_contract.STANDARDS_GATE_REGISTRY_PATH))
        document["gates"].append({
            "gate_id": "known-gate",
            "tool": "uninstalled-producer",
            "tool_version": "9.0.0",
            "check": "known-check",
            "mode": "*",
            "dimensions": ["*"],
            "lifecycle": ["not-batch-scoped"],
            "revalidation_role": "unsupported",
            "revalidation_owner": "none",
            "claim_edge": "none",
            "scope_protocol": "none",
            "binding_protocol": "not-authorizing",
        })
        kblib.atomic_write_yaml(registry, document)
        known = self.configure_manual_gate(owner="known-gate")
        self.assertTrue(known.authorized, known.diagnostics)
        self.assertEqual("known-gate", known.extension_gates[0].owner_gate_id)
        unknown = self.configure_manual_gate(owner="missing-gate")
        self.assertIn("extension-gate-owner-reference", self.checks(unknown))

        document["gates"][-1].pop("lifecycle")
        kblib.atomic_write_yaml(registry, document)
        malformed = self.configure_manual_gate(owner="known-gate")
        self.assertIn(
            "extension-gate-owner-registry", self.checks(malformed))

    def test_producer_receipt_and_consumer_capabilities_are_closed(self):
        cases = (
            ({"producer_kind": "script"},
             "extension-gate-producer-kind"),
            ({"producer_capability": "unknown-producer-v1"},
             "extension-gate-producer-capability"),
            ({"receipt_schema": "unknown-receipt-v1"},
             "extension-gate-receipt-schema"),
            ({"consumer_capability": "unknown-consumer-v1"},
             "extension-gate-consumer-capability"),
        )
        for overrides, expected in cases:
            with self.subTest(expected=expected):
                contract = self.configure_manual_gate(**overrides)
                self.assertIn(expected, self.checks(contract))
                self.assertEqual((), contract.extension_gates)

    def test_capability_registry_errors_fail_closed_without_crashing(self):
        self.fixture.write_gates(
            registration="Configured", rows=self.fixture.gate_row())

        self.fixture.capabilities.write_text(
            "schema_version: 1\ncapabilities: invalid\n",
            encoding="utf-8")
        contract = profile_contract.load_profile_contract(
            self.fixture.root, self.fixture.manifest)
        self.assertFalse(contract.authorized)
        self.assertIn("extension-gate-capability-registry",
                      self.checks(contract))
        self.assertEqual((), contract.extension_gates)

    def test_deterministic_gate_without_scan_producer_is_unauthorized(self):
        contract = self.configure_manual_gate(
            judgment="not-produced",
            producer_kind="deterministic",
            producer_capability="registered-scan-v1",
            receipt_schema="deterministic-gate-result-v1")
        checks = self.checks(contract)
        self.assertIn("extension-gate-judgment-reference", checks)
        self.assertIn("extension-gate-producer-reference", checks)

    def test_registration_and_closed_table_shape_fail_closed(self):
        self.fixture.write_gates(
            registration="None", rows=self.fixture.gate_row())
        self.assertIn("extension-gates-none-with-rows", self.checks())
        self.fixture.write_gates(registration="Configured")
        self.assertIn("extension-gates-configured-empty", self.checks())
        self.fixture.write_gates(
            header="| Gate ID |\n|---|\n", registration="None")
        self.assertIn("extension-gates-table-header", self.checks())

    def test_sentinel_gate_row_suppresses_dependent_parsing(self):
        row = "|" + " TODO(profile) |" * len(
            profile_contract.EXTENSION_GATE_HEADER) + "\n"
        self.fixture.write_gates(registration="Configured", rows=row)
        contract = self.fixture.load()
        self.assertEqual({"profile-contract-sentinel"}, self.checks(contract))
        self.assertEqual((), contract.extension_gates)


class PathClosureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ProfileContractFixture(self)
        self.fixture.write_scans(
            "residual-content-scan-v1",
            "profiles/sample/scan-configs/residual.yaml")

    def checks(self, contract):
        return {diagnostic.check for diagnostic in contract.diagnostics}

    def test_foreign_config_is_rejected(self):
        foreign = self.fixture.root / "profiles/foreign/config.yaml"
        foreign.parent.mkdir()
        foreign.write_text("schema_version: 1\n", encoding="utf-8")
        self.fixture.write_scans(
            "residual-content-scan-v1", "profiles/foreign/config.yaml")
        contract = self.fixture.load()
        self.assertIn("scan-config-path-outside-profile",
                      self.checks(contract))
        self.assertIn("profiles/foreign/config.yaml",
                      profile_contract.format_diagnostics(
                          contract.diagnostics))

    def test_noncanonical_config_spellings_are_rejected(self):
        values = (
            "/tmp/config.yaml",
            "profiles/sample/../sample/scan-configs/residual.yaml",
            "profiles/sample//scan-configs/residual.yaml",
            r"profiles\sample\scan-configs\residual.yaml",
        )
        for value in values:
            with self.subTest(value=value):
                self.fixture.write_scans(
                    "residual-content-scan-v1", value)
                contract = self.fixture.load()
                self.assertIn("scan-config-path-invalid",
                              self.checks(contract), contract.diagnostics)

    def test_missing_directory_and_symlink_config_are_rejected(self):
        directory = self.fixture.profile / "scan-configs/directory"
        directory.mkdir()
        for value in (
            "profiles/sample/scan-configs/missing.yaml",
            "profiles/sample/scan-configs/directory",
        ):
            with self.subTest(value=value):
                self.fixture.write_scans(
                    "residual-content-scan-v1", value)
                self.assertIn(
                    "scan-config-path-invalid",
                    self.checks(self.fixture.load()))
        symlink = self.fixture.profile / "scan-configs/link.yaml"
        symlink.symlink_to(self.fixture.config)
        self.fixture.write_scans(
            "residual-content-scan-v1",
            "profiles/sample/scan-configs/link.yaml")
        self.assertIn(
            "profile-contract-snapshot-invalid",
            self.checks(self.fixture.load()))

    def test_hardlinked_profile_dependency_is_rejected(self):
        hardlink = self.fixture.profile / "scan-configs/hardlink.yaml"
        os.link(self.fixture.config, hardlink)
        self.fixture.write_scans(
            "residual-content-scan-v1",
            "profiles/sample/scan-configs/hardlink.yaml")
        self.assertIn("profile-contract-snapshot-invalid",
                      self.checks(self.fixture.load()))

    def test_hardlinked_manifest_is_rejected_by_linker_itself(self):
        source = self.fixture.profile / "manifest-source.md"
        source.write_bytes(self.fixture.manifest.read_bytes())
        self.fixture.manifest.unlink()
        os.link(source, self.fixture.manifest)
        self.assertIn("profile-contract-snapshot-invalid",
                      self.checks(self.fixture.load()))

    def test_hardlinked_bound_registry_is_rejected_by_linker_itself(self):
        source = self.fixture.profile / "registries/audit-source.md"
        source.write_bytes(self.fixture.audit.read_bytes())
        self.fixture.audit.unlink()
        os.link(source, self.fixture.audit)
        self.assertIn("profile-contract-snapshot-invalid",
                      self.checks(self.fixture.load()))

    def test_intermediate_symlink_is_rejected_even_when_target_is_local(self):
        target = self.fixture.profile / "real-configs"
        target.mkdir()
        (target / "config.yaml").write_text("x: 1\n", encoding="utf-8")
        (self.fixture.profile / "linked-configs").symlink_to(target,
                                                             target_is_directory=True)
        self.fixture.write_scans(
            "residual-content-scan-v1",
            "profiles/sample/linked-configs/config.yaml")
        self.assertIn("profile-contract-snapshot-invalid",
                      self.checks(self.fixture.load()))

    def test_filesystem_case_alias_is_not_a_canonical_dependency_path(self):
        alias = "profiles/sample/scan-configs/RESIDUAL.yaml"
        if not (self.fixture.root / alias).exists():
            self.skipTest("filesystem is case-sensitive")
        self.fixture.write_scans(
            "residual-content-scan-v1", alias)

        contract = self.fixture.load()

        self.assertIn("scan-config-path-invalid", self.checks(contract))
        self.assertIn("exactly match repository directory entries",
                      profile_contract.format_diagnostics(
                          contract.diagnostics))

    def test_foreign_predicate_owner_is_rejected(self):
        foreign = self.fixture.root / "profiles/foreign/predicate.md"
        foreign.parent.mkdir()
        foreign.write_text("# Foreign\n\n## Acceptance\n", encoding="utf-8")
        rows = (
            "| `sample-item` | `coverage_and_integration` | `Batch Review` | "
            "One run. | `emits` | "
            "`profiles/foreign/predicate.md#Acceptance` |\n"
        )
        self.fixture.write_audit(judgment_rows=rows)
        contract = self.fixture.load()
        self.assertIn("predicate-owner-path-outside-profile",
                      self.checks(contract))

    def test_heading_must_exist_exactly_once_and_fenced_examples_do_not_count(self):
        self.fixture.owner.write_text(
            "# Predicate\n\n```md\n## Acceptance\n```\n",
            encoding="utf-8")
        missing = self.fixture.load()
        self.assertIn("predicate-owner-heading-count", self.checks(missing))
        self.fixture.owner.write_text(
            "# Predicate\n\n## Acceptance\nA\n\n## Acceptance\nB\n",
            encoding="utf-8")
        duplicate = self.fixture.load()
        self.assertIn("predicate-owner-heading-count", self.checks(duplicate))

    def test_fence_prefix_with_trailing_text_is_not_a_closing_fence(self):
        self.fixture.owner.write_text(
            "# Predicate\n\n```text\n"
            "```not-a-closing-fence\n"
            "## Acceptance\n"
            "```\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertIn("predicate-owner-heading-count", self.checks(contract))

    def test_fence_info_comment_does_not_hide_later_real_heading(self):
        self.fixture.owner.write_text(
            "# Predicate\n\n```lang <!--\nignored\n```\n\n"
            "## Acceptance\nVisible predicate.\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)

    def test_html_comment_heading_is_not_a_predicate_owner_target(self):
        self.fixture.owner.write_text(
            "# Predicate\n\n<!--\n## Acceptance\n-->\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertIn("predicate-owner-heading-count", self.checks(contract))

    def test_raw_html_block_heading_is_not_a_predicate_owner_target(self):
        self.fixture.owner.write_text(
            "# Predicate\n\n<div>raw html\n"
            "## Acceptance\n</div>\n\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertIn("predicate-owner-heading-count", self.checks(contract))

    def test_quoted_html_attribute_cannot_expose_a_hidden_heading(self):
        for quote in ('"', "'"):
            with self.subTest(quote=quote):
                self.fixture.owner.write_text(
                    "# Predicate\n\n<custom data=%sa>b%s>\n"
                    "## Acceptance\n</custom>\n\n" % (quote, quote),
                    encoding="utf-8")
                contract = self.fixture.load()
                self.assertIn(
                    "predicate-owner-heading-count", self.checks(contract))

    def test_closing_hash_requires_whitespace_before_it(self):
        self.fixture.owner.write_text(
            "# Predicate\n\n## Acceptance#\nNot the requested heading.\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertIn("predicate-owner-heading-count", self.checks(contract))

    def test_custom_html_block_heading_is_not_a_predicate_owner_target(self):
        self.fixture.owner.write_text(
            "# Predicate\n\n<x-claim source=\"example\">\n"
            "## Acceptance\n</x-claim>\n\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertIn("predicate-owner-heading-count", self.checks(contract))

    def test_predicate_owner_heading_requires_strict_utf8(self):
        self.fixture.owner.write_bytes(b"# Predicate\n\n## Acceptance\n\xff\n")
        contract = self.fixture.load()
        self.assertIn("predicate-owner-unreadable", self.checks(contract))

    def test_scan_config_requires_strict_utf8(self):
        self.fixture.config.write_bytes(b"schema_version: \xff\n")
        contract = self.fixture.load()
        self.assertIn("scan-config-unreadable", self.checks(contract))

    def test_transitive_dependency_suffix_cannot_hide_unfilled_sentinel(self):
        hidden = self.fixture.profile / "scan-configs/residual.bin"
        hidden.write_text("TODO(profile)\n", encoding="utf-8")
        self.fixture.write_scans(
            "residual-content-scan-v1",
            "profiles/sample/scan-configs/residual.bin")

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIn("profile-contract-sentinel", self.checks(contract))


class RegistryShapeAndCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ProfileContractFixture(self)

    def checks(self, contract=None):
        contract = contract or self.fixture.load()
        return {diagnostic.check for diagnostic in contract.diagnostics}

    def test_all_three_sections_are_exact_and_fence_aware(self):
        self.fixture.write_scans(
            prefix="```md\n## Scan Registrations\n| fake |\n```\n\n")
        contract = self.fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)

    def test_fake_fence_closer_cannot_surface_registry_sections(self):
        self.fixture.write_scans(
            prefix=(
                "```text\n"
                "```not-a-closing-fence\n"
                "## Scan Registrations\n"
                "| fake |\n"
                "```\n\n"))
        self.fixture.write_audit(
            suffix=(
                "\n```text\n"
                "```not-a-closing-fence\n"
                "## Judgment Items\n"
                "| fake |\n"
                "```\n"))

        contract = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.fixture.write_scans(suffix="\n## Scan Registrations\n")
        self.assertIn("registered-scans-section-count", self.checks())

        self.fixture.write_audit(suffix="\n## Judgment Items\n")
        self.assertIn("judgment-items-section-count", self.checks())

    def test_fake_fence_closer_cannot_surface_manifest_slot_bindings(self):
        self.fixture.manifest.write_text(
            "# Sample\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "```text\n"
            "```not-a-closing-fence\n"
            "## Implemented Slots\n\n"
            "- `Audit Dimension Registry`: "
            "`registries/audit-dimensions.md`\n"
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n"
            "```\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIn("profile-contract-slot-missing", self.checks(contract))

    def test_comment_removal_cannot_synthesize_a_manifest_heading(self):
        self.fixture.manifest.write_text(
            "# Sample\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "#<!-- hidden separator --># Implemented Slots\n\n"
            "- `Audit Dimension Registry`: "
            "`registries/audit-dimensions.md`\n"
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIn("profile-contract-slot-missing", self.checks(contract))

    def test_html_comment_line_cannot_supply_a_slot_binding(self):
        self.fixture.manifest.write_text(
            "# Sample\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "## Implemented Slots\n\n"
            "<!-- hidden -->- `Audit Dimension Registry`: "
            "`registries/audit-dimensions.md`\n"
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIn("profile-contract-slot-missing", self.checks(contract))

    def test_indented_code_cannot_supply_a_slot_binding(self):
        self.fixture.manifest.write_text(
            "# Sample\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "## Implemented Slots\n\n"
            "    - `Audit Dimension Registry`: "
            "`registries/audit-dimensions.md`\n"
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIn("profile-contract-slot-missing", self.checks(contract))

    def test_tab_expanded_indented_code_cannot_supply_a_slot_binding(self):
        self.fixture.manifest.write_text(
            "# Sample\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "## Implemented Slots\n\n"
            "  \t- `Audit Dimension Registry`: "
            "`registries/audit-dimensions.md`\n"
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n",
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertFalse(contract.authorized)
        self.assertIn("profile-contract-slot-missing", self.checks(contract))

    def test_exact_code_span_accepts_a_suffix_independent_slot_path(self):
        binary_named_text = self.fixture.profile / "priority.bin"
        binary_named_text.write_text(
            "Strict UTF-8 slot bytes.\n", encoding="utf-8")
        text = self.fixture.manifest.read_text(encoding="utf-8")
        self.fixture.manifest.write_text(
            text.replace(
                "- `Priority Rubric`: `slots.md`",
                "- `Priority Rubric`: `priority.bin`"),
            encoding="utf-8")

        contract = self.fixture.load()

        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertIn(
            ("Priority Rubric", "profiles/sample/priority.bin"),
            {(edge.owner_id, edge.path)
             for edge in contract.dependency_edges
             if edge.kind == "manifest-slot"})

    def test_extension_dimension_schema_and_judgment_reference_are_closed(self):
        self.fixture.write_audit(
            registration="Configured",
            extension_rows=(
                "| `custom` | `review + receipt` | Custom fitness. |\n"),
            judgment_rows=(
                "| `sample-item` | `custom` | `Batch Review` | One run. | "
                "`consumes` | `profiles/sample/predicate.md#Acceptance` |\n"),
        )
        contract = self.fixture.load()
        self.assertTrue(contract.authorized, contract.diagnostics)
        self.assertEqual(("review", "receipt"),
                         contract.extension_dimensions[0].targets)
        self.fixture.write_audit(
            registration="None",
            extension_rows=(
                "| `rendering` | `both` | Collision. |\n"),
            judgment_rows=(
                "| `sample-item` | `unknown_dimension` | `Batch Review` | "
                "One run. | `invalid` | "
                "`profiles/sample/predicate.md#Acceptance` |\n"),
        )
        checks = self.checks()
        self.assertIn("extension-dimension-base-collision", checks)
        self.assertIn("extension-dimension-target-invalid", checks)
        self.assertIn("extension-dimensions-none-with-rows", checks)
        self.assertIn("judgment-item-dimension-unknown", checks)
        self.assertIn("judgment-item-evidence-role-invalid", checks)

    def test_scan_judgment_reference_must_resolve_exactly_once(self):
        self.fixture.write_scans(rows=(
            "| `sample-scan` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `custom-scan-v1` | `None` | candidate-only "
            "| `missing-item` |\n"
        ))
        self.assertIn("registered-scan-judgment-reference", self.checks())

    def test_required_scan_row_must_be_unique(self):
        second = (
            "| `other-scan` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `custom-scan-v1` | `None` | candidate-only "
            "| `sample-item` |\n"
        )
        default = (
            "| `sample-scan` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `custom-scan-v1` | `None` | candidate-only "
            "| `sample-item` |\n"
        )
        self.fixture.write_scans(rows=default + second)
        self.assertIn("registered-scans-required-count", self.checks())

    def test_capability_configuration_contract_is_fail_closed(self):
        self.fixture.write_scans("residual-content-scan-v1", "None")
        self.assertIn("registered-scan-config-required", self.checks())
        self.fixture.write_scans(
            "custom-scan-v1", "profiles/sample/scan-configs/residual.yaml")
        self.assertIn("registered-scan-config-forbidden", self.checks())

    def test_unknown_capability_is_fail_closed(self):
        self.fixture.write_scans("not-registered-v1")
        self.assertIn("registered-scan-capability-unknown", self.checks())

    def test_sentinel_rows_suppress_dependent_diagnostics(self):
        self.fixture.write_audit(judgment_rows=(
            "| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) | "
            "TODO(profile) | TODO(profile) |\n"))
        self.fixture.write_scans(rows=(
            "| TODO(profile) | `K12/09 item 6 — residual-content scan` | "
            "TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) "
            "| TODO(profile) |\n"))
        contract = self.fixture.load()
        checks = self.checks(contract)
        self.assertEqual({"profile-contract-sentinel"}, checks)
        self.assertEqual(2, len(contract.diagnostics))
        self.assertFalse(contract.authorized)
        self.assertIsNone(contract.fingerprint)

    def test_partial_parse_cannot_compile_and_error_includes_source(self):
        wrong_header = "| ID | Target | Meaning |\n|---|---|---|\n"
        self.fixture.write_audit(extension_header=wrong_header)
        contract = self.fixture.load()
        self.assertFalse(contract.authorized)
        with self.assertRaises(profile_contract.ProfileContractError) as caught:
            profile_contract.compile_registered_scan_command(
                self.fixture.root, contract)
        message = str(caught.exception)
        self.assertIn("extension-dimensions-table-header", message)
        self.assertIn("registries/audit-dimensions.md", message)

    def test_compile_rejects_a_different_repository_root(self):
        contract = self.fixture.load()
        with self.assertRaises(profile_contract.ProfileContractError):
            profile_contract.compile_registered_scan_command(
                self.fixture.root.parent, contract)


if __name__ == "__main__":
    unittest.main()
