## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views|Queue Compilation Replanning and Views]].
- Next: [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]].

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

## Transition Gates

Only the integrator changes Queue lifecycle/holds via `Tools/update_queue.py`,
with expected revisions/SHA under the shared lock. Such writes and canonical
delta application require task state `active`; the first activation atomically
uses the task-state owner to change `planned -> active`. Workers write only
manifest objects, their receipts, and `.cambium/deltas/<batch-id>.yaml`.

| Transition | Required evidence |
|---|---|
| `queued -> open` | current `--require-ready` receipt; closed dependencies; bound confirmation when required; disjoint active manifest; concurrency/exclusivity satisfied |
| `open -> merge-ready` | exact-manifest delta; current receipts and scoped checks; K12/14 in-batch review |
| `merge-ready -> closed` | delta applied; global gates and Coverage/Queue reconciliation passed; current consistency and batch-close receipts bind the recomputed repository snapshot |
| `merge-ready -> open` | failed merge; append-only `invalidation_history` freezes the archived delta SHA/path and invalidated receipts |

`check_queue.py` solely gates Queue structure, cross-state agreement, readiness,
evidence, revisions/SHA, concurrency, recovery, and terminal count.
