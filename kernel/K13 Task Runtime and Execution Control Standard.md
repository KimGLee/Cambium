## Purpose

This page is the stable entry point of the Task Runtime and Execution Control
standard. Detailed rules are maintained by the responsibility-specific modules
below.

The K13 machine-readable identities, state classes, transition catalogs, and
control-status closed sets are registered once in
[`runtime-state-model.json`](K13%20Task%20Runtime%20and%20Execution%20Control/runtime-state-model.json).
The modules below explain their semantics and invariants without maintaining a
second machine contract.

## Reading Rule

- Use this MOC only to locate the canonical semantic owner. Loading decisions
  are owned outside Kernel; opening this index is not evidence that any leaf was
  loaded.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace\|Runtime State Model and Namespace]] | `Runtime State Namespace`, `Execution Roles`, `Authority Boundary` |
| [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics\|Task Contract Binding and Time Semantics]] | `Purpose`, `Core Execution Principle`, `Phase 0: Freeze The Contract`, `Time And Stop Semantics` |
| [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules\|Task State and Transition Rules]] | `Task State Machine` |
| [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis\|Guidance Classification and Impact Analysis]] | `Mid-task Guidance And Contract Amendment`: cumulative rule, classification, intake, and impact |
| [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching\|Guidance Disposition and Safe Switching]] | `Mid-task Guidance And Contract Amendment` |
| [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning\|Amendment Log and Controlled Replanning]] | `Mid-task Guidance And Contract Amendment` |
| [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract\|Progress Ledger Contract]] | `Progress Ledger`, `Machine-readable Ledger` |
| [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle\|Required Queue Contract and Lifecycle]] | `Purpose And Ownership`, `Queue Document Contract`, `Batch Work Specification Binding`, `Revisions And Fingerprints`, `Batch Lifecycle` |
| [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views\|Queue Compilation Replanning and Views]] | `Purpose And Boundary`, `Queue Materialization`, `Controlled Replanning`, `External Result Contract`, `Derived Human View`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration\|Batch Admission Transitions and Serial Integration]] | `Concurrent Batches`, `Serial Integration`, `Transition Gates` |
| [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy\|Completion Policy]] | `Completion Policy`, `Maintenance Completion Policy` |
| [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings\|Completion Gate Bindings]] | `Completion Gates` |
| [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover\|Interruption Recovery and Rollover]] | `Interruption And Resume` |
| [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction\|Standards Adoption State Transaction]] | `Purpose And Boundary`, `Permitted Transaction`, `External Transaction Contract`, `Resume Boundary`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary\|Resume Next Action Vocabulary]] | `Purpose And Boundary`, `Next-action Invariants`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy\|Escalation Policy]] | `Purpose And Boundary`, `The Kernel Trigger`, `Profile-declared Triggers`, `Firing And Resuming`, `A Trigger Is Not A Gate`, `Authority Boundary`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/18 Initial Task Planning Transaction\|Initial Task Planning Transaction]] | `Purpose And Boundary`, `What The Plan Supplies And What It May Never Infer`, `Where The Transaction Stops`, `External Transaction Contract`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery\|Card Context Activation and Read-back Delivery]] | `Purpose And Boundary`, `Activation Delivery Contract`, `Packaging And Transport Boundary`, `Progressive Read-back`, `Failure And Resume`, `External Result Contract`, `Related` |
| [[kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate\|Assignment State and Delivery Gate]] | `Purpose And Boundary`, `Assignment Contract`, `Delivery States`, `Reading Boundary Scope`, `Attempt Invalidation`, `What This Gate Does Not Prove`, `Related` |

## Related Standards

- [[kernel/K00 Standards Overview|K00 Standards Overview]]
- [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
