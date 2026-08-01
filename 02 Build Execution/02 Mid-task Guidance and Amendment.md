## Navigation

- Parent: [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[Knowledge Base Standards/02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]].
- Next: [[Knowledge Base Standards/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]].

## Mid-task Guidance And Contract Amendment

长任务执行中，用户新增的看法、纠正、主题、优先级、来源线索、格式偏好或停止指令统称为 `Guidance Event`。Guidance Event 必须被保留、分类和处置，不能只依赖当前上下文记忆，也不能未经判断就直接写入 canonical knowledge。

**重要 Guidance Event** 指改变目标、范围、验收、优先级或内容判断的消息；本页与 [[kernel/12 Quality Assurance/04 Guidance and Source Review|12/04]] 的处置义务均以此门槛为准。纯状态询问或确认类消息记一行 log，不占 guidance_id、不进入 Amendment Log。

### Cumulative Amendment Rule

最新用户指令具有最高 task authority，但它默认只修改明确涉及的 contract 维度：

- 新增主题不自动取消原 scope。
- 调整优先级不自动降低原 acceptance criteria。
- 表达个人看法不自动成为知识事实。
- 提供来源线索不自动证明来源中的 claim。
- 修改图表偏好不自动要求重写所有历史页面。
- 与旧要求不冲突的 constraints 继续有效。

只有新旧要求在同一维度直接冲突时，最新明确指令才覆盖旧值。高影响歧义无法从上下文可靠解决时，将相关 guidance 标记为 `clarification-required`，暂停受影响动作，同时继续不受影响的 Required work。

### Guidance Classification

| Guidance Type | Example | Default Route |
|---|---|---|
| Operational control | 暂停、停止、持续到某时间、立即切换 | 更新 task state 或 time contract |
| Scope amendment | 增加 Cache、Memory 或新领域 | 更新 scope version 和 Coverage Ledger |
| Priority or sequence | 先做 Memory，再做 Retrieval | 更新 queue revision |
| Acceptance or quality feedback | Agent Basic Flow 没有讲清 | 触发定向审计，确认后登记 gap |
| Presentation preference | 流程图改为横向 | 更新当前 batch constraint；可复用时评估 Standards amendment |
| Knowledge hypothesis | Cache 是当前行业热点 | 记录为 research signal，进入证据调查 |
| Source lead | OpenAI 或 Anthropic 有相关文章 | 进入 source capture 和 claim extraction |
| Correction | 当前定义、公式或系统链路可能错误 | 评估传播范围，必要时立即中断修正 |
| Project or first-party context | 用户描述自己的系统、指标或事故 | 保留为有边界的 first-party context，不泛化为行业事实 |
| Governance candidate | 以后所有流程图都不能牺牲完整性 | 只有用户明确授权后才修改 Standards |

同一 Guidance Event 可以同时属于多类。例如“Cache 是行业热点，需要优先补全”同时是 scope amendment、priority change 和 research signal。

### Intake And Impact Analysis

```text
Receive Guidance
 -> Preserve Meaning
 -> Classify Type
 -> Check Conflict And Authority
 -> Analyze Scope / Dependency / Evidence / Batch Impact
 -> Choose Disposition
 -> Amend And Version The Right Contract
 -> Map To Ledgers And Queue
 -> Acknowledge Interpretation
 -> Execute At A Safe Boundary
 -> Verify And Close
```

Impact analysis 至少检查：

- 是否改变 objective、scope、exclusions、acceptance、time 或 Standards。
- 是否影响当前 batch 的有效性和已写内容。
- 是否暴露新的 prerequisite、canonical owner 或跨模块依赖。
- 是否需要 source intake、external verification 或 evidence maturity 限定。
- 是否改变 Required / optional / deferred disposition。
- 是否需要回查已经关闭的页面或 batch（仅当 guidance 为 correction 类且明确指向已关闭对象时）。
- 是否改变 Completion Gate 或预计的 Terminal Audit scope。

### Disposition

每条重要 guidance 必须选择一个明确 disposition：

- `interrupt-now`：立即保存一致 checkpoint 并切换。
- `apply-to-current-batch`：与当前 owner 和 acceptance 一致，可在不扩大 batch 边界的情况下整合。
- `queue-next`：当前最小可验收单元完成后立即执行。
- `queue-by-dependency`：加入 Required Queue，由 prerequisite order 决定位置。
- `research-first`：先做 source inventory、claim extraction 和 gap analysis。
- `deferred`：暂缓，必须记录原因、re-entry condition 和 authority。
- `clarification-required`：高影响语义不能可靠判断，等待用户澄清。
- `superseded`：被后续明确 guidance 替代，并保留替代关系。
- `not-applicable`：与当前 contract 无关或已被现有工作完整覆盖，必须说明依据。

不得使用 `deferred` 或 `not-applicable` 静默丢弃用户新增要求。

### Safe Switching Policy

默认在最小安全边界切换，而不是在文件或验证中间留下不一致状态。通常先完成当前原子编辑、保存文件并运行必要的局部检查，再 checkpoint 和重排队列。并发执行时，中断与切换由 integrator 执行：按 Amendment Record 的 `affected_batches` 定位受影响批次，未受影响批次不中断。

以下情况必须立即中断：

- 用户明确要求立即停止、暂停或切换。
- 新 constraint 禁止继续当前动作。
- 当前工作存在安全、数据完整性或严重事实错误。
- 新信息使当前 batch 的基础假设失效。
- 继续执行会扩大错误、覆盖用户修改或产生不可逆副作用。

以下情况通常不立即中断：

- 新增一个与当前 batch 无直接依赖的跨领域主题。
- 只改变后续优先级。
- 需要先研究来源才能确认的用户 hypothesis。
- 可在当前原子操作后安全处理的格式或导航要求。

小型、同 owner、同 acceptance 的补充可以进入当前 batch；跨 owner 或跨系统的新主题必须形成独立 vertical slice。不得把持续到来的 guidance 全部塞进当前 batch，造成 batch 无边界扩张。

### Amendment Record

重要 Guidance Event 必须进入 Progress Ledger 的 Amendment Log。记录至少包括：

```text
guidance_id
received_at
message_reference
raw_guidance_summary
normalized_intent
guidance_types
authority_scope
evidence_role
affected_scope
affected_pages
affected_batches
dependency_impact
conflict_analysis
disposition
contract_version_before / after
scope_version_before / after
queue_revision_before / after
batch_revision_before / after
standards_version_before / after
completion_gate_impact
status
verification_evidence
```

`raw_guidance_summary` 应保留原意，但不复制无关对话或敏感信息。`normalized_intent` 说明执行者如何理解要求。`evidence_role` 区分 user authority、research signal、source lead、first-party context 和 externally verified claim。

`guidance_id` 使用 task-local、单调递增且不复用的标识，例如 `G-001`、`G-002`。这样 checkpoint 和 Terminal Audit 才能用 `last_reconciled_guidance_id` 与 `guidance_cutoff_id` 建立明确边界。

Guidance status 建议使用：

```text
received
 -> classified
 -> mapped
 -> in-progress
 -> verified

classified -> clarification-required
classified / mapped -> deferred
received / classified / mapped -> superseded
```

### Versioning Rules

- `contract_version`：objective、constraints、acceptance、time、exclusions 或 pause policy 改变时提升。
- `scope_version`：in-scope domains、Required objects 或 coverage disposition 改变时提升。
- `queue_revision`：只改变优先级和 dependency order 时提升。
- `batch_revision`：当前 batch 的 pages、acceptance 或 verification plan 改变时提升。
- `standards_version`：只有可复用 governance rule 且用户明确授权修改 Standards 时提升。

一次 guidance 可以提升多个版本。仅新增研究线索但尚未接受为 scope 时，不提前修改 scope version。

### User-facing Acknowledgement

收到影响任务的重要 guidance 后，应在简短进度更新中说明：

- 被理解为什么类型。
- 影响哪些 scope、batch 或 evidence work。
- 将立即应用、在安全边界后切换、按依赖排队，还是先研究。
- 是否改变 contract、scope、queue 或 Standards version。

没有实质歧义时不需要反复请求确认；但不能让用户直到最终报告才发现其 guidance 被延期或忽略。
