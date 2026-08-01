## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/02 Rendering Verification|Rendering Verification]].
- Next: [[kernel/12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].

## Module Review

Before a module is complete, check:

- Whether the Overview reflects the real module structure.
- Whether the coverage matrix still has unexplained P0 / P1 concepts.
- Whether the prerequisite chain is continuous.
- Whether the mainline dependencies and foundation preservation requirements declared by the selected profile's `Profile Scope` remain intact.
- Whether duplicate canonical notes exist.
- Whether orphan notes exist.
- Whether the profile artifact synchronization gates registered by the `Routing And Gate Registry` pass.
- Whether the Case Study can use the module's knowledge.
- Whether new external sources went through gap analysis rather than producing isolated pages by article title.
- Whether file depth is balanced; core topics MUST NOT be visibly thinner than peripheral topics.
- Standards modules MUST additionally confirm that the domain MOC matches the actual leaf files, that each original section has exactly one owner, and that Applicable Read Sets are navigable in both directions.

Module Review first consumes the valid AuditReceipts of closed batches, then reviews the owner, dependency, coverage, and navigation invariants that can only be judged across batches. Local mechanisms with no relevant change SHOULD NOT be re-reviewed page by page; when receipts are missing or invalidated, or sampling exposes a systemic problem, expand the scope per [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Coverage Reconciliation Review

Before a module or long task completes, the Coverage Ledger MUST be reconciled against the actual file system, the scope contract, and the competency matrix:

- Every in-scope file has exactly one inventory record.
- Every Required knowledge object not yet created still has an explicit record.
- Excluded directories are not counted as deliverables or accidentally modified.
- No P0 / P1 core, process-flow, system, or risk/control page is `unassessed`.
- Every Required item that has not reached its target state has an active or queued batch.
- `deferred` has a reason, a re-entry condition, and an owner; `excluded` has a scope basis.
- Sequence or progress checkboxes, file existence, resolvable wiki links, and `Related` references are not treated as authoring completion; for status separation see [[kernel/11 Expression Layer/06 Sequence and Progress Semantics|Sequence And Progress Semantics]].
- Core pages are not visibly thinner than newly created peripheral or frontier pages.
- Coverage Ledger summary counts match the automated scan counts.

Line counts and section counts can only trigger review candidates. An Atomic Term Note MAY deliberately stay concise; Core, Process, System, and Risk/Control pages MUST have their question coverage checked by note type.

## Batch Review

Under concurrent execution, a batch's body may link only to already-merged content or pages within the batch's own manifest; links to pages in an in-flight batch are deferred until both batches have merged: the author records the missing link in the batch's delta under `open_gaps_added` (type: link), to be absorbed by a maintenance run within budget; link placement follows [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]] (Related is not the only place a reference appears).

Gate merge rules (for tier determination see [[kernel/00 Standards Control/02 Task Routing and Pre-execution|00/02]] Effort Tiering):

- Note-level acceptance for S/M-tier pages is folded into Batch Review; no separate note gate is opened.
- S-tier pages are reviewed by sampling: by default sample `max(2, 20%)` of the batch's S-tier pages (check all if fewer than 2); when sampling finds problems, expand the scope per [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].
- M-tier pages pass, page by page within the batch gate, the corresponding Gate checklist provided by the `Runtime Card Provider`.
- L-tier pages keep an independent note gate, executed in full per [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]], and are not folded into this section.

The batch close checklist has two groups: **in-batch items** are completed by the batch itself before it enters `merge-ready` (may run in parallel with other batches); **global items** are verified by the integrator during serial merge. The serial zone performs only deterministic actions and global verification, not in-batch manual review.

In-batch items (merge-ready preconditions):

- All Required pages in the batch contract have reached the target `authoring_status`.
- Canonical ownership, Sources, metadata, body wiki links, and navigation are synchronized.
- Required migrations registered by the `Expression Layer Entry` are complete or have an explicit disposition; the concrete gate is bound by the `Routing And Gate Registry`.
- Automated checks (`--scope` level), manual content review, and the applicable rendering level are complete.
- An AuditPlan has been generated from changed objects, acceptance predicates, and dependency changes; still-valid historical evidence has an explicit `reused_receipt_id`, and new checks produce dimension-specific AuditReceipts.
- The delta has been written out; no unverified modifications are left to the next batch.

Global items (verified by the integrator during serial merge):

- Guidance reconciliation per [[kernel/12 Quality Assurance/04 Guidance and Source Review|12/04]] (incremental).
- The direct / dependency invalidations affected by the current batch are closed, `unresolved_invalidations = 0`.
- The delta is applied via `Tools/apply_delta.py`, and the Coverage Ledger and Progress Ledger are updated in sync.

When Batch Review does not pass, the batch MUST NOT be closed; gaps return to the execution phase, the batch stays unaccepted, and it MUST NOT be marked closed in order to start the next topic.
