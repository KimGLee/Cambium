## Navigation

- Parent: [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]].
- Previous: [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]].
- Next: [[kernel/09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]].

## Overview And MOC

每个顶层领域至少需要：

- Overview：领域边界、核心模块和关系。
- Sequence view：学习或执行顺序，由所选 profile 的路由机制绑定具体实现。
- Coverage map：已覆盖、缺失和优先级。

Overview 不是文件列表，应解释模块之间的依赖和职责。

Coverage map 是 [[kernel/02 Build Execution/03 Inventory and Coverage Reconciliation#Phase 1: Inventory|Coverage Ledger]] 的读者视图，不独立维护另一套完成状态。页面有 incoming link、sequence-view entry 或可解析 Wiki link，只能证明可导航，不能证明 authoring、profile readiness 或 evidence 状态已经完成。

## Related Section

`Related` 用于补充邻近页面，不承担正文中的因果和依赖说明。

Related links 应按语义组织，避免无序堆积。内容多时可以拆为：

- Prerequisites
- Components
- Alternatives
- Applications
- Evidence And Sources
- Supersedes / Superseded By
- Expression Layer

## Link Creation Policy

- 需要引用的 canonical page 已存在时直接链接。
- 需要新页面时必须同时创建足够内容，不能只制造 unresolved link。
- 大批量创建前先检查是否已有同义页面。
- 名词提取遵循 [[kernel/05 Terminology Standard|Terminology Standard]]。
- 外部来源触发的新链接和页面遵循 [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]。
- 一篇文章不能仅因包含多个名词就与所有名词建立弱连接；只链接实际受其 claim 影响的知识对象。
