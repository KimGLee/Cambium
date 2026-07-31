## Navigation

- Parent: [[Knowledge Base Standards/11 Interview Content Standard|11 Interview Content Standard]].
- Previous: [[Knowledge Base Standards/11 Interview Content/01 Interview Architecture and Separation|Interview Architecture and Separation]].
- Next: [[Knowledge Base Standards/11 Interview Content/03 Card Structure and Answer Levels|Card Structure and Answer Levels]].

## Interview Card Granularity

不要求每个知识页一对一生成 Interview Card。

单独建卡：

- 高频核心概念。
- 能产生三个以上独立追问。
- 有独立机制、tradeoff 和失败模式。
- 需要超过 90 秒才能完整讲清。

合并建卡：

- 同一机制下的多个原子参数。
- 常被放在同一道比较题中的指标。
- 单独内容很短、拆分后会碎片化的主题。

例如：Temperature、Top-p、Max Tokens、Stop Sequence 可以组成 `Generation Controls Interview Card`。

## Interview Coverage Status

每个 P0 / P1 canonical topic 都必须在 Coverage Ledger 中记录 `interview_status`：

- `missing`：需要面试覆盖但没有映射。
- `mapped`：已确定目标 Interview Card。
- `drafted`：Card 已写入但尚未通过 Interview Review。
- `reviewed`：Card 已通过内容和双语审阅。
- `interview-ready`：canonical knowledge 与 Card 都通过相应验收。
- `not-required`：按 granularity policy 不需要独立 Card，必须说明由哪个合并 Card 覆盖或为什么不需要。

一个 Interview Card 可以覆盖多个紧密相关的 canonical notes，但每个知识页仍需能导航到该 Card。知识页有 Card link 只表示 `mapped`，不能自动升级为 `interview-ready`。

## Interview Card Categories

### Concept Card

负责定义、机制、比较、失败模式和使用边界，主要引用 canonical Term / Concept / Algorithm / Metric Notes。

### System Design Card

负责端到端架构、组件 contract、状态、协调、评估、可靠性、安全、扩展和成本，主要引用 System Component / System Design Notes。

### Project Deep Dive Card

负责把真实项目或行业案例转化为可验证的面试表达：业务问题、个人职责、架构决策、指标来源、上线方式、失败复盘和改进。

Project Deep Dive 不能只背案例结论，也不能把 Source Note 中未经综合的 claim 当作项目事实。
