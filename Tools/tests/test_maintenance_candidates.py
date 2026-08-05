#!/usr/bin/env python3
"""Set-level tests for the K00/08 maintenance candidate contract."""

import copy
import pathlib
import sys
import tempfile
import unittest


TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import maintenance_candidates


class MaintenanceCandidateTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def record(self, path, *, priority="P1", selection="selected",
               previous=0, current=0, disposition=None, reason=None,
               reentered=False, sources=None):
        return {
            "candidate_id": maintenance_candidates.candidate_id_for_path(path),
            "object_path": path,
            "source_kinds": sources or ["freshness"],
            "priority": priority,
            "previous_deferred_runs": previous,
            "consecutive_deferred_runs": current,
            "reentered_after_terminal": reentered,
            "selection": selection,
            "disposition": disposition,
            "disposition_reason": reason,
        }

    def test_valid_partition_closes_coverage_and_queue_sets(self):
        candidates = [
            self.record("Topics/A.md", priority="P0"),
            self.record("Topics/B.md", selection="deferred", current=1),
        ]
        errors, context = maintenance_candidates.validate_candidates(
            self.root, candidates)
        self.assertEqual([], errors)
        manifest = {
            "selected_candidate_ids": [candidates[0]["candidate_id"]],
            "deferred_candidate_ids": [candidates[1]["candidate_id"]],
            "selected_objects": ["Topics/A.md"],
            "required_batch_ids": ["B1"],
            "deferred_count": 1,
        }
        errors = maintenance_candidates.validate_partition(
            manifest, context,
            queue_items=[{"id": "B1", "order": 1,
                          "manifest": ["Topics/A.md"]}],
            coverage_candidates=copy.deepcopy(candidates),
            coverage_pages=[{"path": "Topics/A.md"},
                            {"path": "Topics/B.md"}],
        )
        self.assertEqual([], errors)

    def test_deferred_count_cannot_replace_the_deferred_set(self):
        candidates = [
            self.record("Topics/A.md", priority="P0"),
            self.record("Topics/B.md", selection="deferred", current=1),
        ]
        errors, context = maintenance_candidates.validate_candidates(
            self.root, candidates)
        self.assertEqual([], errors)
        manifest = {
            "selected_candidate_ids": [candidates[0]["candidate_id"]],
            "deferred_candidate_ids": [candidates[1]["candidate_id"]],
            "selected_objects": ["Topics/A.md"],
            "required_batch_ids": ["B1"],
            "deferred_count": 999,
        }
        errors = maintenance_candidates.validate_partition(
            manifest, context,
            queue_items=[{"id": "B1", "order": 1,
                          "manifest": ["Topics/A.md"]}],
            coverage_candidates=candidates,
            coverage_pages=[{"path": "Topics/A.md"},
                            {"path": "Topics/B.md"}],
        )
        self.assertIn(
            "maintenance budget manifest deferred_count must equal 1", errors)

    def test_manifest_ids_must_be_exact_disjoint_projection(self):
        candidates = [
            self.record("Topics/A.md", priority="P0"),
            self.record("Topics/B.md", selection="deferred", current=1),
        ]
        errors, context = maintenance_candidates.validate_candidates(
            self.root, candidates)
        self.assertEqual([], errors)
        manifest = {
            "selected_candidate_ids": [candidates[0]["candidate_id"],
                                       candidates[1]["candidate_id"]],
            "deferred_candidate_ids": [candidates[1]["candidate_id"]],
            "selected_objects": ["Topics/A.md"],
            "required_batch_ids": ["B1"],
            "deferred_count": 1,
        }
        errors = maintenance_candidates.validate_partition(
            manifest, context,
            queue_items=[{"id": "B1", "order": 1,
                          "manifest": ["Topics/A.md"]}],
            coverage_candidates=candidates,
            coverage_pages=[{"path": "Topics/A.md"},
                            {"path": "Topics/B.md"}],
        )
        self.assertTrue(any("selected_candidate_ids" in error
                            for error in errors), errors)

    def test_third_deferral_requires_log_only_disposition(self):
        record = self.record(
            "Topics/A.md", selection="deferred", previous=2, current=3)
        errors, _ = maintenance_candidates.validate_candidates(
            self.root, [record], previous_candidates=[self.record(
                "Topics/A.md", selection="deferred", previous=1, current=2)])
        self.assertTrue(any("third consecutive deferral" in error
                            for error in errors), errors)
        record["disposition"] = "log-only"
        record["disposition_reason"] = "Automatic demotion after three runs"
        errors, _ = maintenance_candidates.validate_candidates(
            self.root, [record], previous_candidates=[self.record(
                "Topics/A.md", selection="deferred", previous=1, current=2)])
        self.assertEqual([], errors)

    def test_spurious_reentry_after_nonterminal_prior_is_rejected(self):
        prior = [self.record(
            "Topics/A.md", selection="deferred", current=1,
        )]
        current = [self.record(
            "Topics/A.md", selection="selected", previous=1,
            reentered=True,
        )]
        errors, _ = maintenance_candidates.validate_candidates(
            self.root, current, previous_candidates=prior)
        self.assertTrue(any("may re-enter only after a terminal prior" in error
                            for error in errors), errors)

    def test_nonterminal_deferred_candidate_cannot_disappear_next_run(self):
        prior = [self.record(
            "Topics/A.md", selection="deferred", current=1,
        )]
        errors, _ = maintenance_candidates.validate_candidates(
            self.root, [], previous_candidates=prior)
        self.assertTrue(any("silently drops prior nonterminal deferred" in error
                            for error in errors), errors)

    def test_terminal_candidate_requires_explicit_reentry(self):
        previous = self.record(
            "Topics/A.md", selection="deferred", previous=2, current=3,
            disposition="log-only", reason="three-run demotion")
        current = self.record("Topics/A.md", selection="selected")
        errors, _ = maintenance_candidates.validate_candidates(
            self.root, [current], previous_candidates=[previous])
        self.assertTrue(any("requires explicit re-entry" in error
                            for error in errors), errors)
        current["reentered_after_terminal"] = True
        errors, _ = maintenance_candidates.validate_candidates(
            self.root, [current], previous_candidates=[previous])
        self.assertEqual([], errors)

    def test_candidate_identity_and_order_are_deterministic(self):
        records = [
            self.record("Topics/B.md", priority="P1"),
            self.record("Topics/A.md", priority="P0"),
        ]
        records[0]["candidate_id"] = "candidate-sha256:" + "0" * 64
        errors, _ = maintenance_candidates.validate_candidates(
            self.root, records)
        self.assertTrue(any("candidate_id must be" in error for error in errors))
        self.assertTrue(any("must be ordered by priority" in error
                            for error in errors))

    def test_container_values_fail_closed_without_type_error(self):
        malformed_fields = {
            "candidate_id": ["not-a-scalar"],
            "source_kinds": [{"freshness": True}],
            "priority": {"P0": True},
            "selection": ["selected"],
            "disposition": {"kind": "retained"},
        }
        for field, value in malformed_fields.items():
            with self.subTest(field=field):
                record = self.record("Topics/A.md")
                record[field] = value
                errors, context = maintenance_candidates.validate_candidates(
                    self.root, [record])
                self.assertTrue(errors)
                self.assertIn("candidate_state_sha256", context)

    def test_source_kinds_scalar_fails_closed_without_type_error(self):
        for value in ("freshness", {"freshness": True}, 7):
            with self.subTest(value=value):
                record = self.record("Topics/A.md")
                record["source_kinds"] = value
                errors, _ = maintenance_candidates.validate_candidates(
                    self.root, [record])
                self.assertTrue(any("source_kinds must be" in error
                                    for error in errors), errors)

    def test_noncanonical_nested_values_fail_closed_without_exception(self):
        for field, value in (("source_kinds", [[]]), ("disposition", {})):
            with self.subTest(field=field):
                record = self.record("Topics/A.md")
                record[field] = value
                errors, context = maintenance_candidates.validate_candidates(
                    self.root, [record])
                self.assertTrue(any(
                    "cannot be represented by canonical restricted YAML" in
                    error for error in errors), errors)
                self.assertIsNone(context["candidate_state_sha256"])

    def test_non_list_candidate_state_has_explicit_invalid_fingerprint(self):
        errors, context = maintenance_candidates.validate_candidates(
            self.root, {"not": "a list"})
        self.assertTrue(errors)
        self.assertIsNone(context["candidate_state_sha256"])


if __name__ == "__main__":
    unittest.main()
