"""Synthetic-fixture tests for check_boundary_contract.py and
render_boundary_projection.py (gate: boundary-contract, advisory).

Rule owner under test: kernel/K08 Metadata and Status/09 Page Boundary
Contract.md through the shared shape and rendering contract in
kblib.validate_boundary_shape / kblib.render_boundary_projection_lines
plus the cross-page checker and the projection renderer. Each negative
test carries exactly one defect.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from Tools.tests.profile_fixture import install_loadable_profile

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import runtime_paths

COMPOSER = TOOLS / "compose_page_contract.py"
CHECKER = TOOLS / "check_boundary_contract.py"
RENDERER = TOOLS / "render_boundary_projection.py"

APPLICABILITY_BASE = """schema_version: 1
fields:
  type:
    mode: required
    shape: nonempty-string
  authoring_status:
    mode: required
    shape: nonempty-string
  boundary:
    mode: optional
    shape: delegated
    delegate: boundary-contract
"""

RELATIONSHIP_BASE = """schema_version: 1
relationships:
  evidence_sources:
    mode: optional
    direction: evidence-input
    target:
      - source-note
    shape: list-of-paths
"""

SOURCES_ROLE_BASE = """schema_version: 1
role: sources
default_titles:
  - Sources
applicability:
  condition:
    any:
      - field: type
        in:
          - never-used-type
binding_satisfies:
  fields:
    - evidence_sources
  directions:
    - evidence-input
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

CONTRACT_LABELED = CONTRACT_DEFAULTS + """boundary_projection:
  labels:
    owns: "Owns（职责）"
    excludes: "Not owned here（不归本页）"
"""

ALPHA = """---
type: concept
authoring_status: drafted
boundary:
  owns:
    - alpha-core
    - alpha-group:
        - alpha-sub-one
        - alpha-sub-two
  excludes:
    - concern: beta-core
      owner: "Domain/Beta"
  goals:
    - "Keep alpha coherent."
  non_goals:
    - "Own beta."
---
# Alpha

## Definition

Alpha prose.

<!-- boundary-projection:begin -->
<!-- boundary-projection:end -->
"""

BETA = """---
type: concept
authoring_status: drafted
boundary:
  owns:
    - beta-core
---
# Beta
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
        "Domain/Alpha.md": ALPHA,
        "Domain/Beta.md": BETA,
    }


class BoundaryContractTests(unittest.TestCase):
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
             "--output", str(root / runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH)],
            text=True, capture_output=True, check=False)
        self.assertEqual(expect, result.returncode,
                         result.stdout + result.stderr)
        return result

    def check(self, root, *args):
        return subprocess.run(
            [sys.executable, str(CHECKER), str(root),
             "--profile", "profiles/test-profile",
             "--contract",
             str(root / runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH), *args],
            text=True, capture_output=True, check=False)

    def render(self, root, *args):
        return subprocess.run(
            [sys.executable, str(RENDERER), str(root),
             "--profile", "profiles/test-profile",
             "--contract",
             str(root / runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH), *args],
            text=True, capture_output=True, check=False)

    def ready(self, files=None, contract=CONTRACT_DEFAULTS):
        """Build, compose, and fill the projection blocks."""
        root = self.build(files or base_files(contract))
        self.compose(root)
        result = self.render(root, "--apply")
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        return root

    # ---- the healthy pair ----

    def test_valid_blocks_pass(self):
        root = self.ready()
        result = self.check(root)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
        self.assertIn("2 with a boundary block", result.stdout)

    def test_unrelated_unloadable_slot_blocks_checker_and_renderer(self):
        root = self.ready()
        manifest = root / "profiles/test-profile/profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "- `Priority Rubric`: `slots.md`",
                "- `Priority Rubric`: `broken-priority.md`"),
            encoding="utf-8")
        (manifest.parent / "broken-priority.md").write_text(
            "TODO(profile)\n", encoding="utf-8")
        checked = self.check(root)
        rendered = self.render(root, "--check")
        self.assertEqual(1, checked.returncode, checked.stdout)
        self.assertEqual(1, rendered.returncode, rendered.stdout)
        self.assertIn("profile-load", checked.stdout)
        self.assertIn("profile-load", rendered.stdout)

    def test_profile_change_rejects_prechange_contract_for_both_consumers(self):
        """Boundary checks and rendering must not consume Profile A's IR."""
        root = self.ready()
        metadata = root / "profiles/test-profile/metadata-contract.yaml"
        metadata.write_text(CONTRACT_LABELED, encoding="utf-8")

        checked = self.check(root)
        rendered = self.render(root, "--check")

        self.assertEqual(1, checked.returncode, checked.stdout)
        self.assertEqual(1, rendered.returncode, rendered.stdout)
        self.assertIn("does not match the selected Profile", checked.stdout)
        self.assertIn("does not match the selected Profile", rendered.stdout)

    def test_owner_reference_resolves_without_md_suffix(self):
        # ALPHA's excludes names "Domain/Beta" without .md; the healthy
        # pair passing proves suffixless resolution.
        root = self.ready()
        self.assertEqual(self.check(root).returncode, 0)

    # ---- B1 shape ----

    def test_bad_slug_is_a_candidate(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace("- alpha-core",
                                                 "- Alpha_Core")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("kebab-case", result.stdout)

    def test_empty_owns_is_a_candidate(self):
        files = base_files()
        files["Domain/Beta.md"] = BETA.replace(
            "boundary:\n  owns:\n    - beta-core", "boundary:\n  owns: []")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("owns must be a nonempty list", result.stdout)

    def test_exclude_entry_missing_owner_is_a_candidate(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace(
            "      owner: \"Domain/Beta\"\n", "")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("exactly `concern` and `owner`", result.stdout)

    def test_empty_goal_string_is_a_candidate(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace(
            "- \"Keep alpha coherent.\"", "- \"\"")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("goals", result.stdout)

    # ---- B2 self-consistency ----

    def test_owned_and_excluded_slug_is_a_candidate(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace("- alpha-core",
                                                 "- beta-core")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("both in owns and as an excluded concern",
                      result.stdout)

    def test_self_owner_is_a_candidate(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace(
            "owner: \"Domain/Beta\"", "owner: \"Domain/Alpha\"")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("declaring page itself", result.stdout)

    # ---- B3 resolvability ----

    def test_unresolvable_owner_is_a_candidate(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace(
            "owner: \"Domain/Beta\"", "owner: \"Domain/Missing\"")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("does not resolve inside the vault", result.stdout)

    # ---- B4 reciprocity ----

    def test_owner_without_claim_is_a_violation(self):
        files = base_files()
        files["Domain/Beta.md"] = BETA.replace("- beta-core",
                                               "- something-else")
        root = self.build(files)
        self.compose(root)
        result = self.check(root, "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("does not claim concern", result.stdout)

    def test_owner_without_block_stays_a_candidate_under_strict(self):
        files = base_files()
        files["Domain/Beta.md"] = ("---\ntype: concept\n"
                                   "authoring_status: drafted\n---\n# B\n")
        files["Domain/Alpha.md"] = ALPHA.replace(
            "<!-- boundary-projection:begin -->\n"
            "<!-- boundary-projection:end -->\n", "")
        root = self.build(files)
        self.compose(root)
        result = self.check(root, "--strict")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("migration-tolerated", result.stdout)

    def test_reciprocity_accepts_a_sub_slug_claim(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace("concern: beta-core",
                                                 "concern: beta-sub")
        files["Domain/Beta.md"] = BETA.replace(
            "    - beta-core",
            "    - beta-core:\n        - beta-sub")
        root = self.ready(files)
        result = self.check(root)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)

    # ---- B5 uniqueness ----

    def test_two_owners_of_one_concern_is_a_candidate(self):
        files = base_files()
        files["Domain/Beta.md"] = BETA.replace(
            "    - beta-core", "    - beta-core\n    - alpha-core")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("owned by 2 pages", result.stdout)
        self.assertIn("Domain/Alpha.md", result.stdout)
        self.assertIn("Domain/Beta.md", result.stdout)

    # ---- B6 projection ----

    def test_stale_projection_is_a_candidate_and_strict_failure(self):
        root = self.ready()
        alpha = root / "Domain/Alpha.md"
        alpha.write_text(alpha.read_text(encoding="utf-8").replace(
            "`alpha-core`", "`hand-edited`"), encoding="utf-8")
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("stale", result.stdout)
        self.assertEqual(self.check(root, "--strict").returncode, 1)

    def test_orphaned_markers_are_a_candidate(self):
        files = base_files()
        files["Domain/Beta.md"] = (
            "---\ntype: concept\nauthoring_status: drafted\n---\n# B\n\n"
            "<!-- boundary-projection:begin -->\n"
            "<!-- boundary-projection:end -->\n")
        files["Domain/Alpha.md"] = BETA.replace("# Beta", "# Alpha")
        files["Domain/Alpha.md"] = files["Domain/Alpha.md"].replace(
            "beta-core", "alpha-core")
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("orphaned", result.stdout)

    def test_duplicate_begin_marker_is_a_candidate(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace(
            "<!-- boundary-projection:begin -->",
            "<!-- boundary-projection:begin -->\n"
            "<!-- boundary-projection:begin -->", 1)
        root = self.build(files)
        self.compose(root)
        result = self.check(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("2 begin", result.stdout)

    # ---- fail-closed inputs ----

    def test_missing_contract_fails(self):
        root = self.build(base_files())
        result = self.check(root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("compose it", result.stdout)

    def test_zero_page_scope_fails(self):
        root = self.build(base_files())
        self.compose(root)
        (root / "Empty").mkdir()
        result = self.check(root, "--scope", "Empty")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("effective scan set is empty", result.stdout)

    # ---- renderer ----

    def test_renderer_is_idempotent(self):
        root = self.ready()
        before = (root / "Domain/Alpha.md").read_bytes()
        result = self.render(root, "--apply")
        self.assertEqual(result.returncode, 0)
        self.assertIn("written=0", result.stdout)
        self.assertEqual(before, (root / "Domain/Alpha.md").read_bytes())

    def test_renderer_check_reports_stale_then_current(self):
        root = self.build(base_files())
        self.compose(root)
        result = self.render(root, "--check")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.render(root, "--apply")
        self.assertEqual(self.render(root, "--check").returncode, 0)

    def test_renderer_skips_pages_without_markers(self):
        root = self.ready()
        result = self.render(root, "--check")
        self.assertIn("no_markers=1", result.stdout)  # Beta

    def test_renderer_rejects_malformed_markers(self):
        files = base_files()
        files["Domain/Alpha.md"] = ALPHA.replace(
            "<!-- boundary-projection:end -->", "", 1)
        root = self.build(files)
        self.compose(root)
        result = self.render(root, "--check")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("malformed", result.stdout)

    def test_profile_labels_override_the_rendered_block(self):
        root = self.ready(contract=CONTRACT_LABELED)
        text = (root / "Domain/Alpha.md").read_text(encoding="utf-8")
        self.assertIn("Owns（职责）", text)
        self.assertIn("Not owned here（不归本页）", text)
        self.assertIn("**Goals**", text)  # un-overridden kernel default
        self.assertEqual(self.check(root).returncode, 0)

    def test_projection_content_lists_subs_and_owner_link(self):
        root = self.ready()
        text = (root / "Domain/Alpha.md").read_text(encoding="utf-8")
        self.assertIn("`alpha-group` (`alpha-sub-one`, `alpha-sub-two`)",
                      text)
        self.assertIn("[[Domain/Beta\\|Beta]]", text)


if __name__ == "__main__":
    unittest.main()
