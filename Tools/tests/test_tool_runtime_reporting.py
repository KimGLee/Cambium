import contextlib
import io
import os
import sys
import unittest


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

from Tools.platform.common import reporting  # noqa: E402
from Tools.platform.agent_interface import entrypoint_loader  # noqa: E402


class CanonicalJsonOutputTests(unittest.TestCase):
    def test_writer_preserves_the_exact_canonical_stdout_bytes(self):
        output = io.StringIO()
        payload = {"z": [2, 1], "a": {"value": "文字"}}

        reporting.write_canonical_json(payload, stream=output)

        self.assertEqual(
            '{"a":{"value":"文字"},"z":[2,1]}\n',
            output.getvalue(),
        )

    def test_array_writer_preserves_order_and_exact_canonical_bytes(self):
        output = io.StringIO()
        payload = ({"z": 2, "a": "文字"}, {"result": "pass"})

        reporting.write_canonical_json_array(payload, stream=output)

        self.assertEqual(
            '[{"a":"文字","z":2},{"result":"pass"}]\n',
            output.getvalue(),
        )

    def test_array_writer_can_preserve_an_unanswered_empty_stdout(self):
        for payload in (None, [], ()):
            with self.subTest(payload=payload):
                output = io.StringIO()
                reporting.write_canonical_json_array(
                    payload, stream=output, omit_if_empty=True)
                self.assertEqual("", output.getvalue())

    def test_array_writer_emits_empty_array_unless_asked_to_omit_it(self):
        output = io.StringIO()

        reporting.write_canonical_json_array([], stream=output)

        self.assertEqual("[]\n", output.getvalue())


class FindingSetTests(unittest.TestCase):
    def test_findings_preserve_rows_and_offer_common_projections(self):
        findings = reporting.FindingSet()
        findings.add("shape", "A.md", "pass", "valid")
        findings.add("shape", "B.md", "fail", "invalid")

        self.assertEqual(1, findings.count("pass"))
        self.assertEqual(1, findings.count("fail"))
        self.assertEqual(
            [{"check": "shape", "target": "B.md", "result": "fail",
              "details": "invalid"}],
            findings.failures(),
        )


class JsonReceiptCollectorTests(unittest.TestCase):
    def test_json_wrappers_preserve_each_current_runner_verdict(self):
        for code in (0, 1, 2):
            with self.subTest(wrapper="collector", code=code):
                collector = reporting.JsonReceiptCollector(emit_empty=True)
                actual = collector.run(
                    lambda code=code: code,
                    stdout=io.StringIO(), stderr=io.StringIO())
                self.assertEqual(code, actual)

            with self.subTest(wrapper="redirected-checker", code=code):
                capture = reporting.RedirectedJsonReceipts()
                projected = io.StringIO()
                human = io.StringIO()
                with contextlib.redirect_stdout(projected), \
                        contextlib.redirect_stderr(human):
                    capture.begin(True)
                    actual = reporting.run_redirected_json(
                        capture, lambda code=code: code)
                self.assertEqual(code, actual)

    def test_writer_keeps_empty_stdout_when_no_receipt_was_produced(self):
        output = io.StringIO()
        human = io.StringIO()
        collector = reporting.JsonReceiptCollector()
        code = collector.run(lambda: (print("refused"), 1)[1],
                             stdout=output, stderr=human)
        self.assertEqual(1, code)
        self.assertEqual("", output.getvalue())
        self.assertEqual("refused\n", human.getvalue())

    def test_scanner_can_publish_an_empty_array(self):
        output = io.StringIO()
        collector = reporting.JsonReceiptCollector(emit_empty=True)
        collector.run(lambda: 0, stdout=output, stderr=io.StringIO())
        self.assertEqual("[]\n", output.getvalue())

    def test_each_run_resets_the_collector(self):
        collector = reporting.JsonReceiptCollector()
        first = io.StringIO()
        second = io.StringIO()

        def produce():
            collector.record([{"result": "pass"}])
            return 0

        collector.run(produce, stdout=first, stderr=io.StringIO())
        collector.run(lambda: 1, stdout=second, stderr=io.StringIO())
        self.assertIn('"result":"pass"', first.getvalue())
        self.assertEqual("", second.getvalue())


class RedirectedJsonReceiptsTests(unittest.TestCase):
    def test_begin_record_finish_restores_stdout(self):
        capture = reporting.RedirectedJsonReceipts()
        original_stdout = sys.stdout
        projected = io.StringIO()
        human = io.StringIO()
        try:
            sys.stdout = projected
            original_stderr = sys.stderr
            sys.stderr = human
            try:
                capture.begin(True)
                print("human")
                capture.record([{"result": "pass"}])
                capture.finish(True)
                self.assertIs(sys.stdout, projected)
            finally:
                sys.stderr = original_stderr
        finally:
            sys.stdout = original_stdout
        self.assertEqual("human\n", human.getvalue())
        self.assertEqual('[{"result":"pass"}]\n', projected.getvalue())

    def test_unanswered_run_restores_stdout_without_publishing_receipts(self):
        capture = reporting.RedirectedJsonReceipts()
        original_stdout = sys.stdout
        projected = io.StringIO()
        human = io.StringIO()
        try:
            sys.stdout = projected
            original_stderr = sys.stderr
            sys.stderr = human
            try:
                capture.begin(True)
                print("human")
                capture.record([{"result": "fail"}])
                capture.finish(False)
                self.assertIs(sys.stdout, projected)
            finally:
                sys.stderr = original_stderr
        finally:
            sys.stdout = original_stdout
        self.assertEqual("human\n", human.getvalue())
        self.assertEqual("", projected.getvalue())


class CheckerReportingBoundaryTests(unittest.TestCase):
    CHECKERS = (
        "check_structure",
        "check_batch_close",
        "check_boundary_contract",
        "check_proof",
        "check_links",
        "check_page_contract",
    )

    def test_checkers_delegate_json_projection_to_the_shared_reporter(self):
        for name in self.CHECKERS:
            with self.subTest(checker=name):
                module = entrypoint_loader.load_tool_implementation(
                    name, TOOLS)
                self.assertIsInstance(
                    module._JSON_REPORTER,
                    reporting.RedirectedJsonReceipts,
                )
                for legacy_name in (
                        "_json_begin", "_json_enabled", "_json_record",
                        "_json_finish", "_JSON_STDOUT", "_JSON_RECEIPTS"):
                    self.assertFalse(hasattr(module, legacy_name), legacy_name)

    def test_collecting_checkers_delegate_to_the_shared_collector(self):
        for name in ("check_vocab", "check_residual_content"):
            with self.subTest(checker=name):
                module = entrypoint_loader.load_tool_implementation(
                    name, TOOLS)
                self.assertIsInstance(
                    module._JSON_REPORTER,
                    reporting.JsonReceiptCollector,
                )
                self.assertFalse(hasattr(module, "_emit_json_receipts"))

    def test_transaction_writers_have_no_local_receipt_collector(self):
        for name in ("adopt_standards", "apply_delta"):
            with self.subTest(writer=name):
                source = entrypoint_loader.describe_entrypoint(
                    name, TOOLS).implementation_source
                self.assertIn(
                    "_JSON_REPORTER = reporting.JsonReceiptCollector()",
                    source,
                )
                for legacy_name in (
                        "_JSON_RECEIPTS", "def _record_receipts(",
                        "def emit_json_receipts(",
                        "def _run_reporting_json("):
                    self.assertNotIn(legacy_name, source)

    def test_queue_writers_delegate_nonempty_array_projection(self):
        for name in (
                "check_queue", "update_queue", "update_task",
                "register_amendment"):
            with self.subTest(writer=name):
                source = entrypoint_loader.describe_entrypoint(
                    name, TOOLS).implementation_source
                self.assertIn(
                    "reporting.write_canonical_json_array("
                    "produced, omit_if_empty=True)",
                    source,
                )
                self.assertNotIn("def _emit_json_receipts(", source)

    def test_object_producers_share_the_canonical_json_writer(self):
        producers = (
            "record_rendering_verification",
            "record_changed_scope_evidence",
            "record_substantive_review",
            "record_batch_page_review",
            "complete_audit_receipt",
            "prepare_audit_plan",
        )
        for name in producers:
            with self.subTest(producer=name):
                source = entrypoint_loader.describe_entrypoint(
                    name, TOOLS).implementation_source
                self.assertIn("reporting.write_canonical_json(", source)
                self.assertNotIn("def _emit(", source)

    def test_manual_producer_outputs_preserve_json_and_human_bytes(self):
        cases = (
            ("record_gate_attestation",
             "[PASS] manual Gate evidence recorded: receipt-1\n"),
            ("record_batch_review",
             "[PASS] batch-review wrapper recorded: receipt-1\n"),
        )
        receipt = {"z": 2, "receipt_id": "receipt-1", "a": "文字"}
        expected_json = \
            '[{"a":"文字","receipt_id":"receipt-1","z":2}]\n'
        for name, expected_human in cases:
            with self.subTest(producer=name):
                module = entrypoint_loader.load_tool_implementation(
                    name, TOOLS)
                json_output = io.StringIO()
                with contextlib.redirect_stdout(json_output):
                    module._output(receipt, True)
                self.assertEqual(expected_json, json_output.getvalue())

                human_output = io.StringIO()
                with contextlib.redirect_stdout(human_output):
                    module._output(receipt, False)
                self.assertEqual(expected_human, human_output.getvalue())


if __name__ == "__main__":
    unittest.main()
