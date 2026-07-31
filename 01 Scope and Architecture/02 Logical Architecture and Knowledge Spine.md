## Navigation

- Parent: [[Knowledge Base Standards/01 Scope and Architecture Standard|01 Scope and Architecture Standard]].
- Previous: [[Knowledge Base Standards/01 Scope and Architecture/01 Scope Boundaries|Scope Boundaries]].
- Next: [[Knowledge Base Standards/01 Scope and Architecture/03 Foundation Preservation|Foundation Preservation]].

## Logical Architecture

未来知识库采用“基础层支撑、Agent/Harness 组织、生产系统落地、评估与安全横切”的结构，而不是把所有主题平铺在顶层：

```text
Foundational Knowledge
  -> Agent Decision And Reasoning
  -> Harness Runtime And Control
  -> Production Agent Systems

Evaluation / Reliability / Safety / Governance
  -> cross-cut every layer

Source Notes / Research Synthesis
  -> continuously update the knowledge graph

Case Studies / Interview Preparation
  -> reuse canonical knowledge
```

这是一种 logical center，不要求立即把所有物理目录移动到 Agent 文件夹下。

## Knowledge Spine

Agent/Harness 主线按以下端到端链路组织：

```text
User Goal
 -> Agent Decision And Planning
 -> Harness Context And Policy
 -> Orchestration
 -> Tool And Environment Execution
 -> State And Artifacts
 -> Verification
 -> Recovery
 -> Outcome And Evaluation
```

每个系统主题应说明它位于链路的哪里、依赖哪些基础知识、影响哪些下游环节。基础页面负责完整机制，Agent/Harness 页面只解释该机制在当前系统中的作用并通过 wiki links 复用。
