## Navigation

- Parent: [[Knowledge Base Standards/04 Content Depth Standard|04 Content Depth Standard]].
- Next: [[Knowledge Base Standards/04 Content Depth/02 Core Concept Structure|Core Concept Structure]].

## Purpose

本标准定义“内容足够详细”的可检查含义，避免核心页面只停留在定义、两三句解释或优缺点列表。

## Depth Is Question Coverage

深度不等于字数。一个主题是否讲透，应检查它能否回答：

1. 它解决什么问题？
2. 为什么这个问题会出现？
3. 朴素方案为什么不够？
4. 核心机制是什么？
5. 机制依赖哪些假设？
6. 数学、数据流或执行过程是什么？
7. 有什么最小例子？
8. 什么时候应该使用？
9. 什么时候不应该使用？
10. 替代方案是什么？
11. 主要 tradeoff 是什么？
12. 会如何失败？
13. 如何检测和调试失败？
14. 如何评估结果？
15. 在生产系统中还要考虑什么？

## Depth Classes

### Atomic

适合单一术语或参数，例如 Epoch、Top-p、Logits。

至少覆盖：定义、作用、直觉、一个例子、边界、误区、使用位置和相关概念。

软性篇幅参考：500–1200 个中文字。

### Core

适合高频核心机制，例如 Bias-Variance、Backpropagation、Self-Attention、RAG。

至少覆盖：问题来源、机制、公式或流程、假设、worked example、选择规则、替代方案、失败模式、评估和工程考虑。

软性篇幅参考：1500–3000 个中文字。

### System

适合组件和完整系统，例如 Context Manager、Agent Harness、Serving Platform。

至少覆盖：目标、非目标、需求、组件、接口、数据流、状态、生命周期、并发、失败、安全、观测、扩展、成本和替代方案。

软性篇幅参考：2500–6000 个中文字。

篇幅只用于发现异常，不能用无信息密度的重复内容凑长度。

## Foundation Depth Rule

以 Agent/Harness 为知识主线不降低基础页面的深度要求。

- 数学与统计页面要解释定义、公式、假设、直觉、数值例子和边界。
- ML/DL 页面要解释训练或推理机制、数据要求、评估、失败和选择依据。
- LLM 页面要解释模型行为的来源，不能只写“Agent 会使用它”。
- Retrieval/RAG 页面要解释检索、排序、grounding 和 evaluation，不能退化为 Agent 工具清单。
- Agent/Harness 页面通过 wiki links 使用基础知识，只补充当前系统语境，不复制完整基础机制。

基础知识页应能脱离 Agent 页面独立学习；Agent 页面则必须能够沿 prerequisites 回溯到完整基础解释。
