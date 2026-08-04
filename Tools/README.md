# Tools: Machine-readable State Layer and Deterministic Checks

This directory contains the machine-readable schemas and deterministic tools
shipped with Cambium. All scripts use only the Python 3 standard library, and
all supported YAML parsing goes through the restricted-subset parser in
`kblib.py`.

## Ownership boundary

| Layer | Owns | Does not own |
|---|---|---|
| `kernel/` | Cross-domain rules, gates, routes, and vocabulary semantics | Instance choices or executable implementations |
| Selected profile | Domain choices; registered scan identity, scope, matcher configuration, candidate predicate, and judgment binding | Kernel defaults or Cambium-shipped executable code |
| `Tools/` | Deterministic execution, safe parsing/traversal, generated-artifact compilation, receipts, and exit semantics | Canonical policy prose or final content judgment |
| Generated artifacts | A reproducible projection of their declared inputs | Independent rules, profile selection, or authority |

No tool modifies canonical standards prose. The only standards-tree writer is
`stamp_cards.py`, which updates compiled Markdown under `kernel/Cards`;
`--check` is strictly read-only. Persistent executable checks shipped by
Cambium belong here even when a selected profile supplies their parameters.

The core distribution tools are `check_links`, `check_vocab`, `check_moc`,
`check_proof`, `apply_delta`, `compose_vocab`, `check_profile`,
`check_residual_content`, `stamp_cards`, and `kblib`.
`check_freshness` and `duplicate_check` are maintenance-run tools.

## Tool inventory

| Script | Purpose | Typical invocation |
|---|---|---|
| `check_links.py` | Wiki link missing / ambiguous / heading verification (K09/03, K09/05); `--scope` accepts a directory or a single page; the effective scan set is checked after exclusions, and zero files fail for both scoped and whole-root runs; exact full-path links into excluded areas still resolve (`excluded_target`) | `python3 Tools/check_links.py . --receipts Tools/receipts/links.jsonl` |
| `check_vocab.py` | Frontmatter controlled-vocabulary check (K08 module; vocabulary from the composed `vocab.yaml`, which exists only once a profile has been selected and composed -- without it the check reports that and exits 1); `--scope` accepts a directory or a single page; the post-exclusion effective scan set must be nonempty; `--quota-p0` / `--quota-p1` cap P0/P1 shares, defaults 15/35 (kernel defaults; a profile or task contract may override); compiled kernel Cards are outside the knowledge-page schema | `python3 Tools/check_vocab.py . --scope kernel --exclude kernel/Cards --quota-p0 15 --quota-p1 35 --receipts Tools/receipts/vocab.jsonl` |
| `check_moc.py` | Standard Module MOC Module Index vs. actual H2 headings consistency candidates (K12/05; **candidates only**); recursively scans every non-hidden directory unless the caller explicitly supplies `--exclude`, and is fence-aware (fenced code blocks ignored); maintenance runs and governance | `python3 Tools/check_moc.py .` |
| `check_proof.py` | Terminal Proof consistency check (K12/15): field completeness; active K00/03, Progress Ledger, Standards-version, and profile agreement; selected profile loadability through `check_profile.py`; R01/R12/R08 presence; Rxx, profile-route, Card-path, actual-readback, and incremental-manual-scope path structure; zero conditions; reconciliation/QA/review results must read `passed`; evidence fields must not declare failure. With `--root`, every recorded path, including `incremental_manual_scope`, must be a repository-contained regular file and the Rxx/Card/kernel-Read-Set binding is checked against both canonical indexes; `--progress-ledger` is then required. Without `--root`, no registry agreement is claimed and the run is structural lint only. Optional Coverage Ledger cross-check. Verifies proof consistency, not the underlying content judgments | `python3 Tools/check_proof.py proof.yaml --root . --progress-ledger progress_ledger.yaml --ledger coverage_ledger.yaml` |
| `apply_delta.py` | Deterministic application of a coverage delta during the serial merge (K02/05 Concurrent Batches); reads official templates with quote-aware inline-comment handling, merges `gate_receipts` in block-list form, warns on non-core scalar keys, re-parses the merged output before writing and aborts if it no longer parses; atomic write with automatic backup; gap/watermark entries are printed as integrator todos | `python3 Tools/apply_delta.py ledger.yaml delta.yaml --apply` |
| `compose_vocab.py` | Persistent vocabulary compiler: composes `vocab.yaml` from the kernel base and the profile selected in K00/03 active state. The selected manifest declares `profile_id` and its one `Vocabulary Extensions` binding; `volatility_defaults` registers each domain once; the resolved extensions path supplies base-field extension ownership; profile-only controlled fields are added to the frontmatter list automatically. `--extensions` may repeat the bound active path but cannot select another profile; the output header is provenance only. `--check` requires both parsed values and deterministic provenance/rendering to match | `python3 Tools/compose_vocab.py --check` |
| `check_profile.py` | Filled-profile structural check: derives the slot list from `profiles/README.md`; verifies identity syntax and directory agreement, slot bindings, sparse execution overrides against their closed registry, and `Configured`/inactive table consistency; rejects leftover `TODO(profile)` markers and reserved IDs. It checks structure, never answer quality, and is not run against `_template` itself | `python3 Tools/check_profile.py profiles/<profile-id> --receipts Tools/receipts/profile.jsonl` |
| `check_residual_content.py` | Generic K12/09 item 6 residual-content scanner. The selected profile owns every accepted/excluded content root and every literal frontmatter/heading matcher; only VCS metadata directories named `.git`, `.hg`, or `.svn` are always outside traversal. The tool owns safe traversal, fence-aware matching, a hard ≤55-second evidence-production budget, zero-file and missing-accepted-root failure, receipts, and `0/1/2` exit semantics; missing excluded roots are allowed. The caller must still satisfy the kernel's ≤60-second whole-command contract. `--scan-id` binds every receipt to the stable registry ID; receipts from a successfully loaded config record its SHA-256 so configuration changes invalidate old evidence. Findings are candidates only. Tool contract owner: K12/09 item 6; scan-definition owner: selected profile `Registered Scan Registry` | `python3 Tools/check_residual_content.py . --scan-id <stable-scan-id> --config profiles/<profile-id>/scan-configs/<scan>.yaml --time-limit 55 --receipts Tools/receipts/residual.jsonl` |
| `stamp_cards.py` | Kernel route and Runtime Card verification (K00/03 Write-back Checklist): checks the shared `kernel-runtime-routes` registry identity, exact R01-R12 coverage across both indexes and the on-disk Read Set/Card pairs, filename prefixes, source boundaries, `source_hash`, and that every `compiled_from` equals K00/03 active `standards_version`; defaults to `kernel/Cards`; missing, empty, incomplete, or malformed layers fail closed; `--check` is read-only; `--set-version` must equal the active version and stamps every Card including the Index | `python3 Tools/stamp_cards.py . --check` |
| `check_freshness.py` | Freshness check: computes review_by from volatility and last_verified (fallback: last_reviewed, then file modification time per K08/05, flagged pending first verification); `--defaults` accepts a flat mapping or `Tools/vocab.yaml` / a profile's `vocabulary-extensions.yaml` (their `volatility_defaults`); an all-skip run reports NOTHING CHECKED as a candidate, not a pass | `python3 Tools/check_freshness.py . --as-of 2026-07-21 --defaults profiles/<your-profile-id>/vocabulary-extensions.yaml --exclude Cards --receipts Tools/receipts/fresh.jsonl` |
| `duplicate_check.py` | Cross-file duplicate paragraph candidate detection; full vault by default; `--exclude` is repeatable and defaults to the single component `legacy`, the conventional name for a frozen-snapshot area that a vault need not have; compiled Cards and profile skeletons should be excluded from corpus-duplication review; supports `--receipts` and exits 2 when candidates exist | `python3 Tools/duplicate_check.py . --exclude _template --exclude Cards --receipts Tools/receipts/dup.jsonl` |
| `kblib.py` | Shared library and sole restricted-YAML parser owner. Duplicate mapping keys, multiple documents, unsupported constructs, and invalid indentation fail closed; it also provides Markdown and receipt helpers. Receipt output creates its requested parent directory and IDs include a per-invocation random token; not invoked directly | imported by the scripts above |

## Kernel module and route identity

`Kxx` and `Rxx` are separate namespaces. `Kxx` names a normative Standards
module; `Rxx` names an execution route. A route may compile several modules,
and no numeric correspondence between a route and its source modules is
implied.

Kernel routes are the continuous closed set R01-R12. The Read Set Index has
`type: route-index`, the Card Index has `type: card-index`, and both declare
`registry_id: kernel-runtime-routes` plus a `route_registry`. An index is not a
route and therefore declares neither `route_id` nor the retired `card_id`.
Every concrete Read Set declares `type: read-set` and one `route_id`; its
Runtime Card declares `type: runtime-card`, the same `route_id`, and the Read
Set path. R05 is a normal required member of the sequence, not an optional
profile gap.

Legacy `card_id` / `card_registry` fields and duplicate identity keys are
structural failures, including inside registry entries. The scan includes
case-variant Markdown suffixes and Markdown symlinks so route files cannot be
hidden from the four-way comparison by naming or link indirection.

`stamp_cards.py` compares four representations before it considers hashes:
the Read Set Index registry, the Read Set files on disk, the Card Index
registry, and the Runtime Card files on disk. All four must have the same twelve
route IDs and the same route-to-Read-Set bindings, and each concrete filename
must start with its `route_id`. A structural mismatch exits 1; a structurally
valid but stale Card layer exits 2 in `--check` mode; only exact agreement and
current hashes and agreement with K00/03 active `standards_version` exits 0.
Uniform Cards carrying an older version are still stale. Its successful
summary reports routes, Read Sets, Runtime Cards, indexes, and stale artifacts
separately.

## Canonical full-tree configuration

The full-tree link check for this repository is `python3 Tools/check_links.py
.`, with no exclusions: every file in the published tree is active and is
audited. `--exclude` remains available for a vault that carries an unaudited
area -- byte-verbatim frozen snapshots are the usual case -- and explicit
full-path links from active files into such an area still resolve, counted
separately as `excluded_target`.

The full-tree duplicate check is `python3 Tools/duplicate_check.py . --exclude
_template --exclude Cards`. `profiles/_template/` deliberately repeats form
labels and unfilled sentinels, while `kernel/Cards/` deliberately compresses
kernel source rules. Both therefore create expected textual similarity and are
outside a knowledge-corpus duplication review. Excluding `_template` does not
weaken the check for real profiles -- a profile copied from the template lives
under its own directory name and is scanned normally. Excluding `Cards` does
not skip the canonical rule text, which remains under the rest of `kernel/`.

## Invocation split

- **Batch close** = the Batch-close Closed List (owner: K12/09; a seven-item
  closed list, including full-vault `check_links`, `check_vocab`, and the
  selected profile's registered residual-content verifier).
- **Note close** = `check_links.py` / `check_vocab.py` with `--scope` set to
  the page itself (self-check; no receipts produced). Both tools fail on an
  empty scan set, so a mistyped page path cannot pass silently.
- **Maintenance run** = `check_freshness.py` (once at the start of the run)
  plus `duplicate_check.py` (full vault or `--scope`; candidates go into the
  candidates pool). Neither is invoked at batch or single-page level.
- **Governance** = `stamp_cards.py . --check`, `check_moc.py`, and
  `check_profile.py` against each filled profile a deployment selects. The
  published `_template` is a form, not a runnable profile.
  `compose_vocab.py --check` joins that list in a vault that has composed a
  vocabulary. This repository ships no composed `vocab.yaml`, so here the
  command reports that no profile is selected and exits 1; see Generated
  artifacts below.
- **Profile bring-up** = copy `profiles/_template/`, fill the copy, then run
  `check_profile.py` against that filled profile before loading it. The form
  itself is not a runtime target. Profile bring-up is not part of batch or note
  close because a profile is authored once and then loaded, not edited per
  batch. Setup is currently manual and file-based: `check_profile.py` validates
  structure and bindings but does not ask questions, generate domain choices,
  author a profile, approve it, or select it.

Shared conventions:

- Human-readable summaries go to stdout; machine-readable receipts are
  appended as JSONL via `--receipts PATH`.
- Exit codes: `0` = clean success; `1` = failure or unreliable evidence;
  `2` = reliable but non-clean outcome as defined by that tool. Receipt-based
  candidate checks use 2 for one or more candidates; `stamp_cards.py` uses it
  for stale artifacts, and `compose_vocab.py` uses it for a check mismatch.
- `check_residual_content.py` requires the profile's stable `--scan-id` and a
  profile-owned `--config`. Every emitted receipt includes that `scan_id` and
  the exact config-byte `config_fingerprint`; an unreadable or invalid config
  records a null fingerprint and exits 1.
- A scan registered by a profile is run only by a vault that loads that
  profile. Content matches may only produce review candidates; the final
  verdict belongs to scoped human/model review. Invalid configuration,
  incomplete scope, unsafe paths, read errors, or execution failure still
  return 1 because the scan did not produce reliable evidence.

## Receipts flow (K12/07 Audit Evidence Reuse and Invalidation)

```text
script run with --receipts creates the requested parent directory and produces JSONL receipts
  (receipt_id: audit-<tool>-<timestamp>-<run-token>-<seq>)
 -> receipts enter the Audit Receipt Register / Batch Contract; the Coverage
    Ledger's pages[].gate_receipts records only the latest valid receipt_id
 -> before batch close, generate one AuditPlan (schemas/audit_plan.template.yaml):
    freeze the snapshot, diff changed_objects, resolve direct/dependency invalidation
 -> old receipts passing the Reuse Gate go into reused_receipts (a reuse reason
    is mandatory); receipts affected by changes go into invalidated_receipts;
    new results supersede old receipts
 -> the Terminal Audit runs the Batch-close Closed List against the final frozen
    snapshot (K12/09); the result-set reference goes into the Terminal Proof's
    full_deterministic_results; unresolved_invalidations must be 0
```

The random run token prevents same-second invocations from reusing an ID.
Previously issued receipt IDs remain immutable identifiers and are not renamed
when the generator format changes. Their evidence-reuse validity may still be
revoked by the normal invalidation rules.

Script receipts are the lightweight layer (fields in
`schemas/receipt.template.jsonl`); on entering the Register, the AuditPlan
layer completes the full AuditReceipt fields per K12/07 (scope /
acceptance_predicate / fingerprints), with the script receipt_id serving as
evidence_ref. Tool-specific optional fields may bind the receipt more tightly
to its invocation contract; the residual scanner uses `scan_id` and
`config_fingerprint` so a registry or config change cannot reuse stale scan
evidence silently.

## schemas/ templates (the template is the schema doc)

- `coverage_ledger.template.yaml` -- Coverage Ledger (owner: K02/03)
- `progress_ledger.template.yaml` -- Progress Ledger (owner: K02/08; consumes
  the Task Contract and version/state rules defined by K02/01 and K02/02)
- `receipt.template.jsonl` -- script-level receipt (concept owner: K12/07),
  including the optional `scan_id` and `config_fingerprint` extension fields
  used by the residual scanner
- `coverage_delta.template.yaml` -- state increment of a concurrent batch
  (owner: K02/05 Concurrent Batches; applied by the integrator during the
  serial merge; includes the `watermark_advance` pass-through field)
- `watermark.template.yaml` -- external scan watermark (owner: K06/07
  Environmental Scanning and Watermark; consumed by the K06/03 intake
  pipeline; the instance lives at Tools/state/watermark.yaml and is advanced
  by maintenance batches)
- `audit_plan.template.yaml` -- AuditPlan (owner: K12/07 Incremental Audit Planning)
- `terminal_proof.template.yaml` -- machine-readable Terminal Proof projection;
  its 32 fields copy K12/15 field by field, and `check_proof.py` reads that
  projection while K12/15 remains the normative field-list owner
- `execution_defaults.template.yaml` -- the canonical machine-readable
  membership registry of which kernel execution defaults a profile may
  override and which constants it may not. Each entry points to the kernel
  module that owns the item's meaning and value; `check_profile.py` consumes
  this registry directly
- `residual_scan_config.template.yaml` -- machine-parameter form for
  `check_residual_content.py`; a selected profile owns its filled copy while
  its Registered Scan Registry remains the owner of scan identity, invocation,
  candidate semantics, and Judgment Item binding

## Restricted YAML subset

All `.yaml` state files may only use what `kblib.parse_yaml_subset` accepts:

- `key: value` scalars: strings (optionally quoted), integers, floats,
  booleans, null, the inline empty list `[]`, and simple inline lists
  `[a, b]`;
- `- item` lists indented under `key:`; list items may be a one-level flat
  map;
- two-level indented nested maps (the parser is recursive, but the standards
  convention uses two levels only);
- `#` comments (a `#` inside quotes is not a comment).

Not supported: duplicate mapping keys, anchors/aliases, block scalars (`|`
`>`), flow maps `{}`, tags, multi-document streams, tab indentation.
Duplicate keys at the same mapping level and all unsupported declarations fail
closed; the parser never applies last-value-wins semantics.

## Generated artifacts

`vocab.yaml` is a **generated artifact**, produced by `compose_vocab.py` from
`kernel/K08 Metadata and Status/vocabulary-base.yaml` plus the
`vocabulary-extensions.yaml` of the profile selected by K00/03 active state.
The artifact header records compilation provenance and the sha256 of both
inputs; it never selects the active profile. The tool carries no default
profile of its own. Every run reads K00/03; an argument-free run derives the
extensions path from the selected manifest, and an explicit `--extensions`
must name that same bound file.

The composed contract has one declaration source for each identity.
`profile_id` and the slot binding are declared only in `profile.md`; kernel
base identity and composition policy come only from the base input; a
kernel-field `extension_owner` is derived from the bound extensions-file path.
Legacy duplicate declarations are rejected rather than silently treated as a
second source.

**This repository ships no composed `vocab.yaml`.** Committing one would write
instance-specific compiled values and provenance into the generic release,
even though its K00/03 active state intentionally selects no profile. What is
published here is a kernel base and an interface, not an adopter artifact.
Until a profile is selected and composed,
`compose_vocab.py --check` exits 1 and reports the selectable direct-child
profiles it can find. `check_vocab.py` exits 1 and points at the same step.
Both report the expected
not-yet-configured state of a repository with no selected profile; neither is
a defect in the blank form.

Compose the artifact once, against your own profile:

```text
python3 Tools/compose_vocab.py
```

This command succeeds only after K00/03 selects that profile. After that,
`compose_vocab.py` with no arguments recomposes from the active state, and
`compose_vocab.py --check` verifies that the artifact still matches the
currently selected profile rather than merely agreeing with its old header.

`stamp_cards.py` pre-renders and round-trips every frontmatter block before it
writes. An ordinary write error rolls back earlier writes in that invocation;
a hard process or device interruption is not a filesystem transaction, so the
next `--check` must still be used to detect and restamp any interrupted layer.

Runtime Cards differ from the composed vocabulary in one distribution detail:
they ship with `kernel/` because every task needs routing before a profile can
contribute domain values. They are still compiled artifacts. The normative
route list is the Read Set Index's `kernel-runtime-routes` registry; the Card
Index mirrors it, and each Read Set/Card pair shares one Rxx `route_id`.
Authoritative rule definitions live in each Card's `source_files`; after
revising an owner standard, regenerate and stamp every affected Card, never
edit only the Card, and never cite a Card as standards text when adjudicating a
conflict. A profile may add a supplemental route, but it cannot replace or
disable the kernel Card layer.
