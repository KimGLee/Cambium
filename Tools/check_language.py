#!/usr/bin/env python3
"""Chinese-first language scan (candidate-only; never fails).

This script implements the agent-atlas profile's registered language scan
(Chinese-first contract, see profiles/agent-atlas/language-contract.md); it
is profile tooling, not a kernel gate.

The contract's acceptance-and-audit rules limit what automation may decide:
automated checks may surface signals such as English-only heading
candidates, but character ratios and English density can only produce
review candidates and must never auto-fail, because code, schemas, source
identity, and interview-English sections may be legitimate. Final judgement
requires a scoped human or model review with recorded exceptions. Every
finding from this script is therefore result=candidate; it never emits fail.

Checks:
a) reader-facing H2/H3 headings that are entirely English (no Chinese
   characters) and lack a `（Chinese gloss）` suffix -- the contract
   requires English headings to use the `English Title（Chinese gloss）`
   format;
b) reverse bilingual headings in the form `Chinese（English）` -- the
   contract forbids the reverse format; the English identity must sit
   outside the parentheses;
c) missing Chinese gloss after an English term's first occurrence in body
   text: NOT checked. That judgement depends on semantic boundaries
   ("first meaningful occurrence", "protected English") that cannot be
   decided deterministically and is left to human/model review.

Exemptions: only from --exempt COMPONENT (repeatable; default: none) --
files whose path contains an exempted component are skipped entirely.
Heading samples inside code blocks are always skipped.

Exit codes: 0 = no candidates, 2 = candidates found (this script never
returns 1).

Usage: python3 check_language.py <vault_root> [--scope SUBPATH]
       [--exempt COMPONENT ...] [--receipts PATH]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_language"
TOOL_VERSION = "1.0.0"

CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
# Reverse bilingual: starts with Chinese (proper nouns allowed in between),
# with pure English / digits / common punctuation inside the parentheses.
REVERSE_RE = re.compile(
    r"^(?P<zh>[^（()]*[一-鿿][^（()]*)（(?P<en>[A-Za-z][A-Za-z0-9 ,./&+'\-]*)）$")


def has_cjk(text):
    return bool(CJK_RE.search(text))


def is_exempt(rel, components):
    parts = rel.replace(os.sep, "/").split("/")
    return any(comp in parts for comp in components)


def main():
    ap = argparse.ArgumentParser(
        description="Chinese-first language scan (produces candidates only)")
    ap.add_argument("vault_root", help="vault root directory")
    ap.add_argument("--scope", help="only scan .md files under this subpath")
    ap.add_argument("--exempt", action="append", default=[],
                    metavar="COMPONENT",
                    help="exempt files whose path contains this component "
                         "(repeatable; default: none)")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    exempt_components = [e.strip("/") for e in args.exempt if e.strip("/")]

    receipts = []
    seq = 0
    counts = {"files": 0, "exempt_files": 0, "headings": 0,
              "english_only": 0, "reverse_bilingual": 0}

    for full, rel in kblib.iter_md_files(args.vault_root, args.scope):
        if is_exempt(rel, exempt_components):
            counts["exempt_files"] += 1
            continue
        counts["files"] += 1
        rel_disp = rel.replace(os.sep, "/")
        text = kblib.strip_code(open(full, encoding="utf-8", errors="replace").read())
        for lineno, level, heading in kblib.headings_of(text):
            if level not in (2, 3):  # only reader-facing H2/H3 are checked
                continue
            counts["headings"] += 1
            where = "%s:%d" % (rel_disp, lineno)
            if not has_cjk(heading):
                counts["english_only"] += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "language-english-only-heading", where,
                    "candidate",
                    "H%d is English-only with no （Chinese gloss） suffix: %r; "
                    "the language contract requires reader-facing English "
                    "headings to use `English Title（Chinese gloss）`; whether "
                    "this is a legitimate exception is a human call"
                    % (level, heading), seq))
                continue
            m = REVERSE_RE.match(heading.strip())
            if m:
                counts["reverse_bilingual"] += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "language-reverse-bilingual-heading", where,
                    "candidate",
                    "H%d uses the reverse bilingual format `Chinese（English）`: "
                    "%r; the language contract requires the English identity "
                    "outside the parentheses (`English（Chinese）`); possible "
                    "false positive, human judgement required"
                    % (level, heading), seq))

    total = counts["english_only"] + counts["reverse_bilingual"]
    if total == 0:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "language-check-summary",
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "no language candidates found (english_only=0, "
            "reverse_bilingual=0; %d files exempted)"
            % counts["exempt_files"], seq))

    print("check_language: scanned %(files)d files (plus %(exempt_files)d "
          "exempted), %(headings)d H2/H3 headings" % counts)
    print("  candidates: english_only_heading=%(english_only)d "
          "reverse_bilingual_heading=%(reverse_bilingual)d (always candidate; "
          "final judgement per the language contract goes to human/model "
          "review)" % counts)
    shown = 0
    for r in receipts:
        if r["result"] == "candidate" and shown < 20:
            print("  [CAND %s] %s" % (r["check"], r["target"]))
            shown += 1
    if total > shown:
        print("  ... %d more candidates in receipts" % (total - shown))

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
