## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]].
- Next: [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]].

## Purpose

This module owns the bound a maintenance run declares before it starts, and what becomes of the candidates that bound leaves out. It is read at maintenance-run start, and by any rule that converts other work into maintenance-run budget. It decides how much one run may take on; when that run may be called complete is decided by [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|Maintenance Completion]].

## Maintenance Run Envelope

When a maintenance run starts, a budget envelope MUST be declared, choosing one of three: N pages, N batches, or N hours.

- Candidate list = the complete `knowledge-freshness` candidate set ∪ the
  maintenance-watermark delta ∪ re-review marks ∪ the registered duplicate,
  vocabulary, and language candidate sets. The freshness member is every
  candidate outcome, not an overdue-only projection; its semantic classes and
  closed-world pass rule are owned by
  [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|K08/05]].
- Fuse duplicate object paths before selection, retaining every contributing source kind. The fused list is ordered by priority, then canonical object path and stable candidate ID, and only then truncated to the budget. A producer's display order, age value, or candidate subtype cannot create a second budget order.
- Candidates arising from changed pages within a batch are adjudicated in that batch (the author is present; lowest cost); candidates from existing pages always enter the pool, and neither block any gate nor surface as to-dos.
- A candidate not selected by the budget for 3 consecutive maintenance runs is automatically demoted to log-only: the record is kept, but it does not count as a to-do, does not appear in gate output, and does not count toward any completion determination; it re-enters the pool when hit again by a new scan.
- At maintenance-run start, output the deferred age distribution; items lingering more than 3 runs MUST be explicitly dispositioned: demotion, retirement, or a recorded retention rationale. "Deferred does not constitute a gap" is retained, but is not a basis for skipping checks.
- For retirement of high-in-degree pages, the incoming-link retargeting work counts against the maintenance-run budget as pages, converted at "retargeted links ÷ 6".
- The truncated portion is recorded as deferred in the Ledger and does not constitute a gap.
- Stopping points are batch boundaries; do not stop mid-batch.

For persistent execution, Coverage owns the complete fused candidate state and the closed budget manifest freezes the same ordered records. Each object-path record identifies its source kinds, priority, prior/current consecutive deferral age, selected/deferred partition, re-entry status, and any disposition/reason. Candidate IDs are partitioned exactly once; the derived deferred count cannot replace that set. Queue manifests equal only the selected object set, while deferred candidates remain outside current Required work. The maintenance completion gate checks these set equalities and age rules. It does not decide whether the four source processes made correct semantic judgments; that remains part of constructing and reviewing the candidate list. A later run may age this state only from the latest prior maintenance gate for the same Standards version and selected Profile that was persisted and consumed by exactly one canonical completed-maintenance task transition. Omitting that predecessor or naming an older eligible gate is invalid; neither action may reset deferral age.

## Related

- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
