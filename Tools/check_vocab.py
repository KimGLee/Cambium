#!/usr/bin/env python3
"""Frontmatter controlled-vocabulary check script.

Rule owners:
- "08 Metadata and Status/01 Frontmatter and Core Vocabularies.md" (schema and
  the type/domain vocabularies);
- "08 Metadata and Status/02 Scope Level Depth and Priority.md"
  (scope/level/depth/priority);
- "08 Metadata and Status/03 Status Axes.md" (the four status axes and
  coverage_disposition);
- "08 Metadata and Status/04 Evidence and Relationship Metadata.md"
  (evidence_maturity; the legacy `status` field is a migration-period
  compatibility alias of authoring_status).
Vocabulary values come from the compiled artifact Tools/vocab.yaml (it must be
regenerated after revising the owner pages).

Method:
- Parse each .md file's `---` fenced frontmatter with the restricted YAML
  subset parser (kblib.parse_yaml_subset);
- values of controlled fields must be in the vocabulary: unknown value ->
  result=fail;
- a field missing or empty -> result=candidate (whether absence is allowed is
  a human call: 08/01 says "use the applicable fields", 08/05 says pages
  without frontmatter default to unassessed);
- a file without any frontmatter -> one candidate; frontmatter beyond the
  subset grammar and thus unparseable -> one candidate.

Scope semantics: --scope may be a directory or a single .md file (note-close
self-check, 00/05). A --scope that matches no files is result=fail -- a
zero-file scan is an invocation error, never a pass.

Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_vocab.py <vault_root> [--scope SUBPATH]
       [--vocab Tools/vocab.yaml] [--quota-p0 N] [--quota-p1 N]
       [--receipts PATH]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_vocab"
TOOL_VERSION = "1.1.0"


def load_vocab(path):
    data = kblib.parse_yaml_subset(open(path, encoding="utf-8").read())
    fields = data.get("fields") or {}
    vocab = {}
    for name, spec in fields.items():
        vocab[name] = {
            "values": [str(v) for v in (spec.get("values") or [])],
            "owner": spec.get("owner", ""),
        }
    return vocab


def main():
    ap = argparse.ArgumentParser(description="Frontmatter controlled-vocabulary check")
    ap.add_argument("vault_root", help="vault root directory")
    ap.add_argument("--scope", help="only scan .md files under this subpath")
    ap.add_argument("--vocab", default=None,
                    help="path to vocab.yaml (defaults to vocab.yaml next to this script)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="subpath to exclude (repeatable; e.g. the compiled "
                         "Cards/ artifacts, whose frontmatter is not governed "
                         "by the 08 domain knowledge-page schema)")
    ap.add_argument("--quota-p0", type=float, default=15.0,
                    help="P0 priority quota in percent (default 15; kernel "
                         "default; the selected profile manifest or task "
                         "contract may override)")
    ap.add_argument("--quota-p1", type=float, default=35.0,
                    help="P1 priority quota in percent (default 35; kernel "
                         "default; the selected profile manifest or task "
                         "contract may override)")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    vocab_path = args.vocab or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "vocab.yaml")
    vocab = load_vocab(vocab_path)

    receipts = []
    seq = 0
    counts = {"files": 0, "no_frontmatter": 0, "unparseable": 0,
              "unknown_value": 0, "missing_field": 0, "ok_values": 0}
    dist = {"priority": {}, "tier": {}}  # 00/02 Priority Quota distribution stats

    excludes = [e.strip("/").replace(os.sep, "/") for e in args.exclude]
    scan_files = kblib.iter_md_files(args.vault_root, args.scope)
    if args.scope and not scan_files:
        # A gate that scans nothing must fail, not silently pass (00/05 note
        # close; a nonexistent or empty --scope is an invocation error).
        receipts = [kblib.make_receipt(
            TOOL, TOOL_VERSION, "scope-empty",
            args.scope + " @ " + os.path.abspath(args.vault_root), "fail",
            "--scope matched no .md files (path missing, empty, or fully "
            "excluded); a zero-file scan cannot serve as a gate result", 1)]
        print("check_vocab: scanned 0 file(s) — FAIL: --scope %r matched no files" % args.scope)
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)
    for full, rel in scan_files:
        rel_disp = rel.replace(os.sep, "/")
        if any(rel_disp == e or rel_disp.startswith(e + "/") for e in excludes):
            continue
        counts["files"] += 1
        text = open(full, encoding="utf-8", errors="replace").read()
        fm_text = kblib.extract_frontmatter(text)
        if fm_text is None:
            counts["no_frontmatter"] += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "frontmatter-missing", rel_disp, "candidate",
                "file has no frontmatter; per 08/05 it defaults to "
                "authoring_status=unassessed, whether frontmatter must be "
                "added is a human call", seq))
            continue
        try:
            fm = kblib.parse_yaml_subset(fm_text)
        except kblib.YamlSubsetError as exc:
            counts["unparseable"] += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "frontmatter-unparseable", rel_disp, "candidate",
                "frontmatter is beyond the restricted YAML subset grammar and "
                "cannot be judged deterministically: %s" % exc, seq))
            continue
        if not isinstance(fm, dict):
            counts["unparseable"] += 1
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "frontmatter-unparseable", rel_disp, "candidate",
                "top level of frontmatter is not a mapping", seq))
            continue
        for _axis in ("priority", "tier"):
            _v = fm.get(_axis)
            if isinstance(_v, str) and _v.strip():
                dist[_axis][_v.strip()] = dist[_axis].get(_v.strip(), 0) + 1

        # Legacy `status` field: treated as a migration-period compatibility
        # alias of authoring_status (08/04)
        effective = dict(fm)
        if "authoring_status" not in effective and "status" in effective:
            effective["authoring_status"] = effective["status"]

        for field, spec in vocab.items():
            value = effective.get(field)
            if field not in effective or value is None or value == "" or value == []:
                counts["missing_field"] += 1
                seq += 1
                receipts.append(kblib.make_receipt(
                    TOOL, TOOL_VERSION, "vocab-field-missing",
                    "%s#%s" % (rel_disp, field), "candidate",
                    "controlled field %s is missing or empty; whether absence "
                    "is allowed is a human call (owner: %s)"
                    % (field, spec["owner"]), seq))
                continue
            for v in (value if isinstance(value, list) else [value]):
                sval = str(v)
                if sval not in spec["values"]:
                    counts["unknown_value"] += 1
                    seq += 1
                    receipts.append(kblib.make_receipt(
                        TOOL, TOOL_VERSION, "vocab-unknown-value",
                        "%s#%s" % (rel_disp, field), "fail",
                        "value %r of field %s is not in the controlled "
                        "vocabulary (owner: %s; allowed values: %s)"
                        % (sval, field, spec["owner"], ", ".join(spec["values"])), seq))
                else:
                    counts["ok_values"] += 1

    if not any(r["result"] == "fail" for r in receipts):
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, "vocab-check-summary",
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "no illegal controlled-vocabulary values found (unknown_value=0; "
            "candidates counted separately)", seq))

    print("check_vocab: scanned %(files)d file(s)" % counts)
    print("  no_frontmatter=%(no_frontmatter)d unparseable=%(unparseable)d "
          "unknown_value(fail)=%(unknown_value)d missing_field(candidate)=%(missing_field)d "
          "ok_values=%(ok_values)d" % counts)
    for r in receipts:
        if r["result"] == "fail":
            print("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))

    # Distribution stats and Priority Quota check (owner: 00/02 Effort Tiering / Priority Quota)
    for _axis in ("priority", "tier"):
        _tot = sum(dist[_axis].values())
        if _tot:
            _parts = ", ".join("%s=%d(%.0f%%)" % (k, v, 100.0 * v / _tot)
                               for k, v in sorted(dist[_axis].items()))
            print("  %s distribution: %s" % (_axis, _parts))
    _ptot = sum(dist["priority"].values())
    for _pcls, _quota in (("P0", args.quota_p0), ("P1", args.quota_p1)):
        _n = dist["priority"].get(_pcls, 0)
        if _ptot and _n * 100.0 / _ptot > _quota:
            seq += 1
            receipts.append(kblib.make_receipt(
                TOOL, TOOL_VERSION, "priority-quota", "vault", "candidate",
                "%s share %.0f%% (%d/%d) exceeds the 00/02 Priority Quota "
                "target <=%.0f%%; over-quota pages must be downgraded or an "
                "exemption recorded in the Coverage Ledger"
                % (_pcls, _n * 100.0 / _ptot, _n, _ptot, _quota), seq))
            print("  [CAND priority-quota] %s share %.0f%% exceeds the <=%.0f%% quota (00/02)"
                  % (_pcls, _n * 100.0 / _ptot, _quota))

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
