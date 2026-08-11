#!/usr/bin/env python3
"""Frontmatter controlled-vocabulary check script.

Rule owners:
- "kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies.md" (schema and
  the type/domain vocabularies);
- "kernel/K08 Metadata and Status/02 Scope Level Depth and Priority.md"
  (scope/level/depth/priority);
- "kernel/K08 Metadata and Status/03 Status Axes.md" (the four status axes and
  coverage_disposition);
- "kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata.md"
  (evidence_maturity; the legacy `status` field is a migration-period
  compatibility alias of authoring_status).
Vocabulary values come from the composed artifact Tools/vocab.yaml, produced by
compose_vocab.py from the kernel base plus one selected profile's extensions.
It is not a file the standard ships: a vault that has selected no profile
carries none, and this check says so and exits 1 rather than assuming a
vocabulary. Existence is not validity either: an artifact that is empty,
unparseable, or carries no `fields` mapping is refused the same way, because
an empty field set makes every controlled value legal and turns this gate into
an unconditional pass. It must be regenerated after revising the owner pages.

Method:
- Parse each .md file's `---` fenced frontmatter with the restricted YAML
  subset parser (kblib.parse_yaml_subset);
- values of controlled fields must be in the vocabulary: unknown value ->
  result=fail;
- a field missing or empty -> result=candidate (whether absence is allowed is
  a human call: K08/01 says "use the applicable fields", K08/05 says pages
  without frontmatter default to unassessed);
- a file without any frontmatter -> one candidate; frontmatter beyond the
  subset grammar and thus unparseable -> one candidate.

Scope semantics: --scope may be a directory or a single .md file (note-close
self-check, K00/05). After explicit exclusions are applied, an empty effective
scan set is result=fail for both scoped and whole-root runs -- a zero-file
scan is an invocation error, never a pass.

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
import compose_vocab
import profile_admission

TOOL = "check_vocab"
TOOL_VERSION = "1.5.0"
GATE_ID = "frontmatter-vocabulary"
# The `Check` cell K00/12 registers for this Gate; every receipt this
# tool offers as gate evidence carries it verbatim.
GATE_CHECK = "vocab-check-summary"


def _make_receipt(check, target, result, details, seq, root=None):
    """Build one producer-era vocabulary receipt with its stable Gate ID.

    ``root`` binds the Required Queue identity a Gate consumer compares
    against; outside a Cambium runtime those fields stay absent.
    """
    receipt = kblib.make_receipt(
        TOOL, TOOL_VERSION, check, target, result, details, seq, root=root)
    receipt["gate_id"] = GATE_ID
    return receipt


def load_vocab(path, text=None):
    """Load the composed artifact, refusing anything that is not a vocabulary.

    File existence is not validity. `parse_yaml_subset` maps empty input to
    `{}`, so a truncated or half-written `vocab.yaml` used to yield an empty
    field set, and an empty field set silently makes every controlled value
    legal -- the gate then reports a pass it never checked. K12/05 requires
    this check's input to be composed from the kernel base and the selected
    profile's `Vocabulary Extensions`; `kblib.parse_vocabulary_artifact`
    is that requirement as a deterministic predicate.
    """
    if text is None:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    data = kblib.parse_vocabulary_artifact(text)
    fields = data.get("fields") or {}
    vocab = {}
    for name, spec in fields.items():
        vocab[name] = {
            "values": [str(v) for v in (spec.get("values") or [])],
            "owner": spec.get("owner", ""),
        }
    return vocab


def main(argv=None, *, authorized_admission=None):
    ap = argparse.ArgumentParser(description="Frontmatter controlled-vocabulary check")
    ap.add_argument("vault_root", help="vault root directory")
    ap.add_argument("--scope", help="only scan .md files under this subpath")
    ap.add_argument("--vocab", default=None,
                    help="path to vocab.yaml (defaults to vocab.yaml next to this script)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="subpath to exclude (repeatable; e.g. the compiled "
                         "kernel/Cards artifacts, whose frontmatter is not governed "
                         "by the K08 module's knowledge-page schema)")
    ap.add_argument("--quota-p0", type=float, default=15.0,
                    help="P0 priority quota in percent (default 15; kernel "
                         "default; the selected profile manifest or task "
                         "contract may override)")
    ap.add_argument("--quota-p1", type=float, default=35.0,
                    help="P1 priority quota in percent (default 35; kernel "
                         "default; the selected profile manifest or task "
                         "contract may override)")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args(argv)

    vocab_path = args.vocab or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "vocab.yaml")
    if not os.path.exists(vocab_path):
        # The vocabulary is a composed artifact, not a shipped file: it exists
        # only once a profile has been selected. Report that as an
        # unconfigured vault, not as a crash.
        print("check_vocab: no composed vocabulary at %s" % vocab_path)
        print("  vocab.yaml is generated by compose_vocab.py from the kernel "
              "base plus one selected profile's extensions.")
        print("  No profile is selected by default, so a tree that has not "
              "composed one carries no vocabulary to check against.")
        print("  Complete profile adoption in K00/03, compose it, then re-run:")
        print("    python3 Tools/compose_vocab.py")
        print("  Or point this check at an existing artifact with --vocab PATH.")
        return 1
    root = os.path.realpath(os.path.abspath(args.vault_root))
    artifact_snapshot = None
    admission = authorized_admission
    try:
        canonical_vocab = (
            os.path.commonpath((root, os.path.realpath(vocab_path))) == root and
            os.path.relpath(os.path.realpath(vocab_path), root).replace(
                os.sep, "/") == compose_vocab.DEFAULT_OUTPUT)
    except ValueError:
        canonical_vocab = False
    if canonical_vocab:
        if admission is None:
            admission, admission_errors = profile_admission.admit_profile(root)
        else:
            admission_errors = []
            if os.path.realpath(admission.root) != root:
                admission_errors.append(
                    "authorized admission belongs to another repository root")
        if admission is not None:
            artifact_snapshot, artifact_errors = \
                compose_vocab.admitted_artifact(
                    root, compose_vocab.DEFAULT_OUTPUT, admission)
            admission_errors.extend(artifact_errors)
        if admission_errors:
            details = "; ".join(admission_errors)
            receipts = [_make_receipt(
                "vocab-artifact-stale", vocab_path, "fail", details, 1,
                root=args.vault_root)]
            print("check_vocab: FAIL — composed vocabulary is not current: %s"
                  % details)
            kblib.write_receipts(args.receipts, receipts)
            return kblib.exit_code(receipts)
    try:
        vocab = load_vocab(
            vocab_path,
            artifact_snapshot.read_text()
            if artifact_snapshot is not None else None)
    except (ValueError, OSError, UnicodeError) as exc:
        # An unreadable or non-composed artifact is an evidence-production
        # failure, not a clean corpus: continuing would report "no illegal
        # value" against a vocabulary that was never loaded.
        receipts = [_make_receipt(
            "vocab-artifact-invalid", vocab_path, "fail",
            "the composed vocabulary at %s is not usable as this gate's "
            "input: %s; K12/05 requires it to be composed from the kernel "
            "base and the selected profile's Vocabulary Extensions, so "
            "regenerate it with Tools/compose_vocab.py" % (vocab_path, exc),
            1, root=args.vault_root)]
        print("check_vocab: FAIL — composed vocabulary at %s is not usable: %s"
              % (vocab_path, exc))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    receipts = []
    seq = 0
    counts = {"files": 0, "no_frontmatter": 0, "unparseable": 0,
              "unknown_value": 0, "missing_field": 0, "ok_values": 0}
    dist = {"priority": {}, "tier": {}}  # K00/07 Priority Quota distribution stats

    excludes = [e.strip("/").replace(os.sep, "/") for e in args.exclude]
    scan_files = [
        (full, rel) for full, rel in
        kblib.iter_md_files(args.vault_root, args.scope)
        if not any(
            rel.replace(os.sep, "/") == excluded or
            rel.replace(os.sep, "/").startswith(excluded + "/")
            for excluded in excludes
        )
    ]
    if not scan_files:
        # The post-exclusion effective set owns the gate result. A scoped run,
        # an empty whole root, and a fully excluded root all fail closed.
        target = (args.scope or ".") + " @ " + os.path.abspath(args.vault_root)
        receipts = [_make_receipt(
            "scan-empty", target, "fail",
            "effective scan set contains no .md files (path missing, empty, "
            "or fully excluded); a zero-file scan cannot serve as a gate "
            "result", 1, root=args.vault_root)]
        print("check_vocab: scanned 0 file(s) — FAIL: effective scan set is empty")
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)
    for full, rel in scan_files:
        rel_disp = rel.replace(os.sep, "/")
        counts["files"] += 1
        text = open(full, encoding="utf-8", errors="replace").read()
        fm_text = kblib.extract_frontmatter(text)
        if fm_text is None:
            counts["no_frontmatter"] += 1
            seq += 1
            receipts.append(_make_receipt(
                "frontmatter-missing", rel_disp, "candidate",
                "file has no frontmatter; per K08/05 it defaults to "
                "authoring_status=unassessed, whether frontmatter must be "
                "added is a human call", seq, root=args.vault_root))
            continue
        try:
            fm = kblib.parse_yaml_subset(fm_text)
        except kblib.YamlSubsetError as exc:
            counts["unparseable"] += 1
            seq += 1
            receipts.append(_make_receipt(
                "frontmatter-unparseable", rel_disp, "candidate",
                "frontmatter is beyond the restricted YAML subset grammar and "
                "cannot be judged deterministically: %s" % exc, seq,
                root=args.vault_root))
            continue
        if not isinstance(fm, dict):
            counts["unparseable"] += 1
            seq += 1
            receipts.append(_make_receipt(
                "frontmatter-unparseable", rel_disp, "candidate",
                "top level of frontmatter is not a mapping", seq,
                root=args.vault_root))
            continue
        for _axis in ("priority", "tier"):
            _v = fm.get(_axis)
            if isinstance(_v, str) and _v.strip():
                dist[_axis][_v.strip()] = dist[_axis].get(_v.strip(), 0) + 1

        # Legacy `status` field: treated as a migration-period compatibility
        # alias of authoring_status (K08/04)
        effective = dict(fm)
        if "authoring_status" not in effective and "status" in effective:
            effective["authoring_status"] = effective["status"]

        for field, spec in vocab.items():
            value = effective.get(field)
            if field not in effective or value is None or value == "" or value == []:
                counts["missing_field"] += 1
                seq += 1
                receipts.append(_make_receipt(
                    "vocab-field-missing",
                    "%s#%s" % (rel_disp, field), "candidate",
                    "controlled field %s is missing or empty; whether absence "
                    "is allowed is a human call (owner: %s)"
                    % (field, spec["owner"]), seq, root=args.vault_root))
                continue
            for v in (value if isinstance(value, list) else [value]):
                sval = str(v)
                if sval not in spec["values"]:
                    counts["unknown_value"] += 1
                    seq += 1
                    receipts.append(_make_receipt(
                        "vocab-unknown-value",
                        "%s#%s" % (rel_disp, field), "fail",
                        "value %r of field %s is not in the controlled "
                        "vocabulary (owner: %s; allowed values: %s)"
                        % (sval, field, spec["owner"],
                           ", ".join(spec["values"])), seq,
                        root=args.vault_root))
                else:
                    counts["ok_values"] += 1

    if admission is not None:
        currency = compose_vocab.artifact_currency_errors(
            root, vocab_path, admission)
        for error in currency:
            seq += 1
            receipts.append(_make_receipt(
                "vocab-artifact-currency", vocab_path, "fail", error, seq,
                root=args.vault_root))

    if not any(r["result"] == "fail" for r in receipts):
        seq += 1
        receipts.append(_make_receipt(
            GATE_CHECK,
            (args.scope or ".") + " @ " + os.path.abspath(args.vault_root), "pass",
            "no illegal controlled-vocabulary values found (unknown_value=0; "
            "candidates counted separately)", seq, root=args.vault_root))

    if admission is not None:
        evidence = {
            "selected_profile_manifest": admission.manifest_repo_path,
            "profile_snapshot_sha256":
                admission.evaluation.profile_snapshot_sha256,
            "profile_contract_fingerprint":
                admission.evaluation.profile_contract_fingerprint,
            "profile_load_inputs_sha256":
                admission.evaluation.profile_load_inputs_sha256,
            "compiled_vocab_sha256": (
                artifact_snapshot.sha256
                if artifact_snapshot is not None else None),
        }
        for receipt in receipts:
            receipt.update(evidence)

    print("check_vocab: scanned %(files)d file(s)" % counts)
    print("  no_frontmatter=%(no_frontmatter)d unparseable=%(unparseable)d "
          "unknown_value(fail)=%(unknown_value)d missing_field(candidate)=%(missing_field)d "
          "ok_values=%(ok_values)d" % counts)
    for r in receipts:
        if r["result"] == "fail":
            print("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))

    # Distribution stats and Priority Quota check (owner: K00/07 Effort Tiering / Priority Quota)
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
            receipts.append(_make_receipt(
                "priority-quota", "vault", "candidate",
                "%s share %.0f%% (%d/%d) exceeds the K00/07 Priority Quota "
                "target <=%.0f%%; over-quota pages must be downgraded or an "
                "exemption recorded in the Coverage Ledger"
                % (_pcls, _n * 100.0 / _ptot, _n, _ptot, _quota), seq,
                root=args.vault_root))
            print("  [CAND priority-quota] %s share %.0f%% exceeds the <=%.0f%% quota (K00/07)"
                  % (_pcls, _n * 100.0 / _ptot, _quota))

    if admission is not None:
        final_currency = compose_vocab.artifact_currency_errors(
            root, vocab_path, admission)
        existing_currency = {
            receipt.get("details") for receipt in receipts
            if receipt.get("check") == "vocab-artifact-currency"
        }
        for error in final_currency:
            if error in existing_currency:
                continue
            seq += 1
            receipts.append(_make_receipt(
                "vocab-artifact-currency", vocab_path, "fail", error, seq,
                root=args.vault_root))
        for receipt in receipts:
            receipt.update(evidence)

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
