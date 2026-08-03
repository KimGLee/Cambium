## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Next: [[kernel/K02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]].

## Purpose

This standard specifies how ultra-long knowledge base build tasks are planned, executed, verified, and resumed, preventing mass up-front creation of empty-shell pages, later loss of consistency, or repeated work after interruption.

This document governs long tasks that build the knowledge base; it does not define the deployed runtime agent's internal implementation. Checkpoint, context continuity, pause / resume, and recovery records are governed by K02 and executed through [[kernel/Read Sets/R07 Long-running Execution Read Set|R07 Long-running Execution]] using the Task Contract and Progress Ledger. The selected profile's `Profile Scope` supplies only the organizing knowledge mainline, concrete layer roles, and canonical knowledge placement used by that work.

## Core Execution Principle

```text
Architecture before expansion.
Canonical ownership before writing.
Foundations before unsupported system claims.
Evidence before canonical promotion.
Representative samples before bulk migration.
Complete batches before claiming progress.
Verification after every batch.
Time boundaries are not completion evidence.
Every in-scope page must have an explicit disposition.
```

## Phase 0: Freeze The Contract

Before formal execution, confirm:

- The target role and knowledge boundaries.
- The organizing mainline registered by the selected `Profile Scope`, and the constraint that foundational knowledge MUST be preserved in full.
- The excluded scope.
- Top-level directories and ownership.
- Note type, depth, metadata, and language conventions.
- The expression-artifact split registered by the selected `Expression Layer Entry`.
- Sources, diagrams, and quality gates.
- The source-to-knowledge intake, evidence maturity, and canonical promotion approach.
- Contract version, scope version, queue revision, initial batch revision, and Standards version.
- The concurrent batch cap `concurrency_cap` (the kernel default is `3`; the selected profile manifest or task contract MAY explicitly override it); batch concurrency admission and merge rules are in [[kernel/K02 Build Execution/05 Batch Execution|K02/05]] Concurrent Batches.
- Selected Rxx route IDs and Runtime Card paths, the actual loaded set (any combined namespaced profile route and every Read Set or leaf path actually read back), triggered items, and gate items not yet executed.
- The authority allowed to modify scope, priority, batches, and Standards.
- `minimum_run_until`, `checkpoint_at`, `hard_stop_at`, and the Completion Gate.
- Handling of pause, cancel, block, and resume.
- The recording, acknowledgement, safe switching, and amendment policy for mid-task guidance.
- How Required, optional, deferred, and excluded coverage is determined.

Before the standards are confirmed, no large-scale migration is performed.

Freeze `standards_version` once the task starts. The Standards MUST NOT be modified in passing during content build; only a governance change explicitly authorized by the user may modify them. After a Standards change, the version MUST be bumped, and [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]] Active-task Adoption MUST be executed per the changed-predicate list of the revision record (an empty list is a no-op).

## Time And Stop Semantics

Time fields MUST use explicit semantics; they cannot all be written as an ambiguous "deadline":

- `minimum_run_until`: MUST NOT voluntarily stop before this time. Reaching this time only lifts the earliest-stop restriction; it does not mean the task is complete.
- `checkpoint_at`: at this time, record progress, re-verify the plan, or report to the user; the task continues by default.
- `hard_stop_at`: on reaching this time, execution MUST stop and a checkpoint MUST be written. If the Completion Gate has not passed, the state MUST be `paused` and cannot be written as `complete`.
- `completion_gate`: quality and coverage conditions independent of time, defining what evidence true completion requires.

When the user says "no stopping before some time", it MUST be recorded as `minimum_run_until`. Only when the user says "stop at some time" is it recorded as `hard_stop_at`. When the semantics are unclear, the ambiguity MUST be resolved before large-scale execution.

Without a `hard_stop_at`, the task continues until the Completion Gate passes, the user pauses or cancels, or a real blocker appears. When Required gaps remain after reaching `minimum_run_until`, the task MUST continue.

## Task State Machine

Long-task state is recorded only in the task Progress Ledger; it is not expressed via the `authoring_status` of knowledge pages:

```text
planned
 -> active
 -> completion-candidate
 -> complete

active <-> paused
active <-> blocked
completion-candidate -> active
planned / active / paused / blocked / completion-candidate -> cancelled
```

- `planned`: the contract, scope, or inventory has not yet met the execution threshold.
- `active`: executing, or the next Required batch has been determined.
- `paused`: the task is not complete but is paused due to user request, `hard_stop_at`, a run interruption, or an explicit checkpoint; resume information MUST be saved.
- `blocked`: an external dependency exists that cannot be resolved in the current environment, and no other Required work can proceed.
- `completion-candidate`: the executor believes the scope is satisfied and awaits the Terminal Audit.
- `complete`: the Terminal Audit has produced a valid Terminal Proof.
- `cancelled`: the user has explicitly terminated the current contract; it does not mean the knowledge scope is complete.

`paused`, `blocked`, `cancelled`, and `complete` MUST be distinguished. The runtime environment ending, no files being under edit, reaching a point in time, or `In-progress batch: None` cannot automatically produce `complete`.
