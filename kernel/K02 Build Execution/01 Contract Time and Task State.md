## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Next: [[kernel/K02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]].

## Purpose

This page owns contract freezing, time semantics, and whole-task state for
persistent knowledge work. R07 executes checkpoint/resume through the Progress
Ledger; a persistent R10 run uses the same state machine but the bounded
completion predicate owned by [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|K00/06]]. It does not
define an Agent runtime implementation.

## Core Execution Principle

```text
Architecture before expansion.
Canonical ownership before writing.
Complete batches before claiming progress.
Verification after every batch.
Time boundaries are not completion evidence.
Every in-scope page must have an explicit disposition.
```

## Phase 0: Freeze The Contract

Before formal execution, freeze the decisions listed in K00/06, including:

- Objective, scope/exclusions, ownership and profile bindings, source and gate
  policy, coverage dispositions, and amendment authority.
- Contract/scope/Standards versions, selected profile and loaded routes, exactly
  one `completion_semantics` value (`build` or `maintenance`), time fields, and
  the Completion Gate.
- When persistent state applies, the Queue path, revisions/fingerprint,
  concurrency cap, checkpoint/recovery policy, and identity shared by Coverage,
  Queue, and Progress.

Every writer first probes for `.cambium/`. Only R07/R11, resumable,
multi-batch, or otherwise persistent Required work initializes it when absent;
bounded single-note work does not. Existing state is resumed, never
overwritten. K02/09 owns the runtime namespace and cross-state contract.

Freeze `standards_version` and `selected_profile_manifest` once work starts.
Only an authorized governance change may modify them; afterward run K12/10
Active-task Adoption against the revision's changed predicates.

## Time And Stop Semantics

Time fields MUST use explicit semantics; they cannot all be written as an ambiguous "deadline":

- `minimum_run_until`: MUST NOT voluntarily stop before this time. Reaching this time only lifts the earliest-stop restriction; it does not mean the task is complete.
- `checkpoint_at`: at this time, record progress, re-verify the plan, or report to the user; the task continues by default.
- `hard_stop_at`: on reaching this time, execution MUST stop and a checkpoint MUST be written. If the Completion Gate has not passed, the state MUST be `paused` and cannot be written as `complete`.
- `completion_gate`: quality and coverage conditions independent of time, defining what evidence true completion requires.

"Do not stop before" maps to `minimum_run_until`; "stop at" maps to
`hard_stop_at`. Resolve ambiguity before large-scale execution.

Without a `hard_stop_at`, work continues until the selected Completion Gate
passes, the user pauses/cancels, or a real blocker appears. Required gaps after
`minimum_run_until` still require continuation.

## Task State Machine

Long-task state is recorded only in the task Progress Ledger; it is not expressed via the `authoring_status` of knowledge pages. The common transitions are:

```text
planned -> active / paused / blocked / cancelled
active -> paused / blocked / cancelled
paused -> active / blocked / cancelled
blocked -> active / paused / cancelled
```

The frozen completion semantics adds exactly one mutually exclusive closure path:

```text
build:       planned / active -> completion-candidate -> complete
maintenance: planned / active -> complete
```

The direct `planned` closure edge exists only for a materialized nonempty Queue
whose batches were all validly cancelled by Amendment before any opened. It
still requires the selected full completion gate; it is not an empty-Queue
shortcut.

- `planned`: the contract, scope, or inventory has not yet met the execution threshold.
- `active`: executing, or the next Required batch is known.
- `paused`: unfinished work stopped by request, `hard_stop_at`, interruption, or checkpoint; resume information MUST be saved.
- `blocked`: an external dependency exists that cannot be resolved in the current environment, and no other Required work can proceed.
- `completion-candidate`: a build-only state in which the executor believes the scope is satisfied and awaits the Terminal Audit; a maintenance task MUST NOT enter it.
- `complete`: the selected closure passed: a valid Terminal Proof for build, or a valid maintenance completion gate for maintenance.
- `cancelled`: the user has explicitly terminated the current contract; it does not mean the knowledge scope is complete.

`Tools/update_task.py` is the sole ordinary task-state writer. The first batch
opening may invoke its helper for `planned -> active`; direct operator use of
that edge is rejected. Every transition records a receipt and refreshes the
checkpoint. Build closure consumes K02/09 `--require-complete`, then the K12/16
Proof pass. Maintenance closure consumes K02/09
`--require-maintenance-complete` directly and never invokes `check_proof.py`.
Progress keeps mutually exclusive `terminal_audit` and
`maintenance_completion` blocks; K02/08 owns their separation.

While task state is not `active`, Queue lifecycle/hold writes and canonical
delta application are prohibited, except that first atomic
`planned -> active` activation. Resume a `paused` or `blocked` task through
`update_task.py` before continuing batch execution.

`paused`, `blocked`, `cancelled`, and `complete` MUST be distinguished. The runtime environment ending, no files being under edit, reaching a point in time, or `In-progress batch: None` cannot automatically produce `complete`.
