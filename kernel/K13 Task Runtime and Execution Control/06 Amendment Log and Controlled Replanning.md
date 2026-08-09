## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching|Guidance Disposition and Safe Switching]].
- Next: [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|Progress Ledger Contract]].

## Mid-task Guidance And Contract Amendment

### Amendment Record

Important Guidance Events MUST enter the Amendment Log of the Progress Ledger. The record includes at least:

```text
guidance_id
received_at
message_reference
raw_guidance_summary
normalized_intent
guidance_types
authority_scope
evidence_role
affected_scope
affected_pages
affected_batches
dependency_impact
conflict_analysis
disposition
contract_version_before / after
scope_version_before / after
queue_revision_before / after
queue_state_revision_before / after
standards_version_before / after
completion_gate_impact
status
verification_evidence
```

`raw_guidance_summary` SHOULD preserve the original meaning but not copy irrelevant conversation or sensitive information. `normalized_intent` states how the executor understood the requirement. `evidence_role` distinguishes user authority, research signal, source lead, first-party context, and externally verified claim.

`guidance_id` uses a task-local, monotonically increasing, never-reused identifier, e.g. `G-001`, `G-002`. Only then can checkpoints and the Terminal Audit use `last_reconciled_guidance_id` and `guidance_cutoff_id` to establish explicit boundaries.

Recommended guidance status values:

```text
received
 -> classified
 -> mapped
 -> in-progress
 -> verified

classified -> clarification-required
classified / mapped -> deferred
received / classified / mapped -> superseded
classified -> not-applicable
```

### Versioning Rules

- `contract_version`: bump when the objective, constraints, acceptance, time, exclusions, or pause policy changes.
- `scope_version`: bump when in-scope domains, Required objects, or coverage disposition change.
- `queue_revision`: bump for a structural Queue change per [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]].
- `queue_state_revision`: bump only for a Queue lifecycle/hold change per K13/08.
- `standards_version`: bump only for a reusable governance rule with explicit user authorization to modify the Standards.

One guidance MAY bump multiple versions. When only a research lead is added and it has not yet been accepted into scope, do not bump the scope version early.

### Operational Amendment Registration

An approved decision is not executable merely because an Agent can append an
`approved` row to Progress. The three operational forms supported by the
current runtime -- `queue-replan`, `scope-replan`, and `cancel-batch` -- MUST
first be registered by `Tools/register_amendment.py`. That writer consumes the
exact staged plan or Coverage proposal, derives rather than guesses the
affected structure, compare-and-swaps all three canonical state fingerprints,
and appends only the pending Progress row plus its
`registration_receipt`. Registration changes no task state, Queue revision,
Queue lifecycle, Coverage bytes, or scope version.

The caller supplies one explicit `approval_reference`; it identifies the
approval inside the local trust domain but is not a cryptographic signature.
Only the integrator may apply registration, and only one operational Amendment
may be pending at a time. Directly inserting or editing an executable pending
row is forbidden.

A pending registration whose execution can no longer validate — its planned
final state fails the deterministic checks, or the approval is rescinded — is
retired through the same writer's withdrawal action, never by editing the row:
the integrator supplies a nonempty reason, the writer publishes an append-only
withdrawal receipt naming the registration receipt, and the row's status
becomes `withdrawn` with write-back still false. A withdrawn registration
authorizes nothing; its bound plan and proposal bytes remain verified
immutable evidence, and its amendment ID is never reused. Without this action
the one-pending rule would let a single mis-registered Amendment wedge every
future operational Amendment forever.

Registration is a controlled writer transaction, not a second Gate ID. The
existing `required-queue-consistency` control owns deterministic validation of
the pending authorization and its cross-state bindings; each downstream writer
then consumes the exact registration receipt instead of recreating that check.

The writer publishes the append-only receipt before replacing Progress, so an
interruption cannot leave canonical Progress pointing at absent evidence. An
unreferenced registration receipt has no authority. If publication is
interrupted, the shared writer lock retains the before/planned-after
fingerprints and receipt identity for reconciliation. A verified execution
commit MUST name that receipt, start from the registration's exact three-state
after-image, and have a timestamp no earlier than registration.

Receipt lifetime has two distinct meanings. While the row is
`approved / writeback_done=false`, its registration receipt is current
authorization and MUST resolve through the Standards-adoption-filtered current
receipt catalog against the live Contract, Coverage, Queue, revisions, and
staged artifact bytes. After the registered operation is committed and the row
becomes `verified / writeback_done=true`, that registration receipt proves the
past authorization only; validators resolve it from immutable history, while
the transaction commit receipt names the registration it consumed. Historical
registration evidence never authorizes a new replan or cancellation.

The baseline transaction writer covers scope/disposition replans and
cancellation. It MUST NOT be bypassed by directly editing a materialized Task
Contract. If a host has no guarded writer for a non-scope Contract change, the
operator MUST pause or cancel the current task, preserve its runtime history,
and carry the approved change into a successor task.

Queue edits follow K13/08. A same-scope replan stages a full Coverage proposal under `.cambium/deltas/replans/`; after registration, `compile_queue.py --apply-replan` binds it, its diff, the registered Amendment, the consumed registration receipt, and all three state fingerprints before writing state. Scope/disposition changes, including cancellation, register the exact `amendment_plan` before using `apply_amendment.py`. Both paths write back Progress and preserve terminal history; editing Queue alone never amends scope.
