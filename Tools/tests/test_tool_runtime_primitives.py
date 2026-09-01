import os
import sys
import unittest


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORY = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

from Tools.execution.task_runtime import queue_runtime as queue_primitives  # noqa: E402
import Tools.platform.common.primitives as platform_primitives  # noqa: E402


class SharedPrimitiveTests(unittest.TestCase):
    def test_catalog_record_only_unwraps_the_two_supported_shapes(self):
        record = {"receipt_id": "R-1"}
        self.assertIs(record, platform_primitives.catalog_record(record))
        self.assertIs(
            record,
            platform_primitives.catalog_record(("receipts.jsonl", record)),
        )
        self.assertIsNone(platform_primitives.catalog_record(None))
        self.assertIsNone(platform_primitives.catalog_record(("source", [])))
        self.assertIsNone(platform_primitives.catalog_record(("source",)))
        self.assertIsNone(platform_primitives.catalog_record(["source", record]))
        catalog = {"R-1": ("receipts.jsonl", record)}
        self.assertIs(
            record, platform_primitives.catalog_receipt(catalog, "R-1"))
        self.assertIsNone(platform_primitives.catalog_receipt(catalog, "R-2"))
        self.assertIsNone(platform_primitives.catalog_receipt([], "R-1"))

    def test_queue_runtime_reexports_the_platform_timestamp_predicates(self):
        self.assertIs(
            platform_primitives.nonempty_string,
            queue_primitives.nonempty_string)
        self.assertIs(
            platform_primitives.timestamp_value,
            queue_primitives.timestamp_value)
        self.assertIs(
            platform_primitives.valid_timestamp,
            queue_primitives.valid_timestamp)
        self.assertEqual(
            "Tools.platform.common.primitives",
            queue_primitives.valid_timestamp.__module__)
        self.assertEqual(
            "Tools/platform/common/primitives.py",
            os.path.relpath(
                platform_primitives.__file__, REPOSITORY).replace(
                    os.sep, "/"))

    def test_timestamp_contract_is_unchanged(self):
        self.assertTrue(platform_primitives.valid_timestamp(
            "2026-08-30T12:00:00Z"))
        self.assertTrue(platform_primitives.valid_timestamp(
            "2026-08-30T20:00:00+08:00"))
        self.assertFalse(platform_primitives.valid_timestamp(
            "2026-08-30T12:00:00"))
        self.assertIsNone(platform_primitives.timestamp_value("not-a-time"))


if __name__ == "__main__":
    unittest.main()
