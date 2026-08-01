## Purpose

This page is the stable entry point of the Build Execution standard. The detailed rules have been split into the modules below by responsibility; the original content has not been reduced.

## Reading Rule

- First use this MOC to locate the rule owner, then read the modules required by the current task, event, or quality gate.
- Entering this domain does not require reading all modules at once.
- Each module returns to its parent via `Navigation` and links to the adjacent modules before and after it.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/02 Build Execution/01 Contract Time and Task State\|Contract Time and Task State]] | `Purpose`, `Core Execution Principle`, `Phase 0: Freeze The Contract`, `Time And Stop Semantics`, `Task State Machine` |
| [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]] | `Mid-task Guidance And Contract Amendment` |
| [[kernel/02 Build Execution/03 Inventory and Coverage Reconciliation\|Inventory and Coverage Reconciliation]] | `Phase 1: Inventory`, `Coverage Reconciliation`, `Machine-readable Ledger` |
| [[kernel/02 Build Execution/04 Architecture Samples and Dependency Build\|Architecture Samples and Dependency Build]] | `Phase 2: Architecture And Mapping`, `Phase 3: Representative Samples`, `Phase 4: Dependency-ordered Build` |
| [[kernel/02 Build Execution/05 Batch Execution and Progress Ledger\|Batch Execution and Progress Ledger]] | `Batch Policy`, `Concurrent Batches`, `Source-driven Expansion Batch`, `Progress Ledger`, `Machine-readable Ledger` |
| [[kernel/02 Build Execution/06 Existing Changes Migration and Resume\|Existing Changes Migration and Resume]] | `Existing Changes`, `Migration Safety`, `Interruption And Resume` |
| [[kernel/02 Build Execution/07 Completion and Handoff\|Completion and Handoff]] | `Completion Policy`, `Final Handoff`, `Related` |

## Applicable Read Sets

- [[kernel/Read Sets/03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]
- [[kernel/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]
- [[kernel/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]
- [[kernel/Read Sets/09 Standards Governance Read Set|Standards Governance]]

## Related Standards

- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]]
- [[kernel/00 Standards Overview|00 Standards Overview]]
- [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]]
