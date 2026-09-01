"""Ownership tests for the Structure Registry coverage projection.

Pure tests own only the renderer's marker-delimited projection and section
replacement contracts. One small filesystem checkpoint proves that the
application writer consumes those contracts; Profile admission, Structure
Registry reference validation, Coverage validation, and public CLI transport
are tested by their respective owners.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import Tools.knowledge.structure.render_structure_projection as renderer


REGISTRY = {
    "schema_version": 2,
    "applicability": {"state": "configured", "reason": None},
    "units": [{
        "id": "U-DOMAIN",
        "kind": "domain",
        "parent": None,
        "root": "Domain",
        "entry": {
            "path": "Domain/Overview.md",
            "expected_type": "overview",
        },
        "global_map_entry": None,
        "roles": {
            "coverage": {
                "mode": "derived",
                "generator_capability": renderer.CAPABILITY_ID,
                "inputs_owner": "planning/capability-matrix.yaml",
                "path": "Domain/Overview.md",
                "heading": "Coverage Reader View",
            },
        },
    }],
    "support_layers": [],
}

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


def capture_main(root, *arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), \
            contextlib.redirect_stderr(stderr):
        code = renderer.main([str(root), *arguments])
    return int(code or 0), stdout.getvalue(), stderr.getvalue()


class StructureProjectionContractTests(unittest.TestCase):
    """Unit/contract: deterministic bytes owned by the renderer."""

    def test_block_projects_only_rows_and_coverage_under_the_unit_root(self):
        matrix = [{
            "capability_id": "CAP-001",
            "capability": "Example capability",
            "canonical_markdown_paths": ["Domain/Page.md"],
            "current_level": "2 Core",
            "target_level": "3 System",
            "gap_ids": ["GAP-1"],
        }, {
            "capability_id": "CAP-OUTSIDE",
            "capability": "Outside capability",
            "canonical_markdown_paths": ["Other/Page.md"],
            "current_level": "1 Listed",
            "target_level": "2 Core",
            "gap_ids": [],
        }]
        dispositions = {
            "Domain/Page.md": "required",
            "Domain/Optional.md": "excluded",
            "Other/Page.md": "required",
        }

        lines = renderer.render_block(
            "U-DOMAIN", "Domain", matrix, dispositions)

        self.assertEqual(renderer.BEGIN, lines[0])
        self.assertEqual(renderer.END, lines[-1])
        rendered = "\n".join(lines)
        self.assertIn("CAP-001", rendered)
        self.assertNotIn("CAP-OUTSIDE", rendered)
        self.assertIn("records 2 page(s) under this root, 1 of them", rendered)
        self.assertEqual(
            lines,
            renderer.render_block(
                "U-DOMAIN", "Domain", matrix, dispositions),
        )

    def test_section_replacement_is_bounded_idempotent_and_requires_heading(self):
        block = [renderer.BEGIN, "generated", renderer.END]

        projected, found, changed = renderer.replace_section_block(
            OVERVIEW, "Coverage Reader View", block)

        self.assertTrue(found)
        self.assertTrue(changed)
        self.assertIn("Curated reader guidance that must survive.", projected)
        self.assertIn("## Next Section\n\nUntouched.", projected)
        self.assertLess(projected.index(renderer.BEGIN),
                        projected.index("Curated reader guidance"))
        repeated, found, changed = renderer.replace_section_block(
            projected, "Coverage Reader View", block)
        self.assertTrue(found)
        self.assertFalse(changed)
        self.assertEqual(projected, repeated)

        missing, found, changed = renderer.replace_section_block(
            OVERVIEW, "Missing Reader View", block)
        self.assertFalse(found)
        self.assertFalse(changed)
        self.assertEqual(OVERVIEW, missing)


class StructureProjectionWriterIntegrationTests(unittest.TestCase):
    """Integration: one admitted local checkpoint exercises the writer seam."""

    def test_apply_check_and_input_drift_share_one_minimal_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "planning/capability-matrix.yaml": MATRIX,
                "Domain/Overview.md": OVERVIEW,
            }
            for relative, text in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            admission = SimpleNamespace()
            capability = {
                "capability_id": renderer.CAPABILITY_ID,
                "kind": renderer.CAPABILITY_KIND,
                "input_owners": [renderer.COVERAGE_LEDGER_OWNER],
            }
            patches = (
                mock.patch.object(
                    renderer.profile_admission, "admit_profile",
                    return_value=(admission, [])),
                mock.patch.object(
                    renderer.profile_admission, "currency_errors",
                    return_value=[]),
                mock.patch.object(
                    renderer, "registry_document", return_value=REGISTRY),
                mock.patch.object(
                    renderer, "projection_capability",
                    return_value=(capability, None)),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                code, stdout, stderr = capture_main(root, "--apply")
                self.assertEqual(0, code, stdout + stderr)
                target = root / "Domain/Overview.md"
                first = target.read_bytes()
                self.assertIn(b"CAP-001", first)
                self.assertIn(
                    b"Curated reader guidance that must survive.", first)

                code, stdout, stderr = capture_main(root, "--check")
                self.assertEqual(0, code, stdout + stderr)
                code, stdout, stderr = capture_main(root, "--apply")
                self.assertEqual(0, code, stdout + stderr)
                self.assertEqual(first, target.read_bytes())

                matrix = root / "planning/capability-matrix.yaml"
                matrix.write_text(
                    MATRIX.replace("2 Core", "3 System"),
                    encoding="utf-8")
                code, stdout, stderr = capture_main(root, "--check")
                self.assertEqual(2, code, stdout + stderr)
                self.assertIn("stale", stdout)


if __name__ == "__main__":
    unittest.main()
