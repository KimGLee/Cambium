## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]].
- Next: [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]].

## Purpose And Sole Ownership

This module solely owns active-task Standards adoption: changed-predicate
impact, invalidated evidence, and gate reruns when materialized task identity
differs from the canonical adopter Standards state. R09 owns the revision;
[[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|K13/15]]
owns the write transaction. Pre-Task initial adoption belongs to R09.

## Trigger And Invariants

Batch activation, resume, and completion entry compare
`.cambium/governance/standards_state.yaml` with the Contract and three task
state objects. Mismatch blocks normal work until adoption commits.
Only `active` or `paused` may adopt; stale `completion-candidate` first returns
through K13/03.

Explicit changed predicates decide impact. Semantically neutral wording,
comments, path-neutral splits, Card restamps, or version-only changes take the
no-predicate-change branch. Changed gates, Profile/vocabulary/route/evidence
contracts, or acceptance predicates take the predicate-change branch. Stop if
the revision record disagrees; version mismatch alone never means full-corpus
review.

Adoption changes Standards/Profile/load-set identity and advances
`queue_revision` once. It preserves objective, scope, completion semantics,
Task state, Queue `state_revision`/membership/order/dependencies, all batch
lifecycle/holds/manifests/Work Specs, and content. Incompatible bound Work
Specs must be upgraded through their owner before adoption.

## Restricted-YAML Adoption Plan

The sole persistent input is
`.cambium/deltas/standards-adoptions/<adoption-id>.yaml`, validated by
`Tools/schemas/standards_adoption_plan.template.yaml`. No prose copy or second
state table is allowed. Exact top-level fields:

```text
schema_version, adoption_id, task_id, task_state_before,
contract_version_before, contract_version_after,
standards_version_before, standards_version_after,
standards_effective_date_after, standards_state_sha256_before,
selected_profile_manifest_before, selected_profile_manifest_after,
governance_revision_ref, governance_revision_sha256,
upstream_source_ref, upstream_revision_id,
standards_snapshot_sha256_after, profile_snapshot_sha256_after,
profile_contract_fingerprint_after, profile_load_inputs_sha256_after,
selected_route_ids_after, selected_card_paths_after,
selected_profile_route_ids_after, selected_read_sets_after,
loaded_module_paths_after, queue_revision_before, queue_revision_after,
queue_state_revision_before, coverage_sha256_before,
required_queue_sha256_before, progress_sha256_before, changed_predicates,
invalidated_evidence, invalidation_boundaries, immediate_gate_reruns,
boundary_gate_reruns
```

Closed rows:

- predicate: `predicate_id`, `owner_path`, `change_kind`, `affected_gate_ids`;
- invalidated evidence: `receipt_id`, `predicate_ids`, `dimension_ids`, `boundary_ids`,
  `reason_code`, `revalidation_scope_ids`;
- boundary: `boundary_id`, `predicate_ids`, `target_kind`, `target_ids`,
  `required_gate_ids`.

Boundary `target_kind` is one of six values. `batch` names a deferred
enforcement scope by itself. `profile-load` names the candidate after Profile
and is enforced during plan admission, before any state write. The other four
reach a rerun only through invalidated evidence whose
`revalidation_scope_ids` name Queue batches, because their deferred gates are
claimed at a batch transition. Except for a `profile-load` boundary already
discharged at admission, a boundary reaching no batch by either route is
rejected, not recorded as protection nothing applies.

| `target_kind` | `target_ids` resolve against | Own enforcement point |
|---|---|---|
| `batch` | the Required Queue | each `required_gate_ids` entry holds the transition it belongs to |
| `profile-load` | exactly the plan's one `selected_profile_manifest_after` | after-image plan admission, before any state write |
| `receipt` | the current receipt catalog | none |
| `task` | exactly the plan's `task_id` | none |
| `terminal-audit`, `maintenance-completion` | unresolved | none |

A `profile-load` boundary's `target_ids` MUST be exactly the one-element list
containing `selected_profile_manifest_after`, and its `required_gate_ids` MUST
include `profile-load`; it MAY also name downstream gates affected by the same
changed predicate. The canonical producer validates the after image and emits
the gate result during admission. `profile-load` is therefore removed from the
post-admission immediate/deferred rerun projections; the boundary's other
required gates still need ordinary invalidated-evidence reachability to a
Queue batch and remain enforced at their registered positions.

Changing `selected_profile_manifest` is itself a Profile-authority predicate
change even when two packages currently contain equivalent bytes: a
path-bound `profile-load` result cannot transfer to another manifest. Such a
plan MUST declare at least one changed predicate whose `affected_gate_ids`
contains `profile-load`, and exactly one `profile-load` boundary MUST reference
every predicate that names that Gate. The same unique-boundary rule applies
when a same-path revision explicitly declares a Profile-load-affecting
predicate. A semantically neutral same-path revision need not invent one.

For a plan admitted under the current producer, `affected_gate_ids` record the
semantic leaves actually affected. They are not copied into boundary
authorization. The planner MUST project each value through the
[[kernel/K00 Standards Control/12 Control Registry#Standards Revalidation Capability Registry\|Standards Revalidation Capability Registry]]:

- `special-owner` is discharged only by its registered after-image admission;
- `immediate-owner` is claimed by the adoption's current after-image receipt;
- `native-owner` projects to itself and is deferred to its ordinary transition;
- `semantic-leaf` projects to its registered owner, never to a raw leaf
  receipt;
- `mechanism-only` and `advisory` create no blocking boundary claim; and
- `unsupported` makes a changed predicate naming that Gate unadmittable until K00/12 assigns
  an owner and protocol.

Each `required_gate_ids` entry is therefore an owner Gate ID, not an inventory
of raw findings. Every blocking owner projected from a predicate MUST occur on
at least one concrete invalidation boundary that references that predicate.
`boundary_gate_reruns` is only the exact sorted projection of post-admission
boundary owners: the `immediate-owner` and every `native-owner` reached by the
plan. Placing a Gate in that union creates no edge and cannot compensate for an
omitted owner boundary. `profile-load` is excluded because admission already
discharged it. `required-queue-consistency` is not excluded: when a current
boundary projects that owner it remains in `boundary_gate_reruns`, and its
immediate receipt is the revalidation aggregate's sole raw due receipt.
Advisory-only and mechanism-only changes may leave that projection empty.

Owner claims are consumed only at their registered claim edge. `profile-load`
is the special after-image admission above. `required-queue-consistency` is the
only immediate raw Gate receipt: it binds the staged after Queue, Coverage,
Progress, Profile identity, and repository snapshot at adoption commit. When a
boundary names that owner, the aggregate consumes this same receipt as its
only raw due receipt; the owner remains visible in `boundary_gate_reruns`.
Every native owner is deferred to the transition that already requires it --
`queued -> open`, `open -> merge-ready`, `merge-ready -> closed`, or the
registered Queue-exhaustion/completion edge. The revalidation aggregate records
that deferred owner; it does not demand a second receipt early and does not
substitute for the native transition receipt.

If a target batch has already passed a native owner's claim edge, neither a
fresh leaf receipt nor an aggregate may call the obligation complete. The plan
is refused until a sanctioned rollback puts the batch before that edge, or a
successor/Amendment owns the work. Historical evidence made under the
superseded predicate is evidence of that historical attempt, not current
authorization.

IDs/references must resolve. Invalidated-evidence `reason_code` is
`predicate-changed`, `receipt-schema-changed`, `profile-binding-changed`, or
`gate-semantics-changed`. Managed paths are repository-contained/non-symlinked.
Before values equal current bytes; Standards version must change.
`queue_revision_after = queue_revision_before + 1`; state revision is invariant.
The after Profile passes `profile-load`; the load set resolves independently
and Profile-closure members are not added to `loaded_module_paths`. Predicate, Profile-path, or load-set change
bumps `contract_version`; a pure identity no-op may retain it.

`governance_revision_ref` is exactly
`kernel/K00 Standards Control/03 Standards Governance.md`; its SHA binds all
approved governance-rule bytes. The separate
`standards_state_sha256_before` binds the current adopter identity, and
`standards_effective_date_after` becomes the next state's effective date.
After snapshot SHAs deterministically bind all `kernel/` and the selected
Profile directory. The 1.3 producer persists the exact typed dependency graph
as `profile_contract_fingerprint_after`; the 1.4 producer additionally
persists the fingerprint of the complete canonical profile-load root-input closure as
`profile_load_inputs_sha256_after`; the 1.5 producer additionally records
the upstream identity pair (`upstream_source_ref`, `upstream_revision_id`)
-- the distribution publishes no version numbers, so this pair, or its
explicit null form declaring no upstream, is what makes upstream and
downstream comparable. Both values are identical across the plan,
prepare/commit receipts, Progress record, and writer-lock intent, and are
re-CAS before state writes, after state writes, and immediately before and
after final receipt publication. A sealed pre-1.3 chain may omit the contract
fingerprint, and a sealed pre-1.4 chain may omit the root-input fingerprint;
when a legacy chain carries either field it remains canonical and identical
across that chain. Replay selects these rules from the commit receipt's
producer version, applies no later Profile path/boundary rule, and never
reparses the current Profile. The
passing Profile closure guarantees that every
Profile-owned dependency is inside that directory; its `profile-load`
contract fingerprint binds the typed edges that the directory digest alone
cannot express.

Corrective adoption is deliberately asymmetric. The current before Profile
is authoritative for recording identity and impact, but it need not pass the
new `profile-load` contract: requiring that would withhold the sole sanctioned
transaction that can migrate away from an invalid Profile. The candidate
after Profile MUST pass. A failing after image blocks plan admission rather
than being written into runtime state.

This asymmetry is an explicit transaction capability, not the default runtime
rule. Ordinary readers and writers MUST require full `profile-load` from
`validate_runtime`; only the adoption's persisted current/before read may use
the smaller identity/sentinel guard, and that guard MUST be unavailable to a
state override, pending receipt, candidate after image, or post-write state.

Plan admission is not a lease on mutable Profile bytes. It captures the
candidate manifest, Profile snapshot, and typed-contract fingerprint without
publishing that candidate result into the current Queue receipt identity. On
apply, the writer MUST rerun full `profile-load` and compare all three under
the shared lock before the first write, after the state writes, and immediately
before and after final receipt publication. Pre-commit drift restores the
four before images and records abort. If commit evidence may already be
durable, rollback still restores those state bytes and records abort, but the
writer lock remains for explicit reconciliation.

## Adoption Branches

No-predicate-change is exactly:

```text
changed_predicates: []
invalidated_evidence: []
invalidation_boundaries: []
immediate_gate_reruns: [required-queue-consistency]
boundary_gate_reruns: []
```

State bytes still synchronize, so Queue consistency reruns; nothing reopens.

For semantic change, predicates are nonempty. Apart from a required
`profile-load` after-image boundary, post-admission blocking boundaries are
nonempty exactly when the K00/12 capability projection produces an immediate
or native owner. Immediate reruns remain exactly
`[required-queue-consistency]`. `boundary_gate_reruns` equals the sorted union
of those post-admission boundary owners after removing only `profile-load`,
which admission already discharged. A projected `required-queue-consistency`
therefore remains in the union and supplies the aggregate's sole raw due
receipt; native owners remain deferred to their registered transitions. The
union never lists semantic leaves, advisory Gates, or mechanism-only Gates.
Scope follows
explicit predicate, projected owner, Profile, receipt-dependency, and
registered-gate edges, never similarity or backlinks.

Affected batches are the union of boundary batch targets and Queue batch IDs in
invalidated-evidence revalidation scopes. Affected `merge-ready` batches require formal
rollback first; affected `open` batches require `revalidation-required`. The
writer changes neither.

Historical receipt bytes and Queue references remain unchanged. Accumulated
invalidated-evidence receipt IDs are stale for current
delta/readiness/completion/recovery reuse.
Historical transitions/closed proof use the full catalog and producer-era
identity. Unaffected evidence remains reusable under K12/07.

Producer-era identity means no historical receipt is re-judged against a
current producer constant. A revision that moves a producer's `Tool version`
retires the value earlier receipts carry, and nothing may restamp sealed
evidence. A historical validator MUST instead accept only a
`standards_version` this instance's own chain accounts for — an adoption
record's before or after version, or the live identity where no adoption
occurred — and MUST NOT compare `tool_version` against the current constant.
Current authorization is unaffected: it still requires the registered producer
tuple exactly, per K12/17.

The capability registry follows the same producer-era boundary. A consumed
historical aggregate keeps the leaf/owner and claim-edge meaning recorded by
its own producer era; the current registry is not applied backward to invent a
missing owner, revoke a consumed transition, or require a field its producer
never promised. New plans and new authorization use only the current
capability table.

## Acceptance And Resume

Only `Tools/adopt_standards.py` applies the plan. Commit proves:

1. adopter Standards state and three-task-state after identity agree, and the
   Progress after load set is complete;
2. Progress appends one entry binding plan, four before SHAs, after
   Coverage/Queue SHAs, and immediate-gate receipt; only commit receipt binds
   the self-containing after Progress SHA;
3. Queue/Progress revision advanced once and all invariants above held;
4. historical receipts stayed byte-identical and invalidations stayed explicit;
5. commit chains old/new Contract anchors; and
6. staged after bytes passed Queue consistency. Deferred owner Gates block only
   their native boundary; the transaction receipt substitutes for no owner or
   semantic member evidence.

Before commit, old identity is authoritative. Uncertain writes reconcile from
lock, plan SHA, state SHAs, and prepare/commit/abort chain under K13/15. After
commit, resume follows Queue state and enforces deferred gates at their boundary.
