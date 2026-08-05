## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|Progress Ledger Contract]].
- Next: [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views|Queue Compilation Replanning and Views]].

## Purpose And Ownership

The Required Queue owns batch manifests, order, dependencies, lifecycle, holds,
and transition evidence. Coverage owns object disposition, owner, and batch
projection; Progress owns task state/contract, Amendments, checkpoints,
completion binding, and Queue reference. Reports/executor lists are not
authority.

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
