## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|Guidance Classification and Impact Analysis]].
- Next: [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|Amendment Log and Controlled Replanning]].

## Mid-task Guidance And Contract Amendment

### Disposition

Each important guidance MUST be given one explicit disposition. [`runtime-state-model.json`](runtime-state-model.json) is the sole machine owner of disposition and status membership and of which statuses are final. The entries below define the meaning of registered dispositions; their presence in prose does not create or extend the closed set.

- `interrupt-now`: immediately save a consistent checkpoint and switch.
- `apply-to-current-batch`: consistent with the current owner and acceptance; can be integrated without expanding the batch boundary.
- `queue-next`: execute immediately after the current smallest acceptable unit completes.
- `queue-by-dependency`: add the object/dependency to Coverage, then recompile Queue.
- `research-first`: do source inventory, claim extraction, and gap analysis first.
- `deferred`: postponed; the reason, re-entry condition, and authority MUST be recorded.
- `clarification-required`: high-impact semantics cannot be reliably judged; await user clarification.
- `superseded`: replaced by later explicit guidance, with the replacement relationship preserved.
- `not-applicable`: unrelated to the current contract or already fully covered by existing work; the basis MUST be stated.

`deferred` or `not-applicable` MUST NOT be used to silently drop requirements newly added by the user.

### Safe Switching Policy

By default, switch at the smallest safe boundary rather than leaving inconsistent state in the middle of a file or a verification. Usually first complete the current atomic edit, save the file, and run the necessary local checks, then checkpoint and re-order the queue. Under concurrent execution, interruption and switching are performed by the integrator: locate the affected batches per the Amendment Record's `affected_batches`; unaffected batches are not interrupted.

The following cases MUST interrupt immediately:

- The user explicitly requests an immediate stop, pause, or switch.
- A new constraint forbids continuing the current action.
- The current work contains a safety, data-integrity, or serious factual error.
- New information invalidates the current batch's underlying assumptions.
- Continuing would enlarge an error, overwrite user modifications, or produce irreversible side effects.

The following cases usually do not interrupt immediately:

- Adding a cross-domain topic with no direct dependency on the current batch.
- Only changing subsequent priorities.
- A user hypothesis that requires source research before confirmation.
- Formatting or navigation requirements that can be handled safely after the current atomic operation.

Small additions with the same owner and the same acceptance MAY enter the current batch; new topics that cross owners or systems MUST form an independent vertical slice. Continuously arriving guidance MUST NOT all be stuffed into the current batch, causing unbounded batch expansion.

### User-facing Acknowledgement

After receiving important guidance that affects the task, a brief progress update SHOULD state:

- What type it was understood as.
- Which scope, batches, or evidence work it affects.
- Whether it will be applied immediately, switched to after a safe boundary, queued by dependency, or researched first.
- Whether it changes the contract, scope, queue, or Standards version.

When there is no substantive ambiguity, repeated confirmation requests are not needed; but the user must not discover only in the final report that their guidance was deferred or ignored.
