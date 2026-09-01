#!/usr/bin/env python3
"""Page boundary contract check — the `boundary-contract` gate (advisory).

Rule owner:
- "kernel/K08 Metadata and Status/09 Page Boundary Contract.md"
  (the `boundary` block schema, cross-page rules, projection authority,
  and enablement).

Per page carrying a `boundary` frontmatter block, against K08/09:
- B1 shape: key closure, kebab-case slugs, grouped-entry and excludes entry
  shapes, goals/non_goals string lists (kblib.validate_boundary_shape);
- B2 self-consistency: no slug both owned and excluded, no repeated owned
  slug, and no `excludes[].owner` resolving to the declaring page itself;
- B3 resolvability: every `excludes[].owner` resolves to an existing page
  inside the vault (with or without the .md suffix);
- B4 reciprocity: the owner page's own `boundary.owns` contains the
  excluded concern at either level. An owner page with no `boundary` block
  at all is a migration-tolerated candidate even under --strict; an owner
  carrying the block but not the concern is a violation;
- B5 uniqueness: one concern slug is owned by at most one page across the
  effective scan set (the content-plane single-owner mapping);
- B6 projection freshness: a page whose body carries the
  `<!-- boundary-projection:begin/end -->` markers owns exactly one
  well-formed pair whose content matches the deterministic rendering of its
  own `boundary` block (labels from the compiled contract's
  `boundary_projection`, K08/09 defaults otherwise). Markers without a
  boundary block are orphaned. A page without markers is skipped, never
  stale — marker placement is curated (K08/09 Projection).

Concern vocabulary membership stays with the `frontmatter-vocabulary`
gate; presence, mode, and the unknown-field closure of the `boundary`
field stay with the `page-contract` gate; whether a boundary is drawn
correctly stays with semantic review.

Input includes the compiled contract produced by
Tools/compose_page_contract.py (.cambium/derived/page_contract.yaml by
default) for
the projection display labels; an absent or unparseable contract is a
failure, never a pass. Scope defaults to the union of the selected
Profile Scope's registered layer directories; --scope narrows it. A
zero-page effective scan set fails closed.

Enablement (K08/09): advisory by default — violations are candidates,
exit 2. --strict turns violations into failures (exit 1) except the B4
migration-tolerated case, and is the mode a later governance decision
promotes to a gate.

Exit codes: 0 = all pass, 1 = hard failure (or violations under --strict),
2 = advisory candidates.

Usage: python3 check_boundary_contract.py <vault_root>
       [--profile PROFILE_DIR]
       [--contract .cambium/derived/page_contract.yaml]
       [--scope SUBPATH] [--exclude SUBPATH] [--strict] [--receipts PATH]
"""

import os
import sys

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.knowledge.metadata.compose_page_contract as compose_page_contract
from Tools.knowledge.structure import boundary_contract
import Tools.governance.profile.profile_admission as profile_admission
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting
from Tools.platform.repository import repository
TOOL = "check_boundary_contract"
TOOL_VERSION = "1.1.0"
GATE_ID = "boundary-contract"
# The `Check` cell K00/12 registers for this Gate.
GATE_CHECK = "boundary-contract-summary"
RECEIPT_TYPE_ID = "boundary-contract-gate-receipt-v1"


def current_receipt_errors(record, *, root=None):
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION,
        checks=("boundary-contract", GATE_CHECK))
    if isinstance(record, dict) and record.get("gate_id") != GATE_ID:
        errors.append("gate_id must identify boundary-contract")
    return errors

JSON_FLAG_HELP = reporting.JSON_CHECK_HELP
_JSON_REPORTER = reporting.RedirectedJsonReceipts()


ACTIVE_STATE_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
SCOPE_SLOT = profile_admission.PROFILE_SCOPE_SLOT
def run(root, profile_override, contract_path, scope, excludes, strict,
        receipts_path):
    root = os.path.abspath(root)
    findings = reporting.FindingSet()
    violation = "fail" if strict else "candidate"

    admission, admission_errors = profile_admission.admit_profile(
        root, profile_override, active_state_path=ACTIVE_STATE_PATH)
    for error in admission_errors:
        findings.add("boundary-contract-profile-load", ACTIVE_STATE_PATH,
                     "fail", error)

    contract_abs = contract_path if os.path.isabs(contract_path) \
        else os.path.join(root, contract_path)
    artifact_snapshot = None
    if admission is not None:
        artifact_snapshot, artifact_errors = \
            compose_page_contract.admitted_artifact(
                root, contract_abs, admission)
        for error in artifact_errors:
            findings.add("boundary-contract-artifact-current", contract_abs,
                         "fail", error)
    labels = None
    label_text = None
    if artifact_snapshot is not None:
        label_text = artifact_snapshot.read_text()
    else:
        try:
            label_text = kblib.read_text(contract_abs, errors="replace")
        except OSError as exc:
            findings.add(
                "boundary-contract-input",
                contract_abs,
                "fail",
                "cannot parse the compiled contract: %s — compose it with "
                "Tools/compose_page_contract.py" % exc,
            )
    if label_text is not None:
        labels, label_error = boundary_contract.projection_labels_from_text(
            label_text
        )
        if label_error:
            findings.add(
                "boundary-contract-input", contract_abs, "fail", label_error
            )

    scan_roots = []
    if labels is not None and admission is not None:
        if scope:
            scan_roots = [scope]
        else:
            scan_roots, scope_errors = \
                profile_admission.scope_directories(admission)
            for error in scope_errors:
                if error == "no Logical Architecture layer table found":
                    error += "; the default scan scope cannot be resolved"
                findings.add(
                    "boundary-contract-profile", SCOPE_SLOT, "fail", error)

    pages = []
    for scan_root in scan_roots:
        base = os.path.normpath(os.path.join(root, scan_root))
        if not os.path.isdir(base) and not (
                os.path.isfile(base) and base.lower().endswith(".md")):
            findings.add("boundary-contract-scope", scan_root, "fail",
                         "scan root does not exist")
            continue
        for full, _rel in kblib.iter_md_files(root, scope=scan_root):
            pages.append(full)
    exclude_roots = [os.path.normpath(os.path.join(root, e))
                     for e in excludes]

    pages = [
        path for path in sorted(set(pages))
        if not repository.path_is_within_any(path, exclude_roots)
    ]

    if labels is not None and not pages:
        findings.add("boundary-contract-scope",
                     ",".join(scan_roots) or "<none>", "fail",
                     "the effective scan set is empty; a zero-page scan is "
                     "an invocation error, never a pass")

    # First pass: collect every in-scope boundary block for B5.
    blocks = {}
    owners_of = {}
    checked = 0
    for path in pages:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        block, parse_ok = boundary_contract.boundary_block_from_text(
            kblib.read_text(path, errors="replace")
        )
        if block is None:
            if not parse_ok:
                continue  # frontmatter defects stay with page-contract
            lines = kblib.read_text(path, errors="replace").splitlines()
            _b, _e, marker_error = boundary_contract.projection_marker_pair(lines)
            if marker_error or _b is not None:
                findings.add("boundary-projection", rel, violation,
                             "projection markers are present but the page "
                             "carries no boundary block; the markers are "
                             "orphaned")
            continue
        checked += 1
        blocks[rel] = block
        for slug in kblib.boundary_owned_slugs(block):
            owners_of.setdefault(slug, []).append(rel)

    # Second pass: per-page rules.
    for rel, block in blocks.items():
        path = os.path.join(root, rel)

        for check, label, details in kblib.validate_boundary_shape(
                block, target=rel + ":boundary"):
            findings.add(check, label, violation, details)

        for entry in block.get("excludes") or [] \
                if isinstance(block.get("excludes"), list) else []:
            if not isinstance(entry, dict):
                continue
            concern = entry.get("concern")
            owner = entry.get("owner")
            if not isinstance(owner, str) or not owner.strip():
                continue
            target = "%s:boundary:excludes:%s" % (rel, concern)
            resolved = repository.resolve_markdown_reference(root, owner)
            if resolved is None:
                findings.add("boundary-owner-resolvability", target,
                             violation,
                             "owner %r does not resolve inside the vault"
                             % owner)
                continue
            if os.path.realpath(resolved) == os.path.realpath(path):
                findings.add("boundary-consistency", target, violation,
                             "owner resolves to the declaring page itself")
                continue
            owner_block, _ok = boundary_contract.boundary_block_from_text(
                kblib.read_text(resolved, errors="replace")
            )
            if owner_block is None:
                findings.add("boundary-reciprocity", target, "candidate",
                             "owner %r carries no boundary block yet; "
                             "migration-tolerated candidate (K08/09)"
                             % owner)
            elif concern not in kblib.boundary_owned_slugs(owner_block):
                findings.add("boundary-reciprocity", target, violation,
                             "owner %r does not claim concern %r in its "
                             "own boundary.owns" % (owner, concern))

        lines = kblib.read_text(path, errors="replace").splitlines()
        begin, end, marker_error = boundary_contract.projection_marker_pair(lines)
        if marker_error:
            findings.add("boundary-projection", rel, violation, marker_error)
        elif begin is not None:
            current = [line.rstrip() for line in lines[begin:end + 1]]
            expected = kblib.render_boundary_projection_lines(block, labels)
            if current != expected:
                findings.add("boundary-projection", rel, violation,
                             "the owned projection block is stale; "
                             "regenerate it with "
                             "Tools/render_boundary_projection.py --apply")

    # B5 uniqueness across the effective scan set.
    for slug in sorted(owners_of):
        holders = owners_of[slug]
        if len(holders) > 1:
            findings.add("boundary-uniqueness", slug, violation,
                         "concern is owned by %d pages (%s); one concern "
                         "has at most one owner (K08/09)"
                         % (len(holders), ", ".join(sorted(holders))))

    if admission is not None:
        for error in profile_admission.currency_errors(admission):
            findings.add("boundary-contract-profile-currency",
                         admission.manifest_repo_path, "fail", error)
        for error in compose_page_contract.artifact_currency_errors(
                root, contract_abs, admission):
            findings.add("boundary-contract-artifact-currency", contract_abs,
                         "fail", error)
    fails = findings.count("fail")
    candidates = findings.count("candidate")
    print("check_boundary_contract: scanned %d page(s), %d with a boundary "
          "block, mode=%s"
          % (len(pages), checked, "strict" if strict else "advisory"))
    for row in findings.rows:
        print("  [%s] %s (%s): %s" % (row["result"].upper(), row["check"],
                                      row["target"], row["details"]))
    print("  fail=%d candidate=%d" % (fails, candidates))
    if fails:
        print("  Conclusion: boundary-contract check failed (K08/09).")
    elif candidates:
        print("  Conclusion: advisory candidates found; they support "
              "migration planning and no existing gate consumes them "
              "(K08/09 Enablement).")
    else:
        print("  Conclusion: every scanned boundary block satisfies the "
              "page boundary contract. Concern vocabulary membership and "
              "whether a boundary is drawn correctly remain owned by their "
              "own gates.")

    if receipts_path or _JSON_REPORTER.enabled:
        # The receipt set is this run's structured result, so `--json` builds
        # it even with no receipts file to append to.  Neither destination
        # changes what the receipts say.
        receipts = []
        seq = 1
        for row in findings.rows:
            receipt = kblib.make_receipt(
                TOOL, TOOL_VERSION, "boundary-contract", row["target"],
                row["result"], row["details"], seq,
                receipt_type_id=RECEIPT_TYPE_ID, root=root)
            receipt["gate_id"] = GATE_ID
            receipts.append(receipt)
            seq += 1
        summary = kblib.make_receipt(
            TOOL, TOOL_VERSION, GATE_CHECK, "boundary-contract",
            "fail" if fails else ("candidate" if candidates else "pass"),
            "pages=%d boundary_pages=%d fail=%d candidate=%d mode=%s"
            % (len(pages), checked, fails, candidates,
               "strict" if strict else "advisory"),
            seq, receipt_type_id=RECEIPT_TYPE_ID, root=root)
        summary["gate_id"] = GATE_ID
        if admission is not None:
            summary.update({
                "selected_profile_manifest": admission.manifest_repo_path,
                "profile_snapshot_sha256":
                    admission.evaluation.profile_snapshot_sha256,
                "profile_contract_fingerprint":
                    admission.evaluation.profile_contract_fingerprint,
                "profile_load_inputs_sha256":
                    admission.evaluation.profile_load_inputs_sha256,
                "compiled_page_contract_sha256": (
                    artifact_snapshot.sha256
                    if artifact_snapshot is not None else None),
            })
        receipts.append(summary)
        if receipts_path:
            kblib.write_receipts(receipts_path, receipts)
        _JSON_REPORTER.record(receipts)

    if fails:
        return 1
    return 2 if candidates else 0


def main(argv=None):
    """CLI entry point; `--json` projects the produced receipts onto stdout."""
    return reporting.run_redirected_json(
        _JSON_REPORTER, lambda: _main(argv))


def _main(argv=None):
    parser = kblib.ArgumentParser(
        description="Validate page boundary blocks against the K08/09 page "
                    "boundary contract (gate: boundary-contract; advisory "
                    "by default).")
    parser.add_argument("vault_root", help="vault root directory")
    parser.add_argument("--profile",
                        help="profile directory override; default is the "
                             "selected_profile_manifest of the active "
                             "Standards state")
    parser.add_argument("--contract",
                        default=runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH,
                        help="compiled contract path (default %s)" %
                        runtime_paths.PAGE_CONTRACT_ARTIFACT_PATH)
    parser.add_argument("--scope",
                        help="only scan .md files under this subpath "
                             "(directory or single page)")
    parser.add_argument("--exclude", action="append", default=[],
                        help="subpath to exclude; repeatable")
    parser.add_argument("--strict", action="store_true",
                        help="treat violations as failures except the B4 "
                             "migration-tolerated case; the mode a "
                             "governance decision promotes to a gate")
    parser.add_argument("--receipts",
                        help="JSONL path to append machine-readable "
                             "receipts to")
    parser.add_argument("--json", action="store_true", help=JSON_FLAG_HELP)
    args = parser.parse_args(argv)
    _JSON_REPORTER.begin(args.json)
    return run(args.vault_root, args.profile, args.contract, args.scope,
               args.exclude, args.strict, args.receipts)


if __name__ == "__main__":
    sys.exit(main())
