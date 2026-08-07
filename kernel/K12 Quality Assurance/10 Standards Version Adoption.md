## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]].
- Next: [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]].

## Purpose And Sole Ownership

This module solely owns active-task Standards adoption: changed-predicate
impact, invalidated evidence, and gate reruns when materialized task identity differs
from K00/03. R09 owns the revision; [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|K13/15]]
owns the write transaction. Pre-Task initial adoption belongs to R09.

## Trigger And Invariants

Batch activation, resume, and completion entry compare K00/03 with the Contract
and three state objects. Mismatch blocks normal work until adoption commits.
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
selected_profile_manifest_before, selected_profile_manifest_after,
governance_revision_ref, governance_revision_sha256,
standards_snapshot_sha256_after, profile_snapshot_sha256_after,
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

Boundary `target_kind` is one of six values. Only `batch` names its enforcement
scope by itself; the other five reach a rerun only through invalidated evidence
whose `revalidation_scope_ids` name Queue batches, because a deferred gate is
claimed at a batch transition. A boundary reaching no batch by either route is
rejected, not recorded as protection nothing applies.

| `target_kind` | `target_ids` resolve against | Own enforcement point |
|---|---|---|
| `batch` | the Required Queue | each `required_gate_ids` entry holds that batch's next transition |
| `receipt` | the current receipt catalog | none |
| `task` | exactly the plan's `task_id` | none |
| `terminal-audit`, `maintenance-completion`, `profile-load` | unresolved | none |

IDs/references must resolve. Invalidated-evidence `reason_code` is
`predicate-changed`, `receipt-schema-changed`, `profile-binding-changed`, or
`gate-semantics-changed`. Managed paths are repository-contained/non-symlinked.
Before values equal current bytes; Standards version must change.
`queue_revision_after = queue_revision_before + 1`; state revision is invariant.
After Profile/load set resolves. Predicate, Profile-path, or load-set change
bumps `contract_version`; a pure identity no-op may retain it.

`governance_revision_ref` is exactly
`kernel/K00 Standards Control/03 Standards Governance.md`; its SHA binds all
approved bytes, whose active version/Profile equal the plan after identity.
After snapshot SHAs deterministically bind all `kernel/` and the selected
Profile directory.

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

For semantic change, predicates and boundaries are nonempty. Immediate reruns
remain exactly `[required-queue-consistency]`. Deferred reruns equal the sorted
set union of predicate `affected_gate_ids` and boundary `required_gate_ids`;
batch-close/Terminal gates occur only there. Scope follows explicit predicate,
owner, Profile, receipt-dependency, and registered-gate edges, never similarity
or backlinks.

Affected batches are the union of boundary batch targets and Queue batch IDs in
invalidated-evidence revalidation scopes. Affected `merge-ready` batches require formal
rollback first; affected `open` batches require `revalidation-required`. The
writer changes neither.

Historical receipt bytes and Queue references remain unchanged. Accumulated
invalidated-evidence receipt IDs are stale for current
delta/readiness/completion/recovery reuse.
Historical transitions/closed proof use the full catalog and producer-era
identity. Unaffected evidence remains reusable under K12/07.

## Acceptance And Resume

Only `Tools/adopt_standards.py` applies the plan. Commit proves:

1. three-state after identity and Progress after load set agree;
2. Progress appends one entry binding plan, three before SHAs, after
   Coverage/Queue SHAs, and immediate-gate receipt; only commit receipt binds
   the self-containing after Progress SHA;
3. Queue/Progress revision advanced once and all invariants above held;
4. historical receipts stayed byte-identical and invalidations stayed explicit;
5. commit chains old/new Contract anchors; and
6. staged after bytes passed Queue consistency. Deferred gates block only their
   named boundary; the transaction receipt substitutes for no gate.

Before commit, old identity is authoritative. Uncertain writes reconcile from
lock, plan SHA, state SHAs, and prepare/commit/abort chain under K13/15. After
commit, resume follows Queue state and enforces deferred gates at their boundary.
