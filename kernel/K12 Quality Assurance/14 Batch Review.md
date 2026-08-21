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

The batch close checklist has two groups: **in-batch items** are completed by the batch before it is eligible for `merge-ready` (may run in parallel with other batches); the integrator verifies that boundary, records one current `batch-review` Gate receipt, and writes the Queue transition. The receipt is a `manual-attestation` protocol `1.0.0` pass with `gate_id: batch-review`, `check: batch_gate`, the exact Batch ID as `target` and `batch_id`, the current Task ID, and `delta_page_receipt_ids` equal to the sorted unique receipt IDs carried by every Delta page. Those page receipts may remain valid historical evidence, but they do not authorize the lifecycle edge by themselves. The transition consumes the wrapper as its `evidence_receipt`; an invalidated wrapper or page receipt is rejected. When the selected Profile registers Batch Review Requirements, the wrapper additionally binds the frozen judgment set: `review_requirement_set_sha256` equal to the value the activation receipt froze at `queued -> open`, `judgment_receipt_ids` as the sorted unique current `profile_batch_judgment` receipts, and `judgment_record_set_sha256` over the exact actual `(target, judgment item, receipt)` records. `open -> merge-ready` recomputes the expected expansion from the authorized Profile and the frozen manifest and refuses the batch on one missing, extra, duplicated, drifted, mis-roled, or reused record; each judgment receipt binds the batch's current activation, the target's semantic content fingerprint, and the Profile contract fingerprint, so a reopened batch, a changed page, or a revised Profile invalidates the evidence rather than carrying it. A requirement-free Profile owes nothing and its wrapper keeps its exact prior shape; a batch activated before the review era replays under its own producer protocol and must not carry the fields. **Global items** are verified by the integrator during serial merge. The serial zone performs only deterministic actions and global verification, not in-batch manual review.

In-batch items (merge-ready preconditions):

- All Required pages in the batch contract have reached the target `authoring_status`.
- Canonical ownership, Sources, metadata, body wiki links, and navigation are synchronized.
- Required expression migrations registered by the `Expression Layer Entry` are complete or have an explicit disposition and pass R05; any supplemental profile gate is also closed.
- Automated checks (`--scope` level), manual content review, and the applicable rendering level are complete.
- An AuditPlan has been generated from changed objects, acceptance predicates, and dependency changes; still-valid historical evidence has an explicit `reused_receipt_id`, and new checks produce dimension-specific AuditReceipts.
- Page frontmatter projections of every page the batch touched agree with the
  post-delta Coverage owner state, per [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|K08/07]]. A substantive change advances evidence-bound `last_content_modified` and invalidates the old review; `last_reviewed` returns only from review evidence for the current semantic fingerprint. Any `last_verified` change cites the separate verification evidence that earned it.
- Every Batch Review Requirement the selected Profile registers has its per-target judgment recorded through `Tools/record_batch_judgment.py` — one current receipt per expected record, produced before this boundary, never reconstructed at close.
- The delta has been written out; no unverified modifications are left to the next batch.

Global items (verified by the integrator during serial merge):

- Guidance reconciliation per [[kernel/K12 Quality Assurance/04 Guidance and Source Review|K12/04]] (incremental).
- The direct / dependency invalidations affected by the current batch are closed, `unresolved_invalidations = 0`.
- The exact delta is applied through canonical `Tools/apply_delta.py --root`; then the current full snapshot and Coverage/Queue relation pass their global checks. A current `Tools/check_queue.py` consistency receipt binds the Queue revisions and fingerprint consumed by the close transition.
- The current batch-close producer freezes every manifest page through the
  canonical no-follow target-snapshot API and emits one distinct
  `page_review_acceptance` receipt per page. Each child binds the semantic
  content fingerprint computed from the same authorized Core + typed Profile
  projection rules, its own `checked_at` UTC date as `reviewed_on`, reviewer
  attestation, and exact Profile/Metadata Execution Contract identities. The
  aggregator binds the unique sorted child-receipt set. Immediately before
  publication, all frozen page identities and exact bytes pass a final CAS;
  drift refuses the close rather than dating content nobody reviewed.

Only after the global items pass may the integrator record `merge-ready -> closed` through `Tools/update_queue.py`; that guarded close also derives the Coverage `next_batch` projection and updates the Progress Queue reference. Delta application and close are ordered, independently evidenced integrator writes—not one falsely atomic multi-file step. A failed merge records the failure and returns the item to `open`; a worker cannot write either transition.

When Batch Review does not pass, the batch MUST NOT be closed; gaps return to the execution phase, the batch stays unaccepted, and it MUST NOT be marked closed in order to start the next topic.
