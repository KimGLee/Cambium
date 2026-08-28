## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings|Completion Gate Bindings]].
- Next: [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|Standards Adoption State Transaction]].

## Interruption And Resume

Before a planned interruption, the registered task-state transaction records `paused` or `blocked` and a checkpoint. A sudden interruption may prevent that transition, so durable Queue state, Deltas, receipts, and transaction evidence must remain independently discoverable. A checkpoint binds its time, summary, task transition, Coverage and Queue fingerprints, and Queue revisions; it is not a second editable batch list.

The effective restart view combines the checkpoint with the Task Contract, Coverage, Queue, Work Specs, Deltas, receipts, and current runtime validation. It must expose:

- task, scope, Standards, selected Profile, and Queue identity;
- open or merge-ready batches, holds, pending Deltas, and unfinished Required
  objects;
- every Work Spec binding;
- pending Guidance and Amendments, accepted checks, and modified or unverified
  work;
- exactly one machine-resolvable next action, including the block reason and
  any work still allowed to proceed.

At every restart, `runtime-startup-recovery` is evaluated before any Agent assumes the repository is unused. If no persistent task state exists, an authorized task may initialize beside preserved governance and history. If task state exists, initialization cannot replace it. The startup result binds the current state and selects one next action from K13/16's machine contract.

Resume must verify current user requirements, task state, Contract and time semantics, Standards and Profile identity, cross-state consistency, Work Spec currency, pending Deltas and transaction evidence, new user changes, evidence currency, and dependency order. A new batch activation additionally requires `required-queue-admission`.

An uncertain writer or publication is evidence of a possible interrupted transaction. It takes precedence over ordinary execution until the registered recovery capability establishes that no live writer remains and reconciles the authoritative state, revisions, Deltas, receipts, and any archived before image. Age alone cannot prove that transaction evidence is stale. An apply receipt alone cannot authorize Queue close; all owner receipts for the boundary must remain current.

The Agent consumes the reported next action rather than inferring a fresh start from an empty local context. Only after reconciliation may a paused or blocked task return to `active`. A new task cannot reuse current task state: prior state must be terminal and its history preserved through the adopter's archive or rollover mechanism.
