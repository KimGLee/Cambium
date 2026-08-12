## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|Task Contract Binding and Time Semantics]].
- Next: [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|Guidance Classification and Impact Analysis]].

## Task State Machine

Long-task state is recorded only in the task Progress Ledger; it is not expressed via the `authoring_status` of knowledge pages. The common transitions are:

```text
planned -> active / paused / blocked / cancelled
active -> paused / blocked / cancelled
paused -> active / blocked / cancelled
blocked -> active / paused / cancelled
```

The frozen completion semantics adds exactly one mutually exclusive closure path:

```text
build:       planned / active -> completion-candidate -> complete
             completion-candidate -> active / paused  # invalidated evidence
maintenance: planned / active -> complete
```

If a Standards/Profile mismatch invalidates build-completion evidence before
`complete`, `completion-candidate` may transition through
`Tools/update_task.py` to `paused` (preserve the checkpoint) or `active`
(continue eligible work) and resets `terminal_audit` to `invalidated`. This
explicit rollback precedes K12/10 adoption;
the adoption writer itself never changes task state.

The direct `planned` closure edge exists only for a materialized nonempty Queue
whose batches were all validly cancelled by Amendment before any opened. It
still requires the selected full completion gate; it is not an empty-Queue
shortcut.

- `planned`: the contract, scope, or inventory has not yet met the execution threshold.
- `active`: executing, or the next Required batch is known.
- `paused`: unfinished work stopped by request, `hard_stop_at`, interruption, checkpoint, or a fired escalation trigger ([[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|K13/17]] owns which conditions oblige one); resume information MUST be saved.
- `blocked`: an external dependency exists that cannot be resolved in the current environment, and no other Required work can proceed.
- `completion-candidate`: a build-only state in which the executor believes the scope is satisfied and awaits the Terminal Audit; a maintenance task MUST NOT enter it.
- `complete`: the selected closure passed: a valid Terminal Proof for build, or a valid maintenance completion gate for maintenance.
- `cancelled`: the user has explicitly terminated the current contract; it does not mean the knowledge scope is complete.

`Tools/update_task.py` is the sole ordinary task-state writer. The first batch
opening may invoke its helper for `planned -> active`; direct operator use of
that edge is rejected. Every transition records a receipt and refreshes the
checkpoint. Build closure consumes [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings|K13/12]] `--require-complete`, then the K12/16
Proof pass. Maintenance closure consumes K13/12
`--require-maintenance-complete` directly and never invokes `check_proof.py`.
Progress keeps mutually exclusive `terminal_audit` and
`maintenance_completion` blocks; [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|K13/07]] owns their separation.

While task state is not `active`, Queue lifecycle/hold writes and canonical
delta application are prohibited, except that first atomic
`planned -> active` activation. Resume a `paused` or `blocked` task through
`update_task.py` before continuing batch execution.

`paused`, `blocked`, `cancelled`, and `complete` MUST be distinguished. The runtime environment ending, no files being under edit, reaching a point in time, or `In-progress batch: None` cannot automatically produce `complete`.
