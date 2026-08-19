#!/usr/bin/env python3
"""Boundary projection renderer — the registered generator for the K08/09
`<!-- boundary-projection:begin/end -->` block.

Rule owner:
- "kernel/K08 Metadata and Status/09 Page Boundary Contract.md"
  (Projection: the block between the markers is tool-owned and
  regenerated, never hand-edited; marker placement is curated).

For every page in scope whose frontmatter carries a `boundary` block and
whose body carries exactly one well-formed marker pair, the owned block is
recomputed deterministically from the `boundary` block and the display
labels of the compiled contract's `boundary_projection` (K08/09 defaults
otherwise) — the same rendering `Tools/check_boundary_contract.py`
compares against, imported from kblib so no second rendering truth
exists. A page with a boundary block but no markers is skipped and
counted, never treated as stale: where the block sits is an authoring
decision; only its content is owned here. Malformed markers are input
errors.

Modes: default = report what would render; --check = exit 2 when any
owned block is stale; --apply = write the owned blocks atomically.

Exit codes: 0 = current / applied, 1 = input error, 2 = --check stale.

Usage: python3 render_boundary_projection.py <vault_root>
       [--profile PROFILE_DIR] [--contract Tools/page_contract.yaml]
       [--scope SUBPATH] [--check | --apply]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import compose_page_contract
import profile_admission

TOOL = "render_boundary_projection"
TOOL_VERSION = "1.1.0"

ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
SCOPE_SLOT = "Profile Scope"
BEGIN = kblib.BOUNDARY_PROJECTION_BEGIN
END = kblib.BOUNDARY_PROJECTION_END


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def scope_directories(admission, errors):
    path, error = profile_admission.require_slot(admission, SCOPE_SLOT)
    if error:
        errors.append(error)
        return []
    try:
        layers = kblib.profile_scope_layers(
            admission.slot_text(SCOPE_SLOT))
    except (OSError, UnicodeError) as exc:
        errors.append("cannot read admitted Profile Scope: %s" % exc)
        return []
    directories = sorted({d for dirs in layers.values() for d in dirs})
    if not directories:
        errors.append("no Logical Architecture layer table found")
    return directories


def load_labels(path, errors, text=None):
    try:
        data = kblib.parse_yaml_subset(
            read_text(path) if text is None else text)
    except (OSError, kblib.YamlSubsetError) as exc:
        errors.append("cannot parse the compiled contract: %s — compose it "
                      "with Tools/compose_page_contract.py" % exc)
        return None
    if not isinstance(data, dict) or \
            not isinstance(data.get("fields"), dict):
        errors.append("the compiled contract carries no fields mapping")
        return None
    projection = data.get("boundary_projection")
    labels = projection.get("labels") \
        if isinstance(projection, dict) else None
    return labels if isinstance(labels, dict) else {}


def boundary_block_of(text):
    raw = kblib.extract_frontmatter(text)
    if raw is None:
        return None
    try:
        fields = kblib.parse_yaml_subset(raw)
    except kblib.YamlSubsetError:
        return None
    if not isinstance(fields, dict):
        return None
    return fields.get(kblib.BOUNDARY_FIELD)


def marker_pair(lines):
    begins = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if not begins and not ends:
        return None, None, None
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        return None, None, "malformed projection markers (%d begin, %d end)" \
            % (len(begins), len(ends))
    return begins[0], ends[0], None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render the K08/09 boundary projection blocks from "
                    "page `boundary` frontmatter.")
    parser.add_argument("vault_root", help="vault root directory")
    parser.add_argument("--profile",
                        help="profile directory override; default is the "
                             "selected_profile_manifest of the active "
                             "Standards state")
    parser.add_argument("--contract", default="Tools/page_contract.yaml",
                        help="compiled contract path (default "
                             "Tools/page_contract.yaml)")
    parser.add_argument("--scope",
                        help="only scan .md files under this subpath")
    parser.add_argument("--check", action="store_true",
                        help="exit 2 when any owned block is stale; the "
                             "default report never fails on staleness")
    parser.add_argument("--apply", action="store_true",
                        help="rewrite the stale owned blocks atomically; "
                             "omit to only report what would render")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.vault_root)

    errors = []
    admission, admission_errors = profile_admission.admit_profile(
        root, args.profile, active_state_path=ACTIVE_STATE_PATH)
    errors.extend(admission_errors)
    contract_abs = args.contract if os.path.isabs(args.contract) \
        else os.path.join(root, args.contract)
    artifact_snapshot = None
    if admission is not None:
        artifact_snapshot, artifact_errors = \
            compose_page_contract.admitted_artifact(
                root, contract_abs, admission)
        errors.extend(artifact_errors)
    labels = load_labels(
        contract_abs, errors,
        artifact_snapshot.read_text()
        if artifact_snapshot is not None else None)
    scan_roots = []
    if labels is not None and admission is not None:
        if args.scope:
            scan_roots = [args.scope]
        else:
            scan_roots = scope_directories(admission, errors)
    if errors:
        for error in errors:
            print("render_boundary_projection: %s" % error)
        return 1

    pages = []
    for scan_root in scan_roots:
        base = os.path.normpath(os.path.join(root, scan_root))
        if not os.path.isdir(base) and not (
                os.path.isfile(base) and base.lower().endswith(".md")):
            print("render_boundary_projection: scan root does not exist: %s"
                  % scan_root)
            return 1
        for full, _rel in kblib.iter_md_files(root, scope=scan_root):
            pages.append(full)
    if not pages:
        print("render_boundary_projection: the effective scan set is "
              "empty; a zero-page scan is an invocation error")
        return 1

    stale = 0
    written = 0
    skipped = 0
    malformed = 0
    pending = []
    for path in sorted(set(pages)):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        text = read_text(path)
        block = boundary_block_of(text)
        if block is None:
            continue
        lines = text.splitlines()
        begin, end, marker_error = marker_pair(lines)
        if marker_error:
            print("render_boundary_projection: %s: %s" % (rel, marker_error))
            malformed += 1
            continue
        if begin is None:
            skipped += 1
            continue
        expected = kblib.render_boundary_projection_lines(block, labels)
        current = [line.rstrip() for line in lines[begin:end + 1]]
        if current == expected:
            print("render_boundary_projection: %s is current" % rel)
            continue
        if args.apply:
            new_lines = lines[:begin] + expected + lines[end + 1:]
            new_text = "\n".join(new_lines) + \
                ("\n" if text.endswith("\n") else "")
            pending.append((path, new_text, rel))
        else:
            stale += 1
            print("render_boundary_projection: %s is stale" % rel)

    currency = profile_admission.currency_errors(admission)
    currency.extend(compose_page_contract.artifact_currency_errors(
        root, contract_abs, admission))
    if currency:
        for error in currency:
            print("render_boundary_projection: %s" % error)
        return 1
    for path, new_text, rel in pending:
        kblib.atomic_write_text(path, new_text)
        written += 1
        print("render_boundary_projection: wrote %s" % rel)
    currency = profile_admission.currency_errors(admission)
    currency.extend(compose_page_contract.artifact_currency_errors(
        root, contract_abs, admission))
    if currency:
        for error in currency:
            print("render_boundary_projection: %s" % error)
        return 1

    print("render_boundary_projection: stale=%d written=%d "
          "no_markers=%d malformed=%d"
          % (stale, written, skipped, malformed))
    if malformed:
        return 1
    if args.check and stale:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
