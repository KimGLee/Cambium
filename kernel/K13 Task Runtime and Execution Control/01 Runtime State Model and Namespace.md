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

## Control Accretion Decision

Previously, scattered K02 prose and hand-maintained Progress batch lists owned
this risk but could not prevent cross-state drift. [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]] is the sole rule
owner and `check_queue.py` the sole gate. Progress therefore no longer owns a
duplicate `batches[]`, active list, merge queue, or batch receipts; it keeps
only the accepted Queue reference and whole-task state.
