## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/18 Initial Task Planning Transaction|Initial Task Planning Transaction]].
- Next: [[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|Assignment State and Delivery Gate]].

## Purpose And Boundary

This module owns the implementation-independent boundary between a frozen reading obligation and its observable delivery to one execution context. The route and loading owners determine what must be read; this module does not repeat their member lists, phase mappings, or read-back predicates.

Queue admission proves that work may begin. It does not prove that governance content reached a later execution context. Context delivery is a separate result consumed through the Assignment boundary in K13/20. Neither result proves that an Agent read, understood, or obeyed the delivered material.

## Activation Delivery Contract

Before an execution context is treated as running, the delivery boundary must bind:

- the current task, admitted work, Standards, selected Profile, and frozen
  loading-selection identities;
- an exact manifest of the Card projections and canonical read-back targets
  due at that boundary;
- the content identity of every delivered target and of the complete manifest;
- the receiving execution context and one non-transferable delivery attempt;
  and
- evidence that the required manifest and the observed deliveries agree
  exactly.

Preparing or recording a manifest is not delivery. Delivery is established only after the target content has crossed the declared delivery boundary and the result is bound back to the same context and attempt. An execution environment that cannot make that result observable may operate only under an explicitly degraded claim; it cannot assert machine-enforced delivery.

Delivery evidence does not transfer to a different context or attempt. A changed loading selection, Card projection, canonical target, Standards or Profile identity, or other manifest input invalidates the affected evidence. Historical evidence remains historical and is interpreted under the contract that produced it; it cannot authorize delivery under a newer manifest.

## Packaging And Transport Boundary

A Tool implementation may package or partition the frozen payload to fit its transport, provided that packaging does not change target membership, content identity, phase obligation, or the observable completeness of delivery. It must detect truncation, externalization, omission, duplication, foreign acknowledgement, and content drift whenever it claims machine-enforced delivery.

The current protocol identity, field names, serialization, byte budgets, chunking rules, command flags, session identifiers, environment variables, nonce and acknowledgement design, and environment-conformance checks belong to the Tool engineering contract. Retired activation protocols are not parsed or replayed. Kernel requires only the externally observable result: exact current content is delivered completely to the bound context, or the claim fails closed.

## Progressive Read-back

Read Set owns the declared targets and the conditions under which they become due. This module owns only their delivery result. A semantic condition may be declared by the Agent or user; an observable lifecycle or Gate condition may be reported by its deterministic owner. Neither path may create a target absent from the frozen loading boundary.

Once a condition is established, read-back must bind the triggering rule, the frozen target, its current content identity, the parent activation, and the receiving context. If the applicable subcondition cannot be resolved safely, the complete declared boundary for that condition is due. Silent omission and undeclared whole-Kernel injection are both invalid fallbacks.

## Failure And Resume

Activation and read-back fail closed when a required target or identity cannot be resolved, content no longer matches the frozen commitment, the context or attempt changes, the host cannot support the asserted delivery assurance, or the observed evidence is incomplete or inconsistent.

Resume re-evaluates the current manifest and re-earns delivery for the new context at every phase that is still due. Recovery never converts a prepared manifest, stale receipt, matching hash alone, or successful process exit into proof of delivery. It either establishes the current observable result or returns the work to the owner of the changed loading, governance, or runtime state.

## External Result Contract

The registered `card-context-delivery-v1` capability must expose:

- the frozen selection and payload identities it consumed;
- the execution context and attempt to which the result applies;
- the exact delivery set and its completeness status;
- explicit degraded or failed assurance when delivery cannot be proved; and
- structured rejection reasons sufficient to return to the correct owner.

Its registered consumers may write delivery evidence to adopter runtime state, but the capability does not own the underlying Card, Read Set, Profile, Kernel rule, Queue lifecycle, or host transport policy.

## Related

- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|Assignment State and Delivery Gate]]
