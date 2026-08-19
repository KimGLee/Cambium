# Tools: Machine-readable State Layer and Deterministic Checks

This directory contains the machine-readable schemas and deterministic tools
shipped with Cambium. All scripts use only the Python 3 standard library, and
all supported YAML parsing goes through the restricted-subset parser in
`kblib.py`.

## Ownership boundary

| Layer | Owns | Does not own |
|---|---|---|
| `kernel/` | Cross-domain rules, gates, routes, and vocabulary semantics | Instance choices or executable implementations |
| Selected profile | Domain choices; registered scan identity, scope, matcher configuration, candidate predicate, and judgment binding | Kernel defaults or Cambium-shipped executable code |
| `Tools/` | Deterministic execution, safe parsing/traversal, generated-artifact compilation, receipts, and exit semantics | Canonical policy prose or final content judgment |
| Generated artifacts | A reproducible projection of their declared inputs | Independent rules, profile selection, or authority |

No tool modifies canonical standards prose. The only standards-tree writer is
`stamp_cards.py`, which updates compiled Markdown under `kernel/Cards`;
`--check` is strictly read-only. Persistent executable checks shipped by
Cambium belong here even when a selected profile supplies their parameters.

## Evidence trust boundary

The local tool baseline checks receipt shape, declared producer/tool-version
labels, SHA-256 bindings, state transitions, cross-receipt chains, and evidence
currency. A matching label identifies the contract a record claims to follow;
it does not authenticate the executable that emitted it. Likewise, actor and
reviewer fields are recorded assertions, not authenticated operating-system or
human identities. SHA-256 binds evidence to bytes inside this trust domain but
is not a signature. Without externally signed receipts, a protected runner, or
equivalent attestation, an actor with write access to the repository, tools,
and evidence can construct an internally consistent history. The tools fail
closed on malformed, incomplete, stale, or internally inconsistent evidence;
they do not claim adversarial provenance verification.

The core distribution tools are `check_links`, `check_vocab`, `check_moc`,
`check_proof`, `check_corpus_plan`, `record_corpus_acceptance`, `init_state`,
`check_queue`, `check_batch_close`, `apply_task_plan`, `apply_contract_amendment`, `compile_queue`, `update_task`,
`update_queue`, `register_amendment`, `apply_amendment`, `adopt_standards`,
`seal_receipts`,
`apply_profile_adoption`,
`render_queue`, `apply_delta`, `compose_vocab`, `check_profile`,
`check_structure`, `compose_page_contract`, `check_page_contract`,
`check_boundary_contract`, `render_boundary_projection`,
`render_structure_projection`, `project_page_state`,
`check_residual_content`, `scaffold_profile`, `profile_onboarding_status`, `profile_contract`, `profile_admission`, `stamp_cards`, `run_gates`,
`compile_cli_contract`, `render_interface_projection`, `render_host_configs`,
`amendment_policy`, `batch_settlement`, `candidate_lifecycle`,
`coverage_delta`, `maintenance_candidates`, and `kblib`.
`check_freshness` and `duplicate_check` are maintenance-run tools.
This list and the inventory table below name every `Tools/*.py` file shipped
with Cambium; a script absent from both is not part of the distribution.

## Tool inventory

| Script | Purpose | Typical invocation |
|---|---|---|
| `run_gates.py` | Adopter verification sweep 1.0.0 (K00/12 Verification Run and Process Contract). The set it runs is DERIVED, never listed: every Stable Gate ID Registry row whose producer is a named deterministic tool and whose Lifecycle is `not-batch-scoped`. Preflights the registry/producer agreement guard and compiled-artifact freshness (`compose_vocab --check`, `compose_page_contract --check`); reports `manual-attestation` rows as human-recorded (producing the `stamp_cards --check` input for `runtime-card-synchronization`) and transaction writers (`adopt_standards`, `record_corpus_acceptance`) as never-swept; a registry row it cannot classify fails the run closed so the registry cannot outgrow its executor silently. One `check_vocab` run serves both of that producer's gates. In an adopter runtime (selected profile outside `profiles/examples/`) it also reports a candidate per `distribution-boundary.yaml` tree present in the working tree (owner K00/03 Distribution Boundary). Exit codes follow the shared process contract: `1` = at least one failure, `2` = no failure but holds each of which a person must read, `0` = clean; `--list` prints the derivation without running; `--profile` overrides the live runtime's selected manifest; `--exclude` passes through to scanners that accept it | `python3 Tools/run_gates.py . --exclude _to_delete` |
| `check_links.py` | Wiki link missing / ambiguous / heading verification (K09/03, K09/05); `--scope` accepts a directory or a single page; the effective scan set is checked after exclusions, and zero files fail for both scoped and whole-root runs; an exact full-path link into an excluded area resolves as `excluded_target` before any active basename fallback | `python3 Tools/check_links.py . --receipts Tools/receipts/links.jsonl` |
| `check_vocab.py` | Frontmatter controlled-vocabulary check 1.8.0 (K08 module; vocabulary from the composed `vocab.yaml`, which exists only once a profile has been selected and composed -- without it the check reports that and exits 1). It validates only values that are present: an unknown controlled value or unparseable frontmatter fails, while a page without frontmatter and a missing/empty controlled field are diagnostic counts because applicability and required presence belong to the compiled page contract. `--scope` accepts a directory or a single page; the post-exclusion effective scan set must be nonempty; `--quota-p0` / `--quota-p1` cap P0/P1 shares, defaults 15/35 (kernel defaults; a profile or task contract may override), compared with exact rational arithmetic; each over-quota class raises one candidate carrying its structured `priority_share` (pages/total/share/quota), and every run emits the registered `priority-quota-distribution` Gate receipt (K00/12) with all per-class shares, the exceeded classes, and the `--policy-fingerprint` it was handed; the canonical artifact must be byte-current for the same admitted Profile and carries its Profile/artifact fingerprints in receipts; compiled kernel Cards are outside the knowledge-page schema | `python3 Tools/check_vocab.py . --scope kernel --exclude kernel/Cards --quota-p0 15 --quota-p1 35 --receipts Tools/receipts/vocab.jsonl` |
| `check_moc.py` | Standard Module MOC Module Index vs. actual H2 headings consistency candidates (K12/05; **candidates only**); recursively scans every non-hidden directory unless the caller explicitly supplies `--exclude`, and is fence-aware (fenced code blocks ignored); maintenance runs and governance | `python3 Tools/check_moc.py .` |
| `check_proof.py` | Terminal Proof Gate producer 1.17.0 (K12/16): field completeness; canonical, non-symlinked Coverage/Progress/Queue state; exact candidate-state fingerprints, or after completion the same pre-complete Progress fingerprint bound through the latest task-transition receipt and its current after-image; task/scope/contract/Standards/profile agreement plus exact equality of all five selection lists with the frozen Progress Task Contract; no pending Guidance/Amendment; current Queue revisions, zero remaining work, live completion gate and Coverage gaps; selected profile loadability; required terminal R01/R12/R08 selection and exact R01-R13 route/Card/Read-Set registry agreement; passed reconciliation/QA/review results; and complete receipt evidence for the seven base dimensions plus exactly the selected Profile registry extensions targeting `receipt`. In root mode one authorized Profile view and one runtime result supply admission, active K00 identity, extension-dimension enumeration, complete Profile snapshot, typed-contract fingerprint, and the fingerprint of the three root-owned profile-load inputs; Queue and Corpus consumers reuse those objects without rerunning the producer. The final boundary rebinds the Profile, K00, three state files, canonical profile-load inputs, and whole repository. The pass receipt carries all three Profile fingerprints plus `repository_snapshot_sha256`, so a later K, Card, Read Set, Profile, or Tool revision cannot be consumed as the old Proof. Unregistered dimension keys and receipt lists under `review`-only dimensions fail, and every cited receipt must remain in the Standards-adoption-filtered current catalog—historical evidence is retained but cannot authorize a new proof. It rejects a Progress contract whose `completion_semantics` is `maintenance`; without `--root`, it is structural lint only | `python3 Tools/check_proof.py .cambium/receipts/terminal-proof.yaml --root . --progress-ledger .cambium/state/progress_ledger.yaml --ledger .cambium/state/coverage_ledger.yaml --receipts .cambium/receipts/terminal.jsonl` |
| `check_corpus_plan.py` | Corpus Planning structural/reconciliation gate and Agent query interface 1.7.0: resolves the explicit or Progress-selected Profile; validates the three closed restricted-YAML planning contracts, explicit IDs/relations, Profile Scope, scale/evidence links, and Gap promotion handoff. Structural receipts carry Gate ID `corpus-plan-structure`. `--json` exposes `structural_reconciliation_valid` and the separately resolved `semantic_acceptance` status; it emits no ambiguous aggregate `valid` field and persists no report. The tool never infers relations or makes the semantic decision | `python3 Tools/check_corpus_plan.py . --json` |
| `record_corpus_acceptance.py` | Sole `corpus-plan-semantic-acceptance` producer. Consumes one closed restricted-YAML plan directly under `.cambium/deltas/corpus-plan-acceptances/`; requires every current Capability ID exactly once in Matrix order, the Profile-bound authority Role and decision scope, and explicit accepted/rejected decisions. Dry-run by default. `--apply` appends a fresh structural receipt and a distinct semantic JSONL receipt bound to the plan, Profile/slot/Scope, three planning artifacts, canonical runtime state, repository snapshot, authority, and exact decisions. It creates no Markdown projection | `python3 Tools/record_corpus_acceptance.py . --plan .cambium/deltas/corpus-plan-acceptances/CPA-001.yaml --actor-role <role-id> --apply` |
| `init_state.py` | Create an adopter's empty `.cambium/` namespace (producer 1.3.0), including `work_specs/`, and the three canonical state files. Dry-run by default; `--apply` stages and reparses a complete tree before one atomic no-replace rename, requires the caller to choose `--completion-semantics build` or `maintenance`, records the task objective plus repeatable explicit exclusions alongside Standards/profile identity, requires the candidate selected Profile to pass the same `profile-load` closure used at public Queue admission, and never invents Required work. The Profile snapshot, typed-contract fingerprint, and resolved Profile override are compared at admission and immediately before and after publication; a staged shared-writer lock publishes with the namespace, post-publication drift atomically withdraws it, and an unprovable rollback retains the exact recovery lock. Any pre-existing `.cambium/`—including an empty directory that wins a publication race—is preserved; the diagnostic directs the operator to `check_queue.py --resume-status` rather than overwriting it | `python3 Tools/init_state.py . --task-id TASK --objective "Concrete outcome" --exclude "Out-of-scope boundary" --completion-semantics build --scope-version s1 --standards-version VERSION --profile-manifest profiles/my-profile/profile.md --apply` |
| `apply_task_plan.py` | Sole writer of the initial planning transaction 1.1.0 (K13/18). `init_state.py` leaves the Task Contract's five selection fields, Coverage, and the Queue empty because it infers nothing; this tool fills the first two from one operator-confirmed restricted-YAML plan under `.cambium/deltas/task-plans/`, so those first values are never hand-edited. Dry-run by default. The plan names routes, not paths: `selected_card_paths`, `selected_read_sets`, and `loaded_module_paths` are resolved from `selected_route_ids` through the same canonical Card/Read Set indexes `check_proof` binds at Terminal, then transitively closed over loading boundaries, because selecting R01 alone reaches every other route and well over a hundred modules and a hand-typed list would be a declaration nobody checked; a path the plan does list is kept and closed over, which is how a profile supplemental Read Set is selected. The derived declaration must then satisfy `check_queue`'s own closure findings, which K00/15 makes an admission judgment rather than a live error precisely because a plan is still writable. It fails closed on an unknown or missing plan field, a `before` SHA-256 that does not match current Coverage/Queue/Progress bytes, a disagreeing task ID, a `task_state` other than `planned`, an already populated Coverage or Queue, an unfilled `TODO(plan)` sentinel, a current runtime that does not validate, a route absent from the registry, a Card whose route is not selected, a Read Set closure that does not resolve, Coverage the Queue compiler rejects, or a proposed after-image that fails `check_queue`. It compiles the Queue in memory only to prove one is derivable and to report its size; it writes no Queue bytes, because before first materialization Coverage and the Contract are adopter inputs while the Queue crossing that line is materialization itself, which `compile_queue --apply` owns. The state it leaves is the unmaterialized runtime that `check_queue`'s own `allow_unmaterialized_queue` names and that `compile_queue` sets to read it; both the dry run and the commit print the exact compiler command with the untouched Queue revision and fingerprint filled in. Writes Coverage and Progress under the shared state-writer lock after re-verifying the before images, appends one commit receipt, and restores the before images plus an abort receipt on any failure after the first replacement. Re-applying the same plan bytes resumes an interruption; a different plan over an already-planned runtime is refused. The initial contract may carry the closed `amendment_authority` block; absent or `user-only` is the safe default, and delegated mode names only registered bounded change classes. The receipt carries no Gate ID: the state it writes is consumed by gates that already exist | `python3 Tools/apply_task_plan.py . --plan .cambium/deltas/task-plans/TP-001.yaml --apply` |
| `apply_contract_amendment.py` | Guarded writer 1.1.0 for the two closed non-scope Task Contract fields the runtime supports (K13/06 Contract Amendment; field shape owner K13/02): `policy_exceptions` and `amendment_authority`. Consumes one confirmed restricted-YAML plan under `.cambium/deltas/contract-amendments/`; no pending phase -- it validates the complete after-image (including the K13/02 exception shape and the proposed runtime under `check_queue` with its own commit receipt as the anchor event) and commits Queue + Progress under the shared writer lock, or writes nothing. Advances `contract_version` and the Queue revision exactly once; changes no scope, batch structure, or lifecycle; integrator-only on apply. A schema-2 plan supplies both complete after-images; `changed_contract_fields` records which actually moved. The verified `contract-amendment` row it appends binds plan path/SHA and the commit receipt, and the contract anchor chain follows the fingerprint change instead of failing closed. Every exception for a registered policy must carry the CURRENT effective-policy fingerprint (`kblib.effective_priority_policy`; the refusal prints the expected value -- it is not computable by hand), and the effective ceilings -- exception where granted, standing quota where not -- must jointly stay strictly below 100 (K00/07). Refuses while any batch is `merge-ready` (the Queue-revision bump would strand its `delta_apply` binding); re-resolves the policy and re-verifies the plan bytes inside the commit lock; participates in the generic writer recovery protocol (`receipt_id`/`receipt_path`/`transaction_phase` in the lock metadata), and an uncertain receipt append retains the lock. Re-applying needs a fresh plan against the moved runtime; an exception is removed by confirming a plan whose after list no longer carries it | `python3 Tools/apply_contract_amendment.py . --plan .cambium/deltas/contract-amendments/CA-001.yaml --actor-role integrator --apply` |
| `check_queue.py` | Required Queue Gate producer 1.20.1 (K13/08): validates schema, manifests, Coverage projection, dependencies, lifecycle/task receipts, holds, confirmations, hash-bound complex-batch Work Specs, deltas, concurrency, Progress revisions/fingerprint, paths, readiness, and terminal count. For current Standards revalidation it validates K00/12's closed capability registry, projects semantic leaves to their owner Gates, accepts raw receipts only for the due immediate-owner set, and records native owners as deferred to the transition that already owns them; historical plans and consumed aggregates keep producer-era semantics, including both the raw affected-gate union and boundary-level required gates recorded by pre-1.6 adoption producers. It also derives the live Task Contract's transitive Read Set closure: every referenced Read Set must be declared, kernel/profile types and namespaces must agree with the selected Profile and route IDs, and every ordinary boundary target must occur in `loaded_module_paths`; Profile-owned contract dependencies are authorized by `profile-load` and are not added to that kernel load list. Both the public R01 Queue admission and the lower-level runtime validator require the complete selected-Profile closure by default, so ordinary writers cannot bypass `profile-load`. The sole smaller identity/sentinel escape is an explicit `adopt_standards.py` option for its persisted current/before read; it is rejected for state overrides or pending receipts, and every candidate after-image remains under full `profile-load`. Unsafe or non-UTF-8 inputs fail closed. The hot receipt catalog never deserializes `.cambium/receipts/cold/` (K12/07): the cold manifest and index load instead. What sealing retires is that deserialization, not integrity -- every run re-hashes every sealed segment against the manifest, proves every projection against the exact sealed line it names, proves both cold registers against the seal receipt that wrote them, and fails closed on an unreferenced segment, an unfinished seal transaction, or a sealed row that still has a hot twin. Rows of a seal whose binding does not hold -- including one produced by an unsupported sealing protocol, or whose segment hash failed -- never enter the catalog at all. Cold paths may not traverse a symlink or carry a second hard link, and a close attestation's born-cold candidate evidence is compared against the hash it bound, not just its length. A sealed receipt then satisfies existence and the closed-bundle identity branch through its thin projection, and a consumer needing live field revalidation of a sealed body fails closed unless it has an explicit sealed branch. The Standards-revalidation consumption replay is such a branch: it resolves the aggregate a Queue transition consumed from the segment that receipt's verified projection names, re-proving the record's own hash at the read, because the consumed keys live in `revalidation_bindings` and the retraction test reads `invalidated_by` and no projection carries either. An aggregate a recorded transition consumed but that resolves in neither namespace fails the run closed rather than reopening a discharged obligation. `--require-complete` is the build-closure Queue gate, so a Terminal Proof cannot authorize an under-declared live load set. `--require-maintenance-complete` additionally consumes current budget-manifest-closed, Coverage-ledger-advanced, and watermark-advanced receipts; reconciles the manifest's complete selected/deferred candidate partition with Coverage and the Queue manifest union; enforces consecutive-deferral disposition; and binds the maintenance pass to all three current state objects. `--resume-status` reports objective/exclusions, completion semantics, three live SHAs, checkpoint/task history, Work Spec bindings, maintenance candidate SHA/partition/prior gate, controls, the applicable completion block, locks, and an exact `next_action`. Valid interrupted delta phases become `admit-delta:<id>` or `apply-delta:<id>`; an applied batch without a current close bundle becomes `run-batch-close-gate:<id>`, while a recovered current bundle becomes `close-applied-batch:<id>:<queue-receipt>:<close-receipt>:<apply-receipt>` plus an exact copyable close command. Current close attestations also validate the `exact-carry-v1` baseline plus carried/fresh partitions and their born-cold evidence; historical Queue transitions replay update_queue/1.2.0 while new ones require 1.3.0, and historical closed deltas replay apply_delta/1.4.0 while new applies require 1.5.0. A writer lock always takes recovery priority; inconsistent evidence becomes `repair-runtime` only when no interrupted writer must first be reconciled | `python3 Tools/check_queue.py . --resume-status` |
| `check_batch_close.py` | Sole supported producer contract 1.10.0 for the K12/09 merged-snapshot close bundle. Under the shared runtime lock it first runs the complete `profile-load` producer for the selected manifest—identity, all 13 slots, package snapshot, and typed secondary closure—and compiles the required Registered Scan from that exact authorized in-memory contract. A valid Audit/Scan subgraph cannot execute when any other Profile slot is broken. Scan identity, verifier, optional explicit config, predicate, semantics, and Judgment Item bindings therefore share the same authority as admission; the Cambium residual scanner requires its Profile-owned config, while a registered custom verifier may validly declare no `--config`. For one `merge-ready` batch with a current `apply_delta` receipt, it recomputes real repository bytes before/after the Closed List checks and receipt publication; runs `check_links`, Cambium-owned YAML/Markdown structure, a deterministic in-memory Markdown/Wiki-link graph JSON projection plus basename candidates, Coverage file-count, guidance/contract continuity, the selected profile's registered verifier, and `check_vocab` (excluding `kernel/Cards` and `profiles/` — profile directories are control plane, and shipped example instances carry their own vocabularies); invokes the same registered verifier first with the additional standard `--positive-controls-only` flag and then as its unchanged production command, requiring both final pass summaries to bind exactly the same producer, check, scan/config identity, positive-control result/mode/count, and canonical control fingerprint. It also compares each self-report to the admitted contract: `scan_id` must equal the Registered Scan ID, and an explicit config fingerprint must equal the SHA-256 of the admitted config bytes. It records an explicit reviewer attestation with a reviewer label different from the integrator label; creates the canonical `check_queue` consistency receipt through that checker's shared producer; and emits the exact three IDs consumed by close. Candidate detail is written once per attempt as a born-cold evidence file under `.cambium/receipts/cold/close-evidence/`; the attestation binds it by path/hash/bytes/records and carries counts, per-type counts, the accepted-set fingerprint, and only the policy-exception dispositions inline, while member and failure receipts bind the same evidence instead of repeating rows (K12/09). Version 1.10.0 is the only producer protocol a current close action or recovery may consume. Versions 1.4.0 through 1.9.0 remain recognized only while replaying already-sealed closed history; 1.4.0 keeps its seven-member Closed List shape, and no historical version can authorize a new close. Labels and attestations remain assertions under the Evidence trust boundary. Item 3 does not scan ordinary repository JSON or fenced JSON examples; item 1 alone owns missing/ambiguous/heading verdicts. Every run still performs the complete scan. An ordinary finding may carry from only the immediately preceding verified close when its prior disposition was `accept-while-unchanged`, its stable ID, exact observation hash, and producer version still match, and it is not manifest-local page-contract debt; legacy evidence grants no carry, a disappearance breaks continuity, and a type selector expands only the exact fresh rows present now. Fresh findings use the current-only selectors or `--accept-while-unchanged-id/type`. Candidate prose alone is insufficient. A priority-quota candidate cannot use those generic selectors: it is consumed only through a currently valid bounded contract policy exception (K00/07), compared with exact rational arithmetic over the candidate's structured share, judged against the effective-policy fingerprint from one resolver call shared with the quotas handed to `check_vocab`, and sealed into the disposition as decision facts so the receipt replays after revocation. A failed run emits only a failed attempt, while an uncertain append retains the lock | `python3 Tools/check_batch_close.py . --batch B1 --integrator alice --reviewer bob --review-attestation "Reviewed the exact listed candidates and merged snapshot."` |
| `seal_receipts.py` | Receipt cold-chain writer 1.3.0 (K12/07 Receipt Sealing). **`--apply` is a maintenance-window operation**: run it only in a declared quiet window, after confirming no other Cambium or adopter writer, checker or receipt appender is active against the repository. Moves verified frozen rows of closed batches -- each batch's close-bundle trio as one unit, whole per-batch registers, page-contract snapshots -- verbatim into `.cambium/receipts/cold/segments/`, appends one manifest entry per segment and one thin projection per receipt, rewrites the hot registers without the sealed rows, and adopts into the manifest only those born-cold close-evidence files a current attestation binds by hash. Refuses to run unless the complete runtime validation passes with zero errors, no writer lock is active, and no delta application is pending; every byte the plan was computed from is re-compared inside the locks. The shared receipt append mutex (`.cambium/tmp/receipt-append.free`/`.held`, a rename because mounts that refuse `unlink` cannot release a lock directory) is a guard against the accident of running a writer beside a seal, not a proof of mutual exclusion under arbitrary concurrency -- it is re-entrant per process and binds only appenders using the shared primitive. Publication is journalled -- a `begin` row and a hash-bound pending record before the first segment byte, a `complete` row only after every postcondition is re-proved -- so an interrupted seal fails every later run closed; `--reconcile --apply` automatically finishes the publication paths this tool implements and refuses a live writer's lock or a drifted pending record, while any other interruption is resolved by the runbook below. What sealing retires is deserialization, not integrity: `check_queue` re-hashes every segment, re-proves every projection against the sealed line it names, and re-proves both cold registers against this tool's receipt on every run. Never seals: transition history, Standards adoptions, amendments, its own register, activation/confirmation gates, batch-review wrappers, the Standards-revalidation aggregate a recorded Queue transition consumed (its replay reads `revalidation_bindings` and `invalidated_by`, which no projection carries), or anything bound to a non-closed batch | `python3 Tools/seal_receipts.py . --apply` |
| `compile_queue.py` | Queue compiler 1.5.0 deterministically compiles Queue structure from explicit Required Coverage assignments plus top-level `batch_specs`; never infers semantic dependencies or backlinks. Every spec explicitly declares both Work Spec fields: null/null for a simple batch, or one exact `.cambium/work_specs/*.yaml` path/SHA pair for a complex batch. Initial `--apply` is integrator-only and writes the unique origin receipt into Progress. A same-scope replan consumes a complete `.cambium/deltas/replans/*.coverage.yaml` proposal—never pre-edited canonical Coverage—and a matching current registration written by `register_amendment.py`; it commits Coverage/Queue/Progress under one shared lock after exact three-file CAS, registration/Amendment/diff binding, and conflict checks. Registration binds either explicit-user authority or the Task Contract's exact delegated change classes, which are re-derived before write. Terminal history remains immutable; interrupted/incompletely rolled-back writes retain the lock | `python3 Tools/compile_queue.py . --coverage-proposal .cambium/deltas/replans/A1.coverage.yaml --output .cambium/tmp/queue-replan.yaml` |
| `update_task.py` | Sole Progress task-state transition writer. Dry-run-first and integrator-only; compare-and-swaps current Progress and Queue SHAs under the shared lock, records a transition receipt and restart checkpoint, and requires a reason for pause/block. One successful entry runtime admission freezes the Profile/K00 authority pair for the whole transaction: proposed, locked, and post-write validation inject it without rerunning Profile load, while both sides of every Progress/receipt write perform currency CAS. A build task consumes a current Queue-complete receipt to enter `completion-candidate`, then a canonical `check_proof` 1.17 pass receipt to enter `complete`; the proof and transition repeat its Profile closure and repository snapshot, and the writer rechecks the repository before/after state and receipt publication. A maintenance task never enters `completion-candidate`; its `planned` or `active` state enters `complete` only by consuming a current `check_queue --require-maintenance-complete` receipt through `--maintenance-completion-receipt`. Direct `planned -> active` remains rejected; `update_queue.py` invokes that owner only while opening the first batch | `python3 Tools/update_task.py . --transition paused --checkpoint-summary "waiting for source" --expected-progress-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `update_queue.py` | Lifecycle writer 1.6.0, dry-run-first, integrator-only lifecycle/hold transition with legal-state enforcement, current contract-conformant gate/confirmation/batch receipts, exact managed delta validation and frozen SHA, optimistic revision/SHA checks, the shared writer lock, rollback, result-state revalidation, and before/after receipt history. Queue writes require task state `active`; the first open atomically invokes the task-state owner for `planned -> active`. The `open -> merge-ready` edge proves and binds the prospective routed-gap settlement before freezing the Delta. Close requires the exact `apply_delta` receipt and derives Coverage `next_batch`. Cancellation goes through a registered `apply_amendment.py` transaction | `python3 Tools/update_queue.py . --id B1 --transition open --gate-receipt RECEIPT --expected-state-revision 0 --expected-sha256 sha256:... --actor-role integrator --apply` |
| `register_amendment.py` | Sole registration writer 1.2.0 of executable operational Amendment rows for same-scope Queue replans, scope replans, batch cancellation, and narrow gap-routing reconciliation. It derives the closed impact/change-class set and chooses explicit-user or matching contract-delegated authority; unknown or nondelegable classes fail closed. It accepts only the current state schema, defaults to dry-run; `--decision-mode auto|contract-delegated|explicit-user` makes the authority source explicit, requires an integrator plus exact Coverage/Queue/Progress SHA compare-and-swap, and rechecks repository-contained proposals/plans under the shared lock. It publishes the append-only receipt first, then one approved pending Progress row that names it; an unreferenced receipt is inert, so interruption cannot leave Progress pointing at absent evidence. A pending receipt is current authorization and must bind the live Progress bytes; a verified execution must bridge its three before-SHAs and time to registration, after which the registration is historical evidence only. At most one operational Amendment may be pending. `--withdraw <amendment-id> --reason "..."` retires a pending registration whose execution can no longer validate (K13/06): it publishes an append-only withdrawal receipt naming the registration receipt and sets the row's status to `withdrawn` with write-back still false; the bound plan/proposal bytes stay verified immutable evidence and the amendment ID is never reused | `python3 Tools/register_amendment.py . --operation scope-replan --plan .cambium/deltas/amendments/A1.yaml --date YYYY-MM-DD --summary "Approved scope change" --approval-reference APPROVAL --expected-coverage-sha256 sha256:... --expected-progress-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `apply_amendment.py` | Cross-Ledger writer 1.2.0 consumes one registered approved scope/disposition change as a guarded Coverage/Queue/Progress transaction. The plan and registration receipt bind exact before revisions and all three SHAs to a complete Coverage proposal; `scope-replan` recompiles current Queue structure, `cancel-batch` retires one queued/open leaf, and `gap-routing-reconciliation` closes or reroutes existing gaps without creating findings; every operation preserves terminal history. The writer re-derives the registered authority impact under lock. A durable prepare receipt plus lock-owner fingerprints make an interrupted multi-file write diagnosable; commit/abort receipts record the consumed registration and outcome. It does not write non-scope Task Contract changes; direct post-materialization edits fail closed and currently require a preserved successor task | `python3 Tools/apply_amendment.py . --plan .cambium/deltas/amendments/A1.yaml --expected-coverage-sha256 sha256:... --expected-progress-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `adopt_standards.py` | Sole active-task Standards/Profile adoption writer 1.6.0 (K12/10 semantics; K13/15 transaction). Its closed YAML plan binds approved K00/03 bytes and upstream identity, deterministic after Kernel/Profile snapshots, Task/Contract identity, Queue revisions, three state SHAs, changed semantic predicates, dimension/boundary-specific invalidated evidence, the capability-registry projection from leaves to owner Gates, the complete derived after-load contract, and the root-owned profile-load-input fingerprint. The candidate `selected_profile_manifest_after` must pass full `profile-load` before any state write. Admission captures receipt-free snapshot/contract/input evidence; apply reruns and compares it under the writer lock before state writes, after state writes, and immediately before and after final receipt publication. Candidate evaluation never enters the current Queue receipt catalog. Drift before a durable commit restores the three before images and records abort; drift after commit evidence additionally retains the recovery lock. A `profile-load` invalidation boundary targets exactly that after-image manifest and requires the `profile-load` Gate; admission itself is not batch-scoped and is omitted from the batch rerun union, while any downstream Gates named by the same boundary keep their declared batch/Terminal reachability obligations. The Read Set closure is not a hand-picked sample: selected Read Sets are transitively closed, profile supplemental routes remain inside the selected Profile and declared route namespace, and ordinary boundary targets are all loaded modules. Dry-run is default; apply accepts only `active`/`paused`, rejects incompatible Work Specs, affected `merge-ready` batches, or affected `open` batches without `revalidation-required`, and changes no lifecycle/hold itself. It requires all three canonical state objects to satisfy the current schema, synchronizes identity/load set, advances Queue/Progress `queue_revision` once, records append-only adoption history, and consumes immediate Queue consistency before commit. Only `required-queue-consistency` is an immediate raw claim; native review, close, and completion owners remain required by their ordinary transitions, and raw leaf receipts cannot discharge them early. Sealed pre-1.3 history may omit the typed-contract fingerprint, sealed pre-1.4 history may omit the root-input fingerprint, and sealed pre-1.5 history may omit the upstream identity pair; historical receipts are not rewritten and remain catalogued, but only compatible producer protocols may satisfy the live execution chain. Prepare/commit/abort plus the lock recover partial writes; no Markdown adoption report is produced | `python3 Tools/adopt_standards.py . --plan .cambium/deltas/standards-adoptions/SA-001.yaml --apply --actor-role integrator` |
| `render_queue.py` | Deterministically render the optional human view at `.cambium/reports/required_queue.md`, including each Queue item's Work Spec path/SHA binding; validates canonical state first and never reads the Markdown back as input | `python3 Tools/render_queue.py .` |
| `apply_delta.py` | Delta writer 1.5.0 deterministically applies one worker Coverage delta during serial merge. Every mode rejects Queue/compiler-owned control fields. `--preflight` validates the prospective routed-gap after-image while the batch is still open and writes nothing. Canonical `--root` mode binds the exact managed paths and merge-ready manifest, requires integrator role plus current Coverage/Queue SHAs, uses the shared writer lock, revalidates the result, rolls back ordinary failures, and publishes a bound receipt into a new file rather than appending to a shared JSONL -- omit `--receipts` and the run names `.cambium/receipts/<receipt_id>.jsonl` itself; an existing `--receipts` path is refused. Gap obligations and their settlement fingerprints are bound into current receipts. `next_batch_updates` remains a suggestion for the integrator. Detached two-path mode remains for non-runtime ledgers and is not a canonical-state write | `python3 Tools/apply_delta.py .cambium/state/coverage_ledger.yaml .cambium/deltas/B1.yaml --root . --expected-coverage-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `compose_vocab.py` | Persistent vocabulary compiler 1.7.0: composes `vocab.yaml` from the kernel base and the profile selected in K00/03 active state. The selected manifest declares `profile_id` and its one `Vocabulary Extensions` binding; `volatility_defaults` registers each domain once; the resolved extensions path supplies base-field extension ownership; profile-only controlled fields are added to the frontmatter list automatically. `--extensions` may repeat the bound active path but cannot select another profile; the output header is provenance only. `--check` requires both parsed values and deterministic provenance/rendering to match | `python3 Tools/compose_vocab.py --check` |
| `scaffold_profile.py` | Safe candidate-profile scaffolder 1.0.0: copies `profiles/_template` to `profiles/<profile-id>` using ONLY the exact whitelist in `profiles/template-files.yaml` (never a directory walk, so junk in the template is never copied; a missing or symlinked whitelisted file fails closed), then performs only the mechanical derivations that are pure functions of the profile id — the manifest `profile_id`, the registered-scan verifier command's own `--config` path, and both Audit Dimension predicate-owner paths with their `#heading` fragments (the interview's `self_path_rewrites`). Every rewrite is anchored to exact template text and fails closed on template drift; every semantic `TODO(profile)` answer is left in place, so the fresh candidate is EXPECTED to still fail `check_profile.py` until the interview is complete. Dry-run by default; `--apply` stages into a dot-prefixed directory inside `profiles/` and publishes with one rename, removing the staging tree on any failure. Refuses an existing destination in any form (directory — even empty — file, or symlink), never merges or overwrites, touches neither `kernel/` (including K00/03) nor `.cambium/`, writes no receipt, and never selects or adopts the candidate — selection remains R09 adoption | `python3 Tools/scaffold_profile.py . --profile-id my-profile --apply` |
| `profile_onboarding_status.py` | Read-only onboarding status projector 1.0.0: derives — and never stores — the adoption/onboarding state of one root and exactly one machine-readable `next_action` token (`not-a-cambium-root`, `resume-existing-task`, `repair-control-state`, `confirm-profile-identity`, `complete-profile-interview`, `authorize-r09`, `found-empty-corpus`, `prepare-task-plan`, `onboarding-complete`), with existing-runtime recovery always winning over scaffolding and adoption. It reports whether the root is an adopting root, the K00/03 placeholder state (pre-adoption / adopted with the four values / inconsistent naming the fields), the selected manifest, the selected or targeted profile's Corpus Planning `applicability.state`, every candidate profile with its sentinel count plus a full in-process `profile-load` evaluation of the targeted candidate split into mechanical vs semantic-unresolved finding counts, the corpus page count outside the distribution/control trees, and `.cambium/` presence. It writes nothing, creates no receipts, owns no ledger, and decides nothing — every value is derived from bytes owned elsewhere, and each state's next step stays with its canonical owner tool | `python3 Tools/profile_onboarding_status.py . --json` |
| `apply_profile_adoption.py` | Sole no-runtime R09 Profile-adoption transaction writer 1.0.0: the sibling of `adopt_standards.py` for the two R09 branches that exist BEFORE any `.cambium/` runtime does — initial adoption (all four K00/03 Standards Control placeholders uninstantiated) and a pre-runtime profile revision (all four instantiated and matching the plan's `before` cells). Dry-run first; its closed restricted-YAML plan (`schemas/profile_adoption_plan.template.yaml`) binds the exact current K00/03 bytes plus the candidate's `profile-load` snapshot, typed-contract, and root-input fingerprints, and apply re-verifies every binding through the canonical `check_profile` producer — drift, a failing candidate, a partial K00/03 instantiation, or a branch/state mismatch refuses with zero writes, and the tool never adopts unseen bytes or reimplements any part of the Gate. The transaction stages backups of every to-be-touched file under a dot-prefixed `.r09-adoption-<plan-id>/` journal, writes the K00/03 after-image (four cells plus one Change Summary row) and the mechanical K00/16 re-measure the Revision Write-back Checklist names, then drives `compose_vocab`, `compose_page_contract`, `stamp_cards --set-version`, and `stamp_cards --check` against the new state; any failure restores every touched byte (verified) and marks the journal aborted, so no partial adoption survives. Re-running with the same plan recovers an interruption; a different plan over an existing journal is refused. On success it appends the exact `profile-load` pass receipt plus its own commit receipt (which, like `apply_task_plan.py`, registers no Gate ID) to `<plan>.receipts.jsonl` beside the plan or an explicit `--receipts` path — never `.cambium/receipts/`, because no runtime exists, and a root carrying `.cambium/` anywhere is refused toward the active-task `adopt_standards.py` flow. The candidate Profile directory is read-only to this tool | `python3 Tools/apply_profile_adoption.py . --plan adoption-plans/PA-001.yaml --apply` |
| `check_profile.py` | Sole `profile-load` Gate producer 1.9.0. It derives the slot list from `profiles/README.md`; verifies identity/directory agreement, slot bindings, sparse execution overrides, `Configured`/inactive table consistency, invalid UTF-8, sentinels, reserved IDs, and the Structure Registry's closed shape. It then calls `profile_contract.py` once to authorize the machine-active self-path closure from the selected manifest through the Audit Dimension Registry's extension dimensions and Judgment Item owner headings and the Registered Scan Registry's verifier, optional config, predicate, semantics, and Judgment Item references. Every Profile-owned path must remain lexically and physically inside the selected Profile, exact heading references resolve once, and symlink/hardlink aliases fail closed. A pass summary uses check `profile-check-summary`, Gate ID `profile-load`, dimension `guidance_and_contract`, and binds `selected_profile_manifest`, the complete Profile-tree `profile_snapshot_sha256`, `profile_contract_fingerprint`, and the canonical root-input `profile_load_inputs_sha256`. Receipt output is refused inside the Profile itself so validation cannot mutate the package whose snapshot it binds. The checker parses one immutable Profile-tree snapshot and rechecks both that tree and the canonical inputs before authorization. It checks authority and structure, never answer quality, and is not run against `_template` itself. `--json` writes one deterministic structured-diagnostics object to stdout (tool, root, result, findings), each finding carrying a category from the closed classification map: `mechanical` (an assisting agent can fix it directly and rerun — path resolution, identity/directory agreement, table and manifest shape, self-reference containment, declaration word shape) vs `semantic-unresolved` (an operator answer is missing or unconfirmed — `unfilled-placeholder` sentinels and other open decisions); human output, receipts, and exit codes are unchanged | `python3 Tools/check_profile.py profiles/<profile-id> --root . --receipts Tools/receipts/profile.jsonl` |
| `check_structure.py` | Sole `structure-registry` gate 1.1.0 (K01/05, K01/06): resolves the selected profile's Structure Registry against the vault — unit and support-layer roots, canonical entries and `expected_type` frontmatter, embedded headings, per-mode role declarations, Profile Scope layer membership, module-inside-parent containment, flat/grouped layout consistency with declared class-to-directory agreement, Corpus Planning Global Map entry bindings, and Coverage Ledger `structural_unit` references; `--profile` overrides the active-state selection; fails closed on an unresolved profile, unbound or unreadable registry, or a configured registry with no units. It proves structure declarations, never content quality or class-assignment semantics | `python3 Tools/check_structure.py . --profile profiles/<profile-id> --receipts Tools/receipts/structure.jsonl` |
| `compose_page_contract.py` | Deterministic page-contract compiler 1.2.0 (K08/06): composes the kernel `applicability-base.yaml` and `relationship-base.yaml` with the selected profile's `Metadata Contract` and `Vocabulary Extensions` and the K07 `sources-role-base.yaml` into `Tools/page_contract.yaml`, including the profile-bound section-role display titles; a profile difference may only tighten a kernel mode, extensions must not collide with kernel fields, and `--check` verifies the artifact is byte-current; the K08/09 boundary projection display labels compose as kernel defaults overlaid by the profile's `boundary_projection.labels`; `--profile` names a profile for a validation run without selecting it | `python3 Tools/compose_page_contract.py --profile profiles/<profile-id>` |
| `project_page_state.py` | K08/07 page-state projector 1.1.0: rewrites the page-frontmatter copies of the Ledger-owned projection fields (`coverage_disposition`, `authoring_status`, `next_batch`) to the Coverage Ledger owner values — update on divergence, remove when the owner value is empty, never add a field the page does not carry. Dry run reads each selected target once. Apply holds the shared runtime writer lock, builds one immutable Ledger/page plan, stages only changed pages, and performs one final exact identity-and-bytes descriptor open per changed page; safely missing rows remain typed no-ops and are revalidated. Cooperating writers use the same lock, and each changed page then uses a no-clobber claim/install sequence; the batch is not a filesystem-wide atomic transaction. A later failure restores claimed original inodes in reverse order, while unexpected namespace drift or an unproven rollback retains the writer lock plus a journal that pre-registers page-to-artifact before/after evidence. The batch close runs it (or the integrator acts as it) after the close projection so no page keeps a pre-close status or a stale routing to a closed batch | `python3 Tools/project_page_state.py . --apply` |
| `check_page_contract.py` | Advisory `page-contract` gate 1.4.0 (K08/06-08): validates pages against the compiled contract — required/conditional presence, empty-placeholder noise, forbidden fields, non-persisted derived values, `coverage_disposition` reconciliation against the Coverage Ledger, date/url/path/list shapes, relationship target types, the unknown-field closure (the legacy `status` alias is reported for migration), and the K07 sources-role section by registered display title with at most one role heading per page — a missing `Related` is never reported (K09/04); scope defaults to the Profile Scope layer directories and a zero-page scan fails closed; a `delegated`-shaped field (the K08/09 `boundary` block) is checked here for presence and mode only, its internal structure staying with `boundary-contract`; violations are candidates (exit 2) until a governance decision promotes `--strict` | `python3 Tools/check_page_contract.py . --profile profiles/<profile-id> --receipts Tools/receipts/page-contract.jsonl` |
| `check_boundary_contract.py` | Advisory `boundary-contract` gate 1.1.0 (K08/09): validates every in-scope page carrying a `boundary` frontmatter block — schema and slug shapes, in-block uniqueness and owns/excludes overlap, `excludes[].owner` resolvability and non-self-reference, reciprocity against the owner page's own `boundary.owns` (an owner with no block at all stays a migration-tolerated candidate even under `--strict`), corpus-wide one-owner-per-concern uniqueness, and freshness of the marker-delimited boundary projection against the shared kblib rendering with the compiled contract's display labels; pages without markers are skipped, never stale; concern vocabulary membership stays with `frontmatter-vocabulary`; violations are candidates (exit 2) until a governance decision promotes `--strict` | `python3 Tools/check_boundary_contract.py . --profile profiles/<profile-id> --receipts Tools/receipts/boundary.jsonl` |
| `render_boundary_projection.py` | Registered generator 1.1.0 for the K08/09 boundary projection block: recomputes the marker-delimited block from each page's `boundary` frontmatter and the compiled contract's `boundary_projection` labels through the same kblib rendering the checker compares against; marker placement is curated, so a page without markers is skipped and counted; `--check` reports stale blocks, `--apply` writes them atomically, malformed markers are input errors | `python3 Tools/render_boundary_projection.py . --profile profiles/<profile-id> --check` |
| `render_structure_projection.py` | Registered generator 1.1.0 for Structure Registry `derived` coverage roles (K01/05): computes each unit's projection from the Capability Matrix and Coverage Ledger and owns only the marker-delimited block inside the registered section — curated prose around it is conserved; `--check` reports stale blocks, `--apply` writes them atomically, and roles without a page target render on demand; it copies no Queue lifecycle and never writes back into planning artifacts | `python3 Tools/render_structure_projection.py . --profile profiles/<profile-id> --check` |
| `check_residual_content.py` | Generic, Profile-blind K12/09 item 6 residual-content scanner: it receives `--scan-id` and `--config` explicitly and neither discovers the selected Profile nor parses its registry. The selected profile owns every accepted/excluded content root and every literal frontmatter/heading matcher in that config; only VCS metadata directories named `.git`, `.hg`, or `.svn` are always outside traversal. The tool owns safe traversal, fence-aware matching, a hard ≤55-second evidence-production budget, zero-file, missing-accepted-root, and inert-matcher failure, receipts, and `0/1/2` exit semantics; missing excluded roots are allowed. Its `mandated_headings` control inputs run through the production `classify` path. `--positive-controls-only` loads the same config and executes those controls without scanning repository content; batch close runs that explicit mode before the production scan and binds the two final summaries. When a production run finds no candidate, the accepted roots are additionally re-read as the profile's own known-residual sample and the configuration must recognise at least one Markdown file there, otherwise the run fails with `residual-content-inert-matcher`; the summary then names the witness. The caller must still satisfy the kernel's ≤60-second whole-command contract. `--scan-id` binds every receipt to the stable registry ID; receipts from a successfully loaded config record its SHA-256 so configuration changes invalidate old evidence. Findings are candidates only. Tool contract owner: K12/09 item 6; scan-definition owner: selected profile `Registered Scan Registry` | `python3 Tools/check_residual_content.py . --scan-id <stable-scan-id> --config profiles/<profile-id>/scan-configs/<scan>.yaml --time-limit 55 --receipts Tools/receipts/residual.jsonl` |
| `profile_contract.py` | Shared library and sole typed Profile-contract linker, not a command. It parses the exact machine-active Audit Dimension and Registered Scan sections into a source-addressable intermediate representation; resolves Profile-owned files and heading fragments under lexical and real-path containment; rejects ambiguous, missing, symlinked, or multiply linked dependencies; and emits a canonical dependency-graph fingerprint only when the whole contract is authorized. `check_profile.py` and every runtime consumer reached through `profile_admission.py` consume this same result instead of independently reinterpreting those Markdown cells. It can compile the one required scan command for a caller, but it neither executes a verifier nor scans repository content | imported by the scripts above; no command-line entry point |
| `profile_admission.py` | Shared consumer adapter, not a command. It selects the explicit or K00/03-approved Profile, performs exactly one complete `profile-load`, exposes the authorized immutable Profile snapshot and typed slot paths/text, and rechecks Profile-tree, root-input, and active-selection currency before a consumer emits a pass result or writes an artifact. Profile-dependent tools use this view instead of reopening the manifest or slot files under a later revision | imported by the Profile-dependent scripts above; no command-line entry point |
| `stamp_cards.py` | Kernel route and Runtime Card verification (K00/03 Write-back Checklist): checks the shared `kernel-runtime-routes` registry identity, exact R01-R13 coverage across both indexes and the on-disk Read Set/Card pairs, filename prefixes, source boundaries, `source_hash`, that every `compiled_from` equals K00/03 active `standards_version`, that every `python3`-prefixed command span in the layer supplies the required arguments its tool declares, that every Card and Read Set carries the H2 sequence registered for it in K00/14 `Card And Read Set Skeleton`, that every kernel leaf module is named by some Read Set loading boundary registered in K00/15, that every kernel leaf module satisfies the K00/03 size budget as amended by the K00/16 register, and that every row of the K00/12 `Stable Gate ID Registry` agrees with the producer it names; defaults to `kernel/Cards`; missing, empty, incomplete, or malformed layers fail closed; `--check` is read-only; `--set-version` must equal the active version and stamps every Card including the Index | `python3 Tools/stamp_cards.py . --check` |
| `compile_cli_contract.py` | Persistent CLI invocation-contract compiler 1.0.0: derives `Tools/compiled/cli-contract.yaml` from the `argparse` declaration each `Tools/*.py` CLI builds for itself, so the calling contract has one source rather than a prose restatement that can drift. Each tool is imported with `parse_args` patched to raise the instant its parser is complete, so no tool behaviour runs and no tool signature changes; per argument it records `option_strings` (empty for a positional), `dest`, `required`, the evaluated `default`, `choices`, `nargs`, `action`, `type` name and `help`, plus each `add_mutually_exclusive_group` and the receipt extension fields that tool's own source writes onto a `make_*receipt(...)` result. The artifact is machine-generated and must not be hand-edited; it registers no K00/12 Gate ID because it depends on no selected profile and `run_gates` could therefore never sweep it, which is why `make check` runs it directly. `--check` exits 2 when the artifact is stale or hand-edited, 1 only when the evidence itself is unreliable | `python3 Tools/compile_cli_contract.py . --check` |
| `render_interface_projection.py` | Agent-facing form projection 1.0.0: projects `Tools/compiled/cli-contract.yaml` into the interface shapes an agent runtime actually reads, so a protocol-shaped tool list is a derived view of the one compiled contract rather than a second declaration of it. `FORMS` is a registry, not a special case: each entry names its own output and builder, `--form` selects one, and an argument-free run writes or checks every registered form. The `mcp` form writes `Tools/compiled/mcp-tools.json` -- per tool a `name`, the argparse `description`, and an `inputSchema` whose properties are keyed by `dest` (an undeclared `type` projects as `string`, which is what argv carries; `choices` becomes `enum`, `required` becomes the `required` array, an empty `option_strings` is the positional), plus `stdio` and `streamable-http` and no other transport branch. Every projected field is bound in the tool's own `FIELD_SOURCES` table to the upstream field or rule it comes from, and a field no source covers fails the run; `--sources` prints that table. The artifact carries the sha256 of the contract bytes it was projected from and that contract's own manifest hash, so one upstream change invalidates every form at once and no two forms are ever compared with each other. It is machine-generated and must not be hand-edited, and it registers no K00/12 Gate ID for the same reason its upstream does not. `--check` exits 2 when an artifact is stale or hand-edited, and 1 when the evidence is unreliable -- including when the compiled contract changes underneath the run | `python3 Tools/render_interface_projection.py . --check` |
| `render_host_configs.py` | MCP server registration and corpus binding 1.0.0: renders the one server definition body this tool declares (`command`, `args`, `cwd`, `env`, and the dsh-only connection-resilience superset) into the configuration file each supported host actually reads. Registration -- where the server is and how it starts -- is once per machine; binding -- which corpus this run governs, carried as `CAMBIUM_WORKSPACE_ROOT` -- is once per corpus. `HOSTS` is a registry with one builder and one output file per host: Claude Code (`<corpus>/.mcp.json`), Kimi Code (`<corpus>/.kimi-code/mcp.json`), Codex (`<corpus>/.codex/config.toml`, loaded only for a trusted project), dsh's per-corpus `.env` (binding only) and dsh's `$DSH_HOME/profiles/<name>/` rows (registration only). The five products are templates rendered under `Tools/compiled/host-configs/` for an adopter's corpus repository; this distribution registers no MCP server with itself and writes none of these files at its own root. Every product carries `CAMBIUM_INTERFACE_SOURCE_HASH`, the sha256 of the `compiled/mcp-tools.json` bytes it was rendered against, so one upstream change makes all five stale at once. Every rendered field is bound in the tool's own `FIELD_SOURCES` table -- the server name included, because the name is spelled into those paths -- and a field no source covers fails the run; `--sources` prints that table. `--distribution-root` and `--workspace-root` substitute the two placeholders for an onboarding flow writing a bound copy. It is machine-generated and must not be hand-edited, and it registers no K00/12 Gate ID for the same reason its upstream does not. `--check` exits 2 when a product is stale or hand-edited, and 1 when the evidence is unreliable | `python3 Tools/render_host_configs.py . --check` |
| `check_freshness.py` | Freshness check 1.3.0: computes review_by from volatility and last_verified (fallback: last_reviewed, then file modification time per K08/05, flagged pending first verification); `--defaults` accepts a flat mapping or `Tools/vocab.yaml` / a profile's `vocabulary-extensions.yaml` (their `volatility_defaults`); canonical `Tools/vocab.yaml` is consumed only through the current admitted Profile and immutable artifact bytes, while explicit flat defaults remain standalone inputs; an all-skip run reports NOTHING CHECKED as a candidate, not a pass | `python3 Tools/check_freshness.py . --as-of 2026-07-21 --defaults profiles/<your-profile-id>/vocabulary-extensions.yaml --exclude Cards --receipts Tools/receipts/fresh.jsonl` |
| `duplicate_check.py` | Cross-file duplicate paragraph candidate detection; full vault by default; `--exclude` is repeatable and defaults to the single component `legacy`, the conventional name for a frozen-snapshot area that a vault need not have; compiled Cards and profile skeletons should be excluded from corpus-duplication review; supports `--receipts` and exits 2 when candidates exist | `python3 Tools/duplicate_check.py . --exclude _template --exclude Cards --receipts Tools/receipts/dup.jsonl` |
| `maintenance_candidates.py` | Shared library, not a command: the pure K00/08 maintenance-candidate set algebra `check_queue.py` uses for `--require-maintenance-complete` and `--resume-status`. It validates the closed candidate record fields, the four `source_kinds` (`freshness`, `watermark`, `needs-rereview`, `candidate-pool`), the selected/deferred partition against Coverage and the budget manifest, deferral age, and re-entry disposition, and it computes the stable `candidate-sha256:` identity and candidate-state fingerprint. It performs no writes, produces no receipts, and never decides whether the source scans found the right candidates | imported by `check_queue.py`; no command-line entry point |
| `candidate_lifecycle.py` | Pure K12/09 `exact-carry-v1` candidate set algebra. It hashes exact observations, partitions the current full scan against only the immediately preceding verified close, applies current-only or bounded-unchanged dispositions, and validates compact carried/fresh attestation fields. It does not scan, choose a baseline, write state, or mint receipts | imported by `check_batch_close.py` and `check_queue.py`; no command-line entry point |
| `coverage_delta.py` | Pure Coverage open-gap projection shared by Delta admission and application. It owns stable gap identity and applies exact add/close lists to an in-memory Coverage object; it performs no writes, chooses no route, and grants no Amendment authority | imported by Delta and settlement consumers; no command-line entry point |
| `batch_settlement.py` | Pure K13/08 routed-gap settlement predicates. It derives the exact obligation set and prospective after-image binding for a batch, and validates narrow close/reroute reconciliation against actionable later Queue targets; it performs no writes and never mutates a frozen Delta | imported by Queue, Delta, and Amendment consumers; no command-line entry point |
| `amendment_policy.py` | Pure K13/02-K13/06 operational-Amendment impact and authority policy. It derives the closed change-class set and writer operation and checks that exact set against explicit-user or Task Contract delegation; it performs no writes, stores no decision, and unknown or nondelegable effects fail closed | imported by Amendment and contract consumers; no command-line entry point |
| `kblib.py` | Shared library 1.7.0 and sole restricted-YAML parser owner. Duplicate keys and unsupported constructs fail closed; it also provides deterministic YAML rendering, repository-contained managed paths, typed snapshots for existing or safely missing repository targets, file and repository-snapshot SHA-256 fingerprints, atomic writes, Markdown helpers, and receipts | imported by the scripts above |

Every ordinary runtime writer (`compile_queue`, `update_queue`, `apply_delta`,
`register_amendment`, and `apply_amendment`) carries one indivisible authority
context from its first successful `check_queue.validate_runtime` call.  The
context contains the exact authorized Profile snapshot/contract/root-input
view and approved K00/03 byte view.  Proposed, locked, post-write, and
persisted-state validations inject those same objects instead of rerunning
`profile-load`; state and receipt publication CAS-check both views before and
after each boundary.  The lock owner records their durable fingerprints so a
restart can identify the authority revision of an interrupted transaction.

## Required Queue flow

The persistent runtime namespace belongs to the adopting repository, not this
uninstantiated distribution:

```text
.cambium/
  state/coverage_ledger.yaml
  state/required_queue.yaml
  state/progress_ledger.yaml
  work_specs/<batch-id>.yaml
  deltas/<batch-id>.yaml
  deltas/standards-adoptions/<adoption-id>.yaml
  receipts/*.jsonl
  reports/required_queue.md
  tmp/
```

The normal control sequence is:

1. At the start of every task, test whether `.cambium/` exists. If it does, run
   `check_queue.py . --resume-status` before any state/content write and resume
   only by following its `next_action` after reconciling the recorded task,
   checkpoint binding, task receipt, lifecycle groups, pending controls/deltas,
   completion semantics and its applicable completion block, holds, and locks.
   Never initialize over it. A new task requires the
   old task to be explicitly completed/cancelled and later archived or rolled
   over; current tools do not automate rollover.
2. Only when `.cambium/` is absent, and only for a selected persistent,
   resumable, or multi-batch route, run `init_state.py --apply` after profile
   adoption, a successful `profile-load` of that candidate Profile, and task
   definition. Declare exactly one
   `--completion-semantics build|maintenance`; the tool has no default.
   Bounded work does not create an empty runtime.
   It creates empty state, so `check_queue.py` returns 2 until Required work is
   materialized; that is an honest pre-execution hold, not successful admission.
3. Inventory every in-scope object in Coverage. Required objects explicitly
   project `batch` / `next_batch`; top-level `batch_specs` declares each
   proposed batch's family, order hint, mode, confirmation flag, and explicit
   dependencies. It also declares `work_spec_path` and `work_spec_sha256`:
   null/null for a simple batch, or the exact path and SHA-256 of one restricted-YAML
   contract directly under `.cambium/work_specs/` for a complex batch. The
   Work Spec uses `schemas/batch_work_spec.template.yaml`; its closed field
   sets carry only that batch's outcomes, ordered instruction DAG, observable
   acceptance conditions, and constraints. Every target is either the batch
   or exact Queue-manifest paths; unfilled sentinels fail validation.
   Queue order, lifecycle, holds, revisions, and receipts stay in Queue. This
   keeps a closed batch and a different successor from sharing one accidental
   configuration.
   For maintenance, also freeze the complete fused candidate list into
   Coverage `maintenance_candidates` before initial Queue materialization:
   selected candidates alone become Required batch manifests, while deferred
   candidates remain recorded outside current Queue work. A later run must
   retain the prior gate and its consuming task-completion receipt so deferral
   age and explicit re-entry can be checked.
4. Run `compile_queue.py` as a deterministic proposal. Only the integrator may
   apply an initial empty-to-materialized Queue, and must supply the current
   Queue revision and SHA-256. That first write records one immutable
   `initial_queue_receipt` in Progress so restart can bind the structure to its
   recorded origin. For a non-empty Queue, copy Coverage to
   `.cambium/deltas/replans/<amendment>.coverage.yaml` and edit only
   `batch_specs` plus Required pages' `batch`/`next_batch`. The canonical
   Coverage file remains unchanged while the diff is reviewed. A same-scope
   `--apply-replan` requires that proposal, exact Coverage/Queue/Progress SHAs,
   current Queue/state revisions, integrator role, and a pending approved
   Amendment first written by `register_amendment.py`, whose current receipt
   binds the proposal path/SHA, affected pages/batches, exact diff, and live
   three-state fingerprints.
   It then publishes all three canonical files under the shared lock and marks
   the Amendment verified. Closed/cancelled history is preserved exactly and
   in-flight structure cannot change.
5. Before activation, resume, or completion entry, compare the active K00/03
   Standards/Profile identity with the Task Contract and all three state
   objects. On mismatch, consume the R09-authorized restricted-YAML plan under
   `.cambium/deltas/standards-adoptions/` and dry-run
   `adopt_standards.py`. A stale `completion-candidate` first transitions
   legally to `paused` or `active`, and incompatible bound Work Specs are
   upgraded before this step. Formally roll back affected `merge-ready`
   batches and place affected `open` batches under `revalidation-required`;
   the writer verifies but never performs those lifecycle/hold changes. The
   plan binds approved K00/03 bytes and deterministic after Kernel/Profile
   snapshots. Plan admission runs the full typed `profile-load` closure against
   `selected_profile_manifest_after`; this after-image requirement is not
   relaxed merely because the current Profile is invalid. Full `profile-load`
   is also the default lower-level runtime invariant for every ordinary reader
   and writer. Only `adopt_standards.py` may explicitly request the smaller
   identity/sentinel guard for its persisted current/before read, so the sole
   corrective path can replace a broken closure; that capability is rejected
   for state overrides, pending receipts, candidate after images, and
   post-write state. Only the integrator applies the plan. The writer
   preserves that Task state and every batch lifecycle/hold, increments
   `queue_revision` once, appends transaction/history, and leaves historical
   receipt bytes identical and filters declared invalidated-evidence receipt IDs from current-use
   gate/reuse catalogs without erasing producer-era history. It generates and consumes the sole immediate
   Queue-consistency gate before commit. Predicate-selected batch-close or
   Terminal gates remain deferred to their named boundaries; they do not block
   unrelated earlier work. Do not create a Markdown adoption-status copy.
6. Run `check_queue.py`; activate one ready item with `update_queue.py`.
   The first activation alone records `planned -> active`; do not call
   `update_task.py` to bypass an unmaterialized or unopened Queue. Pause, block, or
   resume the whole task with `update_task.py`; Queue and canonical delta writes
   are rejected until task state is `active`.
   When confirmation is required, supply the same confirmation receipt to
   `check_queue.py --require-ready ... --confirmation-receipt ...` and the
   subsequent `update_queue.py` activation; the ready receipt binds it.
   Workers change only manifest objects, their receipt area, and
   `.cambium/deltas/<batch-id>.yaml`. The integrator alone changes canonical
   state and serially applies deltas. `apply_delta.py --root` applies only
   worker-owned status/evidence fields; `update_queue.py` performs lifecycle
   transitions and the close-time Coverage projection. After interruption,
   follow the reported `admit-delta`, `apply-delta`,
   `run-batch-close-gate`, or fully receipt-qualified `close-applied-batch`
   phase instead of redoing a completed phase. A passed
   canonical apply opens a strict apply-to-close interval: until that receipt
   is consumed by closing the same batch, every other Queue/Coverage write is
   rejected. Run `check_batch_close.py` in that interval. It prints
   `delta_apply_receipt`, `queue_consistency_receipt`, and
   `close_gate_receipt`, plus a complete `update_queue.py` close command. If
   that stdout is lost after publication, `check_queue.py --resume-status`
   reconstructs the same command from the complete receipt catalog and the
   current state/snapshot. It selects the latest current-compatible bundle by
   `checked_at`, then receipt ID; stale, structurally invalid, internally
   conflicting, or snapshot-mismatched bundles remain visible but are never
   selected. Without such a bundle, resume requires
   `run-batch-close-gate:<id>` and never treats an apply receipt alone as close
   authority. An unresolved writer lock instead requires
   `reconcile-interrupted-write` before either path. If it reports candidates,
   an independent reviewer must inspect the concrete
   list and rerun with each stable `--accept-candidate-id` or the exact
   `--accept-candidate-type tool:check`; an unused or overly generic selector
   fails. The tool reads K12/09 item 6 from the selected profile's Registered
   Scan Registry and executes only a repository-contained `Tools/*.py`
   command without a shell, with the 60-second limit. Do not hand-author the
   seven member receipts, review receipt, Queue receipt, or aggregator.
7. A scope/disposition change is not an ordinary Queue transition. Prepare one
   complete proposed Coverage document and its exact `amendment_plan`, register
   the approved decision with `register_amendment.py`, then pass that exact
   plan to `apply_amendment.py`. This is the sole
   cancellation entry and the scope-changing replan entry. It updates Coverage,
   Queue, and Progress under one shared lock while honestly retaining
   per-file atomicity and interruption evidence rather than claiming a
   multi-file atomic filesystem operation.
8. Preserve closed/cancelled history, then follow the frozen completion
   semantics. For `build`, run `check_queue.py --require-complete`, consume its
   receipt to enter `completion-candidate`, rerun the same Queue gate against
   the post-transition Progress bytes, produce Terminal Proof with
   `check_proof.py`, and consume that pass receipt to enter `complete`. For
   `maintenance`, do not enter `completion-candidate` and do not run
   `check_proof.py`. Instead run:

   ```text
   python3 Tools/check_queue.py . --require-maintenance-complete \
     --budget-manifest-receipt RECEIPT \
     --ledger-advance-receipt RECEIPT \
     --watermark-advance-receipt RECEIPT \
     --receipts .cambium/receipts/maintenance-completion.jsonl
   ```

   This gate requires a nonempty Queue with zero remaining work, reconciled
   controls, terminal batch history, persisted applicable batch/close gates,
   an exact schema-v2 candidate partition equal across the manifest, Coverage,
   and Queue, a valid prior-run age/re-entry chain, and three current compatible
   maintenance receipts. If matching completed maintenance history exists, the
   latest canonically consumed gate is the mandatory predecessor; `null` or an
   older eligible gate cannot reset candidate age. Consume its pass receipt
   through the `--maintenance-completion-receipt` argument of an
   `update_task.py --transition complete` call (plus the ordinary expected-SHA,
   actor-role, checkpoint, and `--apply` arguments). Both `planned` and
   `active` may enter their applicable completion path: this prevents a planned Queue whose
   batches were all validly cancelled by Amendment from deadlocking before any
   batch opened. A maintenance gate that passed before an interruption remains
   consumable only while its bound Coverage, Queue, Progress, revisions, and
   evidence receipts are still current. Zero remaining work is required in
   either mode, but an empty Queue file is not.
9. `render_queue.py` may refresh the human report. The report is never an input
   to a checker, compiler, transition, or Terminal Proof.

Queue tools constrain their writable outputs to the matching managed
subdirectory: receipts cannot overwrite state, reports cannot overwrite Queue,
and compiler proposals can only be written under `.cambium/tmp/`. A symlink or
hard link cannot alias authority, and a symlink or `..` path cannot escape or
cross those boundaries. Structure and lifecycle writers share one fail-closed
lock under `.cambium/tmp/`. A lock is evidence of either a live writer or a
possible interrupted write, not disposable clutter: before removal, establish
that no writer remains and reconcile all state files, revisions/fingerprint,
receipts,
pending deltas, and recorded delta-archive moves. Receipt JSONL is append-only:
writers never restore an old file image over concurrent appends. A fully
reconciled handled abort may close its lock; a partial or uncertain append
retains it.

## Kernel module and route identity

`Kxx` and `Rxx` are separate namespaces. `Kxx` names a normative Standards
module; `Rxx` names an execution route. A route may compile several modules,
and no numeric correspondence between a route and its source modules is
implied.

Kernel routes are the continuous closed set R01-R13. The Read Set Index has
`type: route-index`, the Card Index has `type: card-index`, and both declare
`registry_id: kernel-runtime-routes` plus a `route_registry`. An index is not a
route and therefore declares neither `route_id` nor the retired `card_id`.
Every concrete Read Set declares `type: read-set` and one `route_id`; its
Runtime Card declares `type: runtime-card`, the same `route_id`, and the Read
Set path. R05 is a normal required member of the sequence, not an optional
profile gap.

Legacy `card_id` / `card_registry` fields and duplicate identity keys are
structural failures, including inside registry entries. The scan includes
case-variant Markdown suffixes and Markdown symlinks so route files cannot be
hidden from the four-way comparison by naming or link indirection.

`stamp_cards.py` compares four representations before it considers hashes:
the Read Set Index registry, the Read Set files on disk, the Card Index
registry, and the Runtime Card files on disk. All four must have the same thirteen
route IDs and the same route-to-Read-Set bindings, and each concrete filename
must start with its `route_id`. A structural mismatch exits 1; a structurally
valid but stale Card layer exits 2 in `--check` mode; only exact agreement and
current hashes and agreement with K00/03 active `standards_version` exits 0.

It also compares each layer command against the tool that command names. A code
span whose first token is `python3` is the copy-and-run form an agent types
verbatim, so the named script must exist and must receive every required
positional and required option it declares. Each contract is read statically
from the tool's own source, so no argument list is duplicated in `stamp_cards`
and the tool stays the sole owner of its interface. A span that only names a
tool or a flag in prose is a reference, not a command, and is not scanned.

Two further checks read their rule out of the kernel pages that own it:
`Card And Read Set Skeleton` in `kernel/K00 Standards Control/14 Card And Read
Set Skeleton.md`, and `Read Set Loading Boundaries` in `kernel/K00 Standards
Control/15 Read Set Loading Boundaries.md`. Every Runtime Card and kernel Read
Set must carry exactly the H2
sequence registered for it there — the default sequence, or the variant
registered under its route ID — so a new section name is created by registering
it in the same governance change, never by editing the artifact alone. And
every kernel leaf module must be named by some Read Set loading boundary, which
is every Read Set section other than `Purpose` and `Related`; a leaf no boundary
names cannot be reached by any routed task. Both fail closed: a missing or
unparseable owner section exits 1 rather than skipping the check. No section
name, route shape, or leaf path is restated in tool code.

A fourth check measures the leaf module size budget. `kernel/K00 Standards
Control/03 Standards Governance.md` states the target and the soft cap, and
`kernel/K00 Standards Control/16 Leaf Module Size Register.md` carries the
approved exceptions; both numbers and every registered cap are read from those
pages rather than restated in tool code. Exceeding a registered cap is an
error. Standing over the soft cap with no registered exception, and a
registered measured value that no longer matches the file, are candidates,
because the owner calls that value a soft cap and asks only for a re-measure.

Uniform Cards carrying an older version are still stale. Its successful
summary reports routes, Read Sets, Runtime Cards, indexes, and stale artifacts
separately.

## Canonical full-tree configuration

The full-tree link check for this repository is `python3 Tools/check_links.py
.`, with no exclusions: every file in the published tree is active and is
audited. `--exclude` remains available for a vault that carries an unaudited
area -- byte-verbatim frozen snapshots are the usual case -- and explicit
full-path links from active files into such an area still resolve, counted
separately as `excluded_target`. Because the path is explicit, that exact
excluded target takes precedence over an active page that merely has the same
basename; excluded targets are not inspected for headings or lifecycle state.

The focused standard-library regression suite is:

```text
python3 -m unittest discover -s Tools/tests -p 'test_*.py'
```

The full-tree duplicate check is `python3 Tools/duplicate_check.py . --exclude
_template --exclude Cards`. `profiles/_template/` deliberately repeats form
labels and unfilled sentinels, while `kernel/Cards/` deliberately compresses
kernel source rules. Both therefore create expected textual similarity and are
outside a knowledge-corpus duplication review. Excluding `_template` does not
weaken the check for real profiles -- a profile copied from the template lives
under its own directory name and is scanned normally. Excluding `Cards` does
not skip the canonical rule text, which remains under the rest of `kernel/`.

## Invocation split

- **Batch close** = `check_batch_close.py` executes the Batch-close Closed List
  (owner: K12/09; including full-vault `check_links`, `check_vocab`, and the
  selected profile's registered residual-content verifier). The integrator
  separately consumes the single K13/08 Queue gate before recording
  `merge-ready -> closed`; it is not an eighth content check. A successful
  consistency receipt records `repository_snapshot_sha256`, computed over
  every current regular file except the root `.git/` and `.cambium/`
  namespaces. All seven receipts, the independent global review, and the
  explicit independent-review attestation, global review, and close
  aggregator bind that value as `merged_snapshot_sha256`;
  `update_queue.py` recomputes it before and under the write lock, so receipt
  strings whose required labels or bindings are absent, stale, or inconsistent
  with current content are rejected. This is a local consistency property, not
  authentication of the tool, actor, or reviewer that produced the records.
  Item 2 checks
  all Markdown structure/frontmatter but applies Cambium's restricted YAML
  grammar only to Cambium-owned machine YAML (kernel, selected profile, and
  composed `Tools/vocab.yaml`); unrelated application YAML in the adopter's
  Git repository is outside that contract. Canonical `.cambium` YAML is
  independently parsed by `check_queue.py`. Batch close asks
  `profile_contract.py` to authorize and compile the Registered Scan row; the
  invoked residual scanner itself remains Profile-blind and receives only its
  explicit command arguments. The bundled scanner requires a Profile-owned
  config, while the typed registry also permits a custom verifier with no
  `--config` argument.
- **Persistent task / multi-batch control** = `check_queue.py --resume-status`
  at every restart or new-Agent entry when `.cambium/` exists, then the Queue
  gate at admission, activation, batch close, and the selected build or
  maintenance completion path. `init_state.py`,
  `compile_queue.py`, and `update_queue.py` write only through their explicit
  dry-run/apply boundary; a bounded single-note task does not create an empty
  Queue merely to satisfy this route.
- **Active-task Standards adoption** = K12/10 validates one restricted-YAML
  changed-predicate plan; `adopt_standards.py` is the only writer of the three
  synchronized runtime identities and Progress Contract/load set. R09 creates
  the governance input and confirms Work Spec compatibility, while R07 applies
  or recovers the transaction. The selected Profile after-image must pass
  `profile-load` before the transaction can write. Its admission boundary is
  not batch-scoped and is not added to the batch rerun union; other changed-
  predicate gates are still enforced at their declared batch or Terminal
  boundaries. Queue consistency is immediate. The plan and
  append-only receipts are the Agent interface; no persistent prose projection
  is part of the protocol.
- **Corpus Planning** = `check_corpus_plan.py` validates the selected Profile's
  configured restricted-YAML Global Map, Capability Matrix, and Gap Register
  against their explicit IDs, paths, relations, scale, evidence, and Coverage
  handoffs. `record_corpus_acceptance.py` separately records the Profile-bound
  authority's ordered Capability decisions from a restricted-YAML plan into
  append-only JSONL receipts. Agents consume the normalized current state on
  demand with `--json`; no persistent planning report duplicates the three
  canonical artifacts.
- **Note close** = `check_links.py` / `check_vocab.py` with `--scope` set to
  the page itself (self-check; no receipts produced). Both tools fail on an
  empty scan set, so a mistyped page path cannot pass silently.
- **Maintenance run** = `check_freshness.py` (once at the start of the run)
  plus `duplicate_check.py` (full vault or `--scope`; candidates go into the
  candidates pool). Neither is invoked at batch or single-page level. A
  bounded single-note run does not acquire `.cambium/` merely for maintenance
  bookkeeping. A persistent, resumable, or multi-batch R10 run initializes
  with `--completion-semantics maintenance` and closes through
  `check_queue.py --require-maintenance-complete`, never R08 or Terminal Proof.
- **Governance** = `stamp_cards.py . --check`, `check_moc.py`, and the
  `check_profile.py` 1.9.0 `profile-load` Gate against each filled profile a
  deployment selects.
  `check_moc.py` is a pure diagnostic: it carries no Gate ID, has no row in
  the K00/12 Control Registry, is not a member of the K12/09 Batch-close
  Closed List, and is not one of the four `source_kinds` a maintenance run
  fuses. Its receipts are candidates for the governance or maintenance
  operator to read; no gate consumes them and finding a candidate creates no
  automatic obligation. K12/05 is the kernel statement of that boundary. The
  published `_template` is a form, not a runnable profile.
  `compose_vocab.py --check` joins that list in a vault that has composed a
  vocabulary. This repository ships no composed `vocab.yaml`, so here the
  command reports that no profile is selected and exits 1; see Generated
  artifacts below.
- **Profile bring-up** = scaffold a candidate with `scaffold_profile.py`
  (whitelist copy of `profiles/_template/` plus mechanical derivation; manual
  whitelist copy is the no-agent fallback), fill the candidate through the
  interview contract or by hand, then run `check_profile.py --root .` against
  it before loading it.
  A successful pass binds both the selected Profile tree snapshot and the
  typed dependency graph fingerprint; no partial contract emits the pass
  summary. The form
  itself is not a runtime target. Profile bring-up is not part of batch or note
  close because a profile is authored once and then loaded, not edited per
  batch. `check_profile.py` validates
  authority, self-path closure, structure, and bindings but does not ask
  questions, generate domain choices, author a profile, approve it, judge the
  quality of its answers, or select it; the scaffolder likewise creates only
  an unadopted candidate.

Shared conventions:

- Human-readable summaries go to stdout; machine-readable receipts are
  appended as JSONL via `--receipts PATH`.
- Two receipt destinations exist and they are not interchangeable. The runtime
  receipt register is `.cambium/receipts/**/*.jsonl` and nothing else: every
  tool that reads evidence by receipt ID -- `check_queue.py`,
  `check_batch_close.py`, `check_proof.py`, `update_queue.py`,
  `update_task.py`, `adopt_standards.py`, `apply_amendment.py`,
  `register_amendment.py` -- builds its catalog by walking that one directory,
  so a receipt written anywhere else can never be consumed by ID, by a gate,
  or by Coverage `gate_receipts`. Tools whose receipts are gate evidence
  therefore default `--receipts` into that namespace, and `kblib` rejects a
  `.cambium` path that is not `.cambium/receipts/**/*.jsonl`. The
  `Tools/receipts/...` paths in the invocation column above are the other
  case: a standalone diagnostic run outside any Cambium runtime, where the
  receipt is a local artifact for the operator to read. `LICENSE.md` treats
  that directory as adopter-generated output. Pass an explicit
  `.cambium/receipts/<name>.jsonl` whenever the run is meant to become
  evidence.
- Exit codes: `0` = clean success; `1` = failure or unreliable evidence;
  `2` = reliable but non-clean outcome as defined by that tool. Receipt-based
  candidate checks use 2 for one or more candidates; `stamp_cards.py` uses it
  for stale artifacts, `compose_vocab.py` uses it for a check mismatch, and
  `check_queue.py` uses it for a valid but empty/held/dependency-blocked state
  or a reliable resume hold such as in-flight work or writer-lock evidence.
- `check_residual_content.py` requires the profile's stable `--scan-id` and a
  profile-owned `--config`. Every emitted receipt includes that `scan_id` and
  the exact config-byte `config_fingerprint`; an unreadable or invalid config
  records a null fingerprint and exits 1.
- A scan registered by a profile is run only by a vault that loads that
  profile. Content matches may only produce review candidates; the final
  verdict belongs to scoped human/model review. Invalid configuration,
  incomplete scope, unsafe paths, read errors, or execution failure still
  return 1 because the scan did not produce reliable evidence.

## Receipts flow (K12/07 Audit Evidence Reuse and Invalidation)

```text
script run with --receipts creates the requested parent directory and produces JSONL receipts
  (receipt_id: audit-<tool>-<timestamp>-<run-token>-<seq>)
 -> receipts enter the Audit Receipt Register / Batch Contract; the Coverage
    Ledger's pages[].gate_receipts records only the latest valid receipt_id
 -> before batch close, generate one AuditPlan (schemas/audit_plan.template.yaml):
    freeze the snapshot, diff changed_objects, resolve direct/dependency invalidation
 -> old receipts passing the Reuse Gate go into reused_receipts (a reuse reason
    is mandatory); receipts affected by changes go into invalidated_receipts;
    new results supersede old receipts
 -> the Terminal Audit runs the Batch-close Closed List against the final frozen
    snapshot (K12/09); the result-set reference goes into the Terminal Proof's
    full_deterministic_results; unresolved_invalidations must be 0
```

The random run token prevents same-second invocations from reusing an ID.
Previously issued receipt IDs remain immutable identifiers and are not renamed
when the generator format changes. Their evidence-reuse validity may still be
revoked by the normal invalidation rules.

Script receipts are the lightweight layer (fields in
`schemas/receipt.template.jsonl`); on entering the Register, the AuditPlan
layer completes the full AuditReceipt fields per K12/07 (scope /
acceptance_predicate / fingerprints), with the script receipt_id serving as
evidence_ref. Tool-specific optional fields may bind the receipt more tightly
to its invocation contract; the residual scanner uses `scan_id` and
`config_fingerprint` so a registry or config change cannot reuse stale scan
evidence silently.

## schemas/ templates (the template is the schema doc)

- `coverage_ledger.template.yaml` -- object-level Coverage Ledger (owner:
  K02/01); includes disposition, canonical owner, object-side batch projection,
  and top-level `batch_specs` as explicit Queue-compiler proposal inputs,
  including the null/null or path/SHA Work Spec binding
- `required_queue.template.yaml` -- batch/work-unit contract and lifecycle
  (owner: K13/08); its explicit manifests reconcile bidirectionally with
  Coverage and each item preserves its compiled Work Spec binding
- `batch_work_spec.template.yaml` -- immutable Agent-readable contract for one
  declared complex batch under `.cambium/work_specs/`; the whole restricted-
  YAML document has a closed top-level and record grammar, binds the exact
  batch ID and ordered Queue manifest, requires nonempty outcomes,
  instructions, acceptance conditions, and constraints, and rejects unfilled
  sentinels or Queue-owned state at any nesting depth
- `global_map.template.yaml` -- closed restricted-YAML K02 Corpus Planning
  contract for canonical entries and typed dependencies; entry Layer IDs
  resolve against the selected Profile Scope's logical-layer table rather than
  restating that table
- `capability_matrix.template.yaml` -- closed restricted-YAML K02 Corpus
  Planning contract for testable capabilities, Matrix priority, canonical
  paths, current/target scale values, evidence, and Gap IDs
- `gap_register.template.yaml` -- closed restricted-YAML K02 Corpus Planning
  contract for stable semantic-gap history, bidirectional capability links,
  candidate ownership, close conditions, evidence, and promoted Coverage paths
- `corpus_plan_acceptance.template.yaml` -- closed restricted-YAML authority
  decision plan: exact Profile-bound role/scope plus one ordered
  accepted/rejected decision and rationale for every current Capability ID;
  consumed only by `record_corpus_acceptance.py`, never as canonical state
- `progress_ledger.template.yaml` -- task-level Progress Ledger (owner: K13/07);
  stores the Task Contract and accepted Queue path/revisions/fingerprint, not a
  second batch list; the contract declares `completion_semantics`, and the
  mutually exclusive `terminal_audit` / `maintenance_completion` blocks keep
  the non-applicable path inert. Its empty route/load lists are deliberately
  uninstantiated: a materialized contract records the complete transitive Read
  Set closure and every ordinary module target, never a partial example
- `maintenance_budget_manifest.template.yaml` -- the closed budget-envelope
  manifest consumed by the maintenance completion gate; schema v2 records one
  fused record per candidate object, the exact selected/deferred ID partition,
  prior/current deferral age, re-entry and disposition, while Coverage keeps
  the matching canonical candidate state. Deferred work outside the envelope
  does not become current Required work. A `pages` budget counts
  `selected_objects`, a `batches` budget counts `required_batch_ids`, and an
  `hours` budget requires `consumed_hours >= 0` and no greater than
  `budget_limit`; `consumed_hours` is null for the other two axes
- `amendment_plan.template.yaml` -- cross-Ledger scope/disposition transaction
  input first fixed by `register_amendment.py` and then consumed by
  `apply_amendment.py`; binds one approved decision, a complete Coverage
  proposal, exact revision edges, and its proposal SHA
- `receipt.template.jsonl` -- script-level receipt (concept owner: K12/07),
  including the optional `scan_id` and `config_fingerprint` extension fields
  used by the residual scanner plus the manifest, Profile-tree snapshot, and
  typed contract fingerprint bound by a `profile-load` pass
- `coverage_delta.template.yaml` -- state increment of a concurrent batch
  (owner: K13/10 Concurrent Batches; applied by the integrator during the
  serial merge; includes the `watermark_advance` pass-through field)
- `watermark.template.yaml` -- external scan watermark (owner: K06/07
  Environmental Scanning and Watermark; consumed by the K06/03 intake
  pipeline; the instance lives at Tools/state/watermark.yaml and is advanced
  by maintenance batches). `last_run_id` binds the enclosing maintenance run;
  `last_batch_id` separately records the Queue batch that performed the final
  advance
- `audit_plan.template.yaml` -- AuditPlan (owner: K12/07 Incremental Audit Planning)
- `terminal_proof.template.yaml` -- machine-readable Terminal Proof projection;
  its fields copy K12/16 field by field, including current Queue completion
  evidence; `check_proof.py` reads the projection while K12/16 remains the
  normative field-list owner; it applies only to `build` completion semantics
  and copies the already-validated route/load lists from the frozen live Task
  Contract rather than reconstructing or minimizing them
- `execution_defaults.template.yaml` -- executor-side placeholder
  configuration for the shipped `profiles/_template/` form: the reserved
  `profile_id` values and the unfilled sentinel, consumed by
  `check_profile.py`, `check_queue.py`, and `check_proof.py`. The closed
  membership registry of which kernel execution defaults a profile may
  override and which constants it may not is a rule carrier and lives at
  `kernel/K00 Standards Control/execution-defaults-base.yaml`; the file header
  here carries the block-by-block relocation table
- `standards_adoption_plan.template.yaml` -- the closed restricted-YAML
  changed-predicate plan consumed by `adopt_standards.py` (semantics owner:
  K12/10; transaction owner: K13/15); it binds approved K00/03 bytes, the
  deterministic after Kernel/Profile snapshots, Task/Contract identity, Queue
  revisions, all three state SHA-256 values, the changed predicates, the
  dimension- and boundary-specific invalidated evidence, and the immediate
  versus deferred gate split. The selected Profile after-image must pass
  `profile-load`; a `profile-load` boundary targets exactly that manifest and
  is admission-only rather than batch-scoped. Its empty after-load lists are
  placeholders; a real plan supplies the complete derived Read Set/module
  closure
- `profile_adoption_plan.template.yaml` -- the closed restricted-YAML plan
  consumed by `apply_profile_adoption.py`, the no-runtime sibling of the
  active-task adoption plan above (rule owner: K00/03; R09 both branches).
  It declares the branch (`initial-adoption` or `profile-revision`), the
  four K00/03 after values, the Change Summary row content, an empty
  `changed_predicates` list (a nonempty list belongs to
  `adopt_standards.py`), and the compare-and-swap fingerprints: exact
  current K00/03 bytes plus the candidate Profile's `profile-load` tree
  snapshot, typed contract fingerprint, and root-input fingerprint. Its
  `TODO(profile-adoption)` sentinels must all be replaced
- `task_plan.template.yaml` -- the closed restricted-YAML initial task plan
  consumed by `apply_task_plan.py` (transaction owner: K13/18). It supplies the
  complete Task Contract and the complete initial Coverage inventory plus
  `batch_specs`, and a `before` compare-and-swap over all three state files. It
  carries no Required Queue body: the Queue is compiled from `coverage_after` by
  the compiler that owns it, and a Queue written here would be a second
  authority. Its `TODO(plan)` sentinels must all be replaced; the transaction
  refuses a plan that still carries one
- `contract_amendment.template.yaml` -- the closed restricted-YAML Contract
  Amendment plan consumed by `apply_contract_amendment.py` (transaction owner:
  K13/06; field owner: K13/02). It carries the complete `policy_exceptions`
  after-image, never a diff, and a `before` compare-and-swap over all three
  state files; its `TODO(amendment)` sentinels must all be replaced
- `residual_scan_config.template.yaml` -- machine-parameter form for
  `check_residual_content.py`; a selected profile owns its filled copy while
  its Registered Scan Registry remains the owner of scan identity, invocation,
  candidate semantics, and Judgment Item binding. This config is mandatory for
  the bundled residual scanner; a different registered verifier may have no
  config argument, subject to the same typed contract authorization

## Restricted YAML subset

All `.yaml` state files may only use what `kblib.parse_yaml_subset` accepts:

- `key: value` scalars: strings (optionally quoted), integers, floats,
  booleans, null, the inline empty list `[]`, and simple inline lists
  `[a, b]`;
- `- item` lists indented under `key:`; list items may be a one-level flat
  map;
- two-level indented nested maps (the parser is recursive, but the standards
  convention uses two levels only);
- `#` comments (a `#` inside quotes is not a comment).

Not supported: duplicate mapping keys, anchors/aliases, block scalars (`|`
`>`), flow maps `{}`, tags, multi-document streams, tab indentation.
Duplicate keys at the same mapping level and all unsupported declarations fail
closed; the parser never applies last-value-wins semantics.

## Generated artifacts

`compiled/cli-contract.yaml` is a **generated artifact**, produced by
`compile_cli_contract.py` from the `argparse` declaration every `Tools/*.py`
CLI builds for itself. It is the machine-readable statement of how these
tools are called: per argument the `option_strings` (empty exactly for a
positional), `dest`, `required`, evaluated `default`, `choices`, `nargs`,
`action`, `type` name and `help`, plus each mutually exclusive group and the
receipt extension fields derived from that tool's own source. `choices` is
recorded as a canonically ordered set, because several tools build it from a
Python set whose iteration order is not stable between processes. Do not edit
it by hand; regenerate with `python3 Tools/compile_cli_contract.py .` and
verify with `python3 Tools/compile_cli_contract.py . --check`, which `make
check` runs. It carries no Gate ID: it depends on no selected profile, and
`run_gates` cannot start before a profile is selected.

`compiled/mcp-tools.json` is a **generated artifact**, produced by
`render_interface_projection.py` from `compiled/cli-contract.yaml`. It is the
same interface statement in the shape a Model Context Protocol runtime reads:
per tool a `name`, the tool's own argparse `description`, and an `inputSchema`
whose properties are keyed by `dest`. The mapping is mechanical -- an
undeclared argparse `type` projects as `string`, which is what argv carries;
`choices` becomes `enum`; the arguments argparse marks required become the
`required` array; an argument with empty `option_strings` is the positional,
which is the upstream artifact's own stated rule. `additionalProperties` is
`false` because argparse rejects an option it did not declare. Two transports
are declared, `stdio` and `streamable-http`; there is no `sse` and no
`websocket` branch, and their absence is structural rather than a key marking
them unsupported. Values the compiled contract carries but JSON Schema has no
place for -- the exact option spellings, the argparse action and `nargs`, and
each mutually exclusive group -- travel verbatim under `x-cambium-cli` and
`x-cambium-mutually-exclusive` rather than being dropped or restated.

It is JSON, not the restricted YAML subset, because its payload already is
JSON Schema; serialization goes through `kblib.canonical_json_bytes`. It
carries `source_hash`, the sha256 of the exact `cli-contract.yaml` bytes it
was projected from, and `source_manifest_hash`, that contract's own
fingerprint of the tool sources behind it. Every form binds that same
upstream, so one upstream change invalidates all of them at once and no two
generated forms are ever compared with each other. Do not edit it by hand,
and do not treat it as the basis for revising a tool: it is downstream of each
tool's argparse block, so a change starts there, then
`python3 Tools/compile_cli_contract.py .`, then
`python3 Tools/render_interface_projection.py .`. Verify with
`python3 Tools/render_interface_projection.py . --check`, which `make check`
runs directly after its upstream; like that upstream it carries no Gate ID,
because it depends on no selected profile.

`compiled/host-configs/` holds five **generated artifacts**, produced by
`render_host_configs.py` from one MCP server definition body declared in that
tool. They answer a different question from the two artifacts above: not what
the server offers, but where it is, how it starts, and which corpus it
governs.

Registration and binding are two things. *Registration* -- `command`, `args`,
`cwd`, and dsh's connection-resilience block -- says where the server is and
how to start it, and is installed once per machine. *Binding* -- the
`CAMBIUM_WORKSPACE_ROOT` environment variable -- says which corpus this run
governs, and must be written once per corpus. Three of the four hosts write
both halves into one file, which makes the distinction easy to miss; `dsh`
separates them by force, its registration living in a profile under
`$DSH_HOME` and its binding in a `.env` beside the corpus. That separation is
why the tool models two halves and lets each host recombine them.
`CAMBIUM_WORKSPACE_ROOT` is the contract path for the binding: MCP's
2026-07-28 revision named server configuration as the migration direction when
it deprecated roots.

| Product | Copy to | Carries | Host |
|---|---|---|---|
| `claude-code.mcp.json` | `<corpus>/.mcp.json` | registration + binding | Claude Code |
| `kimi-code.mcp.json` | `<corpus>/.kimi-code/mcp.json` | registration + binding | Kimi Code |
| `codex.config.toml` | `<corpus>/.codex/config.toml` | registration + binding | Codex |
| `dsh.env` | `<corpus>/.env` | binding only | dsh |
| `dsh-profile-patch.yaml` | `$DSH_HOME/profiles/<name>/` | registration only | dsh |

**These are templates for an adopter's corpus repository, not files for this
one.** They are rendered under names that carry their destination, so no path
in this repository is one a host would load, and this distribution registers
no MCP server with itself. An adopter copies them, or an onboarding flow
renders a bound copy directly with `--distribution-root` and
`--workspace-root`, which substitute the two placeholders. A placeholder is
not a valid absolute path on any of these hosts, so an un-substituted copy
fails at launch rather than resolving to something.

Claude Code and Kimi Code are separate entries writing separate files even
though their JSON shapes agree today: one shared file would be a claim that
they will keep agreeing, and nothing in either host holds them to it. The
three fields `dsh` accepts and the others do not -- `toolCallTimeoutMs`,
`failOnStartupError`, `reconnect.*` -- are a superset, not a disagreement, so
the products that cannot carry them drop them rather than encoding a different
intent.

`cwd` is a fallback and nothing more. All four hosts start a stdio server in
the session's own working directory, and **none of their plugin-packaging
documentation mentions a `cwd` or an environment field at all**; what this
registration rests on is the absolute path inside `args`, and what binds the
server to a corpus is `CAMBIUM_WORKSPACE_ROOT`, never an inherited working
directory.

The server name is `cambium`, and the shape it must satisfy is the
*intersection* of the four hosts rather than the union: lowercase letters and
digits joined by single hyphens, no spaces, first and last character
alphanumeric, no consecutive hyphens, and inside `^[a-z0-9][a-z0-9_-]{0,63}$`.
The tool checks its own declared name against both and exits 1 if it fails, so
the constraint is executable rather than a remark. No skills ship with this
registration, and no `SKILL.md` may sit at the root of what is packaged: Kimi
Code reads such a root as a single-skill bundle and stops looking. That rule
is checked against the rendered tree and against every rendered document, not
merely written here.

### First contact is manual, in all three interactive hosts

Installing this configuration cannot be finished by a repository on its own
behalf, and that is the hosts' security model rather than a gap in this line:

- Claude Code asks a person to trust the workspace before it loads a
  project-level `.mcp.json`; a repository that was just cloned cannot approve
  itself.
- Codex reads a project-level `.codex/config.toml` only while the project is
  trusted, and only a person grants that trust.
- Kimi Code ships no non-interactive registration command at all; the entry
  point is `/mcp-config` inside its TUI.

Plan for one human step per host on first contact. An onboarding flow can
write the files; it cannot approve them.

Every product carries `CAMBIUM_INTERFACE_SOURCE_HASH`, the sha256 of the exact
`compiled/mcp-tools.json` bytes it was rendered against, in the environment
the server is launched with -- so a server can refuse a tool list it was not
registered against, and so one upstream change makes all five products stale
at once. It travels as an environment value rather than a comment because two
of the five formats are JSON, and a provenance field only three products could
carry would bind only three. JSON and YAML are serialized through the shared
`kblib` canonical renderers; TOML and dotenv have no `kblib` renderer to
share, so this tool carries small deterministic emitters for them and re-reads
every product through a parser for its own format before writing it.

The stdio entry point these products name, `Tools/mcp_server.py`, is not
shipped yet: what is rendered today is the registration shape for it, and the
tool says so on every run until that file exists. Do not edit these products
by hand; regenerate with `python3 Tools/render_host_configs.py .` and verify
with `python3 Tools/render_host_configs.py . --check`, which `make check` runs
directly after `render_interface_projection --check`. Like both upstreams they
carry no Gate ID, because they depend on no selected profile.

`vocab.yaml` is a **generated artifact**, produced by `compose_vocab.py` from
`kernel/K08 Metadata and Status/vocabulary-base.yaml` plus the
`vocabulary-extensions.yaml` of the profile selected by K00/03 active state.
The artifact header records compilation provenance and the sha256 of both
inputs; it never selects the active profile. The tool carries no default
profile of its own. Every run reads K00/03; an argument-free run derives the
extensions path from the selected manifest, and an explicit `--extensions`
must name that same bound file.

The composed contract has one declaration source for each identity.
`profile_id` and the slot binding are declared only in `profile.md`; kernel
base identity and composition policy come only from the base input; a
kernel-field `extension_owner` is derived from the bound extensions-file path.
Legacy duplicate declarations are rejected rather than silently treated as a
second source.

**This repository ships no composed `vocab.yaml`.** Committing one would write
instance-specific compiled values and provenance into the generic release,
even though its K00/03 active state intentionally selects no profile. What is
published here is a kernel base and an interface, not an adopter artifact.
Until a profile is selected and composed,
`compose_vocab.py --check` exits 1 and reports the selectable direct-child
profiles it can find. `check_vocab.py` exits 1 and points at the same step.
Both report the expected
not-yet-configured state of a repository with no selected profile; neither is
a defect in the blank form.

Compose the artifact once, against your own profile:

```text
python3 Tools/compose_vocab.py
```

This command succeeds only after K00/03 selects that profile. After that,
`compose_vocab.py` with no arguments recomposes from the active state, and
`compose_vocab.py --check` verifies that the artifact still matches the
currently selected profile rather than merely agreeing with its old header.

`stamp_cards.py` pre-renders and round-trips every frontmatter block before it
writes. An ordinary write error rolls back earlier writes in that invocation;
a hard process or device interruption is not a filesystem transaction, so the
next `--check` must still be used to detect and restamp any interrupted layer.

Runtime Cards differ from the composed vocabulary in one distribution detail:
they ship with `kernel/` because every task needs routing before a profile can
contribute domain values. They are still compiled artifacts. The normative
route list is the Read Set Index's `kernel-runtime-routes` registry; the Card
Index mirrors it, and each Read Set/Card pair shares one Rxx `route_id`.
Authoritative rule definitions live in each Card's `source_files`; after
revising an owner standard, regenerate and stamp every affected Card, never
edit only the Card, and never cite a Card as standards text when adjudicating a
conflict. A profile may add a supplemental route, but it cannot replace or
disable the kernel Card layer.


## Sealing maintenance window and recovery runbook

`seal_receipts.py --apply` is the only operation in this runtime that removes
bytes from a register. It is supported **only** inside a declared quiet window
with a single writer. The receipt append mutex guards the accident of running a
checker or writer beside a seal; it is not a concurrency protocol, and running a
seal against a live runtime is outside the supported boundary regardless of what
the mutex reports.

### Before `--apply`

1. Confirm no other Cambium or adopter process is running against the
   repository — no writer, no checker, no receipt appender, on any host or
   session.
2. `python3 Tools/check_queue.py . --resume-status` — the runtime must be clean,
   with no writer lock and no pending delta application.
3. `python3 Tools/seal_receipts.py .` (no `--apply`) — read the plan and confirm
   the register list and receipt counts are what you expect.
4. Take a restorable copy of `.cambium/` and record its hash. This is the
   fallback that makes every failure below recoverable by hand.

### After an interruption

An interrupted seal always fails later runs closed. Do not re-run `--apply`
blindly; the journal and pending record are the recovery evidence.

1. `python3 Tools/seal_receipts.py . --reconcile` — reports the unfinished seal,
   its pending record, and the row and rewrite counts still outstanding.
2. If the report is clean, `--reconcile --apply` finishes it. This covers the
   publication steps the tool itself performs.
3. `--reconcile` refuses, by design, when the writer lock's owner process is
   still running, when the pending record's bytes no longer match the hash the
   journal bound to it, or when the pending record is gone. Each refusal is a
   real condition, not a false alarm:
   - **owner still running** — a seal is in progress. Wait for it, or establish
     that the process is genuinely gone before doing anything else.
   - **pending drifted** — the recovery plan was edited after the transaction
     wrote it. Do not reconcile. Restore `.cambium/` from the pre-seal copy.
   - **pending missing** — the transaction's intent is unrecoverable. Restore
     `.cambium/` from the pre-seal copy.
4. For any interruption `--reconcile` does not cover, restore `.cambium/` from
   the pre-seal copy and re-run the whole sealing step in a fresh quiet window.
   Sealing is idempotent in effect: nothing sealable is lost by starting over
   from a verified pre-image.

### After `--apply`

1. `python3 Tools/seal_receipts.py . --verify` — every segment, projection and
   register binding is re-proved.
2. `python3 Tools/check_queue.py . --resume-status` — full runtime validation
   must be clean.
3. Only then release the maintenance window.
