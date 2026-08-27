## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]].
- Next: [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]].

## Control Registry

The [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]] governs content rules — "where the rule lives"; this Control Registry governs control obligations — "where the check happens". Each risk object has one and only one canonical Gate ID. Other layers either consume a still-valid receipt for that ID or invoke the same registered producer against the required snapshot; they never infer a producer from prose or reimplement it as a parallel check.

| Gate ID | Risk object | Canonical gate (sole) | Consumption boundary |
|---|---|---|---|
| `profile-load` | Candidate or selected Profile identity, manifest/slot completeness, and the single-Profile dependency closure defined by [[kernel/K00 Standards Control/17 Profile Dependency Closure\|Profile Dependency Closure]] | The registered `profile-load` producer derives the typed closure and binds the Profile snapshot, typed contract fingerprint, and canonical root-input fingerprint | Candidate selection and active-task adoption validate the after image; ordinary execution requires a current passing selection. An invalid current Profile does not block a corrective adoption whose after Profile passes |
| `runtime-startup-recovery` | Existing runtime discovery, new-task collision, and interrupted-writer recovery | The registered producer for the [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Runtime Startup Gate\|Runtime Startup Gate]] emits one machine-readable next action before a state write | Runtime consumers follow that action; none may initialize over or infer around existing state |
| `large-scale-execution-admission` | Large-scale execution admission | [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate\|Large-scale Pre-execution Gate]] | R11 packages the gate with the actual work route but does not authorize content work |
| `wiki-link-integrity` | Wiki link integrity | The K12/09 Closed List consumes the registered link-check summary | Note close uses only its scoped self-check; migration retargets affected links; Terminal Audit reruns the same gate on the frozen snapshot |
| `frontmatter-vocabulary` | Legality of controlled frontmatter values that are actually present; field presence and conditional applicability remain owned by `page-contract` | The K12/09 Closed List consumes the registered vocabulary-check summary | Note close uses a scoped self-check; Terminal Audit reruns the same gate on the frozen snapshot |
| `priority-quota-distribution` | Whole-corpus priority share measurement under one identified effective policy ([[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota\|K00/07]]) | The registered quota-distribution receipt: per-class structured shares, exceeded classes, and the effective-policy fingerprint. It measures and itemizes; only a bounded Task Contract policy exception may disposition an excess | Batch close, Maintenance/REBASE coverage reconciliation, and the Terminal Audit consume the same structured receipt; none of them re-derives a share from display text |
| `required-queue-consistency` | Queue structure, Work Spec binding, operational Amendment registration, and Queue/Coverage/Progress drift | The registered consistency producer for K13/08 | Resume, operational Amendment writers, batch close, Standards adoption, and Terminal Audit consume the same current consistency contract |
| `required-queue-admission` | Readiness, dependencies, confirmation, concurrent-write conflicts, and the K13/10 hub classification | The registered admission producer for K13/10 | Activation consumes the batch-bound receipt; no other layer recreates readiness |
| `required-queue-completion` | Build Queue exhaustion and completion readiness | The registered build-completion producer for K13/12 | Entry to build `completion-candidate` consumes the frozen Queue-complete receipt |
| `maintenance-completion` | Maintenance Queue exhaustion, candidate partition, and maintenance evidence closure | The registered maintenance-completion producer for K13/12 | Maintenance task completion consumes the frozen maintenance-complete receipt |
| `batch-review` | In-batch review authorization for one exact Delta evidence set | K12/14 current `manual-attestation` batch-review gate | `open -> merge-ready` consumes exactly one current gate that binds the Delta's page receipt IDs and, when the selected Profile registers Batch Review Requirements, the exact frozen judgment set; page or judgment receipts alone never authorize the transition |
| `batch-close` | Complete merged-snapshot batch-close bundle | The registered batch-close producer for K12/09 | Every close reruns the full current scan. A prior verified close may carry forward only an explicitly durable, byte-exact unchanged candidate disposition; the close transition consumes the resulting current bundle |
| `page-contract` | Compiled frontmatter page contract: applicability modes, writer/projection persistence, relationship shapes and targets, and the unknown-field closure | The registered `page-contract` producer over the uniquely composed page contract | Whole-corpus backlog remains advisory, while K12/09 consumes the current manifest-page slice at batch close; other pages never become that batch's ticket |
| `boundary-contract` | Page boundary blocks: K08/09 schema and self-consistency, owner resolvability, reciprocity, corpus-wide concern uniqueness, and boundary projection freshness | The registered `boundary-contract` producer over the same composed contract | Advisory under the K08/09 Enablement rule: candidates support migration planning and no existing gate consumes them; field applicability stays with `page-contract`, and concern vocabulary membership stays with `frontmatter-vocabulary`. Promotion to a blocking gate is a separate governance decision. Relevant contract, owner, vocabulary, or producer-protocol changes invalidate the affected boundary evidence |
| `structure-registry` | Structure Registry resolution: unit and support-layer declarations against the vault, Profile Scope layers, Global Map bindings, and Coverage unit references | The registered `structure-registry` producer for K01/05 | Module close, structural migration, planning reconciliation, and Terminal Audit consume the same receipt; during Standards adoption its changed predicate projects to the `profile-load` after-image owner, whose admitted snapshot includes the registry bytes and stable identity checks; neither Gate proves content acceptance or class-assignment semantics |
| `corpus-plan-structure` | Corpus-planning structure, role separation, explicit relations, and Gap-to-Coverage promotion drift | K02/04 registered structural/reconciliation receipt | R11, R13, Module Review, affected batch close, and Terminal Audit consume structure only; it is not semantic acceptance |
| `corpus-plan-semantic-acceptance` | Profile-authorized semantic capability acceptance | K02/04 registered authority-decision receipt | R13 records it; Module Review and Terminal Audit consume it separately from structure and reject stale authority/artifact/runtime bindings |
| `content-correctness` | Content correctness | K12/01 tiered review attestation | Batch review uses changed, invalidated, and sampled scope; Terminal Audit consumes current attestations and bounded sampling |
| `source-promotion` | Promotion of a source-driven new canonical page | The [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Source Intake And Promotion Review\|Source Intake And Promotion Review]] attestation recorded against the [[kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate#Canonical Promotion Gate\|Canonical Promotion Gate]] criteria | Promotion to `reviewed`, batch close, and Terminal Audit consume the same attestation; the Source Audit proves cross-batch invariants and does not re-decide one promotion |
| `expression-layer-acceptance` | R05 expression artifact acceptance, canonical binding, and migration conservation | The [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance#Acceptance Criteria\|Expression Acceptance Criteria]] attestation at the R05 Gate | A readiness promotion, batch close, and Terminal Audit consume it; a profile supplemental gate loads alongside the kernel floor and never replaces it |
| `coverage-reconciliation` | Semantic Coverage reconciliation | K12/03 Coverage Reconciliation Review attestation | Run after inventory and scope/guidance changes and before completion-candidate; the Queue checker owns only deterministic set equality |
| `standards-adoption` | Active-task Standards/Profile consistency and adoption | K12/10 semantics plus the registered K13/15 transaction receipt | Governance owns the revision; execution applies it; later boundaries consume post-adoption gates rather than rewriting runtime state |
| `standards-revalidation` | Deferred post-adoption changed-predicate claims at their declared boundary | The registered revalidation producer for K12/10 | The aggregate consumes exact current receipts only for owner Gates due at that point; native owners remain mandatory at their ordinary transitions, and raw semantic-leaf receipts never substitute for either |
| `guidance-disposition` | Guidance disposition | K13/05 disposition attestation after K13/04 classification | Batch close reconciles only the increment; Terminal Audit reads the canonical ledger disposition |
| `receipt-validity` | Receipt reuse and invalidation judgment | K12/07 AuditPlan and Reuse Gate attestation | Batch start loads the register; later boundaries consume the same invalidation decision |
| `rendering` | Rendering verification | K12/02 Level 0/1 evidence plus any triggered visual attestation | Batch close consumes its enumerated member; Terminal Audit reuses it while current |
| `registered-residual-content` | Registered residual-content scan | K12/09 item 6 and the selected Profile residual verifier | Other layers consume the registered summary and candidate dispositions; no second corpus-wide scan |
| `duplicate-detection` | Duplicate detection | K12/05 duplicate review attestation | Maintenance/governance consumes it; batch close retains only its basename-level member |
| `knowledge-freshness` | Knowledge freshness | K08/05 maintenance-start freshness receipt or disposition attestation | It is not part of the ordinary batch automatic list |
| `depth-balance` | Depth balance | K12/03 Module Review attestation | Coverage counts raise candidates only and do not replace semantic review |
| `prerequisite-completeness` | Prerequisite completeness | K12/03 Module Review attestation | Link resolution remains owned by `wiki-link-integrity`; semantic chain continuity is not inferred from links |
| `canonical-ownership-uniqueness` | Canonical ownership uniqueness | K12/03 Module Review attestation | Closed List basename candidates and K12/02 duplicate-heading findings remain inputs, not this verdict |
| `terminal-proof` | Frozen build-completion proof | The registered Terminal Proof producer for K12/16 | The final task transition consumes this exact proof receipt; no report wording substitutes for it |

`profile-load` replaces the former manual self-path warning as the canonical
owner of Profile package integrity. It does not supersede
`registered-residual-content`: the former proves which Profile dependencies
are authorized and resolvable, while the latter executes the admitted scan
against corpus bytes and produces candidates. Runtime consumers reuse the
typed Profile contract; they do not add parallel path rules.

## Verification Set Contract

The adopter verification set is derived from the Stable Gate ID Registry in
[`control-registry.yaml`](control-registry.yaml) and is never maintained as a
prose command list. Batch-positioned
producers run at their registered boundary, manual attestations follow the Gate
Receipt Payload Contract, and transaction producers emit evidence only inside
their own controlled transaction.

Verification aggregation preserves three observable outcomes: pass, fail, and
hold. A hold is reliable non-clean evidence that still requires a declared
judgment; it is neither silently promoted to pass nor collapsed into failure.
The command runner, process exit mapping, and diagnostic formatting belong to
the Tool implementation.

## Stable Gate ID Registry

[`control-registry.yaml`](control-registry.yaml) is the sole machine registry
for Gate receipt identity and producer availability. Values in `tool`,
`tool_version`, `check`, and `mode`
are stable producer-capability and protocol identifiers, not Python module,
file, or invocation names. The revalidation fields in the same registry own
leaf-to-owner projection and claim edges; those fields do not substitute for
the receipt selector. `tool`, `tool_version`, `check`, `mode`, and `dimensions`
form the canonical
receipt selector. Tool,
version, and check are always exact; only Mode and Dimension may use `*` when no narrower
mode exists. `manual-attestation` is an explicit producer class with current
protocol version `1.0.0`, not a request for an Agent to guess a tool or version
from the descriptive table above. What a receipt of either kind MUST carry to be
consumed for its Gate ID, and who may record a `manual-attestation` one, are
owned by [[kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract#Gate Receipt Payload|Gate Receipt Payload Contract]].

`Dimension` closes the last gap in that selector: a Gate ID whose canonical gate
files verdicts under several receipt dimensions was, without it, satisfied by a
receipt for any one of them, so evidence re-established in one dimension
discharged an obligation raised in another. Named dimension identities must
resolve in K12's `audit-dimension-base.yaml`; the
[[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map#Gate Receipt Dimension Boundary\|Gate Receipt Dimension Boundary]]
and the
[[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Item Map\|K12/08 Item Map]]
explain their filing semantics. The exact current Gate selector is owned only
by the corresponding row in `control-registry.yaml`; prose does not override
that row.

A cell holds one of three things. One or more base receipt dimensions: the
receipt MUST carry `dimension` and it MUST be one of them, and a consumer that
knows which dimension its obligation was raised in narrows to that one value.
`none`: the Gate binds member receipts that already carry the verdicts, so its
own receipt carries no `dimension` at all. `*`: the row's producer is a named
tool whose identity already fixes what its receipt means and which writes no
`dimension` field, so nothing is narrowed here; it is not a licence to file such
a receipt under any dimension.

`Lifecycle` is not part of that selector. It records the position at which the
Gate's producer can run. It is producer-availability evidence for a
`native-owner` claim edge; it does not turn a semantic leaf into a boundary
owner or independently decide what an adoption may consume. Those decisions
come from the revalidation fields in the machine registry. A Lifecycle value
holds one of three things, and the three do not mix. One or more batch lifecycle
states, tokenized the way `Dimension` is: the producer runs against a batch at
those positions. `queue-exhausted`: it runs only once the Queue holds no
non-terminal batch. `not-batch-scoped`: it takes no batch and no Queue position
constrains it, so it can run at any time. Each value is the producing tool's own
guard, not an expectation: a producer that begins accepting a further position
changes its single machine row. The YAML validator rejects duplicate Gate IDs,
unknown dimensions or positions, ambiguous selectors, and producer identities
that disagree with the implementation actually emitting receipts.

## Standards Revalidation Capability Registry

The `revalidation_*` fields and role contracts in
[`control-registry.yaml`](control-registry.yaml) are the sole machine registry
for turning a semantic Gate impact into a Standards-adoption claim. The
receipt-selector fields still own receipt identity and producer position;
the revalidation fields own whether that Gate is an
adoption boundary owner, a leaf whose claim is projected to another owner, or
not a blocking Standards-revalidation capability in this protocol version.
Neither field group substitutes for the other. Every Gate carries exactly one
revalidation projection, and every owner reference must resolve inside the
same registry.

A `special-owner` is claimed only by candidate after-image admission. An
`immediate-owner` is the one raw Gate receipt an adoption may consume directly
after its state after-image exists. A `native-owner` is claimed only by the
ordinary transition that already owns that Gate. A `semantic-leaf` never
authorizes an adoption boundary directly: the planner projects it to `Owner`,
which must be a distinct `special-owner`, `immediate-owner`, or `native-owner`.
The owner's receipt binds the leaf through the registered member chain; for a
Profile-owned leaf projected to `profile-load`, that chain is the exact slot
bytes inside the typed Profile snapshot and root-input fingerprints. A
`mechanism-only` Gate may carry or aggregate claims but creates none about
itself. `unsupported` rejects a new affected-Gate projection until the machine
registry is revised; `advisory` may be reported but creates no blocking claim.

This registry governs new plan admission and current authorization only.
Historical adoption plans, transition receipts, revalidation aggregates, and
sealed evidence retain their recorded identities and semantics. A later
capability role, owner, or binding protocol neither repairs nor invalidates a
decision already consumed in history.
