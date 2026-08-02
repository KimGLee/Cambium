## Purpose

Used for reviewing content, closing a batch or module, and performing the Completion Gate, the Terminal Audit, and the final report.

## Start

First read:

- [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]
- The Read Sets relevant to the finding under review.
- [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]
- [[kernel/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]]
- [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]
- [[kernel/02 Build Execution/07 Completion and Handoff|Completion and Handoff]]
- The selected profile's `Language Contract`.

## Triggered

- Diagrams, tables, formulas, images, embeds, or a specific display problem: read [[kernel/12 Quality Assurance/02 Rendering Verification|Rendering Verification]]. Audit Level 0 / Level 1 deterministic evidence first; audit UI, screenshot, or recording evidence only when a recorded visual exception trigger exists.
- Guidance or source promotion: read [[kernel/12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]]; Expression Layer content: load the specialized-review role registered by the selected profile in the `Routing And Gate Registry`.
- Directory migration: read the Gate modules of [[kernel/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]].

## Completion Rule

Passing structural checks MUST NOT lead to skipping correctness, depth, provenance, integration, or the applicable deterministic rendering. The audit first derives its scope from AuditReceipts, fingerprints, and invalidation events: the final graph-related checks run per the Batch-close Closed List (12/07), and expensive manual review covers changed, invalidated, overdue, and sampled objects. The Terminal Audit may audit only a completion candidate that already satisfies all applicable gates; without a visual exception trigger, the absence of UI, screenshot, or recording evidence MUST NOT be judged a failure.

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[kernel/12 Quality Assurance Standard|Quality Assurance]]
