## Purpose

本页是 Terminology 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[Knowledge Base Standards/05 Terminology/01 Terminology Extraction\|Terminology Extraction]] | `Purpose`、`Core Rule`、`Extraction Criteria`、`Do Not Extract`、`Source-discovered Terminology` |
| [[Knowledge Base Standards/05 Terminology/02 Ownership and Term Structure\|Ownership and Term Structure]] | `Ownership`、`Suggested Structure`、`Term Note Structure` |
| [[Knowledge Base Standards/05 Terminology/03 Naming Context and Linking\|Naming Context and Linking]] | `Naming And Aliases`、`Contextual Use`、`Display Language Contract（显示语言契约）`、`Link Frequency` |
| [[Knowledge Base Standards/05 Terminology/04 Interview and Acceptance\|Interview and Acceptance]] | `Interview Relationship`、`Interview Preparation`、`Acceptance Criteria`、`Related` |

## Post-migration Extensions（迁移后扩展）

下列章节是在拆分完成后经用户明确 governance instruction 新增的规则，不属于 v1.1 的 `195` 个原始 H2 blocks，因此不改变 `195 / 195` 内容守恒计数：

| Version | New section | Canonical module | Responsibility |
|---|---|---|---|
| `1.5` | `Display Language Contract（显示语言契约）` | [[Knowledge Base Standards/05 Terminology/03 Naming Context and Linking\|Naming Context and Linking]] | 术语显示语言契约：`English Term（中文解释）` 显示顺序、canonical 英文文件名、aliases 与正文显示的边界 |

## Applicable Read Sets

- [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]
- [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]
- [[Knowledge Base Standards/Read Sets/05 Interview Content Read Set|Interview Content]]

## Related Standards

- [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]]
- [[Knowledge Base Standards/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]]
- [[Knowledge Base Standards/11 Interview Content Standard|11 Interview Content Standard]]
- [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
