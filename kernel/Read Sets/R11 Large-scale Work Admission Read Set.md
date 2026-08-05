---
type: read-set
route_id: R11
---

## Purpose

Used only to admit large-scale creation, moves, or deletion to execution. It packages the canonical Large-scale Pre-execution Gate; it does not authorize authoring, source promotion, expression work, migration, or long-running execution by itself.

## Start

First load [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01 Core Bootstrap]], then read:

- [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate|Large-scale Pre-execution Gate]]
- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Task Contract Decisions|Task Contract Decisions]]
- [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|Task Contract Binding and Time Semantics]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|Global Map Contract]]
- [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|Capability Matrix Contract]]
- [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|Gap Register Contract]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Incremental Audit Planning|Incremental Audit Planning]]

Also load the route for the actual work. R11 never replaces that route.

## Triggered

- Module construction: combine [[kernel/Read Sets/R03 Module Build Read Set|R03 Module Build]].
- Source-driven work: combine [[kernel/Read Sets/R04 Source-driven Expansion Read Set|R04 Source-driven Expansion]].
- Expression-layer work: combine [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]] and its profile binding.
- Moves, splits, merges, or deletion: combine [[kernel/Read Sets/R06 Migration and Refactor Read Set|R06 Migration and Refactor]].
- Multiple batches, checkpointing, or resume: combine [[kernel/Read Sets/R07 Long-running Execution Read Set|R07 Long-running Execution]].
- Missing or stale Global Map, Capability Matrix, or Gap Register: combine [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Corpus Planning]] and reconcile them before admission; R11 consumes their gate but does not author them.
- A visual escalation proposal: read [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]] before registering its objective trigger and unresolved question.

## Admission Gate

Every item in the canonical [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate|Large-scale Pre-execution Gate]] MUST be resolved. State is initialized only when `.cambium/` is absent; if it exists, `python3 Tools/check_queue.py . --resume-status` is the first state action and the recorded task must be reconciled rather than overwritten. The configured Corpus Planning artifacts pass `check_corpus_plan.py`; the Queue manifest and Coverage projection agree; and `check_queue.py .` plus `--require-ready <initial-batch-id>` pass before execution. At task start only the Audit Receipt Register is loaded; an AuditPlan is built exactly once before batch close. When any admission condition is missing, remain in planning or investigation.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction]]
- [[kernel/K13 Task Runtime and Execution Control Standard|Task Runtime and Execution Control]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
