---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/01 Core Bootstrap Read Set.md
  - 00 Standards Overview.md
  - 00 Standards Control/02 Task Routing and Pre-execution.md
  - 00 Standards Control/04 Control State and Scope.md
  - 00 Standards Control/05 Core Principles and Standards Map.md
  - 00 Standards Control/06 Completion Precedence and Task Contract.md
source_hash: f3a02e84157f
---
# 01 Core Bootstrap Card（核心引导卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

任务路由（无卡任务读原 Read Set）：

| 任务类型 | Read Set | Card |
|---|---|---|
| 单页新建/重写/补全 | RS 02 | 02 |
| 模块建设/系统扩展 | RS 03 | 03 |
| 来源驱动扩展 | RS 04 | 04 |
| 面试内容 | RS 05 | 05 |
| 迁移/重构 | RS 06 | [[Knowledge Base Standards/Cards/06 Migration and Refactor Card\|06]] |
| 长任务续跑/checkpoint | RS 07＋内容 RS | [[Knowledge Base Standards/Cards/07 Long-running Execution Card\|07]] |
| 审计/完成验收 | RS 08＋finding 相关 RS | [[Knowledge Base Standards/Cards/08 Audit and Completion Card\|08]] |
| 修改 Standards/控制面 | RS 09 | [[Knowledge Base Standards/Cards/09 Standards Governance Card\|09]]（必须通读原文，卡仅导航） |
| 维护轮/保鲜 | RS 10 | [[Knowledge Base Standards/Cards/10 Maintenance Run Card\|10]] |

Protected Defaults：
- `Knowledge Base Standards` 仅 governance 授权可改；`Python Algorithm Agent Training` 排除。
- 文件名只用英文；正文中文解释；双语只写 `English（中文）`。
- 一个知识对象一个 owner，共享定义走 wiki link。
- 不回滚来源不明的用户修改；外部来源必过 claim→review→promotion。
- Guidance 必入 Amendment Log；不建空壳页、红链、两三句 P0/P1 页。
- 渲染 deterministic-first；视觉须升级条件。

完成优先级：用户最新明确指令 > 知识 ownership 与事实正确 > 安全与数据完整 > 本标准 > 局部风格；新指令只覆盖同维度冲突项。

Pre-execution Gate（10 条全过才可大批量修改）：
- [ ] 已读 00＋Core Bootstrap
- [ ] 已解析 Read Sets/triggered/gate modules
- [ ] 已记录 contract/scope/queue/batch、standards version、loaded set（Cards＋升级回读）、排除与最新要求
- [ ] 已定 minimum_run_until/checkpoint_at/hard_stop_at/Completion Gate，缺省留空
- [ ] Coverage Ledger 已建并对账文件系统与 exclusions
- [ ] 已盘点 ownership/incoming links/用户修改/Required Queue
- [ ] 已识别基础依赖，不塞进 Agent/Harness 页
- [ ] 来源任务已建 source inventory＋claim 方案
- [ ] 已定本批完成条件、rendering_mode、确定性命令、视觉 trigger
- [ ] 已载 Audit Receipt Register，分可复用/失效证据；不建 AuditPlan（关批前一次）

## During（执行中）

Batch 循环 11 步（压缩自 00/02）：1 版本自检（delta→增量 adoption；无则一行 receipt）；2 对账增量 guidance（仅 `last_reconciled_guidance_id` 之后）；3 取 Required Queue 下一批；4 定 type/owner/目标状态；5 补前置缺口；6 收集分类来源；7 写完整一批；8 集成链接/metadata/sources/interview；9 关批前一次 AuditPlan＋批内项＋增量 QA，产分维度 receipts，写 delta 入 merge-ready；10 integrator 串行合并：apply_delta＋封闭清单（12/07）＋12/03 全局项＋更新全局 Ledger；11 Batch Review＋invalidations=0 才关批，否则保持 active/merge-ready。批开始不做对账。

五状态轴独立、不得互替：task_state/authoring_status/interview_status/evidence_maturity/learning_status；coverage_disposition 另记。

## Gate（关闭前）

- [ ] missing=0、ambiguous=0：终审快照封闭清单证明
- [ ] Guidance reconciliation 三计数＝0（unclassified/accepted-unmapped/implemented-unverified）
- [ ] Required gaps 全关或用户改 disposition；无未验证 batch
- [ ] unresolved_invalidations=0；适用 gates 全过
- [ ] 达 minimum_run_until 且未违反 hard_stop_at；Final Handoff 已写
- [ ] Terminal Proof：跑 `Tools/check_proof.py`

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| 规则冲突/优先级 | [[Knowledge Base Standards/00 Standards Control/06 Completion Precedence and Task Contract\|00/06]] |
| guidance/scope 变化 | [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment\|02/02]] |
| task_complete 公式 | [[Knowledge Base Standards/02 Build Execution/07 Completion and Handoff\|02/07]] |
| Terminal Audit 流程 | [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report\|12/06]] |
| 审计证据复用/失效 | [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|12/07]] |
| 迁移/重构 | [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set\|RS 06]] |
| 改 Standards | [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set\|RS 09]] |
