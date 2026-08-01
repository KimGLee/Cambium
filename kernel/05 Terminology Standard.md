## Purpose

本页是 Terminology 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/05 Terminology/01 Terminology Extraction\|Terminology Extraction]] | `Purpose`、`Core Rule`、`Extraction Criteria`、`Do Not Extract`、`Source-discovered Terminology` |
| [[kernel/05 Terminology/02 Ownership and Term Structure\|Ownership and Term Structure]] | `Ownership`、`Suggested Structure`、`Term Note Structure` |
| [[kernel/05 Terminology/03 Naming Context and Linking\|Naming Context and Linking]] + `Language Contract` | `Naming And Aliases`、`Contextual Use`、`Link Frequency`；`Display Language Contract（显示语言契约）` 由 profile slot 提供 |
| [[kernel/05 Terminology/04 Terminology Acceptance\|Terminology Acceptance]] + `Expression Layer Entry` | `Acceptance Criteria`、`Related`；术语表达关系由 profile slot 提供 |

## Post-migration Extensions（迁移后扩展）

迁移与版本历史不进入 active standard；扩展登记表当前为空：

| Version | New section | Canonical module | Responsibility |
|---|---|---|---|

## Applicable Read Sets

- [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]
- [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]
- 由所选 profile 的 `Routing And Gate Registry` 注册的 `Expression Layer Read Set`

## Related Standards

- [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]]
- [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]]
- 所选 profile 的 `Expression Layer Entry`
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
