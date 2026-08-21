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
passes it to every child tool as `CAMBIUM_EXECUTION_CONTEXT_ID`. A successful
admission result reached through that interface records:

```text
delivery_mode: host-context-injection
delivery_assurance: machine-delivered
execution_context_id: mcp:<session-id>
```

The same MCP session must consume the admission at `queued -> open`; another
session receives a different ID and is refused. This proves that the exact
tool-result payload entered the named host session. It does not authenticate
the human/Agent identity or prove cognition.

A direct CLI result still carries the complete Bundle, but records
`cli-tool-result`, `degraded`, and no execution-context ID. Queue `open` may
still be written by a human integrator because it is admission, not worker
execution. A runtime or adapter MUST NOT claim machine-enforced Card delivery
from that degraded record.

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

`check_queue --resume-status --json` includes a fresh Bundle delivery for
every active batch. A new MCP session therefore receives the current Cards
before it acts on `next_action`; future Assignment State records the delivery
chain before entering `running`.

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
