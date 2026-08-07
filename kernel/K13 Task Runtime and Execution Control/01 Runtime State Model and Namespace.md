## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Next: [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|Task Contract Binding and Time Semantics]].

## Runtime State Namespace

Persistent, resumable, multi-batch, R07, or R11 work uses:

```text
.cambium/
  state/{coverage_ledger.yaml,required_queue.yaml,progress_ledger.yaml}
  work_specs/  deltas/  receipts/  reports/  tmp/
```

State, Work Specs, deltas, and receipts are durable; `deltas/` also contains
restricted-YAML controlled-operation plans such as active-task Standards
adoption. Reports are derived, and
managed paths stay repository-contained. `work_specs/` contains only immutable
restricted-YAML contracts for complex batches, each bound by path and SHA-256 from
Coverage `batch_specs` and the compiled Required Queue. It is not a second
Queue, task ledger, or general documentation directory. Initialize only when
`.cambium/` is absent;
otherwise run `check_queue.py --resume-status` before any write and follow its
machine `next_action`. Bounded work needs no empty Queue. A lock remains until
the state SHAs, receipts, deltas/archive moves, and absence of a live writer
reconcile. New tasks archive rather than repurpose existing state.

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

## Control Accretion Decision

Previously, scattered K02 prose and hand-maintained Progress batch lists owned
this risk but could not prevent cross-state drift. [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]] is the sole rule
owner and `check_queue.py` the sole gate. Progress therefore no longer owns a
duplicate `batches[]`, active list, merge queue, or batch receipts; it keeps
only the accepted Queue reference and whole-task state.
