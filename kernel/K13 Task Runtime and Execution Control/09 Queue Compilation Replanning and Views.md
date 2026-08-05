## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]].
- Next: [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]].

## Compiler, Updates, And Views

`compile_queue.py` deterministically proposes structure from Coverage
`batch_specs`, without inferred edges or silent deletion. Initial apply starts
from an empty Queue and records its origin. Same-scope replan uses a complete
staged Coverage proposal bound to its Amendment, diff, and all live-state SHAs;
terminal history remains and in-flight structure cannot change.

`update_queue.py` alone applies lifecycle/hold transitions and the close-time
Coverage projection. After canonical delta apply, only checks and that batch's
close may proceed until the apply receipt is consumed. Cancellation is never a
direct Queue transition.

An apply receipt alone never authorizes close. Restart recovery of a missing or
persisted close bundle is owned by [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|K13/14]];
this page only owns the close transition's required evidence.

`apply_amendment.py` is the sole scope-replan/cancellation transaction and
binds the approved Amendment, complete Coverage proposal, revisions, and three
state SHAs. These writers share the recovery lock and durable prepare/outcome
evidence; uncertain recovery retains the lock. `render_queue.py` writes only a
human view.
