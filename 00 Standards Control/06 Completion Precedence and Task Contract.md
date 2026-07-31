## Navigation

- Parent: [[Knowledge Base Standards/00 Standards Overview|00 Standards Overview]].
- Previous: [[Knowledge Base Standards/00 Standards Control/05 Core Principles and Standards Map|Core Principles and Standards Map]].

## Definition Of Complete

一个模块只有同时满足以下条件才算完成：

- 主题覆盖符合 competency matrix，而不是只覆盖用户最先列出的名词。
- 基础知识与 Agent/Harness 主线之间的 prerequisite chain 连续，基础页面没有因架构调整而被降级为空壳。
- 核心概念达到规定深度，并有前置、子概念、应用和失败模式链接。
- 专有名词已经 canonicalize，没有重复定义。
- 重要页面有例子、评估方法、工程考虑和可靠来源。
- 面试内容已经进入独立 Interview Cards，并反向链接知识页。
- Overview、Roadmap、Cheat Sheet 和 Question Bank 已同步。
- Wiki links 达到 `missing=0`、`ambiguous=0`。
- Markdown、表格、公式、图片和 graph 配置均可正常使用。
- 来源驱动的新知识保留 claim-level provenance，并通过 canonical promotion gate。

一个长任务只有同时满足以下条件才算完成：

- Coverage Ledger 已与文件系统、scope、exclusions 和 competency matrix 对账。
- Amendment Log 已覆盖所有 cutoff 内 guidance，不存在未分类、accepted-but-unmapped 或 implemented-but-unverified 项。
- 所有 Required authoring gaps 已关闭，或者用户明确修改了 disposition。
- 没有未验证 batch 或遗留修改。
- 没有仍处于 direct、dependency、overdue 或 systemic `unresolved_invalidations` 的 Required 审计证据。
- 所有适用的 Single Note、Batch、Module、Interview、Source Promotion 和 Rendering gates 已通过。
- 已达到 `minimum_run_until`，且没有违反 `hard_stop_at`。
- 已写 Final Handoff，明确 optional、deferred 和 external evidence backlog。
- Terminal Audit 已产生 Terminal Proof。

task_complete 的机器可校验公式的 canonical 定义位于 [[Knowledge Base Standards/02 Build Execution/07 Completion and Handoff|Completion and Handoff]] 的 Completion Policy 一节。

Authoring completion 不要求所有前沿结论达到 `validated`；但不能用外部证据缺口掩盖未完成的正文、来源、面试迁移或 QA。

## Maintenance Completion

完成语义分为两种，任务 contract 冻结时必须声明其一，两种语义不得混用：

- Build completion：现有闭环语义，按本页 Definition Of Complete 执行，Terminal Proof 适用。
- Maintenance completion：有界语义，同时满足以下条件即完成：
  - 本轮预算封套内的候选清单已关闭（封套定义见 [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]] 的 Maintenance Run Envelope）。
  - Ledger 与 `Tools/state/watermark.yaml` 已推进。
  - 各批次通过适用的 QA gates。

Maintenance completion 不要求全库 Terminal Proof；预算截掉的 deferred 项由下一轮维护消化，不构成缺口。

## Standard Precedence

当规则冲突时，按以下优先级处理：

```text
User's latest explicit instruction
 -> Knowledge ownership and factual correctness
 -> Safety and data integrity
 -> These knowledge base standards
 -> Existing local style
```

`User's latest explicit instruction` 采用 incremental amendment 语义：只覆盖同一维度中冲突的旧要求，不自动删除其它 scope、acceptance、safety、quality 或时间约束。用户对当前 task 的目标和优先级具有 authority；用户提出的技术判断仍需按 Sources 和 evidence maturity 验证。

## Task Contract Decisions

每个超长任务只需确认会改变默认值的事项：

- Objective、contract version、scope version、queue revision、in-scope domains 和 exclusions。
- Standards version、selected Cards 与 Read Sets、实际 loaded set（Cards 与升级回读的 module paths）和尚未触发的 gate 项；内容任务默认冻结。
- P0 / P1 的目标 authoring 和 interview status。
- `minimum_run_until`、`checkpoint_at`、`hard_stop_at`。
- Required、optional、deferred 和 excluded 的边界。
- 当前任务是否包含 Frontmatter migration、目录迁移或全局 UI / graph 配置。
- 时效性来源的 review window 和允许保留的 external evidence backlog。
- Mid-task guidance 的默认 acknowledgement、safe switching 和 amendment policy；未特别说明时采用 `02` 默认值。
- Audit Receipt Register 的存储位置、legacy-evidence adoption 和任何改变默认 invalidation/review policy 的决定。

没有改变默认值时，不重复讨论已经 approved 的目录、source-to-knowledge、双语 Interview Card 和 Agent/Harness logical center。

## Related

- [[Knowledge Base Standards/12 Quality Assurance Standard|Quality Assurance Standard]]
- [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|Knowledge Base Build Execution Standard]]
