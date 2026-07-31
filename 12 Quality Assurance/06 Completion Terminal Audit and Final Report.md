## Navigation

- Parent: [[Knowledge Base Standards/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[Knowledge Base Standards/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]].

## Completion Gate

页面升级为 `reviewed` 前必须通过 Single Note Review。

来源驱动的新 canonical page 升级为 `reviewed` 前，还必须通过 Source Intake And Promotion Review。

Batch 关闭前必须通过 Batch Review。

模块宣告完成前必须通过 Module Review。

P0 / P1 topic 的 `interview_status` 升级为 `interview-ready` 前必须通过 Interview Review。

长任务只能在完成 Coverage Reconciliation Review、Guidance Reconciliation Review 和 Terminal Audit 后标记 `complete`。

历史 gate 结果只能通过 [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] 的 Reuse Gate 进入 Terminal Proof；`reviewed`、日期或“此前通过”本身不是可复用证据。

任何一个适用的硬性门槛失败，都必须保持原状态，不得因为任务接近结束、达到时间点、已运行较久或创建大量文件而降低标准。

Authoring completion 不要求所有前沿结论达到 `validated`。无法在当前任务中取得的独立生产数据、跨实现复现或未来监测结果可以进入 evidence backlog，但必须：

- 不影响当前正文对已知机制的完整解释。
- 限制 claim 强度并保留 `evidence_maturity`。
- 记录缺失证据、重新核验条件和受影响页面。
- 不用 evidence backlog 掩盖缺少正文、来源、面试迁移或 QA 的 Required authoring gap。

## Terminal Audit

任务从 `active` 进入 `completion-candidate` 后执行 Terminal Audit：

1. 冻结新增内容，记录 contract、scope、queue、Standards version、`guidance_cutoff_id` 和候选完成状态。
   - 同时记录 selected Cards 与 Read Sets，及 loaded set（Cards 与升级回读的 module paths）。
2. 加载 Audit Receipt Register，计算 changed、directly invalidated、dependency-invalidated、overdue 和 legacy-evidence。
3. 执行 Guidance Reconciliation Review，确认所有 cutoff 以内的 guidance 都有最终 disposition。
4. 将 Coverage Ledger 与文件系统、exclusions、competency matrix 和 Required Queue 对账；若 completion-candidate 冻结前已完成该对账且其后无文件变化，直接复用该结果，不重复执行。
5. 确认所有 batch 已关闭且 merge 队列清空（无 `merge-ready` 未合并批次、无已写出未应用的 delta），没有未验证修改或 unresolved invalidation。
6. 运行 [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] 的 Batch-close Closed List（对最终冻结快照）。
7. 对 changed、invalidated、overdue 与有界抽样对象执行 note-type-aware 内容审阅；其余有效 receipts 按 Reuse Gate 复用。
8. 检查 Source Promotion、Interview migration、Overview / Roadmap / Cheat Sheet 同步；专项 Audit 只证明跨批次 invariant，不无差别重做局部机制审阅。
9. 审核本轮 `rendering_mode`、Level 0 / Level 1 确定性证据；只有存在记录的客观 trigger 时才审核 Level 2–4 UI、截图或录屏证据，并按已确认的系统性影响扩大检查。
10. 对抽样或定向检查发现的系统性问题执行 family expansion；修复与重检按 Terminal Findings And Convergence 分级处置。
11. 生成 receipt reconciliation、Final Handoff 和 Terminal Proof。

终审 findings 按 Terminal Findings And Convergence 分级处置，不因单项 minor 或 major finding 使 task state 整体返回 `active`；未按分级闭环的失败项进入 Required Queue。不能修改报告措辞来绕过失败。

Terminal Proof 至少包含：

```text
scope_version
contract_version
queue_revision
batch_revision
standards_version
selected_read_sets
loaded_module_paths
guidance_cutoff_id
guidance_reconciliation_result
coverage_reconciliation_result
required_authoring_gaps
unverified_batches
automated_QA_result
manual_review_result
rendering_evidence
audit_snapshot_id
audit_receipt_register
reused_receipts
superseded_receipts
invalidated_receipts
unresolved_invalidations
full_deterministic_results
incremental_manual_scope
sampling_scope_and_result
systemic_expansions
deferred_evidence_backlog
final_handoff
time_contract_result
```

只有 guidance 三个未决计数为 0、`required_authoring_gaps = 0`、`unverified_batches = 0`、`unresolved_invalidations = 0` 且所有适用 gate 通过时，task state 才能改为 `complete`。

`full_deterministic_results`：终审对最终冻结快照全量运行的确定性检查的完整结果集引用。`unverified_batches` 计数包含处于 `merge-ready` 但未合并的批次；该值为 0 即要求 merge 队列清空。

`rendering_evidence` 必须说明最高实际级别和验证结果。没有 visual exception trigger 时，记录 `visual_trigger: not_applicable` 即可；缺少 UI、截图或录屏不得因此阻止完成。

## Terminal Findings And Convergence

终审 findings 按 [[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]] 的三级分级处置：

- `minor`：记录，不阻断完成。
- `major`：就地修复＋仅对该对象定向重检＋该对象 receipt supersede；不重新冻结快照、不重跑 Batch-close Closed List。
- `critical`（影响完成谓词）：task state 返回 `active`；重入终审时复用所有未失效 receipts，Batch-close Closed List 只重跑一次。

终审轮次上限为 2：第 2 轮只确认第 1 轮 findings 已关闭，不引入新审查范围；超出轮次上限时升级用户决策。

终审期间收到的 guidance：仅“改变目标、范围或验收”类使终审失效；修正类按 major 就地处理，不整体作废终审；状态询问类不影响 cutoff。分支细则见 [[Knowledge Base Standards/12 Quality Assurance/04 Guidance Source and Interview Review|12/04]] 的 Guidance During Terminal Audit。

## Final Report

每个大批次完成后报告：

- 新建、扩展、移动和删除了哪些文件。
- 哪些内容达到 `authoring_status: drafted / reviewed`，哪些主题达到 `interview_status: interview-ready`。
- 自动检查结果。
- 未完成缺口和原因。
- 是否有未验证的时效性结论。
- 哪些结论仍处于 signal、single-source、contested 或 superseded。
- 下一批依赖和风险。
- 本批接收、应用、排队、延期或 supersede 了哪些 guidance，以及对应版本变化。
- 执行了哪些 rendering level 和确定性验证；若进入 Level 2–4，报告 trigger、unresolved question、最小检查目标、结果和是否触发扩大检查；若未进入，明确 `visual_trigger: not_applicable`。
- 哪些 AuditReceipts 被复用、supersede 或 invalidated，增量人工审阅和抽样覆盖了哪些范围，以及是否触发 systemic expansion。

最终任务报告还必须附 Amendment Log 摘要、Guidance Reconciliation、Coverage Ledger 汇总、Terminal Proof、optional / deferred work 和 external evidence backlog。

## Related

- [[kernel/04 Content Depth Standard|Content Depth Standard]]
- [[Knowledge Base Standards/07 Sources and Accuracy Standard|Sources and Accuracy Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[Knowledge Base Standards/08 Metadata and Status Standard|Metadata and Status Standard]]
- [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|Knowledge Base Build Execution Standard]]
