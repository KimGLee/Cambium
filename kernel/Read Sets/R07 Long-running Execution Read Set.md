---
type: read-set
route_id: R07
---

## Purpose

Used for long tasks requiring multiple batches, sustained time constraints, checkpoints, resume, the Coverage Ledger, or the Terminal Proof.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]]
- [[kernel/K00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]]
- [[kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[kernel/K02 Build Execution/05 Batch Execution|Batch Execution]]
- [[kernel/K02 Build Execution/08 Progress Ledger|Progress Ledger]]
- [[kernel/K02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]]
- [[kernel/K02 Build Execution/07 Completion and Handoff|Completion and Handoff]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]

Also combine the authoring, source, `Expression Layer`, or migration Read Set matching the actual content type.

## Triggered

- Mid-task guidance, scope change, correction, or priority change received: read [[kernel/K02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]].
- User guidance also contains a technical hypothesis or source lead: read [[kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|User Guidance Hypotheses and Source Leads]].
- Closing a guidance amendment: read [[kernel/K12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].
- New source-driven batch: read [[kernel/K06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy|Evidence Maturity and Batch Policy]].
- Batch activation finds the current Standards version differs from the contract-frozen one: read [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]].

## Gate

Each batch uses [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]], and generates, reuses, or invalidates verification evidence per [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]; at serial merge the integrator runs [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]]; a task completion candidate MUST combine [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]].

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K02 Knowledge Base Build Execution Standard|Build Execution]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
