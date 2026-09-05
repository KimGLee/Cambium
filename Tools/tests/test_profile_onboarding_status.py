"""Owner tests for read-only draft onboarding, distinct from admission."""

import contextlib
from dataclasses import replace
import io
import json
import unittest
from unittest import mock

import Tools.governance.profile.profile_onboarding_status as onboarding
from Tools.tests.support.profile_contract_fixture import CurrentProfileContractFixture
from Tools.tests.support.profile_onboarding_status_fixture import (
    INCOMPLETE_DRAFT, INVALID_DRAFT, OnboardingScenario, READY_DRAFT,
)


class OnboardingDecisionContractTests(unittest.TestCase):
    def test_next_action_precedence_is_one_closed_decision_table(self):
        cases = (
            ("not-root", OnboardingScenario(adopting_root=False), None, "not-a-cambium-root"),
            ("runtime-wins", OnboardingScenario(
                standards_state="inconsistent", standards_problems=["broken state"],
                runtime_present=True, runtime_has_content=True), None, "resume-existing-task"),
            ("inconsistent-control", OnboardingScenario(
                standards_state="inconsistent", standards_problems=["broken state"]),
             None, "repair-control-state"),
            ("no-candidate", OnboardingScenario(), None, "confirm-profile-identity"),
            ("ambiguous-candidate", OnboardingScenario(candidates=("alpha", "beta")),
             None, "confirm-profile-identity"),
            ("unknown-target", OnboardingScenario(candidates=("alpha",)),
             "missing", "confirm-profile-identity"),
            ("incomplete-candidate", OnboardingScenario(
                candidates=("candidate",), drafts={"candidate": INCOMPLETE_DRAFT}),
             None, "complete-profile-interview"),
            ("invalid-candidate", OnboardingScenario(
                candidates=("candidate",), drafts={"candidate": INVALID_DRAFT}),
             None, "complete-profile-interview"),
            ("ready-candidate", OnboardingScenario(
                candidates=("candidate",), drafts={"candidate": READY_DRAFT}),
             None, "validate-profile-load"),
            ("adopted-empty", OnboardingScenario(standards_state="adopted"),
             None, "found-empty-corpus"),
            ("planning-configured", OnboardingScenario(
                standards_state="adopted", corpus_pages=2, planning_state="configured"),
             None, "prepare-task-plan"),
            ("planning-not-applicable", OnboardingScenario(
                standards_state="adopted", corpus_pages=2, planning_state="not-applicable"),
             None, "onboarding-complete"),
            ("planning-unreadable", OnboardingScenario(
                standards_state="adopted", corpus_pages=2, planning_state="unreadable"),
             None, "repair-control-state"),
        )
        for name, scenario, target, expected in cases:
            with self.subTest(case=name):
                view = scenario.derive(target)
                self.assertEqual(expected, view["next_action"])
                self.assertEqual(onboarding.TOOL, view["tool"])

    def test_report_projects_draft_outputs_without_manufacturing_pass_evidence(self):
        incomplete = replace(INCOMPLETE_DRAFT, unresolved_items=(
            "slots.profile-scope.goal", "slots.role-registry.process_roles",
            "slots.source-policy.source_authority"))
        scenario = OnboardingScenario(
            candidates=("alpha", "beta"),
            candidate_ids={"alpha": "alpha-id", "beta": "beta-id"},
            drafts={"alpha": incomplete}, corpus_pages=4)
        view = scenario.derive("alpha")
        self.assertEqual("pre-adoption", view["standards_state"])
        self.assertEqual("existing", view["corpus_state"])
        self.assertEqual(4, view["corpus_page_count"])
        self.assertEqual({
            "directory": "profiles/alpha", "profile_id": "alpha-id",
            "unresolved_count": 3, "targeted": True,
            "draft": onboarding.evaluate_candidate(incomplete),
        }, view["candidates"][0])
        self.assertEqual({
            "directory": "profiles/beta", "profile_id": "beta-id",
            "unresolved_count": 0, "targeted": False,
            "draft": onboarding.evaluate_candidate(READY_DRAFT),
        }, view["candidates"][1])
        self.assertEqual("complete-profile-interview", view["next_action"])
        self.assertFalse(any(
            token in view["candidates"][0] for token in ("profile_load", "receipt", "authorized")))


class OnboardingProfileDirectoryIntegrationTests(unittest.TestCase):
    def test_complete_and_incomplete_candidates_are_deterministic_read_only_drafts(self):
        fixture = CurrentProfileContractFixture(self)
        complete_slots = fixture.document["slots"]

        def tree_bytes():
            return {path.relative_to(fixture.root).as_posix(): path.read_bytes()
                    for path in sorted(fixture.root.rglob("*")) if path.is_file()}

        for slots, state, action in (
                ({}, "incomplete", "complete-profile-interview"),
                (complete_slots, "ready", "validate-profile-load")):
            with self.subTest(state=state):
                fixture.document["slots"] = slots
                fixture.save()
                before = tree_bytes()
                outputs = []
                with mock.patch.object(
                        onboarding.check_profile, "evaluate_profile_load",
                        side_effect=AssertionError("draft inspection must not invoke admission")):
                    for _iteration in range(2):
                        buffer = io.StringIO()
                        with contextlib.redirect_stdout(buffer):
                            code = onboarding.main([str(fixture.root), "--json"])
                        self.assertEqual(0, code, buffer.getvalue())
                        outputs.append(buffer.getvalue())
                self.assertEqual(outputs[0], outputs[1])
                view = json.loads(outputs[0])
                self.assertEqual(action, view["next_action"])
                self.assertEqual("test-profile", view["candidates"][0]["profile_id"])
                self.assertEqual(state, view["candidates"][0]["draft"]["result"])
                self.assertEqual(before, tree_bytes())
                self.assertFalse((fixture.root / ".cambium").exists())


if __name__ == "__main__":
    unittest.main()
