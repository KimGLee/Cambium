## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views|Queue Compilation Replanning and Views]].
- Next: [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]].

## Concurrent Batches

Batches may execute concurrently by default; the cap is controlled by the contract's `concurrency_cap` field. `3` is the kernel default; the selected profile manifest or task contract MAY explicitly override it, and the resolved cap MUST be recorded at runtime. It bounds concurrently open batches, not the number of agents a runtime uses. Before Batch B changes from `queued` to `open`, the integrator runs `Tools/check_queue.py . --require-ready <batch-id>`. B MAY be activated while other batches are open if and only if all of the following hold:

1. B's frozen Queue manifest is disjoint from the manifests of all open batches, and each manifest exactly matches the Coverage `batch` / `next_batch` projection.
2. B does not edit control or hub pages, including kernel Runtime Cards, MOCs, the Overview, shared terminology pages, and pages bound by the `Expression Layer Entry` or other profile-registered hub roles. Hub page synchronization is performed by the integrator as a separate small step after that batch's serial merge completes and before the next batch's merge begins; this content-editing action is not part of the serial zone's deterministic action list.
3. Every Queue dependency of B is `closed`; B does not depend on pages of in-flight batches.

The machine-decidable members of condition 2's page set come from metadata that already exists: a page whose frontmatter carries `type: overview`, `runtime-card`, or `card-index`; a page carrying `type: term` with `scope: shared`; and any page the selected profile's `Expression Layer Entry` registers as a canonical dependency map. "Other profile-registered hub roles" remains in force, but no profile slot registers one today, so that clause currently contributes no page and is a future extension point. Editing and creating differ: an existing hub page in the frozen manifest blocks concurrent activation and takes the exclusive or `serial-integrator` route below, while a hub page this batch creates does not block it and is reported as a candidate for that batch's hub synchronization step.

Condition 2 is time-invariant, and its reporting reflects that. Whether a queued batch's manifest edits an existing hub page does not depend on which batch is being admitted, how many batches are active, or what has closed since — the answer is the same at every moment until a structural Amendment changes the batch's `execution_mode`. Reported only through readiness, such a batch looks merely "not yet its turn" and the defect stays invisible until it reaches the head of the Queue, so a whole mis-specified family is rediscovered one batch at a time. The consistency mode therefore reports every queued batch that fails condition 2 as a candidate over the whole Queue, naming the batch, the hub pages, and the current mode. It stays a candidate rather than an error because the repair is an Amendment and the Amendment tools refuse to run against a runtime carrying errors: a hard failure would wedge the instance out of its own repair path. The other admission conditions stay readiness-only, because each of them is a statement about *now* — a dependency not yet closed, a cap currently reached, a manifest currently overlapping active work — and becomes true or false as the run proceeds.

For a complex batch, readiness additionally requires a current Work Spec
path/hash whose batch ID and ordered manifest equal B. The worker reads that
specification after activation together with the Standards for the selected
route. The specification narrows this batch's instructions; it cannot enlarge
the frozen manifest or override Kernel, Profile, Queue, or Amendment state.

Migration or refactor batches necessarily edit hub pages and cross-batch pages, do not meet concurrency admission, and MUST use an exclusive or `serial-integrator` execution mode; while such a batch is open, no other batch is activated.

Write partition: a concurrent batch writes only three places — the pages in its own manifest, its own directory under `.cambium/receipts/`, and its own delta file `.cambium/deltas/<batch>.yaml`, whose schema is at `Tools/schemas/coverage_delta.template.yaml`. That file is the batch's **Delta**: the record of the changes the batch produced, written by the worker and applied by the integrator at close. Every file under `.cambium/state/`, plus the Amendment Log and watermark, is writable only by the integrator.

Batch close has two phases: after in-batch work completes in parallel, the integrator verifies the `merge-ready` preconditions, records the current K12/14 `batch-review` gate that binds the exact Delta page receipt-ID set, and records `open -> merge-ready` with that gate as transition evidence; in-batch work includes writing, the `--scope` self-check, all review receipts present, completion of the K12/14 in-batch items, and the exact-manifest delta written out. Historical page evidence remains reusable while valid, but it cannot authorize the transition without this current wrapper. The integrator then merges batches serially one by one: apply the delta through canonical `Tools/apply_delta.py --root`, run the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]] against the merged full snapshot, verify the K12/14 global items, obtain a current Queue consistency receipt and any conditionally required Corpus Planning child receipt, and record `merge-ready -> closed` through `Tools/update_queue.py`. The close transition derives the Coverage `next_batch` projection and synchronizes the Progress Queue reference under the shared write lock. Each serial merge handles exactly one batch; the sequence is guarded and recoverable but is not misrepresented as one filesystem-atomic operation.

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
| `queued -> open` | current `--require-ready` receipt; closed dependencies; bound confirmation when required; valid current Work Spec pair when non-null; disjoint active manifest; concurrency/exclusivity satisfied |
| `open -> merge-ready` | exact-manifest delta; valid page receipts and scoped checks; one current K12/14 `batch-review` wrapper binding their exact IDs |
| `merge-ready -> closed` | delta applied; global gates and Coverage/Queue reconciliation passed; current consistency and batch-close receipts bind the recomputed repository snapshot; when R13 is selected or the manifest intersects the validator-parsed Corpus Planning affected set, the close bundle contains a distinct current Corpus Planning child receipt |
| `merge-ready -> open` | failed merge; append-only `invalidation_history` freezes the archived delta SHA/path and invalidated receipts. Before the apply that is the whole record. After the apply the record also names the delta-apply receipt being undone and the byte-exact Coverage restore that undid it, read from the pre-apply Coverage archive the apply wrote; an absent or non-matching archive fails closed for manual recovery |

`Tools/update_queue.py` recomputes the Corpus Planning requirement from the
current Progress route selection, Queue manifest, and validator-parsed explicit
path projection before close and again under the writer lock. The close
aggregator cannot turn the gate off by declaring `corpus_plan_required: false`,
and a child whose Profile, Scope, slot, artifact, state, revision, or repository
fingerprint is stale cannot authorize the transition.

`check_queue.py` solely gates Queue structure, cross-state agreement, readiness,
Work Spec binding, evidence, revisions/SHA, concurrency, recovery, and terminal count.
