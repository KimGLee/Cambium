## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]].
- Next: [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|Global Map Contract]].

## Purpose And Ownership

This module is the sole kernel owner of the cross-layer, runtime, and audit boundaries,
deterministic validation, receipt freshness, affected-path projection, and
agent query boundary for Corpus Planning. K02/03 owns applicability,
lifecycle, and reconciliation. K02/05, K02/06, and K02/07 own the exact record
contracts. The selected profile supplies paths, scale, and pass authority; it
does not redefine these runtime or gate boundaries.

## Runtime And Audit Boundaries

Coverage remains the sole owner of page or not-yet-created object disposition,
canonical owner, prerequisites, and approved batch projection. The Required
Queue remains the sole owner of batch manifests, order, dependencies,
lifecycle, holds, revisions, fingerprints, and transition evidence. Progress
remains the sole owner of task contract and task state. The three
corpus-planning artifacts MAY reference stable object IDs or paths from those
owners, but MUST NOT copy their mutable state into a second hand-maintained
control plane.

[[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]]
owns evidence reuse, invalidation, receipts, and bounded systemic expansion for
specialized audits. A finding MAY identify an unadmitted semantic gap for the
Gap Register, or an accepted repair object for Coverage and Queue, but neither
the finding nor the register replaces the canonical AuditPlan, AuditReceipt,
Coverage, or Queue. Conversely, a corpus-planning pass does not constitute a
specialized audit, Module Review, Terminal Audit, or Terminal Proof.

When `Corpus Planning` has `applicability.state: configured`, an affected-scope audit MAY use only the Global Map's
explicit downstream edges, the Matrix's explicit canonical-owner and Gap
links, and the Gap Register's explicit capability/target links to form the
initial affected set. It still verifies that set against the changed predicate
and applies bounded systemic expansion. Corpus Planning supplies scope inputs;
it does not select an audit result or make semantic-similarity inferences.

## Explicit Affected-path Projection

For deterministic batch-close applicability, the Corpus Planning affected set
is projected only from validated explicit path fields: the selected Profile
manifest, Profile Scope, Corpus Planning slot, and three artifact bindings;
every Global Map
Entry path; every Matrix canonical and evidence path; and every Gap promoted
and evidence path. The checker consumes the normalized repository-relative
paths it already parsed while validating these contracts. Layer directories,
typed-edge endpoints, capability or gap prose, backlinks, basename matches,
and semantic similarity MUST NOT be expanded into additional paths. An
operator who needs a broader planning gate explicitly changes the planning
scope under its canonical owner; the runtime does not infer scope.

## Machine Gates And Agent Query

The `global-map`, `capability-matrix`, and `gap-register` machine contracts are
the unique normative carriers of their closed field sets. K02/03 owns their
lifecycle; this module owns the two distinct Gates that consume those records.
The shared Corpus Planning receipt-binding fields, applicability-dependent
path/SHA currentness classes, and the `R13` / `manifest` close-trigger
identities are carried once by
[`corpus-planning-contract.yaml`](corpus-planning-contract.yaml).
Gate producers and consumers MUST use that projection; neither side may keep a
parallel binding or trigger list.

The registered producer for Gate ID `corpus-plan-structure` validates a
configured adopter after changing a bound
artifact, promoting a Gap, closing an affected batch, or entering an applicable
module or task-completion gate. It validates paths, stable identities, explicit
relations, scale membership, bidirectional links, and promotion reconciliation.
Its pass proves only structure and reconciliation; semantic acceptance remains
a separate result and the two decisions are never collapsed into one verdict.

The registered producer for Gate ID `corpus-plan-semantic-acceptance` consumes
one machine-readable decision plan under the `corpus-plan-acceptance-plan`
contract. The plan names
every current Capability ID exactly once, in Matrix order, with `accepted` or
`rejected`, a rationale, the Profile-bound authority Role ID, and the closed
decision-scope ID. The producer validates that envelope and the deterministic
rank boundary but does not invent the authority's semantic decision.

An applied decision appends two separate AuditReceipts: a fresh
`corpus-plan-structure` receipt and a
`corpus-plan-semantic-acceptance` receipt that names the former. Both bind the
exact Profile and planning-artifact identities, task and Queue identity,
applicability, and repository snapshot. The semantic receipt additionally
binds the decision plan, authority Role, decision scope, and exact ordered
Capability decisions. A change to any bound identity or byte makes the
affected receipt stale. Any human-readable or Agent-facing query result is a
derived projection and creates no additional state owner.

For batch close, the gate is applicable when the frozen task contract requires
Corpus Planning or the batch manifest intersects the exact affected-path
projection defined above. An explicit Corpus Planning task requires
`applicability.state: configured`; a manifest-only
intersection MAY consume a current `not-applicable` structural receipt when the bounded batch merely
changes the inactive slot itself. Unaffected batches do not acquire the child
gate. A structural receipt never substitutes for semantic acceptance at a
boundary that asserts a Capability has reached its target.
