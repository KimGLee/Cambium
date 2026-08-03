## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/K02 Build Execution/05 Batch Execution|Batch Execution]].
- Next: [[kernel/K02 Build Execution/07 Completion and Handoff|Completion and Handoff]].

## Existing Changes

- By default, all existing modifications belong to the user.
- Do not roll back changes unrelated to the current task.
- When user modifications exist in the same file, understand them first and work on top of them.
- Request a user decision only when a modification makes the task unable to continue.
- Do not use destructive resets or bulk-overwrite strategies.

## Migration Safety

When moving or splitting files:

1. First identify the canonical target.
2. Inventory incoming and outgoing links.
3. Create and verify the new pages.
4. Update references.
5. Confirm the content is fully migrated.
6. Only then delete duplicate content or old files.
7. The knowledge-base-wide check is covered by the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]] of the batch in which the migration closes.

Deleting first and rewriting afterwards MUST NOT be done.

## Interruption And Resume

Before a task is interrupted, the task state MUST be updated to `paused` or `blocked` and a checkpoint MUST be written. The checkpoint includes at least:

- The current contract, scope, queue, active batches, and standards version.
- Each active batch's state (`active` / `merge-ready`), the merge queue, deltas written out but not yet applied, accepted results, and unverified modifications.
- The most recent QA result.
- The unfinished Required items in the Coverage Ledger.
- Guidance not yet classified, mapped, or verified.
- Last reconciled guidance ID and unresolved Amendment Records.
- Modified files.
- The next precise action, not a vague "keep improving".
- The blocking reason, attempted approaches, and other work that can still proceed.

After an interruption, the task SHOULD resume from the Progress Ledger, Coverage Ledger, and current file state instead of starting over.

On resume, first check:

- Whether the user's latest requirements change the objective.
- Whether the last state was `paused`, `blocked`, or already has a Terminal Proof.
- Whether the contract, scope, queue, active batches, Standards versions, and time semantics are still valid.
- Whether each active batch has unverified changes; for `merge-ready` batches, deltas already written out are carried forward by the integrator into serial merge after resume, without redoing in-batch work.
- Whether new user modifications have appeared.
- Whether the last automated check results are still valid.
- Whether the next action still follows the dependency order.

Only after the resume checks complete may the task state be set back to `active`.
