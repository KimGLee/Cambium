## Navigation

- Parent: [[Knowledge Base Standards/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]].
- Next: [[Knowledge Base Standards/03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]].

## Purpose

本标准定义不同笔记类型的职责，避免把定义、机制、系统设计、案例和面试内容混在同一个文件中。

## Note Types

### Term Note

负责一个专有名词的 canonical definition、别名、直觉、形式化含义、例子和误区。

Term Note 不负责解释某个完整算法或系统如何工作，也不保存完整面试话术。

### Concept Note

负责解释一个机制或思想：问题来源、工作原理、假设、边界、例子、失败模式和应用。

例如：Bias-Variance Tradeoff、Backpropagation、Self-Attention、Grounded Generation。

### Process / Flow Note

负责解释一个过程如何从入口状态推进到可验证出口，包括参与者、authority、输入、前置条件、顺序、决策点、分支、循环、状态变化、外部副作用、失败处理和终止条件。

例如：Agent Basic Flow、Tool Calling Flow、RAG Pipeline、Training Loop、Release And Rollout Flow。

Process / Flow Note 不拥有每个组件的完整内部机制。它通过 wiki links 复用组件页面，但必须在当前流程中说明：

- 谁在该步骤作决定，谁真正执行。
- 输入、输出、状态和 authority 如何变化。
- 哪些步骤是确定性 Harness control，哪些是 model proposal。
- 何时 branch、loop、retry、timeout、cancel、pause 或 handoff。
- 外部副作用如何记录、确认、补偿或对账。
- 何时可以停止，以及 completion 如何被独立验证。

只有一条 happy-path 箭头链、没有控制与失败语义的页面，不满足 Process / Flow Note。

### Algorithm Note

负责算法的目标、核心思想、数学过程、训练与推理、复杂度、超参数、适用条件、优缺点、过拟合控制和解释方法。

例如：Decision Tree、SVM、K-Means、XGBoost。

### Metric Note

负责指标定义、公式、数值例子、适用场景、边界、阈值、与其它指标的冲突和常见误读。

Metric Note 不负责重复整个任务类型的定义。

### System Component Note

负责一个系统组件的职责、接口、输入输出、状态、生命周期、依赖、失败模式、观测和安全。

例如：Context Manager、MCP Client、Retriever、Budget Manager。

### System Design Note

负责完整系统：需求、架构、组件关系、数据流、API、状态、可靠性、安全、扩展、成本和替代方案。

例如：RAG Pipeline、Agent Harness、Model Serving Platform。

### Comparison Note

负责在统一维度下比较多个方案，并提供选择规则和边界案例。

例如：L1 vs L2、RAG vs Fine-tuning、MCP vs API Tool。

Comparison Note 不能只是两列优缺点列表。

### Risk And Control Note

负责威胁模型、攻击或失败路径、影响、检测、缓解、残余风险和验证方式。

例如：Data Leakage、Prompt Injection、Secret Leakage、Rate Limit。

### Source Note

负责忠实记录一个值得复用或持续追踪的外部来源：来源身份、问题背景、关键 claims、证据、限制、未证明内容和可能影响的知识页。

Source Note 不拥有通用定义、机制或行业结论，也不要求为每一个普通 URL 建立文件。

### Research Synthesis Note

负责围绕一个研究问题综合多个来源：术语映射、共同观察、冲突、证据强弱、厂商特定选择、可推广机制、开放问题和建议的知识图谱变更。

Research Synthesis 可以承载尚在形成的前沿问题，但不能长期代替已经稳定的 canonical concept、system 或 risk/control notes。

### Case Study

负责把已有知识用于真实问题：需求、约束、决策、架构、end-to-end flow、tradeoff、故障、指标来源、安全、上线过程和复盘。

Case Study 不拥有基础概念定义，必须链接 canonical notes，并区分公开事实、合理推断和知识库建议。

### Interview Card

负责 30 秒、90 秒、追问树、误区、评分信号和自测。详细规则见 [[Knowledge Base Standards/11 Interview Content Standard|Interview Content Standard]]。

### Overview / MOC

负责领域边界、模块关系、主要入口、prerequisite chain 和 coverage navigation。Overview / MOC 不拥有叶子知识的完整机制，也不能用链接列表代替模块关系解释。

### Roadmap

负责学习或准备顺序、优先级和验收节点，不承担核心知识解释。

### Cheat Sheet

负责压缩复习和快速定位，所有详细解释必须链接回 canonical notes。

### Standards And Management Note

负责规则、Coverage Ledger、覆盖矩阵、进度、审计结果和迁移记录，不进入正常知识学习主线。

## Type And Depth Fit

Note type 决定页面承担什么责任，depth class 决定需要回答到什么程度：

- Term Note 通常是 `atomic`，可以有意保持简洁。
- Concept、Comparison 和 Metric 通常是 `core`。
- Process / Flow 根据范围可以是 `core` 或 `system`。
- System Component 和完整 System Design 通常是 `system`。
- Source Note 和 Research Synthesis 由 claim coverage 和 evidence boundary 决定，不按篇幅升级。

行数只能用于发现异常，不能改变 note type，也不能证明 depth。不能把本应解释机制或生产流程的页面标成 Term Note 来规避 Core / System 深度要求。
