## Purpose

本页是 Quality Assurance 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review\|Quality Dimensions and Single Note Review]] | `Purpose`、`Quality Dimensions`、`Single Note Review`、`Substantive Correctness Review` |
| [[kernel/12 Quality Assurance/02 Rendering Verification\|Rendering Verification]] | `Rendering Verification Levels` |
| [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review\|Module Coverage and Batch Review]] | `Module Review`、`Coverage Reconciliation Review`、`Batch Review` |
| [[kernel/12 Quality Assurance/04 Guidance and Source Review\|Guidance and Source Review]] | `Guidance Reconciliation Review`、`Source Intake And Promotion Review` |
| [[kernel/12 Quality Assurance/05 Automated and Manual Checks\|Automated and Manual Checks]] | `Automated Checks`、`Domain-specific Checks`、`Manual Checks` |
| [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report\|Completion Terminal Audit and Final Report]] | `Completion Gate`、`Terminal Audit`、`Terminal Findings And Convergence`、`Final Report`、`Related` |
| [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|Audit Evidence Reuse and Invalidation]] | `Purpose`、`Audit Layers`、`Dimension-specific Audit Receipt`、`Reuse Gate`、`Invalidation`、`Content-level Propagation`、`Incremental Audit Planning`、`Batch-close Closed List`、`Incremental By Default`、`Specialized Audit Boundary`、`Terminal Reconciliation Rules`、`Active-task Adoption`、`Related` |
| `Audit Dimension Registry` + `Registered Scan Registry` + `Routing And Gate Registry` | profile-owned QA dimensions、scans 和扩展 gates |

## Post-migration Extensions

已冻结 baseline 的内容守恒分母不因随后登记 extension 而追溯改变。迁移与版本历史不进入 active standard；kernel extension registry 当前为空：

| Extension | Canonical owner | Responsibility |
|---|---|---|

## Applicable Read Sets

- [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]
- [[Knowledge Base Standards/Read Sets/03 Module Build Read Set|Module Build]]
- [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]
- 由所选 profile 的 `Routing And Gate Registry` 注册的 `Expression Layer Read Set`
- [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]
- [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]
- [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]
- [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set|Standards Governance]]

## Related Standards

- [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[kernel/04 Content Depth Standard|04 Content Depth Standard]]
- [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]]
- [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]]
- 所选 profile 的 `Expression Layer Entry`、`Audit Dimension Registry` 与 `Registered Scan Registry`
