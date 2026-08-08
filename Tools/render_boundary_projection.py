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

TOOL = "render_boundary_projection"
TOOL_VERSION = "1.0.0"

ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
SCOPE_SLOT = "Profile Scope"
BEGIN = kblib.BOUNDARY_PROJECTION_BEGIN
END = kblib.BOUNDARY_PROJECTION_END


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def resolve_profile_dir(root, override, errors):
    if override:
        profile_dir = override if os.path.isabs(override) \
            else os.path.join(root, override)
        if not os.path.isdir(profile_dir):
            errors.append("--profile does not name an existing directory")
            return None
        return profile_dir
    try:
        state_text = read_text(os.path.join(root, ACTIVE_STATE_PATH))
    except OSError as exc:
        errors.append("cannot read the active Standards state: %s" % exc)
        return None
    state, parse_errors = kblib.active_standards_state(state_text)
    errors.extend(parse_errors)
    manifest = state.get("selected_profile_manifest") or ""
    if "{{" in manifest or not manifest.strip():
        errors.append("no instantiated selected_profile_manifest; pass "
                      "--profile and --scope for a validation run")
        return None
    manifest_path = os.path.join(root, manifest)
    if not os.path.isfile(manifest_path):
        errors.append("selected profile manifest does not exist")
        return None
    return os.path.dirname(manifest_path)


def scope_directories(root, profile_dir, errors):
    try:
        manifest_text = read_text(os.path.join(profile_dir, "profile.md"))
    except OSError as exc:
        errors.append("cannot read the profile manifest: %s" % exc)
        return []
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = bindings.get(SCOPE_SLOT)
    if binding is None:
        errors.append("the manifest does not bind the `Profile Scope` slot")
        return []
    kind, detail = kblib.resolve_profile_binding(binding, root, profile_dir)
    if kind != "path":
        errors.append("Profile Scope binding %r does not resolve" % binding)
        return []
    layers = kblib.profile_scope_layers(read_text(detail))
    directories = sorted({d for dirs in layers.values() for d in dirs})
    if not directories:
        errors.append("no Logical Architecture layer table found")
    return directories


def load_labels(path, errors):
    try:
        data = kblib.parse_yaml_subset(read_text(path))
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
    parser.add_argument("vault_root")
    parser.add_argument("--profile")
    parser.add_argument("--contract", default="Tools/page_contract.yaml",
                        help="compiled contract path (default "
                             "Tools/page_contract.yaml)")
    parser.add_argument("--scope",
                        help="only scan .md files under this subpath")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.vault_root)

    errors = []
    contract_abs = args.contract if os.path.isabs(args.contract) \
        else os.path.join(root, args.contract)
    labels = load_labels(contract_abs, errors)
    scan_roots = []
    if labels is not None:
        if args.scope:
            scan_roots = [args.scope]
        else:
            profile_dir = resolve_profile_dir(root, args.profile, errors)
            if profile_dir is not None:
                scan_roots = scope_directories(root, profile_dir, errors)
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
            kblib.atomic_write_text(path, new_text)
            written += 1
            print("render_boundary_projection: wrote %s" % rel)
        else:
            stale += 1
            print("render_boundary_projection: %s is stale" % rel)

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
