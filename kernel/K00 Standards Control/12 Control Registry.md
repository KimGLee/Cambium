## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]].
- Next: [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]].

## Control Registry

The [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]] governs content rules — "where the rule lives"; this Control Registry governs control obligations — "where the check happens". Each risk object has one and only one canonical Gate ID. Other layers either consume a still-valid receipt for that ID or invoke the same registered producer against the required snapshot; they never infer a producer from prose or reimplement it as a parallel check.

| Gate ID | Risk object | Canonical gate (sole) | Consumption boundary |
|---|---|---|---|
| `runtime-card-synchronization` | Runtime Card completeness and source synchronization, the leaf module size budget of [[kernel/K00 Standards Control/03 Standards Governance#Leaf Module Size Budget\|Leaf Module Size Budget]], and the agreement between the `Stable Gate ID Registry` below and the producers its rows name | The [[kernel/K00 Standards Control/03 Standards Governance#Revision Write-back Checklist\|Revision Write-back Checklist]] `manual-attestation` signed at Governance close, with `Tools/stamp_cards.py . --check` as its input; that run measures every leaf against the budget and its register, and a registered growth cap it reports as exceeded is a failure of this gate, as is a registry row whose producer contradicts it | Routine tasks consume stamped Cards; profile loading cannot waive or recreate the gate |
| `profile-load` | Candidate or selected Profile identity, manifest/slot completeness, and the single-Profile dependency closure defined by [[kernel/K00 Standards Control/17 Profile Dependency Closure\|Profile Dependency Closure]] | `Tools/check_profile.py` `profile-check-summary`, which derives the typed closure and binds the Profile directory snapshot, typed contract fingerprint, and canonical root-input fingerprint | R09 candidate selection and active-task adoption validate the after image; R01 freezes only a current passing selection; batch close resolves item 6 from that same contract before invoking it; Terminal Proof root validation reruns the producer. An invalid current Profile blocks ordinary execution but never blocks a corrective R09/K13/15 adoption whose after Profile passes |
| `runtime-startup-recovery` | Existing runtime discovery, new-task collision, and interrupted-writer recovery | The [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Runtime Startup Gate\|Runtime Startup Gate]] runs `check_queue.py --resume-status` before a state write | R01, R07, and task routes consume the machine action; none may initialize over or infer around existing state |
| `large-scale-execution-admission` | Large-scale execution admission | [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate\|Large-scale Pre-execution Gate]] | R11 packages the gate with the actual work route but does not authorize content work |
| `wiki-link-integrity` | Wiki link integrity | The K12/09 Closed List consumes the `check_links` summary | Note close uses only its scoped self-check; migration retargets affected links; Terminal Audit reruns the same gate on the frozen snapshot |
| `frontmatter-vocabulary` | Legality of controlled frontmatter values that are actually present; field presence and conditional applicability remain owned by `page-contract` | The K12/09 Closed List consumes the `check_vocab` summary | Note close uses a scoped self-check; Terminal Audit reruns the same gate on the frozen snapshot |
| `priority-quota-distribution` | Whole-corpus priority share measurement under one identified effective policy ([[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota\|K00/07]]) | The `check_vocab` `priority-quota-distribution` receipt: per-class structured shares, the exceeded classes, and the effective-policy fingerprint they were measured under. It measures and itemizes; the human call on an excess stays with the per-class quota candidates, which only a bounded contract policy exception may disposition | Batch close, Maintenance/REBASE coverage reconciliation, and the Terminal Audit consume the same structured receipt; none of them re-derives a share from display text |
| `required-queue-consistency` | Queue structure, Work Spec binding, operational Amendment registration, and Queue/Coverage/Progress drift | K13/08 `check_queue.py` consistency mode | Resume, operational Amendment writers, batch close, Standards adoption, and Terminal Audit consume the same current consistency contract |
| `required-queue-admission` | Readiness, dependencies, confirmation, concurrent-write conflicts, and the K13/10 condition-2 hub classification, whose inputs are the manifest pages' own frontmatter and the selected profile's `Expression Layer Entry` rows | K13/10 `check_queue.py --require-ready <batch-id>` | Activation consumes the batch-bound receipt; no other layer recreates readiness |
| `required-queue-completion` | Build Queue exhaustion and completion readiness | K13/12 `check_queue.py --require-complete` | Entry to build `completion-candidate` consumes the frozen Queue-complete receipt |
| `maintenance-completion` | Maintenance Queue exhaustion, candidate partition, and maintenance evidence closure | K13/12 `check_queue.py --require-maintenance-complete` | Maintenance task completion consumes the frozen maintenance-complete receipt |
| `batch-review` | In-batch review authorization for one exact Delta evidence set | K12/14 current `manual-attestation` batch-review gate | `open -> merge-ready` consumes exactly one current gate that binds the Delta's page receipt IDs; page receipts alone never authorize the transition |
| `batch-close` | Complete merged-snapshot batch-close bundle | K12/09 `check_batch_close.py` batch-close aggregator | Every close reruns the full current scan. A prior verified close may carry forward only an explicitly durable, byte-exact unchanged candidate disposition; the close transition consumes the resulting current bundle |
| `page-contract` | Compiled frontmatter page contract: applicability modes, writer/projection persistence, relationship shapes and targets, and the unknown-field closure | K08/06 `Tools/check_page_contract.py` page-contract receipt, over the contract composed by `Tools/compose_page_contract.py` | Whole-corpus backlog remains advisory, while K12/09 consumes the current manifest-page slice at batch close; other pages never become that batch's ticket |
| `boundary-contract` | Page boundary blocks: K08/09 schema and self-consistency, owner resolvability, reciprocity, corpus-wide concern uniqueness, and boundary projection freshness against `Tools/render_boundary_projection.py` output | K08/09 `Tools/check_boundary_contract.py` boundary-contract receipt, over the same compiled contract's projection labels | Advisory under the K08/09 Enablement rule: candidates support migration planning and no existing gate consumes them; the `boundary` field's presence, mode, and unknown-field closure stay with `page-contract`, and concern vocabulary membership stays with `frontmatter-vocabulary`; promotion to a blocking gate is a separate governance decision under K12/10. Invalidation: a `boundary` block, a page referenced as an owner, the profile's `boundary_projection` labels or concern vocabulary, or the tool version changes; the rerun boundary is every in-scope page carrying a `boundary` block plus every page referenced as an owner |
| `structure-registry` | Structure Registry resolution: unit and support-layer declarations against the vault, Profile Scope layers, Global Map bindings, and Coverage unit references | K01/05 `Tools/check_structure.py` structure-registry receipt | R03 module close, R06 structural migration, R13 reconciliation, and Terminal Audit consume the same receipt; it proves structure declarations, never content acceptance or class-assignment semantics |
| `corpus-plan-structure` | Corpus-planning structure, role separation, explicit relations, and Gap-to-Coverage promotion drift | K02/04 `check_corpus_plan.py` structural/reconciliation receipt | R11, R13, Module Review, affected batch close, and Terminal Audit consume structure only; it is not semantic acceptance |
| `corpus-plan-semantic-acceptance` | Profile-authorized semantic capability acceptance | K02/04 `record_corpus_acceptance.py` authority-decision receipt | R13 records it; Module Review and Terminal Audit consume it separately from structure and reject stale authority/artifact/runtime bindings |
| `content-correctness` | Content correctness | K12/01 tiered review attestation | Batch review uses changed, invalidated, and sampled scope; Terminal Audit consumes current attestations and bounded sampling |
| `source-promotion` | Promotion of a source-driven new canonical page | The [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Source Intake And Promotion Review\|Source Intake And Promotion Review]] attestation recorded against the [[kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate#Canonical Promotion Gate\|Canonical Promotion Gate]] criteria | Promotion to `reviewed`, batch close, and Terminal Audit consume the same attestation; the Source Audit proves cross-batch invariants and does not re-decide one promotion |
| `expression-layer-acceptance` | R05 expression artifact acceptance, canonical binding, and migration conservation | The [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance#Acceptance Criteria\|Expression Acceptance Criteria]] attestation at the R05 Gate | A readiness promotion, batch close, and Terminal Audit consume it; a profile supplemental gate loads alongside the kernel floor and never replaces it |
| `coverage-reconciliation` | Semantic Coverage reconciliation | K12/03 Coverage Reconciliation Review attestation | Run after inventory and scope/guidance changes and before completion-candidate; the Queue checker owns only deterministic set equality |
| `standards-adoption` | Active-task Standards/Profile consistency and adoption | K12/10 semantics plus the K13/15 `adopt_standards.py` commit receipt | R09 owns the revision; R07 applies it; later boundaries consume post-adoption gates rather than rewriting runtime state |
| `standards-revalidation` | Deferred post-adoption changed-predicate claims at their declared boundary | K12/10 `check_queue.py --require-revalidation <batch-id>` | The aggregate consumes exact current receipts only for owner Gates due at that point; native owners remain mandatory at their ordinary transitions, and raw semantic-leaf receipts never substitute for either |
| `guidance-disposition` | Guidance disposition | K13/05 disposition attestation after K13/04 classification | Batch close reconciles only the increment; Terminal Audit reads the canonical ledger disposition |
| `receipt-validity` | Receipt reuse and invalidation judgment | K12/07 AuditPlan and Reuse Gate attestation | Batch start loads the register; later boundaries consume the same invalidation decision |
| `rendering` | Rendering verification | K12/02 Level 0/1 evidence plus any triggered visual attestation | Batch close consumes its enumerated member; Terminal Audit reuses it while current |
| `registered-residual-content` | Registered residual-content scan | K12/09 item 6 and the selected Profile residual verifier | Other layers consume the registered summary and candidate dispositions; no second corpus-wide scan |
| `duplicate-detection` | Duplicate detection | K12/05 duplicate review attestation | Maintenance/governance consumes it; batch close retains only its basename-level member |
| `knowledge-freshness` | Knowledge freshness | K08/05 maintenance-start freshness receipt or disposition attestation | It is not part of the ordinary batch automatic list |
| `depth-balance` | Depth balance | K12/03 Module Review attestation | Coverage counts raise candidates only and do not replace semantic review |
| `prerequisite-completeness` | Prerequisite completeness | K12/03 Module Review attestation | Link resolution remains owned by `check_links`; semantic chain continuity is not inferred from links |
| `canonical-ownership-uniqueness` | Canonical ownership uniqueness | K12/03 Module Review attestation | Closed List basename candidates and K12/02 duplicate-heading findings remain inputs, not this verdict |
| `terminal-proof` | Frozen build-completion proof | K12/16 `check_proof.py` summary receipt | The final task transition consumes this exact proof receipt; no report wording substitutes for it |

`profile-load` replaces the former manual self-path warning as the canonical
owner of Profile package integrity. It does not supersede
`registered-residual-content`: the former proves which Profile dependencies
are authorized and resolvable, while the latter executes the admitted scan
against corpus bytes and produces candidates. Runtime consumers reuse the
typed Profile contract; they do not add parallel path rules.

## Verification Run and Process Contract

The **adopter verification set** is derived from the Stable Gate ID Registry
below, never listed anywhere else: it is every row whose producer is a named
deterministic tool and whose Lifecycle is `not-batch-scoped`.
Batch-positioned rows run at their batch boundary, `manual-attestation` rows
are recorded by a person under the Gate Receipt Payload Contract, and
transaction writers (`adopt_standards`, `record_corpus_acceptance`) produce
their receipts only inside their own guarded transactions -- a verification
sweep never invokes them. `Tools/run_gates.py` executes this derivation; a
registry row it cannot classify fails the run closed, so extending the
registry forces the runner to be extended with it rather than silently
narrowing the set. A prose checklist of these commands, wherever it appears,
is a copy of this derivation and loses to it on disagreement.

Every registered deterministic producer answers through one **process
contract** (implementation: `kblib.exit_code`): exit `0` = every emitted
receipt passed; `1` = at least one failure or the run could not produce
reliable evidence; `2` = no failure, but one or more candidates or holds. `2`
is a HOLD -- it is never mapped to success and never to failure by any
consumer, machine or human; each held line names a judgment a person still
owes. A tool-specific meaning of `2` (a stale stamp, a held Queue) is still
this contract: reliable evidence, non-clean outcome, read the lines.

## Stable Gate ID Registry

This closed table is the machine registry for Gate receipt identity and
producer availability. It is not the Standards-adoption capability registry:
the separate table below owns leaf-to-owner projection and claim edges.
`Tool`, `Tool version`, `Check`, `Mode`, and `Dimension` are the canonical
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
discharged an obligation raised in another. It is a **derived selector view**,
not the authority: the values are owned by the
[[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map#Gate Receipt Dimensions\|Gate Receipt Dimensions]]
half of the dimension map together with the
[[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Item Map\|K12/08 Item Map]] it is read with, and those prevail on disagreement.

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
come from the Standards Revalidation Capability Registry below. A Lifecycle
cell holds one of three things, and the three do not mix. One or more batch lifecycle
states, tokenized the way `Dimension` is: the producer runs against a batch at
those positions. `queue-exhausted`: it runs only once the Queue holds no
non-terminal batch. `not-batch-scoped`: it takes no batch and no Queue position
constrains it, so it can run at any time. Each value is the producing tool's own
guard, not an expectation: a producer that begins accepting a further position
moves its own cell.

| Gate ID | Tool | Tool version | Check | Mode | Dimension | Lifecycle |
|---|---|---|---|---|---|---|
| `runtime-card-synchronization` | `manual-attestation` | `1.0.0` | `runtime-card-synchronization` | `*` | `guidance_and_contract` | `not-batch-scoped` |
| `profile-load` | `check_profile` | `1.9.0` | `profile-check-summary` | `*` | `guidance_and_contract` | `not-batch-scoped` |
| `runtime-startup-recovery` | `check_queue` | `1.20.1` | `required_queue` | `resume-status` | `*` | `not-batch-scoped` |
| `large-scale-execution-admission` | `manual-attestation` | `1.0.0` | `large-scale-execution-admission` | `*` | `guidance_and_contract` | `not-batch-scoped` |
| `wiki-link-integrity` | `check_links` | `1.5.0` | `link-check-summary` | `*` | `*` | `not-batch-scoped` |
| `frontmatter-vocabulary` | `check_vocab` | `1.8.0` | `vocab-check-summary` | `*` | `*` | `not-batch-scoped` |
| `priority-quota-distribution` | `check_vocab` | `1.8.0` | `priority-quota-distribution` | `*` | `*` | `not-batch-scoped` |
| `required-queue-consistency` | `check_queue` | `1.20.1` | `required_queue` | `consistency` | `*` | `not-batch-scoped` |
| `required-queue-admission` | `check_queue` | `1.20.1` | `required_queue` | `require-ready:*` | `*` | `queued` |
| `required-queue-completion` | `check_queue` | `1.20.1` | `required_queue` | `require-complete` | `*` | `queue-exhausted` |
| `maintenance-completion` | `check_queue` | `1.20.1` | `required_queue` | `require-maintenance-complete` | `*` | `queue-exhausted` |
| `batch-review` | `manual-attestation` | `1.0.0` | `batch_gate` | `*` | `none` | `open` |
| `batch-close` | `check_batch_close` | `1.10.0` | `batch_close_gate` | `*` | `*` | `merge-ready` |
| `structure-registry` | `check_structure` | `1.1.0` | `structure-registry-summary` | `*` | `*` | `not-batch-scoped` |
| `page-contract` | `check_page_contract` | `1.4.0` | `page-contract-summary` | `*` | `*` | `not-batch-scoped` |
| `boundary-contract` | `check_boundary_contract` | `1.1.0` | `boundary-contract-summary` | `*` | `*` | `not-batch-scoped` |
| `corpus-plan-structure` | `check_corpus_plan` | `1.7.0` | `corpus_plan` | `*` | `*` | `not-batch-scoped` |
| `corpus-plan-semantic-acceptance` | `record_corpus_acceptance` | `1.0.0` | `corpus_plan_semantic_acceptance` | `*` | `*` | `not-batch-scoped` |
| `content-correctness` | `manual-attestation` | `1.0.0` | `content-correctness` | `*` | `content_and_depth`, `formula_and_numeric`, `rendering`, `source_and_currentness`, `structure_and_links` | `not-batch-scoped` |
| `source-promotion` | `manual-attestation` | `1.0.0` | `source-promotion` | `*` | `coverage_and_integration`, `source_and_currentness` | `not-batch-scoped` |
| `expression-layer-acceptance` | `manual-attestation` | `1.0.0` | `expression-layer-acceptance` | `*` | `content_and_depth`, `coverage_and_integration`, `guidance_and_contract`, `source_and_currentness`, `structure_and_links` | `not-batch-scoped` |
| `coverage-reconciliation` | `manual-attestation` | `1.0.0` | `coverage-reconciliation` | `*` | `coverage_and_integration` | `not-batch-scoped` |
| `standards-adoption` | `adopt_standards` | `1.6.0` | `standards_adoption` | `*` | `*` | `not-batch-scoped` |
| `standards-revalidation` | `check_queue` | `1.20.1` | `required_queue` | `require-revalidation:*` | `*` | `queued`, `open` |
| `guidance-disposition` | `manual-attestation` | `1.0.0` | `guidance-disposition` | `*` | `guidance_and_contract` | `not-batch-scoped` |
| `receipt-validity` | `manual-attestation` | `1.0.0` | `receipt-validity` | `*` | `guidance_and_contract` | `not-batch-scoped` |
| `rendering` | `manual-attestation` | `1.0.0` | `rendering` | `*` | `rendering`, `structure_and_links` | `not-batch-scoped` |
| `registered-residual-content` | `check_residual_content` | `1.2.0` | `residual-content-summary` | `*` | `*` | `not-batch-scoped` |
| `duplicate-detection` | `manual-attestation` | `1.0.0` | `duplicate-detection` | `*` | `structure_and_links` | `not-batch-scoped` |
| `knowledge-freshness` | `manual-attestation` | `1.0.0` | `knowledge-freshness` | `*` | `source_and_currentness` | `not-batch-scoped` |
| `depth-balance` | `manual-attestation` | `1.0.0` | `depth-balance` | `*` | `content_and_depth` | `not-batch-scoped` |
| `prerequisite-completeness` | `manual-attestation` | `1.0.0` | `prerequisite-completeness` | `*` | `coverage_and_integration` | `not-batch-scoped` |
| `canonical-ownership-uniqueness` | `manual-attestation` | `1.0.0` | `canonical-ownership-uniqueness` | `*` | `structure_and_links` | `not-batch-scoped` |
| `terminal-proof` | `check_proof` | `1.17.0` | `proof-check-summary` | `*` | `*` | `queue-exhausted` |

## Standards Revalidation Capability Registry

This is the sole machine registry for turning a semantic Gate impact into a
Standards-adoption claim. The Stable Gate ID Registry above still owns receipt
identity and producer position; this table owns whether that Gate is an
adoption boundary owner, a leaf whose claim is projected to another owner, or
not a blocking Standards-revalidation capability in this protocol version.
Neither table substitutes for the other.

The table is closed. Its header is exactly `Gate ID`, `Role`, `Owner`,
`Claim edge`, `Scope protocol`, and `Binding protocol`; every Gate ID in the Stable
Gate ID Registry occurs exactly once here and no other Gate ID occurs. `Owner`
is either one Gate ID from that registry or `none`. The other cells use only
these tokens:

- `Role`: `special-owner`, `immediate-owner`, `native-owner`, `semantic-leaf`,
  `mechanism-only`, `unsupported`, or `advisory`;
- `Claim edge`: `after-image-admission`, `adoption-commit`,
  `native-transition`, `project-to-owner`, `mechanism-input-only`,
  `advisory-only`, or `none`;
- `Scope protocol`: `profile-after-image`, `runtime-after-image`,
  `native-owner-scope`, `inherit-owner-scope`, `diagnostic-scope`, or `none`;
- `Binding protocol`: `profile-fingerprints`,
  `runtime-state-fingerprints`, `native-owner-receipt`,
  `owner-member-chain`, or `not-authorizing`.

A `special-owner` is claimed only by candidate after-image admission. An
`immediate-owner` is the one raw Gate receipt an adoption may consume directly
after its state after-image exists. A `native-owner` is claimed only by the
ordinary transition that already owns that Gate. A `semantic-leaf` never
authorizes an adoption boundary directly: the planner projects it to `Owner`,
and the owner's receipt binds the leaf through its own member chain. A
`mechanism-only` Gate may carry or aggregate claims but creates none about
itself. `unsupported` rejects a new affected-Gate projection until this table is
revised; `advisory` may be reported but creates no blocking claim.

| Gate ID | Role | Owner | Claim edge | Scope protocol | Binding protocol |
|---|---|---|---|---|---|
| `runtime-card-synchronization` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `profile-load` | `special-owner` | `profile-load` | `after-image-admission` | `profile-after-image` | `profile-fingerprints` |
| `runtime-startup-recovery` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `large-scale-execution-admission` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `wiki-link-integrity` | `semantic-leaf` | `batch-close` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `frontmatter-vocabulary` | `semantic-leaf` | `batch-close` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `priority-quota-distribution` | `semantic-leaf` | `batch-close` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `required-queue-consistency` | `immediate-owner` | `required-queue-consistency` | `adoption-commit` | `runtime-after-image` | `runtime-state-fingerprints` |
| `required-queue-admission` | `native-owner` | `required-queue-admission` | `native-transition` | `native-owner-scope` | `native-owner-receipt` |
| `required-queue-completion` | `native-owner` | `required-queue-completion` | `native-transition` | `native-owner-scope` | `native-owner-receipt` |
| `maintenance-completion` | `native-owner` | `maintenance-completion` | `native-transition` | `native-owner-scope` | `native-owner-receipt` |
| `batch-review` | `native-owner` | `batch-review` | `native-transition` | `native-owner-scope` | `native-owner-receipt` |
| `batch-close` | `native-owner` | `batch-close` | `native-transition` | `native-owner-scope` | `native-owner-receipt` |
| `structure-registry` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `page-contract` | `semantic-leaf` | `batch-close` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `boundary-contract` | `advisory` | `none` | `advisory-only` | `diagnostic-scope` | `not-authorizing` |
| `corpus-plan-structure` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `corpus-plan-semantic-acceptance` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `content-correctness` | `semantic-leaf` | `batch-review` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `source-promotion` | `semantic-leaf` | `batch-review` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `expression-layer-acceptance` | `semantic-leaf` | `batch-review` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `coverage-reconciliation` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `standards-adoption` | `mechanism-only` | `none` | `mechanism-input-only` | `none` | `not-authorizing` |
| `standards-revalidation` | `mechanism-only` | `none` | `mechanism-input-only` | `none` | `not-authorizing` |
| `guidance-disposition` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `receipt-validity` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `rendering` | `semantic-leaf` | `batch-review` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `registered-residual-content` | `semantic-leaf` | `batch-close` | `project-to-owner` | `inherit-owner-scope` | `owner-member-chain` |
| `duplicate-detection` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `knowledge-freshness` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `depth-balance` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `prerequisite-completeness` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `canonical-ownership-uniqueness` | `unsupported` | `none` | `none` | `none` | `not-authorizing` |
| `terminal-proof` | `native-owner` | `terminal-proof` | `native-transition` | `native-owner-scope` | `native-owner-receipt` |

This registry governs new plan admission and current authorization only.
Historical adoption plans, transition receipts, revalidation aggregates, and
sealed evidence are replayed under their recorded producer era. A later
capability role, owner, or binding protocol neither repairs nor invalidates a
decision already consumed in history.
