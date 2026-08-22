## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|Card Context Activation and Read-back Delivery]].

## Purpose And Boundary

This module owns the mapping between one admitted batch and one temporary
execution context, and the gate that decides when that context may be called
`running`. [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|K13/19]]
owns what is delivered and how one piece is proven; this module owns whether
enough of it arrived. Nothing here is a second Queue: the Assignment record
carries no work list, no batch lifecycle, and no completion semantics, and it
is discarded when its context ends while the batch survives.

The separation matters because the two lifecycles fail differently. A batch is
durable work that outlives any agent; an Assignment is one attempt by one
context to carry it. Losing the context loses the delivery evidence and
nothing else.

## Why This Is A Separate Gate

`open` means a batch is admitted and its partition reserved. It does not mean
any worker holds the Cards. Before this module existed the distance between
those two facts was unmeasured: a runtime could call a worker `running` on the
strength of an admission receipt, and the 2026-08-22 host measurement showed
exactly that failure reaching production -- a conformant server delivery, a
receipt claiming machine delivery, and a model context that never received the
bytes. The claim was unfalsifiable because no gate consumed delivery evidence.

## Assignment Record

An Assignment binds, for one execution context:

- `assignment_id`, and the `batch_id` it carries;
- `execution_context_id`, and the optional parent context it was spawned from;
- the role (`integrator`, `writer`, `reviewer`, or `researcher`) and that
  role's permitted write scope;
- the frozen `card_bundle_sha256` taken from Queue admission;
- the current `delivery_attempt_id`;
- the delivery state below, and the handoff checkpoint if one exists.

Role topology is runtime metadata. It is never Profile configuration, and an
Assignment never widens a scope the Queue and Profile did not already grant.

## Delivery States

```text
pending      Assignment created against an admitted batch
delivering   at least one piece delivered, ack set incomplete
delivered    ack set complete and Adapter conformance current
running      worker may execute
```

`pending -> delivering` requires one delivered piece. `delivering -> delivered`
requires all of:

- the ack set equals the frozen piece manifest exactly -- no missing, extra,
  duplicated, or foreign record;
- every ack binds the same `assignment_id`, `execution_context_id`,
  `card_bundle_sha256`, and `delivery_attempt_id`;
- the host's declared adapter identity resolves to a current
  inline-delivery conformance registration.

Only `delivered` admits `running`. A runtime that cannot reach `delivered`
may still work, but records `degraded` and MUST NOT claim machine-enforced
Card delivery. Queue `open` is unaffected either way: a human integrator
admits batches without any Assignment at all.

## Attempt Invalidation

Delivery evidence is bound to one attempt in one context, and does not
transfer. A new execution context, a reassignment, a reopened batch, a new
`card_bundle_sha256`, or a revised Profile contract each start a new
`delivery_attempt_id` and void every earlier ack. Recovery is to deliver the
current pieces again, never to carry evidence across the boundary that
invalidated it.

This is deliberately expensive to fake and cheap to redo: re-delivery is
idempotent reading, while a transferable ack would let a context claim
delivery it never received.

## What This Gate Does Not Prove

`delivered` means the frozen bytes were delivered within budget to a
conformant adapter and acknowledged from the same context. It does not prove
the worker read them, understood them, or will obey them. Cognition is not
observable here and no field in this module asserts it.

## Related

- [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|Card Context Activation and Read-back Delivery]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
