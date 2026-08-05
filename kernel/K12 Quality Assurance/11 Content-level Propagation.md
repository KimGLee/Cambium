## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]].
- Next: [[kernel/K12 Quality Assurance/12 Substantive Correctness Review|Substantive Correctness Review]].

## Purpose

This module owns the mark an author leaves on downstream notes when a mechanism section changes, and the route by which that mark reaches a later maintenance run. The mark defers re-reading; it does not invalidate a receipt and emits none of its own, so it cannot by itself fail a gate. Receipt invalidation is decided by [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Content-level Propagation

When a note's mechanism sections (Definition, Mechanism, formulas, core conclusions) are substantively modified, the author MUST mark the direct downstream notes `needs_rereview` along the semantic dependency edges defined in [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Dependency Invalidation|Dependency Invalidation]] (prerequisite, claim-evidence), and record this into the Coverage Ledger via the batch delta's `open_gaps_added` (type: rereview) — under concurrency the author does not write the Ledger directly ([[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|K13/10]] write partition). The marks flow into the maintenance run's candidate pool to be absorbed within budget; on-the-spot handling is not required. The same page is marked into the pool only once per maintenance run cycle. The re-review action is re-reading whether the downstream reasoning still holds, not re-running mechanical checks.

## Related

- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]
- [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
