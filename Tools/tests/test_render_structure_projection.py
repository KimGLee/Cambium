"""Tests for render_structure_projection.py (K01/05 derived roles).

The tool owns only the marker-delimited block inside a registered section;
these tests prove insertion preserves curated prose, application is
idempotent, staleness is detected after an input change, and a missing
heading is reported rather than invented.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / \
    "render_structure_projection.py"

MANIFEST = """# Test Profile

## Implemented Slots

- `Structure Registry`: `structure-registry.yaml`
"""

REGISTRY = """schema_version: 1
applicability:
  state: configured
  reason: null
units:
  - id: U-DOMAIN
    kind: domain
    parent: null
    root: "Domain"
    entry:
      path: "Domain/Overview.md"
      expected_type: overview
    global_map_entry: null
    roles:
      sequence:
        mode: not-applicable
        reason: "n/a"
      coverage:
        mode: derived
        generator: "Tools/render_structure_projection.py"
        inputs_owner: "Corpus Planning/capability_matrix.yaml"
        path: "Domain/Overview.md"
        heading: "Coverage Reader View"
      quick_reference:
        mode: not-applicable
        reason: "n/a"
      expression:
        mode: not-applicable
        reason: "n/a"
support_layers: []
"""

MATRIX = """schema_version: 1
capabilities:
  - capability_id: CAP-001
    capability: Example capability
    priority: P0
    map_entry_ids: []
    canonical_markdown_paths:
      - Domain/Page.md
    current_level: 2 Core
    target_level: 3 System
    evidence_paths: []
    gap_ids:
      - GAP-1
"""

OVERVIEW = """---
type: overview
---
# Overview

## Coverage Reader View

Curated reader guidance that must survive.

## Next Section

Untouched.
"""


class RenderProjectionTests(unittest.TestCase):
    def build(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        files = {
            "profile/profile.md": MANIFEST,
            "profile/structure-registry.yaml": REGISTRY,
            "Corpus Planning/capability_matrix.yaml": MATRIX,
            "Domain/Overview.md": OVERVIEW,
            "Domain/Page.md": "---\ntype: concept\n---\n# P\n",
        }
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    def run_tool(self, root, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(root),
             "--profile", "profile", *args],
            text=True, capture_output=True, check=False)

    def test_apply_inserts_block_and_preserves_prose(self):
        root = self.build()
        result = self.run_tool(root, "--apply")
        self.assertEqual(0, result.returncode, result.stdout)
        text = (root / "Domain/Overview.md").read_text(encoding="utf-8")
        self.assertIn("structure-projection:begin", text)
        self.assertIn("CAP-001", text)
        self.assertIn("Curated reader guidance that must survive.", text)
        self.assertIn("## Next Section", text)
        begin = text.index("structure-projection:begin")
        prose = text.index("Curated reader guidance")
        self.assertLess(begin, prose)

    def test_apply_is_idempotent_and_check_is_clean(self):
        root = self.build()
        self.run_tool(root, "--apply")
        first = (root / "Domain/Overview.md").read_bytes()
        result = self.run_tool(root, "--check")
        self.assertEqual(0, result.returncode, result.stdout)
        self.run_tool(root, "--apply")
        self.assertEqual(first, (root / "Domain/Overview.md").read_bytes())

    def test_check_detects_stale_block_after_input_change(self):
        root = self.build()
        self.run_tool(root, "--apply")
        matrix = root / "Corpus Planning/capability_matrix.yaml"
        matrix.write_text(MATRIX.replace("2 Core", "3 System"),
                          encoding="utf-8")
        result = self.run_tool(root, "--check")
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("stale", result.stdout)

    def test_missing_heading_is_reported_not_invented(self):
        root = self.build()
        (root / "Domain/Overview.md").write_text(
            "---\ntype: overview\n---\n# Overview\n\n## Other\n\nx\n",
            encoding="utf-8")
        result = self.run_tool(root, "--check")
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("not found", result.stdout)


if __name__ == "__main__":
    unittest.main()
