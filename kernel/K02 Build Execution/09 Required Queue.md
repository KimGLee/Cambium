## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/K02 Build Execution/08 Progress Ledger|Progress Ledger]].

## Purpose And Ownership

The Required Queue owns batch manifests, order, dependencies, lifecycle, holds,
and transition evidence. Coverage owns object disposition, owner, and batch
projection; Progress owns task state/contract, Amendments, checkpoints,
completion binding, and Queue reference. Reports/executor lists are not
authority.

## Runtime State Namespace

Persistent, resumable, multi-batch, R07, or R11 work uses:

```text
.cambium/
  state/{coverage_ledger.yaml,required_queue.yaml,progress_ledger.yaml}
  deltas/  receipts/  reports/  tmp/
```

State, deltas, and receipts are durable; reports are derived, and managed paths
stay repository-contained. Initialize only when `.cambium/` is absent;
otherwise run `check_queue.py --resume-status` before any write and follow its
machine `next_action`. Bounded work needs no empty Queue. A lock remains until
the state SHAs, receipts, deltas/archive moves, and absence of a live writer
reconcile. New tasks archive rather than repurpose existing state.

## Queue Document Contract

`.cambium/state/required_queue.yaml` follows its Tools schema. Identity includes
schema, task, scope, Standards/profile, both revisions, and `required_queue`.

Every item explicitly supplies `id`, `family`, unique contiguous `order`,
positive `record_count`, nonempty unique `manifest`, nullable `source_route`,
`execution_mode`, `depends_on`, `confirmation_required`, `state`, and
`hold_state`. Dependencies are explicit, acyclic, earlier than dependents, and
never inferred. `concurrent-worker` may coexist; `serial-integrator` is
exclusive.

An in-flight manifest is frozen. Coverage projects its sets through `batch` /
`next_batch`; top-level `batch_specs` is compiler input, not lifecycle state,
with exactly `id`, `family`, `order_hint`, `source_route`, `execution_mode`,
`depends_on`, and `confirmation_required`. Outside controlled
replan/cancellation staging, Queue and Coverage sets must be equal.

## Revisions And Fingerprints

`queue_revision` increments on structure/verification-contract change;
`state_revision` (externally `queue_state_revision`) on lifecycle/hold change.
References also bind canonical Queue SHA-256. Structure and lifecycle never
hide inside each other.

## Batch Lifecycle

```text
queued -> open -> merge-ready -> closed
queued/open -> cancelled
merge-ready -> open
```

`open` freezes its partition; `merge-ready` has exact delta, receipts, and QA;
`closed` passed serial integration/global gates. Terminal history is immutable;
later work uses a successor. Cancellation needs a scope/disposition Amendment.

`hold_state` independently takes `none`, `confirmation-required`, `blocked`,
`revalidation-required`, or `paused`; it is neither lifecycle nor task state.
Each non-queued item retains ordered `transition_receipts` binding task/item,
before/after state/hold, revision edge, Queue revision/fingerprints, tool, and
integrator. State fields record timezone-aware timestamps and required
activation/confirmation/delta/batch/close/cancellation/successor evidence.
Referenced receipts must exist, pass, remain valid, and match mode/scope.

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

## Compiler, Updates, And Views

`compile_queue.py` deterministically proposes structure from Coverage
`batch_specs`, without inferred edges or silent deletion. Initial apply starts
from an empty Queue and records its origin. Same-scope replan uses a complete
staged Coverage proposal bound to its Amendment, diff, and all live-state SHAs;
terminal history remains and in-flight structure cannot change.

`update_queue.py` alone applies lifecycle/hold transitions and the close-time
Coverage projection. After canonical delta apply, only checks and that batch's
close may proceed until the apply receipt is consumed. Cancellation is never a
direct Queue transition.

An apply receipt alone never authorizes close. Restart recovery of a missing or
persisted close bundle is owned by [[kernel/K02 Build Execution/06 Existing Changes Migration and Resume|K02/06]];
this page only owns the close transition's required evidence.

`apply_amendment.py` is the sole scope-replan/cancellation transaction and
binds the approved Amendment, complete Coverage proposal, revisions, and three
state SHAs. These writers share the recovery lock and durable prepare/outcome
evidence; uncertain recovery retains the lock. `render_queue.py` writes only a
human view.

## Completion Gates

Progress freezes one completion path. Build uses `--require-complete` before
`completion-candidate` and again for Terminal Proof. Maintenance uses
`--require-maintenance-complete`, never task state `completion-candidate` or
`check_proof.py`. It closes the candidate set, exact partition, Queue
projection, and prior-run age/re-entry. The gate consumes current
budget-manifest-closed, Coverage-ledger-advanced,
and watermark-advanced receipts; requires a nonempty Queue with zero remaining
work, reconciled controls, terminal history, and applicable batch/close-gate
evidence; and emits a receipt binding the current three state SHAs and Queue
revisions. Only `update_task.py` may consume it to mark the task complete.

A planned nonempty Queue whose batches were all validly cancelled by Amendment
may enter its selected completion path; an empty Queue cannot. After
interruption, resume consumes a maintenance pass only while
bindings remain current; else next action is
`run-maintenance-completion-gate`, never `enter-completion-candidate`.

## Control Accretion Decision

Previously, scattered K02 prose and hand-maintained Progress batch lists owned
this risk but could not prevent cross-state drift. This page is the sole rule
owner and `check_queue.py` the sole gate. Progress therefore no longer owns a
duplicate `batches[]`, active list, merge queue, or batch receipts; it keeps
only the accepted Queue reference and whole-task state.
