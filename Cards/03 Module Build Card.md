---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/03 Module Build Read Set.md
  - 01 Scope and Architecture/02 Logical Architecture and Knowledge Spine.md
  - 01 Scope and Architecture/03 Foundation Preservation.md
  - 01 Scope and Architecture/04 Folder and Shared Ownership.md
  - 02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - 02 Build Execution/04 Architecture Samples and Dependency Build.md
  - 02 Build Execution/05 Batch Execution and Progress Ledger.md
  - 12 Quality Assurance/03 Module Coverage and Batch Review.md
  - 12 Quality Assurance/05 Automated and Manual Checks.md
source_hash: bd3ed9ceb0a5
---
# 03 Module Build Card（模块建设卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

流程线：Inventory→Coverage Ledger→架构＋competency matrix→代表性样例（各 type 一个，经用户确认）→依赖有序 vertical slices→批次循环。

- Inventory 排除 `Python Algorithm Agent Training`；无 metadata 旧页默认 `unassessed`。
- Coverage Ledger 字段见 `Tools/schemas/coverage_ledger.template.yaml`（path/type/domain/depth/priority/owner/两 status/disposition/missing/deferred_reason/next_batch/receipt）。每个 in-scope 文件恰一条；Required 未建对象也有记录；可与文件系统对账。
- 主题定位 knowledge spine（九环见 01/02）；归属按"最低合理公共层"。

## During（执行中）

- 依赖序出自 Required Queue：基础批→Agent/Harness slice→新基础缺口→生产集成→评估/安全→案例→面试。
- 缺基础先补 canonical foundation note，不复制进 Agent 页。
- batch＝可独立验收小模块；规模按档位分级（S≤24/M≤10/L≤6）；清单不相交批次可并发（≤`concurrency_cap`，02/05），关批由 integrator 串行合并；每批同步链接、metadata、Sources、Interview、QA，Overview/MOC 由 integrator 合并后同步；禁止只建文件名＋标题关批。
- active 时不允许长期 `In-progress batch: None`；关批后先 reconciliation 再取下一批。
- 目录迁移五条件：ownership 明确、incoming links 盘点、无同名歧义、MOC 同步、链接验证由所在批次 Batch-close Closed List 覆盖。

## Gate（关闭前）

Batch 关闭（清单 owner：12/03）：
- [ ] Required pages 全达目标 authoring_status
- [ ] ownership/Sources/metadata/链接/导航同步
- [ ] interview migration 完成或有明确 disposition
- [ ] Guidance 入 Amendment Log 并映射
- [ ] AuditPlan＋分维度 receipts；unresolved_invalidations=0
- [ ] 双 Ledger 更新；不留未验证修改
- [ ] 批级 gate＝Batch-close Closed List（12/07，七项，含 check_vocab 全库）；note 级仅 check_links、check_vocab `--scope 本页` 自查（不产 receipt）

模块关闭：Overview 反映真实结构；P0/P1 无 unassessed、无未解释概念；prerequisite chain 连续；无重复/orphan；Roadmap/Interview 同步；核心页不薄于边缘页。完整模块关闭组合 RS 08。

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| 来源驱动扩展 | [[Knowledge Base Standards/Read Sets/04 Source-driven Expansion Read Set\|RS 04]] |
| 长任务续跑/checkpoint | [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set\|RS 07]] |
| 模块关闭审计 | [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set\|RS 08]] |
| Progress Ledger 字段 | [[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger\|02/05]] |
| 拆合/重复判断 | [[Knowledge Base Standards/03 Note Types and Ownership/03 Split and Duplication Policy\|03/03]] |
