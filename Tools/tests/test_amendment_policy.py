"""Closed impact derivation and Task Contract Amendment delegation."""

import copy
import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import amendment_policy  # noqa: E402


def page(path="Topics/A.md", disposition="required", batch="B1"):
    return {
        "path": path,
        "coverage_disposition": disposition,
        "canonical_owner": path,
        "type": "concept",
        "priority": "P1",
        "tier": "M",
        "authoring_status": "drafted",
        "prerequisites": [],
        "batch": batch,
        "next_batch": batch,
        "deferred_reason": None,
        "reentry_condition": None,
        "gate_receipts": [],
        "property_state": {},
    }


def batch(batch_id="B1", execution_mode="serial-integrator"):
    return {
        "id": batch_id,
        "family": "Core",
        "order_hint": 1,
        "source_route": "R03",
        "execution_mode": execution_mode,
        "depends_on": [],
        "confirmation_required": False,
        "work_spec_path": None,
        "work_spec_sha256": None,
    }


def coverage():
    return {
        "schema_version": 1,
        "task_id": "task",
        "updated_at": "2026-08-15T00:00:00Z",
        "scope_version": "s1",
        "standards_version": "3.9.2",
        "selected_profile_manifest": "profiles/p/profile.yaml",
        "batch_specs": [batch()],
        "maintenance_candidates": [],
        "pages": [page()],
        "open_gaps": [],
    }


def queue(state="queued"):
    return {
        "required_queue": [{
            "id": "B1", "state": state, "hold_state": "none",
        }],
    }


def authority(*classes):
    return {
        "schema_version": 1,
        "authority_id": "AUTH-001",
        "mode": "delegated-integrator",
        "allowed_change_classes": sorted(classes),
    }


class AmendmentPolicyTests(unittest.TestCase):
    def test_property_state_adoption_is_coverage_only_and_user_decided(self):
        before = coverage()
        before["pages"][0].pop("property_state")
        after = copy.deepcopy(before)
        after["pages"][0].update({
            "property_state": {},
            "legacy_property_state": {
                "last_reviewed": {
                    "status": "legacy-unverified",
                    "value": "2026-07-31",
                },
            },
        })

        impact = amendment_policy.derive_amendment_impact(
            before, after, queue())

        self.assertEqual([], impact["forbidden_reasons"])
        self.assertEqual("property-state-migration",
                         impact["writer_operation"])
        self.assertEqual(["property-state-adoption"],
                         impact["change_classes"])
        self.assertEqual(["Topics/A.md"], impact["affected_pages"])
        self.assertEqual([], impact["affected_batches"])
        with self.assertRaises(amendment_policy.UserDecisionRequired):
            amendment_policy.resolve_authority(
                {"amendment_authority": authority()}, impact)

    def test_property_state_adoption_cannot_rewrite_current_owner(self):
        before = coverage()
        after = copy.deepcopy(before)
        after["pages"][0]["property_state"] = {
            "last_reviewed": {"invented": True},
        }

        impact = amendment_policy.derive_amendment_impact(
            before, after, queue())

        self.assertTrue(any(
            "may only adopt one absent owner mapping" in reason
            for reason in impact["forbidden_reasons"]), impact)

    def test_required_growth_derives_one_closed_scope_replan(self):
        before = coverage()
        after = copy.deepcopy(before)
        after["scope_version"] = "s2"
        after["pages"].append(page("Topics/B.md", batch="B2"))
        after["batch_specs"].append(batch("B2"))

        impact = amendment_policy.derive_amendment_impact(
            before, after, queue())

        self.assertEqual([], impact["forbidden_reasons"])
        self.assertEqual("scope-replan", impact["writer_operation"])
        self.assertEqual(
            ["batch-add", "required-object-add"],
            impact["change_classes"])
        self.assertEqual(["Topics/B.md"], impact["affected_pages"])
        self.assertEqual(["B2"], impact["affected_batches"])

    def test_queued_reroute_and_batch_update_are_queue_replan(self):
        before = coverage()
        after = copy.deepcopy(before)
        after["pages"][0]["batch"] = "B2"
        after["pages"][0]["next_batch"] = "B2"
        after["batch_specs"][0]["execution_mode"] = "concurrent-worker"

        impact = amendment_policy.derive_amendment_impact(
            before, after, queue())

        self.assertEqual([], impact["forbidden_reasons"])
        self.assertEqual("queue-replan", impact["writer_operation"])
        self.assertEqual(
            ["queued-batch-update", "required-object-reroute"],
            impact["change_classes"])
        self.assertEqual(["B1", "B2"], impact["affected_batches"])

    def test_open_work_spec_change_is_known_but_never_delegated_in_v1(self):
        before = coverage()
        after = copy.deepcopy(before)
        after["batch_specs"][0]["work_spec_path"] = \
            ".cambium/deltas/work-specs/B1.yaml"
        after["batch_specs"][0]["work_spec_sha256"] = "sha256:" + "1" * 64
        live_queue = queue(state="open")
        live_queue["required_queue"][0]["hold_state"] = \
            "revalidation-required"

        impact = amendment_policy.derive_amendment_impact(
            before, after, live_queue)

        self.assertEqual([], impact["forbidden_reasons"])
        self.assertEqual(
            ["open-work-spec-update"], impact["change_classes"])
        with self.assertRaises(amendment_policy.UserDecisionRequired):
            amendment_policy.resolve_authority(
                {"amendment_authority": authority(
                    "required-object-add")}, impact)

    def test_contract_delegation_binds_the_exact_derived_impact(self):
        before = coverage()
        after = copy.deepcopy(before)
        after["scope_version"] = "s2"
        after["pages"].append(page("Topics/B.md", batch="B2"))
        after["batch_specs"].append(batch("B2"))
        impact = amendment_policy.derive_amendment_impact(
            before, after, queue())
        contract = {"amendment_authority": authority(
            "batch-add", "required-object-add")}

        decision = amendment_policy.resolve_authority(contract, impact)

        self.assertEqual("contract-delegated", decision["decision_mode"])
        self.assertEqual("AUTH-001", decision["authority_id"])
        self.assertEqual("contract:AUTH-001",
                         decision["approval_reference"])
        record = dict(decision, operation="scope-replan")
        self.assertEqual(
            decision,
            amendment_policy.require_decision_binding(
                contract, impact, record))

        record["amendment_impact_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(
                amendment_policy.AmendmentPolicyError,
                "amendment_impact_sha256"):
            amendment_policy.require_decision_binding(
                contract, impact, record)

    def test_absent_or_user_only_authority_requires_fresh_user_decision(self):
        before = coverage()
        after = copy.deepcopy(before)
        after["batch_specs"][0]["execution_mode"] = "concurrent-worker"
        impact = amendment_policy.derive_amendment_impact(
            before, after, queue())

        for contract in ({}, {"amendment_authority": {
                "schema_version": 1, "authority_id": "AUTH-001",
                "mode": "user-only", "allowed_change_classes": [],
        }}):
            with self.subTest(contract=contract):
                with self.assertRaises(
                        amendment_policy.UserDecisionRequired):
                    amendment_policy.resolve_authority(contract, impact)
                explicit = amendment_policy.resolve_authority(
                    contract, impact, requested_mode="explicit-user",
                    approval_reference="user:approved")
                self.assertEqual("explicit-user",
                                 explicit["decision_mode"])
                self.assertIsNone(explicit["authority_id"])

    def test_gap_metadata_removal_and_terminal_structure_fail_closed(self):
        cases = []
        before = coverage()
        gap = copy.deepcopy(before)
        gap["open_gaps"].append({"gap_id": "G1"})
        cases.append((gap, queue(), "gap-reconciliation"))

        removed = copy.deepcopy(before)
        removed["pages"] = []
        cases.append((removed, queue(), "removal"))

        terminal = copy.deepcopy(before)
        terminal["batch_specs"][0]["execution_mode"] = "concurrent-worker"
        cases.append((terminal, queue(state="closed"),
                      "no supported Amendment effect"))

        for after, live_queue, expected in cases:
            with self.subTest(expected=expected):
                impact = amendment_policy.derive_amendment_impact(
                    before, after, live_queue)
                self.assertTrue(impact["forbidden_reasons"])
                self.assertIn(expected,
                              "\n".join(impact["forbidden_reasons"]))
                with self.assertRaises(
                        amendment_policy.AmendmentPolicyError):
                    amendment_policy.resolve_authority(
                        {"amendment_authority": authority(
                            "queued-batch-update")}, impact)

    def test_authority_shape_is_closed_and_sorted(self):
        malformed = authority("required-object-add")
        malformed["allowed_change_classes"] = [
            "required-object-add", "batch-add"]
        self.assertTrue(amendment_policy.amendment_authority_errors(
            malformed))
        malformed["allowed_change_classes"] = ["future-class"]
        self.assertIn(
            "unsupported delegated class",
            "\n".join(amendment_policy.amendment_authority_errors(
                malformed)))

    def test_gap_reconciliation_is_known_but_requires_explicit_user(self):
        before = coverage()
        before["open_gaps"] = [{
            "id": "G1", "page": "Topics/A.md", "type": "review",
            "next_batch": "B1",
        }]
        after = copy.deepcopy(before)
        after["open_gaps"][0]["next_batch"] = "B2"
        live_queue = queue(state="closed")
        live_queue["required_queue"].append({
            "id": "B2", "state": "queued", "hold_state": "none",
        })

        impact = amendment_policy.derive_amendment_impact(
            before, after, live_queue)
        self.assertEqual([], impact["forbidden_reasons"])
        self.assertEqual("gap-routing-reconciliation",
                         impact["writer_operation"])
        self.assertEqual(["gap-routing-reconciliation"],
                         impact["change_classes"])
        with self.assertRaises(amendment_policy.UserDecisionRequired):
            amendment_policy.resolve_authority(
                {"amendment_authority": authority(
                    "required-object-add")}, impact)
        decision = amendment_policy.resolve_authority(
            {}, impact, requested_mode="explicit-user",
            approval_reference="user:gap-reconciliation")
        self.assertEqual("explicit-user", decision["decision_mode"])


if __name__ == "__main__":
    unittest.main()
