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
```

### Versioning Rules

- `contract_version`: bump when the objective, constraints, acceptance, time, exclusions, or pause policy changes.
- `scope_version`: bump when in-scope domains, Required objects, or coverage disposition change.
- `queue_revision`: bump for a structural Queue change per [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]].
- `queue_state_revision`: bump only for a Queue lifecycle/hold change per K13/08.
- `standards_version`: bump only for a reusable governance rule with explicit user authorization to modify the Standards.

One guidance MAY bump multiple versions. When only a research lead is added and it has not yet been accepted into scope, do not bump the scope version early.

The baseline transaction writer covers scope/disposition replans and
cancellation. It MUST NOT be bypassed by directly editing a materialized Task
Contract. If a host has no guarded writer for a non-scope Contract change, the
operator MUST pause or cancel the current task, preserve its runtime history,
and carry the approved change into a successor task.

Queue edits follow K13/08. A same-scope replan stages a full Coverage proposal under `.cambium/deltas/replans/`; `compile_queue.py --apply-replan` binds it, its diff, the approved Amendment, and all three state fingerprints before writing state. Scope/disposition changes, including cancellation, use `apply_amendment.py`. Both paths write back Progress and preserve terminal history; editing Queue alone never amends scope.
