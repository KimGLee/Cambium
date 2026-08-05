## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/K02 Build Execution/04 Architecture Samples and Dependency Build|Architecture Samples and Dependency Build]].
- Next: [[kernel/K02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]].

## Batch Policy

Each batch SHOULD be a small module that can be accepted independently, not an arbitrary number of files. Its identity, frozen manifest, dependencies, execution mode, lifecycle, and hold state are owned by [[kernel/K02 Build Execution/09 Required Queue|K02/09]]; this page owns how an admitted batch executes.

A batch completes at least:

1. Canonical notes.
2. This batch's delta written out: worker-owned page status and evidence may enter Coverage through the delta; `next_batch_updates` and watermark advancement remain explicit integrator work. Queue/compiler-owned disposition, ownership, routing, priority, tier, type, prerequisites, and deferral fields are forbidden in a worker delta. The [[kernel/K02 Build Execution/08 Progress Ledger#Progress Ledger]] Queue reference and `Tools/state/watermark.yaml` are reconciled by their respective integrator steps.

The batch-close acceptance checklist is governed by [[kernel/K12 Quality Assurance/14 Batch Review#Batch Review|K12/14 Batch Review]]; in-batch items are completed before `merge-ready`, and global items are verified at serial merge.

Batch size is tiered by the dominant tier: tier S ≤24 pages, tier M ≤10 pages, tier L ≤6 pages; a mixed batch follows the cap of the highest tier among them. 24 / 10 / 6 are kernel defaults; the selected profile MAY explicitly override them in the manifest, and the resolved caps MUST be loaded and recorded at runtime.

Bulk-creating only file names and headings and then marking the whole batch complete is not allowed.

## Concurrent Batches

Batches may execute concurrently by default; the cap is controlled by the contract's `concurrency_cap` field. `3` is the kernel default; the selected profile manifest or task contract MAY explicitly override it, and the resolved cap MUST be recorded at runtime. Before Batch B changes from `queued` to `open`, the integrator runs `Tools/check_queue.py . --require-ready <batch-id>`. B MAY be activated while other batches are open if and only if all of the following hold:

1. B's frozen Queue manifest is disjoint from the manifests of all open batches, and each manifest exactly matches the Coverage `batch` / `next_batch` projection.
2. B does not edit control or hub pages, including kernel Runtime Cards, MOCs, the Overview, shared terminology pages, and pages bound by the `Expression Layer Entry` or other profile-registered hub roles. Hub page synchronization is performed by the integrator as a separate small step after that batch's serial merge completes and before the next batch's merge begins; this content-editing action is not part of the serial zone's deterministic action list.
3. Every Queue dependency of B is `closed`; B does not depend on pages of in-flight batches.

Migration or refactor batches necessarily edit hub pages and cross-batch pages, do not meet concurrency admission, and MUST use an exclusive or `serial-integrator` execution mode; while such a batch is open, no other batch is activated.

Write partition: a concurrent batch writes only three places — the pages in its own manifest, its own directory under `.cambium/receipts/`, and its own delta file `.cambium/deltas/<batch>.yaml`, whose schema is at `Tools/schemas/coverage_delta.template.yaml`. Every file under `.cambium/state/`, plus the Amendment Log and watermark, is writable only by the integrator.

Batch close has two phases: after in-batch work completes in parallel, the integrator verifies the `merge-ready` preconditions and records `open -> merge-ready`; in-batch work includes writing, the `--scope` self-check, all review receipts present, completion of the K12/14 in-batch items, and the exact-manifest delta written out. The integrator then merges batches serially one by one: apply the delta through canonical `Tools/apply_delta.py --root`, run the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]] against the merged full snapshot, verify the K12/14 global items, obtain a current Queue consistency receipt, and record `merge-ready -> closed` through `Tools/update_queue.py`. The close transition derives the Coverage `next_batch` projection and synchronizes the Progress Queue reference under the shared write lock. Each serial merge handles exactly one batch; the sequence is guarded and recoverable but is not misrepresented as one filesystem-atomic operation.

Known exceptions to the serial zone keep an explicit registration mechanism; the current register is empty.

The control plane is always executed single-threaded by the integrator, including guidance disposition, Queue structural revision, Queue state transition, contract changes, Standards adoption, batch activation, and merging. Workers submit deltas; they never change Queue state. Stall alarms are timed per batch.

## Source-driven Expansion Batch

When expanding the knowledge base from primary or vendor sources, papers, postmortems, or community discussions, the batch MUST follow the [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]: a source-driven batch MUST run all stages (Stage 1–10) of the [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] in full.

A source batch MAY produce zero, one, or multiple canonical notes.
