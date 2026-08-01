## Purpose

本页是 Metadata and Status 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/08 Metadata and Status/01 Frontmatter and Core Vocabularies\|Frontmatter and Core Vocabularies]] + `Vocabulary Extensions` | `Purpose`、`Frontmatter Schema`、`Type Vocabulary`、`Domain Vocabulary`、`Freshness And Lifecycle Vocabulary` |
| [[kernel/08 Metadata and Status/02 Scope Level Depth and Priority\|Scope Level Depth and Priority]] + `Priority Rubric` + `Vocabulary Extensions` | `Scope`、`Level`、`Depth`、`Priority` |
| [[kernel/08 Metadata and Status/03 Status Axes\|Status Axes]] + `Vocabulary Extensions` | `Status Axes` |
| [[kernel/08 Metadata and Status/04 Evidence and Relationship Metadata\|Evidence and Relationship Metadata]] + `Language Contract` | `Evidence Maturity`、`Prerequisites`、`Aliases` |
| [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata\|Review Source and Migration Metadata]] + `Vocabulary Extensions` | `Review Dates`、`Freshness And Review Due`、`Conditional Source Metadata`、`Migration Rules`、`Related` |

Machine-readable base values 登记在 `kernel/08 Metadata and Status/vocabulary-base.yaml`；所选 profile 只通过 `Vocabulary Extensions` 追加值。Markdown prose 仍是字段语义与行为规则的唯一 owner，machine registries 不复制升级 gate。

## Applicable Read Sets

- [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]
- [[Knowledge Base Standards/Read Sets/03 Module Build Read Set|Module Build]]
- [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]
- [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]

## Related Standards

- [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]]
- [[kernel/04 Content Depth Standard|04 Content Depth Standard]]
- `Expression Layer Entry`（所选 profile 的表达层标准）
- [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]]
