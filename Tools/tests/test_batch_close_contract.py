"""K12 owns one machine-readable Batch-close Closed List."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import batch_close_contract as contract  # noqa: E402
from queue_runtime import close_gate  # noqa: E402


class RegistryShapeTests(unittest.TestCase):

    def document(self):
        return copy.deepcopy(contract.load_batch_close_closed_list())

    def test_shipped_registry_is_the_current_ordered_eight_member_contract(self):
        document = self.document()
        member_ids = contract.validate_batch_close_closed_list(document)

        self.assertEqual(8, len(member_ids))
        self.assertEqual(
            tuple(row["member_id"] for row in document["members"]),
            member_ids)
        self.assertEqual(member_ids, contract.CLOSED_LIST_EVIDENCE_FIELDS)
        self.assertEqual(member_ids, close_gate.CLOSED_LIST_EVIDENCE_FIELDS)
        self.assertEqual("wiki_link_resolution", member_ids[0])
        self.assertEqual("manifest_page_contract", member_ids[-1])

    def test_registry_order_is_preserved_in_the_machine_projection(self):
        document = self.document()
        document["members"][1], document["members"][2] = \
            document["members"][2], document["members"][1]
        projected = contract.validate_batch_close_closed_list(document)

        self.assertEqual(document["members"][1]["member_id"], projected[1])
        self.assertEqual(document["members"][2]["member_id"], projected[2])

    def test_duplicate_or_open_member_shape_is_rejected(self):
        duplicate = self.document()
        duplicate["members"].append(copy.deepcopy(duplicate["members"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate.*member_id"):
            contract.validate_batch_close_closed_list(duplicate)

        open_shape = self.document()
        open_shape["members"][0]["tool"] = "check_links"
        with self.assertRaisesRegex(
                ValueError,
                "fields are not closed or do not bind exactly one producer"):
            contract.validate_batch_close_closed_list(open_shape)

    def test_missing_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(OSError):
                contract.load_batch_close_closed_list(root)


class ProducerEraProjectionTests(unittest.TestCase):

    def test_legacy_1_4_replay_derives_the_first_seven_registry_members(self):
        current = contract.CLOSED_LIST_EVIDENCE_FIELDS
        legacy = contract.closed_list_evidence_fields_for_producer_version(
            "1.4.0")

        self.assertEqual(7, len(legacy))
        self.assertEqual(current[:7], legacy)
        self.assertEqual(
            legacy, contract.LEGACY_CLOSED_LIST_EVIDENCE_FIELDS)
        self.assertEqual({"1.4.0"}, contract.LEGACY_CLOSED_LIST_VERSIONS)

    def test_post_1_4_and_current_eras_project_the_complete_registry(self):
        for version in ("1.5.0", "1.12.0"):
            with self.subTest(version=version):
                self.assertEqual(
                    contract.CLOSED_LIST_EVIDENCE_FIELDS,
                    contract.closed_list_evidence_fields_for_producer_version(
                        version))


class SingleAuthorityTests(unittest.TestCase):

    def test_producer_and_consumer_do_not_redeclare_the_current_tuple(self):
        producer = (TOOLS / "check_batch_close.py").read_text(
            encoding="utf-8")
        consumer = (TOOLS / "queue_runtime/close_gate.py").read_text(
            encoding="utf-8")

        self.assertNotIn(
            "check_queue.CLOSED_LIST_EVIDENCE_FIELDS", producer)
        self.assertIn(
            "batch_close_contract.CLOSED_LIST_EVIDENCE_FIELDS", producer)
        self.assertNotIn("CLOSED_LIST_EVIDENCE_FIELDS = (", consumer)
        self.assertIn(
            "closed_list_evidence_fields_for_producer_version", consumer)

    def test_k12_prose_references_but_does_not_repeat_the_machine_closed_set(self):
        prose = (REPO / "kernel/K12 Quality Assurance/"
                 "09 Batch-close Closed List.md").read_text(encoding="utf-8")
        module_index = (
            REPO / "kernel/K12 Quality Assurance Standard.md"
        ).read_text(encoding="utf-8")

        self.assertIn("batch-close-closed-list.yaml", prose)
        self.assertIn("batch-close-closed-list.yaml", module_index)
        self.assertNotIn("1. Wiki link missing", prose)
        self.assertNotIn("the following eight items", prose)


if __name__ == "__main__":
    unittest.main()
