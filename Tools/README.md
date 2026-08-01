# Tools: Machine-readable State Layer and Deterministic Checks

This directory is the machine-readable state layer and the deterministic check
script layer of Standards v2.3. All scripts use only the python3 standard
library; YAML parsing goes through the restricted-subset parser in `kblib.py`.
Nothing in this directory modifies any standards `.md` file; the standards
prose owns every vocabulary and field list.

Layering: check_links/check_vocab/check_moc/check_proof/apply_delta/compose_vocab/kblib
are kernel tooling; check_language is profile tooling (agent-atlas registered
scan); check_freshness/duplicate_check are maintenance tooling.

## Tool inventory

| Script | Purpose | Typical invocation |
|---|---|---|
| `check_links.py` | Wiki link missing / ambiguous / heading verification (09/03, 09/05); `--scope` accepts a directory or a single page (an empty scan set fails); `--exclude` keeps files out of scanning and basename disambiguation, while exact full-path links into excluded areas still resolve (`excluded_target`) | `python3 Tools/check_links.py . --exclude legacy --receipts Tools/receipts/links.jsonl` |
| `check_vocab.py` | Frontmatter controlled-vocabulary check (08 domain; vocabulary from `vocab.yaml`); `--scope` accepts a directory or a single page (an empty scan set fails); `--quota-p0` / `--quota-p1` cap P0/P1 shares, defaults 15/35 (kernel defaults; a profile or task contract may override) | `python3 Tools/check_vocab.py . --scope kernel --quota-p0 15 --quota-p1 35 --receipts Tools/receipts/vocab.jsonl` |
| `check_moc.py` | Domain MOC Module Index vs. actual H2 headings consistency candidates (12/05; **candidates only**); recursively scans for Module Index sections and is fence-aware (fenced code blocks ignored); maintenance runs and governance | `python3 Tools/check_moc.py . --exclude legacy` |
| `check_proof.py` | Terminal Proof consistency check (12/06): field completeness, zero conditions, reconciliation/QA/review results must read `passed`, evidence fields must not declare failure; `--root` additionally requires path-valued fields to resolve; optional Coverage Ledger cross-check. Verifies the proof's consistency, not the work itself | `python3 Tools/check_proof.py proof.yaml --root . --ledger coverage_ledger.yaml` |
| `apply_delta.py` | Deterministic application of a coverage delta during the serial merge (02/05 Concurrent Batches); merges `gate_receipts` in block-list form, warns on non-core scalar keys, re-parses the merged output before writing and aborts if it no longer parses; atomic write with automatic backup; gap/watermark entries are printed as integrator todos | `python3 Tools/apply_delta.py ledger.yaml delta.yaml --apply` |
| `compose_vocab.py` | Persistent vocabulary compiler: composes `vocab.yaml` from the kernel base and the selected profile's extensions; `--check` recomputes and compares | `python3 Tools/compose_vocab.py --check` |
| `stamp_cards.py` | Runtime Cards source_hash stamping and verification (00/03 Write-back Checklist); `--cards-dir` defaults to `Cards` and a missing directory exits 0; `--check` verifies only; `--set-version` stamps a uniform version incl. the Card Index | `python3 Tools/stamp_cards.py . --check` |
| `check_language.py` | Language-policy candidate detection for the agent-atlas profile (10/05; **candidates only**); exemptions come only from `--exempt` -- there is no built-in path exemption | `python3 Tools/check_language.py . --scope profiles --exempt kernel --receipts Tools/receipts/lang.jsonl` |
| `check_freshness.py` | Freshness check: computes review_by from volatility and last_verified (fallback: last_reviewed, then file modification time per 08/05, flagged pending first verification); `--defaults` accepts a flat mapping or `Tools/vocab.yaml` / a profile's `vocabulary-extensions.yaml` (their `volatility_defaults`); an all-skip run reports NOTHING CHECKED as a candidate, not a pass | `python3 Tools/check_freshness.py . --as-of 2026-07-21 --exclude legacy --defaults Tools/vocab.yaml --receipts Tools/receipts/fresh.jsonl` |
| `duplicate_check.py` | Cross-file duplicate paragraph candidate detection; full vault by default; `--exclude` defaults to `legacy`; supports `--receipts` and exits 2 when candidates exist | `python3 Tools/duplicate_check.py . --scope kernel --receipts Tools/receipts/dup.jsonl` |
| `kblib.py` | Shared library (restricted YAML subset parser, Markdown helpers, receipt helpers); not invoked directly | imported by all scripts above |

## Canonical full-tree configuration

The full-tree link check for this repository is `python3 Tools/check_links.py
. --exclude legacy`: frozen `legacy/` snapshots are byte-verbatim historical
artifacts whose contents are not audited (they may contain links that were
valid at snapshot time), while explicit full-path links into them from active
files still resolve. Running without `--exclude legacy` audits the snapshots
themselves and reports their historical dead links.

## Invocation split

- **Batch close** = the Batch-close Closed List (owner: 12/07; a seven-item
  closed list, including full-vault `check_links` and `check_vocab`).
- **Note close** = `check_links.py` / `check_vocab.py` with `--scope` set to
  the page itself (self-check; no receipts produced). Both tools fail on an
  empty scan set, so a mistyped page path cannot pass silently.
- **Maintenance run** = `check_freshness.py` (once at the start of the run)
  plus `duplicate_check.py` (full vault or `--scope`; candidates go into the
  candidates pool). Neither is invoked at batch or single-page level.
- **Governance** = `stamp_cards.py --check`, `check_moc.py`, and
  `compose_vocab.py --check`.

Shared conventions:

- Human-readable summaries go to stdout; machine-readable receipts are
  appended as JSONL via `--receipts PATH`.
- Exit codes: `0` = all pass; `1` = at least one fail; `2` = no fail but at
  least one candidate.
- `check_language.py` never returns 1: per 10/05 Acceptance And Audit,
  language signals may only produce review candidates, and the final verdict
  belongs to human/model review. It is registered as a scan of the
  agent-atlas profile; kernel-only vaults do not run it.

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
`kernel/08 Metadata and Status/vocabulary-base.yaml` plus
`profiles/agent-atlas/vocabulary-extensions.yaml` (the file header records
both input hashes). The same applies to interview cards and every other
machine-readable object derived from the standards: the authoritative
definitions live in the owner standard files. After revising an owner
standard, regenerate the artifact (`python3 Tools/compose_vocab.py`); never
edit only the artifact without the owner, and never cite an artifact as
standards text. `compose_vocab.py --check` (governance) verifies that the
committed artifact still matches its inputs.
