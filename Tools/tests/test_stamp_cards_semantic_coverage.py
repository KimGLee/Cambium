from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import Tools.platform.distribution.stamp_cards as stamp_cards


class CuratedCardAuthorityTests(unittest.TestCase):
    def test_cards_are_curated_projections_not_compiled_artifacts(self):
        cards, _read_sets = stamp_cards.discover_cards(REPOSITORY)
        for route_id, row in cards.items():
            with self.subTest(route_id=route_id):
                self.assertEqual("curated", row["data"]["generation_mode"])
                self.assertNotIn("compiled_source_hash", row["data"])
                self.assertNotIn("readback_sources", row["data"])
                self.assertNotIn("readback_policy", row["data"])
                self.assertEqual(row["body_hash"],
                                 row["reviewed_card_hash"])

    def test_review_hash_proves_currentness_only(self):
        cards, _read_sets = stamp_cards.discover_cards(REPOSITORY)
        for route_id, row in cards.items():
            with self.subTest(route_id=route_id):
                expected = stamp_cards.source_digest(
                    REPOSITORY, row["source_files"])
                self.assertEqual(expected, row["source_hash"])
                self.assertEqual(expected, row["reviewed_source_hash"])


if __name__ == "__main__":
    unittest.main()
