## Purpose

本页是 Expression Layer 的 kernel 入口。Kernel 只规定表达产物与 canonical knowledge 之间的职责分离、状态隔离、证据绑定、链接、迁移和验收不变量。

具体产物类型、显示名称、组织方式和 readiness vocabulary 由所选 profile 的 `Expression Layer Entry` 注册；kernel 不复制这些 profile 规则。

## Module Index

| Module | Canonical sections |
|---|---|
| [[kernel/11 Expression Layer/01 Expression Architecture and Separation\|Expression Architecture and Separation]] | `Purpose`、`Core Separation`、`Physical Structure` |
| [[kernel/11 Expression Layer/02 Expression Coverage and Readiness\|Expression Coverage and Readiness]] | `Expression Coverage And Readiness` |
| [[kernel/11 Expression Layer/04 Evidence-bound Expression\|Evidence-bound Expression]] | `Canonical Evidence Boundary` |
| [[kernel/11 Expression Layer/05 Expression Knowledge Binding\|Expression Knowledge Binding]] | `Resolvable Binding`、`Bidirectional Knowledge Flow`、`Evidence Maturity Boundary` |
| [[kernel/11 Expression Layer/06 Sequence and Progress Semantics\|Sequence and Progress Semantics]] | `Sequence And Progress Semantics` |
| [[kernel/11 Expression Layer/07 Expression Migration Audit and Acceptance\|Expression Migration Audit and Acceptance]] | `Migration Policy`、`Scoped Migration Audit`、`Candidate-only Automation`、`Acceptance Criteria` |

## Profile Interface

- `Expression Layer Entry` 注册当前 profile 的表达产物、入口和唯一规则 owners。
- Profile 可以增加产物类型、模板、分类和 readiness values，但不能取消本域的职责分离、canonical evidence、状态独立、双向绑定或 create-before-remove 不变量。
- Kernel 只引用 slot 与抽象角色，不直接点名任何 profile 实现。

## Related Standards

- [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]]
- [[kernel/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]]
- [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]]
- [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]]
