## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]].
- Next: [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Completion Gate

Before a page is promoted to `reviewed`, it MUST pass [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#Single Note Review|Single Note Review]].

Before a source-driven new canonical page is promoted to `reviewed`, it MUST also pass [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Source Intake And Promotion Review|Source Intake And Promotion Review]].

Before a batch closes, it MUST pass [[kernel/K12 Quality Assurance/14 Batch Review#Batch Review|Batch Review]].

Before a module is declared complete, it MUST pass [[kernel/K12 Quality Assurance/03 Module and Coverage Review#Module Review|Module Review]].

Before a profile-owned expression readiness axis is promoted to its completion value, the artifact MUST pass the R05 kernel gate and the supplemental gate registered for that axis in the `Routing And Gate Registry`; the kernel does not name concrete status values or artifacts.

A long task may be marked `complete` only after completing [[kernel/K12 Quality Assurance/03 Module and Coverage Review#Coverage Reconciliation Review|Coverage Reconciliation Review]], [[kernel/K12 Quality Assurance/04 Guidance and Source Review#Guidance Reconciliation Review|Guidance Reconciliation Review]], and the [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence#Terminal Audit|Terminal Audit]].

Historical gate results may enter the Terminal Proof only through the [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Reuse Gate|Reuse Gate]]; `reviewed`, a date, or "passed previously" is not by itself reusable evidence.

The Completion Gate states no judgment items of its own; it consumes the receipts emitted by the modules it points at, which are registered in [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].

If any applicable hard gate fails, the current state MUST be kept; the standard MUST NOT be lowered because the task is near its end, a time point has been reached, the run has lasted long, or many files have been created.

Authoring completion does not require all frontier conclusions to reach `validated`. Independent production data, cross-implementation reproduction, or future monitoring results that cannot be obtained within the current task MAY enter the evidence backlog, but MUST:

- Not affect the current body's complete explanation of known mechanisms.
- Limit claim strength and retain `evidence_maturity`.
- Record the missing evidence, the re-verification conditions, and the affected pages.
- Not use the evidence backlog to conceal a Required authoring gap missing body text, sources, profile-registered expression migration, or QA.

## Final Report

After each large batch completes, report:

- Which files were created, expanded, moved, and deleted.
- Which content reached the target `authoring_status`; which profile-owned readiness axes reached the completion values registered in the `Routing And Gate Registry`.
- Automated check results.
- Unfinished gaps and their reasons.
- Whether there are unverified time-sensitive conclusions.
- Which conclusions remain signal, single-source, contested, or superseded.
- Next-batch dependencies and risks.
- Which guidance this batch received, applied, queued, deferred, or superseded, and the corresponding version changes.
- Which rendering levels and deterministic verifications were performed; if Levels 2–4 were entered, report the trigger, unresolved question, minimal check target, result, and whether expanded checking was triggered; if not entered, state `visual_trigger: not_applicable` explicitly.
- Which AuditReceipts were reused, superseded, or invalidated, what scope the incremental manual review and sampling covered, and whether systemic expansion was triggered.

The final task report MUST also attach the Amendment Log summary, Guidance Reconciliation, Coverage Ledger summary, Terminal Proof, optional / deferred work, and the external evidence backlog.

## Related

- [[kernel/K04 Content Depth Standard|Content Depth Standard]]
- [[kernel/K07 Sources and Accuracy Standard|Sources and Accuracy Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[kernel/K08 Metadata and Status Standard|Metadata and Status Standard]]
- [[kernel/K02 Knowledge Base Build Execution Standard|Knowledge Base Build Execution Standard]]
