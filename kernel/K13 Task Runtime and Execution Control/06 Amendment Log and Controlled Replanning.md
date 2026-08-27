## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching|Guidance Disposition and Safe Switching]].
- Next: [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|Progress Ledger Contract]].

## Mid-task Guidance And Contract Amendment

### Amendment Record

Important Guidance Events enter the Amendment Log in Progress. The registered
Amendment-record machine contract is the sole normative source for fields,
shapes, and serialization. Closed Guidance/Amendment status membership,
finality, registered operational Amendment identities, and their execution
capability class are owned by
[`runtime-state-model.json`](runtime-state-model.json). This page owns their
semantic boundary.

Each record binds the original Guidance identity and time, a bounded summary
and normalized intent, classification and authority/evidence role, affected
scope and dependencies, conflict analysis, disposition, before/after version
effects, completion impact, status, and verification evidence. Summaries retain
the user's meaning without copying irrelevant or sensitive conversation.

Guidance IDs are task-local, monotonic, and never reused. Status records the
progress from receipt through classification, mapping, execution, and
verification, with explicit branches for clarification, deferral,
supersession, and non-applicability. A status is not execution authority.
Finality also preserves write-back meaning: `verified` is final only after
write-back, while `withdrawn` is final only before any write. The machine
model owns this predicate; prose consumers do not reconstruct it from the
status label alone.

### Versioning Rules

- `contract_version` advances when objective, constraints, acceptance, time,
  exclusions, or pause policy changes.
- `scope_version` advances when in-scope domains, Required objects, or coverage
  disposition changes.
- `queue_revision` advances for Queue structural or verification-contract
  change under K13/08.
- `queue_state_revision` advances only for Queue lifecycle or hold change.
- `standards_version` changes only when Standards adoption selects a different
  upstream Git commit. A Profile-only revision retains it and binds the new
  Profile snapshot and typed contract fingerprint in adoption evidence.

One Guidance item may advance several versions. A research lead not yet
accepted into scope does not advance scope early.

### Operational Amendment Registration

An approved decision is not executable merely because Progress contains an
`approved` row. Operational amendment classes and their plan schemas are owned
by the registered Amendment machine contract. Before any supported replan,
cancellation, routing reconciliation, or other operational change, the
registered amendment-registration capability must:

- bind the exact staged proposal and current Coverage, Queue, and Progress
  identities;
- derive the complete change-class set, affected objects and batches, and
  writer operation rather than accept a prose assertion;
- prove either that the live Task Contract delegates every derived class or
  that fresh explicit user approval covers the complete impact;
- publish one pending, evidence-bound Amendment record without changing task
  state, Queue structure or lifecycle, Coverage, or scope;
- reject unsupported effects and any attempt to use approval text to bypass a
  lifecycle or writer boundary.

Registration and execution must derive the same impact. A changed proposal,
revoked delegation, mismatched approval, drifted state, or different effect set
invalidates registration. At most one unverified operational Amendment is
pending. A valid pending registration may be explicitly withdrawn before any
write; withdrawal preserves its identity and bound evidence and authorizes
nothing.

Registration is a controlled transaction, not a second Gate. The
`required-queue-consistency` Gate owns cross-state validation, and the eventual
writer consumes the exact registration evidence rather than recreating an
approval check. An uncertain registration or execution remains fail-closed and
recoverable and cannot leave authoritative state pointing at absent evidence.

While a row is approved but unwritten, its registration evidence is current
authorization only for the exact live Contract, state, and staged bytes. After
verified write-back, it proves past authorization only; the commit evidence
names what it consumed. Historical registration never authorizes a new change.
Direct edits to a materialized Task Contract, Queue, or Coverage cannot bypass
this path.

### Contract Amendment

The registered Contract-amendment transaction is limited to the Task Contract
authorization fields explicitly opened by the Task Contract machine contract,
including bounded policy exceptions and amendment delegation. It consumes one
confirmed plan, validates the complete after image, and either commits one
verified Amendment with an evidence-bound Contract anchor or changes nothing.

A successful Contract Amendment advances `contract_version` and
`queue_revision` exactly once while preserving scope, batch structure,
lifecycle, and task state. Policy exceptions bind the current effective policy
and must remain within the policy owner's ceilings. Delegation changes use only
the closed change-class vocabulary. A `merge-ready` batch blocks such a revision
because it would strand frozen integration evidence.

A Contract change outside the opened allowlist requires pausing or cancelling
the current task, preserving its runtime history, and carrying the approved
change into a successor task. Extending the allowlist is a governance change,
not an implementation convenience.

Queue replans follow K13/08 and K13/09. Scope or disposition changes,
cancellation, and gap-routing reconciliation consume the exact registered plan
through their registered transaction capabilities. Every path writes back
Progress, preserves terminal history, and proves the declared state result;
editing Queue alone never amends scope.
