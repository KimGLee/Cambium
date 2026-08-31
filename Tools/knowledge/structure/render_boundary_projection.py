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
       [--profile PROFILE_DIR]
       [--contract .cambium/derived/page_contract.yaml]
       [--scope SUBPATH] [--check | --apply]
"""

import os
import sys

import Tools.platform.common.kblib as kblib
import Tools.knowledge.metadata.compose_page_contract as compose_page_contract
from Tools.knowledge.structure import boundary_contract
import Tools.governance.profile.profile_admission as profile_admission
import Tools.execution.task_runtime.runtime_paths as runtime_paths

TOOL = "render_boundary_projection"
TOOL_VERSION = "1.1.0"

ACTIVE_STATE_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
SCOPE_SLOT = profile_admission.PROFILE_SCOPE_SLOT
def main(argv=None):
    parser = kblib.ArgumentParser(
        description="Render the K08/09 boundary projection blocks from "
                    "page `boundary` frontmatter.")
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
    label_text = None
    if artifact_snapshot is not None:
        label_text = artifact_snapshot.read_text()
    else:
        try:
            label_text = kblib.read_text(contract_abs, errors="replace")
        except OSError as exc:
            errors.append(
                "cannot parse the compiled contract: %s — compose it with "
                "Tools/compose_page_contract.py" % exc
            )
    labels = None
    if label_text is not None:
        labels, label_error = boundary_contract.projection_labels_from_text(
            label_text
        )
        if label_error:
            errors.append(label_error)
    scan_roots = []
    if labels is not None and admission is not None:
        if args.scope:
            scan_roots = [args.scope]
        else:
            scan_roots, scope_errors = profile_admission.scope_directories(
                admission)
            errors.extend(scope_errors)
    if errors:
        for error in errors:
            print("render_boundary_projection: %s" % error)
        return 1

    pages = []
    for scan_root in scan_roots:
        base = os.path.normpath(os.path.join(root, scan_root))
        scope_capability = kblib.inherited_path_capability(
            scan_root, "transaction")
        scope_exists = (scope_capability is not None and
                        scope_capability["exists"])
        if not scope_exists and not os.path.isdir(base) and not (
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
        text = kblib.read_text(path, errors="replace")
        block, _parse_ok = boundary_contract.boundary_block_from_text(text)
        if block is None:
            continue
        lines = text.splitlines()
        begin, end, marker_error = boundary_contract.projection_marker_pair(lines)
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
