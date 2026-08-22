# Escalation Policy

Interface: [Escalation Policy slot](../../README.md#escalation-policy-slot)

This corpus uses long autonomous batch runs, so the executor may reach
situations that require a person before work can continue: the plan changes
materially, a batch stops moving, or an action cannot be undone. The kernel
trigger for modifying the Standards or the selected Profile is owned by
[[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|K13/17]]
and is not repeated here.

Thresholds are derived from the Progress Ledger rather than copied into this
Profile. At each maintenance boundary, or after another twenty batches close:

- `replan_magnitude` is three times the largest Required-record-count change
  made by an ordinary replan, with a 5% floor. Until ten ordinary replans have
  completed, the threshold is 30%. An ordinary replan is one the user did not
  pre-review item by item.
- `batch_age` is ten times the rolling p99 duration of the latest twenty closed
  batches, clamped to four through forty-eight hours. Until twenty batches
  have closed, the threshold is forty-eight hours.

The formulas are Profile policy; the current values remain runtime state.

## Escalation Triggers

- Registration: Configured

| Trigger ID | Condition that fires it | `machine-checkable` or `review-checkable` | Deciding Role ID reference | Resume condition |
|---|---|---|---|---|
| `replan_magnitude` | One replan changes the Required record count by more than the ledger-derived `replan_magnitude` threshold. | `machine-checkable` | `stopper` | The user approves the replanned scope. |
| `batch_stalled` | An `open` or `merge-ready` batch remains in that state longer than the ledger-derived `batch_age` threshold. | `machine-checkable` | `stopper` | The user decides whether to finish, split, or abandon the batch. |
| `irreversible_operation` | The next action physically deletes a page, or rewrites history by any means other than a registered Amendment | `review-checkable` | `stopper` | The user authorizes that specific operation |
