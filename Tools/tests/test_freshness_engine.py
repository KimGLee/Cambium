import datetime
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import freshness_engine as engine


AS_OF = datetime.date(2026, 8, 14)


class FreshnessEngineTests(unittest.TestCase):
    def policy(self, defaults=None):
        return engine.FreshnessPolicy(
            as_of=AS_OF,
            volatility_defaults=defaults,
        )

    def snapshot(self, path="Topic.md", *, frontmatter=None,
                 modified_on=datetime.date(2026, 1, 1),
                 frontmatter_error=False, excluded=False):
        return engine.PageSnapshot(
            path=path,
            frontmatter={} if frontmatter is None else frontmatter,
            modified_on=modified_on,
            frontmatter_error=frontmatter_error,
            excluded=excluded,
        )

    def classify(self, frontmatter, **kwargs):
        return engine.classify_page(
            self.snapshot(frontmatter=frontmatter, **kwargs), self.policy())

    def test_valid_selected_baseline_does_not_hide_future_unselected_event(self):
        outcome = self.classify({
            "volatility": "fast",
            "last_verified": "2026-08-01",
            "last_reviewed": "2099-01-01",
        })
        self.assertEqual(engine.FUTURE_BASELINE, outcome.kind)
        self.assertEqual(
            ["last_reviewed"], [reason.field for reason in outcome.reasons])

    def test_invalid_last_verified_cannot_fall_back_to_last_reviewed(self):
        outcome = self.classify({
            "volatility": "fast",
            "last_verified": "not-a-date",
            "last_reviewed": "2026-08-01",
        })
        self.assertEqual(engine.INVALID_BASELINE, outcome.kind)
        self.assertIsNone(outcome.baseline_field)

    def test_blank_last_verified_is_absent_and_allows_reviewed_fallback(self):
        outcome = self.classify({
            "volatility": "fast",
            "last_verified": "  ",
            "last_reviewed": "2026-08-01",
        })
        self.assertEqual(engine.FRESH, outcome.kind)
        self.assertEqual("last_reviewed", outcome.baseline_field)

    def test_content_modified_after_review_is_a_rereview_candidate(self):
        outcome = self.classify({
            "volatility": "slow",
            "last_content_modified": "2026-08-10",
            "last_reviewed": "2026-08-09",
        })
        self.assertEqual(engine.MODIFIED_SINCE_REVIEW, outcome.kind)
        self.assertEqual(
            ["content_modified_since_review"],
            [reason.code for reason in outcome.reasons])

    def test_review_on_modification_date_closes_intermediate_state(self):
        outcome = self.classify({
            "volatility": "slow",
            "last_content_modified": "2026-08-10",
            "last_reviewed": "2026-08-10",
        })
        self.assertEqual(engine.FRESH, outcome.kind)
        self.assertEqual("last_reviewed", outcome.baseline_field)

    def test_invalid_content_modified_date_cannot_be_hidden(self):
        outcome = self.classify({
            "volatility": "slow",
            "last_content_modified": "not-a-date",
            "last_reviewed": "2026-08-10",
        })
        self.assertEqual(engine.INVALID_BASELINE, outcome.kind)
        self.assertEqual(
            ["last_content_modified"],
            [reason.field for reason in outcome.reasons])

    def test_date_parser_rejects_prefixes_and_invalid_calendar_dates(self):
        for value in ("2026-08-14T00:00:00Z", "2026-02-30", 20260814):
            with self.subTest(value=value):
                self.assertIsNone(engine.parse_iso_date(value))

    def test_temporal_validation_precedes_stable_policy(self):
        outcome = self.classify({
            "volatility": "stable",
            "last_verified": "2099-01-01",
        })
        self.assertEqual(engine.FUTURE_BASELINE, outcome.kind)

    def test_temporal_validation_precedes_unresolved_volatility(self):
        outcome = self.classify({"last_verified": "2099-01-01"})
        self.assertEqual(engine.FUTURE_BASELINE, outcome.kind)

    def test_invalid_explicit_volatility_cannot_use_a_valid_default(self):
        snapshot = self.snapshot(frontmatter={
            "domain": "systems",
            "volatility": "rapid",
            "last_verified": "2026-08-01",
        })
        outcome = engine.classify_page(
            snapshot, self.policy(defaults={"systems": "fast"}))
        self.assertEqual(engine.INVALID_VOLATILITY, outcome.kind)

    def test_missing_volatility_without_default_is_a_candidate(self):
        outcome = self.classify({"last_verified": "2026-08-01"})
        self.assertEqual(engine.UNRESOLVED_VOLATILITY, outcome.kind)
        self.assertTrue(outcome.is_candidate)

    def test_defaulted_volatility_is_recorded_as_policy_source(self):
        snapshot = self.snapshot(frontmatter={
            "domain": "systems",
            "last_verified": "2026-08-01",
        })
        outcome = engine.classify_page(
            snapshot, self.policy(defaults={"systems": "fast"}))
        self.assertEqual(engine.FRESH, outcome.kind)
        self.assertEqual("defaults", outcome.volatility_source)

    def test_unparseable_frontmatter_is_a_page_candidate(self):
        snapshot = self.snapshot(
            frontmatter=None, frontmatter_error=True)
        outcome = engine.classify_page(snapshot, self.policy())
        self.assertEqual(engine.UNPARSEABLE_FRONTMATTER, outcome.kind)

    def test_inactive_lifecycle_is_out_of_scope_before_temporal_validation(self):
        outcome = self.classify({
            "lifecycle": "retired",
            "volatility": "fast",
            "last_verified": "2099-01-01",
        })
        self.assertEqual(engine.INACTIVE, outcome.kind)
        self.assertFalse(outcome.is_candidate)

    def test_baseline_equal_to_as_of_is_valid(self):
        outcome = self.classify({
            "volatility": "fast",
            "last_verified": AS_OF.isoformat(),
        })
        self.assertEqual(engine.FRESH, outcome.kind)

    def test_review_by_equal_to_as_of_is_zero_day_overdue(self):
        baseline = AS_OF - datetime.timedelta(days=120)
        outcome = self.classify({
            "volatility": "fast",
            "last_verified": baseline.isoformat(),
        })
        self.assertEqual(engine.OVERDUE, outcome.kind)
        self.assertEqual(0, outcome.overdue_days)

    def test_missing_event_dates_are_pending_for_nonstable_page(self):
        outcome = self.classify({"volatility": "fast"})
        self.assertEqual(engine.PENDING_FIRST_VERIFICATION, outcome.kind)
        self.assertEqual("file-modified", outcome.baseline_field)

    def test_stable_page_without_event_dates_requires_first_verification(self):
        outcome = self.classify({"volatility": "stable"})
        self.assertEqual(engine.PENDING_FIRST_VERIFICATION, outcome.kind)
        self.assertTrue(outcome.is_candidate)
        self.assertEqual("file-modified", outcome.baseline_field)
        self.assertIsNone(outcome.review_by)

    def test_maximum_valid_date_with_interval_does_not_overflow(self):
        snapshot = self.snapshot(frontmatter={
            "volatility": "fast",
            "last_verified": "9999-12-31",
        })
        outcome = engine.classify_page(
            snapshot,
            engine.FreshnessPolicy(as_of=datetime.date.max),
        )
        self.assertEqual(engine.FRESH, outcome.kind)
        self.assertEqual(datetime.date.max, outcome.baseline)
        self.assertIsNone(outcome.review_by)

    def test_pending_due_date_beyond_calendar_is_explicit_not_a_crash(self):
        snapshot = self.snapshot(
            frontmatter={"volatility": "fast"},
            modified_on=datetime.date.max,
        )
        outcome = engine.classify_page(
            snapshot,
            engine.FreshnessPolicy(as_of=datetime.date.max),
        )
        self.assertEqual(engine.PENDING_FIRST_VERIFICATION, outcome.kind)
        self.assertIsNone(outcome.review_by)

    def test_mixed_run_cannot_turn_an_unresolved_page_into_a_pass(self):
        pages = (
            self.snapshot("Fresh.md", frontmatter={
                "volatility": "fast",
                "last_verified": "2026-08-01",
            }),
            self.snapshot("Unresolved.md", frontmatter={
                "last_verified": "2026-08-01",
            }),
        )
        run = engine.evaluate_freshness(pages, self.policy())
        self.assertEqual("candidate", run.result)
        self.assertEqual(1, run.candidate_count)
        self.assertEqual(1, run.counts[engine.FRESH])
        self.assertEqual(1, run.counts[engine.UNRESOLVED_VOLATILITY])
        self.assertTrue(run.complete)
        self.assertEqual(run.discovered_count, sum(run.counts.values()))

    def test_candidate_category_prevents_zero_day_sort_collision(self):
        zero_day = (AS_OF - datetime.timedelta(days=120)).isoformat()
        pages = (
            self.snapshot("Future.md", frontmatter={
                "priority": "P0",
                "volatility": "fast",
                "last_verified": "2099-01-01",
            }),
            self.snapshot("Overdue.md", frontmatter={
                "priority": "P0",
                "volatility": "fast",
                "last_verified": zero_day,
            }),
        )
        run = engine.evaluate_freshness(reversed(pages), self.policy())
        self.assertEqual(
            [engine.OVERDUE, engine.FUTURE_BASELINE],
            [item.kind for item in run.candidates],
        )

    def test_evaluation_is_independent_of_input_iteration_order(self):
        pages = (
            self.snapshot("B.md", frontmatter={
                "volatility": "fast", "last_verified": "2099-01-01"}),
            self.snapshot("A.md", frontmatter={
                "volatility": "fast", "last_verified": "2026-08-01"}),
        )
        forward = engine.evaluate_freshness(pages, self.policy())
        backward = engine.evaluate_freshness(reversed(pages), self.policy())
        self.assertEqual(forward, backward)

    def test_zero_page_run_is_not_positive_freshness_evidence(self):
        run = engine.evaluate_freshness((), self.policy())
        self.assertTrue(run.nothing_checked)
        self.assertEqual("candidate", run.result)
        self.assertEqual(1, run.candidate_count)


if __name__ == "__main__":
    unittest.main()
