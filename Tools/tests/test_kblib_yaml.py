"""The canonical YAML emitter's quoting rule, against the real grammar.

`canonical_yaml` self-checks by re-reading its own output through
`parse_yaml_subset`, which is deliberately more permissive than YAML.
That check proves the module is self-consistent; it cannot prove the
bytes are YAML. These tests hold the emitter to the spec's own rule for
what may begin a plain scalar, which is what a third-party reader
enforces.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kblib  # noqa: E402


# YAML 1.2 `c-indicator`. A plain scalar may not begin with any of them,
# except that `-`, `?` and `:` are allowed when a non-space follows.
ALWAYS = ",[]{}#&*!|>'\"%@`"
ONLY_ALONE = "-?:"


class PlainScalarHeadTests(unittest.TestCase):
    def test_an_indicator_head_is_never_left_bare(self):
        for head in ALWAYS:
            value = head + "tail"
            with self.subTest(value=value):
                self.assertNotEqual(kblib._yaml_scalar(value)[0], head)

    def test_the_conditional_indicators_are_quoted_only_when_alone(self):
        for head in ONLY_ALONE:
            with self.subTest(head=head):
                self.assertNotEqual(kblib._yaml_scalar(head), head)
                self.assertNotEqual(kblib._yaml_scalar(head + " x"), head + " x")

    def test_an_ordinary_value_starting_with_a_dash_stays_bare(self):
        # `--check` and friends are legal plain scalars; quoting them
        # would rewrite artifacts for no reason.
        for value in ("--check", "-1x", "-name"):
            with self.subTest(value=value):
                self.assertEqual(kblib._yaml_scalar(value), value)

    def test_the_two_shapes_this_rule_was_written_for(self):
        # The npm scope in the dsh registration, and the argparse `nargs`
        # value that made the shipped CLI contract unreadable.
        self.assertEqual(kblib._yaml_scalar("@deepseek-ai/dsh-mcp-client"),
                         '"@deepseek-ai/dsh-mcp-client"')
        self.assertEqual(kblib._yaml_scalar("?"), '"?"')


class DocumentRoundTripTests(unittest.TestCase):
    def test_a_document_carrying_indicator_values_round_trips(self):
        document = {
            "name": "@deepseek-ai/dsh-mcp-client",
            "nargs": "?",
            "flag": "--check",
            "nested": {"star": "*ref", "pct": "%dir"},
            "items": ["!tag", ">fold", "plain"],
        }

        self.assertEqual(
            kblib.parse_yaml_subset(kblib.canonical_yaml(document)), document)

    def test_every_rendered_value_is_quoted_or_starts_outside_the_set(self):
        document = {"k%d" % index: head + "tail"
                    for index, head in enumerate(ALWAYS)}

        for line in kblib.canonical_yaml(document).splitlines():
            _, _, value = line.partition(": ")
            quoted = (len(value) >= 2 and value[0] == value[-1]
                      and value[0] in "\"'")
            with self.subTest(line=line):
                # A quoted scalar legitimately opens with its own quote;
                # what must never appear is a *plain* scalar opening with
                # an indicator.
                self.assertTrue(quoted or value[:1] not in ALWAYS)


if __name__ == "__main__":
    unittest.main()
