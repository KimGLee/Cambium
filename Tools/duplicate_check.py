#!/usr/bin/env python3
"""Cross-file duplicate block detection.

Purpose: paragraph-level similarity scan over all .md files in the vault to
find copied passages across files that may violate the Cross-domain Rule
Registry (see kernel/K00 Standards Control/11 Standards Map and Rule Registry.md).
Output is candidates only; whether
a finding is an actual violation is a human call, and candidates are
digested through the maintenance-run candidates pool.

Invocation tier (v2.0): vault-wide by default, used by maintenance runs and
governance tasks; no longer invoked at batch or single-page level (batch
close keeps only the basename-level duplicate candidates in the Batch-close
Closed List, see K12/09).

--scope SUBPATH: only report similar pairs where at least one side lives
under the subpath (the vault-wide index is still built, so pairs between
in-scope files and the rest of the vault are not missed).

Method and thresholds:
- paragraphs are split on blank lines; only paragraphs >= 40 characters are
  considered;
- similarity: 12-character sliding shingle sets; report when Jaccard > 0.5
  or containment > 0.7;
- automatic exclusions: files whose path contains a component given via
  --exclude (repeatable; defaults to the single component `legacy`, the
  conventional name for a frozen-snapshot area, which a vault need not
  have); paragraphs dominated by link lists (lines starting with [[
  make up > 60%); paragraph pairs within the same file.

Usage: python3 duplicate_check.py [vault_path] [--scope SUBPATH]
       [--exclude COMPONENT] [--json] (vault defaults to the current
       directory).
"""

import contextlib
import os
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL, TOOL_VERSION = "duplicate_check", "1.1.0"

MIN_PARA_LEN = 40      # minimum paragraph length (characters) to compete
SHINGLE_SIZE = 12      # shingle window length (characters)
JACCARD_THRESHOLD = 0.5
CONTAINMENT_THRESHOLD = 0.7
LINK_LINE_RATIO = 0.6  # paragraph is a link list when [[-leading lines exceed this ratio
MAX_EXAMPLES_PER_PAIR = 3  # example paragraphs shown per file pair


# ---------------------------------------------------------------------------
# `--json` output (machine-readable receipts)
#
# Purely additive: without the flag not one byte of this tool's behaviour
# moves.  With it, everything written for a person goes to stderr and stdout
# carries exactly one canonical JSON array -- the receipt objects this run
# handed to the receipt writer, serialized verbatim.
#
# Nothing is filtered or renamed.  `schemas/receipt.template.jsonl` guarantees
# only the base fields every receipt carries; extension fields differ per
# producer and are discoverable from the receipt itself, which is why that
# template says its examples are "not the complete set".  A field allowlist
# here would silently drop exactly the fields a caller came for.
#
# Serialization goes through `kblib.canonical_json_bytes`; this module owns no
# serializer.  The flag changes no verdict, no exit code, and no receipt
# write.  A run that writes no receipt -- a dry run, or a refusal -- emits the
# empty array; a usage error still exits through argparse before any of this,
# leaving stdout empty and the reason on stderr.
# ---------------------------------------------------------------------------
JSON_HELP = ("write the receipts this run produced to stdout as one canonical "
             "JSON array and move the human-readable report to stderr; "
             "receipts written, verdicts, and exit codes are unchanged")

_JSON_RECEIPTS = []


def _record_receipts(receipts):
    """Remember the exact receipt objects handed to the receipt writer."""
    _JSON_RECEIPTS.extend(receipts)
    return receipts


def _run_reporting_json(runner):
    """Run `runner`, reserving stdout for JSON and giving stderr the prose."""
    stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        exit_code = runner()
    stdout.write(kblib.canonical_json_bytes(_JSON_RECEIPTS).decode("utf-8"))
    stdout.write("\n")
    stdout.flush()
    return exit_code


def iter_markdown_files(vault: Path, excludes):
    """Iterate all .md files under the vault, skipping excluded path components."""
    for path in sorted(vault.rglob("*.md")):
        rel_parts = path.relative_to(vault).parts
        if any(comp in rel_parts for comp in excludes):
            continue
        yield path


def split_paragraphs(text: str):
    """Split on blank lines; return the list of paragraph texts."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def is_link_list(paragraph: str) -> bool:
    """Whether the paragraph is mostly a wiki-link list ([[-leading lines > 60%)."""
    lines = [ln.strip() for ln in paragraph.splitlines() if ln.strip()]
    if not lines:
        return True
    link_lines = sum(1 for ln in lines if ln.lstrip("-*>0123456789. \t|").startswith("[["))
    return link_lines / len(lines) > LINK_LINE_RATIO


def shingles(paragraph: str):
    """Build the paragraph's 12-character shingle set (whitespace-collapsed sliding window)."""
    normalized = re.sub(r"\s+", " ", paragraph)
    if len(normalized) < SHINGLE_SIZE:
        return set()
    return {normalized[i:i + SHINGLE_SIZE] for i in range(len(normalized) - SHINGLE_SIZE + 1)}


def collect_paragraphs(vault: Path, excludes):
    """Collect all comparable paragraphs: [(file, para_text, shingle_set), ...]."""
    items = []
    for path in iter_markdown_files(vault, excludes):
        text = path.read_text(encoding="utf-8", errors="replace")
        for para in split_paragraphs(text):
            if len(para) < MIN_PARA_LEN or is_link_list(para):
                continue
            sh = shingles(para)
            if sh:
                items.append((path, para, sh))
    return items


def find_duplicates(items):
    """Compare paragraphs pairwise; return similar-paragraph records grouped by file pair.

    An inverted index pre-filters pairs sharing a shingle, avoiding a full
    O(n^2) exact comparison.
    """
    index = defaultdict(set)  # shingle -> item indexes
    for i, (_, _, sh) in enumerate(items):
        for s in sh:
            index[s].add(i)

    candidate_pairs = set()
    for idxs in index.values():
        if 1 < len(idxs) <= 50:  # extremely common shingles are not used for pairing
            candidate_pairs.update(combinations(sorted(idxs), 2))

    pairs = defaultdict(list)  # (file_a, file_b) -> [(score_desc, para_a, para_b)]
    for i, j in sorted(candidate_pairs):
        path_a, para_a, sh_a = items[i]
        path_b, para_b, sh_b = items[j]
        if path_a == path_b:  # pairs within the same file are excluded
            continue
        inter = len(sh_a & sh_b)
        if not inter:
            continue
        jaccard = inter / len(sh_a | sh_b)
        containment = inter / min(len(sh_a), len(sh_b))
        if jaccard > JACCARD_THRESHOLD or containment > CONTAINMENT_THRESHOLD:
            key = tuple(sorted((str(path_a), str(path_b))))
            pairs[key].append((f"jaccard={jaccard:.2f} containment={containment:.2f}", para_a, para_b))
    return pairs


def summarize(paragraph: str, width: int = 80) -> str:
    """Compress the paragraph into a single-line summary."""
    flat = re.sub(r"\s+", " ", paragraph)
    return flat[:width] + ("…" if len(flat) > width else "")


def path_in_scope(path_str: str, scope: Path) -> bool:
    """Whether path equals scope or lives under it (scope may be a file or directory)."""
    try:
        Path(path_str).resolve().relative_to(scope)
        return True
    except ValueError:
        return False


def main():
    ap = kblib.ArgumentParser(
        description="Cross-file duplicate paragraph candidate detection "
                    "(for maintenance runs and governance tasks)")
    ap.add_argument("vault", nargs="?", default=".",
                    help="vault root directory (default: current directory)")
    ap.add_argument("--scope",
                    help="subpath (relative to vault, or absolute): only report "
                         "similar pairs with at least one side under it")
    ap.add_argument("--exclude", action="append", default=None,
                    metavar="COMPONENT",
                    help="skip files whose path contains this component "
                         "(repeatable; default: legacy)")
    ap.add_argument("--receipts",
                    help="JSONL path to append machine-readable receipts to "
                         "(shared convention, Tools/schemas/receipt.template.jsonl)")
    ap.add_argument("--json", action="store_true", help=JSON_HELP)
    args = ap.parse_args()

    if not args.json:
        return _run(args)
    return _run_reporting_json(lambda: _run(args))


def _run(args):
    vault = Path(args.vault)
    excludes = args.exclude if args.exclude is not None else ["legacy"]
    excludes = [c.strip("/") for c in excludes if c.strip("/")]
    scope = None
    if args.scope:
        scope_path = Path(args.scope)
        scope = (scope_path if scope_path.is_absolute() else vault / scope_path).resolve()

    items = collect_paragraphs(vault, excludes)
    pairs = find_duplicates(items)
    if scope is not None:
        pairs = {
            key: records for key, records in pairs.items()
            if path_in_scope(key[0], scope) or path_in_scope(key[1], scope)
        }

    receipts = []
    if not pairs:
        print("No cross-file similar paragraphs above the thresholds.")
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "duplicate-check-summary",
            (args.scope or ".") + " @ " + str(vault.resolve()), "pass",
            "no cross-file similar paragraphs above the thresholds", 1))
        kblib.write_receipts(args.receipts, _record_receipts(receipts))
        return kblib.exit_code(receipts)

    scope_note = f" (scope: {args.scope})" if scope is not None else ""
    print(f"Found {len(pairs)} file pair(s) with similar paragraphs "
          f"(candidates, human judgement required){scope_note}:\n")
    seq = 0
    for (file_a, file_b), records in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        print(f"[{len(records)} match(es)] {file_a} <-> {file_b}")
        for score, para_a, para_b in records[:MAX_EXAMPLES_PER_PAIR]:
            print(f"  - {score}")
            print(f"    A: {summarize(para_a)}")
            print(f"    B: {summarize(para_b)}")
        print()
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "duplicate-paragraphs",
            f"{file_a} <-> {file_b}", "candidate",
            "%d similar paragraph pair(s) above thresholds (K03/03 split and "
            "duplication policy; candidates only, disposition is a human "
            "call)" % len(records), seq))
    kblib.write_receipts(args.receipts, _record_receipts(receipts))
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
