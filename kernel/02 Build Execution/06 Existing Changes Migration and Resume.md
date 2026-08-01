## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|Batch Execution and Progress Ledger]].
- Next: [[kernel/02 Build Execution/07 Completion and Handoff|Completion and Handoff]].

## Existing Changes

- 默认所有现有修改都属于用户。
- 不回滚与当前任务无关的改动。
- 同一文件存在用户修改时，先理解并在其基础上工作。
- 只有修改使任务无法继续时才请求用户决定。
- 不使用 destructive reset 或批量覆盖策略。

## Migration Safety

移动或拆分文件时：

1. 先识别 canonical target。
2. 盘点 incoming and outgoing links。
3. 创建并验证新页面。
4. 更新引用。
5. 确认内容完整迁移。
6. 再删除重复内容或旧文件。
7. 全库检查由所在批次关闭的 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Batch-close Closed List]] 覆盖。

禁止先删除后补写。

## Interruption And Resume

任务中断前必须把 task state 更新为 `paused` 或 `blocked`，并写入 checkpoint。checkpoint 至少包括：

- 当前 contract、scope、queue、active batches 和 standards version。
- 各 active 批次的状态（`active` / `merge-ready`）、merge 队列、已写出未应用的 delta、已接受成果和未验证修改。
- 最近一次 QA 结果。
- Coverage Ledger 的未完成 Required 项。
- 尚未完成分类、映射或验证的 guidance。
- Last reconciled guidance ID 和 unresolved Amendment Records。
- 修改过的文件。
- 下一个精确动作，而不是模糊的“继续完善”。
- 阻塞原因、已尝试方案和可继续推进的其它工作。

任务中断后应从 Progress Ledger、Coverage Ledger 和当前文件状态恢复，而不是重新开始。

恢复时先检查：

- 用户最新要求是否改变目标。
- 上次状态是 `paused`、`blocked` 还是已经有 Terminal Proof。
- Contract、scope、queue、active batches、Standards versions 和时间语义是否仍有效。
- 各 active 批次是否有未验证改动；`merge-ready` 批次已写出的 delta 由 integrator 恢复后继续串行合并，不重做批内工作。
- 是否出现用户新修改。
- 上次自动检查结果是否仍有效。
- 下一个动作是否仍符合 dependency order。

恢复检查完成后才能把 task state 改回 `active`。
