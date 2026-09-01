"""Owned tests for the independent curated-Card size budget.

Card schema, source-review currentness, curated semantic coverage, and command
transport have separate owners. The contract cases below use one serialized
budget or one Card machine object; only the projection smoke check reads the
shipped Card collection.
"""

import contextlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import Tools.execution.context_delivery.card_contract as card_contract
from Tools.platform.common import kblib
import Tools.platform.distribution.stamp_cards as stamp_cards


REPOSITORY = Path(__file__).resolve().parents[2]
READ_SET_PATH = "Read Set/R01 Fixture Read Set.md"


def _write_budget(root, value):
    path = root / stamp_cards.CARD_BUDGET_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kblib.canonical_yaml(value), encoding="utf-8")


@contextlib.contextmanager
def _minimal_root():
    with tempfile.TemporaryDirectory() as workspace:
        yield Path(workspace)


def _card_text(*, action_items=1, suffix=""):
    actions = "\n".join("- action-%d" % number
                        for number in range(1, action_items + 1))
    return """---
type: card
generation_mode: curated
route_id: R01
read_set_id: R01
read_set: Read Set/R01 Fixture Read Set.md
source_files:
  - Read Set/R01 Fixture Read Set.md
source_hash: '000000000000'
reviewed_source_hash: '000000000000'
reviewed_card_hash: '000000000000'
---
# Fixture Card

## Purpose

Fixture.

## Actions

%s

## Stop or escalate

Stop.

## Read-back hook

Read back.%s
""" % (actions, suffix)


class CardBudgetContractTests(unittest.TestCase):
    def test_budget_document_has_one_closed_positive_machine_shape(self):
        valid = kblib.parse_yaml_subset(kblib.read_text(
            REPOSITORY / stamp_cards.CARD_BUDGET_PATH))
        invalid = {
            "extra-field": (dict(valid, comment="not contractual"),
                            "invalid closed shape"),
            "schema-version": (
                dict(valid, schema_version=valid["schema_version"] + 1),
                "unsupported Card budget schema_version"),
            "zero-body-budget": (dict(valid, max_body_bytes=0),
                                 "must be a positive integer"),
            "boolean-action-budget": (dict(valid, max_action_items=True),
                                      "must be a positive integer"),
        }
        with _minimal_root() as root:
            _write_budget(root, valid)
            self.assertEqual(valid, stamp_cards._load_budget(root))
            for label, (value, expected) in invalid.items():
                with self.subTest(label=label):
                    _write_budget(root, value)
                    with self.assertRaisesRegex(
                            card_contract.CardContractError, expected):
                        stamp_cards._load_budget(root)

    def test_body_and_action_limits_are_independent_boundary_predicates(self):
        schema = card_contract.load_schema(REPOSITORY)
        read_sets = {"R01": {"path": READ_SET_PATH}}
        with _minimal_root() as root:
            card = root / "Card/R01 Fixture Card.md"
            card.parent.mkdir(parents=True)
            boundary = _card_text()
            body_bytes = len(stamp_cards._body(boundary).encode("utf-8"))
            budget = dict(
                stamp_cards._load_budget(REPOSITORY),
                max_body_bytes=body_bytes,
                max_action_items=1,
            )
            with (
                    mock.patch.object(stamp_cards, "_load_card_schema",
                                      return_value=schema),
                    mock.patch.object(stamp_cards, "_load_budget",
                                      return_value=budget),
                    mock.patch.object(
                        stamp_cards.read_set_contract, "load_schema",
                        return_value={}),
                    mock.patch.object(
                        stamp_cards.read_set_contract, "discover",
                        return_value=read_sets)):
                card.write_text(boundary, encoding="utf-8")
                records, _read_sets = stamp_cards.discover_cards(root)
                self.assertEqual(body_bytes, records["R01"]["body_bytes"])
                self.assertEqual(1, records["R01"]["action_items"])

                card.write_text(_card_text(suffix="x"), encoding="utf-8")
                with self.assertRaisesRegex(
                        card_contract.CardContractError,
                        "body has .* budget"):
                    stamp_cards.discover_cards(root)

                two_actions = _card_text(action_items=2)
                budget["max_body_bytes"] = len(
                    stamp_cards._body(two_actions).encode("utf-8"))
                card.write_text(two_actions, encoding="utf-8")
                with self.assertRaisesRegex(
                        card_contract.CardContractError,
                        "has 2 action items; budget is 1"):
                    stamp_cards.discover_cards(root)


class ShippedCardBudgetProjectionTests(unittest.TestCase):
    def test_shipped_projection_obeys_the_serialized_budget(self):
        budget = stamp_cards._load_budget(REPOSITORY)
        cards, _read_sets = stamp_cards.discover_cards(REPOSITORY)
        self.assertTrue(cards)
        self.assertTrue(all(
            row["body_bytes"] <= budget["max_body_bytes"] and
            row["action_items"] <= budget["max_action_items"]
            for row in cards.values()))


if __name__ == "__main__":
    unittest.main()
