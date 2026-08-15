## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]].
- Next: [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|Cross-page and Control-plane Dimension Map]].

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
| `dimension` | exactly one of the values that registry's `Dimension` cell admits for the Gate ID, where it narrows: a Gate covering several dimensions is not identified by the producer tuple alone, so a receipt that names none of them has not said which obligation it answers. A row carrying `none` takes no such field, and a row carrying `*` names a producer that writes none |
| `target` | the exact object verified |
| `result` | `pass` |
| `details` | the concrete evidence statement; a bare "QA passed" is not one |
| `checked_at` | the UTC verification time, not earlier than the obligation the receipt answers |
| `invalidated_by` | null while the receipt is valid |
| `task_id`, `standards_version` | equal to the live Required Queue values when that Queue exists |
| `selected_profile_manifest` | equal to the live Required Queue value when that Queue exists; `profile-load` additionally requires the exact manifest it verified before a Queue exists |

These identity fields state the run that produced the evidence. A boundary consumes the receipt only while the applicable values still equal the live Queue values, so a receipt written before an adoption changed any of them is history rather than authorization. A producer running where no canonical Queue exists omits all three rather than writing null: an omitted field claims nothing, while an explicit null asserts an identity nobody observed. The one exception is `profile-load`, whose receipt still carries `selected_profile_manifest` because that manifest is the Gate's target even during pre-Task candidate validation.

The same candidate spelling applies when a Queue already exists but R09 checks
a different after Profile: that receipt carries only the candidate manifest
identity and MUST NOT combine the live before Task/Standards identity with the
after manifest. A current-use receipt for the already-selected Profile carries
all three live identity fields normally.

A Gate whose owner requires more binds more, and that owner states the addition: the `batch-review` wrapper additionally binds the batch and the exact Delta page receipt IDs per [[kernel/K12 Quality Assurance/14 Batch Review#Batch Review|Batch Review]], and the close bundle binds the merged-snapshot digest and member chain per [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]].

A `profile-load` receipt additionally carries `profile_snapshot_sha256`,
`profile_contract_fingerprint`, and `profile_load_inputs_sha256`. The first is
the path-sensitive digest of the complete candidate or selected Profile
directory; the second deterministically binds the typed closure derived from the manifest:
dependency edge kinds, their owner and target identities, canonical paths, and
optional heading fragments; the third binds the canonical root-owned Profile
interface and execution-default inputs that governed the derivation. Its
`target` and `selected_profile_manifest` are the same canonical manifest path.
Changing any digest, or resolving the same target bytes through a different
Profile, makes the receipt inapplicable rather than transferable.

A Gate that consumes a Profile-derived compiled artifact additionally carries
that artifact's canonical SHA-256 and the same three Profile-load fingerprints.
The consumer MUST establish byte equality with the deterministic composition
from its one admitted Profile view; a provenance comment or matching path does
not substitute for that equality.

A current `terminal-proof` 1.17 receipt additionally carries
`repository_snapshot_sha256`: the path-sensitive digest of every regular
repository file outside the root `.git/` and `.cambium/` namespaces observed by
the Terminal run. The completion writer MUST compare that digest with current
bytes before authorizing `complete` and at both sides of its Progress and
receipt publications. Historical replay checks that a sealed 1.17 receipt kept
a canonical digest; it does not reinterpret that completed decision against
today's repository.

## Standards-adoption Boundary Authority

A current raw receipt proves only its registered Gate. It does not acquire
Standards-adoption authority merely because an adoption plan names that Gate as
affected. The
[[kernel/K00 Standards Control/12 Control Registry#Standards Revalidation Capability Registry\|Standards Revalidation Capability Registry]]
is the sole leaf-to-owner projection:

- a `semantic-leaf` receipt is member evidence for its registered owner and
  MUST be enumerated by that owner's binding protocol; it MUST NOT be supplied
  directly as authorization for an adoption boundary;
- a `native-owner` receipt authorizes only its ordinary transition, at the
  lifecycle position registered in K00/12; making the same receipt early does
  not discharge that transition;
- `required-queue-consistency`, the sole `immediate-owner`, remains in
  `boundary_gate_reruns` when a current boundary projects it and is the only raw
  Gate receipt a post-adoption revalidation aggregate may consume directly;
- `profile-load` is consumed only as the candidate after-image admission; and
- `mechanism-only`, `unsupported`, and `advisory` receipts never become
  blocking boundary authorization.

An owner receipt does not erase its leaves. Its owner contract binds the exact
member receipt IDs, scope, and fingerprints required for that native decision;
a prose assertion that the members were checked is not an owner chain. A
revalidation aggregate may record native owners deferred to their transitions,
but it neither manufactures those owner receipts nor upgrades a raw leaf into
one.

These rules apply to new current authorization. A transition that already
consumed an aggregate is replayed under that aggregate's producer era, including
the leaf/owner protocol that era recorded. Historical raw receipts and sealed
aggregates stay immutable and are not rejected for lacking fields or owner
links introduced later.

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
