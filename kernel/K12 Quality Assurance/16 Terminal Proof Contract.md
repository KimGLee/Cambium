## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]].

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

`selected_card_paths` is a one-to-one materialization of `selected_route_ids`: every selected Rxx route has exactly its canonical Card path and no other Card path appears. `selected_read_sets` records only actual source readbacks and may therefore be a subset of the selected routes. With repository-root validation, a kernel Read Set must be registered to one of the selected Rxx routes. A profile Read Set may be recorded only when `selected_profile_route_ids` is non-empty; because the profile route registry is prose rather than a machine-readable canonical map, its exact route-to-path binding remains a manual review item and MUST NOT be reported as deterministically verified.

`full_deterministic_results` references the complete result set of the deterministic checks run in full against the final frozen snapshot. The `unverified_batches` count includes batches that are `merge-ready` but unmerged; a value of 0 therefore requires the Queue-derived merge view to be empty. `queue_check_receipt` binds this claim to the frozen Queue bytes rather than a separately maintained merge list.

`rendering_evidence` MUST state the highest level actually used and the verification result. When there is no visual exception trigger, recording `visual_trigger: not_applicable` suffices; the absence of UI, screenshots, or recordings MUST NOT block completion on that account.

## Terminal Completion Gate

After the task has entered `completion-candidate`, first run `python3 Tools/check_queue.py <repository-root> --require-complete --receipts <proof-queue-receipt>`, then run `python3 Tools/check_proof.py <proof> --root <repository-root> --progress-ledger .cambium/state/progress_ledger.yaml --ledger .cambium/state/coverage_ledger.yaml --receipts <proof-receipt>`; both MUST receive exit 0. This Queue receipt is distinct from the pre-transition receipt consumed to enter `completion-candidate`: it binds the frozen post-transition Progress bytes. Finally, `update_task.py --transition complete` consumes the Proof pass receipt.

The two Ledger arguments and the Queue reference are fixed canonical, non-symlinked state objects under the named repository root; caller-selected substitutes are forbidden. `check_proof.py` requires Progress state `completion-candidate` or `complete` with no pending Guidance or Amendment; verifies common task, scope, Standards, profile, and contract identity; binds canonical Coverage and Queue bytes, Queue revisions, remaining count, completion receipt, and zero Coverage gaps. In `completion-candidate`, the Proof and pass receipt bind the current candidate Progress bytes. After `complete`, revalidation instead binds those same pre-complete bytes through the latest task-transition receipt, whose after-fingerprint binds the current complete Progress bytes; the completed state is therefore verifiable without rewriting the Proof. The selected profile must also pass `check_profile.py`.

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
