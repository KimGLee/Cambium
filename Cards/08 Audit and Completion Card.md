---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/08 Audit and Completion Read Set.md
  - 02 Build Execution/07 Completion and Handoff.md
  - 12 Quality Assurance/06 Completion Terminal Audit and Final Report.md
  - 12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
source_hash: 2d4fac573f9e
---
# 08 Audit and Completion Card（审计与完成卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

- Terminal Audit 只审已满足全部适用 gate 的 completion-candidate；结构检查通过≠完成，correctness/depth/provenance/integration 不可跳过。
- 只读 RS 08＋finding 相关 Read Sets。
- 审计范围由 receipt/fingerprint/invalidation 生成：便宜确定性＝终审快照封闭清单一次；人工只审 changed/invalidated/overdue/抽样（P0/P1 长期由 freshness 兜底）。
- 无 visual trigger 时缺 UI/截图/录屏不判失败。

## During（执行中）

Terminal Audit 11 步（canonical 12/06）：
1 冻结快照，记 versions/guidance_cutoff_id/Read Sets；2 载 Receipt Register，算 changed/invalidated/overdue/legacy；3 Guidance Reconciliation（cutoff 内全有终局 disposition）；4 Coverage Ledger 对账文件系统/exclusions/Required Queue；5 确认全部 batch 已关、merge 队列清空（无 merge-ready 未合并、无未应用 delta）、无未验证修改与 unresolved invalidation；6 最终冻结快照跑封闭清单（12/07）；7 changed/invalidated/overdue 页 note-type-aware 审阅，其余有界抽样＋Reuse Gate 复用；8 查 promotion/interview migration/Overview/Roadmap/Cheat Sheet 同步；9 审 rendering_mode 与 Level 0/1 证据，无 trigger 记 not_applicable；10 系统性问题 family expansion，按下方分级处置；11 生成 receipt reconciliation、Final Handoff、Terminal Proof。
Findings 三级（12/06）：minor 记录不阻断；major 就地修复＋定向重检＋receipt supersede，不重冻结快照、不重跑封闭清单；critical（影响完成谓词）回 active，重入复用未失效 receipts、封闭清单只重跑一次。两轮上限：第 2 轮只确认第 1 轮关闭；超轮升级用户。未闭环项入 Required Queue；不得改措辞绕过。

- Terminal Proof 28 字段：按 Tools/schemas/terminal_proof.template.yaml 填，check_proof.py 校验（owner 12/06）。
- 零值条件：guidance 三个未决计数=0 ∧ required_authoring_gaps=0 ∧ unverified_batches=0（含 merge-ready 未合并批）∧ unresolved_invalidations=0 ∧ 全部适用 gate 通过，才能 complete。
- Invalidation 处理（12/07）：direct（内容/predicate/verifier/review_due 到期/新证据/correction）与 dependency（只传播依赖维度）；unresolved 项须重验、supersede 或经授权改 disposition。

## Gate（关闭前）

- [ ] check_proof.py pass；零值条件全部成立
- [ ] Final Report 要点齐：文件增改、达到状态、自动检查结果、缺口与原因、时效性未验证结论、guidance 处置、rendering level/trigger、receipt 复用/失效/抽样；附 Amendment Log 摘要、Coverage 汇总、Terminal Proof、deferred/evidence backlog
- [ ] 不因 token/文件数/时间到达宣告完成（02/07）

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| Reuse Gate/失效传播细则 | [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|12/07]] |
| Terminal Proof 字段语义 | [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report\|12/06]] |
| 渲染例外升级 | [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification\|12/02]] |
