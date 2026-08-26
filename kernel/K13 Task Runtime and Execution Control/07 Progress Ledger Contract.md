## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|Amendment Log and Controlled Replanning]].
- Next: [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]].

## Progress Ledger

The Progress Ledger owns only whole-task control state:

- task state and the frozen Task Contract: objective, scope, Standards,
  selected Profile, actual loading selection, exclusions, time bounds, and
  completion semantics;
- the canonical Required Queue identity, revisions, fingerprint, initial
  materialization evidence, and receipts consumed by task-state transitions;
- pending and reconciled Guidance, verified Amendments, restart checkpoint, and
  the completion binding selected by the Contract.

Progress contains explicit build and maintenance completion blocks, but only
the block selected by `completion_semantics` may advance. Build uses Terminal
Audit and Terminal Proof; maintenance uses its bounded completion Gate. Neither
block may act as evidence for the other.

Current phase, completed objects, Coverage counts, ready/open/merge views,
batch review, evidence maturity, audit summaries, checks, gaps, questions, and
next dependencies are read-through or derived views of Coverage, Queue,
receipts, and reports. A checkpoint may summarize them but cannot become a
second authority.

Batch membership, order, dependencies, lifecycle, holds, and transition
evidence exist only in the
[[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue]].
Any display cache is generated from that owner and verified by
`required-queue-consistency`; it is never edited independently.

Recorded Guidance statuses are the sole authority for reconciliation progress.
The last reconciled Guidance identity is derived from the longest recorded
prefix that has left `received`, rather than stored as a second cursor.
`guidance_cutoff_id` is different: it is recorded because it freezes Terminal
Audit entry rather than restating status.

Progress is measured by governance and quality state, not cumulative file
count. Profile hub checkboxes and user learning state cannot compute build
progress; page authoring, expression readiness, evidence maturity, and personal
learning remain separate axes.

## Machine-readable Ledger

The registered progress-ledger machine contract is the normative source for
Ledger fields, shapes, and serialization. Task states, completion semantics,
Guidance and Amendment status membership, completion-control states, and the
canonical Ledger identity/fingerprint relationship are owned by
[`runtime-state-model.json`](runtime-state-model.json). The current adopter
value belongs to `.cambium`; an optional human-readable report is derived and
never a basis for reconciliation.

Only registered task-state, Amendment, Queue-replan, Standards-adoption, and
other explicitly coupled transaction capabilities may change Progress. Generic
Guidance prose does not substitute for operational authorization, and a
manually inserted `approved` row has no authority. Every accepted write must
produce an externally verifiable result and preserve evidence needed for
resume and recovery.
