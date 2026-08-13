## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|Escalation Policy]].

## Purpose And Boundary

This module owns only the transaction that turns an empty runtime namespace
into a planned one. It defines no field: the Task Contract is
[[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|K13/02]]'s,
the Coverage record
[[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|K02/01]]'s,
the Required Queue
[[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]]'s.
What is owned here is that those first values are written together, from one
confirmed input, or not at all.

`Tools/init_state.py` publishes the namespace and infers nothing: the Contract's
five selection fields are empty, Coverage holds no object, the Queue is empty.
`Tools/apply_task_plan.py` is the sole writer of that edge. It consumes one
restricted-YAML plan under `.cambium/deltas/task-plans/<plan-id>.yaml`, defaults
to dry run, and writes only with `--apply`.

## What The Plan Supplies And What It May Never Infer

The plan carries the complete Task Contract and initial Coverage inventory,
including `batch_specs`. Every value is one a person already decided;
`approval_reference` names where.

Exactly two derivations are permitted, both deterministic and both owned
elsewhere: the Required Queue from the confirmed Coverage, and the Card, Read
Set, and module closure from the confirmed route IDs. The second is not a
convenience: selecting R01 alone closes over every other route and past a
hundred modules, so demanding those lists by hand collects a declaration nobody
checked, and
[[kernel/K00 Standards Control/15 Read Set Loading Boundaries|K00/15]] places
that completeness judgment on a plan being admitted because it is still
writable there. A path the plan does list is kept and closed over; that is how
a profile supplemental Read Set is selected, having no registry of its own.

Which objects are Required, who owns each, its priority, prerequisites, and
batch assignment are answers, not derivations. `init_state.py` reports `no work
inferred` for that reason; this transaction does not weaken it.

A Coverage record for an object that does not exist yet is normal: K02/01
requires one for every Required object, and a writer that demanded the file
first could never plan unwritten work.

## Where The Transaction Stops

The writer writes the Task Contract and Coverage. It does not write the Queue.

Before the first Queue materialization both are adopter inputs; after it, every
canonical write must be the after-image of a qualified writer's receipt. The
Queue crossing that line is what materialization means, and
[[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views|K13/09]]'s
compiler already owns it, so this transaction stops at the boundary rather than
becoming a second Queue authority.

The state it leaves — Coverage naming batches the Queue does not yet carry — is
the unmaterialized runtime, not a broken one, and running the compiler both
completes it and resumes an interruption in it. The writer MUST report that the
Queue is unmaterialized and name the command that materializes it; a run
reporting only success invites the operator to stop one step early.

## Guarded Write Protocol

Before writing anything, the tool reparses the plan and all three state objects
and fails closed on any of four classes: a plan that is not the closed shape or
still carries an unfilled sentinel; a runtime that has moved, is not the empty
skeleton, names a different task, or does not currently validate; a route or
Coverage selection that does not resolve; and a proposed after-image that fails
`check_queue`.

It then takes the shared state-writer lock, re-verifies the before images under
it, replaces Coverage and Progress, and appends one commit receipt to
`.cambium/receipts/task-plans.jsonl`. A failure after the first replacement
restores the before images and records an abort.

The receipt records a transaction, not a gate, and claims no Gate ID. The state
it writes is consumed by `required-queue-consistency`,
`required-queue-admission`, `large-scale-execution-admission`, and where
applicable `corpus-plan-structure` — all of which already exist. A gate with no
lifecycle boundary to guard would be ceremony.

## Applying It Twice

A run interrupted before commit restores the before images, so the same plan
applies cleanly on retry. Once it has committed, its own compare-and-swap
declines it: the state has moved. A *different* plan applied over an
already-planned runtime is refused: it would be a scope change routed around
[[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|Amendment]]
and replan, where later change belongs. This is not a policy laid on top of the
machine — once the Queue is materialized the Contract fingerprint is frozen and
any later mutation already fails closed. The refusal only declines to create a
path around that.

## Control Accretion Decision

Per [[kernel/K00 Standards Control/03 Standards Governance#Control Accretion Rule|Control Accretion Rule]].

- **Which layer owned this risk, and why insufficient?** None did. The
  documented path was to hand-edit canonical runtime state, which
  [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01]] forbids and which records
  nothing about what was confirmed.
- **Which layer owns the canonical gate?** None is added; the four gates named
  above consume this transaction's output unchanged.
- **Is the superseded layer deleted?** Yes. The instruction to fill the Coverage
  Ledger by hand is removed wherever it appeared.

## Related

- [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]]
- [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|Standards Adoption State Transaction]]
