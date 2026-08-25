## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]].
- Next: [[kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract|Gate Receipt Payload Contract]].

## Terminal Proof Contract

The Terminal Proof is the machine-readable completion claim produced after the [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence#Terminal Audit|Terminal Audit]] for `completion_semantics: build`. It does not apply to maintenance completion; `check_proof.py` MUST reject a Progress contract that selects `maintenance`. It contains at least:

```text
task_id
scope_version
contract_version
coverage_ledger_sha256
progress_ledger_sha256
required_queue_path
queue_revision
queue_state_revision
required_queue_sha256
remaining_required_work_units
queue_check_receipt
corpus_plan_check_receipt
corpus_plan_semantic_acceptance_receipt
standards_version
selected_profile_manifest
selected_route_ids
selected_card_paths
selected_profile_route_ids
selected_read_sets
loaded_module_paths
guidance_cutoff_id
guidance_reconciliation_result
coverage_reconciliation_result
required_authoring_gaps
unverified_batches
automated_QA_result
manual_review_result
rendering_evidence
audit_snapshot_id
dimension_coverage
audit_receipt_register
reused_receipts
superseded_receipts
invalidated_receipts
unresolved_invalidations
full_deterministic_results
incremental_manual_scope
sampling_scope_and_result
systemic_expansions
deferred_evidence_backlog
final_handoff
time_contract_result
```

`selected_card_paths` is a one-to-one materialization of `selected_route_ids`: every selected Rxx route has exactly its canonical Card path and no other Card path appears. The five selection lists (`selected_route_ids`, `selected_card_paths`, `selected_profile_route_ids`, `selected_read_sets`, and `loaded_module_paths`) MUST exactly match the frozen Progress Task Contract, including order; a passing live Queue gate does not authorize a Proof to declare a different load set. `selected_read_sets` records only actual source readbacks and may therefore be a subset of the selected routes. With repository-root validation, a kernel Read Set must be registered to one of the selected Rxx routes. A profile Read Set may be recorded only when `selected_profile_route_ids` is non-empty; because the profile route registry is prose rather than a machine-readable canonical map, its exact route-to-path binding remains a manual review item and MUST NOT be reported as deterministically verified.

Repository-root validation also reruns the canonical `profile-load` producer
against the exact frozen `selected_profile_manifest`. Its passing
`profile-check-summary`, Profile snapshot, Profile-contract fingerprint, and
fingerprint of the complete canonical profile-load root-input closure are part of the
deterministic result and proof summary; the Proof checker does not maintain a
second registry parser. Immediately before summary publication it rebinds both
the Profile tree and those root-owned inputs to the shared evaluation. Profile
dependency closure is separate from the five selection lists above and none of
its members is inserted into `loaded_module_paths` merely to prove Profile
loading.

`full_deterministic_results` references the complete result set of the deterministic checks run in full against the final frozen snapshot. The `unverified_batches` count includes batches that are `merge-ready` but unmerged; a value of 0 therefore requires the Queue-derived merge view to be empty. `queue_check_receipt` binds this claim to the frozen Queue bytes rather than a separately maintained merge list.

`corpus_plan_check_receipt` identifies exactly one current
`check_corpus_plan.py` pass in `audit_receipt_register`. It is required for
every build Terminal Proof, including an explicit `applicability.state: not-applicable` Profile
slot. The checker re-resolves the selected Profile and slot, re-hashes the
Profile/Scope/slot/bound artifacts, and requires the receipt's task, Queue revisions,
three state fingerprints, applicability, and repository snapshot to match the
frozen candidate. A missing, duplicate, malformed, differently versioned, or
stale receipt blocks completion.

`corpus_plan_semantic_acceptance_receipt` is `null` only when the current
Corpus Planning slot has `applicability.state: not-applicable`. When it has
`applicability.state: configured`, the field identifies exactly one current
passed `record_corpus_acceptance.py` receipt in
`audit_receipt_register`. The receipt MUST carry Gate ID
`corpus-plan-semantic-acceptance`, consume the named current structural receipt,
cover every current Capability ID in Matrix order with `accepted`, and bind the
exact decision plan, Profile authority Role and decision scope, Profile/Scope/
slot/artifact bytes, canonical state fingerprints, Queue revisions, and frozen
repository snapshot. A rejected, stale, absent, duplicate, or structurally
unmatched receipt blocks completion.

`rendering_evidence` MUST state the highest level actually used and the verification result. When there is no visual exception trigger, recording `visual_trigger: not_applicable` suffices; the absence of UI, screenshots, or recordings MUST NOT block completion on that account.

`dimension_coverage` accounts for each of the seven base receipt dimensions fixed by [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Dimension-specific Audit Receipt|K12/07]]. A dimension that ran records the receipt IDs carrying its verdicts; a dimension with no in-scope object records an explicit `not-applicable: <reason>` declaration. An omitted dimension, an empty receipt list, or a reasonless declaration is not a pass, because a dimension nobody ran and a dimension with nothing to review are the same absence of receipts until the Proof separates them. The Terminal Proof owns this declaration, as it owns `rendering_evidence`; an extension dimension registered through the `Audit Dimension Registry` MAY appear as an additional entry under the same rules. A registered dimension whose target list carries `receipt` is accounted for on the same terms as the base seven; the permission above covers a `review`-only registration, which emits no receipt to cite. A registry the gate cannot enumerate blocks completion rather than reading as no registration. Every cited receipt MUST remain current under the active Standards adoption, resolve to exactly one uninvalidated record of the declared dimension in `audit_receipt_register`, and MUST NOT be cited under two dimensions, since a receipt carries one dimension. Whether a stated reason is true remains a manual review item.

## Terminal Completion Gate

After the task has entered `completion-candidate`, first run `python3 Tools/check_queue.py <repository-root> --require-complete --receipts <proof-register>` and `python3 Tools/check_corpus_plan.py <repository-root> --receipts <proof-register>`. For a configured plan, record or refresh semantic acceptance against the same frozen candidate with `python3 Tools/record_corpus_acceptance.py <repository-root> --plan <.cambium/deltas/corpus-plan-acceptances/id.yaml> --actor-role <Profile-bound-role-id> --receipts <proof-register> --apply`. Record the exact Queue, structural, and semantic receipt IDs in the Proof, then run `python3 Tools/check_proof.py <proof> --root <repository-root> --progress-ledger .cambium/state/progress_ledger.yaml --ledger .cambium/state/coverage_ledger.yaml --receipts <proof-receipt>`; every applicable command MUST receive exit 0. The Queue receipt is distinct from the pre-transition receipt consumed to enter `completion-candidate`: it binds the frozen post-transition Progress bytes. Finally, `update_task.py --transition complete` consumes the Proof pass receipt.

The two Ledger arguments and the Queue reference are fixed canonical, non-symlinked state objects under the named repository root; caller-selected substitutes are forbidden. `check_proof.py` requires Progress state `completion-candidate` or `complete` with no pending Guidance or Amendment; verifies common task, scope, Standards, profile, and contract identity; binds canonical Coverage and Queue bytes, Queue revisions, remaining count, completion receipt, and zero Coverage gaps. In `completion-candidate`, the Proof and pass receipt bind the current candidate Progress bytes. The 1.17 pass receipt additionally carries the path-sensitive repository snapshot that the one Terminal run observed outside `.git/` and `.cambium/`. `update_task.py` consumes current producer 1.17 evidence only after comparing its selected manifest, Profile snapshot, typed-contract fingerprint, root-owned-input fingerprint, and repository snapshot with the one Profile/K00 authority context admitted at transaction entry. Proposed, locked, and post-write runtime validations inject that same view pair; state and receipt publication each have authority currency checks immediately before and after, and a build completion additionally re-hashes the repository at those boundaries. After `complete`, historical revalidation instead binds the same pre-complete Progress bytes through the latest task-transition receipt, whose after-fingerprint binds the current complete Progress bytes; it shape-checks each proof by its producer era without loading today's repository or reinterpreting 1.16 evidence as if it had promised the 1.17 input/repository bindings. The selected Profile must also pass `profile-load`; a structural-lint invocation cannot stand in for that root-bound result.

Running `check_proof.py` without `--root` is structural lint only: it deliberately does not resolve files or verify canonical runtime state or the route/Card/Read Set registry, and therefore cannot support a transition to `complete`.

## Evidence Trust Boundary

Repository-root validation checks the Proof and referenced local evidence for
structure, declared producer/tool-version labels, exact state and snapshot
SHA-256 bindings, transition and receipt-chain agreement, and currency. It can
therefore reject missing, stale, incomplete, or internally inconsistent
evidence. These checks do not authenticate the executable that ran, the
operating-system identity behind an actor field, or the human/process identity
and independence of a reviewer. SHA-256 values are byte-integrity bindings,
not signed provenance. A party able to rewrite the repository, its tools, and
all evidence can construct a different but internally consistent Proof. Claims
requiring adversarial provenance MUST add an external trust anchor such as
signed receipts, a protected execution service, or equivalent attestation;
that facility is outside this baseline.

Only when the three open guidance counters are 0, `remaining_required_work_units = 0`, `required_authoring_gaps = 0`, `unverified_batches = 0`, `unresolved_invalidations = 0`, and all applicable gates pass, may the task state be changed to `complete`.
