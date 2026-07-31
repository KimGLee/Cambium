## Navigation

- Parent: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Previous: [[kernel/04 Content Depth/05 Source and Evaluation Depth|Source and Evaluation Depth]].

## Example Standard

重要主题应尽量包含三类例子：

- Minimal example：用最小输入展示机制。
- Real-world example：说明在业务或生产系统中的使用。
- Failure example：展示错误使用、边界或反例。

数学主题需要数值例子；系统主题需要 data flow；风险主题需要 attack / failure path。

## Deep-Dive Standard

每个 P0 / P1 核心主题至少建立一条三层以上的 why-chain：

```text
Why is it needed?
 -> Why does the naive solution fail?
 -> Why does this mechanism help?
 -> Under what assumption does it stop helping?
 -> How would we detect that failure?
```

正文必须提供答案，不能只列问题。

## Failure And Debugging Standard

不能只写笼统缺点。Failure Mode 应说明：

- Trigger：什么条件触发。
- Symptom：观察到什么现象。
- Root cause：底层原因是什么。
- Detection：通过什么指标或日志发现。
- Mitigation：如何缓解。
- Residual risk：仍有什么风险。

## Anti-patterns

- 只有 Definition、Advantages、Disadvantages。
- 每个 section 只有一句话。
- 把同一个定义换词重复三次。
- 只讲理想路径，不讲假设和失败。
- 只有公式，没有符号解释和数值例子。
- 只有流程图，没有说明每一步为什么存在。
- 把复杂过程画成无分支、无循环、无失败路径的一条直线。
- 把 proposer 的提议、gatekeeper 的授权和 executor 产生的 external effect 合并成一个“system executes”步骤。
- 为了让图适配视口而删除关键 transition、状态或 recovery path。
- 用大量链接代替当前页面应承担的机制说明。
- 结尾有 Expression Layer Answer，但正文不足以支撑追问。
- 为突出某 profile 应用主线，把基础页面压缩成只说明“在当前应用中如何使用”。
- 把文章摘要直接当作 canonical mechanism explanation。
- 系统页面只有组件列表，没有 execution、state、coordination、evidence 和 recovery paths。

## Related

- [[kernel/03 Note Types and Ownership Standard|Note Types and Ownership Standard]]
- [[Knowledge Base Standards/07 Sources and Accuracy Standard|Sources and Accuracy Standard]]
- [[Knowledge Base Standards/12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
