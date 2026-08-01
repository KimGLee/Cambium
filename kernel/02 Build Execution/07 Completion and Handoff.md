## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]].

## Completion Policy

不能因为以下原因提前宣告完成：

- Token 或上下文消耗较大。
- 已创建大量文件。
- profile-registered planning artifact 中大部分 checkbox 已存在。
- 自动链接检查通过。
- 任务执行时间较长。
- 达到 `minimum_run_until` 或某个 checkpoint。
- Progress Ledger 暂时没有 active batch。
- 大部分页面已经是 `reviewed`。

任务只能从 `active` 进入 `completion-candidate`，完成 [[kernel/12 Quality Assurance Standard|Quality Assurance Standard]] 的 Terminal Audit 后才能进入 `complete`。

Terminal Audit 的 canonical procedure 位于 [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report#Terminal Audit|Terminal Audit]]。

Terminal Proof 至少证明：

```text
scope_reconciled
AND guidance_reconciled
AND required_authoring_gaps = 0
AND unverified_batches = 0
AND unresolved_invalidations = 0
AND required_QA_passed
AND final_handoff_written
AND time_contract_satisfied
```

其中：

- `scope_reconciled`：Coverage Ledger 与文件系统、scope 和 exclusions 对账。
- `guidance_reconciled`：所有 accepted guidance 已映射、验证、明确延期或被后续 guidance 取代，不存在未分类、accepted-but-unmapped 或 implemented-but-unverified 项。
- `required_authoring_gaps = 0`：所有 Required 页面达到目标 authoring 状态，或经过明确授权改变 disposition。
- `unverified_batches = 0`：不存在只写入但未验收的批次。
- `unresolved_invalidations = 0`：所有因内容、依赖、contract、Standards、review due 或系统性问题失效的 Required receipts 已重验、supersede 或经授权改变 disposition。
- `required_QA_passed`：Single Note、Module、Expression Layer、Source Promotion 和 Rendering gates 按适用范围通过；Expression Layer gate 由 `Routing And Gate Registry` 绑定的 profile role 提供。
- `final_handoff_written`：剩余 optional、deferred 和 evidence gaps 已明确。
- `time_contract_satisfied`：若存在 `minimum_run_until`，当前时间已达到；若存在 `hard_stop_at`，没有越过用户要求的停止边界。

Authoring completion 与 evidence closure 分离的 canonical 规则（含四条可执行条件）见 [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|12/06]]；缺正文机制、Sources、Expression Layer migration 或 Required QA 的页面仍是 authoring gap。

用户可以在 Completion Gate 前暂停或取消任务，但该动作不能被报告为完成。

## Final Handoff

最终交付需要说明：

- Task state、scope version 和 standards version。
- Selected Runtime Card IDs 与 Read Sets，以及最终 loaded set（`Runtime Card Provider` 解析的 artifacts 与升级回读的 modules）。
- Contract version、queue revision 和 Amendment Log 摘要。
- 知识架构和范围。
- 完成模块及成熟度。
- 新增和迁移内容。
- Source Notes、Research Synthesis 和 canonical promotions。
- `Expression Layer Entry` 输出的 coverage 与 readiness，并引用 `Routing And Gate Registry` 绑定的 profile expression gate role 结果。
- QA 结果。
- Audit Receipt reconciliation：复用、superseded、invalidated、legacy-evidence、抽样和 systemic expansion。
- Coverage Ledger 汇总、Required authoring gaps 和 Terminal Proof。
- Guidance reconciliation 结果和仍处于 deferred / clarification-required 的记录。
- 尚未覆盖的 P1 / P2 内容。
- Optional、deferred 和 external evidence backlog，以及重新进入条件。
- 后续维护方式。

## Related

- [[Knowledge Base Standards/00 Standards Overview|Standards Overview]]
- [[kernel/08 Metadata and Status Standard|Metadata and Status Standard]]
- [[kernel/12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
