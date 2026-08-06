## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]].
- Next: [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]].

## Guidance Reconciliation Review

Before every batch close and before a long task enters `completion-candidate`, reconciliation MUST be performed against [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis#Mid-task Guidance And Contract Amendment|Mid-task Guidance And Contract Amendment]]. Batch-close reconciliation is incremental: reconcile only new guidance after `last_reconciled_guidance_id`, plus existing open items; the three-counter semantics are unchanged, only the counting scope narrows to increment + existing open items.

The minimum pass condition is:

```text
unclassified_guidance = 0
accepted_unmapped_guidance = 0
implemented_unverified_guidance = 0
```

The checks include:

- Every **important Guidance Event** (positively defined: messages that change objective, scope, acceptance, priority, or content judgment) has a `guidance_id` and an Amendment Record; pure status inquiries or confirmation-type messages get one log line, consume no `guidance_id`, and do not enter an Amendment.
- Raw guidance and normalized intent have the same meaning, with no suggestion widened into a command and no command downgraded into a suggestion.
- New requirements modify only the contract dimensions explicitly involved; non-conflicting old constraints remain in effect.
- Version bumps of scope, contract, queue, batch, and Standards match the actual impact.
- Accepted guidance has been mapped to the current batch, the Required Queue, the Coverage Ledger, source intake, or an explicit deferred record.
- `research-first` user hypotheses are not written as canonical facts before source verification.
- User-provided URLs use the actual documents as Sources; first-party context has not been generalized without bounds.
- `deferred` has authority, a reason, and a re-entry condition; `not-applicable` has a checkable basis.
- `superseded` preserves the before/after guidance relationship.
- The safe switching policy was followed; switching left no half-written files, unverified modifications, or loss of the current batch's consistency.
- `clarification-required` items affecting Required completion are resolved; otherwise `completion-candidate` MUST NOT be entered.

An explicit scope or acceptance requirement from a user with task authority MUST NOT be changed to optional or deferred by the executor unilaterally. Dependency-based queueing MAY adjust execution timing, but MUST NOT silently cancel a requirement.

### Guidance During Terminal Audit

Record `guidance_cutoff_id` when the Terminal Audit starts. When new guidance arrives afterwards:

- Changes the current objective, scope, acceptance, exclusions, time contract, or Required content: the Terminal Audit is invalidated and the task state returns to `active`.
- Fixes factual, link, source, or QA problems in the candidate results: handle in place as major per [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence#Terminal Findings And Convergence|Terminal Findings And Convergence]] (targeted re-check + receipt supersede); the Terminal Audit is not voided as a whole.
- The user explicitly designates it as a future task or optional backlog: record the new contract / backlog assignment without changing the current Terminal Proof.
- Only asks about status and does not change the task: answer normally without changing the cutoff.

New requirements MUST NOT be ignored on the grounds that "the Terminal Audit has already started", nor may guidance that explicitly belongs to a future task be forced into the current scope.

## Source Intake And Promotion Review

Source-driven expansion requires additional checks:

- Whether source identity, date, URL, source type, and applicability boundary are clear.
- Whether key claims can be located in the original source.
- Whether source authority and evidence role are judged separately.
- Whether community signals have been miswritten as verified regularities.
- Whether official company articles are used only to support their actual disclosure scope.
- Whether user hypotheses, source leads, and first-party context preserve evidence boundaries per [[kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads#User Guidance, Hypotheses And Source Leads|User Guidance, Hypotheses And Source Leads]].
- Whether multiple sources are genuinely independent, and whether terminology and experimental conditions are comparable.
- Whether the choice to update, create, split, merge, or defer for new information has a graph impact rationale.
- Whether new canonical notes pass the [[kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate#Canonical Promotion Gate|canonical promotion gate]].
- Whether contested or superseded conclusions retain their status, sources, and supersession relationships.

A single source-driven batch is responsible for claim and promotion correctness at that time; the subsequent Source Audit is responsible for cross-batch identity/currentness, conflicts, supersession, and affected-note propagation. If the artifact, source dependency, review due date, and acceptance predicates are unchanged, local source receipts MAY be reused; a specialized Audit MUST NOT be used to rewrite stable mechanisms unrelated to its global invariant.
