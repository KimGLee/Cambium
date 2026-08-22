## Purpose

This page is the stable entry point of the Task Runtime and Execution Control standard. The detailed rules have been split into the modules below by responsibility; the original K02 rule text has not been reduced.

## Reading Rule

- First use this MOC to locate the rule owner, then read the modules required by the current task, event, or quality gate.
- Entering this domain does not require reading all modules at once.
- Each module returns to its parent via `Navigation` and links to the adjacent modules before and after it.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace\|Runtime State Model and Namespace]] | `Runtime State Namespace`, `Execution Roles`, `Control Accretion Decision` |
| [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics\|Task Contract Binding and Time Semantics]] | `Purpose`, `Core Execution Principle`, `Phase 0: Freeze The Contract`, `Time And Stop Semantics` |
| [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules\|Task State and Transition Rules]] | `Task State Machine` |
| [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis\|Guidance Classification and Impact Analysis]] | `Mid-task Guidance And Contract Amendment`: cumulative rule, classification, intake, and impact |
| [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching\|Guidance Disposition and Safe Switching]] | `Mid-task Guidance And Contract Amendment` |
| [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning\|Amendment Log and Controlled Replanning]] | `Mid-task Guidance And Contract Amendment` |
| [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract\|Progress Ledger Contract]] | `Progress Ledger`, `Machine-readable Ledger` |
| [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle\|Required Queue Contract and Lifecycle]] | `Purpose And Ownership`, `Queue Document Contract`, `Batch Work Specification Binding`, `Revisions And Fingerprints`, `Batch Lifecycle` |
| [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views\|Queue Compilation Replanning and Views]] | `Compiler, Updates, And Views` |
| [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration\|Batch Admission Transitions and Serial Integration]] | `Concurrent Batches`, `Transition Gates` |
| [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy\|Completion Policy]] | `Completion Policy`, `Maintenance Completion Policy` |
| [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings\|Completion Gate Bindings]] | `Completion Gates` |
| [[kernel/K13 Task Runtime and Execution Control/13 Final Handoff\|Final Handoff]] | `Final Handoff`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover\|Interruption Recovery and Rollover]] | `Interruption And Resume` |
| [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction\|Standards Adoption State Transaction]] | `Purpose And Boundary`, `Permitted Transaction`, `Guarded Write Protocol`, `Resume Boundary`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary\|Resume Next Action Vocabulary]] | `Purpose And Boundary`, `Token Table`, `Tokens Without An Automated Path`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy\|Escalation Policy]] | `Purpose And Boundary`, `The Kernel Trigger`, `Profile-declared Triggers`, `Firing And Resuming`, `A Trigger Is Not A Gate`, `Control Accretion Decision`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/18 Initial Task Planning Transaction\|Initial Task Planning Transaction]] | `Purpose And Boundary`, `What The Plan Supplies And What It May Never Infer`, `Where The Transaction Stops`, `Guarded Write Protocol`, `Applying It Twice`, `Control Accretion Decision`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery\|Card Context Activation and Read-back Delivery]] | `Purpose And Boundary`, `Frozen Reading Plan`, `Card Activation Bundle`, `Execution-context Delivery`, `Budgeted Piece Delivery`, `Frozen Review Plan`, `Progressive Read-back`, `Resume Reassignment And Failure`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate\|Assignment State and Delivery Gate]] | `Purpose And Boundary`, `Why This Is A Separate Gate`, `Assignment Record`, `Delivery States`, `Attempt Invalidation`, `What This Gate Does Not Prove`, `Related` |

## Applicable Read Sets

- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]]
- [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]]
- [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]]
- [[kernel/Read Sets/R09 Standards Governance Read Set|Standards Governance]]
- [[kernel/Read Sets/R10 Maintenance Run Read Set|Maintenance Run]]
- [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]]

## Related Standards

- [[kernel/K00 Standards Overview|K00 Standards Overview]]
- [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
