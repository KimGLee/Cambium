## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]].
- Next: [[kernel/02 Build Execution/05 Batch Execution|Batch Execution]].

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

The dependency order MUST be produced from the Coverage Ledger's Required Queue. The Progress Ledger keeps at least:

- Active batch.
- Ordered Required Queue.
- Optional backlog.
- Deferred items and re-entry conditions.

`Next dependency` is only the first candidate in the Required Queue and cannot replace the full queue. While the state is `active`, recording `In-progress batch: None` for an extended period is not allowed; after closing a batch, complete reconciliation first, then select the next Required batch.
