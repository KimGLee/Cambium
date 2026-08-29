## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views|Queue Compilation Replanning and Views]].
- Next: [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]].

## Concurrent Batches

Batches may execute concurrently under the resolved Contract concurrency cap. The Kernel default is three open batches; a selected Profile or Task Contract may explicitly override it. The cap limits concurrently open batches, not the number of execution contexts a Host uses.

A queued batch may open concurrently only when:

- its frozen manifest is disjoint from every open manifest and agrees exactly
  with Coverage projection;
- it does not modify a registered control, navigation hub, shared terminology
  owner, or other exclusive integration owner;
- every Queue dependency is closed and it does not depend on in-flight pages;
- a complex batch has a current Work Spec matching its exact batch and ordered
  manifest;
- confirmation and any other admission preconditions are satisfied.

The hub/control set is supplied by canonical machine metadata and selected Profile extension bindings; this module does not hardcode current repository types or infer future roles. Editing an existing exclusive owner requires exclusive or `serial-integrator` execution. Creating a new future hub does not retroactively make its pre-creation path shared, but it must be surfaced for post-merge synchronization.

Migration and refactor batches that necessarily cross owner partitions are exclusive. While one is open, no other batch opens.

A concurrent worker may write only its frozen manifest objects, its own execution evidence, and its exact batch Delta. Canonical Coverage, Queue, Progress, Amendment, and maintenance state remain integrator-owned. The registered Coverage-delta machine contract owns Delta shape and serialization.

Card delivery and read-back follow K13/19; Queue `open` remains admission rather than proof that a worker received, read, or understood context.

## Serial Integration

Batch close has two distinct evidenced boundaries:

1. The merge-readiness boundary consumes the current K12/14 `batch-review`
   wrapper, exact Delta and page evidence, and prospective zero-unsettled
   K13/08 reference settlement.
2. The integrator applies that exact Delta, proves landed zero-unsettled
   references, runs the K12/09 Closed List and K12/14 global items, consumes
   current Queue consistency and any applicable Corpus Planning evidence, and
   records the registered close transition.

Each serial integration handles exactly one batch. Delta application and Queue close are ordered, independently evidenced writes; they are not represented as one atomic object. Interruption must be recoverable without inferring which boundary completed.

The control plane is single-threaded under the integrator role, including Guidance disposition, structural revision, lifecycle transitions, Contract changes, Standards adoption, batch activation, and merge. Workers submit Deltas and never change Queue state.

## Transition Gates

Only the registered Queue transaction changes lifecycle or holds, and only the registered Coverage-delta transaction changes canonical Coverage. Except for the first atomic activation from `planned`, these writes require task state `active`.

Exact edge membership and its division between the ordinary Queue writer, Amendment cancellation writer, and historical replay protocol are owned only by [`runtime-state-model.json`](runtime-state-model.json). The operation categories below specify the evidence attached when the registry authorizes a corresponding edge; they do not create an edge or form a second edge catalog.

| Operation boundary | Required observable evidence |
|---|---|
| Initial batch admission | current `required-queue-admission`; closed dependencies; required confirmation; current Work Spec when bound; disjoint manifest and concurrency/exclusivity compliance |
| Merge readiness | exact-manifest Delta; current page and scoped-check evidence; one current `batch-review` wrapper; zero prospective unsettled K13/08 references bound to exact Delta and Coverage bytes |
| Serial close | exact Delta applied; zero landed unsettled references; Closed List and global review passed; current Queue consistency and batch-close evidence over one repository snapshot; any applicable Corpus Planning child evidence |
| Invalidation rollback | recorded merge failure and immutable invalidation history binding the archived Delta, invalidated evidence, and any byte-exact Coverage restoration required by a prior apply |

Corpus Planning applicability is resolved from the frozen Task Contract and validator-defined affected-path set, not trusted from a caller-provided boolean. Stale Profile, planning, state, Queue, or repository bindings cannot authorize close.

`required-queue-consistency` is the sole Gate for Queue structure, cross-state agreement, readiness, Work Spec binding, evidence, revisions and fingerprints, concurrency, recovery, and terminal work count.
