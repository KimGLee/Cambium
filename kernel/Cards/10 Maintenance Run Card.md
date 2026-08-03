---
type: runtime-card
card_id: kernel-10
read_set: kernel/Read Sets/10 Maintenance Run Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/10 Maintenance Run Read Set.md
  - kernel/00 Standards Control/08 Maintenance Run Envelope.md
  - kernel/00 Standards Control/06 Completion Precedence and Task Contract.md
  - kernel/08 Metadata and Status/05 Review Source and Migration Metadata.md
  - kernel/06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark.md
  - kernel/02 Build Execution/05 Batch Execution.md
  - kernel/12 Quality Assurance/14 Batch Review.md
  - kernel/12 Quality Assurance/09 Batch-close Closed List.md
source_hash: 7114909f72fd
---
# Maintenance Run Card

> Compiled kernel guidance. Do not hand-edit. Maintenance completion is bounded by the declared run envelope, not by whole-corpus completion.

## Use When

Perform periodic freshness, re-verification, watermark, `needs_rereview`, or candidate-pool work. Load [[kernel/Cards/01 Core Bootstrap Card|Core Bootstrap]] and combine the content Card for every selected object.

## Before Start

- [ ] Choose exactly one budget envelope: N pages, N batches, or N hours.
- [ ] Build the candidate manifest from overdue re-verification ∪ watermark delta ∪ `needs_rereview` marks ∪ the registered candidates pool.
- [ ] Sort by priority, truncate to the envelope, and record the remainder as deferred rather than as a hidden gap.
- [ ] Output deferred age distribution. Explicitly disposition items lingering beyond the kernel threshold.
- [ ] Resolve batch boundaries, selected content Cards, profile scans, source routes, and tier-specific review before editing.

## During

- Adjudicate candidates caused by the current batch inside that batch; existing-object candidates enter the pool and do not become automatic gate failures.
- Reverify whether each selected object's priority, evidence, owner, content, links, and freshness still hold.
- Run source updates through `kernel-04`; retire or merge only after canonical ownership and incoming links are reconciled.
- Update the Ledger and watermark at the owning checkpoint. Stop only at a batch boundary.
- An item repeatedly outside the envelope moves to log-only under the kernel rule and re-enters only when a new scan hits it.

## Gate

- [ ] Every selected batch passes Batch Review and the Batch-close Closed List on the merged snapshot.
- [ ] Selected candidates have a final disposition; deferred items carry forward with age and re-entry state.
- [ ] Ledger, receipt, review date, and watermark state are advanced consistently.
- [ ] The declared manifest inside the budget envelope is closed.
- [ ] Report bounded Maintenance completion. Do not require or claim a whole-corpus Terminal Proof for deferred work outside the envelope.

## Read Back When

Read RS 10 and the canonical owner for freshness calculation, `needs_rereview` propagation, retirement/merge, L-tier substantive review, source intake, profile expression work, budget conversion, or candidate demotion/re-entry.
