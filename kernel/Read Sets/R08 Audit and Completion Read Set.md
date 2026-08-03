---
type: read-set
route_id: R08
---

## Purpose

Used for reviewing content, closing a batch or module, and performing the Completion Gate, the Terminal Audit, and the final report.

## Start

First read:

- [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]]
- The Read Sets relevant to the finding under review.
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]]
- [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
- [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]]
- [[kernel/K02 Build Execution/07 Completion and Handoff|Completion and Handoff]]
- The selected profile's `Language Contract`.

## Triggered

- Diagrams, tables, formulas, images, embeds, or a specific display problem: read [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]]. Audit Level 0 / Level 1 deterministic evidence first; audit UI, screenshot, or recording evidence only when a recorded visual exception trigger exists, judged against [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]].
- Guidance or source promotion: read [[kernel/K12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]]. Expression-layer content: combine [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]] and the artifact's supplemental profile audit or readiness gates.
- Directory migration: read the Gate modules of [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]].

## Completion Rule

Passing structural checks MUST NOT lead to skipping correctness, depth, provenance, integration, or the applicable deterministic rendering. The audit first derives its scope from AuditReceipts, fingerprints, and invalidation events: the final graph-related checks run per the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]], and expensive manual review covers changed, invalidated, overdue, and sampled objects. The Terminal Audit may audit only a completion candidate that already satisfies all applicable gates; without a visual exception trigger, the absence of UI, screenshot, or recording evidence MUST NOT be judged a failure.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
