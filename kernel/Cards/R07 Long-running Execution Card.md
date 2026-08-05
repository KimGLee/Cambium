---
type: runtime-card
route_id: R07
read_set: kernel/Read Sets/R07 Long-running Execution Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R07 Long-running Execution Read Set.md
  - kernel/K00 Standards Control/09 Default Constraints Snapshot.md
  - kernel/K00 Standards Control/10 Batch Execution Checklist.md
  - kernel/K02 Build Execution/01 Contract Time and Task State.md
  - kernel/K02 Build Execution/02 Mid-task Guidance and Amendment.md
  - kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - kernel/K02 Build Execution/05 Batch Execution.md
  - kernel/K02 Build Execution/08 Progress Ledger.md
  - kernel/K02 Build Execution/09 Required Queue.md
  - kernel/K02 Build Execution/06 Existing Changes Migration and Resume.md
  - kernel/K02 Build Execution/07 Completion and Handoff.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/K12 Quality Assurance/10 Standards Version Adoption.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
source_hash: '726b1558e1ca'
---
# R07 Long-running Execution Card

> Compiled kernel guidance. Do not hand-edit. Always combine this Card with the Card for the actual content being changed.

## Use When

Run a multi-batch task, sustain checkpoints, resume after interruption, maintain a Coverage Ledger, or approach a Terminal Proof. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]] and the content Card. If the work also meets the large-scale creation, move, or deletion predicate, pass R11 before execution.

## Before Start

- [ ] If `.cambium/` exists, run `python3 Tools/check_queue.py . --resume-status` before any state write; resume the recorded task instead of initializing a replacement.
- [ ] Freeze the long-run Task Contract: Standards version, exact `selected_profile_manifest`, time semantics, route IDs, Card paths, actual read-backs, completion semantics, and the Queue path/revisions/fingerprint.
- [ ] Reconcile `.cambium/` Coverage, Queue, and Progress with the file system and user modifications. Ready, open, and merge-ready lists are derived from the Queue, never edited in Progress as a second authority.
- [ ] Define batch manifests, tier-derived caps, concurrency admission, write partitions, merge order, and acceptance conditions.
- [ ] Load the Audit Receipt Register and classify evidence as reusable, invalidated, overdue, or missing.
- [ ] State the next checkpoint and exact recovery action; a vague “continue improving” is not resumable state.

## During

Each batch follows the fixed loop: version/Guidance self-check → `check_queue.py --require-ready` → integrator records `queued -> open` → execute the frozen manifest → build one AuditPlan, finish in-batch QA, and write the delta → integrator records `open -> merge-ready` → serially applies the delta and global gates → reconciles Coverage/Queue/Progress → records `merge-ready -> closed`.

- Concurrent batches have disjoint manifests and merged prerequisites; only the integrator writes shared control state and hub pages.
- After one canonical delta apply passes, perform checks and close that batch before any other Queue/Coverage write; the apply receipt opens a strict serial critical section.
- Treat meaningful user changes to objective, scope, acceptance, priority, or content judgment as Guidance: classify, disposition, record, switch safely, and verify closure.
- Reuse a receipt only when its predicate remains compatible, fingerprints match, and no relevant invalidation exists.
- A Standards delta triggers the registered adoption procedure before the batch continues.
- Pause or block with a complete checkpoint. Resume from the machine-readable state only after the Queue path, revisions, fingerprint, holds, unapplied deltas, and cross-state `check_queue.py` result are reconciled.

## Gate

- [ ] Every Queue transition is written by the integrator and passes its owning readiness, in-batch, or serial-merge gate.
- [ ] No batch reported `closed` has an unapplied delta; open and merge-ready work remains explicit in the Queue.
- [ ] Guidance counters, Required gaps, unverified batches, and unresolved invalidations stay explicit.
- [ ] Ledger, receipt, source, link, rendering, and watermark state are updated at the layer that owns them.
- [ ] A completion candidate loads [[kernel/Cards/R08 Audit and Completion Card|Audit and Completion]]; elapsed time or exhausted context never substitutes for it.

## Read Back When

Read R07 Read Set and the canonical owner for full Guidance dispositions, concurrent-write boundaries, receipt fingerprints, invalidation propagation, Standards adoption, checkpoint recovery, or Terminal Proof fields.
