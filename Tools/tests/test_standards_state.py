import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))
import Tools.governance.standards.standards_state as standards_state
from Tools.tests.support.profile_fixture import FIXTURE_UPSTREAM_REVISION


class StandardsStateTests(unittest.TestCase):
    REVISION = FIXTURE_UPSTREAM_REVISION
    OTHER_REVISION = "fedcba9876543210fedcba9876543210fedcba98"

    def value(self):
        return {
            "schema_version": standards_state.SCHEMA_VERSION,
            "state_revision": 3,
            "upstream_revision_id": self.REVISION,
            "status": "approved",
            "effective_date": "2026-08-21",
            "selected_profile_manifest": "profiles/agent-atlas/profile.md",
            "latest_adoption_receipt": "audit-adopt_standards-example-0001",
            "upstream_source_ref": "https://github.com/KimGLee/Cambium",
        }

    def test_round_trip_and_snapshot(self):
        value = self.value()
        text = standards_state.canonical_text(value)
        parsed, errors = standards_state.parse(text)
        self.assertEqual(errors, [])
        self.assertEqual(parsed, value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / standards_state.STATE_PATH
            path.parent.mkdir(parents=True)
            path.write_text(text, encoding="utf-8")
            state, view, errors = standards_state.snapshot(root)
        self.assertEqual(errors, [])
        self.assertEqual(state, value)
        self.assertEqual(view["active_standards_path"], standards_state.STATE_PATH)
        self.assertEqual(view["upstream_revision_id"], self.REVISION)

    def test_closed_and_no_markdown_fallback(self):
        value = self.value()
        value["history"] = []
        self.assertIn("unsupported field", "; ".join(
            standards_state.state_errors(value)))
        with tempfile.TemporaryDirectory() as directory:
            state, view, errors = standards_state.snapshot(directory)
        self.assertIsNone(state)
        self.assertIsNone(view)
        self.assertIn("absent", "; ".join(errors))

    def test_selected_profile_manifest_uses_the_shared_selectable_envelope(self):
        for manifest in (
                "profiles/a/b/profile.md",
                "profiles/_template/profile.md",
                "profiles/examples/demo/profile.md"):
            with self.subTest(manifest=manifest):
                value = self.value()
                value["selected_profile_manifest"] = manifest
                self.assertIn(
                    "selected_profile_manifest is invalid",
                    "; ".join(standards_state.state_errors(value)),
                )

    def test_next_state_advances_only_current_identity(self):
        before = self.value()
        revision = self.OTHER_REVISION
        after = standards_state.next_state(
            before,
            effective_date="2026-08-22",
            selected_profile_manifest="profiles/agent-atlas/profile.md",
            latest_adoption_receipt="audit-next-0001",
            upstream_source_ref="upstream", upstream_revision_id=revision)
        self.assertEqual(after["state_revision"], 4)
        self.assertEqual(revision, after["upstream_revision_id"])
        self.assertNotIn("change_summary", after)
        self.assertNotIn("history", after)

    def test_upstream_commit_is_the_only_standards_identity(self):
        for mutation in (
                {"upstream_revision_id": "abc123"},
                {"upstream_source_ref": None},
                {"upstream_revision_id": None},
                {"release_label": "X.Y.Z"}):
            with self.subTest(mutation=mutation):
                value = self.value()
                value.update(mutation)
                self.assertTrue(standards_state.state_errors(value))


if __name__ == "__main__":
    unittest.main()
