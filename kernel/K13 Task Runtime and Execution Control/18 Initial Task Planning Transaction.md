## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|Escalation Policy]].
- Next: [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|Card Context Activation and Read-back Delivery]].

## Purpose And Boundary

This module owns only the transaction that turns empty task runtime into a planned task. It defines no Task Contract, Coverage, Queue, Card, or Read Set field. K13/02 owns Task Contract semantics, K02/01 owns Coverage, K13/08 owns Required Queue, and the independent routing/loading mechanism owns resolution of the task's loading selection.

The transaction writes one confirmed Task Contract and the planning-only Coverage inventory together or writes neither. It cannot infer that a repository has work merely because files, templates, Cards, Read Sets, or candidate Coverage entries exist, and it does not establish current page state.

## What The Plan Supplies And What It May Never Infer

The registered initial-task-plan machine contract is the sole normative source for plan fields, shapes, sentinels, and serialization. A confirmed plan binds:

- the complete Task Contract, including the user-confirmed objective, scope,
  authority, completion semantics, and resolved loading selection;
- the complete planned-work inventory and batch specifications, containing
  object identity, ownership, disposition and Queue assignment but no current
  authoring status, property state, Gate evidence or Receipt;
- an approval reference for every semantic decision supplied by a person.

The transaction may deterministically validate and normalize those confirmed values but cannot decide which objects are Required, their semantic owners, priority, prerequisites, batch assignment, route selection, Profile policy, or current page status. An object need not already exist as a file to be planned as Required. Pre-existing page metadata and old runtime evidence are outside this transaction's inputs and cannot be copied into the new runtime by it.

## Where The Transaction Stops

The initial planning transaction writes the Task Contract and planning-only Coverage records. It does not write or own the Required Queue and does not project page metadata. Before first Queue materialization those are confirmed adopter inputs; Queue compilation is the separate authority boundary owned by K13/09. Current Coverage state for one manifest is first materialized by the queued-to-open transition owned by K13/10.

The resulting unmaterialized state may validly have Coverage batch projections while the Queue is still empty. The transaction result must make that state explicit and identify Queue materialization as the next owned capability. A generic success result that hides this remaining boundary is insufficient.

## External Transaction Contract

The registered initial-task-planning transaction must:

- consume one current confirmed plan and an empty, valid task-runtime before
  image;
- reject unresolved references, unfilled sentinels, current-state drift, a
  different task identity, or an after image that fails cross-state validation;
- publish the complete Task Contract and planning-only Coverage after images
  together with one immutable transaction result, or preserve the before
  image;
- make interruption fail closed and recoverable without losing the confirmed
  plan or inventing a commit;
- emit no Gate claim of its own; existing consistency, admission, large-scale,
  and planning Gates consume its resulting state at their ordinary boundaries.

Applying the same plan after a verified commit is a no-op refusal because state has moved. A different plan over planned runtime is an Amendment and replan, not initialization. This prevents initialization from becoming a path around the frozen Contract.

## Related

- [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]]
- [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|Standards Adoption State Transaction]]
