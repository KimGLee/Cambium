#!/usr/bin/env python3
"""Structure Registry resolution check — the `structure-registry` gate.

Rule owners:
- "kernel/K01 Scope and Architecture/05 Structural Unit Interface.md"
  (unit kinds, module admission, role implementation modes, registry
  ownership boundaries);
- "kernel/K01 Scope and Architecture/06 Support Layer Structural
  Interfaces.md" (support layer shared base, layouts, role-specific
  bindings);
- "kernel/K00 Standards Control/profile-interface.yaml" and K01/05-K01/06
  (the common slot contract and structural semantics).

The registry's byte-level shape contract lives in
``kblib.validate_structure_registry_shape`` and is shared with
``check_profile.py``; this tool adds the vault-resolution half:

- every unit root, entry, and role path resolves inside the vault;
- every derived role names a registered projection capability and either a
  repository-relative corpus artifact or a runtime object ID that capability
  declares; Profile bytes never bind Tool or `.cambium` implementation paths;
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

import os
import sys

import Tools.platform.common.kblib as kblib
from Tools.execution.evidence import receipt_type_contract
import Tools.governance.control.metadata_execution_contract as metadata_execution_contract
import Tools.knowledge.metadata.page_frontmatter_contract as page_frontmatter_contract
import Tools.governance.profile.profile_admission as profile_admission
import Tools.governance.profile.profile_contract as profile_contract
import Tools.execution.task_runtime.runtime_paths as runtime_paths
from Tools.platform.common import reporting

TOOL = "check_structure"
TOOL_VERSION = "1.2.0"
GATE_ID = "structure-registry"
# The `Check` cell K00/12 registers for this Gate; every receipt this tool
# offers as gate evidence carries it verbatim.
GATE_CHECK = "structure-registry-summary"
RECEIPT_TYPE_ID = "structure-registry-gate-receipt-v1"


def current_receipt_errors(record, *, root=None):
    errors = receipt_type_contract.base_receipt_errors(
        record, receipt_type_id=RECEIPT_TYPE_ID,
        tool=TOOL, tool_version=TOOL_VERSION,
        checks=("structure-registry", GATE_CHECK))
    if isinstance(record, dict) and record.get("gate_id") != GATE_ID:
        errors.append("gate_id must identify structure-registry")
    return errors

JSON_FLAG_HELP = reporting.JSON_CHECK_HELP
_JSON_REPORTER = reporting.RedirectedJsonReceipts()


ACTIVE_STATE_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
STRUCTURE_SLOT = profile_contract.STRUCTURE_REGISTRY_SLOT
CORPUS_SLOT = profile_contract.CORPUS_PLANNING_SLOT
SCOPE_SLOT = profile_contract.PROFILE_SCOPE_SLOT
COVERAGE_LEDGER_PATH = runtime_paths.COVERAGE_PATH


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
    text = kblib.strip_code(kblib.read_text(path, errors="replace"))
    return any(h.strip() == heading.strip()
               for _lineno, _level, h in kblib.headings_of(text))


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
        input_owner = role.get("inputs_owner")
        owner_kind = kblib.structure_input_owner_reference_kind(input_owner)
        if owner_kind == "corpus-artifact":
            vault_path(root, input_owner, findings, "structure-role",
                       label + ":inputs_owner")
        if role.get("path") is not None:
            path = vault_path(root, role.get("path"), findings,
                              "structure-role", label + ":path")
            if path is not None and isinstance(role.get("heading"), str):
                if not heading_exists(path, role["heading"]):
                    findings.add("structure-role", label + ":heading", "fail",
                                 "heading %r not found in %r"
                                 % (role["heading"], role.get("path")))


def projection_capability_entries(root, findings, input_snapshots):
    """Bind the root-owned projection-capability namespace once."""
    relative = metadata_execution_contract.DEFAULT_CAPABILITIES_PATH
    try:
        document, snapshot = metadata_execution_contract.\
            load_operation_capabilities_snapshot(root, relative)
    except metadata_execution_contract.MetadataExecutionContractError as exc:
        findings.add(
            "structure-capability-registry", relative, "fail",
            "cannot bind the root-owned Tool capability registry: %s" % exc)
        return None
    input_snapshots.append(snapshot)
    return {
        entry["capability_id"]: entry
        for entry in document["capabilities"]
        if entry["kind"] == "projection"
    }


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


def global_map_entry_ids(path, text=None):
    try:
        data = kblib.parse_yaml_subset(
            kblib.read_text(path, errors="replace") if text is None else text)
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



def md_files_under(path):
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                yield os.path.join(dirpath, name)


def run(root, profile_override, receipts_path):
    root = os.path.abspath(root)
    findings = reporting.FindingSet()
    summary = {"units": 0, "modules": 0, "support_layers": 0}
    input_snapshots = []
    global_map_snapshot = None
    coverage_snapshot = None

    admission, admission_errors = profile_admission.admit_profile(
        root, profile_override, active_state_path=ACTIVE_STATE_PATH)
    for error in admission_errors:
        findings.add("structure-profile-load", ACTIVE_STATE_PATH, "fail",
                     error)
    registry = None
    registry_rel = None
    if admission is not None:
        _registry_value, error = profile_admission.require_slot(
            admission, STRUCTURE_SLOT)
        if error:
            findings.add("structure-slot", STRUCTURE_SLOT, "fail", error)
        else:
            registry = admission.slot_document(STRUCTURE_SLOT)
            registry_rel = admission.manifest_repo_path + "#slots.structure-registry"

    state = None
    if registry is not None:
        for check, target, details in \
                kblib.validate_structure_registry_shape(
                    registry, registry_rel):
            findings.add(check, target, "fail", details)
        applicability = registry.get("applicability")
        state = applicability.get("state") \
            if isinstance(applicability, dict) else None

    if registry is not None and not findings.failures() and \
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
        scope, error = profile_admission.require_slot(
            admission, SCOPE_SLOT)
        if error:
            findings.add("structure-slot", SCOPE_SLOT, "fail", error)
        if scope is not None:
            scope_layers = {row["layer_id"]: tuple(row["directories"])
                            for row in scope["logical_architecture"]}
            if not scope_layers:
                findings.add(
                    "structure-scope", SCOPE_SLOT, "fail",
                    "no Logical Architecture layers found in the "
                    "Profile Scope; layer membership cannot be resolved")
        all_layer_dirs = {d for dirs in scope_layers.values() for d in dirs}

        # Corpus Planning / Global Map context.
        cp_state, gm_ids = None, None
        cp_slot, error = profile_admission.require_slot(
            admission, CORPUS_SLOT)
        if error:
            findings.add("structure-slot", CORPUS_SLOT, "fail", error)
        if cp_slot is not None:
            cp_data = admission.slot_document(CORPUS_SLOT)
            applicability = cp_data.get("applicability") \
                if isinstance(cp_data, dict) else None
            cp_state = applicability.get("state") \
                if isinstance(applicability, dict) else None
            bindings = cp_data.get("artifact_bindings") \
                if isinstance(cp_data, dict) else None
            gm_rel = bindings.get("global_map") \
                if isinstance(bindings, dict) else None
            if cp_state == "configured" and gm_rel:
                gm_path = vault_path(root, gm_rel, findings,
                                     "structure-global-map",
                                     CORPUS_SLOT + ":global_map")
                if gm_path is not None:
                    try:
                        gm_snapshot = kblib.repository_file_snapshot(
                            root, gm_rel, singly_linked=True)
                        gm_ids = global_map_entry_ids(
                            gm_path, gm_snapshot.read_text())
                    except (OSError, UnicodeError, ValueError) as exc:
                        findings.add(
                            "structure-global-map", gm_rel, "fail",
                            "cannot bind Global Map to one immutable input: %s"
                            % exc)
                    else:
                        input_snapshots.append(gm_snapshot)
                        global_map_snapshot = gm_snapshot
                    if gm_ids is None:
                        findings.add("structure-global-map", gm_rel, "fail",
                                     "cannot read Global Map entries")

        unit_roots = {u.get("id"): u.get("root") for u in units
                      if isinstance(u, dict)}
        projection_capabilities = projection_capability_entries(
            root, findings, input_snapshots)
        if projection_capabilities is not None:
            for check, label, details in \
                    kblib.validate_structure_registry_references(
                        registry, projection_capabilities, registry_rel):
                findings.add(check, label, "fail", details)

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
                actual = page_frontmatter_contract.page_type(entry_abs)
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
                actual = page_frontmatter_contract.page_type(entry_abs)
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
                        value = page_frontmatter_contract.scalar_field(
                            md_path, page_field)
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
                ledger_snapshot = kblib.repository_file_snapshot(
                    root, COVERAGE_LEDGER_PATH, singly_linked=True)
                ledger = kblib.parse_yaml_subset(ledger_snapshot.read_text())
            except (OSError, UnicodeError, ValueError,
                    kblib.YamlSubsetError) as exc:
                ledger = None
                findings.add(
                    "structure-coverage", COVERAGE_LEDGER_PATH, "fail",
                    "cannot bind Coverage Ledger to one immutable input: %s" %
                    exc)
            else:
                input_snapshots.append(ledger_snapshot)
                coverage_snapshot = ledger_snapshot
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

    if admission is not None:
        for error in profile_admission.currency_errors(admission):
            findings.add("structure-profile-currency",
                         admission.manifest_repo_path, "fail", error)
    for snapshot in input_snapshots:
        try:
            current = kblib.repository_file_snapshot(
                root, snapshot.repository_path, singly_linked=True)
        except (OSError, ValueError) as exc:
            findings.add(
                "structure-input-currency", snapshot.repository_path,
                "fail", "cannot re-bind admitted input: %s" % exc)
            continue
        if current.sha256 != snapshot.sha256:
            findings.add(
                "structure-input-currency", snapshot.repository_path,
                "fail", "input changed during Structure Registry validation")
    fails = findings.failures()
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

    if receipts_path or _JSON_REPORTER.enabled:
        # The receipt set is this run's structured result, so `--json` builds
        # it even with no receipts file to append to.  Neither destination
        # changes what the receipts say.
        receipts = []
        seq = 1
        for row in findings.rows:
            receipt = kblib.make_receipt(
                TOOL, TOOL_VERSION, "structure-registry", row["target"],
                row["result"], row["details"], seq,
                receipt_type_id=RECEIPT_TYPE_ID, root=root)
            receipt["gate_id"] = GATE_ID
            receipts.append(receipt)
            seq += 1
        summary_receipt = kblib.make_receipt(
            TOOL, TOOL_VERSION, GATE_CHECK, "structure-registry",
            "fail" if fails else "pass",
            "units=%d modules=%d support_layers=%d errors=%d state=%s"
            % (summary["units"], summary["modules"],
               summary["support_layers"], len(fails), state or "unresolved"),
            seq, receipt_type_id=RECEIPT_TYPE_ID, root=root)
        summary_receipt["gate_id"] = GATE_ID
        if admission is not None:
            summary_receipt.update(dict(zip(
                profile_contract.PROFILE_LOAD_EVIDENCE_FIELDS,
                (
                    admission.manifest_repo_path,
                    admission.evaluation.profile_snapshot_sha256,
                    admission.evaluation.profile_contract_fingerprint,
                    admission.evaluation.profile_load_inputs_sha256,
                ),
            )))
        if global_map_snapshot is not None:
            summary_receipt["global_map_path"] = \
                global_map_snapshot.repository_path
            summary_receipt["global_map_sha256"] = \
                global_map_snapshot.sha256
        if coverage_snapshot is not None:
            summary_receipt["coverage_ledger_sha256"] = \
                coverage_snapshot.sha256
        receipts.append(summary_receipt)
        if receipts_path:
            kblib.write_receipts(receipts_path, receipts)
        _JSON_REPORTER.record(receipts)

    return 1 if fails else 0


def main(argv=None):
    """CLI entry point; `--json` projects the produced receipts onto stdout."""
    return reporting.run_redirected_json(
        _JSON_REPORTER, lambda: _main(argv))


def _main(argv=None):
    parser = kblib.ArgumentParser(
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
    parser.add_argument("--json", action="store_true", help=JSON_FLAG_HELP)
    args = parser.parse_args(argv)
    _JSON_REPORTER.begin(args.json)
    return run(args.vault_root, args.profile, args.receipts)


if __name__ == "__main__":
    sys.exit(main())
