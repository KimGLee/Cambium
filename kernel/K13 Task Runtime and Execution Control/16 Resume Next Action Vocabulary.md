## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|Standards Adoption State Transaction]].
- Next: [[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|Escalation Policy]].

## Purpose And Boundary

This module owns the semantic contract of the machine-readable next action
reported by `runtime-startup-recovery`. It does not own task state, Queue
lifecycle, completion, or recovery implementation.

The Kernel owns the priority and result invariants below. The Tool
implementation owns token spelling, parameter encoding, deterministic
evaluation, and routing to executable capabilities; those implementation
details do not form a second Kernel vocabulary in this page.

## Next-action Invariants

Every valid startup evaluation produces exactly one action under these rules:

- possible interrupted writes and invalid runtime state take precedence over
  ordinary batch execution;
- paused or blocked task state is resolved before Queue work resumes;
- already-applied, ready-to-close, or in-flight work is reconciled before new
  work is activated;
- pending Guidance, Amendments, Standards revalidation, and completion
  obligations are handled at their owned boundaries;
- build and maintenance completion select mutually exclusive actions;
- an unmaterialized Queue selects Queue materialization, never initialization
  of a second task;
- unresolved holds or dependencies remain attached to the existing task.

A token may be emitted only when its named capability would admit the current
state. The status result cannot recommend an operation whose own producer must
reject it, because one impossible action would hide every later action.

Where no deterministic capability can complete the selected action, the token
must say that operator intervention is required and preserve the occupied
runtime state. Such a token is a truthful recovery boundary, not permission to
infer success or discard history.

The Agent consumes the exact selected action and its bound object identities.
Token text is routing output, not independent authorization: each eventual
operation still requires its ordinary Gate and transaction evidence.

## Related

- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings|Completion Gate Bindings]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
