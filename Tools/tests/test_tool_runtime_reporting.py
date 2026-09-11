import contextlib
import io
import json
import os
import sys
import unittest


TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

from Tools.platform.common import reporting  # noqa: E402
from Tools.platform.common import kblib  # noqa: E402
from Tools.platform.agent_interface import entrypoint_loader  # noqa: E402
from Tools.platform.common.host_environment import HostEnvironmentUnavailable
from Tools.platform.common.host_environment import host_handoff


class CanonicalJsonOutputTests(unittest.TestCase):
    def test_invocation_observation_separates_ack_output_and_process_result(self):
        contract = kblib.load_yaml_file(os.path.join(
            TOOLS, "agent-interface-policy.yaml"))["output_contracts"]["json-option-object"]
        payload = {"applied": True, "next_action_error": "read-back unavailable"}
        for code, missing, ack_error, output, reliable, readable in (
                (0, [], None, payload, True, True),
                (0, ["unconsumed"], None, payload, False, True),
                (2, ["unconsumed"], None, payload, False, True),
                (1, [], None, payload, True, True),
                (1, [], "foreign ACK", payload, False, True),
                (9, [], None, payload, False, True),
                (-9, [], None, payload, False, True),
                (0, [], None, "broken JSON", True, False)):
            with self.subTest(code=code, missing=missing, ack_error=ack_error, output=output):
                raw = output.encode() if isinstance(output, str) else kblib.canonical_json_bytes(output)
                observed = reporting.observe_invocation(
                    contract, raw, code, {"json": True},
                    binding={"missing": missing, "acknowledgement_error": ack_error})
                self.assertEqual(reliable, observed["invocation_reliable"])
                self.assertEqual(readable, observed["output_reliable"])
                if readable:
                    self.assertEqual(payload, observed["stdout_json"])

    def test_complete_checker_process_is_validated_before_gate_selection(self):
        for results, code in ((["pass"], 0), (["pass", "fail"], 1),
                              (["pass", "candidate"], 2), (["candidate", "fail"], 1)):
            rows = [{"result": result} for result in results]
            self.assertIs(rows, reporting.validate_receipt_process(code, rows))
            for bad_code in (-9, 9, True, *({0, 1, 2} - {code})):
                with self.subTest(results=results, code=bad_code), self.assertRaises(ValueError):
                    reporting.validate_receipt_process(bad_code, rows)
        for malformed in (None, {}, [], [None], [{}], [{"result": "passed"}]):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                reporting.validate_receipt_process(0, malformed)

    def test_output_observation_keeps_declared_host_handoff_separate_from_payloads(self):
        contracts = kblib.load_yaml_file(os.path.join(
            TOOLS, "agent-interface-policy.yaml"))["output_contracts"]
        failure = HostEnvironmentUnavailable(
            "compiler unavailable", capability_id="static-markdown-render-v1",
            code="execution-unavailable", constructs=("mermaid-fence",))
        prior = '{"earlier_step":"completed"}\n'
        handoff = host_handoff(failure.diagnostic(), prior_output=prior)
        for name in ("json-option-receipts", "receipt-publication", "text-report"):
            with self.subTest(contract=name):
                observed = reporting.observe_tool_output(
                    contracts[name], kblib.canonical_json_bytes(handoff), 0,
                    {"json": True}, host_boundary=True)
                self.assertEqual("parsed", observed["stdout_parse"])
                self.assertFalse(observed["output_reliable"])
                self.assertEqual(handoff, observed["stdout_json"])
                self.assertEqual(prior, observed["stdout_json"]["prior_output"])
                self.assertNotIn("applied", observed["stdout_json"])
                self.assertNotIn("publication", observed["stdout_json"])
        malformed = (
            {key: value for key, value in handoff.items() if key != "host_preparation"},
            {**handoff, "host_environment": {"message": "missing identity"}},
            {**handoff, "host_preparation": {"capability_id": "invented"}},
            {**handoff, "applied": False},
        )
        for payload in malformed:
            with self.subTest(malformed=payload):
                observed = reporting.observe_tool_output(
                    contracts["text-report"], kblib.canonical_json_bytes(payload), 1,
                    {}, host_boundary=True)
                self.assertEqual("unparseable", observed["stdout_parse"])
                self.assertFalse(observed["output_reliable"])
        undeclared = reporting.observe_tool_output(
            contracts["json-option-object"], kblib.canonical_json_bytes(handoff), 1,
            {"json": True})
        self.assertEqual("unparseable", undeclared["stdout_parse"])
        normal = {"status": "await-host", "next_action": {"kind": "host-input"}}
        observed = reporting.observe_tool_output(
            contracts["json-option-object"], kblib.canonical_json_bytes(normal), 0,
            {"json": True}, host_boundary=True)
        self.assertEqual(normal, observed["stdout_json"])
        self.assertTrue(observed["output_reliable"])
        publication = kblib.ReceiptPublication()
        publication.outcome = "present"
        uncertain = reporting.publication_result(publication, status="recorded")
        observed = reporting.observe_tool_output(
            contracts["receipt-publication"], kblib.canonical_json_bytes(uncertain), 0, {})
        self.assertEqual("parsed", observed["stdout_parse"])
        self.assertFalse(observed["output_reliable"])

    def test_publication_facts_keep_append_confirmation_and_business_result_separate(self):
        # One owner matrix; producer tests only prove their connection to it.
        cases = (
            ("not-attempted", False, False, None, "planned", False, "planned"),
            ("not-attempted", False, False, "refused", "invalid", False, "invalid"),
            ("absent", False, False, "append failed", "invalid", False, "invalid"),
            ("present", False, False, "fsync failed", "recorded", True, "uncertain"),
            ("uncertain", False, False, "partial bytes", "recorded", None, "uncertain"),
            ("present", False, False, None, "recorded", True, "uncertain"),
            ("present", True, False, None, "recorded", True, "recorded"),
            ("not-attempted", True, True, None, "already-present", False, "already-present"),
        )
        for outcome, confirmed, reused, error, status, applied, expected_status in cases:
            with self.subTest(outcome=outcome, confirmed=confirmed, reused=reused, error=error):
                publication = kblib.ReceiptPublication()
                publication.outcome = outcome
                publication.confirmed = confirmed
                publication.error = OSError(error) if error else None
                result = reporting.publication_result(
                    publication, status=status,
                    result="fail", verdict="changes-required")
                self.assertIs(applied, result["applied"])
                self.assertEqual(expected_status, result["status"])
                self.assertEqual(outcome, result["publication"]["append"])
                self.assertEqual("confirmed" if confirmed else "unconfirmed",
                                 result["publication"]["record_confirmation"])
                self.assertEqual(reused, result["publication"]["reused"])
                self.assertEqual([error] if error else [], result["errors"])
                self.assertEqual(("fail", "changes-required"),
                                 (result["result"], result["verdict"]))
                self.assertEqual(expected_status != "uncertain",
                                 reporting.publication_result_reliable(result))

    def test_publication_decoder_rejects_contradictory_or_incomplete_facts(self):
        publication = kblib.ReceiptPublication()
        publication.outcome = "present"
        publication.confirmed = True
        original = reporting.publication_result(publication, status="recorded")
        malformed = (
            {**original, "applied": False},
            {**original, "errors": "hidden error"},
            {**original, "errors": ["late error"]},
            {**original, "publication": {**original["publication"], "append": "unknown"}},
            {**original, "publication": {**original["publication"], "reused": True}},
            {**original, "publication": {"append": "present"}},
        )
        for value in malformed:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    reporting.validate_publication_result(value)
        self.assertIs(original, reporting.validate_publication_result(original))
        # A same-page dispatch reports independent append facts; there is no
        # aggregate applied flag that could conceal a failed later item.
        publication.confirmed = False
        uncertain = reporting.publication_result(publication, status="recorded")
        self.assertTrue(reporting.publication_result_reliable([original]))
        self.assertFalse(reporting.publication_result_reliable([original, uncertain]))
        for collection in ([], [original, malformed[0]], [[original]]):
            with self.subTest(collection=collection), self.assertRaises(ValueError):
                reporting.validate_publication_result(collection)

    def test_host_handoff_is_not_a_receipt_or_a_claim_that_nothing_was_written(self):
        failure = HostEnvironmentUnavailable("compiler unavailable", capability_id="render",
                                             code="execution-unavailable")
        @reporting.host_environment_boundary
        def operation():
            raise failure
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(1, operation())
        result = json.loads(output.getvalue())
        self.assertEqual("await-host", result["status"])
        self.assertEqual(failure.diagnostic(), result["host_environment"])
        self.assertIsNone(result["host_preparation"]["arguments"])
        @reporting.host_environment_boundary
        def after_output():
            print("earlier operation output")
            raise failure
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(1, after_output())
        self.assertEqual("earlier operation output\n", json.loads(output.getvalue())["prior_output"])
        @reporting.host_environment_boundary
        def invalid():
            raise ValueError("invalid evidence")
        with self.assertRaisesRegex(ValueError, "invalid evidence"):
            invalid()

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
            "prepare_audit_plan",
        )
        for name in producers:
            with self.subTest(producer=name):
                source = entrypoint_loader.describe_entrypoint(
                    name, TOOLS).implementation_source
                self.assertIn("reporting.write_canonical_json(", source)
                self.assertNotIn("def _emit(", source)

    def test_manual_producer_outputs_share_json_and_human_publication_facts(self):
        receipt = {"z": 2, "receipt_id": "receipt-1", "a": "文字"}
        publication = kblib.ReceiptPublication()
        publication.outcome = "present"
        publication.confirmed = True
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            payload = reporting.write_publication_result(
                publication, json_output=True, status="recorded", receipts=[receipt])
        self.assertEqual([receipt], json.loads(output.getvalue())["receipts"])
        self.assertEqual(payload, json.loads(output.getvalue()))
        human = io.StringIO()
        with contextlib.redirect_stdout(human):
            reporting.write_publication_result(
                publication, json_output=False, status="recorded", receipts=[receipt])
        self.assertIn("append=present; record confirmation=confirmed", human.getvalue())
        self.assertIn("receipt: receipt-1", human.getvalue())
        publication.confirmed = False
        publication.error = OSError("flush failed")
        diagnostic = io.StringIO()
        with contextlib.redirect_stderr(diagnostic):
            reporting.write_publication_result(
                publication, json_output=False, status="invalid")
        self.assertIn("[UNCERTAIN]", diagnostic.getvalue())
        self.assertIn("append=present", diagnostic.getvalue())
        self.assertIn("flush failed", diagnostic.getvalue())


if __name__ == "__main__":
    unittest.main()
