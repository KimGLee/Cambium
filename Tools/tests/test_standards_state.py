import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import standards_state


class StandardsStateTests(unittest.TestCase):
    def value(self):
        return {
            "schema_version": 1,
            "state_revision": 3,
            "standards_version": "3.12.0",
            "status": "approved",
            "effective_date": "2026-08-21",
            "selected_profile_manifest": "profiles/agent-atlas/profile.md",
            "latest_adoption_receipt": "audit-adopt_standards-example-0001",
            "upstream_source_ref": "https://github.com/KimGLee/Cambium",
            "upstream_revision_id": "abc123",
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
        self.assertEqual(view["standards_version"], "3.12.0")

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
        after = standards_state.next_state(
            before, standards_version="3.13.0",
            effective_date="2026-08-22",
            selected_profile_manifest="profiles/agent-atlas/profile.md",
            latest_adoption_receipt="audit-next-0001",
            upstream_source_ref="upstream", upstream_revision_id="def456")
        self.assertEqual(after["state_revision"], 4)
        self.assertNotIn("change_summary", after)
        self.assertNotIn("history", after)


if __name__ == "__main__":
    unittest.main()
