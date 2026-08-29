## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]].
- Next: [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]].

## Batch Review

Under concurrent execution, a batch's body may link only to already-merged content or pages within the batch's own manifest; links to pages in an in-flight batch are deferred until both batches have merged: the author records the missing link in the batch's delta under `open_gaps_added` (type: link), to be absorbed by a maintenance run within budget; link placement follows [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|K12/01]] (Related is not the only place a reference appears).

Gate merge rules (for tier determination see [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|K00/07]] Effort Tiering):

- Note-level acceptance for S/M-tier pages is folded into Batch Review; no separate note gate is opened, and an M-tier page MUST NOT produce an independent `substantive-review-record`.
- For `n` S-tier pages, check all when `n < 2`; otherwise sample `max(2, ceil(n × 20 / 100))`. The Tool deterministically selects and freezes the set. Findings expand scope under [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]].
- M-tier pages pass the canonical [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#M-tier Gate Checklist|M-tier checklist]] page by page. Its sole atomic projection is [`batch-review-obligation-registry.yaml`](batch-review-obligation-registry.yaml); every atom stays in the AuditPlan, and conditional `not-applicable` requires a reason.
- L-tier pages keep an independent note gate, executed in full per [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|K12/01]], and are not folded into this section.

The registry also owns the M/S producer-evidence contract. A `consumes` atom has an exact selector or `hold`; a Tool cannot substitute an arbitrary pass. Sampled-S evidence remains dimensionless and is never fabricated as an `AuditReceipt`.

**In-batch items** precede `merge-ready`; one current `batch-review` Gate receipt binds the batch, task, Delta evidence, complete applicable AuditPlan closure, and any Profile-registered judgments. Missing, extra, stale, or mis-bound evidence fails. **Global items** are verified during serial merge without repeating semantic review.

In-batch items (merge-ready preconditions):

- All Required pages in the batch contract have reached the target `authoring_status`.
- Canonical ownership, Sources, metadata, body wiki links, and navigation are synchronized.
- Required expression migrations registered by the `Expression Layer Entry` are complete or have an explicit disposition and pass R05; any supplemental profile gate is also closed.
- Changed-scope automated checks, manual content review, and the applicable
  rendering level are complete.
- The [`AuditPlan`](audit-plan-contract.yaml) is complete; reuse is explicit, and each obligation retains its planned evidence kind. Only dimension-specific obligations produce an [`AuditReceipt`](audit-receipt-contract.yaml).
- Page frontmatter projections of every page the batch touched agree with the
  post-delta Coverage owner state, per [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|K08/07]]. A substantive change advances evidence-bound `last_content_modified` and invalidates the old review; `last_reviewed` returns only from review evidence for the current semantic fingerprint. Any `last_verified` change cites the separate verification evidence that earned it.
- Each Profile-registered Batch Review Requirement has one current per-target judgment bound to its `profile-extension` plan row and fingerprints; close cannot reconstruct or accept a free-standing judgment.
- The delta has been written out; no unverified modifications are left to the next batch.

Global items (verified by the integrator during serial merge):

- Guidance reconciliation per [[kernel/K12 Quality Assurance/04 Guidance and Source Review|K12/04]] (incremental).
- The direct / dependency invalidations affected by the current batch are closed, `unresolved_invalidations = 0`.
- The exact delta is applied through the canonical Coverage-delta transaction;
  then the current full snapshot and Coverage/Queue relation pass their global
  checks. A current `required-queue-consistency` receipt binds the Queue
  revisions and fingerprint consumed by close.
- The current batch-close producer freezes every manifest page through the
  canonical no-follow target-snapshot API and emits one distinct
  `page_review_acceptance` receipt per page. Each child binds the semantic
  content fingerprint computed from the same authorized Core + typed Profile
  projection rules, its own `checked_at` UTC date as `reviewed_on`, reviewer
  attestation, and exact Profile/Metadata Execution Contract identities. The
  aggregator binds the unique sorted child-receipt set. Immediately before
  publication, all frozen page identities and exact bytes pass a final CAS;
  drift refuses the close rather than dating content nobody reviewed.

Only after the global items pass and the complete frozen AuditPlan closure has been consumed may the registered Queue transaction record `merge-ready -> closed`; the guarded close also derives the Coverage `next_batch` projection and updates the Progress Queue reference. Delta application and close are ordered, independently evidenced integrator writes, not one falsely atomic multi-object step. A failed merge records the failure and returns the item to `open`; a worker cannot write either transition.

When Batch Review does not pass, the batch MUST NOT be closed; gaps return to the execution phase, the batch stays unaccepted, and it MUST NOT be marked closed in order to start the next topic.
