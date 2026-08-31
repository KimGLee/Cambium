"""Inline-delivery conformance probe for one Host Adapter build.

The current Tool delivery contract has separate identity, transport, and
acknowledgement evidence.  This probe supplies the transport observation:
whether a within-budget tool result reaches the model context whole.  A server
can prove what it sent and an ack can prove which context answered, but neither
can see what the host did in between.  That gap is measured against a live host
rather than asserted.

The probe is not a unit test.  It needs a real adapter, so it prints an exact
procedure, then validates the observations that procedure returns.  What is
machine-checkable offline -- the payload shape and the registry schema --
lives in `test_host_conformance.py`.

Both controls are mandatory:

  positive  a payload of exactly `minimum_bytes` must arrive whole, proven by
            the model reporting the nonce placed at its very end;
  negative  a larger payload must be OBSERVED to be externalized or truncated.

A positive result alone is not a pass.  A probe that cannot fail cannot
certify, and the negative control is what proves this one can.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import Tools.platform.common.kblib as kblib
import inline_probe_server

REGISTRY_PATH = "Tools/host-conformance.yaml"
CONFORMANCE_VERSION = "activation-inline-v1"
PROBE_PROMPT = (
    "Call the probe tool with {\"size_bytes\": %d}. Then answer exactly two "
    "lines. First line TAIL=<the string inside the <<TAIL ...>> marker as it "
    "appears in the tool result; write TAIL=ABSENT if it is not there, and do "
    "not open any file to find it>. Second line PERSISTED=<YES if the tool "
    "result mentions persisted-output or an oversized-output notice, "
    "otherwise NO>. Use no tool other than the probe tool."
)


def load_registry(root):
    with open(os.path.join(root, REGISTRY_PATH), encoding="utf-8") as handle:
        return kblib.parse_yaml_subset(handle.read())


def procedure(root):
    """Return the exact, reproducible steps for one adapter measurement."""
    registry = load_registry(root)
    minimum = registry["minimum_bytes"]
    return {
        "conformance_version": registry["conformance_version"],
        "minimum_bytes": minimum,
        "server": "Tools/tests/inline_probe_server.py",
        "expected_tail_nonce": inline_probe_server.NONCE,
        "controls": [
            {
                "control": "positive",
                "size_bytes": minimum,
                "prompt": PROBE_PROMPT % minimum,
                "required": "TAIL equals the nonce and PERSISTED is NO",
            },
            {
                "control": "negative",
                "size_bytes": minimum * 2,
                "prompt": PROBE_PROMPT % (minimum * 2),
                "required": "TAIL is ABSENT or PERSISTED is YES",
            },
        ],
    }


def evaluate(root, positive_tail, positive_persisted, negative_tail,
             negative_persisted):
    """Judge one observed pair; both controls must hold."""
    nonce = inline_probe_server.NONCE
    findings = []
    if positive_tail != nonce:
        findings.append(
            "positive control did not deliver the trailing nonce inline; the "
            "adapter truncated or externalized a within-budget result")
    if positive_persisted:
        findings.append(
            "positive control was externalized; a within-budget result must "
            "be inlined")
    if negative_tail == nonce and not negative_persisted:
        findings.append(
            "negative control was also delivered whole, so this run cannot "
            "detect externalization and certifies nothing")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure one Host Adapter's inline tool-result delivery")
    parser.add_argument("root", help="Cambium repository root")
    parser.add_argument("--emit-plan", action="store_true",
                        help="print the exact measurement procedure as JSON")
    parser.add_argument("--positive-tail", help="TAIL reported at the budget")
    parser.add_argument("--positive-persisted", action="store_true",
                        help="the budget-sized result was externalized")
    parser.add_argument("--negative-tail", help="TAIL reported above budget")
    parser.add_argument("--negative-persisted", action="store_true",
                        help="the oversized result was externalized")
    args = parser.parse_args(argv)

    if args.emit_plan:
        print(json.dumps(procedure(args.root), indent=2, sort_keys=True))
        return 0
    if args.positive_tail is None or args.negative_tail is None:
        print("[FAIL] both --positive-tail and --negative-tail are required; "
              "a positive result alone cannot certify")
        return 1
    findings = evaluate(args.root, args.positive_tail,
                        args.positive_persisted, args.negative_tail,
                        args.negative_persisted)
    for finding in findings:
        print("[FAIL] %s" % finding)
    if findings:
        return 1
    print("[PASS] adapter meets %s at %d bytes; register it in %s with the "
          "declared clientInfo name and version range it was measured against"
          % (CONFORMANCE_VERSION, load_registry(args.root)["minimum_bytes"],
             REGISTRY_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
