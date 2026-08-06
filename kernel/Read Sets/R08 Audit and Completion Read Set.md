---
type: read-set
route_id: R08
---

## Purpose

Used only by a task whose contract declares `completion_semantics: build`, after the whole task enters `completion-candidate`, to perform the Completion Gate, Terminal Audit, Terminal Proof, and final report. Page, batch, module, maintenance, and targeted-audit gates remain with their owning routes. A maintenance task MUST NOT combine R08, and `check_proof.py` rejects maintenance semantics.

## Start

First read:

- [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]]
- The Read Sets relevant to the finding under review.
- [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]] for the changed, invalidated, overdue, sampled, and specialized-invariant review scope used inside the Terminal Audit.
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]]
- [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]]
- [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|Cross-page and Control-plane Dimension Map]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
- [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]]
- [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]]
- [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings|Completion Gate Bindings]]
- [[kernel/K13 Task Runtime and Execution Control/13 Final Handoff|Final Handoff]]
- The selected profile's `Language Contract`.

## Triggered

- Guidance, source, expression, migration, rendering, and specialized findings follow the Triggered routes of R12 and the applicable task route. R08 does not duplicate those gate bodies.

## Completion Rule

Passing structural checks MUST NOT lead to skipping correctness, depth, provenance, integration, or the applicable deterministic rendering. The audit first derives its scope from AuditReceipts, fingerprints, and invalidation events: the final graph-related checks run per the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]], and expensive manual review covers changed, invalidated, overdue, and sampled objects. The Terminal Audit may audit only a completion candidate that already satisfies all applicable gates, including `check_queue.py --require-complete` against the frozen Queue and `remaining_required_work_units = 0`; without a visual exception trigger, the absence of UI, screenshot, or recording evidence MUST NOT be judged a failure.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
