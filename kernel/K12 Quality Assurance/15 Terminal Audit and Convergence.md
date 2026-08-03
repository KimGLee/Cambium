## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]].

## Terminal Audit

The Terminal Audit is the last gate of a long task; the states it runs between, and the reporting it feeds, are owned by [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting#Completion Gate|Completion Gate]]. It states no judgment items of its own; it consumes the receipts emitted by the modules its steps point at, which are registered in [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].

After the task moves from `active` to `completion-candidate`, run the Terminal Audit:

1. Freeze new content; record the contract, scope, queue, Standards version, selected profile manifest, `guidance_cutoff_id`, and the candidate completion state.
   - Also record the selected Rxx route IDs and their corresponding canonical Runtime Card paths, any combined `P:<profile_id>:<route_name>` supplemental routes, and every Read Set or leaf path actually read back. Terminal evidence MUST include R01 for the common control boundary, R12 for the bounded targeted/specialized review scope, and R08 for this audit/completion route.
2. Load the Audit Receipt Register; compute changed, directly invalidated, dependency-invalidated, overdue, and legacy-evidence.
3. Run [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Guidance Reconciliation Review|Guidance Reconciliation Review]] and confirm that all guidance within the cutoff has a final disposition.
4. Reconcile the Coverage Ledger against the file system, exclusions, competency matrix, and Required Queue; if that reconciliation was already completed before the completion-candidate freeze and no files changed afterwards, reuse that result directly without re-running.
5. Confirm all batches are closed and the merge queue is empty (no `merge-ready` unmerged batches, no written-out unapplied deltas), and there are no unverified modifications or unresolved invalidations.
6. Run the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]] (against the final frozen snapshot).
7. Run note-type-aware content review on changed, invalidated, overdue, and bounded-sampling objects; reuse the remaining valid receipts per the [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Reuse Gate|Reuse Gate]].
8. Check Source Promotion, the R05 expression-layer migration and synchronization gate for every in-scope artifact, and any supplemental profile gate; specialized Audits prove only cross-batch invariants and do not indiscriminately redo local mechanism review.
9. Review this round's `rendering_mode` and Level 0 / Level 1 deterministic evidence; review Level 2–4 UI, screenshot, or recording evidence only when a recorded objective trigger exists, and expand checks according to confirmed systemic impact.
10. Perform family expansion for systemic problems found by sampling or targeted checks; fixes and re-checks are handled by grade per Terminal Findings And Convergence.
11. Produce the receipt reconciliation, Final Handoff, and Terminal Proof.

Terminal Audit findings are handled by grade per Terminal Findings And Convergence; a single minor or major finding does not return the task state to `active` as a whole; failed items not closed by grade enter the Required Queue. Report wording MUST NOT be modified to bypass a failure.

The Terminal Proof contains at least:

```text
scope_version
contract_version
queue_revision
batch_revision
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

`selected_card_paths` is a one-to-one materialization of `selected_route_ids`: every selected Rxx route has exactly its canonical Card path and no other Card path appears. `selected_read_sets` is different: it records only actual source readbacks and may therefore be a subset of the selected routes. With repository-root validation, a kernel Read Set must be registered to one of the selected Rxx routes. A profile Read Set may be recorded only when `selected_profile_route_ids` is non-empty; because the profile route registry is prose rather than a machine-readable canonical map, its exact route-to-path binding remains a manual review item and MUST NOT be reported as deterministically verified.

The Terminal Completion Gate MUST run `python3 Tools/check_proof.py <proof> --root <repository-root> --progress-ledger <progress-ledger>` and receive exit 0. This proves that K00/03 active state, the frozen Progress Ledger contract, and the proof use the same Standards version and selected profile manifest; the selected profile must also pass `check_profile.py`. Running `check_proof.py` without `--root` is structural lint only: it deliberately does not resolve files or verify the canonical route/Card/Read Set registry, and therefore cannot support a transition to `complete`.

Only when the three open guidance counters are 0, `required_authoring_gaps = 0`, `unverified_batches = 0`, `unresolved_invalidations = 0`, and all applicable gates pass, may the task state be changed to `complete`.

`full_deterministic_results`: a reference to the complete result set of the deterministic checks the Terminal Audit ran in full against the final frozen snapshot. The `unverified_batches` count includes batches that are `merge-ready` but unmerged; a value of 0 therefore requires the merge queue to be empty.

`rendering_evidence` MUST state the highest level actually used and the verification result. When there is no visual exception trigger, recording `visual_trigger: not_applicable` suffices; the absence of UI, screenshots, or recordings MUST NOT block completion on that account.

## Terminal Findings And Convergence

Terminal Audit findings are handled with the three-level grading of [[kernel/K12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]]:

- `minor`: record; does not block completion.
- `major`: fix in place + targeted re-check of that object only + receipt supersede for that object; do not re-freeze the snapshot, do not re-run the Batch-close Closed List.
- `critical` (affecting a completion predicate): the task state returns to `active`; on re-entering the Terminal Audit, reuse all non-invalidated receipts, and re-run the Batch-close Closed List only once.

The Terminal Audit round cap is 2: round 2 only confirms that round 1's findings are closed and introduces no new review scope; when the round cap is exceeded, escalate to the user for decision. This round cap is a fixed kernel constant, not a default that the selected profile or task contract may override.

Guidance received during the Terminal Audit: only the "changes objective, scope, or acceptance" kind invalidates the Terminal Audit; corrective guidance is handled in place as major without voiding the Terminal Audit as a whole; status inquiries do not affect the cutoff. For the branch details see [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Guidance During Terminal Audit|Guidance During Terminal Audit]].
