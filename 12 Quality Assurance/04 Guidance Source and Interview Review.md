## Navigation

- Parent: [[Knowledge Base Standards/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]].
- Next: [[Knowledge Base Standards/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]].

## Guidance Reconciliation Review

每个 batch 关闭前和长任务进入 `completion-candidate` 前，必须对 [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment#Mid-task Guidance And Contract Amendment|Mid-task Guidance And Contract Amendment]] 执行 reconciliation。batch 关闭对账为增量：只对 `last_reconciled_guidance_id` 之后的新 guidance 执行对账，加上既有未决项；三计数语义不变，仅计算范围收窄为增量＋既有未决项。

最低通过条件为：

```text
unclassified_guidance = 0
accepted_unmapped_guidance = 0
implemented_unverified_guidance = 0
```

检查内容包括：

- 所有**重要 Guidance**（正面定义：改变目标、范围、验收、优先级或内容判断的消息）都有 `guidance_id` 和 Amendment Record；纯状态询问或确认类消息记一行 log，不占 `guidance_id`、不入 Amendment。
- Raw guidance 与 normalized intent 含义一致，没有把建议扩大为命令或把命令降级为建议。
- 新要求只修改明确涉及的 contract 维度；未冲突的旧 constraints 仍然有效。
- Scope、contract、queue、batch 和 Standards 的版本提升与实际影响一致。
- Accepted guidance 已映射到 current batch、Required Queue、Coverage Ledger、source intake 或明确 deferred record。
- `research-first` 的用户 hypothesis 没有在来源验证前写成 canonical fact。
- 用户提供的 URL 以实际文档作为 Source；first-party context 没有被无边界泛化。
- `deferred` 有 authority、原因和 re-entry condition；`not-applicable` 有可检查依据。
- `superseded` 保留前后 guidance 关系。
- Safe switching policy 已遵守，没有因切换留下半写文件、未验证修改或失去当前 batch 的一致性。
- 影响 Required completion 的 `clarification-required` 已解决；否则不能进入 `completion-candidate`。

对用户有 task authority 的明确 scope 或 acceptance requirement，不能由执行者自行改成 optional 或 deferred。Dependency-based queueing 可以调整执行时点，但不能静默取消要求。

### Guidance During Terminal Audit

Terminal Audit 开始时记录 `guidance_cutoff_id`。之后收到新 guidance 时：

- 改变当前 objective、scope、acceptance、exclusions、time contract 或 Required content：Terminal Audit 失效，task state 返回 `active`。
- 修正候选结果中的事实、链接、来源或 QA 问题：按 [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|12/06]] Terminal Findings And Convergence 的 major 就地处理（定向重检＋receipt supersede），不整体作废终审。
- 用户明确指定为未来任务或 optional backlog：记录新的 contract / backlog 归属，不改变当前 Terminal Proof。
- 只询问状态且不改变任务：正常答复，不改变 cutoff。

不能通过“Terminal Audit 已经开始”忽略新要求，也不能把明确属于未来任务的 guidance 强行塞入当前 scope。

## Source Intake And Promotion Review

Source-driven expansion 需要额外检查：

- Source identity、日期、URL、source type 和 applicability boundary 是否清楚。
- Key claims 是否可以定位到原始来源。
- Source authority 和 evidence role 是否分别判断。
- 社区信号是否被误写成已验证规律。
- 官方公司文章是否只用于支撑其实际披露范围。
- 用户 hypothesis、source lead 和 first-party context 是否按 [[kernel/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads#User Guidance, Hypotheses And Source Leads|User Guidance, Hypotheses And Source Leads]] 保留证据边界。
- 多来源是否真正独立，术语和实验条件是否可比。
- 新信息为何更新、新建、拆分、合并或暂缓是否有 graph impact 理由。
- 新 canonical note 是否通过 [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline#Stage 9: Verification And Promotion|canonical promotion gate]]。
- Contested 或 superseded 结论是否保留状态、来源和替代关系。

单个 source-driven batch 负责当时的 claim 和 promotion correctness；后续 Source Audit 负责跨批次 identity/currentness、冲突、supersession 和 affected-note propagation。若 artifact、source dependency、review due 或 acceptance predicate 未变化，可以复用局部 source receipt；不能借专项 Audit 重写与其 global invariant 无关的稳定机制。

## Interview Review

- 30 秒回答是否直接、准确。
- 90 秒回答是否包含问题、机制、tradeoff 和场景。
- Deep Dive 是否有至少三层有效追问。
- Follow-up 是否有答案，不只是问题列表。
- 中英文含义是否一致。
- Strong / Weak Signals 是否可以用于评分。
- Interview Card 是否回链 canonical knowledge。
- System / Project Deep Dive 是否按 [[Knowledge Base Standards/11 Interview Content/04 System Deep Dive and Bilingual Policy|11/04]] 的骨架要素逐项覆盖。
- Emerging 或 contested 结论是否有明确限定。
- L 档 Interview 集的实质正确性复核按 [[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]] 的 Substantive Correctness Review 规则执行。

单个 batch 负责其 Card 内容质量和 create-before-remove 迁移；全库 Interview Audit 负责 P0/P1 coverage、Card granularity、重复答案、双向导航和遗漏。后者复用仍有效的 canonical content receipts，只对失效、变化或抽样对象重新进行语义深审。
