## Navigation

- Parent: [[Knowledge Base Standards/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]].

## Purpose

本模块规定单页、batch、module、专项 audit 和 Terminal Audit 之间怎样复用验证证据，同时保证后续修改不会让旧结果被错误继承。目标不是减少质量维度，而是消除两种错误：

1. 每一层都从头重复昂贵的人工审阅，浪费执行时间和上下文；
2. 只因为某页曾经通过，就在内容、依赖或规则已经变化后继续沿用旧结论。

核心链路：变更对象与 acceptance predicates 生成按维度的 AuditPlan，产出不可变 AuditReceipts 并记录 dependency / contract fingerprints；predicates 与 fingerprints 保持有效期间可复用，相关变化触发失效，局部失败显示系统性影响时有界扩大，最终在冻结快照上做 Terminal reconciliation。

## Audit Layers

各层拥有不同问题，不能用名称不同掩盖相同工作：

| Layer | Owns | Reuses | Must not do |
|---|---|---|---|
| Single Note Review | 一个页面在当前版本下的 type-aware content、source、link 和 rendering quality | 同一页面未受影响维度的有效 receipt | 宣告模块或全库完整 |
| Batch Review | 本批 Required objects、集成边和控制面闭环 | 本批开始前仍有效的 prerequisite receipts | 无条件重审所有历史页面 |
| Module Review | owner completeness、dependency continuity、duplicate/orphan 和入口一致性 | 已关闭 batch 的有效局部 receipts | 把局部通过等同于模块完整 |
| Specialized Audit | 跨批次的 source、case、interview、migration 或 currentness invariant | 已通过的局部内容 receipts | 逐页重做与专项 invariant 无关的内容审阅 |
| Terminal Audit | 最终冻结快照的 scope、guidance、coverage、全局 invariants 和 proof | 所有仍有效的 receipt 与 batch evidence | 盲目信任历史状态或无差别重做全部人工审阅 |

同一个 invariant 可以在多个层被再次确认，但每次必须说明新的审计对象。例如 Batch link check 证明本批写入后图仍可解析，Terminal full-vault link check 证明最终快照没有被后续批次破坏。

## Dimension-specific Audit Receipt

审计证据按维度保存，不能只记录一个模糊的 `reviewed: true`。至少使用：

```text
structure_and_links
content_and_depth
formula_and_numeric
source_and_currentness
interview
coverage_and_integration
rendering
guidance_and_contract
```

一次验证产生不可变 `AuditReceipt`，例如：

```yaml
receipt_id: audit-<stable-id>
dimension: structure_and_links
scope: ["<audited path or snapshot>"]
acceptance_predicate: "missing=0 AND ambiguous=0"
artifact_fingerprint: "sha256:..."
dependency_fingerprint: "sha256:..."
contract_fingerprint: "sha256:..."
standards_version: "2.0"
verifier: {name: "kb-audit", version: "..."}
method: deterministic-full
result: passed
evidence_ref: "..."
created_at: "..."
review_due:
supersedes:
```

字段语义：

- `scope`：receipt 实际覆盖的页面、module、batch 或全库 snapshot。
- `acceptance_predicate`：被证明的具体条件；不能只写 `QA passed`。
- `artifact_fingerprint`：覆盖正文内容、文件路径，以及 frontmatter 中的 `type`、`priority`、`tier`、`coverage_disposition`、`lifecycle`、`prerequisites`。**明确排除**：`authoring_status`、`interview_status`、`learning_status`、`last_reviewed`、`last_verified`、`review_by`、`next_batch`——状态轴与调度字段的回写**不使凭证失效**。
- `dependency_fingerprint`：该维度依赖的 canonical owners、sources、schemas、MOC 或配置。
- `contract_fingerprint`：scope、acceptance、exclusions、queue/guidance cutoff 等相关控制状态。
- `verifier` / `method`：脚本、compiler、人工 rubric 或模型审阅的身份与版本。
- `evidence_ref`：命令结果、review record、compiled artifact 或 Batch Review 证据位置。
- `review_due`：时效性事实需要重新核验的时间；稳定机制可以留空。

`last_reviewed`、`last_verified`、文件长度或 `authoring_status` 不能替代 AuditReceipt。

Receipt 的 canonical 格式为 JSONL（schema 见 `Tools/schemas/receipt.template.jsonl`）。确定性检查的 receipt 由 `Tools/check_*.py` 以 `--receipts` 参数自动产出；人工检查的 receipt 按同一 schema 手记。脚本级 receipt 是轻量层，进入 Audit Receipt Register 时由 AuditPlan 层补齐本节的完整 AuditReceipt 字段，脚本 `receipt_id` 作为 `evidence_ref`。

Receipt 默认保存在 Batch Contract、Audit Report 或独立管理索引中；Coverage Ledger 只需要记录受影响对象的最新有效 receipt IDs 和 invalidation state，不要求把完整 receipt 复制到每篇知识页。

## Reuse Gate

历史 receipt 只有同时满足以下条件才可复用：

```text
receipt.result = passed
AND current_scope is contained in receipt.scope
AND acceptance_predicate is unchanged or weaker
AND artifact_fingerprint matches
AND relevant dependency_fingerprint matches
AND contract_fingerprint matches the audited dimension
AND verifier remains accepted
AND review_due is empty or not reached
AND no applicable invalidation event exists
```

复用必须记录 `reused_receipt_id` 和复用理由，不能只写“此前已检查”。单批复用 ≤10 张 receipts 时，允许整批一次性声明复用理由。允许按维度部分复用：例如正文未变但新增 incoming links 时，`content_and_depth` 继续有效，`structure_and_links` 与 `coverage_and_integration` 重新计算。

以下情况不应触发无关维度重审：

- 另一个独立模块发生修改；
- 只更新 Progress Ledger 的文字说明；
- 未改变 claim 的排版修复，不应自动失效 source review；
- 未改变正文或 host contract 的链接修复，不应自动触发视觉识别。

## Invalidation

### Direct Invalidation

以下变化使对应 receipt 失效：

- scope 内文件内容、路径或 `artifact_fingerprint` 覆盖字段变化（排除字段的回写不失效，见字段语义）；
- acceptance predicate、note type、priority 或 Required disposition 变化；
- verifier 或 parser/compiler 版本发生不兼容变化；
- `review_due` 到期；
- 新证据直接推翻或限制已审 claim；
- 用户 correction 或 accepted guidance 改变被审语义；
- 审计本身发现 receipt 的输入不完整或结果错误。

### Dependency Invalidation

只传播到真正依赖该变化的维度：

| Changed dependency | Normally invalidates |
|---|---|
| canonical prerequisite mechanism | content/integration of dependent claims |
| Source Note or official current contract | source/currentness and dependent claims |
| Interview Card | interview mapping and migration coverage |
| path、heading or alias | structure/link and navigation integration |
| MOC、Coverage or Required Queue | coverage/integration and contract reconciliation |
| formula convention or metric denominator | formula/numeric and dependent evaluation claims |
| language/display contract | content/depth；若改变 heading、path 或 alias，再失效 structure/link 与 integration |
| theme、plugin or rendering contract | rendering receipts for affected constructs only |
| Standards gate semantics | receipts whose acceptance predicate became stricter or different |

Dependency graph 不要求把任意 backlink 视为语义依赖。正文中的 prerequisite、claim evidence、canonical ownership、Card mapping、MOC membership 和 contract mapping 才是主要 invalidation edges。

### Systemic Expansion

若一次定向检查发现可能影响同类页面的系统性问题：

1. 记录 failure signature 和 suspected family；
2. 使该 family 的对应维度 receipts 进入 `suspect`；
3. 扩大到有界 sample；
4. 若重复出现，失效整个 family 并建立 repair batch；
5. 修复后只重跑失效维度及其必要全局 invariants。

不能因为一个局部问题无界重审全库，也不能因抽样通过而覆盖已知失败。

## Content-level Propagation

当一篇笔记的机制性章节（Definition、Mechanism、公式、核心结论）发生实质修改时，作者必须沿本页定义的语义依赖边（prerequisite、claim-evidence）把直接下游笔记标记为 `needs_rereview`，并经本批 delta 的 `open_gaps_added`（type: rereview）记入 Coverage Ledger——并发下作者不直接写 Ledger（[[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] 写入权分区）。该标记汇入维护轮的候选清单按预算消化，不要求当场处理。同一页面在一个维护轮周期内只标记入池一次。复核动作是重读下游推理是否仍成立，不是重跑机械检查。

## Incremental Audit Planning

每个 batch 仅在关闭前生成一次 `AuditPlan`；批次开始只加载 Audit Receipt Register，不另做 AuditPlan：

```text
1. Freeze current artifact and contract snapshot.
2. Diff against the latest accepted snapshot.
3. Resolve direct and dependency invalidations.
4. Partition checks into:
   - mandatory full deterministic
   - changed-scope deterministic
   - invalidated semantic review
   - overdue (freshness) targeted review
   - bounded sampling
   - reusable evidence
5. Run checks and emit new receipts.
6. Reconcile invalidated, replaced and reused receipts.
7. Close only when required invalidations are zero.
```

## Batch-close Closed List

**Batch-close Closed List（批次关闭封闭清单）**：以下七项、仅以下七项，在每个 batch 由 integrator 串行合并关闭时对合并后的完整 in-scope snapshot 运行（并发批次逐个合并，见 [[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches）——

1. Wiki link missing / ambiguous / heading resolution（check_links）
2. Markdown / YAML / fence / table 结构有效性
3. graph JSON 与 duplicate **basename** candidates
4. Coverage file-count 对账
5. guidance ID 与 contract version 连续性
6. Interview 残留章节扫描（grep 级）
7. Frontmatter 受控词表校验（check_vocab，词表取自 `Tools/vocab.yaml`）

新检查进入本清单需 governance 修订，且必须满足：确定性脚本、全库单次运行 ≤60 秒。12/05 与 12/06 对本清单只引用，不另行开列。

它们是便宜且容易被其它页面修改破坏的全局 invariants。新结果 supersede 前一 receipt，而不是视为无意义重复。

## Incremental By Default

以下检查默认只覆盖 changed、invalidated、overdue 或 sampled scope（P0/P1 页面的长期保障由 freshness 到期复验承担，不设常驻人工审阅范围）：

- 机制、why-chain、failure 和 production depth 人工审阅；
- 中文解释完整性、`English（中文）` 顺序、英文保留边界和 reader-facing 表格语言审阅；
- 来源 claim 与正文语气逐项核验；
- Interview Card 中英文语义和 deep-dive 质量；
- 公式推导和数值上下文的深审；
- host-specific rendering exception。

## Specialized Audit Boundary

专项 Audit 必须先声明跨批次 invariant：

| Audit | Primary global question | Reuse boundary |
|---|---|---|
| Source Audit | identity/currentness、claim conflicts、promotion 和 affected-note propagation 是否一致 | 不重写未变页面的一般机制 |
| Case Audit | public fact、inference、recommendation、metric provenance 和 transferability 是否跨案例一致 | 复用已通过 canonical mechanism |
| Interview Audit | P0/P1 coverage、Card granularity、migration、双向导航和评分结构是否完整 | 不复制 canonical content review |
| Metadata Migration Audit | schema migration 是否守恒、状态是否有证据 | 不把 migration 当 authoring review |
| Full-scope Reconciliation | owner、scope、coverage、queue 和 graph 是否闭环 | 不替代 Terminal Proof |

如果专项 Audit 发现局部 receipt 已失效，应创建明确 repair item；不能在专项报告中静默重写页面后继续沿用旧 Batch Review。

## Terminal Reconciliation Rules

Terminal Audit 的 canonical 流程与 Terminal Proof 字段清单（含 `full_deterministic_results`）的 canonical 定义均位于 [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|12/06]]；本节只规定该流程中证据复用与失效对账的规则。

`unresolved_invalidations` 必须为 `0`。复用 receipt 不是降低标准；它要求证明被审对象和验收条件没有发生相关变化。

## Active-task Adoption

一次 Standards 修订的**受影响范围** = 修订记录中显式列出的 changed-predicate 清单（哪些 acceptance predicate 或 gate 语义发生变化）所对应的 receipts 与 batches。**修订记录未列出的，一律不受影响。**无 predicate 变化的修订（措辞、版本戳、瘦身、注释）走 no-op 路径：字节 diff + 一行 adoption receipt 即完成，不触发失效、不产 Amendment Record 表格。

Standards version 变化且 changed-predicate 清单非空时，active、paused 和 completion-candidate task 必须：

1. 记录旧、新 Standards version；
2. 重新解析本模块和受影响 gate modules；
3. 判断新规则是否改变现有 Batch/Terminal acceptance predicates；
4. 对无法满足新 receipt schema 的旧证据标记 `legacy-evidence`，而不是伪造 fingerprint；
5. 允许从当前 batch 开始生成完整 receipts；
6. Terminal Audit 对 legacy evidence 采用风险定向复核，不要求无差别重写已关闭 batch。

## Related

- [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]
- [[Knowledge Base Standards/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]
- [[Knowledge Base Standards/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger|Batch Execution and Progress Ledger]]
