#!/usr/bin/env python3
"""Structure Registry resolution check — the `structure-registry` gate.

Rule owners:
- "kernel/K01 Scope and Architecture/05 Structural Unit Interface.md"
  (unit kinds, module admission, role implementation modes, registry
  ownership boundaries);
- "kernel/K01 Scope and Architecture/06 Support Layer Structural
  Interfaces.md" (support layer shared base, layouts, role-specific
  bindings);
- "profiles/README.md#Structure Registry Slot" (the closed slot shape,
  carried by profiles/_template/structure-registry.yaml).

The registry's byte-level shape contract lives in
``kblib.validate_structure_registry_shape`` and is shared with
``check_profile.py``; this tool adds the vault-resolution half:

- every unit root, entry, and role path resolves inside the vault;
- embedded headings exist in their pages; a declared ``expected_type``
  matches the entry page's frontmatter ``type``;
- a module root sits strictly inside its parent's root; a domain root is one
  of the Profile Scope's registered layer directories, and a support layer
  root belongs to its declared ``layer_id``;
- ``flat`` layout has no content pages in subdirectories; ``grouped`` layout
  classes map one-to-one onto existing directories under the root, and every
  page under a class directory carries the declared ``page_field`` value —
  the check compares declared class against path and never infers a class
  from content;
- ``global_map_entry`` values resolve to entry IDs of the configured Corpus
  Planning Global Map, and are null when Corpus Planning is not configured;
- when the runtime Coverage Ledger records ``structural_unit`` values, each
  references a registered unit id.

This gate proves structure declarations only. Whether a class assignment,
promotion, or evidence binding is semantically right stays with manual review
(K12/03); content acceptance is not decided here.

Fail-closed: a missing or unresolvable selected profile, an unbound or
unreadable registry, or a `configured` registry over an empty resolution
scope is result=fail, never a pass.

Exit codes: 0 = all pass, 1 = at least one fail.

Usage: python3 check_structure.py <vault_root> [--profile PROFILE_DIR]
       [--receipts PATH]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_structure"
TOOL_VERSION = "1.0.0"
GATE_ID = "structure-registry"
# The `Check` cell K00/12 registers for this Gate; every receipt this tool
# offers as gate evidence carries it verbatim.
GATE_CHECK = "structure-registry-summary"

ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
STRUCTURE_SLOT = "Structure Registry"
CORPUS_SLOT = "Corpus Planning"
SCOPE_SLOT = "Profile Scope"
COVERAGE_LEDGER_PATH = ".cambium/state/coverage_ledger.yaml"


class Findings:
    def __init__(self):
        self.rows = []

    def add(self, check, target, result, details):
        self.rows.append({"check": check, "target": target,
                          "result": result, "details": details})

    def fails(self):
        return [r for r in self.rows if r["result"] == "fail"]


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def resolve_profile_dir(root, override, findings):
    """Return the selected profile directory, or None (fail recorded)."""
    if override:
        profile_dir = os.path.join(root, override) \
            if not os.path.isabs(override) else override
        if not os.path.isdir(profile_dir):
            findings.add("structure-profile", override, "fail",
                         "--profile does not name an existing directory")
            return None
        return profile_dir
    state_path = os.path.join(root, ACTIVE_STATE_PATH)
    try:
        state_text = read_text(state_path)
    except OSError as exc:
        findings.add("structure-profile", ACTIVE_STATE_PATH, "fail",
                     "cannot read the active Standards state: %s" % exc)
        return None
    state, errors = kblib.active_standards_state(state_text)
    for error in errors:
        findings.add("structure-profile", ACTIVE_STATE_PATH, "fail", error)
    manifest = state.get("selected_profile_manifest") or ""
    if "{{" in manifest or not manifest.strip():
        findings.add(
            "structure-profile", ACTIVE_STATE_PATH, "fail",
            "no instantiated selected_profile_manifest; pass --profile to "
            "check an unselected profile directory")
        return None
    manifest_path = os.path.join(root, manifest)
    if not os.path.isfile(manifest_path):
        findings.add("structure-profile", manifest, "fail",
                     "selected profile manifest does not exist")
        return None
    return os.path.dirname(manifest_path)


def slot_path(root, profile_dir, manifest_text, slot, findings,
              required=True):
    """Resolve one slot binding to an absolute path, or None."""
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = bindings.get(slot)
    if binding is None:
        if required:
            findings.add("structure-slot", slot, "fail",
                         "the selected manifest does not bind the `%s` slot"
                         % slot)
        return None
    kind, detail = kblib.resolve_profile_binding(binding, root, profile_dir)
    if kind != "path":
        findings.add("structure-slot", slot, "fail",
                     "slot `%s` binding %r does not resolve to a profile "
                     "file" % (slot, binding))
        return None
    return detail


def vault_path(root, relative, findings, check, label, kind="file"):
    """Resolve a repository-relative path inside the vault; None on fail."""
    if not isinstance(relative, str) or not relative.strip():
        findings.add(check, label, "fail", "empty path")
        return None
    candidate = os.path.normpath(os.path.join(root, relative))
    root_real = os.path.realpath(root)
    try:
        inside = os.path.commonpath(
            (root_real, os.path.realpath(candidate))) == root_real
    except ValueError:
        inside = False
    if not inside:
        findings.add(check, label, "fail",
                     "path %r escapes the vault root" % relative)
        return None
    exists = os.path.isdir(candidate) if kind == "dir" \
        else os.path.isfile(candidate)
    if not exists:
        findings.add(check, label, "fail",
                     "%s %r does not exist" % (kind, relative))
        return None
    return candidate


def heading_exists(path, heading):
    text = kblib.strip_code(read_text(path))
    return any(h.strip() == heading.strip()
               for _lineno, _level, h in kblib.headings_of(text))


def page_type(path):
    raw = kblib.extract_frontmatter(read_text(path))
    if raw is None:
        return None
    try:
        fields = kblib.parse_yaml_subset(raw)
    except kblib.YamlSubsetError:
        return None
    value = fields.get("type") if isinstance(fields, dict) else None
    return str(value) if value is not None else None


def page_field_value(path, field):
    raw = kblib.extract_frontmatter(read_text(path))
    if raw is None:
        return None
    try:
        fields = kblib.parse_yaml_subset(raw)
    except kblib.YamlSubsetError:
        return None
    value = fields.get(field) if isinstance(fields, dict) else None
    return str(value) if value is not None else None


def check_role(root, findings, label, role):
    """Vault resolution for one already-shape-valid role mapping."""
    if not isinstance(role, dict):
        return
    mode = role.get("mode")
    if mode == "embedded":
        path = vault_path(root, role.get("path"), findings,
                          "structure-role", label + ":path")
        if path is not None and isinstance(role.get("heading"), str):
            if not heading_exists(path, role["heading"]):
                findings.add("structure-role", label + ":heading", "fail",
                             "heading %r not found in %r"
                             % (role["heading"], role.get("path")))
    elif mode == "standalone":
        vault_path(root, role.get("path"), findings, "structure-role",
                   label + ":path")
    elif mode == "derived":
        vault_path(root, role.get("generator"), findings, "structure-role",
                   label + ":generator")
        vault_path(root, role.get("inputs_owner"), findings,
                   "structure-role", label + ":inputs_owner")
        if role.get("path") is not None:
            path = vault_path(root, role.get("path"), findings,
                              "structure-role", label + ":path")
            if path is not None and isinstance(role.get("heading"), str):
                if not heading_exists(path, role["heading"]):
                    findings.add("structure-role", label + ":heading", "fail",
                                 "heading %r not found in %r"
                                 % (role["heading"], role.get("path")))


def check_reference(root, findings, label, value):
    """Resolve a path-like reference, tolerating a `#Heading` suffix."""
    if not isinstance(value, str) or not value.strip():
        return
    target, _, heading = value.partition("#")
    target = target.strip()
    if "/" not in target and not target.lower().endswith((".md", ".yaml")):
        return  # a field name or symbolic reference, validated by shape
    kind = "dir" if not target.lower().endswith(
        (".md", ".yaml", ".yml", ".py", ".jsonl")) else "file"
    path = vault_path(root, target, findings, "structure-reference", label,
                      kind=kind)
    if path is not None and heading.strip() and kind == "file" and \
            target.lower().endswith(".md"):
        if not heading_exists(path, heading.strip()):
            findings.add("structure-reference", label, "fail",
                         "heading %r not found in %r"
                         % (heading.strip(), target))


def under(root, child_rel, parent_rel):
    child = os.path.normpath(os.path.join(root, child_rel))
    parent = os.path.normpath(os.path.join(root, parent_rel))
    try:
        return os.path.commonpath((parent, child)) == parent \
            and child != parent
    except ValueError:
        return False


def global_map_entry_ids(path):
    try:
        data = kblib.parse_yaml_subset(read_text(path))
    except (OSError, kblib.YamlSubsetError):
        return None
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None
    ids = set()
    for entry in entries:
        if isinstance(entry, dict) and entry.get("entry_id"):
            ids.add(str(entry["entry_id"]))
    return ids


def corpus_planning_state(path):
    """Return (state, global_map_relpath) of the Corpus Planning slot."""
    try:
        data = kblib.parse_yaml_subset(read_text(path))
    except (OSError, kblib.YamlSubsetError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    applicability = data.get("applicability")
    state = applicability.get("state") \
        if isinstance(applicability, dict) else None
    bindings = data.get("artifact_bindings")
    gm = bindings.get("global_map") if isinstance(bindings, dict) else None
    return state, gm


def md_files_under(path):
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                yield os.path.join(dirpath, name)


def run(root, profile_override, receipts_path):
    findings = Findings()
    summary = {"units": 0, "modules": 0, "support_layers": 0}

    profile_dir = resolve_profile_dir(root, profile_override, findings)
    registry = None
    manifest_text = None
    if profile_dir is not None:
        manifest_path = os.path.join(profile_dir, "profile.md")
        try:
            manifest_text = read_text(manifest_path)
        except OSError as exc:
            findings.add("structure-profile", manifest_path, "fail",
                         "cannot read the profile manifest: %s" % exc)
    registry_path = None
    if manifest_text is not None:
        registry_path = slot_path(root, profile_dir, manifest_text,
                                  STRUCTURE_SLOT, findings)
    if registry_path is not None:
        if not registry_path.lower().endswith(".yaml"):
            findings.add("structure-slot", STRUCTURE_SLOT, "fail",
                         "Structure Registry must bind a restricted-YAML "
                         ".yaml file")
        else:
            try:
                registry = kblib.parse_yaml_subset(read_text(registry_path))
            except (OSError, kblib.YamlSubsetError) as exc:
                findings.add("structure-registry", STRUCTURE_SLOT, "fail",
                             "cannot parse the registry: %s" % exc)

    state = None
    if registry is not None:
        registry_rel = os.path.relpath(registry_path, root).replace(
            os.sep, "/")
        for check, target, details in \
                kblib.validate_structure_registry_shape(
                    registry, registry_rel):
            findings.add(check, target, "fail", details)
        applicability = registry.get("applicability")
        state = applicability.get("state") \
            if isinstance(applicability, dict) else None

    if registry is not None and not findings.fails() and \
            state == "configured":
        units = registry.get("units") or []
        layers = registry.get("support_layers") or []
        summary["units"] = len(units)
        summary["modules"] = sum(1 for u in units
                                 if isinstance(u, dict)
                                 and u.get("kind") == "module")
        summary["support_layers"] = len(layers)

        # Profile Scope layer directories.
        scope_layers = {}
        scope_path = slot_path(root, profile_dir, manifest_text, SCOPE_SLOT,
                               findings)
        if scope_path is not None:
            scope_layers = kblib.profile_scope_layers(read_text(scope_path))
            if not scope_layers:
                findings.add(
                    "structure-scope", SCOPE_SLOT, "fail",
                    "no Logical Architecture layer table found in the "
                    "Profile Scope; layer membership cannot be resolved")
        all_layer_dirs = {d for dirs in scope_layers.values() for d in dirs}

        # Corpus Planning / Global Map context.
        cp_state, gm_ids = None, None
        cp_path = slot_path(root, profile_dir, manifest_text, CORPUS_SLOT,
                            findings, required=False)
        if cp_path is not None:
            cp_state, gm_rel = corpus_planning_state(cp_path)
            if cp_state == "configured" and gm_rel:
                gm_path = vault_path(root, gm_rel, findings,
                                     "structure-global-map",
                                     CORPUS_SLOT + ":global_map")
                if gm_path is not None:
                    gm_ids = global_map_entry_ids(gm_path)
                    if gm_ids is None:
                        findings.add("structure-global-map", gm_rel, "fail",
                                     "cannot read Global Map entries")

        unit_roots = {u.get("id"): u.get("root") for u in units
                      if isinstance(u, dict)}

        def check_global_map_binding(label, value):
            if value is None:
                return
            if cp_state != "configured":
                findings.add(
                    "structure-global-map", label, "fail",
                    "global_map_entry %r is declared but Corpus Planning is "
                    "not configured; the binding must be null" % value)
            elif gm_ids is not None and value not in gm_ids:
                findings.add("structure-global-map", label, "fail",
                             "entry id %r is not registered in the Global "
                             "Map" % value)

        for index, unit in enumerate(units):
            if not isinstance(unit, dict):
                continue
            label = "units[%d]:%s" % (index, unit.get("id"))
            root_rel = unit.get("root")
            root_abs = vault_path(root, root_rel, findings, "structure-unit",
                                  label + ":root", kind="dir")
            entry = unit.get("entry") or {}
            entry_abs = None
            if isinstance(entry, dict):
                entry_abs = vault_path(root, entry.get("path"), findings,
                                       "structure-unit", label + ":entry")
            if entry_abs is not None and root_abs is not None and \
                    not under(root, entry.get("path"), root_rel):
                findings.add("structure-unit", label + ":entry", "fail",
                             "the canonical entry must sit inside the unit "
                             "root %r" % root_rel)
            expected = entry.get("expected_type") \
                if isinstance(entry, dict) else None
            if entry_abs is not None and expected is not None:
                actual = page_type(entry_abs)
                if actual != expected:
                    findings.add(
                        "structure-unit", label + ":entry:expected_type",
                        "fail",
                        "entry page type is %r, expected %r"
                        % (actual, expected))
            kind = unit.get("kind")
            if kind == "domain" and scope_layers and root_rel is not None \
                    and root_rel not in all_layer_dirs:
                findings.add(
                    "structure-unit", label + ":root", "fail",
                    "a domain root must be one of the Profile Scope's "
                    "registered layer directories; %r is not" % root_rel)
            if kind == "module":
                parent_root = unit_roots.get(unit.get("parent"))
                if parent_root and root_rel and \
                        not under(root, root_rel, parent_root):
                    findings.add(
                        "structure-unit", label + ":root", "fail",
                        "a module root must sit strictly inside its "
                        "parent's root %r" % parent_root)
            check_global_map_binding(label + ":global_map_entry",
                                     unit.get("global_map_entry"))
            roles = unit.get("roles") or {}
            if isinstance(roles, dict):
                for role_name, role in sorted(roles.items()):
                    check_role(root, findings,
                               "%s:roles:%s" % (label, role_name), role)

        for index, layer in enumerate(layers):
            if not isinstance(layer, dict):
                continue
            label = "support_layers[%d]:%s" % (index, layer.get("layer_id"))
            root_rel = layer.get("root")
            root_abs = vault_path(root, root_rel, findings,
                                  "structure-layer", label + ":root",
                                  kind="dir")
            layer_id = layer.get("layer_id")
            if scope_layers and layer_id is not None:
                registered = scope_layers.get(layer_id)
                if registered is None:
                    findings.add(
                        "structure-layer", label + ":layer_id", "fail",
                        "%r is not a Layer ID registered by the Profile "
                        "Scope Logical Architecture" % layer_id)
                elif root_rel is not None and root_rel not in registered:
                    findings.add(
                        "structure-layer", label + ":root", "fail",
                        "root %r is not a registered directory of layer %r"
                        % (root_rel, layer_id))
            entry = layer.get("entry") or {}
            entry_abs = None
            entry_rel = entry.get("path") if isinstance(entry, dict) else None
            if isinstance(entry, dict):
                entry_abs = vault_path(root, entry_rel, findings,
                                       "structure-layer", label + ":entry")
            if entry_abs is not None and root_abs is not None and \
                    not under(root, entry_rel, root_rel):
                findings.add("structure-layer", label + ":entry", "fail",
                             "the canonical entry must sit inside the layer "
                             "root %r" % root_rel)
            expected = entry.get("expected_type") \
                if isinstance(entry, dict) else None
            if entry_abs is not None and expected is not None:
                actual = page_type(entry_abs)
                if actual != expected:
                    findings.add(
                        "structure-layer", label + ":entry:expected_type",
                        "fail",
                        "entry page type is %r, expected %r"
                        % (actual, expected))
            check_global_map_binding(label + ":global_map_entry",
                                     layer.get("global_map_entry"))
            check_role(root, findings, label + ":coverage",
                       layer.get("coverage"))

            layout = layer.get("layout")
            if root_abs is not None and layout == "flat":
                for md_path in md_files_under(root_abs):
                    rel = os.path.relpath(md_path, root_abs)
                    if os.sep in rel:
                        findings.add(
                            "structure-layout", label, "fail",
                            "flat layout, but %r sits in a subdirectory of "
                            "%r" % (rel.replace(os.sep, "/"), root_rel))
            taxonomy = layer.get("taxonomy")
            if root_abs is not None and layout == "grouped" and \
                    isinstance(taxonomy, dict):
                page_field = taxonomy.get("page_field")
                class_dirs = {}
                for row in taxonomy.get("classes") or []:
                    if not isinstance(row, dict):
                        continue
                    class_name = row.get("class")
                    directory = row.get("directory")
                    c_label = "%s:taxonomy:%s" % (label, class_name)
                    dir_abs = vault_path(root, directory, findings,
                                         "structure-layout",
                                         c_label + ":directory", kind="dir")
                    if dir_abs is not None and \
                            not under(root, directory, root_rel):
                        findings.add(
                            "structure-layout", c_label, "fail",
                            "class directory %r must sit inside the layer "
                            "root %r" % (directory, root_rel))
                    if dir_abs is not None:
                        class_dirs[class_name] = (directory, dir_abs)
                covered = set()
                for class_name, (directory, dir_abs) in \
                        sorted(class_dirs.items()):
                    for md_path in md_files_under(dir_abs):
                        covered.add(os.path.realpath(md_path))
                        if not isinstance(page_field, str):
                            continue
                        value = page_field_value(md_path, page_field)
                        rel = os.path.relpath(md_path, root).replace(
                            os.sep, "/")
                        if value != class_name:
                            findings.add(
                                "structure-layout",
                                "%s:%s" % (label, rel), "fail",
                                "page under class directory %r carries "
                                "%s=%r, expected %r; the declared class and "
                                "the path must agree"
                                % (directory, page_field, value, class_name))
                entry_real = os.path.realpath(entry_abs) \
                    if entry_abs is not None else None
                for md_path in md_files_under(root_abs):
                    real = os.path.realpath(md_path)
                    if real == entry_real or real in covered:
                        continue
                    rel = os.path.relpath(md_path, root).replace(os.sep, "/")
                    findings.add(
                        "structure-layout", "%s:%s" % (label, rel), "fail",
                        "grouped layout, but this page is neither the "
                        "canonical entry nor inside a registered class "
                        "directory")

            bindings = layer.get("bindings") or {}
            if isinstance(bindings, dict):
                for field, value in sorted(bindings.items()):
                    if field == "readiness_projection" and \
                            isinstance(value, dict):
                        check_role(root, findings,
                                   "%s:bindings:%s" % (label, field), value)
                    elif isinstance(value, str):
                        check_reference(root, findings,
                                        "%s:bindings:%s" % (label, field),
                                        value)

        # Coverage Ledger structural_unit references.
        ledger_path = os.path.join(root, COVERAGE_LEDGER_PATH)
        if os.path.isfile(ledger_path):
            try:
                ledger = kblib.parse_yaml_subset(read_text(ledger_path))
            except kblib.YamlSubsetError:
                ledger = None
            pages = ledger.get("pages") if isinstance(ledger, dict) else None
            registered_ids = set(unit_roots)
            registered_ids.update(
                layer.get("layer_id") for layer in layers
                if isinstance(layer, dict) and layer.get("layer_id"))
            for page in pages or []:
                if not isinstance(page, dict):
                    continue
                ref = page.get("structural_unit")
                if ref is not None and str(ref) not in registered_ids:
                    findings.add(
                        "structure-coverage",
                        str(page.get("path")), "fail",
                        "Coverage records structural_unit %r, which is not "
                        "a registered unit or support layer id" % ref)

    fails = findings.fails()
    print("check_structure: units=%d modules=%d support_layers=%d state=%s"
          % (summary["units"], summary["modules"], summary["support_layers"],
             state or "unresolved"))
    for row in findings.rows:
        if row["result"] != "pass":
            print("  [%s] %s (%s): %s" % (row["result"], row["check"],
                                          row["target"], row["details"]))
    print("  errors=%d" % len(fails))
    if fails:
        print("  Conclusion: structure registry resolution failed "
              "(K01/05, K01/06).")
    elif state == "not-applicable":
        print("  Conclusion: registry declares not-applicable with an empty "
              "unit set; nothing to resolve.")
    else:
        print("  Conclusion: every registered unit and support layer "
              "resolves against the vault. This proves structure "
              "declarations, not content quality.")

    if receipts_path:
        receipts = []
        seq = 1
        for row in findings.rows:
            receipt = kblib.make_receipt(
                TOOL, TOOL_VERSION, "structure-registry", row["target"],
                row["result"], row["details"], seq, root=root)
            receipt["gate_id"] = GATE_ID
            receipts.append(receipt)
            seq += 1
        summary_receipt = kblib.make_receipt(
            TOOL, TOOL_VERSION, GATE_CHECK, "structure-registry",
            "fail" if fails else "pass",
            "units=%d modules=%d support_layers=%d errors=%d state=%s"
            % (summary["units"], summary["modules"],
               summary["support_layers"], len(fails), state or "unresolved"),
            seq, root=root)
        summary_receipt["gate_id"] = GATE_ID
        receipts.append(summary_receipt)
        kblib.write_receipts(receipts_path, receipts)

    return 1 if fails else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate the selected profile's Structure Registry "
                    "against the vault (gate: structure-registry).")
    parser.add_argument("vault_root", help="vault root directory")
    parser.add_argument("--profile",
                        help="profile directory override; default is the "
                             "selected_profile_manifest of the active "
                             "Standards state")
    parser.add_argument("--receipts",
                        help="JSONL path to append machine-readable "
                             "receipts to")
    args = parser.parse_args(argv)
    return run(args.vault_root, args.profile, args.receipts)


if __name__ == "__main__":
    sys.exit(main())
