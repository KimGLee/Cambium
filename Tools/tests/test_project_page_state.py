"""Tests for the K08/07 page-state projector."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
TOOL = REPO / "Tools" / "project_page_state.py"

LEDGER = """schema_version: 1
pages:
  - path: "Domain/Closed.md"
    coverage_disposition: required
    authoring_status: reviewed
    next_batch:
  - path: "Domain/Routed.md"
    coverage_disposition: required
    authoring_status: drafted
    next_batch: T-002
  - path: "Domain/Bare.md"
    coverage_disposition: required
    authoring_status: drafted
    next_batch: T-003
"""

CLOSED = """---
type: concept
authoring_status: drafted
next_batch: T-001
---
# Closed
"""

ROUTED = """---
type: concept
authoring_status: drafted
next_batch: T-001
---
# Routed
"""

BARE = """---
type: concept
---
# Bare
"""


class ProjectPageStateTests(unittest.TestCase):
    def build(self):
        root = tempfile.mkdtemp()
        files = {
            ".cambium/state/coverage_ledger.yaml": LEDGER,
            "Domain/Closed.md": CLOSED,
            "Domain/Routed.md": ROUTED,
            "Domain/Bare.md": BARE,
        }
        for rel, body in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
        return root

    def run_tool(self, root, *argv):
        return subprocess.run(
            [sys.executable, str(TOOL), root, *argv],
            capture_output=True, text=True)

    def read(self, root, rel):
        with open(os.path.join(root, rel), encoding="utf-8") as handle:
            return handle.read()

    def test_dry_run_plans_but_writes_nothing(self):
        root = self.build()
        result = self.run_tool(root)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("PLAN", result.stdout)
        self.assertIn("dry run", result.stdout)
        self.assertEqual(CLOSED, self.read(root, "Domain/Closed.md"))

    def test_apply_updates_removes_and_never_adds(self):
        root = self.build()
        result = self.run_tool(root, "--apply")
        self.assertEqual(0, result.returncode, result.stdout)
        closed = self.read(root, "Domain/Closed.md")
        # updated to the owner value
        self.assertIn("authoring_status: reviewed", closed)
        # removed: owner next_batch is empty (the closed-batch stale copy)
        self.assertNotIn("next_batch", closed)
        routed = self.read(root, "Domain/Routed.md")
        self.assertIn("next_batch: T-002", routed)
        # a page that never carried a projection field does not gain one
        bare = self.read(root, "Domain/Bare.md")
        self.assertNotIn("authoring_status", bare)
        self.assertNotIn("next_batch", bare)
        # idempotent: a second run plans zero changes
        again = self.run_tool(root, "--apply")
        self.assertIn("field_changes=0", again.stdout)

    def test_page_scope_and_unknown_page(self):
        root = self.build()
        result = self.run_tool(root, "--page", "Domain/Routed.md", "--apply")
        self.assertEqual(0, result.returncode, result.stdout)
        # only the scoped page was touched
        self.assertIn("next_batch: T-001", self.read(root, "Domain/Closed.md"))
        self.assertIn("next_batch: T-002", self.read(root, "Domain/Routed.md"))
        unknown = self.run_tool(root, "--page", "Domain/Absent.md")
        self.assertEqual(1, unknown.returncode, unknown.stdout)
        self.assertIn("not in the Coverage Ledger", unknown.stdout)


if __name__ == "__main__":
    unittest.main()
