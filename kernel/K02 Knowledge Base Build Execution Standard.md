## Purpose

This page is the stable entry point of the Build Execution standard. The detailed rules have been split into the modules below by responsibility; the original content has not been reduced.

## Reading Rule

- First use this MOC to locate the rule owner, then read the modules required by the current task, event, or quality gate.
- Entering this domain does not require reading all modules at once.
- Each module returns to its parent via `Navigation` and links to the adjacent modules before and after it.

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/K02 Build Execution/01 Contract Time and Task State\|Contract Time and Task State]] | `Purpose`, `Core Execution Principle`, `Phase 0: Freeze The Contract`, `Time And Stop Semantics`, `Task State Machine` |
| [[kernel/K02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]] | `Mid-task Guidance And Contract Amendment` |
| [[kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation\|Inventory and Coverage Reconciliation]] | `Phase 1: Inventory`, `Coverage Reconciliation`, `Machine-readable Ledger` |
| [[kernel/K02 Build Execution/04 Architecture Samples and Dependency Build\|Architecture Samples and Dependency Build]] | `Phase 2: Architecture And Mapping`, `Phase 3: Representative Samples`, `Phase 4: Dependency-ordered Build` |
| [[kernel/K02 Build Execution/05 Batch Execution\|Batch Execution]] | `Batch Policy`, `Concurrent Batches`, `Source-driven Expansion Batch` |
| [[kernel/K02 Build Execution/06 Existing Changes Migration and Resume\|Existing Changes Migration and Resume]] | `Existing Changes`, `Migration Safety`, `Interruption And Resume` |
| [[kernel/K02 Build Execution/07 Completion and Handoff\|Completion and Handoff]] | `Completion Policy`, `Final Handoff`, `Related` |
| [[kernel/K02 Build Execution/08 Progress Ledger\|Progress Ledger]] | `Progress Ledger`, `Machine-readable Ledger` |

## Applicable Read Sets

- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]]
- [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]]
- [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]]
- [[kernel/Read Sets/R09 Standards Governance Read Set|Standards Governance]]

## Related Standards

- [[kernel/K06 Knowledge Intake and Evolution Standard|K06 Knowledge Intake and Evolution Standard]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
- [[kernel/K00 Standards Overview|K00 Standards Overview]]
- [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]]
