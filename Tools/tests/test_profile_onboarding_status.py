"""Owner tests for deterministic Profile onboarding status projection."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import Tools.governance.profile.profile_onboarding_status as onboarding
from Tools.tests.support.profile_onboarding_status_fixture import (
    FAILING_PROFILE_LOAD,
    OnboardingScenario,
    PASSING_PROFILE_LOAD,
)


class OnboardingDecisionContractTests(unittest.TestCase):
    def test_next_action_precedence_is_one_closed_decision_table(self):
        cases = (
            ("not-root", OnboardingScenario(adopting_root=False), None,
             "not-a-cambium-root"),
            ("runtime-wins", OnboardingScenario(
                standards_state="inconsistent",
                standards_problems=["broken state"],
                runtime_present=True,
                runtime_has_content=True), None, "resume-existing-task"),
            ("inconsistent-control", OnboardingScenario(
                standards_state="inconsistent",
                standards_problems=["broken state"]), None,
             "repair-control-state"),
            ("no-candidate", OnboardingScenario(), None,
             "confirm-profile-identity"),
            ("ambiguous-candidate", OnboardingScenario(
                candidates=("alpha", "beta")), None,
             "confirm-profile-identity"),
            ("unknown-target", OnboardingScenario(
                candidates=("alpha",)), "missing",
             "confirm-profile-identity"),
            ("incomplete-candidate", OnboardingScenario(
                candidates=("candidate",),
                profile_loads={"candidate": FAILING_PROFILE_LOAD}), None,
             "complete-profile-interview"),
            ("complete-candidate", OnboardingScenario(
                candidates=("candidate",),
                profile_loads={"candidate": PASSING_PROFILE_LOAD}), None,
             "authorize-r09"),
            ("adopted-empty", OnboardingScenario(
                standards_state="adopted"), None,
             "found-empty-corpus"),
            ("planning-configured", OnboardingScenario(
                standards_state="adopted", corpus_pages=2,
                planning_state="configured"), None,
             "prepare-task-plan"),
            ("planning-not-applicable", OnboardingScenario(
                standards_state="adopted", corpus_pages=2,
                planning_state="not-applicable"), None,
             "onboarding-complete"),
            ("planning-unreadable", OnboardingScenario(
                standards_state="adopted", corpus_pages=2,
                planning_state="unreadable"), None,
             "repair-control-state"),
        )
        for name, scenario, target, expected in cases:
            with self.subTest(case=name):
                view = scenario.derive(target)
                self.assertEqual(expected, view["next_action"])
                self.assertEqual(onboarding.TOOL, view["tool"])

    def test_report_projects_owned_inputs_without_revalidating_them(self):
        scenario = OnboardingScenario(
            candidates=("alpha", "beta"),
            candidate_ids={"alpha": "alpha-id", "beta": "beta-id"},
            sentinel_counts={"alpha": 3},
            profile_loads={"alpha": FAILING_PROFILE_LOAD},
            corpus_pages=4,
        )
        view = scenario.derive("alpha")
        self.assertEqual("pre-adoption", view["standards_state"])
        self.assertEqual("existing", view["corpus_state"])
        self.assertEqual(4, view["corpus_page_count"])
        self.assertEqual({
            "directory": "profiles/alpha",
            "profile_id": "alpha-id",
            "sentinel_count": 3,
            "targeted": True,
            "profile_load": FAILING_PROFILE_LOAD,
        }, view["candidates"][0])
        self.assertEqual({
            "directory": "profiles/beta",
            "profile_id": "beta-id",
            "sentinel_count": 0,
            "targeted": False,
            "profile_load": None,
        }, view["candidates"][1])
        self.assertEqual("complete-profile-interview", view["next_action"])


class OnboardingProfileDirectoryIntegrationTests(unittest.TestCase):
    def test_one_current_profile_directory_is_deterministic_and_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "adopter"
            for name in ("kernel", "Tools", "profiles/candidate"):
                (root / name).mkdir(parents=True, exist_ok=True)
            profile = root / "profiles/candidate/profile.md"
            profile.write_text(
                """# Candidate

## Profile Identity

- `profile_id`: `candidate`

## Implemented Slots

- `Corpus Planning`: `corpus-planning.yaml`
""",
                encoding="utf-8")
            (profile.parent / "corpus-planning.yaml").write_text(
                "applicability:\n  state: not-applicable\n",
                encoding="utf-8")

            def tree_bytes():
                return {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in sorted(root.rglob("*")) if path.is_file()
                }

            before = tree_bytes()
            outputs = []
            with mock.patch.object(
                    onboarding, "evaluate_candidate",
                    return_value=dict(PASSING_PROFILE_LOAD)), \
                    mock.patch.object(
                        onboarding, "corpus_page_count", return_value=0):
                for _iteration in range(2):
                    buffer = io.StringIO()
                    with contextlib.redirect_stdout(buffer):
                        code = onboarding.main([str(root), "--json"])
                    self.assertEqual(0, code)
                    outputs.append(buffer.getvalue())

            self.assertEqual(outputs[0], outputs[1])
            view = json.loads(outputs[0])
            self.assertEqual("authorize-r09", view["next_action"])
            self.assertEqual("candidate", view["candidates"][0]["profile_id"])
            self.assertEqual(
                "not-applicable", view["corpus_planning_state"])
            self.assertEqual(before, tree_bytes())
            self.assertFalse((root / ".cambium").exists())


if __name__ == "__main__":
    unittest.main()
