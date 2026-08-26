## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|Task Contract Binding and Time Semantics]].
- Next: [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|Guidance Classification and Impact Analysis]].

## Task State Machine

Long-task state is recorded only in the task Progress Ledger; it is not
expressed via the `authoring_status` of knowledge pages.

[`runtime-state-model.json`](runtime-state-model.json) is the sole machine
owner of task-state identities, state classes, and legal transition edges. It
registers separate current and historical catalogs for the mutually exclusive
`build` and `maintenance` completion semantics. The descriptions below explain
what the states mean; their order here is not a second transition table.

If a Standards/Profile mismatch invalidates build-completion evidence before
`complete`, `completion-candidate` may transition through the registered
task-state transaction to `paused` (preserve the checkpoint) or `active`
(continue eligible work) and resets `terminal_audit` to `invalidated`. This
explicit rollback precedes K12/10 adoption;
the adoption writer itself never changes task state.

The build model's closure from `planned` is available only for a materialized
nonempty Queue whose batches were all validly cancelled by Amendment before
any opened. It still enters `completion-candidate` and requires the selected
full completion gate; it is not an empty-Queue shortcut. Maintenance never
enters `completion-candidate` and can reach `complete` only from `planned` or
`active` after its own completion Gate.

- `planned`: the contract, scope, or inventory has not yet met the execution threshold.
- `active`: executing, or the next Required batch is known.
- `paused`: unfinished work stopped by request, `hard_stop_at`, interruption, checkpoint, or a fired escalation trigger ([[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|K13/17]] owns which conditions oblige one); resume information MUST be saved.
- `blocked`: an external dependency exists that cannot be resolved in the current environment, and no other Required work can proceed.
- `completion-candidate`: a build-only state in which the executor believes the scope is satisfied and awaits the Terminal Audit; a maintenance task MUST NOT enter it.
- `complete`: the selected closure passed: a valid Terminal Proof for build, or a valid maintenance completion gate for maintenance.
- `cancelled`: the user has explicitly terminated the current contract; it does not mean the knowledge scope is complete.

The registered task-state transaction is the sole ordinary task-state writer. The first batch
opening may invoke its helper for `planned -> active`; direct operator use of
that edge is rejected. Every transition records a receipt and refreshes the
checkpoint. Build closure consumes K13/12
`required-queue-completion` and then the K12/16 `terminal-proof` pass.
Maintenance closure consumes K13/12
`maintenance-completion` directly and never enters Terminal
Proof.
Progress keeps mutually exclusive `terminal_audit` and
`maintenance_completion` blocks; [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|K13/07]] owns their separation.

Current writes are authorized only by the completion-specific current catalog.
Historical transition receipts are replayed against the fixed historical
catalog they were produced under; a later current-catalog revision cannot
retroactively authorize or invalidate an old edge.

While task state is not `active`, Queue lifecycle/hold writes and canonical
delta application are prohibited, except that first atomic
`planned -> active` activation. Resume a `paused` or `blocked` task through
the task-state transaction before continuing batch execution.

`paused`, `blocked`, `cancelled`, and `complete` MUST be distinguished. The runtime environment ending, no files being under edit, reaching a point in time, or `In-progress batch: None` cannot automatically produce `complete`.
