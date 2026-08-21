# Routing And Gate Registry

Interface: [Routing And Gate Registry slot](../../README.md#routing-and-gate-registry-slot)

Every subsection of this registry is `None`. That is the minimal legal state
of this slot: the profile adds no supplemental route, no extra L-tier
trigger, no cross-batch Specialized Audit invariant, and no extension gate,
so every task on this profile runs the kernel routes and kernel gates
unchanged. Nothing else in this profile depends on a registration here —
there is no readiness axis, so no readiness gate is required.

## Supplemental Routes

- Registration: None

| Profile route ID: `P:<profile_id>:<route_name>` | Kernel route ID reference | Repo-relative Profile Read Set path |
|---|---|---|

## Additional L-tier Triggers

- Registration: None

| Testable materiality predicate | Why full L-tier review is required |
|---|---|

## Specialized Audit Invariants

- Registration: None

| Judgment Item ID reference | Applicability / trigger predicate | Verification procedure or existing Scan/receipt-source reference | Evidence-reuse predicate/boundary |
|---|---|---|---|

## Batch Review Requirements

- Registration: None

`None` keeps the table empty. A configured row makes one registered Judgment
Item a standing per-batch obligation with machine-checked completion: at
`queued -> open` the row expands against the frozen manifest into an exact
expected record set delivered with the Card Activation Bundle, each expected
record must be answered by one current `profile_batch_judgment` receipt from
`Tools/record_batch_judgment.py`, and `open -> merge-ready` refuses the batch
until the batch-review wrapper binds exactly that set. A requirement differs
from an Extension Gate on purpose: a Gate changes one persisted property
after a judgment, while a requirement proves the judgment happened for every
applicable target and writes nothing back to any page. The first-version
enums are closed — target selector `each-manifest-page` or `batch`, trigger
`before-merge-ready`, producer kind `manual-attestation`, receipt schema
`page-batch-judgment-v1` — and natural-language applicability is deliberately
not accepted, so a declared rule can never be one the machine does not know
when to apply. The Judgment Item and the pass-authority role must both
resolve during `profile-load`; each Judgment Item may be required at most
once. An absent section means no requirements and changes nothing for an
existing Profile.

| Judgment Item ID reference | Target selector: `each-manifest-page` or `batch` | Trigger: `before-merge-ready` | Producer kind: `manual-attestation` | Receipt schema | Pass-authority Role ID reference |
|---|---|---|---|---|---|

## Extension Gates

- Registration: None

`None` keeps the table empty. A configured row is an executable contract, not
a prose reminder: its Gate and transition IDs are each unique; its role,
field/completion values, Judgment Item, semantic owner, producer capability,
receipt schema, and consumer capability must all resolve during
`profile-load`. A `deterministic` row uses `registered-scan-v1` with
`deterministic-gate-result-v1` and its Judgment Item must resolve to exactly
one Registered Scan. A `manual-attestation` row uses
`manual-attestation-v1` with `manual-gate-attestation-v1`; its named
pass-authority role is the producer. The initial transition consumer is
`metadata-transition-integrator-v1`, implemented by
`Tools/apply_metadata_transition.py`; manual evidence is produced by
`Tools/record_gate_attestation.py`, while a deterministic row is adapted from
its exact Registered Scan by `Tools/record_gate_result.py`. These executable
paths are declared in `Tools/operation-capabilities.yaml`, and their stable
no-follow file hashes are part of the compiled Metadata Execution Contract;
changing an implementation therefore invalidates the old Profile/runtime
binding. The producer and consumer both load this
typed row through the selected Profile contract, so neither command accepts a
caller-supplied field schema or policy callback. The field must also be present
in the Profile Metadata Contract extension-field slot, and the installed
Metadata Execution Contract must expose the closed generic Profile-enum
owner-to-page writer. Deterministic evidence executes staged, hashed scanner,
runtime, and Profile-snapshot configuration inputs; it is consumable only while
the bound repository snapshot remains current. Write multiple completion values as
comma-separated code literals. `None` is legal only as the pair field =
`None`, completion values = `None` only for a non-field transition whose
consumer registers the distinct `non-field-transition` operation. The shipped
`metadata-transition-integrator-v1` registers only
`typed-field-metadata-transition`, so it cannot authorize such a row. A
deterministic typed-field Gate declares exactly one completion value: one scan
pass cannot choose among multiple state values.

| Gate ID | Kernel Gate ID or repo-relative owner path, optionally `#heading` | Blocked transition/action ID | Pass-authority Role ID reference | Applicability predicate | Vocabulary field ID or `None` | Registered completion value(s) or `None` | Judgment Item ID reference | Producer kind: `deterministic` or `manual-attestation` | Producer capability | Receipt schema | Consumer capability |
|---|---|---|---|---|---|---|---|---|---|---|---|
