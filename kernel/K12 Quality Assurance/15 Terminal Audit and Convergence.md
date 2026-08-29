## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]].
- Next: [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]].

## Terminal Audit

Terminal Audit is the last gate for `completion_semantics: build`; its states and reporting are owned by [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting#Completion Gate|Completion Gate]]. It states no judgment items of its own; it consumes the receipts emitted by the modules its steps point at, which are registered in [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]]. Maintenance completion is bounded by K00/06 and K13/12 and MUST NOT enter this audit.

Before a build task enters `completion-candidate`, the task transition consumes a current `required-queue-completion` receipt. That receipt authorizes only the transition; because the transition changes Progress bytes, it is not the frozen completion receipt.

Against the post-transition frozen candidate, Terminal Audit must establish all of the following:

- the Contract, scope, Standards, selected Profile, loaded-set identity,
  guidance cutoff, and exact Coverage, Progress, Queue, and repository
  fingerprints are fixed for the decision;
- changed, directly invalidated, dependency-invalidated, overdue, sampled, and
  reusable evidence are completely partitioned;
- Guidance Reconciliation has a final disposition for every in-cutoff item;
- Coverage, Required Queue, file scope, and configured Corpus Planning artifacts
  reconcile, with current `corpus-plan-structure` and, when configured,
  `corpus-plan-semantic-acceptance` evidence;
- a new post-transition `required-queue-completion` receipt proves zero
  remaining Required work and is not reused from transition entry;
- the Batch-close Closed List passes on the frozen snapshot;
- changed, invalidated, overdue, and sampled objects receive note-type-aware
  review while still-current evidence is reused only through K12/07;
- Source Promotion, expression synchronization, and applicable Profile Gates
  are closed;
- rendering evidence follows the deterministic-first escalation boundary, and
  systemic findings receive bounded family expansion;
- receipt reconciliation, Final Handoff, and a conforming
  [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof]]
  are produced.

This semantic owner does not prescribe the action order or implementation used to establish these outcomes. Terminal Audit findings are handled by grade below; a single minor or major finding does not return the whole task to `active`. Failed items not closed by grade become successor batches through the canonical Coverage/Queue amendment path, without reopening closed history. Report wording MUST NOT be changed to bypass a failure. The field contract and deterministic completion check are owned solely by K12/16.

## Terminal Findings And Convergence

Terminal Audit findings are handled with the three-level grading of [[kernel/K12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]]:

- `minor`: record; does not block completion.
- `major`: fix in place + targeted re-check of that object only + receipt supersede for that object; do not re-freeze the snapshot, do not re-run the Batch-close Closed List.
- `critical` (affecting a completion predicate): the task state returns to `active`; on re-entering the Terminal Audit, reuse all non-invalidated receipts, and re-run the Batch-close Closed List only once.

The Terminal Audit round cap is 2: round 2 only confirms that round 1's findings are closed and introduces no new review scope; when the round cap is exceeded, escalate to the user for decision. This round cap is a fixed kernel constant, not a default that the selected profile or task contract may override.

Guidance received during the Terminal Audit: only the "changes objective, scope, or acceptance" kind invalidates the Terminal Audit; corrective guidance is handled in place as major without voiding the Terminal Audit as a whole; status inquiries do not affect the cutoff. For the branch details see [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Guidance During Terminal Audit|Guidance During Terminal Audit]].
