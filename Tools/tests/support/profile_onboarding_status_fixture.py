"""In-memory draft producer outputs for onboarding decision tests.

These objects are producer checkpoints, not complete Profiles or Gate
evaluations. The status projector remains real; only its upstream reads are
replaced. No fixture can manufacture a pass/admission result.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional
from unittest import mock

import Tools.governance.profile.profile_contract as profile_contract
import Tools.governance.profile.profile_layout_contract as profile_layout_contract
import Tools.governance.profile.profile_onboarding_status as onboarding


READY_DRAFT = profile_contract.ProfileDraft(
    profile_id="candidate", manifest_repo_path="profiles/candidate/profile.toml",
    slot_values={}, diagnostics=(), unresolved_items=(), ready=True)
INCOMPLETE_DRAFT = replace(
    READY_DRAFT, ready=False,
    unresolved_items=("slots.profile-scope.goal", "slots.role-registry.process_roles"))
INVALID_DRAFT = replace(
    READY_DRAFT, ready=False, diagnostics=(profile_contract.Diagnostic(
        "profile-draft-shape", "profiles/candidate/profile.toml",
        "slots.profile-scope.goal.statement must be a string"),))


@dataclass
class OnboardingScenario:
    """Supply one typed draft output per candidate to the real projector."""

    adopting_root: bool = True
    standards_state: str = "pre-adoption"
    standards_values: Optional[dict] = None
    standards_uninstantiated: list = field(default_factory=list)
    standards_problems: list = field(default_factory=list)
    candidates: tuple = ()
    candidate_ids: dict = field(default_factory=dict)
    drafts: dict = field(default_factory=dict)
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
            "selected_profile_manifest": "profiles/candidate/profile.toml",
            "status": "approved",
            "upstream_revision_id": "a" * 40,
        }

    def derive(self, targeted_id=None):
        def candidate_draft(_root, directory):
            name = Path(directory).name
            draft = self.drafts.get(name, READY_DRAFT)
            if not isinstance(draft, profile_contract.ProfileDraft):
                raise TypeError("onboarding fixture requires a ProfileDraft output")
            slots = {key: draft.slot_document(key) for key in draft.slot_values}
            slots["corpus-planning"] = {
                "applicability": {"state": self.planning_state}}
            return replace(
                draft, profile_id=self.candidate_ids.get(name, name),
                manifest_repo_path="profiles/%s/%s" % (
                    name, profile_layout_contract.PROFILE_MANIFEST_NAME),
                slot_values=slots)

        with mock.patch.object(
                onboarding.os.path, "isdir", return_value=self.adopting_root), \
                mock.patch.object(
                    onboarding, "standards_view", return_value=(
                        self.standards_state, self._standards_values(),
                        list(self.standards_uninstantiated),
                        list(self.standards_problems))), \
                mock.patch.object(
                    onboarding, "candidate_directories",
                    return_value=list(self.candidates)), \
                mock.patch.object(
                    onboarding, "_candidate_draft", side_effect=candidate_draft), \
                mock.patch.object(
                    onboarding, "corpus_page_count", return_value=self.corpus_pages), \
                mock.patch.object(
                    onboarding, "runtime_view", return_value={
                        "present": self.runtime_present,
                        "state_has_content": self.runtime_has_content,
                    }):
            return onboarding.derive_status("/synthetic/adopter", targeted_id)


__all__ = [
    "INCOMPLETE_DRAFT", "INVALID_DRAFT", "OnboardingScenario", "READY_DRAFT",
]
