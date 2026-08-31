#!/usr/bin/env python3
"""Cross-file duplicate block detection.

Purpose: paragraph-level similarity scan over all .md files in the vault to
find copied passages across files that may violate the Cross-domain Rule
Registry (see kernel/K00 Standards Control/11 Standards Map and Rule Registry.md).
Output is candidates only; whether
a finding is an actual violation is a human call, and candidates are
separate from the maintenance-run candidate pool until its owning lifecycle
consumer explicitly admits them.  This producer never selects maintenance
work or supplies the semantic duplicate verdict.

Invocation tier (v2.0): repository-wide by default, used by maintenance runs
and governance tasks; no longer invoked at batch or single-page level (batch
close keeps only the basename-level duplicate candidates in the Batch-close
Closed List, see K12/09).  The caller supplies the repository root and may
supply a reporting scope.  The Tool consumes Cambium's shared Git-managed
Markdown boundary; it does not infer an adopter's content directories from
their names or from a selected Profile.

--scope SUBPATH: only report similar pairs where at least one side lives
under the subpath (the vault-wide index is still built, so pairs between
in-scope files and the rest of the vault are not missed).

Method and thresholds:
- paragraphs are split on blank lines; only paragraphs >= 40 characters are
  considered;
- similarity: 12-character sliding shingle sets; report when Jaccard > 0.5
  or containment > 0.7;
- explicit exclusions: files whose path contains a component supplied via
  --exclude (repeatable; no directory name is excluded by default);
  paragraphs dominated by link lists (lines starting with [[ make up > 60%);
  paragraph pairs within the same file.  Shingles present in more than 50
  paragraphs are not used to form candidate pairs, but a pair formed by any
  less-common shared shingle is still scored against its complete shingle
  sets.

Usage: python3 duplicate_check.py VAULT_PATH [--scope SUBPATH]
       [--exclude COMPONENT] [--json]
"""

import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
from Tools.platform.common import reporting

TOOL, TOOL_VERSION = "duplicate_check", "1.1.0"
RECEIPT_TYPE_ID = "duplicate-scan-receipt-v1"
RECEIPT_CHECKS = ("duplicate-check-summary", "duplicate-paragraphs")


def current_receipt_errors(record, *, root=None):
    return receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=RECEIPT_CHECKS)

MIN_PARA_LEN = 40      # minimum paragraph length (characters) to compete
SHINGLE_SIZE = 12      # shingle window length (characters)
JACCARD_THRESHOLD = 0.5
CONTAINMENT_THRESHOLD = 0.7
LINK_LINE_RATIO = 0.6  # paragraph is a link list when [[-leading lines exceed this ratio
MAX_EXAMPLES_PER_PAIR = 3  # example paragraphs shown per file pair


JSON_HELP = reporting.JSON_CHECK_HELP
_JSON_REPORTER = reporting.JsonReceiptCollector(emit_empty=True)


def iter_markdown_files(vault: Path, excludes):
    """Iterate the shared managed Markdown set minus explicit exclusions."""
    for absolute, relative in kblib.iter_managed_md_files(vault):
        if any(component in relative.split("/") for component in excludes):
            continue
        yield Path(absolute)


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
        text = kblib.read_text(path, errors="replace")
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


def _scope_paths(vault: Path, scope):
    """Resolve a caller scope through the shared managed-content owner."""
    return frozenset(
        str(Path(absolute))
        for absolute, _relative in kblib.iter_managed_md_files(vault, scope)
    )


def _parser():
    ap = kblib.ArgumentParser(
        description="Cross-file duplicate paragraph candidate detection "
                    "(for maintenance runs and governance tasks)")
    ap.add_argument("vault", help="repository root directory")
    ap.add_argument("--scope",
                    help="subpath (relative to vault, or absolute): only report "
                         "similar pairs with at least one side under it")
    ap.add_argument("--exclude", action="append", default=[],
                    metavar="COMPONENT",
                    help="skip files whose path contains this component "
                         "(repeatable; no component is excluded by default)")
    ap.add_argument("--receipts",
                    help="JSONL path to append machine-readable receipts to "
                         "(shared convention, Tools/schemas/receipt.template.jsonl)")
    ap.add_argument("--json", action="store_true", help=JSON_HELP)
    return ap


def main(argv=None):
    args = _parser().parse_args(argv)

    if not args.json:
        return _run(args)
    return _JSON_REPORTER.run(lambda: _run(args))


def _run(args):
    vault = Path(args.vault)
    excludes = [component.strip("/") for component in args.exclude
                if component.strip("/")]
    scope_paths = _scope_paths(vault, args.scope) if args.scope else None

    items = collect_paragraphs(vault, excludes)
    pairs = find_duplicates(items)
    if scope_paths is not None:
        pairs = {
            key: records for key, records in pairs.items()
            if key[0] in scope_paths or key[1] in scope_paths
        }

    receipts = []
    if not pairs:
        print("No cross-file similar paragraphs above the thresholds.")
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "duplicate-check-summary",
            (args.scope or ".") + " @ " + str(vault.resolve()), "pass",
            "no cross-file similar paragraphs above the thresholds", 1,
            receipt_type_id=RECEIPT_TYPE_ID))
        kblib.write_receipts(args.receipts, _JSON_REPORTER.record(receipts))
        return kblib.exit_code(receipts)

    scope_note = f" (scope: {args.scope})" if scope_paths is not None else ""
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
            "call)" % len(records), seq,
            receipt_type_id=RECEIPT_TYPE_ID))
    kblib.write_receipts(args.receipts, _JSON_REPORTER.record(receipts))
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
