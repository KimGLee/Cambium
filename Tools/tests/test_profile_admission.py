"""Shared admission tests for Profile-dependent Gate consumers."""

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / "Tools"
sys.path.insert(0, str(TOOLS))

import profile_admission
import standards_state

from Tools.tests.profile_fixture import (
    FIXTURE_UPSTREAM_REVISION,
    install_loadable_profile,
)


class ProfileAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.profile = install_loadable_profile(self.root)

    def install_active_state(self):
        target = self.root / standards_state.STATE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(standards_state.canonical_text({
            "schema_version": 1,
            "state_revision": 1,
            "standards_version": FIXTURE_UPSTREAM_REVISION,
            "status": "approved",
            "effective_date": "2026-08-11",
            "selected_profile_manifest": "profiles/test-profile/profile.md",
            "latest_adoption_receipt": "audit-profile-admission-fixture",
            "upstream_source_ref": "fixture://cambium",
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
        }), encoding="utf-8")
        return target

    def test_one_evaluation_supplies_all_typed_slot_bytes(self):
        real = profile_admission.check_profile.evaluate_profile_load
        with mock.patch.object(
                profile_admission.check_profile, "evaluate_profile_load",
                wraps=real) as evaluate:
            admission, errors = profile_admission.admit_profile(
                self.root, self.profile)
        self.assertEqual([], errors)
        self.assertIsNotNone(admission)
        self.assertEqual(1, evaluate.call_count)
        self.assertEqual(14, len(admission.slot_paths))
        self.assertIn("# Synthetic Slot Fixture",
                      admission.slot_text("Profile Scope"))
        self.assertEqual([], profile_admission.currency_errors(admission))

    def test_unrelated_unloadable_slot_refuses_admission(self):
        manifest = self.profile / "profile.md"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "- `Priority Rubric`: `slots.md`",
                "- `Priority Rubric`: `broken.md`"),
            encoding="utf-8")
        (self.profile / "broken.md").write_text(
            "TODO(profile)\n", encoding="utf-8")
        admission, errors = profile_admission.admit_profile(
            self.root, self.profile)
        self.assertIsNone(admission)
        self.assertIn("TODO(profile)", "\n".join(errors))

    def test_consumer_reads_authorized_slot_bytes_after_live_tree_changes(self):
        scope = self.profile / "slots.md"
        original = scope.read_text(encoding="utf-8")
        real = profile_admission.check_profile.evaluate_profile_load

        def mutate_after_evaluation(*args, **kwargs):
            evaluation = real(*args, **kwargs)
            scope.write_text("# Transient revision B\n", encoding="utf-8")
            return evaluation

        with mock.patch.object(
                profile_admission.check_profile, "evaluate_profile_load",
                side_effect=mutate_after_evaluation):
            admission, errors = profile_admission.admit_profile(
                self.root, self.profile)
        self.assertEqual([], errors)
        self.assertEqual(original, admission.slot_text("Profile Scope"))
        self.assertIn("selected Profile changed after profile-load",
                      "\n".join(profile_admission.currency_errors(
                          admission)))

    def test_active_state_change_during_evaluation_is_rejected(self):
        state = self.install_active_state()
        real = profile_admission.check_profile.evaluate_profile_load

        def mutate_after_evaluation(*args, **kwargs):
            evaluation = real(*args, **kwargs)
            state.write_text(
                state.read_text(encoding="utf-8").replace(
                    "status: approved", "status: draft"),
                encoding="utf-8")
            return evaluation

        with mock.patch.object(
                profile_admission.check_profile, "evaluate_profile_load",
                side_effect=mutate_after_evaluation):
            admission, errors = profile_admission.admit_profile(self.root)
        self.assertIsNone(admission)
        self.assertIn("active Standards state changed while profile-load",
                      "\n".join(errors))

    def test_active_state_change_invalidates_admitted_selection(self):
        state = self.install_active_state()
        admission, errors = profile_admission.admit_profile(self.root)
        self.assertEqual([], errors)
        state.write_text(
            state.read_text(encoding="utf-8").replace(
                "status: approved", "status: draft"),
            encoding="utf-8")
        self.assertIn("active Standards state changed",
                      "\n".join(profile_admission.currency_errors(
                          admission)))

    def test_active_state_hard_link_is_not_an_admissible_selection_source(self):
        state = self.install_active_state()
        os.link(state, self.root / "active-state-alias.md")

        admission, errors = profile_admission.admit_profile(self.root)

        self.assertIsNone(admission)
        self.assertIn("unsafe, absent, or unreadable",
                      "\n".join(errors))

    def test_canonical_profile_load_input_change_invalidates_admission(self):
        admission, errors = profile_admission.admit_profile(
            self.root, self.profile)
        self.assertEqual([], errors)
        interface = (
            self.root / profile_admission.check_profile.DEFAULT_INTERFACE)
        interface.write_text(
            interface.read_text(encoding="utf-8") + "\n<!-- revision B -->\n",
            encoding="utf-8")

        self.assertIn(
            "canonical profile-load inputs changed after admission",
            "\n".join(profile_admission.currency_errors(admission)),
        )


if __name__ == "__main__":
    unittest.main()
