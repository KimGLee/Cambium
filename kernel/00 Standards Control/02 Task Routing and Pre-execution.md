## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]].
- Next: [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]].

## Task Routing Table

所有任务先加载 [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]，再按下表组合 task-specific Read Sets 或 event modules。

| Task | Required Read Set Or Module | Main Decision |
|---|---|---|
| 新建或定向扩展一个概念页 | [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] | note type、owner、depth、sources、links 和 note gate |
| 新建流程页、系统页或完整模块 | [[kernel/Read Sets/03 Module Build Read Set\|Module Build]] | logical placement、foundation、dependency order、MOC 和 module gate |
| 根据官方厂商资料、论文、代码、案例或社区信号扩展知识 | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]]，并组合 authoring Read Set | claim、evidence role、gap、promotion、update / new / defer / supersede |
| 建立行业 Case Study | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]] + [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] | reported fact、inference、recommendation 和指标 provenance |
| 创建、迁移或审查表达层内容 | 所选 profile 的 `Routing And Gate Registry` 注册的 `Expression Layer Read Set` | knowledge 与 expression 分离、表达规则、追问结构和 migration coverage |
| 批量重命名、移动、拆分、合并或目录重构 | [[kernel/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor]] | source / target map、incoming links、ownership、回滚和内容守恒 |
| 启动、恢复、暂停或完成长任务 | [[kernel/Read Sets/07 Long-running Execution Read Set\|Long-running Execution]]，并组合实际内容 Read Set | task state、时间语义、Coverage Ledger、Required Queue 和 Terminal Proof |
| 内容审查、batch 关闭或完成验收 | [[kernel/Read Sets/08 Audit and Completion Read Set\|Audit and Completion]]，加上与被审 finding 相关的 Read Sets | correctness、depth、provenance、integration、rendering 和 terminal state |
| 修改 Standards、Read Sets 或控制面结构 | [[kernel/Read Sets/09 Standards Governance Read Set\|Standards Governance]] | authority、version、migration map、active task impact 和全库验证 |
| 处理中途用户引导、范围或优先级变化 | [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]]；涉及 hypothesis 时再加载 [[kernel/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads\|User Guidance Hypotheses and Source Leads]] | guidance type、authority、evidence role、disposition、safe switching 和 version impact |
| 拆分专有名词 | [[kernel/05 Terminology/01 Terminology Extraction\|Terminology Extraction]] + [[kernel/05 Terminology/02 Ownership and Term Structure\|Ownership and Term Structure]] | 是否可复用、是否已有 canonical owner、是否值得独立页面 |
| 数学、公式、表格、图片或渲染修复 | [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] 的 triggered modules + [[kernel/12 Quality Assurance/02 Rendering Verification\|Rendering Verification]] | Level 0 / Level 1 确定性验证；只有未决显示问题才升级视觉识别 |
| 周期性 knowledge-corpus 更新 / 保鲜（Maintenance Run） | [[kernel/Read Sets/10 Maintenance Run Read Set\|Maintenance Run]] | 预算封套、候选清单、水位线推进和有界完成语义 |

## Effort Tiering

页面级验收强度按 S/M/L 分档执行。本节是分档规则的 canonical owner；各 Runtime Card 中的 Tiering 表由本节编译产生。

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review\|12/03]] 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋对应 Card 的 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页，以及所选 profile 的 `Routing And Gate Registry` 登记的额外 L 档触发项 | 完整流程：[[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review\|12/01]] 全量 review＋独立 note gate＋适用的 expression migration 核对 |

- P0 / P1 的具体授予条件由所选 profile 的 `Priority Rubric` 登记。
- 分档存在争议时上调一档。
- 每个页面的 tier 记入 Coverage Ledger 的 `tier` 字段（schema 见 `Tools/schemas/coverage_ledger.template.yaml`）。
- 分档只调节验收仪式的强度，不改变任何内容质量标准本身。

### Priority Quota（优先级配额）

tier 由 priority 派生，priority 通胀会使分档失效。Kernel 默认全库配额：

- `P0` 占比目标 ≤15%；具体授予对象由所选 profile 的 `Priority Rubric` 登记。
- `P1` 占比目标 ≤35%；具体授予对象由所选 profile 的 `Priority Rubric` 登记。
- 其余页面为 `P2`（含全部术语存根、占位页与绝大多数 Source Notes）。

超出配额的 P0/P1 必须降级，或在 Coverage Ledger 记录显式豁免理由；无豁免记录的超配按 coverage 对账缺口处理。REBASE 与 Maintenance Run 的 coverage 对账必须检查 priority 与 tier 分布（`Tools/check_vocab.py` 输出分布统计与超配候选）。所选 profile 可以覆写 15% / 35% 默认值，但必须显式登记。

## Maintenance Run Envelope

维护轮启动时必须声明预算封套，三选一：N 页、N 批次或 N 小时。

- 候选清单 = `check_freshness` 过期清单 ∪ 水位线增量 ∪ `needs_rereview` 标记 ∪ candidates 池（duplicate / vocab / language）；按 priority 排序后截断到预算。
- batch 内 changed 页面产生的候选当批判定（作者在场，成本最低）；存量页候选一律入池，不在任何 gate 阻塞或提示为待办。
- 候选在池中连续 3 个维护轮未被预算选中，自动降级为 log-only：保留记录，不计入待办、不出现在 gate 输出、不计入任何完成判定；再次被新扫描命中时重新入池。
- 维护轮开始时输出 deferred 年龄分布；滞留超过 3 轮的项必须显式处置：降级、退役或记录保留理由。"deferred 不构成缺口"保留，但不作为免检依据。
- 高入度页面退役的入链改指工作按"改指数 ÷ 6"折算为页数计入维护轮预算。
- 被截掉的部分记入 Ledger 的 deferred，不构成缺口。
- 停点为批次边界，不在批次中途停止。

## Pre-execution Gate

满足以下条件后才能开始大批量修改：

1. 已读取 `00` 和 Core Bootstrap。
2. 已根据 Task Routing Table 解析 task-specific Read Sets、triggered modules 和 gate modules。
3. 已记录 contract / scope / queue / initial batch / Standards version、loaded set（Runtime Card IDs、`Runtime Card Provider` 解析的 artifacts 与升级回读的 module paths）、目标范围、排除范围和最新用户要求。
4. 已明确 `minimum_run_until`、`checkpoint_at`、`hard_stop_at` 和 Completion Gate；未提供的字段明确留空。
5. 已建立或刷新 Coverage Ledger，并与文件系统和 exclusions 对账。
6. 已盘点 ownership、incoming links、用户修改和 Required Queue。
7. 已识别基础知识依赖，不能把所有前置内容塞进所选 `Profile Scope` 声明的应用主线页面。
8. 来源驱动任务已建立 source inventory 和 claim extraction 方案。
9. 已定义当前 batch 的完成条件、`rendering_mode`、确定性验证命令，以及任何视觉升级的客观 trigger 和 unresolved question。
10. 已加载最新 Audit Receipt Register（[[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]]）；开工阶段只加载 Register，不构建 AuditPlan——AuditPlan 在批次关闭前构建一次。

任一条件缺失时，先补计划或调查，不直接进行大规模创建、移动或删除。

## Default Constraints Snapshot

以下规则在所有长任务中默认生效：

- 所选 profile 的 `Profile Scope` 登记内容主线、基础知识层和完整性谓词；kernel 要求主线与基础知识同时保全。
- 排除范围从所选 profile 的 `Profile Scope` / `Excluded Scope` role 读取，kernel 不固化部署路径。
- Active Standards 是受保护的控制面；内容建设任务中冻结，只有用户明确授权的 governance change 才能修改。
- 文件夹、文件名、知识正文、标题和首次术语的 reader-facing language 取值由所选 profile 的 `Language Contract` 提供。
- 一个知识对象只有一个 canonical owner；其它页面通过 wiki links 复用。
- 专有名词的定义、主题机制、系统交互、案例应用和表达层内容分层维护；表达产物由 `Expression Layer Entry` 登记。
- 外部来源不能直接等同于 canonical knowledge，必须经过 source-to-knowledge pipeline。
- 不创建空壳页面、长期红链接或只有两三句的 P0 / P1 核心页面。
- 不回滚、覆盖或删除无法确认来源的现有用户修改。
- 每个 batch 同步正文链接、metadata、Sources、Expression Layer mapping 和 QA；Overview / MOC 等枢纽页由 integrator 在批次合并后同步（[[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]]）。
- Batch、专项审计和 Terminal Audit 通过 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] 复用仍有效的分维度证据；不能盲信旧状态，也不能无差别重做全部人工审阅。
- `task_state`、`authoring_status`、profile-owned expression status axis、`evidence_maturity` 和 `learning_status` 分别维护；具体 expression axis 由 `Expression Layer Entry` 登记。
- 中途 Guidance Event 必须分类、记录 disposition 并映射到 Amendment Log、Coverage Ledger、Required Queue 或 source intake。
- 用户对 task scope 和 priority 有 authority；用户 hypothesis 和 source lead 仍需证据核验。
- 直接内容提取和结构检查全量执行；静态 compile / parse 按内容触发；所选 profile 绑定的 `knowledge-host UI`、截图和视觉模型只在确定性证据无法消除具体显示不确定性时使用。
- 录屏只用于静态证据和 targeted screenshot 无法表达的时序或交互问题。
- 完成必须满足 `missing=0`、`ambiguous=0`、Guidance / Coverage Reconciliation、适用 QA gates 和 Terminal Proof。

## Batch Execution Checklist

1. 版本自检：对比 [[kernel/00 Standards Control/03 Standards Governance|00/03]] 当前版本与 contract 冻结版本；有 delta 按 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] Active-task Adoption 增量采纳，无 delta 记一行 receipt。标准变更由批次激活自检发现，用户通知仅作提醒。
2. Reconcile 增量 guidance：只对账 `last_reconciled_guidance_id` 之后的 Guidance Events 与 Amendment Log。
3. 从有序 Required Queue 中选择下一个 batch。
4. 解析 note type、canonical owner 与目标 status。
5. 解决 prerequisite 与 foundation 缺口。
6. 需要时收集并分类 sources。
7. 写完一个完整的 dependency-aware batch。
8. 整合正文链接、导航、metadata、sources 和 Expression Layer mapping。
9. 批次关闭前构建一次 AuditPlan 并处理 receipts（[[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]]）：完成 `--scope` 自查、所需增量人工/渲染 QA 与 [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|12/03]] 批内项，发放或 supersede 分维度 AuditReceipts，写出 delta；批次进入 `merge-ready`。视觉检查仅凭已记录的 exception trigger 升级。
10. integrator 串行合并（[[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches）：应用 delta、运行 Batch-close Closed List、核验 12/03 全局项并更新全局 Ledger 与 Amendment Log；批次自身不写全局账本。
11. 仅在 Batch Review 通过且 unresolved invalidations = 0 后关闭 batch；否则保持 active 或 merge-ready。

注：批开始不执行 Coverage 对账；对账在批次关闭执行。
