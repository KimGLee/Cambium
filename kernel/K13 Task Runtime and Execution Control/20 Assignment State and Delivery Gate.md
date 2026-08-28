## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|Card Context Activation and Read-back Delivery]].

## Purpose And Boundary

This module owns the semantic mapping between one admitted batch and one temporary execution context, and the delivery result required before that context may be called `running`. K13/19 owns what is delivered and the evidence for each piece; this module owns whether the required set arrived.

An Assignment is not a second Queue. It carries no work list, batch lifecycle, or completion semantics. A batch is durable work that outlives execution contexts; an Assignment is one attempt by one context to carry it. Losing an Assignment invalidates its delivery evidence but not the batch.

## Assignment Contract

An Assignment may have a Tool-owned machine representation, but its field names, shapes, serialization, and transport encoding are not Kernel rules. Semantically, one Assignment binds:

- a stable Assignment and admitted batch identity;
- the acting execution-context identity and optional parent context;
- the acting role and its already-authorized write scope;
- the frozen delivery-obligation identity;
- one delivery-attempt identity bound to that obligation and context; and
- the delivery result at each applicable boundary and any handoff checkpoint.

Role topology is runtime metadata, not Profile policy. An Assignment never widens the scope granted by Queue and selected Profile.

## Delivery States

Delivery progresses from pending, through partial delivery, to a complete boundary result and then `running`. A boundary becomes delivered only when:

- the observed delivery set equals the frozen required set exactly, with no
  missing, extra, duplicate, or foreign record;
- every evidence record binds the same Assignment, context, frozen obligation,
  and delivery attempt; and
- the declared delivery assurance is externally established for the bound
  context.

Delivered initial context admits `running`. An execution environment unable to establish that result may operate only in explicitly degraded mode and cannot claim machine-enforced Card delivery. Queue `open` remains unaffected because batch admission and context delivery are different decisions.

## Reading Boundary Scope

Initial delivery changes timing, not obligation. Later declared reading boundaries remain due at their consuming lifecycle transitions. The applicable loading declaration owns which content is due; the delivery implementation resolves that declaration. Each boundary result is proved independently under its frozen obligation.

## Attempt Invalidation

Delivery evidence never transfers between attempts or contexts. A new context, reassignment, reopened batch, or change to a frozen delivery input creates a new delivery-attempt identity and invalidates earlier evidence for the affected boundaries. Recovery resolves the current obligation and redelivers what is still due; evidence for an unaffected boundary remains usable only while its own complete binding stays current.

## What This Gate Does Not Prove

Delivered means the complete frozen content was observably delivered to the bound context under the declared assurance. It does not prove that the worker read, understood, or will obey it. Cognition is not observable here and no Assignment field may assert it.

## Related

- [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery|Card Context Activation and Read-back Delivery]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
