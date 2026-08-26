---
type: card
generation_mode: curated
route_id: R08
read_set_id: R08
read_set: Read Set/R08 Audit and Completion Read Set.md
standards_version: '{{ standards_version }}'
source_files:
  - Read Set/R08 Audit and Completion Read Set.md
  - kernel/K12 Quality Assurance/15 Terminal Audit and Convergence.md
  - kernel/K12 Quality Assurance/16 Terminal Proof Contract.md
  - kernel/K13 Task Runtime and Execution Control/11 Completion Policy.md
source_hash: '3dfccc4842f5'
reviewed_source_hash: '3dfccc4842f5'
reviewed_card_hash: 'c16a90084b0d'
---
# R08 Audit and Completion Card

## Purpose

Evaluate an already requested completion candidate and produce the applicable
completion evidence without substituting a checklist for the final verdict.

## Actions

- Resolve the R08 completion Read Set only after the completion phase is entered.
- Reconcile current scope, Coverage, Queue, invalidations, reused evidence, and
  applicable Profile dimensions.
- Require `required-queue-completion` and `terminal-proof` for build completion,
  or the registered maintenance completion Gate for maintenance semantics.
- From the verified resulting state, prepare a bounded handoff that states the
  completed scope and current evidence/result, and separates unresolved,
  optional, deferred, and external-evidence backlog with re-entry conditions.

## Stop or escalate

- Stop while required work, invalidation, failed evidence, or unresolved
  completion semantics remains.
- Escalate only the unresolved semantic judgment; do not report completion.

## Read-back hook

Return to Read Set `R08` and the failing canonical owner for every disputed or
incomplete proof condition.
