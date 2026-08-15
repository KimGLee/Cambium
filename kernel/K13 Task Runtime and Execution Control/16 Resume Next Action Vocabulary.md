## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|Standards Adoption State Transaction]].

## Purpose And Boundary

This module owns one object: the vocabulary of the machine-readable
`next_action` that `check_queue.py . --resume-status` reports. Exactly one
token is reported per run.

It owns the token names and what each selects, nothing more. The runtime state
each row reads, and the obligation to consume the reported token rather than
infer a fresh start, stay with
[[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|K13/14]];
the completion path with K13/12; batch lifecycle and holds with K13/08. Rows
follow the resume scan's evaluation order: an unresolved writer lock and a
failing runtime resolve ahead of the batch cycle. `<id>` is a batch ID; `<ids>`
a comma-separated ascending list.

## Token Table

| Token | Reported when | Selected action |
|---|---|---|
| `reconcile-interrupted-write` | An unresolved writer lock is present | Verify no writer remains, reconcile state files, receipts, revisions, and deltas, then remove only a proven-stale lock |
| `repair-runtime` | The scan reported errors (stale revisions, changed fingerprint, stale or duplicated `delta_apply` receipt, revalidation barrier), or no close bundle is recoverable because the applied batch is not `merge-ready` or the snapshot cannot be read | Repair and reconcile the existing runtime first; do not initialize over it |
| `resume-paused-task` | Task state is `paused` | Reconcile, return the task to `active` through `update_task.py`, rerun `--resume-status`, and follow the token then reported |
| `resolve-blocked-task` | Task state is `blocked` | Resolve the recorded block reason, then as above; work the block report names as free may proceed |
| `close-applied-batch:<id>:<queue-receipt>:<close-receipt>:<apply-receipt>` | An unheld `merge-ready` batch holds a current unconsumed `delta_apply` receipt and a valid, snapshot-matched close bundle was recovered | Run the exact `update_queue.py` close command reported with it; all three receipts bind |
| `run-batch-close-gate:<id>` | Same applied state, but no current bundle was recovered | Run `check_batch_close.py` for that batch before any Queue close, control input, other batch, or terminal archival |
| `archive-terminal-runtime` | Task state is `complete` or `cancelled` | Preserve unfinished batch and control records as incomplete history, then archive or roll the namespace over explicitly; see below |
| `reconcile-control-input` | Pending Guidance or pending Amendments are recorded | Classify, dispose, and log them per K13/04-K13/06 before batch work resumes |
| `run-standards-revalidation:<id>` | Batches carry outstanding Standards or profile revalidation and the aggregate's producer would admit them; the lowest-ordered is named. One a producer refuses is never named | Run the aggregate with only the owner receipts currently due; native owners stay required at their ordinary transitions. Consume it before merge, apply, or close |
| `run-terminal-audit` | Task state is `completion-candidate` | Preserve the frozen candidate and run the Terminal Audit; do not activate new work |
| `apply-delta:<id>` | The lowest-ordered `merge-ready` batch has `hold_state` `none` and no current apply receipt | Apply its already written-out delta in serial merge; in-batch work is not redone |
| `admit-delta:<id>` | The lowest-ordered `open` batch has a managed delta at handoff status `candidate` and `hold_state` `none` | Admit that handoff candidate through its admission gate |
| `resume-in-flight-batches:<ids>` | `open` or `merge-ready` batches exist but none qualified for admission, apply, or close | Reconcile the named batches before starting new work; see below |
| `complete-maintenance-task:<gate-receipt>` | No remaining work, maintenance semantics, and a current maintenance completion gate receipt exists | Consume that gate with `update_task.py`; do not regenerate state or a Terminal Proof |
| `run-maintenance-completion-gate` | Same, but no current gate receipt exists | Run `check_queue.py --require-maintenance-complete` with the current budget-manifest, Ledger-advance, and watermark-advance receipts, then consume it |
| `enter-completion-candidate` | No remaining work and build completion semantics | Take a current `--require-complete` receipt, enter `completion-candidate`, then run the build Terminal Audit |
| `activate-ready-batch:<ids>` | Nothing is in flight and one or more batches are activatable | Activate through `check_queue.py --require-ready <id>` before execution begins |
| `materialize-required-queue` | The Required Queue holds no items | Compile the Queue for the recorded task; do not initialize a second task over it |
| `resolve-holds-dependencies` | Items remain, none is ready, and none is in flight | Resolve the existing task's recorded holds or unmet dependencies |

## Tokens Without An Automated Path

Two rows name a state the current tools cannot leave on their own; reporting
them is correct, reading them as executable is not.

- `archive-terminal-runtime` has no procedure behind it: K13/14 records that
  automatic rollover is not part of the current tools, so the move is an
  explicit operator action and the namespace stays occupied until it is made.
- `resume-in-flight-batches:<ids>` also covers a held `merge-ready` batch that
  already carries a current `delta_apply` receipt: close, apply, and admit each
  require `hold_state` `none`, so none is selected. The token names the batch
  but no step that advances it; releasing the hold restores one.

These two are reported deliberately, and that is the line. A token its own
named producer would refuse is not in this class: nobody can take that action,
and since one token is reported per run it hides every later row while the
condition holds. `run-standards-revalidation:<id>` was one — it named batches
the `standards-revalidation` Gate's K00/12 cells (`queued, open`) exclude. A
row MUST select on what its named producer admits.

## Related

- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings|Completion Gate Bindings]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
