## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/02 Rendering Verification|Rendering Verification]].
- Next: [[kernel/12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].

## Module Review

一个模块完成前检查：

- Overview 是否反映真实模块结构。
- Coverage matrix 是否还有未解释的 P0 / P1 概念。
- Prerequisite chain 是否连续。
- 所选 profile 的 `Profile Scope` 声明的主线依赖与基础保全要求是否仍然完整。
- 是否存在重复 canonical notes。
- 是否存在 orphan notes。
- `Routing And Gate Registry` 注册的 profile artifact synchronization gates 是否通过。
- Case Study 是否能使用该模块知识。
- 新外部来源是否经过 gap analysis，而不是按文章标题产生孤立页面。
- 文件深度是否均衡，核心主题不能明显薄于边缘主题。
- Standards 模块还必须确认 domain MOC 与实际 leaf files 一致、每个原章节只有一个 owner、Applicable Read Sets 可双向导航。

Module Review 先消费已关闭 batches 的有效 AuditReceipts，再审查跨 batch 才能判断的 owner、dependency、coverage 和 navigation invariants。没有相关变化的局部 mechanism 不应被逐页重审；receipt 缺失、失效或抽样暴露系统问题时，按 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] 扩大范围。

## Coverage Reconciliation Review

模块或长任务完成前，必须把 Coverage Ledger 与实际文件系统、scope contract 和 competency matrix 对账：

- 每个 in-scope 文件恰好有一个 inventory 记录。
- 每个 Required 但尚未创建的知识对象仍有明确记录。
- 排除目录没有被计入成果或误改。
- P0 / P1 的 core、process-flow、system、risk/control 页面不存在 `unassessed`。
- 每个未达到目标状态的 Required 项都有 active 或 queued batch。
- `deferred` 有原因、re-entry condition 和 owner；`excluded` 有 scope 依据。
- 序列或进度 checkbox、文件存在、Wiki link 可解析和 `Related` 引用没有被当作 authoring completion；状态分离见 [[kernel/11 Expression Layer/06 Sequence and Progress Semantics|Sequence And Progress Semantics]]。
- 核心页面没有明显薄于新建的边缘或前沿页面。
- Coverage Ledger 汇总数量与自动扫描数量一致。

行数和 section 数量只能触发审阅候选。Atomic Term Note 可以有意保持简洁；Core、Process、System 和 Risk/Control 页面必须按 note type 检查问题覆盖。

## Batch Review

并发执行时，批次正文只能链接到已合并内容或本批清单内的页面；指向在途批次页面的链接留待双方批次合并后补充：作者把缺链记入本批 delta 的 `open_gaps_added`（type: link），由维护轮按预算消化；补链位置遵循 [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]]（Related 不是唯一引用位置）。

Gate 合并规则（分档判定见 [[kernel/00 Standards Control/02 Task Routing and Pre-execution|00/02]] Effort Tiering）：

- S/M 档页面的 note 级验收并入 Batch Review 执行，不单独开 note gate。
- S 档页面按抽样复核：默认抽取 `max(2, 20%)` 的本批 S 档页面（不足 2 个则全查）；抽样发现问题时按 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] 扩大范围。
- M 档页面在 batch gate 内逐页通过 `Runtime Card Provider` 提供的对应 Gate 清单。
- L 档页面保留独立 note gate，按 [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]] 全量执行，不并入本节。

关批清单分两组：**批内项**在批次进入 `merge-ready` 前由批次自身完成（可与其它批次并行）；**全局项**由 integrator 在串行合并时核验。串行区只执行确定性动作与全局核验，不做批内人工审阅。

批内项（merge-ready 前提）：

- Batch contract 中的 Required pages 全部达到目标 `authoring_status`。
- Canonical ownership、Sources、metadata、正文 Wiki links 和导航已同步。
- 由 `Expression Layer Entry` 注册的 Required migration 已完成或有明确 disposition；具体 gate 由 `Routing And Gate Registry` 绑定。
- 自动检查（`--scope` 级）、人工内容审阅和适用的 rendering level 已完成。
- 已从 changed objects、acceptance predicates 和 dependency changes 生成 AuditPlan；仍有效的历史证据有明确 `reused_receipt_id`，新检查产生 dimension-specific AuditReceipts。
- delta 已写出，没有把未验证修改留给下一个 batch。

全局项（integrator 串行合并时核验）：

- guidance 对账见 [[kernel/12 Quality Assurance/04 Guidance and Source Review|12/04]]（增量）。
- 当前 batch 影响的 direct / dependency invalidations 已关闭，`unresolved_invalidations = 0`。
- delta 经 `Tools/apply_delta.py` 应用，Coverage Ledger 与 Progress Ledger 同步更新。

未通过 Batch Review 时，batch 不得关闭；缺口回到执行阶段处理，batch 保持未验收状态，不能为了开始下一主题而标记关闭。
