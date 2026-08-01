## Navigation

- Parent: [[Knowledge Base Standards/00 Standards Overview|00 Standards Overview]].
- Next: [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]].

## Purpose

`Knowledge Base Standards` 定义整个 Obsidian 知识库的内容、结构、引用、来源、面试拆分和质量验收规则。

这套标准的目标不是增加文件数量，而是保证知识库能够支持：

- 系统学习：知道前置知识、核心机制和后续方向。
- 深度理解：能够解释原因、假设、边界和失败模式。
- 工程实践：能够讨论实现、评估、可靠性、安全和成本。
- 大厂面试：能够提供分层、准确、可追问的中英文回答。
- 长期维护：一个概念只有一个事实来源，内容可以复用和更新。
- 持续演化：能够从官方文章、论文、案例和社区信号中发现知识缺口，并通过证据综合安全扩展知识图谱。

## Operating Role

[[Knowledge Base Standards/00 Standards Overview|00 Standards Overview]] 是整个标准体系的唯一入口和规则路由器。它负责告诉执行者：

- 当前任务必须读取哪些标准。
- 读取标准的先后顺序。
- 哪些约束始终生效。
- 何时可以开始修改知识库。
- 完成前必须经过哪些验收。

总体 Index 不替代细则。长任务不能只读取 `00` 后直接执行，必须按下面的 routing 跳转到对应 Runtime Cards，例外情形回读 Read Sets 和 leaf modules。

## Mandatory Reading Protocol

任何知识库任务开始前，按以下顺序解析规则：

```text
00 Standards Overview
 -> Card Index And Task Runtime Cards
 -> Escalate To Read Sets And Leaf Modules When Required
 -> Inspect Existing Knowledge And Links
 -> Freeze Task Contract And Loaded Set
 -> Execute One Verifiable Batch
 -> Gate Checks And Scripts
```

所有任务从 [[Knowledge Base Standards/Cards/00 Card Index|Card Index]] 进入，读取任务对应的 Runtime Card；Core Bootstrap 约束由 [[Knowledge Base Standards/Cards/01 Core Bootstrap Card|Card 01]] 承载。需要回读原文时，从 [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]] 选择实际任务对应的 Read Set；不得因为任务属于知识库长任务就自动加载 `01`、`02`、`08`、`12` 的全部模块。

长任务必须组合实际内容类型对应的 Card 与 [[Knowledge Base Standards/Cards/07 Long-running Execution Card|Card 07]]；回读原文时组合相应 Read Sets。质量规则在任务开始时通过 Gate 列表进入 contract，在到达对应 checkpoint 时再读取完整 gate procedure。

Task Contract 或 Progress Ledger 必须记录：

- `standards_version`。
- 实际的 loaded set：读取的 Cards 与升级回读的 module paths。
- 使用的 Cards 与 Read Sets。
- 尚未触发但已经登记的 gate modules。
- Standards 或 task scope 变化后的重新解析结果。

## Card-first Reading Mode

默认阅读模式为读取任务对应的 Runtime Card（入口见 [[Knowledge Base Standards/Cards/00 Card Index|Card Index]]），替代全量 Read Set 阅读。Card 是对应 Read Set 的 Start/Triggered/Gate 模块的忠实压缩，覆盖日常任务所需的判定、流程和 Gate 清单。

以下情形必须回读标准原文，不得只依赖卡片：

- 卡片未覆盖当前情形，或对卡片内容存疑。
- 规则争议或规则冲突需要裁决。
- L 档页面的深度规则（完整清单只在原文中维护）。
- Governance 任务：必须通读 RS 09 原文，卡片不可作为修订依据。

Cards 为编译产物，禁止手改。卡片与标准原文冲突时，以标准原文为准，并按 [[Knowledge Base Standards/00 Standards Control/03 Standards Governance|Standards Governance]] 的 Revision Write-back Checklist 触发重新生成。

## Default Read Sets

当前 Read Sets：

- [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]：所有任务共同控制边界。
- [[kernel/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]：单个 canonical note。
- [[kernel/Read Sets/03 Module Build Read Set|Module Build]]：完整知识模块。
- [[kernel/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]：外部来源和社区信号。
- [[profiles/agent-atlas/interview/05 Interview Content Read Set|Interview Content]]：Interview Cards、Roadmap 和 Question Bank。
- [[kernel/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]：移动、重命名、拆分和目录重构。
- [[kernel/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]：batch、checkpoint、resume 和 Terminal Proof。
- [[kernel/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]：质量审查和完成验收。
- [[kernel/Read Sets/09 Standards Governance Read Set|Standards Governance]]：控制面规则或结构变更。
- [[kernel/Read Sets/10 Maintenance Run Read Set|Maintenance Run]]：周期性更新与保鲜，按预算封套消化过期复验、水位线增量与 needs_rereview。

v1.1 原文已归档至 `Archive/`（vault 根目录），不参与任何 routing。
