#!/usr/bin/env python3
"""Deterministic freshness (review_by) check.

Invocation tier (v2.0): maintenance-run only; not part of per-batch checks
(removed from the 12/05 per-batch checklist; run once at the start of a
maintenance run).

Method:
- scan the frontmatter of every .md file in the vault (restricted YAML
  subset parser, kblib);
- skip pages whose `lifecycle` is retired / merged;
- skip files whose path contains a component given via --exclude
  (repeatable; default: none);
- volatility: an explicit frontmatter declaration always wins; when a
  domain -> volatility mapping is supplied via --defaults (a flat file, or
  Tools/vocab.yaml / a profile's vocabulary-extensions.yaml via their
  volatility_defaults section), pages without an explicit declaration fall
  back to the mapping through their `domain`; otherwise (no --defaults, or
  domain missing / unmapped) the page is skipped and counted in the summary;
- re-verification interval: fast = 120 days, slow = 365 days, stable = no
  due date (never produces candidates);
- baseline date is `last_verified`, falling back to `last_reviewed`; when
  both are missing, the file's modification time is used as the most recent
  substantive modification date (08/05) and the page is flagged "pending
  first verification" with its computed due date;
- `review_by` = baseline + interval; --as-of (default: today) >= review_by
  counts as overdue;
- when every scanned file is skipped for lack of a resolvable volatility,
  the run reports NOTHING CHECKED as a candidate result -- an all-skip run
  is not evidence of freshness.

Result semantics: overdue and pending-first-verification pages are always
result=candidate -- they only feed the maintenance-run candidate list and
never change any status axis of a page. Output is sorted by priority (P0
first), then days overdue (largest first); pending-first-verification items
come after overdue items of the same priority.
Exit codes: 0 = no candidates, 2 = candidates found; this script never
produces fail.

Usage: python3 check_freshness.py <vault_root> [--scope SUBPATH]
       [--as-of YYYY-MM-DD] [--defaults FILE] [--exclude COMPONENT]
       [--receipts PATH]
"""

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_freshness"
TOOL_VERSION = "1.1.0"

# Re-verification interval (days) per volatility tier.
INTERVAL_DAYS = {"fast": 120, "slow": 365, "stable": None}

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def parse_date(value):
    """Parse a frontmatter date value into a date; return None if unparseable."""
    if value is None:
        return None
    s = str(value).strip().strip("\"'")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def load_frontmatter(path):
    """Return (frontmatter dict or None, whether parsing failed)."""
    text = open(path, encoding="utf-8", errors="replace").read()
    fm_text = kblib.extract_frontmatter(text)
    if fm_text is None:
        return None, False
    try:
        fm = kblib.parse_yaml_subset(fm_text)
    except kblib.YamlSubsetError:
        return None, True
    if not isinstance(fm, dict):
        return None, True
    return fm, False


def load_defaults(path):
    """Load a domain -> volatility mapping (restricted YAML subset).

    Accepts either a flat `domain: volatility` file, or a composed vocabulary
    artifact / profile extensions file carrying a nested `volatility_defaults`
    mapping (Tools/vocab.yaml, profiles/*/vocabulary-extensions.yaml) -- in
    that case the nested mapping is used.

    Returns a dict; raises ValueError on a malformed file or on a volatility
    value outside fast / slow / stable.
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    try:
        mapping = kblib.parse_yaml_subset(text)
    except kblib.YamlSubsetError as exc:
        raise ValueError("defaults file is not parseable YAML subset: %s" % exc)
    if isinstance(mapping, dict) and isinstance(mapping.get("volatility_defaults"), dict):
        mapping = mapping["volatility_defaults"]
    if not isinstance(mapping, dict):
        raise ValueError("defaults file must be a flat domain -> volatility "
                         "mapping or contain a volatility_defaults mapping")
    result = {}
    for domain, volatility in mapping.items():
        volatility = str(volatility)
        if volatility not in INTERVAL_DAYS:
            raise ValueError(
                "defaults file maps domain %r to invalid volatility %r "
                "(expected fast / slow / stable)" % (domain, volatility))
        result[str(domain)] = volatility
    return result


def main():
    ap = argparse.ArgumentParser(
        description="Freshness / review_by overdue candidate check")
    ap.add_argument("vault_root", help="vault root directory")
    ap.add_argument("--scope", help="only scan .md files under this subpath")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="reference date YYYY-MM-DD for overdue computation "
                         "(default: today)")
    ap.add_argument("--defaults", dest="defaults", default=None,
                    help="optional domain -> volatility mapping file "
                         "(restricted YAML subset); without it only pages "
                         "with an explicit volatility declaration are checked")
    ap.add_argument("--exclude", action="append", default=[],
                    metavar="COMPONENT",
                    help="skip files whose path contains this component "
                         "(repeatable; default: none)")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    as_of = parse_date(args.as_of) if args.as_of else datetime.date.today()
    if as_of is None:
        print("check_freshness: cannot parse --as-of (expected YYYY-MM-DD): %r"
              % args.as_of)
        return 1

    defaults_map = None
    if args.defaults:
        try:
            defaults_map = load_defaults(args.defaults)
        except (OSError, ValueError) as exc:
            print("check_freshness: cannot load --defaults file: %s" % exc)
            return 1

    exclude_components = [e.strip("/") for e in args.exclude if e.strip("/")]

    counts = {"files": 0, "excluded": 0, "skipped_lifecycle": 0,
              "unparseable": 0, "skipped_no_volatility": 0, "stable": 0,
              "fresh": 0, "overdue": 0, "pending_first_verification": 0}
    candidates = []  # (prio_rank, -overdue_days, rel, details)

    for full, rel in kblib.iter_md_files(args.vault_root, args.scope):
        rel_disp = rel.replace(os.sep, "/")

        # ---- path-component exclusion (--exclude) ----
        parts = rel_disp.split("/")
        if any(comp in parts for comp in exclude_components):
            counts["excluded"] += 1
            continue

        fm, unparseable = load_frontmatter(full)
        fm = fm or {}
        counts["files"] += 1
        if unparseable:
            counts["unparseable"] += 1

        # ---- lifecycle skip: retired / merged pages are no longer kept fresh ----
        lifecycle = str(fm.get("lifecycle") or "active")
        if lifecycle in ("retired", "merged"):
            counts["skipped_lifecycle"] += 1
            continue

        # ---- volatility: explicit declaration > --defaults mapping > skip ----
        volatility = fm.get("volatility")
        volatility = str(volatility) if volatility else None
        if volatility not in INTERVAL_DAYS:
            volatility = None
            if defaults_map is not None:
                domain = str(fm.get("domain") or "")
                volatility = defaults_map.get(domain)
        if volatility not in INTERVAL_DAYS:
            counts["skipped_no_volatility"] += 1
            continue
        interval = INTERVAL_DAYS[volatility]
        if interval is None:
            counts["stable"] += 1
            continue

        priority = str(fm.get("priority") or "")
        prio_rank = PRIORITY_ORDER.get(priority, len(PRIORITY_ORDER))
        prio_disp = priority or "no-priority"

        # ---- baseline date: last_verified > last_reviewed > file
        # modification time (08/05: with no last_verified, the creation date
        # or the date of the most recent substantive modification is used
        # instead and the page is marked awaiting first verification) ----
        pending_first = False
        baseline = parse_date(fm.get("last_verified"))
        baseline_field = "last_verified"
        if baseline is None:
            baseline = parse_date(fm.get("last_reviewed"))
            baseline_field = "last_reviewed"
        if baseline is None:
            pending_first = True
            baseline = datetime.date.fromtimestamp(os.path.getmtime(full))
            baseline_field = "file-modified"

        review_by = baseline + datetime.timedelta(days=interval)
        if pending_first:
            counts["pending_first_verification"] += 1
            state = ("overdue %d days" % (as_of - review_by).days
                     if as_of >= review_by else "due %s" % review_by.isoformat())
            details = ("pending first verification, %s: no last_verified / "
                       "last_reviewed; baseline %s=%s + %d days (08/05; "
                       "volatility=%s, priority=%s)"
                       % (state, baseline_field, baseline.isoformat(),
                          interval, volatility, prio_disp))
            candidates.append((prio_rank, 1, rel_disp, details))
        elif as_of >= review_by:
            overdue_days = (as_of - review_by).days
            counts["overdue"] += 1
            details = ("overdue %d days: review_by=%s (%s=%s + %d days, "
                       "volatility=%s, priority=%s)"
                       % (overdue_days, review_by.isoformat(),
                          baseline_field, baseline.isoformat(),
                          interval, volatility, prio_disp))
            candidates.append((prio_rank, -overdue_days, rel_disp, details))
        else:
            counts["fresh"] += 1

    # Sort: priority (P0 first) > days overdue (largest first) > pending > path
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    receipts = []
    seq = 0
    for _, _, rel_disp, details in candidates:
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "freshness", rel_disp, "candidate",
            details + "; enters the maintenance-run candidate list; "
                      "does not change any status axis", seq))
    all_skipped = (counts["files"] > 0
                   and counts["skipped_no_volatility"] == counts["files"])
    if not candidates:
        seq += 1
        if all_skipped:
            # "Nothing was checked" must not read as "nothing is stale":
            # every scanned file lacked a resolvable volatility, so the run
            # produced no freshness evidence at all (08/05).
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "freshness-check-summary",
                (args.scope or ".") + " @ " + os.path.abspath(args.vault_root),
                "candidate",
                "as_of=%s: all %d scanned file(s) were skipped for lack of a "
                "resolvable volatility (no explicit field and no --defaults "
                "match); this run checked nothing and is not evidence of "
                "freshness" % (as_of.isoformat(), counts["files"]), seq))
        else:
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "freshness-check-summary",
                (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
                "as_of=%s no overdue or pending-first-verification pages"
                % as_of.isoformat(), seq))

    print("check_freshness: as_of=%s checked %d files (plus %d excluded, "
          "%d retired/merged)" % (as_of.isoformat(), counts["files"],
                                  counts["excluded"],
                                  counts["skipped_lifecycle"]))
    print("  overdue=%(overdue)d pending_first_verification="
          "%(pending_first_verification)d fresh=%(fresh)d "
          "stable_no_due_date=%(stable)d "
          "skipped_no_volatility=%(skipped_no_volatility)d "
          "unparseable_frontmatter=%(unparseable)d" % counts)
    for _, _, rel_disp, details in candidates:
        print("  [CANDIDATE] %s — %s" % (rel_disp, details))
    if not candidates:
        if all_skipped:
            print("  Conclusion: NOTHING CHECKED — all %d file(s) skipped for "
                  "lack of a resolvable volatility; supply --defaults (a "
                  "profile's vocabulary-extensions.yaml, or a composed "
                  "Tools/vocab.yaml) or add volatility frontmatter. This is "
                  "not evidence of freshness." % counts["files"])
        else:
            print("  Conclusion: no maintenance-run candidates (overdue=0, "
                  "pending_first_verification=0).")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
