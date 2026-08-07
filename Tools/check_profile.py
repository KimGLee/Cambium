#!/usr/bin/env python3
"""Profile manifest completeness check script.

Rule owners:
- "profiles/README.md" (the normative profile interface: which slots exist and
  what constrains each; the Execution Default Overrides Contract);
- "kernel/K00 Standards Control/execution-defaults-base.yaml" (the canonical
  membership registry for the overridable / constitutional split, and the
  admissible value form of an item whose owner module fixes one);
- "Tools/schemas/execution_defaults.template.yaml" (executor-side placeholder
  configuration only: reserved profile_id values and the unfilled sentinel).

What this script is for: a profile copied from `profiles/_template/` is a
skeleton of constraints and TODOs, not a runnable profile. Nothing in prose can
stop an agent from loading a half-filled skeleton and reporting success. This
script is the mechanical stop: it fails while the skeleton is still visible, so
an unfilled profile cannot pass a gate that runs it.

Method:
- Slot list: the H2 headings of the interface file ending in " Slot", with the
  suffix stripped. The Execution Default Overrides Contract is not a file-bound
  slot -- it is a declaration table, checked separately below.
- Manifest: `<profile_dir>/profile.md`. Its `## Implemented Slots` section must
  bind every interface slot, as `- `Slot Name`: <binding>`.
- A binding is resolved in this order: `[[vault/relative/path|alias]]` wiki
  link -> markdown link `[text](path)` -> a binding whose text says the slot is
  declared `inline` (then profile.md must carry an H2 section whose heading
  starts with the slot name) -> a single inline-code span that looks like a
  path. Anything else is unrecognized.
- Execution Default Overrides: the table contains only explicit overrides;
  sparse-default semantics are owned by the profile interface. Duplicate,
  unknown, default-restating, and constitutional rows fail, and so does a row
  whose value leaves the `value_domain` the kernel registry records for that
  item. A registered form may carry the bound its owner module writes into
  it. An item the registry gives no `value_domain` is left to its owner
  module; this script invents no bound of its own.
- Corpus Planning: the bound slot is a closed restricted-YAML document whose
  applicability, three artifact bindings, ordered capability scale, and pass
  authority are validated directly; Markdown declaration heuristics do not
  define this slot.
- Optional/conditional declarations: `Configured` must be backed by complete
  table rows; `None` and `Not applicable — <reason>` must not retain active
  rows. This makes one declaration control one block instead of relying on
  repeated prose fallbacks.

Two independent incompleteness blocks, either of which fails the profile:
1. the unfilled sentinel (default `TODO(profile)`) appearing anywhere under the
   profile directory;
2. a `profile_id` that is missing or still one of the reserved placeholder
   values.
Each block is cleared only by editing the file, so clearing both is the
mechanical definition of "this profile has been filled in". None of them is
evidence that the answers are *good*; content quality stays a human call.

Result semantics: unbound slots, unresolved bindings, invalid override rows,
and both incompleteness blocks are result=fail. A manifest binding
for a slot the interface does not define is result=candidate (an extension
binding may be legitimate; whether it is, is a human call).

Scope semantics: a profile directory that does not exist, or that has no
profile.md, is result=fail -- a scan with nothing to check is an invocation
error, never a pass.

Exit codes: 0 = all pass, 1 = at least one fail, 2 = no fail but candidates.

Usage: python3 check_profile.py <profile_dir> [--root VAULT_ROOT]
       [--interface profiles/README.md]
       [--defaults Tools/schemas/execution_defaults.template.yaml]
       [--execution-defaults "kernel/K00 Standards Control/execution-defaults-base.yaml"]
       [--receipts PATH]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib

TOOL = "check_profile"
TOOL_VERSION = "1.7.0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_INTERFACE = "profiles/README.md"
DEFAULT_DEFAULTS = "Tools/schemas/execution_defaults.template.yaml"
DEFAULT_EXECUTION_DEFAULTS = (
    "kernel/K00 Standards Control/execution-defaults-base.yaml"
)

MANIFEST_NAME = "profile.md"
SLOT_SUFFIX = " Slot"
SLOTS_SECTION = "Implemented Slots"
OVERRIDES_SECTION = "Execution Default Overrides"

# Extensions read as text during the sentinel scan; anything else (images,
# archives) is skipped and reported in the summary counts.
TEXT_SUFFIXES = (".md", ".yaml", ".yml", ".txt", ".json", ".jsonl", ".py", ".csv")

DECLARATION_RE = re.compile(
    r"^\s*-\s+(Registration|Applicability):\s*(.*?)\s*$"
)

CORPUS_PLANNING_SLOT = "Corpus Planning"
CORPUS_PLANNING_FIELDS = {
    "schema_version", "applicability", "artifact_bindings",
    "capability_scale", "pass_authority",
}
CORPUS_APPLICABILITY_FIELDS = {"state", "reason"}
CORPUS_ARTIFACT_FIELDS = {
    "global_map", "capability_matrix", "gap_register",
}
CORPUS_SCALE_FIELDS = {"rank", "value", "predicate", "target_eligible"}
CORPUS_AUTHORITY_FIELDS = {"role_id", "decision_scope_id"}
CORPUS_DECISION_SCOPE = "corpus-plan-semantic-acceptance"

AUDIT_DIMENSION_SLOT = "Audit Dimension Registry"
AUDIT_DIMENSION_SECTION = "Extension Dimensions"
AUDIT_DIMENSION_TABLE_HEADER = (
    "Dimension ID",
    "Target list(s): `review`, `receipt`, or `review + receipt`",
    "Meaning",
)
AUDIT_DIMENSION_REGISTRATIONS = frozenset(("None", "Configured"))
AUDIT_DIMENSION_TARGETS = {
    "review": frozenset(("review",)),
    "receipt": frozenset(("receipt",)),
    "review + receipt": frozenset(("review", "receipt")),
}
AUDIT_DIMENSION_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
BASE_RECEIPT_DIMENSIONS = (
    "structure_and_links",
    "content_and_depth",
    "formula_and_numeric",
    "source_and_currentness",
    "coverage_and_integration",
    "rendering",
    "guidance_and_contract",
)


def _positive_integer_domain(value):
    """A whole count of one or more, written without sign, unit, or decimals."""
    if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
        return "expected a positive integer"
    return None


def _percent_share_under_100_domain(value):
    """A share of a corpus its owner also partitions, so under the whole.

    The upper end is open because the owner module that fixes this form keeps
    a remainder class outside the quota: a share of 100% leaves that class
    empty and leaves nothing able to exceed the quota it registers. The bound
    belongs to that owner; this function only implements the form it names.
    """
    number = value[:-1].strip() if value.endswith("%") else value
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", number):
        return "expected a number, optionally followed by `%`"
    if not 0 <= float(number) < 100:
        return "expected a percentage share that is at least 0 and under 100"
    return None


# Admissible value forms a `value_domain` in the kernel execution-default
# registry may name.  The registry decides which item carries which form; this
# table only implements the form, and an unknown name is reported rather than
# silently treated as "anything goes".
VALUE_DOMAINS = {
    "positive-integer": _positive_integer_domain,
    "percent-share-under-100": _percent_share_under_100_domain,
}


def blank_fenced(text):
    """Blank out fenced code blocks, keeping inline code and the line count.

    kblib.strip_code also removes inline code, which this script must keep:
    slot names and bindings live inside backticks.
    """
    out = []
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        m = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and m:
            fence = m.group(1)[0] * 3
            out.append("")
            continue
        if fence is not None:
            if m and stripped.startswith(fence):
                fence = None
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def h2_headings(text):
    """Return the H2 heading texts of a fence-blanked document, in order."""
    return [h for _, level, h in kblib.headings_of(blank_fenced(text)) if level == 2]


def section_lines(text, heading):
    """Return the lines of the H2 section with this exact heading (or [])."""
    lines = blank_fenced(text).splitlines()
    out = []
    inside = False
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            if inside and len(m.group(1)) <= 2:
                break
            inside = (len(m.group(1)) == 2 and m.group(2).strip() == heading)
            continue
        if inside:
            out.append(line)
    return out


def h2_sections(text):
    """Return [(H2 heading, section lines)] including nested H3+ content."""
    sections = []
    current = None
    body = []
    for line in blank_fenced(text).splitlines():
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m and len(m.group(1)) <= 2:
            if current is not None:
                sections.append((current, body))
            current = m.group(2).strip() if len(m.group(1)) == 2 else None
            body = []
            continue
        if current is not None:
            body.append(line)
    if current is not None:
        sections.append((current, body))
    return sections


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def interface_slots(text):
    """Slot names = H2 headings ending in ' Slot', suffix stripped."""
    return [h[: -len(SLOT_SUFFIX)].strip()
            for h in h2_headings(text) if h.endswith(SLOT_SUFFIX)]


def parse_bindings(manifest_text):
    """Return the slot mapping and repeated names from Implemented Slots."""
    return kblib.profile_slot_bindings(
        manifest_text, include_duplicates=True
    )


def resolve_binding(binding, root, profile_dir):
    """Resolve one binding through the shared manifest-binding contract."""
    return kblib.resolve_profile_binding(binding, root, profile_dir)


def table_rows(lines):
    """Yield the cell lists of Markdown table rows, skipping separator rows."""
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        yield cells


def markdown_table_data(lines):
    """Return (header, data rows) for each Markdown table in a section."""
    tables = []
    group = []

    def finish():
        if not group:
            return
        rows = list(table_rows(group))
        if rows:
            tables.append((rows[0], rows[1:]))

    for line in lines:
        if line.strip().startswith("|"):
            group.append(line)
        else:
            finish()
            group = []
    finish()
    return tables


def profile_declarations(profile_dir):
    """Yield explicit Registration/Applicability declarations in Markdown."""
    for dirpath, dirnames, filenames in os.walk(profile_dir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith(".") or not name.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, profile_dir).replace(os.sep, "/")
            sections = h2_sections(read_text(full))
            for heading, lines in sections:
                for line in lines:
                    match = DECLARATION_RE.match(line)
                    if match:
                        tables = markdown_table_data(lines)
                        yield (
                            rel,
                            heading,
                            match.group(1),
                            match.group(2).strip(),
                            tables,
                        )


def unbacktick(value):
    value = value.strip()
    m = re.fullmatch(r"`([^`]*)`", value)
    return m.group(1).strip() if m else value


def parse_audit_dimension_registry(text):
    """Parse the closed ``Extension Dimensions`` profile registration.

    Returns ``(registration, rows, errors)``. ``rows`` contains dictionaries
    with ``id``, normalized ``targets``, and ``meaning``. ``errors`` contains
    ``(check, details)`` pairs. Callers MUST treat any error as making the
    complete registry unreadable; valid-looking rows from a partial parse are
    diagnostic data, not authorization to consume a subset.

    This is the one parser shared by profile admission and Terminal Proof. It
    intentionally decides only the machine-readable envelope. Whether a
    dimension is useful, or whether its meaning is true, remains review work.
    """
    errors = []
    matching = [lines for heading, lines in h2_sections(text)
                if heading == AUDIT_DIMENSION_SECTION]
    if len(matching) != 1:
        errors.append((
            "audit-dimension-section-count",
            "expected exactly one `## %s` section; found %d" %
            (AUDIT_DIMENSION_SECTION, len(matching)),
        ))
        return None, (), tuple(errors)

    lines = matching[0]
    declarations = [match.group(2).strip()
                    for match in (DECLARATION_RE.match(line)
                                  for line in lines)
                    if match and match.group(1) == "Registration"]
    registration = declarations[0] if len(declarations) == 1 else None
    if (len(declarations) != 1 or
            registration not in AUDIT_DIMENSION_REGISTRATIONS):
        errors.append((
            "audit-dimension-registration",
            "expected exactly one `- Registration:` declaration whose value "
            "is `None` or `Configured`; found %r" % declarations,
        ))

    tables = markdown_table_data(lines)
    if len(tables) != 1:
        errors.append((
            "audit-dimension-table-count",
            "expected exactly one Markdown registration table; found %d" %
            len(tables),
        ))
        return registration, (), tuple(errors)

    header, data_rows = tables[0]
    if tuple(header) != AUDIT_DIMENSION_TABLE_HEADER:
        errors.append((
            "audit-dimension-table-shape",
            "registration table header must be exactly `%s`; found `%s`" %
            (" | ".join(AUDIT_DIMENSION_TABLE_HEADER),
             " | ".join(header)),
        ))

    if registration == "Configured" and not data_rows:
        errors.append((
            "audit-dimension-configured-empty",
            "`Registration: Configured` requires at least one extension "
            "dimension row",
        ))
    if registration == "None" and data_rows:
        errors.append((
            "audit-dimension-none-with-rows",
            "`Registration: None` requires an empty registration table; "
            "found %d row(s)" % len(data_rows),
        ))

    parsed = []
    seen = set()
    for row_number, cells in enumerate(data_rows, 1):
        label = "registration row %d" % row_number
        if len(cells) != len(AUDIT_DIMENSION_TABLE_HEADER) or any(
                not cell.strip() for cell in cells):
            errors.append((
                "audit-dimension-row-shape",
                "%s must have exactly three non-empty cells; found %d" %
                (label, len(cells)),
            ))
            continue

        dimension_id = unbacktick(cells[0])
        if not AUDIT_DIMENSION_ID_RE.fullmatch(dimension_id):
            errors.append((
                "audit-dimension-id-invalid",
                "%s has invalid Dimension ID %r; use lower_snake_case "
                "starting with a letter" % (label, dimension_id),
            ))
        if dimension_id in seen:
            errors.append((
                "audit-dimension-id-duplicate",
                "%s repeats Dimension ID %r; each extension dimension has "
                "one registration" % (label, dimension_id),
            ))
        else:
            seen.add(dimension_id)
        if dimension_id in BASE_RECEIPT_DIMENSIONS:
            errors.append((
                "audit-dimension-base-collision",
                "%s registers %r, one of the seven base receipt dimensions; "
                "profile registrations may append dimensions but cannot "
                "redefine a base dimension" % (label, dimension_id),
            ))

        target_literal = unbacktick(cells[1])
        targets = AUDIT_DIMENSION_TARGETS.get(target_literal)
        if targets is None:
            errors.append((
                "audit-dimension-target-invalid",
                "%s has target %r; use exactly `review`, `receipt`, or "
                "`review + receipt`" % (label, target_literal),
            ))
            targets = frozenset()

        parsed.append({
            "id": dimension_id,
            "targets": targets,
            "meaning": cells[2].strip(),
        })

    return registration, tuple(parsed), tuple(errors)


def scan_sentinel(profile_dir, sentinel):
    """Return ([(relpath, lineno)], files_read, files_skipped)."""
    hits, read_n, skipped_n = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(profile_dir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            if not name.lower().endswith(TEXT_SUFFIXES):
                skipped_n += 1
                continue
            read_n += 1
            rel = os.path.relpath(full, profile_dir).replace(os.sep, "/")
            for lineno, line in enumerate(read_text(full).splitlines(), 1):
                if sentinel in line:
                    hits.append((rel, lineno))
    return hits, read_n, skipped_n


def validate_corpus_planning_slot(path, target, add):
    """Validate the Profile slot's closed restricted-YAML envelope."""
    try:
        document = kblib.parse_yaml_subset(read_text(path))
    except (OSError, kblib.YamlSubsetError) as exc:
        add("corpus-planning-yaml", target, "fail",
            "cannot parse restricted YAML: %s" % exc)
        return

    def closed(value, fields, label):
        if not isinstance(value, dict):
            add("corpus-planning-schema", label, "fail", "must be a mapping")
            return {}
        missing = sorted(fields - set(value))
        extra = sorted(set(value) - fields)
        if missing:
            add("corpus-planning-schema", label, "fail",
                "missing field(s): %s" % ", ".join(missing))
        if extra:
            add("corpus-planning-schema", label, "fail",
                "unsupported field(s): %s" % ", ".join(extra))
        return value

    document = closed(document, CORPUS_PLANNING_FIELDS, target)
    if type(document.get("schema_version")) is not int or \
            document.get("schema_version") != 1:
        add("corpus-planning-schema", target, "fail",
            "schema_version must be integer 1")
    applicability = closed(
        document.get("applicability"), CORPUS_APPLICABILITY_FIELDS,
        target + ":applicability")
    artifacts = closed(
        document.get("artifact_bindings"), CORPUS_ARTIFACT_FIELDS,
        target + ":artifact_bindings")
    authority = closed(
        document.get("pass_authority"), CORPUS_AUTHORITY_FIELDS,
        target + ":pass_authority")
    scale = document.get("capability_scale")
    if not isinstance(scale, list):
        add("corpus-planning-schema", target + ":capability_scale", "fail",
            "must be a list")
        scale = []

    state = applicability.get("state")
    reason = applicability.get("reason")
    if state == "configured":
        if reason is not None:
            add("corpus-planning-applicability", target, "fail",
                "configured requires null reason")
        paths = []
        for field in ("global_map", "capability_matrix", "gap_register"):
            value = artifacts.get(field)
            if not isinstance(value, str) or not value.strip() or \
                    not value.lower().endswith(".yaml"):
                add("corpus-planning-artifact", target + ":" + field, "fail",
                    "configured requires a repository-relative .yaml path")
            else:
                paths.append(value.strip())
        if len(set(paths)) != len(paths):
            add("corpus-planning-artifact", target, "fail",
                "artifact bindings must be distinct")
        if not scale:
            add("corpus-planning-scale", target, "fail",
                "configured requires at least one scale item")
        values = set()
        eligible = False
        for index, raw in enumerate(scale):
            label = "%s:capability_scale[%d]" % (target, index)
            row = closed(raw, CORPUS_SCALE_FIELDS, label)
            if type(row.get("rank")) is not int or row.get("rank") != index:
                add("corpus-planning-scale", label, "fail",
                    "rank must equal zero-based list position %d" % index)
            value = row.get("value")
            predicate = row.get("predicate")
            if not isinstance(value, str) or not value.strip():
                add("corpus-planning-scale", label, "fail",
                    "value must be a non-empty string")
            elif value in values:
                add("corpus-planning-scale", label, "fail",
                    "scale value must be unique")
            else:
                values.add(value)
            if not isinstance(predicate, str) or not predicate.strip():
                add("corpus-planning-scale", label, "fail",
                    "predicate must be a non-empty string")
            if type(row.get("target_eligible")) is not bool:
                add("corpus-planning-scale", label, "fail",
                    "target_eligible must be boolean")
            eligible = eligible or row.get("target_eligible") is True
        if scale and not eligible:
            add("corpus-planning-scale", target, "fail",
                "at least one scale item must be target eligible")
        if not isinstance(authority.get("role_id"), str) or \
                not authority.get("role_id", "").strip():
            add("corpus-planning-authority", target, "fail",
                "configured requires a non-empty role_id")
        if authority.get("decision_scope_id") != CORPUS_DECISION_SCOPE:
            add("corpus-planning-authority", target, "fail",
                "decision_scope_id must be %s" % CORPUS_DECISION_SCOPE)
    elif state == "not-applicable":
        if not isinstance(reason, str) or not reason.strip():
            add("corpus-planning-applicability", target, "fail",
                "not-applicable requires a non-empty reason")
        if any(artifacts.get(field) is not None
               for field in CORPUS_ARTIFACT_FIELDS):
            add("corpus-planning-artifact", target, "fail",
                "not-applicable requires all artifact bindings to be null")
        if scale:
            add("corpus-planning-scale", target, "fail",
                "not-applicable requires an empty scale list")
        if any(authority.get(field) is not None
               for field in CORPUS_AUTHORITY_FIELDS):
            add("corpus-planning-authority", target, "fail",
                "not-applicable requires null authority fields")
    else:
        add("corpus-planning-applicability", target, "fail",
            "state must be exactly configured or not-applicable")


def main():
    ap = argparse.ArgumentParser(
        description="Profile manifest completeness and unfilled-template check")
    ap.add_argument("profile_dir", help="the profile directory to check "
                                        "(e.g. profiles/<profile-id>)")
    ap.add_argument("--root", default=REPO_ROOT,
                    help="vault root that vault-relative bindings resolve "
                         "against (default: this script's repository root)")
    ap.add_argument("--interface", default=None,
                    help="normative slot interface file "
                         "(default: %s under --root)" % DEFAULT_INTERFACE)
    ap.add_argument("--defaults", default=None,
                    help="machine-readable profile-form placeholder registry "
                         "(default: %s under --root)" % DEFAULT_DEFAULTS)
    ap.add_argument("--execution-defaults", default=None,
                    help="kernel execution-default override registry "
                         "(default: %s under --root)"
                         % DEFAULT_EXECUTION_DEFAULTS)
    ap.add_argument("--receipts", help="JSONL path to append machine-readable receipts to")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    profile_dir = os.path.abspath(args.profile_dir)
    profile_disp = os.path.relpath(profile_dir, root).replace(os.sep, "/")
    interface_path = args.interface or os.path.join(root, DEFAULT_INTERFACE)
    defaults_path = args.defaults or os.path.join(root, DEFAULT_DEFAULTS)
    execution_defaults_path = (args.execution_defaults or
                               os.path.join(root, DEFAULT_EXECUTION_DEFAULTS))

    receipts = []
    seq = 0

    def add(check, target, result, details):
        nonlocal seq
        seq += 1
        receipts.append(kblib.make_receipt(
            TOOL, TOOL_VERSION, check, target, result, details, seq))

    # ---- inputs must be readable before anything can be judged ----
    if not os.path.isdir(profile_dir):
        add("profile-dir-missing", profile_disp, "fail",
            "profile directory does not exist; a scan with nothing to check "
            "is an invocation error, never a pass")
        print("check_profile: FAIL — no such profile directory: %s" % args.profile_dir)
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    manifest_path = os.path.join(profile_dir, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        add("manifest-missing", "%s/%s" % (profile_disp, MANIFEST_NAME), "fail",
            "the profile manifest %s is missing; every slot binding is "
            "declared there, so nothing about this profile can be verified"
            % MANIFEST_NAME)
        print("check_profile: FAIL — %s has no %s" % (profile_disp, MANIFEST_NAME))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    try:
        interface_text = read_text(interface_path)
    except OSError as exc:
        add("interface-unreadable", DEFAULT_INTERFACE, "fail",
            "cannot read the normative slot interface: %s" % exc)
        print("check_profile: FAIL — cannot read interface %s: %s" % (interface_path, exc))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    try:
        defaults = kblib.parse_yaml_subset(read_text(defaults_path))
    except (OSError, kblib.YamlSubsetError) as exc:
        add("defaults-unreadable", DEFAULT_DEFAULTS, "fail",
            "cannot read/parse the profile-form placeholder registry: %s" % exc)
        print("check_profile: FAIL — cannot read defaults %s: %s" % (defaults_path, exc))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    try:
        execution_defaults = kblib.parse_yaml_subset(
            read_text(execution_defaults_path))
    except (OSError, kblib.YamlSubsetError) as exc:
        add("execution-defaults-unreadable", DEFAULT_EXECUTION_DEFAULTS, "fail",
            "cannot read/parse the kernel execution-default registry: %s" % exc)
        print("check_profile: FAIL — cannot read execution defaults %s: %s"
              % (execution_defaults_path, exc))
        kblib.write_receipts(args.receipts, receipts)
        return kblib.exit_code(receipts)

    sentinel = str(defaults.get("unfilled_sentinel") or "TODO(profile)")
    reserved_ids = {str(v) for v in (defaults.get("reserved_profile_ids") or [])}
    overridable = {str(e.get("item")): e
                   for e in (execution_defaults.get("overridable") or [])
                   if isinstance(e, dict) and e.get("item")}
    constitutional = {str(e.get("item")): e
                      for e in (execution_defaults.get("constitutional") or [])
                      if isinstance(e, dict) and e.get("item")}

    manifest_text = read_text(manifest_path)
    manifest_disp = "%s/%s" % (profile_disp, MANIFEST_NAME)

    manifest_h2s = h2_headings(manifest_text)
    for heading in ("Profile Identity", SLOTS_SECTION, OVERRIDES_SECTION):
        count = manifest_h2s.count(heading)
        if count > 1:
            add("manifest-section-duplicate", "%s#%s" %
                (manifest_disp, heading), "fail",
                "manifest contains %d `%s` sections; exactly one is allowed"
                % (count, heading))

    slots = interface_slots(interface_text)
    if not slots:
        add("interface-no-slots", DEFAULT_INTERFACE, "fail",
            "the interface file declares no '<name>%s' H2 heading; with no "
            "slot list there is nothing to check against" % SLOT_SUFFIX)

    # ---- block 1: unfilled sentinel anywhere under the profile directory ----
    hits, files_read, files_skipped = scan_sentinel(profile_dir, sentinel)
    for rel, lineno in hits:
        add("unfilled-placeholder", "%s/%s:%d" % (profile_disp, rel, lineno), "fail",
            "line still carries the unfilled sentinel %r; a profile with any "
            "TODO left is a template skeleton, not a runnable profile"
            % sentinel)

    # ---- block 2: placeholder profile_id ----
    profile_id, identity_errors = kblib.profile_identity(
        manifest_text, os.path.basename(profile_dir), reserved_ids
    )
    for check, details in identity_errors:
        target = ("%s#Profile Identity" % manifest_disp
                  if check == "profile-id-missing"
                  else "%s#profile_id" % manifest_disp)
        add(check, target, "fail", details)

    # ---- explicit optional/conditional block declarations ----
    declaration_count = 0
    for rel, heading, kind, value, tables in profile_declarations(profile_dir):
        declaration_count += 1
        target = "%s/%s#%s" % (profile_disp, rel, heading)
        if sentinel in value:
            continue
        active = value == "Configured"
        registration_inactive = value == "None"
        applicability_inactive = bool(
            re.fullmatch(r"Not applicable — .+", value)
        )
        inactive = registration_inactive or applicability_inactive
        valid = (
            kind == "Registration" and (active or registration_inactive)
        ) or (
            kind == "Applicability" and (active or applicability_inactive)
        )
        if not valid:
            expected = ("`None` or `Configured`" if kind == "Registration"
                        else "`Configured` or `Not applicable — <reason>`")
            add("declaration-invalid", target, "fail",
                "%s declaration %r is invalid; use %s"
                % (kind, value, expected))
            continue
        if active:
            if not tables:
                add("configured-table-missing", target, "fail",
                    "Configured declares an active block, but the section has "
                    "no table to carry its bindings")
            for table_no, (header, rows) in enumerate(tables, 1):
                if not rows:
                    add("configured-table-empty", target, "fail",
                        "Configured table %d has no data row" % table_no)
                    continue
                for row_no, cells in enumerate(rows, 1):
                    if len(cells) != len(header) or any(not cell for cell in cells):
                        add("configured-table-incomplete", target, "fail",
                            "Configured table %d row %d has %d/%d cells or an "
                            "empty cell" %
                            (table_no, row_no, len(cells), len(header)))
        elif inactive and any(rows for _, rows in tables):
            add("inactive-table-has-rows", target, "fail",
                "%s leaves active table rows behind; remove those rows so the "
                "single declaration is authoritative" % value)

    # ---- slot coverage and binding resolution ----
    bindings, duplicate_bindings = parse_bindings(manifest_text)
    for name in duplicate_bindings:
        add("slot-binding-duplicate", "%s#%s" %
            (manifest_disp, SLOTS_SECTION), "fail",
            "slot `%s` is bound more than once; one manifest slot must have "
            "exactly one authoritative binding" % name)
    if slots and not bindings:
        add("slots-section-empty", "%s#%s" % (manifest_disp, SLOTS_SECTION), "fail",
            "the %s section binds no slots; the composed standard cannot be "
            "judged loaded when no slot resolves" % SLOTS_SECTION)

    bound_ok = 0
    for slot in slots:
        binding = bindings.get(slot)
        if binding is None:
            add("slot-unbound", "%s#%s" % (manifest_disp, slot), "fail",
                "interface slot `%s` is not bound in %s; when a slot required "
                "by the current task is missing, the composed standard must "
                "not be judged fully loaded" % (slot, SLOTS_SECTION))
            continue
        kind, detail = resolve_binding(binding, root, profile_dir)
        if kind == "path":
            bound_ok += 1
            if slot == CORPUS_PLANNING_SLOT:
                target = os.path.relpath(
                    detail, root).replace(os.sep, "/")
                if not target.lower().endswith(".yaml"):
                    add("corpus-planning-binding", target, "fail",
                        "Corpus Planning must bind a restricted-YAML .yaml file")
                else:
                    validate_corpus_planning_slot(detail, target, add)
            elif slot == AUDIT_DIMENSION_SLOT:
                target = (os.path.relpath(detail, root).replace(os.sep, "/") +
                          "#" + AUDIT_DIMENSION_SECTION)
                try:
                    with open(detail, encoding="utf-8") as handle:
                        registry_text = handle.read()
                except (OSError, UnicodeError) as exc:
                    add("audit-dimension-registry-unreadable", target, "fail",
                        "cannot read the bound registry: %s" % exc)
                else:
                    _registration, _rows, registry_errors = (
                        parse_audit_dimension_registry(registry_text))
                    for check, details in registry_errors:
                        add(check, target, "fail", details)
        elif kind == "inline":
            if slot == AUDIT_DIMENSION_SLOT:
                add("audit-dimension-binding", "%s#%s" %
                    (manifest_disp, slot), "fail",
                    "Audit Dimension Registry is a required file-bound slot; "
                    "an inline declaration cannot supply its canonical "
                    "Extension Dimensions table")
            elif any(h == slot or h.startswith(slot + " ")
                   for h in h2_headings(manifest_text)):
                bound_ok += 1
            else:
                add("slot-inline-unbacked", "%s#%s" % (manifest_disp, slot), "fail",
                    "slot `%s` is declared inline, but the manifest has no H2 "
                    "section starting with that slot name to carry the "
                    "declaration" % slot)
        elif kind == "unresolved":
            add("slot-binding-unresolved", "%s#%s" % (manifest_disp, slot), "fail",
                "slot `%s` binds to %r, which does not exist under the profile "
                "directory or the vault root" % (slot, detail))
        elif kind == "outside-profile":
            add("slot-binding-outside-profile", "%s#%s" %
                (manifest_disp, slot), "fail",
                "slot `%s` resolves outside the selected profile directory: "
                "%s; a profile must be a self-contained configuration package"
                % (slot, detail))
        else:
            add("slot-binding-unrecognized", "%s#%s" % (manifest_disp, slot), "fail",
                "slot `%s` binding %r is neither a profile-contained path nor an "
                "inline declaration" % (slot, binding))

    for name in sorted(bindings):
        if name not in slots:
            add("slot-not-in-interface", "%s#%s" % (manifest_disp, name), "candidate",
                "`%s` is bound in %s but is not a slot the interface defines; "
                "whether this extension binding is reasonable is a human call"
                % (name, SLOTS_SECTION))

    # ---- Execution Default Overrides sparse table ----
    override_lines = section_lines(manifest_text, OVERRIDES_SECTION)
    override_rows = list(table_rows(override_lines))
    data_rows = override_rows[1:] if override_rows else []
    registered = []
    for cells in data_rows:
        item = unbacktick(cells[0]) if cells else ""
        value = unbacktick(cells[1]) if len(cells) > 1 else ""
        registered.append((item, value))
        if len(cells) != 2:
            add("override-row-shape", "%s#%s" %
                (manifest_disp, item or "<empty>"), "fail",
                "override rows must contain exactly two cells; found %d"
                % len(cells))
    if not override_lines:
        add("overrides-section-missing", "%s#%s" % (manifest_disp, OVERRIDES_SECTION),
            "fail",
            "the manifest has no %s section; the sparse explicit-override "
            "table is required even when it has no data rows"
            % OVERRIDES_SECTION)
    else:
        seen = set()
        for item, value in registered:
            target = "%s#%s" % (manifest_disp, item or "<empty>")
            if item in seen:
                add("override-item-duplicate", target, "fail",
                    "override item `%s` appears more than once" % item)
                continue
            seen.add(item)
            if item in constitutional:
                add("override-constitutional-item", target, "fail",
                    "`%s` is a constitutional constant (owner: %s) and is not "
                    "overridable" %
                    (item, constitutional[item].get("owner", "kernel")))
            elif item not in overridable:
                add("override-item-unknown", target, "fail",
                    "`%s` is not in the closed overridable registry" % item)
            elif not value:
                add("override-choice-empty", target, "fail",
                    "override item `%s` has no explicit profile value" % item)
            elif value == "use-kernel-default":
                add("override-redundant-default", target, "fail",
                    "remove `%s`; unlisted items already use the kernel default"
                    % item)
            else:
                entry = overridable[item]
                domain = entry.get("value_domain")
                if domain is None:
                    continue
                domain = str(domain)
                validate = VALUE_DOMAINS.get(domain)
                if validate is None:
                    add("override-value-domain-unknown", target, "fail",
                        "the registry gives `%s` the value domain %r, which "
                        "this checker does not implement; registry and checker "
                        "must be updated together" % (item, domain))
                    continue
                reason = validate(value)
                if reason:
                    add("override-value-domain", target, "fail",
                        "override value `%s` for `%s` leaves its registered "
                        "value domain %r (owner: %s): %s"
                        % (value, item, domain,
                           entry.get("owner", "kernel"), reason))

    fails = [r for r in receipts if r["result"] == "fail"]
    if not fails:
        add("profile-check-summary", profile_disp, "pass",
            "profile_id=%s; %d/%d interface slot(s) bound and resolved; %d "
            "explicit override(s) registered; %d optional/conditional "
            "declaration(s) structurally consistent; no unfilled sentinel, "
            "placeholder profile id, or unresolved binding remains"
            % (profile_id, bound_ok, len(slots), len(registered),
               declaration_count))

    # ---- human-readable summary ----
    print("check_profile: %s (profile_id=%s)"
          % (profile_disp, profile_id if profile_id else "<none>"))
    print("  interface=%s slots=%d bound_ok=%d explicit_overrides=%d "
          "files_scanned=%d files_skipped=%d"
          % (os.path.relpath(interface_path, root).replace(os.sep, "/"),
             len(slots), bound_ok, len(registered), files_read, files_skipped))
    print("  sentinel_hits(fail)=%d" % len(hits))
    for r in receipts:
        if r["result"] == "fail":
            print("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))
        elif r["result"] == "candidate":
            print("  [CAND %s] %s — %s" % (r["check"], r["target"], r["details"]))
    if fails:
        print("  Conclusion: NOT LOADABLE — %d failure(s). This profile is "
              "incomplete; the composed standard must not be judged fully "
              "loaded." % len(fails))
    else:
        print("  Conclusion: profile manifest complete; every interface slot "
              "resolves and no unfilled-template marker remains. This checks "
              "structure, not whether the answers are good.")

    kblib.write_receipts(args.receipts, receipts)
    return kblib.exit_code(receipts)


if __name__ == "__main__":
    sys.exit(main())
