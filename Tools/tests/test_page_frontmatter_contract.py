from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import Tools.knowledge.metadata.page_frontmatter_contract as page_frontmatter_contract  # noqa: E402


class PageFrontmatterContractTests(unittest.TestCase):
    def test_page_type_reads_one_restricted_yaml_scalar(self):
        with tempfile.TemporaryDirectory() as root:
            page = Path(root) / "A.md"
            page.write_text("---\ntype: Concept\n---\n# A\n", encoding="utf-8")
            self.assertEqual(
                "Concept", page_frontmatter_contract.page_type(page))

    def test_missing_or_invalid_frontmatter_has_no_scalar_projection(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "missing.md"
            invalid = Path(root) / "invalid.md"
            missing.write_text("# Missing\n", encoding="utf-8")
            invalid.write_text("---\n- invalid\n---\n", encoding="utf-8")
            self.assertIsNone(page_frontmatter_contract.page_type(missing))
            self.assertIsNone(page_frontmatter_contract.page_type(invalid))


if __name__ == "__main__":
    unittest.main()
