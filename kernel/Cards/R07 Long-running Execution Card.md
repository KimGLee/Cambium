---
type: runtime-card
route_id: R07
read_set: kernel/Read Sets/R07 Long-running Execution Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R07 Long-running Execution Read Set.md
  - kernel/K00 Standards Control/09 Default Constraints Snapshot.md
  - kernel/K00 Standards Control/10 Batch Execution Checklist.md
  - kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace.md
  - kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics.md
  - kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules.md
  - kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis.md
  - kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching.md
  - kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning.md
  - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
  - kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md
  - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
  - kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production.md
  - kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract.md
  - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
  - kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views.md
  - kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md
  - kernel/K13 Task Runtime and Execution Control/11 Completion Policy.md
  - kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings.md
  - kernel/K13 Task Runtime and Execution Control/13 Final Handoff.md
  - kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover.md
  - kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
  - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/K12 Quality Assurance/10 Standards Version Adoption.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
source_hash: '176b13774aea'
---
# R07 Long-running Execution Card

> Compiled kernel guidance. Do not hand-edit. Always combine this Card with the Card for the actual content being changed.

## Use When

Run a multi-batch task, sustain checkpoints, resume after interruption, maintain a Coverage Ledger, or approach a Terminal Proof. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]] and the content Card. If the work also meets the large-scale creation, move, or deletion predicate, pass R11 before execution.

## Before Start

- [ ] If `.cambium/` exists, run `python3 Tools/check_queue.py . --resume-status` before any state write; resume the recorded task instead of initializing a replacement.
- [ ] Freeze the long-run Task Contract: Standards version, exact `selected_profile_manifest`, time semantics, route IDs, Card paths, actual read-backs, completion semantics, and the Queue path/revisions/fingerprint.
- [ ] Reconcile `.cambium/` Coverage, Queue, and Progress with the file system and user modifications. Ready, open, and merge-ready lists are derived from the Queue, never edited in Progress as a second authority.
- [ ] For persistent multi-batch corpus work, require Corpus Planning `applicability.state: configured` and pass `check_corpus_plan.py`; use its on-demand `--json` projection for recovery and R13 for any planning edit.
- [ ] Define batch manifests, tier-derived caps, concurrency admission, write partitions, merge order, and acceptance conditions.
- [ ] Declare every batch simple with null/null or bind its complex Work Spec path/hash; read a complex spec after activation and never treat it as Queue state or proof.
- [ ] Load the Audit Receipt Register and classify evidence as reusable, invalidated, overdue, or missing.
- [ ] State the next checkpoint and exact recovery action; a vague “continue improving” is not resumable state.

## During

Each batch follows the fixed loop: version/Guidance self-check → `check_queue.py --require-ready` → integrator records `queued -> open` → execute the frozen manifest → build one AuditPlan, finish in-batch QA, and write the delta → integrator records `open -> merge-ready` → serially applies the delta and global gates → reconciles Coverage/Queue/Progress → records `merge-ready -> closed`.

- Concurrent batches have disjoint manifests and merged prerequisites; only the integrator writes shared control state and hub pages.
- In-batch QA is not satisfied by producing the close evidence set alone: each M-tier manifest page passes, page by page, the M-tier Gate Checklist surfaced by the kernel Single Note Authoring Card (K12/14 folds note-level acceptance into Batch Review), including the sources-role and page-contract items; the per-page conclusion is recorded in that page's attestation, not asserted once in the batch wrapper.
- After one canonical delta apply passes, perform checks and close that batch before any other Queue/Coverage write; the apply receipt opens a strict serial critical section.
- Treat meaningful user changes to objective, scope, acceptance, priority, or content judgment as Guidance: classify, disposition, record, switch safely, and verify closure.
- For a same-scope Queue replan, scope replan, or cancellation, prepare its exact proposal or plan and use `register_amendment.py` as the sole approved-row writer before `compile_queue.py` or `apply_amendment.py` consumes it. The pending registration receipt must remain current and bind live state; after verified write-back it proves history only and cannot authorize another action.
- Reuse a receipt only when its predicate remains compatible, fingerprints match, and no relevant invalidation exists.
- A Standards/Profile mismatch blocks normal work. First roll a stale `completion-candidate` back through K13/03, formally roll back affected `merge-ready` batches, and put affected `open` batches under `revalidation-required`. Then use only `adopt_standards.py`; it changes none of those states/holds. Commit consumes Queue consistency; deferred gates run only at named boundaries. Filter accumulated invalidated-evidence receipt IDs from current use, but retain producer-era evidence for historical verification. Never create a prose copy.
- Pause or block with a complete checkpoint. Resume from the machine-readable state only after the Queue path, revisions, fingerprint, holds, unapplied deltas, and cross-state `check_queue.py` result are reconciled.
- Resume also reconciles each Work Spec path/hash. A changed open-batch spec requires an explicit revalidation hold and Amendment/replan; merge-ready and terminal bindings are immutable.
- When `Corpus Planning` is configured, request the current `check_corpus_plan.py --json` projection to recover semantic orientation. Combine R13 before changing a map, capability judgment, gap, or promotion handoff; never persist that projection as another state owner.

## Gate

- [ ] Every Queue transition is written by the integrator and passes its owning readiness, in-batch, or serial-merge gate.
- [ ] No batch reported `closed` has an unapplied delta; open and merge-ready work remains explicit in the Queue.
- [ ] Guidance counters, Required gaps, unverified batches, and unresolved invalidations stay explicit.
- [ ] Ledger, receipt, source, link, rendering, and watermark state are updated at the layer that owns them.
- [ ] Coverage reconciliation does not read a sequence position, checkbox, file existence, resolvable link, or `Related` reference as authoring completion.
- [ ] A completion candidate loads [[kernel/Cards/R08 Audit and Completion Card|Audit and Completion]]; elapsed time or exhausted context never substitutes for it.
- [ ] Each durable checkpoint refreshes the configured corpus-planning check; resume revalidates current inputs and requests a fresh JSON projection when orientation is needed.

## Read Back When

Read R07 Read Set and the canonical owner for full Guidance dispositions, concurrent-write boundaries, receipt fingerprints, invalidation propagation, adoption execution/recovery, checkpoint recovery, or Terminal Proof fields. Read the Gate Receipt Payload Contract before recording or accepting a `manual-attestation` receipt, and the Resume Next Action Vocabulary for the exact token a resume scan reported.
