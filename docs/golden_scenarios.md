# Golden Scenarios

本文件冻结 Cambium 拆分前 v2.3 基线的行为判定，基线 commit 为 `060433eb45856891b26d67d36770ebf72c960971`。拆分后的回归读取面是 `kernel + profiles/agent-atlas`；下列 12 个场景的路由、分档、gate 与关批结果必须保持一致。本文件只记录判定事实，不复制规则原文。

## Shared Decision Vocabulary

- `Core` 表示所有场景先加载 Card 01 / RS 01，再叠加场景专属 Card、Read Set 与 triggered modules。
- S/M/L 是页面级验收分档，不是任务状态：P2、术语存根、占位页或链接聚合页为 S，仅做脚本检查且无独立 note gate，批关闭抽样 `max(2, 20%)`（不足 2 页则全查）；P1 常规页为 M，Card gate 并入 batch gate；P0 或 core concept、process-flow、system、risk-control 主线页、System Deep Dive、Interview Card 集为 L，执行全量 review 与独立 note gate；争议时上调。
- `Batch internal gate` 表示 Required pages 达到目标状态，ownership、Sources、metadata、正文链接与导航同步，Interview migration 有最终 disposition，changed scope 的自动、人工与适用 rendering 检查完成，AuditPlan 与分维度 receipts 已生成，delta 已写出，批次进入 `merge-ready`。
- `CL7` 表示 integrator 在单批串行合并后的完整 in-scope snapshot 运行七项确定性检查：Wiki link missing / ambiguous / heading resolution；Markdown / YAML / fence / table 结构；graph JSON 与 duplicate basename candidates；Coverage file-count 对账；guidance ID 与 contract version 连续性；Interview 残留章节扫描；Frontmatter 受控词表校验。
- 标准关批结果是：integrator 串行应用一个 batch 的 delta，在合并后的完整 snapshot 运行 CL7，再核验 12/03 全局项，包括增量 guidance 对账、本批 direct / dependency invalidations 清零和全局 Ledgers 同步；只有 Batch Review 通过且 `unresolved_invalidations = 0` 才关闭。

## G01 — Single-page Authoring

**Task.** 新建一篇 atomic depth、P1 的常规 canonical note；内容不是 core concept、process-flow、system 或 risk-control 主线页，不引入外部来源、公式、图表或具体显示问题。

**Expected determination.** 路由为 Core + Card 02 / RS 02；页面分为 M 档。页面关闭检查并入 batch gate，执行 Card 02 的 ownership、depth、metadata、links、language 与内容检查，并完成页面范围的 `check_links`、`check_vocab` 自查；没有 visual exception trigger 时 rendering 停在 Level 0 / 1。批关闭执行 Batch internal gate、增量 guidance / invalidation 对账、delta 合并和 CL7，不另开独立 note gate。

## G02 — Module Build

**Task.** 建设一个包含 MOC、多个 leaf pages、跨模块依赖和一篇 P0 system 主线页的完整模块，工作需要多个 batches。

**Expected determination.** 路由为 Core + Card 03 / RS 03，并组合 Card 07 / RS 07；完整模块关闭时再组合 Card 08 / RS 08。分档上，P0 system 主线页为 L 档，其他页面逐页判档；含 L 页的混合 batch 按 L 主导，v2.3 默认上限为 6 页。L 页在成稿并完成 scope 自查后触发独立实质正确性复核与独立 note gate；每批通过 Batch Review，模块结束时再过 Module Review 与 Coverage Reconciliation，任务完成候选再过 Terminal Audit。每批关闭执行 Batch internal gate、delta 串行合并、全局对账和 CL7；模块 gate 复用仍有效的 batch receipts，只补跨 batch 的 owner、dependency、coverage 与 navigation 判断。

## G03 — Source-driven Expansion

**Task.** 一份新的官方厂商文档提供了可定位 claims，需要建立一篇 P2 Source Note，并更新一篇不属于主线类型的 P1 canonical note。

**Expected determination.** 路由为 Core + Card 04 / RS 04，并因修改 canonical note 组合 Card 02 / RS 02；官方材料仍只证明其披露范围。Source Note 为 S，只做脚本检查并进入批关闭抽样；P1 常规 canonical note 为 M。适用 gate 包括 source identity / authority / evidence role、claim classification、gap 与 graph decision、Source Intake and Promotion Review，以及 canonical note 的 M 档 Card gate；未通过 promotion gate 不得标为 canonical。批关闭前完成 pipeline、changed-scope 自查、source receipts 与 watermark delta，随后执行标准串行关批和 CL7。

## G04 — Migration and Refactor

**Task.** 在一个独占 migration batch 内，对由 P1 常规页面组成的现有内容目录执行批量移动、重命名和页面拆分；目标页 priority 按 contract 冻结为 P1，同时保留 canonical ownership、heading anchors、incoming links 与全部原内容。

**Expected determination.** 路由为 Core + Card 06 / RS 06。受影响页面保持 P1 并判为 M；迁移动作本身不产生额外 task tier。迁移 batch 必须独占，不能与其他 active batch 并发；开始前冻结 source / target / incoming links / headings / owner / rollback 清单，删除旧位置只能发生在新位置已建立、验证并完成引用更新之后。适用 gate 是内容块一对一守恒、链接与 heading 解析、Coverage Reconciliation、Batch Review、自动与人工检查及最终 Terminal Audit。批关闭执行标准串行关批和 CL7，其中链接、结构、coverage 与词表结果必须基于迁移后的完整快照。

## G05 — Long-running Resume

**Task.** 一个处理 P1 常规页面的多批次 module-build 任务从 `paused` 恢复；YAML Progress / Coverage Ledgers 记录一个已写出 delta 的 `merge-ready` batch、一个未完成 active batch、最后一次 QA 与下一精确动作。

**Expected determination.** 路由为 Core + Card 03 / RS 03 + Card 07 / RS 07；内容页保持 M，resume 动作本身没有 task tier。恢复先核对最新用户要求、contract / scope / queue / time semantics、工作树、现有用户修改、未验证变更和 guidance，再把 task state 改回 `active`。已 `merge-ready` 的 batch 由 integrator 继续串行合并，不重做批内工作；active batch 从 checkpoint 的下一精确动作继续。各批仍须通过 Batch Review、receipt / invalidation gate 和 CL7；进入完成候选前执行 Coverage Reconciliation，再组合 Card 08 / RS 08。

## G06 — Terminal Audit

**Task.** 一个长任务已成为 `completion-candidate`，所有声明 batches 均已关闭，现需决定是否可以标记 `complete`。

**Expected determination.** 路由为 Core + Card 08 / RS 08，并加载与 findings 相关的内容 Read Sets；Terminal Audit 不产生新的页面 tier，审查对象沿用原分档。先冻结 snapshot 与版本 / guidance cutoff，核对 receipt register、Guidance Reconciliation、Coverage Ledger、Required Queue、merge queue、invalidations 和全部适用 gates；对最终冻结快照再次运行 CL7，只对 changed、invalidated、overdue 与有界抽样对象做语义审阅并复用其余有效 receipts。只有 guidance 三个未决计数、required authoring gaps、unverified batches 与 unresolved invalidations 全部为 0，适用 gates 全过且 Final Handoff / Terminal Proof 完整时，状态才变为 `complete`。

## G07 — Standards Governance Revision

**Task.** 用户明确授权修改 Standards 的模块边界与一项 gate 语义，并要求同步控制面入口和受影响运行时产物。

**Expected determination.** 路由为 Core + Card 09 / RS 09；Governance 任务按 L 档处理，且必须通读 RS 09 的 source modules，Card 09 只能作导航。变更前冻结 standards version、受影响 modules、incoming links 与 active-task impact；执行时提升 `standards_version`，更新 `00` 的 routing 与 Change Summary，并在修订记录给出 changed-predicate 清单。结构变化建立旧内容块到新 owner 的完整映射，并同步 domain MOC、Read Sets、Registry、Cards 与 vocab 产物。适用 gate 包括 Standards coverage / MOC、全库 incoming links、active-task receipt compatibility / invalidation / adoption、Write-back Checklist、`stamp_cards.py --check` 和 Terminal Audit。治理 batch 关闭时完成 changed-scope 检查、标准串行关批与 CL7；不得用拆分缩减、摘要或静默删除规则。

## G08 — Maintenance Run

**Task.** 发起一个预算为两个 batches 的周期性维护轮，候选来自 freshness 过期项、水位线增量、`needs_rereview` 和 duplicate / vocab / language candidates 池，其中包含一篇 P0 system 主线页和若干 P2 Source Notes。

**Expected determination.** 路由为 Core + Card 10 / RS 10；P0 system 主线页为 L，P2 Source Notes 为 S，维护动作本身没有 task tier；若两类同批则按 L 主导并采用 v2.3 默认 6 页上限。四源并集按 priority 排序并截断到预算，超出预算的项进入 deferred；来源内容组合 Card 04，L 页触发独立实质复核。每批通过 Batch Review、推进 Ledgers 与 watermark，并在串行合并后运行 CL7；freshness 与 duplicate 检查属于维护轮候选生成，不加入 CL7。两个预算内 batches 与其适用 gates 关闭后按 Maintenance Completion 完成本轮，不要求全库 Terminal Proof。

## G09 — Concurrent Batch Activation

**Task.** 一个 module-build 长任务中，由 P1 常规页面组成的 Batch A 已 active；准备激活同为 P1 常规页面的 Batch B。两批页面清单不相交，B 不编辑 MOC、Overview、Roadmap、Cheat Sheet 或共享术语页，B 的全部 prerequisites 已在更早 batch 合并，当前 active 数量低于 `concurrency_cap`。

**Expected determination.** 路由为 Core + Card 03 / RS 03 + Card 07 / RS 07；两批页面均为 M，激活行为本身没有 task tier。B 满足 v2.3 的三项准入条件和 cap，因此可以 active；任一条件不成立时不得激活。并发作者只写本批页面、本批 receipts 和本批 delta，全局 Ledgers、queue、guidance、contract、激活与合并由 integrator 单线程控制。A、B 各自先完成 Batch internal gate 进入 `merge-ready`，随后由 integrator 一次只合并一个；每次合并后分别运行 CL7 和 12/03 全局项，不能把两个 batch 合成一次关批。

## G10 — Mid-task Guidance Disposition

**Task.** 一个 module-build 长任务的 P1 常规页面 M batch 执行中，用户要求“当前 batch 完成后，下一个先处理 Topic B”；该要求不新增 scope、不降低 acceptance，也不要求立即中断当前原子操作。

**Expected determination.** 路由为 Core + Card 03 / RS 03 + Card 07 / RS 07，并加载 `02 Build Execution/02 Mid-task Guidance and Amendment.md`；这是一条重要的 priority / sequence Guidance Event，事件本身不改变页面 tier。默认 disposition 为 `queue-next`：保留当前 batch 边界，在安全边界后切换；建立单调 guidance ID 与 Amendment Record，只提升 `queue_revision`，不提升未受影响的 contract 或 scope version。适用 gate 是 Guidance Reconciliation：批关闭时检查该事件已分类、映射并按 disposition 验证，三个 guidance 未决计数为 0；CL7 同时验证 guidance ID 与 contract version 连续性。

## G11 — Review Convergence

**Task.** 一篇新建的单页 canonical note 被判为 L 档；完成 scope 自查后，独立复核第 1 轮给出一个 major finding 和一个 minor finding，作者修复 major、保留并记录 minor，随后进入确认轮。

**Expected determination.** 路由为 Core + Card 02 / RS 02，并触发 `12 Quality Assurance/01 Quality Dimensions and Single Note Review.md` 的独立实质正确性复核。第 2 轮只确认第 1 轮 major 已关闭，不新增审查范围；minor 不阻断，确认轮发现的新问题进入 Open Questions 或标记 `needs_rereview`，不重开本轮。若 major 在两轮后仍未关闭或范围持续扩张，升级用户裁决，不开启第 3 轮。独立 review receipt 必须在 Batch internal gate 前到齐；如替换既有证据则记录 supersede。页面 note gate 通过后，batch 才能进入标准串行关批并运行 CL7。

## G12 — Closed-list Execution Point

**Task.** 一个 module-build 长任务中的两个 P1 常规页面并发 M batches 已完成各自写作、scope 自查、人工 / rendering QA、receipts 与 delta，均处于 `merge-ready`；需要决定固定七项检查何时、对什么快照运行。

**Expected determination.** 路由为 Core + Card 03 / RS 03 + Card 07 / RS 07，并以 `12 Quality Assurance/03 Module Coverage and Batch Review.md` 和 `12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md` 为 gate owner；两批页面均为 M，执行点本身没有 task tier。每个 batch 的 AuditPlan 只在进入 `merge-ready` 前生成一次；CL7 不在 batch 开始时运行，也不在未合并的分支快照运行。Integrator 先应用一个 batch 的 delta，再对合并后的完整 in-scope snapshot 运行 CL7、完成 12/03 全局项并关闭该 batch；然后对下一个 batch 重复同一顺序。最终 Terminal Audit 再对冻结后的最终 snapshot 运行一次 CL7。

## Baseline Trace

| Scenarios | Baseline owners |
|---|---|
| G01–G04 | `00 Standards Control/02 Task Routing and Pre-execution.md`；`Read Sets/02–06`；`Cards/02–06`；`12 Quality Assurance/03 Module Coverage and Batch Review.md` |
| G05、G09、G10、G12 | `Read Sets/07 Long-running Execution Read Set.md`；`Cards/07 Long-running Execution Card.md`；`02 Build Execution/02,05,06`；`12 Quality Assurance/04,07` |
| G06 | `Read Sets/08 Audit and Completion Read Set.md`；`Cards/08 Audit and Completion Card.md`；`12 Quality Assurance/06,07` |
| G07 | `Read Sets/09 Standards Governance Read Set.md`；`Cards/09 Standards Governance Card.md`；`00 Standards Control/03 Standards Governance.md` |
| G08 | `Read Sets/10 Maintenance Run Read Set.md`；`Cards/10 Maintenance Run Card.md`；`00 Standards Control/02,06` |
| G11 | `12 Quality Assurance/01 Quality Dimensions and Single Note Review.md` |
