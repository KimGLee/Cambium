"""Owner-focused tests for Card index rendering and review currentness.

Card schema, Read Set declarations, size budgets, CLI argument transport, and
the complete distributed repository each have separate owners. This module
keeps the two machine behaviours owned by `stamp_cards`: deterministic index
rendering and the explicit curated-review acknowledgement transition.
"""

import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from Tools.execution.context_delivery import card_contract
from Tools.execution.context_delivery import read_set_contract
from Tools.platform.common import kblib
from Tools.platform.distribution import stamp_cards


REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE = "kernel/K00 Fixture.md"
READ_SET = "Read Set/R01 Fixture Read Set.md"
CARD = "Card/R01 Fixture Card.md"


def _write(root, relative, text):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@contextlib.contextmanager
def _minimal_stamp_root():
    """Yield one route and only the machine inputs stamp_cards consumes."""
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        for relative in (
                card_contract.SCHEMA_PATH,
                read_set_contract.SCHEMA_PATH,
                stamp_cards.CARD_BUDGET_PATH):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPOSITORY / relative, target)
        card_schema = card_contract.load_schema(root)
        read_set_schema = read_set_contract.load_schema(root)

        source = _write(root, SOURCE, "# Fixture source\n")
        read_set_data = {
            "type": read_set_schema["document_type"],
            "schema_version": read_set_schema["schema_version"],
            "route_id": "R01",
            "activation_phase": "batch-preflight",
            "narrowable": False,
            "load_edges": [{
                "edge_id": "R01:start",
                "kind": "required",
                "phase_id": "batch-preflight",
                "trigger_id": "route-selected",
                "targets": [SOURCE],
                "read_sets": [],
            }],
        }
        _write(
            root, READ_SET,
            "---\n%s---\n# Fixture Read Set\n\n"
            "## Purpose\n\nFixture loading boundary.\n\n"
            "## Non-deterministic triggers\n\nNone.\n" %
            kblib.canonical_yaml(read_set_data),
        )

        body = (
            "# Fixture Card\n\n"
            "## Purpose\n\nFixture action projection.\n\n"
            "## Actions\n\n- Read the declared source.\n\n"
            "## Stop or escalate\n\nStop when the source is stale.\n\n"
            "## Read-back hook\n\nReturn to the declared Read Set.\n"
        )
        sources = [READ_SET, SOURCE]
        source_hash = stamp_cards.source_digest(root, sources)
        card_data = {
            "type": card_schema["document_type"],
            "generation_mode": card_schema["generation_mode"],
            "route_id": "R01",
            "read_set_id": "R01",
            "read_set": READ_SET,
            "source_files": sources,
            "source_hash": source_hash,
            "reviewed_source_hash": source_hash,
            "reviewed_card_hash": "0" * 12,
        }
        provisional = "---\n%s---\n%s" % (
            kblib.canonical_yaml(card_data), body)
        card_data["reviewed_card_hash"] = \
            stamp_cards.card_body_digest(provisional)
        card = _write(
            root, CARD,
            "---\n%s---\n%s" % (kblib.canonical_yaml(card_data), body),
        )

        cards, read_sets = stamp_cards.discover_cards(root)
        _write(root, card_schema["index_path"],
               stamp_cards.render_card_index(cards, read_sets))
        _write(root, read_set_schema["index_path"],
               stamp_cards.render_read_set_index(read_sets))
        yield root, source, card


def _invoke(root, *arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = stamp_cards.main([str(root), *arguments])
    return code, output.getvalue()


class StampCardsRenderingContractTests(unittest.TestCase):
    def test_generated_indexes_have_one_non_authoritative_introduction(self):
        cards = {"R01": {"path": CARD}}
        read_sets = {"R01": {"path": READ_SET}}
        rendered = (
            stamp_cards.render_card_index(cards, read_sets),
            stamp_cards.render_read_set_index(read_sets),
        )
        for text in rendered:
            with self.subTest(index=text.splitlines()[5]):
                lines = text.splitlines()
                heading = next(index for index, line in enumerate(lines)
                               if line.startswith("# "))
                table = next(index for index, line in enumerate(lines)
                             if line.startswith("| Route ID |"))
                introduction = [
                    line for line in lines[heading + 1:table] if line]
                self.assertEqual(1, len(introduction))
                self.assertIn("generation_mode: generated", text)
                self.assertIn("not", introduction[0].lower())


class StampCardsCurrentnessIntegrationTests(unittest.TestCase):
    def test_source_and_body_changes_require_explicit_review_acknowledgement(self):
        with _minimal_stamp_root() as (root, source, card):
            code, output = _invoke(root, "--check")
            self.assertEqual(0, code, output)

            before = stamp_cards._frontmatter(
                card.read_text(encoding="utf-8"), CARD)
            source.write_text("# Fixture source\n\nChanged.\n",
                              encoding="utf-8")
            code, output = _invoke(root)
            self.assertEqual(2, code, output)
            self.assertIn("review_stale=1", output)
            self.assertIn("updated=1", output)
            observed = stamp_cards._frontmatter(
                card.read_text(encoding="utf-8"), CARD)
            self.assertNotEqual(before["source_hash"],
                                observed["source_hash"])
            self.assertEqual(before["reviewed_source_hash"],
                             observed["reviewed_source_hash"])

            code, output = _invoke(root, "--acknowledge-curated-review")
            self.assertEqual(0, code, output)
            code, output = _invoke(root, "--check")
            self.assertEqual(0, code, output)

            card.write_text(
                card.read_text(encoding="utf-8") + "\nClarification.\n",
                encoding="utf-8",
            )
            code, output = _invoke(root, "--check")
            self.assertEqual(2, code, output)
            self.assertIn("reviewed_card_hash", output)


if __name__ == "__main__":
    unittest.main()
