## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]].
- Next: [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]].

## Purpose

This module owns the bound a maintenance run declares before it starts, and what becomes of the candidates that bound leaves out. It is read at maintenance-run start, and by any rule that converts other work into maintenance-run budget. It decides how much one run may take on; when that run may be called complete is decided by [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|Maintenance Completion]].

## Maintenance Run Envelope

When a maintenance run starts, a budget envelope MUST be declared, choosing one of three: N pages, N batches, or N hours.

- Candidate list = the `check_freshness` overdue list ∪ the watermark delta ∪ `needs_rereview` marks ∪ the candidates pool (duplicate / vocab / language); sort by priority, then truncate to the budget.
- Candidates arising from changed pages within a batch are adjudicated in that batch (the author is present; lowest cost); candidates from existing pages always enter the pool, and neither block any gate nor surface as to-dos.
- A candidate not selected by the budget for 3 consecutive maintenance runs is automatically demoted to log-only: the record is kept, but it does not count as a to-do, does not appear in gate output, and does not count toward any completion determination; it re-enters the pool when hit again by a new scan.
- At maintenance-run start, output the deferred age distribution; items lingering more than 3 runs MUST be explicitly dispositioned: demotion, retirement, or a recorded retention rationale. "Deferred does not constitute a gap" is retained, but is not a basis for skipping checks.
- For retirement of high-in-degree pages, the incoming-link retargeting work counts against the maintenance-run budget as pages, converted at "retargeted links ÷ 6".
- The truncated portion is recorded as deferred in the Ledger and does not constitute a gap.
- Stopping points are batch boundaries; do not stop mid-batch.

## Related

- [[kernel/Read Sets/R10 Maintenance Run Read Set|Maintenance Run Read Set]]
- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
