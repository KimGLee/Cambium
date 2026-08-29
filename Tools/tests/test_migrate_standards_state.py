import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
FIXTURE = TOOLS / "tests" / "fixtures" / "runtime_state" / "valid"
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import kblib
import migrate_standards_state
import standards_state
from profile_fixture import FIXTURE_UPSTREAM_REVISION, install_loadable_profile


class MigrateStandardsStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        install_loadable_profile(self.root)
        (self.root / standards_state.STATE_PATH).unlink()
        receipt = {
            "receipt_id": "audit-adopt-3.0.0",
            "tool": "adopt_standards",
            "tool_version": "1.6.0",
            "transaction_phase": "commit",
            "result": "pass",
            "standards_version_after": FIXTURE_UPSTREAM_REVISION,
            "checked_at": "2026-08-01T12:00:00Z",
            "upstream_source_ref": "https://example.test/cambium.git",
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
        }
        path = self.root / migrate_standards_state.HISTORY_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_projects_live_identity_without_rewriting_history(self):
        history = self.root / migrate_standards_state.HISTORY_PATH
        before = history.read_bytes()

        self.assertEqual(
            0, migrate_standards_state.main([str(self.root), "--apply"]))

        state = kblib.load_yaml_file(
            self.root / standards_state.STATE_PATH)
        self.assertEqual(FIXTURE_UPSTREAM_REVISION,
                         state["standards_version"])
        self.assertEqual("profiles/test-profile/profile.md",
                         state["selected_profile_manifest"])
        self.assertEqual("audit-adopt-3.0.0",
                         state["latest_adoption_receipt"])
        self.assertEqual("2026-08-01", state["effective_date"])
        self.assertEqual(before, history.read_bytes())

    def test_ledgers_must_agree(self):
        queue_path = self.root / migrate_standards_state.QUEUE_PATH
        queue = kblib.load_yaml_file(queue_path)
        queue["standards_version"] = "9.9.9"
        queue_path.write_text(kblib.canonical_yaml(queue), encoding="utf-8")

        self.assertEqual(1, migrate_standards_state.main([str(self.root)]))
        self.assertFalse((self.root / standards_state.STATE_PATH).exists())

    def test_live_version_requires_committed_history(self):
        (self.root / migrate_standards_state.HISTORY_PATH).write_text(
            "", encoding="utf-8")

        self.assertEqual(1, migrate_standards_state.main([str(self.root)]))
        self.assertFalse((self.root / standards_state.STATE_PATH).exists())


if __name__ == "__main__":
    unittest.main()
