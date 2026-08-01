## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]].
- Next: [[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|Batch Execution and Progress Ledger]].

## Phase 2: Architecture And Mapping

- 建立 Knowledge Base Overview。
- 建立 Competency Matrix。
- 建立 Knowledge Gap Tracker。
- 建立 prerequisite graph。
- 建立所选 profile 的 `Profile Scope` / `Knowledge Spine` 与 foundation dependency mapping。
- 标记重复或 ownership 不清的概念。
- 标记需要 source intake、cross-source synthesis 或重新核验的结论。
- 制定目录迁移表，并通过所选 profile 的 `Runtime Card Provider` 与 `Expression Layer Entry` 角色建立表达产物 mapping。

在 mapping 完成前，不批量删除原内容。

## Phase 3: Representative Samples

先选择不同 note types 的样板。样板类型的具体取值由所选 profile 注册的 `Representative Sample Set` 提供；kernel 只要求该集合覆盖足以检验不同模板行为的代表性类型，不复制 profile 的类型清单。

样板用于验证模板是否过重、过浅或产生重复。用户确认样板后再批量应用。

## Phase 4: Dependency-ordered Build

推荐使用 dependency-ordered vertical slices，而不是先把所有基础写完或直接跳到应用主线。具体流程站名与顺序由所选 profile 的 `Dependency-ordered Build Sequence` 角色提供。

每个 vertical slice 都要从基础机制走到运行时使用、生产链路、评估与表达层输出。完整 foundation coverage 仍在 competency matrix 中持续推进，不能因为主线已经可运行就宣告基础完成。

实际顺序可根据用户优先级调整，但必须记录依赖缺口和补齐批次。

Dependency order 必须从 Coverage Ledger 的 Required Queue 产生。Progress Ledger 至少保留：

- Active batch。
- Ordered Required Queue。
- Optional backlog。
- Deferred items and re-entry conditions。

`Next dependency` 只是 Required Queue 的第一个候选，不能替代完整队列。状态为 `active` 时，不允许长期记录 `In-progress batch: None`；关闭一个 batch 后应先完成 reconciliation，再选择下一个 Required batch。
