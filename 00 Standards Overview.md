## Purpose

本文件是 `Knowledge Base Standards` 的唯一总体入口。它只负责版本状态、任务路由、领域索引和加载协议；详细规则由 folder-based leaf modules 维护。

Standards v1.2 对原 `00–12` 全部内容进行了无删减拆分；v1.3 将视觉识别收紧为有客观触发条件的例外升级；v1.4 增加按维度保存的审计证据、失效传播和增量 Terminal Audit；v1.5 增加独立的中文优先技术语言合同，统一英文 identity 与中文解释的显示顺序；v1.6 执行一致性修复，收敛跨域重复、建立 Cross-domain Rule Registry 与 Revision Write-back Checklist，并补全 Read Set 路由；v1.7 新增编译产物层（Runtime Cards）与确定性检查工具层（Tools/）；v1.8 执行标准语料瘦身并引入增量更新引擎（Maintenance Run 与知识时效检查）；v1.9 将阅读协议现代化为 Card-first 默认与升级回读路径（1.8.1、1.8.2 为治理补丁，见 00/03 Change Summary）；v2.0 执行控制面收敛（一险一闸、闸门词定义、生产限流）；v2.1 引入受控并发（批次并发准入、写入权分区与串行合并）；v2.2 串行区提纯（仅确定性动作）与批次规模分级；v2.3 收尾修订（并发化残留清理与登记回写）。
## Current State

| Field | Value |
|---|---|
| Standards version | `2.3` |
| Status | `approved` |
| Effective date | `2026-07-30` |
| Domain MOCs | `13` |
| Canonical leaf modules | `72` |
| Routing model | Runtime Cards（Card-first）+ Read Sets 升级回读 + Triggered / Gate Modules |
| Change authority | User's explicit governance instruction |

完整版本规则由 [[Knowledge Base Standards/00 Standards Control/03 Standards Governance|Standards Governance]] 维护。

## Start Here

```text
Open Standards Overview
 -> Open Card Index And Load Task Cards
 -> Escalate To Read Sets And Leaf Modules When Required
 -> Record Standards Version And Loaded Set
 -> Inspect Existing Knowledge And Links
 -> Freeze Task Contract
 -> Execute One Verifiable Batch
 -> Run Gate Checks And Scripts
```

1. 所有任务从 [[Knowledge Base Standards/Cards/00 Card Index|Card Index]] 进入，读取任务对应的 Runtime Card；Core Bootstrap 约束由 Card 01 承载。
2. 例外情形（卡片未覆盖、规则争议、L 档深度规则、Governance 任务）按 [[Knowledge Base Standards/00 Standards Control/01 Operating Role and Reading Protocol|00/01]] 回读 Read Sets 与 leaf modules。
3. 回读时只加载当前事件和当前 gate 所需的 leaf modules。
4. MOC 用于定位，不等于已经读取其中全部规则。
5. Long-running task 必须组合内容 Card 与 [[Knowledge Base Standards/Cards/07 Long-running Execution Card|Card 07]]。
6. Completion candidate 必须组合 [[Knowledge Base Standards/Cards/08 Audit and Completion Card|Card 08]]；Governance 任务必须通读 [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set|RS 09]] 原文。

编译产物层：`Cards/` 下的 Runtime Cards 是各 Read Set 的编译产物（标准原文是源码，卡片是编译产物），入口为 [[Knowledge Base Standards/Cards/00 Card Index|Card Index]]。日常任务卡片优先，例外情形回读原文，详见 [[Knowledge Base Standards/00 Standards Control/01 Operating Role and Reading Protocol|00/01]] 的 Card-first Reading Mode。

## Task Router

| Task | Primary route |
|---|---|
| 新建或扩展一个 canonical note | [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] |
| 建设完整知识模块、流程体系或 Agent/Harness system slice | [[Knowledge Base Standards/Read Sets/03 Module Build Read Set\|Module Build]] |
| 根据官方文档、论文、代码、案例或社区信息扩展知识 | [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]] |
| 创建、迁移或审查面试内容 | [[Knowledge Base Standards/Read Sets/05 Interview Content Read Set\|Interview Content]] |
| 移动、重命名、拆分、合并或目录重构 | [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor]] |
| 多 batch、持续执行、checkpoint 或 resume | [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set\|Long-running Execution]] |
| 审查、Completion Gate 或 Terminal Audit | [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set\|Audit and Completion]] |
| 修改 Standards、Read Sets、版本或控制面结构 | [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set\|Standards Governance]] |
| 中途 guidance、scope、priority 或 correction | [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]] |

周期性知识库更新与保鲜任务走 Maintenance Run：[[Knowledge Base Standards/Read Sets/10 Maintenance Run Read Set|RS 10]] / [[Knowledge Base Standards/Cards/10 Maintenance Run Card|Card 10]]。

详细任务组合和 Pre-execution Gate 位于 [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]。

## Domain Index

| Domain | Stable MOC | Responsibility |
|---|---|---|
| `00` | [[Knowledge Base Standards/00 Standards Overview\|Standards Overview]] | 总体 Index、Read Set routing 和 Standards control |
| `01` | [[kernel/01 Scope and Architecture Standard\|Scope and Architecture]] | scope、logical architecture、knowledge spine 和 foundation preservation |
| `02` | [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard\|Build Execution]] | task contract、state、guidance、batch、checkpoint、resume 和 handoff |
| `03` | [[kernel/03 Note Types and Ownership Standard\|Note Types and Ownership]] | note type、canonical owner、split 和 duplication |
| `04` | [[kernel/04 Content Depth Standard\|Content Depth]] | concept、flow、system、production、evidence 和 failure depth |
| `05` | [[kernel/05 Terminology Standard\|Terminology]] | term extraction、ownership、aliases、context 和 reuse |
| `06` | [[kernel/06 Knowledge Intake and Evolution Standard\|Knowledge Intake and Evolution]] | source-to-knowledge、claims、promotion 和 evolution |
| `07` | [[Knowledge Base Standards/07 Sources and Accuracy Standard\|Sources and Accuracy]] | source authority、evidence role、verification、provenance 和 uncertainty |
| `08` | [[Knowledge Base Standards/08 Metadata and Status Standard\|Metadata and Status]] | frontmatter、vocabulary、status axes、evidence 和 migration metadata |
| `09` | [[Knowledge Base Standards/09 Wiki Link and Navigation Standard\|Wiki Link and Navigation]] | semantic links、MOC、path、alias、heading 和 graph verification |
| `10` | [[Knowledge Base Standards/10 Writing and Formatting Standard\|Writing and Formatting]] | language、math、tables、code、diagrams、assets 和 rendering |
| `11` | [[Knowledge Base Standards/11 Interview Content Standard\|Interview Content]] | Interview Cards、answer levels、bilingual、roadmap 和 migration |
| `12` | [[Knowledge Base Standards/12 Quality Assurance Standard\|Quality Assurance]] | note、module、batch、source、interview、rendering 和 terminal gates |

## Loading Contract

- `Domain MOC`：说明本领域有哪些 modules、原章节 owner 和适用 Read Sets。
- `Leaf module`：拥有规则正文，是执行时真正需要读取的单位。
- `Read Set`：把任务阶段映射到 leaf modules。
- `Triggered module`：只在 guidance、source、diagram、migration 等条件出现时加载。
- `Gate module`：在 note、batch、module 或 task 关闭前加载。
- `loaded set`：Task Contract 中记录的实际 Cards 与升级回读的 module paths 及版本，不得只写宽泛的 `02` 或 `12`。

模块拆分不改变规则优先级。冲突仍按 [[Knowledge Base Standards/00 Standards Control/06 Completion Precedence and Task Contract#Standard Precedence|Standard Precedence]] 解决。

## Protected Defaults

- `Python Algorithm Agent Training` 排除在当前知识库建设范围外，除非用户单独授权。
- `Knowledge Base Standards` 是受保护控制面，只有明确 governance instruction 才能修改。
- 文件夹和文件名只使用英语，不添加中文注释；正文用中文完成解释，英文标题和首次术语统一写成 `English（中文）`。
- 一个知识对象只有一个 canonical owner；其它页面通过 Wiki links 复用。
- 不回滚、覆盖或删除无法确认来源的用户修改。
- 外部来源必须经过 claim extraction、evidence review 和 promotion decision。
- Mid-task Guidance 必须进入 Amendment Log，不依赖临时上下文。
- 审计结果必须绑定 acceptance predicate、artifact/dependency/contract fingerprints 和 verifier；有效 receipt 可以复用，相关变化必须触发按维度失效。
- Standards 拆分和迁移必须逐块对账，不能借结构调整缩减、摘要或删除规则。
- 渲染验收默认使用源解析和确定性静态验证；UI、截图、视觉模型和录屏必须满足分级升级条件。
- 完成必须通过适用 gates；时间、文件数量和结构检查不能单独证明完成。

完整默认约束位于 [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution#Default Constraints Snapshot|Default Constraints Snapshot]]。

## Migration Compatibility

原 `01–12` 文件路径仍然存在，现作为 stable domain MOC；vault 内 heading-specific links 必须更新到新的 canonical leaf module。v1.1→v1.2 迁移记录见 [[Knowledge Base Standards/00 Standards Control/07 v1.1 to v1.2 Migration Map|v1.1 to v1.2 Migration Map]]；v1.1 原文已归档至 vault 根目录 `Archive/`，不参与任何 routing。

## Related

- [[Knowledge Base Standards/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[Knowledge Base Standards/00 Standards Control/03 Standards Governance|Standards Governance]]
- [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]
