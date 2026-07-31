## Purpose

本页是 Note Types and Ownership 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[Knowledge Base Standards/03 Note Types and Ownership/01 Note Type Catalog\|Note Type Catalog]] | `Purpose`、`Note Types`、`Type And Depth Fit` |
| [[Knowledge Base Standards/03 Note Types and Ownership/02 Ownership and Canonical Notes\|Ownership and Canonical Notes]] | `Ownership Rules`、`Canonical Note Rules` |
| [[Knowledge Base Standards/03 Note Types and Ownership/03 Split and Duplication Policy\|Split and Duplication Policy]] | `Purpose`、`When To Split A Note`、`When Not To Split`、`Duplication Policy`、`Retirement`、`Merge`、`Downgrade And Subtree Deprecation`、`Related` |

## Post-migration Extensions（迁移后扩展）

下列章节是在拆分完成后经用户明确 governance instruction 新增的规则，不属于 v1.1 的 `195` 个原始 H2 blocks，因此不改变 `195 / 195` 内容守恒计数：

| Version | New section | Canonical module | Responsibility |
|---|---|---|---|
| `1.8` | `Retirement`、`Merge`、`Downgrade And Subtree Deprecation` | [[Knowledge Base Standards/03 Note Types and Ownership/03 Split and Duplication Policy\|Split and Duplication Policy]] | 退役与合并工作流；模块职责已扩展为 Split Merge and Retirement Policy，文件名保持不变以避免断链 |

## Applicable Read Sets

- [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]
- [[Knowledge Base Standards/Read Sets/03 Module Build Read Set|Module Build]]
- [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]
- [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]

## Related Standards

- [[Knowledge Base Standards/11 Interview Content Standard|11 Interview Content Standard]]
- [[Knowledge Base Standards/04 Content Depth Standard|04 Content Depth Standard]]
- [[Knowledge Base Standards/05 Terminology Standard|05 Terminology Standard]]
- [[Knowledge Base Standards/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]]
- [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
