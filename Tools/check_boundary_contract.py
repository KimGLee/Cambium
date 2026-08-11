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
Tools/compose_page_contract.py (Tools/page_contract.yaml by default) for
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
       [--profile PROFILE_DIR] [--contract Tools/page_contract.yaml]
       [--scope SUBPATH] [--exclude SUBPATH] [--strict] [--receipts PATH]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import compose_page_contract
import profile_admission

TOOL = "check_boundary_contract"
TOOL_VERSION = "1.1.0"
GATE_ID = "boundary-contract"
# The `Check` cell K00/12 registers for this Gate.
GATE_CHECK = "boundary-contract-summary"

ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
SCOPE_SLOT = "Profile Scope"
BEGIN = kblib.BOUNDARY_PROJECTION_BEGIN
END = kblib.BOUNDARY_PROJECTION_END


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


class Findings:
    def __init__(self):
        self.rows = []

    def add(self, check, target, result, details):
        self.rows.append({"check": check, "target": target,
                          "result": result, "details": details})

    def count(self, result):
        return sum(1 for r in self.rows if r["result"] == result)


def scope_directories(admission, findings):
    """Union of the Profile Scope's registered layer directories."""
    path, error = profile_admission.require_slot(admission, SCOPE_SLOT)
    if error:
        findings.add("boundary-contract-profile", SCOPE_SLOT, "fail",
                     error)
        return []
    try:
        layers = kblib.profile_scope_layers(
            admission.slot_text(SCOPE_SLOT))
    except (OSError, UnicodeError) as exc:
        findings.add("boundary-contract-profile", SCOPE_SLOT, "fail",
                     "cannot read admitted Profile Scope: %s" % exc)
        return []
    directories = sorted({d for dirs in layers.values() for d in dirs})
    if not directories:
        findings.add("boundary-contract-profile", SCOPE_SLOT, "fail",
                     "no Logical Architecture layer table found; the "
                     "default scan scope cannot be resolved")
    return directories


def load_labels(path, findings, text=None):
    """Projection labels from the compiled contract (kernel defaults
    overlaid by its `boundary_projection.labels`, K08/09 Projection)."""
    try:
        data = kblib.parse_yaml_subset(
            read_text(path) if text is None else text)
    except (OSError, kblib.YamlSubsetError) as exc:
        findings.add("boundary-contract-input", path, "fail",
                     "cannot parse the compiled contract: %s — compose it "
                     "with Tools/compose_page_contract.py" % exc)
        return None
    if not isinstance(data, dict) or \
            not isinstance(data.get("fields"), dict):
        findings.add("boundary-contract-input", path, "fail",
                     "the compiled contract carries no fields mapping")
        return None
    projection = data.get("boundary_projection")
    labels = projection.get("labels") \
        if isinstance(projection, dict) else None
    return labels if isinstance(labels, dict) else {}


def resolve_page(root, value):
    """Resolve a page reference with or without the .md suffix."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidates = [value]
    if not value.lower().endswith(".md"):
        candidates.append(value + ".md")
    root_real = os.path.realpath(root)
    for candidate in candidates:
        path = os.path.normpath(os.path.join(root, candidate))
        try:
            inside = os.path.commonpath(
                (root_real, os.path.realpath(path))) == root_real
        except ValueError:
            continue
        if inside and os.path.isfile(path):
            return path
    return None


def boundary_block_of(path):
    """(block, parse_ok) for one page; block is None when absent."""
    raw = kblib.extract_frontmatter(read_text(path))
    if raw is None:
        return None, True
    try:
        fields = kblib.parse_yaml_subset(raw)
    except kblib.YamlSubsetError:
        return None, False
    if not isinstance(fields, dict):
        return None, False
    return fields.get(kblib.BOUNDARY_FIELD), True


def marker_pair(lines):
    """(begin_index, end_index, error) for the projection markers."""
    begins = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if not begins and not ends:
        return None, None, None
    if len(begins) != 1 or len(ends) != 1:
        return None, None, "the page carries %d begin and %d end " \
            "projection marker(s); exactly one well-formed pair is owned" \
            % (len(begins), len(ends))
    if ends[0] < begins[0]:
        return None, None, "the end marker precedes the begin marker"
    return begins[0], ends[0], None


def run(root, profile_override, contract_path, scope, excludes, strict,
        receipts_path):
    root = os.path.abspath(root)
    findings = Findings()
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
    labels = load_labels(
        contract_abs, findings,
        artifact_snapshot.read_text()
        if artifact_snapshot is not None else None)

    scan_roots = []
    if labels is not None and admission is not None:
        if scope:
            scan_roots = [scope]
        else:
            scan_roots = scope_directories(admission, findings)

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

    def excluded(path):
        normalized = os.path.normpath(path)
        return any(normalized == e or normalized.startswith(e + os.sep)
                   for e in exclude_roots)

    pages = [p for p in sorted(set(pages)) if not excluded(p)]

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
        block, parse_ok = boundary_block_of(path)
        if block is None:
            if not parse_ok:
                continue  # frontmatter defects stay with page-contract
            lines = read_text(path).splitlines()
            _b, _e, marker_error = marker_pair(lines)
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
            resolved = resolve_page(root, owner)
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
            owner_block, _ok = boundary_block_of(resolved)
            if owner_block is None:
                findings.add("boundary-reciprocity", target, "candidate",
                             "owner %r carries no boundary block yet; "
                             "migration-tolerated candidate (K08/09)"
                             % owner)
            elif concern not in kblib.boundary_owned_slugs(owner_block):
                findings.add("boundary-reciprocity", target, violation,
                             "owner %r does not claim concern %r in its "
                             "own boundary.owns" % (owner, concern))

        lines = read_text(path).splitlines()
        begin, end, marker_error = marker_pair(lines)
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

    if receipts_path:
        receipts = []
        seq = 1
        for row in findings.rows:
            receipt = kblib.make_receipt(
                TOOL, TOOL_VERSION, "boundary-contract", row["target"],
                row["result"], row["details"], seq, root=root)
            receipt["gate_id"] = GATE_ID
            receipts.append(receipt)
            seq += 1
        summary = kblib.make_receipt(
            TOOL, TOOL_VERSION, GATE_CHECK, "boundary-contract",
            "fail" if fails else ("candidate" if candidates else "pass"),
            "pages=%d boundary_pages=%d fail=%d candidate=%d mode=%s"
            % (len(pages), checked, fails, candidates,
               "strict" if strict else "advisory"),
            seq, root=root)
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
        kblib.write_receipts(receipts_path, receipts)

    if fails:
        return 1
    return 2 if candidates else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate page boundary blocks against the K08/09 page "
                    "boundary contract (gate: boundary-contract; advisory "
                    "by default).")
    parser.add_argument("vault_root", help="vault root directory")
    parser.add_argument("--profile",
                        help="profile directory override; default is the "
                             "selected_profile_manifest of the active "
                             "Standards state")
    parser.add_argument("--contract", default="Tools/page_contract.yaml",
                        help="compiled contract path (default "
                             "Tools/page_contract.yaml)")
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
    args = parser.parse_args(argv)
    return run(args.vault_root, args.profile, args.contract, args.scope,
               args.exclude, args.strict, args.receipts)


if __name__ == "__main__":
    sys.exit(main())
