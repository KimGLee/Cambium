## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]].
- Next: [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]].

## Purpose And Sole Ownership

This module solely owns active-task Standards adoption: changed-predicate impact, invalidated evidence, and Gate reruns when materialized task identity differs from the canonical adopter Standards state. R09 owns the proposed revision; [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction|K13/15]] owns the state transaction. Initial adoption before task runtime belongs to R09.

## Trigger And Invariants

Batch activation, resume, and completion entry compare the canonical adopter Standards identity with the Task Contract and current task-state objects. A mismatch blocks normal work until adoption commits. Only `active` or `paused` may adopt; stale `completion-candidate` first returns through K13/03.

Explicit changed predicates decide impact. Semantically neutral wording, comments, path-neutral splits, Card projection refreshes, or identity-only changes take the no-predicate-change branch. Changed Gates, Profile bindings, vocabulary, evidence contracts, or acceptance predicates take the predicate-change branch. Adoption stops when the approved revision record and declared impact disagree; a version mismatch alone never authorizes a full-corpus review.

Adoption changes Standards, selected Profile, and loading identity and advances `queue_revision` exactly once. It preserves objective, scope, completion semantics, task state, Queue membership/order/dependencies, batch lifecycle and holds, frozen manifests and Work Specs, content, and `state_revision`. Incompatible bound Work Specs must be upgraded through their owner before adoption.

## Adoption Plan Contract

The registered Standards-adoption-plan machine contract is the sole normative source for the plan's fields, closed values, shapes, and serialization. No prose copy or second state table is authoritative. The plan must bind:

- one stable adoption and task identity;
- exact before and proposed-after Standards, Contract, selected Profile, and
  loading identities;
- exact before-state fingerprints and proposed-after revision relationships;
- the approved governance revision and upstream revision identity;
- explicit changed predicates and their canonical owners;
- invalidated evidence and the predicate, dimension, boundary, reason, and
  revalidation scope that invalidated it;
- concrete enforcement boundaries and their target and owner Gate identities;
- the immediate and deferred Gate projection required by K00/12.

All references must resolve and all managed paths must remain repository contained. Before values must equal current authoritative bytes. The upstream revision is resolved from an explicit Git repository and ref to one full commit SHA, recorded only as `upstream_revision_id`. A Profile-only revision MUST retain that upstream identity and instead bind its new Profile snapshot and typed contract fingerprint. `queue_revision` advances by one while `state_revision` remains unchanged. The proposed Profile must pass `profile-load`; its dependency closure is not thereby added to the task's loaded Kernel set. A predicate, Profile, or loaded-set change advances the Contract version; a pure upstream-identity change may retain it.

### Gate Ownership Projection

Changed predicates identify affected semantic leaves; they do not by themselves authorize a boundary. Each affected Gate is projected through the [[kernel/K00 Standards Control/12 Control Registry#Standards Revalidation Capability Registry|Standards Revalidation Capability Registry]]:

- a special owner is discharged only at its registered after-image admission;
- an immediate owner is claimed by current after-image evidence;
- a native owner remains due at its ordinary lifecycle edge;
- a semantic leaf projects to its registered owner;
- mechanism-only and advisory changes create no blocking claim;
- an unsupported affected Gate makes the plan inadmissible until an owner and
  protocol exist.

Every blocking owner must occur on at least one concrete boundary that reaches an enforceable target. Merely listing a Gate in an aggregate creates no edge. `profile-load` is discharged against the proposed Profile before any state write. `required-queue-consistency` is the immediate after-image owner. Native owners remain deferred to the transitions that already claim them; an adoption aggregate records those obligations but substitutes for none of their receipts.

If a target batch has already passed a native owner's claim edge, neither a fresh leaf receipt nor an aggregate can retroactively authorize it. Adoption is refused until a sanctioned rollback restores the boundary or a successor or Amendment owns the work. Historical evidence under the superseded predicate remains historical evidence, not current authorization.

### Corrective Adoption

Corrective adoption is deliberately asymmetric. The current before Profile is authoritative for identity and impact but need not pass the proposed `profile-load` contract; otherwise an invalid Profile could block the only sanctioned migration away from it. The candidate after Profile must pass. This exception belongs only to the registered Standards-adoption transaction and must not be exposed to ordinary readers, writers, state overrides, pending receipts, or post-write state.

A passing candidate check is not a lease on mutable bytes. At commit, the transaction must re-establish the same candidate Profile identity and contract and reject drift before authority changes. Any uncertain outcome must fail closed while preserving the before images, transaction evidence, and a deterministic recovery path.

## Adoption Branches

For a no-predicate-change adoption, changed predicates, invalidated evidence, and deferred boundary claims are empty. State identities still synchronize, so `required-queue-consistency` reruns; no batch reopens and no evidence is invalidated merely because the Standards identity changed.

For semantic change, predicates are nonempty. Blocking boundaries are present exactly when K00/12 projects a special, immediate, or native owner. Scope follows explicit predicate, owner, Profile, evidence-dependency, and registered Gate edges, never similarity or backlinks.

Affected batches are the union of concrete boundary targets and the Queue batches named by invalidated evidence. An affected `merge-ready` batch requires formal rollback before adoption; an affected `open` batch requires `revalidation-required`. The adoption writer records these requirements but does not perform either transition.

Historical receipt bytes and Queue references produced under the current contract remain unchanged. Explicitly invalidated evidence is stale for current delta, readiness, completion, and recovery authorization; unaffected current-contract evidence remains reusable under K12/07.

Retired runtime protocols, producer identities, and receipt formats are outside Cambium's runtime space and are not parsed, adopted, migrated, or reauthorized. If retained at all, their bytes are external static archives. Current authorization and current-format history use only the current capability registry and its current receipt contracts.

## Acceptance And Resume

Only the registered `standards-adoption` transaction capability may apply an approved plan. A successful commit must make the adopter Standards state, Task Contract, Coverage, Queue, and Progress agree on one after identity; append one evidence-bound Progress adoption record; advance the declared revisions once; preserve historical receipts byte-for-byte; retain explicit invalidations; chain old and new Contract anchors; and pass after-image `required-queue-consistency`.

The transaction receipt substitutes for no deferred owner or semantic member evidence. Before commit, the old identity remains authoritative. After commit, resume follows Queue state and enforces every deferred owner at its registered boundary. An uncertain commit is recoverable through the registered transaction protocol and cannot be treated as either silently committed or silently absent.
