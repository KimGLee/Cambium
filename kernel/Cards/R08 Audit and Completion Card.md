---
type: runtime-card
route_id: R08
read_set: kernel/Read Sets/R08 Audit and Completion Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R08 Audit and Completion Read Set.md
  - kernel/Read Sets/R12 Targeted and Specialized Audit Read Set.md
  - kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
  - kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
  - kernel/K12 Quality Assurance/15 Terminal Audit and Convergence.md
  - kernel/K12 Quality Assurance/16 Terminal Proof Contract.md
  - kernel/K00 Standards Control/17 Profile Dependency Closure.md
  - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
  - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
  - kernel/K13 Task Runtime and Execution Control/11 Completion Policy.md
  - kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings.md
  - kernel/K13 Task Runtime and Execution Control/13 Final Handoff.md
readback_sources: []
readback_policy: none
source_hash: '1eca9b5a131e'
compiled_source_hash: '1eca9b5a131e'
---
# R08 Audit and Completion Card

> Compiled kernel guidance. Do not hand-edit. A Card cannot turn structural success into a completion verdict.

## Use When

Load only after the whole task enters `completion-candidate`. This Card owns Completion Gate and Terminal Audit routing; page, batch, module, maintenance, and targeted-audit gates remain with their owning Cards. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]], the Cards relevant to the completion predicates, and [[kernel/Cards/R12 Targeted and Specialized Audit Card|R12 Targeted and Specialized Audit]] for the bounded review performed inside the Terminal Audit.

## Before Start

- [ ] Require `completion-candidate`, freeze content and the candidate snapshot, and record contract, scope, Queue path/structural revision/state revision/SHA-256, Standards version, `selected_profile_manifest`, its `profile-load` Profile snapshot and typed-contract fingerprints, Guidance cutoff, Cards, Read Sets, and read-back modules.
- [ ] Derive audit scope from changed, invalidated, overdue, invalidated-evidence, and bounded-sampling objects; do not indiscriminately redo valid evidence.
- [ ] Confirm all prerequisite gates have already run. Terminal Audit does not replace an omitted page, batch, module, source, or expression gate.

## During

Load receipts and invalidations → reconcile Guidance and Coverage → rerun one root-bound `profile-load` evaluation whose exact contract supplies the Profile extension dimensions and whose two fingerprints bind Terminal Proof → when configured, run `check_corpus_plan.py` and confirm the pass authority's capability decision → run `check_queue.py --require-complete` against the frozen Queue and require `remaining_required_work_units = 0` → run the Batch-close Closed List → use R12 for changed/invalidated/overdue/sampled and specialized-invariant review → verify source promotion and profile extension gates → review deterministic rendering and only triggered visual evidence → expand systemic findings → produce receipt reconciliation, Final Handoff, and Terminal Proof.

- Review correctness, depth, provenance, integration, maintainability, and applicable rendering, not only structure.
- Without a visual exception trigger, UI, screenshot, and recording evidence are not applicable.
- Minor findings are recorded; major findings are fixed and targetedly rechecked; a critical completion-predicate failure returns the task to active.
- Terminal Audit is capped at two rounds. Round 2 closes round 1 findings and opens no new review scope; exceeding the cap requires user decision.

## Completion Gate

- [ ] Guidance reconciliation has zero unclassified, accepted-unmapped, and implemented-unverified items.
- [ ] The current Queue completion receipt matches its path, structural/state revisions, and SHA-256; all Required work units are closed, with authorized cancellation history only.
- [ ] `required_authoring_gaps = 0`.
- [ ] When `Corpus Planning` is configured, its current structural/reconciliation check passes and the profile-declared pass authority has accepted the required capability outcomes.
- [ ] `unverified_batches = 0`, including no `merge-ready` unmerged batch.
- [ ] `unresolved_invalidations = 0`.
- [ ] All applicable page, module, source, expression, rendering, batch, and terminal gates pass.
- [ ] Terminal Proof binds the same successful `profile-load` evaluation used to derive Profile extension obligations; it never combines a contract from one Profile revision with fingerprints from another.
- [ ] In `completion-candidate`, rerun `check_queue.py --require-complete --receipts <proof-queue-receipt>` so the cited receipt binds the frozen Progress bytes. Final Handoff and machine-readable Terminal Proof are complete, and `python3 Tools/check_proof.py <proof.yaml> --root <repository-root> --progress-ledger <progress-ledger> --ledger <coverage-ledger> --receipts <proof-receipt>` passes; `update_task.py --transition complete` consumes that Proof pass receipt. A run without `--root` is structural lint only and cannot support `complete`.
- [ ] Time contract is satisfied without using time, file count, or check count as proof of completion.

## Read Back When

Read R08 Read Set and the canonical owner for Terminal Proof semantics, task-state transition, prerequisite-gate reconciliation, or finding convergence. Targeted and specialized audit scope reads R12; a migration finding additionally reads R06.
