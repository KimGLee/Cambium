## Navigation

- Parent: [[Knowledge Base Standards/07 Sources and Accuracy Standard|07 Sources and Accuracy Standard]].
- Next: [[Knowledge Base Standards/07 Sources and Accuracy/02 Claims Sources and Classification|Claims Sources and Classification]].

## Purpose

本标准规定知识来源、事实核验、数学准确性和时效性管理，避免内容看起来完整但无法验证或已经过时。

## Source Hierarchy

优先级从高到低：

1. 原始论文、正式规范、标准和官方技术报告。
2. 官方文档、教材、大学课程资料。
3. 权威机构或核心维护者的技术文章。
4. 高质量二手解释，用于辅助直觉。
5. 社区内容，只用于补充实践经验，不能单独支撑关键结论。

技术问题使用一手来源核对。协议、API、框架和版本行为优先官方文档。

来源层级只回答“来源通常有多可靠”，不能回答“该来源在当前论证中证明了什么”。具体 source-to-knowledge 准入遵循 [[Knowledge Base Standards/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]。

## Source Authority And Evidence Role

每个重要来源需要同时判断：

- Source authority：作者是否直接拥有数据、系统或实验信息。
- Evidence role：它用于发现问题、解释机制、证明实现、提供实验、展示失败还是反驳结论。
- Applicability boundary：结论适用于哪些模型、任务、Harness、组织和时间范围。
- Potential bias：是否存在厂商宣传、选择性披露、社区幸存者偏差或 benchmark 激励。

社区内容权威级别通常较低，但可以是高价值 discovery signal 或 failure evidence；官方公司文章可以证明其公开系统，却不能自动证明行业普遍规律（详见 [[Knowledge Base Standards/07 Sources and Accuracy/03 Official and Cross-source Verification|07/03]]）。

七种 evidence roles 的 canonical 定义见 [[Knowledge Base Standards/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|06/03]] Stage 4。
