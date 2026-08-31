"""Owned tests for evidence-backed metadata property state.

State transitions consume already-admitted rules and already-observed page
fingerprints. The projector owns repository after-images separately, so only
one test below crosses that adjacent boundary with a real page.
"""

import copy
from pathlib import Path
import sys
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import Tools.governance.control.metadata_execution_contract as \
    metadata_execution_contract
import Tools.knowledge.metadata.metadata_page_state_contract as \
    metadata_page_state_contract
import Tools.knowledge.metadata.metadata_property_state as state
import Tools.knowledge.metadata.project_page_state as project_page_state
import Tools.platform.common.kblib as kblib


PAGE_PATH = "Topics/A.md"
BEFORE_FINGERPRINT = "sha256:" + "1" * 64
AFTER_FINGERPRINT = "sha256:" + "2" * 64

# Compile the machine owner once from the live authority and capability
# registry. Individual tests consume its admitted rules directly; they do not
# copy a repository or revalidate a generated projection.
METADATA_CONTRACT = \
    metadata_execution_contract.compile_metadata_execution_contract(
        REPOSITORY)
CORE_RULES = tuple(metadata_execution_contract.rules_for_capability(
    METADATA_CONTRACT, state.PAGE_WRITER_CAPABILITY))


def coverage():
    return {
        "pages": [{
            "path": PAGE_PATH,
            "coverage_disposition": "required",
            "authoring_status": "drafted",
            "next_batch": "B1",
            "gate_receipts": [],
            "property_state": {},
        }],
    }


def receipt(check, receipt_id="audit-event-1",
            checked_at="2026-08-20T12:00:00Z"):
    return {
        "receipt_id": receipt_id,
        "tool": "fixture",
        "tool_version": "1.0.0",
        "check": check,
        "target": PAGE_PATH,
        "result": "pass",
        "invalidated_by": None,
        "checked_at": checked_at,
    }


def owner_record(value, receipt_id, fingerprint=BEFORE_FINGERPRINT):
    return {
        "value": value,
        "evidence_receipt": receipt_id,
        "content_fingerprint": fingerprint,
    }


def observed(fingerprint):
    return mock.patch.object(
        state, "semantic_page_snapshot", return_value=(None, fingerprint))


class MetadataPropertyStateUnitTests(unittest.TestCase):
    """Pure transitions over admitted rules and observed fingerprints."""

    def test_content_change_creates_current_owner_and_is_idempotent(self):
        with observed(AFTER_FINGERPRINT):
            proposed, paths, events = state.apply_content_change(
                coverage(), None, [PAGE_PATH], receipt("delta_apply"),
                before_semantic_fingerprints={
                    PAGE_PATH: BEFORE_FINGERPRINT,
                },
                rules=CORE_RULES)

        record = proposed["pages"][0]["property_state"][
            state.LAST_CONTENT_MODIFIED]
        self.assertEqual("2026-08-20", record["value"])
        self.assertEqual("audit-event-1", record["evidence_receipt"])
        self.assertEqual(AFTER_FINGERPRINT, record["content_fingerprint"])
        self.assertEqual((PAGE_PATH,), paths)
        self.assertEqual(
            BEFORE_FINGERPRINT,
            events[0]["before_semantic_content_sha256"])

        with observed(AFTER_FINGERPRINT):
            unchanged, paths, events = state.apply_content_change(
                proposed, None, [PAGE_PATH],
                receipt(
                    "delta_apply", "audit-event-2",
                    "2026-08-21T12:00:00Z"),
                before_semantic_fingerprints={
                    PAGE_PATH: AFTER_FINGERPRINT,
                },
                rules=CORE_RULES)
        self.assertEqual(proposed, unchanged)
        self.assertEqual((), paths)
        self.assertEqual((), events)

    def test_content_change_invalidates_each_dependent_owner_by_rule(self):
        gate_rule = state.gate_projection_rule(
            "readiness_state", ("accepted", "rejected"))
        rules = metadata_execution_contract.AuthorizedProjectionRules(
            CORE_RULES + (gate_rule,),
            METADATA_CONTRACT.contract_fingerprint,
            "sha256:" + "3" * 64)
        current = coverage()
        current["pages"][0]["property_state"] = {
            state.LAST_REVIEWED: owner_record(
                "2026-08-19", "audit-review-old"),
            "readiness_state": owner_record(
                "accepted", "audit-gate-old"),
        }

        with observed(AFTER_FINGERPRINT):
            proposed, _paths, events = state.apply_content_change(
                current, None, [PAGE_PATH], receipt("delta_apply"),
                before_semantic_fingerprints={
                    PAGE_PATH: BEFORE_FINGERPRINT,
                },
                rules=rules)

        properties = proposed["pages"][0]["property_state"]
        self.assertIsNone(properties[state.LAST_REVIEWED]["value"])
        self.assertEqual(
            AFTER_FINGERPRINT,
            properties[state.LAST_REVIEWED]["content_fingerprint"])
        self.assertNotIn("readiness_state", properties)
        self.assertEqual(
            [state.LAST_REVIEWED, "readiness_state"],
            events[0]["invalidated_property_fields"])
        self.assertEqual(
            ["tombstone-current-owner", "remove-owner-and-page-copy"],
            [row["action"] for row in
             events[0]["invalidated_property_records"]])

    def test_repeated_content_change_refreshes_current_review_tombstone(self):
        current = coverage()
        current["pages"][0]["property_state"] = {
            state.LAST_REVIEWED: owner_record(
                None, "audit-content-old"),
        }
        next_receipt = receipt(
            "delta_apply", "audit-content-second",
            "2026-08-21T12:00:00Z")

        with observed(AFTER_FINGERPRINT):
            proposed, _paths, events = state.apply_content_change(
                current, None, [PAGE_PATH], next_receipt,
                before_semantic_fingerprints={
                    PAGE_PATH: BEFORE_FINGERPRINT,
                },
                rules=CORE_RULES)

        tombstone = proposed["pages"][0]["property_state"][
            state.LAST_REVIEWED]
        self.assertIsNone(tombstone["value"])
        self.assertEqual("audit-content-second", tombstone["evidence_receipt"])
        self.assertEqual(AFTER_FINGERPRINT, tombstone["content_fingerprint"])
        self.assertEqual(
            [state.LAST_REVIEWED],
            events[0]["invalidated_property_fields"])

    def test_apply_time_first_observation_is_not_a_change_baseline(self):
        with self.assertRaisesRegex(ValueError, "before fingerprints"):
            state.apply_content_change(
                coverage(), None, [PAGE_PATH], receipt("delta_apply"),
                before_semantic_fingerprints={}, rules=CORE_RULES)

    def test_gate_transition_accepts_only_its_declared_completion_values(self):
        proposed = state.apply_gate_transition(
            coverage(), PAGE_PATH, "interview_status", "interview-ready",
            "audit-gate-1", AFTER_FINGERPRINT,
            ("draft", "interview-ready"))
        self.assertEqual(
            "interview-ready",
            proposed["pages"][0]["property_state"][
                "interview_status"]["value"])

        with self.assertRaisesRegex(ValueError, "not one of"):
            state.apply_gate_transition(
                coverage(), PAGE_PATH, "interview_status", "invented",
                "audit-gate-1", AFTER_FINGERPRINT,
                ("draft", "interview-ready"))


class MetadataPropertyStateContractTests(unittest.TestCase):
    """Receipt and typed-value acceptance at the owner boundary."""

    def test_page_review_requires_current_content_and_updates_owner_state(self):
        current_receipt = receipt(
            state.PAGE_REVIEW_CHECK, "audit-review-1")
        current_receipt.update({
            "reviewed_on": "2026-08-20",
            "semantic_content_sha256": AFTER_FINGERPRINT,
            "metadata_execution_contract_fingerprint":
                METADATA_CONTRACT.contract_fingerprint,
        })

        with observed(AFTER_FINGERPRINT):
            proposed, paths = state.apply_review_acceptance(
                coverage(), None, [current_receipt], rules=CORE_RULES,
                metadata_contract_fingerprint=
                    METADATA_CONTRACT.contract_fingerprint)

        row = proposed["pages"][0]
        reviewed = row["property_state"][state.LAST_REVIEWED]
        self.assertEqual("2026-08-20", reviewed["value"])
        self.assertEqual("reviewed", row["authoring_status"])
        self.assertEqual(["audit-review-1"], row["gate_receipts"])
        self.assertEqual((PAGE_PATH,), paths)

        stale_receipt = copy.deepcopy(current_receipt)
        stale_receipt["receipt_id"] = "audit-review-stale"
        stale_receipt["semantic_content_sha256"] = BEFORE_FINGERPRINT
        with observed(AFTER_FINGERPRINT), self.assertRaisesRegex(
                ValueError, "current semantic content"):
            state.apply_review_acceptance(
                coverage(), None, [stale_receipt], rules=CORE_RULES)

    def test_profile_gate_owner_domain_is_the_declared_enum(self):
        rule = state.gate_projection_rule(
            "interview_status", ("interview-ready",))
        with self.assertRaises(ValueError):
            metadata_page_state_contract.typed_owner_value(
                "mapped", rule, PAGE_PATH)
        self.assertEqual(
            "interview-ready",
            metadata_page_state_contract.typed_owner_value(
                "interview-ready", rule, PAGE_PATH))


class MetadataPropertyStateIntegrationTests(unittest.TestCase):
    """One real in-process state-to-projector handoff."""

    def test_content_owner_state_projects_into_the_exact_after_image(self):
        before_text = "# A\n\nBody before\n"
        after_text = "# A\n\nBody after\n"
        before = project_page_state.semantic_content_fingerprint(
            PAGE_PATH, before_text, CORE_RULES)
        after = project_page_state.semantic_content_fingerprint(
            PAGE_PATH, after_text, CORE_RULES)
        with observed(after):
            proposed, paths, _events = state.apply_content_change(
                coverage(), None, [PAGE_PATH], receipt("delta_apply"),
                before_semantic_fingerprints={PAGE_PATH: before},
                rules=CORE_RULES)
        projected, changes = project_page_state.project_page(
            after_text, proposed["pages"][0], CORE_RULES)

        self.assertEqual((PAGE_PATH,), paths)
        self.assertIn(
            (state.LAST_CONTENT_MODIFIED, None, "2026-08-20"), changes)
        frontmatter = kblib.parse_yaml_subset(
            kblib.extract_frontmatter(projected))
        self.assertEqual(
            "2026-08-20", frontmatter[state.LAST_CONTENT_MODIFIED])
        self.assertTrue(projected.endswith(after_text))


if __name__ == "__main__":
    unittest.main()
