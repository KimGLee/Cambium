## Purpose

本页是 Scope and Architecture 标准的稳定入口。详细规则已经按职责拆分到下列模块，原始内容没有缩减。

## Reading Rule

- 先用本 MOC 定位规则 owner，再读取当前任务、事件或质量门需要的模块。
- 不要求因为进入本领域就一次性读取全部模块。
- 每个模块通过 `Navigation` 返回父级，并连接前后相邻模块。

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/01 Scope and Architecture/01 Scope Boundaries\|Scope Boundaries]] | `Purpose`、`Profile Scope Interface` |
| [[kernel/01 Scope and Architecture/02 Logical Architecture and Knowledge Spine\|Logical Architecture and Knowledge Spine]] | `Logical Architecture`、`Knowledge Spine` |
| [[kernel/01 Scope and Architecture/03 Foundation Preservation\|Foundation Preservation]] | `Foundation Preservation Rule` |
| [[kernel/01 Scope and Architecture/04 Folder and Shared Ownership\|Folder and Shared Ownership]] | `Physical Folder Policy`、`Shared Ownership Rule`、`Architecture Anti-patterns`、`Related` |

完整生效时还必须加载所选 profile 注册的 `Profile Scope`，由它提供具体目标、逻辑层、knowledge spine、基础层目录、共享层名和排除清单。

## Applicable Read Sets

- [[kernel/Read Sets/03 Module Build Read Set|Module Build]]
- [[kernel/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]

## Related Standards

- [[kernel/04 Content Depth Standard|04 Content Depth Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- 所选 profile 注册的 `Expression Layer Entry`
- [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]]
- [[kernel/05 Terminology Standard|05 Terminology Standard]]
