## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]].
- Next: [[kernel/K13 Task Runtime and Execution Control/13 Final Handoff|Final Handoff]].

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
