---
type: runtime-card
route_id: R10
read_set: kernel/Read Sets/R10 Maintenance Run Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R10 Maintenance Run Read Set.md
  - kernel/K00 Standards Control/02 Task Routing.md
  - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
  - kernel/K00 Standards Control/08 Maintenance Run Envelope.md
  - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
  - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
  - kernel/K08 Metadata and Status/05 Review Source and Migration Metadata.md
  - kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority.md
  - kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark.md
  - kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production.md
  - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
  - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
  - kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md
  - kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings.md
  - kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
readback_sources:
  - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
  - kernel/K12 Quality Assurance/11 Content-level Propagation.md
  - kernel/K12 Quality Assurance/12 Substantive Correctness Review.md
readback_policy: declared
source_hash: '1b513ada03a8'
compiled_source_hash: '1b513ada03a8'
---
# R10 Maintenance Run Card

> Compiled kernel guidance. Do not hand-edit. Maintenance completion is bounded by the declared run envelope, not by whole-corpus completion.

## Use When

Perform periodic freshness, re-verification, watermark, `needs_rereview`, or candidate-pool work. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]] and combine the content Card for every selected object.

## Before Start

- [ ] Confirm the activation Bundle contains R01, R10, and the exact frozen
  maintenance reading plan before selecting candidates.
- [ ] Inspect the repository root for `.cambium/state/` before any write. If it
  exists, run `python3 Tools/check_queue.py . --resume-status` and follow its
  exact `next_action`; never initialize a replacement or restart candidate age.
- [ ] If task state is absent, initialize it only for a persistent, resumable,
  or multi-batch run, preserving governance/history under `.cambium/`, with
  `completion_semantics: maintenance`. A bounded
  single-note run does not create an empty runtime namespace.
- [ ] Choose exactly one budget envelope: N pages, N batches, or N hours.
- [ ] Build the candidate manifest from the complete freshness candidate set
  ∪ watermark delta ∪ `needs_rereview` marks ∪ the registered candidates
  pool. Preserve every freshness `candidate` outcome; do not reduce the set
  back to overdue pages or drop an active page whose policy is unresolved.
- [ ] When persistent state applies, bind the manifest to the latest
  canonically consumed maintenance gate for the same Standards/Profile. `null`,
  an older gate, or a reused maintenance `run_id` cannot reset deferral age.
- [ ] Fuse duplicate object paths while retaining every contributing source;
  order once by priority, canonical path, then stable candidate ID; truncate to
  the envelope; record the exact selected/deferred partition, not only counts.
- [ ] Output deferred age distribution. Explicitly disposition items lingering more than 3 runs.
- [ ] For retirement of high-in-degree pages, count incoming-link retargeting against the page budget at `retargeted links ÷ 6`.
- [ ] Resolve batch boundaries, selected content Cards, profile scans, source routes, and tier-specific review before editing.
- [ ] For persistent multi-batch maintenance, consume R07's current Corpus Planning check and on-demand JSON projection; load R13 only if the run changes a map, capability, or gap handoff.

## During

- Adjudicate candidates caused by the current batch inside that batch; existing-object candidates enter the pool and do not become automatic gate failures.
- Reverify whether each selected object's priority, evidence, owner, content, links, and freshness still hold.
- Compute `review_by` in tool output, reports, and receipts only; do not persist the derived date onto pages, and record a real external validity boundary as `source_valid_until`, never as derived freshness (K08/07).
- Run source updates through `R04`; retire or merge only after canonical ownership and incoming links are reconciled.
- Use R13 only when maintenance changes a corpus-wide map entry, capability judgment, or semantic-gap handoff; page freshness alone does not rewrite corpus planning.
- For persistent work, move each selected batch through the Required Queue;
  workers write only their manifest, receipts, and delta, while the integrator
  owns Queue, Coverage, Progress, Ledger, and watermark writes.
- Update the Ledger and watermark at the owning checkpoint. The watermark's
  `last_run_id` identifies the enclosing maintenance run; `last_batch_id`
  identifies the Queue batch that performed the final advance. Stop only at a
  batch boundary.
- An item outside the envelope for 3 consecutive runs moves to log-only and re-enters only when a new scan hits it.

## Gate

- [ ] Every selected batch passes Batch Review and the Batch-close Closed List on the merged snapshot.
- [ ] Selected candidates have a final disposition; deferred items carry forward with age and re-entry state.
- [ ] Ledger, receipt, review date, and watermark state are advanced consistently.
- [ ] The declared manifest inside the budget envelope is closed.
- [ ] For persistent state, run `check_queue.py --require-maintenance-complete`
  with explicit budget-manifest, Ledger-advance, and watermark-advance receipt
  IDs. Require a nonempty Queue, zero remaining work, terminal selected batches,
  and the exact candidate partition.
- [ ] Consume that pass with `update_task.py --transition complete`. Never enter
  `completion-candidate` and never run `check_proof.py` for Maintenance
  completion. After interruption, reuse a prior pass only when `--resume-status`
  reports it current-compatible.
- [ ] Report bounded Maintenance completion. Do not require or claim a whole-corpus Terminal Proof for deferred work outside the envelope.

## Read Back When

Read the R10 Read Set and the canonical owner for freshness calculation, `needs_rereview` propagation, retirement/merge, L-tier substantive review, source intake, budget conversion, or candidate demotion/re-entry. Expression-artifact maintenance additionally reads R05 and the artifact's profile binding.
