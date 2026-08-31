"""In-memory producer outputs for Profile onboarding decision tests."""

from dataclasses import dataclass, field
from typing import Optional
from unittest import mock

import Tools.governance.profile.profile_onboarding_status as onboarding


PASSING_PROFILE_LOAD = {
    "result": "pass",
    "mechanical": 0,
    "semantic_unresolved": 0,
}
FAILING_PROFILE_LOAD = {
    "result": "fail",
    "mechanical": 1,
    "semantic_unresolved": 2,
}


@dataclass
class OnboardingScenario:
    """Supply already-owned inputs to the deterministic status projector."""

    adopting_root: bool = True
    standards_state: str = "pre-adoption"
    standards_values: Optional[dict] = None
    standards_uninstantiated: list = field(default_factory=list)
    standards_problems: list = field(default_factory=list)
    candidates: tuple = ()
    candidate_ids: dict = field(default_factory=dict)
    sentinel_counts: dict = field(default_factory=dict)
    profile_loads: dict = field(default_factory=dict)
    planning_state: str = "not-applicable"
    corpus_pages: int = 0
    runtime_present: bool = False
    runtime_has_content: bool = False

    def _standards_values(self):
        if self.standards_values is not None:
            return self.standards_values
        if self.standards_state != "adopted":
            return None
        return {
            "effective_date": "2026-08-13",
            "selected_profile_manifest": "profiles/candidate/profile.md",
            "status": "approved",
            "upstream_revision_id": "a" * 40,
        }

    def derive(self, targeted_id=None):
        def directory_exists(_path):
            return self.adopting_root

        def candidate_id(_root, name):
            return self.candidate_ids.get(name, name)

        def sentinels(path, _sentinel):
            name = str(path).rstrip("/").rsplit("/", 1)[-1]
            return self.sentinel_counts.get(name, 0)

        def profile_load(_root, name):
            return dict(self.profile_loads.get(
                name, PASSING_PROFILE_LOAD))

        with mock.patch.object(
                onboarding.os.path, "isdir", side_effect=directory_exists), \
                mock.patch.object(
                    onboarding, "standards_view", return_value=(
                        self.standards_state,
                        self._standards_values(),
                        list(self.standards_uninstantiated),
                        list(self.standards_problems))), \
                mock.patch.object(
                    onboarding, "unfilled_sentinel",
                    return_value="TODO(profile)"), \
                mock.patch.object(
                    onboarding, "candidate_directories",
                    return_value=list(self.candidates)), \
                mock.patch.object(
                    onboarding, "candidate_profile_id",
                    side_effect=candidate_id), \
                mock.patch.object(
                    onboarding, "sentinel_count", side_effect=sentinels), \
                mock.patch.object(
                    onboarding, "evaluate_candidate",
                    side_effect=profile_load), \
                mock.patch.object(
                    onboarding, "corpus_planning_state",
                    return_value=self.planning_state), \
                mock.patch.object(
                    onboarding, "corpus_page_count",
                    return_value=self.corpus_pages), \
                mock.patch.object(
                    onboarding, "runtime_view", return_value={
                        "present": self.runtime_present,
                        "state_has_content": self.runtime_has_content,
                    }):
            return onboarding.derive_status(
                "/synthetic/adopter", targeted_id)


__all__ = [
    "FAILING_PROFILE_LOAD",
    "OnboardingScenario",
    "PASSING_PROFILE_LOAD",
]
