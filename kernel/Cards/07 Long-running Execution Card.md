---
type: runtime-card
card_id: kernel-07
read_set: kernel/Read Sets/07 Long-running Execution Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/07 Long-running Execution Read Set.md
  - kernel/00 Standards Control/09 Default Constraints Snapshot.md
  - kernel/00 Standards Control/10 Batch Execution Checklist.md
  - kernel/02 Build Execution/01 Contract Time and Task State.md
  - kernel/02 Build Execution/02 Mid-task Guidance and Amendment.md
  - kernel/02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - kernel/02 Build Execution/05 Batch Execution.md
  - kernel/02 Build Execution/08 Progress Ledger.md
  - kernel/02 Build Execution/06 Existing Changes Migration and Resume.md
  - kernel/02 Build Execution/07 Completion and Handoff.md
  - kernel/12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/12 Quality Assurance/14 Batch Review.md
  - kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/12 Quality Assurance/10 Standards Version Adoption.md
  - kernel/12 Quality Assurance/06 Completion Gate and Reporting.md
source_hash: 75c83b79b662
---
# Long-running Execution Card

> Compiled kernel guidance. Do not hand-edit. Always combine this Card with the Card for the actual content being changed.

## Use When

Run a multi-batch task, sustain checkpoints, resume after interruption, maintain a Coverage Ledger, or approach a Terminal Proof. Load [[kernel/Cards/01 Core Bootstrap Card|Core Bootstrap]] and the content Card.

## Before Start

- [ ] Freeze objective, scope, exclusions, ownership, Standards version, selected profile, Card IDs, Read Sets, and time semantics in the Task Contract.
- [ ] Reconcile Coverage and Progress Ledgers with the file system, Required Queue, batch state, merge queue, and user modifications.
- [ ] Define batch manifests, tier-derived caps, concurrency admission, write partitions, merge order, and acceptance conditions.
- [ ] Load the Audit Receipt Register and classify evidence as reusable, invalidated, overdue, or missing.
- [ ] State the next checkpoint and exact recovery action; a vague “continue improving” is not resumable state.

## During

Each batch follows the fixed loop: version self-check → incremental Guidance reconciliation → select next Required work → resolve type/owner/target → close prerequisites → collect sources → author the batch → integrate links/metadata/sources → build one AuditPlan and complete in-batch QA → write the delta and enter `merge-ready` → integrator serially applies the delta, runs global checks, updates Ledgers, and closes the batch.

- Concurrent batches have disjoint manifests and merged prerequisites; only the integrator writes shared control state and hub pages.
- Treat meaningful user changes to objective, scope, acceptance, priority, or content judgment as Guidance: classify, disposition, record, switch safely, and verify closure.
- Reuse a receipt only when its predicate remains compatible, fingerprints match, and no relevant invalidation exists.
- A Standards delta triggers the registered adoption procedure before the batch continues.
- Pause or block with a complete checkpoint; resume from the machine-readable Ledgers and verify the contract before returning to active.

## Gate

- [ ] Every batch passes its in-batch review before `merge-ready` and its global checks during serial merge.
- [ ] The merge queue has no unapplied delta for a batch reported closed.
- [ ] Guidance counters, Required gaps, unverified batches, and unresolved invalidations stay explicit.
- [ ] Ledger, receipt, source, link, rendering, and watermark state are updated at the layer that owns them.
- [ ] A completion candidate loads [[kernel/Cards/08 Audit and Completion Card|Audit and Completion]]; elapsed time or exhausted context never substitutes for it.

## Read Back When

Read RS 07 and the canonical owner for full Guidance dispositions, concurrent-write boundaries, receipt fingerprints, invalidation propagation, Standards adoption, checkpoint recovery, or Terminal Proof fields.
