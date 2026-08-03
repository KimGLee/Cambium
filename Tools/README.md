# Tools: Machine-readable State Layer and Deterministic Checks

This directory is the machine-readable state layer and the deterministic check
script layer of Standards v2.3. All scripts use only the python3 standard
library; YAML parsing goes through the restricted-subset parser in `kblib.py`.
No tool modifies canonical standards prose. In write mode, `stamp_cards.py`
updates only the compiled `.md` artifacts under `kernel/Cards`; `--check` is
strictly read-only. The standards prose owns every vocabulary and rule body.

Layering: check_links/check_vocab/check_moc/check_proof/apply_delta/compose_vocab/check_profile/stamp_cards/kblib
are kernel tooling; check_freshness/duplicate_check are maintenance tooling.
A profile may register scans of its own through its `Registered Scans`
registry; those scripts belong to that profile, not to this directory.

## Tool inventory

| Script | Purpose | Typical invocation |
|---|---|---|
| `check_links.py` | Wiki link missing / ambiguous / heading verification (09/03, 09/05); `--scope` accepts a directory or a single page (an empty scan set fails); `--exclude` keeps files out of scanning and basename disambiguation, while exact full-path links into excluded areas still resolve (`excluded_target`) | `python3 Tools/check_links.py . --receipts Tools/receipts/links.jsonl` |
| `check_vocab.py` | Frontmatter controlled-vocabulary check (08 domain; vocabulary from the composed `vocab.yaml`, which exists only once a profile has been selected and composed -- without it the check reports that and exits 1); `--scope` accepts a directory or a single page (an empty scan set fails); `--quota-p0` / `--quota-p1` cap P0/P1 shares, defaults 15/35 (kernel defaults; a profile or task contract may override); compiled kernel Cards are outside the knowledge-page schema | `python3 Tools/check_vocab.py . --scope kernel --exclude kernel/Cards --quota-p0 15 --quota-p1 35 --receipts Tools/receipts/vocab.jsonl` |
| `check_moc.py` | Domain MOC Module Index vs. actual H2 headings consistency candidates (12/05; **candidates only**); recursively scans for Module Index sections and is fence-aware (fenced code blocks ignored); maintenance runs and governance | `python3 Tools/check_moc.py .` |
| `check_proof.py` | Terminal Proof consistency check (12/06): field completeness, zero conditions, reconciliation/QA/review results must read `passed`, evidence fields must not declare failure; `--root` additionally requires path-valued fields to resolve; optional Coverage Ledger cross-check. Verifies the proof's consistency, not the work itself | `python3 Tools/check_proof.py proof.yaml --root . --ledger coverage_ledger.yaml` |
| `apply_delta.py` | Deterministic application of a coverage delta during the serial merge (02/05 Concurrent Batches); merges `gate_receipts` in block-list form, warns on non-core scalar keys, re-parses the merged output before writing and aborts if it no longer parses; atomic write with automatic backup; gap/watermark entries are printed as integrator todos | `python3 Tools/apply_delta.py ledger.yaml delta.yaml --apply` |
| `compose_vocab.py` | Persistent vocabulary compiler: composes `vocab.yaml` from the kernel base and the selected profile's extensions. There is no default profile: `--extensions` names one, and when the flag is omitted the path is read back from the existing `--output` header, so an argument-free run recomposes whichever profile the committed artifact was built from, and a run with no artifact to read from fails and lists the profiles it can find. `--check` recomputes and compares at the value level, ignoring the header comments | `python3 Tools/compose_vocab.py --check` |
| `check_profile.py` | Profile manifest completeness and unfilled-template check: derives the slot list from `profiles/README.md`, verifies every slot is bound and resolves, verifies each overridable execution default is registered and that no constitutional constant is, and **fails while the profile is still an unfilled `profiles/_template/` copy** (three independent conditions: a remaining `TODO(profile)` marker, a reserved placeholder `profile_id`, a surviving `Template Usage` section). Checks structure, never answer quality | `python3 Tools/check_profile.py profiles/<profile-id> --receipts Tools/receipts/profile.jsonl` |
| `stamp_cards.py` | Kernel Runtime Card structure, Read Set coverage, Card Index membership, source boundary, source_hash, and uniform-version verification (00/03 Write-back Checklist); defaults to `kernel/Cards`; missing, empty, incomplete, or malformed Card layers fail closed; `--check` is read-only; `--set-version` stamps every Card including the Index | `python3 Tools/stamp_cards.py . --check` |
| `check_freshness.py` | Freshness check: computes review_by from volatility and last_verified (fallback: last_reviewed, then file modification time per 08/05, flagged pending first verification); `--defaults` accepts a flat mapping or `Tools/vocab.yaml` / a profile's `vocabulary-extensions.yaml` (their `volatility_defaults`); an all-skip run reports NOTHING CHECKED as a candidate, not a pass | `python3 Tools/check_freshness.py . --as-of 2026-07-21 --defaults profiles/<your-profile-id>/vocabulary-extensions.yaml --exclude Cards --receipts Tools/receipts/fresh.jsonl` |
| `duplicate_check.py` | Cross-file duplicate paragraph candidate detection; full vault by default; `--exclude` is repeatable and defaults to the single component `legacy`, the conventional name for a frozen-snapshot area that a vault need not have; compiled Cards and profile skeletons should be excluded from corpus-duplication review; supports `--receipts` and exits 2 when candidates exist | `python3 Tools/duplicate_check.py . --exclude _template --exclude Cards --receipts Tools/receipts/dup.jsonl` |
| `kblib.py` | Shared library (restricted YAML subset parser, Markdown helpers, receipt helpers); not invoked directly | imported by all scripts above |

## Canonical full-tree configuration

The full-tree link check for this repository is `python3 Tools/check_links.py
.`, with no exclusions: every file in the published tree is active and is
audited. `--exclude` remains available for a vault that carries an unaudited
area -- byte-verbatim frozen snapshots are the usual case -- and explicit
full-path links from active files into such an area still resolve, counted
separately as `excluded_target`.

The full-tree duplicate check is `python3 Tools/duplicate_check.py . --exclude
_template --exclude Cards`. `profiles/_template/` repeats scaffolding and TODO
instructions across slot files, while `kernel/Cards/` deliberately compresses
kernel source rules. Both therefore create expected textual similarity and are
outside a knowledge-corpus duplication review. Excluding `_template` does not
weaken the check for real profiles -- a profile copied from the template lives
under its own directory name and is scanned normally. Excluding `Cards` does
not skip the canonical rule text, which remains under the rest of `kernel/`.

## Invocation split

- **Batch close** = the Batch-close Closed List (owner: 12/07; a seven-item
  closed list, including full-vault `check_links` and `check_vocab`).
- **Note close** = `check_links.py` / `check_vocab.py` with `--scope` set to
  the page itself (self-check; no receipts produced). Both tools fail on an
  empty scan set, so a mistyped page path cannot pass silently.
- **Maintenance run** = `check_freshness.py` (once at the start of the run)
  plus `duplicate_check.py` (full vault or `--scope`; candidates go into the
  candidates pool). Neither is invoked at batch or single-page level.
- **Governance** = `stamp_cards.py . --check`, `check_moc.py`, and
  `check_profile.py` against each profile the repository ships.
  `compose_vocab.py --check` joins that list in a vault that has composed a
  vocabulary. This repository ships no composed `vocab.yaml`, so here the
  command reports that no profile is selected and exits 1; see Generated
  artifacts below.
- **Profile bring-up** = `check_profile.py` against a profile freshly copied
  from `profiles/_template/`. It is expected to fail at first and to keep
  failing until the copy is filled in; that failure is the tool's purpose, not
  a defect in the copy. It is not part of any batch or note close, because a
  profile is authored once and then loaded, not edited per batch.

Shared conventions:

- Human-readable summaries go to stdout; machine-readable receipts are
  appended as JSONL via `--receipts PATH`.
- Exit codes: `0` = all pass; `1` = at least one fail; `2` = no fail but at
  least one candidate.
- A scan registered by a profile is run only by a vault that loads that
  profile, and may only produce review candidates: per 10/05 Acceptance And
  Audit the final verdict belongs to human/model review, so such a scan never
  returns 1.

## Receipts flow (12/07 Audit Evidence Reuse and Invalidation)

```text
script run with --receipts produces JSONL receipts (receipt_id: audit-<tool>-<timestamp>-<seq>)
 -> receipts enter the Audit Receipt Register / Batch Contract; the Coverage
    Ledger's pages[].gate_receipts records only the latest valid receipt_id
 -> before batch close, generate one AuditPlan (schemas/audit_plan.template.yaml):
    freeze the snapshot, diff changed_objects, resolve direct/dependency invalidation
 -> old receipts passing the Reuse Gate go into reused_receipts (a reuse reason
    is mandatory); receipts affected by changes go into invalidated_receipts;
    new results supersede old receipts
 -> the Terminal Audit runs the Batch-close Closed List against the final frozen
    snapshot (12/07); the result-set reference goes into the Terminal Proof's
    full_deterministic_results; unresolved_invalidations must be 0
```

Script receipts are the lightweight layer (fields in
`schemas/receipt.template.jsonl`); on entering the Register, the AuditPlan
layer completes the full AuditReceipt fields per 12/07 (scope /
acceptance_predicate / fingerprints), with the script receipt_id serving as
evidence_ref.

## schemas/ templates (the template is the schema doc)

- `coverage_ledger.template.yaml` -- Coverage Ledger (owner: 02/03)
- `progress_ledger.template.yaml` -- Progress Ledger (owner: 02/05, 02/01, 02/02)
- `receipt.template.jsonl` -- script-level receipt (concept owner: 12/07)
- `coverage_delta.template.yaml` -- state increment of a concurrent batch
  (owner: 02/05 Concurrent Batches; applied by the integrator during the
  serial merge; includes the `watermark_advance` pass-through field)
- `watermark.template.yaml` -- external scan watermark (owner: 06/03 Stage 1
  incremental scanning; the instance lives at Tools/state/watermark.yaml and
  is advanced by maintenance batches)
- `audit_plan.template.yaml` -- AuditPlan (owner: 12/07 Incremental Audit Planning)
- `terminal_proof.template.yaml` -- Terminal Proof, the 28 fields copied field
  by field from 12/06; also the single source of truth for
  `check_proof.py`'s required field list
- `execution_defaults.template.yaml` -- the machine-readable registry of which
  kernel execution defaults a profile may override and which constants it may
  not, each entry naming the kernel module that owns the value; a hand-kept
  copy of the Execution Default Overrides Contract in `profiles/README.md`
  (that file remains the normative owner), and the list `check_profile.py`
  checks a profile's overrides table against

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

Not supported: anchors/aliases, block scalars (`|` `>`), flow maps `{}`,
tags, multi-document streams, tab indentation.

## Generated artifacts

`vocab.yaml` is a **generated artifact**, produced by `compose_vocab.py` from
`kernel/08 Metadata and Status/vocabulary-base.yaml` plus the
`vocabulary-extensions.yaml` of one selected profile. Which profile that is,
is recorded in the artifact's own header, together with the sha256 of both
inputs. The tool carries no default profile of its own; an argument-free run
reads the profile back out of that header, which is how a recompose can name
no profile on the command line and still be unambiguous.

**This repository ships no composed `vocab.yaml`.** Committing one would write
a selected profile into the artifact header, and that profile would become the
vocabulary of every clone -- the outcome `compose_vocab.py` refuses to produce
when asked for a default. What is published here is a kernel base and an
interface, not a selection. Until a profile is selected and composed,
`compose_vocab.py --check` exits 1 and lists the profiles it can find, and
`check_vocab.py` exits 1 and points at the same step. Both are the
not-yet-configured signal, not a defect: it is the same signal
`check_profile.py profiles/_template` gives for an unfilled template.

Compose the artifact once, against your own profile:

```text
python3 Tools/compose_vocab.py --extensions profiles/<your-profile-id>/vocabulary-extensions.yaml
```

After that, `compose_vocab.py` with no arguments recomposes from the header,
and `compose_vocab.py --check` verifies the artifact still matches its inputs.

Runtime Cards differ from the composed vocabulary in one distribution detail:
they ship with `kernel/` because every task needs routing before a profile can
contribute domain values. They are still compiled artifacts. The authoritative
definitions live in their `source_files`; after revising an owner standard,
regenerate and stamp every affected Card, never edit only the Card, and never
cite a Card as standards text when adjudicating a conflict. A profile may add a
supplemental route, but it cannot replace or disable the kernel Card layer.
