## Navigation

- Parent: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Next: [[kernel/04 Content Depth/02 Core Concept Structure|Core Concept Structure]].

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

适合单一术语或参数，例如 Timeout、Checksum、Lease。

至少覆盖：定义、作用、直觉、一个例子、边界、误区、使用位置和相关概念。

软性篇幅参考：500–1200 个由所选 profile 的 `Language Contract` 定义的内容长度单位。

### Core

适合高频核心机制，例如 Transaction Isolation、Eventual Consistency、Control Loop、Caching。

至少覆盖：问题来源、机制、公式或流程、假设、worked example、选择规则、替代方案、失败模式、评估和工程考虑。

软性篇幅参考：1500–3000 个由所选 profile 的 `Language Contract` 定义的内容长度单位。

### System

适合组件和完整系统，例如 Task Scheduler、Message Broker、Order Processing Platform。

至少覆盖：目标、非目标、需求、组件、接口、数据流、状态、生命周期、并发、失败、安全、观测、扩展、成本和替代方案。

软性篇幅参考：2500–6000 个由所选 profile 的 `Language Contract` 定义的内容长度单位。

篇幅只用于发现异常，不能用无信息密度的重复内容凑长度。

## Foundation Depth Rule

所选 profile 的知识主线不降低基础页面的深度要求。

基础知识页应能脱离 profile 应用页独立学习；profile 应用页则必须能够沿 prerequisites 回溯到完整基础解释。逐学科要求由 `Profile Scope` 的 `Foundation Depth Requirements` 登记。
