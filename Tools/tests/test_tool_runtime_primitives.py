import os
import sys
import unittest


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORY = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

from Tools.execution.task_runtime import queue_runtime as queue_primitives  # noqa: E402
import Tools.platform.common.primitives as platform_primitives  # noqa: E402


class SharedPrimitiveTests(unittest.TestCase):
    def test_document_projection_is_scoped_by_owner_and_exact_bytes(self):
        calls = []
        def owner(document):
            calls.append(document["value"])
            if type(document["value"]) is not int:
                raise ValueError("integer required")
            return {"values": [document["value"]]}
        original = {"value": 1}
        snapshot = platform_primitives.validated_document(
            original, owner, cache_projection=True)
        original["value"] = 2
        projected = platform_primitives.document_projection(snapshot, owner)
        projected["values"].append(99)
        self.assertEqual({"values": [1]},
            platform_primitives.document_projection(snapshot, owner))
        self.assertEqual([1], calls)
        selected = platform_primitives.document_projection(snapshot, owner, path=("values",))
        selected.append(88)
        self.assertEqual([1], platform_primitives.document_projection(snapshot, owner, path=("values",)))
        self.assertIsNone(platform_primitives.document_projection(snapshot, owner, path=None))
        self.assertEqual([1], calls)
        with self.assertRaises(KeyError):
            platform_primitives.document_projection(snapshot, owner, path=("missing",))
        self.assertEqual("different-owner",
            platform_primitives.document_projection(snapshot, lambda _: "different-owner"))
        snapshot["value"] = True  # bool == 1 must not match the captured bytes.
        with self.assertRaisesRegex(ValueError, "integer required"):
            platform_primitives.document_projection(snapshot, owner, path=None)
        uncached = platform_primitives.validated_document(original, owner)
        self.assertIs(original, uncached)
        platform_primitives.document_projection(uncached, owner)
        self.assertEqual([1, True, 2, 2], calls)

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
