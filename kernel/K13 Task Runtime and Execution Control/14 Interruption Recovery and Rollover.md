## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/13 Final Handoff|Final Handoff]].
- Next: [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|Standards Adoption State Transaction]].

## Interruption And Resume

Before a planned interruption, use `Tools/update_task.py` to set task state to
`paused` or `blocked` and write its checkpoint. A sudden interruption may
prevent that transition, so durable Queue state, receipts, deltas, and
writer-lock evidence remain independently discoverable. The Progress
checkpoint itself stores only its schema fields: recorded time and summary,
task state/transition receipt, exact Coverage and Queue fingerprints, and both
Queue revisions.

The effective restart view combines that checkpoint with the Task Contract,
Queue, Coverage, receipts, deltas, and `--resume-status`. Together they expose:

- Task/scope/Standards/profile identity and canonical Queue binding.
- Open or merge-ready batches, holds, pending deltas, and unfinished Required objects.
- Each batch's explicit simple declaration or complex Work Spec path and fingerprint.
- Pending Guidance/Amendments, last accepted checks, and any modified or unverified work.
- The precise next action; on a block, its reason, attempts, and other work that may proceed.

These are read-through facts, not extra checkpoint keys or a second editable
batch list.

At every restart—and before a new Agent task assumes the repository is
unused—the first runtime action is:

```text
python3 Tools/check_queue.py . --resume-status
```

If `.cambium/state/` is absent, there is no persistent task state to resume and
an authorized task may initialize it beside any valid governance/history
namespace. If task state exists, `init_state.py` MUST NOT be used to replace
it. The status view identifies the recorded task and Profile,
task state/checkpoint, Queue revisions and fingerprint, lifecycle groups, Work Spec bindings,
holds, pending deltas, writer locks, latest task transition, pending Guidance
or Amendments, Terminal Audit state, and one machine-readable `next_action`.
For an intact handoff that action distinguishes `admit-delta:<id>`,
`apply-delta:<id>`, `run-batch-close-gate:<id>`, and the fully bound
`close-applied-batch:<id>:<queue-receipt>:<close-receipt>:<apply-receipt>`.
An apply receipt alone never authorizes close. If the close tool published a
current bundle before its stdout was lost, resume recovers the latest valid
bundle from the receipt catalog, reports its repository snapshot, and emits an
exact copyable close command. Stale, structurally invalid, internally
conflicting, or snapshot-mismatched bundles are reported but not selected.
This is a local consistency decision, not authentication of the recorded
producer, actor, or reviewer. An unresolved writer lock takes precedence as
`reconcile-interrupted-write`; other malformed or conflicting evidence becomes
`repair-runtime`. The tokens named here are part of a larger reported set; the
complete `next_action` vocabulary, with each token's reporting condition and
selected action, is owned by
[[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary|K13/16]].
Its checkpoint binding is `current`, `historical`, or `initial`; `historical`
means later recorded state must be followed from receipts and deltas rather
than mistaken for a clean checkpoint. The Agent then checks:

- Whether the user's latest requirements change the objective.
- Whether the last state was `paused`, `blocked`, or already has a Terminal Proof.
- Whether the contract, scope, Queue path/revisions/fingerprint, Standards version, selected profile manifest, and time semantics are still valid.
- Whether `Tools/check_queue.py .` passes across Queue, Coverage, and Progress; stale revisions, a changed fingerprint, unresolved hold, or unapplied delta MUST be reconciled before execution resumes.
- Whether each `open` batch has unverified changes; for `merge-ready` batches, deltas already written out are carried forward by the integrator into serial merge after resume, without redoing in-batch work.
- Whether every non-null Work Spec still matches its Queue fingerprint, batch ID, and exact manifest; a changed open-batch spec remains under `revalidation-required` until the approved replan and new admission evidence are reconciled.
- Whether a Standards-adoption plan, shared writer lock, or prepare receipt is pending. If so, defer to [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|K13/15]]; do not infer success from one updated Ledger or reconstruct the plan from prose.
- Whether new user modifications have appeared.
- Whether the last automated check results are still valid.
- Whether the next action still follows the dependency order; a new activation additionally requires `check_queue.py --require-ready <batch-id>`.

A writer lock is evidence of either a live writer or a possible interrupted
write. Do not remove it until no writer remains and state files, transition
receipts, revisions/fingerprint, deltas, and any recorded archive move have
been reconciled. Receipt registers are append-only; uncertain appends retain
the lock rather than rolling back unrelated evidence. An Agent may
not infer a clean restart merely from an old lock timestamp.

The Agent MUST consume the reported `next_action`, not infer a fresh start from
an empty local context. Only after reconciliation may a `paused` or `blocked`
task return to `active`, through `update_task.py`; Queue and canonical delta
writes remain rejected beforehand. A new task cannot reuse the namespace: the
existing task must first be explicitly
completed or cancelled and later handled by an archive/rollover procedure.
Automatic rollover is not part of the current tools.
