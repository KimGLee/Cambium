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
- Each of the 13 slots is file-bound. A binding may spell its exact
  profile-relative path in a wiki link, Markdown link, or one inline-code span;
  it has no extension guessing, path normalization, case alias,
  repository-root fallback, or inline-manifest alternative. Execution Default
  Overrides is the sole manifest-resident contract.
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
- Profile dependency closure: the Audit Dimension and Registered Scan
  registries are compiled through ``profile_contract`` into one typed,
  fail-closed graph.  Predicate owners and every explicit verifier
  ``--config`` stay inside the selected Profile; optional owner headings must
  resolve exactly once.  The passing Gate receipt binds both the complete
  Profile tree and the typed edge graph.
- Optional/conditional declarations: `Configured` must be backed by complete
  table rows; `None` and `Not applicable — <reason>` must not retain active
  rows. This makes one declaration control one block instead of relying on
  repeated prose fallbacks.

Two independent incompleteness blocks, either of which fails the profile:
1. the unfilled sentinel (default `TODO(profile)`) appearing anywhere under the
   profile directory;
2. a `profile_id` that is missing or still one of the reserved placeholder
   values.
Each block is cleared only by editing the file.  Clearing them is necessary
but no longer sufficient: the manifest, all slots, and the transitive Profile
dependency closure must also resolve. None of these checks is evidence that
the answers are *good*; content quality stays a human call.

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

from collections.abc import Mapping
import contextlib
from dataclasses import dataclass
import io
import json
import os
import re
import sys
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kblib
import metadata_execution_contract
import profile_contract

TOOL = "check_profile"
TOOL_VERSION = "2.0.0"
GATE_ID = "profile-load"
GATE_CHECK = "profile-check-summary"
GATE_DIMENSION = "guidance_and_contract"

# ``None`` has a public meaning for :func:`evaluate_profile_load`: omit Queue
# identity from the in-memory receipts.  The CLI still needs its historical
# behaviour of reading live identity from ``--root``, so an internal sentinel
# distinguishes that default from an explicit identity-free evaluation.
_LIVE_RUNTIME_RECEIPT_IDENTITY = object()


@dataclass(frozen=True)
class ProfileLoadEvaluation:
    """One complete, in-memory evaluation of the ``profile-load`` Gate.

    ``contract`` is exposed only when the same invocation emitted the passing
    Gate summary.  Consumers therefore cannot accidentally authorize a partial
    typed IR returned alongside fail/candidate findings.  ``findings`` contains
    only non-pass receipts; the authoritative pass receipt, when present, is
    available separately as ``summary_receipt``.
    """

    exit_code: int
    findings: Tuple[dict, ...]
    contract: Optional[profile_contract.ProfileContract]
    profile_id: Optional[str]
    profile_snapshot_sha256: Optional[str]
    profile_contract_fingerprint: Optional[str]
    execution_default_overrides: Tuple[Tuple[str, str], ...]
    profile_snapshot: Optional[object]
    profile_load_inputs_sha256: Optional[str]
    summary_receipt: Optional[dict]
    output: str

    @property
    def authorized(self):
        return (
            self.exit_code == 0 and
            self.contract is not None and
            self.profile_id is not None and
            self.summary_receipt is not None and
            self.profile_snapshot_sha256 is not None and
            self.profile_contract_fingerprint is not None and
            self.profile_load_inputs_sha256 is not None
        )


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_INTERFACE = "profiles/README.md"
DEFAULT_DEFAULTS = "Tools/schemas/execution_defaults.template.yaml"
DEFAULT_EXECUTION_DEFAULTS = (
    "kernel/K00 Standards Control/execution-defaults-base.yaml"
)
DEFAULT_OPERATION_CAPABILITIES = "Tools/operation-capabilities.yaml"
DEFAULT_METADATA_AUTHORITY = (
    "kernel/K08 Metadata and Status/metadata-authority-base.yaml")
DEFAULT_METADATA_CONTRACT = (
    "Tools/compiled/metadata-execution-contract.json")
DEFAULT_APPLICABILITY_BASE = profile_contract.KERNEL_APPLICABILITY_PATH
DEFAULT_RELATIONSHIP_BASE = profile_contract.KERNEL_RELATIONSHIP_PATH
DEFAULT_GATE_REGISTRY = (
    "kernel/K00 Standards Control/12 Control Registry.md")
CANONICAL_PROFILE_LOAD_INPUTS = (
    DEFAULT_INTERFACE,
    DEFAULT_DEFAULTS,
    DEFAULT_EXECUTION_DEFAULTS,
    DEFAULT_OPERATION_CAPABILITIES,
    DEFAULT_METADATA_AUTHORITY,
    DEFAULT_METADATA_CONTRACT,
    DEFAULT_APPLICABILITY_BASE,
    DEFAULT_RELATIONSHIP_BASE,
    DEFAULT_GATE_REGISTRY,
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

STRUCTURE_REGISTRY_SLOT = "Structure Registry"
PRIORITY_RUBRIC_SLOT = "Priority Rubric"
METADATA_CONTRACT_SLOT = "Metadata Contract"

AUDIT_DIMENSION_SLOT = "Audit Dimension Registry"

# ---------------------------------------------------------------------------
# Structured finding classification (``--json``).
#
# An assisting agent triaging a failed run needs to know which findings it
# can fix directly and re-run (MECHANICAL: path resolution, identity and
# directory agreement, table/manifest shape, self-reference containment,
# declaration word shape) and which findings name an operator answer that is
# missing or unconfirmed (SEMANTIC_UNRESOLVED: the unfilled sentinel and
# every other finding whose subject is the *content* of a decision rather
# than the shape of one already made).  The map is a closed dict over every
# check code this producer can emit -- its own literals, the kblib
# identity/shape validators it consumes, and the profile_contract
# diagnostics it forwards (``profile-contract-sentinel`` is re-emitted as
# ``unfilled-placeholder`` and therefore does not appear here).
# test_check_profile pins the coverage against the emitting sources, so
# adding a check without classifying it fails the suite.
#
# Non-obvious calls, decided by reading each check:
# * profile-id-*: the manifest identity must equal the profile directory
#   name (profile-id-directory-mismatch), so the correct value is a pure
#   function of the package location -- mechanical, including the reserved
#   placeholder case.
# * declaration-invalid / extension-dimensions-registration /
#   corpus-planning-applicability: the operator's declaration exists but is
#   misspelled or mis-shaped; normalizing an already-made choice to its
#   legal spelling is mechanical.  (An *unanswered* declaration still
#   carries the sentinel and fails as unfilled-placeholder instead.)
# * configured-table-missing/-empty/-incomplete, *-row-empty, and the empty
#   registry findings: the declared structure demands content that simply is
#   not there (or a cell is blank); inventing that content would be a domain
#   decision, so these stay semantic-unresolved.
# * override-choice-empty / override-value-domain: the profile value is
#   absent or rejected; an admissible replacement is an operator choice.
#   The sibling override rows (duplicate, unknown item, constitutional,
#   redundant default, row shape, unknown domain name) each have one
#   determined fix -- remove or reshape the row -- and stay mechanical.
# * slot-not-in-interface: the tool's own result text says whether the
#   extension binding is reasonable "is a human call" -- semantic-unresolved.
# ---------------------------------------------------------------------------
MECHANICAL = "mechanical"
SEMANTIC_UNRESOLVED = "semantic-unresolved"

_SEMANTIC_UNRESOLVED_CHECKS = frozenset((
    "unfilled-placeholder",
    "slot-not-in-interface",
    "override-choice-empty",
    "override-value-domain",
    "configured-table-missing",
    "configured-table-empty",
    "configured-table-incomplete",
    "extension-dimensions-configured-empty",
    "extension-dimensions-row-empty",
    "judgment-items-empty",
    "judgment-items-row-empty",
    "registered-scans-empty",
    "registered-scans-row-empty",
    "extension-gates-configured-empty",
    "extension-gates-row-empty",
))

_MECHANICAL_CHECKS = frozenset((
    # invocation and canonical-input handling
    "profile-receipt-path-inside-profile",
    "profile-load-noncanonical-input",
    "profile-load-input-unreadable",
    "profile-load-input-changed",
    "profile-load-metadata-contract-invalid",
    "profile-dir-missing",
    "manifest-missing",
    "profile-snapshot-invalid",
    "profile-snapshot-changed-during-check",
    "interface-unreadable",
    "defaults-unreadable",
    "execution-defaults-unreadable",
    "profile-text-unreadable",
    # interface and manifest shape
    "interface-no-slots",
    "profile-interface-slot-registry-mismatch",
    "manifest-section-duplicate",
    "slots-section-empty",
    "slot-unbound",
    "slot-binding-duplicate",
    "slot-binding-inline",
    "slot-binding-invalid",
    "slot-binding-unresolved",
    "slot-binding-outside-profile",
    "slot-binding-unrecognized",
    # manifest identity (the value is a pure function of the directory name)
    "profile-id-missing",
    "profile-id-duplicate",
    "profile-id-placeholder",
    "profile-id-invalid",
    "profile-id-directory-mismatch",
    # optional/conditional declarations
    "declaration-invalid",
    "inactive-table-has-rows",
    # Corpus Planning slot envelope
    "corpus-planning-binding",
    "corpus-planning-yaml",
    "corpus-planning-schema",
    "corpus-planning-applicability",
    "corpus-planning-artifact",
    "corpus-planning-scale",
    "corpus-planning-authority",
    # Structure Registry slot shape (kblib validator)
    "structure-registry-binding",
    "structure-registry-yaml",
    "structure-registry-schema",
    "structure-registry-applicability",
    "structure-registry-unit",
    "structure-registry-parent",
    "structure-registry-layer",
    "structure-registry-layout",
    "structure-registry-role",
    # Priority Rubric quota block
    "priority-quota-policy",
    # Metadata Contract slot shape (kblib validator)
    "metadata-contract-binding",
    "metadata-contract-yaml",
    "metadata-contract-schema",
    "metadata-contract-applicability",
    "metadata-contract-entry",
    "metadata-contract-condition",
    "metadata-contract-section-role",
    "metadata-contract-boundary-projection",
    # Execution Default Overrides table
    "overrides-section-missing",
    "override-row-shape",
    "override-item-duplicate",
    "override-constitutional-item",
    "override-item-unknown",
    "override-redundant-default",
    "override-value-domain-unknown",
    # typed dependency closure (profile_contract diagnostics)
    "profile-contract-manifest-path",
    "profile-contract-profile-root",
    "profile-contract-snapshot-invalid",
    "profile-contract-manifest-name",
    "profile-contract-manifest-unreadable",
    "profile-contract-slot-duplicate",
    "profile-contract-slot-missing",
    "profile-contract-slot-invalid",
    "profile-contract-slot-unresolved",
    "profile-contract-slot-outside-profile",
    "profile-contract-slot-unreadable",
    "extension-dimensions-registration",
    "extension-dimensions-none-with-rows",
    "extension-dimension-id-invalid",
    "extension-dimension-id-duplicate",
    "extension-dimension-base-collision",
    "extension-dimension-target-invalid",
    "judgment-item-id-invalid",
    "judgment-item-id-duplicate",
    "judgment-item-dimension-unknown",
    "judgment-item-evidence-role-invalid",
    "registered-scan-id-invalid",
    "registered-scan-id-duplicate",
    "registered-scan-judgment-reference",
    "registered-scans-required-count",
    "registered-scan-command-literal",
    "registered-scan-command-parse",
    "registered-scan-command-shape",
    "registered-scan-command-interpreter",
    "registered-scan-command-script",
    "registered-scan-command-root",
    "registered-scan-command-shell-operator",
    "registered-scan-command-gate-option",
    "registered-scan-command-scan-id",
    "registered-scan-command-config",
    # typed Profile extension Gate execution contract
    "extension-gates-registration",
    "extension-gates-none-with-rows",
    "extension-gate-deterministic-completion",
    "extension-gate-id-invalid",
    "extension-gate-id-duplicate",
    "extension-gate-transition-invalid",
    "extension-gate-transition-duplicate",
    "extension-gate-owner-registry",
    "extension-gate-owner-reference",
    "extension-gate-owner-heading-empty",
    "extension-gate-owner-heading-missing",
    "extension-gate-owner-path-invalid",
    "extension-gate-owner-unreadable",
    "extension-gate-owner-heading-non-markdown",
    "extension-gate-owner-heading-count",
    "extension-gate-role-registry",
    "extension-gate-role-reference",
    "extension-gate-vocabulary-registry",
    "extension-gate-metadata-contract",
    "extension-gate-kernel-metadata-registry",
    "extension-gate-field-reference",
    "extension-gate-field-applicability",
    "extension-gate-field-shape",
    "extension-gate-field-kernel-collision",
    "extension-gate-field-completion",
    "extension-gate-completion-invalid",
    "extension-gate-completion-reference",
    "extension-gate-judgment-reference",
    "extension-gate-producer-kind",
    "extension-gate-capability-registry",
    "extension-gate-producer-capability",
    "extension-gate-producer-reference",
    "extension-gate-receipt-schema",
    "extension-gate-consumer-capability",
    "extension-gate-writer-capability",
    # registry table shape (composed `<section>-<shape>` diagnostics)
    "extension-dimensions-section-count",
    "extension-dimensions-table-count",
    "extension-dimensions-table-shape",
    "extension-dimensions-table-header",
    "extension-dimensions-table-separator",
    "extension-dimensions-row-shape",
    "judgment-items-section-count",
    "judgment-items-table-count",
    "judgment-items-table-shape",
    "judgment-items-table-header",
    "judgment-items-table-separator",
    "judgment-items-row-shape",
    "registered-scans-section-count",
    "registered-scans-table-count",
    "registered-scans-table-shape",
    "registered-scans-table-header",
    "registered-scans-table-separator",
    "registered-scans-row-shape",
    "extension-gates-section-count",
    "extension-gates-table-count",
    "extension-gates-table-shape",
    "extension-gates-table-header",
    "extension-gates-table-separator",
    "extension-gates-row-shape",
    # Profile-owned dependency resolution (composed `<kind>-<failure>`)
    "predicate-owner-heading-empty",
    "predicate-owner-heading-missing",
    "predicate-owner-path-invalid",
    "predicate-owner-path-outside-profile",
    "predicate-owner-unreadable",
    "predicate-owner-heading-non-markdown",
    "predicate-owner-heading-count",
    "scan-config-heading-empty",
    "scan-config-heading-missing",
    "scan-config-path-invalid",
    "scan-config-path-outside-profile",
    "scan-config-unreadable",
    "scan-config-heading-non-markdown",
    "scan-config-heading-count",
))

if _MECHANICAL_CHECKS & _SEMANTIC_UNRESOLVED_CHECKS:
    raise AssertionError(
        "finding category defined twice: %s" %
        sorted(_MECHANICAL_CHECKS & _SEMANTIC_UNRESOLVED_CHECKS))

FINDING_CATEGORIES = {
    **{check: MECHANICAL for check in sorted(_MECHANICAL_CHECKS)},
    **{check: SEMANTIC_UNRESOLVED
       for check in sorted(_SEMANTIC_UNRESOLVED_CHECKS)},
}


def finding_category(check):
    """Category for one emitted check code; unknown codes stay conservative.

    The closed map is pinned by tests, so an unknown code here means a
    mis-deployed tree; classifying it as semantic-unresolved keeps an
    assisting agent from auto-"fixing" a finding nobody classified.
    """
    return FINDING_CATEGORIES.get(check, SEMANTIC_UNRESOLVED)


def canonical_profile_load_inputs(root):
    """Return immutable canonical producer inputs and their aggregate hash."""
    snapshots = {}
    for relative in CANONICAL_PROFILE_LOAD_INPUTS:
        snapshots[relative] = kblib.repository_file_snapshot(
            root, relative, singly_linked=True)
    capabilities = kblib.parse_yaml_subset(
        snapshots[DEFAULT_OPERATION_CAPABILITIES].read_text())
    capabilities = metadata_execution_contract.\
        validate_operation_capabilities_document(capabilities)
    for relative in metadata_execution_contract.\
            capability_implementation_paths(capabilities):
        snapshots[relative] = kblib.repository_file_snapshot(
            root, relative, singly_linked=True)
    fingerprint = kblib.sha256_bytes(
        "\0".join(
            "%s\0%s" % (relative, snapshots[relative].sha256)
            for relative in sorted(snapshots)))
    return snapshots, fingerprint


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
    """Blank non-authoritative Markdown, retaining inline code and line count."""
    return kblib.blank_markdown_authority(text)


def h2_headings(text):
    """Return the H2 heading texts of a fence-blanked document, in order."""
    return [h for _, level, h in kblib.headings_of(blank_fenced(text)) if level == 2]


def section_lines(text, heading):
    """Return the lines of the H2 section with this exact heading (or [])."""
    lines = blank_fenced(text).splitlines()
    out = []
    inside = False
    for line in lines:
        parsed = kblib.markdown_atx_heading(line)
        if parsed is not None:
            if inside and parsed[0] <= 2:
                break
            inside = (parsed[0] == 2 and parsed[1] == heading)
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
        parsed = kblib.markdown_atx_heading(line)
        if parsed is not None and parsed[0] <= 2:
            if current is not None:
                sections.append((current, body))
            current = parsed[1] if parsed[0] == 2 else None
            body = []
            continue
        if current is not None:
            body.append(line)
    if current is not None:
        sections.append((current, body))
    return sections


def read_text(path):
    with open(path, encoding="utf-8", errors="strict") as handle:
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


def profile_declarations(profile_snapshot):
    """Yield declarations from the same immutable bytes as profile-load."""
    prefix = profile_snapshot.relative_directory.rstrip("/") + "/"
    for repository_path, data in sorted(profile_snapshot.files.items()):
        if (not repository_path.startswith(prefix) or
                not repository_path.lower().endswith(".md")):
            continue
        rel = repository_path[len(prefix):]
        sections = h2_sections(data.decode("utf-8"))
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


def scan_sentinel(profile_snapshot, sentinel):
    """Return marker locations from every regular Profile file.

    The sentinel is ASCII text, so scanning bytes covers uncommon suffixes
    and binary assets without pretending those assets are UTF-8 documents.
    Known text suffixes are still decoded strictly; typed authority files with
    other suffixes receive their strict-UTF-8 check from ``profile_contract``.
    """
    hits, read_n, skipped_n = [], 0, 0
    needle = sentinel.encode("utf-8")
    prefix = profile_snapshot.relative_directory.rstrip("/") + "/"
    for repository_path, data in sorted(profile_snapshot.files.items()):
        if not repository_path.startswith(prefix):
            skipped_n += 1
            continue
        read_n += 1
        rel = repository_path[len(prefix):]
        if repository_path.lower().endswith(TEXT_SUFFIXES):
            data.decode("utf-8")
        for lineno, line in enumerate(data.splitlines(), 1):
            if needle in line:
                hits.append((rel, lineno))
    return hits, read_n, skipped_n


def validate_corpus_planning_slot(path, target, add, text=None):
    """Validate the Profile slot's closed restricted-YAML envelope."""
    try:
        document = kblib.parse_yaml_subset(
            read_text(path) if text is None else text)
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


def main(argv=None, *, _evaluation_out=None,
         _receipt_identity=_LIVE_RUNTIME_RECEIPT_IDENTITY,
         _write_receipts=True):
    ap = kblib.ArgumentParser(
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
    ap.add_argument("--json", action="store_true",
                    help="write one deterministic JSON object (tool, root, "
                         "result, findings each carrying a closed "
                         "mechanical/semantic-unresolved category) to stdout "
                         "instead of the human summary; receipts and exit "
                         "codes are unchanged")
    args = ap.parse_args(argv)

    def say(message):
        """Human summary line; silenced when --json owns stdout."""
        if not args.json:
            print(message)

    # Canonicalize both endpoints before relativizing.  macOS exposes the
    # same temporary tree as both /var and /private/var; mixing those aliases
    # must not make a contained Profile appear to escape its repository.
    root = os.path.realpath(os.path.abspath(args.root))
    profile_dir = os.path.realpath(os.path.abspath(args.profile_dir))
    profile_disp = os.path.relpath(profile_dir, root).replace(os.sep, "/")
    interface_path = args.interface or os.path.join(root, DEFAULT_INTERFACE)
    defaults_path = args.defaults or os.path.join(root, DEFAULT_DEFAULTS)
    execution_defaults_path = (args.execution_defaults or
                               os.path.join(root, DEFAULT_EXECUTION_DEFAULTS))

    checked_manifest_identity = (
        MANIFEST_NAME if profile_disp == "." else
        "%s/%s" % (profile_disp, MANIFEST_NAME)
    )
    if _receipt_identity is _LIVE_RUNTIME_RECEIPT_IDENTITY:
        live_identity = kblib.runtime_receipt_identity(root)
        if (live_identity.get("selected_profile_manifest") and
                live_identity.get("selected_profile_manifest") !=
                checked_manifest_identity):
            # Candidate Profile evaluation while a different Profile is live
            # must not combine the live Task/Standards identity with the
            # candidate manifest.  K12/17 permits a pre-Task profile-load
            # receipt to claim only the exact manifest it actually checked.
            effective_receipt_identity = {
                "selected_profile_manifest": checked_manifest_identity,
            }
        else:
            effective_receipt_identity = dict(live_identity)
    else:
        effective_receipt_identity = dict(_receipt_identity or {})

    receipts = []
    seq = 0
    contract = None
    profile_id = None
    profile_snapshot_sha256 = None
    profile_snapshot = None
    profile_load_inputs_sha256 = None
    resolved_overrides = ()
    summary = None

    def add(check, target, result, details):
        nonlocal seq
        seq += 1
        receipt = kblib.make_receipt(
            TOOL, TOOL_VERSION, check, target, result, details, seq,
            identity=effective_receipt_identity)
        receipt["gate_id"] = GATE_ID
        receipt["dimension"] = GATE_DIMENSION
        receipts.append(receipt)

    def finish(*, write_receipts=True):
        """Close one invocation and optionally expose its exact in-memory IR."""
        exit_code = kblib.exit_code(receipts)
        if write_receipts and _write_receipts:
            kblib.write_receipts(args.receipts, receipts)
        if args.json:
            # One deterministic structured-diagnostics object: same checks,
            # same order, same exit semantics as the human summary, plus the
            # closed mechanical/semantic-unresolved category per finding.
            print(json.dumps({
                "tool": TOOL,
                "tool_version": TOOL_VERSION,
                "profile_dir": profile_disp,
                "root": root,
                "result": {0: "pass", 1: "fail", 2: "candidate"}[exit_code],
                "findings": [
                    {
                        "check": receipt["check"],
                        "target": receipt["target"],
                        "details": receipt["details"],
                        "category": finding_category(receipt["check"]),
                    }
                    for receipt in receipts
                    if receipt["result"] != "pass"
                ],
            }, ensure_ascii=False, sort_keys=True, indent=2))
        if _evaluation_out is not None:
            authorized_contract = (
                contract
                if (exit_code == 0 and contract is not None and
                    contract.authorized and summary is not None)
                else None
            )
            _evaluation_out.update({
                "exit_code": exit_code,
                "receipts": tuple(receipts),
                "contract": authorized_contract,
                "profile_id": (
                    profile_id if authorized_contract is not None else None
                ),
                "profile_snapshot_sha256": profile_snapshot_sha256,
                "profile_contract_fingerprint": (
                    authorized_contract.fingerprint
                    if authorized_contract is not None else None
                ),
                "execution_default_overrides": (
                    resolved_overrides
                    if authorized_contract is not None else ()
                ),
                "profile_snapshot": (
                    profile_snapshot
                    if authorized_contract is not None else None
                ),
                "profile_load_inputs_sha256": (
                    profile_load_inputs_sha256
                    if authorized_contract is not None else None
                ),
                "summary_receipt": summary,
            })
        return exit_code

    if args.receipts:
        receipt_spellings = (
            os.path.abspath(os.fspath(args.receipts)),
            os.path.realpath(os.path.abspath(os.fspath(args.receipts))),
        )
        inside_profile = False
        for spelling in receipt_spellings:
            try:
                inside_profile = (
                    os.path.commonpath((profile_dir, spelling)) == profile_dir)
            except ValueError:
                inside_profile = False
            if inside_profile:
                break
        if inside_profile:
            add("profile-receipt-path-inside-profile", profile_disp, "fail",
                "--receipts must stay outside the Profile directory so "
                "validation cannot mutate the package whose snapshot it "
                "binds")
            say("check_profile: FAIL — receipt output cannot be written "
                  "inside the selected Profile")
            return finish(write_receipts=False)

    # ``profile-load`` is one registered Gate, not a caller-defined lint.
    # Its three normative inputs are fixed under the checked repository root;
    # allowing an invocation to substitute a smaller interface, a different
    # sentinel registry, or a broader override registry would produce an
    # indistinguishable but weaker pass receipt.
    normative_inputs = (
        ("interface", args.interface, DEFAULT_INTERFACE),
        ("defaults", args.defaults, DEFAULT_DEFAULTS),
        ("execution-defaults", args.execution_defaults,
         DEFAULT_EXECUTION_DEFAULTS),
    )
    for label, supplied, expected_relative in normative_inputs:
        if supplied is None:
            continue
        expected_absolute = os.path.join(
            root, *expected_relative.split("/"))
        supplied_absolute = os.path.abspath(os.fspath(supplied))
        if supplied_absolute != expected_absolute:
            add("profile-load-noncanonical-input", supplied_absolute, "fail",
                "--%s cannot replace the registered profile-load input `%s`; "
                "custom inputs may be inspected separately but cannot "
                "authorize this Gate" % (label, expected_relative))
    interface_path = os.path.join(root, *DEFAULT_INTERFACE.split("/"))
    defaults_path = os.path.join(root, *DEFAULT_DEFAULTS.split("/"))
    execution_defaults_path = os.path.join(
        root, *DEFAULT_EXECUTION_DEFAULTS.split("/"))

    normative_snapshots = {}
    try:
        normative_snapshots, profile_load_inputs_sha256 = \
            canonical_profile_load_inputs(root)
    except (OSError, ValueError) as exc:
        add("profile-load-input-unreadable", root, "fail",
            "cannot bind canonical profile-load inputs: %s" % exc)
        say("check_profile: FAIL — canonical profile-load input is not a "
              "stable singly-linked file: %s" % exc)
        return finish()
    try:
        metadata_authority = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_METADATA_AUTHORITY].read_text())
        operation_capabilities = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_OPERATION_CAPABILITIES].read_text())
        compiled_metadata = \
            metadata_execution_contract.compile_metadata_execution_document(
                metadata_authority, operation_capabilities,
                implementation_snapshots={
                    path: normative_snapshots[path]
                    for path in metadata_execution_contract.
                        capability_implementation_paths(
                            operation_capabilities)
                })
        if (normative_snapshots[DEFAULT_METADATA_CONTRACT].read_text() !=
                compiled_metadata.canonical_bytes.decode("utf-8")):
            raise ValueError(
                "compiled metadata execution contract is stale")
    except (OSError, UnicodeError, ValueError, kblib.YamlSubsetError,
            metadata_execution_contract.MetadataExecutionContractError) as exc:
        add("profile-load-metadata-contract-invalid",
            DEFAULT_METADATA_CONTRACT, "fail",
            "canonical metadata authority/capability bundle cannot be "
            "compiled from the same root-input snapshot: %s" % exc)
        return finish()

    # ---- inputs must be readable before anything can be judged ----
    if not os.path.isdir(profile_dir):
        add("profile-dir-missing", profile_disp, "fail",
            "profile directory does not exist; a scan with nothing to check "
            "is an invocation error, never a pass")
        say("check_profile: FAIL — no such profile directory: %s" % args.profile_dir)
        return finish()

    manifest_path = os.path.join(profile_dir, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        add("manifest-missing", "%s/%s" % (profile_disp, MANIFEST_NAME), "fail",
            "the profile manifest %s is missing; every slot binding is "
            "declared there, so nothing about this profile can be verified"
            % MANIFEST_NAME)
        say("check_profile: FAIL — %s has no %s" % (profile_disp, MANIFEST_NAME))
        return finish()

    # Bind the exact Profile bytes before reading any of its declarations.
    # A second digest below must match before a pass receipt can describe this
    # snapshot; otherwise the run combined observations from two revisions.
    try:
        profile_snapshot = kblib.repository_tree_snapshot(
            root, profile_disp)
    except (OSError, ValueError) as exc:
        add("profile-snapshot-invalid", profile_disp, "fail",
            "cannot bind the selected Profile directory snapshot: %s" % exc)
        say("check_profile: FAIL — cannot bind one immutable Profile "
              "snapshot: %s" % exc)
        return finish()
    profile_snapshot_before = profile_snapshot.sha256

    def profile_snapshot_text(path):
        relative = os.path.relpath(
            os.path.abspath(path), root).replace(os.sep, "/")
        return profile_snapshot.read_text(relative)

    try:
        interface_text = normative_snapshots[DEFAULT_INTERFACE].read_text()
    except (OSError, UnicodeError) as exc:
        add("interface-unreadable", DEFAULT_INTERFACE, "fail",
            "cannot read the normative slot interface: %s" % exc)
        say("check_profile: FAIL — cannot read interface %s: %s" % (interface_path, exc))
        return finish()

    try:
        defaults = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_DEFAULTS].read_text())
    except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
        add("defaults-unreadable", DEFAULT_DEFAULTS, "fail",
            "cannot read/parse the profile-form placeholder registry: %s" % exc)
        say("check_profile: FAIL — cannot read defaults %s: %s" % (defaults_path, exc))
        return finish()

    try:
        execution_defaults = kblib.parse_yaml_subset(
            normative_snapshots[DEFAULT_EXECUTION_DEFAULTS].read_text())
    except (OSError, UnicodeError, kblib.YamlSubsetError) as exc:
        add("execution-defaults-unreadable", DEFAULT_EXECUTION_DEFAULTS, "fail",
            "cannot read/parse the kernel execution-default registry: %s" % exc)
        say("check_profile: FAIL — cannot read execution defaults %s: %s"
              % (execution_defaults_path, exc))
        return finish()

    sentinel = str(defaults.get("unfilled_sentinel") or "TODO(profile)")
    reserved_ids = {str(v) for v in (defaults.get("reserved_profile_ids") or [])}
    overridable = {str(e.get("item")): e
                   for e in (execution_defaults.get("overridable") or [])
                   if isinstance(e, dict) and e.get("item")}
    constitutional = {str(e.get("item")): e
                      for e in (execution_defaults.get("constitutional") or [])
                      if isinstance(e, dict) and e.get("item")}

    try:
        hits, files_read, files_skipped = scan_sentinel(
            profile_snapshot, sentinel)
        manifest_text = profile_snapshot_text(manifest_path)
    except (OSError, UnicodeError) as exc:
        add("profile-text-unreadable", profile_disp, "fail",
            "Profile text files must be readable strict UTF-8: %s" % exc)
        say("check_profile: FAIL — Profile text is not strict UTF-8: %s" %
              exc)
        return finish()
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
    if tuple(slots) != profile_contract.PROFILE_FILE_SLOTS:
        add("profile-interface-slot-registry-mismatch", DEFAULT_INTERFACE,
            "fail", "canonical Profile interface slots must equal the typed "
            "linker's closed ordered registry; interface=%r linker=%r" %
            (tuple(slots), profile_contract.PROFILE_FILE_SLOTS))

    # ---- block 1: unfilled sentinel anywhere under the profile directory ----
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
    for rel, heading, kind, value, tables in profile_declarations(
            profile_snapshot):
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
                    validate_corpus_planning_slot(
                        detail, target, add,
                        text=profile_snapshot_text(detail))
            elif slot == STRUCTURE_REGISTRY_SLOT:
                target = os.path.relpath(
                    detail, root).replace(os.sep, "/")
                if not target.lower().endswith(".yaml"):
                    add("structure-registry-binding", target, "fail",
                        "Structure Registry must bind a restricted-YAML "
                        ".yaml file")
                else:
                    try:
                        document = kblib.parse_yaml_subset(
                            profile_snapshot_text(detail))
                    except (OSError, kblib.YamlSubsetError) as exc:
                        add("structure-registry-yaml", target, "fail",
                            "cannot parse restricted YAML: %s" % exc)
                    else:
                        for check, label, details in \
                                kblib.validate_structure_registry_shape(
                                    document, target):
                            add(check, label, "fail", details)
            elif slot == PRIORITY_RUBRIC_SLOT:
                target = os.path.relpath(
                    detail, root).replace(os.sep, "/")
                try:
                    rubric_text = profile_snapshot_text(detail)
                except (OSError, UnicodeError) as exc:
                    add("priority-quota-policy", target, "fail",
                        "cannot read the Priority Rubric: %s" % exc)
                else:
                    _quotas, _configured, policy_errors = \
                        kblib.priority_quota_policy(rubric_text)
                    for details in policy_errors:
                        add("priority-quota-policy", target, "fail", details)
            elif slot == METADATA_CONTRACT_SLOT:
                target = os.path.relpath(
                    detail, root).replace(os.sep, "/")
                if not target.lower().endswith(".yaml"):
                    add("metadata-contract-binding", target, "fail",
                        "Metadata Contract must bind a restricted-YAML "
                        ".yaml file")
                else:
                    try:
                        document = kblib.parse_yaml_subset(
                            profile_snapshot_text(detail))
                    except (OSError, kblib.YamlSubsetError) as exc:
                        add("metadata-contract-yaml", target, "fail",
                            "cannot parse restricted YAML: %s" % exc)
                    else:
                        for check, label, details in \
                                kblib.validate_metadata_contract_shape(
                                    document, target):
                            add(check, label, "fail", details)
        elif kind == "inline":
            add("slot-binding-inline", "%s#%s" % (manifest_disp, slot),
                "fail", "slot `%s` is file-bound; Execution Default Overrides "
                "is the only manifest-resident Profile contract" % slot)
        elif kind == "invalid":
            add("slot-binding-invalid", "%s#%s" % (manifest_disp, slot),
                "fail", "slot `%s` has a non-canonical binding: %s" %
                (slot, detail))
        elif kind == "unresolved":
            add("slot-binding-unresolved", "%s#%s" % (manifest_disp, slot), "fail",
                "slot `%s` binds to %r, which does not exist under the profile "
                "directory" % (slot, detail))
        elif kind == "outside-profile":
            add("slot-binding-outside-profile", "%s#%s" %
                (manifest_disp, slot), "fail",
                "slot `%s` resolves outside the selected profile directory: "
                "%s; a profile must be a self-contained configuration package"
                % (slot, detail))
        else:
            add("slot-binding-unrecognized", "%s#%s" % (manifest_disp, slot), "fail",
                "slot `%s` binding %r is not one canonical profile-relative "
                "file path" % (slot, binding))

    for name in sorted(bindings):
        if name not in slots:
            add("slot-not-in-interface", "%s#%s" % (manifest_disp, name), "candidate",
                "`%s` is bound in %s but is not a slot the interface defines; "
                "whether this extension binding is reasonable is a human call"
                % (name, SLOTS_SECTION))

    # ---- typed Profile dependency closure ----
    # The manifest-to-slot pass above proves the first hop.  Runtime-active
    # registry cells are linked separately so a copied/renamed Profile cannot
    # keep executing another Profile's config or citing its predicate owner.
    contract = profile_contract.load_profile_contract(
        root, manifest_path, sentinel=sentinel,
        profile_snapshot=profile_snapshot,
        root_input_snapshots=normative_snapshots)
    sentinel_targets = {
        "%s:%d" % (("%s/%s" % (profile_disp, rel))
                    if profile_disp != "." else rel, lineno)
        for rel, lineno in hits
    }
    for diagnostic in contract.diagnostics:
        # scan_sentinel above already owns the user-facing incompleteness
        # finding for known text suffixes.  The linker also scans every file
        # in the typed closure, including uncommon suffixes; surface only the
        # markers the broad scan did not already report.
        if diagnostic.check == "profile-contract-sentinel":
            if diagnostic.target not in sentinel_targets:
                add("unfilled-placeholder", diagnostic.target, "fail",
                    diagnostic.details + "; a Profile dependency with any "
                    "TODO left cannot authorize profile-load")
            continue
        add(diagnostic.check, diagnostic.target, "fail", diagnostic.details)

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
    resolved_overrides = tuple(sorted(registered))

    if profile_snapshot_before is not None:
        try:
            profile_snapshot_after = kblib.repository_tree_sha256(
                root, contract.profile_repo_dir or profile_disp)
        except (OSError, ValueError) as exc:
            add("profile-snapshot-invalid", profile_disp, "fail",
                "cannot re-bind the selected Profile directory snapshot: %s" %
                exc)
        else:
            if profile_snapshot_after != profile_snapshot_before:
                add("profile-snapshot-changed-during-check", profile_disp,
                    "fail", "selected Profile bytes changed while "
                    "profile-load was deriving its contract; rerun against "
                    "one stable snapshot")
            else:
                profile_snapshot_sha256 = profile_snapshot_after

    for relative, expected in sorted(normative_snapshots.items()):
        try:
            observed = kblib.repository_file_snapshot(
                root, relative, singly_linked=True)
        except (OSError, ValueError) as exc:
            add("profile-load-input-changed", relative, "fail",
                "canonical input became unreadable during profile-load: %s" %
                exc)
            continue
        if observed.sha256 != expected.sha256:
            add("profile-load-input-changed", relative, "fail",
                "canonical input bytes changed while profile-load was "
                "deriving its contract")

    fails = [r for r in receipts if r["result"] == "fail"]
    candidates = [r for r in receipts if r["result"] == "candidate"]
    if not fails and not candidates:
        add(GATE_CHECK, contract.manifest_repo_path, "pass",
            "profile_id=%s; %d/%d interface slot(s) bound and resolved; %d "
            "explicit override(s) registered; %d optional/conditional "
            "declaration(s) structurally consistent; %d typed dependency "
            "edge(s) authorized; no unfilled sentinel, placeholder profile "
            "id, unresolved binding, or cross-Profile reference remains"
            % (profile_id, bound_ok, len(slots), len(registered),
               declaration_count, len(contract.dependency_edges)))
        summary = receipts[-1]
        summary["selected_profile_manifest"] = contract.manifest_repo_path
        summary["profile_snapshot_sha256"] = profile_snapshot_sha256
        summary["profile_contract_fingerprint"] = contract.fingerprint
        summary["profile_load_inputs_sha256"] = profile_load_inputs_sha256

    # ---- human-readable summary ----
    say("check_profile: %s (profile_id=%s)"
          % (profile_disp, profile_id if profile_id else "<none>"))
    say("  interface=%s slots=%d bound_ok=%d explicit_overrides=%d "
          "files_scanned=%d files_skipped=%d"
          % (os.path.relpath(interface_path, root).replace(os.sep, "/"),
             len(slots), bound_ok, len(registered), files_read, files_skipped))
    say("  sentinel_hits(fail)=%d" % len(hits))
    for r in receipts:
        if r["result"] == "fail":
            say("  [FAIL %s] %s — %s" % (r["check"], r["target"], r["details"]))
        elif r["result"] == "candidate":
            say("  [CAND %s] %s — %s" % (r["check"], r["target"], r["details"]))
    if fails:
        say("  Conclusion: NOT LOADABLE — %d failure(s). This profile is "
              "incomplete; the composed standard must not be judged fully "
              "loaded." % len(fails))
    elif candidates:
        say("  Conclusion: REVIEW REQUIRED — %d candidate finding(s); no "
              "profile-load pass receipt was emitted." % len(candidates))
    else:
        say("  Conclusion: Profile load authorized; every interface slot and "
              "machine-active Profile dependency resolves inside the selected "
              "Profile. This checks authority and structure, not whether the "
              "answers are good.")

    return finish()


def evaluate_profile_load(profile_dir, *, root, interface=None, defaults=None,
                          execution_defaults=None, receipt_identity=None):
    """Evaluate ``profile-load`` once and return its exact contract snapshot.

    This is the shared producer API for Terminal Proof, batch close, and other
    Gate consumers.  It executes the same code path as the CLI but never writes
    receipts.  ``receipt_identity=None`` deliberately disables Queue identity
    injection; callers evaluating a planned/candidate state may instead pass an
    explicit mapping whose values describe that state.
    """
    if receipt_identity is not None and not isinstance(receipt_identity, Mapping):
        raise TypeError("receipt_identity must be a mapping or None")

    argv = [os.fspath(profile_dir), "--root", os.fspath(root)]
    for option, value in (
            ("--interface", interface),
            ("--defaults", defaults),
            ("--execution-defaults", execution_defaults)):
        if value is not None:
            argv.extend((option, os.fspath(value)))

    captured = io.StringIO()
    evaluation = {}
    with contextlib.redirect_stdout(captured):
        exit_code = main(
            argv,
            _evaluation_out=evaluation,
            _receipt_identity=(
                {} if receipt_identity is None else dict(receipt_identity)
            ),
            _write_receipts=False,
        )
    receipts = evaluation.get("receipts", ())
    return ProfileLoadEvaluation(
        exit_code=exit_code,
        findings=tuple(
            receipt for receipt in receipts
            if receipt.get("result") != "pass"
        ),
        contract=evaluation.get("contract"),
        profile_id=evaluation.get("profile_id"),
        profile_snapshot_sha256=evaluation.get("profile_snapshot_sha256"),
        profile_contract_fingerprint=evaluation.get(
            "profile_contract_fingerprint"),
        execution_default_overrides=tuple(
            evaluation.get("execution_default_overrides", ())),
        profile_snapshot=evaluation.get("profile_snapshot"),
        profile_load_inputs_sha256=evaluation.get(
            "profile_load_inputs_sha256"),
        summary_receipt=evaluation.get("summary_receipt"),
        output=captured.getvalue(),
    )


if __name__ == "__main__":
    sys.exit(main())
