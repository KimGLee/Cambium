## Purpose

Read Set 把一个任务映射到需要读取的具体 Standards modules。它解决的是加载边界，不替代任何规则正文。

每个 Read Set 有对应的 Runtime Card（[[Knowledge Base Standards/Cards/00 Card Index|Card Index]]），默认卡片优先；本索引与 Read Sets 用于例外回读、L 档与 Governance 任务。

## Resolution Order

```text
Open Standards Overview
 -> Load Core Bootstrap
 -> Classify Task
 -> Select One Or More Task Read Sets
 -> Resolve Triggered Modules
 -> Record Loaded Module Paths And Standards Version
 -> Execute
 -> Load Gate Modules At The Required Checkpoint
```

一个任务可以组合多个 Read Sets。例如，根据 OpenAI 文章扩展 Agent Cache，同时建立 Interview Cards，需要组合 Source-driven Expansion、Module Build 和 Interview Content。

## Read Set Index

| Read Set | Use |
|---|---|
| [[Knowledge Base Standards/Read Sets/01 Core Bootstrap Read Set\|Core Bootstrap]] | 所有知识库任务的共同控制约束 |
| [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] | 新建或定向扩展一个 canonical note |
| [[Knowledge Base Standards/Read Sets/03 Module Build Read Set\|Module Build]] | 建设一个包含 MOC、leaf pages 和跨模块关系的完整知识模块 |
| [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]] | 根据官方文档、论文、社区信号、案例或用户 source lead 扩展知识 |
| [[Knowledge Base Standards/Read Sets/05 Interview Content Read Set\|Interview Content]] | 创建、迁移或审查 Interview Cards、Roadmap 和 Question Bank |
| [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor]] | 批量移动、重命名、拆分、合并或重构目录 |
| [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set\|Long-running Execution]] | 需要 contract、batch、checkpoint、resume 和持续状态管理的长任务 |
| [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set\|Audit and Completion]] | 执行质量审查、Completion Gate 和 Terminal Audit |
| [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set\|Standards Governance]] | 修改 Standards、Read Sets、规则版本或控制面结构 |
| [[Knowledge Base Standards/Read Sets/10 Maintenance Run Read Set\|Maintenance Run]] | 周期性知识库更新与保鲜：预算封套内消化过期复验、水位线增量与 needs_rereview |

## Selection Rules

- 每次任务都从 Core Bootstrap 开始，但 Core Bootstrap 不能代替任务专属规则。
- Read Set 中的 `Start` modules 在对应工作开始前读取。
- `Triggered` modules 只有在触发条件出现时加载。
- `Gate` modules 在关闭 note、batch、module 或 task 前加载。
- 模块的前置依赖优先于当前模块；无法满足依赖时，先记录 gap。
- Standards version 或模块路径变化后，受影响的 loaded set 必须重新解析。
- Task Contract 或 Progress Ledger 应记录实际读取的 module paths，而不是只记录一个宽泛的 Standard 编号。

## Related

- [[Knowledge Base Standards/00 Standards Overview|Standards Overview]]
- [[Knowledge Base Standards/00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]
