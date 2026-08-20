"""Synthetic-fixture tests for compose_page_contract.py and
check_page_contract.py (gate: page-contract, advisory).

Rule owners under test: kernel/K08 Metadata and Status/06-08 through the
shared shape contract in kblib.validate_metadata_contract_shape plus the
composition and page-validation halves. Each negative test carries exactly
one defect.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from Tools.tests.profile_fixture import install_loadable_profile

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import metadata_execution_contract
import metadata_property_state
import project_page_state

COMPOSER = TOOLS / "compose_page_contract.py"
CHECKER = TOOLS / "check_page_contract.py"

APPLICABILITY_BASE = """schema_version: 1
fields:
  type:
    mode: required
    shape: nonempty-string
  depth:
    mode: optional
    shape: nonempty-string
  authoring_status:
    mode: projection
    shape: nonempty-string
  learning_status:
    mode: user-owned
    shape: nonempty-string
  coverage_disposition:
    mode: projection
    shape: nonempty-string
  deferred_reason:
    mode: conditional
    shape: nonempty-string
    condition:
      all:
        - field: coverage_disposition
          in:
            - deferred
  aliases:
    mode: optional
    shape: list-of-strings
  last_verified:
    mode: optional
    shape: date
  last_content_modified:
    mode: optional
    shape: date
  last_reviewed:
    mode: conditional
    shape: date
    condition:
      all:
        - field: authoring_status
          in:
            - reviewed
  review_by:
    mode: derived
    shape: date
    persisted: false
  boundary:
    mode: optional
    shape: delegated
    delegate: boundary-contract
"""

SOURCES_ROLE_BASE = """schema_version: 1
role: sources
default_titles:
  - Sources
applicability:
  condition:
    any:
      - field: depth
        in:
          - core
          - system
binding_satisfies:
  fields:
    - evidence_sources
  directions:
    - expression-to-canonical
"""

RELATIONSHIP_BASE = """schema_version: 1
relationships:
  source_url:
    mode: conditional
    condition:
      all:
        - field: type
          in:
            - source-note
    direction: page-to-external
    target: external-original
    shape: url
  evidence_sources:
    mode: optional
    direction: evidence-input
    target:
      - source-note
    shape: list-of-paths
"""

MANIFEST = """# Test Profile

## Implemented Slots

- `Profile Scope`: `scope.md`
- `Metadata Contract`: `metadata-contract.yaml`
- `Vocabulary Extensions`: `vocabulary-extensions.yaml`
"""

SCOPE = """# Scope

## Logical Architecture

| Stable Layer ID | Repository-relative directories | Single layer responsibility |
|---|---|---|
| `L-DOMAIN` | `Domain` | Own the domain. |
"""

VOCAB = """schema_version: 1
frontmatter_extensions:
  fields: []
"""

CONTRACT_DEFAULTS = """schema_version: 1
applicability:
  state: kernel-defaults
applicability_differences: []
extension_fields: []
relationship_extensions: []
section_roles: []
"""

CONTRACT_CONFIGURED = """schema_version: 1
applicability:
  state: configured
applicability_differences:
  - field: last_verified
    mode: required
extension_fields:
  - field: card_binding
    mode: optional
    shape: path
    owner: "scope.md"
relationship_extensions: []
section_roles: []
"""

GOOD_PAGE = """---
type: concept
authoring_status: drafted
---
# Page
"""


def base_files(contract=CONTRACT_DEFAULTS):
    return {
        "kernel/applicability-base.yaml": APPLICABILITY_BASE,
        "kernel/relationship-base.yaml": RELATIONSHIP_BASE,
        "kernel/sources-role-base.yaml": SOURCES_ROLE_BASE,
        "profile/profile.md": MANIFEST,
        "profile/scope.md": SCOPE,
        "profile/vocabulary-extensions.yaml": VOCAB,
        "profile/metadata-contract.yaml": contract,
        "Domain/Page.md": GOOD_PAGE,
    }


class PageContractTests(unittest.TestCase):
    def build(self, files):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        profile = install_loadable_profile(root)
        manifest = profile / "profile.md"
        manifest_text = manifest.read_text(encoding="utf-8")
        custom_manifest = files.get("profile/profile.md", MANIFEST)
        for line in custom_manifest.splitlines():
            if not line.startswith("- `") or "`: `" not in line:
                continue
            slot = line.split("`", 2)[1]
            existing = next(
                (candidate for candidate in manifest_text.splitlines()
                 if candidate.startswith("- `%s`:" % slot)),
                None,
            )
            if existing is not None:
                manifest_text = manifest_text.replace(existing, line)
        manifest.write_text(manifest_text, encoding="utf-8")
        for rel, text in files.items():
            if rel == "profile/profile.md":
                continue
            if rel.startswith("profile/"):
                rel = "profiles/test-profile/" + rel[len("profile/"):]
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    def compose(self, root, expect=0):
        result = subprocess.run(
            [sys.executable, str(COMPOSER), "--root", str(root),
             "--base", str(root / "kernel/applicability-base.yaml"),
             "--relationships", str(root / "kernel/relationship-base.yaml"),
             "--sources-role", str(root / "kernel/sources-role-base.yaml"),
             "--profile", "profiles/test-profile",
             "--output", str(root / "page_contract.yaml")],
            text=True, capture_output=True, check=False)
        self.assertEqual(expect, result.returncode,
                         result.stdout + result.stderr)
        return result

    def check(self, root, *args):
        return subprocess.run(
            [sys.executable, str(CHECKER), str(root),
             "--profile", "profiles/test-profile",
             "--contract", str(root / "page_contract.yaml"), *args],
            text=True, capture_output=True, check=False)

    def semantic_fingerprint(self, root, relative, text):
        metadata_contract = \
            metadata_execution_contract.load_metadata_execution_contract(
                root)
        rules = metadata_property_state.profile_gate_projection_rules(
            root, (), metadata_contract=metadata_contract,
            authorized_profile_contract=SimpleNamespace(
                authorized=True, extension_gates=(),
                profile_contract_fingerprint="sha256:" + "f" * 64))
        return project_page_state.semantic_content_fingerprint(
            relative, text, rules)

    # ---- composition ----

    def test_kernel_defaults_compose_and_pass(self):
        root = self.build(base_files())
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)

    def test_composition_is_deterministic_and_check_mode_works(self):
        root = self.build(base_files())
        self.compose(root)
        first = (root / "page_contract.yaml").read_bytes()
        self.compose(root)
        self.assertEqual(first, (root / "page_contract.yaml").read_bytes())
        result = subprocess.run(
            [sys.executable, str(COMPOSER), "--root", str(root),
             "--base", str(root / "kernel/applicability-base.yaml"),
             "--relationships", str(root / "kernel/relationship-base.yaml"),
             "--sources-role", str(root / "kernel/sources-role-base.yaml"),
             "--profile", "profiles/test-profile",
             "--output", str(root / "page_contract.yaml"), "--check"],
            text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)

    def test_kernel_base_byte_change_makes_compiled_contract_stale(self):
        root = self.build(base_files())
        self.compose(root)
        base = root / "kernel/applicability-base.yaml"
        base.write_text(
            base.read_text(encoding="utf-8") + "\n# revision B\n",
            encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(COMPOSER), "--root", str(root),
             "--base", str(base),
             "--relationships", str(root / "kernel/relationship-base.yaml"),
             "--sources-role", str(root / "kernel/sources-role-base.yaml"),
             "--profile", "profiles/test-profile",
             "--output", str(root / "page_contract.yaml"), "--check"],
            text=True, capture_output=True, check=False)

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("is stale", result.stdout)

    def test_unrelated_unloadable_slot_blocks_composition(self):
        files = base_files()
        files["profile/profile.md"] = MANIFEST + \
            "- `Priority Rubric`: `broken-priority.md`\n"
        files["profile/broken-priority.md"] = "TODO(profile)\n"
        root = self.build(files)
        result = self.compose(root, expect=1)
        self.assertIn("profile-load", result.stdout)
        self.assertIn("TODO(profile)", result.stdout)

    def test_unrelated_slot_breakage_blocks_page_gate_after_composition(self):
        root = self.build(base_files())
        self.compose(root)
        manifest = root / "profiles/test-profile/profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "- `Priority Rubric`: `slots.md`",
                "- `Priority Rubric`: `broken-priority.md`"),
            encoding="utf-8")
        (manifest.parent / "broken-priority.md").write_text(
            "TODO(profile)\n", encoding="utf-8")
        result = self.check(root)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("profile-load", result.stdout)

    def test_profile_change_rejects_prechange_compiled_contract(self):
        """A valid Profile B cannot consume a page contract compiled for A."""
        root = self.build(base_files())
        self.compose(root)
        metadata = root / "profiles/test-profile/metadata-contract.yaml"
        metadata.write_text(CONTRACT_CONFIGURED, encoding="utf-8")

        result = self.check(root, "--strict")

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("compiled page contract", result.stdout)
        self.assertIn("does not match the selected Profile", result.stdout)

    def test_loosening_difference_is_a_conflict(self):
        files = base_files(CONTRACT_CONFIGURED.replace(
            "  - field: last_verified\n    mode: required",
            "  - field: type\n    mode: conditional\n"
            "    condition:\n"
            "      all:\n"
            "        - field: type\n"
            "          in:\n"
            "            - concept"))
        root = self.build(files)
        result = self.compose(root, expect=1)
        self.assertIn("not a tightening", result.stdout)

    def test_difference_must_name_a_kernel_field(self):
        files = base_files(CONTRACT_CONFIGURED.replace(
            "field: last_verified", "field: unheard_of"))
        root = self.build(files)
        result = self.compose(root, expect=1)
        self.assertIn("does not name a kernel base field", result.stdout)

    def test_extension_collision_with_kernel_field_is_a_conflict(self):
        files = base_files(CONTRACT_CONFIGURED.replace(
            "field: card_binding", "field: aliases"))
        root = self.build(files)
        result = self.compose(root, expect=1)
        self.assertIn("declared twice", result.stdout)

    # ---- page validation ----

    def test_missing_required_field_is_a_candidate_in_advisory(self):
        files = base_files()
        files["Domain/Page.md"] = "---\nauthoring_status: drafted\n---\n# P\n"
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("type", result.stdout)
        self.assertIn("advisory candidates", result.stdout)

    def test_strict_mode_turns_violations_into_failures(self):
        files = base_files()
        files["Domain/Page.md"] = "---\nauthoring_status: drafted\n---\n# P\n"
        root = self.build(files)
        self.compose(root)
        result = self.check(root, "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_conditional_field_required_when_condition_holds(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "coverage_disposition: deferred\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("deferred_reason", result.stdout)

    def test_delegated_boundary_block_is_known_and_not_shape_checked(self):
        # K08/09: presence and mode stay here; the block's internal
        # structure belongs to the boundary-contract gate, so even a
        # block that gate would reject passes page-contract.
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "boundary:\n  owns:\n    - Not_A_Slug\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)

    def test_present_but_empty_value_is_placeholder_noise(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "aliases: []\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("placeholder", result.stdout)

    def test_persisted_derived_value_is_reported(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "review_by: 2026-01-01\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("not persisted on pages", result.stdout)

    def test_absent_user_owned_field_is_never_a_defect(self):
        root = self.build(base_files())
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_unknown_field_hits_the_closure(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "source_set: something\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("unknown fields are not open metadata", result.stdout)

    def test_legacy_status_alias_is_reported_for_migration(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "status: reviewed\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("legacy `status` alias", result.stdout)

    def test_registered_extension_field_is_known(self):
        files = base_files(CONTRACT_CONFIGURED)
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "last_verified: 2026-08-01\n"
            "card_binding: \"Domain/Page\"\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_tightened_field_is_enforced(self):
        files = base_files(CONTRACT_CONFIGURED)
        root = self.build(files)   # Domain/Page.md has no last_verified
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("last_verified", result.stdout)

    def test_bad_date_shape_is_reported(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "last_verified: soon\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("YYYY-MM-DD", result.stdout)

    def test_source_url_required_on_source_note_and_must_be_external(self):
        files = base_files()
        files["Domain/Source.md"] = (
            "---\ntype: source-note\nauthoring_status: drafted\n"
            "source_url: \"Domain/Page.md\"\n---\n# S\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("external http(s) URL", result.stdout)

    def test_evidence_sources_targets_must_be_source_notes(self):
        files = base_files()
        files["Domain/Source.md"] = (
            "---\ntype: source-note\nauthoring_status: drafted\n"
            "source_url: \"https://example.org/doc\"\n---\n# S\n")
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "evidence_sources:\n  - \"Domain/Source\"\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_evidence_sources_wrong_target_type_is_reported(self):
        files = base_files()
        files["Domain/Other.md"] = GOOD_PAGE
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "evidence_sources:\n  - \"Domain/Other\"\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("expected one of source-note", result.stdout)

    def test_unresolvable_evidence_target_is_reported(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "evidence_sources:\n  - \"Domain/Ghost\"\n---\n# P\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("does not resolve inside the vault", result.stdout)

    def test_projection_disagreeing_with_ledger_is_reported(self):
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "coverage_disposition: optional\n---\n# P\n")
        files[".cambium/state/coverage_ledger.yaml"] = (
            "schema_version: 1\npages:\n"
            "  - path: \"Domain/Page.md\"\n"
            "    coverage_disposition: required\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("disagrees with the Coverage Ledger", result.stdout)

    def test_authoring_status_projection_reconciles_like_any_other(self):
        # K08/07: authoring_status is Ledger-earned; a page copy still
        # showing the pre-close value after the Ledger moved is a defect.
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n---\n# P\n")
        files[".cambium/state/coverage_ledger.yaml"] = (
            "schema_version: 1\npages:\n"
            "  - path: \"Domain/Page.md\"\n"
            "    coverage_disposition: required\n"
            "    authoring_status: reviewed\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("disagrees with the Coverage Ledger", result.stdout)

    def test_stale_projection_with_empty_owner_is_reported(self):
        # The classic dangling reference: the batch closed, the Ledger
        # projected next_batch onward to empty, the page copy still names
        # the closed batch.  (Modeled here on coverage_disposition, the
        # projection field the shared fixture carries.)
        files = base_files()
        files["Domain/Page.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n"
            "coverage_disposition: required\n---\n# P\n")
        files[".cambium/state/coverage_ledger.yaml"] = (
            "schema_version: 1\npages:\n"
            "  - path: \"Domain/Page.md\"\n"
            "    coverage_disposition:\n"
            "    authoring_status: drafted\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("is stale", result.stdout)

    def test_conditional_applicability_does_not_bypass_owner_authority(self):
        """A false presence condition does not make a machine copy optional.

        ``last_reviewed`` is not applicability-required while the page is
        drafted, but once the evidence owner has a current value the page-side
        projection must still reconcile to it.  This is the D-007 axis split:
        applicability answers *when a field is owed*; authority answers *who
        may write its current value*.
        """
        files = base_files()
        page = (
            "---\ntype: concept\nauthoring_status: drafted\n---\n"
            "# P\n\nSubstantive content.\n")
        files["Domain/Page.md"] = page
        root = self.build(files)
        self.compose(root)
        fingerprint = self.semantic_fingerprint(
            root, "Domain/Page.md", page)
        ledger = {
            "schema_version": 1,
            "pages": [{
                "path": "Domain/Page.md",
                "coverage_disposition": "required",
                "authoring_status": "drafted",
                "property_state": {
                    "last_reviewed": {
                        "value": "2026-08-20",
                        "evidence_receipt": "review-receipt-1",
                        "content_fingerprint": fingerprint,
                    },
                },
            }],
        }
        ledger_path = root / ".cambium/state/coverage_ledger.yaml"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        import kblib
        ledger_path.write_text(kblib.canonical_yaml(ledger),
                               encoding="utf-8")

        result = self.check(root)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("last_reviewed", result.stdout)
        self.assertIn("must equal current owner value", result.stdout)
        self.assertNotIn("condition holds", result.stdout)

    def test_property_owner_evidence_cannot_survive_semantic_drift(self):
        original = (
            "---\ntype: concept\nauthoring_status: reviewed\n"
            "last_reviewed: 2026-08-20\n---\n"
            "# P\n\nOriginal reviewed content.\n")
        files = base_files()
        files["Domain/Page.md"] = original
        root = self.build(files)
        self.compose(root)
        fingerprint = self.semantic_fingerprint(
            root, "Domain/Page.md", original)
        ledger = {
            "schema_version": 1,
            "pages": [{
                "path": "Domain/Page.md",
                "coverage_disposition": "required",
                "authoring_status": "reviewed",
                "property_state": {
                    "last_reviewed": {
                        "value": "2026-08-20",
                        "evidence_receipt": "review-receipt-1",
                        "content_fingerprint": fingerprint,
                    },
                },
            }],
        }
        ledger_path = root / ".cambium/state/coverage_ledger.yaml"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        import kblib
        ledger_path.write_text(kblib.canonical_yaml(ledger),
                               encoding="utf-8")
        (root / "Domain/Page.md").write_text(
            original.replace("Original reviewed content.",
                             "Content changed after review."),
            encoding="utf-8")

        result = self.check(root)

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("binds stale semantic content", result.stdout)

    # ---- section roles (K07/02, K09/04) ----

    def sources_files(self, page_body, contract=CONTRACT_DEFAULTS):
        files = base_files(contract)
        files["Domain/Deep.md"] = page_body
        return files

    DEEP_HEADER = ("---\ntype: concept\nauthoring_status: drafted\n"
                   "depth: core\n---\n# Deep\n\n")

    def test_core_page_without_sources_role_is_reported(self):
        root = self.build(self.sources_files(self.DEEP_HEADER + "Body.\n"))
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("owes the sources role", result.stdout)

    def test_sources_heading_satisfies_the_role(self):
        root = self.build(self.sources_files(
            self.DEEP_HEADER + "## Sources\n\n- [Doc](https://e.org)\n"))
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_evidence_binding_satisfies_the_role(self):
        files = self.sources_files(
            "---\ntype: concept\nauthoring_status: drafted\ndepth: core\n"
            "evidence_sources:\n  - \"Domain/Source\"\n---\n# Deep\n")
        files["Domain/Source.md"] = (
            "---\ntype: source-note\nauthoring_status: drafted\n"
            "source_url: \"https://example.org/doc\"\n---\n# S\n"
            "\n## Sources\n\n- x\n")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_duplicate_sources_role_headings_are_reported(self):
        root = self.build(self.sources_files(
            self.DEEP_HEADER + "## Sources\n\n- a\n\n## Sources\n\n- b\n"))
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("more than one sources-role heading", result.stdout)

    def test_missing_related_is_never_reported(self):
        root = self.build(self.sources_files(
            self.DEEP_HEADER + "## Sources\n\n- a\n"))
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Related", result.stdout)

    def test_shallow_page_owes_no_sources_role(self):
        root = self.build(base_files())  # Domain/Page.md has no depth field
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    # ---- fail-closed scope ----

    def test_missing_contract_fails_closed(self):
        root = self.build(base_files())
        result = self.check(root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("cannot parse the compiled contract", result.stdout)

    def test_zero_page_scan_fails_closed(self):
        files = base_files()
        del files["Domain/Page.md"]
        files["Domain/.keep"] = ""
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("zero-page scan", result.stdout)


if __name__ == "__main__":
    unittest.main()
