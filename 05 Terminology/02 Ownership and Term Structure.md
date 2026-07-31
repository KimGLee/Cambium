## Navigation

- Parent: [[Knowledge Base Standards/05 Terminology Standard|05 Terminology Standard]].
- Previous: [[Knowledge Base Standards/05 Terminology/01 Terminology Extraction|Terminology Extraction]].
- Next: [[Knowledge Base Standards/05 Terminology/03 Naming Context and Linking|Naming Context and Linking]].

## Ownership

术语使用“最低合理归属”规则：

1. 有明确领域归属：放在该领域。
2. 多领域复用且有基础学科归属：放在 Shared Foundations。
3. 生产系统通用：放在 AI Systems Engineering。
4. 真正跨领域且无自然 owner：放在未来 `Shared Concepts`。
5. 面试表达不改变术语 owner，Interview Card 只引用它。

不建议建立一个无分类、无限增长的全局 Glossary 文件夹。

## Suggested Structure

```text
Shared Concepts/
├── Mathematics/
├── Data/
├── Evaluation/
├── Systems/
├── Security/
└── Terminology Index.md
```

领域专属术语可以使用：

```text
Deep Learning Knowledge/Terminology/
LLM Knowledge/Terminology/
Agent Knowledge/Terminology/
AI Systems Engineering/Terminology/
```

该结构需要在整体架构确认后再创建，当前规则不自动移动现有术语页。

## Term Note Structure

一个完整 Term Note 通常包含：

```text
Full Name And Aliases（全称与别名）
Definition（定义）
Why This Term Exists（术语存在的原因）
Intuition（直觉理解）
Formal Meaning（形式化含义）
Notation / Data Structure（记号 / 数据结构）
Minimal Example（最小示例）
Where It Is Used（使用场景）
What It Is Not（它不是什么）
Common Misconceptions（常见误解）
Interview Preparation Link（面试准备链接）
Related Terms（相关术语）
Sources（来源）
```

涉及数学时增加公式；涉及系统时增加输入输出和生命周期；涉及协议时增加角色、边界和版本信息。
