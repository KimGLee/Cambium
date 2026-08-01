# Golden Scenarios

This document freezes the behavioral determinations of the pre-split Cambium v2.3 baseline; the baseline commit is `060433eb45856891b26d67d36770ebf72c960971`. The post-split regression read surface is `kernel + profiles/agent-atlas`; the routing, tiering, gate, and batch-close results of the 12 scenarios below must remain identical. This document records determination facts only and does not copy rule text.

## Shared Decision Vocabulary

- `Core` means every scenario first loads Card 01 / RS 01, then layers on the scenario-specific Card, Read Set, and triggered modules.
- S/M/L is a page-level acceptance tier, not a task state: P2 pages, terminology stubs, placeholder pages, and link-aggregation pages are S — script checks only, no independent note gate, and batch-close sampling at `max(2, 20%)` (full inspection when fewer than 2 pages); P1 regular pages are M, with the Card gate folded into the batch gate; P0 pages, core concept, process-flow, system, and risk-control mainline pages, System Deep Dives, and Interview Card sets are L, with full review and an independent note gate; in case of dispute, tier upward.
- `Batch internal gate` means: Required pages have reached the target state; ownership, Sources, metadata, body links, and navigation are synchronized; Interview migration has a final disposition; the automated, manual, and applicable rendering checks for the changed scope are complete; the AuditPlan and per-dimension receipts have been generated; the delta has been written out; and the batch enters `merge-ready`.
- `CL7` means the integrator, on the complete in-scope snapshot after a single batch's serial merge, runs seven deterministic checks: Wiki link missing / ambiguous / heading resolution; Markdown / YAML / fence / table structure; graph JSON and duplicate basename candidates; Coverage file-count reconciliation; guidance ID and contract version continuity; residual Interview section scan; Frontmatter controlled-vocabulary validation.
- The standard batch-close result is: the integrator serially applies one batch's delta, runs CL7 on the merged complete snapshot, then verifies the 12/03 global items, including incremental guidance reconciliation, zeroing of this batch's direct / dependency invalidations, and global Ledgers synchronization; the batch closes only when Batch Review passes and `unresolved_invalidations = 0`.

## G01 — Single-page Authoring

**Task.** Create a new atomic-depth, P1 regular canonical note; the content is not a core concept, process-flow, system, or risk-control mainline page, and introduces no external sources, formulas, diagrams, or specific display issues.

**Expected determination.** Routing is Core + Card 02 / RS 02; the page is tiered M. Page-close checks are folded into the batch gate: Card 02's ownership, depth, metadata, links, language, and content checks are executed, along with page-scoped `check_links` and `check_vocab` self-checks; with no visual exception trigger, rendering stops at Level 0 / 1. Batch close executes the Batch internal gate, incremental guidance / invalidation reconciliation, delta merge, and CL7; no independent note gate is opened.

## G02 — Module Build

**Task.** Build a complete module containing a MOC, multiple leaf pages, cross-module dependencies, and one P0 system mainline page; the work requires multiple batches.

**Expected determination.** Routing is Core + Card 03 / RS 03, combined with Card 07 / RS 07; at full module close, Card 08 / RS 08 is additionally combined. For tiering, the P0 system mainline page is L and the remaining pages are tiered page by page; a mixed batch containing L pages is governed by L, with the v2.3 default cap of 6 pages. L pages, once drafted and after the scope self-check, trigger the independent substantive-correctness review and the independent note gate; every batch passes Batch Review, the module additionally passes Module Review and Coverage Reconciliation at module end, and the task completion candidate then passes Terminal Audit. Every batch close executes the Batch internal gate, serial delta merge, global reconciliation, and CL7; the module gate reuses still-valid batch receipts and only supplements the cross-batch owner, dependency, coverage, and navigation judgments.

## G03 — Source-driven Expansion

**Task.** A new official vendor document provides locatable claims; a P2 Source Note must be established and one P1 canonical note that is not a mainline type must be updated.

**Expected determination.** Routing is Core + Card 04 / RS 04, combined with Card 02 / RS 02 because a canonical note is modified; official material still proves only its scope of disclosure. The Source Note is S — script checks only and inclusion in batch-close sampling; the P1 regular canonical note is M. Applicable gates include source identity / authority / evidence role, claim classification, gap and graph decision, Source Intake and Promotion Review, and the canonical note's M-tier Card gate; content that has not passed the promotion gate must not be marked canonical. Before batch close, the pipeline, changed-scope self-check, source receipts, and watermark delta are completed, followed by the standard serial batch close and CL7.

## G04 — Migration and Refactor

**Task.** Within a single exclusive migration batch, perform bulk moves, renames, and page splits on an existing content directory composed of P1 regular pages; target-page priority is frozen at P1 per the contract, while canonical ownership, heading anchors, incoming links, and all original content are preserved.

**Expected determination.** Routing is Core + Card 06 / RS 06. Affected pages remain P1 and are tiered M; the migration action itself produces no additional task tier. The migration batch must be exclusive and must not run concurrently with any other active batch; before starting, the source / target / incoming links / headings / owner / rollback inventory is frozen, and deletion at the old location may occur only after the new location is established, verified, and all references updated. Applicable gates are one-to-one content-block conservation, link and heading resolution, Coverage Reconciliation, Batch Review, automated and manual checks, and the final Terminal Audit. Batch close executes the standard serial batch close and CL7, where the link, structure, coverage, and vocabulary results must be based on the complete post-migration snapshot.

## G05 — Long-running Resume

**Task.** A multi-batch module-build task working on P1 regular pages resumes from `paused`; the YAML Progress / Coverage Ledgers record one `merge-ready` batch with its delta already written out, one unfinished active batch, the last QA, and the next precise action.

**Expected determination.** Routing is Core + Card 03 / RS 03 + Card 07 / RS 07; content pages remain M, and the resume action itself has no task tier. Resumption first verifies the latest user requirements, contract / scope / queue / time semantics, the working tree, existing user modifications, unverified changes, and guidance, then sets the task state back to `active`. The already `merge-ready` batch is carried forward by the integrator through serial merge without redoing in-batch work; the active batch continues from the checkpoint's next precise action. Each batch must still pass Batch Review, the receipt / invalidation gate, and CL7; before entering completion candidacy, Coverage Reconciliation is executed and Card 08 / RS 08 is then combined.

## G06 — Terminal Audit

**Task.** A long-running task has become a `completion-candidate`, all declared batches are closed, and a decision is needed on whether it may be marked `complete`.

**Expected determination.** Routing is Core + Card 08 / RS 08, plus loading the content Read Sets related to the findings; Terminal Audit produces no new page tier, and review objects retain their original tiers. First freeze the snapshot and the version / guidance cutoff; verify the receipt register, Guidance Reconciliation, Coverage Ledger, Required Queue, merge queue, invalidations, and all applicable gates; run CL7 again on the final frozen snapshot, performing semantic review only on changed, invalidated, overdue, and bounded-sample objects while reusing the remaining valid receipts. Only when the three pending guidance counts, required authoring gaps, unverified batches, and unresolved invalidations are all 0, all applicable gates pass, and the Final Handoff / Terminal Proof is complete does the state become `complete`.

## G07 — Standards Governance Revision

**Task.** The user explicitly authorizes modifying the Standards' module boundaries and one gate's semantics, and requires synchronizing the control-plane entry points and affected runtime artifacts.

**Expected determination.** Routing is Core + Card 09 / RS 09; governance tasks are handled at tier L, and the source modules of RS 09 must be read in full, with Card 09 serving only as navigation. Before the change, freeze the standards version, affected modules, incoming links, and active-task impact; during execution, bump `standards_version`, update `00`'s routing and Change Summary, and provide a changed-predicate list in the revision record. Structural changes establish a complete mapping from old content blocks to new owners, and synchronize the domain MOC, Read Sets, Registry, Cards, and vocab artifacts. Applicable gates include Standards coverage / MOC, repository-wide incoming links, active-task receipt compatibility / invalidation / adoption, the Write-back Checklist, `stamp_cards.py --check`, and Terminal Audit. When the governance batch closes, the changed-scope checks, standard serial batch close, and CL7 are completed; rules must not be reduced through splitting, summarized, or silently deleted.

## G08 — Maintenance Run

**Task.** Initiate a periodic maintenance run budgeted at two batches; candidates come from the freshness-expired items, watermark deltas, `needs_rereview`, and the duplicate / vocab / language candidates pools, and include one P0 system mainline page and several P2 Source Notes.

**Expected determination.** Routing is Core + Card 10 / RS 10; the P0 system mainline page is L, the P2 Source Notes are S, and the maintenance action itself has no task tier; if both kinds share a batch, L governs and the v2.3 default 6-page cap applies. The union of the four sources is sorted by priority and truncated to the budget; items beyond the budget go to deferred; source content combines Card 04, and L pages trigger the independent substantive review. Each batch passes Batch Review, advances the Ledgers and watermark, and runs CL7 after serial merge; freshness and duplicate checks belong to maintenance-run candidate generation and are not added to CL7. Once the two budgeted batches and their applicable gates close, the run finishes per Maintenance Completion; a repository-wide Terminal Proof is not required.

## G09 — Concurrent Batch Activation

**Task.** In a long-running module-build task, Batch A, composed of P1 regular pages, is already active; Batch B, also composed of P1 regular pages, is about to be activated. The two batches' page lists are disjoint; B does not edit the MOC, Overview, Roadmap, Cheat Sheet, or shared terminology pages; all of B's prerequisites were merged in earlier batches; and the current active count is below `concurrency_cap`.

**Expected determination.** Routing is Core + Card 03 / RS 03 + Card 07 / RS 07; the pages of both batches are M, and the activation action itself has no task tier. B satisfies the v2.3 three admission conditions and the cap, so it may go active; if any condition fails, activation is not permitted. Concurrent authors write only their own batch's pages, their own batch's receipts, and their own batch's delta; the global Ledgers, queue, guidance, contract, activation, and merging are controlled single-threaded by the integrator. A and B each first complete the Batch internal gate to enter `merge-ready`; the integrator then merges only one at a time, running CL7 and the 12/03 global items after each merge; the two batches must not be combined into a single batch close.

## G10 — Mid-task Guidance Disposition

**Task.** During execution of an M batch of P1 regular pages in a long-running module-build task, the user requests "after the current batch finishes, handle Topic B first in the next one"; the request adds no scope, lowers no acceptance, and does not require immediately interrupting the current atomic operation.

**Expected determination.** Routing is Core + Card 03 / RS 03 + Card 07 / RS 07, plus loading `02 Build Execution/02 Mid-task Guidance and Amendment.md`; this is an important priority / sequence Guidance Event, and the event itself does not change page tiers. The default disposition is `queue-next`: preserve the current batch boundary and switch after a safe boundary; establish a monotonic guidance ID and an Amendment Record; bump only `queue_revision`, not the unaffected contract or scope version. The applicable gate is Guidance Reconciliation: at batch close, verify that the event has been classified, mapped, and validated per its disposition, and that the three pending guidance counts are 0; CL7 additionally verifies guidance ID and contract version continuity.

## G11 — Review Convergence

**Task.** A newly created single-page canonical note is tiered L; after the scope self-check, round 1 of the independent review yields one major finding and one minor finding; the author fixes the major, keeps and records the minor, and then enters the confirmation round.

**Expected determination.** Routing is Core + Card 02 / RS 02, triggering the independent substantive-correctness review of `12 Quality Assurance/01 Quality Dimensions and Single Note Review.md`. Round 2 only confirms that round 1's major is closed and adds no review scope; the minor is non-blocking, and new issues found in the confirmation round go to Open Questions or are marked `needs_rereview` without reopening the round. If the major remains unclosed after two rounds or the scope keeps expanding, escalate to user adjudication; do not open a round 3. The independent review receipt must be in place before the Batch internal gate; if it replaces existing evidence, record the supersede. Only after the page's note gate passes may the batch enter the standard serial batch close and run CL7.

## G12 — Closed-list Execution Point

**Task.** In a long-running module-build task, two concurrent M batches of P1 regular pages have each completed their writing, scope self-check, manual / rendering QA, receipts, and delta, and both are in `merge-ready`; a decision is needed on when, and against which snapshot, the fixed seven checks run.

**Expected determination.** Routing is Core + Card 03 / RS 03 + Card 07 / RS 07, with `12 Quality Assurance/03 Module Coverage and Batch Review.md` and `12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md` as gate owners; the pages of both batches are M, and the execution point itself has no task tier. Each batch's AuditPlan is generated exactly once, before entering `merge-ready`; CL7 does not run at batch start, nor on an unmerged branch snapshot. The integrator first applies one batch's delta, then runs CL7 on the merged complete in-scope snapshot, completes the 12/03 global items, and closes that batch; the same sequence is then repeated for the next batch. The final Terminal Audit runs CL7 once more on the frozen final snapshot.

## Baseline Trace

| Scenarios | Baseline owners |
|---|---|
| G01–G04 | `00 Standards Control/02 Task Routing and Pre-execution.md`; `Read Sets/02–06`; `Cards/02–06`; `12 Quality Assurance/03 Module Coverage and Batch Review.md` |
| G05, G09, G10, G12 | `Read Sets/07 Long-running Execution Read Set.md`; `Cards/07 Long-running Execution Card.md`; `02 Build Execution/02,05,06`; `12 Quality Assurance/04,07` |
| G06 | `Read Sets/08 Audit and Completion Read Set.md`; `Cards/08 Audit and Completion Card.md`; `12 Quality Assurance/06,07` |
| G07 | `Read Sets/09 Standards Governance Read Set.md`; `Cards/09 Standards Governance Card.md`; `00 Standards Control/03 Standards Governance.md` |
| G08 | `Read Sets/10 Maintenance Run Read Set.md`; `Cards/10 Maintenance Run Card.md`; `00 Standards Control/02,06` |
| G11 | `12 Quality Assurance/01 Quality Dimensions and Single Note Review.md` |
