## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]].
- Next: [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]].

## Compiler, Updates, And Views

`compile_queue.py` deterministically proposes structure from Coverage
`batch_specs`, without inferred edges or silent deletion. Initial apply starts
from an empty Queue and records its origin. Same-scope replan uses a complete
staged Coverage proposal first registered by `register_amendment.py`, then
binds that authorization receipt, its Amendment, deterministic diff, and all
live-state SHAs; terminal history remains and in-flight structure cannot
change.

A `batch_specs` row for a terminal item is no longer live compiler authority.
The compiler ignores its edit or absence and preserves the sealed Queue item;
retiring stale compiler input therefore cannot become a remove conflict or
turn an otherwise unrelated replan into cancellation.

Coverage `batch_specs` explicitly provides each proposed Work Spec path/hash
pair. The compiler copies and validates it; it never guesses whether a batch
is simple or complex. Missing or partial Work Spec fields fail closed; Queue
compilation and replanning do not upgrade predecessor schema shapes. For an
open batch, a Work-Spec-only replan is permitted only after
`update_queue.py` has recorded `revalidation-required`; merge-ready and
terminal Work Spec bindings cannot be replanned.

`update_queue.py` alone applies lifecycle/hold transitions and the close-time
Coverage projection. After canonical delta apply, only checks and that batch's
close may proceed until the apply receipt is consumed. Cancellation is never a
direct Queue transition.

An apply receipt alone never authorizes close. Restart recovery of a missing or
persisted close bundle is owned by [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|K13/14]];
this page only owns the close transition's required evidence.

`apply_amendment.py` is the sole scope-replan/cancellation transaction and
binds the registered Amendment and authorization receipt, complete Coverage
proposal, revisions, and three state SHAs. These writers share the recovery
lock and durable prepare/outcome evidence; uncertain recovery retains the
lock. Registration authority and its lock-time re-derivation are owned by
[[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|K13/06]].
`render_queue.py` writes only a human view.
