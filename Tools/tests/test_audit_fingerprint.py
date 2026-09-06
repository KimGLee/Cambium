"""Independent invariance tests for the K12/07 artifact fingerprint."""

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.audit_fingerprint as audit_fingerprint  # noqa: E402
import Tools.execution.audit.audit_receipt_contract as receipt_contract  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402


BASE = """---
type: knowledge
priority: P1
tier: M
coverage_disposition: required
lifecycle: active
prerequisites:
  - Topics/Owner.md
authoring_status: draft
custom_field: ignored-one
---
# Example

Body bytes.\n"""


class PageArtifactFingerprintTests(unittest.TestCase):

    def test_sources_projection_uses_exact_section_not_code_or_other_prose(self):
        sources = "## Sources\n\n- [Primary](https://example.test)\n"
        prefix = "# Page\n\n```md\n## Sources\nnot authoritative\n```\n"
        expected = kblib.sha256_bytes(sources)
        self.assertEqual(expected, audit_fingerprint.sources_sha256(
            prefix + sources + "## Next\nUnrelated.\n"))
        self.assertEqual(expected, audit_fingerprint.sources_sha256(
            prefix.replace("not authoritative", "changed example") +
            sources + "## Next\nDifferent prose.\n"))
        self.assertNotEqual(expected, audit_fingerprint.sources_sha256(
            prefix + sources.replace("Primary", "Changed primary")))
        self.assertEqual(kblib.sha256_bytes(""),
                         audit_fingerprint.sources_sha256(prefix))

    def fingerprint(self, text=BASE, path="Topics/Example.md"):
        return audit_fingerprint.page_artifact_fingerprint(path, text)

    def test_semantic_fields_come_from_the_contract_not_a_tool_allowlist(self):
        contract = receipt_contract.load_contract(REPOSITORY)
        fields = contract["page_artifact_fingerprint"]["included_frontmatter_fields"]
        fields.reverse()
        self.assertEqual(self.fingerprint(),
            audit_fingerprint.page_artifact_fingerprint("Topics/Example.md", BASE,
                                                       contract=contract))
        fields.append("custom_field")
        def changed(text):
            return audit_fingerprint.page_artifact_fingerprint(
                "Topics/Example.md", text, contract=contract)
        self.assertNotEqual(changed(BASE), changed(BASE.replace("ignored-one", "new-value")))
        self.assertEqual(self.fingerprint(), self.fingerprint(BASE.replace("ignored-one", "new-value")))

    def test_matches_independent_canonical_material_oracle(self):
        expected_material = {
            "protocol_id": "cambium-page-artifact-v1",
            "path": "Topics/Example.md",
            "frontmatter": {
                "type": "knowledge",
                "priority": "P1",
                "tier": "M",
                "coverage_disposition": "required",
                "lifecycle": "active",
                "prerequisites": ["Topics/Owner.md"],
            },
            "body": "# Example\n\nBody bytes.\n",
        }
        expected = kblib.sha256_bytes(
            kblib.canonical_json_bytes(expected_material))
        self.assertEqual(self.fingerprint(), expected)

    def test_every_included_frontmatter_field_changes_fingerprint(self):
        mutations = {
            "type": BASE.replace("type: knowledge", "type: source"),
            "priority": BASE.replace("priority: P1", "priority: P2"),
            "tier": BASE.replace("tier: M", "tier: L"),
            "coverage_disposition": BASE.replace(
                "coverage_disposition: required",
                "coverage_disposition: supporting"),
            "lifecycle": BASE.replace(
                "lifecycle: active", "lifecycle: deprecated"),
            "prerequisites": BASE.replace(
                "Topics/Owner.md", "Topics/Other.md"),
        }
        baseline = self.fingerprint()
        for field, text in mutations.items():
            with self.subTest(field=field):
                self.assertNotEqual(self.fingerprint(text), baseline)

    def test_excluded_fields_spelling_and_mapping_order_do_not_change_hash(self):
        equivalent = """---
custom_field: ignored-two
prerequisites: [Topics/Owner.md]
lifecycle: "active"
coverage_disposition: "required"
tier: "M"
priority: "P1"
authoring_status: published
type: "knowledge"
...
# Example

Body bytes.\n"""
        self.assertEqual(self.fingerprint(equivalent), self.fingerprint())

    def test_missing_and_explicit_null_are_different_semantic_values(self):
        without_priority = BASE.replace("priority: P1\n", "")
        null_priority = BASE.replace("priority: P1", "priority: null")
        self.assertNotEqual(
            self.fingerprint(without_priority), self.fingerprint(null_priority))

    def test_body_and_canonical_path_are_each_bound(self):
        self.assertNotEqual(
            self.fingerprint(BASE.replace("Body bytes.", "Changed body.")),
            self.fingerprint())
        self.assertNotEqual(
            self.fingerprint(path="Topics/Renamed.md"), self.fingerprint())

    def test_body_only_page_binds_all_exact_bytes(self):
        left = self.fingerprint("# No frontmatter\nBody\n")
        right = self.fingerprint("# No frontmatter\nBody \n")
        self.assertNotEqual(left, right)

    def test_incomplete_or_non_mapping_frontmatter_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no closing marker"):
            self.fingerprint("---\ntype: knowledge\n# Body\n")
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            self.fingerprint("---\n- knowledge\n---\n# Body\n")

    def test_noncanonical_paths_fail_closed(self):
        for path in ("/Topics/A.md", "Topics\\A.md", "Topics/../A.md",
                     " Topics/A.md", "Topics//A.md"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.fingerprint(path=path)


class PageSetArtifactFingerprintTests(unittest.TestCase):

    def test_input_order_does_not_change_page_set_fingerprint(self):
        first = [
            ("Topics/B.md", "# B\n"),
            ("Topics/A.md", "# A\n"),
        ]
        second = list(reversed(first))
        self.assertEqual(
            audit_fingerprint.page_set_artifact_fingerprint(first),
            audit_fingerprint.page_set_artifact_fingerprint(second))

    def test_matches_independent_sorted_member_oracle(self):
        pages = [
            ("Topics/B.md", "# B\n"),
            ("Topics/A.md", "# A\n"),
        ]
        members = [{
            "path": path,
            "artifact_fingerprint": kblib.sha256_bytes(
                kblib.canonical_json_bytes({
                    "protocol_id": "cambium-page-artifact-v1",
                    "path": path,
                    "frontmatter": {},
                    "body": text,
                })),
        } for path, text in sorted(pages)]
        expected = kblib.sha256_bytes(kblib.canonical_json_bytes({
            "protocol_id": "cambium-page-artifact-set-v1",
            "members": members,
        }))
        self.assertEqual(
            audit_fingerprint.page_set_artifact_fingerprint(pages), expected)

    def test_page_set_rejects_duplicate_paths_and_bad_members(self):
        with self.assertRaisesRegex(ValueError, "repeat"):
            audit_fingerprint.page_set_artifact_fingerprint([
                ("Topics/A.md", "# A\n"),
                ("Topics/A.md", "# Other A\n"),
            ])
        with self.assertRaisesRegex(ValueError, "pair"):
            audit_fingerprint.page_set_artifact_fingerprint([
                ("Topics/A.md",),
            ])


if __name__ == "__main__":
    unittest.main()
