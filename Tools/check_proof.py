#!/usr/bin/env python3
"""Terminal Proof completeness check script.

Rule owners:
- "12 Quality Assurance/06 Completion Terminal Audit and Final Report.md"
  (the complete Terminal Proof field list, including
   full_deterministic_results; completion conditions: the three open guidance
   counts are 0, required_authoring_gaps=0, unverified_batches=0,
   unresolved_invalidations=0, and all applicable gates pass);
- "12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md"
  (Terminal Reconciliation Rules: unresolved_invalidations must be 0).

Method:
- The required-field list comes from the top-level keys of
  Tools/schemas/terminal_proof.template.yaml (the template copies 12/06 field
  by field and is this script's single source of truth; --template overrides);
- a missing or empty proof field -> fail (Terminal Proof incomplete);
- a zero-condition field (required_authoring_gaps / unverified_batches /
  unresolved_invalidations) that is not 0 -> fail;
- a top-level proof field outside the list -> candidate (whether it is
  reasonable is a human call);
- when --ledger (Coverage Ledger) is given, cross-check: open_gaps non-empty
  while the proof claims required_authoring_gaps=0 -> fail.

Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_proof.py <proof.yaml> [--ledger coverage_ledger.yaml]
       [--template PATH] [--receipts PATH]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_proof"
TOOL_VERSION = "1.0.0"

# 12/06: fields that must be 0 among the completion conditions (the three open
# guidance counts are covered by the review of guidance_reconciliation_result
# and get no numeric assertion here)
ZERO_FIELDS = ("required_authoring_gaps", "unverified_batches",
               "unresolved_invalidations")


def main():
    ap = argparse.ArgumentParser(description="Terminal Proof completeness and zero-condition check")
    ap.add_argument("proof", help="path to the terminal proof YAML file")
    ap.add_argument("--ledger", help="Coverage Ledger YAML, for the open_gaps cross-check")
    ap.add_argument("--template",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "schemas", "terminal_proof.template.yaml"),
                    help="field-list template (default Tools/schemas/terminal_proof.template.yaml)")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    template = kblib.parse_yaml_subset(open(args.template, encoding="utf-8").read())
    required_fields = list(template.keys())

    receipts = []
    seq = 0
    proof_name = os.path.basename(args.proof)

    try:
        proof = kblib.parse_yaml_subset(open(args.proof, encoding="utf-8").read())
    except (OSError, kblib.YamlSubsetError) as exc:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-unreadable", args.proof, "fail",
            "cannot read/parse proof: %s" % exc, seq))
        kblib.write_receipts(args.receipts, receipts)
        print("check_proof: cannot read or parse %s: %s" % (args.proof, exc))
        return 1
    if not isinstance(proof, dict):
        proof = {}

    missing = []
    for field in required_fields:
        value = proof.get(field, None)
        # Note: an empty list [] is legal for list-valued fields (e.g.
        # systemic_expansions: []) and does not count as missing
        if field not in proof or value is None or value == "":
            missing.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-field-missing",
                "%s#%s" % (proof_name, field), "fail",
                "Terminal Proof is missing required field %s (12/06 field list)" % field, seq))

    zero_bad = []
    for field in ZERO_FIELDS:
        if field in missing or field not in proof:
            continue
        value = proof.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            zero_bad.append(field)
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "proof-zero-field",
                "%s#%s" % (proof_name, field), "fail",
                "zero-condition field %s = %r; the completion conditions require it to be 0 (12/06)" % (field, value), seq))

    extra = [k for k in proof if k not in required_fields]
    for field in extra:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-extra-field",
            "%s#%s" % (proof_name, field), "candidate",
            "field %s is not in the 12/06 field list (the list is an 'at least' "
            "list; whether extra fields are reasonable is a human call)"
            % field, seq))

    cross_fail = 0
    if args.ledger:
        try:
            ledger = kblib.parse_yaml_subset(open(args.ledger, encoding="utf-8").read())
        except (OSError, kblib.YamlSubsetError) as exc:
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "ledger-unreadable", args.ledger, "fail",
                "cannot read/parse Coverage Ledger: %s" % exc, seq))
            ledger = None
        if isinstance(ledger, dict):
            open_gaps = ledger.get("open_gaps") or []
            gaps_claim = proof.get("required_authoring_gaps")
            if open_gaps and gaps_claim == 0:
                cross_fail += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "proof-ledger-mismatch",
                    "%s#required_authoring_gaps" % proof_name, "fail",
                    "Coverage Ledger open_gaps has %d unclosed gap(s), but the "
                    "proof claims required_authoring_gaps=0 (02/03: the "
                    "Coverage Ledger is the authoritative record)"
                    % len(open_gaps), seq))

    if not any(r["result"] == "fail" for r in receipts):
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "proof-check-summary", proof_name, "pass",
            "fields complete (%d/%d), all zero-condition fields are 0%s" % (
                len(required_fields), len(required_fields),
                ", consistent with Coverage Ledger open_gaps" if args.ledger else ""), seq))

    print("check_proof: checking %s against %d required template field(s)" % (args.proof, len(required_fields)))
    print("  missing_fields=%d zero_condition_violations=%d extra_fields(candidate)=%d ledger_cross_failures=%d"
          % (len(missing), len(zero_bad), len(extra), cross_fail))
    for r in receipts:
        if r["result"] != "pass":
            print("  [%s %s] %s — %s" % (r["result"].upper()[:4], r["check"],
                                         r["target"], r["details"]))
    if not any(r["result"] == "fail" for r in receipts):
        print("  Conclusion: Terminal Proof completeness check passed.")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
