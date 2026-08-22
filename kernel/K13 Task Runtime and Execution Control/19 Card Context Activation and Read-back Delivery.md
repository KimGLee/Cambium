## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/18 Initial Task Planning Transaction|Initial Task Planning Transaction]].

## Purpose And Boundary

This module owns the boundary between a frozen reading obligation and the
bytes delivered to one execution context. The Task Contract says which routes,
Cards, Read Sets, and modules are required or reachable; it is not evidence
that a later Agent received them. The Card Activation Bundle and Read-back
Addendum are the delivery evidence. Kernel source remains normative, Runtime
Cards remain compiled guidance, and this module does not claim that a model
understood or obeyed either one.

Queue lifecycle and context lifecycle stay separate. `open` means a batch is
admitted and its partition reserved. A host/runtime may call a worker `running`
only after the exact activation payload has entered that worker's execution
context. No reading ledger or scheduler ledger is created here.

## Frozen Reading Plan

The initial Task Plan and later Standards adoption resolve these fields from
the canonical Card/Read Set registries:

```text
selected_route_ids
selected_card_paths
selected_profile_route_ids
selected_read_sets
loaded_module_paths
```

Every current plan includes R01 plus the route for the work. The latter three
fields are the complete allowed/required loading envelope, not an assertion of
past behavior. Their canonical Task Contract fingerprint becomes
`task_contract_sha256`; the five-field projection has its own
`reading_plan_sha256`.

## Card Activation Bundle

`check_queue --require-ready <batch>` compiles one
`card-first-readback-v1` object from exact repository snapshots. It contains:

- task, batch, Standards, Profile, Task Contract, Card Index, reading-plan,
  and read-back-plan identities;
- full bytes plus hashes for R01 and every Card selected by the contract;
- exact Card Index startup bytes when selected; it remains a registry, not an
  Rxx route;
- each Card's paired Read Set hash and equal `source_hash` /
  `compiled_source_hash`, so unacknowledged semantic drift blocks activation;
- full bytes for a selected Profile supplemental Read Set, because it has no
  kernel Runtime Card; and
- full bytes for each source whose Card declares
  `readback_policy: activation`, plus the remaining declared Addendum rules.

The content-addressed manifest produces `card_bundle_sha256` and is stored in
the admission receipt; exact text is a transient tool-result payload, not
duplicated in JSONL. `queued -> open` recompiles it from current bytes,
requires exact equality, and copies its hashes and delivery bindings.
Historical replay validates embedded commitments under that producer era; it
does not reinterpret an already-opened batch using new Card bytes.

## Execution-context Delivery

The stdio MCP server assigns one non-reused ID to each initialized session and
passes it to every child tool as `CAMBIUM_EXECUTION_CONTEXT_ID`, together with
the host's declared `clientInfo` name and version as
`CAMBIUM_HOST_CLIENT_NAME` and `CAMBIUM_HOST_CLIENT_VERSION`. Those are
declared labels: they identify which adapter build ran, not who ran it.

An admission records what it prepared, never what a later reader received:

```text
delivery_mode: host-context-injection
delivery_assurance: host-bound
execution_context_id: mcp:<session-id>
```

A direct CLI admission records `cli-tool-result`, `prepared`, and no
execution-context ID. Queue `open` consumes either, because `open` is
admission and not worker execution; what it still proves is that the frozen
Bundle equals current Card and Read Set bytes.

Earlier eras claimed more here than the transport could support. A v1/v2
admission that reached a bound session recorded `machine-delivered` and
required the same session to consume it at `queued -> open`. That claim was
minted before the result left the server, so a host that externalized an
oversized tool result left the payload outside the model context while the
receipt still asserted delivery, and no gate could observe the divergence.
The session-identity rule is retired -- keeping it would re-couple the Queue
lifecycle to the context lifecycle this module separates -- and delivery
completion is earned per piece rather than asserted at admission.
[[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|K13/20]]
defines completion;
[[kernel/K13 Task Runtime and Execution Control/21 Phased Reading Plan|K13/21]]
names the writers that refuse to act without it.

## Budgeted Piece Delivery

Protocol `card-first-readback-v3` stopped embedding Card and read-back bytes
in the admission result. Admission freezes a piece manifest -- one record per
deliverable file, carrying `piece_id`, `kind`, `path`, `sha256`, and `bytes`
-- and the bytes travel afterwards.

`card-first-phased-readback-v4` freezes the same records and adds the phase
each belongs to, so bytes travel one phase part per result rather than one
file per result. Grouping changes no commitment: every file in a part keeps
its own frozen hash and is re-proved against current bytes at delivery. The
phase set is owned by
[[kernel/K13 Task Runtime and Execution Control/21 Phased Reading Plan|K13/21]].

A piece is always a whole file, and a part holds whole files only. Splitting
one file across results is invalid: the frozen hash binds the complete file,
a receiving model cannot rehash fragments, and no party could then prove a
reassembly was faithful.

`MAX_ACTIVATION_PIECE_ENVELOPE_BYTES` is 49152 and is owned here. The measured
object is the complete serialized delivery, not the source file: envelope,
JSON escaping, nonce, and transport wrapper all count. Under v4 that object
is the phase part. Admission fails closed when any frozen piece would exceed
the budget alone, so an oversized leaf is caught
as a governance problem at its own boundary rather than as a transport
accident mid-batch. [[kernel/K00 Standards Control/16 Leaf Module Size Register|K00/16]]
carries the derived check for `activation` leaves; it consumes this budget and
does not own it.

`check_queue --deliver-activation-piece <batch> --piece <piece-id>` returns one
piece for an already-open batch. The server re-reads the current bytes and
refuses when they differ from the frozen hash, so a source that drifts during
delivery is rejected rather than shipped. Each delivery carries a single-use
nonce placed after the content, and
`check_queue --ack-activation-piece <batch> --piece <piece-id> --piece-nonce
<nonce> --piece-delivery-receipt <id>` returns it from the same execution
context.

The nonce is one part of a three-part guarantee and never the whole of it:

- the server hash proves the delivered object is the frozen file;
- a Host Adapter that has passed inline-delivery conformance proves a
  within-budget result is inlined rather than truncated or externalized;
- the same-context ack proves this execution context consumed the delivery.

Only all three together constitute piece delivery evidence. The ack alone
proves that a nonce was seen, not that the body ahead of it entered the model
context: a host may show a head-and-tail summary, keep structural fields while
externalizing content, surface the nonce separately, or leave an agent reading
only the tail of a spilled file. A host that cannot supply the middle part is
`degraded`, and no runtime may claim machine-enforced delivery from it.

## Frozen Review Plan

Protocol `card-first-readback-v2` adds one delivery-independent commitment to
the Bundle: the Profile's Batch Review Requirements expanded against the
frozen manifest. The expansion is deterministic — each `each-manifest-page`
row over the sorted manifest, each `batch` row over the batch itself — and
its identity hash is `review_requirement_set_sha256`, carried in the
admission receipt and recompiled to exact equality at `queued -> open`. The
Bundle's `batch_review_plan` delivers the same records readably, so the
executing Agent starts with its judgment obligations in context rather than
discovering them at refusal. Per-record evidence is produced by
`Tools/record_batch_judgment.py` while the batch is `open`;
`open -> merge-ready` consumes the exact set through the batch-review
wrapper per [[kernel/K12 Quality Assurance/14 Batch Review|K12/14]]. A v1
activation predates the plan: it replays under its own protocol, carries no
review field, and imposes no judgment obligations — reactivation under the
current protocol is what upgrades an in-flight batch.

## Progressive Read-back

Each Runtime Card declares one closed policy alongside `readback_sources`:

- `none`: the list is empty;
- `activation`: every listed source is included in startup context; or
- `declared`: each source becomes a stable rule in the Bundle's
  `readback_plan` and stays out of startup context.

For a declared rule, `check_queue --deliver-readback <batch>
--readback-rule <rule-id>` reopens the registered path safely, requires its
hash still to equal activation, and returns a `card-readback-addendum-v1`
object carrying the exact source text. The Addendum binds its rule and parent
Bundle. Semantic conditions that no deterministic transition can observe are
declared by the Agent/user after receiving the Card; lifecycle and Gate
conditions are triggered by the integrator. When the exact subcondition is
unclear, deliver all declared sources for that selected route. Silent skip and
whole-Kernel injection are both invalid fallbacks.

## Resume Reassignment And Failure

`check_queue --resume-status --json` re-freezes a current Bundle manifest for
every active batch, so a new MCP session learns which pieces it must pull
before it acts on `next_action`; the bytes follow one budgeted piece at a
time. A new execution context invalidates every earlier ack: delivery evidence
never transfers between contexts, and
[[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|K13/20]]
requires the set to be re-earned. Under v4 that set is the preflight phase
plus the phase being resumed into: phases already earned stay proved by
their own receipts under the plan hash they were earned against, and
re-earning unused phases would make resume cost grow with task progress.

Activation or read-back fails closed when R01 or a selected Card is absent,
the Card Index disagrees with the contract, semantic hashes differ, a path is
unsafe/non-UTF-8, embedded bytes do not match their hash, current Queue/Task
identity drifts, a machine context changes between admission and open, a rule
is unregistered, or a read-back source changes after activation. Recovery is
to rerun current admission/delivery or perform the applicable Standards/task
transition, never to restamp the receipt.

## Related

- [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[kernel/K00 Standards Control/15 Read Set Loading Boundaries|Read Set Loading Boundaries]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate|Assignment State and Delivery Gate]]
