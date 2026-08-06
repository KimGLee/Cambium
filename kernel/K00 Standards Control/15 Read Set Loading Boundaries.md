## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/14 Card And Read Set Skeleton|Card And Read Set Skeleton]].
- Next: [[kernel/K00 Standards Control/16 Leaf Module Size Register|Leaf Module Size Register]].

## Default Read Sets

Current Read Sets:

- [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]]: the shared control boundary for all tasks.
- [[kernel/Read Sets/R02 Single Note Authoring Read Set|Single Note Authoring]]: a single canonical note.
- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]: a complete knowledge module.
- [[kernel/Read Sets/R04 Source-driven Expansion Read Set|Source-driven Expansion]]: external sources and community signals.
- [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]]: creation, migration, and review of expression artifacts; the selected profile supplies the concrete artifact binding and may add supplemental gates.
- [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]]: moves, renames, splits, and directory restructuring.
- [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]]: batch, checkpoint, resume, and Terminal Proof.
- [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]]: task completion acceptance and Terminal Audit.
- [[kernel/Read Sets/R09 Standards Governance Read Set|Standards Governance]]: control-plane rule or structure changes.
- [[kernel/Read Sets/R10 Maintenance Run Read Set|Maintenance Run]]: periodic updates and freshness, digesting overdue re-review, watermark deltas, and needs_rereview within the budget envelope.
- [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]]: the canonical Large-scale Pre-execution Gate.
- [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]]: bounded review of changed, invalidated, overdue, sampled, or specialized-invariant scope.
- [[kernel/Read Sets/R13 Corpus Planning Read Set|Corpus Planning]]: maintain corpus topology, capability coverage, and semantic-gap admission without taking over content work, Queue execution, or audit.

Together these thirteen Read Sets name every kernel leaf module. A leaf that no loading boundary names cannot be reached by any routed task, so a leaf enters some boundary in the change that creates it. A leaf consulted only when a stated condition appears belongs in that route's `Triggered` boundary; being reachable by one link from a leaf already inside a boundary is not a substitute.
