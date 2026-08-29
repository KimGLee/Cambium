## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|Progress Ledger Contract]].
- Next: [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views|Queue Compilation Replanning and Views]].

## Purpose And Ownership

The Required Queue owns batch manifests, order, dependencies, lifecycle, holds, and transition evidence. Coverage owns object disposition, semantic owner, and batch projection. Progress owns task state and Contract, Amendments, checkpoints, completion binding, and the accepted Queue reference. Reports and executor-local lists are never authority.

## Queue Document Contract

The registered required-queue machine contract is the sole normative source for Queue fields, closed values, shapes, and serialization. Its current value belongs to adopter runtime state.

Queue identity binds one task, scope, Standards, selected Profile, structural revision, lifecycle revision, and ordered batch set. Every batch has a stable identity, family, unique order, positive manifest count, nonempty unique manifest, provenance, execution mode, explicit dependencies, confirmation requirement, lifecycle, hold, and optional Work Spec binding. Provenance does not select a runtime route or Card. Dependencies are explicit, acyclic, earlier than their dependents, and never inferred from similarity or backlinks.

An in-flight manifest is frozen. Coverage projects Required objects into Queue batches; compiler inputs are not lifecycle state. Outside an authorized replan or cancellation transaction, Queue membership and Coverage projection must agree exactly.

## Batch Work Specification Binding

A simple batch is fully specified by its Queue identity, manifest, and owning governance and carries an explicit empty Work Spec binding. A complex batch binds one immutable Work Spec identity and byte fingerprint. Complexity is explicit and is never inferred from family, size, prose, or route.

The registered batch-work-spec machine contract is the sole normative source for fields, closed values, shapes, and serialization. Semantically, a Work Spec binds the exact Queue batch and ordered manifest plus unique outcomes, dependency-ordered instructions, observable acceptance conditions, and constraints. Every target is either the whole batch or an exact nonempty subset of its manifest.

A Work Spec contains only instructions unique to that batch. It cannot own or repeat Queue state, order, dependencies, holds, revisions, transition evidence, or task completion. A template or placeholder is not a valid Work Spec.

The Work Spec binding is structural state. A queued batch changes it only through an authorized Amendment and Queue replan. An open batch first enters `revalidation-required`; a `merge-ready` or terminal batch is immutable and later instructions use a successor. Any binding change invalidates prior admission and close evidence.

`required-queue-consistency` validates Work Spec containment, fingerprint, machine contract, batch and manifest identity, instruction graph, target scope, and absence of placeholders. A Work Spec is instruction, not proof: its presence satisfies no execution, review, integration, or semantic-acceptance obligation.

## Revisions And Fingerprints

`queue_revision` advances on Queue structure or verification-contract change. `queue_state_revision` advances on lifecycle or hold change. Every accepted reference also binds the canonical Queue fingerprint. Structure and lifecycle never hide inside one another.

## Batch Lifecycle

[`runtime-state-model.json`](runtime-state-model.json) is the sole machine owner of batch-state identities, active and terminal classes, and legal edge membership. Its current authorization is split by writer capability: the ordinary Queue writer cannot cancel, while the Amendment cancellation writer cannot perform an ordinary lifecycle edge. The historical replay catalog is a separate, fixed composition of the producer-era edge catalogs and does not authorize a current write.

`queued` means admitted but not opened. `open` freezes the batch partition while permitting its owned work to advance. `merge-ready` means the exact Delta, review, and QA evidence exists; invalidated evidence can return that same batch to `open` through the registered ordinary writer. `closed` means serial integration and global Gates passed. `cancelled` means an authorized scope or disposition Amendment retired an actionable batch. `closed` and `cancelled` are terminal: their history is immutable and later work uses a successor.

`hold_state` is independent of lifecycle and task state. The machine model owns its closed values. `none` means no hold; `confirmation-required` awaits the registered confirmation; `blocked` records an external impediment; `revalidation-required` prevents further use of invalidated evidence; and `paused` records an intentional stop. Every lifecycle or hold transition binds the exact before and after state, revision edge, Queue identity, actor role, time, and required evidence. Referenced evidence must exist, pass, remain current for that edge, and match its declared scope.

### Batch Reference Settlement

Before a batch becomes terminal, every live reference it owns must be settled. The closed reference classes are:

| Reference | Owner | Terminal-state invariant |
|---|---|---|
| Coverage page batch projection | Coverage | Ownership moves to the closing batch and unfinished work moves to a valid successor or becomes empty |
| Coverage open-gap routing | Coverage | Every gap routed to this batch is closed or explicitly rerouted to a valid later batch |
| Coverage batch specification input | Coverage | The terminal Queue item owns frozen structure; stale compiler input cannot rebuild or replace it |
| Receipt batch identity | Receipt catalog | Immutable evidence continues to name the historical batch |

Settlement begins at `open -> merge-ready`. The transition projects the exact Delta over current Coverage, binds the complete before obligation set, and requires zero prospective unsettled references. Delta application repeats the same projection, and batch close proves the landed state still has zero unsettled references. A defect is repaired while the batch remains open rather than hidden until after integration.

The invariant is: **a terminal batch preserves its history and loses its live references**. Adding a new reference class requires extending this semantic contract and the settlement Gate together; an implementation cannot introduce an unaccounted reference merely because it can store one.
