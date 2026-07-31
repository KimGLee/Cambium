## Purpose

本页是 Quality Assurance 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review\|Quality Dimensions and Single Note Review]] | `Purpose`、`Quality Dimensions`、`Single Note Review`、`Substantive Correctness Review` |
| [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification\|Rendering Verification]] | `Rendering Verification Levels` |
| [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review\|Module Coverage and Batch Review]] | `Module Review`、`Coverage Reconciliation Review`、`Batch Review` |
| [[Knowledge Base Standards/12 Quality Assurance/04 Guidance Source and Interview Review\|Guidance Source and Interview Review]] | `Guidance Reconciliation Review`、`Source Intake And Promotion Review`、`Interview Review` |
| [[Knowledge Base Standards/12 Quality Assurance/05 Automated and Manual Checks\|Automated and Manual Checks]] | `Automated Checks`、`Domain-specific Checks`、`Manual Checks` |
| [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report\|Completion Terminal Audit and Final Report]] | `Completion Gate`、`Terminal Audit`、`Terminal Findings And Convergence`、`Final Report`、`Related` |
| [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|Audit Evidence Reuse and Invalidation]] | `Purpose`、`Audit Layers`、`Dimension-specific Audit Receipt`、`Reuse Gate`、`Invalidation`、`Content-level Propagation`、`Incremental Audit Planning`、`Batch-close Closed List`、`Incremental By Default`、`Specialized Audit Boundary`、`Terminal Reconciliation Rules`、`Active-task Adoption`、`Related` |

## Post-migration Extensions

下列模块是拆分完成后经用户明确 governance instruction 新增的规则，不属于 v1.1 的 `195` 个原始 H2 blocks，因此不会改变 `195 / 195` 内容守恒计数：

| Version | New module | Responsibility |
|---|---|---|
| `1.4` | [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|Audit Evidence Reuse and Invalidation]] | 分层审计、AuditReceipt、证据复用、失效传播、专项审计边界和增量 Terminal Audit |

## Applicable Read Sets

- [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]
- [[Knowledge Base Standards/Read Sets/03 Module Build Read Set|Module Build]]
- [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]
- [[Knowledge Base Standards/Read Sets/05 Interview Content Read Set|Interview Content]]
- [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]
- [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]
- [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]
- [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set|Standards Governance]]

## Related Standards

- [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[kernel/04 Content Depth Standard|04 Content Depth Standard]]
- [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]]
- [[Knowledge Base Standards/08 Metadata and Status Standard|08 Metadata and Status Standard]]
