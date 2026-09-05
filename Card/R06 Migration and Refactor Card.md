---
type: card
generation_mode: curated
route_id: R06
read_set_id: R06
read_set: Read Set/R06 Migration and Refactor Read Set.md
source_files:
  - Read Set/R06 Migration and Refactor Read Set.md
  - kernel/K02 Knowledge Work Construction/10 Existing Changes and Migration Safety.md
  - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
  - kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
source_hash: '72eb770fcb0f'
reviewed_source_hash: '72eb770fcb0f'
reviewed_card_hash: '70f79fde556d'
---
# R06 Migration and Refactor Card

## Purpose

Move, rename, split, merge, or restructure governed content without losing ownership, references, evidence, or recoverability.

## Actions

- Freeze the admitted before-image, affected closure, target ownership, and rollback boundary.
- Preserve unrelated existing changes and route every changed canonical object to its sole owner.
- When the batch enters `open`, materialize its immutable AuditPlan.
- Before `merge-ready`, satisfy the complete pre-merge closure through the registered producers.
- After Delta application, satisfy every post-delta-close obligation against one identical after-image before invoking the batch-close Gate.
- Read back the resulting state and verify the old and new paths or owners have the intended disposition.

## Stop or escalate

- Stop on an unbounded affected closure, concurrent conflict, ambiguous owner, or non-recoverable write plan.
- Escalate a migration that changes Standards, Profile policy, or admitted scope.

## Read-back hook

Resolve `R06:affected-boundary` when relationships, expression, governance, planning, long-running execution, admission, or audit boundaries are touched.
