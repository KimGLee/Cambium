## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|Assignment State and Delivery Gate]].

## Purpose And Boundary

This module owns the phased reading plan of protocol
`card-first-phased-readback-v4`: which Cards a batch owes at each point of its
own execution, instead of all of them at startup. Freezing is unchanged from
v3 -- everything below is computed at admission; only the moment of delivery
moves. [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|K13/19]]
owns the transport, the piece budget, and what one delivered piece proves;
[[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|K13/20]]
owns Assignment state and the delivery gate. This module owns neither, and no
field of it asserts that anything was read or understood.

Earlier protocols made one startup set carry every Card a batch might ever
need. Cost was paid for routes that never triggered, and the set was largest
exactly when the worker knew least about the work in front of it.

## Phase Set

Five phases, closed, in two tiers.

Batch phases are reached by running the batch at all:

- `batch-preflight`: R01, the batch's work-route Card, and R07.
- `batch-running`: no frozen set; only declared read-back already triggered.
- `batch-gate`: the work route's own Gate, normally a zero increment. R12
  enters only when its Card's self-stated scenario predicate holds.

Task-level conditional phases are reached only when their transition is
actually attempted:

- `governance`: the R09 set, entered only by a real in-batch Standards
  governance transfer.
- `task-completion`: the R08 set, entered only by a completion-candidate
  transition.

The tiers are separated because their triggers are of different kinds. A batch
phase follows from execution; a conditional phase follows from a task-level
transition most batches never make, and charging every batch for those sets is
the waste this protocol exists to remove.

## Route To Phase Mapping

The mapping is deterministic: R01 to `batch-preflight` always; R09 to
`governance`; R08 to `task-completion`; R12 to `batch-gate`; every other
selected route to `batch-preflight`. The batch Work Spec MAY narrow that last
case through the optional `required_route_ids` field. Absent the field the
default is every selected non-conditional route, so an unrevised Work Spec
behaves exactly as it did before.

The Card Index leaves the required set of every phase. It is a registry rather
than a route, and routing disputes are rare enough that carrying it at
preflight charges each batch for a lookup few need; it becomes one declared
rule in `readback_plan` and is retrieved when a dispute makes it worth reading.

## Frozen Phase Plan

Admission freezes four things, at the same moment v3 froze its manifest:

1. the phase set, the route-to-phase mapping, the phase transition predicates,
   and each phase's piece computation rule;
2. one `{piece_id, kind, path, sha256, bytes, phase}` record for every piece of
   every potential phase, conditional phases included;
3. the environment fingerprint: `standards_version`,
   `profile_snapshot_sha256`, `profile_contract_fingerprint`,
   `resolver_version` (the `card_activation` tool version), `work_spec_sha256`,
   and `card_index_sha256`;
4. their composite `phase_plan_sha256`.

Conditional pieces are frozen although most batches never receive them. A plan
computed at the transition would be computed under later bytes, and the batch
could then enter `governance` under a content identity its own admission never
committed to. `phase_plan_sha256` is the attempt-level anchor on which v4
dispatches producer-era replay.

## Phase Packages

A phase is delivered as its pieces greedily packed into N parts against the
budget owned by K13/19: one part per tool result, each carrying a trailing
single-use nonce exactly as a v3 single piece does. Acks are per part, while
ack accounting remains a set of pieces, so the delivery arithmetic of K13/20 is
unchanged by the repackaging.

A standard phase -- `batch-preflight` or `batch-gate` -- MUST pack into
`part_count == 1`. More than one part is not a transport failure but a design
signal: that phase's set has outgrown what a worker can be handed at one
boundary, and the Cards or leaf sizes behind it are what must change.
Conditional phases MAY use several parts, because their sets are entered rarely
and sized by the transition rather than by the budget.

## Invalidation

Any change to a frozen input -- Standards version, Profile snapshot or
contract, resolver version, Work Spec, Card Index, or any piece hash -- changes
`phase_plan_sha256` and voids the plan whole. Recovery is reactivation under
current bytes, never patching one phase into a plan that no longer describes
it.

## Related

- [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|Card Context Activation and Read-back Delivery]]
- [[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|Assignment State and Delivery Gate]]
- [[kernel/K00 Standards Control/02 Task Routing|Task Routing]]
- [[kernel/K00 Standards Control/15 Read Set Loading Boundaries|Read Set Loading Boundaries]]
