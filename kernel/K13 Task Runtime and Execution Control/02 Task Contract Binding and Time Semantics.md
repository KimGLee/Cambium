## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]].
- Next: [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|Task State and Transition Rules]].

## Purpose

This page owns contract freezing and time semantics for persistent knowledge
work; [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|K13/03]] owns whole-task state. R07 executes checkpoint/resume through the Progress
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
overwritten. [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|K13/01]] owns the runtime namespace and cross-state contract.

Freeze `standards_version` and `selected_profile_manifest` once work starts.
Only an authorized governance change may modify them; afterward run K12/10
Active-task Adoption against the revision's changed predicates.

The contract MAY carry a `policy_exceptions` register: bounded, currently
valid exceptions to standing policies, each a closed record of `decision_id`,
`policy_id`, `baseline_policy_fingerprint`, `limit`, `scope_kind` (`task` or
`repository-snapshot`), `scope_ref`, `rationale`, and `approval_reference`.
An exception is contract state because it is *current authorization* -- it
ends with its task or named snapshot, and its baseline fingerprint binds it to
the exact *effective policy* it was judged against (the resolved standing
values, kernel defaults included, under one comparison protocol -- never the
hash of a policy file alone), so a Standards, Profile, or kernel-default
revision it never saw invalidates it. Absent means the same as explicitly
empty. Its sole writer after materialization is the
[[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|K13/06]]
Contract Amendment transaction; the policy each exception excepts keeps its
own owner, and consumption is judged where the policy is consumed.

The contract MAY also carry `amendment_authority`, a closed delegation record
with `schema_version: 1`, a stable nonempty `authority_id`, `mode`, and a sorted
unique `allowed_change_classes` list. Absence is equivalent to
`mode: user-only` with an empty list. `user-only` MUST carry an empty list;
`delegated-integrator` may name only these current operational classes:

```text
batch-add
queued-batch-update
required-object-add
required-object-promote
required-object-reroute
```

The block authorizes the integrator to register exactly those mechanically
derived effects without another user interruption. It does not authorize
Standards/Profile changes, Required-object demotion, batch retirement, open
Work-Spec mutation, gap settlement, arbitrary metadata edits, or a writer
operation whose ordinary lifecycle checks fail. The authority record and the
complete derived impact are fingerprinted into registration evidence and
re-derived under the executing writer's lock. The local record is an
authorization assertion, not proof of an operating-system identity or a
cryptographic signature. After Queue materialization its sole writer is the
K13/06 Contract Amendment transaction.

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
