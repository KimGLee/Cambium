## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/02 Build Execution/04 Architecture Samples and Dependency Build|Architecture Samples and Dependency Build]].
- Next: [[kernel/02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]].

## Batch Policy

Each batch SHOULD be a small module that can be accepted independently, not an arbitrary number of files.

A batch completes at least:

1. Canonical notes.
2. This batch's delta written out: page status, gaps, and next-batch updates enter the Coverage Ledger via the delta; the [[kernel/02 Build Execution/08 Progress Ledger#Progress Ledger|Progress Ledger]] and `Tools/state/watermark.yaml` are updated by the integrator at merge time, and source or maintenance batches write the watermark advance value into the delta's `watermark_advance` field.

The batch-close acceptance checklist is governed by [[kernel/12 Quality Assurance/14 Batch Review#Batch Review|12/03 Batch Review]]; in-batch items are completed before `merge-ready`, and global items are verified at serial merge.

Batch size is tiered by the dominant tier: tier S ≤24 pages, tier M ≤10 pages, tier L ≤6 pages; a mixed batch follows the cap of the highest tier among them. 24 / 10 / 6 are kernel defaults; the selected profile MAY explicitly override them in the manifest, and the resolved caps MUST be loaded and recorded at runtime.

Bulk-creating only file names and headings and then marking the whole batch complete is not allowed.

## Concurrent Batches

Batches may execute concurrently by default; the cap is controlled by the contract's `concurrency_cap` field. `3` is the kernel default; the selected profile manifest or task contract MAY explicitly override it, and the resolved cap MUST be recorded at runtime. Batch B MAY be activated while other batches are active, if and only if all of the following hold:

1. B's page manifest is disjoint from the manifests of all active batches; the integrator determines this at activation per Coverage `next_batch`.
2. B does not edit control or hub pages, including kernel Runtime Cards, MOCs, the Overview, shared terminology pages, and pages bound by the `Expression Layer Entry` or other profile-registered hub roles. Hub page synchronization is performed by the integrator as a separate small step after that batch's serial merge completes and before the next batch's merge begins; this content-editing action is not part of the serial zone's deterministic action list.
3. All of B's prerequisites are located in already-merged batches; B does not depend on pages of in-flight batches.

Migration or refactor batches necessarily edit hub pages and cross-batch pages, do not meet concurrency admission, and MUST execute exclusively; while a migration batch is active, no other batch is activated.

Write partition: a concurrent batch writes only three places — the pages in its own manifest, its own receipts directory, and its own delta file `Machine State/Deltas/<batch>.yaml`, whose schema is at `Tools/schemas/coverage_delta.template.yaml`. The Coverage Ledger, Progress Ledger, Required Queue, Amendment Log, and watermark are writable only by the integrator.

Batch close has two phases: after in-batch work completes in parallel, the batch enters `merge-ready`; in-batch work includes writing, the `--scope` self-check, all review receipts present, completion of the 12/14 in-batch items, and the delta written out. The integrator then merges batches serially one by one, performing only deterministic actions and global verification: apply the delta via `Tools/apply_delta.py`, run the [[kernel/12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]] against the merged full snapshot, verify the 12/14 global items, produce gate receipts, and close. Each serial merge handles exactly one batch.

Known exceptions to the serial zone keep an explicit registration mechanism; the current register is empty.

The control plane is always executed single-threaded by the integrator, including guidance disposition, queue revision, contract changes, standards adoption, batch activation, and merging. Stall alarms are timed per batch.

## Source-driven Expansion Batch

When expanding the knowledge base from primary or vendor sources, papers, postmortems, or community discussions, the batch MUST follow the [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]: a source-driven batch MUST run all stages (Stage 1–10) of the [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] in full.

A source batch MAY produce zero, one, or multiple canonical notes.
