from pathlib import Path
import shutil
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import stamp_cards


class CuratedCardBudgetTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        shutil.copytree(REPOSITORY / "Card", root / "Card")
        shutil.copytree(REPOSITORY / "Read Set", root / "Read Set")
        shutil.copytree(REPOSITORY / "kernel", root / "kernel")
        (root / "Tools").mkdir()
        shutil.copy2(REPOSITORY / "Tools/module-boundaries.yaml",
                     root / "Tools/module-boundaries.yaml")
        return root

    def test_shipped_cards_have_an_independent_small_budget(self):
        cards, read_sets = stamp_cards.discover_cards(REPOSITORY)
        self.assertEqual(13, len(cards))
        self.assertEqual(set(cards), set(read_sets))
        self.assertTrue(all(row["body_bytes"] <= 2200 for row in cards.values()))
        self.assertTrue(all(row["action_items"] <= 10 for row in cards.values()))

    def test_body_byte_budget_fails_closed(self):
        root = self.fixture()
        path = root / "Card/R01 Core Bootstrap Card.md"
        path.write_text(path.read_text(encoding="utf-8") + "x" * 3000,
                        encoding="utf-8")
        with self.assertRaisesRegex(stamp_cards.CardContractError,
                                    "body has .* budget"):
            stamp_cards.discover_cards(root)

    def test_action_item_budget_fails_closed(self):
        root = self.fixture()
        path = root / "Card/R01 Core Bootstrap Card.md"
        path.write_text(path.read_text(encoding="utf-8") +
                        "\n".join("- extra" for _ in range(11)) + "\n",
                        encoding="utf-8")
        with self.assertRaisesRegex(stamp_cards.CardContractError,
                                    "action items"):
            stamp_cards.discover_cards(root)

    def test_card_section_sequence_comes_from_the_card_owned_schema(self):
        root = self.fixture()
        schema = root / "Card/card.schema.yaml"
        schema.write_text(
            schema.read_text(encoding="utf-8").replace(
                "  - Read-back hook", "  - Canonical return"),
            encoding="utf-8")
        with self.assertRaisesRegex(stamp_cards.CardContractError,
                                    "sections must be exactly"):
            stamp_cards.discover_cards(root)


if __name__ == "__main__":
    unittest.main()
