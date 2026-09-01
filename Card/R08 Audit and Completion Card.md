---
type: card
generation_mode: curated
route_id: R08
read_set_id: R08
read_set: Read Set/R08 Audit and Completion Read Set.md
source_files:
  - Read Set/R08 Audit and Completion Read Set.md
  - kernel/K12 Quality Assurance/02 Rendering Verification.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/15 Terminal Audit and Convergence.md
  - kernel/K12 Quality Assurance/16 Terminal Proof Contract.md
  - kernel/K13 Task Runtime and Execution Control/11 Completion Policy.md
source_hash: '54092c787a42'
reviewed_source_hash: '54092c787a42'
reviewed_card_hash: '9fd4b42419e2'
---
# R08 Audit and Completion Card

## Purpose

Evaluate an already requested build completion candidate and produce the applicable completion evidence without substituting a checklist for the final verdict.

## Actions

- Resolve the R08 completion Read Set only after a build task enters its completion boundary; maintenance completion does not use R08.
- Reconcile current scope, Coverage, Queue, invalidations, reused evidence, each registered native evidence kind, full AuditReceipts where required, and applicable Profile dimensions.
- Require the current K12/15–K12/16 Terminal Proof prerequisite set, including its registered Queue, Corpus Planning, Profile-load, and completion evidence, then require `terminal-proof`; return to those owners rather than maintaining a shorter local substitute.
- From the verified resulting state, prepare a bounded handoff that states the completed scope and current evidence/result, and separates unresolved, optional, deferred, and external-evidence backlog with re-entry conditions.

## Stop or escalate

- Stop while required work, invalidation, failed or missing evidence, a rendering `contract-gap` / HOLD, or unresolved completion semantics remains; `not-applicable` cannot substitute for a missing typed contract.
- Escalate only the unresolved semantic judgment; do not report completion.

## Read-back hook

Return to Read Set `R08` and the failing canonical owner for every disputed or incomplete proof condition.
