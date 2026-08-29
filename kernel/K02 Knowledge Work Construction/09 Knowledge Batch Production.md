## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning|Architecture Samples and Dependency Planning]].
- Next: [[kernel/K02 Knowledge Work Construction/10 Existing Changes and Migration Safety|Existing Changes and Migration Safety]].

## Batch Policy

Each batch SHOULD be a small module that can be accepted independently, not an arbitrary number of files. Its identity, frozen manifest, dependencies, execution mode, lifecycle, and hold state are owned by [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]]; this page owns how an admitted batch executes.

A batch completes at least:

1. Canonical notes.
2. This batch's delta written out: worker-owned page status and evidence may
   enter Coverage through the delta; next-batch updates and maintenance
   watermark advancement remain explicit integrator work. Queue-owned
   disposition, ownership, routing, priority, tier, type, prerequisites, and
   deferral fields are forbidden in a worker delta. The
   [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract#Progress Ledger]]
   Queue reference and the canonical maintenance watermark are reconciled by
   their registered integrator capabilities.

The batch-close acceptance checklist is governed by [[kernel/K12 Quality Assurance/14 Batch Review#Batch Review|K12/14 Batch Review]]; in-batch items are completed before `merge-ready`, and global items are verified at serial merge.

Batch size is tiered by the dominant tier: tier S ≤24 pages, tier M ≤10 pages, tier L ≤6 pages; a mixed batch follows the cap of the highest tier among them. 24 / 10 / 6 are kernel defaults; the selected profile MAY explicitly override them in the manifest, and the resolved caps MUST be loaded and recorded at runtime.

Bulk-creating only file names and headings and then marking the whole batch complete is not allowed.

## Source-driven Expansion Batch

When expanding the knowledge base from primary or vendor sources, papers, postmortems, or community discussions, the batch MUST follow the [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]: a source-driven batch MUST run all stages (Stage 1–10) of the [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] in full.

A source batch MAY produce zero, one, or multiple canonical notes.
