## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/12 Control Registry|Control Registry]].
- Next: [[kernel/K00 Standards Control/17 Profile Dependency Closure|Profile Dependency Closure]].

## Purpose And Ownership

This page owns the implementation-independent admission conditions for
runtime-state discovery and for large-scale creation, moves, or deletion. It
does not own task routing, storage layout, recovery algorithms, or commands.

## Runtime Startup Gate

Before any task writes content or task-control state, the
`runtime-startup-recovery` Gate determines whether a persistent task runtime
already exists and emits one current next action. This discovery is universal
even when the new request appears bounded; an earlier task may still be paused,
interrupted, or awaiting integration.

- When no task runtime exists, only an authorized persistent, resumable, or
  multi-batch task may initialize one, after task, Standards, scope, Profile,
  and completion semantics are known. A bounded task does not create empty
  task state.
- When task runtime exists, consumers follow the Gate's reported action and
  reconcile the recorded task, Queue, evidence, pending changes, and any
  interrupted-write condition before another write.
- A new task MUST NOT initialize over, repurpose, or silently reset an existing
  runtime. Terminal state remains durable history until an explicit archive or
  rollover operation handles it.
- Uncertain or inconsistent state fails closed while preserving the evidence
  needed for recovery. Kernel requires a recoverable result; the lock format,
  journal, file sequence, and repair procedure belong to Tool.

The startup gate discovers control state; it does not authorize the content
work itself. A bounded task may proceed without creating task runtime state
when no task runtime exists. When one is present, the recorded task is
reconciled before any content or control write, regardless of the apparent size
of the new request.

## Large-scale Pre-execution Gate

Large-scale creation, moves, or deletion may begin only when all of the
following externally observable conditions hold:

1. The Task Contract fixes objective, scope and exclusions, Standards/Profile
   identity, completion semantics, time bounds, and authorization.
2. The Runtime Startup Gate has passed, and any pre-existing task state has
   been legitimately resumed or reconciled without discarding history.
3. Coverage is current and reconciled against the governed corpus; ownership,
   incoming references, and existing user modifications are accounted for.
4. Corpus Planning is configured and the `corpus-plan-structure` Gate passes
   for the admitted scope.
5. The Required Queue is materialized from explicit Coverage assignments and
   dependencies, and the `required-queue-consistency` Gate passes.
6. Foundational dependencies and source-intake requirements are explicit; they
   are not silently folded into unrelated application pages.
7. The first batch has explicit acceptance, rendering, evidence, and Work Spec
   bindings, and the `required-queue-admission` Gate reports it ready.
8. Current audit evidence is available for reuse and invalidation decisions;
   an AuditPlan is created only at its defined lifecycle boundary.

When any condition is missing, first complete the plan or investigation; do not
proceed directly to large-scale creation, moves, or deletion.

## Related

- [[kernel/K00 Standards Control/02 Task Routing|Task Routing]]
- [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
