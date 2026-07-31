## Navigation

- Parent: [[Knowledge Base Standards/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]].
- Previous: [[Knowledge Base Standards/07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]].
- Next: [[Knowledge Base Standards/07 Sources and Accuracy/05 Time Formula Terminology and Uncertainty|Time Formula Terminology and Uncertainty]].

## Evaluation Provenance

任何 Accuracy、success rate、pass rate、benchmark improvement 或生产效果数字，都必须说明：

```text
Task Definition
 -> Dataset And Sampling
 -> Ground Truth
 -> Trial Setup And Repeat Count
 -> Model + Prompt + Harness + Tools + Environment
 -> Grader
 -> Metric And Aggregation
 -> Uncertainty And Slice Analysis
 -> Leakage Contamination Or Selection Bias Check
 -> Reproduction Boundary
```

Reproduction Boundary 必须说明结论可以复现到什么程度以及复现边界在哪里。无法获得的要素必须显式记录为 `unknown` 并说明原因。

Agent evaluation 还需要区分 transcript、trajectory 和 final environment outcome。非确定性任务不能只给单次运行结果；应说明 trial 数、方差、一致性和失败分布。

## Source Quality

- 链接必须直接支持对应结论。
- 不使用搜索结果页作为来源。
- 不用一篇无关文章支撑多个不同结论。
- 不把厂商营销语言当作中立事实。
- 多种实现不同的地方明确标注“implementation-specific”。
- 经验性建议标注适用环境和限制。
