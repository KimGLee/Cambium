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

R12 owns targeted and specialized audit scope, evidence reuse, invalidation,
receipts, and systemic expansion. An R12 finding MAY identify an unadmitted
semantic gap for the `Gap Register`, or an accepted repair object for Coverage
and Queue, but neither the finding nor the register replaces the canonical
AuditPlan, AuditReceipt, Coverage, or Queue. Conversely, a corpus-planning pass
does not constitute an R12 audit, Module Review, Terminal Audit, or Terminal
Proof.

When `Corpus Planning` has `applicability.state: configured`, R12 MAY use only the Global Map's
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
operator who needs a broader planning gate selects R13 or explicitly changes
the planning records; the runtime does not infer scope.

## Machine Gates And Agent Query

The restricted-YAML skeletons at `Tools/schemas/global_map.template.yaml`,
`Tools/schemas/capability_matrix.template.yaml`, and
`Tools/schemas/gap_register.template.yaml` project the exact closed field sets
owned by K02/05, K02/06, and K02/07. K02/03 owns the lifecycle; this module owns
the two distinct gates that consume those records.

`Tools/check_corpus_plan.py` is the sole producer for Gate ID
`corpus-plan-structure`. A configured adopter runs it after changing a bound
artifact, promoting a Gap, closing an affected batch, or entering an applicable
module or task-completion gate. It validates paths, stable identities, explicit
relations, scale membership, bidirectional links, and promotion reconciliation.
Its pass proves only structure and reconciliation. Its JSON projection uses the
unambiguous field `structural_reconciliation_valid`; it separately exposes the
current `semantic_acceptance` status and never collapses both decisions into a
single `valid` flag.

`Tools/record_corpus_acceptance.py` is the sole producer for Gate ID
`corpus-plan-semantic-acceptance`. It consumes one closed restricted-YAML
decision plan under `.cambium/deltas/corpus-plan-acceptances/`. The plan names
every current Capability ID exactly once, in Matrix order, with `accepted` or
`rejected`, a rationale, the Profile-bound authority Role ID, and the closed
decision-scope ID. The tool validates that envelope and the deterministic rank
boundary but does not invent the authority's semantic decision. It is dry-run
by default; only explicit `--apply` appends evidence.

An applied decision appends two separate JSONL AuditReceipts: a fresh
`corpus-plan-structure` receipt and a
`corpus-plan-semantic-acceptance` receipt that names the former. Both bind the
exact Profile manifest, Corpus Planning slot, Profile Scope, all three planning
artifacts, task identity, Queue revisions, all three canonical runtime-state
fingerprints, applicability, and the path-sensitive repository snapshot. The
semantic receipt additionally binds the decision-plan path and SHA-256,
authority Role, decision scope, and exact ordered Capability decisions. A
change to any bound byte, runtime fingerprint, Queue revision, Profile,
authority binding, or repository snapshot makes the affected receipt stale.

`check_corpus_plan.py --json` is the Agent query interface. It emits a
deterministic on-demand JSON projection from current canonical inputs,
including structural/reconciliation and semantic-acceptance status. The
projection is never persisted or read back. Corpus Planning creates no
Markdown report and no additional state owner.

For batch close, the gate is applicable when either the task selected R13 or
the batch manifest intersects the exact affected-path projection defined
above. R13 requires `applicability.state: configured`; a manifest-only
intersection MAY consume a current `not-applicable` structural receipt when the bounded batch merely
changes the inactive slot itself. Unaffected batches do not acquire the child
gate. A structural receipt never substitutes for semantic acceptance at a
boundary that asserts a Capability has reached its target.
