## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/12 Control Registry|Control Registry]].
- Next: [[kernel/K00 Standards Control/14 Card And Read Set Skeleton|Card And Read Set Skeleton]].

## Purpose And Ownership

This page is the sole owner of runtime-state discovery and recovery before any
write, and of the admission gate for large-scale creation, moves, or deletion.
[[kernel/K00 Standards Control/02 Task Routing|Task Routing]] only selects the
applicable Rxx route; K00/13 is a control leaf, not an R13 route.

## Runtime Startup Gate

Before any task writes content or control state, inspect the repository root
for an existing `.cambium/` namespace. This discovery step is universal even
when the new request initially appears bounded; an earlier persistent task may
still be paused, interrupted, or awaiting integration:

- If `.cambium/` is absent, continue normal routing. Only an authorized
  persistent, resumable, or multi-batch task MAY initialize it once with
  `Tools/init_state.py` after its task, Standards, scope, profile identity, and
  explicit `completion_semantics: build|maintenance` are known; a bounded task
  does not create empty runtime state.
- If `.cambium/` exists, the first state action MUST be
  `python3 Tools/check_queue.py . --resume-status`. The operator reads the
  recorded task state, completion semantics and block, checkpoint, Queue
  revisions/fingerprint, `open`/`merge-ready` items, pending deltas, holds, and
  writer-lock evidence before deciding whether the existing task can resume.
- A new task MUST NOT initialize over, repurpose, or silently reset an existing
  namespace. Even a completed or cancelled task remains durable history until
  an explicit archive or rollover procedure handles it; this Standard does not
  claim that current tools perform that procedure automatically.
- A writer lock may identify an active writer or an interrupted write. It MUST
  NOT be deleted merely because it looks stale. First establish that no writer
  remains, then reconcile the three state files, revisions/fingerprint,
  receipts, and pending deltas. Unreliable or inconsistent state fails closed.

The startup gate discovers control state; it does not authorize the content
work itself. A bounded task may proceed without creating runtime state only
when the namespace is absent. When it is present, the recorded task is
reconciled before any route writes, regardless of the apparent size of the new
request.

## Large-scale Pre-execution Gate

Large-scale creation, moves, or deletion selects R11 Large-scale Work Admission
and MAY begin only after the following conditions are met:

1. `K00` and Core Bootstrap have been read.
2. Task-specific Read Sets, triggered modules, and gate modules have been resolved per the [[kernel/K00 Standards Control/02 Task Routing#Task Routing Table|Task Routing Table]].
3. Contract / scope / Standards version / selected profile manifest, the loaded set (selected Rxx route IDs and Runtime Card paths, any combined namespaced profile route, and every Read Set or leaf path actually read back), the target scope, the excluded scope, and the latest user requirements have been recorded.
4. `minimum_run_until`, `checkpoint_at`, `hard_stop_at`, and the Completion Gate have been made explicit; fields not provided are explicitly left empty.
5. The Runtime Startup Gate has passed. The `.cambium/` namespace was initialized only if absent; otherwise the existing task was inspected and legitimately resumed. Coverage, Queue, and Progress agree on task, scope, Standards version, and selected profile manifest.
6. The Coverage Ledger has been created or refreshed and reconciled against the file system and exclusions; ownership, incoming links, and user modifications have been inventoried.
7. The selected profile's `Corpus Planning` slot uses `applicability.state: configured`; its Global Map, Capability Matrix, and Gap Register bindings exist, reflect the admitted scope, and `python3 Tools/check_corpus_plan.py .` passes. R11 consumes this condition; R13 owns creating or reconciling the artifacts.
8. The Required Queue has been compiled from explicit Coverage assignments and dependencies, and `python3 Tools/check_queue.py .` passes against the current revisions and fingerprint. A missing or empty Queue caused by a wrong path is not a pass.
9. Foundational knowledge dependencies have been identified; all prerequisite content MUST NOT be crammed into the application mainline pages declared by the selected `Profile Scope`.
10. Source-driven tasks have established a source inventory and a claim extraction plan.
11. The initial batch's completion conditions, `rendering_mode`, deterministic verification commands, and the objective trigger and unresolved question for any visual escalation have been defined. A complex initial batch binds a current Work Spec; a simple one explicitly binds null/null. `python3 Tools/check_queue.py . --require-ready <batch-id>` identifies it as activatable before execution begins.
12. The latest Audit Receipt Register has been loaded ([[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]]); at start of work only the Register is loaded, no AuditPlan is built — the AuditPlan is built once before batch close.

When any condition is missing, first complete the plan or investigation; do not
proceed directly to large-scale creation, moves, or deletion.

## Related

- [[kernel/K00 Standards Control/02 Task Routing|Task Routing]]
- [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01 Core Bootstrap]]
- [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|R11 Large-scale Work Admission]]
- [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Corpus Planning]]
- [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
