## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]].
- Next: [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]].

## Terminal Audit

Terminal Audit is the last gate for `completion_semantics: build`; its states and reporting are owned by [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting#Completion Gate|Completion Gate]]. It states no judgment items of its own; it consumes the receipts emitted by the modules its steps point at, which are registered in [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]]. Maintenance completion is bounded by K00/06 and K13/12 and MUST NOT enter this audit.

Before a build task moves from `active` (or the K13/12 all-cancelled `planned`
case) to `completion-candidate`, run the `check_queue.py --require-complete`
gate with `--receipts <candidate-receipt>` and consume that receipt in the task
transition. That receipt authorizes only the transition; the
transition changes Progress bytes, so it is not the frozen completion receipt.
After the transition, run the Terminal Audit:

1. Freeze new content; record the contract, scope, exact Coverage/Progress/Queue SHA-256 fingerprints, Required Queue path, `queue_revision`, `queue_state_revision`, Standards version, selected profile manifest, `guidance_cutoff_id`, and the candidate completion state.
   - Also record the selected Rxx route IDs and their corresponding canonical Runtime Card paths, any combined `P:<profile_id>:<route_name>` supplemental routes, and every Read Set or leaf path actually read back. Terminal evidence MUST include R01 for the common control boundary, R12 for the bounded targeted/specialized review scope, and R08 for this audit/completion route.
2. Load the Audit Receipt Register; compute changed, directly invalidated, dependency-invalidated, overdue, and invalidated-evidence.
3. Run [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Guidance Reconciliation Review|Guidance Reconciliation Review]] and confirm that all guidance within the cutoff has a final disposition.
4. Reconcile the Coverage Ledger against the file system, exclusions, the bound [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract#Capability Matrix Contract|Capability Matrix]] when `Corpus Planning` has `applicability.state: configured`, and Required Queue, including exact Queue-manifest/Coverage-projection equality. Run `python3 Tools/check_corpus_plan.py . --receipts <corpus-plan-receipt>` against the frozen candidate and consume its current Gate ID `corpus-plan-structure` pass. When configured, also consume a current passed Gate ID `corpus-plan-semantic-acceptance` receipt produced from the Profile-authorized restricted-YAML decision plan. The Terminal Proof names both exact receipts and rejects stale bytes. Ordinary affected batch close consumes only the structural gate; Terminal Audit is the boundary that requires full Matrix semantic acceptance.
5. Against the frozen candidate state, rerun `python3 Tools/check_queue.py . --require-complete --receipts <proof-queue-receipt>` and require `remaining_required_work_units = 0`. The pre-transition receipt MUST NOT be reused here. Within the local trust boundary, this records that the checked bytes contain no `queued`, `open`, or `merge-ready` Required batches, unexplained cancellation, written-out unapplied delta, or stale Queue/Progress reference.
6. Run the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]] (against the final frozen snapshot).
7. Run note-type-aware content review on changed, invalidated, overdue, and bounded-sampling objects; reuse the remaining valid receipts per the [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Reuse Gate|Reuse Gate]].
8. Check Source Promotion, the R05 expression-layer migration and synchronization gate for every in-scope artifact, and any supplemental profile gate; specialized Audits prove only cross-batch invariants and do not indiscriminately redo local mechanism review.
9. Review this round's `rendering_mode` and Level 0 / Level 1 deterministic evidence; review Level 2–4 UI, screenshot, or recording evidence only when a recorded objective trigger exists, and expand checks according to confirmed systemic impact.
10. Perform family expansion for systemic problems found by sampling or targeted checks; fixes and re-checks are handled by grade per Terminal Findings And Convergence.
11. Produce the receipt reconciliation, Final Handoff, and the [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof]].

Terminal Audit findings are handled by grade per Terminal Findings And Convergence; a single minor or major finding does not return the task state to `active` as a whole. Failed items not closed by grade become successor batches through the canonical Coverage/Queue amendment path; the integrator does not reopen closed history. Report wording MUST NOT be modified to bypass a failure. The field contract and deterministic completion check are owned solely by [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]].

## Terminal Findings And Convergence

Terminal Audit findings are handled with the three-level grading of [[kernel/K12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]]:

- `minor`: record; does not block completion.
- `major`: fix in place + targeted re-check of that object only + receipt supersede for that object; do not re-freeze the snapshot, do not re-run the Batch-close Closed List.
- `critical` (affecting a completion predicate): the task state returns to `active`; on re-entering the Terminal Audit, reuse all non-invalidated receipts, and re-run the Batch-close Closed List only once.

The Terminal Audit round cap is 2: round 2 only confirms that round 1's findings are closed and introduces no new review scope; when the round cap is exceeded, escalate to the user for decision. This round cap is a fixed kernel constant, not a default that the selected profile or task contract may override.

Guidance received during the Terminal Audit: only the "changes objective, scope, or acceptance" kind invalidates the Terminal Audit; corrective guidance is handled in place as major without voiding the Terminal Audit as a whole; status inquiries do not affect the cutoff. For the branch details see [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Guidance During Terminal Audit|Guidance During Terminal Audit]].
