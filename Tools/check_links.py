#!/usr/bin/env python3
"""Deterministic wiki-link check script (missing / ambiguous / heading resolution).

Rule owners:
- "09 Wiki Link and Navigation/03 Path Alias and Heading Links.md"
  (path/alias rules, `\\|` escaping inside tables, heading links);
- "09 Wiki Link and Navigation/05 Verification and Anti-patterns.md"
  (after each batch of tasks missing=0 and ambiguous=0 are required, and no
  broken heading links);
- "03 Note Types and Ownership/03 Split and Duplication Policy.md"
  (Retirement / Merge: the retirement gate requires every inbound link to be
  repointed to the successor page; a link whose target frontmatter says
  lifecycle: retired / merged is therefore reported as a candidate suggesting
  a repoint).

Method:
- Scan all .md files in the vault; strip fenced code blocks and inline code
  first, then extract links of the form `[[target#heading|alias]]` (handling
  the `\\|` escape);
- Resolution: when target contains `/`, try an exact vault-relative path
  match first; when that fails, or when the target is a bare basename, match
  by basename: exactly one match -> resolved; several matches -> ambiguous;
  no match -> missing;
- Links with `#heading` get a heading-existence check against the resolved
  target file (exact comparison first, then a case-insensitive retry;
  `#^block` references are skipped).

Result semantics: missing / ambiguous / bad heading are always result=fail
(09/05 requires all three to be zero); a target page whose lifecycle is
retired / merged is only result=candidate (suggest repointing to its
superseded_by successor page, 03/03), not a fail.
Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_links.py <vault_root> [--scope SUBPATH]
       [--exclude COMPONENT ...] [--receipts PATH]
"""

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_links"
TOOL_VERSION = "1.1.0"

LINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")


def parse_link(inner):
    """Split out (target_path, heading); drop the alias.

    Inside tables the alias separator is written as `\\|` (09/03: the wiki
    alias pipe must be escaped in Markdown tables), so both `\\|` and `|` are
    treated as the target/alias separator.
    """
    target_part = re.split(r"\\\||\|", inner, maxsplit=1)[0].strip()
    target, _, heading = target_part.partition("#")
    target = target.strip()
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target, heading.strip()


def build_index(files):
    """files: [(fullpath, relpath)]. Returns (path index, basename index)."""
    by_path = {}
    by_base = defaultdict(list)
    for full, rel in files:
        key = rel[:-3].replace(os.sep, "/")  # drop .md, normalize separators
        by_path[key] = full
        by_base[key.rsplit("/", 1)[-1]].append(key)
    return by_path, by_base


def resolve(target, by_path, by_base):
    """Returns (status, resolved_key_or_candidates). status: resolved/ambiguous/missing."""
    if "/" in target and target in by_path:
        return "resolved", target
    base = target.rsplit("/", 1)[-1]
    matches = by_base.get(base, [])
    if len(matches) == 1:
        return "resolved", matches[0]
    if len(matches) > 1:
        return "ambiguous", matches
    return "missing", None


def headings_cache_get(cache, by_path, key):
    if key not in cache:
        text = open(by_path[key], encoding="utf-8", errors="replace").read()
        cache[key] = [h for _, _, h in kblib.headings_of(kblib.strip_code(text))]
    return cache[key]


def lifecycle_cache_get(cache, by_path, key):
    """Returns the target page's {'lifecycle':..., 'superseded_by':...} (missing/unparseable frontmatter counts as active)."""
    if key not in cache:
        info = {"lifecycle": None, "superseded_by": None}
        fm_text = kblib.extract_frontmatter(
            open(by_path[key], encoding="utf-8", errors="replace").read())
        if fm_text is not None:
            try:
                fm = kblib.parse_yaml_subset(fm_text)
            except kblib.YamlSubsetError:
                fm = None
            if isinstance(fm, dict):
                info["lifecycle"] = fm.get("lifecycle")
                info["superseded_by"] = fm.get("superseded_by")
        cache[key] = info
    return cache[key]


def main():
    ap = argparse.ArgumentParser(description="Wiki link missing/ambiguous/heading check")
    ap.add_argument("vault_root", help="vault root directory")
    ap.add_argument("--scope", help="only scan .md files under this subpath (the index still covers the whole vault)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="path component to exclude (repeatable); files whose "
                         "path contains the component are neither scanned for "
                         "outgoing links nor used as resolution targets in "
                         "basename disambiguation")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    excludes = set(args.exclude)

    def keep(rel):
        return not any(part in excludes
                       for part in rel.replace(os.sep, "/").split("/"))

    all_files = [(f, r) for f, r in kblib.iter_md_files(args.vault_root) if keep(r)]
    if args.scope:
        scan_files = [(f, r) for f, r in kblib.iter_md_files(args.vault_root, args.scope)
                      if keep(r)]
    else:
        scan_files = all_files
    by_path, by_base = build_index(all_files)
    heading_cache = {}
    lifecycle_cache = {}

    receipts = []
    seq = 0
    counts = {"links": 0, "missing": 0, "ambiguous": 0, "bad_heading": 0,
              "block_ref_skipped": 0, "retired_target": 0}

    for full, rel in scan_files:
        text = kblib.strip_code(open(full, encoding="utf-8", errors="replace").read())
        rel_key = rel[:-3].replace(os.sep, "/")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in LINK_RE.finditer(line):
                target, heading = parse_link(m.group(1))
                counts["links"] += 1
                where = "%s:%d" % (rel.replace(os.sep, "/"), lineno)
                if target == "":
                    status, resolved = "resolved", rel_key  # [[#heading]] self-reference
                else:
                    status, resolved = resolve(target, by_path, by_base)
                if status == "missing":
                    counts["missing"] += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "link-missing", where, "fail",
                        "[[%s]] has no matching target (missing)" % m.group(1), seq))
                    continue
                if status == "ambiguous":
                    counts["ambiguous"] += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "link-ambiguous", where, "fail",
                        "[[%s]] has multiple basename matches (ambiguous): %s" % (m.group(1), "; ".join(resolved)), seq))
                    continue
                # Target page retired/merged: candidate (03/03 requires inbound
                # links to be repointed to the successor page), not a fail
                if target != "" and resolved != rel_key:
                    life = lifecycle_cache_get(lifecycle_cache, by_path, resolved)
                    if str(life["lifecycle"]) in ("retired", "merged"):
                        counts["retired_target"] += 1
                        seq += 1
                        hint = ("successor page superseded_by: %s" % life["superseded_by"]
                                if life["superseded_by"] else
                                "target page declares no superseded_by; verify its tombstone before repointing")
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION, "link-retired-target", where, "candidate",
                            "[[%s]] points to page %s with lifecycle: %s; consider repointing to the successor page (%s; 03/03 retirement gate)"
                            % (m.group(1), resolved, life["lifecycle"], hint), seq))
                if heading:
                    if heading.startswith("^"):
                        counts["block_ref_skipped"] += 1  # block references cannot be checked deterministically
                        continue
                    hs = headings_cache_get(heading_cache, by_path, resolved)
                    if heading not in hs and heading.casefold() not in {h.casefold() for h in hs}:
                        counts["bad_heading"] += 1
                        seq += 1
                        receipts.append(kblib.make_receipt(
                            TOOL, TOOL_VERSION, "link-bad-heading", where, "fail",
                            "[[%s]]: heading '%s' does not exist in target %s" % (m.group(1), heading, resolved), seq))

    problems = counts["missing"] + counts["ambiguous"] + counts["bad_heading"]
    if problems == 0:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "link-check-summary",
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "missing=0 ambiguous=0 bad_heading=0 (%d link(s) total)" % counts["links"], seq))

    print("check_links: scanned %d file(s), %d link(s)" % (len(scan_files), counts["links"]))
    print("  missing=%(missing)d ambiguous=%(ambiguous)d bad_heading=%(bad_heading)d "
          "block_ref_skipped=%(block_ref_skipped)d retired_target(candidate)=%(retired_target)d" % counts)
    for r in receipts:
        if r["result"] == "fail":
            print("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))
        elif r["result"] == "candidate":
            print("  [CAND %s] %s — %s" % (r["check"], r["target"], r["details"]))
    if problems == 0:
        print("  Conclusion: all link checks passed (09/05: missing=0, ambiguous=0).")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
