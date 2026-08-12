# Escalation Policy

Interface: [Escalation Policy slot](../../README.md#escalation-policy-slot)

This corpus is built by long autonomous batch runs, so the executor reaches
situations no batch gate judges: the plan itself changes shape, a batch stops
moving, or an action cannot be undone. Each row below names one such
situation, what counts as it happening, and who decides. The kernel trigger —
explicit user authorization to modify the Standards or the selected profile —
is owned by
[[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|K13/17]]
and is deliberately not repeated here.

The two magnitudes are this instance's numbers, recalculated at each
maintenance boundary or every twenty closed batches. `replan_magnitude` is
three times the largest change any ordinary replan has made to the Required
record count, floored at 5%, and falls back to 30% while fewer than ten
ordinary replans have run; an ordinary replan is one the user did not
pre-review item by item. `batch_age` is ten times the p99 batch duration over
a rolling twenty batches, clamped to between four and forty-eight hours, and
falls back to forty-eight hours while fewer than twenty batches have closed.
Both live in the Progress Ledger's run history, not in this file, because a
value recomputed from the ledger cannot be restated here without going stale.

## Escalation Triggers

- Registration: Configured

| Trigger ID | Condition that fires it | `machine-checkable` or `review-checkable` | Deciding Role ID reference | Resume condition |
|---|---|---|---|---|
| `quota_overrun` | A priority-quota target is exceeded with no recorded exemption | `machine-checkable` | `stopper` | The user grants an exemption, or the quota is brought back within target |
| `replan_magnitude` | One replan changes the Required record count by more than the current `replan_magnitude` threshold | `machine-checkable` | `stopper` | The user approves the replanned scope |
| `batch_stalled` | An `open` or `merge-ready` batch has been in that state longer than the current `batch_age` threshold | `machine-checkable` | `stopper` | The user rules on whether to finish, split, or abandon the batch |
| `irreversible_operation` | The next action physically deletes a page, or rewrites history by any means other than a registered Amendment | `review-checkable` | `stopper` | The user authorizes that specific operation |
