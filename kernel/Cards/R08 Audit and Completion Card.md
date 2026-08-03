---
type: runtime-card
route_id: R08
read_set: kernel/Read Sets/R08 Audit and Completion Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/R08 Audit and Completion Read Set.md
  - kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
  - kernel/K12 Quality Assurance/15 Terminal Audit and Convergence.md
  - kernel/K02 Build Execution/07 Completion and Handoff.md
source_hash: bc5af8e051ec
---
# R08 Audit and Completion Card

> Compiled kernel guidance. Do not hand-edit. A Card cannot turn structural success into a completion verdict.

## Use When

Review a note, close a batch or module, or audit a completion candidate. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]] and the Cards/Read Sets relevant to the findings.

## Before Start

- [ ] Confirm which layer is being accepted: page, batch, module, maintenance run, or whole task.
- [ ] For Terminal Audit, require `completion-candidate`, freeze content and the candidate snapshot, and record contract, scope, queue, Standards version, Guidance cutoff, Cards, Read Sets, and read-back modules.
- [ ] Derive audit scope from changed, invalidated, overdue, legacy-evidence, and bounded-sampling objects; do not indiscriminately redo valid evidence.
- [ ] Confirm all prerequisite gates have already run. Terminal Audit does not replace an omitted page, batch, module, source, or expression gate.

## During

For Terminal Audit: load receipts and invalidations → reconcile Guidance → reconcile Coverage → confirm all batches closed and merge queue empty → run the Batch-close Closed List on the frozen snapshot → review changed/invalidated/overdue/sampled objects → verify source promotion and profile extension gates → review deterministic rendering and only triggered visual evidence → expand systemic findings → produce receipt reconciliation, Final Handoff, and Terminal Proof.

- Review correctness, depth, provenance, integration, maintainability, and applicable rendering, not only structure.
- Without a visual exception trigger, UI, screenshot, and recording evidence are not applicable.
- Minor findings are recorded; major findings are fixed and targetedly rechecked; a critical completion-predicate failure returns the task to active.
- Terminal Audit is capped at two rounds. Round 2 closes round 1 findings and opens no new review scope; exceeding the cap requires user decision.

## Completion Gate

- [ ] Guidance reconciliation has zero unclassified, accepted-unmapped, and implemented-unverified items.
- [ ] `required_authoring_gaps = 0`.
- [ ] `unverified_batches = 0`, including no `merge-ready` unmerged batch.
- [ ] `unresolved_invalidations = 0`.
- [ ] All applicable page, module, source, expression, rendering, batch, and terminal gates pass.
- [ ] Final Handoff and machine-readable Terminal Proof are complete, and the completion-gate invocation `python3 Tools/check_proof.py <proof.yaml> --root <repository-root>` passes. A run without `--root` is structural lint only and cannot support `complete`.
- [ ] Time contract is satisfied without using time, file count, or check count as proof of completion.

## Read Back When

Read R08 Read Set and the canonical owner for L-tier review, receipt reuse or invalidation, judgment dimensions, rendering levels, specialized audits, Terminal Proof semantics, or finding convergence. A migration finding additionally reads R06 Read Set.
