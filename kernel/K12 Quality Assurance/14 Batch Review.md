## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]].
- Next: [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]].

## Batch Review

Under concurrent execution, a batch's body may link only to already-merged content or pages within the batch's own manifest; links to pages in an in-flight batch are deferred until both batches have merged: the author records the missing link in the batch's delta under `open_gaps_added` (type: link), to be absorbed by a maintenance run within budget; link placement follows [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|K12/01]] (Related is not the only place a reference appears).

Gate merge rules (for tier determination see [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|K00/07]] Effort Tiering):

- Note-level acceptance for S/M-tier pages is folded into Batch Review; no separate note gate is opened.
- S-tier pages are reviewed by sampling: by default sample `max(2, 20%)` of the batch's S-tier pages (check all if fewer than 2); when sampling finds problems, expand the scope per [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].
- M-tier pages pass, page by page within the batch gate, the canonical [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#M-tier Gate Checklist|M-tier Gate Checklist]] as surfaced by the kernel Single Note Authoring Card.
- L-tier pages keep an independent note gate, executed in full per [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|K12/01]], and are not folded into this section.

The batch close checklist has two groups: **in-batch items** are completed by the batch itself before it enters `merge-ready` (may run in parallel with other batches); **global items** are verified by the integrator during serial merge. The serial zone performs only deterministic actions and global verification, not in-batch manual review.

In-batch items (merge-ready preconditions):

- All Required pages in the batch contract have reached the target `authoring_status`.
- Canonical ownership, Sources, metadata, body wiki links, and navigation are synchronized.
- Required expression migrations registered by the `Expression Layer Entry` are complete or have an explicit disposition and pass R05; any supplemental profile gate is also closed.
- Automated checks (`--scope` level), manual content review, and the applicable rendering level are complete.
- An AuditPlan has been generated from changed objects, acceptance predicates, and dependency changes; still-valid historical evidence has an explicit `reused_receipt_id`, and new checks produce dimension-specific AuditReceipts.
- The delta has been written out; no unverified modifications are left to the next batch.

Global items (verified by the integrator during serial merge):

- Guidance reconciliation per [[kernel/K12 Quality Assurance/04 Guidance and Source Review|K12/04]] (incremental).
- The direct / dependency invalidations affected by the current batch are closed, `unresolved_invalidations = 0`.
- The delta is applied via `Tools/apply_delta.py`, and the Coverage Ledger and Progress Ledger are updated in sync.

When Batch Review does not pass, the batch MUST NOT be closed; gaps return to the execution phase, the batch stays unaccepted, and it MUST NOT be marked closed in order to start the next topic.
