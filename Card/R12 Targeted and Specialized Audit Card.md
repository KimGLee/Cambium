---
type: card
generation_mode: curated
route_id: R12
read_set_id: R12
read_set: Read Set/R12 Targeted and Specialized Audit Read Set.md
source_files:
  - Read Set/R12 Targeted and Specialized Audit Read Set.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
  - kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map.md
source_hash: '6bb4957048a9'
reviewed_source_hash: '6bb4957048a9'
reviewed_card_hash: '3f88f08af343'
---
# R12 Targeted and Specialized Audit Card

## Purpose

Audit one declared affected scope or specialized invariant without expanding it silently or claiming whole-task completion.

## Actions

- Confirm the audit object, predicate, dimensions, affected boundary, and evidence eligible for reuse.
- Resolve only the route and conditional owners implicated by that boundary.
- Re-run invalidated dimensions and the necessary global invariants; record unresolved failures as repair work.
- Preserve the audit verdict and current evidence under their canonical owners.

## Stop or escalate

- Stop on an undefined predicate, unbounded expansion, stale evidence, or a verdict outside the admitted audit authority.
- Expand a local finding only through a bounded sample; on recurrence, invalidate the affected family and create repair work.

## Read-back hook

Resolve `R12:audit-scope` for the actual source, rendering, planning, expression, migration, completion, or planning-write-back dimension.
