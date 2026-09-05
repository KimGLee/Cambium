---
type: card
generation_mode: curated
route_id: R12
read_set_id: R12
read_set: Read Set/R12 Targeted and Specialized Audit Read Set.md
source_files:
  - Read Set/R12 Targeted and Specialized Audit Read Set.md
  - kernel/K12 Quality Assurance/02 Rendering Verification.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
  - kernel/K12 Quality Assurance/12 Substantive Correctness Review.md
  - kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map.md
  - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
source_hash: '4445e0b2a2ec'
reviewed_source_hash: '4445e0b2a2ec'
reviewed_card_hash: '1def15842fac'
---
# R12 Targeted and Specialized Audit Card

## Purpose

Audit one declared affected scope or specialized invariant without expanding it silently or claiming whole-task completion.

## Actions

- Confirm the audit object, predicate, dimensions, affected boundary, and evidence eligible for reuse.
- After R12 and the audit scope are already selected, resolve only the conditional owners implicated by that boundary.
- Re-run only the due AuditPlan obligations or registered specialized-audit checks for invalidated dimensions and necessary global invariants. Preserve every planned evidence kind; complete only `audit-receipt` obligations into full AuditReceipts.
- Preserve the audit verdict and current evidence under their canonical owners.

## Stop or escalate

- Stop on an undefined predicate, a structured `contract-gap` / HOLD, unbounded expansion, stale evidence, or a verdict outside the admitted audit authority; a known selector without a valid typed Profile Rendering Contract is HOLD, not pass.
- Expand a local finding only through a bounded sample; on recurrence, invalidate the affected family and create repair work.

## Read-back hook

Resolve `R12:audit-scope` for the actual source, rendering, planning, expression, migration, completion, or planning-write-back dimension.
