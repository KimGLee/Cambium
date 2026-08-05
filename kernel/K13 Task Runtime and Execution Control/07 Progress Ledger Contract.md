## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|Amendment Log and Controlled Replanning]].
- Next: [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]].

## Progress Ledger

The Progress Ledger owns only whole-task control state:

- Task state and Task Contract: objective/contract/scope/Standards/profile identity, exclusions, loaded routes/readbacks, time bounds, and the explicit `completion_semantics: build|maintenance` predicate.
- The canonical Required Queue path, both accepted revisions, Queue SHA-256, immutable initial Queue receipt, and the receipts consumed by task-state transitions.
- Pending/reconciled Guidance, verified Amendments, the last restart checkpoint, and the applicable completion binding.

Progress contains both completion blocks so the chosen path is machine
explicit, but they are mutually exclusive. A build contract activates
`terminal_audit` and holds `maintenance_completion` at `not-applicable` with
null receipt fields. A maintenance contract holds `terminal_audit` at
`not-applicable` and advances `maintenance_completion` through `pending`,
`passed`, or `invalidated`; that block binds `completion_gate_receipt`,
`budget_manifest_receipt`, `ledger_advance_receipt`, and
`watermark_advance_receipt`.
Neither block may act as evidence for the other completion semantics.

Current phase, completed objects, Coverage counts, ready/open/merge status, batch review, evidence maturity, audit/reuse/invalidation summaries, checks, gaps, questions, and next dependency are read-through or derived views of Coverage, Queue, receipts, and reports. A checkpoint MAY summarize them, but Progress MUST NOT become a second authority for them.

Batch membership, order, dependencies, lifecycle, holds, and transition receipts exist only in the [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue]]. Any display cache is explicitly derived, regenerated from the Queue, and checked by `Tools/check_queue.py`; it is never independently edited.

Progress is measured by quality state, not by the cumulative count of created files.

The Progress Ledger cannot use profile-registered hub checkboxes or the user's `learning_status` to compute build progress. Page writing completion, Expression Layer coverage and readiness, evidence maturity, and personal learning progress MUST be summarized separately.

## Machine-readable Ledger

The canonical form of the Progress Ledger is YAML; the schema is at `Tools/schemas/progress_ledger.template.yaml`, and the runtime path is `.cambium/state/progress_ledger.yaml`. Only the restricted subset syntax declared in the template header comment is allowed. A markdown prose view is optional, derived from the YAML, and not a basis for reconciliation. When resuming a task, load the YAML Ledger directly together with the Required Queue and Coverage Ledger instead of re-reading a prose checkpoint.
