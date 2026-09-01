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
  (evidence_maturity).
Vocabulary values come from the composed artifact
.cambium/derived/vocab.yaml, produced by compose_vocab.py from the kernel base
plus one selected profile's extensions.
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
- missing/empty controlled fields and pages without frontmatter are diagnostic
  counts only.  Applicability and required presence belong to the compiled
  page contract; this value checker must not turn a legal absence into a
  repository-wide human decision;
- frontmatter beyond the subset grammar is a failure because no controlled
  value can be proved legal from bytes the producer cannot parse.

Scope semantics: --scope may be a directory or a single .md file (note-close
self-check, K00/05). After explicit exclusions are applied, an empty effective
scan set is result=fail for both scoped and whole-root runs -- a zero-file
scan is an invocation error, never a pass.

Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_vocab.py <vault_root> [--scope SUBPATH]
       [--vocab .cambium/derived/vocab.yaml] [--quota-p0 N] [--quota-p1 N]
       [--receipts PATH] [--json]
"""

import os
import sys
from functools import partial

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.knowledge.metadata.compose_vocab as compose_vocab
import Tools.governance.control.contract_exception_policy as contract_exception_policy
import Tools.governance.profile.profile_admission as profile_admission
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting
from Tools.platform.common import receipts as tool_receipts

TOOL = "check_vocab"
TOOL_VERSION = "1.9.0"
GATE_ID = "frontmatter-vocabulary"
# Every K00/12 Gate this producer binds, with the check each receipt writes;
# the registry guard compares its rows against this mapping.
GATE_CHECKS = {
    "frontmatter-vocabulary": "vocab-check-summary",
    "priority-quota-distribution": "priority-quota-distribution",
}
# The `Check` cell K00/12 registers for this Gate; every receipt this
# tool offers as gate evidence carries it verbatim.
GATE_CHECK = "vocab-check-summary"
RECEIPT_TYPE_ID = "vocabulary-gate-receipt-v1"


def current_receipt_errors(record, *, root=None):
    gate_id = record.get("gate_id") if isinstance(record, dict) else None
    expected_check = GATE_CHECKS.get(gate_id)
    check = record.get("check") if isinstance(record, dict) else None
    allowed = (expected_check,) if check == expected_check else \
        ((check,) if isinstance(check, str) and check else ())
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION, checks=allowed)
    if gate_id not in GATE_CHECKS:
        errors.append("gate_id is not a current check_vocab Gate")
    return errors


JSON_HELP = reporting.JSON_RECEIPT_SUMMARY_HELP
_JSON_REPORTER = reporting.JsonReceiptCollector()


_make_receipt = partial(
    tool_receipts.make_gate_receipt, TOOL, TOOL_VERSION, GATE_ID,
    receipt_type_id=RECEIPT_TYPE_ID)


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
        text = kblib.read_text(path)
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
    ap = kblib.ArgumentParser(description="Frontmatter controlled-vocabulary check")
    ap.add_argument("vault_root", help="vault root directory")
    ap.add_argument("--scope", help="only scan .md files under this subpath")
    ap.add_argument("--vocab", default=None,
                    help="path to vocab.yaml (defaults to vocab.yaml next to this script)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="subpath to exclude (repeatable; e.g. the curated "
                         "Card control plane, whose frontmatter is not governed "
                         "by the K08 module's knowledge-page schema)")
    ap.add_argument(
        "--quota-p0", type=float,
        default=contract_exception_policy.PRIORITY_QUOTA_KERNEL_DEFAULTS[0],
        help="P0 priority quota in percent (defaults to the Kernel policy "
             "registry value; the selected Profile or Task Contract may "
             "supply the already-resolved effective value)")
    ap.add_argument(
        "--quota-p1", type=float,
        default=contract_exception_policy.PRIORITY_QUOTA_KERNEL_DEFAULTS[1],
        help="P1 priority quota in percent (defaults to the Kernel policy "
             "registry value; the selected Profile or Task Contract may "
             "supply the already-resolved effective value)")
    ap.add_argument("--policy-fingerprint",
                    help="effective-policy fingerprint (from the Kernel "
                         "policy registry resolver) the quotas were "
                         "resolved from; recorded on the priority-quota-"
                         "compliance receipt so its consumers can bind the "
                         "policy identity, never re-derive it")
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    ap.add_argument(
        "--json", action="store_true",
        help=JSON_HELP)
    args = ap.parse_args(argv)

    if not args.json:
        return _run(args, None, authorized_admission)

    def reported_run():
        produced = []
        code = _run(args, produced, authorized_admission)
        _JSON_REPORTER.record(produced)
        return code

    return _JSON_REPORTER.run(reported_run)


def _run(args, produced, authorized_admission):
    """Execute one already-parsed invocation; ``produced`` collects receipts.

    Every exit that owns receipts routes through :func:`_finish` below, so the
    ``--json`` view and the JSONL append always describe the same objects.
    """

    def _finish(receipts):
        if produced is not None:
            produced.extend(receipts)
        return kblib.exit_code(receipts)

    priority_shares = {}

    vocab_path = args.vocab or os.path.join(
        os.path.abspath(args.vault_root), compose_vocab.DEFAULT_OUTPUT)
    vocab_capability = kblib.inherited_path_capability(
        vocab_path, "snapshot")
    if ((vocab_capability is not None and not vocab_capability["exists"]) or
            (vocab_capability is None and not os.path.exists(vocab_path))):
        # The vocabulary is a composed artifact, not a shipped file: it exists
        # only once a profile has been selected. Report that as an
        # unconfigured vault, not as a crash.
        print("check_vocab: no composed vocabulary at %s" % vocab_path)
        print("  the effective vocabulary is generated by compose_vocab.py "
              "under %s/ from the kernel base plus one selected profile's "
              "extensions." % runtime_paths.DERIVED_ROOT)
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
            (vocab_capability is not None and
             vocab_capability["spelling"] == compose_vocab.DEFAULT_OUTPUT) or
            (vocab_capability is None and
             os.path.commonpath((root, os.path.realpath(vocab_path))) == root and
             os.path.relpath(os.path.realpath(vocab_path), root).replace(
                 os.sep, "/") == compose_vocab.DEFAULT_OUTPUT))
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
            return _finish(receipts)
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
        return _finish(receipts)

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
        target = args.scope or "."
        receipts = [_make_receipt(
            "scan-empty", target, "fail",
            "effective scan set contains no .md files (path missing, empty, "
            "or fully excluded); a zero-file scan cannot serve as a gate "
            "result", 1, root=args.vault_root)]
        print("check_vocab: scanned 0 file(s) — FAIL: effective scan set is empty")
        kblib.write_receipts(args.receipts, receipts)
        return _finish(receipts)
    for full, rel in scan_files:
        rel_disp = rel.replace(os.sep, "/")
        counts["files"] += 1
        text = kblib.read_text(full, errors="replace")
        fm_text = kblib.extract_frontmatter(text)
        if fm_text is None:
            counts["no_frontmatter"] += 1
            continue
        try:
            fm = kblib.parse_yaml_subset(fm_text)
        except kblib.YamlSubsetError as exc:
            counts["unparseable"] += 1
            seq += 1
            receipts.append(_make_receipt(
                "frontmatter-unparseable", rel_disp, "fail",
                "frontmatter is beyond the restricted YAML subset grammar and "
                "its controlled values cannot be proved legal: %s" % exc, seq,
                root=args.vault_root))
            continue
        if not isinstance(fm, dict):
            counts["unparseable"] += 1
            seq += 1
            receipts.append(_make_receipt(
                "frontmatter-unparseable", rel_disp, "fail",
                "top level of frontmatter is not a mapping", seq,
                root=args.vault_root))
            continue
        for _axis in ("priority", "tier"):
            _v = fm.get(_axis)
            if isinstance(_v, str) and _v.strip():
                dist[_axis][_v.strip()] = dist[_axis].get(_v.strip(), 0) + 1

        for field, spec in vocab.items():
            value = fm.get(field)
            if field not in fm or value is None or value == "" or value == []:
                counts["missing_field"] += 1
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
        _summary = _make_receipt(
            GATE_CHECK,
            args.scope or ".", "pass",
            "no illegal controlled-vocabulary values found "
            "(unknown_value=0; missingness belongs to the page contract)",
            seq, root=args.vault_root)
        _summary["priority_shares"] = priority_shares
        receipts.append(_summary)

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
          "unknown_value(fail)=%(unknown_value)d missing_field(diagnostic)=%(missing_field)d "
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
    # NOT re-initialized here: the summary receipt above already holds a
    # reference to the dict bound at entry, and rebinding the name to a new
    # dict would leave that receipt recording `priority_shares: {}` forever
    # while this loop fills an object nobody references.
    _quota_exceeded = []
    for _pcls, _quota in (("P0", args.quota_p0), ("P1", args.quota_p1)):
        _n = dist["priority"].get(_pcls, 0)
        _share = (_n * 100.0 / _ptot) if _ptot else 0.0
        priority_shares[_pcls] = {
            "pages": _n, "total": _ptot, "share": round(_share, 4),
            "quota": _quota,
        }
        if _ptot and not kblib.quota_share_within_limit(_n, _ptot, _quota):
            # Exact arithmetic, same owner as the authorization comparison:
            # a float rendering must neither invent nor hide an excess.
            # One candidate per class: an exception is a bounded grant for
            # one class at one magnitude, and a type that fused P0 and P1
            # would make accepting one mean accepting both.
            _quota_exceeded.append(_pcls)
            seq += 1
            _receipt = _make_receipt(
                "priority-quota-%s" % _pcls, "vault", "candidate",
                "%s share %.1f%% (%d/%d) exceeds the K00/07 Priority Quota "
                "target <=%.0f%%; resolve by demotion, a profile quota "
                "registration, or a bounded contract policy exception"
                % (_pcls, _share, _n, _ptot, _quota), seq,
                root=args.vault_root)
            _receipt["priority_share"] = priority_shares[_pcls]
            receipts.append(_receipt)
            print("  [CAND priority-quota-%s] share %.1f%% exceeds the <=%.0f%% quota (K00/07)"
                  % (_pcls, _share, _quota))

    # The whole-corpus distribution Gate (K00/12 `priority-quota-
    # distribution`): one receipt carrying the same scan's per-class shares
    # and the policy identity they were measured under, so batch-close,
    # Maintenance/REBASE reconciliation, and the Terminal Audit consume one
    # structured evidence object instead of re-deriving the distribution
    # from display text.  It MEASURES and itemizes; it never judges.  The
    # human call on an excess lives in the per-class candidates above --
    # they are the dispositionable objects K00/07's three instruments
    # answer -- so this receipt is `pass` whenever the measurement
    # completed, with any exceeded classes named in `quota_exceeded`.  A
    # judging result here would mint a second candidate for the same excess
    # and a second place where quota acceptance is decided.
    seq += 1
    _compliance = _make_receipt(
        "priority-quota-distribution", "vault", "pass",
        ("priority shares measured; within the standing quotas"
         if not _quota_exceeded else
         "priority shares measured; class(es) %s exceed the standing "
         "quotas, itemized as per-class candidates (K00/07 owns the "
         "resolution instruments)" % ", ".join(_quota_exceeded)),
        seq, root=args.vault_root)
    _compliance["gate_id"] = "priority-quota-distribution"
    _compliance["priority_shares"] = priority_shares
    _compliance["quota_exceeded"] = list(_quota_exceeded)
    _compliance["policy_fingerprint"] = args.policy_fingerprint
    receipts.append(_compliance)

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
    return _finish(receipts)


if __name__ == "__main__":
    sys.exit(main())
