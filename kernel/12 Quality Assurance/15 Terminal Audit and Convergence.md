## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/14 Batch Review|Batch Review]].

## Terminal Audit

The Terminal Audit is the last gate of a long task; the states it runs between, and the reporting it feeds, are owned by [[kernel/12 Quality Assurance/06 Completion Gate and Reporting#Completion Gate|Completion Gate]]. It states no judgment items of its own; it consumes the receipts emitted by the modules its steps point at, which are registered in [[kernel/12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].

After the task moves from `active` to `completion-candidate`, run the Terminal Audit:

1. Freeze new content; record the contract, scope, queue, Standards version, `guidance_cutoff_id`, and the candidate completion state.
   - Also record the selected kernel Runtime Card IDs and paths, Read Sets, any combined profile extension route, and the module paths read back on escalation.
2. Load the Audit Receipt Register; compute changed, directly invalidated, dependency-invalidated, overdue, and legacy-evidence.
3. Run [[kernel/12 Quality Assurance/04 Guidance and Source Review#Guidance Reconciliation Review|Guidance Reconciliation Review]] and confirm that all guidance within the cutoff has a final disposition.
4. Reconcile the Coverage Ledger against the file system, exclusions, competency matrix, and Required Queue; if that reconciliation was already completed before the completion-candidate freeze and no files changed afterwards, reuse that result directly without re-running.
5. Confirm all batches are closed and the merge queue is empty (no `merge-ready` unmerged batches, no written-out unapplied deltas), and there are no unverified modifications or unresolved invalidations.
6. Run the [[kernel/12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]] (against the final frozen snapshot).
7. Run note-type-aware content review on changed, invalidated, overdue, and bounded-sampling objects; reuse the remaining valid receipts per the [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Reuse Gate|Reuse Gate]].
8. Check Source Promotion, plus the expression-layer migration and profile synchronization gates registered in the `Routing And Gate Registry`; specialized Audits prove only cross-batch invariants and do not indiscriminately redo local mechanism review.
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

Only when the three open guidance counters are 0, `required_authoring_gaps = 0`, `unverified_batches = 0`, `unresolved_invalidations = 0`, and all applicable gates pass, may the task state be changed to `complete`.

`full_deterministic_results`: a reference to the complete result set of the deterministic checks the Terminal Audit ran in full against the final frozen snapshot. The `unverified_batches` count includes batches that are `merge-ready` but unmerged; a value of 0 therefore requires the merge queue to be empty.

`rendering_evidence` MUST state the highest level actually used and the verification result. When there is no visual exception trigger, recording `visual_trigger: not_applicable` suffices; the absence of UI, screenshots, or recordings MUST NOT block completion on that account.

## Terminal Findings And Convergence

Terminal Audit findings are handled with the three-level grading of [[kernel/12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]]:

- `minor`: record; does not block completion.
- `major`: fix in place + targeted re-check of that object only + receipt supersede for that object; do not re-freeze the snapshot, do not re-run the Batch-close Closed List.
- `critical` (affecting a completion predicate): the task state returns to `active`; on re-entering the Terminal Audit, reuse all non-invalidated receipts, and re-run the Batch-close Closed List only once.

The Terminal Audit round cap is 2: round 2 only confirms that round 1's findings are closed and introduces no new review scope; when the round cap is exceeded, escalate to the user for decision. This round cap is a fixed kernel constant, not a default that the selected profile or task contract may override.

Guidance received during the Terminal Audit: only the "changes objective, scope, or acceptance" kind invalidates the Terminal Audit; corrective guidance is handled in place as major without voiding the Terminal Audit as a whole; status inquiries do not affect the cutoff. For the branch details see [[kernel/12 Quality Assurance/04 Guidance and Source Review#Guidance During Terminal Audit|Guidance During Terminal Audit]].
