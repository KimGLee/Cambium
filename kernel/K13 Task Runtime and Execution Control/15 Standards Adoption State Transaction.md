## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]].
- Next: [[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary|Resume Next Action Vocabulary]].

## Purpose And Boundary

This module owns only the controlled runtime-state transaction for an
active-task Standards adoption. [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]]
owns whether an adoption is semantically valid, its changed predicates,
invalidated evidence, invalidation boundaries, and required gate reruns.

`Tools/adopt_standards.py` is the sole writer. It consumes one validated
restricted-YAML plan under
`.cambium/deltas/standards-adoptions/<adoption-id>.yaml`, defaults to dry-run,
and writes only with `--apply --actor-role integrator`.

## Permitted Transaction

The writer may change only:

- the canonical adopter Standards state: current Standards/Profile identity,
  approval/effective-date and upstream provenance, latest adoption receipt,
  and exactly one `state_revision` increment;
- `standards_version` and `selected_profile_manifest` in Coverage and Queue;
- those identity fields and, when K12/10 requires it, `contract_version` in
  the Progress Task Contract;
- Queue `queue_revision`, advanced exactly once, and Progress's accepted copy
  of that same revision;
- Progress's five resolved load-set fields:
  `selected_route_ids`, `selected_card_paths`,
  `selected_profile_route_ids`, `selected_read_sets`, and
  `loaded_module_paths`; and
- one append-only Progress `standards_adoptions` entry binding the plan,
  transaction receipt, before/after identities and load set, all four before
  SHAs, the after Coverage/Queue/Standards-state SHAs, and the immediate-gate receipt. It
  cannot contain its own after Progress SHA; only the commit receipt binds the
  complete four-file after image.

Everything else must remain byte-semantically unchanged. In particular, the
writer cannot change task state, contract objective/scope/completion
semantics, Queue `state_revision`, Queue membership/order, batch lifecycle or holds, manifests, dependencies,
Work Specs, Amendments, checkpoints, terminal history, maintenance history,
Coverage disposition, or knowledge content. A Standards adoption is not a
Queue transition, Amendment, replan, Work Spec migration, or batch execution. The single structural
revision increment records changed Queue identity; it never implies changed
batch structure.

## Guarded Write Protocol

Before writing, the tool reparses the plan, the three task Ledgers, and the
canonical adopter Standards state, validates the K12/10 branch, and
compare-and-swaps the plan's exact
task state, Standards/Profile identity, Queue revisions, and four before
SHA-256 values, plus `queue_revision_after = queue_revision_before + 1`. Only
`active` and `paused` tasks may
adopt. A stale plan, unknown field, unresolvable after load set, current writer
lock, governance-owner/snapshot mismatch, incompatible bound Work Spec,
affected `merge-ready` batch, affected `open` batch without
`revalidation-required`, pending state write, or any requested change outside the
permitted transaction fails closed.

All four canonical state objects must already satisfy the current schema,
including an explicit Progress `standards_adoptions` list. Missing or malformed
current fields fail closed; schema migration is not Standards adoption.

The writer then:

1. acquires the shared state-writer lock;
2. records a `prepare` receipt and the exact before/planned-after fingerprints;
3. stages and reparses all four complete after documents;
4. publishes each file by same-directory atomic replacement while retaining
   enough lock evidence to diagnose a partial multi-file write;
5. runs and consumes the plan's sole immediate
   `required-queue-consistency` gate against the staged after image;
6. revalidates cross-state identity, unchanged lifecycle/state revision, the
   one structural Queue revision increment, and exact after fingerprints; and
7. appends one `commit` receipt, including all four after SHAs, to
   `.cambium/receipts/standards-adoptions.jsonl` before releasing the lock.

The commit receipt also chains the before and after Task Contract anchors. A
task-transition receipt created under the old contract remains historical
evidence and cannot be treated as if it authenticated the new contract bytes.

The filesystem operation is not falsely described as one atomic four-file
write. An ordinary pre-commit failure rolls back to the frozen before images
and appends an `abort` receipt. If rollback or a receipt append is uncertain,
the lock remains with both before and planned-after fingerprints; it is
recovery evidence, not disposable clutter.

Receipts are append-only. The writer never edits historical receipt bytes;
K12/10's invalidated-evidence declarations are new references in the adoption log,
not mutations of the referenced evidence. K12/10 alone owns their current-use
and historical-verification meaning.

## Resume Boundary

At restart, R07 first uses `check_queue.py --resume-status`. An adoption lock
or prepare receipt without a matching current commit takes precedence over
batch execution. The integrator reconciles the plan SHA, lock owner, all four
current state SHA-256 values, and the prepare/commit/abort chain before removing
the lock or retrying. A committed adoption resumes per K12/10 without another
state rewrite.

## Related

- [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]]
- [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
