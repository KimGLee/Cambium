---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/10 Maintenance Run Read Set.md
  - 00 Standards Control/02 Task Routing and Pre-execution.md
  - 00 Standards Control/06 Completion Precedence and Task Contract.md
  - 02 Build Execution/05 Batch Execution and Progress Ledger.md
  - 03 Note Types and Ownership/03 Split and Duplication Policy.md
  - 06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline.md
  - 08 Metadata and Status/05 Review Source and Migration Metadata.md
  - 12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
  - 12 Quality Assurance/03 Module Coverage and Batch Review.md
  - 12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
source_hash: 6fcca29ac5e2
---
# 10 Maintenance Run Card（维护轮执行卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

- 跑 `Tools/check_freshness.py` 得过期/待首验清单；读 `Tools/state/watermark.yaml` 得增量范围；合并 Coverage Ledger 的 `needs_rereview` 标记；合并 candidates 池（duplicate/vocab/language；duplicate_check 本层跑，全库或 `--scope`）。
- 四源并集按 priority 排序（P0 前）。候选 3 轮未被选中→降级 log-only，再命中重新入池。
- 轮开始输出 deferred 年龄分布；滞留超 3 轮显式处置：降级/退役/记录理由（owner 00/02）。
- 声明预算封套三选一（N 页/N 批次/N 小时）并按其截断清单；截掉项记 Ledger deferred，不构成缺口。停点＝批次边界。
- 每页判 tier（S/M/L，争议上调）。

## During（执行中）

- 过期页复验：必答"该主题今天是否仍配当前 priority"；升降级记 Ledger＋理由。
- 新材料走 06/03 增量 Stage 1 起的 pipeline（组合 Card 04）；只扫水位线后新材料，全量重扫须记理由。
- 退役/合并候选走 03/03：确认重复后合并义务优先，仅物理删除需 governance 授权；先盘入链逐条改指接替页（check_links），再 tombstone＋`lifecycle: retired`＋`superseded_by`；高入度退役改指按"改指数÷6"折算入本轮预算（00/02）。
- L 档产出走独立实质正确性复核（12/01：独立第二 agent，仅输入正文与 Sources，产 substantive_review receipt）。

## Gate（关闭前）

- [ ] 批次关闭：封闭清单（12/07，七项，含 check_vocab 全库），按 12/03 Batch Review 验收（freshness/duplicate 不入批次）
- [ ] 批次关闭时推进双 Ledger 与 `Tools/state/watermark.yaml`
- [ ] 本轮清单关闭＝完成：Maintenance Completion（00/06）有界语义，不做全库 Terminal Proof
- [ ] deferred 项移交下一轮维护清单

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| 预算/封套 | [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution\|00/02]] |
| 保质期/volatility | [[Knowledge Base Standards/08 Metadata and Status/05 Review Source and Migration Metadata\|08/05]] |
| 水位线 | [[Knowledge Base Standards/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline\|06/03]] |
| needs_rereview 传播 | [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|12/07]] |
| 退役/合并 | [[Knowledge Base Standards/03 Note Types and Ownership/03 Split and Duplication Policy\|03/03]] |
| 实质复核 | [[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review\|12/01]] |
| 完成语义 | [[Knowledge Base Standards/00 Standards Control/06 Completion Precedence and Task Contract\|00/06]] |
