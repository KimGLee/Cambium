## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]].
- Next: [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]].

## Completion Gates

Progress freezes one completion path. Build uses `required-queue-completion` before `completion-candidate` and again for Terminal Proof. Maintenance uses `maintenance-completion`, never task state `completion-candidate` or Terminal Proof. It closes the candidate set, exact partition, Queue projection, and prior-run age/re-entry. The gate consumes current budget-manifest-closed, Coverage-ledger-advanced, and watermark-advanced receipts; requires a nonempty Queue with zero remaining work, reconciled controls, terminal history, and applicable batch/close-gate evidence; and emits a receipt binding the current three state SHAs and Queue revisions. Only the registered task-state transaction may consume it to mark the task complete.

A planned nonempty Queue whose batches were all validly cancelled by Amendment may enter its selected completion path; an empty Queue cannot. After interruption, resume consumes a maintenance pass only while bindings remain current; else next action is `run-maintenance-completion-gate`, never `enter-completion-candidate`.

For build completion, the frozen Terminal Proof also names a current `corpus-plan-structure` receipt. The `terminal-proof` Gate consumes it from the declared Audit Receipt Register and verifies the exact selected Profile/Scope/slot/artifact fingerprints, canonical state fingerprints, Queue revisions, applicability, and repository snapshot. This receipt is required even when the slot uses `applicability.state: not-applicable`; that explicit inactive contract is the evidence. A stale or missing child blocks the Proof pass and therefore cannot be consumed by the task-state completion transition.
