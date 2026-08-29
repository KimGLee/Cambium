from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = TOOLS.parent
SCRIPT = TOOLS / "stamp_cards.py"


class StampCardsCommandTests(unittest.TestCase):
    def run_tool(self, root, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(root), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False)

    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name in ("Card", "Read Set", "kernel"):
            shutil.copytree(REPOSITORY / name, root / name)
        (root / "Tools/schemas").mkdir(parents=True)
        shutil.copy2(REPOSITORY / "Tools/schemas/card.schema.yaml",
                     root / "Tools/schemas/card.schema.yaml")
        shutil.copy2(REPOSITORY / "Tools/module-boundaries.yaml",
                     root / "Tools/module-boundaries.yaml")
        return root

    def test_shipped_card_and_read_set_layer_is_current(self):
        result = self.run_tool(REPOSITORY, "--check")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("read_sets=13 curated_cards=13 indexes=2 stale=0",
                      result.stdout)

    def test_generated_index_introductions_use_one_physical_line(self):
        for relative in ("Card/Card Index.md",
                         "Read Set/Read Sets Index.md"):
            lines = (REPOSITORY / relative).read_text(
                encoding="utf-8").splitlines()
            heading = next(index for index, line in enumerate(lines)
                           if line.startswith("# "))
            table = next(index for index, line in enumerate(lines)
                         if line.startswith("| Route ID |"))
            prose = [line for line in lines[heading + 1:table] if line]
            self.assertEqual(1, len(prose), relative)

    def test_noncanonical_card_directory_is_rejected(self):
        result = self.run_tool(REPOSITORY, "--cards-dir", "cards",
                               "--check")
        self.assertEqual(1, result.returncode)
        self.assertIn("must be exactly Card", result.stdout)

    def test_adopter_state_never_rebinds_immutable_card_bytes(self):
        root = self.fixture()
        state = root / ".cambium/governance/standards_state.yaml"
        state.parent.mkdir(parents=True)
        state.write_text(
            "standards_version: " + "a" * 40 + "\n",
            encoding="utf-8")

        current = self.run_tool(root, "--check")

        self.assertEqual(0, current.returncode,
                         current.stdout + current.stderr)

    def test_version_stamping_interface_has_been_removed(self):
        result = self.run_tool(
            REPOSITORY, "--set-version", "adopter-invented")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_source_update_does_not_acknowledge_curated_review(self):
        root = self.fixture()
        source = root / "Read Set/R01 Core Bootstrap Read Set.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nContext.\n",
                          encoding="utf-8")
        observed = self.run_tool(root)
        self.assertEqual(2, observed.returncode, observed.stdout)
        self.assertIn("review_stale=1", observed.stdout)
        acknowledged = self.run_tool(root, "--acknowledge-curated-review")
        self.assertEqual(0, acknowledged.returncode,
                         acknowledged.stdout + acknowledged.stderr)
        current = self.run_tool(root, "--check")
        self.assertEqual(0, current.returncode,
                         current.stdout + current.stderr)

    def test_card_body_change_invalidates_curated_review(self):
        root = self.fixture()
        card = root / "Card/R01 Core Bootstrap Card.md"
        card.write_text(card.read_text(encoding="utf-8") + "\nClarification.\n",
                        encoding="utf-8")

        current = self.run_tool(root, "--check")

        self.assertEqual(2, current.returncode, current.stdout)
        self.assertIn("reviewed_card_hash", current.stdout)


if __name__ == "__main__":
    unittest.main()
