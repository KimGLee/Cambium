## Navigation

- Parent: [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]].
- Next: [[Knowledge Base Standards/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|User Guidance Hypotheses and Source Leads]].

## Purpose

本标准规定外部信息如何进入知识库、如何转化为可验证的知识对象，以及何时更新、新建、拆分、合并、暂缓或废弃 Markdown 页面。

它解决的不是“如何给一篇文章写摘要”，而是：

```text
外部世界出现新信息后，知识图谱应该发生什么变化？
```

## Scope

本标准适用于：

- OpenAI、Anthropic 和其它机构的官方 engineering / research articles。
- 论文、benchmark、技术报告、标准和协议更新。
- 生产 case study、postmortem 和公开架构说明。
- 高质量社区讨论、issue、经验总结和新出现的实践问题。
- 现有知识页在学习、面试或工程分析中暴露出的新缺口。

它不替代 [[Knowledge Base Standards/07 Sources and Accuracy Standard|Sources and Accuracy Standard]]。Sources and Accuracy 判断结论是否有可靠依据；本标准判断这些依据应如何改变知识库。

## Core Model

必须区分以下对象：

```text
Source != Claim != Knowledge Object != Markdown File
```

- Source 是文章、论文、讨论、代码、benchmark 或 postmortem。
- Claim 是来源中可以单独判断真伪和适用范围的主张。
- Knowledge Object 是需要被长期维护的术语、机制、组件、系统、风险、控制或案例。
- Markdown File 是知识对象在当前 Obsidian 架构中的承载方式。

不能看到一个新词或文章标题就直接创建同名 canonical note。

## Many-to-many Rule

Source 与 knowledge notes 是 many-to-many 关系：

- 一篇文章可能更新多个已有页面并产生多个新知识对象。
- 多篇文章可能共同支撑一个 Research Synthesis 或 canonical note。
- 一次社区讨论可能只形成待验证 signal，不产生新的 canonical note。
- 一个 canonical note 应尽量由多个独立来源支撑，而不是绑定单一厂商叙事。

知识库结构由问题、机制、边界和复用关系决定，不由文章来源目录决定。
