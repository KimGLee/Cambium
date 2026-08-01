## Purpose

用于批量移动、重命名、拆分、合并或重构目录，同时保护用户修改、canonical ownership、incoming links 和恢复边界。

## Start

先读取 [[Knowledge Base Standards/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]，再读取：

- [[Knowledge Base Standards/02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]]
- [[Knowledge Base Standards/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[Knowledge Base Standards/02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]]
- [[kernel/01 Scope and Architecture/04 Folder and Shared Ownership|Folder and Shared Ownership]]
- [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
- [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]
- [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- [[kernel/09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]]

迁移前必须建立 source path、target path、incoming links、heading anchors、content owner 和 rollback boundary 清单。迁移批次必须独占执行，不与其它批次并发（[[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches）。

## Triggered

- 多批次迁移：组合 [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]。
- 内容 owner 同时变化：读取 [[kernel/03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]]。
- Standards 本身变化：组合 [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set|Standards Governance]]。

## Gate

- [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]
- [[Knowledge Base Standards/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]

## Related

- [[Knowledge Base Standards/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|Build Execution]]
- [[kernel/09 Wiki Link and Navigation Standard|Wiki Link and Navigation]]

