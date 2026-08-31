import inspect
import os
import sys
import unittest


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import Tools.execution.planning.coverage_delta as coverage_delta  # noqa: E402
import Tools.platform.common.kblib as kblib  # noqa: E402
from Tools.tests.support.coverage_delta_fixture import (  # noqa: E402
    FIXTURE_OWNER as PREMERGE_DELTA_FIXTURE_OWNER,
    premerge_delta_document,
)


class CoverageDeltaPublicApiTests(unittest.TestCase):
    TEST_LAYER = "contract"
    PRIMARY_OWNER = (
        "Tools.execution.planning.coverage_delta.delta_policy_errors"
    )
    FIXTURE_OWNER = PREMERGE_DELTA_FIXTURE_OWNER

    def setUp(self):
        self.coverage_text = """\
pages:
  - path: Topics/A.md
    batch:
    next_batch: B1
    authoring_status: draft
    gate_receipts:
      - "gate-old"
open_gaps: []
updated_at: 2026-08-29T00:00:00Z
"""
        self.delta = premerge_delta_document(
            "B1", "Topics/A.md", ["gate-new"],
            generated_at="2026-08-30T00:00:00Z")

    def test_public_plan_and_projection_produce_one_after_image(self):
        self.assertEqual([], coverage_delta.delta_policy_errors(self.delta))
        page_text, planned, rejected, unknown = \
            coverage_delta.plan_page_updates(self.coverage_text, self.delta)
        self.assertEqual(["Topics/A.md"], [path for path, _ in planned])
        self.assertEqual([], rejected)
        self.assertEqual([], unknown)

        after = kblib.parse_yaml_subset(
            coverage_delta.project_coverage_text(page_text, self.delta))
        self.assertEqual("drafted", after["pages"][0]["authoring_status"])
        self.assertEqual(
            ["gate-old", "gate-new"],
            after["pages"][0]["gate_receipts"])
        self.assertEqual("2026-08-30T00:00:00Z", after["updated_at"])

    def test_manifest_mismatch_is_a_rejection_not_a_forceable_mode(self):
        mismatch = dict(self.delta, batch="B2")
        _text, planned, rejected, unknown = \
            coverage_delta.plan_page_updates(self.coverage_text, mismatch)
        self.assertEqual([], planned)
        self.assertEqual([], unknown)
        self.assertEqual([(
            "Topics/A.md", "manifest-mismatch(next_batch=B1,batch=)",
        )], rejected)
        self.assertEqual(
            ["coverage_text", "delta"],
            list(inspect.signature(
                coverage_delta.plan_page_updates).parameters))

    def test_reviewed_promotion_belongs_to_queue_close(self):
        terminal = dict(self.delta)
        terminal["pages"] = [dict(
            self.delta["pages"][0], authoring_status="reviewed")]

        self.assertEqual(
            ["pages[0] cannot promote authoring_status to reviewed; the "
             "merge-ready -> closed Queue transaction owns review "
             "completion and must consume one current per-page review "
             "Receipt"],
            coverage_delta.delta_policy_errors(terminal))

    def test_every_declared_control_field_is_forbidden(self):
        for field in sorted(coverage_delta.DELTA_PAGE_CONTROL_FIELDS):
            with self.subTest(field=field):
                page = dict(self.delta["pages"][0])
                page[field] = None
                errors = coverage_delta.delta_policy_errors(
                    dict(self.delta, pages=[page]))
                self.assertTrue(any(field in error for error in errors), errors)

    def test_gap_delta_adds_and_closes_by_page_type_without_guessing(self):
        coverage = kblib.parse_yaml_subset(self.coverage_text)
        coverage["open_gaps"] = [{
            "page": "Topics/A.md", "type": "link", "note": "old gap",
        }]
        merged = coverage_delta.project_coverage_text(
            kblib.canonical_yaml(coverage), {
                "generated_at": "2026-08-04T03:00:00Z",
                "open_gaps_closed": [{
                    "page": "Topics/A.md", "type": "link",
                }],
                "open_gaps_added": [{
                    "page": "Topics/A.md", "type": "rereview",
                    "note": "downstream reasoning changed",
                }],
            },
        )
        result = kblib.parse_yaml_subset(merged)
        self.assertEqual("2026-08-04T03:00:00Z", result["updated_at"])
        self.assertEqual([{
            "page": "Topics/A.md", "type": "rereview",
            "note": "downstream reasoning changed",
        }], result["open_gaps"])
        with self.assertRaisesRegex(ValueError, "absent gap"):
            coverage_delta.project_coverage_text(
                merged, {"open_gaps_added": [], "open_gaps_closed": [{
                    "page": "Topics/A.md", "type": "link",
                }]})


if __name__ == "__main__":
    unittest.main()
