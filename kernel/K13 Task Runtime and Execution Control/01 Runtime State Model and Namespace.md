## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Next: [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|Task Contract Binding and Time Semantics]].

## Runtime State Namespace

Persistent or resumable work uses adopter-owned runtime state containing these
logical classes:

- adopter Standards and Profile identity;
- canonical Coverage, Required Queue, and Progress state;
- immutable Work Specifications and controlled-operation plans;
- append-only execution, transition, review, and recovery evidence;
- derived reports and explicitly temporary transaction material.

[`runtime-state-model.json`](runtime-state-model.json) is the sole machine
owner of the canonical Ledger identities and their fingerprint-field
relationship. It does not own their adopter-specific paths or current values.

The `.cambium` component owns the physical namespace, file layout, and current
values. Kernel owns only the classes, authority separation, durability, and
observable lifecycle invariants. Governance identity may exist before any task
runtime. Work Specs, plans, state, and evidence are durable; reports are
derived. A Work Spec is not a second Queue or general documentation store.

Task state is initialized only when no task runtime exists. Existing runtime is
resumed and reconciled through the registered runtime-startup capability before
any write; it is never overwritten as a shortcut. Bounded work needs no empty
Queue. An uncertain transaction remains non-authorizing until state and
evidence reconcile. A new task preserves rather than repurposes prior runtime
history.

## Execution Roles

The state above is written by execution contexts, and the three names this
standard uses for them are defined here once:

- An **agent** is an execution context assigned to work. It is not a Cambium
  work unit and holds no authority of its own: the batch is the unit, and the
  Queue is its owner. One agent MAY execute several batches in sequence, and
  isolated agents MAY execute disjoint batches concurrently.
- A **subagent** is a child execution context created by a runtime. It is not a
  separate work unit or authority class, and MAY act as a worker, a researcher,
  or the independent reviewer. Qualifying as that reviewer is the narrowest of
  those roles and requires exactly what [[kernel/K12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]] states; an
  ordinary child context does not qualify by being a subagent.
- The **integrator** is the single logical role holding the control plane. It
  is a role, not a process: a runtime MAY place it in any context, but only one
  holds it at a time. What it exclusively controls, and the single-threaded
  execution of that control plane, are stated by [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration#Concurrent Batches|Concurrent Batches]]; this page names
  the role and does not restate that enumeration.

This page names the roles. It does not define an Agent runtime implementation,
which [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|K13/02]] places outside this standard.

## Authority Boundary

[[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]]
is the sole semantic owner of batch structure and lifecycle.
`required-queue-consistency` is the sole cross-state Gate. Progress keeps only
whole-task state and the accepted Queue reference; it does not own a duplicate
batch list, active list, merge queue, or batch receipts.
