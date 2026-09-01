"""Profile admission adapter, immutable snapshot, and selection tests.

``check_profile`` owns Profile completeness and semantic authorization;
``profile_contract`` owns the typed dependency graph; repository safety tests
own symlink and hard-link rejection. This suite starts from one already
authorized two-file Profile view and tests only the admission adapter and its
currentness boundary. It never constructs an adoption or Task lifecycle.
"""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import Tools.governance.profile.check_profile as check_profile
import Tools.governance.profile.profile_admission as profile_admission
import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.standards.standards_state as standards_state
import Tools.platform.common.kblib as kblib


FIXTURE_UPSTREAM_REVISION = "0123456789abcdef0123456789abcdef01234567"
PROFILE_DIRECTORY = "profiles/test-profile"
PROFILE_MANIFEST = PROFILE_DIRECTORY + "/profile.md"
PROFILE_SLOT = PROFILE_DIRECTORY + "/slots.md"
INPUTS_SHA256 = "sha256:" + "1" * 64


class MinimalAuthorizedProfile:
    """Two-file current-contract view for the admission consumer boundary."""

    SLOT_NAMES = ("Profile Scope", "Priority Rubric")

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.profile = self.root / PROFILE_DIRECTORY
        self.profile.mkdir(parents=True)
        (self.root / PROFILE_MANIFEST).write_text(
            "# Test Profile\n", encoding="utf-8")
        (self.root / PROFILE_SLOT).write_text(
            "# Synthetic Slot Fixture\n", encoding="utf-8")
        self.evaluation = self.make_evaluation()

    def make_evaluation(self):
        edges = tuple(
            profile_contract.DependencyEdge(
                kind="manifest-slot", owner_id=name, path=PROFILE_SLOT)
            for name in self.SLOT_NAMES
        )
        contract = profile_contract.ProfileContract(
            root=str(self.root),
            manifest_path=str(self.root / PROFILE_MANIFEST),
            manifest_repo_path=PROFILE_MANIFEST,
            profile_root=str(self.profile),
            profile_repo_dir=PROFILE_DIRECTORY,
            audit_registry_path=None,
            scan_registry_path=None,
            routing_registry_path=None,
            extension_registration=None,
            extension_dimensions=(),
            judgment_items=(),
            registered_scans=(),
            extension_gate_registration=None,
            extension_gates=(),
            dependency_edges=edges,
            source_cells=(),
            diagnostics=(),
        )
        snapshot = kblib.repository_tree_snapshot(
            self.root, PROFILE_DIRECTORY).project(
                contract.profile_snapshot_paths)
        return check_profile.ProfileLoadEvaluation(
            exit_code=0,
            findings=(),
            contract=contract,
            metadata_execution_contract=object(),
            profile_id="test-profile",
            profile_snapshot_sha256=snapshot.sha256,
            profile_contract_fingerprint=
                contract.profile_contract_fingerprint,
            execution_default_overrides=(),
            profile_snapshot=snapshot,
            profile_load_inputs_sha256=INPUTS_SHA256,
            summary_receipt={"result": "pass"},
            output="",
        )

    def install_active_state(self):
        target = self.root / standards_state.STATE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(standards_state.canonical_text({
            "schema_version": standards_state.SCHEMA_VERSION,
            "state_revision": 1,
            "upstream_revision_id": FIXTURE_UPSTREAM_REVISION,
            "status": "approved",
            "effective_date": "2026-08-11",
            "selected_profile_manifest": PROFILE_MANIFEST,
            "latest_adoption_receipt": "audit-profile-admission-fixture",
            "upstream_source_ref": "fixture://cambium",
        }), encoding="utf-8")
        return target


class ProfileAdmissionContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = MinimalAuthorizedProfile(self.temporary.name)

    def admit_from_evaluation(self):
        admission, errors = profile_admission.admission_from_evaluation(
            self.fixture.root, self.fixture.evaluation)
        self.assertEqual([], errors)
        self.assertIsNotNone(admission)
        return admission

    def test_adapter_calls_the_authorizing_producer_once_and_projects_slots(self):
        with mock.patch.object(
                profile_admission.check_profile, "evaluate_profile_load",
                return_value=self.fixture.evaluation) as evaluate:
            admission, errors = profile_admission.admit_profile(
                self.fixture.root, self.fixture.profile)

        self.assertEqual([], errors)
        self.assertEqual(1, evaluate.call_count)
        self.assertEqual(
            set(MinimalAuthorizedProfile.SLOT_NAMES),
            set(admission.slot_paths),
        )
        self.assertEqual(
            "# Synthetic Slot Fixture\n",
            admission.slot_text("Profile Scope"),
        )

    def test_admitted_bytes_remain_immutable_and_live_mutation_is_stale(self):
        admission = self.admit_from_evaluation()
        (self.fixture.root / PROFILE_SLOT).write_text(
            "# Transient revision B\n", encoding="utf-8")

        self.assertEqual(
            "# Synthetic Slot Fixture\n",
            admission.slot_text("Profile Scope"),
        )
        with mock.patch.object(
                profile_admission, "_profile_load_inputs_sha256",
                return_value=INPUTS_SHA256):
            errors = profile_admission.currency_errors(admission)
        self.assertIn("selected Profile changed after profile-load",
                      "\n".join(errors))

    def test_canonical_input_binding_change_invalidates_admission(self):
        admission = self.admit_from_evaluation()
        with mock.patch.object(
                profile_admission, "_profile_load_inputs_sha256",
                return_value="sha256:" + "3" * 64):
            errors = profile_admission.currency_errors(admission)

        self.assertIn(
            "canonical profile-load inputs changed after admission",
            "\n".join(errors),
        )


class ProfileSelectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = MinimalAuthorizedProfile(self.temporary.name)
        self.state = self.fixture.install_active_state()

    def mutate_state(self):
        self.state.write_text(
            self.state.read_text(encoding="utf-8").replace(
                "status: approved", "status: draft"),
            encoding="utf-8",
        )

    def test_active_selection_is_bound_during_and_after_admission(self):
        def mutate_during_evaluation(*_args, **_kwargs):
            self.mutate_state()
            return self.fixture.evaluation

        with mock.patch.object(
                profile_admission.check_profile, "evaluate_profile_load",
                side_effect=mutate_during_evaluation):
            admission, errors = profile_admission.admit_profile(
                self.fixture.root)
        self.assertIsNone(admission)
        self.assertIn("active Standards state changed while profile-load",
                      "\n".join(errors))

        self.fixture.install_active_state()
        with mock.patch.object(
                profile_admission.check_profile, "evaluate_profile_load",
                return_value=self.fixture.evaluation):
            admission, errors = profile_admission.admit_profile(
                self.fixture.root)
        self.assertEqual([], errors)
        self.assertIsNotNone(admission)

        self.mutate_state()
        self.assertIn(
            "active Standards state changed after profile-load admission",
            "\n".join(profile_admission.currency_errors(admission)),
        )


if __name__ == "__main__":
    unittest.main()
