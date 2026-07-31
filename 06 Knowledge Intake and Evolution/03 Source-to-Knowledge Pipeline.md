## Navigation

- Parent: [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]].
- Previous: [[Knowledge Base Standards/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|User Guidance Hypotheses and Source Leads]].
- Next: [[Knowledge Base Standards/06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles|Intake Note Types and Source Roles]].

## Source-to-Knowledge Pipeline

```text
Environmental Scanning
 -> Source Capture
 -> Claim Extraction
 -> Evidence Classification
 -> Cross-source Synthesis
 -> Knowledge Gap Analysis
 -> Graph Impact Decision
 -> Note Creation Or Update
 -> Integration And Verification
 -> Maintenance Or Supersession
```

### Stage 1: Environmental Scanning

目标是发现值得调查的变化，而不是立即把热门话题写成结论。

需要记录：

- 新出现的问题、能力、失败模式或工程模式。
- 发现来源和首次发现日期。
- Originating guidance ID，适用于用户提供的 hypothesis 或 source lead。
- 与 Agent/Harness 主线的关系。
- 它可能影响的现有模块。
- 为什么值得进一步调查。

社区热度可以触发调查，但不能单独触发 canonical promotion。

增量扫描语义：

- 默认只扫描 `Tools/state/watermark.yaml`（schema 见 `Tools/schemas/watermark.template.yaml`）中 `scanned_until` 之后出现的新材料。
- 水位线按 domain 分节记录已覆盖来源与覆盖截止日期。
- 批次关闭时随 Ledger 一起推进水位线。
- 全量重扫是显式例外，仅用于新领域接入或水位线可疑时，且必须在 Ledger 记录理由。

### Stage 2: Source Capture

对进入研究流程的来源建立可追踪记录：

- Title、author / organization、publication date 和 URL。
- Source 是用户提供的实际文档、artifact 或可核验记录，而不是转述动作本身。
- Source type 和 source authority。
- 原文要解决的问题。
- 原文提供的系统、实验或案例边界。
- 原文没有证明的内容。
- 潜在利益相关、厂商偏差和缺失信息。

只有确实会被复用、对照或持续追踪的来源才建立独立 Source Note。普通引用不需要为每个 URL 创建文件。

### Stage 3: Claim Extraction

把来源拆成可独立核验的 claims，而不是保存一段模糊摘要。

每个关键 claim 至少记录：

- Claim statement。
- Claim type。
- Supporting evidence。
- Conditions and assumptions。
- Scope of applicability。
- Source location。
- Confidence and open questions。

推荐使用以下 claim labels：

- `Reported Claim`：来源明确报告的事实、实验或实现。
- `Reasoned Inference`：根据来源作出的合理推断，但不是原文直接结论。
- `Cross-source Synthesis`：综合多个来源形成的知识库判断。
- `Engineering Recommendation`：基于证据和约束给出的实践建议。

这些标签不能混用。尤其不能把推断改写成厂商已经证实的事实。

### Stage 4: Evidence Classification

来源不能只按“权威或不权威”排序，还要说明它承担什么证据角色。

常见 evidence roles：

- `discovery-signal`：发现新问题或实践痛点。
- `mechanism-evidence`：解释为什么会发生。
- `implementation-evidence`：证明某个系统实际如何实现。
- `empirical-evidence`：提供实验、benchmark 或生产数据。
- `generalization-evidence`：证明结论能否跨模型、团队或场景成立。
- `failure-evidence`：提供失败链路、incident 或反例。
- `contradicting-evidence`：与已有结论冲突。

同一个来源可以承担多个角色，但必须逐项说明依据。

### Stage 5: Cross-source Synthesis

多个来源围绕同一问题时，必须比较：

- 使用的术语是否实际指向同一现象。
- 共同观察是什么。
- 实现选择为什么不同。
- 实验条件和系统边界是否可比。
- 哪些结论互相冲突。
- 哪些只是厂商或模型特定行为。
- 当前证据足以支持什么，不足以支持什么。

当结论仍在形成或跨越多个知识对象时，应建立 Research Synthesis Note，而不是提前制造一个稳定术语。

### Stage 6: Knowledge Gap Analysis

写入前先检查现有知识图谱：

- 是否已经存在同义或相近 canonical note。
- 新信息是补充定义、机制、案例、失败模式还是评估方法。
- 现有页面是否 ownership 错误或粒度过大。
- 新知识是否会被两个以上页面复用。
- 是否需要先补一个前置基础页面。
- 是否只是来源特定细节，不具有独立知识价值。

Knowledge gap 必须以“缺失的问题或机制”描述，不能只写“缺少这篇文章”。

### Stage 7: Graph Impact Decision

每组新证据只能选择有依据的动作：

| Condition | Action |
|---|---|
| 只补强已有结论 | Add source or refine existing section |
| 发现已有页面缺少机制或失败模式 | Expand canonical note |
| 出现可复用且边界明确的新知识对象 | Create canonical note |
| 一个页面承担多个独立 owner | Split existing note |
| 多个页面实际重复 | Merge into one canonical owner |
| 多来源围绕尚未稳定的问题 | Create Research Synthesis Note |
| 描述特定公司或系统的落地 | Create or update Case Study |
| 只有早期社区信号 | Capture as signal and monitor |
| 证据不足或无法核验 | Defer and record open question |
| 新证据推翻旧结论 | Mark contested or superseded |

一个来源可以触发多个动作，但每个动作都需要独立说明 graph value。

### Stage 8: Note Creation And Integration

创建或更新页面时必须同步：

- Canonical ownership。
- Parent、prerequisites、components、applications 和 failure/control links。
- Source Note、Research Synthesis、Case Study 与 canonical notes 的显式关系。
- Overview / MOC 和 coverage map。
- 需要时的 Interview Card 和 Question Bank。
- Metadata、authoring status、interview status、coverage disposition、evidence maturity 和 review dates。

不得只创建孤立页面，等待未来再补关系。

### Stage 9: Verification And Promotion

新页面从外部来源进入 canonical knowledge 前，必须通过 promotion gate：

1. Knowledge object 有明确问题、边界和 owner。
2. 关键 claims 可以追溯到具体来源。
3. Reported fact、inference、synthesis 和 recommendation 已区分。
4. 来源适用范围和厂商特定条件已说明。
5. 已检查同义页面和重复定义。
6. 证据成熟度与正文语气一致。
7. 页面达到对应 depth class，不是来源摘要或空壳。
8. Wiki links、Sources、metadata 和 rendering 已验证。

未通过 promotion gate 的内容可以保留为 Source Note 或 Research Synthesis，但不得标记为稳定 canonical knowledge。

### Stage 10: Maintenance And Supersession

前沿 Agent/Harness 知识需要持续维护：

- 新来源是否支持、限制或反驳现有结论。
- 模型能力变化是否让旧 Harness assumption 失效。
- Benchmark、API、工具和系统环境是否变化。
- 一个 emerging pattern 是否已获得独立复现。
- 旧术语是否被更准确的分类取代。

被替代的页面或结论应保留 supersession 关系和原因，不能静默删除历史判断。
