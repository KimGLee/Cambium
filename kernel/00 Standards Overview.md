## Purpose

本文件是 active Standards 的唯一总体入口。它只负责状态槽位、任务路由、领域索引和加载协议；详细规则由 folder-based leaf modules 维护。

## Current State

| Field | Value |
|---|---|
| Standards version | `{{standards_version}}`（由 active governance state 提供） |
| Status | `{{standards_status}}`（由 active governance state 提供） |
| Effective date | `{{effective_date}}`（由 active governance state 提供） |
| Domain MOCs | `derived-from-active-kernel-domain-registry` |
| Canonical leaf modules | `derived-from-active-kernel-inventory` |
| Routing model | Runtime Cards（Card-first，由 `Runtime Card Provider` 解析）+ Read Sets 升级回读 + Triggered / Gate Modules |
| Change authority | User's explicit governance instruction |

完整状态规则由 [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]] 维护。

## Start Here

```text
Open Standards Overview
 -> Resolve Card Index And Load Task Cards Through Runtime Card Provider
 -> Escalate To Read Sets And Leaf Modules When Required
 -> Record Standards Version And Loaded Set
 -> Inspect Existing Knowledge And Links
 -> Freeze Task Contract
 -> Execute One Verifiable Batch
 -> Run Gate Checks And Scripts
```

1. 所有任务从所选 profile 注册的 `Runtime Card Provider` 进入，解析 Card Index 与任务对应的 Runtime Card；Core Bootstrap 约束由 provider 注册的 Core Bootstrap Card 承载。
2. 例外情形（卡片未覆盖、规则争议、L 档深度规则、Governance 任务）按 [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|00/01]] 回读 Read Sets 与 leaf modules。
3. 回读时只加载当前事件和当前 gate 所需的 leaf modules。
4. MOC 用于定位，不等于已经读取其中全部规则。
5. Long-running task 必须组合内容 Card 与 `Runtime Card Provider` 解析的 Long-running Execution Card。
6. Completion candidate 必须组合 `Runtime Card Provider` 解析的 Audit and Completion Card；Governance 任务必须通读 [[kernel/Read Sets/09 Standards Governance Read Set|RS 09]] 原文。

Runtime Cards 是各 Read Set 的编译产物（标准原文是源码，卡片是编译产物），由所选 profile 的 `Runtime Card Provider` 注册入口。日常任务卡片优先，例外情形回读原文，详见 [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|00/01]] 的 Card-first Reading Mode。

## Task Router

| Task | Primary route |
|---|---|
| 新建或扩展一个 canonical note | [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] |
| 建设完整知识模块、流程体系或 application system slice | [[kernel/Read Sets/03 Module Build Read Set\|Module Build]] |
| 根据官方文档、论文、代码、案例或社区信息扩展知识 | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]] |
| 创建、迁移或审查表达层内容 | 所选 profile 的 `Routing And Gate Registry` 注册的 `Expression Layer Read Set` |
| 移动、重命名、拆分、合并或目录重构 | [[kernel/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor]] |
| 多 batch、持续执行、checkpoint 或 resume | [[kernel/Read Sets/07 Long-running Execution Read Set\|Long-running Execution]] |
| 审查、Completion Gate 或 Terminal Audit | [[kernel/Read Sets/08 Audit and Completion Read Set\|Audit and Completion]] |
| 修改 Standards、Read Sets、版本或控制面结构 | [[kernel/Read Sets/09 Standards Governance Read Set\|Standards Governance]] |
| 中途 guidance、scope、priority 或 correction | [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]] |

周期性知识库更新与保鲜任务走 Maintenance Run：[[kernel/Read Sets/10 Maintenance Run Read Set|RS 10]]，对应 Runtime Card 由 `Runtime Card Provider` 解析。

详细任务组合和 Pre-execution Gate 位于 [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]。

## Domain Index

| Domain | Stable MOC | Responsibility |
|---|---|---|
| `00` | [[kernel/00 Standards Overview\|Standards Overview]] | 总体 Index、Read Set routing 和 Standards control |
| `01` | [[kernel/01 Scope and Architecture Standard\|Scope and Architecture]] | scope、logical architecture、knowledge spine 和 foundation preservation |
| `02` | [[kernel/02 Knowledge Base Build Execution Standard\|Build Execution]] | task contract、state、guidance、batch、checkpoint、resume 和 handoff |
| `03` | [[kernel/03 Note Types and Ownership Standard\|Note Types and Ownership]] | note type、canonical owner、split 和 duplication |
| `04` | [[kernel/04 Content Depth Standard\|Content Depth]] | concept、flow、system、production、evidence 和 failure depth |
| `05` | [[kernel/05 Terminology Standard\|Terminology]] | term extraction、ownership、aliases、context 和 reuse |
| `06` | [[kernel/06 Knowledge Intake and Evolution Standard\|Knowledge Intake and Evolution]] | source-to-knowledge、claims、promotion 和 evolution |
| `07` | [[kernel/07 Sources and Accuracy Standard\|Sources and Accuracy]] | source authority、evidence role、verification、provenance 和 uncertainty |
| `08` | [[kernel/08 Metadata and Status Standard\|Metadata and Status]] | frontmatter、vocabulary、status axes、evidence 和 migration metadata |
| `09` | [[kernel/09 Wiki Link and Navigation Standard\|Wiki Link and Navigation]] | semantic links、MOC、path、alias、heading 和 graph verification |
| `10` | [[kernel/10 Writing and Formatting Standard\|Writing and Formatting]] | naming、prose、math、tables、code、diagrams、assets 和 rendering；reader-facing language 由 `Language Contract` 提供 |
| `11` | [[kernel/11 Expression Layer Standard\|Expression Layer]] | 表达产物、canonical knowledge separation、readiness 与 migration interface |
| `12` | [[kernel/12 Quality Assurance Standard\|Quality Assurance]] | note、module、batch、source、expression、rendering 和 terminal gates |

## Loading Contract

- `Domain MOC`：说明本领域有哪些 modules、原章节 owner 和适用 Read Sets。
- `Leaf module`：拥有规则正文，是执行时真正需要读取的单位。
- `Read Set`：把任务阶段映射到 leaf modules。
- `Triggered module`：只在 guidance、source、diagram、migration 等条件出现时加载。
- `Gate module`：在 note、batch、module 或 task 关闭前加载。
- `loaded set`：Task Contract 中记录的实际 Runtime Card IDs、`Runtime Card Provider` 解析的 artifacts 与升级回读的 module paths，不得只写宽泛的 `02` 或 `12`。

模块拆分不改变规则优先级。冲突仍按 [[kernel/00 Standards Control/06 Completion Precedence and Task Contract#Standard Precedence|Standard Precedence]] 解决。

## Protected Defaults

- Active Standards 是受保护控制面，只有明确 governance instruction 才能修改。
- 文件夹、文件名、正文语言、identity 保留值和首次术语显示形式由所选 profile 的 `Language Contract` 提供。
- 一个知识对象只有一个 canonical owner；其它页面通过 Wiki links 复用。
- 不回滚、覆盖或删除无法确认来源的用户修改。
- 外部来源必须经过 claim extraction、evidence review 和 promotion decision。
- Mid-task Guidance 必须进入 Amendment Log，不依赖临时上下文。
- 审计结果必须绑定 acceptance predicate、artifact/dependency/contract fingerprints 和 verifier；有效 receipt 可以复用，相关变化必须触发按维度失效。
- Standards 拆分和迁移必须逐块对账，不能借结构调整缩减、摘要或删除规则。
- 渲染验收默认使用源解析和确定性静态验证；interactive UI、截图、视觉模型和录屏必须满足分级升级条件。
- 完成必须通过适用 gates；时间、文件数量和结构检查不能单独证明完成。

完整默认约束位于 [[kernel/00 Standards Control/02 Task Routing and Pre-execution#Default Constraints Snapshot|Default Constraints Snapshot]]。

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]
