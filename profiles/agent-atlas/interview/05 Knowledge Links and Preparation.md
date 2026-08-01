## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Parent: [[profiles/agent-atlas/interview/11 Interview Content Standard|11 Interview Content Standard]].
- Previous: [[profiles/agent-atlas/interview/04 System Deep Dive and Bilingual Policy|System Deep Dive and Bilingual Policy]].
- Next: [[profiles/agent-atlas/interview/06 Roadmap and Question Bank|Roadmap and Question Bank]].
- Expression layer contract: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]].
- Kernel terminology contract: [[kernel/05 Terminology Standard|05 Terminology Standard]].
- Kernel link and navigation contract: [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]].

## Terminology Extraction Trigger

- 面试中可能被单独追问。

## Terminology Ownership Boundary

面试表达不改变术语 owner，Interview Card 只引用它。

## Knowledge Links

知识页引用 Interview Card：

```markdown

## Interview Preparation

- Interview Card: `Interview Preparation/Topic Cards/Agent/Agent Harness Interview Card`
```

Interview Card 创建后，该路径必须替换为实际可解析的 wiki link；标准文件不预先制造 unresolved links。

Interview Card 引用 canonical knowledge：

```markdown

## Core Knowledge Links

- [[Agent Knowledge/Harness/Agent Harness|Agent Harness]]
- [[Agent Knowledge/Harness/Tool Registry|Tool Registry]]
- [[Agent Knowledge/Harness/Permission System|Permission System]]
```

需要时链接知识页具体章节，而不是复制章节内容。

Research Synthesis 可以作为前沿问题的补充阅读，但进入标准面试答案的关键结论应已经提升到 reviewed canonical notes，或明确标注为 emerging / contested。

## Interview Relationship

Term Note 不保存完整面试回答，只保存 Interview Card 链接：

```markdown

## Interview Preparation

- Interview Card: `Interview Preparation/Topic Cards/<Domain>/<Term> Interview Card`
```

对应 Interview Card 创建后，这一普通路径应替换为可解析的 wiki link。Interview Card 通过 `Knowledge Prerequisites` 反向引用 Term Note。

## Interview Link Relationship

- Interview：知识页与 Interview Card 的关系。

## P0 / P1 Structural Link

- 对应 Interview Card，适用于 P0 / P1 主题。

## Bidirectional Link Routes

```text
Knowledge Note <-> Interview Card
Roadmap -> Knowledge Note + Interview Card
Question Bank -> Interview Card
```

## Roadmap Routing

- Roadmap：学习顺序，未来归入 Interview Preparation 或 Learning Roadmap。

## Kernel Binding

- Kernel role: `Expression Layer Artifact`
- Expression layer owner: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]]
- Acceptance owner: `Terminology Acceptance`
