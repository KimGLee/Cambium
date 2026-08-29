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
(.cambium/derived/page_contract.yaml by default) — like the effective
vocabulary it exists only
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
       [--contract .cambium/derived/page_contract.yaml] [--scope SUBPATH]
       [--exclude SUBPATH] [--strict] [--receipts PATH]
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import compose_page_contract
import coverage_contract
import profile_admission
import metadata_execution_contract
import metadata_property_state
import project_page_state
import runtime_paths

TOOL = "check_page_contract"
TOOL_VERSION = "1.5.0"
GATE_ID = "page-contract"
# The `Check` cell K00/12 registers for this Gate.
GATE_CHECK = "page-contract-summary"

# ---------------------------------------------------------------------------
# `--json` projection
#
# A check's structured result already exists: it is the set of receipts the
# run produced.  `--json` adds one projection of those same objects -- the
# exact receipt dicts, serialized through `kblib.canonical_json_bytes`, with
# no field whitelist -- onto stdout, and moves every human-readable line to
# stderr for that run.  Serializing the receipt itself is what keeps the
# projection honest: `Tools/schemas/receipt.template.jsonl` guarantees only
# the base fields, and each producer's extension fields are discoverable from
# the receipt, so a whitelist here could only lose evidence.
#
# Without the flag nothing below runs and every byte this tool writes is
# unchanged.  The flag never changes the exit code and never changes what is
# appended to the receipts file.  A run rejected before it produced any
# receipt leaves stdout empty and states the reason on stderr, which is the
# settled shape for a refused invocation.
# ---------------------------------------------------------------------------

_JSON_STDOUT = None
_JSON_RECEIPTS = None


def _json_begin(enabled):
    """Reserve stdout for the projection and send human output to stderr."""
    global _JSON_STDOUT, _JSON_RECEIPTS
    _JSON_STDOUT = None
    _JSON_RECEIPTS = None
    if enabled:
        _JSON_STDOUT = sys.stdout
        sys.stdout = sys.stderr


def _json_enabled():
    """True while `--json` owns stdout for this run."""
    return _JSON_STDOUT is not None


def _json_record(receipts):
    """Hold the exact receipt objects this run produced."""
    global _JSON_RECEIPTS
    if _JSON_STDOUT is not None:
        _JSON_RECEIPTS = list(receipts)


def _json_finish(answered):
    """Restore stdout, emitting the recorded receipts when the run answered."""
    global _JSON_STDOUT, _JSON_RECEIPTS
    stream = _JSON_STDOUT
    receipts = _JSON_RECEIPTS
    _JSON_STDOUT = None
    _JSON_RECEIPTS = None
    if stream is None:
        return
    sys.stdout = stream
    if answered and receipts is not None:
        stream.write(
            kblib.canonical_json_bytes(receipts).decode("utf-8") + "\n")
        stream.flush()


JSON_FLAG_HELP = ("write the receipts this run produced to stdout as one "
                  "canonical JSON array and move the human-readable summary "
                  "to stderr; receipts written and the exit code are "
                  "unchanged")


ACTIVE_STATE_PATH = runtime_paths.ACTIVE_STANDARDS_PATH
SCOPE_SLOT = "Profile Scope"
COVERAGE_LEDGER_PATH = runtime_paths.COVERAGE_PATH
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LEGACY_STATUS_FIELD = "status"


def read_text(path):
    return kblib.read_text(path, errors="replace")


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
        findings.add("page-contract-profile", SCOPE_SLOT, "fail",
                     error)
        return []
    try:
        layers = kblib.profile_scope_layers(
            admission.slot_text(SCOPE_SLOT))
    except (OSError, UnicodeError) as exc:
        findings.add("page-contract-profile", SCOPE_SLOT, "fail",
                     "cannot read admitted Profile Scope: %s" % exc)
        return []
    directories = sorted({d for dirs in layers.values() for d in dirs})
    if not directories:
        findings.add("page-contract-profile", SCOPE_SLOT, "fail",
                     "no Logical Architecture layer table found; the "
                     "default scan scope cannot be resolved")
    return directories


def load_contract(path, findings, text=None):
    try:
        data = kblib.parse_yaml_subset(
            read_text(path) if text is None else text)
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
        receipts_path, *, authorized_admission=None):
    root = os.path.abspath(root)
    findings = Findings()
    violation = "fail" if strict else "candidate"

    if authorized_admission is None:
        admission, admission_errors = profile_admission.admit_profile(
            root, profile_override, active_state_path=ACTIVE_STATE_PATH)
    else:
        admission = authorized_admission
        admission_errors = []
        if os.path.realpath(admission.root) != os.path.realpath(root):
            admission_errors.append(
                "authorized admission belongs to another repository root")
        if (profile_override is not None and
                os.path.realpath(os.path.join(root, profile_override)) !=
                os.path.realpath(os.path.join(
                    root, admission.contract.profile_repo_dir))):
            admission_errors.append(
                "authorized admission does not match --profile override")
    for error in admission_errors:
        findings.add("page-contract-profile-load", ACTIVE_STATE_PATH,
                     "fail", error)

    contract_abs = contract_path if os.path.isabs(contract_path) \
        else os.path.join(root, contract_path)
    artifact_snapshot = None
    if admission is not None:
        artifact_snapshot, artifact_errors = \
            compose_page_contract.admitted_artifact(
                root, contract_abs, admission)
        for error in artifact_errors:
            findings.add("page-contract-artifact-current", contract_abs,
                         "fail", error)
    contract, section_roles = load_contract(
        contract_abs, findings,
        artifact_snapshot.read_text()
        if artifact_snapshot is not None else None)

    scan_roots = []
    ledger_dispositions = {}
    projection_rules = ()
    projection_rule_by_field = {}
    if contract is not None and admission is not None:
        try:
            metadata_contract = \
                metadata_execution_contract.load_metadata_execution_contract(
                    root)
            projection_rules = \
                metadata_property_state.profile_gate_projection_rules(
                    root, admission.contract.extension_gates,
                    metadata_contract=metadata_contract,
                    authorized_profile_contract=admission.contract)
            projection_rule_by_field = {
                rule["field"]: rule for rule in projection_rules
            }
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            findings.add(
                "page-contract-metadata-authority",
                "Tools/compiled/metadata-execution-contract.json", "fail",
                "cannot compose current field authority: %s" % exc)
        if scope:
            scan_roots = [scope]
        else:
            scan_roots = scope_directories(admission, findings)
        ledger_path = os.path.join(root, COVERAGE_LEDGER_PATH)
        if os.path.isfile(ledger_path):
            try:
                ledger = kblib.parse_yaml_subset(read_text(ledger_path))
            except kblib.YamlSubsetError:
                ledger = None
            for page in (ledger or {}).get("pages") or []:
                if isinstance(page, dict) and page.get("path"):
                    ledger_dispositions[str(page["path"])] = page

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
        page_text = read_text(path)
        raw = kblib.extract_frontmatter(page_text)
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
                # Applicability and write authority are orthogonal.  The
                # metadata execution contract below reconciles the copy; this
                # branch only keeps projection-mode presence optional here.
                pass
            if present and empty:
                report("page-contract-empty", "%s:%s" % (rel, name),
                       "present but empty; empty placeholders are noise "
                       "(K08/06)")
                continue
            if present and not empty:
                check_shape(root, rel, name, spec, value, report)

        owner_row = ledger_dispositions.get(rel)
        owner_is_planning = coverage_contract.is_complete_planning_page(
            owner_row)
        for name, rule in sorted(projection_rule_by_field.items()):
            if owner_is_planning:
                # A queued planning row deliberately owns no current page
                # projection.  Reconciliation starts only when its batch is
                # opened and the row is materialized as runtime Coverage.
                continue
            present = name in fields
            page_value = fields.get(name)
            adapter = rule.get("source_adapter")
            policy = rule.get("reconcile_policy")
            owner_value = None
            owner_bound = False
            if isinstance(owner_row, dict):
                if adapter == "coverage-row-value-v1":
                    owner_bound = name in owner_row
                    owner_value = owner_row.get(name)
                elif adapter == "coverage-property-state-v1":
                    states = owner_row.get("property_state")
                    record = states.get(name) if isinstance(states, dict) \
                        else None
                    if record is not None:
                        owner_bound = True
                        if (not isinstance(record, dict) or
                                set(record) !=
                                metadata_property_state.PROPERTY_RECORD_KEYS):
                            report(
                                "page-contract-property-evidence",
                                "%s:%s" % (rel, name),
                                "Coverage owner record is not the closed "
                                "value/evidence/content binding")
                            continue
                        owner_value = record.get("value")
                        if not isinstance(
                                record.get("evidence_receipt"), str) or not \
                                record["evidence_receipt"].strip():
                            report(
                                "page-contract-property-evidence",
                                "%s:%s" % (rel, name),
                                "Coverage owner record has no evidence "
                                "receipt")
                        try:
                            current_semantic = \
                                project_page_state.semantic_content_fingerprint(
                                    rel, page_text, projection_rules)
                        except (TypeError, ValueError) as exc:
                            report(
                                "page-contract-property-evidence",
                                "%s:%s" % (rel, name),
                                "cannot bind current semantic content: %s" %
                                exc)
                        else:
                            if record.get("content_fingerprint") != \
                                    current_semantic:
                                report(
                                    "page-contract-property-evidence",
                                    "%s:%s" % (rel, name),
                                    "Coverage owner evidence binds stale "
                                    "semantic content")
                else:
                    report(
                        "page-contract-metadata-authority",
                        "%s:%s" % (rel, name),
                        "unsupported metadata source adapter %r" % adapter)
                    continue
            if policy == "upsert-exact-or-remove-v1":
                if owner_bound and owner_value is not None and (
                        not present or str(page_value) != str(owner_value)):
                    report(
                        "page-contract-projection", "%s:%s" % (rel, name),
                        "machine projection must equal current owner value "
                        "%r" % owner_value)
                elif owner_bound and owner_value is None and present:
                    report(
                        "page-contract-projection", "%s:%s" % (rel, name),
                        "machine projection is stale because current owner "
                        "state is an evidence-backed removal")
                elif not owner_bound and present:
                    report(
                        "page-contract-projection", "%s:%s" % (rel, name),
                        "machine projection has no current Coverage owner "
                        "record")
            elif (policy == "existing-copy-exact-or-remove-v1" and present
                  and owner_bound and
                  ((owner_value is None) or
                   str(page_value) != str(owner_value))):
                if owner_value is None:
                    details = (
                        "page projection %r is stale because the Coverage "
                        "Ledger owner is empty" % page_value)
                else:
                    details = (
                        "page projection %r disagrees with the Coverage "
                        "Ledger owner %r" % (page_value, owner_value))
                report("page-contract-projection",
                       "%s:%s" % (rel, name), details)

        check_sources_role(root, rel, page_text, fields, contract,
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

    if admission is not None:
        for error in profile_admission.currency_errors(admission):
            findings.add("page-contract-profile-currency",
                         admission.manifest_repo_path, "fail", error)
        for error in compose_page_contract.artifact_currency_errors(
                root, contract_abs, admission):
            findings.add("page-contract-artifact-currency", contract_abs,
                         "fail", error)
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

    if receipts_path or _json_enabled():
        # The receipt set is this run's structured result, so `--json` builds
        # it even with no receipts file to append to.  Neither destination
        # changes what the receipts say.
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
        _json_record(receipts)

    if fails:
        return 1
    return 2 if candidates else 0


def main(argv=None):
    """CLI entry point; `--json` projects the produced receipts onto stdout."""
    try:
        code = _main(argv)
    except BaseException:
        _json_finish(False)
        raise
    _json_finish(True)
    return code


def _main(argv=None):
    parser = kblib.ArgumentParser(
        description="Validate pages against the compiled frontmatter page "
                    "contract (gate: page-contract; advisory by default).")
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
                        help="treat violations as failures; the mode a "
                             "governance decision promotes to a gate")
    parser.add_argument("--receipts",
                        help="JSONL path to append machine-readable "
                             "receipts to")
    parser.add_argument("--json", action="store_true", help=JSON_FLAG_HELP)
    args = parser.parse_args(argv)
    _json_begin(args.json)
    return run(args.vault_root, args.profile, args.contract, args.scope,
               args.exclude, args.strict, args.receipts)


if __name__ == "__main__":
    sys.exit(main())
