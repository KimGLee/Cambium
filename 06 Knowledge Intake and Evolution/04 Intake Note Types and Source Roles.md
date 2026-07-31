## Navigation

- Parent: [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]].
- Previous: [[Knowledge Base Standards/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]].
- Next: [[Knowledge Base Standards/06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy|Evidence Maturity and Batch Policy]].

## Note Types In The Intake Layer

### Source Note

Source Note 忠实描述单一来源：

```text
Source Identity（来源标识）
Problem Addressed（针对的问题）
System Or Experiment Context（系统或实验上下文）
Key Claims（关键主张）
Evidence Provided（提供的证据）
Assumptions And Scope（假设与适用范围）
Limitations（局限性）
What The Source Does Not Establish（该来源不能证明什么）
Affected Knowledge Notes（受影响的知识笔记）
Open Questions（未决问题）
```

Source Note 不拥有通用定义和机制。

### Research Synthesis Note

Research Synthesis Note 围绕一个问题整合多个来源：

```text
Research Question（研究问题）
Source Set And Selection Boundary（来源集合与选取边界）
Terminology Mapping（术语映射）
Agreements（一致结论）
Disagreements（分歧）
Evidence Comparison（证据对比）
Generalizable Mechanisms（可泛化机制）
Vendor-specific Choices（厂商特定选择）
Unresolved Questions（未解决问题）
Recommended Graph Changes（建议的图谱变更）
```

Research Synthesis 不是永久替代 canonical notes。结论稳定后，应把机制提升到正确 owner，并让 synthesis 保留研究过程、分歧和来源关系。

## Source Role Policy

### Official Company Sources

OpenAI、Anthropic 和其它公司官方文章在 intake 中作为一手 implementation evidence，用于证明该公司公开披露的系统、实验和工程经验，不自动证明行业普遍规律。canonical 政策见 [[Knowledge Base Standards/07 Sources and Accuracy/03 Official and Cross-source Verification|07/03]]。

### Community Sources

社区讨论在 intake 中主要作为 discovery signal 和 failure evidence，用于发现问题、收集实践经验并形成需要进一步验证的 hypothesis；社区共识不等于事实。canonical 层级与角色定位见 [[Knowledge Base Standards/07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|07/01]]。

### Papers Benchmarks And Reproductions

- 论文负责理论、方法和受控实验，不自动代表生产表现。
- Benchmark 必须同时记录 task、dataset、grader、harness 和 contamination 风险。
- 独立复现用于判断结论是否能跨实现成立。
- Postmortem 对 failure path 和 recovery 有高价值，但结论仍受具体系统约束。
