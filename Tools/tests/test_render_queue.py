"""Owner-focused tests for the disposable Required Queue projection.

Queue validation, readiness, dependency blocking, and lifecycle transitions
belong to their machine owners. These tests therefore consume one already
validated result: a pure contract test owns the Markdown bytes, while one
small filesystem seam owns report publication, currentness checking, and the
managed report-path boundary. Public CLI/MCP transport is covered by the
shared interface-contract suites and no Task lifecycle is replayed here.
"""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from Tools.execution.task_runtime import render_queue


def validated_result():
    """Return the smallest parsed owner result needed by the projection."""
    items = [{
        "id": "B1",
        "order": 1,
        "family": "Knowledge Review",
        "record_count": 2,
        "execution_mode": "serial-integrator",
        "state": "queued",
        "hold_state": "none",
        "depends_on": [],
    }, {
        "id": "B0",
        "order": 0,
        "family": "Knowledge Review",
        "record_count": 1,
        "execution_mode": "serial-integrator",
        "state": "closed",
        "hold_state": "none",
        "depends_on": [],
    }]
    return {
        "errors": [],
        "queue": {
            "task_id": "task-projection",
            "scope_version": "scope-1",
            "queue_revision": 4,
            "state_revision": 7,
            "required_queue": items,
        },
        "progress": {
            "task_state": "active",
            "contract": {
                "completion_semantics": "build",
                "objective": "Project the current Required Queue.",
                "exclusions": ["Do not replay a Task lifecycle."],
            },
            "maintenance_completion": {
                "state": "not-applicable",
                "completion_gate_receipt": None,
            },
        },
        "queue_sha256": "sha256:" + "1" * 64,
        "remaining": 1,
        "ready": ["B1"],
        "blocked": {},
    }


def invoke(root, *arguments):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = render_queue.main([str(root), *arguments])
    return int(code or 0), stdout.getvalue()


class RenderQueueContractTests(unittest.TestCase):
    def test_projection_is_deterministic_and_contains_only_owner_result_fields(self):
        result = validated_result()

        first = render_queue.render(result)
        second = render_queue.render(result)

        self.assertEqual(first, second)
        self.assertIn("Derived report only", first)
        self.assertIn("Objective: Project the current Required Queue.", first)
        self.assertIn("Exclusions: Do not replay a Task lifecycle.", first)
        self.assertIn("Remaining required work units: `1`", first)
        self.assertIn("- `B1`", first)
        self.assertIn("- `B0`: `closed` (1 object(s))", first)
        self.assertLess(first.index("| 0 | `B0`"), first.index("| 1 | `B1`"))


class RenderQueueWriterIntegrationTests(unittest.TestCase):
    def test_writer_check_and_report_namespace_share_one_projection(self):
        result = validated_result()
        expected = render_queue.render(result)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path = root / ".cambium/state/required_queue.yaml"
            queue_path.parent.mkdir(parents=True)
            queue_path.write_text("authoritative: true\n", encoding="utf-8")
            before = queue_path.read_bytes()

            with mock.patch.object(
                    render_queue.runtime_validation, "validate_runtime",
                    return_value=result):
                code, output = invoke(root)
                self.assertEqual(0, code, output)
                report = root / ".cambium/reports/required_queue.md"
                self.assertEqual(expected, report.read_text(encoding="utf-8"))

                repeated, repeated_output = invoke(root)
                self.assertEqual(0, repeated, repeated_output)
                self.assertEqual(expected, report.read_text(encoding="utf-8"))

                checked, checked_output = invoke(root, "--check")
                self.assertEqual(0, checked, checked_output)

                report.write_text("stale\n", encoding="utf-8")
                stale, stale_output = invoke(root, "--check")
                self.assertEqual(1, stale, stale_output)
                self.assertEqual("stale\n", report.read_text(encoding="utf-8"))

                refused, refused_output = invoke(
                    root, "--output", ".cambium/state/required_queue.yaml")
                self.assertEqual(1, refused, refused_output)
                self.assertEqual(before, queue_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
