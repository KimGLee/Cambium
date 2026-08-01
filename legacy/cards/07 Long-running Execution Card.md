---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/07 Long-running Execution Read Set.md
  - 02 Build Execution/01 Contract Time and Task State.md
  - 02 Build Execution/02 Mid-task Guidance and Amendment.md
  - 02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - 02 Build Execution/05 Batch Execution and Progress Ledger.md
  - 02 Build Execution/06 Existing Changes Migration and Resume.md
  - 02 Build Execution/07 Completion and Handoff.md
  - 12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
source_hash: d07c95911790
---
# 07 Long-running Execution Card（长任务执行卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

- Phase 0 冻结 contract（02/01）：目标/排除/ownership、五版本号、`concurrency_cap`（默认 3）、loaded set（Cards＋升级回读）、时间语义。
- 时间语义：minimum_run_until（此前不得主动停，到达≠完成）；checkpoint_at（记录汇报，默认继续）；hard_stop_at（必须停，Gate 未过只能 paused）；completion_gate（与时间无关）。语义不明先澄清。
- task_state 一行版：planned>active>completion-candidate>complete；active<->paused、active<->blocked、completion-candidate>active、任意>cancelled。complete 只能来自有效 Terminal Proof。
- Coverage Ledger（02/03）：每个 in-scope 文件恰好一条记录；Required 未建对象也有记录；未完成项必有 next_batch。

## During（执行中）

批次循环（11 步见 Card 01）：版本自检 > 增量 guidance > 取批 > 写批 > 集成 > 关批前一次 AuditPlan＋增量 QA > 写 delta 入 merge-ready > integrator 串行合并仅确定性动作（apply_delta.py＋封闭清单＋12/03 全局项＋invalidations=0；批内项在 merge-ready 前完成）。清单不相交批次可并发（≤cap，02/05）；迁移批独占；并发批只写自身页面/receipts/delta，全局 Ledger 仅 integrator 写；枢纽页由 integrator 合并后独立小步同步。

Guidance 处理（仅"重要 Guidance"入流程：改目标/范围/验收/优先级/内容判断；状态询问一行 log 不占 guidance_id）：保留原意 > 分类 > 冲突/影响分析 > 裁决 disposition（interrupt-now/apply-to-current-batch/queue-next/queue-by-dependency/research-first/deferred/clarification-required/superseded/not-applicable）> 写 Amendment Log（ID 单调递增）> 安全边界执行 > 验证关闭。不得用 deferred/not-applicable 静默丢弃；最新指令只覆盖同维度冲突项。

双 Ledger 机读更新：canonical 为 YAML（Tools/schemas/ 的 coverage 与 progress 两模板，受限子集语法）；散文视图可选、由 YAML 派生、不作对账依据。

Receipt 复用（12/07）：脚本 --receipts 产 JSONL；复用须过 Reuse Gate（predicate 不变或更弱＋fingerprint 匹配＋无 invalidation），记 reused_receipt_id 与理由；相关变化按维度失效。实质修改机制性章节→按 12/07 标记下游 needs_rereview 入 Ledger。

## Gate（关闭前）

- [ ] 每个 batch 按 12/03 Batch Review 关闭；unresolved_invalidations=0
- [ ] 中断前置 paused/blocked＋完整 checkpoint（下一精确动作，非"继续完善"）
- [ ] 恢复协议：直接加载 YAML 双 Ledger（不重读散文），核对目标/契约/时间语义、各批未验证改动与用户新修改后才回 active；merge-ready 批已写出的 delta 由 integrator 继续合并，不重做批内工作
- [ ] completion-candidate 前完成 Coverage Reconciliation；随后走 Card 08

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| guidance 分类与裁决细则 | [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment\|02/02]] |
| receipt/invalidation 细则 | [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|12/07]] |
