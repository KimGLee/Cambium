## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]].

## Purpose

This module owns one object: what a receipt MUST carry to be consumed as current authorization for a Gate ID, and who may record one when the registered producer is `manual-attestation`. Those receipts are written by a person or an agent rather than emitted by a script, so without this contract their producer has no statement of the fields the consumer compares, and learns the payload only from a rejection.

It states no field meaning, no reuse or invalidation rule, and no receipt dimension: those stay with [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Dimension-specific Audit Receipt|K12/07]]. The Gate ID and its producer tuple stay with [[kernel/K00 Standards Control/12 Control Registry#Control Registry|Control Registry]]. The identity values are read from the canonical Required Queue owned by [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]] and the active Standards state of [[kernel/K00 Standards Control/03 Standards Governance#Standards Control|K00/03]]. This module adds no Gate ID and no judgment item.

## Gate Receipt Payload

A receipt offered as current authorization for a Gate ID MUST carry all of the following:

| Field | Required value |
|---|---|
| `receipt_id` | this record's append-only ID, never reused |
| `gate_id` | exactly the Gate ID being authorized |
| `tool`, `tool_version`, `check` | exactly the producer tuple registered for that Gate ID in the [[kernel/K00 Standards Control/12 Control Registry#Stable Gate ID Registry\|Stable Gate ID Registry]]; a hand-recorded receipt uses the `manual-attestation` producer class and its current protocol version |
| `target` | the exact object verified |
| `result` | `pass` |
| `details` | the concrete evidence statement; a bare "QA passed" is not one |
| `checked_at` | the UTC verification time, not earlier than the obligation the receipt answers |
| `invalidated_by` | null while the receipt is valid |
| `task_id`, `standards_version`, `selected_profile_manifest` | equal to the live Required Queue values |

The last three are the identity of the run that produced the evidence. A boundary consumes the receipt only while all three still equal the live Queue values, so a receipt written before an adoption changed any of them is history rather than authorization. A producer running where no canonical Queue exists omits the three fields rather than writing null: an omitted field claims nothing, while an explicit null asserts an identity nobody observed.

A Gate whose owner requires more binds more, and that owner states the addition: the `batch-review` wrapper additionally binds the batch and the exact Delta page receipt IDs per [[kernel/K12 Quality Assurance/14 Batch Review#Batch Review|Batch Review]], and the close bundle binds the merged-snapshot digest and member chain per [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]].

## Recording Authority

The actor recording a `manual-attestation` receipt MUST hold the authority for the decision it attests. Where the Gate's owner module names that actor, the naming governs: Batch Review gives the `batch-review` gate to the integrator, and Batch-close Closed List requires distinct integrator and reviewer labels on the close bundle. Where no owner module names one, the authority is the actor bound to `gatekeeper` in the selected profile's `Role Registry`; a profile-registered extension gate instead uses the pass-authority Role ID that gate declares. One actor MAY hold several roles.

This section constrains who may record an attestation. It registers no additional receipt field, and recording one remains an audit assertion rather than authentication, within the boundary stated by [[kernel/K12 Quality Assurance/16 Terminal Proof Contract#Evidence Trust Boundary|Evidence Trust Boundary]].

## Consumption And Rejection

Which layer may consume which Gate ID is decided by the Consumption boundary column of Control Registry; this section states only what makes a receipt unusable there.

A consumer resolves the receipt in the current catalog, never in history, and rejects it whenever the payload above does not hold: a Gate ID or producer tuple that misses the registry, a `result` other than `pass`, a set `invalidated_by`, an identity field differing from the live Queue, or a `checked_at` preceding the obligation it is offered against. The deterministic consumers are `Tools/check_queue.py` at a Standards revalidation boundary under [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]] and at the `open -> merge-ready` transition.

Rejection removes authorization, not the record. Receipts are append-only: a rejected receipt remains immutable history, reusable for the historical claims it still supports under K12/07.

## Related

- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
