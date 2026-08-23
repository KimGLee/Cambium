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
- `batch-gate`: the work route's own Gate, normally a zero increment because
  that Gate is already compiled into the work Card preflight delivered. R12
  enters only when its Card's self-stated scenario holds for this batch.

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
selected route to `batch-preflight`. The batch Work Spec MAY narrow through
the optional `required_route_ids` field, and a narrowed-away route moves to
`batch-running`. Absent the field the default is every selected
non-conditional route, so an unrevised Work Spec behaves exactly as it did
before.

Narrowing reaches R12 and no other override. R12's Card states scenarios and
the Work Spec is where a batch says which scenario it is, so a batch that does
not name R12 is not running a targeted audit and does not owe its Card;
without that, selecting R12 once at task level charges every batch for an
audit almost none of them run. R01, R08, and R09 stay outside a batch's reach
for the opposite reason -- R01 is presumed by every phase, and the other two
are entered by a task-level transition no Work Spec decides -- and a batch
cannot waive an obligation that was never its.

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

## Phase Consumers

Which writer refuses which phase, which
[[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|K13/20]]
defers here:

| Edge | Phase owed | Actor binding |
|---|---|---|
| First `record_batch_judgment` of a batch | `batch-gate` | the judging context |
| `update_task` completion-candidate transition | `task-completion` | the transitioning context |
| `open -> merge-ready` | `batch-gate` | unbound |
| `open -> merge-ready` when the batch manifest touches the control plane | `governance` | unbound |

A judgment is somebody's judgment: evidence that some other context received
the Gate set proves nothing about the context recording the verdict, so a
bound edge requires the actor's own `delivery_attempt_id` to be the one that
covers the phase. The integrator edge is unbound because it reads a batch's
history rather than acting inside it, and making the integrator re-earn a
worker's phase would record the wrong reader; it requires instead that some
one attempt covers the phase.

Coverage is judged per attempt at both kinds of edge, never over their union.
The claim being tested is that one reader received the whole phase, and two
half-deliveries to two contexts leave neither able to say so. For the same
reason, another context's chain present in the same history is not itself a
fault at a bound edge -- only the actor's own absence is.

Touching the control plane is a property of the batch manifest -- a path under
`kernel/`, `profiles/`, or `Tools/` -- and never of which tool is invoked. A
tool-name list is bypassed by editing the file directly, while the manifest is
what the batch actually changes. The check sits on the transition for the same
reason it is not at each writer's own admission: a writer can be circumvented,
an edge cannot.

`prepared` and `degraded` activations are exempt at every edge above. Under
K13/19 they claim no machine-enforced delivery, and what never claimed
enforcement cannot be refused for failing to prove it.

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
