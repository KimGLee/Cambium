## Navigation

- Parent: [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]].
- Previous: [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]].
- Next: [[kernel/06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy|Evidence Maturity and Batch Policy]].

## Note Types In The Intake Layer

### Source Note

A Source Note faithfully describes a single source:

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

A Source Note does not own general definitions or mechanisms.

### Research Synthesis Note

A Research Synthesis Note integrates multiple sources around one question:

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

A Research Synthesis is not a permanent replacement for canonical notes. Once conclusions stabilize, the mechanisms SHOULD be promoted to the correct owner, with the synthesis retaining the research process, disagreements, and source relationships.

## Source Role Policy

### Official Company Sources

In intake, official articles from different companies serve as primary implementation evidence, used to prove the systems, experiments, and engineering experience that company has publicly disclosed; they do not automatically prove industry-wide laws. The canonical policy is in [[kernel/07 Sources and Accuracy/03 Official and Cross-source Verification|07/03]].

### Community Sources

In intake, community discussions serve mainly as discovery signals and failure evidence, used to discover problems, collect practice experience, and form hypotheses requiring further verification; community consensus is not fact. The canonical hierarchy and role positioning are in [[kernel/07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|07/01]].

### Papers Benchmarks And Reproductions

- Papers are responsible for theory, methods, and controlled experiments; they do not automatically represent production performance.
- A benchmark MUST record task, dataset, grader, harness, and contamination risk together.
- Independent reproductions are used to judge whether conclusions hold across implementations.
- Postmortems are high-value for failure paths and recovery, but their conclusions remain constrained by the specific system.
