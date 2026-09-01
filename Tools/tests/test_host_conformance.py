from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS / "tests"))
sys.path.insert(0, str(TOOLS))

import Tools.execution.context_delivery.card_activation as card_activation
import host_conformance_probe
import inline_probe_server


class InlineProbePayloadTests(unittest.TestCase):
    def test_payload_is_exactly_the_requested_size(self):
        for size in (512, 4096, 49152, 65536):
            self.assertEqual(
                size, len(inline_probe_server.build_payload(size).encode(
                    "utf-8")))

    def test_the_nonce_sits_at_the_very_end(self):
        # A leading preview is the failure mode this probe exists to catch, so
        # the evidence token must be the last thing a truncating host drops.
        payload = inline_probe_server.build_payload(49152)
        self.assertIn(inline_probe_server.NONCE, payload[-64:])
        self.assertNotIn(inline_probe_server.NONCE, payload[:-64])


class ConformanceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = host_conformance_probe.load_registry(ROOT)

    def test_registry_minimum_equals_the_protocol_budget(self):
        # A registry that certified a smaller result than the protocol
        # delivers would pass adapters that cannot carry a real piece.
        self.assertEqual(card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES,
                         self.registry["minimum_bytes"])

    def test_only_measured_delivery_channels_claim_transport_assurance(self):
        channels = {
            row["channel_id"]: row for row in self.registry["channels"]
        }

        self.assertFalse(
            channels["agent-native-file-read"]["proves_transport"])
        for channel_id in ("inline-mcp", "remote-bundle"):
            self.assertTrue(channels[channel_id]["proves_transport"])
            self.assertEqual(
                card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES,
                channels[channel_id]["minimum_bytes"])

    def test_every_adapter_row_is_closed_and_measured(self):
        self.assertTrue(self.registry["adapters"])
        for adapter in self.registry["adapters"]:
            for field in ("client_name", "version_range_from",
                          "version_range_before", "measured_inline_bytes",
                          "measured_externalized_bytes", "conformance_version",
                          "measured_on", "evidence"):
                self.assertIn(field, adapter)
            self.assertEqual(host_conformance_probe.CONFORMANCE_VERSION,
                             adapter["conformance_version"])
            self.assertEqual("forbidden",
                             adapter["externalization_below_limit"])
            self.assertGreaterEqual(adapter["measured_inline_bytes"],
                                    self.registry["minimum_bytes"])
            # The negative control has to sit above the positive one, or the
            # row records no discrimination at all.
            self.assertGreater(adapter["measured_externalized_bytes"],
                               adapter["measured_inline_bytes"])


class ProbeJudgementTests(unittest.TestCase):
    def evaluate(self, **overrides):
        arguments = {
            "positive_tail": inline_probe_server.NONCE,
            "positive_persisted": False,
            "negative_tail": "ABSENT",
            "negative_persisted": True,
        }
        arguments.update(overrides)
        return host_conformance_probe.evaluate(ROOT, **arguments)

    def test_both_controls_holding_is_a_pass(self):
        self.assertEqual([], self.evaluate())

    def test_a_truncated_positive_control_fails(self):
        findings = self.evaluate(positive_tail="ABSENT")
        self.assertTrue(any("within-budget" in finding
                            for finding in findings), findings)

    def test_an_externalized_positive_control_fails(self):
        findings = self.evaluate(positive_persisted=True)
        self.assertTrue(findings)

    def test_a_probe_that_cannot_detect_externalization_certifies_nothing(self):
        findings = self.evaluate(negative_tail=inline_probe_server.NONCE,
                                 negative_persisted=False)
        self.assertTrue(any("certifies nothing" in finding
                            for finding in findings), findings)

    def test_plan_names_both_controls_and_the_budget(self):
        plan = host_conformance_probe.procedure(ROOT)
        self.assertEqual(
            ["positive", "negative"],
            [control["control"] for control in plan["controls"]])
        self.assertEqual(card_activation.MAX_ACTIVATION_PIECE_ENVELOPE_BYTES,
                         plan["controls"][0]["size_bytes"])
        self.assertGreater(plan["controls"][1]["size_bytes"],
                           plan["controls"][0]["size_bytes"])


if __name__ == "__main__":
    unittest.main()
