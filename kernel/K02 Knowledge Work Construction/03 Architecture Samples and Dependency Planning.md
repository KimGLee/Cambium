## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation|Coverage Reconciliation]].
- Next: [[kernel/K02 Knowledge Work Construction/04 Knowledge Batch Production|Knowledge Batch Production]].

## Phase 2: Architecture And Mapping

- Build the Knowledge Base Overview.
- Build the Competency Matrix.
- Build the Knowledge Gap Tracker.
- Build the prerequisite graph.
- Build the mapping between the selected profile's `Profile Scope` / `Knowledge Spine` and foundation dependencies.
- Mark concepts that are duplicated or have unclear ownership.
- Mark conclusions that need source intake, cross-source synthesis, or re-verification.
- Draw up the directory migration table, and build the expression-artifact mapping via the selected profile's `Expression Layer Entry` and `Routing And Gate Registry` roles.

Before the mapping is complete, do not bulk-delete original content.

## Phase 3: Representative Samples

First select samples for the different note types. The concrete values of the sample types are provided by the `Representative Sample Set` registered by the selected profile; the kernel only requires that the set cover representative types sufficient to test the behavior of the different templates, and does not copy the profile's type list.

Samples are used to verify whether templates are too heavy, too shallow, or produce duplication. Apply in bulk only after the user confirms the samples.

## Phase 4: Dependency-ordered Build

Dependency-ordered vertical slices SHOULD be used, rather than writing all foundations first or jumping straight to the application mainline. The concrete pipeline stage names and order are provided by the selected profile's `Dependency-ordered Build Sequence` role.

Each vertical slice runs from the foundational mechanism through runtime use, the production chain, evaluation, and expression-layer output. Full foundation coverage still advances continuously in the competency matrix; foundations cannot be declared complete merely because the mainline is already runnable.

The actual order MAY be adjusted per user priorities, but dependency gaps and the batches that fill them MUST be recorded.

Coverage records the Required objects, their explicit prerequisites, and their approved batch projection. `Tools/compile_queue.py` uses only those explicit inputs and approved before/after overrides to produce a deterministic Required Queue proposal; it MUST NOT infer dependencies from semantic similarity or backlinks. The canonical Queue then owns the complete batch order, frozen manifests, and dependency graph as defined by [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]].

The Progress Ledger records only the accepted Queue path, revisions, and fingerprint; any `next dependency`, ready list, active list, or merge queue shown there is a derived view that MUST be reproducible from the Queue. A derived first candidate cannot replace the full Queue. After closing a batch, reconcile Coverage and Queue before asking `check_queue.py --require-ready <batch-id>` to admit the next batch.
