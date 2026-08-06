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
`check_queue`, `check_batch_close`, `compile_queue`, `update_task`,
`update_queue`, `register_amendment`, `apply_amendment`, `adopt_standards`,
`render_queue`, `apply_delta`, `compose_vocab`, `check_profile`,
`check_residual_content`, `stamp_cards`, and `kblib`.
`check_freshness` and `duplicate_check` are maintenance-run tools.

## Tool inventory

| Script | Purpose | Typical invocation |
|---|---|---|
| `check_links.py` | Wiki link missing / ambiguous / heading verification (K09/03, K09/05); `--scope` accepts a directory or a single page; the effective scan set is checked after exclusions, and zero files fail for both scoped and whole-root runs; an exact full-path link into an excluded area resolves as `excluded_target` before any active basename fallback | `python3 Tools/check_links.py . --receipts Tools/receipts/links.jsonl` |
| `check_vocab.py` | Frontmatter controlled-vocabulary check (K08 module; vocabulary from the composed `vocab.yaml`, which exists only once a profile has been selected and composed -- without it the check reports that and exits 1); `--scope` accepts a directory or a single page; the post-exclusion effective scan set must be nonempty; `--quota-p0` / `--quota-p1` cap P0/P1 shares, defaults 15/35 (kernel defaults; a profile or task contract may override); compiled kernel Cards are outside the knowledge-page schema | `python3 Tools/check_vocab.py . --scope kernel --exclude kernel/Cards --quota-p0 15 --quota-p1 35 --receipts Tools/receipts/vocab.jsonl` |
| `check_moc.py` | Standard Module MOC Module Index vs. actual H2 headings consistency candidates (K12/05; **candidates only**); recursively scans every non-hidden directory unless the caller explicitly supplies `--exclude`, and is fence-aware (fenced code blocks ignored); maintenance runs and governance | `python3 Tools/check_moc.py .` |
| `check_proof.py` | Build Terminal Proof consistency check (K12/16): field completeness; canonical, non-symlinked Coverage/Progress/Queue state; exact candidate-state fingerprints, or after completion the same pre-complete Progress fingerprint bound through the latest task-transition receipt and its current after-image; task/scope/contract/Standards/profile agreement; no pending Guidance/Amendment; current Queue revisions, zero remaining work, live completion gate and Coverage gaps; selected profile loadability; required terminal R01/R12/R08 selection and exact R01-R13 route/Card/Read-Set registry agreement; passed reconciliation/QA/review results. It rejects a Progress contract whose `completion_semantics` is `maintenance`; without `--root`, it is structural lint only | `python3 Tools/check_proof.py .cambium/receipts/terminal-proof.yaml --root . --progress-ledger .cambium/state/progress_ledger.yaml --ledger .cambium/state/coverage_ledger.yaml --receipts .cambium/receipts/terminal.jsonl` |
| `check_corpus_plan.py` | Corpus Planning structural/reconciliation gate and Agent query interface: resolves the explicit or Progress-selected Profile; validates the three closed restricted-YAML planning contracts, explicit IDs/relations, Profile Scope, scale/evidence links, and Gap promotion handoff. Structural receipts carry Gate ID `corpus-plan-structure`. `--json` exposes `structural_reconciliation_valid` and the separately resolved `semantic_acceptance` status; it emits no ambiguous aggregate `valid` field and persists no report. The tool never infers relations or makes the semantic decision | `python3 Tools/check_corpus_plan.py . --json` |
| `record_corpus_acceptance.py` | Sole `corpus-plan-semantic-acceptance` producer. Consumes one closed restricted-YAML plan directly under `.cambium/deltas/corpus-plan-acceptances/`; requires every current Capability ID exactly once in Matrix order, the Profile-bound authority Role and decision scope, and explicit accepted/rejected decisions. Dry-run by default. `--apply` appends a fresh structural receipt and a distinct semantic JSONL receipt bound to the plan, Profile/slot/Scope, three planning artifacts, canonical runtime state, repository snapshot, authority, and exact decisions. It creates no Markdown projection | `python3 Tools/record_corpus_acceptance.py . --plan .cambium/deltas/corpus-plan-acceptances/CPA-001.yaml --actor-role <role-id> --apply` |
| `init_state.py` | Create an adopter's empty `.cambium/` namespace, including `work_specs/`, and the three canonical state files. Dry-run by default; `--apply` stages and reparses a complete tree before one atomic no-replace rename, requires the caller to choose `--completion-semantics build` or `maintenance`, records the task objective plus repeatable explicit exclusions alongside Standards/profile identity, and never invents Required work. Any pre-existing `.cambium/`—including an empty directory that wins a publication race—is preserved; the diagnostic directs the operator to `check_queue.py --resume-status` rather than overwriting it | `python3 Tools/init_state.py . --task-id TASK --objective "Concrete outcome" --exclude "Out-of-scope boundary" --completion-semantics build --scope-version s1 --standards-version VERSION --profile-manifest profiles/my-profile/profile.md --apply` |
| `check_queue.py` | Sole deterministic Required Queue gate (K13/08): validates schema, manifests, Coverage projection, dependencies, lifecycle/task receipts, holds, confirmations, hash-bound complex-batch Work Specs, deltas, concurrency, Progress revisions/fingerprint, paths, readiness, and terminal count. `--require-complete` is the build-closure Queue gate. `--require-maintenance-complete` additionally consumes current budget-manifest-closed, Coverage-ledger-advanced, and watermark-advanced receipts; reconciles the manifest's complete selected/deferred candidate partition with Coverage and the Queue manifest union; enforces consecutive-deferral disposition; and binds the maintenance pass to all three current state objects. `--resume-status` reports objective/exclusions, completion semantics, three live SHAs, checkpoint/task history, Work Spec bindings, maintenance candidate SHA/partition/prior gate, controls, the applicable completion block, locks, and an exact `next_action`. Valid interrupted delta phases become `admit-delta:<id>` or `apply-delta:<id>`; an applied batch without a current close bundle becomes `run-batch-close-gate:<id>`, while a recovered current bundle becomes `close-applied-batch:<id>:<queue-receipt>:<close-receipt>:<apply-receipt>` plus an exact copyable close command. A writer lock always takes recovery priority; inconsistent evidence becomes `repair-runtime` only when no interrupted writer must first be reconciled | `python3 Tools/check_queue.py . --resume-status` |
| `check_batch_close.py` | Sole supported producer contract for the K12/09 merged-snapshot close bundle (current receipt protocol 1.2.0). For one `merge-ready` batch with a current `apply_delta` receipt, it holds the shared runtime lock; recomputes real repository bytes before/after the seven checks and receipt publication; runs `check_links`, Cambium-owned YAML/Markdown structure, a deterministic in-memory Markdown/Wiki-link graph JSON projection plus basename candidates, Coverage file-count, guidance/contract continuity, the selected profile's registered residual verifier, and `check_vocab`; records an explicit reviewer attestation with a reviewer label different from the integrator label; creates the canonical `check_queue` consistency receipt through that checker's shared producer; and emits the exact three IDs consumed by close. Only protocol 1.2.0 can form a valid current execution chain; older receipt bytes may remain in the historical catalog but require an external migration adapter before the runtime can continue. Labels and attestations remain assertions under the Evidence trust boundary. Item 3 does not scan ordinary repository JSON or fenced JSON examples; item 1 alone owns missing/ambiguous/heading verdicts. Candidate prose alone is insufficient: every current candidate must be accepted by stable ID or exact `tool:check` type. A failed run emits only a failed attempt, while an uncertain append retains the lock | `python3 Tools/check_batch_close.py . --batch B1 --integrator alice --reviewer bob --review-attestation "Reviewed the exact listed candidates and merged snapshot."` |
| `compile_queue.py` | Deterministically compile Queue structure from explicit Required Coverage assignments plus top-level `batch_specs`; never infers semantic dependencies or backlinks. Every spec explicitly declares both Work Spec fields: null/null for a simple batch, or one exact `.cambium/work_specs/*.yaml` path/SHA pair for a complex batch. Initial `--apply` is integrator-only and writes the unique origin receipt into Progress. A same-scope replan consumes a complete `.cambium/deltas/replans/*.coverage.yaml` proposal—never pre-edited canonical Coverage—and a matching current registration written by `register_amendment.py`; it commits Coverage/Queue/Progress under one shared lock after exact three-file CAS, registration/Amendment/diff binding, and conflict checks. Terminal history remains immutable; interrupted/incompletely rolled-back writes retain the lock | `python3 Tools/compile_queue.py . --coverage-proposal .cambium/deltas/replans/A1.coverage.yaml --output .cambium/tmp/queue-replan.yaml` |
| `update_task.py` | Sole Progress task-state transition writer. Dry-run-first and integrator-only; compare-and-swaps current Progress and Queue SHAs under the shared lock, records a transition receipt and restart checkpoint, and requires a reason for pause/block. A build task consumes a current Queue-complete receipt to enter `completion-candidate`, then a canonical `check_proof` pass receipt to enter `complete`. A maintenance task never enters `completion-candidate`; its `planned` or `active` state enters `complete` only by consuming a current `check_queue --require-maintenance-complete` receipt through `--maintenance-completion-receipt`. Direct `planned -> active` remains rejected; `update_queue.py` invokes that owner only while opening the first batch | `python3 Tools/update_task.py . --transition paused --checkpoint-summary "waiting for source" --expected-progress-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `update_queue.py` | Dry-run-first, integrator-only lifecycle/hold transition with legal-state enforcement, current contract-conformant gate/confirmation/batch receipts, exact managed delta validation and frozen SHA, optimistic revision/SHA checks, the shared writer lock, rollback, result-state revalidation, and before/after receipt history. Queue writes require task state `active`; the first open atomically invokes the task-state owner for `planned -> active`. Close requires the exact `apply_delta` receipt and derives Coverage `next_batch`. Cancellation goes through a registered `apply_amendment.py` transaction | `python3 Tools/update_queue.py . --id B1 --transition open --gate-receipt RECEIPT --expected-state-revision 0 --expected-sha256 sha256:... --actor-role integrator --apply` |
| `register_amendment.py` | Sole writer of executable operational Amendment rows for same-scope Queue replans, scope replans, and batch cancellation. It accepts only the current state schema, defaults to dry-run, requires an integrator plus exact Coverage/Queue/Progress SHA compare-and-swap, and rechecks repository-contained proposals/plans under the shared lock. It publishes the append-only receipt first, then one approved pending Progress row that names it; an unreferenced receipt is inert, so interruption cannot leave Progress pointing at absent evidence. A pending receipt is current authorization and must bind the live Progress bytes; a verified execution must bridge its three before-SHAs and time to registration, after which the registration is historical evidence only. At most one operational Amendment may be pending | `python3 Tools/register_amendment.py . --operation scope-replan --plan .cambium/deltas/amendments/A1.yaml --date YYYY-MM-DD --summary "Approved scope change" --approval-reference APPROVAL --expected-coverage-sha256 sha256:... --expected-progress-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `apply_amendment.py` | Consume one registered approved scope/disposition change as a guarded Coverage/Queue/Progress transaction. The plan and registration receipt bind exact before revisions and all three SHAs to a complete Coverage proposal; `scope-replan` recompiles current Queue structure and `cancel-batch` retires one queued/open leaf without erasing history. A durable prepare receipt plus lock-owner fingerprints make an interrupted multi-file write diagnosable; commit/abort receipts record the consumed registration and outcome. It does not write non-scope Task Contract changes; direct post-materialization edits fail closed and currently require a preserved successor task | `python3 Tools/apply_amendment.py . --plan .cambium/deltas/amendments/A1.yaml --expected-coverage-sha256 sha256:... --expected-progress-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `adopt_standards.py` | Sole active-task Standards/Profile adoption writer (K12/10 semantics; K13/15 transaction). Its closed YAML plan binds approved K00/03 bytes, deterministic after Kernel/Profile snapshots, Task/Contract identity, Queue revisions, three state SHAs, changed predicates, dimension/boundary-specific invalidated evidence, and immediate/deferred gates. Dry-run is default; apply accepts only `active`/`paused`, rejects incompatible Work Specs, affected `merge-ready` batches, or affected `open` batches without `revalidation-required`, and changes no lifecycle/hold itself. It requires all three canonical state objects to satisfy the current schema, synchronizes identity/load set, advances Queue/Progress `queue_revision` once, records append-only adoption history, and consumes immediate Queue consistency before commit. Deferred batch-close/Terminal gates wait for their boundaries. Historical receipts are not rewritten and remain catalogued, but only current producer protocols may satisfy the live execution chain. Prepare/commit/abort plus the lock recover partial writes; no Markdown adoption report is produced | `python3 Tools/adopt_standards.py . --plan .cambium/deltas/standards-adoptions/SA-001.yaml --apply --actor-role integrator` |
| `render_queue.py` | Deterministically render the optional human view at `.cambium/reports/required_queue.md`, including each Queue item's Work Spec path/SHA binding; validates canonical state first and never reads the Markdown back as input | `python3 Tools/render_queue.py .` |
| `apply_delta.py` | Deterministic application of one worker Coverage delta during serial merge. Every mode rejects Queue/compiler-owned control fields. Canonical `--root` mode binds the exact managed paths and merge-ready manifest, requires integrator role plus current Coverage/Queue SHAs, uses the shared writer lock, revalidates the result, rolls back ordinary failures, and publishes a bound receipt; `next_batch_updates` remains a suggestion for the integrator. Detached two-path mode remains for non-runtime ledgers and is not a canonical-state write | `python3 Tools/apply_delta.py .cambium/state/coverage_ledger.yaml .cambium/deltas/B1.yaml --root . --expected-coverage-sha256 sha256:... --expected-queue-sha256 sha256:... --actor-role integrator --apply` |
| `compose_vocab.py` | Persistent vocabulary compiler: composes `vocab.yaml` from the kernel base and the profile selected in K00/03 active state. The selected manifest declares `profile_id` and its one `Vocabulary Extensions` binding; `volatility_defaults` registers each domain once; the resolved extensions path supplies base-field extension ownership; profile-only controlled fields are added to the frontmatter list automatically. `--extensions` may repeat the bound active path but cannot select another profile; the output header is provenance only. `--check` requires both parsed values and deterministic provenance/rendering to match | `python3 Tools/compose_vocab.py --check` |
| `check_profile.py` | Filled-profile structural check: derives the slot list from `profiles/README.md`; verifies identity syntax and directory agreement, slot bindings, sparse execution overrides against their closed registry, and `Configured`/inactive table consistency; rejects leftover `TODO(profile)` markers and reserved IDs. It checks structure, never answer quality, and is not run against `_template` itself | `python3 Tools/check_profile.py profiles/<profile-id> --receipts Tools/receipts/profile.jsonl` |
| `check_residual_content.py` | Generic K12/09 item 6 residual-content scanner. The selected profile owns every accepted/excluded content root and every literal frontmatter/heading matcher; only VCS metadata directories named `.git`, `.hg`, or `.svn` are always outside traversal. The tool owns safe traversal, fence-aware matching, a hard ≤55-second evidence-production budget, zero-file, missing-accepted-root, and inert-matcher failure, receipts, and `0/1/2` exit semantics; missing excluded roots are allowed. K12/09 item 6 non-triviality: when a run finds no candidate, the accepted roots are re-read as the profile's own known-residual sample and the configuration must recognise at least one Markdown file there, otherwise the run fails with `residual-content-inert-matcher` instead of reporting a zero-candidate pass; the passing summary names the witness. The caller must still satisfy the kernel's ≤60-second whole-command contract. `--scan-id` binds every receipt to the stable registry ID; receipts from a successfully loaded config record its SHA-256 so configuration changes invalidate old evidence. Findings are candidates only. Tool contract owner: K12/09 item 6; scan-definition owner: selected profile `Registered Scan Registry` | `python3 Tools/check_residual_content.py . --scan-id <stable-scan-id> --config profiles/<profile-id>/scan-configs/<scan>.yaml --time-limit 55 --receipts Tools/receipts/residual.jsonl` |
| `stamp_cards.py` | Kernel route and Runtime Card verification (K00/03 Write-back Checklist): checks the shared `kernel-runtime-routes` registry identity, exact R01-R13 coverage across both indexes and the on-disk Read Set/Card pairs, filename prefixes, source boundaries, `source_hash`, and that every `compiled_from` equals K00/03 active `standards_version`; defaults to `kernel/Cards`; missing, empty, incomplete, or malformed layers fail closed; `--check` is read-only; `--set-version` must equal the active version and stamps every Card including the Index | `python3 Tools/stamp_cards.py . --check` |
| `check_freshness.py` | Freshness check: computes review_by from volatility and last_verified (fallback: last_reviewed, then file modification time per K08/05, flagged pending first verification); `--defaults` accepts a flat mapping or `Tools/vocab.yaml` / a profile's `vocabulary-extensions.yaml` (their `volatility_defaults`); an all-skip run reports NOTHING CHECKED as a candidate, not a pass | `python3 Tools/check_freshness.py . --as-of 2026-07-21 --defaults profiles/<your-profile-id>/vocabulary-extensions.yaml --exclude Cards --receipts Tools/receipts/fresh.jsonl` |
| `duplicate_check.py` | Cross-file duplicate paragraph candidate detection; full vault by default; `--exclude` is repeatable and defaults to the single component `legacy`, the conventional name for a frozen-snapshot area that a vault need not have; compiled Cards and profile skeletons should be excluded from corpus-duplication review; supports `--receipts` and exits 2 when candidates exist | `python3 Tools/duplicate_check.py . --exclude _template --exclude Cards --receipts Tools/receipts/dup.jsonl` |
| `kblib.py` | Shared library and sole restricted-YAML parser owner. Duplicate keys and unsupported constructs fail closed; it also provides deterministic YAML rendering, repository-contained managed paths, file and repository-snapshot SHA-256 fingerprints, atomic writes, Markdown helpers, and receipts | imported by the scripts above |

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
   adoption and task definition. Declare exactly one
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
   snapshots. Only the integrator applies it. The writer
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
  (owner: K12/09; a seven-item
  closed list, including full-vault `check_links`, `check_vocab`, and the
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
  independently parsed by `check_queue.py`.
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
  or recovers the transaction. Queue consistency is immediate; other changed-
  predicate gates are enforced at their declared boundaries. The plan and
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
- **Governance** = `stamp_cards.py . --check`, `check_moc.py`, and
  `check_profile.py` against each filled profile a deployment selects. The
  published `_template` is a form, not a runnable profile.
  `compose_vocab.py --check` joins that list in a vault that has composed a
  vocabulary. This repository ships no composed `vocab.yaml`, so here the
  command reports that no profile is selected and exits 1; see Generated
  artifacts below.
- **Profile bring-up** = copy `profiles/_template/`, fill the copy, then run
  `check_profile.py` against that filled profile before loading it. The form
  itself is not a runtime target. Profile bring-up is not part of batch or note
  close because a profile is authored once and then loaded, not edited per
  batch. Setup is currently manual and file-based: `check_profile.py` validates
  structure and bindings but does not ask questions, generate domain choices,
  author a profile, approve it, or select it.

Shared conventions:

- Human-readable summaries go to stdout; machine-readable receipts are
  appended as JSONL via `--receipts PATH`.
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
  the non-applicable path inert
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
  used by the residual scanner
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
- `execution_defaults.template.yaml` -- the canonical machine-readable
  membership registry of which kernel execution defaults a profile may
  override and which constants it may not. Each entry points to the kernel
  module that owns the item's meaning and value; `check_profile.py` consumes
  this registry directly
- `residual_scan_config.template.yaml` -- machine-parameter form for
  `check_residual_content.py`; a selected profile owns its filled copy while
  its Registered Scan Registry remains the owner of scan identity, invocation,
  candidate semantics, and Judgment Item binding

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
