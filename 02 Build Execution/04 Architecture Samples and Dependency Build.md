## Navigation

- Parent: [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[Knowledge Base Standards/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]].
- Next: [[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger|Batch Execution and Progress Ledger]].

## Phase 2: Architecture And Mapping

- 建立 Knowledge Base Overview。
- 建立 Competency Matrix。
- 建立 Knowledge Gap Tracker。
- 建立 prerequisite graph。
- 建立 Agent/Harness knowledge spine 与 foundation dependency mapping。
- 标记重复或 ownership 不清的概念。
- 标记需要 source intake、cross-source synthesis 或重新核验的结论。
- 制定目录迁移表和 Interview Card mapping。

在 mapping 完成前，不批量删除原内容。

## Phase 3: Representative Samples

先选择不同 note types 的样板：

- 一个数学 / modeling core concept。
- 一个算法。
- 一个深度学习机制。
- 一个 LLM 或 Retrieval 基础机制。
- 一个完整 system design。
- 一个 risk / control note。
- 一个 Source Note 和一个 Research Synthesis。
- 对应 Interview Cards。

样板用于验证模板是否过重、过浅或产生重复。用户确认样板后再批量应用。

## Phase 4: Dependency-ordered Build

推荐使用 dependency-ordered vertical slices，而不是先把所有基础写完或直接跳到 Agent/Harness：

```text
Architecture And Inventory
 -> Required Foundation Batch
 -> Agent / Harness Vertical Slice
 -> Newly Exposed Foundation Gaps
 -> Production Systems Integration
 -> Evaluation / Reliability / Safety
 -> Case Studies And Research Synthesis
 -> Interview Preparation Final Integration
```

每个 vertical slice 都要从基础机制走到 Agent/Harness 使用、生产链路、评估和面试表达。完整 foundation coverage 仍在 competency matrix 中持续推进，不能因为主线已经可运行就宣告基础完成。

实际顺序可根据用户优先级调整，但必须记录依赖缺口和补齐批次。

Dependency order 必须从 Coverage Ledger 的 Required Queue 产生。Progress Ledger 至少保留：

- Active batch。
- Ordered Required Queue。
- Optional backlog。
- Deferred items and re-entry conditions。

`Next dependency` 只是 Required Queue 的第一个候选，不能替代完整队列。状态为 `active` 时，不允许长期记录 `In-progress batch: None`；关闭一个 batch 后应先完成 reconciliation，再选择下一个 Required batch。
