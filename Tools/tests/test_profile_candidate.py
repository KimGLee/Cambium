"""Candidate edit contract: pure field operations and one local write seam.

No Task, Queue, Batch, or Receipt lifecycle is a fixture for candidate edits.
Governance acceptance remains tested at the Profile contract owner.
"""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from Tools.governance.profile import profile_candidate, profile_codec, profile_contract
from Tools.platform.common import kblib


class CandidateEditUnitTests(unittest.TestCase):
    def setUp(self):
        self.document = {"profile_id": "test", "schema_version": 1, "slots": {
            "records": [{"role_id": "first", "actor": "One"},
                        {"role_id": "second", "actor": "Two"}]}}

    def test_reads_stable_identity_independently_of_order(self):
        selector = ["slots", "records", {"role_id": "second"}, "actor"]
        self.assertEqual("Two", profile_candidate.read_value(self.document, selector))
        self.document["slots"]["records"].reverse()
        self.assertEqual("Two", profile_candidate.read_value(self.document, selector))

    def test_read_returns_defensive_data(self):
        value = profile_candidate.read_value(self.document, ["slots", "records"])
        value.clear()
        self.assertEqual(2, len(self.document["slots"]["records"]))

    def test_set_append_remove_leave_input_unchanged(self):
        after = profile_candidate.apply_edits(self.document, [
            {"op": "set", "path": ["slots", "records", {"role_id": "second"}, "actor"], "value": "New"},
            {"op": "append", "path": ["slots", "records"], "value": {"role_id": "third", "actor": "Three"}},
            {"op": "remove", "path": ["slots", "records", {"role_id": "first"}]},
        ])
        self.assertEqual([{"role_id": "second", "actor": "New"},
                          {"role_id": "third", "actor": "Three"}], after["slots"]["records"])
        self.assertEqual("One", self.document["slots"]["records"][0]["actor"])

    def test_ambiguous_missing_and_positional_selectors_are_rejected(self):
        for selector in (["slots", "absent"], ["slots", "records", 0],
                         ["slots", "records", {"role_id": "absent"}],
                         ["slots", "records", {}]):
            with self.subTest(selector=selector), self.assertRaises(profile_candidate.CandidateError):
                profile_candidate.read_value(self.document, selector)
        self.document["slots"]["records"].append({"role_id": "second", "actor": "Duplicate"})
        with self.assertRaises(profile_candidate.CandidateError):
            profile_candidate.read_value(self.document, ["slots", "records", {"role_id": "second"}])

    def test_identity_unknown_operations_and_implicit_parents_are_rejected(self):
        for edit in (
            {"op": "set", "path": ["profile_id"], "value": "other"},
            {"op": "merge", "path": ["slots"], "value": {}},
            {"op": "set", "path": ["slots", "absent", "policy"], "value": "invented"},
            {"op": "remove", "path": ["slots"], "value": {}},
            {"op": "set", "path": [], "value": {}},
        ):
            with self.subTest(edit=edit), self.assertRaises(profile_candidate.CandidateError):
                profile_candidate.apply_edits(self.document, [edit])


class CandidateEditIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        repository = Path(__file__).resolve().parents[2]
        # Only the draft's declared machine inputs, not an entire repository.
        for relative, snapshot in profile_contract.profile_draft_inputs(repository).items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(snapshot.data)
        self.manifest = self.root / "profiles/candidate/profile.toml"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_bytes(profile_codec.dumps_profile({
            "schema_version": 1, "profile_id": "candidate", "slots": {}}))
        self.edits = [{"op": "set", "path": ["slots", "profile-scope"], "value": {
            "goal": {"statement": "Organize confirmed knowledge.", "readers": ["Maintainer"]}}}]

    def snapshot(self):
        return kblib.repository_tree_snapshot(self.root, "profiles/candidate").sha256

    def test_preview_then_publish_one_partial_answer_without_adoption(self):
        before = self.manifest.read_bytes()
        identity = self.snapshot()
        preview = profile_candidate.edit_candidate(self.root, "candidate", self.edits, identity)
        self.assertEqual("dry-run", preview["result"])
        self.assertEqual(before, self.manifest.read_bytes())
        self.assertFalse(preview["ready"])
        result = profile_candidate.edit_candidate(self.root, "candidate", self.edits, identity, apply=True)
        self.assertEqual("updated", result["result"])
        self.assertTrue(result["resulting_state_verified"])
        self.assertEqual(preview["snapshot_after"], self.snapshot())
        self.assertFalse(result["adoption_performed"])
        self.assertFalse((self.root / ".cambium").exists())
        with self.assertRaisesRegex(profile_candidate.CandidateError, "snapshot changed"):
            profile_candidate.edit_candidate(self.root, "candidate", self.edits, identity, apply=True)

    def test_invalid_afterimage_and_duplicate_input_never_write(self):
        before = self.manifest.read_bytes()
        invalid = [{"op": "set", "path": ["slots", "invented-authority"], "value": True}]
        with self.assertRaises(profile_candidate.CandidateError):
            profile_candidate.edit_candidate(self.root, "candidate", invalid, self.snapshot(), apply=True)
        edits = self.root / "edits.json"
        edits.write_text('[{"op":"set","op":"remove","path":["slots"]}]')
        with redirect_stdout(io.StringIO()) as output:
            code = profile_candidate.main([str(self.root), "--profile-id", "candidate", "--mode", "edit",
                "--edits", str(edits), "--expected-snapshot-sha256", self.snapshot(), "--apply", "--json"])
        self.assertEqual(1, code)
        self.assertIn("duplicate JSON", json.loads(output.getvalue())["error"])
        self.assertEqual(before, self.manifest.read_bytes())

    def test_failure_after_publication_is_uncertain_not_a_no_write_refusal(self):
        original = kblib.atomic_write_text
        def write_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("post-publication persistence observation failed")
        with mock.patch.object(kblib, "atomic_write_text", side_effect=write_then_fail):
            report = profile_candidate.edit_candidate(self.root, "candidate", self.edits, self.snapshot(), apply=True)
        self.assertEqual("uncertain", report["result"])
        self.assertIsNone(report["changed"])
        self.assertFalse(report["resulting_state_verified"])
        self.assertIn("profile-scope", profile_codec.loads_profile(self.manifest.read_bytes())["slots"])


if __name__ == "__main__":
    unittest.main()
