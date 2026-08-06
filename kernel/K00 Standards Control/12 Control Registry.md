## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]].
- Next: [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]].

## Control Registry

The [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]] governs content rules — "where the rule lives"; this Control Registry governs control obligations — "where the check happens". Each risk object has one and only one canonical Gate ID. Other layers either consume a still-valid receipt for that ID or invoke the same registered producer against the required snapshot; they never infer a producer from prose or reimplement it as a parallel check.

| Gate ID | Risk object | Canonical gate (sole) | Consumption boundary |
|---|---|---|---|
| `runtime-card-synchronization` | Runtime Card completeness and source synchronization, and the leaf module size budget of [[kernel/K00 Standards Control/03 Standards Governance#Leaf Module Size Budget\|Leaf Module Size Budget]] | The [[kernel/K00 Standards Control/03 Standards Governance#Revision Write-back Checklist\|Revision Write-back Checklist]] `manual-attestation` signed at Governance close, with `Tools/stamp_cards.py . --check` as its input; that run measures every leaf against the budget and its register, and a registered growth cap it reports as exceeded is a failure of this gate | Routine tasks consume stamped Cards; profile loading cannot waive or recreate the gate |
| `runtime-startup-recovery` | Existing runtime discovery, new-task collision, and interrupted-writer recovery | The [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Runtime Startup Gate\|Runtime Startup Gate]] runs `check_queue.py --resume-status` before a state write | R01, R07, and task routes consume the machine action; none may initialize over or infer around existing state |
| `large-scale-execution-admission` | Large-scale execution admission | [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate\|Large-scale Pre-execution Gate]] | R11 packages the gate with the actual work route but does not authorize content work |
| `wiki-link-integrity` | Wiki link integrity | The K12/09 Closed List consumes the `check_links` summary | Note close uses only its scoped self-check; migration retargets affected links; Terminal Audit reruns the same gate on the frozen snapshot |
| `frontmatter-vocabulary` | Frontmatter vocabulary | The K12/09 Closed List consumes the `check_vocab` summary | Note close uses a scoped self-check; Terminal Audit reruns the same gate on the frozen snapshot |
| `required-queue-consistency` | Queue structure, Work Spec binding, operational Amendment registration, and Queue/Coverage/Progress drift | K13/08 `check_queue.py` consistency mode | Resume, operational Amendment writers, batch close, Standards adoption, and Terminal Audit consume the same current consistency contract |
| `required-queue-admission` | Readiness, dependencies, confirmation, concurrent-write conflicts, and the K13/10 condition-2 hub classification, whose inputs are the manifest pages' own frontmatter and the selected profile's `Expression Layer Entry` rows | K13/10 `check_queue.py --require-ready <batch-id>` | Activation consumes the batch-bound receipt; no other layer recreates readiness |
| `required-queue-completion` | Build Queue exhaustion and completion readiness | K13/12 `check_queue.py --require-complete` | Entry to build `completion-candidate` consumes the frozen Queue-complete receipt |
| `maintenance-completion` | Maintenance Queue exhaustion, candidate partition, and maintenance evidence closure | K13/12 `check_queue.py --require-maintenance-complete` | Maintenance task completion consumes the frozen maintenance-complete receipt |
| `batch-review` | In-batch review authorization for one exact Delta evidence set | K12/14 current `manual-attestation` batch-review gate | `open -> merge-ready` consumes exactly one current gate that binds the Delta's page receipt IDs; page receipts alone never authorize the transition |
| `batch-close` | Complete merged-snapshot batch-close bundle | K12/09 `check_batch_close.py` batch-close aggregator | The close transition consumes the current bundle; later review reuses it only while its snapshot binding remains current |
| `corpus-plan-structure` | Corpus-planning structure, role separation, explicit relations, and Gap-to-Coverage promotion drift | K02/04 `check_corpus_plan.py` structural/reconciliation receipt | R11, R13, Module Review, affected batch close, and Terminal Audit consume structure only; it is not semantic acceptance |
| `corpus-plan-semantic-acceptance` | Profile-authorized semantic capability acceptance | K02/04 `record_corpus_acceptance.py` authority-decision receipt | R13 records it; Module Review and Terminal Audit consume it separately from structure and reject stale authority/artifact/runtime bindings |
| `content-correctness` | Content correctness | K12/01 tiered review attestation | Batch review uses changed, invalidated, and sampled scope; Terminal Audit consumes current attestations and bounded sampling |
| `source-promotion` | Promotion of a source-driven new canonical page | The [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Source Intake And Promotion Review\|Source Intake And Promotion Review]] attestation recorded against the [[kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate#Canonical Promotion Gate\|Canonical Promotion Gate]] criteria | Promotion to `reviewed`, batch close, and Terminal Audit consume the same attestation; the Source Audit proves cross-batch invariants and does not re-decide one promotion |
| `expression-layer-acceptance` | R05 expression artifact acceptance, canonical binding, and migration conservation | The [[kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance#Acceptance Criteria\|Expression Acceptance Criteria]] attestation at the R05 Gate | A readiness promotion, batch close, and Terminal Audit consume it; a profile supplemental gate loads alongside the kernel floor and never replaces it |
| `coverage-reconciliation` | Semantic Coverage reconciliation | K12/03 Coverage Reconciliation Review attestation | Run after inventory and scope/guidance changes and before completion-candidate; the Queue checker owns only deterministic set equality |
| `standards-adoption` | Active-task Standards/Profile consistency and adoption | K12/10 semantics plus the K13/15 `adopt_standards.py` commit receipt | R09 owns the revision; R07 applies it; later boundaries consume post-adoption gates rather than rewriting runtime state |
| `standards-revalidation` | Deferred post-adoption changed-predicate gates at their declared boundary | K12/10 `check_queue.py --require-revalidation <batch-id>` | The named boundary consumes exact Gate-ID receipts and records one current revalidation receipt; unrelated work does not run every gate |
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

## Stable Gate ID Registry

This closed table is the machine registry for Standards revalidation. `Tool`,
`Tool version`, `Check`, and `Mode` are the canonical receipt selector. Tool,
version, and check are always exact; only Mode may use `*` when no narrower
mode exists. `manual-attestation` is an explicit producer class with current
protocol version `1.0.0`, not a request for an Agent to guess a tool or version
from the descriptive table above. What a receipt of either kind MUST carry to be
consumed for its Gate ID, and who may record a `manual-attestation` one, are
owned by [[kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract#Gate Receipt Payload|Gate Receipt Payload Contract]].

| Gate ID | Tool | Tool version | Check | Mode |
|---|---|---|---|---|
| `runtime-card-synchronization` | `manual-attestation` | `1.0.0` | `runtime-card-synchronization` | `*` |
| `runtime-startup-recovery` | `check_queue` | `1.5.0` | `required_queue` | `resume-status` |
| `large-scale-execution-admission` | `manual-attestation` | `1.0.0` | `large-scale-execution-admission` | `*` |
| `wiki-link-integrity` | `check_links` | `1.5.0` | `link-check-summary` | `*` |
| `frontmatter-vocabulary` | `check_vocab` | `1.4.0` | `vocab-check-summary` | `*` |
| `required-queue-consistency` | `check_queue` | `1.5.0` | `required_queue` | `consistency` |
| `required-queue-admission` | `check_queue` | `1.5.0` | `required_queue` | `require-ready:*` |
| `required-queue-completion` | `check_queue` | `1.5.0` | `required_queue` | `require-complete` |
| `maintenance-completion` | `check_queue` | `1.5.0` | `required_queue` | `require-maintenance-complete` |
| `batch-review` | `manual-attestation` | `1.0.0` | `batch_gate` | `*` |
| `batch-close` | `check_batch_close` | `1.2.0` | `batch_close_gate` | `*` |
| `corpus-plan-structure` | `check_corpus_plan` | `1.5.0` | `corpus_plan` | `*` |
| `corpus-plan-semantic-acceptance` | `record_corpus_acceptance` | `1.0.0` | `corpus_plan_semantic_acceptance` | `*` |
| `content-correctness` | `manual-attestation` | `1.0.0` | `content-correctness` | `*` |
| `source-promotion` | `manual-attestation` | `1.0.0` | `source-promotion` | `*` |
| `expression-layer-acceptance` | `manual-attestation` | `1.0.0` | `expression-layer-acceptance` | `*` |
| `coverage-reconciliation` | `manual-attestation` | `1.0.0` | `coverage-reconciliation` | `*` |
| `standards-adoption` | `adopt_standards` | `1.1.0` | `standards_adoption` | `*` |
| `standards-revalidation` | `check_queue` | `1.5.0` | `required_queue` | `require-revalidation:*` |
| `guidance-disposition` | `manual-attestation` | `1.0.0` | `guidance-disposition` | `*` |
| `receipt-validity` | `manual-attestation` | `1.0.0` | `receipt-validity` | `*` |
| `rendering` | `manual-attestation` | `1.0.0` | `rendering` | `*` |
| `registered-residual-content` | `check_residual_content` | `1.1.0` | `residual-content-summary` | `*` |
| `duplicate-detection` | `manual-attestation` | `1.0.0` | `duplicate-detection` | `*` |
| `knowledge-freshness` | `manual-attestation` | `1.0.0` | `knowledge-freshness` | `*` |
| `depth-balance` | `manual-attestation` | `1.0.0` | `depth-balance` | `*` |
| `prerequisite-completeness` | `manual-attestation` | `1.0.0` | `prerequisite-completeness` | `*` |
| `canonical-ownership-uniqueness` | `manual-attestation` | `1.0.0` | `canonical-ownership-uniqueness` | `*` |
| `terminal-proof` | `check_proof` | `1.14.0` | `proof-check-summary` | `*` |
