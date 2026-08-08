---
type: runtime-card
route_id: R12
read_set: kernel/Read Sets/R12 Targeted and Specialized Audit Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R12 Targeted and Specialized Audit Read Set.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
  - kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map.md
  - kernel/K12 Quality Assurance/02 Rendering Verification.md
  - kernel/K12 Quality Assurance/04 Guidance and Source Review.md
  - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
  - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
  - kernel/K02 Knowledge Work Construction/05 Global Map Contract.md
  - kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract.md
  - kernel/K02 Knowledge Work Construction/07 Gap Register Contract.md
source_hash: '30b3cd331ed1'
---
# R12 Targeted and Specialized Audit Card

> Compiled kernel guidance. This Card audits a bounded affected scope or one declared specialized invariant; it cannot produce Terminal Proof.

## Use When

Run an independent targeted review of changed, invalidated, overdue, or sampled objects, or a specialized cross-batch audit. Load [[kernel/Cards/R01 Core Bootstrap Card|R01 Core Bootstrap]] and the Card relevant to the finding. Use R08, not R12 alone, for whole-task completion.

## Before Start

- [ ] Declare the acceptance predicate, audit object, receipt dimension, verifier, and canonical acceptance owner.
- [ ] Partition scope into changed, directly invalidated, dependency-invalidated, overdue, bounded sampling, and reusable evidence; or declare exactly one specialized cross-batch invariant.
- [ ] When Corpus Planning is configured, use only its explicit map downstream, capability-owner/gap, and gap-link relations as inputs to the initial affected set; verify that set against the changed predicate.
- [ ] Confirm which receipts remain reusable by predicate and fingerprint, and which are invalidated or missing.
- [ ] Load the affected task route and every applicable profile audit, scan, or supplemental gate.

## During

- Run complete deterministic invariants only where the owning gate requires them; semantic review stays within changed, invalidated, overdue, or sampled scope.
- A suspected systemic problem expands first to a bounded sample. Only recurrence invalidates the whole affected family and creates a repair batch.
- After a fix, re-run only invalidated dimensions and their necessary global invariants.
- Source, expression, migration, and rendering findings follow their owning routes; visual evidence requires an objective exception trigger and unresolved question.
- A new semantic-gap candidate or planning-relation change is written back through R13 after the finding is recorded; the audit receipt and planning record do not replace one another.
- Do not silently rewrite an audited object while continuing to rely on its old receipt.

## Gate

- [ ] Required checks ran against the declared scope and emitted or superseded dimension-specific receipts.
- [ ] Reuse and invalidation decisions are reconciled.
- [ ] Systemic expansion, if triggered, remained bounded and its affected family is explicit.
- [ ] Unresolved failures became explicit repair items.
- [ ] The result makes no task-completion or Terminal-Proof claim.

## Read Back When

Read [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|R12 Read Set]] for receipt compatibility, dependency invalidation, specialized audit boundaries, or systemic expansion. A whole-task completion candidate additionally loads R08.
