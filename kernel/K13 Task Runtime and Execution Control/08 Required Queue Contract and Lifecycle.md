## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|Progress Ledger Contract]].
- Next: [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views|Queue Compilation Replanning and Views]].

## Purpose And Ownership

The Required Queue owns batch manifests, order, dependencies, lifecycle, holds,
and transition evidence. Coverage owns object disposition, owner, and batch
projection; Progress owns task state/contract, Amendments, checkpoints,
completion binding, and Queue reference. Reports/executor lists are not
authority.

## Queue Document Contract

`.cambium/state/required_queue.yaml` follows its Tools schema. Identity includes
schema, task, scope, Standards/profile, both revisions, and `required_queue`.

Every item explicitly supplies `id`, `family`, unique contiguous `order`,
positive `record_count`, nonempty unique `manifest`, nullable `source_route`,
`execution_mode`, `depends_on`, `confirmation_required`, `state`, and
`hold_state`. It also explicitly supplies `work_spec_path` and
`work_spec_sha256` under the Batch Work Specification Binding below.
Dependencies are explicit, acyclic, earlier than dependents, and never
inferred. `concurrent-worker` may coexist; `serial-integrator` is exclusive.

An in-flight manifest is frozen. Coverage projects its sets through `batch` /
`next_batch`; top-level `batch_specs` is compiler input, not lifecycle state,
with exactly `id`, `family`, `order_hint`, `source_route`, `execution_mode`,
`depends_on`, `confirmation_required`, `work_spec_path`, and
`work_spec_sha256`. Outside controlled
replan/cancellation staging, Queue and Coverage sets must be equal.

## Batch Work Specification Binding

A batch whose unique instructions are fully communicated by its Queue
identity, route, manifest, and owning Standards is explicitly simple:
`work_spec_path: null` and `work_spec_sha256: null`. A complex batch binds both
fields to one regular YAML file directly under `.cambium/work_specs/` and
its `sha256:<64 lowercase hex>` byte fingerprint. The pair is always present;
complexity is never inferred from family, manifest size, prose, or route.

The bound file follows `Tools/schemas/batch_work_spec.template.yaml`. The whole
file is the restricted-YAML contract, not Markdown with a machine header. Its
top-level field set is exactly `schema_version`, `batch_id`, `manifest`,
`outcomes`, `instructions`, `acceptance_conditions`, and `constraints`.
`schema_version` is `1`; batch identity and ordered manifest exactly equal the
Queue item; each of the four record lists is nonempty.

Each outcome contains exactly `outcome_id` and `required_result`. Each
instruction contains exactly `instruction_id`, continuous `order` beginning at
one, nonempty `target_scope`, `required_transformation`, and explicit
`depends_on`; dependencies name only earlier instructions. Each acceptance
condition contains exactly `condition_id`, `target_scope`,
`observable_predicate`, and `evidence_requirement`. Each constraint contains
exactly `constraint_id`, `target_scope`, and `requirement`. IDs are stable and
unique within their record kind. A target scope is either exactly `[batch]` or
a nonempty list of exact Queue-manifest paths; the two forms never mix.

The Work Spec contains only instructions unique to this batch. It MUST NOT own
or restate Queue state, Queue order/dependencies, holds, revisions,
fingerprints, transition receipts, or completion state at any nesting depth.
`TODO(batch)` and `REPLACE-ME` are invalid sentinels, so copying the template
without filling its batch-specific values cannot produce a valid binding.

The Queue pair is structural state. A queued batch changes it only through an
approved Amendment and Queue replan. An open batch first enters
`revalidation-required` through the lifecycle owner, then applies a
Work-Spec-only Amendment/replan; the structural writer does not change the
hold itself. The new Queue revision and SHA invalidate old admission and close
evidence. Merge-ready and terminal bindings are immutable; later instructions
use a successor batch.

`check_queue.py` validates the managed path, byte fingerprint, whole-document
closed schema, batch identity, exact manifest, record IDs, instruction graph,
target scopes, and sentinels. Batch-close validation binds the same pair and
proves the bytes did not change during the close gate. A Work Spec is
instruction, not proof: its presence does not satisfy in-batch work, review,
merged checks, or semantic acceptance.

## Revisions And Fingerprints

`queue_revision` increments on structure/verification-contract change;
`state_revision` (externally `queue_state_revision`) on lifecycle/hold change.
References also bind canonical Queue SHA-256. Structure and lifecycle never
hide inside each other.

## Batch Lifecycle

```text
queued -> open -> merge-ready -> closed
queued/open -> cancelled
merge-ready -> open
```

`open` freezes its partition; `merge-ready` has exact delta, receipts, and QA;
`closed` passed serial integration/global gates. Terminal history is immutable;
later work uses a successor. Cancellation needs a scope/disposition Amendment.

`hold_state` independently takes `none`, `confirmation-required`, `blocked`,
`revalidation-required`, or `paused`; it is neither lifecycle nor task state.
Each non-queued item retains ordered `transition_receipts` binding task/item,
before/after state/hold, revision edge, Queue revision/fingerprints, tool, and
integrator. State fields record timezone-aware timestamps and required
activation/confirmation/delta/batch/close/cancellation/successor evidence.
Referenced receipts must exist, pass, remain valid, and match mode/scope.
