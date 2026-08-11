"""Typed Profile-contract linker tests.

These tests exercise the transitive authority boundary directly.  They do not
run ``check_profile`` or batch close, so a consumer cannot accidentally make a
weak parser look correct.
"""

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import profile_contract


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
    "Deterministic verifier command/path | Candidate predicate/boundary | "
    "Judgment Item ID reference |\n"
    "|---|---|---|---|---|---|\n"
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
        self.owner = self.profile / "predicate.md"
        self.config = self.profile / "scan-configs/residual.yaml"
        self.generic_slot = self.profile / "slots.md"
        self.custom_tool = self.root / "Tools/custom_scan.py"
        self.bundled_tool = self.root / "Tools/check_residual_content.py"
        self.write_defaults()

    def write_defaults(self):
        self.manifest.write_text(
            "# Sample\n\n## Profile Identity\n\n"
            "- `profile_id`: `sample`\n\n"
            "## Implemented Slots\n\n"
            "- `Profile Scope`: `slots.md`\n"
            "- `Corpus Planning`: `slots.md`\n"
            "- `Structure Registry`: `slots.md`\n"
            "- `Metadata Contract`: `slots.md`\n"
            "- `Priority Rubric`: `slots.md`\n"
            "- `Vocabulary Extensions`: `slots.md`\n"
            "- `Language Contract`: `slots.md`\n"
            "- `Expression Layer Entry`: `slots.md`\n"
            "- `Source Policy`: `slots.md`\n"
            "- `Role Registry`: `slots.md`\n"
            "- `Audit Dimension Registry`: "
            "`registries/audit-dimensions.md`\n"
            "- `Registered Scan Registry`: "
            "`registries/registered-scans.md`\n"
            "- `Routing And Gate Registry`: `slots.md`\n",
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

    def write_scans(self, command=None, rows=None, prefix="", suffix=""):
        if command is None:
            command = (
                "python3 Tools/custom_scan.py . --scan-id sample-scan")
        if rows is None:
            rows = (
                "| `sample-scan` | `K12/09 item 6 — residual-content scan` | "
                "Whole repository | `%s` | candidate-only | `sample-item` |\n"
                % command
            )
        self.scans.write_text(
            "# Registered Scan Registry\n\n%s"
            "## Scan Registrations\n\n%s%s%s" %
            (prefix, SCAN_HEADER, rows, suffix),
            encoding="utf-8",
        )

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

    def test_bundled_verifier_accepts_both_config_spellings(self):
        for syntax in (
                "--config profiles/sample/scan-configs/residual.yaml",
                "--config=profiles/sample/scan-configs/residual.yaml"):
            with self.subTest(syntax=syntax):
                self.fixture.write_scans(
                    "python3 Tools/check_residual_content.py . "
                    "--scan-id sample-scan %s --time-limit 55" % syntax)
                contract = self.fixture.load()
                self.assertTrue(contract.authorized, contract.diagnostics)
                self.assertEqual(
                    "profiles/sample/scan-configs/residual.yaml",
                    contract.required_scan.config_dependency.path)

    def test_source_coordinates_and_typed_edges_are_preserved(self):
        self.fixture.write_scans(
            "python3 Tools/check_residual_content.py . "
            "--scan-id=sample-scan "
            "--config=profiles/sample/scan-configs/residual.yaml")
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
        self.fixture.write_scans(
            "python3 Tools/custom_scan.py . --scan-id wrong-id")
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


class PathClosureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ProfileContractFixture(self)
        self.fixture.write_scans(
            "python3 Tools/check_residual_content.py . "
            "--scan-id sample-scan "
            "--config profiles/sample/scan-configs/residual.yaml")

    def checks(self, contract):
        return {diagnostic.check for diagnostic in contract.diagnostics}

    def test_foreign_config_is_rejected_for_both_option_spellings(self):
        foreign = self.fixture.root / "profiles/foreign/config.yaml"
        foreign.parent.mkdir()
        foreign.write_text("schema_version: 1\n", encoding="utf-8")
        for argument in (
                "--config profiles/foreign/config.yaml",
                "--config=profiles/foreign/config.yaml"):
            with self.subTest(argument=argument):
                self.fixture.write_scans(
                    "python3 Tools/check_residual_content.py . "
                    "--scan-id sample-scan %s" % argument)
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
                    "python3 Tools/check_residual_content.py . "
                    "--scan-id sample-scan --config %s" % value)
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
                    "python3 Tools/check_residual_content.py . "
                    "--scan-id sample-scan --config %s" % value)
                self.assertIn(
                    "scan-config-path-invalid",
                    self.checks(self.fixture.load()))
        symlink = self.fixture.profile / "scan-configs/link.yaml"
        symlink.symlink_to(self.fixture.config)
        self.fixture.write_scans(
            "python3 Tools/check_residual_content.py . "
            "--scan-id sample-scan "
            "--config profiles/sample/scan-configs/link.yaml")
        self.assertIn(
            "profile-contract-snapshot-invalid",
            self.checks(self.fixture.load()))

    def test_hardlinked_profile_dependency_is_rejected(self):
        hardlink = self.fixture.profile / "scan-configs/hardlink.yaml"
        os.link(self.fixture.config, hardlink)
        self.fixture.write_scans(
            "python3 Tools/check_residual_content.py . "
            "--scan-id sample-scan "
            "--config profiles/sample/scan-configs/hardlink.yaml")
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
            "python3 Tools/check_residual_content.py . "
            "--scan-id sample-scan "
            "--config profiles/sample/linked-configs/config.yaml")
        self.assertIn("profile-contract-snapshot-invalid",
                      self.checks(self.fixture.load()))

    def test_filesystem_case_alias_is_not_a_canonical_dependency_path(self):
        alias = "profiles/sample/scan-configs/RESIDUAL.yaml"
        if not (self.fixture.root / alias).exists():
            self.skipTest("filesystem is case-sensitive")
        self.fixture.write_scans(
            "python3 Tools/check_residual_content.py . "
            "--scan-id sample-scan --config %s" % alias)

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
            "python3 Tools/check_residual_content.py . "
            "--scan-id sample-scan "
            "--config profiles/sample/scan-configs/residual.bin")

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
            "Whole repository | `python3 Tools/custom_scan.py . "
            "--scan-id sample-scan` | candidate-only | `missing-item` |\n"
        ))
        self.assertIn("registered-scan-judgment-reference", self.checks())

    def test_required_scan_row_must_be_unique(self):
        second = (
            "| `other-scan` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `python3 Tools/custom_scan.py . "
            "--scan-id other-scan` | candidate-only | `sample-item` |\n"
        )
        default = (
            "| `sample-scan` | `K12/09 item 6 — residual-content scan` | "
            "Whole repository | `python3 Tools/custom_scan.py . "
            "--scan-id sample-scan` | candidate-only | `sample-item` |\n"
        )
        self.fixture.write_scans(rows=default + second)
        self.assertIn("registered-scans-required-count", self.checks())

    def test_bundled_verifier_requires_exactly_one_config(self):
        for arguments in (
                "",
                "--config profiles/sample/scan-configs/residual.yaml "
                "--config=profiles/sample/scan-configs/residual.yaml"):
            with self.subTest(arguments=arguments):
                self.fixture.write_scans(
                    "python3 Tools/check_residual_content.py . "
                    "--scan-id sample-scan %s" % arguments)
                self.assertIn("registered-scan-command-config", self.checks())

    def test_command_envelope_is_fail_closed(self):
        commands_and_checks = (
            ("bash Tools/custom_scan.py . --scan-id sample-scan",
             "registered-scan-command-interpreter"),
            ("python3 outside.py . --scan-id sample-scan",
             "registered-scan-command-script"),
            ("python3 Tools/custom_scan.py subdir --scan-id sample-scan",
             "registered-scan-command-root"),
            ("python3 Tools/custom_scan.py . --scan-id wrong",
             "registered-scan-command-scan-id"),
            ("python3 Tools/custom_scan.py . --scan-id sample-scan --receipts x",
             "registered-scan-command-gate-option"),
            ("python3 Tools/custom_scan.py . --scan-id sample-scan ; bad",
             "registered-scan-command-shell-operator"),
        )
        for command, expected in commands_and_checks:
            with self.subTest(command=command):
                self.fixture.write_scans(command)
                self.assertIn(expected, self.checks())

    def test_sentinel_rows_suppress_dependent_diagnostics(self):
        self.fixture.write_audit(judgment_rows=(
            "| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) | "
            "TODO(profile) | TODO(profile) |\n"))
        self.fixture.write_scans(rows=(
            "| TODO(profile) | `K12/09 item 6 — residual-content scan` | "
            "TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |\n"))
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
