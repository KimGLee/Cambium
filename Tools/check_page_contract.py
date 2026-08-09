#!/usr/bin/env python3
"""Frontmatter page-contract check — the `page-contract` gate (advisory).

Rule owners:
- "kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract.md"
  (modes, two-layer composition, unknown-field closure, enablement);
- "kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection
  Authority.md" (derived persistence, projection reconciliation,
  user-owned absence);
- "kernel/K08 Metadata and Status/08 Relationship Metadata Contract.md"
  (relationship shapes, directions, and target types).

Input is the compiled contract produced by Tools/compose_page_contract.py
(Tools/page_contract.yaml by default) — like Tools/vocab.yaml it exists only
once a profile is selected and composed, and an absent, empty, or unparseable
contract is a failure, never a pass. Scope defaults to the union of the
selected Profile Scope's registered layer directories (knowledge content
only); --scope narrows to one directory or page. A zero-page effective scan
set fails closed.

Per page, against the compiled contract:
- required present and nonempty; conditional required when its same-page
  condition holds; a present-but-empty value is placeholder noise in every
  mode; forbidden fields absent;
- derived fields with `persisted: false` do not appear on pages;
- `coverage_disposition` projections reconcile against the Coverage Ledger
  when a runtime ledger exists;
- value shapes: date, url, path, list-of-strings, list-of-paths; path-shaped
  values resolve inside the vault (with or without the .md suffix);
  relationship targets resolve to pages of the declared target type;
- unknown fields: neither the compiled contract nor the composed vocabulary
  registers them (the legacy `status` alias is reported for migration);
- a `delegated`-shaped field (the K08/09 `boundary` block): presence, mode,
  and the unknown-field closure stay here; its internal structure is owned
  by the gate its `delegate` key names (`boundary-contract`,
  Tools/check_boundary_contract.py) and is never re-checked here.

Controlled-value legality stays with the `frontmatter-vocabulary` gate;
whether a source supports a claim stays with K07/K12 substantive review.

Enablement (K08/06): advisory by default — violations are candidates, exit 2.
--strict turns violations into failures (exit 1) and is the mode a later
governance decision promotes to a gate; it adds no legacy branch.

Exit codes: 0 = all pass, 1 = hard failure (or violations under --strict),
2 = advisory candidates.

Usage: python3 check_page_contract.py <vault_root> [--profile PROFILE_DIR]
       [--contract Tools/page_contract.yaml] [--scope SUBPATH]
       [--exclude SUBPATH] [--strict] [--receipts PATH]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_page_contract"
TOOL_VERSION = "1.2.0"
GATE_ID = "page-contract"
# The `Check` cell K00/12 registers for this Gate.
GATE_CHECK = "page-contract-summary"

ACTIVE_STATE_PATH = "kernel/K00 Standards Control/03 Standards Governance.md"
SCOPE_SLOT = "Profile Scope"
COVERAGE_LEDGER_PATH = ".cambium/state/coverage_ledger.yaml"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LEGACY_STATUS_FIELD = "status"


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


def resolve_profile_dir(root, override, findings):
    if override:
        profile_dir = override if os.path.isabs(override) \
            else os.path.join(root, override)
        if not os.path.isdir(profile_dir):
            findings.add("page-contract-profile", override, "fail",
                         "--profile does not name an existing directory")
            return None
        return profile_dir
    state_path = os.path.join(root, ACTIVE_STATE_PATH)
    try:
        state_text = read_text(state_path)
    except OSError as exc:
        findings.add("page-contract-profile", ACTIVE_STATE_PATH, "fail",
                     "cannot read the active Standards state: %s" % exc)
        return None
    state, errors = kblib.active_standards_state(state_text)
    for error in errors:
        findings.add("page-contract-profile", ACTIVE_STATE_PATH, "fail",
                     error)
    manifest = state.get("selected_profile_manifest") or ""
    if "{{" in manifest or not manifest.strip():
        findings.add("page-contract-profile", ACTIVE_STATE_PATH, "fail",
                     "no instantiated selected_profile_manifest; pass "
                     "--profile and --scope for a validation run")
        return None
    manifest_path = os.path.join(root, manifest)
    if not os.path.isfile(manifest_path):
        findings.add("page-contract-profile", manifest, "fail",
                     "selected profile manifest does not exist")
        return None
    return os.path.dirname(manifest_path)


def scope_directories(root, profile_dir, findings):
    """Union of the Profile Scope's registered layer directories."""
    manifest_path = os.path.join(profile_dir, "profile.md")
    try:
        manifest_text = read_text(manifest_path)
    except OSError as exc:
        findings.add("page-contract-profile", manifest_path, "fail",
                     "cannot read the profile manifest: %s" % exc)
        return []
    bindings = kblib.profile_slot_bindings(manifest_text)
    binding = bindings.get(SCOPE_SLOT)
    if binding is None:
        findings.add("page-contract-profile", SCOPE_SLOT, "fail",
                     "the manifest does not bind the `Profile Scope` slot")
        return []
    kind, detail = kblib.resolve_profile_binding(binding, root, profile_dir)
    if kind != "path":
        findings.add("page-contract-profile", SCOPE_SLOT, "fail",
                     "Profile Scope binding %r does not resolve" % binding)
        return []
    layers = kblib.profile_scope_layers(read_text(detail))
    directories = sorted({d for dirs in layers.values() for d in dirs})
    if not directories:
        findings.add("page-contract-profile", SCOPE_SLOT, "fail",
                     "no Logical Architecture layer table found; the "
                     "default scan scope cannot be resolved")
    return directories


def load_contract(path, findings):
    try:
        data = kblib.parse_yaml_subset(read_text(path))
    except (OSError, kblib.YamlSubsetError) as exc:
        findings.add("page-contract-input", path, "fail",
                     "cannot parse the compiled contract: %s — compose it "
                     "with Tools/compose_page_contract.py" % exc)
        return None, None
    fields = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, dict) or not fields:
        findings.add("page-contract-input", path, "fail",
                     "the compiled contract carries no fields mapping; an "
                     "empty contract would turn this gate into an "
                     "unconditional pass")
        return None, None
    roles = data.get("section_roles") \
        if isinstance(data.get("section_roles"), dict) else {}
    return fields, roles


def condition_holds(condition, fields):
    def clause_holds(clause):
        name = clause.get("field")
        if clause.get("absent") is True:
            return name not in fields or fields.get(name) in (None, "", [])
        value = fields.get(name)
        return value is not None and str(value) in \
            [str(v) for v in clause.get("in") or []]

    if not isinstance(condition, dict):
        return False
    ok = True
    if "all" in condition:
        ok = all(clause_holds(c) for c in condition["all"])
    if ok and "any" in condition:
        ok = any(clause_holds(c) for c in condition["any"])
    return ok


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


def page_type_of(path):
    raw = kblib.extract_frontmatter(read_text(path))
    if raw is None:
        return None
    try:
        fields = kblib.parse_yaml_subset(raw)
    except kblib.YamlSubsetError:
        return None
    value = fields.get("type") if isinstance(fields, dict) else None
    return str(value) if value is not None else None


def check_shape(root, rel, name, spec, value, report):
    shape = spec.get("shape")
    if shape == "date":
        if not isinstance(value, str) or not DATE_RE.match(value):
            report("page-contract-shape", "%s:%s" % (rel, name),
                   "must be a YYYY-MM-DD date; found %r" % (value,))
    elif shape == "url":
        if not isinstance(value, str) or \
                not value.lower().startswith(("http://", "https://")):
            report("page-contract-shape", "%s:%s" % (rel, name),
                   "must be an external http(s) URL; found %r" % (value,))
    elif shape == "list-of-strings":
        if not isinstance(value, list) or \
                not all(isinstance(v, str) and v.strip() for v in value):
            report("page-contract-shape", "%s:%s" % (rel, name),
                   "must be a list of nonempty strings")
    elif shape in ("path", "list-of-paths"):
        values = value if isinstance(value, list) else [value]
        if shape == "list-of-paths" and not isinstance(value, list):
            report("page-contract-shape", "%s:%s" % (rel, name),
                   "must be list-shaped")
            return
        targets = spec.get("target")
        target_types = None
        if isinstance(targets, list):
            target_types = [str(t) for t in targets]
        elif isinstance(targets, str) and targets not in (
                "page", "none", "external-original"):
            target_types = [targets]
        for item in values:
            resolved = resolve_page(root, item)
            if resolved is None:
                report("page-contract-target", "%s:%s" % (rel, name),
                       "target %r does not resolve inside the vault"
                       % (item,))
            elif target_types is not None:
                actual = page_type_of(resolved)
                if actual not in target_types:
                    report("page-contract-target", "%s:%s" % (rel, name),
                           "target %r has type %r, expected one of %s"
                           % (item, actual, ", ".join(target_types)))
    elif shape == "delegated":
        # Internal structure is owned by the gate the field's `delegate`
        # key names (K08/09); only presence and mode are checked here.
        pass
    # nonempty-string and unknown shapes: presence checks already cover them.


def check_sources_role(root, rel, text, fields, contract, roles, report):
    """Deterministic sources-role check (K07/02 Source Placement)."""
    sources = roles.get("sources") if isinstance(roles, dict) else None
    if not isinstance(sources, dict):
        return
    titles = {str(v).strip() for v in sources.get("titles") or []}
    if not titles:
        return
    body = kblib.strip_code(text)
    headings = [h.strip() for _l, _lv, h in kblib.headings_of(body)]
    matches = [h for h in headings if h in titles]
    if len(matches) > 1:
        report("page-contract-sources-role", rel,
               "more than one sources-role heading (%s); one page carries "
               "at most one" % ", ".join(sorted(set(matches))))
        return
    condition = (sources.get("applicability") or {}).get("condition")
    if condition is not None and not condition_holds(condition, fields):
        return
    if matches:
        return
    binding = sources.get("binding_satisfies") or {}
    for name in binding.get("fields") or []:
        if fields.get(name) not in (None, "", []):
            return
    directions = set(binding.get("directions") or [])
    if directions:
        for name, spec in contract.items():
            if spec.get("direction") in directions and \
                    fields.get(name) not in (None, "", []):
                return
    report("page-contract-sources-role", rel,
           "page owes the sources role (K07/02) but carries no registered "
           "sources-role heading and no satisfying evidence binding")


def run(root, profile_override, contract_path, scope, excludes, strict,
        receipts_path):
    findings = Findings()
    violation = "fail" if strict else "candidate"

    contract_abs = contract_path if os.path.isabs(contract_path) \
        else os.path.join(root, contract_path)
    contract, section_roles = load_contract(contract_abs, findings)

    scan_roots = []
    ledger_dispositions = {}
    if contract is not None:
        if scope:
            scan_roots = [scope]
        else:
            profile_dir = resolve_profile_dir(root, profile_override,
                                              findings)
            if profile_dir is not None:
                scan_roots = scope_directories(root, profile_dir, findings)
        ledger_path = os.path.join(root, COVERAGE_LEDGER_PATH)
        if os.path.isfile(ledger_path):
            try:
                ledger = kblib.parse_yaml_subset(read_text(ledger_path))
            except kblib.YamlSubsetError:
                ledger = None
            for page in (ledger or {}).get("pages") or []:
                if isinstance(page, dict) and page.get("path"):
                    ledger_dispositions[str(page["path"])] = \
                        page.get("coverage_disposition")

    pages = []
    for scan_root in scan_roots:
        base = os.path.normpath(os.path.join(root, scan_root))
        if not os.path.isdir(base) and not (
                os.path.isfile(base) and base.lower().endswith(".md")):
            findings.add("page-contract-scope", scan_root, "fail",
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

    if contract is not None and not pages:
        findings.add("page-contract-scope", ",".join(scan_roots) or "<none>",
                     "fail",
                     "the effective scan set is empty; a zero-page scan is "
                     "an invocation error, never a pass")

    checked = 0
    for path in pages:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        raw = kblib.extract_frontmatter(read_text(path))
        if raw is None:
            findings.add("page-contract-frontmatter", rel, violation,
                         "no fenced frontmatter; every applicable field "
                         "contract is unverifiable")
            continue
        try:
            fields = kblib.parse_yaml_subset(raw)
        except kblib.YamlSubsetError as exc:
            findings.add("page-contract-frontmatter", rel, violation,
                         "frontmatter is outside the restricted YAML "
                         "subset: %s" % exc)
            continue
        if not isinstance(fields, dict):
            findings.add("page-contract-frontmatter", rel, violation,
                         "frontmatter is not a mapping")
            continue
        checked += 1

        def report(check, target, details):
            findings.add(check, target, violation, details)

        for name, spec in contract.items():
            mode = spec.get("mode")
            present = name in fields
            value = fields.get(name)
            empty = value in (None, "", [])
            if mode == "required":
                if not present or empty:
                    report("page-contract-required", "%s:%s" % (rel, name),
                           "required field is missing or empty")
                    continue
            elif mode == "conditional":
                if condition_holds(spec.get("condition"), fields) and \
                        (not present or empty):
                    report("page-contract-required", "%s:%s" % (rel, name),
                           "condition holds but the field is missing or "
                           "empty")
                    continue
            elif mode == "forbidden":
                if present:
                    report("page-contract-forbidden", "%s:%s" % (rel, name),
                           "forbidden field is present in this context")
                continue
            elif mode == "derived":
                if present and spec.get("persisted") is False:
                    report("page-contract-derived", "%s:%s" % (rel, name),
                           "derived value is not persisted on pages "
                           "(K08/07); it belongs in tool output and "
                           "receipts")
                continue
            elif mode == "projection":
                if name == "coverage_disposition" and present and \
                        not empty and rel in ledger_dispositions:
                    owner_value = ledger_dispositions[rel]
                    if owner_value is not None and \
                            str(owner_value) != str(value):
                        report("page-contract-projection",
                               "%s:%s" % (rel, name),
                               "page projection %r disagrees with the "
                               "Coverage Ledger owner value %r"
                               % (value, owner_value))
            if present and empty:
                report("page-contract-empty", "%s:%s" % (rel, name),
                       "present but empty; empty placeholders are noise "
                       "(K08/06)")
                continue
            if present and not empty:
                check_shape(root, rel, name, spec, value, report)

        check_sources_role(root, rel, read_text(path), fields, contract,
                           section_roles, report)

        for name in sorted(fields):
            if name in contract:
                continue
            if name == LEGACY_STATUS_FIELD:
                report("page-contract-unknown", "%s:%s" % (rel, name),
                       "legacy `status` alias; migrate to "
                       "authoring_status (K08/04 migration rule)")
            else:
                report("page-contract-unknown", "%s:%s" % (rel, name),
                       "field is neither in the compiled contract nor a "
                       "registered extension; unknown fields are not open "
                       "metadata (K08/06)")

    fails = findings.count("fail")
    candidates = findings.count("candidate")
    print("check_page_contract: scanned %d page(s), %d checked, "
          "contract_fields=%d mode=%s"
          % (len(pages), checked, len(contract or {}),
             "strict" if strict else "advisory"))
    for row in findings.rows:
        print("  [%s] %s (%s): %s" % (row["result"].upper(), row["check"],
                                      row["target"], row["details"]))
    print("  fail=%d candidate=%d" % (fails, candidates))
    if fails:
        print("  Conclusion: page-contract check failed (K08/06-08).")
    elif candidates:
        print("  Conclusion: advisory candidates found; they support "
              "migration planning and no existing gate consumes them "
              "(K08/06 Enablement).")
    else:
        print("  Conclusion: every scanned page satisfies the compiled "
              "page contract. Controlled-value legality and claim support "
              "remain owned by their own gates.")

    if receipts_path:
        receipts = []
        seq = 1
        for row in findings.rows:
            # Each finding receipt carries its own finding type as ``check``
            # (e.g. ``page-contract-sources-role``), so a consumer that
            # dispositions candidates can select the exact obligation rather
            # than the whole gate.  The gate summary below keeps GATE_CHECK.
            receipt = kblib.make_receipt(
                TOOL, TOOL_VERSION, row["check"], row["target"],
                row["result"], row["details"], seq, root=root)
            receipt["gate_id"] = GATE_ID
            receipts.append(receipt)
            seq += 1
        summary = kblib.make_receipt(
            TOOL, TOOL_VERSION, GATE_CHECK, "page-contract",
            "fail" if fails else ("candidate" if candidates else "pass"),
            "pages=%d checked=%d fail=%d candidate=%d mode=%s"
            % (len(pages), checked, fails, candidates,
               "strict" if strict else "advisory"),
            seq, root=root)
        summary["gate_id"] = GATE_ID
        receipts.append(summary)
        kblib.write_receipts(receipts_path, receipts)

    if fails:
        return 1
    return 2 if candidates else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate pages against the compiled frontmatter page "
                    "contract (gate: page-contract; advisory by default).")
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
                        help="treat violations as failures; the mode a "
                             "governance decision promotes to a gate")
    parser.add_argument("--receipts",
                        help="JSONL path to append machine-readable "
                             "receipts to")
    args = parser.parse_args(argv)
    return run(args.vault_root, args.profile, args.contract, args.scope,
               args.exclude, args.strict, args.receipts)


if __name__ == "__main__":
    sys.exit(main())
