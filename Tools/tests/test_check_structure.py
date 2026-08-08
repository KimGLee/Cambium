"""Synthetic-fixture tests for check_structure.py (gate: structure-registry).

Rule owners under test: kernel/K01 Scope and Architecture/05 Structural Unit
Interface.md and 06 Support Layer Structural Interfaces.md, through the shared
shape contract in kblib.validate_structure_registry_shape plus the vault
resolution half implemented by the tool. Each negative test carries exactly
one defect so a silently skipped branch cannot hide behind another failure.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_structure.py"


MANIFEST = """# Test Profile

## Implemented Slots

- `Profile Scope`: `scope.md`
- `Corpus Planning`: `corpus-planning.yaml`
- `Structure Registry`: `structure-registry.yaml`
"""

SCOPE = """# Scope

## Logical Architecture

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| `L-DOMAIN` | `Domain` | Own the domain. |
| `L-CASES` | `Cases` | Own the case layer. |
| `L-SYNTHESIS` | `Synthesis` | Own the synthesis layer. |
"""

CORPUS_CONFIGURED = """schema_version: 1
applicability:
  state: configured
  reason: null
artifact_bindings:
  global_map: "planning/global_map.yaml"
  capability_matrix: "planning/capability_matrix.yaml"
  gap_register: "planning/gap_register.yaml"
capability_scale: []
pass_authority:
  role_id: lead
  decision_scope_id: corpus-plan-semantic-acceptance
"""

CORPUS_NOT_APPLICABLE = """schema_version: 1
applicability:
  state: not-applicable
  reason: "No corpus-wide planning."
artifact_bindings:
  global_map: null
  capability_matrix: null
  gap_register: null
capability_scale: []
pass_authority:
  role_id: null
  decision_scope_id: null
"""

GLOBAL_MAP = """schema_version: 1
entries:
  - entry_id: E-DOMAIN
    layer_id: L-DOMAIN
    canonical_markdown_path: "Domain/Domain Overview.md"
    single_responsibility: "Own the domain."
  - entry_id: E-CASES
    layer_id: L-CASES
    canonical_markdown_path: "Cases/Cases Overview.md"
    single_responsibility: "Own the case layer."
typed_dependencies: []
"""

DOMAIN_OVERVIEW = """---
type: overview
---
# Domain Overview

## Reading Order

Read things in order.

## Coverage Reader View

Derived projection renders here.
"""

MODULE_ENTRY = """---
type: system-design
---
# Sub Entry

## Execution Path

Steps.
"""

CASES_OVERVIEW = """---
type: overview
---
# Cases Overview
"""

CASE_PAGE = """---
type: case-study
case_class: reported-system
---
# Case A
"""

SYNTHESIS_OVERVIEW = """---
type: overview
---
# Synthesis Overview
"""

SYNTHESIS_PAGE = """---
type: research-synthesis
---
# Question One
"""


def registry_yaml(units="", support_layers=""):
    return (
        "schema_version: 1\n"
        "applicability:\n"
        "  state: configured\n"
        "  reason: null\n"
        "units:\n%s"
        "support_layers:%s\n"
    ) % (units, ("\n" + support_layers) if support_layers else " []")


UNIT_DOMAIN = """  - id: U-DOMAIN
    kind: domain
    parent: null
    root: "Domain"
    entry:
      path: "Domain/Domain Overview.md"
      expected_type: overview
    global_map_entry: E-DOMAIN
    roles:
      sequence:
        mode: embedded
        path: "Domain/Domain Overview.md"
        heading: "Reading Order"
      coverage:
        mode: derived
        generator: "Tools/gen.py"
        inputs_owner: "planning/global_map.yaml"
        path: "Domain/Domain Overview.md"
        heading: "Coverage Reader View"
      quick_reference:
        mode: not-applicable
        reason: "No quick reference is maintained."
      expression:
        mode: not-applicable
        reason: "No expression layer."
"""

UNIT_MODULE = """  - id: U-SUB
    kind: module
    parent: U-DOMAIN
    root: "Domain/Sub"
    entry:
      path: "Domain/Sub/Sub Entry.md"
      expected_type: system-design
    global_map_entry: null
    roles:
      sequence:
        mode: embedded
        path: "Domain/Sub/Sub Entry.md"
        heading: "Execution Path"
      coverage:
        mode: not-applicable
        reason: "Projected through the parent domain."
      quick_reference:
        mode: not-applicable
        reason: "Parent entry routes here."
      expression:
        mode: not-applicable
        reason: "No expression layer."
"""

LAYER_CASES = """  - layer_id: L-CASES
    role: cases
    root: "Cases"
    entry:
      path: "Cases/Cases Overview.md"
      expected_type: overview
    global_map_entry: E-CASES
    layout: grouped
    taxonomy:
      axis: evidence-form
      page_field: case_class
      classes:
        - class: reported-system
          directory: "Cases/Reported"
    coverage:
      mode: not-applicable
      reason: "No coverage projection yet."
    bindings:
      evidence_binding_owner: "planning/global_map.yaml"
"""

LAYER_SYNTHESIS = """  - layer_id: L-SYNTHESIS
    role: synthesis
    root: "Synthesis"
    entry:
      path: "Synthesis/Synthesis Overview.md"
      expected_type: overview
    global_map_entry: null
    layout: flat
    taxonomy: null
    coverage:
      mode: not-applicable
      reason: "No coverage projection yet."
    bindings:
      question_identity_field: "claim_scope"
      promotion_policy_ref: "planning/global_map.yaml"
"""


def base_files():
    return {
        "profile/profile.md": MANIFEST,
        "profile/scope.md": SCOPE,
        "profile/corpus-planning.yaml": CORPUS_CONFIGURED,
        "planning/global_map.yaml": GLOBAL_MAP,
        "planning/capability_matrix.yaml": "schema_version: 1\n",
        "planning/gap_register.yaml": "schema_version: 1\n",
        "Tools/gen.py": "print('derived')\n",
        "Domain/Domain Overview.md": DOMAIN_OVERVIEW,
        "Domain/Sub/Sub Entry.md": MODULE_ENTRY,
        "Cases/Cases Overview.md": CASES_OVERVIEW,
        "Cases/Reported/Case A.md": CASE_PAGE,
        "Synthesis/Synthesis Overview.md": SYNTHESIS_OVERVIEW,
        "Synthesis/Question One.md": SYNTHESIS_PAGE,
        "profile/structure-registry.yaml": registry_yaml(
            UNIT_DOMAIN + UNIT_MODULE, LAYER_CASES + LAYER_SYNTHESIS),
    }


class CheckStructureTests(unittest.TestCase):
    def run_check(self, files, *args):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(root),
                 "--profile", "profile", *args],
                text=True, capture_output=True, check=False)

    def assert_fail(self, result, needle):
        self.assertEqual(result.returncode, 1,
                         result.stdout + result.stderr)
        self.assertIn(needle, result.stdout)

    # ---- positive controls ----

    def test_configured_registry_resolves(self):
        result = self.run_check(base_files())
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        self.assertIn("units=2 modules=1 support_layers=2", result.stdout)
        self.assertIn("errors=0", result.stdout)

    def test_not_applicable_registry_passes_with_empty_sets(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = (
            "schema_version: 1\n"
            "applicability:\n"
            "  state: not-applicable\n"
            "  reason: \"Flat corpus; nothing passes the module admission "
            "test.\"\n"
            "units: []\n"
            "support_layers: []\n")
        result = self.run_check(files)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        self.assertIn("state=not-applicable", result.stdout)

    # ---- fail-closed scope ----

    def test_missing_registry_binding_fails_closed(self):
        files = base_files()
        files["profile/profile.md"] = MANIFEST.replace(
            "- `Structure Registry`: `structure-registry.yaml`\n", "")
        result = self.run_check(files)
        self.assert_fail(result, "does not bind the `Structure Registry`")

    def test_unparseable_registry_fails_closed(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = "::not yaml::\n"
        result = self.run_check(files)
        self.assert_fail(result, "cannot parse the registry")

    def test_missing_profile_directory_fails_closed(self):
        result = self.run_check({"README.md": "x\n"})
        self.assert_fail(result, "--profile does not name an existing")

    def test_configured_with_no_units_fails_closed(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = (
            "schema_version: 1\n"
            "applicability:\n"
            "  state: configured\n"
            "  reason: null\n"
            "units: []\n"
            "support_layers: []\n")
        result = self.run_check(files)
        self.assert_fail(result, "configured requires at least one unit")

    # ---- shape defects (shared contract) ----

    def test_unknown_top_level_field_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = (
            registry_yaml(UNIT_DOMAIN) + "batch_state: open\n")
        result = self.run_check(files)
        self.assert_fail(result, "unsupported field(s): batch_state")

    def test_duplicate_unit_id_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN + UNIT_DOMAIN)
        result = self.run_check(files)
        self.assert_fail(result, "duplicate unit id")

    def test_module_with_unregistered_parent_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN + UNIT_MODULE.replace(
                "parent: U-DOMAIN", "parent: U-GHOST"))
        result = self.run_check(files)
        self.assert_fail(result, "not a registered unit id")

    def test_parent_cycle_fails(self):
        files = base_files()
        cyclic = (UNIT_MODULE
                  + UNIT_MODULE.replace("U-SUB", "U-SUB2")
                  .replace("parent: U-DOMAIN", "parent: U-SUB"))
        cyclic = cyclic.replace("parent: U-DOMAIN", "parent: U-SUB2", 1)
        files["profile/structure-registry.yaml"] = registry_yaml(cyclic)
        result = self.run_check(files)
        self.assert_fail(result, "cycle")

    def test_missing_role_declaration_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN.replace(
                "      quick_reference:\n"
                "        mode: not-applicable\n"
                "        reason: \"No quick reference is maintained.\"\n",
                ""))
        result = self.run_check(files)
        self.assert_fail(result, "missing field(s): quick_reference")

    def test_unknown_role_mode_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN.replace("mode: not-applicable", "mode: implicit", 1))
        result = self.run_check(files)
        self.assert_fail(result, "absence of a declaration must not")

    def test_invalid_index_mode_fails(self):
        files = base_files()
        sources_layer = LAYER_SYNTHESIS.replace(
            "role: synthesis", "role: sources").replace(
            "    bindings:\n"
            "      question_identity_field: \"claim_scope\"\n"
            "      promotion_policy_ref: \"planning/global_map.yaml\"\n",
            "    bindings:\n"
            "      authority_taxonomy_ref: \"planning/global_map.yaml\"\n"
            "      intake_policy_ref: \"planning/global_map.yaml\"\n"
            "      freshness_policy_ref: \"planning/global_map.yaml\"\n"
            "      index_mode: manual\n")
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN, sources_layer)
        result = self.run_check(files)
        self.assert_fail(result, "must be derived or none")

    # ---- vault resolution defects ----

    def test_embedded_heading_missing_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN.replace('heading: "Reading Order"',
                                'heading: "Missing Order"'))
        result = self.run_check(files)
        self.assert_fail(result, "'Missing Order' not found")

    def test_expected_type_mismatch_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN.replace("expected_type: overview",
                                "expected_type: roadmap"))
        result = self.run_check(files)
        self.assert_fail(result, "expected 'roadmap'")

    def test_domain_root_outside_profile_scope_layers_fails(self):
        files = base_files()
        files["Elsewhere/Elsewhere Overview.md"] = DOMAIN_OVERVIEW
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN.replace('root: "Domain"', 'root: "Elsewhere"')
            .replace("Domain/Domain Overview.md",
                     "Elsewhere/Elsewhere Overview.md"))
        result = self.run_check(files)
        self.assert_fail(result, "registered layer directories")

    def test_module_root_outside_parent_fails(self):
        files = base_files()
        files["Cases/Stray/Stray Entry.md"] = MODULE_ENTRY
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN + UNIT_MODULE
            .replace('root: "Domain/Sub"', 'root: "Cases/Stray"')
            .replace("Domain/Sub/Sub Entry.md", "Cases/Stray/Stray Entry.md"))
        result = self.run_check(files)
        self.assert_fail(result, "strictly inside its parent's root")

    def test_grouped_page_class_mismatch_fails(self):
        files = base_files()
        files["Cases/Reported/Case A.md"] = CASE_PAGE.replace(
            "case_class: reported-system", "case_class: controlled-study")
        result = self.run_check(files)
        self.assert_fail(result, "the declared class and the path must agree")

    def test_grouped_stray_root_page_fails(self):
        files = base_files()
        files["Cases/Unfiled Case.md"] = CASE_PAGE
        result = self.run_check(files)
        self.assert_fail(result, "neither the canonical entry nor inside")

    def test_flat_layout_with_subdirectory_page_fails(self):
        files = base_files()
        files["Synthesis/Group/Question Two.md"] = SYNTHESIS_PAGE
        result = self.run_check(files)
        self.assert_fail(result, "sits in a subdirectory")

    def test_global_map_entry_without_configured_planning_fails(self):
        files = base_files()
        files["profile/corpus-planning.yaml"] = CORPUS_NOT_APPLICABLE
        result = self.run_check(files)
        self.assert_fail(result, "Corpus Planning is not configured")

    def test_unknown_global_map_entry_fails(self):
        files = base_files()
        files["profile/structure-registry.yaml"] = registry_yaml(
            UNIT_DOMAIN.replace("global_map_entry: E-DOMAIN",
                                "global_map_entry: E-GHOST"))
        result = self.run_check(files)
        self.assert_fail(result, "not registered in the Global Map")

    def test_coverage_ledger_unknown_structural_unit_fails(self):
        files = base_files()
        files[".cambium/state/coverage_ledger.yaml"] = (
            "schema_version: 1\n"
            "pages:\n"
            "  - path: \"Domain/Domain Overview.md\"\n"
            "    structural_unit: U-GHOST\n")
        result = self.run_check(files)
        self.assert_fail(result, "not a registered unit or support layer id")

    def test_coverage_ledger_registered_structural_unit_passes(self):
        files = base_files()
        files[".cambium/state/coverage_ledger.yaml"] = (
            "schema_version: 1\n"
            "pages:\n"
            "  - path: \"Domain/Sub/Sub Entry.md\"\n"
            "    structural_unit: U-SUB\n")
        result = self.run_check(files)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
