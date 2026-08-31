"""K12 owns one machine-readable Batch-close Closed List."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest


TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import Tools.execution.audit.batch_close_contract as contract  # noqa: E402
import Tools.execution.audit.check_batch_close as check_batch_close  # noqa: E402
import Tools.execution.task_runtime.queue_runtime.close_gate as close_gate  # noqa: E402


class RegistryShapeTests(unittest.TestCase):

    def document(self):
        return copy.deepcopy(contract.load_batch_close_closed_list())

    def test_shipped_registry_is_the_current_ordered_eight_member_contract(self):
        document = self.document()
        member_ids = contract.validate_batch_close_closed_list(document)

        self.assertEqual(8, len(member_ids))
        self.assertEqual(
            tuple(row["member_id"] for row in document["members"]),
            member_ids)
        self.assertEqual(member_ids, contract.CLOSED_LIST_EVIDENCE_FIELDS)
        self.assertEqual("wiki_link_resolution", member_ids[0])
        self.assertEqual("manifest_page_contract", member_ids[-1])

    def test_registry_order_is_preserved_in_the_machine_projection(self):
        document = self.document()
        document["members"][1], document["members"][2] = \
            document["members"][2], document["members"][1]
        projected = contract.validate_batch_close_closed_list(document)

        self.assertEqual(document["members"][1]["member_id"], projected[1])
        self.assertEqual(document["members"][2]["member_id"], projected[2])

    def test_duplicate_or_open_member_shape_is_rejected(self):
        duplicate = self.document()
        duplicate["members"].append(copy.deepcopy(duplicate["members"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate.*member_id"):
            contract.validate_batch_close_closed_list(duplicate)

        open_shape = self.document()
        open_shape["members"][0]["tool"] = "check_links"
        with self.assertRaisesRegex(
                ValueError,
                "fields are not closed or do not bind exactly one producer"):
            contract.validate_batch_close_closed_list(open_shape)

    def test_missing_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(OSError):
                contract.load_batch_close_closed_list(root)


class SingleAuthorityTests(unittest.TestCase):

    def test_producer_and_consumer_do_not_redeclare_the_current_tuple(self):
        producer = (TOOLS / "execution/audit/check_batch_close.py").read_text(
            encoding="utf-8")
        consumer = (
            TOOLS / "execution/task_runtime/queue_runtime/close_gate.py"
        ).read_text(
            encoding="utf-8")

        self.assertNotIn(
            "check_queue.CLOSED_LIST_EVIDENCE_FIELDS", producer)
        self.assertIn(
            "batch_close_contract.CLOSED_LIST_EVIDENCE_FIELDS", producer)
        self.assertNotIn("CLOSED_LIST_EVIDENCE_FIELDS = (", consumer)
        self.assertNotIn("len(rows) != 8", consumer)

    def test_k12_prose_references_but_does_not_repeat_the_machine_closed_set(self):
        prose = (REPO / "kernel/K12 Quality Assurance/"
                 "09 Batch-close Closed List.md").read_text(encoding="utf-8")
        module_index = (
            REPO / "kernel/K12 Quality Assurance Standard.md"
        ).read_text(encoding="utf-8")

        self.assertIn("batch-close-closed-list.yaml", prose)
        self.assertIn("batch-close-closed-list.yaml", module_index)
        self.assertNotIn("1. Wiki link missing", prose)
        self.assertNotIn("the following eight items", prose)


class BatchCloseToolPureChecks(unittest.TestCase):
    """Tool-owned projections stay fast and separate from runtime ceremony."""

    @staticmethod
    def summary(config_fingerprint="sha256:" + "b" * 64):
        return {
            "tool": "fixture_residual",
            "tool_version": "1.0.0",
            "check": "residual-content-summary",
            "scan_id": "fixture-residuals",
            "config_fingerprint": config_fingerprint,
            "positive_control_result": "passed",
            "positive_control_mode": "production-classifier",
            "positive_control_count": 2,
            "positive_control_fingerprint": "sha256:" + "c" * 64,
            "result": "pass",
        }

    def test_candidate_rows_do_not_replace_the_bound_summary(self):
        candidate = {
            "tool": "fixture_residual",
            "tool_version": "1.0.0",
            "check": "residual-content-candidate",
            "result": "candidate",
        }
        self.assertEqual(
            [], check_batch_close._positive_control_binding_errors(
                {"receipts": [self.summary()]},
                {"receipts": [candidate, self.summary()]},
            ))

    def test_control_and_production_bind_the_admitted_config(self):
        errors = check_batch_close._positive_control_binding_errors(
            {"receipts": [self.summary("sha256:" + "d" * 64)]},
            {"receipts": [self.summary("sha256:" + "d" * 64)]},
            expected_binding={
                "scan_id": "fixture-residuals",
                "config_fingerprint": "sha256:" + "e" * 64,
            },
        )
        self.assertEqual(2, len(errors), errors)
        self.assertTrue(all(
            "config_fingerprint" in error and
            "admitted Profile contract" in error for error in errors
        ))

    def test_positive_control_pair_rejects_missing_or_drifted_identity(self):
        baseline = self.summary("sha256:" + "d" * 64)
        cases = []

        missing = copy.deepcopy(baseline)
        missing.pop("positive_control_result")
        cases.append(("missing-control-result", missing, baseline))

        foreign_scan = copy.deepcopy(baseline)
        foreign_scan["scan_id"] = "foreign-scan"
        cases.append(("foreign-scan", baseline, foreign_scan))

        drifted_config = copy.deepcopy(baseline)
        drifted_config["config_fingerprint"] = "sha256:" + "e" * 64
        cases.append(("config-drift", baseline, drifted_config))

        drifted_controls = copy.deepcopy(baseline)
        drifted_controls["positive_control_fingerprint"] = \
            "sha256:" + "f" * 64
        cases.append(("classifier-drift", baseline, drifted_controls))

        for name, control, production in cases:
            with self.subTest(name=name):
                errors = check_batch_close._positive_control_binding_errors(
                    {"receipts": [control]},
                    {"receipts": [production]},
                    expected_binding={
                        "scan_id": "fixture-residuals",
                        "config_fingerprint": "sha256:" + "d" * 64,
                    },
                )
                self.assertTrue(errors, name)

    def test_graph_projection_is_canonical_and_json_is_not_an_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for parent in ("z-last", "a-first"):
                path = root / parent / "Same.md"
                path.parent.mkdir()
                path.write_text("# Same\n", encoding="utf-8")
            (root / "Graph Source.md").write_text(
                "# Graph Source\n\n[[z-last/Same]] [[Missing]] [[Same]]\n",
                encoding="utf-8",
            )
            ordinary = root / "application-data.json"
            ordinary.write_text("42", encoding="utf-8")
            example = root / "JSON Example.md"
            example.write_text(
                "# JSON Example\n\n```json\n42\n```\n", encoding="utf-8"
            )

            first, first_json = check_batch_close._markdown_graph_projection(root)
            ordinary.write_text('"changed"', encoding="utf-8")
            example.write_text(
                "# JSON Example\n\n```json\n\"changed\"\n```\n",
                encoding="utf-8",
            )
            second, second_json = check_batch_close._markdown_graph_projection(root)
            result = check_batch_close._graph_and_basename_check(root)

        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertNotIn("application-data.json", first_json)
        self.assertEqual(
            ["z-last/Same"],
            [
                edge["resolved_target"]
                for edge in first["resolved_edges"]
                if edge["source"] == "Graph Source"
            ],
        )
        self.assertEqual(
            ["ambiguous", "missing"],
            sorted(
                edge["status"] for edge in first["unresolved_edges"]
                if edge["source"] == "Graph Source"
            ),
        )
        duplicate = next(
            row for row in result["candidates"]
            if row["check"] == "duplicate-markdown-basename"
        )
        self.assertIn("a-first/Same.md", duplicate["details"])
        self.assertIn("z-last/Same.md", duplicate["details"])


if __name__ == "__main__":
    unittest.main()
