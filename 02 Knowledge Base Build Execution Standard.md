## Purpose

本页是 Build Execution 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[Knowledge Base Standards/02 Build Execution/01 Contract Time and Task State\|Contract Time and Task State]] | `Purpose`、`Core Execution Principle`、`Phase 0: Freeze The Contract`、`Time And Stop Semantics`、`Task State Machine` |
| [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]] | `Mid-task Guidance And Contract Amendment` |
| [[Knowledge Base Standards/02 Build Execution/03 Inventory and Coverage Reconciliation\|Inventory and Coverage Reconciliation]] | `Phase 1: Inventory`、`Coverage Reconciliation`、`Machine-readable Ledger` |
| [[Knowledge Base Standards/02 Build Execution/04 Architecture Samples and Dependency Build\|Architecture Samples and Dependency Build]] | `Phase 2: Architecture And Mapping`、`Phase 3: Representative Samples`、`Phase 4: Dependency-ordered Build` |
| [[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger\|Batch Execution and Progress Ledger]] | `Batch Policy`、`Concurrent Batches`、`Source-driven Expansion Batch`、`Progress Ledger`、`Machine-readable Ledger` |
| [[Knowledge Base Standards/02 Build Execution/06 Existing Changes Migration and Resume\|Existing Changes Migration and Resume]] | `Existing Changes`、`Migration Safety`、`Interruption And Resume` |
| [[Knowledge Base Standards/02 Build Execution/07 Completion and Handoff\|Completion and Handoff]] | `Completion Policy`、`Final Handoff`、`Related` |

## Applicable Read Sets

- [[Knowledge Base Standards/Read Sets/03 Module Build Read Set|Module Build]]
- [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]
- [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]
- [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]
- [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set|Standards Governance]]

## Related Standards

- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[Knowledge Base Standards/12 Quality Assurance Standard|12 Quality Assurance Standard]]
- [[Knowledge Base Standards/00 Standards Overview|00 Standards Overview]]
- [[Knowledge Base Standards/08 Metadata and Status Standard|08 Metadata and Status Standard]]
