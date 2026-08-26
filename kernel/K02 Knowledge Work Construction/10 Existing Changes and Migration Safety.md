## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production|Knowledge Batch Production]].

## Existing Changes

- By default, all existing modifications belong to the user.
- Do not roll back changes unrelated to the current task.
- When user modifications exist in the same file, understand them first and work on top of them.
- Request a user decision only when a modification makes the task unable to continue.
- Do not use destructive resets or bulk-overwrite strategies.

## Migration Safety

A migration is valid only when all of the following observable outcomes hold:

- every moved semantic unit has an identified canonical target;
- unique content, authority, and applicable evidence are conserved;
- all affected incoming and outgoing references resolve to the intended owner;
- the replacement owner is present and verified before any duplicate or old
  owner is removed;
- the knowledge-base-wide checks required by the
  [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]]
  pass for the batch in which the migration closes.

This semantic owner does not prescribe the implementation or action sequence
for producing these outcomes. Deleting the old owner before the replacement
is verified violates the conservation invariant.
